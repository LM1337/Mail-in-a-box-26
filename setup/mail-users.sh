#!/bin/bash
#
# User Authentication and Destination Validation
# ----------------------------------------------
#
# This script configures user authentication for Dovecot
# and Postfix (which relies on Dovecot) and destination
# validation by querying an Sqlite3 database of mail users.

source setup/functions.sh # load our functions
source /etc/mailinabox.conf # load global vars

# ### User and Alias Database

# The database of mail users (i.e. authenticated users, who have mailboxes)
# and aliases (forwarders).

db_path=$STORAGE_ROOT/mail/users.sqlite

# $STORAGE_ROOT/mail and users.sqlite belong to root alone (B210). Up to
# v78-r2604.4 the directory was root:www-data 775 and the database root:www-data
# 664, as upstream has them, because Roundcube's password plugin wrote the
# database itself as www-data (and SQLite creates its journal next to it):
# code running as www-data could rewrite every account, its password, its
# privileges and its aliases, and every local account could read all password
# hashes. Roundcube now changes a password through the management daemon
# (setup/webmail.sh, management/self_password.py), and every other reader
# opens the database as root: Dovecot's auth-worker runs as root, Postfix's
# daemons open their sqlite tables as root before they drop their privileges
# and enter their chroot, the management daemon, the nightly backup and the
# tools run as root. In SQLite's rollback journal mode (the default, see
# below) a reader needs no write access to the directory; only the writer
# (root) creates the journal there, with the database's owner and mode.
# What else is in the directory has an owner of its own (mailboxes and sieve:
# mail, dkim: opendkim, postgrey, spamassassin: spampd, roundcube: www-data),
# so the directory itself is root:root 755: www-data can no longer rename,
# replace or remove anything in it. Through descriptors (tools/write_conf.py
# --own), refusing a symbolic link (B147). Only a directory of root's is
# taken: the storage user owns $STORAGE_ROOT and can rename mail/ and put a
# directory of its own there (with a users.sqlite of its choice); --own would
# make that root's, so setup stops instead (--own-root-only). Dovecot, Postfix
# and the management daemon still open users.sqlite by path (README-fork.md,
# "Known issues").
if [ -d "$STORAGE_ROOT/mail" ]; then
	tools/write_conf.py --own-root-only "$STORAGE_ROOT/mail" root root 755
fi

# Create an empty database if it doesn't yet exist. It is made in a directory
# of root's own and written into place with tools/write_conf.py, which does not
# follow a symbolic link: up to v78-r2604.4 www-data could write in
# $STORAGE_ROOT/mail, and sqlite3 as root created the database wherever a link
# put there pointed (B147).
if [ ! -f "$db_path" ]; then
	echo "Creating new user database: $db_path";
	db_tmp=$(mktemp -d)
	echo "CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL UNIQUE, password TEXT NOT NULL, extra, privileges TEXT NOT NULL DEFAULT '', quota TEXT NOT NULL DEFAULT '0');" | sqlite3 "$db_tmp/users.sqlite";
	echo "CREATE TABLE aliases (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL UNIQUE, destination TEXT NOT NULL, permitted_senders TEXT);" | sqlite3 "$db_tmp/users.sqlite";
	echo "CREATE TABLE mfa (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, type TEXT NOT NULL, secret TEXT NOT NULL, mru_token TEXT, label TEXT, FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE);" | sqlite3 "$db_tmp/users.sqlite";
	echo "CREATE TABLE auto_aliases (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL UNIQUE, destination TEXT NOT NULL, permitted_senders TEXT);" | sqlite3 "$db_tmp/users.sqlite";
	tools/write_conf.py "$db_path" 600 < "$db_tmp/users.sqlite"
	rm -rf "$db_tmp"
fi

# Owner and mode of the database (B210): root:root 0600, the password hashes
# are no longer readable by every local account. Changing them does not touch
# the open descriptors of Dovecot and Postfix, so no lookup fails.
tools/write_conf.py --own-root-only "$db_path" root root 600

# The rollback journal, not WAL: in WAL mode every reader must be able to
# write the -shm file next to the database, and Postfix's daemons, which read
# it after they dropped their privileges, cannot (upstream #2185; setup/
# webmail.sh keeps Roundcube from switching its own database's mode). A
# database in WAL mode (byte 18 of the header is 2) is switched back, through
# the checked directory (/proc/self/fd/N: the directory that was opened, not
# a path another account could change).
python3 -I - "$STORAGE_ROOT/mail" << 'PY'
import os, sqlite3, stat, sys
sys.path.insert(0, os.path.join(os.getcwd(), "tools"))
import write_conf
dfd = write_conf.open_dir(sys.argv[1])
st = os.fstat(dfd)
if st.st_uid != 0 or st.st_mode & 0o022:
	sys.exit("%s is not a directory of root's own" % sys.argv[1])
fd = os.open("users.sqlite", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dfd)
with os.fdopen(fd, "rb") as f:
	fst = os.fstat(f.fileno())
	if not stat.S_ISREG(fst.st_mode) or fst.st_uid != 0:
		sys.exit("users.sqlite is not a regular file of root's")
	header = f.read(20)
if len(header) == 20 and header[18] == 2:
	conn = sqlite3.connect("/proc/self/fd/%d/users.sqlite" % dfd)
	mode = conn.execute("PRAGMA journal_mode=DELETE").fetchone()[0]
	conn.close()
	print("users.sqlite was in WAL mode, now:", mode)
PY

# ### User Authentication

# Have Dovecot query our database, and not system users, for authentication.
sed -i "s/#*\(\!include auth-system.conf.ext\)/#\1/"  /etc/dovecot/conf.d/10-auth.conf
sed -i "s/#\(\!include auth-sql.conf.ext\)/\1/"  /etc/dovecot/conf.d/10-auth.conf

# Specify how the database is to be queried for user authentication (passdb)
# and where user mailboxes are stored (userdb). The users.quota column
# (0, bytes, or e.g. 500M/10G) maps directly to Dovecot's quota_storage_size.
# On Dovecot 2.3 MIAB allowed deliveries to overshoot the quota by 10%; 2.4's
# quota_storage_grace only takes a size, so the userdb computes 10% of each
# user's quota (G and M are 2^30/2^20 bytes, divided by 10 and rounded down).
# Written atomically (tools/write_conf.py): a Dovecot config process that
# started while this file was truncated ran without a passdb (B120).
#
# Failed logins from the box itself (B126). Dovecot answers a failed login
# only after auth_failure_delay (2 s), and each one raises a penalty of the
# client's address that delays its next logins, failed or not, by up to
# 15 s. Every login from 127.0.0.1 or ::1 comes from a service of the box
# that checks a client's password with it: Z-Push (ActiveSync, Autodiscover;
# up to three tries per request), Roundcube and Nextcloud's IMAP login. So a
# wrong password took Z-Push 10 to 50 s, and a few failed logins of one
# client below the ban thresholds slowed the logins of all other users of
# these services down to 15 s. fail2ban protects these services with the
# real client's address (miab-zpush, miab-roundcube, miab-owncloud and
# Nextcloud's own throttle), but it ignores 127.0.0.1; and without any limit
# a process on the box that runs as one of these services (a hole in PHP or
# in Roundcube) could try the passwords of every account as fast as Dovecot
# checks them (about 1000 a second on a test machine).
#
# So two Lua passdbs around the SQL one (conf/dovecot-auth-guard/, installed
# in /usr/local/lib/mailinabox/dovecot-auth-guard/, root's, readable by the
# auth process: setup gives /etc/dovecot to the group mail, which the auth
# process, the account dovecot, is not in; their state is in
# /run/miab-auth-guard, tmpfs, 0700 dovecot):
#  * miab-auth-guard-count, the last one, is reached only when no passdb
#    before it accepted the login. For a login from the box it records the
#    failure for the account name and answers at once ("nodelay"), which
#    raises no penalty of 127.0.0.1 either. It records only a 16-bit tag of
#    a salted hash of the wrong password, and a password sent again counts
#    once: a phone that keeps sending an old password (Z-Push tries up to
#    three times per request) or a repeated typo counts once, guesses count
#    each. It returns no password, so it can accept none. Logins from other
#    addresses keep Dovecot's delay and penalty.
#  * miab-auth-guard-check, the first one (deny = yes), refuses an account
#    name with 30 different wrong passwords from the box within 30 minutes
#    (System > Intrusion Detection and Prevention sets both numbers; the Lua code reads
#    them from a small file on every login from the box) for logins from the
#    box, at once and before the password is checked, until it has fewer. Only the failures of the name itself count, so made-up names
#    cannot lower the limit of a real account, and the other accounts are
#    not slowed down. Logins from other addresses (the IMAP and SMTP logins
#    of the user's own mail programs) are not refused. The price: while
#    someone tries the passwords of one account through ActiveSync, webmail
#    or Nextcloud from addresses fail2ban does not ban, that account's own
#    phones, webmail and Nextcloud are refused too (README-fork.md, "Known
#    issues").
# "From the box" is every address of 127.0.0.0/8, ::1, every address of the
# box's interfaces (auth_guard.py writes them, again every 10 minutes) and
# any connection whose source is its destination (a process on the box can
# use any of them; fail2ban ignores them all). Only wrong passwords count, a
# login with the right password never. The accounts on the list (written
# by the management daemon whenever accounts change) are always counted;
# other names share a pool of 500, so made-up names cannot crowd out the
# count of an account. A burst of guesses at the same moment, which can get
# more than the limit checked in one window, counts against the next ones as
# well (the last k windows may hold k times the limit, k = 1 to 4).
# auth_username_chars is empty so that every failure
# reaches these passdbs (Dovecot's list of allowed characters refused names
# with "+" or a space before them, with its delay and the penalty of
# 127.0.0.1).
# If the state cannot be written, failed logins from the box get Dovecot's
# delay and penalty again (as before B126), never no limit.
# management/auth_guard.py (cron, every 10 minutes) mails new locks to the
# report recipient (System > Notifications) and removes the files of names
# without failures in the window.
tools/write_conf.py /etc/tmpfiles.d/miab-auth-guard.conf << EOF;
# Mail-in-a-Box: the state of Dovecot's limit of failed logins from the box
# itself (setup/mail-users.sh). Do not edit.
d /run/miab-auth-guard 0700 dovecot dovecot -
EOF
hide_output systemd-tmpfiles --create /etc/tmpfiles.d/miab-auth-guard.conf
install -d -o root -g root -m 0755 /usr/local/lib/mailinabox/dovecot-auth-guard
for f in guard check count; do
	tools/write_conf.py "/usr/local/lib/mailinabox/dovecot-auth-guard/$f.lua" < "conf/dovecot-auth-guard/$f.lua"
done

tools/write_conf.py /etc/dovecot/conf.d/auth-sql.conf.ext << EOF;
# Every user name reaches the passdbs (Dovecot's default list of allowed
# characters refuses e.g. "+" or a space before them, with its delay and the
# penalty of 127.0.0.1, B126); the SQL passdb escapes %{user}.
auth_username_chars =
sql_driver = sqlite
sqlite_path=$STORAGE_ROOT/mail/users.sqlite

passdb miab-auth-guard-check {
  driver = lua
  lua_file = /usr/local/lib/mailinabox/dovecot-auth-guard/check.lua
  use_worker = no
  deny = yes
}
passdb sql {
  query = SELECT email as user, password FROM users WHERE email='%{user}';
  default_password_scheme = SHA512-CRYPT
}
passdb miab-auth-guard-count {
  driver = lua
  lua_file = /usr/local/lib/mailinabox/dovecot-auth-guard/count.lua
  use_worker = no
}
userdb sql {
  query = SELECT email AS user, "mail" as uid, "mail" as gid, "$STORAGE_ROOT/mail/mailboxes/%{user | domain}/%{user | username}" as home, quota AS quota_storage_size, (CASE WHEN substr(quota, -1) = 'G' THEN CAST(substr(quota, 1, length(quota) - 1) AS INTEGER) * 107374182 WHEN substr(quota, -1) = 'M' THEN CAST(substr(quota, 1, length(quota) - 1) AS INTEGER) * 104857 ELSE CAST(quota AS INTEGER) / 10 END) || 'B' AS quota_storage_grace FROM users WHERE email='%{user}';
  iterate_query = SELECT email AS user FROM users;
}
EOF

# Have Dovecot provide an authorization service that Postfix can access & use.
tools/write_conf.py /etc/dovecot/conf.d/99-local-auth.conf << EOF;
service auth {
  unix_listener /var/spool/postfix/private/auth {
    mode = 0666
    user = postfix
    group = postfix
  }
}
EOF

# And have Postfix use that service. We *disable* it here
# so that authentication is not permitted on port 25 (which
# does not run DKIM on relayed mail, so outbound mail isn't
# correct, see #830), but we enable it specifically for the
# submission port.
tools/editconf.py /etc/postfix/main.cf \
	smtpd_sasl_type=dovecot \
	smtpd_sasl_path=private/auth \
	smtpd_sasl_auth_enable=no

# ### Sender Validation

# We use Postfix's reject_authenticated_sender_login_mismatch filter to
# prevent intra-domain spoofing by logged in but untrusted users in outbound
# email. In all outbound mail (the sender has authenticated), the MAIL FROM
# address (aka envelope or return path address) must be "owned" by the user
# who authenticated. An SQL query will find who are the owners of any given
# address.
tools/editconf.py /etc/postfix/main.cf \
	smtpd_sender_login_maps=sqlite:/etc/postfix/sender-login-maps.cf

# Postfix will query the exact address first, where the priority will be alias
# records first, then user records. If there are no matches for the exact
# address, then Postfix will query just the domain part, which we call
# catch-alls and domain aliases. A NULL permitted_senders column means to
# take the value from the destination column.
cat > /etc/postfix/sender-login-maps.cf << EOF;
dbpath=$db_path
query = SELECT permitted_senders FROM (SELECT permitted_senders, 0 AS priority FROM aliases WHERE source='%s' AND permitted_senders IS NOT NULL UNION SELECT destination AS permitted_senders, 1 AS priority FROM aliases WHERE source='%s' AND permitted_senders IS NULL UNION SELECT email as permitted_senders, 2 AS priority FROM users WHERE email='%s') ORDER BY priority LIMIT 1;
EOF

# ### Destination Validation

# Use a Sqlite3 database to check whether a destination email address exists,
# and to perform any email alias rewrites in Postfix. Additionally, we disable
# SMTPUTF8 because Dovecot's LMTP server that delivers mail to inboxes does
# not support it, and if a message is received with the SMTPUTF8 flag it will
# bounce.
tools/editconf.py /etc/postfix/main.cf \
	smtputf8_enable=no \
	virtual_mailbox_domains=sqlite:/etc/postfix/virtual-mailbox-domains.cf \
	virtual_mailbox_maps=sqlite:/etc/postfix/virtual-mailbox-maps.cf \
	virtual_alias_maps=sqlite:/etc/postfix/virtual-alias-maps.cf \
	local_recipient_maps=\$virtual_mailbox_maps

# SQL statement to check if we handle incoming mail for a domain, either for users or aliases.
cat > /etc/postfix/virtual-mailbox-domains.cf << EOF;
dbpath=$db_path
query = SELECT 1 FROM users WHERE email LIKE '%%@%s' UNION SELECT 1 FROM aliases WHERE source LIKE '%%@%s' UNION SELECT 1 FROM auto_aliases WHERE source LIKE '%%@%s'
EOF

# SQL statement to check if we handle incoming mail for a user.
cat > /etc/postfix/virtual-mailbox-maps.cf << EOF;
dbpath=$db_path
query = SELECT 1 FROM users WHERE email='%s'
EOF

# SQL statement to rewrite an email address if an alias is present.
#
# Postfix makes multiple queries for each incoming mail. It first
# queries the whole email address, then just the user part in certain
# locally-directed cases (but we don't use this), then just `@`+the
# domain part. The first query that returns something wins. See
# http://www.postfix.org/virtual.5.html.
#
# virtual-alias-maps has precedence over virtual-mailbox-maps, but
# we don't want catch-alls and domain aliases to catch mail for users
# that have been defined on those domains. To fix this, we not only
# query the aliases table but also the users table when resolving
# aliases, i.e. we turn users into aliases from themselves to
# themselves. That means users will match in postfix's first query
# before postfix gets to the third query for catch-alls/domain alises.
#
# If there is both an alias and a user for the same address either
# might be returned by the UNION, so the whole query is wrapped in
# another select that prioritizes the alias definition to preserve
# postfix's preference for aliases for whole email addresses.
#
# Since we might have alias records with an empty destination because
# it might have just permitted_senders, skip any records with an
# empty destination here so that other lower priority rules might match.
cat > /etc/postfix/virtual-alias-maps.cf << EOF;
dbpath=$db_path
query = SELECT destination from (SELECT destination, 0 as priority FROM aliases WHERE source='%s' AND destination<>'' UNION SELECT email as destination, 1 as priority FROM users WHERE email='%s' UNION SELECT destination, 2 as priority FROM auto_aliases WHERE source='%s' AND destination<>'') ORDER BY priority LIMIT 1;
EOF

# Load the new configuration
############################

# A reload instead of a restart, so that the listening sockets never close
# (B122), and for Dovecot nothing at all when its configuration did not
# change. Dovecot gets its whole configuration (setup/mail-dovecot.sh and the
# passdb and userdb above) at once, and before the doveadm commands below,
# which need the userdb (B120).

reload_postfix
load_dovecot

# force a recalculation of all user quotas
doveadm quota recalc -A

# Boxes that ran without mail_volatile_path (Dovecot 2.4, and 2.3.21 on Ubuntu
# 24.04) have the lock directory of the duplicate database in the Maildir of
# every user who got a vacation reply or a redirect, and Dovecot shows it as
# the folders "dovecot", "dovecot.lda-dupes" and "dovecot.lda-dupes.locks"
# (setup/mail-dovecot.sh, B66). This runs here and not in mail-dovecot.sh
# because doveadm needs the user database above: a box that comes from 24.04
# has none before this file. The parents are unsubscribed (unless a real
# folder has that name), then the lock directory is deleted through Dovecot
# (which also unsubscribes it and updates the folder list) with its full-text
# index. A directory that holds messages (moved there with a mail program) is
# kept. If Dovecot cannot handle a user, the directory is kept, so the next
# setup run tries again; only the directory of a user who no longer exists is
# removed directly.
n_dupes=0
while IFS= read -r -d '' dupes_dir; do
	dupes_home=$(dirname "$dupes_dir")
	dupes_user=$(basename "$dupes_home")@$(basename "$(dirname "$dupes_home")")
	if [ -n "$(find "$dupes_dir/cur" "$dupes_dir/new" -type f -print -quit 2> /dev/null)" ]; then
		echo "Kept $dupes_dir: it holds messages. Move them to another folder of $dupes_user and run setup again."
		continue
	fi
	if doveadm user "$dupes_user" > /dev/null 2>&1; then dupes_rc=0; else dupes_rc=$?; fi
	if [ "$dupes_rc" -eq 67 ]; then
		# EX_NOUSER: the mailbox directory of a deleted user.
		rm -rf "$dupes_dir"
		n_dupes=$((n_dupes + 1))
		continue
	elif [ "$dupes_rc" -ne 0 ]; then
		echo "Kept $dupes_dir: Dovecot could not look up $dupes_user (exit code $dupes_rc). Setup tries again on its next run."
		continue
	fi
	dupes_failed=
	for dupes_parent in dovecot dovecot.lda-dupes; do
		if [ ! -d "$dupes_home/.$dupes_parent" ]; then
			doveadm mailbox unsubscribe -u "$dupes_user" "$dupes_parent" > /dev/null 2>&1 || dupes_failed=1
		fi
	done
	dupes_guid=$(doveadm -f flow mailbox status -u "$dupes_user" guid dovecot.lda-dupes.locks 2> /dev/null | sed -n 's/.*guid=\([0-9a-f]\{32\}\)$/\1/p' || true)
	if [ -z "$dupes_failed" ] && doveadm mailbox delete -u "$dupes_user" -s dovecot.lda-dupes.locks > /dev/null 2>&1; then
		if [ -n "$dupes_guid" ]; then rm -rf "$dupes_home/xapian-indexes/db_$dupes_guid" "$dupes_home/xapian-indexes/db_${dupes_guid}"_*; fi
		n_dupes=$((n_dupes + 1))
	else
		echo "Kept $dupes_dir: Dovecot could not remove the folders of its duplicate database for $dupes_user. Setup tries again on its next run."
	fi
done < <(find "$STORAGE_ROOT/mail/mailboxes" -mindepth 3 -maxdepth 3 -type d -name .dovecot.lda-dupes.locks -print0 2> /dev/null)
if [ "$n_dupes" -gt 0 ]; then
	echo "Removed the folders of Dovecot's duplicate database from $n_dupes mailboxes."
fi
