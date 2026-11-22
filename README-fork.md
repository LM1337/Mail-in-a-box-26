Mail-in-a-Box for Ubuntu 26.04 (fork)
=====================================

This is a fork of [Mail-in-a-Box](https://github.com/mail-in-a-box/mailinabox)
that runs on **Ubuntu 26.04 LTS**. It is upstream PR #2603 (the Ubuntu 26.04
port) merged with upstream v78, plus the fixes listed in
[CHANGELOG-fork.md](CHANGELOG-fork.md). Each fixed bug is documented with
symptom, cause and affected versions in [BUGS-fork.md](BUGS-fork.md). The
end-to-end tests of each release and their results are in
[TESTING-fork.md](TESTING-fork.md).
Upstream's own history is in
[CHANGELOG.md](CHANGELOG.md), its documentation in [README-upstream.md](README-upstream.md) and
on <https://mailinabox.email>.

Main differences from upstream v78 (Ubuntu 22.04):

* Dovecot 2.4, Postfix and the rest of the mail stack from Ubuntu 26.04.
* PHP 8.5 from Ubuntu. packages.sury.org is pinned to what Ubuntu lacks
  (php8.2 for the Nextcloud upgrade chain, php8.5-imap, php-common). Some of
  PHP's packages are in universe, see "Security updates and Ubuntu Pro".
* Nextcloud 34.0.6. Existing installations are upgraded step by step from
  Nextcloud 26; older versions are refused.
* Roundcube 1.7.6, Z-Push 2.7.7.
* Nextcloud users only see and share with their own mail domain, admins with
  everyone (`NEXTCLOUD_SHARE_SCOPE`, see below).
* fail2ban: repeat offenders get longer bans, slow jails catch slow attacks,
  an allowlist for own networks, a report of password spraying, the reason
  of each ban, and Nextcloud's own login throttle in the control panel (see
  "Intrusion detection and prevention" below).

Diese Abspaltung (Fork) von Mail-in-a-Box läuft auf Ubuntu 26.04 LTS. Die
Unterschiede zu upstream v78 stehen oben und in CHANGELOG-fork.md, die behobenen Fehler einzeln in BUGS-fork.md.

Versioning / Versionierung
--------------------------

Release tags look like `v78-r2604.0-rc3`: `v78` is the upstream release the
fork is based on (not a version number of its own), `r2604` the fork line for
Ubuntu 26.04, `.0`, `.1`, … the fork's own releases on that base, and `-rcN`
a release candidate. The fork never uses an upstream number before upstream
has released it: when it takes over upstream v79, the counter starts again
with `v79-r2604.0`. The `v<upstream>` prefix stays because the tools compare
Mail-in-a-Box versions numerically and `git describe` shows which upstream
code a box runs. Details: [CONTRIBUTING.md](CONTRIBUTING.md#versioning).

Release-Tags sehen so aus: `v78-r2604.0-rc3`. `v78` ist das Upstream-Release,
auf dem der Fork beruht (keine eigene Versionsnummer), `r2604` die Linie für
Ubuntu 26.04, `.0`, `.1` … die eigenen Releases auf dieser Basis und `-rcN`
ein Release Candidate. Eine Upstream-Nummer verwendet der Fork erst, wenn
Upstream sie veröffentlicht hat: Mit der Übernahme von upstream v79 beginnt
der Zähler neu bei `v79-r2604.0`. Das Präfix `v<upstream>` bleibt, weil die
Werkzeuge Mail-in-a-Box-Versionen als Zahlen vergleichen und `git describe`
zeigt, welcher Upstream-Stand auf einer Box läuft.

Installation
------------

On a fresh Ubuntu 26.04 machine:

	sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/setup/bootstrap.sh)"

The environment variables `SOURCE` and `TAG` choose another repository or
tag. They must be given to `bash` after `sudo` (sudo does not pass on the
environment, and `TAG=main curl ...` only sets it for curl). Without `TAG`,
bootstrap.sh installs the current release tag. `TAG=main` installs the
development state of the branch `main`, for testing only (`TAG` may also be
another branch or a full commit id of 40 hex digits, as for the in-place
and migration tools):

	sudo TAG=main bash -c "$(curl -fsSL https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/setup/bootstrap.sh)"

Setup can run without questions with `NONINTERACTIVE=1` and
`PRIMARY_HOSTNAME`, `PUBLIC_IP`, `PUBLIC_IPV6`, `EMAIL_ADDR`/`EMAIL_PW` (first
user, only on an empty box), given the same way.

Upstream's form `curl ... | sudo bash` does not work for an interactive
setup on Ubuntu 26.04: its sudo (sudo-rs) stops setup's dialog boxes when
the script comes through a pipe, and setup hangs without showing anything.
bootstrap.sh then stops with the command above. The pipe still works with
`NONINTERACTIVE=1`, and as root without sudo.

Auf einer frischen Ubuntu-26.04-Maschine genügt der erste Befehl oben. Mit
`SOURCE` und `TAG` lassen sich ein anderes Repository oder ein anderer Tag
wählen. Die Variablen gehören hinter `sudo` vor `bash` (sudo reicht die
Umgebung nicht weiter, und `TAG=main curl ...` gilt nur für curl). Ohne `TAG`
installiert bootstrap.sh den aktuellen Release-Tag; `TAG=main` holt den
Entwicklungsstand des Zweigs `main`, nur zum Testen:
`sudo TAG=main bash -c "$(curl -fsSL .../setup/bootstrap.sh)"` (`TAG` kann
auch ein anderer Zweig oder eine vollständige Commit-Kennung aus 40
Hex-Ziffern sein, wie bei den Werkzeugen für das Upgrade an Ort und Stelle
und den Umzug).

Die Upstream-Form `curl ... | sudo bash` taugt unter Ubuntu 26.04 nicht für
ein Setup mit Rückfragen: Dessen sudo (sudo-rs) hält die Dialogfenster des
Setups an, wenn das Skript über eine Pipe kommt, und das Setup hängt, ohne
etwas anzuzeigen. bootstrap.sh bricht dann mit dem Befehl oben ab. Mit
`NONINTERACTIVE=1` und als root ohne sudo funktioniert die Pipe weiterhin.


Updating the fork / Fork aktualisieren
--------------------------------------

### English

A box that runs this fork is updated like upstream Mail-in-a-Box: run the
bootstrap command from [Installation](#installation) again. It brings
`/root/mailinabox` to the current release tag and runs setup. Read the
upgrade note of the new release in [CHANGELOG-fork.md](CHANGELOG-fork.md)
first. The in-place tool is not needed for this. Setup shows some of its
dialog boxes again (the host name, the public IP address when it differs
from what the Internet sees; from rc7 on no longer the welcome text of a new
installation); Enter keeps the current values.

Files changed by hand in `/root/mailinabox` (a hotfix, for example) must be
put back before the update, or bootstrap.sh stops with "Update failed. Did
you modify something in /root/mailinabox?": `git -C /root/mailinabox status
--short` lists them, `git -C /root/mailinabox checkout -- FILE` puts one
back. Setup downloads some components from GitHub again when the release
changes them (Z-Push on the first update after rc7, as the fork's changes to
it are new), so the box must reach GitHub during the update. Check that
first:

	curl -fsSIL https://github.com/Z-Hub/Z-Push/archive/refs/tags/2.7.7.zip > /dev/null && echo OK

If such a download fails, setup stops in the middle of the update (for
Z-Push after Nextcloud's step, before PHP-FPM and the control panel are
restarted; the box keeps the old Z-Push). Run setup again (`sudo mailinabox`) once
GitHub is reachable: it installs Z-Push and finishes the update.

From v78-r2604.2 on, setup stops at its start, before it changes anything,
when a place in `$STORAGE_ROOT` that it writes as root is a symbolic link:
`mail` itself, `mail/users.sqlite`, `mail/roundcube/roundcube.sqlite`,
and the postgrey, DKIM and SpamAssassin directories in `mail`; also when
one of the two databases has a second hard link or `mailinabox.version`
is not a regular file. Another account (www-data, the storage user) could
have put such a link there (B147). It lists them and says what to do: a
mail store on another disk belongs at `$STORAGE_ROOT/mail` as a bind
mount, not as a link. `$STORAGE_ROOT` itself may be a link in a directory
of root's own, such as `/home/user-data`.

Boxes installed with rc1 to rc3 (with bootstrap.sh or with the in-place
tool) were cloned from the fork's previous home. bootstrap.sh stops on them
with "is a checkout of ..., not of https://github.com/LM1337/Mail-in-a-box-26".
Point the checkout to GitHub once, then run the bootstrap command:

	sudo git -C /root/mailinabox remote set-url origin https://github.com/LM1337/Mail-in-a-box-26
	sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/setup/bootstrap.sh)"

The status checks of rc1 to rc3 look for new releases at the previous home;
they may keep reporting such a box as up to date, so check the
[releases](https://github.com/LM1337/Mail-in-a-box-26/releases) yourself.

Such a checkout also keeps the release tags of the previous home:
`git -C /root/mailinabox tag` lists `v78-r2604.0-rc3` (and rc1, rc2 if they
were fetched) with other commit ids than on GitHub, because the history was
rewritten for publication. Updates are not affected (bootstrap.sh fetches only
the tag it installs, with `--force`). To clean up, delete the old tags:

	sudo git -C /root/mailinabox tag -d v78-r2604.0-rc1 v78-r2604.0-rc2 v78-r2604.0-rc3

("not found" for a tag that is not there is fine). Do not use
`git fetch --tags` for this: the checkout is shallow, and it would download
the history behind every upstream tag of the repository.

One case did affect an update up to v78-r2604.4: a checkout whose current
commit carries a local tag with the name of the release being installed, but
another commit than on GitHub (an old pre-release or a mirror's tag of that
name). bootstrap.sh compared the release name with `git describe` and, when
they matched, fetched nothing: setup then ran on the old code and still
ended with exit code 0. From v78-r2604.5 on, bootstrap.sh also asks the
source for the commit of the tag (`git ls-remote`) and fetches the release
when it is not the checkout's commit ("... is at a local tag ..., but ... has
... on another commit"); if the source cannot be asked, it says so and uses
the checkout as it is. The bootstrap command loads bootstrap.sh from the
branch main, so every update with it does this check from the release of
v78-r2604.5 on. To check by hand that the checkout is the release and its
commit is GitHub's (here for v78-r2604.5; use the name of the release you
install):

	sudo git -C /root/mailinabox describe --always
	sudo git -C /root/mailinabox rev-parse HEAD
	git ls-remote https://github.com/LM1337/Mail-in-a-box-26 'refs/tags/v78-r2604.5^{}'

`describe` must print the release name, and the two commit ids must be
the same. If they are not, delete the local tag and run the bootstrap
command again:

	sudo git -C /root/mailinabox tag -d v78-r2604.5
	sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/setup/bootstrap.sh)"

**Checks around the update** (rc7 and later, `tools/update-check.sh`, as
root; through `curl ... | sudo bash -s -- STEP` without a checkout). Before
the update, `before` records the state of the box (version, services,
status checks, Postfix and Dovecot settings, Nextcloud, Munin, Docker,
crontabs, listening ports, ...) and runs `tests/fork/log-audit.sh` as a
baseline; `backup` runs a Mail-in-a-Box backup and puts an encrypted archive
of `/etc`, `/root/mailinabox`, the crontabs, Z-Push, Munin, Nextcloud's code
and the Docker stacks you name (`--docker-dir`, `--docker-volume`,
`--postgres` for a pg_dump) next to the backups (rsync targets; verified by
checksum) or in `/root/update-check`. After the update, `after` records the
state again and lists each change as EXPECTED (announced by the releases in
between, `tools/expected-changes/`; for an update to a branch or commit
after the newest release also `unreleased.txt` there) or UNEXPECTED (a
Postfix or Dovecot setting that only the newer record has, because a newer
version of the tool records it, is listed as "newly recorded (not judged)"
and counted in the RESULT line), and runs the log audit
against the baseline: only new message classes count (`--internet` accepts
the usual noise of a public box). The lists cover updates of this fork on
one Ubuntu release: after an in-place upgrade or a migration from upstream
Mail-in-a-Box, `after` lists the changes without judging them ("RESULT:
NOT JUDGED"). `mailcheck` sends a marked test mail to
an address of another provider that sends it back (forward or automatic
answer; `--probe ADDRESS` or `PROBE_ADDRESS=` in `/etc/mailinabox.conf`, which
setup keeps from rc7 on) and
waits for it to come back over port 25: outbound, inbound, spam filter,
folder and storage in one round trip. Without a probe address it is skipped.

	sudo /root/mailinabox/tools/update-check.sh before
	sudo /root/mailinabox/tools/update-check.sh backup
	(the update)
	sudo /root/mailinabox/tools/update-check.sh after
	sudo /root/mailinabox/tools/update-check.sh mailcheck --probe probe@example.net

A box on rc6 or earlier has no copy of the tool yet. Run `before` and
`backup` through curl (the tool fetches its helpers from the branch main),
name your Docker stacks if there are any, then update, then run `after` and
`mailcheck` from the new checkout:

	curl -fsSL https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/tools/update-check.sh | sudo bash -s -- before
	curl -fsSL https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/tools/update-check.sh \
	  | sudo bash -s -- backup --docker-dir /opt/myapp --docker-volume myapp_data --postgres myapp-db
	sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/setup/bootstrap.sh)"
	sudo /root/mailinabox/tools/update-check.sh after
	sudo /root/mailinabox/tools/update-check.sh mailcheck --probe probe@example.net

`backup` stops mail for the run of the Mail-in-a-Box backup (as the
nightly one does; in the tests about 15 seconds for an incremental one).
It takes the target and the passphrase only from a `$STORAGE_ROOT/backup`
of root's own (owned by root, not writable by group or others, as setup
makes it) and otherwise stops before anything else; the tool uses a
checkout only when every file in it is root's own. Leave the backup settings alone between `before` and `after`: a changed
target shows up as a change of the status checks. What `after` says:
"RESULT: OK" (exit code 0) when every change is EXPECTED and the log audit
found no new message class; otherwise it names the unexpected changes
(`after/changes.txt`) and the new classes (`after/log-audit.txt`), exit code
1. "RESULT: INCOMPLETE" (exit code 2): nothing unexpected, but the log audit
could not run. After a release upgrade or the first update from upstream:
"RESULT: NOT JUDGED" (exit code 3, or 1 with a new message class). Look at each UNEXPECTED
line; the mail check answers "RESULT: OK" or "RESULT: FAILED" with the
step that failed.

Everything lands in `/root/update-check/<stamp>/` (only root can read it).
`--help` lists the options.
At the end of a setup run on an existing box (not a first install, not
the run of the in-place upgrade or the migration tool), setup points to
the tool: when the newest record has a `before` but no `after`, it prints
the `after` and `mailcheck` commands for that record, otherwise a short
tip. It does not stop.

**From rc7 to v78-r2604.0, step by step.** The steps of the release's
upgrade note, in the order in which they were tested (TESTING-fork.md,
"v78-r2604.0", T5b Part A, on a copy with only the hotfix of
`management/backup.py`; putting back `conf/nginx-alldomains.conf` as well
was tested in the update test after rc7, at `958f2b9`). If you use Docker
stacks next to the box, name them in `backup` as shown above.

	curl -fsSIL https://github.com/Z-Hub/Z-Push/archive/refs/tags/2.7.7.zip > /dev/null && echo OK
	sudo /root/mailinabox/tools/update-check.sh before
	sudo /root/mailinabox/tools/update-check.sh backup
	sudo git -C /root/mailinabox status --short
	sudo git -C /root/mailinabox checkout -- management/backup.py conf/nginx-alldomains.conf
	sudo git -C /root/mailinabox status --short
	sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/setup/bootstrap.sh)"
	sudo /root/mailinabox/tools/update-check.sh after
	sudo /root/mailinabox/tools/update-check.sh mailcheck

The first command must print `OK`. Put back every file that the first
`status --short` lists (the two named above are the hotfixes of rc7; leave
out a file that is not listed); the second `status --short` must print
nothing. Setup asks for the host name and the public IP addresses: Enter
keeps them. `after` should end with "RESULT: OK": it judges the changes by
`tools/expected-changes/v78-r2604.0.txt` (and `any.txt`) and adds
`tests/fork/log-audit-allow-from-rc7.txt` to the log audit by itself
(the old Z-Push had no mark of the fork's changes). In the test, the
changes part said "RESULT: OK - 0 unexpected, 8 expected changes", and the
log audit named two message classes, which the lists of the release accept:
the auth-worker note at setup's Dovecot reload, and Roundcube's CardDAV
migration race ("UNIQUE constraint failed: carddav_migrations.filename") of
two first logins in the same second on a box whose Roundcube was not used
since rc7's setup. Look at any other class it names (`after/log-audit.txt`).
`mailcheck` needs a
probe address (`--probe ADDRESS` or `PROBE_ADDRESS=` in
`/etc/mailinabox.conf`); without one it is skipped.

Right after the update:

* **Allowlist your own networks.** From rc4 on, adaptive banning and the
  slow mail jails are on as soon as setup has finished, with an empty
  allowlist on a box that had none (an allowlist saved under rc4 or later
  stays); there is nothing to turn on. Put the networks your users work
  from (office, VPN) on the allowlist right away, under System > Intrusion
  Protection or with
  `sudo /root/mailinabox/management/fail2ban_admin.py --allow 192.0.2.0/24`.
  Otherwise a single phone with an old password can get the whole office
  banned from the mail ports, for longer each time (up to a week). See
  [Intrusion detection and prevention](#intrusion-protection-adaptive-fail2ban--schutz-vor-anmeldeangriffen).
* **The nightly job moves.** Setup picks a new random minute between 01:00
  and 01:59 (system time) for the nightly backup and status checks on every
  run, as upstream does (`/etc/cron.d/mailinabox-nightly`). Check the time
  there before you plan the next update or upgrade.
* Check that the services are enabled: `systemctl is-enabled dovecot postfix`
  must say `enabled` twice. A box upgraded in place with rc3 had Dovecot
  disabled (B67); setup of later releases enables it again.
* **Munin mails the administrator.** From rc6 on, Munin's alerts work:
  each change of state of a watched value (warning, critical, back to ok)
  is mailed to administrator@ of the box's name. Make sure that address
  reaches someone. From rc7 on, the control panel sets another
  address, critical only, or off (see [Munin alerts](#munin-alerts--warnungen-von-munin);
  since v78-r2604.5 under System > Notifications).
* **fail2ban after the log rotation.** From rc6 on, Dovecot logs through
  syslog, and rsyslog writes its lines to `mail.log` (B85):
  `doveconf -h log_path` must say `syslog`. fail2ban's Dovecot jails then
  see failed IMAP, POP3 and ManageSieve logins also after the weekly
  rotation of `mail.log`.
* **ActiveSync contacts (B99, B128).** From rc7 on, new users get no
  example contact in Nextcloud. Users created before keep it. On rc7 the
  contact sync of their phones over ActiveSync fails until it is deleted (in
  Nextcloud's Contacts, the contact marked "This is an example contact");
  after rc7 Z-Push syncs it like any other contact (B128), and it can stay
  or be deleted.

### Deutsch

Eine Box mit diesem Fork wird wie upstream Mail-in-a-Box aktualisiert: den
Bootstrap-Befehl aus [Installation](#installation) noch einmal aufrufen. Er
bringt `/root/mailinabox` auf den aktuellen Release-Tag und lässt setup
laufen. Vorher den Upgrade-Hinweis des neuen Releases in
[CHANGELOG-fork.md](CHANGELOG-fork.md) lesen. Das Werkzeug für das Upgrade
an Ort und Stelle wird dafür nicht gebraucht. Das Setup zeigt einige seiner
Dialogfenster noch einmal (den Hostnamen und die öffentliche IP-Adresse,
wenn sie von der abweicht, die das Internet sieht; ab rc7 nicht mehr den
Begrüßungstext einer neuen Installation); Enter behält die bisherigen Werte.

Von Hand geänderte Dateien in `/root/mailinabox` (etwa ein Hotfix) müssen vor
dem Update zurückgesetzt werden, sonst bricht bootstrap.sh mit „Update
failed. Did you modify something in /root/mailinabox?“ ab: `git -C
/root/mailinabox status --short` listet sie, `git -C /root/mailinabox
checkout -- DATEI` setzt eine zurück. Setup lädt manche Bestandteile wieder
von GitHub, wenn das Release sie ändert (Z-Push beim ersten Update nach rc7,
weil die Änderungen des Forks daran neu sind); die Box muss GitHub während
des Updates also erreichen. Das vorher prüfen:

	curl -fsSIL https://github.com/Z-Hub/Z-Push/archive/refs/tags/2.7.7.zip > /dev/null && echo OK

Schlägt ein solcher Download fehl, hält setup mitten im Update an (bei
Z-Push nach dem Schritt für Nextcloud, bevor PHP-FPM und das Control Panel
neu gestartet werden; die Box behält das alte Z-Push). Sobald GitHub erreichbar
ist, setup noch einmal aufrufen (`sudo mailinabox`): Es installiert Z-Push
und schließt das Update ab.

Ab v78-r2604.2 bricht setup gleich zu Beginn ab, bevor es etwas ändert,
wenn eine Stelle in `$STORAGE_ROOT`, die es als root beschreibt, ein
symbolischer Link ist: `mail` selbst, `mail/users.sqlite`,
`mail/roundcube/roundcube.sqlite` und die Verzeichnisse von postgrey, DKIM
und SpamAssassin in `mail`; ebenso, wenn eine der beiden Datenbanken einen
zweiten harten Link hat oder `mailinabox.version` keine gewöhnliche Datei
ist. Ein anderes Konto (www-data, der Speicherbenutzer) könnte einen
solchen Link dort angelegt haben (B147). Setup zählt die Stellen auf und
sagt, was zu tun ist: Ein Mailspeicher auf einer anderen Platte gehört
per Bind-Mount nach `$STORAGE_ROOT/mail`, nicht per Link.
`$STORAGE_ROOT` selbst darf ein Link in einem Verzeichnis sein, das nur
root gehört, etwa `/home/user-data`.

Boxen, die mit rc1 bis rc3 installiert wurden (mit bootstrap.sh oder mit dem
In-place-Werkzeug), wurden von der früheren Adresse des Forks geklont.
bootstrap.sh hält bei ihnen mit „is a checkout of ..., not of
https://github.com/LM1337/Mail-in-a-box-26“ an. Den Checkout einmal auf
GitHub umstellen, danach den Bootstrap-Befehl aufrufen:

	sudo git -C /root/mailinabox remote set-url origin https://github.com/LM1337/Mail-in-a-box-26
	sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/setup/bootstrap.sh)"

Die Statusprüfungen von rc1 bis rc3 suchen neue Releases unter der früheren
Adresse; sie melden eine solche Box womöglich weiter als aktuell, deshalb die
[Releases](https://github.com/LM1337/Mail-in-a-box-26/releases) selbst
prüfen.

Ein solcher Checkout behält auch die Release-Tags der früheren Adresse:
`git -C /root/mailinabox tag` zeigt `v78-r2604.0-rc3` (und rc1, rc2, falls
sie geholt wurden) mit anderen Commit-IDs als auf GitHub, weil die Historie
für die Veröffentlichung neu geschrieben wurde. Auf Updates wirkt sich das
nicht aus (bootstrap.sh holt nur den Tag, den es installiert, mit `--force`).
Zum Aufräumen die alten Tags löschen:

	sudo git -C /root/mailinabox tag -d v78-r2604.0-rc1 v78-r2604.0-rc2 v78-r2604.0-rc3

(„not found“ für einen Tag, den es nicht gibt, ist in Ordnung). Nicht
`git fetch --tags` dafür nehmen: Der Checkout ist flach (shallow) und würde
die Historie hinter jedem Upstream-Tag des Repositorys herunterladen.

Ein Fall wirkte sich bis v78-r2604.4 doch auf ein Update aus: ein Checkout,
dessen aktueller Commit einen lokalen Tag mit dem Namen des zu
installierenden Release trägt, aber auf einen anderen Commit als auf GitHub
(ein altes Vorab-Release oder der Tag eines Spiegels mit diesem Namen).
bootstrap.sh verglich den Release-Namen mit `git describe` und holte bei
Gleichheit nichts: Setup lief dann mit dem alten Code und endete trotzdem
mit Exit-Code 0. Ab v78-r2604.5 fragt bootstrap.sh zusätzlich die Quelle
nach dem Commit des Tags (`git ls-remote`) und holt das Release, wenn es
nicht der Commit des Checkouts ist („... is at a local tag ..., but ... has
... on another commit“); ist die Quelle nicht erreichbar, sagt es das und
nimmt den Checkout, wie er ist. Der Bootstrap-Befehl lädt bootstrap.sh
aus dem Zweig main, also macht jedes Update damit diese Prüfung, sobald
v78-r2604.5 veröffentlicht ist. Von Hand prüfen, dass der Checkout das
Release ist und sein Commit der von GitHub (hier für v78-r2604.5; den Namen
des installierten Release einsetzen):

	sudo git -C /root/mailinabox describe --always
	sudo git -C /root/mailinabox rev-parse HEAD
	git ls-remote https://github.com/LM1337/Mail-in-a-box-26 'refs/tags/v78-r2604.5^{}'

`describe` muss den Release-Namen ausgeben, und die beiden Commit-IDs
müssen gleich sein. Sonst den lokalen Tag löschen und den
Bootstrap-Befehl noch einmal ausführen:

	sudo git -C /root/mailinabox tag -d v78-r2604.5
	sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/setup/bootstrap.sh)"

**Prüfungen rund um das Update** (ab rc7, `tools/update-check.sh`, als
root; ohne Checkout über `curl ... | sudo bash -s -- SCHRITT`). Vor dem
Update hält `before` den Zustand der Box fest (Version, Dienste,
Statusprüfungen, Einstellungen von Postfix und Dovecot, Nextcloud, Munin,
Docker, Crontabs, offene Ports, ...) und lässt `tests/fork/log-audit.sh` als
Vergleichsbasis laufen; `backup` macht eine Mail-in-a-Box-Sicherung und legt
ein verschlüsseltes Archiv von `/etc`, `/root/mailinabox`, den Crontabs,
Z-Push, Munin, dem Code von Nextcloud und den genannten Docker-Stacks
(`--docker-dir`, `--docker-volume`, `--postgres` für einen pg_dump) neben die
Sicherungen (rsync-Ziele; per Prüfsumme kontrolliert) oder nach
`/root/update-check`. Nach dem Update hält `after` den Zustand erneut fest,
führt jede Änderung als EXPECTED (von den Releases dazwischen angekündigt,
`tools/expected-changes/`; bei einem Update auf einen Zweig oder Commit nach
dem neuesten Release auch `unreleased.txt` dort) oder UNEXPECTED auf (eine
Postfix- oder Dovecot-Einstellung, die nur die neuere Aufzeichnung hat, weil
eine neuere Version des Werkzeugs sie aufzeichnet, steht unter „newly
recorded (not judged)“ und wird in der RESULT-Zeile mitgezählt) und lässt das Log-Audit gegen
die Vergleichsbasis laufen: Es zählen nur neue Meldungsklassen
(`--internet` nimmt das übliche Rauschen einer öffentlichen Box hin). Die
Listen decken Updates dieses Forks auf einem Ubuntu-Release ab: Nach einem
In-place-Upgrade oder einem Umzug von Upstream-Mail-in-a-Box führt `after`
die Änderungen nur auf, ohne sie zu bewerten („RESULT: NOT JUDGED“).
`mailcheck` schickt eine markierte Testmail an eine Adresse bei einem
anderen Anbieter, die sie zurückschickt (Weiterleitung oder automatische
Antwort; `--probe ADRESSE` oder `PROBE_ADDRESS=` in `/etc/mailinabox.conf`,
das Setup ab rc7 dort stehen lässt),
und wartet, bis sie über Port 25 zurückkommt: Versand, Empfang,
Spamfilter, Ordner und Ablage in einem Durchgang. Ohne Probe-Adresse wird
der Schritt übersprungen.

	sudo /root/mailinabox/tools/update-check.sh before
	sudo /root/mailinabox/tools/update-check.sh backup
	(das Update)
	sudo /root/mailinabox/tools/update-check.sh after
	sudo /root/mailinabox/tools/update-check.sh mailcheck --probe probe@example.net

Eine Box mit rc6 oder älter hat das Werkzeug noch nicht. Dann `before` und
`backup` über curl aufrufen (das Werkzeug holt seine Hilfsdateien vom Zweig
main), dabei die eigenen Docker-Stacks nennen, falls es welche gibt, dann
aktualisieren, dann `after` und `mailcheck` aus dem neuen Checkout:

	curl -fsSL https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/tools/update-check.sh | sudo bash -s -- before
	curl -fsSL https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/tools/update-check.sh \
	  | sudo bash -s -- backup --docker-dir /opt/myapp --docker-volume myapp_data --postgres myapp-db
	sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/setup/bootstrap.sh)"
	sudo /root/mailinabox/tools/update-check.sh after
	sudo /root/mailinabox/tools/update-check.sh mailcheck --probe probe@example.net

`backup` hält die Mail für den Lauf der Mail-in-a-Box-Sicherung an (wie die
nächtliche; in den Tests etwa 15 Sekunden für eine inkrementelle). Ziel und
Passphrase nimmt es nur aus einem `$STORAGE_ROOT/backup`, das root gehört
und weder für die Gruppe noch für andere beschreibbar ist (wie Setup es
anlegt), sonst bricht es vor allem anderen ab; einen Checkout nimmt das
Werkzeug nur, wenn jede Datei darin root gehört. Die
Einstellungen der Sicherung zwischen `before` und `after` nicht ändern: Ein
geändertes Ziel erscheint als Änderung der Statusprüfungen. Was `after`
meldet: „RESULT: OK“ (Exit-Code 0), wenn jede Änderung EXPECTED ist und das
Log-Audit keine neue Meldungsklasse gefunden hat; sonst nennt es die
unerwarteten Änderungen (`after/changes.txt`) und die neuen Klassen
(`after/log-audit.txt`), Exit-Code 1. „RESULT: INCOMPLETE“ (Exit-Code 2):
nichts Unerwartetes, aber das Log-Audit konnte nicht laufen. Nach einem
Release-Upgrade oder dem ersten Update von Upstream: „RESULT: NOT JUDGED“
(Exit-Code 3, oder 1 bei einer neuen Meldungsklasse). Jede
UNEXPECTED-Zeile ansehen; die Mailprüfung
antwortet mit „RESULT: OK“ oder „RESULT: FAILED“ und dem Schritt, der
scheiterte.

Alles landet in `/root/update-check/<Zeitstempel>/` (nur für root lesbar).
`--help` zeigt die Optionen.
Am Ende eines Setup-Laufs auf einer bestehenden Box (keine
Neuinstallation, nicht der Lauf des In-place-Upgrades oder des
Umzugswerkzeugs) weist setup auf das Werkzeug hin: Hat der neueste Eintrag
ein `before`, aber kein `after`, nennt es die Befehle `after` und
`mailcheck` für diesen Eintrag, sonst einen kurzen Tipp. Es hält nicht an.

**Von rc7 auf v78-r2604.0, Schritt für Schritt.** Die Schritte des
Upgrade-Hinweises des Releases, in der getesteten Reihenfolge
(TESTING-fork.md, „v78-r2604.0“, T5b Teil A, auf einer Kopie nur mit dem
Hotfix von `management/backup.py`; das Zurücksetzen von
`conf/nginx-alldomains.conf` dazu lief im Update-Test nach rc7, auf
`958f2b9`). Docker-Stacks neben der Box bei `backup` wie oben angeben.

	curl -fsSIL https://github.com/Z-Hub/Z-Push/archive/refs/tags/2.7.7.zip > /dev/null && echo OK
	sudo /root/mailinabox/tools/update-check.sh before
	sudo /root/mailinabox/tools/update-check.sh backup
	sudo git -C /root/mailinabox status --short
	sudo git -C /root/mailinabox checkout -- management/backup.py conf/nginx-alldomains.conf
	sudo git -C /root/mailinabox status --short
	sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/setup/bootstrap.sh)"
	sudo /root/mailinabox/tools/update-check.sh after
	sudo /root/mailinabox/tools/update-check.sh mailcheck

Der erste Befehl muss `OK` ausgeben. Jede Datei zurücksetzen, die das erste
`status --short` listet (die beiden oben genannten sind die Hotfixes von
rc7; eine nicht gelistete weglassen); das zweite `status --short` muss
nichts ausgeben. Setup fragt nach dem Hostnamen und den öffentlichen
IP-Adressen: Enter behält sie. `after` sollte mit „RESULT: OK“ enden: Es
bewertet die Änderungen nach `tools/expected-changes/v78-r2604.0.txt` (und
`any.txt`) und nimmt `tests/fork/log-audit-allow-from-rc7.txt` von selbst
zur Log-Prüfung dazu (das alte Z-Push hatte keine Marke der Änderungen des
Forks). Im Test meldete der Teil der Änderungen „RESULT: OK - 0 unexpected,
8 expected changes“, und das Log-Audit nannte zwei Meldungsklassen, die die
Listen des Releases zulassen: die Meldung der auth-worker beim Dovecot-Reload
von Setup und den Wettlauf in der CardDAV-Migration von Roundcube („UNIQUE
constraint failed: carddav_migrations.filename“) bei zwei ersten Anmeldungen
in derselben Sekunde auf einer Box, deren Roundcube seit dem Setup von rc7
nicht benutzt wurde. Jede andere Klasse, die es nennt, ansehen
(`after/log-audit.txt`). `mailcheck` braucht eine Prüfadresse (`--probe ADRESSE` oder
`PROBE_ADDRESS=` in `/etc/mailinabox.conf`); ohne sie wird er übersprungen.

Gleich nach dem Update:

* **Eigene Netze freigeben.** Ab rc4 sind die wachsenden Sperren und die
  langsamen Mail-Jails eingeschaltet, sobald setup fertig ist, mit leerer
  Freigabeliste (allowlist), wenn die Box noch keine hatte (eine unter rc4
  oder später gespeicherte bleibt); einzuschalten ist nichts. Die Netze, aus denen
  die Benutzer arbeiten (Büro, VPN), sofort freigeben, unter System >
  Intrusion Detection and Prevention oder mit
  `sudo /root/mailinabox/management/fail2ban_admin.py --allow 192.0.2.0/24`.
  Sonst kann ein einziges Telefon mit altem Passwort das ganze Büro von den
  Mail-Ports aussperren, jedes Mal länger (bis zu einer Woche). Siehe
  [Schutz vor Anmeldeangriffen](#intrusion-protection-adaptive-fail2ban--schutz-vor-anmeldeangriffen).
* **Die nächtliche Aufgabe wandert.** Setup wählt bei jedem Lauf eine neue
  zufällige Minute zwischen 01:00 und 01:59 Uhr (Systemzeit) für die
  nächtliche Sicherung und die Statusprüfungen, wie upstream
  (`/etc/cron.d/mailinabox-nightly`). Die Zeit dort nachsehen, bevor das
  nächste Update oder Upgrade geplant wird.
* Prüfen, ob die Dienste eingeschaltet sind: `systemctl is-enabled dovecot
  postfix` muss zweimal `enabled` sagen. Auf einer mit rc3 an Ort und Stelle
  aktualisierten Box war Dovecot ausgeschaltet (B67); setup späterer
  Releases schaltet es wieder ein.
* **Munin schreibt dem Administrator.** Ab rc6 funktionieren die Warnungen
  von Munin: Jeder Zustandswechsel eines überwachten Werts (Warnung,
  kritisch, wieder in Ordnung) geht per Mail an administrator@ des
  Box-Namens. Sicherstellen, dass diese Adresse jemanden erreicht. Ab rc7
  stellt das Control Panel eine andere Adresse, nur kritisch oder aus ein
  (siehe [Warnungen von Munin](#munin-alerts--warnungen-von-munin); ab
  v78-r2604.5 unter System > Notifications).
* **fail2ban nach der Log-Rotation.** Ab rc6 protokolliert Dovecot über
  syslog, und rsyslog schreibt seine Zeilen in `mail.log` (B85):
  `doveconf -h log_path` muss `syslog` sagen. Die Dovecot-Jails von
  fail2ban sehen dann fehlgeschlagene Anmeldungen bei IMAP, POP3 und
  ManageSieve auch nach der wöchentlichen Rotation von `mail.log`.
* **Kontakte über ActiveSync (B99, B128).** Ab rc7 bekommen neue Benutzer
  in Nextcloud keinen Beispielkontakt mehr. Ältere Benutzer behalten ihn.
  Unter rc7 schlägt der Kontaktabgleich ihrer Telefone über ActiveSync fehl,
  bis er gelöscht ist (in den Kontakten von Nextcloud der Kontakt, der als
  „This is an example contact“ markiert ist); nach rc7 gleicht Z-Push ihn
  wie jeden anderen Kontakt ab (B128), er kann bleiben oder gelöscht werden.


Security / Sicherheit
---------------------

### English

**The user database belongs to root (B210).** `$STORAGE_ROOT/mail/users.sqlite`
holds every mail account with its password hash, its privileges and its
aliases. Upstream (and this fork up to v78-r2604.4) gave it to root:www-data
with mode 0664, in a directory that www-data could write, because Roundcube's
password plugin wrote the new password into it with SQL. Any code running as
www-data, the account of Roundcube, Nextcloud, Z-Push and PHP, could therefore
set the password of any account (also an administrator's), give itself the
admin privilege, or add an alias that forwards a user's mail to the outside;
and every local account could read all password hashes.

That needs code running as www-data first, but such holes are real and
recent: the PHP security releases of October 2026 ("PHP2Shell",
CVE-2026-109618 and CVE-2026-109619, remote code execution, fixed in PHP
8.5.12, 8.4.27, 8.3.36 and 8.2.35) and of 19 November 2026 (PHP 8.5.13 and
others, several remote code execution issues), and Roundcube's
post-authentication remote code execution CVE-2025-49113 (fixed in 1.6.11 and
1.5.10, exploited in the wild). Each of them gives code as www-data on a
Mail-in-a-Box. Before this release that code could take over every mail
account; now it reaches the user database only through the management
daemon, with an account's current password.

Since this release:

* `users.sqlite` is root:root 0600 and `$STORAGE_ROOT/mail` root:root 755.
  Dovecot, Postfix, the management daemon, the backup and the tools all open
  the database as root. The path is the same, so backups and the migration
  and in-place tools work as before.
* Roundcube's Settings > Password calls the management daemon
  (`POST /me/password` on 127.0.0.1, see api/mailinabox.yml) through the
  fork's password driver. The daemon checks the current password, applies
  the same password rules as the control panel and changes only that
  account's password. Failed attempts are logged for fail2ban
  (`miab-management`), and after 5 for an account or 10 for an address
  within 10 minutes, more are refused for a while. Webmail cannot change the
  password of an account with two-factor authentication: an administrator
  changes it in the control panel (Mail & Users > Users), which has no
  password form for other users.
* Going back to v78-r2604.4 works: its setup gives the database and the
  directory back to www-data and Roundcube's plugin back to its SQL driver.

**The migration number cannot be lowered (B211).** `$STORAGE_ROOT` is the
home of the storage user, who owns `mailinabox.version` there, the number of
the last data migration. A lower number made the next setup run run the
migrations again as root, and some of them delete data when they run twice
(the DKIM key, Roundcube's CardDAV tables). Setup now also keeps the number
in `/var/lib/mailinabox/storage-migration` (root's own) and stops before any
migration when `mailinabox.version` says less. After restoring an older
backup of `$STORAGE_ROOT` on the same box, setup stops with that message:
remove `/var/lib/mailinabox/storage-migration` and run setup again, so that
the backup's migrations run. A restore on a new box needs nothing, and the
migration tool removes the record itself before each of its setup runs.

**Backup and DNS settings only from root's directories (B212).** The backup
target and passphrase (`backup/custom.yaml`, `backup/secret_key.txt`) and the
custom DNS records (`dns/custom.yaml`) are read, and the two `custom.yaml`
written, only through a checked directory of root's own: the storage user
could otherwise replace `backup/` or `dns/` in its home and send the backups
to a server of its own, encrypted with a passphrase it knows, or add DNS
records. If one of the two directories is not root's own (owner root, mode
755), backups or DNS updates stop with the reason, shown in the nightly mail
and the status checks.

**Nextcloud takes a forwarded address only from nginx's proxy (B213).** The
proxy of `/caldav`, `/carddav` and `/webdav` connects to Nextcloud from
127.0.0.1 and passes the client's address in `X-Forwarded-For`. nginx now
passes that header to Nextcloud only from this proxy, which proves itself
with a secret from `/etc/nginx/miab-nextcloud-proxy.conf` (root's
only, made once by setup), so another process on the box can no longer
have a failed login logged and banned under an address of its choice. A
proxy of your own in `www/custom.yaml` to the box's own `/cloud` is seen as
127.0.0.1, and so loses all protection against password guessing:
Nextcloud does not throttle 127.0.0.1, fail2ban does not ban it, and
Dovecot answers the IMAP logins with which Nextcloud checks the passwords
at once (B126). Do not use such a proxy on a box reachable from the
Internet; the box's own paths (`/cloud`, `/caldav`, `/carddav`,
`/webdav`) are not affected.

### Deutsch

**Die Benutzerdatenbank gehört root (B210).**
`$STORAGE_ROOT/mail/users.sqlite` enthält alle Mailkonten mit ihren
Passwort-Hashes, Rechten und Aliasen. Upstream (und dieser Fork bis
v78-r2604.4) gab sie root:www-data mit dem Modus 0664, in einem Verzeichnis,
in das www-data schreiben durfte, weil das Passwort-Plugin von Roundcube das
neue Passwort per SQL selbst hineinschrieb. Jeder Code, der als www-data
läuft, dem Konto von Roundcube, Nextcloud, Z-Push und PHP, konnte deshalb das
Passwort jedes Kontos setzen (auch das eines Administrators), sich selbst
Administratorrechte geben oder einen Alias anlegen, der die Mails eines
Benutzers nach außen weiterleitet; und jedes lokale Konto konnte alle
Passwort-Hashes lesen.

Dafür muss zuerst Code als www-data laufen, aber solche Lücken gibt es, und
sie sind neu: die PHP-Sicherheitsupdates vom Oktober 2026 („PHP2Shell“,
CVE-2026-109618 und CVE-2026-109619, Ausführung von Code aus der Ferne,
behoben in PHP 8.5.12, 8.4.27, 8.3.36 und 8.2.35) und vom 19. November 2026
(PHP 8.5.13 und weitere, mehrere Lücken dieser Art) sowie die Lücke
CVE-2025-49113 in Roundcube (Ausführung von Code nach der Anmeldung, behoben in
1.6.11 und 1.5.10, aktiv ausgenutzt). Jede davon bringt Code als www-data auf
eine Mail-in-a-Box. Vor diesem Release konnte dieser Code jedes Mailkonto
übernehmen; jetzt kommt er an die Benutzerdatenbank nur noch über den
Management-Dienst und nur mit dem aktuellen Passwort eines Kontos.

Seit diesem Release:

* `users.sqlite` ist root:root 0600, `$STORAGE_ROOT/mail` root:root 755.
  Dovecot, Postfix, der Management-Dienst, die Sicherung und die Werkzeuge
  öffnen die Datenbank alle als root. Der Pfad ist derselbe, Sicherungen und
  die Werkzeuge für Umzug und Upgrade an Ort und Stelle funktionieren wie
  bisher.
* Einstellungen > Passwort in Roundcube ruft über den Passwort-Treiber des
  Forks den Management-Dienst auf (`POST /me/password` auf 127.0.0.1, siehe
  api/mailinabox.yml). Der Dienst prüft das aktuelle Passwort, wendet
  dieselben Passwortregeln an wie das Control Panel und ändert nur das
  Passwort dieses Kontos. Fehlversuche werden für fail2ban protokolliert
  (`miab-management`); nach 5 für ein Konto oder 10 für eine Adresse innerhalb
  von 10 Minuten werden weitere eine Zeit lang abgewiesen. Das Passwort eines
  Kontos mit Zwei-Faktor-Anmeldung lässt sich im Webmail nicht ändern: Ein
  Administrator ändert es im Control Panel (Mail & Users > Users), das für
  andere Benutzer kein Passwortformular hat.
* Der Weg zurück zu v78-r2604.4 funktioniert: Dessen setup gibt Datenbank
  und Verzeichnis wieder www-data und das Plugin von Roundcube wieder seinem
  SQL-Treiber.

**Die Migrationsnummer lässt sich nicht herabsetzen (B211).**
`$STORAGE_ROOT` ist das Heimatverzeichnis des Speicherbenutzers, dem dort
`mailinabox.version` gehört, die Nummer der letzten Datenmigration. Mit einer
kleineren Nummer führte der nächste Lauf von setup die Migrationen erneut als
root aus, und manche löschen Daten, wenn sie zweimal laufen (den DKIM-Schlüssel,
die CardDAV-Tabellen von Roundcube). Setup hält die Nummer jetzt zusätzlich in
`/var/lib/mailinabox/storage-migration` (gehört root) fest und bricht vor jeder
Migration ab, wenn `mailinabox.version` weniger angibt. Nach dem
Zurückspielen einer älteren Sicherung von `$STORAGE_ROOT` auf derselben Box
bricht setup mit dieser Meldung ab: `/var/lib/mailinabox/storage-migration`
löschen und setup erneut starten, damit die Migrationen der Sicherung laufen.
Auf einer neuen Box ist dafür nichts zu tun, und das Umzugswerkzeug löscht
die Datei vor jedem seiner Läufe von setup selbst.

**Einstellungen von Sicherung und DNS nur aus Verzeichnissen von root (B212).**
Ziel und Passphrase der Sicherung (`backup/custom.yaml`,
`backup/secret_key.txt`) und die eigenen DNS-Einträge (`dns/custom.yaml`)
werden nur über ein geprüftes Verzeichnis gelesen, das root gehört, und die
beiden `custom.yaml` nur so geschrieben: Sonst könnte der Speicherbenutzer
`backup/` oder `dns/` in seinem Heimatverzeichnis ersetzen und die Sicherungen
an einen eigenen Server schicken, verschlüsselt mit einer Passphrase, die er
kennt, oder DNS-Einträge hinzufügen. Gehört eines der beiden Verzeichnisse
nicht root (Besitzer root, Modus 755), halten Sicherungen bzw.
DNS-Aktualisierungen mit dem Grund an, zu sehen in der nächtlichen Mail und in
den Statusprüfungen.

**Nextcloud übernimmt eine weitergereichte Adresse nur vom Proxy von nginx
(B213).** Der Proxy von `/caldav`, `/carddav` und `/webdav` verbindet sich
von 127.0.0.1 aus mit Nextcloud und reicht die Adresse des Clients in
`X-Forwarded-For` weiter. nginx gibt diesen Header jetzt nur noch von diesem
Proxy an Nextcloud weiter; der Proxy weist sich mit einem Geheimnis aus
`/etc/nginx/miab-nextcloud-proxy.conf` aus (nur für root lesbar, von
setup einmal erzeugt). Ein anderer Prozess auf der Box kann so keine
fehlgeschlagene Anmeldung mehr unter einer Adresse seiner Wahl protokollieren
und sperren lassen. Ein eigener Proxy in `www/custom.yaml` auf das `/cloud`
der Box selbst erscheint als 127.0.0.1 und verliert damit jeden Schutz gegen
das Erraten von Passwörtern: Nextcloud bremst 127.0.0.1 nicht, fail2ban
sperrt es nicht, und Dovecot beantwortet die IMAP-Anmeldungen, mit denen
Nextcloud die Passwörter prüft, sofort (B126). Einen solchen Proxy auf einer
Box, die aus dem Internet erreichbar ist, nicht verwenden; die eigenen Pfade
der Box (`/cloud`, `/caldav`, `/carddav`, `/webdav`) sind nicht betroffen.


Setup output / Ausgaben von setup
---------------------------------

### English

Some lines in the output of setup on Ubuntu 26.04 look like errors but are
harmless; setup goes on and ends with "Your Mail-in-a-Box is running.":

* `/usr/bin/pollinate: 57: cannot create /var/cache/pollinate/log: Permission denied`,
  followed by "pollinate could not seed the random number generator (not
  critical)": on a box upgraded from an older Ubuntu, pollinate's log belongs
  to root. Seeding from the pollinate servers is an extra; the kernel seeds
  its random number generator anyway (B56).
* "No upgrade required." and "Note: This command triggers the upgrade
  actions associated with a new version ...", with a link to the upgrade
  documentation: Nextcloud's `occ upgrade`, which setup runs on every run,
  found nothing to upgrade.
* "Synchronizing state of fail2ban.service with SysV service script ..." and
  "Executing: /usr/lib/systemd/systemd-sysv-install enable fail2ban":
  systemctl enabling a service that also has an init script.
* "Connection to 127.0.0.1 10222 port [tcp/*] succeeded!" (up to
  v78-r2604.1): setup waiting for the management daemon. From v78-r2604.2
  on, setup no longer shows nc's output (B174).
* "Commenting out the 127.0.1.1 line of /etc/hosts with another machine's
  name...": setup fixing a provider's host name (B60, B68).
* "Cleaning up legacy php version": setup removing PHP 8.2, which it only
  needs for the step-by-step upgrade of an old Nextcloud.
* `postconf: warning: /etc/postfix/main.cf: support for parameter
  "smtpd_tls_dh1024_param_file" will be removed`, in the output of the
  in-place upgrade (while the release upgrade installs Postfix 3.10) and of
  a box on rc3 or older: their `main.cf` still sets the parameter, which
  setup comments out (B59, since rc4). It is gone after setup's run; a box
  on a current release prints no such warning.

### Deutsch

Einige Zeilen in der Ausgabe von setup unter Ubuntu 26.04 sehen wie Fehler
aus, sind aber harmlos; setup läuft weiter und endet mit „Your Mail-in-a-Box
is running.“:

* `/usr/bin/pollinate: 57: cannot create /var/cache/pollinate/log: Permission denied`,
  danach „pollinate could not seed the random number generator (not
  critical)“: Auf einer von einer älteren Ubuntu-Version aktualisierten Box
  gehört das Protokoll von pollinate root. Das Füllen des Zufallsgenerators
  über die pollinate-Server ist eine Zugabe; der Kernel füllt ihn ohnehin
  (B56).
* „No upgrade required.“ und „Note: This command triggers the upgrade
  actions associated with a new version ...“ mit einem Verweis auf die
  Upgrade-Dokumentation: `occ upgrade` von Nextcloud, das setup bei jedem
  Lauf aufruft, hat nichts zu aktualisieren gefunden.
* „Synchronizing state of fail2ban.service with SysV service script ...“ und
  „Executing: /usr/lib/systemd/systemd-sysv-install enable fail2ban“:
  systemctl schaltet einen Dienst ein, der auch ein Init-Skript hat.
* „Connection to 127.0.0.1 10222 port [tcp/*] succeeded!“ (bis
  v78-r2604.1): setup wartet auf den Verwaltungsdienst. Ab v78-r2604.2
  zeigt setup die Ausgabe von nc nicht mehr (B174).
* „Commenting out the 127.0.1.1 line of /etc/hosts with another machine's
  name...“: setup ersetzt den Hostnamen eines Anbieters (B60, B68).
* „Cleaning up legacy php version“: setup entfernt PHP 8.2, das es nur für
  das schrittweise Upgrade einer alten Nextcloud braucht.
* `postconf: warning: /etc/postfix/main.cf: support for parameter
  "smtpd_tls_dh1024_param_file" will be removed` in der Ausgabe des
  In-place-Upgrades (während das Release-Upgrade Postfix 3.10 installiert)
  und einer Box auf rc3 oder älter: Deren `main.cf` setzt den Parameter
  noch, den setup auskommentiert (B59, seit rc4). Nach dem Lauf von setup
  ist sie verschwunden; eine Box auf einem aktuellen Release gibt keine
  solche Warnung aus.


Known issues / Bekannte Einschränkungen
---------------------------------------

### English

These issues of the current release are known and not fixed. The fixed bugs
are in [BUGS-fork.md](BUGS-fork.md), whose section "Known limitations (not
fixed)" lists a few more.

* **A Dovecot reload ends open IMAP sessions (B122).** Setup reloads
  Dovecot only when its configuration changed, which most updates do not
  do. A reload keeps the listening sockets, so no connection is refused,
  but Dovecot ends the open IMAP sessions, and their clients log in again.
* **A Dovecot reload still causes two client-visible failures (B122, B121,
  B137).** A login that the old login process hands to the new auth
  process at that moment fails as an internal failure; Nextcloud's IMAP
  login (`user_external`) counts it as a failed login of the client
  (harmless for 127.0.0.1 since B121). A FolderSync or Ping that Z-Push
  answers during the reload gets a server error when Z-Push cannot
  connect to Dovecot again (B137); the phone tries again.
* **A race in the migration of Roundcube's CardDAV plugin after an
  upgrade.** When two sessions log in at the same moment for the first
  time after an upgrade of the plugin, its schema migration runs twice and
  logs "duplicate column name: account_id", "no such column: active" or
  "UNIQUE constraint failed: carddav_migrations.filename", and one of the
  logins fails once. After an update from rc7 or earlier,
  `update-check.sh after` accepts the last form. To be reported to the
  plugin project.
* **Nextcloud on SQLite answers a CardDAV write with HTTP 500 now and
  then while its cron job runs.** Nextcloud logs "database is locked",
  and the client writes again later (seen once in the tests). Nextcloud
  already keeps its SQLite database in WAL mode (its default), and PHP
  waits up to 60 s for a lock (pdo_sqlite's default timeout), so no
  setting of Nextcloud or SQLite helps here: the likely cause is a
  transaction that read first and then wants to write after another
  connection wrote meanwhile, which SQLite refuses at once, whatever the
  timeout. Setup supports only SQLite for Nextcloud.
* **Failed logins from the box itself (B126).** Dovecot answers a failed
  login from the box itself at once and does not slow down later logins
  from there: those logins come from Z-Push, Roundcube and Nextcloud, which
  fail2ban protects with the client's own address, and the delay made a
  wrong ActiveSync password take up to 50 s and slowed down every other
  user. "From the box" is every address of 127.0.0.0/8, ::1 and every
  address of the box's interfaces, as a process on the box can use any of
  them. Only wrong passwords count, a login with the right password never. Instead
  Dovecot counts these failures per account: an account with 30 different
  wrong passwords from the box within 30 minutes (System > Intrusion
  Protection changes both numbers) is refused for logins from the box
  (ActiveSync, Autodiscover, webmail, Nextcloud, and IMAP, POP3,
  ManageSieve or SMTP submission from the box) until it has fewer, even
  with its right password. A password sent again counts once: a phone that
  keeps sending an old password, or a repeated typo, does not lock the
  account (Dovecot keeps only a 16-bit tag of a salted hash of each wrong
  password, never the password). Only real accounts are counted, so
  made-up names change nothing for the others. The other accounts are not
  slowed down, and the account's own mail programs that log in from
  outside are not refused. So a process on the box (any local account, or
  code running as www-data after a hole in PHP or a web app) can try at
  most 30 passwords of each account per 30 minutes (a burst of many connections at the same moment can get more through
  in one window, as the passwords are checked in parallel, but then counts
  against the next windows too, so over time only a little more than 30
  per window, about 33 in the lab's worst case;
  the lock then lasts up to 4 windows, 2 hours, and the number of windows
  can be set from 1 to 4 under System > Intrusion Detection and Prevention). Such a process can still raise Dovecot's penalty of
  127.0.0.1 with a login whose authorization name differs from its login
  name (it fails before these checks) and so slow down the others. The
  other side: someone who tries the passwords of one account through
  ActiveSync, webmail or Nextcloud from one or more addresses that fail2ban
  does not ban (fewer than 20 failures within 30 to 120 s each) locks that
  account's phones, webmail and Nextcloud out while they keep trying. The
  box mails each new lock to the report recipient (System > Notifications,
  at most one mail an hour); System > Intrusion Detection and Prevention lists the
  counted and refused accounts with a button to end a lock (also `sudo
  management/auth_guard.py --status` and `--unlock ADDRESS`). If Dovecot
  cannot write its counts (`/run/miab-auth-guard`), failed logins from the
  box get Dovecot's delay again. Logins from other addresses keep
  Dovecot's delay. Guesses through Microsoft's servers once they are on the
  allowlist (System > Intrusion Detection and Prevention): fail2ban no longer bans them,
  and only this limit per account remains.
* **Spamhaus checks of a fresh install through some public resolvers
  (B136).** Through some public resolvers (8.8.8.8 in the tests) Spamhaus
  answers NXDOMAIN, also for its own test entries. That looks like "not
  listed", so setup's network checks of a fresh install can neither see a
  listing nor say that they could not check. Check the hostname and the
  address on https://check.spamhaus.org/; once the box runs, its status
  checks ask through its own resolver.
* **The storage user can still replace $STORAGE_ROOT/mail (B210).**
  `$STORAGE_ROOT` is the storage user's home, so that account can rename
  `mail/` there and put a directory of its own in its place, with a
  `users.sqlite` of its choice (accounts, password hashes, the admin
  privilege) and links back to the mailboxes. Dovecot, Postfix and the
  management daemon open the database by its path and would use that
  copy. It needs code running as the storage user, which no service of the
  box runs; the real accounts then no longer work, so it does not go
  unnoticed. Setup stops at such a directory or database, before it
  changes anything, instead of making it root's ("not taken over").
  `ssl/` (the private keys) can be replaced the same way, and setup does
  not check it: the services would read the keys of the storage user's
  directory.

### Deutsch

Diese Einschränkungen des aktuellen Releases sind bekannt und nicht behoben.
Die behobenen Fehler stehen in [BUGS-fork.md](BUGS-fork.md); dessen Abschnitt
„Known limitations (not fixed)“ nennt noch einige mehr.

* **Ein Reload von Dovecot beendet offene IMAP-Sitzungen (B122).** setup
  lädt Dovecot nur neu, wenn sich seine Konfiguration geändert hat, was bei
  den meisten Updates nicht der Fall ist. Beim Reload bleiben die
  Listening-Sockets offen, keine Verbindung wird abgewiesen, aber Dovecot
  beendet die offenen IMAP-Sitzungen, und ihre Clients melden sich neu an.
* **Ein Reload von Dovecot führt noch zu zwei Fehlern, die Clients sehen
  (B122, B121, B137).** Eine Anmeldung, die der alte Login-Prozess genau in
  diesem Moment an den neuen Auth-Prozess übergibt, scheitert als interner
  Fehler; die IMAP-Anmeldung von Nextcloud (`user_external`) zählt das als
  fehlgeschlagene Anmeldung des Clients (für 127.0.0.1 seit B121 harmlos).
  Ein FolderSync oder Ping, den Z-Push während des Reloads beantwortet,
  bekommt einen Serverfehler, wenn Z-Push keine neue Verbindung zu Dovecot
  bekommt (B137); das Telefon versucht es erneut.
* **Eine Wettlaufsituation in der Migration des CardDAV-Plugins von
  Roundcube nach einem Upgrade.** Melden sich nach einem Upgrade des
  Plugins zwei Sitzungen im selben Moment zum ersten Mal an, läuft seine
  Schema-Migration zweimal und protokolliert „duplicate column name:
  account_id“, „no such column: active“ oder „UNIQUE constraint failed:
  carddav_migrations.filename“, und eine der Anmeldungen scheitert einmal.
  Nach einem Update von rc7 oder älter akzeptiert `update-check.sh after`
  die letzte Form. Eine Meldung an das Plugin-Projekt steht noch aus.
* **Nextcloud mit SQLite beantwortet gelegentlich einen CardDAV-Schreibzugriff
  mit HTTP 500, während sein Cron-Job läuft.** Nextcloud protokolliert
  „database is locked“, und der Client schreibt später erneut (einmal in den
  Tests gesehen). Nextcloud führt seine SQLite-Datenbank bereits im
  WAL-Modus (seine Voreinstellung), und PHP wartet bis zu 60 s auf eine
  Sperre (die Voreinstellung von pdo_sqlite); keine Einstellung von
  Nextcloud oder SQLite hilft hier also: Die wahrscheinliche Ursache ist eine
  Transaktion, die zuerst gelesen hat und dann schreiben will, nachdem eine
  andere Verbindung inzwischen geschrieben hat; das lehnt SQLite sofort ab,
  unabhängig von der Wartezeit. setup unterstützt für Nextcloud nur SQLite.
* **Fehlgeschlagene Anmeldungen von der Box selbst (B126).** Dovecot
  beantwortet eine fehlgeschlagene Anmeldung von der Box selbst sofort und
  bremst spätere Anmeldungen von dort nicht: Diese Anmeldungen kommen von
  Z-Push, Roundcube und Nextcloud, die fail2ban mit der eigenen Adresse des
  Clients schützt, und die Verzögerung ließ ein falsches
  ActiveSync-Passwort bis zu 50 s dauern und bremste alle anderen Benutzer.
  „Von der Box“ heißt jede Adresse aus 127.0.0.0/8, ::1 und jede Adresse
  der Netzwerkschnittstellen der Box, denn ein Prozess auf der Box kann
  jede davon benutzen. Es zählen nur falsche Passwörter, eine Anmeldung mit
  dem richtigen Passwort nie.
  Stattdessen zählt Dovecot diese Fehlversuche pro Konto: Ein Konto mit 30
  verschiedenen falschen Passwörtern von der Box innerhalb von 30 Minuten
  (beide Zahlen lassen sich unter System > Intrusion Detection and Prevention ändern)
  wird für Anmeldungen von der Box (ActiveSync, Autodiscover, Webmail,
  Nextcloud sowie IMAP, POP3, ManageSieve oder SMTP-Versand von der Box)
  abgewiesen, bis es weniger hat, auch mit dem richtigen Passwort. Ein
  erneut gesendetes Passwort zählt nur einmal: Ein Handy, das immer wieder
  ein altes Passwort schickt, oder ein wiederholter Tippfehler sperrt das
  Konto nicht (Dovecot behält von jedem falschen Passwort nur ein
  16-Bit-Kennzeichen eines Hashes mit Zufallswert, nie das Passwort).
  Gezählt werden nur echte Konten, erfundene Namen ändern für die anderen
  also nichts. Die anderen Konten werden nicht gebremst, und die eigenen
  Mailprogramme des Kontos, die sich von außen anmelden, werden nicht
  abgewiesen. Ein Prozess auf der Box (jedes lokale Konto oder Code, der
  nach einer Lücke in PHP oder einer Web-Anwendung als www-data läuft)
  kann also höchstens 30 Passwörter pro Konto und 30 Minuten
  durchprobieren (ein Schub sehr vieler gleichzeitiger Verbindungen kann in einem
  Fenster mehr durchbringen, weil die Passwörter parallel geprüft werden,
  zählt dann aber auch gegen die folgenden Fenster, sodass auf Dauer nicht
  mehr als 30 pro Fenster durchkommen; die Sperre dauert dann bis zu 4
  Fenster, also 2 Stunden, und die Zahl der Fenster lässt sich unter
  System > Intrusion Detection and Prevention von 1 bis 4 einstellen). Ein solcher
  Prozess kann den Strafzähler von Dovecot für 127.0.0.1 weiterhin mit
  einer Anmeldung erhöhen, deren Autorisierungsname vom Anmeldenamen
  abweicht (sie scheitert vor diesen Prüfungen), und so die anderen
  bremsen. Die Kehrseite: Wer die Passwörter eines Kontos über ActiveSync,
  Webmail oder Nextcloud von einer oder mehreren Adressen aus
  durchprobiert, die fail2ban nicht sperrt (je weniger als 20
  Fehlversuche in 30 bis 120 s), sperrt die Handys, das Webmail und
  Nextcloud dieses Kontos aus, solange er weitermacht. Die Box schickt jede
  neue Sperre an den Empfänger der Berichte (System > Notifications,
  höchstens eine Mail pro Stunde); System > Intrusion Detection and Prevention listet die
  gezählten und abgewiesenen Konten mit einem Knopf, der eine Sperre beendet
  (auch `sudo management/auth_guard.py --status` und `--unlock ADRESSE`).
  Kann Dovecot seine Zähler nicht schreiben (`/run/miab-auth-guard`),
  bekommen fehlgeschlagene Anmeldungen von der Box wieder die Verzögerung
  von Dovecot. Anmeldungen von anderen Adressen behalten die Verzögerung
  von Dovecot. Versuche über die Server von Microsoft, sobald sie in der
  Freigabeliste stehen (System > Intrusion Detection and Prevention): fail2ban sperrt sie
  nicht mehr, und es bleibt nur diese Grenze pro Konto.
* **Spamhaus-Prüfungen einer Neuinstallation über manche öffentliche
  Resolver (B136).** Über manche öffentliche Resolver (in den Tests
  8.8.8.8) antwortet Spamhaus mit NXDOMAIN, auch für seine eigenen
  Testeinträge. Das sieht aus wie „nicht gelistet“; die Netzwerkprüfungen
  von setup bei einer Neuinstallation können dort also weder einen Eintrag
  sehen noch melden, dass sie nicht prüfen konnten. Hostname und Adresse
  auf https://check.spamhaus.org/ selbst prüfen; sobald die Box läuft,
  fragen ihre Statusprüfungen über ihren eigenen Resolver.
* **Der Speicherbenutzer kann $STORAGE_ROOT/mail noch ersetzen (B210).**
  `$STORAGE_ROOT` ist das Heimatverzeichnis des Speicherbenutzers; dieses
  Konto kann `mail/` dort umbenennen und ein eigenes Verzeichnis an seine
  Stelle setzen, mit einer `users.sqlite` nach seiner Wahl (Konten,
  Passwort-Hashes, Administratorrechte) und Links zurück auf die Postfächer.
  Dovecot, Postfix und der Management-Dienst öffnen die Datenbank über
  ihren Pfad und nähmen diese Kopie. Dafür muss Code als Speicherbenutzer
  laufen, und kein Dienst der Box läuft so; die echten Konten funktionieren
  dann nicht mehr, es bleibt also nicht unbemerkt. setup bricht bei einem
  solchen Verzeichnis oder einer solchen Datenbank ab, bevor es etwas
  ändert, statt sie root zu geben („not taken over“). Auch `ssl/` (die
  privaten Schlüssel) lässt sich so ersetzen, und setup prüft es nicht:
  Die Dienste läsen dann die Schlüssel aus dem Verzeichnis des
  Speicherbenutzers.

Security updates and Ubuntu Pro / Sicherheitsupdates und Ubuntu Pro
-------------------------------------------------------------------

### English

PHP 8.5 from Ubuntu 26.04 runs the webmail (Roundcube), Nextcloud and
Z-Push. Some of its packages are in Ubuntu's "universe" component,
among them `php8.5-fpm`, which runs all PHP code of the box, and some of
the modules setup installs (such as `php8.5-intl`); others, such as
`php8.5-cli`, are in "main". Other packages of the box are in universe
too: `nsd`, `opendkim`, `opendmarc`, `spampd`, `postgrey`, `fail2ban`,
`munin`, `certbot` and `dovecot-auth-lua` (the limit of failed logins from
the box itself; it comes from the source package `dovecot`, whose other
packages are in main). Canonical guarantees security updates during the
standard support of an LTS release only for "main" (and "restricted"); for
"universe" they are guaranteed only with Ubuntu Pro, service `esm-apps`
(Expanded Security Maintenance for Applications). Without it, an update
of a universe package comes when someone in the Ubuntu community provides
it, or not at all. So far PHP's security updates reached `php8.5-fpm`
together with `php8.5-cli` (both come from the source package `php8.5`),
but that is not promised. `php8.5-imap` comes from packages.sury.org, not
from Ubuntu; Ubuntu Pro does not cover it.

For a box this means: without Ubuntu Pro, a security hole in PHP-FPM, one
of the PHP modules or one of the other universe packages may stay open on
the box. With Ubuntu Pro, these updates come through apt like the others,
and the box's automatic security updates (unattended-upgrades, which
setup turns on) install them: their standard sources include those of
`esm-apps`.

To turn it on, get a token at <https://ubuntu.com/pro> (Canonical offers a
free personal subscription for a few machines; the conditions are on that
page), then:

	sudo pro attach TOKEN
	sudo pro status            # esm-apps: enabled
	sudo pro enable esm-apps   # only if it is not
	sudo apt update && sudo apt upgrade

`pro status` before the attach shows what the machine could use. Setup
does not change the attachment; the box stays attached through setup runs
and updates of the fork.

### Deutsch

PHP 8.5 aus Ubuntu 26.04 betreibt das Webmail (Roundcube), Nextcloud und
Z-Push. Ein Teil seiner Pakete liegt in der Ubuntu-Komponente „universe“,
darunter `php8.5-fpm`, das den gesamten PHP-Code der Box ausführt, und
einige der Module, die setup installiert (etwa `php8.5-intl`); andere wie
`php8.5-cli` liegen in „main“. Auch weitere Pakete der Box liegen in
universe: `nsd`, `opendkim`, `opendmarc`, `spampd`, `postgrey`,
`fail2ban`, `munin`, `certbot` und `dovecot-auth-lua` (die Grenze für
fehlgeschlagene Anmeldungen von der Box selbst; es stammt aus dem
Quellpaket `dovecot`, dessen andere Pakete in main liegen). Canonical garantiert
Sicherheitsupdates während der Standardunterstützung eines LTS-Releases
nur für „main“ (und „restricted“); für „universe“ sind sie nur mit Ubuntu
Pro garantiert, Dienst `esm-apps` (Expanded Security Maintenance for
Applications). Ohne ihn kommt ein Update eines universe-Pakets, wenn
jemand aus der Ubuntu-Gemeinschaft es bereitstellt, oder gar nicht. Bisher
erreichten die Sicherheitsupdates von PHP `php8.5-fpm` zusammen mit
`php8.5-cli` (beide entstehen aus dem Quellpaket `php8.5`), zugesagt ist
das aber nicht. `php8.5-imap` stammt von packages.sury.org, nicht von
Ubuntu; Ubuntu Pro deckt es nicht ab.

Für eine Box heißt das: Ohne Ubuntu Pro kann eine Sicherheitslücke in
PHP-FPM, in einem der PHP-Module oder in einem der anderen universe-Pakete
auf der Box offen bleiben. Mit Ubuntu Pro kommen diese Updates wie die
anderen über apt, und die automatischen Sicherheitsupdates der Box
(unattended-upgrades, die setup einschaltet) spielen sie ein: Deren
Standardquellen enthalten die von `esm-apps`.

Zum Einschalten auf <https://ubuntu.com/pro> ein Token holen (Canonical
bietet ein kostenloses persönliches Abonnement für einige Maschinen an; die
Bedingungen stehen auf dieser Seite), dann:

	sudo pro attach TOKEN
	sudo pro status            # esm-apps: enabled
	sudo pro enable esm-apps   # nur falls nicht
	sudo apt update && sudo apt upgrade

`pro status` vor dem Attach zeigt, was die Maschine nutzen könnte. setup
ändert die Anbindung nicht; die Box bleibt über Setup-Läufe und Updates des
Forks hinweg angebunden.

Greylisting exceptions / Ausnahmen vom Greylisting
--------------------------------------------------

### English

Postgrey delays mail from unknown senders by a few minutes. Single senders
can skip that delay: list them in `/etc/postfix/greylist_bypass_senders`
(Postfix access(5) format, one envelope sender address or domain per line,
followed by `OK`) and run setup (`sudo mailinabox`):

    newsletter@example.com  OK
    example.org             OK

Setup runs `postmap` on the file and adds
`check_sender_access hash:/etc/postfix/greylist_bypass_senders` to
`smtpd_recipient_restrictions` right before greylisting; the quota check
moves in front of it, so a full mailbox is still refused. The file is yours:
setup never writes it and keeps the rule on every run. After later changes,
`postmap /etc/postfix/greylist_bypass_senders` is enough. Without the file the
restrictions are those of upstream Mail-in-a-Box. To turn the exceptions off,
delete the file and run setup; until setup has run, `main.cf` still names the
table, so leave `greylist_bypass_senders.db` in place (without it Postfix
defers all incoming mail with "451 4.3.5"). The envelope sender is easy
to forge, so list single senders, not the domains of whole mail providers.
Servers known by their IP address go into postgrey's own
`/etc/postgrey/whitelist_clients.local` instead.

### Deutsch

Postgrey hält Mail von unbekannten Absendern einige Minuten zurück. Einzelne
Absender können diese Verzögerung überspringen: Sie kommen in
`/etc/postfix/greylist_bypass_senders` (Format von Postfix access(5), je Zeile
eine Absenderadresse des Umschlags oder eine Domain, dahinter `OK`), danach
setup aufrufen (`sudo mailinabox`):

    newsletter@example.com  OK
    example.org             OK

Setup führt `postmap` auf der Datei aus und setzt
`check_sender_access hash:/etc/postfix/greylist_bypass_senders` in
`smtpd_recipient_restrictions` unmittelbar vor das Greylisting; die
Quota-Prüfung rückt davor, ein volles Postfach wird also weiter abgewiesen.
Die Datei gehört dem Administrator: setup schreibt sie nie und behält die
Regel bei jedem Lauf bei. Nach späteren Änderungen genügt
`postmap /etc/postfix/greylist_bypass_senders`. Ohne die Datei bleiben die
Regeln die von upstream Mail-in-a-Box. Zum Abschalten der Ausnahmen die Datei
löschen und setup aufrufen; bis setup gelaufen ist, nennt `main.cf` die
Tabelle noch, deshalb `greylist_bypass_senders.db` so lange liegen lassen
(ohne sie stellt Postfix alle eingehenden Mails mit „451 4.3.5“ zurück). Der
Absender des Umschlags lässt sich leicht fälschen, deshalb einzelne Absender
eintragen, nicht die Domains ganzer Mail-Anbieter. Server, die man an ihrer
IP-Adresse erkennt, gehören stattdessen in die Liste von postgrey selbst,
`/etc/postgrey/whitelist_clients.local`.


Nextcloud: sharing within the mail domain / Teilen innerhalb der Maildomain
---------------------------------------------------------------------------

### English

On a box with several mail domains, Nextcloud users only see and share with
the accounts of their own mail domain: the share dialog (files, folders,
calendars, address books), the contacts menu, the system address book over
CardDAV and the member search of teams. Members of the Nextcloud group
`admin` see and share with everyone. Public links, shares by e-mail and
federated sharing are not affected.

`NEXTCLOUD_SHARE_SCOPE` in `/etc/mailinabox.conf` switches it:

* `domain` (default): as described above.
* `all`: upstream's behaviour, everyone sees everyone.

After changing it, run setup again (`sudo mailinabox`).

How it works: Nextcloud has no setting for "same mail domain", so each mail
domain becomes a Nextcloud group named after the domain (`example.com`), and
Nextcloud lets users share only with members of their own groups
(`shareapi_only_share_with_group_members`,
`shareapi_restrict_user_enumeration_to_group`, team search through the same
rules with `circles search_from_collaborator`). user_external puts a new user
into the group at the first login. `tools/nextcloud-share-scope.sh` sets the
options and puts all existing users into their group; setup runs it and cron
runs it every 5 minutes, so new domains, new users and new admins are picked
up. Setup sets these options again on every run; autocompletion in the share
dialog (`shareapi_allow_share_dialog_user_enumeration`) is left as it is.
Switching to `all` puts the options back to what they were before the fork
first set them.
Nextcloud cannot exempt admins from the rule, so the script puts the members
of `admin` into every domain group. Mail-in-a-Box does not make anyone a
Nextcloud admin; `tools/owncloud-unlockadmin.sh` does that for one account.

Limits:

* When the first user of a new mail domain logs in to Nextcloud, the admins
  see that domain only after the next cron run (at most 5 minutes later).
* Admins are members of every domain group. Every user therefore sees the
  admins in the share dialog, and admins receive what is shared with a whole
  domain group. Turn group sharing off if that is not wanted:
  `sudo -u www-data php8.5 /usr/local/lib/owncloud/occ config:app:set core shareapi_allow_group_sharing --value no`.
* Shares between domains that existed before stay until their owner removes
  them.
* The script never removes anyone from a group. Nextcloud deletes the shares
  of a user who leaves a group and then has no group in common with the
  other side. An account that is no longer admin stays in all domain groups
  until it is removed by hand (`occ group:removeuser <domain> <user>`).
* A team (Nextcloud Teams) that already has members of another domain still
  works, and so does sharing with it. A team member added through the API by
  the exact address is not checked against the domain.
* Calendars and address books can still be shared with an account of another
  domain by a CalDAV/CardDAV request that names the account directly
  (`principal:principals/users/<address>`): Nextcloud checks the groups when
  it searches for sharees, not when it stores such a share. The web interface
  does not offer accounts of other domains, so this needs a hand-made request
  or a client that sends it.
* CardDAV clients that synced the system address book before keep their copy
  of the other domains until they sync it from scratch (remove the address
  book or account in the client and add it again). A client that syncs it may
  also get the names of deleted accounts of other domains as "deleted"
  entries.
* Mail domains longer than 64 characters get no group (Nextcloud stores such
  group names as a hash); their users see no one.
* With `all`, the domain groups stay and show up in the share dialog as
  groups that everyone can share with. `occ group:delete <domain>` removes one, together with the shares
  made to it.

### Deutsch

Auf einer Box mit mehreren Maildomains sehen Nextcloud-Benutzer nur die Konten
ihrer eigenen Maildomain und können nur mit diesen teilen: Teilen-Dialog
(Dateien, Ordner, Kalender, Adressbücher), Kontaktmenü, das
Systemadressbuch über CardDAV und die Mitgliedersuche von Teams. Mitglieder
der Nextcloud-Gruppe `admin` sehen alle und können mit allen teilen.
Öffentliche Links, Freigaben per E-Mail und Federation bleiben unberührt.

`NEXTCLOUD_SHARE_SCOPE` in `/etc/mailinabox.conf` schaltet das um:

* `domain` (Standard): wie oben beschrieben.
* `all`: Verhalten von upstream, alle sehen alle.

Nach einer Änderung Setup erneut laufen lassen (`sudo mailinabox`).

Funktionsweise: Nextcloud kennt keine Einstellung „gleiche Maildomain“. Deshalb
wird jede Maildomain zu einer Nextcloud-Gruppe mit dem Namen der Domain
(`example.com`), und Nextcloud erlaubt das Teilen nur mit Mitgliedern der
eigenen Gruppen (`shareapi_only_share_with_group_members`,
`shareapi_restrict_user_enumeration_to_group`, die Teamsuche mit
`circles search_from_collaborator` nach denselben Regeln). user_external nimmt
neue Benutzer bei der ersten Anmeldung in die Gruppe auf.
`tools/nextcloud-share-scope.sh` setzt die Optionen und nimmt alle
vorhandenen Benutzer in ihre Gruppe auf; Setup ruft es auf und Cron alle
5 Minuten, damit neue Domains, neue Benutzer und neue Admins dazukommen.
Setup setzt diese Optionen bei jedem Lauf neu; die Autovervollständigung im
Teilen-Dialog (`shareapi_allow_share_dialog_user_enumeration`) bleibt, wie sie
ist. Beim Umschalten auf `all` erhalten die Optionen wieder die Werte, die sie
hatten, bevor der Fork sie zum ersten Mal gesetzt hat.
Nextcloud kann Admins nicht von der Regel ausnehmen, deshalb nimmt das Skript
die Mitglieder von `admin` in jede Domaingruppe auf. Mail-in-a-Box macht
niemanden zum Nextcloud-Admin; `tools/owncloud-unlockadmin.sh` erledigt das
für ein Konto.

Grenzen:

* Meldet sich der erste Benutzer einer neuen Maildomain bei Nextcloud an,
  sehen die Admins diese Domain erst nach dem nächsten Cron-Lauf (höchstens
  5 Minuten später).
* Admins sind Mitglied jeder Domaingruppe. Deshalb sieht jeder Benutzer die
  Admins im Teilen-Dialog, und Admins erhalten, was mit einer ganzen
  Domaingruppe geteilt wird. Wer das nicht will, schaltet das Teilen mit
  Gruppen ab:
  `sudo -u www-data php8.5 /usr/local/lib/owncloud/occ config:app:set core shareapi_allow_group_sharing --value no`.
* Freigaben zwischen Domains, die es schon gab, bleiben, bis ihr Besitzer sie
  entfernt.
* Das Skript nimmt niemanden aus einer Gruppe heraus. Nextcloud löscht die
  Freigaben eines Benutzers, der eine Gruppe verlässt und danach keine
  gemeinsame Gruppe mehr mit der Gegenseite hat. Ein Konto, das kein Admin
  mehr ist, bleibt in allen Domaingruppen, bis es von Hand entfernt wird
  (`occ group:removeuser <domain> <benutzer>`).
* Ein Team (Nextcloud Teams), das schon Mitglieder einer anderen Domain hat,
  funktioniert weiter, das Teilen damit auch. Ein Teammitglied, das über die
  API mit der genauen Adresse hinzugefügt wird, wird nicht gegen die Domain
  geprüft.
* Kalender und Adressbücher lassen sich weiterhin mit einem Konto einer
  anderen Domain teilen, wenn eine CalDAV/CardDAV-Anfrage das Konto direkt
  nennt (`principal:principals/users/<adresse>`): Nextcloud prüft die Gruppen
  bei der Suche nach Empfängern, nicht beim Speichern einer solchen Freigabe.
  Die Weboberfläche bietet Konten anderer Domains nicht an; dafür braucht es
  also eine selbst gebaute Anfrage oder ein Programm, das sie schickt.
* CardDAV-Programme, die das Systemadressbuch schon vorher abgeglichen haben,
  behalten ihre Kopie der anderen Domains, bis sie es von Grund auf neu
  abgleichen (Adressbuch oder Konto im Programm entfernen und neu
  hinzufügen). Ein Programm, das es abgleicht, kann außerdem die Namen
  gelöschter Konten anderer Domains als „gelöscht“ gemeldet bekommen.
* Maildomains mit mehr als 64 Zeichen bekommen keine Gruppe (Nextcloud
  speichert solche Gruppennamen als Hash); ihre Benutzer sehen niemanden.
* Mit `all` bleiben die Domaingruppen bestehen und erscheinen im
  Teilen-Dialog als Gruppen, mit denen alle teilen können. `occ group:delete <domain>` entfernt eine,
  zusammen mit den Freigaben an sie.


Favicons
--------

### English

The control panel, Roundcube (`/mail/`) and Nextcloud (`/cloud/`) show the
fork's favicon (`branding/favicon.ico`, see [branding/README.md](branding/README.md)).
Setup sets it on every run:

* Roundcube: the option `skin_logo` (`elastic:[favicon]`) in
  `/usr/local/lib/roundcubemail/config/config.inc.php` and the file
  `mailinabox-favicon.ico` in Roundcube's directory. Only the Elastic skin;
  other skins keep their own favicons. If the skin's own
  `skins/elastic/images/favicon.ico` was replaced by hand, setup keeps it.
  Setup rewrites `config.inc.php` on every run, as upstream does, so a
  `skin_logo` added there by hand does not last.
* Nextcloud: the favicon of the theming app, as if it were uploaded under
  Administration > Theming. Name, logo, colours and background stay as they
  are. Like any uploaded favicon, it replaces the app icons that Nextcloud
  shows in the browser tab, and Nextcloud also serves it as its touch icon.
  If an administrator uploaded a favicon there, setup keeps it; setup only
  sets the favicon when there is none (also after the administrator removed
  it), or when it is the fork's (the one setup set before, or the same file
  as `branding/favicon.ico`). If setting it fails, setup only warns and goes
  on.

To use your own favicon in Nextcloud, upload it under Administration >
Theming. `FAVICON=off` in `/etc/mailinabox.conf`, then `sudo mailinabox`,
gives Roundcube and Nextcloud their own favicons back (in Nextcloud only if
the favicon is still the fork's). The control panel and the `/favicon.ico`
of the web domains are not affected by it.

### Deutsch

Das Control Panel, Roundcube (`/mail/`) und Nextcloud (`/cloud/`) zeigen das
Favicon des Forks (`branding/favicon.ico`, siehe
[branding/README.md](branding/README.md)). Setup setzt es bei jedem Lauf:

* Roundcube: die Option `skin_logo` (`elastic:[favicon]`) in
  `/usr/local/lib/roundcubemail/config/config.inc.php` und die Datei
  `mailinabox-favicon.ico` im Verzeichnis von Roundcube. Nur für den Skin
  Elastic; andere Skins behalten ihre eigenen Favicons. Wurde die Datei
  `skins/elastic/images/favicon.ico` des Skins von Hand ersetzt, behält
  setup sie bei. Setup schreibt `config.inc.php` wie upstream bei jedem Lauf
  neu, ein dort von Hand eingetragenes `skin_logo` bleibt also nicht.
* Nextcloud: das Favicon der Theming-App, als wäre es unter Verwaltung >
  Design hochgeladen. Name, Logo, Farben und Hintergrund bleiben, wie sie
  sind. Wie jedes hochgeladene Favicon ersetzt es die App-Symbole, die
  Nextcloud im Browser-Tab zeigt, und Nextcloud liefert es auch als
  Touch-Icon aus. Hat ein Administrator dort ein Favicon hochgeladen, behält
  setup es bei; setup setzt das Favicon nur, wenn keines gesetzt ist (auch
  nachdem der Administrator es entfernt hat) oder wenn es das des Forks ist
  (das, das setup vorher gesetzt hat, oder dieselbe Datei wie
  `branding/favicon.ico`). Scheitert das Setzen, warnt setup nur und läuft
  weiter.

Ein eigenes Favicon für Nextcloud lädt man unter Verwaltung > Design hoch.
`FAVICON=off` in `/etc/mailinabox.conf` und danach `sudo mailinabox` geben
Roundcube und Nextcloud ihre eigenen Favicons zurück (in Nextcloud nur, wenn
es noch das des Forks ist). Das Control Panel und `/favicon.ico` der
Webdomains betrifft das nicht.


Notifications / Benachrichtigungen
----------------------------------

### English

The box mails its administrator: the daily status check changes, the
backup status, the results of TLS certificate requests, the weekly usage
report, Munin's alerts, and the mail of root, of cron jobs and to
postmaster@, abuse@, admin@ and hostmaster@ of its domains. The control
panel shows and sets where these mails go, under System > Notifications:

* **Send reports to**: Standard (administrator@ of the box's name) or a
  custom address, also of another provider (a plain address: ASCII letters,
  digits and `_ + - .` before the @). It is the recipient of the status
  check changes, backup status, TLS results and usage report, and of
  Munin's alerts while they are set to "Same as the reports". The mails
  come from administrator@ of the box's name. **Send test mail** sends one
  mail to it the way the reports are sent (subject "Test of the
  administrator mail", header `X-Miab-Test: 1`).
* **Munin alerts**: the settings that were on the Munin page in rc7 to
  v78-r2604.4 (see [Munin alerts](#munin-alerts--warnungen-von-munin)). The
  menu entry System > Munin Monitoring opens Munin directly again.
* **administrator@ and the addresses of the domains**: the alias
  administrator@ itself is not changed by this setting. It is an address
  of domain control validation (certificate authorities send their
  confirmation mails there), so its destinations may only be
  administrators of the box (Mail & Users > Aliases). It also gets the
  mail to abuse@, postmaster@, hostmaster@ and admin@ of all domains
  (unless such an address is set by hand) and of root and cron jobs. The
  page shows where it leads, followed through the aliases as Postfix does,
  and warns when it cannot work (a loop of aliases, an address of the box
  that does not exist). If nobody reads that mailbox, complaints about
  spam from your domains, for example, go unnoticed: look at it regularly,
  or set up a forwarding filter in its webmail (Settings > Filters).
* **What the box mails** and **Last deliveries**: each kind of mail with
  where it goes, and the last deliveries to administrator@ or the report
  recipient from the mail log (sent, deferred, bounced).

The setting is stored as `admin_mail` in `$STORAGE_ROOT/settings.yaml`;
without it the reports go to administrator@ as before. The same through
the API: `/system/notifications` (see `api/mailinabox.yml`), or on the box:

	sudo /root/mailinabox/management/admin_mail.py --status   # where the mails go
	sudo /root/mailinabox/management/admin_mail.py --test     # a test mail

### Deutsch

Die Box schreibt ihrem Administrator: die täglichen Änderungen der
Statusprüfungen, den Backup-Status, die Ergebnisse der TLS-Zertifikate, den
wöchentlichen Nutzungsbericht, die Warnungen von Munin sowie die Mails von
root, von cron-Jobs und an postmaster@, abuse@, admin@ und hostmaster@
ihrer Domains. Wohin diese Mails gehen, zeigt und stellt das Control Panel
unter System > Notifications ein:

* **Send reports to**: Standard (administrator@ des Box-Namens) oder eine
  eigene Adresse, auch bei einem anderen Anbieter (eine einfache Adresse:
  ASCII-Buchstaben, Ziffern und `_ + - .` vor dem @). Sie ist der Empfänger
  der Änderungen der Statusprüfungen, des Backup-Status, der TLS-Ergebnisse
  und des Nutzungsberichts sowie der Munin-Warnungen, solange diese auf
  „Same as the reports“ stehen. Absender ist administrator@ des
  Box-Namens. **Send test mail** schickt eine Mail auf demselben Weg wie die
  Berichte (Betreff „Test of the administrator mail“, Kopfzeile
  `X-Miab-Test: 1`).
* **Munin alerts**: die Einstellungen, die in rc7 bis v78-r2604.4 auf der
  Munin-Seite standen (siehe [Warnungen von Munin](#munin-alerts--warnungen-von-munin)).
  Der Menüpunkt System > Munin Monitoring öffnet Munin wieder direkt.
* **administrator@ und die Adressen der Domains**: Der Alias
  administrator@ selbst ändert sich durch diese Einstellung nicht. Er ist
  eine Adresse der Domain-Validierung (Zertifizierungsstellen schicken ihre
  Bestätigungen dorthin), deshalb darf er nur zu Administratoren der Box
  führen (Mail & Users > Aliases). Er bekommt auch die Mails an abuse@,
  postmaster@, hostmaster@ und admin@ aller Domains (außer eine solche
  Adresse ist von Hand gesetzt) sowie von root und cron-Jobs. Die Seite
  zeigt, wohin er führt, so aufgelöst wie Postfix es tut, und warnt, wenn
  das nicht funktionieren kann (eine Alias-Schleife, eine Adresse der Box,
  die es nicht gibt). Liest niemand dieses Postfach, bleiben zum Beispiel
  Spam-Beschwerden über die eigenen Domains unbemerkt: regelmäßig
  hineinschauen oder im Webmail einen Weiterleitungsfilter einrichten
  (Einstellungen > Filter).
* **What the box mails** und **Last deliveries**: jede Art von Mail mit
  ihrem Ziel und die letzten Zustellungen an administrator@ oder den
  Berichtsempfänger aus dem Mail-Log (zugestellt, verzögert,
  zurückgewiesen).

Die Einstellung steht als `admin_mail` in `$STORAGE_ROOT/settings.yaml`;
ohne sie gehen die Berichte wie bisher an administrator@. Dasselbe über
die API: `/system/notifications` (siehe `api/mailinabox.yml`), oder auf der
Box:

	sudo /root/mailinabox/management/admin_mail.py --status   # wohin die Mails gehen
	sudo /root/mailinabox/management/admin_mail.py --test     # eine Testmail


Munin alerts / Warnungen von Munin
----------------------------------

### English

Munin watches the disks, memory, load and services of the box. When a
watched value reaches its warning or critical limit, or is back to normal,
`munin-limits` mails that change, one mail per run (every 5 minutes) with
all changes of that run. A value that stays in warning or critical is not
mailed again; `/var/lib/munin/limits` lists the current states.

The admin panel sets who gets these mails, under System > Notifications
(rc7 to v78-r2604.4: on the page System > Munin Monitoring):

* **Send alerts to**: Same as the reports (the report recipient of
  [Notifications](#notifications--benachrichtigungen), administrator@ of
  the box's name by default), a custom address, or Off. A
  custom address must be a plain address: ASCII letters, digits and
  `_ + - .` before the @, no name, quotes or spaces. The mails come from
  administrator@ of the box's name in every case.
* **Level**: warning and critical (the default), or critical only. Critical
  only mails the changes of plugins that have a critical value and lists
  only those values; warnings and the return to normal are not mailed.
  Munin's text template can name the values that are critical, warning or
  unknown now and those that are back to normal in this run, but not the
  state a value had before. So critical only cannot mail the end of a
  critical state alone (it would have to mail every return to normal, also
  of values that were only in warning, which this level leaves out), and a
  value that drops from critical to warning is not mailed either. To be
  told when a value is back to normal, choose warning and critical;
  `/var/lib/munin/limits` shows the current state of each value.
* **Send test mail** sends one notification to the saved recipient through
  the same command as the alerts (subject "Munin test notification", header
  `X-Miab-Test: 1`).

The setting is stored as `munin_alerts` in `$STORAGE_ROOT/settings.yaml`
and turned into `/etc/munin/munin.conf` (by the control panel when it is
saved, and by setup on every run; Munin reads the file on its next run).
Without the setting the file is the same as in rc6. Changes to
`/etc/munin/munin.conf` by hand do not last; put your own Munin settings
into `/etc/munin/munin-conf.d/`. The same through the API:
`/system/munin/alerts` (see `api/mailinabox.yml`), or on the box:

	sudo /root/mailinabox/management/munin_admin.py --print   # the munin.conf of the setting
	sudo /root/mailinabox/management/munin_admin.py --test    # a test mail

### Deutsch

Munin überwacht Platten, Speicher, Last und Dienste der Box. Erreicht ein
überwachter Wert seine Warn- oder kritische Grenze oder ist er wieder
normal, schickt `munin-limits` eine Mail mit dieser Änderung, eine Mail je
Lauf (alle 5 Minuten) mit allen Änderungen dieses Laufs. Ein Wert, der in
Warnung oder kritisch bleibt, wird nicht noch einmal gemeldet;
`/var/lib/munin/limits` listet die aktuellen Zustände.

Wer diese Mails bekommt, stellt das Control Panel unter System >
Notifications ein (rc7 bis v78-r2604.4: auf der Seite System > Munin
Monitoring):

* **Send alerts to**: Same as the reports (der Berichtsempfänger von
  [Benachrichtigungen](#notifications--benachrichtigungen), standardmäßig
  administrator@ des Box-Namens), eine eigene Adresse oder Off. Eine
  eigene Adresse muss eine einfache Adresse sein: ASCII-Buchstaben, Ziffern
  und `_ + - .` vor dem @, kein Name, keine Anführungszeichen, keine
  Leerzeichen. Absender ist in jedem Fall administrator@ des Box-Namens.
* **Level**: Warnung und kritisch (Standard) oder nur kritisch. Nur kritisch
  meldet die Änderungen der Plugins mit einem kritischen Wert und listet nur
  diese Werte; Warnungen und die Rückkehr zum Normalzustand werden nicht
  gemeldet. Munins Textvorlage kann die Werte nennen, die jetzt kritisch,
  in Warnung oder unbekannt sind, und die Werte, die in diesem Lauf wieder
  normal sind, aber nicht den Zustand, den ein Wert vorher hatte. Deshalb
  kann „nur kritisch“ das Ende eines kritischen Zustands nicht allein
  melden (es müsste jede Rückkehr zum Normalzustand melden, auch die von
  Werten, die nur in Warnung waren, die diese Stufe auslässt), und ein
  Wert, der von kritisch auf Warnung sinkt, wird auch nicht gemeldet. Wer
  erfahren will, wann ein Wert wieder normal ist, wählt Warnung und
  kritisch; `/var/lib/munin/limits` zeigt den aktuellen Zustand jedes
  Werts.
* **Send test mail** schickt eine Benachrichtigung an den gespeicherten
  Empfänger, über denselben Befehl wie die Warnungen (Betreff „Munin test
  notification“, Kopfzeile `X-Miab-Test: 1`).

Die Einstellung steht als `munin_alerts` in `$STORAGE_ROOT/settings.yaml`
und wird in `/etc/munin/munin.conf` umgesetzt (vom Control Panel beim
Speichern und von setup bei jedem Lauf; Munin liest die Datei bei seinem
nächsten Lauf). Ohne die Einstellung ist die Datei dieselbe wie in rc6.
Änderungen von Hand an `/etc/munin/munin.conf` bleiben nicht; eigene
Einstellungen für Munin gehören nach `/etc/munin/munin-conf.d/`. Dasselbe
über die API: `/system/munin/alerts` (siehe `api/mailinabox.yml`), oder auf
der Box:

	sudo /root/mailinabox/management/munin_admin.py --print   # munin.conf der Einstellung
	sudo /root/mailinabox/management/munin_admin.py --test    # eine Testmail


Intrusion detection and prevention (adaptive fail2ban) / Schutz vor Anmeldeangriffen
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
  `miab-owncloud`, `miab-roundcube`, `miab-zpush` and the slow web jails) keep their fixed
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
  `miab-slow-owncloud` (Nextcloud), `miab-slow-zpush` (ActiveSync and
  Autodiscover) and `miab-slow-management` (control panel)
  with the same thresholds. They block HTTP and HTTPS: a calendar or contacts
  app or a phone with an old password polls every few minutes and would get its
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
* **ActiveSync jail.** `miab-zpush` (always on, like Mail-in-a-Box's own
  jails) bans an address after 20 failed ActiveSync or Autodiscover logins
  within 120 seconds on HTTP and HTTPS (B126). Z-Push checks passwords against
  Dovecot from 127.0.0.1, which the Dovecot jails ignore, so before it nothing
  limited password guessing there. Setup has Z-Push log failed logins
  (`LOGAUTHFAIL`) to `/var/log/z-push/z-push-error.log` and
  `autodiscover-error.log`, with the client's address as the last thing on
  the line and control characters escaped, so that a user name a client
  chooses cannot name another address. Only a request with a user name and
  a password is logged and counted: a phone's first request without
  credentials (it waits for the login prompt, also with its user in the URL)
  is not. Nor is a login that Dovecot or Nextcloud cannot check at that
  moment (a temporary failure, e.g. while Dovecot does not answer): Z-Push
  answers it with HTTP 503 and `Retry-After`, so the phone tries again later
  without asking for its password. Each line starts with the user names in
  brackets, escaped, and the filter counts a line only when its message
  belongs to them, so no other warning can pass for a failed login. Since
  the fix of B121 (after rc7) the paths `/caldav`, `/carddav` and
  `/webdav` pass the client's address to Nextcloud, so `miab-owncloud` counts
  and bans those clients too. Some mail apps sync through their provider's
  servers, for example Outlook for iOS and Android with an Exchange
  ActiveSync account: all their users reach the box from the same few
  addresses, and 20 wrong passwords there within two minutes get these
  addresses banned for all of them. Anyone can do that on purpose: an
  account name and a wrong password entered in the app are enough. Repeated,
  such bans lead to recidive's one-week ban of these addresses on all ports.
  If your users sync that way, put those networks on the allowlist.
  System > Intrusion Detection and Prevention recognises a banned address of these
  servers by Microsoft's published IP ranges of Exchange Online and of its
  AutoDetect service (shipped in `conf/fail2ban/microsoft-relays.txt`,
  refreshed with `tools/update-microsoft-relays.py` for a release; the box
  downloads nothing), shows a hint and offers a button that puts the
  network on the allowlist after a question; nothing is put there on its
  own. On the allowlist, password guesses through these servers are no
  longer banned: Z-Push checks each password with an IMAP login from
  127.0.0.1, which Dovecot answers at once and limits only per account
  (30 different wrong passwords in 30 minutes unless set otherwise, B126,
  "Known issues"). The
  address's reverse DNS name is shown only as extra information, and only
  when it resolves back to the address: the owner of an address sets its
  PTR record. Other apps that sync through their provider's servers are
  not recognised. `/var/log/z-push` belongs to root (group
  www-data, which may write the four log files but not replace them), so
  that fail2ban never opens a link or a FIFO there; setup and logrotate
  create the log files.
* **Failed-login report.** The status checks read the mail log of the last
  48 hours (SMTP AUTH, IMAP, POP3, ManageSieve), Z-Push's error logs
  (ActiveSync, Autodiscover) and Nextcloud's log (Nextcloud, CalDAV, CardDAV,
  WebDAV; since v78-r2604.4) and report accounts with failed
  logins from 20 or more addresses within 24 hours (`spray_min_ips`, password
  spraying) and addresses that keep failing for 12 hours or more without being
  banned once in that time (bans that have run out are looked up in
  fail2ban's database). Only accounts that exist on the box are named. Give
  such an account a long password that is not used anywhere else, and if it is an
  administrator, turn on two-factor authentication for the control panel.
* **Thresholds of Mail-in-a-Box's jails** (since v78-r2604.4). The failures,
  window and ban time of Mail-in-a-Box's own jails (`dovecot`,
  `miab-management`, `miab-munin`, `miab-owncloud`, `miab-postfix465`,
  `miab-postfix587`, `miab-roundcube`, `miab-zpush`, `postfix-sasl`, `sshd`)
  can be changed (`jails`); only the changed values are stored and written
  to `mailinabox_adaptive.conf`, the others follow `conf/fail2ban/jails.conf`.
  recidive is not among them: it bans addresses that the others banned again
  and again.
* **Why an address is banned** (since v78-r2604.4). For each ban the control
  panel shows the failures and the log lines that fail2ban kept for it (up to
  10, from its database), the accounts of the box they name and the jail's
  rule (what it watches, its thresholds, the ports it blocks). A user name
  that is no account of the box is replaced by "[unknown name]": it is
  whatever the client sent, a password typed into the wrong field too. A ban
  without lines was set by hand.
* **Nextcloud's own throttle** (since v78-r2604.4). Apart from fail2ban,
  Nextcloud counts failed logins per address (IPv4) or IPv6 network (/56 by
  default, `security.ipv6_normalized_subnet_size`):
  after failures within 12 hours it delays every login from there (0.2 s,
  0.4 s, ... up to 25 s), and after more than 10 failures (`nc_max_attempts`)
  within 30 minutes it refuses them with HTTP 429, also for the accounts with
  the right password behind that address. A calendar or contacts app with an
  old password thus keeps the other devices of its network from syncing, and
  a successful login removes only the failures of its own account. The
  control panel lists the counted addresses (failures in 12 hours and in 30
  minutes, the accounts of the box they tried, the delay, whether they are
  blocked) and resets an address: it deletes the failures of its network,
  as `occ security:bruteforce:reset` does, but also where that does nothing
  (with the throttle off, for an address on the bypass list). The throttle
  can be turned off (`nc_protection`, not recommended: then only
  `miab-owncloud` limits password guessing on Nextcloud); Nextcloud then
  counts no new failures but goes on applying those it counted before for up
  to 12 hours, so turning it off also deletes them. A login that was
  already waiting in the throttle then can still add one; with the
  throttle off setup and the daily status checks delete such stale
  failures, and the control panel shows them with a button to delete them.
  `nc_allowlist`
  (off by default) puts the allowlist on Nextcloud's bypass list too (the
  entries it adds are recorded under `nextcloud_bypass` in settings.yaml and
  removed again when they leave the allowlist; `127.0.0.1/32`, B121, and
  entries made in Nextcloud stay). Only for networks of your own: an address
  that is shared with others (mobile networks, satellite and other
  carrier-grade NAT) would be exempt for them too. Setup and the control
  panel write `auth.bruteforce.protection.enabled` and
  `auth.bruteforce.max-attempts` into Nextcloud's `config.php` (only when
  they differ from Nextcloud's defaults), with
  `tools/nextcloud-bruteforce-config.php` as www-data, because Nextcloud's
  own `occ config:system:set` refuses once setup has made the file read-only
  (`management/nextcloud_throttle.py --setup`, `--status`, `--reset <ip>`).
  For each of the two values on its own: while the settings have no value
  of their own for it, a value set in `config.php` by hand (as Nextcloud
  reads it: `0` and `false` are off) is taken over instead of overwritten:
  setup stores it at once and says so, the control panel shows it and stores
  it with the next save. The overview names only accounts of the box; it
  gets them without giving the list of accounts to www-data (the login names
  come back as salted hashes, which root compares with its own).

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
      jails: {}               # e.g. {miab-roundcube: {maxretry: 25, bantime: 3600}}: maxretry 3 to 1000,
                              # findtime 10 s to 7 days, bantime 1 minute to 365 days
      nc_protection: true     # Nextcloud's own throttle
      nc_max_attempts: 10     # 3 to 1000
      nc_allowlist: false     # the allowlist on Nextcloud's bypass list too

`bantime_max` is at least one week so that it never shortens the recidive
ban. Setup writes `/etc/fail2ban/jail.d/mailinabox_adaptive.conf` and
`/etc/fail2ban/fail2ban.d/mailinabox_adaptive.conf` from them
(`management/fail2ban_admin.py --setup`). A slow jail whose log file does not
exist yet is left out. With `adaptive`, `slow_jails` and `slow_web_jails` off,
an empty allowlist and no changed thresholds (`jails`) neither file exists,
which is exactly upstream's configuration. The `nc_*` settings do not go into
these files.
After editing settings.yaml by hand run `sudo management/fail2ban_admin.py
--apply`: it checks the whole configuration with `fail2ban-client -t`, puts
the old files back if fail2ban rejects it, and reloads fail2ban only if a file
changed. `--print` shows the files, `--allow 192.0.2.0/24` adds a network,
`--report` prints the failed-login report.

In the control panel, **System > Intrusion Detection and Prevention** shows whether
fail2ban runs, the banned addresses (per address: the jails, time left, length
and start of each ban and why, with the log lines; with a filter), the
addresses that Nextcloud's own throttle counts (with a "Reset" button, and a
hint at a banned address that Nextcloud throttles too), the jails with their
counters and the failed-login report (accounts with failures from many
addresses, addresses that keep failing, with their ban status). It unbans an
address in all jails or in one jail, unbans all addresses of a jail (after a
confirmation), and edits the settings: adaptive banning and the two kinds of
slow jails on/off (turning one off asks first), the thresholds of the slow
jails and of Mail-in-a-Box's jails (durations also as `30m`, `6h`, `2d`,
`1w`), the allowlist (one address or network per line), Nextcloud's throttle
(on/off, which asks first, the failures before the block, the allowlist on
its bypass list) and "Restore defaults". It also
shows the address you use the panel from and offers to put it on the
allowlist (for IPv6 its /64, because the browser's own address changes), or
to unban it if it is banned (the slow mail jails block only the mail ports, so
the panel stays reachable). Unsaved edits of the settings form are kept when
you unban an address. The page uses this API (admin
only, changes by POST with form fields):

| Request | |
|---|---|
| `GET /admin/system/fail2ban` | fail2ban running, the jails with their counters and banned addresses (start, length, end and seconds left of each ban, and its `reason`: failures, log lines, accounts, `manual`), the settings, defaults and limits, `jail_info` (each jail's thresholds and what it watches), and `client` (the address of the request, whether it is allowlisted or one of the box's own) |
| `GET /admin/system/fail2ban/settings` | the settings, defaults and warnings about invalid stored values |
| `POST /admin/system/fail2ban/settings` | fields named like the settings; fields not sent keep their value, `reset=1` starts from the defaults. Answers with `changed`, `reloaded`, `restarted` (the jails were restarted), `skipped_jails`, `unbanned_allowlisted` (banned addresses that are on the allowlist now and were unbanned) and the new settings, or HTTP 400 with the reason |
| `POST /admin/system/fail2ban/unban` | `ip`, optionally `jail`. Answers with `unbanned_from`, `still_banned_in` and `history_deleted` |
| `POST /admin/system/fail2ban/unban-all` | `jail`: unbans every address banned in that jail |
| `GET /admin/system/fail2ban/report` | the failed-login report as JSON |
| `GET /admin/system/nextcloud-throttle` | Nextcloud's throttle: on or off, `max_attempts`, the counted addresses (failures in 12 hours and 30 minutes, accounts, `delay_ms`, `blocked`) and its bypass list |
| `POST /admin/system/nextcloud-throttle/reset` | `ip`: deletes Nextcloud's failures of the network of that address; answers with `subnets` and `deleted` |

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
  `miab-munin`, `miab-owncloud`, `miab-roundcube`, `miab-zpush` und die langsamen Web-Jails)
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
  `miab-slow-roundcube`, `miab-slow-owncloud` (Nextcloud), `miab-slow-zpush`
  (ActiveSync und Autodiscover) und
  `miab-slow-management` (Admin-Oberfläche) mit denselben Schwellen. Sie
  sperren HTTP und HTTPS: Eine Kalender- oder Kontakte-App oder ein Telefon
  mit altem Passwort fragt alle paar Minuten ab und würde ihr ganzes Netz für
  Webmail und die Admin-Oberfläche sperren. Nur einschalten, wenn die eigenen Netze in
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
* **ActiveSync-Jail.** `miab-zpush` (immer an, wie die Jails von
  Mail-in-a-Box selbst) sperrt eine Adresse nach 20 fehlgeschlagenen
  Anmeldungen über ActiveSync oder Autodiscover innerhalb von 120 Sekunden für
  HTTP und HTTPS (B126). Z-Push prüft Passwörter von 127.0.0.1 aus bei
  Dovecot, und diese Adresse übergehen die Dovecot-Jails; bisher bremste dort
  also nichts das Raten von Passwörtern. Setup lässt Z-Push fehlgeschlagene
  Anmeldungen protokollieren (`LOGAUTHFAIL`, in
  `/var/log/z-push/z-push-error.log` und `autodiscover-error.log`), mit der
  Adresse des Clients am Ende der Zeile und maskierten Steuerzeichen, damit
  ein vom Client gewählter Benutzername keine andere Adresse unterschieben
  kann. Nur eine Anfrage mit Benutzername und Passwort wird protokolliert
  und gezählt: Die erste Anfrage eines Telefons ohne Zugangsdaten (es wartet
  auf die Anmeldeaufforderung, auch mit seinem Benutzer in der URL) nicht.
  Ebenso wenig eine Anmeldung, die Dovecot oder Nextcloud in dem Moment
  nicht prüfen kann (ein vorübergehender Fehler, etwa wenn Dovecot nicht
  antwortet): Z-Push beantwortet sie mit HTTP 503 und `Retry-After`, und das
  Telefon versucht es später wieder, ohne nach dem Passwort zu fragen. Jede
  Zeile beginnt mit den Benutzernamen in eckigen Klammern, maskiert, und der
  Filter zählt eine Zeile nur, wenn ihre Meldung zu ihnen gehört; so kann
  keine andere Warnung als Fehlanmeldung durchgehen. Seit der Korrektur
  von B121 nach rc7 geben die Pfade `/caldav`, `/carddav` und `/webdav` die
  Adresse des Clients an Nextcloud weiter, also zählt und sperrt
  `miab-owncloud` auch diese Clients. Manche Mail-Apps synchronisieren über
  die Server ihres Anbieters, zum Beispiel Outlook für iOS und Android mit
  einem Exchange-ActiveSync-Konto: Alle ihre Nutzer erreichen die Box von
  denselben wenigen Adressen, und 20 falsche Passwörter dort in zwei Minuten
  lassen diese Adressen für alle sperren. Das kann jeder mit Absicht tun:
  Ein Kontoname und ein falsches Passwort in der App genügen. Wiederholt
  führen solche Sperren zur einwöchigen recidive-Sperre dieser Adressen auf
  allen Ports. Wenn die Nutzer so synchronisieren, diese Netze in die
  Freigabeliste setzen. System > Intrusion Detection and Prevention erkennt eine
  gesperrte Adresse dieser Server an Microsofts veröffentlichten
  IP-Bereichen von Exchange Online und seines AutoDetect-Dienstes
  (mitgeliefert in `conf/fail2ban/microsoft-relays.txt`, für ein Release
  erneuert mit `tools/update-microsoft-relays.py`; die Box lädt nichts
  herunter), zeigt einen Hinweis und bietet eine Schaltfläche an, die das
  Netz nach einer Rückfrage in die Freigabeliste setzt; von selbst kommt
  nichts hinein. In der Freigabeliste werden Passwortversuche über diese
  Server nicht mehr gesperrt: Z-Push prüft jedes Passwort mit einer
  IMAP-Anmeldung von 127.0.0.1 aus, die Dovecot sofort beantwortet und nur
  pro Konto begrenzt (30 verschiedene falsche Passwörter in 30 Minuten,
  sofern nicht anders eingestellt, B126, „Bekannte Einschränkungen“). Den Namen aus
  dem Reverse-DNS zeigt die Seite nur als Zusatzinformation und nur, wenn er wieder auf die
  Adresse auflöst: Den PTR-Eintrag setzt der Inhaber der Adresse. Andere
  Apps, die über die Server ihres Anbieters synchronisieren, erkennt sie
  nicht.
  `/var/log/z-push` gehört root (Gruppe www-data, die die vier Logdateien
  beschreiben, aber nicht ersetzen darf), damit fail2ban dort nie einen Link
  oder eine FIFO öffnet; Setup und logrotate legen die Logdateien an.
* **Bericht über Fehlanmeldungen.** Die Statusprüfungen lesen das Mail-Log der
  letzten 48 Stunden (SMTP AUTH, IMAP, POP3, ManageSieve), die Fehler-Logs
  von Z-Push (ActiveSync, Autodiscover) und das Log von Nextcloud (Nextcloud,
  CalDAV, CardDAV, WebDAV; seit v78-r2604.4) und melden Konten
  mit Fehlanmeldungen von 20 oder mehr Adressen innerhalb von 24 Stunden
  (`spray_min_ips`, Password Spraying) sowie Adressen, die 12 Stunden oder
  länger scheitern, ohne in dieser Zeit ein einziges Mal gesperrt worden zu
  sein (abgelaufene Sperren stehen in der Datenbank von fail2ban). Genannt
  werden nur Konten, die es
  auf der Box gibt. Ein solches Konto braucht ein langes Passwort, das nirgends
  sonst verwendet wird, und, wenn es ein Administrator ist, die
  Zwei-Faktor-Anmeldung für die Admin-Oberfläche.
* **Schwellen der Jails von Mail-in-a-Box** (seit v78-r2604.4). Fehlversuche,
  Zeitfenster und Sperrdauer der eigenen Jails von Mail-in-a-Box (`dovecot`,
  `miab-management`, `miab-munin`, `miab-owncloud`, `miab-postfix465`,
  `miab-postfix587`, `miab-roundcube`, `miab-zpush`, `postfix-sasl`, `sshd`)
  lassen sich ändern (`jails`). Gespeichert und in `mailinabox_adaptive.conf`
  geschrieben werden nur die geänderten Werte, die übrigen folgen
  `conf/fail2ban/jails.conf`. recidive gehört nicht dazu: Es sperrt Adressen,
  die die anderen Jails immer wieder gesperrt haben.
* **Warum eine Adresse gesperrt ist** (seit v78-r2604.4). Zu jeder Sperre
  zeigt die Admin-Oberfläche die Fehlversuche und die Logzeilen, die fail2ban
  dafür aufbewahrt hat (bis zu 10, aus seiner Datenbank), die Konten der Box,
  die darin vorkommen, und die Regel des Jails (was es beobachtet, seine
  Schwellen, welche Ports es sperrt). Ein Benutzername, der kein Konto der
  Box ist, wird durch „[unknown name]“ ersetzt: Er ist, was der Client
  geschickt hat, auch ein Passwort im falschen Feld. Eine Sperre ohne
  Logzeilen wurde von Hand gesetzt.
* **Die eigene Drossel von Nextcloud** (seit v78-r2604.4). Unabhängig von
  fail2ban zählt Nextcloud fehlgeschlagene Anmeldungen je Adresse (IPv4) oder
  IPv6-Netz (standardmäßig /56, `security.ipv6_normalized_subnet_size`): Nach
  Fehlversuchen innerhalb von 12 Stunden verzögert es
  jede Anmeldung von dort (0,2 s, 0,4 s … bis 25 s), und nach mehr als 10
  Fehlversuchen (`nc_max_attempts`) innerhalb von 30 Minuten weist es sie mit
  HTTP 429 ab, auch für die Konten mit richtigem Passwort hinter dieser
  Adresse. Eine Kalender- oder Kontakte-App mit altem Passwort hält so die
  anderen Geräte ihres Netzes vom Synchronisieren ab, und eine erfolgreiche
  Anmeldung löscht nur die Fehlversuche ihres eigenen Kontos. Die
  Admin-Oberfläche listet die gezählten Adressen (Fehlversuche in 12 Stunden
  und in 30 Minuten, die versuchten Konten der Box, die Verzögerung, ob sie
  gesperrt sind) und setzt eine Adresse zurück: Sie löscht die Fehlversuche
  ihres Netzes wie `occ security:bruteforce:reset`, aber auch dort, wo dieses
  nichts tut (bei abgeschalteter Drossel, für eine Adresse auf der
  Ausnahmeliste). Die Drossel lässt sich abschalten (`nc_protection`, nicht
  empfohlen: Dann begrenzt nur noch `miab-owncloud` das Raten von Passwörtern
  bei Nextcloud); Nextcloud zählt dann keine neuen Fehlversuche, wendet die
  bisher gezählten aber noch bis zu 12 Stunden an, deshalb löscht das
  Abschalten sie. Eine Anmeldung, die da schon in der Drossel wartete, kann
  noch einen hinzufügen; bei abgeschalteter Drossel löschen das Setup und
  die täglichen Statusprüfungen solche veralteten Fehlversuche, und die
  Admin-Oberfläche zeigt sie mit einem Knopf zum Löschen an. `nc_allowlist`
  (anfangs aus)
  setzt die Freigabeliste auch auf die Ausnahmeliste von Nextcloud (was sie
  dort einträgt, wird unter `nextcloud_bypass` in settings.yaml vermerkt
  und wieder entfernt, wenn es die Freigabeliste verlässt;
  `127.0.0.1/32`, B121, und in Nextcloud gesetzte Einträge bleiben). Nur für
  eigene Netze: Eine Adresse, die man mit anderen teilt (Mobilfunk, Satellit
  und anderes Carrier-Grade-NAT), wäre auch für diese ausgenommen. Setup und
  Admin-Oberfläche schreiben `auth.bruteforce.protection.enabled` und
  `auth.bruteforce.max-attempts` in die `config.php` von Nextcloud (nur, wenn
  sie vom Standard von Nextcloud abweichen), mit
  `tools/nextcloud-bruteforce-config.php` als www-data, weil
  `occ config:system:set` die Datei ablehnt, sobald das Setup sie
  schreibgeschützt hat (`management/nextcloud_throttle.py --setup`,
  `--status`, `--reset <ip>`). Für jeden der beiden Werte einzeln: Solange
  die Einstellungen keinen eigenen Wert dafür haben, wird ein von Hand in
  `config.php` gesetzter Wert (so, wie Nextcloud ihn liest: `0` und `false`
  sind aus) übernommen statt überschrieben: Das Setup speichert ihn sofort
  und meldet das, die Admin-Oberfläche zeigt ihn an und speichert ihn beim
  nächsten Sichern. Die Übersicht nennt nur Konten der Box; sie erfährt sie,
  ohne www-data die Liste der Konten zu geben (die Anmeldenamen kommen als
  gesalzene Hashes zurück, die root mit seinen eigenen vergleicht).

Die Einstellungen stehen in `$STORAGE_ROOT/settings.yaml` unter `fail2ban`,
nur die Werte, die vom Standard abweichen. Sie überstehen so Setup-Läufe, den
Umzug und das Upgrade an Ort und Stelle (Beispiel und Grenzen siehe oben).
`bantime_max` beträgt mindestens eine Woche, damit die recidive-Sperre nie
kürzer wird. Das Setup schreibt daraus
`/etc/fail2ban/jail.d/mailinabox_adaptive.conf` und
`/etc/fail2ban/fail2ban.d/mailinabox_adaptive.conf`
(`management/fail2ban_admin.py --setup`). Ein langsames Jail, dessen Logdatei
noch fehlt, wird ausgelassen. Sind `adaptive`, `slow_jails` und
`slow_web_jails` aus, ist die Freigabeliste leer und sind keine Schwellen
geändert (`jails`), gibt es keine der beiden Dateien, also genau die
Konfiguration von upstream. Die Einstellungen `nc_*` gehen nicht in diese
Dateien. Nach einer Änderung von settings.yaml von Hand
`sudo management/fail2ban_admin.py --apply` aufrufen: Es prüft die ganze
Konfiguration mit `fail2ban-client -t`, stellt bei einer Ablehnung die alten
Dateien wieder her und lädt fail2ban nur neu, wenn sich eine Datei geändert
hat. `--print` zeigt die Dateien, `--allow 192.0.2.0/24` fügt ein Netz hinzu,
`--report` gibt den Bericht über Fehlanmeldungen aus.

In der Admin-Oberfläche zeigt **System > Intrusion Detection and Prevention**, ob fail2ban
läuft, die gesperrten Adressen (je Adresse die Jails mit Restdauer, Länge und
Beginn jeder Sperre und ihrem Grund samt Logzeilen; mit Filter), die Adressen,
die die eigene Drossel von Nextcloud zählt (mit Knopf „Reset“ und einem
Hinweis bei einer gesperrten Adresse, die auch Nextcloud drosselt), die Jails
mit ihren Zählern und den Bericht über Fehlanmeldungen (Konten mit
Fehlversuchen von vielen Adressen, Adressen, die immer wieder scheitern, mit
ihrem Sperrstatus). Dort lässt sich eine Adresse in allen Jails oder in einem
Jail freigeben, ein ganzes Jail nach Rückfrage leeren und alles einstellen:
mitwachsende Sperren und beide Arten langsamer Jails an/aus (das Ausschalten
fragt nach), die Schwellen der langsamen Jails und der Jails von
Mail-in-a-Box (Dauern auch als `30m`, `6h`, `2d`, `1w`), die Freigabeliste
(eine Adresse oder ein Netz pro Zeile), die Drossel von Nextcloud (an/aus mit
Rückfrage, Fehlversuche bis zur Sperre, Freigabeliste auf ihrer
Ausnahmeliste) und „Restore defaults“. Die Seite zeigt außerdem die Adresse, von der aus sie
benutzt wird, und bietet an, sie in die Freigabeliste aufzunehmen (bei IPv6
ihr /64, weil sich die Adresse des Browsers ändert) oder, falls gesperrt,
freizugeben (die langsamen Mail-Jails sperren nur die Mail-Ports, die
Oberfläche bleibt also erreichbar). Ungespeicherte Änderungen im
Einstellungsformular bleiben bei einer Freigabe erhalten. Sie nutzt die oben beschriebene API
unter `/admin/system/fail2ban` und `/admin/system/nextcloud-throttle` (nur
für Administratoren, Änderungen per POST mit Formularfeldern).

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
    # after reading the check:
    curl -s https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/tools/upgrade-in-place-to-2604.sh \
      | sudo bash

Started from a terminal outside tmux or screen, the tool runs itself in the
tmux session `upgrade-2604` (it installs tmux if needed, or falls back to
screen) and attaches your terminal to it. If the SSH connection drops, the
upgrade goes on: log in again and run `sudo tmux attach -t upgrade-2604`.
When the command has ended, the window stays open until you press Enter
(with `--yes` at most 10 minutes, so that a script calling it through
`ssh -t` gets its exit code). After a reboot the tool continues in a new
tmux session of the same name (`upgrade-2604`; the output from before the
reboot is in the log); when the upgrade has succeeded, its window closes by
itself after 60 seconds, after a failure it stays open.
`--no-tmux` turns this off.

Through `curl | bash`, the tool runs the copy of the release tag (`TAG`,
default: the latest release). Releases up to v78-r2604.0-rc3 do not start
tmux by themselves: with those, start the command inside tmux yourself
(`tmux new -s upgrade-2604`), or take the branch `main` with
`... | sudo TAG=main bash`. The tool warns before it runs such a copy.

What it does, in phases that continue on their own after each reboot:

1. **preflight**: release, Mail-in-a-Box and Nextcloud versions, disk space,
   a backup younger than 24 hours (a backup that is running, e.g. the nightly
   one, does not block: the upgrade waits for it, at most 2 hours,
   `UPGRADE_BACKUP_WAIT`, before it stops anything; the nightly job runs at
   a random minute between 01:00 and 01:59 (system time), the one in
   `/etc/cron.d/mailinabox-nightly`, which every setup run picks anew), and
   a list of
   everything that is not managed by Mail-in-a-Box (Dovecot plugins, systemd
   drop-ins, nginx files, Docker, third-party apt sources). Local extensions
   block the upgrade until you pass `--keep-local`.
2. **snapshot**: a system archive (`/etc` as it was, the code outside the
   data directory, package lists), encrypted with the backup key and copied
   next to the backups (for an rsync target: `<target>-system/`; for backups
   on the machine itself it stays in `/root/upgrade-2604`). Then mail,
   web, cron and the update timers are stopped and masked, so they stay off
   across reboots. **Mail is offline from here.** Then a fresh Mail-in-a-Box
   backup (so it holds all mail) and counts and key fingerprints. With
   `--skip-miab-backup` (or backups turned off) there is no fresh backup, and
   mail keeps running until quiesce.
3. **quiesce**: the backups are paused until the end, and mail goes offline
   here if it is not yet.
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
   backups and timers back on. A Postfix restriction from before that setup
   dropped (an item of `smtpd_*_restrictions`) is a failed check: redo it in
   `main.cf` or accept the result with `--finish`. The greylisting exceptions
   (see above) are kept by setup.

Services of your own that use the mail (e.g. a docker compose stack that logs
in by IMAP or receives Dovecot push calls) can be stopped and started with
hooks in two more directories: `/etc/mailinabox/upgrade-2604.d/before/*.sh`
run right before mail goes offline, `/etc/mailinabox/upgrade-2604.d/after/*.sh`
in phase finish, after mail and the backups are back (and at the end of
`--rollback`). They get the same variables, and `HOOK_STAGE` (`before`,
`local-ext`, `after`). A failing before hook stops the upgrade before mail is
stopped; a failing after hook only warns. If the final check fails, the after
hooks run right after it (mail runs again, the backups stay paused) and not
again in finish. Write hooks so that they can run twice. For example:

    # /etc/mailinabox/upgrade-2604.d/before/10-myapp.sh
    cd /opt/myapp && docker compose stop

    # /etc/mailinabox/upgrade-2604.d/after/10-myapp.sh
    cd /opt/myapp && docker compose up -d

**Local changes to Roundcube** (webmail) do not stop the upgrade: setup
installs the new Roundcube as a new tree in `/usr/local/lib/roundcubemail`
and writes its own `config/config.inc.php` (on every run, also on later
updates). The preflight check (also `--check`) names plugin directories that
setup does not install, plugins added to or left out of the plugin list, and
other settings of `config.inc.php` that differ from what setup writes (of a
setting that setup does not write only its name: its value may be a
password). Before setup the tool keeps the old `config.inc.php` and those
plugin directories in `/root/upgrade-2604/old-roundcube` (the system archive
keeps the whole old tree). They are not copied back on their own: a plugin
for the old Roundcube can break the new one. Phase verify lists what the new
Roundcube does not have (also in `etc-report.txt`) and writes it to
`/root/upgrade-2604/local-changes.json` (root's only); while that file exists,
System Status shows a warning with the items under "show more", so the daily
status mail names it too. Bring back what the new Roundcube supports with a
hook, for example:

    # /etc/mailinabox/upgrade-2604.d/50-roundcube.sh
    RC=/usr/local/lib/roundcubemail
    cp -a "$UPGRADE_STATE_DIR/old-roundcube/plugins/contextmenu" "$RC/plugins/"
    grep -q "'contextmenu'" "$RC/config/config.inc.php" \
      || sed -i "s/^\(\$config\['plugins'\] = array(\)/\1'contextmenu', /" "$RC/config/config.inc.php"

and run `--redo-from local-ext`, which checks again. `cp -a` keeps the
plugin's modes as they were in the old Roundcube; the web server (www-data)
must be able to read the plugin, and phase verify names one that it cannot
read (Roundcube does not load it then). When everything is dealt
with (or not wanted), `upgrade-in-place-to-2604.sh --ack-local` (or removing
the file) ends the warning. Setup writes `config.inc.php` again on the next
update, so keep such a change in a script of your own.

**How long an in-place upgrade takes.** Times of the in-place test runs
(test VMs with 2 vCPUs and 4-6 GB RAM on one host with HDD storage):

| Run | 22.04 → 24.04 | 24.04 → 26.04 | Setup | Mail offline | Reboots |
|---|---|---|---|---|---|
| From 22.04, no other test run on the host | 33-34 min | 29-31 min | 15-16 min | 1 h 21 min - 1 h 25 min | 2 |
| From 22.04, other test runs on the same disks at the same time | 45-73 min | 31-41 min | 15-17 min | 1 h 36 min - 2 h 18 min | 2 |
| From 24.04 (copy of a production box), no other test run on the host | – | 33-41 min | 15-16 min | 50 min - 1 h 01 min | 1 |
| From 24.04 (copy of a production box), other test runs at the same time | – | 46-72 min | 18-23 min | 1 h 08 min - 1 h 41 min | 1 |

A production box (from 24.04, on its own server) was without mail
for 1 h 10 min.

* **What makes it slower:** slow disks, and other load on the same storage
  (other virtual machines, a backup or a large copy at the same time). The
  release upgrades replace most of the system's packages; on disks
  shared with up to five other test runs they took about twice as long. A
  full backup in phase snapshot adds its own time (see below).
* **When mail is offline:** from phase snapshot, before the fresh backup,
  until the end of phase setup (with `--skip-miab-backup`, from phase
  quiesce); the column "Mail offline" is that window.
  Users cannot read or send mail in it. Other mail servers cannot deliver
  and try again later (usually for several days), so incoming mail arrives
  after the upgrade. New SSH logins on port 22 fail for a while during each
  release upgrade, and `sudo` is missing for a while from 24.04 to 26.04
  (see "Logging in during the release upgrades" below).
* **Plan 1-3 hours** of mail outage and announce it. Keep a root shell
  open, and do not reboot while a release upgrade runs, even when it seems
  to hang.

The fresh backup is part of the downtime: a few minutes when it is incremental, much longer when
backup.py makes a full backup (when there is none yet, or on a Saturday or
Sunday after many changes or about a month since the last full one);
`--check` shows the estimate. The release upgrades cannot be undone:
`--rollback` only works before the first one. After that the way back is the
backup. Have the provider's console at hand, SSH can be gone for a while
during the release upgrade or after a reboot.
`--status` shows where it stands; running the command again continues.
`--cleanup-only` removes leftovers of the old releases afterwards.

**Logging in during the release upgrades.** While do-release-upgrade
replaces the SSH server, new SSH logins on port 22 fail for a while (in
the test runs 19 to 42 minutes from 22.04 to 24.04 and 6 to 19 minutes from
24.04 to 26.04, the longer times on a busy disk; from rc7 on the fallback
SSH server below takes key logins of the administrators meanwhile).
Connections that are open stay open, and the upgrade goes on in tmux. From
24.04 to 26.04, `sudo` is also missing for 12 to 37 minutes, while sudo-rs
replaces it:
`sudo tmux attach -t upgrade-2604` then fails with "command not found". In the same release upgrade tmux 3.6 replaces
tmux 3.4 a few minutes after the start. From then until the reboot a new
`tmux attach` cannot reach the run ("open terminal failed: not a
terminal"); a client attached before stays attached. Follow the log
instead: `sudo tail -f /root/upgrade-2604/upgrade.log`. After the reboot
`sudo tmux attach -t upgrade-2604` works again. The tool says so before
each release upgrade, and before a reboot after which a release upgrade
starts by itself (from 22.04 the second one always does). To watch a
release upgrade that starts without a reboot, attach before it starts and
keep that connection open (a root shell opened before with `sudo -i` works
as well). After a reboot it starts before you can attach. If a new login
fails or `sudo` is missing, wait a few minutes and try again. Do not reboot: a release upgrade stopped in the
middle can leave the machine unbootable.

Why: openssh-server stops `ssh.socket` and `ssh.service` when the new
package is unpacked and starts them again only when it is configured, near
the end; nothing listens on port 22 in between. From rc7 on, the tool runs a
**fallback SSH server on port 1022** for the time of each release upgrade
(`UPGRADE_SSH_FALLBACK_PORT=PORT` chooses another port, `off` turns it off):
`ssh -p 1022 you@box`. It runs from a private copy of the old sshd, accepts
only keys, and only of the administrators (members of the groups sudo and
admin, and root if `PermitRootLogin` allows keys;
`UPGRADE_SSH_FALLBACK_USERS="..."` names others), listens on the addresses
of `sshd_config` (ListenAddress), keeps its AllowUsers, AllowGroups,
DenyUsers, DenyGroups, PubkeyAuthOptions, ForceCommand and ChrootDirectory
and allows no forwarding. With StrictModes (sshd's default) it takes only
the key files that sshd accepts: one whose path up to the home directory
another account can write (others, or a group with other members) is
skipped with a warning, as sshd ignores it.
Where sshd asks for more than a key
(`AuthenticationMethods`, e.g. a key and a one-time password) or
`sshd_config` or a file it includes has `Match` blocks, there is no fallback (it would let in with
a key alone); keep a connection open instead. ufw lets the port through
only while it runs; a firewall of the provider must allow it too. Try it before the upgrade with
`--ssh-fallback-test` (10 minutes). The run says when the SSH port (22,
or the ports set in `sshd_config`) stops answering and when it answers
again. The fallback is stopped when the SSH port works again, also when the
tool stops with an error; while the SSH port does not answer, the fallback
stays until the next reboot, and the next run removes it and its firewall
rule.

In the rc7 test runs (OpenSSH 8.9 of 22.04 and 9.6 of 24.04 as the
fallback, also on a box without a group `admin`) a new key login on port
1022 worked through the whole outage of port 22, except for about 20
seconds in the release upgrade from 22.04, when the library switch from
`libtirpc3` to `libtirpc3t64` stops every new sshd on both ports; a user
who is not an administrator was refused there. The fallback ends at the
reboot of the release upgrade: if port 22 does not answer after it, use the
provider's console. Before the upgrade:

    curl -s https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/tools/upgrade-in-place-to-2604.sh \
      | sudo bash -s -- --ssh-fallback-test
    # from your workstation, while the test runs:
    ssh -p 1022 you@box.example.net

`tools/update-check.sh before` and `backup` (see "Updating the fork") also
run on the old box before the upgrade, through `curl ... | sudo bash -s --
STEP`; they find its checkout in `/mailinabox`. After the upgrade `after`
lists the changes without judging them ("RESULT: NOT JUDGED", exit code 3),
since a release upgrade changes almost everything, and still runs the log
audit against the baseline (a new message class: exit code 1), with
`tests/fork/log-audit-allow-old-box.txt` for what the old release logged
before the upgrade stopped mail; `mailcheck` works as after an update.

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
    # nach Durchsicht der Prüfung:
    curl -s https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/tools/upgrade-in-place-to-2604.sh \
      | sudo bash

Aus einem Terminal außerhalb von tmux oder screen gestartet, läuft das
Werkzeug selbst in der tmux-Sitzung `upgrade-2604` (tmux wird bei Bedarf
installiert, sonst dient screen als Ersatz) und hängt das Terminal daran.
Reißt die SSH-Verbindung ab, läuft das Upgrade weiter: neu anmelden und
`sudo tmux attach -t upgrade-2604` aufrufen. Nach dem Ende des Befehls bleibt
das Fenster offen, bis Enter gedrückt wird (mit `--yes` höchstens 10 Minuten,
damit ein Skript, das den Befehl über `ssh -t` aufruft, seinen Exit-Code
bekommt). Nach einem Neustart läuft das Werkzeug in einer neuen
tmux-Sitzung gleichen Namens weiter (`upgrade-2604`; die Ausgabe von vor dem
Neustart steht im Log); ist das Upgrade gelungen, schließt sich ihr Fenster
nach 60 Sekunden von selbst, nach einem Fehler bleibt es offen.
`--no-tmux` schaltet das ab.

Über `curl | bash` führt das Werkzeug die Fassung des Release-Tags aus (`TAG`,
vorgegeben: das neueste Release). Releases bis v78-r2604.0-rc3 starten tmux
noch nicht selbst: mit ihnen den Befehl selbst in tmux starten
(`tmux new -s upgrade-2604`) oder mit `... | sudo TAG=main bash` den Zweig
`main` nehmen. Das Werkzeug warnt, bevor es eine solche Fassung ausführt.

Ablauf in Phasen, die nach jedem Neustart von selbst weiterlaufen:

1. **preflight**: Release, Versionen von Mail-in-a-Box und Nextcloud,
   Speicherplatz, eine Sicherung jünger als 24 Stunden (eine laufende
   Sicherung, etwa die nächtliche, hält nichts an: das Upgrade wartet auf sie,
   höchstens 2 Stunden, `UPGRADE_BACKUP_WAIT`, bevor es etwas anhält; die
   nächtliche Aufgabe läuft zu einer zufälligen Minute zwischen 01:00 und
   01:59 Uhr (Systemzeit), der in `/etc/cron.d/mailinabox-nightly`, die
   jeder Lauf von setup neu wählt) und
   eine Liste von allem, was Mail-in-a-Box nicht verwaltet (Dovecot-Plugins,
   systemd-Drop-ins, nginx-Dateien, Docker, fremde Paketquellen). Lokale
   Erweiterungen halten das Upgrade an, bis `--keep-local` angegeben wird.
2. **snapshot**: ein Systemarchiv (`/etc` im alten Zustand, der Code
   außerhalb des Datenverzeichnisses, Paketlisten), mit dem Backup-Schlüssel
   verschlüsselt und neben die Sicherungen gelegt (bei einem rsync-Ziel:
   `<ziel>-system/`; bei Sicherungen auf der Maschine selbst bleibt es in
   `/root/upgrade-2604`). Danach werden Mail, Web, Cron und die Update-Timer
   angehalten und maskiert, damit sie auch über Neustarts hinweg aus bleiben.
   **Ab hier ist die Mail aus.** Dann eine frische Mail-in-a-Box-Sicherung
   (damit sie alle Mails enthält) sowie Zählungen und
   Schlüssel-Fingerabdrücke. Mit `--skip-miab-backup` (oder abgeschalteten
   Sicherungen) gibt es keine frische Sicherung, und die Mail läuft bis
   quiesce weiter.
3. **quiesce**: Die Sicherungen werden bis zum Ende ausgesetzt; ist die Mail
   noch an, geht sie hier aus.
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
   Konfiguration; Sicherungen und Timer wieder an. Eine Postfix-Regel von
   vorher, die setup verworfen hat (ein Eintrag in `smtpd_*_restrictions`),
   gilt als fehlgeschlagene Prüfung: in `main.cf` wieder eintragen oder das
   Ergebnis mit `--finish` annehmen. Die Ausnahmen vom Greylisting (siehe oben)
   behält setup bei.

Eigene Dienste, die die Mail nutzen (etwa ein docker-compose-Stack, der sich
per IMAP anmeldet oder Push-Aufrufe von Dovecot empfängt), lassen sich mit
Hooks in zwei weiteren Verzeichnissen anhalten und starten:
`/etc/mailinabox/upgrade-2604.d/before/*.sh` laufen unmittelbar, bevor die
Mail ausgeht, `/etc/mailinabox/upgrade-2604.d/after/*.sh` in der Phase finish,
nachdem Mail und Sicherungen wieder laufen (und am Ende von `--rollback`).
Sie bekommen dieselben Variablen und dazu `HOOK_STAGE` (`before`,
`local-ext`, `after`). Ein fehlschlagender before-Hook hält das Upgrade an,
bevor die Mail angehalten wird; ein fehlschlagender after-Hook warnt nur.
Schlägt die Schlussprüfung fehl, laufen die after-Hooks gleich danach (die
Mail läuft wieder, die Sicherungen bleiben ausgesetzt) und in finish nicht
noch einmal. Hooks so schreiben, dass sie zweimal laufen dürfen. Beispiel:

    # /etc/mailinabox/upgrade-2604.d/before/10-myapp.sh
    cd /opt/myapp && docker compose stop

    # /etc/mailinabox/upgrade-2604.d/after/10-myapp.sh
    cd /opt/myapp && docker compose up -d

**Lokale Änderungen an Roundcube** (Webmail) halten das Upgrade nicht an:
Setup installiert das neue Roundcube als neuen Baum in
`/usr/local/lib/roundcubemail` und schreibt seine eigene
`config/config.inc.php` (bei jedem Lauf, auch bei späteren Updates). Die
Vorabprüfung (auch `--check`) nennt Plugin-Verzeichnisse, die setup nicht
installiert, Plugins, die der Plugin-Liste hinzugefügt oder aus ihr
weggelassen wurden, und andere Einstellungen der `config.inc.php`, die von
dem abweichen, was setup schreibt (bei einer Einstellung, die setup nicht
schreibt, nur ihren Namen: ihr Wert kann ein Passwort sein). Vor setup
bewahrt das Werkzeug die alte `config.inc.php` und diese
Plugin-Verzeichnisse in `/root/upgrade-2604/old-roundcube` auf (das
Systemarchiv enthält den ganzen alten Baum). Sie werden nicht von selbst
zurückkopiert: Ein Plugin für das alte Roundcube kann das neue stören. Die
Phase verify listet, was dem neuen Roundcube fehlt (auch in
`etc-report.txt`), und schreibt es in `/root/upgrade-2604/local-changes.json`
(nur für root lesbar); solange es diese Datei gibt, zeigt der Systemstatus
eine Warnung mit den Punkten unter „show more“, die tägliche Statusmail
nennt sie also auch. Was das neue Roundcube unterstützt, holt ein Hook
zurück, zum Beispiel:

    # /etc/mailinabox/upgrade-2604.d/50-roundcube.sh
    RC=/usr/local/lib/roundcubemail
    cp -a "$UPGRADE_STATE_DIR/old-roundcube/plugins/contextmenu" "$RC/plugins/"
    grep -q "'contextmenu'" "$RC/config/config.inc.php" \
      || sed -i "s/^\(\$config\['plugins'\] = array(\)/\1'contextmenu', /" "$RC/config/config.inc.php"

und danach `--redo-from local-ext`, das erneut prüft. `cp -a` behält die
Rechte des Plugins aus dem alten Roundcube; der Webserver (www-data) muss das
Plugin lesen können, und die Phase verify nennt eines, das er nicht lesen
kann (Roundcube lädt es dann nicht). Ist alles erledigt
(oder nicht mehr gewünscht), beendet `upgrade-in-place-to-2604.sh
--ack-local` (oder das Löschen der Datei) die Warnung. Setup schreibt
`config.inc.php` beim nächsten Update wieder neu; eine solche Änderung also
in einem eigenen Skript aufbewahren.

**Wie lange ein Upgrade an Ort und Stelle dauert.** Zeiten der
In-place-Testläufe (Test-VMs mit 2 vCPUs und 4-6 GB RAM auf einem Host mit
HDD-Speicher):

| Lauf | 22.04 → 24.04 | 24.04 → 26.04 | Setup | Mail aus | Neustarts |
|---|---|---|---|---|---|
| Ab 22.04, kein anderer Testlauf auf dem Host | 33-34 min | 29-31 min | 15-16 min | 1 h 21 min - 1 h 25 min | 2 |
| Ab 22.04, gleichzeitig andere Testläufe auf denselben Platten | 45-73 min | 31-41 min | 15-17 min | 1 h 36 min - 2 h 18 min | 2 |
| Ab 24.04 (Kopie einer Produktivbox), kein anderer Testlauf auf dem Host | – | 33-41 min | 15-16 min | 50 min - 1 h 01 min | 1 |
| Ab 24.04 (Kopie einer Produktivbox), gleichzeitig andere Testläufe | – | 46-72 min | 18-23 min | 1 h 08 min - 1 h 41 min | 1 |

Eine Produktivbox (ab 24.04, auf eigenem Server) war 1 h 10 min ohne
Mail.

* **Was es verlangsamt:** langsame Platten und andere Last auf demselben
  Speicher (andere virtuelle Maschinen, eine Sicherung oder eine große Kopie
  zur selben Zeit). Die Release-Upgrades ersetzen die meisten Pakete
  des Systems; auf Platten, die sich bis zu fünf andere Testläufe
  teilten, dauerten sie etwa doppelt so lange. Eine Vollsicherung in der
  Phase snapshot braucht zusätzlich Zeit (siehe unten).
* **Wann die Mail aus ist:** ab der Phase snapshot, vor der frischen
  Sicherung, bis zum Ende der Phase setup (mit `--skip-miab-backup` ab der Phase
  quiesce); die Spalte „Mail aus“ ist dieses
  Fenster. Die Benutzer können darin keine Mail lesen oder senden. Andere
  Mailserver können nicht zustellen und versuchen es später erneut (meist
  über mehrere Tage); eingehende Mail kommt also nach dem Upgrade an. Neue
  SSH-Anmeldungen auf Port 22 schlagen während jedes Release-Upgrades eine
  Zeit lang fehl, und von 24.04 auf 26.04 fehlt `sudo` eine Zeit lang
  (siehe „Anmelden während der Release-Upgrades“ unten).
* **1 bis 3 Stunden** Mailausfall einplanen und ankündigen. Eine root-Shell
  offen lassen und während eines Release-Upgrades nicht neu starten, auch
  wenn es zu hängen scheint.

Die frische Sicherung zählt zur Ausfallzeit: einige Minuten, wenn
sie inkrementell ist, viel länger, wenn backup.py eine Vollsicherung macht
(wenn es noch keine gibt, oder an einem Samstag oder Sonntag nach vielen
Änderungen oder etwa einem Monat seit der letzten Vollsicherung); `--check`
zeigt die Schätzung. Die Release-Upgrades lassen sich nicht zurücknehmen:
`--rollback` geht nur vor dem ersten. Danach führt der Weg zurück über die
Sicherung. Die Konsole des Anbieters sollte bereitliegen, weil SSH während
des Release-Upgrades oder nach einem Neustart eine Weile weg sein kann.
`--status` zeigt den Stand; ein erneuter Aufruf setzt fort. `--cleanup-only`
räumt danach die Reste der alten Releases weg.

**Anmelden während der Release-Upgrades.** Solange do-release-upgrade den
SSH-Server ersetzt, schlagen neue SSH-Anmeldungen auf Port 22 eine Weile
fehl (in den Testläufen 19 bis 42 Minuten von 22.04 auf 24.04 und 6 bis 19
Minuten von 24.04 auf 26.04, die längeren Zeiten bei ausgelasteter Platte;
ab rc7 nimmt der Ersatz-SSH-Server unten derweil die Schlüssel-Anmeldungen
der Administratoren an). Offene Verbindungen bleiben bestehen, und das
Upgrade läuft in tmux weiter. Von 24.04 auf 26.04 fehlt außerdem `sudo` für
12 bis 37 Minuten, weil sudo-rs es ersetzt: `sudo tmux attach -t upgrade-2604`
scheitert dann mit „command not found“. Im selben Release-Upgrade ersetzt
tmux 3.6 einige Minuten nach dem Start tmux 3.4. Von da an bis zum Neustart
erreicht ein neues `tmux attach` den Lauf nicht mehr („open terminal
failed: not a terminal“); ein vorher angehängter Client bleibt angehängt.
Stattdessen dem Protokoll folgen: `sudo tail -f
/root/upgrade-2604/upgrade.log`. Nach dem Neustart geht `sudo tmux attach
-t upgrade-2604` wieder. Das Werkzeug weist vor jedem Release-Upgrade
darauf hin, und vor einem Neustart, nach dem ein
Release-Upgrade von selbst beginnt (von 22.04 aus beginnt das zweite immer
so). Wer ein Release-Upgrade ohne vorherigen Neustart verfolgen will, hängt
sich vorher an und lässt diese Verbindung offen (eine vorher mit `sudo -i`
geöffnete Root-Shell geht auch). Nach einem Neustart beginnt es, bevor man
sich anhängen kann. Scheitert eine neue Anmeldung oder fehlt `sudo`, einige Minuten
warten und es erneut versuchen. Nicht neu starten: ein mitten im Lauf
abgebrochenes Release-Upgrade kann die Maschine so hinterlassen, dass sie
nicht mehr startet.

Der Grund: openssh-server hält `ssh.socket` und `ssh.service` an, wenn das
neue Paket entpackt wird, und startet sie erst wieder, wenn es eingerichtet
wird, gegen Ende; dazwischen hört niemand auf Port 22. Ab rc7 lässt das
Werkzeug für die Dauer jedes Release-Upgrades einen **Ersatz-SSH-Server auf
Port 1022** laufen (`UPGRADE_SSH_FALLBACK_PORT=PORT` wählt einen anderen
Port, `off` schaltet ihn ab): `ssh -p 1022 name@box`. Er läuft aus einer
eigenen Kopie des alten sshd, nimmt nur Schlüssel an, und nur die der
Administratoren (Mitglieder der Gruppen sudo und admin, und root, wenn
`PermitRootLogin` Schlüssel erlaubt; `UPGRADE_SSH_FALLBACK_USERS="..."` nennt
andere), hört auf den Adressen aus `sshd_config` (ListenAddress), behält
dessen AllowUsers, AllowGroups, DenyUsers, DenyGroups, PubkeyAuthOptions,
ForceCommand und ChrootDirectory und erlaubt keine Weiterleitungen. Mit
StrictModes (Voreinstellung von sshd) nimmt er nur die Schlüsseldateien,
die sshd annimmt: Eine, deren Pfad bis zum Heimatverzeichnis ein anderes
Konto beschreiben kann (andere, oder eine Gruppe mit weiteren Mitgliedern),
lässt er mit einer Warnung aus, wie sshd sie übergeht. Wo sshd
mehr als einen Schlüssel verlangt (`AuthenticationMethods`, etwa Schlüssel
und Einmalpasswort) oder `sshd_config` oder eine eingebundene Datei
`Match`-Blöcke hat, gibt es keinen
Ersatz-Server (er ließe mit dem Schlüssel allein herein); dann eine
Verbindung offen halten. ufw lässt den Port nur durch, solange er läuft;
eine Firewall des Anbieters muss ihn ebenfalls erlauben. Vor dem Upgrade lässt er sich mit `--ssh-fallback-test`
ausprobieren (10 Minuten). Der Lauf meldet, wann der SSH-Port (22 oder
die Ports aus `sshd_config`) nicht mehr antwortet und wann wieder. Der
Ersatz-Server wird beendet, sobald der SSH-Port wieder geht, auch wenn das
Werkzeug mit einem Fehler abbricht; antwortet der SSH-Port nicht, bleibt der
Ersatz-Server bis zum nächsten Neustart, und der nächste Lauf entfernt ihn
und seine Firewall-Regel.

In den Testläufen von rc7 (OpenSSH 8.9 von 22.04 und 9.6 von 24.04 als
Ersatz-Server, auch auf einer Box ohne Gruppe `admin`) ging eine neue
Schlüssel-Anmeldung auf Port 1022 während des ganzen Ausfalls von Port 22,
außer etwa 20 Sekunden lang im Release-Upgrade von 22.04, wenn der Wechsel
der Bibliothek `libtirpc3` auf `libtirpc3t64` jeden neuen sshd auf beiden
Ports scheitern lässt; ein Benutzer, der kein Administrator ist, wurde dort
abgewiesen. Der Ersatz-Server endet mit dem Neustart des Release-Upgrades:
Antwortet Port 22 danach nicht, hilft die Konsole des Anbieters. Vor dem
Upgrade:

    curl -s https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/tools/upgrade-in-place-to-2604.sh \
      | sudo bash -s -- --ssh-fallback-test
    # vom eigenen Rechner aus, während der Test läuft:
    ssh -p 1022 name@box.example.net

`tools/update-check.sh before` und `backup` (siehe „Fork aktualisieren“)
laufen auch auf der alten Box vor dem Upgrade, über `curl ... | sudo bash
-s -- SCHRITT`; sie finden ihren Checkout in `/mailinabox`. Nach dem Upgrade
führt `after` die Änderungen auf, ohne sie zu bewerten („RESULT: NOT
JUDGED“, Exit-Code 3), weil ein Release-Upgrade fast alles ändert, und
lässt das Log-Audit trotzdem gegen die Vergleichsbasis laufen (eine neue
Meldungsklasse: Exit-Code 1), mit `tests/fork/log-audit-allow-old-box.txt`
für das, was das alte Release vor dem Anhalten der Mail protokolliert hat;
`mailcheck` geht wie nach einem Update.

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
   `--from admin@old.example.com`. An IPv6 address works with or without
   brackets (`--from root@[2001:db8::1]`). `--check` logs in and runs
   rsync once, as the copy will ("rsync: works").
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
9. **tmux**: the tool runs itself in tmux, see below.
10. Optional, for big boxes: **rehearse** first, see "Downtime and rehearsal".
11. **Fork settings**: full-text search and Nextcloud sharing within the mail
    domain are on by default. To turn them off, give `FTS=off` or
    `NEXTCLOUD_SHARE_SCOPE=all` to the tool
    (`NEXTCLOUD_SHARE_SCOPE=all /root/mailinabox/tools/migrate-to-2604.sh --from ...`),
    or put them into `/etc/mailinabox.conf` on the new machine after a
    rehearsal: the real run keeps them.

#### Quick start

> **tmux**: the copy and setup take hours. If your SSH connection dropped
> outside tmux, they would stop halfway, possibly while the old box is
> already stopped and in the middle of a Nextcloud upgrade. So the tool,
> started from a terminal outside tmux or screen, runs itself in the tmux
> session `migrate-2604` (it installs tmux if needed, or falls back to
> screen) and attaches your terminal to it. After a disconnect, log in again
> and run `sudo tmux attach -t migrate-2604`. When the command has ended, the
> window stays open until you press Enter (with `--yes` at most 10 minutes,
> so that a script calling it through `ssh -t` gets its exit code).
> `--no-tmux` turns this off.

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
like `bootstrap.sh`, at the current release tag). `TAG` and `SOURCE` go
after `sudo`:

	curl -s https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/tools/migrate-to-2604.sh \
	  | sudo bash -s -- --from root@old.example.com

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
3. **stop-old** (asks first): waits for a Mail-in-a-Box backup that runs on
   the old box (e.g. the nightly one; at most 2 hours, `MIGRATE_BACKUP_WAIT`),
   then stops cron, the apt timers (package updates
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
  storage path). The `.migrate-to-2604-partial` directories (up to
  v78-r2604.1 `.rsync-partial`) keep interrupted files out of their real
  place.
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
  `mail/users.sqlite` (root:root 0600, B210), `www` (owner `user-data`).
* After setup, every parked owner is mapped by its old name (from the old
  `/etc/passwd` and `/etc/group`) to the new ID. An owner whose name does
  not exist on the new machine keeps its old number only if that number is
  unused there; if it belongs to another account (e.g. an admin user 1000 on
  the old box and `ubuntu` = 1000 on the new one), the files go to root. Both
  cases are reported.

The new machine must accept 32-bit user IDs (VMs and servers do; some
containers do not, the tool checks).

#### Not migrated

* Changes to `/etc` (e.g. extra Postfix maps, postgrey whitelists,
  SpamAssassin rules, fail2ban jails, cron jobs, firewall rules). The old
  `/etc`, as of the final copy, is kept in `/root/migration/old-etc.tar.gz`
  (unpacked in `/root/migration/old-etc`), and
  `/root/migration/etc-report.txt` lists Postfix settings that differ, files
  named in them and files that exist only on the old box. An item of
  `smtpd_*_restrictions` of the old box that is gone here is a failed check
  (redo it in `main.cf`, or accept the result with `--finish`). Only the
  greylisting exceptions (`/etc/postfix/greylist_bypass_senders`, see above)
  are taken over, before setup. A backup (`--from-backup`) does not contain
  them: copy the file over yourself and run setup again.
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
* Local changes to Roundcube (webmail; it is not part of the data, setup
  installs its own and writes its own `config/config.inc.php`). The check
  (also `--check`) names plugin directories of the old box that setup does
  not install and changes of its `config.inc.php` (the plugin list, and other
  settings; of a setting that setup does not write only its name). The tool
  keeps the old `config.inc.php` and those plugin directories in
  `/root/migration/old-roundcube`, but does not install them (a plugin for
  the old Roundcube can break the new one). Phase verify lists what the new
  Roundcube does not have (also in `etc-report.txt`) and writes it to
  `/root/migration/local-changes.json` (root's only); while that file exists,
  System Status shows a warning with the items under "show more", and so
  does the daily status mail. Bring back what the new Roundcube supports
  (copy the plugin directory to `/usr/local/lib/roundcubemail/plugins/` and
  add it to `$config['plugins']`; setup writes the file again on every run;
  the web server, www-data, must be able to read the plugin, which phase
  verify checks), then end the warning with `migrate-to-2604.sh --ack-local` (or remove the
  file). Not with `--from-backup`: a backup has no Roundcube.

#### After the migration

##### 1. Test before switching DNS

Put the line `<new IP> <hostname>` into the hosts file of your own computer
(`/etc/hosts`; Windows: `C:\Windows\System32\drivers\etc\hosts`). Then open
`https://<hostname>/admin` and `https://<hostname>/mail`, log in, send a test
mail through the new box (SMTP submission) and receive one, and check
Nextcloud (files, contacts, calendars). Remove the line afterwards.

Webmail users must log in again: Roundcube on the new machine has a key of
its own, not the old box's. The spam filter (Bayes) and the greylisting
database are taken over as they are.

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
	sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/setup/bootstrap.sh)"
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
   `--from admin@alt.example.com`. Eine IPv6-Adresse geht mit oder ohne
   eckige Klammern (`--from root@[2001:db8::1]`). `--check` meldet sich an
   und ruft rsync einmal so auf wie später die Kopie („rsync: works“).
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
9. **tmux**: das Werkzeug läuft selbst in tmux, siehe unten.
10. Optional, bei großen Boxen: zuerst **proben**, siehe „Ausfallzeit und
    Probelauf“.
11. **Einstellungen des Forks**: Volltextsuche und Teilen in Nextcloud nur
    innerhalb der Maildomain sind standardmäßig an. Zum Abschalten
    `FTS=off` oder `NEXTCLOUD_SHARE_SCOPE=all` an das Werkzeug übergeben
    (`NEXTCLOUD_SHARE_SCOPE=all /root/mailinabox/tools/migrate-to-2604.sh --from ...`)
    oder nach einem Probelauf in `/etc/mailinabox.conf` der neuen Maschine
    eintragen: Der eigentliche Lauf behält sie bei.

#### Schnellstart

> **tmux**: Kopie und Setup dauern Stunden. Bräche die SSH-Verbindung
> außerhalb von tmux ab, endeten sie mittendrin, womöglich bei schon
> angehaltener alter Box und mitten in einem Nextcloud-Upgrade. Deshalb
> läuft das Werkzeug, aus einem Terminal außerhalb von tmux oder screen
> gestartet, selbst in der tmux-Sitzung `migrate-2604` (tmux wird bei Bedarf
> installiert, sonst dient screen als Ersatz) und hängt das Terminal daran.
> Nach einem Verbindungsabbruch neu anmelden und
> `sudo tmux attach -t migrate-2604` aufrufen. Nach dem Ende des Befehls bleibt
> das Fenster offen, bis Enter gedrückt wird (mit `--yes` höchstens 10
> Minuten, damit ein Skript, das den Befehl über `ssh -t` aufruft, seinen
> Exit-Code bekommt). `--no-tmux` schaltet das ab.

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
`/root/mailinabox`, beim aktuellen Release-Tag). `TAG` und `SOURCE` stehen
hinter `sudo`:

	curl -s https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/tools/migrate-to-2604.sh \
	  | sudo bash -s -- --from root@alt.example.com

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
3. **stop-old** (mit Rückfrage): wartet auf eine Mail-in-a-Box-Sicherung, die
   auf der alten Box läuft (etwa die nächtliche; höchstens 2 Stunden,
   `MIGRATE_BACKUP_WAIT`), und hält dann auf der alten Box cron, die apt-Timer
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
  Datenpfad). Die Verzeichnisse `.migrate-to-2604-partial` (bis
  v78-r2604.1 `.rsync-partial`) halten abgebrochene Dateien von ihrem
  eigentlichen Platz fern.
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
  `mail/users.sqlite` (root:root 0600, B210), `www` (Besitzer `user-data`).
* Nach dem Setup wird jeder geparkte Besitzer über seinen alten Namen (aus
  `/etc/passwd` und `/etc/group` der alten Box) auf die neue Kennung gesetzt.
  Gibt es den Namen auf der neuen Maschine nicht, behält der Besitzer seine
  alte Zahl nur, wenn sie dort unbenutzt ist; gehört sie einem anderen Konto
  (z. B. ein Administrator mit 1000 auf der alten Box und `ubuntu` = 1000 auf
  der neuen), bekommt root die Dateien. Beide Fälle werden gemeldet.

Die neue Maschine muss 32-Bit-Benutzerkennungen annehmen (VMs und Server tun
das, manche Container nicht; das Werkzeug prüft es).

#### Nicht übernommen

* Änderungen in `/etc` (z. B. zusätzliche Postfix-Tabellen,
  postgrey-Ausnahmelisten, SpamAssassin-Regeln, fail2ban-Jails, Cron-Jobs,
  Firewall-Regeln). Das alte `/etc` mit dem Stand der letzten Kopie liegt in
  `/root/migration/old-etc.tar.gz` (entpackt in `/root/migration/old-etc`),
  und `/root/migration/etc-report.txt` listet abweichende
  Postfix-Einstellungen, darin genannte Dateien und Dateien, die es nur auf
  der alten Box gibt. Ein Eintrag in `smtpd_*_restrictions` der alten Box,
  der hier fehlt, gilt als fehlgeschlagene Prüfung (in `main.cf` wieder
  eintragen oder das Ergebnis mit `--finish` annehmen). Nur die Ausnahmen vom
  Greylisting (`/etc/postfix/greylist_bypass_senders`, siehe oben) werden vor
  setup übernommen. Eine Sicherung (`--from-backup`) enthält sie nicht: die
  Datei selbst hinüberkopieren und setup erneut aufrufen.
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
* Lokale Änderungen an Roundcube (Webmail; es gehört nicht zu den Daten,
  setup installiert sein eigenes und schreibt seine eigene
  `config/config.inc.php`). Die Prüfung (auch `--check`) nennt
  Plugin-Verzeichnisse der alten Box, die setup nicht installiert, und
  Änderungen an ihrer `config.inc.php` (die Plugin-Liste und andere
  Einstellungen; bei einer Einstellung, die setup nicht schreibt, nur den
  Namen). Das Werkzeug bewahrt die alte `config.inc.php` und diese
  Plugin-Verzeichnisse in `/root/migration/old-roundcube` auf, installiert sie
  aber nicht (ein Plugin für das alte Roundcube kann das neue stören). Die
  Phase verify listet, was dem neuen Roundcube fehlt (auch in
  `etc-report.txt`), und schreibt es in `/root/migration/local-changes.json`
  (nur für root lesbar); solange es diese Datei gibt, zeigt der Systemstatus
  eine Warnung mit den Punkten unter „show more“, ebenso die tägliche
  Statusmail. Was das neue Roundcube unterstützt, zurückholen (das
  Plugin-Verzeichnis nach `/usr/local/lib/roundcubemail/plugins/` kopieren
  und in `$config['plugins']` eintragen; setup schreibt die Datei bei jedem
  Lauf neu; der Webserver, www-data, muss das Plugin lesen können, was die
  Phase verify prüft), danach die Warnung mit `migrate-to-2604.sh --ack-local` beenden
  (oder die Datei löschen). Nicht bei `--from-backup`: Eine Sicherung enthält
  kein Roundcube.

#### Nach dem Umzug

##### 1. Vor der DNS-Umstellung testen

Die Zeile `<neue IP> <Hostname>` in die hosts-Datei des eigenen Rechners
eintragen (`/etc/hosts`; Windows: `C:\Windows\System32\drivers\etc\hosts`).
Dann `https://<Hostname>/admin` und `https://<Hostname>/mail` öffnen,
anmelden, eine Testmail über die neue Box senden (SMTP-Einlieferung) und eine
empfangen, Nextcloud prüfen (Dateien, Kontakte, Kalender). Die Zeile danach
wieder entfernen.

Webmail-Benutzer müssen sich neu anmelden: Roundcube hat auf der neuen
Maschine einen eigenen Schlüssel, nicht den der alten Box. Spamfilter
(Bayes) und Greylisting-Datenbank werden so übernommen, wie sie sind.

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
	sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/LM1337/Mail-in-a-box-26/main/setup/bootstrap.sh)"
	sudo chown -R user-data:user-data /home/user-data/www && sudo chown user-data:user-data /home/user-data /home/user-data/mailinabox.version
