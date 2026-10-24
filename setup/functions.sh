#!/bin/bash
# Turn on "strict mode." See http://redsymbol.net/articles/unofficial-bash-strict-mode/.
# -e: exit if any command unexpectedly fails.
# -u: exit if we have a variable typo.
# -o pipefail: don't ignore errors in the non-last command in a pipeline
set -euo pipefail

PHP_VER=8.5
PHP_LEGACY_VER=8.2

function hide_output {
	# This function hides the output of a command unless the command fails
	# and returns a non-zero exit code.

	# Get a temporary file.
	OUTPUT=$(mktemp)

	# Execute command, redirecting stderr/stdout to the temporary file. Since we
	# check the return code ourselves, disable 'set -e' temporarily.
	set +e
	"$@" &> "$OUTPUT"
	E=$?
	set -e

	# If the command failed, show the output that was captured in the temporary file.
	if [ $E != 0 ]; then
		# Something failed.
		echo
		echo "FAILED: $*"
		echo -----------------------------------------
		cat "$OUTPUT"
		echo -----------------------------------------
		exit $E
	fi

	# Remove temporary file.
	rm -f "$OUTPUT"
}

function apt_get_quiet {
	# Run apt-get in a totally non-interactive mode.
	#
	# Somehow all of these options are needed to get it to not ask the user
	# questions about a) whether to proceed (-y), b) package options (noninteractive),
	# and c) what to do about files changed locally (we don't cause that to happen but
	# some VM providers muck with their images; -o).
	#
	# Although we could pass -qq to apt-get to make output quieter, many packages write to stdout
	# and stderr things that aren't really important. Use our hide_output function to capture
	# all of that and only show it if there is a problem (i.e. if apt_get returns a failure exit status).
	DEBIAN_FRONTEND=noninteractive hide_output apt-get -y -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confnew" "$@"
}

function apt_install {
	# Install a bunch of packages. We used to report which packages were already
	# installed and which needed installing, before just running an 'apt-get
	# install' for all of the packages.  Calling `dpkg` on each package is slow,
	# and doesn't affect what we actually do, except in the messages, so let's
	# not do that anymore.
	apt_get_quiet install "$@"
}

function get_default_hostname {
	# Guess the machine's hostname. It should be a fully qualified
	# domain name suitable for DNS. None of these calls may provide
	# the right value, but it's the best guess we can make.
	set -- "$(hostname --fqdn      2>/dev/null ||
                 hostname --all-fqdns 2>/dev/null ||
                 hostname             2>/dev/null)"
	printf '%s\n' "$1" # return this value
}

function get_publicip_from_web_service {
	# This seems to be the most reliable way to determine the
	# machine's public IP address: asking a very nice web API
	# for how they see us. Thanks go out to icanhazip.com.
	# See: https://major.io/icanhazip-com-faq/
	#
	# Pass '4' or '6' as an argument to this function to specify
	# what type of address to get (IPv4, IPv6).
	curl -"$1" --fail --silent --max-time 15 icanhazip.com 2>/dev/null || /bin/true
}

function get_default_privateip {
	# Return the IP address of the network interface connected
	# to the Internet.
	#
	# Pass '4' or '6' as an argument to this function to specify
	# what type of address to get (IPv4, IPv6).
	#
	# We used to use `hostname -I` and then filter for either
	# IPv4 or IPv6 addresses. However if there are multiple
	# network interfaces on the machine, not all may be for
	# reaching the Internet.
	#
	# Instead use `ip route get` which asks the kernel to use
	# the system's routes to select which interface would be
	# used to reach a public address. We'll use 8.8.8.8 as
	# the destination. It happens to be Google Public DNS, but
	# no connection is made. We're just seeing how the box
	# would connect to it. There many be multiple IP addresses
	# assigned to an interface. `ip route get` reports the
	# preferred. That's good enough for us. See issue #121.
	#
	# With IPv6, the best route may be via an interface that
	# only has a link-local address (fe80::*). These addresses
	# are only unique to an interface and so need an explicit
	# interface specification in order to use them with bind().
	# In these cases, we append "%interface" to the address.
	# See the Notes section in the man page for getaddrinfo and
	# https://discourse.mailinabox.email/t/update-broke-mailinabox/34/9.
	#
	# Also see ae67409603c49b7fa73c227449264ddd10aae6a9 and
	# issue #3 for why/how we originally added IPv6.

	target=8.8.8.8

	# For the IPv6 route, use the corresponding IPv6 address
	# of Google Public DNS. Again, it doesn't matter so long
	# as it's an address on the public Internet.
	if [ "$1" == "6" ]; then target=2001:4860:4860::8888; fi

	# Get the route information.
	route=$(ip -"$1" -o route get $target 2>/dev/null | grep -v unreachable)

	# Parse the address out of the route information.
	address=$(echo "$route" | sed "s/.* src \([^ ]*\).*/\1/")

	if [[ "$1" == "6" && $address == fe80:* ]]; then
		# For IPv6 link-local addresses, parse the interface out
		# of the route information and append it with a '%'.
		interface=$(echo "$route" | sed "s/.* dev \([^ ]*\).*/\1/")
		address=$address%$interface
	fi

	echo "$address"
}

function ufw_allow {
	if [ -z "${DISABLE_FIREWALL:-}" ]; then
		# ufw has completely unhelpful output
		ufw allow "$1" > /dev/null;
	fi
}

function ufw_limit {
	if [ -z "${DISABLE_FIREWALL:-}" ]; then
		# ufw has completely unhelpful output
		ufw limit "$1" > /dev/null;
	fi
}

function enable_service {
	# The services of Mail-in-a-Box must also start after a reboot. A package
	# installed while its unit was masked (the release upgrade of
	# tools/upgrade-in-place-to-2604.sh up to rc3) stays disabled, and a restart
	# does not change that (B67). Only a disabled unit is enabled; an alias
	# (bind9 is named) is enabled by its real name.
	local unit state
	unit=$(systemctl show -P Id "$1" 2> /dev/null || true)
	[ -n "$unit" ] || return 0
	state=$(systemctl is-enabled "$unit" 2> /dev/null || true)
	if [ "$state" = disabled ]; then
		hide_output systemctl enable "$unit"
	fi
}

function install_unit {
	# Install the systemd unit conf/$1 of Mail-in-a-Box and enable it by name.
	# Upstream linked /etc/systemd/system/$1 to /lib/systemd/system/$1, and
	# enabling the unit by that path does the same; but /lib is a link to
	# usr/lib, so the link points to the unit's own file, and systemd 259 reports
	# "Too many levels of symbolic links" (is-enabled: bad). Such a link (any
	# link there, except a mask) is removed, and reenable replaces the
	# .wants links that go through /lib (B69).
	local unit=/lib/systemd/system/$1 link=/etc/systemd/system/$1
	cp --remove-destination "conf/$1" "$unit" # the target was a symlink into the checkout once
	if [ -L "$link" ] && [ "$(readlink "$link")" != /dev/null ]; then
		rm -f "$link"
	fi
	hide_output systemctl daemon-reload
	hide_output systemctl reenable "$1"
}

function restart_service {
	enable_service "$1"
	hide_output service "$1" restart
}

## Dialog Functions ##
function message_box {
	dialog --title "$1" --msgbox "$2" 0 0
}

function input_box {
	# input_box "title" "prompt" "defaultvalue" VARIABLE
	# The user's input will be stored in the variable VARIABLE.
	# The exit code from dialog will be stored in VARIABLE_EXITCODE.
	# Temporarily turn off 'set -e' because we need the dialog return code.
	declare -n result=$4
	declare -n result_code=$4_EXITCODE
	set +e
	result=$(dialog --stdout --title "$1" --inputbox "$2" 0 0 "$3")
	result_code=$?
	set -e
}

function input_menu {
	# input_menu "title" "prompt" "tag item tag item" VARIABLE
	# The user's input will be stored in the variable VARIABLE.
	# The exit code from dialog will be stored in VARIABLE_EXITCODE.
	declare -n result=$4
	declare -n result_code=$4_EXITCODE
	local IFS=^$'\n'
	set +e
	result=$(dialog --stdout --title "$1" --menu "$2" 0 0 0 "$3")
	result_code=$?
	set -e
}

function wget_verify {
	# Downloads a file from the web and checks that it matches
	# a provided hash. If the comparison fails, exit immediately.
	#
	# The algorithm follows from the length of the hex hash, so the pins
	# can be compared with the checksums upstream publishes:
	#   64 hex chars  = SHA256 (use this for all pins: download.nextcloud.com
	#                   <file>.sha256, the GitHub release asset "digest",
	#                   https://roundcube.net/download/)
	#   128 hex chars = SHA512
	#   40 hex chars  = SHA1 (legacy only, kept for compatibility; no upstream
	#                   publishes SHA1 any more)
	# An optional "sha256:" / "sha512:" / "sha1:" prefix is accepted, so a
	# GitHub digest can be pasted as is. It must match the hash length.
	local URL=$1
	local HASH=${2,,}
	local DEST=$3
	local HASHCMD PREFIX=""
	if [[ "$HASH" =~ ^(sha256|sha512|sha1): ]]; then
		PREFIX=${BASH_REMATCH[1]}
		HASH=${HASH#*:}
	fi
	if [[ ! "$HASH" =~ ^[0-9a-f]+$ ]]; then
		echo "wget_verify: hash for $URL is not a hex string: '$2'"
		exit 1
	fi
	case ${#HASH} in
		64)  HASHCMD=sha256sum ;;
		128) HASHCMD=sha512sum ;;
		40)  HASHCMD=sha1sum ;;
		*)
			echo "wget_verify: hash for $URL has ${#HASH} hex chars, expected 64 (SHA256), 128 (SHA512) or 40 (SHA1)."
			exit 1
			;;
	esac
	if [ -n "$PREFIX" ] && [ "${PREFIX}sum" != "$HASHCMD" ]; then
		echo "wget_verify: hash for $URL is prefixed '$PREFIX:' but has the length of a ${HASHCMD%sum} hash."
		exit 1
	fi
	local CHECKSUM="$HASH  $DEST"
	rm -f "$DEST"
	hide_output wget -O "$DEST" "$URL"
	if ! echo "$CHECKSUM" | $HASHCMD --check --strict > /dev/null; then
		echo "------------------------------------------------------------"
		echo "Download of $URL did not match expected checksum."
		echo "Found ($HASHCMD):"
		$HASHCMD "$DEST"
		if [ "$HASHCMD" != sha256sum ]; then
			echo "SHA256 (for new pins):"
			sha256sum "$DEST"
		fi
		echo
		echo "Expected:"
		echo "$CHECKSUM"
		rm -f "$DEST"
		exit 1
	fi
}

function git_clone {
	# Clones a git repository, checks out a particular commit or tag,
	# and moves the repository (or a subdirectory in it) to some path.
	# We use separate clone and checkout because -b only supports tags
	# and branches, but we sometimes want to reference a commit hash
	# directly when the repo doesn't provide a tag.
	REPO=$1
	TREEISH=$2
	SUBDIR=$3
	TARGETPATH=$4
	TMPPATH=/tmp/git-clone-$$
	rm -rf $TMPPATH "$TARGETPATH"
	git clone -q "$REPO" $TMPPATH || exit 1
	(cd $TMPPATH; git checkout -q "$TREEISH";) || exit 1
	mv $TMPPATH/"$SUBDIR" "$TARGETPATH"
	rm -rf $TMPPATH
}
