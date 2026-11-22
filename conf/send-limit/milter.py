#!/usr/bin/python3 -I
#
# The sending limit of the box (fork, B221): a Postfix milter that lets at
# most RATE mails within PER seconds go out (each recipient counts as one
# mail), for all mail that users and the box itself send: SMTP AUTH on the
# submission ports 465 and 587 (mail programs, Roundcube) and mail through
# sendmail (Z-Push's ActiveSync, Nextcloud, Sieve redirects, cron, programs
# on the box). Mail that comes in on port 25 does not pass this milter.
#
# Up to RATE mails go out at once; more wait at the end of the message until
# they fit (the rate is kept over time), at most MAX_WAIT seconds. A mail
# that would have to wait longer is deferred with a temporary error (4.7.1):
# the mail program or Postfix's pickup sends it again later. So mail is
# slowed down, never lost. Each minute in which mail had to wait is logged
# and added to the events file in the state directory, which
# management/send_limit.py --notify mails to the administrator.
#
# Setup writes the settings file (management/send_limit.py --apply) from
# settings.yaml (System > Intrusion Detection and Prevention); it is read
# again when it changes. Without it the defaults apply. Postfix passes mail
# on when this milter does not answer (milter_default_action=accept).
#
# It runs as a dynamic user without privileges (conf/miab-sendlimit.service).

import os
import sys
import threading
import time

import Milter

SETTINGS = "/usr/local/lib/mailinabox/miab-sendlimit/settings"
STATE_DIR = os.environ.get("STATE_DIRECTORY", "/var/lib/miab-sendlimit")
EVENTS = os.path.join(STATE_DIR, "events")
SOCKET = "inet:8895@127.0.0.1"
DEFAULTS = { "enabled": 1, "rate": 30, "per": 1 }
LIMITS = { "enabled": (0, 1), "rate": (1, 100000), "per": (1, 86400) }
MAX_WAIT = 60 # seconds a mail waits at most (Postfix waits 300 s for a milter)
MAX_EVENTS_FILE = 1024 * 1024 # bytes; management/send_limit.py empties it
TOP_SENDERS = 10


def log(text, level=6):
	# To the journal (SyslogIdentifier=miab-sendlimit): <6> info, <4> warning.
	print(f"<{level}>{text}", file=sys.stderr, flush=True)


class Settings:
	def __init__(self):
		self.values = dict(DEFAULTS)
		self.mtime = None
		self.checked = 0

	def get(self):
		now = time.monotonic()
		if now - self.checked >= 1:
			self.checked = now
			try:
				mtime = os.stat(SETTINGS).st_mtime_ns
			except OSError:
				mtime = None
			if mtime != self.mtime:
				self.mtime = mtime
				self.values = self.read()
		return self.values

	@staticmethod
	def read():
		values = dict(DEFAULTS)
		try:
			with open(SETTINGS, encoding="utf-8") as f:
				for line in f:
					parts = line.split()
					if len(parts) == 2 and parts[0] in LIMITS and parts[1].isdigit():
						lo, hi = LIMITS[parts[0]]
						values[parts[0]] = min(max(int(parts[1]), lo), hi)
		except FileNotFoundError:
			pass
		except OSError as e:
			log(f"the settings file could not be read, the defaults apply: {e}", 4)
		return values


class Limiter:
	# A token bucket kept as the time at which it would be full again (the
	# "theoretical arrival time" of GCRA): it holds RATE mails and refills at
	# RATE per PER seconds. A mail of n recipients takes n; it waits until
	# they are there. Each mail reserves its time under the lock, so waiting
	# mails go out in the order they came.
	def __init__(self):
		self.lock = threading.Lock()
		self.tat = 0.0
		self.params = None

	def reserve(self, n, rate, per, now=None):
		# Returns the seconds to wait, or None: wait longer than MAX_WAIT.
		now = time.monotonic() if now is None else now
		interval = per / rate
		with self.lock:
			if self.params != (rate, per):
				self.params = (rate, per)
				self.tat = min(self.tat, now + rate * interval)
			tat = max(self.tat, now)
			wait = tat + n * interval - rate * interval - now
			if wait <= 0:
				self.tat = tat + n * interval
				return 0.0
			if wait > MAX_WAIT:
				if tat <= now:
					# More recipients than fit in MAX_WAIT, and nothing else
					# waits: it goes out now and the next mails wait for it.
					self.tat = tat + n * interval
					return 0.0
				return None
			self.tat = tat + n * interval
			return wait


class Stats:
	# What had to wait, per minute: written to the events file and the log.
	def __init__(self):
		self.lock = threading.Lock()
		self.reset()

	def reset(self):
		self.delayed = 0
		self.deferred = 0
		self.passed = 0
		self.max_wait = 0.0
		self.senders = {}

	def add(self, sender, n, wait):
		with self.lock:
			if wait is None:
				self.deferred += 1
			elif wait > 0:
				self.delayed += 1
				self.max_wait = max(self.max_wait, wait)
			else:
				self.passed += 1
				return
			s = self.senders.setdefault(sender, [0, 0])
			s[0] += 1
			s[1] += n

	def flush(self, settings):
		with self.lock:
			if not self.delayed and not self.deferred:
				self.reset()
				return
			delayed, deferred, passed, max_wait = self.delayed, self.deferred, self.passed, self.max_wait
			top = sorted(self.senders.items(), key=lambda kv: (-kv[1][1], kv[0]))[:TOP_SENDERS]
			others = len(self.senders) - len(top)
			self.reset()
		v = settings.get()
		log(level=4, text=f"sending was slowed down in the last minute (limit {v['rate']} mails in {v['per']} s): {delayed} mails waited"
			f" (up to {max_wait:.0f} s), {deferred} were deferred, {passed} went out at once; senders: "
			+ ", ".join(f"{s} ({m} mails, {r} recipients)" for s, (m, r) in top) + (f" and {others} more" if others else ""))
		line = " ".join([str(int(time.time())), str(v["rate"]), str(v["per"]), str(delayed), str(deferred), str(passed),
			str(int(max_wait + 0.999)), str(others)] + [f"{s}={m}/{r}" for s, (m, r) in top])
		try:
			if os.path.getsize(EVENTS) > MAX_EVENTS_FILE:
				return
		except OSError:
			pass
		try:
			with open(EVENTS, "a", encoding="utf-8") as f:
				f.write(line + "\n")
		except OSError as e:
			log(f"the events file could not be written: {e}", 4)


settings = Settings()
limiter = Limiter()
stats = Stats()


def sender_name(s):
	# The account (SMTP AUTH) or the envelope sender, without spaces or "="
	# (the events file's separators), at most 200 characters.
	s = (s or "<>").strip().strip("<>") or "<>"
	return "".join(c if c.isprintable() and not c.isspace() and c != "=" else "?" for c in s)[:200]


class SendLimit(Milter.Base):
	def __init__(self):
		self.local = False
		self.reset()

	def reset(self):
		self.sender = None
		self.auth = None
		self.rcpts = 0

	@Milter.noreply
	def connect(self, hostname, family, hostaddr):
		# Postfix's pickup (sendmail) connects as localhost 127.0.0.1, port 0.
		self.local = isinstance(hostaddr, tuple) and len(hostaddr) >= 2 and hostaddr[1] == 0
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
		n = max(1, self.rcpts)
		who = sender_name(self.auth) if self.auth else ("sendmail:" if self.local else "smtp:") + sender_name(self.sender)
		wait = limiter.reserve(n, v["rate"], v["per"])
		stats.add(who, n, wait)
		if wait is None:
			self.setreply("451", "4.7.1", "The box sends too much mail at the moment, try again later")
			return Milter.TEMPFAIL
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
	Milter.set_flags(0) # it changes nothing in the mail
	v = settings.get()
	log(f"started, limit {v['rate']} mails in {v['per']} s" + ("" if v["enabled"] else " (turned off)"))
	Milter.runmilter("miab-sendlimit", SOCKET, 600)


if __name__ == "__main__":
	main()
