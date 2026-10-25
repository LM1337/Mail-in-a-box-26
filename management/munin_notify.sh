#!/bin/bash
# Mails Munin's alerts to the box's administrator.
#
# setup/munin.sh installs this file as /usr/local/lib/mailinabox/munin-notify
# and management/munin_admin.py names it as the command of the contact "admin"
# in /etc/munin/munin.conf. munin-limits (user munin, after each munin-update
# run) starts it when a value changed its state (ok, warning, critical,
# unknown) and pipes the text of all changes of that run into it. This script
# sends that text as one mail with /usr/sbin/sendmail (Postfix); an empty
# input sends nothing.
#
# Options (set by the admin panel's setting, see management/munin_admin.py):
#   --to ADDRESS   the recipient instead of administrator@PRIMARY_HOSTNAME
#   --test         a test notification of the admin panel: subject
#                  "Munin test notification" and the header X-Miab-Test: 1

set -u
# Byte-wise ranges in the address check below.
export LC_ALL=C

host=$(sed -n 's/^PRIMARY_HOSTNAME=//p' /etc/mailinabox.conf 2> /dev/null | tail -n 1)
[ -n "$host" ] || host=$(hostname -f 2> /dev/null || hostname)

# The sender, and the recipient unless --to is given.
from="administrator@$host"
to=$from
test=
while [ $# -gt 0 ]; do
	case "$1" in
		--to)
			if [ $# -lt 2 ]; then echo "munin-notify: --to needs an address" >&2; exit 2; fi
			to=$2; shift 2 ;;
		--test)
			test=1; shift ;;
		*)
			echo "munin-notify: unknown argument" >&2; exit 2 ;;
	esac
done

# The same narrow form of an address as ADDRESS_RE in munin_admin.py: nothing
# that could end a header line or start an option.
re='^[A-Za-z0-9_][A-Za-z0-9_+-]*(\.[A-Za-z0-9_+-]+)*@([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])$'
if [ ${#to} -gt 254 ] || ! [[ $to =~ $re ]]; then
	echo "munin-notify: not a valid recipient address" >&2
	exit 2
fi

# Squeeze the blank lines that the text of services without a value to report
# leaves (level "critical only"), and drop leading ones.
body=$(cat -s | sed '/./,$!d')
if [ -z "${body//[[:space:]]/}" ]; then exit 0; fi

subject="Munin notification $host"
[ -z "$test" ] || subject="Munin test notification $host"

{
	printf 'From: "Munin on %s" <%s>\n' "$host" "$from"
	printf 'To: <%s>\n' "$to"
	printf 'Subject: %s\n' "$subject"
	printf 'Date: %s\n' "$(LC_ALL=C date -R)"
	printf 'Message-ID: <munin.%s.%s@%s>\n' "$(date +%Y%m%d%H%M%S)" "$$" "$host"
	printf 'Auto-Submitted: auto-generated\n'
	[ -z "$test" ] || printf 'X-Miab-Test: 1\n'
	printf 'MIME-Version: 1.0\n'
	printf 'Content-Type: text/plain; charset=UTF-8\n'
	printf 'Content-Transfer-Encoding: 8bit\n'
	printf '\n%s\n' "$body"
} | /usr/sbin/sendmail -i -f "$from" -- "$to"
