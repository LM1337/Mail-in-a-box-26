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
# This script does no file operation in /var/log itself: that directory is
# writable by the group syslog, so rsyslog's user could put a symlink in place
# of mail.log at any time, and a create, chown or chmod by root would follow
# it. rsyslog creates the new mail.log (with its own owner and mode) at its
# next line, so one line is logged first. Only when mail.log is then a regular
# file of rsyslog's user, not a symlink and with one link, is Dovecot told to
# reopen; it appends to that file. Otherwise Dovecot would create the file as
# root with mode 0600, and rsyslog could no longer write to it; the script then
# logs a warning and fails, which shows in "systemctl --failed".
# (Dovecot itself opens log_path as root at every start and reopen, following a
# symlink: upstream behaviour since fac8477, which this script does not change.)

set -u
f=/var/log/mail.log

# The user that rsyslog gives the files it creates ($FileOwner in /etc/rsyslog.conf).
owner=$(sed -n 's/^\$FileOwner[[:space:]]\+\([^[:space:]]\+\).*/\1/p' /etc/rsyslog.conf 2> /dev/null | tail -n 1)
owner=${owner:-syslog}

# The first event comes when logrotate renames the old mail.log.1 to mail.log.2,
# before it renames mail.log. Let the rotation (renames, then the HUP of rsyslog) finish.
sleep 3

logger -p mail.info -t mailinabox "mail.log rotated, reopening Dovecot's log file"
for _ in $(seq 20); do
	[ -e "$f" ] && break
	sleep 0.5
done

if [ ! -f "$f" ] || [ -L "$f" ] || [ "$(stat -c %U:%h "$f" 2> /dev/null)" != "$owner:1" ]; then
	logger -p mail.warning -t mailinabox "Dovecot's log file not reopened: $f is not a regular file of $owner with one link ($(stat -c '%F %U:%G %h' "$f" 2> /dev/null || echo missing)). Dovecot still writes the rotated file until it restarts."
	exit 1
fi

# Nothing to reopen when Dovecot is not running; it opens the file when it starts.
if systemctl is-active --quiet dovecot.service; then
	doveadm log reopen
fi
