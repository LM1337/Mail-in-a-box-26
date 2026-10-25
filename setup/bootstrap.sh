#!/bin/bash
#########################################################
# This script is intended to be run like this:
#
#   sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/setup/bootstrap.sh)"
#
# ("curl ... | sudo bash" works as root, with sudo.ws, or with NONINTERACTIVE=1;
# see below for sudo-rs.)
#
# This is the Ubuntu 26.04 fork of Mail-in-a-Box (see README-fork.md),
# https://github.com/LM1337/Mail-in-a-box-26
#
#########################################################

# The fork's repository (bootstrap.sh compares the checkout's origin with it).
DEFAULT_SOURCE=https://github.com/LM1337/Mail-in-a-box-26

if [ -z "$TAG" ]; then
	# If a version to install isn't explicitly given as an environment
	# variable, then install the latest version. But the latest version
	# depends on the machine's version of Ubuntu. Existing users need to
	# be able to upgrade to the latest version available for that version
	# of Ubuntu to satisfy the migration requirements.
	#
	# Also, the system status checks read this script for TAG = (without the
	# space, but if we put it in a comment it would confuse the status checks!)
	# to get the latest version, so the first such line must be the one that we
	# want to display in status checks.
	#
	# Allow point-release versions of the major releases, e.g. 22.04.1 is OK.
	UBUNTU_VERSION=$( lsb_release -d | sed 's/.*:\s*//' | sed 's/\([0-9]*\.[0-9]*\)\.[0-9]/\1/' )
	if [ "$UBUNTU_VERSION" == "Ubuntu 26.04 LTS" ]; then
		# This machine is running Ubuntu 26.04, which is supported by
		# this fork of Mail-in-a-Box.
		TAG=v78-r2604.0-rc6
	elif [ "$UBUNTU_VERSION" == "Ubuntu 22.04 LTS" ]; then
		# This machine is running Ubuntu 22.04, which is supported by
		# Mail-in-a-Box versions 60 and later.
		TAG=v78
		SOURCE=${SOURCE:-https://github.com/mail-in-a-box/mailinabox}
	elif [ "$UBUNTU_VERSION" == "Ubuntu 18.04 LTS" ]; then
		# This machine is running Ubuntu 18.04, which is supported by
		# Mail-in-a-Box versions 0.40 through 5x.
		echo "Support is ending for Ubuntu 18.04."
		echo "Please immediately begin to migrate your data to"
		echo "a new machine running Ubuntu 22.04. See:"
		echo "https://mailinabox.email/maintenance.html#upgrade"
		TAG=v57a
	elif [ "$UBUNTU_VERSION" == "Ubuntu 14.04 LTS" ]; then
		# This machine is running Ubuntu 14.04, which is supported by
		# Mail-in-a-Box versions 1 through v0.30.
		echo "Ubuntu 14.04 is no longer supported."
		echo "The last version of Mail-in-a-Box supporting Ubuntu 14.04 will be installed."
		TAG=v0.30
	else
		echo "This script may be used only on a machine running Ubuntu 14.04, 18.04, 22.04, or 26.04."
		exit 1
	fi
fi

# Are we running as root?
if [[ $EUID -ne 0 ]]; then
	echo "This script must be run as root. Did you leave out sudo?"
	exit 1
fi

# sudo-rs, the sudo of Ubuntu 26.04, runs the command in a terminal of its own.
# When sudo's own input is not a terminal, as in "curl ... | sudo bash", it
# stops full-screen programs such as dialog: setup's first dialog box would
# hang without being shown. Say so before anything changes.
if [ -z "${NONINTERACTIVE:-}" ] && [ ! -t 0 ]; then
	case "$(readlink -f "/proc/$PPID/exe" 2> /dev/null)" in
		*/cargo/bin/sudo | */sudo-rs)
			echo "Setup asks its questions in dialog boxes, but sudo-rs (the sudo of Ubuntu 26.04)"
			echo "stops them when this script comes through a pipe into sudo. Run it like this instead"
			echo "(variables such as TAG=... go after sudo):"
			echo
			echo "  sudo bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/setup/bootstrap.sh)\""
			echo
			echo "Or give NONINTERACTIVE=1 and the answers (see README-fork.md, Installation)."
			exit 1
			;;
	esac
fi

# Clone the Mail-in-a-Box repository if it doesn't exist.
if [ ! -d "$HOME/mailinabox" ]; then
	if [ ! -f /usr/bin/git ]; then
		echo "Installing git . . ."
		apt-get -q -q update
		DEBIAN_FRONTEND=noninteractive apt-get -q -q install -y git < /dev/null
		echo
	fi

	if [ "$SOURCE" == "" ]; then
		SOURCE=$DEFAULT_SOURCE
	fi

	echo "Downloading Mail-in-a-Box $TAG. . ."
	git clone \
		-b "$TAG" --depth 1 \
		"$SOURCE" \
		"$HOME/mailinabox" \
		< /dev/null 2> /dev/null

	echo
fi

# Change directory to it.
cd "$HOME/mailinabox" || exit

# An existing checkout of upstream Mail-in-a-Box does not have this fork's tags
# (In-Place 5), and a checkout of this fork cloned from elsewhere (up to rc3
# the fork had another home) would fetch the release from there. Say so
# instead of failing with "Update failed" or installing an old release.
if [ "$SOURCE" == "" ]; then SOURCE=$DEFAULT_SOURCE; fi
# GitHub treats the owner and repository names case-insensitively.
ORIGIN=$(git config --get remote.origin.url || true)
ORIGIN_CMP=${ORIGIN%.git}
SOURCE_CMP=${SOURCE%.git}
if [ "${ORIGIN_CMP,,}" != "${SOURCE_CMP,,}" ]; then
	echo "$HOME/mailinabox is a checkout of $ORIGIN, not of $SOURCE."
	if [ -f tools/migrate-to-2604.sh ]; then
		# This fork (rc1 to rc3 were cloned from the fork's previous home).
		echo "To update it from $SOURCE, point it there once and run this command again:"
		echo "  sudo git -C $HOME/mailinabox remote set-url origin $SOURCE"
		echo "(To keep using $ORIGIN instead, give SOURCE=$ORIGIN to bash.)"
	else
		echo "To upgrade this box in place use tools/upgrade-in-place-to-2604.sh, see README-fork.md."
		echo "To use this checkout anyway: sudo git -C $HOME/mailinabox remote set-url origin $SOURCE"
	fi
	exit 1
fi

# Update it.
if [ "$TAG" != "$(git describe --always)" ]; then
	echo "Updating Mail-in-a-Box to $TAG . . ."
	# A release tag, or a branch (TAG=main, for testing): a branch is not a
	# tag, and a local branch of that name may be old or missing.
	if git fetch --depth 1 --force --prune origin tag "$TAG" 2> /dev/null; then
		REF=$TAG
	elif git fetch --depth 1 --force origin "$TAG"; then
		REF=FETCH_HEAD
	else
		echo "Could not fetch $TAG from $ORIGIN."
		exit 1
	fi
	if ! git checkout -q "$REF"; then
		echo "Update failed. Did you modify something in $PWD?"
		exit 1
	fi
	echo
fi

# Start setup script.
setup/start.sh
