# rc7 fragment: tools

Entries for CHANGELOG-fork.md ("## Unreleased") and BUGS-fork.md, to be
merged when rc7 is released. Bug IDs of this fragment: B90 (B91 to B94 not
used).

## CHANGELOG-fork.md

### New

* Tools: `tools/update-check.sh`, the checks around an update of a box of
  this fork, as root (also through `curl ... | sudo bash -s -- STEP`):
  * `before` records the state of the box in
    `/root/update-check/<stamp>/before/` (mode 0700): version and origin of
    `/root/mailinabox`, the units (enabled, active) and the failed ones, the
    mail queue, the error and warning lines of the status checks, the
    warnings of doveconf and postconf, key settings of Postfix and Dovecot
    (e.g. `smtpd_recipient_restrictions`, `log_path`), the Nextcloud status,
    Munin's alert contact and the values that are not ok, Docker containers,
    crontabs, mailname and hosts, fail2ban jails, systemd drop-ins, the
    listening ports, `/etc/mailinabox.conf` and the package versions of the
    mail services. It also runs `tests/fork/log-audit.sh` over the last 24
    hours (`--since`) as the baseline.
  * `backup` runs `management/backup.py` (as the nightly backup; mail stops
    for its run) and writes an archive of `/etc`, `/root/mailinabox`, the
    crontabs, `/var/lib/z-push`, `/var/lib/munin`, `/usr/local/lib/owncloud`
    and the Docker stack directories and volumes named with `--docker-dir`
    and `--docker-volume`, and a pg_dump of each container named with
    `--postgres` (with its `POSTGRES_USER` and `POSTGRES_DB`). Everything is
    encrypted with gpg (AES256, the passphrase of the Mail-in-a-Box backups)
    as it is written, nothing goes to disk unencrypted. For an rsync target
    the files are copied next to the backups
    (`<path>-system/update-check-<stamp>/`, with the backup SSH key) and
    compared by checksum (rsync -c, dry run); otherwise they stay in the
    stamp directory. The backup target is read as Mail-in-a-Box reads it,
    quoted or not.
  * `after` records the state again and compares it with `before`: each
    change is EXPECTED, if the releases between the two versions announce
    it (`tools/expected-changes/<version>.txt` and `any.txt`, one rule per
    line: file, + or -, regex, reason), or UNEXPECTED. The list for rc7
    covers the updates from rc1 to rc6 as well: the quota check in front of
    greylisting in `smtpd_recipient_restrictions` (rc4), `log_path=syslog`
    of Dovecot (rc6, B85), Munin's contact (rc6, B80), the drop-ins of
    Postfix and spampd (rc6, B78 and B81), the new keys of
    `/etc/mailinabox.conf`. Then it runs the log audit since `before`
    against the baseline. Exit code 1 for an unexpected change or a new
    message class.
  * `mailcheck` sends a marked mail (`X-Miab-Test: 1`, a unique token) from
    administrator@PRIMARY_HOSTNAME (`--from`) to an external probe address
    (`--probe` or `PROBE_ADDRESS=` in `/etc/mailinabox.conf`) that forwards
    or answers it, waits (`--timeout`, default 900 s) until a mail with the
    token comes back over port 25 and is stored, and reports the outbound
    delivery (relay, DKIM signature), the inbound delivery (port 25, the
    Authentication-Results), the spam filter (X-Spam-Status), the folder
    (Sieve) and the storage. Without a probe address it says "skipped". The
    mail carries no secrets.
  README-fork.md ("Updating the fork") describes it.
* Tools: during each release upgrade, `tools/upgrade-in-place-to-2604.sh`
  runs a fallback SSH server on port 1022 (`UPGRADE_SSH_FALLBACK_PORT=PORT`,
  or `off`). Cause of the SSH outage: the maintainer scripts of
  openssh-server stop `ssh.socket` and `ssh.service` when the new package
  is unpacked and start them again only when it is configured, near the end
  of the dpkg run; nothing listens on port 22 in between. The fallback runs
  from a private copy of the old sshd (and of sshd-session and sshd-auth
  where they exist), so the package cannot replace it underneath. It
  accepts only public keys, only of the administrators (members of the
  groups sudo and admin, and root if `PermitRootLogin` allows keys;
  `UPGRADE_SSH_FALLBACK_USERS` names others), whose keys it copies (read as
  the user) into a root-owned directory, keeps the AllowUsers, AllowGroups,
  DenyUsers, DenyGroups and the algorithms of the running sshd, and allows no
  forwarding. ufw lets the port through (rate limited) only while it runs.
  It is stopped, and the port closed, when port 22 answers again after the
  release upgrade and on every way out of the tool (also after Ctrl-C);
  while port 22 does not answer it stays until the next reboot, and the next
  run removes it and its ufw rule. `--ssh-fallback-test` starts it for 10
  minutes before an upgrade, to try a login on its port.
* Tools: `tools/upgrade-in-place-to-2604.sh` says in the run when the release
  upgrade has stopped the SSH server on port 22 and when port 22 answers
  again (its SSH banner), with the minutes in between.
* Tests: `tests/fork/log-audit.sh --baseline BEFORE.json` compares with the
  `--json` report of an earlier run: a class that was in it is listed as
  KNOWN, with both counts, and does not count; only new classes are
  UNKNOWN. `--internet` adds `tests/fork/log-audit-allow-internet.txt`, the
  usual noise of a box on the Internet (ufw blocks, SYN floods, password
  guessing on SSH, SMTP submission, Roundcube, Nextcloud and Z-Push, TLS and
  SSH errors of scanners and old clients, nginx 404s in the web roots, mail
  that Postfix rejects as spam, to unknown recipients or for relaying,
  greylisting, reverse DNS warnings, DNS and DNSSEC errors of other zones),
  each rule with its reason; only when asked, the test scenarios do not use
  it.

### Changed

* Tests: `tests/fork/log-audit.sh --since` also takes the short forms `-90s`,
  `-30m`, `-24h`, `-2d` and `-1w`; `date -d` fails on them ("-24h" reads the
  "h" as a time zone).
* Tools: the messages before a release upgrade (and in the motd) name the
  fallback SSH server and how to reach it. The help of
  `tools/upgrade-in-place-to-2604.sh` describes it.

### Fixed

* Tools: for backups on the machine itself (local, or a `file://` target
  below a directory that another account may change),
  `tools/upgrade-in-place-to-2604.sh` no longer copies the encrypted system
  archive as root into `$STORAGE_ROOT/backup/encrypted-system/`: that path
  runs through `$STORAGE_ROOT`, which belongs to the user-data account, so a
  symlink there could have redirected root's mkdir and copy. The archive
  stays in `/root/upgrade-2604`, as the tool already said to copy it off the
  machine. A `file://` target whose path only root can change gets the copy
  as before (B90).

### Upgrade note

* The fallback SSH server of the in-place tool listens on port 1022 during
  each release upgrade. If a firewall of the provider must let it through,
  open it there before the upgrade and try it with
  `sudo /root/mailinabox/tools/upgrade-in-place-to-2604.sh --ssh-fallback-test`.
  `UPGRADE_SSH_FALLBACK_PORT=off` turns it off.

## BUGS-fork.md

Legend (Found by), new entry:

  * *rc7 review*: the review of the tools for rc7 against the rule that root does no file operations by path in directories that another account may write.

Overview row:

| [B90](#b90) | low | Tools | The in-place tool copies the encrypted system archive as root through the user-data account's directory | Fork | no | no | rc7 |

### B90

**The in-place tool copies the encrypted system archive as root through the user-data account's directory** (low, Tools)

* **Symptom:** For backups on the machine itself (target `local`, or a `file://` target), phase snapshot of `tools/upgrade-in-place-to-2604.sh` ran `mkdir -p` and `cp` as root on `$STORAGE_ROOT/backup/encrypted-system/<stamp>/` (or `<target>-system/<stamp>/`). Nothing went wrong in the test runs.
* **Cause:** `$STORAGE_ROOT` (`/home/user-data`) belongs to the user-data account (mode 0755). That account may rename `backup` and put a symlink in its place; root's `mkdir -p` and `cp` then follow it and create directories and the archive files wherever the symlink points. The same for a `file://` target below a directory that another account may write.
* **Impact:** Low: it needs code running as user-data (the account of `$STORAGE_ROOT`, which runs the backup hooks), at the moment of the snapshot, and the content of the files is fixed (the encrypted archive and its checksum). Against the rule of the fork that root does no file operations by path in directories that another account may write.
* **Fix:** `offsite_copy` copies to a local or `file://` target only when the target's directory and all directories above it are root's own (not symlinks, owned by root, not writable by group or others; `root_only_path`). Otherwise the encrypted archive stays in `/root/upgrade-2604` (mode 0700), and the tool says so; it already advised to copy a copy on the machine off it. `tools/update-check.sh backup` keeps its archive in `/root/update-check/<stamp>/` for such targets from the start.
* **Affects:** the fork rc1 to rc6. Origin: Fork.
* **Evidence:** From reading the code; `root_only_path` checked on the box replica of the update test (rc6 after T5b): `/home/user-data/backup/encrypted`, `/home/user-data/backup`, `/tmp/x` and `/var/log` are not root-only, `/root/upgrade-2604/x/y`, `/etc/ssh` and `/mnt/nonexistent/a` are.
* **Found by:** rc7 review; **commit:** see `git log --grep B90`; **fixed in:** v78-r2604.0-rc7
