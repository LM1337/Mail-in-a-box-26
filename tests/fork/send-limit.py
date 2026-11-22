#!/usr/bin/env python3
"""
Offline test of the sending limit (B221): conf/send-limit/milter.py (with a
stand-in for the Milter module) and management/send_limit.py -- python3
stdlib only, no box needed.

  * the token bucket: RATE mails at once, then RATE per PER seconds, in the
    order the mails came; a mail of n recipients takes n; a wait longer than
    MAX_WAIT is refused (deferred), except for a mail too big to fit that
    finds nothing else waiting; a change of the setting applies at once;
  * the milter's settings file: defaults without it, values clamped, broken
    lines ignored; the sender names of the events file;
  * the minute's line of the milter is read back by send_limit.py; broken or
    foreign lines are dropped;
  * the setting of the control panel: defaults, ranges, strict errors, the
    settings file written (and not again when it is the same);
  * notify(): the first event is mailed at once, later ones within the hour
    wait and go out together; status() merges kept and fresh events of the
    last 24 hours and warns when the milter is not running or uses other
    values; the events file is taken by renaming it, a link is not followed.

  tests/fork/send-limit.py

Exit code: 0 = all cases pass, 1 = a case failed (printed).
"""

import importlib.util
import os
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, os.path.join(ROOT, "management"))

# The milter imports pymilter's module "Milter": a stand-in is enough here.
fake = types.ModuleType("Milter")
fake.Base = object
fake.CONTINUE, fake.ACCEPT, fake.TEMPFAIL = "continue", "accept", "tempfail"
fake.noreply = lambda f: f
sys.modules["Milter"] = fake
spec = importlib.util.spec_from_file_location("sendlimit_milter", os.path.join(ROOT, "conf", "send-limit", "milter.py"))
milter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(milter)

import send_limit as sl # noqa: E402

failures = []


def check(name, got, want):
	if got != want:
		failures.append(name)
		print(f"FAIL {name}: got {got!r}, want {want!r}")


# The token bucket.
L = milter.Limiter()
waits = [L.reserve(1, 30, 1, now=100.0) for _ in range(30)]
check("burst of 30 at once", waits, [0.0] * 30)
w = L.reserve(1, 30, 1, now=100.0)
check("31st waits 1/30 s", round(w, 4), round(1 / 30, 4))
w = L.reserve(1, 30, 1, now=100.0)
check("32nd waits 2/30 s", round(w, 4), round(2 / 30, 4))
L = milter.Limiter()
waits = [L.reserve(1, 30, 1, now=100.0) for _ in range(30 + 30 * 60)]
check("flood: last one waits 60 s", round(waits[-1], 3), 60.0)
check("flood: next one deferred", L.reserve(1, 30, 1, now=100.0), None)
check("flood: later it fits again", L.reserve(1, 30, 1, now=140.0) is not None, True)
L = milter.Limiter()
check("steady rate under the limit never waits", all(L.reserve(1, 30, 1, now=1000 + i * 0.05) == 0 for i in range(2000)), True)
L = milter.Limiter()
check("mail of 30 recipients at once", L.reserve(30, 30, 1, now=10.0), 0.0)
check("then a mail of 15 waits 0.5 s", round(L.reserve(15, 30, 1, now=10.0), 3), 0.5)
L = milter.Limiter()
check("mail of 5000 recipients, nothing waits: goes out", L.reserve(5000, 30, 1, now=10.0), 0.0)
check("the next is deferred (would wait ~166 s)", L.reserve(1, 30, 1, now=10.0), None)
check("after the bucket refilled it goes", L.reserve(1, 30, 1, now=10.0 + 5000 / 30), 0.0)
L = milter.Limiter()
check("1 per hour: first goes", L.reserve(1, 1, 3600, now=0.0), 0.0)
check("1 per hour: second deferred", L.reserve(1, 1, 3600, now=1.0), None)
check("1 per hour: after an hour", L.reserve(1, 1, 3600, now=3600.0), 0.0)
L = milter.Limiter()
for _ in range(30 + 30 * 50):
	L.reserve(1, 30, 1, now=0.0)
check("lower rate: the backlog is capped at once", L.reserve(1, 5, 1, now=0.0) is not None, True)

# Which mail counts: SMTP with a login, sendmail (port 0) and SMTP from the
# box itself (loopback); mail from other servers passes uncounted.
check("loopback", [milter.is_loopback(x) for x in ("127.0.0.1", "127.9.8.7", "::1", "::ffff:127.0.0.1", "203.0.113.5", "10.0.0.1", "fe80::1%eth0", "", None)],
	[True, True, True, True, False, False, False, False, False])
milter.settings.values, milter.settings.checked = {"enabled": 1, "rate": 1, "per": 3600}, 10 ** 12
milter.stats = milter.Stats()


def session(addr, auth=None):
	m = milter.SendLimit()
	m.getsymval = lambda k: auth if k == "{auth_authen}" else None
	m.setreply = lambda *a: None
	m.connect("host", 2, addr)
	m.envfrom("<a@example.com>")
	m.envrcpt("<b@example.org>")
	return m.eom()


milter.limiter = milter.Limiter()
first = session(("127.0.0.1", 41000))
check("1 per hour: first local SMTP mail", first, "accept")
check("1 per hour: second local SMTP mail deferred", session(("127.0.0.1", 41001)), "tempfail")
check("sendmail (port 0) counted", session(("127.0.0.1", 0)), "tempfail")
check("SMTP with a login counted", session(("203.0.113.5", 41002), auth="a@example.com"), "tempfail")
check("::1 counted", session(("::1", 41003, 0, 0)), "tempfail")
check("another server: not counted", session(("203.0.113.5", 41004)), "accept")
check("another server over IPv6: not counted", session(("2001:db8::5", 41005, 0, 0)), "accept")
milter.settings.values = {"enabled": 0, "rate": 1, "per": 3600}
check("turned off: local SMTP goes", session(("127.0.0.1", 41006)), "accept")
milter.settings = milter.Settings()

# The milter's settings file.
with tempfile.TemporaryDirectory() as d:
	milter.SETTINGS = os.path.join(d, "settings")
	check("no file: defaults", milter.Settings.read(), {"enabled": 1, "rate": 30, "per": 1})
	open(milter.SETTINGS, "w").write("# c\nenabled 0\nrate 0\nper 999999\nbogus 4\nrate x\n")
	check("file: clamped, broken ignored", milter.Settings.read(), {"enabled": 0, "rate": 1, "per": 86400})
	open(milter.SETTINGS, "w").write(sl.render_settings_file({"enabled": True, "rate": 120, "per": 60}))
	check("written by send_limit.py", milter.Settings.read(), {"enabled": 1, "rate": 120, "per": 60})
	check("read back by send_limit.py", sl.read_settings_file(milter.SETTINGS), {"enabled": True, "rate": 120, "per": 60})
	check("send_limit.py without file", sl.read_settings_file(os.path.join(d, "none")), {"enabled": True, "rate": 30, "per": 1})

check("sender names", [milter.sender_name(s) for s in ("<a@b.c>", "", "<>", "x y=z\n", "a" * 300)],
	["a@b.c", "<>", "<>", "x?y?z", "a" * 200])

# The minute's line of the milter, read back.
with tempfile.TemporaryDirectory() as d:
	milter.EVENTS = os.path.join(d, "events")
	st = milter.Stats()
	st.add("alice@example.com", 3, 0.5)
	st.add("alice@example.com", 2, 12.2)
	st.add("sendmail:www-data@box.example.com", 1, None)
	st.add("bob@example.com", 1, 0)
	s = milter.Settings()
	s.values, s.checked = {"enabled": 1, "rate": 30, "per": 1}, 10 ** 12
	milter.log = lambda *a, **k: None
	st.flush(s)
	st.flush(s) # nothing waited since: no line
	lines = open(milter.EVENTS).read().splitlines()
	check("one line per minute with waits", len(lines), 1)
	e = sl.parse_event(lines[0])
	check("line read back", e and (e["rate"], e["per"], e["delayed"], e["deferred"], e["passed"], e["max_wait"], e["others"]), (30, 1, 2, 1, 1, 13, 0))
	check("senders read back", e and e["senders"], [{"sender": "alice@example.com", "mails": 2, "recipients": 5},
		{"sender": "sendmail:www-data@box.example.com", "mails": 1, "recipients": 1}])
	for bad in ("", "x", "1 2 3", lines[0] + " junk", "root:$6$x:1:2:3", lines[0].replace(" 30 ", " -30 ")):
		if sl.parse_event(bad) is not None:
			failures.append("broken line accepted: " + bad[:30])

	# take_events: renames, reads, removes; a link is not followed.
	evs = sl.take_events(d, consume=False)
	check("peek", (len(evs), os.path.exists(milter.EVENTS)), (1, True))
	evs = sl.take_events(d)
	check("take", (len(evs), os.path.exists(milter.EVENTS), os.listdir(d)), (1, False, []))
	secret = os.path.join(d, "..", "secret-" + os.path.basename(d))
	open(secret, "w").write(lines[0] + "\n")
	os.symlink(secret, milter.EVENTS)
	check("a link is not followed", sl.take_events(d), [])
	os.unlink(secret)
	check("missing directory", sl.take_events(os.path.join(d, "none")), [])

# The setting.
check("defaults", sl.validate_settings({}), ({"enabled": True, "rate": 30, "per": 1}, []))
check("values", sl.validate_settings({"enabled": "0", "rate": "100", "per": "60"})[0], {"enabled": False, "rate": 100, "per": 60})
bad = 0
for v in ({"rate": "0"}, {"rate": "100001"}, {"per": "0"}, {"per": "3601"}, {"rate": "1.5"}, {"rate": "x"}, {"enabled": "maybe"}, {"rate": True}):
	try:
		sl.validate_settings(v)
	except sl.SendLimitError:
		bad += 1
check("strict errors", bad, 8)
out, warn = sl.validate_settings({"rate": "x", "per": 5}, strict=False)
check("loose: default and warning", (out, len(warn)), ({"enabled": True, "rate": 30, "per": 5}, 1))

with tempfile.TemporaryDirectory() as d:
	os.chmod(d, 0o755)
	p = os.path.join(d, "settings")
	check("settings file written", sl.write_settings_file(sl.render_settings_file(sl.DEFAULTS), p), True)
	check("not again when the same", sl.write_settings_file(sl.render_settings_file(sl.DEFAULTS), p), False)
	check("its mode", oct(os.stat(p).st_mode & 0o777), "0o644")
	os.chmod(d, 0o777)
	try:
		sl.write_settings_file("x", p)
		failures.append("directory writable by others accepted")
	except sl.SendLimitError:
		pass
	os.chmod(d, 0o755)

# notify() and status().
T = 10 ** 9
with tempfile.TemporaryDirectory() as d:
	state = os.path.join(d, "state.json")
	mails = []
	ev = lambda t, n=5: {"time": t, "rate": 30, "per": 1, "delayed": n, "deferred": 0, "passed": 1, "max_wait": 2, "others": 0,
		"senders": [{"sender": "alice@example.com", "mails": n, "recipients": n}]}
	check("nothing: no mail", sl.notify(now=T + 1000, take=lambda: [], send=mails.append, state_path=state), False)
	check("first event: mailed", sl.notify(now=T + 1000, take=lambda: [ev(T + 990)], send=mails.append, state_path=state), True)
	check("within the hour: waits", sl.notify(now=T + 2000, take=lambda: [ev(T + 1990), ev(T + 1995)], send=mails.append, state_path=state), False)
	check("after the hour: together", sl.notify(now=T + 4700, take=lambda: [], send=mails.append, state_path=state), True)
	check("two mails", len(mails), 2)
	check("second mail lists both minutes", mails[1].count("mails waited"), 2)
	check("mail names the sender", "alice@example.com" in mails[0] and "postsuper" in mails[0], True)
	sl.get_settings = lambda env: ({"enabled": True, "rate": 30, "per": 1}, [])
	res = sl.status({}, now=T + 5000, take=lambda: [ev(T + 1995), ev(T + 4990, 7)], state_path=state, running=True,
		settings_file=os.path.join(d, "none"))
	check("status: kept + fresh, no duplicates, newest first", [e["time"] for e in res["events"]], [T + 4990, T + 1995, T + 1990, T + 990])
	check("status: day", (res["day"]["minutes"], res["day"]["delayed"], res["day"]["senders"][0]["recipients"]), (4, 22, 22))
	check("status: no warning", res["warnings"], [])
	res = sl.status({}, now=T + 5000 + 86400, take=lambda: [], state_path=state, running=False, settings_file=os.path.join(d, "none"))
	check("status: older than a day dropped", res["day"]["minutes"], 0)
	check("status: not running warns", any("does not run" in w for w in res["warnings"]), True)
	sl.get_settings = lambda env: ({"enabled": True, "rate": 50, "per": 1}, [])
	res = sl.status({}, now=T + 5000, take=lambda: [], state_path=state, running=True, settings_file=os.path.join(d, "none"))
	check("status: other values warn", any("does not use this setting" in w for w in res["warnings"]), True)

print(f"{len(failures)} failed." if failures else "all cases passed.")
sys.exit(1 if failures else 0)
