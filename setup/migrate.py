#!/usr/bin/python3

# Migrates any file structures, database schemas, etc. between versions of Mail-in-a-Box.

# We have to be careful here that any dependencies are already installed in the previous
# version since this script runs before all other aspects of the setup script.

import sys, os, os.path, glob, re, shutil, stat, importlib.util

sys.path.insert(0, 'management')
from utils import load_environment, save_environment, shell
import contextlib

def migration_1(env):
	# Re-arrange where we store SSL certificates. There was a typo also.

	def move_file(fn, domain_name_escaped, filename):
		# Moves an SSL-related file into the right place.
		fn1 = os.path.join( env["STORAGE_ROOT"], 'ssl', domain_name_escaped, file_type)
		os.makedirs(os.path.dirname(fn1), exist_ok=True)
		shutil.move(fn, fn1)

	# Migrate the 'domains' directory.
	for sslfn in glob.glob(os.path.join( env["STORAGE_ROOT"], 'ssl/domains/*' )):
		fn = os.path.basename(sslfn)
		m = re.match(r"(.*)_(certifiate.pem|cert_sign_req.csr|private_key.pem)$", fn)
		if m:
			# get the new name for the file
			domain_name, file_type = m.groups()
			if file_type == "certifiate.pem": file_type = "ssl_certificate.pem" # typo
			if file_type == "cert_sign_req.csr": file_type = "certificate_signing_request.csr" # nicer
			move_file(sslfn, domain_name, file_type)

	# Move the old domains directory if it is now empty.
	with contextlib.suppress(Exception):
		os.rmdir(os.path.join( env["STORAGE_ROOT"], 'ssl/domains'))

def migration_2(env):
	# Delete the .dovecot_sieve script everywhere. This was formerly a copy of our spam -> Spam
	# script. We now install it as a global script, and we use managesieve, so the old file is
	# irrelevant. Also delete the compiled binary form.
	for fn in glob.glob(os.path.join(env["STORAGE_ROOT"], 'mail/mailboxes/*/*/.dovecot.sieve')):
		os.unlink(fn)
	for fn in glob.glob(os.path.join(env["STORAGE_ROOT"], 'mail/mailboxes/*/*/.dovecot.svbin')):
		os.unlink(fn)

def migration_3(env):
	# Move the migration ID from /etc/mailinabox.conf to $STORAGE_ROOT/mailinabox.version
	# so that the ID stays with the data files that it describes the format of. The writing
	# of the file will be handled by the main function.
	pass

def migration_4(env):
	# Add a new column to the mail users table where we can store administrative privileges.
	db = os.path.join(env["STORAGE_ROOT"], 'mail/users.sqlite')
	shell("check_call", ["sqlite3", db, "ALTER TABLE users ADD privileges TEXT NOT NULL DEFAULT ''"])

def migration_5(env):
	# The secret key for encrypting backups was world readable. Fix here.
	os.chmod(os.path.join(env["STORAGE_ROOT"], 'backup/secret_key.txt'), 0o600)

def migration_6(env):
	# We now will generate multiple DNSSEC keys for different algorithms, since TLDs may
	# not support them all. .email only supports RSA/SHA-256. Rename the keys.conf file
	# to be algorithm-specific.
	basepath = os.path.join(env["STORAGE_ROOT"], 'dns/dnssec')
	shutil.move(os.path.join(basepath, 'keys.conf'), os.path.join(basepath, 'RSASHA1-NSEC3-SHA1.conf'))

def migration_7(env):
	# I previously wanted domain names to be stored in Unicode in the database. Now I want them
	# to be in IDNA. Affects aliases only.
	import sqlite3
	conn = sqlite3.connect(os.path.join(env["STORAGE_ROOT"], "mail/users.sqlite"))

	# Get existing alias source addresses.
	c = conn.cursor()
	c.execute('SELECT source FROM aliases')
	aliases = [ row[0] for row in c.fetchall() ]

	# Update to IDNA-encoded domains.
	for email in aliases:
		try:
			localpart, domainpart = email.split("@")
			domainpart = domainpart.encode("idna").decode("ascii")
			newemail = localpart + "@" + domainpart
			if newemail != email:
				c = conn.cursor()
				c.execute("UPDATE aliases SET source=? WHERE source=?", (newemail, email))
				if c.rowcount != 1: raise ValueError("Alias not found.")
				print("Updated alias", email, "to", newemail)
		except Exception as e:
			print("Error updating IDNA alias", email, e)

	# Save.
	conn.commit()

def migration_8(env):
	# Delete DKIM keys. We had generated 1024-bit DKIM keys.
	# By deleting the key file we'll automatically generate
	# a new key, which will be 2048 bits.
	os.unlink(os.path.join(env['STORAGE_ROOT'], 'mail/dkim/mail.private'))

def migration_9(env):
	# Add a column to the aliases table to store permitted_senders,
	# which is a list of user account email addresses that are
	# permitted to send mail using this alias instead of their own
	# address. This was motivated by the addition of #427 ("Reject
	# outgoing mail if FROM does not match Login") - which introduced
	# the notion of outbound permitted-senders.
	db = os.path.join(env["STORAGE_ROOT"], 'mail/users.sqlite')
	shell("check_call", ["sqlite3", db, "ALTER TABLE aliases ADD permitted_senders TEXT"])

def migration_10(env):
	# Clean up the SSL certificates directory.

	# Move the primary certificate to a new name and then
	# symlink it to the system certificate path.
	import datetime
	system_certificate = os.path.join(env["STORAGE_ROOT"], 'ssl/ssl_certificate.pem')
	if not os.path.islink(system_certificate): # not already a symlink
		new_path = os.path.join(env["STORAGE_ROOT"], 'ssl', env['PRIMARY_HOSTNAME'] + "-" + datetime.datetime.now().date().isoformat().replace("-", "") + ".pem")
		print("Renamed", system_certificate, "to", new_path, "and created a symlink for the original location.")
		shutil.move(system_certificate, new_path)
		os.symlink(new_path, system_certificate)

	# Flatten the directory structure. For any directory
	# that contains a single file named ssl_certificate.pem,
	# move the file out and name it the same as the directory,
	# and remove the directory.
	for sslcert in glob.glob(os.path.join( env["STORAGE_ROOT"], 'ssl/*/ssl_certificate.pem' )):
		d = os.path.dirname(sslcert)
		if len(os.listdir(d)) == 1:
			# This certificate is the only file in that directory.
			newname = os.path.join(env["STORAGE_ROOT"], 'ssl', os.path.basename(d) + '.pem')
			if not os.path.exists(newname):
				shutil.move(sslcert, newname)
				os.rmdir(d)

def migration_11(env):
	# Archive the old Let's Encrypt account directory managed by free_tls_certificates
	# because we'll use that path now for the directory managed by certbot.
	try:
		old_path = os.path.join(env["STORAGE_ROOT"], 'ssl', 'lets_encrypt')
		new_path = os.path.join(env["STORAGE_ROOT"], 'ssl', 'lets_encrypt-old')
		shutil.move(old_path, new_path)
	except:
		# meh
		pass

def migration_12(env):
	# Upgrading to Carddav Roundcube plugin to version 3+, it requires the carddav_*
        # tables to be dropped.
        # Checking that the roundcube database already exists.
        if os.path.exists(os.path.join(env["STORAGE_ROOT"], "mail/roundcube/roundcube.sqlite")):
            import sqlite3
            conn = sqlite3.connect(os.path.join(env["STORAGE_ROOT"], "mail/roundcube/roundcube.sqlite"))
            c = conn.cursor()
            # Get a list of all the tables that begin with 'carddav_'
            c.execute("SELECT name FROM sqlite_master WHERE type = ? AND name LIKE ?", ('table', 'carddav_%'))
            carddav_tables = c.fetchall()
            # If there were tables that begin with 'carddav_', drop them
            if carddav_tables:
                for table in carddav_tables:
                    try:
                        table = table[0]
                        c = conn.cursor()
                        dropcmd = f"DROP TABLE {table}"
                        c.execute(dropcmd)
                    except:
                        print("Failed to drop table", table)
            # Save.
            conn.commit()
            conn.close()

            # Delete all sessions, requiring users to login again to recreate carddav_*
            # databases
            conn = sqlite3.connect(os.path.join(env["STORAGE_ROOT"], "mail/roundcube/roundcube.sqlite"))
            c = conn.cursor()
            c.execute("delete from session;")
            conn.commit()
            conn.close()

def migration_13(env):
	# Add the "mfa" table for configuring MFA for login to the control panel.
	db = os.path.join(env["STORAGE_ROOT"], 'mail/users.sqlite')
	shell("check_call", ["sqlite3", db, "CREATE TABLE mfa (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, type TEXT NOT NULL, secret TEXT NOT NULL, mru_token TEXT, label TEXT, FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE);"])

def migration_14(env):
	# Add the "auto_aliases" table.
	db = os.path.join(env["STORAGE_ROOT"], 'mail/users.sqlite')
	shell("check_call", ["sqlite3", db, "CREATE TABLE auto_aliases (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL UNIQUE, destination TEXT NOT NULL, permitted_senders TEXT);"])

def migration_15(env):
	# Add a column to the users table to store their quota limit.  Default to '0' for unlimited.
	db = os.path.join(env["STORAGE_ROOT"], 'mail/users.sqlite')
	shell("check_call", ["sqlite3", db, "ALTER TABLE users ADD COLUMN quota TEXT NOT NULL DEFAULT '0';"])


###########################################################

def get_current_migration():
	ver = 0
	while True:
		next_ver = (ver + 1)
		migration_func = globals().get("migration_%d" % next_ver)
		if not migration_func:
			return ver
		ver = next_ver

# $STORAGE_ROOT is the home of the storage user, who may put a symbolic link,
# a FIFO or a huge file at mailinabox.version. It is read only as a regular
# file and only its first bytes, and written with tools/write_conf.py (a new
# file renamed over the old one, keeping its owner and mode, refusing a link)
# instead of open("w") by path as root (B147).
def read_migration_id(path):
	fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
	with os.fdopen(fd, "rb") as f:
		if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
			raise OSError(f"{path} is not a regular file")
		return f.read(64).decode("utf-8", "replace").strip()

def load_write_conf():
	spec = importlib.util.spec_from_file_location("write_conf",
		os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools", "write_conf.py"))
	write_conf = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(write_conf)
	return write_conf

def write_migration_id(path, ver):
	load_write_conf().write_if_changed(path, (str(ver) + "\n").encode())

# The storage user owns $STORAGE_ROOT and so mailinabox.version: it could
# write a lower number there, and the next setup run would run the data
# migrations from there again as root (each one that cannot run twice
# stopped setup, but before that, depending on the number, migration 8
# deleted the DKIM key, 11 moved the Let's Encrypt account away, 12 dropped
# Roundcube's CardDAV tables and all webmail sessions, 5 chmodded
# backup/secret_key.txt). Setup therefore also records the number of the last
# migration that ran on this box in a file of root's own,
# /var/lib/mailinabox/storage-migration ("NUMBER STORAGE_ROOT"), and does not
# trust a lower number in mailinabox.version (B211). The record counts only for
# the STORAGE_ROOT it names. mailinabox.version stays where it is and as it
# is, so that it goes with the data into backups and to a new box (where no
# record exists, the file counts, as before). A higher number than the record
# counts (the number written after a migration and before the record, a run
# that ended in between), but only up to the newest migration here: above
# it, setup stops unless the record says the same (a downgrade); a missing
# mailinabox.version is taken from the record.
MIGRATION_RECORD = "/var/lib/mailinabox/storage-migration"
RECORD_OWNER = 0 # root (tests/fork/migration-record.py runs as another user)

def read_migration_record(env, path=None):
	# The recorded number for this STORAGE_ROOT, or None.
	path = path or MIGRATION_RECORD
	try:
		fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
	except FileNotFoundError:
		return None
	with os.fdopen(fd, "rb") as f:
		st = os.fstat(f.fileno())
		if not stat.S_ISREG(st.st_mode) or st.st_uid != RECORD_OWNER or st.st_mode & 0o022:
			raise OSError(f"{path} is not a regular file of root's own")
		text = f.read(4096).decode("utf-8", "replace").strip()
	number, _, root = text.partition(" ")
	if not number.isdigit():
		raise OSError(f"{path} does not start with a number")
	if root != env["STORAGE_ROOT"]:
		return None
	return int(number)

def write_migration_record(env, ver, path=None):
	path = path or MIGRATION_RECORD
	if "\n" in env["STORAGE_ROOT"]:
		raise OSError("STORAGE_ROOT has a line break")
	os.makedirs(os.path.dirname(path), mode=0o755, exist_ok=True)
	load_write_conf().write_if_changed(path, ("%d %s\n" % (ver, env["STORAGE_ROOT"])).encode())

def run_migrations():
	if not os.access("/etc/mailinabox.conf", os.W_OK, effective_ids=True):
		print("This script must be run as root.", file=sys.stderr)
		sys.exit(1)

	env = load_environment()

	migration_id_file = os.path.join(env['STORAGE_ROOT'], 'mailinabox.version')
	migration_id = None
	if os.path.lexists(migration_id_file):
		try:
			migration_id = read_migration_id(migration_id_file)
		except OSError as e:
			print(f"Cannot read {migration_id_file}: {e}", file=sys.stderr)
			sys.exit(1)

	try:
		recorded = read_migration_record(env)
	except OSError as e:
		print(f"Cannot read {MIGRATION_RECORD}: {e}", file=sys.stderr)
		sys.exit(1)

	if migration_id is None:
		# Load the legacy location of the migration ID. We'll drop support
		# for this eventually.
		migration_id = env.get("MIGRATIONID")

	if migration_id is None and recorded is not None:
		# The file is gone, but this box ran the migrations up to the
		# record on this STORAGE_ROOT: go on from there (setup/start.sh
		# would otherwise take the data for new and skip all migrations).
		print(f"{migration_id_file} is missing; this box recorded migration #{recorded} for it ({MIGRATION_RECORD}).")
		migration_id = str(recorded)
		try:
			write_migration_id(migration_id_file, recorded)
			# The storage user's again, as setup/start.sh makes it (B147).
			if env.get("STORAGE_USER"):
				import pwd
				pw = pwd.getpwnam(env["STORAGE_USER"])
				load_write_conf().own(migration_id_file, pw.pw_uid, pw.pw_gid, 0o644)
		except (OSError, KeyError) as e:
			print(f"Cannot write {migration_id_file}: {e}", file=sys.stderr)
			sys.exit(1)

	if migration_id is None:
		print()
		print(f"{migration_id_file} file doesn't exists. Skipping migration...")
		return

	if not str(migration_id).strip().isdigit():
		print(f"{migration_id_file} does not hold the number of a migration.", file=sys.stderr)
		sys.exit(1)
	ourver = int(migration_id)

	if recorded is not None and ourver < recorded:
		print(f"""
{migration_id_file} says #{ourver}, but this box has run the data
migrations up to #{recorded} on {env['STORAGE_ROOT']} ({MIGRATION_RECORD}).
Setup does not run migrations again for a lower number: the storage user
owns that file, and a migration that runs twice can delete data (B211).

* If you restored an older backup of {env['STORAGE_ROOT']}, its migrations
  must run: remove {MIGRATION_RECORD} and run setup again.
* Otherwise put the number back, as the storage user (not as root by path
  in its directory):
  sudo -u {env.get('STORAGE_USER', 'user-data')} sh -c 'echo {recorded} > {migration_id_file}'
  and run setup again.""", file=sys.stderr)
		sys.exit(1)

	# A number above the newest migration of this version that the record
	# does not confirm (the storage user's, or a typo; a downgrade leaves the
	# record of the newer release, which ran its migrations up to the number
	# it wrote): no migration would run from there, neither now nor after an
	# update, so the migrations of a later release would be skipped and the
	# record would then claim them. Stop, as for a lower number.
	newest = get_current_migration()
	if ourver > newest and (recorded is None or recorded < ourver):
		if recorded is not None:
			back = recorded
			record_text = f"this box has run the data migrations\nup to #{recorded} on {env['STORAGE_ROOT']} ({MIGRATION_RECORD})."
			back_text = f"#{recorded}, as recorded"
		else:
			back = newest
			record_text = f"this box has no record of the data\nmigrations on {env['STORAGE_ROOT']} ({MIGRATION_RECORD})."
			back_text = f"#{newest} if this version set up the data"
		print(f"""
{migration_id_file} says #{ourver}, more than the newest data
migration of this version (#{newest}), and {record_text}
Setup does not take such a number: the data migrations of later releases
would never run (B211).

* If a newer release of Mail-in-a-Box ran its migrations on this data, run
  the setup of that release.
* Otherwise put the number of the last migration that ran back
  ({back_text}), as the storage user (not as root by path in its
  directory):
  sudo -u {env.get('STORAGE_USER', 'user-data')} sh -c 'echo {back} > {migration_id_file}'
  and run setup again.""", file=sys.stderr)
		sys.exit(1)

	while True:
		next_ver = (ourver + 1)
		migration_func = globals().get("migration_%d" % next_ver)

		if not migration_func:
			# No more migrations to run.
			break

		print()
		print("Running migration to Mail-in-a-Box #%d..." % next_ver)

		try:
			migration_func(env)
		except Exception as e:
			print()
			print("Error running the migration script:")
			print()
			print(e)
			print()
			print("Your system may be in an inconsistent state now. We're terribly sorry. A re-install from a backup might be the best way to continue.")
			sys.exit(1)

		ourver = next_ver

		# Write out our current version now. Do this sooner rather than later
		# in case of any problems. mailinabox.version first, then the record:
		# a run that ends in between leaves a higher number in the file,
		# which the next run takes (see above).
		try:
			write_migration_id(migration_id_file, ourver)
			write_migration_record(env, ourver)
		except OSError as e:
			print(f"Cannot write {migration_id_file} or {MIGRATION_RECORD}: {e}", file=sys.stderr)
			sys.exit(1)

		# Delete the legacy location of this field.
		if "MIGRATIONID" in env:
			del env["MIGRATIONID"]
			save_environment(env)

		# iterate and try next version...

	# The record of a box that had none (the first run of this version), or
	# after a higher number in the file (up to the newest migration here, see
	# above). Never lowered (a downgrade keeps the record of the newer
	# release, whose number is then also in the file).
	if recorded is None or ourver > recorded:
		try:
			write_migration_record(env, ourver)
		except OSError as e:
			print(f"Cannot write {MIGRATION_RECORD}: {e}", file=sys.stderr)
			sys.exit(1)

if __name__ == "__main__":
	if sys.argv[-1] == "--current":
		# Return the number of the highest migration.
		print(str(get_current_migration()))
	elif sys.argv[-1] == "--migrate":
		# Perform migrations.
		run_migrations()
	elif len(sys.argv) == 4 and sys.argv[1] == "--record":
		# setup/start.sh on a new STORAGE_ROOT: record its number (B211).
		write_migration_record({"STORAGE_ROOT": sys.argv[2]}, int(sys.argv[3]))

