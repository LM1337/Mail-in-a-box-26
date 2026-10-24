Mail-in-a-Box for Ubuntu 26.04 (unofficial fork)
================================================

> **This is an unofficial, community-maintained fork of
> [Mail-in-a-Box](https://github.com/mail-in-a-box/mailinabox).** It is not
> affiliated with, maintained or endorsed by the Mail-in-a-Box project or its
> maintainer. Please do **not** ask the upstream project, its forum or Joshua
> Tauberer for help with this fork. Use this repository's
> [issues](https://github.com/LM1337/Mail-in-a-box-26/issues) instead.

**Status: release candidate (`v78-r2604.0-rc3`).** It is tested on test
machines and on a copy of a production box, but it is not a final release.
Make a backup, and try it on a copy or a spare machine before you run it on
the box that holds your mail.

Mail-in-a-Box v78, the latest upstream release, supports Ubuntu 22.04 only.
This fork runs on **Ubuntu 26.04 LTS** and keeps Mail-in-a-Box's design (one
setup command, no configuration options). Main differences from v78: Dovecot
2.4, PHP 8.5, Nextcloud 34, Roundcube 1.7, Z-Push 2.7, full-text search with
fts_xapian. All changes are in [CHANGELOG-fork.md](CHANGELOG-fork.md), every
fixed bug with cause and affected versions in [BUGS-fork.md](BUGS-fork.md).
The full documentation of the fork (English and German) is
[README-fork.md](README-fork.md).

### Supported paths

| You have | Use | Details |
|---|---|---|
| a fresh Ubuntu 26.04 machine | `setup/bootstrap.sh` | [Installation](README-fork.md#installation) |
| a Mail-in-a-Box on Ubuntu 22.04 (v68 or later, older after an update to v78) or a release-upgraded 24.04, and a new 26.04 machine | `tools/migrate-to-2604.sh` (recommended: the old box stays as the way back) | [Migration](README-fork.md#migration-from-mail-in-a-box-22042404--umzug-von-mail-in-a-box) |
| the same machine, no second server | `tools/upgrade-in-place-to-2604.sh` (22.04 → 24.04 → 26.04 or 24.04 → 26.04; cannot be undone after the first release upgrade) | [In-place upgrade](README-fork.md#in-place-upgrade-to-2604--upgrade-an-ort-und-stelle) |

Ubuntu 22.04 boxes that stay on 22.04 should keep using upstream
Mail-in-a-Box v78.

### Quick start (fresh Ubuntu 26.04)

	curl -s https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/setup/bootstrap.sh | sudo bash

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

---

### Deutsch (Kurzfassung)

Dies ist eine **inoffizielle Abspaltung (Fork) von Mail-in-a-Box** für
**Ubuntu 26.04 LTS**. Sie wird nicht vom Mail-in-a-Box-Projekt betreut oder
unterstützt; Fragen bitte nicht im Upstream-Forum stellen, sondern hier als
[Issue](https://github.com/LM1337/Mail-in-a-box-26/issues).

**Stand: Release Candidate (`v78-r2604.0-rc3`).** Vor dem Einsatz eine
Sicherung anlegen und zuerst auf einer Kopie oder einer Ersatzmaschine
ausprobieren.

Unterstützte Wege: Neuinstallation auf Ubuntu 26.04 (`setup/bootstrap.sh`),
Umzug einer bestehenden Box (Ubuntu 22.04 oder per Release-Upgrade auf 24.04
gehoben) auf eine neue 26.04-Maschine (`tools/migrate-to-2604.sh`, empfohlen)
und Upgrade an Ort und Stelle derselben Maschine
(`tools/upgrade-in-place-to-2604.sh`). Einzelheiten stehen auf Deutsch in
[README-fork.md](README-fork.md).

Sicherheitslücken bitte nicht öffentlich melden, sondern über die private
Meldefunktion von GitHub oder per Mail an
[LM1337@networkx.eu](mailto:LM1337@networkx.eu) (siehe [SECURITY.md](.github/SECURITY.md)).

Dank an Joshua Tauberer und alle, die an Mail-in-a-Box mitgearbeitet haben,
sowie an David Blythe (writeDavid) für die 26.04-Portierung. Lizenz: CC0 1.0
(gemeinfrei), wie das Original.
