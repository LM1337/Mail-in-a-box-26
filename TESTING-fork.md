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
  rc6 and rc7 runs used the documented commands with `SOURCE`/`TAG` set to
  the release branch.
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
| T6 | a box on the Internet (public DNS, open port 25), before a final release | fresh install, then an update of it | as T1, then as T5; `tools/update-check.sh` around the update, `mailcheck` with a real external probe address | fresh |

Variants: **T3b** is a clean T3 run from the tag after a first run had found
bugs. **T3c** and **T4b** repeat T3 and T4 with the automatic tmux of rc4;
the SSH client is killed in the middle of the run, and the upgrade must go
on. T3c also runs the before/after hooks for the local web service. **T5b**
updates rc3 to the release under test (from rc5). Most in-place runs in the lab use `--no-backup-check`
(the test VMs have no fresh backup) and run `prepare-testenv.sh` before the
smoke test.

### What the scenarios of rc7 cover

rc7 adds tools and behaviour that the scenarios ran, not only the smoke
test (results in "rc7" below):

* **T5b** (update from the published rc6, Part A, and from rc3, Part B):
  `tools/update-check.sh before` (both parts) and `backup` (Part A) on the
  box before the update, started through `curl … | sudo bash -s -- STEP` as the upgrade note says
  (a box on rc6 has no copy of the tool; the lab pointed the tool's helper
  URL to the release branch, see "rc7"). `backup` with `--docker-dir`, two
  `--docker-volume` (one archive each) and `--postgres` for a stand-in
  Postgres container, and the upload to an rsync target of the lab (an
  account on the peer), verified by checksum; the archives were decrypted
  and the dump restored. After the update `after` and `mailcheck` with a
  lab probe: an address on the peer whose script answers the marked mail
  over port 25. Outbound delivery and the DKIM signature were therefore
  only checked inside the lab. `PROBE_ADDRESS` in `/etc/mailinabox.conf`
  was still there after the update (B103), and an interactive update
  showed no welcome dialog. RESULT OK of `after` was shown with the
  recorded states and the version lines of a tag, because the lab
  installed a branch.
* **T3 and T4** (the release upgrades): the fallback SSH server on port
  1022 on the one-binary OpenSSH of 22.04 (8.9p1, T4) and 24.04 (9.6p1, T3
  and T4): a key login on port 1022 while port 22 was down, the refusal of
  a user who is not an administrator there, the run's notes when port 22
  stops and starts answering, and afterwards no fallback process, no ufw
  rule for its port and none of its files, also after a reboot.
  `--ssh-fallback-test` before the upgrade in both, through
  `curl ... | sudo bash -s --` as the upgrade note says (from the final run
  on). The case of a box without a group `admin` (B100) ran in T4 only (the
  group was deleted before; the 24.04 copy of T3 has an empty one). The
  final run adds the StrictModes check (an administrator whose home others
  can write, B115), a `Match` block in a nested include (B118), and the
  fallback for the release upgrade that starts at the boot into 24.04
  before any SSH login (B119), all in T4. T3 also ran
  `update-check.sh before`, `backup`, `after` and `mailcheck` around the
  in-place upgrade of the upstream box (B106, B110), and `--cleanup-only`
  with `--old-checkout`.
* **T1 and T5b**: Munin's alert setting through the admin panel's API
  (smoke test `api-munin-alerts`, and real alerts of forced warnings and
  criticals to the chosen address with their recovery), the nginx reload
  of setup (nginx's main process the same through the setup runs), the
  OpenDKIM tables unchanged by second setup runs (B95), `settings.yaml`
  mode 0600 after saves in the panel (also T2), and the ActiveSync contact
  sync of new users (B99) with a small ActiveSync client of the lab.
* **All scenarios**: the smoke group `api`, the log audit with `--smoke`
  and the lab's own list; the classes of setup runs carry `[setup]`, from
  the marks that root logged only.
* **T6** (not run for rc7; before the final release): `mailcheck` with a
  real external probe address (delivery to another provider and back, DKIM
  and SPF there), Let's Encrypt, a box on the Internet.

### Client load during updates

The smoke test runs after a setup run, so it does not see what clients see
while setup runs (B120 to B122 were found on a production box with phones
and webmail open during an update). `tests/fork/client-load.py` keeps the
clients of a few test users busy at about the rate of a box with several
phones per user: per user 4 ActiveSync devices that Sync the inbox, the
calendars and the address books and then long-poll with Ping, 2 that
FolderSync and Sync every 8 s, CalDAV and CardDAV requests (also through
the box's `/caldav` proxy, the path of Z-Push), an IMAP login every second,
an IMAP IDLE connection, SMTP AUTH on 587 and a Roundcube session that
refreshes its inbox. The ActiveSync devices recover as phones do (Provision
again after HTTP 449, resync after FolderSync status 9, Sync status 3 or 12
and Ping status 7). `--seed` first puts a marked event, contact and mail
into each user's account, so that the Syncs return items. Each request is
ok, auth (login refused), throttled (HTTP 429, Nextcloud's brute-force
protection), unavailable (no connection, HTTP 502/503/504, a temporary
failure), disconnect (a Ping or IDLE cut, a resync) or error; `--log`
records every request with its latency. With `--marker-file` the results
before setup starts are the baseline: an error that already occurred there
(a problem of the box before the update) is listed, but does not fail the
run. The summary gives the counts per client and phase, the longest outage
per client and user, the first failures and the seconds with failures;
`--report` writes them as JSON.

The update scenarios (T3, T4 and T5b; also T1's second setup runs) run two
instances with 3 test users, from 5 minutes before setup starts until 10
minutes after it ends (Nextcloud's throttle showed only after setup; on the
production box it lasted 30 minutes). The baseline must be long enough for
every new ActiveSync device to finish its first Sync of all folders (on the
2-vCPU copy of the production box under this load about 3 minutes), or an
error of the box that only that Sync shows counts as new:

* one on the box under test, as a normal user, with the clients on
  127.0.0.1 (like Z-Push's own calls);
* one on another host of the test network (the peer, never the jump host,
  whose failed logins would count against the other tests), with another
  `--device-prefix`: only these requests come from a real address, which
  fail2ban and Nextcloud's brute-force protection count.

For example (on the box, and the same on the peer with `--host` the box's
address):

    tests/fork/client-load.py --host 127.0.0.1 --hostname box.example.net \
        --user alice@example.net --user bob@seed2.example.net \
        --user carol@example.net --env-file credentials.env --seed \
        --device-prefix box --marker-file /tmp/setup-started \
        --duration 2400 --log load.jsonl --report load.json

The update driver creates the marker file when it starts setup (or sends
SIGUSR1). For the in-place upgrades (T3, T4) the load runs around the setup
phase only: mail is offline during the release upgrades. Pass criteria:
both instances RESULT OK (no auth or throttled result, no error that did not
occur before setup, each outage shorter than `--max-outage`, 30 s); no
fail2ban `Found` for the peer's address in `/var/log/fail2ban.log` and no
brute-force attempts for it (`occ security:bruteforce:attempts`) during the
window; unavailable results and disconnects only while setup restarts or
reloads a service. An IMAP IDLE or ActiveSync Ping that a reload cuts and
that reconnects is fine, a failed login is not. Afterwards `smoke.py --only
activesync`. The smoke test checks the fail2ban part itself with
`--load-since TIME --load-ip ADDR` (the start of the load and the addresses
of both instances, the peer's and 127.0.0.1): its first check
`load-no-failed-login` fails on a fail2ban `Found` of these addresses or a
failed ActiveSync or Autodiscover login from them since TIME, before the
smoke test's own failed logins (B126).

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
  injected user names) and the Intrusion Protection page; after rc7 the
  status wants `miab-zpush`, the filter cases cover it (B126), and the
  saved backup status (`admin-backup-saved`, B125): a refresh in the
  background, polled until it ends, with the control panel answering
  meanwhile (the slowest answer is in the note), and a new saved status
  afterwards. After rc7, with `--ssh` and after the **api** group:
  `admin-journal-no-hash`, no line of the journal of `mailinabox.service`
  since the start of the run looks like a password hash or the output of
  `doveadm pw` (B127; the run's logins, wrong passwords and password
  changes included). It reads the journal with journalctl alone and counts
  on the test host: a failed `sudo` or journalctl, or a journal it may not
  read, is a FAIL, not an empty count.
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
  secondary nameserver, the type-A shortcut `/dns/custom/{qname}` (it would
  change real A records), the fail2ban writes (group admin, group
  fail2ban). While `api-munin-alerts` has the alerts set to off or to a
  custom address (a few seconds), a real alert of Munin in that moment is
  not sent or goes to the test mailbox.
  `tests/fork/password-hash.py` (after rc7; no box needed, with `--doveadm`
  on a box as root) checks the control panel's SHA-512 crypt (B127): the
  test vectors of its specification, the stored forms it checks itself, the
  plain-text schemes (`{PLAIN}`, `{CLEAR}`, `{CLEARTEXT}`, `{PLAIN-TRUNC}`,
  HEX and B64 encodings; doveadm must not be called for them), its limits,
  and with
  `--doveadm` random passwords (8 to 511 bytes, no line breaks: doveadm
  reads only one line, so these are tested offline) against Dovecot's
  `doveadm pw` both ways, wrong passwords, other schemes through the
  doveadm fallback, and the plain-text cases against doveadm's own result.
  The random passwords go to doveadm on its standard input.
  `tests/fork/api-routes.py` (no box needed) checks that every route of
  `management/daemon.py` is documented and every documented operation has a
  route, that `smoke.py` calls or excludes each of them, and the content
  types it expects.
* **dns**: DNSSEC (RRSIG, DNSKEY), MX and DKIM for each zone, SSHFP against the
  host keys sshd serves, custom records.
* **web**: Nextcloud version, CalDAV, CardDAV and WebDAV with the mail
  password; Nextcloud sharing within the mail domain (from rc4); Roundcube
  login; Z-Push OPTIONS and Autodiscover; `nextcloud-dav-proxy` (after rc7):
  the proxy of `/carddav` passes an escaped name and the query string (a
  card whose name has a space and a `?`, put through Nextcloud's own path,
  is read, found in `?export` and deleted through `/carddav`, and the
  address book stays; B130), nginx's dotfile block does not apply to these
  paths (a file `.htmiab-smoke-...` put through Nextcloud's own path is read
  through `/webdav`, a card `.gitmiab-smoke-...vcf` through `/carddav`), and
  `/caldav` and `/webdav` answer PROPFIND.
* **activesync** (after rc7): `nextcloud-bruteforce-loopback`: 127.0.0.1
  is on Nextcloud's brute-force bypass list, and no entry is there twice
  (B121; a check of the list: Nextcloud counts no attempts for a listed
  address); `nextcloud-forwarded-for`: a failed login (a user that does not
  exist) from the box's public address through the `/webdav` proxy, which
  connects to Nextcloud from 127.0.0.1, is logged and counted by Nextcloud
  for that address, not for 127.0.0.1 (B121; its attempts are reset
  afterwards); `zpush-sync`: an ActiveSync account as a phone sets it
  up (`tests/fork/eas.py`: Provision, FolderSync, Sync of all calendar and
  contact folders), and a marked event and two marked contacts put into
  alice's Nextcloud over DAV just before arrive, one of the cards with a
  name without `.vcf`, like Nextcloud's example contact `default` (B128);
  all are deleted again, and the test device is removed from Z-Push (with
  `--ssh`); `zpush-ping`: a Ping with a heartbeat of 3600 s gets status 5
  with the box's bound at once (no answer within 90 s fails it: no bound;
  a Ping of 60 s of the device then ends the long one), and (with `--ssh`) nginx's
  `fastcgi_read_timeout` of every `/Microsoft-Server-ActiveSync` location is
  at least a minute longer than that bound, so a long Ping does not end
  with 504 (B129). Quick enough to run
  right after a setup run: `--only activesync`.
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
  rotated log, so a jail that a rotation made blind fails (B85). After rc7
  also failed ActiveSync (OPTIONS with a wrong password) and Autodiscover
  logins get the peer banned by `miab-zpush` (B126), on HTTP and HTTPS,
  and 25 ActiveSync requests without credentials (a user in the URL, as a
  phone's first request) must log no failed login and ban nothing
  (`fail2ban-activesync-noauth`). Use a lab address of the peer
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
| rc7 | 2026-10-25 | 68/68 ³ | 79/79 ³ | 79/79 ³ | 79/79 ³ | 79/79 (T5b from rc6), 71/71 (from rc3) ³ |

¹ Certification run at `33f056b`, before the last fixes of rc6 (B80-B85);
not repeated on the code of the release (see "rc6 certification" below).
The earlier rc6 development runs had the same counts (T3 and T5b after a
first run of 71/73).

² The commits after `5d2d3aa` change only the log audit tool, its
allowlist and the documentation.

³ Repeated certification run after the fixes B106-B114 (see "rc7" below),
on `d586ba0`, `f5bd16f` and `20a5162`: the code of setup, of the
management daemon and of the tools' scripts is the same in these commits
and in the final head; between them only `tools/expected-changes/any.txt`
(B114), the allowlists of the log audit and the documentation changed.
Every log audit, with the lists of the final head, ended with 0 unknown
classes. The first run on the release commit `1d3ef06` had the same smoke
counts and found B106-B113.

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

### rc7 (2026-10-25)

All runs installed the release branch from the lab's mirror with the
documented commands and `SOURCE`/`TAG` set to it, before the tag existed;
the published tag itself was not used. `tools/update-check.sh` through
`curl | bash` takes its helpers from the branch main, which still held rc6,
so the lab pointed its URL to the release branch. All five scenarios ran at
the same time on one hypervisor with an HDD pool (at most two release
upgrades at once), so the disk was busy; the longer times below come from
there. The peer for port 25, the fail2ban attacks, the probe address of
`mailcheck` and the rsync target of `backup` was a second test box, at an
rc7 development commit in the first run and at `1d3ef06` in the repeated
one, updated to `518eba7` after it and to `2ad4f04` after the final run.
Every mail the testers sent to a box themselves was a marked test mail.

#### First certification run (release commit `1d3ef06`)

| Run | Result |
|---|---|
| T1 (fresh 26.04) | install exit 0 in 2111 s; smoke 60/60, then 68/68 with `--fail2ban` after each of two reboots; Munin alert script 29/29; three second setup runs (91 to 111 s) without welcome dialog, OpenDKIM tables unchanged, nginx reloaded with the same main process. Log audit: 3 unknown classes (the `tmp.mount` unmount at a shutdown; a Nextcloud "database is locked" of the lab's CardDAV request during a cron minute), 103 allowed |
| T2 (22.04 → fresh 26.04) | "All checks passed"; downtime 42 min 31 s; smoke 21/21, 79/79, 79/79. Log audit of the new box: 5 unknown classes (Postfix's sqlite lookup locked during the smoke test's API write round trip, four classes of one event; `tmp.mount`), 102 allowed; old box: 1 unknown (v74's Munin contact warning), 16 allowed. `--check` proposed the start command without the given addresses (B113) |
| T3 (24.04 copy, in place) | "All checks passed"; mail offline 1 h 23 min; port 22 down 16 min, key logins on 1022 meanwhile; sudo missing about 31 min; smoke 79/79 twice. `update-check.sh before` recorded no version and no status checks and `backup` stopped on the box with its checkout in `/mailinabox` (B106); `after`: "CHANGED - 56 unexpected" for the changes of a release upgrade (B110); `mailcheck`: FAILED for a round trip that worked (B107); `--ssh-fallback-test` left an empty `/root/upgrade-2604` (B111). Log audit: 19 unknown classes over the whole run (17 of the v74 box before it stopped mail, `tmp.mount`), 0 since the second reboot |
| T4 (22.04 → 24.04 → 26.04, in place) | without the group `admin` (B100); "All checks passed"; mail offline 1 h 49 min; port 22 down 31 and 6 min; new logins on 1022 failed twice for a few seconds (the `libtirpc3` switch; `/run/sshd` gone for up to 10 s, B112); smoke 79/79. Log audit: 5 unknown classes (v74's Munin contact warning before it stopped mail, the fallback's `/run/sshd` fatal, a user journal moved aside at the first boot of 24.04, two classes of the lab's own port probes), 586 allowed |
| T5b (rc6 → rc7 and rc3 → rc7) | smoke 79/79 twice (from rc6) and 71/71 (from rc3); `before` and `backup` passed; `after` could not say OK, because setup gives the nightly job a new minute on every run (B108), and from rc3 it missed the changes of rc4 and rc5 (B109); `mailcheck`: FAILED (B107). Log audit: 24 unknown classes, none a defect of the box |
| Peer (rc7 development commit → `1d3ef06`) | interactive update, exit 0 in 89 s, no welcome dialog; smoke `--only api` 5/5. Log audit: 2 unknown classes, both about a lab unit file with mode 0600 |

No smoke run had a FAIL. The defects were B106 to B113 (B114 came
from the repeated run); the harmless classes went into the allowlists with
their reasons (`f8d2963`, `20a5162`), the lab artefacts into the lab's own
list.

#### Certification run after the fixes

Every scenario ran again on the same test VMs, rolled back to their
snapshots (T5b Part A from a snapshot of the box copy updated to the
published rc6, Part B on a temporary copy of the rc3 snapshot). Commits:
`d586ba0` has the fixes B106 to B113; `f5bd16f` adds the rule of B114 to
`tools/expected-changes/any.txt`; `20a5162` adds allowlist lines; the
commits after it change only the documentation. The code of `setup/`,
`management/`, `conf/` and of the tools' scripts is the same in all these
commits and in the final head; each log audit below was run (again, after
the run) with the lists of the final head and the lab's own list.

| Run | Commit | Smoke | Mail offline | New SSH logins | Log audit |
|---|---|---|---|---|---|
| T1 | install `d586ba0`, the later setup runs `f5bd16f` | 60/60, 68/68, 68/68 | – (fresh install; second setup runs not measured) | only the reboots (SSH back after 21 s) | 0 unknown, 102 allowed |
| T2 | `d586ba0` | 21/21, 79/79, 79/79 | 46 min 28 s (stop of the old box to the end of the checks); port 25 and 587 after 8 min, 993 after 9 min | no outage | new box 0 unknown, 111 allowed; old box 0 unknown, 20 allowed |
| T3 | tool `d586ba0`, setup `f5bd16f` | 79/79, 79/79 | 1 h 35 min | port 22 down 19 min, key logins on port 1022 worked meanwhile; sudo missing about 37 min | 0 unknown, 14 known from the baseline, 483 allowed |
| T4 | tool `d586ba0`, setup `f5bd16f` | 79/79 | 2 h 04 min | port 22 down 42 and 6 min; port 1022 worked in every check but one (about 20 s, both ports); sudo missing about 13 min | 0 unknown, 607 allowed |
| T5b Part A (rc6 → rc7) | `d586ba0` | 79/79 (one run 69/79, see below), 79/79 | update runs of 101 and 118 s, a probe every 2 s: ports 25 and 587 failed 1 probe at a time (twice in the second run), 993 and LMTP 1, spampd 3 in a row; one probe mail of each run refused or cut at connect | no outage (a check every 10 s) | 0 unknown, 0 known, 81 allowed |
| T5b Part B (rc3 → rc7) | `20a5162` | 69/71, then 71/71 | update run of 118 s: 1 failed probe on each port, 2 (not in a row) on spampd, one probe mail refused at connect | no outage | 0 unknown, 3 known, 78 allowed |
| Peer (`1d3ef06` → `518eba7`) | `518eba7` | admin and api 12/12 | update run of 86 s: ports 25, 587, 993 and LMTP never failed a probe, spampd 2 in a row; all probe mails delivered | – | 0 unknown, 23 allowed |

The release upgrades took 1 h 10 min (T3) and 1 h 12 min and 32 min (T4),
setup 20, 14 and 46 min (T3, T4, T2; T1's install 41 min). Reboots: SSH
back after 20 to 23 s in every scenario, all units active.

| Run | Details |
|---|---|
| T1 (fresh 26.04) | install exit 0 in 2460 s. Munin's alert setting through the panel's API: 29/29 checks, among them one real alert of a forced warning, one recovery, none on the next run, critical only to a custom address, off. ActiveSync of a new user (B99): Provision, FolderSync, Sync and Ping with status 1, the contact added over CardDAV synced, no example contact. Three second setup runs (non-interactive, interactive bootstrap, interactive `sudo mailinabox`), exit 0 in 88, 109 and 95 s: no welcome dialog, the OpenDKIM tables byte for byte the same (B95), nginx reloaded with the same main process, `settings.yaml` 0600 |
| T2 (22.04 → fresh 26.04) | `--check` proposed the full start command with the given addresses (B113). "All checks passed"; the old box stopped 21:48:17, setup 2744 s, end of the checks 22:34:45. 4 users, 5 aliases, 4 mailboxes, 25 messages, 2 Sieve scripts; the vacation duplicate database came over; `--check-old`: nothing started again. Log audit of the new box with the lists of `d586ba0`: 4 unknown classes (fwupd's timer once during setup, a late timer interrupt of the VM), 0 with those of `20a5162` |
| T3 (24.04 copy, in place) | `update-check.sh before` and `backup` on the upstream box with the checkout in `/mailinabox` (B106): version v74 and 17 errors and 9 warnings of the status checks recorded (all from the test network); v74's `backup.py` ran, the archive took `/mailinabox`, the stack directory and the volume and was verified on the lab's rsync target. `--ssh-fallback-test`: admin key login and sudo on 1022, a non-admin refused there and accepted on 22, nothing left afterwards, also no `/root/upgrade-2604` (B111). The box has an empty group `admin`. "All checks passed", 1 reboot. Port 22 stopped answering 22:29:09 and answered again 22:48:01 (the run's notes); the fallback ran OpenSSH 9.6p1 of 24.04, the non-admin was refused on it. `after`: "RESULT: NOT JUDGED" (B110, exit code 3, the log audit found no new class; a first `after` without the lab's list named 4 classes of the lab: ufw blocks of its probes and Docker of the stand-in). `mailcheck`: RESULT OK over STARTTLS (B107). `PROBE_ADDRESS` kept. `--cleanup-only` purged the old packages, `--old-checkout` deleted `/mailinabox-v74` |
| T4 (22.04 → 24.04 → 26.04, in place) | `--ssh-fallback-test` with and without the group `admin` (B100), as in T3. The run without the group: "All checks passed", 2 reboots. The fallback ran OpenSSH 8.9p1 of 22.04 and 9.6p1 of 24.04 with the users of the group sudo and root; the one failed check at 22:09:55 was the `libtirpc3` switch of 22.04 → 24.04, when a new sshd cannot load its libraries on either port; the non-admin was refused on 1022 both times; afterwards no fallback process, listener, ufw rule or file. Vacation replies after the upgrade; port 25 from the peer delivered. Log audit with the lists of `d586ba0`: 11 unknown classes (a new SSH login during the minutes between the unpack of the new systemd and the re-execution of PID 1 gets no user manager; Nextcloud's example event of a first login left out on a busy SQLite database), 0 with those of `20a5162` |
| T5b Part A (published rc6 → rc7) | `before`, `backup` (through `curl \| sudo bash -s --`) with `--docker-dir`, two `--docker-volume` (one archive each) and `--postgres` (a stand-in container), uploaded and verified by checksum (decrypted and restored in the first run on `1d3ef06`; checksums verified in this run). Interactive update twice, no welcome dialog; the OpenDKIM tables unchanged, nginx's main process the same; `PROBE_ADDRESS` kept; `settings.yaml` 0600. `after`: "CHANGED - 6 unexpected": 3 version lines from installing a branch, the 2 lines of munin-node's process name (B114, fixed in `f5bd16f`) and a status check warning of a second backup cache (the lab had changed the backup target right before `before`); its log audit named 1 class of the lab (a Nextcloud cron job of the snapshot marked as crashed, on the lab's list), so it ended with "look at the unexpected changes ... and the new log message classes" (exit code 1). The same records with the version lines of a tag and the lists of `f5bd16f`: only that warning. `mailcheck`: RESULT OK. Munin through the API: a custom address set, an invalid one refused, a forced warning gave 1 alert, the recovery 1, the next run none. ActiveSync of two new users (B99): status 1. The 69/79 run came right after a reboot that followed the fail2ban group: fail2ban read the attacks again at its start and banned the peer for 4 minutes (fail2ban's normal behaviour after a restart); run again, 79/79 |
| T5b Part B (rc3 → rc7) | `before`, interactive update (no welcome dialog), `PROBE_ADDRESS` kept; `after`: "CHANGED - 2 unexpected, 28 expected", the 2 version lines of the branch install (B109: `/etc/mailname`, the hosts line, Dovecot and `mailinabox.service` enabled again are EXPECTED); with the version lines of a tag "RESULT: OK - 0 unexpected, 30 expected". `mailcheck`: RESULT OK. The first smoke run had 2 FAIL for the two unmarked lab mails of the snapshot, which the lab script had not deleted |

#### Final run after the review of the fixes (`014ff8a`)

A review of the fixes found B115 to B118 (the fallback SSH server took
keys that sshd refuses under StrictModes and missed `Match` blocks in
nested includes; `update-check.sh` used a checkout it had rejected; the
tools took the backup target and passphrase through a directory that the
user-data account can replace). A first run with those fixes (`e967061`)
found B119 in T4 (no fallback for the release upgrade that starts at the
boot into 24.04) and an empty `/root/upgrade-2604` after a refused
`--ssh-fallback-test` (B111); it was stopped for T3 and T4. Its T2
(21/21, 79/79, 79/79) and T5b Part A (79/79 twice) ended with 0 unknown
classes. Then T2, T3, T4 and T5b Part A ran again from their snapshots on
`014ff8a`, which has all fixes: `tools/update-check.sh`,
`tools/migrate-to-2604.sh`, `setup/`, `management/` and `conf/` are the same
as in `e967061`, and `setup/`, `management/` and `conf/` the same as in
`f5bd16f`, the setup runs of T1 above. `2ad4f04` adds allowlist lines; the
commits after it change only the documentation. T1 and T5b Part B did not
run again (they run no code that changed since `f5bd16f` and `20a5162`,
except the lists). Each log audit was run again with the lists of `2ad4f04`
and the lab's own list.

| Run | Smoke | Mail offline | New SSH logins | Log audit |
|---|---|---|---|---|
| T2 | 21/21, 79/79, 79/79 | 29 min 26 s (stop of the old box to the end of the checks); ports 25 and 587 after 3 min 30 s, 993 after 4 min | no outage | new box 0 unknown, 107 allowed; old box 0 unknown, 20 allowed |
| T3 | 79/79, 79/79 | 1 h 08 min (the tool's downtime) | port 22 down 12 min, key logins on port 1022 worked meanwhile; sudo missing about 22 min | 0 unknown, 14 known from the baseline, 491 allowed |
| T4 | 79/79 | 1 h 37 min | port 22 down 25 and 8 min; port 1022 worked in every check of both outages; sudo missing about 15 min | 0 unknown, 616 allowed |
| T5b Part A (rc6 → rc7) | 79/79, 79/79 | update runs of 128 and 92 s, a probe every 2 s: ports 25 and 587 never failed, 993 3 in a row, LMTP 1 at a time (twice), spampd 1 at a time (three times, once in the second run); every probe mail delivered | no outage | 0 unknown, 1 known from the baseline, 87 allowed |
| Peer (`518eba7` → `2ad4f04`) | admin and api 12/12 | non-interactive update run of 78 s | – | 0 unknown, 14 allowed |

Reboots: SSH back after 19 to 23 s, all units active.

| Run | Details |
|---|---|
| T2 (22.04 → fresh 26.04) | `--check` proposed the full start command. "All checks passed"; the backups of the new box were paused and resumed through the checked `backup/` directory (B117); `--check-old`: nothing started again; vacation replies on the new box |
| T3 (24.04 copy, in place) | `update-check.sh before` and `backup` through curl on the v74 box: the checkout `/mailinabox` accepted with its whole tree (B116), version v74 and 17 errors and 9 warnings of the status checks; archive with `/mailinabox`, the stack directory and the volume, verified on the lab's rsync target. `--ssh-fallback-test` through `curl \| sudo bash -s --` as documented: keys file of the administrator `root:<group>` 0640, admin key login and sudo on 1022, the non-admin refused there and accepted on 22, nothing left. "All checks passed"; phase snapshot copied the encrypted system archive to the rsync target through the checked backup directory (B117), the backups paused and resumed with the real target. The fallback ran OpenSSH 9.6p1 of 24.04 while port 22 was down (the run's notes: 04:36:31 and 04:47:42). `mailcheck`: RESULT OK; `PROBE_ADDRESS` kept. `after` with the lists of the box's checkout (`014ff8a`) named 2 classes (certbot's timer during the release upgrade), allowed in `2ad4f04`. `--cleanup-only` and `--old-checkout` as before |
| T4 (22.04 → 24.04 → 26.04, in place) | Before the upgrade, with the group `admin`, through curl: a test administrator with a home of mode 0775 whose group has another member: sshd on port 22 refused his key, the fallback left it out with the warning and refused it as well (B115); the other administrator logged in on 1022 with sudo, the non-admin was refused there. With a `Match` block two include levels down (`sshd_config.d/*.conf` including a file of its own) `--ssh-fallback-test` refused to start (B118) and left no `/root/upgrade-2604` (B111). The test files and that user were removed, then the group `admin` (B100). "All checks passed", 2 reboots. The fallback started for both release upgrades: OpenSSH 8.9p1 of 22.04, and 9.6p1 of 24.04 right after the boot into 24.04, before any SSH login (B119); the non-admin was refused on 1022 both times; afterwards no fallback process, listener, ufw rule or file. Vacation replies after the upgrade; port 25 from the peer delivered |
| T5b Part A (published rc6 → rc7) | `before`, `backup` (through curl) with `--docker-dir`, two `--docker-volume` and `--postgres`, uploaded and verified by checksum on the lab's rsync target; on the box the archives decrypted with the backup passphrase: the volume archives list their files, the pg_dump restored to SQL text with the two rows of the stand-in, the system archive holds 35289 entries with the checkout's `management/`. Interactive update twice (128 and 92 s), no welcome dialog; the OpenDKIM tables byte for byte the same, nginx's main process the same; `PROBE_ADDRESS` kept; `settings.yaml` 0600. `after`: "CHANGED - 4 unexpected": 3 version lines from installing a branch and the status warning of a second backup cache (the lab changed the backup target right before `before`); replayed with the version lines of a tag: only that warning. Its log audit named 4 classes: Dovecot started by setup before its passdb exists and a closed client of spampd (both allowed in `2ad4f04`), and the lab's Nextcloud job of the snapshot. `mailcheck`: RESULT OK over STARTTLS. Munin through the API: a custom address, an invalid one refused, a forced warning gave 1 alert, the recovery 1, the next run none. ActiveSync of two new users (B99): Provision, FolderSync, Sync and a Ping on the contacts with status 1 |

What the update tools reported, in short (all runs): on the update path
(T5b) `before`, `backup` and `mailcheck` passed; `after`, replayed with the
recorded states and the version lines of a tag (the lab installed a
branch), gives RESULT OK from rc3, and from rc6 only a status warning
caused by the test setup remains; on an in-place upgrade
(T3) `before` and `backup` work on the upstream box and `after` lists the
changes as NOT JUDGED.

#### Open findings of rc7

Seen in the runs, not fixed in rc7:

1. Postfix's sqlite lookup has no busy timeout: a mail that is cleaned up
   while the management daemon commits to `users.sqlite` waits a minute in
   maildrop (a temporary error for mail over SMTP). Seen once, during the
   smoke test's API write round trip. Dovecot's auth-worker has none either:
   in T3 of the first run after the review (`e967061`) one login during
   that round trip failed once. Setup's own commit at its end (the
   automatic aliases) caused 44 such failures in one update test after
   rc7; it no longer writes when nothing changes (B133), and Z-Push answers
   a login that Dovecot could not check with 503 instead of counting it as
   a failed login (B126).
2. Setup's restart of Dovecot can store a mail in delivery twice (Postfix
   delivers it again after spampd's 421); no mail is lost.
3. On the busy test host a new user's first Nextcloud login took 20 to 90
   s; Z-Push's CalDAV request through nginx has the default proxy timeout
   of 60 s.
4. `tests/fork/log-audit.sh` replaces only the users that exist at the
   time of the audit by `<user>`: the lines of a deleted test user miss
   the rules written for them. The test scripts delete their users after
   the audit.
5. Through `curl | bash`, `tools/update-check.sh` takes its helpers from
   the branch main; before a release is on main, a test of the release
   branch has to point it elsewhere.
6. The outage times of the release upgrades depend on the load of the
   disk: on the shared test host port 22 was down up to 42 minutes from
   22.04 to 24.04 and sudo was missing up to 37 minutes from 24.04 to 26.04.
   From `6235572` on the tool's texts and its `--check` plan give the times
   of all rc7 runs (19 to 42 and 6 to 19 minutes, 12 to 37 for sudo).
7. In the `libtirpc3` switch of the release upgrade from 22.04, a new sshd
   cannot load its libraries for some seconds (about 20 s in T4), on port
   22 and on the fallback's port; open connections are not affected.
8. Setup restarts Dovecot (setup/mail-dovecot.sh) before
   setup/mail-users.sh has written its passdb, and again two seconds later:
   a login in between fails once ("No passdbs specified"; seen once, from
   the lab's probe in T5b). The client tries again. **Fixed after rc7**
   (B120): Dovecot is loaded once, after its whole configuration is written,
   and its files are written atomically; the log audit no longer accepts the
   message. The update of a production box from rc6 to rc7 showed what such
   failures do to Nextcloud (B121).
9. When Ubuntu has released a new nginx package, setup's `apt-get upgrade`
   restarts nginx (dpkg, not setup), and the requests in that second are cut:
   Z-Push's CalDAV and CardDAV calls through 127.0.0.1:443, ActiveSync Syncs
   that end with HTTP 500, Roundcube. Seen in the update test after rc7
   (nginx 1.28.3-2ubuntu1.12). Before the fix of B126 after rc7, Z-Push
   answered the failed CalDAV/CardDAV logins with 401 (a phone asks for its
   password) and, with `LOGAUTHFAIL` on, counted them as failed logins; now
   503.

Of the open findings of rc6, 1 (the `--check` plan named the fallback SSH
server, and from `6235572` on also says that new SSH logins and sudo fail
for a while), 2 (the fallback SSH server and the run's notes) and 3 (B113)
are done; 4 to 7 remain.

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

The same box was later updated from rc3 to rc6 with the commands of
"Updating the fork" in README-fork.md. rc7 builds on that update: the Munin
alert setting, the API test and the update tools (see CHANGELOG-fork.md,
rc7).

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
* `client-load.py` keeps clients busy during an update and counts what
  failed (see "Client load during updates"); `eas.py` is the small
  ActiveSync client that it and `smoke.py` use, also on its own
  (`EAS_USER=... EAS_PW=... tests/fork/eas.py HOSTNAME`).
* `log-audit.sh` audits the logs of a box under test (as root, on the box,
  read-only): all warnings and errors since `--since TIME` (default: the last
  boot), as message classes with counts and examples (secrets masked),
  compared with `log-audit-allow.txt`. Each line there is a regex and,
  after " # ", the reason; artefacts of the test network and the smoke test
  are marked as such. Exit code 0 if every class is on the list, 1 if not
  (`UNKNOWN`). Give the start of the scenario as `--since`, `--smoke` when
  the smoke test ran (its deliberate failed logins to the control panel,
  `log-audit-allow-smoke.txt`; the default list does not accept them, so
  that they stay visible on a production box), local exceptions of your lab
  with `--allow-extra FILE`, and `--json OUT` for the report. An UNKNOWN class is a defect to fix, or, once checked as harmless,
  a new line with its reason in the allowlist. On a box upgraded in place,
  what it logged between stopping mail and the start of setup carries the
  phase of `tools/upgrade-in-place-to-2604.sh` (`[in-place:release_2404]`,
  from the tool's state file); the noise of the old releases and the release
  upgrades is allowed only with that prefix. From rc7 on, setup marks its
  start and end in the journal (identifier `mailinabox-setup`; only marks
  that root logged count), and what
  the box logged during a setup run carries the prefix `[setup]`; rules
  that start with `^\[setup\]` (cut connections of the restarts of the
  services) apply only there. For the old box of a migration, and for a
  box upgraded in place when `--since` lies before the tool stops mail,
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
  `--rehearse`, `--from-backup`, `--push-zones-to-old` (`--cleanup-only`
  ran in rc7 T3). Of `tools/update-check.sh backup`: the targets other than
  rsync (local, S3, B2), and Docker
  setups other than the stand-ins of the lab. `after` on a real update from
  one tag to the next: the lab installed a branch, so RESULT OK was shown
  with the recorded states and the version lines of a tag.
* **The published tag and GitHub.** The rc7 runs installed the release
  branch from the lab's mirror, not the tag `v78-r2604.0-rc7`, and
  `tools/update-check.sh` through `curl | bash` took its helpers from the
  release branch by a changed URL, not from the branch main on GitHub.
* **The fallback SSH server's refusal** where sshd asks for more than a
  key (`AuthenticationMethods`) or has `Match` blocks: the Match case (also
  two include levels down) ran with `--ssh-fallback-test` on the test boxes,
  `AuthenticationMethods` only against the function; neither in a release
  upgrade. Its StrictModes check was compared with sshd on OpenSSH 8.9p1,
  9.6p1 and 10.2p1 in twelve cases and ran once in T4 (a home of mode 0775
  with a shared group). A box whose sshd listens only on some addresses, a
  firewall of the provider in front of port 1022, and other values of
  `UPGRADE_SSH_FALLBACK_PORT` and `UPGRADE_SSH_FALLBACK_USERS` were not
  tested.
* **The checks of `$STORAGE_ROOT/backup` and of the checkout (B116,
  B117)** refusing a directory: run with the tools on the fresh-install
  test box (a `backup/` of another owner, one replaced by a directory of the
  user-data account, a group-writable file in the checkout), not in a
  scenario.
* **The Internet (T6):** Let's Encrypt certificates, delivery to other
  providers, blocklists, reverse DNS, and `mailcheck` with a real external
  probe address (DKIM and SPF checked by another provider). These need
  public DNS and an open port 25. T6 has not run for any release yet; it
  runs before the final release v78-r2604.0.
* **Other virtualization and hosting providers.** The tests ran on one
  hypervisor with its cloud-init. The cloud-init configuration of hosting
  providers' images (`manage_etc_hosts`, B68) was not tested.
* **IPv6-only boxes.** The test boxes have IPv4 and IPv6.
* **Large boxes.** The test data is small; the only large data set was the
  production upgrade above.
* **Ubuntu 20.04 or older, Mail-in-a-Box older than v60** (the in-place tool
  needs v60, the migration v68), and Nextcloud older than 26. These are not
  supported.
