#!/usr/bin/env python3
"""
Offline test of flush_local_deferred (setup/functions.sh, B225), which setup
runs at its end -- python3 stdlib and bash only, no box needed. Stand-ins for
systemctl and postqueue (its JSON output, `postqueue -j`):

  * deferred mail that waited for spampd (port 10025 refused) or whose
    connection to it was lost is retried (`postqueue -i ID`), each once;
  * deferred mail to another mail server, mail in the active or hold
    queue (held by the sending limit) and a line that is no JSON are left
    alone; a queue id that is not one is never passed on;
  * Postfix not running, or postqueue failing: nothing, and setup goes on;
  * setup/start.sh runs it after the last restart, before its end.

  tests/fork/flush-local.py

Exit code: 0 = all cases pass, 1 = a case failed (printed).
"""

import json
import os
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


def mail(queue, qid, *reasons):
	return json.dumps({"queue_name": queue, "queue_id": qid,
		"recipients": [{"address": "u%d@example.org" % i, "delay_reason": r} for i, r in enumerate(reasons)]})


QUEUE = "\n".join([
	mail("deferred", "A74CB3F0FD", "connect to 127.0.0.1[127.0.0.1]:10025: Connection refused"),
	mail("deferred", "EAEB43F076", "lost connection with 127.0.0.1[127.0.0.1] while sending end of data -- message may be sent more than once"),
	mail("deferred", "B1C2D3E4F5", "host mx.example.net[192.0.2.25] said: 451 4.7.1 Try again later"),
	mail("deferred", "C1C2D3E4F5", "host mx.example.net[192.0.2.25] said: 421 too many", "connect to 127.0.0.1[127.0.0.1]:10025: Connection refused"),
	mail("hold", "D1C2D3E4F5", ""),
	mail("active", "E1C2D3E4F5", ""),
	mail("deferred", "1; touch /x", "connect to 127.0.0.1[127.0.0.1]:10025: Connection refused"),
	"postqueue: warning: not json",
	mail("deferred", "F1C2D3E4F5"),
]) + "\n"

with tempfile.TemporaryDirectory() as tmp:
	bin_dir = os.path.join(tmp, "bin")
	os.makedirs(bin_dir)
	log = os.path.join(tmp, "log")
	queue_file = os.path.join(tmp, "queue")
	with open(queue_file, "w") as f:
		f.write(QUEUE)
	stubs = {
		"systemctl": '#!/bin/sh\necho "systemctl $*" >> "$LOG"\n[ "$ACTIVE" = 1 ]\n',
		"postqueue": '#!/bin/sh\necho "postqueue $*" >> "$LOG"\n'
			'if [ "$1" = -j ]; then [ "$PQ_FAIL" = 1 ] && exit 69; cat "$QUEUE"; fi\nexit 0\n',
	}
	for name, text in stubs.items():
		path = os.path.join(bin_dir, name)
		with open(path, "w") as f:
			f.write(text)
		os.chmod(path, 0o755)

	def run(**env):
		if os.path.exists(log):
			os.remove(log)
		e = dict(os.environ, PATH=bin_dir + ":" + os.environ["PATH"], LOG=log, QUEUE=queue_file, ACTIVE="1", PQ_FAIL="0")
		e.update(env)
		p = subprocess.run(["bash", "-c", "set -euo pipefail\nsource setup/functions.sh\nflush_local_deferred\necho END"],
			cwd=REPO, env=e, capture_output=True, text=True)
		calls = open(log).read().splitlines() if os.path.exists(log) else []
		return p, calls

	p, calls = run()
	retried = [c.split()[-1] for c in calls if c.startswith("postqueue -i")]
	check("mail that waited for spampd or lost its connection to it is retried, each once",
		retried == ["A74CB3F0FD", "EAEB43F076", "C1C2D3E4F5"], repr(retried))
	check("other deferred mail, held and active mail, no JSON, a bad id: left alone",
		not any(i in " ".join(retried) for i in ("B1C2", "D1C2", "E1C2", "F1C2", "touch")), repr(calls))
	check("setup goes on", p.returncode == 0 and p.stdout.strip().endswith("END"), p.stderr)

	p, calls = run(ACTIVE="0")
	check("Postfix not running: postqueue is not called, setup goes on",
		p.returncode == 0 and p.stdout.strip().endswith("END") and not any(c.startswith("postqueue") for c in calls), repr(calls) + p.stderr)

	p, calls = run(PQ_FAIL="1")
	check("postqueue -j fails: nothing retried, setup goes on",
		p.returncode == 0 and p.stdout.strip().endswith("END") and not any(c.startswith("postqueue -i") for c in calls), repr(calls) + p.stderr)

start = open(os.path.join(REPO, "setup", "start.sh"), encoding="utf-8").read()
check("setup/start.sh runs it after the last restart, before its end",
	"\nflush_local_deferred\n" in start
	and start.index("source setup/munin.sh") < start.index("\nflush_local_deferred\n") < start.index("# Done."), True)

if FAILED:
	print("%d case(s) failed" % len(FAILED))
	sys.exit(1)
print("all cases passed")
