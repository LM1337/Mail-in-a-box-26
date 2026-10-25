# Testing of the Ubuntu 26.04 fork

This file lists the end-to-end tests that were run for each release of the
fork: what was tested, how, and with what result. It is meant to help you
judge how mature a release is. Changes are in [CHANGELOG-fork.md](CHANGELOG-fork.md),
fixed bugs in [BUGS-fork.md](BUGS-fork.md).

The fork is a release candidate. The tests below are a small, fixed set of
scenarios on test machines, not a test of every setup that exists. Make a
backup and try a release on a copy before you run it on the box that holds
your mail.

## Test environment

* **Virtual machines** on a private network behind NAT, with IPv4 and IPv6.
  The tests reach them through a jump host.
* **Real Ubuntu cloud images** (22.04 and 26.04, checksums verified), with
  cloud-init.
* **No access to production.** `tests/fork/prepare-testenv.sh` blocks the
  production mail servers outbound in ufw on every test box. It stops if ufw
  is not active.
* **Test boxes:**
  * *the 22.04 test VM*: Ubuntu 22.04 with upstream Mail-in-a-Box v74
    (Nextcloud 26.0.13, Dovecot 2.3), filled with test data by
    `tests/fork/seed-legacy.sh` (see below), kept as a snapshot.
  * *the 26.04 test VM*: a fresh Ubuntu 26.04, kept as a snapshot.
  * *the 24.04 test VM*: a copy of the 22.04 test VM that was given the
    configuration of a real production box and then release-upgraded to
    24.04 like it: Mail-in-a-Box v74, PHP 8.0 from ppa:ondrej, Dovecot 2.3
    with fts_xapian and a custom Dovecot plugin that sends push calls to a
    local web service (a Docker stand-in), a greylisting exception added by
    hand, the old apt sources.
* **A second Mail-in-a-Box as peer.** Port-25 mail and the fail2ban attacks
  come from another test box, so the box under test sees a real foreign MTA.
* **Every run starts from a snapshot** and fetches the tools from the release
  tag (or the release branch, see the notes). Nobody touches the box during
  the run. Most runs start the tool with curl as documented; rc3 T4
  downloaded it from the tag and started it in a tmux session of its own,
  and the runs on a release branch set `SOURCE`/`TAG`. rc5 T4 is the run
  that uses exactly the documented command against the published tag. All
  rc6 runs used the documented commands with `SOURCE`/`TAG` set to the
  release branch.
* **The smoke test measures the box, not itself:** against the unchanged
  22.04 test VM (v74) it passes in full (baseline run with the smoke test of
  rc1/rc2; not repeated with the larger smoke test of rc4/rc5).

The test data (`seed-legacy.sh`): three mail domains, one of them a domain
alias; three users (alice, bob with a 10 MB quota, carol); an alias, a
catch-all and a permitted sender; a Sieve filter and a vacation reply; about
20 mails over port 25 and IMAP APPEND into INBOX, Spam and Archive, with spam and ham training; a Nextcloud
event, contact and file; a custom DNS record; a Roundcube identity with
signature; a local backup. It writes a manifest (POP3 UIDLs, folder counts,
Bayes counts, Sieve scripts, DKIM key, Nextcloud items) that the smoke test
compares against after a migration or upgrade.

## Scenarios

| ID | Start state | Path | Tool / command | Smoke mode |
|---|---|---|---|---|
| T1 | fresh Ubuntu 26.04 | fresh install | `setup/bootstrap.sh` through curl, non-interactive (`NONINTERACTIVE=1`) | fresh, with `--provision` |
| T2 | the 22.04 test VM (v74 with test data) and a fresh 26.04 machine | migration to the new machine | `curl …/tools/migrate-to-2604.sh \| sudo bash -s -- --from <old box>`, on the new machine | migrated |
| T3 | the 24.04 test VM (copy of a production box) | in place, 24.04 → 26.04, one release upgrade | `curl …/tools/upgrade-in-place-to-2604.sh \| sudo bash -s -- --keep-local --yes` | migrated |
| T4 | the 22.04 test VM | in place, 22.04 → 24.04 → 26.04, two release upgrades | `curl …/tools/upgrade-in-place-to-2604.sh \| sudo bash -s -- --yes` | migrated |
| T5 | the 24.04 test VM after an in-place upgrade with rc3 | update of a box that already runs the fork | `git remote set-url` to GitHub, then `sudo bash -c "$(curl -fsSL …/setup/bootstrap.sh)"`; the setup dialogs answered with Enter | migrated |

Variants: **T3b** is a clean T3 run from the tag after a first run had found
bugs. **T3c** and **T4b** repeat T3 and T4 with the automatic tmux of rc4;
the SSH client is killed in the middle of the run, and the upgrade must go
on. T3c also runs the before/after hooks for the local web service. **T5b**
updates rc3 to the release under test (from rc5). Most in-place runs in the lab use `--no-backup-check`
(the test VMs have no fresh backup) and run `prepare-testenv.sh` before the
smoke test.

### What the smoke test checks

`tests/fork/smoke.py` prints PASS, FAIL or SKIP per check and writes a JSON
report. The groups:

* **login**: IMAPS 993, POP3S 995, submission 465 and 587, ManageSieve 4190;
  the logins show up in the mail log report (`mail_log.py`, from rc4); the core services
  are enabled, so they start after a reboot (`services-enabled`, from rc5).
* **migrated** (migration and in-place only): users and aliases; per user the
  POP3 UIDLs and the folders with their message counts; active Sieve scripts;
  Bayes counts; Nextcloud event, contact and file; the custom DNS record; the
  DKIM key; the Roundcube identity. All compared with the manifest. From
  rc6 the mailbox comparison ignores test mails (header `X-Miab-Test: 1`)
  and the automatic replies and bounces to them, and reports how many it
  ignored; any other missing or new mail, and a seeded mail that is there
  twice, is a FAIL.
* **admin**: admin API login, creating and deleting a user and an alias,
  backup status; from rc4 the fail2ban API, settings, report, filters (with
  injected user names) and the Intrusion Protection page.
* **api** (from rc7): the management API as `api/mailinabox.yml` documents
  it. Auth: 401 without credentials (text or JSON by `Accept`, 403 for an
  XMLHttpRequest) and with a wrong password, the API key works, a second
  session's key until its logout and 401 after it; two failed logins in
  all, far below the `miab-management` jail. Every documented read-only
  endpoint (`API_READ_ONLY` in `smoke.py`, with the read-only POSTs
  `system/status`, `system/latest-upstream-version`, `ssl/csr` and
  `mfa/status`) answers 200 with the documented content type and shape. A
  write round trip with marked test data (`smokeapi-<token>`): user,
  password, quota, admin privilege on and off, alias, a custom TXT record
  with POST, PUT and DELETE, privacy set to its own value, the user removed
  and (with `--ssh`) its archived mailbox too; the lists of users, aliases
  and custom records are the same afterwards. Munin's alert
  setting: invalid addresses refused, `munin.conf` for each mode (with
  `--ssh`), the test mail to alice's INBOX (deleted again), the old setting
  and `munin.conf` restored exactly. Not called (`API_NOT_CALLED`, with the
  reasons): reboot, package updates, SSL provisioning and install, web
  update, backup config writes, MFA enable and disable, DNS update,
  secondary nameserver, the fail2ban writes (group admin, group fail2ban).
  `tests/fork/api-routes.py` (no box needed) checks that every route of
  `management/daemon.py` is documented and every documented operation has a
  route, that `smoke.py` calls or excludes each of them, and the content
  types it expects.
* **dns**: DNSSEC (RRSIG, DNSKEY), MX and DKIM for each zone, SSHFP against the
  host keys sshd serves, custom records.
* **web**: Nextcloud version, CalDAV, CardDAV and WebDAV with the mail
  password; Nextcloud sharing within the mail domain (from rc4); Roundcube
  login; Z-Push OPTIONS and Autodiscover.
* **mail**: delivery over port 25 from the peer to a mailbox, an alias, a
  catch-all and a domain alias; no quota rejection for aliases; a 12 MB mail
  to the 10 MB mailbox rejected at RCPT; GETQUOTAROOT; the greylisting
  exception file and its place in the Postfix restrictions and mail to root
  (both from rc4);
  Sieve filter and vacation reply, and no phantom folders after it (from
  rc5); delivery after submission on 465 and 587; permitted sender allowed,
  foreign sender refused.
* **imapsieve**: moving a mail into Spam and out of it trains SpamAssassin;
  full-text search (IMAP SEARCH BODY and `doveadm fts lookup`, from rc3).
* **fail2ban** (opt-in, `--fail2ban`): failed logins from the peer get it
  banned on IMAP, POP3, ManageSieve, 587 and 465, then it is unbanned; from
  rc4 also turning adaptive banning off reaches the running jails. From rc6
  the group first rotates `mail.log` once (`logrotate -f` of the rsyslog
  entry, `fail2ban-log-rotation`) and checks that rsyslog writes the new
  file and that no Dovecot process holds a file in `/var/log` (Dovecot logs
  through syslog; on a box where Dovecot still writes `mail.log` itself, up
  to rc5, it must hold the new file); the attacks then run against the
  rotated log, so a jail that a rotation made blind fails (B85). Use a lab address of the peer
  (`--peer-ssh`), never the jump host.

The number of checks grew from release to release (49 in the first runs, 73
in the rc5 in-place runs, 75 in the final rc6 update runs with
`munin-alert-contact` and `fail2ban-log-rotation`), and it depends on the
mode and on `--fail2ban`.
The counts below are not comparable between releases.

Checked by hand in the in-place and update runs, not by the smoke test:
Dovecot push calls reach the local web service, the hooks run in order, the
greylisting exception is kept, `/etc/mailname` and the root alias, the
errors of the status checks all come from the test network, and (from rc5) all services are enabled and
active after one more reboot.

## Results

Counts are smoke-test PASS/total. Downtime is the time mail was offline, as
the in-place tool reports it.

| Release | Date | T1 fresh | T2 migration | T3 in place from 24.04 | T4 in place from 22.04 | T5 update of the fork |
|---|---|---|---|---|---|---|
| rc1 | 2026-10-23 | 49/49 | 54/54 | not run | not run | – |
| rc2 | 2026-10-23 | 49/49 | 54/54 | not run | not run | – |
| rc3 | 2026-10-23 | not run | not run | 53/55 (T3b) | 55/55 | – |
| rc4 | 2026-10-24 | 60/60 | not run | 56/58 (T3c, pre-merge branch) | 58/58 (T4b, pre-merge branch) | 68/71, from the published tag 69/71 |
| rc5 | 2026-10-24 | 62/62 | not run | 67/73 | 67/73 (from the published tag) | 67/73 (T5b, from rc3) |
| rc6 | 2026-10-25 | 62/62 ¹ | 73/73 ¹ | 73/73 ¹ | 73/73 ¹ | 75/75 (T5b, from rc3, at `5d2d3aa`, the code of the release ²) |

¹ Certification run at `33f056b`, before the last fixes of rc6 (B80-B85);
not repeated on the code of the release (see "rc6 certification" below).
The earlier rc6 development runs had the same counts (T3 and T5b after a
first run of 71/73).

² The commits after `5d2d3aa` change only the log audit tool, its
allowlist and the documentation.

Every FAIL in this table is one of the known differences below, except one
Nextcloud lock in rc4 T5 (see there) and the first runs of rc6 T3 and T5b,
where the stricter comparison of rc6 found mails left in the snapshot (see
there).

### rc1 and rc2 (2026-10-23)

| Run | Result |
|---|---|
| T1 (rc1) | smoke 49/49 |
| T2 (rc1) | the tool reports "All checks passed"; smoke 54/54 |
| T1 (rc2) | smoke 49/49, including fail2ban on 5 protocols |
| T2 (rc2) | "All checks passed"; smoke 54/54. Nextcloud went 26.0.13 → 34.0.5. Mailboxes, Sieve, Bayes, DKIM and DNSSEC, Nextcloud data and the Roundcube identity were taken over |

Both releases were run from the tag, without manual steps.

### rc3 (2026-10-23)

| Run | Result |
|---|---|
| T3b (24.04 → 26.04, from the tag) | "All checks passed" with no manual step; smoke 53/55 (2 known differences); mail offline 52 min, 1 reboot (release upgrade 34 min, setup 16 min). Nextcloud 26 → 34.0.5, full-text search works with the old indexes, push works after the upgrade |
| T4 (22.04 → 24.04 → 26.04) | "All checks passed" with no manual step; smoke 55/55; mail offline 1 h 21 min, 2 reboots (release upgrades 33 and 29 min, setup 16 min) |

The first T3 run found B51-B56, fixed in rc3 before T3b.

### rc4 (2026-10-24)

| Run | Result |
|---|---|
| T4b (22.04, automatic tmux, SSH dropped) | tmux installed and started by the tool; the run went on after the SSH client was killed; "All checks passed"; smoke 58/58; mail offline 1 h 22 min, 2 reboots |
| T3c (24.04 copy, automatic tmux, hooks) | "All checks passed"; smoke 56/58 (2 known differences); mail offline 50 min, 1 reboot. The before hook ran before mail went offline, the after hook at the end; the greylisting exception was kept; push reached the web service |
| T1 | smoke 60/60 on the final release branch. The first run (57/60) found bugs that were fixed before the final run (B63-B65 come from the rc4 test runs) |
| T5 (rc3 → rc4) | start state: the 24.04 copy upgraded in place with rc3 ("All checks passed", mail offline 1 h 02 min, 1 reboot). Update: setup exit 0 in 142 s. Smoke 68/71 (2 known differences, 1 Nextcloud "database is locked" during its own cron job; the smoke test now retries that call, three reruns passed) |
| T5 from GitHub (rc3 → published rc4 tag) | the two documented commands; setup exit 0 in 136 s; smoke 69/71 (2 known differences); no new status-check errors. A probe every 2 s saw no outage, but one mail was deferred for about 5 minutes while setup restarted Dovecot. This run found B66-B69, fixed in rc5 |

T3c and T4b ran on the branch with the tmux feature before it was merged
into rc4. T1 and T5 ran on the release branch; the GitHub run on the
published tag.

### rc5 (2026-10-24)

| Run | Result |
|---|---|
| T5b (rc3 → rc5) | start state: the rc3 box with Dovecot disabled (B67) and the phantom folders of a vacation reply (B66). Setup exit 0 in 143 s; Dovecot and all core units enabled again, the phantom folders removed, `/etc/hosts` and the cloud-init template correct. Reboot: all units active. Smoke 67/73 (6 known differences) |
| T3 (24.04 copy) | "All checks passed"; mail offline 1 h 01 min, 1 reboot (release upgrade 41 min, setup 16 min). The tool enabled Dovecot again after the upgrade. Reboot: all units active. Smoke 67/73 (6 known differences). The run found a false warning about spamd in phase verify, fixed in rc5 and checked again with `--redo-from verify` |
| T1 | install 1671 s, exit 0; reboot: all units enabled and active; smoke 62/62 |
| T4 (22.04 → 24.04 → 26.04, from the published tag) | start state: the 22.04 test VM (Ubuntu 22.04.5, v74, Dovecot 2.3.16, PHP 8.0, Nextcloud 26.0.13), with a vacation reply sent before the upgrade. The published tool, started with `curl … \| sudo bash -s -- --yes --no-backup-check`, fetched the tag, started itself in tmux and ran through both release upgrades and both reboots with no manual step: "All checks passed". Mail offline 1 h 25 min, 2 reboots (release upgrades 34 and 31 min, setup 16 min; whole run 1 h 25 min). Ubuntu 26.04.1, Dovecot 2.4.2, Postfix 3.10.6, PHP 8.5, Nextcloud 34.0.5; `doveconf -n`, `postconf -n` and `postfix check` without warnings; the tool enabled postgrey and Dovecot again after the upgrade; `/etc/hosts` and the cloud-init template correct; status checks: 17 errors, all from the test network, the same after the reboot (no status checks were taken before this run). The vacation duplicate database of Dovecot 2.3 kept working (a sender who had a reply before the upgrade got none after it), and no phantom folders appeared. Reboot: SSH back after 21 s, no failed units, all mail ports listening; IMAP login, submission and port 25 from the peer worked; outgoing mail to the peer worked with a temporary transport override, because the test network's DNS does not route to the peer. Smoke 67/73 (6 known differences). Findings: see below |

T1, T3 and T5b used the release branch and ran one commit before the tagged
code. That commit is the spamd fix in phase verify of the in-place tool: T1
and T5b do not use that tool, and T3's phase verify was run again with the
fix (`--redo-from verify`). The release commit changes only the release tag
in the scripts and the documentation. T4 ran the published tool from GitHub,
which checked out the tag `v78-r2604.0-rc5` itself.

#### Findings of rc5 T4

The T4 run passed, but it showed things an operator upgrading from 22.04
will run into. rc6 fixes 1 (B70), 4 (B71) and 5 (B72); for 2 and 3 the tool
now says before each release upgrade what to expect, and README-fork.md
describes it. 6 is not changed. rc6 T4 checked all of it again (see rc6
below), and 6 did not show there.

1. **False warning about `ssh.service`** (fixed in rc6, B70). Phase verify
   prints "Enabled before the upgrade, disabled now (they do not start after
   a reboot): ssh.service", and `etc-report.txt` advises `systemctl enable`
   for it. Since 24.04, SSH is started by `ssh.socket`, which is enabled and
   works; the warning can be ignored. Following the advice was not tested. T3
   starts on 24.04 and showed no such warning; T5b does not use the in-place
   tool. The check is new in rc5, so the earlier 22.04 runs (rc3 T4, rc4 T4b)
   could not show it either.
2. **New SSH logins fail during parts of both release upgrades** (rc6: the
   tool says so, no change of behaviour), for about 19 minutes in the first
   one (OpenSSH unpacked but not yet configured) and about 7 minutes in the
   second. Open connections keep running, and so does the upgrade in tmux.
   Wait and log in again.
3. **`sudo` is missing for about 12 minutes** during the upgrade to 26.04
   (rc6: the tool says so, no change of behaviour), while it is replaced by
   sudo-rs. `sudo tmux attach -t upgrade-2604` fails with "command not found"
   then. Waiting does not help for tmux: rc6 T3 found that a new `tmux
   attach` cannot reach the run from tmux's replacement until the reboot
   (B73); follow the log with `sudo tail -f` instead.
4. **No view of the run when it is started through `curl | sudo bash`**
   (fixed in rc6, B71). The terminal prints "Could not attach this terminal.
   The run goes on in the tmux session upgrade-2604" and returns. The run
   goes on; follow it with `sudo tmux attach -t upgrade-2604`. `--check`
   still advises starting the command inside tmux, which rc5 does by itself.
5. **The tmux window stays open after the last reboot** with "Press Enter to
   close this window" (seen in T4b as well; fixed in rc6, B72).
6. Minor: `grub2-common.service` failed once on the first boot of 26.04
   ("invalid environment block") and was fine after the next reboot;
   `etc-report.txt` lists the files `/etc/sysctl.d/10-*.conf` that 24.04
   reorganized as gone, which is harmless.

### rc6 (2026-10-25)

All runs used the release branch, started with the documented commands and
`SOURCE`/`TAG` set to it. Every mail the testers sent to a box themselves
(vacation triggers, delivery checks, push tests) was a marked test mail sent
with `smoke.py --send-test-mail`, except the one unmarked mail of the
negative check in T4.

| Run | Commit | Result |
|---|---|---|
| T4 (22.04 → 24.04 → 26.04) | `d78ed0e` | start state: the 22.04 test VM (Ubuntu 22.04.5, v74, Dovecot 2.3.16, Postfix 3.6.4, PHP 8.0, Nextcloud 26.0.13, sudo 1.9.9, tmux 3.2a; `ssh.service` enabled), with a vacation reply sent before the upgrade. Started with `curl … \| sudo bash -s -- --yes --no-backup-check` from a terminal: the terminal showed the run in tmux (B71); Ctrl-b d detached it; a client attached again and killed with SIGKILL did not stop the run; clients attached before each release upgrade stayed attached through the SSH outages and only dropped at the reboots. `--check` no longer advised starting it inside tmux. "All checks passed" with no manual step. Mail offline 1 h 25 min, 2 reboots (release upgrades 33 and 31 min, setup 15 min; whole run 1 h 25 min). The notes about SSH and sudo came before each release upgrade and before the first reboot, once each. Measured: new SSH logins failed for about 19 and 7 minutes, `/usr/bin/sudo` was missing for about 12.5 minutes, each reboot took 21 s. Phase verify: no unit warning (B70; `ssh.service` disabled, started by `ssh.socket`). The tmux window closed 60 s after the end (B72). Both favicons served (Roundcube and Nextcloud, the file of `branding/`). Ubuntu 26.04.1, Dovecot 2.4.2, Postfix 3.10.6, PHP 8.5, Nextcloud 34.0.5; `doveconf -n`, `postconf -n` and `postfix check` without warnings; no failed units (the `grub2-common` failure of rc5 T4 did not show); the vacation duplicate database kept working, no phantom folders. Reboot: SSH back after 22 s, all units active; IMAP login, submission and port 25 from the peer worked. Smoke 73/73. Negative check: one unmarked mail to alice gave 2 FAILs (`mig-folders-alice`, `mig-pop3-uidl-alice`: "1 new, not test mails"); after it was deleted, both passed |
| T3 (24.04 copy) | `d78ed0e` | start state: the 24.04 test VM (Ubuntu 24.04.5, v74, Dovecot 2.3.21 with fts_xapian and the push plugin, PHP 8.0, Nextcloud 26.0.13, Roundcube 1.6.12, sudo 1.9.15, tmux 3.4), hooks for the local web service and the greylisting exception. Started with `curl … \| sudo bash -s -- --keep-local --yes --no-backup-check`: the terminal showed the run with 24.04's sudo, and Ctrl-b d detached it. "All checks passed"; mail offline 53 min (rc5: 1 h 01 min), 1 reboot (release upgrade 33 min, setup 15 min). The before hook ran just before mail went offline, the after hook at the end; push reached the web service after the upgrade; the greylisting exception was kept; full-text search gave the same hits with the old indexes; phase verify listed no unit; the window closed 60 s after the end. Measured: `/usr/bin/sudo` missing for about 15 minutes, new SSH logins failing for about 8.5 minutes. The run found B73: from tmux's replacement (3.4 → 3.6, about 6 minutes into the release upgrade) until the reboot a new `tmux attach` cannot reach the run, although the tool advised it; fixed in `165f18d` (text of the tool and the docs only). Reboot: SSH back after 21 s, all units active, mail delivered. Smoke 71/73 in the first run: alice had one unmarked mail that arrived while the test VM was built, after its manifest, and was in the snapshot; the comparison found it, as it should. Deleted, then 73/73 |
| T5b (rc3 → rc6) | `165f18d`; final smoke at `c0a530c`; repeated at `e6bb8de` | start state: the 24.04 copy upgraded in place with rc3 (Ubuntu 26.04.1, Nextcloud 34.0.5, Roundcube 1.7.5), with Dovecot disabled (B67), mailinabox and munin "bad" (B69), the phantom folders of a vacation reply (B66) and another machine's name in `/etc/hosts`. Update: `git remote set-url`, then `sudo … bash -c "$(curl …/setup/bootstrap.sh)"`, three dialogs answered with Enter; setup exit 0 in 109 s (rc5: 143 s). A probe every 2 s saw Postfix down three times (about 4.5 s in all) and Dovecot three times (under 0.3 s each); one probe mail was refused at connect, the other 6 were delivered at once, none deferred. Afterwards: all core units enabled and active, the phantom folders removed, `/etc/hosts`, the cloud-init template and `/etc/mailname` correct, the greylisting exception kept, Nextcloud sharing limited to the domain, the same full-text hits, push working, both favicons served. Reboot: SSH back after 20 s, all units active, mail delivered. Five more setup runs changed only what upstream changes on every run (the nightly job's minute, the order of the OpenDKIM tables, Roundcube's `des_key`); they found B74 (`10-ssl.conf` grows) and B75 (logrotate fails), fixed in `fb81430` and `c0a530c`. An admin's own favicons (a replaced favicon of the Elastic skin, a favicon uploaded in Nextcloud) were kept on three runs. Smoke 71/73 in the first run: two unmarked mails for alice from when the test VM was built were in the snapshot; deleted, then 73/73 at `c0a530c`. Repeated at `e6bb8de`: three more update runs (one with the apt locks held for 90 s: setup waited and went on, B79), smoke 73/73 |
| T2 (22.04 → fresh 26.04) | `4bbdacd` (a first run at `d58ee33` found B78) | the 22.04 test VM with a vacation reply sent before, and a fresh 26.04 VM. Started on the new machine with `curl …/tools/migrate-to-2604.sh \| sudo bash -s -- --from <old box> --skip-network-checks` (and the addresses of the test network), the questions answered with "y": the terminal showed the run with sudo-rs (B71), Ctrl-b d detached it, a killed client did not stop it. "All checks passed"; downtime 22 min 3 s (from stopping the old box to the end of the checks; setup with Nextcloud 26 → 34 took 21 min 35 s); the new box answered on port 25 and 587 after 3 min and on 993 after 4 min, while setup still ran. Verify: 4 users, 5 aliases, 4 mailboxes, 25 messages, 2 Sieve scripts, Bayes, Nextcloud accounts, contacts and events; DKIM, DNSSEC (DS records unchanged for 3 zones), TLS and backup keys and the Let's Encrypt account unchanged; all 11 services active and enabled. `--check-old`: nothing on the old box started again. The vacation duplicate database came over. Both favicons served. Reboot: SSH back after 17 s, port 25 greeting in 0.3 s. Smoke 73/73 (peer: the old box). `--check` before the runs found B76 and B77 |
| T1 | `e6bb8de` (a first run at `4bbdacd`: 62/62) | install 1193 s (rc5: 1671 s), exit 0. All 14 core units enabled and active before and after a reboot, no failed units; `ssh.socket` active; port 25 greeting 0.08 s after the boot. The admin panel's icons, `/favicon.ico`, Roundcube's and Nextcloud's favicons are the files of `branding/`. Reboot: SSH back after 21 s; submission and port 25 from the peer delivered. Smoke 62/62 |

What ran on which code: T1 and the repeated T5b ran on the last code commit
`e6bb8de`. T3 and T4 ran on `d78ed0e`. After them came B73 (texts of the
in-place tool), B74, B75, B78 and B79 (setup steps) and B76 and B77 (the
migration tool only). The setup steps were tested on 26.04 by the T5b runs
and T1; T3 and T4 were not repeated, so they have not run the new setup
steps on a box that comes through a release upgrade. T2 ran before B79,
whose code path T1 and the T5b runs cover. The release commit changes only
the release tag in the scripts and the documentation.

#### rc6 certification

After the release commit `9858546` came `tests/fork/log-audit.sh`
(`33f056b`) and with it the certification runs: every scenario again, each
followed by a log audit of the box under test. The runs of the first round
shared one hypervisor (T1, T2, T4 and T5b started within two minutes, T3
25 minutes later), so the disk was busy; that is where the longer SSH and
sudo times below come from.

| Run | Commit | Result |
|---|---|---|
| T1 (fresh 26.04) | `33f056b` | install exit 0 in 2085 s; two reboots, SSH back after 21 and 19 s; smoke 62/62 after each reboot |
| T2 (22.04 → fresh 26.04) | `33f056b` | "All checks passed"; setup on the new machine 2451 s; reboot, SSH back after 22 s; smoke 73/73 (and 21/21 for the logins and the migrated data right after the reboot) |
| T3 (24.04 copy, in place) | `33f056b` | "All checks passed"; mail offline 1 h 19 min, 1 reboot; new SSH logins failed for about 14 minutes, `/usr/bin/sudo` was missing for about 26 minutes; a reboot after the run, SSH back after 21 s; smoke 73/73 |
| T4 (22.04 → 24.04 → 26.04, in place) | `33f056b` | "All checks passed"; mail offline 2 h 04 min, 2 reboots; new SSH logins failed for about 36 minutes (22.04 → 24.04) and about 10 minutes (24.04 → 26.04), `/usr/bin/sudo` was missing for about 19 minutes; a reboot after the run, SSH back after 20 s; smoke 73/73 (and 7/7 for the logins and enabled services right after the reboot) |
| T5b (rc3 → rc6) | `33f056b` | update run 1, exit 0 in 144 s; reboot, SSH back after 21 s; smoke 73/73; update run 2, exit 0 in 109 s; reboot, SSH back after 25 s |

The log audit of every one of these runs had classes that were not on the
allowlist of `33f056b`. Each class was checked: the defects became B80
(Munin sent no alerts), B81 (spampd's PID file), B82 (cron during setup),
B83 (nsd not restarted) and B84 (the tools' tmux scope); the harmless ones
went into `tests/fork/log-audit-allow.txt` with their reason (`e6634bf`,
`c7fd0bb`).

The fixes were then tested on the update path T5b, the path of the boxes
that already run the fork, from the same snapshot (the 24.04 copy upgraded
in place with rc3) with the fresh 26.04 test box as peer. Like all rc6
runs, the update runs used the documented command (`setup/bootstrap.sh`
through `curl | sudo bash`) with `SOURCE` and `TAG` set to the release
branch on the lab's mirror, before the tag existed; the published tag
itself was not used.

| Run | Commit | Result |
|---|---|---|
| T5b | `12b4dc2` | update run 1, exit 0 in 133 s; reboot, SSH back after 24 s; smoke 74/74 (with the new `munin-alert-contact`); update run 2, exit 0 in 107 s; reboot, SSH back after 27 s |
| T5b | `c7fd0bb` | update run 1, exit 0 in 141 s; reboot, SSH back after 31 s; smoke 71/74: `fail2ban-imap`, `-pop3` and `-managesieve` failed ("no ban after 26 failed logins"). logrotate.timer had rotated `mail.log` during the smoke test, and Dovecot wrote into `mail.log.1`: this is B85. Update run 2, exit 0 in 105 s; reboot, SSH back after 24 s |
| T5b | `9152190`, then `47d91e8` | the second version of the B85 fix (a path unit that had Dovecot reopen its log), later replaced. Update run 1 to `9152190`: exit 0 in 116 s; reboot, SSH back after 24 s; smoke 74/75. The one FAIL was the new check `fail2ban-log-rotation`, which did not parse its own output (`unexpected output: dovecot=/var/log/mail.log  rsyslog=1 owner=syslog:adm 640`, with two spaces before `rsyslog=`, which the regex did not allow; Dovecot and rsyslog did write the new file); `47d91e8` fixes the regex in `smoke.py`. Update run 2 (`9152190`, 88 s), reboot (SSH back after 25 s), update run 3 to `47d91e8` (103 s); smoke 75/75. Log audit: 0 UNKNOWN, 59 allowed classes, one of them with a new rule in the lab's own list (`(sd-pam)` "pam_systemd(systemd-user:session): Varlink call io.systemd.Login.ReleaseSession failed: io.systemd.Login.NoSuchSession" at the reboot, planned for the repository's allowlist in rc7) |
| T5b, final | `5d2d3aa` | the code of the release: B85 in its final form (Dovecot logs through syslog), the favicon copy in a directory of root's own, and the tools' sudo-rs check by path. After the catch-up of logrotate.timer at the boot of the snapshot (it failed there, B75), update run 1: exit 0 in 112 s; logrotate started again: success; reboot, SSH back after 26 s; smoke 75/75, with `fail2ban-log-rotation` (a forced rotation: `log_path=syslog`, no Dovecot process holds a file in `/var/log`, rsyslog writes the new `mail.log` as syslog:adm 0640; then the bans on IMAP, POP3 and ManageSieve against the rotated log) and `mail-log-logins` (`mail_log.py` counts the IMAP and POP3 logins in the new line form); update run 2: exit 0 in 93 s; reboot, SSH back after 24 s. Run 2 changed in `/etc` and the web apps only what setup changes on every run: as upstream, the minute of the nightly job, the order of the OpenDKIM `KeyTable` and `SigningTable` and Roundcube's `config.inc.php` (setup writes a new `des_key` each time; the snapshot records only the file's hash), and, from the fork, the time stamps of its favicon copies (same content). Log audit since the start of run 1, with the repository's allowlist and the lab's own list: the tool of `5d2d3aa` found 3 UNKNOWN classes: rsyslog's "message repeated N times: [ ... ]" around a lab-only warning (two classes), now that Dovecot's lines go through rsyslog, and one Postfix restart race of setup ("connect #N to subsystem public/cleanup: Connection refused"). `3656d5d` (tests only) classes repeated lines as the repeated line and adds a rule for the race; with its tool and list: 0 UNKNOWN, 58 allowed classes. Two of them matched rules of the lab's own list only: the push plugin of the copied box, whose endpoint is not in the lab, and Docker changing a sysctl of the network interface |

B85 was checked by hand as well. Without a fix (`c7fd0bb`, Dovecot with
its own `log_path`): a forced rotation, then 26 failed IMAP logins from
the peer; all 26 lines went into `mail.log.1` and the `dovecot` jail found
none. The second version of the fix was checked on the same box at
`594cec9` with the helper of `9152190` installed by hand (two forced
rotations, then the bans; a symlink in place of `mail.log`: the helper
exited 1 with its warning; the scripts of these hand checks were not
kept); its own T5b run is the `9152190` row above,
and the version itself was replaced because the check before the reopen
could be raced (see B85). The first version (`594cec9`), whose helper
created and chowned the file as root in `/var/log`, was replaced before
that; its T5b run was stopped and is not counted. On the T5b box at
`5d2d3aa`, after the final run: `doveconf` gives `log_path = syslog` and
`syslog_facility = mail`; no Dovecot process holds a file in `/var/log`;
the units and the helper of the second version are not installed; 30000
lines from one process of a service unit, sent through syslog with
facility mail in 1.3 s, all reached `mail.log` and the journal. On the
same box: `systemctl stop spampd` removed `/run/spampd.pid` and the start
wrote it again (B81); cron was stopped from the start to the end of each
update run (B82); nsd was not restarted by the update runs, whose
`nsd.conf` did not change, only by the reboots (B83).

Targeted check of B84 on the 26.04 test box at `47d91e8` (systemd 259):
both tools pass `bash -n`; the scope lines taken from the tools start a
scope whose description and transient file carry the new text, and a
daemon-reload logs no "Missing '='" or "Unknown key". The resume script,
generated by the in-place tool with a state directory, `TAG` and `SOURCE`
that contain spaces, quotes and `$`, started the tool with unchanged path,
arguments and environment in all three forms (tmux, `exec` in a scope,
plain `exec`), and the scope had the description "Mail-in-a-Box upgrade to
Ubuntu 26.04 (resumed after a reboot)". As a control, the `exec` line of
`33f056b` with the new description failed with a syntax error.
`upgrade-in-place-to-2604.sh --check` exited 0. Limits: systemd 259 does not
log the messages even for the old scope line, so the 22.04 case (systemd
249) is covered only by the T4 run on `33f056b`, which showed the messages,
not by a run with the fix; `migrate-to-2604.sh --check` got only as far as
the SSH login to the old box. The tools' sudo-rs check (`mux_tty`) of
`5d2d3aa` was compared with the one before on the same box: through a
pipe with sudo-rs, through a pipe with classic sudo (`sudo.ws`) and with
a terminal as stdin, both versions of both tools chose the same terminals.
A 22.04 or 24.04 box was not used for it.

**Not repeated on the code of the release.** At the maintainer's
decision, T1 to T4 were not run again on `5d2d3aa`: rc7 is already in
progress, and the full matrix (T1 to T5b, and T6 on the Internet before a
final release) runs again for it. Further runs of T1, T2 and T4 on
intermediate commits (`12b4dc2`, `c7fd0bb`) were stopped early and are not
counted. What changed after `33f056b`, by path:

* **Setup** (used by T1, T2 and T5b, and by the setup phase of T3 and
  T4): B80 (`setup/munin.sh`, `management/munin_notify.sh`), B81
  (`setup/spamassassin.sh`), B82 (`setup/start.sh`), B83 (`setup/dns.sh`),
  B85 (`setup/mail-dovecot.sh`: `log_path=syslog` and the removal of the
  second version's units; `management/mail_log.py`; comments in
  `management/fail2ban_admin.py` and `conf/fail2ban/jails.conf`), and the
  favicon copy for Nextcloud (`setup/nextcloud.sh`). Run on the code of the
  release by T5b only; not on a fresh install, a migration or a box that
  comes through a release upgrade.
* **`tools/migrate-to-2604.sh`** (T2): the scope description of B84, a
  comment about cron, and the sudo-rs check by path. Covered by the
  targeted checks of B84 and `mux_tty`, not by a T2 run.
* **`tools/upgrade-in-place-to-2604.sh`** (T3, T4): the scope and the
  resume scope descriptions and `printf %q` in the resume script (B84);
  `detect_extensions` leaves out the fork's spampd drop-in; the texts with
  the SSH, sudo and release upgrade times; the sudo-rs check by path.
  Covered by the targeted checks and `--check`, not by a T3 or T4 run.
* **Tests and documentation only:** `tests/fork/log-audit.sh` and its
  allowlists, `smoke.py` (`munin-alert-contact`, `fail2ban-log-rotation`,
  `fail2ban-filters`, `services-enabled` on SysV services),
  `prepare-testenv.sh`, README-fork.md, TESTING-fork.md, BUGS-fork.md,
  CHANGELOG-fork.md.

#### Open findings of rc6

Not fixed in rc6:

1. The `--check` plan of `tools/upgrade-in-place-to-2604.sh` does not say
   that new SSH logins and sudo fail for a while; the tool says it only
   during the run, and the docs describe it.
2. The durations in that note come from test runs, and they vary with the
   load of the disk: the tool now says 20 to 40 and 10 to 15 minutes for
   SSH and 12 to 26 minutes for sudo; the certification runs measured up to
   36 and 14 minutes for SSH and 26 minutes for sudo (see "rc6
   certification" above). rc7 is to shorten the SSH outage or announce its
   end in the run.
3. `migrate-to-2604.sh --check` proposes a start command with `--from` and
   `--skip-network-checks`, but without the other options given (such as
   `--public-ip`). This was so before rc6.
4. Started through `curl | sudo bash` with classic sudo (22.04, 24.04), the
   tool attaches the operator's own terminal: a change of the window size
   reaches tmux only on the next attach. With sudo-rs (26.04), if the tool is
   killed while attached, the terminal stays in raw mode (`reset` fixes it).
5. With any uploaded favicon, Nextcloud also serves it as the touch icon,
   with the type `application/octet-stream` (Nextcloud's own code).
6. Updates on the boxes that came through a release upgrade print
   "pollinate: cannot create /var/cache/pollinate/log: Permission denied";
   it is harmless (README-fork.md, "Setup output").
7. A watcher attached before tmux is replaced during the release upgrade to
   26.04 and kept through the SSH outage was only tested in T4, not in T3.

### Production use

rc3 was used to upgrade a production box in place: Ubuntu 24.04 (release-
upgraded from 22.04), Mail-in-a-Box v74 with full-text search, and a Docker
stack that uses the mail by IMAP. The tool reported "All checks passed". Mail
was offline 1 h 10 min, with 1 reboot. Checked afterwards: incoming mail,
IMAP logins, Nextcloud 34.0.5, Roundcube, ActiveSync and Autodiscover,
full-text search with the old indexes, fail2ban.

Four things had to be done by hand: waiting for the nightly backup, installing
tmux, stopping and starting the Docker stack, and putting back a greylisting
exception that setup had dropped. They became features of rc4 (the tool
waits for a running backup, starts itself in tmux, has before/after hooks,
and setup keeps `greylist_bypass_senders`). The bugs found there are B57-B60.
The update test of a copy of this box later showed that rc3 had left
Dovecot disabled (B67); setup of rc5 enables it again.

## Known differences

These FAIL or SKIP results are expected and do not count as defects:

* **`mig-pop3-uidl-<user>` and `mig-folders-<user>` up to rc5** compared
  each mailbox with the manifest written before the upgrade, so mails sent
  to the box before the smoke test (push test mails, mails that trigger the
  vacation reply, the replies themselves, the test mails of the reboot check
  in rc5 T4) counted as new: "0 missing, 2 new (have 8, want 6)",
  "INBOX: 8 msgs != 6". Nothing was missing in these runs. This gave 2 FAILs
  (alice) in rc3 T3b, rc4 T3c and T5, and 6 FAILs (alice, bob, carol) in the
  rc5 runs, where vacation replies were triggered on purpose. From rc6 the
  smoke test marks its own mails (header `X-Miab-Test: 1`) and ignores marked
  mails and the automatic replies and bounces to them; it reports how many
  it ignored. Testers send their own mails with `smoke.py --send-test-mail`
  (see below). Any other missing or new mail, and a seeded mail that is
  there twice, is a FAIL.
* **`nextcloud-share-scope`** skips its admin part when the box's admin
  account is not in the Nextcloud group `admin`. That was the case in the
  test runs; the check still passes.
* **The test network changes the box** (`prepare-testenv.sh`, test boxes
  only): no ufw limit for SSH from the jump host, no greylisting for the
  peer boxes, the DMARC and SPF scores of SpamAssassin neutralized for the
  unsigned test mails, the box's name pinned in `/etc/hosts`, the jump host on
  the fail2ban allowlist. Greylisting itself is therefore not tested; the
  smoke test checks only the configuration of the exception.
* **The status checks report errors** that come from the test network (DNS
  delegation, reverse DNS, glue records, port 25 from outside). Each run
  goes through them; none may come from the box itself.

## Reproducing the tests

Everything is in `tests/fork/`:

* `seed-legacy.sh` fills an upstream Mail-in-a-Box (as root, on the box) with
  the test data and writes the manifest (`/root/seed-manifest.json`).
* `prepare-testenv.sh` adapts a test box to the test network. Test boxes only,
  never a production box. Run it as root after every install or upgrade.
* `smoke.py` runs the checks. `tests/fork/smoke.py --help` lists the options;
  the header of the script has the typical runs for T1, T2 and the baseline.
* `log-audit.sh` audits the logs of a box under test (as root, on the box,
  read-only): all warnings and errors since `--since TIME` (default: the last
  boot), as message classes with counts and examples (secrets masked),
  compared with `log-audit-allow.txt`. Each line there is a regex and,
  after " # ", the reason; artefacts of the test network and the smoke test
  are marked as such. Exit code 0 if every class is on the list, 1 if not
  (`UNKNOWN`). Give the start of the scenario as `--since`, add local
  exceptions of your lab with `--allow-extra FILE`, and `--json OUT` for the
  report. An UNKNOWN class is a defect to fix, or, once checked as harmless,
  a new line with its reason in the allowlist. On a box upgraded in place,
  what it logged between stopping mail and the start of setup carries the
  phase of `tools/upgrade-in-place-to-2604.sh` (`[in-place:release_2404]`,
  from the tool's state file); the noise of the old releases and the release
  upgrades is allowed only with that prefix. From rc7 on, setup marks its
  start and end in the journal (identifier `mailinabox-setup`), and what
  the box logged during a setup run carries the prefix `[setup]`; rules
  that start with `^\[setup\]` (cut connections of the restarts of the
  services) apply only there. For the old box of a migration,
  add `--allow-extra tests/fork/log-audit-allow-old-box.txt`. `--since`
  also takes the short forms `-30m`, `-24h`, `-2d`. With `--baseline
  BEFORE.json` (the `--json` report of an earlier run, e.g. before an
  update) a class that was in it is listed as KNOWN with both counts and
  does not count; only new classes are UNKNOWN. `--internet` adds
  `log-audit-allow-internet.txt`, the usual noise of a box on the Internet
  (firewall blocks, scanners, password guessing, TLS errors of bad clients,
  spam that Postfix rejects, DNS errors of other zones), for production
  boxes only; the test scenarios do not use it.
* `tools/update-check.sh` (`before`, `backup`, `after`, `mailcheck`) records
  the state of a box before and after an update, compares it (with the
  expected changes of `tools/expected-changes/`) and runs `log-audit.sh`
  against the baseline; see "Updating the fork" in README-fork.md. In a
  test lab without an external probe address, `mailcheck --probe` with an
  address of the box itself only exercises the code path: the reply has to
  be sent back over port 25 by hand (or by a small script of the lab), so
  outbound delivery and DKIM are only checked locally.
* Mails that you send to a box under test yourself (vacation triggers,
  delivery checks after a reboot) must be test mails, or the manifest
  comparison counts them as new. Send them with `smoke.py --send-test-mail
  FROM TO` (`--via 587` or `465` submits as FROM, `--via 25` sends over
  port 25, from `--peer-ssh` if given), or add the header `X-Miab-Test: 1`
  to them. `seed-legacy.sh` leaves test mails, and the automatic replies and
  bounces to them, out of the manifest, so it can be run again after them.

Configuration:

* `smoke.py` reads `KEY=VALUE` lines from `--env-file`, by default from
  `$MIAB_TEST_ENV`, else `tests/fork/credentials.env` (ignored by git):
  `TEST_USER_PW`, `FRESH_ADMIN`, `FRESH_ADMIN_PW`, `LEGACY_ADMIN`,
  `LEGACY_ADMIN_PW`, optionally `SEED2_DOMAIN` and `SEED3_DOMAIN` (default
  `seed2.example.net`, `seed3.example.net`). Passwords are never printed.
* `prepare-testenv.sh` needs `JUMP_HOST`, `PEERS`, `BLOCK_V4` and `BLOCK_V6`,
  from the environment or from the file `TESTENV_FILE` (owned by root, mode
  600; it is parsed, not sourced). There are no defaults.

Outline, with a legacy box 192.0.2.10 and a new box 192.0.2.11:

1. Install Ubuntu 22.04 and upstream Mail-in-a-Box on one VM, run
   `seed-legacy.sh`, copy the manifest, take a snapshot. Optionally run the
   smoke test against it as a baseline (`--mode migrated --expect-nc 26`).
2. Install Ubuntu 26.04 on a second VM and take a snapshot.
3. Run the scenario from the table above.
4. Run `prepare-testenv.sh` on the box under test.
5. Run the smoke test from a workstation, e.g. after a migration:

        tests/fork/smoke.py --host 192.0.2.11 --hostname box.legacy.example.net \
            --mode migrated --manifest seed-manifest.json --jump legacy-box \
            --ssh new-box --peer 192.0.2.10 --peer-ssh legacy-box --fail2ban

   The fail2ban group refuses to run when the attacks would come from the
   address of the `--ssh` session; use `--peer-ssh`.

## Not tested

* **Interactive first install** with `sudo bash -c "$(curl …)"` on 26.04. The
  fresh installs ran non-interactively as root; the `sudo bash -c` form was
  tested for updating an existing box.
* **T2 (migration) in rc3 to rc5.** `migrate-to-2604.sh` changed in rc4 and
  rc5 without an end-to-end run; rc6 ran T2 again. The migration was only
  run from a 22.04 source, not from a release-upgraded 24.04 box.
* **Modes of the tools** that the scenarios do not use: `--rollback`,
  `--rehearse`, `--from-backup`, `--push-zones-to-old`, `--cleanup-only`.
* **The Internet:** Let's Encrypt certificates, delivery to other providers,
  blocklists, reverse DNS. These need public DNS and an open port 25.
* **Other virtualization and hosting providers.** The tests ran on one
  hypervisor with its cloud-init. The cloud-init configuration of hosting
  providers' images (`manage_etc_hosts`, B68) was not tested.
* **IPv6-only boxes.** The test boxes have IPv4 and IPv6.
* **Large boxes.** The test data is small; the only large data set was the
  production upgrade above.
* **Ubuntu 20.04 or older, Mail-in-a-Box older than v60** (the in-place tool
  needs v60, the migration v68), and Nextcloud older than 26. These are not
  supported.
