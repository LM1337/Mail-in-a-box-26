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
#  * SpamAssassin: the test domains are not delegated in public DNS, and the
#    public wildcard *.example.net (DMARC p=quarantine on example.net) makes
#    every unsigned port-25 test mail fail DMARC/SPF. Neutralize exactly those
#    scores; GTUBE and the rest of the scoring stay in effect.
#
# Usage: sudo bash tests/fork/prepare-testenv.sh
set -euo pipefail

[ "$(id -u)" = 0 ] || { echo "run as root" >&2; exit 1; }
JUMP_HOST=192.0.2.1
PEERS="192.0.2.1 192.0.2.10 192.0.2.11"

if ! ufw status | grep -q "ALLOW IN.*$JUMP_HOST\|$JUMP_HOST.*ALLOW"; then
	ufw insert 1 allow proto tcp from "$JUMP_HOST" to any port 22 comment 'test: jump host'
fi

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
echo "test environment prepared on $(hostname -f)"
