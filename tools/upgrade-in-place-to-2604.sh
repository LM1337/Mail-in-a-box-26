#!/bin/bash
#########################################################
# Upgrade a Mail-in-a-Box IN PLACE to Ubuntu 26.04 and this fork.
#
# Run this as root on the box itself. Check first (changes nothing), then
# upgrade (started from a terminal outside tmux or screen, it runs itself in
# the tmux session upgrade-2604, see run_in_multiplexer):
#
#   /root/mailinabox-fork/tools/upgrade-in-place-to-2604.sh --check
#   /root/mailinabox-fork/tools/upgrade-in-place-to-2604.sh
#
# or without a checkout of this repository (like setup/bootstrap.sh):
#
#   curl -s https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/tools/upgrade-in-place-to-2604.sh \
#     | sudo bash -s -- --check
#
# Supported boxes:
#  * Ubuntu 22.04 with official Mail-in-a-Box v60 or later and Nextcloud 26 or
#    later: release upgrade to 24.04, reboot, release upgrade to 26.04, reboot.
#  * Ubuntu 24.04 that was itself release-upgraded in place and still runs
#    Mail-in-a-Box v7x (PHP 8.0 from ppa:ondrej, Dovecot 2.3): one release
#    upgrade to 26.04, reboot.
#  * Ubuntu 26.04 with this fork already: setup runs again (like "sudo mailinabox").
#
# Moving to a fresh machine (tools/migrate-to-2604.sh) is the safer way. This
# tool is for boxes that cannot move (IP addresses, provider contracts).
#
# Phases (the state is kept in /root/upgrade-2604, so the command can be run
# again after an interruption and continues where it stopped; after each
# reboot a systemd unit continues it on its own):
#
#   1. preflight        check everything (also alone, with --check)
#   2. snapshot         archive of /etc and the code outside $STORAGE_ROOT,
#                       an encrypted copy of it next to the backups; then
#                       mail goes OFFLINE (mail/web/cron/apt timers stopped
#                       and masked, also across reboots), so that the fresh
#                       Mail-in-a-Box backup holds all mail; fingerprint
#                       (with --skip-miab-backup or backups off, mail keeps
#                       running until quiesce)
#   3. quiesce          backups paused; mail goes OFFLINE here if it is not
#                       yet
#   4. prepare-release  third-party apt sources off, PHP from ppa:ondrej
#                       removed, packages up to date, Prompt=lts
#   5. release-2404     do-release-upgrade 22.04 -> 24.04, reboot (22.04 only)
#   6. release-2604     do-release-upgrade 24.04 -> 26.04, reboot
#   7. cleanup-etc      pristine Dovecot 2.4 configuration, old PHP versions,
#                       the old Python environment, ntp; config checks
#   8. setup            this fork's setup/start.sh on the existing data
#                       (Nextcloud upgrade chain to 34)
#   9. local-ext        the operator's hook scripts (see below)
#  10. verify           compare the fingerprint, services, Nextcloud, DNSSEC,
#                       status checks, changed configuration
#  11. finish           services unmasked, backups resumed
#      cleanup-old      with --cleanup (or alone, --cleanup-only): obsolete
#                       packages and leftovers of the old releases
#
# Local extensions. Files that neither Mail-in-a-Box nor a package put into
# /etc/dovecot, systemd drop-ins for the mail units and extra files in
# /etc/nginx/conf.d block the upgrade unless --keep-local is given: Dovecot
# 2.4 does not read 2.3 configuration, and /etc/dovecot is replaced by a
# pristine copy before setup. To bring such extensions back, put hook scripts
# into /etc/mailinabox/upgrade-2604.d/*.sh. They run in phase local-ext, after
# setup and before verify. Two more stages are for services of the operator
# that use the mail (e.g. a docker compose stack that logs in by IMAP):
#   /etc/mailinabox/upgrade-2604.d/before/*.sh  right before mail goes offline
#       (stop_mail; on a box that only runs setup again: before setup);
#   /etc/mailinabox/upgrade-2604.d/after/*.sh   in phase finish, after mail
#       and the backups are back (and at the end of --rollback); if the final
#       check fails, right after it (mail runs again), and not again in finish.
# All hooks run in the order of their names:
#   * as root, with bash, in /, stdin from /dev/null;
#   * with the environment variables HOOK_STAGE (before, local-ext, after),
#     STORAGE_ROOT, PRIMARY_HOSTNAME, MIAB_DIR (this fork's checkout; in
#     stage before and after --rollback the old one), OLD_ETC
#     (/root/upgrade-2604/old-etc, a copy of /etc as it was before the
#     upgrade; missing on a box that only runs setup again),
#     MOVED_DIR (/root/upgrade-2604/moved, everything this tool moved out of
#     the way, at its original path) and UPGRADE_STATE_DIR;
#   * a non-zero exit code makes the phase fail in stages before and
#     local-ext (fix the hook, run again; all hooks of the stage run again, so
#     write them so that they can run twice); in stage after it is only a
#     warning (the upgrade is not undone).
# After the hooks of local-ext, "doveconf -n" must succeed without warnings.
#
# See --help.
#########################################################

# Everything below is inside functions and the last line calls main, so a
# partially downloaded script (curl | bash) does nothing.

set -euo pipefail
set -E # the ERR trap (see on_err) also fires inside functions

# needrestart (run by apt) must not restart services while mail is offline,
# nor the resume unit this may run in: only list what needs a restart.
export NEEDRESTART_SUSPEND=1 NEEDRESTART_MODE=l

STATE_DIR=${UPGRADE_STATE_DIR:-/root/upgrade-2604}
STATE_FILE=$STATE_DIR/state
LOG_FILE=$STATE_DIR/upgrade.log
# A copy of /etc as it was before anything changed (phase snapshot).
OLD_ETC=$STATE_DIR/old-etc
# Everything this tool moves out of the way, at its original path below it.
MOVED_DIR=$STATE_DIR/moved
# Third-party apt sources and keys, disabled for the release upgrades.
APT_DISABLED=$STATE_DIR/apt-disabled
# .deb files of the packages purged before the release upgrade (for --rollback).
PURGED_DEBS=$STATE_DIR/purged-debs
HOOK_DIR=/etc/mailinabox/upgrade-2604.d
# Hook stages before (mail goes offline) and after (finish); see the header.
HOOK_BEFORE_DIR=$HOOK_DIR/before
HOOK_AFTER_DIR=$HOOK_DIR/after
SCRIPT_NAME=upgrade-in-place-to-2604.sh
RESUME_UNIT=mailinabox-upgrade-2604-resume.service
RESUME_UNIT_FILE=/etc/systemd/system/$RESUME_UNIT
RESUME_SCRIPT=$STATE_DIR/resume.sh
RESUME_MAX=8
TMUX_SESSION=upgrade-2604
# The environment variables this script and setup read (passed into that session).
MUX_ENV=(UPGRADE_STATE_DIR UPGRADE_QUIET_TIMEOUT UPGRADE_BACKUP_MAX_AGE UPGRADE_BACKUP_WAIT UPGRADE_REEXEC TAG SOURCE FTS NEXTCLOUD_SHARE_SCOPE FAVICON)
MUX_TERM=
MUX_TTY=
MUX_RAW_TTY=
# Keep the old configuration files during the release upgrades (removed again in finish).
APT_OVERRIDE=/etc/apt/apt.conf.d/99-upgrade-in-place-to-2604
MOTD_FILE=/etc/motd
MOTD_BEGIN="### begin $SCRIPT_NAME"
MOTD_END="### end $SCRIPT_NAME"
DEFAULT_SOURCE=https://github.com/LM1337/Mail-in-a-box-26
# Raw files of the branch main (GitHub serves them from another host).
DEFAULT_RAW=https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main
DEFAULT_TAG=v78-r2604.0-rc6 # keep in sync with setup/bootstrap.sh
CLONE_DIR=/root/mailinabox
PHP_VER=8.5        # keep in sync with setup/functions.sh
PHP_LEGACY_VER=8.2 # keep in sync with setup/system.sh
QUIET_TIMEOUT=${UPGRADE_QUIET_TIMEOUT:-900}
BACKUP_MAX_AGE=${UPGRADE_BACKUP_MAX_AGE:-86400}
# How long to wait for a Mail-in-a-Box backup that is running (wait_backup_done).
BACKUP_WAIT=${UPGRADE_BACKUP_WAIT:-7200}
GIB=$((1024 * 1024 * 1024))

# Phases that are recorded in the state file, in order.
PHASES=(preflight snapshot quiesce prepare_release release_2404 release_2604 cleanup_etc setup local_ext verify finish)
# A box that already runs this fork on 26.04 only runs setup again (of the
# release tag, see update_fork_dir).
PHASES_RERUN=(preflight setup local_ext verify finish)

# Files in /etc/dovecot/conf.d that upstream Mail-in-a-Box (v60..v78) or this
# fork write or edit. More names are read from the fork's setup scripts when a
# checkout is at hand (fork_dovecot_names).
KNOWN_DOVECOT_CONFD="10-auth.conf 10-mail.conf 10-master.conf 10-ssl.conf 15-lda.conf 15-mailboxes.conf
20-imap.conf 20-pop3.conf 20-lmtp.conf 20-managesieve.conf 90-quota.conf 90-sieve.conf 99-local.conf
99-local-auth.conf 99-local-sieve.conf 99-local-spampd.conf auth-sql.conf.ext 95-mailinabox-fts.conf"
KNOWN_DOVECOT_TOP="dovecot-sql.conf.ext sieve-spam.sieve"
# Dovecot full-text search added by hand on 2.3 boxes; the fork's setup
# installs FTS itself (95-mailinabox-fts.conf).
FTS_FILES="05-local-fts-plugins.conf 99-local-fts.conf"
# Never removed by cleanup-old, only reported.
PROTECTED_RE='^(docker|containerd|runc|webmin|snapd|lxd|mysql-client|mariadb-client)'
# apt origins of the third-party sources this fork's setup adds itself.
FORK_ORIGINS_RE='^(deb\.sury\.org|LP-PPA-duplicity-team-duplicity-release-git)$'

declare -A F=() OLDFP=() NEWFP=() STATE_MEM=()
CHECK_BLOCKERS=()
VERIFY_PROBLEMS=()
EXT_BLOCK=()
EXT_INFO=()
EXT_FTS=()
CHECK_ONLY=
BACKUP_WAITED=
LOG_READY=
LOCKED=
IN_DIE=
USER_STOPPED=
FAILED_CMD=
VERIFY_FAILED=
SESSION_CHECKED=
STORAGE_ROOT=
MIAB_DIR=
SELF=$STATE_DIR/$SCRIPT_NAME
SELF_FILE=

# ---------------------------------------------------------------------------
# Output. Keep in sync with tools/migrate-to-2604.sh (blocker differs: it
# always collects, see blockers_or_die).

say() { echo "$*"; }
warn() { echo "WARNING: $*" >&2; }
die() {
	IN_DIE=1
	echo >&2
	echo "ERROR: $*" >&2
	exit 1
}
# A reason not to start the upgrade. Collected; --check lists them at the
# end, a real run stops at the end of the preflight (blockers_or_die).
blocker() {
	CHECK_BLOCKERS+=("$*")
	echo "BLOCKER: $*" >&2
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
Usage: upgrade-in-place-to-2604.sh --check [options]     (start here)
       upgrade-in-place-to-2604.sh [options]
       upgrade-in-place-to-2604.sh --status [--verbose] | --rollback | --finish
                                   | --cleanup-only [--old-checkout]

Upgrades THIS Mail-in-a-Box in place to Ubuntu 26.04 and this fork: Ubuntu
22.04 (Mail-in-a-Box v60 or later) goes through 24.04 to 26.04 with two
reboots, a box already release-upgraded to 24.04 (Mail-in-a-Box v7x) with one
reboot. Nextcloud must be 26 or later. Run it as root. Started from a
terminal outside tmux or screen, it runs itself in the tmux session
"upgrade-2604" (it installs tmux if needed) and attaches to it: if the SSH
connection drops, log in again and run "sudo tmux attach -t upgrade-2604"
(during a release upgrade new logins and sudo can fail for a while: wait, do
not reboot).
Mail is offline from phase "snapshot" on (after the system archive, before
the fresh backup; with --skip-miab-backup or backups turned off from phase
"quiesce") until setup has finished (typically 1-3 hours). After each reboot the upgrade continues on its own;
follow it with "sudo tmux attach -t upgrade-2604" or
"sudo tail -f /root/upgrade-2604/upgrade.log".
Running the command again continues an interrupted upgrade.

Have the provider's console (VNC, KVM or serial) at hand: if the network
does not come up after a reboot, SSH is gone.

Steps:
  --check, --dry-run      only check this machine and show the plan and what
                          blocks the upgrade. Changes nothing (no state, no
                          clone, no packages).
  --redo-from PHASE       run PHASE and the phases after it again: snapshot
                          (only before the first release upgrade),
                          cleanup-etc, setup, local-ext or verify
  --cleanup               after finish, also run cleanup-old: remove obsolete
                          packages and leftovers of the old releases (with
                          --check: only show what it would remove)
  --cleanup-only          run cleanup-old alone (after the upgrade)
  --old-checkout          cleanup-old also deletes the old Mail-in-a-Box
                          checkout (e.g. /root/mailinabox-v74)

Safety nets:
  --no-backup-check       start even though backups are off or the last one is
                          older than 24 hours
  --skip-miab-backup      do not run a fresh Mail-in-a-Box backup in the
                          snapshot phase (mail then keeps running until
                          phase quiesce)
  --no-offsite            keep the system archive only in /root/upgrade-2604
                          (default: an encrypted copy goes next to the backups)
  --keep-local            local extensions (see the header of the script) do
                          not block the upgrade; they are only reported, and
                          the old /etc/dovecot is moved aside before setup.
                          Hooks in /etc/mailinabox/upgrade-2604.d/*.sh can
                          bring them back for Dovecot 2.4; hooks in its
                          before/ and after/ run right before mail goes
                          offline and when the upgrade is finished or its
                          final check failed (e.g. to stop and start
                          services that use the mail).

Control:
  --yes                   do not ask for confirmation, and reboot without the
                          10-second countdown (unattended use)
  --no-tmux               do not start a tmux session of its own (see above)
  --status [--verbose]    show the state of the upgrade (--verbose: raw)
  --rollback              only before the first release upgrade started: put
                          the apt sources and packages back, start the
                          services again, resume the backups
  --finish                accept a final check with differences: start the
                          remaining services, resume the backups
  -h, --help              show this help

Environment: SOURCE and TAG choose the repository and tag of this fork that
setup runs from (default: the release tag). UPGRADE_STATE_DIR (default
/root/upgrade-2604) holds the state, the log, the system archive and the copy
of the old /etc. UPGRADE_QUIET_TIMEOUT (default 900) is how many seconds to
wait for processes that still use the data, UPGRADE_BACKUP_MAX_AGE (default
86400) the age in seconds the last backup may have, UPGRADE_BACKUP_WAIT
(default 7200) how many seconds to wait for a Mail-in-a-Box backup that is
running (e.g. the nightly one) before anything is stopped.
EOF
}

# ---------------------------------------------------------------------------
# State file: KEY=VALUE lines. Values never contain newlines. With --check,
# values are only kept in memory. Keep in sync with tools/migrate-to-2604.sh.

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
	tmp=$(mktemp "$STATE_DIR/.state.XXXXXX") || die "Cannot write to $STATE_DIR (disk full?)."
	{
		if [ -f "$STATE_FILE" ]; then grep -v "^$1=" "$STATE_FILE" || true; fi
		printf '%s=%s\n' "$1" "$2"
	} > "$tmp" || {
		rm -f "$tmp"
		die "Could not write $STATE_FILE (disk full?)."
	}
	mv "$tmp" "$STATE_FILE" || die "Could not write $STATE_FILE."
}

# Add words to a space-separated list in the state (no duplicates, in order).
state_add() {
	local key=$1
	shift
	state_set "$key" "$(echo "$(state_get "$key") $*" | tr ' ' '\n' | awk 'NF && !seen[$0]++' | tr '\n' ' ' | sed 's/ $//')"
}

phase_is_done() { [ "$(state_get "PHASE_$1")" = "done" ]; }
phase_mark_done() { state_set "PHASE_$1" "done"; }

phase_list() {
	if [ "$(state_get MODE)" = rerun ]; then echo "${PHASES_RERUN[@]}"; else echo "${PHASES[@]}"; fi
}

# Forget PHASE and all phases after it.
phases_reset_from() {
	local from=$1 p found=
	for p in $(phase_list); do
		if [ "$p" = "$from" ]; then found=1; fi
		if [ -n "$found" ]; then
			state_set "PHASE_$p" ""
			state_set "START_$p" ""
			state_set "END_$p" ""
		fi
	done
	[ -n "$found" ] || die "Unknown phase $from."
}

# Mail is offline: quiesce ran and finish (or a rollback) did not.
downtime_active() {
	[ -f "$STATE_FILE" ] && [ "$(state_get QUIESCED)" = 1 ] && ! phase_is_done finish
}

# ---------------------------------------------------------------------------
# Error reporting. Every way out of the script with an error ends here: die,
# a failed command under set -e, Ctrl-C. Keep in sync with tools/migrate-to-2604.sh.

on_err() {
	# Remember the last failed command of the main shell for the exit message.
	if [ "$BASH_SUBSHELL" = 0 ]; then FAILED_CMD="line $1: $2"; fi
}

on_exit() {
	local rc=$?
	if [ -n "$LOCKED" ] && [ "$(cat "$STATE_DIR/pid" 2> /dev/null || true)" = "$$" ]; then rm -f "$STATE_DIR/pid"; fi
	[ "$rc" != 0 ] || return 0
	[ -z "$CHECK_ONLY" ] || return 0
	{
		if [ -z "$IN_DIE" ]; then
			echo
			echo "ERROR: the upgrade stopped (exit code $rc)${FAILED_CMD:+ at $FAILED_CMD}."
		fi
		if [ -n "$LOG_READY" ] && [ -z "$VERIFY_FAILED" ] && [ -z "$USER_STOPPED" ]; then
			echo "The full output is in $LOG_FILE."
			echo "Fix the cause and run the command again; it continues where it stopped."
		fi
		if downtime_active && [ -n "$(state_get SETUP_END_EPOCH)" ]; then
			echo
			echo "Mail runs again (setup has finished), but the upgrade is not finished: cron jobs,"
			echo "update timers and backups stay paused. Continue with: $SELF (or --finish)"
		elif downtime_active; then
			echo
			echo "Mail is OFFLINE (since $(state_get QUIESCED_AT)). Continue with: $SELF"
			if [ "$(state_get RELEASE_STARTED)" != 1 ]; then echo "or go back with: $SELF --rollback"; fi
		fi
	} >&2
	return 0
}

# Ask on the terminal (also when the script came through curl | bash).
# "confirm always ..." asks even with --yes. Keep in sync with tools/migrate-to-2604.sh.
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
# tools/migrate-to-2604.sh.
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
		# Through curl | bash the run uses the copy of the release tag. rc1 to
		# rc3 are older than run_in_multiplexer.
		if [ -z "$SELF_FILE" ]; then
			case "${TAG:-$DEFAULT_TAG}" in
				v78-r2604.0-rc[123])
					say "Through curl | bash the command runs the copy of ${TAG:-$DEFAULT_TAG}, which does not start"
					say "tmux by itself. Start the command inside tmux: tmux new -s $TMUX_SESSION"
					return 0
					;;
			esac
		fi
		say "Started from this terminal, the command runs itself in the tmux session $TMUX_SESSION"
		say "(tmux is installed if needed; reattach after a disconnect with: sudo tmux attach -t $TMUX_SESSION)."
		return 0
	fi
	warn "This does not run inside tmux or screen. If your SSH connection drops, a release
upgrade or setup stops halfway (a release upgrade stopped in the middle can leave the
machine unbootable; a Nextcloud upgrade stopped in the middle stays in maintenance mode).
Better: install tmux (apt-get install tmux) and run the command again without --no-tmux:
it then runs itself in tmux (reattach after a disconnect with: sudo tmux attach -t $TMUX_SESSION)."
	if [ -z "$CHECK_ONLY" ]; then confirm "Continue without tmux or screen?"; fi
}

# A command that changes something, started from a terminal outside tmux and
# screen, runs itself in a tmux session (or screen) of its own: a dropped SSH
# connection then only ends the terminal that is attached to it. Not with
# --no-tmux, --check or --resumed, not without a terminal (automation, nohup)
# and not without a script file. Needs tmux 3.0 or later (a command with
# arguments). Keep in sync with tools/migrate-to-2604.sh.

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

# The terminal to attach (MUX_TTY), and the operator's terminal to put into
# raw mode meanwhile (MUX_RAW_TTY). With a terminal as stdin, that terminal.
# Through "curl ... | sudo bash" (stdin is the pipe), sudo with use_pty (22.04,
# 24.04) and sudo-rs (26.04) run this script in a terminal of sudo's own. Both
# pass its output on, but not the keys: classic sudo does not read the
# operator's terminal while stdin is a pipe, so attach that terminal (that of
# the first parent process on another terminal). sudo-rs does read it, and a
# client there would lose keys to it; it passes them on to its own terminal
# when the operator's terminal is in raw mode. Without a terminal (cron,
# nohup, ssh without -t) both stay empty.
mux_tty() {
	local t mine p sid
	MUX_TTY='' MUX_RAW_TTY=''
	if [ -t 0 ]; then
		t=$(tty 2> /dev/null || true)
		if [ -c "$t" ] && [ "$t" != /dev/tty ]; then MUX_TTY=$t; fi
		return 0
	fi
	(: <> /dev/tty) 2> /dev/null || return 0
	mine=$(ps -o tty= -p $$ 2> /dev/null | tr -d ' ' || true)
	case "$mine" in '' | '?') return 0 ;; esac
	MUX_TTY=/dev/$mine
	# Only when sudo itself has the pipe as stdin; with a terminal as its stdin
	# (sudo -i, then curl | bash) sudo passes the keys on.
	sid=$(ps -o sid= -p $$ 2> /dev/null | tr -d ' ' || true)
	case "$(ps -o comm= -p "${sid:-0}" 2> /dev/null || true)" in sudo | sudo.ws | sudo-rs) ;; *) return 0 ;; esac
	case "$(readlink "/proc/$sid/fd/0" 2> /dev/null || true)" in /dev/pts/* | /dev/tty*) return 0 ;; esac
	p=$$
	while [ -n "$p" ] && [ "$p" -gt 1 ]; do
		t=$(ps -o tty= -p "$p" 2> /dev/null | tr -d ' ' || true)
		if [ -n "$t" ] && [ "$t" != '?' ] && [ "$t" != "$mine" ]; then break; fi
		t=''
		p=$(ps -o ppid= -p "$p" 2> /dev/null | tr -d ' ' || true)
	done
	[ -n "$t" ] && [ -c "/dev/$t" ] || return 0
	if "/proc/$sid/exe" --version 2> /dev/null | grep -q sudo-rs; then
		MUX_RAW_TTY=/dev/$t
	else
		MUX_TTY=/dev/$t
	fi
}

# Attach this terminal (also when stdin is the curl pipe, B71). tmux refuses
# the name /dev/tty, so the terminal's own device, opened for reading and
# writing: tmux draws on the descriptor of its stdin, and on one opened only
# for reading (rc4 and rc5) it drew nothing. screen -d -r: a client of a
# dropped SSH connection may still count as attached. Returns 1 without a
# terminal, so that the caller names the attach command.
mux_attach() { # TOOL
	local rc=0 saved=''
	mux_tty
	[ -n "$MUX_TTY" ] || return 1
	if [ -n "$MUX_RAW_TTY" ]; then
		saved=$(stty -g < "$MUX_RAW_TTY" 2> /dev/null || true)
		stty raw -echo < "$MUX_RAW_TTY" 2> /dev/null || true
	fi
	# shellcheck disable=SC2094 # a terminal, not a file
	case "$1" in
		tmux) TERM=${MUX_TERM:-${TERM:-}} tmux attach-session -t "=$TMUX_SESSION" ;;
		screen) TERM=${MUX_TERM:-${TERM:-}} screen -d -r "$TMUX_SESSION" ;;
	esac 0<> "$MUX_TTY" 1>&0 2>&0 || rc=$?
	if [ -n "$saved" ]; then stty "$saved" < "$MUX_RAW_TTY" 2> /dev/null || true; fi
	return "$rc"
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
# Running scripts given as strings. Keep in sync with tools/migrate-to-2604.sh.

# Print a bash script (given as a string) that runs as a function in / with
# stdin from /dev/null. Further arguments are NAME=VALUE pairs that are set as
# variables for the script.
script_with_vars() {
	local body=$1 kv
	shift
	for kv in "$@"; do printf '%s=%q\n' "${kv%%=*}" "${kv#*=}"; done
	printf '__migrate() {\n%s\n}\ncd / && __migrate < /dev/null\n' "$body"
}

local_bash() {
	script_with_vars "$@" | bash -s
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
# grep, an editor). Keep in sync with tools/migrate-to-2604.sh.
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

# Facts about this box. Cheap, runs on every start. Keep in sync with
# FACTS_SCRIPT in tools/migrate-to-2604.sh; differs: OS_CODENAME, PROMPT,
# MIAB_IS_FORK, the backup target also from a paused custom.yaml, no unit list.
FACTS_SCRIPT="backup_pids() {
$BACKUP_PIDS_SCRIPT
}
$(cat <<'EOF'
. /etc/os-release 2> /dev/null || true
echo "OS_ID=${ID:-unknown}"
echo "OS_VERSION=${VERSION_ID:-unknown}"
echo "OS_CODENAME=${VERSION_CODENAME:-}"
echo "MACHINE_ID=$(cat /etc/machine-id 2> /dev/null)"
echo "NTP_SYNC=$(timedatectl show -p NTPSynchronized --value 2> /dev/null)"
echo "TIMEZONE=$(timedatectl show -p Timezone --value 2> /dev/null)"
echo "PHP_VERSIONS=$(ls /etc/php 2> /dev/null | tr '\n' ' ')"
echo "PROMPT=$(sed -n 's/^[[:space:]]*Prompt[[:space:]]*=[[:space:]]*//p' /etc/update-manager/release-upgrades 2> /dev/null | tail -n 1)"
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
if [ -f "$d/tools/migrate-to-2604.sh" ]; then echo "MIAB_IS_FORK=1"; fi

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

# Backup target (credentials in URLs masked). While the backups are paused
# by this tool, the real settings are in custom.yaml.upgrade-saved.
bf=$SR/backup/custom.yaml
if [ -f "$bf.upgrade-saved" ]; then bf=$bf.upgrade-saved; fi
if [ -e "$bf.upgrade-none" ]; then bf=/nonexistent; fi
echo "BACKUP_TARGET=$(sed -n 's/^target:[[:space:]]*//p' "$bf" 2> /dev/null | head -n 1 | tr -d "\"'" | sed 's#//[^/@]*@#//***@#')"

# Messages waiting in the Postfix queue live in /var/spool/postfix, not in $STORAGE_ROOT.
echo "POSTQUEUE=$(find /var/spool/postfix/deferred /var/spool/postfix/active /var/spool/postfix/incoming /var/spool/postfix/hold /var/spool/postfix/maildrop -type f 2> /dev/null | wc -l)"
if [ -n "$(backup_pids)" ]; then echo "BACKUP_RUNNING=1"; else echo "BACKUP_RUNNING=0"; fi
if systemctl is-active --quiet apt-daily.service 2> /dev/null || systemctl is-active --quiet apt-daily-upgrade.service 2> /dev/null \
	|| pgrep -f 'bin/unattended-upgrade( |$)' > /dev/null; then
	echo "APT_BUSY=1"
fi
if [ -f /root/.ssh/id_rsa_miab ]; then echo "HAS_BACKUP_SSH_KEY=1"; fi
if [ -d /var/lib/z-push ]; then echo "HAS_ZPUSH=1"; fi
if [ -d /var/lib/munin ]; then echo "HAS_MUNIN=1"; fi
EOF
)"

# Size and number of files of $STORAGE_ROOT. Slow on big boxes. Keep in sync
# with tools/migrate-to-2604.sh.
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
# itself, how many for other servers. Keep in sync with tools/migrate-to-2604.sh.
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
# Keep in sync with tools/migrate-to-2604.sh.
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

# Counts and key fingerprints of a $STORAGE_ROOT. Runs before the upgrade
# (snapshot, again after quiesce) and at the end, and the results are
# compared. Keep in sync with tools/migrate-to-2604.sh.
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
# deleted_at columns exist since Nextcloud 22; the box runs 26 or later).
echo "NC_EVENTS=$(q "$nc" "SELECT count(*) FROM ${p}calendarobjects o JOIN ${p}calendars c ON o.calendarid = c.id AND o.calendartype = 0 WHERE c.uri <> 'contact_birthdays' AND o.deleted_at IS NULL AND c.deleted_at IS NULL;")"
EOF
)

# Installed packages that no repository offers (OBSOLETE) or that come only
# from origins other than Ubuntu (FOREIGN), with python3-apt.
OBSOLETE_PY=$(cat <<'EOF'
import re, sys
import apt_pkg
apt_pkg.init()
cache = apt_pkg.Cache(None)
fork = re.compile(sys.argv[1])
for p in cache.packages:
	v = p.current_ver
	if not v:
		continue
	files = [pf for pf, _ in v.file_list]
	repo = [pf for pf in files if pf.archive != "now"]
	name = p.get_fullname(True)
	if not repo:
		print("OBSOLETE %s %s" % (name, v.ver_str))
		continue
	origins = sorted(set(pf.origin or pf.site or "?" for pf in repo))
	if any(o.startswith("Ubuntu") or o.startswith("Canonical") for o in origins):
		continue
	if all(fork.match(o) for o in origins):
		continue
	print("FOREIGN %s %s %s" % (name, v.ver_str, ",".join(origins)))
EOF
)

# ---------------------------------------------------------------------------
# Small helpers.

os_version() { (. /etc/os-release 2> /dev/null && echo "${VERSION_ID:-unknown}"); }
boot_id() { cat /proc/sys/kernel/random/boot_id 2> /dev/null || echo unknown; }

nearest_dir() {
	local d=$1
	while [ ! -d "$d" ]; do d=$(dirname "$d"); done
	echo "$d"
}

mount_of() { df -P "$(nearest_dir "$1")" | awk 'NR == 2 {print $6}'; }
avail_of() { df -B1 --output=avail "$(nearest_dir "$1")" | tail -n 1 | tr -d ' '; }
size_of() { if [ -e "$1" ]; then du -s -B1 "$1" 2> /dev/null | cut -f1; else echo 0; fi; }

pkg_installed() { dpkg-query -W -f='${db:Status-Abbrev}' "$1" 2> /dev/null | grep -q '^.i'; }

# apt-get without questions; keep the configuration files that are there.
# Wait up to 10 minutes for the dpkg lock (unattended-upgrades, apt-daily).
apt_get() {
	DEBIAN_FRONTEND=noninteractive apt-get -q -y -o DPkg::Lock::Timeout=600 -o Dpkg::Options::=--force-confdef \
		-o Dpkg::Options::=--force-confold "$@" < /dev/null
}

# Wait (at most 10 minutes) until nobody holds the dpkg or apt lists locks.
# DPkg::Lock::Timeout does not cover the lists lock of "apt-get update", and
# do-release-upgrade does not wait at all.
# Are the dpkg and apt locks free? (A test lock, released at once; no file is
# created, so --check changes nothing. Not pgrep: unattended-upgrade-shutdown
# --wait-for-signal runs on every Ubuntu server and holds no lock.)
apt_locks_free() {
	python3 -I - <<'PY' 2> /dev/null
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
}

wait_apt_locks() {
	local i
	for i in $(seq 60); do
		if apt_locks_free; then return 0; fi
		if [ "$i" = 1 ]; then say "Waiting for apt/dpkg (another package run holds its lock)..."; fi
		sleep 10
	done
	die "apt/dpkg stays locked for 10 minutes ($(pgrep -a -x 'apt|apt-get|aptitude|dpkg' | tr '\n' ' ')). Run the command again when it is free."
}

apt_update() {
	wait_apt_locks
	apt-get -q -o DPkg::Lock::Timeout=600 update < /dev/null
}

install_packages() {
	say "Installing $*..."
	apt_update > /dev/null || die "apt-get update failed."
	apt_get -q install "$@" || die "Could not install $*."
}

# For run_in_multiplexer. Not while a release upgrade is half-way (packages
# and sources between two releases), and only if nothing is upgraded or
# removed for it. A failure only means: no tmux. Quickly or not at all, and
# not with wait_apt_locks (its die would only end this function).
install_tmux() {
	if [ "$(state_get RELEASE_STARTED)" = 1 ] && ! phase_is_done release_2604; then return 1; fi
	apt_locks_free || { sleep 15 && apt_locks_free; } || return 1
	(
		apt-get -q -q -o DPkg::Lock::Timeout=30 update < /dev/null > /dev/null 2>&1 || exit 1
		if apt-get -s install tmux < /dev/null 2> /dev/null | grep -qE '^(Remv |Inst [^ ]+ \[)'; then exit 1; fi
		DEBIAN_FRONTEND=noninteractive apt-get -q -y -o DPkg::Lock::Timeout=30 -o Dpkg::Options::=--force-confdef \
			-o Dpkg::Options::=--force-confold install tmux < /dev/null > /dev/null 2>&1
	)
}

# The packages "apt-get -s purge" would remove, one per line.
purge_simulation() {
	apt-get -s purge "$@" < /dev/null 2> /dev/null | sed -n 's/^Purg \([^ ]*\).*/\1/p'
}

# Purge PACKAGES, but stop if that would take other packages with it than
# those whose names match ALLOWED_RE.
purge_only() { # ALLOWED_RE PACKAGES...
	local re=$1 extra
	shift
	[ $# -gt 0 ] || return 0
	extra=$(purge_simulation "$@" | grep -Evx "$re" || true)
	if [ -n "$extra" ]; then
		die "Removing $* would also remove these packages, which this tool leaves alone:
$(sed 's/^/  /' <<< "$extra")
Remove them yourself first (or keep them by other means), then run the command again."
	fi
	apt_get purge "$@" || die "Could not remove $*."
}

# Move PATH out of the way, to the same path below $MOVED_DIR (with .1, .2, ...
# if something was moved there before).
move_aside() {
	local p=$1 d n=1
	[ -e "$p" ] || [ -L "$p" ] || return 0
	d=$MOVED_DIR$p
	if [ -e "$d" ] || [ -L "$d" ]; then
		while [ -e "$d.$n" ] || [ -L "$d.$n" ]; do n=$((n + 1)); done
		d=$d.$n
	fi
	mkdir -p "$(dirname "$d")"
	mv "$p" "$d"
	say "  moved $p -> $d"
}

is_fork_dir() { [ -f "$1/setup/start.sh" ] && [ -f "$1/tools/migrate-to-2604.sh" ]; }

# The backup target as Mail-in-a-Box reads it (unmasked; never printed).
backup_target() {
	local b=$STORAGE_ROOT/backup/custom.yaml t
	# Paused by this tool: the real settings are kept aside (or there were none).
	if [ -e "$b.upgrade-none" ]; then
		echo local
		return 0
	fi
	if [ -f "$b.upgrade-saved" ]; then b=$b.upgrade-saved; fi
	t=$(sed -n 's/^target:[[:space:]]*//p' "$b" 2> /dev/null | head -n 1 | tr -d "\"'" || true)
	echo "${t:-local}"
}

# When the last Mail-in-a-Box backup finished (epoch), if any. duplicity keeps
# a copy of each manifest in its archive directory (backup/cache), whatever
# the target; local targets have them in encrypted/.
last_backup_epoch() {
	find "$STORAGE_ROOT/backup/cache" "$STORAGE_ROOT/backup/encrypted" -name 'duplicity-*.manifest*' \
		-printf '%T@\n' 2> /dev/null | sort -n | tail -n 1 | cut -d. -f1 || true
}

backup_pids() { local_bash "$BACKUP_PIDS_SCRIPT"; }

# A Mail-in-a-Box backup that is running (the nightly one starts at 01:04,
# /etc/cron.d/mailinabox-nightly): wait until it has finished, at most
# BACKUP_WAIT seconds. Only before anything is stopped, so Ctrl-C is safe.
# Sets BACKUP_WAITED. Keep in sync with tools/migrate-to-2604.sh (there on
# the old box, LABEL " on the old box").
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

# ---------------------------------------------------------------------------
# This fork's checkout. Keep in sync with tools/migrate-to-2604.sh.

# Setup links /usr/local/bin/mailinabox and the nightly cron job to the setup
# directory and runs it as root, so it must belong to root.
check_checkout_owner() {
	local d=$1 o
	o=$(stat -c %U "$d")
	[ "$o" != root ] || return 0
	warn "The setup scripts in $d belong to the user $o. Setup points
/usr/local/bin/mailinabox and the nightly cron job to this directory and runs them
as root, so $o could change what runs as root, and deleting $d later breaks the box.
Better: sudo git clone $DEFAULT_SOURCE $CLONE_DIR-fork
and run sudo $CLONE_DIR-fork/tools/$SCRIPT_NAME ..."
	if [ -z "$CHECK_ONLY" ]; then confirm "Continue with $d anyway?"; fi
}

checkout_dir() { # the checkout this script runs from, if any
	local d
	[ -n "$SELF_FILE" ] || return 1
	d=$(dirname "$(dirname "$SELF_FILE")")
	[ -f "$d/setup/start.sh" ] || return 1
	echo "$d"
}

# A release tag older than run_in_multiplexer does not start tmux by itself:
# say so before its copy runs (its own check only asks without --yes). Keep
# in sync with tools/migrate-to-2604.sh.
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

# Through curl | bash there is no file to continue from after a reboot:
# clone this fork into DIR and run SCRIPT from there instead. (resolve_miab_dir
# in tools/migrate-to-2604.sh, with the script name and the directory as
# parameters, and the branch main as the fallback when the tag lacks SCRIPT.)
reexec_from_clone() { # SCRIPT DIR ARGS...
	local script=$1 d=$2 source=${SOURCE:-$DEFAULT_SOURCE} tag=${TAG:-$DEFAULT_TAG}
	shift 2
	[ -z "${UPGRADE_REEXEC:-}" ] || die "Could not find tools/$script in $d."
	local how="curl -so $script $DEFAULT_RAW/tools/$script && sudo bash $script"
	command -v git > /dev/null || install_packages git
	if [ -d "$d/.git" ]; then
		# From an earlier run, possibly of an older release from another
		# repository: bring it to the tag from SOURCE, never run it as it is.
		say "Updating $d to $tag from $source..."
		if ! git -C "$d" remote set-url origin "$source" < /dev/null || ! checkout_ref "$d" "$tag" --force; then
			warn "Could not update $d to $tag; downloading it again."
			rm -rf "$d"
		fi
	fi
	if [ ! -d "$d/.git" ]; then
		rm -rf "$d"
		say "Downloading Mail-in-a-Box $tag from $source..."
		git clone -q -b "$tag" --depth 1 "$source" "$d" < /dev/null || rm -rf "$d"
	fi
	if [ ! -f "$d/tools/$script" ] && [ -z "${TAG:-}" ]; then
		# The release tag may not contain this tool yet.
		if [ -d "$d/.git" ]; then
			git -C "$d" fetch -q --depth 1 --force origin main < /dev/null && git -C "$d" checkout -q --force FETCH_HEAD || true
		else
			git clone -q -b main --depth 1 "$source" "$d" < /dev/null || rm -rf "$d"
		fi
	fi
	[ -f "$d/tools/$script" ] || die "Could not download tools/$script from $source ($tag).
Download the script to a file and run it from there:
  $how"
	warn_no_auto_tmux "$d/tools/$script" "$tag"
	UPGRADE_REEXEC=1 exec bash "$d/tools/$script" "$@"
}

# The script itself is kept in the state directory: the resume unit runs that
# copy after a reboot (the original may be in /tmp or in a checkout that
# setup moves).
install_self() {
	[ -n "$SELF_FILE" ] || return 0
	if [ "$SELF_FILE" != "$STATE_DIR/$SCRIPT_NAME" ]; then
		install -m 700 "$SELF_FILE" "$STATE_DIR/.$SCRIPT_NAME.new"
		mv "$STATE_DIR/.$SCRIPT_NAME.new" "$STATE_DIR/$SCRIPT_NAME"
	fi
	local d
	if d=$(checkout_dir) && is_fork_dir "$d" && [[ $d != "$STATE_DIR"/* ]]; then
		state_set SCRIPT_CHECKOUT "$d"
	fi
}

# The PID of another run of this script that is active, if any.
active_run_pid() {
	local pid
	pid=$(cat "$STATE_DIR/pid" 2> /dev/null || true)
	if [ -n "$pid" ] && [ "$pid" != "$$" ] && kill -0 "$pid" 2> /dev/null \
		&& grep -qa "$SCRIPT_NAME" "/proc/$pid/cmdline" 2> /dev/null; then
		echo "$pid"
	fi
	return 0
}

# Only one run at a time (the resume unit and an operator could both start one).
take_lock() {
	local pid
	pid=$(active_run_pid)
	if [ -n "$pid" ]; then
		IN_DIE=1
		die "Another run of $SCRIPT_NAME is active (PID $pid). Follow it with:
  tmux attach -t $TMUX_SESSION     (sudo tmux ... if you are not root)
  tail -f $LOG_FILE"
	fi
	echo $$ > "$STATE_DIR/pid"
	LOCKED=1
}

# The Dovecot configuration files that the fork's setup scripts name.
fork_dovecot_names() {
	local d
	for d in "$(state_get SCRIPT_CHECKOUT)" "$(checkout_dir || true)" "$STATE_DIR/fork" "$(state_get FORK_DIR)"; do
		[ -n "$d" ] && [ -d "$d/setup" ] || continue
		grep -rhoE '/etc/dovecot/conf\.d/[A-Za-z0-9_.-]+' "$d"/setup/*.sh 2> /dev/null | sed 's#.*/##' | sort -u | tr '\n' ' '
		return 0
	done
	return 0
}

# ---------------------------------------------------------------------------
# Preflight.

read_facts() {
	local out
	out=$(local_bash "$FACTS_SCRIPT") || die "Could not read the facts of this machine."
	F=()
	load_kv F <<< "$out"
}

check_space() {
	local -A need_bytes=() need_why=()
	local m nc_dir nc_db sr=$STORAGE_ROOT p total=0
	add_need() { # PATH BYTES WHY
		local mp
		mp=$(mount_of "$1")
		need_bytes[$mp]=$((${need_bytes[$mp]:-0} + $2))
		need_why[$mp]="${need_why[$mp]:+${need_why[$mp]}, }$3"
	}
	# do-release-upgrade wants up to 5 GB for the downloads (/var/cache/apt)
	# and the new packages (/usr), once per release.
	if [ "$(mount_of /var)" = "$(mount_of /)" ]; then
		add_need / $((5 * GIB)) "release upgrade 5 GiB"
	else
		add_need / $((3 * GIB)) "release upgrade 3 GiB"
		add_need /var $((3 * GIB)) "release upgrade downloads 3 GiB"
	fi
	# The system archive (compressed; the uncompressed size is the upper bound).
	for p in /etc "${F[MIAB_DIR]:-/root/mailinabox}" /var/lib/z-push /var/lib/munin /usr/local/lib/owncloud /var/spool/cron /usr/local/bin; do
		total=$((total + $(size_of "$p")))
	done
	add_need "$STATE_DIR" "$total" "system archive $(human "$total")"
	# Its encrypted copy, the unpacked copy of /etc, the saved .deb files.
	add_need "$STATE_DIR" "$total" "encrypted archive $(human "$total")"
	p=$(size_of /etc)
	add_need "$STATE_DIR" "$p" "copy of /etc $(human "$p")"
	local saved=()
	mapfile -t saved < <( (purge_set; downgrade_set) | sed 's/:.*//')
	if [ ${#saved[@]} -gt 0 ]; then
		p=$(($(dpkg-query -W -f='${Installed-Size}\n' "${saved[@]}" 2> /dev/null | awk '{s += $1} END {print s + 0}') * 1024))
		add_need "$STATE_DIR" "$p" "saved packages $(human "$p")"
	fi
	# Setup keeps a copy of the Nextcloud code and database in owncloud-backup/
	# for each step of the upgrade chain: twice that as the margin.
	nc_dir=$(size_of /usr/local/lib/owncloud)
	nc_db=${F[NC_DB_BYTES]:-0}
	add_need "$sr" $((2 * (nc_dir + nc_db))) "Nextcloud upgrade copies $(human $((2 * (nc_dir + nc_db))))"

	for m in "${!need_bytes[@]}"; do
		local a
		a=$(avail_of "$m")
		say "$(printf 'Free on %-12s ' "$m:")$(human "$a") (needed: $(human "${need_bytes[$m]}"): ${need_why[$m]})"
		if [ "$a" -lt "${need_bytes[$m]}" ]; then
			blocker "Not enough disk space on $m: $(human "$a") free, $(human "${need_bytes[$m]}") needed (${need_why[$m]})."
		fi
	done
	if [ "$(mount_of /boot)" != "$(mount_of /)" ] && [ "$(avail_of /boot)" -lt $((300 * 1024 * 1024)) ]; then
		warn "Only $(human "$(avail_of /boot)") free on /boot. Each release upgrade installs a new kernel;
remove old kernels first (apt autoremove --purge)."
	fi
}

# The package manager must be idle and consistent.
check_apt_state() {
	if ! apt_locks_free || [ "${F[APT_BUSY]:-0}" = 1 ]; then
		blocker "The package manager is busy (apt, dpkg or unattended-upgrades). Wait until it is finished."
	fi
	local audit
	audit=$(dpkg --audit 2> /dev/null || true)
	if [ -n "$audit" ]; then
		blocker "dpkg reports half-installed packages (dpkg --audit). Fix them first (dpkg --configure -a):
$(head -n 10 <<< "$audit" | sed 's/^/  /')"
	fi
	if ! apt-get -q -q check < /dev/null > /dev/null 2>&1; then
		blocker "apt reports broken dependencies ('apt-get check'). Fix them first ('apt-get -f install')."
	fi
}

# The next LTS (as do-release-upgrade sees it, from changelogs.ubuntu.com)
# must be offered: the upgrade from an LTS to the next one opens with its
# first point release (e.g. 26.04.1).
check_release_offer() {
	local cur=${F[OS_CODENAME]} meta wanted=() w ok
	case "${F[OS_VERSION]}" in
		22.04) wanted=(noble resolute) ;;
		24.04) wanted=(resolute) ;;
		*) return 0 ;;
	esac
	if ! command -v do-release-upgrade > /dev/null; then
		say "do-release-upgrade:  not installed (the upgrade installs update-manager-core)"
	fi
	case "${F[PROMPT]:-}" in
		lts) ;;
		never) say "Release upgrades:    Prompt=never (set by Mail-in-a-Box); the upgrade sets Prompt=lts." ;;
		*) say "Release upgrades:    Prompt=${F[PROMPT]:-unset}; the upgrade sets Prompt=lts." ;;
	esac
	meta=$(curl -fsS --max-time 20 https://changelogs.ubuntu.com/meta-release-lts 2> /dev/null || true)
	if [ -z "$meta" ]; then
		blocker "Could not fetch https://changelogs.ubuntu.com/meta-release-lts (no internet access?).
do-release-upgrade needs it."
		return 0
	fi
	for w in "${wanted[@]}"; do
		ok=$(awk -v d="$w" '/^Dist: / {cur = $2} /^Supported: / && cur == d {print $2}' <<< "$meta" | tail -n 1)
		if [ "$ok" = 1 ]; then
			say "Release upgrade:     $cur -> $w offered"
		else
			blocker "Ubuntu does not offer the release upgrade to $w yet (meta-release-lts). The upgrade
from one LTS to the next opens with the first point release of the new one."
		fi
		cur=$w
	done
}

# A recent backup must exist (by default): the release upgrades cannot be undone.
# A backup problem only blocks the start: once mail is offline (an
# interrupted quiesce), it no longer stops the run.
backup_blocker() {
	if [ -n "$NO_BACKUP_CHECK" ]; then
		warn "$* Continuing (--no-backup-check)."
	elif [ "$(state_get QUIESCED)" = 1 ]; then
		warn "$* Continuing: mail is offline already."
	else
		blocker "$* Or use --no-backup-check."
	fi
}

check_backup() {
	local target last age running=
	target=$(backup_target)
	# Set below when the age check waits for the running backup: stop_mail
	# checks then even if that backup has finished by itself meanwhile.
	state_set BACKUP_CHECK_DEFERRED ""
	say "Backups:             ${F[BACKUP_TARGET]:-local}"
	if [ "$target" = off ]; then
		backup_blocker "Backups are turned off (System > Backup Status). A release upgrade cannot be undone:
make a backup first."
		return 0
	fi
	# Not a blocker: the upgrade waits for it (wait_backup_done) and then
	# checks the age again (backup_check_after_wait).
	if [ "${F[BACKUP_RUNNING]:-0}" = 1 ]; then
		running=1
		say "Backup running:      yes; the upgrade waits until it has finished (at most $(fmt_dur "$BACKUP_WAIT"))"
		say "                     before it stops anything"
	fi
	last=$(last_backup_epoch)
	if [ -z "$last" ] && [ -n "$running" ]; then
		say "Last backup:         none yet; checked again when the running one has finished"
		state_set BACKUP_CHECK_DEFERRED 1
	elif [ -z "$last" ]; then
		backup_blocker "No Mail-in-a-Box backup found in $STORAGE_ROOT/backup. Make one first
(System > Backup Status, or $(state_get OLD_MIAB_DIR)/management/backup.py)."
		return 0
	else
		age=$(($(date +%s) - last))
		say "Last backup:         $(date -d "@$last" '+%F %H:%M') ($(fmt_dur "$age") ago)"
		if [ "$age" -gt "$BACKUP_MAX_AGE" ] && [ -n "$running" ]; then
			say "                     older than $(fmt_dur "$BACKUP_MAX_AGE"); checked again when the running one has finished"
			state_set BACKUP_CHECK_DEFERRED 1
		elif [ "$age" -gt "$BACKUP_MAX_AGE" ]; then
			backup_blocker "The last backup is $(fmt_dur "$age") old (more than $(fmt_dur "$BACKUP_MAX_AGE")). Check System > Backup Status."
		fi
	fi
	case "$target" in
		local | file://"$STORAGE_ROOT"/*)
			warn "The backups are on this machine ($STORAGE_ROOT/backup/encrypted). If the upgrade breaks the
disk or the machine, they are gone as well. Copy them elsewhere first (or set an offsite target)."
			;;
	esac
	if [ -z "$SKIP_MIAB_BACKUP" ]; then
		say "                     a fresh backup runs in the snapshot phase (--skip-miab-backup)"
	fi
	say "Keep a copy of $STORAGE_ROOT/backup/secret_key.txt OFF this machine: backups"
	say "(and the encrypted system archive) cannot be restored without it."
}

# The PHP packages from ppa:ondrej / deb.sury.org (their versions contain
# "deb.sury.org") and dovecot-antispam are purged before the release upgrade;
# other packages from there are moved back to Ubuntu's versions.
sury_packages() {
	dpkg-query -W -f='${db:Status-Abbrev} ${binary:Package} ${Version}\n' 2> /dev/null \
		| awk '$1 ~ /^.i/ && ($3 ~ /deb\.sury\.org/ || $3 ~ /\+0~[0-9]+\.[0-9]+\+ubuntu[0-9.]+~[0-9]+\.gbp[0-9a-f]+$/) {print $2}' || true
}
PHP_NAME_RE='(php|libapache2-mod-php|libphp)[0-9a-z.+-]*(:[a-z0-9]+)?'

# Build tools that only exist for PHP (php8.0-dev from ppa:ondrej pulls in
# pkg-php-tools): removed with it.
PHP_TOOLING_RE='(pkg-php-tools|dh-php|dh-sequence-php|php-pear|composer|jsonlint)(:[a-z0-9]+)?'

# The PHP packages of ppa:ondrej, dovecot-antispam, and the PHP packages and
# tooling that apt would remove with them (named, so that their .deb files are
# saved for --rollback).
purge_set() {
	local base=()
	mapfile -t base < <(
		sury_packages | grep -Ex "$PHP_NAME_RE" || true
		if pkg_installed dovecot-antispam; then echo dovecot-antispam; fi
	)
	[ ${#base[@]} -gt 0 ] || return 0
	{
		printf '%s\n' "${base[@]}"
		purge_simulation "${base[@]}" | grep -Ex "$PHP_NAME_RE|$PHP_TOOLING_RE" || true
	} | awk '!seen[$0]++'
}
downgrade_set() { sury_packages | grep -Evx "$PHP_NAME_RE" || true; }

check_purge() {
	local purge=() extra
	mapfile -t purge < <(purge_set)
	[ ${#purge[@]} -gt 0 ] || return 0
	say "Removed before the release upgrade (from ppa:ondrej or obsolete): ${purge[*]}"
	local tooling
	tooling=$(printf '%s\n' "${purge[@]}" | grep -Ex "$PHP_TOOLING_RE" | tr '\n' ' ' || true)
	if [ -n "$tooling" ]; then
		warn "Also removed (PHP tooling that needs the PHP of ppa:ondrej): $tooling"
	fi
	extra=$(purge_simulation "${purge[@]}" | grep -Evx "$PHP_NAME_RE|$PHP_TOOLING_RE|dovecot-antispam" || true)
	if [ -n "$extra" ]; then
		blocker "Removing the PHP packages of ppa:ondrej would also remove:
$(sed 's/^/  /' <<< "$extra")
Remove or replace them first."
	fi
	local down=()
	mapfile -t down < <(downgrade_set)
	if [ ${#down[@]} -gt 0 ]; then
		say "Moved back to Ubuntu's versions before the release upgrade: ${down[*]}"
	fi
}

# Is this apt URI the Ubuntu archive (or a mirror of it, or ESM)?
is_ubuntu_uri() {
	local u=${1#*://} host path
	host=${u%%/*}
	host=${host##*@}
	host=${host%%:*}
	if [[ $u == */* ]]; then path=/${u#*/}; else path=/; fi
	case "$host" in
		ppa.launchpad.net | ppa.launchpadcontent.net | private-ppa.launchpadcontent.net) return 1 ;;
		ubuntu.com | *.ubuntu.com | *.canonical.com) return 0 ;;
	esac
	# Mirrors (e.g. http://mirror.example.net/ubuntu/packages): the Release file
	# that apt downloaded from there names its origin. apt names it after the
	# URI without the scheme, "/" replaced by "_".
	local mangled rel
	mangled=${u%/}
	mangled=${mangled##*@}
	mangled=${mangled//\//_}
	for rel in /var/lib/apt/lists/"$mangled"_dists_*Release; do
		[ -f "$rel" ] || continue
		grep -q '^Origin: Ubuntu' "$rel"
		return
	done
	# Never downloaded: only a mirror with the archive at its top level.
	[[ ${path%/} =~ ^/ubuntu(-ports)?(/[a-z-]+)?$ ]]
}

# The active URIs of a .list or .sources file.
source_uris() {
	if [[ $1 == *.sources ]]; then
		grep -iE '^URIs:' "$1" 2> /dev/null | sed 's/^[^:]*:[[:space:]]*//' | tr ' \t' '\n\n' | sed '/^$/d' || true
	else
		sed -e 's/#.*//' "$1" 2> /dev/null | awk '$1 ~ /^deb(-src)?$/ {
			i = 2
			if ($2 ~ /^\[/) { while (i <= NF && $i !~ /\]$/) i++; i++ }
			if (i <= NF) print $i
		}' || true
	fi
}

# Does this file in sources.list.d only point to the Ubuntu archive?
is_ubuntu_source() {
	local f=$1 uris u
	case "$f" in *.list | *.sources) ;; *) return 1 ;; esac
	uris=$(source_uris "$f")
	if [ -z "$uris" ]; then
		# Nothing active. Keep Ubuntu's own files (ubuntu.sources, ubuntu-esm-*.list without Pro).
		[[ $(basename "$f") == ubuntu* ]]
		return
	fi
	while read -r u; do
		is_ubuntu_uri "$u" || return 1
	done <<< "$uris"
	return 0
}

third_party_sources() {
	local f
	for f in /etc/apt/sources.list.d/*; do
		[ -f "$f" ] || continue
		is_ubuntu_source "$f" || echo "$f"
	done
}

# Lines in /etc/apt/sources.list that are not the Ubuntu archive.
third_party_lines() {
	local line u
	[ -f /etc/apt/sources.list ] || return 0
	while IFS= read -r line; do
		u=$(printf '%s\n' "$line" | awk '$1 ~ /^deb(-src)?$/ {
			i = 2
			if ($2 ~ /^\[/) { while (i <= NF && $i !~ /\]$/) i++; i++ }
			if (i <= NF) print $i
		}')
		[ -n "$u" ] || continue
		is_ubuntu_uri "$u" || printf '%s\n' "$line"
	done < /etc/apt/sources.list
}

# Files of the Dovecot packages and the checksums of their configuration files.
declare -A DPKG_OWNED=() DPKG_MD5=()
load_dovecot_files() {
	local pkgs=() f sum
	mapfile -t pkgs < <(dpkg-query -W -f='${db:Status-Abbrev} ${binary:Package}\n' 'dovecot-*' 2> /dev/null | awk '$1 ~ /^.i/ {print $2}' || true)
	[ ${#pkgs[@]} -gt 0 ] || return 0
	while IFS= read -r f; do DPKG_OWNED[$f]=1; done < <(dpkg -L "${pkgs[@]}" 2> /dev/null | grep '^/etc/dovecot/' || true)
	while read -r f sum _; do
		[ -n "$f" ] || continue
		DPKG_OWNED[$f]=1
		DPKG_MD5[$f]=$sum
	done < <(dpkg-query -W -f='${Conffiles}\n' "${pkgs[@]}" 2> /dev/null | grep '^ /etc/dovecot/' || true)
	# Ubuntu's Dovecot packages install dovecot.conf and most of conf.d with
	# ucf, not as dpkg conffiles; the ucf registry names them. They count as
	# the package's, unchanged: ucf's hash file holds the checksum of the newest
	# packaged version, which differs from a file an earlier release upgrade
	# kept, so it cannot tell changes by hand.
	while read -r _ f; do
		if [[ $f == /etc/dovecot/* ]]; then DPKG_OWNED[$f]=1; fi
	done < <(cat /var/lib/ucf/registry 2> /dev/null || true)
}

# What is on this box that Mail-in-a-Box does not manage. Fills EXT_BLOCK
# (blocks the upgrade without --keep-local), EXT_INFO (only reported) and
# EXT_FTS (replaced by the fork's FTS).
detect_extensions() {
	EXT_BLOCK=() EXT_INFO=() EXT_FTS=()
	local known f n base d c names
	known=" $(echo "$KNOWN_DOVECOT_CONFD" | tr '\n' ' ') $(fork_dovecot_names) "
	load_dovecot_files
	if [ -d /etc/dovecot ]; then
		while IFS= read -r -d '' f; do
			n=${f#/etc/dovecot/}
			base=${n##*/}
			case "$n" in
				*.dpkg-old | *.dpkg-dist | *.dpkg-new | *.dpkg-bak | *.ucf-* | *~ | *.svbin | private/*) continue ;;
			esac
			if [[ $n == conf.d/* ]] && [[ $known == *" $base "* ]]; then continue; fi
			if [[ $n != */* ]] && [[ " $KNOWN_DOVECOT_TOP " == *" $n "* ]]; then continue; fi
			if [[ " $FTS_FILES " == *" $base "* ]] || grep -qs 'fts_xapian' "$f"; then
				EXT_FTS+=("$f")
				continue
			fi
			if [[ $n == *.lua ]]; then
				EXT_BLOCK+=("$f (Lua script for Dovecot)")
				continue
			fi
			if [ -n "${DPKG_OWNED[$f]:-}" ]; then
				# A package's file: only a configuration file changed by hand counts.
				if [ -n "${DPKG_MD5[$f]:-}" ] && [ "$(md5sum < "$f" | cut -d' ' -f1)" != "${DPKG_MD5[$f]}" ]; then
					EXT_BLOCK+=("$f (a package's file, changed by hand)")
				fi
				continue
			fi
			EXT_BLOCK+=("$f (neither from Mail-in-a-Box nor from a package)")
		done < <(find /etc/dovecot \( -type f -o -type l \) -print0 2> /dev/null)
	fi

	for d in /etc/systemd/system/{dovecot,postfix,postfix@,nginx,spampd,postgrey,opendkim,opendmarc,nsd}.service.d \
		/etc/systemd/system/dovecot.socket.d /etc/systemd/system/php*-fpm.service.d; do
		[ -d "$d" ] || continue
		for f in "$d"/*; do
			# Written by setup/mail-postfix.sh and setup/spamassassin.sh of this fork.
			case "$f" in
				/etc/systemd/system/postfix.service.d/mailinabox-stale-db.conf) continue ;;
				/etc/systemd/system/spampd.service.d/mailinabox-pidfile.conf) continue ;;
			esac
			if [ -e "$f" ]; then EXT_BLOCK+=("$f (systemd drop-in)"); fi
		done
	done
	for f in /etc/nginx/conf.d/*; do
		[ -e "$f" ] || continue
		case "${f##*/}" in local.conf | ssl.conf) ;; *) EXT_BLOCK+=("$f (nginx configuration)") ;; esac
	done
	for f in /etc/nginx/sites-enabled/*; do
		if [ -e "$f" ]; then EXT_INFO+=("$f (nginx site; not used by Mail-in-a-Box, kept)"); fi
	done

	if command -v docker > /dev/null; then
		c=$(docker ps -q 2> /dev/null | wc -l || true)
		EXT_INFO+=("docker with ${c:-?} running containers (not stopped by this tool; the release upgrade restarts docker; stop them with a hook or by hand if they use mail)")
	fi
	if pkg_installed snapd; then
		names=$(snap list 2> /dev/null | awk 'NR > 1 {print $1}' | tr '\n' ' ' || true)
		EXT_INFO+=("snapd (kept)${names:+: $names}")
	fi
	while IFS= read -r f; do
		[ -n "$f" ] || continue
		EXT_INFO+=("apt source $f (disabled for the upgrade and NOT enabled again)")
	done < <(third_party_sources)
	while IFS= read -r f; do
		[ -n "$f" ] || continue
		EXT_INFO+=("apt source in /etc/apt/sources.list: $f (commented out for the upgrade)")
	done < <(third_party_lines)
	names=$(dpkg-query -W -f='${db:Status-Abbrev} ${binary:Package} ${Version}\n' 2> /dev/null \
		| awk '$1 ~ /^.i/ && ($2 ~ /^(webmin|usermin|docker-ce|docker-ce-cli|containerd\.io|mysql-server|mariadb-server)$/ || $3 ~ /~ppa|ppa[0-9]/) {print $2 " " $3}' \
		| tr '\n' ';' || true)
	if [ -n "$names" ]; then EXT_INFO+=("packages from other sources (kept; check them after the upgrade): ${names%;}"); fi
	for f in /etc/cron.d/*; do
		[ -f "$f" ] || continue
		case "${f##*/}" in mailinabox-* | .placeholder) continue ;; esac
		dpkg -S "$f" > /dev/null 2>&1 && continue
		EXT_INFO+=("$f (cron job; kept, cron is stopped during the upgrade)")
	done
	while IFS= read -r f; do
		if [ -n "$f" ]; then EXT_INFO+=("hook $f (runs right before mail goes offline)"); fi
	done < <(hook_files "$HOOK_BEFORE_DIR")
	while IFS= read -r f; do
		if [ -n "$f" ]; then EXT_INFO+=("hook $f (runs in phase local-ext)"); fi
	done < <(hook_files "$HOOK_DIR")
	while IFS= read -r f; do
		if [ -n "$f" ]; then EXT_INFO+=("hook $f (runs in phase finish, after mail is back)"); fi
	done < <(hook_files "$HOOK_AFTER_DIR")
}

report_extensions() {
	section "Not managed by Mail-in-a-Box"
	detect_extensions
	local x
	if [ ${#EXT_FTS[@]} -gt 0 ]; then
		say "Dovecot full-text search, replaced by the fork's FTS (fts_xapian, 95-mailinabox-fts.conf):"
		for x in "${EXT_FTS[@]}"; do say "  $x"; done
	fi
	if [ ${#EXT_BLOCK[@]} -gt 0 ]; then
		say "Local extensions that the upgrade would lose or break (Dovecot 2.4 does not read 2.3"
		say "configuration, /etc/dovecot is replaced by a pristine copy before setup):"
		for x in "${EXT_BLOCK[@]}"; do say "  $x"; done
		if [ "$(state_get MODE)" = rerun ]; then
			say "(Setup runs again on this Ubuntu 26.04 box; /etc/dovecot is not replaced, nothing blocks.)"
		elif [ -n "$KEEP_LOCAL" ]; then
			say "Continuing (--keep-local). The old files stay in $OLD_ETC (and $MOVED_DIR/etc/dovecot);"
			say "hooks in $HOOK_DIR/*.sh can bring them back (see the header of this script)."
		else
			blocker "Local extensions found (listed above). Use --keep-local to upgrade anyway; bring them back
afterwards with hooks in $HOOK_DIR/*.sh (see the header of this script)."
		fi
	fi
	if [ ${#EXT_INFO[@]} -gt 0 ]; then
		say "Also on this box (reported only):"
		for x in "${EXT_INFO[@]}"; do say "  $x"; done
	fi
	if [ ${#EXT_FTS[@]} -eq 0 ] && [ ${#EXT_BLOCK[@]} -eq 0 ] && [ ${#EXT_INFO[@]} -eq 0 ]; then
		say "Nothing found."
	fi
	if [ -z "$CHECK_ONLY" ]; then
		{
			for x in "${EXT_FTS[@]}"; do echo "FTS $x"; done
			for x in "${EXT_BLOCK[@]}"; do echo "LOCAL $x"; done
			for x in "${EXT_INFO[@]}"; do echo "INFO $x"; done
		} > "$STATE_DIR/local-extensions.txt"
	fi
}

phase_preflight() {
	section "Checking this machine"
	CHECK_BLOCKERS=()
	read_facts
	[ "${F[HAS_CONF]:-0}" = 1 ] || die "/etc/mailinabox.conf is missing. Is this a Mail-in-a-Box?"
	STORAGE_ROOT=${F[CONF_STORAGE_ROOT]:-}
	[[ $STORAGE_ROOT == /* && $STORAGE_ROOT != *" "* && $STORAGE_ROOT != / ]] \
		|| die "Unexpected STORAGE_ROOT '$STORAGE_ROOT' in /etc/mailinabox.conf."

	local mode=upgrade
	# Preflight only runs before quiesce, so the fork cannot be the result of this upgrade.
	if [ "${F[OS_VERSION]}" = 26.04 ] && [ "${F[MIAB_IS_FORK]:-0}" = 1 ]; then mode=rerun; fi
	state_set MODE "$mode"
	# The old checkout, recorded once: setup later points /usr/local/bin/mailinabox elsewhere.
	if [ -z "$(state_get OLD_MIAB_DIR)" ] || ! phase_is_done quiesce; then
		state_set OLD_MIAB_DIR "${F[MIAB_DIR]}"
		state_set OLD_MIAB_VERSION "${F[MIAB_VERSION]:-}"
		state_set OLD_OS_VERSION "${F[OS_VERSION]}"
	fi
	state_set STORAGE_ROOT "$STORAGE_ROOT"
	state_set NC_VERSION "${F[NC_VERSION]:-}"

	say "Ubuntu:              ${F[OS_VERSION]} (${F[OS_CODENAME]})"
	say "Mail-in-a-Box:       ${F[MIAB_VERSION]:-unknown} (${F[MIAB_DIR]})"
	say "Nextcloud:           ${F[NC_VERSION]:-not installed}"
	say "PHP:                 ${F[PHP_VERSIONS]:-none}"
	say "Hostname:            ${F[CONF_PRIMARY_HOSTNAME]:-}"
	say "Public IP:           ${F[CONF_PUBLIC_IP]:-} ${F[CONF_PUBLIC_IPV6]:-}"
	say "Storage:             $STORAGE_ROOT (user ${F[CONF_STORAGE_USER]:-})"

	case "${F[OS_ID]}/${F[OS_VERSION]}" in
		ubuntu/22.04) say "Path:                22.04 -> 24.04 -> 26.04 (two release upgrades, two reboots)" ;;
		ubuntu/24.04)
			say "Path:                24.04 -> 26.04 (one release upgrade, one reboot)"
			say "Note: upstream Mail-in-a-Box does not support Ubuntu 24.04; this looks like a box that"
			say "was release-upgraded in place before. That is what this tool expects."
			;;
		ubuntu/26.04)
			if [ "$mode" = rerun ]; then
				say "Path:                already Ubuntu 26.04 with this fork: setup runs again"
			else
				say "Path:                Ubuntu 26.04 already (release upgrades are skipped)"
			fi
			;;
		ubuntu/14.04 | ubuntu/16.04 | ubuntu/18.04 | ubuntu/20.04)
			blocker "This box runs Ubuntu ${F[OS_VERSION]}. First move it to Ubuntu 22.04 with upstream
Mail-in-a-Box v78 (https://mailinabox.email/maintenance.html#upgrade: a new machine,
restore the backup there), then run this or tools/migrate-to-2604.sh."
			;;
		*) blocker "This box runs ${F[OS_ID]} ${F[OS_VERSION]}, expected Ubuntu 22.04, 24.04 or 26.04." ;;
	esac

	local mv=${F[MIAB_VERSION]:-}
	if [ "${F[MIAB_IS_FORK]:-0}" = 1 ]; then
		:
	elif [[ $mv =~ ^v([0-9]+) ]]; then
		if [ "${BASH_REMATCH[1]}" -lt 60 ]; then
			blocker "Mail-in-a-Box $mv is too old. Update it to v78 first (on Ubuntu 22.04):
  curl -s https://mailinabox.email/setup.sh | sudo bash"
		fi
	else
		warn "Could not read the Mail-in-a-Box version in ${F[MIAB_DIR]}. Continuing; the Nextcloud check below still applies."
	fi

	local nc=${F[NC_VERSION]:-}
	if [ -n "$nc" ] && [ "${nc%%.*}" -lt 26 ] 2> /dev/null; then
		if [ "${F[OS_VERSION]}" = 22.04 ]; then
			blocker "This box runs Nextcloud $nc. This fork's upgrade chain starts at Nextcloud 26.
Update to upstream Mail-in-a-Box v78 first (Nextcloud 27):
  curl -s https://mailinabox.email/setup.sh | sudo bash
then run this command again."
		else
			blocker "This box runs Nextcloud $nc. This fork's upgrade chain starts at Nextcloud 26,
and upstream setup does not run on Ubuntu ${F[OS_VERSION]}. Upgrade Nextcloud to 26 by hand
(occ upgrade, one major version at a time) first."
		fi
	fi
	if [ "${F[NC_MAINTENANCE]:-0}" = 1 ]; then
		warn "Nextcloud is in maintenance mode. Setup turns it off after the upgrade, but check why it is on."
	fi
	if [ -n "${F[NC_EXTRA_APPS]:-}" ]; then
		warn "Nextcloud apps installed by hand are NOT kept (setup replaces /usr/local/lib/owncloud):
${F[NC_EXTRA_APPS]}
Their data stays in the database, and the code is in the system archive. Reinstall them
afterwards if they support Nextcloud 34 (setup keeps the app store off, see 'appstoreenabled')."
	fi

	if [ "$mode" = upgrade ]; then
		if [ -z "$(state_get FILES_OWNCLOUD)" ]; then
			local out
			out=$(local_bash "$SIZE_SCRIPT" "SR=$STORAGE_ROOT") || true
			local -A S=()
			load_kv S <<< "$out"
			state_set SIZE_TOTAL "${S[SIZE_TOTAL]:-0}"
			state_set FILES_TOTAL "${S[FILES_TOTAL]:-0}"
			state_set FILES_OWNCLOUD "${S[FILES_OWNCLOUD]:-0}"
		fi
		say "Data:                $(human "$(state_get SIZE_TOTAL)") in $(state_get FILES_TOTAL) files and directories (stays in place)"
		check_space
		check_apt_state
		check_release_offer
		check_backup
		check_purge
		local held
		held=$(apt-mark showhold 2> /dev/null | tr '\n' ' ' || true)
		if [ -n "$held" ]; then say "Held packages:       $held(released for the upgrade, not held again)"; fi
		if [ "$(timedatectl show -p NTPSynchronized --value 2> /dev/null || true)" != yes ]; then
			warn "The clock is not NTP-synchronized (timedatectl). TLS, TOTP and DNSSEC need the right time."
		fi
		if systemd-detect-virt -c -q 2> /dev/null; then
			warn "This runs in a container ($(systemd-detect-virt -c)). Release upgrades in containers depend on the host."
		fi
		local q
		q=$(local_bash "$QUEUE_SCRIPT" "SR=$STORAGE_ROOT" 2> /dev/null || true)
		local -A Q=()
		load_kv Q <<< "$q"
		if [ "${Q[QUEUE_TOTAL]:-0}" -gt 0 ] 2> /dev/null; then
			say "Postfix queue:       ${Q[QUEUE_TOTAL]} messages (stays in /var/spool/postfix and is sent after the upgrade)"
		fi
		report_extensions
		section "Console access"
		say "Make sure you can reach the provider's console (VNC, KVM, serial) for this machine"
		say "BEFORE you start: if the network does not come up after a reboot (changed interface"
		say "names, old ifupdown configuration, firewall), SSH is gone and the console is the only way in."
	else
		report_extensions
	fi
}

# The last block of --check.
check_summary() {
	section "Result of the check"
	session_check
	if [ ${#CHECK_BLOCKERS[@]} -eq 0 ]; then
		say "No blockers found. Nothing was changed."
		say "Start the upgrade with:"
		say "  $(start_command)"
		exit 0
	fi
	local b
	say "These must be fixed first:"
	for b in "${CHECK_BLOCKERS[@]}"; do say "  - $b"; done
	say "Nothing was changed."
	exit 1
}

blockers_or_die() {
	[ ${#CHECK_BLOCKERS[@]} -gt 0 ] || return 0
	local b msg="These must be fixed first:"
	for b in "${CHECK_BLOCKERS[@]}"; do msg+=$'\n'"  - $b"; done
	if [ "$(state_get QUIESCED)" = 1 ]; then
		die "$msg
Mail is OFFLINE since $(state_get QUIESCED_AT) (an earlier run stopped it). Fix these and run
the command again, or go back with: $SELF --rollback"
	fi
	die "$msg
Nothing was changed. '$(start_command | sed 's/$/ --check/')' lists them again."
}

start_command() {
	local c=$SELF
	if [ -z "$SELF_FILE" ]; then c="$DEFAULT_RAW/tools/$SCRIPT_NAME (saved to a file)"; else c=$SELF_FILE; fi
	echo "$c$(resume_flags | sed 's/^/ /' | tr '\n' ' ' | sed 's/ $//')"
}

show_plan() {
	section "Plan"
	if [ "$(state_get MODE)" = rerun ]; then
		say "This box already runs Ubuntu 26.04 with this fork (${F[MIAB_VERSION]:-}). Its checkout is"
		say "brought to ${TAG:-$DEFAULT_TAG} (unless this script runs from it and TAG= is not set), then"
		say "only setup runs again (like 'sudo mailinabox'), then the hooks in $HOOK_DIR and the checks."
		return 0
	fi
	local v=${F[OS_VERSION]} n=1 nc=${F[NC_VERSION]:-} steps=0 oc
	oc=$(state_get FILES_OWNCLOUD)
	oc=${oc:-0}
	if [[ $nc =~ ^([0-9]+) ]] && [ "${BASH_REMATCH[1]}" -lt 34 ]; then steps=$((34 - BASH_REMATCH[1])); fi
	local offsite="an encrypted copy of the archive next to the backups"
	if [ -n "$NO_OFFSITE" ]; then offsite="the archive stays here (--no-offsite)"; fi
	if fresh_backup_planned; then
		say "$n. Snapshot: system archive (/etc, the code outside $STORAGE_ROOT), $offsite."
		say "   Then MAIL GOES OFFLINE: mail, web, cron and the update timers stopped and masked"
		say "   (they stay off across reboots until setup), a fresh Mail-in-a-Box backup (so it"
		say "   holds all mail), fingerprint."
		n=$((n + 1))
		say "$n. Backups paused until the end."
	else
		say "$n. Snapshot: fingerprint, system archive (/etc, the code outside $STORAGE_ROOT),"
		say "   no fresh backup ($([ -n "$SKIP_MIAB_BACKUP" ] && echo "--skip-miab-backup" || echo "backups are off")),"
		say "   $offsite. Mail keeps running."
		n=$((n + 1))
		say "$n. MAIL GOES OFFLINE: backups paused; mail, web, cron and the update timers stopped"
		say "   and masked (they stay off across reboots until setup)."
	fi
	n=$((n + 1))
	say "$n. Third-party apt sources off, PHP from ppa:ondrej removed, packages updated."
	if [ "$v" = 22.04 ]; then
		n=$((n + 1))
		say "$n. do-release-upgrade to Ubuntu 24.04, reboot (continues on its own)."
	fi
	if [ "$v" != 26.04 ]; then
		n=$((n + 1))
		say "$n. do-release-upgrade to Ubuntu 26.04, reboot (continues on its own)."
	fi
	n=$((n + 1))
	say "$n. Clean up: pristine Dovecot 2.4 configuration, old PHP versions, the old Python"
	say "   environment, ntp. Everything removed is kept in $MOVED_DIR."
	n=$((n + 1))
	say "$n. Setup of this fork (${TAG:-$DEFAULT_TAG}) on the existing data (Nextcloud ${nc:-} -> 34). Mail is back."
	n=$((n + 1))
	say "$n. Hooks ($HOOK_DIR), checks, services and backups back on."
	if [ -n "$(hook_files "$HOOK_BEFORE_DIR")" ]; then
		say "The hooks in $HOOK_BEFORE_DIR run right before mail goes offline."
	fi
	if [ -n "$(hook_files "$HOOK_AFTER_DIR")" ]; then
		say "The hooks in $HOOK_AFTER_DIR run at the end, when mail and the backups are back"
		say "(or right after a final check that failed, as mail runs again then)."
	fi
	say
	local rel=0 bk_lo=0 bk_hi=0 bk=
	if [ "$v" = 22.04 ]; then rel=2; elif [ "$v" = 24.04 ]; then rel=1; fi
	# An incremental backup; a full one is not foreseeable (see below).
	if fresh_backup_planned; then bk_lo=120 bk_hi=900 bk=", the fresh backup"; fi
	local lo=$((rel * 1500 + 600 + 900 + steps * 120 + steps * oc / 50000 + bk_lo)) hi=$((rel * 4200 + 1200 + 1800 + steps * 600 + steps * oc / 10000 + bk_hi))
	say "Expected downtime, roughly: $(fmt_dur "$lo") - $(fmt_dur "$hi")"
	say "  ($rel release upgrade(s) of 20-60 minutes each, reboots, setup 15-30 minutes plus"
	say "  $steps Nextcloud upgrade steps over $oc files$bk)."
	if [ -n "$bk" ]; then
		say "The fresh backup runs with mail offline: a few minutes when it is incremental, much longer"
		say "when backup.py makes a full backup of the $(human "$(state_get SIZE_TOTAL)") (when there is none yet, or on a"
		say "Saturday or Sunday after many changes or about a month since the last full one)."
	fi
	say "The release upgrades cannot be undone; '--rollback' only works before the first one."
}

# ---------------------------------------------------------------------------
# Snapshot.

save_meta() {
	local m=$STATE_DIR/meta
	rm -rf "$m"
	mkdir -p "$m"
	dpkg --get-selections > "$m/dpkg-selections.txt" 2> /dev/null || true
	apt-mark showmanual > "$m/apt-mark-manual.txt" 2> /dev/null || true
	apt-mark showhold > "$m/apt-mark-hold.txt" 2> /dev/null || true
	dpkg -l > "$m/dpkg-l.txt" 2> /dev/null || true
	dpkg-query -W -f='${binary:Package} ${Version}\n' > "$m/packages.txt" 2> /dev/null || true
	doveconf -n > "$m/doveconf-n.txt" 2>&1 || true
	postconf -n > "$m/postconf-n.txt" 2> /dev/null || true
	systemctl list-unit-files --no-legend --no-pager > "$m/unit-files.txt" 2> /dev/null || true
	systemctl list-units --state=active --no-legend --no-pager > "$m/units-active.txt" 2> /dev/null || true
	lsb_release -a > "$m/lsb_release.txt" 2>&1 || true
	crontab -l -u root > "$m/root-crontab.txt" 2> /dev/null || true
	ls -la /etc/apt/sources.list.d /etc/apt/trusted.gpg.d > "$m/apt-files.txt" 2>&1 || true
	{
		echo "MIAB_DIR=$(state_get OLD_MIAB_DIR)"
		echo "MIAB_VERSION=$(state_get OLD_MIAB_VERSION)"
		echo "NC_VERSION=$(state_get NC_VERSION)"
		echo "SNAPSHOT_AT=$(date -u +%FT%TZ)"
	} > "$m/miab-version.txt"
}

# Does the snapshot run a fresh Mail-in-a-Box backup? (Without output.)
fresh_backup_planned() { [ -z "$SKIP_MIAB_BACKUP" ] && [ "$(backup_target)" != off ]; }

# The same, with the reason when not, and the checks that would only fail
# later (before mail is stopped for the backup).
miab_backup_wanted() {
	local dir
	dir=$(state_get OLD_MIAB_DIR)
	if [ -n "$SKIP_MIAB_BACKUP" ]; then
		say "No fresh Mail-in-a-Box backup (--skip-miab-backup); mail keeps running until phase quiesce."
		return 1
	fi
	if [ "$(backup_target)" = off ]; then
		say "Backups are turned off: no fresh Mail-in-a-Box backup; mail keeps running until phase quiesce."
		return 1
	fi
	if [ -e "$STORAGE_ROOT/backup/custom.yaml.upgrade-saved" ] || [ -e "$STORAGE_ROOT/backup/custom.yaml.upgrade-none" ]; then
		# backup.py would see "target: off" and do nothing.
		die "The backups are paused by this tool; a backup now would not run. Use --skip-miab-backup."
	fi
	[ -x "$dir/management/backup.py" ] || die "$dir/management/backup.py is missing. Use --skip-miab-backup to go on without a fresh backup."
	return 0
}

# After waiting for a running backup (or when the preflight saw one running):
# it must have left a backup that is recent enough (like check_backup), or the
# next one would likely fail too.
backup_check_after_wait() {
	local last
	[ -z "$NO_BACKUP_CHECK" ] && [ "$(backup_target)" != off ] || return 0
	last=$(last_backup_epoch)
	if [ -z "$last" ] || [ $(($(date +%s) - last)) -gt "$BACKUP_MAX_AGE" ]; then
		die "The backup that ran has not left a backup younger than $(fmt_dur "$BACKUP_MAX_AGE") (see System >
Backup Status and the mail to the administrator). Nothing was stopped yet. Fix it and run
the command again, or use --no-backup-check."
	fi
}

# With mail stopped (stop_mail): the backup is the last state of the mail.
run_miab_backup() {
	local dir
	dir=$(state_get OLD_MIAB_DIR)
	if [ -n "$(backup_pids)" ]; then
		die "A backup is running already. Wait until it is finished and run the command again."
	fi
	say "Running a Mail-in-a-Box backup now ($dir/management/backup.py, target ${F[BACKUP_TARGET]:-local})."
	say "backup.py stops Postfix, Dovecot, postgrey and PHP for its run and starts them again"
	say "afterwards. They are masked now, so that start fails ('Unit ... is masked'), as it should:"
	say "mail stays offline until setup."
	local rc=0 started
	started=$(date +%s)
	(cd "$dir" && management/backup.py) < /dev/null || rc=$?
	FAILED_CMD=
	[ "$rc" = 0 ] || die "The backup failed (exit code $rc, see above). Fix it (System > Backup Status), or
use --skip-miab-backup if a recent backup exists. Mail stays offline until then; --rollback
brings it back."
	state_set MIAB_BACKUP_AT "$(date -u +%FT%TZ)"
	say "Backup done ($(fmt_dur $(($(date +%s) - started))))."
}

# Copy the encrypted archive to an rsync target: <path>-system/<stamp>/ on the
# backup server, with the backup SSH key, like management/backup.py does.
offsite_rsync() { # URL FILE... (the first FILE names the stamp)
	local url=$1 rest hostpart userhost port=22 path dest rsh out stamp
	shift
	stamp=$(state_get SNAPSHOT_STAMP)
	rest=${url#rsync://}
	hostpart=${rest%%/*}
	if [[ $rest == */* ]]; then path=${rest#*/}; else path=; fi
	userhost=$hostpart
	if [[ $hostpart =~ ^(.*):([0-9]+)$ ]]; then
		userhost=${BASH_REMATCH[1]}
		port=${BASH_REMATCH[2]}
	fi
	path=${path%/}
	dest=${path:-mailinabox}-system/$stamp
	[[ $dest =~ ^[A-Za-z0-9._/~+-]+$ ]] || die "Unexpected characters in the backup path '$path'. Use --no-offsite and copy the archive yourself."
	[ -f /root/.ssh/id_rsa_miab ] || die "/root/.ssh/id_rsa_miab (the backup SSH key) is missing."
	local ssh=(ssh -p "$port" -i /root/.ssh/id_rsa_miab -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=30)
	rsh="ssh -p $port -i /root/.ssh/id_rsa_miab -oBatchMode=yes -oStrictHostKeyChecking=accept-new -oConnectTimeout=30"
	say "Copying the encrypted archive to $userhost:$dest/ (port $port)..."
	# One command, no shell syntax: restricted shells (e.g. SFTP/rsync-only storage accounts) run it as well.
	"${ssh[@]}" "$userhost" "mkdir -p $dest" < /dev/null || die "Could not create $dest on $userhost."
	rsync -t --partial -e "$rsh" "$@" "$userhost:$dest/" < /dev/null || die "Could not copy the archive to $userhost:$dest/."
	out=$(rsync -anc --itemize-changes -e "$rsh" "$@" "$userhost:$dest/" < /dev/null) \
		|| die "Could not compare the copy on $userhost:$dest/."
	[ -z "$out" ] || die "The copy on $userhost:$dest/ differs from the archive here:
$out"
	state_set OFFSITE_COPY "$userhost:$dest/ (port $port)"
	say "Copied and verified (checksums)."
}

offsite_copy() {
	local arch=$1 key=$STORAGE_ROOT/backup/secret_key.txt enc target dir dest stamp gh
	stamp=$(state_get SNAPSHOT_STAMP)
	if [ -n "$NO_OFFSITE" ]; then
		say "The system archive stays only in $STATE_DIR (--no-offsite)."
		return 0
	fi
	[ -r "$key" ] || die "$key is missing; cannot encrypt the archive. Use --no-offsite."
	enc=$arch.gpg
	gh=$STATE_DIR/gnupg
	install -d -m 700 "$gh"
	say "Encrypting the archive with backup/secret_key.txt (gpg, AES256)..."
	gpg --homedir "$gh" --batch --yes --quiet --pinentry-mode loopback --passphrase-file "$key" \
		--symmetric --cipher-algo AES256 -o "$enc" "$arch" < /dev/null || die "gpg could not encrypt $arch."
	gpgconf --homedir "$gh" --kill all > /dev/null 2>&1 || true
	(cd "$(dirname "$enc")" && sha256sum "$(basename "$enc")") > "$enc.sha256"
	state_set SYSTEM_ARCHIVE_GPG "$enc"
	target=$(backup_target)
	case "$target" in
		rsync://*) offsite_rsync "$target" "$enc" "$enc.sha256" ;;
		local | file://*)
			if [ "$target" = local ]; then dir=$STORAGE_ROOT/backup/encrypted; else dir=${target#file://}; fi
			dest=${dir%/}-system/$stamp
			mkdir -p "$dest"
			cp "$enc" "$enc.sha256" "$dest/"
			cmp -s "$enc" "$dest/$(basename "$enc")" || die "The copy in $dest differs from $enc."
			state_set OFFSITE_COPY "$dest/"
			say "Copied the encrypted archive to $dest/."
			if [[ $dest == "$STORAGE_ROOT"/* ]]; then
				warn "That is on this machine. Copy $dest off the machine yourself if it matters."
			fi
			;;
		off) say "Backups are turned off: the encrypted archive stays in $STATE_DIR. Copy $enc off the machine yourself." ;;
		*)
			warn "Backups go to ${target%%://*}://...; this tool copies the archive only to rsync and file
targets. Copy $enc off this machine yourself (it is encrypted with backup/secret_key.txt)."
			;;
	esac
	say "To decrypt it later: gpg --batch --pinentry-mode loopback --passphrase-file secret_key.txt \\"
	say "  -d $(basename "$enc") > $(basename "$arch")"
}

phase_snapshot() {
	section "Snapshot"
	local stamp arch rc=0 p paths=() miab excl=() b q
	miab=$(state_get OLD_MIAB_DIR)
	arch=$(state_get SYSTEM_ARCHIVE)
	# The package lists, the system archive and the copy of /etc record the box
	# as it was, so they are taken while mail still runs: stop_mail masks and
	# disables units in /etc. A run interrupted after stop_mail keeps them.
	if [ "$(state_get QUIESCED)" = 1 ] && [ -f "$arch" ] && [ -d "$OLD_ETC" ] \
		&& [ "$(stat -c %Y "$arch")" -le "$(state_get QUIESCED_EPOCH)" ]; then
		say "Mail is offline since $(state_get QUIESCED_AT). The system archive from before stays: $arch"
	else
		stamp=$(date -u +%Y%m%dT%H%M%SZ)
		state_set SNAPSHOT_STAMP "$stamp"
		if [ "$(state_get QUIESCED)" = 1 ]; then
			# Only when the archive is gone, or an older version of this tool
			# stopped mail first: leave out the masks.
			for p in $(state_get MASKED_UNITS); do excl+=("--exclude=etc/systemd/system/$p"); done
			if [ ${#excl[@]} -gt 0 ]; then
				warn "Mail is offline already, so the system archive and the copy of /etc leave out the
masks of: $(state_get MASKED_UNITS)"
			fi
			if [ -n "$(state_get DISABLED_UNITS)" ]; then
				warn "These units are disabled in them (they were enabled): $(state_get DISABLED_UNITS)"
			fi
			if [ ! -d "$STATE_DIR/meta" ]; then save_meta; fi
		else
			save_meta
		fi

		for p in etc "${miab#/}" var/lib/z-push var/lib/munin usr/local/lib/owncloud var/spool/cron usr/local/bin; do
			if [ -n "$p" ] && [ -e "/$p" ]; then paths+=("$p"); fi
		done
		arch=$STATE_DIR/system-$stamp.tar.gz
		say "Saving $(printf '/%s ' "${paths[@]}")and the package lists to $arch..."
		rc=0
		tar --numeric-owner "${excl[@]}" -czf "$arch.new" -C / "${paths[@]}" -C "$STATE_DIR" meta 2> "$STATE_DIR/tar-errors.txt" || rc=$?
		# tar exits with 1 when a file changed while it was read.
		[ "$rc" -le 1 ] || die "Could not write the system archive (exit code $rc, see $STATE_DIR/tar-errors.txt)."
		mv "$arch.new" "$arch"
		chmod 600 "$arch"
		state_set SYSTEM_ARCHIVE "$arch"
		say "System archive: $(human "$(stat -c %s "$arch")")"

		# Taken once per upgrade and never replaced (the hooks rely on it). One left
		# by an earlier attempt (rolled back) is kept aside.
		if [ -d "$OLD_ETC" ] && [ -n "$(state_get ETC_SAVED_AT)" ]; then
			say "The copy of /etc from $(state_get ETC_SAVED_AT) stays: $OLD_ETC"
		else
			if [ -e "$OLD_ETC" ]; then mv "$OLD_ETC" "$OLD_ETC.$stamp"; fi
			mkdir -p "$OLD_ETC.new"
			tar -C "$OLD_ETC.new" --numeric-owner --strip-components=1 -xzf "$arch" etc \
				|| die "Could not unpack /etc from $arch."
			mv "$OLD_ETC.new" "$OLD_ETC"
			state_set ETC_SAVED_AT "$(date -u +%FT%TZ)"
			say "A copy of /etc as it is now: $OLD_ETC"
		fi

		offsite_copy "$arch"
	fi

	# Mail goes offline before the backup: mail that arrived after it would
	# not be in it (backup.py starts Postfix and Dovecot again after its run).
	if miab_backup_wanted; then
		stop_mail
		b=$(state_get MIAB_BACKUP_AT)
		q=$(state_get QUIESCED_AT)
		if [ -n "$b" ] && [ -n "$q" ] && [[ $b > $q ]]; then
			say "The backup of $b ran with mail offline already, so it holds all mail. Not again."
		else
			run_miab_backup
		fi
	fi

	say "Recording counts and key fingerprints (before the upgrade)..."
	local_bash "$FINGERPRINT_SCRIPT" "SR=$STORAGE_ROOT" > "$STATE_DIR/before-fingerprint.txt" \
		|| die "Could not record the fingerprints."
}

# ---------------------------------------------------------------------------
# Stopping and starting the services.

# Only one machine may back up to a backup target, and nothing may write a
# backup of a half-upgraded box: backup/custom.yaml says "target: off" until
# finish (or --rollback). Keep in sync with tools/migrate-to-2604.sh (marker
# and file names differ).
pause_backups() {
	local b=$STORAGE_ROOT/backup
	[ -d "$b" ] || return 0
	if [ -e "$b/custom.yaml.upgrade-saved" ] || [ -e "$b/custom.yaml.upgrade-none" ]; then return 0; fi
	if [ -f "$b/custom.yaml" ]; then
		mv "$b/custom.yaml" "$b/custom.yaml.upgrade-saved"
	else
		: > "$b/custom.yaml.upgrade-none"
	fi
	printf '%s\n' "# Backups paused by $SCRIPT_NAME until the upgrade is finished." \
		"# The real settings are in custom.yaml.upgrade-saved." 'target: "off"' > "$b/custom.yaml"
	chmod 600 "$b/custom.yaml"
	state_set BACKUPS_PAUSED 1
	say "Backups are paused until the upgrade is finished (backup/custom.yaml)."
}

resume_backups() {
	local b=$STORAGE_ROOT/backup
	if [ -f "$b/custom.yaml" ] && ! grep -qs "^# Backups paused by $SCRIPT_NAME" "$b/custom.yaml" \
		&& { [ -e "$b/custom.yaml.upgrade-saved" ] || [ -e "$b/custom.yaml.upgrade-none" ]; }; then
		warn "backup/custom.yaml was changed during the upgrade (System > Backup Status?). Kept it;
the settings from before the upgrade are in backup/custom.yaml.upgrade-saved (if any)."
		rm -f "$b/custom.yaml.upgrade-none"
		state_set BACKUPS_PAUSED ""
		return 0
	fi
	if [ -e "$b/custom.yaml.upgrade-saved" ]; then
		mv "$b/custom.yaml.upgrade-saved" "$b/custom.yaml"
		say "Backups resumed (backup/custom.yaml${F[BACKUP_TARGET]:+, target ${F[BACKUP_TARGET]}})."
	elif [ -e "$b/custom.yaml.upgrade-none" ]; then
		rm -f "$b/custom.yaml" "$b/custom.yaml.upgrade-none"
		say "Backups resumed (local backups, the default)."
	fi
	state_set BACKUPS_PAUSED ""
}

# The units that serve users or write to $STORAGE_ROOT, and what starts them,
# in the order in which they are stopped. Unlike LOCAL_UNITS in
# tools/migrate-to-2604.sh, the PHP-FPM units are found, not named.
quiesce_units() {
	local u cand=(apt-daily.timer apt-daily-upgrade.timer cron.service mailinabox.service nginx.service)
	mapfile -t -O ${#cand[@]} cand < <(systemctl list-unit-files --type=service --no-legend --plain 'php*-fpm.service' 2> /dev/null | awk '{print $1}' || true)
	cand+=(postfix.service postfix@-.service spampd.service postgrey.service opendkim.service opendmarc.service
		dovecot.socket dovecot.service munin.service munin-node.service)
	for u in "${cand[@]}"; do
		if systemctl cat "$u" > /dev/null 2>&1; then echo "$u"; fi
	done
}

# Mask the units (in /etc, so that they stay off across the reboots of the
# release upgrades; package upgrades do not start masked units either).
# A unit with its own file in /etc/systemd/system (e.g. a link into the old
# checkout) cannot be masked: it is disabled instead.
mask_units() {
	local u st failed=()
	# What is enabled now is enabled again by unquiesce: a package that is
	# purged, or installed while its unit is masked (the release upgrade,
	# cleanup_dovecot), leaves the unit disabled ("Failed to preset unit: ...
	# is masked"), and unmasking does not enable it (B67). A unit masked by an
	# earlier call reports "masked" and is not recorded again.
	for u in "$@"; do
		if [ "$(systemctl is-enabled "$u" 2> /dev/null || true)" = enabled ]; then state_add ENABLED_BEFORE "$u"; fi
	done
	# Recorded first: an interruption must not leave masks nobody removes.
	state_add MASKED_UNITS "$@"
	for u in "$@"; do
		systemctl mask --quiet "$u" 2> /dev/null || true
		st=$(systemctl is-enabled "$u" 2> /dev/null || true)
		[ "$st" != masked ] || continue
		failed+=("$u")
		if [ "$st" = enabled ]; then
			state_add DISABLED_UNITS "$u"
			systemctl disable --quiet "$u" 2> /dev/null || warn "Could not disable $u."
		fi
		warn "Could not mask $u (its unit file is in /etc/systemd/system); disabled it instead."
	done
	if [ ${#failed[@]} -gt 0 ]; then
		state_set MASKED_UNITS "$(for u in $(state_get MASKED_UNITS); do [[ " ${failed[*]} " == *" $u "* ]] || echo "$u"; done | tr '\n' ' ' | sed 's/ $//')"
	fi
	return 0
}

# During the downtime: make sure the units are still masked and stopped (after
# a reboot, a package upgrade or an interrupted run). Until setup starts them.
requiesce() {
	downtime_active || return 0
	[ -z "$(state_get SETUP_STARTED_AT)" ] || return 0
	local u active=()
	for u in $(state_get MASKED_UNITS); do
		if [ "$(systemctl is-enabled "$u" 2> /dev/null || true)" != masked ]; then
			systemctl mask --quiet "$u" 2> /dev/null || warn "Could not mask $u again."
		fi
	done
	for u in $(state_get MASKED_UNITS) $(state_get DISABLED_UNITS); do
		if systemctl is-active --quiet "$u" 2> /dev/null; then active+=("$u"); fi
	done
	if [ ${#active[@]} -gt 0 ]; then
		warn "Running again: ${active[*]}. Stopping them; mail stays offline until setup."
		systemctl stop "${active[@]}" 2> /dev/null || warn "Not all of them stopped: ${active[*]}"
	fi
	return 0
}

# Unmask (and enable again) the recorded units, except the ones given.
unquiesce() { # [UNITS TO KEEP OFF]...
	local keep=" $* " u m=() d=() rest_m=() rest_d=()
	for u in $(state_get MASKED_UNITS); do
		case "$keep" in *" $u "*) rest_m+=("$u") ;; *) m+=("$u") ;; esac
	done
	for u in $(state_get DISABLED_UNITS); do
		case "$keep" in *" $u "*) rest_d+=("$u") ;; *) d+=("$u") ;; esac
	done
	if [ ${#m[@]} -gt 0 ]; then systemctl unmask --quiet "${m[@]}" 2> /dev/null || warn "Could not unmask all of ${m[*]}."; fi
	# Only what is still masked stays recorded (for the next attempt).
	for u in "${m[@]}"; do
		if [ "$(systemctl is-enabled "$u" 2> /dev/null || true)" = masked ]; then
			warn "$u is still masked."
			rest_m+=("$u")
		fi
	done
	for u in "${d[@]}"; do
		if systemctl cat "$u" > /dev/null 2>&1; then systemctl enable --quiet "$u" 2> /dev/null || warn "Could not enable $u again."; fi
	done
	state_set MASKED_UNITS "${rest_m[*]}"
	state_set DISABLED_UNITS "${rest_d[*]}"
	# Enable again what was enabled before the masks (see mask_units).
	local again=() rest_e=()
	for u in $(state_get ENABLED_BEFORE); do
		if [[ " ${m[*]} " != *" $u "* ]] || [[ " ${rest_m[*]} " == *" $u "* ]]; then
			rest_e+=("$u")
		elif [ "$(systemctl is-enabled "$u" 2> /dev/null || true)" = disabled ]; then
			if systemctl enable --quiet "$u" 2> /dev/null; then again+=("$u"); else warn "Could not enable $u again."; fi
		fi
	done
	if [ ${#again[@]} -gt 0 ]; then
		say "Enabled again (the upgrade had left them disabled, so they would not start after a reboot): ${again[*]}"
	fi
	state_set ENABLED_BEFORE "${rest_e[*]}"
}

# Wait until no process here uses $STORAGE_ROOT (for the fingerprint, and so
# that no job is cut off by the release upgrade). tools/migrate-to-2604.sh has
# the same for both boxes; this is its local branch, without the rollback mode.
wait_quiet() {
	local out start now shown=0 timeout=$QUIET_TIMEOUT
	start=$(date +%s)
	while :; do
		out=$(local_bash "$QUIET_SCRIPT" "SR=$STORAGE_ROOT") || die "Could not check the processes on this machine."
		out=$(grep '^BUSY ' <<< "$out" | sed 's/^BUSY /  /' || true)
		if [ -z "$out" ]; then
			if [ "$shown" = 1 ]; then say "Nothing uses $STORAGE_ROOT any more."; fi
			return 0
		fi
		now=$(date +%s)
		if [ $((now - start)) -ge "$timeout" ]; then
			die "These processes still use $STORAGE_ROOT after $(fmt_dur "$timeout") (PID, why, command):
$out
Let them finish (or end them), then run the command again. Mail stays offline."
		fi
		if [ "$shown" = 0 ] || [ $(((now - start) % 120)) -lt 10 ]; then
			say "Waiting until nothing uses $STORAGE_ROOT any more (at most $(fmt_dur "$timeout")):"
			say "$out"
			shown=1
		fi
		sleep 10
	done
}

# Mail goes offline: remember what runs, mask and stop the units (masked,
# they stay off across reboots), wait until nothing uses $STORAGE_ROOT. In
# phase snapshot before the fresh backup, otherwise in phase quiesce. The
# first call starts the downtime (QUIESCED_AT); later calls (an interrupted
# run, phase quiesce after snapshot) only make sure everything is off.
stop_mail() {
	local units=() u active=()
	mapfile -t units < <(quiesce_units)
	if [ "$(state_get QUIESCED)" != 1 ]; then
		read_facts
		if [ "${F[APT_BUSY]:-0}" = 1 ]; then
			die "Package updates are running (apt-daily / unattended-upgrades). Wait until they are finished
and run the command again. Nothing was stopped yet."
		fi
		wait_backup_done
		if [ -n "$BACKUP_WAITED" ] || [ "$(state_get BACKUP_CHECK_DEFERRED)" = 1 ]; then
			backup_check_after_wait
			# The facts (apt) may have changed meanwhile.
			read_facts
			if [ "${F[APT_BUSY]:-0}" = 1 ]; then
				die "Package updates are running (apt-daily / unattended-upgrades). Wait until they are finished
and run the command again. Nothing was stopped yet."
			fi
		fi
		run_hooks before "$HOOK_BEFORE_DIR"
		for u in "${units[@]}"; do
			if systemctl is-active --quiet "$u" 2> /dev/null; then active+=("$u"); fi
		done
		state_add ACTIVE_BEFORE "${active[@]}"
		state_set QUIESCED 1
		state_set QUIESCED_AT "$(date -u +%FT%TZ)"
		state_set QUIESCED_EPOCH "$(date +%s)"
		say "Mail goes OFFLINE now (the downtime starts)."
	fi
	say "Stopping and masking: ${units[*]}"
	mask_units "${units[@]}"
	systemctl stop "${units[@]}" 2> /dev/null || warn "Not all services stopped: ${units[*]}"
	wait_quiet
}

phase_quiesce() {
	if [ "$(state_get QUIESCED)" = 1 ]; then
		section "Pausing the backups (mail is offline since $(state_get QUIESCED_AT))"
	else
		section "Stopping mail (the downtime starts)"
	fi
	stop_mail
	# After the fresh backup of phase snapshot (backup.py would see "off");
	# cron is masked, so no nightly backup runs in between.
	pause_backups
	local q
	q=$(local_bash "$QUEUE_SCRIPT" "SR=$STORAGE_ROOT" 2> /dev/null || true)
	local -A Q=()
	load_kv Q <<< "$q"
	if [ "${Q[QUEUE_TOTAL]:-0}" -gt 0 ] 2> /dev/null; then
		warn "${Q[QUEUE_TOTAL]} messages are in the Postfix queue${Q[QUEUE_LOCAL]:+ (${Q[QUEUE_LOCAL]} for mailboxes of this box)}.
They stay in /var/spool/postfix and are delivered when Postfix runs again after setup."
	fi
	say "Recording counts and key fingerprints again, now that nothing changes..."
	local_bash "$FINGERPRINT_SCRIPT" "SR=$STORAGE_ROOT" > "$STATE_DIR/before-fingerprint.txt" \
		|| die "Could not record the fingerprints."
	if command -v docker > /dev/null && [ "$(docker ps -q 2> /dev/null | wc -l)" -gt 0 ]; then
		warn "Docker containers are running and were NOT stopped: $(docker ps --format '{{.Names}}' 2> /dev/null | tr '\n' ' ')
If they use the mail, stop them with a hook in $HOOK_BEFORE_DIR next time (see the header)."
	fi
	say
	say "MAIL IS OFFLINE NOW (since $(state_get QUIESCED_AT)). Senders queue their mail and retry;"
	say "nsd keeps answering DNS. Mail comes back when setup has finished."
}

# ---------------------------------------------------------------------------
# The release upgrades.

# Move the third-party apt sources and their keys to $APT_DISABLED (and
# comment out such lines in sources.list); "manifest" lists ORIGINAL STORED
# pairs for --rollback.
disable_third_party_sources() {
	local f k keys=() man=$APT_DISABLED/manifest line
	mkdir -p "$APT_DISABLED/sources.list.d" "$APT_DISABLED/keys"
	touch "$man"
	for f in /etc/apt/sources.list.d/*; do
		[ -f "$f" ] || continue
		is_ubuntu_source "$f" && continue
		# Keyrings named with signed-by=, if they live in /etc/apt.
		while IFS= read -r k; do
			if [[ $k == /etc/apt/* ]] && [ -f "$k" ]; then keys+=("$k"); fi
		done < <(grep -hoE '(signed-by=|Signed-By:[[:space:]]*)/[^] ,]+' "$f" 2> /dev/null | sed 's/^[^/]*//' || true)
		mv "$f" "$APT_DISABLED/sources.list.d/"
		printf '%s %s\n' "$f" "$APT_DISABLED/sources.list.d/$(basename "$f")" >> "$man"
		say "  disabled $f"
	done
	if [ -n "$(third_party_lines)" ] && [ ! -e "$APT_DISABLED/sources.list" ]; then
		cp -p /etc/apt/sources.list "$APT_DISABLED/sources.list"
		printf '%s %s\n' /etc/apt/sources.list "$APT_DISABLED/sources.list" >> "$man"
		while IFS= read -r line; do
			# Comment out exactly these lines (fixed strings, not patterns).
			LINE=$line awk '$0 == ENVIRON["LINE"] {print "# disabled by '"$SCRIPT_NAME"': " $0; next} {print}' \
				/etc/apt/sources.list > /etc/apt/sources.list.new
			mv /etc/apt/sources.list.new /etc/apt/sources.list
			say "  commented out in /etc/apt/sources.list: $line"
		done < <(third_party_lines)
	fi
	# Keys in trusted.gpg.d that no package installed are for third-party sources
	# (APT trusts them for every source).
	# Ubuntu's own (archive, Ubuntu Pro / ESM) stay.
	for f in /etc/apt/trusted.gpg.d/*; do
		[ -f "$f" ] || continue
		case "${f##*/}" in ubuntu*) continue ;; esac
		dpkg -S "$f" > /dev/null 2>&1 && continue
		keys+=("$f")
	done
	for k in "${keys[@]}"; do
		[ -f "$k" ] || continue
		# Still named by a source that stays?
		if grep -rqsF -- "$k" /etc/apt/sources.list /etc/apt/sources.list.d/ 2> /dev/null; then continue; fi
		mkdir -p "$APT_DISABLED/keys$(dirname "$k")"
		mv "$k" "$APT_DISABLED/keys$k"
		printf '%s %s\n' "$k" "$APT_DISABLED/keys$k" >> "$man"
		say "  moved the key $k"
	done
}

restore_apt_sources() {
	local man=$APT_DISABLED/manifest orig stored
	[ -f "$man" ] || return 0
	while read -r orig stored; do
		[ -n "$orig" ] && [ -e "$stored" ] || continue
		mkdir -p "$(dirname "$orig")"
		mv -f "$stored" "$orig"
		say "  restored $orig"
	done < "$man"
	rm -f "$man"
}

set_prompt_lts() {
	local f=/etc/update-manager/release-upgrades
	if [ ! -f "$f" ]; then
		mkdir -p /etc/update-manager
		printf '[DEFAULT]\nPrompt=lts\n' > "$f"
	elif grep -q '^[[:space:]]*Prompt[[:space:]]*=' "$f"; then
		sed -i 's/^[[:space:]]*Prompt[[:space:]]*=.*/Prompt=lts/' "$f"
	else
		printf 'Prompt=lts\n' >> "$f"
	fi
}

phase_prepare_release() {
	section "Preparing the packages for the release upgrade"
	local held purge=() down=() p ver pins=()

	held=$(apt-mark showhold 2> /dev/null | tr '\n' ' ' || true)
	if [ -n "$held" ]; then
		state_add HELD_PACKAGES "$held"
		# shellcheck disable=SC2086 # a list of package names
		apt-mark unhold $held > /dev/null || warn "Could not release the held packages $held."
		say "Released the held packages (do-release-upgrade needs that): $held"
	fi

	mapfile -t purge < <(purge_set)
	mapfile -t down < <(downgrade_set)
	if [ ${#purge[@]} -gt 0 ] || [ ${#down[@]} -gt 0 ]; then
		# Keep the .deb files while their sources are still there, for --rollback.
		mkdir -p "$PURGED_DEBS"
		say "Saving the .deb files of ${#purge[@]} packages to remove and ${#down[@]} to switch back to Ubuntu (for --rollback)..."
		for p in "${purge[@]}" "${down[@]}"; do
			ver=$(dpkg-query -W -f='${Version}' "$p" 2> /dev/null || true)
			(cd "$PURGED_DEBS" && apt-get -q -q download "${p%%:*}=$ver" < /dev/null > /dev/null 2>&1) \
				|| warn "Could not save $p $ver (not in the package sources any more); --rollback cannot put it back."
		done
		state_add PURGED_PACKAGES "${purge[@]}"
		state_add SWITCHED_PACKAGES "${down[@]}"
		p=$(printf '%s\n' "${purge[@]}" | grep -Ex "$PHP_TOOLING_RE" | tr '\n' ' ' || true)
		if [ -n "$p" ]; then
			state_add PHP_TOOLING_REMOVED $p
			warn "Also removed (PHP tooling): $p"
		fi
	fi

	say "Disabling the third-party package sources (kept in $APT_DISABLED):"
	disable_third_party_sources
	apt_update || die "apt-get update failed."

	if [ ${#purge[@]} -gt 0 ]; then
		say "Removing PHP from ppa:ondrej and obsolete packages: ${purge[*]}"
		purge_only "$PHP_NAME_RE|$PHP_TOOLING_RE|dovecot-antispam" "${purge[@]}"
	fi
	if [ ${#down[@]} -gt 0 ]; then
		for p in "${down[@]}"; do
			ver=$(apt-cache madison "${p%%:*}" 2> /dev/null | awk -F' [|] ' 'v == "" {v = $2} END {print v}' | tr -d ' ' || true)
			if [ -n "$ver" ]; then pins+=("$p=$ver"); else warn "Ubuntu has no $p; it stays as it is."; fi
		done
		if [ ${#pins[@]} -gt 0 ]; then
			if apt-get -s -q --allow-downgrades install "${pins[@]}" < /dev/null 2> /dev/null | grep -q '^Remv '; then
				warn "Switching ${pins[*]} back to Ubuntu's versions would remove other packages; left as they are."
			else
				say "Switching back to Ubuntu's versions: ${pins[*]}"
				apt_get --allow-downgrades install "${pins[@]}" || warn "Could not switch all of ${pins[*]}."
			fi
		fi
	fi

	say "Bringing the installed packages up to date (Ubuntu ${F[OS_VERSION]})..."
	apt_get dist-upgrade || die "apt-get dist-upgrade failed (see above)."
	local missing=()
	for p in update-manager-core sqlite3 rsync tmux; do pkg_installed "$p" || missing+=("$p"); done
	if [ ${#missing[@]} -gt 0 ]; then apt_get install "${missing[@]}" || die "Could not install ${missing[*]}."; fi

	if [ -z "$(state_get PROMPT_OLD)" ]; then state_set PROMPT_OLD "${F[PROMPT]:-unset}"; fi
	set_prompt_lts
	requiesce

	if [ "$(os_version)" != 26.04 ]; then
		local out rc=0
		out=$(do-release-upgrade -c 2>&1 < /dev/null) || rc=$?
		# The exit code differs between versions of the upgrader; its message does not.
		if ! grep -q "^New release '" <<< "$out"; then
			die "do-release-upgrade does not offer the next release (exit code $rc):
$(sed 's/^/  /' <<< "$out")
Mail stays offline. When it is offered, run the command again; or go back with --rollback."
		fi
		say "$(grep "^New release '" <<< "$out" | head -n 1 || true)"
	fi
}

# Install a unit that continues the upgrade after the reboot, in a tmux
# session the operator can attach to (or directly, without tmux).
install_resume() {
	local flags cmd
	flags=$(state_get RESUME_FLAGS)
	cmd="$(printf '%q' "$STATE_DIR/$SCRIPT_NAME")${flags:+ $flags} --yes --resumed"
	{
		echo '#!/bin/bash'
		echo "# Written by $SCRIPT_NAME: continues the upgrade after a reboot."
		echo "# Removed when the upgrade is finished."
		printf 'SESSION=%q\n' "$TMUX_SESSION"
		printf 'CMD=%q\n' "$cmd"
		printf 'export UPGRADE_STATE_DIR=%q\n' "$STATE_DIR"
		if [ -n "${TAG:-}" ]; then printf 'export TAG=%q\n' "$TAG"; fi
		if [ -n "${SOURCE:-}" ]; then printf 'export SOURCE=%q\n' "$SOURCE"; fi
		cat <<'EOF'
export HOME=/root TERM=xterm-256color LANG=C.UTF-8 NEEDRESTART_SUSPEND=1 NEEDRESTART_MODE=l
# In a scope of its own, outside this unit's cgroup: restarting the unit
# (needrestart, daemon-reexec) must not kill the upgrade.
SCOPE=()
if command -v systemd-run > /dev/null 2>&1; then SCOPE=(systemd-run --scope --quiet --collect "--unit=upgrade-2604-$(date +%s)" --); fi
if command -v tmux > /dev/null 2>&1; then
	if tmux has-session -t "$SESSION" 2> /dev/null; then exit 0; fi
	# After a successful run the window closes by itself after 60 seconds:
	# nobody may be attached after the last reboot (B72). After a failure it
	# stays open until Enter is pressed.
	"${SCOPE[@]}" tmux new-session -d -s "$SESSION" -x 200 -y 50 \
		"trap : INT QUIT; $CMD; rc=\$?; echo; if [ \$rc = 0 ]; then echo \"The upgrade script ended with exit code 0. Press Enter to close this window (it closes by itself after 60 seconds).\"; read -r -t 60 _; else echo \"The upgrade script ended with exit code \$rc. Press Enter to close this window.\"; read -r _; fi; exit \$rc"
	exit 0
fi
eval "exec ${SCOPE[*]} $CMD"
EOF
	} > "$RESUME_SCRIPT"
	chmod 700 "$RESUME_SCRIPT"
	# Type=simple: the boot does not wait for it. RemainAfterExit keeps the
	# tmux server (in this unit's cgroup) alive after resume.sh has exited.
	cat > "$RESUME_UNIT_FILE" <<EOF
# Written by $SCRIPT_NAME; removed when the upgrade is finished.
[Unit]
Description=Continue the upgrade of Mail-in-a-Box to Ubuntu 26.04 ($SCRIPT_NAME)
Wants=network-online.target
After=network-online.target
ConditionPathExists=$RESUME_SCRIPT

[Service]
Type=simple
RemainAfterExit=yes
ExecStart=/bin/bash $RESUME_SCRIPT
StandardOutput=journal+console
StandardError=journal+console

[Install]
WantedBy=multi-user.target
EOF
	systemctl daemon-reload
	systemctl enable --quiet "$RESUME_UNIT" || die "Could not enable $RESUME_UNIT."
	motd_hint
}

remove_resume() {
	if [ -f "$RESUME_UNIT_FILE" ]; then
		# Not stopped: this run may be its process.
		systemctl disable --quiet "$RESUME_UNIT" 2> /dev/null || true
		rm -f "$RESUME_UNIT_FILE"
		systemctl daemon-reload || true
	fi
	rm -f "$RESUME_SCRIPT"
	motd_remove
}

motd_hint() { # [offline|after-setup|verify-failed]
	local how
	case "${1:-offline}" in
		after-setup) how="Mail runs again (setup has finished); the last checks are pending." ;;
		verify-failed) how="Mail runs again, but the final checks FAILED: see --status, then run it again or --finish." ;;
		*) how="Mail is offline. The upgrade continues on its own after each reboot." ;;
	esac
	local next
	if [ "${1:-offline}" = offline ] && next=$(next_release); then
		how+=$'\n'$(release_access_text "$next" reboot)
	fi
	motd_remove
	if [ ! -e "$MOTD_FILE" ]; then state_set MOTD_CREATED 1; fi
	cat >> "$MOTD_FILE" <<EOF
$MOTD_BEGIN
*** Mail-in-a-Box is being upgraded to Ubuntu 26.04 ($SCRIPT_NAME). ***
$how
If SSH does not come back after a reboot, use the provider's console (VNC/KVM).
  follow it:  sudo tmux attach -t $TMUX_SESSION (detach: Ctrl-b d)
          or  sudo tail -f $LOG_FILE
  state:      $SELF --status
$MOTD_END
EOF
}

motd_remove() {
	[ -f "$MOTD_FILE" ] || return 0
	if grep -qF "$MOTD_BEGIN" "$MOTD_FILE"; then
		B=$MOTD_BEGIN E=$MOTD_END awk '$0 == ENVIRON["B"] {skip = 1} !skip {print} $0 == ENVIRON["E"] {skip = 0}' \
			"$MOTD_FILE" > "$MOTD_FILE.new"
		mv "$MOTD_FILE.new" "$MOTD_FILE"
	fi
	if [ "$(state_get MOTD_CREATED)" = 1 ] && [ ! -s "$MOTD_FILE" ]; then
		rm -f "$MOTD_FILE"
		state_set MOTD_CREATED ""
	fi
	return 0
}

# Reboot; the resume unit runs this script again afterwards.
# sshd must come up after the reboot: on 24.04 and later it is started by
# ssh.socket, and a release upgrade can leave neither unit enabled.
ensure_ssh() {
	local out rc=0 u
	if ! systemctl cat ssh.service > /dev/null 2>&1 && ! systemctl cat ssh.socket > /dev/null 2>&1; then
		warn "openssh-server is not installed; after the reboot there is no SSH. Use the provider's console."
		return 0
	fi
	for u in ssh.socket ssh.service; do
		if systemctl is-enabled --quiet "$u" 2> /dev/null; then break; fi
		u=
	done
	if [ -z "$u" ]; then
		if systemctl cat ssh.socket > /dev/null 2>&1; then u=ssh.socket; else u=ssh.service; fi
		systemctl unmask --quiet "$u" 2> /dev/null || true
		systemctl enable --quiet "$u" 2> /dev/null || true
		if systemctl is-enabled --quiet "$u" 2> /dev/null; then
			warn "Neither ssh.socket nor ssh.service was enabled; enabled $u."
		else
			die "Neither ssh.socket nor ssh.service is enabled, and $u could not be enabled: SSH would
not come back after the reboot. Not rebooting. Fix it ('systemctl enable ssh.socket'), then run
the command again."
		fi
	fi
	out=$(sshd -t 2>&1) || rc=$?
	[ "$rc" = 0 ] || die "sshd -t fails (exit code $rc); SSH would not come back after the reboot:
$(sed 's/^/  /' <<< "$out")
Not rebooting. Fix /etc/ssh/sshd_config (the old one is in $OLD_ETC/ssh), then run the command again."
	say "SSH:             $u enabled, sshd -t ok${out:+ ($out)}"
	return 0
}

reboot_and_resume() {
	local why=$1 i
	ensure_ssh
	install_resume
	state_set REBOOT_BOOT_ID "$(boot_id)"
	state_set REBOOT_REASON "$why"
	state_set REBOOTS "$(($(state_get REBOOTS || true) + 1))"
	section "Rebooting: $why"
	say "The upgrade continues on its own after the reboot ($RESUME_UNIT)."
	say "Log in again in a few minutes and follow it with:"
	say "  sudo tmux attach -t $TMUX_SESSION     (detach: Ctrl-b d)"
	say "  sudo tail -f $LOG_FILE"
	local next line
	if next=$(next_release); then
		while IFS= read -r line; do say "$line"; done < <(release_access_text "$next" reboot)
		say "If the machine does not come back on the network at all, look at the provider's console;"
		say "do not reboot it while the release upgrade runs."
	else
		say "If the machine does not come back on the network, use the provider's console."
	fi
	if [ -z "$ASSUME_YES" ]; then
		for i in 10 9 8 7 6 5 4 3 2 1; do
			printf '\rRebooting in %2d seconds (Ctrl-C stops; run the command again to continue)... ' "$i" > /dev/tty 2> /dev/null || true
			sleep 1
		done
		echo > /dev/tty 2> /dev/null || true
	fi
	sync
	systemctl reboot || die "systemctl reboot failed. Reboot by hand; the upgrade continues afterwards."
	# Wait for the shutdown to end this process.
	sleep 600
	exit 0
}

# A reboot that was scheduled but did not happen (countdown interrupted).
pending_reboot() {
	local b
	b=$(state_get REBOOT_BOOT_ID)
	[ -n "$b" ] || return 0
	if [ "$b" = "$(boot_id)" ]; then
		reboot_and_resume "$(state_get REBOOT_REASON) (the reboot has not happened yet)"
	fi
	state_set REBOOT_BOOT_ID ""
}

codename_of() {
	case "$1" in 22.04) echo jammy ;; 24.04) echo noble ;; 26.04) echo resolute ;; esac
}

# Do the active apt sources name this release (codename)?
sources_name() {
	grep -hsv '^[[:space:]]*#' /etc/apt/sources.list /etc/apt/sources.list.d/*.list /etc/apt/sources.list.d/*.sources \
		2> /dev/null | grep -qw -- "$1"
}

# Nothing half-installed and nothing left to upgrade.
packages_clean() {
	local out
	[ -z "$(dpkg --audit 2> /dev/null || true)" ] || return 1
	# Not piped into grep -q: with pipefail, an early grep exit would look clean.
	out=$(apt-get -s -q dist-upgrade < /dev/null 2> /dev/null) || return 1
	! grep -qE '^(Inst|Remv|Conf) ' <<< "$out"
}

# After a release upgrade (also an interrupted one): finish what dpkg and apt
# left. Dies if the packages stay inconsistent; /etc/os-release alone says
# little (base-files is unpacked early).
settle_release() { # TO
	if packages_clean; then return 0; fi
	warn "The packages are not consistent after the release upgrade; running dpkg --configure -a and apt-get dist-upgrade."
	wait_apt_locks
	DEBIAN_FRONTEND=noninteractive dpkg --configure -a --force-confdef --force-confold < /dev/null || true
	apt_get -f install || true
	apt_update || true
	apt_get dist-upgrade || true
	packages_clean || die "The packages are still not consistent after the release upgrade to Ubuntu $1:
$(dpkg --audit 2> /dev/null | head -n 10 | sed 's/^/  /')
$(apt-get -s -q dist-upgrade < /dev/null 2> /dev/null | grep -E '^(Inst|Remv|Conf) ' | head -n 10 | sed 's/^/  /')
See /var/log/dist-upgrade/ and $LOG_FILE. Mail stays offline; not rebooting. Fix it
(dpkg --configure -a, apt-get -f install, apt-get dist-upgrade), then run the command again."
}

# The release upgrade is in place: settle the packages, check SSH, mark the
# phase and reboot.
release_done() { # PHASE TO
	settle_release "$2"
	ensure_ssh
	requiesce
	state_set "END_$1" "$(date +%s)"
	phase_mark_done "$1"
	reboot_and_resume "Ubuntu $2 is installed"
}

release_upgrade() { # PHASE FROM TO
	local phase=$1 from=$2 to=$3 cur rc=0 bid
	cur=$(os_version)
	bid=$(state_get "RELEASE_BOOT_ID_$phase")
	if [ "$cur" = "$to" ] || [ "$cur" = 26.04 ]; then
		if [ -z "$bid" ]; then
			say "Ubuntu $cur already; nothing to do for $(phase_label "$phase")."
			return 0
		fi
		# An earlier run of this phase was interrupted after the release changed.
		say "Ubuntu $cur: checking what the interrupted release upgrade left..."
		settle_release "$cur"
		ensure_ssh
		requiesce
		state_set "END_$phase" "$(date +%s)"
		phase_mark_done "$phase"
		if [ -e /run/reboot-required ] || [ "$bid" = "$(boot_id)" ]; then
			reboot_and_resume "Ubuntu $cur is installed"
		fi
		return 0
	fi
	[ "$cur" = "$from" ] || die "Expected Ubuntu $from here, found $cur."
	# do-release-upgrade wants all updates of the current release installed
	# (after the first release upgrade, 24.04 has its own).
	say "Installing the updates of Ubuntu $from first..."
	apt_update || die "apt-get update failed."
	apt_get dist-upgrade || die "apt-get dist-upgrade failed (see above)."
	requiesce
	if [ -e /run/reboot-required ]; then
		# do-release-upgrade refuses to run until then.
		reboot_and_resume "an updated package needs a reboot before the release upgrade"
	fi
	section "Release upgrade: Ubuntu $from -> $to"
	say "do-release-upgrade runs non-interactively and keeps the existing configuration files."
	say "It takes 20-60 minutes. Its own logs are in /var/log/dist-upgrade/."
	release_access_note "$to"
	# No question here: the downtime has started, and the start of the upgrade
	# was confirmed (the operator may not be watching any more).
	state_set RELEASE_STARTED 1
	state_set "RELEASE_BOOT_ID_$phase" "$(boot_id)"
	set_prompt_lts
	printf '%s\n' "// Written by $SCRIPT_NAME for the release upgrades; removed when it is finished." \
		'Dpkg::Options { "--force-confdef"; "--force-confold"; };' > "$APT_OVERRIDE"
	wait_apt_locks
	# Without a screen session of its own only where nothing hangs up: in tmux
	# or screen, or in the resume unit. The non-interactive frontend answers
	# its questions with the defaults.
	local noscreen=()
	if [ -n "$RESUMED" ] || in_multiplexer; then noscreen=(RELEASE_UPGRADER_NO_SCREEN=1); fi
	env "${noscreen[@]}" DEBIAN_FRONTEND=noninteractive \
		do-release-upgrade -f DistUpgradeViewNonInteractive < /dev/null || rc=$?
	FAILED_CMD=
	cur=$(os_version)
	if [ "$cur" = "$from" ] && sources_name "$(codename_of "$from")" && ! sources_name "$(codename_of "$to")"; then
		# The upgrader refused before it changed anything.
		state_set "RELEASE_BOOT_ID_$phase" ""
		if [ -z "$(state_get RELEASE_BOOT_ID_release_2404)" ] && [ -z "$(state_get RELEASE_BOOT_ID_release_2604)" ]; then
			state_set RELEASE_STARTED ""
		fi
		die "do-release-upgrade did not upgrade (exit code $rc); this is still Ubuntu $from with its
package sources. See its messages above and /var/log/dist-upgrade/main.log. Mail stays offline.
Fix the cause and run the command again$([ "$(state_get RELEASE_STARTED)" != 1 ] && echo ", or go back with: $SELF --rollback")."
	fi
	if [ "$cur" != "$to" ]; then
		die "do-release-upgrade ended (exit code $rc) and this machine still runs Ubuntu $cur.
See /var/log/dist-upgrade/main.log and apt.log. Mail stays offline. If it stopped halfway,
'dpkg --configure -a' and 'apt-get -f install' often finish it; check /etc/os-release. Then
run the command again (it starts do-release-upgrade again while this is Ubuntu $from),
or restore from the backups."
	fi
	if [ "$rc" != 0 ]; then warn "do-release-upgrade ended with exit code $rc. Checking the packages..."; fi
	release_done "$phase" "$to"
}

# What the operator runs into during a release upgrade. In the 22.04 test run
# new SSH logins failed for about 19 minutes from 22.04 to 24.04 (while
# openssh-server was unpacked but not yet configured) and for about 7 minutes
# from 24.04 to 26.04, and /usr/bin/sudo was missing for about 12 minutes
# while sudo-rs replaced sudo. Open connections and the run in tmux go on.
# From 24.04 to 26.04 tmux 3.6 replaces tmux 3.4 a few minutes in; the new
# client cannot attach to the running 3.4 server ("open terminal failed: not
# a terminal") and the old binary no longer runs with the new libraries, so
# until the reboot only clients attached before stay attached (B73). From
# 22.04 to 24.04 the 3.4 client attaches to the 3.2a server.
# WHEN: now (the release upgrade starts now) or reboot (it starts by itself
# after this reboot, before anyone can attach). Also in the motd.
release_access_text() { # TO now|reboot
	local mins=19 attach
	if [ "$1" = 26.04 ]; then mins=7; fi
	if [ "$2" = reboot ]; then
		echo "After the reboot the release upgrade to Ubuntu $1 starts by itself. While it replaces the"
		echo "SSH server, new SSH logins can fail for a while (about $mins minutes in a test run)."
		echo "If a login fails, wait a few minutes and try again. Do not reboot."
	else
		echo "During the release upgrade new SSH logins can fail for a while (about $mins minutes in a test"
		echo "run), while the SSH server is replaced. Connections that are open stay open, and the upgrade"
		if attach=$(own_session_attach); then
			echo "goes on in the session $TMUX_SESSION. To watch it, attach now and keep that connection"
			echo "open: $attach"
		elif in_multiplexer; then
			echo "goes on in your own tmux, screen or mosh session. Keep this connection open (if it drops,"
			echo "reattach to your session)."
		else
			echo "goes on. Keep this connection open."
		fi
		echo "If a new login fails, wait a few minutes and try again. Do not reboot."
	fi
	if [ "$1" = 26.04 ]; then
		echo "sudo is missing for a while (about 12 minutes in a test run) while sudo-rs replaces it:"
		if [ "$2" = reboot ]; then
			echo "sudo then fails with \"command not found\". Wait until it is back."
		else
			echo "sudo then fails with \"command not found\". Wait until it is back, or use a root shell"
			echo "opened before (sudo -i)."
		fi
		# After a reboot the resumed run is in the tool's tmux session.
		if [ "$2" = reboot ] || [ -n "${TMUX:-}" ]; then
			echo "A few minutes after the start tmux 3.6 replaces tmux 3.4. From then until the reboot a new"
			echo "\"tmux attach\" cannot reach a tmux session started before (\"open terminal failed: not a"
			echo "terminal\"); clients attached before stay attached. Follow the log instead:"
			echo "  sudo tail -f $LOG_FILE"
		fi
	fi
}

release_access_note() { # TO
	local line
	say
	while IFS= read -r line; do say "$line"; done < <(release_access_text "$1" now)
	say
}

# The command that attaches to this run, when it runs in the tool's own
# session (not when the operator started it in a tmux or screen session of
# their own, or under mosh).
own_session_attach() {
	[ -n "$RESUMED${MIAB_2604_MUX:-}" ] || return 1
	if [ -n "${TMUX:-}" ]; then
		echo "sudo tmux attach -t $TMUX_SESSION"
	elif [ -n "${STY:-}" ]; then
		echo "sudo screen -d -r $TMUX_SESSION"
	else
		return 1
	fi
}

# The release upgrade that comes next (24.04 or 26.04), if one is still to come.
next_release() {
	local cur
	cur=$(os_version)
	if ! phase_is_done release_2404 && [ "$cur" = 22.04 ]; then
		echo 24.04
	elif ! phase_is_done release_2604 && [ "$cur" = 24.04 ]; then
		echo 26.04
	else
		return 1
	fi
}

phase_release_2404() { release_upgrade release_2404 22.04 24.04; }
phase_release_2604() { release_upgrade release_2604 24.04 26.04; }

# ---------------------------------------------------------------------------
# Cleanup before setup, on 26.04.

cleanup_dovecot() {
	local pkgs=() core=(dovecot-core dovecot-imapd dovecot-pop3d dovecot-lmtpd dovecot-sqlite dovecot-sieve dovecot-managesieved)
	say "Dovecot: replacing the 2.3 configuration with a pristine 2.4 one (the mail stays in $STORAGE_ROOT)..."
	systemctl stop dovecot.socket dovecot.service 2> /dev/null || true
	mapfile -t pkgs < <(dpkg-query -W -f='${db:Status-Abbrev} ${binary:Package}\n' 'dovecot-*' mail-stack-delivery 2> /dev/null \
		| awk '$1 ~ /^(.i|rc)/ {print $2}' || true)
	move_aside /etc/dovecot
	if [ ${#pkgs[@]} -gt 0 ]; then
		purge_only '(dovecot-.*|mail-stack-delivery)(:[a-z0-9]+)?' "${pkgs[@]}"
	fi
	if [ -e /etc/dovecot ]; then move_aside /etc/dovecot; fi
	# Masked before the installation, so that it does not start Dovecot with
	# a configuration that setup has not written yet.
	systemctl mask --quiet dovecot.service dovecot.socket 2> /dev/null || true
	state_add MASKED_UNITS dovecot.socket dovecot.service
	apt_get install "${core[@]}" || die "Could not install ${core[*]}."
	systemctl mask --quiet dovecot.service dovecot.socket 2> /dev/null || true
	systemctl stop dovecot.socket dovecot.service 2> /dev/null || true
	[ -f /etc/dovecot/dovecot.conf ] || die "The Dovecot packages did not create /etc/dovecot/dovecot.conf."
	say "Dovecot $(dovecot --version 2> /dev/null | cut -d' ' -f1) with its own configuration; setup writes Mail-in-a-Box's part."
}

cleanup_php() {
	local pkgs=() d v
	mapfile -t pkgs < <(dpkg-query -W -f='${db:Status-Abbrev} ${binary:Package}\n' 'php*' 'libapache2-mod-php*' 2> /dev/null \
		| awk '$1 ~ /^rc/ || ($1 ~ /^.i/ && $2 ~ /^(php|libapache2-mod-php)(7\.[0-9]+|8\.[0134])([-:]|$)/) {print $2}' || true)
	if [ ${#pkgs[@]} -gt 0 ]; then
		say "PHP: removing the old versions (Mail-in-a-Box uses $PHP_VER, the Nextcloud chain $PHP_LEGACY_VER): ${pkgs[*]}"
		purge_only "$PHP_NAME_RE" "${pkgs[@]}"
	fi
	for d in /etc/php/*; do
		[ -d "$d" ] || continue
		v=${d##*/}
		if [ "$v" = "$PHP_VER" ] || [ "$v" = "$PHP_LEGACY_VER" ]; then
			# Keep it only if packages of that version are installed.
			if dpkg-query -W -f='${db:Status-Abbrev} ${binary:Package}\n' "php$v-*" 2> /dev/null | grep -q '^.i'; then continue; fi
		fi
		move_aside "$d"
	done
}

cleanup_misc() {
	local old cur u l t d
	old=$(state_get OLD_MIAB_DIR)
	if [ -d /usr/local/lib/mailinabox/env ]; then
		say "Removing the old Python environment /usr/local/lib/mailinabox/env (setup builds a new one)."
		rm -rf /usr/local/lib/mailinabox/env
	fi
	for u in mailinabox munin; do
		l=/etc/systemd/system/$u.service
		[ -L "$l" ] || continue
		t=$(readlink -f "$l" || true)
		if [ -n "$old" ] && [[ $t == "$old"/* ]]; then move_aside "$l"; fi
	done
	systemctl daemon-reload || true
	# pip packages of older Pythons (b2sdk, boto3, ... of Mail-in-a-Box v6x/v7x).
	cur=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2> /dev/null || true)
	for d in /usr/local/lib/python3.*; do
		[ -d "$d" ] || continue
		if [ -n "$cur" ] && [ "${d##*/python}" != "$cur" ]; then move_aside "$d"; fi
	done
	# Replaced by conf/sa-learn-ham.sh and sa-learn-spam.sh in this fork.
	move_aside /usr/local/bin/sa-learn-pipe.sh
}

cleanup_ntp() {
	local p=() x
	for x in ntp ntpsec ntpdate ntpsec-ntpdate ntpsec-ntpdig; do
		if pkg_installed "$x"; then p+=("$x"); fi
	done
	if [ ${#p[@]} -gt 0 ]; then
		say "Time: removing ${p[*]}."
		apt_get purge "${p[@]}" || warn "Could not remove ${p[*]}."
	fi
	if pkg_installed chrony; then
		systemctl enable --now --quiet chrony 2> /dev/null || warn "Could not start chrony."
		say "Time: chrony keeps the clock."
	else
		pkg_installed systemd-timesyncd || apt_get install systemd-timesyncd || warn "Could not install systemd-timesyncd."
		systemctl enable --now --quiet systemd-timesyncd 2> /dev/null || warn "Could not start systemd-timesyncd."
		timedatectl set-ntp true 2> /dev/null || true
		say "Time: systemd-timesyncd keeps the clock."
	fi
}

check_configs() {
	local l out used t missing=()
	if command -v nginx > /dev/null; then
		for l in /etc/nginx/modules-enabled/*; do
			if [ -L "$l" ] && [ ! -e "$l" ]; then move_aside "$l"; fi
		done
		if out=$(nginx -t 2>&1); then
			say "nginx -t:        ok"
		else
			warn "nginx -t fails (setup rewrites Mail-in-a-Box's part of the configuration):
$(sed 's/^/  /' <<< "$out")"
		fi
	fi
	if command -v postconf > /dev/null; then
		used=$(postconf -n 2> /dev/null | grep -oE '(^|[ ,=])(btree|cdb|cidr|dbm|environ|hash|inline|ldap|lmdb|memcache|mysql|nis|pcre|pgsql|pipemap|proxy|randmap|regexp|sdbm|socketmap|sqlite|static|tcp|texthash|unionmap|unix):' \
			| sed 's/^[ ,=]//; s/:$//' | sort -u || true)
		for t in $used; do
			postconf -m 2> /dev/null | grep -qx "$t" || missing+=("$t")
		done
		say "Postfix tables:  ${used//$'\n'/ }"
		if [ ${#missing[@]} -gt 0 ]; then
			warn "Postfix on Ubuntu 26.04 does not support these table types used in main.cf: ${missing[*]}
(postconf -m). Setup writes Mail-in-a-Box's own maps and installs postfix-sqlite; tables you
added yourself must be converted (e.g. hash: -> lmdb: and 'postmap lmdb:FILE')."
		fi
	fi
	if command -v opendkim > /dev/null; then
		if out=$(opendkim -n 2>&1); then say "opendkim -n:     ok"; else warn "opendkim -n reports: $out"; fi
	fi
	return 0
}

phase_cleanup_etc() {
	section "Cleaning up for Ubuntu 26.04 (before setup)"
	[ "$(os_version)" = 26.04 ] || die "This needs Ubuntu 26.04, this is $(os_version)."
	say "Everything removed here is kept in $MOVED_DIR; the /etc from before the upgrade is in $OLD_ETC."
	requiesce
	apt_update > /dev/null || warn "apt-get update failed."
	cleanup_dovecot
	cleanup_php
	cleanup_misc
	cleanup_ntp
	check_configs
}

# ---------------------------------------------------------------------------
# Setup.

# Bring an existing checkout of this fork to TAG (without TAG= to DEFAULT_TAG)
# from SOURCE: a 26.04 box with an older release of the fork (rerun), or
# CLONE_DIR from an earlier run. The checkout this script runs from stays as
# it is unless TAG= is set.
update_fork_dir() { # DIR TAG SOURCE
	local d=$1 tag=$2 source=$3 cur
	cur=$(git -C "$d" describe --always --tags 2> /dev/null || true)
	[ "$cur" != "$tag" ] || return 0
	if [ -z "${TAG:-}" ] && [ "$(state_get SCRIPT_CHECKOUT)" = "$d" ]; then
		say "Using $d as it is (${cur:-unknown version}): this script runs from it. Set TAG= to update it."
		return 0
	fi
	[ -d "$d/.git" ] || die "$d is not a git checkout, so it cannot be updated to $tag."
	check_origin "$d" "$source"
	say "Updating $d from ${cur:-an unknown version} to $tag..."
	if checkout_ref "$d" "$tag"; then return 0; fi
	if [ -z "${TAG:-}" ] && checkout_ref "$d" main; then
		warn "The release tag $tag is not published yet. Using the branch main instead."
		return 0
	fi
	die "Could not update $d to $tag from $source. Did you modify something in $d?"
}

# The fork's checkout that setup runs from: the old checkout if it is the
# fork already, the checkout this script came from, or a new clone in
# /root/mailinabox (the old checkout is moved to <dir>-<old version> first).
resolve_fork_dir() {
	local old ver d dest n=1 source=${SOURCE:-$DEFAULT_SOURCE} tag=${TAG:-$DEFAULT_TAG}
	d=$(state_get FORK_DIR)
	if [ -n "$d" ] && is_fork_dir "$d"; then
		MIAB_DIR=$d
		return 0
	fi
	old=$(state_get OLD_MIAB_DIR)
	ver=$(state_get OLD_MIAB_VERSION | tr -c 'A-Za-z0-9._-' '_' | sed 's/_*$//')
	if [ -n "$old" ] && is_fork_dir "$old"; then
		MIAB_DIR=$old
		update_fork_dir "$old" "$tag" "$source"
		state_set FORK_DIR "$MIAB_DIR"
		return 0
	fi
	if [ -n "$old" ] && [ -d "$old" ]; then
		dest=$old-${ver:-old}
		while [ -e "$dest" ]; do
			dest=$old-${ver:-old}.$n
			n=$((n + 1))
		done
		say "Moving the old Mail-in-a-Box checkout $old to $dest."
		mv "$old" "$dest"
		state_set OLD_MIAB_MOVED_TO "$dest"
	fi
	d=$(state_get SCRIPT_CHECKOUT)
	if [ -n "$d" ] && is_fork_dir "$d" && [ "$d" != "$old" ]; then
		# Its owner was checked when the upgrade started (main).
		MIAB_DIR=$d
		state_set FORK_DIR "$MIAB_DIR"
		return 0
	fi
	d=$CLONE_DIR
	if [ -e "$d" ]; then
		is_fork_dir "$d" || die "$d exists and is not a checkout of this fork. Move it away and run the command again."
		update_fork_dir "$d" "$tag" "$source"
	else
		command -v git > /dev/null || install_packages git
		say "Downloading Mail-in-a-Box $tag from $source to $d..."
		if ! git clone -q -b "$tag" --depth 1 "$source" "$d" < /dev/null; then
			if [ -n "${TAG:-}" ]; then die "Could not download $tag from $source."; fi
			warn "The release tag $tag is not published yet. Using the branch main instead."
			git clone -q -b main --depth 1 "$source" "$d" < /dev/null || die "Could not download $source."
		fi
	fi
	MIAB_DIR=$d
	state_set FORK_DIR "$MIAB_DIR"
}

# Run this fork's setup/start.sh. Sets SETUP_SECONDS. Keep in sync with
# tools/migrate-to-2604.sh; differs: the settings come from /etc/mailinabox.conf.
run_setup() {
	local nc
	nc=$(state_get NC_VERSION)
	if [ -n "$nc" ] && [ "${nc%%.*}" -lt 34 ] 2> /dev/null; then
		say "Nextcloud is upgraded step by step from $nc to 34 (one major version per step,"
		say "SQLite database). Depending on the size of the database this takes from"
		say "minutes to more than an hour. A copy of the database goes to owncloud-backup/."
	fi
	local -A C=()
	load_kv C < <(sed -n 's/^\([A-Z_][A-Z0-9_]*\)=/\1=/p' /etc/mailinabox.conf)
	local envs=(NONINTERACTIVE=1 SKIP_NETWORK_CHECKS=1
		"PRIMARY_HOSTNAME=${C[PRIMARY_HOSTNAME]:-}"
		"PUBLIC_IP=${C[PUBLIC_IP]:-}" "PUBLIC_IPV6=${C[PUBLIC_IPV6]:-}"
		"STORAGE_USER=${C[STORAGE_USER]:-user-data}" "STORAGE_ROOT=${C[STORAGE_ROOT]:-$STORAGE_ROOT}")
	if [ -n "${C[PRIVATE_IP]:-}" ]; then envs+=("PRIVATE_IP=${C[PRIVATE_IP]}"); fi
	if [ -n "${C[PRIVATE_IPV6]:-}" ]; then envs+=("PRIVATE_IPV6=${C[PRIVATE_IPV6]}"); fi
	[ -n "${C[PRIMARY_HOSTNAME]:-}" ] || die "/etc/mailinabox.conf has no PRIMARY_HOSTNAME."

	local rc=0 started
	started=$(date +%s)
	(cd "$MIAB_DIR" && env "${envs[@]}" setup/start.sh) < /dev/null || rc=$?
	FAILED_CMD=
	SETUP_SECONDS=$(($(date +%s) - started))
	say "Setup ran for $(fmt_dur "$SETUP_SECONDS")."
	return "$rc"
}

phase_setup() {
	resolve_fork_dir
	section "Running Mail-in-a-Box setup ($(cd "$MIAB_DIR" && git describe --always --tags 2> /dev/null || echo "$MIAB_DIR"))"
	if [ "$(state_get MODE)" != rerun ]; then
		[ "$(os_version)" = 26.04 ] || die "Setup needs Ubuntu 26.04, this is $(os_version)."
		state_set SETUP_STARTED_AT "$(date -u +%FT%TZ)"
		# Setup starts what it needs; cron (backups, Nextcloud jobs) and the
		# update timers stay off until it has finished.
		unquiesce cron.service apt-daily.timer apt-daily-upgrade.timer
	fi
	# Nothing goes offline before (no quiesce): the before stage runs here.
	if [ "$(state_get MODE)" = rerun ]; then run_hooks before "$HOOK_BEFORE_DIR"; fi
	local rc=0
	run_setup || rc=$?
	if [ "$rc" != 0 ]; then
		die "Setup failed (exit code $rc). See the output above and $LOG_FILE.
Fix the cause and run this command again; it continues with setup."
	fi
	state_set SETUP_SECONDS "$SETUP_SECONDS"
	state_set SETUP_END_EPOCH "$(date +%s)"
	if grep -qsF "$MOTD_BEGIN" "$MOTD_FILE"; then motd_hint after-setup; fi
	if [ "$(state_get MODE)" != rerun ]; then
		unquiesce apt-daily.timer apt-daily-upgrade.timer
		say "Mail is back online (setup has started the services)."
	fi
	# Setup does not start cron.
	systemctl start cron.service 2> /dev/null || true
}

# ---------------------------------------------------------------------------
# Hooks, checks, finish.

# The operator's hook scripts in DIR (*.sh, not in subdirectories), in the
# order of their names.
hook_files() { # DIR
	[ -d "$1" ] || return 0
	find "$1" -maxdepth 1 -type f -name '*.sh' 2> /dev/null | LC_ALL=C sort
}

# Run the hooks of a stage (see the header of this script). A failing hook
# stops the run, in stage "after" it only warns: mail runs again, and the
# upgrade is not undone for it.
run_hooks() { # STAGE DIR
	local stage=$1 dir=$2 hooks=() h rc host miab=${MIAB_DIR:-$(state_get FORK_DIR)}
	miab=${miab:-$(state_get OLD_MIAB_DIR)}
	# What the before hooks stop, the after hooks start again (once).
	if [ "$stage" = before ]; then state_set HOOKS_after_AT ""; fi
	mapfile -t hooks < <(hook_files "$dir")
	if [ ${#hooks[@]} -eq 0 ]; then
		if [ "$stage" = local-ext ]; then say "No hooks."; fi
		return 0
	fi
	if [ "$stage" != local-ext ]; then say "Hooks of stage $stage ($dir):"; fi
	host=$(sed -n 's/^PRIMARY_HOSTNAME=//p' /etc/mailinabox.conf 2> /dev/null || true)
	for h in "${hooks[@]}"; do
		say "Running $h..."
		rc=0
		(cd / && env HOOK_STAGE="$stage" STORAGE_ROOT="$STORAGE_ROOT" PRIMARY_HOSTNAME="$host" MIAB_DIR="$miab" \
			OLD_ETC="$OLD_ETC" MOVED_DIR="$MOVED_DIR" UPGRADE_STATE_DIR="$STATE_DIR" bash "$h") < /dev/null || rc=$?
		FAILED_CMD=
		[ "$rc" != 0 ] || continue
		case "$stage" in
			after) warn "The hook $h failed (exit code $rc). The upgrade is not undone for it; run the hook
again by hand when you have fixed it." ;;
			before) die "The hook $h failed (exit code $rc). Mail was not stopped yet. Fix it and run the
command again; all hooks of $dir run again." ;;
			*) die "The hook $h failed (exit code $rc). Fix it and run the command again;
all hooks run again." ;;
		esac
	done
	state_set "HOOKS_${stage//-/_}_AT" "$(date -u +%FT%TZ)"
}

phase_local_ext() {
	section "Local extensions (hooks in $HOOK_DIR)"
	resolve_fork_dir
	local rc out warnings
	run_hooks local-ext "$HOOK_DIR"
	if command -v doveconf > /dev/null; then
		rc=0
		out=$(doveconf -n 2>&1 > /dev/null) || rc=$?
		[ "$rc" = 0 ] || die "doveconf -n fails (exit code $rc):
$(sed 's/^/  /' <<< "$out")
Fix the Dovecot configuration (or the hook that wrote it) and run the command again."
		warnings=$(grep -i 'warning' <<< "$out" || true)
		[ -z "$warnings" ] || die "doveconf -n warns:
$(sed 's/^/  /' <<< "$warnings")
Fix the Dovecot configuration (or the hook that wrote it) and run the command again."
		say "doveconf -n:     ok"
		systemctl restart dovecot || die "Dovecot does not start, see 'journalctl -u dovecot'."
	fi
}

# Keep in sync with tools/migrate-to-2604.sh; differs: before/after labels.
compare_fingerprints() {
	local k o n status
	printf '  %-16s %-18s %-18s %s\n' "" "before" "after" ""
	for k in USERS ALIASES MAILBOXES MESSAGES SIEVE_SCRIPTS DKIM_KEY DNSSEC_KEYS TLS_KEY BACKUP_KEY LE_ACCOUNTS BAYES_SPAM BAYES_HAM NC_ACCOUNTS NC_CARDS NC_EVENTS; do
		o=${OLDFP[$k]:-}
		n=${NEWFP[$k]:-}
		if [ "$o" = "$n" ]; then
			status=OK
		elif [[ $k =~ ^(MESSAGES|BAYES_SPAM|BAYES_HAM)$ && $o =~ ^[0-9]+$ && $n =~ ^[0-9]+$ ]] && [ "$n" -ge "$o" ]; then
			status="OK (new mail since)"
		elif [[ $k =~ ^(MAILBOXES)$ && $o =~ ^[0-9]+$ && $n =~ ^[0-9]+$ ]] && [ "$n" -ge "$o" ]; then
			status="OK (new mailboxes since)"
		else
			status=DIFFERENT
			VERIFY_PROBLEMS+=("$k differs: before ${o:--}, after ${n:--}")
		fi
		printf '  %-16s %-18s %-18s %s\n' "$k" "${o:--}" "${n:--}" "$status"
	done
}

# The items (split at commas) of the smtpd_*_restrictions in BEFORE (output of
# "postconf -n") that are gone now, as "parameter: item". Setup rewrites these
# parameters and drops what an administrator added (e.g. a check_sender_access
# before greylisting). A DNS list that only got return codes (upstream v68:
# zen.spamhaus.org -> zen.spamhaus.org=127.0.0.[2..11]) is not gone. Keep in
# sync with tools/migrate-to-2604.sh.
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

# The units that were enabled before the upgrade (meta/unit-files.txt of
# phase snapshot, taken before the masks) and are disabled now. The services
# of Mail-in-a-Box are enabled again by unquiesce and verify_services (B67);
# for the others a release upgrade can have had its reasons. Units that setup
# turns off on purpose are left out, so that nobody is told to enable them
# again: spamd.service (setup/spamassassin.sh, spampd runs SpamAssassin itself;
# Ubuntu 24.04 had it enabled). Units that are gone (removed packages) or are
# static, generated or an alias now are not "disabled" and so not listed.
# Units that are started another way are left out too (unit_started_otherwise).
SETUP_DISABLED_UNITS="spamd.service"
units_disabled_now() {
	local ref=$STATE_DIR/meta/unit-files.txt u
	[ -s "$ref" ] || return 0
	LC_ALL=C join <(awk '$2 == "enabled" {print $1}' "$ref" | LC_ALL=C sort -u) \
		<(systemctl list-unit-files --no-legend --no-pager 2> /dev/null | awk '$2 == "disabled" {print $1}' | LC_ALL=C sort -u) \
		| grep -vxF -f <(tr ' ' '\n' <<< "$SETUP_DISABLED_UNITS") \
		| while IFS= read -r u; do
			unit_started_otherwise "$u" || echo "$u"
		done || true
}

# Whether a disabled unit still starts after a reboot, because something else
# starts it: an enabled socket, path or timer that activates it (ssh.service
# since Ubuntu 24.04, started by ssh.socket; B70), a unit name that is now
# another unit's name (an alias), or a running unit that pulls it in. Such a
# unit need not be enabled (ssh.socket starts ssh.service on the first
# connection), and the tool does not enable it.
unit_started_otherwise() {
	local u=$1 id t en
	id=$(systemctl show -p Id --value "$u" 2> /dev/null || true)
	if [ -n "$id" ] && [ "$id" != "$u" ]; then
		en=$(systemctl is-enabled "$id" 2> /dev/null || true)
		case "$en" in enabled | enabled-runtime | static | indirect | generated | alias) return 0 ;; esac
	fi
	for t in $(systemctl show -p TriggeredBy --value "$u" 2> /dev/null || true); do
		en=$(systemctl is-enabled "$t" 2> /dev/null || true)
		case "$en" in enabled | enabled-runtime | indirect | generated) return 0 ;; esac
		if systemctl is-active --quiet "$t" 2> /dev/null; then return 0; fi
	done
	for t in $(systemctl show -p WantedBy -p RequiredBy -p UpheldBy --value "$u" 2> /dev/null || true); do
		if systemctl is-active --quiet "$t" 2> /dev/null; then return 0; fi
	done
	return 1
}

# Customized files from before the upgrade that are different or gone now.
# Like etc_report in tools/migrate-to-2604.sh, for one machine.
etc_report() {
	local out=$STATE_DIR/etc-report.txt f d rel gone line units
	[ -d "$OLD_ETC" ] || return 0
	gone=$(postfix_restrictions_gone "$STATE_DIR/meta/postconf-n.txt")
	units=$(units_disabled_now)
	{
		echo "Configuration from before the upgrade that is different or gone now."
		echo "The old /etc (as of $(state_get ETC_SAVED_AT)) is in $OLD_ETC,"
		echo "what this tool moved away in $MOVED_DIR."
		echo
		echo "== Postfix restrictions from before that are gone now (redo them in main.cf)"
		if [ -n "$gone" ]; then sed 's/^/  /' <<< "$gone"; fi
		echo
		echo "== Units enabled before the upgrade that are disabled now (systemctl enable UNIT, if still wanted)"
		if [ -n "$units" ]; then sed 's/^/  /' <<< "$units"; fi
		echo
		echo "== Postfix settings (postconf -n) from before that differ now"
		if [ -s "$STATE_DIR/meta/postconf-n.txt" ]; then
			diff <(sort "$STATE_DIR/meta/postconf-n.txt") <(postconf -n 2> /dev/null | sort) | sed -n 's/^< /  /p' || true
		fi
		echo
		echo "== Files that are different now"
		for rel in postfix/main.cf postfix/master.cf opendkim.conf opendmarc.conf fail2ban/jail.local ssh/sshd_config; do
			if [ -f "$OLD_ETC/$rel" ] && [ -f "/etc/$rel" ] && ! cmp -s "$OLD_ETC/$rel" "/etc/$rel"; then
				echo "  /etc/$rel"
			fi
		done
		echo
		echo "== Files that are gone now"
		for d in postfix nginx/conf.d opendkim fail2ban cron.d cron.daily cron.hourly cron.weekly sysctl.d \
			systemd/system logrotate.d sudoers.d ssh/sshd_config.d mailinabox; do
			[ -e "$OLD_ETC/$d" ] || continue
			(cd "$OLD_ETC" && find "$d" -type f 2> /dev/null) | while read -r f; do
				[ -e "/etc/$f" ] || echo "  /etc/$f"
			done
		done
		echo
		echo "== Dovecot files from before (2.3, not taken over; Dovecot 2.4 has a new configuration)"
		if [ -d "$OLD_ETC/dovecot" ]; then
			(cd "$OLD_ETC" && find dovecot -type f ! -path 'dovecot/private/*' 2> /dev/null) | sort | while read -r f; do
				[ -e "/etc/$f" ] || echo "  /etc/$f"
			done
		fi
		echo
		echo "== Root's crontab from before"
		grep -vE '^[[:space:]]*(#|$)' "$STATE_DIR/meta/root-crontab.txt" 2> /dev/null | sed 's/^/  /' || true
	} > "$out"
	say "Configuration from before that is different or gone now: $out"
	sed -n '1,80p' "$out"
	if [ -n "$units" ]; then
		warn "Enabled before the upgrade, disabled now (they do not start after a reboot): $(tr '\n' ' ' <<< "$units")
If they are still wanted: systemctl enable UNIT (see $out)."
	fi
	# Restrictions decide which mail is accepted: a lost one is a failed check
	# (redo it, or accept with --finish), not only a line in the report.
	if [ -n "$gone" ]; then
		while IFS= read -r line; do
			warn "Postfix restriction from before is gone: $line"
			VERIFY_PROBLEMS+=("Postfix restriction from before is gone: $line (see $out)")
		done <<< "$gone"
	fi
}

# The services of Mail-in-a-Box: running, and enabled so that they start
# after a reboot. A disabled one is enabled: the in-place upgrade of rc3 left
# Dovecot disabled (B67). Keep in sync with tools/migrate-to-2604.sh.
verify_services() {
	local s st en
	for s in postfix dovecot opendkim spampd postgrey nsd nginx "php$PHP_VER-fpm" mailinabox fail2ban cron; do
		st=$(systemctl is-active "$s" 2> /dev/null || true)
		en=$(systemctl is-enabled "$s" 2> /dev/null || true)
		if [ "$en" = disabled ] && systemctl enable --quiet "$s" 2> /dev/null; then
			warn "$s was disabled, so it would not have started after a reboot. Enabled it."
			en=enabled
		fi
		printf '  %-16s %-10s %s\n' "$s" "$st" "${en:-unknown}"
		if [ "$st" != active ]; then VERIFY_PROBLEMS+=("service $s is $st"); fi
		case "$en" in
			enabled | static | indirect | generated | alias) ;;
			*) VERIFY_PROBLEMS+=("service $s is not enabled (${en:-unknown}), it would not start after a reboot") ;;
		esac
	done
}

phase_verify() {
	section "Checking the upgraded box"
	resolve_fork_dir
	VERIFY_PROBLEMS=()
	local out
	out=$(local_bash "$FINGERPRINT_SCRIPT" "SR=$STORAGE_ROOT") || true
	NEWFP=()
	load_kv NEWFP <<< "$out"
	if [ -f "$STATE_DIR/before-fingerprint.txt" ]; then
		OLDFP=()
		load_kv OLDFP < "$STATE_DIR/before-fingerprint.txt"
		compare_fingerprints
	else
		local k
		for k in "${!NEWFP[@]}"; do printf '  %-16s %s\n' "$k" "${NEWFP[$k]}"; done | sort
	fi

	say
	verify_services
	say "  Ubuntu           $(os_version)"
	if [ "$(os_version)" != 26.04 ]; then VERIFY_PROBLEMS+=("this is Ubuntu $(os_version), not 26.04"); fi

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

	if [ -d "$OLD_ETC/nsd/zones" ]; then
		local f z n=0 same=0
		for f in "$OLD_ETC"/nsd/zones/*.ds; do
			[ -f "$f" ] || continue
			# Only zones nsd actually served: a stale .ds file stays behind when
			# e.g. the box's hostname moved into its parent zone.
			z=$(basename "$f" .txt.ds)
			# The name is compared literally (a dot in a regular expression matches any character).
			if [ -f "$OLD_ETC/nsd/nsd.conf.d/zones.conf" ] \
				&& ! sed -n 's/^[[:space:]]*name:[[:space:]]*//p' "$OLD_ETC/nsd/nsd.conf.d/zones.conf" \
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
	say "Running the status checks..."
	(cd "$MIAB_DIR" && management/status_checks.py) > "$STATE_DIR/status-checks.txt" 2>&1 || true
	say "  $(grep -c '^✓' "$STATE_DIR/status-checks.txt" || true) ok, $(grep -c '^?' "$STATE_DIR/status-checks.txt" || true) warnings, $(grep -c '^✖' "$STATE_DIR/status-checks.txt" || true) errors - full report: $STATE_DIR/status-checks.txt"
	grep '^✖' "$STATE_DIR/status-checks.txt" | head -n 25 | sed 's/^/  /' || true

	say
	etc_report
	state_set VERIFY_RAN 1
	if [ ${#VERIFY_PROBLEMS[@]} -gt 0 ]; then
		print_summary
		print_result
	fi
}

# The third-party sources that were disabled and are not handled by setup.
third_party_hints() {
	local man=$APT_DISABLED/manifest orig stored list=()
	[ -f "$man" ] || return 0
	while read -r orig stored; do
		case "$orig" in
			*ondrej* | *sury* | *duplicity* | *.distUpgrade | *.save | /etc/apt/trusted.gpg.d/* | /etc/apt/keyrings/*) ;;
			*) list+=("$orig (now $stored)") ;;
		esac
	done < "$man"
	[ ${#list[@]} -gt 0 ] || return 0
	say
	say "Third-party package sources disabled for the upgrade and NOT enabled again:"
	local x
	for x in "${list[@]}"; do say "  $x"; done
	say "Add them again only for vendors that publish packages for Ubuntu 26.04 (resolute):"
	say "  webmin: curl -o webmin-setup-repo.sh https://raw.githubusercontent.com/webmin/webmin/master/webmin-setup-repo.sh && sh webmin-setup-repo.sh"
	say "  docker: https://docs.docker.com/engine/install/ubuntu/ (or Ubuntu's docker.io)"
	say "  others: change the release name in the file to resolute, put it back in"
	say "          /etc/apt/sources.list.d/ (with its key), then apt-get update."
}

phase_finish() {
	section "Finishing"
	unquiesce
	local t
	for t in apt-daily.timer apt-daily-upgrade.timer; do
		if systemctl is-enabled --quiet "$t" 2> /dev/null; then systemctl start "$t" 2> /dev/null || true; fi
	done
	if [ "$(state_get BACKUPS_PAUSED)" = 1 ]; then resume_backups; fi
	rm -f "$APT_OVERRIDE"
	remove_resume
	state_set FINISHED_AT "$(date -u +%FT%TZ)"
	state_set FINISHED_EPOCH "$(date +%s)"
	if [ -n "$(state_get HOOKS_after_AT)" ]; then
		say "The hooks in $HOOK_AFTER_DIR ran already ($(state_get HOOKS_after_AT))."
	else
		run_hooks after "$HOOK_AFTER_DIR"
	fi
	local held
	held=$(state_get HELD_PACKAGES)
	if [ -n "$held" ]; then say "These packages were held before the upgrade and are not held again: $held"; fi
	third_party_hints
}

# ---------------------------------------------------------------------------
# cleanup-old.

# REPORT (only show) or APPLY.
cleanup_old() {
	local mode=$1 f x obs=() foreign=() auto rc_pkgs=() moved=0
	section "Cleaning up the old releases$([ "$mode" = report ] && echo " (only showing what would be done)")"
	if [ "$(os_version)" != 26.04 ]; then
		say "Runs after the upgrade (this is Ubuntu $(os_version))."
		return 0
	fi
	if [ "$mode" = apply ]; then
		# Never taken away by autoremove: mark them as installed by hand.
		x=$(dpkg-query -W -f='${db:Status-Abbrev} ${binary:Package}\n' 2> /dev/null | awk '$1 ~ /^.i/ {print $2}' | grep -E "$PROTECTED_RE" || true)
		# shellcheck disable=SC2086 # a list of package names
		if [ -n "$x" ]; then apt-mark manual $x > /dev/null 2>&1 || true; fi
		apt_get autoremove --purge || warn "apt-get autoremove failed."
	else
		auto=$(apt-get -s autoremove --purge < /dev/null 2> /dev/null | sed -n 's/^Purg \([^ ]*\).*/\1/p' | grep -Ev "$PROTECTED_RE" | tr '\n' ' ' || true)
		say "apt autoremove --purge would remove: ${auto:-nothing}"
	fi

	# Not the configuration of removed servers or databases (their data may be wanted).
	mapfile -t rc_pkgs < <(dpkg-query -W -f='${db:Status-Abbrev} ${binary:Package}\n' 2> /dev/null | awk '$1 ~ /^rc/ {print $2}' \
		| grep -Ev "$PROTECTED_RE" | grep -Ev -- '-server|^postgresql-|^mysql|^mariadb' || true)
	if [ ${#rc_pkgs[@]} -gt 0 ]; then
		if [ "$mode" = apply ]; then
			say "The configuration files of these removed packages would be purged: ${rc_pkgs[*]}"
			confirm "Purge them?"
			apt_get purge "${rc_pkgs[@]}" || warn "Could not purge all of them."
		else
			say "Configuration files of removed packages would be purged: ${rc_pkgs[*]}"
		fi
	fi

	if python3 -c 'import apt_pkg' 2> /dev/null; then
		while read -r kind name ver origin; do
			case "$kind" in
				OBSOLETE) obs+=("$name $ver") ;;
				FOREIGN) foreign+=("$name $ver ($origin)") ;;
			esac
		done < <(python3 -I -c "$OBSOLETE_PY" "$FORK_ORIGINS_RE" 2> /dev/null || true)
		if [ ${#obs[@]} -gt 0 ]; then
			say "Installed packages that no package source offers any more (NOT removed; check them,"
			say "then 'apt purge NAME' what you do not need):"
			for x in "${obs[@]}"; do say "  $x"; done
		fi
		if [ ${#foreign[@]} -gt 0 ]; then
			say "Packages from other sources than Ubuntu and this fork (kept):"
			for x in "${foreign[@]}"; do say "  $x"; done
		fi
	else
		say "python3-apt is missing: the list of obsolete packages is skipped."
	fi

	for f in /etc/apt/sources.list.d/*.distUpgrade /etc/apt/sources.list.d/*.save /etc/apt/sources.list.save; do
		[ -e "$f" ] || continue
		if [ "$mode" = apply ]; then move_aside "$f"; else say "Would move away: $f"; fi
		moved=$((moved + 1))
	done
	local stem
	for f in /etc/apt/trusted.gpg.d/*; do
		[ -f "$f" ] || continue
		dpkg -S "$f" > /dev/null 2>&1 && continue
		stem=$(basename "$f")
		stem=${stem%.gpg}
		stem=${stem%.asc}
		# A source still uses it if one of the source files has a name that starts the same.
		if compgen -G "/etc/apt/sources.list.d/${stem%%-ubuntu-*}*" > /dev/null; then continue; fi
		if [ "$mode" = apply ]; then move_aside "$f"; else say "Would move away the unused key: $f"; fi
	done
	if [ -s /etc/apt/trusted.gpg ]; then
		say "Note: /etc/apt/trusted.gpg (the old apt-key keyring) still exists; APT trusts its keys for"
		say "every source. Check it with 'gpg --no-default-keyring --keyring /etc/apt/trusted.gpg --list-keys'."
	fi
	for f in /etc/php/*; do
		[ -d "$f" ] || continue
		case "${f##*/}" in "$PHP_VER" | "$PHP_LEGACY_VER") continue ;; esac
		if [ "$mode" = apply ]; then move_aside "$f"; else say "Would move away: $f"; fi
	done
	if [ -f /etc/timezone ]; then
		if [ "$mode" = apply ]; then move_aside /etc/timezone; else say "Would move away: /etc/timezone (Ubuntu 26.04 keeps the time zone in /etc/localtime only)"; fi
	fi
	# Lines in /etc/sysctl.conf that /etc/sysctl.d/60-mailinabox.conf sets as well.
	if [ -f /etc/sysctl.conf ] && [ -f /etc/sysctl.d/60-mailinabox.conf ]; then
		local keys dup
		keys=$(sed -n 's/^[[:space:]]*\([a-z0-9_.]*\)[[:space:]]*=.*/\1/p' /etc/sysctl.d/60-mailinabox.conf)
		dup=$(grep -E "^[[:space:]]*($(echo "$keys" | sed 's/\./\\./g' | paste -sd '|'))[[:space:]]*=" /etc/sysctl.conf || true)
		if [ -n "$dup" ]; then
			if [ "$mode" = apply ]; then
				mkdir -p "$MOVED_DIR/etc"
				cp -p /etc/sysctl.conf "$MOVED_DIR/etc/sysctl.conf.$(date +%s)"
				grep -vxF -- "$dup" /etc/sysctl.conf > /etc/sysctl.conf.new || true
				mv /etc/sysctl.conf.new /etc/sysctl.conf
				say "Removed from /etc/sysctl.conf (set in /etc/sysctl.d/60-mailinabox.conf): $dup"
			else
				say "Would remove from /etc/sysctl.conf (set in /etc/sysctl.d/60-mailinabox.conf): $dup"
			fi
		fi
	fi
	local oc
	oc=$(state_get OLD_MIAB_MOVED_TO)
	if [ -n "$oc" ] && [ -d "$oc" ]; then
		if [ -n "$OLD_CHECKOUT" ] && [ "$mode" = apply ]; then
			confirm "Delete the old checkout $oc?"
			rm -rf "$oc"
			say "Deleted $oc."
		else
			say "The old checkout $oc stays (--old-checkout deletes it)."
		fi
	fi
	say "Never removed, only reported: docker, webmin, snapd, mysql/mariadb clients, files of the operator."
	[ "$mode" = report ] || state_set CLEANUP_OLD_AT "$(date -u +%FT%TZ)"
}

# ---------------------------------------------------------------------------
# Commands.

phase_label() { echo "${1//_/-}"; }

resume_flags() {
	[ -z "$KEEP_LOCAL" ] || echo --keep-local
	[ -z "$NO_BACKUP_CHECK" ] || echo --no-backup-check
	[ -z "$NO_OFFSITE" ] || echo --no-offsite
	[ -z "$SKIP_MIAB_BACKUP" ] || echo --skip-miab-backup
	[ -z "$CLEANUP" ] || echo --cleanup
	[ -z "$OLD_CHECKOUT" ] || echo --old-checkout
	return 0
}

print_summary() {
	section "Summary"
	local p s e d now q f
	for p in $(phase_list); do
		s=$(state_get "START_$p")
		e=$(state_get "END_$p")
		d=
		if [ -n "$s" ] && [ -n "$e" ]; then d=" ($(fmt_dur $((e - s))))"; fi
		if phase_is_done "$p"; then say "  done     $(phase_label "$p")$d"; else say "  pending  $(phase_label "$p")"; fi
	done
	if [ -n "$(state_get CLEANUP_OLD_AT)" ]; then say "  done     cleanup-old ($(state_get CLEANUP_OLD_AT))"; fi
	q=$(state_get QUIESCED_EPOCH)
	[ -n "$q" ] || return 0
	now=$(date +%s)
	f=$(state_get FINISHED_EPOCH)
	e=$(state_get SETUP_END_EPOCH)
	say "Mail offline:    $(state_get QUIESCED_AT)$([ -n "$e" ] && echo " until the end of setup ($(fmt_dur $((e - q))))" || echo ", for $(fmt_dur $((now - q))) so far")"
	if [ -n "$f" ]; then
		say "Downtime:        $(state_get QUIESCED_AT) -> $(state_get FINISHED_AT) ($(fmt_dur $((f - q))))"
	fi
	if [ -n "$(state_get REBOOTS)" ]; then say "Reboots:         $(state_get REBOOTS)"; fi
}

# The last block of a run: the result of the checks.
print_result() {
	section "Result"
	if [ ${#VERIFY_PROBLEMS[@]} -eq 0 ]; then
		say "All checks passed. The upgrade is finished."
		say "  * Review $STATE_DIR/etc-report.txt for customizations to redo by hand."
		say "  * $STATE_DIR holds the system archive and a copy of the old /etc (with keys and"
		say "    password hashes); delete it when you no longer need it."
		if [ -n "$(state_get OFFSITE_COPY)" ]; then say "  * The encrypted archive is also in $(state_get OFFSITE_COPY)."; fi
		if [ -z "$(state_get CLEANUP_OLD_AT)" ]; then say "  * '$SELF --cleanup-only' removes what is left of the old releases ('--check --cleanup-only' shows it)."; fi
		return 0
	fi
	local p
	say "These checks FAILED:"
	for p in "${VERIFY_PROBLEMS[@]}"; do say "  - $p"; done
	# The services the before hooks stopped must not wait for --finish.
	if [ -z "$(state_get HOOKS_after_AT)" ] && [ -n "$(hook_files "$HOOK_AFTER_DIR")" ]; then
		say
		say "Mail runs again, so the hooks of stage after run now (not again in finish)."
		run_hooks after "$HOOK_AFTER_DIR"
	fi
	say
	say "Mail is running again, but cron jobs other than setup's, the update timers and the backups"
	say "stay paused until the checks pass."
	say "  check again:          $SELF"
	say "  accept the result:    $SELF --finish"
	VERIFY_FAILED=1
	if grep -qsF "$MOTD_BEGIN" "$MOTD_FILE"; then motd_hint verify-failed; fi
	exit 2
}

do_status() {
	[ -f "$STATE_FILE" ] || {
		say "No upgrade state in $STATE_DIR."
		return 0
	}
	if [ -n "$VERBOSE" ]; then
		sort "$STATE_FILE"
		return 0
	fi
	local p next='' v
	say "Mode:            $(state_get MODE) (Ubuntu $(state_get OLD_OS_VERSION) -> $(os_version) now)"
	say "Old checkout:    $(state_get OLD_MIAB_DIR) ($(state_get OLD_MIAB_VERSION))"
	v=$(state_get FORK_DIR)
	if [ -n "$v" ]; then say "Fork checkout:   $v"; fi
	v=$(state_get SYSTEM_ARCHIVE)
	if [ -n "$v" ]; then say "System archive:  $v"; fi
	v=$(state_get OFFSITE_COPY)
	if [ -n "$v" ]; then say "Offsite copy:    $v"; fi
	print_summary
	for p in $(phase_list); do
		if ! phase_is_done "$p"; then
			next=$p
			break
		fi
	done
	if [ "$(state_get BACKUPS_PAUSED)" = 1 ]; then say "Backups:         paused until the upgrade is finished"; fi
	if [ -f "$RESUME_UNIT_FILE" ]; then say "After a reboot:  $RESUME_UNIT continues (sudo tmux attach -t $TMUX_SESSION)"; fi
	if [ -n "$(state_get FINISHED_AT)" ]; then
		say "Finished:        $(state_get FINISHED_AT)"
		return 0
	fi
	if [ "$(state_get VERIFY_RAN)" = 1 ] && [ "$next" = verify ]; then
		say "Next:            the final check failed; run '$SELF' to check again or '$SELF --finish'"
	else
		say "Next:            $(phase_label "${next:-preflight}")  ('$SELF' continues)"
	fi
	if downtime_active && [ "$(state_get RELEASE_STARTED)" != 1 ]; then say "Rollback:        $SELF --rollback"; fi
}

do_rollback() {
	[ -f "$STATE_FILE" ] || die "There is no upgrade to roll back ($STATE_FILE is missing)."
	STORAGE_ROOT=$(state_get STORAGE_ROOT)
	if [ "$(state_get RELEASE_STARTED)" = 1 ]; then
		die "A release upgrade has started on this machine ($(state_get OLD_OS_VERSION) -> $(os_version) now).
There is no way back except restoring from the backups:
  * the system archive (/etc, the old checkout, Nextcloud's code, package lists):
    $(state_get SYSTEM_ARCHIVE)
    $([ -n "$(state_get OFFSITE_COPY)" ] && echo "encrypted copy: $(state_get OFFSITE_COPY)")
  * the Mail-in-a-Box backup of $STORAGE_ROOT and backup/secret_key.txt;
    restore it on a fresh Ubuntu with Mail-in-a-Box as described in
    https://mailinabox.email/maintenance.html#restore (or with tools/migrate-to-2604.sh
    --from-backup on a fresh Ubuntu 26.04).
Usually it is better to fix the cause and continue: $SELF"
	fi
	section "Rollback (before the release upgrade)"
	say "Puts back the apt sources and keys, the removed packages (PHP from ppa:ondrej), the"
	say "Prompt setting, unmasks and starts the services and resumes the backups."
	confirm "Roll back?"
	restore_apt_sources
	apt_update || warn "apt-get update failed."
	local debs=() v
	if [ -d "$PURGED_DEBS" ]; then mapfile -t debs < <(find "$PURGED_DEBS" -maxdepth 1 -name '*.deb' | sort); fi
	if [ ${#debs[@]} -gt 0 ]; then
		say "Installing the saved packages again: ${#debs[@]} .deb files"
		apt_get --allow-downgrades install "${debs[@]}" || warn "Could not install all saved packages; see above."
		# Their configuration (php.ini, pools) as it was.
		for v in $(state_get PURGED_PACKAGES | tr ' ' '\n' | sed -n 's/^php\([0-9]\.[0-9]\)-.*/\1/p' | sort -u); do
			if [ -d "$OLD_ETC/php/$v" ]; then
				mkdir -p "/etc/php/$v"
				cp -a "$OLD_ETC/php/$v/." "/etc/php/$v/"
				say "  restored /etc/php/$v from $OLD_ETC"
			fi
		done
	fi
	if [[ " $(state_get PURGED_PACKAGES) " == *" dovecot-antispam "* ]] && ! pkg_installed dovecot-antispam; then
		warn "dovecot-antispam could not be put back. Dovecot does not start while 'antispam' is in
mail_plugins (/etc/dovecot/conf.d/20-imap.conf, 20-pop3.conf): install it, or remove it there."
	fi
	local held
	held=$(state_get HELD_PACKAGES)
	# shellcheck disable=SC2086 # a list of package names
	if [ -n "$held" ]; then apt-mark hold $held > /dev/null || warn "Could not hold $held again."; fi
	v=$(state_get PROMPT_OLD)
	if [ -n "$v" ] && [ "$v" != unset ] && [ -f /etc/update-manager/release-upgrades ]; then
		sed -i "s/^[[:space:]]*Prompt[[:space:]]*=.*/Prompt=$v/" /etc/update-manager/release-upgrades
	fi
	rm -f "$APT_OVERRIDE"
	remove_resume
	unquiesce
	local start=() u
	for u in $(state_get ACTIVE_BEFORE); do start=("$u" "${start[@]}"); done
	if [ ${#start[@]} -gt 0 ]; then
		say "Starting: ${start[*]}"
		systemctl start "${start[@]}" || warn "Not all of them started; see 'systemctl --failed'."
	fi
	if [ "$(state_get BACKUPS_PAUSED)" = 1 ]; then resume_backups; fi
	run_hooks after "$HOOK_AFTER_DIR"
	local saved
	saved=$STATE_DIR/state.rolled-back-$(date -u +%Y%m%dT%H%M%SZ)
	mv "$STATE_FILE" "$saved"
	say
	say "Rolled back. Mail runs again. The old state is in $saved, the system archive and"
	say "the old /etc stay in $STATE_DIR. A new attempt starts from the beginning."
}

do_finish() {
	[ "$(state_get VERIFY_RAN)" = 1 ] || die "Run the upgrade up to the final check first."
	if phase_is_done finish; then
		say "The upgrade is already finished ($(state_get FINISHED_AT))."
		return 0
	fi
	STORAGE_ROOT=$(state_get STORAGE_ROOT)
	confirm "Accept the result of the last check and finish the upgrade (backups resume)?"
	state_set END_verify "$(date +%s)"
	phase_mark_done verify
	state_set START_finish "$(date +%s)"
	phase_finish
	state_set END_finish "$(date +%s)"
	phase_mark_done finish
	print_summary
	say "The upgrade is marked as finished."
}

upgrade_steps_text() {
	case "${F[OS_VERSION]}" in
		22.04) echo "release upgrades to 24.04 and 26.04 and two reboots in between" ;;
		24.04) echo "a release upgrade to 26.04 and a reboot in between" ;;
		*) echo "no release upgrade" ;;
	esac
}

do_upgrade() {
	local p n
	read_facts
	[ "${F[HAS_CONF]:-0}" = 1 ] || die "/etc/mailinabox.conf is missing. Is this a Mail-in-a-Box?"
	STORAGE_ROOT=${F[CONF_STORAGE_ROOT]:-$(state_get STORAGE_ROOT)}
	[[ $STORAGE_ROOT == /* && $STORAGE_ROOT != / ]] || die "Unexpected STORAGE_ROOT '$STORAGE_ROOT'."

	if [ -n "$RESUMED" ]; then
		n=$(($(state_get RESUME_COUNT || true) + 1))
		state_set RESUME_COUNT "$n"
		[ "$n" -le "$RESUME_MAX" ] || die "The upgrade was continued automatically $RESUME_MAX times already. Not again:
look at $LOG_FILE, fix the cause and run $SELF by hand."
	else
		state_set RESUME_COUNT 0
		state_set RESUME_FLAGS "$(resume_flags | tr '\n' ' ' | sed 's/ $//')"
	fi

	if [ -n "$REDO_FROM" ]; then
		case "$REDO_FROM" in
			snapshot)
				[ "$(state_get QUIESCED)" != 1 ] || die "--redo-from snapshot only works before mail was stopped (phase quiesce)."
				[ "$(state_get RELEASE_STARTED)" != 1 ] || die "--redo-from snapshot only works before the first release upgrade."
				phases_reset_from snapshot
				;;
			cleanup-etc | setup | local-ext | verify)
				phase_is_done release_2604 || [ "$(state_get MODE)" = rerun ] \
					|| die "--redo-from $REDO_FROM only works after the release upgrades."
				phases_reset_from "${REDO_FROM//-/_}"
				state_set FINISHED_AT ""
				;;
			*) die "--redo-from takes snapshot, cleanup-etc, setup, local-ext or verify." ;;
		esac
	fi

	if phase_is_done finish && [ -z "$REDO_FROM" ]; then
		say "This upgrade is finished ($(state_get FINISHED_AT)). '--redo-from verify' checks again,"
		say "'--status' shows the state."
		if [ -n "$CLEANUP" ] && [ -z "$RESUMED" ] && [ -z "$(state_get CLEANUP_OLD_AT)" ]; then cleanup_old apply; fi
		return 0
	fi

	pending_reboot
	requiesce

	if ! phase_is_done quiesce; then
		# Nothing is stopped yet: check (again) before the downtime.
		state_set PHASE_preflight ""
		state_set START_preflight "$(date +%s)"
		phase_preflight
		blockers_or_die
		state_set END_preflight "$(date +%s)"
		phase_mark_done preflight
		show_plan
		[ -n "$RESUMED" ] || session_check
		if [ "$(state_get MODE)" = rerun ]; then
			phase_is_done setup || confirm "Run setup again now?"
		elif [ "$(state_get QUIESCED)" = 1 ]; then
			confirm "Mail is OFFLINE since $(state_get QUIESCED_AT). Continue the upgrade ($(upgrade_steps_text))?
Mail stays offline until setup has finished. Nothing asks again. If SSH does not come
back after a reboot, use the provider's console."
		elif ! phase_is_done snapshot && fresh_backup_planned; then
			confirm "Start the upgrade now? The system archive is written first; then mail goes OFFLINE,
before the fresh backup (so that it holds all mail), and stays offline until setup has
finished, with $(upgrade_steps_text). From the first release upgrade on there is no way
back except the backups. Nothing asks again. If SSH does not come back after a reboot,
use the provider's console."
		elif ! phase_is_done snapshot; then
			confirm "Start the upgrade now? The snapshot runs first (mail keeps running), then mail goes
OFFLINE until setup has finished, with $(upgrade_steps_text). From the first
release upgrade on there is no way back except the backups. Nothing asks again.
If SSH does not come back after a reboot, use the provider's console."
		else
			confirm "Stop mail now and continue the upgrade ($(upgrade_steps_text))? Mail stays OFFLINE
until setup has finished. Nothing asks again. If SSH does not come back after a reboot,
use the provider's console."
		fi
	elif [ -z "$RESUMED" ]; then
		session_check
	fi

	for p in $(phase_list); do
		phase_is_done "$p" && continue
		[ -n "$(state_get "START_$p")" ] || state_set "START_$p" "$(date +%s)"
		"phase_$p"
		state_set "END_$p" "$(date +%s)"
		phase_mark_done "$p"
	done
	print_summary
	print_result
	if [ -n "$CLEANUP" ] && [ -n "$RESUMED" ]; then
		say "Not cleaning up unattended (--cleanup after a reboot). Run: $SELF --cleanup-only"
	elif [ -n "$CLEANUP" ]; then
		cleanup_old apply
	fi
}

do_check() {
	if [ "$COMMAND" = cleanup_only ]; then
		cleanup_old report
		exit 0
	fi
	if downtime_active; then
		say "An upgrade is in progress (mail offline since $(state_get QUIESCED_AT)); --check only reports."
		do_status
		exit 0
	fi
	phase_preflight
	show_plan
	if [ -n "$CLEANUP" ]; then cleanup_old report; fi
	check_summary
}

main() {
	ASSUME_YES='' REDO_FROM='' COMMAND=upgrade VERBOSE='' KEEP_LOCAL='' NO_BACKUP_CHECK=''
	NO_OFFSITE='' SKIP_MIAB_BACKUP='' CLEANUP='' OLD_CHECKOUT='' RESUMED='' NO_TMUX=''
	local orig_args=("$@")

	while [ $# -gt 0 ]; do
		case "$1" in
			--redo-from)
				if [ $# -lt 2 ] || [ -z "$2" ]; then die "$1 needs a value. See --help."; fi
				REDO_FROM=$2
				shift 2
				;;
			--keep-local) KEEP_LOCAL=1; shift ;;
			--no-backup-check) NO_BACKUP_CHECK=1; shift ;;
			--no-offsite) NO_OFFSITE=1; shift ;;
			--skip-miab-backup) SKIP_MIAB_BACKUP=1; shift ;;
			--cleanup) CLEANUP=1; shift ;;
			--old-checkout) OLD_CHECKOUT=1; shift ;;
			--yes | -y) ASSUME_YES=1; shift ;;
			--no-tmux) NO_TMUX=1; shift ;;
			--check | --dry-run) CHECK_ONLY=1; shift ;;
			--verbose) VERBOSE=1; shift ;;
			--cleanup-only) COMMAND=cleanup_only; shift ;;
			--rollback) COMMAND=rollback; shift ;;
			--status) COMMAND=status; shift ;;
			--finish) COMMAND=finish; shift ;;
			# Internal: set by the resume unit after a reboot.
			--resumed) RESUMED=1 ASSUME_YES=1; shift ;;
			-h | --help) usage; exit 0 ;;
			*) die "Unknown option $1. See --help." ;;
		esac
	done

	[ "$(id -u)" = 0 ] || die "This must be run as root. Did you leave out sudo?"
	# Absolute path of this script, before leaving the working directory.
	if [[ ${BASH_SOURCE[0]:-} == *.sh ]] && [ -f "${BASH_SOURCE[0]}" ]; then
		SELF_FILE=$(readlink -f "${BASH_SOURCE[0]}")
	fi
	cd /
	trap 'on_err "$LINENO" "$BASH_COMMAND"' ERR
	trap on_exit EXIT

	if [ "$COMMAND" = status ]; then
		do_status
		return 0
	fi

	if [ -n "$CHECK_ONLY" ]; then
		case "$COMMAND" in upgrade | cleanup_only) ;; *) die "--check only works for the upgrade and --cleanup-only." ;; esac
		local d
		if d=$(checkout_dir); then check_checkout_owner "$d"; fi
		do_check
		return 0
	fi

	(umask 077 && mkdir -p "$STATE_DIR")
	chmod 700 "$STATE_DIR"
	if [ -z "$SELF_FILE" ]; then
		reexec_from_clone "$SCRIPT_NAME" "$STATE_DIR/fork" "${orig_args[@]}"
	fi
	# From the real file (after the clone), before the lock: the run in the
	# session takes it. If another run holds it, take_lock says where it is.
	if [ -z "$(active_run_pid)" ]; then run_in_multiplexer "${orig_args[@]}"; fi
	take_lock
	exec > >(tee -a "$LOG_FILE") 2>&1
	LOG_READY=1
	echo
	echo "=== $SCRIPT_NAME $(date -u +%FT%TZ) ${orig_args[*]}"
	install_self
	# Asked now, not when setup runs from it (mail offline, nobody watching).
	local d
	if [ -z "$RESUMED" ] && d=$(checkout_dir) && is_fork_dir "$d"; then check_checkout_owner "$d"; fi

	case "$COMMAND" in
		rollback) do_rollback ;;
		finish) do_finish ;;
		cleanup_only)
			[ -z "$(state_get MODE)" ] || phase_is_done finish || die "Finish the upgrade first (--status)."
			STORAGE_ROOT=$(state_get STORAGE_ROOT)
			cleanup_old apply
			;;
		upgrade) do_upgrade ;;
	esac
}

main "$@"
