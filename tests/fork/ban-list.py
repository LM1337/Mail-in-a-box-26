#!/usr/bin/env python3
"""Checks the list of banned addresses of System > Intrusion Detection and Prevention (B220).

No box needed. fail2ban-client is replaced by a stand-in that answers from
synthetic bans: 10,000 IPv4 addresses and some IPv6 ones in several jails,
a network with many of them, addresses banned in two jails, a permanent
ban, an address in Microsoft's published ranges, and fail2ban's database
with the rows of some bans (sqlite, in a temporary directory).

  * get_status() (GET /system/fail2ban): counters per jail, no per-ban
    lists or reasons, the networks with the most banned addresses, the
    jails that ban the browser's own address, the relay hints (only hits);
    small and fast with 10,000 bans.
  * list_bans() (GET /system/fail2ban/bans): newest ban first (ties by
    address), paging (pages put together give the whole order), the filter
    by part of an address or a jail and by a network in CIDR notation,
    strict parameters (bad values raise ValueError, a 400 of the route),
    the bans per jail without log lines, the relay hint without DNS
    lookups; fast with 10,000 bans.
  * ban_reason() (GET /system/fail2ban/ban-reason): the reasons per jail
    from the newest row of the database, a ban by hand, an address that is
    not banned, a bad address, an unreadable database.
  * fail2ban not running: both answer with running false and the error.
  * The page (management/templates/system-fail2ban.html) uses the new
    routes and no longer the per-ban lists of the status.

Usage: python3 -I tests/fork/ban-list.py
Exit code 0 when every check passed.
"""
import json
import os
import re
import sqlite3
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "management"))
import cloud_relays as cr  # noqa: E402
import fail2ban_admin as f  # noqa: E402

FAILED = []
COUNT = [0]


def check(name, got, want):
	COUNT[0] += 1
	if got != want:
		FAILED.append(name)
		print(f"FAIL {name}\n  want: {want!r}\n  got:  {got!r}")
	else:
		print(f"ok   {name}")


def raises(fn, *args):
	try:
		fn(*args)
	except ValueError as e:
		return str(e) or "ValueError"
	return None


NOW = int(time.time())
KNOWN = {"bob@example.com"}
SECRET = "Hunter2-Secret"
CLIENT = "192.0.2.200"           # the browser's address, banned in two jails
NET24 = "198.51.100."            # 40 banned addresses in one /24
NET64 = "2001:db8:1:2:"          # 5 banned addresses in one /64
PERMANENT = "192.0.2.201"
TWO_ROWS = "192.0.2.202"         # two rows in the database, the newer counts
MANUAL = "192.0.2.203"           # banned by hand: no log lines


def relay_address():
	# The second address of the first IPv4 network of Microsoft's list.
	_h, nets = cr.load()
	net = [n for n in nets if n.version == 4][0]
	return str(net.network_address + 1)


RELAY = relay_address()


def make_bans():
	# {jail: [(ip, start, bantime)]}
	jails = {"dovecot": [], "miab-postfix587": [], "miab-slow-smtp": [], "recidive": [], "miab-roundcube": []}
	names = list(jails)
	i = 0
	for a in range(10, 50):
		for b in range(250):
			ip = f"10.{a}.{b}.7"
			jails[names[i % 3]].append((ip, NOW - 100000 + i * 7, 600 * (1 + i % 4)))
			i += 1
	for k in range(40):
		jails["miab-slow-smtp"].append((f"{NET24}{k + 1}", NOW - 50000 + k, 86400))
	for k in range(5):
		jails["dovecot"].append((f"{NET64}:{k + 1:x}", NOW - 40000 + k, 3600))
	for k in range(45):
		jails["miab-postfix587"].append((f"2001:db8:{k + 10:x}::1", NOW - 30000 + k, 3600))
	# banned in two jails, newest ban in recidive
	for ip in (CLIENT, "10.10.0.7", "10.10.1.7"):
		jails["recidive"].append((ip, NOW - 100, 604800))
	jails["dovecot"].append((CLIENT, NOW - 200, 600))
	jails["miab-roundcube"].append((PERMANENT, NOW - 300, -1))
	jails["miab-roundcube"].append((TWO_ROWS, NOW - 400, 600))
	jails["miab-roundcube"].append((MANUAL, NOW - 500, 600))
	jails["dovecot"].append((RELAY, NOW - 600, 600))
	return jails


BANS = make_bans()


def fmt(t):
	return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t))


class FakeClient:
	# Answers the calls of fail2ban_admin.f2b() like fail2ban-client 1.1.
	def __init__(self, dbfile):
		self.dbfile = dbfile
		self.calls = []
		self.down = False

	def __call__(self, *args, timeout=15):
		self.calls.append(args)
		if self.down:
			raise f.F2BError("fail2ban-client ping failed: Failed to access socket path: /var/run/fail2ban/fail2ban.sock. Is fail2ban running?")
		if args == ("status",):
			return "Status\n|- Number of jail:\t%d\n`- Jail list:\t%s\n" % (len(BANS), ", ".join(BANS))
		if args[0] == "status" and len(args) == 2:
			n = len(BANS[args[1]])
			return ("Status for the jail: %s\n|- Filter\n|  |- Currently failed:\t3\n|  |- Total failed:\t%d\n"
				"`- Actions\n   |- Currently banned:\t%d\n   |- Total banned:\t%d\n") % (args[1], n * 5, n, n + 2)
		if args == ("banned",):
			return repr([{j: [b[0] for b in bans]} for j, bans in BANS.items()])
		if args[0] == "banned":
			return repr([[j for j, bans in BANS.items() if any(b[0] == ip for b in bans)] for ip in args[1:]])
		if args[0] == "get" and args[2:] == ("banip", "--with-time"):
			bans = sorted(BANS[args[1]], key=lambda b: b[1] + (10 ** 10 if b[2] < 0 else b[2]))
			return "".join("%s \t%s + %d = %s\n" % (ip, fmt(s), bt, fmt(s + bt) if bt >= 0 else "permanent") for ip, s, bt in bans)
		if args == ("get", "dbfile"):
			return "Current database file is set to:\n`- " + self.dbfile + "\n"
		raise AssertionError("unexpected fail2ban-client call: %r" % (args,))


def make_db(path):
	con = sqlite3.connect(path)
	con.execute("CREATE TABLE bans(jail TEXT NOT NULL, ip TEXT, timeofban INTEGER NOT NULL, bantime INTEGER NOT NULL, bancount INTEGER NOT NULL default 1, data JSON)")
	line = ("2026-10-26T13:00:00+01:00 box dovecot: imap-login: Login aborted: Logged out (auth failed, 1 attempts in 2 secs) (auth_failed): "
		"user=<%s>, method=PLAIN, rip=%s, lip=10.0.0.1, TLS, session=<x>")
	rows = [
		("dovecot", CLIENT, NOW - 200, 600, json.dumps({"matches": [line % ("bob@example.com", CLIENT)] * 3, "failures": 3})),
		("recidive", CLIENT, NOW - 100, 604800, json.dumps({"matches": [], "failures": 5})),
		("miab-roundcube", TWO_ROWS, NOW - 90000, 600, json.dumps({"matches": [line % ("old", TWO_ROWS)], "failures": 1})),
		("miab-roundcube", TWO_ROWS, NOW - 400, 600, json.dumps({"matches": [line % (SECRET, TWO_ROWS)] * 2, "failures": 20})),
		("miab-roundcube", MANUAL, NOW - 500, 600, json.dumps({"matches": [], "failures": 0})),
	]
	con.executemany("INSERT INTO bans(jail, ip, timeofban, bantime, data) VALUES (?, ?, ?, ?, ?)", rows)
	con.commit()
	con.close()


def all_addresses():
	# The expected order: newest ban of each address first, ties by address.
	newest = {}
	for bans in BANS.values():
		for ip, s, _bt in bans:
			newest[ip] = max(newest.get(ip, s), s)
	return [ip for ip, _ in sorted(newest.items(), key=lambda x: (-x[1], x[0]))]


def main():
	tmp = tempfile.mkdtemp()
	dbfile = os.path.join(tmp, "fail2ban.sqlite3")
	make_db(dbfile)
	client = FakeClient(dbfile)
	f.f2b = client
	f.config_is_current = lambda env, settings=None: True
	f.utils.load_settings = lambda env: {}
	f._known_accounts = lambda env: set(KNOWN)
	lookups = []

	def fake_dns_lookups():
		lookups.append(1)
		return (lambda ip: [], lambda name, rtype: [])
	cr.dns_lookups = fake_dns_lookups
	env = {"STORAGE_ROOT": tmp, "PUBLIC_IP": "192.0.2.1"}
	expected = all_addresses()
	entries = sum(len(v) for v in BANS.values())
	print(f"synthetic: {len(expected)} addresses, {entries} bans in {len(BANS)} jails")

	# --- the overview -------------------------------------------------------
	t = time.time()
	st = f.get_status(env, client_ip=CLIENT)
	d_status = time.time() - t
	body = json.dumps(st)
	check("status: running", (st["running"], st["error"]), (True, None))
	check("status: banned_ips", st["banned_ips"], len(expected))
	check("status: banned_entries", st["banned_entries"], entries)
	check("status: no per-ban lists in the jails", [j["name"] for j in st["jails"] if "banned" in j], [])
	check("status: no reasons", ("reason" in body, "reasons_error" in st, "lines" in body), (False, False, False))
	check("status: banned_count per jail", {j["name"]: j["banned_count"] for j in st["jails"]}, {j: len(v) for j, v in BANS.items()})
	check("status: counters per jail", {j["name"]: j["currently_banned"] for j in st["jails"]}, {j: len(v) for j, v in BANS.items()})
	check("status: client banned in", st["client"]["banned_in"], ["dovecot", "recidive"])
	check("status: jail_info with rules", bool(st["jail_info"]["miab-roundcube"]["watches"]) and st["jail_info"]["miab-roundcube"]["maxretry"] > 0, True)
	top = st["top_networks"]
	check("status: top network first", top[0], {"network": NET24 + "0/24", "addresses": 40, "jails": ["miab-slow-smtp"]})
	check("status: the /64", [n for n in top if n["network"] == "2001:db8:1:2::/64"],
		[{"network": "2001:db8:1:2::/64", "addresses": 5, "jails": ["dovecot"]}])
	check("status: at most 10 networks, each with 2 or more", (len(top) <= 10, all(n["addresses"] >= 2 for n in top)), (True, True))
	check("status: networks by count", [n["addresses"] for n in top], sorted([n["addresses"] for n in top], reverse=True))
	check("status: relay hints only for hits", sorted(st["relays"]), [RELAY])
	check("status: fail2ban-client calls", len(client.calls), 2 + len(BANS))
	ok = d_status < 1.0
	print(f"{'ok  ' if ok else 'FAIL'} status of {entries} bans in {d_status:.3f} s, {len(body)} bytes of JSON")
	COUNT[0] += 1
	if not ok:
		FAILED.append("status time")
	check("status: JSON under 20 KB", len(body) < 20000, True)
	st2 = f.get_status(env, client_ip="192.0.2.99")
	check("status: client not banned", st2["client"]["banned_in"], [])
	st3 = f.get_status(env, client_ip="not an address")
	check("status: invalid client address", st3["client"], None)

	# --- pages --------------------------------------------------------------
	client.calls.clear()
	lookups.clear()
	t = time.time()
	p = f.list_bans()
	d_list = time.time() - t
	check("bans: defaults", (p["running"], p["offset"], p["limit"], p["total"], p["matched"], len(p["addresses"])),
		(True, 0, 50, len(expected), len(expected), 50))
	check("bans: newest first", [a["ip"] for a in p["addresses"]], expected[:50])
	starts = [a["start"] for a in p["addresses"]]
	check("bans: starts not increasing", starts, sorted(starts, reverse=True))
	ok = d_list < 1.5
	print(f"{'ok  ' if ok else 'FAIL'} page of {entries} bans in {d_list:.3f} s, {len(json.dumps(p))} bytes of JSON")
	COUNT[0] += 1
	if not ok:
		FAILED.append("list time")
	check("bans: one fail2ban-client call per jail with bans", len(client.calls), 1 + len(BANS))
	page = []
	for off in range(0, 400, 50):
		page += [a["ip"] for a in f.list_bans("", off, 50)["addresses"]]
	check("bans: pages of 50 put together", page, expected[:400])
	check("bans: limit 200", [a["ip"] for a in f.list_bans("", "200", "200")["addresses"]], expected[200:400])
	last = f.list_bans("", str(len(expected) - 3), "50")
	check("bans: last page", [a["ip"] for a in last["addresses"]], expected[-3:])
	beyond = f.list_bans("", str(len(expected) + 10), "50")
	check("bans: offset beyond the end", (beyond["addresses"], beyond["matched"]), ([], len(expected)))
	check("bans: offset with spaces", f.list_bans("", " 5 ", "")["offset"], 5)

	for desc, off, lim in (("limit 0", "0", "0"), ("limit 201", "0", "201"), ("limit abc", "0", "abc"), ("limit -1", "0", "-1"),
			("offset -1", "-1", "50"), ("offset 1e3", "1e3", "50"), ("offset too large", str(10 ** 7 + 1), "50"),
			("offset 1.5", "1.5", "50"), ("limit 10 digits", "0", "1" * 10)):
		check("bans: refused " + desc, bool(raises(f.list_bans, "", off, lim)), True)

	# --- one address --------------------------------------------------------
	by_ip = {a["ip"]: a for a in f.list_bans("192.0.2.", 0, 200)["addresses"]}
	c = by_ip[CLIENT]
	check("bans: two jails, newest first", [(b["jail"], b["start"]) for b in c["bans"]], [("recidive", NOW - 100), ("dovecot", NOW - 200)])
	check("bans: fields of a ban", sorted(c["bans"][0]), ["bantime", "end", "jail", "remaining", "start"])
	check("bans: end and remaining of the address", (c["start"], c["end"], 0 < c["remaining"] <= 604800),
		(NOW - 100, NOW - 100 + 604800, True))
	pm = by_ip[PERMANENT]
	check("bans: permanent", (pm["end"], pm["remaining"], pm["bans"][0]["end"], pm["bans"][0]["bantime"]), (None, None, None, -1))
	check("bans: no log lines or reasons in a page", any(k in json.dumps(f.list_bans("", 0, 200)) for k in ('"reason"', '"lines"')), False)
	rp = f.list_bans(RELAY, 0, 50)
	check("bans: relay hint of the page", (rp["matched"], (rp["addresses"][0]["relay"] or {}).get("network") is not None,
		rp["addresses"][0]["relay"]["name"]), (1, True, None))
	check("bans: no DNS lookups for a page", lookups, [])
	check("bans: no relay hint for others", by_ip[CLIENT]["relay"], None)

	# --- filters ------------------------------------------------------------
	def matched(flt):
		return f.list_bans(flt, 0, 200)["matched"]
	check("filter: part of an address", matched(NET24), 40)
	check("filter: the whole address", [a["ip"] for a in f.list_bans(CLIENT)["addresses"]], [CLIENT])
	check("filter: IPv6 in capitals", matched("2001:DB8:1:2:"), 5)
	check("filter: jail", matched("recidive"), len(BANS["recidive"]))
	check("filter: part of a jail", matched("SLOW-SM"), len(BANS["miab-slow-smtp"]))
	check("filter: nothing matches", (matched("zzz"), f.list_bans("zzz")["total"]), (0, len(expected)))
	check("filter: CIDR /25", matched("198.51.100.0/25"), 40)
	check("filter: CIDR /28", sorted(a["ip"] for a in f.list_bans("198.51.100.0/28")["addresses"]),
		sorted(f"{NET24}{k}" for k in range(1, 16)))
	check("filter: CIDR with host bits", matched("198.51.100.77/24"), 40)
	check("filter: IPv6 CIDR", matched("2001:db8:1:2::/64"), 5)
	check("filter: CIDR of the other family", matched("2001:db8::/32") >= 50 and matched("10.0.0.0/8") == 10000, True)
	check("filter: /32 of one address", [a["ip"] for a in f.list_bans(CLIENT + "/32")["addresses"]], [CLIENT])
	check("filter: newest first with a filter", [a["ip"] for a in f.list_bans("10.", 0, 50)["addresses"]],
		[ip for ip in expected if "10." in ip][:50])
	check("filter: kept in the answer", f.list_bans(" recidive ")["filter"], "recidive")
	for desc, flt in (("bad network", "198.51.100.0/33"), ("network with letters", "1.2.3.4/abc"), ("space", "a b"), ("markup", "<script>"),
			("65 characters", "1" * 65), ("quote", "1'"), ("two slashes", "1.2.3.0/24/1"), ("non-ASCII", "ä")):
		check("filter: refused " + desc, bool(raises(f.list_bans, flt, 0, 50)), True)
	t = time.time()
	f.list_bans("198.51.100.0/24", 0, 50)
	d_cidr = time.time() - t
	ok = d_cidr < 1.5
	print(f"{'ok  ' if ok else 'FAIL'} CIDR filter over {entries} bans in {d_cidr:.3f} s")
	COUNT[0] += 1
	if not ok:
		FAILED.append("CIDR filter time")

	# --- reasons ------------------------------------------------------------
	r = f.ban_reason(env, CLIENT)
	check("reason: jails of the address", [j["jail"] for j in r["jails"]], ["dovecot", "recidive"])
	dv = r["jails"][0]
	check("reason: failures, account, lines", (dv["reason"]["failures"], dv["reason"]["accounts"], len(dv["reason"]["lines"]), dv["reason"]["manual"]),
		(3, ["bob@example.com"], 3, False))
	check("reason: rule of the jail", (dv["rule"]["watches"] is not None, dv["rule"]["maxretry"]), (True, f.jail_info(f.get_settings(env)[0])["dovecot"]["maxretry"]))
	check("reason: recidive without lines", (r["jails"][1]["reason"]["manual"], r["jails"][1]["reason"]["failures"]), (True, 5))
	r = f.ban_reason(env, TWO_ROWS)
	rr = r["jails"][0]["reason"]
	check("reason: the newest row", (rr["failures"], len(rr["lines"])), (20, 2))
	check("reason: an unknown name is not shown", (any(SECRET.lower() in l.lower() for l in rr["lines"]), rr["unknown_names"]), (False, 2))
	check("reason: ban by hand", f.ban_reason(env, MANUAL)["jails"][0]["reason"]["manual"], True)
	check("reason: banned, but no row", f.ban_reason(env, PERMANENT)["jails"], [{"jail": "miab-roundcube", "reason": None, "rule": f.jail_info(f.get_settings(env)[0])["miab-roundcube"]}])
	check("reason: not banned", f.ban_reason(env, "192.0.2.99"), {"ip": "192.0.2.99", "jails": []})
	check("reason: address normalized", f.ban_reason(env, "2001:DB8:1:2:0:0:0:1")["ip"], "2001:db8:1:2::1")
	for bad in ("", "192.0.2.0/24", "a b", "300.1.1.1", "1.2.3.4%eth0"):
		check("reason: refused %r" % bad, bool(raises(f.ban_reason, env, bad)), True)
	with open(os.path.join(tmp, "broken.sqlite3"), "w") as fh:
		fh.write("not a database\n" * 100)
	client.dbfile = os.path.join(tmp, "broken.sqlite3")
	r = f.ban_reason(env, CLIENT)
	check("reason: unreadable database", ("error" in r, [j["reason"] for j in r["jails"]]), (True, [None, None]))
	client.dbfile = dbfile

	# --- fail2ban not running -----------------------------------------------
	client.down = True
	st = f.get_status(env, client_ip=CLIENT)
	check("down: status", (st["running"], bool(st["error"]), st["client"]["banned_in"], st["top_networks"]), (False, True, [], []))
	p = f.list_bans("", 0, 50)
	check("down: page", (p["running"], bool(p["error"]), p["addresses"], p["total"]), (False, True, [], 0))
	check("down: bad parameters still refused", bool(raises(f.list_bans, "", 0, 500)), True)
	client.down = False

	# --- the page -----------------------------------------------------------
	with open(os.path.join(ROOT, "management", "templates", "system-fail2ban.html"), encoding="utf-8") as fh:
		html = fh.read()
	script = html[html.index("<script>"):]
	check("page: uses /system/fail2ban/bans", '"/system/fail2ban/bans"' in script, True)
	check("page: uses /system/fail2ban/ban-reason", '"/system/fail2ban/ban-reason"' in script, True)
	check("page: no per-ban lists of the status", re.findall(r"\bj\.banned\b|\.banned\.forEach|b\.reason\b|F2B_MAX_ROWS", script), [])
	check("page: no table-responsive around the bans", re.search(r'table-responsive">\s*<table id="f2b-bans"', html) is None, True)

	print("%d of %d checks failed" % (len(FAILED), COUNT[0]))
	return 1 if FAILED else 0


if __name__ == "__main__":
	sys.exit(main())
