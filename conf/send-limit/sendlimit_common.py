# The sending limit of the box (fork, B221): what the milter (sendlimit-milter.py) and
# the release service (sendlimit-release.py) share. Both run with python3 -I, so they
# load this file from their own directory (/usr/local/lib/mailinabox/
# miab-sendlimit, root's).

import ipaddress
import os
import re
import sys
import threading
import time

SETTINGS = "/usr/local/lib/mailinabox/miab-sendlimit/settings"
# The milter's state directory (its dynamic user's): "events" (a line per
# minute in which mail waited or was held) and "held" (a line per mail it put
# on hold, for sendlimit-release.py).
STATE_DIR = "/var/lib/miab-sendlimit"
# sendlimit-release.py's runtime directory (root's, 0755): "release" says that it runs
# and how many mails it still holds back; "held.json" lists them by sender.
RUN_DIR = "/run/miab-sendlimit"
FLAG = os.path.join(RUN_DIR, "release")
HELD_JSON = os.path.join(RUN_DIR, "held.json")
FLAG_FRESH = 15 # seconds: an older flag means sendlimit-release.py does not run

DEFAULTS = { "enabled": 1, "rate": 30, "per": 1 }
LIMITS = { "enabled": (0, 1), "rate": (1, 100000), "per": (1, 86400) }

QID_RE = r"[0-9A-Za-z]{6,24}"
HELD_RE = re.compile(r"^([0-9]{1,12}) (" + QID_RE + r") ([0-9]{1,6}) ([^\s=]{1,210})$")


def log(text, level=6):
	# To the journal (SyslogIdentifier): <6> info, <4> warning.
	print(f"<{level}>{text}", file=sys.stderr, flush=True)


class Settings:
	# The settings file, read again when it changes (looked at once a second).
	def __init__(self, path=SETTINGS):
		self.path = path
		self.values = dict(DEFAULTS)
		self.mtime = None
		self.checked = 0

	def get(self):
		now = time.monotonic()
		if now - self.checked >= 1:
			self.checked = now
			try:
				mtime = os.stat(self.path).st_mtime_ns
			except OSError:
				mtime = None
			if mtime != self.mtime:
				self.mtime = mtime
				self.values = self.read(self.path)
		return self.values

	@staticmethod
	def read(path=SETTINGS):
		values = dict(DEFAULTS)
		try:
			with open(path, encoding="utf-8") as f:
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
	# RATE per PER seconds. A mail of n recipients takes n; reserve() says how
	# long it has to wait for them. Each mail reserves its time under the lock,
	# so waiting mails go out in the order they came.
	def __init__(self):
		self.lock = threading.Lock()
		self.tat = 0.0
		self.params = None

	def reserve(self, n, rate, per, max_wait, now=None):
		# Returns the seconds to wait, or None: longer than max_wait (nothing
		# is reserved then).
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
			if wait > max_wait:
				if tat <= now:
					# More recipients than fit in max_wait, and nothing else
					# waits: it goes now and the next mails wait for it.
					self.tat = tat + n * interval
					return 0.0
				return None
			self.tat = tat + n * interval
			return wait


def is_loopback(addr):
	# 127.0.0.0/8, ::1 and their IPv4-mapped form, as Postfix's mynetworks
	# of Mail-in-a-Box (the box itself).
	try:
		a = ipaddress.ip_address(str(addr).split("%")[0])
	except ValueError:
		return False
	if a.version == 6 and a.ipv4_mapped:
		a = a.ipv4_mapped
	return a.is_loopback


def sender_name(s):
	# The account (SMTP AUTH) or the envelope sender, without spaces or "="
	# (the separators of the state files), at most 200 characters.
	s = (s or "<>").strip().strip("<>") or "<>"
	return "".join(c if c.isprintable() and not c.isspace() and c != "=" else "?" for c in s)[:200]


def read_flag(path=FLAG, now=None):
	# (sendlimit-release.py runs, mails it holds back); None for the count when it does
	# not run.
	now = time.time() if now is None else now
	try:
		with open(path, encoding="ascii") as f:
			parts = f.read(100).split()
		t, held = int(parts[0]), int(parts[1])
	except (OSError, ValueError, IndexError):
		return False, None
	if not -5 <= now - t <= FLAG_FRESH:
		return False, None
	return True, held


def parse_held(line):
	m = HELD_RE.match(line)
	if not m:
		return None
	return { "time": int(m.group(1)), "qid": m.group(2), "rcpts": int(m.group(3)), "sender": m.group(4) }
