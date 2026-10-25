# rc7 fragment: panel-api

Entries for CHANGELOG-fork.md (section of rc7) and BUGS-fork.md, from the
branch `rc7/panel-api`. Bug IDs: B86 to B89; one more defect (the file
descriptor leak of the management daemon, last in this file) needs an ID
outside this range.

## CHANGELOG-fork.md

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
  secondary nameserver, the fail2ban writes). TESTING-fork.md describes it.
* Tests: `tests/fork/api-routes.py` (stdlib only, no box): every route of
  `management/daemon.py` (method and path, path parameters normalised) is
  documented in `api/mailinabox.yml` and every documented operation has a
  route; `smoke.py` calls or excludes each documented operation exactly
  once; the content types it expects are the documented ones. The control
  panel page and Munin's pages behind the session cookie are listed as not
  part of the API. Exit code 1 on drift.

### Fixed

* Munin: setup no longer changes the owner of what a symbolic link in
  `/var/log/munin` points to. It ran `chown munin` as root on the CGI logs
  there, in a directory that belongs to munin; now `chown -h` (B86).
* Settings: the daemon and setup no longer write `settings.yaml` through a
  symbolic link. `$STORAGE_ROOT` belongs to the storage user; root now
  writes a new file under a random name and renames it, and reads the file
  with `O_NOFOLLOW` (B87).
* API: `GET /mail/users/quota` for an address that is not a user answers
  400 with the message instead of 200 with the error inside the JSON, and
  `POST /mail/users/quota` without a quota answers 400 instead of 500
  (B88).
* Setup: setup no longer sources a file with a fixed name in `/tmp`. Each
  run after the first wrote the previous settings to
  `/tmp/mailinabox.prev.conf` and sourced it as root; another local user
  could create that file first and have setup run its commands as root
  (B89).
* Management: the daemon no longer runs out of file descriptors. Each API
  call left `users.sqlite` open (1 to about 90 times per call); after a few
  hundred calls the daemon reached its limit of 1024 open files and
  answered every request with 500 ("unable to open database file") until
  it was restarted. Connections now close with their cursor (B??).
* Tests: `admin-api-tmp-user-alias` removes the archived mailbox of its
  temporary user again (with `--ssh`), which every run left behind as an
  inactive account. `munin-alert-contact` passes when the admin panel
  turned the alerts off. `log-audit-allow.txt` accepts the two deliberate
  failed logins of `api-auth`.

### Upgrade note

* Munin's alerts: nothing to do. Without a setting `munin.conf` stays as in
  rc6 (alerts of warnings and critical values to administrator@). To change
  the address or turn them off: System > Munin Monitoring. Changes to
  `/etc/munin/munin.conf` by hand are overwritten (as before by setup, now
  also when the setting is saved); own Munin settings belong into
  `/etc/munin/munin-conf.d/`.

## BUGS-fork.md

Legend, "Found by", a new entry: *rc7 development*: the work on rc7, its
review and the dev checks of each change on a test box.

Overview rows:

| [B86](#b86) | medium | Munin | setup chowns through symbolic links in /var/log/munin (munin to root) | Upstream | yes | yes | rc7 |
| [B87](#b87) | low | Management | settings.yaml is written as root through a symbolic link in the storage root | Upstream | yes | yes | rc7 |
| [B88](#b88) | low | API | GET /mail/users/quota answers 200 with the error for a non-user, POST without quota 500 | Upstream | yes | yes | rc7 |
| [B89](#b89) | high | Setup | setup sources /tmp/mailinabox.prev.conf as root, a local user can plant it | Upstream | yes | yes | rc7 |
| [B??](#b) | high | Management | the daemon leaks a users.sqlite connection per database call and runs out of file descriptors | 26.04 change | no | yes | rc7 |

### B86

**setup changes the owner of what a link in /var/log/munin points to** (medium, Munin)

* **Symptom:** None in normal operation. A process running as user munin (munin-cron, the plugins it starts, the CGI graph script that the daemon runs as munin) can replace `/var/log/munin/munin-cgi-html.log` or `munin-cgi-graph.log` with a symbolic link to any file, for example `/etc/shadow`; at the next setup run (every update) that file belongs to munin.
* **Cause:** setup/munin.sh runs `chown munin` as root on these two files, in `/var/log/munin`, a directory that belongs to munin (`munin:adm 0755`). chown follows symbolic links, and `fs.protected_symlinks` does not cover this directory (not world-writable and sticky).
* **Fix:** `chown -h`: the owner of a link itself changes, never that of its target. A hard link to another user's file cannot be made there (`fs.protected_hardlinks`).
* **Affects:** v78 yes, PR #2603 yes, the fork up to rc6. Origin: Upstream (the same lines in v78).
* **Evidence:** from reading the code, and the owners on a fresh rc6 test box (`/var/log/munin` munin:adm 0755, `fs.protected_symlinks = 1`, `fs.protected_hardlinks = 1`). The escalation was not carried out. Setup with the fix on that box: exit 0, both logs `munin:adm 0640` as before.
* **Found by:** rc7 development; **commit:** see `git log --grep B86`; **fixed in:** v78-r2604.0-rc7

### B87

**settings.yaml is written as root through a symbolic link** (low, Management)

* **Symptom:** None in normal operation. Whoever can write the storage root (`$STORAGE_ROOT`, owned by the storage user `user-data`) can put a symbolic link at `settings.yaml`; the next change of a panel setting (privacy, intrusion protection, Munin's alerts) or setup then overwrites the link's target as root with the settings.
* **Cause:** `utils.write_settings()` opened `$STORAGE_ROOT/settings.yaml` with `open(path, "w")`, which follows links; `load_settings()` read through a link as well.
* **Fix:** write_settings() writes a new file under a random name in the same directory (`mkstemp`, `O_EXCL`, never through a link), keeps the mode of the old file (0600 for a new one) and renames it over the old file; load_settings() opens it with `O_NOFOLLOW` (a link reads as no settings).
* **Affects:** v78 yes, PR #2603 yes, the fork up to rc6. Origin: Upstream. Low: nothing of Mail-in-a-Box runs as the storage user.
* **Evidence:** from reading the code and the owners on a test box (`/home/user-data` user-data 0755, `settings.yaml` root 0600). With the fix on that box: settings saved through the panel API in all modes of Munin's alerts, the file stays root 0600, and the setting back to the default removes the key.
* **Found by:** rc7 development; **commit:** see `git log --grep B87`; **fixed in:** v78-r2604.0-rc7

### B88

**The quota API answers a non-user with 200 and a missing quota with 500** (low, API)

* **Symptom:** `GET /admin/mail/users/quota?email=<not a user>` answers 200 with `{"email": "...", "quota": ["That's not a user (...).", 400]}`. `POST /admin/mail/users/quota` without the field `quota` answers 500.
* **Cause:** get_mail_quota() returns an error tuple for a non-user, and the JSON branch of the view put it into the answer (only the text branch, `text=1`, returned it as the response). The POST view passed `request.form.get('quota')`, None when missing, to validate_quota(), which calls `.strip()`.
* **Fix:** the GET view returns the error tuple (400); the POST view passes an empty string, which validate_quota() refuses with "No quota provided." (400).
* **Affects:** v78 yes, PR #2603 yes, the fork up to rc6. Origin: Upstream.
* **Evidence:** found while documenting the endpoint for `tests/fork/api-routes.py`. With the fix on a test box: `api-write-roundtrip` gets 400 for the quota of a non-user, for `quota=1.5G` and for a missing quota, and 200 for `1G`.
* **Found by:** rc7 development; **commit:** see `git log --grep B88`; **fixed in:** v78-r2604.0-rc7

### B89

**setup sources a file with a fixed name in /tmp as root** (high, Setup)

* **Symptom:** None in normal operation. A local user, or a service account such as www-data after a hole in a web application, can create `/tmp/mailinabox.prev.conf` with commands of its own; the next setup run (every update, `sudo mailinabox`) runs them as root.
* **Cause:** On every run after the first, setup/start.sh wrote `/etc/mailinabox.conf` with the prefix DEFAULT_ to `/tmp/mailinabox.prev.conf`, sourced that file and removed it. With `fs.protected_regular` (Ubuntu's default) root's write into another user's file in the sticky `/tmp` fails, the `cat` fails, and setup sources the other user's file; without that protection the user could change the file between the write and the `source`.
* **Fix:** setup sources the output of `sed` directly (process substitution), no file.
* **Affects:** v78 yes, PR #2603 yes, the fork up to rc6. Origin: Upstream.
* **Evidence:** from reading the code and `fs.protected_regular = 2` on a 26.04 test box; the escalation was not carried out. Setup with the fix on that box (twice, update runs from the same version): exit 0, the previous answers used (no dialog with `NONINTERACTIVE=1` and the values of `/etc/mailinabox.conf`).
* **Found by:** rc7 development; **commit:** see `git log --grep B89`; **fixed in:** v78-r2604.0-rc7

### B??

**The management daemon leaks a users.sqlite connection per database call and runs out of file descriptors** (high, Management)

* **Symptom:** After a few hundred API calls (the control panel, the status checks of the panel, scripts) the management daemon answers every request with 500; its journal shows `sqlite3.OperationalError: unable to open database file`. A restart of `mailinabox.service` helps until the next few hundred calls.
* **Cause:** `mailconfig.open_database()` never closes the connection it opens; most callers only keep the cursor. Since Python 3.11 a sqlite3 connection is only freed by the cyclic garbage collector, which rarely gets to them in the daemon: each call left `users.sqlite` open, from 1 time (any authenticated GET, through the password check) to about 90 times (`/ssl/status`). The gunicorn worker has a limit of 1024 open files.
* **Fix:** open_database() returns a cursor class that closes its connection when the cursor is freed, which is when the calling function returns (the cursor is in no reference cycle; all callers keep cursor and connection in local variables). An uncommitted transaction is rolled back then, as the garbage collector did before.
* **Affects:** v78 no (Python 3.10 on 22.04 freed the connections by reference counting), PR #2603 yes, the fork up to rc6. Origin: 26.04 change (Python 3.14).
* **Evidence:** fresh-install test box (Python 3.14): the worker held 1013 descriptors of `users.sqlite` after the panel checks and one API smoke run, and the round trip failed with 500 on `users/remove`. Per endpoint, 5 calls each: +7 descriptors for `/system/version`, +20 `/mail/users`, +55 `/dns/zones`, +185 `/web/domains`, +190 `/dns/dump`, +433 `/ssl/status`. With the fix the same 15 endpoints left +0, and after the full `--only api` and `--only admin` runs the workers held 0 descriptors of `users.sqlite`.
* **Found by:** rc7 development (the new smoke group `api`); **commit:** `093118d` "close users.sqlite with its cursor"; **fixed in:** v78-r2604.0-rc7
