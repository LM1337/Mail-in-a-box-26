#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Offline test of the filter of the old box's messages in
tools/migrate-to-2604.sh -- python3 stdlib only, no box needed (B154).

printable() and old_side() pass text from the old box (ssh's messages, the
remote command's standard error) to the terminal and the reports. This test
runs both functions, taken from the tool, in bash and checks:

  * an escape sequence (CSI colour, OSC window title) shows up with "?" for
    ESC and BEL, so it cannot reach the terminal;
  * a line that ends in CR LF (ssh's "Warning: Permanently added ... to the
    list of known hosts.") loses the CR instead of ending in "?"; a CR in
    the middle of a line is still shown as "?";
  * old_side keeps the command's standard output and exit code, and filters
    only its standard error.

  tests/fork/old-side-filter.py

Exit code: 0 = all cases pass, 1 = a case failed (printed).
"""

import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "..", "tools", "migrate-to-2604.sh")
FAILED = []


def check(name, got, want):
	ok = got == want
	print("%s %s%s" % ("ok  " if ok else "FAIL", name, "" if ok else ": want %r, got %r" % (want, got)))
	if not ok:
		FAILED.append(name)


def main():
	src = open(TOOL, encoding="utf-8").read()
	funcs = ""
	for name in ("printable", "old_side"):
		m = re.search(r"\n%s\(\) \{.*?(\}\n|; \}\n)" % name, src, re.S)
		check("%s() found in the tool" % name, m is not None, True)
		if not m:
			return 1
		funcs += m.group(0)
	msg = r"printf 'Warning: Permanently added x to the list of known hosts.\r\n\033]0;TITLE\007\033[31mRED\033[0m\nmid\rdle\n' >&2"
	r = subprocess.run(["bash", "-c", "set -euo pipefail\n" + funcs + "\nold_side bash -c \"%s; echo out; exit 3\" || echo \"rc=$?\"\n" % msg.replace('"', '\\"')],
		capture_output=True, text=True)
	check("old_side: standard output and exit code kept", r.stdout, "out\nrc=3\n")
	check("old_side: standard error filtered, CR of CR LF dropped",
		r.stderr, "Warning: Permanently added x to the list of known hosts.\n?]0;TITLE??[31mRED?[0m\nmid?dle\n")
	r = subprocess.run(["bash", "-c", funcs + "\n{ %s; } 2>&1 | printable\n" % msg], capture_output=True, text=True)
	check("printable: the same", r.stdout, "Warning: Permanently added x to the list of known hosts.\n?]0;TITLE??[31mRED?[0m\nmid?dle\n")
	print()
	print("%d failed" % len(FAILED) if FAILED else "all passed")
	return 1 if FAILED else 0


sys.exit(main())
