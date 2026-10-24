#!/usr/local/lib/mailinabox/env/bin/python3
#
# Adaptive fail2ban (fork).
#
# Mail-in-a-Box bans an IP address only after 20 failed logins within 30
# seconds, for 10 minutes. Slow and distributed attacks never reach that.
# This module adds, on top of conf/fail2ban/jails.conf:
#
#  * adaptive banning: repeated offenders get longer bans (bantime.increment,
#    counted over all jails, remembered in fail2ban's database),
#  * slow jails: the same filters with a window of hours,
#  * an allowlist of own networks (added to ignoreip),
#  * a report of failed logins from many IP addresses for one account
#    (password spraying) and of IPs that keep failing below the ban threshold.
#
# The settings live in $STORAGE_ROOT/settings.yaml under "fail2ban" (only the
# values that differ from DEFAULTS are stored). render_config() turns them into
# JAIL_FILE and SERVER_FILE; apply_config() writes them and reloads fail2ban
# when they changed. With adaptive banning and the slow jails off and an empty
# allowlist no file is written, which is exactly Mail-in-a-Box's own setup.
#
# Command line (as root, from the Mail-in-a-Box directory):
#   management/fail2ban_admin.py --setup        write the files, no reload (setup/start.sh)
#   management/fail2ban_admin.py --apply        write the files, reload fail2ban if they changed
#   management/fail2ban_admin.py --print        show what would be written
#   management/fail2ban_admin.py --allow NET    add an address or network to the allowlist and apply
#   management/fail2ban_admin.py --report       print the spraying report

import os, os.path, re, sys, time, datetime, ipaddress, subprocess, ast

import utils

JAIL_FILE = "/etc/fail2ban/jail.d/mailinabox_adaptive.conf"
SERVER_FILE = "/etc/fail2ban/fail2ban.d/mailinabox_adaptive.conf"

DEFAULTS = {
	"adaptive": True,             # bantime.increment over all jails
	"bantime_max": 7 * 86400,     # bantime.maxtime, seconds
	"memory": 30 * 86400,         # dbpurgeage: how long past bans count, seconds
	"slow_jails": True,
	"slow_maxretry": 10,
	"slow_findtime": 6 * 3600,
	"slow_bantime": 3600,
	"allowlist": [],              # addresses/networks added to ignoreip
	"spray_min_ips": 20,          # report an account failing from this many IPs in 24 h
}

# Inclusive ranges, in seconds for durations. bantime_max is at least one week
# so that it never shortens Mail-in-a-Box's recidive ban (1 week).
LIMITS = {
	"bantime_max": (7 * 86400, 365 * 86400),
	"memory": (7 * 86400, 365 * 86400),
	"slow_maxretry": (3, 1000),
	"slow_findtime": (600, 7 * 86400),
	"slow_bantime": (60, 7 * 86400),
	"spray_min_ips": (2, 100000),
}
BOOLEANS = ("adaptive", "slow_jails")
DURATIONS = ("bantime_max", "memory", "slow_findtime", "slow_bantime")
MAX_ALLOWLIST = 100
MIN_PREFIX = { 4: 8, 6: 16 } # refuse networks so wide that they switch fail2ban off

MAIL_PORTS = "465,587,993,995,4190"

# The slow jails reuse Mail-in-a-Box's filters. The mail jails block only the
# mail ports, so a device with an old password does not lock its network out of
# webmail and the control panel.
SLOW_JAILS = [
	# name, filter, log file, ports
	("miab-slow-smtp", "miab-postfix-submission", "/var/log/mail.log", MAIL_PORTS),
	("miab-slow-dovecot", "miab-dovecot-authfail", "/var/log/mail.log", MAIL_PORTS),
	("miab-slow-roundcube", "miab-roundcube", "/var/log/roundcubemail/errors.log", "http,https"),
	("miab-slow-owncloud", "miab-owncloud", "STORAGE_ROOT/owncloud/nextcloud.log", "http,https"),
	("miab-slow-management", "miab-management-daemon", "/var/log/syslog", "http,https"),
]

# SETTINGS

def parse_bool(value):
	if isinstance(value, bool):
		return value
	if isinstance(value, str):
		v = value.strip().lower()
		if v in ("1", "true", "yes", "on"): return True
		if v in ("0", "false", "no", "off", ""): return False
	raise ValueError("must be true or false")

DURATION_UNITS = { "": 1, "s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800 }

def parse_int(value, units=False):
	# Integers, or for durations also "90m", "6h", "1w".
	if isinstance(value, bool):
		raise ValueError("must be a number")
	if isinstance(value, int):
		return value
	m = re.fullmatch(r"\s*(\d{1,9})\s*([smhdw]?)\s*" if units else r"\s*(\d{1,9})\s*", str(value))
	if not m:
		raise ValueError("must be a whole number" + (" of seconds (or with s, m, h, d, w)" if units else ""))
	return int(m.group(1)) * (DURATION_UNITS[m.group(2)] if units else 1)

def parse_network(value):
	# An address or a network in CIDR notation, returned normalized
	# (a single address without prefix). Only digits, hex, ':', '.' and '/'
	# are accepted, so nothing else can end up in the jail file.
	value = str(value).strip()
	if not re.fullmatch(r"[0-9A-Fa-f:.]+(/\d{1,3})?", value):
		raise ValueError(f"'{value[:60]}' is not an IP address or network")
	try:
		net = ipaddress.ip_network(value, strict=False)
	except ValueError:
		raise ValueError(f"'{value}' is not an IP address or network") from None
	if net.prefixlen < MIN_PREFIX[net.version]:
		raise ValueError(f"'{value}' is too wide (IPv{net.version} networks need at least /{MIN_PREFIX[net.version]})")
	if net.num_addresses == 1:
		return str(net.network_address)
	return str(net)

def parse_allowlist(value):
	if value is None:
		return []
	if isinstance(value, str):
		items = [x for x in re.split(r"[\s,;]+", value) if x]
	elif isinstance(value, (list, tuple)):
		items = [str(x) for x in value]
	else:
		raise ValueError("must be a list of IP addresses or networks")
	ret = []
	for item in items:
		net = parse_network(item)
		if net not in ret:
			ret.append(net)
	if len(ret) > MAX_ALLOWLIST:
		raise ValueError(f"has more than {MAX_ALLOWLIST} entries")
	return ret

def validate_settings(values, strict=True):
	# Returns (settings, warnings): a complete settings dict. With strict=True
	# (API input) any invalid or unknown value raises ValueError. With
	# strict=False (the stored file) invalid values fall back to the default
	# and are reported as warnings.
	settings = dict(DEFAULTS)
	settings["allowlist"] = []
	warnings = []
	if not isinstance(values, dict):
		if strict: raise ValueError("Invalid fail2ban settings.")
		return settings, ["The fail2ban settings in settings.yaml are not a mapping; using the defaults."]
	for key, value in values.items():
		try:
			if key not in DEFAULTS:
				raise ValueError("is not a known setting")
			if key in BOOLEANS:
				value = parse_bool(value)
			elif key == "allowlist":
				value = parse_allowlist(value)
			else:
				value = parse_int(value, units=(key in DURATIONS))
				lo, hi = LIMITS[key]
				if not (lo <= value <= hi):
					raise ValueError(f"must be between {lo} and {hi}")
			settings[key] = value
		except ValueError as e:
			msg = f"fail2ban setting {key}: {e}."
			if strict: raise ValueError(msg) from None
			warnings.append(msg + " Using the default.")
	if settings["memory"] < settings["bantime_max"]:
		msg = "fail2ban setting memory: must be at least the maximum ban time (bantime_max)."
		if strict: raise ValueError(msg)
		warnings.append(msg + " Using the maximum ban time.")
		settings["memory"] = settings["bantime_max"]
	return settings, warnings

def get_settings(env):
	stored = utils.load_settings(env).get("fail2ban", {})
	if stored is None: stored = {}
	return validate_settings(stored, strict=False)

def save_settings(env, settings):
	# Store only what differs from the defaults, so that boxes that never
	# changed a value follow future defaults.
	config = utils.load_settings(env)
	diff = { k: v for k, v in settings.items() if k in DEFAULTS and v != DEFAULTS[k] }
	if diff:
		config["fail2ban"] = diff
	else:
		config.pop("fail2ban", None)
	utils.write_settings(config, env)

def update_settings(env, values, reset=False):
	# Validate and store new values (a partial dict) and apply them. On a
	# failed apply the previous settings and files are restored.
	old, _ = get_settings(env)
	merged = {} if reset else { k: v for k, v in old.items() }
	merged.update(values)
	new, _ = validate_settings(merged, strict=True)
	save_settings(env, new)
	try:
		result = apply_config(env, new)
	except Exception:
		save_settings(env, old)
		raise
	result["settings"] = new
	return result

# RENDERING

def base_ignoreip(env):
	# Same list as conf/fail2ban/jails.conf ("127.0.0.1/8 PUBLIC_IP ::1 PUBLIC_IPV6").
	ret = ["127.0.0.1/8"]
	if env.get("PUBLIC_IP"): ret.append(env["PUBLIC_IP"])
	ret.append("::1")
	if env.get("PUBLIC_IPV6"): ret.append(env["PUBLIC_IPV6"])
	return ret

def slow_jail_logpath(path, env):
	return path.replace("STORAGE_ROOT", env["STORAGE_ROOT"])

def render_config(env, settings):
	# Returns ({path: content or None}, skipped). None means: the file must not
	# exist. skipped lists the slow jails left out because their log file does
	# not exist (fail2ban refuses to start with a jail without a log file).
	files = { JAIL_FILE: None, SERVER_FILE: None }
	skipped = []
	if not (settings["adaptive"] or settings["slow_jails"] or settings["allowlist"]):
		return files, skipped

	lines = [
		"# Mail-in-a-Box (fork): adaptive fail2ban. Do not edit.",
		"# Written by management/fail2ban_admin.py from the \"fail2ban\" settings in",
		"# " + os.path.join(env["STORAGE_ROOT"], "settings.yaml") + " (control panel: System > Intrusion protection).",
		"# Read after mailinabox.conf ('_' sorts after '.'), so the [DEFAULT] values here win.",
		"",
		"[DEFAULT]",
	]
	if settings["allowlist"]:
		lines.append("ignoreip = " + " ".join(base_ignoreip(env) + settings["allowlist"]))
	if settings["adaptive"]:
		lines += [
			"# Each new ban of an IP lasts twice as long as its previous one",
			"# (bantime * 2^bans, all jails together), up to bantime.maxtime.",
			"bantime.increment = true",
			"bantime.overalljails = true",
			"bantime.maxtime = %d" % settings["bantime_max"],
		]

	if settings["slow_jails"]:
		for name, filt, logpath, ports in SLOW_JAILS:
			logpath = slow_jail_logpath(logpath, env)
			if not os.path.exists(logpath):
				skipped.append(name)
				continue
			lines += [
				"",
				f"[{name}]",
				"enabled  = true",
				f"filter   = {filt}",
				f"port     = {ports}",
				f"logpath  = {logpath}",
				"backend  = auto",
				"maxretry = %d" % settings["slow_maxretry"],
				"findtime = %d" % settings["slow_findtime"],
				"bantime  = %d" % settings["slow_bantime"],
			]
	files[JAIL_FILE] = "\n".join(lines) + "\n"

	if settings["adaptive"]:
		# The ban history (and the bans restored after a restart) is kept for
		# dbpurgeage seconds. Debian's default of 1 day forgets offenders, and
		# the recidive bans (1 week), after a day.
		files[SERVER_FILE] = "\n".join([
			"# Mail-in-a-Box (fork): adaptive fail2ban. Do not edit.",
			"# Written by management/fail2ban_admin.py (setting \"memory\").",
			"",
			"[Definition]",
			"dbpurgeage = %d" % settings["memory"],
		]) + "\n"
	return files, skipped

def _read(path):
	try:
		with open(path, encoding="utf-8") as f:
			return f.read()
	except FileNotFoundError:
		return None

def _write(path, content):
	if content is None:
		if os.path.exists(path):
			os.unlink(path)
		return
	os.makedirs(os.path.dirname(path), exist_ok=True)
	tmp = path + ".tmp"
	with open(tmp, "w", encoding="utf-8") as f:
		f.write(content)
	os.chmod(tmp, 0o644)
	os.replace(tmp, path)

def config_is_current(env, settings=None):
	if settings is None:
		settings, _ = get_settings(env)
	files, _ = render_config(env, settings)
	return all(_read(path) == content for path, content in files.items())

def apply_config(env, settings=None, reload=True):
	# Write the files. If they changed, check the whole fail2ban configuration
	# and reload fail2ban (if it runs and reload is True). On an error the
	# previous files are put back and ValueError/RuntimeError is raised.
	if settings is None:
		settings, _ = get_settings(env)
	files, skipped = render_config(env, settings)
	old = { path: _read(path) for path in files }
	result = { "changed": old != files, "skipped_jails": skipped, "reloaded": False }
	if not result["changed"]:
		return result

	def restore():
		for path, content in old.items():
			_write(path, content)

	for path, content in files.items():
		_write(path, content)

	ok, out = config_test()
	if not ok:
		# Only blame our files if the configuration was fine before.
		restore()
		ok_before, _ = config_test()
		if ok_before:
			raise ValueError("fail2ban rejected the new configuration, nothing was changed: " + out)
		for path, content in files.items():
			_write(path, content)

	if reload and is_running():
		try:
			f2b("reload", timeout=120)
			result["reloaded"] = True
		except F2BError as e:
			restore()
			try:
				f2b("reload", timeout=120)
			except F2BError:
				pass
			raise RuntimeError(f"fail2ban could not reload the new configuration, the previous one was restored: {e}") from None
	return result

# TALKING TO FAIL2BAN

class F2BError(Exception):
	pass

def f2b(*args, timeout=15):
	# Run fail2ban-client with an argument list (no shell). Returns stdout.
	try:
		p = subprocess.run(["fail2ban-client", *args], capture_output=True, text=True, timeout=timeout,
			env={ "PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C.UTF-8" }, stdin=subprocess.DEVNULL)
	except FileNotFoundError:
		raise F2BError("fail2ban-client is not installed.") from None
	except subprocess.TimeoutExpired:
		raise F2BError(f"fail2ban-client {args[0]} did not answer within {timeout} seconds.") from None
	if p.returncode != 0:
		msg = (p.stderr.strip() or p.stdout.strip()).splitlines()
		raise F2BError(f"fail2ban-client {args[0]} failed: " + (msg[-1] if msg else f"exit code {p.returncode}"))
	return p.stdout

def config_test():
	try:
		f2b("-t", timeout=120)
		return True, ""
	except F2BError as e:
		return False, str(e)

def is_running():
	try:
		f2b("ping", timeout=10)
		return True
	except F2BError:
		return False

def get_jails():
	out = f2b("status")
	m = re.search(r"Jail list:\s*(.*)", out)
	if not m:
		return []
	return [j.strip() for j in m.group(1).split(",") if j.strip()]

def _literal(out):
	# "fail2ban-client banned ..." prints a Python literal (list/dict of strings).
	try:
		return ast.literal_eval(out.strip())
	except (ValueError, SyntaxError):
		raise F2BError("Unexpected output from fail2ban-client.") from None

def banned_in(ips):
	# Returns {ip: [jails where it is banned]}.
	ips = list(ips)
	if not ips:
		return {}
	ret = {}
	for i in range(0, len(ips), 200):
		chunk = ips[i:i + 200]
		res = _literal(f2b("banned", *chunk))
		for ip, jails in zip(chunk, res):
			ret[ip] = list(jails)
	return ret

def jail_status(jail):
	out = f2b("status", jail)
	def num(label):
		m = re.search(re.escape(label) + r":\s*(\d+)", out)
		return int(m.group(1)) if m else None
	return {
		"currently_failed": num("Currently failed"),
		"total_failed": num("Total failed"),
		"currently_banned": num("Currently banned"),
		"total_banned": num("Total banned"),
	}

def jail_bans(jail):
	# "get <jail> banip --with-time" prints one line per ban, ordered by end of ban:
	#   1.2.3.4 \t2026-10-24 10:00:00 + 600 = 2026-10-24 10:10:00
	# in local time. Permanent bans have a ban time of -1.
	now = time.time()
	bans = []
	for line in f2b("get", jail, "banip", "--with-time").splitlines():
		m = re.match(r"\s*(\S+)\s+(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) \+ (-?\d+) = ", line)
		if not m:
			continue
		start = int(time.mktime(time.strptime(m.group(2), "%Y-%m-%d %H:%M:%S")))
		bantime = int(m.group(3))
		end = None if bantime < 0 else start + bantime
		bans.append({
			"ip": m.group(1),
			"start": start,
			"bantime": bantime,
			"end": end,
			"remaining": None if end is None else max(0, int(end - now)),
		})
	return bans

def jail_kind(name):
	if name in { j[0] for j in SLOW_JAILS }: return "slow"
	if name.startswith("miab-") or name in ("dovecot", "recidive", "postfix-sasl", "sshd"): return "miab"
	return "other"

def get_status(env):
	from concurrent.futures import ThreadPoolExecutor
	settings, warnings = get_settings(env)
	ret = {
		"running": False,
		"error": None,
		"jails": [],
		"banned_entries": 0,
		"banned_ips": 0,
		"settings": settings,
		"settings_warnings": warnings,
		"defaults": DEFAULTS,
		"limits": { k: { "min": lo, "max": hi } for k, (lo, hi) in LIMITS.items() },
		"max_allowlist": MAX_ALLOWLIST,
		"config_current": config_is_current(env, settings),
		"slow_jails": [ j[0] for j in SLOW_JAILS ],
	}
	try:
		jails = get_jails()
		banned = {}
		for item in _literal(f2b("banned")):
			banned.update(item)
	except F2BError as e:
		ret["error"] = str(e)
		return ret
	ret["running"] = True

	def one(jail):
		info = { "name": jail, "kind": jail_kind(jail), "banned": [] }
		try:
			info.update(jail_status(jail))
			if banned.get(jail):
				info["banned"] = jail_bans(jail)
		except F2BError as e:
			info["error"] = str(e)
		return info

	with ThreadPoolExecutor(max_workers=8) as pool:
		ret["jails"] = list(pool.map(one, jails))
	ret["banned_entries"] = sum(len(j["banned"]) for j in ret["jails"])
	ret["banned_ips"] = len({ b["ip"] for j in ret["jails"] for b in j["banned"] })
	return ret

def normalize_ip(value):
	# A single IP address (no network, no zone index), normalized like fail2ban
	# prints it.
	value = str(value or "").strip()
	if not re.fullmatch(r"[0-9A-Fa-f:.]{2,45}", value):
		raise ValueError("Invalid IP address.")
	try:
		return str(ipaddress.ip_address(value))
	except ValueError:
		raise ValueError("Invalid IP address.") from None

def check_jail(jail):
	if jail not in get_jails():
		raise ValueError("Unknown jail.")
	return jail

def unban_ip(ip, jail=None):
	# Without a jail: "fail2ban-client unban <ip>", which unbans the address in
	# all jails (recidive included) and deletes its rows from fail2ban's
	# database, so that a later ban starts again at the initial ban time.
	# With a jail: only that jail and that jail's history.
	ip = normalize_ip(ip)
	if jail:
		jail = check_jail(jail)
	before = banned_in([ip]).get(ip, [])
	if jail:
		f2b("set", jail, "unbanip", ip)
	else:
		f2b("unban", ip)
	after = banned_in([ip]).get(ip, [])
	return {
		"ip": ip,
		"jail": jail or None,
		"unbanned_from": [j for j in before if j not in after],
		"still_banned_in": after,
	}

def unban_jail(jail):
	# Unban every IP banned in one jail (fail2ban has no per-jail flush command).
	jail = check_jail(jail)
	ips = f2b("get", jail, "banip").split()
	for i in range(0, len(ips), 200):
		f2b("set", jail, "unbanip", *ips[i:i + 200], timeout=60)
	return { "jail": jail, "unbanned": len(ips) }

# FAILED-LOGIN REPORT (password spraying, slow attacks)

MAIL_LOGS = ("/var/log/mail.log.1", "/var/log/mail.log") # logrotate: weekly, delaycompress
SCAN_HOURS = 48
ACCOUNT_HOURS = 24
PERSISTENT_MIN_FAILURES = 10
PERSISTENT_MIN_HOURS = 12
REPORT_LIMIT = 50

MONTHS = { m: i + 1 for i, m in enumerate(("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")) }
RE_TS_ISO = re.compile(rb"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:?\d\d)?)\s")
RE_TS_BSD = re.compile(rb"([A-Z][a-z]{2}) +(\d{1,2}) (\d\d):(\d\d):(\d\d)\s")
# postfix (465 and 587 both log as postfix/submission/smtpd):
#   warning: unknown[192.0.2.1]: SASL LOGIN authentication failed: (reason), sasl_username=a@b
RE_SMTP = re.compile(rb"postfix/[\w/-]*smtpd\[\d+\]: warning: [^\[\s]*\[([0-9A-Fa-f:.]+)\]: SASL \S+ authentication failed: .*?(?:, sasl_username=(\S+))?\s*$")
# Dovecot 2.4 (and 2.3 "Aborted login"/"Disconnected"):
#   imap-login: Info: Login aborted: ... (auth failed, 3 attempts in 9 secs) (auth_failed): user=<a@b>, method=PLAIN, rip=192.0.2.1, lip=...
# The user name is logged unescaped, so the greedy user=<.*> takes the last rip= (see filter.d/dovecotimap.conf).
RE_DOVECOT = re.compile(rb"(imap|pop3|managesieve|submission)-login: (?:Info: )?.*?\((?:auth failed|authorization failed|user disabled)(?:, (\d+) attempts)?[^)]*\)(?: \(\w+\))?: user=<(.*)>, (?:method=\S+, )?rip=([0-9A-Fa-f:.]+), lip=")

def _line_time(line, now):
	m = RE_TS_ISO.match(line)
	if m:
		s = m.group(1).decode()
		try:
			dt = datetime.datetime.fromisoformat(s)
		except ValueError:
			return None
		if dt.tzinfo is None:
			return time.mktime(dt.timetuple())
		return dt.timestamp()
	m = RE_TS_BSD.match(line)
	if m and m.group(1).decode() in MONTHS:
		# Dovecot's own log lines: local time, no year.
		year = time.localtime(now).tm_year
		parts = (MONTHS[m.group(1).decode()], int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5)))
		try:
			t = time.mktime((year, *parts, 0, 0, -1))
			if t > now + 86400:
				t = time.mktime((year - 1, *parts, 0, 0, -1))
		except (OverflowError, ValueError):
			return None
		return t
	return None

def _seek(f, size, cutoff, now):
	# Binary search for the first line at or after cutoff, so that only the
	# last hours of a large log are read.
	lo, hi = 0, size
	while hi - lo > 65536:
		mid = (lo + hi) // 2
		f.seek(mid)
		f.readline()
		t = None
		for _ in range(100):
			line = f.readline()
			if not line: break
			t = _line_time(line, now)
			if t is not None: break
		if t is None or t >= cutoff:
			hi = mid
		else:
			lo = mid
	f.seek(lo)
	if lo:
		f.readline()

def scan_failed_logins(hours=SCAN_HOURS, files=MAIL_LOGS, now=None):
	# Returns a list of (time, protocol, ip, user, count) for failed logins of
	# the last hours. Passwords are not in these log lines; the user is what the
	# client sent.
	now = now or time.time()
	cutoff = now - hours * 3600
	events = []
	for fn in files:
		try:
			f = open(fn, "rb")
		except OSError:
			continue
		with f:
			_seek(f, os.fstat(f.fileno()).st_size, cutoff, now)
			for line in f:
				if b"authentication failed" in line:
					m = RE_SMTP.search(line)
					if not m: continue
					ip, user, proto, count = m.group(1), m.group(2) or b"", "smtp", 1
				elif b"-login: " in line and (b"auth failed" in line or b"authorization failed" in line or b"user disabled" in line):
					m = RE_DOVECOT.search(line)
					if not m: continue
					proto = m.group(1).decode()
					count = int(m.group(2)) if m.group(2) else 1
					user, ip = m.group(3), m.group(4)
				else:
					continue
				t = _line_time(line, now)
				if t is None or t < cutoff or t > now + 60:
					continue
				events.append((t, proto, ip.decode(), user.decode("utf-8", "replace").strip().lower()[:320], min(count, 1000)))
	return events

def _own_ips(env):
	ret = set()
	for k in ("PUBLIC_IP", "PUBLIC_IPV6", "PRIVATE_IP", "PRIVATE_IPV6"):
		if env.get(k):
			try:
				ret.add(ipaddress.ip_address(env[k]))
			except ValueError:
				pass
	return ret

def failed_login_report(env, settings=None, now=None, events=None, with_bans=True):
	# Accounts with failed logins from many IPs in the last 24 h, and IPs that
	# keep failing for 12 h or more within the last 48 h. Only accounts that
	# exist on the box are named: a "user name" that does not exist can be
	# anything, including a password typed into the wrong field.
	if settings is None:
		settings, _ = get_settings(env)
	now = now or time.time()
	t0 = time.time()
	if events is None:
		events = scan_failed_logins(now=now)
	own = _own_ips(env)
	allow = [ipaddress.ip_network(n, strict=False) for n in settings["allowlist"]]

	try:
		import mailconfig
		known = { u.lower() for u in mailconfig.get_mail_users(env) } | { a[0].lower() for a in mailconfig.get_mail_aliases(env) }
	except Exception:
		known = set()

	def skip(ip):
		try:
			a = ipaddress.ip_address(ip)
		except ValueError:
			return True
		return a.is_loopback or a in own

	def allowed(ip):
		a = ipaddress.ip_address(ip)
		return any(a in n for n in allow)

	acc_cutoff = now - ACCOUNT_HOURS * 3600
	accounts = {}
	ips = {}
	total = 0
	for t, proto, ip, user, count in events:
		if skip(ip): continue
		total += count
		i = ips.setdefault(ip, { "failures": 0, "first": t, "last": t, "users": set() })
		i["failures"] += count
		i["first"] = min(i["first"], t)
		i["last"] = max(i["last"], t)
		i["users"].add(user)
		if t >= acc_cutoff:
			a = accounts.setdefault(user, { "ips": set(), "failures": 0, "protocols": set() })
			a["ips"].add(ip)
			a["failures"] += count
			a["protocols"].add(proto)

	threshold = settings["spray_min_ips"]
	acc_list = []
	unknown = { "accounts": 0, "flagged": 0, "failures": 0 }
	for user, a in accounts.items():
		if user in known:
			acc_list.append({
				"account": user,
				"ips": len(a["ips"]),
				"failures": a["failures"],
				"protocols": sorted(a["protocols"]),
				"flagged": len(a["ips"]) >= threshold,
			})
		else:
			unknown["accounts"] += 1
			unknown["failures"] += a["failures"]
			if len(a["ips"]) >= threshold:
				unknown["flagged"] += 1
	acc_list.sort(key=lambda a: (-a["ips"], -a["failures"], a["account"]))

	persistent = []
	for ip, i in ips.items():
		hours = (i["last"] - i["first"]) / 3600
		if i["failures"] >= PERSISTENT_MIN_FAILURES and hours >= PERSISTENT_MIN_HOURS:
			persistent.append({
				"ip": ip,
				"failures": i["failures"],
				"first": int(i["first"]),
				"last": int(i["last"]),
				"hours": round(hours, 1),
				"accounts": sorted(u for u in i["users"] if u in known),
				"unknown_accounts": len([u for u in i["users"] if u not in known]),
				"allowlisted": allowed(ip),
				"banned_in": [],
			})
	persistent.sort(key=lambda p: (-p["failures"], p["ip"]))
	persistent_total = len(persistent)
	persistent = persistent[:REPORT_LIMIT]
	if with_bans and persistent:
		try:
			b = banned_in([p["ip"] for p in persistent])
			for p in persistent:
				p["banned_in"] = b.get(p["ip"], [])
		except F2BError:
			pass

	return {
		"scan_hours": SCAN_HOURS,
		"account_hours": ACCOUNT_HOURS,
		"spray_min_ips": threshold,
		"persistent_min_failures": PERSISTENT_MIN_FAILURES,
		"persistent_min_hours": PERSISTENT_MIN_HOURS,
		"failures": total,
		"distinct_ips": len(ips),
		"accounts": acc_list[:REPORT_LIMIT],
		"flagged_accounts": [a["account"] for a in acc_list if a["flagged"]],
		"unknown_accounts": unknown,
		"persistent_ips": persistent, # the REPORT_LIMIT with the most failures
		"persistent_total": persistent_total,
		"seconds": round(time.time() - t0, 2),
	}

def check_failed_logins(rounded_values, env, output):
	# Status check (status_checks.py, System section).
	settings, warnings = get_settings(env)
	for w in warnings:
		output.print_warning(w)
	if not config_is_current(env, settings):
		output.print_warning("""The fail2ban configuration does not match the intrusion protection settings.
			Save the settings again in the control panel (System > Intrusion protection) or re-run setup.""")

	try:
		report = failed_login_report(env, settings)
	except Exception as e:
		output.print_warning("Could not read the mail log for failed logins: " + str(e))
		return

	problems = False
	for a in report["accounts"]:
		if not a["flagged"]: continue
		problems = True
		many = f"{report['spray_min_ips']} or more" if rounded_values else str(a["ips"])
		output.print_warning(f"""The account {a['account']} had failed logins from {many} different IP addresses
			in the last {report['account_hours']} hours. This looks like password spraying. Make sure the account
			has a long password that is not used anywhere else, and if it is an administrator, turn on two-factor
			authentication for the control panel.""")

	lurking = [p for p in report["persistent_ips"] if not p["banned_in"] and not p["allowlisted"]]
	own = [p for p in report["persistent_ips"] if p["allowlisted"]]
	if lurking:
		problems = True
		if rounded_values:
			output.print_warning(f"""Some IP addresses kept failing to log in for {report['persistent_min_hours']}
				hours or more without being banned. See System > Intrusion protection in the control panel.""")
		else:
			if settings["slow_jails"]:
				hint = "If this keeps happening, lower the number of failures or lengthen the window of the slow jails."
			else:
				hint = "Turn on the slow jails to ban such addresses."
			count = str(len(lurking))
			if report["persistent_total"] > len(report["persistent_ips"]):
				count = "At least " + count
			output.print_warning(f"""{count} IP address(es) kept failing to log in for {report['persistent_min_hours']}
				hours or more within the last {report['scan_hours']} hours without being banned (a slow attack below
				the ban thresholds). {hint} (System > Intrusion protection in the control panel)""")
			for p in lurking[:5]:
				output.print_line(f"{p['ip']}: {p['failures']} failures in {p['hours']} hours")
	for p in own[:5]:
		problems = True
		who = ", ".join(p["accounts"]) if p["accounts"] else "an unknown account"
		if rounded_values:
			output.print_warning(f"""A device in an allowlisted network ({p['ip']}) keeps failing to log in as {who}.
				It probably has an old password.""")
		else:
			output.print_warning(f"""A device in an allowlisted network ({p['ip']}) failed to log in as {who}
				{p['failures']} times in {p['hours']} hours. It probably has an old password.""")

	if not problems:
		output.print_ok(f"No signs of password spraying or slow login attacks in the mail log of the last {report['scan_hours']} hours.")

# COMMAND LINE

if __name__ == "__main__":
	import json
	env = utils.load_environment()
	args = sys.argv[1:]
	if args == ["--setup"]:
		# Called by setup/start.sh right before fail2ban is restarted. Never
		# stops setup: on a problem Mail-in-a-Box's own jails stay in effect.
		settings, warnings = get_settings(env)
		for w in warnings:
			print(w)
		try:
			result = apply_config(env, settings, reload=False)
		except Exception as e:
			print("Adaptive fail2ban was not configured:", e)
			for path in (JAIL_FILE, SERVER_FILE):
				_write(path, None)
			sys.exit(0)
		for j in result["skipped_jails"]:
			print(f"fail2ban: {j} left out, its log file does not exist yet.")
	elif args == ["--apply"]:
		print(json.dumps(apply_config(env), indent=2))
	elif args == ["--print"]:
		settings, warnings = get_settings(env)
		files, skipped = render_config(env, settings)
		for w in warnings:
			print("#", w)
		for path, content in files.items():
			print(f"### {path}" + (" (removed)" if content is None else ""))
			if content is not None:
				print(content)
		if skipped:
			print("# left out (no log file):", ", ".join(skipped))
	elif len(args) == 2 and args[0] == "--allow":
		settings, _ = get_settings(env)
		allow = settings["allowlist"] + [parse_network(args[1])]
		print(json.dumps(update_settings(env, { "allowlist": allow }), indent=2))
	elif args == ["--report"]:
		print(json.dumps(failed_login_report(env), indent=2))
	else:
		print("usage: fail2ban_admin.py --setup | --apply | --print | --allow NET | --report", file=sys.stderr)
		sys.exit(2)
