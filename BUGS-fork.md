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
  * *Fork*: introduced and fixed within this fork. B07 never shipped in a tag; B11 shipped in rc1, B57 and B67 in rc3, B68 in rc4.
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
  * *in-place test*: T3, the in-place upgrade of a copy of a production box.
  * *production upgrade*: the in-place upgrade of a production box with rc3.
  * *update test*: the update of a copy of that production box from rc3 to rc4, and the fresh rc4 test box.

## Summary

69 bugs: 1 critical, 13 high, 32 medium, 23 low. B51-B56 were found by the in-place upgrade test for rc3,
B57-B60 by the in-place upgrade of a production box with rc3, B61 while adding the adaptive fail2ban, B62 in the review of rc4, B63-B65 in the test runs of rc4, B66-B69 in the update test of rc4.

| Origin | Count |
|---|---|
| Upstream | 18 |
| PR #2603 | 27 |
| PR #2603 (latent) | 1 |
| 26.04 change | 17 |
| Fork | 6 |

19 of these bugs also affect v78 on Ubuntu 22.04, fully or partly (B13, B17, B19, B28, B30, B31, B32, B33, B34, B35, B37, B45, B49, B56, B58, B60, B61, B62, B63). They are candidates for
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
* **Cause:** The fix of B60 (rc4) edits `/etc/hosts` only. On machines whose cloud-init has `manage_etc_hosts: true` (in the image's `/etc/cloud/cloud.cfg` or, as with Proxmox, in the machine's user data), cloud-init's module update_etc_hosts writes `/etc/hosts` on every boot from `/etc/cloud/templates/hosts.debian.tmpl`, whose line is `127.0.1.1 {{fqdn}} {{hostname}}` with cloud-init's names of the machine, not PRIMARY_HOSTNAME. A drop-in in `/etc/cloud/cloud.cfg.d` cannot turn that off, because the user data overrides it.
* **Fix:** When setup has commented out such a line and cloud-init manages `/etc/hosts` (`manage_etc_hosts` true or template in `cloud-init query combined_cloud_config`, or cloud-init's header in `/etc/hosts`), setup/system.sh changes the template's 127.0.1.1 line to `127.0.1.1 PRIMARY_HOSTNAME <first label>`, as the header that cloud-init writes into `/etc/hosts` suggests, and writes the same line into `/etc/hosts` instead of the commented-out one, so the file stays the same after the next boot. A template that already gives the box's name is left alone, and so is a box where cloud-init's name of the machine is PRIMARY_HOSTNAME. The template is a configuration file of the package cloud-init-base: when an update changes it, dpkg asks, and the local version should be kept. With `manage_etc_hosts: localhost` cloud-init does not use the template; setup then says that the setting can only be changed in the user data.
* **Affects:** v78 no (it does not touch /etc/hosts), PR #2603 no. Origin: Fork (B60's fix in rc4).
* **Evidence:** Fresh rc4 test box (Proxmox cloud-init, `manage_etc_hosts: true` and `fqdn` in the user data; a copy of a production box has the same template and setting): the template has `127.0.1.1 {{fqdn}} {{hostname}}`; re-running the module (`cloud-init single --name update_etc_hosts --frequency always`, as at boot) writes `127.0.1.1 <cloud-init fqdn> <hostname>` back. With the fix: the template and `/etc/hosts` have `127.0.1.1 PRIMARY_HOSTNAME <first label>`, the module writes the same line, and a second setup run changes nothing.
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
* **Cause:** Since Ubuntu 24.04 sshd is socket-activated: `ssh.socket` is enabled and starts `ssh.service`, which is disabled. The check of B67 compares the enabled units of `meta/unit-files.txt` (before the upgrade) with the disabled units now and left out only spamd. It did not look at how a disabled unit is started. Enabling ssh.service as advised would make sshd bind port 22 itself, next to the socket.
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

## Not counted above

* Fixes to `tools/migrate-to-2604.sh` and `tests/fork/` made before they were
  first released (false alarms in the post-migration checks, reboot safety,
  rollback order). These tools are new in the fork, so these fixes are listed
  in the changelog, not here.
* Version and checksum updates (see the version table in CHANGELOG-fork.md).
  Several of them replace outdated, vulnerable or unmaintained releases, but
  they fix no bug of their own.

## Known limitations (not fixed)

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
