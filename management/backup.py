#!/usr/local/lib/mailinabox/env/bin/python

# This script performs a backup of all user data:
# 1) System services are stopped.
# 2) STORAGE_ROOT/backup/before-backup is executed if it exists.
# 3) An incremental encrypted backup is made using duplicity.
# 4) The stopped services are restarted.
# 5) STORAGE_ROOT/backup/after-backup is executed if it exists.

import os, os.path, re, datetime, sys, time
import contextlib, fcntl, hashlib, json, signal, stat
import dateutil.parser, dateutil.relativedelta, dateutil.tz
from datetime import date
import rtyaml
from exclusiveprocess import Lock

from utils import load_environment, shell, wait_for_service
import operator

# Options for every ssh connection to an rsync target (B125). Without them, ssh
# waits for the kernel's TCP retries (about two minutes) when the target does
# not answer a connection request, and a target address that does not answer
# (the IPv6 address, say) delays the next one by as long. With them, ssh gives
# an address 10 s for the connection and the SSH banner together, then tries
# the next address, and makes two such attempts.
SSH_TIMEOUT_OPTIONS = "-oConnectTimeout=10 -oConnectionAttempts=2"

# The saved status of the backups (B125). The control panel shows it at once
# and refreshes it in the background (backup.py --refresh-status, started by
# the management daemon), because a query of the target can take minutes when
# the target does not answer, and the daemon has a single worker. The status
# is saved after each backup run and after each refresh that worked, in a
# directory of root's own (STATUS_DIR, 0700), written atomically. The lock
# file there is held by the refresh and by the whole backup run, so that only
# one of them queries the target (two duplicity processes on one archive
# directory refuse each other) and the nightly backup waits for a refresh.
STATUS_DIR = ("var", "lib", "mailinabox", "backup-status")
STATUS_FILE = "status.json"
STATUS_LOCK = "lock"
# A refresh ends after this many seconds (the process is ended, duplicity
# with it). A target that does not answer took about 4 minutes in a test with
# the ssh options above (duplicity's own 5 attempts), 13 minutes without them.
REFRESH_LIMIT = 900

def reldate(date, ref, clip):
	if ref < date: return clip
	rd = dateutil.relativedelta.relativedelta(ref, date)
	if rd.years > 1: return "%d years, %d months" % (rd.years, rd.months)
	if rd.years == 1: return "%d year, %d months" % (rd.years, rd.months)
	if rd.months > 1: return "%d months, %d days" % (rd.months, rd.days)
	if rd.months == 1: return "%d month, %d days" % (rd.months, rd.days)
	if rd.days >= 7: return "%d days" % rd.days
	if rd.days > 1: return "%d days, %d hours" % (rd.days, rd.hours)
	if rd.days == 1: return "%d day, %d hours" % (rd.days, rd.hours)
	return "%d hours, %d minutes" % (rd.hours, rd.minutes)

def backup_status(env, timings=None):
	# If backups are disabled, return no status.
	config = get_backup_config(env)
	if config["target"] == "off":
		return { }

	# Query duplicity to get a list of all full and incremental
	# backups available.

	backups = { }
	now = datetime.datetime.now(dateutil.tz.tzlocal())
	backup_root = os.path.join(env["STORAGE_ROOT"], 'backup')
	backup_cache_dir = os.path.join(backup_root, 'cache')
	if timings is None:
		timings = {}

	# Get duplicity collection status and parse for a list of backups.
	def parse_line(line):
		keys = line.strip().split()
		date = dateutil.parser.parse(keys[1]).astimezone(dateutil.tz.tzlocal())
		return {
			"date": keys[1],
			"date_str": date.strftime("%Y-%m-%d %X") + " " + now.tzname(),
			"date_delta": reldate(date, now, "the future?"),
			"full": keys[0] == "full",
			"size": 0, # collection-status doesn't give us the size
			"volumes": int(keys[2]), # number of archive volumes for this backup (not really helpful)
		}

	started = time.monotonic()
	code, collection_status = shell('check_output', [
		"/usr/bin/duplicity",
		"collection-status",
		"--archive-dir", backup_cache_dir,
		"--gpg-options", "'--cipher-algo=AES256'",
		"--log-fd", "1",
		*get_duplicity_additional_args(env),
		get_duplicity_target_url(config)
		],
		get_duplicity_env_vars(env),
		# duplicity's and rsync's messages on stderr go into the error below,
		# not into the journal of the caller: they repeat what duplicity logs
		# on stdout and can name the target (B125).
		capture_stderr=True,
		trap=True)
	timings["collection-status"] = time.monotonic() - started
	timings["collection-status exit"] = code
	if code != 0:
		# Command failed. This is likely due to an improperly configured remote
		# destination for the backups or the last backup job terminated unexpectedly.
		raise Exception("Something is wrong with the backup: " + collection_status)
	for line in collection_status.split('\n'):
		if line.startswith((" full", " inc")):
			backup = parse_line(line)
			backups[backup["date"]] = backup

	# Look at the target directly to get the sizes of each of the backups. There is more than one file per backup.
	# Starting with duplicity in Ubuntu 18.04, "signatures" files have dates in their
	# filenames that are a few seconds off the backup date and so don't line up
	# with the list of backups we have. Track unmatched files so we know how much other
	# space is used for those.
	unmatched_file_size = 0
	started = time.monotonic()
	try:
		target_files = list_target_files(config, timings)
	finally:
		timings["file list"] = time.monotonic() - started
	for fn, size in target_files:
		m = re.match(r"duplicity-(full|full-signatures|(inc|new-signatures)\.(?P<incbase>\d+T\d+Z)\.to)\.(?P<date>\d+T\d+Z)\.", fn)
		if not m: continue # not a part of a current backup chain
		key = m.group("date")
		if key in backups:
			backups[key]["size"] += size
		else:
			unmatched_file_size += size

	# Ensure the rows are sorted reverse chronologically.
	# This is relied on by should_force_full() and the next step.
	backups = sorted(backups.values(), key = operator.itemgetter("date"), reverse=True)

	# Get the average size of incremental backups, the size of the
	# most recent full backup, and the date of the most recent
	# backup and the most recent full backup.
	incremental_count = 0
	incremental_size = 0
	first_date = None
	first_full_size = None
	first_full_date = None
	for bak in backups:
		if first_date is None:
			first_date = dateutil.parser.parse(bak["date"])
		if bak["full"]:
			first_full_size = bak["size"]
			first_full_date = dateutil.parser.parse(bak["date"])
			break
		incremental_count += 1
		incremental_size += bak["size"]

	# When will the most recent backup be deleted? It won't be deleted if the next
	# backup is incremental, because the increments rely on all past increments.
	# So first guess how many more incremental backups will occur until the next
	# full backup. That full backup frees up this one to be deleted. But, the backup
	# must also be at least min_age_in_days old too.
	deleted_in = None
	if incremental_count > 0 and incremental_size > 0 and first_full_size is not None:
		# How many days until the next incremental backup? First, the part of
		# the algorithm based on increment sizes:
		est_days_to_next_full = (.5 * first_full_size - incremental_size) / (incremental_size/incremental_count)
		est_time_of_next_full = first_date + datetime.timedelta(days=est_days_to_next_full)

		# ...And then the part of the algorithm based on full backup age:
		est_time_of_next_full = min(est_time_of_next_full, first_full_date + datetime.timedelta(days=config["min_age_in_days"]*10+1))

		# It still can't be deleted until it's old enough.
		est_deleted_on = max(est_time_of_next_full, first_date + datetime.timedelta(days=config["min_age_in_days"]))

		deleted_in = "approx. %d days" % round((est_deleted_on-now).total_seconds()/60/60/24 + .5)

	# When will a backup be deleted? Set the deleted_in field of each backup.
	saw_full = False
	for bak in backups:
		if deleted_in:
			# The most recent increment in a chain and all of the previous backups
			# it relies on are deleted at the same time.
			bak["deleted_in"] = deleted_in
		if bak["full"]:
			# Reset when we get to a full backup. A new chain start *next*.
			saw_full = True
			deleted_in = None
		elif saw_full and not deleted_in:
			# We're now on backups prior to the most recent full backup. These are
			# free to be deleted as soon as they are min_age_in_days old.
			deleted_in = reldate(now, dateutil.parser.parse(bak["date"]) + datetime.timedelta(days=config["min_age_in_days"]), "on next daily backup")
			bak["deleted_in"] = deleted_in

	return {
		"backups": backups,
		"unmatched_file_size": unmatched_file_size,
	}

def should_force_full(config, env):
	# Force a full backup when the total size of the increments
	# since the last full backup is greater than half the size
	# of that full backup.
	inc_size = 0
	# Check if day of week is a weekend day
	weekend = date.today().weekday()>=5
	for bak in backup_status(env)["backups"]:
		if not bak["full"]:
			# Scan through the incremental backups cumulating
			# size...
			inc_size += bak["size"]
		else:
			# ...until we reach the most recent full backup.
			# Return if we should to a full backup, which is based
			# on whether it is a weekend day, the size of the
			# increments relative to the full backup, as well as
			# the age of the full backup.
			if weekend:
				if inc_size > .5*bak["size"]:
					return True
				if dateutil.parser.parse(bak["date"]) + datetime.timedelta(days=config["min_age_in_days"]*10+1) < datetime.datetime.now(dateutil.tz.tzlocal()):
					return True
			return False
	# If we got here there are no (full) backups, so make one.
	return True

def get_passphrase(env):
	# Get the encryption passphrase. secret_key.txt is 2048 random
	# bits base64-encoded and with line breaks every 65 characters.
	# gpg will only take the first line of text, so sanity check that
	# that line is long enough to be a reasonable passphrase. It
	# only needs to be 43 base64-characters to match AES256's key
	# length of 32 bytes.
	backup_root = os.path.join(env["STORAGE_ROOT"], 'backup')
	with open(os.path.join(backup_root, 'secret_key.txt'), encoding="utf-8") as f:
		passphrase = f.readline().strip()
	if len(passphrase) < 43: raise Exception("secret_key.txt's first line is too short!")

	return passphrase

def get_duplicity_target_url(config):
	target = config["target"]

	if get_target_type(config) == "s3":
		from urllib.parse import urlsplit, urlunsplit
		target = list(urlsplit(target))

		# Although we store the S3 hostname in the target URL,
		# duplicity no longer accepts it in the target URL. The hostname in
		# the target URL must be the bucket name. The hostname is passed
		# via get_duplicity_additional_args. Move the first part of the
		# path (the bucket name) into the hostname URL component, and leave
		# the rest for the path. (The S3 region name is also stored in the
		# hostname part of the URL, in the username portion, which we also
		# have to drop here).
		target[1], target[2] = target[2].lstrip('/').split('/', 1)

		target = urlunsplit(target)

	return target

def get_duplicity_additional_args(env):
	config = get_backup_config(env)

	if get_target_type(config) == 'rsync':
		# Extract a port number for the ssh transport.  Duplicity accepts the
		# optional port number syntax in the target, but it doesn't appear to act
		# on it, so we set the ssh port explicitly via the duplicity options.
		from urllib.parse import urlsplit
		try:
			port = urlsplit(config["target"]).port
		except ValueError:
			port = 22
		if port is None:
			port = 22

		return [
			f"--ssh-options='-i /root/.ssh/id_rsa_miab -p {port} {SSH_TIMEOUT_OPTIONS}'",
			f"--rsync-options='-e \"/usr/bin/ssh -oStrictHostKeyChecking=no -oBatchMode=yes {SSH_TIMEOUT_OPTIONS} -p {port} -i /root/.ssh/id_rsa_miab\"'",
		]
	if get_target_type(config) == 's3':
		# See note about hostname in get_duplicity_target_url.
		# The region name, which is required by some non-AWS endpoints,
		# is saved inside the username portion of the URL.
		from urllib.parse import urlsplit, urlunsplit
		target = urlsplit(config["target"])
		endpoint_url = urlunsplit(("https", target.hostname, '', '', ''))
		args = ["--s3-endpoint-url", endpoint_url]
		if target.username: # region name is stuffed here
			args += ["--s3-region-name", target.username]
		return args

	return []

def get_duplicity_env_vars(env):
	config = get_backup_config(env)

	env = { "PASSPHRASE" : get_passphrase(env) }

	if get_target_type(config) == 's3':
		env["AWS_ACCESS_KEY_ID"] = config["target_user"]
		env["AWS_SECRET_ACCESS_KEY"] = config["target_pass"]
		env["AWS_REQUEST_CHECKSUM_CALCULATION"] = "WHEN_REQUIRED"
		env["AWS_RESPONSE_CHECKSUM_VALIDATION"] = "WHEN_REQUIRED"

	return env

def get_target_type(config):
	return config["target"].split(":")[0]

def _target_id(config):
	# Which target a saved status belongs to, without keeping the target
	# itself (a B2 target holds its application key).
	return hashlib.sha256(config["target"].encode("utf-8")).hexdigest()

def _open_status_dir(create):
	# STATUS_DIR as a descriptor, opened one directory at a time from /
	# without following a symbolic link; each directory must belong to root
	# and be writable by no group or other account, so that nobody else can
	# put or swap a file there. With create, the last two are made if they
	# are missing. Raises OSError (FileNotFoundError without create).
	fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
	try:
		for i, name in enumerate(STATUS_DIR):
			last = i == len(STATUS_DIR) - 1
			if create and i >= len(STATUS_DIR) - 2:
				with contextlib.suppress(FileExistsError):
					os.mkdir(name, 0o700 if last else 0o755, dir_fd=fd)
			nfd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
			os.close(fd)
			fd = nfd
			st = os.fstat(fd)
			if st.st_uid != 0 or st.st_mode & 0o022:
				raise OSError("/%s does not belong to root alone" % "/".join(STATUS_DIR[:i + 1]))
			if last and stat.S_IMODE(st.st_mode) != 0o700:
				os.fchmod(fd, 0o700)
		return fd
	except BaseException:
		os.close(fd)
		raise

def _read_saved_status(dfd):
	try:
		fd = os.open(STATUS_FILE, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=dfd)
	except FileNotFoundError:
		return {}
	with os.fdopen(fd, "rb") as f:
		if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
			return {}
		try:
			saved = json.loads(f.read(16 << 20).decode("utf-8"))
		except ValueError:
			return {}
	return saved if isinstance(saved, dict) else {}

def _write_saved_status(dfd, saved):
	# A new file (O_EXCL, 0600) in the same directory, renamed over the old one.
	data = json.dumps(saved, indent=1, sort_keys=True).encode("utf-8")
	tmp = ".%s.%s" % (STATUS_FILE, os.urandom(6).hex())
	fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=dfd)
	try:
		with os.fdopen(fd, "wb") as f:
			f.write(data)
			f.flush()
			os.fsync(f.fileno())
		os.rename(tmp, STATUS_FILE, src_dir_fd=dfd, dst_dir_fd=dfd)
	except BaseException:
		with contextlib.suppress(OSError):
			os.unlink(tmp, dir_fd=dfd)
		raise
	os.fsync(dfd)

def _lock_status(dfd, wait):
	# The descriptor of the lock file, locked exclusively, or None when it is
	# held elsewhere and wait is false. Without wait it is tried for 2 s, in
	# case the daemon is just looking whether it is held (status_refreshing).
	fd = os.open(STATUS_LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=dfd)
	try:
		if wait:
			fcntl.flock(fd, fcntl.LOCK_EX)
			return fd
		for _ in range(20):
			try:
				fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
				return fd
			except BlockingIOError:
				time.sleep(0.1)
		os.close(fd)
		return None
	except BaseException:
		os.close(fd)
		raise

def status_refreshing():
	# Whether a refresh or a backup run holds the lock (for the daemon).
	try:
		dfd = _open_status_dir(create=True)
	except OSError:
		return False
	try:
		fd = os.open(STATUS_LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=dfd)
		try:
			fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
		except BlockingIOError:
			return True
		finally:
			os.close(fd)
		return False
	finally:
		os.close(dfd)

def _mark_running(dfd, config, by):
	# Note who holds the lock since when (the caller holds it); returns the
	# saved status of the current target.
	saved = _read_saved_status(dfd)
	if saved.get("target") != _target_id(config):
		saved = { "target": _target_id(config) }
	running = saved.get("running")
	if not (by == "backup" and isinstance(running, dict) and running.get("by") == "backup" and running.get("pid") == os.getpid()):
		saved["running"] = { "by": by, "started": time.time(), "pid": os.getpid() }
		_write_saved_status(dfd, saved)
	return saved

def _save_status_locked(env, dfd, by):
	# Query the target and save the result; the caller holds the lock.
	# Returns (seconds, timings, error or None, status or None).
	config = get_backup_config(env)
	timings = {}
	started_at = time.time()
	started = time.monotonic()
	error = None
	status = None
	saved = _mark_running(dfd, config, by)
	try:
		status = backup_status(env, timings)
	except Exception as e:
		error = str(e) or e.__class__.__name__
	seconds = time.monotonic() - started
	saved.pop("running", None)
	saved["refresh"] = {
		"by": by,
		"started": started_at,
		"finished": time.time(),
		"seconds": round(seconds, 1),
		"ok": error is None,
		"error": error,
	}
	if error is None:
		saved.update({ "status": status, "time": started_at, "source": by })
	_write_saved_status(dfd, saved)
	return seconds, timings, error, status

def _timings_text(timings):
	parts = []
	if "collection-status" in timings:
		parts.append("collection-status %.1f s (exit %s)" % (timings["collection-status"], timings.get("collection-status exit")))
	if "file list" in timings:
		n = timings.get("file list attempts", 1)
		parts.append("file list %.1f s (%d attempt%s)" % (timings["file list"], n, "" if n == 1 else "s"))
	return ", ".join(parts)

def refresh_saved_status(env):
	# backup.py --refresh-status: one refresh, unless a refresh or a backup
	# run holds the lock. Logs its duration and those of its steps (to the
	# journal of the management daemon, which starts it), never the error
	# text (it can name the target). Exit code 0, 1 when the query failed.
	if get_backup_config(env)["target"] == "off":
		return 0
	log = sys.stderr
	def limit(signum, frame):
		raise TimeoutError("The refresh took longer than %d s and was ended." % REFRESH_LIMIT)
	signal.signal(signal.SIGALRM, limit)
	signal.alarm(REFRESH_LIMIT)
	try:
		dfd = _open_status_dir(create=True)
		try:
			lock = _lock_status(dfd, wait=False)
			if lock is None:
				print("backup status: not refreshed, a backup run or another refresh is in progress", file=log)
				return 0
			try:
				seconds, timings, error, _ = _save_status_locked(env, dfd, "refresh")
				signal.alarm(0)
			finally:
				os.close(lock)
		finally:
			os.close(dfd)
	except Exception:
		# Not a failed query (that is saved): the status could not be saved.
		import traceback
		print("backup status: the refresh could not save the status:", file=log)
		traceback.print_exc(file=log)
		return 1
	if error is None:
		print("backup status: refreshed in %.1f s: %s" % (seconds, _timings_text(timings)), file=log)
		return 0
	print("backup status: the refresh failed after %.1f s: %s" % (seconds, _timings_text(timings) or "no step finished"), file=log)
	return 1

def status_for_checks(env):
	# For the status checks (B128): a query of the target that saves its
	# result as a refresh does, or, while a backup run or a refresh holds the
	# lock (a second duplicity on the same archive directory would fail),
	# the saved status. Never raises for a failed query.
	# Returns (status or None, time_str of the saved status or None when it
	# was queried now, error or None).
	try:
		dfd = _open_status_dir(create=True)
	except OSError:
		dfd = None
	if dfd is None:
		try:
			return backup_status(env), None, None
		except Exception as e:
			return None, None, str(e) or e.__class__.__name__
	try:
		lock = _lock_status(dfd, wait=False)
		if lock is not None:
			try:
				_, _, error, status = _save_status_locked(env, dfd, "status checks")
			finally:
				os.close(lock)
			return status, None, error
	finally:
		os.close(dfd)
	saved = get_saved_status(env)
	return saved["status"], saved["time_str"] or "never", None

def get_saved_status(env):
	# The saved status for the control panel (GET /system/backup/status/saved).
	config = get_backup_config(env)
	ret = {
		"status": None, "time": None, "time_str": None, "age_seconds": None, "source": None,
		"refresh": None, "refreshing": False, "running": None, "now": time.time(),
	}
	if config["target"] == "off":
		ret["status"] = {}
		return ret
	try:
		dfd = _open_status_dir(create=False)
	except FileNotFoundError:
		return ret
	try:
		saved = _read_saved_status(dfd)
	finally:
		os.close(dfd)
	def time_str(t):
		t = datetime.datetime.fromtimestamp(t, dateutil.tz.tzlocal())
		return t.strftime("%Y-%m-%d %X") + " " + t.tzname()
	ret["refreshing"] = status_refreshing()
	if saved.get("target") != _target_id(config):
		return ret
	running = saved.get("running")
	if ret["refreshing"] and isinstance(running, dict) and isinstance(running.get("started"), (int, float)):
		ret["running"] = { "by": running.get("by"), "started": running["started"], "started_str": time_str(running["started"]) }
	refresh = saved.get("refresh")
	if isinstance(refresh, dict) and isinstance(refresh.get("started"), (int, float)):
		ret["refresh"] = dict(refresh, started_str=time_str(refresh["started"]))
	status = saved.get("status")
	if isinstance(status, dict) and isinstance(saved.get("time"), (int, float)):
		# The age of each backup as of now, not as of the query.
		now = datetime.datetime.now(dateutil.tz.tzlocal())
		for bak in status.get("backups", []):
			with contextlib.suppress(Exception):
				bak["date_delta"] = reldate(dateutil.parser.parse(bak["date"]).astimezone(dateutil.tz.tzlocal()), now, "the future?")
		ret.update({
			"status": status,
			"time": saved["time"],
			"time_str": time_str(saved["time"]),
			"age_seconds": max(0, int(ret["now"] - saved["time"])),
			"source": saved.get("source"),
		})
	return ret

def perform_backup(full_backup):
	env = load_environment()

	# Create an global exclusive lock so that the backup script
	# cannot be run more than one.
	Lock(die=True).forever()

	config = get_backup_config(env)
	backup_root = os.path.join(env["STORAGE_ROOT"], 'backup')
	backup_cache_dir = os.path.join(backup_root, 'cache')
	backup_dir = os.path.join(backup_root, 'encrypted')

	# Are backups disabled?
	if config["target"] == "off":
		return

	# Hold the lock of the saved status for the whole run: wait for a refresh
	# of the control panel that queries the target now, and keep new ones
	# from starting (B125). The lock goes with the process. If the directory
	# cannot be used, back up all the same (and say so in the nightly mail).
	try:
		status_dfd = _open_status_dir(create=True)
		status_lock = _lock_status(status_dfd, wait=True) # held until the process ends
		_mark_running(status_dfd, config, "backup")
	except OSError as e:
		print("The saved backup status cannot be written:", e)
		status_dfd = None

	# On the first run, always do a full backup. Incremental
	# will fail. Otherwise do a full backup when the size of
	# the increments since the most recent full backup are
	# large.
	try:
		full_backup = full_backup or should_force_full(config, env)
	except Exception as e:
		# This was the first call to duplicity, and there might
		# be an error already.
		print(e)
		sys.exit(1)

	# Stop services.
	def service_command(service, command, quit=None):
		# Execute silently, but if there is an error then display the output & exit.
		code, ret = shell('check_output', ["/usr/sbin/service", service, command], capture_stderr=True, trap=True)
		if code != 0:
			print(ret)
			if quit:
				sys.exit(code)

	service_command("php8.5-fpm", "stop", quit=True)
	service_command("postfix", "stop", quit=True)
	service_command("dovecot", "stop", quit=True)
	service_command("postgrey", "stop", quit=True)

	# Execute a pre-backup script that copies files outside the homedir.
	# Run as the STORAGE_USER user, not as root. Pass our settings in
	# environment variables so the script has access to STORAGE_ROOT.
	pre_script = os.path.join(backup_root, 'before-backup')
	if os.path.exists(pre_script):
		shell('check_call',
			['su', env['STORAGE_USER'], '-c', pre_script, config["target"]],
			env=env)

	# Run a backup of STORAGE_ROOT (but excluding the backups themselves!).
	# --allow-source-mismatch is needed in case the box's hostname is changed
	# after the first backup. See #396.
	try:
		shell('check_call', [
			"/usr/bin/duplicity",
			"full" if full_backup else "incr",
			"--verbosity", "warning", "--no-print-statistics",
			"--archive-dir", backup_cache_dir,
			"--exclude", backup_root,
			"--exclude", os.path.join(env["STORAGE_ROOT"], "owncloud-backup"),
			"--volsize", "250",
			"--gpg-options", "'--cipher-algo=AES256'",
			"--allow-source-mismatch",
			*get_duplicity_additional_args(env),
			env["STORAGE_ROOT"],
			get_duplicity_target_url(config),
			],
			get_duplicity_env_vars(env))
	finally:
		# Start services again.
		service_command("postgrey", "start", quit=False)
		service_command("dovecot", "start", quit=False)
		service_command("postfix", "start", quit=False)
		service_command("php8.5-fpm", "start", quit=False)

	# Remove old backups. This deletes all backup data no longer needed
	# from more than 3 days ago.
	shell('check_call', [
		"/usr/bin/duplicity",
		"remove-older-than",
		"%dD" % config["min_age_in_days"],
		"--verbosity", "error",
		"--archive-dir", backup_cache_dir,
		"--force",
		*get_duplicity_additional_args(env),
		get_duplicity_target_url(config)
		],
		get_duplicity_env_vars(env))

	# From duplicity's manual:
	# "This should only be necessary after a duplicity session fails or is
	# aborted prematurely."
	# That may be unlikely here but we may as well ensure we tidy up if
	# that does happen - it might just have been a poorly timed reboot.
	shell('check_call', [
		"/usr/bin/duplicity",
		"cleanup",
		"--verbosity", "error",
		"--archive-dir", backup_cache_dir,
		"--force",
		*get_duplicity_additional_args(env),
		get_duplicity_target_url(config)
		],
		get_duplicity_env_vars(env))

	# Save the status of the backups as they are now, for the control panel
	# (B125). A failed query is saved as the result of this refresh; the
	# status of the last query that worked stays. Nothing is printed: the
	# panel shows it, and this script's output is the nightly mail.
	if status_dfd is not None:
		with contextlib.suppress(OSError):
			_save_status_locked(env, status_dfd, "backup")

	# Change ownership of backups to the user-data user, so that the after-bcakup
	# script can access them.
	if get_target_type(config) == 'file':
		shell('check_call', ["/bin/chown", "-R", env["STORAGE_USER"], backup_dir])

	# Execute a post-backup script that does the copying to a remote server.
	# Run as the STORAGE_USER user, not as root. Pass our settings in
	# environment variables so the script has access to STORAGE_ROOT.
	post_script = os.path.join(backup_root, 'after-backup')
	if os.path.exists(post_script):
		shell('check_call',
			['su', env['STORAGE_USER'], '-c', post_script, config["target"]],
			env=env)

	# Our nightly cron job executes system status checks immediately after this
	# backup. Since it checks that dovecot and postfix are running, block for a
	# bit (maximum of 10 seconds each) to give each a chance to finish restarting
	# before the status checks might catch them down. See #381.
	wait_for_service(25, True, env, 10)
	wait_for_service(993, True, env, 10)

def run_duplicity_verification():
	env = load_environment()
	backup_root = os.path.join(env["STORAGE_ROOT"], 'backup')
	config = get_backup_config(env)
	backup_cache_dir = os.path.join(backup_root, 'cache')

	shell('check_call', [
		"/usr/bin/duplicity",
		"--verbosity", "info",
		"verify",
		"--compare-data",
		"--archive-dir", backup_cache_dir,
		"--exclude", backup_root,
		"--exclude", os.path.join(env["STORAGE_ROOT"], "owncloud-backup"),
		*get_duplicity_additional_args(env),
		get_duplicity_target_url(config),
		env["STORAGE_ROOT"],
	], get_duplicity_env_vars(env))

def run_duplicity_restore(args):
	env = load_environment()
	config = get_backup_config(env)
	backup_cache_dir = os.path.join(env["STORAGE_ROOT"], 'backup', 'cache')
	shell('check_call', [
		"/usr/bin/duplicity",
		"restore",
		"--archive-dir", backup_cache_dir,
		*get_duplicity_additional_args(env),
		get_duplicity_target_url(config),
		*args],
		get_duplicity_env_vars(env))

def print_duplicity_command():
	import shlex
	env = load_environment()
	config = get_backup_config(env)
	backup_cache_dir = os.path.join(env["STORAGE_ROOT"], 'backup', 'cache')
	for k, v in get_duplicity_env_vars(env).items():
		print(f"export {k}={shlex.quote(v)}")
	print("duplicity", "{command}", shlex.join([
		"--archive-dir", backup_cache_dir,
		*get_duplicity_additional_args(env),
		get_duplicity_target_url(config)
		]))

def list_target_files(config, timings=None):
	import urllib.parse
	try:
		target = urllib.parse.urlparse(config["target"])
	except ValueError:
		return "invalid target"

	if target.scheme == "file":
		return [(fn, os.path.getsize(os.path.join(target.path, fn))) for fn in os.listdir(target.path)]

	if target.scheme == "rsync":
		rsync_fn_size_re = re.compile(r'.*    ([^ ]*) [^ ]* [^ ]* (.*)')
		rsync_target = '{host}:{path}'

		# Strip off any trailing port specifier because it's not valid in rsync's
		# DEST syntax.  Explicitly set the port number for the ssh transport.
		user_host, *_ = target.netloc.rsplit(':', 1)
		try:
			port = target.port
		except ValueError:
			 port = 22
		if port is None:
			port = 22

		target_path = target.path
		if not target_path.endswith('/'):
			target_path += '/'
		target_path = target_path.removeprefix('/')

		rsync_command = [ 'rsync',
					'-e',
					f'/usr/bin/ssh -i /root/.ssh/id_rsa_miab -oStrictHostKeyChecking=no -oBatchMode=yes {SSH_TIMEOUT_OPTIONS} -p {port}',
					'--list-only',
					'-r',
					rsync_target.format(
						host=user_host,
						path=target_path)
				]

		# duplicity retries its own connections, this one is ours: try twice
		# more (B125), unless the target turned us away. The nightly backup
		# stops when it fails (should_force_full).
		for attempt in range(3):
			code, listing = shell('check_output', rsync_command, trap=True, capture_stderr=True)
			if timings is not None:
				timings["file list attempts"] = attempt + 1
			if code == 0 or attempt == 2 or 'Permission denied (' in listing or 'No such file or directory' in listing:
				break
			time.sleep(5)
		if code == 0:
			ret = []
			for l in listing.split('\n'):
				match = rsync_fn_size_re.match(l)
				if match:
					ret.append( (match.groups()[1], int(match.groups()[0].replace(',',''))) )
			return ret
		if 'Permission denied (publickey).' in listing:
			reason = "Invalid user or check you correctly copied the SSH key."
		elif 'No such file or directory' in listing:
			reason = f"Provided path {target_path} is invalid."
		elif 'Network is unreachable' in listing:
			reason = f"The IP address {target.hostname} is unreachable."
		elif 'Could not resolve hostname' in listing:
			reason = f"The hostname {target.hostname} cannot be resolved."
		else:
			reason = ("Unknown error."
					"Please check running 'management/backup.py --verify'"
					"from mailinabox sources to debug the issue.")
		msg = f"Connection to rsync host failed: {reason}"
		raise ValueError(msg)

	if target.scheme == "s3":
		import boto3.s3
		from botocore.exceptions import ClientError

		# separate bucket from path in target
		bucket_path = target.path.lstrip('/')
		bucket, _, path = bucket_path.partition('/')
		if path and not path.endswith('/'):
			path += '/'

		if bucket == "":
			msg = "Enter an S3 bucket name."
			raise ValueError(msg)

		# connect to the region & bucket
		try:
			if config['target_user'] == "" and config['target_pass'] == "":
				s3 = boto3.client('s3', endpoint_url=f'https://{target.hostname}')
			else:
				s3 = boto3.client('s3', \
					endpoint_url=f'https://{target.hostname}', \
					aws_access_key_id=config['target_user'], \
					aws_secret_access_key=config['target_pass'])
			response = s3.list_objects_v2(Bucket=bucket, Prefix=path)
			bucket_objects = response.get('Contents', [])
			backup_list = [(key['Key'][len(path):], key['Size']) for key in bucket_objects]
		except ClientError as e:
			raise ValueError(e)
		return backup_list
	if target.scheme == 'b2':
		from b2sdk.v1 import InMemoryAccountInfo, B2Api
		from b2sdk.v1.exception import NonExistentBucket
		info = InMemoryAccountInfo()
		b2_api = B2Api(info)

		# Extract information from target
		b2_application_keyid = target.netloc[:target.netloc.index(':')]
		b2_application_key = urllib.parse.unquote(target.netloc[target.netloc.index(':')+1:target.netloc.index('@')])
		b2_bucket = target.netloc[target.netloc.index('@')+1:]

		try:
			b2_api.authorize_account("production", b2_application_keyid, b2_application_key)
			bucket = b2_api.get_bucket_by_name(b2_bucket)
		except NonExistentBucket:
			msg = "B2 Bucket does not exist. Please double check your information!"
			raise ValueError(msg)
		return [(key.file_name, key.size) for key, _ in bucket.ls()]

	raise ValueError(config["target"])


def backup_set_custom(env, target, target_user, target_pass, min_age):
	config = get_backup_config(env, for_save=True)

	# min_age must be an int
	if isinstance(min_age, str):
		min_age = int(min_age)

	config["target"] = target
	config["target_user"] = target_user
	config["target_pass"] = target_pass
	config["min_age_in_days"] = min_age

	# Validate.
	try:
		if config["target"] not in {"off", "local"}:
			# these aren't supported by the following function, which expects a full url in the target key,
			# which is what is there except when loading the config prior to saving
			list_target_files(config)
	except ValueError as e:
		return str(e)

	write_backup_config(env, config)

	return "OK"

def get_backup_config(env, for_save=False, for_ui=False):
	backup_root = os.path.join(env["STORAGE_ROOT"], 'backup')

	# Defaults.
	config = {
		"min_age_in_days": 3,
		"target": "local",
	}

	# Merge in anything written to custom.yaml.
	try:
		with open(os.path.join(backup_root, 'custom.yaml'), encoding="utf-8") as f:
			custom_config = rtyaml.load(f)
		if not isinstance(custom_config, dict): raise ValueError # caught below
		config.update(custom_config)
	except:
		pass

	# When updating config.yaml, don't do any further processing on what we find.
	if for_save:
		return config

	# When passing this back to the admin to show the current settings, do not include
	# authentication details. The user will have to re-enter it.
	if for_ui:
		for field in ("target_user", "target_pass"):
			config.pop(field, None)

	# helper fields for the admin
	config["file_target_directory"] = os.path.join(backup_root, 'encrypted')
	config["enc_pw_file"] = os.path.join(backup_root, 'secret_key.txt')
	if config["target"] == "local":
		# Expand to the full URL.
		config["target"] = "file://" + config["file_target_directory"]
	ssh_pub_key = os.path.join('/root', '.ssh', 'id_rsa_miab.pub')
	if os.path.exists(ssh_pub_key):
		with open(ssh_pub_key, encoding="utf-8") as f:
			config["ssh_pub_key"] = f.read()

	return config

def write_backup_config(env, newconfig):
	backup_root = os.path.join(env["STORAGE_ROOT"], 'backup')
	with open(os.path.join(backup_root, 'custom.yaml'), "w", encoding="utf-8") as f:
		f.write(rtyaml.dump(newconfig))

if __name__ == "__main__":
	if sys.argv[-1] == "--verify":
		# Run duplicity's verification command to check a) the backup files
		# are readable, and b) report if they are up to date.
		run_duplicity_verification()

	elif sys.argv[-1] == "--list":
		# List the saved backup files.
		for fn, size in list_target_files(get_backup_config(load_environment())):
			print(f"{fn}\t{size}")

	elif sys.argv[-1] == "--refresh-status":
		# Refresh the saved status for the control panel (started by the
		# management daemon in the background, B125).
		sys.exit(refresh_saved_status(load_environment()))

	elif sys.argv[-1] == "--status":
		# Show backup status.
		ret = backup_status(load_environment())
		print(rtyaml.dump(ret["backups"]))
		print("Storage for unmatched files:", ret["unmatched_file_size"])

	elif len(sys.argv) >= 2 and sys.argv[1] == "--restore":
		# Run duplicity restore. Rest of command line passed as arguments
		# to duplicity. The restore path should be specified.
		run_duplicity_restore(sys.argv[2:])

	elif sys.argv[-1] == "--duplicity-command":
		print_duplicity_command()

	else:
		# Perform a backup. Add --full to force a full backup rather than
		# possibly performing an incremental backup.
		full_backup = "--full" in sys.argv
		perform_backup(full_backup)
