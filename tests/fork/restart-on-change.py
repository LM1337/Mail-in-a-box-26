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
changed, one that something else restarted after the record was written
(not at boot: a downgrade and the way back up) is restarted, and a failed
restart records nothing. load_php_fpm, the same way:
a reload when the configuration changed, nothing when it did not, a
restart when the reload brings no "ready to handle connections", when
php-fpm -t refuses the configuration, when PHP-FPM does not run afterwards
or did not run before, and a reload when something else restarted it after
the record was written.

service_runs_current_package with stand-ins for systemctl and dpkg-query:
the unit's own package and the library packages after it (an update of
SpamAssassin's Perl modules counts for spampd; a library package that is
not installed does not count).

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
systemctl() {
	case "$*" in
	"show -P ActiveEnterTimestamp svc.service") echo "${STARTED:-}" ;;
	"show -P FinishTimestamp") echo "${BOOTED:-}" ;;
	esac
}
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
	# started_after_record: the record written at 1700000000.
	recfile = os.path.join(rec, "svc-config.sha256")
	def at(**env):
		os.utime(recfile, (1700000000, 1700000000))
		e = {"RUNS": "yes", "FAIL": "no"}
		e.update(env)
		return bash(stub, e)
	rc, out, err = at(STARTED="@1699999000", BOOTED="@1699998000")
	check("started before the record: no restart", rc == 0 and calls() == 3, err)
	rc, out, err = at(STARTED="@1700000100", BOOTED="@1700000200")
	check("started after the record, at boot: no restart", rc == 0 and calls() == 3, err)
	rc, out, err = at(STARTED="@1700000100", BOOTED="@1700000050")
	check("restarted by something else after the record (a downgrade): restart", rc == 0 and calls() == 4, err)
	rc, out, err = at(STARTED="@1700000100", BOOTED="")
	check("started after the record, boot not finished: restart", rc == 0 and calls() == 5, err)
	write(conf, "a = 4\n")
	with open(os.path.join(rec, "svc-config.sha256"), encoding="utf-8") as f:
		before = f.read()
	rc, out, err = bash(stub, {"RUNS": "yes", "FAIL": "yes"})
	with open(os.path.join(rec, "svc-config.sha256"), encoding="utf-8") as f:
		after = f.read()
	check("failed restart: setup stops, nothing recorded", rc != 0 and before == after, "rc=%d" % rc)

# load_php_fpm with stand-ins: the record and PHP-FPM's log in temporary
# files, "systemctl reload" appends "ready to handle connections" to the log
# when READY=yes, "service ... restart" is counted.
with tempfile.TemporaryDirectory() as t:
	rec = os.path.join(t, "state")
	log = os.path.join(t, "fpm.log")
	calls = os.path.join(t, "calls")
	write(log, "old line\n")
	stub = """
PHP_VER=8.5
enable_service() { :; }
sleep() { :; }
service_runs_current_package() { [ "$RUNS" = yes ]; }
php-fpm8.5() { [ "$FPMTEST" = ok ]; }
systemctl() {
	case "$1" in
	reload) echo reload >> {calls}; [ "$READY" = yes ] && echo "NOTICE: ready to handle connections" >> {log}; return 0 ;;
	is-active) [ "$ACTIVE" = yes ] ;;
	show) case "$3" in ActiveEnterTimestamp) echo "${STARTED:-}" ;; FinishTimestamp) echo "${BOOTED:-}" ;; esac ;;
	esac
}
service() { echo "$*" >> {calls}; }
eval "$(declare -f load_php_fpm | sed -e 's|/var/lib/mailinabox|{rec}|g' -e 's|log=/var/log/php$PHP_VER-fpm.log|log={log}|')"
load_php_fpm
""".replace("{calls}", shlex.quote(calls)).replace("{log}", log).replace("{rec}", rec)

	def fpm(**env):
		e = {"RUNS": "yes", "FPMTEST": "ok", "READY": "yes", "ACTIVE": "yes"}
		e.update(env)
		if os.path.exists(calls):
			os.unlink(calls)
		rc, out, err = bash(stub, e)
		try:
			with open(calls, encoding="utf-8") as f:
				c = f.read().split("\n")
		except FileNotFoundError:
			c = []
		return rc, [x for x in c if x], out

	rc, c, out = fpm()
	check("PHP-FPM, no record yet: a reload, no restart", rc == 0 and c == ["reload"], repr((rc, c, out)))
	rc, c, out = fpm()
	check("PHP-FPM, configuration unchanged: nothing", rc == 0 and c == [], repr((rc, c, out)))
	with open(os.path.join(rec, "php-fpm-config.sha256"), "w", encoding="utf-8") as f:
		f.write("changed\n")
	rc, c, out = fpm(READY="no")
	check("PHP-FPM, no ready line after the reload: restart", rc == 0 and c == ["reload", "php8.5-fpm restart"], repr((rc, c, out)))
	os.unlink(os.path.join(rec, "php-fpm-config.sha256"))
	rc, c, out = fpm(FPMTEST="bad")
	check("PHP-FPM, configuration refused by php-fpm -t: restart, no reload", rc == 0 and c == ["php8.5-fpm restart"], repr((rc, c, out)))
	rc, c, out = fpm(RUNS="no")
	check("PHP-FPM not running or an older package: restart", rc == 0 and c == ["php8.5-fpm restart"], repr((rc, c, out)))
	os.unlink(os.path.join(rec, "php-fpm-config.sha256"))
	rc, c, out = fpm(ACTIVE="no")
	check("PHP-FPM stopped after the reload: restart", rc == 0 and c == ["reload", "php8.5-fpm restart"], repr((rc, c, out)))
	rc, c, out = fpm()
	os.utime(os.path.join(rec, "php-fpm-config.sha256"), (1700000000, 1700000000))
	rc, c, out = fpm(STARTED="@1700000100", BOOTED="@1700000200")
	check("PHP-FPM started after the record at boot: nothing", rc == 0 and c == [], repr((rc, c, out)))
	rc, c, out = fpm(STARTED="@1700000100", BOOTED="@1700000050")
	check("PHP-FPM restarted by something else after the record: a reload", rc == 0 and c == ["reload"], repr((rc, c, out)))

# service_runs_current_package with stand-ins: the unit started at 1000,
# dpkg-query answers the Last-Modified time of each package from PKGTIMES
# ("name=time ..."; a package not listed is not installed).
stub = r'''
systemctl() {
	case "$*" in
	"is-active --quiet svc.service") return 0 ;;
	"show -P ActiveEnterTimestamp svc.service") echo "@1000" ;;
	"show -P MainPID svc.service") echo "$$" ;;
	esac
}
dpkg-query() {
	local p=${!#} kv
	for kv in $PKGTIMES; do
		if [ "${kv%%=*}" = "$p" ]; then printf %s "${kv#*=}"; return 0; fi
	done
	return 1
}
service_runs_current_package svc.service "$PKGS"
'''
for name, pkgs, times, want in (
		("own package older than the start: current", "spampd", "spampd=900", 0),
		("own package newer: not current", "spampd", "spampd=1100", 1),
		("own package missing: not current", "spampd", "", 1),
		("no package: current", "", "", 0),
		("a library package updated after the start: not current", "spampd spamassassin libnet-server-perl", "spampd=900 spamassassin=1100 libnet-server-perl=800", 1),
		("library packages older: current", "spampd spamassassin libnet-server-perl", "spampd=900 spamassassin=950 libnet-server-perl=800", 0),
		("a library package not installed: ignored", "spampd spamassassin", "spampd=900", 0)):
	rc, out, err = bash(stub, {"PKGS": pkgs, "PKGTIMES": times})
	check("service_runs_current_package: " + name, rc == want, "rc=%d %s" % (rc, err))

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
