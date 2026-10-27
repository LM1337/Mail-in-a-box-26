# Changelog of the Ubuntu 26.04 fork

Changes from Mail-in-a-Box v78, the last official upstream release (Ubuntu 22.04
only), to this fork. The fork is upstream PR #2603 (writeDavid's Ubuntu 26.04
port, head `c6118db`), merged with v78, plus its own fixes. Newest release first.
The base section at the end describes what the port itself changes.

Bug IDs such as **B01** refer to [BUGS-fork.md](BUGS-fork.md). Each entry there
documents the symptom, cause, fix and affected versions of one bug (v78 on 22.04,
PR #2603). For upstream's own history see CHANGELOG.md.

## Unreleased

### Planned

Seen in the work on rc7 and v78-r2604.0, not done (the certification runs
add their open findings in TESTING-fork.md):

* Setup restarts PHP-FPM once per run (B122), which ends ActiveSync long
  polls; a reload with a `process_control_timeout` would keep them.
* A failed ActiveSync or Autodiscover login takes 10 to 50 s (seen in the
  test of B126): Z-Push tries the IMAP login three times, and Dovecot
  delays failed logins, possibly more for an address with many failures,
  which for Z-Push is 127.0.0.1 for all users. Whether an attack below the
  `miab-zpush` threshold slows down the ActiveSync logins of other users
  is not measured.
* `miab-zpush` counts failures per address, like the other jails, and is
  always on: behind the shared servers of a mail app that syncs through its
  provider's cloud (Outlook for iOS and Android with an ActiveSync
  account), one person with a wrong password, or anyone on purpose, can get
  all users of that app banned, and repeated bans reach recidive's week on
  all ports (B126). The README, the upgrade note and the allowlist help say
  to put such networks on the allowlist; nothing finds them on its own.
  Leaving `miab-zpush` out of recidive would let an attacker guess 20
  passwords every few minutes for good, so it still counts there.
* The failed-login report does not read `nextcloud.log` yet, which now
  has the client's address for `/caldav`, `/carddav` and `/webdav` too
  (B121).
* Setup still restarts OpenDKIM and OpenDMARC (setup/dkim.sh), spampd,
  postgrey, named, systemd-resolved, munin-node and the management daemon
  on every run; while OpenDKIM restarts, Postfix lets mail pass unsigned
  (`milter_default_action`). Candidates for a reload or a restart only on a
  change.
* A Dovecot reload (B122) still has two client-visible moments: a login
  that the old login process hands to the new auth process at that moment
  fails as an internal failure (Nextcloud's `user_external` counts it as a
  failed login of the client; harmless for 127.0.0.1 after B121), and a
  FolderSync that Z-Push answers during the reload can come without the
  mail folders (seen once, for a new device's first FolderSync).
* Roundcube's CardDAV plugin can log "duplicate column name: account_id"
  when several sessions log in at the same moment for the first time after
  an upgrade of the plugin (a race in its schema migration).
* A Dovecot reload ends the open IMAP sessions (their clients log in
  again); setup reloads Dovecot only when its configuration changed (B122).
* Critical only (Munin's alerts) never mails the return to normal.
* The admin panel asks for `/admin/assets/branding/favicon.ico`, which is
  not installed (nginx 404).
* `postconf` warns that `smtpd_tls_dh1024_param_file` will be removed.
* Upstream code below `$STORAGE_ROOT`, which the user-data account owns:
  `management/backup.py` and `management/dns_update.py` still write
  `custom.yaml` as root with `open(..., "w")` (B87 covers only
  `settings.yaml`), and the nightly backup reads its target and
  `secret_key.txt` there by path. An account that can replace `backup/`
  could point the backups (of `$STORAGE_ROOT`, its own data) to a server of
  its own with a passphrase it knows. The fork's tools read them, and write
  the paused `custom.yaml`, only through a checked `backup/` of root's own
  (B117).

## v78-r2604.0 (2026-10-27)

The first release of the fork after seven release candidates, from the
update of a production box from rc6 to rc7 and the analysis of its
ActiveSync errors. Setup disturbs the clients less: it reloads Dovecot,
Postfix and fail2ban instead of restarting them, Dovecot only on a change
(B122), and no longer leaves Dovecot without a passdb (B120), Nextcloud
without a readable config.php (B124) or the logins at the end of a run
without users.sqlite (B133) for a moment; Nextcloud no longer throttles the
box's own services (B121). ActiveSync and Autodiscover get brute-force
protection (B126); Z-Push syncs contacts whose card name has no `.vcf`
(B128) and holds Pings of up to 59 minutes (B129), and the fork's changes
to it are one patch file, applied to a fresh copy (B126, B128); the
`/caldav`, `/carddav` and `/webdav` proxy passes the path as the client
sent it (B130). Security: `/etc/dovecot` belongs to root (B123), and the
control panel no longer writes password hashes into the journal or puts
passwords on a command line (B127). The backup page and the status checks
no longer hang or fail as a whole when a backup target does not answer
(B125, B132), and Roundcube's deny of its config directory is anchored
(B134).

### Fixed

* ActiveSync and Autodiscover have brute-force protection now: the new
  jail `miab-zpush` bans an address after 20 failed logins within 120 s on
  HTTP and HTTPS. Before, nothing limited password guessing there: Z-Push
  checks passwords against Dovecot from 127.0.0.1, which fail2ban ignores,
  and did not log failed logins. Setup turns on Z-Push's `LOGAUTHFAIL` (the
  lines go to `z-push-error.log` and `autodiscover-error.log`; `z-push.log`
  gets no more lines), escapes control characters in Z-Push's log lines and
  puts the client's address at the end of the ActiveSync message, so that a
  user name chosen by a client can neither add a line nor name another
  address for the jail. Z-Push writes the line only for a request with a
  user name and a password, so a phone's first request without credentials
  (it waits for the login prompt, also with its user in the URL) is not
  counted. `/var/log/z-push` belongs to root now (group www-data), so that
  www-data cannot replace the logs that fail2ban opens with a link or a
  FIFO; setup and logrotate (as root) create the log files (B126).
  A login that Dovecot or Nextcloud cannot check at that moment (Dovecot's
  "Temporary authentication failure", a connection that it closes or
  refuses) no longer counts as a failed login: Z-Push answers it with HTTP
  503 and `Retry-After`, which a phone retries without asking for its
  password, and logs no failed login (Autodiscover too: its configuration
  now defines `RETRY_AFTER_DELAY`). Before, such a login with the right
  password was counted (seen once in the update test under client load,
  while users.sqlite was locked, B133), and behind one shared address a
  few such moments could ban all its users from the web ports. Z-Push now
  escapes "]" and "\" in the user names at the start of its log lines, and
  the filter counts a line only when its message names the user of these
  brackets, so that no other warning, even one that ends in text from a
  client, can pass for a failed login. Setup removes a log file with more
  than one link (a hard link that www-data could have made to a file of
  another account) before it gives the log files to www-data (B126).
* Logins no longer fail for a moment at the end of each setup run: setup
  rewrote the automatic aliases in `users.sqlite` every time (since rc4,
  B60), and Dovecot, which reads that database for every login and waits
  at most one second for a lock, answered "Temporary authentication
  failure" (`database is locked` in `mail.log`) to the IMAP, POP3, SMTP
  AUTH and ActiveSync logins of that moment when the commit took longer on
  a busy disk. Setup and the control panel now write the table only when
  it changes (B133).
* Nextcloud's brute-force protection no longer throttles the box's own
  services (seen on a production box at the update from rc6 to rc7):
  setup restarted Dovecot, Nextcloud's `user_external` could not reach IMAP
  for about two seconds, and the CalDAV/CardDAV logins that Z-Push makes
  from 127.0.0.1 failed (12 in two seconds). Nextcloud then answered Z-Push
  with `TooManyRequests` for every user for about 30 minutes, and kept a
  25 s delay after that, so ActiveSync calendars and contacts did not sync.
  Setup now puts 127.0.0.1 on Nextcloud's brute-force bypass list (Z-Push
  checks each password against Dovecot first), on a fresh install, a
  migration and an update, unless Nextcloud already bypasses it, and resets
  its attempts when it adds it, so a throttled box syncs again after the
  update. So that clients on the Internet do not get that bypass too, the
  proxy of `/caldav`, `/carddav` and `/webdav`, which connects to Nextcloud
  from 127.0.0.1, now passes the client's address (`X-Forwarded-For`), and
  Nextcloud takes it from 127.0.0.1 only (`trusted_proxies`): these clients
  are throttled under their own address, and the miab-owncloud jail can ban
  them, which it never could on these paths (B121).
* Nextcloud no longer fails a request (an ActiveSync login got HTTP 401)
  while setup rewrites its `config.php`: root replaced the file with one only
  root could read and gave it to www-data a moment later. The file is now
  written as www-data and replaced atomically (B124).
* `/etc/dovecot` belongs to root now (group `mail` may read): it belonged
  to the account `mail`, which all IMAP, POP3 and LMTP processes run as and
  which could therefore change Dovecot's configuration (read by its root
  processes) and the files that setup writes there as root (B123).
* Dovecot no longer runs without a passdb for two seconds during setup:
  setup restarted it before rewriting `auth-sql.conf.ext`, and a login in
  that moment made Dovecot's config process read the truncated file;
  logins then failed as wrong passwords. Dovecot's configuration is now
  loaded once, after all of it is written, and setup writes Dovecot's files
  (and every file of `tools/editconf.py`) atomically and only when they
  change, following a symbolic link only in a directory of root's own
  (B120).
* Setup disturbs the clients less: Dovecot, Postfix and fail2ban reload
  instead of restarting (Dovecot not at all when its configuration did not
  change), PHP-FPM restarts once per run instead of four times, and
  fail2ban keeps its bans through setup (it lifted all of them for about
  two seconds at each of its two restarts). A service is still restarted
  when it does not run, runs the program of an older package, or still
  uses a library that an upgrade replaced (such as libssl or python3; the
  restarts of earlier versions picked these up on every run). Dovecot's
  checksum covers its settings only (not the kernel and OS version that
  `doveconf -n` names), and is recorded only once Dovecot has loaded the
  configuration; if it has not within 10 s of the reload, setup restarts it
  (B122).
* The backup page of the control panel and the backups no longer hang for
  a minute or more when the rsync target does not answer a connection
  request at once (seen on a production box with a Hetzner Storage Box: ssh
  waited 11 s for an answer over IPv6, and twice the page showed only
  "Something went wrong" after 60 s). ssh to the target now gives an
  address 10 s for the connection and the SSH banner, then tries the next
  one, and makes two attempts, instead of waiting for the kernel's TCP
  retries; the list of the target's files (status page, and the nightly
  backup's choice between a full and an incremental backup) is tried three
  times (B125).
* The control panel no longer writes the password hash of a user into the
  journal at each login (`{SHA512-CRYPT}$6$... (verified)` or "reverse
  password verification check failed", the output of `doveadm pw`), and a
  password that the management daemon checks or sets is no longer in a
  command line, which every local account can read: the daemon hashes and
  checks SHA512-CRYPT itself (Python's crypt module is gone since 3.13) and
  compares in constant time. It writes the same hashes as before and checks
  every form MIAB and Roundcube store (with and without `rounds=`); other
  schemes go to `doveadm pw -t`, with the password on its standard input;
  a password stored in plain text by hand (`{PLAIN}`, `{CLEAR}`, `{CLEARTEXT}`,
  `{PLAIN-TRUNC}`) is compared by the daemon itself, so that it is not in
  doveadm's arguments either. A login with an unknown address takes as long as a wrong password. Setup
  no longer puts the first user's password, and tools/dns_update and
  tools/web_update no longer the API key, on a command line either (B127).
* The backup page shows the status of the backups at once: the status
  saved after the last backup run or refresh that worked, with its time.
  It refreshes it in the background (on a visit when the saved status is
  older than five minutes, and with the new "Refresh now" button) and
  shows a failed refresh with its error next to the saved status. Before,
  the page queried the target while it loaded, and the whole control panel
  waited with it (its service has one worker): on a production box once
  more than a minute, until nginx gave up. The refresh is a process of its
  own (`management/backup.py --refresh-status`); the nightly backup waits
  for one in progress and saves the status at its end. The refresh logs its
  duration and those of its steps (duplicity's collection-status, the list
  of the target's files) in the journal of the management daemon; what
  duplicity, rsync and ssh say on stderr is part of the error shown, no
  longer written into that journal. A refresh is ended after 15 minutes,
  with the rsync and ssh that duplicity started (only those of its own
  session: run by hand from a shell, `backup.py --refresh-status` ends
  nothing else, not the other commands of a pipeline). New API
  calls `GET /system/backup/status/saved` and
  `POST /system/backup/status/refresh`; `GET /system/backup/status` still
  queries the target, but waits for it 30 s at most and not at all while a
  backup runs: it then returns the saved status at once, with
  `in_progress` saying why (it would hold the control panel for as long).
  `tools/update-check.sh backup` no longer takes such a refresh for a
  running backup, and still stops for any other run of `backup.py` (B125).
* The status checks no longer stop as a whole when the status of the
  backups cannot be read (the target does not answer, or another duplicity
  runs on the same archive directory): the System Status page showed only
  "Something went wrong" and the nightly check mailed a traceback. The
  backup check now fails alone with duplicity's message, and while a backup
  run or a refresh of the backup page queries the target it uses the saved
  status, or warns that none has been saved yet (B132).
* nginx waits for the control panel as long as gunicorn lets a request
  run (630 s) instead of its default of 60 s, so that the status checks,
  the TLS provisioning and the backup page's live query are no longer cut
  off with a 504 after a minute (B125).
* The control panel says what happened when its service does not answer:
  for nginx's 502 and 504, a timeout and a lost connection it shows a
  clear message and what to do, on every page, instead of only "Something
  went wrong, sorry." (B125).
* ActiveSync syncs the contacts of users with a card whose name has no
  `.vcf`, such as Nextcloud's example contact `default`, which users whose
  first Nextcloud login was on rc3 to rc6 still have (B99 stopped new ones
  only), and the cards of clients that name them that way. Z-Push asked
  for every card with `.vcf` added and, for such a card, failed with a PHP
  error: the whole Sync answered HTTP 500, every time. Setup now changes
  Z-Push's CardDAV client (conf/zpush/z-push.patches, applied by the new
  `tools/patch_source.py`, which stops setup if a change does not apply):
  it asks once more without `.vcf`, skips a card the server
  does not return instead of failing, and changes or deletes such a card
  from the phone under its own name, keeping its UID (B128).
* A phone's ActiveSync Ping (push) with a heartbeat of more than 630 s no
  longer ends with HTTP 504 after 10.5 minutes (seen on a production box:
  68 in a day, all Pings of one iPhone, spread over the whole day). nginx gave up on
  Z-Push, which waits as long as the phone asks; the PHP process went on
  waiting, and a change it found then reached the phone only with its next
  Ping. nginx now waits up to 3660 s on `/Microsoft-Server-ActiveSync`, and
  Z-Push allows a heartbeat of at most 3540 s, the protocol's maximum: a
  Ping that asks for more gets status 5 with that bound, and the phone
  pings with it. Phones keep their long heartbeats and wake up less often.
  A Ping without a heartbeat of its own now waits 3540 s instead of 600 s
  (Z-Push's default is the bound), and setup warns if Z-Push's config.php
  has no line for the bound (B129).
* The proxy of `/caldav`, `/carddav` and `/webdav` to Nextcloud passes the
  path escaped, as the client sent it, and the query string. It passed
  nginx's decoded path: a name with a space got HTTP 400, an escaped `?`
  began a query string (a DELETE of a card named `?x.vcf` deleted the whole
  address book on a test box), and a query such as `?export` was dropped.
  Only clients set up with these short paths were affected, not those with
  the `/cloud/remote.php/...` URLs or `.well-known`, and not Z-Push. Files
  and cards whose names begin with `.ht`, `.git`, `.svn`, `.hg` or `.bzr`
  pass through these paths as before (nginx's dotfile block does not apply
  to them; B130).
* A path with `/mail/config/` in it no longer gets HTTP 403 unless it is
  Roundcube's config directory (`/mail/config/...` itself): nginx's deny of
  that directory was an unanchored regex (upstream), which also caught
  Nextcloud files and folders below a folder `mail/config` (through
  `/cloud/remote.php` and the `/webdav` proxy) and the pages of static
  sites under such a path. It is anchored now (`^/mail/config/`; B134).
* The release tag is an annotated tag, as CONTRIBUTING.md asks. The tag
  first made for this release on the fork's internal server was a
  lightweight one, which `git describe` without `--tags` does not see:
  the test boxes installed from it showed their commit id as their version
  (status checks, control panel, setup) and bootstrap.sh fetched again on
  every run (B135; never published).
* A fresh install no longer stops at once on a machine whose DNS resolver
  is a public one (1.1.1.1, and the default resolvers of many hosting
  providers), saying that the hostname is listed in the Spamhaus Domain
  Block List. Spamhaus refuses queries through such resolvers and answers
  127.255.255.254, which setup took for a listing (upstream). Setup now
  stops only on a listing (DBL 127.0.1.2 to 127.0.1.99, ZEN 127.0.0.2 to
  127.0.0.11), shows any other answer as a check it could not make, and
  goes on; the status checks look again later through the box's own
  resolver (B136).

### Changed

* Control panel (System > Intrusion Protection): `miab-zpush` is a web
  jail (its bans keep their fixed length with adaptive banning), the slow
  web jails get `miab-slow-zpush` (ActiveSync and Autodiscover), and the
  failed-login report and its status check read Z-Push's error logs as well
  (protocols `activesync` and `autodiscover`, also the files of the last
  rotation). The help texts name ActiveSync and say that `/caldav`,
  `/carddav` and `/webdav` now count under the client's address; the
  allowlist help names the servers of mail apps that sync through their
  provider's cloud (B126, B121).
* Tests: the smoke test's fail2ban status check wants `miab-zpush` (and
  `miab-slow-zpush` with the slow web jails), `fail2ban-filters` has cases
  for the new filter (an e-mail address and user names with
  " from IP 198.51.100.7." in them, an escaped line break, a request without
  credentials, Z-Push's own order of the message), and the fail2ban group bans the peer through
  failed ActiveSync and Autodiscover logins (`fail2ban-activesync`,
  `fail2ban-autodiscover`; it asks only the jails that run, so that a slow
  jail that is off logs no error). `fail2ban-activesync-noauth` sends 25
  ActiveSync requests as a phone sends its first one (a user of the box in
  the URL, no credentials) and wants 401, no failed-login line and no ban.
  More filter cases: user names that differ in case, the form
  `[<user>#<user of the request>]` with an escaped "]", Autodiscover's
  `[#unknown]`, and other warnings that end in the text of a failed login
  (none may match). With `--load-since TIME` (and `--load-ip ADDR`, default
  `--peer`) the new first check `load-no-failed-login` fails when fail2ban
  found a failure of these addresses, or Z-Push logged a failed login from
  them, since TIME: for the client load of an update test, which uses the
  right passwords only (B126).
  The log audit accepts what these
  deliberate failures log (Z-Push's three IMAP tries, its exception and the
  new warning; for Autodiscover, which names no user in brackets, only with
  `--smoke`), and with `--internet` the same lines as password guessing.
* `management/cli.py user add EMAIL -` and `user password EMAIL -` read the
  password from standard input (its first line) instead of the command
  line, which every local account can read; without a password they still
  ask for it. Its usage text says so (B127).
* Tests: the smoke test's new check `admin-journal-no-hash` (with `--ssh`)
  fails when a line of the journal of `mailinabox.service` since the start
  of the run looks like a password hash or the output of `doveadm pw`, and
  when journalctl fails or may not read the journal (B127).
  `tests/fork/password-hash.py` checks the control panel's SHA-512 crypt:
  the test vectors of its specification, the plain-text schemes (without a
  call of doveadm) and its limits without a box, and with `--doveadm` (on a
  box, as root) random passwords against Dovecot's `doveadm pw` both ways,
  other schemes through the fallback and the plain-text schemes against
  doveadm's own result.
  The log audit no longer accepts doveadm's "reverse password verification
  check failed" (smoke and Internet lists): the daemon no longer logs it.
* Tests: the log audit's rule for Postfix's milter warnings while setup
  restarts OpenDKIM or OpenDMARC also accepts a reset later in the milter
  session (`SMFIC_MAIL` and the other commands), not only in the handshake.
  The GitHub counter-test of rc7 (rc6 to rc7) logged it once.
* Tests: the smoke test's new group `activesync` (also right after a setup
  run with `--only activesync`) checks Nextcloud's bypass list (127.0.0.1
  listed, no entry twice: `nextcloud-bruteforce-loopback`), that a failed
  login through the `/webdav` proxy is counted for the client's address and
  not for 127.0.0.1 (`nextcloud-forwarded-for`), and syncs a marked event
  and contact through ActiveSync (`zpush-sync`, with the new small client
  `tests/fork/eas.py`).
* Tests: `tests/fork/client-load.py` keeps the clients of a few users busy
  while setup runs, at the rate that reproduced the production incident:
  per user several ActiveSync devices (`--ping-devices`, `--sync-devices`;
  Sync of the inbox, the calendars and the contacts, Ping, recovery as a
  phone does it after HTTP 449 and resync statuses), CalDAV/CardDAV (also
  through the `/caldav` proxy), IMAP logins and IDLE, SMTP AUTH and
  Roundcube. `--seed` puts a marked event, contact and mail into each
  account first, `--log` records every request with its latency, and with
  `--marker-file` the results before setup are a baseline: an error that
  already occurred there does not fail the run. Outages are counted per
  client and user. The update scenarios run one instance on the box and one
  on another host of the test network, which fail2ban and Nextcloud count
  under a real address (TESTING-fork.md, "Client load during updates").
* Tests: the log audit no longer accepts "No passdbs specified" during
  setup (B120). It accepts what Dovecot logs when setup reloads it (also the
  SIGTERM of the IMAP, POP3, ManageSieve and login processes of the old
  configuration), what nginx logs for the ActiveSync and CalDAV/CardDAV
  requests that the one PHP-FPM restart ends (also nginx's `readv()` reset
  of a response it has begun to read, seen in the update test after the
  merge of B125 to B127), and what Postfix and OpenDKIM
  log when a client comes in during setup's restart of OpenDKIM (also
  "Application error"), and fts-xapian's retries of its write lock when two
  processes index a new folder at once (BUGS-fork.md, known limitations).
* Tests: the smoke test's `zpush-sync` also syncs a marked card whose name
  has no `.vcf` (B128).
* Tests: the smoke test's new check `zpush-ping` (group `activesync`): a
  Ping with a heartbeat of 3600 s gets status 5 with the box's bound at
  once, a Ping of 20 s completes, and with `--ssh` nginx's
  `fastcgi_read_timeout` of every `/Microsoft-Server-ActiveSync` location
  is at least a minute longer than that bound; it reads nginx's time units
  and a value set for the server or http block (B129).
  `tests/fork/eas.py` has `Client.ping_answer` (status, the server's
  heartbeat and the changed folders, also for status 5, with a timeout),
  and its `--ping` accepts status 5 and prints the bound.
* Tests: the smoke test's new check `nextcloud-dav-proxy` (group `web`):
  a card whose name has a space and a `?` is read, found in `?export` and
  deleted through `/carddav`, and the address book stays; a file named
  `.htmiab-smoke-...` put through Nextcloud's own path is read through
  `/webdav`, and a card `.gitmiab-smoke-...vcf` through `/carddav`, as
  nginx's dotfile block must not apply there; `/caldav` and `/webdav`
  answer PROPFIND (B130).
* Tests: the smoke test's new check `nextcloud-mail-config-path` (group
  `web`): `/mail/config/...` still answers 403, a missing static page
  under `/<name>/mail/config/` answers 404, and a file put into Nextcloud
  below a folder `mail/config` is read through `/cloud/remote.php` and
  through `/webdav` (B134). The log audit's smoke list accepts nginx's
  line for that missing page.
* Tests: the smoke test's `zpush-ping` waits 90 s at most for the answer
  to its Ping of 3600 s (on a box without the bound it waited for nginx's
  504 after 635 s, and left Z-Push waiting for up to an hour): no answer
  within 90 s fails the check, and a Ping of 60 s of the same device ends
  the long one in Z-Push (about 2.5 minutes in all, and no Ping is left).
* Setup makes every change of the fork to Z-Push's code in one way: the
  changes of B126 (the escaped log lines and user names, the message and
  condition of a failed login, the 503 for a temporary login failure in
  the IMAP and combined backends), which it made with sed in the installed
  tree, are blocks of conf/zpush/z-push.patches now, with those of B128.
  Setup applies the file to a fresh copy of Z-Push in a directory of
  root's own before it moves the tree to `/usr/local/lib/z-push`, and stops
  if a block does not apply; for the lines the miab-zpush jail relies on,
  the file also names text that must not be left. The tree is marked with
  the version and a checksum of the file's blocks
  (`/usr/local/lib/z-push/version`, such as `2.7.7+patches-<16 hex digits>`,
  from `tools/patch_source.py --digest`; a comment in the file does not
  change it): a change of any block, or a tree that no longer has every
  change (a file changed by hand, checked with `tools/patch_source.py
  --check` on every run), gets a fresh copy of Z-Push on the next setup run
  (B126, B128). The copy is made next to `/usr/local/lib/z-push` (on the
  same file system), patched and configured there, and replaces the old
  tree with two renames, so that no request finds Z-Push without its
  configuration (before, for the moment of about ten steps, requests ran
  with Z-Push's own defaults: no backend, so every request failed, and no
  logging of failed logins). Before, setup also removed the old tree first
  and moved the new one from `/tmp`, a tmpfs on Ubuntu 26.04, so that mv
  copied it file by file: in the update test under client load, two
  ActiveSync requests in that second found Z-Push's files without
  permissions for www-data and ended with a PHP fatal error. On every
  setup run Z-Push's configuration files are written atomically and only
  when they change (`tools/write_conf.py`); before, each backend's
  `config.php` was removed and copied again, and was missing for a moment.
  The mark is written last, after Z-Push's `fixstates`: a setup run that
  stops in between installs Z-Push again at the next run instead of
  leaving out that step, and a temporary directory that such a run left in
  `/usr/local/lib` is removed then. `tools/patch_source.py` refuses a block
  with an empty new text, which it could never count as applied (setup
  would have stopped on every run).
* Tests: the log audit accepts, in a setup run, what the update from rc7
  logs once: the new jail `miab-zpush` skipping the older lines of Z-Push's
  error logs at its first start, and the login that setup's Dovecot reload
  cuts (B122, open finding) as the Z-Push of rc7 answers it (401) before
  setup installs the new one; and Nextcloud's IMAP check of a password that
  such a reload cuts (curl: "Failure when receiving data from the peer",
  "Weird server reply") or fails ("Login denied"). The rule for that 401 is
  in the new `tests/fork/log-audit-allow-from-rc7.txt`, not in the default
  list: in a setup run of the fork's Z-Push, which answers such a login
  with 503, a 401 would be a regression of B126. `tools/update-check.sh
  after` adds that list by itself when the state before the update has no
  mark of the fork's Z-Push (rc7 or earlier); a log audit of your own across
  such an update needs `--allow-extra tests/fork/log-audit-allow-from-rc7.txt`.
  The classes of `nextcloud.log` get the prefix `[setup]` in a setup run
  too, as those of the other logs; the rules for them accept it. In a setup
  run the log audit also accepts fail2ban's "Unable to get failures in
  <log file>": its reload at the end of setup removes a jail's log files
  while the jail may be reading a line just written there (fail2ban 1.1.0,
  seen once in the update test under client load).
* Tests: the smoke test's new check `zpush-patches` (group `activesync`,
  with `--ssh`): `/usr/local/lib/z-push/version` carries the checksum of
  the blocks of the checkout's conf/zpush/z-push.patches, and the installed
  tree has every change of it (B126, B128).
* `tools/update-check.sh after` also uses `tools/expected-changes/unreleased.txt`,
  the changes since the newest release, when the checkout after the update
  is not at a release tag (bootstrap.sh with `TAG=<branch or commit>`) or
  the new version has no list of its own; before, such an update matched no
  release list and every change of the release was UNEXPECTED. The new list
  names the jail `miab-zpush` (and `miab-slow-zpush`, B126) and the mark of
  Z-Push (B126, B128), which the tool now records (`version.txt`: `zpush
  2.7.7+patches-<16 hex digits>`). Every update may also change the version
  named by the status checks, and an update to a branch or commit records
  its commit id as the version (`any.txt`).
* Nextcloud's calendar app 6.6.3 → 6.6.4 (bug fixes; for the fresh install
  and the steps of the upgrade chain to 32, 33 and 34), SHA256
  `0557b6b5852a467cf3f746e59d56478d227f78bf7a66357b30dfc10cae4c7e3c`
  (computed from the download, the same as GitHub's digest of the release
  asset). Its `appinfo/info.xml` accepts Nextcloud 32 to 35 and PHP 8.1 to
  8.5, as 6.6.3's did. Setup installs the pinned apps only together with a
  new Nextcloud version (as upstream; the app store is off), so a box that
  already runs Nextcloud 34.0.5 keeps its calendar app at the update. The
  other pinned components were checked against their upstream releases on
  2026-10-27 and are current.
* `tools/update-check.sh` writes its empty local variables as `''`
  (shellcheck SC1007); no change in what it does.

### Upgrade note

* Boxes on rc7 are updated with the bootstrap command of "Updating the
  fork" in README-fork.md,
  `sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/setup/bootstrap.sh)"`.
  Before it: put back the files changed by hand in `/root/mailinabox`
  (`git -C /root/mailinabox status --short` lists them, `sudo git -C
  /root/mailinabox checkout -- FILE` puts one back), such as the hotfixes of
  rc7 in `management/backup.py` (B125) and `conf/nginx-alldomains.conf`
  (B129), which this release sets itself; and check that the box reaches
  GitHub for the one-time download of Z-Push: `curl -fsSIL
  https://github.com/Z-Hub/Z-Push/archive/refs/tags/2.7.7.zip > /dev/null
  && echo OK` (both explained below). rc7 has `tools/update-check.sh`:
  `before` and `backup` before the update, `after` and `mailcheck` after
  it, all from `/root/mailinabox/tools/`; `after` judges the changes by
  `tools/expected-changes/v78-r2604.0.txt` (and `any.txt`).
* Boxes on rc1 to rc6 are updated the same way, with the steps of rc7's
  upgrade note first: `sudo git -C /root/mailinabox remote set-url origin
  https://github.com/LM1337/Mail-in-a-box-26` for rc1 to rc3, and
  `tools/update-check.sh before` and `backup` through `curl ... | sudo bash
  -s -- STEP`, as these releases have no copy of the tool. Read the upgrade
  notes of every release in between; `after` uses the lists of rc7 and of
  v78-r2604.0.
* Z-Push's message for a failed ActiveSync login reads "Failed to
  authenticate user '...' from IP ...." now (Z-Push: "IP: ... failed to
  authenticate user '...'"), and control characters in Z-Push's log lines
  are escaped (a multi-line message is one line with `\n`). A fail2ban
  filter or log tool of your own for Z-Push needs the new form. A request
  without a password no longer logs that message.
* `/var/log/z-push` belongs to root, group www-data (0750), and Z-Push can
  no longer create files there: setup creates `z-push.log`,
  `z-push-error.log`, `autodiscover.log` and `autodiscover-error.log`, and
  removes what is not a regular file there. Per-user logs of your own
  (`$specialLogUsers` in Z-Push's `config.php`) need their files created
  the same way (www-data, 0640).
* Outlook for iOS and Android syncs an Exchange ActiveSync account through
  Microsoft's servers: if your users do that, put those networks on the
  fail2ban allowlist, or 20 wrong passwords entered there within two
  minutes ban these servers from the web ports for all of these users.
  Not only a user can cause that by mistake: anyone can do it on purpose,
  with any account name and a wrong password in the app, and repeated bans
  of these addresses lead to recidive's ban of one week on all ports
  (B126).
* Z-Push escapes "]" and "\" in the user names at the start of its log
  lines (`[a\]b]`), and Autodiscover's lines start with `[#unknown]`. A
  filter of your own that reads the user names there needs to allow for
  that. A temporary login failure (Dovecot or Nextcloud cannot check the
  password at that moment) is answered with HTTP 503 now and logs
  `Exception: (ServiceUnavailableException)` instead of a failed login
  (B126).
* The backup page shows "No status of this backup target has been saved
  yet" on the first visit after the update, until its first refresh (or
  the next backup run) ends. The saved status is kept in
  `/var/lib/mailinabox/backup-status` (root only).
* Setup sets Nextcloud's `trusted_proxies` (adds 127.0.0.1, keeps the
  others) and `forwarded_for_headers` (`HTTP_X_FORWARDED_FOR` only, the
  Nextcloud default; another value there is replaced). A reverse proxy of
  your own in front of the box keeps working when it sends
  `X-Forwarded-For`.
* `/etc/dovecot` changes from `mail:dovecot` to `root:mail` (no write for
  the group, nothing for others). Your own files there stay readable by the
  mail processes; give a file that other processes must read other
  permissions in another place.
* The first update with this release reloads Dovecot once (its open IMAP
  sessions log in again), as the checksum of its configuration is new.
* The password hashes that the control panel's logins wrote before (B127)
  stay in the journal and in `/var/log/syslog` until these are rotated
  away. To remove them at once: `journalctl --rotate` and
  `journalctl --vacuum-time=1s` (this deletes the whole journal up to now),
  and delete the syslog files that hold such lines, the compressed rotated
  ones (`syslog.2.gz` and older) too: `zgrep -l 'verified)'
  /var/log/syslog*` lists them all (plain `grep` does not look into the
  `.gz` files). Otherwise they stay until logrotate drops them. The nightly
  backups do not contain `/var/log`.
* A new password with a null character or of more than 511 bytes is now
  refused with a message (B127). Before, such a password gave a hash that no
  password matched. Existing passwords are not changed.
* Setup changes a few functions of Z-Push 2.7.7 (conf/zpush/z-push.patches)
  in a fresh copy before it installs it in `/usr/local/lib/z-push`, and
  stops with a message if one of them does not apply. A tree in
  `/usr/local/lib/z-push` that no longer has every change (changes made
  there by hand) is replaced by a fresh copy at the next setup run, and
  the changes made by hand are lost. The first update with this release
  downloads Z-Push 2.7.7 from GitHub once more (its directory is marked
  with a checksum of the fork's changes now), so the box needs to reach
  GitHub during the update, as at a new Z-Push version: check it before
  the update with `curl -fsSIL
  https://github.com/Z-Hub/Z-Push/archive/refs/tags/2.7.7.zip > /dev/null
  && echo OK`. If the download fails, setup stops (after Nextcloud's step,
  before PHP-FPM and the control panel are restarted; the old Z-Push keeps
  running): run it again (`sudo mailinabox`) once GitHub is reachable. A
  later edit of conf/zpush/z-push.patches that changes a block makes every
  box download Z-Push again the same way; a comment does not. Nextcloud's example
  contact now syncs to phones like any other contact; delete it in
  Nextcloud's Contacts if it is not wanted. A phone that got HTTP 500 needs
  no new setup: its next Sync continues (B128).
* After the update, a reload of nginx keeps its old worker processes until
  their running ActiveSync long polls end, up to an hour (before: 10.5
  minutes). Pings of up to 59 minutes hold a PHP-FPM worker each, as they
  already did past nginx's old timeout (B129).
* `/caldav`, `/carddav` and `/webdav` are now prefix locations of nginx: a
  proxy of your own for one of these paths (`www/custom.yaml`) would now
  clash with them (B130).
* A reverse proxy or firewall of your own in front of the box must keep an
  ActiveSync request open for an hour (3660 s) too, or it ends the long Pings
  instead of nginx (B129).
* Put back every file that you changed by hand in `/root/mailinabox`
  before the update, or bootstrap.sh stops with "Update failed. Did you
  modify something in /root/mailinabox?" (git refuses to check out over a
  changed file). `git -C /root/mailinabox status --short` lists them, and
  `git -C /root/mailinabox checkout -- FILE` puts one back. Hotfixes of
  this release made by hand on a box on rc7 are such files: the ActiveSync
  timeout in `conf/nginx-alldomains.conf` (the template nginx's
  `local.conf` is built from, so the change survived the nightly rebuild;
  B129) and the ssh options in `management/backup.py` (B125). The release
  sets both itself. Hand changes to Z-Push's own `config.php` (such as
  `PING_HIGHER_BOUND_LIFETIME`) need nothing: the update installs Z-Push
  again, and setup sets the bound.

### Done from the plan

From the plan for the final release: the list of expected changes of this
release (`tools/expected-changes/v78-r2604.0.txt`, renamed from
`unreleased.txt`, with a new, empty `unreleased.txt` for the next release).
The test matrix T1 to T5b and T6 (on the Internet: Let's Encrypt, delivery
to other providers, `mailcheck` with a real external probe) run on the
release commit; their results are in TESTING-fork.md.

## v78-r2604.0-rc7 (2026-10-25)

From the update of a production box from rc3 to rc6: Munin's alerts are set
in the admin panel, the management API is tested end to end against its
documentation, and an update gets its own tools: the state of the box before
and after, a backup before it, a comparison with the expected changes and an
active mail check. The in-place tool runs a fallback SSH server while the
release upgrades replace OpenSSH. Setup reloads nginx instead of restarting
it, no longer shows the welcome dialog on an update, and writes the OpenDKIM
tables in a fixed order. Security: setup no longer sources or unpacks
anything as root by a fixed name in `/tmp` (B89, B97), and root no longer
writes through symbolic links in directories of other accounts (B86, B87,
B90, B98). The management daemon no longer runs out of file descriptors
(B91), and ActiveSync syncs the contacts of new users again (B99). The
review of the merged release found B100, B101 and B103 to B105 in the new
fallback SSH server, the update tools and the log audit, and B102 in the
in-place tool's copy to an rsync target (all fixed). The certification runs
of rc7 (T1 to T5b) found B106 to B110 and B114 in `tools/update-check.sh` and
its lists of expected changes, B111 and B112 in the fallback SSH server and
B113 in the migration tool's check; the review of those fixes found B115 and
B118 in the fallback SSH server, B116 in `tools/update-check.sh` and B117 in
how the tools use `$STORAGE_ROOT/backup`, and the test runs after it B119 in
the fallback SSH server (all fixed).

### New

* Munin: an admin panel setting for Munin's alerts, under System > Munin
  Monitoring: to the standard address administrator@PRIMARY_HOSTNAME, to a
  custom address, or off; warning and critical (the default) or critical
  only; a button that sends one test notification to the saved recipient
  (subject "Munin test notification", header `X-Miab-Test: 1`, through the
  same command as the alerts, as user munin). `management/munin_admin.py`
  stores the setting as `munin_alerts` in `$STORAGE_ROOT/settings.yaml`
  (only values that differ from the defaults) and makes the whole
  `/etc/munin/munin.conf` from it; setup/munin.sh writes it with `--setup`,
  the daemon when the setting is saved (only if the file differs; Munin
  reads it on its next run). Without the setting the file is byte for byte
  the one of rc6. Off: no contact and `contacts none`; critical only: a
  `contact.admin.text` that leaves out the plugins without a critical
  value, and munin-notify sends nothing for an empty text. Still no
  `always_send`. A custom address must be a plain address (ASCII letters,
  digits and `_ + - .` before the @, no name, quotes, spaces, line breaks
  or shell characters): munin-limits execs the contact's command line, and
  munin-notify checks the address again (`--to`) and passes it to sendmail
  as a separate argument after `--`. The sender stays administrator@. API
  (admin only): `GET`/`POST /system/munin/alerts`,
  `POST /system/munin/alerts/test`. README-fork.md, "Munin alerts".
* API documentation: `api/mailinabox.yml` documents every route of the
  management daemon: the quota endpoints (`/mail/users/quota`), the Munin
  session (`/munin/`), the intrusion protection (`/system/fail2ban`,
  `/settings`, `/unban`, `/unban-all`, `/report`) and Munin's alerts. The
  answers to missing or wrong credentials are documented as they are: 401
  with `WWW-Authenticate` and `X-Reason`, as text or JSON by the `Accept`
  header, and 403 for XMLHttpRequests (it said 403 text/html). Fixed
  content types: `/dns/zonefile/{zone}` is text/plain, `/dns/update`
  text/html, `POST /system/backup/config` a JSON string (also for a refused
  configuration, with 200); `latest-upstream-version` can answer 500 and
  503; the login status can be `missing-totp-token`.
* Tools: `tools/update-check.sh`, the checks around an update of a box of
  this fork, as root (also through `curl ... | sudo bash -s -- STEP`):
  * `before` records the state of the box in
    `/root/update-check/<stamp>/before/` (mode 0700; `UPDATE_CHECK_DIR`
    elsewhere only below directories of root's own): version and origin of
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
    and `--docker-volume` (one archive per volume, B104), and a pg_dump of
    each container named with `--postgres` (with its `POSTGRES_USER` and
    `POSTGRES_DB`); the names and mount points are checked before the
    Mail-in-a-Box backup. Everything is encrypted with gpg (AES256, the
    passphrase of the Mail-in-a-Box backups) as it is written; only the
    package and configuration listings that go into the system archive are
    written in plain text first, in the root-only stamp directory, and
    removed after it. For an rsync target
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
    message class, 2 when nothing is unexpected but the log audit could not
    run.
  * `mailcheck` sends a marked mail (`X-Miab-Test: 1`, a unique token) from
    administrator@PRIMARY_HOSTNAME (`--from`) to an external probe address
    (`--probe` or `PROBE_ADDRESS=` in `/etc/mailinabox.conf`, which setup
    keeps when it rewrites the file, B103) that forwards
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
  groups sudo and admin, also on a box without a group admin, B100, and
  root if `PermitRootLogin` allows keys;
  `UPGRADE_SSH_FALLBACK_USERS` names others), whose keys it copies (read as
  the user) into a root-owned directory, listens on the ListenAddress
  addresses of the running sshd, keeps its AllowUsers, AllowGroups,
  DenyUsers, DenyGroups, PubkeyAuthOptions, ForceCommand, ChrootDirectory,
  PermitTTY and algorithms, and allows no forwarding. It does not start
  where sshd asks for more than a key (`AuthenticationMethods`), accepts no
  keys, or has `Match` blocks in `sshd_config` or its included files
  (`sshd -T` does not apply them), so it never lets in with a key alone whom
  sshd asks for more (B101). ufw lets the port through (rate limited) only
  while it runs.
  It is stopped, and the port closed, when port 22 answers again after the
  release upgrade and on every way out of the tool (also after Ctrl-C);
  while port 22 does not answer it stays until the next reboot, and the next
  run removes it and its ufw rule. Port 22 counts as answering when its SSH
  banner comes on one of the listen addresses of sshd (not only
  127.0.0.1). `--ssh-fallback-test` starts it for 10 minutes
  (`UPGRADE_SSH_FALLBACK_TEST_SECONDS`) before an upgrade, to try a login on
  its port.
* Tools: `tools/upgrade-in-place-to-2604.sh` says in the run when the release
  upgrade has stopped the SSH server on port 22 and when port 22 answers
  again (its SSH banner), with the minutes in between.
* Setup marks its start and end in the journal ("Mail-in-a-Box setup
  started", "Mail-in-a-Box setup ended (exit code N)", identifier
  `mailinabox-setup`). `tests/fork/log-audit.sh` prefixes what the box logs
  in between with `[setup]` (outside the phases of an in-place upgrade;
  only marks that root logged count, B105),
  and allowlist rules that start with `^\[setup\]` accept a class only
  there: connections that setup's restarts of the services cut are normal
  during setup and a finding at any other time. The report names the setup
  runs (`setup_runs` in the JSON report).
* Tests: `tests/fork/smoke.py` group `api` (in every scenario): `api-auth`
  (401 without credentials, as text and JSON, 403 for an XMLHttpRequest,
  401 for a wrong password, the API key, a second session until its logout
  and 401 after it; two failed logins in all), `api-read-only` (29
  documented read-only endpoints, with `system/status`,
  `system/latest-upstream-version`, `ssl/csr` and `mfa/status`: status 200,
  content type and shape), `api-write-roundtrip` (a marked user with
  password, quota and the admin privilege on and off, an alias, a custom
  TXT record with POST, PUT and DELETE, privacy set to its own value; the
  user removed with its archived mailbox; users, aliases, custom records
  and privacy the same afterwards) and `api-munin-alerts` (invalid
  addresses and values refused without a change, `munin.conf` for each
  mode, the test mail in alice's INBOX, the old setting and `munin.conf`
  restored exactly). `API_NOT_CALLED` lists the endpoints it does not call,
  with the reason (reboot, package updates, SSL provisioning and install,
  web update, backup config writes, MFA enable and disable, DNS update,
  secondary nameserver, the type-A shortcut `/dns/custom/{qname}` (it
  would change real A records), the fail2ban writes). TESTING-fork.md
  describes it.
  Run it from the box itself or from a peer: through `--jump` its two
  failed logins come from the jump host.
* Tests: `tests/fork/api-routes.py` (stdlib only, no box): every route of
  `management/daemon.py` (method and path, path parameters normalised) is
  documented in `api/mailinabox.yml` and every documented operation has a
  route; `smoke.py` calls or excludes each documented operation exactly
  once; the content types it expects are the documented ones. The control
  panel page and Munin's pages behind the session cookie are listed as not
  part of the API. Exit code 1 on drift.
* Tests: `tests/fork/log-audit.sh --baseline BEFORE.json` compares with the
  `--json` report of an earlier run: a class that was in it is listed as
  KNOWN, with both counts, and does not count; only new classes are
  UNKNOWN (the prefixes `[in-place:PHASE]` and `[setup]` are ignored for
  the comparison, except for a class that was allowed with its prefix: a
  rule for that phase may have allowed it, so the same class outside the
  phase still counts). `--internet` adds
  `tests/fork/log-audit-allow-internet.txt`, the usual noise of a box on
  the Internet (ufw blocks, SYN floods, password guessing on SSH, SMTP
  submission, the control panel, Roundcube, Nextcloud and Z-Push, TLS and SSH errors of
  scanners and old clients, nginx 404s in the web roots, mail that Postfix
  rejects as spam, to unknown recipients or for relaying, greylisting,
  reverse DNS warnings, DNS and DNSSEC errors of other zones, not of the
  box's own), each rule with its reason; only when asked, the test
  scenarios do not use it. `--smoke` adds
  `tests/fork/log-audit-allow-smoke.txt`, the deliberate failures of the
  smoke test that look like a real attack (the failed logins of
  `api-auth`), for the test scenarios only.
* `tests/fork/log-audit-allow.txt`: rules for `(sd-pam)`'s "Varlink call
  io.systemd.Login.ReleaseSession failed: io.systemd.Login.NoSuchSession"
  at a reboot with an open SSH login; for Z-Push's first ActiveSync device
  of a box (`FileStateMachine->LinkUserDevice()` reads its users file
  before writing it); and, only during setup, for the ActiveSync long
  polls that a restart of PHP-FPM ends (nginx "recv() failed ... while
  reading response header from upstream" for `Cmd=Ping`/`Sync`), for
  Z-Push's CardDAV `ChangesSink` errors when a restart hits its check of
  the address book, and for the 404 of `/server-status?auto` and
  `/nginx_status` that `munin-node-configure` (setup/munin.sh) probes.

### Fixed

* Setup: an update no longer runs as root what another local user put into
  `/tmp`. Each run after the first wrote the settings of
  `/etc/mailinabox.conf` to `/tmp/mailinabox.prev.conf` and sourced that
  file as root; when a file of that name already existed (any local user,
  and www-data, can create one), the write failed and setup sourced the
  other user's file. It now reads the settings through a pipe, no file
  (B89; found twice, also as B96).
* Setup: the downloads of Nextcloud and its apps, Roundcube and its
  plugins, Z-Push and Bootstrap, the certificate request of the first
  self-signed certificate and the daily download of Postgrey's allowlist no
  longer use fixed or predictable names in `/tmp`, but a directory of
  root's own (`mktemp -d`, mode 0700). Another local user could create
  these names first and make setup fail; for Z-Push and the Roundcube
  plugins of git, a directory created in the right moment let them replace
  the unpacked code before setup moved it into place (B97).
* DNS: the management daemon copies the DNSSEC keys for signing a zone
  into a directory of its own (mode 0700), not to `/tmp/K<domain>...`
  under the key's name. Another local user could create these names first
  (the key tags are public); the copy then failed and the zone was not
  signed again, so its signatures would expire after 30 days (B98).
* Munin: setup no longer changes the owner of what a symbolic link in
  `/var/log/munin` points to. It ran `chown munin` as root on the CGI logs
  there, in a directory that belongs to munin; now `chown -h` (B86).
* Settings: the daemon and setup no longer write `settings.yaml` through a
  symbolic link. `$STORAGE_ROOT` belongs to the storage user; root now
  writes a new file under a random name and renames it (with at most the
  read bits of the old file's mode), and reads only a regular file there,
  with `O_NOFOLLOW` and without blocking on a FIFO (B87).
* Tools: for backups on the machine itself (local, or a `file://` target
  below a directory that another account may change),
  `tools/upgrade-in-place-to-2604.sh` no longer copies the encrypted system
  archive as root into `$STORAGE_ROOT/backup/encrypted-system/`: that path
  runs through `$STORAGE_ROOT`, which belongs to the user-data account, so a
  symlink there could have redirected root's mkdir and copy. The archive
  stays in `/root/upgrade-2604`, as the tool already said to copy it off the
  machine. A `file://` target whose path only root can change gets the copy
  as before (B90).
* Tools: for an rsync backup target, `tools/upgrade-in-place-to-2604.sh`
  (and the new `tools/update-check.sh backup`) no longer passes the host
  and path from `custom.yaml` unchecked to ssh and rsync as root: a host or
  path that starts with "-" (an option such as `-oProxyCommand=...`) or has
  other characters than letters, digits, `.`, `_`, `-` (and `@` between user
  and host) stops the tool, which names `--no-offsite` (`--no-upload`).
  `custom.yaml` lies below `$STORAGE_ROOT`, which the user-data account can
  change; current OpenSSH refused the resulting command line anyway (B102).
* Management: the daemon no longer runs out of file descriptors. Each API
  call left `users.sqlite` open (1 to about 90 times per call); after a few
  hundred calls the daemon reached its limit of 1024 open files and
  answered every request with 500 ("unable to open database file") until
  it was restarted. Connections now close with their cursor (B91).
* Nextcloud/Z-Push: ActiveSync syncs the address book of new users again.
  Nextcloud 34 puts an example contact into each new address book under the
  name `default`, without the `.vcf` that Z-Push's CardDAV backend adds when
  it fetches a contact; the Sync of the contacts folder then failed with a
  PHP error (HTTP 500), so no contact reached the phone. Setup turns the
  example contact off (`dav` `enableDefaultContact`). Users created before
  keep their example contact: delete it in Nextcloud's Contacts (it is
  marked "This is an example contact"), and the address book syncs (B99).
* OpenDKIM: the `KeyTable` and `SigningTable` are written in a fixed
  (sorted) order. The domains came from a Python set, whose order changes
  with every process, so with more than one mail domain each setup run (the
  management daemon, which writes them, starts anew in every run) and the
  first DNS update after a reboot rewrote both tables and restarted
  OpenDKIM once more, although nothing had changed. Mail sent in the moment
  of a restart goes out without a DKIM signature (Postfix has
  `milter_default_action=accept`) (B95).
* API: `GET /mail/users/quota` for an address that is not a user answers
  400 with the message instead of 200 with the error inside the JSON, and
  `POST /mail/users/quota` without a quota answers 400 instead of 500
  (B88).
* Tests: `admin-api-tmp-user-alias` removes the archived mailbox of its
  temporary user again (with `--ssh`), which every run left behind as an
  inactive account. `munin-alert-contact` passes when the admin panel
  turned the alerts off. `log-audit.sh --smoke` accepts the two deliberate
  failed logins of `api-auth`; the default allowlist does not, so that real
  failed logins to the control panel stay visible on a production box.
* Tools: `tools/update-check.sh mailcheck` reads the Received header of
  an answer that came in over TLS. Postfix puts the TLS session and
  "(No client certificate requested)" between the client and "by", and
  the check said FAILED for a round trip that had worked (B107).
* Tools: `tools/update-check.sh` finds the checkout of a box that has it in
  `/mailinabox` (an upstream box before the in-place upgrade): from the
  directory that `/usr/local/bin/mailinabox` changes into, as long as it is
  root's own. `before` recorded no version and no status checks there and
  said "0 errors", and `backup` stopped (B106).
* Tools: `tools/update-check.sh after` expects the new minute of the
  nightly job, which setup picks at random on every run; an update that
  changed nothing else ended with "RESULT: CHANGED" (B108).
* Tools: the expected changes of rc7 include those of rc4 and rc5 that the
  state record shows (`/etc/mailname` and `/etc/hosts`, B60; Dovecot and
  `mailinabox.service` enabled again, B67 and B69), for updates from rc1 to
  rc3 (B109).
* Tools: `tools/update-check.sh after` no longer judges an in-place upgrade
  or a migration from upstream Mail-in-a-Box by the lists of the fork's
  updates: it lists the changes and says "RESULT: NOT JUDGED" (exit code
  3) when the Ubuntu release changed or the box came from upstream (B110).
* Tools: `--ssh-fallback-test` of the in-place tool no longer leaves an
  empty `/root/upgrade-2604` behind (B111).
* Tools: the in-place tool puts back `/run/sshd`, which the fallback SSH
  server needs, within 2 s after the release upgrade stops ssh.service (it
  looked every 10 s, and new logins on port 1022 failed meanwhile). Its
  texts gave the outage times of the first rc7 run (B112); they now give
  those of all rc7 runs (see "Changed").
* Tools: `tools/migrate-to-2604.sh --check` proposes the start command with
  all options of the check (`--public-ip`, `--public-ipv6`,
  `--private-ip`, `--hostname`, ...); it named only `--from`, the SSH options
  and `--skip-network-checks`, and `--from` with nothing after it for
  `--from-backup` (B113).
* Tools: `tools/update-check.sh after` accepts both names under which
  munin-node holds its port (`munin-node`, or its path cut to 15
  characters, `/usr/sbin/munin`) (B114).
* Tools: the fallback SSH server of the in-place tool takes, with
  StrictModes (sshd's default), only the key files that sshd accepts on
  port 22: a file whose path up to the home directory another account can
  write (others, or a group with another member than the user; Ubuntu's
  sshd accepts a user private group), or that belongs to another user, is
  skipped with a warning, as sshd ignores it. It accepted such keys, so whoever could write an
  administrator's home could log in on port 1022 as that administrator.
  Its copy of the keys is `root:<the user's group>`, mode 0640 (B115).
* Tools: `tools/update-check.sh` no longer uses a checkout it rejected (it
  warned and, through curl, ran the status checks and `backup.py` from
  `/root/mailinabox` anyway), and a checkout counts only when every file in
  it is root's own and not writable by group or others (B116).
* Tools: `tools/update-check.sh backup`, the in-place tool's system archive
  and the pause of the backups in the in-place and the migration tool use
  `$STORAGE_ROOT/backup` only when it is a directory of root's own, not
  writable by group or others, and then only through one open descriptor:
  the user-data account, which owns `$STORAGE_ROOT`, could put a directory
  of its own there and have the system archive (with `/etc/shadow` and the
  SSH host keys) encrypted with its passphrase and sent to its host, or make
  root create a file through a symbolic link. Otherwise `backup` stops, the
  in-place preflight has a blocker, the archive stays unencrypted in
  `/root/upgrade-2604`, and pausing the backups is left to the operator
  (B117).
* Tools: the fallback SSH server also refuses to start when a file included
  from an included file (for example from `sshd_config.d/*.conf`) has a
  `Match` block; it looked one level deep only (B118).
* Tools: the fallback SSH server also starts for the release upgrade that
  begins by itself after the reboot into 24.04: with socket activation
  `/run/sshd` is missing until the first SSH login, so `sshd -T` failed and
  there was no fallback (B119). The tool creates the directory first. A
  `--ssh-fallback-test` that does not start no longer leaves an empty
  `/root/upgrade-2604` either (B111).

### Changed

* Setup: an interactive update of an existing box (`/etc/mailinabox.conf`
  exists) no longer shows the welcome dialog of a new installation ("You
  should only install this on a brand new Ubuntu installation"). The
  questions that follow (hostname, and the IP addresses where they differ
  from what the box finds) come as before; non-interactive runs are
  unchanged.
* nginx: setup reloads nginx (after `nginx -t`) instead of restarting it.
  A restart gave the running requests only the unit's stop timeout (5 s on
  Ubuntu) and cut long-polling ActiveSync, CalDAV and CardDAV clients; a
  reload lets the old workers finish them. Setup still starts nginx when it
  does not run and restarts it when the running binary is not the
  installed one (a package upgrade that left the old process running). The
  management daemon's web update already reloaded. Setup's restarts of
  PHP-FPM (four per run) still end an ActiveSync long poll, which the
  client then starts again.
* Journal: checked, no change. Since rc6 Dovecot logs through syslog, so
  its lines are in the journal too. The journal stays bounded: setup keeps
  it for 10 days (`MaxRetentionSec=10day`, as upstream), and journald's
  defaults on 26.04 (systemd 259) cap it at 10% of the file system, at most
  4 GiB, and keep 15% free. Its rate limit drops lines only from the
  journal: journald forwards syslog lines to rsyslog before it applies the
  limit, so `/var/log/mail.log`, which fail2ban reads, keeps all of them
  (test box: 100000 lines in a few seconds from one unit, 37500 in the
  journal, all 100000 in the syslog file). A comment in setup/system.sh
  says so.
* Tools: the messages before a release upgrade (and in the motd) name the
  fallback SSH server and how to reach it. The help of
  `tools/upgrade-in-place-to-2604.sh` describes it. The plan of `--check`
  says that new SSH logins on port 22 fail and sudo is missing for a while
  during the release upgrades; the tool gives the times of all rc7 runs
  (port 22: 19 to 42 minutes from 22.04, 6 to 19 minutes from 24.04; sudo:
  12 to 37 minutes), which were 20 to 40, 5 to 20 and 12 to 31.
* Tests: `tests/fork/log-audit.sh --since` also takes the short forms `-90s`,
  `-30m`, `-24h`, `-2d` and `-1w`; `date -d` fails on them ("-24h" reads the
  "h" as a time zone).
* Docs: README-fork.md, "Updating the fork", gives the commands of
  `tools/update-check.sh` for a box on rc6 or earlier (through curl, with
  the Docker options) and what the results and exit codes of `after` mean;
  "In-place upgrade to 26.04" has the outage times of the rc7 tests, what
  the fallback SSH server did in them, how to try it before the upgrade,
  and `update-check.sh` around an in-place upgrade. TESTING-fork.md has the
  results of the rc7 certification runs.

### Upgrade note

* Boxes on rc1 to rc6 are updated with the two commands of "Updating the
  fork" in README-fork.md:
  `sudo git -C /root/mailinabox remote set-url origin https://github.com/LM1337/Mail-in-a-box-26`
  and
  `sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/setup/bootstrap.sh)"`.
  The first one is needed for rc1 to rc3 and changes nothing on rc4 to rc6.
  Setup no longer shows the welcome dialog of a new installation; the other
  dialog boxes (host name, public IP address) are shown as before, and
  Enter keeps the current values.
* Munin's alerts: nothing to do. Without a setting `munin.conf` stays as in
  rc6 (alerts of warnings and critical values to administrator@). To change
  the address or turn them off: System > Munin Monitoring. Changes to
  `/etc/munin/munin.conf` by hand are overwritten (as before by setup, now
  also when the setting is saved); own Munin settings belong into
  `/etc/munin/munin-conf.d/`.
* The first setup run of this release writes the OpenDKIM tables once more,
  in sorted order, and restarts OpenDKIM (B95); later runs leave them alone.
* Users created before this release keep Nextcloud's example contact, and
  their ActiveSync contact sync fails until it is deleted in Nextcloud's
  Contacts (B99). Setup deletes no user data.
* The fallback SSH server of the in-place tool listens on port 1022 during
  each release upgrade. If a firewall of the provider must let it through,
  open it there before the upgrade and try it with
  `curl -s https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/tools/upgrade-in-place-to-2604.sh | sudo bash -s -- --ssh-fallback-test`
  (README-fork.md, "In-place upgrade to 26.04").
  `UPGRADE_SSH_FALLBACK_PORT=off` turns it off.
* Before and after the update, `tools/update-check.sh before`, `backup`,
  `after` and `mailcheck` (see "Updating the fork" in README-fork.md) record
  and compare the state of the box. A box on rc6 or earlier has no copy of
  the tool yet: run `before` and `backup` through
  `curl ... | sudo bash -s -- STEP` (it fetches its helpers from the branch
  main), then update, then `after` and `mailcheck` from
  `/root/mailinabox/tools/`.

### Done from the plan

From the rc6 list ("Planned for rc7" below) and the plan of rc7: the
Munin alert setting, the fallback SSH server and the live note, the order
of the OpenDKIM tables, the `(sd-pam)` rule, the API test, the log audit
baseline and Internet allowlist, the update tools (state, backup,
comparison, mail check) as code, the welcome dialog, the nginx reload with
its allowlist rules, the journal check. The test matrix T1 to T5b ran on
rc7 three times (TESTING-fork.md, "rc7"): on the release commit, where it
found B106 to B113; after those fixes, where it found B114; and, after the
review of those fixes (B115 to B118) and B119, T2 to T5b Part A again on
`014ff8a`. The last smoke run of every scenario had 0 FAIL (two earlier runs
of the second round failed for lab reasons, see TESTING-fork.md), and
every log audit ended with 0 unknown classes with the final allowlists and
the lab's own list: T3 and T4 with the single-binary sshd of 22.04 and
24.04 for the fallback, T5b with `tools/update-check.sh` around the update
(Docker options, rsync upload, lab probe). T6 is left for the final
release.

## v78-r2604.0-rc6 (2026-10-25)

Fixes from the in-place test from 22.04 of rc5, from the test runs of rc6
and from the log audit and smoke tests of its certification runs. Security:
after the weekly rotation of `mail.log` the fail2ban jails for IMAP, POP3
and ManageSieve banned nobody until Dovecot restarted; Dovecot now logs
through syslog, and rsyslog follows the rotation. Munin's alerts reach the
administrator for the first time. The tools show their run in the
terminal, also through `curl | sudo bash`, and say that SSH logins, sudo
and `tmux attach` fail for a while in the release upgrades. Setup waits
for the apt lock of Ubuntu's daily jobs, pauses cron while it runs,
restarts nsd when its configuration changed, and no longer grows
`10-ssl.conf`; logrotate works again on boxes upgraded in place, Postfix
no longer delays its greeting after an unlucky restart, and spampd leaves
no stale PID file. Roundcube and Nextcloud show the fork's favicon. New
test tool: `tests/fork/log-audit.sh`.

### New

* Roundcube and Nextcloud show the fork's favicon (`branding/favicon.ico`).
  Roundcube: setup sets `skin_logo` (`elastic:[favicon]`) and puts the file
  into Roundcube's directory; a replaced `favicon.ico` of the Elastic skin
  and other skins are left alone. Nextcloud: setup sets only the favicon of
  the theming app (name, logo, colours and background stay); a favicon that
  an administrator uploaded under Administration > Theming is kept, and
  setup only replaces the one it set itself. `FAVICON=off` in
  `/etc/mailinabox.conf` turns both off and removes the fork's favicon from
  Nextcloud again. For `occ`, which runs as www-data, setup copies the file
  into a new directory of root's own (mode 0711), not under a file name in
  `/tmp`. See README-fork.md, "Favicons".
* Tests: `tests/fork/log-audit.sh` (as root on the box, read-only) collects
  the warnings and errors since a point in time (`--since`, default the last
  boot) from the journal, `systemctl --failed` and the logs of the services
  (mail.log, nginx, PHP-FPM, fail2ban, Nextcloud, Roundcube, Z-Push, Munin,
  apt, cloud-init, kernel, the tools' own logs), reduces them to message
  classes, counts them and compares them with the allowlist
  `tests/fork/log-audit-allow.txt` (one regex and its reason per line). Exit
  code 1 if a class is not on the list; `--json` writes the report.
  During an in-place upgrade, what the box logs between stopping mail and
  the start of setup gets the phase of the tool as a prefix
  (`[in-place:release_2604]`), so that the allowlist accepts the noise of
  the old releases and the release upgrades only there.
  `tests/fork/log-audit-allow-old-box.txt` adds what the old box logs when
  the migration tool stops it. The allowlist holds the classes of the rc6
  certification runs that were checked as harmless, each with its reason;
  the test lab's own list added the classes of software that the copied
  box runs besides Mail-in-a-Box, and the `(sd-pam)` class of one run (see
  "Planned for rc7"). The defects it found are B80 to B84. Dovecot's
  syslog lines (`dovecot: imap(...): ...`) get the class of Dovecot's
  process, as its own lines in older files do, and its lines below warning
  in the journal (failed logins of clients) are not findings. A line that
  rsyslog shortens to "message repeated N times: [ ... ]" gets the class of
  the repeated line.
  TESTING-fork.md describes it.

### Fixed

* Tools: phase verify of `tools/upgrade-in-place-to-2604.sh` no longer
  warns that `ssh.service` was enabled before the upgrade and is disabled
  now, and `etc-report.txt` no longer advises to enable it. Since 24.04
  `ssh.socket` starts it. Units that are started another way (an enabled
  socket, path or timer, a new name, a running unit that pulls them in)
  are left out of the check (B70).
* Tools: the terminal that the tools attach to their tmux session shows
  the run. It stayed blank in rc4 and rc5 (the terminal was opened only for
  reading), and through `curl ... | sudo bash` the tools did not attach it
  at all ("Could not attach this terminal"). Now they attach it in all
  these forms, with sudo on 22.04 and 24.04 and with sudo-rs on 26.04; Ctrl-b
  d detaches. They tell sudo-rs from sudo by the path of the binary that
  runs the session; a test version ran that binary with `--version` as root.
  `--check` no longer advises to start the command inside tmux, except for a
  `TAG` of rc1 to rc3 (B71).
* Tools: after the last reboot of `tools/upgrade-in-place-to-2604.sh`
  the tmux window closes by itself 60 seconds after a successful run,
  instead of waiting for Enter forever; after a failure it stays open (B72).
* Tools: `tools/upgrade-in-place-to-2604.sh` says that from a few minutes
  into the release upgrade to 26.04 until the reboot a new `tmux attach`
  cannot reach the run ("open terminal failed: not a terminal": tmux 3.6
  replaces tmux 3.4), and to follow the log with `sudo tail -f
  /root/upgrade-2604/upgrade.log` instead. Before, it advised to wait and
  attach again. The log hints say `sudo tail -f` (B73).
* Dovecot: setup no longer adds another commented copy of each SSL setting
  to `/etc/dovecot/conf.d/10-ssl.conf` on every run. The settings were
  passed to `editconf.py` with spaces around "=" (B74).
* System: on boxes upgraded in place to 26.04, `logrotate.service` no
  longer fails every day. The release upgrade leaves cloud-init's old
  `/etc/logrotate.d/cloud-init` next to the new `cloud-init-base`. Setup
  removes unchanged logrotate files that their package no longer ships
  (B75).
* Tools: the Spamhaus checks of `tools/migrate-to-2604.sh` no longer
  append the resolver's search domain to the names they look up. With a
  wildcard record in that domain they reported "unexpected answer" with
  the wildcard's address (B76).
* Tools: `tools/migrate-to-2604.sh --check --skip-network-checks` lists
  the skipped network checks (port 25, Spamhaus) as ignored, not as
  blockers, and no longer exits with code 1 because of them. The run with
  the same options never stopped on them (B77).
* Postfix: the first connections to port 25 after a start of Postfix no
  longer wait 100 seconds for the greeting. A restart at the wrong moment
  left Berkeley DB's temporary file of tlsmgr's TLS session cache
  (`/var/lib/postfix/__db.smtp_scache.db`), and every later start stumbled
  over it. A systemd drop-in of setup removes such files before each start
  (B78).
* Setup: setup no longer stops with "Could not get lock" when apt-daily
  or unattended-upgrades runs at the same time (for example some minutes
  after a boot). It waits up to 10 minutes for the dpkg and apt locks
  before each apt-get call (B79).
* Munin: alerts reach the administrator. munin.conf defines the contact
  before the host tree (after the `[host]` line munin-limits did not find
  it and logged "Missing configuration options for contact admin" every 5
  minutes), and its command `/usr/local/lib/mailinabox/munin-notify`
  (from `management/munin_notify.sh`) sends the alert with
  `/usr/sbin/sendmail` to administrator@PRIMARY_HOSTNAME (there is no
  `mail` command). Only a change of state (ok, warning, critical, unknown)
  is mailed, one mail per run: `always_send`, which would have repeated a
  warning every 5 minutes, is gone. Munin no longer graphs the veth
  interfaces of containers (Docker), whose names change at each start of
  the container and whose old plugins would report "unknown" for ever
  (B80).
* Spam: systemd removes spampd's PID file after each stop, as root
  (drop-in `/etc/systemd/system/spampd.service.d/mailinabox-stale-pid.conf`
  with `ExecStopPost`); spampd itself cannot (it logs "Couldn't unlink
  /run/spampd.pid"), and the stale file stayed behind. The PID file stays
  in the root-owned `/run`. A first version of this fix, replaced before
  the release, moved it into a directory owned by spampd, which would have
  let a compromised spampd redirect root's write of the file with a
  symlink; setup removes that version's drop-in and `/run/spampd` from
  boxes that ran it (B81).
* Setup: cron is stopped while setup runs and started again at its end,
  also when setup fails. Cron jobs no longer run against half-configured
  services, and their mail to root no longer bounces on a new box before
  setup has written the root@ alias. A cron that the tools stopped stays
  stopped (B82).
* DNS: setup restarts nsd when it changed nsd.conf, so that a new address
  of the box and the logging to syslog take effect without a reboot (B83).
* Tools: the tmux scopes of both tools, and the scope in which the in-place
  tool continues after a reboot, have a description; on 22.04 systemd
  complained about the old one (the multi-line command) at every
  daemon-reload. The resume script quotes the scope command with
  `printf %q`, so the description with its spaces reaches systemd-run as
  one argument (B84).
* Dovecot: after a rotation of `/var/log/mail.log` Dovecot's lines go to
  the new file. Dovecot wrote the file itself (`log_path`) and went on
  writing into `mail.log.1` until its next restart (usually the nightly
  backup); in that time the fail2ban jails `dovecot` and
  `miab-slow-dovecot` banned nobody: password guessing on IMAP, POP3 and
  ManageSieve went unpunished. Now Dovecot logs through syslog
  (`log_path=syslog`, its default; facility mail), and rsyslog writes
  `mail.log` and reopens it after each rotation, as for Postfix. No Dovecot
  process opens a file in `/var/log` any more: before, Dovecot's log
  process, which runs as root, opened `mail.log` by name and followed a
  symlink there, in a directory that the group syslog may write.
  `management/mail_log.py` reads the new form of the lines; the fail2ban
  filters and the failed-login report already did. Two versions of this
  fix were replaced before the release: the first created and chowned the
  new `mail.log` as root in `/var/log`, which a symlink could have
  redirected; the second had a path unit run `doveadm log reopen` after a
  check of the file, and Dovecot then opened the path again as root, so
  the check could be raced, and the group syslog could start that unit
  at will. Setup removes that unit (`mailinabox-dovecot-log-reopen.path`
  and `.service`, `/usr/local/lib/mailinabox/dovecot-log-reopen`) from
  boxes that ran it. Upstream bug since 2016 (B85).

### Changed

* Tools: before each release upgrade `tools/upgrade-in-place-to-2604.sh`
  says that new SSH logins fail for a while and, from 24.04 to 26.04, that
  `sudo` is missing for a while because sudo-rs replaces it: attach before
  and keep the connection open; if a login fails, wait, do not reboot. It
  also says so before a reboot after which a release upgrade starts by
  itself, and in the motd while one is to come. It gives rounded ranges
  from the test runs: new SSH logins fail for 20 to 40 minutes from 22.04
  to 24.04 and 10 to 15 minutes from 24.04 to 26.04, `sudo` is missing for
  12 to 26 minutes, the longer times on a busy disk; a release upgrade
  takes 20 to 90 minutes. The measured SSH times were 19 to 36 and 7 to 14
  minutes; README-fork.md ("Logging in during the release upgrades") gives
  them, README.md describes it.
* Tests: `tests/fork/smoke.py` marks every mail it sends with the header
  `X-Miab-Test: 1`. The manifest comparison (`mig-folders-<user>`,
  `mig-pop3-uidl-<user>`) ignores marked mails and the automatic replies
  and bounces to them, and says how many it ignored; any other missing or
  new mail, and a seeded mail that is there twice, is a FAIL. Before, every
  mail sent to the box since the manifest was a FAIL (the 6 known FAILs of
  the rc5 runs). `smoke.py --send-test-mail FROM TO` sends a marked mail
  for the testers' own checks. `seed-legacy.sh` leaves the same mails out of
  the manifest. Manifests of earlier `seed-legacy.sh` runs still work.
  TESTING-fork.md describes it.
* Tests: `tests/fork/smoke.py --fail2ban` rotates `mail.log` once before
  the attacks (`fail2ban-log-rotation`) and checks that rsyslog writes the
  new file and that no Dovecot process holds a file in `/var/log`
  (`log_path=syslog`; with Dovecot's own `log_path`, up to rc5, it must
  hold the new `mail.log`), so a jail that a rotation made blind fails
  (B85). `fail2ban-filters` has a Dovecot line in the syslog form.
* Tests: `tests/fork/smoke.py` checks Munin's alert contact
  (`munin-alert-contact`), and `services-enabled` no longer reports a SysV
  service of 22.04 (postgrey) as not enabled. `prepare-testenv.sh` writes
  its SpamAssassin file with mode 644 also under a umask of 077 (the IMAP
  processes could not read it).

### Upgrade note

* Boxes on rc1 to rc5 are updated with the two commands of "Updating the
  fork" in README-fork.md:
  `sudo git -C /root/mailinabox remote set-url origin https://github.com/LM1337/Mail-in-a-box-26`
  and
  `sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/setup/bootstrap.sh)"`.
  The first one is needed for rc1 to rc3 and changes nothing on rc4 and rc5.
* Munin mails administrator@PRIMARY_HOSTNAME (from and to that address) on
  each change of state of a watched value: one mail when a value reaches
  warning or critical, one when it is back to ok. A value that is in
  warning or critical already is not mailed until its state changes;
  `/var/lib/munin/limits` lists the states. Make sure that address reaches
  someone (it is an alias of the first administrator by default). A
  setting to change the address or turn the alerts off is planned for rc7.
* Dovecot logs through syslog (B85); setup sets `log_path=syslog` and
  restarts Dovecot. Nothing to do by hand. Its lines in `mail.log` now have
  rsyslog's form, as Postfix's: `2026-10-25T13:00:00.123456+00:00 box
  dovecot: imap-login: Logged in: user=<...>, ...` (time stamp, host,
  `dovecot:`, no `Info:`); warnings and errors keep `Warning:` and `Error:`.
  They are also in the journal (`journalctl -u dovecot`) and in
  `/var/log/syslog`. Scripts or filters of your own that parse the old form
  (`Oct 25 13:00:00 imap-login: Info: ...`) need the new one. On a box
  whose `mail.log` was rotated since Dovecot's last restart, the Dovecot
  lines of that time are in `mail.log.1`. Check after the update:
  `doveconf -h log_path` says `syslog`.
* Setup adds the systemd drop-in
  `/etc/systemd/system/spampd.service.d/mailinabox-stale-pid.conf` (B81)
  and sets `pid /run/spampd.pid` in `/etc/spampd.cfg`. The in-place tool
  does not count this drop-in (nor Postfix's `mailinabox-stale-db.conf`)
  as a local extension.
* Cron is paused while setup runs (B82): cron jobs that would fall into
  the minutes of an update run are skipped, not run later. The nightly job
  between 01:00 and 01:59 is not affected unless you update at that time.
* After the update Roundcube and Nextcloud show the fork's favicon. A
  favicon that an administrator uploaded in Nextcloud and a replaced
  favicon of Roundcube's Elastic skin are kept. To keep the old favicons,
  put `FAVICON=off` into `/etc/mailinabox.conf` before the update.
* The first setup run of this release writes the SSL settings of
  `/etc/dovecot/conf.d/10-ssl.conf` once more (B74). The commented copies
  that earlier runs added stay; they are only comments.
* On boxes upgraded in place to 26.04 with rc1 to rc5, setup removes
  cloud-init's old `/etc/logrotate.d/cloud-init` if it is unchanged, and
  logrotate works again (B75). A changed file is kept; then remove the
  duplicate entry by hand.
* For an in-place upgrade, read "Logging in during the release upgrades" in
  README-fork.md ("In-place upgrade to 26.04") first: attach to the run
  before each release upgrade and keep the connection; if a new login
  fails, wait, do not reboot.

### Planned for rc7

* An admin panel setting for Munin's alerts: to administrator@PRIMARY_HOSTNAME
  (the default), to another address, or off; warning and critical or only
  critical; a button that sends a test mail.
* A shorter SSH outage during the release upgrades, or at least a live
  note: for example a fallback sshd on another port while the SSH server is
  replaced (as do-release-upgrade offers when it runs interactively), and a
  message in the run when SSH logins work again.
* A deterministic order of the OpenDKIM tables (`KeyTable`,
  `SigningTable`), so that a setup run without changes leaves them alone.
* A rule in `tests/fork/log-audit-allow.txt` for `(sd-pam)`'s
  "pam_systemd(systemd-user:session): Varlink call
  io.systemd.Login.ReleaseSession failed: io.systemd.Login.NoSuchSession"
  at a reboot, seen in one T5b run of rc6 (the test lab's own list
  accepted it there).
* The full test matrix T1 to T5b again on the release head, and T6 (on the
  Internet: Let's Encrypt, delivery to other providers) before a final
  release.

## v78-r2604.0-rc5 (2026-10-24)

Fixes from the update of a copy of a production box from rc3 to rc4: Dovecot
stays enabled after the in-place upgrade (B67), no more phantom folders from
vacation replies (B66), cloud-init keeps the box's name in /etc/hosts (B68),
and the mailinabox and munin units are enabled by name (B69).

### Fixed

* Dovecot: vacation replies and Sieve redirects no longer create the
  folders `dovecot`, `dovecot.lda-dupes` and `dovecot.lda-dupes.locks`.
  Dovecot 2.4 put the lock files of its duplicate database into a
  directory in the Maildir, which Maildir++ showed as a folder; setup sets
  `mail_volatile_path` to `/run/dovecot-volatile/<domain>/<user>` (a tmpfs
  directory, `/etc/tmpfiles.d/mailinabox-dovecot.conf`) and
  `maildir_stat_dirs = yes`. Dovecot 2.3.21 on Ubuntu 24.04 did the same,
  so boxes that come from 24.04 can bring these folders along. On existing
  boxes setup deletes them (through doveadm, with their subscriptions and
  full-text index, after the user database is set up) unless one holds
  messages; a real folder named `dovecot` keeps its subscription, and a
  user that doveadm cannot handle is retried on the next setup run (B66).
* Tools: `tools/upgrade-in-place-to-2604.sh` left Dovecot disabled: it
  installs Dovecot 2.4 while the unit is masked, which the package cannot
  enable, and after the next reboot there was no IMAP, POP3 or delivery to
  the mailboxes. The tool now records which units are enabled before it
  masks them and enables them again when it unmasks them. Phase verify of
  both tools shows whether each service is enabled, enables a disabled one
  and fails on any other state; the in-place tool also reports units that
  were enabled before the upgrade and are disabled now (warning and
  `etc-report.txt`). Setup enables a disabled service before it restarts it
  (and nsd), so the next setup run heals a box upgraded with rc3 (B67).
* System: on machines where cloud-init writes `/etc/hosts` on every boot
  (`manage_etc_hosts`, e.g. hypervisors and the images of hosting providers),
  the 127.0.1.1 line with another machine's name that setup comments out
  came back after each reboot. Setup now also puts the box's name on the
  127.0.1.1 line of cloud-init's template
  (`/etc/cloud/templates/hosts.debian.tmpl`) and the same line into
  `/etc/hosts`. When an update of cloud-init changes the template, dpkg
  asks about it: keep the local version (B68).
* Setup: `systemctl is-enabled mailinabox` and `munin` no longer fail
  with "Too many levels of symbolic links". Setup enabled the units by
  their path under `/lib`, which left a link in `/etc/systemd/system` to the
  same file; it now removes such a link and enables the units by name
  (B69).

### Changed

* Tests: smoke checks `services-enabled` (the services of Mail-in-a-Box are
  enabled, over `--ssh`) and `sieve-vacation-no-phantom-folders` (after the
  vacation reply, IMAP lists no folder of Dovecot's duplicate database).
* Docs: README-fork.md has a new section "Setup output" with the lines of
  setup's output that look like errors but are harmless on 26.04
  (pollinate "Permission denied", Nextcloud's "No upgrade required", the
  SysV note of systemctl). "Updating the fork" says what to do right after
  an update (allowlist, the nightly job's new minute, enabled services) and
  how to remove the old release tags of rc1 to rc3 checkouts.

### Upgrade note

* Boxes upgraded in place with rc3 have Dovecot disabled (B67): it runs,
  but does not start after a reboot. Check with `systemctl is-enabled
  dovecot`; until this release is installed, `sudo systemctl enable
  dovecot` fixes it. Setup of this release enables it by itself.
* Adaptive banning and the slow mail jails are on as soon as setup of rc4
  or later has finished; there is nothing to turn on. Put your own
  networks on the allowlist right after the update (System > Intrusion
  Protection, or `sudo /root/mailinabox/management/fail2ban_admin.py
  --allow 192.0.2.0/24`), see the upgrade note of rc4.
* Every setup run picks a new random minute between 01:00 and 01:59 for
  the nightly backup and status checks (`/etc/cron.d/mailinabox-nightly`),
  as upstream does. Look it up before the next update or in-place upgrade:
  the in-place tool waits for a running backup before it stops mail, at
  most 2 hours.
* Checkouts of rc1 to rc3 keep the release tags of the fork's previous
  home, which have other commit ids than on GitHub. They do no harm;
  `sudo git -C /root/mailinabox tag -d v78-r2604.0-rc1 v78-r2604.0-rc2
  v78-r2604.0-rc3` removes them. Not `git fetch --tags`: the checkout is
  shallow, and that downloads the history of all upstream tags.

## v78-r2604.0-rc4 (2026-10-24)

Project home on GitHub, adaptive fail2ban with the control panel page System >
Intrusion Protection, Nextcloud sharing within the mail domain, tmux for both
tools, and the fixes from the in-place upgrade of a production box with rc3
(B57-B60), B61 to B65.

### New

* Logo and favicon for the fork: the source files are in `branding/` (CC0,
  with `branding/README.md` on colours and use). The control panel has a
  favicon and shows the icon next to the box name; setup copies the files to
  `/usr/local/lib/mailinabox/vendor/assets/branding/` (served as
  `/admin/assets/branding/`). On the web domains of the box, `/favicon.ico`
  falls back to the fork's icon when the web root has no `favicon.ico` of its
  own. The default page for new boxes (`conf/www_default.html`) shows the
  icon; an existing `index.html` stays as it is. The README header shows the
  wordmark.
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
  The ban checks of that group also accept a ban by the slow jails, which
  count the failures of all Dovecot (SMTP) protocols together and can ban
  the source before the fast jail does.
* Docs: new public README.md (unofficial-fork notice, status, supported paths,
  credits, license); upstream's README is kept as README-upstream.md. New
  `.github/SECURITY.md` (GitHub private vulnerability reporting); fork notes
  in security.md, CODE_OF_CONDUCT.md and CONTRIBUTING.md.

### Changed

* Project home: the fork is now published at
  https://github.com/LM1337/Mail-in-a-box-26. `setup/bootstrap.sh`,
  `tools/migrate-to-2604.sh` and `tools/upgrade-in-place-to-2604.sh` clone
  from there by default, and the
  curl commands in the documentation use
  `https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/...`.
* Status checks: the version check reads the latest release tag from the
  fork's `setup/bootstrap.sh` on GitHub, and the upgrade hint names this
  fork and its URL. A bootstrap.sh without a `TAG=` line now gives "could not
  be determined" instead of an error.
* Setup: `setup/bootstrap.sh` compares the checkout's origin with `SOURCE`
  case-insensitively. A checkout of this fork cloned from its previous
  location (rc1 to rc3) stops with "is a checkout of ..., not of ..." and
  only the command that points it to GitHub
  (`git -C ~/mailinabox remote set-url origin https://github.com/LM1337/Mail-in-a-box-26`);
  the hint to the in-place tool is only given for a checkout of upstream
  Mail-in-a-Box. See "Updating the fork" in README-fork.md. `TAG=` with a
  branch (`TAG=main`, for testing) updates an existing checkout to that
  branch instead of failing with "Update failed" or keeping an old local
  branch, and a fresh install with a branch no longer prints "couldn't find
  remote ref".
* Tools: `tools/upgrade-in-place-to-2604.sh` on a 26.04 box that already
  runs the fork brings `/root/mailinabox` to the release tag (without `TAG=`
  the tool's own one) before setup runs again, instead of running setup of
  the old release; the checkout the tool runs from stays as it is unless
  `TAG=` is set. A clone from an earlier run that `curl | bash` reuses
  (`/root/upgrade-2604/fork`, and `/root/mailinabox` of the migration) is
  fetched from `SOURCE` and checked out at the tag; if that fails, it is
  downloaded again (in place) or the tool stops, instead of running the old
  copy. A checkout of the fork from another repository stops with the
  `git remote set-url` command, as in bootstrap.sh. `TAG=` also takes a
  branch such as `main` for an existing checkout.
* Tools: `tools/migrate-to-2604.sh` keeps the other settings of an existing
  `/etc/mailinabox.conf` on the new machine (e.g. `FTS=off` or
  `NEXTCLOUD_SHARE_SCOPE=all`, set there after a rehearsal) when it writes
  the file again; before, the real run dropped them. Both tools pass `FTS`
  and `NEXTCLOUD_SHARE_SCOPE` from the environment into their tmux session.
* Tools: `tools/upgrade-in-place-to-2604.sh` is executable in git, as its
  own hints assume. The help texts, the reboot hints and the migration's
  quick start say `sudo tmux attach -t ...`: the session belongs to root.
* Branding: the installed box points to the fork instead of only to
  upstream: the Roundcube support link, the admin panel footer, the default web page (new
  boxes only) and the SMTP banner.
* Tests: `tests/fork` no longer contains addresses or host names of a
  particular test network. `prepare-testenv.sh` needs `JUMP_HOST`, `PEERS`,
  `BLOCK_V4` and `BLOCK_V6` (environment or `TESTENV_FILE`); `smoke.py` reads
  its env file from `MIAB_TEST_ENV` (default `tests/fork/credentials.env`,
  ignored by git) and the seed domains from `SEED2_DOMAIN`/`SEED3_DOMAIN`
  (default `seed2.example.net`/`seed3.example.net`), like `seed-legacy.sh`.
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
  (also through `curl | bash`; not through `curl ... | sudo bash` where sudo
  runs the command in a terminal of its own, as sudo-rs on 26.04 and sudo
  1.9.15 on 24.04 do: the tmux client showed nothing there, so the tools say
  so and print `sudo tmux attach -t ...`), keep the window open until Enter (also
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
* fail2ban: the filters `miab-management-daemon` (jails `miab-management`,
  `miab-slow-management`) and `miab-roundcube` (`miab-roundcube`,
  `miab-slow-roundcube`) are anchored. A client could put the control
  panel's failed-login text with a third party's address into an SMTP AUTH
  user name, which Postfix logs to /var/log/syslog as well, and get that
  address banned from the web ports (and through recidive from all); the
  Roundcube filter took the first ` from <ip>.` of the line, which could be
  part of the user name (B62).
* Management: the API call `system/latest-upstream-version` answers HTTP
  503 "The latest version could not be determined." instead of HTTP 500 with
  a traceback in the daemon log when the release cannot be looked up (B63).
* Management: a failed write to the user database (adding a user or alias
  that exists, changing the password, quota or privileges of an address
  that is no user, removing one that does not exist) no longer keeps
  `users.sqlite` locked. With Python 3.14 the connection stayed open with
  its transaction until the garbage collector ran, often for minutes, and
  every other change in the control panel failed with "database is locked"
  (HTTP 500) until then (B64).
* Setup: the documented command is now
  `sudo bash -c "$(curl -fsSL .../setup/bootstrap.sh)"`. With upstream's
  `curl ... | sudo bash`, sudo-rs (the sudo of Ubuntu 26.04) stopped setup's
  first dialog box, and an interactive install or update hung without
  showing anything. bootstrap.sh run that way now stops before changing
  anything and prints the working command; with `NONINTERACTIVE=1`, as root
  or with sudo.ws the pipe still works (B65). The hints with
  `git remote set-url` start with `sudo`.

### Upgrade note

* Boxes on rc1 to rc3 were cloned from the fork's previous home. Point the
  checkout to GitHub once, then run the bootstrap command as usual:
  `sudo git -C /root/mailinabox remote set-url origin https://github.com/LM1337/Mail-in-a-box-26`
  (see "Updating the fork" in README-fork.md). Their status checks look for
  new releases at the previous home and may keep reporting the box as up to
  date until it runs rc4.
* The slow mail jails are on after the upgrade, with an empty allowlist. On a
  box whose users sit behind one office address, put that network on the
  allowlist right after the upgrade (System > Intrusion Protection, or
  `sudo /root/mailinabox/management/fail2ban_admin.py --allow 192.0.2.0/24`).
  Before the upgrade, neither exists yet; `fail2ban: {allowlist:
  [192.0.2.0/24]}` in `$STORAGE_ROOT/settings.yaml` (usually
  `/home/user-data/settings.yaml`) has the same effect from the first setup
  run on. Without it, a single phone with an old password can get the
  office banned from the mail ports, for longer each time.
* Nextcloud sharing is limited to the own mail domain from this release on
  (`NEXTCLOUD_SHARE_SCOPE=domain` is the default). On a box with several
  mail domains, users no longer find the accounts of the other domains in
  the share dialog, the contacts menu, the system address book and the team
  search; admins become members of every domain group. Existing shares
  between domains stay. To keep the old behaviour, put
  `NEXTCLOUD_SHARE_SCOPE=all` into `/etc/mailinabox.conf` before the update
  or in-place upgrade; for a migration, give it to the tool
  (`NEXTCLOUD_SHARE_SCOPE=all /root/mailinabox/tools/migrate-to-2604.sh ...`).
  Set later, it takes effect on the next setup run (`sudo mailinabox`).

## v78-r2604.0-rc3 (2026-10-23)

In-place upgrade and full-text search. Tested in place on a copy of a
production box (Ubuntu 24.04 release-upgraded from 22.04, Mail-in-a-Box v74,
PHP 8.0 from ppa:ondrej, Dovecot 2.3 with fts_xapian and a custom Dovecot plugin):
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
- Limitation: the PR never touched `setup/bootstrap.sh`. It still only knows 22.04 and 18.04, so the curl one-line installer aborts on 26.04. Our fork added a 26.04 branch (a85fa0d).
- Limitation: the apt install of the email validator only runs when `dialog`, `python3` or `pip3` is missing. On a host that already has all three, the address prompt loops on an ImportError. Fixed in our fork (9480754).

### System / apt / PHP source

- `PHP_VER` changes from 8.0 to 8.5, and a new `PHP_LEGACY_VER=8.2` is added for the Nextcloud upgrade chain.
- The `ppa:ondrej/php` PPA is replaced by the Debian-style repository at packages.sury.org. Setup downloads the `debsuryorg-archive-keyring.deb` with curl and installs it, then writes `/etc/apt/sources.list.d/php.list`. This repo is needed because Ubuntu 26.04 has no `php8.5-imap` and no PHP 8.2.
- The `ntp` package is no longer installed (26.04 handles time sync itself). `curl` is installed earlier as a prerequisite for the repo.
- `pollinate` now runs as the `pollinate` user (`sudo -u pollinate`) instead of as root.
- The inotify limit (`fs.inotify.max_user_instances=1024`) now goes into its own file, `/etc/sysctl.d/60-mailinabox.conf`, applied with `sysctl --system`. 26.04 no longer ships `/etc/sysctl.conf`, and `/usr/lib/sysctl.d/50-default.conf` is missing on some installs (contributed by Gwerlas in 0ddb859).
- Limitation: the sury repo is not pinned and its key is trusted globally. Sury's higher version numbers quietly replace Ubuntu's `php8.5-*`, `libgd3` and `php-common`. Those packages then get updates from neither repo, and unattended-upgrades does not cover sury or the duplicity PPA. Our fork added an apt pin and a key fingerprint check, and moves already-replaced packages back to Ubuntu's builds (f31885f, 832f3a7).

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
  - `99-local-sieve.conf` is copied with plain `cp`, so Dovecot sees the literal text `$STORAGE_ROOT` in its paths. User filters and vacation replies do not run (2bf1e1e).
  - `sieve_redirect_envelope_from` sits inside the personal script block, where Dovecot ignores it. Sieve redirects keep the external sender as envelope sender and fail SPF (f7878b8).
  - The userdb still returns the 2.3 field `quota_rule`, so per-user quotas have no effect (6526ad7).
  - `quota_storage_grace = 100M` is a fixed size, not the old 10% per user (85e9eb7).
  - `quota_status_toolarge` is not set. In 2.4.2 it is empty, so Postfix accepts messages larger than the whole quota (728fe54).
  - The 26.04 ManageSieve config opens port 2000 on all interfaces (c929f6f).
  - The fail2ban dovecot jail matches nothing on 26.04 and Dovecot 2.4 (8bbeb60).

### Postfix

- The only Postfix change: `smtpd_tls_dh1024_param_file` points to the new `dh4096.pem`. No other Postfix 3.10 adjustments were made.
- Limitation: Dovecot's quota-status policy now answers `quota_status_success = OK` and `quota_status_nouser = "REJECT Unknown user"`. Postfix asks this service before it resolves aliases, so mail to aliases, catch-alls and domain aliases would be rejected. `OK` also skips the remaining recipient restrictions. Our fork went back to `DUNNO` (6526ad7).

### Spam

- The `dovecot-antispam` plugin no longer exists for Dovecot 2.4. It is replaced by IMAPSieve: `report-spam.sieve` and `report-ham.sieve` run when a message is moved into or out of Spam/Junk, and pipe it to the new wrappers `sa-learn-spam.sh` and `sa-learn-ham.sh` in `/usr/lib/dovecot/sieve`. `sa-learn-pipe.sh` is removed.
- spampd options move from `/etc/default/spampd` to `/etc/spampd.cfg` (`maxsize=2000`, `local-only=0`). `CRON=1` is now written to `/etc/default/spamd` instead of `/etc/default/spamassassin`.
- Limitations the PR left (all fixed in our fork):
  - The sa-learn wrappers and sieve files have CRLF line endings. The shebang `#!/bin/bash\r` fails, so spam/ham learning never runs (f7878b8, plus `.gitattributes` in a3e55c6).
  - spampd 2.62 reads `local-only=0` as "local-only on", so DNSBL, URIBL, Pyzor, Razor and DKIM checks are off.
  - SpamAssassin 4.0 ignores `CRON=1`, so rule updates never run.
  - The spamd daemon, which MIAB does not use, stays enabled (ecc169a).
  - Moving a message from Spam to Trash subfolders or to Junk is learned wrongly (f7878b8).

### DNS

- DSA is removed from the SSHFP records (OpenSSH 10 has no DSA), and `ssh-keyscan` no longer asks for `dsa`.
- When `ssh-keyscan` fails, the SSHFP records are now skipped instead of aborting the whole DNS update. Before this, creating the first user returned HTTP 500 before the user got admin rights (Gwerlas, 615c104).
- Limitation: removing DSA also renumbered the remaining algorithms (ECDSA becomes 2, Ed25519 becomes 3). These numbers are assigned by IANA, so the signed zone would publish wrong SSHFP records. Our fork restored the IANA numbers (142abba).
- Limitation: OpenSSH 10 throttles repeated connections that never log in (`PerSourcePenalties`). The SSHFP records therefore come and go. Our fork reads the host keys sshd actually serves instead (2c7e109, 3e77095).

### Web / PHP-FPM / nginx

- The PHP-FPM socket and service names change from `php8.0-fpm` to `php8.5-fpm` in `nginx-top.conf`, `backup.py` and `owncloud-restore.sh`.
- `listen 443 ssl http2;` becomes `listen 443 ssl;` plus `http2 on;`, the syntax current nginx versions expect.
- The nginx DH parameters and `setup/ssl.sh` switch from a 2048-bit `dh2048.pem` to a newly generated 4096-bit `dh4096.pem`. Limitation: generating 4096-bit parameters adds minutes to every fresh install, and existing boxes already have `dh2048.pem`. Our fork reverted this (e602241).
- Limitation: Nextcloud's `.mjs` ES modules are not served as JavaScript. Fixed in our fork (44ce759).

### Nextcloud chain

- The target version moves from 27.1.11 to 34.0.3. The apps move with it: contacts 8.8.0, calendar 6.5.4, user_external 4.0.0.
- New upgrade steps take an existing install through each major release in turn: 26 → 27.1.11 → 28.0.14 → 29.0.16 → 30.0.17 → 31.0.14 → 32.0.10 → 33.0.7, then 34.
- Upgrades from 26 to 31 run `occ` under a temporarily installed PHP 8.2. Later steps use PHP 8.5. At the end, PHP 8.2 is removed with `apt-get purge php8.2*`.
- The timezone is read with `timedatectl` instead of `/etc/timezone`, which 26.04 no longer has.
- The opcache settings are written to `cli/php.ini` instead of `cli/conf.d/10-opcache.ini`.
- Limitations the PR left (all fixed in our fork):
  - The old steps to Nextcloud 21–26 remain, but they need PHP 8.1 or older, which 26.04 cannot provide (9327323).
  - Setup runs with `set -e`, so a failed `occ upgrade` aborts setup before the retry. Nextcloud then stays in maintenance mode and php-fpm stays stopped, which also takes Roundcube and Z-Push down (6a15bcf).
  - The opcache settings only reach the CLI, not PHP-FPM (6a15bcf).
  - The commit "Placeholder for Nextcloud 35" is mislabelled; it is actually the 33 → 34 step.

### Roundcube

- Roundcube moves from 1.6.19 to 1.7.4, and the CardDAV plugin from 4.4.3 to 5.1.3.
- The nginx `/mail/` location now points to Roundcube 1.7's `public_html/` docroot, uses `try_files` and a nested PHP location.
- Limitations the PR left (all fixed in our fork):
  - The CardDAV preset still uses the 4.x keys `url` and `preemptive_auth`. The 5.x plugin drops them silently, so Nextcloud contacts never appear in Roundcube (9b97bb9).
  - Roundcube 1.7 serves its assets as `static.php/<path>`. These only work because PHP's default `cgi.fix_pathinfo=1` happens to cover them (12b0d72).
  - The html5_notifier icon path does not fit the new docroot.

### Z-Push

- Z-Push moves from 2.7.6 to 2.7.7, the same version and hash as v78. The timezone is read with `timedatectl` instead of `/etc/timezone`.
- Limitation: this also affects upstream v78. In 2.7.7 the autodiscover config does not define `DAV_SSL_VERIFY`, so autodiscover requests fail with HTTP 500 (fixed in our fork, 4e28dfe). `MBSTRING_OVERLOAD` is also missing on PHP 8 (fixed in our fork, 09b9610).

### Management / Python

- `ssl_certificates.py` no longer uses `datetime.utcnow()`, which Python 3.12+ deprecates. It now uses `datetime.now(timezone.utc).replace(tzinfo=None)`.
- `mailinabox.service` and `munin.service` are now enabled with `systemctl enable <path>` instead of `systemctl link` + `unmask`.
- Limitations the PR left (all fixed in our fork):
  - rsyslog on 26.04 writes RFC 3339 timestamps, which `mail_log.py` does not parse, so the usage report loses all Postfix lines (3d541ac).
  - Python 3.14 warns about a `return` inside `finally` in `daemon.py` (1c7dacc).

### Backup

- `backup.py` stops and starts `php8.5-fpm`.
- `duplicity` helpers now come from apt (`python3-gnupg`, `python3-b2sdk`, `python3-boto3`). The `pip3 install b2sdk boto3` line was not removed but left commented out with the note `## TEST:`.

### Tools / other

- `tools/owncloud-restore.sh` only swaps `php8.0-fpm` for `php8.5-fpm`. Limitation: `PHP_VER` is never defined, and the script cannot restore a pre-chain backup whose Nextcloud 27 code will not run on PHP 8.5. Fixed in our fork (7e56f5a).
- Limitation: nsd still logs to `/var/log/nsd.log`, which its systemd sandbox does not let it write. Our fork switched it to syslog (c42df47).

### Merge of v78 into the PR head (d817620)

- v78 itself only changes two things on top of v77: Z-Push 2.7.7 (#2608) and Roundcube 1.6.20 (#2611), plus its CHANGELOG entry and the bootstrap tag.
- Z-Push 2.7.7 merged without a conflict: the PR had already made the same version and hash change, and the PR's `timedatectl` edits stay as they were.
- `setup/bootstrap.sh` took v78's `TAG=v77 → v78`. That only touches the 22.04 branch; a 26.04 branch was added later in our fork.
- `CHANGELOG.md` took the upstream "Version 78 (October 22, 2026)" entry unchanged.
- The one conflict was Roundcube, in `setup/webmail.sh`: v78 has 1.6.20, the PR has 1.7.4. The merge took neither and used 1.7.5, the 1.7 security release that matches 1.6.20 (SHA1 `396b2fa…`, later re-pinned as SHA256). The PR's CardDAV 5.1.3 was kept.
- Apart from these, the merged tree is identical to the PR head (`git diff c6118db d817620` shows only these three files).
