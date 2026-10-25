#!/usr/local/lib/mailinabox/env/bin/python3
#
# Adaptive fail2ban (fork).
#
# Mail-in-a-Box bans an IP address only after 20 failed logins within 30
# seconds, for 10 minutes. Slow and distributed attacks never reach that.
# This module adds, on top of conf/fail2ban/jails.conf:
#
#  * adaptive banning: repeated offenders get longer bans (bantime.increment,
#    per jail, remembered in fail2ban's database); bans of the web ports keep
#    their fixed length,
#  * slow jails: the same filters with a window of hours (mail ports by
#    default, the web logins only when turned on),
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
	"adaptive": True,             # bantime.increment, per jail
	"bantime_max": 7 * 86400,     # bantime.maxtime, seconds
	"memory": 30 * 86400,         # dbpurgeage: how long past bans count, seconds
	"slow_jails": True,           # slow jails for the mail logins
	"slow_web_jails": False,      # slow jails for webmail, Nextcloud, control panel
	"slow_maxretry": 20,
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
BOOLEANS = ("adaptive", "slow_jails", "slow_web_jails")
DURATIONS = ("bantime_max", "memory", "slow_findtime", "slow_bantime")
MAX_ALLOWLIST = 100
MIN_PREFIX = { 4: 8, 6: 16 } # refuse networks so wide that they switch fail2ban off

MAIL_PORTS = "465,587,993,995,4190"

# The slow jails reuse Mail-in-a-Box's filters. The mail jails block only the
# mail ports, so a device with an old password does not lock its network out of
# webmail and the control panel. The web jails block HTTP and HTTPS, so they
# are a separate switch, off by default: a CalDAV/CardDAV client with an old
# password polls Nextcloud every few minutes and would ban its whole network
# from webmail and the control panel.
SLOW_MAIL_JAILS = [
	# name, filter, log file, ports
	("miab-slow-smtp", "miab-postfix-submission", "/var/log/mail.log", MAIL_PORTS),
	("miab-slow-dovecot", "miab-dovecot-authfail", "/var/log/mail.log", MAIL_PORTS),
]
SLOW_WEB_JAILS = [
	("miab-slow-roundcube", "miab-roundcube", "/var/log/roundcubemail/errors.log", "http,https"),
	("miab-slow-owncloud", "miab-owncloud", "STORAGE_ROOT/owncloud/nextcloud.log", "http,https"),
	("miab-slow-management", "miab-management-daemon", "/var/log/syslog", "http,https"),
]
SLOW_JAILS = SLOW_MAIL_JAILS + SLOW_WEB_JAILS

# Mail-in-a-Box's own jails (conf/fail2ban/jails.conf) that ban HTTP and HTTPS.
# With adaptive banning their bans, and those of the slow web jails, keep their
# fixed length: a growing ban would lock a whole office out of the control
# panel (where it could unban itself), webmail and Nextcloud for days.
# recidive still bans addresses that are banned again and again.
WEB_JAILS = ["miab-management", "miab-munin", "miab-owncloud", "miab-roundcube"]

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
	result["unbanned_allowlisted"] = unban_allowlisted(new)
	return result

def unban_allowlisted(settings):
	# ignoreip only stops new bans: an address banned before its network was
	# put on the allowlist stays banned (fail2ban also restores it from its
	# database after a restart). Unban those addresses in all jails, with their
	# ban history. Returns the unbanned addresses.
	if not settings["allowlist"] or not is_running():
		return []
	nets = [ipaddress.ip_network(n, strict=False) for n in settings["allowlist"]]
	try:
		banned = set()
		for item in _literal(f2b("banned")):
			for ips in item.values():
				banned.update(ips)
	except F2BError:
		return []
	ret = []
	for ip in sorted(banned):
		try:
			a = ipaddress.ip_address(ip)
		except ValueError:
			continue
		if any(a in n for n in nets):
			try:
				unban_ip(ip)
				ret.append(ip)
			except (ValueError, F2BError):
				pass
	return ret

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
	if not (settings["adaptive"] or settings["slow_jails"] or settings["slow_web_jails"] or settings["allowlist"]):
		return files, skipped

	lines = [
		"# Mail-in-a-Box (fork): adaptive fail2ban. Do not edit.",
		"# Written by management/fail2ban_admin.py from the \"fail2ban\" settings in",
		"# " + os.path.join(env["STORAGE_ROOT"], "settings.yaml") + " (control panel: System > Intrusion Protection).",
		"# Read after mailinabox.conf ('_' sorts after '.'), so the [DEFAULT] values here win.",
		"",
		"[DEFAULT]",
	]
	if settings["allowlist"]:
		lines.append("ignoreip = " + " ".join(base_ignoreip(env) + settings["allowlist"]))
	if settings["adaptive"]:
		# No bantime.overalljails: with it fail2ban 1.1 takes the exponent from
		# the sum of the ban counts of all jails and stores that sum again in
		# this jail's row, so one burst banned by three jails at once sent the
		# next ban straight to the maximum. Addresses that are banned again and
		# again in any jail are recidive's job.
		lines += [
			"# Each new ban of an address in a jail lasts twice as long as its",
			"# previous ban in that jail (bantime * 2^bans), up to bantime.maxtime.",
			"# Bans in other jails do not count; recidive bans addresses that are",
			"# banned again and again in any jail.",
			"bantime.increment = true",
			"bantime.maxtime = %d" % settings["bantime_max"],
		]
		lines += [
			"",
			"# Bans of the web ports keep their fixed length, so that an office behind",
			"# one address cannot lose the control panel, webmail and Nextcloud for days.",
		]
		for name in WEB_JAILS:
			lines += [f"[{name}]", "bantime.increment = false"]

	slow = (SLOW_MAIL_JAILS if settings["slow_jails"] else []) + (SLOW_WEB_JAILS if settings["slow_web_jails"] else [])
	for name, filt, logpath, ports in slow:
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
		if settings["adaptive"] and ports == "http,https":
			lines.append("bantime.increment = false")
	files[JAIL_FILE] = "\n".join(lines) + "\n"

	if settings["adaptive"]:
		# bantime.increment knows an address only while its row is in the
		# database. fail2ban purges a row of the bips table once the ban is
		# older than dbpurgeage and also older than 3 x its ban time. With
		# Debian's 1 day a 10-minute ban is forgotten after a day, and a repeat
		# offender starts again at 10 minutes.
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

def _bantime_options(content):
	# The bantime.* options of a jail file, with their section.
	ret = []
	section = None
	for line in (content or "").splitlines():
		if line.startswith("["):
			section = line.strip()
		elif line.startswith("bantime."):
			ret.append((section, line.strip()))
	return ret

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

	# A plain reload keeps the running jail objects. It sets the bantime.*
	# options that are in the files, but never resets those that were removed:
	# after turning adaptive banning off, every jail would go on with
	# bantime.increment until fail2ban is restarted. So when these options
	# change, the jails are restarted ("reload --restart"); their bans are
	# restored from fail2ban's database, only the failures counted so far are
	# lost.
	restart = _bantime_options(old[JAIL_FILE]) != _bantime_options(files[JAIL_FILE])
	reload_args = ["reload", "--restart"] if restart else ["reload"]
	if reload and is_running():
		try:
			f2b(*reload_args, timeout=180)
			result["reloaded"] = True
			result["restarted"] = restart
		except F2BError as e:
			restore()
			try:
				f2b(*reload_args, timeout=180)
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
		"slow_jails": [ j[0] for j in SLOW_MAIL_JAILS ],
		"slow_web_jails": [ j[0] for j in SLOW_WEB_JAILS ],
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

def db_path():
	# fail2ban's sqlite database, None if it has none.
	out = f2b("get", "dbfile").strip()
	m = re.search(r"(/\S+)$", out)
	return m.group(1) if m else None

def _forget_stopped_jails(ip, running):
	# "fail2ban-client unban <ip>" deletes the address's rows only for the
	# running jails. Rows of jails that no longer run (e.g. the slow jails
	# after they were turned off) would make a ban start longer when such a
	# jail runs again, so they are deleted here. Returns the number of rows.
	import sqlite3
	path = db_path()
	if not path or not os.path.exists(path):
		return 0
	con = sqlite3.connect(path, timeout=10)
	try:
		with con:
			marks = ",".join("?" * len(running))
			n = 0
			for table in ("bips", "bans"):
				n += con.execute(f"DELETE FROM {table} WHERE ip = ? AND jail NOT IN ({marks})", [ip, *running]).rowcount
			return n
	finally:
		con.close()

def unban_ip(ip, jail=None):
	# Without a jail: "fail2ban-client unban <ip>", which unbans the address in
	# all jails (recidive included) and deletes its rows from fail2ban's
	# database (also those of jails that no longer run), so that a later ban
	# starts again at the initial ban time. The failures that jails counted but
	# did not ban yet are kept by fail2ban.
	# With a jail: only that jail and that jail's history.
	ip = normalize_ip(ip)
	if jail:
		jail = check_jail(jail)
	before = banned_in([ip]).get(ip, [])
	history_complete = True
	if jail:
		f2b("set", jail, "unbanip", ip)
	else:
		f2b("unban", ip)
		try:
			_forget_stopped_jails(ip, get_jails())
		except Exception:
			history_complete = False
	after = banned_in([ip]).get(ip, [])
	return {
		"ip": ip,
		"jail": jail or None,
		"unbanned_from": [j for j in before if j not in after],
		"still_banned_in": after,
		"history_deleted": (not jail) and history_complete,
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
# Dovecot 2.4 (and 2.3 "Aborted login"/"Disconnected"), through syslog without "Info: " (B85),
# in older files written by Dovecot itself with it:
#   dovecot: imap-login: Login aborted: ... (auth failed, 3 attempts in 9 secs) (auth_failed): user=<a@b>, method=PLAIN, rip=192.0.2.1, lip=...
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
		# Dovecot's own log lines (before B85): local time, no year.
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

def client_info(env, ip, settings):
	# The address the control panel is used from (as nginx passes it on), for
	# the "your address" hint on the page. None if it is not a valid address.
	try:
		ip = normalize_ip(ip)
	except ValueError:
		return None
	a = ipaddress.ip_address(ip)
	return {
		"ip": ip,
		"own": a.is_loopback or a in _own_ips(env),
		"allowlisted": any(a in ipaddress.ip_network(n, strict=False) for n in settings["allowlist"]),
		# An IPv6 client usually has a temporary address that changes daily,
		# and the other devices of its network have other addresses: offer the
		# /64 for the allowlist instead.
		"network": str(ipaddress.ip_network(ip + "/64", strict=False)) if a.version == 6 else None,
	}

def bans_since(since):
	# {ip: set of jails} of the bans fail2ban recorded since the given time
	# (its bans table, opened read-only). Rows older than dbpurgeage are gone.
	import sqlite3, urllib.parse
	path = db_path()
	if not path or not os.path.exists(path):
		return {}
	con = sqlite3.connect("file:" + urllib.parse.quote(path) + "?mode=ro", uri=True, timeout=5)
	try:
		ret = {}
		for ip, jail in con.execute("SELECT ip, jail FROM bans WHERE timeofban >= ?", (int(since),)):
			ret.setdefault(str(ip), set()).add(str(jail))
		return ret
	finally:
		con.close()

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
				"banned_before": [],
			})
	persistent.sort(key=lambda p: (-p["failures"], p["ip"]))
	persistent_total = len(persistent)
	persistent = persistent[:REPORT_LIMIT]

	# Current bans, and the bans of the scan window that have run out (so that
	# an address banned 13 hours ago is not reported as "never banned").
	current = {}
	earlier = {}
	if with_bans:
		try:
			for item in _literal(f2b("banned")):
				for jail, banned_ips in item.items():
					for ip in banned_ips:
						current.setdefault(ip, []).append(jail)
		except F2BError:
			pass
		try:
			earlier = bans_since(now - SCAN_HOURS * 3600)
		except Exception:
			pass
	for p in persistent:
		p["banned_in"] = sorted(current.get(p["ip"], []))
		p["banned_before"] = sorted(earlier.get(p["ip"], set()) - set(p["banned_in"]))

	# Banned addresses that failed only as one or two existing accounts: often
	# a device of one's own with an old password (or an attack on these
	# accounts). The allowlist is the remedy for the former.
	devices = []
	for ip, i in ips.items():
		if ip not in current or allowed(ip):
			continue
		users = i["users"]
		if users and len(users) <= 2 and all(u in known for u in users):
			devices.append({ "ip": ip, "accounts": sorted(users), "failures": i["failures"], "banned_in": sorted(current[ip]) })
	devices.sort(key=lambda d: (-d["failures"], d["ip"]))

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
		"banned_devices": devices[:REPORT_LIMIT],
		"seconds": round(time.time() - t0, 2),
	}

def check_failed_logins(rounded_values, env, output):
	# Status check (status_checks.py, System section).
	settings, warnings = get_settings(env)
	for w in warnings:
		output.print_warning(w)
	if not config_is_current(env, settings):
		output.print_warning("""The fail2ban configuration does not match the intrusion protection settings.
			Save the settings again in the control panel (System > Intrusion Protection) or re-run setup.""")

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

	# Addresses banned now or earlier in the scan window were caught; only the
	# ones never banned in it are below the thresholds.
	lurking = [p for p in report["persistent_ips"] if not p["banned_in"] and not p["banned_before"] and not p["allowlisted"]]
	own = [p for p in report["persistent_ips"] if p["allowlisted"]]
	if lurking:
		problems = True
		if rounded_values:
			output.print_warning(f"""Some IP addresses kept failing to log in for {report['persistent_min_hours']}
				hours or more without ever being banned. See System > Intrusion Protection in the control panel.""")
		else:
			if settings["slow_jails"]:
				hint = "If this keeps happening, lower the number of failures or lengthen the window of the slow jails."
			else:
				hint = "Turn on the slow jails to ban such addresses."
			count = str(len(lurking))
			if report["persistent_total"] > len(report["persistent_ips"]):
				count = "At least " + count
			output.print_warning(f"""{count} IP address(es) kept failing to log in for {report['persistent_min_hours']}
				hours or more within the last {report['scan_hours']} hours and were not banned once in that time (a slow
				attack below the ban thresholds). {hint} (System > Intrusion Protection in the control panel)""")
			for p in lurking[:5]:
				output.print_line(f"{p['ip']}: {p['failures']} failures in {p['hours']} hours")
	devices = report["banned_devices"]
	if devices:
		problems = True
		if rounded_values:
			output.print_warning("""Some banned IP addresses failed to log in only as existing accounts. If one of them
				is a device of your own with an old password, put its network on the allowlist (System > Intrusion
				Protection in the control panel).""")
		else:
			output.print_warning(f"""{len(devices)} banned IP address(es) failed to log in only as one or two existing
				accounts. If one of them is a device of your own with an old password (e.g. a phone in the office),
				unban it and put its network on the allowlist (System > Intrusion Protection in the control panel);
				otherwise its bans get longer each time.""")
			for d in devices[:5]:
				output.print_line(f"{d['ip']}: {', '.join(d['accounts'])}, {d['failures']} failures, banned in {', '.join(d['banned_in'])}")
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
