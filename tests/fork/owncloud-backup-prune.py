#!/usr/bin/env python3
"""
Offline test of tools/owncloud_backup_prune.py -- python3 stdlib only, no
box needed.

setup/nextcloud.sh keeps the newest copies of Nextcloud's backups in
$STORAGE_ROOT/owncloud-backup and removes the older ones. In a temporary
STORAGE_ROOT:

  * with five copies (named like setup names them), the three newest stay
    and the two oldest are removed, with everything in them;
  * names that setup does not make (an administrator's copy, a name with
    another date format) and a file or a symbolic link with a copy's name
    stay;
  * a symbolic link in the place of owncloud-backup, or a directory that
    others may write, is left alone and reported, and nothing it points to
    is removed;
  * a symbolic link inside an old copy is removed, not followed (its target
    stays);
  * no owncloud-backup: nothing to do, no problem; KEEP 1 keeps only the
    newest; the command line refuses a bad KEEP;
  * copies of the last 14 days stay beyond KEEP (an upgrade that failed and
    was run again three times keeps the copy from before it), and a name
    that is not a valid time stays.

The owner check (root in setup) is given the test's own uid.

  tests/fork/owncloud-backup-prune.py

Exit code: 0 = all cases pass, 1 = a case failed (printed).
"""

import importlib.util
import io
import os
import sys
import tempfile
import time
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.abspath(os.path.join(HERE, "..", "..", "tools", "owncloud_backup_prune.py"))

spec = importlib.util.spec_from_file_location("owncloud_backup_prune", TOOL)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

FAILED = []


def check(name, cond, detail=""):
	print("%s %s%s" % ("PASS" if cond else "FAIL", name, (": " + detail) if detail and not cond else ""))
	if not cond:
		FAILED.append(name)


def make_copy(base, name, with_link_to=None):
	d = os.path.join(base, name)
	os.makedirs(os.path.join(d, "owncloud-install", "apps"))
	with open(os.path.join(d, "owncloud.db"), "w") as f:
		f.write("db")
	with open(os.path.join(d, "owncloud-install", "apps", "x.php"), "w") as f:
		f.write("<?php")
	if with_link_to:
		os.symlink(with_link_to, os.path.join(d, "link"))
	return d


STAMPS = ["2026-01-02-03:04:05", "2026-03-01-10:00:00", "2026-03-01-10:00:01",
	"2026-10-27-23:59:59", "2026-11-19-12:00:00"]

with tempfile.TemporaryDirectory() as t:
	uid = os.getuid()

	# 1. Five copies, other names, a link inside an old copy.
	sr = os.path.join(t, "sr1")
	ob = os.path.join(sr, "owncloud-backup")
	os.makedirs(ob, mode=0o700)
	victim = os.path.join(t, "victim")
	os.makedirs(victim)
	with open(os.path.join(victim, "keep.txt"), "w") as f:
		f.write("keep")
	for i, s in enumerate(STAMPS):
		make_copy(ob, s, with_link_to=victim if i == 0 else None)
	os.makedirs(os.path.join(ob, "my-own-copy"))
	os.makedirs(os.path.join(ob, "2025-12-31"))
	with open(os.path.join(ob, "2025-01-01-00:00:00"), "w") as f:
		f.write("a file with a copy's name")
	os.symlink(victim, os.path.join(ob, "2025-01-01-00:00:01"))
	os.chmod(ob, 0o700)
	removed, problems = mod.prune(sr, 3, owner=uid)
	check("five copies: the two oldest removed", removed == STAMPS[:2], repr(removed))
	check("five copies: no problem", problems == [], repr(problems))
	left = sorted(os.listdir(ob))
	check("five copies: the three newest stay", all(s in left for s in STAMPS[2:]), repr(left))
	check("five copies: the old ones are gone", not any(s in left for s in STAMPS[:2]), repr(left))
	check("other names stay", all(n in left for n in ["my-own-copy", "2025-12-31", "2025-01-01-00:00:00", "2025-01-01-00:00:01"]), repr(left))
	check("a link inside an old copy is not followed", os.path.exists(os.path.join(victim, "keep.txt")))
	check("the newest copy keeps its content", os.path.exists(os.path.join(ob, STAMPS[-1], "owncloud-install", "apps", "x.php")))

	# Again: nothing more to remove.
	removed, problems = mod.prune(sr, 3, owner=uid)
	check("second run removes nothing", removed == [] and problems == [], repr((removed, problems)))

	# KEEP 1.
	removed, problems = mod.prune(sr, 1, owner=uid)
	check("KEEP 1 keeps only the newest", removed == STAMPS[2:4] and os.path.isdir(os.path.join(ob, STAMPS[-1])), repr(removed))

	# Copies of the last 14 days stay beyond KEEP: a failed upgrade (A), two
	# more failed runs (B, C) and a success with an app update (D, E) on the
	# same days; A stays until it is 14 days old.
	sr7 = os.path.join(t, "sr7")
	ob7 = os.path.join(sr7, "owncloud-backup")
	os.makedirs(ob7, mode=0o700)
	RECENT = ["2026-11-20-10:00:00", "2026-11-20-10:30:00", "2026-11-20-11:00:00", "2026-11-21-09:00:00", "2026-11-21-09:05:00"]
	for s in RECENT + ["2026-02-30-00:00:00"]:
		make_copy(ob7, s)
	day = 86400
	now = time.mktime(time.strptime("2026-11-21-12:00:00", "%Y-%m-%d-%H:%M:%S"))
	removed, problems = mod.prune(sr7, 3, owner=uid, now=now)
	check("copies of the last 14 days stay beyond KEEP", removed == [] and problems == [], repr((removed, problems)))
	removed, problems = mod.prune(sr7, 3, owner=uid, now=now + 15 * day)
	check("after 14 days only the newest KEEP stay", removed == RECENT[:2] and problems == [], repr((removed, problems)))
	check("a name that is not a valid time stays", os.path.isdir(os.path.join(ob7, "2026-02-30-00:00:00")))

	# 2. owncloud-backup is a symbolic link to a directory with copies.
	sr2 = os.path.join(t, "sr2")
	os.makedirs(sr2)
	target = os.path.join(t, "elsewhere")
	os.makedirs(target, mode=0o700)
	for s in STAMPS:
		make_copy(target, s)
	os.symlink(target, os.path.join(sr2, "owncloud-backup"))
	removed, problems = mod.prune(sr2, 3, owner=uid)
	check("link in the place of owncloud-backup: nothing removed", removed == [] and len(os.listdir(target)) == 5, repr(removed))
	check("link in the place of owncloud-backup: reported", len(problems) == 1 and "not a directory" in problems[0], repr(problems))

	# 3. A directory that others may write.
	sr3 = os.path.join(t, "sr3")
	ob3 = os.path.join(sr3, "owncloud-backup")
	os.makedirs(ob3)
	for s in STAMPS:
		make_copy(ob3, s)
	os.chmod(ob3, 0o777)
	removed, problems = mod.prune(sr3, 3, owner=uid)
	check("writable by others: nothing removed", removed == [] and len(os.listdir(ob3)) == 5, repr(removed))
	check("writable by others: reported", len(problems) == 1 and "only root may write" in problems[0], repr(problems))
	os.chmod(ob3, 0o700)

	# 4. Another owner (root in setup).
	removed, problems = mod.prune(sr3, 3, owner=uid + 1)
	check("another owner: nothing removed", removed == [] and len(problems) == 1, repr((removed, problems)))

	# 5. No owncloud-backup.
	sr5 = os.path.join(t, "sr5")
	os.makedirs(sr5)
	removed, problems = mod.prune(sr5, 3, owner=uid)
	check("no owncloud-backup: nothing to do", removed == [] and problems == [], repr((removed, problems)))

	# 6. Command line.
	for bad in (["x", "relative/path"], ["x", t, "0"], ["x", t, "-1"], ["x", t, "3x"], ["x"]):
		err = io.StringIO()
		with redirect_stderr(err), redirect_stdout(io.StringIO()):
			rc = mod.main(bad)
		check("command line refuses %r" % bad[1:], rc == 1)

if FAILED:
	print("%d case(s) failed: %s" % (len(FAILED), ", ".join(FAILED)))
	sys.exit(1)
print("all cases passed")
