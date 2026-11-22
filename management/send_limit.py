#!/usr/local/lib/mailinabox/env/bin/python3
#
# The sending limit of the box (fork, B221).
#
# The Postfix milter conf/send-limit/sendlimit-milter.py (service miab-sendlimit, see
# setup/mail-postfix.sh) lets at most RATE mails within PER seconds go out
# (each recipient counts as one mail) of all mail sent through the
# submission ports, sendmail and SMTP from the box itself (127.0.0.0/8, ::1).
# A mail that does not fit is accepted and put on hold; the release service
# conf/send-limit/sendlimit-release.py (miab-sendlimit-release, root) releases held
# mail at the limit, the senders in turn, and lists it in
# /run/miab-sendlimit/held.json. Without the release service a mail waits at
# most 60 s and is then deferred with a temporary error. Each minute in
# which mail waited or was held, the milter adds a line to its events file:
#
#   <time> <rate> <per> <delayed> <deferred> <passed> <max wait> <others> <held> <sender>=<mails>/<recipients>...
#
#   send_limit.py --release [SENDER]  releases the held mail (of SENDER) now
#   send_limit.py --delete SENDER|--all  deletes held mail (of SENDER)
#
#   send_limit.py --notify   (cron, every 5 minutes) mails new events to the
#                            recipient of the box's reports (System >
#                            Notifications), at most one mail an hour, and
#                            keeps the events of the last 7 days for the
#                            control panel
#   send_limit.py --status   the setting and the events of the last 24 hours
#   send_limit.py --apply    (setup) writes the settings file of the milter
#                            from settings.yaml
#
# The setting is part of System > Intrusion Detection and Prevention (the API
# /system/send-limit), in $STORAGE_ROOT/settings.yaml as "send_limit" (only
# values that differ from the defaults): "enabled", "rate" (mails) and "per"
# (seconds).
#
# The state directory belongs to the milter's dynamic user: root opens the
# events file there without following links, after renaming it, so the
# milter starts a new one.

import json
import os
import re
import stat
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = "/usr/local/lib/mailinabox/miab-sendlimit/settings"
STATE_DIR = "/var/lib/miab-sendlimit"
EVENTS = "events"
NOTIFY_STATE = "/var/lib/mailinabox/send-limit-notify.json"
NOTIFY_INTERVAL = 3600 # seconds between two mails
KEEP = 7 * 86400 # seconds of events kept for the control panel
MAX_KEPT = 5000 # events kept at most
MAX_PENDING = 500 # events kept for the next mail
MAX_READ = 2 * 1024 * 1024 # bytes read of the events file
SUBJECT = "Sending of mail was slowed down by the sending limit"
SERVICE = "miab-sendlimit"
RELEASE_SERVICE = "miab-sendlimit-release"
HELD_JSON = "/run/miab-sendlimit/held.json"
FLAG = "/run/miab-sendlimit/release"

DEFAULTS = { "enabled": True, "rate": 30, "per": 1 }
RANGES = { "rate": [1, 100000], "per": [1, 3600] }

EVENT_RE = re.compile(r"^([0-9]{1,12}) ([0-9]{1,6}) ([0-9]{1,5}) ([0-9]{1,9}) ([0-9]{1,9}) ([0-9]{1,9}) ([0-9]{1,4}) ([0-9]{1,9}) ([0-9]{1,9})((?: [^\s=]{1,210}=[0-9]{1,9}/[0-9]{1,9}){0,10})$")
QID_RE = re.compile(r"^[0-9A-Za-z]{6,24}$")
SENDER_RE = re.compile(r"^[^\s=]{1,210}$")


class SendLimitError(ValueError):
	pass


def validate_settings(values, strict=True):
	# Returns (settings, warnings); strict raises SendLimitError for a bad
	# value, otherwise it takes the default and warns.
	out, warnings = dict(DEFAULTS), []
	if not isinstance(values, dict):
		values = {}
	if "enabled" in values and values["enabled"] not in (None, ""):
		v = values["enabled"]
		if isinstance(v, bool):
			out["enabled"] = v
		elif str(v).strip().lower() in ("1", "true", "yes", "on"):
			out["enabled"] = True
		elif str(v).strip().lower() in ("0", "false", "no", "off"):
			out["enabled"] = False
		else:
			if strict:
				raise SendLimitError("enabled must be 1 or 0.")
			warnings.append("send_limit enabled in settings.yaml is not valid, the default applies.")
	names = { "rate": "The number of mails", "per": "The number of seconds" }
	for k in ("rate", "per"):
		if k not in values or values[k] in (None, ""):
			continue
		v = values[k]
		try:
			if isinstance(v, bool) or not re.fullmatch(r"[0-9]{1,6}", str(v).strip()):
				raise ValueError
			v = int(str(v).strip())
			if not RANGES[k][0] <= v <= RANGES[k][1]:
				raise ValueError
		except ValueError:
			msg = f"{names[k]} must be a whole number from {RANGES[k][0]} to {RANGES[k][1]}."
			if strict:
				raise SendLimitError(msg)
			warnings.append(f"send_limit {k} in settings.yaml is not valid, the default {DEFAULTS[k]} applies. " + msg)
			continue
		out[k] = v
	return out, warnings


def get_settings(env):
	import utils
	return validate_settings(utils.load_settings(env).get("send_limit") or {}, strict=False)


def save_settings(env, values):
	import utils
	config = utils.load_settings(env)
	diff = { k: v for k, v in values.items() if v != DEFAULTS[k] }
	if diff:
		config["send_limit"] = diff
	else:
		config.pop("send_limit", None)
	utils.write_settings(config, env)


def render_settings_file(values):
	return ("# Mail-in-a-Box --- Do not edit / will be overwritten on update.\n"
		"# The sending limit of the box, from settings.yaml (System > Intrusion Detection and Prevention;\n"
		"# management/send_limit.py), read by conf/send-limit/sendlimit-milter.py when it changes.\n"
		f"enabled {1 if values['enabled'] else 0}\n"
		f"rate {values['rate']}\n"
		f"per {values['per']}\n")


def read_settings_file(path=None):
	# The values the milter uses (its defaults without the file).
	out = { "enabled": DEFAULTS["enabled"], "rate": DEFAULTS["rate"], "per": DEFAULTS["per"] }
	try:
		with open(path or SETTINGS_FILE, encoding="utf-8") as f:
			for line in f:
				p = line.split()
				if len(p) == 2 and p[1].isdigit():
					if p[0] == "enabled":
						out["enabled"] = p[1] != "0"
					elif p[0] == "rate":
						out["rate"] = min(max(int(p[1]), 1), 100000)
					elif p[0] == "per":
						out["per"] = min(max(int(p[1]), 1), 86400)
	except OSError:
		pass
	return out


def write_settings_file(text, path=None):
	# A new file renamed over the old one in a directory of root that only
	# root may write (setup/mail-postfix.sh creates it).
	path = path or SETTINGS_FILE
	d, name = os.path.split(path)
	dfd = os.open(d, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
	try:
		st = os.fstat(dfd)
		if st.st_uid != os.geteuid() or stat.S_IMODE(st.st_mode) & 0o022:
			raise SendLimitError(f"{d} is not a directory of this account that only it may write.")
		try:
			fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dfd)
			try:
				if stat.S_IMODE(os.fstat(fd).st_mode) == 0o644 and os.read(fd, 65536).decode("utf-8", "replace") == text:
					return False
			finally:
				os.close(fd)
		except FileNotFoundError:
			pass
		tmp = f".{name}.{os.getpid()}.tmp"
		fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=dfd)
		try:
			os.fchmod(fd, 0o644)
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
	return write_settings_file(render_settings_file(values), path)


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


def parse_event(line):
	m = EVENT_RE.match(line)
	if not m:
		return None
	senders = []
	for item in m.group(10).split():
		s, counts = item.rsplit("=", 1)
		mails, rcpts = counts.split("/")
		senders.append({ "sender": s, "mails": int(mails), "recipients": int(rcpts) })
	return { "time": int(m.group(1)), "rate": int(m.group(2)), "per": int(m.group(3)), "delayed": int(m.group(4)),
		"deferred": int(m.group(5)), "passed": int(m.group(6)), "max_wait": int(m.group(7)), "others": int(m.group(8)),
		"held": int(m.group(9)), "senders": senders }


def take_events(state_dir=STATE_DIR, consume=True):
	# The events the milter wrote since the last call; consume renames the
	# file first, so the milter starts a new one, and removes it after.
	try:
		dfd = os.open(state_dir, os.O_RDONLY | os.O_DIRECTORY)
	except FileNotFoundError:
		return []
	try:
		name = EVENTS
		if consume:
			name = EVENTS + ".taken"
			try:
				os.rename(EVENTS, name, src_dir_fd=dfd, dst_dir_fd=dfd)
			except FileNotFoundError:
				pass
		try:
			fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dfd)
		except (FileNotFoundError, OSError):
			return []
		try:
			if not stat.S_ISREG(os.fstat(fd).st_mode):
				return []
			data = os.read(fd, MAX_READ).decode("utf-8", "replace")
		finally:
			os.close(fd)
		if consume:
			os.unlink(name, dir_fd=dfd)
	finally:
		os.close(dfd)
	return [e for e in (parse_event(l) for l in data.splitlines()) if e]


def load_state(path=NOTIFY_STATE):
	try:
		with open(path, encoding="utf-8") as f:
			s = json.load(f)
		if isinstance(s, dict) and isinstance(s.get("pending"), list) and isinstance(s.get("kept"), list):
			return { "last_sent": int(s.get("last_sent", 0)), "pending": s["pending"][-MAX_PENDING:], "dropped": int(s.get("dropped", 0)),
				"kept": s["kept"][-MAX_KEPT:] }
	except (OSError, ValueError, TypeError):
		pass
	return { "last_sent": 0, "pending": [], "dropped": 0, "kept": [] }


def save_state(state, path=NOTIFY_STATE):
	# /var/lib/mailinabox belongs to root.
	tmp = path + ".new"
	fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
	with os.fdopen(fd, "w", encoding="utf-8") as f:
		json.dump(state, f)
	os.replace(tmp, path)


def summary(events):
	# The senders over several events, most recipients first.
	senders = {}
	for e in events:
		for s in e["senders"]:
			t = senders.setdefault(s["sender"], [0, 0])
			t[0] += s["mails"]
			t[1] += s["recipients"]
	return [{ "sender": s, "mails": m, "recipients": r } for s, (m, r) in sorted(senders.items(), key=lambda kv: (-kv[1][1], kv[0]))]


def describe_sender(s):
	if s.startswith("sendmail:"):
		return f"{s[9:]} (sendmail: ActiveSync, Nextcloud, a Sieve redirect or a program on the box)"
	if s.startswith("smtp:"):
		return f"{s[5:]} (SMTP without login)"
	return f"{s} (logged in by SMTP: a mail program or webmail)"


def message(events, dropped=0, held=None):
	lines = []
	for e in events:
		when = time.strftime("%Y-%m-%d %H:%M", time.localtime(e["time"]))
		lines.append(f"{when}  {e.get('held', 0)} mails put on hold, {e['delayed']} waited (up to {e['max_wait']} s), {e['deferred']} deferred,"
			f" {e['passed']} went out at once (limit {e['rate']} mails in {e['per']} s)")
	if dropped:
		lines.append(f"... and {dropped} more minutes")
	top = summary(events)[:15]
	senders = "\n".join(f"  {s['recipients']:7d} recipients in {s['mails']:6d} mails  {describe_sender(s['sender'])}" for s in top)
	now_held = ""
	if held and held.get("held"):
		now_held = (f"On hold now: {held['held']} mails to {held['recipients']} recipients. They go out at the limit, the senders in turn:\n\n"
			+ "\n".join(f"  {x['recipients']:7d} recipients in {x['mails']:6d} mails  {describe_sender(x['sender'])}" for x in held["senders"][:15]) + "\n\n")
	return ("The sending limit of the box slowed down outgoing mail in these minutes (each recipient counts as one mail). Mail"
		" that did not fit was accepted and put on hold, and goes out at the limit; the senders got no error:\n\n"
		+ "\n".join(lines) + "\n\nWho sent it:\n\n" + (senders or "  (not recorded)") + "\n\n" + now_held +
		"If you did not expect this much mail from the box, an account may have been taken over, or a program on the box sends"
		" spam: change the password of the account named above and end its sessions, and delete its held mail before it goes"
		" out: in the control panel, System > Intrusion Detection and Prevention, \"Delete\" next to the sender (or on the box:"
		" management/send_limit.py --delete SENDER).\n\n"
		"The limit, the held mail and a list of these minutes: the control panel, System > Intrusion Detection and Prevention.\n")


def send_mail(text):
	p = subprocess.run([sys.executable, os.path.join(HERE, "email_administrator.py"), SUBJECT],
		input=text, text=True, capture_output=True, timeout=120)
	if p.returncode != 0:
		raise RuntimeError("email_administrator.py: " + (p.stderr.strip() or p.stdout.strip())[-300:])


def notify(now=None, take=take_events, send=send_mail, state_path=NOTIFY_STATE):
	now = int(time.time()) if now is None else now
	events = take()
	state = load_state(state_path)
	state["kept"] = [e for e in state["kept"] + events if now - e["time"] < KEEP][-MAX_KEPT:]
	for e in events:
		if len(state["pending"]) < MAX_PENDING:
			state["pending"].append(e)
		else:
			state["dropped"] += 1
	# Saved before the mail is sent: the events file is already taken, and a
	# failed send (the mail server busy, for example) keeps them pending.
	if events:
		save_state(state, state_path)
	sent = False
	if state["pending"] and now - state["last_sent"] >= NOTIFY_INTERVAL:
		try:
			send(message(state["pending"], state["dropped"], read_held()))
		except Exception as e:
			print(f"send_limit.py: the mail to the administrator could not be sent, it is tried again next time: {e}", file=sys.stderr)
			return False
		state.update({ "last_sent": now, "pending": [], "dropped": 0 })
		save_state(state, state_path)
		sent = True
	return sent


def service_running(unit=SERVICE):
	try:
		return subprocess.run(["systemctl", "is-active", "--quiet", unit], timeout=10).returncode == 0
	except (OSError, subprocess.SubprocessError):
		return None


def read_held(path=None):
	# The release service's list of held mail by sender (None when missing).
	try:
		with open(path or HELD_JSON, encoding="utf-8") as f:
			h = json.load(f)
		if isinstance(h, dict) and isinstance(h.get("senders"), list):
			return h
	except (OSError, ValueError):
		pass
	return None


def held_qids(sender=None, held=None):
	# The queue ids of the held mail (of one sender), from held.json.
	held = held if held is not None else read_held()
	if held is None:
		raise SendLimitError("The list of held mail is not there (the release service miab-sendlimit-release does not run?).")
	if sender is not None and (not isinstance(sender, str) or not SENDER_RE.match(sender)):
		raise SendLimitError("Not a sender of the list.")
	out = []
	for s in held["senders"]:
		if sender is None or s.get("sender") == sender:
			out += [q for q in s.get("qids", []) if isinstance(q, str) and QID_RE.match(q)]
	return out


def act_on_held(action, sender=None, run=subprocess.run, held=None):
	# action "release" (now, past the limit) or "delete"; sender None: all.
	if action not in ("release", "delete"):
		raise SendLimitError("action must be release or delete.")
	qids = held_qids(sender, held)
	if sender is not None and not qids:
		raise SendLimitError("No held mail of this sender (it may have gone out already).")
	if qids:
		p = run(["postsuper", "-d" if action == "delete" else "-H", "-"], input="".join(q + "\n" for q in qids), capture_output=True, text=True, timeout=300)
		if p.returncode != 0:
			raise RuntimeError("postsuper: " + (p.stderr or "").strip()[-300:])
		if action == "release":
			for q in qids:
				run(["postqueue", "-i", q], capture_output=True, timeout=60)
	return { "action": action, "sender": sender, "mails": len(qids) }


def status(env, now=None, take=None, state_path=NOTIFY_STATE, running=None, settings_file=None):
	# For the control panel (GET /system/send-limit): the setting, what the
	# milter uses, and the minutes of the last 24 hours (also those not yet
	# taken by --notify) in which mail had to wait.
	now = int(time.time()) if now is None else now
	values, warnings = get_settings(env)
	applied = read_settings_file(settings_file)
	if applied != values:
		warnings.append("The milter does not use this setting yet (its settings file differs); save it again, or run setup.")
	if running is None:
		running = service_running()
	if running is False:
		warnings.append(f"The service {SERVICE} does not run: mail is sent without the limit (Postfix passes it on). Run setup, or: systemctl restart {SERVICE}.")
	release_running = service_running(RELEASE_SERVICE) if running is not True else running
	held = read_held() if take is None else None
	if release_running is False:
		warnings.append(f"The service {RELEASE_SERVICE} does not run: nothing is put on hold, mail over the limit waits at most 60 s and is then deferred"
			+ (f", and {held['held']} held mails are not released" if held and held.get("held") else "") + f". Run setup, or: systemctl restart {RELEASE_SERVICE}.")
	fresh = (take or (lambda: take_events(consume=False)))()
	kept = load_state(state_path)["kept"]
	seen = { (e["time"], e["delayed"], e["deferred"]) for e in kept }
	events = [e for e in kept + [e for e in fresh if (e["time"], e["delayed"], e["deferred"]) not in seen] if now - e["time"] < 86400]
	events.sort(key=lambda e: -e["time"])
	return { "settings": values, "defaults": DEFAULTS, "ranges": RANGES, "applied": applied, "warnings": warnings,
		"running": running, "release_running": release_running, "events": events[:200], "more": max(0, len(events) - 200),
		"held": { "mails": (held or {}).get("held", 0), "recipients": (held or {}).get("recipients", 0),
			"senders": [{ k: x.get(k) for k in ("sender", "mails", "recipients", "oldest") } for x in (held or {}).get("senders", [])[:200]] },
		"day": { "minutes": len(events), "delayed": sum(e["delayed"] for e in events), "deferred": sum(e["deferred"] for e in events),
			"held": sum(e.get("held", 0) for e in events),
			"max_wait": max([e["max_wait"] for e in events] or [0]), "senders": summary(events)[:20] } }


def main(argv):
	if not (len(argv) == 2 and argv[1] in ("--notify", "--status", "--apply", "--release")) and not (len(argv) == 3 and argv[1] in ("--release", "--delete")):
		print("usage: send_limit.py --notify | --status | --apply | --release [SENDER] | --delete SENDER|--all", file=sys.stderr)
		return 2
	if os.geteuid() != 0:
		print("send_limit.py: run it as root (sudo).", file=sys.stderr)
		return 1
	sys.path.insert(0, HERE)
	from utils import load_environment
	env = load_environment()
	if argv[1] == "--apply":
		values, warnings = get_settings(env)
		for w in warnings:
			print(w, file=sys.stderr)
		apply_config(env, values)
		return 0
	if argv[1] == "--notify":
		notify()
		return 0
	if argv[1] in ("--release", "--delete"):
		sender = None if len(argv) == 2 or argv[2] == "--all" else argv[2]
		try:
			r = act_on_held(argv[1][2:], sender)
		except SendLimitError as e:
			print(f"send_limit.py: {e}", file=sys.stderr)
			return 1
		print(f"{'Released' if r['action'] == 'release' else 'Deleted'} {r['mails']} held mails" + (f" of {sender}." if sender else "."))
		return 0
	st = status(env)
	for w in st["warnings"]:
		print(w)
	a = st["applied"]
	print(f"Sending limit: {a['rate']} mails in {a['per']} s" + ("" if a["enabled"] else " (turned off)"))
	h = st["held"]
	if h["mails"]:
		print(f"On hold now: {h['mails']} mails to {h['recipients']} recipients:")
		for x in h["senders"]:
			print(f"  {x['recipients']:7d} recipients in {x['mails']:6d} mails  {x['sender']}")
	d = st["day"]
	if not d["minutes"]:
		print("No mail had to wait in the last 24 hours.")
	else:
		print(f"In the last 24 hours the limit acted in {d['minutes']} minutes: {d['held']} mails were put on hold, {d['delayed']} waited (up to {d['max_wait']} s), {d['deferred']} were deferred.")
		for s in d["senders"]:
			print(f"  {s['recipients']:7d} recipients in {s['mails']:6d} mails  {describe_sender(s['sender'])}")
	return 0


if __name__ == "__main__":
	sys.exit(main(sys.argv))
