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
    for DNS.

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


case_query_dns()
case_dbl()

if FAILED:
	print(f"{len(FAILED)} case(s) failed")
	sys.exit(1)
print("all cases passed")
