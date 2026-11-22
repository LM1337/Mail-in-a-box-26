#!/usr/bin/env python3
"""
Offline test of the sending limit (B221): conf/send-limit/sendlimit_common.py,
sendlimit-milter.py (with a stand-in for the Milter module), sendlimit-release.py and
management/send_limit.py -- python3 stdlib only, no box needed.

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
  * the milter's choice: counted mail that does not fit is put on hold (and
    recorded for sendlimit-release.py) while sendlimit-release.py runs, everything is held while
    mail is held; without sendlimit-release.py it waits at most 60 s and is deferred;
  * sendlimit-release.py: the senders in turn (one sender with many mails does not hold
    back the others), the rate kept, its records taken without following a
    link; send_limit.py releases or deletes the held mail of a sender;
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

sys.dont_write_bytecode = True # no __pycache__ in conf/send-limit

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
sys.path.insert(0, os.path.join(ROOT, "management"))

# The milter imports pymilter's module "Milter": a stand-in is enough here.
fake = types.ModuleType("Milter")
fake.Base = object
fake.CONTINUE, fake.ACCEPT, fake.TEMPFAIL = "continue", "accept", "tempfail"
fake.noreply = lambda f: f
sys.modules["Milter"] = fake
fake.QUARANTINE = 0x20


def load(name, file):
	spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "conf", "send-limit", file))
	mod = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(mod)
	return mod


milter = load("sendlimit_milter", "sendlimit-milter.py")
common = sys.modules["sendlimit_common"]
release = load("sendlimit_release", "sendlimit-release.py")
common.log = milter.log = release.log = lambda *a, **k: None

import send_limit as sl # noqa: E402

failures = []


def check(name, got, want):
	if got != want:
		failures.append(name)
		print(f"FAIL {name}: got {got!r}, want {want!r}")


# The token bucket.
L = common.Limiter()
waits = [L.reserve(1, 30, 1, 60, now=100.0) for _ in range(30)]
check("burst of 30 at once", waits, [0.0] * 30)
w = L.reserve(1, 30, 1, 60, now=100.0)
check("31st waits 1/30 s", round(w, 4), round(1 / 30, 4))
w = L.reserve(1, 30, 1, 60, now=100.0)
check("32nd waits 2/30 s", round(w, 4), round(2 / 30, 4))
L = common.Limiter()
waits = [L.reserve(1, 30, 1, 60, now=100.0) for _ in range(30 + 30 * 60)]
check("flood: last one waits 60 s", round(waits[-1], 3), 60.0)
check("flood: next one deferred", L.reserve(1, 30, 1, 60, now=100.0), None)
check("flood: later it fits again", L.reserve(1, 30, 1, 60, now=140.0) is not None, True)
L = common.Limiter()
check("steady rate under the limit never waits", all(L.reserve(1, 30, 1, 60, now=1000 + i * 0.05) == 0 for i in range(2000)), True)
L = common.Limiter()
check("mail of 30 recipients at once", L.reserve(30, 30, 1, 60, now=10.0), 0.0)
check("then a mail of 15 waits 0.5 s", round(L.reserve(15, 30, 1, 60, now=10.0), 3), 0.5)
L = common.Limiter()
check("mail of 5000 recipients, nothing waits: goes out", L.reserve(5000, 30, 1, 60, now=10.0), 0.0)
check("the next is deferred (would wait ~166 s)", L.reserve(1, 30, 1, 60, now=10.0), None)
check("after the bucket refilled it goes", L.reserve(1, 30, 1, 60, now=10.0 + 5000 / 30), 0.0)
L = common.Limiter()
check("1 per hour: first goes", L.reserve(1, 1, 3600, 60, now=0.0), 0.0)
check("1 per hour: second deferred", L.reserve(1, 1, 3600, 60, now=1.0), None)
check("1 per hour: after an hour", L.reserve(1, 1, 3600, 60, now=3600.0), 0.0)
L = common.Limiter()
for _ in range(30 + 30 * 50):
	L.reserve(1, 30, 1, 60, now=0.0)
check("lower rate: the backlog is capped at once", L.reserve(1, 5, 1, 60, now=0.0) is not None, True)

# Which mail counts: SMTP with a login, sendmail (port 0) and SMTP from the
# box itself (loopback); mail from other servers passes uncounted.
check("loopback", [common.is_loopback(x) for x in ("127.0.0.1", "127.9.8.7", "::1", "::ffff:127.0.0.1", "203.0.113.5", "10.0.0.1", "fe80::1%eth0", "", None)],
	[True, True, True, True, False, False, False, False, False])
milter.settings.values, milter.settings.checked = {"enabled": 1, "rate": 1, "per": 3600}, 10 ** 12
milter.stats = milter.Stats()
milter.flag.value, milter.flag.checked = (False, None), 10 ** 12 # sendlimit-release.py does not run


QUARANTINED = []


def session(addr, auth=None, qid="ABCDEF1234", rcpts=1):
	m = milter.SendLimit()
	m.getsymval = lambda k: auth if k == "{auth_authen}" else (qid if k == "i" else None)
	m.setreply = lambda *a: None
	m.quarantine = lambda reason: QUARANTINED.append(qid)
	m.connect("host", 2, addr)
	m.envfrom("<a@example.com>")
	for _ in range(rcpts):
		m.envrcpt("<b@example.org>")
	return m.eom()


milter.limiter = common.Limiter()
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
check("nothing put on hold without sendlimit-release.py", QUARANTINED, [])

# With sendlimit-release.py running: what does not fit is accepted and held.
with tempfile.TemporaryDirectory() as d:
	milter.HELD = os.path.join(d, "held")
	milter.settings.values = {"enabled": 1, "rate": 2, "per": 3600}
	milter.limiter = common.Limiter()
	milter.flag.value, milter.flag.checked = (True, 0), 10 ** 12
	r = [session(("127.0.0.1", 0), qid="AAAA%06d" % i) for i in range(4)]
	check("fits: accepted at once, then held (accepted)", r, ["accept"] * 4)
	check("the two that did not fit are held", QUARANTINED, ["AAAA000002", "AAAA000003"])
	lines = open(milter.HELD).read().splitlines()
	check("held lines for sendlimit-release.py", [common.parse_held(l)["qid"] for l in lines], ["AAAA000002", "AAAA000003"])
	check("held line names the sender", common.parse_held(lines[0])["sender"], "sendmail:a@example.com")
	QUARANTINED.clear()
	milter.limiter = common.Limiter() # room again, but mail is on hold: new mail goes behind it
	milter.flag.value, milter.flag.held_here = (True, 3), 0
	check("while mail is held, new mail is held too", (session(("127.0.0.1", 41010), qid="BBBB000001"), QUARANTINED), ("accept", ["BBBB000001"]))
	QUARANTINED.clear()
	milter.flag.value = (True, 0)
	check("without a queue id it is not held (waits or is deferred)", (session(("127.0.0.1", 41011), qid=None), QUARANTINED), ("accept", []))
	check("a strange queue id is not held", (session(("127.0.0.1", 41012), qid="x y"), QUARANTINED), ("accept", []))
	check("another server is never held", (session(("203.0.113.9", 41013), qid="CCCC000001"), QUARANTINED), ("accept", []))
	os.unlink(milter.HELD)
	os.chmod(d, 0o500)
	if os.geteuid() != 0:
		milter.limiter = common.Limiter()
		milter.limiter.reserve(2, 2, 3600, 60)
		check("held file not writable: deferred instead (never held without a record)", (session(("127.0.0.1", 0), qid="DDDD000001"), QUARANTINED), ("tempfail", []))
	os.chmod(d, 0o700)

# sendlimit-release.py's flag.
with tempfile.TemporaryDirectory() as d:
	f = os.path.join(d, "release")
	check("no flag", common.read_flag(f, now=1000), (False, None))
	open(f, "w").write("1000 7\n")
	check("fresh flag", common.read_flag(f, now=1005), (True, 7))
	check("old flag", common.read_flag(f, now=1100), (False, None))
	open(f, "w").write("junk\n")
	check("broken flag", common.read_flag(f, now=1000), (False, None))

# sendlimit-release.py: the senders in turn, the rate kept.
held = [{"time": 1, "qid": "SPAM%06d" % i, "rcpts": 1, "sender": "spammer@example.com"} for i in range(100)]
held += [{"time": 50, "qid": "GOOD000001", "rcpts": 1, "sender": "alice@example.com"}, {"time": 60, "qid": "GOOD000002", "rcpts": 1, "sender": "bob@example.com"}]
L = common.Limiter()
out, turn = release.pick(held, L, 10, 1, "", now=100.0)
check("one round: 10 mails at 10 a second", len(out), 10)
check("the others are not held back by the spammer", {"GOOD000001", "GOOD000002"} <= {h["qid"] for h in out}, True)
check("spammer gets the rest of the round", sum(1 for h in out if h["sender"] == "spammer@example.com"), 8)
out2, turn = release.pick([h for h in held if h not in out], L, 10, 1, turn, now=100.0)
check("no room in the same instant", out2, [])
out2, turn = release.pick([h for h in held if h not in out], L, 10, 1, turn, now=100.5)
check("half a second later: 5 more", len(out2), 5)
big = [{"time": 1, "qid": "BIGG000001", "rcpts": 500, "sender": "list@example.com"}]
check("a mail bigger than the bucket goes when it is full", len(release.pick(big, common.Limiter(), 10, 1, "", now=0.0)[0]), 1)
sm = release.summary(held, 100)
check("summary by sender, most recipients first", (sm["held"], sm["senders"][0]["sender"], sm["senders"][0]["mails"], len(sm["senders"][0]["qids"])),
	(102, "spammer@example.com", 100, 100))

with tempfile.TemporaryDirectory() as d:
	open(os.path.join(d, "held"), "w").write("10 ABCDEF1234 3 alice@example.com\nbroken line\n20 ZZZZZZZZ99 1 sendmail:x@y\n")
	got = release.take_held(d)
	check("take_held: lines read, broken dropped, file removed", ([h["qid"] for h in got], os.listdir(d)), (["ABCDEF1234", "ZZZZZZZZ99"], []))
	secret = os.path.join(d, "..", "secret-held-" + os.path.basename(d))
	open(secret, "w").write("10 ABCDEF1234 3 alice@example.com\n")
	os.symlink(secret, os.path.join(d, "held"))
	check("take_held: a link is not followed", release.take_held(d), [])
	os.unlink(secret)
	st = os.path.join(d, "state.json")
	release.save_state({"held": got + [{"time": "x", "qid": "../etc", "rcpts": 1, "sender": "a"}], "released": 3, "turn": "a"}, st)
	check("state saved and loaded, bad entries dropped", [h["qid"] for h in release.load_state(st)["held"]], ["ABCDEF1234", "ZZZZZZZZ99"])

# send_limit.py: release or delete held mail.
heldjson = {"held": 3, "recipients": 3, "senders": [{"sender": "spammer@example.com", "mails": 2, "recipients": 2, "oldest": 1, "qids": ["SPAM000001", "SPAM000002"]},
	{"sender": "alice@example.com", "mails": 1, "recipients": 1, "oldest": 2, "qids": ["GOOD000001", "../../x"]}]}
calls = []


class P:
	returncode = 0
	stderr = ""


def run(argv, **kw):
	calls.append((argv, kw.get("input")))
	return P()


r = sl.act_on_held("delete", "spammer@example.com", run=run, held=heldjson)
check("delete one sender", (r["mails"], calls), (2, [(["postsuper", "-d", "-"], "SPAM000001\nSPAM000002\n")]))
calls.clear()
r = sl.act_on_held("release", None, run=run, held=heldjson)
check("release all: bad ids dropped, then postqueue -i each", (r["mails"], [c[0] for c in calls]),
	(3, [["postsuper", "-H", "-"], ["postqueue", "-i", "SPAM000001"], ["postqueue", "-i", "SPAM000002"], ["postqueue", "-i", "GOOD000001"]]))
bad = 0
for a, snd in (("bounce", None), ("delete", "nobody@example.com"), ("delete", "a b"), ("delete", 5)):
	try:
		sl.act_on_held(a, snd, run=run, held=heldjson)
	except sl.SendLimitError:
		bad += 1
check("bad actions and senders refused", bad, 4)
try:
	sl.act_on_held("delete", None, run=run, held=None) if False else sl.held_qids(None, held=None)
	failures.append("no list accepted")
except sl.SendLimitError:
	pass
milter.settings = common.Settings()

# The milter's settings file.
with tempfile.TemporaryDirectory() as d:
	SET = os.path.join(d, "settings")
	check("no file: defaults", common.Settings.read(SET), {"enabled": 1, "rate": 30, "per": 1})
	open(SET, "w").write("# c\nenabled 0\nrate 0\nper 999999\nbogus 4\nrate x\n")
	check("file: clamped, broken ignored", common.Settings.read(SET), {"enabled": 0, "rate": 1, "per": 86400})
	open(SET, "w").write(sl.render_settings_file({"enabled": True, "rate": 120, "per": 60}))
	check("written by send_limit.py", common.Settings.read(SET), {"enabled": 1, "rate": 120, "per": 60})
	check("read back by send_limit.py", sl.read_settings_file(SET), {"enabled": True, "rate": 120, "per": 60})
	check("send_limit.py without file", sl.read_settings_file(os.path.join(d, "none")), {"enabled": True, "rate": 30, "per": 1})

check("sender names", [common.sender_name(s) for s in ("<a@b.c>", "", "<>", "x y=z\n", "a" * 300)],
	["a@b.c", "<>", "<>", "x?y?z", "a" * 200])

# The minute's line of the milter, read back.
with tempfile.TemporaryDirectory() as d:
	milter.EVENTS = os.path.join(d, "events")
	st = milter.Stats()
	st.add("alice@example.com", 3, "delayed", 0.5)
	st.add("alice@example.com", 2, "delayed", 12.2)
	st.add("sendmail:www-data@box.example.com", 1, "deferred")
	st.add("bob@example.com", 1, "passed")
	st.add("carol@example.com", 4, "held")
	s = common.Settings()
	s.values, s.checked = {"enabled": 1, "rate": 30, "per": 1}, 10 ** 12
	milter.log = lambda *a, **k: None
	st.flush(s)
	st.flush(s) # nothing waited since: no line
	lines = open(milter.EVENTS).read().splitlines()
	check("one line per minute with waits", len(lines), 1)
	e = sl.parse_event(lines[0])
	check("line read back", e and (e["rate"], e["per"], e["delayed"], e["deferred"], e["passed"], e["max_wait"], e["others"], e["held"]), (30, 1, 2, 1, 1, 13, 0, 1))
	check("senders read back", e and e["senders"], [{"sender": "alice@example.com", "mails": 2, "recipients": 5},
		{"sender": "carol@example.com", "mails": 1, "recipients": 4}, {"sender": "sendmail:www-data@box.example.com", "mails": 1, "recipients": 1}])
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
	ev = lambda t, n=5: {"time": t, "rate": 30, "per": 1, "delayed": n, "deferred": 0, "passed": 1, "max_wait": 2, "others": 0, "held": 1,
		"senders": [{"sender": "alice@example.com", "mails": n, "recipients": n}]}
	check("nothing: no mail", sl.notify(now=T + 1000, take=lambda: [], send=mails.append, state_path=state), False)
	check("first event: mailed", sl.notify(now=T + 1000, take=lambda: [ev(T + 990)], send=mails.append, state_path=state), True)
	check("within the hour: waits", sl.notify(now=T + 2000, take=lambda: [ev(T + 1990), ev(T + 1995)], send=mails.append, state_path=state), False)
	check("after the hour: together", sl.notify(now=T + 4700, take=lambda: [], send=mails.append, state_path=state), True)
	check("two mails", len(mails), 2)
	check("second mail lists both minutes", mails[1].count("mails put on hold"), 2)
	check("mail names the sender and how to delete", "alice@example.com" in mails[0] and "--delete" in mails[0], True)
	check("mail lists the held mail", "On hold now: 3 mails" in sl.message([ev(T)], 0, heldjson), True)
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
