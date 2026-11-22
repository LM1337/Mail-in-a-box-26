#!/usr/bin/python3 -I
#
# The sending limit of the box (fork, B221): a Postfix milter that lets at
# most RATE mails within PER seconds go out (each recipient counts as one
# mail), for all mail that users and the box itself send: SMTP AUTH on the
# submission ports 465 and 587 (mail programs, Roundcube), mail through
# sendmail (Z-Push's ActiveSync, Nextcloud, Sieve redirects, cron, programs
# on the box) and SMTP from the box itself without a login (127.0.0.0/8 and
# ::1 on port 25, which Postfix lets relay as mynetworks). Mail that other
# servers send to the box is not counted.
#
# Up to RATE mails go out at once. A mail that does not fit waits a moment
# (SHORT_WAIT); if it still does not fit, Postfix accepts it and puts it on
# hold (its hold queue), and sendlimit-release.py (service miab-sendlimit-release)
# releases the held mails at RATE per PER seconds, taking the senders in
# turn, so that one sender with many mails does not hold back the others.
# While mail is on hold, all new mail goes on hold behind it. The sender
# never sees an error, and the administrator can delete held mail (an
# account that was taken over) before it goes out.
#
# Without sendlimit-release.py (its flag in /run/miab-sendlimit is missing or old),
# nothing is put on hold, as nothing would release it: a mail waits at most
# MAX_WAIT seconds and is then deferred with a temporary error (4.7.1), so
# that its sender sends it again later.
#
# Each minute in which mail waited or was held is logged and added to the
# events file in the state directory, which management/send_limit.py
# --notify mails to the administrator. Setup writes the settings file
# (management/send_limit.py --apply) from settings.yaml (System > Intrusion
# Detection and Prevention); it is read again when it changes. Postfix passes
# mail on when this milter does not answer (milter_default_action=accept).
#
# It runs as a dynamic user without privileges (conf/miab-sendlimit.service).

import os
import sys
import threading
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__))) # after the system's: pymilter has a module "milter" of its own

import Milter # noqa: E402

import sendlimit_common as common # noqa: E402

STATE_DIR = os.environ.get("STATE_DIRECTORY", common.STATE_DIR)
EVENTS = os.path.join(STATE_DIR, "events")
HELD = os.path.join(STATE_DIR, "held")
SOCKET = "inet:8895@127.0.0.1"
SHORT_WAIT = 2 # seconds a mail waits before it is put on hold
MAX_WAIT = 60 # seconds a mail waits at most without sendlimit-release.py (Postfix waits 300 s for a milter)
MAX_STATE_FILE = 4 * 1024 * 1024 # bytes; send_limit.py and sendlimit-release.py empty them
TOP_SENDERS = 10
log = common.log


class Flag:
	# sendlimit-release.py's flag, looked at once a second: (it runs, mails on hold).
	def __init__(self):
		self.value = (False, None)
		self.checked = 0
		self.lock = threading.Lock()
		self.held_here = 0 # put on hold since the last look

	def get(self):
		now = time.monotonic()
		with self.lock:
			if now - self.checked >= 1:
				self.checked = now
				self.value = common.read_flag()
				self.held_here = 0
			return self.value[0], (self.value[1] or 0) + self.held_here

	def held(self):
		with self.lock:
			self.held_here += 1


class Stats:
	# What waited or was held, per minute: written to the events file and the log.
	def __init__(self):
		self.lock = threading.Lock()
		self.reset()

	def reset(self):
		self.delayed = 0
		self.held = 0
		self.deferred = 0
		self.passed = 0
		self.max_wait = 0.0
		self.senders = {}

	def add(self, sender, n, outcome, wait=0.0):
		# outcome: "passed", "delayed", "held" or "deferred"
		with self.lock:
			if outcome == "passed":
				self.passed += 1
				return
			setattr(self, outcome, getattr(self, outcome) + 1)
			self.max_wait = max(self.max_wait, wait)
			s = self.senders.setdefault(sender, [0, 0])
			s[0] += 1
			s[1] += n

	def flush(self, settings):
		with self.lock:
			if not (self.delayed or self.held or self.deferred):
				self.reset()
				return
			delayed, held, deferred, passed, max_wait = self.delayed, self.held, self.deferred, self.passed, self.max_wait
			top = sorted(self.senders.items(), key=lambda kv: (-kv[1][1], kv[0]))[:TOP_SENDERS]
			others = len(self.senders) - len(top)
			self.reset()
		v = settings.get()
		log(level=4, text=f"sending was slowed down in the last minute (limit {v['rate']} mails in {v['per']} s): {held} mails were put on hold,"
			f" {delayed} waited (up to {max_wait:.0f} s), {deferred} were deferred, {passed} went out at once; senders: "
			+ ", ".join(f"{s} ({m} mails, {r} recipients)" for s, (m, r) in top) + (f" and {others} more" if others else ""))
		append(EVENTS, " ".join([str(int(time.time())), str(v["rate"]), str(v["per"]), str(delayed), str(deferred), str(passed),
			str(int(max_wait + 0.999)), str(others), str(held)] + [f"{s}={m}/{r}" for s, (m, r) in top]))


def append(path, line):
	try:
		if os.path.getsize(path) > MAX_STATE_FILE:
			log(f"{path} is full (nobody takes its lines), the line is dropped", 4)
			return False
	except OSError:
		pass
	try:
		with open(path, "a", encoding="utf-8") as f:
			f.write(line + "\n")
		return True
	except OSError as e:
		log(f"{path} could not be written: {e}", 4)
		return False


settings = common.Settings()
limiter = common.Limiter()
stats = Stats()
flag = Flag()


class SendLimit(Milter.Base):
	def __init__(self):
		self.local = False
		self.loopback = False
		self.reset()

	def reset(self):
		self.sender = None
		self.auth = None
		self.rcpts = 0

	@Milter.noreply
	def connect(self, hostname, family, hostaddr):
		# Postfix's pickup (sendmail) connects as localhost 127.0.0.1, port 0.
		self.local = isinstance(hostaddr, tuple) and len(hostaddr) >= 2 and hostaddr[1] == 0
		self.loopback = common.is_loopback(hostaddr[0] if isinstance(hostaddr, tuple) and hostaddr else None)
		return Milter.CONTINUE

	@Milter.noreply
	def envfrom(self, mailfrom, *args):
		self.reset()
		self.sender = mailfrom
		self.auth = self.getsymval("{auth_authen}")
		return Milter.CONTINUE

	@Milter.noreply
	def envrcpt(self, to, *args):
		self.rcpts += 1
		return Milter.CONTINUE

	def eom(self):
		v = settings.get()
		if not v["enabled"]:
			return Milter.ACCEPT
		if not (self.auth or self.local or self.loopback):
			return Milter.ACCEPT # from another server, without a login
		n = max(1, self.rcpts)
		who = common.sender_name(self.auth) if self.auth else ("sendmail:" if self.local else "smtp:") + common.sender_name(self.sender)
		running, held = flag.get()
		qid = self.getsymval("i")
		if running and qid and common.parse_held(f"0 {qid} 1 x"):
			wait = None if held else limiter.reserve(n, v["rate"], v["per"], SHORT_WAIT)
			if wait is None:
				# On hold behind the others; sendlimit-release.py releases it.
				if append(HELD, f"{int(time.time())} {qid} {n} {who}"):
					self.quarantine("miab-sendlimit: the box's sending limit, released by miab-sendlimit-release")
					flag.held()
					stats.add(who, n, "held")
					return Milter.ACCEPT
				wait = limiter.reserve(n, v["rate"], v["per"], MAX_WAIT)
		else:
			wait = limiter.reserve(n, v["rate"], v["per"], MAX_WAIT)
		if wait is None:
			stats.add(who, n, "deferred")
			self.setreply("451", "4.7.1", "The box sends too much mail at the moment, try again later")
			return Milter.TEMPFAIL
		stats.add(who, n, "delayed" if wait > 0 else "passed", wait)
		if wait > 0:
			time.sleep(wait)
		return Milter.ACCEPT

	def abort(self):
		self.reset()
		return Milter.CONTINUE


def flusher():
	while True:
		time.sleep(60 - time.time() % 60)
		try:
			stats.flush(settings)
		except Exception as e:
			log(f"the minute's numbers could not be written: {e}", 4)


def main():
	threading.Thread(target=flusher, daemon=True).start()
	Milter.factory = SendLimit
	Milter.set_flags(Milter.QUARANTINE) # it changes nothing in the mail, it only puts it on hold
	v = settings.get()
	log(f"started, limit {v['rate']} mails in {v['per']} s" + ("" if v["enabled"] else " (turned off)"))
	Milter.runmilter("miab-sendlimit", SOCKET, 600)


if __name__ == "__main__":
	main()
