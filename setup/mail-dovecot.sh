#!/bin/bash
#
# Dovecot (IMAP/POP and LDA)
# ----------------------
#
# Dovecot is *both* the IMAP/POP server (the protocol that email applications
# use to query a mailbox) as well as the local delivery agent (LDA),
# meaning it is responsible for writing emails to mailbox storage on disk.
# You could imagine why these things would be bundled together.
#
# As part of local mail delivery, Dovecot executes actions on incoming
# mail as defined in a "sieve" script.
#
# Dovecot's LDA role comes after spam filtering. Postfix hands mail off
# to Spamassassin which in turn hands it off to Dovecot. This all happens
# using the LMTP protocol.

source setup/functions.sh # load our functions
source /etc/mailinabox.conf # load global vars


# Install packages for dovecot. These are all core dovecot plugins,
# but dovecot-lucene is packaged by *us* in the Mail-in-a-Box PPA,
# not by Ubuntu.

echo "Installing Dovecot (IMAP server)..."
apt_install \
	dovecot-core dovecot-imapd dovecot-pop3d dovecot-lmtpd dovecot-sqlite sqlite3 \
	dovecot-sieve dovecot-managesieved

# The `dovecot-imapd`, `dovecot-pop3d`, and `dovecot-lmtpd` packages automatically
# enable IMAP, POP and LMTP protocols.

# Set basic daemon options.

## The 'default_client_limit' is 1000, which is lower than required, if
# all of our services reach their maximum, currently:
# service imap-urlauth-login { process_limit=250 }
# service imap-login { process_limit=250 }
# service pop3-login { process_limit=250 }
# service lmtp { process_limit=250 }
# service managesieve-login { process_limit=250 }
# So we set it to our mimumum, 1250.
## The `default_process_limit` is 100, which constrains the total number
# of active IMAP connections (at, say, 5 open connections per user that
# would be 20 users). Set it to 250 times the number of cores this
# machine has, so on a two-core machine that's 500 processes/100 users).
## The `default_vsz_limit` is the maximum amount of virtual memory that
# can be allocated. It should be set *reasonably high* to avoid allocation
# issues with larger mailboxes. We're setting it to 1/3 of the total
# available memory (physical mem + swap) to be sure.
# See here for discussion:
# - https://www.dovecot.org/list/dovecot/2012-August/137569.html
# - https://www.dovecot.org/list/dovecot/2011-December/132455.html
tools/editconf.py /etc/dovecot/conf.d/10-master.conf \
    default_client_limit="$(($(nproc) * 1250))" \
	default_process_limit="$(($(nproc) * 250))" \
	default_vsz_limit="$(($(free -tm  | tail -1 | awk '{print $2}') / 3))M" \
	log_path=/var/log/mail.log

# The inotify `max_user_instances` default is 128, which constrains
# the total number of watched (IMAP IDLE push) folders by open connections.
# See http://www.dovecot.org/pipermail/dovecot/2013-March/088834.html.
# A reboot is required for this to take effect (which we don't do as
# as a part of setup). Test with `cat /proc/sys/fs/inotify/max_user_instances`.
# 26.04 no longer ships /etc/sysctl.conf, and /usr/lib/sysctl.d belongs to the
# distribution's packages: that file is not always there and gets replaced on
# upgrade. Drop our own file in /etc/sysctl.d instead, which is what it is for.
cat > /etc/sysctl.d/60-mailinabox.conf <<EOF
# Managed by Mail-in-a-Box.
fs.inotify.max_user_instances=1024
EOF

# Apply it now.
hide_output sysctl --system


# Copy in preconfigured dovecot configuration files
cp -f conf/dovecot-10-mail.conf /etc/dovecot/conf.d/10-mail.conf
cp -f conf/dovecot-mailboxes.conf /etc/dovecot/conf.d/15-mailboxes.conf
cp -f conf/dovecot-20-imap.conf /etc/dovecot/conf.d/20-imap.conf
cp -f conf/dovecot-20-pop3.conf /etc/dovecot/conf.d/20-pop3.conf
cp -f conf/dovecot-20-lmtp.conf /etc/dovecot/conf.d/20-lmtp.conf
cp -f conf/dovecot-90-quota.conf /etc/dovecot/conf.d/90-quota.conf
# The sieve config names paths under $STORAGE_ROOT, which a plain copy would
# leave as literal text. Only that one variable is substituted, Dovecot's own
# %{...} variables stay as they are.
sed "s|\$STORAGE_ROOT|$STORAGE_ROOT|g" conf/dovecot-99-local-sieve.conf > /etc/dovecot/conf.d/99-local-sieve.conf

# Set the location where we'll store user mailboxes. '%{user|domain}' is the domain name and '%{user|username}' is the
# username part of the user's email address. We'll ensure that no bad domains or email addresses
# are created within the management daemon.
tools/editconf.py /etc/dovecot/conf.d/10-mail.conf \
    mail_path="$STORAGE_ROOT/mail/mailboxes/%{user|domain}/%{user|username}"

# The user's home (userdb "home" in mail-users.sh) is that same directory, the
# root of the Maildir. Dovecot 2.4 puts the lock files of the duplicate
# database (vacation replies, redirects) into a directory .dovecot.lda-dupes.locks
# next to the database, and Maildir++ takes every directory whose name starts
# with a dot for a folder: users got the folders "dovecot", "dovecot.lda-dupes"
# and "dovecot.lda-dupes.locks". mail_volatile_path moves the lock files (and
# Dovecot's other short-lived lock files) out of the Maildir, to a tmpfs. The
# database itself (.dovecot.lda-dupes, a file) stays in the home, as on 22.04;
# maildir_stat_dirs keeps such files out of the folder list also on file
# systems that do not tell files from directories when listing (B66).
cat > /etc/tmpfiles.d/mailinabox-dovecot.conf << EOF;
# Managed by Mail-in-a-Box (setup/mail-dovecot.sh): Dovecot's mail_volatile_path.
d /run/dovecot-volatile 0700 mail mail -
EOF
hide_output systemd-tmpfiles --create /etc/tmpfiles.d/mailinabox-dovecot.conf
tools/editconf.py /etc/dovecot/conf.d/10-mail.conf \
    mail_volatile_path="/run/dovecot-volatile/%{user|domain}/%{user|username}" \
    maildir_stat_dirs=yes

# ### IMAP/POP

# Require that passwords are sent over SSL only, and allow the usual IMAP authentication mechanisms.
# The LOGIN mechanism is supposedly for Microsoft products like Outlook to do SMTP login (I guess
# since we're using Dovecot to handle SMTP authentication?).
tools/editconf.py /etc/dovecot/conf.d/10-auth.conf \
	auth_allow_cleartext=no \
	"auth_mechanisms=plain login"
# A box upgraded in place from Dovecot 2.3 can still have the old names of these
# settings in the kept configuration files, and Dovecot 2.4 refuses to start
# with them. Comment them out (In-Place 1).
tools/editconf.py /etc/dovecot/conf.d/10-auth.conf -e disable_plaintext_auth=
tools/editconf.py /etc/dovecot/conf.d/10-ssl.conf -e \
	"ssl_cert=" "ssl_key=" "ssl_dh=" "ssl_dh_parameters_length=" "ssl_prefer_server_ciphers=" \
	"ssl_protocols=" "ssl_ca="

# Enable SSL, specify the location of the SSL certificate and private key files.
# Use Mozilla's "Intermediate" recommendations at https://ssl-config.mozilla.org/#server=dovecot&server-version=2.2.33&config=intermediate&openssl-version=1.1.1,
# except that the current version of Dovecot does not have a TLSv1.3 setting, so we only use TLSv1.2.
tools/editconf.py /etc/dovecot/conf.d/10-ssl.conf \
	"ssl = required" \
	"ssl_server_cert_file = $STORAGE_ROOT/ssl/ssl_certificate.pem" \
	"ssl_server_key_file = $STORAGE_ROOT/ssl/ssl_private_key.pem" \
	"ssl_cipher_list = ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384" \
	"ssl_server_prefer_ciphers = client" \
	"ssl_server_dh_file = $STORAGE_ROOT/ssl/dh2048.pem"

# Disable in-the-clear IMAP/POP because there is no reason for a user to transmit
# login credentials outside of an encrypted connection. Only the over-TLS versions
# are made available (IMAPS on port 993; POP3S on port 995).
sed -i "s/#port = 143/port = 0/" /etc/dovecot/conf.d/10-master.conf
sed -i "s/#port = 110/port = 0/" /etc/dovecot/conf.d/10-master.conf

# ### LDA (LMTP)

# Enable Dovecot's LDA service with the LMTP protocol. It will listen
# on port 10026, and Spamassassin will be configured to pass mail there.
#
# The disabled unix socket listener is normally how Postfix and Dovecot
# would communicate (see the Postfix setup script for the corresponding
# setting also commented out).
#
cat > /etc/dovecot/conf.d/99-local.conf << EOF;
service lmtp {
  inet_listener lmtp {
    listen = 127.0.0.1
    port = 10026
  }
}

# Enable imap-login on localhost to allow the user_external plugin
# for Nextcloud to do imap authentication. (See #1577)
service imap-login {
  inet_listener imap {
    listen = 127.0.0.1
    port = 143
  }
}

# The 26.04 package's 20-managesieve.conf also opens the deprecated ManageSieve
# port 2000 on all interfaces. Mail-in-a-Box only uses (and monitors) 4190.
service managesieve-login {
  inet_listener sieve_deprecated {
    port = 0
  }
}

# Keep the LMTP settings Mail-in-a-Box depends on out of reach of the package's
# ucf-managed 20-lmtp.conf: its version strips the domain from the user name
# (every delivery would fail with "User doesn't exist") and has no sieve plugin.
protocol lmtp {
  auth_username_format = %{user | lower}
  mail_plugins {
    sieve = yes
  }
}
EOF

# Setting a `postmaster_address` is required or LMTP won't start. An alias
# will be created automatically by our management daemon.
tools/editconf.py /etc/dovecot/conf.d/15-lda.conf \
	"postmaster_address=postmaster@$PRIMARY_HOSTNAME"

# ### Full-text search

# Index message bodies and attachments with the fts_xapian plugin, so that
# IMAP SEARCH (Roundcube, phones, desktop clients) does not have to read every
# message of a large mailbox. The indexes live in each user's home, which is
# the mailbox directory (userdb "home" in mail-users.sh), in xapian-indexes/.
# Set FTS=off in /etc/mailinabox.conf to turn it off.
# Boxes that added fts_xapian by hand for Dovecot 2.3 have it in these files,
# whose 2.3 syntax Dovecot 2.4 refuses. Our own file below replaces them.
rm -f /etc/dovecot/conf.d/05-local-fts-plugins.conf /etc/dovecot/conf.d/99-local-fts.conf
if [ "${FTS:-xapian}" != "off" ]; then
	apt_install dovecot-fts-xapian
	cat > /etc/dovecot/conf.d/95-mailinabox-fts.conf << EOF;
# Managed by Mail-in-a-Box (setup/mail-dovecot.sh). FTS=off in
# /etc/mailinabox.conf turns full-text search off.
mail_plugins {
  fts = yes
  fts_xapian = yes
}

# Index new mail on delivery and on save, not only on the first search.
fts_autoindex = yes
mailbox Trash {
  fts_autoindex = no
}

# Dovecot 2.4 requires a language even though fts_xapian does not use it.
language en {
  default = yes
}

fts xapian {
  # Shortest search term that still matches inside words.
  partial = 3
  verbose = 0
}

# Indexing a large mailbox for the first time needs more than the default.
service indexer-worker {
  vsz_limit = 2G
}
EOF
	# The plugin's README recommends this once a day to compact the indexes.
	cat > /etc/cron.d/mailinabox-fts << EOF;
# Managed by Mail-in-a-Box (setup/mail-dovecot.sh).
30 3 * * * root nice -n 19 ionice -c 3 /usr/bin/doveadm fts optimize -A >/dev/null 2>&1
EOF
else
	rm -f /etc/dovecot/conf.d/95-mailinabox-fts.conf /etc/cron.d/mailinabox-fts
fi

# Copy the global sieve script into where we've told Dovecot to look for it. Then
# compile it. Global scripts must be compiled now because Dovecot won't have
# permission later.
cp conf/sieve-spam.txt /etc/dovecot/sieve-spam.sieve
sievec /etc/dovecot/sieve-spam.sieve

# PERMISSIONS

# Ensure configuration files are owned by dovecot and not world readable.
chown -R mail:dovecot /etc/dovecot
chmod -R o-rwx /etc/dovecot

# Ensure mailbox files have a directory that exists and are owned by the mail user.
mkdir -p "$STORAGE_ROOT/mail/mailboxes"
chown -R mail:mail "$STORAGE_ROOT/mail/mailboxes"

# Same for the sieve scripts.
mkdir -p "$STORAGE_ROOT/mail/sieve"
mkdir -p "$STORAGE_ROOT/mail/sieve/global_before"
mkdir -p "$STORAGE_ROOT/mail/sieve/global_after"
chown -R mail:mail "$STORAGE_ROOT/mail/sieve"

# Allow the IMAP/POP ports in the firewall.
ufw_allow imaps
ufw_allow pop3s

# Allow the Sieve port in the firewall.
ufw_allow sieve

# Restart services.
restart_service dovecot

# Boxes that ran without mail_volatile_path have the lock directory of the
# duplicate database in the Maildir of every user who got a vacation reply or
# a redirect, and Dovecot shows it as the folders "dovecot",
# "dovecot.lda-dupes" and "dovecot.lda-dupes.locks" (above, B66). Delete it
# through Dovecot (which also unsubscribes it and updates the folder list) and
# its full-text index; the lock files are not needed any more. A directory
# that holds messages (moved there with a mail program) is kept.
n_dupes=0
while IFS= read -r -d '' dupes_dir; do
	dupes_home=$(dirname "$dupes_dir")
	dupes_user=$(basename "$dupes_home")@$(basename "$(dirname "$dupes_home")")
	if [ -n "$(find "$dupes_dir/cur" "$dupes_dir/new" -type f -print -quit 2> /dev/null)" ]; then
		echo "Kept $dupes_dir: it holds messages. Move them to another folder of $dupes_user and run setup again."
		continue
	fi
	dupes_guid=$(doveadm -f flow mailbox status -u "$dupes_user" guid dovecot.lda-dupes.locks 2> /dev/null | sed -n 's/.*guid=\([0-9a-f]\{32\}\)$/\1/p' || true)
	doveadm mailbox delete -u "$dupes_user" -s dovecot.lda-dupes.locks > /dev/null 2>&1 || rm -rf "$dupes_dir"
	doveadm mailbox unsubscribe -u "$dupes_user" dovecot.lda-dupes dovecot > /dev/null 2>&1 || true
	if [ -n "$dupes_guid" ]; then rm -rf "$dupes_home/xapian-indexes/db_$dupes_guid" "$dupes_home/xapian-indexes/db_${dupes_guid}"_*; fi
	n_dupes=$((n_dupes + 1))
done < <(find "$STORAGE_ROOT/mail/mailboxes" -mindepth 3 -maxdepth 3 -type d -name .dovecot.lda-dupes.locks -print0 2> /dev/null)
if [ "$n_dupes" -gt 0 ]; then
	echo "Removed the folders of Dovecot's duplicate database from $n_dupes mailboxes."
fi
