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

Seen in the work on rc7, v78-r2604.0, v78-r2604.1, v78-r2604.2,
v78-r2604.3, v78-r2604.4, v78-r2604.5 and this release, not done (the certification runs add their open findings in TESTING-fork.md):

* **The in-place and migration tools trust a local tag of the release name**\
  `tools/upgrade-in-place-to-2604.sh` (an existing checkout of the fork,
  `update_fork_dir`) and `tools/migrate-to-2604.sh` (`resolve_miab_dir`)
  still decide by the name that `git describe` prints whether to fetch the
  release, as bootstrap.sh did before B202: a local tag of the release's
  name on another commit keeps the old code. The same comparison with the
  commit of the tag at the source (`git ls-remote`) would find it (seen in
  the work on B202).
* **Munin critical-only alerts never mail the return to normal**\
  Critical only (Munin's alerts) never mails the return to normal. Not
  possible with Munin's text template, which `contact.admin.text` sets:
  munin-limits (Munin 2.0) gives it the values that are critical, warning
  or unknown now and those back to normal in this run (`fofields`), not
  the state a value had before, so a template cannot tell a value back
  from critical from one back from warning, nor see one that drops from
  critical to warning. README-fork.md (Munin alerts) says so. A fix would
  need munin-notify to keep the critical values of the last run itself.
* **The storage user can still replace $STORAGE_ROOT/mail and ssl/**\
  The storage user owns `$STORAGE_ROOT` and can rename `mail/` and `ssl/`
  in it and put directories of its own there: Dovecot, Postfix and the
  management daemon open `users.sqlite` by path, and the services read the
  private keys by path. Setup no longer makes such a `mail/` or database
  root's (it stops), but the services would use them. A fix needs both in
  a directory of root's outside `$STORAGE_ROOT` (or a bind mount), which
  changes the paths of the backups and the tools; README-fork.md, "Known
  issues" (seen in the review of B210 to B213).
* **A local fail2ban file with ignoreip overrides the panel's allowlist**\
  A `jail.local` or `jail.d/*.local` of the administrator that sets
  `ignoreip` in `[DEFAULT]` is read after `jail.d/mailinabox_adaptive.conf`
  and replaces the `ignoreip` that the allowlist of System > Intrusion
  Protection writes there: the panel lists an address as allowlisted, and
  no jail ignores it. The page does not warn about it (seen in the test
  runs of this release).
* **A package run started just before mail goes offline is not in the snapshot**\
  The in-place tool takes the package lists and the system archive while
  mail still runs, checks for running package updates, and then masks and
  stops the units. A package run that starts after that check and before
  the masks (`apt-daily-upgrade.service` has `KillMode=process`, so
  stopping it leaves unattended-upgrade running) ends while `stop_mail`
  waits for the dpkg lock (B190), but its changes are not in the package
  lists and the archive that `--rollback` uses. Comparing
  `/var/log/apt/history.log` or the mtime of `/var/lib/dpkg/status` with
  the moment of the archive after that wait would find it (seen in the
  review of this release, from the code; not seen in a test run).
* **No log line for a successful webmail password change**\
  `POST /me/password` (webmail's password change through the management
  daemon, B210) logs failures (for fail2ban) but not a successful change
  (seen in the test runs of this release).
* **The journal may lose a whole file at a rotation**\
  setup/system.sh sets journald's `MaxRetentionSec=10day` (upstream). On a
  copy of a production box the system journal before a moment in an update
  test was gone while syslog and mail.log were intact, which takes the
  setup marks that the log audit needs; a likely cause, not confirmed, is
  that journald removes a rotated file whole when its oldest entry is
  older than the retention (seen in the test runs of this release).
* **www-data is still in the group dovecot**\
  Setup adds www-data to the group dovecot, as upstream did "so PHP can use
  doveadm, for the password changing plugin". No version of this fork uses
  that (its password plugin hashed in PHP, and since B210 the management
  daemon changes the password). The group gives access to some of Dovecot's
  sockets (for example its statistics); taking www-data out of it needs a
  check of what else relies on it (seen in the work on B210).
* **spampd checks at most three mails at a time**\
  Postfix hands each mail for the box's users to spampd, which runs
  Ubuntu's default of three processes (`max-servers 3` in
  `/etc/spampd.cfg`; setup sets only its ports). At about 2 s per check,
  a burst of incoming mail waits in Postfix's queue: in an update test
  with client load and an extra mail every 2 s, local delivery took 10 to
  22 s before any restart, and after setup's restarts four mails waited
  about 100 s past setup's end. More processes would need more memory
  (about 100 MB each); a setting for it would let a busy box choose (seen
  in the test of B225).

## v78-r2604.5 (2026-11-23)

A larger release. New: a per-account limit of failed logins through the
box's own services (the account lock, B126), a sending limit with an
emergency brake against floods of outgoing mail (B221), banned addresses
page by page (B220), a switch that turns fail2ban off for tests,
System > Notifications, and setup restarts services only when
their configuration changed. Fixed: the status pages and mails (B178 to
B184), the in-place and migration tools (B154, B161, B186 to B190, B200 to
B204), the reading of root's files from the storage user's directories
(B183, B191, B210 to B213), and the restarts during an update (B122, B189,
B222 to B225). Tested by the full set of scenarios T1 to T5b and T7, an
in-place upgrade from 24.04 (T3) and updates of a copy of a production box
from v78-r2604.4 under client load (T5b and three repeated runs), see
TESTING-fork.md.

### New

* **fail2ban can be turned off for tests**\
  System > Intrusion Detection and Prevention > Settings has a checkbox
  "fail2ban (on by default)". Turned off, fail2ban is stopped and disabled
  (`systemctl disable --now`), so that no address is banned after failed
  logins and the current bans are lifted, for example while a test sends
  wrong passwords on purpose; turned on again, it is enabled and started,
  and the bans that have not run out come back from its database. The page
  asks before turning it off and shows a warning while it is off, and the
  status checks warn instead of reporting "fail2ban is not running"
  (so the daily status mail mentions it). Setup keeps it off
  (`fail2ban_admin.py --setup` exits with code 4, `setup/start.sh` then
  stops and disables it instead of reloading it). Nextcloud's throttle and
  the limit of failed logins through the box's own services do not depend
  on it. API: the field `enabled` of `/system/fail2ban/settings` and of the
  status. New offline test `tests/fork/fail2ban-switch.py`.

* **Sending limit with an emergency brake: a flood of mail from the box is stopped (B221)**\
  All mail that the users and the box itself send now passes a small
  Postfix milter (`conf/send-limit/sendlimit-milter.py`, service
  `miab-sendlimit`, package `python3-milter` from universe): mail programs
  and webmail (SMTP with login on ports 465 and 587), ActiveSync,
  Nextcloud, Sieve redirects, cron and other programs on the box
  (sendmail), and SMTP from the box itself without a login (127.0.0.1 and
  ::1 on port 25, which Postfix lets relay). Up to 30 mails go out at
  once, then 30 a second; each recipient counts as one mail. The first
  mail more sets off the brake: from then on all outgoing mail is accepted
  and put on hold in Postfix's queue (no sender gets an error, nothing is
  lost), the recipient of the box's reports is mailed at once, and the new
  service `miab-sendlimit-release` lets held mail go out only at 10 mails a
  minute, the senders in turn, or, if so set, nothing at all until the
  administrator ends the brake. Without the stop the brake ends by itself
  once nothing is held and no more than the limit came for 30 minutes. An
  account that was taken over so gets a few dozen mails out instead of
  thousands (in a test 6 to 7 of 120 at a limit of 5 a second), and its
  held mail can be deleted before it goes out. System > Intrusion
  Detection and Prevention (the page's new name) sets the limit and the
  brake, shows the brake with "End the brake", lists the held mail by
  sender with "Release now" and "Delete", and the minutes of the last 24
  hours in which the limit acted; API `/system/send-limit` and
  `/system/send-limit/held`, command line `management/send_limit.py
  --status`, `--release`, `--delete`, `--end`. While the brake is on,
  held mail goes out at the brake's rate on average; as a token bucket it
  may let up to that many go at once, so a minute can see a few more.
  Nothing is released in the brake's first period (`brake_per`), also no
  mail with more recipients than `brake_rate` (the first version let such
  mail out at once: 60 to 120 recipients in the first second in the lab).
  A changed limit keeps counting the mails that went out, up to the new
  limit (a first version treated the bucket as full after a change: with
  30 a second restored after a test with 1 an hour, the next mail set off
  the brake).
  The box's own mail to administrator@ and to the report recipient is
  never held. The release service releases only mail that is in the hold
  queue and had arrived when the milter held it (up to 5 days before, as
  sendmail's mail enters Postfix's queue when it is written to the
  maildrop, which can be long before pickup hands it to the milter); mail
  in the hold queue that is not on its list (held by hand, or a record it
  could not verify) is counted, and the control panel and the
  administrator's mail say how many and how to release or delete it. Mail from
  other servers is not counted. The milter runs as a dynamic user without
  privileges, and it fails closed: when it does not answer (stopped,
  crashed or hung), Postfix refuses outgoing mail with a temporary error
  (`454 4.3.0` on the submission ports, `451 4.7.1` on port 25;
  `default_action=tempfail` for this milter only, OpenDKIM and OpenDMARC
  keep `accept`) instead of letting it out without a limit; mail programs
  send it again, webmail shows an error, the mail of ActiveSync and
  sendmail waits in Postfix's maildrop
  queue until the milter is back, and systemd restarts it after 2 seconds
  without ever giving up. Mail from other servers does not depend on it:
  on port 25 Postfix asks it only for mail from the box itself
  (`smtpd_milter_maps`, `/etc/postfix/sendlimit-milters.cidr`). The box's
  own reports (status checks, backup and TLS reports, the usage report, the
  mails of the guard and of the sending limit, the test mail of System >
  Notifications) go through a new listener of Postfix, `127.0.0.1:10587`
  (`postfix/adminmail` in the log), which does not pass this milter: it
  takes mail only from the box itself, only to administrator@ and the report
  recipient (`/etc/postfix/sendlimit-admin-recipients`, written by
  `send_limit.py --apply` and again when the report recipient changes) and
  at most 20 mails a minute, so it cannot be used to send mail elsewhere.
  So the administrator still gets mail while the milter is down: the cron
  job of the sending limit asks the milter every 5 minutes (Postfix's first
  question, so a stopped or hung milter is caught as well as a missing one)
  and mails when it has not answered for 4 minutes, and again when it
  answers; mail of cron jobs and Munin's alerts (sendmail) wait with the
  rest. Turned off (the checkbox of the limit), the milter is taken out of
  Postfix's way altogether (`smtpd_milter_maps` empty, `non_smtpd_milters`
  and `$sendlimit_submission_milters` without it; `send_limit.py --apply`
  sets this when the setting changes, setup reads the milter's settings
  file), so that nothing then depends on it; held mail goes out, and the
  cron job does not watch the milter. A downgrade to v78-r2604.4 keeps `smtpd_milter_maps` and the two services,
  so mail from the box itself on port 25 still passes the limit (or, with the
  services removed, is refused: remove the setting with `postconf -X
  smtpd_milter_maps`). Without
  the release service nothing is held (a mail then waits at most 20
  seconds, sendmail 60, and is deferred with `451 4.7.1`; the minutes then
  count each new try of such a mail as deferred again). Limits: the
  recipients are counted as the sender gave them, before Postfix expands
  aliases, so a mail to an alias that forwards to many addresses counts
  once (only administrators add aliases), and mail from other servers that
  aliases forward on is not counted either. A mail with more recipients
  than the limit goes out at once when nothing waits and counts in full,
  so the next mail within the following seconds sets off the brake; a box
  whose users send to many recipients at once should raise the limit.
  A second, long limit stops a steady flood below the first one: by
  default at most 1000 mails (recipients) an hour, set and turned off on the
  same page (`long_enabled`, `long_rate`, `long_per`); a mail must fit both,
  and more than either sets off the same brake, whose mail and log line say
  which limit it was. In the lab test of the first version, floods of 1000
  mails by SMTP at 23 a second, and of 300 by webmail, ActiveSync and
  sendmail at 2 to 7 a second, all went out without the brake. Before, an
  account that was taken over or a program on the box could send any
  amount of mail in the box's name before anyone noticed, and ruin the
  reputation of its address with other mail providers. New offline test
  `tests/fork/send-limit.py`, smoke checks `admin-send-limit` and the
  `GET /system/send-limit` shape.

* **New page System > Notifications: where reports and alerts go**\
  The control panel has a new page System > Notifications. It sets the
  recipient of the box's reports (status check changes, backup status, TLS
  results, usage report): administrator@ of the box's name as before, or
  a custom address, also of another provider, with a test mail. Munin's
  alert settings moved there from the Munin page; their standard
  recipient ("Same as the reports") follows the report recipient. The page
  shows where the alias administrator@ leads, followed through the
  aliases as Postfix does, warns about a loop or an address of the box
  that does not exist, and says that the mail to abuse@, postmaster@,
  hostmaster@, admin@ and of root and cron jobs still goes there (the alias
  is an address of domain control validation and is not changed). It
  lists what the box mails and the last deliveries from the mail log. API
  `/system/notifications`, command line `management/admin_mail.py`; new
  offline test `tests/fork/admin-mail.py` and smoke checks
  `api-notifications`, `admin-notifications-unit`.
* **System > Munin Monitoring opens Munin directly again**\
  The menu entry opens Munin in a new tab without leaving the page shown
  (the tab is opened in the click, so pop-up blockers let it through). The
  old address `#munin` still works.
* **Setup points to tools/update-check.sh at the end of a run**\
  At the end of a setup run on an existing box, setup prints a short hint
  at `tools/update-check.sh`, without stopping: when the newest record in
  `/root/update-check/` has a state from before an update but none from
  after it, the commands `after` and `mailcheck` with that record
  (`--dir STAMP`); otherwise that `before` and `backup` can be run before
  the next update and `after` and `mailcheck` after it (optional). Not on
  a first install, and not when the in-place upgrade or the migration tool
  runs setup (they have their own reports and now set `MIAB_SETUP_TOOL`
  for their setup run). New offline test `tests/fork/update-check-hint.py`.
* **Intrusion Detection and Prevention recognises banned Microsoft servers (B126)**\
  System > Intrusion Detection and Prevention shows a hint at a banned address of the
  servers through which Outlook for iOS and Android syncs Exchange
  ActiveSync accounts: 20 wrong passwords there within two minutes get all
  users of the app banned, and anyone can cause it on purpose (B126;
  `miab-zpush` still counts for recidive). The hint offers a
  button "Put <network> on the allowlist", which asks first and says what
  it costs (guesses through these servers are no longer banned, and with
  Dovecot's answer at once to the IMAP logins of Z-Push from 127.0.0.1,
  B126, not slowed down either); nothing is
  put on the allowlist on its own. The addresses are recognised by
  Microsoft's published IP ranges of Exchange Online (Microsoft 365 IP
  Address and URL web service, service area Exchange) and of its
  AutoDetect service, which Microsoft names for an ActiveSync server that
  Outlook for iOS and Android reaches, shipped as
  `conf/fail2ban/microsoft-relays.txt` with its source, version, date and
  SHA256 sums; `tools/update-microsoft-relays.py` refreshes it, the box
  downloads nothing, and a list changed by hand is not used. Reverse DNS
  decides nothing: the address's PTR name is shown only when it resolves
  back to the address. API: `/system/fail2ban` has `relays` and
  `relays_source`. New offline test `tests/fork/cloud-relays.py` and smoke
  check `admin-cloud-relays-unit`.

### Changed

* **System > Intrusion Protection is now "Intrusion Detection and Prevention"**\
  The page has a new name, in the menu, on the page and in the texts and
  mails of the box that point to it: it detects attacks (fail2ban's jails,
  the failed-login report, the limit of failed logins from the box itself)
  and now also prevents a flood of mail from the box (the sending limit,
  B221). Its link (`#fail2ban`) and the API paths stay the same. The
  administrator's audit line for its settings now says "the intrusion
  detection and prevention settings"; the log audit accepts both forms.

* **Intrusion Detection and Prevention lists the banned addresses page by page (B220)**\
  Under a larger attack System > Intrusion Detection and Prevention loaded for a long
  time or not at all, and its table "Banned in, and why" was wider than
  the page (B220). The page now shows the networks with the most banned
  addresses (a click filters by one) and a compact table, one row per
  address: address, jails, since, end, "Why?" and "Unban". "Why?" loads
  the failures, log lines and rule of each ban into a row below, with
  "in this jail only"; long text wraps. The filter (part of an address or
  jail, or a network such as `192.0.2.0/24`) is applied on the server, in
  pages of 50 with previous and next. API: `GET /system/fail2ban` is an
  overview without the bans (counters, `banned_count` per jail,
  `top_networks`, `client.banned_in`, relay hints); new
  `GET /system/fail2ban/bans` (`filter`, `offset`, `limit` up to 200) and
  `GET /system/fail2ban/ban-reason?ip=`. A script that read `jails[].banned`
  or `reason` from the status uses these now. New offline test
  `tests/fork/ban-list.py` (10,000 synthetic bans), smoke checks
  `admin-fail2ban-bans` and `admin-ban-list-unit`.
* **Tests: the lab preparation leaves the seeded mails alone**\
  New `tests/fork/spam-move.py` for test boxes: it moves a marked test mail
  of its own into Spam and back, so that IMAPSieve runs sa-learn as for a
  user's client, deletes it and checks that the other mails keep their
  UIDs. The preparation of the update test's start snapshot (T5b) moved a
  seeded INBOX mail instead, which gave it a new UID and so a new POP3 UIDL,
  and the smoke check `mig-pop3-uidl-alice` failed on every run from that
  snapshot, also before any update (T5b of v78-r2604.3). A snapshot
  prepared with the new script works with the original manifest
  (TESTING-fork.md, "Test environment").
* **Tests: log audit allowlists from the test runs of this release**\
  `tests/fork/log-audit.sh` also names the local part of a mailbox path
  under the box's own name `<user>` (the mailboxes of the box's name, such
  as postmaster@, kept their local part and missed the rules of
  fts-xapian's notes). New or wider rules, each with its reason: a report
  recipient at another provider in System > Notifications; Roundcube's
  CardDAV migration race of two first logins (README-fork.md names it for an
  update from rc7); Z-Push's
  "could not stat folder" at setup's Dovecot reload; fail2ban's note on the
  first match of `miab-munin` after its start; the in-place and migration
  tools' own notices of local Roundcube changes; the first start of the
  slow-login jails on a box upgraded in place; dbus, systemd-tmpfiles,
  AppArmor (named) and containerd notes of the release upgrades; and in
  `log-audit-allow-old-box.txt` Dovecot 2.3's anvil note at the old box's
  stop and `postqueue`'s note when `--check-old` reads the stopped old
  box's queue. From the repeated runs: an IMAP process and an smtpd that
  lose their service in the moment of setup's Dovecot and Postfix reloads.
* **Checks that the control panel's icons and scripts are installed**\
  The planned item "Control panel asks for a favicon.ico that is not
  installed" (an nginx 404 for `/admin/assets/branding/favicon.ico`, noted
  in rc7) is closed without a change of setup: setup/management.sh copies
  the file since the fork's icons were added, and T1 of v78-r2604.0 found
  the panel's icons served. A possible source of the 404 is an update of
  rc7 or earlier, where setup emptied the assets directory before it
  filled it again (B157, fixed in v78-r2604.2). New offline check
  `tests/fork/panel-assets.py` (every file that a template names under
  `/admin/assets/` is one that setup installs, and the icons that setup
  copies are in the repository) and smoke check `admin-panel-assets`
  (each of them is served, the icons are the files of `branding/`).
* **Setup restarts OpenDKIM, spampd and others only on a change**\
  Setup restarted OpenDKIM and OpenDMARC, spampd, postgrey, named,
  systemd-resolved, munin-node and the management daemon on every run,
  also when nothing had changed; while OpenDKIM restarts, Postfix passes
  mail unsigned (`milter_default_action`), while spampd or postgrey
  restart, deliveries wait or are deferred, and while named restarts, the
  box's lookups fail. Each of them is now restarted only when what it
  reads at its start changed since setup last restarted it (a checksum in
  `/var/lib/mailinabox/<unit>-config.sha256`, as for Dovecot since B122:
  its configuration files and drop-ins; for OpenDKIM also `TrustedHosts`
  and the DKIM key file, not `KeyTable` and `SigningTable`, for which the
  management daemon restarts it; Munin's plugin links; the management
  daemon's code, start script, `/etc/mailinabox.conf` and the packages of
  its virtualenv), or when it
  does not run or runs the program of an older package (for spampd,
  postgrey and munin-node also of the Perl modules they read, which no
  "(deleted)" mapping shows: `spamassassin`, `libnet-server-perl`,
  `munin-common`, so that a SpamAssassin update still restarts spampd as
  the restart on every run did), or when it was started since setup
  recorded the checksum, by anything else or at boot (the record names
  the unit's systemd `InvocationID` too). The
  last one covers a downgrade to v78-r2604.4, whose setup restarts them
  with its own code and keeps no checksum, and the way back up, also with
  a reboot in between (the services then start at boot from the old
  checkout and files): the
  checksum is the same as before the downgrade, and the management daemon
  of v78-r2604.4 (without `POST /me/password` for webmail's password
  change) would have kept running. A first version went by the start
  time and trusted every start at boot, which missed the reboot (found in
  the review). The price: the first setup run after a reboot, or after a
  restart by an administrator or a package, restarts each of them once
  more. Not after sa-update's restart of spampd for new rules (nearly
  daily): a hook after the package's (`sa-update-hooks.d/spampd-record`)
  records that run when spampd's files are those of the record, and a
  drop-in lets `spamassassin-maintenance.service` write that one record
  (found in the review). The management daemon's restart of OpenDKIM for
  new DKIM tables and the postgrey whitelist update (every 28 days) still
  cost one more restart at the next run. The same holds for
  PHP-FPM (B122, a reload then). The first run of
  this release restarts each of them once more. New offline test
  `tests/fork/restart-on-change.py`. `tools/update-check.sh after` accepts
  the new drop-in of `spamassassin-maintenance.service`
  (`expected-changes/v78-r2604.5.txt`; without it, every update to this
  release ended "RESULT: CHANGED", found in its test runs), and
  `tests/fork/update-check-compare.py` checks that every drop-in that setup
  writes is in a list of expected changes.
* **Setup removes old Nextcloud backup copies, keeps the newest three**\
  `$STORAGE_ROOT/owncloud-backup` grew with every update of Nextcloud and of
  its pinned apps: each leaves a copy of the database, `config.php` and the
  replaced code, nothing removed them (one box had 2.5 GB there), and the
  directory is not in the box's backup. setup/nextcloud.sh now keeps the
  three newest copies (named by setup's date and time, the one of the run
  among them) and all of the last 14 days, and removes the older ones;
  other names in the directory stay. The 14 days keep the copy from
  before an upgrade that failed: every later run makes another copy, of
  the half-upgraded state. It works through one descriptor of the directory, which must be
  root's own and not writable by others (B177), and does not follow a
  symbolic link (the storage user owns `$STORAGE_ROOT`); a problem is
  reported and setup goes on. New tool `tools/owncloud_backup_prune.py`,
  offline test `tests/fork/owncloud-backup-prune.py`.
* **README: known issues (B122, B121, B137)**\
  README-fork.md has a new section "Known issues / Bekannte
  Einschränkungen" (English and German) with three issues from the list of
  planned work: a Dovecot reload ends the open IMAP sessions (B122); it
  still causes two client-visible failures, a login handed to the new auth
  process at that moment and a Z-Push answer that cannot connect again
  (B122, B121, B137); and a race in the migration of Roundcube's CardDAV
  plugin when two sessions log in at once after its upgrade (to be
  reported to the plugin project).
* **Setup's comment on Spamhaus and public resolvers corrected (B136)**\
  The comment in setup/network-checks.sh no longer names 8.8.8.8 among the
  resolvers whose queries Spamhaus refuses with 127.255.255.254: through
  8.8.8.8 Spamhaus answers NXDOMAIN, also for its own test entries, so
  setup's checks can neither see a listing there nor say that they could
  not check. This stays a known issue (README-fork.md, "Known issues").
* **README: PHP 8.5 in universe, security updates with Ubuntu Pro**\
  README-fork.md has a new section "Security updates and Ubuntu Pro /
  Sicherheitsupdates und Ubuntu Pro" (English and German): `php8.5-fpm`
  and some PHP modules of the box (and `nsd`, `opendkim`, `opendmarc`,
  `spampd`, `postgrey`, `fail2ban`, `munin`, `certbot`) are in Ubuntu's
  universe component, whose security updates Canonical guarantees only
  with Ubuntu Pro (`esm-apps`); what that means for a box, and how to turn
  it on (`pro attach`, a free personal subscription).
* **Postfix's smtpd_tls_dh1024_param_file warning explained in the README (B59)**\
  The planned item "postconf warns that smtpd_tls_dh1024_param_file will
  be removed" is closed without a code change: a fresh install and an
  updated box of the current branch print no such warning (`postconf`,
  `postconf -d`, `postfix check`, the journal; the parameter is set in
  neither `main.cf` nor `master.cf`). The warnings in the test runs came
  from boxes on rc3 (before B59, which comments the parameter out) and
  from the in-place upgrade, while the release upgrade installs Postfix
  3.10 and `main.cf` of the old box still sets it, before setup runs.
  README-fork.md lists the line under "Setup output".
* **README: Nextcloud on SQLite and HTTP 500 during cron, a known issue**\
  The planned item "Nextcloud on SQLite answers CardDAV writes with HTTP
  500 during cron" moves to README-fork.md, "Known issues": Nextcloud's
  SQLite database is in WAL mode already (Nextcloud's default
  `sqlite.journal_mode`) and PHP waits up to 60 s for a lock (pdo_sqlite's
  default), checked on a test box; the immediate "database is locked" of a
  transaction that read first and then writes after another connection
  wrote is not changed by any setting, so setup changes nothing.
### Fixed

* **The sending limit warns when its release service does not run (B226)**\
  The control panel's page of the sending limit and `send_limit.py
  --status` showed no warning when only `miab-sendlimit-release` had
  stopped (then nothing is held or released); they now check both
  services on their own.

* **Mail that arrives during setup no longer waits 5 minutes (B225)**\
  Mail to the box's users that arrived while setup restarted spampd or
  Dovecot was deferred, and Postfix tried it again only after 5 minutes.
  At its end, setup now retries those mails at once (only those: other
  deferred mail keeps its schedule, held mail stays held). Found in the
  update test with client load.
* **Ports 465 and 587 no longer stop answering for a minute after a restart of Dovecot (B224)**\
  A submission process of Postfix that started while Dovecot restarted
  could not reach Dovecot's auth socket and exited, and Postfix then
  started no new one for 60 s: mail programs got no answer. Postfix now
  waits 10 s (`service_throttle_time`), and setup installs Dovecot's
  packages so that their scripts do not restart Dovecot: an update
  restarts it once, after setup wrote its configuration. Found in the
  update test with client load.
* **No failed logins when an update brings new passdbs (B223)**\
  Setup reloads Dovecot when its configuration changed. A reload that
  brings new passdbs (this release's account lock) could make Dovecot's
  auth process die under load, and the logins in that moment failed.
  Setup now restarts Dovecot when a passdb or userdb changed, and reloads
  it for all other changes as before. Found in the update test with client
  load.
* **Mail no longer waits 5 to 10 minutes after a reboot (B222)**\
  At boot Postfix started before spampd listened on port 10025; mail in
  the queue found the port refused, and Postfix then held back all mail to
  the box's users for 5 to 10 minutes, also mail that came in later. The
  start of spampd now ends only when it listens, and Postfix starts after
  it (systemd drop-ins written by `setup/spamassassin.sh`). Found in the
  in-place test.
* **No status change mail every night with nc's "succeeded!" line (B184)**\
  The status checks test outbound port 25 with nc, and the nc of Ubuntu
  26.04 prints "Connection to aspmx.l.google.com ... succeeded!" on
  standard error. The nightly job mails everything that the status checks
  print, so a "Status Checks Change Notice" with only that line went out
  every night, also when nothing had changed (now also to a report
  recipient at another provider). nc's output is now discarded. New cases
  in `tests/fork/status-dns.py`.
* **System Status "show more" and TLS result are shown again (B178)**\
  System Status shows the extra lines of its checks again: the "show more"
  link under a check was missing since rc4, so for example the DS records
  that "This domain's DNSSEC DS record is not set ... See below for
  instructions" refers to could not be seen. The TLS page shows the result
  of a certificate request again ("The TLS certificate was provisioned and
  installed." or the error). Both came from the update of the control
  panel's jQuery to 3.x, which reads `<div/>` as an opening tag (B178). New
  static check `tests/fork/panel-fragments.py`.
* **Status change mail shows changed checks whole; DNSSEC messages say where (B179)**\
  The daily "Status Checks Change Notice" shows a changed check with all of
  its lines: a DNSSEC warning now comes with the DS records to set, also
  when only the message changed (it said "See below for instructions."
  with nothing below), and a changed line comes with its message. The
  DNSSEC messages say that the DS records are listed below the message,
  in the control panel under "show more", instead of "see below". New
  offline test `tests/fork/status-changes.py`.
* **The control panel sends the HSTS header of the box (B180)**\
  nginx answers `/admin/` (the control panel, its API and Munin's pages)
  with the same HSTS header (`Strict-Transport-Security`) as the other
  pages of the box's name, or with none when HSTS is off for it in
  `$STORAGE_ROOT/www/custom.yaml`: the location's own headers had replaced
  the server's (B180, upstream). New offline test
  `tests/fork/nginx-hsts.py` and smoke check `web-hsts-admin`.
* **Status checks no longer crash on overlong domain names (B181)**\
  The status checks end no longer with a traceback when a lookup cannot be
  made: a mail domain whose name is too long with `.dbl.spamhaus.org`
  appended (more than about 237 characters) gets the warning that it is
  too long to be looked up in the Spamhaus DBL, and a lookup that a DNAME
  makes too long (YXDOMAIN) counts as a failed lookup (B181, upstream).
  New offline test `tests/fork/status-dns.py` and smoke check
  `admin-status-dns-unit`.
* **Failed DS lookup: "could not check", not "DS record is not set" (B182)**\
  When the lookup of a zone's DS record times out or fails, System Status
  and the daily status change notice say "Could not check this domain's
  DNSSEC DS record: the DNS lookup timed out/failed" instead of "This
  domain's DNSSEC DS record is not set" with the DS records to set (B182,
  upstream; B150 had left the DS lookups as they were). A zone's checks
  look its DS records up once instead of three times. New cases in
  `tests/fork/status-dns.py`.
* **In-place upgrade and migration name local Roundcube changes (B200)**\
  The in-place upgrade (tools/upgrade-in-place-to-2604.sh) and the
  migration (tools/migrate-to-2604.sh) no longer lose local changes to
  Roundcube without a word. Setup installs the new Roundcube as a new tree
  and writes its own `config/config.inc.php`, so plugins installed by hand
  and changes to that file were gone afterwards, and neither the check nor
  `etc-report.txt` named them. The preflight check (also `--check`) now
  warns, without stopping the upgrade, and names the plugin directories
  that setup does not install, plugins added to or left out of the plugin
  list, and other settings that differ from what setup writes (a setting
  that setup does not write by its name only, as its value may be a
  password). Before setup the tools keep the old `config.inc.php` and
  those plugin directories in `old-roundcube/` of their state directory
  (the in-place upgrade's system archive now also holds the whole old
  Roundcube). They are not copied back on their own, since a plugin for the
  old Roundcube can break the new one. Phase verify lists what the new
  Roundcube does not have, also in `etc-report.txt`, says how a hook in
  `/etc/mailinabox/upgrade-2604.d/` brings it back, and writes the open
  items into `local-changes.json` (root's only) in the state directory;
  while that file exists, System Status shows a warning with the items
  under "show more", and so the daily status change mail names it too. The
  new option `--ack-local` of both tools, or removing the file, ends it.
  New offline test `tests/fork/roundcube-local.py`. A first version of the
  migration tool's report stopped its preflight check, and so `--check`
  and the migration of every box with such changes, with "STORAGE_ROOT:
  unbound variable" (B185, found in the test runs of this release; the
  test now runs both tools' reports as bash with `set -u`). The kept
  plugin copies keep their modes (`old-roundcube/` itself is root's only),
  and phase verify names a local plugin that the web server cannot read:
  a first version made the copies root's only, and a plugin brought back
  with `cp -a` as proposed was not loaded by Roundcube, which logged an
  error on every request (B186, found in the test runs of this release; a
  first version of the check read the list of plugin directories, which
  the tools pass as a pipe, twice and so never named a plugin, found in
  the review of this release).
* **update-check.sh records the two TLS key exchange parameters of Postfix (B201)**\
  tools/update-check.sh now records `tls_eecdh_auto_curves` and
  `tls_ffdhe_auto_groups` too, so a change of Postfix's key exchange (such
  as the post-quantum one of v78-r2604.3) shows in its list of changes.
  `after` judges only the settings that both records have: a setting that
  only the record after the update has (recorded by a newer version of the
  tool, so its value before is unknown) is listed in a section "Newly
  recorded (not judged)" of `changes.txt` and counted in the RESULT line,
  not as an unexpected change. New offline test
  `tests/fork/update-check-compare.py`.
* **update-check after an in-place upgrade uses the old box's allowlist (B187)**\
  After an in-place upgrade, the log audit of `tools/update-check.sh after`
  starts while the old release still ran. It now adds
  `tests/fork/log-audit-allow-old-box.txt` by itself when the Ubuntu
  release changed, so lines such as SpamAssassin's daily restart of spamd
  on 24.04 before the upgrade are no longer new message classes ("RESULT:
  look at the new log message classes", exit code 1). New cases in
  `tests/fork/update-check-compare.py`.
* **bootstrap.sh is no longer fooled by a local tag of the release name (B202)**\
  bootstrap.sh fetched nothing when `git describe` printed the name of the
  release to install, so a local tag of that name on another commit (an
  old pre-release, a mirror's tag) kept the old code, and setup ran on it
  and ended with exit code 0. It now also asks the source for the commit
  of the tag (`git ls-remote`) and fetches the release when that is not the
  checkout's commit; after the checkout, it stops if the commit is still
  another one. When the source cannot be asked, it says so and uses the
  checkout as before. README-fork.md ("Updating the fork") is updated.
* **In-place upgrade --check proposes the start command with SOURCE and TAG (B203)**\
  The start command that `upgrade-in-place-to-2604.sh --check` proposes
  (and repeats when blockers stop a run) now begins with `SOURCE=...` and
  `TAG=...` when they are set, quoted for the shell, and through
  `curl | bash` names the script of that source instead of the GitHub URL.
  Whoever copied the line before ran the release from GitHub instead of
  the source and tag that were checked.
* **TAG may be a full commit id, also for a fresh clone (B188)**\
  The in-place upgrade and the migration through `curl | bash`, and a first
  install with `setup/bootstrap.sh`, clone the fork with `git clone -b
  $TAG`, which takes a tag or a branch only: `TAG=<commit id>` stopped
  with "Remote branch ... not found", although `--check` proposes the start
  command with it (B203). A full commit id (40 hex digits) is now fetched
  by its id; a short one fails with a hint. When the download fails, the
  in-place tool's advice names the given `SOURCE` instead of GitHub, and
  `setup/bootstrap.sh` says so (with the same hint for a short commit id)
  instead of ending without a message. New offline test
  `tests/fork/clone-ref.py`.
* **Migration tool filters the old box's error messages too (B154)**\
  `tools/migrate-to-2604.sh` passes the standard error of every command
  that talks to the old box (its scripts through ssh, the login checks, the
  copies of `/etc` and of the zones, rsync's checks and copies) to the
  terminal with control characters replaced by "?", as it does for the
  other text of the old box since B154; before, an error message of the old
  box could send escape sequences to the terminal. The progress filter of
  the main copy does the same for rsync's output. The carriage return at
  the end of ssh's own messages is dropped rather than shown as "?" (a
  first version printed "... to the list of known hosts.?"). New offline
  test `tests/fork/old-side-filter.py`.
* **In-place upgrade: no package run while mail goes offline (B190)**\
  When the in-place upgrade stopped mail, its mask of `apt-daily.timer`
  reloaded systemd, and `apt-daily-upgrade.timer` started a missed run of
  unattended-upgrade at once, which installed packages after the system
  archive and the package lists had been taken (so `--rollback` would
  restore another package state). The services of both timers are now
  masked first, in one call, and stay masked as long as the timers; the
  tool waits for the dpkg lock after stopping the units. New offline test
  `tests/fork/quiesce-order.py`.
* **Right in-place upgrade messages after a failed --redo-from (B161)**\
  When a `--redo-from` of the in-place upgrade fails, the exit message
  names the redo and when it started, and says that cron jobs, update
  timers and backups run when the upgrade had finished before (the redo
  does not pause them again; it said they "stay paused"), or stay paused
  until it is finished. A failed redo of setup says that setup runs again
  since then and mail may be offline until it has, instead of "Mail is
  OFFLINE" since the start of the upgrade's downtime. `--status` shows the
  downtime up to the end of the first setup and a line "Redo:" with the
  time setup ran again (or so far), instead of counting "Mail offline ...
  so far" from the start of the original downtime.
* **Migration tool's files in /root/migration are root's only (B204)**\
  The files and directories directly in `/root/migration` (the state of
  `tools/migrate-to-2604.sh`) are 0600 and 0700, among them the copies of
  the old box's backup key `old-id_rsa_miab`, of its `passwd` and `group`
  and the archive of its `/etc`; they were 0644 in a directory of root's
  only (0700), so nothing was exposed. The copies of the old box are
  written with umask 077, and the tool takes group and other access away
  from the entries directly in the directory at its start, after each
  phase and at its end, also from those of a migration that an older
  version of the tool started. The unpacked copy of the old `/etc`
  (`old-etc/`) keeps the modes of the old box inside its 0700 directory.
  The file with the exit code that the tmux window writes after the run
  (`.multiplexer-exit-code`) is made 0600 as well; a first version left it
  0644 until the next call of the tool.
* **Setup waits for Nextcloud's database lock (B189)**\
  Setup's update of the `user_external` rows in Nextcloud's SQLite database
  gave up at once when a CalDAV or CardDAV client or Nextcloud's cron job
  was writing ("Error: stepping, database is locked (5)" in setup's
  output). It now waits up to 60 seconds for the lock.
* **Setup leaves PHP-FPM alone when its configuration is unchanged (B122)**\
  Setup restarted PHP-FPM once per run (B122), which ended every running
  request: ActiveSync's Pings and Syncs, CalDAV and CardDAV, webmail and
  Nextcloud got HTTP 502. Now setup does nothing when PHP-FPM runs the
  current package and its configuration (`/etc/php/8.5/fpm` with the
  pools and the modules of `conf.d`, `mods-available`) is the one it
  loaded last (a checksum in `/var/lib/mailinabox/php-fpm-config.sha256`),
  so an update that changes nothing there no longer disturbs the clients.
  When it changed, setup reloads PHP-FPM instead of restarting it: the
  reload reads php.ini, the pools and the modules anew as a restart does
  (checked with a module turned off and `memory_limit` changed), keeps the
  listening socket, and lets the running requests finish for up to 5 s
  (`process_control_timeout`, new in `php-fpm.conf`). A request that runs
  longer, such as a Ping, is still ended then (502, as before), and new
  requests wait up to those 5 s; so the plan's idea that a reload would
  keep the long polls does not hold. Setup checks the configuration
  (`php-fpm8.5 -t`) first and restarts PHP-FPM when it does not run (after
  an upgrade of Nextcloud), runs an older package or replaced module, or
  has not logged "ready to handle connections" within 30 s of the reload.
* **Failed ActiveSync logins no longer take 10 to 50 seconds (B126)**\
  A wrong password over ActiveSync or Autodiscover took 13 to 26 s (seen
  up to 50 s), and a few failed logins of one client, below the ban
  threshold of `miab-zpush`, slowed the correct logins of all other users
  down to 15 s (measured on a test box: one wrong password every 3 s).
  Z-Push checks each password with up to three IMAP logins from
  127.0.0.1, and Dovecot delayed each failed login by 2 s and raised a
  penalty of 127.0.0.1 that delayed all later logins from there, of every
  user, by up to 15 s; Roundcube's and Nextcloud's IMAP logins come from
  127.0.0.1 too. Dovecot now answers failed logins from 127.0.0.1 and ::1
  at once and raises no penalty for them, and limits them per account
  instead (see "Security": "Failed logins from the box itself are limited
  per account"). These logins all come from services that fail2ban
  protects with the client's own address (`miab-zpush`, `miab-roundcube`,
  `miab-owncloud` and Nextcloud's throttle); logins from other addresses
  keep Dovecot's delay and penalty. Guesses through Microsoft's servers
  once they are on the allowlist are in README-fork.md, "Known issues".

### Security

* **Failed logins from the box itself are limited per account (B126)**\
  Without Dovecot's delay for 127.0.0.1 (B126 above), a process on the box
  that runs as one of its services, for example code run as www-data
  through a hole in PHP or in Roundcube, could try the passwords of every
  account as fast as Dovecot checks them (about 1000 a second on a test
  machine, against 5 to 30 a second with the delay); fail2ban does not ban
  127.0.0.1. Dovecot now counts the failed logins from 127.0.0.1 and ::1
  per account name, with two small Lua passdbs around the SQL one
  (package `dovecot-auth-lua`, `conf/dovecot-auth-guard/`): an account
  with 30 different wrong passwords from the box within 30 minutes (both
  numbers can be changed under System > Intrusion Detection and Prevention, which also
  lists the counted and refused accounts with a button to end a lock; the
  API `/system/auth-guard`) is refused for logins from the box until it
  has fewer, at once and before
  its password is checked, so further guesses tell nothing, not even a
  right one. A password sent again counts once, as with Dovecot's own
  penalty: a phone that keeps sending an old password (Z-Push tries up to
  three times per request) or a repeated typo cannot lock the account,
  while each guess counts; only a 16-bit tag of a hash of the password
  with a random salt is kept, never the password. Only the failures of
  the account itself count, and only real accounts are counted (the
  management daemon writes the list of accounts whenever they change; a
  name not on it, such as an account added while the list could not be
  written, is counted in a separate pool of 500 names):
  made-up names do not lower the limit of a real account, crowd out its
  count or fill the state. Only wrong passwords count; a login with the
  right password never does. "From the box" means every address of
  127.0.0.0/8, ::1, every address of the box's interfaces (link-local ones
  included, written again every 10 minutes) and any connection from an
  address to itself, as a process on the box can use any of them. Many
  connections at the same moment can get more guesses checked before the
  first failure is recorded, as the passwords are checked in parallel;
  such a burst then counts against the next windows as well (refused
  while the last k windows hold k times the limit, k = 1 to 4), so over
  time only a little more than the limit per window gets through: a
  burst that fills fewer than 4 windows can be repeated as soon as it
  leaves them (in the lab, bursts of 100 every 30 seconds with a window
  of 1 minute got 33 guesses a minute checked, not 30). A lock after a
  normal attack ends one window after it; after a burst it can last up to
  4 windows (2 hours by default). The number of windows can be set from 1
  to 4 as well (1: a lock never lasts longer than one window, but bursts
  get more through); and `auth_username_chars` is empty, so that a user name with "+"
  or a space no longer fails before these checks with Dovecot's delay and
  the penalty of 127.0.0.1. The other accounts
  are not slowed down (no penalty of 127.0.0.1), and the account's own
  mail programs that log in from outside are not refused. The price:
  someone who tries the passwords of one account through ActiveSync,
  webmail or Nextcloud from addresses fail2ban does not ban locks that
  account's phones, webmail and Nextcloud out while they keep trying.
  New locks are mailed to the report recipient (System > Notifications),
  at most one mail an hour (`management/auth_guard.py`, every 10
  minutes; the cron job does nothing when the program is missing, so a
  downgrade to v78-r2604.4 does not mail an error every 10 minutes);
  `sudo management/auth_guard.py --status` shows the counts and
  `--unlock ADDRESS` ends a lock as well. Dovecot reads the setting on
  every login from the box, so a change applies at once. If Dovecot cannot write its counts in
  `/run/miab-auth-guard`, failed logins from the box get Dovecot's delay
  again, never no limit. Setup now also reloads Dovecot when only these
  Lua files change (they are part of the configuration's checksum).

* **Webmail can no longer rewrite the user database (B210)**\
  `users.sqlite`, the database of all mail accounts, their password hashes,
  privileges and aliases, is root's only now (root:root 0600), and
  `$STORAGE_ROOT/mail` is root:root 755. Up to v78-r2604.4 the database was
  root:www-data 0664 in a directory that www-data could write, as upstream
  has it, because Roundcube's password plugin wrote it with SQL. So any code
  running as www-data could set the password of any account (also an
  administrator's), give itself the admin privilege, or add an alias that
  forwards a user's mail to the outside, and every local account could read
  all password hashes. Code running as www-data takes a hole in PHP,
  Roundcube, Nextcloud or Z-Push, but such holes are real and recent: the
  PHP releases of October 2026 ("PHP2Shell", CVE-2026-109618 and
  CVE-2026-109619, remote code execution, fixed in PHP 8.5.12, 8.4.27,
  8.3.36 and 8.2.35) and of 19 November 2026 (PHP 8.5.13 and others,
  several remote code execution issues), and Roundcube's post-authentication
  remote code execution CVE-2025-49113 (fixed in 1.6.11 and 1.5.10,
  exploited in the wild). Each gives code as www-data on a Mail-in-a-Box,
  and before this release that code could take over every mail account.
  Roundcube's Settings > Password now changes the password through the
  management daemon: the fork's password driver
  (`conf/roundcube-password-mailinabox.php`) calls the new endpoint
  `POST /me/password` on 127.0.0.1 (nginx does not pass it on from the
  Internet), which checks the current password (and
  two-factor authentication) as the control panel's login does, applies the
  same password rules and hash as the control panel, changes only the
  caller's own password, logs failed attempts for fail2ban's
  `miab-management` jail and refuses more after 5 failures for an account
  (one that exists, so that made-up names cannot push a real account's
  failures out of the limiter) or 10 for an address within 10 minutes. Roundcube's own messages (a wrong
  current password, a short new one) are as before. Every other reader opens
  the database as root (Dovecot's auth-worker, Postfix's daemons before they
  drop their privileges, the management daemon, the backup, the tools); the
  database stays in SQLite's rollback journal mode, in which readers need no
  write access to the directory. New offline test
  `tests/fork/self-password.py`, smoke check `api-self-password` (the
  endpoint closed from outside, and Roundcube's settings page).

* **Setup no longer reruns data migrations for a lowered version (B211)**\
  The storage user owns `$STORAGE_ROOT/mailinabox.version` and could write a
  lower number into it, and the next setup run ran the data migrations from
  there again as root (depending on the number deleting the DKIM key, moving
  the Let's Encrypt account away, dropping Roundcube's CardDAV tables and
  all webmail sessions). Setup now also records the number of the last
  migration that ran in `/var/lib/mailinabox/storage-migration` (root's own,
  with the path of the `$STORAGE_ROOT` it belongs to) and stops before any
  migration when the file says less, with what to do; a missing file is
  taken from the record. A higher number counts as before, but only up to
  the newest migration of the running version: above it setup stops too,
  unless the record has the same number (a downgrade), so a wrong number
  cannot skip the migrations of later releases. A first version took such
  a number and recorded the newest migration, and the next release's
  migrations were then skipped and recorded as run (found in the review). The
  file itself stays where and as it was, so it
  still goes into backups and to a new box. New offline test
  `tests/fork/migration-record.py`.

* **Backup and DNS settings only from directories of root's own (B212)**\
  The nightly backup, the control panel and the DNS update read
  `backup/custom.yaml`, `backup/secret_key.txt` and `dns/custom.yaml`
  below `$STORAGE_ROOT`, and write the two `custom.yaml`, only through the
  checked directory (a directory of root's own, not a symbolic link, not
  writable by group or others, opened once), as the fork's tools do since
  B117 and as `settings.yaml` is written since B87. Upstream read them by
  path and wrote `custom.yaml` with `open(..., "w")` as root: the storage
  user, which owns `$STORAGE_ROOT`, could replace `backup/` and have the
  backups of `$STORAGE_ROOT` go to a server of its own with a passphrase it
  knows, or put records of its own into the DNS zones. When such a
  directory or file cannot be trusted, no backup is made and the DNS zones
  are not rebuilt (the old ones stay), with the reason (for the backup in
  the nightly mail, for both in the status checks); the web configuration
  and the TLS certificates go on without the custom DNS records. `backup/custom.yaml` is
  now written with mode 0600 (it can hold the target's credentials). New
  offline test `tests/fork/storage-dirs.py`.

* **Status checks read the DNSSEC key only through a checked dns/ (B183)**\
  The DNSSEC check of the status checks read `dns/dnssec/<algorithm>.conf`
  and the KSK's `.key` file by path for the public key that it shows with
  the DS records to set. With a `dns/` of the storage user's own in place
  of the box's (B212), System Status answered HTTP 500 and the status
  checks ended with a traceback, also in the nightly status mail, and with
  a `dnssec/` of its own the key shown came from its files. The key is now
  read only through the checked `dns/` and `dnssec/` (root's own, not
  writable by others, regular files of root's); when that fails, the DS
  records to set are shown without the key, with the reason, and the other
  checks go on. New cases in `tests/fork/storage-dirs.py` and
  `tests/fork/status-dns.py`.

* **Zone signing reads the DNSSEC keys only through a checked dns/ (B191)**\
  The DNS update (and its daily run that signs the zones again) read the
  `.conf` files in `dns/dnssec/` and the key files they name by path, as
  root, and wrote the patched copies to its temporary directory under the
  names from the `.conf` without checking them. The storage user could put
  a `dns/` of its own in place of the box's (B212), even while the update
  ran, whose `.conf` names a key with `../` in its name: root then copied
  a file of the storage user's to a place of its choice outside the
  temporary directory (for example a configuration directory that a root
  job reads), and signed the zones with its keys. The `.conf` files and
  the keys are now read only through the checked `dns/` and `dnssec/`
  (root's own, not writable by others, regular files of root's), a key
  name must be a plain file name (`K` and letters, digits, `._+-`), and
  the copies are new files created in the temporary directory only. When
  that fails the DNS update stops with the reason and the zones stay as
  they are. The keys' hash in the zone files is unchanged, so no zone is
  signed again for this update. New cases in `tests/fork/storage-dirs.py`.

* **Nextcloud takes X-Forwarded-For only from nginx's own proxy (B213)**\
  Nextcloud takes the client's address from `X-Forwarded-For` on every
  connection from 127.0.0.1 (`trusted_proxies`, B121), so any local account
  or service could make it log a failed login under another address, which
  the `miab-owncloud` jail then banned. nginx's proxy of `/caldav`,
  `/carddav` and `/webdav` now proves itself to `/cloud` with a secret
  header (from `/etc/nginx/miab-nextcloud-proxy.conf`, root's only,
  made once by setup and kept), and nginx passes `X-Forwarded-For` to
  Nextcloud's PHP only with that secret; PHP never sees the secret. Until
  setup has made the file (a setup run that stopped early), nginx's
  configuration still loads, and the proxy's clients are seen as
  127.0.0.1. Clients
  on the Internet keep their own address through the proxy (throttle and
  jail as before), Z-Push stays 127.0.0.1, and another local request is
  logged as 127.0.0.1, which fail2ban ignores. A downgrade to
  v78-r2604.4 leaves the file unused. New smoke check
  `nextcloud-forwarded-for-local`.

### Upgrade note

* **User database root's only; webmail password changes via the daemon (B210)**\
  Setup gives `$STORAGE_ROOT/mail` to root:root 755 and `users.sqlite` to
  root:root 0600 (through descriptors, and only when root owns them
  already: otherwise setup stops before it changes anything, naming
  them with "not taken over"; check such a
  directory and give it to root with `chown root:root`), and switches
  Roundcube's password
  plugin to the fork's driver. Mail is not interrupted: Dovecot and Postfix
  keep their open database, and new lookups open it as root. Between
  setup's Roundcube step and the restart of the management daemon a few
  minutes later, a password change in webmail fails with "Could not save
  new password. Connection error." (try again after the update). Webmail
  cannot change the password of an account with two-factor authentication
  (the daemon would need its code): an administrator changes it in the
  control panel (Mail & Users > Users). A user who is not an administrator
  and has turned on two-factor authentication can no longer change their
  own password; the old SQL driver did not check it. Scripts of your own that read
  `users.sqlite` as another account than root no longer can. A backup of
  this version restored on an older version, or a downgrade to
  v78-r2604.4, works: its setup gives the directory and the database back
  to www-data and the plugin back to its SQL driver (the driver file
  `plugins/password/drivers/mailinabox.php` stays, unused). An older backup
  restored on this version gets the new owner and modes at the next setup
  run.

* **Backups stop if backup/ is not root's own (B212)**\
  If `$STORAGE_ROOT/backup` or `$STORAGE_ROOT/dns` is not a directory of
  root's own (owner root, mode 755 as setup makes them), or `custom.yaml`
  or `secret_key.txt` in it is not a regular file of root's, backups (and
  DNS updates) stop with the reason. Put them right with `chown root:root`
  and `chmod 755` (and check the files in them).

* **A proxy of your own to the box's /cloud is seen as 127.0.0.1 (B213)**\
  A proxy that you set up in `www/custom.yaml` to the box's own `/cloud`
  (`https://127.0.0.1/cloud/...`) no longer passes the client's address to
  Nextcloud: Nextcloud sees 127.0.0.1, which is on its brute-force bypass
  list, so its clients skip Nextcloud's throttle and the `miab-owncloud`
  jail, and Dovecot answers the IMAP logins with which Nextcloud checks
  their passwords at once (B126): nothing slows down password guesses
  through such a proxy. Do not use one on a box reachable from the
  Internet. The box's own paths (`/caldav`, `/carddav`, `/webdav`, `/cloud`)
  are not affected.

* **Restoring an older backup on the same box: remove the migration record (B211)**\
  The first setup run of this version records the box's migration number
  in `/var/lib/mailinabox/storage-migration`. If you later restore a backup
  of `$STORAGE_ROOT` made before a migration of a newer release, setup stops
  ("... says #N, but this box has run the data migrations up to #M"):
  remove that file and run setup again, so that the backup's migrations
  run. A restore on a new box is not affected (a new box has no record),
  and `tools/migrate-to-2604.sh` removes the record before each of its
  setup runs, as the copy of the old box decides there (also after its
  rehearsal or a rollback on the same machine). A downgrade to
  v78-r2604.4 ignores the record and leaves the number as it is, so the
  way back up works too.

* **The update removes all but the three newest Nextcloud backup copies**\
  The first setup run of this release removes every copy in
  `$STORAGE_ROOT/owncloud-backup` but the three newest and those of the
  last 14 days. To keep an older
  one, move it out of that directory before the update (to a name that is
  not a date and time, or elsewhere).
* **The update restarts Dovecot, reloads PHP-FPM once and restarts a few services**\
  The first setup run of this release restarts Dovecot (its new passdbs
  of the account lock, B126, B223: the open IMAP sessions end, and their
  clients log in again; a login in the few seconds of the restart fails,
  and Postfix's submission ports may not answer for up to 10 s, B224) and
  reloads PHP-FPM (its new `process_control_timeout`, B122: a Ping
  that is open then gets HTTP 502 after 5 s), and restarts OpenDKIM,
  OpenDMARC, spampd, postgrey, named, systemd-resolved, munin-node and the
  management daemon once more, as it has no checksums of them yet. Later
  runs leave them alone unless their configuration changes or they were
  started since by something else; the first run after a reboot restarts
  them (PHP-FPM: reloads it) once more.

## v78-r2604.4 (2026-11-19)

A small release: the control panel's intrusion protection
(System > Intrusion Protection) shows why an address is banned, shows and
resets Nextcloud's own login throttle (which answers HTTP 429 to a whole
network after failed logins, e.g. of one calendar app with an old
password) and lets the administrator set its threshold and the thresholds
of Mail-in-a-Box's jails. Setup updates the pinned Nextcloud apps also when
Nextcloud itself stays (B176, calendar 6.6.6) and keeps its backup copies
root-only (B177). It also notes Ubuntu's nginx security update for two
HTTP/2 vulnerabilities. Tested by a fresh install (T1) and an update of a
copy of a production box from v78-r2604.3 (T5b), see TESTING-fork.md.

### New

* **Intrusion Protection shows why an address is banned**\
  Intrusion protection (System > Intrusion Protection) shows why an
  address is banned: for each ban the failures and the log lines that
  fail2ban kept for it (up to 10, from its database), the accounts of the
  box they name, and the jail's rule (what it watches, its thresholds, the
  ports it blocks). A user name that is no account of the box is replaced
  by "[unknown name]", as the failed-login report leaves such names out (it
  is whatever the client sent, a password typed into the wrong field too); a
  ban without lines was set by hand. The name is replaced wherever the line
  repeats it (Z-Push's brackets, also with spaces as sshd, nginx and
  Postfix log them); a line of Nextcloud's log shows its URL only for an
  account, and one that is not valid JSON no more than its login message.
  `GET /admin/system/fail2ban` gives the same as `reason` of each ban and
  `jail_info`.
* **Nextcloud's login throttle in the control panel**\
  Nextcloud's own brute-force throttle in the control panel. Apart from
  fail2ban, Nextcloud counts failed logins per address (IPv4) or IPv6
  network (/56 by default): after failures within 12 hours it delays every
  login from there,
  up to 25 seconds, and after more than 10 failures within 30 minutes it
  refuses them with HTTP 429, also for the accounts with the right password
  behind that address, so one calendar or contacts app with an old password
  keeps the other devices of its network from syncing. Nothing showed this
  so far. The new section "Nextcloud throttle" lists the counted addresses
  (failures in 12 hours and in 30 minutes, the accounts of the box they
  tried, the delay, whether they are blocked) and resets an address (it
  deletes the failures of its network, also with the throttle off and for
  an address on the bypass list, where Nextcloud's own reset does nothing);
  a banned address that Nextcloud throttles too gets a hint with a button.
  New settings: `nc_protection` (Nextcloud's throttle on, the default;
  turning it off asks first and deletes the failures counted so far, which
  Nextcloud would otherwise go on applying for up to 12 hours; failures
  that logins already waiting in the throttle add afterwards are stale too:
  setup and the daily status checks delete them, and the control panel
  shows them with a button),
  `nc_max_attempts` (failures before the
  maximum delay and the block, 10 by default, 3 to 1000) and `nc_allowlist`
  (off by default: the allowlist goes on Nextcloud's bypass list too; the
  entries it adds are recorded under `nextcloud_bypass` in settings.yaml and
  removed again when they leave the allowlist, `127.0.0.1/32` of B121 and
  entries made in Nextcloud stay). Setup and the control panel write the
  first two into Nextcloud's `config.php` only when they differ from
  Nextcloud's defaults, as www-data with the new
  `tools/nextcloud-bruteforce-config.php` (Nextcloud's own
  `occ config:system:set` refuses once setup has made the file read-only),
  and atomically as setup writes it (B124); the overview reads Nextcloud's
  database read-only as www-data, and a reset deletes there as www-data.
  For each of the two on its own, while the settings have no value of their
  own for it, a value set in `config.php` by hand is taken over instead of
  overwritten, as Nextcloud reads it (`0` and `false` are off, the string
  `'false'` is on): setup stores it at once, the control panel shows it and
  stores it with the next save. The overview names only accounts of the
  box without giving their list to www-data: the reader returns the login
  names as salted hashes (a new salt each time), which root compares with
  the hashes of its accounts. New API: `GET
  /admin/system/nextcloud-throttle`, `POST
  /admin/system/nextcloud-throttle/reset`; `management/nextcloud_throttle.py
  --setup | --status | --reset <ip>`; setup/start.sh applies the settings
  after fail2ban's (never stopping setup). The status checks warn when
  Nextcloud's settings do not match.
* **Thresholds of the box's fail2ban jails can be changed**\
  The thresholds of Mail-in-a-Box's own jails can be changed (setting
  `jails`; the control panel shows a table with failures, window and ban
  time): `dovecot`, `miab-management`, `miab-munin`, `miab-owncloud`,
  `miab-postfix465`, `miab-postfix587`, `miab-roundcube`, `miab-zpush`,
  `postfix-sasl` and `sshd`, not recidive. Only the values that differ from
  `conf/fail2ban/jails.conf` are stored and written into
  `mailinabox_adaptive.conf`; fail2ban is reloaded, and `fail2ban-client
  -t` checks the configuration first as for the other settings.
* **Failed-login report also reads Nextcloud's log**\
  The failed-login report and its status check read Nextcloud's log too
  (one line per failed login of Nextcloud, CalDAV, CardDAV and WebDAV, with
  the address that the miab-owncloud jail takes), so accounts and addresses
  that fail only there show up.
* **New smoke checks for jail values, ban reasons and Nextcloud throttle**\
  New smoke checks (group admin): `admin-fail2ban-jail-values`,
  `admin-fail2ban-ban-reason`, `admin-nextcloud-throttle`,
  `admin-nextcloud-throttle-settings`; the opt-in group fail2ban checks the
  reason of its real ban. Every change of the settings writes a line to the
  management daemon's log, as an unban and a reset do.
* **Log audit allow list accepts new control panel audit lines**\
  Tests: `tests/fork/log-audit-allow.txt` accepts these audit lines of the
  control panel (settings saved or reset, unbans, resets of Nextcloud's
  throttle), the failed Nextcloud logins of the new throttle checks, and
  two lines that bind and Postfix log once right after the management
  daemon has flushed bind's cache for a DNS change (as upstream); the
  update test logged them as unknown.

### Fixed

* **New Nextcloud app pins reach existing boxes (B176)**\
  A new version of the Nextcloud apps contacts, calendar or user_external
  that setup pins reaches an existing box now also when Nextcloud itself
  stays: setup compares the installed versions with the pins, downloads and
  checks every new release first (a failed download changes nothing),
  stops PHP-FPM, backs up the database (a consistent copy with `VACUUM
  INTO`, as www-data), config.php and the old apps to
  `$STORAGE_ROOT/owncloud-backup`, swaps the apps without using a name of
  its own in Nextcloud's directory (which www-data owns) and runs `occ
  upgrade`. Before, a new pin took effect only with the next Nextcloud
  version, and a fresh install and an updated box differed (B176).
  Calendar 6.6.5 to 6.6.6. New smoke check `admin-nextcloud-app-versions`.
* **Nextcloud backup copies are root-only now (B177)**\
  The copies that setup keeps in `$STORAGE_ROOT/owncloud-backup` before an
  update of Nextcloud or of its apps (the database with every user's
  calendars and contacts, Nextcloud's code) were readable by every local
  account (directory 0755, database copies 0644). Setup now keeps the
  directory at 0700 on every run, which closes the copies of earlier
  updates too; if something else than a directory is in its place (a
  symbolic link, a file), setup stops before a backup instead of writing
  through it. New smoke check `admin-nextcloud-backup-private` (B177).

### Security

* **nginx security update fixes two HTTP/2 CVEs**\
  nginx: Ubuntu's security update 1.28.3-2ubuntu1.13 fixes CVE-2026-123633
  (use-after-free in HTTP/2 when proxying, with few free
  `worker_connections`) and CVE-2026-123007 (heap buffer overflow in the
  HTTP/2 flow control). The box serves HTTPS with HTTP/2 and proxies
  `/admin`, `/caldav`, `/carddav` and `/webdav`. No change of the fork's
  code: setup installs the update with the other package updates
  (setup/system.sh), and unattended-upgrades does within a day.

### Upgrade note

* **Install the nginx update now, independent of this release**\
  Install the nginx update now, independent of this release:
  `sudo apt update && sudo apt upgrade` (nginx restarts for a second). The
  version must be 1.28.3-2ubuntu1.13 or later (`dpkg-query -W nginx`).
* **Update installs calendar 6.6.6; Nextcloud answers 503 briefly**\
  The update installs calendar 6.6.6 and runs `occ upgrade`: Nextcloud
  answers 503 for a few seconds.
* **New settings start with present values; reset throttled addresses**\
  The new settings start with Nextcloud's and fail2ban's present values, so
  nothing changes on its own. A device with an old password that keeps a
  network throttled shows up under System > Intrusion Protection, "Nextcloud
  throttle": fix its password, then reset the address.

## v78-r2604.3 (2026-11-16)

A small release: Postfix offers the post-quantum key exchange
X25519MLKEM768 on ports 25, 465 and 587 and to other mail servers, as
nginx and Dovecot already did, and a user whose password has an umlaut or
another character beyond ASCII can log in to the control panel again
(B175). Tested by a fresh install (T1) and an update of a copy of a
production box from v78-r2604.2 (T5b); see TESTING-fork.md,
"v78-r2604.3".

### Changed

* **Postfix offers post-quantum key exchange**\
  Post-quantum key exchange for mail: Postfix offers the hybrid group
  X25519MLKEM768 (ML-KEM-768 with X25519) on ports 25, 465 and 587, and its
  SMTP client offers it to other mail servers. setup/mail-postfix.sh sets
  `tls_eecdh_auto_curves` and `tls_ffdhe_auto_groups` empty, so Postfix
  uses OpenSSL's default groups, as postconf(5) says for post-quantum
  cryptography; with OpenSSL 3.5 these are X25519MLKEM768, X25519, P-256,
  X448, P-384, P-521, ffdhe2048 and ffdhe3072. Postfix's own lists
  (`postconf -d`) have no post-quantum group, so mail was the only TLS
  service of the box without it: nginx (443) and Dovecot (993, 995, 4190)
  use OpenSSL's defaults and already negotiate X25519MLKEM768. Mail that is
  recorded today cannot be decrypted later with a quantum computer, where
  both sides offer the group ("harvest now, decrypt later").
  * Clients and servers without the group get X25519 or P-256 as before;
    TLS 1.2 and the cipher lists do not change. The SMTP client sends key
    shares for X25519MLKEM768 and X25519, so a server without the new group
    answers without an extra round trip; its first TLS message is about
    1.2 kB larger.
  * Not changed: the certificate (RSA 2048), DKIM (RSA 2048) and DNSSEC
    (ECDSA P-256, RSA/SHA-256) keys. They sign; a quantum computer would
    have to break them at the time of an attack, and there are no
    post-quantum certificates, DKIM or DNSSEC algorithms in use yet.
    Larger RSA keys or DH parameters (4096 bit) do not help against a
    quantum computer.
  * New smoke check `tls-key-exchange`: X25519MLKEM768, X25519 only, P-256
    only and TLS 1.2 on ports 443, 993, 465, 587 and 25.

### Fixed

* **Control panel login works with non-ASCII passwords (B175)**\
  A user whose password has an umlaut or another character beyond ASCII
  can log in to the control panel again. The management daemon read the
  user name and password of the Authorization header as ASCII and
  answered "Login failed: 'ascii' codec can't decode byte ...", although
  the panel had set that password and mail took it. The daemon now reads
  them as UTF-8, else as Latin-1 (what the panel's pages up to
  v78-r2604.2 sent, 'ü' as one byte), and the panel sends UTF-8, so that
  characters beyond Latin-1 such as '€' arrive too. New smoke check
  `admin-login-non-ascii`: a test user with 'ü', 'ß' and later '€' in its
  password logs in with the header in UTF-8 and in Latin-1, to the panel
  and to IMAP (B175). It and `admin-api-tmp-user-alias` remove their test
  user's archived mailbox also when they fail.

### Upgrade note

* **How to update boxes from v78-r2604.2**\
  Boxes on v78-r2604.2 are updated with the bootstrap command of "Updating
  the fork" in README-fork.md,
  `sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/setup/bootstrap.sh)"`,
  with `tools/update-check.sh before` and `backup` before it and `after`
  and `mailcheck` after it, all from `/root/mailinabox/tools/`, as for
  v78-r2604.2. `git -C /root/mailinabox status --short` must print nothing
  first. `after` has no list of changes for this release
  (`tools/expected-changes/v78-r2604.3.txt` names none): the two Postfix
  parameters are not in its record (see Planned), the smoke check
  `tls-key-exchange` shows them. Boxes on v78-r2604.1 or earlier take the
  steps of the upgrade notes in between first.
* **Update restarts Postfix and the management daemon**\
  Setup restarts Postfix once for its new TLS groups. Mail clients and
  servers without X25519MLKEM768 connect as before. The update restarts
  the management daemon: control panel sessions end, log in again.

## v78-r2604.2 (2026-11-15)

A bug-fix release: the fixes of a bug scan of v78-r2604.1
(B145-B173) and of its test runs (B174), and upstream's fix of the IPv6
Spamhaus check (#2617, B144), with the security releases Roundcube 1.7.6
and CardDAV plugin 5.1.5 and Nextcloud 34.0.6. A fresh install with
`PRIMARY_HOSTNAME` in the environment no longer stops without a word at
its network checks (B145), and an interactive install runs them as well
(B146). Code that runs as www-data can no longer become root at the next
setup run (B147). A setup run or a backup that fails no longer leaves
PHP-FPM or mail stopped (B148, B149), setup runs no longer log out the
webmail users (B172) and stop when the daemon's DNS or web update fails
(B159), moving mail into or out of Spam no longer creates a folder
"spamassassin" (B155), and nc's "Connection to ... succeeded!" lines are
gone from setup's output (B174). The status checks no longer take a
failed DNS lookup for an answer (B150). The in-place tool keeps its
options across reboots (B153) and gets fixes for SSH, its checks and the
release tag (B151, B156, B160-B162, B168, B169, the last also in the
migration tool); the migration tool checks every value of the old box
before it uses it (B154) and follows no link where it writes as root
(B166), with fixes for a symbolic link as `$STORAGE_ROOT`, folders named
`.rsync-partial`, Spamhaus and IPv6 addresses (B163-B165, B167).
Tested by a fresh install with the network checks (T1, T1n), an update
of a copy of a production box from v78-r2604.1 (T5b), and a migration
and an in-place upgrade from upstream v78 on Ubuntu 22.04 (T2, T4); see
TESTING-fork.md, "v78-r2604.2".

### Fixed

* **Fresh install no longer stops silently at the network checks (B145)**\
  A fresh install with `PRIMARY_HOSTNAME` in the environment no longer
  stops without a message at the network checks when Spamhaus answers that
  the hostname or the address is not listed, which is the normal answer:
  `host` exits 1 for it, and setup's strict mode ended the run there. A
  lookup that fails (SERVFAIL, REFUSED, a timeout) is now shown as "Could
  not check whether ... is listed ...", and setup goes on, as for
  Spamhaus' refusal of a public resolver; a listing still stops setup
  (B145).
* **Interactive fresh install runs the network checks (B146)**\
  A fresh install through the dialogs now runs the network checks too
  (the Spamhaus lists and outgoing port 25): the test that was meant to
  skip existing installs also skipped every interactive first install.
  Existing installs, the in-place upgrade and the migration still skip
  them (B146).
* **Setup no longer follows symbolic links planted by www-data (B147)**\
  Setup no longer runs Nextcloud's config.php (a file of www-data's) as
  PHP as root to read the Nextcloud version, and no longer changes owner
  and mode, writes, creates or moves files by path where www-data or the
  storage user could have put a symbolic link: `$STORAGE_ROOT/mail`,
  `users.sqlite` (also when setup creates it), `roundcube.sqlite`,
  `mailinabox.version` (start.sh and setup/migrate.py), the postgrey, DKIM
  and SpamAssassin directories (and the first move of postgrey's
  database), Nextcloud's first config.php and autoconfig.php, and the
  default homepage in `$STORAGE_ROOT/www`. Code that ran as www-data (a
  hole in a web app) could become root at the next setup run. Roundcube's
  database update and Nextcloud's database fix-up run as www-data, and
  Roundcube's CardDAV plugin belongs to root and is read-only for www-data
  (upstream let www-data change its code). The backup before a Nextcloud
  upgrade takes only regular files, and tools/owncloud-restore.sh refuses
  a backup whose files are links, reads the backup's version without
  running it and copies the backup without writing through a link. Setup
  checks these paths when it starts, before it changes anything, and stops
  there with a list of what to fix (B147).
* **Setup installs only the deb.sury.org key file (B158)**\
  Setup installs only the checked key file of deb.sury.org, not the
  keyring package with its maintainer scripts; the package that earlier
  versions installed is removed, the key stays at the same path (B158).
* **Failed setup run restarts PHP-FPM (B149)**\
  A setup run that ends with an error after the Nextcloud upgrade had
  stopped PHP-FPM (a failed download, an `occ` step, the Z-Push download)
  starts PHP-FPM again, so webmail, Nextcloud and ActiveSync no longer
  answer 502 until a later run. A successful run still restarts PHP-FPM
  once (B149).
* **Nightly backup restarts mail services after a failure (B148)**\
  The nightly backup starts Postfix, Dovecot, PHP-FPM and postgrey again
  also when the `before-backup` script fails or one of the services does
  not stop. Before, mail stayed down until someone started them, and the
  mail about it could not be sent (B148).
* **Setup runs no longer log out webmail users (B172)**\
  Setup runs no longer log out all webmail users: setup keeps Roundcube's
  `des_key`, with which Roundcube encrypts the password in each session
  and its "remember me" logins, instead of writing a new one each time
  (B172).
* **No more phantom "spamassassin" folder in mailboxes (B155)**\
  Moving a message into or out of Spam no longer creates a folder
  "spamassassin" (sa-learn's state directory, which it made in the
  Maildir); the learning was not affected. Setup removes these folders,
  through Dovecot, when they hold no messages and nothing but Dovecot's
  own files and were not created as real folders; one with messages or
  other files is kept, with a note in setup's output (B155).
* **Roundcube update keeps configuration when a download fails (B157)**\
  A Roundcube update no longer leaves webmail without its configuration
  and plugins when a download fails: the new release is put together with
  its plugins and configuration next to the installed one and replaces it
  only then. The control panel's jQuery and Bootstrap are replaced the
  same way (B157).
* **Setup output has no "Connection to ... succeeded!" lines (B174)**\
  Setup's output no longer has "Connection to ... succeeded!" lines from
  `nc` (the port 25 check of a fresh install and the wait for the
  management daemon); only nc's exit code is used, as before (B174).
* **Setup stops when the DNS or web update fails (B159)**\
  Setup stops with a clear message when the management daemon answers the
  DNS or web update with an error (HTTP 500, 401) or cannot be reached.
  Before, setup printed the daemon's answer and went on to "Your
  Mail-in-a-Box is running" with the old DNS zones or nginx configuration
  (or, when the daemon could not be reached, stopped without a word).
  `tools/dns_update` and `tools/web_update` now exit with an error in that
  case, which the daily DNSSEC job's mail shows as well (B159).
* **Spamhaus ZEN check uses the correct IPv6 name (B144)**\
  The status checks look up the box's IPv6 address in Spamhaus ZEN under
  the right name, its 32 nibbles in reverse order as in ip6.arpa. Before,
  they reversed the eight 16-bit groups, a name that never exists, so the
  check said "IPv6 address is not blacklisted" for any address, also a
  listed one (B144; the fix of upstream #2617 by N9ZL).
* **Status checks no longer treat a failed DNS lookup as an answer (B150)**\
  The status checks no longer take a failed DNS lookup for an answer. When
  the resolver answers SERVFAIL or REFUSED (or no server can be reached),
  the Spamhaus ZEN and DBL checks now warn that they could not check,
  instead of "not blacklisted"; a timed-out or failed MX lookup is a "could
  not check" warning instead of "no MX record", which was OK on the box's
  own name and, on other domains, OK when both A lookups had timed out; the
  DANE TLSA check warns that it could not check instead of calling the
  record "not correct, it is '[timeout]'"; and a custom secondary
  nameserver is no longer reported as having a "consistent SOA record"
  when neither SOA lookup worked (B150).
* **Version check no longer aborts the status checks (B170)**\
  The status checks with the version check on (privacy setting off) no
  longer end as a whole when the connection breaks while the latest version
  is read (a reset, a TLS error, a cut answer); the check says that the
  latest version could not be determined, and the API call
  `/system/latest-upstream-version` answers 503 instead of 500 (B170).
* **Control panel dialog messages are shown as text (B171)**\
  Messages in the control panel's dialogs are shown as text: a message
  given as a string was inserted as HTML because the function tested a
  name that it does not have. The random password of the Users page and
  the answer of a reboot still show as before. Short messages now appear
  in the small dialog, as upstream intended (B171).
* **update-check.sh after no longer says OK after a crash (B152)**\
  `tools/update-check.sh after` no longer says "RESULT: OK" when
  `status_checks.py` crashed or hit its time limit: such a run adds the line
  "✖ status checks did not finish (exit code N)" to `status.txt`, which is
  always UNEXPECTED, and the checks missing after the crash are no longer
  counted as errors and warnings that are gone. The summary of the state
  names it (B152).
* **PHP 8.5 for Nextcloud tools (B173)**\
  `tools/owncloud-unlockadmin.sh` runs Nextcloud's `occ` with PHP 8.5, the
  version Mail-in-a-Box installs, and `tools/update-check.sh` records
  Nextcloud's status with the PHP version of the box's checkout, not with
  whatever `php` points to (B173).
* **In-place upgrade recognises a refused release upgrade (B151)**\
  The in-place upgrade (`tools/upgrade-in-place-to-2604.sh`) recognises a
  release upgrade that do-release-upgrade refused before it changed
  anything. Before, it said that the machine "still runs Ubuntu 22.04 ...
  or restore from the backups", and `--rollback` refused with mail offline,
  because its check of the apt sources failed whenever one of the source
  file patterns matched no file (every 22.04 box has no `*.sources`) (B151).
* **In-place upgrade keeps environment options across reboots (B153)**\
  The in-place upgrade keeps the options given in the environment across
  its reboots. Before, the run after the first reboot, which is the one
  that runs setup on a box from 22.04 or 24.04, had only `TAG` and
  `SOURCE`: `FTS=off`, `NEXTCLOUD_SHARE_SCOPE=all` and `FAVICON=off` were
  ignored and setup wrote the defaults to `/etc/mailinabox.conf`, and the
  fallback SSH server of the second release upgrade ignored
  `UPGRADE_SSH_FALLBACK_USERS`. `PROBE_ADDRESS` (the probe address of
  `update-check.sh mailcheck`, which setup keeps in `/etc/mailinabox.conf`)
  and `DISABLE_FIREWALL=1` now reach setup too, in the tool's tmux session
  and after a reboot; before, setup installed and enabled ufw on such a box.
  `tools/migrate-to-2604.sh` passes these two to setup in its tmux session
  as well, which did not get them while another tmux session was open
  (B153).
* **In-place upgrade no longer stops at "sshd -t fails" (B156)**\
  The in-place upgrade no longer stops with "sshd -t fails ... Not
  rebooting" in a boot in which nobody has logged in over SSH yet (sshd is
  socket activated on 24.04 and 26.04, and `/run/sshd` is missing until
  its first connection); it creates the directory first, as it already did
  for its fallback SSH server (B156).
* **In-place upgrade package checks now stop it correctly (B160)**\
  The in-place upgrade's checks whether switching packages from
  ppa:ondrej back to Ubuntu's versions, or installing tmux for its own
  session, would remove other packages work: before, they never stopped
  it, because `grep -q` at the end of the pipe made apt-get fail. The same
  trap could leave the fallback SSH server's port closed in ufw on a box
  with a long rule list, and move `/etc/php/8.5` or `8.2` aside in the
  cleanup before setup although packages of that version were installed
  (B160).
* **In-place upgrade --redo-from and --finish report states correctly (B161)**\
  After a `--redo-from` that fails, the in-place upgrade no longer says
  that mail runs again while setup is pending, and `--finish` no longer
  accepts the final check from before the redo: it needs a check that has
  run since, and setup done (B161).
* **In-place upgrade handles sshd on a port other than 22 (B162)**\
  With sshd on another port than 22, the in-place upgrade's SSH watcher
  and its "is SSH back?" check use sshd's ports (from `sshd -T`). Before,
  it reported SSH down for the whole release upgrade and left the fallback
  SSH server and its ufw rule running until the next reboot. The help and
  the plan of `--check` no longer say that SSH is on port 22 (B162).
* **In-place upgrade offsite copy check ignores permissions (B168)**\
  The in-place upgrade's offsite copy of the system archive is compared by
  content and times only, as it is copied. Before, a backup account whose
  umask gives new files other permissions (e.g. 077) made the snapshot
  phase stop with "The copy ... differs" for a correct copy (B168).
* **In-place upgrade uses main only if the tag is unpublished (B169)**\
  The in-place upgrade uses the branch main instead of the release tag
  only when the tag is not published in the repository (git ls-remote).
  Before, any failure to fetch the tag, such as a network error, made setup
  run from main with the note "The release tag ... is not published yet";
  now such a failure stops with git's message, and the command can be run
  again. `tools/migrate-to-2604.sh` does the same: before, a failure to
  download the tag, or to check it out in a clone with local changes, ran
  the migration and setup from main (B169).
* **Migration tool no longer runs values from the old box as code (B154)**\
  `tools/migrate-to-2604.sh` no longer runs values that the old box reports
  as bash code on the new machine, and writes only plain values into the
  new `/etc/mailinabox.conf`. An old box that was broken into (often the
  reason for a move) could run commands as root on the new machine,
  already with `--check` (its clock and the size of its data went into bash
  arithmetic), and setup sourced its storage user, MTA-STS mode and
  hostname from the new `/etc/mailinabox.conf`. Every value of the old box
  is now checked against the form that Mail-in-a-Box gives, right after it
  is read, and the tool stops at a setting of another form, naming it
  (correct it on the old box); values that are only shown get "?" for
  control characters. The hostname (also one taken from a restored TLS
  certificate) and the addresses (also the answer of icanhazip.com and the
  options) are checked the same way, and `--storage-root` must be an
  absolute path of letters, digits and `. _ - /`. Command lines, unit
  names, settings and file names of the old box (and the command lines of
  other accounts' processes here) reach the terminal, the report of the
  old `/etc` and the saved Postfix queue listing with "?" for control
  characters, so that they cannot send escape sequences to the terminal
  (B154).
* **Migration tool follows a symlinked $STORAGE_ROOT (B163)**\
  `tools/migrate-to-2604.sh` measures and watches a `$STORAGE_ROOT` that is
  a symbolic link on the old box (for example to another volume) where it
  points. Before, it showed "Data to copy: 0" and checked no disk space
  (the copy failed hours later on a full disk), and before the final copy
  it did not wait for processes that still had files open there (B163).
* **Migration tool copies folders named .rsync-partial (B164)**\
  `tools/migrate-to-2604.sh` copies folders named `.rsync-partial`, such as
  an IMAP folder "rsync-partial" or such a folder in Nextcloud. rsync left
  them out without an error, because the tool used that name for
  interrupted files, and after a resumed copy the tool deleted every such
  folder on the new machine. The tool's own name for it is now
  `.migrate-to-2604-partial`, and the cleanup removes only root's
  directories of that name, without following a link put into the path
  (B164).
* **Migration tool says "could not check" when Spamhaus is unreachable (B165)**\
  `tools/migrate-to-2604.sh` says "could not check" when it cannot reach
  Spamhaus, instead of reporting the new IP address as not listed. It asks
  Spamhaus' test entries (127.0.0.2 and dbltest.com) first; only when they
  answer does no answer mean "not listed". The result for the hostname in
  Spamhaus' Domain Block List is shown as well (B165).
* **Migration tool follows no links where root writes (B166)**\
  `tools/migrate-to-2604.sh` follows no link where root writes into trees
  that another party shapes. It writes its marker in `$STORAGE_ROOT`
  through `tools/write_conf.py`; before, root wrote it by path, so an
  account that owns that directory during the migration could put a link
  there and have any file overwritten and set to mode 0600 at the next
  run. The greylisting exceptions are taken over from the old `/etc` only
  as a regular file reached without a link, and never with a wider mode (a
  link from the old box could put e.g. `/etc/shadow` of the new machine
  into a file readable by every account). The owner mapping puts
  setuid/setgid bits back through a descriptor of the same file. With
  `--from-backup`, `mailinabox.version`, `www/` and the dotfiles get their
  owner without following links, and the backup key goes only into a
  checked `backup/` directory of root's own (B166).
* **Migration tool --from takes an IPv6 address (B167)**\
  `tools/migrate-to-2604.sh --from` takes an IPv6 address, with or without
  brackets (`--from root@[2001:db8::1]`). Before, `--check` passed and the
  first copy failed, because rsync needs the address in brackets and ssh
  without them. `--check` now also runs rsync once (a listing of
  `$STORAGE_ROOT` on the old box) with the same target and remote command
  as the copy, so that a problem there shows up before the migration
  (B167).

### Changed

* **Roundcube 1.7.6 and CardDAV plugin 5.1.5**\
  Roundcube 1.7.5 → 1.7.6 (security release of 2026-11-09), SHA256
  `0168085bf0bfeeb5d4eca3b9730effbe610dbdb380a68567d292fec51f09db36`; its
  Elastic skin has the same favicon.ico as 1.7.5. Roundcube's CardDAV
  plugin (rcmcarddav) 5.1.4 → 5.1.5 (security release: photos that a
  contact's vCard only references by a URL are no longer downloaded by the
  server; its admin setting `download_photos` would turn that on again,
  and setup does not set it), SHA256
  `aea05586822848d9b2f2cdac6b59bdd500d3f93b1b0eeba0295a4aaeb335ad18`.
* **Nextcloud 34.0.6 with contacts 8.10.0 and calendar 6.6.5**\
  Nextcloud 34.0.5 → 34.0.6, SHA256
  `ec74a0cf6de20e2a234c5bde55e370e4a7f12b46a266ae3d33c8f3edc17b153e`, with
  the contacts app 8.9.2 → 8.10.0
  (`035d943115f129d20fbaba19b2124a0d2f65a59c35cabe142495bb6ae650d549`;
  its `appinfo/info.xml` accepts Nextcloud 33 to 36 and PHP 8.2 to 8.5)
  and the calendar app 6.6.4 → 6.6.5
  (`e3afbc2a10db87920f5347279423422411010550a809b2902c0e8cf2f2492107`;
  Nextcloud 32 to 35, PHP 8.1 to 8.5), for the fresh install and the final
  step of the upgrade chain (and the commented step to 34 for later). The
  steps to 27 … 33 and user_external 4.0.0 (still no release for
  Nextcloud 35) are unchanged. A box on 34.0.5 takes the upgrade at the
  update: its `occ upgrade` also updates the two apps. The hashes were
  checked against the publishers' digests (GitHub's asset digest,
  Nextcloud's `.sha256`).
* **update-check.sh after expects new Nextcloud version and warnings (B150, B144)**\
  `tools/update-check.sh after` expects the new Nextcloud version in
  `occ status` (`nextcloud.txt`: `version` and `versionstring`), and the
  status checks' new warnings where a DNS lookup of the box fails or times
  out ("Could not connect to zen.spamhaus.org" and "... dbl.spamhaus.org",
  "Could not check this domain's MX record", "Could not check the DANE
  TLSA record", and `[error]` where a check showed `[Not Set]`) (B150). A
  listing of the box's IPv6 address, which the status checks see from this
  release on (B144), stays UNEXPECTED. The other component updates and
  fixes change nothing in the recorded state.
* **write_conf.py --own, --own-tree and --check-own (B147)**\
  `tools/write_conf.py --own PATH USER GROUP MODE` changes the owner and
  mode of one file or directory through a descriptor and refuses a
  symbolic link, a file with more than one hard link or anything else;
  `--own-tree` takes optional modes for files and directories, and
  `--check-own PATH...` changes nothing and names each path that `--own`
  would refuse (setup's check at its start) (B147).
* **New tests for phantom folder and setup network checks (B155, B145)**\
  Tests: the smoke test's new check `imapsieve-no-phantom-folder` (group
  imapsieve) fails when alice, bob or carol has a folder "spamassassin"
  (B155). TESTING-fork.md has the scenario T1n: setup's network checks on
  the installed T1 box under setup's shell options, through its own
  resolver, which gives Spamhaus' "not listed"; no scenario ran that
  answer under setup before (B145). The log audit's list
  (`tests/fork/log-audit-allow.txt`) accepts the harmless lines that T4
  and T2 from upstream v78 showed: the boot messages of a virtual machine
  in other forms (a PCI hotplug slot with a hex digit, the kernel's time
  in 22.04's syslog, QEMU's interrupt overrides, the CPU bring-up lines,
  udev of 24.04), grub's os-prober note at prepare-release's kernel
  update, polkit's tmpfiles group and 22.04's ntp under its old AppArmor
  profile during the release upgrade, ntpsec trying the global IPv6
  address before it is usable, and ssh's note in the migration log that
  it recorded the old box's host key.
* **Docs: README names new versions and tool changes (B164, B167, B162)**\
  Docs: README.md and README-fork.md name the new component versions.
  README-fork.md (English and German): the migration tool's partial
  directory is `.migrate-to-2604-partial` (B164), `--from` takes an IPv6
  address and `--check` tries the copy's rsync once (B167), the in-place
  tool reports the SSH port of `sshd_config`, not always 22 (B162), and
  after a migration webmail users log in again because Roundcube on the new
  machine has a key of its own. "Updating the fork" says that setup stops
  at its start when a place it writes in `$STORAGE_ROOT` is a symbolic
  link (B147), and "Setup output" that the "Connection to ... succeeded!"
  line is gone (B174).

### Upgrade note

* **Updating from v78-r2604.1 to v78-r2604.2 (B152)**\
  Boxes on v78-r2604.1 are updated with the bootstrap command of "Updating
  the fork" in README-fork.md,
  `sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/setup/bootstrap.sh)"`,
  with `tools/update-check.sh before` and `backup` before it and `after`
  and `mailcheck` after it, all from `/root/mailinabox/tools/`, as for
  v78-r2604.1. `git -C /root/mailinabox status --short` must print nothing
  first. `after` judges the changes by `tools/expected-changes/any.txt` and
  `v78-r2604.2.txt`: Nextcloud's new version, and the new warnings of the
  status checks where a DNS lookup of the box fails (see below). When the
  status checks crash or time out, `after` now lists "✖ status checks did
  not finish (exit code N)" as UNEXPECTED; their output is in
  `after/status-full.txt` of the run's directory in `/root/update-check`
  (B152). Boxes on v78-r2604.0 or earlier take the steps of the upgrade
  notes in between first.
* **Nextcloud 34.0.6 upgrade restarts PHP-FPM briefly (B149)**\
  The update upgrades Nextcloud to 34.0.6 on every box. PHP-FPM is
  stopped while Nextcloud upgrades, so webmail, Nextcloud and ActiveSync
  answer 502 for that time (as at every Nextcloud update); if setup ends
  with an error, PHP-FPM is started again now (B149).
* **Webmail users stay logged in across setup runs (B172)**\
  Webmail users stay logged in across setup runs from now on, also across
  this update: the new setup takes the `des_key` from the installed
  Roundcube configuration, which the last run of the old setup wrote, and
  writes a new one only when there is none (B172). Up to v78-r2604.1 every
  setup run, and so every update, logged them out.
* **Setup refuses symbolic links and extra hard links in mail data (B147)**\
  Setup now stops at its start, before it changes anything ("Setup
  stopped before it changed anything ..."), when `$STORAGE_ROOT/mail`,
  `users.sqlite` or `roundcube/roundcube.sqlite` in it, or its postgrey,
  DKIM or SpamAssassin directory is a symbolic link, when one of the two
  databases has a second hard link, or when
  `$STORAGE_ROOT/mailinabox.version` is not a regular file. It lists them
  and says what to do: if you moved the mail store to another disk with a
  symbolic link, put the directory back or mount the disk at
  `$STORAGE_ROOT/mail` with a bind mount instead; remove the other name of
  a database with a second hard link (`find / -xdev -samefile FILE` shows
  it); then run setup again. `$STORAGE_ROOT` itself may still be a link in
  a directory of root's own (such as `/home/user-data`) (B147).
* **Setup removes sa-learn's "spamassassin" mail folders (B155)**\
  Setup removes the folders "spamassassin" that sa-learn created. It
  prints "Removed the state directory of sa-learn (the folder
  "spamassassin") from N mailboxes", and "Kept ..." with the reason for a
  folder that holds messages or other files: move the messages to another
  folder and run setup again (B155).
* **Package `debsuryorg-archive-keyring` removed, key file kept (B158)**\
  The package `debsuryorg-archive-keyring` is removed; the key file it
  installed stays at `/usr/share/keyrings/debsuryorg-archive-keyring.gpg`,
  now as a file of setup's (B158).
* **Roundcube shows no contact photos linked by URL**\
  Contacts whose vCard links to a photo by URL show no photo in
  Roundcube any more (CardDAV plugin 5.1.5); photos stored in the vCard
  itself are not affected.
* **Setup fails when the management daemon cannot update DNS or web (B159)**\
  Setup now ends with exit code 1 and "Setup stopped: the management
  daemon could not update ..." when the DNS or web update fails, after the
  daemon's answer. Mail and the web server keep running; fix the cause and
  run setup again (B159).
* **System Status may show new warnings for failed lookups (B150, B144)**\
  System Status may show new warnings: where the box's resolver fails or
  times out for a lookup, the checks now say that they could not check
  (Spamhaus ZEN and DBL, the MX record, the DANE TLSA record) instead of
  OK or a wrong error, and show `[error]` where they showed `[Not Set]`
  (B150). The box's IPv6 address is now really looked up in Spamhaus ZEN,
  so a listing missed so far shows up as an error (B144), which `after`
  lists as UNEXPECTED.
* **In-place and migration tools stop when the release tag is unreachable (B169)**\
  The in-place upgrade and the migration tool now stop when they cannot
  fetch their release tag (a network or GitHub error) instead of running
  setup from the branch main; run the command again when the source can be
  reached. They use main only when the repository answers that the tag is
  not published yet (B169).
* **Earlier in-place upgrades ignored settings given in the environment (B153)**\
  A box upgraded in place from 22.04 or 24.04 by an earlier version of the
  tool, with `FTS=off`, `NEXTCLOUD_SHARE_SCOPE=all`, `FAVICON=off` or
  `PROBE_ADDRESS=...` given in the environment, got the defaults in
  `/etc/mailinabox.conf` (B153): put the values there and run `sudo
  mailinabox`. With `DISABLE_FIREWALL=1` given, setup installed and
  enabled ufw: turn it off with `sudo ufw disable` if the box relies on
  another firewall (setup reads `DISABLE_FIREWALL` from its environment
  only).
* **Continuing a migration; unusual settings stop the migration tool (B154)**\
  A migration that is in progress can be continued with this release's
  `tools/migrate-to-2604.sh`. Folders `.rsync-partial` that an interrupted
  copy of an earlier version left on the new machine are removed by the
  next copy. An old box whose `/etc/mailinabox.conf` has a `STORAGE_ROOT`,
  `STORAGE_USER`, `PRIMARY_HOSTNAME` or `MTA_STS_MODE` of an unusual form
  (for example a hostname with an underscore or a trailing dot) now stops
  the tool with the name of the setting; correct it on the old box and run
  the command again (B154).

## v78-r2604.1 (2026-10-27)

A bug-fix release for the control panel's login. After a session had
ended (two days unused, a logout elsewhere, a changed password, or a
restart of the management daemon, which every update does), a reload still
showed the admin menus and the last panel from the credentials saved in the
browser (B141); the page now asks the box (the new `GET /admin/me`) before
it shows any menu or panel. "Remember me" had no effect, so every login
was kept in the browser beyond its tab (B142). `update-check.sh after`
accepts the new version line of an update to this or a later release
(B143), and the log audit accepts what a backup's stop of PHP-FPM logs.
This release had no full test matrix: the control panel changes were
tested in a browser test and the API smoke test on a test box (see
TESTING-fork.md, "v78-r2604.1").

### Fixed

* **Control panel shows no menus for ended sessions (B141)**\
  The control panel no longer shows its menus and the last panel for saved
  credentials whose session has ended. A session ends after two days
  without use, at a logout, when the password or MFA changes, and whenever
  the management daemon restarts (at every update). Before, a reload showed
  the admin menus and the last panel from the copy in the browser until an
  API call failed; the welcome and guide pages, which call no API, never
  noticed. On load the page now asks the box first (the new
  `GET /admin/me`, which takes a session key only, never a password) and
  shows no menu and no panel until the answer: for an ended session the
  login, and after it the requested panel; the menus follow the privileges
  in the box's answer, not the saved copy. When the box does not answer
  (its service stopped or restarting, or busy for more than 20 seconds
  with a long request of another tab), the login panel says so and the
  saved login is kept, so that a reload afterwards needs no password. A
  link or the back button while the box is being asked opens the panel of
  the new address with the answer, without the login form in between. A
  reload with an ended session is no longer logged as failed logins (each
  API call with the old key was one). Log out starts again with a fresh
  page (after at most five seconds, also when the box is busy; the login
  form is disabled until then), and a login of another user in the same
  tab after a session ended reloads the page and opens the welcome page,
  so that no panel shows data loaded for the user before. While the page
  loads, before its script has run, the menus no longer show for a moment
  either (on every load, also logged out): Bootstrap's style overrode the
  rule that hides them (B141).
* **Control panel's "Remember me" works (B142)**\
  "Remember me" on the control panel's login works: without it, the login
  is kept for the browser tab only (sessionStorage) and ends with it.
  Before, every login was saved in the browser's localStorage and was still
  there after the browser was closed and opened again, also when "Remember
  me" was not ticked (B142).
* **`update-check.sh after` no longer flags the new version line (B143)**\
  `tools/update-check.sh after` no longer lists the new version line as
  UNEXPECTED after an update to a release after v78-r2604.0: the rule of
  `tools/expected-changes/any.txt` for the version of `/root/mailinabox`
  named only v78-r2604.0 and its release candidates (B143).

### Changed

* **Tests: log audit accepts 502s while backup stops PHP-FPM**\
  Tests: the log audit accepts nginx's 502 for a request to Roundcube,
  Nextcloud or Z-Push while `management/backup.py` has PHP-FPM stopped
  for a backup (the socket is missing, or the request in progress is
  cut), in every phase, as backup.py logs no marks that would limit it to
  its run (with any host and the referrer that nginx adds for a browser's
  request, which also covers such lines at setup's PHP-FPM restart; also
  a line that the audit cuts at 400 characters, a long request with a
  referrer, as setup's rule for the same lines now does too); and
  the kernel's note that the free page reporting of a
  virtual machine took long on a busy host. A production box's
  `update-check.sh after` named them in the update to v78-r2604.0 (the
  backup step and the nightly backup stop PHP-FPM the same way).
* **Management daemon function `session_me` renamed**\
  Management daemon: the function behind `GET /admin/me` is named
  `session_me`, so it no longer reuses the module's name `me`, which holds
  the daemon's own path (no change in behavior; a later use of that path
  would have failed).
* **README-fork.md: stale local release tag blocks the update**\
  Docs: README-fork.md, "Updating the fork": a checkout whose current
  commit has a local tag with the name of the release being installed,
  but another commit than on GitHub (an old pre-release or a mirror's
  tag), is not updated: bootstrap.sh compares the name with `git
  describe`, fetches nothing, and setup runs on the old code and ends with
  exit code 0. How to check after the update (`git describe`, `git
  rev-parse HEAD` against `git ls-remote`) and the fix (`git tag -d`, then
  the bootstrap command again), in English and German.

### Upgrade note

* **Updating from v78-r2604.0 to this release (B143)**\
  Boxes on v78-r2604.0 are updated with the bootstrap command of "Updating
  the fork" in README-fork.md,
  `sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/setup/bootstrap.sh)"`,
  with `tools/update-check.sh before` and `backup` before it and `after`
  and `mailcheck` after it, all from `/root/mailinabox/tools/`. There is no
  file to put back unless you changed one by hand: `git -C
  /root/mailinabox status --short` must print nothing (`sudo git -C
  /root/mailinabox checkout -- FILE` puts a file back). `after` judges the
  changes by `tools/expected-changes/any.txt` and `v78-r2604.1.txt`; this
  release changes nothing in the recorded state but the version (B143).
  `sudo git -C /root/mailinabox describe --always` should print
  `v78-r2604.1` afterwards (see README-fork.md for a local tag of that name
  on another commit).
* **The update ends control panel sessions**\
  The update restarts the management daemon, which ends every control panel
  session: log in again. A page that is still open shows the login on its
  next reload ("Your session has ended") or at its next call to the box,
  not the admin menus. A login without "Remember me" is now kept for the
  browser tab only; tick it to stay logged in after the browser is closed
  (for at most two days without use, as before). API clients are not affected; the new
  `GET /admin/me` takes session keys only.
* **Updating from rc7 or earlier**\
  Boxes on rc7 or earlier are updated the same way, with the steps of the
  upgrade note of v78-r2604.0 first (for rc1 to rc6 also those of rc7).
  Read the upgrade notes of every release in between; `after` uses the
  lists of all of them.

## v78-r2604.0 (2026-10-27)

The first release of the fork after seven release candidates, from the
update of a production box from rc6 to rc7 and the analysis of its
ActiveSync errors. Setup disturbs the clients less: it reloads Dovecot,
Postfix and fail2ban instead of restarting them, Dovecot only on a change
(B122), and no longer leaves Dovecot without a passdb (B120), Nextcloud
without a readable config.php (B124) or the logins at the end of a run
without users.sqlite (B133) for a moment, and keeps cron off for its whole
run (B138); Nextcloud no longer throttles the box's own services (B121). A
fresh install no longer stops on Spamhaus' refusal of public resolvers
(B136), and the first certificates cover the box's own name (B140) and
publish the MTA-STS record (B139).
ActiveSync and Autodiscover get brute-force protection (B126); Z-Push syncs contacts whose card name has no `.vcf`
(B128), holds Pings of up to 59 minutes (B129) and no longer answers a
FolderSync without the mail folders when an IMAP session is cut (B137), and
the fork's changes
to it are one patch file, applied to a fresh copy (B126, B128); the
`/caldav`, `/carddav` and `/webdav` proxy passes the path as the client
sent it (B130). Security: `/etc/dovecot` belongs to root (B123), and the
control panel no longer writes password hashes into the journal or puts
passwords on a command line (B127). The backup page and the status checks
no longer hang or fail as a whole when a backup target does not answer
(B125, B132), and Roundcube's deny of its config directory is anchored
(B134).

### Fixed

* **ActiveSync and Autodiscover get brute-force protection (B126, B133)**\
  ActiveSync and Autodiscover have brute-force protection now: the new
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
* **Logins no longer fail briefly at the end of setup (B133)**\
  Logins no longer fail for a moment at the end of each setup run: setup
  rewrote the automatic aliases in `users.sqlite` every time (since rc4,
  B60), and Dovecot, which reads that database for every login and waits
  at most one second for a lock, answered "Temporary authentication
  failure" (`database is locked` in `mail.log`) to the IMAP, POP3, SMTP
  AUTH and ActiveSync logins of that moment when the commit took longer on
  a busy disk. Setup and the control panel now write the table only when
  it changes (B133).
* **Nextcloud's brute-force protection no longer throttles Z-Push (B121)**\
  Nextcloud's brute-force protection no longer throttles the box's own
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
* **Nextcloud no longer fails requests while setup rewrites `config.php` (B124)**\
  Nextcloud no longer fails a request (an ActiveSync login got HTTP 401)
  while setup rewrites its `config.php`: root replaced the file with one only
  root could read and gave it to www-data a moment later. The file is now
  written as www-data and replaced atomically (B124).
* **`/etc/dovecot` belongs to root (B123)**\
  `/etc/dovecot` belongs to root now (group `mail` may read): it belonged
  to the account `mail`, which all IMAP, POP3 and LMTP processes run as and
  which could therefore change Dovecot's configuration (read by its root
  processes) and the files that setup writes there as root (B123).
* **Dovecot no longer runs without a passdb during setup (B120)**\
  Dovecot no longer runs without a passdb for two seconds during setup:
  setup restarted it before rewriting `auth-sql.conf.ext`, and a login in
  that moment made Dovecot's config process read the truncated file;
  logins then failed as wrong passwords. Dovecot's configuration is now
  loaded once, after all of it is written, and setup writes Dovecot's files
  (and every file of `tools/editconf.py`) atomically and only when they
  change, following a symbolic link only in a directory of root's own
  (B120).
* **Setup disturbs clients less with reloads instead of restarts (B122)**\
  Setup disturbs the clients less: Dovecot, Postfix and fail2ban reload
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
* **Backup page and backups no longer hang on a slow rsync target (B125)**\
  The backup page of the control panel and the backups no longer hang for
  a minute or more when the rsync target does not answer a connection
  request at once (seen on a production box with a remote rsync backup
  server: ssh waited 11 s for an answer over IPv6, and twice the page
  showed only "Something went wrong" after 60 s). ssh to the target now
  gives an address 10 s for the connection and the SSH banner, then tries
  the next one, and makes two attempts, instead of waiting for the kernel's TCP
  retries; the list of the target's files (status page, and the nightly
  backup's choice between a full and an incremental backup) is tried three
  times (B125).
* **Password hashes no longer in the journal or command lines (B127)**\
  The control panel no longer writes the password hash of a user into the
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
* **Backup page shows the saved status at once (B125)**\
  The backup page shows the status of the backups at once: the status
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
* **Status checks survive an unreadable backup status (B132)**\
  The status checks no longer stop as a whole when the status of the
  backups cannot be read (the target does not answer, or another duplicity
  runs on the same archive directory): the System Status page showed only
  "Something went wrong" and the nightly check mailed a traceback. The
  backup check now fails alone with duplicity's message, and while a backup
  run or a refresh of the backup page queries the target it uses the saved
  status, or warns that none has been saved yet (B132).
* **nginx waits for the control panel up to 630 s (B125)**\
  nginx waits for the control panel as long as gunicorn lets a request
  run (630 s) instead of its default of 60 s, so that the status checks,
  the TLS provisioning and the backup page's live query are no longer cut
  off with a 504 after a minute (B125).
* **Control panel explains when its service does not answer (B125)**\
  The control panel says what happened when its service does not answer:
  for nginx's 502 and 504, a timeout and a lost connection it shows a
  clear message and what to do, on every page, instead of only "Something
  went wrong, sorry." (B125).
* **ActiveSync syncs contacts whose card name has no `.vcf` (B128)**\
  ActiveSync syncs the contacts of users with a card whose name has no
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
* **ActiveSync Ping with a long heartbeat no longer ends in 504 (B129)**\
  A phone's ActiveSync Ping (push) with a heartbeat of more than 630 s no
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
* **`/caldav`, `/carddav` and `/webdav` proxy passes escaped path and query (B130)**\
  The proxy of `/caldav`, `/carddav` and `/webdav` to Nextcloud passes the
  path escaped, as the client sent it, and the query string. It passed
  nginx's decoded path: a name with a space got HTTP 400, an escaped `?`
  began a query string (a DELETE of a card named `?x.vcf` deleted the whole
  address book on a test box), and a query such as `?export` was dropped.
  Only clients set up with these short paths were affected, not those with
  the `/cloud/remote.php/...` URLs or `.well-known`, and not Z-Push. Files
  and cards whose names begin with `.ht`, `.git`, `.svn`, `.hg` or `.bzr`
  pass through these paths as before (nginx's dotfile block does not apply
  to them; B130).
* **nginx's `/mail/config/` deny no longer catches other paths (B134)**\
  A path with `/mail/config/` in it no longer gets HTTP 403 unless it is
  Roundcube's config directory (`/mail/config/...` itself): nginx's deny of
  that directory was an unanchored regex (upstream), which also caught
  Nextcloud files and folders below a folder `mail/config` (through
  `/cloud/remote.php` and the `/webdav` proxy) and the pages of static
  sites under such a path. It is anchored now (`^/mail/config/`; B134).
* **Release tag is an annotated tag (B135)**\
  The release tag is an annotated tag, as CONTRIBUTING.md asks. The tag
  first made for this release on the fork's internal server was a
  lightweight one, which `git describe` without `--tags` does not see:
  the test boxes installed from it showed their commit id as their version
  (status checks, control panel, setup) and bootstrap.sh fetched again on
  every run (B135; never published).
* **Fresh install no longer stops on public DNS resolvers (B136)**\
  A fresh install no longer stops at once on a machine whose DNS resolver
  is a public one (1.1.1.1, and the default resolvers of many hosting
  providers), saying that the hostname is listed in the Spamhaus Domain
  Block List. Spamhaus refuses queries through such resolvers and answers
  127.255.255.254, which setup took for a listing (upstream). Setup now
  stops only on a listing (DBL 127.0.1.2 to 127.0.1.99, ZEN 127.0.0.2 to
  127.0.0.11), shows any other answer as a check it could not make, and
  goes on; the status checks look again later through the box's own
  resolver (B136).
* **ActiveSync FolderSync during an IMAP failure keeps mail folders (B137)**\
  A FolderSync of a phone during an IMAP failure, such as setup's Dovecot
  reload, which ends every IMAP session, no longer answers without the
  mail folders. Z-Push's IMAP backend took a failed folder list for an
  empty one (upstream Z-Push): a new phone got only its calendars and
  address books, and for a phone already set up the answer meant deleting
  its mail folders (it got them back at its next FolderSync and downloaded
  their mail again); a Ping in that moment sent the phone into such a
  FolderSync. Z-Push now connects again and asks once more, and if there
  is still no list it fails the request with a server error (FolderSync
  status 6, which the phone retries later). Another change in
  conf/zpush/z-push.patches, so the update installs Z-Push again (B137).
* **Setup keeps cron off for its whole run (B138)**\
  Setup keeps cron off for its whole run: needrestart, which apt runs,
  started cron again in the middle of setup when setup's `apt-get upgrade`
  replaced a library that a cron job still running from before setup used
  (stopping cron leaves its running jobs alone). Setup now also masks cron
  in `/run` while it runs; a run that is killed leaves the mask until the
  next boot or the next setup run, which removes it (B138, a gap in the fix
  of B82 in rc6).
* **DNS updates as soon as a certificate is installed (B139)**\
  DNS is updated as soon as a certificate is installed (Let's Encrypt from
  the control panel or the nightly run, or a certificate of your own). The
  `_mta-sts` TXT record of a mail domain is published only when its policy
  host has a valid certificate, and after the first certificates of a box
  it was missing until the next DNS update (the daily one at the latest):
  the status checks reported the MTA-STS policy as missing, and other mail
  servers did not use it yet (upstream; B139).
* **First Let's Encrypt run certifies the box's own name too (B140)**\
  The first Let's Encrypt provisioning of a fresh box certifies the box's
  own name too. When the box's name is below one of its mail domains (the
  usual layout), the request grouped by DNS zone lost the box's name and
  its `mta-sts.` name, and mail and the control panel kept the self-signed
  certificate until a second run (by hand or the nightly one; upstream;
  B140).

### Changed

* **Docs: in-place upgrade timing table**\
  Docs: README-fork.md, "In-place upgrade to 26.04", has a table of the
  times of the in-place test runs (each release upgrade, setup, mail
  offline, from 22.04 and from 24.04, with and without other load on the
  same storage), what makes an upgrade slower and when mail is offline
  (English and German).
* **Intrusion Protection covers `miab-zpush` and Z-Push error logs (B126, B121)**\
  Control panel (System > Intrusion Protection): `miab-zpush` is a web
  jail (its bans keep their fixed length with adaptive banning), the slow
  web jails get `miab-slow-zpush` (ActiveSync and Autodiscover), and the
  failed-login report and its status check read Z-Push's error logs as well
  (protocols `activesync` and `autodiscover`, also the files of the last
  rotation). The help texts name ActiveSync and say that `/caldav`,
  `/carddav` and `/webdav` now count under the client's address; the
  allowlist help names the servers of mail apps that sync through their
  provider's cloud (B126, B121).
* **Tests: fail2ban checks for the `miab-zpush` jail (B126)**\
  Tests: the smoke test's fail2ban status check wants `miab-zpush` (and
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
* **`management/cli.py` reads passwords from standard input (B127)**\
  `management/cli.py user add EMAIL -` and `user password EMAIL -` read the
  password from standard input (its first line) instead of the command
  line, which every local account can read; without a password they still
  ask for it. Its usage text says so (B127).
* **Tests: journal hash check and `password-hash.py` (B127)**\
  Tests: the smoke test's new check `admin-journal-no-hash` (with `--ssh`)
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
* **Tests: log audit accepts later milter resets**\
  Tests: the log audit's rule for Postfix's milter warnings while setup
  restarts OpenDKIM or OpenDMARC also accepts a reset later in the milter
  session (`SMFIC_MAIL` and the other commands), not only in the handshake.
  The GitHub counter-test of rc7 (rc6 to rc7) logged it once.
* **Tests: new `activesync` smoke test group**\
  Tests: the smoke test's new group `activesync` (also right after a setup
  run with `--only activesync`) checks Nextcloud's bypass list (127.0.0.1
  listed, no entry twice: `nextcloud-bruteforce-loopback`), that a failed
  login through the `/webdav` proxy is counted for the client's address and
  not for 127.0.0.1 (`nextcloud-forwarded-for`), and syncs a marked event
  and contact through ActiveSync (`zpush-sync`, with the new small client
  `tests/fork/eas.py`).
* **Tests: `client-load.py` keeps clients busy during setup**\
  Tests: `tests/fork/client-load.py` keeps the clients of a few users busy
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
* **Tests: log audit stops accepting "No passdbs specified" (B120, B125, B127)**\
  Tests: the log audit no longer accepts "No passdbs specified" during
  setup (B120). It accepts what Dovecot logs when setup reloads it (also the
  SIGTERM of the IMAP, POP3, ManageSieve and login processes of the old
  configuration), what nginx logs for the ActiveSync and CalDAV/CardDAV
  requests that the one PHP-FPM restart ends (also nginx's `readv()` reset
  of a response it has begun to read, seen in the update test after the
  merge of B125 to B127), and what Postfix and OpenDKIM
  log when a client comes in during setup's restart of OpenDKIM (also
  "Application error"), and fts-xapian's retries of its write lock when two
  processes index a new folder at once (BUGS-fork.md, known limitations).
* **Tests: `zpush-sync` also syncs a card without `.vcf` (B128)**\
  Tests: the smoke test's `zpush-sync` also syncs a marked card whose name
  has no `.vcf` (B128).
* **Tests: `zpush-ping` check for long heartbeats (B129)**\
  Tests: the smoke test's new check `zpush-ping` (group `activesync`): a
  Ping with a heartbeat of 3600 s gets status 5 with the box's bound at
  once, a Ping of 20 s completes, and with `--ssh` nginx's
  `fastcgi_read_timeout` of every `/Microsoft-Server-ActiveSync` location
  is at least a minute longer than that bound; it reads nginx's time units
  and a value set for the server or http block (B129).
  `tests/fork/eas.py` has `Client.ping_answer` (status, the server's
  heartbeat and the changed folders, also for status 5, with a timeout),
  and its `--ping` accepts status 5 and prints the bound.
* **Tests: `nextcloud-dav-proxy` smoke check (B130)**\
  Tests: the smoke test's new check `nextcloud-dav-proxy` (group `web`):
  a card whose name has a space and a `?` is read, found in `?export` and
  deleted through `/carddav`, and the address book stays; a file named
  `.htmiab-smoke-...` put through Nextcloud's own path is read through
  `/webdav`, and a card `.gitmiab-smoke-...vcf` through `/carddav`, as
  nginx's dotfile block must not apply there; `/caldav` and `/webdav`
  answer PROPFIND (B130).
* **Tests: `nextcloud-mail-config-path` smoke check (B134)**\
  Tests: the smoke test's new check `nextcloud-mail-config-path` (group
  `web`): `/mail/config/...` still answers 403, a missing static page
  under `/<name>/mail/config/` answers 404, and a file put into Nextcloud
  below a folder `mail/config` is read through `/cloud/remote.php` and
  through `/webdav` (B134). The log audit's smoke list accepts nginx's
  line for that missing page.
* **Tests: `zpush-ping` waits at most 90 s**\
  Tests: the smoke test's `zpush-ping` waits 90 s at most for the answer
  to its Ping of 3600 s (on a box without the bound it waited for nginx's
  504 after 635 s, and left Z-Push waiting for up to an hour): no answer
  within 90 s fails the check, and a Ping of 60 s of the same device ends
  the long one in Z-Push (about 2.5 minutes in all, and no Ping is left).
* **Z-Push changes are patch blocks in `z-push.patches` (B126, B128)**\
  Setup makes every change of the fork to Z-Push's code in one way: the
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
* **Tests: log audit accepts messages of the update from rc7 (B122, B126)**\
  Tests: the log audit accepts, in a setup run, what the update from rc7
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
* **Tests: `zpush-patches` smoke check (B126, B128)**\
  Tests: the smoke test's new check `zpush-patches` (group `activesync`,
  with `--ssh`): `/usr/local/lib/z-push/version` carries the checksum of
  the blocks of the checkout's conf/zpush/z-push.patches, and the installed
  tree has every change of it (B126, B128).
* **`update-check.sh after` also uses the `unreleased.txt` list**\
  `tools/update-check.sh after` also uses `tools/expected-changes/unreleased.txt`,
  the changes since the newest release, when the checkout after the update
  is not at a release tag (bootstrap.sh with `TAG=<branch or commit>`) or
  the new version has no list of its own; before, such an update matched no
  release list and every change of the release was UNEXPECTED. The new list
  names the jail `miab-zpush` (and `miab-slow-zpush`, B126) and the mark of
  Z-Push (B126, B128), which the tool now records (`version.txt`: `zpush
  2.7.7+patches-<16 hex digits>`). Every update may also change the version
  named by the status checks, and an update to a branch or commit records
  its commit id as the version (`any.txt`).
* **Nextcloud calendar app 6.6.3 to 6.6.4**\
  Nextcloud's calendar app 6.6.3 → 6.6.4 (bug fixes; for the fresh install
  and the steps of the upgrade chain to 32, 33 and 34), SHA256
  `0557b6b5852a467cf3f746e59d56478d227f78bf7a66357b30dfc10cae4c7e3c`
  (computed from the download, the same as GitHub's digest of the release
  asset). Its `appinfo/info.xml` accepts Nextcloud 32 to 35 and PHP 8.1 to
  8.5, as 6.6.3's did. Setup installs the pinned apps only together with a
  new Nextcloud version (as upstream; the app store is off), so a box that
  already runs Nextcloud 34.0.5 keeps its calendar app at the update. The
  other pinned components were checked against their upstream releases on
  2026-10-27 and are current.
* **`update-check.sh` empty variables written as `''`**\
  `tools/update-check.sh` writes its empty local variables as `''`
  (shellcheck SC1007); no change in what it does.
* **Tests: client load counts FolderSync status 6 as unavailable (B137)**\
  Tests: the client load (`tests/fork/client-load.py`) counts a
  FolderSync status 6 as "unavailable" (a server error that the phone
  retries, like HTTP 503; within `--max-outage`), and the log audit accepts
  Z-Push's warning that it connects again for a folder list in a setup run
  (B137).
* **Tests: log audit accepts systemd's cron leftover note (B138)**\
  Tests: the log audit accepts systemd's note of the left-over processes
  of a cron job when setup starts cron again at its end (B138).
* **Tests: log audit accepts more cron and reverse DNS notes**\
  Tests: the log audit accepts systemd's note of the left-over processes
  of any cron job when setup starts cron again (not only of Nextcloud's
  `cron.php`), and with `--internet` the reverse DNS warning of Postfix
  also for clients of the submission ports (scanners).
* **Tests: log audit accepts more repeated-run messages (B135)**\
  Tests: more classes of the repeated runs in the log audit's lists: git's
  warning that a release tag is a tag object when the in-place and
  migration tools clone it (`git clone -b <tag> --depth 1`; every release
  tag is annotated, B135), ntpd's skipped link-local addresses of Docker's
  interfaces during an in-place upgrade, logind's note on a login over the
  in-place tool's fallback SSH server started from a login session, and on
  the old box (upstream v74)
  Dovecot 2.3's notes at stop-old and cron's mail to root@, which has no
  alias there.
* **Log audit accepts Dovecot auth-worker end note at setup reload (B122)**\
  Tests: the log audit accepts the auth-worker processes' note of their
  end at setup's Dovecot reload (`Killed with signal 15` from the master,
  B122), seen in the repeated update test.
* **Log audit allowlists from the final runs of this release**\
  Tests: the log audit's lists, from the final runs of this release: the
  first start of the jails that read mail.log in the setup run that adds
  them (a migration), Postfix's cleanup and systemd at setup's OpenDKIM
  restart, the smoke test's rejected mails from a client with reverse DNS
  (a box on the Internet), Outlook's Autodiscover schema that Z-Push does
  not support (HTTP 400), the TLS error "unexpected message" of old
  clients and scanners (`--internet`), and Dovecot 2.3's note when the
  migration stops the old box during a delivery (old-box list).
* **Log audit accepts Roundcube CardDAV migration race after update from rc7**\
  Tests: `tests/fork/log-audit-allow-from-rc7.txt`, which `update-check.sh
  after` adds by itself after an update from rc7 or earlier, accepts
  Roundcube's CardDAV migration race ("UNIQUE constraint failed:
  carddav_migrations.filename") of two first logins in the same second on
  a box whose Roundcube was not used since an earlier setup run upgraded
  the plugin; `after` named it in the update test from rc7.

### Upgrade note

* **Updating boxes on rc7: bootstrap command and preparations (B125, B129)**\
  Boxes on rc7 are updated with the bootstrap command of "Updating the
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
* **Updating boxes on rc1 to rc6 follows the rc7 steps first**\
  Boxes on rc1 to rc6 are updated the same way, with the steps of rc7's
  upgrade note first: `sudo git -C /root/mailinabox remote set-url origin
  https://github.com/LM1337/Mail-in-a-box-26` for rc1 to rc3, and
  `tools/update-check.sh before` and `backup` through `curl ... | sudo bash
  -s -- STEP`, as these releases have no copy of the tool. Read the upgrade
  notes of every release in between; `after` uses the lists of rc7 and of
  v78-r2604.0.
* **Z-Push failed-login log message changed, log control characters escaped**\
  Z-Push's message for a failed ActiveSync login reads "Failed to
  authenticate user '...' from IP ...." now (Z-Push: "IP: ... failed to
  authenticate user '...'"), and control characters in Z-Push's log lines
  are escaped (a multi-line message is one line with `\n`). A fail2ban
  filter or log tool of your own for Z-Push needs the new form. A request
  without a password no longer logs that message.
* **`/var/log/z-push` is root-owned and setup creates the log files**\
  `/var/log/z-push` belongs to root, group www-data (0750), and Z-Push can
  no longer create files there: setup creates `z-push.log`,
  `z-push-error.log`, `autodiscover.log` and `autodiscover-error.log`, and
  removes what is not a regular file there. Per-user logs of your own
  (`$specialLogUsers` in Z-Push's `config.php`) need their files created
  the same way (www-data, 0640).
* **Outlook for iOS and Android can trigger fail2ban bans of Microsoft servers (B126)**\
  Outlook for iOS and Android syncs an Exchange ActiveSync account through
  Microsoft's servers: if your users do that, put those networks on the
  fail2ban allowlist, or 20 wrong passwords entered there within two
  minutes ban these servers from the web ports for all of these users.
  Not only a user can cause that by mistake: anyone can do it on purpose,
  with any account name and a wrong password in the app, and repeated bans
  of these addresses lead to recidive's ban of one week on all ports
  (B126).
* **Z-Push log user-name escaping and HTTP 503 on temporary login failure (B126)**\
  Z-Push escapes "]" and "\" in the user names at the start of its log
  lines (`[a\]b]`), and Autodiscover's lines start with `[#unknown]`. A
  filter of your own that reads the user names there needs to allow for
  that. A temporary login failure (Dovecot or Nextcloud cannot check the
  password at that moment) is answered with HTTP 503 now and logs
  `Exception: (ServiceUnavailableException)` instead of a failed login
  (B126).
* **Backup page shows no saved status until its first refresh**\
  The backup page shows "No status of this backup target has been saved
  yet" on the first visit after the update, until its first refresh (or
  the next backup run) ends. The saved status is kept in
  `/var/lib/mailinabox/backup-status` (root only).
* **Setup sets Nextcloud `trusted_proxies` and `forwarded_for_headers`**\
  Setup sets Nextcloud's `trusted_proxies` (adds 127.0.0.1, keeps the
  others) and `forwarded_for_headers` (`HTTP_X_FORWARDED_FOR` only, the
  Nextcloud default; another value there is replaced). A reverse proxy of
  your own in front of the box keeps working when it sends
  `X-Forwarded-For`.
* **`/etc/dovecot` ownership changes to root:mail**\
  `/etc/dovecot` changes from `mail:dovecot` to `root:mail` (no write for
  the group, nothing for others). Your own files there stay readable by the
  mail processes; give a file that other processes must read other
  permissions in another place.
* **First update reloads Dovecot once; phones may show one password prompt (B126)**\
  The first update with this release reloads Dovecot once (its open IMAP
  sessions log in again), as the checksum of its configuration is new. In
  that second, the Z-Push of rc7 or earlier, which runs until setup
  installs the new one later in the same run, can answer an ActiveSync
  request with HTTP 401 when its CalDAV or CardDAV login through Nextcloud
  is cut (seen once for one request in the update test under client load):
  a phone may show a password prompt once (the password is unchanged).
  The new Z-Push answers such a moment with 503 (B126).
* **Old password hashes remain in the journal and syslog until rotated (B127)**\
  The password hashes that the control panel's logins wrote before (B127)
  stay in the journal and in `/var/log/syslog` until these are rotated
  away. To remove them at once: `journalctl --rotate` and
  `journalctl --vacuum-time=1s` (this deletes the whole journal up to now),
  and delete the syslog files that hold such lines, the compressed rotated
  ones (`syslog.2.gz` and older) too: `zgrep -l 'verified)'
  /var/log/syslog*` lists them all (plain `grep` does not look into the
  `.gz` files). Otherwise they stay until logrotate drops them. The nightly
  backups do not contain `/var/log`.
* **Passwords with a null character or over 511 bytes are refused (B127)**\
  A new password with a null character or of more than 511 bytes is now
  refused with a message (B127). Before, such a password gave a hash that no
  password matched. Existing passwords are not changed.
* **Setup patches Z-Push 2.7.7 and downloads it once more (B128)**\
  Setup changes a few functions of Z-Push 2.7.7 (conf/zpush/z-push.patches)
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
* **nginx reload keeps old workers up to an hour for ActiveSync polls (B129)**\
  After the update, a reload of nginx keeps its old worker processes until
  their running ActiveSync long polls end, up to an hour (before: 10.5
  minutes). Pings of up to 59 minutes hold a PHP-FPM worker each, as they
  already did past nginx's old timeout (B129).
* **`/caldav`, `/carddav` and `/webdav` are prefix locations in nginx (B130)**\
  `/caldav`, `/carddav` and `/webdav` are now prefix locations of nginx: a
  proxy of your own for one of these paths (`www/custom.yaml`) would now
  clash with them (B130).
* **Reverse proxies must keep ActiveSync requests open for an hour (B129)**\
  A reverse proxy or firewall of your own in front of the box must keep an
  ActiveSync request open for an hour (3660 s) too, or it ends the long Pings
  instead of nginx (B129).
* **Hand-changed files in `/root/mailinabox` must be restored before the update (B125, B129)**\
  Put back every file that you changed by hand in `/root/mailinabox`
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
The test matrix T1 to T5b and T6 (on the Internet: Let's Encrypt, public
DNS, TLS and DANE, mail to and from an external mailbox); their first run
found B135 to B139 and the repeated one B140. Which commit each scenario
ran, and the results, are in TESTING-fork.md ("v78-r2604.0"); `mailcheck`
ran with the lab's probe address, the round trip with the external mailbox
by the test's own script.

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

* **Munin alert settings in the control panel with test notification**\
  Munin: an admin panel setting for Munin's alerts, under System > Munin
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
* **API documentation covers every route of the management daemon**\
  API documentation: `api/mailinabox.yml` documents every route of the
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
* **New `update-check.sh` tool checks a box around an update (B103, B104)**\
  Tools: `tools/update-check.sh`, the checks around an update of a box of
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
* **In-place tool runs a fallback SSH server on port 1022 (B100, B101)**\
  Tools: during each release upgrade, `tools/upgrade-in-place-to-2604.sh`
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
* **In-place tool reports when port 22 is down and back**\
  Tools: `tools/upgrade-in-place-to-2604.sh` says in the run when the release
  upgrade has stopped the SSH server on port 22 and when port 22 answers
  again (its SSH banner), with the minutes in between.
* **Setup marks its start and end in the journal (B105)**\
  Setup marks its start and end in the journal ("Mail-in-a-Box setup
  started", "Mail-in-a-Box setup ended (exit code N)", identifier
  `mailinabox-setup`). `tests/fork/log-audit.sh` prefixes what the box logs
  in between with `[setup]` (outside the phases of an in-place upgrade;
  only marks that root logged count, B105),
  and allowlist rules that start with `^\[setup\]` accept a class only
  there: connections that setup's restarts of the services cut are normal
  during setup and a finding at any other time. The report names the setup
  runs (`setup_runs` in the JSON report).
* **Smoke test group `api` covers the management API**\
  Tests: `tests/fork/smoke.py` group `api` (in every scenario): `api-auth`
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
* **New `api-routes.py` test checks routes against the API documentation**\
  Tests: `tests/fork/api-routes.py` (stdlib only, no box): every route of
  `management/daemon.py` (method and path, path parameters normalised) is
  documented in `api/mailinabox.yml` and every documented operation has a
  route; `smoke.py` calls or excludes each documented operation exactly
  once; the content types it expects are the documented ones. The control
  panel page and Munin's pages behind the session cookie are listed as not
  part of the API. Exit code 1 on drift.
* **Log audit gains `--baseline`, `--internet` and `--smoke` allowlists**\
  Tests: `tests/fork/log-audit.sh --baseline BEFORE.json` compares with the
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
* **More log audit allowlist rules for reboot, Z-Push and setup noise**\
  `tests/fork/log-audit-allow.txt`: rules for `(sd-pam)`'s "Varlink call
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

* **Setup no longer sources a settings file from `/tmp` as root (B89, B96)**\
  Setup: an update no longer runs as root what another local user put into
  `/tmp`. Each run after the first wrote the settings of
  `/etc/mailinabox.conf` to `/tmp/mailinabox.prev.conf` and sourced that
  file as root; when a file of that name already existed (any local user,
  and www-data, can create one), the write failed and setup sourced the
  other user's file. It now reads the settings through a pipe, no file
  (B89; found twice, also as B96).
* **Setup uses private temporary directories for downloads (B97)**\
  Setup: the downloads of Nextcloud and its apps, Roundcube and its
  plugins, Z-Push and Bootstrap, the certificate request of the first
  self-signed certificate and the daily download of Postgrey's allowlist no
  longer use fixed or predictable names in `/tmp`, but a directory of
  root's own (`mktemp -d`, mode 0700). Another local user could create
  these names first and make setup fail; for Z-Push and the Roundcube
  plugins of git, a directory created in the right moment let them replace
  the unpacked code before setup moved it into place (B97).
* **DNSSEC keys are copied to a private directory for zone signing (B98)**\
  DNS: the management daemon copies the DNSSEC keys for signing a zone
  into a directory of its own (mode 0700), not to `/tmp/K<domain>...`
  under the key's name. Another local user could create these names first
  (the key tags are public); the copy then failed and the zone was not
  signed again, so its signatures would expire after 30 days (B98).
* **Setup no longer changes owners through symlinks in `/var/log/munin` (B86)**\
  Munin: setup no longer changes the owner of what a symbolic link in
  `/var/log/munin` points to. It ran `chown munin` as root on the CGI logs
  there, in a directory that belongs to munin; now `chown -h` (B86).
* **`settings.yaml` is no longer written through a symbolic link (B87)**\
  Settings: the daemon and setup no longer write `settings.yaml` through a
  symbolic link. `$STORAGE_ROOT` belongs to the storage user; root now
  writes a new file under a random name and renames it (with at most the
  read bits of the old file's mode), and reads only a regular file there,
  with `O_NOFOLLOW` and without blocking on a FIFO (B87).
* **In-place tool no longer copies the system archive into `$STORAGE_ROOT` (B90)**\
  Tools: for backups on the machine itself (local, or a `file://` target
  below a directory that another account may change),
  `tools/upgrade-in-place-to-2604.sh` no longer copies the encrypted system
  archive as root into `$STORAGE_ROOT/backup/encrypted-system/`: that path
  runs through `$STORAGE_ROOT`, which belongs to the user-data account, so a
  symlink there could have redirected root's mkdir and copy. The archive
  stays in `/root/upgrade-2604`, as the tool already said to copy it off the
  machine. A `file://` target whose path only root can change gets the copy
  as before (B90).
* **Backup host and path are validated before ssh and rsync run as root (B102)**\
  Tools: for an rsync backup target, `tools/upgrade-in-place-to-2604.sh`
  (and the new `tools/update-check.sh backup`) no longer passes the host
  and path from `custom.yaml` unchecked to ssh and rsync as root: a host or
  path that starts with "-" (an option such as `-oProxyCommand=...`) or has
  other characters than letters, digits, `.`, `_`, `-` (and `@` between user
  and host) stops the tool, which names `--no-offsite` (`--no-upload`).
  `custom.yaml` lies below `$STORAGE_ROOT`, which the user-data account can
  change; current OpenSSH refused the resulting command line anyway (B102).
* **Management daemon no longer runs out of file descriptors (B91)**\
  Management: the daemon no longer runs out of file descriptors. Each API
  call left `users.sqlite` open (1 to about 90 times per call); after a few
  hundred calls the daemon reached its limit of 1024 open files and
  answered every request with 500 ("unable to open database file") until
  it was restarted. Connections now close with their cursor (B91).
* **ActiveSync syncs the address book of new users again (B99)**\
  Nextcloud/Z-Push: ActiveSync syncs the address book of new users again.
  Nextcloud 34 puts an example contact into each new address book under the
  name `default`, without the `.vcf` that Z-Push's CardDAV backend adds when
  it fetches a contact; the Sync of the contacts folder then failed with a
  PHP error (HTTP 500), so no contact reached the phone. Setup turns the
  example contact off (`dav` `enableDefaultContact`). Users created before
  keep their example contact: delete it in Nextcloud's Contacts (it is
  marked "This is an example contact"), and the address book syncs (B99).
* **OpenDKIM tables are written in a fixed order (B95)**\
  OpenDKIM: the `KeyTable` and `SigningTable` are written in a fixed
  (sorted) order. The domains came from a Python set, whose order changes
  with every process, so with more than one mail domain each setup run (the
  management daemon, which writes them, starts anew in every run) and the
  first DNS update after a reboot rewrote both tables and restarted
  OpenDKIM once more, although nothing had changed. Mail sent in the moment
  of a restart goes out without a DKIM signature (Postfix has
  `milter_default_action=accept`) (B95).
* **Quota API answers 400 for invalid requests (B88)**\
  API: `GET /mail/users/quota` for an address that is not a user answers
  400 with the message instead of 200 with the error inside the JSON, and
  `POST /mail/users/quota` without a quota answers 400 instead of 500
  (B88).
* **Smoke test and log audit fixes for temporary user and Munin alerts**\
  Tests: `admin-api-tmp-user-alias` removes the archived mailbox of its
  temporary user again (with `--ssh`), which every run left behind as an
  inactive account. `munin-alert-contact` passes when the admin panel
  turned the alerts off. `log-audit.sh --smoke` accepts the two deliberate
  failed logins of `api-auth`; the default allowlist does not, so that real
  failed logins to the control panel stay visible on a production box.
* **`update-check.sh mailcheck` reads Received headers of TLS answers (B107)**\
  Tools: `tools/update-check.sh mailcheck` reads the Received header of
  an answer that came in over TLS. Postfix puts the TLS session and
  "(No client certificate requested)" between the client and "by", and
  the check said FAILED for a round trip that had worked (B107).
* **`update-check.sh` finds the checkout of an upstream box (B106)**\
  Tools: `tools/update-check.sh` finds the checkout of a box that has it in
  `/mailinabox` (an upstream box before the in-place upgrade): from the
  directory that `/usr/local/bin/mailinabox` changes into, as long as it is
  root's own. `before` recorded no version and no status checks there and
  said "0 errors", and `backup` stopped (B106).
* **`update-check.sh after` expects the random minute of the nightly job (B108)**\
  Tools: `tools/update-check.sh after` expects the new minute of the
  nightly job, which setup picks at random on every run; an update that
  changed nothing else ended with "RESULT: CHANGED" (B108).
* **Expected changes of rc7 include those of rc4 and rc5 (B109)**\
  Tools: the expected changes of rc7 include those of rc4 and rc5 that the
  state record shows (`/etc/mailname` and `/etc/hosts`, B60; Dovecot and
  `mailinabox.service` enabled again, B67 and B69), for updates from rc1 to
  rc3 (B109).
* **`update-check.sh after` does not judge in-place upgrades or migrations (B110)**\
  Tools: `tools/update-check.sh after` no longer judges an in-place upgrade
  or a migration from upstream Mail-in-a-Box by the lists of the fork's
  updates: it lists the changes and says "RESULT: NOT JUDGED" (exit code
  3) when the Ubuntu release changed or the box came from upstream (B110).
* **Fallback SSH test no longer leaves an empty `/root/upgrade-2604` (B111)**\
  Tools: `--ssh-fallback-test` of the in-place tool no longer leaves an
  empty `/root/upgrade-2604` behind (B111).
* **In-place tool restores `/run/sshd` within 2 seconds (B112)**\
  Tools: the in-place tool puts back `/run/sshd`, which the fallback SSH
  server needs, within 2 s after the release upgrade stops ssh.service (it
  looked every 10 s, and new logins on port 1022 failed meanwhile). Its
  texts gave the outage times of the first rc7 run (B112); they now give
  those of all rc7 runs (see "Changed").
* **Migration tool `--check` proposes the start command with all options (B113)**\
  Tools: `tools/migrate-to-2604.sh --check` proposes the start command with
  all options of the check (`--public-ip`, `--public-ipv6`,
  `--private-ip`, `--hostname`, ...); it named only `--from`, the SSH options
  and `--skip-network-checks`, and `--from` with nothing after it for
  `--from-backup` (B113).
* **`update-check.sh after` accepts both munin-node port names (B114)**\
  Tools: `tools/update-check.sh after` accepts both names under which
  munin-node holds its port (`munin-node`, or its path cut to 15
  characters, `/usr/sbin/munin`) (B114).
* **Fallback SSH server only takes key files that sshd accepts (B115)**\
  Tools: the fallback SSH server of the in-place tool takes, with
  StrictModes (sshd's default), only the key files that sshd accepts on
  port 22: a file whose path up to the home directory another account can
  write (others, or a group with another member than the user; Ubuntu's
  sshd accepts a user private group), or that belongs to another user, is
  skipped with a warning, as sshd ignores it. It accepted such keys, so whoever could write an
  administrator's home could log in on port 1022 as that administrator.
  Its copy of the keys is `root:<the user's group>`, mode 0640 (B115).
* **`update-check.sh` rejects checkouts not owned by root (B116)**\
  Tools: `tools/update-check.sh` no longer uses a checkout it rejected (it
  warned and, through curl, ran the status checks and `backup.py` from
  `/root/mailinabox` anyway), and a checkout counts only when every file in
  it is root's own and not writable by group or others (B116).
* **Backup tools use `$STORAGE_ROOT/backup` only when it is root's own (B117)**\
  Tools: `tools/update-check.sh backup`, the in-place tool's system archive
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
* **Fallback SSH server refuses `Match` blocks in nested includes (B118)**\
  Tools: the fallback SSH server also refuses to start when a file included
  from an included file (for example from `sshd_config.d/*.conf`) has a
  `Match` block; it looked one level deep only (B118).
* **Fallback SSH server starts for the upgrade after the reboot into 24.04 (B119)**\
  Tools: the fallback SSH server also starts for the release upgrade that
  begins by itself after the reboot into 24.04: with socket activation
  `/run/sshd` is missing until the first SSH login, so `sshd -T` failed and
  there was no fallback (B119). The tool creates the directory first. A
  `--ssh-fallback-test` that does not start no longer leaves an empty
  `/root/upgrade-2604` either (B111).

### Changed

* **Interactive setup update skips the new-installation welcome dialog**\
  Setup: an interactive update of an existing box (`/etc/mailinabox.conf`
  exists) no longer shows the welcome dialog of a new installation ("You
  should only install this on a brand new Ubuntu installation"). The
  questions that follow (hostname, and the IP addresses where they differ
  from what the box finds) come as before; non-interactive runs are
  unchanged.
* **Setup reloads nginx instead of restarting it**\
  nginx: setup reloads nginx (after `nginx -t`) instead of restarting it.
  A restart gave the running requests only the unit's stop timeout (5 s on
  Ubuntu) and cut long-polling ActiveSync, CalDAV and CardDAV clients; a
  reload lets the old workers finish them. Setup still starts nginx when it
  does not run and restarts it when the running binary is not the
  installed one (a package upgrade that left the old process running). The
  management daemon's web update already reloaded. Setup's restarts of
  PHP-FPM (four per run) still end an ActiveSync long poll, which the
  client then starts again.
* **Journal size and rate limit checked, no change**\
  Journal: checked, no change. Since rc6 Dovecot logs through syslog, so
  its lines are in the journal too. The journal stays bounded: setup keeps
  it for 10 days (`MaxRetentionSec=10day`, as upstream), and journald's
  defaults on 26.04 (systemd 259) cap it at 10% of the file system, at most
  4 GiB, and keep 15% free. Its rate limit drops lines only from the
  journal: journald forwards syslog lines to rsyslog before it applies the
  limit, so `/var/log/mail.log`, which fail2ban reads, keeps all of them
  (test box: 100000 lines in a few seconds from one unit, 37500 in the
  journal, all 100000 in the syslog file). A comment in setup/system.sh
  says so.
* **Pre-upgrade messages name the fallback SSH server and outage times**\
  Tools: the messages before a release upgrade (and in the motd) name the
  fallback SSH server and how to reach it. The help of
  `tools/upgrade-in-place-to-2604.sh` describes it. The plan of `--check`
  says that new SSH logins on port 22 fail and sudo is missing for a while
  during the release upgrades; the tool gives the times of all rc7 runs
  (port 22: 19 to 42 minutes from 22.04, 6 to 19 minutes from 24.04; sudo:
  12 to 37 minutes), which were 20 to 40, 5 to 20 and 12 to 31.
* **Log audit `--since` accepts short forms like `-24h`**\
  Tests: `tests/fork/log-audit.sh --since` also takes the short forms `-90s`,
  `-30m`, `-24h`, `-2d` and `-1w`; `date -d` fails on them ("-24h" reads the
  "h" as a time zone).
* **Docs: updating the fork and in-place upgrade outage times**\
  Docs: README-fork.md, "Updating the fork", gives the commands of
  `tools/update-check.sh` for a box on rc6 or earlier (through curl, with
  the Docker options) and what the results and exit codes of `after` mean;
  "In-place upgrade to 26.04" has the outage times of the rc7 tests, what
  the fallback SSH server did in them, how to try it before the upgrade,
  and `update-check.sh` around an in-place upgrade. TESTING-fork.md has the
  results of the rc7 certification runs.

### Upgrade note

* **Update from rc1 to rc6 takes two commands**\
  Boxes on rc1 to rc6 are updated with the two commands of "Updating the
  fork" in README-fork.md:
  `sudo git -C /root/mailinabox remote set-url origin https://github.com/LM1337/Mail-in-a-box-26`
  and
  `sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/setup/bootstrap.sh)"`.
  The first one is needed for rc1 to rc3 and changes nothing on rc4 to rc6.
  Setup no longer shows the welcome dialog of a new installation; the other
  dialog boxes (host name, public IP address) are shown as before, and
  Enter keeps the current values.
* **Munin alerts need no action on update**\
  Munin's alerts: nothing to do. Without a setting `munin.conf` stays as in
  rc6 (alerts of warnings and critical values to administrator@). To change
  the address or turn them off: System > Munin Monitoring. Changes to
  `/etc/munin/munin.conf` by hand are overwritten (as before by setup, now
  also when the setting is saved); own Munin settings belong into
  `/etc/munin/munin-conf.d/`.
* **First setup run rewrites OpenDKIM tables once (B95)**\
  The first setup run of this release writes the OpenDKIM tables once more,
  in sorted order, and restarts OpenDKIM (B95); later runs leave them alone.
* **Users created earlier keep Nextcloud's example contact (B99)**\
  Users created before this release keep Nextcloud's example contact, and
  their ActiveSync contact sync fails until it is deleted in Nextcloud's
  Contacts (B99). Setup deletes no user data.
* **Fallback SSH port 1022 may need a provider firewall rule**\
  The fallback SSH server of the in-place tool listens on port 1022 during
  each release upgrade. If a firewall of the provider must let it through,
  open it there before the upgrade and try it with
  `curl -s https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/tools/upgrade-in-place-to-2604.sh | sudo bash -s -- --ssh-fallback-test`
  (README-fork.md, "In-place upgrade to 26.04").
  `UPGRADE_SSH_FALLBACK_PORT=off` turns it off.
* **Run `update-check.sh` steps around the update**\
  Before and after the update, `tools/update-check.sh before`, `backup`,
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

* **Roundcube and Nextcloud show the fork's favicon**\
  Roundcube and Nextcloud show the fork's favicon (`branding/favicon.ico`).
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
* **New `log-audit.sh` collects log warnings and errors (B80–B84)**\
  Tests: `tests/fork/log-audit.sh` (as root on the box, read-only) collects
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

* **In-place tool no longer warns about disabled `ssh.service` (B70)**\
  Tools: phase verify of `tools/upgrade-in-place-to-2604.sh` no longer
  warns that `ssh.service` was enabled before the upgrade and is disabled
  now, and `etc-report.txt` no longer advises to enable it. Since 24.04
  `ssh.socket` starts it. Units that are started another way (an enabled
  socket, path or timer, a new name, a running unit that pulls them in)
  are left out of the check (B70).
* **Tool terminals attach to the tmux session and show the run (B71)**\
  Tools: the terminal that the tools attach to their tmux session shows
  the run. It stayed blank in rc4 and rc5 (the terminal was opened only for
  reading), and through `curl ... | sudo bash` the tools did not attach it
  at all ("Could not attach this terminal"). Now they attach it in all
  these forms, with sudo on 22.04 and 24.04 and with sudo-rs on 26.04; Ctrl-b
  d detaches. They tell sudo-rs from sudo by the path of the binary that
  runs the session; a test version ran that binary with `--version` as root.
  `--check` no longer advises to start the command inside tmux, except for a
  `TAG` of rc1 to rc3 (B71).
* **tmux window closes 60 seconds after a successful last run (B72)**\
  Tools: after the last reboot of `tools/upgrade-in-place-to-2604.sh`
  the tmux window closes by itself 60 seconds after a successful run,
  instead of waiting for Enter forever; after a failure it stays open (B72).
* **In-place tool advises `tail -f` when tmux attach is impossible (B73)**\
  Tools: `tools/upgrade-in-place-to-2604.sh` says that from a few minutes
  into the release upgrade to 26.04 until the reboot a new `tmux attach`
  cannot reach the run ("open terminal failed: not a terminal": tmux 3.6
  replaces tmux 3.4), and to follow the log with `sudo tail -f
  /root/upgrade-2604/upgrade.log` instead. Before, it advised to wait and
  attach again. The log hints say `sudo tail -f` (B73).
* **Setup no longer duplicates Dovecot SSL settings in `10-ssl.conf` (B74)**\
  Dovecot: setup no longer adds another commented copy of each SSL setting
  to `/etc/dovecot/conf.d/10-ssl.conf` on every run. The settings were
  passed to `editconf.py` with spaces around "=" (B74).
* **`logrotate.service` no longer fails on in-place upgraded boxes (B75)**\
  System: on boxes upgraded in place to 26.04, `logrotate.service` no
  longer fails every day. The release upgrade leaves cloud-init's old
  `/etc/logrotate.d/cloud-init` next to the new `cloud-init-base`. Setup
  removes unchanged logrotate files that their package no longer ships
  (B75).
* **Migration tool Spamhaus checks ignore the resolver search domain (B76)**\
  Tools: the Spamhaus checks of `tools/migrate-to-2604.sh` no longer
  append the resolver's search domain to the names they look up. With a
  wildcard record in that domain they reported "unexpected answer" with
  the wildcard's address (B76).
* **Migration tool `--check` lists skipped network checks as ignored (B77)**\
  Tools: `tools/migrate-to-2604.sh --check --skip-network-checks` lists
  the skipped network checks (port 25, Spamhaus) as ignored, not as
  blockers, and no longer exits with code 1 because of them. The run with
  the same options never stopped on them (B77).
* **Postfix no longer delays the first port 25 connections (B78)**\
  Postfix: the first connections to port 25 after a start of Postfix no
  longer wait 100 seconds for the greeting. A restart at the wrong moment
  left Berkeley DB's temporary file of tlsmgr's TLS session cache
  (`/var/lib/postfix/__db.smtp_scache.db`), and every later start stumbled
  over it. A systemd drop-in of setup removes such files before each start
  (B78).
* **Setup waits for apt and dpkg locks (B79)**\
  Setup: setup no longer stops with "Could not get lock" when apt-daily
  or unattended-upgrades runs at the same time (for example some minutes
  after a boot). It waits up to 10 minutes for the dpkg and apt locks
  before each apt-get call (B79).
* **Munin alerts reach the administrator (B80)**\
  Munin: alerts reach the administrator. munin.conf defines the contact
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
* **systemd removes spampd's stale PID file after each stop (B81)**\
  Spam: systemd removes spampd's PID file after each stop, as root
  (drop-in `/etc/systemd/system/spampd.service.d/mailinabox-stale-pid.conf`
  with `ExecStopPost`); spampd itself cannot (it logs "Couldn't unlink
  /run/spampd.pid"), and the stale file stayed behind. The PID file stays
  in the root-owned `/run`. A first version of this fix, replaced before
  the release, moved it into a directory owned by spampd, which would have
  let a compromised spampd redirect root's write of the file with a
  symlink; setup removes that version's drop-in and `/run/spampd` from
  boxes that ran it (B81).
* **Cron is paused while setup runs (B82)**\
  Setup: cron is stopped while setup runs and started again at its end,
  also when setup fails. Cron jobs no longer run against half-configured
  services, and their mail to root no longer bounces on a new box before
  setup has written the root@ alias. A cron that the tools stopped stays
  stopped (B82).
* **Setup restarts nsd after changing nsd.conf (B83)**\
  DNS: setup restarts nsd when it changed nsd.conf, so that a new address
  of the box and the logging to syslog take effect without a reboot (B83).
* **Tmux scopes of the tools have a description (B84)**\
  Tools: the tmux scopes of both tools, and the scope in which the in-place
  tool continues after a reboot, have a description; on 22.04 systemd
  complained about the old one (the multi-line command) at every
  daemon-reload. The resume script quotes the scope command with
  `printf %q`, so the description with its spaces reaches systemd-run as
  one argument (B84).
* **Dovecot logs through syslog so rotation no longer blinds fail2ban (B85)**\
  Dovecot: after a rotation of `/var/log/mail.log` Dovecot's lines go to
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

* **In-place tool warns about SSH and sudo outages during release upgrades**\
  Tools: before each release upgrade `tools/upgrade-in-place-to-2604.sh`
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
* **Smoke test ignores its own marked test mails in manifest comparison**\
  Tests: `tests/fork/smoke.py` marks every mail it sends with the header
  `X-Miab-Test: 1`. The manifest comparison (`mig-folders-<user>`,
  `mig-pop3-uidl-<user>`) ignores marked mails and the automatic replies
  and bounces to them, and says how many it ignored; any other missing or
  new mail, and a seeded mail that is there twice, is a FAIL. Before, every
  mail sent to the box since the manifest was a FAIL (the 6 known FAILs of
  the rc5 runs). `smoke.py --send-test-mail FROM TO` sends a marked mail
  for the testers' own checks. `seed-legacy.sh` leaves the same mails out of
  the manifest. Manifests of earlier `seed-legacy.sh` runs still work.
  TESTING-fork.md describes it.
* **Smoke test checks fail2ban after a mail.log rotation (B85)**\
  Tests: `tests/fork/smoke.py --fail2ban` rotates `mail.log` once before
  the attacks (`fail2ban-log-rotation`) and checks that rsyslog writes the
  new file and that no Dovecot process holds a file in `/var/log`
  (`log_path=syslog`; with Dovecot's own `log_path`, up to rc5, it must
  hold the new `mail.log`), so a jail that a rotation made blind fails
  (B85). `fail2ban-filters` has a Dovecot line in the syslog form.
* **Smoke test checks Munin alert contact and enabled services**\
  Tests: `tests/fork/smoke.py` checks Munin's alert contact
  (`munin-alert-contact`), and `services-enabled` no longer reports a SysV
  service of 22.04 (postgrey) as not enabled. `prepare-testenv.sh` writes
  its SpamAssassin file with mode 644 also under a umask of 077 (the IMAP
  processes could not read it).

### Upgrade note

* **Updating boxes on rc1 to rc5**\
  Boxes on rc1 to rc5 are updated with the two commands of "Updating the
  fork" in README-fork.md:
  `sudo git -C /root/mailinabox remote set-url origin https://github.com/LM1337/Mail-in-a-box-26`
  and
  `sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/setup/bootstrap.sh)"`.
  The first one is needed for rc1 to rc3 and changes nothing on rc4 and rc5.
* **Munin mails administrator on each change of state**\
  Munin mails administrator@PRIMARY_HOSTNAME (from and to that address) on
  each change of state of a watched value: one mail when a value reaches
  warning or critical, one when it is back to ok. A value that is in
  warning or critical already is not mailed until its state changes;
  `/var/lib/munin/limits` lists the states. Make sure that address reaches
  someone (it is an alias of the first administrator by default). A
  setting to change the address or turn the alerts off is planned for rc7.
* **Dovecot lines in mail.log now use rsyslog's format (B85)**\
  Dovecot logs through syslog (B85); setup sets `log_path=syslog` and
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
* **Setup adds the spampd PID drop-in (B81)**\
  Setup adds the systemd drop-in
  `/etc/systemd/system/spampd.service.d/mailinabox-stale-pid.conf` (B81)
  and sets `pid /run/spampd.pid` in `/etc/spampd.cfg`. The in-place tool
  does not count this drop-in (nor Postfix's `mailinabox-stale-db.conf`)
  as a local extension.
* **Cron jobs during an update run are skipped**\
  Cron is paused while setup runs (B82): cron jobs that would fall into
  the minutes of an update run are skipped, not run later. The nightly job
  between 01:00 and 01:59 is not affected unless you update at that time.
* **Roundcube and Nextcloud show the fork's favicon**\
  After the update Roundcube and Nextcloud show the fork's favicon. A
  favicon that an administrator uploaded in Nextcloud and a replaced
  favicon of Roundcube's Elastic skin are kept. To keep the old favicons,
  put `FAVICON=off` into `/etc/mailinabox.conf` before the update.
* **First setup run rewrites Dovecot SSL settings once more (B74)**\
  The first setup run of this release writes the SSL settings of
  `/etc/dovecot/conf.d/10-ssl.conf` once more (B74). The commented copies
  that earlier runs added stay; they are only comments.
* **Setup removes cloud-init's old logrotate file (B75)**\
  On boxes upgraded in place to 26.04 with rc1 to rc5, setup removes
  cloud-init's old `/etc/logrotate.d/cloud-init` if it is unchanged, and
  logrotate works again (B75). A changed file is kept; then remove the
  duplicate entry by hand.
* **Read the SSH login notes before an in-place upgrade**\
  For an in-place upgrade, read "Logging in during the release upgrades" in
  README-fork.md ("In-place upgrade to 26.04") first: attach to the run
  before each release upgrade and keep the connection; if a new login
  fails, wait, do not reboot.

### Planned for rc7

* **Admin panel setting for Munin alerts**\
  An admin panel setting for Munin's alerts: to administrator@PRIMARY_HOSTNAME
  (the default), to another address, or off; warning and critical or only
  critical; a button that sends a test mail.
* **Shorter SSH outage during release upgrades**\
  A shorter SSH outage during the release upgrades, or at least a live
  note: for example a fallback sshd on another port while the SSH server is
  replaced (as do-release-upgrade offers when it runs interactively), and a
  message in the run when SSH logins work again.
* **Deterministic order of the OpenDKIM tables**\
  A deterministic order of the OpenDKIM tables (`KeyTable`,
  `SigningTable`), so that a setup run without changes leaves them alone.
* **Test log audit rule for a pam_systemd message at reboot**\
  A rule in `tests/fork/log-audit-allow.txt` for `(sd-pam)`'s
  "pam_systemd(systemd-user:session): Varlink call
  io.systemd.Login.ReleaseSession failed: io.systemd.Login.NoSuchSession"
  at a reboot, seen in one T5b run of rc6 (the test lab's own list
  accepted it there).
* **Full test matrix T1 to T5b and T6 before final release**\
  The full test matrix T1 to T5b again on the release head, and T6 (on the
  Internet: Let's Encrypt, delivery to other providers) before a final
  release.

## v78-r2604.0-rc5 (2026-10-24)

Fixes from the update of a copy of a production box from rc3 to rc4: Dovecot
stays enabled after the in-place upgrade (B67), no more phantom folders from
vacation replies (B66), cloud-init keeps the box's name in /etc/hosts (B68),
and the mailinabox and munin units are enabled by name (B69).

### Fixed

* **Sieve vacation replies no longer create Dovecot duplicate-database folders (B66)**\
  Dovecot: vacation replies and Sieve redirects no longer create the
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
* **In-place tool no longer leaves Dovecot disabled (B67)**\
  Tools: `tools/upgrade-in-place-to-2604.sh` left Dovecot disabled: it
  installs Dovecot 2.4 while the unit is masked, which the package cannot
  enable, and after the next reboot there was no IMAP, POP3 or delivery to
  the mailboxes. The tool now records which units are enabled before it
  masks them and enables them again when it unmasks them. Phase verify of
  both tools shows whether each service is enabled, enables a disabled one
  and fails on any other state; the in-place tool also reports units that
  were enabled before the upgrade and are disabled now (warning and
  `etc-report.txt`). Setup enables a disabled service before it restarts it
  (and nsd), so the next setup run heals a box upgraded with rc3 (B67).
* **cloud-init no longer restores the foreign 127.0.1.1 hosts line (B68)**\
  System: on machines where cloud-init writes `/etc/hosts` on every boot
  (`manage_etc_hosts`, e.g. hypervisors and the images of hosting providers),
  the 127.0.1.1 line with another machine's name that setup comments out
  came back after each reboot. Setup now also puts the box's name on the
  127.0.1.1 line of cloud-init's template
  (`/etc/cloud/templates/hosts.debian.tmpl`) and the same line into
  `/etc/hosts`. When an update of cloud-init changes the template, dpkg
  asks about it: keep the local version (B68).
* **`systemctl is-enabled` works for mailinabox and munin units (B69)**\
  Setup: `systemctl is-enabled mailinabox` and `munin` no longer fail
  with "Too many levels of symbolic links". Setup enabled the units by
  their path under `/lib`, which left a link in `/etc/systemd/system` to the
  same file; it now removes such a link and enables the units by name
  (B69).

### Changed

* **Smoke checks for enabled services and Sieve vacation folders**\
  Tests: smoke checks `services-enabled` (the services of Mail-in-a-Box are
  enabled, over `--ssh`) and `sieve-vacation-no-phantom-folders` (after the
  vacation reply, IMAP lists no folder of Dovecot's duplicate database).
* **README-fork.md documents harmless setup output and update steps**\
  Docs: README-fork.md has a new section "Setup output" with the lines of
  setup's output that look like errors but are harmless on 26.04
  (pollinate "Permission denied", Nextcloud's "No upgrade required", the
  SysV note of systemctl). "Updating the fork" says what to do right after
  an update (allowlist, the nightly job's new minute, enabled services) and
  how to remove the old release tags of rc1 to rc3 checkouts.

### Upgrade note

* **Boxes upgraded in place with rc3 have Dovecot disabled (B67)**\
  Boxes upgraded in place with rc3 have Dovecot disabled (B67): it runs,
  but does not start after a reboot. Check with `systemctl is-enabled
  dovecot`; until this release is installed, `sudo systemctl enable
  dovecot` fixes it. Setup of this release enables it by itself.
* **Adaptive banning and slow mail jails are on after the update**\
  Adaptive banning and the slow mail jails are on as soon as setup of rc4
  or later has finished; there is nothing to turn on. Put your own
  networks on the allowlist right after the update (System > Intrusion
  Protection, or `sudo /root/mailinabox/management/fail2ban_admin.py
  --allow 192.0.2.0/24`), see the upgrade note of rc4.
* **Setup picks a new random minute for the nightly job**\
  Every setup run picks a new random minute between 01:00 and 01:59 for
  the nightly backup and status checks (`/etc/cron.d/mailinabox-nightly`),
  as upstream does. Look it up before the next update or in-place upgrade:
  the in-place tool waits for a running backup before it stops mail, at
  most 2 hours.
* **Old release tags of rc1 to rc3 checkouts**\
  Checkouts of rc1 to rc3 keep the release tags of the fork's previous
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

* **Logo and favicon for the fork**\
  Logo and favicon for the fork: the source files are in `branding/` (CC0,
  with `branding/README.md` on colours and use). The control panel has a
  favicon and shows the icon next to the box name; setup copies the files to
  `/usr/local/lib/mailinabox/vendor/assets/branding/` (served as
  `/admin/assets/branding/`). On the web domains of the box, `/favicon.ico`
  falls back to the fork's icon when the web root has no `favicon.ico` of its
  own. The default page for new boxes (`conf/www_default.html`) shows the
  icon; an existing `index.html` stays as it is. The README header shows the
  wordmark.
* **In-place tool gets before and after hooks for operator services**\
  Tools: `tools/upgrade-in-place-to-2604.sh` has two more hook stages for
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
* **Postfix greylisting bypass list for chosen senders**\
  Postfix: senders listed in `/etc/postfix/greylist_bypass_senders` (an
  access(5) file of the administrator, e.g. `newsletter@example.com OK`)
  skip greylisting. If the file exists, setup runs postmap on it and puts
  `check_sender_access hash:/etc/postfix/greylist_bypass_senders` right before
  postgrey, with the quota check in front of both; without it the
  restrictions stay as upstream. Before, setup dropped such a rule added by
  hand on every run. To turn it off, delete the file and run setup (keep the
  `.db` until then). `tools/migrate-to-2604.sh` takes the file over from the
  old box before setup (not from a backup, which does not contain it).
* **Nextcloud sharing limited to the user's own mail domain**\
  Nextcloud: users only see and share with the accounts of their own mail
  domain (share dialog, contacts menu, system address book, calendar and team
  member search); members of the Nextcloud group `admin` with everyone.
  Each mail domain becomes a Nextcloud group (user_external `groupDomain`),
  `tools/nextcloud-share-scope.sh` sets the sharing options, puts existing
  users into their group and the admins into all of them; setup runs it, cron
  every 5 minutes. `NEXTCLOUD_SHARE_SCOPE=all` in `/etc/mailinabox.conf` keeps
  upstream's behaviour and puts back the sharing options from before. See
  README-fork.md for the limits.
* **Smoke check for Nextcloud share scope**\
  Tests: smoke check `nextcloud-share-scope` (sharee search across domains,
  system address book, admin view).
* **fail2ban adaptive intrusion protection and slow mail jails**\
  fail2ban: adaptive intrusion protection, on by default (README-fork.md,
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
* **Status checks report failed-login patterns from the mail log**\
  Status checks: a report of failed logins in the mail log of the last
  48 hours: accounts that failed from 20 or more addresses within 24 hours
  (password spraying), addresses that keep failing for 12 hours or more
  without a single ban in that time (expired bans are read from fail2ban's
  database), and banned addresses that failed only as one or two existing
  accounts (probably an own device with an old password: allowlist it). Only
  existing accounts are named.
* **Management API calls for fail2ban**\
  Management API (admin): `GET /system/fail2ban` (jails, bans with time
  left), `GET`/`POST /system/fail2ban/settings`, `POST /system/fail2ban/unban`
  (one jail, or all jails including the ban history), `POST
  /system/fail2ban/unban-all` (one jail), `GET /system/fail2ban/report`.
* **Control panel page System > Intrusion Protection**\
  Control panel: new page System > Intrusion Protection. It lists the banned
  addresses (jails, time left; filter) and the jails with their counters,
  unbans an address in all jails or in one jail and empties a jail (with a
  confirmation), shows the failed-login report and edits the settings
  (adaptive banning and slow jails on/off with a confirmation before turning
  off, thresholds, allowlist, restore defaults). It shows the admin's own
  address (for IPv6 its /64) and offers to allowlist or unban it.
* **Smoke checks for the fail2ban admin pages and adaptive banning**\
  Tests: smoke checks `admin-fail2ban-status`, `admin-fail2ban-settings`,
  `admin-fail2ban-report`, `admin-fail2ban-filters` (fail2ban-regex with
  injected user names) and `admin-fail2ban-panel`, and in the opt-in fail2ban
  group `fail2ban-adaptive-toggle` (turning adaptive banning off reaches the
  running jails); `prepare-testenv.sh` puts the jump host on the allowlist.
  The ban checks of that group also accept a ban by the slow jails, which
  count the failures of all Dovecot (SMTP) protocols together and can ban
  the source before the fast jail does.
* **New public README, SECURITY.md and fork notes**\
  Docs: new public README.md (unofficial-fork notice, status, supported paths,
  credits, license); upstream's README is kept as README-upstream.md. New
  `.github/SECURITY.md` (GitHub private vulnerability reporting); fork notes
  in security.md, CODE_OF_CONDUCT.md and CONTRIBUTING.md.

### Changed

* **The fork is published on GitHub**\
  Project home: the fork is now published at
  https://github.com/LM1337/Mail-in-a-box-26. `setup/bootstrap.sh`,
  `tools/migrate-to-2604.sh` and `tools/upgrade-in-place-to-2604.sh` clone
  from there by default, and the
  curl commands in the documentation use
  `https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/...`.
* **Version check reads the fork's release tag from GitHub**\
  Status checks: the version check reads the latest release tag from the
  fork's `setup/bootstrap.sh` on GitHub, and the upgrade hint names this
  fork and its URL. A bootstrap.sh without a `TAG=` line now gives "could not
  be determined" instead of an error.
* **bootstrap.sh compares the checkout's origin case-insensitively**\
  Setup: `setup/bootstrap.sh` compares the checkout's origin with `SOURCE`
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
* **In-place tool checks out the release tag before setup**\
  Tools: `tools/upgrade-in-place-to-2604.sh` on a 26.04 box that already
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
* **Migration tool keeps other settings of /etc/mailinabox.conf**\
  Tools: `tools/migrate-to-2604.sh` keeps the other settings of an existing
  `/etc/mailinabox.conf` on the new machine (e.g. `FTS=off` or
  `NEXTCLOUD_SHARE_SCOPE=all`, set there after a rehearsal) when it writes
  the file again; before, the real run dropped them. Both tools pass `FTS`
  and `NEXTCLOUD_SHARE_SCOPE` from the environment into their tmux session.
* **Tools are executable and hint at `sudo tmux attach`**\
  Tools: `tools/upgrade-in-place-to-2604.sh` is executable in git, as its
  own hints assume. The help texts, the reboot hints and the migration's
  quick start say `sudo tmux attach -t ...`: the session belongs to root.
* **Installed box points to the fork instead of only upstream**\
  Branding: the installed box points to the fork instead of only to
  upstream: the Roundcube support link, the admin panel footer, the default web page (new
  boxes only) and the SMTP banner.
* **Test scripts no longer contain a particular test network**\
  Tests: `tests/fork` no longer contains addresses or host names of a
  particular test network. `prepare-testenv.sh` needs `JUMP_HOST`, `PEERS`,
  `BLOCK_V4` and `BLOCK_V6` (environment or `TESTENV_FILE`); `smoke.py` reads
  its env file from `MIAB_TEST_ENV` (default `tests/fork/credentials.env`,
  ignored by git) and the seed domains from `SEED2_DOMAIN`/`SEED3_DOMAIN`
  (default `seed2.example.net`/`seed3.example.net`), like `seed-legacy.sh`.
* **Verify phase reports Postfix restrictions that are gone**\
  Tools: phase verify of `tools/upgrade-in-place-to-2604.sh` and
  `tools/migrate-to-2604.sh` reports each item of an `smtpd_*_restrictions`
  parameter from before (of the old box) that is gone now ("Postfix
  restriction ... is gone: ...") as a failed check and at the top of
  `etc-report.txt`, not only as a changed line of `postconf -n`. A DNS list
  that only got return codes (upstream v68, `zen.spamhaus.org=127.0.0.[2..11]`)
  does not count as gone.
* **A running backup no longer stops the upgrade or migration start**\
  Tools: a Mail-in-a-Box backup that is running (e.g. the nightly one at
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
* **Tools run in tmux so a dropped SSH connection does not stop them**\
  Tools: `tools/upgrade-in-place-to-2604.sh` and `tools/migrate-to-2604.sh`
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

* **In-place tool stops mail before its fresh backup (B57)**\
  Tools: `tools/upgrade-in-place-to-2604.sh` stops mail (and masks the units)
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
* **Usage report counts Dovecot 2.4 logins again (B58)**\
  Management: the usage report (`mail_log.py`) counts IMAP, POP3 and
  ManageSieve logins again: Dovecot 2.4 logs them as "Logged in:", not
  "Login:" (B58).
* **Setup drops Postfix's `smtpd_tls_dh1024_param_file` (B59)**\
  Postfix: setup no longer sets `smtpd_tls_dh1024_param_file` and removes it
  from an existing main.cf. Postfix 3.10 warned on every `postconf` call that
  its support will be removed; the default uses the RFC 7919 FFDHE groups
  (B59).
* **Mail of cron jobs and root reaches the administrator (B60)**\
  System: mail of cron jobs and root reaches the administrator. Setup writes
  PRIMARY_HOSTNAME to `/etc/mailname` (Postfix's myorigin; a provider's image
  could leave its own name there, and such mail bounced daily), comments out
  a 127.0.1.1 line in `/etc/hosts` with another machine's name, makes
  root@PRIMARY_HOSTNAME an automatic alias to administrator@ and writes the
  automatic aliases at the end of every setup run. The Nextcloud cron jobs
  send their output to root instead of www-data (B60).
* **fail2ban submission filter can no longer ban third parties (B61)**\
  fail2ban: the `miab-postfix-submission` filter (jails `miab-postfix465`,
  `miab-postfix587`) is anchored. A client could put `[<ip>]: ` into the SASL
  user name, which Postfix logs after the client address, and get a third
  party banned (B61).
* **fail2ban management and Roundcube filters are anchored (B62)**\
  fail2ban: the filters `miab-management-daemon` (jails `miab-management`,
  `miab-slow-management`) and `miab-roundcube` (`miab-roundcube`,
  `miab-slow-roundcube`) are anchored. A client could put the control
  panel's failed-login text with a third party's address into an SMTP AUTH
  user name, which Postfix logs to /var/log/syslog as well, and get that
  address banned from the web ports (and through recidive from all); the
  Roundcube filter took the first ` from <ip>.` of the line, which could be
  part of the user name (B62).
* **Latest-version API answers 503 instead of 500 (B63)**\
  Management: the API call `system/latest-upstream-version` answers HTTP
  503 "The latest version could not be determined." instead of HTTP 500 with
  a traceback in the daemon log when the release cannot be looked up (B63).
* **Failed user database writes no longer keep it locked (B64)**\
  Management: a failed write to the user database (adding a user or alias
  that exists, changing the password, quota or privileges of an address
  that is no user, removing one that does not exist) no longer keeps
  `users.sqlite` locked. With Python 3.14 the connection stayed open with
  its transaction until the garbage collector ran, often for minutes, and
  every other change in the control panel failed with "database is locked"
  (HTTP 500) until then (B64).
* **Documented setup command works with sudo-rs (B65)**\
  Setup: the documented command is now
  `sudo bash -c "$(curl -fsSL .../setup/bootstrap.sh)"`. With upstream's
  `curl ... | sudo bash`, sudo-rs (the sudo of Ubuntu 26.04) stopped setup's
  first dialog box, and an interactive install or update hung without
  showing anything. bootstrap.sh run that way now stops before changing
  anything and prints the working command; with `NONINTERACTIVE=1`, as root
  or with sudo.ws the pipe still works (B65). The hints with
  `git remote set-url` start with `sudo`.

### Upgrade note

* **Boxes on rc1 to rc3 must point the checkout to GitHub**\
  Boxes on rc1 to rc3 were cloned from the fork's previous home. Point the
  checkout to GitHub once, then run the bootstrap command as usual:
  `sudo git -C /root/mailinabox remote set-url origin https://github.com/LM1337/Mail-in-a-box-26`
  (see "Updating the fork" in README-fork.md). Their status checks look for
  new releases at the previous home and may keep reporting the box as up to
  date until it runs rc4.
* **Slow mail jails start with an empty allowlist**\
  The slow mail jails are on after the upgrade, with an empty allowlist. On a
  box whose users sit behind one office address, put that network on the
  allowlist right after the upgrade (System > Intrusion Protection, or
  `sudo /root/mailinabox/management/fail2ban_admin.py --allow 192.0.2.0/24`).
  Before the upgrade, neither exists yet; `fail2ban: {allowlist:
  [192.0.2.0/24]}` in `$STORAGE_ROOT/settings.yaml` (usually
  `/home/user-data/settings.yaml`) has the same effect from the first setup
  run on. Without it, a single phone with an old password can get the
  office banned from the mail ports, for longer each time.
* **Nextcloud sharing limited to own mail domain by default**\
  Nextcloud sharing is limited to the own mail domain from this release on
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

* **In-place upgrade tool for 22.04 and 24.04 boxes**\
  Tools: `tools/upgrade-in-place-to-2604.sh` upgrades a box in place:
  22.04 → 24.04 → 26.04 or a release-upgraded 24.04 box → 26.04, then setup of
  this fork on the existing data. Detects local extensions, makes an encrypted
  system archive next to the backups, keeps mail off across reboots, continues
  on its own after each reboot, supports operator hooks
  (`/etc/mailinabox/upgrade-2604.d`), compares counts and fingerprints before
  and after, and removes leftovers of the old releases (`--cleanup-only`).
  See README-fork.md.
* **Dovecot full-text search with fts_xapian**\
  Dovecot: full-text search with fts_xapian (`95-mailinabox-fts.conf`, on by
  default, `FTS=off` in `/etc/mailinabox.conf`), a daily
  `doveadm fts optimize -A`. Hand-made 2.3 FTS files are replaced; existing
  Xapian indexes keep working.
* **Smoke check for full-text search**\
  Tests: smoke check `fts-search` (IMAP SEARCH BODY and `doveadm fts lookup`).

### Fixes for boxes upgraded in place

* **In-place boxes: Dovecot 2.3 setting names commented out (B51)**\
  Dovecot: Dovecot 2.3 setting names kept in 10-auth/10-ssl are commented out (B51).
* **In-place boxes: dovecot-antispam leftovers removed (B52)**\
  Spam: leftovers of the dovecot-antispam setup of older versions are removed (B52).
* **In-place boxes: Python venv rebuilt when it no longer runs (B53)**\
  Management: the Python venv is rebuilt when its interpreter no longer runs (B53).
* **In-place boxes: bootstrap.sh explains a checkout of another origin (B54)**\
  Setup: bootstrap.sh explains an existing checkout of another origin (B54).
* **In-place boxes: old PPA sources and keys removed (B55)**\
  System/apt: PPA sources and keys of earlier releases are removed; Launchpad builds of ppa:ondrej are moved back to Ubuntu packages (B55).
* **In-place boxes: a failing pollinate no longer stops setup (B56)**\
  System: a failing pollinate no longer stops setup (B56).

## v78-r2604.0-rc2 (2026-10-23)

Fixes from the review before rc2. Certified from the tag without manual
steps: fresh install (49/49 smoke checks) and migration from a v74 box
(54/54).

### Fixes

* **SSHFP records come from the host key sshd serves (B11, B34)**\
  DNS: SSHFP records come from the public key sshd actually serves. It is derived from the private host key, with `.pub` only as a fallback (B11). ECDSA P-384/P-521 keys map to algorithm 3 (B34).
* **Quota validation accepts ASCII digits only (B17)**\
  Mail: quota validation accepts ASCII digits only. Unicode digits such as a fullwidth `１０G` broke the user's Dovecot userdb lookup (B17, also in v78).
* **Z-Push no longer crashes on RTF bodies on PHP 8 (B31)**\
  Z-Push: `MBSTRING_OVERLOAD` is defined for `z_RTF` on PHP 8. CalDAV Sync requests with RTF bodies used to crash with HTTP 500 (B31, also in v78).
* **Migration tool hardening**\
  Tools: `migrate-to-2604.sh` hardening:
  * stopped units stay disabled across reboots;
  * backups are paused again after every rsync;
  * rollback is safe (backups paused, leftover backup runs ended, `virtual_transport` restored, zone restore and nsd reload separated);
  * the Nextcloud event and `occ status` checks are more accurate.
* **`prepare-testenv.sh` requires active ufw with deny rules**\
  Tests: `prepare-testenv.sh` fails unless ufw is active and the production deny rules are loaded in the kernel, whatever the caller's locale.

## v78-r2604.0-rc1 (2026-10-23)

First release of the fork: PR #2603 + v78 + the fixes below.

### New

* **Migration tool moves a box to a fresh 26.04 machine**\
  `tools/migrate-to-2604.sh` moves a box (upstream v68+ on Ubuntu 22.04, or a 24.04 in-place upgrade) to a fresh Ubuntu 26.04 machine in one command.
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
* **Seed data, smoke test and test-network scripts in `tests/fork/`**\
  `tests/fork/`: seed data for a legacy box (`seed-legacy.sh`), end-to-end smoke test (`smoke.py`) and test-network preparation (`prepare-testenv.sh`).

### Fixes

Setup and system
* **Bootstrap accepts Ubuntu 26.04 and installs from the fork (B05, B40)**\
  Bootstrap accepts Ubuntu 26.04 and installs from the fork (B05). The version status check compares against the fork's tag (B40).
* **`email_validator` is installed when missing (B21)**\
  `email_validator` is installed whenever it is missing for the address prompt (B21).
* **TLS uses MIAB's `dh2048.pem` again (B43)**\
  TLS: back to MIAB's `dh2048.pem` instead of generating 4096-bit parameters (B43).
* **Timezone check uses `/etc/localtime` (B44)**\
  The timezone check uses `/etc/localtime` (B44).
* **`wget_verify` picks the hash algorithm by length (B45, B46)**\
  `wget_verify` picks the hash algorithm by length and no longer overwrites the caller's variables (B45, B46).
* **sury PHP repository is pinned and its key checked (B25, B26, B27, …)**\
  sury PHP repository:
  * pinned to the packages Ubuntu 26.04 lacks (B25);
  * keyring checked against the key fingerprint (B26);
  * key no longer trusted globally (B27);
  * PHP packages it had already replaced move back to Ubuntu (B07).
* **unattended-upgrades covers sury and the duplicity PPA (B28)**\
  unattended-upgrades covers sury and the duplicity PPA (B28, also in v78).

Dovecot 2.4
* **Mail to aliases and catch-alls is no longer rejected by quota-status (B01)**\
  quota-status answers DUNNO, so mail to aliases, catch-alls and domain aliases is no longer rejected (B01).
* **Per-user quota fixes (B02, B38, B14, …)**\
  Per-user quota:
  * the limit comes from the userdb (`quota_storage_size`) (B02);
  * the maildir quota driver keeps the usage up to date (B38);
  * the grace is 10% of each user's quota again (B14);
  * `quota_status_toolarge` is set (B15).
* **User Sieve filters and vacation replies run again (B04)**\
  `$STORAGE_ROOT` is expanded in `99-local-sieve.conf`, so user filters and vacation replies run (B04).
* **Sieve redirects use the recipient as envelope sender (B03)**\
  Sieve redirects use the recipient as envelope sender (B03).
* **ManageSieve port 2000 closed, LMTP settings pinned (B39, B13)**\
  ManageSieve port 2000 is closed (B39). LMTP username format and sieve plugin are pinned in `99-local.conf` (B13).

Spam
* **IMAPSieve spam and ham learning runs (B06, B16, B47, …)**\
  IMAPSieve spam/ham learning runs:
  * LF line endings, enforced by `.gitattributes` (B06);
  * 120 s pipe timeout (B16);
  * no failed-pipe noise in the log (B47);
  * ham rules skip trash and spam moves (B22).
* **spampd runs DNSBL, URIBL, Pyzor and Razor checks (B24)**\
  spampd local-only mode is really off, so DNSBL, URIBL, Pyzor and Razor checks run (B24).
* **SpamAssassin rule updates run via a timer (B23, B48)**\
  SpamAssassin rule updates run via `spamassassin-maintenance.timer` (B23). The unused spamd is disabled (B48).

fail2ban
* **The dovecot fail2ban jail works with Dovecot 2.4 (B09, B08, B33)**\
  The dovecot jail reads `mail.log` (B09). The filter matches Dovecot 2.4 login failures (B08) and IPv6 local addresses (B33, also in v78), and resists IP injection through the user name.

DNS
* **SSHFP records keep IANA algorithm numbers and avoid ssh-keyscan (B12, B36, B35)**\
  SSHFP records:
  * keep the IANA algorithm numbers (B12);
  * are built from the host key files instead of `ssh-keyscan`, which OpenSSH 10's PerSourcePenalties throttled (B36);
  * no longer depend on sshd listening on IPv4 localhost (B35, also in v78).
* **nsd logs to syslog only (B37)**\
  nsd logs to syslog only (B37, also in v78).

Web, Nextcloud, Roundcube, Z-Push
* **nginx serves Nextcloud `.mjs` modules and Roundcube 1.7 assets (B10, B50)**\
  nginx serves Nextcloud `.mjs` ES modules as JavaScript, so the Contacts app loads (B10). Roundcube 1.7 `static.php/<path>` assets get a proper PATH_INFO split (B50).
* **Nextcloud upgrade failure handling and opcache settings (B19, B42)**\
  Nextcloud:
  * `occ upgrade` failure handling works under `set -e` (B19, also in v78);
  * opcache settings also apply to PHP-FPM (B42).
* **Webmail CardDAV preset uses carddav 5.x keys (B20)**\
  Webmail: the CardDAV preset uses the carddav 5.x keys (`discovery_url`, `preemptive_basic_auth`) (B20).
* **Z-Push autodiscover no longer crashes with HTTP 500 (B32)**\
  Z-Push: `DAV_SSL_VERIFY` is defined for autodiscover. Z-Push 2.7.7 crashed with HTTP 500 (B32, also in v78).

Management and tools
* **`mail_log.py` parses RFC 3339 timestamps (B18)**\
  `mail_log.py` parses RFC 3339 rsyslog timestamps (B18).
* **`daemon.py` no longer returns inside `finally` in `/logout` (B41)**\
  `daemon.py` no longer has a `return` inside `finally` in `/logout` (B41).
* **`ssl_certificates.py` uses timezone-aware certificate dates**\
  `ssl_certificates.py` uses the timezone-aware `not_valid_*_utc` properties (cryptography >= 42) and an aware UTC "now". It is a separate `fix(ssl)` commit, so it can be reverted without touching the version bump.
* **`owncloud-restore.sh` refuses unusable backups (B30, B29, B49)**\
  `owncloud-restore.sh`:
  * refuses backups without application code (B30, also in v78);
  * refuses code that cannot run on PHP 8.5 (B29);
  * uses a defined PHP version (B49).
* **Comment explains Postfix's harmless "no SASL support" warning**\
  Postfix: a comment explains the harmless "no SASL support" warning on port 25.

### Setup and supply chain

* **`wget_verify` picks the hash by length; all pins are SHA256**\
  `wget_verify` picks the hash algorithm by length (64 hex = SHA256,
  128 = SHA512, 40 = SHA1 kept for compatibility). Every active pin is now
  SHA256 and was checked against the upstream checksum where one is
  published (Nextcloud `.sha256`, GitHub release digest, roundcube.net).
* **Nextcloud upgrade chain starts at Nextcloud 26**\
  The Nextcloud upgrade chain starts at Nextcloud 26. Installs with
  Nextcloud 20-25 skip the migration with a message (they need PHP <= 8.1).
* **packages.sury.org is pinned and its keyring checked**\
  packages.sury.org is pinned to what Ubuntu 26.04 lacks (php-common,
  php8.2, php8.2-*, php8.5-imap); its keyring is checked against key
  `15058500A0235D97F5D10063B188E2B695BD4743` and no longer trusted globally.
* **Management venv is recreated when system Python changes**\
  The management venv is recreated when the system Python version changes.
* **html5_notifier icon works with Roundcube 1.7**\
  The html5_notifier icon is resolved through `rcmail.assets_path()` so it
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

* **Scope exceptions of the version-update series**\
  Scope exceptions of the version-update series (intended, not drift):
  * `management/ssl_certificates.py` is outside the version-pin file set.
    Its change was first part of the cryptography bump and now sits in its
    own `fix(ssl)` commit. Not required by cryptography 50 (the naive
    `not_valid_before`/`not_valid_after` still exist there and only warn).
  * `setup/management.sh`: besides the pip/venv lines, the jQuery and
    Bootstrap pin lines changed. Those pins are defined only there.
  * `management/templates/login.html`: besides the asset pin, `$.trim(x)`
    became `String(x || '').trim()` (same behaviour; `$.trim` is deprecated
    in jQuery 3.5+).
* **Verification of the sury apt pin on a fresh 26.04 VM**\
  The sury apt pin (`/etc/apt/preferences.d/mailinabox-sury-php`) was
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
