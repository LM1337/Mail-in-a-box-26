#!/bin/bash
# TEST ENVIRONMENT ONLY - never run this on a production box.
#
# Adapts a Mail-in-a-Box test VM on a private test network (e.g. a bridge on
# the virtualization host) so that tests/fork/smoke.py measures the box and
# not the test network. Run as root after every (re)install; it is idempotent.
#
#  * ufw: MIAB rate-limits ssh ("ufw limit 22/tcp", 6 connections / 30 s per IP).
#    All test traffic comes through the jump host, so allow it fully.
#  * postgrey: skip greylisting for the peer test boxes, otherwise every
#    port-25 test waits 180 s or more.
#  * /etc/hosts: a public wildcard record of the parent domain (e.g.
#    *.example.net) can resolve the test host names to production servers.
#    Pin the box's own PRIMARY_HOSTNAME to its own address, also in
#    cloud-init's hosts template (cloud-init regenerates /etc/hosts on every
#    boot).
#  * Outbound firewall: block the production mail server and the wildcard
#    target, so a test box can never talk to them, whatever DNS says.
#  * SpamAssassin: the test domains are not delegated in public DNS, and a
#    public wildcard with a strict DMARC policy on the parent domain makes
#    every unsigned port-25 test mail fail DMARC/SPF. Neutralize exactly those
#    scores; GTUBE and the rest of the scoring stay in effect.
#  * fail2ban: put the jump host on the allowlist of the adaptive fail2ban
#    (management/fail2ban_admin.py), so that no jail (the slow ones count
#    failures over hours) can lock the test lab out. Attacks for fail2ban
#    tests must come from another source (the peer, or a container on the box).
#
# Configuration (environment, or KEY=VALUE lines in the file TESTENV_FILE,
# e.g. the same file as smoke.py's --env-file). There are no defaults: the
# script refuses to run without them.
#   JUMP_HOST   IP of the jump host the tests come through, e.g. 192.0.2.1
#   PEERS       IPs that skip greylisting, e.g. "192.0.2.1 192.0.2.10 192.0.2.11"
#   BLOCK_V4    production IPv4 addresses to block outbound, e.g. "203.0.113.5"
#   BLOCK_V6    production IPv6 addresses to block outbound, e.g. "2001:db8::1"
#               (may be set to "" when there are none)
#
# Usage: sudo TESTENV_FILE=/root/testenv.env bash tests/fork/prepare-testenv.sh
#        (the file must be owned by root, mode 600; it is parsed, not sourced)
set -euo pipefail
# ufw translates its output via Python gettext, which reads LANGUAGE before
# LC_ALL; force untranslated output so the "ufw status" parsing below works.
export LC_ALL=C
unset LANGUAGE

[ "$(id -u)" = 0 ] || { echo "run as root" >&2; exit 1; }
if [ -n "${TESTENV_FILE:-}" ]; then
	# The file is read, never sourced (this runs as root): it must be a regular
	# file owned by root and not writable by anyone else, and only the four
	# keys below are taken from it, each a space-separated list of IPs.
	[ -f "$TESTENV_FILE" ] && [ ! -L "$TESTENV_FILE" ] \
		|| { echo "TESTENV_FILE $TESTENV_FILE is not a regular file" >&2; exit 1; }
	case "$(stat -c '%u %a' "$TESTENV_FILE")" in
		"0 600" | "0 400") ;;
		*) echo "TESTENV_FILE $TESTENV_FILE must be owned by root with mode 600" >&2; exit 1 ;;
	esac
	while IFS='=' read -r key value; do
		case "$key" in JUMP_HOST | PEERS | BLOCK_V4 | BLOCK_V6) ;; *) continue ;; esac
		value=${value%\"}
		value=${value#\"}
		value=${value%\'}
		value=${value#\'}
		[[ $value =~ ^[0-9A-Fa-f.:\ ]*$ ]] || { echo "TESTENV_FILE: $key is not a list of IP addresses" >&2; exit 1; }
		printf -v "$key" '%s' "$value"
	done < "$TESTENV_FILE"
fi
: "${JUMP_HOST:?JUMP_HOST must be set (see the header of this script)}"
: "${PEERS:?PEERS must be set (see the header of this script)}"
: "${BLOCK_V4:?BLOCK_V4 must be set (see the header of this script)}"
: "${BLOCK_V6?BLOCK_V6 must be set, to an empty value when there is none (see the header of this script)}"

# An inactive ufw accepts new rules into user.rules without loading them, so
# the outbound block below would silently not be enforced.
case "$(ufw status)" in
	"Status: active"*) ;;
	*) echo "ufw is not active: the production block would not be enforced (run ufw --force enable)" >&2; exit 1 ;;
esac

if ! ufw status | grep -q "ALLOW IN.*$JUMP_HOST\|$JUMP_HOST.*ALLOW"; then
	ufw insert 1 allow proto tcp from "$JUMP_HOST" to any port 22 comment 'test: jump host'
fi

# shellcheck disable=SC1091
source /etc/mailinabox.conf
for f in /etc/hosts /etc/cloud/templates/hosts.debian.tmpl; do
	[ -f "$f" ] || continue
	sed -i "/# miab-testenv\$/d" "$f"
	echo "$PUBLIC_IP $PRIMARY_HOSTNAME # miab-testenv" >> "$f"
	[ -n "${PUBLIC_IPV6:-}" ] && echo "$PUBLIC_IPV6 $PRIMARY_HOSTNAME # miab-testenv" >> "$f"
done

for ip in $BLOCK_V4 $BLOCK_V6; do
	ufw status | grep -q "DENY OUT.*$ip\|$ip.*DENY OUT" || ufw deny out to "$ip" comment 'test: never reach production' >/dev/null
done
# Verify that the DROP rules are actually loaded in the kernel (this also
# catches IPV6=no in /etc/default/ufw).
for ip in $BLOCK_V4; do
	iptables -S ufw-user-output | grep -q -- "-d $ip/32 .*-j DROP" || { echo "outbound block for $ip not loaded" >&2; exit 1; }
done
for ip in $BLOCK_V6; do
	ip6tables -S ufw6-user-output | grep -q -- "-d $ip/128 .*-j DROP" || { echo "outbound block for $ip not loaded" >&2; exit 1; }
done

WL=/etc/postgrey/whitelist_clients.local
touch "$WL"
for ip in $PEERS; do
	grep -qx "$ip" "$WL" || echo "$ip" >> "$WL"
done
systemctl restart postgrey

cat > /etc/spamassassin/zz-miab-testenv.cf <<'CF'
# TEST ENVIRONMENT ONLY (tests/fork/prepare-testenv.sh): test domains are not
# delegated in public DNS, so DMARC/SPF results are meaningless here.
score DMARC_FAIL_QUARANTINE 0
score DMARC_FAIL_REJECT 0
score SPF_NONE 0
CF
systemctl restart spampd

F2B_ADMIN="$(cd "$(dirname "$0")/../.." && pwd)/management/fail2ban_admin.py"
if [ -x "$F2B_ADMIN" ] && [ -x /usr/local/lib/mailinabox/env/bin/python3 ]; then
	"$F2B_ADMIN" --allow "$JUMP_HOST" > /dev/null
	fail2ban-client unban "$JUMP_HOST" > /dev/null || true
elif [ -f /etc/fail2ban/jail.d/mailinabox_adaptive.conf ]; then
	# Run from a copy outside the checkout: the allowlist step needs the box's
	# management/fail2ban_admin.py next to this script.
	echo "WARNING: $F2B_ADMIN not found, $JUMP_HOST is NOT on the fail2ban allowlist;" >&2
	echo "run the copy in the box's checkout (e.g. /root/mailinabox/tests/fork/prepare-testenv.sh)." >&2
fi
echo "test environment prepared on $(hostname -f)"
