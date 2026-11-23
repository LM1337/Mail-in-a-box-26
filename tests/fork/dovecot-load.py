#!/usr/bin/env python3
"""
Offline test of load_dovecot (setup/functions.sh), which loads Dovecot's
configuration at the end of setup's mail part -- python3 stdlib and bash
only, no box needed. Stand-ins for doveconf, doveadm, systemctl and service,
and temporary paths for the records, the Lua scripts and Dovecot's binary
copy of its configuration:

  * Dovecot does not run (or runs an older package): a restart, and both
    records are written;
  * nothing changed: nothing at all;
  * a changed setting outside the passdbs and userdbs: a reload;
  * a new passdb, a changed userdb or a changed Lua script of the auth
    guard: a restart, not a reload (B223: on a reload, the auth process of
    Dovecot 2.4 can die when its workers see other passdbs);
  * a box without the record of the passdbs (an update from v78-r2604.4 or
    older) and a changed configuration: a restart; with an unchanged
    configuration nothing, and the record is written then;
  * a box that an older version loaded since (a downgrade, which writes
    only the record of the whole configuration, and the way back up): a
    restart, although the passdbs equal the record's;
  * a reload that Dovecot does not take within 10 s: a restart;
  * doveconf -n refusing the configuration stops setup, nothing is loaded.

apt_install_held (B224), with a stand-in for apt_install and a temporary
policy-rc.d: while Dovecot runs, the packages' scripts may not start or
restart it (other units may), and the file is gone afterwards, also when
apt-get fails (setup stops with its code); nothing when Dovecot does not
run; a policy-rc.d that is not ours is left as it is; one of ours left by
a killed run is removed. setup/mail-dovecot.sh installs Dovecot's packages
with it.

  tests/fork/dovecot-load.py

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


def write(path, text):
	os.makedirs(os.path.dirname(path), exist_ok=True)
	with open(path, "w", encoding="utf-8") as f:
		f.write(text)


CONF = """# 2.4.1 (abc): /etc/dovecot/dovecot.conf
# OS: Linux 7.0.0 x86_64 Ubuntu 26.04
auth_mechanisms = plain login
passdb miab-auth-guard-check {
  driver = lua
  lua_file = /usr/local/lib/mailinabox/dovecot-auth-guard/check.lua
}
passdb sql {
  driver = sql
  fields {
    nopassword = n
  }
}
userdb sql {
  driver = sql
}
protocol imap {
  mail_max_userip_connections = 20
}
"""

with tempfile.TemporaryDirectory() as t:
	rec = os.path.join(t, "rec")
	lua = os.path.join(t, "lua")
	run = os.path.join(t, "run")
	conf = os.path.join(t, "doveconf.txt")
	log = os.path.join(t, "log")
	os.makedirs(rec)
	os.makedirs(run)
	write(os.path.join(lua, "check.lua"), "-- check\n")
	write(conf, CONF)
	binary = os.path.join(run, "dovecot.conf.binary")
	write(binary, "1")

	script = """
enable_service() { :; }
hide_output() { "$@"; }
service_runs_current_package() { [ "$RUNS" = yes ]; }
doveconf() { [ "$BAD" = yes ] && { echo "doveconf: Fatal: bad"; return 89; }; cat {conf}; }
doveadm() { :; }
sleep() { :; }
systemctl() {
	echo "systemctl $*" >> {log}
	if [ "$*" = "reload dovecot" ] && [ "$TAKES" = yes ]; then rm -f {binary}; echo 2 > {binary}; fi
}
service() { echo "service $*" >> {log}; }
eval "$(declare -f load_dovecot | sed -e 's|/var/lib/mailinabox|{rec}|g' \
	-e 's|/usr/local/lib/mailinabox/dovecot-auth-guard|{lua}|g' -e 's|/run/dovecot|{run}|g')"
load_dovecot
"""
	for k, v in (("{conf}", conf), ("{log}", log), ("{binary}", binary), ("{rec}", rec), ("{lua}", lua), ("{run}", run)):
		script = script.replace(k, shlex.quote(v) if k != "{rec}" and k != "{lua}" and k != "{run}" else v)

	def load(**env):
		e = {"PATH": "/usr/bin:/bin", "RUNS": "yes", "TAKES": "yes", "BAD": "no"}
		e.update(env)
		if os.path.exists(log):
			os.remove(log)
		p = subprocess.run(["bash", "-c", "set -euo pipefail\nsource setup/functions.sh\n" + script], cwd=REPO,
			env=e, capture_output=True, text=True, timeout=60)
		calls = open(log, encoding="utf-8").read().split("\n") if os.path.exists(log) else []
		calls = [c for c in calls if c]
		return p.returncode, calls, p.stdout + p.stderr

	auth_rec = os.path.join(rec, "dovecot-auth.sha256")
	conf_rec = os.path.join(rec, "dovecot-config.sha256")
	RESTART = ["service dovecot restart"]
	RELOAD = ["systemctl reload dovecot"]

	rc, calls, out = load(RUNS="no")
	check("not running: restart, both records", rc == 0 and calls == RESTART
		and os.path.exists(auth_rec) and os.path.exists(conf_rec), "%d %r %s" % (rc, calls, out))
	rc, calls, out = load()
	check("nothing changed: nothing", rc == 0 and calls == [], "%d %r %s" % (rc, calls, out))

	write(conf, CONF.replace("= 20", "= 30"))
	rc, calls, out = load()
	check("a setting outside the passdbs: reload", rc == 0 and calls == RELOAD, "%d %r %s" % (rc, calls, out))
	rc, calls, out = load()
	check("then nothing", rc == 0 and calls == [], "%d %r %s" % (rc, calls, out))

	write(conf, CONF.replace("= 20", "= 30").replace("passdb sql {", "passdb miab-auth-guard-count {\n  driver = lua\n}\npassdb sql {"))
	rc, calls, out = load()
	check("a new passdb: restart, not reload (B223)", rc == 0 and calls == RESTART, "%d %r %s" % (rc, calls, out))
	rc, calls, out = load()
	check("then nothing", rc == 0 and calls == [], "%d %r %s" % (rc, calls, out))

	write(conf, CONF.replace("= 20", "= 30").replace("nopassword = n", "nopassword = y"))
	rc, calls, out = load()
	check("a setting nested in a passdb: restart", rc == 0 and calls == RESTART, "%d %r %s" % (rc, calls, out))

	write(conf, CONF.replace("= 20", "= 30").replace("nopassword = n", "nopassword = y").replace("userdb sql {\n  driver = sql", "userdb sql {\n  driver = sql\n  args = x"))
	rc, calls, out = load()
	check("a changed userdb: restart", rc == 0 and calls == RESTART, "%d %r %s" % (rc, calls, out))

	write(os.path.join(lua, "check.lua"), "-- check 2\n")
	rc, calls, out = load()
	check("a changed Lua script: restart", rc == 0 and calls == RESTART, "%d %r %s" % (rc, calls, out))

	os.remove(auth_rec)
	rc, calls, out = load()
	check("no passdb record, configuration unchanged: nothing, record written",
		rc == 0 and calls == [] and os.path.exists(auth_rec), "%d %r %s" % (rc, calls, out))
	os.remove(auth_rec)
	write(conf, CONF)
	rc, calls, out = load()
	check("no passdb record (update from r2604.4), configuration changed: restart",
		rc == 0 and calls == RESTART and os.path.exists(auth_rec), "%d %r %s" % (rc, calls, out))

	# A downgrade: the older version reloads its configuration and writes
	# only the record of the whole configuration; the way back up brings the
	# passdbs of the record again, but Dovecot runs the older ones.
	write(conf_rec, "0" * 64 + "\n")
	rc, calls, out = load()
	check("an older version loaded since (downgrade and back): restart",
		rc == 0 and calls == RESTART, "%d %r %s" % (rc, calls, out))
	rc, calls, out = load()
	check("then nothing", rc == 0 and calls == [], "%d %r %s" % (rc, calls, out))

	write(conf, CONF.replace("= 20", "= 40"))
	rc, calls, out = load(TAKES="no")
	check("a reload that Dovecot does not take: restart",
		rc == 0 and calls == RELOAD + RESTART, "%d %r %s" % (rc, calls, out))

	write(conf, CONF.replace("= 20", "= 50"))
	before = open(conf_rec, encoding="utf-8").read()
	rc, calls, out = load(BAD="yes")
	check("doveconf -n refuses: setup stops, nothing loaded or recorded",
		rc != 0 and calls == [] and open(conf_rec, encoding="utf-8").read() == before and "FAILED: doveconf -n" in out,
		"%d %r %s" % (rc, calls, out))

# apt_install_held (B224): a policy-rc.d of our own while apt-get runs.
with tempfile.TemporaryDirectory() as t:
	policy = os.path.join(t, "policy-rc.d")
	seen = os.path.join(t, "seen")
	script = """
apt_install() {
	echo "apt $*" >> {seen}
	if [ -e {policy} ]; then
		for a in "dovecot restart" "dovecot.service restart" "--quiet dovecot (start)" "nginx restart" "postfix.service start"; do
			r=0; sh {policy} $a || r=$?; echo "policy $a $r" >> {seen}
		done
	fi
	[ "$APTFAIL" != yes ] || exit 100
}
systemctl() { [ "$*" = "is-active --quiet dovecot.service" ] && [ "$ACTIVE" = yes ]; }
eval "$(declare -f apt_install_held | sed 's|/usr/sbin/policy-rc.d|{policy}|g')"
apt_install_held dovecot dovecot-core dovecot-auth-lua
echo "after rc=$?"
""".replace("{seen}", shlex.quote(seen)).replace("{policy}", policy)

	def held(**env):
		e = {"PATH": "/usr/bin:/bin", "ACTIVE": "yes", "APTFAIL": "no"}
		e.update(env)
		if os.path.exists(seen):
			os.remove(seen)
		p = subprocess.run(["bash", "-c", "set -euo pipefail\nsource setup/functions.sh\n" + script], cwd=REPO,
			env=e, capture_output=True, text=True, timeout=60)
		lines = open(seen, encoding="utf-8").read().split("\n") if os.path.exists(seen) else []
		return p.returncode, [l for l in lines if l], p.stdout + p.stderr

	rc, lines, out = held()
	check("apt_install_held, Dovecot runs: its starts and restarts are refused, others allowed, the file removed",
		rc == 0 and lines == ["apt dovecot-core dovecot-auth-lua", "policy dovecot restart 101", "policy dovecot.service restart 101",
			"policy --quiet dovecot (start) 101", "policy nginx restart 0", "policy postfix.service start 0"]
		and not os.path.exists(policy) and "after rc=0" in out, "%d %r %s" % (rc, lines, out))
	rc, lines, out = held(APTFAIL="yes")
	check("apt_install_held, apt-get fails: setup stops with its code, the file removed",
		rc == 100 and not os.path.exists(policy) and "after rc" not in out, "%d %r %s" % (rc, lines, out))
	rc, lines, out = held(ACTIVE="no")
	check("apt_install_held, Dovecot does not run (a first install): no policy",
		rc == 0 and lines == ["apt dovecot-core dovecot-auth-lua"] and not os.path.exists(policy), "%d %r %s" % (rc, lines, out))
	write(policy, "#!/bin/sh\nexit 101\n")
	rc, lines, out = held()
	check("apt_install_held, a policy-rc.d that is not ours: left as it is and used",
		rc == 0 and open(policy, encoding="utf-8").read() == "#!/bin/sh\nexit 101\n"
		and "policy nginx restart 101" in lines, "%d %r %s" % (rc, lines, out))
	os.remove(policy)
	write(policy, "#!/bin/sh\n# mailinabox: setup holds dovecot (apt_install_held in setup/functions.sh)\nexit 101\n")
	rc, lines, out = held(ACTIVE="no")
	check("apt_install_held, one of ours left by a killed run: removed",
		rc == 0 and not os.path.exists(policy) and lines == ["apt dovecot-core dovecot-auth-lua"], "%d %r %s" % (rc, lines, out))

for script, n in (("setup/mail-dovecot.sh", 2),):
	src = open(os.path.join(REPO, script), encoding="utf-8").read()
	check("%s installs Dovecot's packages with apt_install_held" % script,
		src.count("apt_install_held dovecot ") == n and "apt_install dovecot" not in src)

if FAILED:
	print("%d case(s) failed: %s" % (len(FAILED), ", ".join(FAILED)))
	sys.exit(1)
print("all cases passed")
