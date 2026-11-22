#!/usr/bin/python3 -I
#
# The sending limit of the box (fork, B221): releases the mails that the
# milter (sendlimit-milter.py) put on hold, at most RATE mails (recipients) within PER
# seconds, taking the senders in turn (the oldest mail of each), so that one
# sender with many mails does not hold back the others. Runs as root
# (postsuper and postqueue), as the service miab-sendlimit-release.
#
# It takes the milter's lines "<time> <queue id> <recipients> <sender>" from
# the file "held" in the milter's state directory (which belongs to the
# milter's dynamic user: renamed and opened there through the directory's
# descriptor, without following a link), keeps them in STATE (root's), and
# releases a mail with "postsuper -H" and "postqueue -i" (into the active
# queue at once, not at the next run of the deferred queue). It releases
# only mails that the milter put on hold: a mail held by hand stays. A mail
# that is no longer in the hold queue (deleted, or released by hand) is
# forgotten when the queue is looked at (postqueue -j, every few seconds
# while mail is held).
#
# Each loop it writes its flag (RUN_DIR/release: the time and the number of
# mails it holds back), which the milter reads: without a fresh flag the
# milter puts nothing on hold. RUN_DIR/held.json lists the held mails by
# sender for the control panel (management/send_limit.py).

import json
import os
import stat
import subprocess
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__))) # after the system's: pymilter has a module "milter" of its own

import sendlimit_common as common # noqa: E402

STATE = "/var/lib/mailinabox/send-limit-held.json"
LOOP = 0.5 # seconds
CHECK_QUEUE = 5 # seconds between two looks at the hold queue while mail is held
log = common.log


def take_held(state_dir=common.STATE_DIR, limit=5000):
	# The milter's files held.d/<queue id> ("<time> <recipients> <sender>"),
	# read without following a link and removed. Its temporary files (".*")
	# are left for it.
	out = []
	try:
		dfd = os.open(os.path.join(state_dir, "held.d"), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
	except OSError:
		return out
	try:
		for name in os.listdir(dfd)[:limit]:
			if not common.QID_ONLY.match(name):
				continue
			try:
				fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dfd)
			except OSError:
				continue
			try:
				data = os.read(fd, 512).decode("utf-8", "replace") if stat.S_ISREG(os.fstat(fd).st_mode) else ""
			finally:
				os.close(fd)
			try:
				os.unlink(name, dir_fd=dfd)
			except OSError:
				pass
			parts = data.strip().split(" ")
			h = common.parse_held(f"{parts[0]} {name} {' '.join(parts[1:])}") if len(parts) == 3 else None
			if h:
				out.append(h)
	finally:
		os.close(dfd)
	return out


def pending_held(state_dir=common.STATE_DIR):
	# The queue ids of the milter's records not taken yet (written after
	# take_held() ran in this loop): their mail is not "held by others".
	try:
		dfd = os.open(os.path.join(state_dir, "held.d"), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
	except OSError:
		return set()
	try:
		return { n for n in os.listdir(dfd) if common.QID_ONLY.match(n) }
	finally:
		os.close(dfd)


def take_passed(state_dir=common.STATE_DIR):
	# (pid, recipients) of the milter's "passed" file, or None.
	try:
		fd = os.open(os.path.join(state_dir, "passed"), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
	except OSError:
		return None
	try:
		if not stat.S_ISREG(os.fstat(fd).st_mode):
			return None
		m = common.PASSED_RE.match(os.read(fd, 64).decode("ascii", "replace").strip())
	finally:
		os.close(fd)
	return (int(m.group(1)), int(m.group(2))) if m else None


def hold_queue():
	# {queue id: arrival time} of Postfix's hold queue, or None when
	# postqueue failed.
	try:
		p = subprocess.run(["postqueue", "-j"], capture_output=True, text=True, timeout=120)
	except (OSError, subprocess.SubprocessError) as e:
		log(f"postqueue -j failed: {e}", 4)
		return None
	if p.returncode != 0:
		log(f"postqueue -j failed: {p.stderr.strip()[:200]}", 4)
		return None
	ids = {}
	for line in p.stdout.splitlines():
		try:
			j = json.loads(line)
		except ValueError:
			continue
		if j.get("queue_name") == "hold" and isinstance(j.get("queue_id"), str) and isinstance(j.get("arrival_time"), int):
			ids[j["queue_id"]] = j["arrival_time"]
	return ids


ARRIVAL_SLACK = 30 # seconds a record may come before its mail is in the hold queue
MAX_AGE = 5 * 86400 # a mail held at most this long after it arrived (Postfix's maximal_queue_lifetime)
COUNT_HOLD = 300 # seconds between two counts of the mail held by others while none is held here


def verified(h, ids):
	# The milter's record names a mail that is in the hold queue and had
	# arrived when the milter held it (not later, so a record cannot name
	# mail that comes after it, and at most MAX_AGE before). Postfix's arrival
	# time is when the mail entered its queue: for sendmail the time it was
	# written to the maildrop, which can be long before the milter holds it
	# (pickup busy with a flood, or the mail deferred while the release
	# service did not run), and for SMTP the start of a slow transfer. The
	# first version allowed 30 s either way, and such mail stayed on hold for
	# ever, listed nowhere (found in the lab test).
	if h["qid"] not in ids:
		return False
	arrival = ids[h["qid"]]
	return arrival <= h["time"] + ARRIVAL_SLACK and h["time"] - arrival <= MAX_AGE


def release(qids):
	# Into the deferred queue (postsuper -H), then into the active queue at
	# once (postqueue -i, one id per call). Returns how many were released
	# (a mail deleted meanwhile is not).
	if not qids:
		return 0
	p = subprocess.run(["postsuper", "-H", "-", "hold"], input="".join(q + "\n" for q in qids), capture_output=True, text=True, timeout=120)
	if p.returncode != 0:
		log(f"postsuper -H failed: {p.stderr.strip()[:300]}", 4)
	done = [q for q in qids if f"{q}: released from hold" in p.stderr]
	for q in done:
		subprocess.run(["postqueue", "-i", q], capture_output=True, timeout=60)
	return len(done)


def load_state(path=STATE):
	try:
		with open(path, encoding="utf-8") as f:
			s = json.load(f)
		held = [h for h in s.get("held", []) if isinstance(h, dict) and common.parse_held(f"{h.get('time')} {h.get('qid')} {h.get('rcpts')} {h.get('sender')}")]
		since = s.get("brake_since")
		reason = s.get("brake_reason")
		return { "held": held, "released": int(s.get("released", 0)), "turn": str(s.get("turn", "")),
			"brake": bool(s.get("brake")) and isinstance(since, int), "brake_since": since if isinstance(since, int) else None,
			"brake_reason": reason if isinstance(reason, str) and len(reason) < 100 else None,
			"last_held": int(s.get("last_held", 0)), "last_over": int(s.get("last_over", 0)) }
	except (OSError, ValueError, TypeError, AttributeError):
		return { "held": [], "released": 0, "turn": "", "brake": False, "brake_since": None, "brake_reason": None, "last_held": 0, "last_over": 0 }


def save_state(state, path=STATE):
	tmp = path + ".new"
	fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
	with os.fdopen(fd, "w", encoding="utf-8") as f:
		json.dump(state, f)
	os.replace(tmp, path)


def write_public(path, text, mode=0o644):
	tmp = f"{path}.{os.getpid()}.tmp"
	fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
	with os.fdopen(fd, "w", encoding="utf-8") as f:
		os.fchmod(f.fileno(), mode)
		f.write(text)
	os.replace(tmp, path)


def pick(held, limiter, rate, per, turn, now=None, also=()):
	# The mails to release now: the senders in turn after `turn` (the oldest
	# mail of each), as long as the bucket has room (and the buckets of
	# `also`, [(limiter, rate, per)]: the long limit). Returns (mails, turn).
	by_sender = {}
	for h in held:
		by_sender.setdefault(h["sender"], []).append(h)
	for v in by_sender.values():
		v.sort(key=lambda h: (h["time"], h["qid"]))
	order = sorted(by_sender)
	if turn in order:
		i = order.index(turn) + 1
		order = order[i:] + order[:i]
	out = []
	while order:
		progressed = False
		for s in list(order):
			h = by_sender[s][0]
			if common.reserve_all([(limiter, rate, per), *also], h["rcpts"], 0, now=now) is None:
				return out, turn
			out.append(h)
			turn = s
			by_sender[s].pop(0)
			if not by_sender[s]:
				order.remove(s)
			progressed = True
		if not progressed:
			break
	return out, turn


def notify_now():
	# The administrator's mail about a new brake, at once (setup/management.sh
	# writes this unit: management/send_limit.py --notify).
	try:
		subprocess.run(["systemctl", "start", "--no-block", "miab-sendlimit-notify.service"], capture_output=True, timeout=30)
	except (OSError, subprocess.SubprocessError) as e:
		log(f"the mail to the administrator could not be started: {e}", 4)


def summary(held, now, state=None, v=None):
	senders = {}
	for h in held:
		s = senders.setdefault(h["sender"], { "sender": h["sender"], "mails": 0, "recipients": 0, "oldest": h["time"], "qids": [] })
		s["mails"] += 1
		s["recipients"] += h["rcpts"]
		s["oldest"] = min(s["oldest"], h["time"])
		if len(s["qids"]) < 100000:
			s["qids"].append(h["qid"])
	out = { "time": int(now), "held": len(held), "recipients": sum(h["rcpts"] for h in held),
		"senders": sorted(senders.values(), key=lambda s: (-s["recipients"], s["sender"])) }
	if state is not None and v is not None:
		out.update({ "brake": state["brake"], "brake_since": state["brake_since"], "brake_reason": state.get("brake_reason"),
			"other_hold": state.get("other_hold", 0), "stop": bool(v["stop"]),
			"brake_rate": v["brake_rate"], "brake_per": v["brake_per"], "calm": v["calm"] })
	return out


def main():
	settings = common.Settings()
	limiter = common.Limiter()
	long_limiter = common.Limiter()
	brake_limiter = common.Limiter()
	# The rate at which counted mail comes in (the milter's direct passes and
	# the held mails): the brake goes on when it is above the limit, and ends
	# by itself only after "calm" minutes below it. A held mail that waits
	# behind others (after the administrator ended the brake) does not set
	# it off again on its own.
	arrivals = common.Limiter()
	long_arrivals = common.Limiter()
	state = load_state()
	known = { h["qid"] for h in state["held"] }
	checked = set() # records verified against the hold queue
	last_check = 0.0
	last_count = 0.0
	last_log = time.time()
	released_minute = 0
	last_passed = take_passed() # the milter's count from before is not charged
	last_v = None
	os.makedirs(common.RUN_DIR, mode=0o755, exist_ok=True)
	log(f"started, {len(state['held'])} mails on hold from before")
	while True:
		now = time.time()
		changed = False
		v = settings.get()
		# What the milter let through at once is taken from this bucket too.
		p = take_passed()
		if p is not None:
			if last_passed is not None and p[0] == last_passed[0] and p[1] >= last_passed[1]:
				delta = p[1] - last_passed[1]
			else:
				delta = p[1] if last_passed is not None else 0 # a new milter process
			if delta and v["enabled"]:
				for l, r, per in common.limit_pairs(v, limiter, long_limiter) + common.limit_pairs(v, arrivals, long_arrivals):
					l.charge(delta, r, per)
			last_passed = p
		new = [h for h in take_held() if h["qid"] not in known]
		if new:
			state["held"].extend(new)
			known.update(h["qid"] for h in new)
			state["last_held"] = int(now)
			changed = True
			over, reasons = [], []
			pairs = common.limit_pairs(v, arrivals, long_arrivals)
			for h in new:
				if common.reserve_all(pairs, h["rcpts"], 0) is None:
					reasons += [r for r in common.over_limits(pairs, h["rcpts"]) if r not in reasons]
					for l, r, per in pairs:
						l.charge(h["rcpts"], r, per)
					over.append(h)
			if over:
				state["last_over"] = int(now)
			if over and not state["brake"] and v["enabled"]:
				# More mail than the limit: the brake is on, all mail is held.
				state["brake"], state["brake_since"] = True, int(now)
				state["brake_reason"] = " and ".join(common.describe_limit(r, per) for r, per in reasons) or common.describe_limit(v["rate"], v["per"])
				brake_limiter = common.Limiter()
				# In debt by one period: the first slow release comes after
				# about brake_per seconds, also for a mail of more recipients
				# than brake_rate (which goes when the bucket is not in debt; with
				# a bucket that was only full, it went out at once: the lab
				# test saw 60 to 120 recipients out in the brake's first second).
				brake_limiter.charge(2 * v["brake_rate"], v["brake_rate"], v["brake_per"])
				log(f"THE BRAKE IS ON: more than {state['brake_reason']}; all outgoing mail is held"
					+ (" until the administrator ends the brake" if v["stop"] else f" and goes out at {v['brake_rate']} mails in {v['brake_per']} s")
					+ "; senders: " + ", ".join(sorted({ h["sender"] for h in over }))[:500], 4)
				notify_now()
		if os.path.lexists(common.END):
			try:
				os.unlink(common.END)
			except OSError:
				pass
			if state["brake"]:
				state["brake"], state["brake_since"], state["brake_reason"] = False, None, None
				changed = True
				log(f"the administrator ended the brake; {len(state['held'])} held mails go out at the limit", 4)
		if state["brake"] and not v["stop"] and not state["held"] and now - state.get("last_over", 0) >= v["calm"] * 60:
			state["brake"], state["brake_since"], state["brake_reason"] = False, None, None
			changed = True
			log(f"the brake ended by itself: no held mail left, and no more mail than the limit for {v['calm']} minutes")
		if not v["enabled"] and state["brake"]:
			state["brake"], state["brake_since"], state["brake_reason"] = False, None, None
			changed = True
		recheck = os.path.lexists(common.RECHECK)
		if recheck:
			try:
				os.unlink(common.RECHECK)
			except OSError:
				pass
		unchecked = [h for h in state["held"] if h["qid"] not in checked]
		ids = None
		if state["held"] and (recheck or ((unchecked or now - last_check >= CHECK_QUEUE) and now - last_check >= 1)):
			last_check = now
			ids = hold_queue()
			if ids is not None:
				# A record whose mail is not (yet) in the hold queue waits a
				# little: the milter writes it just before Postfix holds the mail.
				keep = []
				for h in state["held"]:
					if verified(h, ids):
						checked.add(h["qid"])
						keep.append(h)
					elif h["qid"] not in ids and h["qid"] not in checked and now - h["time"] < ARRIVAL_SLACK:
						keep.append(h)
					elif h["qid"] in ids:
						log(f"a record of the milter names {h['qid']}, which is held but did not arrive then; it is left alone", 4)
				if len(keep) != len(state["held"]):
					state["held"] = keep
					known = { h["qid"] for h in keep }
					checked &= known
					changed = True
		elif recheck or now - last_count >= COUNT_HOLD:
			ids = hold_queue()
		if ids is not None:
			# Mail in the hold queue that is not on this list (held by hand,
			# or a record that could not be verified): the control panel and
			# the administrator's mail say how many.
			last_count = now
			# A mail the milter held after this loop read its records is in
			# the hold queue but not on the list yet: its record waits in
			# held.d (the first version counted it for one loop, and the
			# administrator's mail of a brake said so; found in the lab test).
			other = [q for q in ids if q not in known]
			if other:
				pending = pending_held()
				other = [q for q in other if q not in pending]
			other = len(other)
			if other != state.get("other_hold", 0):
				state["other_hold"] = other
				changed = True
		ready = [h for h in state["held"] if h["qid"] in checked]
		if ready:
			if not v["enabled"]:
				out = ready # turned off: everything goes
			elif state["brake"] and v["stop"]:
				out = [] # nothing until the administrator ends the brake
			elif state["brake"]:
				out, state["turn"] = pick(ready, brake_limiter, v["brake_rate"], v["brake_per"], state["turn"])
			else:
				out, state["turn"] = pick(ready, limiter, v["rate"], v["per"], state["turn"], also=common.limit_pairs(v, limiter, long_limiter)[1:])
			if out:
				n_released = release([h["qid"] for h in out])
				gone = { h["qid"] for h in out }
				state["held"] = [h for h in state["held"] if h["qid"] not in gone]
				known -= gone
				checked -= gone
				state["released"] += n_released
				released_minute += n_released
				changed = True
		if changed:
			save_state(state)
		try:
			write_public(common.FLAG, f"{int(now)} {len(state['held'])} {1 if state['brake'] else 0}\n")
			if changed or v != last_v or not os.path.exists(common.HELD_JSON):
				write_public(common.HELD_JSON, json.dumps(summary(state["held"], now, state, v)), 0o600)
				last_v = dict(v)
		except OSError as e:
			log(f"{common.RUN_DIR} could not be written: {e}", 4)
		if now - last_log >= 60:
			if released_minute or state["held"]:
				log(f"released {released_minute} held mails in the last minute, {len(state['held'])} still on hold", 4 if state["held"] else 6)
			released_minute = 0
			last_log = now
		time.sleep(LOOP)


if __name__ == "__main__":
	main()
