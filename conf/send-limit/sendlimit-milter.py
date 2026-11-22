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
# Up to RATE mails go out at once, then RATE per PER seconds. The first mail
# that does not fit sets off the brake: Postfix accepts it and puts it on
# hold (its hold queue), and from then on all counted mail is held. The
# release service (sendlimit-release.py, miab-sendlimit-release) mails the
# administrator at once and, as set, releases nothing until the
# administrator ends the brake ("stop"), or releases held mail very slowly
# (BRAKE_RATE per BRAKE_PER seconds, the senders in turn) and ends the brake
# by itself once nothing is held and nothing was held for a while. So an
# account that was taken over gets a few dozen mails out, not thousands, and
# the administrator can delete the rest. The sender never sees an error.
# Mail to administrator@ of the box alone (the box's own reports) is never
# held.
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
# Detection and Prevention); it is read again when it changes. When this
# milter does not answer, Postfix refuses the mail with a temporary error
# (default_action tempfail for this milter only, setup/dkim.sh): it fails
# closed, so a crash never lets mail out without the limit.
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
HELD_DIR = os.path.join(STATE_DIR, "held.d")
PASSED = os.path.join(STATE_DIR, "passed")
SOCKET = "inet:8895@127.0.0.1"
SHORT_WAIT = 0 # seconds a mail waits for room before it is put on hold
MAX_WAIT = 20 # seconds an SMTP mail waits at most without the release service: mail programs and
	# webmail give up after about 60 s, and a mail that Postfix accepts after they gave up is sent twice
MAX_WAIT_LOCAL = 60 # through sendmail nobody waits for the answer (Postfix waits 300 s for a milter)
MAX_STATE_FILE = 4 * 1024 * 1024 # bytes; send_limit.py and sendlimit-release.py empty them
TOP_SENDERS = 10
log = common.log


class Flag:
	# The release service's flag, looked at once a second: (it runs, mails
	# on hold, the brake is on).
	def __init__(self):
		self.value = (False, None, None)
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
			running, held, brake = self.value
			return running, (held or 0) + self.held_here, bool(brake) or self.held_here > 0

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


def record_held(qid, n, who):
	# A file per held mail, written under a temporary name and renamed, so
	# that the release service reads it whole or not at all.
	try:
		os.makedirs(HELD_DIR, mode=0o700, exist_ok=True)
		tmp = os.path.join(HELD_DIR, f".{qid}.tmp")
		fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
		try:
			os.write(fd, f"{int(time.time())} {n} {who}\n".encode("utf-8"))
		finally:
			os.close(fd)
		os.rename(tmp, os.path.join(HELD_DIR, qid))
		return True
	except OSError as e:
		log(f"a held mail could not be recorded ({e}); it is not held", 4)
		return False


class Passed:
	# Recipients let through at once, for the release service's bucket.
	def __init__(self):
		self.lock = threading.Lock()
		self.wlock = threading.Lock() # one writer at a time (the writer thread, a mail put on hold)
		self.total = 0
		self.written = -1

	def add(self, n):
		with self.lock:
			self.total += n

	def write(self):
		with self.wlock:
			self._write()

	def _write(self):
		with self.lock:
			total = self.total
		if total == self.written:
			return
		try:
			tmp = PASSED + ".tmp"
			fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
			try:
				os.write(fd, f"{os.getpid()} {total}\n".encode("ascii"))
			finally:
				os.close(fd)
			os.rename(tmp, PASSED)
			self.written = total
		except OSError as e:
			log(f"{PASSED} could not be written: {e}", 4)


settings = common.Settings()
passed = Passed()
ADMIN = common.admin_address()
limiter = common.Limiter()
long_limiter = common.Limiter()


def reserve(n, v, max_wait):
	# The mail must fit the short limit and, when it is on, the long one.
	return common.reserve_all(common.limit_pairs(v, limiter, long_limiter), n, max_wait)
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
		self.to_admin = True

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
		if (to or "").strip().strip("<>").lower() not in (ADMIN, settings.get().get("report")) or not (self.loopback and not self.auth):
			self.to_admin = False # only SMTP from the box itself without a login, as management/email_administrator.py sends
		return Milter.CONTINUE

	def eom(self):
		v = settings.get()
		if not v["enabled"]:
			return Milter.ACCEPT
		if not (self.auth or self.local or self.loopback):
			return Milter.ACCEPT # from another server, without a login
		if self.rcpts and self.to_admin:
			return Milter.ACCEPT # the box's mail to its administrator alone
		n = max(1, self.rcpts)
		who = common.sender_name(self.auth) if self.auth else ("sendmail:" if self.local else "smtp:") + common.sender_name(self.sender)
		running, held, brake = flag.get()
		qid = self.getsymval("i")
		if running and qid and common.QID_ONLY.match(qid) and held < common.MAX_HELD:
			wait = None if (brake or held) else reserve(n, v, SHORT_WAIT)
			if wait is None:
				# On hold behind the others; sendlimit-release.py releases it.
				# The count of the direct passes is written first, so that the
				# release service has charged them when it sees this mail.
				passed.write()
				if record_held(qid, n, who):
					self.quarantine("miab-sendlimit: the box's sending limit, released by miab-sendlimit-release")
					flag.held()
					stats.add(who, n, "held")
					return Milter.ACCEPT
				wait = reserve(n, v, MAX_WAIT_LOCAL if self.local else MAX_WAIT)
		else:
			wait = reserve(n, v, MAX_WAIT_LOCAL if self.local else MAX_WAIT)
		if wait is None:
			stats.add(who, n, "deferred")
			self.setreply("451", "4.7.1", "The box sends too much mail at the moment, try again later")
			return Milter.TEMPFAIL
		stats.add(who, n, "delayed" if wait > 0 else "passed", wait)
		passed.add(n)
		if wait > 0:
			time.sleep(wait)
		return Milter.ACCEPT

	def abort(self):
		self.reset()
		return Milter.CONTINUE


def passed_writer():
	while True:
		time.sleep(0.5)
		passed.write()


def flusher():
	while True:
		time.sleep(60 - time.time() % 60)
		try:
			stats.flush(settings)
		except Exception as e:
			log(f"the minute's numbers could not be written: {e}", 4)


def main():
	threading.Thread(target=flusher, daemon=True).start()
	threading.Thread(target=passed_writer, daemon=True).start()
	Milter.factory = SendLimit
	Milter.set_flags(Milter.QUARANTINE) # it changes nothing in the mail, it only puts it on hold
	v = settings.get()
	log(f"started, limit {v['rate']} mails in {v['per']} s" + ("" if v["enabled"] else " (turned off)"))
	Milter.runmilter("miab-sendlimit", SOCKET, 600)


if __name__ == "__main__":
	main()
