#!/usr/bin/env python3
"""
Offline test of System > Notifications (management/admin_mail.py) --
python3 stdlib only, no box needed.

  * resolve(): administrator@ followed through the aliases as Postfix does
    (an alias set by hand before a mailbox before an automatic alias, then
    the catch-all of the domain, a domain alias keeps the local part): a
    mailbox, an outside address, a loop, an address of the box that does
    not exist, several destinations, an alias that names itself (not a
    loop: a copy for its mailbox);
  * the report recipient: standard, custom, invalid values refused, a
    broken stored value falls back to the standard address;
  * Munin's standard recipient follows the reports (munin-notify --to only
    for another address than administrator@);
  * the last deliveries from a mail log (to= and orig_to=, other mail left
    out, the newest last);
  * the test mail: sender administrator@, recipient the report address,
    marked with X-Miab-Test: 1 and Auto-Submitted.

users.sqlite is a temporary database with the tables of the box; the
modules that need a box (password_hash, email_validator, idna) are replaced
by stand-ins, settings.yaml by a dictionary.

  tests/fork/admin-mail.py

Exit code: 0 = all cases pass, 1 = a case failed (printed).
"""

import os
import sqlite3
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
MGMT = os.path.abspath(os.path.join(HERE, "..", "..", "management"))
HOST = "box.example.com"


class Anything(types.ModuleType):
	def __getattr__(self, name):
		if name.startswith("__"):
			raise AttributeError(name)
		return lambda *a, **k: None


for name in ("password_hash", "idna"):
	sys.modules[name] = Anything(name)
ev = types.ModuleType("email_validator")
ev.EmailNotValidError = ValueError
ev.validate_email = lambda *a, **k: None
sys.modules["email_validator"] = ev
sys.path.insert(0, MGMT)

import utils # noqa: E402 (after the stand-ins)

SETTINGS = {}
utils.load_settings = lambda env: dict(SETTINGS)
def _write_settings(config, env):
	SETTINGS.clear()
	SETTINGS.update(config)
utils.write_settings = _write_settings

import admin_mail # noqa: E402
import munin_admin # noqa: E402

failures = []


def check(name, got, want):
	if got != want:
		failures.append(name)
		print(f"FAIL {name}\n  want: {want!r}\n  got:  {got!r}")
	else:
		print(f"ok   {name}")


def make_db(root, users=(), aliases=(), auto=()):
	os.makedirs(os.path.join(root, "mail"), exist_ok=True)
	db = os.path.join(root, "mail", "users.sqlite")
	if os.path.exists(db):
		os.unlink(db)
	c = sqlite3.connect(db)
	c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL UNIQUE, password TEXT NOT NULL, extra, privileges TEXT NOT NULL DEFAULT '', quota TEXT NOT NULL DEFAULT '0')")
	c.execute("CREATE TABLE aliases (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL UNIQUE, destination TEXT NOT NULL, permitted_senders TEXT)")
	c.execute("CREATE TABLE auto_aliases (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL UNIQUE, destination TEXT NOT NULL, permitted_senders TEXT)")
	for u in users:
		c.execute("INSERT INTO users (email, password) VALUES (?, 'x')", (u,))
	for s, d in aliases:
		c.execute("INSERT INTO aliases (source, destination) VALUES (?, ?)", (s, d))
	for s, d in auto:
		c.execute("INSERT INTO auto_aliases (source, destination) VALUES (?, ?)", (s, d))
	c.commit()
	c.close()


def targets(env, address=None):
	r = admin_mail.resolve(env, address)
	return sorted((t["address"], t["kind"]) for t in r["targets"]), len(r["problems"])


with tempfile.TemporaryDirectory() as root:
	env = { "STORAGE_ROOT": root, "PRIMARY_HOSTNAME": HOST }
	A = "administrator@" + HOST
	AUTO = [("postmaster@" + HOST, A), ("abuse@" + HOST, A), ("root@" + HOST, A)]

	# A fresh install: administrator@ to the first user.
	make_db(root, users=["me@example.com"], aliases=[(A, "me@example.com")], auto=AUTO)
	check("first user", targets(env), ([("me@example.com", "mailbox")], 0))

	# The box of the report: administrator@ -> postmaster@, which is a
	# mailbox; its automatic alias back to administrator@ does not count.
	make_db(root, users=["postmaster@" + HOST], aliases=[(A, "postmaster@" + HOST)], auto=AUTO)
	check("postmaster mailbox", targets(env), ([("postmaster@" + HOST, "mailbox")], 0))

	# The same without the mailbox: a loop.
	make_db(root, users=["me@example.com"], aliases=[(A, "postmaster@" + HOST)], auto=AUTO)
	got = admin_mail.resolve(env)
	check("loop", (got["targets"], len(got["problems"]), "Loop" in " ".join(got["problems"])), ([], 1, True))

	# An address of the box that does not exist.
	make_db(root, users=["me@example.com"], aliases=[(A, "nobody@example.com")], auto=AUTO)
	got = admin_mail.resolve(env)
	check("unknown local", (got["targets"], "no mailbox or alias" in " ".join(got["problems"])), ([], True))

	# Outside the box, and several destinations.
	make_db(root, users=["me@example.com"], aliases=[(A, "me@example.com, ops@other.example")], auto=AUTO)
	check("mailbox and outside", targets(env), ([("me@example.com", "mailbox"), ("ops@other.example", "external")], 0))

	# An alias that names itself keeps a copy in the mailbox (Postfix does
	# not expand an address again that its own expansion contains); without
	# the mailbox that copy is rejected; no loop either way.
	O = "ops@example.com"
	make_db(root, users=["me@example.com", O], aliases=[(A, O), (O, O + ", me@gmail.example")], auto=AUTO)
	check("alias naming itself, a mailbox", targets(env), ([("me@gmail.example", "external"), (O, "mailbox")], 0))
	make_db(root, users=["me@example.com"], aliases=[(A, O), (O, O + ", me@gmail.example")], auto=AUTO)
	got = admin_mail.resolve(env)
	check("alias naming itself, no mailbox", (targets(env)[0], "Loop" in " ".join(got["problems"]), "names itself" in " ".join(got["problems"])),
		([("me@gmail.example", "external")], False, True))

	# An alias set by hand wins over a mailbox of the same name.
	make_db(root, users=["me@example.com", "postmaster@" + HOST], aliases=[(A, "postmaster@" + HOST), ("postmaster@" + HOST, "me@example.com")], auto=AUTO)
	check("alias before mailbox", targets(env), ([("me@example.com", "mailbox")], 0))

	# The catch-all of the domain, and a domain alias (the local part stays).
	make_db(root, users=["all@example.com", "x@example.net"], aliases=[(A, "who@example.com"), ("@example.com", "all@example.com")], auto=AUTO)
	check("catch-all", targets(env), ([("all@example.com", "mailbox")], 0))
	make_db(root, users=["x@example.net"], aliases=[(A, "x@example.org"), ("@example.org", "@example.net")], auto=AUTO)
	check("domain alias", targets(env), ([("x@example.net", "mailbox")], 0))

	# No alias at all: the automatic aliases exist, administrator@ not.
	make_db(root, users=["me@example.com"], aliases=[], auto=AUTO)
	s = admin_mail.status(env)
	check("no administrator alias", (s["admin_alias"]["targets"], any("has no destination" in w for w in s["warnings"])), ([], True))

	# The report recipient.
	make_db(root, users=["me@example.com"], aliases=[(A, "me@example.com")], auto=AUTO)
	check("standard", admin_mail.report_address(env), A)
	munin_admin.apply_config = lambda env, settings=None: False
	r = admin_mail.update_settings(env, { "recipient": "custom", "address": "ops@other.example" })
	check("custom saved", (SETTINGS.get("admin_mail"), r["changed"], admin_mail.report_address(env)),
		({ "recipient": "custom", "address": "ops@other.example" }, True, "ops@other.example"))
	s = admin_mail.status(env)
	check("custom targets", (s["to"], s["targets"][0]["kind"]), ("ops@other.example", "external"))
	refused = 0
	for bad in ({ "recipient": "custom", "address": "" }, { "recipient": "custom", "address": "a b@example.com" },
			{ "recipient": "custom", "address": "x@example.com\nBcc: y@example.com" }, { "recipient": "custom", "address": "$(id)@example.com" },
			{ "recipient": "custom", "address": "-oQ/tmp/x@example.com" }, { "recipient": "everyone" }):
		try:
			admin_mail.update_settings(env, bad)
		except admin_mail.AdminMailError:
			refused += 1
	check("invalid refused, setting kept", (refused, admin_mail.report_address(env)), (6, "ops@other.example"))

	# Munin's standard recipient follows the reports.
	ms = dict(munin_admin.DEFAULTS)
	check("munin follows custom", munin_admin.notify_argv(env, ms), [munin_admin.NOTIFY, "--to", "ops@other.example"])
	check("munin status default", munin_admin.recipient_address(env, ms), "ops@other.example")
	admin_mail.update_settings(env, { "recipient": "admin" })
	check("back to standard", ("admin_mail" in SETTINGS, admin_mail.report_address(env)), (False, A))
	check("munin bare command again", munin_admin.notify_argv(env, ms), [munin_admin.NOTIFY])

	# A broken stored value: the standard address, with a warning.
	SETTINGS["admin_mail"] = { "recipient": "custom", "address": "not an address" }
	st, warning = admin_mail.get_settings(env)
	check("broken setting", (admin_mail.report_address(env), bool(warning)), (A, True))
	SETTINGS.clear()

	# The last deliveries from the mail log.
	log = os.path.join(root, "mail.log")
	with open(log, "w") as f:
		f.write(f"2026-11-20T01:05:01.1+01:00 box postfix/lmtp[1]: AAA111: to=<me@example.com>, orig_to=<{A}>, relay=127.0.0.1[127.0.0.1]:10025, delay=2, dsn=2.0.0, status=sent (250 2.0.0 <me@example.com> x Saved)\n")
		f.write("2026-11-20T01:06:01.1+01:00 box postfix/lmtp[1]: BBB222: to=<me@example.com>, relay=127.0.0.1[127.0.0.1]:10025, delay=2, dsn=2.0.0, status=sent (250 2.0.0 other mail)\n")
		f.write("2026-11-21T01:05:01.1+01:00 box postfix/smtp[2]: CCC333: to=<ops@other.example>, relay=mx.other.example[192.0.2.1]:25, delay=1, dsn=4.7.1, status=deferred (host said: 450 try later)\n")
	admin_mail.MAIL_LOGS = (log,)
	admin_mail.update_settings(env, { "recipient": "custom", "address": "ops@other.example" })
	d = admin_mail.recent_deliveries(env)
	check("deliveries", [(x["queue_id"], x["to"], x["status"]) for x in d],
		[("AAA111", "me@example.com", "sent"), ("CCC333", "ops@other.example", "deferred")])

	# The test mail.
	sent = {}
	class FakeSMTP:
		def __init__(self, host, port, timeout=None):
			sent["server"] = (host, port)
		def __enter__(self): return self
		def __exit__(self, *a): return False
		def ehlo(self): pass
		def send_message(self, msg, from_addr=None, to_addrs=None):
			sent.update(msg=msg, from_addr=from_addr, to_addrs=to_addrs)
	admin_mail.smtplib.SMTP = FakeSMTP
	to, mid = admin_mail.send_test(env)
	m = sent["msg"]
	check("test mail", (to, sent["server"], sent["from_addr"], sent["to_addrs"], m["To"], m["X-Miab-Test"], m["Auto-Submitted"], A in m["From"]),
		("ops@other.example", ("127.0.0.1", 10587), A, ["ops@other.example"], "ops@other.example", "1", "auto-generated", True))

	# The listener of the box's own reports (127.0.0.1:10587, which does not
	# pass the milter of the sending limit); port 25 where it is missing.
	class RefusedSMTP(FakeSMTP):
		def __init__(self, host, port, timeout=None):
			if port == 10587:
				raise ConnectionRefusedError(111, "Connection refused")
			super().__init__(host, port, timeout)
	admin_mail.smtplib.SMTP = RefusedSMTP
	admin_mail.send_test(env)
	check("test mail: port 25 without the listener", sent["server"], ("127.0.0.1", 25))

print(f"{len(failures)} failed." if failures else "all cases passed.")
sys.exit(1 if failures else 0)
