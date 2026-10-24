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

# Create an empty database if it doesn't yet exist.
if [ ! -f "$db_path" ]; then
	echo "Creating new user database: $db_path";
	echo "CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL UNIQUE, password TEXT NOT NULL, extra, privileges TEXT NOT NULL DEFAULT '', quota TEXT NOT NULL DEFAULT '0');" | sqlite3 "$db_path";
	echo "CREATE TABLE aliases (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL UNIQUE, destination TEXT NOT NULL, permitted_senders TEXT);" | sqlite3 "$db_path";
	echo "CREATE TABLE mfa (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, type TEXT NOT NULL, secret TEXT NOT NULL, mru_token TEXT, label TEXT, FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE);" | sqlite3 "$db_path";
	echo "CREATE TABLE auto_aliases (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL UNIQUE, destination TEXT NOT NULL, permitted_senders TEXT);" | sqlite3 "$db_path";
fi

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
cat > /etc/dovecot/conf.d/auth-sql.conf.ext << EOF;
sql_driver = sqlite
sqlite_path=$STORAGE_ROOT/mail/users.sqlite

passdb sql {
  query = SELECT email as user, password FROM users WHERE email='%{user}';
  default_password_scheme = SHA512-CRYPT
}
userdb sql {
  query = SELECT email AS user, "mail" as uid, "mail" as gid, "$STORAGE_ROOT/mail/mailboxes/%{user | domain}/%{user | username}" as home, quota AS quota_storage_size, (CASE WHEN substr(quota, -1) = 'G' THEN CAST(substr(quota, 1, length(quota) - 1) AS INTEGER) * 107374182 WHEN substr(quota, -1) = 'M' THEN CAST(substr(quota, 1, length(quota) - 1) AS INTEGER) * 104857 ELSE CAST(quota AS INTEGER) / 10 END) || 'B' AS quota_storage_grace FROM users WHERE email='%{user}';
  iterate_query = SELECT email AS user FROM users;
}
EOF

# Have Dovecot provide an authorization service that Postfix can access & use.
cat > /etc/dovecot/conf.d/99-local-auth.conf << EOF;
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

# Restart Services
##################

restart_service postfix
restart_service dovecot

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
