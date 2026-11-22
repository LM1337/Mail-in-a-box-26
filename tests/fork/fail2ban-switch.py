"""Checks the switch that turns fail2ban off for tests (System > Intrusion Detection and Prevention).

No box needed. systemctl and fail2ban-client are replaced by stand-ins.

  * the setting "enabled": on by default, "0"/"1" from the form, stored only
    when it differs from the default;
  * sync_service(): turned off, fail2ban is stopped and disabled; turned on
    again, enabled and started; nothing when it already is as it should be
    (only "disable" again while off, so that a reboot does not start it); a
    failure raises RuntimeError with systemctl's message;
  * setup/start.sh stops and disables fail2ban on exit code 4 of
    fail2ban_admin.py --setup, and --setup exits 4 while it is off;
  * the status checks warn while it is off instead of reporting an error; the
    page has the checkbox, sends it and asks before turning it off.

Usage: python3 -I tests/fork/fail2ban-switch.py
Exit code 0 when every check passed.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "management"))
import fail2ban_admin as f  # noqa: E402

FAILED = []


def check(name, got, want):
	if got != want:
		FAILED.append(name)
		print(f"FAIL {name}\n  want: {want!r}\n  got:  {got!r}")
	else:
		print(f"ok   {name}")


s, w = f.validate_settings({})
check("default: on", (s["enabled"], w), (True, []))
check("form 0: off", f.validate_settings({"enabled": "0"})[0]["enabled"], False)
check("form 1: on", f.validate_settings({"enabled": "1"})[0]["enabled"], True)
try:
	f.validate_settings({"enabled": "maybe"})
	check("bad value refused", "accepted", "ValueError")
except ValueError:
	check("bad value refused", "ValueError", "ValueError")


class P:
	def __init__(self, rc=0, err=""):
		self.returncode, self.stdout, self.stderr = rc, "", err


def runner(rc=0, err=""):
	calls = []
	def run(cmd, **kw):
		calls.append(cmd)
		return P(rc, err)
	return run, calls


for running, enabled, want_ret, want_calls in [
		(True, False, "stopped", [["systemctl", "disable", "--now", "fail2ban"]]),
		(False, True, "started", [["systemctl", "enable", "--now", "fail2ban"]]),
		(True, True, None, []),
		(False, False, None, [["systemctl", "disable", "fail2ban"]])]:
	f.is_running = lambda r=running: r
	run, calls = runner()
	check(f"sync: running={running} enabled={enabled}", (f.sync_service({"enabled": enabled}, run=run), calls), (want_ret, want_calls))
f.is_running = lambda: False
run, calls = runner(1, "Job for fail2ban.service failed.\n")
try:
	f.sync_service({"enabled": True}, run=run)
	check("sync: failure raises", "no error", "RuntimeError")
except RuntimeError as e:
	check("sync: failure raises with systemctl's message", "Job for fail2ban.service failed." in str(e), True)

start = open(os.path.join(ROOT, "setup", "start.sh")).read()
check("setup: exit code 4 stops and disables fail2ban",
	'elif [ "$f2b_setup_rc" = 4 ]; then' in start and "hide_output systemctl disable --now fail2ban" in start.split('elif [ "$f2b_setup_rc" = 4 ]; then')[1].split("else")[0], True)
admin = open(os.path.join(ROOT, "management", "fail2ban_admin.py")).read()
check("--setup exits 4 while off", "if not settings[\"enabled\"]:\n\t\t\tsys.exit(4)" in admin and "sys.exit(3 if settings[\"enabled\"] else 4)" in admin, True)
sc = open(os.path.join(ROOT, "management", "status_checks.py")).read()
check("status checks: a warning while off", "print_warning(\"fail2ban is turned off" in sc, True)
page = open(os.path.join(ROOT, "management", "templates", "system-fail2ban.html")).read()
check("page: checkbox, rendered, sent, asked before off",
	all(x in page for x in ('id="f2b-enabled"', "$('#f2b-enabled').prop('checked', s.enabled !== false)",
		"enabled: $('#f2b-enabled').prop('checked') ? \"1\" : \"0\"", "values.enabled == \"0\")")), True)

print(f"{len(FAILED)} failed." if FAILED else "all cases passed.")
sys.exit(1 if FAILED else 0)
