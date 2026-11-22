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
# minute in which mail waited or was held), "held.d/<queue id>" (a file per
# mail it put on hold: "<time> <recipients> <sender>", for the release
# service) and "passed" ("<pid> <recipients>": the recipients it let through
# at once since it started, which the release service takes from its own
# bucket, so that both together keep the limit).
STATE_DIR = "/var/lib/miab-sendlimit"
# sendlimit-release.py's runtime directory (root's, 0755): "release" says that it runs
# and how many mails it still holds back; "held.json" lists them by sender.
RUN_DIR = "/run/miab-sendlimit"
FLAG = os.path.join(RUN_DIR, "release")
END = os.path.join(RUN_DIR, "end") # written by send_limit.py (root): the administrator ends the brake
RECHECK = os.path.join(RUN_DIR, "recheck") # written by send_limit.py after it released or deleted held mail
MAILINABOX_CONF = "/etc/mailinabox.conf"
HELD_JSON = os.path.join(RUN_DIR, "held.json")
FLAG_FRESH = 15 # seconds: an older flag means sendlimit-release.py does not run

# rate/per: the limit, and what sets off the brake. While the brake is on,
# all counted mail is held; "stop" 1 releases nothing until the
# administrator ends the brake, 0 releases held mail at brake_rate per
# brake_per seconds, and the brake ends by itself once nothing is held and
# no mail was held for "calm" minutes.
DEFAULTS = { "enabled": 1, "rate": 30, "per": 1, "stop": 0, "brake_rate": 10, "brake_per": 60, "calm": 30 }
LIMITS = { "enabled": (0, 1), "rate": (1, 100000), "per": (1, 86400), "stop": (0, 1), "brake_rate": (1, 100000),
	"brake_per": (1, 86400), "calm": (1, 1440) }

QID_RE = r"[0-9A-Za-z]{6,24}"
HELD_RE = re.compile(r"^([0-9]{1,12}) (" + QID_RE + r") ([0-9]{1,6}) ([^\s=]{1,210})$")
QID_ONLY = re.compile("^" + QID_RE + "$")
PASSED_RE = re.compile(r"^([0-9]{1,10}) ([0-9]{1,15})$")
MAX_HELD = 100000 # the milter holds no more mail while this many are held


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
					elif len(parts) == 2 and parts[0] == "report" and re.fullmatch(r"[^\s@=]{1,64}@[a-z0-9.-]{1,253}", parts[1].lower()):
						values["report"] = parts[1].lower() # the report recipient of System > Notifications
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
	#
	# A mail with more recipients than the bucket holds would never fit: it
	# goes as soon as the bucket is not in debt (so it does not wait for ever
	# behind a trickle of other mail) and pays in full: the next mails wait
	# until its recipients are paid for, so the rate holds over time.

	def __init__(self):
		self.lock = threading.Lock()
		self.tat = 0.0
		self.params = None

	def charge(self, n, rate, per, now=None):
		# n recipients that went out elsewhere (the milter's direct passes,
		# for the release service): taken from the bucket in full.
		now = time.monotonic() if now is None else now
		with self.lock:
			self.tat = max(self.tat, now) + n * per / rate

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
			full = now + rate * interval # the bucket is empty, not in debt, while tat <= full
			if n > rate:
				# It goes when the debt is paid (at once if there is none).
				wait = max(0.0, tat - full)
				if wait > max_wait:
					return None
				self.tat = tat + n * interval
				return wait
			wait = tat + n * interval - full
			if wait <= 0:
				self.tat = tat + n * interval
				return 0.0
			if wait > max_wait:
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
	# (the release service runs, mails it holds back, the brake is on); the
	# count and the brake are None when it does not run.
	now = time.time() if now is None else now
	try:
		with open(path, encoding="ascii") as f:
			parts = f.read(100).split()
		t, held, brake = int(parts[0]), int(parts[1]), parts[2] == "1"
	except (OSError, ValueError, IndexError):
		return False, None, None
	if not -5 <= now - t <= FLAG_FRESH:
		return False, None, None
	return True, held, brake


def admin_address(path=MAILINABOX_CONF):
	# administrator@ of the box's name: the mail of the box to its
	# administrator (management/email_administrator.py) is never held.
	try:
		with open(path, encoding="utf-8") as f:
			for line in f:
				if line.startswith("PRIMARY_HOSTNAME="):
					host = line.split("=", 1)[1].strip().strip("'\"").lower()
					if re.fullmatch(r"[a-z0-9.-]{1,253}", host):
						return "administrator@" + host
	except OSError:
		pass
	return None


def parse_held(line):
	m = HELD_RE.match(line)
	if not m:
		return None
	return { "time": int(m.group(1)), "qid": m.group(2), "rcpts": int(m.group(3)), "sender": m.group(4) }
