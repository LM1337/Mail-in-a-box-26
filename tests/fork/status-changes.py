#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Offline test of the daily "Status Checks Change Notice" -- python3 stdlib
only, no box needed (B179).

management/status_checks.py --show-changes compares the status checks with
those of the run before (status_changes()). A check is its message with the
print_line lines after it (instructions, details); this test checks that a
changed check is always shown whole:

  * a changed message comes with its unchanged lines (a DNSSEC warning that
    says the DS records are below it comes with the DS records);
  * a changed line comes with its message;
  * unchanged checks are not shown; a new category, a removed check and a
    removed category are;
  * the record read back from JSON (lists) compares equal to the one of
    the run (tuples).

The modules that status_checks.py imports and that are not in the standard
library, or need a box, are replaced by empty stand-ins.

  tests/fork/status-changes.py

Exit code: 0 = all cases pass, 1 = a case failed (printed).
"""

import importlib.util
import json
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
MGMT = os.path.join(HERE, "..", "..", "management")

STUBS = ["dateutil", "dateutil.parser", "dateutil.relativedelta", "dateutil.tz",
	"dns", "dns.exception", "dns.name", "dns.reversename", "dns.resolver", "idna", "psutil",
	"postfix_mta_sts_resolver", "postfix_mta_sts_resolver.resolver",
	"dns_update", "web_update", "ssl_certificates", "mailconfig", "utils",
	"backup", "fail2ban_admin"]


class Anything(types.ModuleType):
	def __getattr__(self, name):
		if name.startswith("__"):
			raise AttributeError(name)
		return lambda *a, **k: None


def load():
	for name in STUBS:
		sys.modules[name] = Anything(name)
	spec = importlib.util.spec_from_file_location("status_checks", os.path.join(MGMT, "status_checks.py"))
	mod = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(mod)
	return mod


def H(t): return ("add_heading", (t,), {})
def W(t): return ("print_warning", (t,), {})
def E(t): return ("print_error", (t,), {})
def OK(t): return ("print_ok", (t,), {})
def L(t, mono=False): return ("print_line", (t,), {"monospace": True} if mono else {})


DS_LINES = [L("Follow the instructions provided by your domain name registrar."), L(""),
	L("Option 1:"), L("Key Tag: 12345"), L("Digest: abcdef"), L("Bulk/Record Format:"),
	L("example.com.\t3600\tIN\tDS\t12345 13 2 abcdef", mono=True)]


def texts(calls):
	return [c[0] + ":" + c[1][0] for c in calls]


def case(name, prev, cur, want):
	got = texts(sm.status_changes(json.loads(json.dumps(prev)), cur))
	if got != texts(want):
		print(f"FAIL {name}")
		print("  want: " + "\n        ".join(texts(want)))
		print("  got:  " + "\n        ".join(got))
		return False
	print(f"ok   {name}")
	return True


sm = load()
results = []

base = [H("System"), OK("SSH disallows password-based login."),
	H("example.com"), OK("Nameserver glue records are correct."),
	E("This domain's DNSSEC DS record is incorrect. ...")] + DS_LINES + [
	L("The DS record is currently set to:"), L("Key Tag: 999, Algorithm: 8, Digest Type: 2, Digest: 00")]

# Nothing changed: nothing to report.
results.append(case("unchanged", base, list(base), []))

# The DS record was removed at the registrar: the message changes from
# "incorrect" to "not set", the DS records stay the same. The new message
# must come with them (before B179: alone, "See below" with nothing below).
cur = [H("System"), OK("SSH disallows password-based login."),
	H("example.com"), OK("Nameserver glue records are correct."),
	W("This domain's DNSSEC DS record is not set. ...")] + DS_LINES
results.append(case("message changed, lines kept", base, cur,
	[H("example.com -- Previously:"), E("This domain's DNSSEC DS record is incorrect. ...")] + DS_LINES + [
	L("The DS record is currently set to:"), L("Key Tag: 999, Algorithm: 8, Digest Type: 2, Digest: 00"),
	H("example.com -- Currently:"), W("This domain's DNSSEC DS record is not set. ...")] + DS_LINES))

# Only a line of the instructions changed (a new key): it comes with its
# message (before: the lone line).
prev2 = list(cur)
cur2 = [c if c != L("Key Tag: 12345") else L("Key Tag: 54321") for c in cur]
results.append(case("line changed, message kept", prev2, cur2,
	[H("example.com -- Previously:"), W("This domain's DNSSEC DS record is not set. ...")] + DS_LINES + [
	H("example.com -- Currently:"), W("This domain's DNSSEC DS record is not set. ...")]
	+ [c if c != L("Key Tag: 12345") else L("Key Tag: 54321") for c in DS_LINES]))

# A check without lines changes, the check with lines after it does not:
# only the changed one is shown.
cur3 = [c if c != OK("Nameserver glue records are correct.") else E("Nameserver glue records are incorrect.") for c in cur]
results.append(case("other check changed", cur, cur3,
	[H("example.com -- Previously:"), OK("Nameserver glue records are correct."),
	H("example.com -- Currently:"), E("Nameserver glue records are incorrect.")]))

# A new domain: its category is added whole; a removed check and a removed
# category are reported.
cur4 = [H("System"), H("example.org"), W("This domain's DNSSEC DS record is not set. ...")] + DS_LINES
results.append(case("added, removed", cur, cur4,
	[H("System -- Removed"), OK("SSH disallows password-based login."),
	H("example.org -- Added"), W("This domain's DNSSEC DS record is not set. ...")] + DS_LINES + [
	H("example.com"), W("This section was removed.")]))

# Lines before the first message of a category are a check of their own.
prev5 = [H("Misc"), L("note a"), OK("fine")]
cur5 = [H("Misc"), L("note b"), OK("fine")]
results.append(case("leading lines", prev5, cur5,
	[H("Misc -- Previously:"), L("note a"), H("Misc -- Currently:"), L("note b")]))

failed = results.count(False)
print(f"{len(results)} cases, {failed} failed.")
sys.exit(1 if failed else 0)
