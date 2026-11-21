#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Offline test of the order in which tools/upgrade-in-place-to-2604.sh masks
the units when mail goes offline -- python3 stdlib only, no box needed
(B190).

Every "systemctl mask" reloads systemd. When the tool masked apt-daily.timer,
the reload let apt-daily-upgrade.timer (Persistent=true) start its missed
run at once, and unattended-upgrade installed packages while mail went
offline and after the system archive was made. This test runs quiesce_units
and mask_units, taken from the tool, in bash with a stand-in systemctl that
records its calls, and checks:

  * quiesce_units lists apt-daily.service and apt-daily-upgrade.service
    before the timers;
  * mask_units masks both services in its first call, together, before any
    timer;
  * phase setup and the end of setup keep the services masked as long as
    the timers (unquiesce is given both).

  tests/fork/quiesce-order.py

Exit code: 0 = all cases pass, 1 = a case failed (printed).
"""

import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "..", "tools", "upgrade-in-place-to-2604.sh")
FAILED = []


def check(name, got, want):
	ok = got == want
	print("%s %s%s" % ("ok  " if ok else "FAIL", name, "" if ok else ": want %r, got %r" % (want, got)))
	if not ok:
		FAILED.append(name)


def main():
	src = open(TOOL, encoding="utf-8").read()
	funcs = ""
	for name in ("quiesce_units", "mask_units"):
		m = re.search(r"\n%s\(\) \{.*?\n\}\n" % name, src, re.S)
		check("%s() found" % name, m is not None, True)
		if not m:
			return 1
		funcs += m.group(0)
	d = tempfile.mkdtemp()
	log = os.path.join(d, "calls")
	masked = os.path.join(d, "masked")
	with open(os.path.join(d, "systemctl"), "w") as f:
		f.write("""#!/bin/bash
echo "$*" >> %s
case "$1" in
	cat) exit 0 ;;
	list-unit-files) echo "php8.0-fpm.service enabled enabled" ;;
	mask) shift; for u in "$@"; do [ "$u" = --quiet ] || echo "$u" >> %s; done ;;
	is-enabled) if grep -qx "$2" %s 2> /dev/null; then echo masked; else echo enabled; fi ;;
esac
exit 0
""" % (log, masked, masked))
	os.chmod(os.path.join(d, "systemctl"), 0o755)
	script = funcs + """
state_add() { :; }
state_get() { echo; }
state_set() { :; }
warn() { echo "WARNING: $*" >&2; }
mapfile -t units < <(quiesce_units)
echo "UNITS ${units[*]}"
mask_units "${units[@]}"
"""
	r = subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=dict(os.environ, PATH=d + ":" + os.environ["PATH"]))
	units = (re.search(r"^UNITS (.*)$", r.stdout, re.M) or [None, ""])[1].split()
	check("quiesce_units: the apt services before the timers",
		[u for u in units if u.startswith("apt-daily")], ["apt-daily.service", "apt-daily-upgrade.service", "apt-daily.timer", "apt-daily-upgrade.timer"])
	masks = [l.split()[1:] for l in open(log).read().splitlines() if l.startswith("mask ")]
	check("mask_units: first mask call has both apt services, together",
		[x for x in masks[0] if x != "--quiet"] if masks else None, ["apt-daily.service", "apt-daily-upgrade.service"])
	first_timer = next((i for i, m in enumerate(masks) if any(x.endswith(".timer") for x in m)), None)
	check("mask_units: no timer masked before the services", first_timer is not None and first_timer > 0, True)
	for where in ("unquiesce cron.service apt-daily.timer apt-daily-upgrade.timer apt-daily.service apt-daily-upgrade.service",
			"unquiesce apt-daily.timer apt-daily-upgrade.timer apt-daily.service apt-daily-upgrade.service"):
		check("phase setup keeps the apt services masked with the timers: %s" % where, where in src, True)
	print()
	print("%d failed" % len(FAILED) if FAILED else "all passed")
	return 1 if FAILED else 0


sys.exit(main())
