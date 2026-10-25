#!/bin/bash
# Mails Munin's alerts to the box's administrator.
#
# setup/munin.sh installs this file as /usr/local/lib/mailinabox/munin-notify
# and names it as the command of the contact "admin" in /etc/munin/munin.conf.
# munin-limits (user munin, after each munin-update run) starts it when a
# value changed its state (ok, warning, critical, unknown) and pipes the text
# of all changes of that run into it. This script sends that text as one mail
# with /usr/sbin/sendmail (Postfix); an empty input sends nothing.

set -u

host=$(sed -n 's/^PRIMARY_HOSTNAME=//p' /etc/mailinabox.conf 2> /dev/null | tail -n 1)
[ -n "$host" ] || host=$(hostname -f 2> /dev/null || hostname)

# The recipient of the alerts. It is set here only, so that a later setting
# can change it in one place.
to="administrator@$host"

body=$(cat)
if [ -z "${body//[[:space:]]/}" ]; then exit 0; fi

{
	printf 'From: "Munin on %s" <%s>\n' "$host" "$to"
	printf 'To: <%s>\n' "$to"
	printf 'Subject: Munin notification %s\n' "$host"
	printf 'Date: %s\n' "$(LC_ALL=C date -R)"
	printf 'Message-ID: <munin.%s.%s@%s>\n' "$(date +%Y%m%d%H%M%S)" "$$" "$host"
	printf 'Auto-Submitted: auto-generated\n'
	printf 'MIME-Version: 1.0\n'
	printf 'Content-Type: text/plain; charset=UTF-8\n'
	printf 'Content-Transfer-Encoding: 8bit\n'
	printf '\n%s\n' "$body"
} | /usr/sbin/sendmail -i -f "$to" -- "$to"
