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
MAX_READ = 8 * 1024 * 1024
MAX_HELD = 200000 # mails kept track of
log = common.log


def take_held(state_dir=common.STATE_DIR):
	# The milter's new lines: renamed, read without following a link, removed.
	try:
		dfd = os.open(state_dir, os.O_RDONLY | os.O_DIRECTORY)
	except OSError:
		return []
	try:
		try:
			os.rename("held", "held.taken", src_dir_fd=dfd, dst_dir_fd=dfd)
		except FileNotFoundError:
			pass
		try:
			fd = os.open("held.taken", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dfd)
		except OSError:
			return []
		try:
			if not stat.S_ISREG(os.fstat(fd).st_mode):
				return []
			data = b""
			while len(data) < MAX_READ:
				chunk = os.read(fd, 1 << 20)
				if not chunk:
					break
				data += chunk
		finally:
			os.close(fd)
		os.unlink("held.taken", dir_fd=dfd)
	finally:
		os.close(dfd)
	return [h for h in (common.parse_held(l) for l in data.decode("utf-8", "replace").splitlines()) if h]


def hold_queue():
	# The queue ids in Postfix's hold queue, or None when postqueue failed.
	try:
		p = subprocess.run(["postqueue", "-j"], capture_output=True, text=True, timeout=120)
	except (OSError, subprocess.SubprocessError) as e:
		log(f"postqueue -j failed: {e}", 4)
		return None
	if p.returncode != 0:
		log(f"postqueue -j failed: {p.stderr.strip()[:200]}", 4)
		return None
	ids = set()
	for line in p.stdout.splitlines():
		try:
			j = json.loads(line)
		except ValueError:
			continue
		if j.get("queue_name") == "hold" and isinstance(j.get("queue_id"), str):
			ids.add(j["queue_id"])
	return ids


def release(qids):
	# Into the deferred queue (postsuper -H), then into the active queue at
	# once (postqueue -i, one id per call).
	if not qids:
		return
	p = subprocess.run(["postsuper", "-H", "-"], input="".join(q + "\n" for q in qids), capture_output=True, text=True, timeout=120)
	if p.returncode != 0:
		log(f"postsuper -H failed: {p.stderr.strip()[:300]}", 4)
	for q in qids:
		subprocess.run(["postqueue", "-i", q], capture_output=True, timeout=60)


def load_state(path=STATE):
	try:
		with open(path, encoding="utf-8") as f:
			s = json.load(f)
		held = [h for h in s.get("held", []) if isinstance(h, dict) and common.parse_held(f"{h.get('time')} {h.get('qid')} {h.get('rcpts')} {h.get('sender')}")]
		return { "held": held[:MAX_HELD], "released": int(s.get("released", 0)), "turn": str(s.get("turn", "")) }
	except (OSError, ValueError, TypeError, AttributeError):
		return { "held": [], "released": 0, "turn": "" }


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


def pick(held, limiter, rate, per, turn, now=None):
	# The mails to release now: the senders in turn after `turn` (the oldest
	# mail of each), as long as the bucket has room. Returns (mails, turn).
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
			if limiter.reserve(h["rcpts"], rate, per, 0, now=now) is None:
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


def summary(held, now):
	senders = {}
	for h in held:
		s = senders.setdefault(h["sender"], { "sender": h["sender"], "mails": 0, "recipients": 0, "oldest": h["time"], "qids": [] })
		s["mails"] += 1
		s["recipients"] += h["rcpts"]
		s["oldest"] = min(s["oldest"], h["time"])
		if len(s["qids"]) < 100000:
			s["qids"].append(h["qid"])
	return { "time": int(now), "held": len(held), "recipients": sum(h["rcpts"] for h in held),
		"senders": sorted(senders.values(), key=lambda s: (-s["recipients"], s["sender"])) }


def main():
	settings = common.Settings()
	limiter = common.Limiter()
	state = load_state()
	known = { h["qid"] for h in state["held"] }
	last_check = 0.0
	last_log = time.time()
	released_minute = 0
	os.makedirs(common.RUN_DIR, mode=0o755, exist_ok=True)
	log(f"started, {len(state['held'])} mails on hold from before")
	while True:
		now = time.time()
		changed = False
		new = [h for h in take_held() if h["qid"] not in known]
		if new:
			state["held"].extend(new[:max(0, MAX_HELD - len(state["held"]))])
			known.update(h["qid"] for h in new)
			changed = True
		if state["held"] and now - last_check >= CHECK_QUEUE:
			last_check = now
			ids = hold_queue()
			if ids is not None:
				# A line the milter wrote just before Postfix moved its mail to
				# the hold queue waits one more look.
				keep = [h for h in state["held"] if h["qid"] in ids or now - h["time"] < 2 * CHECK_QUEUE]
				if len(keep) != len(state["held"]):
					state["held"] = keep
					known = { h["qid"] for h in keep }
					changed = True
		v = settings.get()
		if state["held"]:
			if v["enabled"]:
				out, state["turn"] = pick(state["held"], limiter, v["rate"], v["per"], state["turn"])
			else:
				out = list(state["held"]) # turned off: everything goes
			if out:
				release([h["qid"] for h in out])
				gone = { h["qid"] for h in out }
				state["held"] = [h for h in state["held"] if h["qid"] not in gone]
				known -= gone
				state["released"] += len(out)
				released_minute += len(out)
				changed = True
		if changed:
			save_state(state)
		try:
			write_public(common.FLAG, f"{int(now)} {len(state['held'])}\n")
			if changed or not os.path.exists(common.HELD_JSON):
				write_public(common.HELD_JSON, json.dumps(summary(state["held"], now)), 0o600)
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
