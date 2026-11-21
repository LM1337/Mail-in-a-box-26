#!/usr/bin/env python3
"""
Offline test of the checked directories below STORAGE_ROOT (B212) --
python3 stdlib only, no box needed.

$STORAGE_ROOT/backup and $STORAGE_ROOT/dns belong to root, but the storage
user owns STORAGE_ROOT and can replace either. management/backup.py and
management/dns_update.py read and write their files only through the
checked directory (management/utils.py open_root_dir, read_root_file,
write_root_file). Run as an ordinary user: "root's own" is this user here
(utils.ROOT_DIR_OWNER), and rtyaml, dateutil, exclusiveprocess, dnspython,
ssl_certificates and mailconfig are replaced by stand-ins (YAML as JSON).

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
    directory with its read bits kept; web_update.py (the web configuration,
    the TLS certificates, the status checks) goes on without the records
    of a replaced dns/ and says why, instead of failing; the KSK's public
    key that the status checks show with the DS records is read only
    through a checked dns/ and dns/dnssec/, a replaced one or a link there
    gives ValueError (B183); the zone signing reads the .conf files and the
    keys only through them (the keys' hash as before) and writes the
    patched copies only into its temporary directory: a replaced dns/, a
    key name with a path, a key file that is a link and a .conf without a
    ZSK are refused, and nothing is written elsewhere (B191);
  * tools/write_conf.py --own-root-only (setup's owner of $STORAGE_ROOT/mail
    and users.sqlite) refuses a directory that root does not own already,
    where --own would take it over; --check-own-root-only (setup/start.sh's
    check before setup changes anything) names such a directory or
    database, and setup/start.sh runs it for both.

  tests/fork/storage-dirs.py

Exit code: 0 = all cases pass, 1 = a case failed (printed).
"""

import contextlib
import io
import json
import os
import shutil
import subprocess
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
		"dns", "dns.resolver", "ssl_certificates", "mailconfig"):
	sys.modules[name] = Anything(name)

import utils  # noqa: E402
utils.ROOT_DIR_OWNER = os.getuid()
import backup  # noqa: E402
import dns_update  # noqa: E402
import web_update  # noqa: E402

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
WEB_ENV = dict(ENV, PUBLIC_IP="192.0.2.100", PUBLIC_IPV6="2001:db8::100")
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
	with contextlib.redirect_stderr(io.StringIO()) as err:
		got = web_update.get_domains_with_a_records(WEB_ENV)
	check("dns %s: web and TLS go on without the records, with the reason" % how, (got, "not used" in err.getvalue()), (set(), True))
fresh()
check("dns: web_update reads the custom A records", web_update.get_domains_with_a_records(WEB_ENV), {"www.example.com"})

# The status checks' DNSSEC check reads the KSK's public key only through
# the checked dns/ and dns/dnssec/ (B183).
def dnssec_keys():
	k = os.path.join(ROOT, "dns", "dnssec")
	os.makedirs(k, exist_ok=True)
	os.chmod(k, 0o755)
	write(os.path.join(k, "ECDSAP256SHA256.conf"), "KSK=K_domain_.+013+11111\nZSK=K_domain_.+013+22222\n", 0o644)
	write(os.path.join(k, "K_domain_.+013+11111.key"), "_domain_.\tIN\tDNSKEY\t257 3 13 GOODKEY\n", 0o600)
fresh()
dnssec_keys()
check("dnssec key: read through the checked directories", dns_update.read_dnssec_ksk_pubkey(ENV, "ECDSAP256SHA256"), "GOODKEY")
check("dnssec key: an algorithm without a .conf", raises(dns_update.read_dnssec_ksk_pubkey, ENV, "RSASHA256"), "ValueError")
for how in ("link", "group-writable", "own directory without dnssec/"):
	fresh()
	dnssec_keys()
	if how == "own directory without dnssec/":
		shutil.rmtree(os.path.join(ROOT, "dns"))
		os.makedirs(os.path.join(ROOT, "dns"))
		os.chmod(os.path.join(ROOT, "dns"), 0o755)
	else:
		swap("dns", how)
	check("dnssec key, dns/ replaced (%s): ValueError, no other exception" % how,
		raises(dns_update.read_dnssec_ksk_pubkey, ENV, "ECDSAP256SHA256"), "ValueError")
fresh()
dnssec_keys()
k = os.path.join(ROOT, "dns", "dnssec")
os.makedirs(os.path.join(OUTSIDE, "dnssec"))
write(os.path.join(OUTSIDE, "dnssec", "ECDSAP256SHA256.conf"), "KSK=K_domain_.+013+33333\n", 0o644)
write(os.path.join(OUTSIDE, "dnssec", "K_domain_.+013+33333.key"), "_domain_.\tIN\tDNSKEY\t257 3 13 EVILKEY\n", 0o644)
shutil.rmtree(k)
os.symlink(os.path.join(OUTSIDE, "dnssec"), k)
check("dnssec key, dnssec/ a link: refused", raises(dns_update.read_dnssec_ksk_pubkey, ENV, "ECDSAP256SHA256"), "ValueError")
os.unlink(k)
dnssec_keys()
os.unlink(os.path.join(k, "K_domain_.+013+11111.key"))
os.symlink(os.path.join(OUTSIDE, "dnssec", "K_domain_.+013+33333.key"), os.path.join(k, "K_domain_.+013+11111.key"))
check("dnssec key, the .key a link: refused", raises(dns_update.read_dnssec_ksk_pubkey, ENV, "ECDSAP256SHA256"), "ValueError")
write(os.path.join(k, "ECDSAP256SHA256.conf"), "KSK=../../outside/x\n", 0o644)
check("dnssec key, a KSK name with a path: refused", raises(dns_update.read_dnssec_ksk_pubkey, ENV, "ECDSAP256SHA256"), "ValueError")

# Signing the zones (as root, the nightly job and every DNS update) reads the
# .conf files and the keys only through the checked dns/ and dns/dnssec/, and
# writes the patched copies only into its temporary directory (B191).
import hashlib  # noqa: E402
TMPBASE = os.path.join(tmp, "t")  # the parent of sign_zone's temporary directory

def signing_keys():
	dnssec_keys()
	k = os.path.join(ROOT, "dns", "dnssec")
	write(os.path.join(k, "K_domain_.+013+11111.private"), "Private-key-format: v1.3\nPrivateKey: KSKPRIV\n", 0o600)
	write(os.path.join(k, "K_domain_.+013+22222.key"), "_domain_.\tIN\tDNSKEY\t256 3 13 ZSKPUB\n", 0o600)
	write(os.path.join(k, "K_domain_.+013+22222.private"), "Private-key-format: v1.3\nPrivateKey: ZSKPRIV\n", 0o600)
	write(os.path.join(k, "RSASHA256.conf"), "KSK=K_domain_.+008+33333\nZSK=K_domain_.+008+44444\nDOMAINS=none\n", 0o644)

def sign(domain="example.com"):
	# sign_zone with ldns-signzone and ldns-key2ds replaced: what it would
	# have signed with, and the patched copies it wrote.
	calls, seen = [], {}
	def shell(method, cmd, **kw):
		calls.append(cmd)
		if cmd[0].endswith("ldns-signzone"):
			for key in cmd[5:]:
				for ext in (".key", ".private"):
					st = os.lstat(key + ext)
					seen[os.path.basename(key) + ext] = (open(key + ext).read(), oct(st.st_mode & 0o777), os.path.dirname(key))
		return "DS\n" if method == "check_output" else 0
	os.makedirs(TMPBASE, exist_ok=True)
	dns_update.shell = shell
	# The .ds file next to the zone goes to the test's directory.
	dns_update.open = lambda p, *a, **k: open(os.path.join(tmp, "zone.ds") if p.startswith("/etc/nsd/") else p, *a, **k)
	saved_tempdir, tempfile.tempdir = tempfile.tempdir, TMPBASE
	try:
		dns_update.sign_zone(domain, "example.com.txt", ENV)
	finally:
		del dns_update.open
		dns_update.shell = utils.shell
		tempfile.tempdir = saved_tempdir
	return calls, seen

fresh()
signing_keys()
want = hashlib.sha1("".join(["KSK", "K_domain_.+013+11111", "Private-key-format: v1.3\nPrivateKey: KSKPRIV\n",
	"ZSK", "K_domain_.+013+22222", "Private-key-format: v1.3\nPrivateKey: ZSKPRIV\n"]).encode("utf8")).hexdigest()
check("dnssec signing: the keys' hash as before (no zone is signed again for it)", dns_update.hash_dnssec_keys("example.com", ENV), want)
calls, seen = sign()
check("dnssec signing: signed with the KSK and the ZSK of the enabled algorithm",
	sorted(seen), ["Kexample.com.+013+11111.key", "Kexample.com.+013+11111.private", "Kexample.com.+013+22222.key", "Kexample.com.+013+22222.private"])
check("dnssec signing: the copies patched, 0600, in one temporary directory outside STORAGE_ROOT",
	(seen.get("Kexample.com.+013+11111.key", ("",))[0], {v[1] for v in seen.values()}, len({v[2] for v in seen.values()}),
	any(v[2].startswith(ROOT) for v in seen.values())),
	("example.com.\tIN\tDNSKEY\t257 3 13 GOODKEY\n", {"0o600"}, 1, False))
check("dnssec signing: the temporary directory is gone", any(os.path.exists(v[2]) for v in seen.values()), False)
check("dnssec signing: the DS records from the KSK only", [c[-1] for c in calls if c[0].endswith("ldns-key2ds")],
	[os.path.join(next(iter(seen.values()))[2], "Kexample.com.+013+11111.key")] * 3 if seen else None)
# The case of the review: the .conf names a key outside dnssec/. From
# dnssec/ the path reaches the storage user's files in STORAGE_ROOT, from the
# temporary directory a directory of root's elsewhere (here tmp/etc/logrotate.d).
evil = "KSK=../../etc/logrotate.d/x\nZSK=K_domain_.+013+22222\n"
for how in ("dns/ replaced (group-writable)", "dnssec/ of root's, the KSK with a path"):
	fresh()
	if how.startswith("dns/ replaced"):
		swap("dns", "group-writable")
	signing_keys()
	write(os.path.join(ROOT, "dns", "dnssec", "ECDSAP256SHA256.conf"), evil, 0o644)
	write(os.path.join(ROOT, "etc", "logrotate.d", "x.private"), "/var/log/x { postrotate\n id\n endscript }\n", 0o644)
	write(os.path.join(ROOT, "etc", "logrotate.d", "x.key"), "x\n", 0o644)
	os.makedirs(os.path.join(tmp, "etc", "logrotate.d"))
	check("dnssec signing, %s: the hash refused (ValueError)" % how, raises(dns_update.hash_dnssec_keys, "example.com", ENV), "ValueError")
	check("dnssec signing, %s: signing refused (ValueError)" % how, raises(sign), "ValueError")
	check("dnssec signing, %s: nothing written outside the temporary directory" % how,
		os.listdir(os.path.join(tmp, "etc", "logrotate.d")), [])
fresh()
signing_keys()
k = os.path.join(ROOT, "dns", "dnssec")
os.unlink(os.path.join(k, "K_domain_.+013+22222.private"))
write(os.path.join(OUTSIDE, "zsk.private"), "PrivateKey: OTHER\n", 0o600)
os.symlink(os.path.join(OUTSIDE, "zsk.private"), os.path.join(k, "K_domain_.+013+22222.private"))
check("dnssec signing, a key file a link: refused", (raises(dns_update.hash_dnssec_keys, "example.com", ENV), raises(sign)), ("ValueError", "ValueError"))
os.unlink(os.path.join(k, "K_domain_.+013+22222.private"))
write(os.path.join(k, "K_domain_.+013+22222.private"), "PrivateKey: ZSKPRIV\n", 0o600)
write(os.path.join(k, "ECDSAP256SHA256.conf"), "KSK=K_domain_.+013+11111\n", 0o644)
check("dnssec signing, a .conf without a ZSK: refused", raises(sign), "ValueError")
shutil.rmtree(os.path.join(ROOT, "dns"))
check("dnssec signing, no dns/: an error as before (no keys, no zone)", raises(sign), "ValueError")

# tools/write_conf.py --own-root-only ($STORAGE_ROOT/mail and users.sqlite):
# only what root owns already is taken, not a directory or database that the
# storage user put in place of them.
import importlib.util  # noqa: E402
spec = importlib.util.spec_from_file_location("write_conf", os.path.join(MGMT, "..", "tools", "write_conf.py"))
write_conf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(write_conf)
me, mygid = os.getuid(), os.getgid()
d = os.path.join(tmp, "mail")
os.makedirs(d, exist_ok=True)
os.chmod(d, 0o775)
write_conf.ROOT_UID = me + 1
check("--own-root-only: another owner's directory refused", raises(write_conf.own, d, me, mygid, 0o755, True), "OSError")
check("--own-root-only: refused, mode unchanged", oct(os.stat(d).st_mode & 0o777), "0o775")
write_conf.own(d, me, mygid, 0o755)
check("--own takes it (the old behaviour)", oct(os.stat(d).st_mode & 0o777), "0o755")
write_conf.ROOT_UID = me
os.chmod(d, 0o775)
write_conf.own(d, me, mygid, 0o755, True)
check("--own-root-only: root's own directory taken", oct(os.stat(d).st_mode & 0o777), "0o755")

# --check-own-root-only: setup/start.sh's check before setup changes anything.
db = os.path.join(d, "users.sqlite")
with open(db, "w") as f:
	f.write("db")
write_conf.ROOT_UID = me + 1
check("--check-own: another owner's directory is fine", write_conf.check_own(d), None)
check("--check-own-root-only: another owner's directory named",
	"belongs to uid %d, not to root" % me in (write_conf.check_own(d, True) or ""), True)
check("--check-own-root-only: another owner's database named",
	"users.sqlite belongs to uid %d" % me in (write_conf.check_own(db, True) or ""), True)
check("--check-own-root-only: a missing path is fine", write_conf.check_own(os.path.join(d, "none"), True), None)
os.symlink(db, os.path.join(d, "link"))
check("--check-own-root-only: a link is named as a link",
	"is a symbolic link" in (write_conf.check_own(os.path.join(d, "link"), True) or ""), True)
write_conf.ROOT_UID = me
check("--check-own-root-only: root's own is fine", (write_conf.check_own(d, True), write_conf.check_own(db, True)), (None, None))
if me != 0:
	p = subprocess.run([sys.executable, "-I", os.path.join(MGMT, "..", "tools", "write_conf.py"), "--check-own-root-only", d, db],
		capture_output=True, text=True)
	check("--check-own-root-only (command): exit 1, both named",
		(p.returncode, p.stdout.count("not to root")), (1, 2))
	p = subprocess.run([sys.executable, "-I", os.path.join(MGMT, "..", "tools", "write_conf.py"), "--check-own-root-only", os.path.join(d, "none")],
		capture_output=True, text=True)
	check("--check-own-root-only (command): a missing path, exit 0", (p.returncode, p.stdout), (0, ""))
start_sh = open(os.path.join(MGMT, "..", "setup", "start.sh"), encoding="utf-8").read()
check("setup/start.sh checks the owner of mail/ and users.sqlite before setup changes anything",
	'tools/write_conf.py --check-own-root-only "$pf_root/mail" "$pf_root/mail/users.sqlite"' in start_sh
	and start_sh.index("--check-own-root-only") < start_sh.index("source setup/system.sh"), True)

shutil.rmtree(tmp)
if failures:
	print("\n%d case(s) failed: %s" % (len(failures), ", ".join(failures)))
	sys.exit(1)
print("\nall cases pass")
