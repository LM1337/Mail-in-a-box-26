#!/usr/bin/python3 -I
#
# Remove old copies of Nextcloud's backups that setup keeps:
#
#   tools/owncloud_backup_prune.py STORAGE_ROOT [KEEP]
#
# setup/nextcloud.sh makes a new directory in $STORAGE_ROOT/owncloud-backup
# for every update of Nextcloud and of its pinned apps (B176), named after
# the time of the update (date +%Y-%m-%d-%T, e.g. 2026-11-19-12:00:00), with
# a copy of the database, config.php and the replaced code. Nothing removed
# them, and the directory is not in the box's backup. This keeps the KEEP
# newest of these directories (default 3) and every one of the last
# MIN_AGE_DAYS days (by its name), and removes the older ones: a failed
# upgrade of Nextcloud leaves config.php at the old version, so each later
# run of setup makes another copy, of the half-upgraded state, and a count
# alone would remove the copy of the state before the upgrade after three
# such runs. Other names in owncloud-backup (copies an administrator put
# there), and a name that is not a valid time, are left alone.
#
# The storage user owns $STORAGE_ROOT and could put a symbolic link in the
# place of owncloud-backup at any moment, so the directory is opened once,
# without following a link (tools/write_conf.py's open_dir for the path to
# STORAGE_ROOT, O_NOFOLLOW for owncloud-backup), and everything below is
# done through that descriptor: it must be a directory of root's own that no
# other account may write (0700 since B177), and the copies in it are
# removed with shutil.rmtree(dir_fd=...), which does not follow symbolic
# links. Only directories are removed; anything else with such a name is
# left alone.
#
# Exit code 0 (also when nothing was removed or owncloud-backup does not
# exist), 1 when owncloud-backup could not be checked or a copy could not be
# removed (printed); setup goes on either way.

import os
import re
import shutil
import stat
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from write_conf import open_dir

STAMP = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{2}:[0-9]{2}:[0-9]{2}$")
DEFAULT_KEEP = 3
MIN_AGE_DAYS = 14


def age_days(name, now):
	"""The age in days of the copy named after its local time, or None."""
	try:
		made = time.mktime(time.strptime(name, "%Y-%m-%d-%H:%M:%S"))
	except (ValueError, OverflowError):
		return None
	return (now - made) / 86400


def copies(dfd):
	"""The names of the backup copies in the directory dfd, oldest first."""
	names = []
	for name in os.listdir(dfd):
		if not STAMP.match(name):
			continue
		st = os.stat(name, dir_fd=dfd, follow_symlinks=False)
		if stat.S_ISDIR(st.st_mode):
			names.append(name)
	return sorted(names)


def prune(storage_root, keep=DEFAULT_KEEP, owner=0, now=None, min_age_days=MIN_AGE_DAYS):
	"""Returns (removed names, problems). owner: the uid that must own
	owncloud-backup (root; the offline test passes its own)."""
	now = time.time() if now is None else now
	if keep < 1:
		raise ValueError("KEEP must be at least 1")
	if not shutil.rmtree.avoids_symlink_attacks:
		return [], ["this Python's shutil.rmtree cannot remove a tree without following symbolic links"]
	root_fd = open_dir(storage_root)
	try:
		try:
			bfd = os.open("owncloud-backup", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
		except FileNotFoundError:
			return [], []
		except OSError:
			return [], ["%s/owncloud-backup is not a directory (a symbolic link or a file); left alone" % storage_root]
	finally:
		os.close(root_fd)
	removed, problems = [], []
	try:
		st = os.fstat(bfd)
		if st.st_uid != owner or st.st_mode & 0o022:
			return [], ["%s/owncloud-backup is not a directory of root's own that only root may write; left alone" % storage_root]
		names = copies(bfd)
		for name in names[:-keep]:
			age = age_days(name, now)
			if age is None or age < min_age_days:
				continue
			try:
				shutil.rmtree(name, dir_fd=bfd)
				removed.append(name)
			except OSError as e:
				problems.append("could not remove %s/owncloud-backup/%s: %s" % (storage_root, name, e))
	finally:
		os.close(bfd)
	return removed, problems


def main(argv):
	if len(argv) not in (2, 3) or not argv[1].startswith("/"):
		print("usage: owncloud_backup_prune.py STORAGE_ROOT [KEEP]", file=sys.stderr)
		return 1
	keep = DEFAULT_KEEP
	if len(argv) == 3:
		if not re.fullmatch(r"[1-9][0-9]{0,2}", argv[2]):
			print("owncloud_backup_prune.py: KEEP must be a number from 1 to 999", file=sys.stderr)
			return 1
		keep = int(argv[2])
	try:
		removed, problems = prune(argv[1], keep)
	except OSError as e:
		removed, problems = [], ["%s: %s" % (argv[1], e)]
	if removed:
		print("Removed %d old Nextcloud backup cop%s from %s/owncloud-backup (kept the newest %d and those of the last %d days): %s"
			% (len(removed), "y" if len(removed) == 1 else "ies", argv[1], keep, MIN_AGE_DAYS, ", ".join(removed)))
	for p in problems:
		print("owncloud_backup_prune.py: %s" % p, file=sys.stderr)
	return 1 if problems else 0


if __name__ == "__main__":
	sys.exit(main(sys.argv))
