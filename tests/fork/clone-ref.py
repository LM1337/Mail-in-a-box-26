#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Offline test of the fresh clone of a tag, a branch or a commit id -- python3
stdlib and git only, no box needed (B188).

tools/upgrade-in-place-to-2604.sh and tools/migrate-to-2604.sh clone the
fork with clone_ref(), and setup/bootstrap.sh clones it for a first
install, at TAG. "git clone -b" takes a tag or a branch but no commit id,
so TAG=<commit id> failed in these three places (an update of an existing
checkout fetched it already). This test makes a repository in a temporary
directory (a branch, a tag, a commit only reachable from the branch) and
checks with file:// URLs:

  * clone_ref of both tools clones a tag, a branch and a full commit id
    (HEAD at that commit), and fails for a short commit id (with the hint
    to give the full one) and for a commit id that the source does not
    have, without leaving the directory behind;
  * the clone block of bootstrap.sh does the same for a full commit id and
    a tag, and stops with a message for an unknown commit id, a short
    commit id (with the hint) and an unknown tag, leaving no directory;
  * neither tool clones with "git clone -b $tag" any more.

  tests/fork/clone-ref.py

Exit code: 0 = all cases pass, 1 = a case failed (printed).
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
FAILED = []


def check(name, got, want):
	ok = got == want
	print("%s %s%s" % ("ok  " if ok else "FAIL", name, "" if ok else ": want %r, got %r" % (want, got)))
	if not ok:
		FAILED.append(name)


def git(*args, cwd=None):
	env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t",
		GIT_COMMITTER_EMAIL="t@example.com", GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1")
	return subprocess.run(["git"] + list(args), cwd=cwd, capture_output=True, text=True, env=env, check=True).stdout.strip()


def main():
	t = tempfile.mkdtemp()
	src = os.path.join(t, "src")
	os.makedirs(src)
	git("-c", "init.defaultBranch=main", "init", "-q", cwd=src)
	for i in range(3):
		with open(os.path.join(src, "f"), "w") as f:
			f.write("%d\n" % i)
		git("add", "f", cwd=src)
		git("commit", "-q", "-m", "c%d" % i, cwd=src)
		if i == 0:
			git("tag", "-a", "-m", "v1", "v1", cwd=src)
		if i == 1:
			mid = git("rev-parse", "HEAD", cwd=src)
	head = git("rev-parse", "HEAD", cwd=src)
	url = "file://" + src
	env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1")

	for tool in ("tools/upgrade-in-place-to-2604.sh", "tools/migrate-to-2604.sh"):
		s = open(os.path.join(ROOT, tool), encoding="utf-8").read()
		m = re.search(r"\nclone_ref\(\) \{.*?\n\}\n", s, re.S)
		check("%s: clone_ref found" % tool, m is not None, True)
		if not m:
			continue
		check("%s: no fresh clone of $tag with git clone -b" % tool, re.search(r'git clone -q -b "\$tag"', s) is None, True)
		fn = "warn() { echo \"WARNING: $*\" >&2; }\n" + m.group(0)
		for ref, want in (("v1", "c0"), ("main", "c2"), (mid, "c1")):
			d = os.path.join(t, "c-%s-%s" % (os.path.basename(tool), ref[:8]))
			r = subprocess.run(["bash", "-c", fn + 'clone_ref "$1" "$2" "$3"', "x", url, ref, d], capture_output=True, text=True, env=env)
			got = (r.returncode, git("log", "-1", "--format=%s", cwd=d) if r.returncode == 0 else r.stderr)
			check("%s: clone_ref %s" % (tool, "commit id" if ref == mid else ref), got, (0, want))
		for ref, hint in ((mid[:7], True), ("0" * 40, False)):
			d = os.path.join(t, "c-%s-bad-%s" % (os.path.basename(tool), ref[:8]))
			r = subprocess.run(["bash", "-c", fn + 'clone_ref "$1" "$2" "$3"', "x", url, ref, d], capture_output=True, text=True, env=env)
			check("%s: clone_ref %s fails, no directory left%s" % (tool, "short id" if hint else "unknown commit", ", hint" if hint else ""),
				(r.returncode != 0, os.path.exists(d), "full commit id" in r.stderr), (True, False, hint))

	s = open(os.path.join(ROOT, "setup", "bootstrap.sh"), encoding="utf-8").read()
	m = re.search(r'\n(if \[ ! -d "\$HOME/mailinabox" \]; then\n.*?\n\techo\nfi\n)', s, re.S)
	check("bootstrap.sh: clone block found", m is not None, True)
	if m:
		for ref, want in ((head, (0, "c2")), ("v1", (0, "c0")), ("0" * 40, (1, None))):
			home = tempfile.mkdtemp(dir=t)
			r = subprocess.run(["bash", "-c", m.group(1)], capture_output=True, text=True,
				env=dict(env, HOME=home, TAG=ref, SOURCE=url))
			d = os.path.join(home, "mailinabox")
			got = (r.returncode, git("log", "-1", "--format=%s", cwd=d) if os.path.isdir(os.path.join(d, ".git")) else None)
			check("bootstrap.sh: fresh clone of %s" % ("an unknown commit id" if ref.startswith("000") else "a commit id" if ref == head else ref),
				got, want)
		for ref, hint in ((head[:7], True), ("no-such-tag", False)):
			home = tempfile.mkdtemp(dir=t)
			r = subprocess.run(["bash", "-c", m.group(1)], capture_output=True, text=True,
				env=dict(env, HOME=home, TAG=ref, SOURCE=url))
			check("bootstrap.sh: %s fails with the message%s, no directory left" % ("a short commit id" if hint else "an unknown tag", ", the hint" if hint else ""),
				(r.returncode, "Could not download" in r.stdout, "full commit id" in r.stdout, os.path.exists(os.path.join(home, "mailinabox"))),
				(1, True, hint, False))
	shutil.rmtree(t)
	print()
	print("%d failed" % len(FAILED) if FAILED else "all passed")
	return 1 if FAILED else 0


sys.exit(main())
