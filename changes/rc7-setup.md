# rc7 fragment: setup

Entries of the setup strand for CHANGELOG-fork.md ("Unreleased") and
BUGS-fork.md, to be merged into them when the strands come together.

## CHANGELOG-fork.md

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
  management daemon's web update already reloaded.

### New

* Setup marks its start and end in the journal ("Mail-in-a-Box setup
  started", "Mail-in-a-Box setup ended (exit code N)", identifier
  `mailinabox-setup`). `tests/fork/log-audit.sh` prefixes what the box logs
  in between with `[setup]` (outside the phases of an in-place upgrade),
  and allowlist rules that start with `^\[setup\]` accept a class only
  there: connections that setup's restarts of the services cut are normal
  during setup and a finding at any other time. The report names the setup
  runs (`setup_runs` in the JSON report).
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
  `/tmp`. setup/start.sh wrote the settings of `/etc/mailinabox.conf` to
  `/tmp/mailinabox.prev.conf` and sourced that file; when a file of that
  name already existed (any local user can create one), the write failed and
  setup sourced the other user's file. It now reads the settings through a
  pipe (B96).
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
* OpenDKIM: the `KeyTable` and `SigningTable` are written in a fixed
  (sorted) order. The domains came from a Python set, whose order changes
  with every process, so with more than one mail domain each setup run (the
  management daemon, which writes them, starts anew in every run) and the
  first DNS update after a reboot rewrote both tables and restarted
  OpenDKIM once more, although nothing had changed. Mail sent in the moment
  of a restart goes out without a DKIM signature (Postfix has
  `milter_default_action=accept`) (B95).
* Nextcloud/Z-Push: ActiveSync syncs the address book of new users again.
  Nextcloud 34 puts an example contact into each new address book under the
  name `default`, without the `.vcf` that Z-Push's CardDAV backend adds when
  it fetches a contact; the Sync of the contacts folder then failed with a
  PHP error (HTTP 500), so no contact reached the phone. Setup turns the
  example contact off (`dav` `enableDefaultContact`). Users created before
  keep their example contact: delete it in Nextcloud's Contacts (it is
  marked "This is an example contact"), and the address book syncs (B99).

## BUGS-fork.md

### B95

**The OpenDKIM tables are rewritten in another order, and OpenDKIM restarted, without a change** (low, Mail)

* **Symptom:** On a box with more than one mail domain, each run of setup and the first DNS update after each start of the management daemon (e.g. after a reboot) rewrite `/etc/opendkim/KeyTable` and `/etc/opendkim/SigningTable` with the same lines in another order and restart OpenDKIM, although no domain changed; in a setup run that is a second restart after the one of setup/dkim.sh. A comparison of `/etc` before and after an update shows both files as changed, and a mail sent in the moment of a restart goes out without a DKIM signature (Postfix passes mail on when a milter does not answer, `milter_default_action=accept`), so it can fail DMARC at the receiver.
* **Cause:** `write_opendkim_tables()` in `management/dns_update.py` writes one line per domain in the order of `get_mail_domains()`, a Python set. The order of a set of strings depends on the hash seed, which Python chooses at random for every process (here: every start of the management daemon), so the content differs from run to run and the "did the file change" check sees a change.
* **Fix:** The domains are sorted before the tables are written. The patterns `*@domain` never overlap (a domain contains no "@"), so the order does not change which key signs a mail. The first run with the fix writes the tables once more in sorted order; from then on they only change when the domains do.
* **Affects:** v78 yes, PR #2603 yes. Origin: Upstream.
* **Evidence:** rc6 T5b: a second update run changed the order of both tables (noted in B74). The same set of four domains printed in four different orders with `PYTHONHASHSEED` 1 to 4. rc7, on a fresh test box with six mail domains: two setup runs after the install left both tables byte-identical (SHA-256), and OpenDKIM was restarted once per run (by setup/dkim.sh), not by the DNS update.
* **Found by:** update test; **commit:** see `git log --grep B95`; **fixed in:** v78-r2604.0-rc7

### B96

**Setup sources a file in /tmp that another local user can put there: local root** (critical, Setup)

* **Symptom:** A local user without privileges (a shell account on the box, or a service account that can write to `/tmp`) creates `/tmp/mailinabox.prev.conf` with shell commands. The next time the admin runs setup on the box (`sudo mailinabox`, an update with `setup/bootstrap.sh`, the upgrade and migration tools), setup runs these commands as root. Setup prints "/tmp/mailinabox.prev.conf: Permission denied" and goes on as usual.
* **Cause:** setup/start.sh copied `/etc/mailinabox.conf` with a `DEFAULT_` prefix to `/tmp/mailinabox.prev.conf`, sourced that file and removed it. `/tmp` is writable by everyone. On Ubuntu (`fs.protected_regular = 2`) root may not open another user's file in a sticky directory for writing, so the copy fails, and the `source` that follows reads the other user's file. Without that protection root would overwrite the file, which still belongs to the other user, who could change it before the `source`.
* **Fix:** setup reads the settings through a pipe (`source <(sed s/^/DEFAULT_/ /etc/mailinabox.conf)`); no file is written.
* **Affects:** v78 yes, PR #2603 yes. Origin: Upstream. Only boxes with a local user or service that an attacker controls; the first install (no `/etc/mailinabox.conf` yet) does not read the file.
* **Evidence:** On a fresh 26.04 test box, an unprivileged user wrote `id > /root/b96-proof.txt` into `/tmp/mailinabox.prev.conf`; the three lines of setup/start.sh, run with sudo, printed "Permission denied" and wrote `uid=0(root)` into `/root/b96-proof.txt`, then removed the user's file.
* **Found by:** rc7 review; **commit:** see `git log --grep B96`; **fixed in:** v78-r2604.0-rc7

### B97

**Setup downloads and unpacks code under fixed names in /tmp** (high, Setup)

* **Symptom:** None in normal use. A local user without privileges who watches `/tmp` (inotify) can create a directory under the name that setup is about to use. For Z-Push, setup removes `/tmp/z-push` and then unpacks the release into it; a directory of the other user's own created in between receives the unpacked files, and its owner can replace `Z-Push-*/src` before setup moves it to `/usr/local/lib/z-push`, whose `z-push-admin.php` setup then runs as root. The Roundcube plugins (`git_clone`, `/tmp/git-clone-PID`) work the same way, with code that runs as www-data. The other names (`/tmp/nextcloud.zip`, `contacts.tgz`, `calendar.tgz`, `user_external.tgz`, `roundcube.tgz`, `carddav.tar.gz`, `bootstrap.zip`, `ssl_cert_sign_req-PID.csr`, and `postgrey_whitelist_clients` of the daily cron job) only let the other user make setup fail: root may not write into their file (`fs.protected_regular`) or follow their link (`fs.protected_symlinks`).
* **Cause:** setup/zpush.sh, setup/nextcloud.sh, setup/webmail.sh, setup/management.sh, setup/ssl.sh, `git_clone` in setup/functions.sh and the cron job written by setup/mail-postfix.sh download, unpack and move files as root by fixed or predictable paths in `/tmp`, which everyone can write.
* **Fix:** Each of them uses a directory of root's own from `mktemp -d` (mode 0700, random name) and removes it afterwards. `git_clone` clones into a subdirectory of it, so the plugin directory keeps its usual mode.
* **Affects:** v78 yes, PR #2603 yes. Origin: Upstream. Only during an install or update of the component (a new version), and only with a local user or service that an attacker controls.
* **Evidence:** From reading the code; the race was not run. A fresh install of the fix on a 26.04 test box unpacked all components (smoke test), and no `mailinabox`, `z-push`, `git-clone`, `.zip` or `.tgz` entry was left in `/tmp`.
* **Found by:** rc7 review; **commit:** see `git log --grep B97`; **fixed in:** v78-r2604.0-rc7

### B98

**DNSSEC: the keys are copied to /tmp under their own names for signing** (medium, DNS)

* **Symptom:** A local user without privileges creates files named like the box's DNSSEC keys in `/tmp` (`K<domain>.+<algorithm>+<key tag>.private` and `.key`; domain, algorithm and key tag are in the public DNSKEY records). From then on each DNS update of that zone fails with "Permission denied" (`fs.protected_regular`), in setup and in the management daemon, and the zone is no longer signed again; its signatures expire 30 days after the last signing, and resolvers that validate DNSSEC then reject the domain. On a system without `fs.protected_regular` root writes the private key into the other user's file instead.
* **Cause:** `sign_zone()` in `management/dns_update.py` wrote a copy of each key with the real domain name to `'/tmp/' + key name` (with umask 077, but by a fixed path in a directory that everyone can write) and removed the copies after signing.
* **Fix:** The copies go into a `tempfile.TemporaryDirectory()` (mode 0700, random name), which is removed after signing, also when signing fails.
* **Affects:** v78 yes, PR #2603 yes. Origin: Upstream. Only boxes with a local user or service that an attacker controls.
* **Evidence:** From reading the code. On a fresh 26.04 test box with the fix, setup signed the zones (`.signed` files and DS records written), and no key file was left in `/tmp`.
* **Found by:** rc7 review; **commit:** see `git log --grep B98`; **fixed in:** v78-r2604.0-rc7

### B99

**ActiveSync cannot sync the address book of new users: Nextcloud's example contact breaks Z-Push** (high, Z-Push)

* **Symptom:** A phone that syncs a new user's contacts over ActiveSync gets HTTP 500 for the Sync of the address book, every time, and shows no contacts. `/var/log/z-push/z-push-error.log`: "Attempt to read property "vcard" on null" and "Fatal error: /usr/local/lib/z-push/backend/carddav/carddav.php:484 - Uncaught Error: Call to a member function __toString() on null" (from `BackendCardDAV->GetMessage()`). Mail and calendar sync are not affected.
* **Cause:** Since Nextcloud 30 the dav app writes an example contact into the default address book of each new user, with the card name `default` (`ExampleContactService::createDefaultContact()`). Z-Push's CardDAV client (`include/z_carddav.php`, `get_xml_vcard()`) appends `.vcf` to every card it fetches, so it asks for `default.vcf`, gets an empty answer, and `GetMessage()` dereferences the missing card.
* **Fix:** setup/nextcloud.sh sets `occ config:app:set dav enableDefaultContact --value false --type boolean`, so new users get no example contact. Example contacts of users created before stay (setup does not delete user data); deleting the example contact in Nextcloud's Contacts makes their address book sync.
* **Affects:** v78 no (Nextcloud 27), PR #2603 yes (Nextcloud 34). Origin: PR #2603.
* **Evidence:** rc7 setup strand, fresh 26.04 test box: a minimal ActiveSync 14.0 client (Provision, FolderSync, Sync, Ping) for the admin, whose address book held only Nextcloud's `default` card, got HTTP 500 for the second Sync of the contacts folder with the errors above. With the setting, a user created afterwards had no example contact; Sync answered 200 (status 1) and a Ping on the contacts folder ran its 20 s heartbeat and ended with status 1, no new line in the error log. The smoke test checks only `OPTIONS` of ActiveSync.
* **Found by:** rc7 setup tests (log audit of the restart window); **commit:** see `git log --grep B99`; **fixed in:** v78-r2604.0-rc7
