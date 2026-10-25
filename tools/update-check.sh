#!/bin/bash
#########################################################
# Checks around an update of a Mail-in-a-Box of this fork: the state before
# and after, a backup before, a mail round trip after.
#
# Run this as root on the box. The usual order:
#
#   tools/update-check.sh before      record the state, log audit baseline
#   tools/update-check.sh backup      fresh Mail-in-a-Box backup, encrypted
#                                     archive of the system next to it
#   (the update, see "Updating the fork" in README-fork.md)
#   tools/update-check.sh after       record the state again, compare it with
#                                     the one before, log audit of the update
#   tools/update-check.sh mailcheck   send a test mail over an external probe
#                                     address and wait for it to come back
#
# or without a checkout of this repository (like setup/bootstrap.sh):
#
#   curl -fsSL https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/tools/update-check.sh \
#     | sudo bash -s -- before
#
# Everything goes into /root/update-check/<stamp>/ (mode 0700): "before"
# makes a new stamp directory, the other steps use the newest one (or
# --dir STAMP). Nothing is written elsewhere, except the archive of "backup"
# on the backup server (rsync targets) and the backup of management/backup.py
# itself.
#
# before / after record (files in before/ and after/): the version and the
# origin of /root/mailinabox, the units (enabled, active) and the failed
# ones, the mail queue, the status checks (their error and warning lines),
# the warnings of doveconf and postconf, key settings of
# Postfix and Dovecot, the Nextcloud status, Munin's alert contact and
# limits, Docker containers, crontabs, mailname and hosts, fail2ban jails,
# systemd drop-ins, the listening ports, /etc/mailinabox.conf and the package
# versions of the mail services. "before" also runs tests/fork/log-audit.sh
# (default: the last 24 hours) as the baseline; "after" compares each file
# with "before" and marks the changes that the releases in between announce
# as EXPECTED (tools/expected-changes/<version>.txt, see there), the others as
# UNEXPECTED, and runs the log audit since "before" against that baseline
# (only new message classes count).
#
# backup: management/backup.py (as the nightly backup: incremental unless a
# full one is due; it stops Postfix, Dovecot, postgrey and PHP for its run),
# then a tar archive of /etc, /root/mailinabox, the crontabs, /var/lib/z-push,
# /var/lib/munin, /usr/local/lib/owncloud and the Docker stack directories and
# volumes named with --docker-dir and --docker-volume, and a pg_dump of each
# container named with --postgres. Each is encrypted with gpg (AES256) with
# the passphrase of the Mail-in-a-Box backups ($STORAGE_ROOT/backup/
# secret_key.txt) right as it is written; nothing goes to disk unencrypted.
# For an rsync target the files are copied next to the backups
# (<path>-system/update-check-<stamp>/, with the backup SSH key, like
# management/backup.py) and compared by checksum (rsync -c, dry run); for
# other targets they stay in the stamp directory (copy them off the machine).
#
# mailcheck: sends a marked mail (header X-Miab-Test: 1, a unique token) from
# administrator@PRIMARY_HOSTNAME (or --from) to an external probe address
# (--probe or PROBE_ADDRESS in /etc/mailinabox.conf): an address of another
# provider that forwards the mail back or answers it. It then waits for the
# mail with the token to come back over port 25 and be stored, and reports
# the outbound delivery, the inbound delivery, the spam filter, the folder
# (Sieve) and the storage. Without a probe address it says "skipped".
#
# See --help.
#########################################################

# Everything below is inside functions and the last line calls main, so a
# partially downloaded script (curl | bash) does nothing.

set -euo pipefail

STATE_ROOT=${UPDATE_CHECK_DIR:-/root/update-check}
SCRIPT_NAME=update-check.sh
# Raw files of the branch main (GitHub serves them from another host).
DEFAULT_RAW=https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main
MIAB_DIR=/root/mailinabox
STORAGE_ROOT=/home/user-data
PRIMARY_HOSTNAME=
PROBE_ADDRESS=
RUN_DIR=
SELF_REPO=
GPG_HOME=

say() { echo "$*"; }
warn() { echo "WARNING: $*" >&2; }
die() {
	echo >&2
	echo "ERROR: $*" >&2
	exit 1
}
section() {
	echo
	echo "-----------------------------------------------"
	echo "$*"
	echo "-----------------------------------------------"
}
human() { numfmt --to=iec-i --suffix=B "${1:-0}" 2> /dev/null || echo "${1:-0} bytes"; }

usage() {
	cat <<'EOF'
Usage: update-check.sh before    [--since TIME] [log audit options]
       update-check.sh backup    [--no-miab-backup] [--no-upload] [--docker-dir DIR]...
                                 [--docker-volume NAME]... [--postgres CONTAINER]...
       update-check.sh after     [--since TIME] [log audit options]
       update-check.sh mailcheck [--probe ADDRESS] [--from ADDRESS] [--timeout SECONDS]

Checks around an update of this fork (see "Updating the fork" in
README-fork.md): before the update "before" and "backup", after it "after"
and "mailcheck". Run it as root. Each step writes into
/root/update-check/<stamp>/ (mode 0700); "before" starts a new stamp, the
other steps use the newest one.

Steps:
  before        record the state of the box (before/) and run the log audit
                of the last 24 hours (--since) as the baseline
  backup        Mail-in-a-Box backup now (management/backup.py; mail stops
                for its run, as in the nightly backup), then an encrypted
                archive of /etc, /root/mailinabox, the crontabs, Z-Push,
                Munin, Nextcloud's code and the Docker stacks you name, copied
                next to the backups (rsync targets) and verified
  after         record the state again (after/), compare it with before/:
                each change is EXPECTED (announced by the releases in
                between, tools/expected-changes/) or UNEXPECTED; then the log
                audit since "before" against the baseline (only new message
                classes count). Exit code 1 if anything unexpected or new.
  mailcheck     mail round trip: a marked test mail to the probe address,
                which must send it back (forward or answer); waits until it
                is stored here and reports outbound, inbound, spam filter,
                folder (Sieve) and storage. Without a probe address: skipped.

Options:
  --dir STAMP           use /root/update-check/STAMP instead of the newest
  --since TIME          log audit window: "24 hours ago", "-24h", "2026-10-25
                        08:15" (default: 24 hours for before, the time of
                        before for after)
  --internet            log audit with tests/fork/log-audit-allow-internet.txt
                        (the usual noise of a box on the Internet)
  --allow-extra FILE    an allowlist of your own for the log audit (repeatable)
  --no-miab-backup      backup: no management/backup.py run, only the archive
  --no-upload           backup: keep the archive only in the stamp directory
  --docker-dir DIR      backup: also archive this directory (e.g. a docker
                        compose stack, /opt/app) (repeatable)
  --docker-volume NAME  backup: also archive this Docker volume (repeatable)
  --postgres CONTAINER  backup: pg_dump of the database of this container, with
                        its POSTGRES_USER and POSTGRES_DB (repeatable)
  --probe ADDRESS       mailcheck: the probe address (default: PROBE_ADDRESS
                        in /etc/mailinabox.conf)
  --from ADDRESS        mailcheck: the sender, an address of this box that
                        receives the mail back (default:
                        administrator@PRIMARY_HOSTNAME)
  --timeout SECONDS     mailcheck: how long to wait for the mail (default 900)
  -h, --help            show this help

Environment: UPDATE_CHECK_DIR (default /root/update-check).
EOF
}

# ---------------------------------------------------------------------------
# Setup of a run.

# Values of /etc/mailinabox.conf, read (not sourced).
conf_get() { sed -n "s/^$1=//p" /etc/mailinabox.conf 2> /dev/null | tail -n 1; }

load_conf() {
	[ -r /etc/mailinabox.conf ] || die "/etc/mailinabox.conf is missing: is this a Mail-in-a-Box?"
	STORAGE_ROOT=$(conf_get STORAGE_ROOT)
	PRIMARY_HOSTNAME=$(conf_get PRIMARY_HOSTNAME)
	PROBE_ADDRESS=$(conf_get PROBE_ADDRESS)
	[ -n "$STORAGE_ROOT" ] && [ -n "$PRIMARY_HOSTNAME" ] || die "/etc/mailinabox.conf has no STORAGE_ROOT or PRIMARY_HOSTNAME."
}

# The state directory: root's own, no symlink.
init_state_root() {
	if [ -L "$STATE_ROOT" ]; then die "$STATE_ROOT is a symlink; remove it."; fi
	(umask 077 && mkdir -p "$STATE_ROOT")
	[ "$(stat -c %u "$STATE_ROOT")" = 0 ] || die "$STATE_ROOT is not owned by root."
	chmod 700 "$STATE_ROOT"
}

new_run_dir() {
	local stamp
	stamp=$(date -u +%Y%m%d-%H%M%S)
	RUN_DIR=$STATE_ROOT/$stamp
	mkdir -m 700 "$RUN_DIR" || die "Could not create $RUN_DIR."
}

# The newest stamp directory (with a before/ if asked), or the one of --dir.
pick_run_dir() { # [need-before]
	local d
	if [ -n "$OPT_DIR" ]; then
		[[ $OPT_DIR =~ ^[0-9]{8}-[0-9]{6}$ ]] || die "--dir wants a stamp like 20261025-130000 (a directory in $STATE_ROOT)."
		RUN_DIR=$STATE_ROOT/$OPT_DIR
		[ -d "$RUN_DIR" ] && [ ! -L "$RUN_DIR" ] || die "$RUN_DIR does not exist."
	else
		RUN_DIR=
		for d in "$STATE_ROOT"/[0-9]*-[0-9]*; do
			[ -d "$d" ] && [ ! -L "$d" ] || continue
			[[ ${d##*/} =~ ^[0-9]{8}-[0-9]{6}$ ]] || continue
			if [ "${1:-}" = need-before ] && [ ! -f "$d/before/time.txt" ]; then continue; fi
			RUN_DIR=$d # the glob is sorted, the last one is the newest
		done
	fi
	if [ "${1:-}" = need-before ] && { [ -z "$RUN_DIR" ] || [ ! -f "$RUN_DIR/before/time.txt" ]; }; then
		die "No state from before the update in $STATE_ROOT${OPT_DIR:+/$OPT_DIR}. Run \"$SCRIPT_NAME before\" first."
	fi
	return 0
}

# The checkout this script runs from, if any (not through curl | bash).
find_self_repo() {
	local f d
	f=${BASH_SOURCE[0]:-}
	[[ $f == *.sh ]] && [ -f "$f" ] || return 0
	d=$(cd "$(dirname "$f")/.." && pwd)
	if [ -f "$d/tests/fork/log-audit.sh" ]; then SELF_REPO=$d; fi
}

# A file of this fork (path relative to the repository), downloaded from the
# branch main into the stamp directory (once per stamp).
fork_file() { # REL
	local rel=$1 f
	f=$RUN_DIR/fetched/$rel
	if [ ! -f "$f" ]; then
		(umask 077 && mkdir -p "$(dirname "$f")")
		curl -fsSL --max-time 120 -o "$f.part" "$DEFAULT_RAW/$rel" < /dev/null || {
			rm -f "$f.part"
			return 1
		}
		mv "$f.part" "$f"
	fi
	echo "$f"
}

# ---------------------------------------------------------------------------
# State record (before/ and after/). Read-only on the box; each file is one
# aspect, one item per line, sorted where the order means nothing. Files
# named in INFO_FILES change by themselves (queue, Munin states, packages):
# their differences are shown, not judged.

INFO_FILES="queue.txt munin-limits.txt packages.txt"

# Units whose state is recorded (those that exist).
UNITS="postfix dovecot nginx spampd opendkim opendmarc postgrey fail2ban nsd named munin-node cron
chrony rsyslog ssh.service ssh.socket ufw docker containerd unattended-upgrades"

php_fpm_units() {
	systemctl list-unit-files --no-legend --no-pager 'php*-fpm.service' 2> /dev/null | awk '{print $1}' || true
}

record_units() {
	local u e a
	for u in $UNITS $(php_fpm_units) $(systemctl list-unit-files --no-legend --no-pager 'mailinabox*' 2> /dev/null | awk '{print $1}'); do
		systemctl cat "$u" > /dev/null 2>&1 || continue
		e=$(systemctl is-enabled "$u" 2> /dev/null | head -n 1 || true)
		a=$(systemctl is-active "$u" 2> /dev/null | head -n 1 || true)
		echo "$u ${e:-unknown} ${a:-unknown}"
	done | sort -u
}

record_postconf() {
	local k
	for k in myhostname mydestination inet_interfaces inet_protocols relayhost smtpd_tls_security_level \
		smtp_tls_security_level smtpd_tls_protocols smtpd_tls_mandatory_protocols smtpd_milters non_smtpd_milters \
		milter_default_action smtpd_sender_restrictions smtpd_recipient_restrictions smtpd_relay_restrictions \
		smtpd_helo_restrictions virtual_transport virtual_mailbox_domains virtual_mailbox_maps virtual_alias_maps \
		message_size_limit mailbox_size_limit recipient_delimiter smtputf8_enable; do
		printf '%s = %s\n' "$k" "$(postconf -h "$k" 2> /dev/null || echo '(unknown)')"
	done
}

record_doveconf() {
	local k v
	for k in log_path protocols ssl_min_protocol auth_mechanisms mail_driver mail_path mail_location mail_home \
		postmaster_address recipient_delimiter lmtp_save_to_detail_mailbox first_valid_uid; do
		# Dovecot 2.4 prints lists (protocols) one item per line.
		if v=$(doveconf -h "$k" 2> /dev/null); then printf '%s = %s\n' "$k" "$(paste -sd, - <<< "$v" | sed 's/,/, /g')"; fi
	done
}

record_status_checks() { # DIR
	local d=$1
	if [ -x "$MIAB_DIR/management/status_checks.py" ]; then
		(cd "$MIAB_DIR" && umask 022 && timeout 900 management/status_checks.py) > "$d/status-full.txt" 2>&1 < /dev/null || true
		# The error (✖) and warning (?) lines; numbers vary (days to expiry...).
		grep -E '^[[:space:]]*(✖|\?)' "$d/status-full.txt" | sed -E 's/^[[:space:]]+//; s/[0-9]+/N/g' | sort > "$d/status.txt" || true
	else
		echo "(no $MIAB_DIR/management/status_checks.py)" > "$d/status.txt"
	fi
}

record_nextcloud() {
	if [ -f /usr/local/lib/owncloud/occ ]; then
		(umask 022 && timeout 120 runuser -u www-data -- php /usr/local/lib/owncloud/occ status --no-ansi < /dev/null 2>&1) \
			| sed -E 's/^[[:space:]]*-[[:space:]]*//' | grep -v '^$' || true
	else
		echo "(Nextcloud not installed)"
	fi
}

record_munin() {
	grep -E '^[[:space:]]*contacts?[[:space:]]|^[[:space:]]*contact\.' /etc/munin/munin.conf 2> /dev/null | sed -E 's/^[[:space:]]+//' || true
	# The values that are not ok (a new warning after the update stands out).
	grep -E ';state (warning|critical|unknown)$' /var/lib/munin/limits 2> /dev/null | awk -F';' '{print "not ok: " $3 " " $4 " " $5}' | sort || true
	if tail -n 200 /var/log/munin/munin-limits.log 2> /dev/null | grep -q 'Missing configuration options for contact'; then
		echo "munin-limits.log: \"Missing configuration options for contact\" in its last 200 lines"
	fi
}

# /var/lib/munin/limits: "group;host;plugin;field;state ok|warning|critical|unknown".
record_munin_limits() {
	grep -E ';state [a-z]+$' /var/lib/munin/limits 2> /dev/null | awk '{print $NF}' | sort | uniq -c | awk '{print "state " $2 " " $1}' || true
}

record_crontabs() {
	local f
	{ crontab -l -u root 2> /dev/null || echo "(no crontab for root)"; } | sed 's/^/root crontab: /'
	for f in /etc/cron.d/* /var/spool/cron/crontabs/*; do
		[ -f "$f" ] || continue
		echo "$f $(sha256sum < "$f" | cut -c1-16)"
	done
}

record_mailname() {
	echo "mailname: $(cat /etc/mailname 2> /dev/null || echo '-')"
	echo "hostname -f: $(hostname -f 2> /dev/null || echo '-')"
	echo "PRIMARY_HOSTNAME: $PRIMARY_HOSTNAME"
	grep -E '^127\.0\.1\.1[[:space:]]' /etc/hosts 2> /dev/null | sed 's/^/hosts: /' || true
}

record_dropins() {
	local f
	for f in /etc/systemd/system/*.d/*.conf; do
		[ -f "$f" ] || continue
		echo "$f $(sha256sum < "$f" | cut -c1-16)"
	done
}

# Without the ports of the ephemeral range (containerd's random local port).
# Of the processes that hold a socket (Postfix's master and its smtpd
# children...), the first name in sort order: the master's, which stays.
record_listening() {
	ss -Hltnp 2> /dev/null | awk '{
		proc = "~"; rest = $0
		while (match(rest, /\(\("[^"]+"|\),\("[^"]+"/)) {
			name = substr(rest, RSTART, RLENGTH); sub(/^[(),]*"/, "", name); sub(/"$/, "", name)
			if (name < proc) proc = name
			rest = substr(rest, RSTART + RLENGTH)
		}
		if (proc == "~") proc = "-"
		port = $4; sub(/.*:/, "", port)
		if (port + 0 < 32768) print "tcp " $4 " " proc
	}' | sort -u || true
}

record_conf() {
	sed -E '/^[[:space:]]*(#|$)/d; s/^([A-Za-z0-9_]*(PASS|SECRET|TOKEN|KEY)[A-Za-z0-9_]*)=.*/\1=***/' /etc/mailinabox.conf 2> /dev/null | sort || true
}

record_packages() {
	dpkg-query -W -f='${binary:Package} ${Version}\n' postfix dovecot-core nginx 'php*-fpm' spampd spamassassin opendkim \
		opendmarc postgrey fail2ban nsd bind9 munin munin-node duplicity openssh-server 2> /dev/null | awk 'NF == 2' | sort || true
}

# The backup target as Mail-in-a-Box reads it (unmasked; never printed).
# management/backup.py reads custom.yaml with rtyaml, so quoted and unquoted
# values work; without its Python environment, a plain parse.
backup_target() {
	local t py=/usr/local/lib/mailinabox/env/bin/python
	if [ -x "$py" ] && [ -f "$MIAB_DIR/management/backup.py" ]; then
		if t=$(cd "$MIAB_DIR/management" && "$py" -c 'import backup, utils
print(backup.get_backup_config(utils.load_environment())["target"])' 2> /dev/null); then
			echo "${t#file://"$STORAGE_ROOT"/backup/encrypted}" | sed 's|^$|local|'
			return 0
		fi
	fi
	t=$(sed -nE "s/^target:[[:space:]]*['\"]?([^'\"[:space:]]*)['\"]?[[:space:]]*$/\1/p" "$STORAGE_ROOT/backup/custom.yaml" 2> /dev/null | head -n 1 || true)
	echo "${t:-local}"
}

# The target without user names and passwords (B2 and S3 URLs carry keys).
masked_target() {
	sed -E 's#^([a-z0-9+]+://)[^@/]*@#\1***@#' <<< "$1"
}

record_backup() {
	local t
	t=$(backup_target)
	echo "target: $(masked_target "$t")"
	echo "secret_key.txt: $([ -r "$STORAGE_ROOT/backup/secret_key.txt" ] && echo present || echo missing)"
}

record_queue() {
	local n
	n=$(postqueue -j 2> /dev/null | wc -l || true)
	echo "messages in the queue: ${n:-?}"
	postqueue -j 2> /dev/null | sed -nE 's/.*"queue_name": *"([a-z]+)".*/\1/p' | sort | uniq -c | awk '{print "queue " $2 " " $1}' || true
}

record_state() { # DIR
	local d=$1
	rm -rf "$d"
	mkdir -m 700 "$d"
	date -u +%s > "$d/time.txt"
	date -u +%FT%TZ >> "$d/time.txt"
	{
		echo "miab $(git -C "$MIAB_DIR" describe --tags --always 2> /dev/null || echo unknown)"
		echo "origin $(git -C "$MIAB_DIR" remote get-url origin 2> /dev/null || echo unknown)"
		echo "ubuntu $(. /etc/os-release 2> /dev/null && echo "${VERSION_ID:-unknown}")"
		echo "storage version $(cat "$STORAGE_ROOT/mailinabox.version" 2> /dev/null || echo unknown)"
	} > "$d/version.txt"
	say "  version, units..."
	record_units > "$d/units.txt"
	systemctl --failed --no-legend --plain --no-pager 2> /dev/null | awk '{print $1}' | sort > "$d/failed.txt" || true
	record_queue > "$d/queue.txt"
	say "  Postfix, Dovecot..."
	record_postconf > "$d/postconf.txt"
	record_doveconf > "$d/doveconf.txt"
	{ doveconf -n 2>&1 > /dev/null | sed 's/^/doveconf: /' || true; } > "$d/config-warnings.txt"
	{ postconf -n 2>&1 > /dev/null | sed 's/^/postconf: /' || true; } >> "$d/config-warnings.txt"
	record_nextcloud > "$d/nextcloud.txt"
	record_munin > "$d/munin.txt"
	record_munin_limits > "$d/munin-limits.txt"
	if command -v docker > /dev/null; then
		docker ps -a --format '{{.Names}} {{.Image}} {{.State}}' 2> /dev/null | sort > "$d/docker.txt" || true
	else
		echo "(no docker)" > "$d/docker.txt"
	fi
	record_crontabs > "$d/crontabs.txt"
	record_mailname > "$d/mailname.txt"
	fail2ban-client status 2> /dev/null | sed -n 's/.*Jail list:[[:space:]]*//p' | tr ',' '\n' | sed 's/^[[:space:]]*//; /^$/d' \
		| sort | sed 's/^/jail /' > "$d/fail2ban.txt" || true
	record_dropins > "$d/dropins.txt"
	record_listening > "$d/listening.txt"
	record_conf > "$d/mailinabox-conf.txt"
	record_packages > "$d/packages.txt"
	record_backup > "$d/backup.txt"
	say "  status checks (a minute or two)..."
	record_status_checks "$d"
}

summary_of() { # DIR
	local d=$1 n
	say "Version:        $(sed -n 's/^miab //p' "$d/version.txt") ($(sed -n 's/^origin //p' "$d/version.txt"))"
	n=$(grep -c . "$d/failed.txt" || true)
	say "Failed units:   ${n:-0}$( [ "${n:-0}" = 0 ] || echo " ($(tr '\n' ' ' < "$d/failed.txt"))")"
	say "Status checks:  $(grep -c '^✖' "$d/status.txt" || true) errors, $(grep -c '^?' "$d/status.txt" || true) warnings"
	say "Mail queue:     $(sed -n 's/^messages in the queue: //p' "$d/queue.txt")"
}

# ---------------------------------------------------------------------------
# Log audit (tests/fork/log-audit.sh).

# A log-audit.sh that knows --baseline (rc7 and later), with its allowlists
# next to it: of this checkout, of /root/mailinabox, or downloaded.
log_audit_path() {
	local d f
	for d in "$SELF_REPO" "$MIAB_DIR"; do
		f=$d/tests/fork/log-audit.sh
		if [ -n "$d" ] && [ -f "$f" ] && grep -q -- '--baseline' "$f" && [ -f "$d/tests/fork/log-audit-allow-internet.txt" ]; then
			echo "$f"
			return 0
		fi
	done
	for f in log-audit.sh log-audit-allow.txt log-audit-allow-internet.txt; do
		fork_file "tests/fork/$f" > /dev/null || return 1
	done
	echo "$RUN_DIR/fetched/tests/fork/log-audit.sh"
}

run_log_audit() { # OUT_PREFIX SINCE [--baseline FILE]
	local out=$1 since=$2 la rc=0 extra=()
	shift 2
	la=$(log_audit_path) || { warn "Could not get tests/fork/log-audit.sh; no log audit."; return 2; }
	if [ -n "$OPT_INTERNET" ]; then extra+=(--internet); fi
	local f
	for f in "${OPT_ALLOW_EXTRA[@]+"${OPT_ALLOW_EXTRA[@]}"}"; do extra+=(--allow-extra "$f"); done
	say "Log audit since $since ($la)..."
	bash "$la" --since "$since" "${extra[@]+"${extra[@]}"}" "$@" --json "$out.json" > "$out.txt" 2>&1 || rc=$?
	if [ "$rc" -ge 2 ]; then
		warn "The log audit failed (exit code $rc):"
		sed 's/^/  /' "$out.txt" >&2
		return 2
	fi
	grep -E '^(RESULT|baseline):' "$out.txt" | sed 's/^/  /' || true
	if [ "$rc" = 1 ]; then
		say "  New message classes (details in $out.txt):"
		sed -n '/^UNKNOWN (/,/^$/p' "$out.txt" | grep -E '^  \[' | head -n 30 | sed 's/^  /    /' || true
	fi
	return "$rc"
}

# ---------------------------------------------------------------------------
# before / after

do_before() {
	init_state_root
	new_run_dir
	exec > >(tee -a "$RUN_DIR/update-check.log") 2>&1
	section "State before the update: $RUN_DIR/before"
	record_state "$RUN_DIR/before"
	say
	summary_of "$RUN_DIR/before"
	say
	run_log_audit "$RUN_DIR/before/log-audit" "${OPT_SINCE:-24 hours ago}" || true
	say
	say "Recorded in $RUN_DIR/before. Next: $SCRIPT_NAME backup, then the update, then $SCRIPT_NAME after."
}

# Compares before/ and after/ with the rules of tools/expected-changes/*.txt
# (their format is in the header of each file).
compare_states() { # BEFORE AFTER RULES...
	python3 -I - "$@" <<'PY'
import collections, os, re, sys

before, after, rule_files = sys.argv[1], sys.argv[2], sys.argv[3:]
INFO = set(os.environ["UC_INFO_FILES"].split())
SKIP = {"time.txt", "status-full.txt", "log-audit.json", "log-audit.txt", "changes.txt"}

rules = []
for path in rule_files:
    for n, raw in enumerate(open(path, encoding="utf-8"), 1):
        line = raw.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        spec, _, reason = line.partition(" # ")
        parts = spec.strip().split(None, 2)
        if len(parts) != 3 or parts[1] not in ("+", "-", "~") or not reason.strip():
            print("%s:%d: want FILE +|-|~ REGEX # REASON" % (path, n), file=sys.stderr)
            sys.exit(2)
        try:
            rx = re.compile(parts[2])
        except re.error as e:
            print("%s:%d: bad regex: %s" % (path, n, e), file=sys.stderr)
            sys.exit(2)
        rules.append({"file": parts[0], "sign": parts[1], "re": rx, "reason": reason.strip(),
                      "src": "%s:%d" % (os.path.basename(path), n), "hits": 0})

def lines(p):
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            return [l.rstrip("\n") for l in f if l.strip()]
    except OSError:
        return None

names = sorted(set(os.listdir(before)) | set(os.listdir(after)))
expected, unexpected, info, missing = [], [], [], []
for name in names:
    if name in SKIP or not name.endswith(".txt"):
        continue
    b, a = lines(os.path.join(before, name)), lines(os.path.join(after, name))
    if b is None or a is None:
        missing.append("%s (only %s)" % (name, "after" if b is None else "before"))
        continue
    gone, new = collections.Counter(b) - collections.Counter(a), collections.Counter(a) - collections.Counter(b)
    changes = [("-", l) for l in sorted(gone.elements())] + [("+", l) for l in sorted(new.elements())]
    for sign, l in changes:
        if name in INFO:
            info.append((name, sign, l, ""))
            continue
        for r in rules:
            if r["file"] in (name, "*") and r["sign"] in (sign, "~") and r["re"].search(l):
                r["hits"] += 1
                expected.append((name, sign, l, "%s (%s)" % (r["reason"], r["src"])))
                break
        else:
            unexpected.append((name, sign, l, ""))

w = sys.stdout.write
def show(title, items):
    w("%s (%d):\n" % (title, len(items)))
    for name, sign, l, why in items:
        w("  %-20s %s %s\n" % (name, sign, l[:300]))
        if why:
            w("  %-20s   expected: %s\n" % ("", why))
show("UNEXPECTED changes", unexpected)
show("EXPECTED changes", expected)
show("Changes of values that change by themselves (not judged)", info)
if missing:
    w("Recorded only once (not compared): %s\n" % ", ".join(missing))
w("RESULT: %s - %d unexpected, %d expected changes\n" % ("OK" if not unexpected else "CHANGED", len(unexpected), len(expected)))
sys.exit(1 if unexpected else 0)
PY
}

# "v78-r2604.0-rc7-3-gabc1234" -> "v78-r2604.0-rc7"
release_of() { sed -nE 's/^miab (v[0-9][^ ]*)$/\1/p' "$1/version.txt" | sed -E 's/-[0-9]+-g[0-9a-f]+$//'; }

# Is version A older than version B? Final releases come after their rcs.
version_lt() { # A B
	local a=${1#v} b=${2#v}
	dpkg --compare-versions "${a//-rc/~rc}" lt "${b//-rc/~rc}" 2> /dev/null
}

# The expected-change lists of the releases after BEFORE up to AFTER, and
# any.txt (what every update changes).
expected_rule_files() { # BEFORE_VERSION AFTER_VERSION
	local from=$1 to=$2 d f v seen=" " any=
	local dirs=()
	if [ -n "$SELF_REPO" ]; then dirs+=("$SELF_REPO/tools/expected-changes"); fi
	dirs+=("$MIAB_DIR/tools/expected-changes")
	# The list of the new release itself, if no checkout has it.
	if [ -n "$to" ] && [ ! -f "${dirs[0]}/$to.txt" ] && [ ! -f "$MIAB_DIR/tools/expected-changes/$to.txt" ]; then
		if f=$(fork_file "tools/expected-changes/$to.txt" 2> /dev/null); then dirs+=("$(dirname "$f")"); else rm -f "$f"; fi
	fi
	for d in "${dirs[@]}"; do
		if [ -z "$any" ] && [ -f "$d/any.txt" ]; then
			any=$d/any.txt
			echo "$any"
		fi
		for f in "$d"/v*.txt; do
			[ -f "$f" ] || continue
			v=$(basename "$f" .txt)
			[[ $seen == *" $v "* ]] && continue
			if [ -n "$from" ] && ! version_lt "$from" "$v"; then continue; fi
			if [ -n "$to" ] && version_lt "$to" "$v"; then continue; fi
			seen+="$v "
			echo "$f"
		done
	done
}

do_after() {
	init_state_root
	pick_run_dir need-before
	exec > >(tee -a "$RUN_DIR/update-check.log") 2>&1
	section "State after the update: $RUN_DIR/after"
	record_state "$RUN_DIR/after"
	say
	summary_of "$RUN_DIR/after"
	local from to rules=() f rc=0 arc=0
	from=$(release_of "$RUN_DIR/before")
	to=$(release_of "$RUN_DIR/after")
	while IFS= read -r f; do rules+=("$f"); done < <(expected_rule_files "$from" "$to")
	section "Changes from ${from:-?} to ${to:-?}"
	if [ ${#rules[@]} = 0 ]; then
		say "No list of expected changes for these versions (tools/expected-changes/): every change is unexpected."
	else
		say "Expected changes from: $(printf '%s ' "${rules[@]}")"
	fi
	UC_INFO_FILES=$INFO_FILES compare_states "$RUN_DIR/before" "$RUN_DIR/after" "${rules[@]+"${rules[@]}"}" \
		| tee "$RUN_DIR/after/changes.txt" || rc=$?
	[ "$rc" -le 1 ] || die "Could not compare the states (exit code $rc, see above)."
	section "Log audit of the update"
	local since
	since=${OPT_SINCE:-@$(head -n 1 "$RUN_DIR/before/time.txt")}
	if [ -f "$RUN_DIR/before/log-audit.json" ]; then
		run_log_audit "$RUN_DIR/after/log-audit" "$since" --baseline "$RUN_DIR/before/log-audit.json" || arc=$?
	else
		warn "No log audit from before ($RUN_DIR/before/log-audit.json); without a baseline."
		run_log_audit "$RUN_DIR/after/log-audit" "$since" || arc=$?
	fi
	say
	if [ "$rc" = 0 ] && [ "$arc" = 0 ]; then
		say "RESULT: OK - no unexpected change, no new log message class. Next: $SCRIPT_NAME mailcheck"
		return 0
	fi
	say "RESULT: look at the unexpected changes ($RUN_DIR/after/changes.txt) and the new log"
	say "message classes ($RUN_DIR/after/log-audit.txt). Next: $SCRIPT_NAME mailcheck"
	return 1
}

# ---------------------------------------------------------------------------
# backup

# gpg with a home of its own (no agent or keyring of root's).
gpg_enc() { # OUT (reads stdin)
	gpg --homedir "$GPG_HOME" --batch --yes --quiet --pinentry-mode loopback \
		--passphrase-file "$STORAGE_ROOT/backup/secret_key.txt" --symmetric --cipher-algo AES256 -o "$1"
}

# tar of PATHS (relative to /) | gpg. tar's exit code 1 (a file changed while
# it was read: logs, the live Nextcloud) is accepted.
tar_enc() { # OUT DIR PATHS...
	local out=$1 dir=$2 st
	shift 2
	set +o pipefail
	tar -C "$dir" --warning=no-file-changed --warning=no-file-removed -czf - -- "$@" | gpg_enc "$out"
	st=("${PIPESTATUS[@]}")
	set -o pipefail
	[ "${st[0]}" -le 1 ] || die "tar failed (exit code ${st[0]}) for $out."
	[ "${st[1]}" = 0 ] || die "gpg failed (exit code ${st[1]}) for $out."
}

valid_name() { [[ $1 =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]]; }

upload_rsync() { # URL DIR (copies DIR/*.gpg and SHA256SUMS)
	local url=$1 dir=$2 rest hostpart userhost port=22 path dest rsh out
	rest=${url#rsync://}
	hostpart=${rest%%/*}
	if [[ $rest == */* ]]; then path=${rest#*/}; else path=; fi
	userhost=$hostpart
	if [[ $hostpart =~ ^(.*):([0-9]+)$ ]]; then
		userhost=${BASH_REMATCH[1]}
		port=${BASH_REMATCH[2]}
	fi
	path=${path%/}
	dest=${path:-mailinabox}-system/update-check-${RUN_DIR##*/}
	# The target comes from custom.yaml below $STORAGE_ROOT, which the
	# user-data account can replace: nothing of it may reach ssh or rsync as
	# an option (a leading "-") or as shell syntax (B102).
	[[ $dest =~ ^[A-Za-z0-9._/~+][A-Za-z0-9._/~+-]*$ ]] || die "Unexpected characters in the backup path '$path'. Use --no-upload and copy $dir yourself."
	[[ $userhost =~ ^[A-Za-z0-9_][A-Za-z0-9._-]*(@[A-Za-z0-9_][A-Za-z0-9._-]*)?$ ]] || die "Unexpected characters in the backup host '$userhost'. Use --no-upload."
	[ -f /root/.ssh/id_rsa_miab ] || die "/root/.ssh/id_rsa_miab (the backup SSH key) is missing."
	local ssh=(ssh -p "$port" -i /root/.ssh/id_rsa_miab -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=30)
	rsh="ssh -p $port -i /root/.ssh/id_rsa_miab -oBatchMode=yes -oStrictHostKeyChecking=accept-new -oConnectTimeout=30"
	say "Copying to $userhost:$dest/ (port $port)..."
	# One command, no shell syntax: restricted shells (e.g. SFTP/rsync-only storage accounts) run it as well.
	"${ssh[@]}" -- "$userhost" "mkdir -p $dest" < /dev/null || die "Could not create $dest on $userhost."
	(cd "$dir" && rsync -t --partial -e "$rsh" ./*.gpg SHA256SUMS "$userhost:$dest/" < /dev/null) \
		|| die "Could not copy the archive to $userhost:$dest/."
	out=$(cd "$dir" && rsync -anc --itemize-changes -e "$rsh" ./*.gpg SHA256SUMS "$userhost:$dest/" < /dev/null) \
		|| die "Could not compare the copy on $userhost:$dest/."
	[ -z "$out" ] || die "The copy on $userhost:$dest/ differs from the archive here:
$out"
	say "Verified: the copy on $userhost:$dest/ is identical (rsync checksums)."
	echo "$userhost:$dest/ (port $port)" > "$dir/uploaded-to.txt"
}

do_backup() {
	init_state_root
	pick_run_dir
	if [ -z "$RUN_DIR" ]; then new_run_dir; fi
	exec > >(tee -a "$RUN_DIR/update-check.log") 2>&1
	local key=$STORAGE_ROOT/backup/secret_key.txt target out=$RUN_DIR/backup paths=() p n v c
	[ -r "$key" ] || die "$key is missing; cannot encrypt."
	target=$(backup_target)
	for p in "${OPT_DOCKER_DIRS[@]+"${OPT_DOCKER_DIRS[@]}"}"; do
		[[ $p == /* ]] && [ -d "$p" ] && [ ! -L "$p" ] || die "--docker-dir $p: not an absolute path of a directory."
		[[ $p =~ ^/[A-Za-z0-9._/+-]+$ ]] || die "--docker-dir $p: unexpected characters."
	done
	for v in "${OPT_VOLUMES[@]+"${OPT_VOLUMES[@]}"}"; do
		valid_name "$v" || die "--docker-volume $v: not a volume name."
		docker volume inspect "$v" > /dev/null 2>&1 || die "There is no Docker volume $v."
	done
	for c in "${OPT_POSTGRES[@]+"${OPT_POSTGRES[@]}"}"; do
		valid_name "$c" || die "--postgres $c: not a container name."
		[ "$(docker inspect -f '{{.State.Running}}' "$c" 2> /dev/null || true)" = true ] || die "The container $c does not run."
	done

	section "Mail-in-a-Box backup"
	if [ -n "$OPT_NO_MIAB_BACKUP" ]; then
		say "Skipped (--no-miab-backup)."
	elif [ "$target" = off ]; then
		say "Backups are turned off (System > Backup Status): no Mail-in-a-Box backup."
	else
		[ -x "$MIAB_DIR/management/backup.py" ] || die "$MIAB_DIR/management/backup.py is missing (or use --no-miab-backup)."
		if pgrep -f 'management/backup\.py' > /dev/null; then
			die "A Mail-in-a-Box backup is running already. Wait until it is finished and run this again."
		fi
		say "management/backup.py to $(masked_target "$target") (it stops Postfix, Dovecot, postgrey and PHP for its run)..."
		local started rc=0
		started=$(date +%s)
		(cd "$MIAB_DIR" && umask 022 && management/backup.py) < /dev/null || rc=$?
		[ "$rc" = 0 ] || die "The Mail-in-a-Box backup failed (exit code $rc, see above)."
		say "Done ($(($(date +%s) - started)) s)."
	fi

	section "System archive: $out"
	rm -rf "$out"
	mkdir -m 700 "$out" "$out/meta"
	GPG_HOME=$out/gnupg
	mkdir -m 700 "$GPG_HOME"
	trap 'gpgconf --homedir "$GPG_HOME" --kill all > /dev/null 2>&1 || true' EXIT
	dpkg --get-selections > "$out/meta/dpkg-selections.txt" 2> /dev/null || true
	dpkg -l > "$out/meta/dpkg-l.txt" 2> /dev/null || true
	doveconf -n > "$out/meta/doveconf-n.txt" 2>&1 || true
	postconf -n > "$out/meta/postconf-n.txt" 2> /dev/null || true
	systemctl list-unit-files --no-legend --no-pager > "$out/meta/unit-files.txt" 2> /dev/null || true
	git -C "$MIAB_DIR" describe --tags --always > "$out/meta/miab-version.txt" 2> /dev/null || true
	for p in etc root/mailinabox var/spool/cron var/lib/z-push var/lib/munin usr/local/lib/owncloud; do
		if [ -e "/$p" ]; then paths+=("$p"); fi
	done
	for p in "${OPT_DOCKER_DIRS[@]+"${OPT_DOCKER_DIRS[@]}"}"; do paths+=("${p#/}"); done
	paths+=("${out#/}/meta")
	n=$(du -scb "${paths[@]/#//}" 2> /dev/null | tail -n 1 | cut -f1 || echo 0)
	local avail
	avail=$(df -B1 --output=avail "$out" | tail -n 1 | tr -d ' ')
	[ "${avail:-0}" -gt "$n" ] || die "Not enough space in $STATE_ROOT: $(human "$avail") free, the archive takes up to $(human "$n")."
	say "Archiving$(printf ' /%s' "${paths[@]:0:${#paths[@]}-1}") ($(human "$n") before compression)..."
	tar_enc "$out/system.tar.gz.gpg" / "${paths[@]}"
	if [ ${#OPT_VOLUMES[@]} -gt 0 ]; then
		local mp vols=() vdir=
		for v in "${OPT_VOLUMES[@]}"; do
			mp=$(docker volume inspect -f '{{.Mountpoint}}' "$v")
			[ -d "$mp" ] && [ ! -L "$mp" ] || die "The mount point of the volume $v ($mp) is not a directory."
			if [ -z "$vdir" ]; then vdir=$(dirname "$mp"); fi
			[ "$(dirname "$mp")" = "$vdir" ] || die "The Docker volumes are in different directories; archive them one by one."
			vols+=("$(basename "$mp")")
		done
		say "Archiving the Docker volumes ${OPT_VOLUMES[*]}..."
		tar_enc "$out/docker-volumes.tar.gz.gpg" "$vdir" "${vols[@]}"
	fi
	for c in "${OPT_POSTGRES[@]+"${OPT_POSTGRES[@]}"}"; do
		say "pg_dump of the database of $c..."
		set +o pipefail
		# shellcheck disable=SC2016 # expanded inside the container
		docker exec "$c" sh -c 'exec pg_dump -U "$POSTGRES_USER" -Fc "${POSTGRES_DB:-$POSTGRES_USER}"' < /dev/null \
			| gpg_enc "$out/postgres-$c.dump.gpg"
		local prc=("${PIPESTATUS[@]}")
		set -o pipefail
		[ "${prc[0]}" = 0 ] || die "pg_dump in $c failed (exit code ${prc[0]})."
		[ "${prc[1]}" = 0 ] || die "gpg failed for the dump of $c."
	done
	gpgconf --homedir "$GPG_HOME" --kill all > /dev/null 2>&1 || true
	rm -rf "$GPG_HOME"
	(cd "$out" && sha256sum ./*.gpg > SHA256SUMS)
	say "Encrypted (gpg AES256, passphrase: the first line of $key):"
	(cd "$out" && for f in ./*.gpg; do printf '  %s %s\n' "${f#./}" "$(human "$(stat -c %s "$f")")"; done)
	rm -rf "$out/meta"

	section "Copy"
	if [ -n "$OPT_NO_UPLOAD" ]; then
		say "The archive stays in $out (--no-upload). Copy it off this machine yourself."
	else
		case "$target" in
			rsync://*) upload_rsync "$target" "$out" ;;
			*)
				(cd "$out" && sha256sum -c --quiet SHA256SUMS) || die "The checksums of $out do not match."
				say "The backups go to $(masked_target "$target"); this tool copies only to rsync targets."
				say "The archive stays in $out (checksums verified). Copy it off this machine yourself."
				;;
		esac
	fi
	say
	say "To decrypt later: gpg --batch --pinentry-mode loopback --passphrase-file secret_key.txt -d system.tar.gz.gpg | tar -xzf -"
	say "Next: the update, then $SCRIPT_NAME after."
}

# ---------------------------------------------------------------------------
# mailcheck

valid_address() { [[ $1 =~ ^[A-Za-z0-9._%+=-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$ ]]; }

# Reads mail.log from OFFSET for the test mail (and the first poll returns the
# result of the delivery); fetches the stored copy that came back. Prints
# KEY=VALUE lines; FOUND=1 when the mail is back.
mailcheck_poll() { # TOKEN PROBE OFFSET SINCE_EPOCH
	python3 -I - "$@" <<'PY'
import json, os, re, subprocess, sys, time

token, probe, offset, since = sys.argv[1], sys.argv[2].lower(), int(sys.argv[3]), int(sys.argv[4])
out = {}

# Outbound: the queue ID of the mail (cleanup's message-id line), then its delivery.
try:
    with open("/var/log/mail.log", "rb") as f:
        if os.fstat(f.fileno()).st_size >= offset:
            f.seek(offset)
        log = f.read().decode("utf-8", "replace").splitlines()
except OSError:
    log = []
qid = None
for l in log:
    m = re.search(r" postfix/cleanup\[\d+\]: ([0-9A-Za-z]+): message-id=<%s@" % token, l)
    if m:
        qid = m.group(1)
        break
if qid:
    out["QID"] = qid
    for l in log:
        if (": %s: to=<" % qid) in l and probe in l.lower():
            m = re.search(r"relay=([^,]+),.* status=(\w+) \((.*)\)$", l)
            if m:
                out["OUT_STATUS"], out["OUT_RELAY"], out["OUT_TEXT"] = m.group(2), m.group(1), m.group(3)[:200]
        if (": %s: DKIM-Signature field added" % qid) in l:
            m = re.search(r"\(s=([^,]+), d=([^)]+)\)", l)
            out["OUT_DKIM"] = "d=%s, s=%s" % (m.group(2), m.group(1)) if m else "yes"

# Inbound: mail stored since the start that carries the token in its header
# (subject, Message-ID, In-Reply-To or References), whose Postfix hop here is
# a delivery over SMTP (port 25), not the local pickup of the test mail itself.
age = max(60, int(time.time()) - since + 60)
try:
    p = subprocess.run(["doveadm", "-f", "json", "fetch", "-A", "user mailbox uid hdr", "savedsince", "%dsecs" % age],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=120)
    msgs = json.loads(p.stdout.decode("utf-8", "replace") or "[]")
except (subprocess.SubprocessError, ValueError, OSError):
    msgs = []
for msg in msgs:
    hdr = msg.get("hdr", "")
    if token not in hdr:
        continue
    unfolded = re.sub(r"\r?\n[ \t]+", " ", hdr)
    received = [l[len("Received:"):].strip() for l in unfolded.splitlines() if l.lower().startswith("received:")]
    hop = next((r for r in received if "(Postfix" in r), "")
    if not hop or "from userid" in hop or re.search(r"\bwith (ESMTPSA|ESMTPA|LMTP)\b", hop):
        continue  # the test mail itself (or a submission), not one that came back
    out["FOUND"] = "1"
    out["IN_USER"], out["IN_MAILBOX"], out["IN_UID"] = msg.get("user", "?"), msg.get("mailbox", "?"), msg.get("uid", "?")
    m = re.match(r"from (\S+) \(([^)]*)\)\s+by \S+ \(Postfix\) with (\S+) id (\S+)", hop)
    if m:
        out["IN_FROM"] = "%s (%s)" % (m.group(1), m.group(2))
        out["IN_WITH"] = m.group(3)
        out["IN_QID"] = m.group(4).rstrip(";")
    for l in unfolded.splitlines():
        k = l.split(":", 1)[0].lower()
        if k == "x-spam-status":
            out["IN_SPAM"] = l.split(":", 1)[1].strip()[:120]
        elif k == "authentication-results":
            res = re.findall(r"\b(dkim|spf|dmarc)=(\w+)", l)
            if res:
                out["IN_AUTH"] = (out.get("IN_AUTH", "") + " " + " ".join("%s=%s" % r for r in res)).strip()
    break
if out.get("IN_QID"):
    for l in log:
        m = re.search(r" (postfix(?:/[a-z]+)*/smtpd)\[\d+\]: %s: client=(\S+)" % re.escape(out["IN_QID"]), l)
        if m:
            out["IN_SMTPD"] = m.group(1)
for k, v in out.items():
    print("%s=%s" % (k, v.replace("\n", " ")))
PY
}

do_mailcheck() {
	local probe=${OPT_PROBE:-$PROBE_ADDRESS} from=${OPT_FROM:-administrator@$PRIMARY_HOSTNAME} timeout=${OPT_TIMEOUT:-900}
	if [ -z "$probe" ]; then
		say "mailcheck: skipped (no probe address: set PROBE_ADDRESS=... in /etc/mailinabox.conf or use --probe)."
		return 0
	fi
	valid_address "$probe" || die "The probe address '$probe' does not look like a mail address."
	valid_address "$from" || die "The sender '$from' does not look like a mail address."
	[[ $timeout =~ ^[0-9]+$ ]] || die "--timeout wants seconds."
	init_state_root
	pick_run_dir
	if [ -z "$RUN_DIR" ]; then new_run_dir; fi
	exec > >(tee -a "$RUN_DIR/update-check.log") 2>&1
	local token offset start res k v n=0
	token=miabcheck$(od -An -N10 -tx1 /dev/urandom | tr -d ' \n')
	offset=$(stat -c %s /var/log/mail.log 2> /dev/null || echo 0)
	start=$(date +%s)
	section "Mail check: $from -> $probe"
	say "Token: $token (timeout $timeout s)"
	{
		echo "From: Mail-in-a-Box update check <$from>"
		echo "To: <$probe>"
		echo "Subject: Mail-in-a-Box update check $token"
		echo "Message-ID: <$token@$PRIMARY_HOSTNAME>"
		echo "Date: $(LC_ALL=C date -R)"
		echo "X-Miab-Test: 1"
		echo "MIME-Version: 1.0"
		echo "Content-Type: text/plain; charset=us-ascii"
		echo
		echo "This is a test mail of tools/update-check.sh on $PRIMARY_HOSTNAME (Mail-in-a-Box)."
		echo "The probe address forwards or answers it, and the box checks that it comes back."
		echo
		echo "Token: $token"
	} | /usr/sbin/sendmail -i -f "$from" -- "$probe" || die "sendmail failed."
	declare -A R=()
	local shown_out=
	while :; do
		res=$(mailcheck_poll "$token" "$probe" "$offset" "$start" || true)
		R=()
		while IFS='=' read -r k v; do [ -n "$k" ] && R[$k]=$v; done <<< "$res"
		if [ -n "${R[OUT_STATUS]:-}" ] && [ "$shown_out" != "${R[OUT_STATUS]}" ]; then
			say "$(date +%T) outbound: ${R[OUT_STATUS]} (relay ${R[OUT_RELAY]:-?})"
			shown_out=${R[OUT_STATUS]}
		fi
		[ -z "${R[FOUND]:-}" ] || break
		if [ "${R[OUT_STATUS]:-}" = bounced ]; then break; fi
		if [ $(($(date +%s) - start)) -ge "$timeout" ]; then break; fi
		n=$((n + 1))
		if [ $((n % 4)) = 0 ]; then say "$(date +%T) waiting for the mail to come back ($(($(date +%s) - start)) s)..."; fi
		sleep 15
	done
	local elapsed ok=1
	elapsed=$(($(date +%s) - start))
	say
	if [ -n "${R[OUT_STATUS]:-}" ]; then
		say "  outbound:  ${R[OUT_STATUS]}, relay ${R[OUT_RELAY]:-?}: ${R[OUT_TEXT]:-}"
	else
		say "  outbound:  no delivery of the test mail in mail.log (queue ID ${R[QID]:-not found})"
	fi
	say "             DKIM signature: ${R[OUT_DKIM]:-none logged}"
	if [ "${R[OUT_STATUS]:-}" != sent ]; then ok=; fi
	if [ -n "${R[FOUND]:-}" ]; then
		say "  inbound:   back after $elapsed s, from ${R[IN_FROM]:-?} with ${R[IN_WITH]:-?}${R[IN_SMTPD]:+ (${R[IN_SMTPD]}, port 25)}"
		say "  checks:    ${R[IN_AUTH]:-no Authentication-Results}"
		say "  spam:      ${R[IN_SPAM]:-no X-Spam-Status header (spam filter did not run)}"
		case "${R[IN_MAILBOX]}" in
			INBOX) say "  folder:    INBOX (no Sieve rule moved it)" ;;
			Spam) say "  folder:    Spam (moved by the spam filter's Sieve rule)" ;;
			*) say "  folder:    ${R[IN_MAILBOX]} (moved by a Sieve rule of the user)" ;;
		esac
		say "  storage:   stored for ${R[IN_USER]}, uid ${R[IN_UID]}"
		# Over port 25: Postfix's smtpd (not submission), or by the Received header
		# if mail.log has no line of it.
		case "${R[IN_SMTPD]:-}:${R[IN_WITH]:-}" in postfix/smtpd:* | :SMTP | :ESMTP | :ESMTPS | :UTF8SMTP | :UTF8SMTPS) ;; *) ok= ;; esac
		if [ -z "${R[IN_SPAM]:-}" ]; then ok=; fi
	else
		say "  inbound:   the mail did not come back within $elapsed s"
		ok=
	fi
	say
	if [ -n "$ok" ]; then
		say "RESULT: OK - mail goes out and comes back in over port 25, through the spam filter, and is stored."
		return 0
	fi
	say "RESULT: FAILED - see above, /var/log/mail.log (token $token) and the probe mailbox."
	return 1
}

# ---------------------------------------------------------------------------

main() {
	COMMAND='' OPT_DIR='' OPT_SINCE='' OPT_INTERNET='' OPT_NO_MIAB_BACKUP='' OPT_NO_UPLOAD=''
	OPT_PROBE='' OPT_FROM='' OPT_TIMEOUT=''
	OPT_ALLOW_EXTRA=() OPT_DOCKER_DIRS=() OPT_VOLUMES=() OPT_POSTGRES=()
	while [ $# -gt 0 ]; do
		case "$1" in
			before | backup | after | mailcheck)
				[ -z "$COMMAND" ] || die "Give one step (before, backup, after or mailcheck). See --help."
				COMMAND=$1
				shift
				;;
			--dir | --since | --allow-extra | --docker-dir | --docker-volume | --postgres | --probe | --from | --timeout)
				if [ $# -lt 2 ] || [ -z "$2" ]; then die "$1 needs a value. See --help."; fi
				case "$1" in
					--dir) OPT_DIR=$2 ;;
					--since) OPT_SINCE=$2 ;;
					--allow-extra) OPT_ALLOW_EXTRA+=("$(readlink -f -- "$2")") ;;
					--docker-dir) OPT_DOCKER_DIRS+=("${2%/}") ;;
					--docker-volume) OPT_VOLUMES+=("$2") ;;
					--postgres) OPT_POSTGRES+=("$2") ;;
					--probe) OPT_PROBE=$2 ;;
					--from) OPT_FROM=$2 ;;
					--timeout) OPT_TIMEOUT=$2 ;;
				esac
				shift 2
				;;
			--internet) OPT_INTERNET=1; shift ;;
			--no-miab-backup) OPT_NO_MIAB_BACKUP=1; shift ;;
			--no-upload) OPT_NO_UPLOAD=1; shift ;;
			-h | --help) usage; exit 0 ;;
			*) die "Unknown option $1. See --help." ;;
		esac
	done
	[ -n "$COMMAND" ] || { usage; exit 2; }
	[ "$(id -u)" = 0 ] || die "This must be run as root. Did you leave out sudo?"
	find_self_repo
	umask 077
	cd /
	load_conf
	if [ ! -d "$MIAB_DIR/.git" ] && [ -n "$SELF_REPO" ]; then MIAB_DIR=$SELF_REPO; fi
	case "$COMMAND" in
		before) do_before ;;
		backup) do_backup ;;
		after) do_after ;;
		mailcheck) do_mailcheck ;;
	esac
}

main "$@"
