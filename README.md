<h1 align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="branding/logo-wordmark-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="branding/logo-wordmark.svg">
    <img src="branding/logo-wordmark.svg" alt="Mail-in-a-box-26" width="372" height="80">
  </picture>
</h1>

<p align="center"><b>Mail-in-a-Box for Ubuntu 26.04 (unofficial fork)</b></p>

An unofficial fork of [Mail-in-a-Box](https://github.com/mail-in-a-box/mailinabox)
v78 that runs on **Ubuntu 26.04 LTS** with current versions of its software.

### Why this fork

Mail-in-a-Box v78, the latest upstream release, installs only on **Ubuntu
22.04 LTS**. Standard security maintenance for Ubuntu 22.04 ends in **May
2027** (after that only with Ubuntu Pro ESM, until May 2032). Several parts of
the v78 stack are no longer supported by their projects, or only get security
fixes:

* **PHP 8.0** from the third-party PPA `ppa:ondrej/php`. php.net ended
  security support for PHP 8.0 on 26 November 2023. v78 stays on 8.0 because
  of Nextcloud.
* **Nextcloud 27.1.11**. Nextcloud 27 reached end of life in June 2024.
* **Roundcube 1.6**, an LTS branch that only gets important security fixes;
  its active support ended on 10 May 2026.
* Since Dovecot 2.4 came out (January 2025), **Dovecot 2.3** only gets
  critical security fixes from its project, and the OpenSSL project no longer
  supports **OpenSSL 3.0**. Ubuntu 22.04 still backports security fixes to its
  packages (Dovecot 2.3.16, OpenSSL 3.0.2) until May 2027.

A port to Ubuntu 26.04 has been proposed upstream in
[PR #2603](https://github.com/mail-in-a-box/mailinabox/pull/2603) by
[@writeDavid](https://github.com/writeDavid) (open, not yet merged). This fork
builds on that port. Its goals:

* Run on **Ubuntu 26.04 LTS** (standard support until May 2031, ESM until May
  2036) with current versions of PHP, Nextcloud, Roundcube and Dovecot.
* Use Ubuntu's own packages where possible: PHP 8.5 comes from the Ubuntu
  archive. packages.sury.org is only a fallback, limited by an apt pin to what
  Ubuntu lacks (`php8.5-imap`, `php-common`, and PHP 8.2 for the Nextcloud
  upgrade chain).
* Keep Mail-in-a-Box's design: one setup command, almost no user-configurable
  setup options (the only new switches in `/etc/mailinabox.conf` are
  `FTS=off` and `NEXTCLOUD_SHARE_SCOPE=all`; the intrusion protection
  settings are in the control panel under System > Intrusion Protection).
* Provide a way from an existing box: a migration to a new 26.04 machine, or
  an in-place upgrade from Ubuntu 22.04 or 24.04 (see
  [Supported paths](#supported-paths)). Started outside tmux or screen, both
  tools run themselves in tmux, so a dropped SSH connection does not stop
  them halfway.
* Protect the logins better than v78 does: repeat offenders get longer
  fail2ban bans (up to a week), slow jails catch attacks that stay below
  the normal limits, own networks can be put on an allowlist, and the status
  checks report password spraying. Bans and settings are managed in the
  control panel (System > Intrusion Protection).
* Keep the mail domains of a box apart in Nextcloud: in the web interface
  and the system address book, users only find and share with the accounts
  of their own mail domain, members of the Nextcloud group `admin` with
  everyone (`NEXTCLOUD_SHARE_SCOPE=all` keeps upstream's behaviour). This is
  not a hard separation, e.g. a hand-made CalDAV request can still share
  with another domain; see the
  [limits](README-fork.md#nextcloud-sharing-within-the-mail-domain--teilen-innerhalb-der-maildomain).

### Main components

| Component | Mail-in-a-Box v78 (Ubuntu 22.04) | This fork (Ubuntu 26.04) |
|---|---|---|
| Ubuntu | 22.04 LTS (standard support until May 2027) | 26.04 LTS (standard support until May 2031) |
| PHP | 8.0 from `ppa:ondrej/php` (no security support since 26 Nov 2023) | 8.5 from the Ubuntu archive (security support until 31 Dec 2029) |
| Nextcloud ¹ | 27.1.11 (end of life June 2024) | 34.0.5 (supported until June 2027) ³ |
| Nextcloud apps contacts / calendar / user_external ¹ | 5.5.4 / 4.7.20 / 3.4.0 | 8.9.2 / 6.6.4 / 4.0.0 |
| Roundcube ¹ | 1.6.20 (LTS, security fixes only), CardDAV plugin 4.4.3 | 1.7.5 (current stable), CardDAV plugin 5.1.4 |
| Z-Push ¹ | 2.7.7 | 2.7.7 (unchanged) |
| Dovecot | 2.3.16 | 2.4.2 |
| Full-text search (Dovecot) | none | **new:** fts_xapian 1.9.3, on by default (`FTS=off` turns it off) |
| Postfix | 3.6.4 | 3.10.6 |
| fail2ban | 0.11.2 | 1.1.0, **new:** longer bans for repeat offenders, slow jails, allowlist (System > Intrusion Protection) |
| SpamAssassin (via spampd) | 3.4.6 (spampd 2.53), learning via dovecot-antispam | 4.0.2 (spampd 2.62), **new:** learning via IMAPSieve |
| nginx | 1.18.0 | 1.28.3 |
| OpenSSL | 3.0.2 | 3.5.5 (LTS, supported until April 2030) |
| Python (management daemon) | 3.10.12 | 3.14.4 |
| duplicity (backups) ² | 3.2.2 | 3.2.2 (unchanged) |

Versions as of `v78-r2604.0` (October 2026). For v78 the table shows the
version pinned in v78's setup scripts or the current Ubuntu 22.04 package.

¹ Pinned by the setup scripts (download with checksum). These change only with
a new release of Mail-in-a-Box or of this fork.

² From `ppa:duplicity-team/duplicity-release-git`, in v78 and in the fork.

³ Nextcloud 35 was released in September 2026; this fork stays on 34 until
the user_external app (Nextcloud logins with the mail password) supports 35.

Rows without a mark come from the Ubuntu archive (except PHP in v78, which
comes from `ppa:ondrej/php`) and are updated with Ubuntu's package updates;
the version shown is the upstream version Ubuntu ships. Most of them are in
Ubuntu's main component, which gets security updates during standard support;
`dovecot-fts-xapian`, `fail2ban` and `spampd` are in universe.

---

> **This is an unofficial, community-maintained fork of
> [Mail-in-a-Box](https://github.com/mail-in-a-box/mailinabox).** It is not
> affiliated with, maintained or endorsed by the Mail-in-a-Box project or its
> maintainer. Please do **not** ask the upstream project, its forum or Joshua
> Tauberer for help with this fork. Use this repository's
> [issues](https://github.com/LM1337/Mail-in-a-box-26/issues) instead.

**Status: first release (`v78-r2604.0`).** It is tested on test machines, on
a copy of a production box and on a box on the Internet (which tests ran for
each release, their results and what was not tested are in
[TESTING-fork.md](TESTING-fork.md)). Make a backup, and try an update on a copy
or a spare machine before you run it on the box that holds your mail.

All changes are in [CHANGELOG-fork.md](CHANGELOG-fork.md), every fixed bug
with cause and affected versions in [BUGS-fork.md](BUGS-fork.md). The full
documentation of the fork (English, with German sections) is
[README-fork.md](README-fork.md).

### Supported paths

| You have | Use | Details |
|---|---|---|
| a fresh Ubuntu 26.04 machine | `setup/bootstrap.sh` | [Installation](README-fork.md#installation) |
| a box with this fork (rc1 to rc3: point its checkout to GitHub first) | `setup/bootstrap.sh` again | [Updating the fork](README-fork.md#updating-the-fork--fork-aktualisieren) |
| a Mail-in-a-Box on Ubuntu 22.04 (v68 or later, older after an update to v78) or a release-upgraded 24.04, and a new 26.04 machine | `tools/migrate-to-2604.sh` (recommended: the old box stays as the way back) | [Migration](README-fork.md#migration-from-mail-in-a-box-22042404--umzug-von-mail-in-a-box) |
| the same machine, no second server | `tools/upgrade-in-place-to-2604.sh`. Both start points end on 26.04: from 22.04 it runs two Ubuntu release upgrades (first to 24.04, then to 26.04), from 24.04 only one. `--rollback` works until the first release upgrade starts; after that the only way back is restoring the backup. During each release upgrade new SSH logins fail for a while, and from 24.04 to 26.04 `sudo` is missing for a while and a new `tmux attach` fails until the reboot (follow `sudo tail -f /root/upgrade-2604/upgrade.log` instead): attach to the run before it starts and keep the connection open (when it starts right after a reboot, you cannot); if a login fails, wait, do not reboot | [In-place upgrade](README-fork.md#in-place-upgrade-to-2604--upgrade-an-ort-und-stelle) |

Ubuntu 22.04 boxes that stay on 22.04 should keep using upstream
Mail-in-a-Box v78.

### Quick start (fresh Ubuntu 26.04)

	sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/setup/bootstrap.sh)"

This installs the current release tag. The box's status checks compare the
installed version with the latest release of this repository (unless the
version check is disabled in the privacy setting).

### Reporting problems

* Bugs and questions: [GitHub issues](https://github.com/LM1337/Mail-in-a-box-26/issues).
  Please include the output of `sudo mailinabox` or of the tool's `--status`,
  the Ubuntu release and the version (`git -C ~/mailinabox describe`).
  Remove passwords, keys and your domain names first.
* **Security vulnerabilities: do not open a public issue.** Report them
  privately through
  [GitHub private vulnerability reporting](https://github.com/LM1337/Mail-in-a-box-26/security/advisories/new)
  or by email to [LM1337@networkx.eu](mailto:LM1337@networkx.eu), see [SECURITY.md](.github/SECURITY.md). Vulnerabilities that also affect
  upstream Mail-in-a-Box v78 should additionally be reported to upstream as
  described in its [security guide](security.md).

### Credits

* **Mail-in-a-Box** was created by [Joshua Tauberer (@JoshData)](https://github.com/JoshData)
  and is developed by its
  [contributors](https://github.com/mail-in-a-box/mailinabox/graphs/contributors).
  Almost all of this code is theirs. Upstream: <https://mailinabox.email>;
  upstream's own README is kept as [README-upstream.md](README-upstream.md).
* The **Ubuntu 26.04 port** this fork is based on is by
  [David Blythe (@writeDavid)](https://github.com/writeDavid)
  ([writeDavid/mailinabox-26.04](https://github.com/writeDavid/mailinabox-26.04),
  upstream [PR #2603](https://github.com/mail-in-a-box/mailinabox/pull/2603),
  not yet merged upstream), with fixes by
  [Yoann Gauthier-Colin (@Gwerlas)](https://github.com/Gwerlas).
* The IMAPSieve spam/ham learning that replaces dovecot-antispam comes from
  upstream [PR #2571](https://github.com/mail-in-a-box/mailinabox/pull/2571)
  by [@yeah](https://github.com/yeah) (not yet merged upstream).
* Fork maintenance, the migration and in-place upgrade tools and the fixes in
  CHANGELOG-fork.md: [@LM1337](https://github.com/LM1337), with AI assistance
  (commits marked `Co-Authored-By: Claude`).

### License

Like Mail-in-a-Box, this fork is in the public domain: copyright and related
rights are waived through
[CC0 1.0 Universal](https://creativecommons.org/publicdomain/zero/1.0/), see
[LICENSE](LICENSE). The fork's own changes are released under the same
waiver, and so must be all contributions (see [CONTRIBUTING.md](CONTRIBUTING.md)).
CC0 does not cover trademarks: "Mail-in-a-Box" is the name of the upstream
project and is used here only to say what this fork is based on.
`conf/dovecot-*.conf` contain comments from Dovecot's default configuration
(Dovecot's license: MIT/LGPL-2.1). The programs that setup downloads and
installs (Nextcloud, Roundcube, Z-Push, the Roundcube plugins, Ubuntu and
sury.org packages) keep their own licenses.

A German version of the fork documentation is in [README-fork.md](README-fork.md).
