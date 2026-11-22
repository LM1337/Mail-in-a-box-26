#!/usr/bin/env python3
"""Checks how System > Intrusion Detection and Prevention recognises Microsoft's servers (B126).

No box needed. management/cloud_relays.py tells a banned address of the
servers through which Outlook for iOS and Android syncs Exchange ActiveSync
accounts by Microsoft's published IP ranges in
conf/fail2ban/microsoft-relays.txt, and shows the address's PTR name only
when that name resolves back to the address. This test checks:

  * the shipped file: its header (sources, version, date, SHA256 sums), IPv4
    and IPv6 networks, the AutoDetect ranges, every network accepted by the
    allowlist; a file changed by hand (a network added, removed or changed,
    a line that is no network) is refused;
  * the matching: addresses inside and just outside the ranges, IPv4 and
    IPv6, an IPv4-mapped IPv6 address, the most specific network, invalid
    input;
  * forward-confirmed reverse DNS with stand-in lookups: a confirmed name,
    a spoofed PTR name without a forward match (also one that names
    Microsoft), a name that resolves to another address, failing lookups,
    names with characters a host name cannot have, IPv6 through AAAA;
  * relay_hints(): only addresses in the ranges get a hint, the name only
    when confirmed, at most MAX_LOOKUPS lookups;
  * tools/update-microsoft-relays.py: only the service area Exchange of a
    web service answer is taken, with the AutoDetect ranges.

Usage: python3 -I tests/fork/cloud-relays.py
Exit code 0 when every check passed.
"""
import importlib.util
import ipaddress
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "management"))
import cloud_relays as cr  # noqa: E402
import fail2ban_admin as f2b  # noqa: E402

FAILED = []


def check(name, got, want):
	if got != want:
		FAILED.append(name)
		print(f"FAIL {name}\n  want: {want!r}\n  got:  {got!r}")
	else:
		print(f"ok   {name}")


def refused(text):
	try:
		cr.parse(text)
	except ValueError as e:
		return str(e)
	return None


with open(cr.DATA_FILE, encoding="ascii") as f:
	SHIPPED = f.read()
HEADER, NETS = cr.parse(SHIPPED)


def case_file():
	h = HEADER
	check("file: source is Microsoft's web service, service area Exchange",
		h.get("source", "").startswith("https://endpoints.office.com/endpoints/Worldwide?ServiceAreas=Exchange&"), True)
	check("file: version, date and SHA256 of the answer",
		(bool(re.fullmatch(r"\d{10}", h.get("source-version", ""))), bool(re.fullmatch(r"\d{4}-\d\d-\d\d", h.get("retrieved", ""))),
		 bool(re.fullmatch(r"[0-9a-f]{64}", h.get("source-sha256", "")))), (True, True, True))
	check("file: the AutoDetect ranges of the other page", h.get("extra-source", "").startswith("https://learn.microsoft.com/")
		and all(ipaddress.ip_network(n) in NETS for n in h.get("extra-networks", "").split()) and len(h.get("extra-networks", "").split()) >= 1, True)
	check("file: IPv4 and IPv6 networks", (sum(n.version == 4 for n in NETS) > 5, sum(n.version == 6 for n in NETS) > 5), (True, True))
	bad = []
	for n in NETS:
		try:
			f2b.parse_network(str(n))
		except ValueError as e:
			bad.append(str(e))
	check("file: every network is accepted by the allowlist", bad, [])

	lines = SHIPPED.splitlines(True)
	first = next(i for i, l in enumerate(lines) if not l.startswith("#"))
	check("file changed by hand: a network added", refused(SHIPPED + "192.0.2.0/24\n") is not None, True)
	check("file changed by hand: a network removed", refused("".join(lines[:first] + lines[first + 1:])) is not None, True)
	check("file changed by hand: a network widened", refused(SHIPPED.replace("\n40.96.0.0/13\n", "\n40.0.0.0/8\n")) is not None, True)
	check("file: a line that is no network", refused(SHIPPED + "evil.example.com\n") is not None, True)
	check("file: a network with host bits", refused("# networks-sha256: %s\n52.96.0.1/14\n" % cr.networks_sha256(["52.96.0.1/14"])) is not None, True)
	check("file: no networks", refused("# networks-sha256: %s\n" % cr.networks_sha256([])) is not None, True)
	check("file: a right sum with other networks is used", refused("# networks-sha256: %s\n192.0.2.0/24\n" % cr.networks_sha256(["192.0.2.0/24"])), None)


def case_match():
	m = lambda ip: (lambda n: str(n) if n else None)(cr.match(ip, NETS))
	for ip, want in (
			("52.98.1.2", "52.96.0.0/14"), ("52.96.0.0", "52.96.0.0/14"), ("52.99.255.255", "52.96.0.0/14"),
			("52.95.255.255", None), ("52.100.0.0", "52.100.0.0/14"), ("40.92.5.5", "40.92.0.0/15"),
			("52.125.130.1", "52.125.128.0/20"), ("52.127.97.255", "52.127.96.0/23"), ("52.127.98.0", None),
			("13.107.6.153", "13.107.6.152/31"), ("13.107.6.154", None),
			("192.0.2.1", None), ("8.8.8.8", None),
			("2603:1026:12::5", "2603:1026::/36"), ("2603:1026:1000::", None), ("2620:1ec:4::152", "2620:1ec:4::152/128"),
			("2620:1ec:4::154", None), ("2001:db8::1", None),
			("::ffff:52.98.1.2", "52.96.0.0/14"),
			("not an address", None), ("52.98.1.2/32", None), ("", None)):
		check(f"match {ip!r}", m(ip), want)
	nets = [ipaddress.ip_network("10.0.0.0/8"), ipaddress.ip_network("10.1.0.0/16")]
	check("match: the most specific network", str(cr.match("10.1.2.3", nets)), "10.1.0.0/16")


class Lookups:
	# Stand-in DNS: PTR {ip: [names] or exception}, ADDR {(name, rtype): [addresses] or exception}.
	def __init__(self, ptr, addr):
		self.ptr, self.addr, self.calls = ptr, addr, []

	def ptr_lookup(self, ip):
		self.calls.append(("PTR", ip))
		a = self.ptr.get(ip, [])
		if isinstance(a, BaseException):
			raise a
		return a

	def addr_lookup(self, name, rtype):
		self.calls.append((rtype, name))
		a = self.addr.get((name, rtype), [])
		if isinstance(a, BaseException):
			raise a
		return a


def case_fcrdns():
	L = Lookups({
		"52.98.1.2": ["mail-x1.outbound.protection.outlook.com."],
		"52.98.1.3": ["spoofed.outlook.com"],               # forward lookup does not give the address
		"52.98.1.4": ["other.outlook.com"],                  # resolves to another address
		"52.98.1.5": RuntimeError("SERVFAIL"),
		"52.98.1.6": ["timeout.outlook.com"],
		"52.98.1.7": ["bad name.outlook.com", "<script>.example", "-x.example", "ok.Outlook.COM"],
		"52.98.1.8": ["first.example.net", "second.outlook.com"],
		"2603:1026:12::5": ["mail-v6.outlook.com"],
		"52.98.1.9": ["v4only.outlook.com"],
		"52.98.1.10": ["a" * 64 + ".outlook.com"],
	}, {
		("mail-x1.outbound.protection.outlook.com", "A"): ["52.98.1.2"],
		("spoofed.outlook.com", "A"): [],
		("other.outlook.com", "A"): ["52.98.9.9"],
		("timeout.outlook.com", "A"): TimeoutError(),
		("ok.Outlook.COM", "A"): ["52.98.1.7"],
		("first.example.net", "A"): ["203.0.113.1"],
		("second.outlook.com", "A"): ["52.98.1.8"],
		("mail-v6.outlook.com", "AAAA"): ["2603:1026:12:0::5"],
		("v4only.outlook.com", "AAAA"): ["2603:1026:12::9"],
		("a" * 64 + ".outlook.com", "A"): ["52.98.1.10"],
	})
	f = lambda ip: cr.fcrdns(ip, L.ptr_lookup, L.addr_lookup)
	check("fcrdns: name that resolves back", f("52.98.1.2"), "mail-x1.outbound.protection.outlook.com")
	check("fcrdns: spoofed PTR without forward match", f("52.98.1.3"), None)
	check("fcrdns: PTR whose name resolves to another address", f("52.98.1.4"), None)
	check("fcrdns: PTR lookup fails", f("52.98.1.5"), None)
	check("fcrdns: forward lookup fails", f("52.98.1.6"), None)
	check("fcrdns: names a host cannot have are skipped, the name is shown in lower case", f("52.98.1.7"), "ok.outlook.com")
	check("fcrdns: the second PTR name resolves back", f("52.98.1.8"), "second.outlook.com")
	check("fcrdns: IPv6 through AAAA (another written form of the address)", f("2603:1026:12::5"), "mail-v6.outlook.com")
	check("fcrdns: no PTR record", f("52.98.1.11"), None)
	check("fcrdns: a label longer than 63 characters", f("52.98.1.10"), None)
	check("fcrdns: names that are not host names are not looked up",
		[c for c in L.calls if c[1] in ("bad name.outlook.com", "<script>.example", "-x.example")], [])
	# A spoofed PTR record that names Microsoft decides nothing: an address
	# outside the ranges gets no hint at all (relay_hints below).


def case_hints():
	with tempfile.TemporaryDirectory() as d:
		path = os.path.join(d, "relays.txt")
		with open(path, "w", encoding="ascii") as fh:
			fh.write(SHIPPED)
		L = Lookups({"52.98.1.2": ["mail-x1.outlook.com"], "52.98.1.3": ["spoofed.outlook.com"],
			"198.51.100.7": ["looks-like.outlook.com"], "2603:1026:12::5": ["v6.outlook.com"]},
			{("mail-x1.outlook.com", "A"): ["52.98.1.2"], ("looks-like.outlook.com", "A"): ["198.51.100.7"],
			 ("v6.outlook.com", "AAAA"): ["2603:1026:12::5"]})
		hints, source = cr.relay_hints(["198.51.100.7", "52.98.1.2", "52.98.1.3", "2603:1026:12::5", "52.98.1.2"], path=path,
			lookups=(L.ptr_lookup, L.addr_lookup))
		check("relay_hints: only the addresses in the ranges", sorted(hints), ["2603:1026:12::5", "52.98.1.2", "52.98.1.3"])
		check("relay_hints: a forward-confirmed PTR name outside the ranges gives no hint", "198.51.100.7" in hints, False)
		check("relay_hints: an address outside the ranges is not looked up", [c for c in L.calls if "198.51.100.7" in c or "looks-like.outlook.com" in c], [])
		check("relay_hints: hint of a confirmed name",
			hints["52.98.1.2"], {"provider": "Microsoft", "service": cr.SERVICE, "network": "52.96.0.0/14", "name": "mail-x1.outlook.com"})
		check("relay_hints: spoofed PTR gives no name", hints["52.98.1.3"]["name"], None)
		check("relay_hints: IPv6", (hints["2603:1026:12::5"]["network"], hints["2603:1026:12::5"]["name"]), ("2603:1026::/36", "v6.outlook.com"))
		check("relay_hints: the source of the list", source, {"version": HEADER["source-version"], "retrieved": HEADER["retrieved"], "networks": len(NETS)})

		many = ["52.98.2.%d" % i for i in range(cr.MAX_LOOKUPS + 10)]
		L2 = Lookups({}, {})
		hints, _ = cr.relay_hints(many, path=path, lookups=(L2.ptr_lookup, L2.addr_lookup))
		check("relay_hints: every address gets a hint, at most MAX_LOOKUPS are looked up",
			(len(hints), len([c for c in L2.calls if c[0] == "PTR"])), (len(many), cr.MAX_LOOKUPS))

		with open(path, "a", encoding="ascii") as fh:
			fh.write("192.0.2.0/24\n")
		try:
			cr.relay_hints(["192.0.2.1"], path=path, lookups=(L.ptr_lookup, L.addr_lookup))
			got = "used"
		except ValueError:
			got = "refused"
		check("relay_hints: a file changed by hand is refused (also after it was read once)", got, "refused")


def case_tool():
	spec = importlib.util.spec_from_file_location("update_microsoft_relays", os.path.join(ROOT, "tools", "update-microsoft-relays.py"))
	tool = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(tool)
	answer = json.dumps([
		{"id": 1, "serviceArea": "Exchange", "ips": ["40.96.0.0/13", "2603:1006::/40"]},
		{"id": 2, "serviceArea": "Exchange", "ips": ["40.96.0.0/13"]},
		{"id": 9, "serviceArea": "Exchange", "urls": ["*.protection.outlook.com"]},
		{"id": 46, "serviceArea": "Common", "ips": ["20.190.128.0/18"]},
		{"id": 99, "serviceArea": "SharePoint", "ips": ["13.107.136.0/22"]},
	]).encode()
	text = tool.render(answer, "2026103000", "2026-11-21")
	h, nets = cr.parse(text)
	check("tool: only the service area Exchange, with the AutoDetect ranges, IPv4 first",
		[str(n) for n in nets], ["40.96.0.0/13"] + tool.AUTODETECT + ["2603:1006::/40"])
	check("tool: header of the file", (h["source-version"], h["retrieved"], h["extra-networks"]), ("2026103000", "2026-11-21", " ".join(tool.AUTODETECT)))
	try:
		tool.render(json.dumps([{"serviceArea": "Common", "ips": ["20.190.128.0/18"]}]).encode(), "1", "2026-11-21")
		got = "written"
	except ValueError:
		got = "refused"
	check("tool: an answer without Exchange ranges is refused", got, "refused")
	check("tool: the shipped file has the AutoDetect ranges of the tool", HEADER["extra-networks"], " ".join(tool.AUTODETECT))


case_file()
case_match()
case_fcrdns()
case_hints()
case_tool()

if FAILED:
	print(f"{len(FAILED)} check(s) failed")
	sys.exit(1)
print("all checks passed")
