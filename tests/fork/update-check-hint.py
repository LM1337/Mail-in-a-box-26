#!/usr/bin/env python3
"""
Offline test of setup's hint at tools/update-check.sh (update_check_hint in
setup/functions.sh, called at the end of setup/start.sh) -- python3 stdlib
and bash only, no box needed.

The function runs in bash with UPDATE_CHECK_DIR set to a temporary
directory:

  * no record directory, an empty one, or a symbolic link in its place:
    the general tip;
  * the newest record has before/ but no after/: "after" and "mailcheck"
    with that record's stamp (--dir), and the tool's path in the checkout;
  * the newest record has after/ too, or has no before/time.txt: the
    general tip (an older record with only before/ does not count);
  * names that are not stamps and a symbolic link with a stamp's name are
    not taken as records;
  * the exit code is 0 in every case (it never stops setup, which runs
    with set -euo pipefail).

It also checks that setup/start.sh calls the function only when neither
FIRST_TIME_SETUP nor MIAB_SETUP_TOOL is set, and that both tools that run
setup set MIAB_SETUP_TOOL.

  tests/fork/update-check-hint.py

Exit code: 0 = all cases pass, 1 = a case failed (printed).
"""

import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
FAILED = []


def check(name, cond, detail=""):
	print("%s %s%s" % ("PASS" if cond else "FAIL", name, (": " + detail) if detail and not cond else ""))
	if not cond:
		FAILED.append(name)


def hint(root):
	env = {"PATH": "/usr/bin:/bin", "UPDATE_CHECK_DIR": root}
	p = subprocess.run(["bash", "-c", "source setup/functions.sh; update_check_hint"],
		cwd=REPO, env=env, capture_output=True, text=True, timeout=30)
	return p.returncode, p.stdout, p.stderr


def record(root, stamp, before=True, after=False):
	d = os.path.join(root, stamp)
	os.makedirs(d, mode=0o700)
	if before:
		os.makedirs(os.path.join(d, "before"))
		with open(os.path.join(d, "before", "time.txt"), "w", encoding="utf-8") as f:
			f.write("2026-11-21 10:00:00\n")
	if after:
		os.makedirs(os.path.join(d, "after"))


def general(out):
	return "Tip: tools/update-check.sh" in out and "--dir" not in out


TOOL = os.path.join(REPO, "tools", "update-check.sh")

with tempfile.TemporaryDirectory() as t:
	rc, out, err = hint(os.path.join(t, "missing"))
	check("no record directory: general tip", rc == 0 and general(out), out + err)

	empty = os.path.join(t, "empty")
	os.makedirs(empty)
	rc, out, err = hint(empty)
	check("empty record directory: general tip", rc == 0 and general(out), out + err)

	# The newest record has only before/.
	r = os.path.join(t, "r1")
	os.makedirs(r)
	record(r, "20261101-080000", after=True)
	record(r, "20261121-100000")
	os.makedirs(os.path.join(r, "notes"))
	rc, out, err = hint(r)
	check("before without after: names after --dir STAMP",
		rc == 0 and ("sudo %s after --dir 20261121-100000" % TOOL) in out, out + err)
	check("before without after: names mailcheck --dir STAMP",
		("sudo %s mailcheck --dir 20261121-100000" % TOOL) in out, out)
	check("before without after: no general tip", "Tip:" not in out, out)

	# A symbolic link with a newer stamp's name is not a record.
	os.symlink(os.path.join(r, "20261101-080000"), os.path.join(r, "20261122-000000"))
	rc, out, err = hint(r)
	check("a link with a stamp's name is not taken", "--dir 20261121-100000" in out, out + err)

	# The newest record has after/ too; an older one has only before/.
	r2 = os.path.join(t, "r2")
	os.makedirs(r2)
	record(r2, "20261101-080000")
	record(r2, "20261121-100000", after=True)
	rc, out, err = hint(r2)
	check("newest record complete: general tip (an older one does not count)", rc == 0 and general(out), out + err)

	# The newest record has no before/time.txt (before failed).
	r3 = os.path.join(t, "r3")
	os.makedirs(r3)
	record(r3, "20261121-100000", before=False)
	rc, out, err = hint(r3)
	check("newest record without before: general tip", rc == 0 and general(out), out + err)

	# A symbolic link in the place of the record directory.
	link = os.path.join(t, "link")
	os.symlink(r, link)
	rc, out, err = hint(link)
	check("link in the place of the record directory: general tip", rc == 0 and general(out), out + err)

start = open(os.path.join(REPO, "setup", "start.sh"), encoding="utf-8").read()
check("start.sh calls the hint only without FIRST_TIME_SETUP and MIAB_SETUP_TOOL",
	re.search(r'if \[ -z "\$\{FIRST_TIME_SETUP:-\}" \] && \[ -z "\$\{MIAB_SETUP_TOOL:-\}" \]; then\n\tupdate_check_hint\nfi', start) is not None)
for tool in ("upgrade-in-place-to-2604.sh", "migrate-to-2604.sh"):
	src = open(os.path.join(REPO, "tools", tool), encoding="utf-8").read()
	runs = src.count("setup/start.sh) < /dev/null")
	marks = src.count("local envs=(NONINTERACTIVE=1 SKIP_NETWORK_CHECKS=1 MIAB_SETUP_TOOL=%s" % tool)
	check("%s sets MIAB_SETUP_TOOL for its setup run" % tool, runs == 1 and marks == 1, "runs=%d marks=%d" % (runs, marks))

if FAILED:
	print("%d case(s) failed: %s" % (len(FAILED), ", ".join(FAILED)))
	sys.exit(1)
print("all cases passed")
