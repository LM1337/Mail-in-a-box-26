#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Client load for update tests of the Mail-in-a-Box fork -- python3 stdlib only.

Keeps the clients of a real box busy while setup (or an update tool) runs,
and counts what failed: ActiveSync (Sync of the calendar and the contacts,
then Ping, the long poll), CalDAV/CardDAV (PROPFIND of the user's calendars
and address books in Nextcloud), IMAP (a login every second, as Nextcloud's
user_external does, and an IDLE connection), SMTP AUTH on port 587, and
Roundcube (a logged-in session that refreshes the inbox).

Each request ends as one of
  ok           it worked
  auth         the login was refused (HTTP 401, IMAP/SMTP authentication
               failed): a client shows a password prompt or stops syncing
  throttled    Nextcloud's brute-force protection answered (HTTP 429,
               TooManyRequests)
  unavailable  no connection, HTTP 502/503/504, a temporary failure
               (IMAP [UNAVAILABLE], SMTP 4xx): a service was restarting
  disconnect   the connection broke during a request (a Ping or IDLE cut
               by a restart); the client reconnects
  error        anything else (an unexpected status or answer)
and the summary lists, per client type, the counts, the longest run of
"unavailable" in seconds and the first failures with their time.

Exit code: 0 if there was no auth, throttled or error result and no outage
longer than --max-outage seconds; 1 otherwise; 2 on a usage error. Short
outages and disconnects are expected while setup restarts a service; failed
logins are not (TESTING-fork.md, "Client load during updates").

Typical run on the box under test, as a normal user (the clients then come
from 127.0.0.1, like Z-Push's own CalDAV/CardDAV calls; fail2ban ignores
that address), from the start of setup until a few minutes after it:

    TEST_USER_PW=... tests/fork/client-load.py --host 127.0.0.1 \\
        --hostname box.example.net --user alice@example.net \\
        --user bob@example.org --duration 900 --report load.json

or from a workstation through the box's ports (--jump SSHHOST as in
smoke.py). Do not run it from an address whose failed logins must not count
against the box's fail2ban (a jump host that other tests need): a failed
login during the update is what this tool looks for.

The users must exist with the password of --user-pw-var (default
TEST_USER_PW, from the environment or --env-file); smoke.py --provision
creates alice, bob and carol. The password is never printed. Stop with
Ctrl-C or SIGTERM (or --duration); the summary is printed then.
"""

import argparse
import base64
import json
import os
import re
import signal
import socket
import ssl
import sys
import threading
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eas  # noqa: E402  (tests/fork/eas.py)
import smoke  # noqa: E402  (tests/fork/smoke.py: Net, http_req, load_env_file)

KINDS = ("ok", "auth", "throttled", "unavailable", "disconnect", "error")
FAILURES = ("auth", "throttled", "error")

STOP = threading.Event()


class Stats:
    def __init__(self):
        self.lock = threading.Lock()
        self.by_client = {}
        self.events = []
        self.verbose = True

    def record(self, client, user, kind, detail=""):
        now = time.time()
        with self.lock:
            s = self.by_client.setdefault(client, {
                "counts": {k: 0 for k in KINDS}, "outage_start": None, "longest_outage": 0.0,
                "outages": 0, "first": {}})
            s["counts"][kind] += 1
            if kind == "unavailable":
                if s["outage_start"] is None:
                    s["outage_start"] = now
                    s["outages"] += 1
                s["longest_outage"] = max(s["longest_outage"], now - s["outage_start"])
            elif kind == "ok":
                s["outage_start"] = None
            if kind != "ok":
                s["first"].setdefault(kind, [])
                if len(s["first"][kind]) < 5:
                    s["first"][kind].append("%s %s %s" % (ts(now), user, smoke.redact(detail)[:160]))
                self.events.append({"time": ts(now), "client": client, "user": user, "kind": kind,
                                    "detail": smoke.redact(detail)[:300]})
                if self.verbose:
                    print("%s %-11s %-11s %s %s" % (ts(now), client, kind, user, smoke.redact(detail)[:160]),
                          flush=True)


def ts(t):
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + ".%03dZ" % int((t % 1) * 1000)


def sleep(seconds):
    STOP.wait(seconds)


# ---------------------------------------------------------------------------
# raw IMAP (login and IDLE) with classified answers
# ---------------------------------------------------------------------------

class IMAPResult(Exception):
    def __init__(self, kind, msg):
        super().__init__(msg)
        self.kind = kind


class RawIMAP:
    def __init__(self, addr, hostname, timeout=30):
        sock = socket.create_connection(addr, timeout=timeout)
        self.sock = smoke.ssl_ctx().wrap_socket(sock, server_hostname=hostname)
        self.buf = b""
        self.n = 0
        greeting = self.line()
        if not greeting.startswith(b"* OK"):
            raise IMAPResult("unavailable", "greeting %r" % greeting[:80])

    def line(self):
        while b"\r\n" not in self.buf:
            d = self.sock.recv(65536)
            if not d:
                raise ConnectionResetError("connection closed by the server")
            self.buf += d
        line, _, self.buf = self.buf.partition(b"\r\n")
        return line

    def cmd(self, text):
        self.n += 1
        tag = b"c%d" % self.n
        self.sock.sendall(tag + b" " + text + b"\r\n")
        while True:
            line = self.line()
            if line.startswith(tag + b" "):
                return line[len(tag) + 1:]

    def login(self, user, pw):
        ir = base64.b64encode(b"\0" + user.encode() + b"\0" + pw.encode())
        r = self.cmd(b"AUTHENTICATE PLAIN " + ir)
        if r.startswith(b"OK"):
            return
        if b"[UNAVAILABLE]" in r or b"Temporary" in r:
            raise IMAPResult("unavailable", "login: %s" % r[:120].decode(errors="replace"))
        if r.startswith(b"NO"):
            raise IMAPResult("auth", "login: %s" % r[:120].decode(errors="replace"))
        raise IMAPResult("error", "login: %s" % r[:120].decode(errors="replace"))

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def classify(e):
    if isinstance(e, IMAPResult):
        return e.kind
    kind = eas.classify_exception(e)
    return "error" if kind == "status" else kind


# ---------------------------------------------------------------------------
# the clients
# ---------------------------------------------------------------------------

def run_loop(name, user, stats, fn, interval):
    """Call fn() every interval seconds until STOP; fn returns a detail text
    or raises; each call is one result."""
    while not STOP.is_set():
        t0 = time.time()
        try:
            detail = fn()
            stats.record(name, user, "ok", detail or "")
        except Exception as e:  # classified below
            stats.record(name, user, classify(e), "%s: %s" % (type(e).__name__, e))
        sleep(max(0.0, interval - (time.time() - t0)))


def imap_login_client(args, net, user, pw, stats):
    def once():
        m = RawIMAP(net.addr(993), args.hostname, timeout=20)
        try:
            m.login(user, pw)
            r = m.cmd(b"SELECT INBOX")
            if not r.startswith(b"OK"):
                raise IMAPResult("error", "SELECT: %s" % r[:80].decode(errors="replace"))
            m.cmd(b"LOGOUT")
        finally:
            m.close()
    run_loop("imap-login", user, stats, once, args.imap_interval)


def imap_idle_client(args, net, user, pw, stats):
    while not STOP.is_set():
        m = None
        try:
            m = RawIMAP(net.addr(993), args.hostname, timeout=20)
            m.login(user, pw)
            r = m.cmd(b"SELECT INBOX")
            if not r.startswith(b"OK"):
                raise IMAPResult("error", "SELECT: %s" % r[:80].decode(errors="replace"))
            stats.record("imap-idle", user, "ok", "connected")
            while not STOP.is_set():
                m.n += 1
                tag = b"c%d" % m.n
                m.sock.sendall(tag + b" IDLE\r\n")
                if not m.line().startswith(b"+"):
                    raise IMAPResult("error", "IDLE refused")
                m.sock.settimeout(1.0)
                started = time.time()
                while not STOP.is_set() and time.time() - started < args.idle_renew:
                    try:
                        line = m.line()
                    except (socket.timeout, TimeoutError):
                        continue
                    if line.startswith(b"* BYE"):
                        raise ConnectionResetError("BYE: %s" % line[:80].decode(errors="replace"))
                m.sock.settimeout(20)
                m.sock.sendall(b"DONE\r\n")
                while True:
                    line = m.line()
                    if line.startswith(tag + b" "):
                        break
            m.cmd(b"LOGOUT")
        except Exception as e:
            stats.record("imap-idle", user, classify(e), "%s: %s" % (type(e).__name__, e))
            sleep(1.0)
        finally:
            if m:
                m.close()


def smtp_client(args, net, user, pw, stats):
    import smtplib

    def once():
        h, p = net.addr(587)
        try:
            s = smtplib.SMTP(h, p, local_hostname="loadtest.invalid", timeout=30)
        except smtplib.SMTPConnectError as e:
            raise IMAPResult("unavailable", "connect: %s" % e)
        try:
            s.starttls(context=smoke.ssl_ctx())
            s.ehlo()
            try:
                s.login(user, pw)
            except smtplib.SMTPAuthenticationError as e:
                raise IMAPResult("unavailable" if 400 <= e.smtp_code < 500 else "auth",
                                 "AUTH %d %s" % (e.smtp_code, e.smtp_error[:100].decode(errors="replace")))
        except smtplib.SMTPServerDisconnected as e:
            raise ConnectionResetError(str(e))
        except smtplib.SMTPResponseException as e:
            raise IMAPResult("unavailable" if 400 <= e.smtp_code < 500 else "error", "%d %s" % (e.smtp_code, e.smtp_error[:100]))
        finally:
            try:
                s.quit()
            except Exception:
                pass
    run_loop("smtp-auth", user, stats, once, args.smtp_interval)


def dav_client(args, ctx, user, pw, stats):
    body = '<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/><d:displayname/></d:prop></d:propfind>'
    uid = {}

    def userid():
        if "id" not in uid:
            r = smoke.http_req(ctx, "GET", "/cloud/ocs/v1.php/cloud/user?format=json",
                               headers={"OCS-APIRequest": "true"}, auth=(user, pw), timeout=60)
            check_http(r, "OCS user")
            try:
                ocs = r.json()["ocs"]
                code = ocs["meta"]["statuscode"]
            except (ValueError, KeyError, TypeError):
                raise IMAPResult("error", "OCS user: unexpected answer")
            if code == 429:
                raise IMAPResult("throttled", "OCS user: TooManyRequests")
            if code == 997:
                raise IMAPResult("auth", "OCS user: not logged in")
            if code not in (100, 200) or not isinstance(ocs.get("data"), dict):
                raise IMAPResult("error", "OCS user: status %s" % code)
            uid["id"] = ocs["data"]["id"]
        return uid["id"]

    def once(kind):
        path = {"caldav": "/cloud/remote.php/dav/calendars/%s/",
                "carddav": "/cloud/remote.php/dav/addressbooks/users/%s/"}[kind] % urllib.parse.quote(userid())
        r = smoke.http_req(ctx, "PROPFIND", path, auth=(user, pw), body=body,
                           headers={"Depth": "1", "Content-Type": "application/xml"}, timeout=60)
        check_http(r, kind, want=207)

    def both():
        once("caldav")
        once("carddav")
    run_loop("dav", user, stats, both, args.dav_interval)


def check_http(r, what, want=200):
    if r.status == want:
        return
    t = r.text()[:2000]
    if r.status == 429 or "TooManyRequests" in t:
        raise IMAPResult("throttled", "%s: HTTP %d TooManyRequests" % (what, r.status))
    if r.status == 401:
        raise IMAPResult("auth", "%s: HTTP 401" % what)
    if r.status in (502, 503, 504):
        raise IMAPResult("unavailable", "%s: HTTP %d%s" % (what, r.status,
                                                           " (maintenance mode)" if "aintenance" in t else ""))
    raise IMAPResult("error", "%s: HTTP %d" % (what, r.status))


def activesync_client(args, net, n, user, pw, stats):
    c = eas.Client(args.hostname, user, pw, "miabload%s%02d" % (args.token, n), addr=net.addr(443), timeout=90,
                   user_agent="miab-fork-client-load/1")
    ready = False
    while not STOP.is_set():
        try:
            if not ready:
                c.provision()
                c.folder_sync()
                cals = c.folders_of(eas.TYPE_CALENDAR, eas.TYPE_USER_CALENDAR)
                cons = c.folders_of(eas.TYPE_CONTACTS, eas.TYPE_USER_CONTACTS)
                if not cals or not cons:
                    raise eas.EASError("error", "FolderSync: %d calendar, %d contact folders" % (len(cals), len(cons)))
                folders = [(f["ServerId"], "Calendar") for f in cals] + [(f["ServerId"], "Contacts") for f in cons]
                ready = True
            c.sync([f for f, _ in folders])
            stats.record("activesync", user, "ok", "sync")
            if STOP.is_set():
                break
            st = c.ping(folders, args.ping_heartbeat)
            stats.record("activesync", user, "ok", "ping %s" % st)
        except eas.EASError as e:
            if e.kind == "status" and "Ping status 7" in str(e):
                # "folder hierarchy out of date": a phone runs FolderSync again
                stats.record("activesync", user, "disconnect", "Ping status 7, FolderSync again")
                ready = False
                continue
            stats.record("activesync", user, classify(e), "%s: %s" % (type(e).__name__, e))
            if e.kind == "status":
                ready = False  # start over with Provision and FolderSync
            sleep(1.0)
        except Exception as e:
            stats.record("activesync", user, classify(e), "%s: %s" % (type(e).__name__, e))
            sleep(1.0)


def roundcube_client(args, ctx, user, pw, stats):
    sess = {}

    def login():
        jar, cookie = smoke.roundcube_login(ctx, user)
        r = smoke.http_req(ctx, "GET", "/mail/?_task=mail&_mbox=INBOX", headers={"Cookie": cookie()}, timeout=60)
        check_http(r, "roundcube mailbox")
        m = re.search(r'"request_token":"([^"]+)"', r.text())
        if not m:
            raise IMAPResult("error", "no request token after the login")
        sess.update(jar=jar, cookie=cookie, token=m.group(1))

    def eat(resp):
        # Roundcube renews its session cookie (roundcube_sessauth) every few
        # minutes; a browser takes the new one from each answer.
        for v in resp.header("Set-Cookie"):
            k, _, rest = v.partition("=")
            sess["jar"][k.strip()] = rest.split(";", 1)[0]

    def once():
        if not sess:
            try:
                login()
            except smoke.Fail as e:
                raise IMAPResult("auth" if "_task=login" in str(e) else "error", "login: %s" % e)
            return "login"
        # what the inbox view does every minute (refresh_interval)
        r = smoke.http_req(ctx, "POST", "/mail/?_task=mail&_action=refresh",
                           form={"_mbox": "INBOX", "_remote": "1", "_unlock": "0"},
                           headers={"Cookie": sess["cookie"](), "X-Roundcube-Request": sess["token"],
                                    "X-Requested-With": "XMLHttpRequest"}, timeout=60)
        eat(r)
        if r.status in (401, 403) or "session_error" in r.text() or "_task=login" in r.text():
            sess.clear()
            raise IMAPResult("error", "refresh: session lost (HTTP %d)" % r.status)
        check_http(r, "roundcube refresh")
        if "Connection to storage server failed" in r.text() or "storage_error" in r.text():
            raise IMAPResult("unavailable", "refresh: Roundcube could not reach IMAP")
        return None
    run_loop("roundcube", user, stats, once, args.rc_interval)


CLIENTS = ["activesync", "dav", "imap-login", "imap-idle", "smtp-auth", "roundcube"]


def main():
    ap = argparse.ArgumentParser(description="MIAB fork client load", formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__)
    ap.add_argument("--host", required=True, help="address of the box as reachable from here (127.0.0.1 on the box)")
    ap.add_argument("--hostname", required=True, help="PRIMARY_HOSTNAME (TLS SNI, HTTP Host)")
    ap.add_argument("--jump", help="ssh host to forward the ports through (as in smoke.py)")
    ap.add_argument("--user", action="append", required=True, help="a mail user (repeat for more)")
    ap.add_argument("--env-file", default=smoke.DEFAULT_ENV_FILE)
    ap.add_argument("--user-pw-var", default="TEST_USER_PW", help="variable with the users' password")
    ap.add_argument("--clients", default=",".join(CLIENTS), help="comma list of: " + ",".join(CLIENTS))
    ap.add_argument("--duration", type=float, default=0, help="seconds to run (0: until Ctrl-C or SIGTERM)")
    ap.add_argument("--max-outage", type=float, default=30,
                    help="longest acceptable run of 'unavailable' results of one client type, in seconds")
    ap.add_argument("--imap-interval", type=float, default=1.0)
    ap.add_argument("--smtp-interval", type=float, default=5.0)
    ap.add_argument("--dav-interval", type=float, default=2.0)
    ap.add_argument("--rc-interval", type=float, default=5.0)
    ap.add_argument("--ping-heartbeat", type=int, default=60, help="ActiveSync Ping heartbeat in seconds")
    ap.add_argument("--idle-renew", type=float, default=600, help="seconds before IDLE is renewed")
    ap.add_argument("--quiet", action="store_true", help="print only the summary, not each failure")
    ap.add_argument("--report", help="write the JSON report (summary and every non-ok result) to this file")
    args = ap.parse_args()

    clients = [c for c in args.clients.split(",") if c]
    bad = [c for c in clients if c not in CLIENTS]
    if bad:
        ap.error("unknown client: " + ",".join(bad))
    env = smoke.load_env_file(args.env_file)
    pw = os.environ.get(args.user_pw_var) or env.get(args.user_pw_var, "")
    if not pw:
        print("%s missing (environment or --env-file %s)" % (args.user_pw_var, args.env_file), file=sys.stderr)
        return 2
    smoke.SECRETS.add(pw)
    args.token = "%04d" % (os.getpid() % 10000)

    try:
        net = smoke.Net(args.host, args.hostname, args.jump)
    except Exception as e:
        print("cannot set up network path: %s" % smoke.redact(e), file=sys.stderr)
        return 2
    ctx = smoke.Ctx()
    ctx.net = net
    ctx.hostname = args.hostname
    ctx.user_pw = pw

    stats = Stats()
    stats.verbose = not args.quiet
    signal.signal(signal.SIGTERM, lambda *_: STOP.set())
    started = time.time()
    threads = []
    for n, user in enumerate(args.user):
        targets = {
            "activesync": (activesync_client, (args, net, n, user, pw, stats)),
            "dav": (dav_client, (args, ctx, user, pw, stats)),
            "imap-login": (imap_login_client, (args, net, user, pw, stats)),
            "imap-idle": (imap_idle_client, (args, net, user, pw, stats)),
            "smtp-auth": (smtp_client, (args, net, user, pw, stats)),
            "roundcube": (roundcube_client, (args, ctx, user, pw, stats)),
        }
        for c in clients:
            fn, a = targets[c]
            t = threading.Thread(target=fn, args=a, name="%s-%s" % (c, user), daemon=True)
            t.start()
            threads.append(t)
    print("%s client load started: %s for %s" % (ts(started), ",".join(clients), ", ".join(args.user)), flush=True)
    try:
        while not STOP.is_set():
            if args.duration and time.time() - started >= args.duration:
                break
            STOP.wait(0.5)
    except KeyboardInterrupt:
        pass
    STOP.set()
    for t in threads:
        t.join(5)
    net.close()
    ended = time.time()

    failed = False
    summary = {}
    print()
    print("client load %s .. %s (%.0f s)" % (ts(started), ts(ended), ended - started))
    print("%-11s %7s %5s %9s %11s %10s %5s  %s" % ("CLIENT", "ok", "auth", "throttled", "unavailable",
                                                 "disconnect", "error", "longest outage"))
    for c in clients:
        s = stats.by_client.get(c, {"counts": {k: 0 for k in KINDS}, "longest_outage": 0.0, "outages": 0,
                                    "first": {}})
        k = s["counts"]
        bad = sum(k[x] for x in FAILURES) or s["longest_outage"] > args.max_outage
        failed = failed or bool(bad)
        summary[c] = {"counts": k, "longest_outage_seconds": round(s["longest_outage"], 1),
                      "outages": s["outages"], "first": s["first"], "result": "FAIL" if bad else "OK"}
        print("%-11s %7d %5d %9d %11d %10d %5d  %.1f s in %d outage(s)  %s" % (
            c, k["ok"], k["auth"], k["throttled"], k["unavailable"], k["disconnect"], k["error"],
            s["longest_outage"], s["outages"], "FAIL" if bad else "OK"))
        for kind in ("auth", "throttled", "error"):
            for line in s["first"].get(kind, []):
                print("    %-9s %s" % (kind, line))
    print("RESULT: %s" % ("FAIL (failed logins, throttling, errors or a long outage)" if failed else
                          "OK (at most short outages and disconnects)"))
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump({"started": ts(started), "ended": ts(ended), "host": args.host, "hostname": args.hostname,
                       "users": args.user, "clients": clients, "max_outage": args.max_outage,
                       "result": "FAIL" if failed else "OK", "summary": summary, "events": stats.events},
                      f, indent=2)
            f.write("\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
