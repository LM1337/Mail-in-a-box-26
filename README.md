Mail-in-a-Box for Ubuntu 26.04 (unofficial fork)
================================================

An unofficial fork of [Mail-in-a-Box](https://github.com/mail-in-a-box/mailinabox)
v78 that runs on **Ubuntu 26.04 LTS** with current versions of its software.

### Why this fork

Mail-in-a-Box v78, the latest upstream release, installs only on **Ubuntu
22.04 LTS**. Standard security maintenance for Ubuntu 22.04 ends in **May
2027** (after that only with Ubuntu Pro ESM, until May 2032). Several parts of
the v78 stack are already out of support upstream:

* **PHP 8.0** from the third-party PPA `ppa:ondrej/php`. php.net ended
  security support for PHP 8.0 on 26 November 2023. v78 stays on 8.0 because
  of Nextcloud.
* **Nextcloud 27.1.11**. Nextcloud 27 reached end of life in June 2024.
* **Roundcube 1.6**, an LTS branch that only gets important security fixes;
  its active support ended on 10 May 2026.
* **Dovecot 2.3** and **OpenSSL 3.0** are no longer actively supported by
  their projects. Ubuntu 22.04 still backports security fixes to its packages
  (Dovecot 2.3.16, OpenSSL 3.0.2) until May 2027.

Upstream is working on Ubuntu 26.04 (the port in
[PR #2603](https://github.com/mail-in-a-box/mailinabox/pull/2603) is open, not
yet merged). This fork builds on that port. Its goals:

* Run on **Ubuntu 26.04 LTS** (standard support until May 2031, ESM until May
  2036) with current versions of PHP, Nextcloud, Roundcube and Dovecot.
* Use Ubuntu's own packages where possible: PHP 8.5 comes from the Ubuntu
  archive. packages.sury.org is only a fallback, limited by an apt pin to what
  Ubuntu lacks (`php8.5-imap`, `php-common`, and PHP 8.2 for the Nextcloud
  upgrade chain).
* Keep Mail-in-a-Box's design: one setup command, no configuration options.
* Provide a way from an existing box: a migration to a new 26.04 machine, or
  an in-place upgrade from Ubuntu 22.04 or 24.04 (see
  [Supported paths](#supported-paths)).

### Main components

| Component | Mail-in-a-Box v78 (Ubuntu 22.04) | This fork (Ubuntu 26.04) |
|---|---|---|
| Ubuntu | 22.04 LTS (standard support until May 2027) | 26.04 LTS (standard support until May 2031) |
| PHP | 8.0 from `ppa:ondrej/php` (no security support since 26 Nov 2023) | 8.5 from the Ubuntu archive (security support until 31 Dec 2029) |
| Nextcloud ¹ | 27.1.11 (end of life June 2024) | 34.0.5 (supported until June 2027) ³ |
| Nextcloud apps contacts / calendar / user_external ¹ | 5.5.4 / 4.7.20 / 3.4.0 | 8.9.2 / 6.6.3 / 4.0.0 |
| Roundcube ¹ | 1.6.20 (LTS, security fixes only), CardDAV plugin 4.4.3 | 1.7.5 (current stable), CardDAV plugin 5.1.4 |
| Z-Push ¹ | 2.7.7 | 2.7.7 (unchanged) |
| Dovecot | 2.3.16 | 2.4.2 |
| Full-text search (Dovecot) | none | **new:** fts_xapian 1.9.3, on by default (`FTS=off` turns it off) |
| Postfix | 3.6.4 | 3.10.6 |
| SpamAssassin (via spampd) | 3.4.6 (spampd 2.53), learning via dovecot-antispam | 4.0.2 (spampd 2.62), **new:** learning via IMAPSieve |
| nginx | 1.18.0 | 1.28.3 |
| OpenSSL | 3.0.2 | 3.5.5 (LTS, supported until April 2030) |
| Python (management daemon) | 3.10.12 | 3.14.4 |
| duplicity (backups) ² | 3.2.2 | 3.2.2 (unchanged) |

Versions as of `v78-r2604.0-rc3` (October 2026). For v78 the table shows the
version pinned in v78's setup scripts or the current Ubuntu 22.04 package.

¹ Pinned by the setup scripts (download with checksum). These change only with
a new release of Mail-in-a-Box or of this fork.

Rows without a mark come from the Ubuntu archive (except PHP in v78, which
comes from `ppa:ondrej/php`) and are updated by Ubuntu's security updates; the version shown is the upstream version Ubuntu ships.

² From `ppa:duplicity-team/duplicity-release-git`, in v78 and in the fork.

³ Nextcloud 35 was released in October 2026; this fork is still on 34.

---

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

All changes are in [CHANGELOG-fork.md](CHANGELOG-fork.md), every fixed bug
with cause and affected versions in [BUGS-fork.md](BUGS-fork.md). The full
documentation of the fork (English and German) is
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

Eine inoffizielle Abspaltung (Fork) von
[Mail-in-a-Box](https://github.com/mail-in-a-box/mailinabox) v78, die auf
**Ubuntu 26.04 LTS** mit aktuellen Versionen ihrer Software läuft.

#### Warum dieser Fork

Mail-in-a-Box v78, die neueste Upstream-Version, lässt sich nur auf **Ubuntu
22.04 LTS** installieren. Die normale Sicherheitsunterstützung für Ubuntu 22.04
endet im **Mai 2027** (danach nur noch mit Ubuntu Pro ESM bis Mai 2032).
Mehrere Teile von v78 werden von ihren Projekten schon nicht mehr unterstützt:

* **PHP 8.0** aus dem Fremd-PPA `ppa:ondrej/php`. php.net hat die
  Sicherheitsunterstützung für PHP 8.0 am 26. November 2023 beendet. v78
  bleibt wegen Nextcloud bei 8.0.
* **Nextcloud 27.1.11**. Nextcloud 27 ist seit Juni 2024 am Ende seiner
  Lebensdauer.
* **Roundcube 1.6**, ein LTS-Zweig, der nur noch wichtige Sicherheitskorrekturen
  bekommt; die aktive Unterstützung endete am 10. Mai 2026.
* **Dovecot 2.3** und **OpenSSL 3.0** werden von ihren Projekten nicht mehr
  aktiv unterstützt. Ubuntu 22.04 portiert Sicherheitskorrekturen bis Mai 2027
  in seine Pakete zurück (Dovecot 2.3.16, OpenSSL 3.0.2).

Upstream arbeitet an Ubuntu 26.04 (die Portierung in
[PR #2603](https://github.com/mail-in-a-box/mailinabox/pull/2603) ist offen,
noch nicht übernommen). Dieser Fork baut auf dieser Portierung auf. Ziele:

* Betrieb auf **Ubuntu 26.04 LTS** (normale Unterstützung bis Mai 2031, ESM
  bis Mai 2036) mit aktuellen Versionen von PHP, Nextcloud, Roundcube und
  Dovecot.
* Wo möglich Ubuntus eigene Pakete: PHP 8.5 kommt aus dem Ubuntu-Archiv.
  packages.sury.org dient nur als Notlösung und ist per apt-Pin auf das
  beschränkt, was Ubuntu fehlt (`php8.5-imap`, `php-common` und PHP 8.2 für
  die Nextcloud-Upgrade-Kette).
* Das Konzept von Mail-in-a-Box bleibt: ein Setup-Befehl, keine
  Konfigurationsoptionen.
* Ein Weg für bestehende Boxen: Umzug auf eine neue 26.04-Maschine oder
  Upgrade an Ort und Stelle von Ubuntu 22.04 oder 24.04.

#### Hauptkomponenten

| Komponente | Mail-in-a-Box v78 (Ubuntu 22.04) | Dieser Fork (Ubuntu 26.04) |
|---|---|---|
| Ubuntu | 22.04 LTS (normale Unterstützung bis Mai 2027) | 26.04 LTS (normale Unterstützung bis Mai 2031) |
| PHP | 8.0 aus `ppa:ondrej/php` (keine Sicherheitsunterstützung seit 26.11.2023) | 8.5 aus dem Ubuntu-Archiv (Sicherheitsunterstützung bis 31.12.2029) |
| Nextcloud ¹ | 27.1.11 (Ende der Lebensdauer Juni 2024) | 34.0.5 (unterstützt bis Juni 2027) ³ |
| Nextcloud-Apps contacts / calendar / user_external ¹ | 5.5.4 / 4.7.20 / 3.4.0 | 8.9.2 / 6.6.3 / 4.0.0 |
| Roundcube ¹ | 1.6.20 (LTS, nur Sicherheitskorrekturen), CardDAV-Plugin 4.4.3 | 1.7.5 (aktuelle stabile Version), CardDAV-Plugin 5.1.4 |
| Z-Push ¹ | 2.7.7 | 2.7.7 (unverändert) |
| Dovecot | 2.3.16 | 2.4.2 |
| Volltextsuche (Dovecot) | keine | **neu:** fts_xapian 1.9.3, standardmäßig an (`FTS=off` schaltet sie ab) |
| Postfix | 3.6.4 | 3.10.6 |
| SpamAssassin (über spampd) | 3.4.6 (spampd 2.53), Lernen über dovecot-antispam | 4.0.2 (spampd 2.62), **neu:** Lernen über IMAPSieve |
| nginx | 1.18.0 | 1.28.3 |
| OpenSSL | 3.0.2 | 3.5.5 (LTS, unterstützt bis April 2030) |
| Python (Verwaltungsdienst) | 3.10.12 | 3.14.4 |
| duplicity (Sicherungen) ² | 3.2.2 | 3.2.2 (unverändert) |

Stand: `v78-r2604.0-rc3` (Oktober 2026). Für v78 steht in der Tabelle die in
den Setup-Skripten von v78 festgelegte Version oder das aktuelle Paket von
Ubuntu 22.04.

¹ Von den Setup-Skripten fest vorgegeben (Download mit Prüfsumme). Diese
Versionen ändern sich nur mit einer neuen Version von Mail-in-a-Box oder
dieses Forks.

Zeilen ohne Markierung kommen aus dem Ubuntu-Archiv (außer PHP in v78, das
aus `ppa:ondrej/php` stammt) und werden über die
Sicherheitsaktualisierungen von Ubuntu aktualisiert; angegeben ist die
Upstream-Version, die Ubuntu ausliefert.

² Aus `ppa:duplicity-team/duplicity-release-git`, in v78 wie im Fork.

³ Nextcloud 35 ist im Oktober 2026 erschienen; dieser Fork ist noch bei 34.

#### Hinweis und Stand

Dies ist eine **inoffizielle Abspaltung**. Sie wird nicht vom
Mail-in-a-Box-Projekt betreut oder unterstützt; Fragen bitte nicht im
Upstream-Forum stellen, sondern hier als
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
