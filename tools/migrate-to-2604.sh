#!/bin/bash
#########################################################
# Move a Mail-in-a-Box to a new machine running Ubuntu 26.04.
#
# Run this as root on the NEW machine, a fresh Ubuntu 26.04 install. Check
# first, then migrate (started from a terminal outside tmux or screen, it runs
# itself in the tmux session migrate-2604, see run_in_multiplexer):
#
#   /root/mailinabox/tools/migrate-to-2604.sh --check --from root@old.example.com
#   /root/mailinabox/tools/migrate-to-2604.sh --from root@old.example.com
#
# or without a checkout of this repository (like setup/bootstrap.sh):
#
#   curl -s https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/tools/migrate-to-2604.sh \
#     | sudo bash -s -- --from root@old.example.com
#
# Supported old boxes: official Mail-in-a-Box v60 or later on Ubuntu 22.04
# with Nextcloud 26 or later (v68+), and boxes that were release-upgraded in
# place to Ubuntu 24.04 and still run Mail-in-a-Box v7x.
#
# This does what upstream documents for moving a box ("restore your backup
# on a new machine, then run setup", https://mailinabox.email/maintenance.html#upgrade),
# in one command:
#
#  1. preflight    check both machines (also alone, with --check)
#  2. sync-live    rsync $STORAGE_ROOT while the old box keeps running
#                  (optional: --rehearse runs setup on that copy once)
#  3. stop-old     stop and mask (until reboot) the mail/web services, cron and
#                  the apt timers on the old box (asks first)
#  4. sync-final   wait until nothing uses $STORAGE_ROOT there, rsync the changes
#  5. prepare      /etc/mailinabox.conf with the new IPs, backups paused,
#                  ownership placeholders
#  6. setup        this fork's setup/start.sh, non-interactive
#  7. ownership    map file owners to this machine's user IDs
#  8. extras       Z-Push device state and munin graphs (outside $STORAGE_ROOT)
#  9. verify       compare keys and counts, status checks, next steps
#
# The data on the old box is never changed. Its services are only stopped
# and masked in /run, and "--rollback" starts them again. The state of a
# migration is kept in /root/migration, so the command can be run again after
# an interruption and continues where it stopped.
#
# See README-fork.md ("Migration from Mail-in-a-Box") and --help.
#########################################################

# Everything below is inside functions and the last line calls main, so a
# partially downloaded script (curl | bash) does nothing.

set -euo pipefail
set -E # the ERR trap (see on_err) also fires inside functions

STATE_DIR=${MIGRATE_STATE_DIR:-/root/migration}
STATE_FILE=$STATE_DIR/state
LOG_FILE=$STATE_DIR/migrate.log
MARKER=.migrate-to-2604
# Files that a copy replaces or deletes on this machine after it already ran
# as the mail server are kept below $STORAGE_ROOT/$OVERWRITTEN (same file system).
OVERWRITTEN=.migrate-overwritten
PARTIAL_DIR=.rsync-partial
# File owners that this machine does not know yet are parked at old ID + ID_OFFSET
# until setup has created the system users (see phase_prepare / phase_ownership).
ID_OFFSET=2000000000
DEFAULT_SOURCE=https://github.com/LM1337/Mail-in-a-box-26
# Raw files of the branch main (GitHub serves them from another host).
DEFAULT_RAW=https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main
DEFAULT_TAG=v78-r2604.0-rc4 # keep in sync with setup/bootstrap.sh
CLONE_DIR=/root/mailinabox
PHP_VER=8.5 # keep in sync with setup/functions.sh
QUIET_TIMEOUT=${MIGRATE_QUIET_TIMEOUT:-900}
# How long to wait for a Mail-in-a-Box backup on the old box (wait_backup_done).
BACKUP_WAIT=${MIGRATE_BACKUP_WAIT:-7200}
# Where --push-zones-to-old keeps the old box's own zone files (on the old box).
OLD_NSD_SAVE=/root/migrate-to-2604-nsd-orig
TMUX_SESSION=migrate-2604
# The environment variables this script and setup read (passed into that
# session); SSH_AUTH_SOCK for an SSH agent that logs in on the old box.
MUX_ENV=(MIGRATE_STATE_DIR MIGRATE_QUIET_TIMEOUT MIGRATE_BACKUP_WAIT MIGRATE_REEXEC TAG SOURCE SSH_AUTH_SOCK FTS NEXTCLOUD_SHARE_SCOPE)
MUX_TERM=

# Phases that are recorded in the state file, in order.
PHASES_SSH=(sync_live stop_old sync_final prepare setup ownership extras verify)
PHASES_BACKUP=(restore prepare setup ownership verify)

# The units on THIS machine that serve users or write to $STORAGE_ROOT. They
# are stopped (and masked in /run) before a copy into $STORAGE_ROOT once setup
# has run here, and on --rollback.
LOCAL_UNITS=(cron.service mailinabox.service nginx.service "php$PHP_VER-fpm.service" php8.2-fpm.service
	postfix.service postfix@-.service dovecot.socket dovecot.service spampd.service postgrey.service
	opendkim.service opendmarc.service munin.service munin-node.service)

declare -A OLD=() OLDFP=() NEWFP=() STATE_MEM=()
SSH_ARGS=()
SSH_TARGET=
NET_BLOCKERS=()
CHECK_BLOCKERS=()
VERIFY_PROBLEMS=()
CHECK_ONLY=
CHECK_TMP=
BACKUP_WAITED=
LOG_READY=
IN_DIE=
USER_STOPPED=
FAILED_CMD=
VERIFY_FAILED=
SESSION_CHECKED=
SELF=$CLONE_DIR/tools/migrate-to-2604.sh
SELF_FILE=

say() { echo "$*"; }
warn() { echo "WARNING: $*" >&2; }
die() {
	IN_DIE=1
	echo >&2
	echo "ERROR: $*" >&2
	exit 1
}
# A reason not to start the migration. --check collects them, otherwise stop.
blocker() {
	if [ -n "$CHECK_ONLY" ]; then
		CHECK_BLOCKERS+=("$*")
		echo "BLOCKER: $*" >&2
	else
		die "$*"
	fi
}
section() {
	echo
	echo "-----------------------------------------------"
	echo "$*"
	echo "-----------------------------------------------"
}
human() { numfmt --to=iec-i --suffix=B "${1:-0}" 2> /dev/null || echo "${1:-0} bytes"; }
fmt_dur() { # seconds -> "7 min" / "2 h 05 min"
	local m=$(((${1:-0} + 59) / 60))
	if [ "$m" -lt 60 ]; then echo "$m min"; else printf '%d h %02d min\n' $((m / 60)) $((m % 60)); fi
}

usage() {
	cat <<'EOF'
Usage: migrate-to-2604.sh --check --from [USER@]OLD_HOST [options]    (start here)
       migrate-to-2604.sh --from [USER@]OLD_HOST [options]
       migrate-to-2604.sh --from-backup DIR|URL --backup-key FILE [options]
       migrate-to-2604.sh --status [--verbose] | --check-old | --rollback
                          | --finish | --push-zones-to-old

Moves a Mail-in-a-Box (official v68 or later on Ubuntu 22.04, or a box
release-upgraded in place to Ubuntu 24.04) to THIS machine, a fresh Ubuntu
26.04 install. Run it as root on the new machine. The copy and setup take
hours, and a dropped SSH connection would stop them halfway: started from a
terminal outside tmux or screen, it runs itself in the tmux session
"migrate-2604" (it installs tmux if needed) and attaches to it. If the SSH
connection drops, log in again and run "sudo tmux attach -t migrate-2604".
The old machine's data is never changed; only its services are stopped for
the final copy, after you confirm. Running the command again continues an
interrupted migration.

Source (one of):
  --from [USER@]HOST      the old box, over SSH. USER defaults to root; a user
                          with passwordless sudo ("sudo -n") works as well.
  --from-backup DIR|URL   a Mail-in-a-Box backup (duplicity) instead, e.g. a
                          copy of the old /home/user-data/backup/encrypted
  --backup-key FILE       the old box's backup/secret_key.txt (--from-backup)

SSH:
  --ssh-key FILE          private key for the login on the old box
  --ssh-port PORT         SSH port of the old box (default 22)

New box (defaults: taken from the old box or detected):
  --hostname NAME         PRIMARY_HOSTNAME (default: the old box's)
  --public-ip IP          public IPv4 address of this machine
  --public-ipv6 IP        public IPv6 address of this machine. If this machine
                          has a public IPv6 address, setup always uses it (also
                          on later runs); to have no IPv6, remove it from the
                          machine instead.
  --private-ip IP         private IPv4 address (default: detected by setup)
  --private-ipv6 IP       private IPv6 address (default: detected by setup)
  --storage-root DIR      only with --from-backup (default /home/user-data)
  --keep-timezone         keep this machine's time zone (default: the old box's)

Steps:
  --check, --dry-run      only check both machines and show the plan, the
                          downtime estimate and what blocks the move. Changes
                          nothing (no state, no copy, no packages, no clone).
  --sync-only             only copy the data while the old box keeps running,
                          then stop. Repeat it to keep the copy fresh; run the
                          command without it for the switch-over.
  --rehearse              after the live copy, run setup once on that copy (the
                          old box keeps running): installs the packages ahead
                          of time and measures how long setup takes. The real
                          switch-over copies the data again and is shorter.
  --switch-over           needed together with --yes to stop the old box
                          without asking (see --yes)

Copy:
  --bwlimit KBPS          limit the live copy to KBPS KiB/s (not the final one)
  --compress              compress the rsync stream (slow links)
  --with-owncloud-backup  also copy owncloud-backup/ (copies from old Nextcloud
                          upgrades, not part of Mail-in-a-Box backups either)
  --skip-local-backups    do not copy backup/encrypted/ (local backups)
  --no-extras             do not copy Z-Push device state and munin graphs
  --skip-network-checks   stop the old box even though outbound port 25 is
                          blocked here or the new IP is on the Spamhaus list

Control:
  --yes                   do not ask for confirmation (unattended use). --yes
                          never starts the downtime on its own: use
                          "--sync-only --yes" for unattended copying, and add
                          --switch-over only if the old box may be stopped
                          unattended right after the live copy.
  --no-tmux               do not start a tmux session of its own (see above)
  --redo-from PHASE       run PHASE and the phases after it again:
                          sync-final, setup, extras or verify
  --status [--verbose]    show the state of the migration (--verbose: raw)
  --check-old             show whether anything runs again on the old box
  --rollback              start the old box's services again (and stop and
                          disable the mail and web services here, pause the
                          backups here)
  --finish                accept a final check with differences: resume the
                          backups here and mark the migration finished
  --push-zones-to-old     after the migration: let the old box's nsd serve this
                          box's DNS zones (new IPs) until the glue records have
                          propagated. The one change to files on the old box;
                          --rollback undoes it.
  -h, --help              show this help

Environment: SOURCE and TAG choose the repository and tag when the script
is run through curl, e.g.
  curl -s .../tools/migrate-to-2604.sh | sudo TAG=main bash -s -- --from root@old.example.com
MIGRATE_STATE_DIR (default /root/migration) holds the state, the log and the
copy of the old /etc. MIGRATE_QUIET_TIMEOUT (default 900) is how many seconds
to wait for processes that still use the data, MIGRATE_BACKUP_WAIT (default
7200) how many seconds to wait for a Mail-in-a-Box backup that runs on the old
box (e.g. the nightly one) before it is stopped.
EOF
}

# ---------------------------------------------------------------------------
# State file: KEY=VALUE lines. Values never contain newlines. With --check,
# values are only kept in memory.

state_get() {
	if [ -n "${STATE_MEM[$1]+x}" ]; then
		printf '%s\n' "${STATE_MEM[$1]}"
		return 0
	fi
	[ -f "$STATE_FILE" ] || return 0
	sed -n "s/^$1=//p" "$STATE_FILE" | tail -n 1
}

state_set() {
	if [ -n "$CHECK_ONLY" ]; then
		STATE_MEM[$1]=$2
		return 0
	fi
	local tmp
	tmp=$(mktemp "$STATE_DIR/.state.XXXXXX")
	{
		if [ -f "$STATE_FILE" ]; then grep -v "^$1=" "$STATE_FILE" || true; fi
		printf '%s=%s\n' "$1" "$2"
	} > "$tmp"
	mv "$tmp" "$STATE_FILE"
}

phase_is_done() { [ "$(state_get "PHASE_$1")" = "done" ]; }
phase_mark_done() { state_set "PHASE_$1" "done"; }

# Forget PHASE and all phases after it.
phases_reset_from() {
	local from=$1 p found=
	local -a list
	if [ "$(state_get SOURCE_MODE)" = backup ]; then list=("${PHASES_BACKUP[@]}"); else list=("${PHASES_SSH[@]}"); fi
	for p in "${list[@]}"; do
		if [ "$p" = "$from" ]; then found=1; fi
		if [ -n "$found" ]; then state_set "PHASE_$p" ""; fi
	done
	[ -n "$found" ] || die "Unknown phase $from."
}

old_box_is_down() {
	[ -f "$STATE_FILE" ] && [ "$(state_get SOURCE_MODE)" = ssh ] && phase_is_done stop_old && ! phase_is_done verify
}

# ---------------------------------------------------------------------------
# Error reporting. Every way out of the script with an error ends here: die,
# a failed command under set -e, Ctrl-C.

on_err() {
	# Remember the last failed command of the main shell for the exit message.
	if [ "$BASH_SUBSHELL" = 0 ]; then FAILED_CMD="line $1: $2"; fi
}

on_exit() {
	local rc=$?
	ssh_close
	if [ -n "$CHECK_TMP" ]; then rm -rf "$CHECK_TMP"; fi
	[ "$rc" != 0 ] || return 0
	[ -z "$CHECK_ONLY" ] || return 0
	{
		if [ -z "$IN_DIE" ]; then
			echo
			echo "ERROR: the migration stopped (exit code $rc)${FAILED_CMD:+ at $FAILED_CMD}."
		fi
		if [ -n "$LOG_READY" ] && [ -z "$VERIFY_FAILED" ] && [ -z "$USER_STOPPED" ]; then
			echo "The full output is in $LOG_FILE."
			echo "Fix the cause and run the command again; it continues where it stopped."
		fi
		if old_box_is_down; then
			echo
			echo "The old box is STOPPED (downtime). To bring it back: $SELF --rollback"
		fi
	} >&2
	return 0
}

# Ask on the terminal (also when the script came through curl | bash).
# "confirm always ..." asks even with --yes.
confirm() {
	if [ "$1" = always ]; then
		shift
	elif [ -n "$ASSUME_YES" ]; then
		return 0
	fi
	if ! (: < /dev/tty) 2> /dev/null; then
		die "There is no terminal to ask: $1 Run with --yes for unattended use."
	fi
	local answer=
	printf '\n%s [y/N] ' "$1" > /dev/tty
	read -r answer < /dev/tty || true
	if ! [[ $answer =~ ^[Yy]([Ee][Ss])?$ ]]; then
		IN_DIE=1 USER_STOPPED=1
		echo "Stopped. Nothing was changed by this step. Run the command again to continue." >&2
		exit 1
	fi
}

# Long phases must survive a dropped SSH connection. Keep in sync with
# tools/upgrade-in-place-to-2604.sh.
in_multiplexer() {
	[ -z "${TMUX:-}${STY:-}" ] || return 0
	# sudo drops TMUX and STY, so look at the parent processes as well.
	local p=$$ c
	while [ -n "$p" ] && [ "$p" -gt 1 ]; do
		c=$(cat "/proc/$p/comm" 2> /dev/null) || return 1
		case "$c" in tmux* | screen* | SCREEN* | byobu* | zellij | mosh-server) return 0 ;; esac
		p=$(awk '/^PPid:/ {print $2}' "/proc/$p/status" 2> /dev/null)
	done
	return 1
}

session_check() {
	[ -z "$SESSION_CHECKED" ] || return 0
	SESSION_CHECKED=1
	in_multiplexer && return 0
	# Started with nohup (SIGHUP ignored) or without a terminal (nothing to hang up).
	if trap -p HUP | grep -q "''"; then return 0; fi
	if ! (: < /dev/tty) 2> /dev/null; then return 0; fi
	if [ -n "$CHECK_ONLY" ] && [ -z "$NO_TMUX" ]; then
		if [ -z "$SELF_FILE" ]; then
			# Through curl | bash the run uses the copy of the release tag, which
			# may be older than this feature.
			say "Through curl | bash the command runs the copy of ${TAG:-$DEFAULT_TAG}. If that release does not"
			say "start tmux by itself yet, start the command inside tmux: tmux new -s $TMUX_SESSION"
			return 0
		fi
		say "Started from this terminal, the command runs itself in the tmux session $TMUX_SESSION"
		say "(tmux is installed if needed; reattach after a disconnect with: sudo tmux attach -t $TMUX_SESSION)."
		return 0
	fi
	warn "This does not run inside tmux or screen. If your SSH connection drops, the copy
or setup stops halfway (a Nextcloud upgrade stopped in the middle stays in maintenance mode).
Better: install tmux (apt-get install tmux) and run the command again without --no-tmux:
it then runs itself in tmux (reattach after a disconnect with: sudo tmux attach -t $TMUX_SESSION)."
	if [ -z "$CHECK_ONLY" ]; then confirm "Continue without tmux or screen?"; fi
}

# A command that changes something, started from a terminal outside tmux and
# screen, runs itself in a tmux session (or screen) of its own: a dropped SSH
# connection then only ends the terminal that is attached to it. Not with
# --no-tmux, --check or --resumed, not without a terminal (automation, nohup)
# and not without a script file. Needs tmux 3.0 or later (a command with
# arguments). Keep in sync with tools/upgrade-in-place-to-2604.sh.

mux_has() { # TOOL: is there a session named $TMUX_SESSION?
	case "$1" in
		tmux) tmux has-session -t "=$TMUX_SESSION" 2> /dev/null ;;
		# screen -ls exits with 1 even when it lists sessions (pipefail).
		screen) { screen -ls 2> /dev/null || true; } | grep -qE "^[[:space:]]+[0-9]+\.${TMUX_SESSION}[[:space:]]" ;;
	esac
}

# The process in the session's window: the shell of mux_start or of the
# resume unit.
mux_pane_pid() { # TOOL
	local p
	case "$1" in
		tmux) tmux list-panes -t "=$TMUX_SESSION" -F '#{pane_pid}' 2> /dev/null | head -n 1 ;;
		screen)
			p=$({ screen -ls 2> /dev/null || true; } | sed -nE "s/^[[:space:]]+([0-9]+)\.${TMUX_SESSION}[[:space:]].*/\1/p" | head -n 1)
			if [ -n "$p" ]; then pgrep -P "$p" | head -n 1; fi
			;;
	esac
}

# Is the session a window of this tool whose command has ended, so that it
# only waits for Enter? Its shell has no child process then.
mux_finished() { # TOOL
	local p
	p=$(mux_pane_pid "$1" || true)
	[ -n "$p" ] || return 1
	grep -qa 'Press Enter to close this window' "/proc/$p/cmdline" 2> /dev/null || return 1
	[ -z "$(pgrep -P "$p" || true)" ]
}

mux_kill() { # TOOL
	case "$1" in
		tmux) tmux kill-session -t "=$TMUX_SESSION" ;;
		screen) screen -S "$TMUX_SESSION" -X quit ;;
	esac > /dev/null 2>&1 || true
}

# The terminal type to attach with. tmux and screen need its terminfo entry,
# which a server often lacks (xterm-ghostty, xterm-kitty, ...). Prints
# nothing for a terminal they cannot use.
mux_term() {
	local t
	case "${TERM:-dumb}" in dumb | unknown) return 0 ;; esac
	if ! command -v tput > /dev/null; then
		echo "$TERM"
		return 0
	fi
	for t in "$TERM" xterm-256color; do
		if tput -T "$t" clear > /dev/null 2>&1 && tput -T "$t" cup 0 0 > /dev/null 2>&1; then
			echo "$t"
			return 0
		fi
	done
}

# Attach this terminal (also when stdin is the curl pipe). tmux refuses the
# name /dev/tty, so the terminal's own device. screen -d -r: a client of a
# dropped SSH connection may still count as attached.
# Not through "curl ... | sudo bash" when sudo runs the command in a terminal
# of its own (sudo-rs on 26.04, use_pty of sudo 1.9.14+ on 24.04): the client
# shows nothing there. Return 1, so that the caller names the attach command.
mux_attach() { # TOOL
	local t sid
	if [ ! -t 0 ]; then
		sid=$(ps -o sid= -p $$ 2> /dev/null | tr -d ' ' || true)
		case "$(ps -o comm= -p "${sid:-0}" 2> /dev/null || true)" in
			sudo | sudo.ws | sudo-rs)
				say "This terminal cannot show the session: sudo runs this command in a terminal of its"
				say "own, and its input is the curl pipe."
				return 1
				;;
		esac
	fi
	t=$(ps -o tty= -p $$ 2> /dev/null | tr -d ' ' || true)
	case "$t" in '' | '?') t=/dev/tty ;; *) t=/dev/$t ;; esac
	# shellcheck disable=SC2094 # a terminal, not a file
	case "$1" in
		tmux) TERM=${MUX_TERM:-${TERM:-}} tmux attach-session -t "=$TMUX_SESSION" ;;
		screen) TERM=${MUX_TERM:-${TERM:-}} screen -d -r "$TMUX_SESSION" ;;
	esac < "$t" > "$t" 2>&1
}

# Start the session; the window stays open after the command until Enter is
# pressed (with --yes at most 10 minutes: a caller such as "ssh -t ... --yes"
# must not wait for someone to press it), and the exit code is kept in RC_FILE.
mux_start() { # TOOL RC_FILE HINT ARGS...
	local tool=$1 rc_file=$2 hint=$3 v scope=() env_file=$STATE_DIR/.multiplexer-env close=
	shift 3
	if [ -n "$ASSUME_YES" ]; then close=600; fi
	# A tmux server that runs already gives a new session its own environment,
	# not this one: pass what the script reads, and unset what is not set here.
	# In a file, not on the command line (ps shows that to every user, and
	# SOURCE may hold a token).
	rm -f "$rc_file" "$env_file"
	(
		umask 077
		for v in PATH HOME LANG LC_ALL "${MUX_ENV[@]}"; do
			if [ -n "${!v+x}" ]; then printf 'export %s=%q\n' "$v" "${!v}"; else printf 'unset %s\n' "$v"; fi
		done > "$env_file"
		echo 'export MIAB_2604_MUX=1' >> "$env_file"
	) || return 1
	# trap : INT: Ctrl-C stops the command, but not this shell (bash ends
	# itself after a child that died of SIGINT), so the window stays open.
	# shellcheck disable=SC2016 # expanded by that bash
	local cmd=(bash -c '
trap : INT QUIT
rc_file=$1 hint=$2 env_file=$3 close=$4
shift 4
wait_enter() { if [ -n "$close" ]; then read -r -t "$close" _; else read -r _; fi; }
if ! . "$env_file"; then
	echo "Could not read $env_file. Press Enter to close this window."
	wait_enter
	exit 1
fi
rm -f "$env_file"
printf "%s\n\n" "$hint"
"$@"
rc=$?
echo "$rc" > "$rc_file"
echo
echo "The command ended with exit code $rc. Press Enter to close this window${close:+ (it closes by itself after $close seconds, --yes)}."
wait_enter
exit "$rc"' mux "$rc_file" "$hint" "$env_file" "$close" bash "$SELF_FILE" "$@")
	case "$tool" in
		tmux)
			# In a scope of its own (like the resume unit): logind must not end the
			# tmux server with the SSH session (KillUserProcesses=yes).
			if command -v systemd-run > /dev/null 2>&1 && [ -d /run/systemd/system ]; then
				scope=(systemd-run --scope --quiet --collect "--unit=$TMUX_SESSION-$$" --)
				"${scope[@]}" tmux new-session -d -s "$TMUX_SESSION" "${cmd[@]}" < /dev/null && return 0
			fi
			tmux new-session -d -s "$TMUX_SESSION" "${cmd[@]}" < /dev/null && return 0
			;;
		screen) screen -dmS "$TMUX_SESSION" "${cmd[@]}" < /dev/null && return 0 ;;
	esac
	rm -f "$env_file"
	return 1
}

run_in_multiplexer() { # ARGS (the original arguments)
	[ -z "$NO_TMUX$CHECK_ONLY${RESUMED:-}${MIAB_2604_MUX:-}" ] || return 0
	[ -n "$SELF_FILE" ] || return 0
	in_multiplexer && return 0
	if trap -p HUP | grep -q "''"; then return 0; fi
	(: < /dev/tty) 2> /dev/null || return 0
	MUX_TERM=$(mux_term)
	if [ -z "$MUX_TERM" ]; then
		say "tmux cannot use this terminal (TERM=${TERM:-}); running without it."
		return 0
	fi
	local tool='' again rc rc_file=$STATE_DIR/.multiplexer-exit-code pre=''
	if command -v tmux > /dev/null; then
		tool=tmux
	else
		say "Installing tmux, so that this run survives a dropped SSH connection..."
		if install_tmux && command -v tmux > /dev/null; then
			tool=tmux
		elif command -v screen > /dev/null; then
			warn "Could not install tmux; using screen."
			tool=screen
		else
			warn "Could not install tmux."
			return 0
		fi
	fi
	if [ "$MUX_TERM" != "${TERM:-}" ]; then pre="TERM=$MUX_TERM "; fi
	if [ -n "${SUDO_USER:-}" ]; then pre+="sudo "; fi
	case "$tool" in
		tmux) again="${pre}tmux attach -t $TMUX_SESSION" ;;
		screen) again="${pre}screen -d -r $TMUX_SESSION" ;;
	esac
	if mux_has "$tool" && mux_finished "$tool"; then
		say "The window of an earlier run in the $tool session $TMUX_SESSION only waits for Enter"
		say "(its output is in $LOG_FILE). Closing it and starting this run."
		mux_kill "$tool"
		sleep 1
	fi
	if mux_has "$tool"; then
		say "Something still runs in the $tool session $TMUX_SESSION (an earlier run?)."
		say "This command is NOT started; attaching to that session instead."
		sleep 3
		mux_attach "$tool" || warn "Could not attach this terminal; attach with: $again"
		trap - EXIT
		say "This command was NOT run, because the $tool session $TMUX_SESSION was in use."
		say "Run it again when the run there has ended."
		exit 1
	fi
	local hint="This runs in the $tool session $TMUX_SESSION and goes on if the SSH connection drops.
Then ssh in again and run: $again"
	if [ "$tool" = tmux ]; then hint+="     (detach without stopping it: Ctrl-b d)"; else hint+="     (detach: Ctrl-a d)"; fi
	if ! mux_start "$tool" "$rc_file" "$hint" "$@"; then
		warn "Could not start a $tool session; continuing without it."
		return 0
	fi
	say "$hint"
	local attached=1
	mux_attach "$tool" || attached=''
	# The output stays in the session; this process ends here.
	trap - EXIT
	if mux_has "$tool"; then
		if [ -n "$attached" ]; then
			say "Detached. The run goes on in the $tool session $TMUX_SESSION; back to it with: $again"
		else
			warn "Could not attach this terminal. The run goes on in the $tool session $TMUX_SESSION; attach with: $again"
		fi
		exit 0
	fi
	rc=$(cat "$rc_file" 2> /dev/null || true)
	if ! [[ $rc =~ ^[0-9]+$ ]]; then
		say "The $tool session $TMUX_SESSION has ended (the output is in $LOG_FILE)."
		exit 1
	fi
	say "The run in the $tool session ended with exit code $rc (the output is in $LOG_FILE)."
	exit "$rc"
}

# ---------------------------------------------------------------------------
# Running things on the old box.

ssh_init() {
	OLD_USER=root
	OLD_HOST=$FROM
	if [[ $FROM == *@* ]]; then
		OLD_USER=${FROM%%@*}
		OLD_HOST=${FROM#*@}
	fi
	[ -n "$OLD_HOST" ] || die "--from needs a host name."
	SSH_TARGET="$OLD_USER@$OLD_HOST"

	local ctl=$STATE_DIR
	if [ -n "$CHECK_ONLY" ]; then ctl=$CHECK_TMP; fi
	SSH_ARGS=(-o BatchMode=yes -o ConnectTimeout=20 -o ServerAliveInterval=30 -o ServerAliveCountMax=10
		-o StrictHostKeyChecking=accept-new
		# One multiplexed connection for everything: Mail-in-a-Box rate-limits
		# new SSH connections with "ufw limit" (6 per 30 seconds).
		-o ControlMaster=auto -o "ControlPath=$ctl/ssh-%C" -o ControlPersist=900)
	if [ -n "$SSH_PORT" ]; then SSH_ARGS+=(-p "$SSH_PORT"); fi
	# --check changes nothing: a new host key goes to a temporary file, not to ~/.ssh/known_hosts.
	if [ -n "$CHECK_ONLY" ]; then SSH_ARGS+=(-o "UserKnownHostsFile=$ctl/known_hosts ~/.ssh/known_hosts"); fi
	if [ -n "$SSH_KEY" ]; then
		[ -r "$SSH_KEY" ] || die "Cannot read the SSH key $SSH_KEY."
		SSH_ARGS+=(-i "$SSH_KEY" -o IdentitiesOnly=yes)
	fi

	# rsync's -e takes one string, quoted with single quotes.
	local a
	RSYNC_RSH=ssh
	for a in "${SSH_ARGS[@]}"; do
		[[ $a != *\'* ]] || die "SSH options must not contain single quotes: $a"
		RSYNC_RSH+=" '$a'"
	done

	if [ "$OLD_USER" = root ]; then
		REMOTE_SUDO=
		RSYNC_PATH=rsync
	else
		REMOTE_SUDO="sudo -n "
		RSYNC_PATH="sudo -n rsync"
	fi

	say "Connecting to $SSH_TARGET..."
	if ! ssh "${SSH_ARGS[@]}" "$SSH_TARGET" true < /dev/null; then
		die "Cannot log in to $SSH_TARGET with SSH (key authentication, no password prompts).
Set up the key login for root of THIS machine first:
  ssh-keygen -t ed25519                (here, as root; accept the defaults)
  cat /root/.ssh/id_ed25519.pub        (copy this line)
  on $OLD_HOST: append the line to /root/.ssh/authorized_keys
  test it here: ssh ${SSH_PORT:+-p $SSH_PORT }$SSH_TARGET true
Or give another key with --ssh-key, or use a user with passwordless sudo: --from USER@$OLD_HOST."
	fi
	if [ -n "$REMOTE_SUDO" ] && ! ssh "${SSH_ARGS[@]}" "$SSH_TARGET" "sudo -n true" < /dev/null; then
		die "$OLD_USER on $OLD_HOST cannot use sudo without a password (sudo -n).
Allow it, e.g. with '$OLD_USER ALL=(ALL) NOPASSWD:ALL' in /etc/sudoers.d/, or log in as root."
	fi
}

ssh_from_state() {
	FROM=$(state_get FROM)
	[ -n "$FROM" ] || die "No old box is recorded in $STATE_FILE."
	SSH_KEY=${SSH_KEY:-$(state_get SSH_KEY)}
	SSH_PORT=${SSH_PORT:-$(state_get SSH_PORT)}
	ssh_init
}

ssh_close() {
	if [ ${#SSH_ARGS[@]} -gt 0 ] && [ -n "$SSH_TARGET" ]; then
		ssh "${SSH_ARGS[@]}" -O exit "$SSH_TARGET" > /dev/null 2>&1 || true
	fi
}

# Run a bash script (given as a string) as root on the old box. Further
# arguments are NAME=VALUE pairs that are set as variables for the script.
# The script is wrapped in a function so that bash has read all of it before
# anything runs, and it runs in / with stdin from /dev/null.
script_with_vars() {
	local body=$1 kv
	shift
	for kv in "$@"; do printf '%s=%q\n' "${kv%%=*}" "${kv#*=}"; done
	printf '__migrate() {\n%s\n}\ncd / && __migrate < /dev/null\n' "$body"
}

# shellcheck disable=SC2029 # REMOTE_SUDO is meant to expand here
remote_bash() {
	script_with_vars "$@" | ssh "${SSH_ARGS[@]}" "$SSH_TARGET" "${REMOTE_SUDO}bash -s"
}

local_bash() {
	script_with_vars "$@" | bash -s
}

# Run one command line as root on the old box.
# shellcheck disable=SC2029 # the command line is built here on purpose
remote() {
	ssh "${SSH_ARGS[@]}" "$SSH_TARGET" "$REMOTE_SUDO$1" < /dev/null
}

# Read KEY=VALUE lines into the associative array named by $1.
load_kv() {
	local -n _arr=$1
	local k v
	while IFS='=' read -r k v; do
		# shellcheck disable=SC2004 # associative array: the key must be expanded
		if [[ $k =~ ^[A-Z][A-Z0-9_]*$ ]]; then _arr[$k]=$v; fi
	done
}

# The PIDs of a running Mail-in-a-Box backup: a python running
# management/backup.py, or duplicity. From /proc and not with pgrep -f, which
# also matches any command line that only names them (the checking shell, a
# grep, an editor). Keep in sync with tools/upgrade-in-place-to-2604.sh.
BACKUP_PIDS_SCRIPT=$(cat <<'EOF'
for f in /proc/[0-9]*/cmdline; do
	a=()
	mapfile -d '' -t -n 3 a 2> /dev/null < "$f" || continue
	case "${a[0]:-}" in python* | */python* | duplicity | */duplicity) ;; *) continue ;; esac
	for x in "${a[@]}"; do
		case "$x" in
			management/backup.py | */management/backup.py | duplicity | */duplicity)
				f=${f#/proc/}
				echo "${f%/cmdline}"
				break
				;;
		esac
	done
done
EOF
)

# Facts about the old box. Cheap, runs on every start.
FACTS_SCRIPT="backup_pids() {
$BACKUP_PIDS_SCRIPT
}
$(cat <<'EOF'
. /etc/os-release 2> /dev/null || true
echo "OS_ID=${ID:-unknown}"
echo "OS_VERSION=${VERSION_ID:-unknown}"
echo "MACHINE_ID=$(cat /etc/machine-id 2> /dev/null)"
echo "EPOCH=$(date +%s)"
echo "NTP_SYNC=$(timedatectl show -p NTPSynchronized --value 2> /dev/null)"
echo "TIMEZONE=$(timedatectl show -p Timezone --value 2> /dev/null)"
echo "RSYNC_VERSION=$(rsync --version 2> /dev/null | sed -n '1s/^rsync *version *\([^ ]*\).*/\1/p')"
echo "PHP_VERSIONS=$(ls /etc/php 2> /dev/null | tr '\n' ' ')"
if [ ! -f /etc/mailinabox.conf ]; then
	echo "HAS_CONF=0"
	return 0
fi
echo "HAS_CONF=1"
sed -n 's/^\([A-Z_][A-Z0-9_]*\)=\(.*\)$/CONF_\1=\2/p' /etc/mailinabox.conf
SR=$(sed -n 's/^STORAGE_ROOT=//p' /etc/mailinabox.conf)

# The setup directory, from the "mailinabox" start script that setup writes.
d=$(sed -n 's/^cd //p' /usr/local/bin/mailinabox 2> /dev/null | head -n 1)
[ -n "$d" ] || d=/root/mailinabox
echo "MIAB_DIR=$d"
echo "MIAB_VERSION=$(git -c safe.directory='*' -C "$d" describe --always --tags 2> /dev/null)"

cfg=$SR/owncloud/config.php
if [ -f "$cfg" ]; then
	echo "NC_VERSION=$(sed -n "s/^[[:space:]]*'version'[[:space:]]*=>[[:space:]]*'\([0-9.]*\)'.*/\1/p" "$cfg" | head -n 1)"
	if grep -Eq "'maintenance'[[:space:]]*=>[[:space:]]*true" "$cfg"; then echo "NC_MAINTENANCE=1"; fi
	if grep -Eq "'appstoreenabled'[[:space:]]*=>[[:space:]]*false" "$cfg"; then echo "NC_APPSTORE=0"; else echo "NC_APPSTORE=1"; fi
fi
echo "NC_DB_BYTES=$(stat -c %s "$SR/owncloud/owncloud.db" 2> /dev/null || echo 0)"
# Nextcloud apps that are neither shipped with Nextcloud nor installed by
# Mail-in-a-Box live in /usr/local/lib/owncloud/apps, outside $STORAGE_ROOT.
if [ -f /usr/local/lib/owncloud/core/shipped.json ] && command -v python3 > /dev/null; then
	echo "NC_EXTRA_APPS=$(python3 -I - <<'PY' 2> /dev/null
import json, os
d = "/usr/local/lib/owncloud"
with open(d + "/core/shipped.json", encoding="utf-8") as f:
	s = json.load(f)
miab = ("contacts", "calendar", "user_external")
known = set(s.get("shippedApps", [])) | set(s.get("alwaysEnabled", [])) | set(miab)
def is_miab(a):
	# Older MIAB versions unpacked GitHub source archives next to the apps,
	# leaving directories like contacts-5.5.3 or calendar-4.7.6 behind.
	return any(a.startswith(m + "-") and a[len(m) + 1:][:1].isdigit() for m in miab)
print(" ".join(sorted(a for a in os.listdir(d + "/apps") if a not in known and not is_miab(a) and os.path.isdir(os.path.join(d, "apps", a)))))
PY
)"
fi

# Backup target (credentials in URLs masked).
echo "BACKUP_TARGET=$(sed -n 's/^target:[[:space:]]*//p' "$SR/backup/custom.yaml" 2> /dev/null | head -n 1 | sed 's#//[^/@]*@#//***@#')"

# Messages waiting in the Postfix queue live in /var/spool/postfix, not in $STORAGE_ROOT.
echo "POSTQUEUE=$(find /var/spool/postfix/deferred /var/spool/postfix/active /var/spool/postfix/incoming /var/spool/postfix/hold /var/spool/postfix/maildrop -type f 2> /dev/null | wc -l)"
if [ -n "$(backup_pids)" ]; then echo "BACKUP_RUNNING=1"; else echo "BACKUP_RUNNING=0"; fi
if systemctl is-active --quiet apt-daily.service 2> /dev/null || systemctl is-active --quiet apt-daily-upgrade.service 2> /dev/null \
	|| pgrep -f 'bin/unattended-upgrade( |$)' > /dev/null; then
	echo "APT_BUSY=1"
fi

# Units to stop for the switch-over, in this order: the timers that start
# package updates (whose postinst scripts restart services), cron (backups,
# Nextcloud cron), the services that serve users or write to $STORAGE_ROOT,
# and the socket units that would start one of them again on the next
# connection (e.g. dovecot.socket).
cand="apt-daily.timer apt-daily-upgrade.timer anacron.timer cron.service mailinabox.service nginx.service"
cand="$cand $(systemctl list-units --type=service --state=active --no-legend --plain 'php*-fpm.service' 2> /dev/null | awk '{print $1}' | tr '\n' ' ')"
cand="$cand postfix.service $(systemctl list-units --type=service --state=active --no-legend --plain 'postfix@*.service' 2> /dev/null | awk '{print $1}' | tr '\n' ' ')"
cand="$cand spampd.service postgrey.service opendkim.service opendmarc.service dovecot.service"
for sock in $(systemctl list-units --type=socket --state=active --no-legend --plain 2> /dev/null | awk '{print $1}'); do
	for t in $(systemctl show -p Triggers --value "$sock" 2> /dev/null); do
		case " $cand " in *" $t "*) cand="$cand $sock"; break ;; esac
	done
done
s=
for u in $cand; do
	if systemctl is-active --quiet "$u" 2> /dev/null; then s="$s $u"; fi
done
echo "ACTIVE_UNITS=${s# }"
if [ -f /root/.ssh/id_rsa_miab ]; then echo "HAS_BACKUP_SSH_KEY=1"; fi
if [ -d /var/lib/z-push ]; then echo "HAS_ZPUSH=1"; fi
if [ -d /var/lib/munin ]; then echo "HAS_MUNIN=1"; fi
EOF
)"

# Size and number of files of $STORAGE_ROOT and of the parts that may be left
# out. Slow on big boxes.
SIZE_SCRIPT=$(cat <<'EOF'
sz() { if [ -e "$1" ]; then du -s -B1 "$1" 2> /dev/null | cut -f1; else echo 0; fi; }
nf() { if [ -e "$1" ]; then du -s --inodes "$1" 2> /dev/null | cut -f1; else echo 0; fi; }
echo "SIZE_TOTAL=$(sz "$SR")"
echo "SIZE_OWNCLOUD_BACKUP=$(sz "$SR/owncloud-backup")"
echo "SIZE_BACKUP_CACHE=$(sz "$SR/backup/cache")"
echo "SIZE_BACKUP_ENCRYPTED=$(sz "$SR/backup/encrypted")"
echo "FILES_TOTAL=$(nf "$SR")"
echo "FILES_OWNCLOUD=$(nf "$SR/owncloud")"
EOF
)

# The Postfix queue: how many messages wait for a local mailbox of the box
# itself, how many for other servers.
QUEUE_SCRIPT=$(cat <<'EOF'
if ! command -v python3 > /dev/null; then
	echo "QUEUE_TOTAL=$(find /var/spool/postfix/deferred /var/spool/postfix/active /var/spool/postfix/incoming /var/spool/postfix/hold /var/spool/postfix/maildrop -type f 2> /dev/null | wc -l)"
	return 0
fi
postqueue -j 2> /dev/null | python3 -I -c '
import json, sqlite3, sys
dom = set()
try:
	c = sqlite3.connect("file:%s?mode=ro" % sys.argv[1], uri=True)
	for (e,) in c.execute("SELECT email FROM users UNION SELECT source FROM aliases"):
		if "@" in e:
			dom.add(e.rsplit("@", 1)[1].lower())
except Exception:
	pass
t = l = 0
for line in sys.stdin:
	try:
		m = json.loads(line)
	except ValueError:
		continue
	t += 1
	if any(r.get("address", "").rsplit("@", 1)[-1].lower() in dom for r in m.get("recipients", [])):
		l += 1
print("QUEUE_TOTAL=%d" % t)
print("QUEUE_LOCAL=%d" % l)
print("QUEUE_REMOTE=%d" % (t - l))
' "$SR/mail/users.sqlite"
EOF
)

# Processes that still use $SR: a file open there, the working directory there
# (interactive shells excepted), or a known job (backup, Nextcloud cron, ...).
# cron.service has KillMode=process, so stopping cron does not end its jobs.
QUIET_SCRIPT=$(cat <<'EOF'
pat='cron\.php|daily_tasks|management/backup\.py|/usr/bin/duplicity|sa-learn|owncloud/occ'
{
	find /proc/[0-9]*/fd -maxdepth 1 \( -lname "$SR" -o -lname "$SR/*" \) 2> /dev/null | cut -d/ -f3 | sed 's/$/ 1fd/'
	pgrep -f "$pat" | sed 's/$/ 2job/'
	find /proc/[0-9]*/cwd -maxdepth 0 \( -lname "$SR" -o -lname "$SR/*" \) 2> /dev/null | cut -d/ -f3 | sed 's/$/ 3cwd/'
} | sort -k1,1n -k2,2 | awk '!seen[$1]++' | while read -r pid why; do
	[ "$pid" != "$$" ] || continue
	comm=$(cat "/proc/$pid/comm" 2> /dev/null) || continue
	case "$comm" in nsd) continue ;; esac
	if [ "$why" = 3cwd ]; then
		case "$comm" in bash | sh | dash | zsh | fish | tmux* | screen | sudo | su | login | sshd) continue ;; esac
	fi
	echo "BUSY $pid ${why#?} $comm: $(tr '\0' ' ' < "/proc/$pid/cmdline" 2> /dev/null | cut -c1-150)"
done
EOF
)

# State of the units stopped on the old box: which are active, and when each
# was last started (changes if it was started again in between, even if it
# stopped again).
OLD_STATUS_SCRIPT=$(cat <<'EOF'
for u in $UNITS; do
	if systemctl is-active --quiet "$u" 2> /dev/null; then echo "ACTIVE $u"; fi
	echo "STAMP $u $(systemctl show -p ActiveEnterTimestampMonotonic --value "$u" 2> /dev/null)"
done
EOF
)

# Mask the units in /run (gone after a reboot), stop them, report the units
# that could not be masked (unit files in /etc/systemd/system take precedence).
OLD_STOP_SCRIPT=$(cat <<'EOF'
for u in $UNITS; do
	systemctl mask --runtime --quiet "$u" 2> /dev/null || true
	if [ "$(systemctl is-enabled "$u" 2> /dev/null)" != masked-runtime ]; then echo "NOMASK $u"; fi
done
systemctl stop $UNITS || echo "STOPFAILED"
EOF
)

# --rollback: set virtual_transport back to VT (if given) and stop a Postfix
# that runs outside systemd (both from the queue hint in handle_old_queue).
OLD_POSTFIX_RESET_SCRIPT=$(cat <<'EOF'
if [ -n "$VT" ] && command -v postconf > /dev/null; then
	cur=$(postconf -h virtual_transport 2> /dev/null || true)
	if [ "$cur" != "$VT" ]; then postconf -e "virtual_transport = $VT" && echo "VTFIXED $cur"; fi
fi
if command -v postfix > /dev/null && postfix status > /dev/null 2>&1 \
	&& ! systemctl is-active --quiet postfix@-.service && ! systemctl is-active --quiet postfix.service; then
	postfix stop > /dev/null 2>&1 && echo "PFSTOPPED"
fi
true
EOF
)

OLD_START_SCRIPT=$(cat <<'EOF'
for u in $UNITS; do systemctl unmask --runtime --quiet "$u" 2> /dev/null || true; done
systemctl start $START
EOF
)

# Counts and key fingerprints of a $STORAGE_ROOT. Runs on the old box after its
# services were stopped and on this box at the end, and the results are compared.
FINGERPRINT_SCRIPT=$(cat <<'EOF'
q() { if [ -f "$1" ]; then sqlite3 -readonly "$1" "$2" 2> /dev/null || echo "-"; else echo "-"; fi; }
h() { if [ -f "$1" ]; then sha256sum < "$1" | cut -c1-16; else echo "-"; fi; }
db=$SR/mail/users.sqlite
echo "USERS=$(q "$db" 'SELECT count(*) FROM users;')"
echo "ALIASES=$(q "$db" 'SELECT count(*) FROM aliases;')"
echo "MAILBOXES=$(find "$SR/mail/mailboxes" -mindepth 2 -maxdepth 2 -type d 2> /dev/null | wc -l)"
echo "MESSAGES=$(find "$SR/mail/mailboxes" -type f \( -path '*/cur/*' -o -path '*/new/*' \) 2> /dev/null | wc -l)"
echo "SIEVE_SCRIPTS=$(find "$SR/mail/sieve" -type f -name '*.sieve' 2> /dev/null | wc -l)"
echo "DKIM_KEY=$(h "$SR/mail/dkim/mail.private")"
if ls "$SR"/dns/dnssec/*.private > /dev/null 2>&1; then
	echo "DNSSEC_KEYS=$(cat "$SR"/dns/dnssec/*.private | sha256sum | cut -c1-16)"
else
	echo "DNSSEC_KEYS=-"
fi
echo "TLS_KEY=$(h "$SR/ssl/ssl_private_key.pem")"
echo "BACKUP_KEY=$(h "$SR/backup/secret_key.txt")"
echo "LE_ACCOUNTS=$(find "$SR/ssl/lets_encrypt/accounts" -name regr.json 2> /dev/null | wc -l)"
if id spampd > /dev/null 2>&1 && command -v sa-learn > /dev/null; then
	m=$(runuser -u spampd -- sa-learn --dump magic 2> /dev/null || true)
	echo "BAYES_SPAM=$(echo "$m" | awk '/non-token data: nspam/ {print $3}')"
	echo "BAYES_HAM=$(echo "$m" | awk '/non-token data: nham/ {print $3}')"
fi
nc=$SR/owncloud/owncloud.db
p=$(sed -n "s/^[[:space:]]*'dbtableprefix'[[:space:]]*=>[[:space:]]*'\([A-Za-z0-9_]*\)'.*/\1/p" "$SR/owncloud/config.php" 2> /dev/null | head -n 1)
p=${p:-oc_}
echo "NC_ACCOUNTS=$(q "$nc" "SELECT count(*) FROM ${p}accounts;")"
# Only the users' own address books: Nextcloud keeps a system address book of
# all accounts (principals/system/system) that newer versions fill differently.
echo "NC_CARDS=$(q "$nc" "SELECT count(*) FROM ${p}cards c JOIN ${p}addressbooks a ON c.addressbookid = a.id WHERE a.principaluri NOT LIKE 'principals/system/%';")"
# Only objects of real calendars that are not in the trash: the cached objects
# of webcal subscriptions (calendartype 1, calendarid is a subscription id) and
# the trash change with Nextcloud's background jobs (calendartype and the
# deleted_at columns exist since Nextcloud 22; the old box runs 26 or later).
echo "NC_EVENTS=$(q "$nc" "SELECT count(*) FROM ${p}calendarobjects o JOIN ${p}calendars c ON o.calendarid = c.id AND o.calendartype = 0 WHERE c.uri <> 'contact_birthdays' AND o.deleted_at IS NULL AND c.deleted_at IS NULL;")"
EOF
)

# Parks file owners at ID + offset (shift), or maps parked owners to this
# machine's IDs by the user/group names of the old box (map). Usage:
#   python3 -c "$UIDMAP_PY" shift|map ROOT OFFSET OLD_PASSWD OLD_GROUP [SKIP,NAMES]
# SKIP,NAMES are entries directly below ROOT that are left alone.
UIDMAP_PY=$(cat <<'EOF'
import grp, os, pwd, stat, sys

mode, root, offset = sys.argv[1], sys.argv[2], int(sys.argv[3])
skip = set(x for x in (sys.argv[6] if len(sys.argv) > 6 else "").split(",") if x)

def table(fn):
	t = {}
	with open(fn, encoding="utf-8", errors="replace") as f:
		for line in f:
			p = line.rstrip("\n").split(":")
			if len(p) >= 3 and p[2].isdigit():
				t.setdefault(int(p[2]), p[0])
	return t

old = {"user": table(sys.argv[4]), "group": table(sys.argv[5])}

def new_id(kind, name):
	try:
		return pwd.getpwnam(name).pw_uid if kind == "user" else grp.getgrnam(name).gr_gid
	except KeyError:
		return None

def name_here(kind, i):
	try:
		return pwd.getpwuid(i).pw_name if kind == "user" else grp.getgrgid(i).gr_name
	except KeyError:
		return None

cache = {"user": {}, "group": {}}
unmapped = {}
changes = {}

def target(kind, i):
	c = cache[kind]
	if i in c:
		return c[i]
	if mode == "shift":
		name = old[kind].get(i)
		# Root, and IDs that already belong to the same name here (mail, www-data, ...), stay.
		if i == 0 or i >= offset or (name is not None and new_id(kind, name) == i):
			r = (i, None)
		else:
			r = (i + offset, None)
	else:
		if i < offset:
			r = (i, None)
		else:
			o = i - offset
			name = old[kind].get(o)
			n = new_id(kind, name) if name is not None else None
			if n is not None:
				r = (n, None)
				changes[(kind, name, o, n)] = True
			else:
				label = "%s %s (old ID %d)" % (kind, name if name else "<no name>", o)
				here = name_here(kind, o)
				if here is not None:
					# The old number belongs to another account here: do not hand it the files.
					r = (0, "%s: does not exist here and ID %d is '%s' here, set to root" % (label, o, here))
				else:
					r = (o, "%s: does not exist here, kept the old number (unused here)" % label)
	c[i] = r
	return r

total = changed = errors = 0

def visit(path):
	global total, changed, errors
	try:
		st = os.lstat(path)
	except OSError as e:
		errors += 1
		print("  cannot stat %s: %s" % (path, e))
		return
	total += 1
	u, ux = target("user", st.st_uid)
	g, gx = target("group", st.st_gid)
	for x in (ux, gx):
		if x:
			unmapped[x] = unmapped.get(x, 0) + 1
	if (u, g) != (st.st_uid, st.st_gid):
		try:
			os.chown(path, u, g, follow_symlinks=False)
			# chown clears setuid/setgid bits, put them back.
			if not stat.S_ISLNK(st.st_mode) and st.st_mode & (stat.S_ISUID | stat.S_ISGID):
				os.chmod(path, stat.S_IMODE(st.st_mode))
			changed += 1
		except OSError as e:
			errors += 1
			print("  cannot chown %s: %s" % (path, e))
	if total % 250000 == 0:
		print("  ... %d entries" % total, flush=True)

visit(root)
stack = [root]
while stack:
	d = stack.pop()
	try:
		it = os.scandir(d)
	except OSError as e:
		errors += 1
		print("  cannot list %s: %s" % (d, e))
		continue
	with it:
		for e in it:
			if d == root and e.name in skip:
				continue
			visit(e.path)
			try:
				if e.is_dir(follow_symlinks=False):
					stack.append(e.path)
			except OSError:
				pass

print("  %d entries checked, %d changed, %d errors." % (total, changed, errors))
for kind, name, o, n in sorted(changes):
	if o != n:
		print("  %s %s: %d -> %d" % (kind, name, o, n))
for x, cnt in sorted(unmapped.items()):
	print("  NOT MAPPED: %s; %d entries" % (x, cnt))
sys.exit(1 if errors else 0)
EOF
)

# Filters rsync's output: progress updates (ending in \r) go to the terminal
# only, and every 5 minutes one of them goes to the log; all other lines go to
# stdout (terminal and log) and to the stats file argv[1]. argv[2] is the log.
PROGRESS_PY=$(cat <<'EOF'
import sys, time
stats = open(sys.argv[1], "w", encoding="utf-8", errors="replace")
log = open(sys.argv[2], "a", encoding="utf-8", errors="replace")
try:
	tty = open("/dev/tty", "w", encoding="utf-8", errors="replace")
except OSError:
	tty = None
out = sys.stdout
last = time.time()
shown = False

def full(s):
	global shown
	if tty and shown:
		tty.write("\r\033[K")
		tty.flush()
		shown = False
	out.write(s + "\n")
	out.flush()
	stats.write(s + "\n")
	stats.flush()

def progress(s):
	global last, shown
	s = s.strip()
	if not s:
		return
	if tty:
		tty.write("\r" + s + "\033[K")
		tty.flush()
		shown = True
	if time.time() - last >= 300:
		last = time.time()
		stamp = time.strftime("%H:%M")
		if tty:
			log.write("  [%s] %s\n" % (stamp, s))
			log.flush()
		else:
			out.write("  [%s] %s\n" % (stamp, s))
			out.flush()

buf = b""
inp = sys.stdin.buffer
while True:
	chunk = inp.read1(65536)
	if not chunk:
		break
	buf += chunk
	while True:
		found = [x for x in (buf.find(b"\r"), buf.find(b"\n")) if x >= 0]
		if not found:
			break
		i = min(found)
		seg, sep, buf = buf[:i].decode("utf-8", "replace"), buf[i:i + 1], buf[i + 1:]
		if sep == b"\r":
			progress(seg)
		elif seg.strip():
			full(seg)
if buf.strip():
	full(buf.decode("utf-8", "replace"))
if tty and shown:
	tty.write("\n")
EOF
)

# The PTR record of an IPv4 address, asked directly at public resolvers
# (systemd-resolved answers for local addresses with the local hostname).
PTR_PY=$(cat <<'EOF'
import random, socket, struct, sys

def name(b, i):
	out = []
	while True:
		n = b[i]
		if n & 0xC0 == 0xC0:
			out.append(name(b, ((n & 0x3F) << 8) | b[i + 1])[0])
			return ".".join(x for x in out if x), i + 2
		i += 1
		if n == 0:
			return ".".join(out), i
		out.append(b[i:i + n].decode("ascii", "replace"))
		i += n

ip = sys.argv[1]
q = ".".join(reversed(ip.split("."))) + ".in-addr.arpa"
qid = random.randrange(65536)
pkt = struct.pack(">HHHHHH", qid, 0x0100, 1, 0, 0, 0)
pkt += b"".join(bytes([len(x)]) + x.encode() for x in q.split(".")) + b"\0" + struct.pack(">HH", 12, 1)
for server in ("9.9.9.9", "1.1.1.1"):
	s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	s.settimeout(4)
	try:
		s.sendto(pkt, (server, 53))
		b = s.recv(4096)
	except OSError:
		continue
	if struct.unpack(">H", b[:2])[0] != qid:
		continue
	an = struct.unpack(">H", b[6:8])[0]
	i = name(b, 12)[1] + 4
	for _ in range(an):
		i = name(b, i)[1]
		t, _c, _ttl, l = struct.unpack(">HHIH", b[i:i + 10])
		i += 10
		if t == 12:
			print(name(b, i)[0])
			sys.exit(0)
		i += l
	sys.exit(0)
EOF
)

# ---------------------------------------------------------------------------
# This machine.

install_packages() {
	say "Installing $*..."
	apt-get -q -q update < /dev/null || die "apt-get update failed."
	DEBIAN_FRONTEND=noninteractive apt-get -q -q install -y "$@" < /dev/null || die "Could not install $*."
}

# For run_in_multiplexer. A failure only means: no tmux. Quickly or not at
# all: short lock timeouts.
install_tmux() {
	(
		apt-get -q -q -o DPkg::Lock::Timeout=30 update < /dev/null > /dev/null 2>&1 || exit 1
		DEBIAN_FRONTEND=noninteractive apt-get -q -q -y -o DPkg::Lock::Timeout=30 install tmux < /dev/null > /dev/null 2>&1
	)
}

preflight_local() {
	[ "$(id -u)" = 0 ] || die "This must be run as root on the new machine. Did you leave out sudo?"
	local id ver
	# shellcheck source=/dev/null
	id=$(. /etc/os-release && echo "${ID:-}")
	# shellcheck source=/dev/null
	ver=$(. /etc/os-release && echo "${VERSION_ID:-}")
	if [ "$id" != ubuntu ] || [ "$ver" != 26.04 ]; then
		blocker "The new machine must run Ubuntu 26.04 (this one runs $id $ver). Run this on the new machine."
	fi
	if [ -f /etc/mailinabox.conf ] && [ "$(state_get CONF_WRITTEN)" != 1 ]; then
		blocker "Mail-in-a-Box is already set up on this machine (/etc/mailinabox.conf exists).
Migrate to a fresh Ubuntu 26.04 install."
	fi

	local missing=() p pkgs=()
	for p in rsync git sqlite3 curl python3 ssh; do
		command -v "$p" > /dev/null || missing+=("$p")
	done
	[ ${#missing[@]} -gt 0 ] || return 0
	if [ -n "$CHECK_ONLY" ]; then
		say "Missing here (the migration installs them): ${missing[*]}"
		if ! command -v ssh > /dev/null || ! command -v python3 > /dev/null; then
			die "--check needs ssh and python3 on this machine: apt-get install openssh-client python3"
		fi
		return 0
	fi
	for p in "${missing[@]}"; do
		if [ "$p" = ssh ]; then pkgs+=(openssh-client); else pkgs+=("$p"); fi
	done
	install_packages "${pkgs[@]}"
}

# Setup links /usr/local/bin/mailinabox and the nightly cron job to the setup
# directory and runs it as root, so it must belong to root.
check_checkout_owner() {
	local d=$1 o
	o=$(stat -c %U "$d")
	[ "$o" != root ] || return 0
	warn "The setup scripts in $d belong to the user $o. Setup points
/usr/local/bin/mailinabox and the nightly cron job to this directory and runs them
as root, so $o could change what runs as root, and deleting $d later breaks the box.
Better: sudo git clone $DEFAULT_SOURCE $CLONE_DIR
and run sudo $CLONE_DIR/tools/migrate-to-2604.sh ..."
	if [ -z "$CHECK_ONLY" ]; then confirm "Continue with $d anyway?"; fi
}

# A release tag older than run_in_multiplexer does not start tmux by itself:
# say so before its copy runs (its own check only asks without --yes). Keep
# in sync with tools/upgrade-in-place-to-2604.sh.
warn_no_auto_tmux() { # FILE TAG
	grep -q '^run_in_multiplexer()' "$1" 2> /dev/null && return 0
	[ -z "$NO_TMUX$CHECK_ONLY" ] || return 0
	in_multiplexer && return 0
	(: < /dev/tty) 2> /dev/null || return 0
	warn "The downloaded $2 does not start tmux by itself yet (TAG=main does). If your SSH
connection drops outside tmux or screen, the run stops halfway. Better: stop now
(Ctrl-C), run tmux new -s $TMUX_SESSION and start the command again in there."
	sleep 5
}

# Find this fork's setup scripts: the checkout this script runs from, or a
# clone in /root/mailinabox (like setup/bootstrap.sh) when it runs through curl.
checkout_dir() { # the checkout this script runs from, if any
	local d
	[ -n "$SELF_FILE" ] || return 1
	d=$(dirname "$(dirname "$SELF_FILE")")
	[ -f "$d/setup/start.sh" ] || return 1
	echo "$d"
}

# Keep these three in sync with tools/upgrade-in-place-to-2604.sh.
# GitHub treats the owner and repository names case-insensitively, and a
# trailing .git or / names the same repository.
same_repo() { # URL URL
	local a=${1%/} b=${2%/}
	a=${a%.git}
	b=${b%.git}
	[ "${a,,}" = "${b,,}" ]
}

# A checkout cloned from another repository (rc1 to rc3 came from the fork's
# previous home) would fetch the release from there: stop with the command
# that points it to SOURCE, as setup/bootstrap.sh does.
check_origin() { # DIR SOURCE
	local o
	o=$(git -C "$1" config --get remote.origin.url 2> /dev/null || true)
	same_repo "$o" "$2" && return 0
	die "$1 is a checkout of ${o:-an unknown repository}, not of $2.
Point it there once and run the command again:
  sudo git -C $1 remote set-url origin $2
(To keep using ${o:-it} instead, set SOURCE=${o:-...}.)"
}

# Fetch REF (a release tag, or a branch such as main) from origin and check
# it out. A tag is fetched as a tag, so that git describe names the version.
checkout_ref() { # DIR REF [--force]
	local d=$1 ref=$2 force=${3:-}
	if git -C "$d" fetch -q --depth 1 --force --prune origin tag "$ref" < /dev/null 2> /dev/null; then
		git -C "$d" checkout -q ${force:+"$force"} "$ref"
	else
		git -C "$d" fetch -q --depth 1 --force origin "$ref" < /dev/null \
			&& git -C "$d" checkout -q ${force:+"$force"} FETCH_HEAD
	fi
}

resolve_miab_dir() {
	local d
	if d=$(checkout_dir); then
		MIAB_DIR=$d
		check_checkout_owner "$d"
		return 0
	fi
	[ -z "${MIGRATE_REEXEC:-}" ] || die "Could not find the setup scripts next to $SELF."

	local source=${SOURCE:-$DEFAULT_SOURCE} tag=${TAG:-$DEFAULT_TAG}
	local how="curl -s $DEFAULT_RAW/tools/migrate-to-2604.sh | sudo TAG=main bash -s -- --from root@old.example.com"
	d=$CLONE_DIR
	if [ ! -d "$d" ]; then
		command -v git > /dev/null || install_packages git
		say "Downloading Mail-in-a-Box $tag from $source..."
		if ! git clone -q -b "$tag" --depth 1 "$source" "$d" < /dev/null; then
			if [ -n "${TAG:-}" ]; then
				die "Could not download $tag from $source. Set TAG and SOURCE like this:
  $how"
			fi
			warn "The release tag $tag is not published yet. Using the branch main instead."
			git clone -q -b main --depth 1 "$source" "$d" < /dev/null \
				|| die "Could not download $source. Set TAG and SOURCE like this:
  $how"
		fi
	elif [ "$tag" != "$(git -C "$d" describe --always --tags 2> /dev/null)" ]; then
		# From an earlier run (e.g. a rehearsal with an older release): bring it
		# to the tag from SOURCE instead of running the old copy.
		[ -d "$d/.git" ] || die "$d is not a git checkout, so it cannot be updated to $tag."
		check_origin "$d" "$source"
		say "Updating $d to $tag..."
		if ! checkout_ref "$d" "$tag"; then
			if [ -z "${TAG:-}" ] && checkout_ref "$d" main; then
				warn "The release tag $tag is not published yet. Using the branch main instead."
			else
				die "Could not update $d to $tag from $source. Did you modify something in $d?"
			fi
		fi
	fi
	[ -x "$d/tools/migrate-to-2604.sh" ] || die "$d has no tools/migrate-to-2604.sh. Is it this fork?"
	warn_no_auto_tmux "$d/tools/migrate-to-2604.sh" "$tag"
	MIGRATE_REEXEC=1 exec "$d/tools/migrate-to-2604.sh" "$@"
}

nearest_dir() {
	local d=$1
	while [ ! -d "$d" ]; do d=$(dirname "$d"); done
	echo "$d"
}

# The target directory must be empty or hold an earlier copy made by this
# tool from the same old box (marker file), before rsync --delete runs.
check_target() {
	local sr=$1 owner=$2
	if [ -e "$sr" ] && [ ! -d "$sr" ]; then
		blocker "$sr exists and is not a directory."
		return 0
	fi
	[ -d "$sr" ] || return 0
	if [ -f "$sr/$MARKER" ]; then
		if [ "$(head -n 1 "$sr/$MARKER")" != "$owner" ]; then
			blocker "$sr holds a copy made from another machine ($(head -n 1 "$sr/$MARKER")).
This old box is $owner. Move the directory away first."
		fi
	elif [ "$(state_get TARGET_OWNER)" = "$owner" ]; then
		: # ours, the marker was removed at the end of an earlier run
	elif [ -n "$(find "$sr" -mindepth 1 -maxdepth 1 ! -name lost+found -print -quit)" ]; then
		blocker "$sr is not empty and was not created by this tool.
Move it away (or use an empty disk) and run the command again."
	fi
}

# The ownership placeholders need 32-bit user IDs (not in some containers).
check_big_ids() {
	local t
	t=$(mktemp "$1/.migrate-idtest.XXXXXX")
	if ! chown "$((ID_OFFSET + 1)):$((ID_OFFSET + 1))" "$t" 2> /dev/null; then
		rm -f "$t"
		blocker "The file system of $1 does not accept large user IDs (a container?).
Use a virtual machine or a real server as the new box."
		return 0
	fi
	rm -f "$t"
}

claim_target() {
	local sr=$1 owner=$2
	check_target "$sr" "$owner"
	mkdir -p "$sr"
	echo "$owner" > "$sr/$MARKER"
	chmod 600 "$sr/$MARKER"
	state_set TARGET_OWNER "$owner"
	check_big_ids "$sr"
}

detect_ip() { # 4|6
	local ip
	ip=$(curl -"$1" --fail --silent --max-time 15 icanhazip.com 2> /dev/null || true)
	if [ -z "$ip" ]; then
		if [ "$1" = 4 ]; then
			ip=$(ip -4 route get 1.1.1.1 2> /dev/null | sed -n 's/.* src \([^ ]*\).*/\1/p' | head -n 1)
		else
			ip=$(ip -6 route get 2001:4860:4860::8888 2> /dev/null | sed -n 's/.* src \([^ ]*\).*/\1/p' | head -n 1)
		fi
	fi
	echo "$ip"
}

# Decide hostname and IPs for the new box once and keep them in the state.
choose_new_settings() {
	local v
	v=$(state_get NEW_PRIMARY_HOSTNAME)
	NEW_PRIMARY_HOSTNAME=${OPT_HOSTNAME:-${v:-${OLD[CONF_PRIMARY_HOSTNAME]:-}}}
	[ -n "$NEW_PRIMARY_HOSTNAME" ] || die "The hostname is unknown. Give it with --hostname."

	v=$(state_get NEW_PUBLIC_IP)
	NEW_PUBLIC_IP=${OPT_PUBLIC_IP:-$v}
	[ -n "$NEW_PUBLIC_IP" ] || NEW_PUBLIC_IP=$(detect_ip 4)
	[ -n "$NEW_PUBLIC_IP" ] || die "Could not detect the public IPv4 address. Give it with --public-ip."

	if [ -n "$OPT_PUBLIC_IPV6" ]; then
		NEW_PUBLIC_IPV6=$OPT_PUBLIC_IPV6
	elif [ "$(state_get NEW_PUBLIC_IPV6_SET)" = 1 ]; then
		NEW_PUBLIC_IPV6=$(state_get NEW_PUBLIC_IPV6)
	else
		NEW_PUBLIC_IPV6=$(detect_ip 6)
	fi
	NEW_PRIVATE_IP=${OPT_PRIVATE_IP:-$(state_get NEW_PRIVATE_IP)}
	NEW_PRIVATE_IPV6=${OPT_PRIVATE_IPV6:-$(state_get NEW_PRIVATE_IPV6)}

	state_set NEW_PRIMARY_HOSTNAME "$NEW_PRIMARY_HOSTNAME"
	state_set NEW_PUBLIC_IP "$NEW_PUBLIC_IP"
	state_set NEW_PUBLIC_IPV6 "$NEW_PUBLIC_IPV6"
	state_set NEW_PUBLIC_IPV6_SET 1
	state_set NEW_PRIVATE_IP "$NEW_PRIVATE_IP"
	state_set NEW_PRIVATE_IPV6 "$NEW_PRIVATE_IPV6"
}

# What setup/network-checks.sh checks (setup runs with SKIP_NETWORK_CHECKS=1
# here), plus the reverse DNS. Fills NET_BLOCKERS.
network_checks() {
	NET_BLOCKERS=()
	if timeout 10 bash -c 'exec 3<> /dev/tcp/aspmx.l.google.com/25' 2> /dev/null; then
		say "Outbound port 25:  open"
	else
		say "Outbound port 25:  BLOCKED (no connection to aspmx.l.google.com:25)"
		NET_BLOCKERS+=("Outbound connections to port 25 fail here. Many providers block port 25 for new servers
(e.g. Hetzner Cloud, AWS, Google Cloud, DigitalOcean); ask them to unblock it.")
	fi

	local a rev ptr
	if [[ $NEW_PUBLIC_IP =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
		rev=$(echo "$NEW_PUBLIC_IP" | awk -F. '{print $4"."$3"."$2"."$1}')
		a=$(getent -s dns hosts "$rev.zen.spamhaus.org" 2> /dev/null | awk '{print $1; exit}' || true)
		case "$a" in
			"") say "Spamhaus ZEN:      $NEW_PUBLIC_IP is not listed" ;;
			127.255.255.*) say "Spamhaus ZEN:      no answer (Spamhaus refuses public resolvers); check $NEW_PUBLIC_IP on https://check.spamhaus.org/" ;;
			127.0.0.*)
				say "Spamhaus ZEN:      $NEW_PUBLIC_IP is LISTED ($a)"
				NET_BLOCKERS+=("The IP address $NEW_PUBLIC_IP is listed in the Spamhaus Block List (https://check.spamhaus.org/).
Mail from this machine would be rejected. Get another IP address or have it delisted.")
				;;
			*) say "Spamhaus ZEN:      unexpected answer $a" ;;
		esac
	fi
	a=$(getent -s dns hosts "$NEW_PRIMARY_HOSTNAME.dbl.spamhaus.org" 2> /dev/null | awk '{print $1; exit}' || true)
	case "$a" in
		127.0.1.*) warn "The hostname $NEW_PRIMARY_HOSTNAME is listed in the Spamhaus Domain Block List ($a), see https://check.spamhaus.org/." ;;
	esac
	ptr=
	if [[ $NEW_PUBLIC_IP =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
		ptr=$(python3 -I -c "$PTR_PY" "$NEW_PUBLIC_IP" 2> /dev/null || true)
	fi
	if [ "$ptr" = "$NEW_PRIMARY_HOSTNAME" ]; then
		say "Reverse DNS (PTR): $NEW_PUBLIC_IP -> $ptr"
	else
		say "Reverse DNS (PTR): $NEW_PUBLIC_IP -> ${ptr:-none}"
		warn "Set the reverse DNS (PTR) of $NEW_PUBLIC_IP${NEW_PUBLIC_IPV6:+ and $NEW_PUBLIC_IPV6} to $NEW_PRIMARY_HOSTNAME at the
hosting provider now, before the switch-over. Without it, many servers reject mail from this box."
	fi
}

# ---------------------------------------------------------------------------
# Preflight for the SSH source.

old_owner_key() {
	echo "${OLD[MACHINE_ID]:-}:${OLD[CONF_PRIMARY_HOSTNAME]:-}:${OLD[CONF_STORAGE_ROOT]:-}"
}

read_old_facts() {
	local facts
	facts=$(remote_bash "$FACTS_SCRIPT") || die "Could not read the facts of the old box."
	OLD=()
	load_kv OLD <<< "$facts"
}

read_old_queue() {
	local out
	OLD[QUEUE_TOTAL]=${OLD[POSTQUEUE]:-0}
	OLD[QUEUE_LOCAL]=
	out=$(remote_bash "$QUEUE_SCRIPT" "SR=${OLD[CONF_STORAGE_ROOT]:-}" 2> /dev/null) || return 0
	load_kv OLD <<< "$out"
}

preflight_old() {
	section "Checking the old box ($OLD_HOST)"
	read_old_facts
	[ "${OLD[HAS_CONF]:-0}" = 1 ] || die "$OLD_HOST has no /etc/mailinabox.conf. Is it a Mail-in-a-Box?"

	local known key
	key=$(old_owner_key)
	known=$(state_get OLD_KEY)
	if [ -n "$known" ] && [ "$known" != "$key" ]; then
		die "This migration was started from another machine
(machine-id:hostname:storage $known, this one is $key).
Use the same --from, or move $STATE_DIR away to start a new migration."
	fi
	state_set OLD_KEY "$key"
	state_set SOURCE_MODE ssh
	state_set FROM "$FROM"
	state_set SSH_KEY "$SSH_KEY"
	state_set SSH_PORT "$SSH_PORT"

	say "Ubuntu:            ${OLD[OS_VERSION]}"
	say "Mail-in-a-Box:     ${OLD[MIAB_VERSION]:-unknown} (${OLD[MIAB_DIR]})"
	say "Nextcloud:         ${OLD[NC_VERSION]:-not installed}"
	say "PHP:               ${OLD[PHP_VERSIONS]:-none}"
	say "Hostname:          ${OLD[CONF_PRIMARY_HOSTNAME]:-}"
	say "Public IP:         ${OLD[CONF_PUBLIC_IP]:-} ${OLD[CONF_PUBLIC_IPV6]:-}"
	say "Storage:           ${OLD[CONF_STORAGE_ROOT]:-} (user ${OLD[CONF_STORAGE_USER]:-})"
	say "Backups:           ${OLD[BACKUP_TARGET]:-local}"

	case "${OLD[OS_ID]}/${OLD[OS_VERSION]}" in
		ubuntu/22.04) ;;
		ubuntu/24.04)
			say "Note: Ubuntu 24.04 is not supported by upstream Mail-in-a-Box; this looks"
			say "like a box that was release-upgraded in place. That is fine for the move:"
			say "only the data is taken over, none of the old programs."
			;;
		ubuntu/26.04) blocker "The old box already runs Ubuntu 26.04. Nothing to migrate." ;;
		ubuntu/18.04 | ubuntu/20.04)
			blocker "The old box runs Ubuntu ${OLD[OS_VERSION]}. First move it to Ubuntu 22.04 with
upstream Mail-in-a-Box v78 (https://mailinabox.email/maintenance.html#upgrade), then run this."
			;;
		*) blocker "The old box runs ${OLD[OS_ID]} ${OLD[OS_VERSION]}, expected Ubuntu 22.04 or 24.04." ;;
	esac

	local mv=${OLD[MIAB_VERSION]:-}
	if [[ $mv =~ ^v([0-9]+) ]]; then
		if [ "${BASH_REMATCH[1]}" -lt 60 ]; then
			blocker "Mail-in-a-Box $mv is too old. Update the old box to v78 first:
  curl -s https://mailinabox.email/setup.sh | sudo bash"
		fi
	else
		warn "Could not read the Mail-in-a-Box version in ${OLD[MIAB_DIR]}. Continuing; the Nextcloud check below still applies."
	fi

	local nc=${OLD[NC_VERSION]:-}
	if [ -n "$nc" ] && [ "${nc%%.*}" -lt 26 ] 2> /dev/null; then
		if [ "${OLD[OS_VERSION]}" = 22.04 ]; then
			blocker "The old box runs Nextcloud $nc. This fork's upgrade chain starts at Nextcloud 26.
Update the old box to upstream Mail-in-a-Box v78 first (Nextcloud 27):
  curl -s https://mailinabox.email/setup.sh | sudo bash
then run this command again."
		else
			blocker "The old box runs Nextcloud $nc. This fork's upgrade chain starts at Nextcloud 26,
and upstream setup does not run on Ubuntu ${OLD[OS_VERSION]}. Upgrade Nextcloud on the old box
to 26 by hand (occ upgrade, one major version at a time) or migrate from a 22.04 box with v78."
		fi
	fi
	if [ "${OLD[NC_MAINTENANCE]:-0}" = 1 ]; then
		warn "Nextcloud on the old box is in maintenance mode. Setup turns it off after the upgrade, but check why it is on."
	fi
	if [ -n "${OLD[NC_EXTRA_APPS]:-}" ]; then
		warn "Nextcloud apps installed by hand on the old box are NOT migrated (they live in
/usr/local/lib/owncloud/apps, outside the data): ${OLD[NC_EXTRA_APPS]}
Their data stays in the database. Reinstall them afterwards if they support Nextcloud 34
(setup keeps the app store off, see 'appstoreenabled' in config.php)."
	fi
	if [ "${OLD[NC_APPSTORE]:-0}" = 1 ] && [ -n "$nc" ]; then
		say "Note: the Nextcloud app store is enabled on the old box. Setup turns it off ('appstoreenabled' => false)."
	fi

	[ -n "${OLD[RSYNC_VERSION]:-}" ] || blocker "rsync is not installed on the old box. Install it there (apt-get install rsync) and run this again."

	local skew=$(($(date +%s) - ${OLD[EPOCH]:-0}))
	skew=${skew#-}
	if [ "$skew" -gt 120 ]; then
		warn "The clocks of the two machines differ by $skew seconds. Check NTP on both."
	fi
	if [ "$(timedatectl show -p NTPSynchronized --value 2> /dev/null || true)" != yes ]; then
		warn "This machine's clock is not NTP-synchronized (timedatectl). TLS, TOTP and DNSSEC need the right time."
	fi
	if [ "${OLD[BACKUP_RUNNING]:-0}" = 1 ]; then
		say "Backup:            a Mail-in-a-Box backup runs on the old box right now. The copy goes on;"
		say "                   the switch-over waits until it has finished before it stops the old box."
	fi

	read_old_queue
	if [ "${OLD[QUEUE_TOTAL]:-0}" -gt 0 ] 2> /dev/null; then
		say "Postfix queue:     ${OLD[QUEUE_TOTAL]} messages${OLD[QUEUE_LOCAL]:+ (${OLD[QUEUE_LOCAL]} for mailboxes of the box, ${OLD[QUEUE_REMOTE]:-?} outgoing)}"
		say "                   The queue is not migrated. Check it on the old box before the switch-over"
		say "                   ('postqueue -p'; 'postqueue -f' retries now)."
	else
		say "Postfix queue:     empty"
	fi
}

check_space() {
	local sr=$1
	if [ -z "$(state_get SIZE_TOTAL)" ]; then
		say "Measuring the size of $sr on the old box (this can take a few minutes)..."
		local out
		out=$(remote_bash "$SIZE_SCRIPT" "SR=$sr") || die "Could not measure $sr on the old box."
		local -A S=()
		load_kv S <<< "$out"
		state_set SIZE_TOTAL "${S[SIZE_TOTAL]:-0}"
		state_set SIZE_OWNCLOUD_BACKUP "${S[SIZE_OWNCLOUD_BACKUP]:-0}"
		state_set SIZE_BACKUP_CACHE "${S[SIZE_BACKUP_CACHE]:-0}"
		state_set SIZE_BACKUP_ENCRYPTED "${S[SIZE_BACKUP_ENCRYPTED]:-0}"
		state_set FILES_TOTAL "${S[FILES_TOTAL]:-0}"
		state_set FILES_OWNCLOUD "${S[FILES_OWNCLOUD]:-0}"
	fi
	local total copy margin need avail
	total=$(state_get SIZE_TOTAL)
	copy=$((total - $(state_get SIZE_BACKUP_CACHE)))
	if [ -z "$WITH_OWNCLOUD_BACKUP" ]; then copy=$((copy - $(state_get SIZE_OWNCLOUD_BACKUP))); fi
	if [ -n "$SKIP_LOCAL_BACKUPS" ]; then copy=$((copy - $(state_get SIZE_BACKUP_ENCRYPTED))); fi
	state_set SIZE_COPY "$copy"
	# Margin: 10% for growth, two copies of the Nextcloud database and of the
	# Nextcloud code that setup puts into owncloud-backup/ (rehearsal and real
	# run), and 3 GB for the software.
	margin=$((copy / 10 + 2 * (${OLD[NC_DB_BYTES]:-0} + 700 * 1024 * 1024) + 3 * 1024 * 1024 * 1024))
	need=$((copy + margin))
	avail=$(df -B1 --output=avail "$(nearest_dir "$sr")" | tail -n 1 | tr -d ' ')

	say "Data to copy:      $(human "$copy") (of $(human "$total") in $sr, $(state_get FILES_TOTAL) files and directories)"
	if [ "$(state_get SIZE_OWNCLOUD_BACKUP)" != 0 ] && [ -z "$WITH_OWNCLOUD_BACKUP" ]; then
		say "                   not copied: owncloud-backup/ $(human "$(state_get SIZE_OWNCLOUD_BACKUP)") (--with-owncloud-backup)"
	fi
	if [ "$(state_get SIZE_BACKUP_ENCRYPTED)" != 0 ] && [ -z "$SKIP_LOCAL_BACKUPS" ]; then
		say "                   includes local backups $(human "$(state_get SIZE_BACKUP_ENCRYPTED)") (--skip-local-backups)"
	fi
	say "Free on this box:  $(human "$avail") (needed with margin: $(human "$need"))"

	if phase_is_done sync_live || phase_is_done restore; then
		# Most of the data is here already, only warn when it gets tight.
		if [ "$avail" -lt $((margin / 2)) ]; then
			warn "Only $(human "$avail") free on this machine."
		fi
	elif [ "$avail" -lt "$need" ]; then
		blocker "Not enough disk space here: $(human "$avail") free, $(human "$need") needed."
	fi
}

# The old /etc, its Postfix settings and root's crontab, for reference. Taken
# on the first run and again in sync-final (old box stopped, latest state).
snapshot_old_etc() {
	say "Saving a copy of the old box's /etc, 'postconf -n' and root's crontab in $STATE_DIR..."
	local rc=0
	# shellcheck disable=SC2029
	ssh "${SSH_ARGS[@]}" "$SSH_TARGET" "${REMOTE_SUDO}tar -C / --numeric-owner -czf - etc 2> /dev/null" \
		< /dev/null > "$STATE_DIR/old-etc.tar.gz.new" || rc=$?
	# tar exits with 1 when a file changed while it was read.
	[ "$rc" -le 1 ] || die "Could not copy /etc from the old box (exit code $rc)."
	mv "$STATE_DIR/old-etc.tar.gz.new" "$STATE_DIR/old-etc.tar.gz"
	rm -rf "$STATE_DIR/old-etc"
	mkdir -p "$STATE_DIR/old-etc"
	tar -C "$STATE_DIR/old-etc" --numeric-owner -xzf "$STATE_DIR/old-etc.tar.gz" \
		|| die "Could not unpack $STATE_DIR/old-etc.tar.gz."
	remote "postconf -n" > "$STATE_DIR/old-postconf.txt" 2> /dev/null || true
	remote "crontab -l -u root" > "$STATE_DIR/old-root-crontab.txt" 2> /dev/null || true
	state_set ETC_SAVED_AT "$(date -u +%FT%TZ)"
}

save_old_users() {
	if ! remote "getent passwd" > "$STATE_DIR/old-passwd.new" || ! remote "getent group" > "$STATE_DIR/old-group.new" \
		|| [ ! -s "$STATE_DIR/old-passwd.new" ] || [ ! -s "$STATE_DIR/old-group.new" ]; then
		die "Could not read the users and groups of the old box."
	fi
	mv "$STATE_DIR/old-passwd.new" "$STATE_DIR/old-passwd"
	mv "$STATE_DIR/old-group.new" "$STATE_DIR/old-group"
}

# Copies of things outside $STORAGE_ROOT, for reference and for later phases.
save_reference() {
	if [ "$(state_get REFERENCE_SAVED)" = 1 ]; then return 0; fi
	snapshot_old_etc
	save_old_users
	remote "dpkg-query -W -f '\${binary:Package} \${Version}\n'" > "$STATE_DIR/old-packages.txt" 2> /dev/null || true
	if [ "${OLD[HAS_BACKUP_SSH_KEY]:-0}" = 1 ]; then
		remote "cat /root/.ssh/id_rsa_miab" > "$STATE_DIR/old-id_rsa_miab" || die "Could not read /root/.ssh/id_rsa_miab on the old box."
		remote "cat /root/.ssh/id_rsa_miab.pub" > "$STATE_DIR/old-id_rsa_miab.pub" || true
	fi
	state_set REFERENCE_SAVED 1
}

# A rough estimate of the downtime: everything from stop-old to verify.
estimate_downtime() {
	local files oc nc steps=0 cnt refresh reh
	files=$(state_get FILES_TOTAL)
	files=${files:-0}
	oc=$(state_get FILES_OWNCLOUD)
	oc=${oc:-0}
	nc=${OLD[NC_VERSION]:-$(state_get NC_VERSION)}
	if [[ $nc =~ ^([0-9]+) ]] && [ "${BASH_REMATCH[1]}" -lt 34 ]; then steps=$((34 - BASH_REMATCH[1])); fi
	cnt=$(state_get LIVE_SYNC_COUNT)
	refresh=$(state_get LAST_LIVE_SYNC_SECONDS)
	reh=$(state_get REHEARSAL_SETUP_SECONDS)

	local flo fhi fwhy wlo whi slo shi swhy vlo vhi
	if [ "${cnt:-0}" -ge 2 ] && [ -n "$refresh" ]; then
		flo=$refresh fhi=$((refresh * 3 / 2)) fwhy="as long as the last refresh"
	else
		flo=$((files / 20000 + 60)) fhi=$((files / 2000 + 300)) fwhy="guessed; run --sync-only once more to measure it"
	fi
	wlo=$((2 * files / 50000)) whi=$((2 * files / 10000))
	if [ -n "$reh" ]; then
		slo=$((reh / 2)) shi=$reh swhy="the rehearsal took $(fmt_dur "$reh"); faster now that the packages are installed"
	else
		slo=$((900 + steps * 120 + steps * oc / 50000)) shi=$((1800 + steps * 600 + steps * oc / 10000))
		swhy="15-30 min packages + $steps Nextcloud upgrade steps over $oc files; --rehearse measures it"
	fi
	vlo=$((files / 100000)) vhi=$((files / 20000))
	say "Expected downtime, roughly (from stopping the old box to the end of the checks):"
	say "  final copy        $(fmt_dur "$flo") - $(fmt_dur "$fhi")  ($fwhy)"
	say "  file owners       $(fmt_dur "$wlo") - $(fmt_dur "$whi")  (two passes over $files files)"
	say "  setup             $(fmt_dur "$slo") - $(fmt_dur "$shi")  ($swhy)"
	say "  checks            $(fmt_dur "$vlo") - $(fmt_dur "$vhi")"
	say "  total             $(fmt_dur $((flo + wlo + slo + vlo))) - $(fmt_dur $((fhi + whi + shi + vhi)))"
	say "Then the DNS change takes effect over 1-3 days (see README-fork.md, 'Switch DNS')."
}

show_plan_ssh() {
	section "Plan"
	say "Old box:   $SSH_TARGET  ${OLD[CONF_PUBLIC_IP]:-} ${OLD[CONF_PUBLIC_IPV6]:-}"
	say "New box:   this machine  $NEW_PUBLIC_IP ${NEW_PUBLIC_IPV6:-}"
	say "Hostname:  $NEW_PRIMARY_HOSTNAME"
	say "Data:      $SSH_TARGET:$STORAGE_ROOT -> $STORAGE_ROOT"
	if [ "$NEW_PRIMARY_HOSTNAME" != "${OLD[CONF_PRIMARY_HOSTNAME]:-}" ]; then
		warn "The hostname changes from ${OLD[CONF_PRIMARY_HOSTNAME]:-} to $NEW_PRIMARY_HOSTNAME.
Then MX/NS records, the TLS certificate and all clients must be changed as well."
	fi
	say
	say "1. Copy the data while the old box keeps running (can take hours)."
	say "   Optional: --rehearse runs setup once on that copy, the old box keeps running."
	say "2. Stop mail, web, cron and the update timers on the old box - the downtime"
	say "   starts (you are asked first)."
	say "3. Copy the changes, run setup here (Nextcloud ${OLD[NC_VERSION]:-} -> 34), fix the file owners."
	say "4. Check the result and show how to test the new box and what to change in DNS."
	say "The old box keeps all its data. '$SELF --rollback' starts its services again."
	say
	estimate_downtime
}

# ---------------------------------------------------------------------------
# Making sure nothing writes to $STORAGE_ROOT while it is copied.

# Wait until no process on the old box (old) or here (local) uses $STORAGE_ROOT.
# "rollback" (local only): wait at most a minute, then end this machine's
# backup jobs and only warn about the rest, so that the old box is not left down.
wait_quiet() {
	local where=$1 mode=${2:-} label out start now shown=0 timeout=$QUIET_TIMEOUT pids
	if [ "$where" = old ]; then label="on the old box"; else label="on this machine"; fi
	if [ "$mode" = rollback ] && [ "$timeout" -gt 60 ]; then timeout=60; fi
	start=$(date +%s)
	while :; do
		if [ "$where" = old ]; then
			out=$(remote_bash "$QUIET_SCRIPT" "SR=$STORAGE_ROOT") || die "Could not check the processes on the old box."
		else
			out=$(local_bash "$QUIET_SCRIPT" "SR=$STORAGE_ROOT") || die "Could not check the processes on this machine."
		fi
		out=$(grep '^BUSY ' <<< "$out" | sed 's/^BUSY /  /' || true)
		if [ -z "$out" ]; then
			if [ "$shown" = 1 ]; then say "Nothing $label uses $STORAGE_ROOT any more."; fi
			return 0
		fi
		now=$(date +%s)
		if [ "$mode" = rollback ] && [ $((now - start)) -ge "$timeout" ]; then
			# The old box takes over the backup target again: a backup still running
			# here must not write to it at the same time. Duplicity cleans up an
			# interrupted backup on its next run.
			# Found like wait_backup_done does: pkill -f would also end any process
			# whose command line only names them (an editor, a tmux server).
			pids=$(local_bash "$BACKUP_PIDS_SCRIPT" | paste -sd ' ' || true)
			if [ -n "$pids" ]; then
				warn "Ending the backup that is still running on this machine (PID $pids)."
				# shellcheck disable=SC2086 # a list of PIDs
				kill -TERM $pids 2> /dev/null || true
				sleep 10
				pids=$(local_bash "$BACKUP_PIDS_SCRIPT" | paste -sd ' ' || true)
				# shellcheck disable=SC2086 # a list of PIDs
				if [ -n "$pids" ]; then kill -KILL $pids 2> /dev/null || true; fi
				sleep 2
			fi
			out=$(local_bash "$QUIET_SCRIPT" "SR=$STORAGE_ROOT" | grep '^BUSY ' | sed 's/^BUSY /  /' || true)
			if [ -n "$out" ]; then
				warn "These processes on this machine still use $STORAGE_ROOT (PID, why, command):
$out
The rollback copies nothing here, so it continues. End them before the next attempt."
			fi
			return 0
		fi
		if [ $((now - start)) -ge "$timeout" ]; then
			die "These processes $label still use $STORAGE_ROOT after $(fmt_dur "$timeout") (PID, why, command):
$out
Copying now could take over half-written databases. Let them finish (or end them),
then run the command again."
		fi
		if [ "$shown" = 0 ] || [ $(((now - start) % 120)) -lt 10 ]; then
			say "Waiting until nothing $label uses $STORAGE_ROOT any more (at most $(fmt_dur "$timeout")):"
			say "$out"
			shown=1
		fi
		sleep 10
	done
}

backup_pids() { remote_bash "$BACKUP_PIDS_SCRIPT"; }

# A Mail-in-a-Box backup that is running (the nightly one starts at 01:04,
# /etc/cron.d/mailinabox-nightly): wait until it has finished, at most
# BACKUP_WAIT seconds. Only before anything is stopped, so Ctrl-C is safe.
# Sets BACKUP_WAITED. Keep in sync with tools/upgrade-in-place-to-2604.sh
# (there on that box, without LABEL).
wait_backup_done() { # [LABEL]
	local label=${1:-} pids start fails=0
	BACKUP_WAITED=
	pids=$(backup_pids | paste -sd ' ')
	[ -n "$pids" ] || return 0
	BACKUP_WAITED=1
	start=$(date +%s)
	say "A Mail-in-a-Box backup is running$label (PID $pids). Waiting until it has finished"
	say "(at most $(fmt_dur "$BACKUP_WAIT"); nothing was stopped yet, so Ctrl-C is safe here)..."
	while :; do
		# errexit does not apply in a command substitution: a failed check
		# (e.g. ssh) must not count as "finished".
		if ! pids=$(backup_pids); then
			fails=$((fails + 1))
			echo
			[ "$fails" -lt 3 ] || die "Could not check $fails times in a row whether the backup$label still runs.
Nothing was stopped yet. Run the command again."
			warn "Could not check whether the backup$label still runs; trying again."
			sleep 30
			continue
		fi
		fails=0
		[ -n "$pids" ] || break
		if [ $(($(date +%s) - start)) -ge "$BACKUP_WAIT" ]; then
			echo
			die "The backup$label still runs after $(fmt_dur "$BACKUP_WAIT") (PID $(paste -sd ' ' <<< "$pids")).
Nothing was stopped yet. Run the command again when it has finished."
		fi
		printf '.'
		sleep 30
	done
	echo
	say "The backup$label has finished (waited $(fmt_dur $(($(date +%s) - start))))."
}

local_units() {
	local u
	for u in "${LOCAL_UNITS[@]}"; do
		if systemctl cat "$u" > /dev/null 2>&1; then echo "$u"; fi
	done
}

# Disable those of the given units that are enabled, and remember them for
# local_unquiesce. A masked unit reports "masked-runtime", not "enabled": a
# unit still masked in /run (by an older run of this script, without a reboot
# since) is unmasked for the check and the disable, then masked again.
local_disable() {
	local u st en=() remask=()
	for u in "$@"; do
		st=$(systemctl is-enabled "$u" 2> /dev/null || true)
		if [ "$st" = masked-runtime ]; then
			systemctl unmask --runtime --quiet "$u" 2> /dev/null || true
			remask+=("$u")
			st=$(systemctl is-enabled "$u" 2> /dev/null || true)
		fi
		if [ "$st" = enabled ]; then en+=("$u"); fi
	done
	if [ ${#en[@]} -gt 0 ]; then
		systemctl disable --quiet "${en[@]}" || warn "Could not disable ${en[*]} here."
	fi
	for u in "${remask[@]}"; do
		systemctl mask --runtime --quiet "$u" 2> /dev/null || warn "Could not mask $u here."
	done
	[ ${#en[@]} -gt 0 ] || return 0
	state_set LOCAL_DISABLED "$(echo "$(state_get LOCAL_DISABLED) ${en[*]}" | tr ' ' '\n' | awk 'NF && !seen[$0]++' | tr '\n' ' ')"
}

# Once setup has run here, nothing here may run while rsync replaces
# $STORAGE_ROOT: stop the Mail-in-a-Box units and mask them in /run.
# "disable" also disables them, so that a reboot does not start them; setup
# (local_unquiesce) enables them again. "rollback" (with "disable") does not
# stop at processes that still use $STORAGE_ROOT (see wait_quiet).
local_quiesce() {
	local units=() u
	mapfile -t units < <(local_units)
	[ ${#units[@]} -gt 0 ] || return 0
	say "Stopping the Mail-in-a-Box services on this machine (they are started again by setup)..."
	if [ "${1:-}" = disable ]; then local_disable "${units[@]}"; fi
	for u in "${units[@]}"; do
		systemctl mask --runtime --quiet "$u" 2> /dev/null || warn "Could not mask $u here."
	done
	systemctl stop "${units[@]}" 2> /dev/null || warn "Not all services stopped here: ${units[*]}"
	state_set LOCAL_MASKED 1
	wait_quiet local "${2:-}"
}

local_unquiesce() {
	local units=() list
	if [ "$(state_get LOCAL_MASKED)" = 1 ]; then
		mapfile -t units < <(local_units)
		if [ ${#units[@]} -gt 0 ]; then systemctl unmask --runtime --quiet "${units[@]}" 2> /dev/null || true; fi
		state_set LOCAL_MASKED ""
	fi
	list=$(state_get LOCAL_DISABLED)
	if [ -n "$list" ]; then
		# shellcheck disable=SC2086 # a list of unit names
		systemctl enable --quiet $list || warn "Could not enable $list again."
		state_set LOCAL_DISABLED ""
	fi
}

local_needs_quiesce() { [ "$(state_get CONF_WRITTEN)" = 1 ] || [ -f /etc/mailinabox.conf ]; }

# The state of the units stopped on the old box: OLD_ACTIVE_NOW (running
# again) and OLD_STAMPS_NOW (unit=last start time).
old_status() {
	local out kind u v
	OLD_ACTIVE_NOW='' OLD_STAMPS_NOW=''
	out=$(remote_bash "$OLD_STATUS_SCRIPT" "UNITS=$(state_get OLD_SERVICES)") \
		|| die "Could not read the state of the services on the old box."
	while read -r kind u v; do
		case "$kind" in
			ACTIVE) OLD_ACTIVE_NOW="$OLD_ACTIVE_NOW $u" ;;
			STAMP) OLD_STAMPS_NOW="$OLD_STAMPS_NOW $u=$v" ;;
		esac
	done <<< "$out"
	OLD_ACTIVE_NOW=${OLD_ACTIVE_NOW# }
	OLD_STAMPS_NOW=${OLD_STAMPS_NOW# }
}

# The units that run again or were started again since they were stopped.
old_changed_units() {
	local -A before=()
	local p list=
	for p in $(state_get OLD_STAMPS); do before[${p%%=*}]=${p#*=}; done
	for p in $OLD_STAMPS_NOW; do
		# A start sets a new, non-zero time; 0 or nothing means systemd unloaded the unit.
		case "${p#*=}" in "" | 0) continue ;; esac
		if [ "${before[${p%%=*}]-}" != "${p#*=}" ]; then list="$list ${p%%=*}"; fi
	done
	for p in $OLD_ACTIVE_NOW; do
		case " $list " in *" $p "*) ;; *) list="$list $p" ;; esac
	done
	echo "${list# }"
}

# Mask and stop units on the old box and remember when they were last started.
stop_old_units() {
	local unit_list=$1 out
	out=$(remote_bash "$OLD_STOP_SCRIPT" "UNITS=$unit_list") || die "Could not stop the services on the old box."
	if grep -q '^STOPFAILED' <<< "$out"; then
		die "Could not stop all of these on the old box: $unit_list"
	fi
	if grep -q '^NOMASK ' <<< "$out"; then
		warn "Could not mask on the old box (unit file in /etc/systemd/system?): $(sed -n 's/^NOMASK //p' <<< "$out" | tr '\n' ' ')
They are stopped, but something could start them again; the final copy checks for that."
	fi
	old_status
	state_set OLD_STAMPS "$OLD_STAMPS_NOW"
}

# ---------------------------------------------------------------------------
# Phases for the SSH source.

report_overwritten() {
	local d=$1 n m
	n=$(find "$d" -type f 2> /dev/null | wc -l)
	m=$(find "$d/mail/mailboxes" -type f \( -path '*/new/*' -o -path '*/cur/*' \) 2> /dev/null | wc -l)
	state_set OVERWRITTEN_DIRS "$(state_get OVERWRITTEN_DIRS) $d"
	say "$n files that this copy replaced or deleted here are kept in $d."
	if [ "$m" -gt 0 ]; then
		say "$m of them are mail messages (e.g. mail that reached this box after a DNS switch)."
		say "To put one folder of them back into a mailbox later, e.g.:"
		say "  doveadm import -u USER@DOMAIN maildir:$d/mail/mailboxes/DOMAIN/USER '' all"
		say "(see 'man doveadm-import'; messages that are on both boxes then exist twice)."
	fi
}

run_rsync() { # live|final
	local mode=$1
	local args=(-aHAXS --numeric-ids --delete "--partial-dir=$PARTIAL_DIR" --human-readable "--info=progress2,stats2"
		-e "$RSYNC_RSH" "--rsync-path=$RSYNC_PATH"
		"--exclude=/$MARKER" --exclude=/lost+found --exclude=/backup/cache/ "--exclude=/$OVERWRITTEN/")
	if [ -z "$WITH_OWNCLOUD_BACKUP" ]; then args+=(--exclude=/owncloud-backup/); fi
	if [ -n "$SKIP_LOCAL_BACKUPS" ]; then args+=(--exclude=/backup/encrypted/); fi
	if [ -n "$COMPRESS" ]; then args+=(-z); fi
	if [ "$mode" = live ] && [ -n "$BWLIMIT" ]; then args+=(--bwlimit="$BWLIMIT"); fi
	# The file list of the final copy is built first, so the percentage is right from the start.
	if [ "$mode" = final ]; then args+=(--no-inc-recursive); fi

	say "To copy: about $(human "$(state_get SIZE_COPY)") in $(state_get FILES_TOTAL) files and directories (measured"
	say "at the start). rsync shows how much it has copied; its percentage is only reliable"
	say "once it no longer shows 'ir-chk' (it is still reading the file list)."

	local clean_partial='' try=0 rc started bdir wait
	local st=() extra=()
	if [ "$(state_get RSYNC_INTERRUPTED)" = 1 ]; then clean_partial=1; fi
	state_set RSYNC_INTERRUPTED 1
	started=$(date +%s)
	while :; do
		try=$((try + 1))
		extra=() bdir=
		if [ "$(state_get NEW_RAN_LIVE)" = 1 ]; then
			# This machine ran as the mail server: keep what the copy replaces or deletes.
			bdir=$STORAGE_ROOT/$OVERWRITTEN/$(date -u +%Y%m%dT%H%M%SZ)-$mode-$try
			extra=(--backup "--backup-dir=$bdir")
		fi
		set +e
		rsync "${args[@]}" "${extra[@]}" "$SSH_TARGET:$STORAGE_ROOT/" "$STORAGE_ROOT/" 2>&1 \
			| python3 -I -c "$PROGRESS_PY" "$STATE_DIR/rsync-$mode.txt" "$LOG_FILE"
		st=("${PIPESTATUS[@]}")
		set -e
		FAILED_CMD=
		rc=${st[0]}
		if [ -n "$bdir" ] && [ -d "$bdir" ]; then report_overwritten "$bdir"; fi
		case "$rc" in
			10 | 12 | 30 | 35 | 255)
				if [ "$try" -le 3 ]; then
					wait=$((30 * (1 << (try - 1))))
					warn "rsync lost the connection (exit code $rc). Trying again in $wait seconds ($try of 3)..."
					sleep "$wait"
					continue
				fi
				;;
		esac
		break
	done
	# Also after a failed copy: it may already have replaced the paused custom.yaml.
	repause_backups

	local n
	n=$(sed -n 's/^Number of files: \([0-9,]*\) .*/\1/p' "$STATE_DIR/rsync-$mode.txt" 2> /dev/null | tr -d , | tail -n 1)
	if [ -n "$n" ]; then state_set FILES_TOTAL "$n"; fi
	if [ "$mode" = live ]; then
		state_set LAST_LIVE_SYNC_SECONDS "$(($(date +%s) - started))"
	else
		state_set LAST_FINAL_SYNC_SECONDS "$(($(date +%s) - started))"
	fi

	case "$rc" in
		0) ;;
		24) say "(Some files vanished during the copy. That is normal while the old box is running.)" ;;
		23)
			if [ "$mode" = final ]; then
				die "rsync could not copy everything (exit code 23, see above). Fix the cause and run the command again."
			fi
			warn "rsync could not copy everything (exit code 23). The final copy will try again."
			;;
		*) die "rsync failed with exit code $rc. Run the command again to resume the copy." ;;
	esac
	state_set RSYNC_INTERRUPTED ""
	# The data here is a copy of the old box again.
	state_set NEW_RAN_LIVE ""
	if [ -n "$clean_partial" ]; then
		find "$STORAGE_ROOT" -xdev -type d -name "$PARTIAL_DIR" -prune -exec rm -rf {} + 2> /dev/null || true
	fi
}

phase_sync_live() {
	section "Copying $STORAGE_ROOT while the old box is running"
	# Disabled as well: a reboot before the switch-over must not start them on the copy.
	if local_needs_quiesce; then local_quiesce disable; fi
	say "This is the long part. It can be interrupted and resumed: just run the command again."
	run_rsync live
	phase_mark_done sync_live
	state_set LAST_LIVE_SYNC "$(date -u +%FT%TZ)"
	state_set LIVE_SYNC_COUNT "$(($(state_get LIVE_SYNC_COUNT || true) + 1))"
}

# Mail in the old Postfix queue is not in $STORAGE_ROOT. Try to deliver it
# now, and stop unless the user accepts what is left.
handle_old_queue() {
	read_old_queue
	[ "${OLD[QUEUE_TOTAL]:-0}" -gt 0 ] 2> /dev/null || return 0
	say "${OLD[QUEUE_TOTAL]} messages are in the old box's Postfix queue. Trying to deliver them now (postqueue -f)..."
	remote "postqueue -f" > /dev/null 2>&1 || true
	local _
	for _ in 1 2 3 4 5 6; do
		sleep 10
		read_old_queue
		[ "${OLD[QUEUE_LOCAL]:-1}" != 0 ] || break
	done
	[ "${OLD[QUEUE_TOTAL]:-0}" -gt 0 ] 2> /dev/null || return 0
	remote "postqueue -p" > "$STATE_DIR/old-postqueue.txt" 2> /dev/null || true
	state_set OLD_QUEUE_SAVED "${OLD[QUEUE_TOTAL]}"
	say "Still in the queue: ${OLD[QUEUE_TOTAL]} messages, ${OLD[QUEUE_LOCAL]:-?} of them for mailboxes of the box."
	say "The listing is in $STATE_DIR/old-postqueue.txt. The queue is not migrated; it stays on the old box."
	if [ "${OLD[QUEUE_LOCAL]:-1}" != 0 ]; then
		warn "Mail for the box's own mailboxes is still waiting in the old queue (e.g. spampd or
Dovecot were slow). It would only exist on the old box. To deliver it to the new box after
the switch-over, on the old box:
  postconf -e 'virtual_transport = smtp:[$NEW_PUBLIC_IP]:25'
  postsuper -r ALL; postfix start; postqueue -f
and when 'postqueue -p' shows no more of it: postfix stop, and set virtual_transport back
(its old value is in $STATE_DIR/old-postconf.txt)."
		confirm always "Stop the old box anyway?"
	fi
}

phase_stop_old() {
	section "Stopping the old box"
	read_old_facts
	if [ "${OLD[APT_BUSY]:-0}" = 1 ]; then
		die "Package updates are running on the old box (apt-daily / unattended-upgrades).
Wait until they are finished and run the command again. Nothing was stopped yet."
	fi
	if [ ${#NET_BLOCKERS[@]} -gt 0 ] && [ -z "$SKIP_NETWORK_CHECKS" ]; then
		die "$(printf '%s\n' "${NET_BLOCKERS[@]}")
The old box was not stopped. Fix this first (or use --skip-network-checks)."
	fi
	if [ -n "$ASSUME_YES" ] && [ -z "$SWITCH_OVER" ]; then
		die "--yes does not stop the old box on its own. Add --switch-over, or run without --yes."
	fi
	wait_backup_done " on the old box"
	if [ -n "$BACKUP_WAITED" ]; then
		# The facts (apt) may have changed meanwhile.
		read_old_facts
		if [ "${OLD[APT_BUSY]:-0}" = 1 ]; then
			die "Package updates are running on the old box (apt-daily / unattended-upgrades).
Wait until they are finished and run the command again. Nothing was stopped yet."
		fi
	fi
	handle_old_queue
	session_check

	say "These units will be stopped on $OLD_HOST: ${OLD[ACTIVE_UNITS]:-}"
	say "They are masked in /run until the next reboot of the old box ('systemctl mask --runtime'),"
	say "so that nothing starts them again (sockets, package updates, backups). The data and the"
	say "configuration of the old box are not changed. nsd keeps answering DNS. Mail sent to the"
	say "box meanwhile waits at the senders, who retry for days."
	if [ -s "$STATE_DIR/old-postqueue.txt" ]; then say "The old Postfix queue is listed in $STATE_DIR/old-postqueue.txt."; fi
	confirm "Stop the services on the old box now? The downtime starts."

	# Keep units recorded by an interrupted earlier attempt, for --rollback.
	local list
	list=$(echo "$(state_get OLD_SERVICES) ${OLD[ACTIVE_UNITS]:-}" | tr ' ' '\n' | awk 'NF && !seen[$0]++' | tr '\n' ' ')
	list=${list% }
	[ -n "$list" ] || die "None of the expected services runs on the old box (${OLD[ACTIVE_UNITS]:-nothing found})."
	state_set OLD_SERVICES "$list"
	state_set STOPPED_AT "$(date -u +%FT%TZ)"
	phase_mark_done stop_old
	stop_old_units "$list"
	wait_quiet old
}

phase_sync_final() {
	section "Copying the last changes (old box stopped)"
	old_status
	local changed
	changed=$(old_changed_units)
	if [ -n "$changed" ]; then
		warn "Started again on the old box since it was stopped: $changed. Stopping them again."
		stop_old_units "$(state_get OLD_SERVICES)"
	fi
	wait_quiet old
	if local_needs_quiesce; then local_quiesce disable; fi

	# The users and groups and /etc once more, now that nothing changes on the old box.
	save_old_users
	snapshot_old_etc

	local attempt
	for attempt in 1 2 3; do
		say "Recording counts and key fingerprints of the old box for the final check..."
		remote_bash "$FINGERPRINT_SCRIPT" "SR=$STORAGE_ROOT" > "$STATE_DIR/old-fingerprint.txt" \
			|| die "Could not read the fingerprints of the old box."
		run_rsync final
		# Anything that ran on the old box during the copy may have changed data after rsync read it.
		old_status
		changed=$(old_changed_units)
		if [ -z "$changed" ]; then
			state_set OLD_CHANGED_AFTER_FINAL ""
			phase_mark_done sync_final
			return 0
		fi
		warn "During the final copy these started on the old box: $changed.
What they changed may be missing here. Stopping them again and copying once more ($attempt of 3)."
		stop_old_units "$(state_get OLD_SERVICES)"
		wait_quiet old
	done
	die "Services on the old box keep starting again ($changed). Find out what starts them
('journalctl -u UNIT' on the old box), then run the command again."
}

write_mailinabox_conf() {
	# setup/start.sh treats this as a re-run: it runs setup/migrate.py on the copied
	# data first and keeps STORAGE_USER/STORAGE_ROOT/MTA_STS_MODE. It rewrites the
	# file with the IPs given in the environment (see run_setup). The other
	# settings of a file from an earlier run (FTS=off or NEXTCLOUD_SHARE_SCOPE=all,
	# set after a rehearsal) are kept: setup reads them as its defaults.
	local keep=""
	if [ -f /etc/mailinabox.conf ]; then
		keep=$(grep -E '^[A-Z_][A-Z0-9_]*=' /etc/mailinabox.conf \
			| grep -vE '^(STORAGE_USER|STORAGE_ROOT|PRIMARY_HOSTNAME|PUBLIC_IP|PUBLIC_IPV6|PRIVATE_IP|PRIVATE_IPV6|MTA_STS_MODE)=' || true)
	fi
	{
		cat <<EOF
STORAGE_USER=$STORAGE_USER
STORAGE_ROOT=$STORAGE_ROOT
PRIMARY_HOSTNAME=$NEW_PRIMARY_HOSTNAME
PUBLIC_IP=$NEW_PUBLIC_IP
PUBLIC_IPV6=$NEW_PUBLIC_IPV6
PRIVATE_IP=$NEW_PRIVATE_IP
PRIVATE_IPV6=$NEW_PRIVATE_IPV6
MTA_STS_MODE=$MTA_STS_MODE
EOF
		if [ -n "$keep" ]; then printf '%s\n' "$keep"; fi
	} > /etc/mailinabox.conf.new
	chmod 644 /etc/mailinabox.conf.new
	mv /etc/mailinabox.conf.new /etc/mailinabox.conf
	state_set CONF_WRITTEN 1
}

# Only one box may ever back up to a backup target. Until the migration is
# finished, the copied backup/custom.yaml is replaced by "target: off" here.
pause_backups() {
	local b=$STORAGE_ROOT/backup
	[ -d "$b" ] || return 0
	if [ -e "$b/custom.yaml.migrate-saved" ] || [ -e "$b/custom.yaml.migrate-none" ]; then return 0; fi
	if [ -f "$b/custom.yaml" ]; then
		mv "$b/custom.yaml" "$b/custom.yaml.migrate-saved"
	else
		: > "$b/custom.yaml.migrate-none"
	fi
	printf '%s\n' "# Backups paused by migrate-to-2604.sh until the migration is finished." \
		"# The real settings are in custom.yaml.migrate-saved." 'target: "off"' > "$b/custom.yaml"
	chmod 600 "$b/custom.yaml"
	state_set BACKUPS_PAUSED 1
	say "Backups are paused on this machine until the migration is finished (backup/custom.yaml)."
}

# A copy (rsync --delete) replaces the paused backup/custom.yaml with the old
# box's real one and removes custom.yaml.migrate-saved/-none: pause again, with
# the settings just copied as the saved ones.
repause_backups() {
	local b=$STORAGE_ROOT/backup
	[ "$(state_get BACKUPS_PAUSED)" = 1 ] && [ -d "$b" ] || return 0
	# Still the paused file (an interrupted copy may have removed only its
	# marker; the next copy brings the real one).
	if grep -qs '^# Backups paused by migrate-to-2604\.sh' "$b/custom.yaml"; then return 0; fi
	rm -f "$b/custom.yaml.migrate-saved" "$b/custom.yaml.migrate-none"
	pause_backups
}

resume_backups() {
	local b=$STORAGE_ROOT/backup
	if [ -e "$b/custom.yaml.migrate-saved" ]; then
		mv "$b/custom.yaml.migrate-saved" "$b/custom.yaml"
		say "Backups resumed with the old box's settings (backup/custom.yaml${OLD[BACKUP_TARGET]:+, target ${OLD[BACKUP_TARGET]}})."
	elif [ -e "$b/custom.yaml.migrate-none" ]; then
		rm -f "$b/custom.yaml" "$b/custom.yaml.migrate-none"
		say "Backups resumed (local backups, the default)."
	fi
	state_set BACKUPS_PAUSED ""
}

# The work of phase_prepare, also used by the rehearsal.
prepare_machine() {
	write_mailinabox_conf
	say "Wrote /etc/mailinabox.conf for $NEW_PRIMARY_HOSTNAME ($NEW_PUBLIC_IP ${NEW_PUBLIC_IPV6:-})."

	local tz=${OLD[TIMEZONE]:-}
	if [ "$(state_get SOURCE_MODE)" = ssh ] && [ -z "$KEEP_TIMEZONE" ] && [ -n "$tz" ] \
		&& [ -e "/usr/share/zoneinfo/$tz" ] \
		&& [ "$tz" != "$(timedatectl show -p Timezone --value 2> /dev/null || true)" ]; then
		say "Setting the time zone to $tz, as on the old box."
		timedatectl set-timezone "$tz" || warn "Could not set the time zone."
	fi

	# The SSH key for rsync backup targets (setup/system.sh only creates one if
	# it is missing), so that the backup server keeps accepting this box.
	if [ -s "$STATE_DIR/old-id_rsa_miab" ] && [ ! -f /root/.ssh/id_rsa_miab ]; then
		say "Taking over the backup SSH key /root/.ssh/id_rsa_miab."
		install -d -m 700 /root/.ssh
		install -m 600 "$STATE_DIR/old-id_rsa_miab" /root/.ssh/id_rsa_miab
		if [ -s "$STATE_DIR/old-id_rsa_miab.pub" ]; then
			install -m 644 "$STATE_DIR/old-id_rsa_miab.pub" /root/.ssh/id_rsa_miab.pub
		fi
	fi

	# The greylisting exceptions are a fork feature that lives in /etc
	# (setup/mail-postfix.sh reads the file). Not in a backup: only over SSH.
	local gb=/etc/postfix/greylist_bypass_senders
	if [ -f "$STATE_DIR/old-etc$gb" ] && [ ! -e "$gb" ]; then
		say "Taking over the greylisting exceptions $gb from the old box."
		install -D -m 644 "$STATE_DIR/old-etc$gb" "$gb"
	fi

	if [ "$(state_get SOURCE_MODE)" = ssh ]; then
		pause_backups
		# rsync copied numeric IDs. The system users (opendkim, spampd, postgrey,
		# user-data, ...) get other IDs here and do not exist yet. Park every owner
		# that is not already the same here at ID + offset; setup re-owns its own
		# directories by name, and phase_ownership maps the rest by name.
		say "Parking file owners that are unknown here (placeholder IDs)..."
		python3 -I -c "$UIDMAP_PY" shift "$STORAGE_ROOT" "$ID_OFFSET" \
			"$STATE_DIR/old-passwd" "$STATE_DIR/old-group" "$OVERWRITTEN" \
			|| die "Could not change the owners in $STORAGE_ROOT."
	fi
}

phase_prepare() {
	section "Preparing this machine"
	prepare_machine
	phase_mark_done prepare
}

# Run this fork's setup/start.sh. Sets SETUP_SECONDS.
run_setup() {
	local nc=${OLD[NC_VERSION]:-$(state_get NC_VERSION)}
	if [ -n "$nc" ] && [ "${nc%%.*}" -lt 34 ] 2> /dev/null; then
		say "Nextcloud is upgraded step by step from $nc to 34 (one major version per step,"
		say "SQLite database). Depending on the size of the database this takes from"
		say "minutes to more than an hour. A copy of the database goes to owncloud-backup/."
	fi
	local envs=(NONINTERACTIVE=1 SKIP_NETWORK_CHECKS=1
		"PRIMARY_HOSTNAME=$NEW_PRIMARY_HOSTNAME"
		"PUBLIC_IP=$NEW_PUBLIC_IP" "PUBLIC_IPV6=$NEW_PUBLIC_IPV6"
		"STORAGE_USER=$STORAGE_USER" "STORAGE_ROOT=$STORAGE_ROOT")
	if [ -n "$NEW_PRIVATE_IP" ]; then envs+=("PRIVATE_IP=$NEW_PRIVATE_IP"); fi
	if [ -n "$NEW_PRIVATE_IPV6" ]; then envs+=("PRIVATE_IPV6=$NEW_PRIVATE_IPV6"); fi

	local rc=0 started
	started=$(date +%s)
	(cd "$MIAB_DIR" && env "${envs[@]}" setup/start.sh) < /dev/null || rc=$?
	FAILED_CMD=
	SETUP_SECONDS=$(($(date +%s) - started))
	say "Setup ran for $(fmt_dur "$SETUP_SECONDS")."
	return "$rc"
}

phase_setup() {
	section "Running Mail-in-a-Box setup ($(cd "$MIAB_DIR" && git describe --always --tags 2> /dev/null || echo "$MIAB_DIR"))"
	local_unquiesce
	if [ "$(state_get SOURCE_MODE)" = ssh ]; then
		# From here on this machine may receive mail: later copies keep what they replace.
		state_set NEW_RAN_LIVE 1
		state_set SETUP_STARTED_AT "$(date -u +%FT%TZ)"
	fi
	local rc=0
	run_setup || rc=$?
	if [ "$rc" != 0 ]; then
		die "Setup failed (exit code $rc). See the output above and $LOG_FILE.
Fix the cause and run this command again; it continues with setup."
	fi
	state_set SETUP_SECONDS "$SETUP_SECONDS"
	# Setup does not start cron, and it was stopped here before the copy.
	systemctl start cron.service 2> /dev/null || true
	phase_mark_done setup
}

restart_local_services() {
	local s
	for s in postfix dovecot opendkim opendmarc spampd postgrey nginx "php$PHP_VER-fpm" mailinabox munin-node cron; do
		if systemctl cat "$s.service" > /dev/null 2>&1; then
			systemctl restart "$s" || warn "$s did not start, see 'journalctl -u $s'."
		fi
	done
}

map_owners() {
	python3 -I -c "$UIDMAP_PY" map "$STORAGE_ROOT" "$ID_OFFSET" \
		"$STATE_DIR/old-passwd" "$STATE_DIR/old-group" "$OVERWRITTEN" \
		|| die "Could not change the owners in $STORAGE_ROOT. Run the command again after fixing the cause."
}

# --from-backup: there is no list of the old users. Fix what belongs to the
# storage user and report every owner that setup does not use.
fix_restored_owners() {
	local su sg f
	su=$(id -u "$STORAGE_USER")
	sg=$(id -g "$STORAGE_USER")
	chown "$STORAGE_USER:$STORAGE_USER" "$STORAGE_ROOT"
	if [ -f "$STORAGE_ROOT/mailinabox.version" ]; then chown "$STORAGE_USER:$STORAGE_USER" "$STORAGE_ROOT/mailinabox.version"; fi
	if [ -d "$STORAGE_ROOT/www" ]; then chown -R "$STORAGE_USER:$STORAGE_USER" "$STORAGE_ROOT/www"; fi
	# The storage user's dotfiles (its home directory is $STORAGE_ROOT).
	find "$STORAGE_ROOT" -mindepth 1 -maxdepth 1 -name '.*' ! -name "$MARKER" ! -name "$OVERWRITTEN" \
		-exec chown -R "$STORAGE_USER:$STORAGE_USER" {} + 2> /dev/null || true

	f=$STATE_DIR/foreign-owners.txt
	find "$STORAGE_ROOT" -xdev \( -nouser -o -nogroup \
		-o \( -uid +999 ! -uid 65534 ! -uid "$su" \) -o \( -gid +999 ! -gid 65534 ! -gid "$sg" \) \) \
		-printf '%U:%G (%u:%g) %p\n' 2> /dev/null > "$f" || true
	if [ -s "$f" ]; then
		warn "$(wc -l < "$f") files in $STORAGE_ROOT have owners that setup does not use. duplicity restored
them with the old numbers, which may belong to other accounts here (e.g. 1000). Owners and counts:"
		cut -d' ' -f1,2 "$f" | sort | uniq -c | sort -rn | head -n 15
		say "All of them are listed in $f. Change them with chown where needed."
	fi
}

phase_ownership() {
	section "Fixing file owners"
	if [ "$(state_get SOURCE_MODE)" = ssh ]; then
		map_owners
	else
		fix_restored_owners
	fi
	say "Restarting the services..."
	restart_local_services
	phase_mark_done ownership
}

phase_extras() {
	section "Copying Z-Push device state and munin graphs"
	if [ -n "$NO_EXTRAS" ]; then
		say "Skipped (--no-extras)."
		phase_mark_done extras
		return 0
	fi
	local args=(-aHAX --numeric-ids -e "$RSYNC_RSH" --rsync-path="$RSYNC_PATH")
	if [ "${OLD[HAS_ZPUSH]:-0}" = 1 ]; then
		# Same Z-Push 2.7 state format; without it every phone does a full resync.
		mkdir -p /var/lib/z-push
		rsync "${args[@]}" "$SSH_TARGET:/var/lib/z-push/" /var/lib/z-push/ || warn "Could not copy the Z-Push state."
		chown -R www-data:www-data /var/lib/z-push
		chmod 750 /var/lib/z-push
		say "Z-Push state copied."
	fi
	if [ "${OLD[HAS_MUNIN]:-0}" = 1 ] && id munin > /dev/null 2>&1; then
		mkdir -p /var/lib/munin
		rsync "${args[@]}" "$SSH_TARGET:/var/lib/munin/" /var/lib/munin/ || warn "Could not copy the munin data."
		chown -R munin:munin /var/lib/munin
		say "munin graphs copied."
	fi
	systemctl restart "php$PHP_VER-fpm" || true
	phase_mark_done extras
}

# --rehearse: setup on the live copy while the old box keeps running. It
# installs the packages ahead of time and measures how long setup takes.
do_rehearsal() {
	section "Rehearsal: running setup on the copy (the old box keeps running)"
	say "Setup runs here on the data copied so far. Cron and the backups stay off here, and"
	say "the Mail-in-a-Box services here are stopped and disabled afterwards. Nothing on the old box"
	say "changes. The switch-over later copies the data again and runs setup once more."
	confirm "Run the rehearsal now?"
	prepare_machine
	local_unquiesce
	# Keep cron off: no backups, no Nextcloud reminder mails from the copy. Bring the
	# installed packages up to date first, so that no package update restarts it.
	say "Updating the installed packages..."
	apt-get -q -q update < /dev/null || true
	DEBIAN_FRONTEND=noninteractive apt-get -q -q -y upgrade < /dev/null || warn "apt-get upgrade failed; setup tries again."
	# Disabled too, so that a reboot does not start it (local_unquiesce enables it again).
	local_disable cron.service
	systemctl mask --runtime --quiet cron.service 2> /dev/null || true
	systemctl stop cron.service 2> /dev/null || true
	state_set LOCAL_MASKED 1
	local rc=0
	run_setup || rc=$?
	if [ "$rc" != 0 ]; then
		local_quiesce disable
		die "Setup failed during the rehearsal (exit code $rc). Nothing on the old box was changed.
Fix the cause (see the output above), then run --rehearse again, or continue as usual."
	fi
	section "Rehearsal: file owners"
	map_owners
	# Disabled as well: the rehearsal upgraded the packages, and a reboot
	# (new kernel) must not start cron and the services on the copy.
	local_quiesce disable
	state_set REHEARSAL_SETUP_SECONDS "$SETUP_SECONDS"
	state_set REHEARSED_AT "$(date -u +%FT%TZ)"
	section "Rehearsal done"
	say "Setup took $(fmt_dur "$SETUP_SECONDS"). The packages are installed now; the services here are"
	say "stopped again. Before the switch-over the next run copies the data again (old box running)."
	say
	estimate_downtime
	say
	say "Next: $SELF --sync-only to refresh the copy, then $SELF for the switch-over."
}

# ---------------------------------------------------------------------------
# Restore from a backup.

backup_passphrase() {
	# Like management/backup.py: only the first line of secret_key.txt is used
	# (gpg reads only one line; CRLF line endings from a copy via Windows are removed).
	local pass
	pass=$(head -n 1 "$BACKUP_KEY" | tr -d '\r\n[:space:]')
	[ ${#pass} -ge 43 ] || return 1
	printf '%s' "$pass"
}

phase_restore() {
	section "Restoring $STORAGE_ROOT from the backup"
	[ -r "$BACKUP_KEY" ] || die "Cannot read the backup key $BACKUP_KEY (--backup-key)."
	local url=$FROM_BACKUP
	if [[ $url != *://* ]]; then
		[ -d "$url" ] || die "$url is not a directory."
		url="file://$(cd "$url" && pwd)"
	fi
	if ! command -v duplicity > /dev/null; then install_packages duplicity; fi
	# duplicity restores owners by name. Create the storage user now (as setup
	# would), so that its files get its ID here and not the old number.
	if ! id -u "$STORAGE_USER" > /dev/null 2>&1; then
		say "Creating the user $STORAGE_USER (as setup does)."
		useradd -m "$STORAGE_USER"
	fi
	say "Restoring from $url. This takes a while for big boxes and starts over when interrupted."
	local pass
	pass=$(backup_passphrase) || die "The first line of $BACKUP_KEY is too short for a Mail-in-a-Box backup key (secret_key.txt)."
	mkdir -p "$STATE_DIR/duplicity-cache"
	PASSPHRASE=$pass duplicity restore --force --progress \
		--archive-dir "$STATE_DIR/duplicity-cache" "$url" "$STORAGE_ROOT" \
		|| die "duplicity could not restore the backup. Remote targets (S3, B2, rsync) may need
their credentials in the environment; see README-fork.md for the manual way."

	# Backups leave out $STORAGE_ROOT/backup. Put the key back so that this box
	# can read the old backups and continue them.
	install -d -m 700 "$STORAGE_ROOT/backup"
	if [ ! -f "$STORAGE_ROOT/backup/secret_key.txt" ]; then
		install -m 600 "$BACKUP_KEY" "$STORAGE_ROOT/backup/secret_key.txt"
	fi
	state_get TARGET_OWNER > "$STORAGE_ROOT/$MARKER"
	phase_mark_done restore
}

preflight_backup() {
	section "Checking the backup"
	BACKUP_KEY=${BACKUP_KEY:-$(state_get BACKUP_KEY)}
	[ -n "$BACKUP_KEY" ] || die "--from-backup needs --backup-key (the old box's backup/secret_key.txt)."
	[ -r "$BACKUP_KEY" ] || blocker "Cannot read the backup key $BACKUP_KEY."
	if [ -r "$BACKUP_KEY" ] && ! backup_passphrase > /dev/null; then
		blocker "The first line of $BACKUP_KEY is too short for a Mail-in-a-Box backup key (secret_key.txt)."
	fi
	state_set SOURCE_MODE backup
	state_set FROM_BACKUP "$FROM_BACKUP"
	state_set BACKUP_KEY "$BACKUP_KEY"
	STORAGE_ROOT=${OPT_STORAGE_ROOT:-$(state_get STORAGE_ROOT)}
	STORAGE_ROOT=${STORAGE_ROOT:-/home/user-data}
	STORAGE_USER=$(state_get STORAGE_USER)
	STORAGE_USER=${STORAGE_USER:-user-data}
	MTA_STS_MODE=enforce
	[[ $STORAGE_ROOT == /* && $STORAGE_ROOT != *" "* ]] || die "--storage-root must be an absolute path without spaces."
	state_set STORAGE_ROOT "$STORAGE_ROOT"
	state_set STORAGE_USER "$STORAGE_USER"
	if [ -n "$CHECK_ONLY" ]; then
		check_target "$STORAGE_ROOT" "backup:$FROM_BACKUP"
	else
		claim_target "$STORAGE_ROOT" "backup:$FROM_BACKUP"
	fi
	if [[ $FROM_BACKUP != *://* ]]; then
		[ -d "$FROM_BACKUP" ] || blocker "$FROM_BACKUP is not a directory."
		local size avail
		size=$(du -s -B1 "$FROM_BACKUP" 2> /dev/null | cut -f1 || echo 0)
		avail=$(df -B1 --output=avail "$(nearest_dir "$STORAGE_ROOT")" | tail -n 1 | tr -d ' ')
		say "Backup size:       $(human "$size") (compressed; the restored data is bigger)"
		say "Free on this box:  $(human "$avail")"
	fi
}

after_restore_checks() {
	local cfg=$STORAGE_ROOT/owncloud/config.php nc
	if [ -f "$cfg" ]; then
		nc=$(sed -n "s/^[[:space:]]*'version'[[:space:]]*=>[[:space:]]*'\([0-9.]*\)'.*/\1/p" "$cfg" | head -n 1)
		state_set NC_VERSION "$nc"
		if [ -n "$nc" ] && [ "${nc%%.*}" -lt 26 ] 2> /dev/null; then
			die "The backup has Nextcloud $nc. This fork's upgrade chain starts at Nextcloud 26.
Restore it on Ubuntu 22.04 with upstream Mail-in-a-Box v78 first, or migrate from that box."
		fi
	fi
	if [ -z "$OPT_HOSTNAME" ] && [ -z "$(state_get NEW_PRIMARY_HOSTNAME)" ] && [ -f "$STORAGE_ROOT/ssl/ssl_certificate.pem" ]; then
		OPT_HOSTNAME=$(openssl x509 -in "$STORAGE_ROOT/ssl/ssl_certificate.pem" -noout -subject -nameopt multiline 2> /dev/null \
			| sed -n 's/^ *commonName *= *//p' | head -n 1)
		if [ -n "$OPT_HOSTNAME" ]; then say "Hostname from the restored TLS certificate: $OPT_HOSTNAME"; fi
	fi
}

# ---------------------------------------------------------------------------
# Verification and the report.

compare_fingerprints() {
	local k o n status
	printf '  %-16s %-18s %-18s %s\n' "" "old box" "new box" ""
	for k in USERS ALIASES MAILBOXES MESSAGES SIEVE_SCRIPTS DKIM_KEY DNSSEC_KEYS TLS_KEY BACKUP_KEY LE_ACCOUNTS BAYES_SPAM BAYES_HAM NC_ACCOUNTS NC_CARDS NC_EVENTS; do
		o=${OLDFP[$k]:-}
		n=${NEWFP[$k]:-}
		if [ "$o" = "$n" ]; then
			status=OK
		elif [[ $k =~ ^(MESSAGES|BAYES_SPAM|BAYES_HAM)$ && $o =~ ^[0-9]+$ && $n =~ ^[0-9]+$ ]] && [ "$n" -ge "$o" ]; then
			status="OK (new mail since)"
		elif [[ $k =~ ^(MAILBOXES)$ && $o =~ ^[0-9]+$ && $n =~ ^[0-9]+$ ]] && [ "$n" -ge "$o" ]; then
			# Mail-in-a-Box keeps the mail directory of a deleted user, so
			# accounts added (or added and removed) since the switch-over
			# only ever raise this number.
			status="OK (new mailboxes since)"
		else
			status=DIFFERENT
			VERIFY_PROBLEMS+=("$k differs: old box ${o:--}, new box ${n:--}")
		fi
		printf '  %-16s %-18s %-18s %s\n' "$k" "${o:--}" "${n:--}" "$status"
	done
}

# The items (split at commas) of the smtpd_*_restrictions in BEFORE (output of
# "postconf -n") that are gone now, as "parameter: item". Setup rewrites these
# parameters and drops what an administrator added (e.g. a check_sender_access
# before greylisting). A DNS list that only got return codes (upstream v68:
# zen.spamhaus.org -> zen.spamhaus.org=127.0.0.[2..11]) is not gone. Keep in
# sync with tools/upgrade-in-place-to-2604.sh.
postfix_restrictions_gone() { # BEFORE
	local ref=$1 p old now item
	[ -s "$ref" ] || return 0
	for p in smtpd_client_restrictions smtpd_helo_restrictions smtpd_sender_restrictions smtpd_relay_restrictions \
		smtpd_recipient_restrictions smtpd_data_restrictions smtpd_end_of_data_restrictions; do
		old=$(sed -n "s/^${p}[[:space:]]*=[[:space:]]*//p" "$ref")
		[ -n "$old" ] || continue
		now=$(postconf -h "$p" 2> /dev/null | restriction_items | sed 's/=.*//')
		while IFS= read -r item; do
			grep -qxF -- "${item%%=*}" <<< "$now" || echo "$p: $item"
		done < <(restriction_items <<< "$old")
	done
}

restriction_items() {
	tr ',' '\n' | sed 's/^[[:space:]]*//; s/[[:space:]]*$//; s/[[:space:]][[:space:]]*/ /g; /^$/d'
}

etc_report() {
	local out=$STATE_DIR/etc-report.txt old=$STATE_DIR/old-etc gone line
	[ -d "$old/etc" ] || return 0
	gone=$(postfix_restrictions_gone "$STATE_DIR/old-postconf.txt")
	{
		echo "Customizations of the old box that are NOT migrated (they live in /etc,"
		echo "not in $STORAGE_ROOT). The old /etc (as of $(state_get ETC_SAVED_AT)) is in"
		echo "$STATE_DIR/old-etc.tar.gz and unpacked in $old."
		echo
		echo "== Postfix restrictions of the old box that are gone here (redo them in main.cf)"
		if [ -n "$gone" ]; then sed 's/^/  /' <<< "$gone"; fi
		echo
		echo "== Postfix settings of the old box (postconf -n) that differ here"
		if [ -s "$STATE_DIR/old-postconf.txt" ]; then
			diff <(sort "$STATE_DIR/old-postconf.txt") <(postconf -n 2> /dev/null | sort) | sed -n 's/^< /  /p' || true
		fi
		echo
		echo "== Files named in the old Postfix settings that are missing or different here"
		if [ -s "$STATE_DIR/old-postconf.txt" ]; then
			grep -oE '/etc/[A-Za-z0-9_./-]+' "$STATE_DIR/old-postconf.txt" | sort -u | while read -r f; do
				if [ ! -f "$old$f" ]; then continue; fi
				if [ ! -e "$f" ]; then
					echo "  missing here:  $f"
				elif ! cmp -s "$old$f" "$f"; then
					echo "  different:     $f"
				fi
			done
		fi
		echo
		echo "== Files of the old box that do not exist here"
		local d
		for d in postfix postgrey spamassassin dovecot nginx fail2ban opendkim opendmarc.conf nsd munin \
			cron.d cron.hourly cron.daily cron.weekly cron.monthly systemd/system ssh/sshd_config.d \
			logrotate.d sudoers.d apt/sources.list.d ufw/applications.d; do
			[ -e "$old/etc/$d" ] || continue
			(cd "$old" && find "etc/$d" -type f) | while read -r f; do
				[ -e "/$f" ] || echo "  /$f"
			done
		done
		echo
		echo "== Firewall rules of the old box (/etc/ufw/user.rules, compare with 'ufw status')"
		grep -E '^### tuple' "$old/etc/ufw/user.rules" 2> /dev/null | sed 's/^### tuple ### /  /' || true
		echo
		echo "== Crontab of root on the old box"
		grep -vE '^[[:space:]]*(#|$)' "$STATE_DIR/old-root-crontab.txt" 2> /dev/null | sed 's/^/  /' || true
	} > "$out"
	say "Customizations of the old /etc that were not migrated: $out"
	sed -n '1,80p' "$out"
	# Restrictions decide which mail is accepted: a lost one is a failed check
	# (redo it, or accept with --finish), not only a line in the report.
	if [ -n "$gone" ]; then
		while IFS= read -r line; do
			warn "Postfix restriction of the old box is gone: $line"
			VERIFY_PROBLEMS+=("Postfix restriction of the old box is gone: $line (see $out)")
		done <<< "$gone"
	fi
}

dns_next_steps() {
	local py=/usr/local/lib/mailinabox/env/bin/python zones=()
	if [ -f /etc/nsd/nsd.conf.d/zones.conf ]; then
		mapfile -t zones < <(sed -n 's/^[[:space:]]*name:[[:space:]]*//p' /etc/nsd/nsd.conf.d/zones.conf)
	fi
	if [ ${#zones[@]} -eq 0 ] || [ ! -x "$py" ]; then return 0; fi
	"$py" -I - "$NEW_PRIMARY_HOSTNAME" "${zones[@]}" <<'PY' || true
import sys
import dns.resolver
r = dns.resolver.Resolver(configure=False)
r.nameservers = ["9.9.9.9", "1.1.1.1"]
r.lifetime = 6
host = sys.argv[1].lower().rstrip(".")
for z in sys.argv[2:]:
	try:
		ns = sorted(str(x.target).lower().rstrip(".") for x in r.resolve(z, "NS"))
	except Exception as e:
		print("     %-30s NS unknown (%s)" % (z, type(e).__name__))
		continue
	own = any(n == "ns1." + host or n == "ns2." + host for n in ns)
	print("     %-30s %s  (NS: %s)" % (z, "served by this box" if own else "external DNS", " ".join(ns)))
PY
}

# The custom secondary nameservers (System > Custom DNS, "_secondary_nameserver").
secondary_nameservers() {
	local f=$STORAGE_ROOT/dns/custom.yaml py=/usr/local/lib/mailinabox/env/bin/python
	[ -f "$f" ] || return 0
	if [ -x "$py" ]; then
		"$py" -I - "$f" <<'PY' 2> /dev/null && return 0
import sys, yaml
with open(sys.argv[1], encoding="utf-8") as f:
	c = yaml.safe_load(f) or {}
v = c.get("_secondary_nameserver")
if isinstance(v, dict):
	v = v.get("A")
if isinstance(v, list):
	v = " ".join(str(x) for x in v)
if v:
	print(v)
PY
	fi
	sed -n 's/^_secondary_nameserver:[[:space:]]*//p' "$f" | tr -d "'\""
}

next_steps() {
	section "Next steps"
	local old_ip=${OLD[CONF_PUBLIC_IP]:-} old_ip6=${OLD[CONF_PUBLIC_IPV6]:-} host=$NEW_PRIMARY_HOSTNAME sec
	say "1. Test this box BEFORE you change DNS. On your own computer, add the line"
	say "     $NEW_PUBLIC_IP $host"
	say "   to /etc/hosts (Windows: C:\\Windows\\System32\\drivers\\etc\\hosts), open"
	say "   https://$host/admin and https://$host/mail, log in, send a test mail through"
	say "   this box (SMTP submission) and receive one, check Nextcloud (files, contacts,"
	say "   calendars). Remove the line again afterwards. Webmail users must log in again"
	say "   (setup gives Roundcube a new key); spam filter (Bayes) and greylisting data were"
	say "   taken over as they are."
	say
	say "2. DNS. Zones and who serves them:"
	dns_next_steps
	if [ -n "$old_ip" ] && [ "$old_ip" = "$NEW_PUBLIC_IP" ] && [ "$old_ip6" = "$NEW_PUBLIC_IPV6" ]; then
		say "   * The IP addresses did not change. Nothing to change in DNS."
	else
		say "   * Zones served by this box (NS ns1/ns2.$host): change the glue records"
		say "     ns1.$host and ns2.$host at the registrar to $NEW_PUBLIC_IP ${NEW_PUBLIC_IPV6:-}."
		say "     The DS records stay the same, the DNSSEC keys were taken over."
		say "     Resolvers keep the NS/glue records for the TTL the TLD sets (e.g. 2 days for .com,"
		say "     1 day for .de) and the records of these zones for up to 1 day (Mail-in-a-Box uses"
		say "     TTL 86400). Until then the old box's nsd keeps answering, with the OLD IPs: expect"
		say "     1 to 3 days in which some senders and clients still try the stopped old box."
		say "     Senders queue the mail and retry (usually for 4-5 days; some send a delay warning"
		say "     after a few hours). To shorten this, let the old nsd hand out the new IPs:"
		say "       $SELF --push-zones-to-old"
		say "   * Zones with external DNS: change the A/AAAA records of $host (and the ones"
		say "     listed in the admin panel under System > External DNS) to the new IPs. That"
		say "     takes effect within their TTL."
		sec=$(secondary_nameservers || true)
		if [ -n "$sec" ]; then
			say "   * Custom secondary nameservers are set: $sec"
			say "     Change the primary (master) IP at that DNS provider to $NEW_PUBLIC_IP ${NEW_PUBLIC_IPV6:-}."
			say "     Until then it keeps fetching the zones from the old IP (and serves the old ones"
			say "     for up to 14 days, the SOA expire time, if the old box is switched off)."
		fi
		say "   * Set the reverse DNS (PTR) of $NEW_PUBLIC_IP ${NEW_PUBLIC_IPV6:+and $NEW_PUBLIC_IPV6 }to $host"
		say "     with the hosting provider, if not done yet."
		say "   * MX records point to $host and need no change while the hostname stays the"
		say "     same. SPF records with explicit ip4:/ip6: entries must be changed."
	fi
	say
	say "3. Afterwards:"
	say "   * Check /var/log/mail.log here once DNS points to this box."
	if [ "$(state_get SOURCE_MODE)" = ssh ]; then
		if [ -n "$(state_get OLD_QUEUE_SAVED)" ]; then
			say "   * The old Postfix queue (not migrated) is listed in $STATE_DIR/old-postqueue.txt."
		fi
		if [ "$(state_get BACKUPS_PAUSED)" = 1 ]; then
			say "   * Backups are PAUSED here until the checks pass (or '$SELF --finish')."
		else
			say "   * Backups: target '${OLD[BACKUP_TARGET]:-local}' and secret_key.txt were taken over;"
			say "     check System > Backup Status after the next night. Only one box may ever back up"
			say "     to a backup target: never start the old box's services again (a reboot does)."
		fi
		say "   * The old box stays stopped; its units are masked until it reboots. Do not reboot it."
		say "     '$SELF --check-old' shows whether anything runs there again. Switch it off"
		say "     when DNS has switched over (glue TTL plus a day). Until then '$SELF --rollback'"
		say "     starts its services again."
		say "   * Review $STATE_DIR/etc-report.txt for customizations to redo by hand."
		say "   * $STATE_DIR holds a copy of the old /etc (with password hashes and keys);"
		say "     delete it when you no longer need it."
		if [ -n "$(state_get OVERWRITTEN_DIRS)" ]; then
			say "   * Files kept from earlier attempts: $STORAGE_ROOT/$OVERWRITTEN (delete when no longer needed)."
		fi
	else
		say "   * Backups: secret_key.txt was put back, but a backup does not contain the backup"
		say "     settings (backup/custom.yaml). Set the target again under System > Backup Status."
	fi
}

phase_verify() {
	section "Checking the new box"
	VERIFY_PROBLEMS=()
	local out
	out=$(local_bash "$FINGERPRINT_SCRIPT" "SR=$STORAGE_ROOT") || true
	NEWFP=()
	load_kv NEWFP <<< "$out"
	if [ -f "$STATE_DIR/old-fingerprint.txt" ]; then
		OLDFP=()
		load_kv OLDFP < "$STATE_DIR/old-fingerprint.txt"
		compare_fingerprints
	else
		local k
		for k in "${!NEWFP[@]}"; do printf '  %-16s %s\n' "$k" "${NEWFP[$k]}"; done | sort
	fi

	say
	local s st
	for s in postfix dovecot opendkim spampd postgrey nsd nginx "php$PHP_VER-fpm" mailinabox fail2ban cron; do
		st=$(systemctl is-active "$s" 2> /dev/null || true)
		printf '  %-16s %s\n' "$s" "$st"
		if [ "$st" != active ]; then VERIFY_PROBLEMS+=("service $s is $st"); fi
	done

	say
	if [ -f /usr/local/lib/owncloud/occ ]; then
		say "Nextcloud:"
		# -e: exit code 1 in maintenance mode, 2 if 'occ upgrade' is needed (and
		# without -v occ status would then print nothing).
		local nc_rc=0 nc_out
		nc_out=$(sudo -u www-data "php$PHP_VER" /usr/local/lib/owncloud/occ status -e -v 2> /dev/null) || nc_rc=$?
		if [ -n "$nc_out" ]; then sed 's/^/  /' <<< "$nc_out"; fi
		# Exit code 1 is also any other occ failure: check the output.
		if [ "$nc_rc" = 1 ] && ! grep -q 'maintenance: true' <<< "$nc_out"; then nc_rc=failed; fi
		case "$nc_rc" in
			0) ;;
			1) VERIFY_PROBLEMS+=("Nextcloud is in maintenance mode (find out why, then 'occ maintenance:mode --off')") ;;
			2) VERIFY_PROBLEMS+=("Nextcloud needs 'occ upgrade'") ;;
			failed) VERIFY_PROBLEMS+=("'occ status' failed (exit code 1)") ;;
			*) VERIFY_PROBLEMS+=("'occ status' failed (exit code $nc_rc)") ;;
		esac
	fi

	if [ -d "$STATE_DIR/old-etc/etc/nsd/zones" ]; then
		local f z n=0 same=0
		for f in "$STATE_DIR"/old-etc/etc/nsd/zones/*.ds; do
			[ -f "$f" ] || continue
			# Only zones the old nsd actually served: a stale .ds file stays
			# behind when e.g. the box's hostname moved into its parent zone.
			z=$(basename "$f" .txt.ds)
			# The name is compared literally (a dot in a regular expression matches any character).
			if [ -f "$STATE_DIR/old-etc/etc/nsd/nsd.conf.d/zones.conf" ] \
				&& ! sed -n 's/^[[:space:]]*name:[[:space:]]*//p' "$STATE_DIR/old-etc/etc/nsd/nsd.conf.d/zones.conf" \
				| tr -d '"' | sed 's/[[:space:]]*$//' | grep -xF -- "$z" > /dev/null; then
				continue
			fi
			n=$((n + 1))
			# Compare as sets: the order of the records in the file is not stable.
			if [ -f "/etc/nsd/zones/$(basename "$f")" ] \
				&& [ "$(sort "$f")" = "$(sort "/etc/nsd/zones/$(basename "$f")")" ]; then
				same=$((same + 1))
			fi
		done
		if [ "$n" -gt 0 ]; then say "DNSSEC DS records unchanged: $same of $n zones."; fi
		if [ "$same" != "$n" ]; then VERIFY_PROBLEMS+=("DS records changed for $((n - same)) of $n zones (would break DNSSEC)"); fi
	fi

	say
	say "Running the status checks (DNS checks fail until DNS points to this box)..."
	(cd "$MIAB_DIR" && management/status_checks.py) > "$STATE_DIR/status-checks.txt" 2>&1 || true
	say "  $(grep -c '^✓' "$STATE_DIR/status-checks.txt" || true) ok, $(grep -c '^?' "$STATE_DIR/status-checks.txt" || true) warnings, $(grep -c '^✖' "$STATE_DIR/status-checks.txt" || true) errors - full report: $STATE_DIR/status-checks.txt"
	grep '^✖' "$STATE_DIR/status-checks.txt" | head -n 25 | sed 's/^/  /' || true

	if [ "$(state_get SOURCE_MODE)" = ssh ]; then
		say
		etc_report
		old_status
		local changed
		changed=$(old_changed_units)
		if [ -n "$changed" ]; then
			# Kept in the state, so that a second check does not forget it.
			state_set OLD_CHANGED_AFTER_FINAL "$(state_get OLD_CHANGED_AFTER_FINAL) $changed"
			stop_old_units "$(state_get OLD_SERVICES)"
		fi
		changed=$(state_get OLD_CHANGED_AFTER_FINAL)
		if [ -n "$changed" ]; then
			VERIFY_PROBLEMS+=("Started again on the old box after the final copy:$changed. Changes made there since are not here; '$SELF --redo-from sync-final' copies again")
		fi
	fi

	state_set VERIFY_RAN 1
	if [ ${#VERIFY_PROBLEMS[@]} -eq 0 ]; then
		finish_migration
	fi
}

finish_migration() {
	rm -f "$STORAGE_ROOT/$MARKER"
	if [ "$(state_get BACKUPS_PAUSED)" = 1 ]; then resume_backups; fi
	phase_mark_done verify
	state_set FINISHED_AT "$(date -u +%FT%TZ)"
}

# The last block of a run: the result of the checks.
print_result() {
	section "Result"
	if [ ${#VERIFY_PROBLEMS[@]} -eq 0 ]; then
		say "All checks passed. The migration is finished; follow the next steps above"
		say "(test the box first, then change DNS)."
		return 0
	fi
	local p
	say "These checks FAILED:"
	for p in "${VERIFY_PROBLEMS[@]}"; do say "  - $p"; done
	say
	say "Look at them before you change DNS. Backups stay paused here. The old box stays stopped."
	say "  check again:          $SELF"
	say "  accept the result:    $SELF --finish"
	say "  back to the old box:  $SELF --rollback"
	VERIFY_FAILED=1
	exit 2
}

# ---------------------------------------------------------------------------
# Commands.

phase_label() { echo "${1//_/-}"; }

do_status() {
	[ -f "$STATE_FILE" ] || {
		say "No migration state in $STATE_DIR."
		return 0
	}
	if [ -n "$VERBOSE" ]; then
		sed -e '/^SSH_KEY=/d' "$STATE_FILE" | sort
		return 0
	fi
	local -a list
	local p next='' v
	if [ "$(state_get SOURCE_MODE)" = backup ]; then
		list=("${PHASES_BACKUP[@]}")
		say "Source:          backup $(state_get FROM_BACKUP)"
	else
		list=("${PHASES_SSH[@]}")
		say "Source:          $(state_get FROM) (over SSH)"
	fi
	say "Data:            $(state_get STORAGE_ROOT) ($(human "$(state_get SIZE_COPY)"), $(state_get FILES_TOTAL) files)"
	say "New box:         $(state_get NEW_PRIMARY_HOSTNAME)  $(state_get NEW_PUBLIC_IP) $(state_get NEW_PUBLIC_IPV6)"
	v=$(state_get LAST_LIVE_SYNC)
	if [ -n "$v" ]; then
		say "Last live copy:  $v (took $(fmt_dur "$(state_get LAST_LIVE_SYNC_SECONDS)"), $(state_get LIVE_SYNC_COUNT) copies so far)"
	fi
	v=$(state_get REHEARSED_AT)
	if [ -n "$v" ]; then say "Rehearsal:       $v (setup took $(fmt_dur "$(state_get REHEARSAL_SETUP_SECONDS)"))"; fi
	say "Phases:"
	for p in "${list[@]}"; do
		if phase_is_done "$p"; then
			say "  done     $(phase_label "$p")"
		else
			say "  pending  $(phase_label "$p")"
			[ -n "$next" ] || next=$p
		fi
	done
	if old_box_is_down; then
		say "Old box:         services STOPPED since $(state_get STOPPED_AT) (downtime)"
	elif [ -n "$(state_get ROLLED_BACK_AT)" ] && ! phase_is_done stop_old; then
		say "Old box:         running again since the rollback at $(state_get ROLLED_BACK_AT)"
	fi
	if [ "$(state_get BACKUPS_PAUSED)" = 1 ]; then say "Backups here:    paused until the migration is finished"; fi
	if [ "$(state_get ZONES_PUSHED)" = 1 ]; then say "DNS zones:       pushed to the old box's nsd"; fi
	v=$(state_get OVERWRITTEN_DIRS)
	if [ -n "$v" ]; then say "Kept files:      $v"; fi
	if [ -n "$(state_get FINISHED_AT)" ] && phase_is_done verify; then
		say "Finished:        $(state_get FINISHED_AT)"
		return 0
	fi
	if [ "$(state_get VERIFY_RAN)" = 1 ] && [ "$next" = verify ]; then
		say "Next:            the final check failed; run '$SELF' to check again or '$SELF --finish'"
	else
		say "Next:            $(phase_label "${next:-sync_live}")  ('$SELF' continues)"
	fi
	if old_box_is_down; then say "Rollback:        $SELF --rollback"; fi
}

do_check_old() {
	[ "$(state_get SOURCE_MODE)" = ssh ] || die "Only for a migration with --from."
	ssh_from_state
	if [ -z "$(state_get OLD_SERVICES)" ]; then
		say "This tool has not stopped anything on the old box (or it was rolled back)."
		return 0
	fi
	old_status
	local changed
	changed=$(old_changed_units)
	say "Stopped on $OLD_HOST since $(state_get STOPPED_AT): $(state_get OLD_SERVICES)"
	if [ -z "$changed" ]; then
		say "Nothing of it was started again."
		return 0
	fi
	warn "Started again since then: $changed${OLD_ACTIVE_NOW:+ (running now: $OLD_ACTIVE_NOW)}."
	if ! phase_is_done sync_final; then
		say "The final copy has not run yet; it stops them again."
	else
		say "Mail or data changed there since the final copy is not on this box. Stop them on"
		say "the old box (systemctl stop ...) and find out what started them."
	fi
	IN_DIE=1 USER_STOPPED=1
	exit 1
}

do_rollback() {
	[ "$(state_get SOURCE_MODE)" = ssh ] || die "Rollback is only possible for a migration with --from."
	ssh_from_state
	STORAGE_ROOT=$(state_get STORAGE_ROOT)
	local list
	list=$(state_get OLD_SERVICES)
	[ -n "$list" ] || die "No services of the old box were stopped by this tool (or an earlier --rollback started them again)."
	local rev=() s
	for s in $list; do rev=("$s" "${rev[@]}"); done

	section "Rollback to the old box"
	say "This machine: stop and disable the Mail-in-a-Box services (until the next attempt),"
	say "              and pause the backups."
	say "Old box ($OLD_HOST): unmask and start again: ${rev[*]}"
	if [ "$(state_get ZONES_PUSHED)" = 1 ]; then say "              and put its own DNS zone files back ($OLD_NSD_SAVE)."; fi
	if [ "$(state_get NEW_RAN_LIVE)" = 1 ] || [ -n "$(state_get FINISHED_AT)" ]; then
		warn "This machine has run as the mail server since $(state_get SETUP_STARTED_AT).
If DNS already points here, change it back first (glue records / A records), and know that
mail received here since then is NOT on the old box and is not copied back. The next attempt
keeps whatever its copy replaces here in $STORAGE_ROOT/$OVERWRITTEN/."
		confirm always "Roll back to the old box anyway?"
	else
		confirm "Roll back to the old box?"
	fi

	# This machine first, so that the two boxes are never live at the same time.
	# Backups paused first, so that they stay paused here even if a later step fails.
	pause_backups
	if [ -f /etc/mailinabox.conf ]; then local_quiesce disable rollback; fi
	if [ "$(state_get ZONES_PUSHED)" = 1 ]; then
		# Restore and reload separately: once the restore removed $OLD_NSD_SAVE,
		# only the reload is left to do by hand.
		# shellcheck disable=SC2016 # expanded on the old box
		if remote_bash 'if [ -d "$SAVE" ]; then cp -a "$SAVE/." /etc/nsd/zones/ && rm -rf "$SAVE"; fi' \
			"SAVE=$OLD_NSD_SAVE"; then
			state_set ZONES_PUSHED ""
			remote "systemctl reload nsd || nsd-control reload" > /dev/null 2>&1 \
				|| warn "Put the old box's own zone files back, but could not reload nsd there ('systemctl reload nsd' there)."
		else
			warn "Could not put the old box's own zone files back. On the old box, run:
  cp -a $OLD_NSD_SAVE/. /etc/nsd/zones/ && rm -rf $OLD_NSD_SAVE   # if $OLD_NSD_SAVE still exists
  systemctl reload nsd || nsd-control reload"
		fi
	fi
	# The queue hint of the stop (handle_old_queue) may have pointed virtual_transport
	# to this machine and started Postfix outside systemd on the old box: undo both,
	# so that systemd starts Postfix with the old setting.
	local vt out ip ip6
	vt=$(sed -n 's/^virtual_transport = //p' "$STATE_DIR/old-postconf.txt" 2> /dev/null | head -n 1)
	# A sync_final run after the queue hint was applied snapshots the redirected
	# value: never "restore" a transport to this machine, use the Mail-in-a-Box default.
	ip=$(state_get NEW_PUBLIC_IP)
	ip6=$(state_get NEW_PUBLIC_IPV6)
	if { [ -n "$ip" ] && [[ $vt == *"[$ip]"* ]]; } || { [ -n "$ip6" ] && [[ $vt == *"[$ip6]"* ]]; }; then
		warn "The saved virtual_transport of the old box ($vt) points to this machine; using lmtp:[127.0.0.1]:10025."
		vt="lmtp:[127.0.0.1]:10025"
	fi
	out=$(remote_bash "$OLD_POSTFIX_RESET_SCRIPT" "VT=$vt") || warn "Could not check Postfix on the old box."
	if grep -q '^VTFIXED ' <<< "$out"; then
		warn "virtual_transport on the old box was '$(sed -n 's/^VTFIXED //p' <<< "$out")', set back to '$vt'."
	fi
	if grep -q '^PFSTOPPED' <<< "$out"; then
		warn "Postfix ran on the old box outside systemd (postfix start); stopped it, systemd starts it now."
	fi
	remote_bash "$OLD_START_SCRIPT" "UNITS=$list" "START=${rev[*]}" \
		|| die "Could not start the services on the old box. On the old box, run:
  postfix status && postfix stop  # if it was started by hand
  postconf virtual_transport      # set it back if it points to this machine${vt:+ (old value: $vt)}
  systemctl unmask --runtime $list
  systemctl start ${rev[*]}"
	# Mail that waited for this machine is delivered on the old box now.
	if grep -q '^VTFIXED \|^PFSTOPPED' <<< "$out"; then remote "postqueue -f" > /dev/null 2>&1 || true; fi
	# The data here is now behind the old box: start over from the live copy next time.
	state_set PHASE_stop_old ""
	phases_reset_from sync_final
	state_set OLD_SERVICES ""
	state_set OLD_STAMPS ""
	state_set VERIFY_RAN ""
	state_set FINISHED_AT ""
	state_set ROLLED_BACK_AT "$(date -u +%FT%TZ)"
	say
	say "The old box runs again. This machine's Mail-in-a-Box services are stopped and disabled,"
	say "and its backups are paused. To make a new attempt, run the migration command again: it"
	say "copies the data again and continues. Once this machine has been live for a while, do"
	say "not roll back any more: the mail it received would be missing on the old box."
}

do_finish() {
	[ "$(state_get VERIFY_RAN)" = 1 ] || die "Run the migration up to the final check first."
	if phase_is_done verify; then
		say "The migration is already finished ($(state_get FINISHED_AT))."
		return 0
	fi
	STORAGE_ROOT=$(state_get STORAGE_ROOT)
	confirm "Accept the result of the last check and finish the migration (backups here resume)?"
	finish_migration
	say "The migration is marked as finished. Backups run here again from the next night on."
}

do_push_zones() {
	[ "$(state_get SOURCE_MODE)" = ssh ] || die "Only for a migration with --from."
	phase_is_done setup || die "Run this after the migration (setup has not run here yet)."
	ssh_from_state
	local here=() f old_names push=() skip=()
	for f in /etc/nsd/zones/*.signed; do
		if [ -f "$f" ]; then here+=("$(basename "$f")"); fi
	done
	[ ${#here[@]} -gt 0 ] || die "This machine has no signed DNS zones in /etc/nsd/zones."
	old_names=$(remote_bash "sed -n 's/^[[:space:]]*zonefile:[[:space:]]*//p' /etc/nsd/nsd.conf.d/zones.conf | tr -d '\"' | sed 's#.*/##'") \
		|| die "Could not read the zones of the old box."
	for f in "${here[@]}"; do
		if grep -qxF "$f" <<< "$old_names"; then push+=("$f"); else skip+=("$f"); fi
	done
	[ ${#push[@]} -gt 0 ] || die "The old box serves none of this machine's zones."

	section "Serving this box's DNS zones from the old box"
	say "Resolvers that still have the old glue records ask the old box's nsd. With this,"
	say "it answers with the new IPs. The old box's zone files are replaced:"
	say "  ${push[*]}"
	if [ ${#skip[@]} -gt 0 ]; then say "Not served by the old box, left out: ${skip[*]}"; fi
	say "This is the one change to files on the old box. Its own zone files are kept in"
	say "$OLD_NSD_SAVE there; --rollback puts them back. Its nsd keeps these zones until"
	say "it is switched off (the signatures are valid for about 30 days)."
	confirm "Copy the zones to the old box now?"
	# shellcheck disable=SC2016 # expanded on the old box
	remote_bash 'if [ ! -d "$SAVE" ]; then mkdir -p "$SAVE" && cp -a /etc/nsd/zones/. "$SAVE/"; fi' "SAVE=$OLD_NSD_SAVE" \
		|| die "Could not save the old box's zone files."
	# shellcheck disable=SC2029 # REMOTE_SUDO is meant to expand here
	tar -C /etc/nsd/zones -cf - "${push[@]}" \
		| ssh "${SSH_ARGS[@]}" "$SSH_TARGET" "${REMOTE_SUDO}tar -C /etc/nsd/zones --no-same-owner -xf -" \
		|| die "Could not copy the zones to the old box."
	remote "systemctl reload nsd || nsd-control reload" || warn "Could not reload nsd on the old box ('systemctl reload nsd' there)."
	state_set ZONES_PUSHED 1
	say "Done. Check it with: dig +short @${OLD[CONF_PUBLIC_IP]:-$OLD_HOST} $(state_get NEW_PRIMARY_HOSTNAME) A"
}

check_summary() {
	section "Result of the check"
	local b all=()
	all=("${CHECK_BLOCKERS[@]}")
	for b in "${NET_BLOCKERS[@]}"; do all+=("$b (blocks the switch-over; --skip-network-checks)"); done
	session_check
	if [ ${#all[@]} -eq 0 ]; then
		say "No blockers found. Nothing was changed on either machine."
		say "Start the migration with:"
		say "  $SELF --from $FROM${SSH_KEY:+ --ssh-key $SSH_KEY}${SSH_PORT:+ --ssh-port $SSH_PORT}"
		exit 0
	fi
	say "These must be fixed first:"
	for b in "${all[@]}"; do say "  - $b"; done
	say "Nothing was changed on either machine."
	exit 1
}

main() {
	FROM='' FROM_BACKUP='' BACKUP_KEY='' SSH_KEY='' SSH_PORT='' OPT_HOSTNAME='' OPT_PUBLIC_IP=''
	OPT_PUBLIC_IPV6='' OPT_PRIVATE_IP='' OPT_PRIVATE_IPV6='' OPT_STORAGE_ROOT='' KEEP_TIMEZONE=''
	SYNC_ONLY='' BWLIMIT='' COMPRESS='' WITH_OWNCLOUD_BACKUP='' SKIP_LOCAL_BACKUPS='' NO_EXTRAS=''
	ASSUME_YES='' REDO_FROM='' COMMAND=migrate REHEARSE='' SWITCH_OVER='' SKIP_NETWORK_CHECKS='' VERBOSE=''
	NO_TMUX=''
	local orig_args=("$@")

	while [ $# -gt 0 ]; do
		case "$1" in
			--from | --from-backup | --backup-key | --ssh-key | --ssh-port | --hostname | --public-ip | --public-ipv6 \
				| --private-ip | --private-ipv6 | --storage-root | --bwlimit | --redo-from)
				if [ $# -lt 2 ] || [ -z "$2" ]; then die "$1 needs a value. See --help."; fi
				case "$1" in
					--from) FROM=$2 ;;
					--from-backup) FROM_BACKUP=$2 ;;
					--backup-key) BACKUP_KEY=$2 ;;
					--ssh-key) SSH_KEY=$2 ;;
					--ssh-port) SSH_PORT=$2 ;;
					--hostname) OPT_HOSTNAME=$2 ;;
					--public-ip) OPT_PUBLIC_IP=$2 ;;
					--public-ipv6) OPT_PUBLIC_IPV6=$2 ;;
					--private-ip) OPT_PRIVATE_IP=$2 ;;
					--private-ipv6) OPT_PRIVATE_IPV6=$2 ;;
					--storage-root) OPT_STORAGE_ROOT=$2 ;;
					--bwlimit) BWLIMIT=$2 ;;
					--redo-from) REDO_FROM=$2 ;;
				esac
				shift 2
				;;
			--keep-timezone) KEEP_TIMEZONE=1; shift ;;
			--sync-only) SYNC_ONLY=1; shift ;;
			--rehearse) REHEARSE=1; shift ;;
			--switch-over) SWITCH_OVER=1; shift ;;
			--skip-network-checks) SKIP_NETWORK_CHECKS=1; shift ;;
			--compress) COMPRESS=1; shift ;;
			--with-owncloud-backup) WITH_OWNCLOUD_BACKUP=1; shift ;;
			--skip-local-backups) SKIP_LOCAL_BACKUPS=1; shift ;;
			--no-extras) NO_EXTRAS=1; shift ;;
			--yes | -y) ASSUME_YES=1; shift ;;
			--no-tmux) NO_TMUX=1; shift ;;
			--check | --dry-run) CHECK_ONLY=1; shift ;;
			--verbose) VERBOSE=1; shift ;;
			--rollback) COMMAND=rollback; shift ;;
			--status) COMMAND=status; shift ;;
			--check-old) COMMAND=check_old; shift ;;
			--finish) COMMAND=finish; shift ;;
			--push-zones-to-old) COMMAND=push_zones; shift ;;
			-h | --help) usage; exit 0 ;;
			*) die "Unknown option $1. See --help." ;;
		esac
	done
	if [ "$OPT_PUBLIC_IPV6" = none ]; then
		die "--public-ipv6 none is not supported: setup always uses the IPv6 address it detects
on this machine (also on later runs). To have no IPv6, remove it from the machine."
	fi

	[ "$(id -u)" = 0 ] || die "This must be run as root on the new machine. Did you leave out sudo?"
	# Absolute path of this script (for messages), before leaving the working directory.
	if [[ ${BASH_SOURCE[0]:-} == *.sh ]] && [ -f "${BASH_SOURCE[0]}" ]; then
		SELF_FILE=$(readlink -f "${BASH_SOURCE[0]}")
		SELF=$SELF_FILE
	fi
	cd /
	trap 'on_err "$LINENO" "$BASH_COMMAND"' ERR
	trap on_exit EXIT

	case "$COMMAND" in
		status)
			do_status
			return 0
			;;
	esac

	if [ -n "$CHECK_ONLY" ]; then
		[ "$COMMAND" = migrate ] || die "--check only works for a migration (--from or --from-backup)."
		CHECK_TMP=$(mktemp -d)
		local d
		if d=$(checkout_dir); then check_checkout_owner "$d"; fi
	else
		if [ "$COMMAND" = migrate ]; then
			resolve_miab_dir "${orig_args[@]}"
		fi
		(umask 077 && mkdir -p "$STATE_DIR")
		chmod 700 "$STATE_DIR"
		# From the real file (after the clone); --check-old changes nothing.
		if [ "$COMMAND" != check_old ]; then run_in_multiplexer "${orig_args[@]}"; fi
		exec > >(tee -a "$LOG_FILE") 2>&1
		LOG_READY=1
		echo
		echo "=== migrate-to-2604.sh $(date -u +%FT%TZ) ${orig_args[*]}"
	fi

	case "$COMMAND" in
		rollback) do_rollback; return 0 ;;
		check_old) do_check_old; return 0 ;;
		finish) do_finish; return 0 ;;
		push_zones) do_push_zones; return 0 ;;
	esac

	if [ -n "$FROM" ] && [ -n "$FROM_BACKUP" ]; then die "Use either --from or --from-backup."; fi
	if [ -z "$FROM" ] && [ -z "$FROM_BACKUP" ]; then
		# Continue a migration with the recorded source.
		case "$(state_get SOURCE_MODE)" in
			ssh) FROM=$(state_get FROM) ;;
			backup) FROM_BACKUP=$(state_get FROM_BACKUP) ;;
			*) usage; exit 1 ;;
		esac
	fi
	if [ -n "$FROM" ]; then
		SSH_KEY=${SSH_KEY:-$(state_get SSH_KEY)}
		SSH_PORT=${SSH_PORT:-$(state_get SSH_PORT)}
	fi
	if [ -n "$BWLIMIT" ] && ! [[ $BWLIMIT =~ ^[0-9]+$ ]]; then die "--bwlimit takes KiB/s as a number."; fi
	if [ -n "$REHEARSE" ] && [ -n "$SYNC_ONLY" ]; then die "Use either --rehearse or --sync-only."; fi

	preflight_local

	if [ -n "$REDO_FROM" ] && [ -z "$CHECK_ONLY" ]; then
		case "$REDO_FROM" in
			sync-final)
				phase_is_done stop_old || die "--redo-from sync-final needs a stopped old box."
				if [ "$(state_get NEW_RAN_LIVE)" = 1 ] || phase_is_done verify; then
					warn "This machine has run as the mail server. Copying from the old box again REPLACES
the mail and all other changes made here since with the old box's data (what is replaced
is kept in $(state_get STORAGE_ROOT)/$OVERWRITTEN/)."
					confirm always "Really copy everything from the old box again?"
				fi
				phases_reset_from sync_final
				;;
			setup | extras | verify) phases_reset_from "$REDO_FROM" ;;
			*) die "--redo-from takes sync-final, setup, extras or verify." ;;
		esac
	fi

	if phase_is_done verify && [ -z "$REDO_FROM" ]; then
		say "This migration is finished ($(state_get FINISHED_AT)). Use --redo-from verify to check again,"
		say "--status to see the state."
		return 0
	fi

	if [ -n "$FROM" ]; then
		migrate_ssh
	else
		migrate_backup
	fi
}

migrate_ssh() {
	if [ -n "$ASSUME_YES" ] && [ -z "$SYNC_ONLY$REHEARSE$SWITCH_OVER$CHECK_ONLY" ] && ! phase_is_done stop_old; then
		die "--yes does not start the downtime on its own. Use '--sync-only --yes' for unattended
copying and run the switch-over attended, or add --switch-over to stop the old box
unattended right after the copy."
	fi
	ssh_init
	preflight_old
	STORAGE_ROOT=${OLD[CONF_STORAGE_ROOT]:-}
	STORAGE_USER=${OLD[CONF_STORAGE_USER]:-user-data}
	MTA_STS_MODE=${OLD[CONF_MTA_STS_MODE]:-enforce}
	[[ $STORAGE_ROOT == /* && $STORAGE_ROOT != *" "* && $STORAGE_ROOT != / ]] \
		|| die "Unexpected STORAGE_ROOT '$STORAGE_ROOT' on the old box."
	if [ -n "$OPT_STORAGE_ROOT" ] && [ "$OPT_STORAGE_ROOT" != "$STORAGE_ROOT" ]; then
		die "--storage-root cannot change the path with --from (Nextcloud keeps it in config.php)."
	fi
	state_set STORAGE_ROOT "$STORAGE_ROOT"
	state_set STORAGE_USER "$STORAGE_USER"
	state_set NC_VERSION "${OLD[NC_VERSION]:-}"

	section "Checking this machine"
	local key
	key=$(old_owner_key)
	check_target "$STORAGE_ROOT" "$key"
	if [ -n "$CHECK_ONLY" ]; then check_big_ids "$(nearest_dir "$STORAGE_ROOT")"; fi
	check_space "$STORAGE_ROOT"
	choose_new_settings
	network_checks

	if [ -n "$CHECK_ONLY" ]; then
		show_plan_ssh
		check_summary
	fi

	if ! phase_is_done stop_old; then
		[ -z "$REHEARSE" ] || phase_is_done sync_live || say "The rehearsal first makes the live copy."
		show_plan_ssh
		if [ "$(state_get NEW_RAN_LIVE)" = 1 ]; then
			warn "This machine has already run as the mail server (setup ran here before a rollback).
Copying from the old box again REPLACES $STORAGE_ROOT here, including mail that reached this
machine. What the copy replaces or deletes is kept in $STORAGE_ROOT/$OVERWRITTEN/."
			confirm always "Copy the old box's data over this machine's data again?"
		elif ! phase_is_done sync_live; then
			confirm "Start copying? The old box keeps running."
		fi
		claim_target "$STORAGE_ROOT" "$key"
		save_reference
		session_check
		phase_sync_live
		if [ -n "$REHEARSE" ]; then
			do_rehearsal
			return 0
		fi
		if [ -n "$SYNC_ONLY" ]; then
			say
			say "Live copy done ($(state_get LAST_LIVE_SYNC), took $(fmt_dur "$(state_get LAST_LIVE_SYNC_SECONDS)"))."
			say "Run the command again with --sync-only to refresh it, with --rehearse to try setup,"
			say "or without them to switch over."
			return 0
		fi
		phase_stop_old
	else
		[ -z "$SYNC_ONLY$REHEARSE" ] || die "The old box is already stopped; --sync-only and --rehearse make no sense now. Run without them to continue."
		claim_target "$STORAGE_ROOT" "$key"
	fi
	phase_is_done sync_final || phase_sync_final
	phase_is_done prepare || phase_prepare
	phase_is_done setup || phase_setup
	phase_is_done ownership || phase_ownership
	phase_is_done extras || phase_extras
	phase_verify
	next_steps
	print_result
}

migrate_backup() {
	preflight_backup
	if [ -n "$CHECK_ONLY" ]; then
		section "Plan"
		say "Restore $FROM_BACKUP into $STORAGE_ROOT, then run setup (hostname from --hostname"
		say "or the restored TLS certificate)."
		check_summary
	fi
	if ! phase_is_done restore; then
		confirm "Restore the backup into $STORAGE_ROOT?"
		phase_restore
	fi
	after_restore_checks
	choose_new_settings
	if ! phase_is_done prepare; then
		section "Plan"
		say "Hostname:  $NEW_PRIMARY_HOSTNAME"
		say "IPs:       $NEW_PUBLIC_IP ${NEW_PUBLIC_IPV6:-}"
		say "Data:      $STORAGE_ROOT (user $STORAGE_USER)"
		network_checks
		confirm "Run setup for $NEW_PRIMARY_HOSTNAME on the restored data?"
		phase_prepare
	fi
	phase_is_done setup || phase_setup
	phase_is_done ownership || phase_ownership
	phase_verify
	next_steps
	print_result
}

main "$@"
