#!/usr/bin/env python3
"""
Offline test of the checksum that decides whether setup restarts a service
(config_checksum and restart_on_change in setup/functions.sh) -- python3
stdlib and bash only, no box needed.

config_checksum runs in bash on temporary files:

  * the same files give the same checksum, a changed content, a new file in
    a tree:, a new name or another link target in a dir: and a new inode of
    a stat: file give another one;
  * a missing file, tree or directory gives a checksum (no error, setup
    runs with set -euo pipefail), and a file that appears changes it;
  * Python's __pycache__ below a tree: does not count (the management
    daemon writes it when it starts);
  * stat: does not read the file (a file of mode 000 gives a checksum).

restart_on_change runs with stand-ins for the service commands and a
temporary record directory: the first call restarts and records, a second
one with the same files does nothing, a change restarts again, a service
that does not run (or runs an older package) is restarted although nothing
changed, and a failed restart records nothing.

It also checks that the services of the planned item are no longer
restarted with restart_service.

  tests/fork/restart-on-change.py

Exit code: 0 = all cases pass, 1 = a case failed (printed).
"""

import os
import shlex
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


def bash(script, env=None):
	e = {"PATH": "/usr/bin:/bin"}
	e.update(env or {})
	p = subprocess.run(["bash", "-c", "source setup/functions.sh\n" + script], cwd=REPO, env=e,
		capture_output=True, text=True, timeout=60)
	return p.returncode, p.stdout.strip(), p.stderr.strip()


def checksum(*args):
	rc, out, err = bash("config_checksum " + " ".join(shlex.quote(a) for a in args))
	if rc != 0 or len(out) != 64:
		raise AssertionError("config_checksum failed: rc=%d out=%r err=%r" % (rc, out, err))
	return out


def write(path, text):
	os.makedirs(os.path.dirname(path), exist_ok=True)
	with open(path, "w", encoding="utf-8") as f:
		f.write(text)


with tempfile.TemporaryDirectory() as t:
	conf = os.path.join(t, "etc", "svc.conf")
	tree = os.path.join(t, "etc", "svc.d")
	plugins = os.path.join(t, "plugins")
	key = os.path.join(t, "key")
	write(conf, "a = 1\n")
	write(os.path.join(tree, "10-x.conf"), "x\n")
	os.makedirs(plugins)
	os.symlink("/usr/share/munin/plugins/cpu", os.path.join(plugins, "cpu"))
	write(key, "secret\n")
	args = [conf, "tree:" + tree, "dir:" + plugins, "stat:" + key]

	base = checksum(*args)
	check("same files, same checksum", checksum(*args) == base)

	write(conf, "a = 2\n")
	c1 = checksum(*args)
	check("changed content: another checksum", c1 != base)
	write(conf, "a = 1\n")
	check("content back: the checksum of before", checksum(*args) == base)

	write(os.path.join(tree, "20-y.conf"), "y\n")
	c2 = checksum(*args)
	check("new file in a tree: another checksum", c2 != base)
	os.unlink(os.path.join(tree, "20-y.conf"))

	write(os.path.join(tree, "__pycache__", "x.cpython-314.pyc"), "bytecode")
	check("__pycache__ below a tree does not count", checksum(*args) == base)

	os.symlink("/usr/share/munin/plugins/df", os.path.join(plugins, "df"))
	c3 = checksum(*args)
	check("new name in a dir: another checksum", c3 != base)
	os.unlink(os.path.join(plugins, "df"))
	os.unlink(os.path.join(plugins, "cpu"))
	os.symlink("/usr/share/munin/plugins/cpu_", os.path.join(plugins, "cpu"))
	check("another link target in a dir: another checksum", checksum(*args) != base)
	os.unlink(os.path.join(plugins, "cpu"))
	os.symlink("/usr/share/munin/plugins/cpu", os.path.join(plugins, "cpu"))
	check("link target back: the checksum of before", checksum(*args) == base)

	os.chmod(key, 0)
	check("stat: does not read the file", checksum(*args) == base or os.getuid() == 0)
	os.chmod(key, 0o600)
	os.rename(key, key + ".old")
	write(key, "secret\n")
	check("stat: a new inode gives another checksum", checksum(*args) != base)

	missing = [os.path.join(t, "no.conf"), "tree:" + os.path.join(t, "no.d"),
		"dir:" + os.path.join(t, "no-plugins"), "stat:" + os.path.join(t, "no-key")]
	m = checksum(*missing)
	check("missing file, tree, dir and stat: a checksum, no error", len(m) == 64)
	write(os.path.join(t, "no.conf"), "now\n")
	check("a file that appears changes the checksum", checksum(*missing) != m)

	# restart_on_change with stand-ins: the record directory is a temporary
	# one, "service" records its calls, the package check is a switch.
	rec = os.path.join(t, "state")
	log = os.path.join(t, "service.log")
	stub = """
enable_service() { :; }
service_runs_current_package() { [ "$RUNS" = yes ]; }
service() { echo "$*" >> {log}; [ "$FAIL" != yes ]; }
eval "$(declare -f restart_on_change | sed 's|/var/lib/mailinabox|{rec}|g')"
restart_on_change svc svc-pkg {args}
""".replace("{log}", shlex.quote(log)).replace("{rec}", rec).replace("{args}", " ".join(shlex.quote(a) for a in args))

	def calls():
		try:
			with open(log, encoding="utf-8") as f:
				return f.read().count("svc restart")
		except FileNotFoundError:
			return 0

	rc, out, err = bash(stub, {"RUNS": "yes", "FAIL": "no"})
	check("first call: restart and record", rc == 0 and calls() == 1 and os.path.exists(os.path.join(rec, "svc-config.sha256")), err)
	rc, out, err = bash(stub, {"RUNS": "yes", "FAIL": "no"})
	check("nothing changed: no restart", rc == 0 and calls() == 1, err)
	write(conf, "a = 3\n")
	rc, out, err = bash(stub, {"RUNS": "yes", "FAIL": "no"})
	check("changed configuration: restart", rc == 0 and calls() == 2, err)
	rc, out, err = bash(stub, {"RUNS": "no", "FAIL": "no"})
	check("not running or an older package: restart", rc == 0 and calls() == 3, err)
	write(conf, "a = 4\n")
	with open(os.path.join(rec, "svc-config.sha256"), encoding="utf-8") as f:
		before = f.read()
	rc, out, err = bash(stub, {"RUNS": "yes", "FAIL": "yes"})
	with open(os.path.join(rec, "svc-config.sha256"), encoding="utf-8") as f:
		after = f.read()
	check("failed restart: setup stops, nothing recorded", rc != 0 and before == after, "rc=%d" % rc)

for script, unit in (("setup/dkim.sh", "opendkim"), ("setup/dkim.sh", "opendmarc"), ("setup/spamassassin.sh", "spampd"),
		("setup/mail-postfix.sh", "postgrey"), ("setup/system.sh", "named"), ("setup/system.sh", "systemd-resolved"),
		("setup/munin.sh", "munin-node"), ("setup/management.sh", "mailinabox")):
	src = open(os.path.join(REPO, script), encoding="utf-8").read()
	check("%s: %s only on a change" % (script, unit),
		"restart_on_change %s " % unit in src and "restart_service %s\n" % unit not in src
		and "systemctl restart %s\n" % unit not in src)

if FAILED:
	print("%d case(s) failed: %s" % (len(FAILED), ", ".join(FAILED)))
	sys.exit(1)
print("all cases passed")
