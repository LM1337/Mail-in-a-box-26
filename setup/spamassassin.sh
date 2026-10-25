#!/bin/bash
# Spam filtering with spamassassin via spampd
# -------------------------------------------
#
# spampd sits between postfix and dovecot. It takes mail from postfix
# over the LMTP protocol, runs spamassassin on it, and then passes the
# message over LMTP to dovecot for local delivery.
#
# In order to move spam automatically into the Spam folder we use the dovecot sieve
# plugin.

source /etc/mailinabox.conf # get global vars
source setup/functions.sh # load our functions

# Install packages and basic configuration
# ----------------------------------------

# Install packages.
# libmail-dkim-perl is needed to make the spamassassin DKIM module work.
# For more information see Debian Bug #689414:
# https://bugs.debian.org/cgi-bin/bugreport.cgi?bug=689414
echo "Installing SpamAssassin..."
apt_install spampd razor pyzor libmail-dkim-perl

# Allow spamassassin to download new rules. Since SpamAssassin 4.0 (Ubuntu 26.04)
# /etc/cron.daily/spamassassin does nothing by default and CRON=1 is no longer
# read from /etc/default/spamd. The daily sa-update/sa-compile run from
# spamassassin-maintenance.timer instead, which a fresh install leaves disabled.
# After an update, spamassassin-maint runs /etc/spamassassin/sa-update-hooks.d/spampd,
# which restarts spampd so that it loads the new rules.
# A first update is started at the end of this script, once the SpamAssassin
# configuration below has been written.
hide_output systemctl enable --now spamassassin-maintenance.timer

# spampd runs SpamAssassin in-process, so the spamd daemon is not used. On Ubuntu 26.04
# it is a separate package (spamassassin Recommends spamc, which Recommends spamd) and
# is enabled by default. Stop it to save its memory and its localhost:783 listener.
if systemctl cat spamd.service &> /dev/null; then
	hide_output systemctl disable --now spamd.service
fi

# Configure pyzor, which is a client to a live database of hashes of
# spam emails. Set the pyzor configuration directory to something sane.
# The default is ~/.pyzor. We used to use that, so we'll kill that old
# directory. Then write the public pyzor server to its servers file.
# That will prevent an automatic download on first use, and also means
# we can skip 'pyzor discover', both of which are currently broken by
# something happening on Sourceforge (#496).
rm -rf ~/.pyzor
tools/editconf.py /etc/spamassassin/local.cf -s \
	pyzor_options="--homedir /etc/spamassassin/pyzor"
mkdir -p /etc/spamassassin/pyzor
echo "public.pyzor.org:24441" > /etc/spamassassin/pyzor/servers
# check with: pyzor --homedir /etc/mail/spamassassin/pyzor ping

# Configure spampd:
# * Pass messages on to docevot on port 10026. This is actually the default setting but we don't
#   want to lose track of it. (We've configured Dovecot to listen on this port elsewhere.)
# * Increase the maximum message size of scanned messages from the default of 64KB to 2000KB.
#   Specified in KBytes.
# * Disable localmode so Pyzor, DKIM and DNS checks can be used.
#
# /etc/spampd.cfg holds "name value" lines. spampd 2.62 treats a value of 0 as "no value"
# (`$v = $2 || ""`), so "local-only 0" or "local-only=0" turn local-only mode ON. Comment
# out every local-only line and use the negated option instead. Also drop the "name=value"
# lines that earlier versions of this script appended.
#
# The shipped file has no maxsize line, and anything after an uncommented "--" line is
# passed to Net::Server instead of spampd. So our own lines are (re)inserted before the
# "# End inserts from ADDOPTS" marker, or at the top of the file if the marker is gone.
sed -i -E '/^(maxsize=2000|local-only=0)$/d' /etc/spampd.cfg
sed -i -E 's/^[[:space:]]*-{0,2}(local-only|l)([[:space:]=].*)?$/#&/' /etc/spampd.cfg
sed -i -E '/^[[:space:]]*-{0,2}(no-local-only|maxsize)([[:space:]=].*)?$/d' /etc/spampd.cfg
if grep -q '^# End inserts from ADDOPTS' /etc/spampd.cfg; then
	sed -i '/^# End inserts from ADDOPTS/i maxsize 2000\nno-local-only' /etc/spampd.cfg
else
	sed -i '1i maxsize 2000\nno-local-only' /etc/spampd.cfg
fi
tools/editconf.py /etc/spampd.cfg -s \
	relayport=10026 \
	pid=/run/spampd/spampd.pid

# spampd writes its PID file as root and removes it when it stops, but by then
# it runs as user spampd and cannot delete files in /run ("Couldn't unlink
# /run/spampd.pid [Permission denied]"), so a stale PID file stayed behind
# (B81). Keep the PID file in a directory that belongs to spampd, and remove
# a stale one before each start. (RuntimeDirectory= cannot be used: systemd
# gives that directory to the unit's user, root, at the start of spampd.)
SPAMPD_DROPIN=/etc/systemd/system/spampd.service.d/mailinabox-pidfile.conf
SPAMPD_DROPIN_TEXT="[Service]
ExecStartPre=/usr/bin/install -d -o spampd -g spampd -m 0755 /run/spampd
ExecStartPre=/usr/bin/rm -f /run/spampd/spampd.pid
PIDFile=/run/spampd/spampd.pid"
if [ "$(cat "$SPAMPD_DROPIN" 2> /dev/null)" != "$SPAMPD_DROPIN_TEXT" ]; then
	mkdir -p "$(dirname "$SPAMPD_DROPIN")"
	echo "$SPAMPD_DROPIN_TEXT" > "$SPAMPD_DROPIN"
	systemctl daemon-reload
fi
# A spampd started with the old location stops quietly at the restart below
# when its PID file is gone (it only removes a file that exists).
rm -f /run/spampd.pid

# Spamassassin normally wraps spam as an attachment inside a fresh
# email with a report about the message. This also protects the user
# from accidentally opening a message with embedded malware.
#
# It's nice to see what rules caused the message to be marked as spam,
# but it's also annoying to get to the original message when it is an
# attachment, modern mail clients are safer now and don't load remote
# content or execute scripts, and it is probably confusing to most users.
#
# Tell Spamassassin not to modify the original message except for adding
# the X-Spam-Status & X-Spam-Score mail headers and related headers.
tools/editconf.py /etc/spamassassin/local.cf -s \
	report_safe=0 \
	"add_header all Report"=_REPORT_ \
	"add_header all Score"=_SCORE_

# Authentication-Results SPF/Dmarc checks
# ---------------------------------------
# OpenDKIM and OpenDMARC are configured to validate and add "Authentication-Results: ..."
# headers by checking the sender's SPF & DMARC policies. Instead of blocking mail that fails
# these checks, we can use these headers to evaluate the mail as spam.
#
# Our custom rules are added to their own file so that an update to the deb package config
# does not remove our changes.
#
# We need to escape period's in $PRIMARY_HOSTNAME since spamassassin config uses regex.

escapedprimaryhostname="${PRIMARY_HOSTNAME//./\\.}"

cat > /etc/spamassassin/miab_spf_dmarc.cf << EOF
# Evaluate DMARC Authentication-Results
header DMARC_PASS Authentication-Results =~ /$escapedprimaryhostname; dmarc=pass/
describe DMARC_PASS DMARC check passed
score DMARC_PASS -0.1

header DMARC_NONE Authentication-Results =~ /$escapedprimaryhostname; dmarc=none/
describe DMARC_NONE DMARC record not found
score DMARC_NONE 0.1

header DMARC_FAIL_NONE Authentication-Results =~ /$escapedprimaryhostname; dmarc=fail \(p=none/
describe DMARC_FAIL_NONE DMARC check failed (p=none)
score DMARC_FAIL_NONE 2.0

header DMARC_FAIL_QUARANTINE Authentication-Results =~ /$escapedprimaryhostname; dmarc=fail \(p=quarantine/
describe DMARC_FAIL_QUARANTINE DMARC check failed (p=quarantine)
score DMARC_FAIL_QUARANTINE 5.0

header DMARC_FAIL_REJECT Authentication-Results =~ /$escapedprimaryhostname; dmarc=fail \(p=reject/
describe DMARC_FAIL_REJECT DMARC check failed (p=reject)
score DMARC_FAIL_REJECT 10.0

# Evaluate SPF Authentication-Results
header SPF_PASS Authentication-Results =~ /$escapedprimaryhostname; spf=pass/
describe SPF_PASS SPF check passed
score SPF_PASS -0.1

header SPF_NONE Authentication-Results =~ /$escapedprimaryhostname; spf=none/
describe SPF_NONE SPF record not found
score SPF_NONE 2.0

header SPF_FAIL Authentication-Results =~ /$escapedprimaryhostname; spf=fail/
describe SPF_FAIL SPF check failed
score SPF_FAIL 5.0
EOF

# Bayesean learning
# -----------------
#
# Spamassassin can learn from mail marked as spam or ham, but it needs to be
# configured. We'll store the learning data in our storage area.
#
# These files must be:
# * The imap-sieve Dovecot Plugin, when users move messages in or out of the Spam folder. (TBD)
# * Readable by the spampd process ('spampd' user) during mail filtering.
# * Writable by the Dovecot sa-learn wrappers (via the spampd group).
#
# We'll have these files owned by spampd and grant group access to Dovecot.
#
# Spamassassin will change the access rights back to the defaults, so we must also configure
# the filemode in the config file.

tools/editconf.py /etc/spamassassin/local.cf -s \
	bayes_path="$STORAGE_ROOT/mail/spamassassin/bayes" \
	bayes_file_mode=0666

mkdir -p "$STORAGE_ROOT/mail/spamassassin"
chown -R spampd:spampd "$STORAGE_ROOT/mail/spamassassin"

# Mail-in-a-Box before the Dovecot 2.4 port trained SpamAssassin with the
# dovecot-antispam plugin. It does not exist for Dovecot 2.4, and its settings
# would stop Dovecot from starting on a box upgraded in place (In-Place 2).
rm -f /etc/dovecot/conf.d/99-local-spampd.conf /usr/local/bin/sa-learn-pipe.sh
if dpkg-query -W -f='${db:Status-Abbrev}' dovecot-antispam 2>/dev/null | grep -q '^[ih]i'; then
	apt_get_quiet purge dovecot-antispam
fi

# Install the IMAPSieve sieve scripts and sa-learn shell wrappers
# original author: yeah
#
mkdir -p /usr/lib/dovecot/sieve
cp -f conf/sieve-report-spam.sieve /usr/lib/dovecot/sieve/report-spam.sieve
cp -f conf/sieve-report-ham.sieve /usr/lib/dovecot/sieve/report-ham.sieve
sievec /usr/lib/dovecot/sieve/report-spam.sieve
sievec /usr/lib/dovecot/sieve/report-ham.sieve

cp -f conf/sa-learn-spam.sh /usr/lib/dovecot/sieve/sa-learn-spam.sh
cp -f conf/sa-learn-ham.sh /usr/lib/dovecot/sieve/sa-learn-ham.sh
chmod +x /usr/lib/dovecot/sieve/sa-learn-spam.sh
chmod +x /usr/lib/dovecot/sieve/sa-learn-ham.sh

# Have Dovecot run its mail process with a supplementary group (the spampd group)
# so that it can access the learning files.

tools/editconf.py /etc/dovecot/conf.d/10-mail.conf \
	mail_access_groups=spampd

# Create empty bayes training data (if it doesn't exist). Once the files exist,
# ensure they are group-writable so that the Dovecot process has access.
sudo -u spampd /usr/bin/sa-learn --sync 2>/dev/null
chmod -R 660 "$STORAGE_ROOT/mail/spamassassin"
chmod 770 "$STORAGE_ROOT/mail/spamassassin"

# Kick services.
restart_service spampd
restart_service dovecot

# Fetch current rules once now instead of waiting for the first 06:00 timer run
# (Persistent=true does not catch up when the timer has never run). This runs
# after the configuration above is final, so that its lint check sees it. Don't
# block setup on the network for it.
systemctl start --no-block spamassassin-maintenance.service || true
