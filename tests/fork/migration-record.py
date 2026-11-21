#!/usr/bin/env python3
"""
Offline test of the migration record (setup/migrate.py, B211) -- python3
stdlib only, no box needed.

setup/migrate.py is loaded with its migrations replaced by recorders, the
environment and the root check patched, STORAGE_ROOT and the record
(/var/lib/mailinabox/storage-migration) in a temporary directory:

  * a box without a record (the first run of this version, or a new box
    after a migration or restore): the file counts, the migrations after it
    run, the record is written;
  * the record and the file agree: nothing runs;
  * a lower number in mailinabox.version (the storage user's): setup stops
    before any migration, the file and the record stay;
  * a higher number in the file (a run that ended after writing the file and
    before the record): taken, the record follows;
  * a number above the newest migration that the record does not confirm
    (the storage user's, or a typo; with a lower record or none): setup
    stops before any migration with the number to write back, the file and
    the record stay, so the right number can be written back and a later
    release's migrations still run; the same number in the record (a
    downgrade) is taken and the record is never lowered;
  * mailinabox.version missing: taken from the record, the migrations after
    it run (not skipped as on a new box);
  * the record of another STORAGE_ROOT does not count;
  * a record that is not a regular file of its owner, or is writable by
    others, stops setup;
  * a failed migration leaves file and record at the last one that ran;
  * --record (setup/start.sh on a new STORAGE_ROOT).

  tests/fork/migration-record.py

Exit code: 0 = all cases pass, 1 = a case failed (printed).
"""

import importlib.util
import io
import os
import shutil
import sys
import tempfile
import contextlib

sys.dont_write_bytecode = True  # no setup/__pycache__ in the checkout
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))

os.chdir(REPO)  # migrate.py imports management/utils.py by a relative path
spec = importlib.util.spec_from_file_location("migrate", os.path.join(REPO, "setup", "migrate.py"))
migrate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migrate)

failures = []
RAN = []


def check(name, got, want):
	if got != want:
		failures.append(name)
		print(f"FAIL {name}\n  want: {want!r}\n  got:  {got!r}")
	else:
		print(f"ok   {name}")


LAST = 15  # the migrations of the test: 1 .. LAST
FAIL_AT = []


def recorder(n):
	def m(env):
		if n in FAIL_AT:
			raise Exception("migration %d failed (test)" % n)
		RAN.append(n)
	return m


for name in [k for k in vars(migrate) if k.startswith("migration_")]:
	delattr(migrate, name)
for n in range(1, LAST + 1):
	setattr(migrate, "migration_%d" % n, recorder(n))

tmp = tempfile.mkdtemp(prefix="migration-record-")
ROOT = os.path.join(tmp, "user-data")
RECORD = os.path.join(tmp, "var-lib-mailinabox", "storage-migration")
VERSION = os.path.join(ROOT, "mailinabox.version")
migrate.MIGRATION_RECORD = RECORD
migrate.RECORD_OWNER = os.getuid()
migrate.load_environment = lambda: {"STORAGE_ROOT": ROOT}
migrate.os.access = lambda *a, **k: True


def state(version=None, record=None):
	shutil.rmtree(tmp)
	os.makedirs(ROOT)
	if version is not None:
		with open(VERSION, "w") as f:
			f.write("%s\n" % version)
	if record is not None:
		os.makedirs(os.path.dirname(RECORD))
		with open(RECORD, "w") as f:
			f.write(record)
		os.chmod(RECORD, 0o644)
	RAN.clear()


def run():
	# (exit code or None, migrations run, file, record, stderr)
	err = io.StringIO()
	code = None
	RAN.clear()
	with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
		try:
			migrate.run_migrations()
		except SystemExit as e:
			code = e.code
	def read(p):
		try:
			with open(p) as f:
				return f.read().strip()
		except FileNotFoundError:
			return None
	return code, list(RAN), read(VERSION), read(RECORD), err.getvalue()


state(version=12)
check("no record: file counts, record written", run()[:4], (None, [13, 14, 15], "15", "15 " + ROOT))
check("agree: nothing runs", run()[:4], (None, [], "15", "15 " + ROOT))

state(version=7, record="15 %s\n" % ROOT)
code, ran, v, r, err = run()
check("lower number: stopped, nothing run, both kept", (code, ran, v, r), (1, [], "7", "15 " + ROOT))
check("lower number: the message names both ways", ("remove " + RECORD in err, "echo 15 >" in err), (True, True))

state(version=14, record="13 %s\n" % ROOT)
check("higher number than the record: taken", run()[:4], (None, [15], "15", "15 " + ROOT))

state(version=999, record="15 %s\n" % ROOT)
code, ran, v, r, err = run()
check("number above the newest: stopped, nothing run, both kept", (code, ran, v, r), (1, [], "999", "15 " + ROOT))
check("number above the newest: the message names the recorded number", "echo 15 >" in err, True)
with open(VERSION, "w") as f:
	f.write("15\n")
check("then the right number written back is taken", run()[:4], (None, [], "15", "15 " + ROOT))
setattr(migrate, "migration_16", recorder(16))
check("and a later release's migration runs", run()[:4], (None, [16], "16", "16 " + ROOT))
state(version=999, record="15 %s\n" % ROOT)
check("number above the newest with a later release: stopped, its migration not skipped",
	run()[:4], (1, [], "999", "15 " + ROOT))
delattr(migrate, "migration_16")
state(version=999, record=None)
code, ran, v, r, err = run()
check("number above the newest, no record: stopped, no record written", (code, ran, v, r), (1, [], "999", None))
check("number above the newest, no record: the message names the newest", "echo 15 >" in err, True)
state(version=16, record="16 %s\n" % ROOT)
check("a downgrade (file and record of a newer release): taken, the record not lowered",
	run()[:4], (None, [], "16", "16 " + ROOT))
state(version=17, record="16 %s\n" % ROOT)
check("a downgrade after a run that ended before the record: stopped", run()[:4], (1, [], "17", "16 " + ROOT))
state(version=None, record="12 %s\n" % ROOT)
check("file missing: from the record", run()[:4], (None, [13, 14, 15], "15", "15 " + ROOT))
import pwd  # noqa: E402
migrate.load_environment = lambda: {"STORAGE_ROOT": ROOT, "STORAGE_USER": pwd.getpwuid(os.getuid()).pw_name}
state(version=None, record="15 %s\n" % ROOT)
os.makedirs(ROOT, exist_ok=True)
check("file missing: written back, the storage user's, mode 0644", (run()[:3], oct(os.stat(VERSION).st_mode & 0o777)), ((None, [], "15"), "0o644"))
migrate.load_environment = lambda: {"STORAGE_ROOT": ROOT}

state(version=None, record=None)
check("new STORAGE_ROOT without record: skipped as before", run()[:4], (None, [], None, None))

state(version=7, record="15 /home/other\n")
check("record of another STORAGE_ROOT does not count", run()[:4], (None, list(range(8, 16)), "15", "15 " + ROOT))

state(version=15, record="15 %s\n" % ROOT)
os.chmod(RECORD, 0o666)
check("record writable by others: stopped", run()[0], 1)
state(version=15, record=None)
os.makedirs(os.path.dirname(RECORD))
os.symlink(VERSION, RECORD)
check("record a symbolic link: stopped", run()[0], 1)
state(version=15, record="garbage\n")
check("record without a number: stopped", run()[0], 1)

state(version=11, record="11 %s\n" % ROOT)
FAIL_AT.append(14)
check("failed migration: file and record at the last one", run()[:4], (1, [12, 13], "13", "13 " + ROOT))
FAIL_AT.clear()
check("then the next run goes on", run()[:4], (None, [14, 15], "15", "15 " + ROOT))

state(version="x7", record=None)
check("not a number in the file: stopped", run()[0], 1)

state()
migrate.write_migration_record({"STORAGE_ROOT": ROOT}, 15)
check("--record writes the record", migrate.read_migration_record({"STORAGE_ROOT": ROOT}), 15)
check("record mode", oct(os.stat(RECORD).st_mode & 0o777), "0o644")

shutil.rmtree(tmp)
if failures:
	print("\n%d case(s) failed: %s" % (len(failures), ", ".join(failures)))
	sys.exit(1)
print("\nall cases pass")
