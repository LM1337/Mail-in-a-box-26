#!/bin/bash
# TEST ENVIRONMENT ONLY - never run this on a production box.
#
# Adapts a Mail-in-a-Box test VM on the internal test bridge (192.0.2.0/24 on
# the virtualization host) so that tests/fork/smoke.py measures the box and not the test
# network. Run as root after every (re)install; it is idempotent.
#
#  * ufw: MIAB rate-limits ssh ("ufw limit 22/tcp", 6 connections / 30 s per IP).
#    All test traffic comes through the jump host 192.0.2.1, so allow it fully.
#  * postgrey: skip greylisting for the peer test boxes, otherwise every
#    port-25 test waits 180 s or more.
#  * /etc/hosts: the public wildcard *.example.net resolves the test host names
#    to production servers (A 198.51.100.240, AAAA of a production box). Pin the
#    box's own PRIMARY_HOSTNAME to its own address, also in cloud-init's hosts
#    template (Proxmox cloud-init regenerates /etc/hosts on every boot).
#  * Outbound firewall: block the production mail server and the wildcard
#    target, so a test box can never talk to them, whatever DNS says.
#  * SpamAssassin: the test domains are not delegated in public DNS, and the
#    public wildcard *.example.net (DMARC p=quarantine on example.net) makes
#    every unsigned port-25 test mail fail DMARC/SPF. Neutralize exactly those
#    scores; GTUBE and the rest of the scoring stay in effect.
#  * fail2ban: put the jump host on the allowlist of the adaptive fail2ban
#    (management/fail2ban_admin.py), so that no jail (the slow ones count
#    failures over hours) can lock the test lab out. Attacks for fail2ban
#    tests must come from another source (the peer, or a container on the box).
#
# Usage: sudo bash tests/fork/prepare-testenv.sh
set -euo pipefail
# ufw translates its output via Python gettext, which reads LANGUAGE before
# LC_ALL; force untranslated output so the "ufw status" parsing below works.
export LC_ALL=C
unset LANGUAGE

[ "$(id -u)" = 0 ] || { echo "run as root" >&2; exit 1; }
JUMP_HOST=192.0.2.1
PEERS="192.0.2.1 192.0.2.10 192.0.2.11"
BLOCK_V4="198.51.100.5 198.51.100.240"
BLOCK_V6="2001:db8::1"

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
fi
echo "test environment prepared on $(hostname -f)"
