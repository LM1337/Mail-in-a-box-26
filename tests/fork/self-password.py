#!/usr/bin/env python3
"""
Offline test of POST /me/password (management/self_password.py, B210) --
python3 stdlib only, no box needed.

  * HTTP Basic credentials: UTF-8 and Latin-1, a password with ":", no
    scheme, another scheme, broken base64, no ":";
  * the change: the current password checked with the daemon's login check
    (stand-in), only the caller's own account changed, the new password
    through the policy (stand-in: refused -> 400), no credentials -> 401;
  * two-factor authentication: no code -> 403 with the hint to use the
    control panel, not counted as a failure; a wrong code -> 403, counted;
  * failures are logged (the miab-management jail) and limited: 5 per
    account (any address, also 127.0.0.1) and 10 per address within 10
    minutes refuse more attempts with 429, a right password does not get
    through then either; a success clears the account's count; old failures
    expire;
  * the limiter keeps at most max_keys keys, and drops those of addresses
    before those of accounts (forged addresses do not flush an account's
    failures); failures for accounts that do not exist count only for the
    address, so made-up names with forged addresses do not flush a real
    account's failures either.

  tests/fork/self-password.py

Exit code: 0 = all cases pass, 1 = a case failed (printed).
"""

import base64
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "management")))

import self_password as sp  # noqa: E402

failures = []


def check(name, got, want):
	if got != want:
		failures.append(name)
		print(f"FAIL {name}\n  want: {want!r}\n  got:  {got!r}")
	else:
		print(f"ok   {name}")


class Headers(dict):
	def getlist(self, name):
		v = self.get(name)
		return [v] if v is not None else []


class Req:
	def __init__(self, user=None, pw=None, new=None, xff=None, remote="127.0.0.1", raw_auth=None, totp=None, enc="utf-8"):
		h = Headers()
		if raw_auth is not None:
			h["Authorization"] = raw_auth
		elif user is not None:
			h["Authorization"] = "Basic " + base64.b64encode(("%s:%s" % (user, pw)).encode(enc)).decode()
		if xff:
			h["X-Forwarded-For"] = xff
		if totp:
			h["x-auth-token"] = totp
		self.headers = h
		self.form = {} if new is None else {"password": new}
		self.remote_addr = remote


USERS = {"alice@example.com": "right-pass", "bob@example.com": "bob-pass"}
MFA = {"bob@example.com": "123456"}
CHANGED = []
LOGGED = []


def check_user_auth(email, pw, request, env):
	if USERS.get(email) != pw:
		raise ValueError("Incorrect email address or password.")
	if email in MFA:
		token = request.headers.get("x-auth-token")
		if not token:
			raise ValueError("missing-totp-token")
		if token != MFA[email]:
			raise ValueError("invalid-totp-token")


def set_mail_password(email, pw, env):
	if len(pw) < 8:
		raise ValueError("Passwords must be at least eight characters.")
	if email not in USERS:
		return ("That's not a user (%s)." % email, 400)
	USERS[email] = pw
	CHANGED.append(email)
	return "OK"


class Clock:
	t = 1000.0

	def __call__(self):
		return self.t


def account_exists(email, env):
	return email in USERS


def run(req, limiter):
	return sp.change_own_password(req, {}, check_user_auth, set_mail_password, limiter, LOGGED.append, account_exists)


# Basic credentials
check("basic utf-8", sp.parse_basic_auth("Basic " + base64.b64encode("ä@x:pä:ss".encode()).decode()), ("ä@x", "pä:ss"))
check("basic latin-1", sp.parse_basic_auth("Basic " + base64.b64encode("u@x:p\xfc".encode("latin-1")).decode()), ("u@x", "p\xfc"))
check("basic none", sp.parse_basic_auth(""), (None, None))
check("basic other scheme", sp.parse_basic_auth("Bearer abc"), (None, None))
check("basic broken base64", sp.parse_basic_auth("Basic %%%"), (None, None))
check("basic no colon", sp.parse_basic_auth("Basic " + base64.b64encode(b"nocolon").decode()), (None, None))

clock = Clock()
lim = sp.FailureLimiter(clock=clock)

# No credentials, wrong password, policy, change
check("no credentials", run(Req(new="newpass123"), lim)[1], 401)
check("no credentials not logged", len(LOGGED), 0)
body, st = run(Req("alice@example.com", "wrong", "newpass123", xff="198.51.100.7"), lim)
check("wrong current password", (body, st), (sp.MSG_BAD_LOGIN, 403))
check("wrong current password logged", len(LOGGED), 1)
check("policy refuses", run(Req("alice@example.com", "right-pass", "short"), lim), ("Passwords must be at least eight characters.", 400))
check("nothing changed yet", CHANGED, [])
check("no new password", run(Req("alice@example.com", "right-pass", ""), lim), ("No password provided.", 400))
check("change", run(Req("alice@example.com", "right-pass", "newpass123"), lim), ("OK", 200))
check("only the caller changed", (CHANGED, USERS["bob@example.com"]), (["alice@example.com"], "bob-pass"))
check("old password no longer works", run(Req("alice@example.com", "right-pass", "x" * 9), lim)[1], 403)
check("new password works", run(Req("alice@example.com", "newpass123", "right-pass"), lim), ("OK", 200))

# Two-factor authentication
n = len(LOGGED)
body, st = run(Req("bob@example.com", "bob-pass", "newpass123"), lim)
check("mfa without code", (body, st), (sp.MSG_MFA, 403))
check("mfa without code not logged", len(LOGGED), n)
check("mfa without code unchanged", USERS["bob@example.com"], "bob-pass")
body, st = run(Req("bob@example.com", "bob-pass", "newpass123", totp="000000"), lim)
check("mfa wrong code", st, 403)
check("mfa wrong code logged", len(LOGGED), n + 1)
check("mfa right code", run(Req("bob@example.com", "bob-pass", "newpass123", totp="123456"), lim), ("OK", 200))

# Limits per account (also from 127.0.0.1 without X-Forwarded-For)
clock.t = 5000.0
lim = sp.FailureLimiter(clock=clock)
for i in range(sp.MAX_FAILURES_ACCOUNT):
	run(Req("alice@example.com", "guess%d" % i, "newpass456", remote="127.0.0.1"), lim)
body, st = run(Req("alice@example.com", "right-pass", "newpass456", xff="203.0.113.9"), lim)
check("account limit: right password refused too", (body, st), (sp.MSG_LIMIT, 429))
check("account limit: other account still works", run(Req("bob@example.com", "newpass123", "bob-pass2", totp="123456", xff="203.0.113.9"), lim)[1], 200)
check("account limit: case of the address", run(Req("ALICE@example.com", "x", "y" * 9), lim)[1], 429)
clock.t += sp.WINDOW + 1
check("account limit expires", run(Req("alice@example.com", "right-pass", "newpass456"), lim), ("OK", 200))

# Limits per address; a success clears the account's count
lim = sp.FailureLimiter(clock=clock)
for i in range(sp.MAX_FAILURES_ADDRESS):
	run(Req("nobody%d@example.com" % i, "x", "newpass789", xff="192.0.2.50"), lim)
check("address limit", run(Req("alice@example.com", "newpass456", "newpass789", xff="192.0.2.50"), lim), (sp.MSG_LIMIT, 429))
check("address limit: other address", run(Req("alice@example.com", "newpass456", "newpass789", xff="192.0.2.51"), lim), ("OK", 200))
lim = sp.FailureLimiter(clock=clock)
for i in range(sp.MAX_FAILURES_ACCOUNT - 1):
	run(Req("alice@example.com", "x", "y" * 9, xff="192.0.2.%d" % i), lim)
run(Req("alice@example.com", "newpass789", "newpass790"), lim)
check("success clears the account's failures", run(Req("alice@example.com", "x", "y" * 9), lim)[1], 403)
check("then the next one counts from 1", lim.blocked("account:alice@example.com", 2), False)

# Size of the limiter
lim = sp.FailureLimiter(clock=clock, max_keys=10)
for i in range(30):
	clock.t += 1
	lim.add("k%d" % i)
check("limiter keeps max_keys", (len(lim.failures), "k29" in lim.failures, "k0" in lim.failures), (10, True, False))
lim = sp.FailureLimiter(clock=clock, max_keys=10)
clock.t += 1
lim.add("account:victim@example.com")
for i in range(30):
	clock.t += 1
	lim.add("address:192.0.2.%d" % i)
check("new addresses do not flush an account's failures", ("account:victim@example.com" in lim.failures, len(lim.failures)), (True, 10))

# Made-up account names with forged addresses (each a new one) do not
# flush a real account's failures
lim = sp.FailureLimiter(clock=clock, max_keys=50)
for i in range(sp.MAX_FAILURES_ACCOUNT):
	clock.t += 1
	run(Req("alice@example.com", "guess%d" % i, "y" * 9), lim)
check("victim blocked", run(Req("alice@example.com", "newpass456", "y" * 9), lim)[1], 429)
for i in range(200):
	clock.t += 0.01
	run(Req("r%d@x" % i, "pw", "y" * 9, xff="2001:db8::%x" % i), lim)
check("made-up accounts are not counted", any(k.startswith("account:r") for k in lim.failures), False)
check("made-up accounts and forged addresses: the victim stays blocked", run(Req("alice@example.com", "newpass456", "y" * 9), lim)[1], 429)
check("a made-up account still counts for its address",
	[run(Req("ghost@example.com", "pw", "y" * 9, xff="192.0.2.99"), lim)[1] for i in range(sp.MAX_FAILURES_ADDRESS + 1)][-1], 429)

if failures:
	print("\n%d case(s) failed: %s" % (len(failures), ", ".join(failures)))
	sys.exit(1)
print("\nall cases pass")
