# Bugs fixed in the Ubuntu 26.04 fork

Every bug this fork fixes compared with Mail-in-a-Box v78 (the last official
release, Ubuntu 22.04) and with upstream PR #2603 (writeDavid's Ubuntu 26.04 port,
head `c6118db`, the base of this fork). The release notes are in
[CHANGELOG-fork.md](CHANGELOG-fork.md).

Each entry was written from its commit and then checked a second time against the
code at `v78` and `c6118db`. Where a claim comes from reading the code and was not
reproduced on a box, the evidence line says so.

## Legend

* **Origin**
  * *Upstream*: the bug is already in v78 and shows on 22.04 boxes.
  * *PR #2603*: the port introduced it.
  * *26.04 change*: a package or OS change in 26.04 that the port did not handle.
  * *Fork*: introduced and fixed within this fork. B07, B100, B101, B103-B112, B114-B116, B118 and B119 never shipped in a tag (found in the development of the release that fixes them); B11, B54, B76, B77, B90 and B117 shipped in rc1, B57, B67, B73 and B102 in rc3, B68, B71, B72, B84 and B113 in rc4, B70 in rc5.
  * *latent*: the code is wrong, but nothing triggers it yet.
* **v78 / PR**: whether a v78 box on 22.04 or a box installed from the PR head is affected.
* **Severity**
  * *critical*: mail loss, a security hole, or setup fails.
  * *high*: a core feature is broken.
  * *medium*: a feature is degraded.
  * *low*: cosmetic issues, warnings, or edge cases.
* **Found by**
  * *initial review*: the first review of the PR (an internal, unpublished report; its findings are cited as "Befund" with their number).
  * *audit*: five code auditors, each finding confirmed by a verifier.
  * *late review*: a review before rc2.
  * *test run*: the T1/T2 smoke tests on VMs.
  * *in-place test*: T3, the in-place upgrade of a copy of a production box, and T4, the in-place upgrade of the 22.04 test box.
  * *production upgrade*: the in-place upgrade of a production box with rc3.
  * *production update*: the update of a production box from rc6 to rc7 (setup of the published tag, with phones and calendars syncing) and its analysis.
  * *update test*: the update of a copy of that production box from rc3 to a later release (rc4 to rc6; T5b in rc6), and the fresh rc4 test box.
  * *log audit*: `tests/fork/log-audit.sh` on the boxes of the certification runs of rc6 (T1 to T5b), each warning and error classified.
  * *rc7 development*: the work on the changes of rc7 and their checks on a test box (new smoke test groups, setup runs, the log audit of the restart window).
  * *rc7 certification*: the test matrix T1 to T5b on the release commit of rc7, with a test address on the peer box that answers the mail check and an rsync account there as the backup target.
  * *ActiveSync analysis*: the analysis of the ActiveSync errors after rc7 (HTTP 500 for contacts in the update test with client load, HTTP 504 in nginx's log of a production box) on a copy of that box at rc6 and at the fixed branch.
  * *rc7 review*: the review of rc7's code, of setup and of the tools against the fork's rule that root does no file operations by path in directories that another account may write (such as `/tmp`, `/var/log/<service>`, `$STORAGE_ROOT`).

## Summary

126 bugs: 2 critical, 19 high, 52 medium, 53 low. B51-B56 were found by the in-place upgrade test for rc3,
B57-B60 by the in-place upgrade of a production box with rc3, B61 while adding the adaptive fail2ban, B62 in the review of rc4, B63-B65 in the test runs of rc4, B66-B69 in the update test of rc4, B70-B72 in the in-place test T4 of rc5, B73 in the in-place test T3 of rc6, B74 and B75 in the update test T5b of rc6, B76-B78 in the migration test T2 of rc6, B79 in the repeated update test after T1 of rc6, B80-B84 by the log audit of the certification runs of rc6, B85 by the smoke test of the certification run of T5b, B86-B89, B91 and B99 in the development of rc7 (B91 by its new API smoke test, B99 in its setup tests), B90 and B96-B98 in the review of rc7 against the rule that root does no file operations by path in directories that another account may write, B95 from the update test T5b of rc6 (fixed in rc7), B100-B105 in the review of the merged rc7 (B102 in the in-place tool since rc3, the others in code new in rc7), B106-B114 in the certification runs T2 to T5b of rc7 (B113 in the migration tool since rc4, the others in code new in rc7), B115-B118 in the review of the fixes of those runs (B117 in the migration tool since rc1 and the in-place tool since rc3, the others in code new in rc7), B119 in the test runs after that review, B120-B122 at the update of a production box from rc6 to rc7, B123 in the review of their fixes (in setup since upstream), B124 in the update test with client load after that review, B125 by a user report from a production box (its backup page), B128 in the update test with client load (found there, its cause in the ActiveSync analysis on a copy of the production box), B129 in nginx's log of the production box after the update (its cause in that analysis), B130 in that analysis. B92-B94 are not used; B96 is the same bug as B89, found twice and counted once.

| Origin | Count |
|---|---|
| Upstream | 42 |
| PR #2603 | 29 |
| PR #2603 (latent) | 1 |
| 26.04 change | 20 |
| Fork | 34 |

43 of these bugs also affect v78 on Ubuntu 22.04, fully or partly (B13, B17, B19, B28, B30, B31, B32, B33, B34, B35, B37, B45, B49, B56, B58, B60, B61, B62, B63, B78, B79, B80, B82, B83, B85, B86, B87, B88, B89, B95, B97, B98, B120, B121, B122, B123, B124, B125, B126, B127, B128, B129, B130). They are candidates for
upstream pull requests, independent of the 26.04 port.

## Overview

| ID | Severity | Component | Bug | Origin | v78 | PR | Fixed in |
|---|---|---|---|---|---|---|---|
| [B01](#b01) | critical | Dovecot | quota-status policy rejects mail to aliases, catch-alls and domain aliases | PR #2603 | no | yes | rc1 |
| [B02](#b02) | high | Dovecot | Per-user mailbox quotas ignored on Dovecot 2.4 (userdb still returns quota_rule) | 26.04 change | no | yes | rc1 |
| [B03](#b03) | high | Dovecot | Sieve redirects keep the external sender as MAIL FROM and fail SPF | PR #2603 | no | yes | rc1 |
| [B04](#b04) | high | Dovecot | Sieve script paths keep literal $STORAGE_ROOT, so user filters and vacation replies do not run | PR #2603 | no | yes | rc1 |
| [B05](#b05) | high | Setup | bootstrap.sh rejects Ubuntu 26.04, curl installer aborts | PR #2603 | no | yes | rc1 |
| [B06](#b06) | high | Spam | IMAPSieve spam/ham learning never runs (CRLF shebang in sa-learn-*.sh) | PR #2603 | no | yes | rc1 |
| [B07](#b07) | high | System/apt | PHP 8.5 packages installed from deb.sury.org before the pin get no updates from any repository | Fork | no | no | rc1 |
| [B08](#b08) | high | fail2ban | dovecotimap filter does not match Dovecot 2.4 'Login aborted' lines | 26.04 change | no | yes | rc1 |
| [B09](#b09) | high | fail2ban | fail2ban dovecot jail reads the systemd journal instead of mail.log on 26.04 | 26.04 change | no | yes | rc1 |
| [B10](#b10) | high | nginx | Nextcloud .mjs ES modules served as application/octet-stream, Contacts web UI blank | PR #2603 | no | yes | rc1 |
| [B11](#b11) | medium | DNS | SSHFP records built from .pub files instead of the key sshd actually serves | Fork | no | no | rc2 |
| [B12](#b12) | medium | DNS | SSHFP records published with wrong algorithm numbers after DSA removal | PR #2603 | no | yes | rc1 |
| [B13](#b13) | medium | Dovecot | LMTP username format and sieve plugin lost if the package 20-lmtp.conf is restored | PR #2603 | partly | yes | rc1 |
| [B14](#b14) | medium | Dovecot | Quota grace is a fixed size on Dovecot 2.4 instead of 10% per user | PR #2603 | no | partly | rc1 |
| [B15](#b15) | medium | Dovecot | quota-status accepts messages larger than the whole quota (empty quota_status_toolarge on Dovecot 2.4.2) | PR #2603 (latent) | no | latent | rc1 |
| [B16](#b16) | medium | Dovecot | sa-learn can be killed by the 10s Sieve pipe timeout | PR #2603 | no | yes | rc1 |
| [B17](#b17) | medium | Management | Quota validation accepts non-ASCII Unicode digits, breaking the user's Dovecot userdb lookup | Upstream | yes | yes | rc2 |
| [B18](#b18) | medium | Management | mail_log.py ignores postfix/postgrey lines with RFC 3339 rsyslog timestamps | 26.04 change | no | yes | rc1 |
| [B19](#b19) | medium | Nextcloud | Failed occ upgrade aborts setup under set -e: no retry, Nextcloud stuck in maintenance mode, php-fpm left stopped | Upstream | yes | yes | rc1 |
| [B20](#b20) | medium | Roundcube | Roundcube CardDAV preset uses carddav 4.x keys, so no Nextcloud addressbook is set up | PR #2603 | no | yes | rc1 |
| [B21](#b21) | medium | Setup | Email prompt loops forever when dialog, python3 and pip3 are already installed (email_validator never installed) | PR #2603 | no | yes | rc1 |
| [B22](#b22) | medium | Spam | Ham learning fires for moves to "Deleted *", Trash subfolders and Spam<->Junk | PR #2603 | no | yes | rc1 |
| [B23](#b23) | medium | Spam | SpamAssassin rule updates never run on 26.04; setup aborts if /etc/default/spamd is missing | PR #2603 | no | yes | rc1 |
| [B24](#b24) | medium | Spam | spampd still runs in local-only mode (no DNSBL/URIBL/Pyzor/Razor/DKIM checks) | PR #2603 | no | yes | rc1 |
| [B25](#b25) | medium | System/apt | Unpinned sury repo replaces Ubuntu's PHP 8.5, libgd3 and php-common | PR #2603 | no | yes | rc1 |
| [B26](#b26) | medium | System/apt | sury keyring .deb installed without verifying the signing key | PR #2603 | no | yes | rc1 |
| [B27](#b27) | medium | System/apt | sury signing key trusted globally via /etc/apt/trusted.gpg.d | PR #2603 | no | yes | rc1 |
| [B28](#b28) | medium | System/apt | unattended-upgrades does not cover the third-party PHP and duplicity repositories | Upstream | yes | yes | rc1 |
| [B29](#b29) | medium | Tools | owncloud-restore.sh restores pre-upgrade-chain Nextcloud code that cannot run on PHP 8.5 | 26.04 change | no | yes | rc1 |
| [B30](#b30) | medium | Tools | owncloud-restore.sh wipes Nextcloud and reports "Done" when the backup has no application code | Upstream | yes | yes | rc1 |
| [B31](#b31) | medium | Z-Push | Z-Push CalDAV sync fails with HTTP 500 when a client sends an RTF body (undefined MBSTRING_OVERLOAD) | Upstream | yes | yes | rc2 |
| [B32](#b32) | medium | Z-Push | Z-Push autodiscover fails with HTTP 500: DAV_SSL_VERIFY undefined (Z-Push 2.7.7) | Upstream | yes | yes | rc1 |
| [B33](#b33) | medium | fail2ban | dovecotimap filter ignores login failures on the IPv6 local address | Upstream | yes | yes | rc1 |
| [B34](#b34) | low | DNS | No SSHFP record for ECDSA host keys on the P-384/P-521 curves | Upstream | partly | partly | rc2 |
| [B35](#b35) | low | DNS | No SSHFP records (PR) or failed DNS update (v78) when sshd does not listen on IPv4 localhost | Upstream | yes | yes | rc1 |
| [B36](#b36) | low | DNS | SSHFP records flap in and out of the signed zone because ssh-keyscan hits OpenSSH PerSourcePenalties | 26.04 change | no | yes | rc1 |
| [B37](#b37) | low | DNS | nsd cannot write /var/log/nsd.log; logrotate entry is dead | Upstream | yes | yes | rc1 |
| [B38](#b38) | low | Dovecot | Control panel mailbox usage not maintained: quota driver defaults to count, maildirsize never written | PR #2603 | no | yes | rc1 |
| [B39](#b39) | low | Dovecot | ManageSieve listens on deprecated port 2000 on all interfaces | 26.04 change | no | yes | rc1 |
| [B40](#b40) | low | Management | Version status check compares a 26.04 box against the 22.04 upstream tag | PR #2603 | no | yes | rc1 |
| [B41](#b41) | low | Management | daemon.py /logout uses return inside finally (SyntaxWarning on Python 3.14) | 26.04 change | no | yes | rc1 |
| [B42](#b42) | low | Nextcloud | Nextcloud opcache settings only reach PHP CLI, not PHP-FPM, on PHP 8.5 | PR #2603 | no | yes | rc1 |
| [B43](#b43) | low | Setup | Port switches DH parameters to a new dh4096.pem, adding minutes of generation on fresh installs and the first setup run on upgraded boxes | PR #2603 | no | yes | rc1 |
| [B44](#b44) | low | Setup | Timezone check relies on /etc/timezone, which 26.04's tzdata no longer writes | 26.04 change | no | yes | rc1 |
| [B45](#b45) | low | Setup | wget_verify only accepts SHA1, so pins cannot be checked against published upstream checksums | Upstream | yes | yes | rc1 |
| [B46](#b46) | low | Setup | wget_verify overwrites the caller's global URL/HASH/DEST variables | Upstream | no | no | rc1 |
| [B47](#b47) | low | Spam | Failed sa-learn runs are logged as failed Sieve pipe actions | PR #2603 | no | yes | rc1 |
| [B48](#b48) | low | Spam | Unused spamd daemon runs on 26.04 | 26.04 change | no | yes | rc1 |
| [B49](#b49) | low | Tools | owncloud-restore.sh uses undefined $PHP_VER for occ | Upstream | partly | partly | rc1 |
| [B50](#b50) | low | nginx | Roundcube 1.7 static.php assets rely on PHP-FPM cgi.fix_pathinfo (no PATH_INFO passed) | PR #2603 | no | yes | rc1 |
| [B51](#b51) | high | Dovecot | Dovecot 2.3 setting names kept in 10-auth.conf/10-ssl.conf stop Dovecot 2.4 on boxes upgraded in place | 26.04 change | no | yes | rc3 |
| [B52](#b52) | medium | Spam | dovecot-antispam leftovers (99-local-spampd.conf, package, sa-learn-pipe.sh) of older Mail-in-a-Box break Dovecot 2.4 | 26.04 change | no | yes | rc3 |
| [B53](#b53) | high | Management | Broken management venv is kept after a release upgrade, pip fails | PR #2603 | no | yes | rc3 |
| [B54](#b54) | low | Setup | bootstrap.sh fails with 'Update failed' over an upstream checkout | Fork | no | no | rc3 |
| [B55](#b55) | medium | System/apt | PPA sources and keys of earlier releases stay trusted; Launchpad sury builds are not moved back to Ubuntu | PR #2603 | no | yes | rc3 |
| [B56](#b56) | low | System | pollinate cache owned by root makes setup fail on boxes upgraded in place | Upstream | partly | partly | rc3 |
| [B57](#b57) | medium | Tools | In-place upgrade: mail accepted after the fresh backup of phase snapshot is missing from it | Fork | no | no | rc4 |
| [B58](#b58) | medium | Management | mail_log.py counts no IMAP/POP3 logins of Dovecot 2.4 ("Logged in:") | 26.04 change | partly | yes | rc4 |
| [B59](#b59) | low | Postfix | Postfix 3.10 warns on every postconf call about smtpd_tls_dh1024_param_file | 26.04 change | no | yes | rc4 |
| [B60](#b60) | medium | System | Mail of cron and root bounces: /etc/mailname keeps another name, root@PRIMARY_HOSTNAME does not exist | Upstream | yes | yes | rc4 |
| [B61](#b61) | medium | fail2ban | SMTP AUTH filter takes a host from the client's user name, so a client can get a third party banned | Upstream | yes | yes | rc4 |
| [B62](#b62) | medium | fail2ban | Control panel and Roundcube filters take a host from text written by a client, so a client can get a third party banned | Upstream | yes | yes | rc4 |
| [B63](#b63) | low | Management | API call system/latest-upstream-version fails with HTTP 500 and a traceback when the latest version cannot be determined | Upstream | yes | yes | rc4 |
| [B64](#b64) | medium | Management | A failed write to users.sqlite keeps the database locked until garbage collection, other control panel changes fail | 26.04 change | no | yes | rc4 |
| [B65](#b65) | high | Setup | 'curl ... \| sudo bash' hangs at setup's first dialog box: sudo-rs stops it | 26.04 change | no | yes | rc4 |
| [B66](#b66) | medium | Dovecot | Vacation replies and redirects create the folders "dovecot", "dovecot.lda-dupes" and "dovecot.lda-dupes.locks" | 26.04 change | no | yes | rc5 |
| [B67](#b67) | high | Tools | In-place upgrade leaves Dovecot disabled: no IMAP, POP3 or mail delivery after the next reboot | Fork | no | no | rc5 |
| [B68](#b68) | low | System | cloud-init puts the 127.0.1.1 line with another machine's name back into /etc/hosts on every boot | Fork | no | no | rc5 |
| [B69](#b69) | low | Setup | systemctl is-enabled mailinabox and munin fail with "Too many levels of symbolic links" | PR #2603 | no | yes | rc5 |
| [B70](#b70) | low | Tools | In-place upgrade from 22.04 warns that ssh.service is disabled and advises to enable it, although ssh.socket starts it | Fork | no | no | rc6 |
| [B71](#b71) | low | Tools | The terminal attached to the tool's tmux session shows nothing; through "curl \| sudo bash" it is not attached at all | Fork | no | no | rc6 |
| [B72](#b72) | low | Tools | After the last reboot of the in-place upgrade the tmux window waits for Enter forever | Fork | no | no | rc6 |
| [B73](#b73) | low | Tools | During the release upgrade to 26.04 "tmux attach" cannot reach the in-place upgrade until the reboot, although the tool advises it | Fork | no | no | rc6 |
| [B74](#b74) | low | Dovecot | Every setup run adds another commented copy of each SSL setting to 10-ssl.conf | PR #2603 | no | yes | rc6 |
| [B75](#b75) | low | System | logrotate.service fails every day on boxes upgraded in place to 26.04: cloud-init's old logrotate file stays | 26.04 change | no | no | rc6 |
| [B76](#b76) | low | Tools | The migration tool's Spamhaus checks follow the resolver's search domain and can report a wildcard address | Fork | no | no | rc6 |
| [B77](#b77) | low | Tools | "migrate-to-2604.sh --check --skip-network-checks" still lists the skipped network checks as blockers and exits 1 | Fork | no | no | rc6 |
| [B78](#b78) | low | Postfix | After a Postfix restart at the wrong moment, every start of Postfix delays the first SMTP greetings by 100 seconds | Upstream | yes | yes | rc6 |
| [B79](#b79) | low | Setup | setup stops with "Could not get lock" when apt-daily or unattended-upgrades runs at the same time | Upstream | yes | yes | rc6 |
| [B80](#b80) | medium | Munin | Munin never sends its alerts: no contact is defined, and there is no "mail" command | Upstream | yes | yes | rc6 |
| [B81](#b81) | low | Spam | spampd cannot remove its PID file when it stops, a stale one stays in /run | 26.04 change | no | yes | rc6 |
| [B82](#b82) | low | Setup | Cron jobs run while setup runs; their mail to root bounces before the root alias exists | Upstream | yes | yes | rc6 |
| [B83](#b83) | low | DNS | nsd keeps its old listen addresses and logging after setup changed nsd.conf | Upstream | yes | yes | rc6 |
| [B84](#b84) | low | Tools | On 22.04 systemd complains about the tools' tmux scope at every daemon-reload | Fork | no | no | rc6 |
| [B85](#b85) | medium | Dovecot | After the weekly rotation of mail.log Dovecot writes into mail.log.1, and fail2ban's Dovecot jails see no failed login | Upstream | yes | yes | rc6 |
| [B86](#b86) | medium | Munin | setup chowns through symbolic links in /var/log/munin (munin to root) | Upstream | yes | yes | rc7 |
| [B87](#b87) | low | Management | settings.yaml is written as root through a symbolic link in the storage root | Upstream | yes | yes | rc7 |
| [B88](#b88) | low | API | GET /mail/users/quota answers 200 with the error for a non-user, POST without quota 500 | Upstream | yes | yes | rc7 |
| [B89](#b89) | critical | Setup | setup sources /tmp/mailinabox.prev.conf as root, a local user can plant it (local root) | Upstream | yes | yes | rc7 |
| [B90](#b90) | low | Tools | The in-place tool copies the encrypted system archive as root through the user-data account's directory | Fork | no | no | rc7 |
| [B91](#b91) | high | Management | The daemon leaks a users.sqlite connection per database call and runs out of file descriptors | 26.04 change | no | yes | rc7 |
| [B95](#b95) | low | Mail | The OpenDKIM tables are rewritten in another order, and OpenDKIM restarted, without a change | Upstream | yes | yes | rc7 |
| [B96](#b96) | - | Setup | Duplicate of B89 (found twice), not counted | Upstream | yes | yes | rc7 |
| [B97](#b97) | high | Setup | Setup downloads and unpacks code under fixed names in /tmp | Upstream | yes | yes | rc7 |
| [B98](#b98) | medium | DNS | DNSSEC: the keys are copied to /tmp under their own names for signing | Upstream | yes | yes | rc7 |
| [B99](#b99) | high | Z-Push | ActiveSync cannot sync the address book of new users: Nextcloud's example contact breaks Z-Push | PR #2603 | no | yes | rc7 |
| [B100](#b100) | high | Tools | The fallback SSH server of the in-place tool never starts on a box without the group admin | Fork | no | no | rc7 |
| [B101](#b101) | medium | Tools | The fallback SSH server of the in-place tool logs in with a key alone where sshd asks for more, and listens on all addresses | Fork | no | no | rc7 |
| [B102](#b102) | low | Tools | The in-place tool passes the host of an rsync backup target to ssh unchecked, so a leading "-" is read as an option | Fork | no | no | rc7 |
| [B103](#b103) | medium | Tools | Setup drops PROBE_ADDRESS from /etc/mailinabox.conf, so the mail check after an update is skipped | Fork | no | no | rc7 |
| [B104](#b104) | medium | Tools | update-check.sh backup fails with two or more Docker volumes, after the Mail-in-a-Box backup | Fork | no | no | rc7 |
| [B105](#b105) | low | Tests | Any local account can fake the setup marks in the journal, and the log audit then accepts its messages as setup noise | Fork | no | no | rc7 |
| [B106](#b106) | medium | Tools | update-check.sh does not find the checkout of a box in /mailinabox: no status checks before the update, and the backup stops | Fork | no | no | rc7 |
| [B107](#b107) | medium | Tools | update-check.sh mailcheck reports FAILED when the mail comes back over TLS | Fork | no | no | rc7 |
| [B108](#b108) | medium | Tools | update-check.sh after never says OK: every setup run moves the nightly job to another minute | Fork | no | no | rc7 |
| [B109](#b109) | low | Tools | The expected changes of rc7 miss changes of rc4 and rc5, so an update from rc1 to rc3 lists them as unexpected | Fork | no | no | rc7 |
| [B110](#b110) | low | Tools | update-check.sh after judges an in-place upgrade or a migration from upstream by the lists of the fork's updates | Fork | no | no | rc7 |
| [B111](#b111) | low | Tools | The test of the fallback SSH server leaves an empty /root/upgrade-2604 | Fork | no | no | rc7 |
| [B112](#b112) | low | Tools | The fallback SSH server refuses new logins for up to 10 s after the release upgrade stops ssh.service | Fork | no | no | rc7 |
| [B113](#b113) | low | Tools | migrate-to-2604.sh --check proposes a start command without the options it was given | Fork | no | no | rc7 |
| [B114](#b114) | low | Tools | update-check.sh after lists munin-node's port as changed when the process shows under another name | Fork | no | no | rc7 |
| [B115](#b115) | medium | Tools | The fallback SSH server of the in-place tool accepts keys that sshd refuses under StrictModes | Fork | no | no | rc7 |
| [B116](#b116) | low | Tools | update-check.sh runs the status checks and the backup from a checkout that it has just rejected | Fork | no | no | rc7 |
| [B117](#b117) | low | Tools | The tools take the backup target and passphrase, and write custom.yaml, through a directory that the user-data account can replace | Fork | no | no | rc7 |
| [B118](#b118) | low | Tools | The fallback SSH server misses Match blocks in files included from included files | Fork | no | no | rc7 |
| [B119](#b119) | medium | Tools | The fallback SSH server does not start for the release upgrade that begins right after the reboot into 24.04 | Fork | no | no | rc7 |
| [B120](#b120) | medium | Dovecot | Setup restarts Dovecot before it rewrites the passdb, and logins can fail as wrong passwords for two seconds | Upstream | yes | yes | after rc7 |
| [B121](#b121) | high | Nextcloud | Nextcloud throttles 127.0.0.1 after a setup run, and ActiveSync stops syncing calendars and contacts for every user | Upstream | yes | yes | after rc7 |
| [B122](#b122) | medium | Setup | Setup restarts Dovecot, Postfix, PHP-FPM and fail2ban several times per run; each restart cuts the clients, and fail2ban lifts all bans for a moment | Upstream | yes | yes | after rc7 |
| [B124](#b124) | medium | Nextcloud | Setup replaces Nextcloud's config.php with a file only root can read, for a moment, and Nextcloud fails the requests in that moment (an ActiveSync login gets HTTP 401) | Upstream | yes | yes | after rc7 |
| [B123](#b123) | medium | Dovecot | /etc/dovecot belongs to the account mail, which can change the configuration that Dovecot's root processes read and the files that setup writes there as root | Upstream | yes | yes | after rc7 |
| [B125](#b125) | low | Backup | The backup page and the backups wait up to two minutes when the rsync target does not answer a connection request | Upstream | yes | yes | after rc7 |
| [B128](#b128) | high | Z-Push | ActiveSync answers every contacts Sync with HTTP 500 for a user with a card whose name has no .vcf, such as Nextcloud's example contact left from rc3 to rc6 | Upstream | yes | yes | after rc7 |
| [B129](#b129) | medium | Z-Push | nginx ends an ActiveSync Ping with a heartbeat of more than 630 s with HTTP 504, while Z-Push still waits | Upstream | yes | yes | after rc7 |
| [B130](#b130) | medium | nginx | The /caldav, /carddav and /webdav proxy passes the decoded path: a space gives 400, an escaped ? starts a query string (a DELETE can hit the whole address book), query strings are lost | Upstream | yes | yes | after rc7 |

## Details

### B01

**quota-status policy rejects mail to aliases, catch-alls and domain aliases** (critical, Dovecot)

* **Symptom:** Inbound SMTP mail to an alias, catch-all or domain-alias address is rejected at RCPT time with "Unknown user" instead of being delivered to the target mailbox. Mail sent directly to real mailbox addresses gets through.
* **Cause:** Postfix calls the Dovecot quota-status policy service (check_policy_service inet:127.0.0.1:12340, last in smtpd_recipient_restrictions) with the original recipient before alias resolution. The PR set quota_status_nouser = "REJECT Unknown user" (and quota_status_success = OK), so every address that is not a Dovecot user is rejected.
* **Fix:** Sets quota_status_success and quota_status_nouser to DUNNO again (as in MIAB on Dovecot 2.3), as global settings outside the service block, so Postfix makes the decision. Also binds the listener to 127.0.0.1 and sets client_limit = 1.
* **Affects:** v78 no, PR #2603 yes. Origin: PR #2603 port.
* **Evidence:** c6118db:conf/dovecot-90-quota.conf lines 6-7: `quota_status_success = OK` / `quota_status_nouser = "REJECT Unknown user"`. v78:setup/mail-dovecot.sh lines 83-84 write `quota_status_success = DUNNO` / `quota_status_nouser = DUNNO` into 90-quota.conf (no conf/dovecot-90-quota.conf in v78). Policy hookup is the same in both: setup/mail-postfix.sh:241 `...check_policy_service inet:127.0.0.1:12340`. Recorded as Befund 6.1 in the initial review ("very likely" impact); the internal test report lists it as confirmed and fixed. Neither d817620 nor any commit before 6526ad7 touched the file.
* **Report upstream:** PR #2603: the bug is in the port's new conf/dovecot-90-quota.conf. v78 main is not affected.
* **Found by:** initial review; **commit:** `6526ad7`; **fixed in:** v78-r2604.0-rc1

### B02

**Per-user mailbox quotas ignored on Dovecot 2.4 (userdb still returns quota_rule)** (high, Dovecot)

* **Symptom:** A quota set for a user in the control panel (e.g. 10M) has no effect. The mailbox stays unlimited, and over-quota mail is neither rejected by quota-status nor at LMTP delivery.
* **Cause:** The ported userdb query still returns the Dovecot 2.3 field `'*:bytes=' || quota AS quota_rule`. Dovecot 2.4 removed quota_rule and reads the per-user limit from quota_storage_size, so the per-user value never reaches the quota plugin.
* **Fix:** The userdb query now returns `quota AS quota_storage_size`, and 90-quota.conf sets the global default quota_storage_size = 0 (unlimited) outside the quota block so the userdb value can override it.
* **Affects:** v78 no, PR #2603 yes. Origin: new on 26.04 (package/OS change, not handled by the port).
* **Evidence:** c6118db:setup/mail-users.sh:46 `userdb sql { query = SELECT ... '*:bytes=' || quota AS quota_rule ...`. v78:setup/mail-users.sh:54 has the same quota_rule mapping, but v78 runs Dovecot 2.3 on 22.04, which supports quota_rule, so quotas work there. Recorded as Befund 6.4 in the initial review ("presumably"), confirmed as fixed in the internal test report ("user quotas did not apply"). Whether Dovecot 2.4.2 ignores the unknown field silently or logs an error is not shown in the repo.
* **Report upstream:** PR #2603: the port changed the userdb block to 2.4 syntax but kept the 2.3-only quota_rule field. v78 is not affected.
* **Found by:** initial review; **commit:** `6526ad7`; **fixed in:** v78-r2604.0-rc1

### B03

**Sieve redirects keep the external sender as MAIL FROM and fail SPF** (high, Dovecot)

* **Symptom:** Mail forwarded by a user's Sieve redirect rule is sent with the original external sender as envelope sender. The target server sees an SPF failure and may reject the mail or file it as spam.
* **Cause:** The PR put sieve_redirect_envelope_from = recipient inside the `sieve_script personal { }` block. In Dovecot 2.4 this is an engine-wide setting, so a value set inside that block has no effect and the default (original sender) stays in force.
* **Fix:** Moves sieve_redirect_envelope_from = recipient to top level in conf/dovecot-99-local-sieve.conf.
* **Affects:** v78 no, PR #2603 yes. Origin: PR #2603 port.
* **Evidence:** c6118db:conf/dovecot-99-local-sieve.conf:30-35 has `sieve_script personal { ... sieve_redirect_envelope_from = recipient }`. v78:setup/mail-dovecot.sh:207-214 sets it in the Dovecot 2.3 `plugin { }` block, where it takes effect. That it is silently ignored inside a sieve_script block comes from the audit and the commit message. This read-only review did not check it against the Dovecot 2.4 source or docs.
* **Report upstream:** PR #2603. The 2.4 config translation was done there. v78 on Dovecot 2.3 is correct.
* **Found by:** audit; **commit:** `f7878b8`; **fixed in:** v78-r2604.0-rc1

### B04

**Sieve script paths keep literal $STORAGE_ROOT, so user filters and vacation replies do not run** (high, Dovecot)

* **Symptom:** Personal Sieve filters and vacation auto-replies (ManageSieve / Roundcube managesieve) have no effect on incoming mail. The admin-provided global_before/global_after scripts under the storage root are not run either. Only the spam-to-Spam global script at /etc/dovecot/sieve-spam.sieve, which uses an absolute path, still works.
* **Cause:** PR #2603 moved the Sieve config from a shell heredoc (where bash expands $STORAGE_ROOT) into the static file conf/dovecot-99-local-sieve.conf and installed it with a plain `cp -f`. The paths of the personal, global_before and global_after sieve_script blocks therefore reached Dovecot 2.4 as the literal text `$STORAGE_ROOT/mail/sieve/...`, a path that does not exist.
* **Fix:** Install the file with `sed "s|\$STORAGE_ROOT|$STORAGE_ROOT|g"` so that only $STORAGE_ROOT is replaced with the real storage root, while Dovecot's own %{user | domain} / %{user | username} variables are left untouched.
* **Affects:** v78 no, PR #2603 yes. Origin: PR #2603 port.
* **Evidence:** v78:setup/mail-dovecot.sh:206-215 writes the file with an unquoted heredoc `cat > /etc/dovecot/conf.d/99-local-sieve.conf << EOF` containing `sieve_before2 = $STORAGE_ROOT/mail/sieve/global_before`, `sieve = $STORAGE_ROOT/mail/sieve/%d/%n.sieve` and `sieve_dir = $STORAGE_ROOT/mail/sieve/%d/%n`, so bash expands the variable. conf/dovecot-99-local-sieve.conf does not exist in v78. c6118db:setup/mail-dovecot.sh:85 has `cp -f conf/dovecot-99-local-sieve.conf /etc/dovecot/conf.d/99-local-sieve.conf`. c6118db:conf/dovecot-99-local-sieve.conf contains `path = $STORAGE_ROOT/mail/sieve/global_before`, `path = $STORAGE_ROOT/mail/sieve/global_after`, `path = $STORAGE_ROOT/mail/sieve/%{user | domain }/%{user | username }` and the matching `active_path ... .sieve`. The cp line is unchanged in the merge d817620 (line 85) and was replaced only by 2bf1e1e. The initial review (Befund 6.3) and the internal test report record it as confirmed: the sieve paths stayed as the literal text `$STORAGE_ROOT`. I did not check here how Dovecot 2.4 itself handles a bare `$NAME` in a value (literal text or config error). The commit message and the test report both say literal text.
* **Report upstream:** PR #2603. The regression comes from the port's change from heredoc to cp and exists only in that PR. MIAB main (v78) expands the variable correctly through its heredoc.
* **Found by:** initial review; **commit:** `2bf1e1e`; **fixed in:** v78-r2604.0-rc1

### B05

**bootstrap.sh rejects Ubuntu 26.04, curl installer aborts** (high, Setup)

* **Symptom:** Running the one-line installer (curl .../setup.sh | sudo bash) on Ubuntu 26.04 prints "This script may be used only on a machine running Ubuntu 14.04, 18.04, or 22.04." and exits 1, so nothing is installed. The supported 26.04 install path only works via a manual git clone plus setup/start.sh.
* **Cause:** PR #2603 switched setup/preflight.sh to require Ubuntu 26.04 but did not touch setup/bootstrap.sh, whose OS switch only maps 22.04/18.04/14.04 to a TAG and exits for everything else. Even if 26.04 had been accepted, SOURCE defaulted to github.com/mail-in-a-box/mailinabox, which has no 26.04 tag.
* **Fix:** Adds an "Ubuntu 26.04 LTS" branch (first in the chain) that sets TAG=v78-r2604.0-rc1 and makes the default SOURCE the fork's repository (at that time on an internal Gitea server, since the move to GitHub https://github.com/LM1337/Mail-in-a-box-26), while the 22.04 branch keeps TAG=v78 and pins SOURCE to upstream GitHub; it also updates the error text and the header comment.
* **Affects:** v78 no, PR #2603 yes. Origin: PR #2603 port.
* **Evidence:** v78:setup/bootstrap.sh lines 23-43 accept only 22.04 (TAG=v78), 18.04 and 14.04, with else -> exit 1. That is correct for v78, which supports only 22.04 (v78:setup/preflight.sh:15 requires VERSION_ID 22.04), so a v78 box on 22.04 is not affected. c6118db:setup/bootstrap.sh is identical apart from TAG=v77 (still no 26.04 branch, SOURCE=https://github.com/mail-in-a-box/mailinabox), while c6118db:setup/preflight.sh:15 requires VERSION_ID 26.04. So the PR's own supported OS is rejected by its bootstrap. d817620 is unchanged (TAG=v78, 22.04 only). The commit message for a85fa0d says "bootstrap.sh rejected 26.04, so the curl install aborted". HEAD now has TAG=v78-r2604.0-rc2 (8ee9806).
* **Report upstream:** PR #2603: the port has to add a 26.04 branch to setup/bootstrap.sh before it can be installed the standard way (upstream would use its own tag and SOURCE, not the fork URL). Not MIAB main, because v78 on 22.04 behaves correctly.
* **Found by:** initial review; **commit:** `a85fa0d`; **fixed in:** v78-r2604.0-rc1

### B06

**IMAPSieve spam/ham learning never runs (CRLF shebang in sa-learn-*.sh)** (high, Spam)

* **Symptom:** When a user moves mail into or out of Spam/Junk, SpamAssassin learns nothing. Instead the Dovecot log shows a failed Sieve pipe action: the exec of /usr/lib/dovecot/sieve/sa-learn-*.sh fails with ENOENT ("No such file or directory"), because the interpreter "/bin/bash\r" does not exist.
* **Cause:** PR #2603 added conf/sa-learn-spam.sh, sa-learn-ham.sh and the report-*.sieve and dovecot-99-local-sieve.conf files with CRLF line endings. setup/spamassassin.sh copies them unchanged with cp -f, so the installed scripts start with "#!/bin/bash\r", and the kernel cannot execute an interpreter by that name.
* **Fix:** Converts all five sieve/sa-learn files to LF line endings.
* **Affects:** v78 no, PR #2603 yes. Origin: PR #2603 port.
* **Evidence:** c6118db:conf/sa-learn-ham.sh | od -c shows `#!/bin/bash\r\n`. `file` reports "with CRLF line terminators" for all five files at c6118db. c6118db:setup/spamassassin.sh:150-153 runs `cp -f conf/sa-learn-*.sh /usr/lib/dovecot/sieve/` + chmod +x with no CR stripping, and c6118db has no .gitattributes. v78 has none of these files (git show v78:conf/sa-learn-ham.sh -> fatal). It used the dovecot-antispam plugin with a heredoc-generated /usr/local/bin/sa-learn-pipe.sh (v78:setup/spamassassin.sh:176-182). No fork commit between d817620 and f7878b8 touched these files.
* **Report upstream:** PR #2603. The CRLF files come from the PR itself. MIAB main (v78) is not affected.
* **Found by:** audit; **commit:** `f7878b8`, `a3e55c6`; **fixed in:** v78-r2604.0-rc1

### B07

**PHP 8.5 packages installed from deb.sury.org before the pin get no updates from any repository** (high, System/apt)

* **Symptom:** On boxes set up with the PR #2603 code (or the fork before f31885f), php8.5-*, libgd3, php8.5-apcu, -imagick and -pspell are sury builds. Once the sury pin is in place, apt-get upgrade and unattended-upgrades install no further updates for them, so PHP security fixes stop arriving without any warning.
* **Cause:** PR #2603 added packages.sury.org without a pin, so sury's higher version numbers replaced Ubuntu's php8.5-* and libgd3. The fork's pin (f31885f) puts everything except php-common, php8.2-* and php8.5-imap at priority -1 for sury. An APT pin never downgrades, so the installed sury builds keep a version above Ubuntu's and are stuck.
* **Fix:** After apt-get update, setup/system.sh finds installed sury builds (version suffix +0~X.Y+ubuntuNN~N.gbpHASH) that are not on the allow-list. It simulates the change with apt-get -s, then installs the newest non-sury version from apt-cache madison with --allow-downgrades. If apt would remove a package, it skips the change and prints the manual command. Afterwards it restores the auto-installed marks taken from apt-mark showauto.
* **Affects:** v78 no, PR #2603 no. Origin: fork-internal (introduced and fixed within the fork).
* **Evidence:** c6118db:setup/system.sh lines 112-119 add 'deb [signed-by=...] https://packages.sury.org/php/ $(lsb_release -sc) main' with no /etc/apt/preferences.d entry, so php8.5-* come from sury. f31885f adds /etc/apt/preferences.d/mailinabox-sury-php ('Package: *' / 'Pin: origin packages.sury.org' / 'Pin-Priority: -1'), and only from then on do these packages receive no updates at all. On a pure PR head box they still get sury updates through a manual or setup apt-get upgrade, but not through unattended-upgrades (see the separate entry), hence 'partly'. v78:setup/system.sh line 115 uses only ppa:ondrej/php for PHP 8.0, which Ubuntu 22.04 does not ship, so no two repositories compete for the same packages. The commit message reports a test in an isolated apt root with the 26.04 test box's dpkg status: 20 packages moved back to Ubuntu 8.5.4-0ubuntu1.5 / libgd3 2.3.3-13ubuntu2 and nothing was removed.
* **Report upstream:** PR #2603: the sury source is added unpinned, so on 26.04 sury silently replaces Ubuntu's php8.5-*, libgd3 and php-common. The PR should pin sury to the packages Ubuntu lacks. The migration of already-affected boxes is specific to the fork.
* **Found by:** audit; **commit:** `832f3a7`; **fixed in:** v78-r2604.0-rc1

### B08

**dovecotimap filter does not match Dovecot 2.4 'Login aborted' lines** (high, fail2ban)

* **Symptom:** Even when the jail reads mail.log, failed IMAP/POP3/ManageSieve logins on 26.04 are not matched, so there is no brute-force protection for Dovecot.
* **Cause:** Dovecot 2.4 logs '<proto>-login: Info: Login aborted: <reason> (<details>) (<event reason>): user=<..>, method=.., rip=.., lip=..'. The filter only knew the Dovecot 2.3 '(Aborted login|Disconnected)(: Inactivity)? (...)' form.
* **Fix:** Rewrites failregex so it matches both the 2.4 'Login aborted: ... (...) (event)' form and the 2.3 form (auth failed, authorization failed, user disabled, tried to use ... auth, no auth attempts). It matches the user field greedily and forbids '>' after lip=, except in a final session=<..>, so a crafted user name cannot get a third-party IP banned.
* **Affects:** v78 no, PR #2603 yes. Origin: new on 26.04 (package/OS change, not handled by the port).
* **Evidence:** v78 and c6118db conf/fail2ban/filter.d/dovecotimap.conf have the same failregex: '^%(__prefix_line)s(pop3|imap|managesieve)-login: (Info: )?(Aborted login|Disconnected)(: Inactivity)? \(((no auth attempts|auth failed, \d+ attempts)...'. There is no 'Login aborted' alternative. v78 runs Dovecot 2.3, which logs the 'Aborted login' form, so v78 is unaffected. Commit message: fail2ban-regex 1.1.0 matched all 11 synthetic lines (2.4 and 2.3 format) and the 3 real 'no auth attempts' lines from the 26.04 test box. The initial review notes the 'Login aborted:' text in libdovecot-login.so 2.4.2. The user-name injection guard belongs to this new regex. The v78 regex uses user=<\S*> and the fixed ', rip=' with a space, so it does not look exploitable the same way, but that was not tested.
* **Report upstream:** PR #2603: the port moves to Dovecot 2.4 but keeps the 2.3-only filter. Not MIAB main (22.04/Dovecot 2.3 is unaffected), although a filter that matches both formats could also go upstream.
* **Found by:** audit; **commit:** `8bbeb60`; **fixed in:** v78-r2604.0-rc1

### B09

**fail2ban dovecot jail reads the systemd journal instead of mail.log on 26.04** (high, fail2ban)

* **Symptom:** On 26.04 the [dovecot] jail never counts an IMAP/POP3/ManageSieve login failure, so brute-force clients against Dovecot are never banned. fail2ban-client shows the jail running but with zero failures.
* **Cause:** fail2ban 1.1.0 on 26.04 ships paths-debian.conf with dovecot_backend = systemd, and the stock jail.conf [dovecot] section has backend = %(dovecot_backend)s. MIAB's jail.d/mailinabox.conf [dovecot] only overrides logpath, so the jail reads the journal (no journalmatch) while Dovecot writes only to log_path=/var/log/mail.log.
* **Fix:** Adds backend = auto to the [dovecot] section of conf/fail2ban/jails.conf so the jail reads /var/log/mail.log again, like the miab-* jails.
* **Affects:** v78 no, PR #2603 yes. Origin: new on 26.04 (package/OS change, not handled by the port).
* **Evidence:** /etc/fail2ban/jail.conf:627-631 '[dovecot] / port = ... / logpath = %(dovecot_log)s / backend = %(dovecot_backend)s' (fail2ban 1.1.0-9; checked on a 26.04 host with that package, the backend line is 631)
* **Report upstream:** PR #2603: the port added nothing for fail2ban 1.1's Debian systemd backends, and c6118db has the same jails.conf as v78. Not MIAB main, since v78 only targets 22.04.
* **Found by:** audit; **commit:** `8bbeb60`; **fixed in:** v78-r2604.0-rc1

### B10

**Nextcloud .mjs ES modules served as application/octet-stream, Contacts web UI blank** (high, nginx)

* **Symptom:** In the Nextcloud web UI the Contacts app shows a blank page, and parts of the core UI (user status, theming, viewer) do not work. The browser console reports module scripts refused because of a non-JavaScript MIME type. CardDAV/CalDAV sync is not affected.
* **Cause:** Nextcloud 28+ and contacts 8.x ship ES modules as .mjs files (contacts 8.x has only contacts-main.mjs as entry point; core dist/ has more than 100). The nginx /cloud/ location has no MIME mapping for mjs, because /etc/nginx/mime.types on Ubuntu 26.04 has no mjs entry and default_type is application/octet-stream. Browsers refuse to run module scripts served with that type.
* **Fix:** The /cloud/ location in conf/nginx-primaryonly.conf now includes /etc/nginx/mime.types and adds a types block mapping mjs to text/javascript. The include is needed because a types block replaces the inherited map. Nested locations inherit it, and other locations stay unchanged.
* **Affects:** v78 no, PR #2603 yes. Origin: PR #2603 port.
* **Evidence:** Checked against the release artifacts. The zip central directory of nextcloud-27.1.11.zip (v78) lists 27992 entries and 0 .mjs files. nextcloud-28.0.14.zip has 17 .mjs, all in bundled apps (logreader, activity, settings) and none in core dist/. nextcloud-34.0.3.zip (PR) has 928 .mjs, about 111 of them in core dist/ (for example dist/user_status-menu.mjs). contacts-v5.5.4.tar.gz (v78) has only js/contacts-main.js. contacts-v8.8.0.tar.gz (PR) has only js/contacts-main.mjs plus .chunk.mjs files. Ubuntu 26.04 nginx-common 1.28.3-2ubuntu1.11 /etc/nginx/mime.types maps only 'application/javascript js', with no mjs. Upstream nginx release-1.18.0 (22.04) is the same, so v78 is unaffected only because NC 27/contacts 5.5.4 ship no .mjs. This box's /etc/mime.types does list mjs, but nginx does not read that file.
* **Report upstream:** PR #2603: its Nextcloud 34 / contacts 8.8.0 bump ships .mjs, but nginx was not adapted. MIAB main will also need this as soon as it moves to Nextcloud >= 28.
* **Found by:** audit; **commit:** `44ce759`; **fixed in:** v78-r2604.0-rc1

### B11

**SSHFP records built from .pub files instead of the key sshd actually serves** (medium, DNS)

* **Symptom:** On a box whose private SSH host keys were copied over a fresh install (or whose .pub was edited or deleted), the signed zone published SSHFP fingerprints that did not match the host key sshd presents, or left out that algorithm entirely. Clients using VerifyHostKeyDNS then got a mismatch or no DNS confirmation. On HostKeyAgent setups no SSHFP records were published at all.
* **Cause:** Fork commit 2c7e109 (replacing ssh-keyscan because of OpenSSH 10 PerSourcePenalties) read '<HostKey>.pub' for every hostkey line of `sshd -T`. sshd derives the public key from the private key and ignores a missing or mismatching .pub, so the .pub can be stale or absent. With HostKeyAgent the HostKey path already ends in .pub, so the code opened 'x.pub.pub'. A leftover .pub without its private key was published even though sshd skips that HostKey.
* **Fix:** Adds get_ssh_host_public_key(), which follows sshd's precedence: a path ending in .pub is used as-is, otherwise the key is derived with `ssh-keygen -y -P "" -f path` (empty stdin), and the .pub is only a fallback. No record is returned when the private key is missing and no HostKeyAgent is set.
* **Affects:** v78 no, PR #2603 no. Origin: fork-internal (introduced in 2c7e109, shipped in tag v78-r2604.0-rc1, fixed in v78-r2604.0-rc2).
* **Evidence:** v78:management/dns_update.py:455 and c6118db:management/dns_update.py:457 both run `ssh-keyscan ... localhost`, which returns the key sshd presents on the wire, so neither has this bug. Commit 2c7e109 (fork, 22.10.2026) replaced keyscan with `open(path.strip() + ".pub")` over get_ssh_config_values("hostkey"). 3e77095 replaces that loop body with get_ssh_host_public_key(path.strip()).
* **Report upstream:** none: the faulty .pub-reading code exists only in the fork (2c7e109). If 2c7e109's keyscan replacement is offered to MIAB main or PR #2603 (the OpenSSH 10 PerSourcePenalties issue is real on 26.04), it should go with this fix included.
* **Found by:** late review; **commit:** `3e77095`; **fixed in:** v78-r2604.0-rc2

### B12

**SSHFP records published with wrong algorithm numbers after DSA removal** (medium, DNS)

* **Symptom:** The signed zone for the box hostname publishes SSHFP records with the wrong algorithm numbers: the ECDSA fingerprint is labelled 2 (DSA) and the Ed25519 fingerprint is labelled 3 (ECDSA). SSH clients using VerifyHostKeyDNS do not get a matching DNS-validated fingerprint for ECDSA or Ed25519 host keys. For Ed25519 there is no algorithm-4 record, so the client silently falls back to known_hosts. A client that negotiates the ECDSA host key does find an algorithm-3 record, but it holds the Ed25519 hash, so OpenSSH treats it as a mismatch and prints the changed-host-key warning ("Update the SSHFP RR in DNS with the new host key..."). Only the RSA record (1) is correct.
* **Cause:** When the port dropped DSA support in build_sshfp_records(), it deleted the "ssh-dss": 2 entry from the algorithm_number dict and renumbered the remaining entries (ECDSA 3->2, Ed25519 4->3). SSHFP algorithm numbers are fixed by IANA (1 RSA, 2 DSA, 3 ECDSA, 4 Ed25519) and do not depend on which key types exist.
* **Fix:** Restores the IANA numbers (ecdsa-sha2-nistp256: 3, ssh-ed25519: 4) and keeps DSA out of the scan, with a comment that the numbers must not be renumbered.
* **Affects:** v78 no, PR #2603 yes. Origin: PR #2603 port.
* **Evidence:** v78:management/dns_update.py build_sshfp_records(): {"ssh-rsa": 1, "ssh-dss": 2, "ecdsa-sha2-nistp256": 3, "ssh-ed25519": 4} (correct). c6118db:management/dns_update.py: comment "# Removed support for dsa (not shipped with 26.04)" and {"ssh-rsa": 1, "ecdsa-sha2-nistp256": 2, "ssh-ed25519": 3}; introduced in PR commit 191cffe (git log -S'Removed support for dsa'). Still wrong in merge d817620 (lines 438-442), fixed in 142abba.
* **Report upstream:** PR #2603: the renumbering exists only in the PR's port (commit 191cffe), and MIAB main/v78 has the correct numbers. It should be reported as a review comment on the PR.
* **Found by:** initial review; **commit:** `142abba`; **fixed in:** v78-r2604.0-rc1

### B13

**LMTP username format and sieve plugin lost if the package 20-lmtp.conf is restored** (medium, Dovecot)

* **Symptom:** every LMTP delivery fails with "550 5.1.1 User doesn't exist" and the mail bounces back to the senders (it is not held in the Postfix queue)
* **Cause:** The PR overwrites the package conffile /etc/dovecot/conf.d/20-lmtp.conf with its own copy (`cp -f conf/dovecot-20-lmtp.conf`), and the LMTP sieve plugin is set only in that file. The settings MIAB depends on are therefore lost when the package version comes back. According to the commit, the 26.04 package version also sets an auth_username_format that strips the domain.
* **Fix:** Pins `protocol lmtp { auth_username_format = %{user | lower}; mail_plugins { sieve = yes } }` in 99-local.conf, which the package does not manage and which is read after 20-lmtp.conf.
* **Affects:** v78 partly, PR #2603 yes. Origin: PR #2603 port.
* **Evidence:** c6118db:setup/mail-dovecot.sh:83 has `cp -f conf/dovecot-20-lmtp.conf /etc/dovecot/conf.d/20-lmtp.conf`. In c6118db, conf/dovecot-20-lmtp.conf contains only `protocol lmtp { mail_plugins { sieve = yes } }`, and `git grep username_format` finds nothing in c6118db or v78, so the PR never sets the LMTP username format itself. v78:setup/mail-dovecot.sh:187 adds the sieve plugin with a sed edit of the package 20-lmtp.conf, so replacing that conffile on v78 would also drop the sieve plugin. That part can affect v78. The domain-stripping auth_username_format is described only in the c929f6f commit message and code comment (setup/mail-dovecot.sh:156-158). The package file is not in the repo, so I could not check it here. I have no evidence that the 22.04 Dovecot 2.3 20-lmtp.conf strips the domain. Severity is high because delivery breaks completely once triggered, but it only happens after that admin choice.
* **Report upstream:** PR #2603: the port should keep the settings delivery depends on out of package-managed conffiles. The sieve-plugin part could also go to MIAB main as a minor robustness issue, because v78 sed-edits the package 20-lmtp.conf.
* **Found by:** audit; **commit:** `c929f6f`; **fixed in:** v78-r2604.0-rc1

### B14

**Quota grace is a fixed size on Dovecot 2.4 instead of 10% per user** (medium, Dovecot)

* **Symptom:** A message that overshoots the mailbox quota by much more than 10% is still accepted and delivered (the fixed grace is 10M in the fork, 100M in the PR, no matter how big the quota is).
* **Cause:** Dovecot 2.3's quota_grace accepted a percentage, and MIAB used 10%. Dovecot 2.4's quota_storage_grace only takes an absolute size. The port replaced the percentage with one global fixed value (100M in the PR, 10M in the fork after 6526ad7), so the grace no longer scales with each user's quota. The PR used a fixed 100M, the first fork fix a fixed 10M.
* **Fix:** The userdb query in setup/mail-users.sh now returns 10% of users.quota as quota_storage_grace (G/M suffixes converted to bytes and divided by 10, plain byte values divided by 10, quota 0 stays unlimited). The global 10M in conf/dovecot-90-quota.conf is kept only as a fallback.
* **Affects:** v78 no, PR #2603 partly. Origin: PR #2603 port.
* **Evidence:** v78 setup/mail-dovecot.sh:81 writes the plugin setting `quota_grace = 10%%` (percentage, Dovecot 2.3), and v78 has no conf/dovecot-90-quota.conf. c6118db conf/dovecot-90-quota.conf:1-3 has `quota maildir { quota_storage_grace = 100M }`, a fixed size, so the PR introduced the defect. In the PR head, though, the userdb still returns the 2.3 field `'*:bytes=' || quota AS quota_rule` (c6118db setup/mail-users.sh:46), which 2.4 ignores (fixed as Befund 6.4 in 6526ad7). Per-user quotas therefore had no effect at all in the PR head, and the grace problem could not be seen on its own there; that is why affects_pr2603 is 'partly'. 6526ad7 changed the value to 10M, still fixed, and 85e9eb7^:conf/dovecot-90-quota.conf has `quota_storage_grace = 10M`. tests/fork/smoke.py:1497-1500 (c_overquota) fails when the over-quota mail is delivered. The commit message reports that failure; the test run itself was not re-checked here.
* **Report upstream:** PR #2603: its conf/dovecot-90-quota.conf uses a fixed quota_storage_grace = 100M, and it still uses quota_rule in the userdb. Both should be reported to the 26.04 port together. Not relevant to MIAB main (v78 on 22.04 / Dovecot 2.3 uses a correct 10% quota_grace).
* **Found by:** test run; **commit:** `85e9eb7`; **fixed in:** v78-r2604.0-rc1

### B15

**quota-status accepts messages larger than the whole quota (empty quota_status_toolarge on Dovecot 2.4.2)** (medium, Dovecot)

* **Symptom:** A message bigger than the recipient's entire quota is not rejected at RCPT time. Postfix accepts it, and LMTP delivery then fails with 552, so Postfix sends a bounce (DSN) to the sender afterwards. On MIAB/22.04 the same message is refused in the SMTP dialogue with 522 5.2.2 Mailbox is full.
* **Cause:** The quota-status policy service answers with quota_status_toolarge when a single message exceeds the whole quota limit. The 2.4 docs say this setting defaults to quota_status_overquota, but according to the commit's test result it is empty in Dovecot 2.4.2. The service then returns 'action=' (empty), and Postfix treats that as accept. The port's 90-quota.conf never set quota_status_toolarge.
* **Fix:** Adds quota_status_toolarge = "522 5.2.2 Mailbox is full" to conf/dovecot-90-quota.conf, so too-large messages are rejected at RCPT just like over-quota ones.
* **Affects:** v78 no, PR #2603 latent. Origin: PR #2603 port (missing setting); first exposed by fork commit 6526ad7, which made per-user quotas take effect.
* **Evidence:** c6118db:conf/dovecot-90-quota.conf (service quota-status block) sets only quota_status_success = OK, quota_status_nouser = "REJECT Unknown user" and quota_status_overquota = "522 5.2.2 Mailbox is full". There is no quota_status_toolarge, and git grep finds no 'toolarge' anywhere in c6118db. The PR therefore has the gap, but it is latent there: c6118db:setup/mail-users.sh:46 returns quota_rule (a 2.3 field) and no quota_storage_size is set, so there is no limit a message could exceed (see 6526ad7's commit message).
* **Report upstream:** PR #2603, but only together with the per-user quota fix (6526ad7: quota_storage_size from the userdb instead of quota_rule). Without that fix, the PR has no quota limit, so this setting has nothing to act on. Optionally also report to Dovecot that the 2.4.2 default contradicts the 2.4 docs. Not MIAB main, because v78 on Dovecot 2.3 is unaffected.
* **Found by:** test run; **commit:** `728fe54`; **fixed in:** v78-r2604.0-rc1

### B16

**sa-learn can be killed by the 10s Sieve pipe timeout** (medium, Dovecot)

* **Symptom:** When a message is moved into or out of Spam, the learning run can be aborted before it finishes, especially on a slow box or during a Bayes auto-expiry. The message is then not learned and a pipe timeout error is logged.
* **Cause:** The IMAPSieve pipe runs sa-learn under Pigeonhole's default sieve_pipe_exec_timeout. The commit gives that default as 10s. sa-learn loads the full SpamAssassin rule set for each message. The 22.04 antispam plugin pipe had no such limit.
* **Fix:** Sets sieve_pipe_exec_timeout = 120s in conf/dovecot-99-local-sieve.conf.
* **Affects:** v78 no, PR #2603 yes. Origin: PR #2603 port.
* **Evidence:** c6118db:conf/dovecot-99-local-sieve.conf:41 sets only sieve_pipe_bin_dir, with no sieve_pipe_exec_timeout. v78 used dovecot-antispam with antispam_pipe_program=/bin/bash (v78:setup/spamassassin.sh:155-163), so the Sieve pipe timeout did not apply. The 10s default is taken from the commit message, not checked against the Pigeonhole source here. The bug was latent while the CRLF shebang bug was present.
* **Report upstream:** PR #2603. It replaced antispam with an IMAPSieve pipe.
* **Found by:** audit; **commit:** `f7878b8`; **fixed in:** v78-r2604.0-rc1

### B17

**Quota validation accepts non-ASCII Unicode digits, breaking the user's Dovecot userdb lookup** (medium, Management)

* **Symptom:** An admin can save a quota such as fullwidth '１０G' or Arabic-Indic '٣G' through the admin panel or API, and it is accepted and stored. Dovecot then cannot parse that user's quota, so mail delivery to the user (LMTP/quota-status) tempfails and IMAP login fails. On the fork HEAD the computed quota_storage_grace also silently becomes '0B'.
* **Cause:** validate_quota() used re.match(r'^[\d]+[GM]?$', quota) on a str pattern without re.ASCII, so \d matches any Unicode decimal digit (category Nd). The earlier check r"[\s,.]" does not catch these characters, so the value reaches users.quota unchanged. Dovecot's size parser only accepts ASCII digits.
* **Fix:** Replaces the check with re.fullmatch(r'[0-9]+[GM]?', quota, flags=re.ASCII), so only ASCII digits with an optional G/M suffix are stored.
* **Affects:** v78 yes, PR #2603 yes. Origin: upstream (also in v78 on 22.04).
* **Evidence:** v78:management/mailconfig.py:435 and c6118db:management/mailconfig.py:435 are identical: `if not re.match(r'^[\d]+[GM]?$', quota):`. The regex came in with upstream commit ce45217 ('bringing in quota changes'). The check is reached from add_mail_user (v78 mailconfig.py:343) and set_mail_quota (v78 mailconfig.py:402), and both write the value to the DB. Python test on the old check: '１０G' and '٣G' pass, but they fail the new fullmatch/re.ASCII check. How Dovecot consumes the value: v78 setup/mail-users.sh:54 `'*:bytes=' || quota AS quota_rule` (Dovecot 2.3). c6118db setup/mail-users.sh:46 uses the same quota_rule. HEAD setup/mail-users.sh:50 uses `quota AS quota_storage_size` plus a grace CASE expression where CAST('１０' AS INTEGER) gives 0, hence '0B'. The '0B' grace symptom is fork-only, because v78 uses a static quota_grace = 10%%. The 2.4 failure (userdb lookup failing) comes from the commit message. On v78/Dovecot 2.3, the claim that '*:bytes=１０G' is rejected as an invalid quota rule and breaks mail user init/login is inferred from 2.3's ASCII-only size parsing. It was not reproduced on a 22.04 box. Also, v78's set_mail_quota commits to the DB before `doveadm quota recalc -u` (check_call), so a failing recalc would not roll back the stored value. Trigger needs an admin (or API caller with admin rights) to enter non-ASCII digits.
* **Report upstream:** MIAB main: the identical validate_quota regex is in v78 (and in PR #2603, which inherits it unchanged), so a one-line fix with re.ASCII/[0-9] applies upstream. PR #2603 benefits from the same fix but did not introduce it.
* **Found by:** late review; **commit:** `7574e10`; **fixed in:** v78-r2604.0-rc2

### B18

**mail_log.py ignores postfix/postgrey lines with RFC 3339 rsyslog timestamps** (medium, Management)

* **Symptom:** The weekly "Mail-in-a-Box Usage Report" (daily_tasks.sh runs `mail_log.py -t week`) and manual mail_log.py runs show only Dovecot login data. Sent and received mail, greylisting and rejects from postfix and postgrey are missing, and nothing reports an error.
* **Cause:** On Ubuntu 26.04 (and since 24.04), rsyslog writes /var/log/mail.log with RFC 3339 timestamps (e.g. 2026-10-22T22:01:23.217307+00:00), because the stock config no longer sets RSYSLOG_TraditionalFileFormat. Dovecot still writes the traditional format ("Oct 22 22:01:23") to the same file through log_path. The regex in scan_mail_log_line() only matches `\w+\s+\d+ \d+:\d+:\d+`, so every rsyslog line fails the match and the function returns True, which silently skips the line.
* **Fix:** The regex now accepts both the traditional and the RFC 3339 timestamp. ISO timestamps are parsed with fromisoformat() and converted to naive local time, so they compare correctly with NOW/START_DATE/END_DATE. The strptime year-rollover heuristic now runs for traditional lines only.
* **Affects:** v78 no, PR #2603 yes. Origin: new on 26.04 (package/OS change, not handled by the port).
* **Evidence:** The regex is the same in all three refs: v78, c6118db and d817620 management/mail_log.py:329 `m = re.match(r"(\w+[\s]+\d+ \d+:\d+:\d+) ([\w]+ )?([\w\-/]+)[^:]*: (.*)", line)`, followed by strptime '%Y %b %d %H:%M:%S' at :348. No ref configures the rsyslog file template. setup/system.sh only installs and restarts rsyslog (v78:153/183/191, c6118db:155/185/193), so the format comes from the Ubuntu package default. Dovecot log_path=/var/log/mail.log is set in v78 setup/mail-dovecot.sh:50 and c6118db/HEAD :59, which explains the mixed-format file. Why v78 is not affected: Ubuntu 22.04's stock /etc/rsyslog.conf sets `$ActionFileDefaultTemplate RSYSLOG_TraditionalFileFormat`, and Ubuntu dropped that line from 24.04 on. This comes from Ubuntu packaging and cannot be checked in this repo. The commit message gives the 26.04 behaviour and the code comment says "Ubuntu >= 24.04". Consumer: HEAD management/daily_tasks.sh:15. 3d541ac is the only commit after d817620 that touches mail_log.py.
* **Report upstream:** PR #2603: it targets 26.04 and has the unchanged regex, so its weekly report loses all postfix/postgrey data. MIAB main should also get the fix, because any future upstream move to Ubuntu 24.04+ hits the same rsyslog default. On 22.04 (v78) there is nothing to fix yet.
* **Found by:** audit; **commit:** `3d541ac`; **fixed in:** v78-r2604.0-rc1

### B19

**Failed occ upgrade aborts setup under set -e: no retry, Nextcloud stuck in maintenance mode, php-fpm left stopped** (medium, Nextcloud)

* **Symptom:** If any `occ upgrade` hop fails during setup, setup aborts at once with no retry. Nextcloud stays in maintenance mode. php-fpm stays stopped, so Nextcloud, Roundcube and Z-Push are down until the next reboot or setup run (webmail.sh runs before nextcloud.sh and calls restart_service php-fpm). If the failed run had already written the new version to config.php, so that no upgrade is pending, every later setup run aborts at the final `occ upgrade`, which returns 2 (maintenance mode still on), until an admin runs `occ maintenance:mode --off` by hand.
* **Cause:** Three separate defects. (1) setup/functions.sh sets `set -euo pipefail`, so a non-zero `occ upgrade` kills the script before `E=$?` runs. The retry and the `maintenance:mode --off` after a successful retry are unreachable, and the `-ne 3` checks are dead code (per the commit message NC 34 returns 0/2/5, never 3). (2) Even without set -e, the intended logic ends in a bare `exit 1` after the second failure (v78:setup/nextcloud.sh:146, c6118db:162/184) and in the final check (v78:381). php-fpm was stopped before the chain (v78:179) and is only restarted at the end (v78:457), so it stays stopped on every failure path, not just because of set -e. (3) Exit code 2 (no upgrade pending but maintenance mode still on) counts as failure and is never handled. Later runs keep aborting at the final upgrade for that reason, and set -e has nothing to do with it.
* **Fix:** The three inline copies are replaced by helpers. NextcloudUpgrade captures the exit code with `|| E=$?`, turns maintenance mode off on code 2, retries up to 3 times, and turns maintenance mode off after a successful retry. NextcloudUpgradeDb runs the db:add-missing-*/bigint steps. NextcloudUpgradeFailed restarts php-fpm, points to the backup and exits. The final post-app-enable upgrade now also goes through NextcloudUpgrade.
* **Affects:** v78 yes, PR #2603 yes. Origin: upstream (also in v78 on 22.04).
* **Evidence:** On v78 the set -e abort applies to every InstallNextcloud hop (20->21 ... 25->26 at :223-243, plus the final 27.1.11 install at :248, nextcloud_ver=27.1.11 at :23) and to the final post-app-enable upgrade (:379-381).
* **Report upstream:** MIAB main and PR #2603. The same dead retry/maintenance handling under set -e is in v78 and in the PR head (the PR even duplicates it for the legacy-PHP path), so both benefit.
* **Found by:** audit; **commit:** `6a15bcf`; **fixed in:** v78-r2604.0-rc1

### B20

**Roundcube CardDAV preset uses carddav 4.x keys, so no Nextcloud addressbook is set up** (medium, Roundcube)

* **Symptom:** Webmail users whose preset 'ownCloud' account is created under carddav 5.x (new users, or a fresh install without the old Roundcube DB) see no Nextcloud contacts in Roundcube, because the account has no discovery_url and so no addressbook. Users cannot add the URL by hand because hide_preferences hides the carddav settings.
* **Cause:** PR #2603 bumped the rcmcarddav plugin from 4.4.3 to 5.1.3 (commit 191cffe), but the preset in carddav/config.inc.php kept the 4.x keys 'url' and 'preemptive_auth'. According to the commit message, carddav 5.x parsePresetArray() silently drops unknown keys and discovery_url defaults to NULL, so the preset account has no discovery URL. Accounts migrated from 4.x had no fixed discovery_url either, so they did not get it on login.
* **Fix:** Writes the preset in 5.x format: 'discovery_url' and 'preemptive_basic_auth' => true, both added to 'fixed' so migrated accounts get the URL on their next login. It also adds 'accountname', sets the addressbook name template to '%a (%N)' to match the 4.x naming, and drops the unused suppress_version_warning.
* **Affects:** v78 no, PR #2603 yes. Origin: PR #2603 port.
* **Evidence:** v78:setup/webmail.sh:43 CARDDAV_VERSION=4.4.3, and the preset at lines 153ff uses 'url' => 'https://${PRIMARY_HOSTNAME}/cloud/remote.php/dav/addressbooks/users/%u/contacts/' and 'preemptive_auth' => '1'. These are valid 4.x keys, so v78 works. c6118db:setup/webmail.sh:43 CARDDAV_VERSION=5.1.3 (bump added in 191cffe, an ancestor of c6118db) with the same unchanged 4.x preset block. d817620 is identical. Just before the fix (9b97bb9^) the plugin was 5.1.4 (fork commit 26f8e84) with the same 4.x preset. The claim that 5.x drops unknown keys and that 5.1.3+ updates a fixed null discovery_url comes from the commit message. I did not check it against the rcmcarddav source in this repo.
* **Report upstream:** PR #2603: the bug comes from the PR's carddav 5.x version bump without a matching preset change. MIAB main (v78) still ships 4.4.3 and is not affected, but any upstream move to carddav 5.x needs the same preset change.
* **Found by:** audit; **commit:** `9b97bb9`; **fixed in:** v78-r2604.0-rc1

### B21

**Email prompt loops forever when dialog, python3 and pip3 are already installed (email_validator never installed)** (medium, Setup)

* **Symptom:** On the first interactive setup run on an Ubuntu 26.04 host that already has dialog, python3 and pip3 (for example a provider image with python3-pip preinstalled), every email address is rejected with "That's not a valid email address." The admin can only leave the prompt with ESC/cancel, which ends setup. The workaround is to set PRIMARY_HOSTNAME or NONINTERACTIVE.
* **Cause:** PR #2603 removed v78's unconditional `pip3 install email_validator` (pip installs into the system Python are blocked by PEP 668 on 26.04). It moved python3-email-validator into the apt install line, but that line only runs when /usr/bin/dialog, /usr/bin/python3 or /usr/bin/pip3 is missing. When all three exist, email_validator is never installed. `python3 management/mailconfig.py validate-email` then fails with an ImportError (line 15 imports email_validator, line 16 imports idna), which gives a non-zero exit, and the while loop asks again.
* **Fix:** The install condition now checks whether the modules import (`python3 -I -c 'import email_validator, idna'`) instead of whether pip3 exists. It also installs python3-idna explicitly and no longer installs python3-pip in questions.sh, because system.sh installs it later.
* **Affects:** v78 no, PR #2603 yes. Origin: PR #2603 port.
* **Evidence:** On Ubuntu 26.04, python3-email-validator Depends: python3-dnspython, python3-idna, python3 (apt-cache depends). So the explicit python3-idna in the fix is redundant but harmless. The part that matters is the import-based condition.
* **Report upstream:** PR #2603: the regression comes from the port's switch from pip3 to apt in setup/questions.sh. MIAB main (v78) is not affected because it runs pip3 install unconditionally.
* **Found by:** audit; **commit:** `9480754`; **fixed in:** v78-r2604.0-rc1

### B22

**Ham learning fires for moves to "Deleted *", Trash subfolders and Spam<->Junk** (medium, Spam)

* **Symptom:** Spam that is deleted from Spam/Junk into a "Deleted Items"/"Deleted Messages" folder or a Trash subfolder is learned as ham, which poisons the Bayes database. Moving a message from Spam to Junk (or back) learns it as ham and as spam at once.
* **Cause:** The PR's report-ham.sieve skips only a destination mailbox named exactly "Trash". The 22.04 antispam setup used the trash pattern "trash;Deleted *". The PR also defines both Spam and Junk as spam folders (mailbox + imapsieve_from blocks), so a Spam->Junk copy triggers both report-spam and report-ham.
* **Fix:** report-ham.sieve now stops for Trash, Spam and Junk, and for matches on "Deleted *", "Trash/*" and "Trash.*", all with the i;ascii-casemap comparator.
* **Affects:** v78 no, PR #2603 yes. Origin: PR #2603 port.
* **Evidence:** c6118db:conf/sieve-report-ham.sieve:7 has `if string "${mailbox}" "Trash" { stop; }` only. c6118db:conf/dovecot-99-local-sieve.conf:56 is `mailbox Junk` (report-spam) and :63/:70 are `imapsieve_from Spam`/`imapsieve_from Junk` (report-ham). v78:setup/spamassassin.sh:157-158 uses `antispam_spam_pattern_ignorecase = SPAM` (Junk is not a spam folder there, so no double learning) and `antispam_trash_pattern_ignorecase = trash;Deleted *`. Note: the default Sieve comparator is already i;ascii-casemap (RFC 5228), so the explicit case-insensitive comparator is not itself a behaviour change. This bug was latent while the CRLF shebang bug stopped every learning run.
* **Report upstream:** PR #2603. The IMAPSieve replacement for the antispam plugin is introduced there.
* **Found by:** audit; **commit:** `f7878b8`; **fixed in:** v78-r2604.0-rc1

### B23

**SpamAssassin rule updates never run on 26.04; setup aborts if /etc/default/spamd is missing** (medium, Spam)

* **Symptom:** sa-update never runs, so the rules stay at "UPDATE version 000" (only the rules shipped with the package) forever. On systems installed without Recommends, where /etc/default/spamd does not exist, setup aborts with a FileNotFoundError from editconf.
* **Cause:** SpamAssassin 4.0 on 26.04 no longer reads CRON=1 from /etc/default/spamd, and /etc/cron.daily/spamassassin does nothing. Updates come from spamassassin-maintenance.timer, which a fresh install leaves disabled. The port only changed the CRON=1 target path from /etc/default/spamassassin to /etc/default/spamd, and editconf fails when that file is absent.
* **Fix:** Drops the CRON=1 editconf call, enables spamassassin-maintenance.timer, and at the end of the script starts one non-blocking spamassassin-maintenance.service run so the first update lints the final local.cf. The spampd sa-update hook restarts spampd after each update.
* **Affects:** v78 no, PR #2603 yes. Origin: PR #2603 port.
* **Evidence:** c6118db:setup/spamassassin.sh:26-27 `tools/editconf.py /etc/default/spamd CRON=1`. v78:setup/spamassassin.sh:26-27 `tools/editconf.py /etc/default/spamassassin CRON=1`. On 22.04 (SpamAssassin 3.4) /etc/cron.daily/spamassassin reads CRON from /etc/default/spamassassin, so updates work on v78. This is based on the 3.4 Debian packaging and was not re-checked on a 22.04 box. Fixed in ecc169a:setup/spamassassin.sh:33 (`systemctl enable --now spamassassin-maintenance.timer`) and :204 (`systemctl start --no-block spamassassin-maintenance.service || true`). apt_install (setup/functions.sh:54-60) does not pass --no-install-recommends, so the FileNotFoundError only occurs where Recommends are disabled.
* **Report upstream:** PR #2603: the port's CRON=1 retarget does nothing on SpamAssassin 4.0 and needs the timer-based mechanism.
* **Found by:** audit; **commit:** `ecc169a`; **fixed in:** v78-r2604.0-rc1

### B24

**spampd still runs in local-only mode (no DNSBL/URIBL/Pyzor/Razor/DKIM checks)** (medium, Spam)

* **Symptom:** SpamAssassin inside spampd skips every network test: no DNSBL/URIBL, Pyzor, Razor or DKIM network checks. Spam detection is noticeably weaker, and `spampd --show config` reports `local-only 1` (seen on the 26.04 test box).
* **Cause:** spampd 2.62 on 26.04 reads /etc/spampd.cfg as "name value" lines and treats a value of 0 as no value (`$v = $2 || ""`). editconf without -s could not match the shipped `local-only 1` line, so it appended `local-only=0`. spampd read that as a bare --local-only, which means on, and the shipped `local-only 1` line stayed active as well.
* **Fix:** Comments out every local-only line, removes the `maxsize=2000`/`local-only=0` lines earlier runs appended, and re-inserts `maxsize 2000` and `no-local-only` before the ADDOPTS end marker (or at the top of the file), ahead of the Net::Server `--` section. relayport=10026 is now set with editconf -s.
* **Affects:** v78 no, PR #2603 yes. Origin: PR #2603 port.
* **Evidence:** c6118db:setup/spamassassin.sh:49-51 `tools/editconf.py /etc/spampd.cfg maxsize=2000 local-only=0` (name=value form, no -s). v78:setup/spamassassin.sh:49-52 writes `/etc/default/spampd` with `LOCALONLY=0` and `ADDOPTS="--maxsize=2000"`. That is the 22.04 package interface, so the spampd.cfg parsing problem cannot occur there. Whether jammy's spampd honours LOCALONLY=0 was not checked in this repo. Fixed in ecc169a:setup/spamassassin.sh:71-79. The commit also places maxsize before the `--` passthrough section. Whether the appended `maxsize=2000` in c6118db was actually ignored is not stated in the commit and not verified, so it is not listed as a separate bug.
* **Report upstream:** PR #2603: the defective spampd.cfg handling is the port's own code and affects every 26.04 install of the PR.
* **Found by:** audit; **commit:** `ecc169a`; **fixed in:** v78-r2604.0-rc1

### B25

**Unpinned sury repo replaces Ubuntu's PHP 8.5, libgd3 and php-common** (medium, System/apt)

* **Symptom:** On a fresh 26.04 install the packages Ubuntu is supposed to provide (php8.5-*, libgd3, php-common, and PECL modules such as apcu/imagick/pspell per the follow-up 832f3a7) get installed or upgraded from packages.sury.org. They carry sury's version suffix, and the PHP stack ends up on third-party builds even though Ubuntu 26.04 ships PHP 8.5 itself.
* **Cause:** sury's version strings (suffix +ubuntuXX.YY~N.gbpHASH) sort above Ubuntu's (8.5.4-0ubuntu1.5 for php8.5-*, 2.3.3-13ubuntu2 for libgd3, per 832f3a7), so at equal priority 500 APT takes sury's builds for every package both repos carry.
* **Fix:** Adds /etc/apt/preferences.d/mailinabox-sury-php, which lets only php-common, php${PHP_LEGACY_VER}, php${PHP_LEGACY_VER}-* and php${PHP_VER}-imap come from origin packages.sury.org (priority 500) and gives everything else from that origin priority -1.
* **Affects:** v78 no, PR #2603 yes. Origin: PR #2603 port.
* **Evidence:** c6118db:setup/system.sh:113-119 adds 'deb [signed-by=...] https://packages.sury.org/php/ $(lsb_release -sc) main' to /etc/apt/sources.list.d/php.list. There is no preferences.d entry anywhere in c6118db:setup/system.sh, and c6118db:setup/functions.sh:8 sets PHP_VER=8.5, i.e. Ubuntu's stock PHP is the intended one. v78:setup/system.sh:115 uses 'add-apt-repository --y ppa:ondrej/php', also unpinned. On 22.04, though, PHP 8.0 exists only in that PPA, so taking PHP from ondrej there is upstream's intended design, not this bug. Caveats: the pin only affects new installs (CHANGELOG-fork.md:122-128 says it had not been tested on a real VM yet). Existing boxes are migrated back to Ubuntu builds by the follow-up 832f3a7 (Audit).
* **Report upstream:** PR #2603: the unpinned sury source is in the port itself. MIAB main (v78, ondrej PPA on 22.04) is not affected.
* **Found by:** initial review; **commit:** `f31885f`; **fixed in:** v78-r2604.0-rc1

### B26

**sury keyring .deb installed without verifying the signing key** (medium, System/apt)

* **Symptom:** Because curl runs without -f, an HTTP error is not caught at download time: the error body gets saved as the .deb in a fixed, predictable /tmp path. The following 'hide_output dpkg -i' then fails on the non-deb file, and setup aborts with a confusing dpkg error. It does not continue silently.
* **Cause:** The port runs 'curl -sSLo /tmp/debsuryorg-archive-keyring.deb' and then 'dpkg -i' with no fingerprint or hash check. The only trust anchor is TLS to packages.sury.org.
* **Fix:** Downloads with 'curl -f' into a mktemp directory and extracts the .deb with dpkg-deb -x. gpg --show-keys must find exactly fingerprint 15058500A0235D97F5D10063B188E2B695BD4743 in usr/share/keyrings/debsuryorg-archive-keyring.gpg before dpkg -i runs, otherwise setup exits.
* **Affects:** v78 no, PR #2603 yes. Origin: PR #2603 port.
* **Evidence:** c6118db:setup/system.sh:117-118: 'hide_output curl -sSLo /tmp/debsuryorg-archive-keyring.deb https://packages.sury.org/debsuryorg-archive-keyring.deb' then 'hide_output dpkg -i /tmp/debsuryorg-archive-keyring.deb', with no check in between. v78:setup/system.sh:115 adds ppa:ondrej/php through add-apt-repository, which gets the PPA key from Launchpad. No sury keyring .deb is involved, so this code path does not exist in v78.
* **Report upstream:** PR #2603: the unchecked keyring install is introduced by the port. Not relevant to MIAB main v78.
* **Found by:** initial review; **commit:** `f31885f`; **fixed in:** v78-r2604.0-rc1

### B27

**sury signing key trusted globally via /etc/apt/trusted.gpg.d** (medium, System/apt)

* **Symptom:** After setup, the sury key is trusted for every APT source, including the Ubuntu archive, not only for packages.sury.org.
* **Cause:** The commit's comment states that, besides /usr/share/keyrings, the debsuryorg-archive-keyring package installs the key as /etc/apt/trusted.gpg.d/debsuryorg-archive.gpg, and the port leaves it there. APT trusts keys in trusted.gpg.d for all sources, which defeats the signed-by= scoping in php.list.
* **Fix:** Deletes /etc/apt/trusted.gpg.d/debsuryorg-archive.gpg after dpkg -i, so the key is used only through signed-by= (the comment notes that dpkg does not restore a deleted conffile on reinstall).
* **Affects:** v78 no, PR #2603 yes. Origin: PR #2603 port.
* **Evidence:** c6118db:setup/system.sh:118 installs the keyring .deb and nothing removes the trusted.gpg.d copy. The file path comes from the comment in f31885f (setup/system.sh, 'The keyring package also installs the key into /etc/apt/trusted.gpg.d/'). I did not check the .deb's file list in this read-only review. v78 does not install this package (v78:setup/system.sh:115 uses add-apt-repository ppa:ondrej/php). Whether add-apt-repository on 22.04 puts the ondrej key in trusted.gpg.d, a similar global trust, was not checked here and is not the same code.
* **Report upstream:** PR #2603: the port added the keyring package and its global key copy. Not relevant to MIAB main v78.
* **Found by:** initial review; **commit:** `f31885f`; **fixed in:** v78-r2604.0-rc1

### B28

**unattended-upgrades does not cover the third-party PHP and duplicity repositories** (medium, System/apt)

* **Symptom:** Security updates for packages from the PHP third-party repository (on v78: PHP 8.0 from ppa:ondrej/php; on 26.04: php-common, php8.2-*, php8.5-imap from deb.sury.org) and for duplicity from its PPA are never installed automatically. They only arrive when the admin runs apt or re-runs setup.
* **Cause:** Setup enables APT::Periodic::Unattended-Upgrade in 02periodic but never adds the PPA/sury origins. The stock 50unattended-upgrades only allows the Ubuntu archive, -security and ESM.
* **Fix:** Adds /etc/apt/apt.conf.d/51mailinabox-unattended-upgrades with Unattended-Upgrade::Origins-Pattern entries for origin=deb.sury.org and origin=LP-PPA-duplicity-team-duplicity-release-git, both restricted to codename=${distro_codename}.
* **Affects:** v78 yes, PR #2603 yes. Origin: upstream (also in v78 on 22.04).
* **Evidence:** v78:setup/system.sh lines 111 and 115 add ppa:duplicity-team/duplicity-release-git and ppa:ondrej/php. Lines 261-266 write only 02periodic (MaxAge, Update-Package-Lists, Unattended-Upgrade, Verbose). git grep for 'Origins-Pattern|Allowed-Origins' finds nothing in v78 or c6118db, only in 832f3a7:setup/system.sh line 344. On v78 the matching origin would be LP-PPA-ondrej-php, which the fork's new file does not list because the fork no longer uses that PPA. That v78 itself is affected follows from the stock Ubuntu 22.04 50unattended-upgrades (Ubuntu/-security/ESM only); this was not verified on a live 22.04 box.
* **Report upstream:** MIAB main: v78 has the same gap for ppa:ondrej/php (PHP 8.0, which Roundcube, Z-Push and Nextcloud run on) and for the duplicity PPA, so it is a real security-update gap upstream. Also PR #2603, which keeps it for sury.
* **Found by:** audit; **commit:** `832f3a7`; **fixed in:** v78-r2604.0-rc1

### B29

**owncloud-restore.sh restores pre-upgrade-chain Nextcloud code that cannot run on PHP 8.5** (medium, Tools)

* **Symptom:** On a box migrated from 22.04, the backup taken before the 26.04 upgrade chain holds Nextcloud 27 code. Restoring it puts that code under php8.5-fpm, so `occ maintenance:mode --off` fails and Nextcloud does not work, yet the script still prints "Done".
* **Cause:** Backups from before the chain (taken once, before the 26->27->...->34 steps) hold code older than NC 33. On a box migrated from v78 that is NC 27.1.11, and an interrupted chain can leave NC 28-32. None of these versions accepts PHP 8.5: lib/versioncheck.php limits NC 27 to below 8.3, NC 30 to below 8.4, and NC 31/32 to below 8.5. PHP 8.2 is purged at the end of setup, so the restore can only use 8.5. The script never checks the backup's version.
* **Fix:** The script reads $CONFIG['version'] from the backup's config.php and restores the application only when the major version is 33 or higher. For older versions it restores only DB/config and tells the admin to re-run setup, which walks the upgrade chain from the restored version.
* **Affects:** v78 no, PR #2603 yes. Origin: new on 26.04 (package/OS change, not handled by the port).
* **Evidence:** v78 ships nextcloud_ver=27.1.11 with PHP_VER=8.0 (v78:setup/functions.sh:8), so on 22.04 every backup's code runs on the same PHP 8.0 and restoring it works. c6118db:setup/functions.sh sets PHP_VER=8.5 and PHP_LEGACY_VER=8.2, with nextcloud_ver=34.0.3. c6118db:tools/owncloud-restore.sh runs `service php8.5-fpm stop` and then copies owncloud-install without any version check. In 7e56f5a:setup/nextcloud.sh the backup is taken once before the InstallNextcloud chain 27.1.11 ... 33.0.10, and the comment says NC 27 runs with PHP 8.2.
* **Report upstream:** PR #2603: the PR added the PHP 8.5 and upgrade-chain setup but did not adapt the restore script to it.
* **Found by:** audit; **commit:** `7e56f5a`; **fixed in:** v78-r2604.0-rc1

### B30

**owncloud-restore.sh wipes Nextcloud and reports "Done" when the backup has no application code** (medium, Tools)

* **Symptom:** If the admin restores a backup directory that has only owncloud.db and config.php (for example one taken on a fresh box with restored user-data), the script deletes /usr/local/lib/owncloud. It then prints cp/chmod/ln/occ errors and still says "Done", which leaves Nextcloud without an installation. A directory that has config.php but no owncloud.db passes validation as well.
* **Cause:** setup/nextcloud.sh copies /usr/local/lib/owncloud into owncloud-install only when that directory exists (`if [ -d /usr/local/lib/owncloud/ ]`). The restore script nevertheless runs `rm -rf` followed by an unconditional `cp -r "$1/owncloud-install"` with no check and no `set -e`. Its validation tests only `$1/config.php`.
* **Fix:** The script now requires both config.php and owncloud.db, always restores the DB and config, and copies the application only if owncloud-install exists. Otherwise it leaves the application directory absent and tells the admin to run 'sudo mailinabox'.
* **Affects:** v78 yes, PR #2603 yes. Origin: upstream (also in v78 on 22.04).
* **Evidence:** v78:tools/owncloud-restore.sh has `if [ ! -f "$1/config.php" ]` as its only check, then `rm -rf /usr/local/lib/owncloud/` and `cp -r  "$1/owncloud-install" /usr/local/lib/owncloud`, and ends with an unconditional `echo "Done"`. c6118db:tools/owncloud-restore.sh is identical apart from php8.0->php8.5. In v78:setup/nextcloud.sh (lines ~181-193) the backup copies owncloud-install only `if [ -d /usr/local/lib/owncloud/ ]`, so backups without code also occur on 22.04, for example on a reinstall over restored STORAGE_ROOT.
* **Report upstream:** MIAB main: the missing-code/missing-db handling and the false "Done" are present unchanged in v78 and are not tied to 26.04.
* **Found by:** audit; **commit:** `7e56f5a`; **fixed in:** v78-r2604.0-rc1

### B31

**Z-Push CalDAV sync fails with HTTP 500 when a client sends an RTF body (undefined MBSTRING_OVERLOAD)** (medium, Z-Push)

* **Symptom:** When an ActiveSync client (e.g. Outlook or a mobile device) creates or changes a calendar appointment or task with an RTF body, the Sync request fails with HTTP 500. The change never reaches CalDAV/Nextcloud, and the client keeps retrying.
* **Cause:** Z-Push 2.7.7 include/z_RTF.php still reads it without a guard in byte_strlen()/byte_substr(). loadrtf() calls uncompress(), and uncompress() calls byte_substr() on its first line, so any RTF body throws an Error 'Undefined constant "MBSTRING_OVERLOAD"'. index.php's catch (Exception) does not catch it.
* **Fix:** conf/zpush/backend_caldav.php (installed as backend/caldav/config.php and require_once'd at caldav.php:29) now defines MBSTRING_OVERLOAD as 0 if it is missing, so z_RTF falls back to plain strlen/substr.
* **Affects:** v78 yes, PR #2603 yes. Origin: upstream (also in v78 on 22.04).
* **Evidence:** loadrtf() at :94-95 first calls uncompress(), which immediately calls byte_substr($src,0,16) at z_RTF.php:117 and byte_strlen at :119 (before any length or magic check), so the undefined constant is hit for any RTF payload, even an empty or malformed one; the byte_strlen call at :96 is only reached after a successful uncompress. The resulting Error is not caught by index.php:159 (catch (Exception)), so PHP-FPM ends the request with HTTP 500.
* **Report upstream:** Z-Push (Z-Hub/Z-Push): the root cause is the unguarded constant in include/z_RTF.php, and the right fix there is a defined() guard. MIAB main as well, because v78 on PHP 8.0 has the same bug and the one-line define in conf/zpush/backend_caldav.php is a workaround that can be sent upstream. PR #2603 inherits it but did not cause it.
* **Found by:** late review; **commit:** `09b9610`; **fixed in:** v78-r2604.0-rc2

### B32

**Z-Push autodiscover fails with HTTP 500: DAV_SSL_VERIFY undefined (Z-Push 2.7.7)** (medium, Z-Push)

* **Symptom:** ActiveSync autodiscover requests (e.g. Outlook/mobile clients setting up an account automatically) fail with HTTP 500 as soon as the combined backend logs in to CalDAV. Clients cannot auto-configure the account; manual server entry on the main ActiveSync endpoint is not affected.
* **Cause:** Z-Push 2.7.7's CalDAV/CardDAV clients read the constant DAV_SSL_VERIFY on every request (include/z_caldav.php:282, include/z_carddav.php:830). On the main endpoint it is defined in config.php (line 429), and ZPush::CheckConfig() (lib/core/zpush.php:445) also sets DAV_SSL_VERIFY_AUTO as a fallback. index.php calls that method. The autodiscover endpoint loads its own config (MIAB's conf/zpush/autodiscover_config.php, copied to /usr/local/lib/z-push/autodiscover/config.php) and runs only ZPushAutodiscover::CheckConfig() (autodiscover.php:43/315), which has no such fallback. BackendCombined logs in to IMAP first, then to CalDAV. CalDAV's Logon() calls CheckConnection(), and that request reads the undefined constant. PHP 8 then throws an Error. The try blocks in autodiscover.php only catch Exception, so the Error stays uncaught and the request ends with HTTP 500.
* **Fix:** Adds `if (!defined('DAV_SSL_VERIFY')) define('DAV_SSL_VERIFY', DAV_SSL_VERIFY_AUTO);` to conf/zpush/autodiscover_config.php, which keeps certificate verification on except for the loopback address (127.0.0.1) the MIAB CalDAV/CardDAV backends use.
* **Affects:** v78 yes, PR #2603 yes. Origin: upstream (also in v78 on 22.04).
* **Evidence:** Z-Push 2.7.7 source checked: z_caldav.php:282-284 and z_carddav.php:830-832 read DAV_SSL_VERIFY without a defined() guard. The constants DAV_SSL_VERIFY_OFF/ON/AUTO are defined in lib/core/zpushdefs.php:1068-1070, which composer autoload_files loads, so the fix line itself resolves. ZPush::CheckConfig() has a defined() fallback, but ZPushAutodiscover::CheckConfig() does not. Z-Push 2.7.6 (tag 2.7.6, include/z_caldav.php:229-230, z_carddav.php:780-781) hardcoded CURLOPT_SSL_VERIFYPEER/HOST=false and never used the constant, so the regression starts with 2.7.7. Limit: the effect on v78 is inferred from identical code and the identical Z-Push version, not reproduced on a 22.04 box.
* **Report upstream:** Both. Z-Push (Z-Hub) is the root cause: 2.7.7 added the DAV_SSL_VERIFY default only to ZPush::CheckConfig() and left it out of ZPushAutodiscover::CheckConfig(), so any autodiscover config without the define crashes. MIAB main needs the one-line define in conf/zpush/autodiscover_config.php as a workaround, because v78 bumped to 2.7.7 (#2608). PR #2603 inherits the issue through its own 2.7.7 bump.
* **Found by:** test run; **commit:** `4e28dfe`; **fixed in:** v78-r2604.0-rc1

### B33

**dovecotimap filter ignores login failures on the IPv6 local address** (medium, fail2ban)

* **Symptom:** Failed IMAP/POP3/ManageSieve logins from clients connecting to the box's IPv6 address are never counted, so IPv6 brute-force attackers are not banned.
* **Cause:** The failregex requires an IPv4 local address: 'lip=(\d{1,3}\.){3}\d{1,3}'. A connection over IPv6 logs an IPv6 lip and never matches.
* **Fix:** The new failregex accepts any address after lip= ('lip=[^,>\s]+'), including IPv6.
* **Affects:** v78 yes, PR #2603 yes. Origin: upstream (also in v78 on 22.04).
* **Evidence:** v78:conf/fail2ban/filter.d/dovecotimap.conf and c6118db:conf/fail2ban/filter.d/dovecotimap.conf both end with '... rip=<HOST>, lip=(\d{1,3}\.){3}\d{1,3}(, TLS( handshaking)?(: Disconnected)?)?(, session=<\S+>)?\s*$'. v78 jails.conf whitelists PUBLIC_IPV6, so MIAB expects IPv6 service. On v78 this applies only to boxes with IPv6 configured. No real IPv6 log line from a 22.04 box was checked here.
* **Report upstream:** MIAB main: the IPv4-only lip has been in the upstream filter since before v78 and affects 22.04 IPv6 boxes. PR #2603 carries it unchanged.
* **Found by:** audit; **commit:** `8bbeb60`; **fixed in:** v78-r2604.0-rc1

### B34

**No SSHFP record for ECDSA host keys on the P-384/P-521 curves** (low, DNS)

* **Symptom:** A box whose ECDSA host key uses the nistp384 or nistp521 curve publishes no ECDSA SSHFP record. The key is silently skipped, and there is no error or status-check warning.
* **Cause:** The algorithm_number map only had 'ecdsa-sha2-nistp256'. For the other curves the lookup raised KeyError, which the bare except around the record build swallowed. RFC 6594 assigns SSHFP algorithm 3 to ECDSA on any curve, the same value `ssh-keygen -r` emits.
* **Fix:** Maps ecdsa-sha2-nistp384 and ecdsa-sha2-nistp521 to algorithm 3, and narrows the bare except to (KeyError, ValueError).
* **Affects:** v78 partly, PR #2603 partly. Origin: upstream (also in v78 on 22.04).
* **Evidence:** v78:management/dns_update.py:435-440 algorithm_number = {ssh-rsa:1, ssh-dss:2, ecdsa-sha2-nistp256:3, ssh-ed25519:4}, then `except: pass` at line 467. c6118db:management/dns_update.py:438-442 also has only nistp256 (and with wrong numbers 2/3, fixed separately in 142abba 'Befund 6.2'). 'partly' because only boxes with a non-default ECDSA curve are hit: Ubuntu's default generated ECDSA host key is nistp256. Not verified on a live box: that v78's `ssh-keyscan -t ecdsa` returns a nistp384/521 key. I believe it does, because keyscan's ECDSA type offers all three curves.
* **Report upstream:** MIAB main: a one-line mapping fix that applies to v78 as well. Worth a small PR, but low impact because only non-default host key curves are affected.
* **Found by:** late review; **commit:** `3e77095`; **fixed in:** v78-r2604.0-rc2

### B35

**No SSHFP records (PR) or failed DNS update (v78) when sshd does not listen on IPv4 localhost** (low, DNS)

* **Symptom:** If sshd binds only to the public IP or only to IPv6 (ListenAddress), `ssh-keyscan -4 localhost` fails. On v78 the exception escapes and the DNS update fails; on the PR head the SSHFP records silently disappear.
* **Cause:** SSHFP records were built by connecting to sshd on 127.0.0.1 with ssh-keyscan instead of reading the host keys.
* **Fix:** Records come from the host keys listed by `sshd -T` (later: the public key derived from the private host key), independent of the listen address.
* **Affects:** v78 yes, PR #2603 yes. Origin: upstream (also in v78 on 22.04).
* **Evidence:** v78:management/dns_update.py:455 shell('check_output', ['ssh-keyscan','-4',...,'localhost']) without trap; c6118db:management/dns_update.py:457-466 uses trap=True and returns nothing on a non-zero exit. Derived from the code, not reproduced on a box.
* **Report upstream:** MIAB main and PR #2603, together with the SSHFP-from-key-files change.
* **Found by:** test run; **commit:** `2c7e109`; **fixed in:** v78-r2604.0-rc1

### B36

**SSHFP records flap in and out of the signed zone because ssh-keyscan hits OpenSSH PerSourcePenalties** (low, DNS)

* **Symptom:** The published SSHFP records come and go between DNS updates: on the 26.04 test VM the zone showed 3 SSHFP records, then 2, then none. Each change also bumps the zone serial and forces a re-sign. Clients that use VerifyHostKeyDNS cannot rely on the records.
* **Cause:** build_sshfp_records() ran `ssh-keyscan -4 -t rsa,ecdsa,ed25519 -p <port> localhost` on every DNS zone build. OpenSSH 9.8+ (26.04 ships 10.x) has PerSourcePenalties, whose default noauth penalty refuses repeated connections from a source that connects and leaves without authenticating. Some keyscan connections from localhost were refused, so key types were missing at random. The PR's trap=True path turns a non-zero exit into 'no SSHFP records' instead of an error.
* **Fix:** Builds the SSHFP records from the .pub files of the host keys that `sshd -T` lists (via the new utils.get_ssh_config_values('hostkey'), which returns every hostkey line), so no SSH connection is made and the result is deterministic and matches ssh-keygen -r.
* **Affects:** v78 no, PR #2603 yes. Origin: new on 26.04 (package/OS change, not handled by the port).
* **Evidence:** v78:management/dns_update.py:455 runs `shell("check_output", ["ssh-keyscan", "-4", "-t", "rsa,dsa,ecdsa,ed25519", "-p", str(port), "localhost"])`, but 22.04 ships OpenSSH 8.9, which has no PerSourcePenalties (added in 9.8), so the scan is not throttled there. c6118db:management/dns_update.py:457 still runs `ssh-keyscan -4 -t rsa,ecdsa,ed25519 ... localhost` with trap=True (lines 459-466 skip SSHFP on a non-zero exit) on 26.04/OpenSSH 10.x. Neither v78 nor c6118db mentions PerSourcePenalties anywhere (git grep), so the penalty defaults apply. The flapping (3, then 2, then 0 records) is taken from the commit message about the test VM; I did not reproduce it here. Note: a later fork commit, 3e77095 (Review), refines this fix so the key is derived from the private key with ssh-keygen -y instead of trusting the .pub file.
* **Report upstream:** PR #2603: the bug only appears on 26.04/OpenSSH >= 9.8, which is the PR's target. MIAB main should take it once it supports 24.04+ (24.04 ships OpenSSH 9.6, which has no PerSourcePenalties either, so main is not affected today).
* **Found by:** test run; **commit:** `2c7e109`; **fixed in:** v78-r2604.0-rc1

### B37

**nsd cannot write /var/log/nsd.log; logrotate entry is dead** (low, DNS)

* **Symptom:** Every time nsd starts it logs "Cannot open /var/log/nsd.log for appending (Read-only file system), logging to stderr". /var/log/nsd.log never gets written, so the MIAB logrotate entry /etc/logrotate.d/nsd has nothing to rotate. nsd falls back to stderr, which systemd captures in the journal, so no messages are lost. The only effects are the error line and a useless logfile/logrotate setup.
* **Cause:** setup/dns.sh writes `logfile: "/var/log/nsd.log"` into nsd.conf. The packaged nsd.service runs with ProtectSystem=strict and ReadWritePaths=/var/lib/nsd /etc/nsd /run, so /var/log is read-only for nsd.
* **Fix:** nsd.conf now uses `log-only-syslog: yes` (the package default) in place of the logfile line, and setup runs `rm -f /etc/logrotate.d/nsd` where it used to write the logrotate stanza.
* **Affects:** v78 yes, PR #2603 yes. Origin: upstream (also in v78 on 22.04).
* **Evidence:** The 22.04 unit was checked: Ubuntu jammy's debian/nsd.service (git.launchpad.net/ubuntu/+source/nsd, branch ubuntu/jammy) has ProtectSystem=strict and ReadWritePaths=/var/lib/nsd /etc/nsd /run, the same as the 26.04 package nsd 4.14.0-1. So affects_v78=yes is confirmed independently of the commit message. Debian's shipped /etc/nsd/nsd.conf sets `log-only-syslog: yes`, which is the 'package default' the fix restores. The nsd 4.14.0-1 package ships no /etc/logrotate.d/nsd.
* **Report upstream:** MIAB main: the logfile directive and the logrotate stanza come from upstream (#1434) and are still in v78, so every install whose nsd.service has the sandbox gets the error. PR #2603 copied the lines unchanged and could take the fix too.
* **Found by:** audit; **commit:** `c42df47`; **fixed in:** v78-r2604.0-rc1

### B38

**Control panel mailbox usage not maintained: quota driver defaults to count, maildirsize never written** (low, Dovecot)

* **Symptom:** In the admin panel's user list, the mailbox size, quota and percentage show '?' for mailboxes that have no maildirsize file (e.g. on fresh 26.04 installs). For migrated mailboxes they show values from the old 2.3 maildirsize file that are never updated.
* **Cause:** In Dovecot 2.4, `quota maildir { }` only names the quota root. The driver comes from quota_driver, whose default in Dovecot 2.4 is count, and count does not write the Maildir++ maildirsize file. management/mailconfig.py reads that file to compute box_size/box_quota and falls back to '?' if it is missing.
* **Fix:** Declares the quota root as `quota "User quota" { quota_driver = maildir }`, so Dovecot keeps writing maildirsize.
* **Affects:** v78 no, PR #2603 yes. Origin: PR #2603 port.
* **Evidence:** c6118db:conf/dovecot-90-quota.conf lines 1-3 `quota maildir { quota_storage_grace = 100M }` set no quota_driver. v78:setup/mail-dovecot.sh:79 sets `quota = maildir` in the 2.3 plugin block, which selects the maildir driver. management/mailconfig.py:149 opens `mail/mailboxes/{domain}/{user}/maildirsize`, and the except branch sets box_size/box_quota/percent = '?'. The default driver being count is taken from the Dovecot 2.4 quota docs (the initial review names `quota_driver = count` or `maildir` as options). The '?' display on a 26.04 test box is not recorded in the repo or test report: the symptom is derived from the code, not observed.
* **Report upstream:** PR #2603: the port's 90-quota.conf relies on the 2.4 default driver, which breaks the existing usage display in the control panel.
* **Found by:** initial review; **commit:** `6526ad7`; **fixed in:** v78-r2604.0-rc1

### B39

**ManageSieve listens on deprecated port 2000 on all interfaces** (low, Dovecot)

* **Symptom:** On a 26.04 box Dovecot opens a second ManageSieve listener on TCP 2000 on all interfaces, next to the intended 4190. The status checks do not monitor it, and it is reachable from outside whenever ufw is off (DISABLE_FIREWALL=1).
* **Cause:** The Dovecot 2.4 package's conf.d/20-managesieve.conf on 26.04 enables the inet_listener sieve_deprecated (port 2000). The PR's setup/mail-dovecot.sh never touches the managesieve-login service, so the package default stays in place.
* **Fix:** Adds `service managesieve-login { inet_listener sieve_deprecated { port = 0 } }` to the 99-local.conf heredoc in setup/mail-dovecot.sh, so only 4190 is left.
* **Affects:** v78 no, PR #2603 yes. Origin: new on 26.04 (package/OS change, not handled by the port).
* **Evidence:** c929f6f adds the block at setup/mail-dovecot.sh:147-153 with the comment "The 26.04 package's 20-managesieve.conf also opens the deprecated ManageSieve port 2000 on all interfaces". `git grep sieve_deprecated` finds nothing in v78 or c6118db, so neither version sets a managesieve-login listener. c6118db:management/status_checks.py:42 only checks port 4190. With ufw on (c6118db:setup/system.sh:275-295, default deny, only named ports allowed) the port is blocked from outside, so the exposure is mainly when DISABLE_FIREWALL is set. The fail2ban dovecot jail (conf/fail2ban/jails.conf:10-15) has no port restriction. Not verified in the repo, so it rests on the commit text plus my knowledge of the stock 2.3 config: the 22.04 Dovecot 2.3 package ships sieve_deprecated commented out, which is why v78 is marked as not affected.
* **Report upstream:** PR #2603: the port should disable the listener the 26.04 package enables. Not MIAB main, because v78 on 22.04 does not have it.
* **Found by:** audit; **commit:** `c929f6f`; **fixed in:** v78-r2604.0-rc1

### B40

**Version status check compares a 26.04 box against the 22.04 upstream tag** (low, Management)

* **Symptom:** With the version check enabled (privacy setting off), a 26.04 box gets a permanent status-check error: "A new version of Mail-in-a-Box is available... The latest version is v78", plus upgrade instructions at mailinabox.email that do not work on 26.04. Or, on the fork, the check never shows up to date, because the running tag (v78-r2604.0-rcX) can never equal upstream's TAG.
* **Cause:** get_latest_miab_version() fetches https://mailinabox.email/setup.sh and takes the first TAG= line, which is upstream's 22.04 tag (v78). check_miab_version() compares that string with `git describe` of the local checkout, so a 26.04 install is always measured against the 22.04 release line.
* **Fix:** get_latest_miab_version() now reads the TAG from the fork's setup/bootstrap.sh (at that time on the internal Gitea server, since the move to GitHub from https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/setup/bootstrap.sh), where the 26.04 branch is the first TAG= line, and the upgrade hint points to the fork's repository URL.
* **Affects:** v78 no, PR #2603 yes. Origin: PR #2603 port.
* **Evidence:** v78:management/status_checks.py:988 and c6118db:management/status_checks.py:988 are identical: re.search(b'TAG=(.*)', urlopen("https://mailinabox.email/setup.sh?ping=1")...). check_miab_version (c6118db lines 992-1010) reports an error whenever this_ver != latest_ver. On v78/22.04, `git describe` yields v78 and the first TAG= in upstream bootstrap is v78, so it reports OK (not affected). On a PR-head box, the PR changes neither the URL nor bootstrap.sh's TAG ordering, so the latest version is always the 22.04 tag. The exact local `git describe` output on a PR-head install was not checked: it depends on how the clone was made, probably v77 since the branch is based on df7f245e. The mismatch and the misleading upgrade hint follow from the code either way. The fork comment in v78 bootstrap.sh says that the first TAG= line must be the one shown in status checks, and a85fa0d puts the 26.04 branch first for this reason.
* **Report upstream:** PR #2603: once 26.04 is supported upstream, bootstrap.sh must list the 26.04 TAG first (or the check must pick the TAG for the running OS), or 26.04 boxes get false upgrade warnings. The fork's URL change itself is fork-specific and not for upstream.
* **Found by:** initial review; **commit:** `a85fa0d`; **fixed in:** v78-r2604.0-rc1

### B41

**daemon.py /logout uses return inside finally (SyntaxWarning on Python 3.14)** (low, Management)

* **Symptom:** On Ubuntu 26.04, Python 3.14 prints "SyntaxWarning: 'return' in a 'finally' block" when it compiles management/daemon.py. The daemon is started as gunicorn wsgi:app with PYTHONPATH=$PWD/management (setup/management.sh), so daemon.py is imported as a module and its bytecode is cached in management/__pycache__. The warning therefore appears in the mailinabox service journal only when the .pyc is rebuilt, i.e. on the first start after install or after daemon.py changes, not on every start. Logout itself keeps working.
* **Cause:** logout() returns json_response({"status": "ok"}) from a finally: block. PEP 765 makes Python 3.14 warn about this at compile time. The same construct also silently swallows any exception other than ValueError that auth_service.authenticate() raises, and answers ok anyway.
* **Fix:** Removes the finally: clause and returns json_response({"status": "ok"}) after the try/except, so normal logout still answers ok and an unexpected exception now gives a 500 instead of being swallowed.
* **Affects:** v78 no, PR #2603 yes. Origin: new on 26.04 (package/OS change, not handled by the port).
* **Evidence:** v78:management/daemon.py lines 170-178 and c6118db:management/daemon.py lines 170-178 are identical: `except ValueError:\n\t\tpass\n\tfinally:\n\t\treturn json_response({ "status": "ok" })`. The construct dates back to upstream code from before the ruff cleanups (git log -L shows it unchanged through 2b42685/13b38cc/3fa0819). The warning comes from PEP 765, which exists only in Python 3.14+, so the Python 3.10 on 22.04 under v78 does not show it. v78 does have the latent swallowing of non-ValueError exceptions, but that is visible only when authenticate() fails unexpectedly. It is not a normal-operation symptom, so I set affects_v78 to no; I did not test whether such an exception can actually happen. The PR head targets 26.04 (Python 3.14) with the unchanged code, so the warning appears there.
* **Report upstream:** MIAB main: a two-line fix that becomes relevant as soon as upstream runs on Python 3.14+, and it also stops non-ValueError exceptions being swallowed on every release. Also PR #2603, because the port targets Python 3.14 and still has the construct.
* **Found by:** audit; **commit:** `1c7dacc`; **fixed in:** v78-r2604.0-rc1

### B42

**Nextcloud opcache settings only reach PHP CLI, not PHP-FPM, on PHP 8.5** (low, Nextcloud)

* **Symptom:** The web SAPI (php8.5-fpm serving Nextcloud, Roundcube, Z-Push) ignores the Nextcloud-recommended opcache settings and runs on compiled defaults. In practice only opcache.revalidate_freq differs (2 instead of 1). Any later raise of these values, for example interned_strings_buffer=16, would silently not apply to the web interface.
* **Cause:** Up to PHP 8.4, the editconf target cli/conf.d/10-opcache.ini is a symlink to the shared mods-available/opcache.ini that FPM also loads. PHP 8.5 has opcache built in and ships no opcache.ini, so the port switched the target to cli/php.ini, which only the CLI SAPI reads.
* **Fix:** Writes the same opcache values (without enable_cli) into /etc/php/$PHP_VER/fpm/php.ini as well. FPM is restarted at the end of the script.
* **Affects:** v78 no, PR #2603 yes. Origin: PR #2603 port.
* **Evidence:** v78:setup/nextcloud.sh:399 `tools/editconf.py /etc/php/"$PHP_VER"/cli/conf.d/10-opcache.ini`. v78:tools/editconf.py:147 writes via `open(filename, "w")`, which follows the symlink into mods-available/opcache.ini (shared by cli and fpm conf.d). That conf.d symlink layout is standard Debian/ondrej PHP packaging and was not checked on a live 22.04 box here. PR commit 191cffe changed the line to `/etc/php/"$PHP_VER"/cli/php.ini`, and c6118db:setup/nextcloud.sh:480 writes only cli/php.ini. No fpm/php.ini opcache edit exists in c6118db or 6a15bcf^ (:479). The claim that the effective difference is only revalidate_freq is based on PHP's compiled defaults (interned_strings_buffer=8, max_accelerated_files=10000, memory_consumption=128, save_comments=1) and was not measured on a box.
* **Report upstream:** PR #2603. The regression comes from the port's switch to cli/php.ini for PHP 8.5; v78 on 22.04 is not affected.
* **Found by:** audit; **commit:** `6a15bcf`; **fixed in:** v78-r2604.0-rc1

### B43

**Port switches DH parameters to a new dh4096.pem, adding minutes of generation on fresh installs and the first setup run on upgraded boxes** (low, Setup)

* **Symptom:** A fresh install, and the first setup run on an existing box that already has dh2048.pem, spends many extra minutes in `openssl dhparam ... 4096` ("Creating initial SSL certificate and perfect forward secrecy Diffie-Hellman parameters..."). The existing dh2048.pem is left unused. Only DHE cipher suites, which come after the ECDHE suites in the cipher lists, use the file.
* **Cause:** PR #2603 renamed the DH parameter file from dh2048.pem to dh4096.pem and raised the size to 4096 bits in setup/ssl.sh, conf/nginx-ssl.conf, setup/mail-postfix.sh and setup/mail-dovecot.sh. Ubuntu 26.04 did not require this. Because the file name changed, setup/ssl.sh's existence check fails on boxes that already have dh2048.pem, so it always generates new 4096-bit parameters.
* **Fix:** Points nginx (ssl_dhparam), Postfix (smtpd_tls_dh1024_param_file), Dovecot 2.4 (ssl_server_dh_file) and the generation and check in setup/ssl.sh back to $STORAGE_ROOT/ssl/dh2048.pem with 2048 bits, as in upstream MIAB.
* **Affects:** v78 no, PR #2603 yes. Origin: PR #2603 port.
* **Evidence:** v78: conf/nginx-ssl.conf:5 `ssl_dhparam STORAGE_ROOT/ssl/dh2048.pem;`, setup/mail-dovecot.sh:117 `ssl_dh=<$STORAGE_ROOT/ssl/dh2048.pem`, setup/mail-postfix.sh:143 `dh2048.pem`, setup/ssl.sh:96-97 `openssl dhparam -out "$STORAGE_ROOT/ssl/dh2048.pem" 2048`. c6118db (and d817620, after the v78 merge): the same lines read dh4096.pem, and setup/ssl.sh:97 is `openssl dhparam -out "$STORAGE_ROOT/ssl/dh4096.pem" 4096`. Introduced in the PR's squashed commit 191cffe (its message says "dovecot ssl / ssl dh upgrade to 4096" and "changed to dh4096.pem"). HEAD matches v78 again (dh2048.pem), and CHANGELOG-fork.md lists "TLS: back to MIAB's dh2048.pem". This is a cost/compatibility regression, not a functional failure: TLS works with either file. The "many minutes" figure comes from the commit message; it was not measured here.
* **Report upstream:** PR #2603: suggest keeping dh2048.pem, because the rename forces regeneration on upgraded boxes and slows fresh installs without a 26.04 requirement. Not relevant for MIAB main or Z-Push.
* **Found by:** initial review; **commit:** `e602241`; **fixed in:** v78-r2604.0-rc1

### B44

**Timezone check relies on /etc/timezone, which 26.04's tzdata no longer writes** (low, Setup)

* **Symptom:** A non-interactive run writes 'Etc/UTC' to /etc/timezone and restarts rsyslog on the first run (and again after a tzdata upgrade removes the file). It does not change /etc/localtime, so the system zone is not actually set and the stale /etc/timezone can disagree with the real zone in /etc/localtime.
* **Cause:** setup/system.sh treats a missing /etc/timezone as 'no timezone configured'. On 26.04 tzdata keeps the zone only in the /etc/localtime symlink, so the file is always missing.
* **Fix:** Both branches now check /etc/localtime. The non-interactive default symlinks /etc/localtime to /usr/share/zoneinfo/Etc/UTC instead of writing /etc/timezone. Any leftover /etc/timezone is removed.
* **Affects:** v78 no, PR #2603 yes. Origin: new on 26.04 (package/OS change, not handled by the port).
* **Evidence:** v78:setup/system.sh lines 178 and 188 ('if [ ! -f /etc/timezone ]') and line 190 ('echo "Etc/UTC" > /etc/timezone'). c6118db:setup/system.sh lines 180, 190 and 192 are identical. On 22.04 (v78) tzdata still maintains /etc/timezone, so the check works there; that statement comes from the commit message and known Ubuntu packaging, not from a 22.04 box. Z-Push and Nextcloud no longer read /etc/timezone in c6118db (git grep finds only system.sh), while v78 zpush.sh lines 57 and 83 and nextcloud.sh line 324 still 'cat /etc/timezone'.
* **Report upstream:** PR #2603: the port keeps the 22.04-era /etc/timezone check, which misbehaves on 26.04. Not relevant for MIAB main on 22.04.
* **Found by:** audit; **commit:** `832f3a7`; **fixed in:** v78-r2604.0-rc1

### B45

**wget_verify only accepts SHA1, so pins cannot be checked against published upstream checksums** (low, Setup)

* **Symptom:** Download pins (Nextcloud, Nextcloud apps, Roundcube, carddav, Z-Push, jQuery, Bootstrap) must be SHA1. No upstream publishes SHA1 any more, so a maintainer can only copy the hash out of a failed setup run (trust on first download) instead of comparing it with the vendor's SHA256. Integrity checking also relies on SHA1, which is a weak algorithm.
* **Cause:** wget_verify always ran `sha1sum --check --strict` and printed `sha1sum` on mismatch, so every pin had to be a 40-hex SHA1. Nextcloud publishes only .sha256/.sha512, GitHub release assets carry a SHA256 digest and roundcube.net lists SHA256.
* **Fix:** wget_verify chooses sha256sum/sha512sum/sha1sum from the hex length (64/128/40), accepts an optional matching 'sha256:'-style prefix, rejects non-hex or wrong-length hashes, also prints the SHA256 on mismatch, and Z-Push 2.7.7 is re-pinned by the SHA256 of its tag archive.
* **Affects:** v78 yes, PR #2603 yes. Origin: upstream (also in v78 on 22.04).
* **Evidence:** HEAD:setup/nextcloud.sh:25-26 (nextcloud_hash, with the SHA256 comment at :22-24) and management.sh:90/99 now use SHA256 pins, done in other commits (9327323, 26f8e84, 8e5e779)
* **Report upstream:** MIAB main: the SHA1-only wget_verify is in v78 and affects every maintainer who bumps a pin. The change is generic and does not depend on 26.04, so it could also go into PR #2603.
* **Found by:** initial review; **commit:** `7041fb3`; **fixed in:** v78-r2604.0-rc1

### B46

**wget_verify overwrites the caller's global URL/HASH/DEST variables** (low, Setup)

* **Symptom:** Nothing an admin can see in v78 or the PR. After a call, the shell variables HASH, URL and DEST hold the values of the last download, so a sourced setup script that reads its own $HASH after a wget_verify call would get another file's hash.
* **Cause:** wget_verify assigned URL=$1, HASH=$2, DEST=$3 without `local`. The setup scripts are sourced into one shell by start.sh, so these assignments overwrite globals of the same name. setup/webmail.sh itself defines a global HASH (the Roundcube pin) and then calls wget_verify with $CARDDAV_HASH.
* **Fix:** URL, HASH, DEST, HASHCMD, PREFIX and CHECKSUM are declared `local` inside wget_verify.
* **Affects:** v78 no, PR #2603 no. Origin: upstream (also in v78 on 22.04).
* **Evidence:** v78:setup/functions.sh:190-192 `URL=$1` / `HASH=$2` / `DEST=$3` (no local); v78:setup/start.sh:116-118 `source setup/webmail.sh` / nextcloud.sh / zpush.sh in the same shell; v78:setup/webmail.sh:40 `HASH=15c7...` is read only at :72 (Roundcube download), before the carddav call at :88 sets the global HASH to CARDDAV_HASH. No later reader of $HASH/$URL/$DEST exists in setup/ or tools/ (git grep on 7041fb3~1), so this defect is latent and cannot be observed. c6118db has the same function unchanged.
* **Report upstream:** MIAB main, optional: a latent cleanup only, worth sending together with the hash-algorithm change rather than reporting it as a bug on its own.
* **Found by:** initial review; **commit:** `7041fb3`; **fixed in:** v78-r2604.0-rc1

### B47

**Failed sa-learn runs are logged as failed Sieve pipe actions** (low, Spam)

* **Symptom:** A learning run that fails (for example on a Bayes lock timeout) makes sa-learn exit non-zero. Because the wrapper ends with exec, that exit code becomes the pipe program's result, so Dovecot logs a failed Sieve pipe action (a runtime error) for the user's IMAP move. The move itself still succeeds.
* **Cause:** The PR's wrappers `exec /usr/bin/sa-learn --spam|--ham`, so sa-learn's exit code and stdout go straight to Dovecot. The 22.04 sa-learn-pipe.sh discarded stdout and always exited 0.
* **Fix:** The wrappers now run sa-learn with stdout sent to /dev/null and then `exit 0`. stderr is kept for diagnosis.
* **Affects:** v78 no, PR #2603 yes. Origin: PR #2603 port.
* **Evidence:** c6118db:conf/sa-learn-spam.sh:6 `exec /usr/bin/sa-learn --spam` (same in sa-learn-ham.sh). v78:setup/spamassassin.sh:176-181 sa-learn-pipe.sh: `/usr/bin/sa-learn $* /tmp/sendmail-msg-$$.txt > /dev/null` ... `exit 0`. The commit message describes the effect (pipe failure logged as a runtime error). It was not reproduced in this review.
* **Report upstream:** PR #2603. The wrappers come from there.
* **Found by:** audit; **commit:** `f7878b8`; **fixed in:** v78-r2604.0-rc1

### B48

**Unused spamd daemon runs on 26.04** (low, Spam)

* **Symptom:** A spamd daemon runs next to spampd, using memory and listening on localhost:783, although MIAB never uses it.
* **Cause:** On 26.04 spamd is a separate package that comes in through Recommends (spamassassin -> spamc -> spamd) and is enabled by default. spampd runs SpamAssassin in-process, and neither the port nor upstream disables spamd.
* **Fix:** If spamd.service exists, setup now runs `systemctl disable --now spamd.service`.
* **Affects:** v78 no, PR #2603 yes. Origin: new on 26.04 (package/OS change, not handled by the port).
* **Evidence:** c6118db:setup/spamassassin.sh has no handling of spamd.service (grep only finds the comment at line 127). v78:setup/spamassassin.sh does not disable it either. On 22.04 the spamd daemon is part of the spamassassin package, and whether its unit is enabled by default there was not verified, so affects_v78=no rests on the commit's statement that the default-enabled separate package is new on 26.04. Fixed in ecc169a:setup/spamassassin.sh:38-40.
* **Report upstream:** PR #2603 (low priority): a resource and hygiene issue on 26.04 installs, no functional failure.
* **Found by:** audit; **commit:** `ecc169a`; **fixed in:** v78-r2604.0-rc1

### B49

**owncloud-restore.sh uses undefined $PHP_VER for occ** (low, Tools)

* **Symptom:** The final `occ maintenance:mode --off` runs through plain `php` instead of the intended versioned binary. It works only if /usr/bin/php happens to point to a suitable PHP version.
* **Cause:** The script sources /etc/mailinabox.conf, which does not set PHP_VER, and never sources setup/functions.sh. As a result `"php$PHP_VER"` expands to `php`, which goes through the update-alternatives link.
* **Fix:** The script now defines PHP_VER=8.5 itself (kept in sync with setup/functions.sh) and uses php"$PHP_VER" for the fpm service, for the version check and for occ.
* **Affects:** v78 partly, PR #2603 partly. Origin: upstream (also in v78 on 22.04).
* **Evidence:** v78:tools/owncloud-restore.sh line `sudo -u www-data "php$PHP_VER" /usr/local/lib/owncloud/occ maintenance:mode --off`. PHP_VER is defined only in setup/functions.sh (v78: PHP_VER=8.0, c6118db: PHP_VER=8.5), and the script hard-codes php8.0-fpm / php8.5-fpm for the service. Whether plain `php` points to the wrong version depends on the alternatives state of the box. I did not verify this; on boxes where only one PHP CLI is installed, or where the highest version wins in auto mode, it is probably harmless. That is why the impact is rated 'partly'.
* **Report upstream:** MIAB main: the latent undefined variable is present unchanged in v78. It is a small cleanup, best reported together with the missing-code bug.
* **Found by:** audit; **commit:** `7e56f5a`; **fixed in:** v78-r2604.0-rc1

### B50

**Roundcube 1.7 static.php assets rely on PHP-FPM cgi.fix_pathinfo (no PATH_INFO passed)** (low, nginx)

* **Symptom:** With the default PHP setting nothing goes wrong. If an admin sets cgi.fix_pathinfo=0 in PHP-FPM, a common hardening step, every Roundcube 1.7 CSS, JS and image request (/mail/static.php/skins/..., /mail/static.php/plugins/...) fails, and the webmail UI loads without styles or scripts.
* **Cause:** The nested Roundcube location only matched `\.php$`, so /mail/static.php/<path> URIs fell through to the unanchored server-level `location ~ /mail/.*\.php` block. That block used `fastcgi_split_path_info ^/mail(/.*)()$`, which sent SCRIPT_FILENAME=public_html//static.php/skins/... and no PATH_INFO. Splitting the path into script and PATH_INFO was therefore left to PHP-FPM's cgi.fix_pathinfo=1 guessing.
* **Fix:** The nested location now matches `\.php(/|$)`, splits `^/mail(/.+?\.php)(/.*)?$`, passes `fastcgi_param PATH_INFO $fastcgi_path_info` and drops the server-level `~ /mail/.*\.php` fallback block, which is now unreachable. The /mail/config/ 403 block stays.
* **Affects:** v78 no, PR #2603 yes. Origin: PR #2603 port.
* **Evidence:** c6118db:conf/nginx-alldomains.conf has `location /mail/ { alias /usr/local/lib/roundcubemail/public_html/; ... location ~ \.php$ { fastcgi_split_path_info ^/mail(/.*)()$; ... } }` with no PATH_INFO param, plus the server-level `location ~ /mail/.*\.php` fallback. 12b0d72~1 is identical (unchanged through the d817620 merge). c6118db:setup/webmail.sh pins VERSION=1.7.4 (1.7.5 before 12b0d72). v78:conf/nginx-alldomains.conf instead has `location /mail/ { alias /usr/local/lib/roundcubemail/; }` and v78:setup/webmail.sh has VERSION=1.6.20, so on v78 static assets are served directly as files and do not go through static.php/PATH_INFO. Neither v78 nor 12b0d72 sets cgi.fix_pathinfo anywhere (`git grep fix_pathinfo` finds only the new comment in 12b0d72), so the PHP default of 1 applies and the bug stays hidden. The fix_pathinfo=0 breakage comes from the commit message's analysis. It was not reproduced on a box as far as the repo shows.
* **Report upstream:** PR #2603: the nested `\.php$` location without PATH_INFO and the leftover unanchored server-level `~ /mail/.*\.php` block come from the port's nginx config for Roundcube 1.7 public_html. MIAB main (v78, Roundcube 1.6 served from the install root) is not affected.
* **Found by:** audit; **commit:** `12b0d72`; **fixed in:** v78-r2604.0-rc1

### B51

**Dovecot 2.3 setting names kept in 10-auth.conf/10-ssl.conf stop Dovecot 2.4 on boxes upgraded in place** (high, Dovecot)

* **Symptom:** After a release upgrade from 22.04/24.04 (old configuration files kept), Dovecot 2.4 refuses to start and setup stops at the first Dovecot restart.
* **Cause:** setup/mail-dovecot.sh edits 10-auth.conf and 10-ssl.conf with editconf.py, which only adds the 2.4 names (auth_allow_cleartext, ssl_server_*) and never removes the 2.3 names disable_plaintext_auth, ssl_cert, ssl_key, ssl_dh, ssl_dh_parameters_length, ssl_prefer_server_ciphers.
* **Fix:** The 2.3 names are commented out with editconf.py -e. The in-place tool additionally starts from a pristine /etc/dovecot.
* **Affects:** v78 no, PR #2603 yes. Origin: 26.04 change.
* **Found by:** in-place test (T3 on a copy of a production box) and review; **commit:** `bdbb5c3`; **fixed in:** v78-r2604.0-rc3

### B52

**dovecot-antispam leftovers (99-local-spampd.conf, package, sa-learn-pipe.sh) of older Mail-in-a-Box break Dovecot 2.4** (medium, Spam)

* **Symptom:** On a box upgraded in place, Dovecot 2.4 rejects the plugin { antispam_* } settings of v74 and the dovecot-antispam 2.3 module.
* **Cause:** Mail-in-a-Box before the port trained SpamAssassin with dovecot-antispam; the port switched to IMAPSieve but never removed the old file and package.
* **Fix:** setup/spamassassin.sh removes the file, the pipe script and the package.
* **Affects:** v78 no, PR #2603 yes. Origin: 26.04 change.
* **Found by:** in-place test (T3 on a copy of a production box) and review; **commit:** `0c17784`; **fixed in:** v78-r2604.0-rc3

### B53

**Broken management venv is kept after a release upgrade, pip fails** (high, Management)

* **Symptom:** Setup stops in setup/management.sh at pip install with 'bad interpreter' on a release-upgraded box.
* **Cause:** The version check tested `-x $venv/bin/python3`, which is false for the dangling link to the removed python3.10/3.12, so the old venv was neither deleted nor recreated.
* **Fix:** The check runs the interpreter; when it fails or the version differs, the venv is rebuilt.
* **Affects:** v78 no, PR #2603 yes. Origin: PR #2603.
* **Found by:** in-place test (T3 on a copy of a production box) and review; **commit:** `22a4cea`; **fixed in:** v78-r2604.0-rc3

### B54

**bootstrap.sh fails with 'Update failed' over an upstream checkout** (low, Setup)

* **Symptom:** On a box with an upstream ~/mailinabox the curl installer stops with 'Update failed. Did you modify something?'.
* **Cause:** The fork's tags do not exist in the upstream clone's origin.
* **Fix:** bootstrap.sh names the foreign origin and points to tools/upgrade-in-place-to-2604.sh.
* **Affects:** v78 no, PR #2603 no. Origin: Fork.
* **Found by:** in-place test (T3 on a copy of a production box) and review; **commit:** `5e851f7`; **fixed in:** v78-r2604.0-rc3

### B55

**PPA sources and keys of earlier releases stay trusted; Launchpad sury builds are not moved back to Ubuntu** (medium, System/apt)

* **Symptom:** After a release upgrade, ondrej and duplicity PPA files of jammy/noble (also *.distUpgrade) remain, their keys stay in trusted.gpg.d for every source, and php-common/libgd3 builds from ppa:ondrej get no updates.
* **Cause:** setup/system.sh only knew the sury source and the new version format (+0~…gbpHASH), not the Launchpad format (+deb.sury.org+N).
* **Fix:** Old PPA sources and keys are removed, the duplicity PPA is added again for the current release, the downgrade loop matches both formats.
* **Affects:** v78 no, PR #2603 yes. Origin: PR #2603.
* **Found by:** in-place test (T3 on a copy of a production box) and review; **commit:** `fcbfe3d`; **fixed in:** v78-r2604.0-rc3

### B56

**pollinate cache owned by root makes setup fail on boxes upgraded in place** (low, System)

* **Symptom:** Setup stops right after 'Initializing system random number generator...' with 'cannot create /var/cache/pollinate/log: Permission denied'.
* **Cause:** A pollinate log created by root on an older release; setup runs pollinate as the pollinate user with set -e.
* **Fix:** A failing pollinate is reported and does not stop setup (seeding is not required).
* **Affects:** v78 partly, PR #2603 partly. Origin: Upstream.
* **Found by:** in-place test (T3 on a copy of a production box) and review; **commit:** `81d3050`; **fixed in:** v78-r2604.0-rc3

### B57

**In-place upgrade: mail accepted after the fresh backup of phase snapshot is missing from it** (medium, Tools)

* **Symptom:** The Mail-in-a-Box backup that `tools/upgrade-in-place-to-2604.sh` makes before the upgrade lacks the mail (and other changes) of the minutes between its end and the start of the downtime. If the upgrade fails and the box is restored from that backup, that mail is lost.
* **Cause:** Phase snapshot ran management/backup.py while mail was running. backup.py stops Postfix, Dovecot, postgrey and PHP for its run and starts them again afterwards; then the system archive was written, encrypted and copied (several minutes on a production box), and only phase quiesce stopped mail.
* **Fix:** Mail, web, cron and the update timers are stopped and masked before the fresh backup (stop_mail, recorded in the state like quiesce, so the downtime and `--rollback` start there); backup.py cannot start the masked units again. Phase quiesce then only pauses the backups. With `--skip-miab-backup` or backups off, mail keeps running until quiesce as before. The system archive, the copy of `/etc` and the package lists are taken before the stop, so they do not record the masks (restoring `/etc` from them must not leave Postfix and Dovecot masked); a run interrupted after the stop keeps them and skips a backup that already ran with mail offline.
* **Affects:** v78 no, PR #2603 no. Origin: Fork (rc3).
* **Found by:** production upgrade; **commit:** see `git log --grep B57`; **fixed in:** v78-r2604.0-rc4

### B58

**mail_log.py counts no IMAP/POP3 logins of Dovecot 2.4 ("Logged in:")** (medium, Management)

* **Symptom:** On Ubuntu 26.04 the "User logins per hour" part of the weekly "Mail-in-a-Box Usage Report" (and of `management/mail_log.py -l`) lists no IMAP, POP3 or ManageSieve logins at all, only the SMTP logins taken from Postfix. Nothing reports an error.
* **Cause:** Dovecot 2.4 logs a successful login as `imap-login: Info: Logged in: user=<...>, method=PLAIN, rip=...`; Dovecot 2.3 logged `Info: Login: user=<...>`. scan_dovecot_login_line() only matched `Info: Login: user=<(.*?)>, method=PLAIN, rip=(.*?),`, so no 2.4 line matched. The regex also counted only method=PLAIN, while auth_mechanisms allows LOGIN too.
* **Fix:** The regex accepts `Login:` and `Logged in:` and any mechanism name. The protocol is named after the service without "-login" (managesieve instead of "mana").
* **Affects:** v78 partly (only the "Login:" line with method=PLAIN is counted, so AUTH LOGIN logins are missing, and ManageSieve shows as "mana": v78:management/mail_log.py matches `method=PLAIN` and passes `service[:4]`, while v78:setup/mail-dovecot.sh enables `auth_mechanisms=plain login`), PR #2603 yes. Origin: 26.04 change (the missing 2.4 lines), upstream (the mechanism and the protocol name).
* **Evidence:** /var/log/mail.log of the 26.04 test box (Dovecot 2.4.2, log_path=/var/log/mail.log): `Oct 23 02:16:29 imap-login: Info: Logged in: user=<...>, method=PLAIN, rip=192.0.2.10, lip=192.0.2.11, mpid=53945, TLS, session=<...>`, likewise for pop3-login and managesieve-login; no "Info: Login:" line. The code before the fix counted none of 108 sample lines as an IMAP/POP3 login (only 3 SMTP logins), the fixed code 24 IMAP, 2 POP3 and 2 ManageSieve logins for alice. The fail2ban filter dovecotimap.conf already matches the 2.4 "Login aborted: ... (auth failed, ...)" lines (fail2ban-regex on the same box), the Postfix lines of mail_log.py are unchanged in 3.10.
* **Report upstream:** MIAB main: count every mechanism, not only method=PLAIN, and name the protocol after the service without "-login".
* **Found by:** production upgrade; **commit:** see `git log --grep B58`; **fixed in:** v78-r2604.0-rc4

### B59

**Postfix 3.10 warns on every postconf call about smtpd_tls_dh1024_param_file** (low, Postfix)

* **Symptom:** Every `postconf` call (in setup, the status checks, the tools and by hand) and every Postfix start prints `postconf: warning: /etc/postfix/main.cf: support for parameter "smtpd_tls_dh1024_param_file" will be removed; instead, do not specify (leave at default)`.
* **Cause:** setup/mail-postfix.sh set smtpd_tls_dh1024_param_file=$STORAGE_ROOT/ssl/dh2048.pem, as upstream did for the DHE ciphers of old clients. Postfix 3.10 deprecates the parameter; its default (empty) uses the FFDHE groups of tls_ffdhe_auto_groups (ffdhe2048 ffdhe3072, RFC 7919) with OpenSSL 3.
* **Fix:** Setup no longer sets the parameter and comments out an existing line with editconf.py -e. dh2048.pem stays: nginx (ssl_dhparam) and Dovecot (ssl_server_dh_file) still use it.
* **Affects:** v78 no, PR #2603 yes. Origin: 26.04 change.
* **Evidence:** On the 26.04 test box (Postfix 3.10.6, OpenSSL 3.5.5) `postconf -h smtpd_recipient_restrictions` prints the warning on stderr; `postconf -d` gives `smtpd_tls_dh1024_param_file =` and `tls_ffdhe_auto_groups = ffdhe2048 ffdhe3072`. v78 (Postfix 3.6 on 22.04) sets the same parameter without a warning. Nothing else in the repo references the parameter.
* **Found by:** production upgrade; **commit:** see `git log --grep B59`; **fixed in:** v78-r2604.0-rc4

### B60

**Mail of cron and root bounces: /etc/mailname keeps another name, root@PRIMARY_HOSTNAME does not exist** (medium, System)

* **Symptom:** Output of cron jobs and other mail to local accounts (root, www-data) never reaches the administrator. On a box installed on a hosting provider's image it bounces every day with "mail for <the hosting provider's default host name> loops back to myself" (3 to 7 bounces a day on the production box, before and after the upgrade); on other boxes it bounces as unknown user.
* **Cause:** Postfix takes the domain of unqualified local addresses from myorigin=/etc/mailname. Setup set /etc/hostname but never /etc/mailname, which kept the name the machine had when Postfix was first installed (the provider's name, also on the 127.0.1.1 line of /etc/hosts). And even with /etc/mailname = PRIMARY_HOSTNAME, root@PRIMARY_HOSTNAME is neither a user nor an alias: PRIMARY_HOSTNAME is a virtual mailbox domain, where /etc/aliases does not apply. www-data, the owner of the Nextcloud cron jobs, has no address either.
* **Fix:** setup/system.sh writes PRIMARY_HOSTNAME to /etc/mailname and comments out a 127.0.1.1 line in /etc/hosts that names neither PRIMARY_HOSTNAME nor its first label. root@PRIMARY_HOSTNAME is a required alias, so it becomes an automatic alias to administrator@PRIMARY_HOSTNAME (a manual alias or user of that name wins). Setup writes the automatic aliases at the end (`mailconfig.py update-auto-aliases`), so existing boxes get it without a change of users or aliases. The Nextcloud cron file sends its output to root (MAILTO=root).
* **Affects:** v78 yes, PR #2603 yes. Origin: upstream (also in v78 on 22.04). The wrong /etc/mailname only where the machine had another name when Postfix was installed; the missing root@ alias everywhere.
* **Evidence:** Production box (from the upgrade report): /etc/mailname was the hosting provider's default host name of the machine, /etc/hosts had the same name on the 127.0.1.1 line, and mail.log showed the daily "loops back to myself" bounces since at least 2026-10-18. 26.04 test box: `postconf -h myorigin` is /etc/mailname, `postmap -q root@<PRIMARY_HOSTNAME> sqlite:/etc/postfix/virtual-alias-maps.cf` finds nothing (hostmaster@ and postmaster@ resolve to administrator@), /etc/hosts still has the cloud-init line `127.0.1.1 testvm.example.net testvm`. v78:setup/system.sh only writes /etc/hostname, v78:management/mailconfig.py get_required_aliases() has administrator@, hostmaster@, postmaster@, admin@ and abuse@ but no root@. The bounce of root@PRIMARY_HOSTNAME as unknown user is derived from the Postfix configuration, it was not reproduced (no mail was sent on the test box).
* **Report upstream:** MIAB main: the missing /etc/mailname and root@ handling are the same in v78.
* **Found by:** production upgrade; **commit:** see `git log --grep B60`; **fixed in:** v78-r2604.0-rc4

### B61

**SMTP AUTH filter takes a host from the client's user name, so a client can get a third party banned** (medium, fail2ban)

* **Symptom:** A client that sends AUTH on port 465 or 587 with a user name like `x[198.51.100.7]: x authentication failed` gets 198.51.100.7 banned (miab-postfix465/587: 20 in 30 s), not itself. With the fork's adaptive banning the slow jail `miab-slow-smtp` reuses the filter, so the third party is banned after 20 lines in 6 hours, and longer each time.
* **Cause:** conf/fail2ban/filter.d/miab-postfix-submission.conf had `failregex=postfix/submission/smtpd.*warning.*\[<HOST>\]: .* authentication (failed|aborted)`. The greedy `.*` before `\[<HOST>\]` takes the last `[ip]: ` of the line, and Postfix appends the client-chosen `sasl_username=` after the client address. The same kind of bug as B08's user name in dovecotimap.conf.
* **Fix:** Anchored like fail2ban's own postfix filter: `^%(__prefix_line)swarning: [-._\w]+\[<HOST>\]: SASL \S+ authentication (?:failed|aborted)` with `_daemon = postfix/submission/smtpd`, so only the address right after `warning:` can be the host. tests/fork/smoke.py `admin-fail2ban-filters` runs fail2ban-regex with such a line on the box.
* **Affects:** v78 yes, PR #2603 yes. Origin: upstream (also in v78 on 22.04).
* **Evidence:** fail2ban-regex 1.1.0 with the old filter and the line `warning: unknown[203.0.113.5]: SASL LOGIN authentication failed: (reason unavailable), sasl_username=x[198.51.100.7]: x authentication failed` gives 198.51.100.7, with the new one 203.0.113.5. That Postfix logs the user name unescaped is from the log format (`sasl_username=` is printed as sent, brackets, colons and spaces are printable); not reproduced with a live AUTH.
* **Report upstream:** MIAB main: anchor miab-postfix-submission.conf.
* **Found by:** review (adaptive fail2ban); **commit:** "fail2ban: anchor the SMTP AUTH filter (B61)"; **fixed in:** v78-r2604.0-rc4

### B62

**Control panel and Roundcube filters take a host from text written by a client, so a client can get a third party banned** (medium, fail2ban)

* **Symptom:** A client that fails SMTP AUTH with a user name like `Mail-in-a-Box Management Daemon: Failed login attempt from ip 198.51.100.7 - timestamp 1` adds a failure for 198.51.100.7 to the control panel jail `miab-management` (20 in 30 s, from several source addresses), and with the fork's slow web jails also to `miab-slow-management`. The third party is then banned from the control panel, webmail and Nextcloud (ports 80/443), and repeated bans make `recidive` block it on all ports. The Roundcube filter had the same weakness for user names containing ` from <ip>. AUTHENTICATE`.
* **Cause:** conf/fail2ban/filter.d/miab-management-daemon.conf had the unanchored `failregex = Mail-in-a-Box Management Daemon: Failed login attempt from ip <HOST> - timestamp .*` and reads /var/log/syslog, which also gets every Postfix line (rsyslog `*.*;auth,authpriv.none -/var/log/syslog`); Postfix logs the client-chosen `sasl_username=` as sent (the premise of B61). miab-roundcube.conf had `IMAP Error: Login failed for .*? from <HOST>\. AUTHENTICATE.*`: the lazy `.*?` took the first ` from <ip>. AUTHENTICATE`, which can be inside the user name before Roundcube's own `against <host> from <ip>`.
* **Fix:** Both filters are anchored. The control panel filter only takes lines of the daemon itself (`_daemon = (?:start|gunicorn)` with Flask's `[time] WARNING in daemon: ` prefix, or the untagged copy the daemon sends through /dev/log), up to the end of the line. The Roundcube filter is anchored at the start of the line, and its greedy `.*` takes the last `against <host> from <ip>. AUTHENTICATE <mechanism>:`, the one Roundcube wrote. tests/fork/smoke.py `admin-fail2ban-filters` checks real and forged lines of both.
* **Affects:** v78 yes, PR #2603 yes. Origin: upstream (also in v78 on 22.04, same filters and the same rsyslog rule). The Roundcube part is latent with Mail-in-a-Box's Roundcube settings: `login_username_filter = email` refuses user names with spaces unless they are quoted, and Roundcube lowercases the user name, so a forged `AUTHENTICATE` no longer matches.
* **Evidence:** fail2ban-regex 1.1.0 on the 26.04 test box: the old control panel filter gives 198.51.100.7 for the line `box postfix/submission/smtpd[1234]: warning: unknown[203.0.113.5]: SASL PLAIN authentication failed: (reason unavailable), sasl_username=Mail-in-a-Box Management Daemon: Failed login attempt from ip 198.51.100.7 - timestamp 1`, the new one nothing; both match the two real lines of a failed control panel login (`start[pid]: [time] WARNING in daemon: Mail-in-a-Box Management Daemon: ...` and `box Mail-in-a-Box Management Daemon: ...`). The old Roundcube filter gives 198.51.100.7 for `Login failed for x from 198.51.100.7. AUTHENTICATE against localhost from 203.0.113.5. AUTHENTICATE PLAIN: ...`, the new one 203.0.113.5; a real failed webmail login with a quoted user name was logged lowercased (`"x from 198.51.100.7. authenticate"@example.com`) and gives the real address with both. Dovecot writes /var/log/mail.log itself and truncates long user names, so its lines do not reach syslog. The forged lines were checked with fail2ban-regex only, no ban was made.
* **Report upstream:** MIAB main: anchor miab-management-daemon.conf and miab-roundcube.conf.
* **Found by:** review of rc4; **commit:** "fail2ban: anchor the control panel and Roundcube filters (B62)"; **fixed in:** v78-r2604.0-rc4

### B63

**API call system/latest-upstream-version fails with HTTP 500 and a traceback when the latest version cannot be determined** (low, Management)

* **Symptom:** `POST /admin/system/latest-upstream-version` answers HTTP 500 with Flask's "Internal Server Error" page, and the management daemon logs a TypeError traceback, whenever the release cannot be looked up (no network, the release URL answers 404, or the script has no `TAG=` line). The status checks themselves handle the same case ("Latest Mail-in-a-Box version could not be determined").
* **Cause:** management/daemon.py `system_latest_upstream_version()` returns the result of `get_latest_miab_version()` as it is. That function returns None in these cases, and a Flask view must not return None; the `try`/`except` around the call does not catch it, because Flask raises the TypeError after the view has returned.
* **Fix:** The view answers HTTP 503 with "The latest version could not be determined." when the version is None.
* **Affects:** v78 yes, PR #2603 yes. Origin: upstream (same view and the same None in v78).
* **Evidence:** 26.04 test box with rc4 before the project home on GitHub was published (raw.githubusercontent.com answered 404): the call gave HTTP 500, journal `TypeError: The view function for 'system_latest_upstream_version' did not return a valid response`. The control panel itself does not use this call; API clients do.
* **Report upstream:** MIAB main: return an error status instead of None.
* **Found by:** test run (rc4); **commit:** see `git log --grep B63`; **fixed in:** v78-r2604.0-rc4

### B64

**A failed write to users.sqlite keeps the database locked until garbage collection, other control panel changes fail** (medium, Management)

* **Symptom:** After one failed change in the control panel or the API, such as adding a user or an alias that already exists or changing the password of an address that is no user, every following change of users, aliases, passwords, quotas or privileges fails with HTTP 500 for minutes; the daemon logs `sqlite3.OperationalError: database is locked`. Reading (logins, mail delivery) keeps working.
* **Cause:** management/mailconfig.py opens a new connection for each change and returns early on these errors without commit() or close(). The write statement has already started the implicit transaction and taken the database's write lock. Python 3.10 (22.04) freed the connection, and rolled the transaction back, as soon as the function returned. Since Python 3.11 an `sqlite3.Connection` is part of a reference cycle, so it is only freed by the cyclic garbage collector, which in the mostly idle daemon can take minutes. Ubuntu 26.04 has Python 3.14.
* **Fix:** The error paths of add_mail_user, set_mail_password, set_mail_quota, remove_mail_user, add_remove_mail_user_privilege, add_mail_alias and remove_mail_alias close the connection, which rolls the transaction back.
* **Affects:** v78 no (Python 3.10), PR #2603 yes. Origin: 26.04 change (Python 3.14).
* **Evidence:** 26.04 test box: `POST /admin/mail/users/add` for an existing user (HTTP 400), then `sqlite3 users.sqlite "BEGIN IMMEDIATE"` fails with "database is locked" for more than two minutes; the smoke test's second run on the same box failed `provision-test-accounts` and `admin-api-tmp-user-alias` with HTTP 500. A minimal script (connect, failing INSERT, return) leaves the database locked with Python 3.12 and 3.14 and frees it with Python 3.10; `gc.collect()` frees it in all. With the fix, the same three API errors leave the database writable.
* **Found by:** test run (rc4); **commit:** see `git log --grep B64`; **fixed in:** v78-r2604.0-rc4

### B65

**'curl ... | sudo bash' hangs at setup's first dialog box: sudo-rs stops it** (high, Setup)

* **Symptom:** An interactive install or update with the documented command `curl -s .../setup/bootstrap.sh | sudo bash` prints "Installing packages needed for setup..." (or the update lines) and then nothing; keys do nothing. Setup waits forever in its first dialog box ("Hello and thanks for deploying a Mail-in-a-Box!"). Nothing has been changed by setup at that point; in the test the stopped processes were ended from another shell (kill -INT, then -CONT).
* **Cause:** Ubuntu 26.04's `sudo` is sudo-rs. It runs the command in a pseudo terminal of its own, and when its own standard input is not a terminal (here the pipe from curl) it stops full-screen programs such as dialog: the dialog process and setup/start.sh are in state T (stopped), and nothing reaches the screen. Simple reads from /dev/tty (the tools' y/N questions) are not affected. Ubuntu 22.04's sudo 1.9.9 does not use a pseudo terminal, so upstream's `curl ... | sudo bash` works there.
* **Fix:** The documentation and the header of setup/bootstrap.sh use `sudo bash -c "$(curl -fsSL .../setup/bootstrap.sh)"`, which keeps sudo's input on the terminal. bootstrap.sh stops before it changes anything, with that command, when it runs interactively with its input from a pipe under sudo-rs (parent process /usr/lib/cargo/bin/sudo). `NONINTERACTIVE=1`, a root shell (`sudo -i`, then `curl ... | bash`) and sudo.ws keep working with the pipe.
* **Affects:** v78 no (22.04), PR #2603 yes (upstream's command on 26.04). Origin: 26.04 change (sudo-rs).
* **Evidence:** 26.04 test box with sudo-rs 0.2.13, in tmux and over a plain `ssh -tt`: `cat t.sh | sudo bash` with `t.sh` = `dialog --msgbox x 6 30; echo RC=$?` shows nothing and the dialog stays stopped after Enter; the same with `sudo.ws`, with `sudo bash -c "$(cat t.sh)"` and with `sudo bash -c 'cat t.sh | bash'` shows the box and ends with RC=0 on Enter. The update of the rc3 test box with `curl ... | sudo SOURCE=... TAG=... bash` hung like this (ps: `dialog` and `setup/start.sh` in state T+). A `printf q > /dev/tty; read a < /dev/tty` through the same pipe works.
* **Found by:** test run (rc4); **commit:** see `git log --grep B65`; **fixed in:** v78-r2604.0-rc4

### B66

**Vacation replies and redirects create the folders "dovecot", "dovecot.lda-dupes" and "dovecot.lda-dupes.locks"** (medium, Dovecot)

* **Symptom:** After the first vacation reply or Sieve redirect of a user, mail programs, Roundcube and `doveadm mailbox list` show the folders `dovecot`, `dovecot.lda-dupes` and `dovecot.lda-dupes.locks`; full-text search indexes `dovecot.lda-dupes.locks` as a folder, and LMTP can log `Error: maildir: stat(.../.dovecot.lda-dupes/tmp) failed: Not a directory` (the mail is still delivered). A user cannot get rid of them: Dovecot creates them again.
* **Cause:** The user's home (userdb `home`) is the root of the Maildir, as in upstream. Dovecot keeps the duplicate database of vacation and redirect in the home (`~/.dovecot.lda-dupes`, a file; that is the same on 22.04), and Dovecot 2.4 (already 2.3.21 on Ubuntu 24.04) locks each entry with a file in a directory next to it, `~/.dovecot.lda-dupes.locks/`, unless `mail_volatile_path` is set (lib-storage/mail-duplicate.c). Maildir++ takes every directory whose name starts with a dot for a folder, so the lock directory became the folder `dovecot.lda-dupes.locks` (Dovecot then made a Maildir of it), with `dovecot` and `dovecot.lda-dupes` as its parents. Dovecot 2.3.16 (22.04) used a single dotlock file `.dovecot.lda-dupes.lock`, which a listing skips. So boxes that come from 24.04 (in place or with tools/migrate-to-2604.sh) can bring these folders along. Dovecot's documentation advises against a home that is the Maildir for this reason ("Non-mailbox files may show up as mailboxes").
* **Fix:** setup/mail-dovecot.sh sets `mail_volatile_path = /run/dovecot-volatile/%{user|domain}/%{user|username}` (a tmpfs directory of the mail user, created by `/etc/tmpfiles.d/mailinabox-dovecot.conf`), so these lock files, and Dovecot's other short-lived lock files, are no longer written into the Maildir; and `maildir_stat_dirs = yes`, which keeps the database file out of the folder list also on file systems that do not report file types when listing (on ext4 the setting has no effect). The home stays where it is, so Sieve, quota, the full-text indexes and backups are unchanged. On existing boxes setup (at the end of setup/mail-users.sh, once the user database is in place, which a box from 24.04 does not have before) unsubscribes `dovecot.lda-dupes` and `dovecot` unless a real folder has that name, deletes the lock directory through `doveadm mailbox delete -s` (it unsubscribes it and updates the folder list) and removes its full-text index. A lock directory that holds messages (moved there with a mail program) is kept with a message; if doveadm fails for a user, the directory is kept as well, so the next setup run tries again; only the directory of a user who no longer exists is removed directly. The duplicate database stays, so a sender who got a vacation reply does not get a second one.
* **Affects:** v78 no (Dovecot 2.3.16 on 22.04), PR #2603 yes. Origin: 26.04 change (Dovecot 2.4; upstream on 24.04 with Dovecot 2.3.21 has the lock directory too).
* **Evidence:** Fresh rc4 test box and a copy of a production box updated to rc4: `doveadm mailbox list -u` of the user with the vacation reply listed `dovecot`, `dovecot.lda-dupes` and `dovecot.lda-dupes.locks`; the directory `.dovecot.lda-dupes.locks` in the Maildir had `cur/`, `new/`, `tmp/` and `dovecot-uidlist`, and xapian-indexes had a database for it; the box copy logged the LMTP error above. Dovecot 2.4.2 source: `mail_duplicate_db_init()` puts the database at `<home>/.dovecot.<name>` and the lock directory at `<mail_volatile_path or home>/.dovecot.<name>.locks`; the 2.3.21 source does the same, the 2.3.16 source has no lock directory (one dotlock on the database file). With the fix on the fresh box: setup removed the folders of the existing user (folder list, subscriptions and its full-text index clean), and for a new user with a vacation script two mails from the same sender gave one reply ("discarded duplicate vacation response" for the second), the lock directory was in `/run/dovecot-volatile/<domain>/<user>/` and no folder appeared.
* **Report upstream:** MIAB main: relevant once upstream moves to Dovecot 2.4 (PR #2603).
* **Found by:** update test; **commit:** see `git log --grep B66`; **fixed in:** v78-r2604.0-rc5

### B67

**In-place upgrade leaves Dovecot disabled: no IMAP, POP3 or mail delivery after the next reboot** (high, Tools)

* **Symptom:** After `tools/upgrade-in-place-to-2604.sh` (rc3) everything works, "All checks passed", and the status checks are green, but `systemctl is-enabled dovecot` says `disabled`. The next reboot leaves Dovecot off: no IMAP, POP3 or ManageSieve, and Postfix cannot deliver to the mailboxes (LMTP), so incoming mail waits in the queue. Updating to rc4 does not change it.
* **Cause:** cleanup_dovecot purges the Dovecot 2.3 packages, which removes their enablement links, and installs Dovecot 2.4 while the units are masked (so that it does not start with a configuration setup has not written yet). The package's `deb-systemd-helper` cannot enable a masked unit (`Failed to preset unit: Unit /etc/systemd/system/dovecot.service is masked`). unquiesce removed the masks but only enabled again the units it had disabled itself, and setup's `restart_service` starts a service without enabling it. phase verify and the status checks only look at running services.
* **Fix:** mask_units records which units are enabled before it masks them, and unquiesce enables those again that are disabled after the masks are gone ("Enabled again ..."). phase verify of both tools shows whether each service is enabled, enables a disabled one and counts any other state (e.g. masked) as a failed check; `tools/upgrade-in-place-to-2604.sh` also lists in `etc-report.txt` and as a warning the units that `meta/unit-files.txt` (before the upgrade) has as enabled and that are disabled now, except those that setup turns off on purpose (`spamd.service`: spampd runs SpamAssassin itself, and Ubuntu 24.04 had spamd enabled). Setup's `restart_service` enables a disabled unit before restarting it, and setup/system.sh restarts `named` by that name (bind9.service is only an alias link, which a disabled named does not have, so enabling or restarting it by that name fails), and setup/dns.sh does the same for nsd, so the next setup run (`sudo mailinabox`, or the update to the next release) heals a box upgraded with rc3.
* **Affects:** v78 no, PR #2603 no. Origin: Fork (rc3, `tools/upgrade-in-place-to-2604.sh`). `tools/migrate-to-2604.sh` installs Dovecot with setup on a fresh machine and is not affected; it gets the same check in phase verify.
* **Evidence:** Copy of a production box upgraded in place with rc3: `meta/unit-files.txt` of the tool has `dovecot.service enabled`, the upgrade log has `Failed to preset unit: Unit /etc/systemd/system/dovecot.service is masked` and `deb-systemd-helper: error: systemctl preset failed` when dovecot-core 2.4 was set up, and after the upgrade and after the update to rc4 `dovecot.service` is `disabled`; after a reboot Dovecot was inactive and the status checks had three more errors (IMAP, LMTP, Sieve). It was the only Mail-in-a-Box service that went from enabled to disabled. The production box upgraded with rc3 has the same state. A fresh rc4 box has it `enabled`.
* **Found by:** update test; **commit:** see `git log --grep B67`; **fixed in:** v78-r2604.0-rc5

### B68

**cloud-init puts the 127.0.1.1 line with another machine's name back into /etc/hosts on every boot** (low, System)

* **Symptom:** Setup prints "Commenting out the 127.0.1.1 line of /etc/hosts with another machine's name..." on every run: after each reboot `/etc/hosts` has the line `127.0.1.1 <the provider's or the template's name of the machine> <short name>` again. /etc/mailname keeps the box's name, so mail of root and cron still reaches the administrator; the provider's name resolves to the box itself again.
* **Cause:** The fix of B60 (rc4) edits `/etc/hosts` only. On machines whose cloud-init has `manage_etc_hosts: true` (in the image's `/etc/cloud/cloud.cfg` or, as with some hypervisors, in the machine's user data), cloud-init's module update_etc_hosts writes `/etc/hosts` on every boot from `/etc/cloud/templates/hosts.debian.tmpl`, whose line is `127.0.1.1 {{fqdn}} {{hostname}}` with cloud-init's names of the machine, not PRIMARY_HOSTNAME. A drop-in in `/etc/cloud/cloud.cfg.d` cannot turn that off, because the user data overrides it.
* **Fix:** When setup has commented out such a line and cloud-init manages `/etc/hosts` (`manage_etc_hosts` true or template in `cloud-init query combined_cloud_config`, or cloud-init's header in `/etc/hosts`), setup/system.sh changes the template's 127.0.1.1 line to `127.0.1.1 PRIMARY_HOSTNAME <first label>`, as the header that cloud-init writes into `/etc/hosts` suggests, and writes the same line into `/etc/hosts` instead of the commented-out one, so the file stays the same after the next boot. A template that already gives the box's name is left alone, and so is a box where cloud-init's name of the machine is PRIMARY_HOSTNAME. The template is a configuration file of the package cloud-init-base: when an update changes it, dpkg asks, and the local version should be kept. With `manage_etc_hosts: localhost` cloud-init does not use the template; setup then says that the setting can only be changed in the user data.
* **Affects:** v78 no (it does not touch /etc/hosts), PR #2603 no. Origin: Fork (B60's fix in rc4).
* **Evidence:** Fresh rc4 test box (cloud-init of the hypervisor, `manage_etc_hosts: true` and `fqdn` in the user data; a copy of a production box has the same template and setting): the template has `127.0.1.1 {{fqdn}} {{hostname}}`; re-running the module (`cloud-init single --name update_etc_hosts --frequency always`, as at boot) writes `127.0.1.1 <cloud-init fqdn> <hostname>` back. With the fix: the template and `/etc/hosts` have `127.0.1.1 PRIMARY_HOSTNAME <first label>`, the module writes the same line, and a second setup run changes nothing.
* **Found by:** update test; **commit:** see `git log --grep B68`; **fixed in:** v78-r2604.0-rc5

### B69

**systemctl is-enabled mailinabox and munin fail with "Too many levels of symbolic links"** (low, Setup)

* **Symptom:** `systemctl is-enabled mailinabox` and `systemctl is-enabled munin` print `Failed to get unit file state for mailinabox.service: Too many levels of symbolic links`, and `systemctl list-unit-files` shows them as `bad`. The services still run and start at boot, but tools that check the enablement (such as phase verify, B67) cannot tell whether they are enabled.
* **Cause:** setup/management.sh and setup/munin.sh copy the unit to `/lib/systemd/system/` and then run `systemctl enable /lib/systemd/system/<unit>` (PR #2603; v78 ran `systemctl link -f` with the same path, then enabled the unit by name). Enabling by path creates the link `/etc/systemd/system/<unit> -> /lib/systemd/system/<unit>`. Since `/lib` is a link to `usr/lib`, that link points to the unit's own file in the search path, and systemd 259 treats it as a loop. systemd 249 (22.04) accepted the same link.
* **Fix:** A new function `install_unit` in setup/functions.sh copies the unit, removes a link `/etc/systemd/system/<unit>` (unless it is a mask), reloads systemd and enables the unit by name with `systemctl reenable`, which also replaces the `.wants` links that go through `/lib`. Existing boxes are repaired on the next setup run.
* **Affects:** v78 no (systemd 249), PR #2603 yes. Origin: PR #2603 (with systemd 259 of 26.04). A box upgraded in place from v78 also has the link from `systemctl link -f`.
* **Evidence:** Fresh rc4 test box and a copy of a production box updated to rc4: `ls -l /etc/systemd/system/mailinabox.service` gives `-> /lib/systemd/system/mailinabox.service`, `/lib -> usr/lib`, and is-enabled fails as above for mailinabox.service and munin.service (systemd 259.9). After removing the link and `systemctl reenable`, both are `enabled`, the `.wants` links point to `/usr/lib/systemd/system/`, and the management daemon keeps running.
* **Report upstream:** PR #2603: enable the units by name.
* **Found by:** update test; **commit:** see `git log --grep B69`; **fixed in:** v78-r2604.0-rc5

### B70

**In-place upgrade from 22.04 warns that ssh.service is disabled and advises to enable it, although ssh.socket starts it** (low, Tools)

* **Symptom:** On a box that comes from Ubuntu 22.04, phase verify of `tools/upgrade-in-place-to-2604.sh` prints "Enabled before the upgrade, disabled now (they do not start after a reboot): ssh.service", and `etc-report.txt` lists it under "systemctl enable UNIT, if still wanted". SSH works and comes back after a reboot.
* **Cause:** Since Ubuntu 24.04 sshd is socket-activated: `ssh.socket` is enabled and starts `ssh.service`, which is disabled. The check of B67 compares the enabled units of `meta/unit-files.txt` (before the upgrade) with the disabled units now and left out only spamd. It did not look at how a disabled unit is started. Enabling ssh.service is not needed: ssh.socket starts it on the first connection.
* **Fix:** The check leaves out a disabled unit that is started another way: by an enabled (or running) socket, path or timer that activates it (`TriggeredBy`), when its name is now another unit's name, or when a running unit pulls it in. Units that are gone (removed packages) or are static, generated or an alias now were already not listed. The tool never enables such units itself.
* **Affects:** v78 no, PR #2603 no. Origin: Fork (rc5, the check of B67). Only boxes that come from 22.04: a box that starts on 24.04 already has ssh.service disabled before the upgrade. `tools/migrate-to-2604.sh` has no such check.
* **Evidence:** rc5 T4 (22.04 test VM, from the published tag): the warning and the line in `etc-report.txt`, with `ssh.socket` enabled and active after the upgrade. The new check run against the unit list of that run before the upgrade on a fresh 26.04 box lists nothing (the old check: ssh.service); with units added to that list by hand it still lists rsync, nftables and chrony-wait, but not iscsid (started by iscsid.socket).
* **Found by:** in-place test; **commit:** see `git log --grep B70`; **fixed in:** v78-r2604.0-rc6

### B71

**The terminal attached to the tool's tmux session shows nothing; through "curl | sudo bash" it is not attached at all** (low, Tools)

* **Symptom:** Started as documented, `curl ... | sudo bash -s -- ...`, both tools start themselves in tmux, but print "Could not attach this terminal. The run goes on in the tmux session upgrade-2604" (or `migrate-2604`) and return to the shell: the operator does not see the run. Started from a file (`sudo bash tools/upgrade-in-place-to-2604.sh`), the terminal is attached, but stays blank until the run ends; the keys work (Ctrl-b d detaches). The run itself goes on in both cases. `--check` through `curl | bash` also advised to start the command inside tmux, which the release does by itself.
* **Cause:** mux_attach opened the terminal for the tmux client only for reading (`< "$t" > "$t"`). tmux draws on the descriptor of the client's stdin, so it drew nothing (tmux 3.2a, 3.4 and 3.6 alike). rc4 then took the blank terminal for a limit of sudo's own terminal (use_pty of sudo on 22.04 and 24.04, sudo-rs on 26.04) and gave up when stdin is a pipe. There is a second limit there: with stdin a pipe, classic sudo passes the output of its terminal on but not the keys, and sudo-rs passes the keys on only while the operator's terminal is in raw mode.
* **Fix:** mux_attach opens the terminal for reading and writing. When stdin is a pipe and sudo itself has the pipe as stdin, it attaches the operator's terminal (that of sudo's own process) with classic sudo; with sudo-rs it attaches sudo's terminal and puts the operator's terminal into raw mode while attached (and back afterwards). Without a terminal (cron, nohup, `ssh` without `-t`) the tools run without tmux, as before. `--check` warns about a release without the automatic tmux only for rc1 to rc3. Same in both tools.
* **Affects:** v78 no, PR #2603 no. Origin: Fork (rc4, the automatic tmux; "not attached at all" since rc4's last commit, the same for rc5).
* **Evidence:** rc5 T4: the terminal of `curl ... | sudo bash -s -- --yes --no-backup-check` printed the message and returned. On a 26.04 test box, with the tools' own tmux functions, a pseudo terminal over `ssh -tt` and a ticker as the run: the rc5 code drew nothing in all start forms (curl pipe or file, sudo-rs or classic sudo 1.9.17 with use_pty, tmux 3.2a, 3.4 and 3.6); the new code drew the run and detached with Ctrl-b d in 36 of 36 runs (both tools; curl pipe, file and `sudo bash -c "curl | bash"`; sudo-rs and classic sudo), and the terminal was back in line mode afterwards. Attaching the operator's terminal under sudo-rs lost keys to sudo-rs in 3 of 5 runs, hence the raw mode there.
* **Found by:** in-place test; **commit:** see `git log --grep B71`; **fixed in:** v78-r2604.0-rc6

### B72

**After the last reboot of the in-place upgrade the tmux window waits for Enter forever** (low, Tools)

* **Symptom:** After the in-place upgrade has finished, the tmux session `upgrade-2604` is still there; its window ends with "The upgrade script ended with exit code 0. Press Enter to close this window." and stays open until someone attaches and presses Enter, or until the next reboot.
* **Cause:** After a reboot the resume unit starts the tool in a new tmux session whose window waits for Enter without a time limit. The first window has a limit with `--yes` (10 minutes), the resumed one had none, although the resumed run always runs with `--yes` and usually nobody is attached.
* **Fix:** When the resumed run has succeeded, the window closes by itself after 60 seconds (Enter closes it at once). After a failure it stays open until Enter is pressed, so that the output can be read.
* **Affects:** v78 no, PR #2603 no. Origin: Fork (rc4, the automatic tmux). Only `tools/upgrade-in-place-to-2604.sh`; `tools/migrate-to-2604.sh` does not reboot.
* **Evidence:** rc4 T4b and rc5 T4: the window with "Press Enter to close this window" was still open after the run. On a 26.04 test box, the window of the new resume script closed 61 seconds after a run with exit code 0 and was still open 70 seconds after a run with exit code 1.
* **Found by:** in-place test; **commit:** see `git log --grep B72`; **fixed in:** v78-r2604.0-rc6

### B73

**During the release upgrade to 26.04 "tmux attach" cannot reach the in-place upgrade until the reboot, although the tool advises it** (low, Tools)

* **Symptom:** A few minutes into the release upgrade from 24.04 to 26.04, `sudo tmux attach -t upgrade-2604` (with sudo.ws or sudo-rs while `/usr/bin/sudo` is missing) prints "open terminal failed: not a terminal" and returns. It stays so until the reboot after the release upgrade. The tool and README-fork.md advised to wait when a login or sudo fails and then attach, and the motd and the reboot message offer `tail -f /root/upgrade-2604/upgrade.log`, which a user other than root cannot read. The run itself goes on, and a client attached before stays attached.
* **Cause:** The release upgrade replaces tmux 3.4 by tmux 3.6 while the 3.4 server of the run keeps running. The 3.6 client cannot attach to the 3.4 server. The old binary is deleted, and its copy under `/proc/PID/exe` no longer starts with the new libtinfo ("version `NCURSES6_TINFO_6.4.current' not found"). From 22.04 to 24.04 the new client (3.4) attaches to the old server (3.2a).
* **Fix:** Before the release upgrade to 26.04, before a reboot after which it starts by itself, and in the motd the tool says that a new `tmux attach` cannot reach the run from a few minutes after the start until the reboot, and to follow the log with `sudo tail -f /root/upgrade-2604/upgrade.log` instead. The other log hints say `sudo tail -f` as well. README-fork.md and README.md describe it. No second tmux is kept: a copy of the old binary would need the old C library and libtinfo next to it.
* **Affects:** v78 no, PR #2603 no. Origin: Fork (the in-place tool since rc3). Only `tools/upgrade-in-place-to-2604.sh`; `tools/migrate-to-2604.sh` has no release upgrade.
* **Evidence:** rc6 T3 (copy of a 24.04 production box): tmux 3.4 was replaced by 3.6a at 5 min 40 s into the release upgrade (dpkg.log); a new attach over `ssh -tt` with sudo.ws and with sudo-rs failed with "open terminal failed: not a terminal" after that, `/proc/PID/exe attach` failed with the libtinfo error, and the session was reachable again after the reboot. On a 26.04 test box with the 22.04 and 24.04 tmux binaries and their own libraries: a 3.6 client fails against a 3.4 server and against a 3.2a server, a 3.4 client attaches to a 3.2a server and to a 3.4 server.
* **Found by:** in-place test; **commit:** see `git log --grep B73`; **fixed in:** v78-r2604.0-rc6

### B74

**Every setup run adds another commented copy of each SSL setting to 10-ssl.conf** (low, Dovecot)

* **Symptom:** After each run of setup, `/etc/dovecot/conf.d/10-ssl.conf` has one more commented copy of each of the six SSL settings that setup sets (`#ssl = required`, `#ssl_server_cert_file = ...` and so on), so the file changes on every run although nothing else changed. Dovecot reads the same settings; only the file grows.
* **Cause:** setup/mail-dovecot.sh passed the settings to `tools/editconf.py` with spaces around "=" (`"ssl = required"`). editconf.py splits at the "=" and keeps the spaces in the value, so it never finds the line it wrote before as the same setting: it comments it out and adds it again. Upstream fixed the same for Dovecot 2.3 in 2019 (commit 81176c8); the port's new 2.4 names brought the spaces back.
* **Fix:** The settings are passed without spaces around "=". The first run with the fix writes each line once more in that form, without a new commented copy; from then on the file stays the same. Commented copies from earlier runs stay in the file; they are only comments.
* **Affects:** v78 no (`ssl=required` and the other settings without spaces), PR #2603 yes. Origin: PR #2603.
* **Evidence:** rc6 T5b (copy of a production box on rc3, updated with setup/bootstrap.sh): of all files in `/etc`, a second update run changed only `10-ssl.conf` in content (besides the random minute of the nightly cron job and the order of the OpenDKIM tables, both as upstream), with one more commented copy of each of the six lines. The new arguments, run twice on that file and on the 26.04 package's `10-ssl.conf`, change nothing on the second run; the old ones add a commented line per setting and run.
* **Found by:** update test; **commit:** see `git log --grep B74`; **fixed in:** v78-r2604.0-rc6

### B75

**logrotate.service fails every day on boxes upgraded in place to 26.04: cloud-init's old logrotate file stays** (low, System)

* **Symptom:** On a box upgraded in place from 24.04 to 26.04, `systemctl --failed` lists `logrotate.service` after its daily run, and its journal says "error: cloud-init-base:1 duplicate log entry for /var/log/cloud-init-output.log" and "found error in file cloud-init-base, skipping". The other logs are still rotated.
* **Cause:** On 26.04 the package cloud-init-base ships `/etc/logrotate.d/cloud-init-base`, which cloud-init shipped as `/etc/logrotate.d/cloud-init` before. The release upgrade does not remove the old file: dpkg keeps it as an obsolete conffile of cloud-init. Both files name `/var/log/cloud-init*.log`, and logrotate rejects the second one and exits with an error. A fresh 26.04 install has only the new file. setup did not look at such files.
* **Fix:** setup/system.sh removes obsolete conffiles of dpkg in `/etc/logrotate.d` that are unchanged (the MD5 sum dpkg recorded). A file changed by the administrator stays.
* **Affects:** v78 no, PR #2603 no (only boxes upgraded in place). Origin: 26.04 change (the packaging of cloud-init). Boxes upgraded with `tools/upgrade-in-place-to-2604.sh` get the fix in its setup phase, boxes upgraded with an earlier release on their next update.
* **Evidence:** rc6 T5b (copy of a production box upgraded in place with rc3, updated with setup/bootstrap.sh): `logrotate.service` failed at its first run on the copy with the errors above. `dpkg-query -W -f='${Conffiles}'` lists `/etc/logrotate.d/cloud-init` as obsolete for cloud-init, with the same MD5 sum as the file and as `cloud-init-base`'s file; the fresh 26.04 test box has no such file and the new step does nothing there. With a changed copy of the file the step kept it; with the unchanged file the next update removed it and `logrotate.service` ran without errors.
* **Found by:** update test; **commit:** see `git log --grep B75`; **fixed in:** v78-r2604.0-rc6

### B76

**The migration tool's Spamhaus checks follow the resolver's search domain and can report a wildcard address** (low, Tools)

* **Symptom:** `tools/migrate-to-2604.sh` (phase preflight and `--check`) prints "Spamhaus ZEN: unexpected answer 2001:db8::1" with an IPv6 address instead of "is not listed" or "no answer (Spamhaus refuses public resolvers)", when the new machine's resolver has a search domain (`search example.net` in `/etc/resolv.conf`, for example from DHCP or cloud-init) and that domain has a wildcard record (`*.example.net`). The Domain Block List check reads such an answer as well; it only warns on 127.0.1.x, so it stays silent.
* **Cause:** The tool looked up `<reversed IP>.zen.spamhaus.org` and `<hostname>.dbl.spamhaus.org` with `getent -s dns hosts` without a trailing dot. getent asks for an AAAA record first. Spamhaus has none, so the resolver tries the name again with the search domain appended (`....zen.spamhaus.org.example.net`), and the wildcard answers. The same happened for the always-listed test address 127.0.0.2.
* **Fix:** Both names end with a dot, so the resolver takes them as they are and does not append the search domain.
* **Affects:** v78 no, PR #2603 no. Origin: Fork (the migration tool, since rc1). setup/network-checks.sh of upstream uses `host` the same way, but the tool runs setup with `SKIP_NETWORK_CHECKS=1`.
* **Evidence:** rc6 T2 (fresh 26.04 test box with `search` set to a domain with a wildcard record): `--check` printed "Spamhaus ZEN: unexpected answer" with the wildcard's IPv6 address. On that box `getent -s dns hosts` returned the wildcard address with the search domain appended for the box's reversed IP, for 2.0.0.127 and for the DBL name; with the trailing dot it returned 127.255.255.254 (Spamhaus refuses the public resolver) for all three.
* **Found by:** test run (T2 of rc6); **commit:** see `git log --grep B76`; **fixed in:** v78-r2604.0-rc6

### B77

**"migrate-to-2604.sh --check --skip-network-checks" still lists the skipped network checks as blockers and exits 1** (low, Tools)

* **Symptom:** With `--skip-network-checks`, `--check` still ends with "These must be fixed first:" and the blocked outbound port 25 (or a Spamhaus listing), and exits with code 1. The real run with the same options does not stop on them, so the check and the run disagree.
* **Cause:** check_summary() added the network blockers to the list of blockers without looking at `--skip-network-checks`; only phase stop-old honoured the option.
* **Fix:** With `--skip-network-checks`, `--check` lists them under "Ignored because of --skip-network-checks" and does not count them as blockers; the command it suggests keeps the option. Without the option nothing changes.
* **Affects:** v78 no, PR #2603 no. Origin: Fork (the migration tool, since rc1).
* **Evidence:** rc6 T2: `--check ... --skip-network-checks` on a test box with port 25 blocked listed the port as the only blocker and exited 1; the run with the same options started.
* **Found by:** test run (T2 of rc6); **commit:** see `git log --grep B77`; **fixed in:** v78-r2604.0-rc6

### B78

**After a Postfix restart at the wrong moment, every start of Postfix delays the first SMTP greetings by 100 seconds** (low, Postfix)

* **Symptom:** After each start of Postfix (a setup run, a reboot, a package update), the first connections to port 25 get the "220" greeting only after about 100 seconds; then it works normally until the next start. mail.log shows `postfix/tlsmgr: error: open database /var/lib/postfix/smtp_scache.db: File exists` and `warning: btree:/var/lib/postfix/smtp_scache is unavailable` 100 seconds after "open smtp TLS cache". The TLS session cache for outgoing mail stays off. Senders retry, so no mail is lost, but it is delayed.
* **Cause:** The package's `main.cf` keeps the outgoing TLS session cache in a Berkeley DB btree (`smtp_tls_session_cache_database = btree:${data_directory}/smtp_scache`). tlsmgr empties it when it starts; Berkeley DB writes the new file as `__db.smtp_scache.db` first and renames it. When Postfix is stopped during that moment, the temporary file stays. Every later tlsmgr finds it, retries for 100 seconds, gives up with "File exists" and runs without the cache. Meanwhile smtpd on port 25 sent no greeting (port 587 answered at once in the test). setup restarts Postfix several times within seconds, which is enough to hit it.
* **Fix:** setup/mail-postfix.sh adds a systemd drop-in, `/etc/systemd/system/postfix.service.d/mailinabox-stale-db.conf`, that removes `/var/lib/postfix/__db.*` before each start of Postfix. While Postfix is stopped these files are always stale. The in-place tool does not count this drop-in as a local extension.
* **Affects:** v78 yes, PR #2603 yes. Origin: Upstream (the package default and the restarts of setup). Not reproduced on 22.04, which has the same default and Berkeley DB 5.3.
* **Evidence:** rc6 T2 (migration to a fresh 26.04 test box): setup restarted Postfix 60 ms after tlsmgr had started to open the cache (journal), and `__db.smtp_scache.db` stayed from that moment. After that, every restart of Postfix gave the first port 25 connection its greeting after 100 seconds, with the errors above. With the file removed, the greeting came at once; with the file put back and the drop-in in place, a start removed it and the greeting came at once.
* **Found by:** test run (T2 of rc6); **commit:** see `git log --grep B78`; **fixed in:** v78-r2604.0-rc6

### B79

**setup stops with "Could not get lock" when apt-daily or unattended-upgrades runs at the same time** (low, Setup)

* **Symptom:** setup (a fresh install or an update with `setup/bootstrap.sh`) stops in the middle with "FAILED: apt-get ... install ..." and "E: Could not get lock /var/lib/dpkg/lock-frontend. It is held by process N (apt-get)" or "E: Unable to lock directory /var/lib/apt/lists/". The steps after it do not run. Running setup again finishes it.
* **Cause:** Ubuntu's apt-daily, apt-daily-upgrade and unattended-upgrades start by themselves, for example some minutes after a boot, and hold the dpkg or apt locks for a while. setup called apt-get without waiting, and apt-get gives up at once when a lock is taken.
* **Fix:** `apt_get_quiet` in setup/functions.sh waits up to 10 minutes until the dpkg locks, the lock of the package lists and the lock of the download cache are free, and passes `DPkg::Lock::Timeout=600` to apt-get. That option alone only covers the dpkg locks. The other apt-get calls of setup (`update`, `purge`) go through `apt_get_quiet` as well.
* **Affects:** v78 yes, PR #2603 yes. Origin: Upstream.
* **Evidence:** rc6 update test after T1: setup on the copy of a production box (started about 30 minutes after a boot) stopped at "Installing Munin" with the lock error above; the journal showed apt-daily.service starting at that second. On a 26.04 test box with a lock held by a test process, `apt-get install` failed at once without the option and waited with it; `apt-get update` failed at once with and without the option while the lock of the package lists was held.
* **Found by:** update test; **commit:** see `git log --grep B79`; **fixed in:** v78-r2604.0-rc6

### B80

**Munin never sends its alerts: no contact is defined, and there is no "mail" command** (medium, Munin)

* **Symptom:** When a value that Munin watches crosses its warning or critical limit (disk usage, for example), nobody gets a mail. `/var/log/munin/munin-limits.log` says "[WARNING] Missing configuration options for contact admin; skipping" every 5 minutes, on every box.
* **Cause:** setup/munin.sh wrote `contacts admin` and the `contact.admin.*` lines after the `[$PRIMARY_HOSTNAME]` line of munin.conf, and every line after a host line belongs to that host. So there was no global contact "admin", and munin-limits skipped it. The contact's command `mail -s ...` would not have worked either: Ubuntu has no `mail` command unless a mail client is installed, and setup installs none. With `contact.admin.always_send warning critical` the contact would also have sent a mail every 5 minutes while a warning lasts.
* **Fix:** setup/munin.sh defines the contact before the host tree, without `always_send`, so munin-limits mails only when a state changes (ok, warning, critical, unknown), one mail per run with all changes. Its command is `/usr/local/lib/mailinabox/munin-notify` (installed by setup from `management/munin_notify.sh`, root, mode 0755), which sends the text munin-limits pipes into it with `/usr/sbin/sendmail` to administrator@PRIMARY_HOSTNAME, with From, To, Subject ("Munin notification" and the box name), Date, Message-ID and `Auto-Submitted: auto-generated`. The recipient is set in that script only. munin.conf is written on every setup run, so updates and the in-place upgrade get the fix. Setup no longer activates Munin's interface plugins for the veth interfaces of containers (Docker): such an interface gets a new name at each start of its container, and the plugin of the old name reports "unknown" for ever, which would now be mailed as an alert. A box whose limit states are all "ok" sends nothing after the update; a box with a value already in warning or critical mails it only at its next change of state.
* **Affects:** v78 yes, PR #2603 yes, the fork up to rc5. Origin: Upstream (the same lines in v78).
* **Evidence:** All rc6 certification boxes logged the warning every 5 minutes; the log audits of the T5b runs with the fix have no such line. `smoke.py` checks the contact (`munin-alert-contact`), and it passed in those runs. Checked by hand during development, output not kept: on a fresh rc6 test box, a temporary warning limit of 1 % for the root file system (a drop-in in `/etc/munin/munin-conf.d/`) made munin-limits send one mail, which reached the administrator's mailbox through the administrator@ alias; a second run without a change sent none; removing the limit sent one recovery mail, and the run after it none. Likewise from development, output not kept: the T5b box (a copy of a production box with Docker) sent one alert, "veth... errors: UNKNOWNs", 15 minutes after a reboot had restarted the container under a new veth name; hence the veth rule.
* **Found by:** log audit; **commit:** see `git log --grep B80`; **fixed in:** v78-r2604.0-rc6

### B81

**spampd cannot remove its PID file when it stops, a stale one stays in /run** (low, Spam)

* **Symptom:** Each stop or restart of spampd logs `Couldn't unlink "/run/spampd.pid" [Permission denied]`, and `/run/spampd.pid` stays with the old process ID. Should a later process get that ID, Net::Server would refuse to start spampd.
* **Cause:** The 26.04 package runs spampd 2.62 with `/etc/spampd.cfg` (`pid /run/spampd.pid`, `user spampd`). Net::Server writes the PID file as root and removes it at the stop, when it runs as user spampd, which cannot delete files in `/run`.
* **Fix:** setup/spamassassin.sh adds a systemd drop-in, `/etc/systemd/system/spampd.service.d/mailinabox-stale-pid.conf`, with `ExecStopPost=/usr/bin/rm -f /run/spampd.pid`: systemd removes the file as root after each stop (also after a crash), so no stale PID file stays. The PID file stays where the package puts it, in the root-owned `/run`. spampd's own message at the stop remains; it is harmless (spampd has dropped its privileges by then), and `tests/fork/log-audit-allow.txt` lists it. The in-place tool does not count the drop-in as a local extension.
* **Not done, and why:** A first version of this fix (on the branch before the release, never tagged) moved the PID file to `/run/spampd/`, a directory owned by spampd, so that spampd could remove it. That is a local privilege escalation: Net::Server opens the PID file as root with a plain `open '>'` and then chowns it to spampd, both following symlinks. A compromised spampd (it parses untrusted mail through SpamAssassin) could put a symlink there, for example to `/etc/sudoers`, and at the next start root would truncate that file and give it to spampd. Removing the file before the start does not close the race, and a sticky directory does not help (`fs.protected_symlinks` covers only world-writable sticky directories). Setup removes that version's drop-in (`mailinabox-pidfile.conf`) and `/run/spampd` from boxes that ran it, and sets `pid /run/spampd.pid` again.
* **Affects:** v78 no (spampd 2.53 of 22.04), PR #2603 yes, the fork up to rc5. Origin: 26.04 change.
* **Evidence:** rc6 certification runs: the message at every stop on the fresh, migrated, updated and upgraded boxes, and `/run/spampd.pid` left behind with the old process ID. With the fix, on the T5b box after the final run (`5d2d3aa`): the file was gone after `systemctl stop spampd` and written again by the next start, with the new process ID; `/run/spampd` does not exist.
* **Found by:** log audit; **commit:** see `git log --grep B81`; **fixed in:** v78-r2604.0-rc6

### B82

**Cron jobs run while setup runs; their mail to root bounces before the root alias exists** (low, Setup)

* **Symptom:** On a fresh install or a migration to a new machine, mail.log shows mail to `root@PRIMARY_HOSTNAME` bounced with "User doesn't exist", and the bounce to the sender (`munin@` or `www-data@`) is dropped. In the migration test it was the output of Nextcloud's `cron.php`, run by `/etc/cron.d/mailinabox-nextcloud` in the middle of the Nextcloud upgrade steps; on a fresh install it was munin-cron, which ran between the unpack and the configuration of the munin package and failed with "Permission denied" and "Cannot create temporary file".
* **Cause:** cron runs during setup. Setup installs the cron jobs early (Nextcloud, Munin), and they then run against services that setup has not finished. Their mail to root goes to root@PRIMARY_HOSTNAME, an automatic alias that setup/start.sh writes near the end. `tools/migrate-to-2604.sh` stopped cron on the new machine only when setup had already run there, although its comment said cron was stopped; `tools/upgrade-in-place-to-2604.sh` keeps cron stopped until setup has finished.
* **Fix:** setup/start.sh stops cron at its start and starts it again when it ends, also when it fails (a trap). A cron that is already stopped (the in-place and migration tools stop it themselves) is left alone.
* **Affects:** v78 yes (cron runs during setup; v78 has no root@ alias at all), PR #2603 yes. Origin: Upstream.
* **Evidence:** rc6 T2 (migration to a fresh 26.04 test box): cron ran during the whole migration (about 42 minutes), and a cron job's mail to root bounced at 10:03:26 (a mail to www-data@ at 10:03:27); rc6 T1 (fresh install): munin-cron at 10:05:01 during the munin install, the same bounce. With the fix, on the T5b box (`5d2d3aa`): cron was stopped at the start of each of the two update runs and started at its end (journal: 14:57:15 to 14:59:07 and 15:09:56 to 15:11:28 for runs of 112 and 93 s).
* **Found by:** log audit; **commit:** see `git log --grep B82`; **fixed in:** v78-r2604.0-rc6

### B83

**nsd keeps its old listen addresses and logging after setup changed nsd.conf** (low, DNS)

* **Symptom:** After the address of a box changed (PRIVATE_IP or PRIVATE_IPV6), nsd still answers only on the old address until it is restarted. After an in-place upgrade nsd keeps logging to stderr (journal lines with their own time stamp prefix, and "Cannot open /var/log/nsd.log") until the next reboot.
* **Cause:** setup writes the `server:` section of `/etc/nsd/nsd.conf` (the addresses to listen on, the logging), but never restarts nsd; the management daemon only runs `nsd-control reconfig` and `reload`, which reload the zones and keep the listen addresses and the log settings.
* **Fix:** setup/dns.sh restarts nsd when it changed nsd.conf and nsd is running.
* **Affects:** v78 yes, PR #2603 yes. Origin: Upstream. Only when nsd.conf changes: a new address, or the first setup run after an upgrade from a release with the old `logfile:` setting.
* **Evidence:** rc6 certification lab: after a v74 test box got new addresses and setup ran again, nsd refused port 53 on the new address until a reboot. rc6 T3 and T4 (in-place upgrades): nsd logged to stderr from the start of the new release until the reboot after setup. With the fix, on the T5b box (`5d2d3aa`): the two update runs, which did not change nsd.conf, did not restart nsd (only the reboots did). The restart with a changed nsd.conf was checked by hand during development; that output was not kept.
* **Found by:** log audit; **commit:** see `git log --grep B83`; **fixed in:** v78-r2604.0-rc6

### B84

**On 22.04 systemd complains about the tools' tmux scope at every daemon-reload** (low, Tools)

* **Symptom:** From the start of `tools/upgrade-in-place-to-2604.sh` on Ubuntu 22.04 until the first reboot, the journal gets 19 to 20 lines like `/run/systemd/transient/upgrade-2604-4164.scope:12: Missing '=', ignoring line.` and "Unknown key name 'rc' in section 'Unit'" at every daemon-reload of the upgrade (more than 3000 lines in a test run). The upgrade is not affected.
* **Cause:** The tools start their tmux session in a scope (`systemd-run --scope`) without `--description`, so systemd uses the command line as the description, here a multi-line `bash -c` script. systemd 249 (22.04) writes it into the transient unit file without escaping the line breaks and then reads the lines as settings.
* **Fix:** Both tools give the scope a description ("Mail-in-a-Box upgrade to Ubuntu 26.04 (tmux session upgrade-2604)", the migration likewise), and so does the scope that continues the upgrade after a reboot ("... (resumed after a reboot)"). The resume script, which runs that scope without tmux with `eval exec`, quotes the scope command with `printf %q`; with the old `${SCOPE[*]}` the description's spaces and parentheses would have broken the command line.
* **Affects:** v78 no, PR #2603 no. Origin: Fork (rc4, the automatic tmux). The messages appear only on 22.04; `tools/migrate-to-2604.sh` runs on 26.04, where only the description was the script.
* **Evidence:** rc6 T4 (22.04 test box): 3382 such lines from 09:32 until the reboot into 24.04, all for the scope `upgrade-2604-<PID>`. Check of the fix on a 26.04 test box (systemd 259), with the scope lines taken from both tools: `bash -n` passes, the scopes and their transient files carry the description, and a daemon-reload logs nothing. The resume script, generated by the tool with a state directory, `TAG` and `SOURCE` that contain spaces, quotes and `$`, started the tool with unchanged path, arguments and environment in all three forms (tmux, `exec` in a scope, plain `exec`); the old `exec` line with the new description failed with a syntax error. Limit: systemd 259 logs nothing even for the old scope, so the absence of the 22.04 messages was not reproduced on systemd 249; T4 was not repeated with the fix.
* **Found by:** log audit; **commit:** see `git log --grep B84`; **fixed in:** v78-r2604.0-rc6

### B85

**After the weekly rotation of mail.log Dovecot writes into mail.log.1, and fail2ban's Dovecot jails see no failed login** (medium, Dovecot)

* **Symptom:** After logrotate has rotated `/var/log/mail.log`, Dovecot's lines (logins, failed logins, LMTP deliveries) no longer appear in `mail.log` but in `mail.log.1`, until Dovecot restarts. In that time the fail2ban jails `dovecot` and `miab-slow-dovecot` ban nobody: password guessing on IMAP, POP3 and ManageSieve goes unpunished. The mail log report (`management/mail_log.py`), the failed-login part of the admin's fail2ban report and `tests/fork/log-audit.sh` miss those lines in `mail.log` as well. In the smoke test of the rc6 certification run of T5b, 26 failed logins each on IMAP, POP3 and ManageSieve from the peer banned nobody (fail2ban-imap, -pop3, -managesieve FAIL).
* **Cause:** Since upstream commit fac8477 (2016, "Configured Dovecot to log into its own logfile", together with `logpath = /var/log/mail.log` for the fail2ban jail) Dovecot writes `/var/log/mail.log` itself (`log_path`) and keeps the file open. logrotate rotates `mail.log` with the rsyslog entry of the rsyslog package, whose postrotate only sends rsyslog a HUP. Dovecot is not told and goes on writing into the renamed file. The nightly backup stops and starts Dovecot, which then opens the new file. The same setting has Dovecot's log process, which runs as root, open `mail.log` by name at every start, following a symlink, in `/var/log`, which the group syslog may write (root:syslog 0775 on Ubuntu; `fs.protected_symlinks` does not apply there).
* **Impact:** The Dovecot jails are blind from each weekly rotation (logrotate.timer: daily at midnight with up to 1 hour random delay; `mail.log` weekly) until the next Dovecot restart, on a box usually the nightly backup (`/etc/cron.d/mailinabox-nightly`, about 01:00-02:00): about one to two hours per week. Longer when logrotate runs after the nightly job, e.g. when logrotate.timer catches up after a boot (`Persistent=true`), when no backup runs, or when the backup fails before it stops Dovecot: then up to a day or more.
* **Fix:** `setup/mail-dovecot.sh` sets `log_path=syslog` (Dovecot's default) instead of `/var/log/mail.log`. Dovecot sends its lines to syslog with facility mail; rsyslog, which runs as user syslog, writes them into `/var/log/mail.log` together with Postfix's, and logrotate's rsyslog entry has it reopen its files after each rotation. No Dovecot process opens or holds a file in `/var/log` any more; the root log process only writes to the syslog socket. The lines take rsyslog's form: `<RFC 3339 time> <host> dovecot: imap-login: Logged in: ...`, without `Info:` (warnings and errors keep `Warning:` and `Error:`). The fail2ban filters (`dovecotimap`, `miab-dovecot-authfail`: `dovecot: ` is in fail2ban's `__prefix_line`, `Info: ` was optional) and the failed-login report (`management/fail2ban_admin.py`) match both forms; `management/mail_log.py` takes the process after `dovecot: ` as the service and accepts the lines without `Info: `; `tests/fork/log-audit.sh` files them under Dovecot's process, as the old lines. The old lines in rotated files keep their form and are still read. rsyslog shortens a line that repeats the one before it to "message repeated N times"; Dovecot's login lines carry their session ID, so two of them are never equal. Setup removes the path unit of the second test version (below) from boxes that ran it.
* **Not done, and why:** Two earlier versions on the branch, never tagged, were replaced. The first had a path unit (`mailinabox-dovecot-log-reopen.path`, watching `mail.log.1`) start a helper that created, chowned and chmodded the new `mail.log` as root in `/var/log`; the syslog user could put a symlink there, and a file such as `/etc/shadow` would have ended up owned by syslog. The second helper did no file operation itself: it had rsyslog create the file, checked that `mail.log` was a regular file of rsyslog's user with one link, not a symlink, and then ran `doveadm log reopen`. But Dovecot's root log process then opened the path again by name, so the file could be swapped for a symlink between the check and the open; and since the group syslog can change `mail.log.1` at any time and the unit had no start limit, an account in that group could have root reopen the path as often as it liked to win that race. A reopen also has Dovecot create a missing `mail.log` as root with mode 0600, which rsyslog can no longer write. A root-only directory for a file of Dovecot's own (for example `/var/log/dovecot/`) would be safe as well, but would take Dovecot's lines out of `mail.log`, where the jails, `mail_log.py`, the report and administrators look for them. An edit of `/etc/logrotate.d/rsyslog` would be undone by the rsyslog package (conffile), and a second logrotate entry for `mail.log` is an error. The second version's note that syslog would lose bursts of Dovecot lines to rate limits was wrong (see Evidence).
* **Affects:** v78 yes, PR #2603 yes, the fork up to rc5. Origin: Upstream (fac8477, 2016).
* **Evidence:** Control by hand on the T5b box at `c7fd0bb` (Dovecot with its own `log_path`): `logrotate -f` of the rsyslog entry, then 26 failed IMAP logins from the peer: Dovecot's log process wrote `mail.log.1`, all 26 lines went there, and the `dovecot` jail found none. The smoke test of the T5b run at `c7fd0bb` had the three Dovecot fail2ban FAILs above; Dovecot restarted at 13:16:39, at the start of the second update run. A production box on rc3 showed the same: after the weekly rotation Dovecot's log file descriptor pointed to `mail.log.1`. `tests/fork/smoke.py --fail2ban` rotates `mail.log` once before the attacks (`fail2ban-log-rotation`), so a blind jail fails the test. With the fix (final T5b run at `5d2d3aa`, update from rc3, see TESTING-fork.md): `fail2ban-log-rotation` passed (`log_path=syslog`, no Dovecot process holds a file in `/var/log`, rsyslog wrote the new `mail.log` as syslog:adm 0640), and then the Dovecot jails banned the peer on IMAP, POP3 and ManageSieve; `mail-log-logins` counted the IMAP and POP3 logins in the new line form; smoke 75/75. On that box: the units and the helper of the second version were not installed, and 30000 lines from one process of a service unit, sent through syslog with facility mail in 1.3 s, all reached the journal and `mail.log` (journald's default burst is scaled by the free disk space; rsyslog's `imuxsock` has no rate limit by default).
* **Found by:** update test (the fail2ban group of the smoke test, rc6 T5b); **commit:** see `git log --grep B85`; **fixed in:** v78-r2604.0-rc6

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
* **Fix:** write_settings() writes a new file under a random name in the same directory (`mkstemp`, `O_EXCL`, never through a link), keeps the read bits of the old file's mode, nothing more (0600 for a new one; a mode such as 0666 or setuid that the storage user gave a file of its own becomes 0644), and renames it over the old file; load_settings() opens it with `O_NOFOLLOW` and `O_NONBLOCK` and reads only a regular file (a link, a FIFO or anything else reads as no settings, and a FIFO no longer blocks the daemon).
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

**setup sources a file with a fixed name in /tmp as root: local root** (critical, Setup)

* **Symptom:** None in normal operation. A local user without privileges (a shell account on the box, or a service account that can write to `/tmp`, such as www-data: Ubuntu's PHP-FPM has no private `/tmp`, so a weakness in Nextcloud, Roundcube or Z-Push is enough) creates `/tmp/mailinabox.prev.conf` with shell commands. The next time the admin runs setup on the box (`sudo mailinabox`, an update with `setup/bootstrap.sh`, the upgrade and migration tools), setup runs these commands as root. Setup prints "/tmp/mailinabox.prev.conf: Permission denied" and goes on as usual.
* **Cause:** On every run after the first, setup/start.sh wrote `/etc/mailinabox.conf` with the prefix DEFAULT_ to `/tmp/mailinabox.prev.conf`, sourced that file and removed it. `/tmp` is writable by everyone. With `fs.protected_regular` (Ubuntu's default, 2) root may not open another user's file in the sticky `/tmp` for writing, so the copy fails, and the `source` that follows reads the other user's file; without that protection root would overwrite the file, which still belongs to the other user, who could change it between the write and the `source`.
* **Fix:** setup sources the output of `sed` directly (process substitution, `source <(sed s/^/DEFAULT_/ /etc/mailinabox.conf)`); no file is written.
* **Affects:** v78 yes, PR #2603 yes, the fork up to rc6. Origin: Upstream. Only boxes with a local user or service that an attacker controls; the first install (no `/etc/mailinabox.conf` yet) does not read the file.
* **Evidence:** On a fresh 26.04 test box, an unprivileged user wrote `id > /root/b96-proof.txt` into `/tmp/mailinabox.prev.conf`; the three lines of setup/start.sh, run with sudo, printed "Permission denied" and wrote `uid=0(root)` into `/root/b96-proof.txt`, then removed the user's file. Setup with the fix (update runs from the same version, non-interactive with the values of `/etc/mailinabox.conf`, and interactive): exit 0, the previous answers used.
* **Found by:** rc7 development, and independently by rc7 review (as B96); **commit:** see `git log --grep B89` and `git log --grep B96` (the same change on two branches); **fixed in:** v78-r2604.0-rc7

### B90

**The in-place tool copies the encrypted system archive as root through the user-data account's directory** (low, Tools)

* **Symptom:** For backups on the machine itself (target `local`, or a `file://` target), phase snapshot of `tools/upgrade-in-place-to-2604.sh` ran `mkdir -p` and `cp` as root on `$STORAGE_ROOT/backup/encrypted-system/<stamp>/` (or `<target>-system/<stamp>/`). Nothing went wrong in the test runs.
* **Cause:** `$STORAGE_ROOT` (`/home/user-data`) belongs to the user-data account (mode 0755). That account may rename `backup` and put a symlink in its place; root's `mkdir -p` and `cp` then follow it and create directories and the archive files wherever the symlink points. The same for a `file://` target below a directory that another account may write.
* **Impact:** Low: it needs code running as user-data (the account of `$STORAGE_ROOT`, which runs the backup hooks), at the moment of the snapshot, and the content of the files is fixed (the encrypted archive and its checksum). Against the rule of the fork that root does no file operations by path in directories that another account may write.
* **Fix:** `offsite_copy` copies to a local or `file://` target only when the target's directory and all directories above it are root's own (not symlinks, owned by root, not writable by group or others; `root_only_path`). Otherwise the encrypted archive stays in `/root/upgrade-2604` (mode 0700), and the tool says so; it already advised to copy a copy on the machine off it. `tools/update-check.sh backup` keeps its archive in `/root/update-check/<stamp>/` for such targets from the start.
* **Affects:** the fork rc1 to rc6. Origin: Fork.
* **Evidence:** From reading the code; `root_only_path` checked on the box replica of the update test (rc6 after T5b): `/home/user-data/backup/encrypted`, `/home/user-data/backup`, `/tmp/x` and `/var/log` are not root-only, `/root/upgrade-2604/x/y`, `/etc/ssh` and `/mnt/nonexistent/a` are.
* **Found by:** rc7 review; **commit:** see `git log --grep B90`; **fixed in:** v78-r2604.0-rc7

### B91

**The management daemon leaks a users.sqlite connection per database call and runs out of file descriptors** (high, Management)

* **Symptom:** After a few hundred API calls (the control panel, the status checks of the panel, scripts) the management daemon answers every request with 500; its journal shows `sqlite3.OperationalError: unable to open database file`. A restart of `mailinabox.service` helps until the next few hundred calls.
* **Cause:** `mailconfig.open_database()` never closes the connection it opens; most callers only keep the cursor. Since Python 3.11 a sqlite3 connection is only freed by the cyclic garbage collector, which rarely gets to them in the daemon: each call left `users.sqlite` open, from 1 time (any authenticated GET, through the password check) to about 90 times (`/ssl/status`). The gunicorn worker has a limit of 1024 open files.
* **Fix:** open_database() returns a cursor class that closes its connection when the cursor is freed, which is when the calling function returns (the cursor is in no reference cycle; all callers keep cursor and connection in local variables). An uncommitted transaction is rolled back then, as the garbage collector did before.
* **Affects:** v78 no (Python 3.10 on 22.04 freed the connections by reference counting), PR #2603 yes, the fork up to rc6. Origin: 26.04 change (Python 3.14).
* **Evidence:** fresh-install test box (Python 3.14): the worker held 1013 descriptors of `users.sqlite` after the panel checks and one API smoke run, and the round trip failed with 500 on `users/remove`. Per endpoint, 5 calls each: +7 descriptors for `/system/version`, +20 `/mail/users`, +55 `/dns/zones`, +185 `/web/domains`, +190 `/dns/dump`, +433 `/ssl/status`. With the fix the same 15 endpoints left +0, and after the full `--only api` and `--only admin` runs the workers held 0 descriptors of `users.sqlite`.
* **Found by:** rc7 development (the new smoke group `api`); **commit:** `093118d`; **fixed in:** v78-r2604.0-rc7

### B95

**The OpenDKIM tables are rewritten in another order, and OpenDKIM restarted, without a change** (low, Mail)

* **Symptom:** On a box with more than one mail domain, each run of setup and the first DNS update after each start of the management daemon (e.g. after a reboot) rewrite `/etc/opendkim/KeyTable` and `/etc/opendkim/SigningTable` with the same lines in another order and restart OpenDKIM, although no domain changed; in a setup run that is a second restart after the one of setup/dkim.sh. A comparison of `/etc` before and after an update shows both files as changed, and a mail sent in the moment of a restart goes out without a DKIM signature (Postfix passes mail on when a milter does not answer, `milter_default_action=accept`), so it can fail DMARC at the receiver.
* **Cause:** `write_opendkim_tables()` in `management/dns_update.py` writes one line per domain in the order of `get_mail_domains()`, a Python set. The order of a set of strings depends on the hash seed, which Python chooses at random for every process (here: every start of the management daemon), so the content differs from run to run and the "did the file change" check sees a change.
* **Fix:** The domains are sorted before the tables are written. The patterns `*@domain` never overlap (a domain contains no "@"), so the order does not change which key signs a mail. The first run with the fix writes the tables once more in sorted order; from then on they only change when the domains do.
* **Affects:** v78 yes, PR #2603 yes, the fork up to rc6. Origin: Upstream.
* **Evidence:** rc6 T5b: a second update run changed the order of both tables (noted in B74). The same set of four domains printed in four different orders with `PYTHONHASHSEED` 1 to 4. rc7, on a fresh test box with six mail domains: four setup runs after the install (three non-interactive, one interactive) left both tables byte-identical (SHA-256), and OpenDKIM was restarted once per run (by setup/dkim.sh), not by the DNS update.
* **Found by:** update test; **commit:** see `git log --grep B95`; **fixed in:** v78-r2604.0-rc7

### B96

**Duplicate of [B89](#b89)** (Setup)

* The setup strand of rc7 found and fixed the same bug as B89 (setup sources `/tmp/mailinabox.prev.conf` as root) independently, under this ID, and reproduced it on a test box (see the evidence of B89). Both branches made the same change; it is counted once, as B89.
* **Found by:** rc7 review; **commit:** see `git log --grep B96`; **fixed in:** v78-r2604.0-rc7

### B97

**Setup downloads and unpacks code under fixed names in /tmp** (high, Setup)

* **Symptom:** None in normal use. A local user without privileges who watches `/tmp` (inotify) can create a directory under the name that setup is about to use. For Z-Push, setup removes `/tmp/z-push` and then unpacks the release into it; a directory of the other user's own created in between receives the unpacked files, and its owner can replace `Z-Push-*/src` before setup moves it to `/usr/local/lib/z-push`, whose `z-push-admin.php` setup then runs as root. The Roundcube plugins (`git_clone`, `/tmp/git-clone-PID`) work the same way, with code that runs as www-data. The other names (`/tmp/nextcloud.zip`, `contacts.tgz`, `calendar.tgz`, `user_external.tgz`, `roundcube.tgz`, `carddav.tar.gz`, `bootstrap.zip`, `ssl_cert_sign_req-PID.csr`, and `postgrey_whitelist_clients` of the daily cron job) only let the other user make setup fail: root may not write into their file (`fs.protected_regular`) or follow their link (`fs.protected_symlinks`).
* **Cause:** setup/zpush.sh, setup/nextcloud.sh, setup/webmail.sh, setup/management.sh, setup/ssl.sh, `git_clone` in setup/functions.sh and the cron job written by setup/mail-postfix.sh download, unpack and move files as root by fixed or predictable paths in `/tmp`, which everyone can write.
* **Fix:** Each of them uses a directory of root's own from `mktemp -d` (mode 0700, random name) and removes it afterwards. `git_clone` clones into a subdirectory of it, so the plugin directory keeps its usual mode.
* **Affects:** v78 yes, PR #2603 yes, the fork up to rc6. Origin: Upstream. Only during an install or update of the component (a new version), and only with a local user or service that an attacker controls.
* **Evidence:** From reading the code; the race was not run. A fresh install of the fix on a 26.04 test box unpacked all components (smoke test), and no `mailinabox`, `z-push`, `git-clone`, `.zip` or `.tgz` entry was left in `/tmp`.
* **Found by:** rc7 review; **commit:** see `git log --grep B97`; **fixed in:** v78-r2604.0-rc7

### B98

**DNSSEC: the keys are copied to /tmp under their own names for signing** (medium, DNS)

* **Symptom:** A local user without privileges creates files named like the box's DNSSEC keys in `/tmp` (`K<domain>.+<algorithm>+<key tag>.private` and `.key`; domain, algorithm and key tag are in the public DNSKEY records). From then on each DNS update of that zone fails with "Permission denied" (`fs.protected_regular`), in setup and in the management daemon, and the zone is no longer signed again; its signatures expire 30 days after the last signing, and resolvers that validate DNSSEC then reject the domain. On a system without `fs.protected_regular` root writes the private key into the other user's file instead.
* **Cause:** `sign_zone()` in `management/dns_update.py` wrote a copy of each key with the real domain name to `'/tmp/' + key name` (with umask 077, but by a fixed path in a directory that everyone can write) and removed the copies after signing.
* **Fix:** The copies go into a `tempfile.TemporaryDirectory()` (mode 0700, random name), which is removed after signing, also when signing fails.
* **Affects:** v78 yes, PR #2603 yes, the fork up to rc6. Origin: Upstream. Only boxes with a local user or service that an attacker controls.
* **Evidence:** From reading the code. On a fresh 26.04 test box with the fix, setup signed the zones (`.signed` files and DS records written), and no key file was left in `/tmp`.
* **Found by:** rc7 review; **commit:** see `git log --grep B98`; **fixed in:** v78-r2604.0-rc7

### B99

**ActiveSync cannot sync the address book of new users: Nextcloud's example contact breaks Z-Push** (high, Z-Push)

* **Symptom:** A phone that syncs a new user's contacts over ActiveSync gets HTTP 500 for the Sync of the address book, every time, and shows no contacts. `/var/log/z-push/z-push-error.log`: "Attempt to read property "vcard" on null" and "Fatal error: /usr/local/lib/z-push/backend/carddav/carddav.php:484 - Uncaught Error: Call to a member function __toString() on null" (from `BackendCardDAV->GetMessage()`). Mail and calendar sync are not affected.
* **Cause:** The dav app of Nextcloud 34 (1.40) writes an example contact into the default address book of each new user, with the card name `default` (`ExampleContactService::createDefaultContact()`). Z-Push's CardDAV client (`include/z_carddav.php`, `get_xml_vcard()`) appends `.vcf` to every card it fetches, so it asks for `default.vcf`, gets an empty answer, and `GetMessage()` dereferences the missing card.
* **Fix:** setup/nextcloud.sh sets `occ config:app:set dav enableDefaultContact --value false --type boolean`, so new users get no example contact. Example contacts of users created before stay (setup does not delete user data); deleting the example contact in Nextcloud's Contacts makes their address book sync. B128 fixes Z-Push itself, so that such cards sync.
* **Affects:** v78 no (Nextcloud 27), PR #2603 yes (Nextcloud 34), the fork up to rc6. Origin: PR #2603.
* **Evidence:** fresh 26.04 test box of the setup tests of rc7: a minimal ActiveSync 14.0 client (Provision, FolderSync, Sync, Ping) for the admin, whose address book held only Nextcloud's `default` card, got HTTP 500 for the second Sync of the contacts folder with the errors above. With the setting, a user created afterwards had no example contact; Sync answered 200 (status 1) and a Ping on the contacts folder ran its 20 s heartbeat and ended with status 1, no new line in the error log. The smoke test checks only `OPTIONS` of ActiveSync.
* **Found by:** rc7 development (the setup tests of rc7, log audit of the restart window); **commit:** see `git log --grep B99`; **fixed in:** v78-r2604.0-rc7

### B100

**The fallback SSH server of the in-place tool never starts on a box without the group admin** (high, Tools)

* **Symptom:** Before each release upgrade `tools/upgrade-in-place-to-2604.sh` says "No administrator (group sudo or admin, or root) has an SSH key; no fallback SSH server." although the administrators have keys, and new SSH logins fail while the release upgrade replaces OpenSSH, as before rc7.
* **Cause:** `fallback_users` read the members with `getent group sudo admin`. getent exits 2 when one of the keys does not exist, and Ubuntu has had no group `admin` since 12.04. Under the tool's `set -euo pipefail` the failed assignment ended the process substitution that lists the users before it printed any, root included.
* **Fix:** one `getent group` call per group, and a missing group is no error.
* **Affects:** the development of rc7 only (the fallback is new in rc7, never in a tag). Origin: Fork.
* **Evidence:** reproduced with the function under the tool's shell options on a machine without the group `admin`: no user and the ERR trap before the fix, the members of sudo and root after it. The lab box of the rc7 development has a group `admin` (gid 107), which is why its runs of `--ssh-fallback-test` did not show it.
* **Found by:** rc7 review; **commit:** see `git log --grep B100`; **fixed in:** v78-r2604.0-rc7

### B101

**The fallback SSH server of the in-place tool logs in with a key alone where sshd asks for more, and listens on all addresses** (medium, Tools)

* **Symptom:** During a release upgrade (and `--ssh-fallback-test`) the fallback on port 1022 lets an administrator in with the key alone where sshd asks for a key and a second factor (`AuthenticationMethods publickey,keyboard-interactive`, e.g. a one-time password), ignores what `Match` blocks restrict (e.g. `PermitRootLogin no` for some source addresses), the FIDO touch or PIN of `PubkeyAuthOptions`, `ForceCommand` and `ChrootDirectory`, and listens on all addresses where sshd listens only on an internal or VPN address (ufw opens the port from anywhere). Where sshd does not listen on 127.0.0.1, the tool never sees port 22 answer again and leaves the fallback running until the reboot, with a warning that port 22 does not answer.
* **Cause:** `ssh_fallback_start` wrote `AuthenticationMethods publickey` and copied only a fixed list of keys from `sshd -T`, without `authenticationmethods`, `listenaddress`, `pubkeyauthoptions`, `forcecommand` and `chrootdirectory`. `sshd -T` without `-C` does not apply Match blocks. `ssh_banner` connected only to 127.0.0.1.
* **Fix:** The fallback does not start where sshd accepts no keys, where no alternative of `AuthenticationMethods` is a key alone, or where `sshd_config` or a file it includes has a `Match` line; the tool says why and advises to keep a connection open. It listens on the ListenAddress addresses of sshd (on its own port) and keeps `PubkeyAuthOptions`, `ForceCommand`, `ChrootDirectory`, `PermitTTY`, `PermitUserRC` and `Banner`. The banner check of port 22 (and of the fallback's port) tries each listen address of sshd (0.0.0.0 and `[::]` as 127.0.0.1 and ::1), read before the release upgrade.
* **Affects:** the development of rc7 only (never in a tag). Origin: Fork. Only boxes with such sshd settings; the default configuration of Ubuntu (keys or passwords, all addresses, no Match block) was not affected.
* **Evidence:** from reading the code; on the rc7 test box `sshd -T` printed `permitrootlogin prohibit-password` and `sshd -T -C addr=192.0.2.5` `no` for a `Match Address 192.0.2.0/24` block. With the fix on that box: `--ssh-fallback-test` with the default configuration wrote `ListenAddress [::]:1022` and `0.0.0.0:1022`, a key login on port 1022 worked, and the end of the test stopped the server, closed the ufw rule and removed its files; with a `Match` block in `sshd_config.d` it refused with the warning (removed again afterwards). The checks of `AuthenticationMethods` (any, `publickey,keyboard-interactive`, `publickey,password publickey`) and `PubkeyAuthentication no` were run against the function with a stubbed `sshd -T`.
* **Found by:** rc7 review; **commit:** see `git log --grep B101`; **fixed in:** v78-r2604.0-rc7

### B102

**The in-place tool passes the host of an rsync backup target to ssh unchecked, so a leading "-" is read as an option** (low, Tools)

* **Symptom:** None in normal operation. For an rsync backup target, phase snapshot of `tools/upgrade-in-place-to-2604.sh` runs `ssh ... USER@HOST "mkdir -p PATH-system/STAMP"` and then rsync as root, with USER@HOST and PATH taken from `$STORAGE_ROOT/backup/custom.yaml`. A target such as `rsync://-oProxyCommand=.../x` makes ssh read the host as an option.
* **Cause:** `offsite_rsync` checked the characters of the path only, and neither path nor host for a leading "-". `custom.yaml` lies below `$STORAGE_ROOT`, which belongs to the user-data account: that account can rename `backup/` and put its own `custom.yaml` there (the same threat as B90). The control panel does not save such a target, because its own rsync check fails on it.
* **Impact:** Low. OpenSSH 9.6 and later (and the patched OpenSSH of Ubuntu) refuse the destination that follows such an option, `"mkdir -p ..."`, with "hostname contains invalid characters" before they run a ProxyCommand or open a log file of `-E`, and the tool stops there; an OpenSSH without that check would run the ProxyCommand as root. It needs code running as user-data and the moment of the snapshot.
* **Fix:** The host must be `[user@]host` of letters, digits, `.`, `_` and `-`, each part starting with a letter, digit or `_`, and the path must not start with "-"; otherwise the tool stops and names `--no-offsite`. ssh gets `--` before the host. The new `tools/update-check.sh backup` (rc7) checks the same and had allowed a leading "-" in its first version.
* **Affects:** the fork rc3 to rc6 (the in-place tool). Origin: Fork. A target with an IPv6 address in brackets is now refused with that message (copy the archive by hand).
* **Evidence:** from reading the code. On OpenSSH 10.2 (26.04): `ssh ... "-oProxyCommand=touch pwned" "mkdir -p box-system/x"` and `ssh ... -Elnk "mkdir -p ..."` both ended with "hostname contains invalid characters"; no file was created, and the target of the symlink `lnk` was not written. The new checks accept `u123456@backup.example.net`, `backup@192.0.2.5` and `host.example` and refuse `-Evmlinuz`, `-oProxyCommand=...`, `u@-o...`, names with spaces and a path `-rf`. The OpenSSH builds of 22.04 and 24.04 were not tried.
* **Found by:** rc7 review (in `tools/update-check.sh`, then the same code in the in-place tool); **commit:** see `git log --grep B102`; **fixed in:** v78-r2604.0-rc7

### B103

**Setup drops PROBE_ADDRESS from /etc/mailinabox.conf, so the mail check after an update is skipped** (medium, Tools)

* **Symptom:** With the probe address set as documented (`PROBE_ADDRESS=` in `/etc/mailinabox.conf`), `tools/update-check.sh mailcheck` after the update says "mailcheck: skipped" and exits 0, and `after` reports the line `mailinabox-conf.txt - PROBE_ADDRESS=...` as UNEXPECTED.
* **Cause:** setup/start.sh writes `/etc/mailinabox.conf` anew on every run from a fixed list of keys, so every setup run, the update included, removed the key. The order of the tool (before, backup, update, after, mailcheck) puts the mail check after it.
* **Fix:** setup/start.sh keeps `PROBE_ADDRESS` (from the environment or the file) when it is a plain mail address; another value is left out with a message (the file is sourced as root).
* **Affects:** the development of rc7 only (never in a tag). Origin: Fork.
* **Evidence:** from reading the code; the lines of setup/start.sh that read and write the file, run against a copy: the key kept on two runs, and `PROBE_ADDRESS='x;id'` left out with the message. Not run in a full setup.
* **Found by:** rc7 review; **commit:** see `git log --grep B103`; **fixed in:** v78-r2604.0-rc7

### B104

**update-check.sh backup fails with two or more Docker volumes, after the Mail-in-a-Box backup** (medium, Tools)

* **Symptom:** `tools/update-check.sh backup --docker-volume A --docker-volume B` stops with "The Docker volumes are in different directories; archive them one by one." after `management/backup.py` (which stops mail for its run) and the system archive have run. With one volume the archive held a bare `_data/` without the volume's name.
* **Cause:** The step archived all volumes in one tar relative to the parent of their mount points and required that parent to be the same. Docker mounts each local volume at `/var/lib/docker/volumes/<name>/_data`, so the parents always differ. The mount points were looked up only after the backup.
* **Fix:** One archive per volume, `docker-volume-<name>.tar.gz.gpg`, of the content of its mount point. The mount points are looked up and checked with the other options, before the Mail-in-a-Box backup.
* **Affects:** the development of rc7 only (never in a tag). Origin: Fork.
* **Evidence:** the mount point of the volume on the box replica of the update test is `/var/lib/docker/volumes/<id>/_data`. With the fix there: `backup --no-miab-backup --no-upload` with that volume and a second test volume wrote `docker-volume-<id>.tar.gz.gpg` and `docker-volume-<test>.tar.gz.gpg`; the second decrypted with the backup passphrase to its one test file, and the checksums matched. The test volume and the archive were removed afterwards.
* **Found by:** rc7 review; **commit:** see `git log --grep B104`; **fixed in:** v78-r2604.0-rc7

### B105

**Any local account can fake the setup marks in the journal, and the log audit then accepts its messages as setup noise** (low, Tests)

* **Symptom:** None in normal operation. An account such as www-data or munin runs `logger -t mailinabox-setup "Mail-in-a-Box setup started"`; `tests/fork/log-audit.sh` then gives everything the box logs from that moment the prefix `[setup]` (a run without an end lasts until the next start), and the rules for setup runs accept the classes they cover (ActiveSync long polls that nginx and PHP-FPM cut, Z-Push's CardDAV errors, the 404 of the Munin probes) at any time. `tools/update-check.sh` runs this audit as root before and after an update of a production box.
* **Cause:** `setup_runs()` selected the marks by `SYSLOG_IDENTIFIER` alone, which the client chooses.
* **Fix:** Only marks with `_UID=0` count; journald sets that field from the sending process. The phases of an in-place upgrade come from the tool's state file in `/root`, which only root can write.
* **Affects:** the development of rc7 only (the setup marks are new in rc7, never in a tag). Origin: Fork.
* **Evidence:** On the fresh-install test box: a line with that identifier from root and one from the account nobody; `journalctl SYSLOG_IDENTIFIER=mailinabox-setup` listed both, with `_UID=0` only root's (test lines with another text, so that they mark no setup run).
* **Found by:** rc7 review; **commit:** see `git log --grep B105`; **fixed in:** v78-r2604.0-rc7

### B106

**update-check.sh does not find the checkout of a box in /mailinabox: no status checks before the update, and the backup stops** (medium, Tools)

* **Symptom:** On a box whose Mail-in-a-Box checkout is `/mailinabox` (installed with an older upstream bootstrap.sh; such a box is upgraded with `tools/upgrade-in-place-to-2604.sh`), `tools/update-check.sh before` records "miab unknown" and "(no /root/mailinabox/management/status_checks.py)" and still says "Status checks: 0 errors, 0 warnings". `backup` stops with "ERROR: /root/mailinabox/management/backup.py is missing", and with `--no-miab-backup` the system archive leaves out the checkout.
* **Cause:** The tool took `/root/mailinabox` as the checkout and otherwise only its own checkout, which it does not have when it runs through `curl ... | bash`. The summary counted the lines of a record that had none.
* **Fix:** The checkout is the directory that `/usr/local/bin/mailinabox` (written by setup: `cd DIR`) changes into, else `/root/mailinabox`, else the tool's own checkout. It must be a git checkout of root's own (no symbolic link, not writable by group or others, also the directories above it), because `management/status_checks.py` and `management/backup.py` run from it as root. The system archive takes that directory. Without status checks the summary says "not run".
* **Affects:** the development of rc7 only (never in a tag). Origin: Fork.
* **Evidence:** The in-place test T3 of rc7 (a copy of a production box on 24.04 with upstream v74 in `/mailinabox`): `before` and `backup` as above. With the fix, `before` through a pipe on the 22.04 test box with v74 in `/mailinabox` recorded `miab v74`, its origin, and 30 errors and 4 warnings of the status checks.
* **Found by:** rc7 certification (T3); **commit:** see `git log --grep B106`; **fixed in:** v78-r2604.0-rc7

### B107

**update-check.sh mailcheck reports FAILED when the mail comes back over TLS** (medium, Tools)

* **Symptom:** The answer of the probe address comes back over port 25, passes the spam filter and is stored, and `tools/update-check.sh mailcheck` still shows "inbound: back after 15 s, from ? with ?" and "RESULT: FAILED". It happens with every answer that arrives with STARTTLS, which on the Internet is almost every one.
* **Cause:** Postfix writes two comments between the client and `by` in its Received header: the TLS session (`(using TLSv1.3 with cipher ... (256/256 bits) ...)`, with parentheses inside) and `(No client certificate requested)`; setup turns them on (`smtpd_tls_received_header=yes`). The pattern of the tool expected `by` right after the first comment, so it found neither the protocol nor the queue ID, and the check for a delivery over port 25 failed.
* **Fix:** The pattern skips any number of comments between the client and `by`, with one level of parentheses inside them.
* **Affects:** the development of rc7 only (never in a tag). Origin: Fork.
* **Evidence:** The in-place test T3 and the update test T5b of rc7, with a test address on the peer box of the test network that answers over port 25: the stored answer had the Received header above (ESMTPS), the pattern gave no match in Python, and the same header without the TLS comments matched. With the fix, `mailcheck` on the T3 box: "from ... with ESMTPS (postfix/smtpd, port 25)" and "RESULT: OK".
* **Found by:** rc7 certification (T3, T5b); **commit:** see `git log --grep B107`; **fixed in:** v78-r2604.0-rc7

### B108

**update-check.sh after never says OK: every setup run moves the nightly job to another minute** (medium, Tools)

* **Symptom:** After an update that changed nothing else, `tools/update-check.sh after` lists `crontabs.txt - /etc/cron.d/mailinabox-nightly <hash>` and `+ /etc/cron.d/mailinabox-nightly <another hash>` as UNEXPECTED and ends with "RESULT: CHANGED".
* **Cause:** setup/management.sh writes the nightly job (backup and status checks) with a new random minute between 01:00 and 01:59 on every run, as upstream does (README-fork.md says so), and `tools/expected-changes/any.txt` had no rule for it.
* **Fix:** A rule in `any.txt` for that file.
* **Affects:** the development of rc7 only (never in a tag). Origin: Fork.
* **Evidence:** The update test T5b of rc7 (rc6 to rc7, two setup runs): the checksum of the file changed before the update, after the first and after the second run. The records of that update, replayed with the version lines of a tag (the test installed a branch), gave 2 unexpected changes, both of this file, and with the rule "RESULT: OK - 0 unexpected, 5 expected changes".
* **Found by:** rc7 certification (T5b); **commit:** see `git log --grep B108`; **fixed in:** v78-r2604.0-rc7

### B109

**The expected changes of rc7 miss changes of rc4 and rc5, so an update from rc1 to rc3 lists them as unexpected** (low, Tools)

* **Symptom:** `tools/update-check.sh after` of an update from rc3 lists as UNEXPECTED: the new `/etc/mailname` and the new 127.0.1.1 line of `/etc/hosts` (B60, rc4), Dovecot from disabled to enabled (B67, rc5) and `mailinabox.service` from unknown to enabled (B69, rc5).
* **Cause:** `tools/expected-changes/v78-r2604.0-rc7.txt` covers the updates from all earlier releases, but its rc4 rules missed B60, and it had no rules for rc5.
* **Fix:** Rules for these changes.
* **Affects:** the development of rc7 only (never in a tag); only updates from rc1 to rc3 show them. Origin: Fork.
* **Evidence:** The update test T5b of rc7, from rc3 directly to rc7: 10 unexpected changes, of them these 6 lines (the others came from installing a branch instead of a tag). The same lines, compared with the new rules: 0 unexpected.
* **Found by:** rc7 certification (T5b); **commit:** see `git log --grep B109`; **fixed in:** v78-r2604.0-rc7

### B110

**update-check.sh after judges an in-place upgrade or a migration from upstream by the lists of the fork's updates** (low, Tools)

* **Symptom:** After an in-place upgrade (Ubuntu 24.04 with upstream v74 to 26.04 with the fork), `tools/update-check.sh after` lists dozens of changes as UNEXPECTED (PHP-FPM and NTP units, the Dovecot 2.4 settings, Nextcloud 26 to 34, crontabs, listening ports) and ends with "RESULT: CHANGED", although each of them belongs to the upgrade.
* **Cause:** The lists in `tools/expected-changes/` describe the updates of this fork on one Ubuntu release, and the tool applied them to every update.
* **Fix:** When the Ubuntu release before and after differs, or the version before is upstream Mail-in-a-Box (not a v78-r2604 release), `after` says so above the changes, lists them without judging them and ends with "RESULT: NOT JUDGED" (exit code 3; 1 if the log audit found new message classes). The help and README-fork.md say so.
* **Affects:** the development of rc7 only (never in a tag). Origin: Fork.
* **Evidence:** The in-place test T3 of rc7: "RESULT: CHANGED - 56 unexpected, 24 expected", every unexpected change one of the release upgrade or of the step from v74.
* **Found by:** rc7 certification (T3); **commit:** see `git log --grep B110`; **fixed in:** v78-r2604.0-rc7

### B111

**The test of the fallback SSH server leaves an empty /root/upgrade-2604** (low, Tools)

* **Symptom:** After `tools/upgrade-in-place-to-2604.sh --ssh-fallback-test` on a box that never ran the tool, an empty directory `/root/upgrade-2604` (root, mode 0700) is left.
* **Cause:** The test creates the tool's state directory for the files of the fallback and removed only those files afterwards.
* **Fix:** The test removes the state directory again when it made it and it is empty (`rmdir`, which removes neither a symbolic link nor a directory with files), from the exit handler, so also when the fallback does not start (a refusal) or the test is ended with Ctrl-C; the first fix covered only a test that ran to its end.
* **Affects:** the development of rc7 only (never in a tag). Origin: Fork.
* **Evidence:** The in-place test T3 of rc7. With the fix, on the fresh-install test box: after a test of 30 s neither `/root/upgrade-2604` nor the ufw rule for port 1022 nor files of the fallback were left. The review run of the fixes (T4) left an empty `/root/upgrade-2604` after a test that refused to start (a `Match` block); with the second fix, on the 24.04 test box, nothing was left after such a refusal.
* **Found by:** rc7 certification (T3); **commit:** see `git log --grep B111`; **fixed in:** v78-r2604.0-rc7

### B112

**The fallback SSH server refuses new logins for up to 10 s after the release upgrade stops ssh.service** (low, Tools)

* **Symptom:** A new login on port 1022 in the seconds after the release upgrade stopped ssh.service fails; sshd logs "fatal: Missing privilege separation directory: /run/sshd".
* **Cause:** Stopping ssh.service removes its RuntimeDirectory `/run/sshd`, which the fallback needs as well. The tool's watcher puts it back, but looked only every 10 s.
* **Fix:** The watcher checks `/run/sshd` every 2 s (port 22 still every 10 s). The comment on the fallback also names the few seconds of the 22.04 to 24.04 upgrade in which `libtirpc3` is removed before `libtirpc3t64` is unpacked; new logins then fail on both ports. The texts of the tool and README-fork.md give the outage times measured in the rc7 tests (port 22: 6 to 16 minutes from 24.04 to 26.04; sudo missing 12 to 31 minutes).
* **Affects:** the development of rc7 only (never in a tag). Origin: Fork.
* **Evidence:** The in-place test T4 of rc7: ssh.service stopped at 20:28:49, the failed login with the message above at 20:28:50, the directory back at 20:28:59. With the fix, on the fresh-install test box during `--ssh-fallback-test`: `/run/sshd` removed by hand was back within 0.5 s.
* **Found by:** rc7 certification (T4); **commit:** see `git log --grep B112`; **fixed in:** v78-r2604.0-rc7

### B113

**migrate-to-2604.sh --check proposes a start command without the options it was given** (low, Tools)

* **Symptom:** `tools/migrate-to-2604.sh --check --from admin@192.0.2.10 --public-ip 192.0.2.11 --public-ipv6 2001:db8::11 --private-ip 192.0.2.11 --skip-network-checks` ends with "Start the migration with: .../migrate-to-2604.sh --from admin@192.0.2.10 --skip-network-checks". Whoever copies that line migrates with the addresses that setup detects instead of the given ones. With `--from-backup` the line says `--from` with nothing after it.
* **Cause:** The line was put together from `--from`, `--ssh-key`, `--ssh-port` and `--skip-network-checks` only.
* **Fix:** It repeats the command line of the check without `--check` (or `--dry-run`), each argument quoted for the shell.
* **Affects:** rc4 to rc6 (the line is new in rc4). Origin: Fork.
* **Evidence:** The migration test T2 of rc6 and of rc7: the check log ends with the short command above.
* **Found by:** rc7 certification (T2; first seen in T2 of rc6); **commit:** see `git log --grep B113`; **fixed in:** v78-r2604.0-rc7

### B114

**update-check.sh after lists munin-node's port as changed when the process shows under another name** (low, Tools)

* **Symptom:** After an update, `tools/update-check.sh after` lists `listening.txt - tcp *:4949 /usr/sbin/munin` and `+ tcp *:4949 munin-node` as UNEXPECTED.
* **Cause:** The record names the process that holds a port by its process name (`ss -p`). munin-node is a Perl script, and its process name is not always the same: the same box showed `/usr/sbin/munin` (the script's path cut to the 15 characters of a process name) after the boot and `munin-node` after setup had restarted it; other boxes showed `munin-node` after a boot. Why it differs was not found out.
* **Fix:** A rule in `tools/expected-changes/any.txt` accepts both names for port 4949.
* **Affects:** the development of rc7 only (never in a tag). Origin: Fork.
* **Evidence:** The repeated update test T5b of rc7 (rc6 to rc7): the record before the update (taken after a boot) had `/usr/sbin/munin`, the one after the setup run `munin-node`; `/proc/<pid>/cmdline` was `/usr/bin/perl -wT /usr/sbin/munin-node --foreground` both times. Other boxes of the test network showed `munin-node`.
* **Found by:** rc7 certification (T5b, repeated run); **commit:** see `git log --grep B114`; **fixed in:** v78-r2604.0-rc7

### B115

**The fallback SSH server of the in-place tool accepts keys that sshd refuses under StrictModes** (medium, Tools)

* **Symptom:** None in normal operation. During each release upgrade (and the 10 minutes of `--ssh-fallback-test`) the fallback on port 1022 accepts an administrator's key from an `authorized_keys` that sshd on port 22 ignores: one whose file, `~/.ssh`, home directory or a directory above them can be written by others or by a group with other members, or belongs to another user.
* **Cause:** sshd (`StrictModes yes`, the default) checks the owner and mode of the key file and of each directory above it up to the home directory (`auth_secure_path`) and ignores the file if one of them fails. Ubuntu's sshd (Debian's user-group-modes patch) accepts a part that its group may write only when that group has exactly one member, the user (a user private group). `user_keys` read the file as the user and copied it into a root-owned file below `/etc/ssh`, which passes that check, so the fallback accepted what sshd had refused. Whoever can write such an administrator's home (for example another account in a shared group of a home with mode 0775) could add a key, log in on port 1022 as that administrator and use sudo.
* **Fix:** With StrictModes (from `sshd -T`) the tool resolves each key file and checks it and the directories above it as Ubuntu's sshd does: a regular file, owned by root or the user, not writable by others, and writable by its group only when the group's only member is the user (no other user has it as primary group, and its member list is empty or only the owner); the same for each directory up to the home directory (or `/`). It skips a file that fails, with a warning, and reads the real path afterwards, which only root and the user can change. The keys file of the fallback is `root:<the user's group>` with mode 0640 (sshd reads it as the user), so other accounts no longer see the key options.
* **Affects:** the development of rc7 only (the fallback is new in rc7, never in a tag). Origin: Fork. Only boxes where another account can write an administrator's home or `.ssh`.
* **Evidence:** from reading the code and OpenSSH's `auth.c`. On the test boxes with OpenSSH 8.9p1 (22.04), 9.6p1 (24.04) and 10.2p1 (26.04), twelve cases each, sshd's own answer to a key login on port 22 compared with the function of the tool: home 0750 and 0775 with a user private group, `authorized_keys` 0664 with it, a root-owned `authorized_keys` and a symbolic link inside `.ssh` taken by both; a home 0775 whose group has a second member (supplementary or primary) or is another user's, a home or `authorized_keys` writable by others, a `.ssh` of another user and a symbolic link into a directory of mode 1777 refused by both. A first version that refused every group-writable part was stricter than Ubuntu's sshd (it refused a home 0775 with a user private group that sshd accepts). Also with the function: an absolute root-owned `/etc/ssh/<dir>/%u` taken, the same in a directory of mode 0775 refused, and with `StrictModes no` the key of a home 0775 taken. In the final run of rc7 (T4, OpenSSH 8.9p1): an administrator with a home 0775 whose group has a second member was refused by sshd on port 22 and, with the warning, by the fallback; the keys file of the other administrator was `root:<group>` 0640 and his login on port 1022 worked.
* **Found by:** rc7 review (of the certification fixes); **commit:** see `git log --grep B115`; **fixed in:** v78-r2604.0-rc7

### B116

**update-check.sh runs the status checks and the backup from a checkout that it has just rejected** (low, Tools)

* **Symptom:** None in normal operation. When `/root/mailinabox` (or a directory above it) is not root's own, `tools/update-check.sh` warns "not used as the Mail-in-a-Box checkout" and then, run through `curl | bash`, uses it anyway: as root it runs `management/status_checks.py` and `management/backup.py` from it, imports its Python modules for the backup target and runs its `tests/fork/log-audit.sh`. Inside an accepted checkout it checked nothing: a group-writable `management/utils.py` or a `.git/config` of another account (which git reads as root) passed.
* **Cause:** `MIAB_DIR` started as `/root/mailinabox`, and the loop of `find_miab_dir` only skipped the rejected candidate without clearing it; `root_only_path` checked the directory and those above it, not the files in it.
* **Fix:** `MIAB_DIR` starts empty; a candidate counts only if, besides the path, every file and directory in it is owned by root and not writable by group or others (symbolic links are not followed). Without a checkout the status checks are "not run", the version is "unknown", the system archive leaves out the checkout, and `backup` needs `--no-miab-backup`.
* **Affects:** the development of rc7 only (never in a tag). Origin: Fork. With `/root` at mode 0700, another account can hardly reach `/root/mailinabox`.
* **Evidence:** from reading the code. On the fresh-install test box: the clean checkout was taken; with `g+w` on `management/utils.py` or a `.git/config` owned by nobody it was rejected with the warning and `MIAB_DIR` stayed empty. The check of the 254 files of the checkout took about 20 ms. Through curl there: with `g+w` on `management/utils.py`, `backup --no-miab-backup --no-upload` warned and archived without the checkout. In the final run of rc7 the checkouts `/mailinabox` (v74, T3) and `/root/mailinabox` (rc6, T5b) were accepted.
* **Found by:** rc7 review (of the certification fixes); **commit:** see `git log --grep B116`; **fixed in:** v78-r2604.0-rc7

### B117

**The tools take the backup target and passphrase, and write custom.yaml, through a directory that the user-data account can replace** (low, Tools)

* **Symptom:** None in normal operation. `tools/update-check.sh backup` and phase snapshot of `tools/upgrade-in-place-to-2604.sh` encrypt the system archive (`/etc` with `/etc/shadow` and the SSH host keys, the crontabs, the checkout) with `$STORAGE_ROOT/backup/secret_key.txt` and copy it to the target in `$STORAGE_ROOT/backup/custom.yaml`, both read as root by path. The in-place and the migration tool pause the backups by moving and writing `custom.yaml` there as root, by path.
* **Cause:** `$STORAGE_ROOT` is the home of the user-data account. That account can rename `backup/` and put a directory of its own in its place, with `secret_key.txt` and `rsync://...` of its choice; the B102 checks only refuse options and shell syntax in the target. The system archive then went, encrypted with a passphrase the account knows, to a host it chose. With a dangling symbolic link as `custom.yaml` or `custom.yaml.upgrade-none` in such a directory, root's writes of the paused file created a file at the link's target.
* **Fix:** The tools open `$STORAGE_ROOT/backup` once and check the open directory: a directory of root's own, not writable by group or others, and the same device and inode as the entry at the path (not a symbolic link). They then read the target and the passphrase and change `custom.yaml` only through that descriptor (`/proc/PID/fd/N/...`), so a directory put there later does not count, and take only regular files of root's in it. Otherwise `update-check.sh backup` stops before anything else, the in-place preflight has a blocker (not `--no-backup-check`), phase snapshot keeps the archive unencrypted in `/root/upgrade-2604` (mode 0700) and copies nothing, and pausing or resuming the backups is left to the operator with a warning. `management/backup.py`, which runs nightly as root, still reads these files by path (upstream code; see "Planned" in CHANGELOG-fork.md).
* **Affects:** the migration tool since rc1, the in-place tool since rc3, `update-check.sh` (new in rc7). Origin: Fork. It needs code running as user-data at the time of the backup or upgrade.
* **Evidence:** from reading the code. On the fresh-install test box, with the functions of the tool: a root-owned directory was taken and its target read through the descriptor, also after it was renamed and replaced by another directory with another target; a directory owned by nobody, a symbolic link, mode 0775 and a symbolic link as a file in it were refused; without `custom.yaml` the target was `local`. Through curl there: `backup` stopped with the message above when `backup/` belonged to nobody, and when it had been renamed and replaced by a directory of the user-data account with another target. In the final run of rc7: `update-check.sh backup` uploaded to the lab's rsync target (T3, T5b), the in-place tool encrypted its system archive and copied it there (T3; on T4, with local backups, it stayed in `/root/upgrade-2604`) and paused and resumed the backups (T3 with the real target, T4 with none), and the migration tool paused and resumed them (T2), each through the checked directory.
* **Found by:** rc7 review (of the certification fixes; in `update-check.sh`, then the same design in the in-place and the migration tool); **commit:** see `git log --grep B117`; **fixed in:** v78-r2604.0-rc7

### B118

**The fallback SSH server misses Match blocks in files included from included files** (low, Tools)

* **Symptom:** On a box whose `sshd_config.d/*.conf` includes another file with a `Match` block (for example `Match User alice` with a second factor, or `Match Address` with `DenyUsers`), `tools/upgrade-in-place-to-2604.sh` starts the fallback SSH server, which applies none of what that block restricts on port 22.
* **Cause:** `ssh_fallback_refusal` (B101) looked for `Match` in `sshd_config` and the files of its own `Include` lines only; sshd follows `Include` in included files as well (up to 16 levels).
* **Fix:** It follows the `Include` lines of every included file (globs, relative paths below `/etc/ssh`, `Include=` and any case, each file once) and refuses the fallback when one of them has a `Match` block, or when the includes go deeper than 16 levels.
* **Affects:** the development of rc7 only (never in a tag). Origin: Fork.
* **Evidence:** from reading the code. On the fresh-install test box, with the function of the tool: a `Match User` block two levels down and a lower-case `match address` three levels down (with a relative `include`) were found, a loop of two files ended without a refusal, and without the test files there was none. In the final run of rc7 (T4, 22.04): `--ssh-fallback-test` refused to start with a `Match User` block in a file included from `sshd_config.d/*.conf`.
* **Found by:** rc7 review (of the certification fixes); **commit:** see `git log --grep B118`; **fixed in:** v78-r2604.0-rc7

### B119

**The fallback SSH server does not start for the release upgrade that begins right after the reboot into 24.04** (medium, Tools)

* **Symptom:** On a box upgraded from 22.04, the second release upgrade (24.04 to 26.04) starts by itself after the reboot, and the tool says "WARNING: sshd -T fails; no fallback SSH server." New SSH logins then fail while that release upgrade replaces OpenSSH, as before rc7. The first release upgrade, and a release upgrade started from an SSH session, are not affected.
* **Cause:** `sshd -T` (and the fallback itself) needs `/run/sshd`, the privilege separation directory, and fails with "Missing privilege separation directory: /run/sshd" without it. On 24.04 sshd is socket activated: ssh.service, whose RuntimeDirectory is `/run/sshd`, starts only with the first SSH connection after the boot. The tool resumes at boot, before anyone has logged in. The test runs before had not shown it, because the outage monitor of the lab logged in every few seconds.
* **Fix:** Before `sshd -T` (for the fallback and for the listen addresses of the banner check) the tool creates `/run/sshd` (mode 0755) when it is missing, as its watcher already did during the release upgrade: `/run` is root's own, `mkdir` follows no symbolic link, and a symbolic link there is left alone.
* **Affects:** the development of rc7 only (never in a tag). Origin: Fork. Every in-place upgrade from 22.04 (the second release upgrade always starts after a reboot), unless someone logs in over SSH between the boot and its start.
* **Evidence:** The review run of the fixes, T4: the warning above at the start of the release upgrade to 26.04. On the 24.04 test box right after a boot, through the guest agent (no SSH login): `/run/sshd` missing, `sshd -T` exit code 255 with that message, ssh.socket active and ssh.service inactive; with the fix, `--ssh-fallback-test` there started the fallback on port 1022 and created `/run/sshd`. In the final run of rc7 (T4) the fallback started at the boot into 24.04 and ran OpenSSH 9.6p1 while port 22 was down.
* **Found by:** rc7 review run (T4 after the review fixes); **commit:** see `git log --grep B119`; **fixed in:** v78-r2604.0-rc7

### B120

**Setup restarts Dovecot before it rewrites the passdb, and logins can fail as wrong passwords for two seconds** (medium, Dovecot)

* **Symptom:** During a setup run (an update, too) Dovecot logs "auth: Fatal: No passdbs specified in configuration file. PLAIN mechanism needs one" and "master: Error: service(auth): command startup failed, throttling for 2.000 secs". Logins in the next two seconds fail like a wrong password (IMAP `NO`), not like a server that is down. Nextcloud's IMAP login (user_external) counts each such failure as a failed login (see B121); phones and mail programs may ask for the password.
* **Cause:** setup/mail-dovecot.sh restarted Dovecot, and setup/mail-users.sh then rewrote `auth-sql.conf.ext` (the passdb and userdb) with `cat >`: the file is truncated and then written. Dovecot 2.4 starts its config process on demand, at the first login after a (re)start, and that process parses the configuration files at that moment; one that started while the file was empty gave Dovecot no passdb. setup/mail-users.sh restarted Dovecot again two seconds later, which ended it.
* **Fix:** Dovecot is loaded once per run, in setup/mail-users.sh after its whole configuration (with the passdb) is written, before the `doveadm` commands that need it, and not at all when the configuration did not change (`load_dovecot` in setup/functions.sh, see B122). Setup writes Dovecot's files atomically and only when they change: a new file in the same directory, renamed over the old one, through the new `tools/write_conf.py`, which opens the path one directory at a time and follows a symbolic link only in a directory of root's own; `tools/editconf.py` writes the same way, and `10-mail.conf` is put together in a directory of root's own before it is written once. The log audit's rule that accepted the two messages during setup is removed.
* **Affects:** v78 yes (from reading the code: the same order of restarts and writes; not reproduced on 22.04), PR #2603 yes, the fork up to rc7. Origin: Upstream. Seen only now and then: the config process has to start in the moment of the write.
* **Evidence:** The update test T5b of rc7: a probe every 2 s got one failed IMAP login between setup's two Dovecot restarts, with the messages above. On the fresh-install test box, with a loop that rewrote `auth-sql.conf.ext` the way setup did: 6 of 10 config processes started by a login (after killing the config and auth processes) had no passdb; with writes through a renamed file, 0 of 14. On that box, setup runs with clients running (see `tests/fork/client-load.py`): without the fix 3 Dovecot restarts per run, failed CalDAV logins (HTTP 401) of the test users in the restart windows; with the fix no restart, one reload in the first run (none in the next), no failed login. The production box's own log of the update (B121) was not checked for the message.
* **Found by:** production update (rc6 to rc7, its analysis; the message was an open finding of the rc7 certification); **commit:** see `git log --grep B120`; **fixed in:** the release after v78-r2604.0-rc7

### B121

**Nextcloud throttles 127.0.0.1 after a setup run, and ActiveSync stops syncing calendars and contacts for every user** (high, Nextcloud)

* **Symptom:** After an update, phones stop syncing calendars (and some contacts) over ActiveSync, for every user at once, for about 30 minutes; after that every request waits 25 seconds. `nextcloud.log` shows `OCA\DAV\Connector\Sabre\Exception\TooManyRequests` for the CalDAV and CardDAV requests of all users, and `z-push-error.log` "BackendCalDAV->Logon(): User '...' is not authenticated on CalDAV 'https://127.0.0.1:443/caldav/...'" and `AuthenticationRequiredException`. `occ security:bruteforce:attempts 127.0.0.1` shows attempts and a delay of 25000 ms, bypass-listed false.
* **Cause:** Z-Push syncs calendars and contacts from Nextcloud over `https://127.0.0.1` (the `/caldav` and `/carddav` proxy of nginx) with each user's password. Nextcloud checks these logins against Dovecot over IMAP (user_external). While setup restarted Dovecot (B120, B122), they failed ("Could not connect to imap server via curl", "IMAP server returned an error"), and Nextcloud's brute-force protection counted them as failed logins of 127.0.0.1, of all users together. After more than 10 attempts it answers every login from that address with `TooManyRequests` for 30 minutes; a successful login would reset only that user's attempts, but none got through.
* **Fix:** setup/nextcloud.sh puts 127.0.0.1/32 on Nextcloud's brute-force bypass list (app config `bruteForce`, keys `whitelist_N`, which Nextcloud's core reads, as Administration > Security does), on a fresh install, a migration and an update, unless Nextcloud already bypasses that address (`occ security:bruteforce:attempts`, e.g. a range of an administrator); entries of an administrator are kept. Before it adds the address, it resets its attempts, so a box that is throttled now syncs again after the update. ::1 is not added: no service of the box calls Nextcloud over it. The proxy of `/caldav`, `/carddav` and `/webdav` (conf/nginx-primaryonly.conf), which connects to Nextcloud from 127.0.0.1 and is open to the Internet, now passes the client's address in `X-Forwarded-For` (replacing what the client sent) and drops the forwarded host and protocol headers, and Nextcloud takes that address from 127.0.0.1 only (`trusted_proxies` gets 127.0.0.1, `forwarded_for_headers` is `X-Forwarded-For` only): clients on the Internet keep their own address there, the throttle and the miab-owncloud jail (which never saw their address on these paths before), and Z-Push stays 127.0.0.1. Z-Push checks each password against Dovecot before it calls Nextcloud, so the throttle of 127.0.0.1 never slowed down a password guesser there. The smoke test checks the bypass list, that a failed login through `/webdav` from another address is counted for that address, and an ActiveSync sync of a calendar and the contacts (group `activesync`). The first version of this fix (never released) listed 127.0.0.1 and ::1 without the proxy change: every client of `/caldav`, `/carddav` and `/webdav` on the Internet then appeared as 127.0.0.1 and skipped the throttle (found in its review).
* **Affects:** v78 yes (the same Nextcloud brute-force protection, user_external and Z-Push backends), PR #2603 yes, the fork up to rc7. Origin: Upstream. A box with few ActiveSync users may stay below the 10 attempts.
* **Evidence:** A production box at the update from rc6 to rc7: 12 failed logins from 127.0.0.1 during one Dovecot restart, then 136 `TooManyRequests` in about 30 minutes, attempts 12 and a delay of 25000 ms until `occ security:bruteforce:reset 127.0.0.1`. On the fresh-install test box: during a setup run without the fix, the CalDAV requests of the test users from 127.0.0.1 failed with HTTP 401 in Dovecot's restart windows ("Login failed ... (Remote IP: '127.0.0.1')", also from Z-Push's CardDAV backend); 11 failed logins of other users from 127.0.0.1 gave attempts 11 and a delay of 25000 ms, and then a valid login of a test user got HTTP 429 and its ActiveSync Provision HTTP 401. The next setup run with the fix reset the attempts and listed both addresses (bypass-listed true, attempts 0); ActiveSync and CalDAV worked again at once, and a setup run with clients running had no failed login. After the review of the first fix: on the fresh-install test box, a failed login through `/webdav` from the box's public address was logged and counted by Nextcloud for that address (smoke check `nextcloud-forwarded-for`); a setup run from a throttled state (no bypass entry, attempts 11, delay 25000 ms) ended with 127.0.0.1 bypass-listed and 0 attempts; a run with the administrator entries 10.0.0.0/8 and 127.0.0.0/8 added nothing and kept them. On the copy of the production box, three setup runs (rc6 to the fix and two reruns) with the client load of `tests/fork/client-load.py` on the box and from another host (4 Ping and 2 Sync devices per user there): no throttled result, no brute-force attempts for the other host's address, no fail2ban `Found` for it.
* **Found by:** production update (rc6 to rc7); **commit:** see `git log --grep B121`; **fixed in:** the release after v78-r2604.0-rc7

### B122

**Setup restarts Dovecot, Postfix, PHP-FPM and fail2ban several times per run; each restart cuts the clients, and fail2ban lifts all bans for a moment** (medium, Setup)

* **Symptom:** Each setup run, also an update without changes, restarted Dovecot 3 times, Postfix 3, PHP-FPM 4 and fail2ban 2 times. Each restart refused connections for a second or two: IMAP and SMTP logins failed, ActiveSync and Nextcloud requests got HTTP 502, Nextcloud counted the failed IMAP logins (B121). fail2ban unbanned every address when it stopped and banned them again from its database about two seconds later.
* **Cause:** Each script that changes a service's configuration restarted it (`restart_service`), and setup/start.sh restarted fail2ban once more at the end.
* **Fix:** New functions in setup/functions.sh load a configuration with a reload where the service supports it (the listening sockets stay) and restart a service only when it does not run, or runs the program of an older package (the service started before its package was last installed or upgraded), or its main process still maps a program or library file that has been replaced since (`(deleted)` in `/proc/PID/maps`, e.g. after an upgrade of libssl or python3; the restarts of earlier versions picked these up on every run). Dovecot: one `doveadm reload` per run, in setup/mail-users.sh, and none when its configuration is the one it loaded last (a checksum of the settings of `doveconf -n` and of the certificate files, in `/var/lib/mailinabox`, recorded only once the master has loaded it: when it has not within 10 s of the reload, setup restarts Dovecot); a reload still ends Dovecot's open IMAP sessions, whose clients log in again. Postfix: `postfix reload` (a restart only when `inet_interfaces` or `inet_protocols` change). PHP-FPM: one restart after setup/zpush.sh instead of one per script (a reload ends the running requests just the same with the package's `process_control_timeout`). fail2ban: `fail2ban-client reload`, which keeps the bans (`reload --restart` when the `bantime.*` options of the adaptive configuration change, see `management/fail2ban_admin.py --setup`).
* **Affects:** v78 yes, PR #2603 yes, the fork up to rc7. Origin: Upstream.
* **Evidence:** A production box at the update from rc6 to rc7: the restarts above, fail2ban without bans for about 2 s. On the fresh-install test box, a setup run with clients running (`tests/fork/client-load.py`: ActiveSync, CalDAV/CardDAV, IMAP logins every second and IDLE, SMTP AUTH, Roundcube) without the fix: Dovecot 3, Postfix 3, PHP-FPM 4 and fail2ban 2 restarts, failed CalDAV logins, refused IMAP connections, a temporary SMTP AUTH failure (454) and HTTP 502 for ActiveSync. With the fix: Postfix 3 reloads, PHP-FPM 1 restart (2 ActiveSync requests got 502), fail2ban 1 reload with a test ban kept, Dovecot 1 reload in the first run (its 2 IDLE connections reconnected) and none in the next; no failed login, no refused connection. After the review: with the package lists of dovecot-core and postfix touched, the next setup run restarted both once and reloaded them afterwards; with a changed `bantime_max` fail2ban ran `reload --restart` (its marker ban was lifted for 0.7 s and restored from its database, the process stayed); otherwise a plain reload that kept the ban. On the copy of the production box under the client load above: Dovecot reloaded once in the first run (its IDLE connections logged in again, its master process stayed) and not in the reruns, PHP-FPM restarted once per run (one second of HTTP 502 for the ActiveSync and DAV requests in progress), no failed login of a client.
* **Found by:** production update (rc6 to rc7); **commit:** see `git log --grep B122`; **fixed in:** the release after v78-r2604.0-rc7

### B123

**/etc/dovecot belongs to the account mail, which can change the configuration that Dovecot's root processes read and the files that setup writes there as root** (medium, Dovecot)

* **Symptom:** `/etc/dovecot` and everything in it belong to `mail:dovecot` (the group may read, others nothing). The account `mail`, which all IMAP, POP3, LMTP and ManageSieve processes of the users run as, can change Dovecot's configuration, which the master and config processes read as root, and can replace the files and directories (also with symbolic links) in which setup writes as root by path (`sed -i`, `tools/editconf.py`, `cp`, `chown -R`).
* **Cause:** setup/mail-dovecot.sh ran `chown -R mail:dovecot /etc/dovecot` and `chmod -R o-rwx /etc/dovecot` at its end (upstream), so that the mail processes can read the global sieve script and its compiled copy.
* **Fix:** `/etc/dovecot` belongs to `root:mail`: directories 0750 and files 0640 at most (group write and every permission of others taken away), so the mail processes still read everything they read before (the global sieve script, an administrator's own files there such as a Lua script) and write nothing. Dovecot's other processes get their settings from its config process (root). setup/mail-dovecot.sh does this at its start, before it writes anything there, and again at its end, with `tools/write_conf.py --own-tree`, which changes the tree top down through open descriptors and follows no symbolic link (safe while the old owner could still change it); a file with several hard links is left alone with a warning. The global sieve script is written atomically. A new pigeonhole whose binary format changes cannot save its recompiled copy of that script until setup compiles it again (a warning at delivery; the script still runs).
* **Affects:** v78 yes, PR #2603 yes, the fork up to rc7. Origin: Upstream. Only matters to an attacker who already runs code as `mail` (e.g. through a bug in an IMAP process): from there to root.
* **Evidence:** From reading the code (setup/mail-dovecot.sh) and the file modes on a box of the fork. After the fix, on a fresh install and on the copy of the production box (updated from rc6, with an administrator's Lua push script in `/etc/dovecot`): every file and directory there `root:mail` without group write and without permissions for others, the smoke test (with delivery through the global sieve script, spam and Sieve filters, ActiveSync and IMAP) passed, and the log audit showed no permission error of a Dovecot process.
* **Found by:** review of the fixes of B120-B122; **commit:** see `git log --grep B123`; **fixed in:** the release after v78-r2604.0-rc7

### B124

**Setup replaces Nextcloud's config.php with a file only root can read, for a moment, and Nextcloud fails the requests in that moment** (medium, Nextcloud)

* **Symptom:** During a setup run (every update), a Nextcloud request fails with "fopen(/usr/local/lib/owncloud/config/config.php): Failed to open stream: Permission denied" (nginx's error log). When it is Z-Push's login to CardDAV or CalDAV, Z-Push answers the phone's request with HTTP 401 ("BackendCardDAV->Logon(): User '...' failed to authenticate", `AuthenticationRequiredException`), which a phone may show as a password prompt.
* **Cause:** setup/nextcloud.sh wrote the new `config.php` as root to a file of `mktemp` (mode 0600, root) in /tmp, moved it over `config.php`, and gave it to www-data only afterwards (`chown`); a request between the two found the file unreadable. Root also wrote it by path into `$STORAGE_ROOT/owncloud`, which belongs to www-data.
* **Fix:** The PHP that merges the settings runs as www-data and replaces `config.php` atomically (a new file in the same directory, renamed over it); it stops setup if www-data cannot read the old file. The two `sed -i` that switch `config_is_read_only` run as www-data as well.
* **Affects:** v78 yes (the same code), PR #2603 yes, the fork up to rc7. Origin: Upstream. Needs a request in the moment between the two commands; with a few phones per user seen once per setup run or less.
* **Evidence:** The update test T5b with client load after the review of B120-B123 (copy of a production box, rc6 to the fixed branch, second run): one FolderSync of an ActiveSync device from another host got HTTP 401 at the moment setup rewrote `config.php`, with the messages above; no other failed login in the run.
* **Found by:** update test (with client load, after the review of B120-B123); **commit:** see `git log --grep B124`; **fixed in:** the release after v78-r2604.0-rc7

### B125

**The backup page and the backups wait up to two minutes when the rsync target does not answer a connection request** (low, backup)

* **Symptom:** The backup page of the control panel (`/admin#system_backup`) sometimes loads for a long time, and now and then shows only "Something went wrong, sorry." after exactly 60 s (nginx answers 504). On a production box with a Hetzner Storage Box as rsync target the page usually needed 6-11 s; once ssh waited 11-13 s in `SYN-SENT` for the Storage Box to answer over IPv6, and twice the request ran into nginx's 60 s limit. Right after, connections to both addresses of the Storage Box took 0.01-0.2 s: the target (or the way to it) drops a connection request now and then.
* **Cause:** management/backup.py runs ssh (through duplicity and rsync, for the status page twice per call: duplicity's `collection-status` and the list of the target's files) without `ConnectTimeout`. ssh then waits for the kernel's TCP retries (6 by default, after 1, 3, 7, 15, 31 and 63 s, about two minutes in all) before it gives up or tries the target's next address, so one dropped connection request costs 1 s, 3 s, 7 s or more.
* **Fix:** Every ssh connection to the rsync target gets `-oConnectTimeout=10 -oConnectionAttempts=2` (duplicity's `--ssh-options` and `--rsync-options`, and the list of the target's files): ssh gives an address 10 s for the TCP connection and the SSH banner together (OpenSSH counts both against `ConnectTimeout`), then tries the next one (IPv4 after IPv6), and makes two such attempts. A dropped connection request now costs at most 10 s per connection. A target that does not answer at all fails each ssh call after about 21 s (one address) or 41 s (IPv6 and IPv4) instead of about two minutes per address. duplicity retries its own failed calls (5 times, 30 s apart); the list of the target's files, which MIAB makes itself (status page, and `should_force_full` before each nightly backup, which ends the run when it fails), is now tried three times, 5 s apart, unless the target refused the key or the path. 5 s would have left too little time for the banner after a retried SYN, and a failed file list would have cost a night's backup. The status page itself still waits for the target; showing the status of the last backup at once is planned (CHANGELOG-fork.md, Planned).
* **Affects:** v78 yes, PR #2603 yes, the fork up to rc7. Origin: Upstream.
* **Evidence:** A trace of the processes of `mailinabox.service` on the production box (ssh in `SYN-SENT` for 11-13 s, kernel stack `__inet_stream_connect`) and the nginx log (two 504 after 60 s, each the first visit of the page after a backup). After the fix: ssh with the new options against an address that does not answer gives up after about 21 s (before: about 130 s); on the production box with the new options, the status page answered in 8 s and its ssh calls carry the options (process trace); the nightly backup with them is still to be checked.
* **Found by:** user report (backup page shows only an error); **commit:** see `git log --grep B125`; **fixed in:** the release after v78-r2604.0-rc7

### B128

**ActiveSync answers every contacts Sync with HTTP 500 for a user with a card whose name has no .vcf, such as Nextcloud's example contact left from rc3 to rc6** (high, Z-Push)

* **Symptom:** For such a user, every ActiveSync Sync that includes the contacts folder answers HTTP 500, and with it the other folders of the same request; the phone shows no contacts and may stop syncing the calendars of that request too. `z-push-error.log`: "Attempt to read property "vcard" on null" and "Fatal error: /usr/local/lib/z-push/backend/carddav/carddav.php:484 - Uncaught Error: Call to a member function __toString() on null", as in B99.
* **Cause:** Z-Push 2.7.7 makes a card's ActiveSync id from its name on the server without `.vcf`, and its CardDAV client (`include/z_carddav.php`, `get_xml_vcard()`) asks for every card under id + `.vcf`. For a card whose name has no extension that name does not exist. Nextcloud (Sabre) leaves a name it does not know out of an `addressbook-multiget` answer instead of answering 404 for it, so the answer is an empty multistatus; Z-Push's own retry without the extension follows only a 404 and never runs. `GetMessage()` then dereferences the missing card (`StatMessage()` the same way), and the PHP error ends the whole request. Such cards are Nextcloud 34's example contact `default` (B99), which the dav app wrote at the first Nextcloud login of each user on rc3 to rc6 (in the web, over DAV, or through the CardDAV login of Roundcube or Z-Push); B99 stops new ones, those written before stay. And the cards of other clients that name them without `.vcf`, in the user's own address books or in one shared with them: Z-Push merges all of them into one contacts folder. Nextcloud's system address book (cards `Database:<user>.vcf`, `OCA\UserExternal\IMAP:<user>.vcf`) is not the cause: those names have the extension, and the backslash, escaped or not, reaches the card.
* **Fix:** setup/zpush.sh changes Z-Push's code on every run, also on a box that does not download Z-Push again: the new conf/zpush/z-push.patches, applied by the new tools/patch_source.py. It replaces exact pieces of text, counts a piece that is already changed as done, and stops setup when a piece is not found once (another Z-Push version); every file is checked before the first one is written, then replaced atomically like tools/write_conf.py does, in directories of root's own and without following a link that another account could set. The changes: `get_xml_vcard()` asks once more for the name without `.vcf` when the answer for the name with it holds no card; `GetMessage()` and `StatMessage()` log a card that the server does not return and skip it instead of failing, so one card can no longer stop the Sync; a change or deletion of a card from the phone goes to the card's existing name (with `.vcf` or without, found with one GET) and keeps its UID, so that editing such a card on the phone changes it instead of adding a second card `<name>.vcf` (which the unchanged code would have done). Setup changes no cards: the example contact now syncs like any other one.
* **Affects:** v78 yes for cards of other clients without `.vcf` (its Nextcloud 27 writes no example contact), PR #2603 yes (Nextcloud 34), the fork up to rc7 (with B99: users whose first Nextcloud login was on rc3 to rc6, and every user with such a card). Origin: Upstream (Z-Push 2.7.7); PR #2603 brought the example contact. A device that got HTTP 500 needs no new setup: its Sync state was not saved at the error, and its next Sync continues.
* **Evidence:** A copy of a production box at rc6 (the update test's disk), on a test box: a new test user, whose first login had written the example contact, got HTTP 500 for the contacts Sync with the errors above; after the card was deleted, the same user synced 2 contacts (from the system address book), and other users synced. After the update to rc7 (B99) a user created before the update still got HTTP 500, one created after did not. A card put as `contacts/zp-noext-1` gave HTTP 500 for that user, and its deletion ended it. A multiget for `contacts/default.vcf` answered an empty 207 (131 bytes), one for `contacts/default` the card; multigets of the system address book's cards (with `%5c`, `%5C` or a backslash) answered the card. With the change applied: a device that had got HTTP 500 continued with its saved sync key and received 3 contacts with the example contact; a Change of it from the device updated `default` in place (the same UID, no second card), and a Delete from the device removed it; no new line in `z-push-error.log`. Setup of the fixed branch on that box (an update, with Z-Push 2.7.7 as rc6 had installed it): it changed both files, and a second setup run left them alone; a device that had got HTTP 500 just before the update continued with its saved sync key and received the card without `.vcf`; existing devices and users synced on, new devices of users from before the update and a user created after it synced, also with a card put without `.vcf`; no new line in `z-push-error.log`. The smoke test's `zpush-sync` (with its card without `.vcf`) failed with HTTP 500 before the update and passed after it (76 of 76 checks). The checksum mark of the review: after the update from rc6 (one new download of Z-Push, as its directory had no mark) `/usr/local/lib/z-push/version` read `2.7.7+patches-<checksum>`; with one block of the patch file edited for a test, tools/patch_source.py on the changed tree stopped with exit 1 (neither the block's old nor its new text found), the trap the mark avoids, and setup/zpush.sh installed a fresh copy and applied the edited block (exit 0); with the file restored, again a fresh copy with the original changes, and the next runs (one of them a full setup) left Z-Push alone.
* **Found by:** update test (with client load after the review of B120-B123: every contacts Sync of the new load test users answered HTTP 500) and the ActiveSync analysis (the cause); **commit:** see `git log --grep B128`; **fixed in:** the release after v78-r2604.0-rc7

### B129

**nginx ends an ActiveSync Ping with a heartbeat of more than 630 s with HTTP 504, while Z-Push still waits** (medium, Z-Push)

* **Symptom:** A phone whose Ping (the push long poll) asks for a heartbeat of more than 630 s gets HTTP 504 after 10.5 minutes for every Ping, instead of an answer; nginx's error log: "upstream timed out (110: Connection timed out) while reading response header from upstream" for `Cmd=Ping`. On a production box after the update to rc7: 68 such 504 in a day, all Pings of one iPhone, spread over the whole day (about three an hour on average). The PHP process goes on waiting after the 504 and holds an FPM worker until the phone's next request or the end of the heartbeat; a change it finds in that time is answered into a closed connection, and the phone learns of it only with its next Ping.
* **Cause:** Z-Push waits as long as the phone asks (`SyncCollections::CheckForChanges()`), with nothing to bound it: `PING_HIGHER_BOUND_LIFETIME` is `false` in its `config.php`, and PHP's `max_execution_time` (600 s, setup/nextcloud.sh) does not apply, as Z-Push sets its own time limit (`SCRIPT_TIMEOUT`, 0). nginx gives up after `fastcgi_read_timeout 630` in the `/Microsoft-Server-ActiveSync` location (conf/nginx-alldomains.conf). iOS asks for long heartbeats on stable networks, and ActiveSync allows up to 3540 s (59 minutes). A Sync with a wait (`Wait`, `HeartbeatInterval`) is checked by Z-Push only against 60-3540 s, not against the Ping bound, so it needs the longer nginx timeout too.
* **Fix:** nginx waits up to 3660 s for `/Microsoft-Server-ActiveSync` (the value of Z-Push's own nginx example: the protocol's maximum and two minutes), and setup/zpush.sh sets `PING_HIGHER_BOUND_LIFETIME` to 3540, so that a Ping that asks for more gets status 5 with that bound at once and the phone pings with it, instead of a 504. Phones keep their long heartbeat (fewer connections than with a 504 every 10.5 minutes). An FPM worker per pushing device is held as long as before; PHP already ignored the 630 s.
* **Affects:** v78 yes (the same values: `fastcgi_read_timeout 630`, no Ping bound), PR #2603 yes, the fork up to rc7. Origin: Upstream.
* **Evidence:** On a copy of a production box (the box's defaults): a Ping with a heartbeat of 1800 s ended with "HTTP 504 after 630.1 s" and the error log line above, the same message as on the production box; Z-Push's log of the device showed the Ping still waiting ("lifetime 1800 seconds") after the 504, until the device's next request ended it after 668 s. With the ActiveSync timeout lowered to 60 s for a test: a Ping of 120 s got 504 after 60 s; with a Ping bound of 45 s, a Ping of 120 s got status 5 with heartbeat 45 at once, and a Ping of 45 s status 1 after 46 s; with a timeout of 200 s and no bound, a Ping of 120 s status 1 after 121 s. After the setup of the fixed branch: a Ping of 3600 s got status 5 with the bound 3540 at once, a Ping of 900 s answered HTTP 200 with status 1 after 902 s, and nginx logged no timeout; the smoke test's `zpush-ping` got HTTP 504 after 635 s before the update and passed after it. With the check's 90 s limit of the review: on the box before the update it failed after 90 s ("no status 5 within 90 s"; the whole group `activesync` 124 s); with the bound removed by hand after the update, it ended the long Ping with one of 60 s (HTTP 200 after 61 s) and left no device in Z-Push (181 s for the group); with the bound it passed in 0.3 s.
* **Found by:** production update (nginx's log of the box after the update to rc7) and the ActiveSync analysis (the cause); **commit:** see `git log --grep B129`; **fixed in:** the release after v78-r2604.0-rc7

### B130

**The /caldav, /carddav and /webdav proxy passes the decoded path: a space gives 400, an escaped ? starts a query string (a DELETE can hit the whole address book), query strings are lost** (medium, nginx)

* **Symptom:** Through `https://<box>/carddav/...`, `/caldav/...` or `/webdav/...` (the short paths that MIAB proxies to Nextcloud's `remote.php`): a resource whose name has a space (`%20`) gets HTTP 400; a name with an escaped `?` (`%3F`) reaches another resource, as Nextcloud gets the `?` unescaped and takes the rest for a query string, so that a DELETE of a card named `?x.vcf` deleted the whole address book that holds it (seen on a test box) and a DELETE through `/webdav` could in the same way hit a folder; and a request's query string (such as `?export` of an address book) is dropped (HTTP 501). The URLs below `/cloud/remote.php/` and the `.well-known` redirects are not affected, nor is Z-Push (it uses the proxy only for its first requests and then the hrefs that Nextcloud sends).
* **Cause:** conf/nginx-primaryonly.conf proxied them with `location ~ ^/((caldav|carddav|webdav).*)$ { proxy_pass https://127.0.0.1/cloud/remote.php/$1; }`. `$1` is captured from nginx's normalized, decoded path, and a `proxy_pass` with a variable sends that text as it is: not escaped again and without the query string.
* **Fix:** Three prefix locations, `/caldav`, `/carddav` and `/webdav`, each with a `proxy_pass` to the same path below `/cloud/remote.php` and no variable: nginx then replaces the prefix in the normalized path, escapes the result again and passes the query string. They match the same paths as before (anything that begins with them) and keep the headers of B121. They are `^~` locations, so nginx checks no regex location for these paths, as before: the old regex location came before every regex that can match them except Roundcube's `~ /mail/config/`, as nginx-primaryonly.conf is placed before the dotfile block at the end of nginx-alldomains.conf (`location ~ /\.(ht|svn|git|hg|bzr) { deny all; }`, which upstream keeps off Nextcloud's user files, #414) and before a custom include. Plain prefix locations would lose to that block: a file `.gitignore` or `.svn` through `/webdav` would get 403 (seen on a test box with a first version of this fix). A path with `/mail/config/` in it still gets 403, as before: Roundcube's unanchored `~ /mail/config/` comes before Nextcloud's location too and answers the request that the proxy makes to `/cloud/remote.php`. `$request_uri` was not used: it is not normalized and would let `../` reach other paths of Nextcloud from 127.0.0.1.
* **Affects:** v78 yes (the same location), PR #2603 yes, the fork up to rc7. Origin: Upstream. Only DAV clients configured with the short paths and resource names with a space, `?`, `#` or `%`.
* **Evidence:** On a test box (a copy of a production box), through `/carddav`: a GET of `contacts/zp%20space.vcf` went to Nextcloud as `.../contacts/zp space.vcf` and got 400; a GET of `zp%3Fprobe.vcf` as `.../contacts/zp?probe.vcf` (404); a DELETE of `contacts/%3Fzp.vcf` as `DELETE .../contacts/?zp.vcf` and got 204: the test user's whole address book `contacts` was gone, not the card; a GET of `contacts/?export` lost the `?export` (501). With prefix locations: 200 for the first two, `?export` 200, and the DELETE removed only the card. After the setup of the fixed branch: the same requests (nginx passed `%20` and `%3F` on to Nextcloud), and the smoke test's `nextcloud-dav-proxy` failed with HTTP 400 before the update and passed after it. The `^~` locations of the review, on another copy of that box: files `.htmiab-lab-1` and `.gitmiab-lab-1`, put through `/cloud/remote.php/dav`, answered 200 through `/webdav` with the old regex location (before the update) and with `^~` (after it), and 403 ("access forbidden by rule", the dotfile block) with the plain prefix locations of the first version of this fix (the box's nginx configuration edited for one minute); `/webdav/sub/.svn` got Nextcloud's 404 with the old and the new locations and 403 with plain prefix locations; `/webdav/x/mail/config/y` got 403 with all three. The smoke test with the dotfile reads in `nextcloud-dav-proxy`: 76 of 76 checks after each of two setup runs, log audit 0 unknown.
* **Found by:** ActiveSync analysis (the requests of Z-Push through the proxy); **commit:** see `git log --grep B130`; **fixed in:** the release after v78-r2604.0-rc7

## Not counted above

* Fixes to `tools/migrate-to-2604.sh` and `tests/fork/` made before they were
  first released (false alarms in the post-migration checks, reboot safety,
  rollback order). These tools are new in the fork, so these fixes are listed
  in the changelog, not here.
* Version and checksum updates (see the version table in CHANGELOG-fork.md).
  Several of them replace outdated, vulnerable or unmaintained releases, but
  they fix no bug of their own.

## Known limitations (not fixed)

* **Full-text search: an error once when a folder is indexed for the first
  time.** dovecot-fts-xapian 1.9.3 keeps a small SQLite database per folder
  and opens it without a busy timeout. When two processes create it at the
  same moment (the indexer after a delivery and the IMAP process of the
  same user), the second one logs `FTS Xapian: Can not execute (CREATE TABLE
  IF NOT EXISTS dict ...) : database is locked` (or `disk I/O error`). The
  first one creates it, and search works. Seen in the rc6 test runs; to be
  reported to the plugin. The Xapian index itself behaves the same way
  (seen after rc7, when the smoke test's vacation mail and its IMAP session
  indexed a new inbox at once): the second writer logs `Can't lock the DB :
  DatabaseLockError` for every try during a second or two, a reader `Can not
  open RO index` and `GetLastUID: Can not open db RO`, and then the folder is
  indexed.

* **Nextcloud stays on 34.** The `user_external` app (IMAP login) has no release
  for Nextcloud 35 yet.
* **sury dependency.** Ubuntu 26.04 has no `php8.5-imap` (needed by Z-Push) and
  no PHP 8.2 (needed temporarily for the Nextcloud 26 to 31 upgrade steps).
  Both come from packages.sury.org, restricted by an apt pin.
* **Not covered by the test environment:** Let's Encrypt issuance, outbound
  port 25 to the internet, blacklist checks, reverse DNS.
* **Migration sources tested:** MIAB v74 on Ubuntu 22.04 with Nextcloud
  26.0.13. A 24.04 in-place upgrade with PHP 8.0 was tested on a copy of a
  production box (rc3) and run on a production box (rc3, which found
  B57-B60).
* **Upstream v74 with current ondrej/sury PHP 8.0:** the php8.0-fpm unit's
  `ProtectSystem=full` makes Nextcloud 26 answer HTTP 503 ("Cannot write into
  apps directory") unless `appstoreenabled` is false. Upstream later fixed this
  and the fork has the fix. It matters for old boxes before they migrate.
