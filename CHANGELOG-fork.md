# Changelog of the Ubuntu 26.04 fork

Changes from Mail-in-a-Box v78, the last official upstream release (Ubuntu 22.04
only), to this fork. The fork is upstream PR #2603 (writeDavid's Ubuntu 26.04
port, head `c6118db`), merged with v78, plus its own fixes. Newest release first.
The base section at the end describes what the port itself changes.

Bug IDs such as **B01** refer to [BUGS-fork.md](BUGS-fork.md). Each entry there
documents the symptom, cause, fix and affected versions of one bug (v78 on 22.04,
PR #2603). For upstream's own history see CHANGELOG.md.

## Unreleased

### New

* Tools: `tools/upgrade-in-place-to-2604.sh` has two more hook stages for
  services of the operator that use the mail (e.g. a docker compose stack
  with IMAP logins): `/etc/mailinabox/upgrade-2604.d/before/*.sh` run right
  before mail goes offline (a failure stops the upgrade before anything is
  stopped), `/etc/mailinabox/upgrade-2604.d/after/*.sh` in phase finish
  after mail and the backups are back, and at the end of `--rollback` (a
  failure only warns). If the final check fails, the after hooks run right
  after it, as mail runs again, and not again in finish: services stopped
  by a before hook do not wait for `--finish`. All hooks get `HOOK_STAGE`; the hooks in the
  directory itself still run only in phase local-ext. `--check` lists all
  three stages.
* Postfix: senders listed in `/etc/postfix/greylist_bypass_senders` (an
  access(5) file of the administrator, e.g. `newsletter@example.com OK`)
  skip greylisting. If the file exists, setup runs postmap on it and puts
  `check_sender_access hash:/etc/postfix/greylist_bypass_senders` right before
  postgrey, with the quota check in front of both; without it the
  restrictions stay as upstream. Before, setup dropped such a rule added by
  hand on every run. To turn it off, delete the file and run setup (keep the
  `.db` until then). `tools/migrate-to-2604.sh` takes the file over from the
  old box before setup (not from a backup, which does not contain it).
* Nextcloud: users only see and share with the accounts of their own mail
  domain (share dialog, contacts menu, system address book, calendar and team
  member search); members of the Nextcloud group `admin` with everyone.
  Each mail domain becomes a Nextcloud group (user_external `groupDomain`),
  `tools/nextcloud-share-scope.sh` sets the sharing options, puts existing
  users into their group and the admins into all of them; setup runs it, cron
  every 5 minutes. `NEXTCLOUD_SHARE_SCOPE=all` in `/etc/mailinabox.conf` keeps
  upstream's behaviour and puts back the sharing options from before. See
  README-fork.md for the limits.
* Tests: smoke check `nextcloud-share-scope` (sharee search across domains,
  system address book, admin view).
* fail2ban: adaptive intrusion protection, on by default (README-fork.md,
  "Intrusion protection"; control panel: System > Intrusion Protection).
  Each new ban of an address in a jail lasts twice as long as its previous
  ban in that jail, up to one week (no `bantime.overalljails`; recidive
  handles addresses banned in many jails); bans of the web ports keep their
  fixed length; the ban history is kept for 30 days. Slow jails for SMTP AUTH
  and IMAP/POP3/ManageSieve ban after 20 failures within 6 hours on the mail
  ports (the Dovecot one ignores connections without a login attempt); slow
  jails for Roundcube, Nextcloud and the control panel (HTTP/HTTPS) are a
  separate switch, off by default. An allowlist of own networks is added to
  ignoreip; saving it unbans addresses that are banned and now on it. Changing the adaptive options restarts the jails (`reload
  --restart`), because a plain reload leaves the old values in running jails. The settings are stored in
  settings.yaml under `fail2ban`; `management/fail2ban_admin.py` writes
  `jail.d/mailinabox_adaptive.conf` and `fail2ban.d/mailinabox_adaptive.conf`
  from them (setup, `--apply`), checks them with `fail2ban-client -t` and
  reloads fail2ban only on a change. All off with an empty allowlist is
  upstream's configuration. Before, a production box had 19,586 failed SMTP
  logins from 4,627 addresses in a week and no ban.
* Status checks: a report of failed logins in the mail log of the last
  48 hours: accounts that failed from 20 or more addresses within 24 hours
  (password spraying), addresses that keep failing for 12 hours or more
  without a single ban in that time (expired bans are read from fail2ban's
  database), and banned addresses that failed only as one or two existing
  accounts (probably an own device with an old password: allowlist it). Only
  existing accounts are named.
* Management API (admin): `GET /system/fail2ban` (jails, bans with time
  left), `GET`/`POST /system/fail2ban/settings`, `POST /system/fail2ban/unban`
  (one jail, or all jails including the ban history), `POST
  /system/fail2ban/unban-all` (one jail), `GET /system/fail2ban/report`.
* Control panel: new page System > Intrusion Protection. It lists the banned
  addresses (jails, time left; filter) and the jails with their counters,
  unbans an address in all jails or in one jail and empties a jail (with a
  confirmation), shows the failed-login report and edits the settings
  (adaptive banning and slow jails on/off with a confirmation before turning
  off, thresholds, allowlist, restore defaults). It shows the admin's own
  address (for IPv6 its /64) and offers to allowlist or unban it.
* Tests: smoke checks `admin-fail2ban-status`, `admin-fail2ban-settings`,
  `admin-fail2ban-report`, `admin-fail2ban-filters` (fail2ban-regex with
  injected user names) and `admin-fail2ban-panel`, and in the opt-in fail2ban
  group `fail2ban-adaptive-toggle` (turning adaptive banning off reaches the
  running jails); `prepare-testenv.sh` puts the jump host on the allowlist.

### Changed

* Tools: phase verify of `tools/upgrade-in-place-to-2604.sh` and
  `tools/migrate-to-2604.sh` reports each item of an `smtpd_*_restrictions`
  parameter from before (of the old box) that is gone now ("Postfix
  restriction ... is gone: ...") as a failed check and at the top of
  `etc-report.txt`, not only as a changed line of `postconf -n`. A DNS list
  that only got return codes (upstream v68, `zen.spamhaus.org=127.0.0.[2..11]`)
  does not count as gone.
* Tools: a Mail-in-a-Box backup that is running (e.g. the nightly one at
  01:04) no longer stops the start. `tools/upgrade-in-place-to-2604.sh`
  reports it in the preflight (also with `--check`) without a blocker, then
  waits for it with progress dots before anything is stopped (at most 2
  hours, `UPGRADE_BACKUP_WAIT`; Ctrl-C is safe) and checks the age of the
  last backup again, also when that backup has finished by itself before the
  stop; `tools/migrate-to-2604.sh` waits the same way on the old box before
  stop-old (`MIGRATE_BACKUP_WAIT`). A check that fails while waiting (e.g.
  ssh) is not taken for "finished": it is retried, and three failures in a
  row stop the run before anything is stopped. A running backup is found in
  `/proc` (a python running `management/backup.py`, or duplicity), no longer
  with `pgrep -f`, which also matched command lines that only name them; the
  `--rollback` of the migration ends a backup still running by these PIDs,
  no longer with `pkill -f`.
* Tools: `tools/upgrade-in-place-to-2604.sh` and `tools/migrate-to-2604.sh`
  run themselves in a tmux session (`upgrade-2604`, `migrate-2604`) when a
  command that changes something is started from a terminal outside tmux or
  screen, so a dropped SSH connection no longer stops a release upgrade, the
  copy or setup halfway. They install tmux if it is missing (in place: not
  in the middle of a release upgrade, and only if that upgrades or removes
  no other package), fall back to screen, pass the arguments and the
  environment variables they read into the session, attach the terminal
  (also through `curl | bash`), keep the window open until Enter (also
  after Ctrl-C; with `--yes` at most 10 minutes, so that `ssh -t ... --yes`
  returns) and exit with the code of the run. The environment goes
  through a file readable only by root, not the command line. A terminal
  type without a terminfo entry on the box (xterm-ghostty, xterm-kitty, ...)
  attaches as xterm-256color; screen reattaches with `screen -d -r`. A
  window of an earlier run that only waits for Enter is closed; if something
  still runs in a session of the same name, the command is NOT started (the
  terminal is attached to that session and the tool says so). Installing
  tmux waits for the apt locks only briefly. Through `curl | bash`, the copy
  of an older release tag that does not start tmux itself gets a warning
  first. `--no-tmux` turns it off; `--check`, `--status`, the resume unit and
  runs without a terminal are unchanged.

### Fixed

* Tools: `tools/upgrade-in-place-to-2604.sh` stops mail (and masks the units)
  before the fresh Mail-in-a-Box backup of phase snapshot, not after it, so
  the backup holds all mail. Before, backup.py started Postfix and Dovecot
  again after its run, and mail accepted while the system archive was written
  and copied was missing from the backup (B57). The downtime starts there;
  with `--skip-miab-backup` or backups off, mail keeps running until quiesce
  as before. `--rollback` brings it back as before. The system archive, the
  copy of `/etc` and the package lists are still taken before the stop, so
  they hold `/etc` without the masks; a run interrupted after the stop keeps
  them and does not repeat a backup that already ran with mail offline.
  The downtime estimate of the plan (`--check`) includes the fresh backup and
  says that a full one can take much longer.
* Management: the usage report (`mail_log.py`) counts IMAP, POP3 and
  ManageSieve logins again: Dovecot 2.4 logs them as "Logged in:", not
  "Login:" (B58).
* Postfix: setup no longer sets `smtpd_tls_dh1024_param_file` and removes it
  from an existing main.cf. Postfix 3.10 warned on every `postconf` call that
  its support will be removed; the default uses the RFC 7919 FFDHE groups
  (B59).
* System: mail of cron jobs and root reaches the administrator. Setup writes
  PRIMARY_HOSTNAME to `/etc/mailname` (Postfix's myorigin; a provider's image
  could leave its own name there, and such mail bounced daily), comments out
  a 127.0.1.1 line in `/etc/hosts` with another machine's name, makes
  root@PRIMARY_HOSTNAME an automatic alias to administrator@ and writes the
  automatic aliases at the end of every setup run. The Nextcloud cron jobs
  send their output to root instead of www-data (B60).
* fail2ban: the `miab-postfix-submission` filter (jails `miab-postfix465`,
  `miab-postfix587`) is anchored. A client could put `[<ip>]: ` into the SASL
  user name, which Postfix logs after the client address, and get a third
  party banned (B61).

### Upgrade note

* The slow mail jails are on after the upgrade, with an empty allowlist. On a
  box whose users sit behind one office address, put that network on the
  allowlist (System > Intrusion Protection, or `sudo
  management/fail2ban_admin.py --allow 192.0.2.0/24`) before or right after
  the upgrade: a single phone with an old password can otherwise get the
  office banned from the mail ports, for longer each time.

## v78-r2604.0-rc3 (2026-10-23)

In-place upgrade and full-text search. Tested in place on a copy of a
production box (Ubuntu 24.04 release-upgraded from 22.04, Mail-in-a-Box v74,
PHP 8.0 from ppa:ondrej, Dovecot 2.3 with fts_xapian and a Lua push plugin):
"All checks passed", smoke test 53/55 (the two differences were a test mail
of the preparation), about 50 minutes of mail downtime.

### New

* Tools: `tools/upgrade-in-place-to-2604.sh` upgrades a box in place:
  22.04 → 24.04 → 26.04 or a release-upgraded 24.04 box → 26.04, then setup of
  this fork on the existing data. Detects local extensions, makes an encrypted
  system archive next to the backups, keeps mail off across reboots, continues
  on its own after each reboot, supports operator hooks
  (`/etc/mailinabox/upgrade-2604.d`), compares counts and fingerprints before
  and after, and removes leftovers of the old releases (`--cleanup-only`).
  See README-fork.md.
* Dovecot: full-text search with fts_xapian (`95-mailinabox-fts.conf`, on by
  default, `FTS=off` in `/etc/mailinabox.conf`), a daily
  `doveadm fts optimize -A`. Hand-made 2.3 FTS files are replaced; existing
  Xapian indexes keep working.
* Tests: smoke check `fts-search` (IMAP SEARCH BODY and `doveadm fts lookup`).

### Fixes for boxes upgraded in place

* Dovecot: Dovecot 2.3 setting names kept in 10-auth/10-ssl are commented out (B51).
* Spam: leftovers of the dovecot-antispam setup of older versions are removed (B52).
* Management: the Python venv is rebuilt when its interpreter no longer runs (B53).
* Setup: bootstrap.sh explains an existing checkout of another origin (B54).
* System/apt: PPA sources and keys of earlier releases are removed; Launchpad builds of ppa:ondrej are moved back to Ubuntu packages (B55).
* System: a failing pollinate no longer stops setup (B56).

## v78-r2604.0-rc2 (2026-10-23)

Fixes from the review before rc2. Certified from the tag without manual
steps: fresh install (49/49 smoke checks) and migration from a v74 box
(54/54).

### Fixes

* DNS: SSHFP records come from the public key sshd actually serves. It is derived from the private host key, with `.pub` only as a fallback (B11). ECDSA P-384/P-521 keys map to algorithm 3 (B34).
* Mail: quota validation accepts ASCII digits only. Unicode digits such as a fullwidth `１０G` broke the user's Dovecot userdb lookup (B17, also in v78).
* Z-Push: `MBSTRING_OVERLOAD` is defined for `z_RTF` on PHP 8. CalDAV Sync requests with RTF bodies used to crash with HTTP 500 (B31, also in v78).
* Tools: `migrate-to-2604.sh` hardening:
  * stopped units stay disabled across reboots;
  * backups are paused again after every rsync;
  * rollback is safe (backups paused, leftover backup runs ended, `virtual_transport` restored, zone restore and nsd reload separated);
  * the Nextcloud event and `occ status` checks are more accurate.
* Tests: `prepare-testenv.sh` fails unless ufw is active and the production deny rules are loaded in the kernel, whatever the caller's locale.

## v78-r2604.0-rc1 (2026-10-23)

First release of the fork: PR #2603 + v78 + the fixes below.

### New

* `tools/migrate-to-2604.sh` moves a box (upstream v68+ on Ubuntu 22.04, or a 24.04 in-place upgrade) to a fresh Ubuntu 26.04 machine in one command.
  * Phases:
    1. `--check` dry run with a downtime estimate and checks of port 25, Spamhaus and PTR.
    2. Live rsync, then an optional `--rehearse`.
    3. Stop of the old box: services, sockets, cron and apt timers stay masked until reboot.
    4. Wait for open files, then the final rsync.
    5. Setup, user-ID mapping and checks.
    6. Next steps for DNS. `--push-zones-to-old` shortens the glue switch.
  * Resumable. Backups stay paused until the new box is verified.
  * Further modes: `--rollback`, `--status`, `--check-old`, `--finish` and `--from-backup`.
  * Details in README-fork.md.
* `tests/fork/`: seed data for a legacy box (`seed-legacy.sh`), end-to-end smoke test (`smoke.py`) and test-network preparation (`prepare-testenv.sh`).

### Fixes

Setup and system
* Bootstrap accepts Ubuntu 26.04 and installs from the fork (B05). The version status check compares against the fork's tag (B40).
* `email_validator` is installed whenever it is missing for the address prompt (B21).
* TLS: back to MIAB's `dh2048.pem` instead of generating 4096-bit parameters (B43).
* The timezone check uses `/etc/localtime` (B44).
* `wget_verify` picks the hash algorithm by length and no longer overwrites the caller's variables (B45, B46).
* sury PHP repository:
  * pinned to the packages Ubuntu 26.04 lacks (B25);
  * keyring checked against the key fingerprint (B26);
  * key no longer trusted globally (B27);
  * PHP packages it had already replaced move back to Ubuntu (B07).
* unattended-upgrades covers sury and the duplicity PPA (B28, also in v78).

Dovecot 2.4
* quota-status answers DUNNO, so mail to aliases, catch-alls and domain aliases is no longer rejected (B01).
* Per-user quota:
  * the limit comes from the userdb (`quota_storage_size`) (B02);
  * the maildir quota driver keeps the usage up to date (B38);
  * the grace is 10% of each user's quota again (B14);
  * `quota_status_toolarge` is set (B15).
* `$STORAGE_ROOT` is expanded in `99-local-sieve.conf`, so user filters and vacation replies run (B04).
* Sieve redirects use the recipient as envelope sender (B03).
* ManageSieve port 2000 is closed (B39). LMTP username format and sieve plugin are pinned in `99-local.conf` (B13).

Spam
* IMAPSieve spam/ham learning runs:
  * LF line endings, enforced by `.gitattributes` (B06);
  * 120 s pipe timeout (B16);
  * no failed-pipe noise in the log (B47);
  * ham rules skip trash and spam moves (B22).
* spampd local-only mode is really off, so DNSBL, URIBL, Pyzor and Razor checks run (B24).
* SpamAssassin rule updates run via `spamassassin-maintenance.timer` (B23). The unused spamd is disabled (B48).

fail2ban
* The dovecot jail reads `mail.log` (B09). The filter matches Dovecot 2.4 login failures (B08) and IPv6 local addresses (B33, also in v78), and resists IP injection through the user name.

DNS
* SSHFP records:
  * keep the IANA algorithm numbers (B12);
  * are built from the host key files instead of `ssh-keyscan`, which OpenSSH 10's PerSourcePenalties throttled (B36);
  * no longer depend on sshd listening on IPv4 localhost (B35, also in v78).
* nsd logs to syslog only (B37, also in v78).

Web, Nextcloud, Roundcube, Z-Push
* nginx serves Nextcloud `.mjs` ES modules as JavaScript, so the Contacts app loads (B10). Roundcube 1.7 `static.php/<path>` assets get a proper PATH_INFO split (B50).
* Nextcloud:
  * `occ upgrade` failure handling works under `set -e` (B19, also in v78);
  * opcache settings also apply to PHP-FPM (B42).
* Webmail: the CardDAV preset uses the carddav 5.x keys (`discovery_url`, `preemptive_basic_auth`) (B20).
* Z-Push: `DAV_SSL_VERIFY` is defined for autodiscover. Z-Push 2.7.7 crashed with HTTP 500 (B32, also in v78).

Management and tools
* `mail_log.py` parses RFC 3339 rsyslog timestamps (B18).
* `daemon.py` no longer has a `return` inside `finally` in `/logout` (B41).
* `ssl_certificates.py` uses the timezone-aware `not_valid_*_utc` properties (cryptography >= 42) and an aware UTC "now". It is a separate `fix(ssl)` commit, so it can be reverted without touching the version bump.
* `owncloud-restore.sh`:
  * refuses backups without application code (B30, also in v78);
  * refuses code that cannot run on PHP 8.5 (B29);
  * uses a defined PHP version (B49).
* Postfix: a comment explains the harmless "no SASL support" warning on port 25.

### Setup and supply chain

* `wget_verify` picks the hash algorithm by length (64 hex = SHA256,
  128 = SHA512, 40 = SHA1 kept for compatibility). Every active pin is now
  SHA256 and was checked against the upstream checksum where one is
  published (Nextcloud `.sha256`, GitHub release digest, roundcube.net).
* The Nextcloud upgrade chain starts at Nextcloud 26. Installs with
  Nextcloud 20-25 skip the migration with a message (they need PHP <= 8.1).
* packages.sury.org is pinned to what Ubuntu 26.04 lacks (php-common,
  php8.2, php8.2-*, php8.5-imap); its keyring is checked against key
  `15058500A0235D97F5D10063B188E2B695BD4743` and no longer trusted globally.
* The management venv is recreated when the system Python version changes.
* The html5_notifier icon is resolved through `rcmail.assets_path()` so it
  works with Roundcube 1.7's `public_html` docroot.

### Version updates

| Component | Old | New | SHA256 of the new artifact |
|---|---|---|---|
| Nextcloud (fresh install / final step) | 34.0.3 | 34.0.5 | `d077fdca3dc78ef60b5bbc51182f2a1737aa01e2044d6c23f4e7b72146f5239a` |
| Nextcloud chain step to 33 | 33.0.7 | 33.0.10 | `ff602a1f1ba202f2137f10eecd201d3e80c5d94fd17ab984c688fb1bcb290645` |
| Nextcloud chain step to 32 | 32.0.10 | 32.0.15 | `33e7adbe81c1ad0be61123a0fadc63ae2e392759f0c2557e008863eb69c6453d` |
| Nextcloud chain step to 31 | 31.0.14 | 31.0.14 (re-pinned) | `6f34d623f7c24c5ecb3c165083ddb5d6a10186dbc2fa73a23efda26ec92091a7` |
| Nextcloud chain step to 30 | 30.0.17 | 30.0.17 (re-pinned) | `da51e17762785a36c1cf3fe2dc96cb356870695e384485e5980395493c15caf9` |
| Nextcloud chain step to 29 | 29.0.16 | 29.0.16 (re-pinned) | `6221c764b63369be6122bc414ee26a25bd9ce466f7d9ab29cd5ddb0c124c8eeb` |
| Nextcloud chain step to 28 | 28.0.14 | 28.0.14 (re-pinned) | `593f174f5098c793fb0314fd5847d891ed4e4db908ceba0d4e571544ac855c2d` |
| Nextcloud chain step to 27 | 27.1.11 | 27.1.11 (re-pinned) | `ffbfd9857bcaaacaea97d709063b7d81132feb41051063ab6c171c95c6daf142` |
| Nextcloud chain steps to 21-26 | 21.0.7 ... 26.0.13 | removed | - |
| contacts (fresh install, steps to 33/34) | 8.8.0 | 8.9.2 | `92f7c79c411273045ed6346f6988c05af673c3170a3adaba91a15066b8dce7c5` |
| contacts (step to 32) | 8.3.19 | 8.3.21 | `45d12ff526515ce5efc52d8e0d42bd3446a66b9a423ee4eb92ebd44a6b5974c3` |
| contacts (steps to 30/31) | 7.3.19 | 7.3.19 (re-pinned) | `568472420cf212ceeb1dccc044c0bdaa83504ef15251a2c6e39b22b6064a3ab8` |
| contacts (step to 29) | 6.0.7 | 6.0.7 (re-pinned) | `29b4942b9b224dcb7e7528fafb6a6094e45593e893dff61e519c34b19bed29a6` |
| contacts (steps to 27/28) | 5.5.4 | 5.5.4 (re-pinned) | `178aa6ec0b06d6bd72ff8eb87ac32ff267e97ccd93246b1eae1b5bb5263a61b0` |
| calendar (fresh install, steps to 32/33/34) | 6.5.4 | 6.6.3 | `bda8f38c609b2182533887f67eacb543edf437066d0356912ac6324c94743080` |
| calendar (steps to 30/31) | 5.5.23 | 5.5.24 | `9a4e1b869aa478317363cb0876a5d128aa584e427216d2cbfb808215f5c296a8` |
| calendar (steps to 27-29) | 4.7.20 | 4.7.20 (re-pinned) | `f62b43853dfc1fc971b4ffe5992cedc499e8ed7dc118265cfdfe8c1531d4a912` |
| user_external (fresh install, steps to 31-34) | 4.0.0 | 4.0.0 (re-pinned) | `f1f98c577bd02177fe74e9199f8e50d0c288ffa94bb50a227101a5ba0633c529` |
| user_external (steps to 27-30) | 3.4.0 | 3.4.0 (re-pinned) | `5a7fbed5da3cbe335f753027b662179c92c17fb37babc875e9e285d8a13d47f3` |
| Roundcube | 1.7.5 | 1.7.5 (re-pinned) | `93a66c94e3efff7db93187c1c9d7f35546647a3e1e7b9327cc87911564edf9d1` |
| Roundcube plugin rcmcarddav | 5.1.3 | 5.1.4 | `0ffa55ec6da5671d6c413a27d2511e903cd4e63de03c3e9480038844fa4625eb` |
| Roundcube plugin html5_notifier | git 68d9ca1 (kitist URL) | git 5d85947 (stremlau URL) | git commit pin |
| Z-Push | 2.7.7 | 2.7.7 (re-pinned) | `7a8e0094adf216521ee491078f78e709cd68257d05a868b3992d5665c01d8790` |
| jQuery (admin panel) | 2.2.4 | 3.7.1 | `fc9a93dd241f6b045cbff0481cf4e1901becd0e12fb45166a8f17f95823f0b1a` |
| Bootstrap (admin panel) | 3.4.1 | 3.4.1 (re-pinned) | `d49793cf773cbd393ac2cf340c3b4ddab5365fa7c292098ac07e12eab3efd92e` |
| pip: cryptography | ==37.0.2 | >=50.0.2,<51 (50.0.2) | wheel cp311-abi3-manylinux_2_34_x86_64 `9dab55f57c74c3cad24c323bacbbd04be4705ba6eb0d92e920b1fc4837ed5079` |
| pip: email_validator | >=1.0.0 | >=2.3.0,<3 (2.3.0) | `80f13f623413e6b197ae73bb10bf4eb0908faf509ad8362c5edeb0be7fd450b4` |
| pip: idna | >=2.0.0 | >=3.20 (3.20) | `ab7ae7122974553370f0bdb919e1a960b2cd1bc1ef0276416d896db81c14582c` |
| pip: b2sdk | unbounded | >=2.13 (2.13.2) | `f2d7663392d869c17d44b7304bae6e06ecefda18742b197a693a93298943310d` |
| pip: boto3 | unbounded | >=1.43 (1.43.118) | `ab8f3d2c622ef039338b4f228d97ea55f1abd573d84bb9b9a5ee8cb6780c0ccd` |
| sury keyring (debsuryorg-archive-keyring) | 2025.11.18, unchecked | 2025.11.18, key fingerprint checked | `.deb` `7511384559c9ddf1d5ce5f60be429ae9d4e7d01d9480d6f1b7a30c0810cf8b60` (not pinned, rotates in place) |
| Docs tool: Bootstrap (readable_bash.py) | 3.2.0 | 3.4.1 | SRI sha384 in the page |
| Docs tool: jQuery (readable_bash.py) | 1.10.1 | 3.7.1 | SRI sha384 in the page |
| Test tooling: dnspython | dnspython3 (1.15.0) | >=2.9,<3 (2.9.0) | `9a4aedb833c3c1b49214d04d44d3032ab7a9135f7c1d29a549b4ff78fd82fda9` |
| API docs: renderer | redoc-cli (0.13.21) | @redocly/cli 2.69.0 | npm integrity `sha512-un2CnJ+2OO82wArjuH132mD9lHs2oNJL8DtX50aCt6YrFTWIMWywCBRgxjznHdJ1lJAgck1giQgMc6yUL4kD0A==` |

Unchanged because they are already the newest compatible release:
Bootstrap 3.4.1 (final 3.x; 5.x needs an admin template rewrite),
persistent_login 5.3.0, Z-Push 2.7.7, Roundcube 1.7.5, Nextcloud 27.1.11,
28.0.14, 29.0.16, 30.0.17 and 31.0.14 (last patch of each major).
Nextcloud stays on 34: user_external has no release for Nextcloud 35 yet.

### Notes for review and testing

* Scope exceptions of the version-update series (intended, not drift):
  * `management/ssl_certificates.py` is outside the version-pin file set.
    Its change was first part of the cryptography bump and now sits in its
    own `fix(ssl)` commit. Not required by cryptography 50 (the naive
    `not_valid_before`/`not_valid_after` still exist there and only warn).
  * `setup/management.sh`: besides the pip/venv lines, the jQuery and
    Bootstrap pin lines changed. Those pins are defined only there.
  * `management/templates/login.html`: besides the asset pin, `$.trim(x)`
    became `String(x || '').trim()` (same behaviour; `$.trim` is deprecated
    in jQuery 3.5+).
* The sury apt pin (`/etc/apt/preferences.d/mailinabox-sury-php`) was
  verified on a fresh 26.04 VM (certification run for rc2): `php8.5-*` and
  `libgd3` come from Ubuntu (`8.5.4-0ubuntu1.5`, `2.3.3-13ubuntu2`), and only
  `php-common`, `php8.5-imap` and the temporary `php8.2-*` come from sury.
  Priority -1 does not downgrade packages on its own. Machines that already
  pulled sury's builds are moved back by setup (B07).

## Base: Ubuntu 26.04 port (PR #2603) and merge of v78

What the port changes compared with v77/v78, as included in this fork. Where it
names a limitation, the fix is listed above and in BUGS-fork.md.

### Bootstrap / preflight

- `setup/preflight.sh` now accepts only Ubuntu 26.04 (or 26.04.x) instead of 22.04, and the error message says so.
- `setup/questions.sh` installs `python3-email-validator` and `python3-dnspython` from apt instead of running a global `pip3 install email_validator`. Ubuntu 26.04 blocks system-wide pip installs (PEP 668, "externally managed environment").
- The Vagrant box changes from `ubuntu/jammy64` to `cloud-image/ubuntu-26.04`.
- Limitation: the PR never touched `setup/bootstrap.sh`. It still only knows 22.04 and 18.04, so the curl one-line installer aborts on 26.04. Our fork added a 26.04 branch (73209cf).
- Limitation: the apt install of the email validator only runs when `dialog`, `python3` or `pip3` is missing. On a host that already has all three, the address prompt loops on an ImportError. Fixed in our fork (7347986).

### System / apt / PHP source

- `PHP_VER` changes from 8.0 to 8.5, and a new `PHP_LEGACY_VER=8.2` is added for the Nextcloud upgrade chain.
- The `ppa:ondrej/php` PPA is replaced by the Debian-style repository at packages.sury.org. Setup downloads the `debsuryorg-archive-keyring.deb` with curl and installs it, then writes `/etc/apt/sources.list.d/php.list`. This repo is needed because Ubuntu 26.04 has no `php8.5-imap` and no PHP 8.2.
- The `ntp` package is no longer installed (26.04 handles time sync itself). `curl` is installed earlier as a prerequisite for the repo.
- `pollinate` now runs as the `pollinate` user (`sudo -u pollinate`) instead of as root.
- The inotify limit (`fs.inotify.max_user_instances=1024`) now goes into its own file, `/etc/sysctl.d/60-mailinabox.conf`, applied with `sysctl --system`. 26.04 no longer ships `/etc/sysctl.conf`, and `/usr/lib/sysctl.d/50-default.conf` is missing on some installs (contributed by Gwerlas in 0ddb859).
- Limitation: the sury repo is not pinned and its key is trusted globally. Sury's higher version numbers quietly replace Ubuntu's `php8.5-*`, `libgd3` and `php-common`. Those packages then get updates from neither repo, and unattended-upgrades does not cover sury or the duplicity PPA. Our fork added an apt pin and a key fingerprint check, and moves already-replaced packages back to Ubuntu's builds (d84aad5, d3ebd9e).

### Dovecot 2.4

- The PR no longer edits the packaged config files with sed/editconf. It ships its own `conf/dovecot-10-mail.conf`, `20-imap`, `20-pop3`, `20-lmtp`, `90-quota` and `99-local-sieve`, written in 2.4 syntax (`mail_plugins { quota = yes }` blocks, `mail_driver=maildir`).
- The mailbox path is now set with `mail_path=.../%{user|domain}/%{user|username}` (2.4 variable syntax) instead of `mail_location=maildir:.../%d/%n`.
- The SQL auth config moves into `auth-sql.conf.ext` as `sql_driver = sqlite`, `passdb sql {}` and `userdb sql {}` with `%{user}` queries. The separate `dovecot-sql.conf.ext` is gone.
- Settings renamed for 2.4:
  - `disable_plaintext_auth` becomes `auth_allow_cleartext=no`.
  - `ssl_cert`/`ssl_key`/`ssl_dh` become `ssl_server_cert_file`/`ssl_server_key_file`/`ssl_server_dh_file`.
  - `ssl_prefer_server_ciphers` becomes `ssl_server_prefer_ciphers`.
  - `ssl_min_protocol` and `ssl_dh_parameters_length` are dropped.
  - The listener option `address =` becomes `listen =`.
- `default_client_limit` is set to `nproc × 1250`, so that all services together can reach their `process_limit` of 250 each.
- The IMAP IDLE interval of 4 minutes, `mail_max_userip_connections` (IMAP 40, POP3 10 is new) and the POP3 UIDL format (now `%{uid | hex(8)}%{uidvalidity | hex(8)}`) move into the shipped config files.
- Sieve is rebuilt with 2.4 `sieve_script` blocks (global before/after, personal, spam-global) and gains the `sieve_imapsieve` and `sieve_extprograms` plugins.
- Limitations the PR left (all fixed in our fork):
  - `99-local-sieve.conf` is copied with plain `cp`, so Dovecot sees the literal text `$STORAGE_ROOT` in its paths. User filters and vacation replies do not run (451b7e3).
  - `sieve_redirect_envelope_from` sits inside the personal script block, where Dovecot ignores it. Sieve redirects keep the external sender as envelope sender and fail SPF (600d4ed).
  - The userdb still returns the 2.3 field `quota_rule`, so per-user quotas have no effect (6813745).
  - `quota_storage_grace = 100M` is a fixed size, not the old 10% per user (1642feb).
  - `quota_status_toolarge` is not set. In 2.4.2 it is empty, so Postfix accepts messages larger than the whole quota (05e5a8d).
  - The 26.04 ManageSieve config opens port 2000 on all interfaces (fc8b984).
  - The fail2ban dovecot jail matches nothing on 26.04 and Dovecot 2.4 (3b910e9).

### Postfix

- The only Postfix change: `smtpd_tls_dh1024_param_file` points to the new `dh4096.pem`. No other Postfix 3.10 adjustments were made.
- Limitation: Dovecot's quota-status policy now answers `quota_status_success = OK` and `quota_status_nouser = "REJECT Unknown user"`. Postfix asks this service before it resolves aliases, so mail to aliases, catch-alls and domain aliases would be rejected. `OK` also skips the remaining recipient restrictions. Our fork went back to `DUNNO` (6813745).

### Spam

- The `dovecot-antispam` plugin no longer exists for Dovecot 2.4. It is replaced by IMAPSieve: `report-spam.sieve` and `report-ham.sieve` run when a message is moved into or out of Spam/Junk, and pipe it to the new wrappers `sa-learn-spam.sh` and `sa-learn-ham.sh` in `/usr/lib/dovecot/sieve`. `sa-learn-pipe.sh` is removed.
- spampd options move from `/etc/default/spampd` to `/etc/spampd.cfg` (`maxsize=2000`, `local-only=0`). `CRON=1` is now written to `/etc/default/spamd` instead of `/etc/default/spamassassin`.
- Limitations the PR left (all fixed in our fork):
  - The sa-learn wrappers and sieve files have CRLF line endings. The shebang `#!/bin/bash\r` fails, so spam/ham learning never runs (600d4ed, plus `.gitattributes` in b4e792f).
  - spampd 2.62 reads `local-only=0` as "local-only on", so DNSBL, URIBL, Pyzor, Razor and DKIM checks are off.
  - SpamAssassin 4.0 ignores `CRON=1`, so rule updates never run.
  - The spamd daemon, which MIAB does not use, stays enabled (df7b5cc).
  - Moving a message from Spam to Trash subfolders or to Junk is learned wrongly (600d4ed).

### DNS

- DSA is removed from the SSHFP records (OpenSSH 10 has no DSA), and `ssh-keyscan` no longer asks for `dsa`.
- When `ssh-keyscan` fails, the SSHFP records are now skipped instead of aborting the whole DNS update. Before this, creating the first user returned HTTP 500 before the user got admin rights (Gwerlas, 615c104).
- Limitation: removing DSA also renumbered the remaining algorithms (ECDSA becomes 2, Ed25519 becomes 3). These numbers are assigned by IANA, so the signed zone would publish wrong SSHFP records. Our fork restored the IANA numbers (478a546).
- Limitation: OpenSSH 10 throttles repeated connections that never log in (`PerSourcePenalties`). The SSHFP records therefore come and go. Our fork reads the host keys sshd actually serves instead (2800a86, 2755ab2).

### Web / PHP-FPM / nginx

- The PHP-FPM socket and service names change from `php8.0-fpm` to `php8.5-fpm` in `nginx-top.conf`, `backup.py` and `owncloud-restore.sh`.
- `listen 443 ssl http2;` becomes `listen 443 ssl;` plus `http2 on;`, the syntax current nginx versions expect.
- The nginx DH parameters and `setup/ssl.sh` switch from a 2048-bit `dh2048.pem` to a newly generated 4096-bit `dh4096.pem`. Limitation: generating 4096-bit parameters adds minutes to every fresh install, and existing boxes already have `dh2048.pem`. Our fork reverted this (8fc67b2).
- Limitation: Nextcloud's `.mjs` ES modules are not served as JavaScript. Fixed in our fork (a0a98fd).

### Nextcloud chain

- The target version moves from 27.1.11 to 34.0.3. The apps move with it: contacts 8.8.0, calendar 6.5.4, user_external 4.0.0.
- New upgrade steps take an existing install through each major release in turn: 26 → 27.1.11 → 28.0.14 → 29.0.16 → 30.0.17 → 31.0.14 → 32.0.10 → 33.0.7, then 34.
- Upgrades from 26 to 31 run `occ` under a temporarily installed PHP 8.2. Later steps use PHP 8.5. At the end, PHP 8.2 is removed with `apt-get purge php8.2*`.
- The timezone is read with `timedatectl` instead of `/etc/timezone`, which 26.04 no longer has.
- The opcache settings are written to `cli/php.ini` instead of `cli/conf.d/10-opcache.ini`.
- Limitations the PR left (all fixed in our fork):
  - The old steps to Nextcloud 21–26 remain, but they need PHP 8.1 or older, which 26.04 cannot provide (cfbbe7a).
  - Setup runs with `set -e`, so a failed `occ upgrade` aborts setup before the retry. Nextcloud then stays in maintenance mode and php-fpm stays stopped, which also takes Roundcube and Z-Push down (20cee15).
  - The opcache settings only reach the CLI, not PHP-FPM (20cee15).
  - The commit "Placeholder for Nextcloud 35" is mislabelled; it is actually the 33 → 34 step.

### Roundcube

- Roundcube moves from 1.6.19 to 1.7.4, and the CardDAV plugin from 4.4.3 to 5.1.3.
- The nginx `/mail/` location now points to Roundcube 1.7's `public_html/` docroot, uses `try_files` and a nested PHP location.
- Limitations the PR left (all fixed in our fork):
  - The CardDAV preset still uses the 4.x keys `url` and `preemptive_auth`. The 5.x plugin drops them silently, so Nextcloud contacts never appear in Roundcube (562bd6e).
  - Roundcube 1.7 serves its assets as `static.php/<path>`. These only work because PHP's default `cgi.fix_pathinfo=1` happens to cover them (17fad3e).
  - The html5_notifier icon path does not fit the new docroot.

### Z-Push

- Z-Push moves from 2.7.6 to 2.7.7, the same version and hash as v78. The timezone is read with `timedatectl` instead of `/etc/timezone`.
- Limitation: this also affects upstream v78. In 2.7.7 the autodiscover config does not define `DAV_SSL_VERIFY`, so autodiscover requests fail with HTTP 500 (fixed in our fork, c9d2f92). `MBSTRING_OVERLOAD` is also missing on PHP 8 (fixed in our fork, 73baad3).

### Management / Python

- `ssl_certificates.py` no longer uses `datetime.utcnow()`, which Python 3.12+ deprecates. It now uses `datetime.now(timezone.utc).replace(tzinfo=None)`.
- `mailinabox.service` and `munin.service` are now enabled with `systemctl enable <path>` instead of `systemctl link` + `unmask`.
- Limitations the PR left (all fixed in our fork):
  - rsyslog on 26.04 writes RFC 3339 timestamps, which `mail_log.py` does not parse, so the usage report loses all Postfix lines (253c257).
  - Python 3.14 warns about a `return` inside `finally` in `daemon.py` (f0e19bc).

### Backup

- `backup.py` stops and starts `php8.5-fpm`.
- `duplicity` helpers now come from apt (`python3-gnupg`, `python3-b2sdk`, `python3-boto3`). The `pip3 install b2sdk boto3` line was not removed but left commented out with the note `## TEST:`.

### Tools / other

- `tools/owncloud-restore.sh` only swaps `php8.0-fpm` for `php8.5-fpm`. Limitation: `PHP_VER` is never defined, and the script cannot restore a pre-chain backup whose Nextcloud 27 code will not run on PHP 8.5. Fixed in our fork (476fe7e).
- Limitation: nsd still logs to `/var/log/nsd.log`, which its systemd sandbox does not let it write. Our fork switched it to syslog (1562989).

### Merge of v78 into the PR head (d7044d6)

- v78 itself only changes two things on top of v77: Z-Push 2.7.7 (#2608) and Roundcube 1.6.20 (#2611), plus its CHANGELOG entry and the bootstrap tag.
- Z-Push 2.7.7 merged without a conflict: the PR had already made the same version and hash change, and the PR's `timedatectl` edits stay as they were.
- `setup/bootstrap.sh` took v78's `TAG=v77 → v78`. That only touches the 22.04 branch; a 26.04 branch was added later in our fork.
- `CHANGELOG.md` took the upstream "Version 78 (October 22, 2026)" entry unchanged.
- The one conflict was Roundcube, in `setup/webmail.sh`: v78 has 1.6.20, the PR has 1.7.4. The merge took neither and used 1.7.5, the 1.7 security release that matches 1.6.20 (SHA1 `396b2fa…`, later re-pinned as SHA256). The PR's CardDAV 5.1.3 was kept.
- Apart from these, the merged tree is identical to the PR head (`git diff c6118db d7044d6` shows only these three files).
