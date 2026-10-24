Mail-in-a-Box for Ubuntu 26.04 (fork)
=====================================

This is a fork of [Mail-in-a-Box](https://github.com/mail-in-a-box/mailinabox)
that runs on **Ubuntu 26.04 LTS**. It is upstream PR #2603 (the Ubuntu 26.04
port) merged with upstream v78, plus the fixes listed in
[CHANGELOG-fork.md](CHANGELOG-fork.md). Each fixed bug is documented with
symptom, cause and affected versions in [BUGS-fork.md](BUGS-fork.md).
Upstream's own history is in
[CHANGELOG.md](CHANGELOG.md), its documentation in [README.md](README.md) and
on <https://mailinabox.email>.

Main differences from upstream v78 (Ubuntu 22.04):

* Dovecot 2.4, Postfix and the rest of the mail stack from Ubuntu 26.04.
* PHP 8.5 from Ubuntu. packages.sury.org is pinned to what Ubuntu lacks
  (php8.2 for the Nextcloud upgrade chain, php8.5-imap, php-common).
* Nextcloud 34.0.5. Existing installations are upgraded step by step from
  Nextcloud 26; older versions are refused.
* Roundcube 1.7.5, Z-Push 2.7.7.
* fail2ban: repeat offenders get longer bans, slow jails catch slow attacks,
  an allowlist for own networks, a report of password spraying (see
  "Intrusion protection" below).

Diese Abspaltung (Fork) von Mail-in-a-Box läuft auf Ubuntu 26.04 LTS. Die
Unterschiede zu upstream v78 stehen oben und in CHANGELOG-fork.md, die behobenen Fehler einzeln in BUGS-fork.md.

Installation
------------

On a fresh Ubuntu 26.04 machine:

	curl -s https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/setup/bootstrap.sh | sudo bash

The environment variables `SOURCE` and `TAG` choose another repository or
tag. They must be given to `bash` after `sudo` (sudo does not pass on the
environment, and `TAG=main curl ...` only sets it for curl). Until the first
release tag exists, use the branch `main`:

	curl -s https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/setup/bootstrap.sh | sudo TAG=main bash

Setup can run without questions with `NONINTERACTIVE=1` and
`PRIMARY_HOSTNAME`, `PUBLIC_IP`, `PUBLIC_IPV6`, `EMAIL_ADDR`/`EMAIL_PW` (first
user, only on an empty box), given the same way.

Auf einer frischen Ubuntu-26.04-Maschine genügt der erste Befehl oben. Mit
`SOURCE` und `TAG` lassen sich ein anderes Repository oder ein anderer Tag
wählen. Die Variablen gehören hinter `sudo` vor `bash` (sudo reicht die
Umgebung nicht weiter, und `TAG=main curl ...` gilt nur für curl). Solange es
noch keinen Release-Tag gibt, den Zweig `main` nehmen:
`curl -s .../setup/bootstrap.sh | sudo TAG=main bash`.


Intrusion protection (adaptive fail2ban) / Schutz vor Anmeldeangriffen
---------------------------------------------------------------------

### English

Mail-in-a-Box bans an IP address after 20 failed logins within 30 seconds,
for 10 minutes. Attacks that try a few passwords per address, or one password
every few minutes, are never banned: a production box had 19,586 failed SMTP
logins from 4,627 addresses in one week and not a single ban. The fork adds
the following, on by default:

* **Adaptive banning.** Each new ban of an address in a jail lasts twice as
  long as its previous ban in that jail (fail2ban's `bantime.increment`), up
  to one week (`bantime_max`), and the address is banned there again after
  fewer failures. Bans in other jails do not count (no
  `bantime.overalljails`, which in fail2ban 1.1 adds up the ban counts of all
  jails and sends the second incident straight to the maximum); addresses
  banned again and again in any jail get Mail-in-a-Box's one-week recidive
  ban on all ports. Bans of the web ports (`miab-management`, `miab-munin`,
  `miab-owncloud`, `miab-roundcube` and the slow web jails) keep their fixed
  length, so that an office cannot lose the control panel, webmail and
  Nextcloud for days. fail2ban's database keeps the ban history for 30 days
  (`memory`, sets `dbpurgeage`; Debian's 1 day forgets a 10-minute ban after a
  day). Turning adaptive banning on or off restarts the jails
  (`fail2ban-client reload --restart`: a plain reload does not reset the
  options in running jails); their bans are restored from the database.
* **Slow jails.** `miab-slow-smtp` (SMTP AUTH on 465/587) and
  `miab-slow-dovecot` (IMAP, POP3, ManageSieve) ban an address after
  20 failures within 6 hours, for 1 hour the first time (`slow_maxretry`,
  `slow_findtime`, `slow_bantime`). They use Mail-in-a-Box's filters; the
  Dovecot one does not count connections without a login attempt (monitoring,
  TLS probes). They block only the mail ports (465, 587, 993, 995, 4190).
  `slow_web_jails` (off by default) adds `miab-slow-roundcube`,
  `miab-slow-owncloud` (Nextcloud) and `miab-slow-management` (control panel)
  with the same thresholds. They block HTTP and HTTPS: a calendar or contacts
  app with an old password polls Nextcloud every few minutes and would get its
  whole network banned from webmail and the control panel. Turn them on only
  with your networks on the allowlist. fail2ban applies a changed ban time
  also to the current first bans of a jail (a repeat offender's longer ban
  keeps its length), and an address with a ban history is banned again after
  fewer failures.
* **Allowlist.** Addresses and networks in `allowlist` (empty by default) are
  never banned, in addition to the box's own addresses. Saving the settings
  unbans addresses that are banned and now on the allowlist. Put your office or
  home network there: the jails count the failures of an address, not of an
  account, so all devices behind one office address add up, and a phone with
  an old password gets its network banned from the mail ports, for longer
  each time. The status checks warn about banned addresses that failed only
  as one or two existing accounts (often such a device).
* **Failed-login report.** The status checks read the mail log of the last
  48 hours (SMTP AUTH, IMAP, POP3, ManageSieve) and report accounts with failed
  logins from 20 or more addresses within 24 hours (`spray_min_ips`, password
  spraying) and addresses that keep failing for 12 hours or more without being
  banned once in that time (bans that have run out are looked up in
  fail2ban's database). Only accounts that exist on the box are named. Give
  such an account a long password that is not used anywhere else, and if it is an
  administrator, turn on two-factor authentication for the control panel.

The settings are stored in `$STORAGE_ROOT/settings.yaml` under `fail2ban`,
only the values that differ from the defaults, so they survive setup runs, the
migration and the in-place upgrade:

    fail2ban:
      adaptive: true          # repeat offenders get longer bans
      bantime_max: 604800     # seconds, 1 week to 1 year
      memory: 2592000         # seconds, at least bantime_max
      slow_jails: true        # mail ports
      slow_web_jails: false   # webmail, Nextcloud, control panel (HTTP/HTTPS)
      slow_maxretry: 20       # 3 to 1000
      slow_findtime: 21600    # seconds, 10 minutes to 7 days
      slow_bantime: 3600      # seconds, 1 minute to 7 days
      allowlist: []           # e.g. [192.0.2.0/24, 2001:db8:1::/48], at most 100
      spray_min_ips: 20

`bantime_max` is at least one week so that it never shortens the recidive
ban. Setup writes `/etc/fail2ban/jail.d/mailinabox_adaptive.conf` and
`/etc/fail2ban/fail2ban.d/mailinabox_adaptive.conf` from them
(`management/fail2ban_admin.py --setup`). A slow jail whose log file does not
exist yet is left out. With `adaptive`, `slow_jails` and `slow_web_jails` off
and an empty allowlist neither file exists, which is exactly upstream's configuration.
After editing settings.yaml by hand run `sudo management/fail2ban_admin.py
--apply`: it checks the whole configuration with `fail2ban-client -t`, puts
the old files back if fail2ban rejects it, and reloads fail2ban only if a file
changed. `--print` shows the files, `--allow 192.0.2.0/24` adds a network,
`--report` prints the failed-login report.

In the control panel, **System > Intrusion Protection** shows whether
fail2ban runs, the banned addresses (per address: the jails, time left, length
and start of each ban; with a filter), the jails with their counters and the
failed-login report (accounts with failures from many addresses, addresses
that keep failing, with their ban status). It unbans an address in all jails
or in one jail, unbans all addresses of a jail (after a confirmation), and
edits the settings: adaptive banning and the two kinds of slow jails on/off
(turning one off asks first), the thresholds (durations also as `30m`, `6h`, `2d`, `1w`), the
allowlist (one address or network per line) and "Restore defaults". It also
shows the address you use the panel from and offers to put it on the
allowlist (for IPv6 its /64, because the browser's own address changes), or
to unban it if it is banned (the slow mail jails block only the mail ports, so
the panel stays reachable). Unsaved edits of the settings form are kept when
you unban an address. The page uses this API (admin
only, changes by POST with form fields):

| Request | |
|---|---|
| `GET /admin/system/fail2ban` | fail2ban running, the jails with their counters and banned addresses (start, length, end and seconds left of each ban), the settings, defaults and limits, and `client` (the address of the request, whether it is allowlisted or one of the box's own) |
| `GET /admin/system/fail2ban/settings` | the settings, defaults and warnings about invalid stored values |
| `POST /admin/system/fail2ban/settings` | fields named like the settings; fields not sent keep their value, `reset=1` starts from the defaults. Answers with `changed`, `reloaded`, `restarted` (the jails were restarted), `skipped_jails`, `unbanned_allowlisted` (banned addresses that are on the allowlist now and were unbanned) and the new settings, or HTTP 400 with the reason |
| `POST /admin/system/fail2ban/unban` | `ip`, optionally `jail`. Answers with `unbanned_from`, `still_banned_in` and `history_deleted` |
| `POST /admin/system/fail2ban/unban-all` | `jail`: unbans every address banned in that jail |
| `GET /admin/system/fail2ban/report` | the failed-login report as JSON |

Unbanning without a jail runs `fail2ban-client unban <ip>`: the address is
unbanned in all jails, recidive included, and its ban history is deleted (by
fail2ban for the running jails, by the control panel in fail2ban's database
for jails that no longer run, e.g. turned-off slow jails), so a new ban starts
again at the initial ban time. Unbanning in one jail removes
only that jail's ban and history. Failures that other jails counted but did
not ban yet stay counted; to keep a device from being banned again, fix its
password or put its network on the allowlist. Locked out? From another
address (or the provider's console) run `sudo fail2ban-client unban <ip>`.

### Deutsch

Mail-in-a-Box sperrt eine IP-Adresse nach 20 fehlgeschlagenen Anmeldungen
innerhalb von 30 Sekunden für 10 Minuten. Angriffe mit wenigen Passwörtern
pro Adresse oder einem Passwort alle paar Minuten werden nie gesperrt: Eine
Produktivbox hatte in einer Woche 19.586 fehlgeschlagene SMTP-Anmeldungen von
4.627 Adressen und keine einzige Sperre. Der Fork ergänzt, standardmäßig
eingeschaltet:

* **Mitwachsende Sperren.** Jede neue Sperre einer Adresse in einem Jail
  dauert doppelt so lange wie ihre vorige Sperre in diesem Jail
  (`bantime.increment` von fail2ban), höchstens eine Woche (`bantime_max`),
  und die Adresse wird dort nach weniger Fehlversuchen wieder gesperrt.
  Sperren in anderen Jails zählen nicht mit (kein `bantime.overalljails`: Das
  zählt in fail2ban 1.1 die Sperren aller Jails zusammen und schickt schon den
  zweiten Vorfall auf die Höchstdauer); Adressen, die in irgendeinem Jail
  immer wieder gesperrt werden, bekommen die einwöchige recidive-Sperre von
  Mail-in-a-Box auf allen Ports. Sperren der Web-Ports (`miab-management`,
  `miab-munin`, `miab-owncloud`, `miab-roundcube` und die langsamen Web-Jails)
  behalten ihre feste Dauer, damit ein Büro nicht tagelang Admin-Oberfläche,
  Webmail und Nextcloud verliert. Die Datenbank von fail2ban behält die
  Sperrgeschichte 30 Tage (`memory`, setzt `dbpurgeage`; mit den 1 Tag von
  Debian ist eine 10-Minuten-Sperre nach einem Tag vergessen). Das Ein- oder
  Ausschalten startet die Jails neu (`fail2ban-client reload --restart`: Ein
  einfaches Neuladen setzt die Optionen laufender Jails nicht zurück); ihre
  Sperren werden aus der Datenbank wiederhergestellt.
* **Langsame Jails.** `miab-slow-smtp` (SMTP AUTH auf 465/587) und
  `miab-slow-dovecot` (IMAP, POP3, ManageSieve) sperren eine Adresse nach
  20 Fehlversuchen innerhalb von 6 Stunden, beim ersten Mal für 1 Stunde
  (`slow_maxretry`, `slow_findtime`, `slow_bantime`). Sie nutzen die Filter
  von Mail-in-a-Box; der für Dovecot zählt Verbindungen ohne Anmeldeversuch
  nicht mit (Überwachung, TLS-Prüfungen). Sie sperren nur die Mail-Ports (465,
  587, 993, 995, 4190). `slow_web_jails` (anfangs aus) ergänzt
  `miab-slow-roundcube`, `miab-slow-owncloud` (Nextcloud) und
  `miab-slow-management` (Admin-Oberfläche) mit denselben Schwellen. Sie
  sperren HTTP und HTTPS: Eine Kalender- oder Kontakte-App mit altem Passwort
  fragt Nextcloud alle paar Minuten ab und würde ihr ganzes Netz für Webmail
  und die Admin-Oberfläche sperren. Nur einschalten, wenn die eigenen Netze in
  der Freigabeliste stehen. Eine geänderte Sperrdauer wendet fail2ban auch
  auf die laufenden ersten Sperren eines Jails an (die längere Sperre eines
  Wiederholungstäters behält ihre Dauer), und eine Adresse mit
  Sperrgeschichte wird schon nach weniger Fehlversuchen wieder gesperrt.
* **Freigabeliste.** Adressen und Netze in `allowlist` (anfangs leer) werden
  nie gesperrt, zusätzlich zu den eigenen Adressen der Box. Beim Speichern
  der Einstellungen werden gesperrte Adressen, die nun in der Freigabeliste
  stehen, entsperrt. Hier gehört das
  Netz des Büros oder von zu Hause hinein: Die Jails zählen die Fehlversuche
  einer Adresse, nicht eines Kontos, alle Geräte hinter einer Büroadresse
  zählen also zusammen, und ein Telefon mit altem Passwort sperrt sein Netz
  für die Mail-Ports, jedes Mal länger. Die Statusprüfungen warnen vor
  gesperrten Adressen, die nur mit einem oder zwei vorhandenen Konten
  gescheitert sind (oft ein solches Gerät).
* **Bericht über Fehlanmeldungen.** Die Statusprüfungen lesen das Mail-Log der
  letzten 48 Stunden (SMTP AUTH, IMAP, POP3, ManageSieve) und melden Konten
  mit Fehlanmeldungen von 20 oder mehr Adressen innerhalb von 24 Stunden
  (`spray_min_ips`, Password Spraying) sowie Adressen, die 12 Stunden oder
  länger scheitern, ohne in dieser Zeit ein einziges Mal gesperrt worden zu
  sein (abgelaufene Sperren stehen in der Datenbank von fail2ban). Genannt
  werden nur Konten, die es
  auf der Box gibt. Ein solches Konto braucht ein langes Passwort, das nirgends
  sonst verwendet wird, und, wenn es ein Administrator ist, die
  Zwei-Faktor-Anmeldung für die Admin-Oberfläche.

Die Einstellungen stehen in `$STORAGE_ROOT/settings.yaml` unter `fail2ban`,
nur die Werte, die vom Standard abweichen. Sie überstehen so Setup-Läufe, den
Umzug und das Upgrade an Ort und Stelle (Beispiel und Grenzen siehe oben).
`bantime_max` beträgt mindestens eine Woche, damit die recidive-Sperre nie
kürzer wird. Das Setup schreibt daraus
`/etc/fail2ban/jail.d/mailinabox_adaptive.conf` und
`/etc/fail2ban/fail2ban.d/mailinabox_adaptive.conf`
(`management/fail2ban_admin.py --setup`). Ein langsames Jail, dessen Logdatei
noch fehlt, wird ausgelassen. Sind `adaptive`, `slow_jails` und
`slow_web_jails` aus und ist die Freigabeliste leer, gibt es keine der beiden Dateien, also genau die
Konfiguration von upstream. Nach einer Änderung von settings.yaml von Hand
`sudo management/fail2ban_admin.py --apply` aufrufen: Es prüft die ganze
Konfiguration mit `fail2ban-client -t`, stellt bei einer Ablehnung die alten
Dateien wieder her und lädt fail2ban nur neu, wenn sich eine Datei geändert
hat. `--print` zeigt die Dateien, `--allow 192.0.2.0/24` fügt ein Netz hinzu,
`--report` gibt den Bericht über Fehlanmeldungen aus.

In der Admin-Oberfläche zeigt **System > Intrusion Protection**, ob fail2ban
läuft, die gesperrten Adressen (je Adresse die Jails mit Restdauer, Länge und
Beginn jeder Sperre; mit Filter), die Jails mit ihren Zählern und den Bericht
über Fehlanmeldungen (Konten mit Fehlversuchen von vielen Adressen, Adressen,
die immer wieder scheitern, mit ihrem Sperrstatus). Dort lässt sich eine
Adresse in allen Jails oder in einem Jail freigeben, ein ganzes Jail nach
Rückfrage leeren und alles einstellen: mitwachsende Sperren und beide Arten
langsamer Jails an/aus (das Ausschalten fragt nach), die Schwellen (Dauern auch als `30m`,
`6h`, `2d`, `1w`), die Freigabeliste (eine Adresse oder ein Netz pro Zeile)
und „Restore defaults“. Die Seite zeigt außerdem die Adresse, von der aus sie
benutzt wird, und bietet an, sie in die Freigabeliste aufzunehmen (bei IPv6
ihr /64, weil sich die Adresse des Browsers ändert) oder, falls gesperrt,
freizugeben (die langsamen Mail-Jails sperren nur die Mail-Ports, die
Oberfläche bleibt also erreichbar). Ungespeicherte Änderungen im
Einstellungsformular bleiben bei einer Freigabe erhalten. Sie nutzt die oben beschriebene API
unter `/admin/system/fail2ban` (nur für Administratoren, Änderungen per POST
mit Formularfeldern).

Eine Freigabe ohne Jail ruft `fail2ban-client unban <ip>` auf: Die Adresse
wird in allen Jails freigegeben, recidive eingeschlossen, und ihre
Sperrgeschichte wird gelöscht (von fail2ban für die laufenden Jails, von der
Admin-Oberfläche in der Datenbank von fail2ban für Jails, die nicht mehr
laufen, etwa ausgeschaltete langsame Jails); eine neue Sperre beginnt also wieder mit der
anfänglichen Dauer. Eine Freigabe in einem Jail entfernt nur dessen Sperre und
Geschichte. Fehlversuche, die andere Jails gezählt, aber noch nicht gesperrt
haben, bleiben gezählt. Damit ein Gerät nicht erneut gesperrt wird, sein
Passwort korrigieren oder sein Netz in die Freigabeliste aufnehmen. Selbst
ausgesperrt? Von einer anderen Adresse (oder über die Konsole des Anbieters)
`sudo fail2ban-client unban <ip>` ausführen.


In-place upgrade to 26.04 / Upgrade an Ort und Stelle
-----------------------------------------------------

### English

`tools/upgrade-in-place-to-2604.sh` upgrades **the same machine** to Ubuntu
26.04 and this fork, when moving to a new machine is not an option (same IP
address, no second server). Supported: Ubuntu 22.04 with Mail-in-a-Box v60 or
later (22.04 → 24.04 → 26.04, two release upgrades) and boxes that were already
release-upgraded to 24.04 and still run Mail-in-a-Box v7x (one release
upgrade). Nextcloud must be 26 or later.

    curl -s https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/tools/upgrade-in-place-to-2604.sh \
      | sudo bash -s -- --check
    # inside tmux or screen, after reading the check:
    curl -s https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/tools/upgrade-in-place-to-2604.sh \
      | sudo bash

What it does, in phases that continue on their own after each reboot:

1. **preflight**: release, Mail-in-a-Box and Nextcloud versions, disk space,
   a backup younger than 24 hours, and a list of everything that is not
   managed by Mail-in-a-Box (Dovecot plugins, systemd drop-ins, nginx files,
   Docker, third-party apt sources). Local extensions block the upgrade until
   you pass `--keep-local`.
2. **snapshot**: counts and key fingerprints, a fresh Mail-in-a-Box backup and
   a system archive (`/etc`, the code outside the data directory, package
   lists). The archive is encrypted with the backup key and copied next to the
   backups (for an rsync target: `<target>-system/`).
3. **quiesce**: mail, web, cron and the update timers are stopped and masked,
   so they stay off across reboots. **Mail is offline from here.**
4. **prepare-release**, **release-2404**, **release-2604**: third-party sources
   off, PHP from ppa:ondrej removed, `do-release-upgrade` (old configuration
   files are kept), checks that the package system is clean, reboot.
5. **cleanup-etc**: a pristine Dovecot 2.4 configuration, old PHP versions,
   the old Python environment and ntp are removed (kept in
   `/root/upgrade-2604/moved`).
6. **setup** of this fork on the existing data (including the Nextcloud
   upgrade chain). Mail is back.
7. **local-ext**: your hooks in `/etc/mailinabox/upgrade-2604.d/*.sh` bring
   local extensions back for Dovecot 2.4. They run as root with
   `STORAGE_ROOT`, `PRIMARY_HOSTNAME`, `OLD_ETC` (the old `/etc`) and
   `MOVED_DIR`; a non-zero exit stops the upgrade.
8. **verify** and **finish**: counts and fingerprints compared with before,
   services, Nextcloud, status checks, a report of configuration that changed;
   backups and timers back on.

Downtime on a test box was about 50 minutes; plan 1-3 hours. The release
upgrades cannot be undone: `--rollback` only works before the first one.
After that the way back is the backup. Have the provider's console at hand,
SSH can be gone for a while during the release upgrade or after a reboot.
`--status` shows where it stands; running the command again continues.
`--cleanup-only` removes leftovers of the old releases afterwards.

Full-text search with fts_xapian is part of the fork (on by default, `FTS=off`
in `/etc/mailinabox.conf` turns it off). Boxes that added fts_xapian by hand
get it replaced by the fork's configuration; the existing indexes are used.

### Deutsch

`tools/upgrade-in-place-to-2604.sh` hebt **dieselbe Maschine** auf Ubuntu
26.04 und diesen Fork, wenn ein Umzug auf eine neue Maschine nicht in Frage
kommt (gleiche IP-Adresse, kein zweiter Server). Unterstützt werden Ubuntu
22.04 mit Mail-in-a-Box ab v60 (22.04 → 24.04 → 26.04, zwei Release-Upgrades)
und Boxen, die schon per Release-Upgrade auf 24.04 gehoben wurden und noch
Mail-in-a-Box v7x fahren (ein Release-Upgrade). Nextcloud muss mindestens
Version 26 haben.

    curl -s https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/tools/upgrade-in-place-to-2604.sh \
      | sudo bash -s -- --check
    # in tmux oder screen, nach Durchsicht der Prüfung:
    curl -s https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/tools/upgrade-in-place-to-2604.sh \
      | sudo bash

Ablauf in Phasen, die nach jedem Neustart von selbst weiterlaufen:

1. **preflight**: Release, Versionen von Mail-in-a-Box und Nextcloud,
   Speicherplatz, eine Sicherung jünger als 24 Stunden und eine Liste von
   allem, was Mail-in-a-Box nicht verwaltet (Dovecot-Plugins,
   systemd-Drop-ins, nginx-Dateien, Docker, fremde Paketquellen). Lokale
   Erweiterungen halten das Upgrade an, bis `--keep-local` angegeben wird.
2. **snapshot**: Zählungen und Schlüssel-Fingerabdrücke, eine frische
   Mail-in-a-Box-Sicherung und ein Systemarchiv (`/etc`, der Code außerhalb
   des Datenverzeichnisses, Paketlisten). Das Archiv wird mit dem
   Backup-Schlüssel verschlüsselt und neben die Sicherungen gelegt (bei einem
   rsync-Ziel: `<ziel>-system/`).
3. **quiesce**: Mail, Web, Cron und die Update-Timer werden angehalten und
   maskiert, damit sie auch über Neustarts hinweg aus bleiben. **Ab hier ist
   die Mail aus.**
4. **prepare-release**, **release-2404**, **release-2604**: fremde Quellen aus,
   PHP aus ppa:ondrej entfernt, `do-release-upgrade` (alte Konfigurationsdateien
   bleiben), Prüfung, dass das Paketsystem sauber ist, Neustart.
5. **cleanup-etc**: frische Dovecot-2.4-Konfiguration; alte PHP-Versionen, die
   alte Python-Umgebung und ntp werden entfernt (aufbewahrt in
   `/root/upgrade-2604/moved`).
6. **setup** dieses Forks auf den vorhandenen Daten (samt
   Nextcloud-Upgrade-Kette). Die Mail ist wieder da.
7. **local-ext**: eigene Hooks in `/etc/mailinabox/upgrade-2604.d/*.sh`
   holen lokale Erweiterungen für Dovecot 2.4 zurück. Sie laufen als root mit
   `STORAGE_ROOT`, `PRIMARY_HOSTNAME`, `OLD_ETC` (das alte `/etc`) und
   `MOVED_DIR`; ein Exit-Code ungleich 0 hält das Upgrade an.
8. **verify** und **finish**: Zählungen und Fingerabdrücke gegen vorher,
   Dienste, Nextcloud, Statusprüfungen, ein Bericht über geänderte
   Konfiguration; Sicherungen und Timer wieder an.

Die Ausfallzeit lag auf einer Testbox bei etwa 50 Minuten; einplanen sollte
man 1 bis 3 Stunden. Die Release-Upgrades lassen sich nicht zurücknehmen:
`--rollback` geht nur vor dem ersten. Danach führt der Weg zurück über die
Sicherung. Die Konsole des Anbieters sollte bereitliegen, weil SSH während
des Release-Upgrades oder nach einem Neustart eine Weile weg sein kann.
`--status` zeigt den Stand; ein erneuter Aufruf setzt fort. `--cleanup-only`
räumt danach die Reste der alten Releases weg.

Die Volltextsuche mit fts_xapian gehört zum Fork (standardmäßig an, `FTS=off`
in `/etc/mailinabox.conf` schaltet sie ab). Auf Boxen, die fts_xapian von Hand
eingerichtet haben, ersetzt sie die Konfiguration des Forks; die vorhandenen
Indexe werden weiter genutzt.


Migration from Mail-in-a-Box (22.04/24.04) / Umzug von Mail-in-a-Box
-------------------------------------------------------------------

### English

The recommended way to Ubuntu 26.04 is a move to a **new machine** with a
fresh Ubuntu 26.04 install: the old box stays untouched and is the way back.
(To upgrade the same machine, see the in-place section above.) `tools/migrate-to-2604.sh` does
that with one command, run as root on the new machine. It follows the path
documented by upstream (["restore your backup on a new machine, then run
setup"](https://mailinabox.email/maintenance.html#upgrade)), but copies the
data directly from the old box with rsync instead of going through a backup.

#### Supported old boxes

| Old box | Supported | Notes |
|---|---|---|
| Ubuntu 22.04, Mail-in-a-Box v68 ... v78 | yes | Nextcloud 26 or 27 |
| Ubuntu 22.04, Mail-in-a-Box v60 ... v67 | after an update | Nextcloud 23/25: first update the old box to upstream v78 (`curl -s https://mailinabox.email/setup.sh \| sudo bash`), then migrate |
| Ubuntu 24.04, release-upgraded in place, Mail-in-a-Box v7x (e.g. PHP 8.0 from ppa:ondrej) | yes | needs Nextcloud 26 or later; none of the old programs are taken over, only the data |
| Ubuntu 18.04/20.04, Mail-in-a-Box before v60 | no | move to 22.04 + v78 first |

The tool reads the Ubuntu release, the Mail-in-a-Box version (`git describe`
in the old setup directory) and the Nextcloud version (from `config.php`) and
explains what to do when the old box is too old.

#### Before you start

1. **New machine**: a fresh Ubuntu 26.04 install (a VM or a server, not a
   container), with at least as much disk space as the old box uses (the
   tool checks it, with a margin).
2. **SSH key login** from root on the new machine to root on the old box:

		# on the new machine, as root (sudo -i):
		ssh-keygen -t ed25519              # accept the defaults
		cat /root/.ssh/id_ed25519.pub      # copy this line
		# on the old box: append the line to /root/.ssh/authorized_keys
		# back on the new machine, test it:
		ssh root@old.example.com true

   Instead of root, a user with passwordless sudo works:
   `--from admin@old.example.com`.
3. **TTLs**: lower the TTL of records hosted elsewhere (A/AAAA of the box,
   SPF with `ip4:`) to e.g. 300 seconds 1 to 2 days ahead. The zones the box
   serves itself use a fixed TTL of 1 day; see "Switch DNS" below.
4. **Reverse DNS**: set the PTR of the new IP addresses to the hostname of
   the box now, at the hosting provider.
5. **Port 25 and blocklists**: many providers block outgoing port 25 for new
   servers (e.g. Hetzner Cloud, AWS, Google Cloud, DigitalOcean); ask them to
   unblock it. Check the new IP address on <https://check.spamhaus.org/>.
   `--check` tests both, and the tool does not stop the old box while port
   25 is blocked or the IP is listed (unless `--skip-network-checks`).
6. **Fresh backup** of the old box (System > Backup Status, or
   `sudo /root/mailinabox/management/backup.py` there).
7. **Postfix queue** of the old box: look at it (`postqueue -p`) and deliver
   what can be delivered (`postqueue -f`). The queue is not migrated.
8. **Announce the maintenance window** to the users. `--check` estimates the
   downtime; afterwards the DNS change takes effect over 1 to 3 days.
9. **tmux**: run the tool inside tmux or screen, see below.
10. Optional, for big boxes: **rehearse** first, see "Downtime and rehearsal".

#### Quick start

> **Run it in tmux or screen** (`apt-get install tmux`, then
> `tmux new -s migrate`; reattach after a disconnect with
> `tmux attach -t migrate`). The copy and setup take hours. If your SSH
> connection drops outside tmux, they stop halfway, possibly while the old
> box is already stopped and in the middle of a Nextcloud upgrade.

On the new machine, as root (`sudo -i`):

	git clone https://github.com/LM1337/Mail-in-a-box-26 /root/mailinabox
	/root/mailinabox/tools/migrate-to-2604.sh --check --from root@old.example.com
	/root/mailinabox/tools/migrate-to-2604.sh --from root@old.example.com

`--check` (alias `--dry-run`) checks both machines and shows the plan, the
sizes, the IP addresses, the free space, the downtime estimate and what
blocks the move. It changes nothing: no state, no copy, no packages. Run it
first.

Clone into `/root/mailinabox` as root, not into a user's home directory:
setup points `/usr/local/bin/mailinabox` and the nightly cron job to that
directory and runs them as root.

Without a clone (the tool clones the fork into `/root/mailinabox` itself,
like `bootstrap.sh`). `TAG` and `SOURCE` go after `sudo`; until the release
tag exists, the tool falls back to the branch `main`:

	curl -s https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/tools/migrate-to-2604.sh \
	  | sudo TAG=main bash -s -- --from root@old.example.com

For big boxes, copy the data ahead of time and switch over later:

	/root/mailinabox/tools/migrate-to-2604.sh --from root@old.example.com --sync-only   # hours, box keeps running
	/root/mailinabox/tools/migrate-to-2604.sh --rehearse      # optional: setup on the copy, box keeps running
	/root/mailinabox/tools/migrate-to-2604.sh --sync-only     # refresh shortly before the switch-over
	/root/mailinabox/tools/migrate-to-2604.sh                 # switch-over: stops the old box (asks first)

`--yes` skips the questions, but it never starts the downtime on its own:
`--sync-only --yes` copies unattended (e.g. overnight), and the switch-over
should be run attended. Only `--yes --switch-over` stops the old box
without asking, right after the live copy, at a time you cannot predict.

`--status` shows where the migration stands, `--help` all options
(`--hostname`, `--public-ip`, `--public-ipv6`, `--bwlimit`, `--compress`,
`--redo-from`, `--rollback`, `--finish`, `--check-old`,
`--push-zones-to-old`, ...). If the new machine has a public IPv6 address,
setup always uses it; to have no IPv6, remove it from the machine.

#### Phases

1. **preflight** (every run): both machines (Ubuntu release, Mail-in-a-Box
   and Nextcloud versions, rsync, SSH/sudo, clocks, disk space with margin,
   the Postfix queue), the target directory, port 25, Spamhaus and the PTR
   of the new IP. After the first confirmation, a copy of the old box's
   `/etc`, users/groups, `postconf -n`, root's crontab and the backup SSH key
   goes to `/root/migration`.
2. **sync-live**: `rsync -aHAXS --numeric-ids --delete` of `$STORAGE_ROOT`
   while the old box keeps running. Resumable, retried automatically after
   connection problems; repeat it with `--sync-only`.
3. **stop-old** (asks first): stops cron, the apt timers (package updates
   would restart services), the management daemon, nginx, PHP-FPM, Postfix,
   spampd, postgrey, OpenDKIM/OpenDMARC, Dovecot and the socket units that
   would start one of them again (e.g. `dovecot.socket`). They are masked
   with `systemctl mask --runtime`, which lives in `/run` and is gone after
   a reboot; nothing in the old box's configuration or data changes. nsd
   keeps running. The downtime starts here.
4. **sync-final**: waits until no process on the old box has a file open in
   `$STORAGE_ROOT` (cron jobs that were already running, a backup, Nextcloud
   `cron.php`), records counts and key fingerprints, copies the changes and
   then checks that nothing was started on the old box meanwhile (if so, it
   stops it again and copies once more). `/etc` is saved once more.
5. **prepare**: `/etc/mailinabox.conf` with the old hostname, storage path
   and MTA-STS mode and the new IP addresses; the old time zone; the backup
   SSH key `/root/.ssh/id_rsa_miab`; backups paused (see "Data safety");
   file owners are parked (see below).
6. **setup**: this fork's `setup/start.sh` with `NONINTERACTIVE=1`. It runs
   the data migrations (`setup/migrate.py`), the Nextcloud upgrade chain
   26 → 34 and the Roundcube database update.
7. **ownership**: file owners are mapped to the user IDs of the new machine.
8. **extras**: Z-Push device state (`/var/lib/z-push`, so phones do not
   resync everything) and munin graphs (`/var/lib/munin`). `--no-extras`.
9. **verify**: compares old and new (users, aliases, mailboxes, number of
   messages, Sieve scripts, DKIM key, DNSSEC keys and DS records, TLS key,
   backup key, Let's Encrypt account, Bayes counts, Nextcloud accounts,
   contacts and events), checks the services, `occ status`, the status
   checks, the old box (nothing started again) and writes a report of
   `/etc` customizations. Then it shows the next steps and, as the last
   block, the result. If a check fails, the exit code is 2, the backups stay
   paused, and running the command again checks again; `--finish` accepts
   the result.

The state is in `/root/migration/state`; running the command again continues
where it stopped. The log is `/root/migration/migrate.log`. When the tool
stops with an error after stop-old, it says so and prints the command to
start the old box again.

#### Downtime and rehearsal

The downtime lasts from stop-old until verify: the final copy (about as
long as a `--sync-only` refresh), two passes over all files for the owners,
setup with the package installation (15 to 30 minutes on a fresh machine)
and one Nextcloud upgrade step per major version (8 steps from Nextcloud 26,
each re-owning the whole Nextcloud data directory), and the checks. For a
box with a few hundred GB this can be 1 to 3 hours. The plan and `--check`
show an estimate.

To know it better and to shorten it:

* `--rehearse` runs setup once on the live copy while the old box keeps
  running. It installs the packages ahead of time and measures how long
  setup takes. Cron and the backups stay off on the new machine during the
  rehearsal, and its services are stopped and disabled again afterwards, so
  that a reboot does not start them; every later copy pauses the backups
  there again. The switch-over
  copies the data again and runs setup once more, now without the package
  installation.
* Or rehearse the whole migration against a snapshot of the new VM, measure
  the time, and reset the snapshot.

#### Data safety

* Nothing on the old box is changed or deleted. Its services are only
  stopped and masked until its next reboot, after confirmation.
  `--rollback` starts them again (see "Rollback").
* `rsync --delete` only runs into an empty target or into a target that
  carries the marker of an earlier run from the same old box
  (`$STORAGE_ROOT/.migrate-to-2604` with its machine-id, hostname and
  storage path). The `.rsync-partial` directories keep interrupted files
  out of their real place.
* Once setup has run on the new machine, the tool stops and masks its
  Mail-in-a-Box services before every further copy and waits until nothing
  uses `$STORAGE_ROOT` there. Files that such a copy replaces or deletes are
  kept in `$STORAGE_ROOT/.migrate-overwritten/<time>/`, and the tool asks
  even with `--yes` before the first such copy.
* Only one box may ever back up to a backup target. The copied
  `backup/custom.yaml` is replaced by `target: "off"` on the new machine
  until the checks pass (the original is `custom.yaml.migrate-saved`).
* Not copied: `backup/cache/` (rebuilt automatically) and `owncloud-backup/`
  (copies from old Nextcloud upgrades; `--with-owncloud-backup` copies it).
  `--skip-local-backups` also leaves out `backup/encrypted/`.

#### User IDs and file owners

rsync copies numeric owners (`--numeric-ids`). The system users get other IDs
on the new machine (opendkim, spampd, postgrey, `user-data`, ...), and most of
them do not even exist before setup has installed the packages. Mapping by
name during the copy is therefore not possible (and `rsync --usermap` cannot
map a whole range to an offset). Instead:

* Before setup, every owner that is not root and not the same name with the
  same ID on the new machine (`mail` = 8, `www-data` = 33 are fixed) is
  parked at *old ID + 2000000000*.
* Setup re-owns its own directories by name: `mail/mailboxes` and
  `mail/sieve` (mail), `mail/dkim` (opendkim), `mail/postgrey` (postgrey),
  `mail/spamassassin` (spampd), `mail/roundcube`, `owncloud` (www-data),
  `mail/users.sqlite` (root:www-data), `www` (owner `user-data`).
* After setup, every parked owner is mapped by its old name (from the old
  `/etc/passwd` and `/etc/group`) to the new ID. An owner whose name does
  not exist on the new machine keeps its old number only if that number is
  unused there; if it belongs to another account (e.g. an admin user 1000 on
  the old box and `ubuntu` = 1000 on the new one), the files go to root. Both
  cases are reported.

The new machine must accept 32-bit user IDs (VMs and servers do; some
containers do not, the tool checks).

#### Not migrated

* Changes to `/etc` (e.g. extra Postfix maps such as a
  `greylist_bypass_senders` table, postgrey whitelists, SpamAssassin rules,
  fail2ban jails, cron jobs, firewall rules). The old `/etc`, as of the
  final copy, is kept in `/root/migration/old-etc.tar.gz` (unpacked in
  `/root/migration/old-etc`), and `/root/migration/etc-report.txt` lists
  Postfix settings that differ, files named in them and files that exist
  only on the old box.
* Nextcloud apps installed by hand (they live in `/usr/local/lib/owncloud/apps`,
  outside the data). The tool lists them. Setup keeps the app store disabled
  (`'appstoreenabled' => false`).
* Mail in the old box's Postfix queue (`/var/spool/postfix`). Before the
  stop, the tool runs `postqueue -f`, waits a minute and saves the listing in
  `/root/migration/old-postqueue.txt`. If mail for the box's own mailboxes is
  still waiting, it asks (even with `--yes`) and prints how to deliver that
  mail to the new box later.
* Logs (`/var/log`, so the usage reports start empty) and ACL entries with
  named users (none in a normal box).

#### After the migration

##### 1. Test before switching DNS

Put the line `<new IP> <hostname>` into the hosts file of your own computer
(`/etc/hosts`; Windows: `C:\Windows\System32\drivers\etc\hosts`). Then open
`https://<hostname>/admin` and `https://<hostname>/mail`, log in, send a test
mail through the new box (SMTP submission) and receive one, and check
Nextcloud (files, contacts, calendars). Remove the line afterwards.

Webmail users must log in again: setup gives Roundcube a new key. The spam
filter (Bayes) and the greylisting database are taken over as they are.

##### 2. Switch DNS

* **Zones the box serves itself** (NS `ns1`/`ns2.<hostname>`, the default):
  change the glue records `ns1.<hostname>` and `ns2.<hostname>` at the
  registrar to the new IP addresses. The DS records stay the same, the
  DNSSEC keys are taken over.
  Resolvers cache the NS/glue records for the TTL the TLD sets (e.g. 2 days
  for .com, 1 day for .de), and the records of these zones for up to 1 day
  (Mail-in-a-Box serves them with TTL 86400; this cannot be lowered ahead).
  Until then the old box's nsd keeps answering, with the OLD IP addresses.
  So expect **1 to 3 days** (glue TTL plus 86400 seconds) in which some
  senders and clients still try the stopped old box. Mail is not lost:
  senders queue it and retry, usually for 4 to 5 days; some send a delay
  warning to their user after a few hours, a few give up earlier.
* **Shorter**: let the old box's nsd hand out the new IP addresses as well:

		/root/mailinabox/tools/migrate-to-2604.sh --push-zones-to-old

  This copies `/etc/nsd/zones/*.signed` from the new box to the old box's
  `/etc/nsd/zones` (its own files are kept in
  `/root/migrate-to-2604-nsd-orig` there) and runs `systemctl reload nsd`
  there. It is the one deliberate change to files on the old box.
  `--rollback` puts the old files back (by hand:
  `cp -a /root/migrate-to-2604-nsd-orig/. /etc/nsd/zones/` and
  `systemctl reload nsd` on the old box). Then only the cached records of
  up to 1 day remain.
* **Zones with external DNS**: change the A/AAAA records of the hostname
  (and the others listed in the admin panel under System > External DNS) to
  the new IP addresses. They take effect within their TTL.
* **Custom secondary nameservers** (System > Custom DNS,
  `_secondary_nameserver`): change the primary (master) IP address at that
  DNS provider to the new IP. Until then it fetches the zones from the old
  IP; if the old box is switched off, it serves the old zones for up to
  14 days (SOA expire). The tool lists them.
* **PTR** of the new IPs to the hostname, if not done yet.
* **MX** does not change as long as the hostname stays the same. SPF
  records with explicit `ip4:`/`ip6:` entries must be changed.

##### 3. Afterwards

* **Backups** resume on the new box with the same `secret_key.txt` and
  target once the checks have passed (or after `--finish`). Never start the
  old box's services again, because two boxes would then write to one
  backup target.
* **The old box** stays stopped; its services are masked until its next
  reboot. Do not reboot it while DNS may still point to it.
  `--check-old` shows whether anything runs there again. Switch it off once
  DNS has switched over (glue TTL plus a day).
* Review `/root/migration/etc-report.txt` and redo the customizations
  you still need by hand.
* Delete `/root/migration` when you no longer need it (it contains the old
  password hashes and keys), and `$STORAGE_ROOT/.migrate-overwritten` if it
  exists.

#### Rollback

`/root/mailinabox/tools/migrate-to-2604.sh --rollback` goes back to the old
box. Use it when the new box does not work and you want the old one back,
best before you change DNS.

It pauses the backups on the new machine, stops and disables its
Mail-in-a-Box services (they are enabled again by the next attempt) and ends
a backup that still runs there after a minute. It puts the old box's own zone
files back if `--push-zones-to-old` ran, sets `virtual_transport` on the old
box back (to the Mail-in-a-Box default `lmtp:[127.0.0.1]:10025` if the saved
value points to the new machine) and stops a Postfix started there by hand
(the queue hint of the stop), unmasks the services on the old box and starts them again.

* If DNS was changed already, change the glue or A/AAAA records back.
* Mail that reached the new box after a DNS switch is **not** copied back
  to the old box. The next attempt keeps the files its copy replaces in
  `$STORAGE_ROOT/.migrate-overwritten/`, from where single folders can be
  imported with `doveadm import`.
* To try again, run the migration command again; it copies the data again
  and continues.
* Once the new box has been live for a while, do not roll back any more:
  the mail it received would be missing on the old box.

#### From a backup instead of SSH

	/root/mailinabox/tools/migrate-to-2604.sh --from-backup /mnt/old-backup/encrypted \
	  --backup-key /root/secret_key.txt [--hostname box.example.com]

This restores the duplicity backup into `/home/user-data` (`--storage-root`
for another path; it must be the old box's path, Nextcloud stores it), puts
`secret_key.txt` back, then runs prepare, setup, ownership and verify. The
storage user is created before the restore, so that its files get its new
ID. The hostname is read from the restored TLS certificate unless
`--hostname` is given. Limits: a backup does not contain `backup/` (so no
`custom.yaml`; set the backup target again), the old `/etc`, Z-Push or
munin, and there is no list of the old user IDs (setup re-owns the service
directories, the storage user's files and dotfiles are fixed explicitly,
and every other owner with an ID of 1000 or more is reported in
`/root/migration/foreign-owners.txt`). A remote backup URL (`s3://`,
`b2://`, `rsync://`, ...) is passed to duplicity; put its credentials in the
environment. If that does not work, restore by hand and run setup:

	sudo apt-get install duplicity
	sudo useradd -m user-data
	sudo PASSPHRASE="$(head -n 1 secret_key.txt | tr -d '\r')" duplicity restore --force file:///path/to/encrypted /home/user-data
	sudo install -D -m 600 secret_key.txt /home/user-data/backup/secret_key.txt
	curl -s https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/setup/bootstrap.sh | sudo TAG=main bash
	sudo chown -R user-data:user-data /home/user-data/www && sudo chown user-data:user-data /home/user-data /home/user-data/mailinabox.version

### Deutsch

Der empfohlene Weg zu Ubuntu 26.04 ist der Umzug auf eine **neue Maschine**
mit frisch installiertem Ubuntu 26.04: Die alte Box bleibt unverändert und ist
der Weg zurück. (Zum Upgrade derselben Maschine siehe den Abschnitt oben.)
`tools/migrate-to-2604.sh` erledigt das mit einem Befehl, der als root auf der
neuen Maschine läuft. Das Werkzeug folgt dem vom Upstream-Projekt
beschriebenen Weg („Sicherung auf einer neuen Maschine einspielen, dann Setup
ausführen“), kopiert die Daten aber mit rsync direkt von der alten Box statt
über eine Sicherung.

#### Unterstützte alte Boxen

| Alte Box | Unterstützt | Hinweise |
|---|---|---|
| Ubuntu 22.04, Mail-in-a-Box v68 ... v78 | ja | Nextcloud 26 oder 27 |
| Ubuntu 22.04, Mail-in-a-Box v60 ... v67 | nach Aktualisierung | Nextcloud 23/25: die alte Box zuerst auf upstream v78 bringen (`curl -s https://mailinabox.email/setup.sh \| sudo bash`), dann umziehen |
| Ubuntu 24.04, per Release-Upgrade aktualisiert, Mail-in-a-Box v7x (z. B. PHP 8.0 aus ppa:ondrej) | ja | braucht Nextcloud 26 oder neuer; übernommen werden nur die Daten, keine alten Programme |
| Ubuntu 18.04/20.04, Mail-in-a-Box vor v60 | nein | zuerst auf 22.04 mit v78 umziehen |

Das Werkzeug liest Ubuntu-Version, Mail-in-a-Box-Version (`git describe` im
alten Setup-Verzeichnis) und Nextcloud-Version (aus `config.php`) aus und
erklärt, was zu tun ist, wenn die alte Box zu alt ist.

#### Vor dem Umzug

1. **Neue Maschine**: frisch installiertes Ubuntu 26.04 (eine VM oder ein
   Server, kein Container) mit mindestens so viel Plattenplatz, wie die alte
   Box belegt (das Werkzeug prüft das, mit Reserve).
2. **Anmeldung per SSH-Schlüssel** von root auf der neuen Maschine als root
   auf der alten Box:

		# auf der neuen Maschine, als root (sudo -i):
		ssh-keygen -t ed25519              # Vorgaben übernehmen
		cat /root/.ssh/id_ed25519.pub      # diese Zeile kopieren
		# auf der alten Box: die Zeile an /root/.ssh/authorized_keys anhängen
		# zurück auf der neuen Maschine testen:
		ssh root@alt.example.com true

   Statt root geht auch ein Benutzer mit sudo ohne Passwort:
   `--from admin@alt.example.com`.
3. **TTL**: Die TTL von Einträgen, die anderswo gehostet werden (A/AAAA der
   Box, SPF mit `ip4:`), 1 bis 2 Tage vorher auf z. B. 300 Sekunden senken.
   Die Zonen, die die Box selbst bedient, haben eine feste TTL von einem Tag;
   siehe unten „DNS umstellen“.
4. **Reverse DNS**: den PTR-Eintrag der neuen IP-Adressen jetzt schon beim
   Hoster auf den Hostnamen der Box setzen.
5. **Port 25 und Sperrlisten**: Viele Anbieter sperren ausgehenden Port 25
   für neue Server (z. B. Hetzner Cloud, AWS, Google Cloud, DigitalOcean);
   die Freischaltung beantragen. Die neue IP-Adresse auf
   <https://check.spamhaus.org/> prüfen. `--check` testet beides, und das
   Werkzeug hält die alte Box nicht an, solange Port 25 gesperrt oder die IP
   gelistet ist (außer mit `--skip-network-checks`).
6. **Frische Sicherung** der alten Box (System > Backup Status oder dort
   `sudo /root/mailinabox/management/backup.py`).
7. **Postfix-Warteschlange** der alten Box ansehen (`postqueue -p`) und
   zustellen, was zustellbar ist (`postqueue -f`). Die Warteschlange zieht
   nicht mit um.
8. **Wartungsfenster ankündigen**. `--check` schätzt die Ausfallzeit;
   danach wirkt die DNS-Umstellung über 1 bis 3 Tage.
9. **tmux**: das Werkzeug in tmux oder screen starten, siehe unten.
10. Optional, bei großen Boxen: zuerst **proben**, siehe „Ausfallzeit und
    Probelauf“.

#### Schnellstart

> **In tmux oder screen starten** (`apt-get install tmux`, dann
> `tmux new -s migrate`; nach einem Verbindungsabbruch mit
> `tmux attach -t migrate` wieder verbinden). Kopie und Setup dauern
> Stunden. Bricht die SSH-Verbindung außerhalb von tmux ab, enden sie
> mittendrin, womöglich bei schon angehaltener alter Box und mitten in einem
> Nextcloud-Upgrade.

Auf der neuen Maschine als root (`sudo -i`):

	git clone https://github.com/LM1337/Mail-in-a-box-26 /root/mailinabox
	/root/mailinabox/tools/migrate-to-2604.sh --check --from root@alt.example.com
	/root/mailinabox/tools/migrate-to-2604.sh --from root@alt.example.com

`--check` (auch `--dry-run`) prüft beide Maschinen und zeigt Plan, Größen,
IP-Adressen, freien Platz, die geschätzte Ausfallzeit und alles, was den
Umzug verhindert. Es ändert nichts: kein Zustand, keine Kopie, keine Pakete.
Zuerst ausführen.

Als root nach `/root/mailinabox` klonen, nicht in das Home-Verzeichnis eines
Benutzers: Das Setup verweist `/usr/local/bin/mailinabox` und den nächtlichen
Cron-Job auf dieses Verzeichnis und führt sie als root aus.

Ohne Klon (das Werkzeug klont den Fork wie `bootstrap.sh` selbst nach
`/root/mailinabox`). `TAG` und `SOURCE` stehen hinter `sudo`; solange es den
Release-Tag noch nicht gibt, nimmt das Werkzeug den Zweig `main`:

	curl -s https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/tools/migrate-to-2604.sh \
	  | sudo TAG=main bash -s -- --from root@alt.example.com

Bei großen Boxen die Daten vorab kopieren und später umschalten:

	/root/mailinabox/tools/migrate-to-2604.sh --from root@alt.example.com --sync-only   # Stunden, Box läuft weiter
	/root/mailinabox/tools/migrate-to-2604.sh --rehearse      # optional: Setup auf der Kopie, Box läuft weiter
	/root/mailinabox/tools/migrate-to-2604.sh --sync-only     # kurz vor der Umschaltung auffrischen
	/root/mailinabox/tools/migrate-to-2604.sh                 # Umschaltung: hält die alte Box an (mit Rückfrage)

`--yes` überspringt die Rückfragen, beginnt die Ausfallzeit aber nie von
selbst: `--sync-only --yes` kopiert unbeaufsichtigt (z. B. über Nacht), die
Umschaltung sollte man beaufsichtigt starten. Nur `--yes --switch-over` hält
die alte Box ohne Rückfrage an, direkt nach der Kopie, zu einem nicht
vorhersehbaren Zeitpunkt.

`--status` zeigt den Stand des Umzugs, `--help` alle Optionen
(`--hostname`, `--public-ip`, `--public-ipv6`, `--bwlimit`, `--compress`,
`--redo-from`, `--rollback`, `--finish`, `--check-old`,
`--push-zones-to-old` …). Hat die neue Maschine eine öffentliche
IPv6-Adresse, verwendet das Setup sie immer; wer kein IPv6 will, entfernt sie
von der Maschine.

#### Phasen

1. **preflight** (bei jedem Lauf): beide Maschinen (Ubuntu-Version,
   Mail-in-a-Box- und Nextcloud-Version, rsync, SSH/sudo, Uhrzeit,
   Speicherplatz mit Reserve, Postfix-Warteschlange), das Zielverzeichnis,
   Port 25, Spamhaus und der PTR-Eintrag der neuen IP. Nach der ersten
   Bestätigung kommt eine Kopie von `/etc`, Benutzern/Gruppen,
   `postconf -n`, der Crontab von root und dem Sicherungs-SSH-Schlüssel der
   alten Box nach `/root/migration`.
2. **sync-live**: `rsync -aHAXS --numeric-ids --delete` von `$STORAGE_ROOT`,
   während die alte Box weiterläuft. Fortsetzbar, nach Verbindungsproblemen
   automatisch wiederholt; mit `--sync-only` wiederholbar.
3. **stop-old** (mit Rückfrage): hält auf der alten Box cron, die apt-Timer
   (Paketaktualisierungen würden Dienste neu starten), den Verwaltungsdienst,
   nginx, PHP-FPM, Postfix, spampd, postgrey, OpenDKIM/OpenDMARC, Dovecot und
   die Socket-Units an, die einen davon wieder starten würden (z. B.
   `dovecot.socket`). Sie werden mit `systemctl mask --runtime` gesperrt; das
   liegt in `/run` und verschwindet beim nächsten Neustart. An Konfiguration
   und Daten der alten Box ändert sich nichts. nsd läuft weiter. Ab hier
   beginnt die Ausfallzeit.
4. **sync-final**: wartet, bis kein Prozess auf der alten Box mehr eine
   Datei in `$STORAGE_ROOT` geöffnet hat (bereits laufende Cron-Jobs, eine
   Sicherung, Nextcloud-`cron.php`), hält Zähler und
   Schlüssel-Fingerabdrücke fest, kopiert die Änderungen und prüft danach,
   ob auf der alten Box inzwischen etwas gestartet wurde (dann hält es das
   wieder an und kopiert noch einmal). `/etc` wird noch einmal gesichert.
5. **prepare**: `/etc/mailinabox.conf` mit altem Hostnamen, Datenpfad und
   MTA-STS-Modus und den neuen IP-Adressen; die alte Zeitzone; der
   Sicherungs-SSH-Schlüssel `/root/.ssh/id_rsa_miab`; Sicherungen pausiert
   (siehe „Datensicherheit“); Dateibesitzer werden geparkt (siehe unten).
6. **setup**: `setup/start.sh` dieses Forks mit `NONINTERACTIVE=1`. Es führt
   die Datenmigrationen (`setup/migrate.py`), die Nextcloud-Upgrade-Kette
   26 → 34 und die Roundcube-Datenbankaktualisierung aus.
7. **ownership**: Die Dateibesitzer werden auf die Benutzerkennungen der
   neuen Maschine umgesetzt.
8. **extras**: Z-Push-Gerätezustand (`/var/lib/z-push`, damit Telefone nicht
   alles neu synchronisieren) und munin-Grafiken (`/var/lib/munin`).
   Abschaltbar mit `--no-extras`.
9. **verify**: vergleicht alt und neu (Benutzer, Aliasse, Postfächer, Anzahl
   der Nachrichten, Sieve-Skripte, DKIM-Schlüssel, DNSSEC-Schlüssel und
   DS-Einträge, TLS-Schlüssel, Sicherungsschlüssel, Let’s-Encrypt-Konto,
   Bayes-Zähler, Nextcloud-Konten, Kontakte und Termine), prüft die Dienste,
   `occ status`, die Statusprüfungen und die alte Box (nichts wieder
   gestartet) und schreibt einen Bericht der Anpassungen in `/etc`. Danach
   zeigt es die nächsten Schritte und als letzten Block das Ergebnis.
   Schlägt eine Prüfung fehl, ist der Rückgabewert 2, die Sicherungen
   bleiben pausiert, und ein erneuter Aufruf prüft noch einmal; `--finish`
   übernimmt das Ergebnis.

Der Zustand liegt in `/root/migration/state`; ein erneuter Aufruf setzt an der
unterbrochenen Stelle fort. Das Protokoll ist `/root/migration/migrate.log`.
Bricht das Werkzeug nach stop-old mit einem Fehler ab, sagt es das und nennt
den Befehl, der die alte Box wieder startet.

#### Ausfallzeit und Probelauf

Die Ausfallzeit reicht von stop-old bis verify: die letzte Kopie (etwa so
lange wie eine Auffrischung mit `--sync-only`), zwei Durchläufe über alle
Dateien für die Besitzer, das Setup mit der Paketinstallation (15 bis
30 Minuten auf einer frischen Maschine) und einem Nextcloud-Upgrade-Schritt
je Hauptversion (8 Schritte ab Nextcloud 26, jeder setzt die Besitzer im
ganzen Nextcloud-Datenverzeichnis neu) sowie die Prüfungen. Bei einer Box mit
einigen hundert GB können das 1 bis 3 Stunden sein. Plan und `--check`
zeigen eine Schätzung.

Um das genauer zu wissen und abzukürzen:

* `--rehearse` führt das Setup einmal auf der Kopie aus, während die alte
  Box weiterläuft. Es installiert die Pakete vorab und misst, wie lange das
  Setup dauert. Cron und Sicherungen bleiben auf der neuen Maschine während
  des Probelaufs aus, ihre Dienste werden danach wieder angehalten und
  deaktiviert, damit ein Neustart sie nicht startet; jede spätere Kopie
  pausiert die Sicherungen dort erneut. Die
  Umschaltung kopiert die Daten erneut und führt das Setup noch einmal aus,
  dann ohne Paketinstallation.
* Oder den ganzen Umzug gegen einen Snapshot der neuen VM proben, die Zeit
  messen und den Snapshot zurücksetzen.

#### Datensicherheit

* Auf der alten Box wird nichts geändert oder gelöscht. Ihre Dienste werden
  nach Rückfrage nur angehalten und bis zum nächsten Neustart gesperrt.
  `--rollback` startet sie wieder (siehe „Zurück zur alten Box“).
* `rsync --delete` läuft nur in ein leeres Ziel oder in ein Ziel mit der
  Markierung eines früheren Laufs von derselben alten Box
  (`$STORAGE_ROOT/.migrate-to-2604` mit deren machine-id, Hostname und
  Datenpfad). Die Verzeichnisse `.rsync-partial` halten abgebrochene
  Dateien von ihrem eigentlichen Platz fern.
* Sobald das Setup auf der neuen Maschine gelaufen ist, hält das Werkzeug
  vor jeder weiteren Kopie deren Mail-in-a-Box-Dienste an, sperrt sie und
  wartet, bis dort nichts mehr `$STORAGE_ROOT` benutzt. Dateien, die eine
  solche Kopie ersetzt oder löscht, bleiben in
  `$STORAGE_ROOT/.migrate-overwritten/<Zeit>/` erhalten, und vor der ersten
  solchen Kopie fragt das Werkzeug auch mit `--yes` nach.
* Auf ein Sicherungsziel darf immer nur eine Box sichern. Die kopierte
  `backup/custom.yaml` wird auf der neuen Maschine durch `target: "off"`
  ersetzt, bis die Prüfungen bestanden sind (das Original liegt in
  `custom.yaml.migrate-saved`).
* Nicht kopiert werden `backup/cache/` (wird neu aufgebaut) und
  `owncloud-backup/` (Kopien früherer Nextcloud-Upgrades;
  `--with-owncloud-backup` kopiert sie mit). `--skip-local-backups` lässt auch
  `backup/encrypted/` weg.

#### Benutzerkennungen und Dateibesitzer

rsync überträgt die Besitzer als Zahlen (`--numeric-ids`). Die Systembenutzer
haben auf der neuen Maschine andere Kennungen (opendkim, spampd, postgrey,
`user-data` …), und die meisten gibt es vor dem Setup noch gar nicht. Eine
Zuordnung nach Namen beim Kopieren ist deshalb nicht möglich (und
`rsync --usermap` kann keinen ganzen Bereich um einen Versatz verschieben).
Stattdessen:

* Vor dem Setup wird jeder Besitzer, der nicht root ist und nicht schon mit
  gleichem Namen und gleicher Kennung auf der neuen Maschine existiert
  (`mail` = 8 und `www-data` = 33 sind fest), auf *alte Kennung + 2000000000*
  geparkt.
* Das Setup setzt seine eigenen Verzeichnisse nach Namen: `mail/mailboxes` und
  `mail/sieve` (mail), `mail/dkim` (opendkim), `mail/postgrey` (postgrey),
  `mail/spamassassin` (spampd), `mail/roundcube`, `owncloud` (www-data),
  `mail/users.sqlite` (root:www-data), `www` (Besitzer `user-data`).
* Nach dem Setup wird jeder geparkte Besitzer über seinen alten Namen (aus
  `/etc/passwd` und `/etc/group` der alten Box) auf die neue Kennung gesetzt.
  Gibt es den Namen auf der neuen Maschine nicht, behält der Besitzer seine
  alte Zahl nur, wenn sie dort unbenutzt ist; gehört sie einem anderen Konto
  (z. B. ein Administrator mit 1000 auf der alten Box und `ubuntu` = 1000 auf
  der neuen), bekommt root die Dateien. Beide Fälle werden gemeldet.

Die neue Maschine muss 32-Bit-Benutzerkennungen annehmen (VMs und Server tun
das, manche Container nicht; das Werkzeug prüft es).

#### Nicht übernommen

* Änderungen in `/etc` (z. B. zusätzliche Postfix-Tabellen wie
  `greylist_bypass_senders`, postgrey-Ausnahmelisten, SpamAssassin-Regeln,
  fail2ban-Jails, Cron-Jobs, Firewall-Regeln). Das alte `/etc` mit dem Stand
  der letzten Kopie liegt in `/root/migration/old-etc.tar.gz` (entpackt in
  `/root/migration/old-etc`), und `/root/migration/etc-report.txt` listet
  abweichende Postfix-Einstellungen, darin genannte Dateien und Dateien, die
  es nur auf der alten Box gibt.
* Von Hand installierte Nextcloud-Apps (sie liegen in
  `/usr/local/lib/owncloud/apps`, außerhalb der Daten). Das Werkzeug listet
  sie auf. Das Setup lässt den App-Store abgeschaltet
  (`'appstoreenabled' => false`).
* Mails in der Postfix-Warteschlange der alten Box (`/var/spool/postfix`).
  Vor dem Anhalten ruft das Werkzeug `postqueue -f` auf, wartet eine Minute
  und sichert die Liste in `/root/migration/old-postqueue.txt`. Warten noch
  Mails für die eigenen Postfächer der Box, fragt es nach (auch mit `--yes`)
  und zeigt, wie man sie später an die neue Box zustellt.
* Protokolle (`/var/log`, die Nutzungsberichte beginnen leer) und
  ACL-Einträge mit benannten Benutzern (in einer normalen Box keine).

#### Nach dem Umzug

##### 1. Vor der DNS-Umstellung testen

Die Zeile `<neue IP> <Hostname>` in die hosts-Datei des eigenen Rechners
eintragen (`/etc/hosts`; Windows: `C:\Windows\System32\drivers\etc\hosts`).
Dann `https://<Hostname>/admin` und `https://<Hostname>/mail` öffnen,
anmelden, eine Testmail über die neue Box senden (SMTP-Einlieferung) und eine
empfangen, Nextcloud prüfen (Dateien, Kontakte, Kalender). Die Zeile danach
wieder entfernen.

Webmail-Benutzer müssen sich neu anmelden: Das Setup gibt Roundcube einen
neuen Schlüssel. Spamfilter (Bayes) und Greylisting-Datenbank werden so
übernommen, wie sie sind.

##### 2. DNS umstellen

* **Zonen, die die Box selbst bedient** (NS `ns1`/`ns2.<Hostname>`, der
  Normalfall): beim Registrar die Glue-Einträge `ns1.<Hostname>` und
  `ns2.<Hostname>` auf die neuen IP-Adressen ändern. Die DS-Einträge bleiben
  gleich, die DNSSEC-Schlüssel werden übernommen.
  Resolver speichern NS- und Glue-Einträge bis zu deren TTL zwischen, die die
  TLD festlegt (z. B. 2 Tage bei .com, 1 Tag bei .de), und die Einträge
  dieser Zonen bis zu einem Tag (Mail-in-a-Box liefert sie mit TTL 86400 aus;
  das lässt sich vorab nicht senken). So lange antwortet der nsd-Dienst der
  alten Box weiter, mit den ALTEN IP-Adressen. Mit **1 bis 3 Tagen**
  (Glue-TTL plus 86400 Sekunden) ist also zu rechnen, in denen manche
  Absender und Clients noch die angehaltene alte Box versuchen. Mails gehen
  dabei nicht verloren: Die Absender halten sie zurück und versuchen es
  erneut, meist 4 bis 5 Tage lang; manche melden ihrem Benutzer nach einigen
  Stunden eine Verzögerung, wenige geben früher auf.
* **Kürzer**: den nsd-Dienst der alten Box ebenfalls die neuen IP-Adressen
  ausliefern lassen:

		/root/mailinabox/tools/migrate-to-2604.sh --push-zones-to-old

  Das kopiert `/etc/nsd/zones/*.signed` von der neuen Box nach
  `/etc/nsd/zones` der alten Box (deren eigene Dateien bleiben dort in
  `/root/migrate-to-2604-nsd-orig` erhalten) und führt dort
  `systemctl reload nsd` aus. Das ist die einzige bewusste Änderung an
  Dateien der alten Box. `--rollback` legt die alten Dateien zurück (von
  Hand auf der alten Box: `cp -a /root/migrate-to-2604-nsd-orig/. /etc/nsd/zones/`
  und `systemctl reload nsd`). Dann bleiben nur die zwischengespeicherten
  Einträge von bis zu einem Tag.
* **Zonen mit externem DNS**: die A/AAAA-Einträge des Hostnamens (und die
  übrigen, die die Admin-Oberfläche unter System > External DNS nennt) auf
  die neuen IP-Adressen ändern. Sie wirken innerhalb ihrer TTL.
* **Eigene sekundäre Nameserver** (System > Custom DNS,
  `_secondary_nameserver`): beim DNS-Anbieter die primäre IP-Adresse
  (Master) auf die neue IP ändern. Bis dahin holt er die Zonen von der alten
  IP; ist die alte Box abgeschaltet, liefert er die alten Zonen noch bis zu
  14 Tage aus (SOA-Expire). Das Werkzeug listet sie auf.
* **PTR** der neuen IP-Adressen auf den Hostnamen, falls noch nicht
  geschehen.
* **MX** ändert sich nicht, solange der Hostname gleich bleibt.
  SPF-Einträge mit festen `ip4:`/`ip6:`-Angaben müssen angepasst werden.

##### 3. Danach

* **Sicherungen** laufen auf der neuen Box mit demselben `secret_key.txt`
  und Ziel weiter, sobald die Prüfungen bestanden sind (oder nach
  `--finish`). Die Dienste der alten Box nie wieder starten, sonst schreiben
  zwei Boxen in ein Sicherungsziel.
* **Die alte Box** bleibt angehalten; ihre Dienste sind bis zum nächsten
  Neustart gesperrt. Nicht neu starten, solange DNS noch auf sie zeigen
  kann. `--check-old` zeigt, ob dort wieder etwas läuft. Abschalten, sobald
  DNS umgestellt ist (Glue-TTL plus ein Tag).
* `/root/migration/etc-report.txt` durchsehen und die noch benötigten
  Anpassungen von Hand nachziehen.
* `/root/migration` löschen, wenn es nicht mehr gebraucht wird (es enthält
  die alten Passwort-Hashes und Schlüssel), ebenso
  `$STORAGE_ROOT/.migrate-overwritten`, falls vorhanden.

#### Zurück zur alten Box

`/root/mailinabox/tools/migrate-to-2604.sh --rollback` kehrt zur alten Box
zurück. Gedacht ist es für den Fall, dass die neue Box nicht funktioniert und
die alte wieder laufen soll, am besten vor der DNS-Umstellung.

Es pausiert die Sicherungen auf der neuen Maschine, hält deren
Mail-in-a-Box-Dienste an und deaktiviert sie (der nächste Versuch aktiviert
sie wieder) und beendet nach einer Minute eine Sicherung, die dort noch
läuft. Es legt die eigenen Zonendateien der alten Box zurück, falls
`--push-zones-to-old` lief, setzt `virtual_transport` auf der alten Box
zurück (auf den Mail-in-a-Box-Standard `lmtp:[127.0.0.1]:10025`, falls der
gesicherte Wert auf die neue Maschine zeigt) und hält ein dort von Hand gestartetes Postfix an (der Hinweis zur
Warteschlange beim Anhalten), hebt die Sperre der Dienste auf der alten Box
auf und startet sie wieder.

* Wurde DNS schon umgestellt, die Glue- oder A/AAAA-Einträge zurückändern.
* Mails, die nach einer DNS-Umstellung auf der neuen Box angekommen sind,
  werden **nicht** zur alten Box zurückkopiert. Der nächste Versuch bewahrt
  die Dateien, die seine Kopie ersetzt, in
  `$STORAGE_ROOT/.migrate-overwritten/` auf; einzelne Ordner lassen sich von
  dort mit `doveadm import` übernehmen.
* Für einen neuen Versuch den Umzugsbefehl einfach erneut aufrufen; er
  kopiert die Daten noch einmal und macht weiter.
* War die neue Box schon eine Weile in Betrieb, nicht mehr zurückkehren:
  Die Mails, die sie empfangen hat, fehlten sonst auf der alten Box.

#### Aus einer Sicherung statt über SSH

	/root/mailinabox/tools/migrate-to-2604.sh --from-backup /mnt/alte-sicherung/encrypted \
	  --backup-key /root/secret_key.txt [--hostname box.example.com]

Das spielt die duplicity-Sicherung nach `/home/user-data` ein
(`--storage-root` für einen anderen Pfad; es muss der Pfad der alten Box sein,
Nextcloud speichert ihn), legt `secret_key.txt` zurück und führt dann
prepare, setup, ownership und verify aus. Der Speicherbenutzer wird vor dem
Einspielen angelegt, damit seine Dateien seine neue Kennung bekommen. Der
Hostname wird aus dem eingespielten TLS-Zertifikat gelesen, sofern
`--hostname` fehlt. Grenzen: Eine Sicherung enthält weder `backup/` (also
kein `custom.yaml`; das Sicherungsziel neu einstellen) noch das alte `/etc`,
Z-Push oder munin, und es gibt keine Liste der alten Benutzerkennungen (das
Setup setzt die Dienstverzeichnisse, die Dateien und Punktdateien des
Speicherbenutzers werden gezielt korrigiert, und jeder andere Besitzer mit
einer Kennung ab 1000 wird in `/root/migration/foreign-owners.txt` gemeldet).
Eine entfernte Sicherungs-URL (`s3://`, `b2://`, `rsync://` …) wird an
duplicity weitergereicht; die Zugangsdaten gehören in die Umgebung. Klappt
das nicht, von Hand einspielen und das Setup starten:

	sudo apt-get install duplicity
	sudo useradd -m user-data
	sudo PASSPHRASE="$(head -n 1 secret_key.txt | tr -d '\r')" duplicity restore --force file:///pfad/zu/encrypted /home/user-data
	sudo install -D -m 600 secret_key.txt /home/user-data/backup/secret_key.txt
	curl -s https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/setup/bootstrap.sh | sudo TAG=main bash
	sudo chown -R user-data:user-data /home/user-data/www && sudo chown user-data:user-data /home/user-data /home/user-data/mailinabox.version
