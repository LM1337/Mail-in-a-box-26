#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Offline test of the DNS lookups of the status checks -- python3 stdlib only,
no box needed (B181).

management/status_checks.py asks DNS through query_dns(), which turns
dnspython's answers and exceptions into a value: the records, the caller's
"no such record" value (nxdomain), "[timeout]" or "[error]". This test runs
query_dns() and the checks built on it against a stand-in for dnspython
whose resolver answers from a table:

  * query_dns: records, NXDOMAIN and NoAnswer (nxdomain), NoNameservers,
    a name that is too long (NameTooLong) and YXDOMAIN ("[error]", no
    exception out of the status checks), a timeout ("[timeout]"); a
    nameserver given with "at" gets a resolver of its own;
  * the Spamhaus DBL check of a mail domain: not listed, listed, a failed
    lookup, and a domain whose name with ".dbl.spamhaus.org" is too long
    for DNS;
  * the DNSSEC DS check (B182): a lookup that timed out or failed gives
    "Could not check this domain's DNSSEC DS record" without the DS records
    to set, not "DS record is not set"; no DS record, a correct and a wrong
    one as before; the checks of a zone look its DS records up once, check
    them first when they are set or the lookup failed, and suggest DNSSEC
    last only when no DS record is set; the box's own name checks the DS
    records of its zone only when they are set; when the KSK's public key
    cannot be read through the checked dns/ (B183), the DS records to set
    are still suggested, without the key and with the reason.

The test of outbound port 25 discards the output of nc (B184).

The modules that status_checks.py imports and that are not in the standard
library, or need a box, are replaced by stand-ins.

  tests/fork/status-dns.py

Exit code: 0 = all cases pass, 1 = a case failed (printed).
"""

import importlib.util
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
MGMT = os.path.join(HERE, "..", "..", "management")

STUBS = ["dateutil", "dateutil.parser", "dateutil.relativedelta", "dateutil.tz",
	"idna", "psutil", "postfix_mta_sts_resolver", "postfix_mta_sts_resolver.resolver",
	"dns_update", "web_update", "ssl_certificates", "mailconfig", "utils",
	"backup", "fail2ban_admin"]


class Anything(types.ModuleType):
	def __getattr__(self, name):
		if name.startswith("__"):
			raise AttributeError(name)
		return lambda *a, **k: None


# --- a stand-in for dnspython: the exceptions status_checks.py uses, and a
# resolver that answers from ANSWERS {(qname, rtype): records or exception}.

class DNSException(Exception): pass
class Timeout(DNSException): pass
class FormError(DNSException): pass
class NameTooLong(FormError): pass
class NXDOMAIN(DNSException): pass
class NoAnswer(DNSException): pass
class NoNameservers(DNSException): pass
class YXDOMAIN(DNSException): pass


def from_text(name):
	# Like dns.name.from_text: the wire form of a name may have 255 octets
	# (each label with its length byte, and the root).
	labels = [x for x in name.rstrip(".").split(".")]
	if sum(len(x.encode()) + 1 for x in labels) + 1 > 255:
		raise NameTooLong("A DNS name is > 255 octets long.")
	return name


ANSWERS = {}
CALLS = []


class Resolver:
	def __init__(self, configure=True):
		self.nameservers = ["127.0.0.1"]
		self.timeout = self.lifetime = None

	def resolve(self, qname, rtype):
		CALLS.append((qname, rtype, tuple(self.nameservers)))
		from_text(qname)  # dnspython makes a Name of the text first
		a = ANSWERS.get((qname.rstrip("."), rtype), NXDOMAIN())
		if isinstance(a, BaseException):
			raise a
		return list(a)


DEFAULT = Resolver()


def make_dns():
	dns = types.ModuleType("dns")
	dns.__path__ = []
	exc = types.ModuleType("dns.exception")
	exc.DNSException, exc.Timeout, exc.FormError = DNSException, Timeout, FormError
	name = types.ModuleType("dns.name")
	name.NameTooLong, name.from_text = NameTooLong, from_text
	res = types.ModuleType("dns.resolver")
	for c in (NXDOMAIN, NoAnswer, NoNameservers, YXDOMAIN):
		setattr(res, c.__name__, c)
	res.Resolver = Resolver
	res.get_default_resolver = lambda: DEFAULT
	rev = types.ModuleType("dns.reversename")
	rev.from_address = lambda a: a
	dns.exception, dns.name, dns.resolver, dns.reversename = exc, name, res, rev
	return {"dns": dns, "dns.exception": exc, "dns.name": name, "dns.resolver": res, "dns.reversename": rev}


def load():
	for n in STUBS:
		sys.modules[n] = Anything(n)
	sys.modules.update(make_dns())
	spec = importlib.util.spec_from_file_location("status_checks", os.path.join(MGMT, "status_checks.py"))
	mod = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(mod)
	return mod


class Output:
	# Records the calls of the checks (print_ok, print_warning, ...).
	def __init__(self):
		self.calls = []

	def __getattr__(self, attr):
		if not attr.startswith("print_") and attr != "add_heading":
			raise AttributeError(attr)
		return lambda *a, **k: self.calls.append((attr, " ".join(" ".join(a).split())))


sm = load()
FAILED = []


def check(name, got, want):
	if got != want:
		FAILED.append(name)
		print(f"FAIL {name}\n  want: {want!r}\n  got:  {got!r}")
	else:
		print(f"ok   {name}")


LONG = ".".join(["a" * 59] * 4)  # 239 characters: fits, but not with .dbl.spamhaus.org


def case_query_dns():
	ANSWERS.clear()
	ANSWERS[("example.com", "A")] = ["192.0.2.1"]
	ANSWERS[("example.com", "MX")] = ["10 box.example.com."]
	ANSWERS[("noanswer.example.com", "A")] = NoAnswer()
	ANSWERS[("servfail.example.com", "A")] = NoNameservers()
	ANSWERS[("slow.example.com", "A")] = Timeout()
	ANSWERS[("dname.example.com", "A")] = YXDOMAIN()
	q = sm.query_dns
	check("query_dns: A records", q("example.com", "A"), "192.0.2.1")
	check("query_dns: MX without the final dot", q("example.com", "MX"), "10 box.example.com")
	check("query_dns: NXDOMAIN", q("nx.example.com", "A"), "[Not Set]")
	check("query_dns: NXDOMAIN, nxdomain=None", q("nx.example.com", "A", nxdomain=None), None)
	check("query_dns: NoAnswer", q("noanswer.example.com", "A", nxdomain=None), None)
	check("query_dns: NoNameservers", q("servfail.example.com", "A", nxdomain=None), "[error]")
	check("query_dns: timeout", q("slow.example.com", "A", nxdomain=None), "[timeout]")
	check("query_dns: YXDOMAIN", q("dname.example.com", "A", nxdomain=None), "[error]")
	check("query_dns: name too long for DNS", q(LONG + ".dbl.spamhaus.org", "A", nxdomain=None), "[error]")
	check("query_dns: the longest name that fits", q(LONG, "A", nxdomain=None), None)
	check("query_dns: as_list", q("example.com", "A", as_list=True), ["192.0.2.1"])
	del CALLS[:]
	q("example.com", "A", at="198.51.100.53")
	check("query_dns: at= asks that nameserver", CALLS[-1][2], ("198.51.100.53",))
	check("query_dns: at= leaves the default resolver alone", DEFAULT.nameservers, ["127.0.0.1"])
	check("dns_name_too_long", (sm.dns_name_too_long(LONG + ".dbl.spamhaus.org"), sm.dns_name_too_long(LONG)), (True, False))


def case_dbl():
	def run(domain):
		out = Output()
		sm.check_domain_dbl(domain, out)
		return out.calls
	ANSWERS.clear()
	ANSWERS[("listed.example.com.dbl.spamhaus.org", "A")] = ["127.0.1.2"]
	ANSWERS[("servfail.example.com.dbl.spamhaus.org", "A")] = NoNameservers()
	check("dbl: not listed", run("example.com"), [("print_ok", "Domain is not blacklisted by dbl.spamhaus.org.")])
	got = run("listed.example.com")
	check("dbl: listed", [(a, t[:52]) for a, t in got], [("print_error", "This domain is listed in the Spamhaus Domain Block L")])
	check("dbl: failed lookup", run("servfail.example.com"),
		[("print_warning", "Could not connect to dbl.spamhaus.org. Could not determine whether the domain servfail.example.com is blacklisted. Please try again later.")])
	check("dbl: name too long with the suffix", run(LONG),
		[("print_warning", f"Could not determine whether the domain {LONG} is blacklisted by dbl.spamhaus.org: its name is too long to be looked up there.")])


# --- the DNSSEC DS check (B182)

ZONE_DS = "example.com.\t3600\tIN\tDS\t12345 13 2 ABCDEF0123"
FILES = {
	"/etc/nsd/zones/example.com.txt.ds": ZONE_DS + "\n",
	"/storage/dns/dnssec/Kexample.key": "example.com.\tIN\tDNSKEY\t257 3 13 PUBKEYDATA\n",
}


class FakePath:
	# os.path for status_checks.py with exists() answering from FILES.
	def __getattr__(self, name):
		return getattr(os.path, name)

	@staticmethod
	def exists(p):
		return p in FILES


class FakeOs:
	path = FakePath()

	def __getattr__(self, name):
		return getattr(os, name)


def fake_open(p, *a, **k):
	import io
	if p not in FILES:
		raise FileNotFoundError(p)
	return io.StringIO(FILES[p])


ENV = {"STORAGE_ROOT": "/storage", "PRIMARY_HOSTNAME": "box.example.com", "PUBLIC_IP": "192.0.2.1", "PUBLIC_IPV6": None}
ZONEFILES = {"example.com": "example.com.txt"}


def ds_messages(ds_answer):
	ANSWERS.clear()
	if ds_answer is not None:
		ANSWERS[("example.com", "DS")] = ds_answer
	out = Output()
	sm.check_dnssec("example.com", ENV, out, ZONEFILES)
	return out.calls


def case_dnssec():
	sm.os = FakeOs()
	sm.open = fake_open
	sm.load_env_vars_from_file = lambda fn: {"KSK": "Kexample"}
	sm.read_dnssec_ksk_pubkey = lambda env, alg_name: "PUBKEYDATA"

	ANSWERS.clear()
	ANSWERS[("a.example.com", "DS")] = ["12345 13 2 ABCDEF0123"]
	ANSWERS[("b.example.com", "DS")] = NoAnswer()
	ANSWERS[("c.example.com", "DS")] = NoNameservers()
	ANSWERS[("d.example.com", "DS")] = Timeout()
	check("query_ds: records, none, failed, timed out",
		[sm.query_ds(d) for d in ("a.example.com", "b.example.com", "c.example.com", "d.example.com", "e.example.com")],
		[["12345 13 2 ABCDEF0123"], [], "[error]", "[timeout]", []])

	for name, answer, verb in (("failed", NoNameservers(), "failed"), ("timed out", Timeout(), "timed out")):
		got = ds_messages(answer)
		check(f"check_dnssec: lookup {name}: one warning, no DS records to set", got,
			[("print_warning", f"Could not check this domain's DNSSEC DS record: the DNS lookup {verb}. Please try again later. If this persists, see the other issues listed here for this domain.")])
	got = ds_messages(None)
	check("check_dnssec: no DS record: not set, with the DS records to set",
		(got[0][0], got[0][1][:44], any("ABCDEF0123" in t for _, t in got[1:])),
		("print_warning", "This domain's DNSSEC DS record is not set. T", True))
	check("check_dnssec: correct DS record", ds_messages(["12345 13 2 ABCDEF0123"]),
		[("print_ok", "DNSSEC 'DS' record is set correctly at registrar.")])
	got = ds_messages(["11111 13 2 0000"])
	check("check_dnssec: wrong DS record: incorrect, with the current one",
		(got[0][0], got[0][1][:46], got[-1][1]),
		("print_error", "This domain's DNSSEC DS record is incorrect. T", "Key Tag: 11111, Algorithm: 13, Digest Type: 2, Digest: 0000"))
	check("check_dnssec: the KSK's public key with the DS records to set",
		any(t == "PUBKEYDATA" for _, t in ds_messages(None)), True)

	# B183: the key cannot be read through a checked dns/ (the storage user
	# replaced it): the DS records to set without the key, no exception.
	def refused(env, alg_name):
		raise ValueError("/storage/dns is not a directory of root's own")
	sm.read_dnssec_ksk_pubkey = refused
	try:
		got = ds_messages(None)
	except Exception as e:
		got = [("exception", repr(e))]
	check("check_dnssec: key not readable (B183): no exception, DS records still suggested, the reason named",
		(got[0][0], any("ABCDEF0123" in t for _, t in got[1:]), any(t == "PUBKEYDATA" for _, t in got),
			any(t.startswith("Public Key: not shown, the key cannot be read: /storage/dns is not") for _, t in got)),
		("print_warning", True, False, True))
	sm.read_dnssec_ksk_pubkey = lambda env, alg_name: "PUBKEYDATA"

	# Which DNSSEC checks the checks of a zone and of the box's name make.
	seen = []
	real_check_dnssec = sm.check_dnssec
	sm.check_dnssec = lambda domain, env, output, zf, is_checking_primary=False, ds=None: seen.append((domain, is_checking_primary, ds))
	sm.get_custom_dns_config = lambda env: []
	sm.get_custom_dns_records = lambda records, qname, rtype: []
	sm.get_secondary_dns = lambda records, mode=None: []
	sm.get_mail_aliases = lambda env: []
	sm.build_tlsa_record = lambda env: "3 1 1 X"
	try:
		for name, answer, first, last in (
				("DS set", ["12345 13 2 ABCDEF0123"], [("example.com", False, ["12345 13 2 ABCDEF0123"])], []),
				("no DS", None, [], [("example.com", False, [])]),
				("DS lookup failed", NoNameservers(), [("example.com", False, "[error]")], []),
				("DS lookup timed out", Timeout(), [("example.com", False, "[timeout]")], [])):
			ANSWERS.clear()
			if answer is not None:
				ANSWERS[("example.com", "DS")] = answer
			del seen[:]
			del CALLS[:]
			ds = sm.query_ds("example.com")
			sm.check_dns_zone("example.com", ENV, Output(), ZONEFILES, ds=ds)
			got_first = list(seen)
			del seen[:]
			sm.check_dns_zone_suggestions("example.com", ENV, Output(), ZONEFILES, [], ds=ds)
			lookups = [c for c in CALLS if c[1] == "DS"]
			check(f"zone checks, {name}: DNSSEC first / last, one DS lookup", (got_first, list(seen), len(lookups)), (first, last, 1))

			del seen[:]
			sm.check_primary_hostname_dns("box.example.com", ENV, Output(), ["example.com"], ZONEFILES)
			want = [("example.com", True, answer)] if isinstance(answer, list) else []
			check(f"box's name, {name}: DS records of its zone checked only when set", seen, want)
	finally:
		sm.check_dnssec = real_check_dnssec


# --- the test of outbound port 25 prints nothing (B184): nc's "Connection
# to ... succeeded!" on standard error made the nightly status mail go out
# every night.

def case_port25():
	import tempfile
	d = tempfile.mkdtemp()
	nc = os.path.join(d, "nc")
	for code in (0, 1):
		with open(nc, "w") as f:
			f.write("#!/bin/sh\necho 'Connection to aspmx.l.google.com 25 port [tcp/smtp] succeeded!' >&2\necho out\nexit %d\n" % code)
		os.chmod(nc, 0o755)
		sm.NC = nc
		cap = os.path.join(d, "cap")
		saved = [os.dup(1), os.dup(2)]
		fd = os.open(cap, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
		sys.stdout.flush(); sys.stderr.flush()
		os.dup2(fd, 1); os.dup2(fd, 2)
		try:
			got = sm.outbound_port25_open()
		finally:
			sys.stdout.flush(); sys.stderr.flush()
			os.dup2(saved[0], 1); os.dup2(saved[1], 2)
			os.close(fd); os.close(saved[0]); os.close(saved[1])
		check("port 25 test (nc exit %d): %s, nc's output discarded (B184)" % (code, "open" if code == 0 else "blocked"),
			(got, open(cap).read()), (code == 0, ""))
	sm.NC = os.path.join(d, "missing")
	check("port 25 test: nc missing counts as blocked", sm.outbound_port25_open(), False)


case_query_dns()
case_dbl()
case_dnssec()
case_port25()

if FAILED:
	print(f"{len(FAILED)} case(s) failed")
	sys.exit(1)
print("all cases passed")
