#!/usr/bin/env python3
"""
Offline test of the checked directories below STORAGE_ROOT (B212) --
python3 stdlib only, no box needed.

$STORAGE_ROOT/backup and $STORAGE_ROOT/dns belong to root, but the storage
user owns STORAGE_ROOT and can replace either. management/backup.py and
management/dns_update.py read and write their files only through the
checked directory (management/utils.py open_root_dir, read_root_file,
write_root_file). Run as an ordinary user: "root's own" is this user here
(utils.ROOT_DIR_OWNER), and rtyaml, dateutil, exclusiveprocess, dnspython
and ssl_certificates are replaced by stand-ins (YAML as JSON).

  * open_root_dir: a directory of the owner, not writable by group or
    others, is taken; a symbolic link, a group-writable directory, one of
    another owner and a file are refused;
  * read_root_file: a regular file is read; a link, a FIFO (no hang), a file
    of another owner and one over the limit are refused;
  * write_root_file: replaces a symbolic link at the name (its target stays
    unchanged), gives the mode, leaves no temporary file;
  * backup.py: target and passphrase come from a checked backup/; with
    backup/ replaced by a link or a group-writable directory, or custom.yaml
    a link, the settings fall back to the defaults with dir_error, the
    passphrase is not read, saving the settings is refused and the nightly
    backup stops with the reason; custom.yaml is written 0600 through the
    directory (a link there is replaced, not followed);
  * dns_update.py: the custom records come from a checked dns/; a replaced
    dns/ raises ValueError (the zones are not built without the records), a
    missing file gives no records, the file is written through the
    directory with its read bits kept.

  tests/fork/storage-dirs.py

Exit code: 0 = all cases pass, 1 = a case failed (printed).
"""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import types

HERE = os.path.dirname(os.path.abspath(__file__))
MGMT = os.path.abspath(os.path.join(HERE, "..", "..", "management"))
sys.path.insert(0, MGMT)


class Anything(types.ModuleType):
	def __getattr__(self, name):
		if name.startswith("__"):
			raise AttributeError(name)
		return Anything(name)

	def __call__(self, *a, **k):
		return None


rtyaml = types.ModuleType("rtyaml")
rtyaml.load = lambda text: json.loads(text)
rtyaml.dump = lambda obj: json.dumps(obj, indent=1) + "\n"
sys.modules["rtyaml"] = rtyaml
for name in ("dateutil", "dateutil.parser", "dateutil.relativedelta", "dateutil.tz", "exclusiveprocess",
		"dns", "dns.resolver", "ssl_certificates"):
	sys.modules[name] = Anything(name)

import utils  # noqa: E402
utils.ROOT_DIR_OWNER = os.getuid()
import backup  # noqa: E402
import dns_update  # noqa: E402

failures = []


def check(name, got, want):
	if got != want:
		failures.append(name)
		print(f"FAIL {name}\n  want: {want!r}\n  got:  {got!r}")
	else:
		print(f"ok   {name}")


def raises(fn, *a):
	try:
		fn(*a)
	except Exception as e:
		return type(e).__name__
	return None


tmp = tempfile.mkdtemp(prefix="storage-dirs-")
ROOT = os.path.join(tmp, "user-data")
ENV = {"STORAGE_ROOT": ROOT}
OUTSIDE = os.path.join(tmp, "outside")
PASS = "A" * 60
EVIL = "E" * 60


def write(path, text, mode=0o600):
	os.makedirs(os.path.dirname(path), exist_ok=True)
	with open(path, "w") as f:
		f.write(text)
	os.chmod(path, mode)


def fresh():
	shutil.rmtree(tmp)
	os.makedirs(os.path.join(ROOT, "backup"))
	os.makedirs(os.path.join(ROOT, "dns"))
	os.makedirs(OUTSIDE)
	for d in ("backup", "dns"):
		os.chmod(os.path.join(ROOT, d), 0o755)
	write(os.path.join(ROOT, "backup", "custom.yaml"), json.dumps({"target": "rsync://good@example.com/box", "min_age_in_days": 5}))
	write(os.path.join(ROOT, "backup", "secret_key.txt"), PASS + "\nmore\n")
	write(os.path.join(ROOT, "dns", "custom.yaml"), json.dumps({"www.example.com": "192.0.2.1"}), 0o644)
	# What another account put elsewhere: a directory with its own settings.
	write(os.path.join(OUTSIDE, "custom.yaml"), json.dumps({"target": "rsync://evil@example.net/x"}))
	write(os.path.join(OUTSIDE, "secret_key.txt"), EVIL + "\n")


def swap(name, how):
	# Replace ROOT/name as the storage user could.
	p = os.path.join(ROOT, name)
	shutil.rmtree(p)
	if how == "link":
		os.symlink(OUTSIDE, p)
	elif how == "group-writable":
		shutil.copytree(OUTSIDE, p)
		os.chmod(p, 0o775)


# utils
fresh()
d = os.path.join(ROOT, "backup")
fd = utils.open_root_dir(d)
check("open_root_dir: own directory", type(fd), int)
check("read_root_file: regular file", utils.read_root_file(fd, "secret_key.txt").decode().split("\n")[0], PASS)
os.symlink(os.path.join(OUTSIDE, "secret_key.txt"), os.path.join(d, "link"))
check("read_root_file: link refused", raises(utils.read_root_file, fd, "link"), "OSError")
os.mkfifo(os.path.join(d, "fifo"))
result = {}
t = threading.Thread(target=lambda: result.setdefault("r", raises(utils.read_root_file, fd, "fifo")), daemon=True)
t.start()
t.join(5)
check("read_root_file: FIFO refused, no hang", result.get("r"), "OSError")
check("read_root_file: missing", raises(utils.read_root_file, fd, "nothing"), "FileNotFoundError")
write(os.path.join(d, "big"), "x" * 100)
check("read_root_file: over the limit", raises(utils.read_root_file, fd, "big", 10), "OSError")
utils.write_root_file(fd, "link", b"new\n", 0o600)
check("write_root_file: link replaced, target unchanged",
	(os.path.islink(os.path.join(d, "link")), open(os.path.join(OUTSIDE, "secret_key.txt")).read()), (False, EVIL + "\n"))
check("write_root_file: mode", oct(os.stat(os.path.join(d, "link")).st_mode & 0o777), "0o600")
check("write_root_file: no temporary file left", sorted(n for n in os.listdir(d) if n.startswith(".")), [])
os.close(fd)
os.chmod(d, 0o775)
check("open_root_dir: group-writable refused", raises(utils.open_root_dir, d), "OSError")
os.chmod(d, 0o755)
utils.ROOT_DIR_OWNER = os.getuid() + 1
check("open_root_dir: another owner refused", raises(utils.open_root_dir, d), "OSError")
utils.ROOT_DIR_OWNER = os.getuid()
check("open_root_dir: a file refused", raises(utils.open_root_dir, os.path.join(d, "big")), "OSError")
check("open_root_dir: missing", raises(utils.open_root_dir, os.path.join(ROOT, "nothing")), "FileNotFoundError")
os.rename(d, d + ".real")
os.symlink(d + ".real", d)
check("open_root_dir: symbolic link refused", raises(utils.open_root_dir, d), "OSError")

# backup.py
fresh()
c = backup.get_backup_config(ENV)
check("backup: target from the checked directory", (c["target"], c["min_age_in_days"], "dir_error" in c), ("rsync://good@example.com/box", 5, False))
check("backup: passphrase", backup.get_passphrase(ENV), PASS)
for how in ("link", "group-writable"):
	fresh()
	swap("backup", how)
	c = backup.get_backup_config(ENV)
	check("backup %s: defaults, dir_error" % how, (c["target"].startswith("file://"), bool(c.get("dir_error"))), (True, True))
	check("backup %s: passphrase not read" % how, raises(backup.get_passphrase, ENV), "BackupDirError")
	check("backup %s: settings not saved" % how, raises(backup.write_backup_config, ENV, {"target": "off"}), "BackupDirError")
	check("backup %s: outside unchanged" % how, json.load(open(os.path.join(OUTSIDE, "custom.yaml")))["target"], "rsync://evil@example.net/x")
	out = io.StringIO()
	code = None
	with contextlib.redirect_stdout(out):
		try:
			backup.load_environment = lambda: ENV
			backup.Lock = lambda **k: types.SimpleNamespace(forever=lambda: None)
			backup.perform_backup(False)
		except SystemExit as e:
			code = e.code
	check("backup %s: nightly backup stops with the reason" % how, (code, "No backup was made" in out.getvalue()), (1, True))
fresh()
p = os.path.join(ROOT, "backup", "custom.yaml")
os.unlink(p)
os.symlink(os.path.join(OUTSIDE, "custom.yaml"), p)
c = backup.get_backup_config(ENV)
check("backup custom.yaml a link: not followed, dir_error", (c["target"].startswith("file://"), bool(c.get("dir_error"))), (True, True))
backup.write_backup_config(ENV, {"target": "off", "dir_error": "x"})
check("backup write: link replaced, outside unchanged, no dir_error stored",
	(os.path.islink(p), json.load(open(p)), json.load(open(os.path.join(OUTSIDE, "custom.yaml")))["target"]),
	(False, {"target": "off"}, "rsync://evil@example.net/x"))
check("backup write: mode 0600", oct(os.stat(p).st_mode & 0o777), "0o600")
check("backup: target off read back", backup.get_backup_config(ENV)["target"], "off")
fresh()
os.unlink(os.path.join(ROOT, "backup", "custom.yaml"))
check("backup: no custom.yaml gives the default", backup.get_backup_config(ENV)["target"].startswith("file://"), True)

# dns_update.py
fresh()
check("dns: records from the checked directory", list(dns_update.get_custom_dns_config(ENV)), [("www.example.com", "A", "192.0.2.1")])
dns_update.write_custom_dns_config([("www.example.com", "A", "192.0.2.2")], ENV)
p = os.path.join(ROOT, "dns", "custom.yaml")
check("dns: written through the directory, mode kept", (json.load(open(p)), oct(os.stat(p).st_mode & 0o777)), ({"www.example.com": "192.0.2.2"}, "0o644"))
os.unlink(p)
check("dns: no custom.yaml, no records", list(dns_update.get_custom_dns_config(ENV)), [])
for how in ("link", "group-writable"):
	fresh()
	swap("dns", how)
	check("dns %s: refused (ValueError)" % how, raises(lambda: list(dns_update.get_custom_dns_config(ENV))), "ValueError")
	check("dns %s: not written" % how, raises(dns_update.write_custom_dns_config, [("a.example.com", "A", "192.0.2.9")], ENV), "ValueError")
	check("dns %s: outside unchanged" % how, "a.example.com" in open(os.path.join(OUTSIDE, "custom.yaml")).read(), False)

shutil.rmtree(tmp)
if failures:
	print("\n%d case(s) failed: %s" % (len(failures), ", ".join(failures)))
	sys.exit(1)
print("\nall cases pass")
