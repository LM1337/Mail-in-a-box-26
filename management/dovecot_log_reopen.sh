#!/bin/bash
# Points Dovecot at the new /var/log/mail.log after a rotation (B85).
#
# setup/mail-dovecot.sh installs this file as /usr/local/lib/mailinabox/dovecot-log-reopen.
# mailinabox-dovecot-log-reopen.path starts it (through the .service of the same name)
# when /var/log/mail.log.1 changes, i.e. when logrotate renames mail.log, whether in
# the weekly run of logrotate.timer or in a run by hand.
#
# Dovecot writes /var/log/mail.log itself (log_path) and keeps the file open.
# logrotate's rsyslog entry only tells rsyslog to reopen it, so without this
# Dovecot goes on writing into mail.log.1 until it is restarted, and the
# fail2ban jails dovecot and miab-slow-dovecot, which read mail.log, see none
# of its failed logins.
#
# rsyslog (user syslog) creates the new mail.log only at its next line. If
# Dovecot reopened first, it would create the file as root with mode 0600, and
# rsyslog could no longer write to it. So the new file gets the owner, group and
# mode that rsyslog gives the files it creates ($FileOwner, $FileGroup and
# $FileCreateMode in /etc/rsyslog.conf), before the reopen and once more after it.

set -u
f=/var/log/mail.log

rsyslog_setting() { # NAME DEFAULT
	local v
	v=$(sed -n "s/^\\\$$1[[:space:]]\\+\\([^[:space:]]\\+\\).*/\\1/p" /etc/rsyslog.conf 2> /dev/null | tail -n 1)
	echo "${v:-$2}"
}
owner=$(rsyslog_setting FileOwner syslog)
group=$(rsyslog_setting FileGroup adm)
mode=$(rsyslog_setting FileCreateMode 0640)

# The first event comes when logrotate renames the old mail.log.1 to mail.log.2,
# before it renames mail.log. Let the rotation (renames, then the HUP of rsyslog) finish.
sleep 3

fix_owner() {
	if [ ! -e "$f" ]; then
		(umask 077 && : >> "$f") || return 0
	fi
	if [ "$(stat -c %U:%G "$f")" != "$owner:$group" ]; then chown "$owner:$group" "$f" || true; fi
	if [ "$(stat -c %a "$f")" != "$(printf %o "$((8#$mode))")" ]; then chmod "$mode" "$f" || true; fi
}

fix_owner
# Nothing to reopen when Dovecot is not running; it opens the file when it starts.
if systemctl is-active --quiet dovecot.service; then
	doveadm log reopen
fi
fix_owner
exit 0
