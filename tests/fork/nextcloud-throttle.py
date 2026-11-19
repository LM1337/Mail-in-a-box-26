#!/usr/bin/env python3
"""Checks management/nextcloud_throttle.py without a box.

* The database reader (run here as the current user on a temporary SQLite
  database shaped like Nextcloud's): its input holds no account of the box
  (only a random salt), its output no login name (only salted hashes), and
  root's side finds the accounts among them.
* The overview with the protection off: delay and block are shown as
  Nextcloud applies them, and the entries are flagged stale.
* The takeover of values set by hand in config.php, per value: a stored
  nc_max_attempts does not stop the takeover of a hand-set
  protection.enabled = false, and the other way round; Nextcloud's own reading
  (a PHP bool cast) decides what is off.

Usage: python3 -I tests/fork/nextcloud-throttle.py
Exit code 0 when every check passed.
"""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "management"))
import nextcloud_throttle as nt  # noqa: E402
import fail2ban_admin  # noqa: E402

bad = 0

def check(ok, desc, info=""):
    global bad
    print("%s  %-60s %s" % ("ok  " if ok else "FAIL", desc, "" if ok else info))
    bad += not ok

ACCOUNTS = {"bob@example.com", "carol@example.com"}
SECRET = "Typed-Password-77"

with tempfile.TemporaryDirectory() as d:
    db = os.path.join(d, "owncloud.db")
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE oc_bruteforce_attempts (id INTEGER PRIMARY KEY, action TEXT, occurred INTEGER, ip TEXT, subnet TEXT, metadata TEXT)")
    con.execute("CREATE TABLE oc_appconfig (appid TEXT, configkey TEXT, configvalue TEXT)")
    now = int(time.time())
    rows = []
    for i in range(12):
        rows.append(("login", now - 60 * i, "192.0.2.10", "192.0.2.10/32", json.dumps({"user": "Bob@Example.com"})))
    rows.append(("login", now - 30, "192.0.2.10", "192.0.2.10/32", json.dumps({"user": SECRET})))
    rows.append(("login", now - 30, "2001:db8:1:2::5", "2001:db8:1::/56", json.dumps({"user": "carol@example.com"})))
    con.executemany("INSERT INTO oc_bruteforce_attempts (action, occurred, ip, subnet, metadata) VALUES (?, ?, ?, ?, ?)", rows)
    con.execute("INSERT INTO oc_appconfig VALUES ('bruteForce', 'whitelist_1', '127.0.0.1/32')")
    con.commit()
    con.close()

    seen = {}
    def fake_run_www(argv, stdin=None, extra_env=None, timeout=120):
        seen["stdin"] = stdin
        p = subprocess.run([sys.executable, "-I", *argv[1:]], input=stdin, capture_output=True, text=True, timeout=timeout)
        seen["stdout"] = p.stdout
        return p
    nt._run_www = fake_run_www
    cfg = {"dbtype": "sqlite3", "dbtableprefix": "oc_", "datadirectory": d, "enabled_effective": True, "max_attempts_effective": 10}
    r = nt._read_db({"STORAGE_ROOT": d}, cfg, now - 12 * 3600, now - 1800, ACCOUNTS)
    check(not any(a in (seen.get("stdin") or "") for a in ACCOUNTS) and "salt" in json.loads(seen["stdin"]),
          "the reader gets no account, only a salt", seen.get("stdin", "")[:120])
    out = seen.get("stdout") or ""
    check(SECRET not in out and "bob@example.com" not in out.lower() and "carol" not in out,
          "the reader returns no login name", out[:120])
    check(sorted(r["known"]) == [("192.0.2.10/32", "bob@example.com"), ("2001:db8:1::/56", "carol@example.com")],
          "root finds the accounts among the hashes", r["known"])

    # The overview with the protection off: delay and block as Nextcloud
    # applies them, entries flagged stale.
    nt.nc_config = lambda env, set_values=None: dict(cfg, enabled=False, enabled_effective=False, max_attempts=None)
    nt._state = lambda env: {}
    fail2ban_admin._known_accounts = lambda env: set(ACCOUNTS)
    settings, _ = fail2ban_admin.validate_settings({"nc_protection": False})
    o = nt.get_overview({"STORAGE_ROOT": d}, settings, now)
    e = {x["address"]: x for x in o["entries"]}
    check(o["available"] and o["enabled"] is False and o["stale"] is True, "protection off: entries flagged stale", o.get("error"))
    b = e.get("192.0.2.10", {})
    check(b.get("blocked") is True and b.get("delay_ms") == nt.MAX_DELAY_MS and b.get("accounts") == ["bob@example.com"] and b.get("unknown_names") == 1,
          "protection off: delay and block still shown, names masked", b)
    check(e.get("2001:db8:1::/56", {}).get("network") is True, "an IPv6 network is shown as a network", list(e))

# The takeover per value.
def takeover(stored, cfg):
    nt.utils.load_settings = lambda env: {"fail2ban": stored}
    return nt.hand_set_values({}, dict({"enabled": None, "enabled_effective": True, "max_attempts": None, "max_attempts_effective": 10}, **cfg))[0]

check(takeover({"nc_max_attempts": 12}, {"enabled": False, "enabled_effective": False}) == {"nc_protection": False},
      "stored nc_max_attempts: a hand-set enabled=false is taken over")
check(takeover({"nc_protection": False}, {"max_attempts": 20, "max_attempts_effective": 20}) == {"nc_max_attempts": 20},
      "stored nc_protection: a hand-set max-attempts is taken over")
check(takeover({"nc_protection": False, "nc_max_attempts": 12}, {"enabled": True, "max_attempts": 20, "max_attempts_effective": 20}) == {},
      "both stored: nothing is taken over")
check(takeover({}, {"enabled": "false", "enabled_effective": True}) == {},
      "the string 'false' is on for Nextcloud: not taken over as off")
check(takeover({}, {"enabled": 0, "enabled_effective": False, "max_attempts": 5000, "max_attempts_effective": 5000}) == {"nc_protection": False, "nc_max_attempts": 1000},
      "0 is off; an out-of-range max-attempts is taken over as the limit")

print("%d checks failed" % bad)
sys.exit(1 if bad else 0)
