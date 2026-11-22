#!/usr/bin/env python3
"""
Offline test of management/auth_guard.py -- python3 stdlib only, no box
needed (B126: the limit of failed logins from the box itself).

  * the values of conf/dovecot-auth-guard/guard.lua are read (window 1800 s,
    limit 30, at most 2000 names without the list of accounts), the box's
    own addresses and the list of accounts written for the Lua code;
  * an account name becomes the same file name as in guard.lua (lower case,
    %XX for other bytes), and back;
  * scan(): names with different wrong passwords in the window (a tag sent
    again counts once), files of names without any
    are removed, old .tmp files too, a symbolic link and other names are
    left alone, a directory of another mode is refused; the events are read
    once (also a leftover events.read), broken lines are dropped; --unlock
    removes the name's file;
  * notify(): the first event is mailed at once, later ones wait for the
    next hour and are mailed together, a name without an account is marked,
    the pending events are capped.

  tests/fork/auth-guard.py

Exit code: 0 = all cases pass, 1 = a case failed (printed).
"""

import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "management"))

import auth_guard as ag # noqa: E402

failures = []


def check(name, got, want):
	if got != want:
		failures.append(name)
		print(f"FAIL {name}\n  want: {want!r}\n  got:  {got!r}")
	else:
		print(f"ok   {name}")


cfg = ag.settings()
lv = ag.lua_values()
check("values of guard.lua", (lv["DIR"], lv["DEFAULT_WINDOW"], lv["DEFAULT_LIMIT"], lv["MAX_NAMES"], lv["SETTINGS"], lv["LIMIT_MIN"], lv["LIMIT_MAX"], lv["WINDOW_MIN"], lv["WINDOW_MAX"]),
	("/run/miab-auth-guard", 1800, 30, 2000, "/usr/local/lib/mailinabox/dovecot-auth-guard/settings", 3, 1000, 60, 86400))
check("accounts path", lv["ACCOUNTS"], "/usr/local/lib/mailinabox/dovecot-auth-guard/accounts")
cfg = ag.settings(settings_file="/nonexistent")
check("defaults apply without a settings file", (cfg["LIMIT"], cfg["WINDOW"]), (30, 1800))
check("panel defaults and ranges", (ag.defaults(), ag.ranges()), ({"limit": 30, "window": 30, "span": 4}, {"limit": [3, 1000], "window": [1, 1440], "span": [1, 4]}))
good, _ = ag.validate_settings({"limit": "50", "window": 60, "span": "2"})
check("valid setting", good, {"limit": 50, "window": 60, "span": 2})
bad = 0
for v in ({"limit": "2"}, {"limit": "1001"}, {"limit": "3.5"}, {"limit": "-5"}, {"limit": "30\nwindow 1"}, {"window": "0"}, {"window": "1441"}, {"limit": True}, {"span": "0"}, {"span": "5"}):
	try:
		ag.validate_settings(v)
	except ag.AuthGuardError:
		bad += 1
check("invalid settings refused", bad, 10)
st, warn = ag.validate_settings({"limit": "x", "window": 10}, strict=False)
check("stored bad value: default and a warning", (st, len(warn)), ({"limit": 30, "window": 10, "span": 4}, 1))
check("settings file text", ag.render_settings_file({"limit": 50, "window": 60, "span": 2}).splitlines()[-3:], ["limit 50", "window 3600", "span 2"])
env_ips = {"PUBLIC_IP": "192.0.2.10", "PUBLIC_IPV6": "2001:DB8:0:0::10", "PRIVATE_IP": "192.0.2.10", "PRIVATE_IPV6": "", "OTHER": "x"}
check("box addresses", ag.box_addresses(env_ips, interfaces=["127.0.0.1", "fe80::B8FC:1eff:fe60:6fe3", "198.51.100.7", "192.0.2.10"]),
	["192.0.2.10", "2001:db8::10", "127.0.0.1", "fe80::b8fc:1eff:fe60:6fe3", "198.51.100.7"])
check("box addresses refuse junk", ag.box_addresses({"PUBLIC_IP": "1.2.3.4\nlimit 3", "PUBLIC_IPV6": "fe80::1%eth0"}, interfaces=[]), [])
_out = "2: eth0    inet 192.0.2.10/24 brd 192.0.2.255 scope global eth0\n2: eth0    inet6 fe80::1%eth0/64 scope link\n2: eth0    inet6 2001:db8::10/64 scope global"
_orig = ag.subprocess.run
ag.subprocess.run = lambda *a, **k: type("R", (), {"stdout": _out})()
check("ip -o addr parsed", ag.interface_addresses(), ["192.0.2.10", "fe80::1", "2001:db8::10"])
ag.subprocess.run = _orig
check("settings file with addresses", ag.render_settings_file({"limit": 30, "window": 30}, ["192.0.2.10", "2001:db8::10"]).splitlines()[-2:], ["local 192.0.2.10", "local 2001:db8::10"])
check("accounts list", ag.render_accounts(["b@example.com", "A@example.com", "a@example.com"]), "a-a@example.com\na-b@example.com\n")

check("key plain", ag.key_of("Alice@Example.com"), "a-alice@example.com")
check("key escaped", ag.key_of("a/b c@ex.com"), "a-a%2Fb%20c@ex.com")
check("key umlaut", (ag.key_of("jörg@ex.com"), ag.key_of("JÖRG@ex.com")), ("a-j%C3%B6rg@ex.com", "a-j%C3%96rg@ex.com")) # as Lua: only A-Z lowered
check("key long (as Lua's FNV-1a)", ag.key_of("x" * 300 + "@ex.com"), "h-406c9ac38f299459-307")
check("name back", (ag.name_of("a-j%C3%B6rg@ex.com"), ag.name_of("a-a%0Ab@ex.com"), ag.name_of("h-0123456789abcdef-300")),
	("jörg@ex.com", "a?b@ex.com", "(a name of more than 200 characters)"))
check("key pattern", [bool(ag.KEY_RE.match(k)) for k in ("a-alice@example.com", "a-..", "h-0123456789abcdef-12", "total", "a-x/y", "events")],
	[True, True, True, False, False, False])

NOW = 1_800_000_000
W = cfg["WINDOW"]

with tempfile.TemporaryDirectory() as root:
	d = os.path.join(root, "state")
	os.mkdir(d, 0o700)

	def put(name, lines, age=0):
		# lines: times (each with a tag of its own) or (time, tag)
		p = os.path.join(d, name)
		with open(p, "w") as f:
			for i, t in enumerate(lines):
				t, tag = t if isinstance(t, tuple) else (t, "%04x" % i)
				f.write(f"{t} {tag}\n")
		os.utime(p, (NOW - age, NOW - age))

	put("a-alice@example.com", [NOW - 10] * 120)                     # locked
	put("a-bob@example.com", [NOW - W - 5] * 3 + [NOW - 100] * 2)   # 2 in the window
	put("a-dave@example.com", [(NOW - 50, "beef")] * 30 + [(NOW - 40, "0001"), "junk"]) # an old password sent 30 times: 2 different
	put("a-old@example.com", [NOW - 4 * W - 100] * 4, age=4 * W + 50) # older than the 4 windows: removed
	put("a-fresh@example.com", [NOW - W - 100], age=10)              # none in the window, kept for 4 windows
	put("x.tmp", [], age=120)                                        # old tmp: removed
	put("a-y@example.com.tmp", [], age=5)                            # new tmp: kept
	os.symlink("/etc/passwd", os.path.join(d, "a-link@example.com"))
	with open(os.path.join(d, "events.read"), "w") as f:
		f.write(f"{NOW - 900} locked 100 a-carol@example.com\n")
	with open(os.path.join(d, "events"), "w") as f:
		f.write(f"{NOW - 5} locked 100 a-alice@example.com\nbroken line\n{NOW - 4} locked 100 ../../etc\n{NOW - 3} names 10000 -\n")

	res = ag.scan(d, W, now=NOW)
	names = sorted((n["key"], n["failures"]) for n in res["names"])
	check("scan names", names, [("a-alice@example.com", 120), ("a-bob@example.com", 2), ("a-dave@example.com", 2)])
	check("scan removed", sorted(os.listdir(d)), ["a-alice@example.com", "a-bob@example.com", "a-dave@example.com", "a-fresh@example.com", "a-link@example.com", "a-y@example.com.tmp"])
	check("scan events", [(e["kind"], e["key"]) for e in res["events"]], [("locked", "a-carol@example.com"), ("locked", "a-alice@example.com"), ("names", "-")])
	check("events read once", ag.scan(d, W, now=NOW)["events"], [])
	check("status keeps events", (open(os.path.join(d, "events"), "w").write(f"{NOW} locked 100 a-bob@example.com\n") > 0,
		len(ag.scan(d, W, now=NOW, consume=False)["events"]), os.path.exists(os.path.join(d, "events"))), (True, 0, True))
	ag.scan(d, W, now=NOW, consume=False, remove="a-alice@example.com")
	check("unlock", os.path.exists(os.path.join(d, "a-alice@example.com")), False)
	check("missing dir", ag.scan(os.path.join(root, "nothing"), W, now=NOW)["missing"], True)
	os.chmod(d, 0o750)
	try:
		ag.scan(d, W, now=NOW)
		check("refuses mode 0750", "no error", "ValueError")
	except ValueError:
		check("refuses mode 0750", "ValueError", "ValueError")
	os.chmod(d, 0o700)

	# notify(): at once, then at most hourly.
	ag.known_accounts = lambda env: {"alice@example.com"}
	sp = os.path.join(root, "notify.json")
	mails = []
	def scan_with(events):
		return lambda: { "names": [], "events": events, "missing": False }
	ev = lambda t, k: { "time": t, "kind": "locked", "count": 100, "key": k }
	sent1 = ag.notify({}, cfg, now=NOW, scan_func=scan_with([ev(NOW - 60, "a-alice@example.com")]), send=mails.append, state_path=sp)
	sent2 = ag.notify({}, cfg, now=NOW + 600, scan_func=scan_with([ev(NOW + 500, "a-ghost@example.com")]), send=mails.append, state_path=sp)
	sent3 = ag.notify({}, cfg, now=NOW + 1200, scan_func=scan_with([]), send=mails.append, state_path=sp)
	sent4 = ag.notify({}, cfg, now=NOW + 3700, scan_func=scan_with([]), send=mails.append, state_path=sp)
	check("notify rate", (sent1, sent2, sent3, sent4, len(mails)), (True, False, False, True, 2))
	check("mail 1", ("alice@example.com: 100 different wrong passwords in 30 minutes" in mails[0], "no such account" in mails[0]), (True, False))
	check("mail 2 marks unknown", "ghost@example.com (no such account)" in mails[1], True)
	check("state after", ag.load_state(sp)["pending"], [])
	sp2 = os.path.join(root, "notify2.json"); m2 = []
	ag.notify({}, cfg, now=NOW, scan_func=scan_with([]), send=m2.append, state_path=sp2, problems=["list"])
	ag.notify({}, cfg, now=NOW + 4000, scan_func=scan_with([]), send=m2.append, state_path=sp2, problems=["list"])
	ag.notify({}, cfg, now=NOW + 8000, scan_func=scan_with([]), send=m2.append, state_path=sp2, problems=[])
	ag.notify({}, cfg, now=NOW + 12000, scan_func=scan_with([]), send=m2.append, state_path=sp2, problems=["list"])
	check("a problem is mailed once until it is gone", len(m2), 2)
	many = [ev(NOW + 3800 + i, f"a-u{i}@example.com") for i in range(ag.MAX_PENDING + 5)]
	ag.notify({}, cfg, now=NOW + 3800, scan_func=scan_with(many), send=mails.append, state_path=sp)
	st = ag.load_state(sp)
	check("pending capped", (len(st["pending"]), st["dropped"]), (ag.MAX_PENDING, 5))

# The burst rule (as guard.lua): refused while the different wrong passwords
# of the last k windows reach k * limit, k = 1..4.
burst = "".join(f"{NOW - 10} {i:04x}\n" for i in range(100))  # a burst of 100 at once
check("burst: refused in its window", ag._recent(burst, NOW, W, 30)[:2], (100, True))
check("burst: still refused 2 windows later", ag._recent(burst, NOW + 2 * W, W, 30)[:2], (0, True))
check("burst: open after 4 windows", ag._recent(burst, NOW + 3 * W + 20, W, 30)[1], False)
check("span 1: a burst locks one window only", (ag._recent(burst, NOW, W, 30, 1)[1], ag._recent(burst, NOW + W, W, 30, 1)[1]), (True, False))
check("span 2: still refused in the next window", ag._recent(burst, NOW + W, W, 30, 2)[1], True)
few = "".join(f"{NOW - 10} {i:04x}\n" for i in range(29))
check("29 in a window: not refused", ag._recent(few, NOW, W, 30)[:2], (29, False))
check("the same tag again counts once", ag._recent(f"{NOW - 5} beef\n{NOW - 1} beef\n", NOW, W, 30)[0], 1)
msg = ag.message([{ "time": NOW, "kind": k, "count": 500, "key": "-" } for k in ("pool", "list", "addresses")], set(), {"LIMIT": 30, "WINDOW": 1800})
check("events pool, list, addresses in the mail", ("no account of the box" in msg, "list of accounts could not be written" in msg, "ip -o addr" in msg), (True, True, True))

with tempfile.TemporaryDirectory() as root:
	# The settings file: written through the directory's descriptor, read back
	# as the Lua code reads it; values out of range ignored.
	sf = os.path.join(root, "settings")
	os.chmod(root, 0o755)
	af = os.path.join(root, "accounts")
	check("accounts file written 0640 with its group", (ag.write_settings_file("a-x@example.com\n", af, group=os.getgid(), mode=0o640), oct(os.stat(af).st_mode & 0o777)), (True, "0o640"))
	check("accounts unchanged not rewritten", ag.write_settings_file("a-x@example.com\n", af, group=os.getgid(), mode=0o640), False)
	os.chmod(af, 0o644)
	check("a changed mode is put back", (ag.write_settings_file("a-x@example.com\n", af, group=os.getgid(), mode=0o640), oct(os.stat(af).st_mode & 0o777)), (True, "0o640"))
	check("file written", ag.write_settings_file(ag.render_settings_file({"limit": 50, "window": 60, "span": 2}), sf), True)
	check("unchanged file not rewritten", ag.write_settings_file(ag.render_settings_file({"limit": 50, "window": 60, "span": 2}), sf), False)
	c = ag.settings(settings_file=sf)
	check("Lua-side reading of the file", (c["LIMIT"], c["WINDOW"], c["SPAN"], oct(os.stat(sf).st_mode & 0o777)), (50, 3600, 2, "0o644"))
	with open(sf, "w") as f:
		f.write("limit 2\nwindow 999999\nspan 9\n")
	c = ag.settings(settings_file=sf)
	check("out of range: defaults", (c["LIMIT"], c["WINDOW"], c["SPAN"]), (30, 1800, 4))
	os.chmod(root, 0o777)
	try:
		ag.write_settings_file("x", sf)
		check("refuses a directory others may write", "written", "AuthGuardError")
	except ag.AuthGuardError:
		check("refuses a directory others may write", "AuthGuardError", "AuthGuardError")
	os.chmod(root, 0o755)

	# status() and unlock() of the control panel.
	ag.known_accounts = lambda env: {"alice@example.com"}
	ag.get_settings = lambda env: ({"limit": 30, "window": 30, "span": 4}, [])
	ag.settings = lambda *a, **k: dict(ag.lua_values(), LIMIT=30, WINDOW=1800, SPAN=4)
	res = ag.status({}, scan_func=lambda: {"names": [{"key": "a-alice@example.com", "failures": 31, "last": NOW}, {"key": "a-x%40y@example.com", "failures": 2, "last": NOW}], "events": [], "missing": False})
	check("status", [(n["name"], n["refused"], n["account"]) for n in res["names"]], [("alice@example.com", True, True), ("x@y@example.com", False, False)])
	check("status setting", (res["settings"], res["applied"], res["warnings"]), ({"limit": 30, "window": 30, "span": 4}, {"limit": 30, "window": 30, "span": 4}, []))
	removed = []
	ag.unlock("a-alice@example.com", scan_func=lambda: removed.append(1))
	refused = 0
	for k in ("../x", "total", "events", "a-a/b", ""):
		try:
			ag.unlock(k, scan_func=lambda: removed.append(2))
		except ag.AuthGuardError:
			refused += 1
	check("unlock", (removed, refused), ([1], 5))

print(f"{len(failures)} failed." if failures else "all cases passed.")
sys.exit(1 if failures else 0)
