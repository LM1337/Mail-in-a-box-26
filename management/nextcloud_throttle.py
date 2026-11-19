#!/usr/local/lib/mailinabox/env/bin/python3
#
# Nextcloud's brute-force throttle (fork), for System > Intrusion Protection.
#
# Nextcloud counts each failed login in its table bruteforce_attempts, under
# the address of the client: an IPv4 address (stored as <address>/32) or the
# /64 network of an IPv6 address. Before it checks a login it counts the
# failures of that address (lib/private/Security/Bruteforce/Throttler.php):
#
#  * within the last 12 hours: the login is delayed by 0.1 s * 2^failures, up
#    to 25 s; above auth.bruteforce.max-attempts (10 by default) always 25 s,
#  * above max-attempts within the last 12 hours and also within the last 30
#    minutes: the login is refused at once with HTTP 429 (TooManyRequests),
#    also for an account with the right password behind the same address.
#
# A successful login removes only the failures of that account from that
# address, so a device with an old password keeps a whole network throttled
# (and the devices with the right password behind it). The failures are kept
# per action ("login" for the logins of the web interface and of CalDAV,
# CardDAV and WebDAV, others for share links and the like), and each action is
# counted on its own. Addresses on the bypass list (the "whitelist_N" keys of
# the app config "bruteForce") are never counted or throttled.
#
# This module shows the throttled addresses (read from the database, read-only
# and as www-data, which owns it), resets an address ("occ
# security:bruteforce:reset"), and applies the settings nc_protection,
# nc_max_attempts and nc_allowlist that fail2ban_admin.py stores with the
# other intrusion protection settings: the first two are system settings in
# config.php (tools/nextcloud-bruteforce-config.php), the last puts the
# allowlist on the bypass list. The entries it adds there are recorded in
# settings.yaml ("nextcloud_bypass"), so that only these are removed again:
# 127.0.0.1/32 (setup/nextcloud.sh, B121) and entries of an administrator
# (Administration > Security) are never touched.
#
# Command line (as root, from the Mail-in-a-Box directory):
#   management/nextcloud_throttle.py --setup     apply the settings (setup/start.sh; never fails)
#   management/nextcloud_throttle.py --status    print the throttled addresses
#   management/nextcloud_throttle.py --reset IP  reset the failures of an address

import os, os.path, re, sys, json, math, time, ipaddress, subprocess

import utils

NC_ROOT = "/usr/local/lib/owncloud"
RUNUSER = "/usr/sbin/runuser"
HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_TOOL = os.path.join(HERE, "..", "tools", "nextcloud-bruteforce-config.php")

DEFAULT_MAX_ATTEMPTS = 10   # Throttler::MAX_ATTEMPTS
MAX_DELAY_MS = 25000        # Throttler::MAX_DELAY_MS
WINDOW_HOURS = 12           # the delay counts the failures of the last 12 hours
BLOCK_MINUTES = 30          # the 429 counts those of the last 30 minutes too
MAX_ENTRIES = 500
MAX_ACCOUNTS = 20
SYSTEM_BYPASS = "127.0.0.1/32" # setup/nextcloud.sh (B121)
STATE_KEY = "nextcloud_bypass" # settings.yaml: {whitelist_N: network} added by this module
NC_KEYS = ("nc_protection", "nc_max_attempts", "nc_allowlist")

class NCError(Exception):
	pass

def php_binary():
	# The PHP version of setup/functions.sh (PHP_VER), which runs Nextcloud.
	try:
		with open(os.path.join(HERE, "..", "setup", "functions.sh"), encoding="utf-8") as f:
			for line in f:
				m = re.match(r"PHP_VER=([0-9]+\.[0-9]+)\s*$", line)
				if m:
					return "/usr/bin/php" + m.group(1)
	except OSError:
		pass
	return "/usr/bin/php8.5"

def _run_www(argv, stdin=None, extra_env=None, timeout=120):
	# Runs a command as www-data, with a clean environment, in /.
	env = { "PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C.UTF-8" }
	env.update(extra_env or {})
	try:
		return subprocess.run([RUNUSER, "-u", "www-data", "--", *argv], input=stdin, capture_output=True, text=True,
			timeout=timeout, cwd="/", env=env, stdin=None if stdin is not None else subprocess.DEVNULL)
	except (OSError, subprocess.TimeoutExpired) as e:
		raise NCError(f"{os.path.basename(argv[0])} could not be run as www-data: {e}") from None

def _fail(what, p):
	msg = (p.stderr.strip() or p.stdout.strip() or f"exit code {p.returncode}").splitlines()
	return NCError(f"{what} failed: {msg[-1][:300]}")

def occ(*args, timeout=120):
	p = _run_www([php_binary(), NC_ROOT + "/occ", "--no-interaction", *args], timeout=timeout)
	if p.returncode != 0:
		raise _fail("occ " + args[0], p)
	return p.stdout

def config_php(env):
	return os.path.join(env["STORAGE_ROOT"], "owncloud", "config.php")

def nc_config(env, set_values=None):
	# Nextcloud's brute-force system settings (and what the overview needs) as
	# tools/nextcloud-bruteforce-config.php reads them; with set_values (key:
	# value, None removes the key) it changes them first.
	with open(CONFIG_TOOL, encoding="utf-8") as f:
		code = f.read()
	extra = { "NC_CONFIG": config_php(env) }
	if set_values is not None:
		extra["NC_SET"] = json.dumps(set_values)
	p = _run_www([php_binary()], stdin=code, extra_env=extra, timeout=60)
	if p.returncode != 0:
		raise _fail("Reading Nextcloud's config.php" if set_values is None else "Writing Nextcloud's config.php", p)
	try:
		return json.loads(p.stdout.strip().splitlines()[-1])
	except (ValueError, IndexError):
		raise NCError("Unexpected output when reading Nextcloud's config.php.") from None

# Read as www-data (the owner of the database, its directory and its -wal
# and -shm files, which a connection of root could create with the wrong
# owner), read-only. Aggregated in SQL: an attack can leave many thousand rows.
DB_READER = r"""
import json, sqlite3, sys, urllib.parse
path, prefix, since, recent = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
con = sqlite3.connect("file:" + urllib.parse.quote(path) + "?mode=ro", uri=True, timeout=10)
try:
    t = prefix + "bruteforce_attempts"
    rows = con.execute("SELECT subnet, action, ip, metadata, COUNT(*), SUM(occurred >= ?), MIN(occurred), MAX(occurred) FROM " + t
        + " WHERE occurred >= ? GROUP BY subnet, action, ip, metadata ORDER BY MAX(occurred) DESC LIMIT 50000", (recent, since)).fetchall()
    bypass = con.execute("SELECT configkey, configvalue FROM " + prefix + "appconfig WHERE appid = 'bruteForce' AND configkey LIKE 'whitelist\\_%' ESCAPE '\\'").fetchall()
finally:
    con.close()
json.dump({"rows": rows, "bypass": bypass}, sys.stdout)
"""

def _read_db(env, cfg, since, recent):
	if (cfg.get("dbtype") or "sqlite3") not in ("sqlite", "sqlite3"):
		raise NCError("Nextcloud does not use SQLite here, so the overview cannot read its throttle.")
	prefix = cfg.get("dbtableprefix") or "oc_"
	if not re.fullmatch(r"[A-Za-z0-9_]{0,32}", prefix):
		raise NCError("Nextcloud's table prefix is not a plain name.")
	datadir = cfg.get("datadirectory") or os.path.join(env["STORAGE_ROOT"], "owncloud")
	path = os.path.join(datadir, "owncloud.db")
	p = _run_www(["/usr/bin/python3", "-I", "-c", DB_READER, path, prefix, str(int(since)), str(int(recent))], timeout=60)
	if p.returncode != 0:
		raise _fail("Reading Nextcloud's database", p)
	try:
		return json.loads(p.stdout)
	except ValueError:
		raise NCError("Unexpected output when reading Nextcloud's database.") from None

def delay_ms(attempts, max_attempts):
	# Throttler::calculateDelay.
	if attempts <= 0:
		return 0
	if attempts > max_attempts:
		return MAX_DELAY_MS
	delay = 0.1 * 2 ** attempts
	if delay > MAX_DELAY_MS / 1000:
		return MAX_DELAY_MS
	return int(math.ceil(delay * 1000))

def _network(value):
	# A bypass entry as Nextcloud reads it (an address or a range in CIDR
	# notation), or None.
	try:
		return ipaddress.ip_network(str(value).strip(), strict=False)
	except ValueError:
		return None

def _cidr(net):
	# The form this module writes to the bypass list: always with a prefix.
	n = ipaddress.ip_network(net, strict=False)
	return f"{n.network_address}/{n.prefixlen}"

def _user(metadata):
	try:
		m = json.loads(metadata) if metadata else {}
	except ValueError:
		return None
	u = m.get("user") if isinstance(m, dict) else None
	return str(u).strip().lower()[:320] if u else None

def _effective(cfg):
	enabled = cfg.get("enabled")
	max_attempts = cfg.get("max_attempts")
	return (enabled is not False), (max_attempts if isinstance(max_attempts, int) and max_attempts > 0 else DEFAULT_MAX_ATTEMPTS)

def _state(env):
	st = utils.load_settings(env).get(STATE_KEY)
	if not isinstance(st, dict):
		return {}
	return { str(k): str(v) for k, v in st.items() if re.fullmatch(r"whitelist_\d+", str(k)) }

def _save_state(env, state):
	config = utils.load_settings(env)
	if state:
		config[STATE_KEY] = dict(sorted(state.items(), key=lambda kv: int(kv[0][10:])))
	else:
		config.pop(STATE_KEY, None)
	utils.write_settings(config, env)

def _bypass_entries(bypass, state):
	# The bypass list for the overview: where each entry comes from.
	ret = []
	for key, value in sorted(bypass, key=lambda kv: (len(kv[0]), kv[0])):
		net = _network(value)
		if state.get(key) == str(value):
			source = "panel"
		elif net is not None and str(net) == SYSTEM_BYPASS:
			source = "system"
		else:
			source = "other"
		ret.append({ "key": key, "network": str(value), "source": source })
	return ret

def get_overview(env, settings=None, now=None):
	import fail2ban_admin
	if settings is None:
		settings, _ = fail2ban_admin.get_settings(env)
	now = int(now or time.time())
	ret = {
		"available": False,
		"error": None,
		"window_hours": WINDOW_HOURS,
		"block_minutes": BLOCK_MINUTES,
		"max_delay_ms": MAX_DELAY_MS,
		"default_max_attempts": DEFAULT_MAX_ATTEMPTS,
		"entries": [],
		"entries_total": 0,
		"bypass": [],
		"now": now,
	}
	try:
		cfg = nc_config(env)
	except (NCError, OSError) as e:
		ret["error"] = str(e)
		return ret
	enabled, max_attempts = _effective(cfg)
	ret.update(enabled=enabled, max_attempts=max_attempts, config_current=_config_matches(cfg, settings))
	if cfg.get("memcache_distributed") and not cfg.get("force_database"):
		# Nextcloud then counts in the distributed cache (Redis), not in the
		# database.
		ret["error"] = "Nextcloud keeps its brute-force counters in its distributed cache (memcache.distributed), so they cannot be shown here."
		return ret
	try:
		data = _read_db(env, cfg, now - WINDOW_HOURS * 3600, now - BLOCK_MINUTES * 60)
	except NCError as e:
		ret["error"] = str(e)
		return ret
	ret["available"] = True
	state = _state(env)
	ret["bypass"] = _bypass_entries(data.get("bypass") or [], state)
	ret["bypass_current"] = _bypass_matches(settings, data.get("bypass") or [], state)
	bypass_nets = [n for n in (_network(v) for _, v in (data.get("bypass") or [])) if n is not None]
	# Only the accounts of this box are named, as in the failed-login report:
	# another login name is whatever the client sent (a password typed into
	# the wrong field too).
	known = fail2ban_admin._known_accounts(env)

	groups = {}
	for subnet, action, ip, metadata, count, recent, first, last in data.get("rows") or []:
		g = groups.setdefault(str(subnet), { "subnet": str(subnet), "ips": set(), "accounts": set(), "actions": {}, "first": first, "last": last })
		g["ips"].add(str(ip))
		u = _user(metadata)
		if u:
			g["accounts"].add(u)
		a = g["actions"].setdefault(str(action), [0, 0])
		a[0] += int(count)
		a[1] += int(recent or 0)
		g["first"] = min(g["first"], first)
		g["last"] = max(g["last"], last)

	entries = []
	for g in groups.values():
		attempts = sum(a[0] for a in g["actions"].values())
		recent = sum(a[1] for a in g["actions"].values())
		# Each action is counted on its own: the worst one decides.
		worst = max(a[0] for a in g["actions"].values())
		blocked = enabled and any(a[0] > max_attempts and a[1] > max_attempts for a in g["actions"].values())
		addrs = []
		for ip in g["ips"]:
			try:
				addrs.append(ipaddress.ip_address(ip))
			except ValueError:
				pass
		bypassed = any(a in n for a in addrs for n in bypass_nets if a.version == n.version)
		net = _network(g["subnet"])
		if net is not None and net.num_addresses == 1:
			address = str(net.network_address)
		else:
			address = str(net) if net is not None else g["subnet"]
		entries.append({
			"subnet": g["subnet"],
			"address": address,
			"ips": sorted(g["ips"])[:20],
			"ips_total": len(g["ips"]),
			"attempts": attempts,
			"recent": recent,
			"actions": { k: v[0] for k, v in sorted(g["actions"].items()) },
			"accounts": sorted(a for a in g["accounts"] if a in known)[:MAX_ACCOUNTS],
			"accounts_total": len([a for a in g["accounts"] if a in known]),
			"unknown_names": len([a for a in g["accounts"] if a not in known]),
			"first": int(g["first"]),
			"last": int(g["last"]),
			"delay_ms": 0 if (bypassed or not enabled) else delay_ms(worst, max_attempts),
			"blocked": blocked and not bypassed,
			"bypassed": bypassed,
		})
	entries.sort(key=lambda e: (not e["blocked"], -e["delay_ms"], -e["last"], e["address"]))
	ret["entries_total"] = len(entries)
	ret["entries"] = entries[:MAX_ENTRIES]
	return ret

def reset(env, ip):
	# Deletes the failures of an address (all actions; for IPv6 those of its
	# /64), as Administration > Security and "occ security:bruteforce:reset"
	# do. Returns the attempts Nextcloud counts afterwards.
	import fail2ban_admin
	ip = fail2ban_admin.normalize_ip(ip)
	cfg = nc_config(env)
	enabled, _ = _effective(cfg)
	if not enabled:
		raise ValueError("Nextcloud's brute-force protection is off, so it neither counts nor resets failures.")
	occ("security:bruteforce:reset", ip)
	after = None
	try:
		j = json.loads(occ("security:bruteforce:attempts", ip, "--output=json").strip().splitlines()[-1])
		after = j.get("attempts")
	except (NCError, ValueError, IndexError):
		pass
	return { "ip": ip, "attempts": after }

# SETTINGS

def settings_changed(old, new):
	if any(old.get(k) != new.get(k) for k in NC_KEYS):
		return True
	return bool(new.get("nc_allowlist") or old.get("nc_allowlist")) and old.get("allowlist") != new.get("allowlist")

def desired_config(settings):
	# config.php keys: None means not set (Nextcloud's default).
	return {
		"auth.bruteforce.protection.enabled": None if settings["nc_protection"] else False,
		"auth.bruteforce.max-attempts": None if settings["nc_max_attempts"] == DEFAULT_MAX_ATTEMPTS else settings["nc_max_attempts"],
	}

def _config_matches(cfg, settings):
	want = desired_config(settings)
	return cfg.get("enabled") == want["auth.bruteforce.protection.enabled"] \
		and cfg.get("max_attempts") == want["auth.bruteforce.max-attempts"]

def desired_bypass(settings):
	if not settings["nc_allowlist"]:
		return []
	return [_cidr(n) for n in settings["allowlist"]]

def _bypass_matches(settings, bypass, state):
	present = { str(_network(v)) for _, v in bypass if _network(v) is not None }
	want = desired_bypass(settings)
	cur = dict(bypass)
	ours_unwanted = [k for k, v in state.items() if cur.get(k) == v and v not in want]
	return all(str(_network(n)) in present for n in want) and not ours_unwanted

def config_is_current(env, settings):
	cfg = nc_config(env)
	if not _config_matches(cfg, settings):
		return False
	state = _state(env)
	if not settings["nc_allowlist"] and not state:
		return True
	data = _read_db(env, cfg, time.time(), time.time())
	return _bypass_matches(settings, data.get("bypass") or [], state)

def _list_bypass():
	out = occ("config:list", "bruteForce")
	try:
		keys = json.loads(out or "{}").get("apps", {}).get("bruteForce") or {}
	except ValueError:
		raise NCError("Unexpected output of occ config:list bruteForce.") from None
	if not isinstance(keys, dict):
		return {}
	return { str(k): str(v) for k, v in keys.items() if re.fullmatch(r"whitelist_\d+", str(k)) }

def apply_settings(env, settings):
	# Writes config.php and the bypass list as the settings say. Returns what
	# changed.
	result = { "config_changed": False, "bypass_added": [], "bypass_removed": [] }
	cfg = nc_config(env)
	want = desired_config(settings)
	have = { "auth.bruteforce.protection.enabled": cfg.get("enabled"), "auth.bruteforce.max-attempts": cfg.get("max_attempts") }
	change = { k: v for k, v in want.items() if have[k] != v }
	if change:
		nc_config(env, change)
		result["config_changed"] = True

	state = _state(env)
	wanted = desired_bypass(settings)
	if not wanted and not state:
		return result
	current = _list_bypass()
	new_state = dict(state)
	for key, net in state.items():
		if current.get(key) != net:
			# Removed or changed by an administrator: no longer ours.
			del new_state[key]
		elif net not in wanted:
			occ("config:app:delete", "bruteForce", key)
			del new_state[key]
			del current[key]
			result["bypass_removed"].append(net)
	present = { str(_network(v)) for v in current.values() if _network(v) is not None }
	used = [int(k[10:]) for k in current]
	for net in wanted:
		if str(_network(net)) in present:
			continue
		n = max(used + [0]) + 1
		key = f"whitelist_{n}"
		occ("config:app:set", "bruteForce", key, "--value", net, "--type", "string")
		used.append(n)
		present.add(str(_network(net)))
		new_state[key] = net
		result["bypass_added"].append(net)
	if new_state != state:
		_save_state(env, new_state)
	return result

# COMMAND LINE

if __name__ == "__main__":
	import fail2ban_admin
	env = utils.load_environment()
	args = sys.argv[1:]
	if args == ["--setup"]:
		# Called by setup/start.sh after fail2ban_admin.py --setup. Never stops
		# setup: on a problem Nextcloud keeps its current settings.
		settings, _ = fail2ban_admin.get_settings(env)
		try:
			r = apply_settings(env, settings)
		except Exception as e:
			print("Nextcloud's brute-force settings were not applied:", e)
			sys.exit(0)
		if r["config_changed"]:
			print("Nextcloud: brute-force settings written to config.php.")
		if r["bypass_added"]:
			print("Nextcloud: added to the brute-force bypass list (allowlist):", ", ".join(r["bypass_added"]))
		if r["bypass_removed"]:
			print("Nextcloud: removed from the brute-force bypass list:", ", ".join(r["bypass_removed"]))
	elif args == ["--status"]:
		print(json.dumps(get_overview(env), indent=2))
	elif len(args) == 2 and args[0] == "--reset":
		print(json.dumps(reset(env, args[1]), indent=2))
	else:
		print("usage: nextcloud_throttle.py --setup | --status | --reset IP", file=sys.stderr)
		sys.exit(2)
