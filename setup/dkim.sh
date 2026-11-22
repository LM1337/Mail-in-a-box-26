#!/bin/bash
# OpenDKIM
# --------
#
# OpenDKIM provides a service that puts a DKIM signature on outbound mail.
#
# The DNS configuration for DKIM is done in the management daemon.

source setup/functions.sh # load our functions
source /etc/mailinabox.conf # load global vars

# Install DKIM...
echo "Installing OpenDKIM/OpenDMARC..."
apt_install opendkim opendkim-tools opendmarc

# Make sure configuration directories exist.
mkdir -p /etc/opendkim;
mkdir -p "$STORAGE_ROOT/mail/dkim"

# Used in InternalHosts and ExternalIgnoreList configuration directives.
# Not quite sure why.
echo "127.0.0.1" > /etc/opendkim/TrustedHosts

# We need to at least create these files, since we reference them later.
# Otherwise, opendkim startup will fail
touch /etc/opendkim/KeyTable
touch /etc/opendkim/SigningTable

if grep -q "ExternalIgnoreList" /etc/opendkim.conf; then
	true # already done #NODOC
else
	# Add various configuration options to the end of `opendkim.conf`.
	cat >> /etc/opendkim.conf << EOF;
Canonicalization		relaxed/simple
MinimumKeyBits          1024
ExternalIgnoreList      refile:/etc/opendkim/TrustedHosts
InternalHosts           refile:/etc/opendkim/TrustedHosts
KeyTable                refile:/etc/opendkim/KeyTable
SigningTable            refile:/etc/opendkim/SigningTable
Socket                  inet:8891@127.0.0.1
RequireSafeKeys         false
EOF
fi

# Create a new DKIM key. This creates mail.private and mail.txt
# in $STORAGE_ROOT/mail/dkim. The former is the private key and
# the latter is the suggested DNS TXT entry which we'll include
# in our DNS setup. Note that the files are named after the
# 'selector' of the key, which we can change later on to support
# key rotation.
#
# A 1024-bit key is seen as a minimum standard by several providers
# such as Google. But they and others use a 2048 bit key, so we'll
# do the same. Keys beyond 2048 bits may exceed DNS record limits.
if [ ! -f "$STORAGE_ROOT/mail/dkim/mail.private" ]; then
	opendkim-genkey -b 2048 -r -s mail -D "$STORAGE_ROOT/mail/dkim"
fi

# Ensure files are owned by the opendkim user and are private otherwise.
# The mode through a descriptor, see setup/mail-postfix.sh (B147).
chown -R opendkim:opendkim "$STORAGE_ROOT/mail/dkim"
tools/write_conf.py --own "$STORAGE_ROOT/mail/dkim" opendkim opendkim 700

tools/editconf.py /etc/opendmarc.conf -s \
	"Syslog=true" \
	"Socket=inet:8893@[127.0.0.1]" \
	"FailureReports=false"

# SPFIgnoreResults causes the filter to ignore any SPF results in the header
# of the message. This is useful if you want the filter to perform SPF checks
# itself, or because you don't trust the arriving header. This added header is
# used by spamassassin to evaluate the mail for spamminess.

tools/editconf.py /etc/opendmarc.conf -s \
        "SPFIgnoreResults=true"

# SPFSelfValidate causes the filter to perform a fallback SPF check itself
# when it can find no SPF results in the message header. If SPFIgnoreResults
# is also set, it never looks for SPF results in headers and always performs
# the SPF check itself when this is set. This added header is used by
# spamassassin to evaluate the mail for spamminess.

tools/editconf.py /etc/opendmarc.conf -s \
        "SPFSelfValidate=true"

# Disables generation of failure reports for sending domains that publish a
# "none" policy.

tools/editconf.py /etc/opendmarc.conf -s \
        "FailureReportsOnNone=false"

# AlwaysAddARHeader Adds an "Authentication-Results:" header field even to
# unsigned messages from domains with no "signs all" policy. The reported DKIM
# result will be  "none" in such cases. Normally unsigned mail from non-strict
# domains does not cause the results header field to be added. This added header
# is used by spamassassin to evaluate the mail for spamminess.

tools/editconf.py /etc/opendkim.conf -s \
        "AlwaysAddARHeader=true"

# Add OpenDKIM and OpenDMARC as milters to postfix, which is how OpenDKIM
# intercepts outgoing mail to perform the signing (by adding a mail header)
# and how they both intercept incoming mail to add Authentication-Results
# headers. The order possibly/probably matters: OpenDMARC relies on the
# OpenDKIM Authentication-Results header already being present.
#
# Be careful. If we add other milters later, this needs to be concatenated
# on the smtpd_milters line.
#
# The OpenDMARC milter is skipped in the SMTP submission listener by
# configuring smtpd_milters there to only list the OpenDKIM milter
# (see mail-postfix.sh).
#
# The sending limit of the box (inet:127.0.0.1:8895, see mail-postfix.sh) comes
# last, and it fails closed: when it does not answer (stopped, crashed, hung),
# Postfix refuses the mail with a temporary error ("451 4.7.1"; default_action
# tempfail for this milter only) instead of letting it out without a limit.
# The sender sends it again; sendmail's mail waits in the maildrop queue until
# the milter is back (systemd restarts it within seconds). OpenDKIM and
# OpenDMARC keep milter_default_action=accept. On port 25 it is asked only for
# mail from the box itself (127.0.0.0/8, ::1, which mynetworks lets relay),
# through smtpd_milter_maps, so that mail from other servers never depends on
# it; through sendmail (non_smtpd_milters) for all mail; the submission ports
# list it in master.cf ($sendlimit_submission_milters of mail-postfix.sh).
#
# When the sending limit is turned off (System > Intrusion Detection and
# Prevention; "enabled 0" in the milter's settings file, which
# management/send_limit.py --apply writes and which then also sets these
# values when it is turned on or off in the control panel), Postfix does not
# ask the milter at all, so nothing depends on it. The same values are in
# send_limit.py (POSTFIX).
sendlimit_milter="{ inet:127.0.0.1:8895, default_action=tempfail }"
tools/write_conf.py /etc/postfix/sendlimit-milters.cidr << EOF;
# Mail-in-a-Box (setup/dkim.sh): the milters of mail from the box itself on port 25.
127.0.0.0/8	inet:127.0.0.1:8891 inet:127.0.0.1:8893 $sendlimit_milter
::ffff:127.0.0.0/104	inet:127.0.0.1:8891 inet:127.0.0.1:8893 $sendlimit_milter
::1/128	inet:127.0.0.1:8891 inet:127.0.0.1:8893 $sendlimit_milter
EOF
if grep -qx 'enabled 0' /usr/local/lib/mailinabox/miab-sendlimit/settings 2> /dev/null; then
	tools/editconf.py /etc/postfix/main.cf \
		"smtpd_milters=inet:127.0.0.1:8891 inet:127.0.0.1:8893" \
		smtpd_milter_maps= \
		"non_smtpd_milters=inet:127.0.0.1:8891 inet:127.0.0.1:8893" \
		milter_default_action=accept
else
	tools/editconf.py /etc/postfix/main.cf \
		"smtpd_milters=inet:127.0.0.1:8891 inet:127.0.0.1:8893" \
		smtpd_milter_maps=cidr:/etc/postfix/sendlimit-milters.cidr \
		"non_smtpd_milters=inet:127.0.0.1:8891 inet:127.0.0.1:8893 $sendlimit_milter" \
		milter_default_action=accept
fi

# We need to explicitly enable the opendmarc service, or it will not start
hide_output systemctl enable opendmarc

# Restart OpenDKIM and OpenDMARC only when their configuration (or package)
# changed: while OpenDKIM restarts, Postfix passes mail unsigned. The key and
# signing tables are not part of it: the management daemon restarts OpenDKIM
# when it writes them (management/dns_update.py). Postfix only reads the
# milter settings again (B122).
restart_on_change opendkim opendkim /etc/opendkim.conf /etc/default/opendkim \
	/etc/opendkim/TrustedHosts "stat:$STORAGE_ROOT/mail/dkim/mail.private" \
	tree:/etc/systemd/system/opendkim.service.d
restart_on_change opendmarc opendmarc /etc/opendmarc.conf /etc/default/opendmarc \
	tree:/etc/systemd/system/opendmarc.service.d
reload_postfix

