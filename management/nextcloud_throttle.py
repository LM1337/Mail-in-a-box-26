#!/usr/local/lib/mailinabox/env/bin/python3
#
# Nextcloud's brute-force throttle (fork), for System > Intrusion Protection.
#
# Nextcloud counts each failed login in its table bruteforce_attempts, under
# the network of the client: an IPv4 address (stored as <address>/32) or the
# IPv6 network of the address (/56 by default, security.ipv6_normalized_subnet_size,
# 32 to 64). Before it checks a login it counts the failures of that network
# (lib/private/Security/Bruteforce/Throttler.php):
#
#  * within the last 12 hours: the login is delayed by 0.1 s * 2^failures, up
#    to 25 s; above auth.bruteforce.max-attempts (10 by default) always 25 s,
#  * above max-attempts within the last 12 hours and also within the last 30
#    minutes: the login is refused at once with HTTP 429 (TooManyRequests),
#    also for an account with the right password behind the same address.
#
# A successful login removes only the failures of that account from that
# network, so a device with an old password keeps a whole network throttled
# (and the devices with the right password behind it). The failures are kept
# per action ("login" for the logins of the web interface and of CalDAV,
# CardDAV and WebDAV, others for share links and the like), and each action is
# counted on its own. An address on the bypass list (the "whitelist_N" keys of
# the app config "bruteForce") is never counted or throttled; the other
# addresses of its network are. With auth.bruteforce.protection.enabled off,
# Nextcloud counts no new failures and resets none ("occ
# security:bruteforce:reset" does nothing then), but the failures counted
# before still delay and refuse logins until they are older than 12 hours.
#
# This module shows the counted networks (read from the database, read-only
# and as www-data, which owns it), resets one (deletes its rows, as
# www-data, which also works with the protection off or for an address on
# the bypass list, where occ does nothing), and applies the settings
# nc_protection, nc_max_attempts and nc_allowlist that fail2ban_admin.py
# stores with the other intrusion protection settings: the first two are
# system settings in config.php (tools/nextcloud-bruteforce-config.php), the
# last puts the allowlist on the bypass list. Turning the protection off also
# deletes the failures counted so far. The entries this module adds to the
# bypass list are recorded in settings.yaml ("nextcloud_bypass", after each
# change), so that only these are removed again: 127.0.0.1/32
# (setup/nextcloud.sh, B121) and entries of an administrator (Administration
# > Security) are never touched.
#
# Command line (as root, from the Mail-in-a-Box directory):
#   management/nextcloud_throttle.py --setup     apply the settings (setup/start.sh); while the
#                                                 settings have no value of their own, it takes
#                                                 over values set in config.php by hand
#   management/nextcloud_throttle.py --status    print the counted networks
#   management/nextcloud_throttle.py --reset IP  reset the failures of the network of an address

import os, os.path, re, sys, json, math, time, hashlib, ipaddress, subprocess

import utils

NC_ROOT = "/usr/local/lib/owncloud"
RUNUSER = "/usr/sbin/runuser"
HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_TOOL = os.path.join(HERE, "..", "tools", "nextcloud-bruteforce-config.php")

DEFAULT_MAX_ATTEMPTS = 10   # Throttler::MAX_ATTEMPTS
MAX_DELAY_MS = 25000        # Throttler::MAX_DELAY_MS
WINDOW_HOURS = 12           # the delay counts the failures of the last 12 hours
BLOCK_MINUTES = 30          # the 429 counts those of the last 30 minutes too
MAX_ROWS = 20000            # (network, action, address) groups read
MAX_NAMES = 20000           # (network, login name) pairs read, the most recent
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

# The database is read and written as www-data, the owner of the database,
# its directory and its -wal and -shm files (a connection of root could
# create these with the wrong owner). Reading is aggregated in SQL: an attack
# can leave many thousand rows, also with a new login name in each. The
# parameters come on standard input. Nothing about the accounts of the box
# goes to www-data: root sends a random salt (new each time), the reader
# returns the login names of each network as salted hashes (the most recent
# MAX_NAMES), and root compares them with the hashes of its accounts.
DB_READER = r"""
import hashlib, json, sqlite3, sys, urllib.parse
p = json.load(sys.stdin)
salt = bytes.fromhex(p["salt"])
def h(u):
    return hashlib.sha256(salt + u.strip().lower().encode("utf-8")).hexdigest() if isinstance(u, str) else None
con = sqlite3.connect("file:" + urllib.parse.quote(p["path"]) + "?mode=ro", uri=True, timeout=10)
con.create_function("h", 1, h, deterministic=True)
try:
    t = p["prefix"] + "bruteforce_attempts"
    out = {}
    if p["attempts"]:
        out["rows"] = con.execute("SELECT subnet, action, ip, COUNT(*), SUM(occurred >= ?), MIN(occurred), MAX(occurred) FROM " + t
            + " WHERE occurred >= ? GROUP BY subnet, action, ip ORDER BY MAX(occurred) DESC LIMIT ?", (p["recent"], p["since"], p["limit"])).fetchall()
        out["names"] = con.execute("SELECT subnet, COUNT(DISTINCT CASE WHEN json_valid(metadata) THEN lower(json_extract(metadata, '$.user')) END) FROM " + t
            + " WHERE occurred >= ? GROUP BY subnet", (p["since"],)).fetchall()
        out["hashes"] = con.execute("SELECT subnet, h(u) FROM (SELECT subnet, CASE WHEN json_valid(metadata) THEN json_extract(metadata, '$.user') END AS u, MAX(occurred) AS last FROM " + t
            + " WHERE occurred >= ? GROUP BY subnet, u) WHERE u IS NOT NULL ORDER BY last DESC LIMIT ?", (p["since"], p["names"])).fetchall()
    out["bypass"] = con.execute("SELECT configkey, configvalue FROM " + p["prefix"] + "appconfig WHERE appid = 'bruteForce' AND configkey LIKE 'whitelist\\_%' ESCAPE '\\'").fetchall()
finally:
    con.close()
json.dump(out, sys.stdout)
"""

# Deletes the failures of the networks that contain an address, or all of
# them ("ip": null), as Nextcloud's own reset does (its backend deletes by
# network). Prints the networks and the number of rows deleted.
DB_DELETER = r"""
import ipaddress, json, sqlite3, sys, urllib.parse
p = json.load(sys.stdin)
con = sqlite3.connect("file:" + urllib.parse.quote(p["path"]) + "?mode=rw", uri=True, timeout=30)
try:
    t = p["prefix"] + "bruteforce_attempts"
    with con:
        if p["ip"] is None:
            subnets = None
            n = con.execute("DELETE FROM " + t).rowcount
        else:
            a = ipaddress.ip_address(p["ip"])
            subnets = []
            for (s,) in con.execute("SELECT DISTINCT subnet FROM " + t).fetchall():
                try:
                    net = ipaddress.ip_network(s, strict=False)
                except ValueError:
                    continue
                if net.version == a.version and a in net:
                    subnets.append(s)
            n = 0
            for s in subnets:
                n += con.execute("DELETE FROM " + t + " WHERE subnet = ?", (s,)).rowcount
finally:
    con.close()
json.dump({"subnets": subnets, "deleted": n}, sys.stdout)
"""

def _db(env, cfg):
	if (cfg.get("dbtype") or "sqlite3") not in ("sqlite", "sqlite3"):
		raise NCError("Nextcloud does not use SQLite here, so its throttle cannot be read or reset here.")
	if cfg.get("memcache_distributed") and not cfg.get("force_database"):
		# Nextcloud then counts in the distributed cache (Redis), not in the
		# database.
		raise NCError("Nextcloud keeps its brute-force counters in its distributed cache (memcache.distributed), so they cannot be read or reset here.")
	prefix = cfg.get("dbtableprefix") or "oc_"
	if not re.fullmatch(r"[A-Za-z0-9_]{0,32}", prefix):
		raise NCError("Nextcloud's table prefix is not a plain name.")
	datadir = cfg.get("datadirectory") or ""
	if not datadir.startswith("/"):
		raise NCError("Nextcloud's data directory is not known.")
	return { "path": os.path.join(datadir, "owncloud.db"), "prefix": prefix }

def _run_db(script, params, what):
	p = _run_www(["/usr/bin/python3", "-I", "-c", script], stdin=json.dumps(params), timeout=120)
	if p.returncode != 0:
		raise _fail(what, p)
	try:
		return json.loads(p.stdout)
	except ValueError:
		raise NCError(f"Unexpected output when {what.lower()}.") from None

def _read_db(env, cfg, since=0, recent=0, known=(), attempts=True):
	# "known" of the result: (network, account) for the accounts given.
	salt = os.urandom(16)
	params = dict(_db(env, cfg), since=int(since), recent=int(recent), salt=salt.hex(), attempts=attempts,
		limit=MAX_ROWS, names=MAX_NAMES)
	r = _run_db(DB_READER, params, "Reading Nextcloud's database")
	hashes = { hashlib.sha256(salt + a.strip().lower().encode("utf-8")).hexdigest(): a for a in known }
	r["known"] = sorted({ (str(s), hashes[hu]) for s, hu in r.get("hashes") or [] if hu in hashes })
	r["names_truncated"] = len(r.get("hashes") or []) >= MAX_NAMES
	return r

def delete_attempts(env, cfg, ip=None):
	# ip None: every failure of every network.
	return _run_db(DB_DELETER, dict(_db(env, cfg), ip=ip), "Deleting Nextcloud's failed logins")

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

def _effective(cfg):
	# As Nextcloud reads them (tools/nextcloud-bruteforce-config.php).
	enabled = cfg.get("enabled_effective")
	max_attempts = cfg.get("max_attempts_effective")
	return (enabled is not False), (max_attempts if isinstance(max_attempts, int) and not isinstance(max_attempts, bool) else DEFAULT_MAX_ATTEMPTS)

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
	ret.update(enabled=enabled, max_attempts=max_attempts, ipv6_prefix=cfg.get("ipv6_prefix"),
		config_current=_config_matches(cfg, settings))
	# Only the accounts of this box are named, as in the failed-login report:
	# another login name is whatever the client sent (a password typed into
	# the wrong field too).
	known = fail2ban_admin._known_accounts(env)
	try:
		data = _read_db(env, cfg, now - WINDOW_HOURS * 3600, now - BLOCK_MINUTES * 60, known)
	except NCError as e:
		ret["error"] = str(e)
		return ret
	ret["available"] = True
	state = _state(env)
	ret["bypass"] = _bypass_entries(data.get("bypass") or [], state)
	ret["bypass_current"] = _bypass_matches(settings, data.get("bypass") or [], state)
	bypass_nets = [n for n in (_network(v) for _, v in (data.get("bypass") or [])) if n is not None]

	names = { str(s): int(n or 0) for s, n in data.get("names") or [] }
	accounts = {}
	for s, u in data.get("known") or []:
		accounts.setdefault(str(s), set()).add(str(u))
	groups = {}
	for subnet, action, ip, count, recent, first, last in data.get("rows") or []:
		g = groups.setdefault(str(subnet), { "ips": set(), "actions": {}, "first": first, "last": last })
		g["ips"].add(str(ip))
		a = g["actions"].setdefault(str(action), [0, 0])
		a[0] += int(count)
		a[1] += int(recent or 0)
		g["first"] = min(g["first"], first)
		g["last"] = max(g["last"], last)

	def bypassed(ip):
		try:
			a = ipaddress.ip_address(ip)
		except ValueError:
			return False
		return any(a.version == n.version and a in n for n in bypass_nets)

	entries = []
	for subnet, g in groups.items():
		attempts = sum(a[0] for a in g["actions"].values())
		recent = sum(a[1] for a in g["actions"].values())
		# Each action is counted on its own: the worst one decides. Also with
		# the protection off: Nextcloud still applies the failures counted
		# before (it only stops counting new ones).
		worst = max(a[0] for a in g["actions"].values())
		blocked = any(a[0] > max_attempts and a[1] > max_attempts for a in g["actions"].values())
		ips = sorted(g["ips"])
		bypassed_ips = [ip for ip in ips if bypassed(ip)]
		net = _network(subnet)
		if net is not None and net.num_addresses == 1:
			address = str(net.network_address)
		else:
			address = str(net) if net is not None else subnet
		known_here = sorted(accounts.get(subnet, ()))
		entries.append({
			"subnet": subnet,
			"address": address,
			"network": net is not None and net.num_addresses > 1,
			"ips": ips[:20],
			"ips_total": len(ips),
			"attempts": attempts,
			"recent": recent,
			"actions": { k: v[0] for k, v in sorted(g["actions"].items()) },
			"accounts": known_here[:MAX_ACCOUNTS],
			"accounts_total": len(known_here),
			"unknown_names": max(0, names.get(subnet, 0) - len(known_here)),
			"first": int(g["first"]),
			"last": int(g["last"]),
			# What Nextcloud applies to an address of this network that is not
			# on the bypass list.
			"delay_ms": delay_ms(worst, max_attempts),
			"blocked": blocked,
			# The addresses that failed here and are on the bypass list now
			# (Nextcloud does not throttle them); "bypassed": all of them.
			"bypassed_ips": bypassed_ips[:20],
			"bypassed": bool(ips) and len(bypassed_ips) == len(ips),
		})
	entries.sort(key=lambda e: (e["bypassed"], not e["blocked"], -e["delay_ms"], -e["last"], e["address"]))
	# With the protection off every row is stale: counted before it was
	# turned off, or by a login that was already waiting in the throttle
	# then (up to 25 s, with the old configuration) and registered its
	# failure after the deletion. Nextcloud still applies them for up to
	# 12 hours. Setup and the daily status checks delete them; the control
	# panel shows them with a button (a GET deletes nothing).
	ret["stale"] = (not enabled) and bool(entries)
	ret["entries_total"] = len(entries)
	ret["entries_truncated"] = len(data.get("rows") or []) >= MAX_ROWS
	ret["entries"] = entries[:MAX_ENTRIES]
	return ret

def delete_stale(env, cfg=None):
	# With the protection off: deletes every failure still in the database
	# (see "stale" in get_overview). Returns the number deleted, None when
	# the protection is on.
	if cfg is None:
		cfg = nc_config(env)
	enabled, _ = _effective(cfg)
	if enabled:
		return None
	return int(delete_attempts(env, cfg).get("deleted") or 0)

def reset(env, ip):
	# Deletes the failures of the network of an address (all actions), as
	# Administration > Security and "occ security:bruteforce:reset" do, but
	# also with the protection off and for an address on the bypass list,
	# where these do nothing.
	import fail2ban_admin
	ip = fail2ban_admin.normalize_ip(ip)
	cfg = nc_config(env)
	r = delete_attempts(env, cfg, ip)
	return { "ip": ip, "subnets": r.get("subnets") or [], "deleted": int(r.get("deleted") or 0) }

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
	data = _read_db(env, cfg, attempts=False)
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
	# changed. The bypass entries this module adds or removes are recorded
	# after each change, so a failure in between leaves no entry unrecorded.
	result = { "config_changed": False, "attempts_deleted": 0, "bypass_added": [], "bypass_removed": [] }
	cfg = nc_config(env)
	want = desired_config(settings)
	have = { "auth.bruteforce.protection.enabled": cfg.get("enabled"), "auth.bruteforce.max-attempts": cfg.get("max_attempts") }
	change = { k: v for k, v in want.items() if have[k] != v }
	was_on, _ = _effective(cfg)
	if change:
		cfg = nc_config(env, change)
		result["config_changed"] = True
	if not settings["nc_protection"]:
		# Off: Nextcloud stops counting (config.php first, so that no new
		# failure is counted after the deletion), but it goes on applying
		# the failures counted before, for up to 12 hours. PHP-FPM may use
		# the old config.php for up to a second (opcache.revalidate_freq=1),
		# so after turning it off the deletion waits 2 seconds.
		if was_on:
			time.sleep(2)
		try:
			result["attempts_deleted"] = int(delete_attempts(env, cfg).get("deleted") or 0)
		except NCError as e:
			raise NCError(f"The protection is off now, but the failures counted before could not be deleted, so they still delay logins for up to {WINDOW_HOURS} hours: {e}") from None

	state = _state(env)
	wanted = desired_bypass(settings)
	if not wanted and not state:
		return result
	current = _list_bypass()
	for key, net in list(state.items()):
		if current.get(key) != net:
			# Removed or changed by an administrator: no longer ours.
			del state[key]
			_save_state(env, state)
		elif net not in wanted:
			occ("config:app:delete", "bruteForce", key)
			del state[key]
			del current[key]
			_save_state(env, state)
			result["bypass_removed"].append(net)
	present = { str(_network(v)) for v in current.values() if _network(v) is not None }
	used = [int(k[10:]) for k in current]
	for net in wanted:
		if str(_network(net)) in present:
			continue
		n = max(used + [0]) + 1
		key = f"whitelist_{n}"
		# Recorded before it is set: an entry that is recorded but not set is
		# dropped on the next run (above), one that is set but not recorded
		# would stay for good.
		state[key] = net
		_save_state(env, state)
		occ("config:app:set", "bruteForce", key, "--value", net, "--type", "string")
		used.append(n)
		present.add(str(_network(net)))
		result["bypass_added"].append(net)
	return result

def hand_set_values(env, cfg=None):
	# For each of nc_protection and nc_max_attempts on its own: while the
	# settings have no value of their own for it (never saved, or saved at
	# its default), the value that an administrator set in config.php by
	# hand, as Nextcloud reads it, to be taken over instead of overwritten:
	# ({setting: value}, [description]). The control panel shows them in its
	# form (and stores them with the next save), setup stores them at once.
	import fail2ban_admin
	stored = utils.load_settings(env).get("fail2ban")
	if not isinstance(stored, dict):
		stored = {}
	if all(k in stored for k in ("nc_protection", "nc_max_attempts")):
		return {}, []
	if cfg is None:
		cfg = nc_config(env)
	enabled, ma = _effective(cfg)
	vals, msgs = {}, []
	if "nc_protection" not in stored and not enabled:
		vals["nc_protection"] = False
		msgs.append("auth.bruteforce.protection.enabled = " + json.dumps(cfg.get("enabled")))
	if "nc_max_attempts" not in stored and cfg.get("max_attempts") is not None and ma != DEFAULT_MAX_ATTEMPTS:
		lo, hi = fail2ban_admin.LIMITS["nc_max_attempts"]
		vals["nc_max_attempts"] = min(hi, max(lo, ma))
		msgs.append("auth.bruteforce.max-attempts = " + json.dumps(cfg.get("max_attempts"))
			+ ("" if lo <= ma <= hi else f" (as {vals['nc_max_attempts']}, the settings take {lo} to {hi})"))
	return vals, msgs

def import_hand_set(env, settings):
	# setup: store the values of hand_set_values. Returns (settings, messages).
	import fail2ban_admin
	vals, msgs = hand_set_values(env)
	if not vals:
		return settings, []
	new = dict(settings, **vals)
	fail2ban_admin.save_settings(env, new)
	return new, msgs

# COMMAND LINE

if __name__ == "__main__":
	import fail2ban_admin
	env = utils.load_environment()
	args = sys.argv[1:]
	if args == ["--setup"]:
		# Called by setup/start.sh after fail2ban_admin.py --setup. Never stops
		# setup: on a problem Nextcloud keeps its current settings.
		try:
			settings, _ = fail2ban_admin.get_settings(env)
			settings, imported = import_hand_set(env, settings)
			if imported:
				print("Nextcloud: took over " + ", ".join(imported) + " from config.php into the intrusion protection settings (System > Intrusion Protection).")
			r = apply_settings(env, settings)
		except Exception as e:
			print("Nextcloud's brute-force settings were not applied:", e)
			sys.exit(0)
		if r["config_changed"]:
			print("Nextcloud: brute-force settings written to config.php.")
		if r["attempts_deleted"]:
			print(f"Nextcloud: the protection is off, {r['attempts_deleted']} failed logins counted before were deleted.")
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
