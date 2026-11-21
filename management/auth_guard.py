#!/usr/local/lib/mailinabox/env/bin/python3
#
# The limit of failed logins from the box itself (fork, B126 follow-up).
#
# Dovecot's Lua passdbs conf/dovecot-auth-guard/{check,count}.lua (setup/
# mail-users.sh) count the failed logins that come from 127.0.0.1 and ::1
# (Z-Push's ActiveSync and Autodiscover, Roundcube, Nextcloud's IMAP login,
# and any process on the box) per account name, and refuse an account name
# for these logins while it has LIMIT different wrong passwords within
# WINDOW seconds (a password sent again counts once). Their state is in
# /run/miab-auth-guard (the account dovecot, 0700): a file per name with a
# line "<time> <tag>" per new wrong password (a 16-bit tag of a salted hash,
# never the password), and "events" with a line per new lock.
#
#   auth_guard.py --notify     (cron, every 10 minutes) mails new locks to the
#                              recipient of the box's reports (System >
#                              Notifications), at most one mail an hour, and
#                              removes the files of names without a failure
#                              in the window
#   auth_guard.py --status     the names with failures in the window, locked
#                              ones marked
#   auth_guard.py --unlock ADDRESS
#                              forgets the failures of ADDRESS (its lock ends)
#
# root does nothing by path in the state directory, which the account dovecot
# can write: a child process that runs as dovecot reads and changes it
# through the directory's descriptor and hands the result to root as JSON.

import json
import os
import pwd
import re
import stat
import subprocess
import sys
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD_LUA = os.path.join(HERE, "..", "conf", "dovecot-auth-guard", "guard.lua")
NOTIFY_STATE = "/var/lib/mailinabox/auth-guard-notify.json"
NOTIFY_INTERVAL = 3600 # seconds between two mails
MAX_PENDING = 200 # events kept for the next mail
MAX_FILE = 65536 # bytes read of a name's file
SUBJECT = "Logins refused after failed logins from the box itself"

KEY_RE = re.compile(r"^(a-[a-z0-9@._+%-]{1,200}|h-[0-9a-f]{16}-[0-9]{1,4})$")
EVENT_RE = re.compile(r"^([0-9]{1,12}) (locked|names) ([0-9]{1,9}) (\S{1,210})$")


def settings(path=GUARD_LUA):
	# The values of guard.lua (M.DIR, M.WINDOW, M.LIMIT, M.MAX_NAMES), so that
	# both read the same ones.
	values = { "DIR": "/run/miab-auth-guard", "WINDOW": 1800, "LIMIT": 100, "MAX_NAMES": 10000 }
	with open(path, encoding="utf-8") as f:
		for line in f:
			m = re.match(r'^M\.([A-Z_]+) = (?:"([^"]*)"|([0-9]+))', line)
			if m and m.group(1) in values:
				values[m.group(1)] = m.group(2) if m.group(2) is not None else int(m.group(3))
	return values


def key_of(address):
	# The file name of an account name, as guard.lua's M.key() (A-Z in lower
	# case, as Lua's string.lower; every byte other than a-z 0-9 @ . _ + - as
	# %XX); None for a name that guard.lua hashes (longer than 200 characters
	# escaped).
	u = (address or "").encode("utf-8").lower()
	e = "".join(chr(b) if (0x61 <= b <= 0x7a or 0x30 <= b <= 0x39 or b in b"@._+-") else "%%%02X" % b for b in u)
	if len(e) <= 200:
		return "a-" + e
	return None


def name_of(key):
	# The account name of a file name, printable.
	if key.startswith("h-"):
		return "(a name of more than 200 characters)"
	name = urllib.parse.unquote(key[2:], errors="replace")
	return "".join(c if c.isprintable() and c not in "\r\n" else "?" for c in name)[:254]


def _recent(text, now, window):
	# The different tags (wrong passwords) within the window, as guard.lua's
	# M.recent(): lines "<time> <tag>".
	tags = set()
	for line in text.splitlines():
		m = re.fullmatch(r"([0-9]{1,12}) ([0-9a-fA-F]{4})", line)
		if m:
			t = int(m.group(1))
			if now - t < window and t <= now + 60:
				tags.add(m.group(2))
	return len(tags)


def scan(state_dir, window, now=None, consume=True, remove=None):
	# Runs as the account dovecot (see as_dovecot). Returns the names with
	# failures within the window and, with consume, the new events; removes
	# the files of names without failures within the window, and the file of
	# the key "remove".
	now = int(time.time()) if now is None else now
	try:
		dfd = os.open(state_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
	except FileNotFoundError:
		return { "names": [], "events": [], "missing": True }
	try:
		st = os.fstat(dfd)
		if st.st_uid != os.geteuid() or stat.S_IMODE(st.st_mode) & 0o077:
			raise ValueError(f"{state_dir} is not the directory of this account with mode 0700")

		def read(name, limit=MAX_FILE):
			fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dfd)
			try:
				if not stat.S_ISREG(os.fstat(fd).st_mode):
					return None
				return os.read(fd, limit).decode("utf-8", "replace")
			finally:
				os.close(fd)

		events = []
		if consume:
			# "events" is renamed first, so that count.lua starts a new one.
			for name in ("events.read", "events"):
				try:
					if name == "events":
						os.rename("events", "events.read", src_dir_fd=dfd, dst_dir_fd=dfd)
					text = read("events.read", 1048576 + 4096)
				except FileNotFoundError:
					continue
				for line in (text or "").splitlines():
					m = EVENT_RE.match(line)
					if m and (m.group(4) == "-" or KEY_RE.match(m.group(4))):
						events.append({ "time": int(m.group(1)), "kind": m.group(2), "count": int(m.group(3)), "key": m.group(4) })
				os.unlink("events.read", dir_fd=dfd)

		names = []
		for entry in os.scandir(dfd):
			name = entry.name
			try:
				est = os.stat(name, dir_fd=dfd, follow_symlinks=False)
			except FileNotFoundError:
				continue
			if name.endswith(".tmp"):
				if now - est.st_mtime > 60:
					os.unlink(name, dir_fd=dfd)
				continue
			if not KEY_RE.match(name) or not stat.S_ISREG(est.st_mode):
				continue
			if name == remove:
				os.unlink(name, dir_fd=dfd)
				continue
			text = read(name)
			n = _recent(text or "", now, window)
			if n == 0 and now - est.st_mtime >= window:
				os.unlink(name, dir_fd=dfd)
				continue
			if n:
				names.append({ "key": name, "failures": n, "last": int(est.st_mtime) })
		return { "names": names, "events": events, "missing": False }
	finally:
		os.close(dfd)


def as_dovecot(func, *args, **kwargs):
	# Runs func in a child process as the account dovecot and returns its
	# result (JSON through a pipe).
	pw = pwd.getpwnam("dovecot")
	r, w = os.pipe()
	pid = os.fork()
	if pid == 0:
		os.close(r)
		code = 0
		try:
			os.setgroups([])
			os.setgid(pw.pw_gid)
			os.setuid(pw.pw_uid)
			out = json.dumps({ "ok": func(*args, **kwargs) })
		except Exception as e:
			out = json.dumps({ "error": f"{type(e).__name__}: {e}" })
			code = 1
		with os.fdopen(w, "w") as f:
			f.write(out)
		os._exit(code)
	os.close(w)
	with os.fdopen(r) as f:
		data = f.read()
	os.waitpid(pid, 0)
	res = json.loads(data or '{"error": "no answer"}')
	if "error" in res:
		raise RuntimeError(res["error"])
	return res["ok"]


def known_accounts(env):
	try:
		from mailconfig import get_mail_users
		return set(u.lower() for u in get_mail_users(env))
	except Exception:
		return None


def describe(key, accounts):
	name = name_of(key)
	if accounts is not None and key.startswith("a-") and name.lower() not in accounts:
		return name + " (no such account)"
	return name


def message(events, accounts, cfg, dropped=0):
	lines = []
	minutes = cfg["WINDOW"] // 60
	for e in events:
		when = time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime(e["time"]))
		if e["kind"] == "locked":
			lines.append(f"{when}  {describe(e['key'], accounts)}: {e['count']} different wrong passwords in {minutes} minutes")
		else:
			lines.append(f"{when}  failed logins of more than {e['count']} account names in {minutes} minutes; the names with the fewest failures are no longer counted")
	if dropped:
		lines.append(f"... and {dropped} more")
	return (
		f"Dovecot refused the logins from the box itself (ActiveSync, Autodiscover, webmail, Nextcloud) for these accounts "
		f"after {cfg['LIMIT']} different wrong passwords in {minutes} minutes (a password sent again counts once):\n\n" + "\n".join(lines) + "\n\n"
		f"These logins come through services of the box, so fail2ban does not see the failures of one account from many "
		f"addresses. It may be someone who tries the account's passwords through ActiveSync, webmail or Nextcloud from many "
		f"addresses, or a process on the box that tries passwords (a phone with an old password sends the same one again and counts once). While an "
		f"account is refused, its own phones, webmail and Nextcloud are refused too; its mail programs that log in over IMAP "
		f"or SMTP from outside are not. The lock ends when the account has had fewer than {cfg['LIMIT']} different wrong "
		f"passwords in the last {minutes} minutes.\n\n"
		f"The current state: sudo management/auth_guard.py --status\n"
		f"To end a lock now: sudo management/auth_guard.py --unlock ADDRESS\n")


def load_state(path=NOTIFY_STATE):
	try:
		with open(path, encoding="utf-8") as f:
			s = json.load(f)
		if isinstance(s, dict) and isinstance(s.get("pending"), list):
			return { "last_sent": int(s.get("last_sent", 0)), "pending": s["pending"][:MAX_PENDING], "dropped": int(s.get("dropped", 0)) }
	except (OSError, ValueError, TypeError):
		pass
	return { "last_sent": 0, "pending": [], "dropped": 0 }


def save_state(state, path=NOTIFY_STATE):
	# /var/lib/mailinabox belongs to root.
	tmp = path + ".new"
	fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
	with os.fdopen(fd, "w", encoding="utf-8") as f:
		json.dump(state, f)
	os.replace(tmp, path)


def send_mail(text):
	p = subprocess.run([sys.executable, os.path.join(HERE, "email_administrator.py"), SUBJECT],
		input=text, text=True, capture_output=True, timeout=120)
	if p.returncode != 0:
		raise RuntimeError("email_administrator.py: " + (p.stderr.strip() or p.stdout.strip())[-300:])


def notify(env, cfg, now=None, scan_func=None, send=send_mail, state_path=NOTIFY_STATE):
	now = int(time.time()) if now is None else now
	res = (scan_func or (lambda: as_dovecot(scan, cfg["DIR"], cfg["WINDOW"], now)))()
	state = load_state(state_path)
	for e in res["events"]:
		if len(state["pending"]) < MAX_PENDING:
			state["pending"].append(e)
		else:
			state["dropped"] += 1
	sent = False
	if state["pending"] and now - state["last_sent"] >= NOTIFY_INTERVAL:
		send(message(state["pending"], known_accounts(env), cfg, state["dropped"]))
		state = { "last_sent": now, "pending": [], "dropped": 0 }
		sent = True
	if res["events"] or sent:
		save_state(state, state_path)
	return sent


def main(argv):
	if len(argv) < 2 or argv[1] not in ("--notify", "--status", "--unlock") or (argv[1] == "--unlock") != (len(argv) == 3) or len(argv) > 3:
		print("usage: auth_guard.py --notify | --status | --unlock ADDRESS", file=sys.stderr)
		return 2
	if os.geteuid() != 0:
		print("auth_guard.py: run it as root (sudo).", file=sys.stderr)
		return 1
	cfg = settings()
	sys.path.insert(0, HERE)
	from utils import load_environment
	env = load_environment()
	if argv[1] == "--notify":
		notify(env, cfg)
		return 0
	if argv[1] == "--unlock":
		key = key_of(argv[2])
		if key is None or not KEY_RE.match(key):
			print("auth_guard.py: not an account name.", file=sys.stderr)
			return 1
		as_dovecot(scan, cfg["DIR"], cfg["WINDOW"], consume=False, remove=key)
		print(f"The failed logins of {name_of(key)} are forgotten.")
		return 0
	res = as_dovecot(scan, cfg["DIR"], cfg["WINDOW"], consume=False)
	if res["missing"]:
		print(f"{cfg['DIR']} does not exist (Dovecot's limit of failed logins from the box itself is not set up).")
		return 1
	accounts = known_accounts(env)
	print(f"Different wrong passwords from the box itself in the last {cfg['WINDOW'] // 60} minutes (refused at {cfg['LIMIT']}):")
	if not res["names"]:
		print("  none")
	for n in sorted(res["names"], key=lambda n: -n["failures"]):
		mark = "  REFUSED" if n["failures"] >= cfg["LIMIT"] else ""
		print(f"  {n['failures']:5d}  {describe(n['key'], accounts)}{mark}")
	return 0


if __name__ == "__main__":
	sys.exit(main(sys.argv))
