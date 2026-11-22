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
#    (password spraying) and of IPs that keep failing below the ban threshold,
#  * the thresholds of Mail-in-a-Box's own jails (setting "jails"), the
#    banned addresses page by page, and why each address is banned (the log
#    lines fail2ban kept, read on demand),
#  * the settings of Nextcloud's own brute-force throttle (nc_*), which
#    management/nextcloud_throttle.py applies.
#
# The settings live in $STORAGE_ROOT/settings.yaml under "fail2ban" (only the
# values that differ from DEFAULTS are stored). render_config() turns them into
# JAIL_FILE and SERVER_FILE; apply_config() writes them and reloads fail2ban
# when they changed. With adaptive banning and the slow jails off, an empty
# allowlist and no changed thresholds no file is written, which is exactly
# Mail-in-a-Box's own setup. The nc_* settings do not go into these files.
#
# Command line (as root, from the Mail-in-a-Box directory):
#   management/fail2ban_admin.py --setup        write the files, no reload (setup/start.sh;
#                                               exit code 3: the jails need a restart)
#   management/fail2ban_admin.py --apply        write the files, reload fail2ban if they changed
#   management/fail2ban_admin.py --print        show what would be written
#   management/fail2ban_admin.py --allow NET    add an address or network to the allowlist and apply
#   management/fail2ban_admin.py --report       print the spraying report

import os, os.path, re, stat, sys, time, datetime, ipaddress, subprocess, ast, json

import utils

JAIL_FILE = "/etc/fail2ban/jail.d/mailinabox_adaptive.conf"
SERVER_FILE = "/etc/fail2ban/fail2ban.d/mailinabox_adaptive.conf"

DEFAULTS = {
	"enabled": True,              # fail2ban runs; off (stopped and disabled) only for tests
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
	"jails": {},                  # changed thresholds of Mail-in-a-Box's own jails, see OVERRIDE_JAILS
	# Nextcloud's own throttle (management/nextcloud_throttle.py)
	"nc_protection": True,        # auth.bruteforce.protection.enabled
	"nc_max_attempts": 10,        # auth.bruteforce.max-attempts (Nextcloud's default)
	"nc_allowlist": False,        # put the allowlist on Nextcloud's bypass list too
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
	"nc_max_attempts": (3, 1000),
}
BOOLEANS = ("enabled", "adaptive", "slow_jails", "slow_web_jails", "nc_protection", "nc_allowlist")
DURATIONS = ("bantime_max", "memory", "slow_findtime", "slow_bantime")
MAX_ALLOWLIST = 100
MIN_PREFIX = { 4: 8, 6: 16 } # refuse networks so wide that they switch fail2ban off

MAIL_PORTS = "465,587,993,995,4190"

# The slow jails reuse Mail-in-a-Box's filters. The mail jails block only the
# mail ports, so a device with an old password does not lock its network out of
# webmail and the control panel. The web jails block HTTP and HTTPS, so they
# are a separate switch, off by default: a CalDAV/CardDAV client with an old
# password polls Nextcloud every few minutes (a phone over ActiveSync too) and would
# ban its whole network from webmail and the control panel.
SLOW_MAIL_JAILS = [
	# name, filter, log file, ports
	("miab-slow-smtp", "miab-postfix-submission", "/var/log/mail.log", MAIL_PORTS),
	("miab-slow-dovecot", "miab-dovecot-authfail", "/var/log/mail.log", MAIL_PORTS),
]
# Z-Push's error logs (ActiveSync and Autodiscover), which the miab-zpush jail
# (conf/fail2ban/jails.conf) and the failed-login report read (B126).
ZPUSH_LOGS = ("/var/log/z-push/z-push-error.log", "/var/log/z-push/autodiscover-error.log")
SLOW_WEB_JAILS = [
	("miab-slow-roundcube", "miab-roundcube", "/var/log/roundcubemail/errors.log", "http,https"),
	("miab-slow-owncloud", "miab-owncloud", "STORAGE_ROOT/owncloud/nextcloud.log", "http,https"),
	("miab-slow-management", "miab-management-daemon", "/var/log/syslog", "http,https"),
	# A log file or a tuple of them.
	("miab-slow-zpush", "miab-zpush", ZPUSH_LOGS, "http,https"),
]
SLOW_JAILS = SLOW_MAIL_JAILS + SLOW_WEB_JAILS

# Mail-in-a-Box's own jails (conf/fail2ban/jails.conf) that ban HTTP and HTTPS.
# With adaptive banning their bans, and those of the slow web jails, keep their
# fixed length: a growing ban would lock a whole office out of the control
# panel (where it could unban itself), webmail and Nextcloud for days.
# recidive still bans addresses that are banned again and again.
WEB_JAILS = ["miab-management", "miab-munin", "miab-owncloud", "miab-roundcube", "miab-zpush"]

# Mail-in-a-Box's own jails whose thresholds can be changed in the control
# panel (setting "jails": {jail: {maxretry, findtime, bantime}}, only the
# values that differ from conf/fail2ban/jails.conf are stored). They are
# written into JAIL_FILE, which fail2ban reads after mailinabox.conf. recidive
# is left out: it watches the bans of all the other jails, and the maximum ban
# time of adaptive banning is measured against its one-week ban.
OVERRIDE_JAILS = ["dovecot", "miab-management", "miab-munin", "miab-owncloud", "miab-postfix465",
	"miab-postfix587", "miab-roundcube", "miab-zpush", "postfix-sasl", "sshd"]
JAIL_OPTIONS = ("maxretry", "findtime", "bantime")
JAIL_LIMITS = { "maxretry": (3, 1000), "findtime": (10, 7 * 86400), "bantime": (60, 365 * 86400) }
# Debian's /etc/fail2ban/jail.conf [DEFAULT] (fail2ban 1.1), for the values
# that jails.conf leaves out, and its [recidive].
DEBIAN_JAIL_DEFAULTS = { "maxretry": 5, "findtime": 600, "bantime": 600 }
DEBIAN_RECIDIVE = { "findtime": 86400, "bantime": 604800 }
JAILS_CONF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "conf", "fail2ban", "jails.conf")

# What each jail watches and which ports its bans block, for the reasons of
# the bans in the control panel.
JAIL_INFO = {
	"dovecot": ("failed IMAP and POP3 logins (Dovecot)", "the mail ports"),
	"miab-management": ("failed logins to this control panel", "HTTP and HTTPS"),
	"miab-munin": ("failed logins to Munin (/admin/munin)", "HTTP and HTTPS"),
	"miab-owncloud": ("failed Nextcloud logins (also CalDAV, CardDAV and WebDAV)", "HTTP and HTTPS"),
	"miab-postfix465": ("failed SMTP AUTH logins on port 465", "port 465"),
	"miab-postfix587": ("failed SMTP AUTH logins on port 587", "port 587"),
	"miab-roundcube": ("failed webmail logins (Roundcube)", "HTTP and HTTPS"),
	"miab-zpush": ("failed ActiveSync and Autodiscover logins (Z-Push)", "HTTP and HTTPS"),
	"postfix-sasl": ("failed SMTP AUTH logins (Postfix)", "SMTP and the mail ports"),
	"sshd": ("failed SSH logins", "SSH"),
	"recidive": ("addresses that other jails banned again and again", "all ports"),
	"miab-slow-smtp": ("failed SMTP AUTH logins over hours", "the mail ports"),
	"miab-slow-dovecot": ("failed IMAP, POP3 and ManageSieve logins over hours", "the mail ports"),
	"miab-slow-roundcube": ("failed webmail logins over hours", "HTTP and HTTPS"),
	"miab-slow-owncloud": ("failed Nextcloud logins over hours", "HTTP and HTTPS"),
	"miab-slow-management": ("failed control panel logins over hours", "HTTP and HTTPS"),
	"miab-slow-zpush": ("failed ActiveSync and Autodiscover logins over hours", "HTTP and HTTPS"),
}

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

_jail_defaults = None

def jail_defaults():
	# {jail: {maxretry, findtime, bantime}} as conf/fail2ban/jails.conf (and
	# Debian's defaults where it sets nothing) configure the jails, for
	# OVERRIDE_JAILS and recidive.
	global _jail_defaults
	if _jail_defaults is None:
		import configparser
		cp = configparser.ConfigParser(interpolation=None, strict=False)
		try:
			cp.read(JAILS_CONF, encoding="utf-8")
		except configparser.Error:
			pass
		ret = {}
		for name in OVERRIDE_JAILS + ["recidive"]:
			d = dict(DEBIAN_JAIL_DEFAULTS)
			if name == "recidive":
				d.update(DEBIAN_RECIDIVE)
			if cp.has_section(name):
				for opt in JAIL_OPTIONS:
					if cp.has_option(name, opt):
						try:
							d[opt] = parse_int(cp.get(name, opt).strip(), units=True)
						except ValueError:
							pass
			ret[name] = d
		_jail_defaults = ret
	return _jail_defaults

def parse_jails(value):
	# The changed thresholds of Mail-in-a-Box's own jails: a mapping (or its
	# JSON, as the control panel sends it) of jail to {maxretry, findtime,
	# bantime}. Values equal to the default, empty ones and null are dropped,
	# so that a jail follows future defaults again.
	if value is None or value == "":
		return {}
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except ValueError:
			raise ValueError("must be a JSON object of jails") from None
	if not isinstance(value, dict):
		raise ValueError("must be a mapping of jails")
	defaults = jail_defaults()
	ret = {}
	for jail in sorted(value, key=str):
		opts = value[jail]
		if jail not in OVERRIDE_JAILS:
			raise ValueError(f"'{str(jail)[:40]}' is not a jail whose thresholds can be changed")
		if opts is None:
			continue
		if not isinstance(opts, dict):
			raise ValueError(f"{jail}: must be a mapping of maxretry, findtime and bantime")
		o = {}
		for opt in sorted(opts, key=str):
			v = opts[opt]
			if opt not in JAIL_OPTIONS:
				raise ValueError(f"{jail}: '{str(opt)[:40]}' is not maxretry, findtime or bantime")
			if v is None or (isinstance(v, str) and v.strip() == ""):
				continue
			n = parse_int(v, units=(opt != "maxretry"))
			lo, hi = JAIL_LIMITS[opt]
			if not lo <= n <= hi:
				raise ValueError(f"{jail} {opt}: must be between {lo} and {hi}")
			if n != defaults[jail][opt]:
				o[opt] = n
		if o:
			ret[jail] = o
	return ret

def jail_rules(settings):
	# {jail: {maxretry, findtime, bantime}} as the settings configure them,
	# for Mail-in-a-Box's jails and the slow jails.
	ret = {}
	for name, d in jail_defaults().items():
		r = dict(d)
		r.update(settings["jails"].get(name, {}))
		ret[name] = r
	for name, *_ in SLOW_JAILS:
		ret[name] = { "maxretry": settings["slow_maxretry"], "findtime": settings["slow_findtime"], "bantime": settings["slow_bantime"] }
	return ret

def validate_settings(values, strict=True):
	# Returns (settings, warnings): a complete settings dict. With strict=True
	# (API input) any invalid or unknown value raises ValueError. With
	# strict=False (the stored file) invalid values fall back to the default
	# and are reported as warnings.
	settings = dict(DEFAULTS)
	settings["allowlist"] = []
	settings["jails"] = {}
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
			elif key == "jails":
				value = parse_jails(value)
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
	# Values set in Nextcloud's config.php by hand, while the settings have
	# none of their own, are taken over (unless this request sets them), so
	# that a save does not overwrite them (nextcloud_throttle.hand_set_values).
	if not reset:
		try:
			import nextcloud_throttle
			old.update(nextcloud_throttle.hand_set_values(env)[0])
		except Exception:
			pass
	merged = {} if reset else { k: v for k, v in old.items() }
	merged.update(values)
	new, _ = validate_settings(merged, strict=True)
	save_settings(env, new)
	try:
		result = apply_config(env, new)
	except Exception:
		save_settings(env, old)
		raise
	# Nextcloud's throttle (its config.php and bypass list), when one of its
	# settings changed or its configuration does not match them. On a
	# failure the previous settings are restored there and in fail2ban.
	import nextcloud_throttle
	result["nextcloud"] = None
	nc_apply = nextcloud_throttle.settings_changed(old, new)
	if not nc_apply:
		try:
			nc_apply = not nextcloud_throttle.config_is_current(env, new)
		except Exception:
			# Nextcloud cannot be read now; its settings did not change, so
			# the fail2ban part stays saved (the status checks report it).
			nc_apply = False
	if nc_apply:
		try:
			result["nextcloud"] = nextcloud_throttle.apply_settings(env, new)
		except Exception as e:
			# Part of it may have been written (config.php, some bypass
			# entries, which are recorded as they are made): put back the
			# previous settings everywhere, and say whether that worked.
			save_settings(env, old)
			restored = True
			try:
				apply_config(env, old)
			except Exception:
				restored = False
			try:
				nextcloud_throttle.apply_settings(env, old)
			except Exception:
				restored = False
			if restored:
				raise RuntimeError(f"Nextcloud's brute-force settings could not be changed, the previous settings were restored: {e}") from None
			raise RuntimeError(f"Nextcloud's brute-force settings could not be changed: {e} The previous settings are saved again, but could not be applied everywhere; save them again or re-run setup.") from None
	# fail2ban itself, when it was turned on or off (the setting "enabled").
	result["service"] = None
	if old["enabled"] != new["enabled"] or not new["enabled"]:
		try:
			result["service"] = sync_service(new)
		except RuntimeError:
			save_settings(env, old)
			try:
				sync_service(old)
			except RuntimeError:
				pass
			raise
	result["settings"] = new
	result["unbanned_allowlisted"] = unban_allowlisted(new)
	return result

def sync_service(settings, run=subprocess.run):
	# fail2ban runs while "enabled" is on (the default). Turned off (for tests)
	# it is stopped and disabled, so no address is banned and the current bans
	# are lifted; turned on again it is enabled and started, and bans that
	# have not run out come back from its database. Returns "started",
	# "stopped" or None.
	want = settings.get("enabled", True)
	running = is_running()
	if want == running:
		if not want:
			run(["systemctl", "disable", "fail2ban"], capture_output=True, timeout=60)
		return None
	try:
		p = run(["systemctl", "enable" if want else "disable", "--now", "fail2ban"], capture_output=True, text=True, timeout=180)
	except (OSError, subprocess.SubprocessError) as e:
		raise RuntimeError(f"fail2ban could not be {'started' if want else 'stopped'}: {e}") from None
	if p.returncode != 0:
		raise RuntimeError(f"fail2ban could not be {'started' if want else 'stopped'}: " + ((p.stderr or p.stdout or "").strip().splitlines() or [f"exit code {p.returncode}"])[-1])
	return "started" if want else "stopped"

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
	# A list of the jail's log files (one or more).
	paths = (path,) if isinstance(path, str) else path
	return [p.replace("STORAGE_ROOT", env["STORAGE_ROOT"]) for p in paths]

def render_config(env, settings):
	# Returns ({path: content or None}, skipped). None means: the file must not
	# exist. skipped lists the slow jails left out because their log file does
	# not exist (fail2ban refuses to start with a jail without a log file).
	files = { JAIL_FILE: None, SERVER_FILE: None }
	skipped = []
	if not (settings["adaptive"] or settings["slow_jails"] or settings["slow_web_jails"] or settings["allowlist"] or settings["jails"]):
		return files, skipped

	def jail_lines(name):
		# The changed thresholds of one of Mail-in-a-Box's jails.
		o = settings["jails"].get(name, {})
		return [f"{opt} = {o[opt]}" for opt in JAIL_OPTIONS if opt in o]

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
			lines += [f"[{name}]", "bantime.increment = false"] + jail_lines(name)

	others = [name for name in OVERRIDE_JAILS if settings["jails"].get(name) and not (settings["adaptive"] and name in WEB_JAILS)]
	if others:
		lines += [
			"",
			"# Thresholds of Mail-in-a-Box's jails changed in the control panel (setting \"jails\").",
		]
		for name in others:
			lines += [f"[{name}]"] + jail_lines(name)

	slow = (SLOW_MAIL_JAILS if settings["slow_jails"] else []) + (SLOW_WEB_JAILS if settings["slow_web_jails"] else [])
	for name, filt, logpath, ports in slow:
		# fail2ban refuses a jail whose log files do not exist: leave out the
		# missing ones, and the jail when none exists.
		logpaths = [p for p in slow_jail_logpath(logpath, env) if os.path.exists(p)]
		if not logpaths:
			skipped.append(name)
			continue
		lines += [
			"",
			f"[{name}]",
			"enabled  = true",
			f"filter   = {filt}",
			f"port     = {ports}",
			"logpath  = " + "\n           ".join(logpaths),
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
	result["restart_jails"] = restart
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

def jail_info(settings):
	# {jail: {maxretry, findtime, bantime, watches, blocks}}: each jail's
	# thresholds and what it watches and blocks (the rule shown with a ban).
	rules = jail_rules(settings)
	ret = {}
	for name in set(rules) | set(JAIL_INFO):
		watches, blocks = JAIL_INFO.get(name, (None, None))
		ret[name] = dict(rules.get(name, {}), watches=watches, blocks=blocks)
	return ret

def banned_ips():
	# {jail: [addresses]} of the running jails, in one call of
	# "fail2ban-client banned" (no ban times: those need one call per jail).
	ret = {}
	for item in _literal(f2b("banned")):
		for jail, ips in item.items():
			ret[str(jail)] = [str(ip) for ip in ips]
	return ret

TOP_NETWORKS = 10
TOP_NETWORK_PREFIX = { 4: 24, 6: 64 }

def top_networks(by_ip, limit=TOP_NETWORKS):
	# The IPv4 /24 and IPv6 /64 networks with the most banned addresses (at
	# least two), with their jails: a hint at an attack from one network.
	# by_ip is {address: [jails]}.
	nets = {}
	for ip, jails in by_ip.items():
		try:
			a = ipaddress.ip_address(ip)
		except ValueError:
			continue
		net = ipaddress.ip_network(f"{a}/{TOP_NETWORK_PREFIX[a.version]}", strict=False)
		n = nets.setdefault(net, [0, set()])
		n[0] += 1
		n[1].update(jails)
	top = sorted(((net, n) for net, n in nets.items() if n[0] >= 2),
		key=lambda x: (-x[1][0], x[0].version, x[0]))[:limit]
	return [{ "network": str(net), "addresses": n[0], "jails": sorted(n[1]) } for net, n in top]

def get_status(env, client_ip=None):
	# The overview of the page: the jails and their counters, how many
	# addresses are banned, the networks with the most of them, the relay
	# hints and the settings. The bans themselves are paged by list_bans(),
	# the reasons of an address's bans read by ban_reason() (B220): with
	# thousands of bans the status carried every ban and its log lines.
	from concurrent.futures import ThreadPoolExecutor
	settings, warnings = get_settings(env)
	# The form shows values set in Nextcloud's config.php by hand while the
	# settings have none of their own (stored with the next save).
	nc_hand_set = []
	try:
		import nextcloud_throttle
		vals, nc_hand_set = nextcloud_throttle.hand_set_values(env)
		settings = dict(settings, **vals)
	except Exception:
		pass
	ret = {
		"running": False,
		"enabled": settings["enabled"],
		"error": None,
		"jails": [],
		"banned_entries": 0,
		"banned_ips": 0,
		"top_networks": [],
		"settings": settings,
		"settings_warnings": warnings,
		"nc_hand_set": nc_hand_set,
		"defaults": DEFAULTS,
		"limits": { k: { "min": lo, "max": hi } for k, (lo, hi) in LIMITS.items() },
		"max_allowlist": MAX_ALLOWLIST,
		"config_current": config_is_current(env, settings),
		"slow_jails": [ j[0] for j in SLOW_MAIL_JAILS ],
		"slow_web_jails": [ j[0] for j in SLOW_WEB_JAILS ],
		"override_jails": OVERRIDE_JAILS,
		"jail_defaults": jail_defaults(),
		"jail_limits": { k: { "min": lo, "max": hi } for k, (lo, hi) in JAIL_LIMITS.items() },
		"jail_info": jail_info(settings),
		"relays": {},
		"relays_source": None,
	}
	# The address the control panel is used from, and the jails that ban it
	# (the page offers to unban it).
	if client_ip is not None:
		ret["client"] = client_info(env, client_ip, settings)
		if ret["client"]:
			ret["client"]["banned_in"] = []
	try:
		jails = get_jails()
		banned = banned_ips()
	except F2BError as e:
		ret["error"] = str(e)
		return ret
	ret["running"] = True

	def one(jail):
		info = { "name": jail, "kind": jail_kind(jail), "banned_count": len(banned.get(jail, [])) }
		try:
			info.update(jail_status(jail))
		except F2BError as e:
			info["error"] = str(e)
		return info

	with ThreadPoolExecutor(max_workers=8) as pool:
		ret["jails"] = list(pool.map(one, jails))
	by_ip = {}
	for jail in jails:
		for ip in banned.get(jail, []):
			by_ip.setdefault(ip, []).append(jail)
	ret["banned_entries"] = sum(len(v) for v in by_ip.values())
	ret["banned_ips"] = len(by_ip)
	ret["top_networks"] = top_networks(by_ip)
	if ret.get("client"):
		ret["client"]["banned_in"] = by_ip.get(ret["client"]["ip"], [])
	# Banned addresses of the servers that relay the ActiveSync logins of
	# Outlook for iOS and Android (Microsoft's published ranges,
	# cloud_relays.py, B126): the control panel shows a hint and offers to
	# put the network on the allowlist; nothing is allowlisted on its own.
	try:
		import cloud_relays
		ret["relays"], ret["relays_source"] = cloud_relays.relay_hints(by_ip)
	except Exception as e:
		ret["relays_error"] = f"The list of Microsoft's servers (conf/fail2ban/microsoft-relays.txt) could not be read: {e}"
	return ret

# One page of the banned addresses (GET /system/fail2ban/bans, B220).

BANS_PAGE = 50
BANS_PAGE_MAX = 200
BANS_OFFSET_MAX = 10 ** 7
RE_BANS_FILTER = re.compile(r"[0-9A-Za-z:._/-]{0,64}")

def _query_int(value, name, default, lo, hi):
	if value is None or str(value).strip() == "":
		return default
	if not re.fullmatch(r"\s*\d{1,9}\s*", str(value)):
		raise ValueError(f"{name} must be a whole number.")
	n = int(value)
	if not lo <= n <= hi:
		raise ValueError(f"{name} must be from {lo} to {hi}.")
	return n

def parse_bans_filter(value):
	# ("text", lower-case substring of an address or jail), ("network",
	# ip_network) for a filter in CIDR notation, or ("", None) for none.
	value = str(value or "").strip()
	if not RE_BANS_FILTER.fullmatch(value):
		raise ValueError("The filter takes up to 64 letters, digits and the characters : . _ / - (part of an address or a jail, or a network in CIDR notation).")
	if not value:
		return "", None
	if "/" in value:
		try:
			return "network", ipaddress.ip_network(value, strict=False)
		except ValueError:
			raise ValueError("The filter is not a network in CIDR notation.") from None
	return "text", value.lower()

def _matches(kind, value, ip, bans):
	if kind == "text":
		return value in ip.lower() or any(value in b["jail"].lower() for b in bans)
	if kind == "network":
		try:
			return ipaddress.ip_address(ip) in value
		except ValueError:
			return False
	return True

def list_bans(filter="", offset=None, limit=None):
	# The banned addresses that match the filter, newest ban first (ties by
	# address), from offset on, at most limit of them, each with its bans
	# per jail and a relay hint (without the PTR name, which the status has).
	# Raises ValueError for a bad parameter.
	from concurrent.futures import ThreadPoolExecutor
	kind, value = parse_bans_filter(filter)
	offset = _query_int(offset, "offset", 0, 0, BANS_OFFSET_MAX)
	limit = _query_int(limit, "limit", BANS_PAGE, 1, BANS_PAGE_MAX)
	ret = { "running": False, "error": None, "total": 0, "matched": 0, "offset": offset, "limit": limit,
		"filter": str(filter or "").strip(), "addresses": [] }
	try:
		banned = banned_ips()
	except F2BError as e:
		ret["error"] = str(e)
		return ret
	ret["running"] = True

	def one(jail):
		try:
			return jail, jail_bans(jail), None
		except F2BError as e:
			return jail, [], str(e)

	by_ip = {}
	errors = {}
	with ThreadPoolExecutor(max_workers=8) as pool:
		for jail, bans, error in pool.map(one, [j for j, ips in banned.items() if ips]):
			if error:
				errors[jail] = error
			for b in bans:
				by_ip.setdefault(b["ip"], []).append({ "jail": jail, "start": b["start"], "bantime": b["bantime"],
					"end": b["end"], "remaining": b["remaining"] })
	if errors:
		ret["jail_errors"] = errors
	ret["total"] = len(by_ip)
	matched = [(max(b["start"] for b in bans), ip) for ip, bans in by_ip.items() if _matches(kind, value, ip, bans)]
	matched.sort(key=lambda x: (-x[0], x[1]))
	ret["matched"] = len(matched)
	page = [ip for _start, ip in matched[offset:offset + limit]]
	relays = {}
	if page:
		try:
			import cloud_relays
			relays, _source = cloud_relays.relay_hints(page, names=False)
		except Exception as e:
			ret["relays_error"] = f"The list of Microsoft's servers (conf/fail2ban/microsoft-relays.txt) could not be read: {e}"
	for ip in page:
		bans = sorted(by_ip[ip], key=lambda b: (-b["start"], b["jail"]))
		permanent = any(b["end"] is None for b in bans)
		end = None if permanent else max(b["end"] for b in bans)
		ret["addresses"].append({
			"ip": ip,
			"start": bans[0]["start"],  # of its newest ban
			"end": end,                 # when its last ban ends, None if one is permanent
			"remaining": None if permanent else max(b["remaining"] for b in bans),
			"bans": bans,
			"relay": relays.get(ip),
		})
	return ret

def ban_reason(env, ip):
	# Why an address is banned, per jail that bans it now: the failures,
	# accounts and log lines that fail2ban kept for its newest ban there
	# (ban_reasons), and the jail's rule. Loaded on demand by the page.
	ip = normalize_ip(ip)
	jails = sorted(banned_in([ip]).get(ip, []))
	settings, _ = get_settings(env)
	info = jail_info(settings)
	ret = { "ip": ip, "jails": [] }
	try:
		reasons = ban_reasons(env, [(jail, ip, None) for jail in jails])
	except Exception as e:
		reasons = {}
		ret["error"] = f"The reasons of the bans could not be read from fail2ban's database: {e}"
	for jail in jails:
		ret["jails"].append({ "jail": jail, "reason": reasons.get((jail, ip)), "rule": info.get(jail) })
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
# Z-Push's error logs and their last rotation (weekly, delaycompress) (B126).
ZPUSH_SCAN_LOGS = tuple(p for f in ZPUSH_LOGS for p in (f + ".1", f))
SCAN_LOGS = MAIL_LOGS + ZPUSH_SCAN_LOGS
SCAN_HOURS = 48
ACCOUNT_HOURS = 24
PERSISTENT_MIN_FAILURES = 10
PERSISTENT_MIN_HOURS = 12
REPORT_LIMIT = 50

MONTHS = { m: i + 1 for i, m in enumerate(("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")) }
RE_TS_ISO = re.compile(rb"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:?\d\d)?)\s")
RE_TS_BSD = re.compile(rb"([A-Z][a-z]{2}) +(\d{1,2}) (\d\d):(\d\d):(\d\d)\s")
RE_TS_ZPUSH = re.compile(rb"(\d\d)/(\d\d)/(\d{4}) (\d\d):(\d\d):(\d\d) ") # local time, day first
# postfix (465 and 587 both log as postfix/submission/smtpd):
#   warning: unknown[192.0.2.1]: SASL LOGIN authentication failed: (reason), sasl_username=a@b
# The user is split off the rest of the line in Python (smtp_user): a regex
# with a lazy part before an optional group at the end of the line took a
# quarter of a second for a line with a long run of spaces.
RE_SMTP = re.compile(rb"postfix/[\w/-]*smtpd\[\d+\]: warning: [^\[\s]*\[([0-9A-Fa-f:.]+)\]: SASL \S+ authentication failed: (.*)$")
SASL_USER = b", sasl_username="

def smtp_user(m):
	# (user, start, end) of a match of RE_SMTP: the text after Postfix's
	# ", sasl_username=" behind the reason, to the end of the line (a
	# client's name can have spaces); (b"", None, None) without it.
	tail = m.group(2)
	i = tail.find(SASL_USER)
	if i < 0:
		return b"", None, None
	start = m.start(2) + i + len(SASL_USER)
	value = tail[i + len(SASL_USER):]
	lead = len(value) - len(value.lstrip())
	return value.strip(), start + lead, start + len(value.rstrip())
# Dovecot 2.4 (and 2.3 "Aborted login"/"Disconnected"), through syslog without "Info: " (B85),
# in older files written by Dovecot itself with it:
#   dovecot: imap-login: Login aborted: ... (auth failed, 3 attempts in 9 secs) (auth_failed): user=<a@b>, method=PLAIN, rip=192.0.2.1, lip=...
# The user name is logged unescaped, so the greedy user=<.*> takes the last rip= (see filter.d/dovecotimap.conf).
RE_DOVECOT = re.compile(rb"(imap|pop3|managesieve|submission)-login: (?:Info: )?.*?\((?:auth failed|authorization failed|user disabled)(?:, (\d+) attempts)?[^)]*\)(?: \(\w+\))?: user=<(.*)>, (?:method=\S+, )?rip=([0-9A-Fa-f:.]+), lip=")
# Z-Push (LOGAUTHFAIL, B126), anchored like
# conf/fail2ban/filter.d/miab-zpush.conf: the user names and the e-mail
# address come from the client, the address is the last thing on the line
# (setup/zpush.sh moves it there in the ActiveSync message), and the message
# must follow the user names in brackets that belong to it (setup/zpush.sh
# escapes "]" and "\" in them): the user of "[<user>]" (apart from case), or
# the first user of "[<user>#<user of the request>]"; Autodiscover's are
# always "[#unknown]".
#   26/10/2026 13:00:00 [12345] [WARN] [bob@example.com] Failed to authenticate user 'bob@example.com' from IP 192.0.2.1.
#   26/10/2026 13:00:00 [12345] [WARN] [#unknown] Unable to complete autodiscover because login failed for user with email 'bob@example.com' from IP 192.0.2.1.
RE_ZPUSH = re.compile(rb"^\d\d/\d\d/\d{4} \d\d:\d\d:\d\d \[\s*\d+\] \[ ?WARN\] \[(?:(?P<same>[^\]\\#]*)|(?P<auth>[^\]\\#]+)#(?:[^\]\\]|\\.)*)\] Failed to authenticate user '(?P<user>(?i:(?P=same))|(?P=auth))' from IP (?P<ip>[0-9A-Fa-f:.]+)\.\r?\n?$")
RE_AUTODISCOVER = re.compile(rb"^\d\d/\d\d/\d{4} \d\d:\d\d:\d\d \[\s*\d+\] \[ ?WARN\] \[#unknown\] Unable to complete autodiscover because login failed for user with email '(?P<user>.*)' from IP (?P<ip>[0-9A-Fa-f:.]+)\.\r?\n?$")
# Nextcloud's log, one JSON object per line (setup/nextcloud.sh sets
# logdateformat 'Y-m-d H:i:s' in the box's time zone), one line per failed
# login; the address is remoteAddr, as the miab-owncloud filter takes it:
#   {"reqId":"...","level":2,"time":"2026-10-26 13:00:00","remoteAddr":"192.0.2.1",...,"message":"Login failed: 'bob@example.com' (Remote IP: '192.0.2.1')",...}
# (user_external's "IMAP Login failed via curl" lines, several per failed
# login, are not counted.)
RE_TS_NC = re.compile(rb'"time":"(\d{4}-\d\d-\d\d)[ T](\d\d:\d\d:\d\d)(?:\.\d+)?(Z|[+-]\d\d:?\d\d)?"')
RE_NC_LOGIN = re.compile(r"^Login failed: '(.*)' \(Remote IP: '([0-9A-Fa-f:.]+)'\)$", re.S)
# The user names in other log lines that fail2ban keeps for a ban (the
# reasons of the bans): Roundcube's errors.log, nginx's access log (Munin's
# Basic login) and sshd (the name of an account that does not exist).
RE_ROUNDCUBE = re.compile(rb"IMAP Error: Login failed for (.*?) against \S+ from ")
# The names are taken up to the text that follows them, as the filters do:
# nginx logs $remote_user and sshd the user name without escaping spaces.
RE_NGINX_USER = re.compile(rb"^\S+ - (.*?) \[\d\d/[A-Z][a-z]{2}/\d{4}:\d\d:\d\d:\d\d [+-]\d{4}\] ")
RE_SSH_INVALID = re.compile(rb"([Ii]nvalid user )(.*)( from [0-9A-Fa-f:.]+ port \d+)")
# A line of Nextcloud's log that is not valid JSON: the login message in it.
RE_NC_LOGIN_RAW = re.compile(rb'"message":"Login failed: \'(.*?)\' \(Remote IP: \'([0-9A-Fa-f:.]+)\'\)"')

def nextcloud_logs(env):
	# Nextcloud's log and the file of its own rotation (log_rotate_size);
	# logrotate compresses its rotated file at once (setup/nextcloud.sh).
	base = os.path.join(env["STORAGE_ROOT"], "owncloud", "nextcloud.log")
	return (base + ".1", base)

def _line_time(line, now):
	if line[:1] == b"{":
		# Nextcloud (local time unless its log date format names a zone).
		m = RE_TS_NC.search(line, 0, 400)
		if not m:
			return None
		tz = m.group(3).decode() if m.group(3) else ""
		try:
			dt = datetime.datetime.fromisoformat(m.group(1).decode() + "T" + m.group(2).decode() + ("+00:00" if tz == "Z" else tz))
		except ValueError:
			return None
		return dt.timestamp() if dt.tzinfo else time.mktime(dt.timetuple())
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
	m = RE_TS_ZPUSH.match(line)
	if m:
		d, mo, y, hh, mi, ss = (int(x) for x in m.groups())
		try:
			return time.mktime((y, mo, d, hh, mi, ss, 0, 0, -1))
		except (OverflowError, ValueError):
			return None
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

def _open_log(fn):
	# Opens a log file for reading, or returns None. Z-Push's logs are in a
	# directory of www-data: no symbolic link is followed there, and only a
	# regular file is read (not a FIFO, which would block).
	try:
		fd = os.open(fn, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
	except OSError:
		return None
	try:
		if not stat.S_ISREG(os.fstat(fd).st_mode):
			os.close(fd)
			return None
		return os.fdopen(fd, "rb")
	except OSError:
		os.close(fd)
		return None

def scan_failed_logins(hours=SCAN_HOURS, files=SCAN_LOGS, now=None):
	# Returns a list of (time, protocol, ip, user, count) for failed logins of
	# the last hours. Passwords are not in these log lines; the user is what the
	# client sent.
	now = now or time.time()
	cutoff = now - hours * 3600
	events = []
	for fn in files:
		f = _open_log(fn)
		if f is None:
			continue
		with f:
			_seek(f, os.fstat(f.fileno()).st_size, cutoff, now)
			for line in f:
				if RE_TS_ZPUSH.match(line):
					# A line of Z-Push (no line of mail.log starts so).
					if b"] Failed to authenticate user '" in line:
						m = RE_ZPUSH.match(line)
						if not m: continue
						user, ip, proto, count = m.group("user"), m.group("ip"), "activesync", 1
						if user == b"unknown":
							continue # names no user (setup/zpush.sh logs only requests with a password; miab-zpush skips it too)
					elif b"Unable to complete autodiscover because login failed" in line:
						m = RE_AUTODISCOVER.match(line)
						if not m: continue
						user, ip, proto, count = m.group("user"), m.group("ip"), "autodiscover", 1
					else:
						continue
				elif line[:1] == b"{":
					# A line of Nextcloud's log (no line of the other logs starts so).
					if b"Login failed: '" not in line: continue
					try:
						j = json.loads(line)
					except ValueError:
						continue
					if not isinstance(j, dict): continue
					m = RE_NC_LOGIN.match(str(j.get("message", "")))
					if not m: continue
					addr = str(j.get("remoteAddr") or m.group(2))
					try:
						ipaddress.ip_address(addr)
					except ValueError:
						continue
					user, ip, proto, count = m.group(1).encode("utf-8", "replace"), addr.encode(), "nextcloud", 1
				elif b"authentication failed" in line:
					m = RE_SMTP.search(line)
					if not m: continue
					ip, user, proto, count = m.group(1), smtp_user(m)[0], "smtp", 1
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

def _known_accounts(env):
	# The mail users and aliases of the box, lower case.
	try:
		import mailconfig
		return { u.lower() for u in mailconfig.get_mail_users(env) } | { a[0].lower() for a in mailconfig.get_mail_aliases(env) }
	except Exception:
		return set()

# REASONS OF BANS

REASON_LINES = 10        # fail2ban keeps up to dbmaxmatches (10) lines per ban
REASON_LINE_CHARS = 300
UNKNOWN_NAME = b"[unknown name]"

# Where a user name is in a log line: (regex, group, method). The first ones
# are those of the failed-login report and the filters; the others catch the
# lines of the filters that the report's regexes do not match (Dovecot's
# "tried to use ..." and "no auth attempts" lines, a user=<...> anywhere).
_USER_FIELDS = [
	(RE_DOVECOT, 3, "search"),
	(RE_ZPUSH, "user", "match"),
	(RE_AUTODISCOVER, "user", "match"),
	(RE_ROUNDCUBE, 1, "search"),
	(RE_NGINX_USER, 1, "match"),
	(RE_SSH_INVALID, 2, "search"),
]

def _smtp_span(line):
	m = RE_SMTP.search(line)
	if not m:
		return []
	name, start, end = smtp_user(m)
	return [(start, end, name)] if name else []

def _sasl_span(line):
	# sasl_username= in another line of Postfix: to the end of the line.
	i = line.find(b"sasl_username=")
	while i > 0 and (line[i - 1:i].isalnum() or line[i - 1:i] == b"_"):
		i = line.find(b"sasl_username=", i + 1)
	if i < 0:
		return []
	start = i + len(b"sasl_username=")
	value = line[start:]
	lead = len(value) - len(value.lstrip())
	name = value.strip()
	return [(start + lead, start + len(value.rstrip()), name)] if name else []

RE_USER_FIELD = re.compile(rb"user=<(.*)>, (?:method=\S+, )?rip=")
RE_USER_FIELD_SHORT = re.compile(rb"user=<([^>]*)>")

def _user_field_span(line):
	# user=<...> in a line of Dovecot that RE_DOVECOT does not match (the
	# filter's "tried to use ...", "no auth attempts"), at its first place
	# only: tried at every "user=<" of a line, the regexes take time that
	# grows with the square of their number.
	i = line.find(b"user=<")
	while i > 0 and (line[i - 1:i].isalnum() or line[i - 1:i] == b"_"):
		i = line.find(b"user=<", i + 1)
	if i < 0:
		return []
	m = RE_USER_FIELD.match(line, i) or RE_USER_FIELD_SHORT.match(line, i)
	if not m or not m.group(1).strip():
		return []
	return [(m.start(1), m.end(1), m.group(1))]

_USER_SPAN_FUNCS = [_smtp_span, _sasl_span, _user_field_span]
# Z-Push's user names in brackets ("[<user>]" or "[<user>#<user of the
# request>]", escaped by setup/zpush.sh), which repeat what the client sent.
RE_ZPUSH_NAMES = re.compile(rb"^\d\d/\d\d/\d{4} \d\d:\d\d:\d\d \[\s*\d+\] \[ ?WARN\] \[((?:[^\]\\]|\\.)*)\]")
_NAME_CHARS = rb"A-Za-z0-9._@+\-"

MIN_REPEAT_NAME = 4 # shorter names are masked only where the line names them

def _unescape(name):
	# Z-Push escapes "]", "#" and "\" in the brackets.
	return re.sub(rb"\\(.)", rb"\1", name)

def _name_spans(line):
	# (start, end, name) of each place where the line names a user.
	spans = []
	for fn in _USER_SPAN_FUNCS:
		spans += fn(line)
	for rx, group, how in _USER_FIELDS:
		m = getattr(rx, how)(line)
		if m and m.group(group) not in (None, b"", b"-") and m.group(group).strip():
			spans.append((m.start(group), m.end(group), m.group(group)))
	m = RE_ZPUSH_NAMES.match(line)
	if m and m.group(1) != b"#unknown": # "[#unknown]": Autodiscover's placeholder
		pos = m.start(1)
		for part in re.split(rb"(?<!\\)#", m.group(1)):
			if part.strip():
				spans.append((pos, pos + len(part), part))
			pos += len(part) + 1
	return spans

def _mask_name(text, name, repl=UNKNOWN_NAME):
	# The other occurrences of a name in the line, apart from case: where it
	# stands on its own (between other characters than those of an address),
	# else wherever it is.
	pat = re.compile(rb"(?<![" + _NAME_CHARS + rb"])" + re.escape(name) + rb"(?![" + _NAME_CHARS + rb"])", re.I)
	new = pat.sub(lambda m: repl, text)
	if new == text:
		new = re.compile(re.escape(name), re.I).sub(lambda m: repl, text)
	return new

def _nc_reason_line(line, known):
	# A line of Nextcloud's log: the fields that matter instead of the whole
	# JSON object. The URL only for an account of the box: a WebDAV path names
	# the login name (.../principals/users/<name>/), also in other messages.
	try:
		j = json.loads(line)
	except ValueError:
		j = None
	if not isinstance(j, dict):
		# Not valid JSON: only the time and the login message, else nothing.
		ts = RE_TS_NC.search(line, 0, 400)
		when = (ts.group(1) + b" " + ts.group(2)).decode() + " – " if ts else ""
		m = RE_NC_LOGIN_RAW.search(line)
		if not m:
			return when + "[a line of Nextcloud's log that could not be read]", None, True
		try:
			user = json.loads(b'"' + m.group(1) + b'"').strip().lower()
		except ValueError:
			user = None
		if user in known:
			return (when + "Login failed: '%s' (Remote IP: '%s')" % (user, m.group(2).decode()))[:REASON_LINE_CHARS], user, False
		return when + "Login failed: %s (Remote IP: '%s')" % (UNKNOWN_NAME.decode(), m.group(2).decode()), None, True
	msg = str(j.get("message", ""))
	m = RE_NC_LOGIN.match(msg)
	user = m.group(1).strip().lower() if m else None
	own = bool(m) and user in known
	parts = [str(j.get(k)) for k in ("time", "remoteAddr", "method") if j.get(k)]
	if own and j.get("url"):
		parts.append(str(j["url"]))
	if m and not own:
		msg = "Login failed: %s (Remote IP: '%s')" % (UNKNOWN_NAME.decode(), m.group(2))
	text = " ".join(parts) + " – " + msg
	if j.get("userAgent"):
		ua = str(j["userAgent"])
		if m and not own and len(m.group(1).strip()) >= MIN_REPEAT_NAME:
			ua = _mask_name(ua.encode("utf-8", "replace"), m.group(1).encode("utf-8", "replace")).decode("utf-8", "replace")
		text += " – " + ua
	return text[:REASON_LINE_CHARS], (user if own else None), bool(m) and not own

def _reason_line(line, known):
	# One log line of a ban, for the control panel: (text, account, masked).
	# account is the first account of this box the line names. Every user
	# name that is not an account of this box is replaced, as the
	# failed-login report leaves such names out: it is whatever the client
	# sent, a password typed into the wrong field too. It is replaced where
	# the line names a user (also in Z-Push's brackets), and a name of 4 or
	# more characters also wherever else the line repeats it (a shorter one
	# would hit other words, "1" the "1 attempts" of Dovecot).
	if line[:1] == b"{":
		return _nc_reason_line(line, known)
	account, unknown = None, []
	for start, end, name in _name_spans(line):
		user = name.decode("utf-8", "replace").strip().lower()
		plain = _unescape(name).decode("utf-8", "replace").strip().lower()
		if user in known or plain in known:
			account = account or (user if user in known else plain)
		else:
			unknown.append((start, end, name))
	if not unknown:
		return line.decode("utf-8", "replace")[:REASON_LINE_CHARS], account, False
	# The places, merged where they overlap (sasl_username=<name with a
	# space> is matched by two regexes).
	mark = bytearray(len(line))
	for start, end, _ in unknown:
		mark[start:end] = b"\x01" * (end - start)
	# A NUL stands for the replacement until the end (a log line has none), so
	# that a name like "name" does not hit the replacement text itself.
	out, i = bytearray(), 0
	while i < len(line):
		if mark[i]:
			while i < len(line) and mark[i]:
				i += 1
			out += b"\0"
		else:
			out.append(line[i])
			i += 1
	text = bytes(out)
	for _, _, name in sorted(unknown, key=lambda u: -len(u[2])):
		for n in (name, _unescape(name)):
			if len(n.strip()) >= MIN_REPEAT_NAME:
				text = _mask_name(text, n.strip(), b"\0")
	text = text.replace(b"\0", UNKNOWN_NAME)
	return text.decode("utf-8", "replace")[:REASON_LINE_CHARS], account, True

def _reason(data, known):
	if isinstance(data, bytes):
		data = data.decode("utf-8", "replace")
	try:
		d = json.loads(data) if data else {}
	except (ValueError, TypeError):
		d = {}
	if not isinstance(d, dict):
		d = {}
	raw = d.get("matches") or []
	if not isinstance(raw, list):
		raw = []
	lines, accounts, masked = [], [], 0
	for m in raw[-REASON_LINES:]:
		if isinstance(m, (list, tuple)):
			m = "".join(str(x) for x in m)
		text, account, was_masked = _reason_line(str(m).rstrip("\r\n").encode("utf-8", "replace"), known)
		lines.append(text)
		if account and account not in accounts:
			accounts.append(account)
		if was_masked:
			masked += 1
	failures = d.get("failures")
	return {
		"failures": failures if isinstance(failures, int) and not isinstance(failures, bool) else None,
		"accounts": accounts,       # accounts of this box named in the lines
		"unknown_names": masked,    # lines with a name that is no account here (replaced)
		"lines": lines,             # the newest of the lines fail2ban kept, at most REASON_LINES
		"manual": not raw,          # no lines: banned by hand (fail2ban-client ... banip)
	}

def ban_reasons(env, bans):
	# {(jail, ip): reason} for the current bans, a list of (jail, ip, start of
	# the ban or None), from the newest row of each in fail2ban's bans table
	# (opened read-only, like bans_since): the number of failures and the log
	# lines that fail2ban kept for the ban. Without a start the newest row of
	# the address in the jail, which is that of its current ban.
	import sqlite3, urllib.parse
	if not bans:
		return {}
	path = db_path()
	if not path or not os.path.exists(path):
		return {}
	rows = {}
	con = sqlite3.connect("file:" + urllib.parse.quote(path) + "?mode=ro", uri=True, timeout=5)
	try:
		# One row per ban, through the index on (jail, ip): the newest that
		# began by the start of the current ban.
		for jail, ip, start in bans:
			if start is None:
				r = con.execute("SELECT data FROM bans WHERE jail = ? AND ip = ? ORDER BY timeofban DESC LIMIT 1",
					(jail, ip)).fetchone()
			else:
				r = con.execute("SELECT data FROM bans WHERE jail = ? AND ip = ? AND timeofban <= ? ORDER BY timeofban DESC LIMIT 1",
					(jail, ip, int(start) + 5)).fetchone()
			if r is not None:
				rows[(jail, ip)] = r[0]
	finally:
		con.close()
	known = _known_accounts(env)
	return { key: _reason(data, known) for key, data in rows.items() }

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
		events = scan_failed_logins(now=now, files=SCAN_LOGS + nextcloud_logs(env))
	own = _own_ips(env)
	allow = [ipaddress.ip_network(n, strict=False) for n in settings["allowlist"]]

	known = _known_accounts(env)

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
		output.print_warning("""The fail2ban configuration does not match the intrusion detection and prevention settings.
			Save the settings again in the control panel (System > Intrusion Detection and Prevention) or re-run setup.""")
	try:
		import nextcloud_throttle
		nc_current = nextcloud_throttle.config_is_current(env, settings)
	except Exception:
		nc_current = True # Nextcloud not readable now; its own checks report that
	if not nc_current:
		output.print_warning("""Nextcloud's brute-force settings do not match the intrusion detection and prevention settings.
			Save the settings again in the control panel (System > Intrusion Detection and Prevention) or re-run setup.""")
	# With Nextcloud's protection off, the failures left in its database are
	# stale but still delay logins for up to 12 hours (a login that was
	# waiting in the throttle when it was turned off can add one after the
	# deletion): the daily run of the status checks deletes them.
	try:
		import nextcloud_throttle
		n = nextcloud_throttle.delete_stale(env)
		if n:
			output.print_ok(f"Deleted {n} stale failed Nextcloud logins (Nextcloud's brute-force protection is off).")
	except Exception:
		pass

	try:
		report = failed_login_report(env, settings)
	except Exception as e:
		output.print_warning("Could not read the mail, ActiveSync and Nextcloud logs for failed logins: " + str(e))
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
				hours or more without ever being banned. See System > Intrusion Detection and Prevention in the control panel.""")
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
				attack below the ban thresholds). {hint} (System > Intrusion Detection and Prevention in the control panel)""")
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
				unban it and put its network on the allowlist (System > Intrusion Detection and Prevention in the control panel);
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
		output.print_ok(f"No signs of password spraying or slow login attacks in the mail, ActiveSync and Nextcloud logs of the last {report['scan_hours']} hours.")

# COMMAND LINE

if __name__ == "__main__":
	import json
	env = utils.load_environment()
	args = sys.argv[1:]
	if args == ["--setup"]:
		# Called by setup/start.sh right before fail2ban is reloaded. Never
		# stops setup: on a problem Mail-in-a-Box's own jails stay in effect.
		# Exit code 3 when the bantime.* options changed: setup then has
		# fail2ban restart its jails ("reload --restart", see apply_config).
		# Exit code 4 when fail2ban is turned off (the setting "enabled", for
		# tests): setup then stops and disables it instead.
		settings, warnings = get_settings(env)
		for w in warnings:
			print(w)
		try:
			result = apply_config(env, settings, reload=False)
		except Exception as e:
			print("Adaptive fail2ban was not configured:", e)
			for path in (JAIL_FILE, SERVER_FILE):
				_write(path, None)
			# The removed files may have had bantime.* options.
			sys.exit(3 if settings["enabled"] else 4)
		if not settings["enabled"]:
			sys.exit(4)
		for j in result["skipped_jails"]:
			print(f"fail2ban: {j} left out, its log file does not exist yet.")
		if result.get("restart_jails"):
			sys.exit(3)
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
