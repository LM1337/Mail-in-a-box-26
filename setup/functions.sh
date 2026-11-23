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
	#
	# apt-daily, apt-daily-upgrade and unattended-upgrades run by themselves, for
	# example shortly after a boot. apt-get fails at once when one of them holds
	# a lock, so wait for them first (B79).
	wait_for_apt_locks
	DEBIAN_FRONTEND=noninteractive hide_output apt-get -y -o DPkg::Lock::Timeout=600 -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confnew" "$@"
}

function wait_for_apt_locks {
	# Wait (at most 10 minutes) until no other package run holds the dpkg or apt
	# locks. DPkg::Lock::Timeout covers only the dpkg locks, not the locks of the
	# package lists and of the download cache. The test lock is released at once.
	local i
	command -v python3 > /dev/null || return 0
	for i in $(seq 120); do
		if python3 -I - <<- 'PY' 2> /dev/null; then
			import fcntl, os, sys
			for f in ("/var/lib/dpkg/lock-frontend", "/var/lib/dpkg/lock", "/var/lib/apt/lists/lock", "/var/cache/apt/archives/lock"):
			    try:
			        fd = os.open(f, os.O_WRONLY)
			    except OSError:
			        continue
			    try:
			        fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
			        fcntl.lockf(fd, fcntl.LOCK_UN)
			    except OSError:
			        sys.exit(1)
			    finally:
			        os.close(fd)
			PY
			return 0
		fi
		if [ "$i" = 1 ]; then echo "Waiting for another package run (apt-daily, unattended-upgrades) to finish..."; fi
		sleep 5
	done
	echo "apt/dpkg is still locked after 10 minutes. Run setup again when it is free." >&2
	exit 1
}

function apt_install {
	# Install a bunch of packages. We used to report which packages were already
	# installed and which needed installing, before just running an 'apt-get
	# install' for all of the packages.  Calling `dpkg` on each package is slow,
	# and doesn't affect what we actually do, except in the messages, so let's
	# not do that anymore.
	apt_get_quiet install "$@"
}

function apt_install_held {
	# apt_install "$2"..., while the packages' own scripts may not start or
	# restart the unit "$1" (B224). dovecot-core restarts Dovecot whenever a
	# package adds a module of it (its dpkg trigger), and that restart comes
	# with the old configuration, before setup has written the new one:
	# setup's own restart (load_dovecot) follows a few seconds later. Each
	# restart takes Dovecot's auth socket away for a moment, and every new
	# submission process of Postfix that meets that moment exits ("no SASL
	# authentication mechanisms"), after which Postfix's master throttles
	# the service. Held this way, Dovecot is restarted once, by setup.
	#
	# Done with a policy-rc.d of our own (invoke-rc.d and deb-systemd-invoke
	# ask it), only while the unit runs, and never over a policy-rc.d that
	# is not ours (a container's): then this is apt_install. The file is
	# removed right after apt-get, also when it fails; one left by a setup
	# run that was killed in that moment is replaced and removed by the
	# next. A unit whose package was updated in the same call keeps running
	# the old program until setup restarts it (service_runs_current_package).
	local unit=$1 policy=/usr/sbin/policy-rc.d rc=0
	local mark="# mailinabox: setup holds $1 (apt_install_held in setup/functions.sh)"
	shift
	if [ -e "$policy" ] && ! grep -qxF "$mark" "$policy" 2> /dev/null; then
		apt_install "$@"
		return
	fi
	if ! systemctl is-active --quiet "$unit".service; then
		rm -f "$policy"
		apt_install "$@"
		return
	fi
	# Its arguments: [--quiet] UNIT ACTION [RUNLEVEL] (invoke-rc.d passes
	# --quiet first when it was given it).
	printf '#!/bin/sh\n%s\nfor a; do case "$a" in %s|%s.service) exit 101 ;; esac; done\nexit 0\n' "$mark" "$unit" "$unit" > "$policy"
	chmod 755 "$policy"
	( apt_install "$@" ) || rc=$?
	rm -f "$policy"
	if [ "$rc" != 0 ]; then exit "$rc"; fi
}

function flush_local_deferred {
	# Retries now the deferred mail that waited for a service on the box
	# itself (B225): setup restarts spampd and Dovecot, and mail that
	# Postfix handed to them in that moment (port 10025 refused, or the
	# connection lost) would wait for Postfix's next try, up to 5 minutes
	# (minimal_backoff_time). Only those mails: other deferred mail keeps
	# its schedule, so a mail server that throttles the box is not asked
	# again at once. Held mail (the sending limit) is not deferred mail and
	# stays held.
	systemctl is-active --quiet postfix || return 0
	local id
	{ postqueue -j 2> /dev/null || true; } | python3 -c '
import json, sys
for line in sys.stdin:
	try:
		m = json.loads(line)
	except ValueError:
		continue
	if m.get("queue_name") == "deferred" and any("127.0.0.1[127.0.0.1]" in (r.get("delay_reason") or "") for r in m.get("recipients", [])):
		print(m.get("queue_id", ""))
' | while read -r id; do
		[[ "$id" =~ ^[0-9A-Za-z]+$ ]] && postqueue -i "$id" > /dev/null 2>&1 || true
	done
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
	# does not change that (B67). Only a disabled unit is enabled, by its real
	# name. Pass the real name: an alias such as bind9.service (named.service)
	# is a link that exists only while its unit is enabled, so it cannot find
	# a disabled unit.
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

# Setup restarted the mail services several times per run: Dovecot 3, Postfix
# 3, PHP-FPM 4, fail2ban 2 times. Each restart closes the listening sockets for
# a second or two, and the clients of the box notice: IMAP logins fail, and
# Nextcloud's IMAP login (user_external), which Z-Push's CalDAV/CardDAV calls
# go through, counted each of those as a failed login of 127.0.0.1 (B121,
# B122). The functions below load a new configuration with a reload where the
# service supports it (the listening sockets stay), and restart only when the
# service does not run or runs the program of an older package.

function service_runs_current_package {
	# True if the unit is active, was started after the package was last
	# installed or upgraded, and its main process uses no program or library
	# file that has been replaced since it started. An upgrade normally
	# restarts its service (dpkg); one that left the old process running (or a
	# service started before the package of a plugin it loads) needs a
	# restart, a reload is not enough. The same holds after an upgrade of a
	# library or of the interpreter (system.sh's apt upgrade: libssl,
	# python3), which the restarts of earlier versions picked up on every
	# run: the kernel shows a replaced file of a process's mappings as
	# "(deleted)" in /proc/PID/maps (what needrestart looks at, too).
	#
	# PACKAGE may name more packages after the unit's own, separated by
	# spaces: libraries that the program reads rather than maps, such as the
	# Perl modules of spampd, postgrey and munin-node (an update of
	# SpamAssassin's modules changes nothing in spampd's package and shows no
	# "(deleted)" mapping). These others count only when they are installed.
	local unit=$1 pkg=$2 started installed pid p first=1
	local pkgs=()
	systemctl is-active --quiet "$unit" || return 1
	started=$(systemctl show -P ActiveEnterTimestamp "$unit" 2> /dev/null || true)
	[ -n "$started" ] || return 1
	started=$(date -d "$started" +%s 2> /dev/null) || return 1
	read -r -a pkgs <<< "$pkg" # empty: a service of no package of its own
	for p in "${pkgs[@]}"; do
		installed=$(dpkg-query -W -f='${db-fsys:Last-Modified}' "$p" 2> /dev/null || true)
		if [[ ! $installed =~ ^[0-9]+$ ]]; then
			[ -z "$first" ] || return 1
		elif [ "$installed" -gt "$started" ]; then
			return 1
		fi
		first=
	done
	pid=$(systemctl show -P MainPID "$unit" 2> /dev/null || true)
	[[ $pid =~ ^[1-9][0-9]*$ ]] || return 1
	! grep -qE ' /(usr/)?(lib|lib64|libexec|bin|sbin)/[^ ]* \(deleted\)$' "/proc/$pid/maps" 2> /dev/null
}

function unit_invocation {
	# unit_invocation UNIT
	# The InvocationID of UNIT's current run, or nothing. systemd gives a unit
	# a new one each time it starts (at boot, at a restart by setup, an
	# administrator, a package or a hook); a reload keeps it.
	local id
	id=$(systemctl show -P InvocationID "$1" 2> /dev/null || true)
	if [[ $id =~ ^[0-9a-f]{32}$ ]]; then
		echo "$id"
	fi
}

function record_matches {
	# record_matches UNIT RECORD SUM
	# True when RECORD ("SUM INVOCATION", written by write_record right after
	# setup restarted or reloaded UNIT) names SUM and the run of UNIT that is
	# active now. Any other start of UNIT since makes it false: what the unit
	# read then is not known. A downgrade to a version that keeps no record
	# (v78-r2604.4 restarts these services on every run, with its own code
	# and configuration) and the way back up give the same checksum as
	# before the downgrade, also with a reboot in between (the services
	# start at boot from the old checkout and the old files then), and the
	# old version would have kept running. The start time of the unit cannot
	# tell these apart from a plain reboot. The price: one more restart (or
	# reload) at the first setup run after a reboot or after a restart by
	# something else, unless that restart recorded itself (refresh_record).
	local inv
	inv=$(unit_invocation "$1")
	[ -n "$inv" ] && [ "$(cat "$2" 2> /dev/null || true)" = "$3 $inv" ]
}

function write_record {
	# write_record UNIT RECORD SUM
	# Records SUM with the run of UNIT that is active now (record_matches).
	mkdir -p "$(dirname "$2")"
	echo "$3 $(unit_invocation "$1")" > "$2"
}

function refresh_record {
	# refresh_record UNIT ARG...
	# For a restart of UNIT by something of the box's own, such as spampd's
	# sa-update hook: when UNIT's record names the checksum of what it reads
	# now (ARG..., as for restart_on_change), the run of UNIT that is active
	# now started with the files that setup recorded, and it is recorded
	# (write_record), so that the next setup run does not restart it once
	# more. Nothing otherwise (no record; other files, e.g. those of a
	# downgrade; UNIT does not run): the next setup run restarts it then.
	local unit=$1 sum record
	shift
	record=/var/lib/mailinabox/$unit-config.sha256
	systemctl is-active --quiet "$unit.service" || return 0
	sum=$(config_checksum "$@")
	if [ "$(cut -d' ' -f1 "$record" 2> /dev/null || true)" = "$sum" ]; then
		write_record "$unit.service" "$record" "$sum"
	fi
}

function record_hook {
	# record_hook UNIT ARG...
	# Prints a bash script that runs refresh_record UNIT ARG..., with the
	# functions it needs (from this file, so that it computes the checksum
	# as setup does). It always exits with 0.
	echo '#!/bin/bash'
	echo "# Written by Mail-in-a-Box setup: records the run of $1 that a hook before this one started, see refresh_record in setup/functions.sh."
	echo 'PATH=/usr/sbin:/usr/bin:/sbin:/bin'
	declare -f config_checksum unit_invocation write_record refresh_record
	printf 'refresh_record'
	printf ' %q' "$@"
	echo ' || true'
	echo 'exit 0'
}

function config_checksum {
	# The SHA-256 of what a service reads when it starts, for restart_on_change.
	# Each argument is
	#   FILE       its content ("missing" when it does not exist);
	#   tree:DIR   the names and contents of the regular files below DIR
	#              (without Python's __pycache__ directories);
	#   dir:DIR    the names in DIR, with their types and the targets of the
	#              symbolic links (Munin's plugins), not their contents;
	#   stat:FILE  its name, inode, size and time, read without following a
	#              symbolic link and without opening it (a file of another
	#              account, such as the DKIM key, which root does not read).
	# All of them are in directories of root's own, except the stat: ones.
	local a
	for a in "$@"; do
		case "$a" in
		tree:*)
			echo "$a"
			find "${a#tree:}" -name __pycache__ -prune -o -type f -print0 2> /dev/null | LC_ALL=C sort -z | xargs -0r sha256sum 2> /dev/null || true ;;
		dir:*)
			echo "$a"
			find "${a#dir:}" -mindepth 1 -maxdepth 1 -printf '%f %y %l\n' 2> /dev/null | LC_ALL=C sort || true ;;
		stat:*)
			stat -c '%n %i %s %Y' -- "${a#stat:}" 2> /dev/null || echo "${a#stat:} missing" ;;
		*)
			if [ -f "$a" ]; then
				echo "$a $(sha256sum < "$a" 2> /dev/null || echo unreadable)"
			else
				echo "$a missing"
			fi ;;
		esac
	done | sha256sum | cut -d' ' -f1
}

function restart_on_change {
	# restart_on_change UNIT "PACKAGE [LIBRARY-PACKAGE...]" ARG...
	# Setup restarted OpenDKIM, OpenDMARC, spampd, postgrey, named,
	# systemd-resolved, munin-node and the management daemon on every run,
	# also when nothing had changed. While OpenDKIM restarts, Postfix passes
	# mail unsigned (milter_default_action=accept); while OpenDMARC, spampd
	# or postgrey restart, mail waits or is deferred. This restarts UNIT only
	# when what it reads at its start (ARG..., see config_checksum) is not
	# what it read at the last restart by setup (the checksum is kept in
	# /var/lib/mailinabox/UNIT-config.sha256, as for Dovecot, see
	# load_dovecot), or when it does not run or runs the program of an older
	# PACKAGE (service_runs_current_package; empty PACKAGE: only the
	# replaced files are checked), or when it was started since setup wrote
	# the record, by anything else or at boot (record_matches: a downgrade
	# and the way back up). A box updated to this version restarts each of
	# them once more, as it has no checksums yet.
	local unit=$1 pkg=$2 sum record
	shift 2
	record=/var/lib/mailinabox/$unit-config.sha256
	sum=$(config_checksum "$@")
	enable_service "$unit"
	if service_runs_current_package "$unit.service" "$pkg" && record_matches "$unit.service" "$record" "$sum"; then
		return 0
	fi
	hide_output service "$unit" restart
	write_record "$unit.service" "$record" "$sum"
}

function reload_fail2ban {
	# fail2ban unbans every address when it stops and bans them again from its
	# database only after it has started (about 2 seconds without any ban). A
	# reload keeps the running jails and their bans, starts the new jails and
	# stops the removed ones. "reload_fail2ban --restart" also restarts the
	# jails (needed when bantime.* options were removed, see
	# management/fail2ban_admin.py); their bans come back from the database.
	# fail2ban is restarted only when it does not run, runs an older package,
	# or refuses the reload (then the restart shows the same error in its log,
	# as before).
	enable_service fail2ban
	if service_runs_current_package fail2ban.service fail2ban && fail2ban-client ping > /dev/null 2>&1; then
		if fail2ban-client reload "$@" > /dev/null 2>&1; then
			return 0
		fi
		echo "fail2ban did not reload its configuration; restarting it."
	fi
	hide_output service fail2ban restart
}

function reload_postfix {
	# Postfix reads main.cf and master.cf again on a reload; its processes
	# finish their sessions first. Only inet_interfaces and inet_protocols
	# need a restart: pass "restart" when they changed. Postfix is also
	# restarted when it does not run or runs an older package.
	enable_service postfix
	if [ "${1:-}" != restart ] && service_runs_current_package postfix.service postfix \
			&& postfix status > /dev/null 2>&1; then
		hide_output postfix check
		hide_output service postfix reload
		return
	fi
	hide_output service postfix restart
}

function restart_php_fpm {
	# setup/web.sh, webmail.sh, nextcloud.sh and zpush.sh each change PHP-FPM's
	# configuration (php.ini, the pool, PHP modules). setup/start.sh sets
	# PHP_FPM_RESTART=later and loads it once, after the last of them; a
	# script run on its own loads it at once (load_php_fpm).
	if [ "${PHP_FPM_RESTART:-}" = later ]; then
		return 0
	fi
	load_php_fpm
}

function load_php_fpm {
	# Setup restarted PHP-FPM once per run (B122). A restart ends every
	# running request, ActiveSync's long polls among them, and nginx answers
	# 502 for them and, for a second, for new ones (ActiveSync, CalDAV and
	# CardDAV, webmail, Nextcloud).
	#
	# Now nothing is done when PHP-FPM runs the program of the current
	# package, was not started since by anything else or at boot
	# (record_matches), and its configuration is the one it loaded last: the files in
	# /etc/php/VER/fpm (php.ini, php-fpm.conf, the pools, the modules in
	# conf.d) and mods-available, as a checksum in
	# /var/lib/mailinabox/php-fpm-config.sha256 (config_checksum). PHP code
	# that setup replaces needs nothing: opcache checks the files' times
	# (opcache.revalidate_freq=1, setup/nextcloud.sh).
	#
	# Otherwise a reload: PHP-FPM runs its program again in the same process
	# (SIGUSR2), which reads php-fpm.conf, the pools, php.ini and the modules
	# (conf.d) anew, as a restart does, and keeps the listening socket, so no
	# connection is refused: new requests wait in its queue until the new
	# workers take them. First the old workers finish their running
	# requests, for up to process_control_timeout (setup/web.sh sets 5 s;
	# with the package's 0 a reload ends them at once); a longer request,
	# such as an ActiveSync Ping, is ended then (nginx answers it with 502,
	# as at a restart), and new requests wait that long. php-fpm -t first: a
	# reload with a configuration that PHP-FPM refuses would stop it, so the
	# restart below shows the error then. The reload is asynchronous: setup
	# waits until PHP-FPM logs that it is ready again ("ready to handle
	# connections" in its log after the reload), and restarts it if it has
	# not within 30 s or no longer runs.
	#
	# A restart also when PHP-FPM does not run (setup/nextcloud.sh stopped it
	# for an upgrade of Nextcloud) or runs the program of an older package or
	# a replaced module (service_runs_current_package).
	local unit=php$PHP_VER-fpm log=/var/log/php$PHP_VER-fpm.log sum size i
	local record=/var/lib/mailinabox/php-fpm-config.sha256
	sum=$(config_checksum "tree:/etc/php/$PHP_VER/fpm" "dir:/etc/php/$PHP_VER/fpm/conf.d" \
		"tree:/etc/php/$PHP_VER/mods-available" "tree:/etc/systemd/system/$unit.service.d")
	enable_service "$unit"
	if service_runs_current_package "$unit.service" "$unit"; then
		if record_matches "$unit.service" "$record" "$sum"; then
			return 0
		fi
		if "php-fpm$PHP_VER" -t > /dev/null 2>&1; then
			size=$(stat -c %s "$log" 2> /dev/null || echo 0)
			if systemctl reload "$unit" > /dev/null 2>&1; then
				for i in $(seq 300); do
					if [[ $(tail -c "+$((size + 1))" "$log" 2> /dev/null || true) == *"ready to handle connections"* ]]; then
						if systemctl is-active --quiet "$unit"; then
							write_record "$unit.service" "$record" "$sum"
							return 0
						fi
						break
					fi
					systemctl is-active --quiet "$unit" || break
					sleep 0.1
				done
			fi
		fi
		echo "PHP-FPM did not load its new configuration with a reload; restarting it."
	fi
	hide_output service "$unit" restart
	write_record "$unit.service" "$record" "$sum"
}

function stop_php_fpm {
	# setup/nextcloud.sh stops PHP-FPM while it upgrades Nextcloud. It runs
	# again only after the restart that follows zpush.sh (PHP_FPM_RESTART=later
	# above): a run that ended in between left webmail, Nextcloud and
	# ActiveSync without PHP-FPM (HTTP 502) until a later run got that far.
	# start.sh's EXIT trap starts it again then (start_stopped_php_fpm, B149).
	PHP_FPM_STOPPED=1
	service php"$PHP_VER"-fpm stop &> /dev/null || /bin/true
}

function start_stopped_php_fpm {
	# Starts PHP-FPM if this run stopped it (stop_php_fpm) and it does not run.
	# After the restart at the end of the service scripts it runs, so this does
	# nothing (B122: one restart per run).
	if [ -n "${PHP_FPM_STOPPED:-}" ] && ! systemctl is-active --quiet php"$PHP_VER"-fpm 2> /dev/null; then
		echo "Starting PHP-FPM again, which setup had stopped for the Nextcloud upgrade."
		service php"$PHP_VER"-fpm start &> /dev/null || echo "PHP-FPM did not start (service php$PHP_VER-fpm start)." >&2
	fi
	return 0
}

function load_dovecot {
	# Load Dovecot's configuration after setup has written all of it.
	# doveconf -n first: a configuration that Dovecot refuses stops setup with
	# Dovecot's message, and the running Dovecot keeps the old one.
	#
	# Nothing is done when Dovecot runs the program of the current package and
	# already loaded this configuration (its checksum is kept in
	# /var/lib/mailinabox/dovecot-config.sha256; after a reboot Dovecot has
	# loaded the same files): an update that changes nothing in Dovecot's
	# files does not disturb its clients at all. Otherwise a reload
	# (doveadm reload): the listening sockets stay, so no connection is
	# refused, but Dovecot ends the running IMAP sessions (the clients log in
	# again). Dovecot is restarted only when it does not run or runs an older
	# package.
	#
	# The reload is asynchronous: wait until the master has read the new
	# configuration (it writes its binary copy again) before the caller runs
	# doveadm against it.
	#
	# The checksum covers the settings of doveconf -n (not its comment lines,
	# which name the Dovecot version, the kernel and the OS release and
	# change with them; the package check above covers the version) and, as
	# Dovecot reads the certificate, key and DH files only when it loads its
	# configuration, their size and time (stat, which reads nothing through
	# a link).
	#
	# The checksum is recorded only once Dovecot has loaded the configuration:
	# when the master has not written its binary copy again within 10 seconds
	# of the reload (it keeps the old configuration when the new one fails at
	# runtime, e.g. a listener it cannot bind, which doveconf -n does not
	# see), Dovecot is restarted, which fails loudly then.
	#
	# A second checksum covers only the passdbs and userdbs (their blocks in
	# doveconf -n and the Lua scripts): when they change, Dovecot is
	# restarted instead (B223). It is recorded in
	# /var/lib/mailinabox/dovecot-auth.sha256 together with the checksum of
	# the whole configuration it was loaded with: it counts only while the
	# record of the whole configuration still names that one, so a box
	# without the file (an update from v78-r2604.4 or older) and a box that
	# an older version loaded since (a downgrade and the way back up) count
	# as changed.
	local conf sum auth_sum before i reloaded record=/var/lib/mailinabox/dovecot-config.sha256
	local auth_record=/var/lib/mailinabox/dovecot-auth.sha256
	conf=$(doveconf -n 2>&1) || { echo; echo "FAILED: doveconf -n"; echo "$conf"; exit 1; }
	auth_sum=$( {
		awk 'depth == 0 && /^(passdb|userdb)([ \t]|\{|$)/ { on = 1 }
			on { print; n = gsub(/\{/, "{"); m = gsub(/\}/, "}"); depth += n - m; if (depth <= 0) { on = 0; depth = 0 } }' <<< "$conf"
		sha256sum /usr/local/lib/mailinabox/dovecot-auth-guard/*.lua 2> /dev/null || true
	} | sha256sum | cut -d' ' -f1)
	sum=$( {
		grep -v '^#' <<< "$conf"
		sed -nE 's/^ *(ssl_server_)?(cert|key|dh)_file = //p' <<< "$conf" | while read -r f; do
			stat -L -c '%n %i %s %Y' -- "$f" 2> /dev/null || echo "$f missing"
		done
		# The Lua scripts of the auth process (the limit of failed logins
		# from the box itself, setup/mail-users.sh) are read when it starts:
		# their content (lua_file, and the library they load).
		sha256sum /usr/local/lib/mailinabox/dovecot-auth-guard/*.lua 2> /dev/null || true
	} | sha256sum | cut -d' ' -f1)
	enable_service dovecot
	# The packages of Dovecot's modules count too: a module installed while
	# Dovecot ran (its restart held back by apt_install_held, B224) needs a
	# restart.
	if service_runs_current_package dovecot.service "dovecot-core dovecot-imapd dovecot-pop3d dovecot-lmtpd dovecot-sqlite dovecot-sieve dovecot-managesieved dovecot-auth-lua dovecot-fts-xapian" \
			&& doveadm process status > /dev/null 2>&1; then
		if [ "$(cat "$record" 2> /dev/null || true)" = "$sum" ]; then
			# Dovecot runs this configuration, so also these passdbs.
			[ "$(cat "$auth_record" 2> /dev/null || true)" = "$auth_sum $sum" ] || echo "$auth_sum $sum" > "$auth_record"
			return 0
		fi
		if [ "$(cat "$auth_record" 2> /dev/null || true)" != "$auth_sum $(cat "$record" 2> /dev/null || true)" ]; then
			# A new passdb or userdb: a restart, not a reload (B223). On a
			# reload, the auth processes that still answer logins with the
			# old passdbs meet the new ones ("Auth worker sees different
			# passdbs/userdbs than auth server"), the auth process of
			# Dovecot 2.4 can then die on an assertion, and the logins in
			# that moment fail.
			hide_output service dovecot restart
		else
			before=$(stat -c %Y.%i /run/dovecot/dovecot.conf.binary 2> /dev/null || true)
			hide_output systemctl reload dovecot
			reloaded=
			for i in $(seq 100); do
				if [ "$(stat -c %Y.%i /run/dovecot/dovecot.conf.binary 2> /dev/null || true)" != "$before" ]; then
					reloaded=1
					break
				fi
				sleep 0.1
			done
			if [ -z "$reloaded" ]; then
				echo "Dovecot did not load its new configuration within 10 seconds of the reload; restarting it."
				hide_output service dovecot restart
			fi
		fi
	else
		hide_output service dovecot restart
	fi
	mkdir -p /var/lib/mailinabox
	echo "$sum" > "$record"
	echo "$auth_sum $sum" > "$auth_record"
}

function reload_nginx {
	# Load a new nginx configuration. A reload lets the old workers finish
	# their requests; a restart gives them only the unit's stop timeout (5 s
	# on Ubuntu) and then cuts long-polling ActiveSync, CalDAV and CardDAV
	# clients. A reload also opens new listen sockets. nginx is (re)started
	# only when it does not run, or when the running binary is not the
	# installed one any more (an upgrade of the package that left the old
	# process running). nginx -t first, so that a bad configuration stops
	# setup with nginx's message, and the running nginx keeps its old one.
	local pid
	enable_service nginx
	pid=$(systemctl show -P MainPID nginx.service 2> /dev/null || true)
	if ! systemctl is-active --quiet nginx.service || [ -z "$pid" ] || [ "$pid" = 0 ] \
		|| [ ! "/proc/$pid/exe" -ef /usr/sbin/nginx ]; then
		hide_output service nginx restart
		return
	fi
	hide_output nginx -t
	hide_output service nginx reload
}

function update_check_hint {
	# A short hint at tools/update-check.sh at the end of a setup run on an
	# existing box (setup/start.sh; not on a first install, and not when the
	# in-place upgrade or the migration tool runs setup: they have their own
	# reports). When the newest record in /root/update-check (as the tool,
	# UPDATE_CHECK_DIR) has a state from before an update but none from after
	# it, this run is most likely that update: name "after" and "mailcheck"
	# with that record. Otherwise the general tip. It never stops setup.
	local root=${UPDATE_CHECK_DIR:-/root/update-check} d newest='' tool
	tool="$(pwd)/tools/update-check.sh"
	if [ -d "$root" ] && [ ! -L "$root" ]; then
		for d in "$root"/[0-9]*-[0-9]*; do
			[ -d "$d" ] && [ ! -L "$d" ] || continue
			[[ ${d##*/} =~ ^[0-9]{8}-[0-9]{6}$ ]] || continue
			newest=$d # the glob is sorted, the last one is the newest
		done
	fi
	echo
	if [ -n "$newest" ] && [ -f "$newest/before/time.txt" ] && [ ! -e "$newest/after" ]; then
		echo "tools/update-check.sh recorded the state of this box before an update,"
		echo "but not yet after it ($newest)."
		echo "To compare the state and to test the mail round trip now:"
		echo
		echo "  sudo $tool after --dir ${newest##*/}"
		echo "  sudo $tool mailcheck --dir ${newest##*/}"
	else
		echo "Tip: tools/update-check.sh can check an update of this box: \"before\" and"
		echo "\"backup\" before the next update, \"after\" and \"mailcheck\" after it"
		echo "(optional; see \"Updating the fork\" in README-fork.md)."
	fi
	echo
	return 0
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
	# Clone into a directory of root's own (mktemp -d, mode 0700), not under a
	# predictable name in /tmp that another local user could create first (B97).
	TMPPATH=$(mktemp -d) || exit 1
	rm -rf "$TARGETPATH"
	git clone -q "$REPO" "$TMPPATH/repo" || exit 1
	(cd "$TMPPATH/repo"; git checkout -q "$TREEISH";) || exit 1
	mv "$TMPPATH/repo/$SUBDIR" "$TARGETPATH"
	rm -rf "$TMPPATH"
}
