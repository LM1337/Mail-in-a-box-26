#!/bin/bash
# Install the 'host', 'sed', and and 'nc' tools. This script is run before
# the rest of the system setup so we may not yet have things installed.
apt_get_quiet install bind9-host sed netcat-openbsd

# Spamhaus answers a query for a listed name or address with an address in
# 127.0.0.0/8 that says which list it is on, and a query it did not answer
# with one in 127.255.255.0/24: 127.255.255.254 for a query that came through
# a public resolver (1.1.1.1, 8.8.8.8, the default resolvers of many hosting
# providers), which it refuses, 127.255.255.255 for too many queries. Setup
# used to stop on any answer, so a fresh install on such a machine stopped,
# saying the hostname was listed (B136). Only a listing stops setup now; an
# answer that is no listing is shown, and setup goes on (the status checks
# look again later, through the box's own resolver). The trailing dot keeps
# the resolver's search domains out: with a wildcard record there, "not
# listed" would come back as an address.
function spamhaus_answer {
	host -t A "$1." 2> /dev/null | awk '/ has address / { print $NF; exit }'
}
function spamhaus_not_checked {
	echo
	echo "Could not check whether $1 is listed in the Spamhaus $2:"
	echo "Spamhaus answered $3, which is no listing (127.255.255.254: it"
	echo "refuses queries through public DNS resolvers). Check it yourself on"
	echo "https://check.spamhaus.org/. Setup goes on."
	echo
}

# Stop if the PRIMARY_HOSTNAME is listed in the Spamhaus Domain Block List.
# The user might have chosen a name that was previously in use by a spammer
# and will not be able to reliably send mail. Do this after any automatic
# choices made above.
SPAMHAUS_ANSWER=$(spamhaus_answer "$PRIMARY_HOSTNAME.dbl.spamhaus.org")
if [[ $SPAMHAUS_ANSWER =~ ^127\.0\.1\.([2-9]|[1-9][0-9])$ ]]; then
	echo
	echo "The hostname you chose '$PRIMARY_HOSTNAME' is listed in the"
	echo "Spamhaus Domain Block List ($SPAMHAUS_ANSWER). See"
	echo "https://check.spamhaus.org/."
	echo
	echo "You will not be able to send mail using this domain name, so"
	echo "setup cannot continue."
	echo
	exit 1
elif [ -n "$SPAMHAUS_ANSWER" ]; then
	spamhaus_not_checked "the hostname $PRIMARY_HOSTNAME" "Domain Block List" "$SPAMHAUS_ANSWER"
fi

# Stop if the IPv4 address is listed in the ZEN Spamhouse Block List.
# The user might have ended up on an IP address that was previously in use
# by a spammer, or the user may be deploying on a residential network. We
# will not be able to reliably send mail in these cases.
if [[ $PUBLIC_IP =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
	REVERSED_IPV4=$(echo "$PUBLIC_IP" | awk -F. '{ print $4"."$3"."$2"."$1 }')
	SPAMHAUS_ANSWER=$(spamhaus_answer "$REVERSED_IPV4.zen.spamhaus.org")
	if [[ $SPAMHAUS_ANSWER =~ ^127\.0\.0\.([2-9]|1[01])$ ]]; then
		echo
		echo "The IP address $PUBLIC_IP is listed in the Spamhaus Block List"
		echo "($SPAMHAUS_ANSWER). See https://check.spamhaus.org/."
		echo
		echo "You will not be able to send mail using this machine, so setup"
		echo "cannot continue."
		echo
		echo "Associate a different IP address with this machine if possible."
		echo "Many residential network IP addresses are listed, so Mail-in-a-Box"
		echo "typically cannot be used on a residential Internet connection."
		echo
		exit 1
	elif [ -n "$SPAMHAUS_ANSWER" ]; then
		spamhaus_not_checked "the IP address $PUBLIC_IP" "Block List (ZEN)" "$SPAMHAUS_ANSWER"
	fi
fi

# Stop if we cannot make an outbound connection on port 25. Many residential
# networks block outbound port 25 to prevent their network from sending spam.
# See if we can reach one of Google's MTAs with a 5-second timeout.
if ! nc -z -w5 aspmx.l.google.com 25; then
	echo
	echo "Outbound mail (port 25) seems to be blocked by your network."
	echo
	echo "You will not be able to send mail using this machine, so setup"
	echo "cannot continue."
	echo
	echo "Many residential networks block port 25 to prevent hijacked"
	echo "machines from being able to send spam. I just tried to connect"
	echo "to Google's mail server on port 25 but the connection did not"
	echo "succeed."
	echo
	exit 1
fi
