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
#   auth_guard.py --apply      (setup) writes the settings file that the Lua
#                              code reads from settings.yaml
#
# --apply also writes the box's own addresses (a login from them counts as
# one from the box) and the list of accounts (only real accounts are
# counted), which --notify and every change of the users write again.
#
# The limit (30 different wrong passwords) and the window (30 minutes) are
# set in the control panel (System > Intrusion Detection and Prevention, the API
# /system/auth-guard); the Lua code reads them on every login from the box.
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
EVENT_RE = re.compile(r"^([0-9]{1,12}) (locked|names|pool|list|addresses) ([0-9]{1,9}) (\S{1,210})$")
LIST_PATH_HINT = "/usr/local/lib/mailinabox/dovecot-auth-guard/accounts"
SPAN_KEEP = 4 # the most windows a name's file is kept for (guard.lua's M.SPAN_MAX)


def lua_values(path=GUARD_LUA):
	# The values of guard.lua (M.DIR, M.DEFAULT_LIMIT, ...), so that both read
	# the same ones.
	values = { "DIR": "/run/miab-auth-guard", "DEFAULT_LIMIT": 30, "DEFAULT_WINDOW": 1800, "MAX_NAMES": 10000,
		"SETTINGS": "/usr/local/lib/mailinabox/dovecot-auth-guard/settings",
		"ACCOUNTS": "/usr/local/lib/mailinabox/dovecot-auth-guard/accounts",
		"LIMIT_MIN": 3, "LIMIT_MAX": 1000, "WINDOW_MIN": 60, "WINDOW_MAX": 86400,
		"DEFAULT_SPAN": 4, "SPAN_MIN": 1, "SPAN_MAX": 4 }
	with open(path, encoding="utf-8") as f:
		for line in f:
			m = re.match(r'^M\.([A-Z_]+)(?:, M\.([A-Z_]+))? = (?:"([^"]*)"|([0-9]+)(?:, ([0-9]+))?)', line)
			if not m:
				continue
			if m.group(3) is not None:
				if m.group(1) in values:
					values[m.group(1)] = m.group(3)
				continue
			for name, v in ((m.group(1), m.group(4)), (m.group(2), m.group(5))):
				if name in values and v is not None:
					values[name] = int(v)
	return values


def settings(path=GUARD_LUA, settings_file=None):
	# guard.lua's values plus the limit and the window that apply (LIMIT,
	# WINDOW in seconds): read from the settings file as M.load() reads it.
	cfg = lua_values(path)
	cfg["LIMIT"], cfg["WINDOW"], cfg["SPAN"] = cfg["DEFAULT_LIMIT"], cfg["DEFAULT_WINDOW"], cfg["DEFAULT_SPAN"]
	try:
		with open(settings_file or cfg["SETTINGS"], encoding="ascii", errors="replace") as f:
			text = f.read(4096)
	except OSError:
		text = ""
	for line in text.splitlines():
		m = re.fullmatch(r"([a-z]+) ([0-9]{1,9})", line)
		if not m:
			continue
		v = int(m.group(2))
		if m.group(1) == "limit" and cfg["LIMIT_MIN"] <= v <= cfg["LIMIT_MAX"]:
			cfg["LIMIT"] = v
		elif m.group(1) == "window" and cfg["WINDOW_MIN"] <= v <= cfg["WINDOW_MAX"]:
			cfg["WINDOW"] = v
		elif m.group(1) == "span" and cfg["SPAN_MIN"] <= v <= cfg["SPAN_MAX"]:
			cfg["SPAN"] = v
	return cfg


# The setting of the control panel (System > Intrusion Detection and Prevention), in
# $STORAGE_ROOT/settings.yaml as "auth_guard" (only values that differ from
# the defaults): "limit" (different wrong passwords), "window" (minutes) and
# "span" (windows that a burst counts against, 1 to 4).

class AuthGuardError(ValueError):
	pass


def defaults(cfg=None):
	cfg = cfg or lua_values()
	return { "limit": cfg["DEFAULT_LIMIT"], "window": cfg["DEFAULT_WINDOW"] // 60, "span": cfg["DEFAULT_SPAN"] }


def ranges(cfg=None):
	cfg = cfg or lua_values()
	return { "limit": [cfg["LIMIT_MIN"], cfg["LIMIT_MAX"]], "window": [cfg["WINDOW_MIN"] // 60, cfg["WINDOW_MAX"] // 60],
		"span": [cfg["SPAN_MIN"], cfg["SPAN_MAX"]] }


def validate_settings(values, strict=True, cfg=None):
	# Returns (settings, warnings); strict raises AuthGuardError for a bad
	# value, otherwise it takes the default and warns.
	d, r = defaults(cfg), ranges(cfg)
	out, warnings = dict(d), []
	if not isinstance(values, dict):
		values = {}
	names = { "limit": "The number of different wrong passwords", "window": "The window in minutes",
		"span": "The number of windows" }
	for k in ("limit", "window", "span"):
		if k not in values or values[k] in (None, ""):
			continue
		v = values[k]
		try:
			if isinstance(v, bool) or not re.fullmatch(r"[0-9]{1,6}", str(v).strip()):
				raise ValueError
			v = int(str(v).strip())
			if not r[k][0] <= v <= r[k][1]:
				raise ValueError
		except ValueError:
			msg = f"{names[k]} must be a whole number from {r[k][0]} to {r[k][1]}."
			if strict:
				raise AuthGuardError(msg)
			warnings.append(f"auth_guard {k} in settings.yaml is not valid, the default {d[k]} applies. " + msg)
			continue
		out[k] = v
	return out, warnings


def get_settings(env):
	import utils
	return validate_settings(utils.load_settings(env).get("auth_guard") or {}, strict=False)


def save_settings(env, values):
	import utils
	config = utils.load_settings(env)
	diff = { k: v for k, v in values.items() if v != defaults()[k] }
	if diff:
		config["auth_guard"] = diff
	else:
		config.pop("auth_guard", None)
	utils.write_settings(config, env)


ADDRESS_RE = re.compile(r"^[0-9a-fA-F:.]{2,45}$")


def interface_addresses():
	# Every address of the box's interfaces (ip -o addr: also link-local,
	# temporary and additional ones), without prefix length and scope.
	try:
		out = subprocess.run(["ip", "-o", "addr", "show"], capture_output=True, text=True, timeout=10).stdout
	except (OSError, subprocess.SubprocessError):
		return []
	return re.findall(r"\binet6? ([0-9a-fA-F:.]+)(?:%\S+)?/\d+", out)


def box_addresses(env, interfaces=None):
	# The box's own addresses (/etc/mailinabox.conf and its interfaces): a
	# process on the box can connect to them, so logins from them are logins
	# from the box. Written as Dovecot prints them (compressed, lower case).
	import ipaddress
	out = []
	values = [(env.get(k) or "").strip() for k in ("PUBLIC_IP", "PUBLIC_IPV6", "PRIVATE_IP", "PRIVATE_IPV6")]
	values += interface_addresses() if interfaces is None else interfaces
	for v in values:
		try:
			a = ipaddress.ip_address(v)
		except ValueError:
			continue
		s = a.compressed.lower()
		if ADDRESS_RE.match(s) and s not in out:
			out.append(s)
	return out


def render_settings_file(values, addresses=()):
	return ("# Mail-in-a-Box: Dovecot's limit of failed logins from the box itself\n"
		"# (System > Intrusion Detection and Prevention; management/auth_guard.py). Do not edit.\n"
		f"limit {values['limit']}\nwindow {values['window'] * 60}\nspan {values.get('span', 4)}\n"
		+ "".join(f"local {a}\n" for a in addresses if ADDRESS_RE.match(a)))


def write_settings_file(text, path=None, group=None, mode=0o644):
	# Through the descriptor of its directory, which must be root's and not
	# writable by others (setup/mail-users.sh creates it); a new file is
	# renamed over the old one, so Dovecot reads the old or the new one.
	# group: the group of the new file (with mode 0640 for the accounts).
	path = path or lua_values()["SETTINGS"]
	d, name = os.path.split(path)
	dfd = os.open(d, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
	try:
		st = os.fstat(dfd)
		if st.st_uid != os.geteuid() or stat.S_IMODE(st.st_mode) & 0o022:
			raise AuthGuardError(f"{d} is not a directory of this account that only it may write.")
		try:
			fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dfd)
			try:
				st = os.fstat(fd)
				same = stat.S_IMODE(st.st_mode) == mode and (group is None or st.st_gid == group)
				if same and os.read(fd, 16 * 1048576).decode("utf-8", "replace") == text:
					return False
			finally:
				os.close(fd)
		except FileNotFoundError:
			pass
		tmp = f".{name}.{os.getpid()}.tmp"
		fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=dfd)
		try:
			if group is not None:
				os.fchown(fd, -1, group)
			os.fchmod(fd, mode)
			os.write(fd, text.encode("utf-8"))
			os.fsync(fd)
		finally:
			os.close(fd)
		os.rename(tmp, name, src_dir_fd=dfd, dst_dir_fd=dfd)
		return True
	finally:
		os.close(dfd)


def apply_config(env, values=None, path=None):
	if values is None:
		values, _ = get_settings(env)
	return write_settings_file(render_settings_file(values, box_addresses(env)), path)


def render_accounts(users):
	keys = sorted(set(k for k in (key_of(u) for u in users) if k))
	return "".join(k + "\n" for k in keys)


def write_accounts(env, users=None, path=None):
	# The list of accounts for count.lua (only real accounts are counted):
	# root:dovecot 0640, as it names every account of the box. Written by
	# setup, after every change of the users (mailconfig.kick) and by
	# --notify every 10 minutes.
	if users is None:
		from mailconfig import get_mail_users
		users = get_mail_users(env)
	path = path or lua_values()["ACCOUNTS"]
	return write_settings_file(render_accounts(users), path, group=pwd.getpwnam("dovecot").pw_gid, mode=0o640)


def update_settings(env, values, reset=False, path=None):
	current, _ = get_settings(env)
	new, _ = validate_settings({} if reset else { **current, **values }, strict=True)
	save_settings(env, new)
	try:
		apply_config(env, new, path)
	except Exception:
		save_settings(env, current)
		raise
	return { "settings": new, "changed": new != current }


def key_of(address):
	# The file name of an account name, as guard.lua's M.key() (A-Z in lower
	# case, as Lua's string.lower; every byte other than a-z 0-9 @ . _ + - as
	# %XX); "h-" and a hash for a name longer than 200 characters escaped.
	u = (address or "").encode("utf-8").lower()
	e = "".join(chr(b) if (0x61 <= b <= 0x7a or 0x30 <= b <= 0x39 or b in b"@._+-") else "%%%02X" % b for b in u)
	if len(e) <= 200:
		return "a-" + e
	return "h-%016x-%d" % (fnv1a(u), len(u))


def fnv1a(data):
	# 64-bit FNV-1a, as guard.lua's (Lua 5.4 integers wrap around).
	h = 0xcbf29ce484222325
	for b in data:
		h = ((h ^ b) * 1099511628211) & 0xffffffffffffffff
	return h


def name_of(key):
	# The account name of a file name, printable.
	if key.startswith("h-"):
		return "(a name of more than 200 characters)"
	name = urllib.parse.unquote(key[2:], errors="replace")
	return "".join(c if c.isprintable() and c not in "\r\n" else "?" for c in name)[:254]


def _recent(text, now, window, limit=None, span=4):
	# As guard.lua's M.recent(): lines "<time> <tag>", kept for span windows.
	# Returns the different tags (wrong passwords) within the window and,
	# with limit, whether the name is refused: the different tags of the
	# last k windows reach k * limit, for k = 1 to span.
	newest = {}
	for line in text.splitlines():
		m = re.fullmatch(r"([0-9]{1,12}) ([0-9a-fA-F]{4})", line)
		if m:
			t = int(m.group(1))
			if now - t < span * window and t <= now + 60:
				newest[m.group(2)] = max(t, newest.get(m.group(2), t))
	counts = [sum(1 for t in newest.values() if now - t < k * window) for k in range(1, span + 1)]
	refused = limit is not None and any(counts[k - 1] >= k * limit for k in range(1, span + 1))
	return counts[0], refused, bool(newest)


def scan(state_dir, window, now=None, consume=True, remove=None, limit=30, span=4):
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
			n, refused, kept = _recent(text or "", now, window, limit, span)
			if not kept and now - est.st_mtime >= SPAN_KEEP * window:
				os.unlink(name, dir_fd=dfd)
				continue
			if n or refused:
				names.append({ "key": name, "failures": n, "refused": refused, "last": int(est.st_mtime) })
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
		# The child never returns into the caller's code: whatever happens
		# (also a signal or a broken pipe), it ends with os._exit.
		code = 1
		try:
			os.close(r)
			try:
				os.setgroups([])
				os.setgid(pw.pw_gid)
				os.setuid(pw.pw_uid)
				out = json.dumps({ "ok": func(*args, **kwargs) })
				code = 0
			except Exception as e:
				out = json.dumps({ "error": f"{type(e).__name__}: {e}" })
			with os.fdopen(w, "w") as f:
				f.write(out)
		finally:
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
		elif e["kind"] == "pool":
			lines.append(f"{when}  more than {e['count']} names that are no account of the box failed; such names are refused until there is room"
				" (a real account that is missing from the list of accounts is refused too)")
		elif e["kind"] == "list":
			lines.append(f"{when}  the list of accounts could not be written ({LIST_PATH_HINT}); a new account is not counted on its own until it can be written")
		elif e["kind"] == "addresses":
			lines.append(f"{when}  the addresses of the box's interfaces could not be read (ip -o addr); logins from addresses missing from the settings file are not counted")
		else:
			lines.append(f"{when}  failed logins of more than {e['count']} names; new names get Dovecot's delay")
	if dropped:
		lines.append(f"... and {dropped} more")
	return (
		f"Dovecot's limit of failed logins from the box itself (ActiveSync, Autodiscover, webmail, Nextcloud; {cfg['LIMIT']} "
		f"different wrong passwords in {minutes} minutes, a password sent again counts once):\n\n" + "\n".join(lines) + "\n\n"
		f"These logins come through services of the box, so fail2ban sees only each client's own failures. It may be someone who "
		f"tries the account's passwords through ActiveSync, webmail or Nextcloud from one address below fail2ban's thresholds or "
		f"from many, or a process on the box that tries passwords (a phone with an old password sends the same one again and counts once). While an "
		f"account is refused, its own phones, webmail and Nextcloud are refused too; its mail programs that log in over IMAP "
		f"or SMTP from outside are not. The lock ends when the account has had fewer than {cfg['LIMIT']} different wrong "
		f"passwords in the last {minutes} minutes (after a burst of many at once, it lasts up to {cfg.get('SPAN', 4)} times as long).\n\n"
		f"The current state, the setting and a button to end a lock: the control panel, System > Intrusion Detection and Prevention\n"
		f"(or sudo management/auth_guard.py --status, and --unlock ADDRESS).\n")


def load_state(path=NOTIFY_STATE):
	try:
		with open(path, encoding="utf-8") as f:
			s = json.load(f)
		if isinstance(s, dict) and isinstance(s.get("pending"), list):
			return { "last_sent": int(s.get("last_sent", 0)), "pending": s["pending"][:MAX_PENDING], "dropped": int(s.get("dropped", 0)),
				"problems": [p for p in s.get("problems", []) if p in ("list", "addresses")] }
	except (OSError, ValueError, TypeError):
		pass
	return { "last_sent": 0, "pending": [], "dropped": 0, "problems": [] }


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


def notify(env, cfg, now=None, scan_func=None, send=send_mail, state_path=NOTIFY_STATE, problems=()):
	now = int(time.time()) if now is None else now
	res = (scan_func or (lambda: as_dovecot(scan, cfg["DIR"], cfg["WINDOW"], now, limit=cfg["LIMIT"], span=cfg["SPAN"])))()
	state = load_state(state_path)
	# A problem of this run is mailed once until it is gone again.
	known = set(state.get("problems", []))
	events = list(res["events"]) + [{ "time": now, "kind": k, "count": 0, "key": "-" } for k in problems if k not in known]
	for e in events:
		if len(state["pending"]) < MAX_PENDING:
			state["pending"].append(e)
		else:
			state["dropped"] += 1
	sent = False
	if state["pending"] and now - state["last_sent"] >= NOTIFY_INTERVAL:
		send(message(state["pending"], known_accounts(env), cfg, state["dropped"]))
		state = { "last_sent": now, "pending": [], "dropped": 0 }
		sent = True
	changed = set(problems) != known
	state["problems"] = sorted(set(problems))
	if events or sent or changed:
		save_state(state, state_path)
	return sent


def status(env, scan_func=None):
	# For the control panel (GET /system/auth-guard): the setting, and the
	# names with different wrong passwords from the box in the window.
	cfg = settings()
	values, warnings = get_settings(env)
	if (cfg["LIMIT"], cfg["WINDOW"], cfg["SPAN"]) != (values["limit"], values["window"] * 60, values["span"]):
		warnings.append("Dovecot does not use this setting yet (its settings file differs); save it again, or run setup.")
	res = (scan_func or (lambda: as_dovecot(scan, cfg["DIR"], cfg["WINDOW"], consume=False, limit=cfg["LIMIT"], span=cfg["SPAN"])))()
	accounts = known_accounts(env)
	names = []
	for n in sorted(res["names"], key=lambda n: (-n["failures"], n["key"])):
		names.append({ "key": n["key"], "name": name_of(n["key"]), "failures": n["failures"], "last": n["last"],
			"refused": n.get("refused", n["failures"] >= cfg["LIMIT"]),
			"account": None if accounts is None or not n["key"].startswith("a-") else name_of(n["key"]).lower() in accounts })
	if res["missing"]:
		warnings.append(f"{cfg['DIR']} does not exist: Dovecot cannot count, failed logins from the box itself get its delay (run setup).")
	return { "settings": values, "defaults": defaults(cfg), "ranges": ranges(cfg), "warnings": warnings,
		"applied": { "limit": cfg["LIMIT"], "window": cfg["WINDOW"] // 60, "span": cfg["SPAN"] }, "names": names[:500], "more": max(0, len(names) - 500) }


def unlock(key, scan_func=None):
	if not isinstance(key, str) or not KEY_RE.match(key):
		raise AuthGuardError("Not an account name of the list.")
	cfg = settings()
	(scan_func or (lambda: as_dovecot(scan, cfg["DIR"], cfg["WINDOW"], consume=False, remove=key)))()
	return { "key": key, "name": name_of(key) }


def main(argv):
	if len(argv) < 2 or argv[1] not in ("--notify", "--status", "--unlock", "--apply") or (argv[1] == "--unlock") != (len(argv) == 3) or len(argv) > 3:
		print("usage: auth_guard.py --notify | --status | --unlock ADDRESS | --apply", file=sys.stderr)
		return 2
	if os.geteuid() != 0:
		print("auth_guard.py: run it as root (sudo).", file=sys.stderr)
		return 1
	sys.path.insert(0, HERE)
	from utils import load_environment
	env = load_environment()
	if argv[1] == "--apply":
		values, warnings = get_settings(env)
		for w in warnings:
			print(w, file=sys.stderr)
		if not interface_addresses():
			print("auth_guard.py: the addresses of the box's interfaces could not be read (ip -o addr); only 127.0.0.0/8, ::1 and"
				" the addresses of /etc/mailinabox.conf count as the box itself.", file=sys.stderr)
		apply_config(env, values)
		write_accounts(env)
		return 0
	cfg = settings()
	if argv[1] == "--notify":
		problems = []
		try:
			write_accounts(env)
		except Exception as e:
			print(f"auth_guard.py: the list of accounts could not be written: {e}", file=sys.stderr)
			problems.append("list")
		if not interface_addresses():
			print("auth_guard.py: the addresses of the box's interfaces could not be read (ip -o addr).", file=sys.stderr)
			problems.append("addresses")
		try:
			apply_config(env) # the box's addresses may have changed
		except Exception as e:
			print(f"auth_guard.py: the settings file could not be written: {e}", file=sys.stderr)
		notify(env, cfg, problems=problems)
		return 0
	if argv[1] == "--unlock":
		key = key_of(argv[2])
		if key is None or not KEY_RE.match(key):
			print("auth_guard.py: not an account name.", file=sys.stderr)
			return 1
		unlock(key)
		print(f"The wrong passwords of {name_of(key)} are forgotten; its lock, if any, has ended.")
		return 0
	st = status(env)
	for w in st["warnings"]:
		print(w)
	print(f"Different wrong passwords from the box itself in the last {st['applied']['window']} minutes (refused at {st['applied']['limit']}):")
	if not st["names"]:
		print("  none")
	for n in st["names"]:
		mark = "  REFUSED" if n["refused"] else ""
		print(f"  {n['failures']:5d}  {n['name']}{' (no such account)' if n['account'] is False else ''}{mark}")
	return 0


if __name__ == "__main__":
	sys.exit(main(sys.argv))
