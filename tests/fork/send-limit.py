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
  * the listener of the box's own reports: its recipients table written with
    the settings file, Postfix reloaded only when it changes; the milter
    probe (answer, silence, nothing listening); watch_milter() mails once
    after 4 minutes without an answer and once when it answers again;
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
L.reserve(5000, 30, 1, 60, now=10.0)
check("it pays in full: a small mail 40 s later does not fit within 60 s", L.reserve(1, 30, 1, 60, now=50.0), None)
check("it fits once its recipients are paid for", L.reserve(1, 30, 1, 60, now=10.0 + 5000 / 30 - 0.5), 0.0)
L = common.Limiter()
for i in range(100): # a trickle of other mail at 500 an hour: one every 30 s
	L.reserve(1, 500, 3600, 60, now=i * 30.0)
check("a big mail behind a trickle goes at once (no starvation)", L.reserve(600, 500, 3600, 60, now=3000.0), 0.0)
check("and the next mail waits until it is paid for", L.reserve(1, 500, 3600, 120, now=3000.0), None)
L = common.Limiter()
L.charge(30, 30, 1, now=0.0)
check("charge(): passes elsewhere take from the bucket", round(L.reserve(1, 30, 1, 60, now=0.0), 4), round(1 / 30, 4))
L = common.Limiter()
check("1 per hour: first goes", L.reserve(1, 1, 3600, 60, now=0.0), 0.0)
check("1 per hour: second deferred", L.reserve(1, 1, 3600, 60, now=1.0), None)
check("1 per hour: after an hour", L.reserve(1, 1, 3600, 60, now=3600.0), 0.0)
L = common.Limiter()
for _ in range(30 + 30 * 50):
	L.reserve(1, 30, 1, 60, now=0.0)
check("lower rate: the backlog is capped at once", L.reserve(1, 5, 1, 60, now=0.0) is not None, True)
L = common.Limiter()
check("1 per hour, then 30 a second: first goes", L.reserve(1, 1, 3600, 0, now=0.0), 0.0)
check("1 per hour: second held", L.reserve(1, 1, 3600, 0, now=1.0), None)
check("30 a second restored: the next mail goes at once (the mail counted, not a full bucket)",
	L.reserve(1, 30, 1, 0, now=3.0), 0.0)
check("and 28 more in the same second", [L.reserve(1, 30, 1, 0, now=3.0) for _ in range(28)], [0.0] * 28)
check("the 31st in that second does not fit", L.reserve(1, 30, 1, 0, now=3.0), None)
L = common.Limiter()
for _ in range(600):
	L.reserve(1, 1000, 3600, 0, now=0.0)
check("long limit lowered below what went out: full at once", L.reserve(1, 500, 3600, 0, now=10.0), None)
check("long limit raised: what went out still counts", L.reserve(1, 2000, 3600, 0, now=20.0), 0.0)
L = common.Limiter()
for _ in range(800):
	L.reserve(1, 1000, 3600, 0, now=0.0)
check("longer period: the 800 mails still count, 200 more fit", [L.reserve(1, 1000, 7200, 0, now=0.0) for _ in range(200)], [0.0] * 200)
check("longer period: the 1001st does not", L.reserve(1, 1000, 7200, 0, now=0.0), None)

# Which mail counts: SMTP with a login, sendmail (port 0) and SMTP from the
# box itself (loopback); mail from other servers passes uncounted.
check("loopback", [common.is_loopback(x) for x in ("127.0.0.1", "127.9.8.7", "::1", "::ffff:127.0.0.1", "203.0.113.5", "10.0.0.1", "fe80::1%eth0", "", None)],
	[True, True, True, True, False, False, False, False, False])
milter.settings.values, milter.settings.checked = {"enabled": 1, "rate": 1, "per": 3600}, 10 ** 12
milter.stats = milter.Stats()
milter.flag.value, milter.flag.checked = (False, None, None), 10 ** 12 # sendlimit-release.py does not run


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
	milter.HELD_DIR = os.path.join(d, "held.d")
	milter.PASSED = os.path.join(d, "passed")
	milter.passed = milter.Passed()
	milter.settings.values = {"enabled": 1, "rate": 2, "per": 3600}
	milter.limiter = common.Limiter()
	milter.flag.value, milter.flag.checked = (True, 0, False), 10 ** 12
	r = [session(("127.0.0.1", 0), qid="AAAA%06d" % i) for i in range(4)]
	check("fits: accepted at once, then held (accepted)", r, ["accept"] * 4)
	check("the two that did not fit are held", QUARANTINED, ["AAAA000002", "AAAA000003"])
	check("a file per held mail for the release service", sorted(os.listdir(milter.HELD_DIR)), ["AAAA000002", "AAAA000003"])
	got = release.take_held(d)
	check("the release service reads and removes them", ([h["qid"] for h in sorted(got, key=lambda h: h["qid"])], os.listdir(milter.HELD_DIR)), (["AAAA000002", "AAAA000003"], []))
	check("held record names the sender", got[0]["sender"], "sendmail:a@example.com")
	milter.passed.write()
	check("passed: the two that went at once", release.take_passed(d), (os.getpid(), 2))
	QUARANTINED.clear()
	milter.limiter = common.Limiter() # room again, but mail is on hold: new mail goes behind it
	milter.flag.value, milter.flag.held_here = (True, 3, False), 0
	check("while mail is held, new mail is held too", (session(("127.0.0.1", 41010), qid="BBBB000001"), QUARANTINED), ("accept", ["BBBB000001"]))
	QUARANTINED.clear()
	milter.limiter = common.Limiter()
	milter.flag.value, milter.flag.held_here = (True, 0, True), 0
	check("brake on: even mail that fits is held", (session(("127.0.0.1", 41020), qid="EEEE000001"), QUARANTINED), ("accept", ["EEEE000001"]))
	QUARANTINED.clear()
	milter.ADMIN = "administrator@box.example.com"
	milter.settings.values = dict(milter.settings.values, report="reports@example.net")

	def to(addr, rcpt, auth=None, qid="FFFF000001"):
		m = milter.SendLimit()
		m.getsymval = lambda k: auth if k == "{auth_authen}" else (qid if k == "i" else None)
		m.setreply = lambda *a: None
		m.quarantine = lambda reason: QUARANTINED.append(qid)
		m.connect("host", 2, addr)
		m.envfrom("<administrator@box.example.com>")
		for r in rcpt:
			m.envrcpt("<%s>" % r)
		return m.eom()
	check("brake on: the box's mail to administrator@ goes", (to(("127.0.0.1", 41021), ["Administrator@box.example.com"]), QUARANTINED), ("accept", []))
	check("brake on: ... and to the report recipient", (to(("127.0.0.1", 41022), ["reports@example.net"]), QUARANTINED), ("accept", []))
	check("brake on: to the admin and someone else is held", (to(("127.0.0.1", 41023), ["administrator@box.example.com", "x@example.org"], qid="FFFF000002"), QUARANTINED), ("accept", ["FFFF000002"]))
	QUARANTINED.clear()
	check("brake on: to the admin with a login (a user) is held", (to(("203.0.113.5", 41024), ["administrator@box.example.com"], auth="u@box.example.com", qid="FFFF000003"), QUARANTINED), ("accept", ["FFFF000003"]))
	QUARANTINED.clear()
	milter.flag.value = (True, 0, False)
	check("without a queue id it is not held (waits or is deferred)", (session(("127.0.0.1", 41011), qid=None), QUARANTINED), ("accept", []))
	check("a strange queue id is not held", (session(("127.0.0.1", 41012), qid="x y"), QUARANTINED), ("accept", []))
	check("another server is never held", (session(("203.0.113.9", 41013), qid="CCCC000001"), QUARANTINED), ("accept", []))
	import shutil
	shutil.rmtree(milter.HELD_DIR)
	os.chmod(d, 0o500)
	if os.geteuid() != 0:
		milter.limiter = common.Limiter()
		milter.limiter.reserve(2, 2, 3600, 60)
		check("held file not writable: deferred instead (never held without a record)", (session(("127.0.0.1", 0), qid="DDDD000001"), QUARANTINED), ("tempfail", []))
	os.chmod(d, 0o700)

# sendlimit-release.py's flag.
with tempfile.TemporaryDirectory() as d:
	f = os.path.join(d, "release")
	check("no flag", common.read_flag(f, now=1000), (False, None, None))
	open(f, "w").write("1000 7 1\n")
	check("fresh flag", common.read_flag(f, now=1005), (True, 7, True))
	check("old flag", common.read_flag(f, now=1100), (False, None, None))
	open(f, "w").write("1000 7\n")
	check("flag without the brake field", common.read_flag(f, now=1000), (False, None, None))
	open(f, "w").write("junk\n")
	check("broken flag", common.read_flag(f, now=1000), (False, None, None))

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
ids = {"GOOD000001": 50, "SPAM000001": 1, "HAND000001": 1, "LATE000001": 9000, "SLOW000001": 1000, "OLD0000001": 1}
check("verified: in the hold queue and had arrived when recorded",
	[release.verified(h, ids) for h in ({"qid": "GOOD000001", "time": 55}, {"qid": "GOOD000002", "time": 60}, {"qid": "LATE000001", "time": 5000},
		{"qid": "SLOW000001", "time": 1000 + 3600}, {"qid": "OLD0000001", "time": 1 + release.MAX_AGE + 1})], [True, False, False, True, False])
sm = release.summary(held, 100)
check("summary by sender, most recipients first", (sm["held"], sm["senders"][0]["sender"], sm["senders"][0]["mails"], len(sm["senders"][0]["qids"])),
	(102, "spammer@example.com", 100, 100))

with tempfile.TemporaryDirectory() as d:
	hd = os.path.join(d, "held.d")
	os.mkdir(hd)
	open(os.path.join(hd, "ABCDEF1234"), "w").write("10 3 alice@example.com\n")
	open(os.path.join(hd, "ZZZZZZZZ99"), "w").write("20 1 sendmail:x@y\n")
	open(os.path.join(hd, "BROKEN0001"), "w").write("broken line\n")
	open(os.path.join(hd, ".QQQQQQ0001.tmp"), "w").write("30 1 x\n")
	open(os.path.join(hd, "../etc"[:0] + "not-a-qid!"), "w").write("30 1 x\n")
	check("pending_held: the records not taken yet, temporary files and others not",
		release.pending_held(d), {"ABCDEF1234", "ZZZZZZZZ99", "BROKEN0001"})
	got = release.take_held(d)
	check("pending_held: none after take_held", release.pending_held(d), set())
	check("take_held: records read, broken dropped and removed, others left",
		(sorted(h["qid"] for h in got), sorted(os.listdir(hd))), (["ABCDEF1234", "ZZZZZZZZ99"], [".QQQQQQ0001.tmp", "not-a-qid!"]))
	secret = os.path.join(d, "..", "secret-held-" + os.path.basename(d))
	open(secret, "w").write("10 3 alice@example.com\n")
	os.symlink(secret, os.path.join(hd, "LINK000001"))
	check("take_held: a link is not followed", release.take_held(d), [])
	os.unlink(secret)
	import shutil
	shutil.rmtree(hd)
	os.symlink(d, hd)
	check("take_held: held.d as a link is not followed", release.take_held(d), [])
	os.unlink(hd)
	st = os.path.join(d, "state.json")
	release.save_state({"held": got + [{"time": "x", "qid": "../etc", "rcpts": 1, "sender": "a"}], "released": 3, "turn": "a"}, st)
	check("state saved and loaded, bad entries dropped", sorted(h["qid"] for h in release.load_state(st)["held"]), ["ABCDEF1234", "ZZZZZZZZ99"])

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
check("delete one sender (hold and deferred queue only)", (r["mails"], calls), (2, [(["postsuper", "-d", "-", "hold", "deferred"], "SPAM000001\nSPAM000002\n")]))
calls.clear()
r = sl.act_on_held("release", None, run=run, held=heldjson)
check("release all: bad ids dropped, then postqueue -i each", (r["mails"], [c[0] for c in calls]),
	(3, [["postsuper", "-H", "-", "hold"], ["postqueue", "-i", "SPAM000001"], ["postqueue", "-i", "SPAM000002"], ["postqueue", "-i", "GOOD000001"]]))
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
	check("no file: defaults", common.Settings.read(SET), {"enabled": 1, "rate": 30, "per": 1, "stop": 0, "brake_rate": 10, "brake_per": 60, "calm": 30, "long_enabled": 1, "long_rate": 1000, "long_per": 3600})
	open(SET, "w").write("# c\nenabled 0\nrate 0\nper 999999\nbogus 4\nrate x\nlong_per 5\n")
	check("file: clamped, broken ignored", common.Settings.read(SET), dict({"enabled": 1, "rate": 30, "per": 1, "stop": 0, "brake_rate": 10, "brake_per": 60, "calm": 30, "long_enabled": 1, "long_rate": 1000, "long_per": 3600}, enabled=0, rate=1, per=86400, long_per=60))
	vals = dict(sl.DEFAULTS, rate=120, per=60, stop=True, brake_rate=5, brake_per=600, calm=90, long_enabled=False, long_rate=50, long_per=86400)
	open(SET, "w").write(sl.render_settings_file(vals, "Admin@Example.org"))
	check("written by send_limit.py", common.Settings.read(SET), {"enabled": 1, "rate": 120, "per": 60, "stop": 1, "brake_rate": 5, "brake_per": 600, "calm": 90, "long_enabled": 0, "long_rate": 50, "long_per": 86400, "report": "admin@example.org"})
	check("read back by send_limit.py", sl.read_settings_file(SET), vals)
	check("send_limit.py without file", sl.read_settings_file(os.path.join(d, "none")), sl.DEFAULTS)
	check("a strange report address is left out", "report" in sl.render_settings_file(sl.DEFAULTS, "x y@z"), False)

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
check("defaults", sl.validate_settings({}), (sl.DEFAULTS, []))
check("values", sl.validate_settings({"enabled": "0", "rate": "100", "per": "60", "stop": "1", "brake_rate": "1", "brake_per": "3600", "calm": "5", "long_enabled": "0", "long_rate": "200", "long_per": "7200"})[0],
	{"enabled": False, "rate": 100, "per": 60, "stop": True, "brake_rate": 1, "brake_per": 3600, "calm": 5, "long_enabled": False, "long_rate": 200, "long_per": 7200})
bad = 0
for v in ({"rate": "0"}, {"rate": "100001"}, {"per": "0"}, {"per": "3601"}, {"rate": "1.5"}, {"rate": "x"}, {"enabled": "maybe"}, {"rate": True},
		{"stop": "2"}, {"brake_rate": "0"}, {"brake_per": "86401"}, {"calm": "0"}, {"calm": "1441"}):
	try:
		sl.validate_settings(v)
	except sl.SendLimitError:
		bad += 1
check("strict errors", bad, 13)
out, warn = sl.validate_settings({"rate": "x", "per": 5}, strict=False)
check("loose: default and warning", (out, len(warn)), (dict(sl.DEFAULTS, per=5), 1))

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
	st2 = os.path.join(d, "state2.json")

	def failing(text):
		raise RuntimeError("451 4.7.1")
	import io, contextlib
	with contextlib.redirect_stderr(io.StringIO()):
		check("failed send: not sent", sl.notify(now=T + 9000, take=lambda: [ev(T + 8990)], send=failing, state_path=st2), False)
	check("failed send: the minute stays pending", len(sl.load_state(st2)["pending"]), 1)
	check("next run sends it", sl.notify(now=T + 9100, take=lambda: [], send=mails.append, state_path=st2), True)
	st3 = os.path.join(d, "state3.json")
	brake = dict(heldjson, brake=True, brake_since=T + 9500, stop=False, brake_rate=10, brake_per=60, calm=30)
	sl.notify(now=T + 9400, take=lambda: [ev(T + 9390)], send=mails.append, state_path=st3)
	n = len(mails)
	check("a new brake is mailed at once, within the hour", sl.notify(now=T + 9501, take=lambda: [], send=mails.append, state_path=st3, held=brake), True)
	check("the mail says the brake is on", "THE BRAKE IS ON" in mails[-1] and "10 mails in 60 seconds" in mails[-1], True)
	check("the same brake is not mailed again", sl.notify(now=T + 9600, take=lambda: [ev(T + 9590)], send=mails.append, state_path=st3, held=brake), False)
	check("stop: the mail says nothing is sent", "sends nothing until you end the brake" in sl.message([], 0, dict(brake, stop=True)), True)
	sl.END = os.path.join(d, "end")
	check("end: the request file is written", (sl.act_on_held("end")["action"], os.path.exists(sl.END)), ("end", True))
	check("mail lists the held mail", "On hold now: 3 mails" in sl.message([ev(T)], 0, heldjson), True)
	sl.get_settings = lambda env: (dict(sl.DEFAULTS), [])
	res = sl.status({}, now=T + 5000, take=lambda: [ev(T + 1995), ev(T + 4990, 7)], state_path=state, running=True,
		release_running=True, settings_file=os.path.join(d, "none"))
	check("status: kept + fresh, no duplicates, newest first", [e["time"] for e in res["events"]], [T + 4990, T + 1995, T + 1990, T + 990])
	check("status: day", (res["day"]["minutes"], res["day"]["delayed"], res["day"]["senders"][0]["recipients"]), (4, 22, 22))
	check("status: no warning", res["warnings"], [])
	res = sl.status({}, now=T + 5000, take=lambda: [], state_path=state, running=True, release_running=False,
		settings_file=os.path.join(d, "none"))
	check("status: the release service stopped while the milter runs warns (B226)",
		(res["running"], res["release_running"], any(sl.RELEASE_SERVICE + " does not run" in w for w in res["warnings"])), (True, False, True))
	asked = []
	orig_running = sl.service_running
	sl.service_running = lambda unit=sl.SERVICE: asked.append(unit) or (unit == sl.SERVICE)
	res = sl.status({}, now=T + 5000, take=lambda: [], state_path=state, settings_file=os.path.join(d, "none"))
	sl.service_running = orig_running
	check("status: both services are asked, each for itself (B226)",
		(sorted(asked), res["running"], res["release_running"]), (sorted([sl.SERVICE, sl.RELEASE_SERVICE]), True, False))
	res = sl.status({}, now=T + 5000 + 86400, take=lambda: [], state_path=state, running=False, release_running=True, settings_file=os.path.join(d, "none"))
	check("status: older than a day dropped", res["day"]["minutes"], 0)
	check("status: not running warns", any("does not run" in w for w in res["warnings"]), True)
	sl.get_settings = lambda env: (dict(sl.DEFAULTS, rate=50), [])
	res = sl.status({}, now=T + 5000, take=lambda: [], state_path=state, running=True, release_running=True, settings_file=os.path.join(d, "none"))
	check("status: other values warn", any("does not use this setting" in w for w in res["warnings"]), True)

# The listener of the box's own reports: its recipients table, written with the
# settings file; Postfix is reloaded only when the table changes.
with tempfile.TemporaryDirectory() as d:
	os.chmod(d, 0o755)
	check("admin recipients: admin and report, lower case, once",
		[l for l in sl.render_admin_recipients("administrator@Box.example.com", "Ops@other.example").splitlines() if not l.startswith("#")],
		["administrator@box.example.com\tOK", "ops@other.example\tOK"])
	check("admin recipients: same address once, a bad one left out",
		[l for l in sl.render_admin_recipients("administrator@box.example.com", "administrator@box.example.com").splitlines() if not l.startswith("#")]
		+ [l for l in sl.render_admin_recipients("administrator@box.example.com", "a b@x\tOK").splitlines() if not l.startswith("#")],
		["administrator@box.example.com\tOK", "administrator@box.example.com\tOK"])
	reloads = []
	saved = sl.report_recipient
	sl.report_recipient = lambda env: "ops@other.example"
	env = {"PRIMARY_HOSTNAME": "box.example.com"}
	rc = os.path.join(d, "rcpts")
	sl.apply_config(env, dict(sl.DEFAULTS), os.path.join(d, "settings"), rc, reload=lambda: reloads.append(1))
	sl.apply_config(env, dict(sl.DEFAULTS), os.path.join(d, "settings"), rc, reload=lambda: reloads.append(1))
	check("apply: table written, Postfix reloaded once", (open(rc).read().count("\tOK"), len(reloads)), (2, 1))
	sl.report_recipient = lambda env: "new@other.example"
	sl.apply_config(env, dict(sl.DEFAULTS), os.path.join(d, "settings"), rc, reload=lambda: reloads.append(1))
	check("apply: new report recipient, reloaded again", ("new@other.example\tOK" in open(rc).read(), len(reloads)), (True, 2))
	sl.report_recipient = saved

# milter_answers(): a milter that answers Postfix's first question, one that
# accepts the connection and says nothing (stopped or hung), none.
import socket, struct, threading
def fake_milter(answer):
	srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(4)
	def run():
		while True:
			try:
				c, _ = srv.accept()
			except OSError:
				return
			if answer:
				c.recv(64)
				body = b"O" + struct.pack("!III", 6, 0, 0)
				c.sendall(struct.pack("!I", len(body)) + body)
			threading.Timer(3, c.close).start()
	threading.Thread(target=run, daemon=True).start()
	return srv
up, mute = fake_milter(True), fake_milter(False)
free = socket.socket(); free.bind(("127.0.0.1", 0)); free_port = free.getsockname()[1]; free.close()
check("probe: an answering milter", sl.milter_answers(up.getsockname(), timeout=2), True)
check("probe: a milter that says nothing", sl.milter_answers(mute.getsockname(), timeout=1), False)
check("probe: nothing listening", sl.milter_answers(("127.0.0.1", free_port), timeout=1), False)
up.close(); mute.close()

# watch_milter(): a mail after MILTER_GRACE seconds without an answer, once;
# a short gap is not mailed; a mail when it answers again; a failed send is tried again.
with tempfile.TemporaryDirectory() as d:
	st = os.path.join(d, "milter.json")
	sent = []
	send = lambda text, subject: sent.append(subject)
	w = lambda now, ok, snd=send: sl.watch_milter(now=now, probe=lambda: ok, send=snd, state_path=st, waiting=lambda: 7)
	check("watch: up, nothing", (w(T, True), sent), (None, []))
	check("watch: first miss, no mail yet", (w(T + 300, False), sent), (None, []))
	check("watch: answers again before the grace, no mail", (w(T + 400, True), sent), (None, []))
	w(T + 1000, False)
	def broken(text, subject):
		raise OSError("refused")
	check("watch: down past the grace, send fails: tried again", w(T + 1000 + sl.MILTER_GRACE, False, broken), None)
	check("watch: down past the grace: mailed", (w(T + 1300 + sl.MILTER_GRACE, False), sent), ("down", [sl.MILTER_SUBJECT]))
	check("watch: still down: not again", (w(T + 1600 + sl.MILTER_GRACE, False), len(sent)), (None, 1))
	check("watch: answers again: mailed", (w(T + 1900 + sl.MILTER_GRACE, True), len(sent)), ("up", 2))
	check("watch: up again: nothing", (w(T + 2200 + sl.MILTER_GRACE, True), len(sent)), (None, 2))

# Turned off, the milter is taken out of Postfix's way (apply_postfix), and the
# setup scripts write the same values as send_limit.POSTFIX.
calls = []
class P:
	def __init__(self, out="", rc=0): self.stdout, self.stderr, self.returncode = out, "", rc
def fake_run(have):
	def run(cmd, **kw):
		calls.append(cmd)
		if cmd[:2] == ["postconf", "-h"]:
			return P("\n".join(have[k] for k in cmd[2:]) + "\n")
		return P()
	return run
calls.clear()
check("postfix: already on, nothing done", (sl.apply_postfix(True, run=fake_run(sl.POSTFIX[True])), len(calls)), (False, 1))
calls.clear()
check("postfix: turned off", sl.apply_postfix(False, run=fake_run(sl.POSTFIX[True])), True)
check("postfix: off values set, then reload", (calls[1][:2], sorted(calls[1][2:]), calls[2]),
	(["postconf", "-e"], sorted(f"{k}={v}" for k, v in sl.POSTFIX[False].items()), ["postfix", "reload"]))
check("postfix: off has no 8895", any("8895" in v for v in sl.POSTFIX[False].values()), False)
def no_postfix(cmd, **kw):
	raise FileNotFoundError("postconf")
check("postfix: no Postfix, nothing", sl.apply_postfix(True, run=no_postfix), False)
setup = open(os.path.join(HERE, "..", "..", "setup", "dkim.sh")).read() + open(os.path.join(HERE, "..", "..", "setup", "mail-postfix.sh")).read()
check("setup: the milter value of send_limit.POSTFIX", 'sendlimit_milter="' + sl.SL_MILTER + '"' in setup and '"sendlimit_submission_milters=' + sl.POSTFIX[True]["sendlimit_submission_milters"] + '"' in setup, True)
check("setup: the off values of send_limit.POSTFIX", all(x in setup for x in ('"non_smtpd_milters=' + sl.POSTFIX[False]["non_smtpd_milters"] + '"',
	'"sendlimit_submission_milters=' + sl.POSTFIX[False]["sendlimit_submission_milters"] + '"', "smtpd_milter_maps= ", "smtpd_milter_maps=" + sl.POSTFIX[True]["smtpd_milter_maps"])), True)
with tempfile.TemporaryDirectory() as d:
	os.chmod(d, 0o755)
	order = []
	saved = sl.report_recipient
	sl.report_recipient = lambda env: None
	f = os.path.join(d, "settings")
	sl.apply_config({}, dict(sl.DEFAULTS, enabled=False), f, postfix=lambda on: order.append(("postfix", on, open(f).read().count("enabled 0") if os.path.exists(f) else None)))
	sl.apply_config({}, dict(sl.DEFAULTS), f, postfix=lambda on: order.append(("postfix", on, open(f).read().count("enabled 0"))))
	check("apply: off: Postfix first, on: the file first", order, [("postfix", False, None), ("postfix", True, 0)])
	sl.report_recipient = saved
	st = os.path.join(d, "milter.json")
	sl.watch_milter(now=T, probe=lambda: False, send=lambda t, s: None, state_path=st)
	check("watch: turned off clears a miss, no mail", (sl.watch_milter(now=T + 999, probe=lambda: False, send=lambda t, s: failures.append("mailed while off"), state_path=st, enabled=False),
		sl.load_milter_state(st)["down_since"]), (None, None))

# The long limit (a steady flood below the short one): a mail must fit both
# buckets, nothing is reserved when it does not, and the milter holds it.
S1, L1 = common.Limiter(), common.Limiter()
pairs = [(S1, 30, 1), (L1, 5, 3600)]
check("both limits: 5 fit", [common.reserve_all(pairs, 1, 0, now=0.0) for _ in range(5)], [0.0] * 5)
tat_before = S1.tat
check("the 6th does not fit the long one", common.reserve_all(pairs, 1, 0, now=0.5), None)
check("nothing reserved in the short one then", S1.tat, tat_before)
check("over_limits names the long one", common.over_limits(pairs, 1, now=0.5), [(5, 3600)])
check("describe_limit", [common.describe_limit(500, 3600), common.describe_limit(30, 1), common.describe_limit(10, 60), common.describe_limit(100, 7200)],
	["500 mails in 1 hour", "30 mails in 1 s", "10 mails in 1 minute", "100 mails in 2 hours"])
check("limit_pairs: long limit off", len(common.limit_pairs({"rate": 30, "per": 1, "long_enabled": 0, "long_rate": 5, "long_per": 3600}, S1, L1)), 1)
check("limit_pairs: long limit on", len(common.limit_pairs(dict(common.DEFAULTS), S1, L1)), 2)
held6 = [{"qid": "Q%05d" % i, "sender": "s%d" % (i % 2), "rcpts": 1, "time": i} for i in range(6)]
check("pick: the long limit caps the release", len(release.pick(held6, common.Limiter(), 100, 1, "", now=0.0, also=[(common.Limiter(), 4, 3600)])[0]), 4)
check("pick: without it all go", len(release.pick(held6, common.Limiter(), 100, 1, "", now=0.0)[0]), 6)
try:
	sl.validate_settings({"long_per": "59"})
	check("long_per below 60 refused", "accepted", "SendLimitError")
except sl.SendLimitError:
	check("long_per below 60 refused", "SendLimitError", "SendLimitError")
with tempfile.TemporaryDirectory() as d:
	milter.HELD_DIR = os.path.join(d, "held.d")
	milter.PASSED = os.path.join(d, "passed")
	for on, want in ((1, ["LLLL000003", "LLLL000004"]), (0, [])):
		milter.passed = milter.Passed()
		milter.settings.values = {"enabled": 1, "rate": 30, "per": 1, "long_enabled": on, "long_rate": 3, "long_per": 3600}
		milter.limiter, milter.long_limiter = common.Limiter(), common.Limiter()
		milter.flag.value, milter.flag.checked, milter.flag.held_here = (True, 0, False), 10 ** 12, 0
		QUARANTINED.clear()
		r = [session(("127.0.0.1", 0), qid="LLLL%06d" % i) for i in range(5)]
		check(f"milter, long limit {'on' if on else 'off'}: held", (r, QUARANTINED), (["accept"] * 5, want))
		if on:
			check("the direct passes are written before the held record", release.take_passed(d), (os.getpid(), 3))
		release.take_held(d)

# The brake's bucket starts in debt by one period (sendlimit-release.py):
# nothing goes in the brake's first brake_per seconds, also no big mail.
B = common.Limiter()
B.charge(2 * 10, 10, 60, now=0.0)
check("brake start: a mail of 40 waits", (B.reserve(40, 10, 60, 0, now=0.0), B.reserve(40, 10, 60, 0, now=59.0)), (None, None))
check("brake start: it goes after one period", B.reserve(40, 10, 60, 0, now=60.0), 0.0)
B = common.Limiter()
B.charge(2 * 10, 10, 60, now=0.0)
check("brake start: the first small mail after about brake_per", [t for t in range(0, 200) if B.reserve(1, 10, 60, 0, now=float(t)) is not None][:2], [66, 72])

print(f"{len(failures)} failed." if failures else "all cases passed.")
sys.exit(1 if failures else 0)
