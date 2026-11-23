# Testing of the Ubuntu 26.04 fork

This file lists the end-to-end tests that were run for each release of the
fork: what was tested, how, and with what result. It is meant to help you
judge how mature a release is. Changes are in [CHANGELOG-fork.md](CHANGELOG-fork.md),
fixed bugs in [BUGS-fork.md](BUGS-fork.md).

The fork's first release is v78-r2604.0; v78-r2604.1 is a bug-fix release
of the control panel's login, tested without the full set of scenarios
(see "v78-r2604.1"); v78-r2604.2 is a bug-fix release tested with T1, T1n,
T2, T4 and T5b, the last three from upstream's v78 or the previous release
(see "v78-r2604.2"); v78-r2604.3 and v78-r2604.4 are small releases tested
with T1 and T5b (see there). The tests below are a small, fixed set of scenarios
on test machines, not a test of every setup that exists.
Make a backup and try a release on a copy before you run it on the box that
holds your mail.

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

A preparation that should leave the state of a box after its users trained
the spam filter (sa-learn through IMAPSieve) uses `tests/fork/spam-move.py`:
it appends a marked test mail (`X-Miab-Test: 1`, a Message-ID
`@smoketest.invalid`) to a user's INBOX, moves that mail to Spam and back
and deletes it, and checks that the other mails keep their UIDs. Moving a
seeded mail instead gives it a new UID and so a new POP3 UIDL, which the
manifest no longer matches: the start snapshot of T5b from v78-r2604.2 to
v78-r2604.4 was prepared that way, so `mig-pop3-uidl-alice` failed on every
run from it, and the lab used a corrected copy of the manifest for that VM.
A start snapshot prepared with `spam-move.py` works with the original
manifest. The start snapshot of v78-r2604.5 (the box copy at the published
v78-r2604.4) got the moved mail's seeded UID back in the lab and works with
the original manifest too.

## Scenarios

| ID | Start state | Path | Tool / command | Smoke mode |
|---|---|---|---|---|
| T1 | fresh Ubuntu 26.04 | fresh install | `setup/bootstrap.sh` through curl, non-interactive (`NONINTERACTIVE=1`) | fresh, with `--provision` |
| T2 | the 22.04 test VM (v74 with test data) and a fresh 26.04 machine | migration to the new machine | `curl …/tools/migrate-to-2604.sh \| sudo bash -s -- --from <old box>`, on the new machine | migrated |
| T3 | the 24.04 test VM (copy of a production box) | in place, 24.04 → 26.04, one release upgrade | `curl …/tools/upgrade-in-place-to-2604.sh \| sudo bash -s -- --keep-local --yes` | migrated |
| T4 | the 22.04 test VM | in place, 22.04 → 24.04 → 26.04, two release upgrades | `curl …/tools/upgrade-in-place-to-2604.sh \| sudo bash -s -- --yes` | migrated |
| T5 | the 24.04 test VM after an in-place upgrade with rc3 | update of a box that already runs the fork | `git remote set-url` to GitHub, then `sudo bash -c "$(curl -fsSL …/setup/bootstrap.sh)"`; the setup dialogs answered with Enter | migrated |
| T6 | a box on the Internet (public DNS, open port 25), before a final release | fresh install, then an update of it | as T1, then as T5; `tools/update-check.sh` around the update, `mailcheck` with a real external probe address | fresh |
| T7 | a test VM with the published release before, given a copy of the configuration of a production box (users, aliases, settings, custom DNS/web settings; no mail, cloud data, keys or backups; all passwords replaced), isolated from the Internet for mail and DNS | update to the release under test, as on that box | `bootstrap.sh` with `TAG=<commit>`; `tools/update-check.sh before`/`after` | none (logins, maps and the panel checked one by one) |
| T1n | the installed T1 box (from v78-r2604.2) | setup's network checks, `setup/network-checks.sh` of the release before and of the release under test, each under setup's shell options (`set -euo pipefail`) | the script run on the box through its own resolver; cases: not listed, a listed hostname, a listed IP address, a public resolver, a failing resolver | none |

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
  injected user names) and the Intrusion Detection and Prevention page; after rc7 the
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
  `tests/fork/panel-fragments.py` (B178; no box needed) checks that no
  HTML fragment of the control panel's templates has a self-closing tag of
  a non-void element followed by more markup, which jQuery 3 reads as an
  opening tag.
  `tests/fork/admin-mail.py` (System > Notifications; no box needed)
  checks how administrator@ is followed through the aliases (mailbox,
  outside address, loop, unknown address of the box, catch-all, domain
  alias, an alias that names itself, which Postfix delivers to its
  mailbox and does not take for a loop), the report recipient and its invalid values, that Munin's
  standard recipient follows, the list of deliveries and the test mail.
  `tests/fork/nginx-hsts.py` (B180; no box needed) builds the nginx
  configuration of the box's name and of another domain with
  `management/web_update.py` for each HSTS setting of `custom.yaml`
  (`yes`, the default, `preload`, off) and checks that every block of the
  HTTPS server with `add_header` lines of its own has the server's HSTS
  line (nginx inherits a server's `add_header` only into blocks that have
  none), and none when HSTS is off.
  `tests/fork/panel-assets.py` (no box needed) checks that every file the
  control panel's templates name under `/admin/assets/` is one that
  `setup/management.sh` installs (its downloads, Bootstrap 3.4.1's archive,
  its copy of `branding/`), that the icons it copies are in the repository
  and that nginx serves `/admin/assets` from that directory;
  `admin-panel-assets` fetches each of them from the box (HTTP 200, the
  icons the same as the files of `branding/`).
  `tests/fork/status-changes.py` (B179; no box needed) checks that the
  daily status change notice shows a changed check with all of its lines
  and leaves unchanged checks out.
  `api-self-password` (B210): `POST /admin/me/password` from outside gets
  404 from nginx (the endpoint is on 127.0.0.1:10222 only) and changes
  nothing; a test user (`smokepw-<token>`) changes their own password
  through Roundcube's Settings > Password, whose driver calls the
  endpoint (Roundcube's own "Current password incorrect." for a wrong
  current password, the change and the change back, IMAP takes only the
  new password). The user, its archived mailbox
  and (with `--ssh`) its Roundcube record are removed.
  `tests/fork/auth-guard.py` (B126; no box needed) checks
  `management/auth_guard.py`, the reporter of Dovecot's limit of failed
  logins from the box itself: the values it reads from
  `conf/dovecot-auth-guard/guard.lua`, the file names of account names
  (the same as the Lua code's: only A-Z lowered, other bytes as %XX), the
  scan of the state directory (different tags of wrong passwords within
  the window, a tag sent again counted once, files of names
  without failures and old temporary files removed, a symbolic link left
  alone, a directory of another mode refused, events read once, also a
  leftover), `--unlock`, the setting of the control panel (defaults 30 in
  30 minutes, the ranges, invalid values refused, the settings file
  written through its directory's descriptor and read back as the Lua code
  reads it, values out of range ignored), the status and the unlock of the
  API, and the mail of new locks (at once, then at most
  hourly, a name without an account marked, the pending events capped).
  The smoke check `login-auth-guard` (needs `--ssh`) makes 150 IMAP logins
  of a test account with the same wrong password from 127.0.0.1 on the box
  (it must not lock the account), sets the limit to 5 through
  `POST /system/auth-guard` (a limit of 2 must be refused), makes 40
  logins of another test account with different wrong passwords from
  changing addresses of 127.0.0.0/8 (answered at once), then expects that account refused from there with its right
  password, the first account logging in from there in under 3 s, the
  refused account logging in from outside, `GET /system/auth-guard` and
  `--status` naming it and `POST /system/auth-guard/unlock` ending the
  lock; it restores the setting. The Lua code itself was checked with Dovecot 2.4.2 of
  Ubuntu 26.04 in a container (BUGS-fork.md, B126), also against the gaps a
  security review found: rotating 127.x addresses and the box's own
  address (also without a "local" line), a flood of made-up names, a full
  pool of names not on the list, user names with "+", bursts of 200 and 300
  parallel guesses (the rule over 4 windows), the flag of a full pool
  (set, removed after pruning and at a restart), and right passwords in
  parallel (never refused).
  `tests/fork/self-password.py` (B210; no box needed) checks the endpoint's
  logic with stand-ins for the login check and the password change: HTTP
  Basic credentials in UTF-8 and Latin-1, only the caller's password
  changed, the policy, two-factor authentication (no code: 403 and not
  counted; a wrong code: counted), the limits per account and per address
  and their expiry, and that forged addresses, also with made-up account
  names (which count only for the address), do not flush an account's
  failures from the limiter; group admin runs it (`admin-self-password-unit`).
  `tests/fork/migration-record.py` (B211; no box needed) runs
  setup/migrate.py with its migrations replaced by recorders against a
  temporary `STORAGE_ROOT` and record: no record, the same number, a lower
  number in `mailinabox.version` (setup stops before any migration), a
  higher one, one above the newest migration (setup stops unless the
  record has the same number, a downgrade; a later release's migration
  still runs after the right number is written back; a record never
  lowered), a missing file (taken from the record), the record of another
  `STORAGE_ROOT`, a record that is a link, writable by others or broken, and
  a failed migration; group admin runs it (`admin-migration-record-unit`).
  `tests/fork/storage-dirs.py` (B212; no box needed) checks the reads and
  writes of `backup/` and `dns/` below `STORAGE_ROOT` through a checked
  directory (management/utils.py): the helpers (a link, a group-writable
  directory, another owner, a FIFO, the size limit, a link at the name
  replaced without touching its target), backup.py and dns_update.py with
  the directory replaced by a link or a group-writable copy with another
  account's settings (not used, nothing written there, the nightly backup
  stops with the reason), with `custom.yaml` a link, web_update.py
  without the records of a replaced `dns/`, and
  `tools/write_conf.py --own-root-only` (setup's owner of
  `$STORAGE_ROOT/mail` and `users.sqlite`) refusing a directory that root
  does not own already, and `--check-own-root-only` naming such a
  directory or database (also as a command, exit code 1), which
  setup/start.sh runs before setup changes anything, and the KSK's public
  key that the status checks read only through a checked `dns/` and
  `dns/dnssec/` (B183), and the zone signing, which reads the keys
  only through them and writes their patched copies only into its
  temporary directory, also with a key name that holds a path (B191);
  group admin runs it (`admin-storage-dirs-unit`).
  `tests/fork/update-check-compare.py` (B201; no box needed) runs the
  comparison of `tools/update-check.sh after` on states in a temporary
  directory: Postfix and Dovecot settings that only the record after the
  update has are "newly recorded (not judged)" and counted in the RESULT
  line, a changed value of a setting in both records is still judged (with
  and without a rule), a new line of another file is still unexpected,
  every drop-in that setup writes is in a list of expected changes, and
  `after` adds the old-box allowlist after a change of the Ubuntu release
  (B187).
  `tests/fork/roundcube-local.py` (B200; no box needed) checks the report
  of local Roundcube changes that the in-place and migration tools share
  (the two copies must be the same): its idea of setup's settings against
  the configuration that setup/webmail.sh writes, an unchanged
  configuration of the fork and of upstream (nothing to report), extra
  plugin directories, a changed plugin list (also `$config['plugins'][]`),
  changed values of setup's settings, settings set by hand (named without
  their values), comments and strings with `;` and `?>`, files it cannot
  read completely, control characters in names, the comparison with the
  Roundcube after setup and its file `local-changes.json` (0600, removed
  when nothing is open), and System Status's warning from that file
  (which ignores a link and files that another account can write); a
  local plugin that the web server cannot read, the modes of the kept
  copy (B186), and both tools' preflight reports run as bash with `set -u`
  (B185).
  `tests/fork/clone-ref.py` (B188; no box needed) clones a tag, a branch
  and a full commit id from a repository in a temporary directory with the
  tools' `clone_ref` and bootstrap.sh's first clone, and refuses a short or
  unknown commit id without leaving a directory.
  `tests/fork/quiesce-order.py` (B190; no box needed) runs the in-place
  tool's `quiesce_units` and `mask_units` with a stand-in systemctl: the
  services of the apt timers are masked first, together.
  `tests/fork/old-side-filter.py` (B154; no box needed) runs the migration
  tool's filter of the old box's messages: escape sequences shown with
  "?", the CR of a CR LF line end dropped, the command's output and exit
  code kept.
  `tests/fork/owncloud-backup-prune.py` (no box needed) checks the removal
  of old Nextcloud backup copies in a temporary `STORAGE_ROOT`: the three
  newest copies and those of the last 14 days stay (also after three
  failed upgrade runs), older ones go with everything in them, other names
  and a file or link with a copy's name stay, a symbolic link in the place
  of `owncloud-backup` or inside an old copy is not followed, a directory
  that others may write is left alone, and bad arguments are refused.
  `tests/fork/update-check-hint.py` (no box needed) runs setup's hint at
  `tools/update-check.sh` against temporary record directories: the
  commands `after` and `mailcheck` with the stamp when the newest record
  has a `before` but no `after`, the general tip otherwise (no records,
  a complete newest record, a link in the place of a record or of the
  directory), exit code 0 always; and that setup/start.sh shows it only
  without `FIRST_TIME_SETUP` and `MIAB_SETUP_TOOL`, which both tools set.
  `tests/fork/restart-on-change.py` (no box needed) checks the checksum
  that decides whether setup restarts OpenDKIM, OpenDMARC, spampd,
  postgrey, named, systemd-resolved, munin-node and the management daemon:
  a changed file, a new file in a tree, a new name or link target in a
  directory and a new inode of a file it only looks at change it,
  `__pycache__` does not, missing files give no error; and, with stand-ins
  for the service commands, a restart on the first call, on a change and
  for a service that does not run or runs another invocation than the
  record names (started since by something else or at boot: a downgrade,
  a reboot and the way back up), has no readable invocation or a record
  of the earlier format, none without a change, and nothing
  recorded after a failed restart. The same for PHP-FPM (B122): nothing
  without a change of its configuration, a reload on a change or in
  another invocation, a restart
  when the reload brings no "ready to handle connections", when
  `php-fpm8.5 -t` refuses the configuration, or when PHP-FPM does not run
  before or after the reload. The package check counts the unit's own
  package and the library packages after it (an update of SpamAssassin's
  Perl modules for spampd; one that is not installed does not count).
  spampd's sa-update hook (`record_hook`, `refresh_record`) runs with a
  stand-in for systemctl: it records the new invocation when the record
  names the files of now (also a record of the earlier format), after
  which setup does not restart, and leaves the record alone with other
  files (a downgrade's), without a record or when the unit does not run.
  `tests/fork/status-dns.py` (B181; no box needed) runs the status
  checks' `query_dns()` against a stand-in for dnspython: records,
  NXDOMAIN and NoAnswer, a failed lookup, a timeout, YXDOMAIN and a name
  too long for DNS (no exception, `[error]`), a nameserver of its own;
  and the Spamhaus DBL check of a mail domain (not listed, listed, a
  failed lookup, a name too long with `.dbl.spamhaus.org`); and the
  DNSSEC DS check (B182): a DS lookup that timed out or failed gives
  "Could not check" without the DS records to set, no, a correct and a
  wrong DS record give the messages as before, a zone's checks look its
  DS records up once and suggest DNSSEC only when none is set, and the
  box's name checks its zone's DS records only when they are set; an
  unreadable KSK key gives the DS records without it (B183), and the test
  of outbound port 25 discards nc's output (B184). Group admin runs it
  (`admin-status-dns-unit`).
  `tests/fork/cloud-relays.py` (B126; no box needed) checks how System >
  Intrusion Detection and Prevention recognises Microsoft's servers: the shipped list
  `conf/fail2ban/microsoft-relays.txt` (header, IPv4 and IPv6, the
  AutoDetect ranges, every network accepted by the allowlist; a list
  changed by hand is refused), addresses inside and just outside the
  ranges, forward-confirmed reverse DNS with stand-in lookups (a spoofed
  PTR name without a forward match, also one naming Microsoft, gives no
  name; an address outside the ranges gets no hint), the limit of lookups
  per request, and that `tools/update-microsoft-relays.py` takes only the
  service area Exchange of Microsoft's answer. Group admin runs it
  (`admin-cloud-relays-unit`); `admin-fail2ban-status` checks that the box
  reads the list and gives hints only for banned addresses.
  `tests/fork/ban-reasons.py` (v78-r2604.4; no box needed) checks that the
  reasons of bans in System > Intrusion Detection and Prevention show no user name that
  is not an account of the box: the log lines of each jail's filter, also
  with names that the line repeats or that have spaces, and lines of
  Nextcloud's log that are not valid JSON, and long lines that must not
  take long. `tests/fork/fail2ban-switch.py` (no box needed) checks the
  switch that turns fail2ban off for tests: the setting, starting and
  stopping the service (systemctl replaced by a stand-in), setup's exit
  code 4, the status checks' warning and the page's checkbox.
  `tests/fork/ban-list.py` (B220; no box needed) checks the
  banned addresses of that page with a stand-in for fail2ban-client and
  10,000 synthetic bans: the overview without per-ban lists (counters, the
  networks with the most banned addresses, the jails that ban the
  browser's own address, relay hints), the pages (newest ban first, paging,
  the filter by part of an address or jail and by network, bad parameters
  refused), the reasons of one address, fail2ban not running, and that
  each of these answers within a second or so; group admin runs it
  (`admin-ban-list-unit`), and `admin-fail2ban-bans` checks the pages and
  the refused parameters on the box. `tests/fork/nextcloud-throttle.py` (v78-r2604.4; no box
  needed) checks the reader of Nextcloud's throttle on a temporary
  database (no account of the box goes to it, no login name comes back),
  the stale failures with the protection off, and the takeover of values
  set in config.php by hand, per value. Group admin runs both
  (`admin-ban-reasons-masking`, `admin-nextcloud-throttle-unit`), so a
  certification run includes them.
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
  `/caldav` and `/webdav` answer PROPFIND; `nextcloud-mail-config-path`
  (after rc7): Roundcube's `/mail/config/` still answers 403, while a
  missing static page under `/<name>/mail/config/` answers 404 and a
  Nextcloud file below a folder `mail/config` is read through
  `/cloud/remote.php` and `/webdav` (B134); `web-hsts-admin`: the control
  panel (`/admin/`) and its assets send the same HSTS header as `/` of the
  box's name, or none when HSTS is off for it (B180), and
  `web-nginx-hsts-unit` runs `tests/fork/nginx-hsts.py` (described under **admin**).
* **activesync** (after rc7): `nextcloud-bruteforce-loopback`: 127.0.0.1
  is on Nextcloud's brute-force bypass list, and no entry is there twice
  (B121; a check of the list: Nextcloud counts no attempts for a listed
  address); `nextcloud-forwarded-for`: a failed login (a user that does not
  exist) from the box's public address through the `/webdav` proxy, which
  connects to Nextcloud from 127.0.0.1, is logged and counted by Nextcloud
  for that address, not for 127.0.0.1 (B121; its attempts are reset
  afterwards); `nextcloud-forwarded-for-local` (B213, with `--ssh`): a
  failed login from the box itself straight to
  `/cloud/remote.php/webdav/` with a forged `X-Forwarded-For` and a forged
  proof header is logged by Nextcloud as 127.0.0.1, and nothing is counted
  for the forged address; `zpush-sync`: an ActiveSync account as a phone sets it
  up (`tests/fork/eas.py`: Provision, FolderSync, Sync of all calendar and
  contact folders), and a marked event and two marked contacts put into
  alice's Nextcloud over DAV just before arrive, one of the cards with a
  name without `.vcf`, like Nextcloud's example contact `default` (B128);
  all are deleted again, and the test device is removed from Z-Push (with
  `--ssh`); `zpush-ping`: a Ping on the inbox with a heartbeat of 3600 s
  gets status 5 with the box's bound (60-3540 s) at once (no answer within
  90 s fails it: no bound; a Ping of 60 s of the device then ends the long
  one, so that no Ping is left), a Ping of 20 s completes with status 1 or
  2, and (with `--ssh`) nginx's `fastcgi_read_timeout` of every
  `/Microsoft-Server-ActiveSync` location (its own value, else the server's
  or the http block's, in nginx's time units) is at least a minute longer
  than that bound, so a phone's long Ping never ends with 504 (B129);
  `zpush-patches` (with `--ssh`): `/usr/local/lib/z-push/version` carries
  the checksum of the blocks of the checkout's `conf/zpush/z-push.patches`
  (`tools/patch_source.py --digest`), and
  `tools/patch_source.py --check` finds every change of it in the installed
  tree (B126, B128). Quick enough to run right after a setup run:
  `--only activesync`.
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
| v78-r2604.0 | 2026-10-27 | 80/80 ⁴ | 91/91 ⁴ | 91/91 ⁴ | 91/91 ⁴ | 92/92 (T5b from rc6 through rc7), 91/91 (from rc6) ⁴ |
| v78-r2604.1 | 2026-10-27 | not run ⁵ | not run | not run | not run | not run ⁵ |
| v78-r2604.2 | 2026-11-15 | 70/70 twice ⁶ | 81/81 (from v78) ⁶ | not run | 81/81 (from v78) ⁶ | 80/81 (T5b from v78-r2604.1) ⁶ |
| v78-r2604.3 | 2026-11-16 | 71/71, 72/72 ⁷ | not run | not run | not run | 81/82, 82/83 (T5b from v78-r2604.2) ⁷ |
| v78-r2604.4 | 2026-11-19 | 84/84 twice ⁸ | not run | not run | not run | 94/94, 95/95 (T5b from v78-r2604.3) ⁸ |
| v78-r2604.5 | 2026-11-23 | 105/105 twice ⁹ | 21/21, 110/110 ⁹ | 127/127 ⁹ | 21/21, 110/110 ⁹ | 127/127 four times (T5b from v78-r2604.4) ⁹ |

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

⁴ Repeated run after the fixes B135-B140 (see "v78-r2604.0" below): T1,
T2 and T5b Part A on `d06dc67` (T1's last setup run updated the box to
`e6920f2`), T3, T4 and T5b Part B on `e6920f2`. Between the two commits
only the grouping of a Let's Encrypt request (B140), which no lab box
runs, changed outside the tests and the documentation. T6, on the
Internet: fresh install of `d06dc67` with setup's network checks, 80/80
twice, then updated to `e6920f2`, 80/80. Every log audit, with the lists
of the final head and the lab's own lists, ended with 0 unknown classes.
The first run on the release commit `72c1661` had the same smoke counts,
except T6's first smoke run (73/80, the lab's NAT; see there), and found
B135 to B139.

⁵ No test matrix for this bug-fix release: a browser test of the control
panel (62/62) and the smoke test's API group (6/6) on a test box at the
branch (see "v78-r2604.1" below).

⁶ Runs of the branch before the release commit, from the lab's mirror (see
"v78-r2604.2" below): T1 at `b7bdae7` and again at `e63ffe1` with setup's
network checks; T2 at `e63ffe1`; T4 with the in-place tool of `8f0f910`
(the same as in `e63ffe1`) and setup at `e63ffe1`; T5b's update at
`b7bdae7`, its second and third setup runs at `e63ffe1`. T2 and T4 started
from upstream's v78 on 22.04, not from v74. T5b's one FAIL is the test's
own: its preparation had moved one of alice's mails to Spam and back,
which gives the mail a new UID and so a new POP3 UIDL (see the
counter-check below). After `e63ffe1` only the version strings,
`tools/expected-changes/`, the log audit's list and the documentation
changed.

⁷ Runs of the branch before the release commit, from the lab's mirror (see
"v78-r2604.3" below): T1 and T5b at `0d5d0f9` (the post-quantum change),
then again at `2a4024d` (with B175; T1's second setup run at `7c00f91`).
T5b's one FAIL in both runs is the test artefact of v78-r2604.2: it fails
the same way on the snapshot before any update (see the counter-check).
After `2a4024d` only the clean-up of two admin checks of the smoke test
after a failure, the version strings, `tools/expected-changes/` and the
documentation changed.

⁸ Runs of the branch before the release commit, from the lab's mirror (see
"v78-r2604.4" below): T1 at `d80a036` (install and a second setup run),
T5b at `e3df071` and again, from the same snapshot, at `f6e7f8b`. After
`f6e7f8b` only the log audit's list (`d80a036`), the version strings,
`tools/expected-changes/` and the documentation changed; T5b's log audit
was repeated with the list of `d80a036`.

⁹ Runs of the branches before the release commit, from the lab's mirror
(see "v78-r2604.5" below). T1: fresh installs at `fe02b21` and `bd17f24`
(all default groups; at `6bc2109`, before the account lock and the sending
limit, 110/110 with the api group and `--fail2ban`). T2 and T4 ran only at
`6bc2109` (a restricted and the full smoke test), before the account
lock, the sending limit and B222 to B225; T2's full run after a reboot
was 109/110 first (Nextcloud's SQLite lock, the known issue) and 110/110
when repeated. T3 at `65a3916` (21/21 at `6bc2109`); the in-place tool
changed after it by one line (`0415a5e`, B222). T5b at `65a3916`,
`a9eaff0`, `fe02b21` and `bd17f24`, each from the same snapshot of the
copy of a production box at the published v78-r2604.4, under client load
(the load's strict verdict was FAIL in each run, see there). After
`bd17f24` only the log audit's list (`84353e4`), an offline test helper of
`update-check.sh` (`04785d0`), the status warning of B226 (offline test only), the version strings,
`tools/expected-changes/` and the documentation changed.

Every FAIL in this table is one of the known differences below, except one
Nextcloud lock in rc4 T5 (see there), the first runs of rc6 T3 and T5b,
where the stricter comparison of rc6 found mails left in the snapshot (see
there), and T5b of v78-r2604.2 and v78-r2604.3, where the test's preparation
had moved a mail (see there).

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

### After rc7 (the branch before v78-r2604.0, 2026-10-26)

The fixes after rc7 were tested on branches of their own and then merged;
this run tested the merge of the two Z-Push branches (B128 to B130, the Ping
fix of both as B129), the one patch mechanism for Z-Push (B126, B128), B134
and the lists of `tools/update-check.sh`. Both boxes installed the branch
from the lab's repository.

| Run | Commit | Result |
|---|---|---|
| T1 (fresh 26.04) | `c269370` (setup code as at `67d0c10`: only test tools and docs changed after it) | install exit 0 in 1202 s; smoke 80/80 with `--fail2ban` (`zpush-sync` with a card without `.vcf`, `zpush-ping`, `zpush-patches`, `nextcloud-dav-proxy`, `nextcloud-mail-config-path`); the ActiveSync ban test from the peer: 10 correct logins no ban, 26 failed ones banned by `miab-zpush`; the peer unbanned. Log audit since the install: 0 unknown with the lists of the box and the lab's lists; with the lists of `67d0c10` and no lab list 6 unknown, all of the lab (4 classes of the ban test's deliberate wrong passwords, 2 of chronyd after the VM's rollback) |
| T5b (published rc7 → branch head, the production path) | `6174f6c` under client load, then `67d0c10` (second setup run) | the copy of the production box at rc6 (snapshot), 4 users whose first Nextcloud login was on rc6 (each with the example contact `default`), updated to the tag `v78-r2604.0-rc7` from GitHub (exit 0); on rc7 a new ActiveSync device of such a user got HTTP 500 (B128). The two hotpatches of the production box by hand: the ssh options of B125 in the checkout's `management/backup.py`, and the Ping hotfix (`conf/nginx-alldomains.conf` of the checkout, `local.conf`, Z-Push's `config.php`). Then the operator's steps: origin set to the repository of the branch, `update-check.sh before` and `backup` with the tool of rc7 (exit 0), both files put back with `git checkout --`, the update in a pty with the dialogs answered (exit 0, 203 s) under the client load of both instances (5 minutes before setup until 10 minutes after): both RESULT OK, `load-no-failed-login` PASS, no fail2ban `Found` of the load's addresses in the load window. `after`: "RESULT: OK - 0 unexpected, 8 expected changes" (`unreleased.txt`: `miab-zpush`, Z-Push's mark; `any.txt`: the commit as version, the status checks' version line, the nightly minute); its log audit named 1 class (Nextcloud's IMAP check cut by setup's Dovecot reload with curl's "Weird server reply", allowed in `67d0c10`). Smoke 92/92 with `--fail2ban`; the user with the example contact synced 7 contacts on a new device; 12 ActiveSync locations with 3660 s, the bound 3540, `2.7.7+patches-ca0fd9cddf8d4e39`; `mailcheck` RESULT OK. A second setup run to `67d0c10` (exit 0, 86 s) did not install Z-Push again (the same mark, `--check` passed; no inode or mtime was recorded in this run, see the run after the review below); `after` with the repo's smoke list (the smoke test ran in between) and the lab's list: "RESULT: OK - no unexpected change, no new log message class" (exit code 0). Log audit since the start of the run with `--smoke` and the lab's list: 0 unknown, 22 known from the baseline, 105 allowed |

The lab's list for T5b names 4 artefacts of the lab only: the push hook of the
production box's own web mail stack, whose endpoint is a stand-in in the
lab (404),
PHP-FPM's "seems busy" when the deliberately heavy client load starts, a
Nextcloud cron job of the snapshot marked as crashed after the rollback, and
Roundcube's race when the client load logs in to Roundcube with a new user
from two hosts in the same second.

Two earlier update tests of the same path found what the fixes of the run
changed: the first (`9bca224`) the copy of the new Z-Push tree from `/tmp`
(two requests with "Permission denied" and a PHP fatal error, B128) and the
first start of `miab-zpush` and the cut login of setup's Dovecot reload as
the Z-Push of rc7 answers it (new rules of the log audit for a setup run);
the second (`c269370`) Nextcloud's "Login denied" for a CardDAV login cut by
that reload, which `nextcloud.log` logged without the `[setup]` prefix
(`6174f6c`). A third one was not counted: the control panel's API answered
two of the four user additions of the lab script with HTTP 502 right after
the boot, and the client load then used accounts that did not exist.

#### Run after the review of the integration (`958f2b9`, `1fe42bc`)

The review of the integration found that setup configured the new Z-Push
tree only after it was moved in, rewrote the backends' config files with
`rm -f` and `cp` on every run, wrote the mark before `fixstates`, hashed
comments of the patch file into the mark, and allowed rc7's 401 for a cut
login in every setup run. The fixes (`2c4a500`, `958f2b9`) were tested on
both boxes, installed from the lab's repository.

| Run | Commit | Result |
|---|---|---|
| T1 (fresh 26.04) | `958f2b9` | install exit 0 in 1187 s; smoke 80/80 with `--fail2ban` (`zpush-patches`: `2.7.7+patches-bea3439da1b41c7a`, the `--digest` of the patch file, which a comment-only edit does not change); the ActiveSync ban test from the peer: 10 correct logins no ban, 26 failed ones banned by `miab-zpush`; the peer unbanned. Log audit since the install with the box's lists and the lab's lists: 0 unknown, 88 allowed |
| Edge cases of setup/zpush.sh on the T1 box | `958f2b9` | `setup/zpush.sh` on its own, 7 runs, while the box sent an authenticated ActiveSync OPTIONS and an unauthenticated Sync to itself about every half second: 120 answers 200, 121 answers 401, 11 answers 502 (the PHP-FPM restart of a run on its own), no 500; in `z-push-error.log` only the 401 of the unauthenticated requests. A rerun and a run after a comment added to the patch file left the tree alone (the same inodes and mtimes of the tree, `version`, `config.php`, the backends' and Autodiscover's config). The archive's own `version` file (`2.7.7`, the state of a run stopped after the move) and a patched file changed by hand (`--check`: "change 2 is not applied") each gave a fresh copy with the mark. With GitHub unreachable setup stopped in the download (exit 5), the old tree stayed in place and answered, and one `.z-push-new.*` directory was left; the next run with GitHub back removed it and installed Z-Push |
| T5b (published rc7 → branch head, the production path) | `958f2b9` under client load, then `1fe42bc` (second setup run) | as in the run above: the copy of the production box at rc6 with 4 users whose first Nextcloud login was on rc6, updated to the tag `v78-r2604.0-rc7` from GitHub (exit 0; a new ActiveSync device of such a user got HTTP 500), the two hotpatches by hand, then the operator's steps with the new GitHub check (`curl -fsSIL` of the Z-Push archive: OK), `update-check.sh before` and `backup` of rc7 (exit 0), both files put back (status clean), the update in a pty (exit 0, 175 s) under the client load of both instances (5 minutes before setup until 10 minutes after): both RESULT OK, `load-no-failed-login` PASS, no fail2ban `Found` of the load's addresses in the load window, no "Permission denied" or missing class in Z-Push's logs, no temporary directory left. `after`: "RESULT: OK - 0 unexpected, 8 expected changes"; it added `log-audit-allow-from-rc7.txt` by itself (the state before had no mark of Z-Push); its log audit named 1 class, fail2ban's "Unable to get failures in /var/log/mail.log" of setup's fail2ban reload under the load (allowed in a setup run from `1fe42bc`). Smoke 92/92 with `--fail2ban`; the user with the example contact synced 7 contacts on a new device; 12 ActiveSync locations with 3660 s, the bound 3540, `config.php` with `BackendCombined` and `LOGAUTHFAIL`, the backends' config files equal to the repository's; `mailcheck` RESULT OK. A second setup run to `1fe42bc` (exit 0, 94 s): the inodes and mtimes of the tree, its `version` and its config files were the same before and after, so Z-Push was not installed again and no config file was rewritten. `after` with the repo's smoke list and the lab's list: "RESULT: OK - no unexpected change, no new log message class" (exit code 0). Log audit since the start of the run with `--smoke`, `log-audit-allow-from-rc7.txt` and the lab's list: 0 unknown, 22 known from the baseline, 102 allowed |

### v78-r2604.0 (2026-10-27)

All runs installed or updated from the release tag `v78-r2604.0` on the
lab's mirror of the repository (`SOURCE` and `TAG` set to it; the tag was
not on GitHub yet), with the documented commands, on one hypervisor with an
HDD pool (at most two release upgrades at once). T6 ran on a box on the
Internet. The peer for port 25, the fail2ban attacks, the probe address of
`mailcheck` and the rsync target of `backup` was a second test box (at the
tag of the run, from the first run on). Every mail the testers sent to a
box themselves was a marked test mail.

#### First run (release commit `72c1661`)

| Run | Result |
|---|---|
| T1 (fresh 26.04) | install exit 0 in 2508 s; smoke 80/80 twice with `--fail2ban`; Munin 29/29; four second setup runs (non-interactive, interactive bootstrap, interactive `sudo mailinabox`, with a mail probe) exit 0 in 83 to 108 s; the ActiveSync ban test passed. The box showed its commit id as version, and each bootstrap run fetched again: the tag was a lightweight one (B135). Log audit: 0 unknown with the lab's lists |
| T2 (22.04 → fresh 26.04) | "All checks passed"; mail offline 46 min 39 s; smoke 30/30 and 91/91. Log audit of the new box: 4 unknown classes (fail2ban's first start of the mail.log jails in the migration's setup run); of the old box 1 (Dovecot 2.3's LMTP note at stop-old) |
| T3 (24.04 copy, in place) | "All checks passed"; mail offline 1 h 41 min; port 22 down about 18 min, key logins on 1022 meanwhile; smoke 91/91 twice; `after` "NOT JUDGED" (a release upgrade), `mailcheck` OK. Log audit: 0 unknown |
| T4 (22.04 → 24.04 → 26.04, in place) | "All checks passed"; mail offline 2 h 18 min; port 22 down 39 and 8.5 min, 1022 worked in every check but one (about 20 s); smoke 91/91. Log audit: 0 unknown (with one lab line for the lab's own favicon check) |
| T5b Part A (published rc6 → published rc7 → release, the production box's path) | smoke 92/92; the client load's verdict FAIL on both instances: one FolderSync each during setup's Dovecot reload answered without the mail folders (B137). `after`: 1 unexpected change, the lab's origin (the lab set its mirror as origin). Log audit: 8 unknown classes, all harmless or of the lab |
| T5b Part B (rc6 → release) | smoke 91/91; `after`: the same origin line. Log audit: 4 unknown classes, cron started again in the middle of setup by needrestart (B138) |
| T6 (fresh install on the Internet) | the first install stopped after 2 s: setup took Spamhaus' refusal of the public resolver for a DBL listing (B136); the second, with `SKIP_NETWORK_CHECKS=1`, passed. The first certificate run left out the box's own name (B140, its cause found in the repeated run); the MTA-STS record came only with a later DNS update (B139). Smoke three times: 73/80 first (the 7 fail2ban checks found the host's NAT address banned instead of the peer's, a lab artefact; the repeated run routed the peer directly), then 80/80 twice; mail to and from an external mailbox, 10/10 at mail-tester.com; log audit 10 unknown classes, all harmless or of the lab |

The defects were B135 to B140 (B140 from the repeated T6); the harmless
classes went into the allowlists with their reasons (`d06dc67`), the lab
artefacts into the lab's own lists.

#### Repeated run after the fixes

Commits: `d06dc67` has the fixes B135 to B139 (the tag re-created as an
annotated tag); `e6920f2` adds B140 (the grouping of the certificate
request in `management/ssl_certificates.py`, which only a box with Let's
Encrypt runs) and an allowlist line; `332bac5`, `a373c89` and `ca6780f` widen and add
allowlist lines; the commits after them change the documentation and
add one line to `tests/fork/log-audit-allow-from-rc7.txt` (Roundcube's
CardDAV migration race, see T5b Part A). bootstrap.sh compares only the tag's name with `git describe`, so a
box installed before the tag moved stayed at `d06dc67` on a later run of
it, unless the lab removed the local tag first (only possible because the
lab moved its unpublished tag). Every log audit below was run with the
allowlists of the final head and the lab's own lists.

| Run | Commit | Smoke | Mail offline / outage | SSH | Log audit |
|---|---|---|---|---|---|
| T1 (fresh 26.04) | install and runs A to C `d06dc67`, run D (an update) `e6920f2` | 80/80, 80/80 (`--fail2ban`) | runs A to C: ports 25, 587 and https never failed (port 993 not measured: the probe read it without TLS); run D (2 s probe): 25, 587, 993 and LMTP never failed, spampd 1 probe; 8 of 8 marked mails delivered | only the reboots (back after 18 to 21 s) | 0 unknown, 130 allowed |
| T2 (22.04 → fresh 26.04) | `d06dc67` | 30/30, 91/91 | 34 min 17 s (stop of the old box to the end of the checks); ports 25 and 587 after about 4 min, 993 after about 5.5 min | no outage | new box 0 unknown, 115 allowed; old box 0 unknown, 27 allowed |
| T3 (24.04 copy, in place) | `e6920f2` | 91/91, 91/91 | 1 h 19 min (the release upgrade 52 min, setup 21 min) | port 22 down 14 min in the release upgrade, key logins on 1022 meanwhile; sudo missing about 26 min; the reboot of the release upgrade about 2.5 min | 0 unknown, 14 known from the baseline, 499 allowed |
| T4 (22.04 → 24.04 → 26.04, in place) | `e6920f2` | 91/91 | 3 h 25 min in all, of it 1 h 34 min with the run stopped (see below); from the continued start to the end 1 h 51 min (release upgrades 53 and 38 min, setup 16 min) | port 22 down 30 and 9 min, key logins on 1022 in every check outside the reboots; sudo missing about 19 min | 0 unknown, 610 allowed |
| T5b Part A (rc6 → published rc7 → release under client load) | `d06dc67` (both setup runs) | 92/92 | update run of 227 s under load, a probe every 2 s: ports 25, 587, 993 and LMTP never failed, spampd 3 probes in a row (its restart); 13 of 13 probe mails delivered | 0 of 22 checks failed | 0 unknown, 22 known from the baseline, 131 allowed |
| T5b Part B (rc6 → release) | `e6920f2` | 91/91 | update run of 123 s: 25, 587, 993 and LMTP never failed, spampd 4 probes in two windows; 8 of 8 probe mails delivered | 0 of 14 checks failed | 0 unknown, 95 allowed |
| T6 (fresh install on the Internet, then an update) | install `d06dc67`, update to `e6920f2` | 80/80, 80/80, 80/80 (`--fail2ban`) | reboots: port 25 back after 20 to 22 s | reboots: back after 17 to 20 s | 0 unknown, 393 allowed (install to the end, `--internet`) |

The reboots: SSH back after 17 to 24 s in every scenario, no failed unit.
The peer was updated from `72c1661` to `e6920f2` at the end, as an operator
would (bootstrap in a pty, 133 s): ports 25, 587, 993 and LMTP never failed
a probe, spampd 1; 10 of 10 probe mails delivered; smoke `--only api` 6/6;
log audit 0 unknown.

| Run | Details |
|---|---|
| T1 (fresh 26.04) | install exit 0 in 1804 s. Munin's alert setting through the API: 29/29. ActiveSync of a new user: a card with and one without `.vcf` synced, a Ping on the contacts got status 1 after 20 s, and a card added during a 120 s Ping ended it with status 2 after 11 s (B129). Second setup runs A (non-interactive, 87 s), B (interactive bootstrap, 119 s) and C (interactive `sudo mailinabox`, 172 s): exit 0, no welcome dialog, nginx reloaded with the same main process, "Mail-in-a-Box Version: v78-r2604.0" and no new fetch (the annotated tag, B135); run D updated the box to `e6920f2` in 90 s. The ActiveSync ban test from the peer: 10 correct logins no ban, 26 failed ones banned by `miab-zpush`. B137 on the box (a harness that calls Z-Push's folder list): after `doveadm kick` of the session 6 folders, with a refused reconnect `StatusException` code 6. B138: a cron job (`sleep 300`) running in cron's control group, then setup; `systemctl restart cron.service` in the middle of setup (what needrestart does) failed with "Unit cron.service is masked" and cron stayed off; at the end cron was enabled and active and the marker gone. A setup run killed with SIGKILL right after the mask left the mask and the marker (dpkg clean); the next setup run removed both and started cron at its end |
| T2 (22.04 → fresh 26.04) | `--check`: no blockers. "All checks passed", setup 2023 s; old box vs new box: 4 users, 5 aliases, 4 mailboxes, 25 messages, 2 Sieve scripts, the DKIM, DNSSEC, TLS and backup keys, the Let's Encrypt account, Bayes 2/0, Nextcloud 2 accounts, 1 card, 1 event, all the same; DS records unchanged in 3 of 3 zones. Dovecot 2.4.2, Postfix 3.10.6, PHP 8.5.4, Nextcloud 34.0.5, Roundcube 1.7.5; no failed unit. Vacation: a new sender got a reply, a repeated one "discarded duplicate" (the duplicate database came over); port 25 from the peer delivered. `--check-old` right after the run and at the end: nothing started again. `git describe --always` on the box: `v78-r2604.0` (B135). `api-routes.py`: 66 routes, 63 documented operations, 0 problems. The migration's tmux client checks of the first run (detach, a client killed with SIGKILL, reattach) were not repeated: the tools did not change |
| T3 (24.04 copy, in place) | `update-check.sh before` and `backup` through `curl \| bash` from the tag (the stand-in Docker stack and volume): the first `backup` failed because the lab had emptied its directory on the rsync target, which v74's `backup.py` does not create (as in the first run; the in-place tool's preflight then refused to start: no backup younger than 24 h); after the lab recreated it, `backup` exit 0 in 42 s and `--check --keep-local` found no blockers. `--ssh-fallback-test`: admin key login and sudo on 1022, the non-admin refused there and accepted on 22, nothing left afterwards. The in-place run (`--keep-local --yes`, detached after 150 s): "All checks passed", 1 reboot; the before, local-ext and after hooks ran. Ubuntu 26.04.1, Dovecot 2.4.2, Postfix 3.10.6, PHP 8.5.4, Nextcloud 34.0.5; FTS with the old indexes (alice 6, carol 2 hits); `.dovecot.lda-dupes` a file again. The non-admin was refused on 1022 during the outage. `after`: changes not judged (24.04 → 26.04, as documented); its log audit named 8 classes, all now in the lists or of the lab (git's warning on the annotated tag, ntpd and Docker's link-local addresses, spamd's daily restart and cron's bounced mail to root@ on the v74 box, the first attempt's preflight error). `mailcheck` OK; `PROBE_ADDRESS` kept. `--cleanup-only` (the four calls of rc7) reported the packages without a source (not removed, by design), `--old-checkout` deleted `/mailinabox-v74` |
| T4 (22.04 → 24.04 → 26.04, in place) | `--ssh-fallback-test` with the group `admin` (admin on 1022 with sudo, the non-admin refused there and accepted on 22, the admin with a home of mode 0775 refused on both with the tool's warning, B115), the nested `Match` refused (B118), and again without the group (B100). The first start of the in-place run (`curl \| sudo bash -s -- --yes --no-backup-check`, detached after 150 s) stopped in its first release upgrade: do-release-upgrade found no new release (its download of the release list from Ubuntu failed for a moment; the tool's own check a minute before had found 24.04, and it found it again later). The tool stopped with mail offline and printed the command to continue; that command, run as an operator would, went through: "All checks passed", 2 reboots. The tmux clients: one killed with SIGKILL after 30 s did not stop the run, one stayed attached through the first release upgrade until its reboot, one through the second, and one attached after the second reboot ended 60 s after the end of the run, with no tmux server left (B72). The non-admin was refused on 1022 in both outages; afterwards no fallback process, listener, ufw rule or file. Vacation: a new sender got a reply, a repeated one "discarded duplicate"; port 25 from the peer delivered. Favicons: Roundcube and Nextcloud serve the fork's icon. `--check` before the run named only the 102 h old backup (the run used `--no-backup-check`) |
| T5b Part A (published rc6 → published rc7 → release) | the copy of the production box at rc6 with 4 users whose first Nextcloud login was on rc6 (each with the example contact); the published rc7 from GitHub (a new ActiveSync device of such a user got HTTP 500, B128), then only the hand change of B125 in `management/backup.py`. The operator's steps of README-fork.md: the GitHub check (OK), rc7's `update-check.sh before` and `backup` with the Docker stand-ins (exit 0; the copy on the peer verified by checksum), `git checkout -- management/backup.py` (status clean), the lab's origin, bootstrap `TAG=v78-r2604.0` in a pty under the client load of both instances (exit 0). The peer's load: RESULT OK; the box's own load: RESULT FAIL for one result, an ActiveSync request that rc7's Z-Push answered with HTTP 401 in the second of setup's Dovecot reload, before setup installed the new Z-Push (rc7's code; the new Z-Push answers such a moment with 503, B126; see the upgrade note); no failed-login line and no fail2ban `Found` of the load's addresses; no FolderSync without mail folders. The lab put the GitHub origin back before `after` (a box keeps it): "RESULT: OK - 0 unexpected, 8 expected changes" (`any.txt`, `v78-r2604.0.txt`, `log-audit-allow-from-rc7.txt` added by itself); its log audit named 2 classes, so its last line was "RESULT: look at the unexpected changes ... and the new log message classes" (exit code 1): the auth-worker note at the Dovecot reload (allowed from `75265dd`) and Roundcube's CardDAV migration race of the load's simultaneous first logins ("UNIQUE constraint failed: carddav_migrations.filename", then in the lab's list; in `log-audit-allow-from-rc7.txt`, which `after` adds by itself here, from the final head). Both classes, as the run recorded them, are accepted by the lists of the final head (checked with the log audit's matching rules). `mailcheck` OK. The example-contact user synced 7 contacts on a new device; Pings: heartbeat 3600 got status 5 with the bound 3540, a 20 s Ping status 1; 12 ActiveSync locations with 3660 s; Z-Push's mark `2.7.7+patches-0c49176f078e6dae` = `--digest`, `--check` passed. A second setup run (126 s) left the Z-Push tree alone (inodes, mtimes, mark) and nginx's main process; `after` again 0 unexpected changes, its log audit the auth-worker note again (exit code 1; allowed from `75265dd`) |
| T5b Part B (rc6 → release) | GitHub check OK, `before` and `backup` through `curl \| bash` from the tag (exit 0), bootstrap `TAG=v78-r2604.0` (exit 0); `after` with the GitHub origin: "RESULT: OK - 0 unexpected, 11 expected changes" (`any.txt`, `v78-r2604.0-rc7.txt`, `v78-r2604.0.txt`), its log audit 0 unknown, exit 0; `mailcheck` OK; 12 locations with 3660 s, the bound 3540, the mark = digest, the peer not banned |
| T6 (on the Internet) | below |

T6 ran on a VM with a public IPv4 address of a hosting provider (outbound
port 25 open, reverse DNS set to the box's name, IPv6 off), as the name
server of a delegated subdomain of a real domain (without a DS record at
the parent). The box was installed again for the repeated run (a new disk;
the same name and addresses as in the first run). The resolver of the fresh
machine was a public one.

* **Network checks (B136):** setup printed "Could not check whether the
  hostname ... is listed in the Spamhaus Domain Block List: Spamhaus
  answered 127.255.255.254, which is no listing" and the same for the
  address, and went on; port 25 open. Install exit 0 in 1599 s. Before,
  with the code of the release candidate, the same test on that box (the
  public resolver in a mount namespace) stopped as in the first run.
  Spamhaus' test entries still stop setup (a listed name and address).
* **Let's Encrypt (B139, B140):** with the code of `d06dc67` the first run
  requested only the five names of the zone (all seven names were selected
  before it), a second run the box's name and its `mta-sts.` name; right
  after it, DNS was updated ("updated DNS") and the status checks had no
  "MTA-STS policy is missing". After the update to `e6920f2`, with the
  certificates moved aside: one request with all seven names, the box's
  name first; afterwards nothing left to provision; 443, 465 and 993 served
  the new certificate (verified chain).
* **Version (B135):** the status checks and the API name `v78-r2604.0`;
  `git cat-file -t` says `tag`.
* **Public DNS** through several public resolvers: A, NS with glue, MX,
  SPF, DKIM, DMARC, `_mta-sts`, TLSA for 25 and 443, SSHFP, the SRV records
  of CalDAV and CardDAV, and the A records of the service names, as the box
  serves them, except the DKIM key at one resolver (9.9.9.9), which still
  held the key of the first install (see "External mail").
* **TLS:** 443, 25 and 587 with STARTTLS, 465, 993, 995 and 4190 verified
  with TLS 1.3; TLS 1.0 and 1.1 refused on 443, 993 and 465. DANE: the
  `3 1 1` record matched the key on 25 and 443.
* **Web:** the control panel and its API, Roundcube, Nextcloud's status
  and login, CalDAV and CardDAV (207), autoconfig, ActiveSync Autodiscover
  and OPTIONS, the MTA-STS policy (enforce), an ActiveSync Ping of 60 s.
  `/admin/` has no HSTS header (upstream, see "Open findings"); Outlook's
  Autodiscover schema gets 400 (Z-Push supports only the mobile one).
* **External mail:** to an external mailbox at a large German provider in
  16 s, over TLS that the box verified with the provider's DANE records;
  SPF, DMARC and one DKIM check passed there; a second DKIM check of the
  provider failed, because public resolvers still held the DKIM key of the
  first install under the same name (the record's TTL is a day; the lab
  installed the box again). From that mailbox to the box after 543 s
  (greylisting), over TLS 1.3, SPF, DKIM and DMARC pass, spam score -0.3,
  in the inbox. mail-tester.com: 10/10.
* **Smoke:** 80/80 three times with `--fail2ban` (the peer reached the box
  without the host's NAT, so that fail2ban banned the peer's address).
* **The update** to `e6920f2` (bootstrap in a pty, 96 s): `after` named 3
  unexpected changes, all of the lab: spampd not yet listening at `before`
  (the lab had restarted it right before), and the 127.0.1.1 line of
  `/etc/hosts`, which cloud-init had written with the VM's own name at a
  reboot because the lab had removed that line by hand before the install
  (setup fixed it at the update). Smoke 80/80, log audit since the update
  0 unknown.
* **Log audit** from the install to the end, `--internet`, the lists of
  the final head and the lab's list: 0 unknown, 393 allowed.

The lab's own lists of this run name: the client load's simultaneous first
Roundcube logins (T5b), the ban test's made-up user (T1), the B137 harness
(T1), the lab's favicon probe (T4, first run), and on the Internet box its
first boot with the network down (T6, first run).

#### Open findings of v78-r2604.0

* The update from rc7 or earlier: in the second of setup's Dovecot reload
  the old Z-Push can answer an ActiveSync request with 401 (seen once in
  the repeated T5b; upgrade note).
* `/admin/` without HSTS header; Roundcube's CardDAV migration race;
  Nextcloud's trust of `X-Forwarded-For` on every local connection (found
  in the review, B121); a CardDAV write during Nextcloud's cron run on SQLite (500); the start line
  of `upgrade-in-place-to-2604.sh --check` with another `SOURCE`
  (CHANGELOG-fork.md, "Planned").
* do-release-upgrade found no new release once in the repeated T4 (its
  download of the release list failed for a moment); the tool stopped with
  mail offline and the command to continue, which then ran through.

### v78-r2604.1 (2026-10-27)

A bug-fix release (B141 to B143), released without the test matrix T1 to
T6 by the decision of the maintainer. One test box: a fresh install of the
branch at `4ab5db4` from the lab's mirror, then updated with bootstrap.sh
(non-interactive) to `0f9efb8`, `6af973e` and `5001366` (each setup run
exit 0, 74 to 112 s).

| Test | Result |
|---|---|
| Browser test of the control panel (headless Chromium), at `5001366` | 62 PASS, 0 FAIL in 13 groups: every load path of B141 (a valid session in session and local storage, a session ended by age, by a restart of the daemon and by a logout, no connection, nginx's 502, the daemon stopped and busy, a 403 to `/me`, a non-admin whose saved copy claims `admin`, another user after an ended session, the back button after a 403, a link, the back button and the brand link while `/me` was pending), no API call and no menu before `/me` answered, no failed login logged by a reload, the menu bar hidden with scripts off, and "Remember me" with and without the tick (B142) |
| Smoke test, group `api`, at `5001366` | 6/6: `/me` answers `ok` with the privileges for a session key and `invalid` for a password, a wrong password and a key after the logout |

Not tested in this release: the scenarios T1 to T6 (install, migration,
in-place upgrades, the update test with client load, the box on the
Internet), an update from the tag `v78-r2604.0` to the tag `v78-r2604.1`
with `tools/update-check.sh` (so neither the fix of B143 nor the new log
audit rules ran on a box; both were checked against sample lines only), and
the release commit itself, which after `5001366` changes only the version
strings, `tools/expected-changes/`, the log audit's allowlist, the name of
the Python function behind `/me` in `management/daemon.py` (a rename of
the review, no change in behavior; checked with `py_compile` only) and the
documentation.

### v78-r2604.2 (2026-11-15)

A bug-fix release (B144 to B174). The runs installed or updated the branch
`fix/r2604.2` from the lab's mirror of the repository (`SOURCE` and `TAG`
set to it), on one hypervisor; the commits are in the table and in note ⁶
of the results. T2 and T4 started from upstream's v78 on Ubuntu 22.04: the
22.04 test VM with its test data, updated from v74 to v78 by v78's own
`setup/bootstrap.sh` (exit 0, "Your Mail-in-a-Box is running.", Nextcloud
27.1.11). T3 and T6 did not run. The peer for port 25, the probe address
of `mailcheck` and the rsync target of `backup` was the second test box.

| Run | Result |
|---|---|
| T1 (fresh 26.04, `b7bdae7`, `SKIP_NETWORK_CHECKS=1`) | install exit 0 in 1289 s; smoke 70/70; a second setup run at `9ba5f2b` exit 0 in 82 s, which changed nothing but the usual restarts. Checked: the component versions, the owners and modes of B147, the sury key without its package (B158), no leftover Roundcube directory (B157), no folder "spamassassin" after the smoke test's Spam moves (B155), Roundcube's `des_key` unchanged by the second run (B172). Roundcube's CardDAV sync fails in the lab on the box's self-signed certificate (cURL error 60); with that certificate trusted on the box, the address book synced, with no permission error in Roundcube's logs. Log audit: 0 unknown |
| T1 repeated (fresh 26.04, `e63ffe1`, with setup's network checks) | install exit 0 in 1479 s, with "Your Mail-in-a-Box is running."; the network checks run before setup installs its own resolver, so they asked the lab's public resolvers, Spamhaus refused them, and setup printed its two "could not check" notes and went on; no "Connection to ... succeeded!" line (B174); setup's start check (B147) did not stop the fresh box nor the second run; smoke 70/70; a second setup run exit 0 in 75 s, with the same `des_key`. Log audit: 0 unknown |
| T1n (on T1's box, `setup/network-checks.sh` of v78-r2604.1 and of `b7bdae7` under `set -euo pipefail`, through the box's own resolver) | not listed (NXDOMAIN): the old script ended with exit 1 and no output (B145 reproduced), the new one went on; a listed hostname and a listed IP address: both stop, the old one for the IP address without a message, the new one with Spamhaus' message; a public resolver that Spamhaus refuses: both go on; a resolver that does not answer: both stop, the new one with the port 25 message, the old one without a message |
| T2 (v78 on 22.04 → fresh 26.04, `e63ffe1`, `--from` an IPv6 address) | `--check` "No blockers found", its rsync probe over IPv6 worked (B167); Spamhaus through a public resolver and with port 53 blocked: "could not check", never "not listed" (B165); the migration exit 0 in 45 min, "All checks passed. The migration is finished."; mail offline 44 min 45 s; setup upgraded Nextcloud from 27.1.11 in 7 steps (2658 s); no `.rsync-partial` left (B164); `--check-old`: nothing of the old box started again. Smoke 81/81. Log audit of the new box: 1 unknown class, ssh's note in the migration log that it recorded the old box's host key (now in the list); of the old box: 0 unknown |
| T4 (v78 on 22.04 → 24.04 → 26.04 in place, tool of `8f0f910`, setup at `e63ffe1`) | "All checks passed. The upgrade is finished."; mail offline 1 h 54 min, 3 reboots (prepare-release needed one for a kernel update); `PROBE_ADDRESS` given in the environment was in `/etc/mailinabox.conf` after the reboots (B153); the watcher of the SSH server used `sshd`'s port: port 22 down 24 min, the fallback on 1022 opened and closed again, nothing of it left (B162). Smoke 81/81. Log audit: 19 unknown classes, all of the lab VM's boot (QEMU of the host, 4 CPUs) or harmless lines of the release upgrades from 22.04 that the list missed (now in the list; see CHANGELOG-fork.md) |
| T5b (the copy of the production box, updated to the published v78-r2604.1 → `b7bdae7`, then `e63ffe1`) | `update-check.sh before` and `backup` with the tool of v78-r2604.1 exit 0; the update in a pty, the dialogs answered with Enter, exit 0 in 160 s; `after`: 12 expected changes and 1 unexpected, the lab's origin in the version line (the update came from the lab's mirror); `mailcheck` OK. Smoke 80/81: `mig-pop3-uidl-alice` failed because the test's preparation had moved one of alice's mails to Spam and back (to create the folder of B155) after the manifest was written; counter-check: only that mail's UIDL differs, its new UID has the same UIDVALIDITY, Message-ID and Maildir file, the other 5 seeded mails match. Setup removed alice's folder "spamassassin" ("from 1 mailboxes", B155), and the smoke test's Spam moves created none; `des_key` identical in all 6 records (B172); owners and modes (B147); the sury key (B158); no leftover directories (B157); PHP-FPM active after every run (B149); `tools/dns_update` and `tools/web_update` exit 0 (B159); `management/backup.py` exit 0 and every service running afterwards (B148, success path only). A second and a third setup run at `e63ffe1` exit 0 in 85 and 78 s, which changed nothing but the nightly cron minute (B108). Log audit from the update to the backup, against the baseline of v78-r2604.1: 0 unknown |

Not tested in this release: T3 (in place from 24.04) and T6 (a box on the
Internet); the failure paths of B148, B151, B156, B160, B161, B168 and
B169 (the runs took the normal path of each); Roundcube's CardDAV sync
with a certificate that a client trusts by itself (only with the lab's
certificate added on T1's box); and the release commit itself, which
after `e63ffe1` changes only the version strings, `tools/expected-changes/`,
the log audit's list and the documentation. In the lab, the test machines
with an IPv6 address could reach port 25 on the Internet over IPv6 (the
status check "Outbound mail (SMTP port 25) is not blocked" passed through
it; the tests sent no mail there).

### v78-r2604.3 (2026-11-16)

A small release: the post-quantum key exchange in Postfix and B175. The
runs installed or updated the branch `fix/r2604.3` from the lab's mirror
of the repository (`SOURCE` and `TAG` set to it), on one hypervisor; the
commits are in the table and in note ⁷ of the results. T2, T3, T4 and T6
did not run: the release changes two Postfix parameters, the control
panel's login and the smoke test, not the migration or in-place tools.
The peer for port 25, the probe address of `mailcheck` and the rsync
target of `backup` was the second test box; it has no post-quantum group
in Postfix.

| Run | Result |
|---|---|
| T1 (fresh 26.04, `0d5d0f9`) | install exit 0 in 1268 s; smoke 71/71, among them `tls-key-exchange`: X25519MLKEM768, X25519 only, P-256 only and TLS 1.2 on ports 443, 993, 465, 587 and 25; `tls_eecdh_auto_curves` and `tls_ffdhe_auto_groups` empty and once each in main.cf, `postconf` without warnings; log audit 0 unknown classes; a second setup run exit 0. |
| T1 repeated (fresh 26.04, `2a4024d`, with setup's network checks) | install exit 0 in 1212 s with "Your Mail-in-a-Box is running." and setup's two "could not check" notes for Spamhaus; smoke 72/72, among them `admin-login-non-ascii` (a test user with umlauts in its password logs in to the control panel with the Authorization header in UTF-8 and in Latin-1, a wrong password with an umlaut is refused as wrong, and after a change to a password with '€' it logs in to the panel and by IMAP AUTHENTICATE PLAIN) and `tls-key-exchange`; the test passwords are nowhere in the smoke output; log audit 0 unknown classes; a second setup run at `7c00f91` exit 0 in 99 s, which did not rewrite main.cf, restart Postfix or change Roundcube's des_key. |
| T5b (the copy of the production box at v78-r2604.2, updated to `0d5d0f9`) | `update-check.sh before` and `backup` exit 0; the update non-interactive, exit 0 in 107 s; `after`: 7 expected changes and 1 unexpected, the lab's origin in the version line; `mailcheck` OK. Before the update the post-quantum handshakes on 465, 587 and 25 failed, after it all five ports negotiated X25519MLKEM768, and X25519, P-256 and TLS 1.2 still worked. Postfix as client to the peer: TLS 1.3 with X25519, one ServerHello, no HelloRetryRequest; its ClientHello grew from 508 to 1527 bytes (key shares for X25519MLKEM768 and X25519). Smoke 81/82: the FAIL is `mig-pop3-uidl-alice` (see the counter-check). |
| T5b repeated (the copy at the published v78-r2604.2, rebuilt from GitHub, updated to `2a4024d`) | `before` and `backup` exit 0; the update exit 0 in 114 s, without dialogs; `after`: 7 expected, 1 unexpected (the lab's origin); in /etc only main.cf (the two parameters) and the minute of the nightly job changed; `mailcheck` OK; log audit 0 unknown classes. Before the update `admin-login-non-ascii` failed with "'ascii' codec can't decode byte ..." (B175 reproduced), after it passed; FFDHE, DHE and CBC ciphers on port 25 still worked. Smoke 82/83: the FAIL is again `mig-pop3-uidl-alice`. |
| Counter-check of `mig-pop3-uidl-alice` | It fails the same way on the snapshot (v78-r2604.1) and on the rebuilt v78-r2604.2, before any update. The lab's preparation had moved one of alice's seeded mails to Spam and back (its IMAP session in mail.log, the file's new name in `dovecot-uidlist`), so the mail has UID 12 instead of 9, with the same Message-ID and Dovecot GUID, and so a new POP3 UIDL. With the lab's manifest corrected for that VM, `--only migrated` on a new snapshot of v78-r2604.2 passed 14/14; that snapshot is the start of later T5b runs. |

Not tested in this release: T2, T3, T4 and T6; Postfix's SMTP client
against a server that offers X25519MLKEM768 on the Internet (only against
the lab's peer without it, and against itself); the control panel's login
in a browser (only the smoke test's requests; the panel's new UTF-8
encoding of the credentials was compared with base64 of the UTF-8 bytes in
Node); `tools/update-check.sh` does not record the two Postfix parameters,
so its list of changes does not show the post-quantum change (see Planned
in CHANGELOG-fork.md); and the release commit itself, which after
`7c00f91` changes only the version strings, `tools/expected-changes/` and
the documentation.

### v78-r2604.4 (2026-11-19)

A small release: the reasons of bans, Nextcloud's throttle and the jails'
thresholds in the control panel, B176 (the pinned Nextcloud apps on an
existing box, calendar 6.6.6) and B177 (the backup copies of Nextcloud
root-only). The runs installed or updated the branch `fix/r2604.4` from
the lab's mirror of the repository, on one hypervisor; the commits are in
the table and in note ⁸ of the results. T2, T3, T4 and T6 did not run: the
release changes the control panel, Nextcloud's part of setup and the smoke
test, not the migration or in-place tools. The peer for port 25, the probe
address of `mailcheck` and the rsync target of `backup` was the second
test box.

The lab's names stopped resolving on the Internet during the runs (they
had relied on a public wildcard record that was removed); Postfix then
refused the lab's mail with "Sender address rejected: Domain not found".
Each test box and the peer got forward zones for the other boxes' names in
their local resolver (bind, with `validate-except` for these zones, which
the boxes sign without a DS record above them), set after each rollback
and kept by setup. A first `mailcheck` of T5b at `e3df071` failed that way
before the change, and the same `mailcheck` failed the same way on the
snapshot before any update; after the change it passed on the snapshot and
after the update.

| Run | Result |
|---|---|
| T1 (fresh 26.04, `08d7ff3`) | stopped with exit 100 in `apt-get install` of OpenDKIM: the Ubuntu archive did not answer at that time (from the test box, the hypervisor and another machine alike); not a result of the release. |
| T1 repeated (fresh 26.04, `d80a036`, with setup's network checks) | install exit 0 in 1108 s with "Your Mail-in-a-Box is running."; post-quantum key exchange in Postfix as in v78-r2604.3; calendar 6.6.6 and the other pinned versions; `owncloud-backup` 0700 root; smoke 84/84, among them all new checks (`admin-fail2ban-jail-values`, `admin-fail2ban-ban-reason`, `admin-ban-reasons-masking` with its 34 cases, `admin-nextcloud-throttle`, `-throttle-settings`, `-bypass-allowlist`, `-protection-off`, `-hand-set`, `-setup-no-drift`, `-app-versions`, `-backup-private`, `-throttle-unit`); log audit 0 unknown classes. A second setup run exit 0 in 94 s changed no Nextcloud app, made no backup, left the brute-force settings, fail2ban and Postfix alone; smoke again 84/84, log audit 0 unknown. (A smoke run in between used the smoke test of an older release by a mistake in the test script and does not count.) |
| T5b (the copy of the production box at v78-r2604.3, updated to `e3df071`) | `update-check.sh before` and `backup` exit 0; the update non-interactive, exit 0 in 189 s; `after`: 7 expected changes and 1 unexpected, the lab's origin in the version line; smoke 94/94. Setup updated calendar 6.6.5 to 6.6.6 (files, Nextcloud's app list, no upgrade pending), set `owncloud-backup` from 0755 to 0700 and made a backup whose database copy passed `PRAGMA integrity_check` and held the state before the upgrade; Nextcloud's brute-force settings, its bypass list, fail2ban's settings and all jails unchanged; second runs of the settings' setup steps changed nothing. The log audit found the new audit lines of the control panel and the failed logins of the new throttle checks without a rule in its list (fixed in `d80a036`); `mailcheck` failed because of the lab's names (see above). |
| T5b repeated (the same snapshot, updated to `f6e7f8b`) | after the resolver change: `mailcheck` on the snapshot OK; the update exit 0 in 85 s, without dialogs; `after`: 7 expected, 1 unexpected (the lab's origin); `mailcheck` OK; smoke 95/95; the same checks of the release as above passed; the TLS matrix and Postfix's TLS as a client the same before and after. Log audit with the list of `f6e7f8b`: the 5 classes above, with the list of `d80a036`: 0 unknown. |

Not tested in this release: T2, T3, T4 and T6; the opt-in smoke group
fail2ban (its new check of the reason of a real ban); the database copy of
the app update with a large Nextcloud database (only with the small
databases of the test boxes); the failure paths of the app update (a failed download, a failed
`occ upgrade`, a symbolic link in place of `owncloud-backup`) only on a
test box during development, not in these runs; the control panel's page
only in a headless browser at an earlier commit of the branch, and through
the API in the runs; and the release commit itself, which after `d80a036`
changes only the version strings, `tools/expected-changes/` and the
documentation.

### After v78-r2604.4: B210 to B213 (2026-11-21)

The hardening of the user database (B210), of the migration number
(B211), of the backup and DNS settings (B212) and of Nextcloud's forwarded
address (B213), on the branch `fix/r5-harden`. Only T5b ran: the copy of a
production box at v78-r2604.3, updated non-interactively with
`bootstrap.sh` and `TAG=<commit>` from the lab's mirror, with the second
test box as the peer for port 25 and the backup target. During every setup
run the peer sent a marked test mail (`X-Miab-Test: 1`) every 3 s over
port 25 to a mailbox of the box.

| Run | Result |
|---|---|
| T5b, `a985eb9` | setup stopped in web.sh: `nginx -t` refused the map with the proxy's secret ("could not build map_hash"); fixed in `0c41779`. Up to that point the user database was already root:root 0600, and all 48 test mails of the run were accepted. |
| T5b repeated, `0c41779` | exit 0 in 198 s, a second run exit 0; smoke 95 of 104: every request of the `/caldav`, `/carddav` and `/webdav` proxy got HTTP 500 ("fastcgi request length mismatch": the map's regular expression replaced the captures of the PHP location), so Z-Push's ActiveSync answered 503; fixed in `2c1c054` (an update of the same box to it: the groups web and activesync 16/16). |
| T5b final, `7b2b03d` (from the snapshot again) | the nightly backup on v78-r2604.3 first (exit 0). The update exit 0 in 207 s: `$STORAGE_ROOT/mail` root:root 755, `users.sqlite` root:root 0600 and still in the rollback journal mode, Roundcube's driver `mailinabox`, the migration record "15", `/etc/nginx/miab-nextcloud-proxy.conf` root:root 0600, `nginx -t` fine. 68 test mails, all accepted at once; 2 of them deferred for a few seconds inside the box (4.4.x, spampd restarting, as on every setup run before) and delivered on the next try. A second setup run exit 0 in 77 s changed no file's content (only the times of the files setup writes on every run), and the secret stayed. Smoke 104/104, among them `api-self-password` (the endpoint and Roundcube's Settings > Password), `nextcloud-forwarded-for` and `-local`, `zpush-sync`, `zpush-ping`, CalDAV, CardDAV and the backup checks. A failed CalDAV and CardDAV login from the peer was logged by Nextcloud under the peer's address. |
| B211 and B212 on that box | the storage user wrote "11" into `mailinabox.version`: setup stopped before any migration with the message, the DKIM key untouched; with the file removed by the storage user, setup took 15 from the record and wrote it back. The storage user replaced `backup/` with a directory of its own (another target and passphrase): the nightly backup stopped with the reason and wrote nothing to the other target, saving the settings in the control panel was refused, the status checks showed it; after the directory was put back, a backup exit 0. The same with `dns/`: the DNS update failed with the reason and the zones stayed unchanged. |
| Backup and restore | duplicity restored `mail/users.sqlite` from the backup after the update (root:root 0600, `integrity_check` ok) and `mail/` from the backup before it (root:www-data 775 and 0664, as v78-r2604.3 had them). The box with those older modes set back by hand and `mailinabox.version` removed by the storage user, updated to `cc934a9`: exit 0, the modes root's again, the version file written back as the storage user's; smoke 104/104. |
| Downgrade and back | bootstrap with `TAG=v78-r2604.4`: exit 0; the directory and the database root:www-data again, Roundcube's sql driver, the nginx file unused; a password change in Roundcube worked. Then back to `cc934a9`: exit 0, root's again, a password change in Roundcube through the new driver worked. Test mails of both runs all delivered. |

Log audit of the final run (since its first update): one unknown class,
the bounce of an automatic reply to the test mails' sender, which does not
exist on the peer (a lab artifact). Not tested: T1, T2, T3, T4, T6 (a
fresh install creates the database with mode 0600 and the record through
setup/start.sh; not run), the opt-in smoke group fail2ban, a user with
two-factor authentication in Roundcube (offline only).

### v78-r2604.5 (2026-11-23)

The release of the branch `fix/b178`: B178 to B182 (System Status, the
status mail, HSTS of the panel, the DNS checks), B200 to B204 (the tools),
B210 to B213 (the hardening), System > Notifications, the restart of
services only on a change, the Microsoft relay hint and the pruning of
Nextcloud's backup copies; and of the work merged after it on `fix/r5-ipp`
(head `04785d0`): the account lock (B126, a limit of different wrong
passwords per account for logins through the box's own services, from
`fix/r5-guard`), the sending limit with its emergency brake (B221), the
banned addresses page by page (B220), the switch that turns fail2ban off
for tests, and B222 to B225 (restarts during an update and at boot). The
rounds up to "After the review" ran on `fix/b178`; the runs of the added
work follow it. All runs installed or updated the branch from
the lab's mirror of the repository, on one hypervisor, with the second test
box as the peer for port 25, the probe address of `mailcheck`, the rsync
target of `backup` and the source of the attacks. During setup runs of T5b
the peer sent a marked test mail (`X-Miab-Test: 1`) every 3 s over port 25.

The first round ran every scenario on `e9f5641`. Its findings were fixed
in `223d83e` to `6bc2109` (B183 to B190, follow-ups of B154, B200 and
B204, the log audit's lists and normaliser); T1 to T5b ran again on
`6bc2109`, of the feature checks of T5b only the two that had failed. After them only the log audit's lists (`0abae8e`) and
this documentation changed. T6 did not run.

T7 is new: a test VM whose mail and DNS were kept inside the lab, with the
published v78-r2604.4, given a copy of the configuration of a
production box: its users, aliases, settings and custom DNS/web settings,
without mail, cloud data, keys or backups, all passwords replaced; then
updated to the commit under test as on the box. It runs no smoke test
(that would add users to the copy) and was rolled back to its clean
snapshot afterwards.

First round, `e9f5641`:

| Run | Result |
|---|---|
| T1 (fresh 26.04, network checks on) | install exit 0 in 2284 s with "Your Mail-in-a-Box is running." (a first attempt stopped with exit 100 in `apt-get update`: a PHP mirror in the middle of a sync, not the fork). `users.sqlite` root:root 0600, migration record 15, Roundcube's driver `mailinabox`, Dovecot's nodelay passdb, HSTS on `/admin/`, all panel assets, the Microsoft relay list accepted; smoke 110/110 (with `--provision`, the api group and `--fail2ban`), after a reboot 79/79. Two more setup runs exit 0 (98 s, 79 s); the second restarted only units whose files the lab had changed after the install (lab DNS, the test environment, the smoke test's DKIM tables), the third none. Log audit 0 unknown after classification; two rule gaps of the allowlist (a report recipient at another provider, fail2ban's note on `miab-munin`'s first match), fixed in the lists. |
| T2 (22.04 v78 with local Roundcube changes → fresh 26.04) | the documented `--check` and the documented migration stopped in the preflight check with "STORAGE_ROOT: unbound variable" (B185), with nothing changed; with the changes moved aside `--check` found no blockers. With the variable given from outside the migration passed: "All checks passed", mail offline 21 min 45 s, the counts and keys the same, the old Roundcube's changes kept and named, smoke 21/21 and 110/110 after a reboot. ssh's messages from the old box ended in "?" (follow-up of B154), the exit code file of the tmux window was 0644 until the next call (follow-up of B204). |
| T3 (the 24.04 copy of a production box, in place, `--keep-local`) | `TAG=<commit id>` could not be cloned (B188); with `TAG=` the branch at the same commit: "All checks passed", mail offline 1 h 31 min, the push hook, full-text search with the old indexes, the Docker stand-in and the hooks; `mailcheck` OK; smoke 21/21 (19/21 before an unmarked lab mail of the snapshot was removed). The plugin that the documented hook copied back from `old-roundcube/` could not be read by the web server, and Roundcube logged an error on every request (B186); `update-check.sh after` named the old release's spamd line as new (B187). |
| T4 (22.04 v78 → 24.04 → 26.04, in place) | "All checks passed", mail offline 2 h 09 min, 3 reboots, the fallback SSH served every probe while port 22 was down (29/29, 66/66 in total); B200's report and `--ack-local`, B161's messages after a failed `--redo-from`, Dovecot's nodelay; smoke 21/21 and 110/110. When mail went offline, the mask of one apt timer started the other one's missed run: unattended-upgrade installed a kernel after the system archive had been made (B190). |
| T5b (the copy of a production box at the published v78-r2604.4, the operator's update) | `update-check.sh before` and `backup` exit 0; the update interactive in a pty under client load (both instances RESULT OK, no failed login of the load, `load-no-failed-login` PASS), exit 0 in 119 s with the end line; 289 of 289 test mails accepted, 4 deferred inside the box during the documented restarts and delivered, none lost; Dovecot's and PHP-FPM's reloads cut a few IDLE and ActiveSync connections, as documented. `after`: "CHANGED", the lab's origin and the new drop-in of spampd's restart record, which the list of expected changes lacked (fixed in `223d83e`); `mailcheck` OK; smoke 122/122. The modes of B210, the record of B211, Roundcube's driver, `/me/password` 404 from outside, HSTS, the relay list, B126's nodelay (a wrong ActiveSync password answered in 0.035 s instead of 13.5 to 26 s), the pruning of Nextcloud's backup copies (the 3 newest and those of 14 days kept, other names left), the restarts on the first run, none on the second (75 s) and third run, sa-update's restart of spampd recorded through the drop-in; B202 (a local tag of the release name: the old bootstrap was fooled, the new one fetched); two downgrades to v78-r2604.4 and back, a reboot on each side, Roundcube's password change with both drivers; smoke at the end 110/110. Setup printed "database is locked" in Nextcloud's step under the load (B189). |
| T5b features (the same box after the update) | in a headless browser: System Status with "show more" (B178), the TLS and External DNS pages, System > Notifications (a recipient at another provider, the test mail, the Munin select), Munin in a new tab, Intrusion Detection and Prevention with the Microsoft hint, its dialog and the allowlist entry removed again; no console error on these pages. The report recipient got the test mail and a change mail with whole checks (B179); a broken `admin_mail` written by hand was replaced by the standard address with a warning. Roundcube's password change (right and wrong current password, the two-factor hint; the limiter's 403 and 429 answered the harness's own requests to the management daemon, after which Roundcube showed the limiter's message), `users.sqlite` unreadable for www-data, the storage user's swaps of `mail/` and a higher `mailinabox.version` stopped by setup before any change, B213, B182 against a refusing and a silent server; smoke 121/121. Found: with a `dns/` of the storage user's own the status checks ended with a traceback and the panel's status answered HTTP 500 (B183); a status change mail went out every night with nc's "succeeded!" line (B184, also in v78-r2604.4). |
| T7 (the configuration copy, isolated) | the published v78-r2604.4 installed (exit 0, 1492 s), the data imported, setup with it exit 0, `before` exit 0, the update exit 0 in 82 s with the end line, two more setup runs exit 0 with no restart and no changed file but the nightly job's minute (406 files compared); status checks over all domains without a traceback; System > Notifications as the aliases say; all mailboxes, aliases and domains in Postfix's and Dovecot's maps; 14 logins over IMAP, SMTP, webmail and ActiveSync; Roundcube's password change through the new driver; `users.sqlite` root:root 0600; nginx and the custom proxy; the panel in a browser without errors. `after`: the same missing drop-in as in T5b (and the lab's origin). The lab's DNS answered for the box's zones, but the DS lookups of the zone names went to the public parent zones until the lab rejected outgoing DNS (a gap of the harness, closed during the run; only the public zone names left the lab). |

Second round, `6bc2109`:

| Run | Result |
|---|---|
| T5b (the operator's update again, from the start snapshot at the published v78-r2604.4) | `before` and `backup` exit 0 (the copy verified on the rsync target); the update interactive under client load, exit 0 in 123 s with the end line; both load instances RESULT OK with no failed login (0 auth, 0 throttled results); 289 of 289 test mails accepted; the 2 s probe never found ports 25, 587, 993 or LMTP down, spampd 6 s at its restart; setup's output without "database is locked" (B189). `after`, with the published origin as a production box has it: "RESULT: OK - 0 unexpected, 13 expected changes, 2 newly recorded (not judged)", the drop-in accepted; its log audit named new classes of the client load (see below), so it exited 1; `mailcheck` OK. Smoke 122/122 with `--fail2ban`, the api group and `load-no-failed-login`. A second run exit 0 in 87 s: every unit kept its main process and invocation, 36 of 36 mails. B183: with a `dns/` of the storage user's own the status checks exit 0 without a traceback, the panel's status HTTP 200, the DS records shown with "Public Key: not shown" and the reason; the DNS update refused (exit 22), the zones unchanged; restored, the keys shown again. B184: `--show-changes` without a change printed 0 bytes, also through `2>&1`. Reboot: running, no failed unit; the run after it exit 0 in 104 s restarted each restart-on-change unit once (as documented), 41 of 41 mails. Smoke 110/110 at the end. |
| T2 (as in the first round, both machines from their snapshots) | the documented `--check` with `TAG=<full commit id>` named the 3 local Roundcube changes and found no blockers, exit 0 (B185). The documented migration exit 0, "All checks passed"; mail offline 43 min (setup 43 min, with three other runs on the same disks), the new box answered on port 25 after 8.5 min. No "?" at the end of ssh's messages and no escape byte in `migrate.log` (29 banner lines of the old box filtered, B154); no entry of `/root/migration` with group or other bits, the exit code file 0600 (B204); the kept plugin 0755/0644, copied back with `cp -a` and readable by www-data, no load error in Roundcube, `--redo-from verify` exit 0 with only the settings open (B186). Smoke 21/21; after a reboot 109/110: `zpush-sync` got HTTP 500 for a calendar PUT while the first Nextcloud cron jobs after the 7 upgrade steps held the SQLite lock (the known issue), and 110/110 when run again. Log audit of the new box 0 unknown (112 allowed); of the old box one class, `postqueue`'s note at `--check-old` (rule added in `0abae8e`). The migration itself ran with `TAG=` the branch at the same commit; the tool's clone of the full commit id was checked on the new box. |
| T1 (fresh 26.04, network checks on) | bootstrap with `TAG=<full commit id>` (B188): exit 0 in 2345 s with the end line, the checkout at `6bc2109`; 44 of 44 checks; smoke 110/110 (`--provision`, the api group, `--fail2ban`); a second run in a pty exit 0 in 96 s (it restarted the same four units as the first round's second run, after the same lab steps; not traced again); after a reboot 44 of 44 checks and smoke 79/79; log audit 0 unknown, 115 allowed. |
| T3 (the 24.04 copy of a production box, as in the first round, from its snapshot) | `before` and `backup` with the Docker stand-in exit 0 (verified on the rsync target), `--ssh-fallback-test` clean, `--check --keep-local` with `TAG=<full commit id>`: no blockers, the proposed start command with that `TAG`. Started with `TAG=<full commit id>` (B188): cloned, "All checks passed", mail offline 1 h 33 min; the plugin brought back by the documented hook root:root 0755/0644 and loaded, no error in Roundcube's log, `old-roundcube/` 0700 with its `config.inc.php` 0600 (B186). The lab's setting had been put after the closing `?>` of the old configuration, which the report named as "text outside of PHP" (a lab artefact of the first round too). `after`: "RESULT: NOT JUDGED" (exit 3, the documented end of a release change), its log audit with the old-box list (B187) 0 unknown; `mailcheck` OK; `--cleanup-only` (also with `--old-checkout`) exit 0; reboot; smoke 21/21; log audit since the start 0 unknown (516 allowed, 16 known from the baseline). |
| T4 (22.04 v78 seeded → 24.04 → 26.04, in place, from its snapshot) | `--check --no-backup-check` with `TAG=<full commit id>`: no blockers, the start command with that `TAG`; started with it (B188): cloned, "All checks passed", mail offline 2 h 02 min, 3 reboots, setup's end line. When mail went offline both apt timers only logged "Unit to trigger vanished", and `history.log` has no run of unattended-upgrade after the downtime began, only the tool's own package steps (B190). The plugin brought back by the documented hook root:root 0755/0644, readable by www-data, no load error; verify named only the two settings (B186). Reboot: SSH back after 22 s, no failed unit; smoke 21/21 (`--only migrated,api`) and 110/110; log audit since the start with the old-box list 0 unknown, 650 allowed. |

Log audit: each class of every run was classified from its log lines.
The harmless ones got rules in `tests/fork/log-audit-allow*.txt` (in
`ff42e07` and `0abae8e`; `log-audit.sh` also masks the local part of a
mailbox path under the box's own name). Left visible on purpose, all
before or outside the setup runs and with the lab's client load: Nextcloud's
"database is locked" with its ActiveSync and nginx follow-ups (the known
issue of Nextcloud on SQLite), the continuation lines and two variants
("no column named flags", "no such column: active") of the CardDAV
plugin's migration race at two first webmail logins of new users in the
same second (its main lines have rules; README-fork.md names the race for
the update from rc7), Z-Push's loop detection after a Sync that setup's
PHP-FPM reload cut, and three classes of spampd ("Use of uninitialized
value" twice, `process_request` with "Broken pipe") from the second round's
T5b: `update-check.sh backup` stops Postfix for its copy, and mails that
arrive meanwhile end like this, which happens on any box that receives mail
during that backup, not only in the lab.

Not tested in this release: T6 (no box on the Internet); Let's Encrypt
(the TLS page only shown); real Microsoft servers (the relay hint with a
ban set by hand); B181 with a real overlong domain (only
`tests/fork/status-dns.py` through the smoke test); outbound port 25 to
the Internet and the blacklist checks (the lab's resolvers and forward
zones answer, the Spamhaus checks say "could not check"); the in-place
runs with `--no-backup-check` (T4) and the migration with
`--skip-network-checks`; T7 with `SKIP_NETWORK_CHECKS`, without smoke test,
backup, `mailcheck`, client load or reboot; client load only in T5b;
`update-check.sh backup` with Docker volumes only in T3; a downgrade with
the old bootstrap from the mirror's tag (from GitHub's, same commit); a
bootstrap with a tag that the source does not have; the second round did
not repeat the browser checks, the storage user's swaps of `mail/` and of
`mailinabox.version`, B202, the downgrades, T4's `--ssh-fallback-test`
and B161's hook, nor T1's third setup run (the code there did not change);
T7 was not repeated: of its findings only the missing line of the list of
expected changes was fixed, and `after` in the second T5b checked that
line on the same path, without the data of the production box. Also not
run: the log audit of the first round's T5b had no journal for about 25
minutes of the run (the setup marks of that time were gone, see "Planned"
in CHANGELOG-fork.md), so 18 classes were judged only from their lines;
T4's check of a failed login on the fallback port from an account that is
not an administrator; a migration of a box without local Roundcube changes
(both T2 runs had them), and T2's detach, kill and reattach of the tmux
client was not repeated; no run on a box brought back a plugin that the
web server cannot read, so phase verify's warning about it (B186) was
checked only offline, where the tools' call of it was not covered (see
"After the review" below).

After the review, `b0242e9` (B186's verify read its list of plugin
directories twice, B191, bootstrap.sh's message for a failed first clone,
B188): the offline tests pass (22), and the cases added for B186, B191
and B188 fail on the commits before. On the copy of a production box from
its start snapshot at the published v78-r2604.4: `update-check.sh before`
exit 0; the update to `b0242e9` non-interactive (`TAG=<full commit id>`)
exit 0 in 86 s with the end line, 37 of 37 marked mails accepted during
it; the keys' hash in the zone files unchanged by the update; a forced DNS
update exit 0, all 3 zones signed again, `ldns-verify-zone` "Zone is
verified and complete" for each, nsd answers with DNSKEY and RRSIG. B191:
with `custom.yaml` read through the checked `dns/` and then `dns/` swapped
by the storage user for one of its own whose `.conf` names
`../../etc/logrotate.d/...`, the DNS update was refused with "... is not a
directory of root's own", nothing was written to `/etc/logrotate.d`, the
zones stayed unchanged; with that name in root's own `.conf` the update
was refused (exit 22, "names no KSK key file"), the zones unchanged;
restored, the update exit 0 with the same hash. B186: phase verify of both
installed tools, called as the tools call it, named a local plugin of mode
0700/0600 (exit 0, `local-changes.json` written) and nothing once it was
readable. B188: bootstrap.sh's first clone with a short commit id and an
unknown tag exit 1 with the message (and the hint for the short id), no
directory left. Smoke 121/121 with `--fail2ban`; log audit since `before`
0 unknown (76 allowed). Not run after the review: T1 to T4, `after` and
`mailcheck`, client load, a reboot; the in-place and migration tools'
phase verify ran on its own, not in a whole run of a tool.

#### The account lock (B126)

The account lock counts the different wrong passwords of each account in
the logins that the box's own services make to Dovecot (webmail,
ActiveSync and Autodiscover, CalDAV and CardDAV through Nextcloud) and
refuses these logins of the account at the limit (30 in 30 minutes by
default); it replaces the passdb without delay that the rounds above
tested. Its runs on `fix/r5-guard` updated the copy of a production box
from the published v78-r2604.4 non-interactively (`TAG=<full commit id>`)
or installed a fresh box (T1).

| Run | Result |
|---|---|
| T5b, `45e46f6` (the branch merged with `fix/b178`) | the update exit 0 in 103 s with the end line, 42 of 42 marked mails accepted. 100 logins by IMAP from the box itself with the same wrong password, and 50 by ActiveSync and 50 by Autodiscover from the peer: the account's count stayed 1, and the right password went through at once (IMAP 0.03 s). 30 different wrong passwords locked the account: from the box itself its right password got "Too many failed logins", ActiveSync and Autodiscover 503 and webmail 401, while IMAP from the peer and the logins of another account went through. The report mail, the list under System > Intrusion Protection, a limit of 40 (applied without a restart of Dovecot) and the unlock worked, through the API and in a headless browser (7/7). Smoke 122/123: `api-read-only` had no shape check for the new `GET /system/auth-guard` (added in `cbedcce`). A first smoke run used the smoke test of a later commit by a mistake of the harness and does not count. |
| T1 (fresh 26.04, `45e46f6`) | install exit 0 in 1132 s with the end line; 55 of 55 checks after the install, after a third setup run and after a reboot, which recreated the state directory `/run/miab-auth-guard` (0700, dovecot); the second and third setup runs exit 0. Smoke 111/112 (`--fail2ban`) and, after the reboot, 16/17 (`--only login,api`), both with the same `api-read-only` FAIL; log audit 7 unknown classes, 0 with 4 proposed rules (added to the list in `cbedcce`). |
| T5b, `cbedcce` (after the fixes of the security review, `bb37faf` to `cbedcce`) | bootstrap.sh first refused the update in 1 s, as the box's checkout had GitHub as its origin, not the given source (its documented guard; nothing changed); with the origin set as its message says: exit 0 in 126 s with the end line; 62 marked mails, none lost, 4 of them deferred inside the box during spampd's restart and delivered after a `postqueue -f`. The same wrong password 100 times each by IMAP and ActiveSync and 20 times by Autodiscover from the box itself, and 100 + 15 times by ActiveSync and Autodiscover from the peer (7 s apart, as `miab-zpush` bans at 20 in 120 s): the count stayed 1, the right password went through at once. Client load on a test account for 10 minutes, once with 25 different wrong passwords counted before: 0 refused or failed of 11920 and of 12156 IMAP logins, both load verdicts OK. 600 made-up account names: 501 failed, then 99 refused once the pool of 500 was full; the counts of the real accounts unchanged. The cron job mailed the lock. A second setup run exit 0 in 66 s: Dovecot's main process unchanged, no reload. Reboot: the state directory recreated empty (a reboot ends a lock, as documented); lock, refusal and unlock work. Browser 7/7. Smoke 123/123; log audit 14 new classes: 13 from the deliberate wrong passwords and locks (lab), one of the product, the audit line of an unlock (added in `475c99d`). Then updated to `5987f18` (bursts count against 4 windows): exit 0 in 80 s, 37 of 37 mails, smoke 112/112, log audit one class, the full pool of the test (lab). |

The lock test series ran on `475c99d` (with the setting of the number of
windows a burst counts against, `dd4adef`): everyday use, attacks and
operation on the copy of a production box, updated from v78-r2604.4 (exit
0 in 131 s, 48 of 48 mails),
with the peer as the outside world (phones, calendars, mail programs, an
attacker) and a third test box as a second attacker. A refusal in
everyday use would have stopped the release.

| Part | Result |
|---|---|
| Everyday use | 60 minutes on one account (2 ActiveSync devices, webmail in 3 tabs with mail sent through it, CalDAV and CardDAV with parallel requests, Nextcloud, IMAP and SMTP from the peer): 14572 ok results, 35 ActiveSync disconnects, the account's count 0. 25 minutes on 5 accounts: 17579 ok results, 77 ActiveSync disconnects, and in the first minute 7 Nextcloud web logins and one webmail login of the new accounts answered with HTTP 500 and 401; all counts 0. A phone with an old password, tried 153 times in 2 hours while the account's other devices used the right one (10141 ok results): count 1, never refused. A password change in webmail: every device with the old password failed, with the new one it got in at once; count 1. 10 different wrong passwords in an hour: not locked, the right one went through each time. Wrong passwords by IMAP and SMTP from the peer: fail2ban banned the peer as before (`miab-slow-dovecot`, `postfix-sasl`, the same on v78-r2604.4), the lock counted nothing. The box's own jobs, run by hand, left no count. No login of everyday use was refused. |
| Attacks | A slow attack through ActiveSync and webmail from the third test box at the default window: locked at the 30th different wrong password (counted over 6 minutes), the report mail 4 minutes later; the lock ended by itself 1 to 2 s after its expected end (probed every 15 s); a second attack ended with Unlock in the browser (10/10). A distributed attack from 7 addresses: locked at 30 as well. The following locks and the full pool came in one report mail, an hour after the first. Bursts of 100 parallel wrong passwords from the box itself with a window of 1 minute: refused for 60, 121, 181 and 181 s with 1, 2, 3 and 4 windows (the rule: the smaller of the setting and 100/30 windows), another account 10 of 10 logins during each burst (at most 0.62 s). Repeated bursts got more through than the limit: 100 every 30 s for 6 minutes 33.3 checked guesses a minute, 59 every 30 s for 10 minutes 32.4, against 30 a window; the texts had promised 30 and now say what bursts get through (`147b4cb`). 600 made-up names: 501 failed, 99 refused when the pool was full, a real account 40 of 40 logins during it. |
| Operation | Settings changed live (limit 40, window 2 minutes, 3 windows) without a restart of Dovecot: the 40th wrong password locked; invalid values and a name not on the list refused with 400 and a message. A lock outlasted a restart of Dovecot and a setup run (exit 0 in 97 s) and ended at a reboot (as documented); an added account was on the list at once, a removed one gone. Downgrade to v78-r2604.4: exit 0 in 85 s, 32 of 32 mails, right and wrong logins from the box and the peer as on v78-r2604.4; its log audit named 4 classes, the deliberate wrong SMTP passwords from the peer repeated there (lab). The update back: exit 0 in 92 s, 36 of 36 mails, lock and unlock work. A fresh install on the third test box: exit 0 in 1218 s, smoke 112/112 (`--fail2ban`), a second setup run exit 0, after a reboot smoke 81/81 (`--only login,admin,api,web,mail`), log audit 0 unknown; the lab's T1 check "doveconf has nodelay" failed, as it tests the passdb of `fix/b178` that the lock replaced (an outdated check of the harness). |
| End | smoke 123/123 (all default groups and `--fail2ban`); log audit 26 new classes, all in the series' lab list, 0 unknown with it. |

#### The hardening (B210 to B213)

The hardening ran on `fix/r5-harden` before the first round of this
release, see "After v78-r2604.4: B210 to B213" above (the final run at
`7b2b03d` and the update to `cc934a9`, smoke 104/104 each), and in every
run of the release since.

#### The sending limit (B221), the ban list (B220) and the fail2ban switch

These runs on `fix/r5-ipp` include the account lock (`475c99d`). No mail
was to leave the lab: on the test boxes Postfix sent all mail for other
domains to the peer, and a firewall rule dropped TCP 25, 465 and 587 to
every other address (IPv4 and IPv6); the lab checked both before the
first mail and after every setup run, reboot and downgrade, and compared
the mails of each flood at the peer with the box's log. All floods and
brakes ran on the copy of a production box, updated from its snapshot at
the published v78-r2604.4.

First run, `f1c367e`:

| Run | Result |
|---|---|
| Update | a first attempt stopped with exit 100 in `apt-get` (a mirror of the PHP packages in the middle of a sync, not the fork), and the lab's first transport rule had also sent the box's local mail to the peer (inside the lab); from the snapshot again: `update-check.sh before` and `backup` exit 0, the update exit 0 in 154 s with the end line, 55 of 55 mails, `after` "RESULT: OK - 0 unexpected, 20 expected changes", `mailcheck` OK, the services, ports, milters and cron job of the limit in place (18 of 18 checks). A second setup run exit 0 in 101 s: no restart of the two services, no content changed. |
| Everyday use | 60 minutes on 3 accounts with mail programs on 587 and 465, webmail, ActiveSync, CalDAV, CardDAV and Nextcloud: 116 mails to 976 recipients (up to 20 a mail, attachments up to 3 MB) and 32 to themselves, 0 held, the brake never on, the peer got every mail, at most 0.7 s after it was sent. The box's own mail (status checks, reports, the cron jobs, mail to root, Nextcloud's welcome mail, a Sieve redirect): none held. 500 incoming mails from the peer in 15.4 s (100 to an alias that forwards to the peer): not counted, no brake; spampd could not keep up on the 2-vCPU test box, and 12 of them were deferred and delivered later. A mail to 30 recipients went out at once, and so did one to 31 (the changelog then said that it sets off the brake; the text was wrong); two accounts with 20 recipients each in the same second set off the brake (as documented); the administrator's mail of that brake came only with the cron job, 3.5 minutes later. |
| Floods | FAIL: a flood at or below 30 mails a second never set off the brake: 1000 mails by SMTP on 587 at 23 a second (at most 32 in one second), 500 on 465 at 29.5, 300 by webmail at about 2 and 80 with 10 recipients each, 300 by ActiveSync at about 3, 300 by sendmail (pickup took 6.8 a second) and 300 by SMTP to 127.0.0.1:25 at 29 a second: all went out, 0 held. At that rate 10,000 mails leave in about 7 minutes. Fixed by a second, long limit (`759b0e2`; 1000 mails an hour by default since `4ec91ef`). With 5 recipients a mail the brake came on at once: of 300 mails by SMTP 6 (30 recipients) went out, the brake came on in the same second, the administrator's mail 1 s later, 294 held, nothing lost. |
| The brake | The slow release let out 10.0 recipients a minute on average, the senders in turn, but up to 12 in a calendar minute and 15 in a sliding one (a token bucket; the changelog now says so); 276 held mails deleted in the panel never reached the peer; with the quiet time set to 2 minutes the brake ended by itself, as nothing was held. "Release all" and "Release now" let the held mail out at once, past the limit, as the panel says. A flood of ActiveSync mail with 40 recipients each got 3 mails (120 recipients) out within 1 s: a mail over the limit went out before the brake's new bucket was charged (fixed in `759b0e2` and `689e333`: nothing goes out in the brake's first period). In stop mode nothing was released for 2 minutes until "End the brake"; meanwhile the box's own mail through sendmail (mail to root, Nextcloud's mail, a Sieve redirect) was held with the rest, only the reports by SMTP to the administrator passed (the reports have a listener of their own since `aab263b`). A brake with 188 held mails outlasted restarts of the two services and of Postfix, a setup run (exit 0 in 132 s) and a reboot: the hold queue, the list and the brake stayed in step, the slow release went on, nothing was lost (200 = 12 out before the brake + 16 released + 172 deleted). |
| Failure cases | With the release service stopped, mail over the limit waited up to 20 s or got `451 4.7.1` at once, as designed. FAIL: a sendmail mail that the milter had deferred meanwhile was held when the service came back and stayed in the hold queue, on no list and not in the panel, because it had waited more than 30 s in pickup; a sendmail flood of 400 mails with 5 recipients each left 159 such mails (fixed in `a72a0b6`: a record names any mail that had arrived when it was written, up to 5 days before, and mail held by others is counted and shown). FAIL: with the milter stopped, mail went out without a limit (`milter_default_action=accept`, as designed then); since `1c74675` the milter fails closed. With only the release service stopped, `send_limit.py --status` and `GET /system/send-limit` showed no warning: `status()` in `management/send_limit.py` took the milter's state for the release service's while the milter ran (B226, fixed after `04785d0`, offline test only). |
| Settings and pages | 18 invalid values through the API and 10 in the panel refused with 400 and a message; settings saved and restored, with audit lines; the page's new name "Intrusion Detection and Prevention" in the menu and the heading, the old link `#fail2ban` opens it (12/12). The ban list (B220) with 3000 documentation addresses banned in 6 jails (3600 bans): `GET /system/fail2ban` 0.98 s without the list, a page of 50 bans 0.45 to 0.59 s; paging, the filters (network, IPv6 prefix, jail, part of an address), the limits (400 for bad values), "Why?", a click on a network and Unban of one address worked in the browser (the script's own checks 7/9: a row threshold too strict and a missing wait, both of the script); the page loaded in 2.9 to 4.1 s with 3007 elements, as wide as the window; after unbanning all, fail2ban and the page were empty. |
| Downgrade and back | with nothing held: the downgrade to v78-r2604.4 exit 0 in 105 s, the milter no longer in Postfix's settings (its services left running, unused), mail both ways, no error mail of the cron jobs in 15 minutes (they test for their programs), log audit 0 unknown; back to `f1c367e` exit 0 in 75 s, 18 of 18 checks. |
| Fresh install and smoke | a fresh install exit 0 in 1731 s (slow downloads), 18 of 18 checks; a brake with 1 mail a minute: the second mail held, the brake on and the administrator's mail within 3 s, all delivered after End. Smoke 115/116 there and 126/127 on the copy: `admin-send-limit` compared all settings with the three it set (a fault of the test, fixed in `6c6fbc4`). Log audit of the copy: one unknown class, the mails left alone above; two harmless classes got lines in `689e333`. |

A short second round at `a72a0b6` (the long limit, failing closed, the
reports' own listener, the fix of the mails left alone): the update exit
0 in 97 s, `after` 0 unexpected and 21 expected changes, 26 of 26 checks
of the new Postfix settings; `mailcheck` failed once because logrotate
rotated `mail.log` while it waited (`update-check.sh` reads only
`mail.log`) and passed when repeated; a second setup run changed nothing.
Floods of 1500 recipients from full buckets: the brake came on after 1011
(SMTP 587), 1030 (webmail), 1020 (ActiveSync), 1043 (sendmail) and 1009
(127.0.0.1:25) recipients, "more than 1000 mails in 1 hour"; all held
mails of the sendmail flood were listed; with the long limit off, 600
mails at about 20 a second went out unbraked, as before. On the fresh test
box an update to `a72a0b6` ran while the harness ran its checks and
clean-up beside it and ended with exit 1 in Nextcloud's step; repeated
alone: exit 0 in 479 s. The round was stopped for the second run.

Second run, `689e333`:

| Run | Result |
|---|---|
| Update | from the snapshot: exit 0 in 118 s, 41 of 41 mails, `after` 0 unexpected and 21 expected changes (its 3 new log classes from the lab's route probes and a bounce of the peer), `mailcheck` OK, 26 of 26 checks. A second setup run exit 0 in 75 s: no restart, no content changed. |
| Fresh install | a first install was discarded (the first run's agent updated the same test box at the same time) and repeated from the snapshot: exit 0 in 1394 s; 25 of 26 checks (`postfix check` printed something once right after the install and nothing later; not reproduced); smoke 115/116 (`--fail2ban`), log audit 0 unknown. The FAIL: `api-read-only` found the brake on, see "A changed setting". |
| Everyday use | 30 minutes on 3 accounts with all clients: 75 mails to 507 recipients and 16 to themselves, 0 held, 0 deferred, the brake never on, every mail at the peer (at most 3.6 s, median 0.2 to 0.4 s). The box's reports and the test mail of System > Notifications came through the new listener `127.0.0.1:10587`; mail to root, Nextcloud's mail and the Sieve redirect passed the milter at once. |
| Floods (long limit) | from full buckets, the recipients out before the brake: SMTP 587 (1500 at about 20 a second) 1013, SMTP 465 1010, webmail (300 × 5) 1020, ActiveSync (300 × 5) 1010, sendmail (1500) 1040, SMTP to 127.0.0.1:25 1008; the brake's log line and the administrator's mail, 2 to 3 s later, said "more than 1000 mails in 1 hour"; the 10 to 40 over 1000 are the refill of the bucket during the flood. The rest held and deleted; the peer's count equal to the box's log every time; a second account's mails during the brake held and released (at most 52 to 83 s). With the long limit off 600 mails went out unbraked, as before. The administrator's mail of the sendmail flood counted one mail "not on the list" although none was held by hand (a race, fixed in `65a3916`). |
| The brake | nothing released in the brake's first 60 s, also not a mail with 40 recipients, then 9.7 recipients a minute on average, the senders in turn. A sendmail flood of 400 × 5: the hold queue and the list both 294, no mail left alone; deleted (292) and the brake ended in the panel. A mail held by hand showed as 1 "not on the list" in the panel and in the administrator's mail. A mail deferred while the release service was stopped was held, listed and released when it came back. Two accounts with 20 recipients each in the same second set off the brake, as documented. |
| A changed setting | FAIL: after a limit of 1 mail an hour had been set and 30 a second restored, the next mail of any account was held and set off the brake, also 90 s later: the changed setting left the bucket without room; the smoke test had counted the held mail as sent. Found on both test boxes; fixed in `176a09a`, and the smoke test now checks that this mail is not held. |
| Failure cases | the milter stopped, hung, and killed 6 times: mail programs on 587 and 465 got "454 4.3.0 Try again later", webmail an error, SMTP to 127.0.0.1:25 and [::1]:25 "451 4.7.1" (when hung, after 30.0 to 30.6 s); ActiveSync and sendmail mail waited in the maildrop and went out within 37 s after the start; systemd restarted the killed milter each time within 2.2 to 2.4 s; a sender on 587 meanwhile got 40 mails out and 13 temporary errors; 237 of 237 mails from the peer were delivered. The reports came through 10587 meanwhile; it took 20 mails a minute (then 450) and refused other recipients (554). Stopped for 15 minutes, the cron job mailed "does not answer" once and "answers again" once; the text named 451 4.7.1 for all clients (fixed in `65a3916`). |
| Switches | the sending limit turned off in the panel: the milter out of Postfix's settings, the 53 held mails out, every path delivered with the milter stopped, no cron mail, a setup run kept it off; on again: the settings back, a flood braked. fail2ban turned off in the browser (one attempt repeated after a fix of the harness's click): stopped and disabled, the bans lifted, warnings on the page and in the status checks, kept off by a setup run and a reboot, wrong passwords from the peer banned nothing; on again: its 13 jails and the bans that had not run out back; the same through the API. |
| Downgrade and back | the downgrade to v78-r2604.4 exit 0 in 69 s: `smtpd_milter_maps`, the listener 10587 and the two services stay (mail from the box itself on port 25 still passes the limit there), `sendlimit_submission_milters` stays unused (Postfix warns about it); mail from webmail, mail programs and the box went out, no cron error mail in 15 minutes; back: 26 of 26 checks. |
| Smoke and log audit | smoke 126/127 on the copy, with the same `api-read-only` FAIL as the fresh install; log audit of the copy 37 new classes: 34 from the lab (the deliberate stops of the milter, floods and wrong passwords), 3 harmless with proposed lines, 0 defects. |

#### Final T3 and T5b (`65a3916`)

| Run | Result |
|---|---|
| T3 (the 24.04 copy of a production box, in place, `--keep-local`, the tool of `65a3916` by `curl \| sudo bash` in a recorded terminal) | "All checks passed. The upgrade is finished.", all 11 phases done; the tool ran 52 minutes with one reboot, mail was offline 36 minutes. `after` did not judge the changes (the Ubuntu release changed) and named 8 new log classes, judged in the audit below; `mailcheck` OK; smoke 32/32 (`migrated,web,activesync`). The new parts on the upgraded box: 40 of 40 checks (the limit's defaults, Postfix's settings, the listener 10587, fail2ban, the account lock); the users' mail (587, 465, webmail, ActiveSync, 20 recipients with 2 MB) and the box's reports through 10587, 0 held. A setup run after a reboot (the harness's first try had no hostname and ran no setup) exit 0 in 94 s and restarted the two services once, as documented for the first run after a reboot; a run without a reboot before it restarted nothing and changed only the nightly job's minute and a rebuilt greylisting map. Found: after a reboot with mail in the queue, Postfix started 3 s before spampd listened, and 16 local mails, also mails that came in after spampd listened, waited 325 to 602 s (B222, in setup since upstream; fixed in `0415a5e`). A reboot with an empty queue: spampd listened 3 s after boot, no mail deferred. Smoke 127/127; log audit 12 new classes, 3 left with the lab's list: those of B222. |
| T5b (the copy at the published v78-r2604.4, updated non-interactively under client load) | exit 0 in 185 s with the end line; 335 of 335 marked mails; probes: port 993 and LMTP down for one round, spampd 6 s, ports 25 and 587 never; senders 587 10 of 10, 465 9 of 9, webmail 8 of 9, ActiveSync 8 of 9 (one cut read, one 502 at PHP-FPM's reload; both told the client), all accepted mail at the peer; 0 held, the brake never on; 5 local deliveries deferred at the restarts of Dovecot and spampd and delivered after 63 to 384 s (B225 below). The client load's verdict FAIL on both sides: a DAV login got 401 2 s after setup stopped Dovecot, Z-Push answered 500 at the same moment, and one ActiveSync device got no answer for 68 s between Dovecot's stop and PHP-FPM's reload. `after`: 1 unexpected (the lab's origin), 22 expected; `mailcheck` OK; Postfix's settings and the defaults as expected. A second setup run exit 0 in 107 s: no restart of the two services, only the nightly job's minute and the greylisting map changed; reboot: running, no failed unit, mail both ways. The fixes since `689e333`: after a changed setting (1 an hour, and a long limit of 5) mails 5 and 90 s later were not held and set off no brake (`176a09a`); a sendmail flood of 1500 set off the brake after 1050 mails, the hold queue and the list both 453, "not on the list" 0 in 693 samples (`65a3916`), a mail held by hand counted; fail2ban's dialogs say that it was stopped and started; with the milter stopped for 9 minutes the mail named 454 4.3.0, 451 4.7.1 and the waiting ActiveSync mail, then "answers again". Smoke 127/127. Found by the log audit (8 classes): dpkg's trigger restarted Dovecot when setup installed `dovecot-auth-lua`, and 13 s later setup reloaded it with the new passdbs of the account lock; under the load its auth process died ("Panic: ... sasl-server.c", 29 times "Auth worker sees different passdbs/userdbs than auth server"), and a login on the submission port failed (B223, in setup since v78-r2604.0; fixed in `a9eaff0`: a changed passdb or userdb restarts Dovecot). The other 41 new classes: 26 from the lab, 15 harmless in the setup window (7 proposed lines). |

#### B222 to B225: the delta runs

Each delta run updated the copy at the published v78-r2604.4 from its
snapshot under the client load of the final T5b, ran a second setup run,
the smoke test with `--fail2ban` and the log audit, and checked the fix
before it in detail.

| Run | Result |
|---|---|
| Delta 1, `a9eaff0` (B223; B222 on the update path) | the update exit 0 in 219 s; Dovecot restarted twice (dpkg's trigger, then setup), never reloaded; no Panic and no "Auth worker sees different passdbs/userdbs": 6 of the 8 classes of B223 gone. Found: dpkg's restart stopped Dovecot for 6.6 s, 5 new submission processes of Postfix exited ("no SASL authentication mechanisms"), and Postfix then started none for 60 s: port 587 did not answer for 56 s, 3 SMTP logins of the load got no banner for 30 s, and the 2 classes of B223 left ("Connection lost to authentication server", Z-Push's temporary failure) came from that restart (B224, in Postfix's setup since upstream; fixed in `fe02b21`: `service_throttle_time` 10 s, and Dovecot's packages installed without their restart). Also: 2 of 343 marked mails got "451 4.3.5" (Dovecot's quota service during the restart; the sender tries again), 5 local deliveries waited 351 to 396 s. Senders 587 10, 465 9, webmail 10, ActiveSync 7 of 9; 0 held. `after` 1 unexpected (the lab's origin), 25 expected with both drop-ins of B222; `mailcheck` OK. The second setup run exit 0 in 120 s left Dovecot alone. B222: 5 mails put into the maildrop with Postfix stopped, then a reboot: Postfix started 6 ms after spampd's start had ended, the mails were delivered 2.5 to 4.8 s after Postfix's start, no "Connection refused". Smoke 127/127; log audit 40 new classes: 4 from the lab, 30 harmless (11 proposed lines), 6 of B224. |
| Delta 2, `fe02b21` (B224) | the update exit 0 in 238 s; Dovecot restarted once, by setup (stop 1.6 s), dpkg's trigger held, no `policy-rc.d` left; no class of B223. Postfix logged the throttle twice, port 465 answered again 9.1 s after it, port 587 was not interrupted; 352 of 352 marked mails; 0 held. The client load's verdict FAIL on both sides: of 182 failed rounds 86 were inside Dovecot's restart and PHP-FPM's reload, 96 outside, all ActiveSync Provision and FolderSync timeouts (the baseline on v78-r2604.4 had 24 in 5 minutes); no IMAP, SMTP, DAV or webmail failure outside them (the harness's webmail sender had failed its first login before the update in Roundcube's race of parallel first logins, a lab artefact). Found: 3 mails to a user that arrived during the restarts of Dovecot and spampd were deferred and delivered 353 to 374 s later, after Postfix's backoff of 300 s (B225, in setup since upstream; fixed in `bd17f24`: setup retries those mails at its end). The second setup run exit 0 in 143 s restarted nothing. B222 again: the 5 mails delivered 3.0 to 5.6 s after Postfix's start. Smoke 127/127; log audit 1 new class (Nextcloud's "Login failed" during Dovecot's stop, 15 lines). A fresh install: exit 0 in 1318 s, `service_throttle_time` 10 s, no `policy-rc.d`, smoke 105/105, log audit 0 unknown (the lab's outdated check of the passdb of `fix/b178` failed as before). |
| Delta 3, `bd17f24` (B225) | the update exit 0 in 294 s under the client load and a loop that sent a mail to a user of the box every 2 s from setup's start to 60 s after its end; Dovecot restarted once (stop 6.75 s under the load), the throttle once and port 587 back 9.7 s after it; 368 of 369 marked mails (one "451 4.3.5" during Dovecot's stop); every sender's mails accepted; 0 held. Client load FAIL on both sides with the picture of delta 2 (191 failed rounds inside the restart windows, 88 outside, all ActiveSync timeouts). The loop: 176 mails sent, 176 delivered, none twice. 28 mails were deferred in setup's window with a reason at 127.0.0.1; Postfix's own retries delivered 8, setup's end put the other 20 back into delivery within 0.2 s; 16 of them were delivered 9.3 to 20.8 s after the end line, 4 after 99 to 107 s: spampd, with Ubuntu's default of 3 processes, was saturated by the test's own mail loop, and local delivery took 10 to 22 s already before any restart. Accepted as a limit of capacity under the test's load, not a defect of the release (CHANGELOG-fork.md, "Planned"). The second setup run exit 0 in 129 s restarted nothing, 51 of 51 mails. Smoke 127/127; log audit 13 new classes: the known "Login failed" (90 lines, all during Dovecot's stop) and harmless consequences of the longer stop and the extra mail, 0 defects; their lines are in `84353e4`. A fresh install: exit 0 in 1154 s, smoke 105/105, log audit 0 unknown; setup's end ran the retry without an error (the queue was empty). |

After the delta runs only the log audit's list (`84353e4`), an offline
test helper of `update-check.sh` (`tests/fork/update-check-compare.py`,
`04785d0`) and, in the release commit, the warning of the sending limit's
status for a stopped release service (B226, two lines of
`management/send_limit.py`, checked by `tests/fork/send-limit.py` only)
changed, besides the version strings, `tools/expected-changes/` and the
documentation.

Not tested in the added work: T2, T4, T6 and T7 (T2 and T4 ran at
`6bc2109`, before the account lock, the sending limit and B222 to B225);
the in-place tool's line for the drop-in of B222 (`0415a5e`), as T3 ran at
`65a3916`; a reboot with mail in the queue at `bd17f24` (passed at
`a9eaff0` and `fe02b21`, unchanged since); the smoke group `--fail2ban` in
the fresh installs after `689e333`; mail to the Internet: every flood went
to the peer, so neither the limit nor the brake met a real provider, and
the clients were the lab's scripts, not real mail programs and phones;
floods of more than 1500 recipients or longer than an hour, and a flood
across a restart of the two services (their counts live in memory and
start anew; the floods restarted them on purpose); a downgrade with held
mail (the two downgrades of these runs had an empty hold queue); the account lock with
real phones and mail programs, and bursts at the default window of 30
minutes (only at 1 minute); the ban list only with documentation addresses
in a headless browser 1280 pixels wide; the fail2ban switch only on the
test boxes; the warning for a stopped release service (B226) only in
`tests/fork/send-limit.py`, not on a box.

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

The account lock, the sending limit and the fail2ban switch of
v78-r2604.5 ran only in the lab, on test boxes and on copies of a
production box (see "v78-r2604.5").

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
  add `--allow-extra tests/fork/log-audit-allow-old-box.txt`. For an
  update from a box whose Z-Push has no mark of the fork's changes (rc7 or
  earlier), add `--allow-extra tests/fork/log-audit-allow-from-rc7.txt`
  (`tools/update-check.sh after` does that by itself when its state before
  the update has no such mark): the Z-Push of rc7 answers a login cut by
  setup's Dovecot reload with 401 until setup installs the fork's Z-Push,
  and Roundcube's CardDAV plugin can race in a schema migration left from
  an earlier setup run at two first logins.
  `--since`
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

Release checks (B135), in the repository before the tag is published and
on a box installed or updated from it:

        git cat-file -t v78-r2604.0                  # must print: tag
        sudo git -C /root/mailinabox describe --always   # on the box: v78-r2604.0

The status checks and the control panel's version (`/system/version`) name
the tag, and a second run of bootstrap.sh does not fetch again. The tag on
GitHub must be the same tag object (`git ls-remote` shows it and its
`^{}` line), and the release must be created from that tag, so that GitHub
does not make a new one.

## Not tested

* **Setup's network checks under setup's shell options, up to
  v78-r2604.1.** T1 ran setup with `SKIP_NETWORK_CHECKS=1` in every
  release up to v78-r2604.0 (v78-r2604.1 had no test matrix), and so did
  T6 of v78-r2604.0 after its first install had stopped (B136). The repeated T6 ran the checks, but through
  a public resolver that Spamhaus refuses (127.255.255.254, for which
  `host` exits 0). So `setup/network-checks.sh` never took its "not
  listed" path (NXDOMAIN, for which `host` exits 1) under setup's
  `set -euo pipefail`, and B145, which stops such an install without a
  message, shipped that way in v78-r2604.0 and v78-r2604.1. From
  v78-r2604.2 on, T1n runs the checks on the installed T1 box through its
  own resolver (see "Scenarios").
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
  setups other than the stand-ins of the lab. In v78-r2604.0 `after` ran
  on updates from one tag to the next (rc7 and rc6 to the release, from the
  lab's mirror). Once the lab had put the GitHub origin back (with the
  lab's own origin it named that line), its changes were RESULT OK in both;
  from rc6 it ended with RESULT: OK, from rc7 its log audit named two
  classes that the lists of the release accept (T5b Part A).
* **The published tag and GitHub.** The runs of v78-r2604.0 installed the
  tag from the lab's mirror, before it was on GitHub (the boxes downloaded
  Z-Push and the other components from GitHub as usual), and
  `tools/update-check.sh` through `curl | bash` took its helpers from the
  tag by a changed URL, as the branch main on GitHub still held rc7. The
  published rc7 tag came from GitHub (T5b).
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
* **The Internet (T6)** ran for v78-r2604.0 on one VM of one hosting
  provider, IPv4 only, as the name server of a delegated subdomain without
  a DS record at the parent (so no resolver validated its DNSSEC). Not
  tested there: IPv6, a signed delegation, `mailcheck` with a real
  external probe address (the round trip with the external mailbox was
  made by the test's own script; in the lab `mailcheck` ran with the lab's
  probe address),
  desktop mail clients (Outlook's Autodiscover schema was only probed),
  the in-place and migration tools on the Internet, and more than a few
  hours of a public box's traffic.
* **The update of the production box itself.** The operator's steps from
  rc7 ran on a copy of a production box (T5b Part A), not on the box.
* **The account lock and the sending limit outside the lab
  (v78-r2604.5).** Both ran with the lab's scripted clients, and no mail
  of the floods left the lab: no real phone or mail program met a lock,
  and no real mail provider saw a flood or a brake (see "v78-r2604.5").
* **Other virtualization and hosting providers.** The tests ran on one
  hypervisor with its cloud-init. The cloud-init configuration of hosting
  providers' images (`manage_etc_hosts`, B68) was not tested.
* **IPv6-only boxes.** The test boxes have IPv4 and IPv6.
* **Large boxes.** The test data is small; the only large data set was the
  production upgrade above.
* **Ubuntu 20.04 or older, Mail-in-a-Box older than v60** (the in-place tool
  needs v60, the migration v68), and Nextcloud older than 26. These are not
  supported.
