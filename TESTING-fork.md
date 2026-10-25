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
  that uses exactly the documented command against the published tag.
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
updates rc3 to rc5. Most in-place runs in the lab use `--no-backup-check`
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
  DKIM key; the Roundcube identity. All compared with the manifest.
* **admin**: admin API login, creating and deleting a user and an alias,
  backup status; from rc4 the fail2ban API, settings, report, filters (with
  injected user names) and the Intrusion Protection page.
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
  rc4 also turning adaptive banning off reaches the running jails.

The number of checks grew from release to release (49 in the first runs, 73
in the rc5 in-place runs), and it depends on the mode and on `--fail2ban`.
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

Every FAIL in this table is one of the known differences below, except one
Nextcloud lock in rc4 T5 (see there).

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
describes it. 6 is not changed.

1. **False warning about `ssh.service`.** Phase verify prints "Enabled before
   the upgrade, disabled now (they do not start after a reboot):
   ssh.service", and `etc-report.txt` advises `systemctl enable` for it.
   Since 24.04, SSH is started by `ssh.socket`, which is enabled and works;
   the warning can be ignored. Following the advice was not tested. T3 starts
   on 24.04 and showed no such warning; T5b does not use the in-place tool.
   The check is new in rc5, so the earlier 22.04 runs (rc3 T4, rc4 T4b)
   could not show it either.
2. **New SSH logins fail during parts of both release upgrades**, for about
   19 minutes in the first one (OpenSSH unpacked but not yet configured) and
   about 7 minutes in the second. Open connections keep running, and so does
   the upgrade in tmux. Wait and log in again.
3. **`sudo` is missing for about 12 minutes** during the upgrade to 26.04,
   while it is replaced by sudo-rs. `sudo tmux attach -t upgrade-2604` fails
   with "command not found" then; wait until it is back.
4. **No view of the run when it is started through `curl | sudo bash`.** The
   terminal prints "Could not attach this terminal. The run goes on in the
   tmux session upgrade-2604" and returns. The run goes on; follow it with
   `sudo tmux attach -t upgrade-2604`. `--check` still advises starting the
   command inside tmux, which rc5 does by itself.
5. **The tmux window stays open after the last reboot** with "Press Enter to
   close this window" (seen in T4b as well).
6. Minor: `grub2-common.service` failed once on the first boot of 26.04
   ("invalid environment block") and was fine after the next reboot;
   `etc-report.txt` lists the files `/etc/sysctl.d/10-*.conf` that 24.04
   reorganized as gone, which is harmless.

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
* Mails that you send to a box under test yourself (vacation triggers,
  delivery checks after a reboot) must be test mails, or the manifest
  comparison counts them as new. Send them with `smoke.py --send-test-mail
  FROM TO` (`--via 587` or `465` submits as FROM, `--via 25` sends over
  port 25, from `--peer-ssh` if given), or add the header `X-Miab-Test: 1`
  to them.

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
* **T2 (migration) since rc2.** `migrate-to-2604.sh` changed in rc4 and rc5
  (settings of an existing `mailinabox.conf` kept, greylisting exception taken
  over, more checks in phase verify), without a new end-to-end run.
  The migration was only run from a 22.04 source, not from a release-upgraded
  24.04 box.
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
