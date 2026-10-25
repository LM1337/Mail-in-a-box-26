# rc7 fragment: setup

Entries of the setup strand for CHANGELOG-fork.md ("Unreleased") and
BUGS-fork.md, to be merged into them when the strands come together.

## CHANGELOG-fork.md

### Fixed

* Setup: an update no longer runs as root what another local user put into
  `/tmp`. setup/start.sh wrote the settings of `/etc/mailinabox.conf` to
  `/tmp/mailinabox.prev.conf` and sourced that file; when a file of that
  name already existed (any local user can create one), the write failed and
  setup sourced the other user's file. It now reads the settings through a
  pipe (B96).
* OpenDKIM: setup writes the `KeyTable` and `SigningTable` in a fixed
  (sorted) order. The domains came from a Python set, whose order changes
  with every process, so with more than one mail domain each setup run
  rewrote both tables and restarted OpenDKIM, although nothing had changed
  (the management daemon, which writes them, starts anew in every run). Mail
  sent in the moment of the restart went out without a DKIM signature
  (Postfix has `milter_default_action=accept`) (B95).

## BUGS-fork.md

### B95

**Every setup run rewrites the OpenDKIM tables and restarts OpenDKIM** (low, Mail)

* **Symptom:** On a box with more than one mail domain, each run of setup (and the first DNS update after each start of the management daemon, e.g. after a reboot) rewrites `/etc/opendkim/KeyTable` and `/etc/opendkim/SigningTable` with the same lines in another order and restarts OpenDKIM, although no domain changed. A comparison of `/etc` before and after an update shows both files as changed, and a mail sent in the moment of the restart goes out without a DKIM signature (Postfix passes mail on when a milter does not answer, `milter_default_action=accept`), so it can fail DMARC at the receiver.
* **Cause:** `write_opendkim_tables()` in `management/dns_update.py` writes one line per domain in the order of `get_mail_domains()`, a Python set. The order of a set of strings depends on the hash seed, which Python chooses at random for every process (here: every start of the management daemon), so the content differs from run to run and the "did the file change" check sees a change.
* **Fix:** The domains are sorted before the tables are written. The patterns `*@domain` never overlap (a domain contains no "@"), so the order does not change which key signs a mail. The first run with the fix writes the tables once more in sorted order; from then on they only change when the domains do.
* **Affects:** v78 yes, PR #2603 yes. Origin: Upstream.
* **Evidence:** rc6 T5b: a second update run changed the order of both tables (noted in B74). The same set of four domains printed in four different orders with `PYTHONHASHSEED` 1 to 4.
* **Found by:** update test; **commit:** see `git log --grep B95`; **fixed in:** v78-r2604.0-rc7

### B96

**Setup sources a file in /tmp that another local user can put there: local root** (critical, Setup)

* **Symptom:** A local user without privileges (a shell account on the box, or a service account that can write to `/tmp`) creates `/tmp/mailinabox.prev.conf` with shell commands. The next time the admin runs setup on the box (`sudo mailinabox`, an update with `setup/bootstrap.sh`, the upgrade and migration tools), setup runs these commands as root. Setup prints "/tmp/mailinabox.prev.conf: Permission denied" and goes on as usual.
* **Cause:** setup/start.sh copied `/etc/mailinabox.conf` with a `DEFAULT_` prefix to `/tmp/mailinabox.prev.conf`, sourced that file and removed it. `/tmp` is writable by everyone. On Ubuntu (`fs.protected_regular = 2`) root may not open another user's file in a sticky directory for writing, so the copy fails, and the `source` that follows reads the other user's file. Without that protection root would overwrite the file, which still belongs to the other user, who could change it before the `source`.
* **Fix:** setup reads the settings through a pipe (`source <(sed s/^/DEFAULT_/ /etc/mailinabox.conf)`); no file is written.
* **Affects:** v78 yes, PR #2603 yes. Origin: Upstream. Only boxes with a local user or service that an attacker controls; the first install (no `/etc/mailinabox.conf` yet) does not read the file.
* **Evidence:** On a fresh 26.04 test box, an unprivileged user wrote `id > /root/b96-proof.txt` into `/tmp/mailinabox.prev.conf`; the three lines of setup/start.sh, run with sudo, printed "Permission denied" and wrote `uid=0(root)` into `/root/b96-proof.txt`, then removed the user's file.
* **Found by:** rc7 review; **commit:** see `git log --grep B96`; **fixed in:** v78-r2604.0-rc7
