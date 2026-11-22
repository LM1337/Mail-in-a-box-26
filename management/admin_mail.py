#!/usr/local/lib/mailinabox/env/bin/python
# The administrator's mail (System > Notifications in the control panel).
#
# The box mails its own reports (status check changes, backup status, TLS
# certificates, the usage report: management/email_administrator.py) to the
# report recipient, which the setting "admin_mail" in
# $STORAGE_ROOT/settings.yaml chooses:
#
#   recipient  "admin":  administrator@PRIMARY_HOSTNAME (the default),
#              "custom": the address in "address" (also outside the box).
#
# Munin's alerts use the same recipient by default (munin_admin.py). The
# alias administrator@ itself is not changed here: it is an address of
# domain control validation, whose destinations may only be administrators
# of the box (mailconfig.add_mail_alias), and it also gets the mail of root,
# of cron jobs and of postmaster@, abuse@, admin@ and hostmaster@ of the
# domains. This module follows it the way Postfix does
# (virtual-alias-maps.cf: an alias set by hand before a mailbox before an
# automatic alias, then the catch-all of the domain) to show where that mail
# ends up and what cannot work (a loop, an address of the box that does not
# exist), lists the last deliveries from the mail log and sends a test mail.
#
# Command line (as root, from the Mail-in-a-Box directory):
#   management/admin_mail.py --status   where the mails go
#   management/admin_mail.py --test     send a test mail to the report recipient

import contextlib
import os
import re
import smtplib
import sys
import time
import uuid
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

import utils
from mailconfig import open_database

MAIL_LOGS = ("/var/log/mail.log", "/var/log/mail.log.1")
LOG_TAIL_BYTES = 8 * 1024 * 1024 # of each log file, from its end
MAX_DELIVERIES = 10
MAX_DEPTH = 20 # aliases followed in a row, as a guard; Postfix allows 1000

# What the box mails to its administrator (shown on the page). "to" says
# where it goes: "reports" to the report recipient, "munin" as Munin's
# setting says, "alias" to the alias administrator@ (and so where it leads).
MAILS = [
	{ "id": "status-changes", "title": "Status Checks Change Notice", "when": "daily, only when a status check changed", "to": "reports" },
	{ "id": "backup", "title": "Backup Status", "when": "daily, when the nightly backup reports something (an error, a warning)", "to": "reports" },
	{ "id": "tls", "title": "TLS Certificate Provisioning Result", "when": "daily, when certificates were requested or renewed", "to": "reports" },
	{ "id": "usage", "title": "Mail-in-a-Box Usage Report", "when": "weekly, on Mondays", "to": "reports" },
	{ "id": "munin", "title": "Munin alerts", "when": "on each change of state of a watched value", "to": "munin" },
	{ "id": "auth-guard", "title": "Logins refused after failed logins from the box itself", "when": "when an account has had too many different wrong passwords through ActiveSync, webmail or Nextcloud (30 in 30 minutes unless System > Intrusion Detection and Prevention sets others; at most one mail an hour)", "to": "reports" },
	{ "id": "send-limit", "title": "Sending of mail was slowed down by the sending limit", "when": "when the box sent more mail than its sending limit allows (30 mails a second unless System > Intrusion Detection and Prevention sets another; at most one mail an hour)", "to": "reports" },
	{ "id": "root", "title": "Mail to root and of cron jobs", "when": "when a program or a cron job mails root", "to": "alias" },
	{ "id": "role", "title": "Mail to postmaster@, abuse@, admin@ and hostmaster@", "when": "of every mail domain, unless the address is set by hand under Aliases", "to": "alias" },
]


DEFAULTS = {
	"recipient": "admin",   # admin | custom
	"address": "",          # for recipient "custom"
}
RECIPIENTS = ("admin", "custom")


class AdminMailError(Exception):
	pass


def admin_address(env):
	return "administrator@" + env['PRIMARY_HOSTNAME']


def validate_address(address):
	# The same narrow form as Munin's custom address (munin_admin.ADDRESS_RE):
	# munin-notify gets this address on its command line when Munin's alerts
	# follow the reports.
	from munin_admin import ADDRESS_RE
	address = (address or "").strip()
	if address == "":
		raise AdminMailError("Enter the address for the reports.")
	if len(address) > 254 or not ADDRESS_RE.fullmatch(address):
		raise AdminMailError("The address for the reports must be a plain address like name@example.com "
			"(letters, digits and _ + - . before the @, no spaces, quotes or names).")
	return address


def validate_settings(values):
	s = dict(DEFAULTS)
	s.update({ k: v for k, v in values.items() if k in DEFAULTS and v is not None })
	for k in DEFAULTS:
		if not isinstance(s[k], str):
			raise AdminMailError(f"Notification setting {k}: must be a string.")
		s[k] = s[k].strip()
	if s["recipient"] not in RECIPIENTS:
		raise AdminMailError("Notification setting recipient: must be one of " + ", ".join(RECIPIENTS) + ".")
	if s["recipient"] == "custom":
		s["address"] = validate_address(s["address"])
	else:
		s["address"] = ""
	return s


def get_settings(env):
	# The stored settings; a broken value falls back to the defaults (warning
	# returned), so that a report is never lost on it.
	stored = utils.load_settings(env).get("admin_mail") or {}
	if not isinstance(stored, dict):
		stored = {}
	try:
		return validate_settings(stored), None
	except AdminMailError as e:
		return dict(DEFAULTS), f"{e} Using the standard address."


def save_settings(env, settings):
	config = utils.load_settings(env)
	diff = { k: v for k, v in settings.items() if k in DEFAULTS and v != DEFAULTS[k] }
	if diff:
		config["admin_mail"] = diff
	else:
		config.pop("admin_mail", None)
	utils.write_settings(config, env)


def report_address(env, settings=None):
	# Where the box's reports go (and Munin's alerts by default).
	if settings is None:
		settings, _ = get_settings(env)
	if settings["recipient"] == "custom":
		return settings["address"]
	return admin_address(env)


def update_settings(env, values):
	# Validate and store new values (fields not given keep their value), then
	# write munin.conf again, whose standard recipient follows. On a failed
	# write the previous settings are restored.
	import munin_admin
	old, _ = get_settings(env)
	merged = dict(old)
	merged.update({ k: v for k, v in values.items() if v is not None })
	new = validate_settings(merged)
	save_settings(env, new)
	try:
		munin_admin.apply_config(env)
	except Exception:
		save_settings(env, old)
		with contextlib.suppress(Exception):
			munin_admin.apply_config(env)
		raise
	# The sending limit never holds the box's reports to this address.
	with contextlib.suppress(Exception):
		import send_limit
		send_limit.apply_config(env)
	return { "settings": new, "changed": new != old }


def _split(destination):
	return [d.strip().lower() for d in (destination or "").replace("\n", ",").split(",") if d.strip()]


def _tables(env):
	c = open_database(env)
	c.execute("SELECT email FROM users")
	users = { row[0].lower() for row in c.fetchall() }
	c.execute("SELECT source, destination, permitted_senders FROM aliases")
	manual = { row[0].lower(): (row[1], row[2]) for row in c.fetchall() }
	c.execute("SELECT source, destination FROM auto_aliases")
	auto = { row[0].lower(): row[1] for row in c.fetchall() }
	return users, manual, auto


def _lookup(addr, users, manual, auto):
	# One lookup of virtual-alias-maps.cf, for the address and then for the
	# catch-all of its domain (as Postfix queries it): a list of destinations,
	# or None when nothing matches. A mailbox is "itself".
	for key in (addr, "@" + addr.rsplit("@", 1)[-1]):
		if key in manual and manual[key][0]:
			return _split(manual[key][0])
		if key == addr and addr in users:
			return [addr]
		if key in auto and auto[key]:
			return _split(auto[key])
	return None


def resolve(env, address=None):
	# Follows address (default administrator@) through the aliases. Returns
	# { "targets": [ { "address", "kind": "mailbox"|"external", "via": [...] } ],
	#   "problems": [ text, ... ] }.
	users, manual, auto = _tables(env)
	# The domains Postfix takes mail for (virtual-mailbox-domains.cf: of the
	# users, the aliases and the automatic aliases).
	local_domains = { a.rsplit("@", 1)[-1] for a in list(users) + list(manual) + list(auto) }
	start = (address or admin_address(env)).lower()
	targets, problems, seen = [], [], set()

	def walk(addr, path):
		if len(path) > MAX_DEPTH:
			problems.append("The chain of aliases " + " → ".join(path + [addr]) + " is too long.")
			return
		if addr in path:
			problems.append("Loop: " + " → ".join(path + [addr]) + ". Mail on this path cannot be delivered.")
			return
		dests = _lookup(addr, users, manual, auto)
		if dests is None:
			final(addr, path, "no mailbox or alias")
			return
		for d in dests:
			if d.startswith("@"):
				# A domain alias: the local part stays.
				d = addr.rsplit("@", 1)[0] + d
			if d == addr:
				# Postfix does not expand an address again that its own
				# expansion contains ("ops@ → ops@, me@elsewhere" keeps a copy
				# in the mailbox): it is delivered as it is (a mailbox is
				# "itself" in _lookup too).
				final(addr, path, "no mailbox (its alias names itself)")
			else:
				walk(d, path + [addr])

	def final(addr, path, what):
		# An address that is not expanded further: a mailbox of the box, an
		# address of another provider, or one of the box that Postfix rejects.
		if addr in users:
			if (addr, "mailbox") not in seen:
				seen.add((addr, "mailbox"))
				targets.append({ "address": addr, "kind": "mailbox", "via": path })
		elif addr.rsplit("@", 1)[-1] in local_domains:
			via = f" (via {' → '.join(path)})" if path else ""
			problems.append(f"{addr}{via} is an address of this box, but {what}. Mail to it is rejected.")
		elif (addr, "external") not in seen:
			seen.add((addr, "external"))
			targets.append({ "address": addr, "kind": "external", "via": path })

	walk(start, [])
	return { "targets": targets, "problems": problems }


def _log_lines(addresses):
	# Delivery lines of the newest mail logs that name one of the addresses
	# as the recipient or as the original recipient, oldest first.
	needles = [f"<{a}>" for a in addresses]
	lines = []
	for path in reversed(MAIL_LOGS):
		try:
			with open(path, "rb") as f:
				f.seek(0, os.SEEK_END)
				size = f.tell()
				f.seek(max(0, size - LOG_TAIL_BYTES))
				data = f.read()
		except OSError:
			continue
		if size > LOG_TAIL_BYTES:
			data = data.split(b"\n", 1)[-1] # a cut first line
		for raw in data.decode("utf-8", "replace").splitlines():
			if " status=" in raw and any(f"to={n}" in raw for n in needles):
				lines.append(raw)
	return lines


LOG_RE = re.compile(r"^(?P<time>\S+) \S+ postfix/(?P<agent>[\w-]+)\[\d+\]: (?P<queue>[0-9A-F]+): to=<(?P<to>[^>]*)>, (?:orig_to=<(?P<orig>[^>]*)>, )?.*?status=(?P<status>\w+)(?: \((?P<text>.*)\))?$")


def recent_deliveries(env, limit=MAX_DELIVERIES):
	# The last deliveries of mail to administrator@ or to the report
	# recipient from the mail log: time, final recipient, status (sent,
	# deferred, bounced) and Postfix's text.
	addresses = { admin_address(env).lower(), report_address(env).lower() }
	ret = []
	for line in _log_lines(sorted(addresses)):
		m = LOG_RE.match(line)
		if not m:
			continue
		if m.group("to").lower() not in addresses and (m.group("orig") or "").lower() not in addresses:
			continue
		ret.append({ "time": m.group("time"), "to": m.group("to"), "status": m.group("status"),
			"text": (m.group("text") or "")[:300], "queue_id": m.group("queue") })
	return ret[-limit:]


def status(env):
	settings, warning = get_settings(env)
	admin = admin_address(env)
	to = report_address(env, settings)
	users, manual, auto = _tables(env)
	alias = manual.get(admin)
	r_admin = resolve(env)
	r_reports = r_admin if to == admin else resolve(env, to)
	warnings = [warning] if warning else []
	alias_warnings = list(r_admin["problems"])
	if admin not in users and (alias is None or not alias[0]) and not r_admin["targets"]:
		alias_warnings.insert(0, f"{admin} has no destination: mail to it is rejected. Add the alias under Mail & Users > Aliases.")
	elif not r_admin["targets"]:
		alias_warnings.append(f"Mail to {admin} reaches no mailbox and no outside address.")
	if to == admin:
		warnings += alias_warnings
	else:
		warnings += r_reports["problems"]
	munin = None
	try:
		import munin_admin
		m = munin_admin.status(env)
		munin = { "recipient": m.get("recipient"), "to": m.get("to") }
	except Exception: # Munin's settings are optional for this page
		pass
	return dict(settings, **{
		"admin_address": admin,
		"to": to,
		"targets": r_reports["targets"],
		"warnings": warnings,
		"admin_alias": {
			"forwards_to": _split(alias[0]) if alias else [],
			"is_mailbox": admin in users,
			"targets": r_admin["targets"],
			"warnings": alias_warnings,
		},
		"mails": MAILS,
		"munin": munin,
		"deliveries": recent_deliveries(env),
	})


ADMIN_SMTP_PORT = 10587


def admin_smtp(timeout=30):
	# Postfix's listener of the box's own reports (setup/mail-postfix.sh): it
	# does not pass the milter of the sending limit, which fails closed, and
	# takes mail only to administrator@ and the report recipient. Port 25
	# where it is missing (an older setup, a downgrade).
	try:
		return smtplib.SMTP("127.0.0.1", ADMIN_SMTP_PORT, timeout=timeout)
	except ConnectionRefusedError:
		return smtplib.SMTP("127.0.0.1", 25, timeout=timeout)


def send_test(env):
	# A test mail to the report recipient, as the box's own reports are sent
	# (SMTP to 127.0.0.1:25, from administrator@). Returns (to, message id).
	admin = admin_address(env)
	to = report_address(env)
	r = resolve(env, to)
	if not r["targets"]:
		raise AdminMailError(f"Mail to {to} reaches no mailbox and no outside address: " + " ".join(r["problems"]))
	msg = EmailMessage()
	msg["From"] = f'"{env["PRIMARY_HOSTNAME"]}" <{admin}>'
	msg["To"] = to
	msg["Subject"] = f"[{env['PRIMARY_HOSTNAME']}] Test of the administrator mail"
	msg["Date"] = formatdate(localtime=True)
	msg["Message-ID"] = make_msgid(idstring=uuid.uuid4().hex[:12], domain=env["PRIMARY_HOSTNAME"])
	msg["Auto-Submitted"] = "auto-generated"
	msg["X-Miab-Test"] = "1"
	where = ", ".join(t["address"] for t in r["targets"])
	msg.set_content(f"This is a test of the administrator mail of {env['PRIMARY_HOSTNAME']}, sent from the control panel at {time.strftime('%Y-%m-%d %H:%M:%S %Z')}.\n\n"
		f"The box sends its reports to {to}, which goes to: {where}.\n"
		"If you read this, they reach you.\n")
	try:
		with admin_smtp(timeout=30) as s:
			s.ehlo()
			s.send_message(msg, from_addr=admin, to_addrs=[to])
	except (OSError, smtplib.SMTPException) as e:
		raise AdminMailError(f"Postfix did not take the test mail: {e}") from None
	return to, msg["Message-ID"]


if __name__ == "__main__":
	env = utils.load_environment()
	args = sys.argv[1:]
	if args == ["--status"]:
		s = status(env)
		print("Reports go to", s["to"])
		for t in s["targets"]:
			print("  delivered to", t["address"], f"({t['kind']})")
		a = s["admin_alias"]
		print(s["admin_address"], "→", ", ".join(a["forwards_to"]) or ("(mailbox)" if a["is_mailbox"] else "(no destination)"))
		for t in a["targets"]:
			print("  delivered to", t["address"], f"({t['kind']})")
		for w in s["warnings"] + [w for w in a["warnings"] if w not in s["warnings"]]:
			print("  WARNING:", w)
	elif args == ["--test"]:
		try:
			to, mid = send_test(env)
			print("Test mail sent to", to, mid)
		except AdminMailError as e:
			print(e, file=sys.stderr)
			sys.exit(1)
	else:
		print("usage: admin_mail.py --status | --test", file=sys.stderr)
		sys.exit(2)
