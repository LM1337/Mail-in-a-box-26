#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Client load for update tests of the Mail-in-a-Box fork -- python3 stdlib only.

Keeps the clients of a real box busy while setup (or an update tool) runs,
at about the rate of a box with a few phones per user, and records every
request (with its time and latency), so that what clients notice during the
run -- refused connections, failed logins, throttling -- shows up with its
second and protocol, and can be told apart from what already failed before.

Clients per user (intervals jittered):
  eas-ping    --ping-devices ActiveSync devices (default 4): Provision,
              FolderSync, a Sync of the inbox, the calendars and the address
              books, then Ping (the long poll, like a phone's push), and a
              Sync of what changed after each Ping that reports changes.
  eas-sync    --sync-devices ActiveSync devices (default 2) that FolderSync
              (with their key, as a phone does) and Sync the same folders
              every --eas-interval seconds (a tablet with the calendar open).
  dav         CalDAV/CardDAV like a phone with plain basic auth: PROPFIND of
              the calendar home, REPORT of the events of the default
              calendar, PROPFIND of the address book, and a PROPFIND through
              the box's /caldav proxy (the path Z-Push uses).
  imap-login  an IMAP login (and SELECT INBOX) every --imap-interval seconds,
              as Nextcloud's user_external does for each DAV request.
  imap-idle   an IMAP connection in IDLE that reconnects when it is dropped.
  smtp-auth   a submission login (587, STARTTLS, AUTH, QUIT; no mail).
  roundcube   a logged-in Roundcube session that refreshes the inbox.
Each ActiveSync device recovers the way a phone does: HTTP 449 makes it
Provision again, FolderSync status 9, Sync status 3 or 12 and Ping status 7
make it resync the hierarchy or the folder (results "disconnect"), and after
any other failure it starts over with Provision.

--seed first puts one marked event and one marked contact into each user's
default calendar and address book (CalDAV/CardDAV; nothing new if they are
there) and sends each user one marked mail (X-Miab-Test: 1), so that the
Syncs return items. Remove the users after the test (they are test users).

Each request ends as one of
  ok           it worked
  auth         the login was refused (HTTP 401/403, IMAP/SMTP authentication
               failed): a client shows a password prompt or stops syncing
  throttled    the server throttled (HTTP 429, TooManyRequests)
  unavailable  no connection, HTTP 502/503/504, a temporary failure (IMAP
               [UNAVAILABLE], SMTP 4xx, FolderSync status 6): a service was
               restarting
  disconnect   the connection broke during a request (a Ping or IDLE cut by
               a restart), or the server asked the client to resync (above)
  error        anything else (an unexpected status or answer, HTTP 500)

Phases: with --marker-file, every result before that file appears (or
before SIGUSR1) is "baseline", and every one after it "setup"; the update
driver creates the file when it starts setup. Without it, everything counts
as "setup". The verdict: FAIL on any auth or throttled result, on an error
whose kind (client and message without numbers) did not already occur in
the baseline (those are listed as "also before setup"), and on an outage
(a run of unavailable results of one client of one user) longer than
--max-outage seconds; OK otherwise. Exit code 0 OK, 1 FAIL, 2 usage error.

Where to run it (TESTING-fork.md, "Client load during updates"): one
instance on the box under test (--host 127.0.0.1, like Z-Push's own calls),
and one on another host of the test network (never a jump host whose failed
logins would count against other tests): only the second one is counted by
fail2ban and by Nextcloud's brute-force protection under a real address.
Give the two different --device-prefix values.

    TEST_USER_PW=... tests/fork/client-load.py --host 127.0.0.1 \\
        --hostname box.example.net --user alice@example.net \\
        --user bob@example.org --seed --marker-file /tmp/setup-started \\
        --duration 1200 --log load.jsonl --report load.json

The users must exist with the password of --user-pw-var (default
TEST_USER_PW, from the environment or --env-file); smoke.py --provision
creates alice, bob and carol. The password is never printed or logged.
Stop with Ctrl-C, SIGTERM, --stop-file or --duration; the summary is
printed then.
"""

import argparse
import base64
import collections
import json
import os
import random
import re
import signal
import smtplib
import socket
import sys
import threading
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eas  # noqa: E402  (tests/fork/eas.py)
import smoke  # noqa: E402  (tests/fork/smoke.py: Net, http_req, load_env_file)

KINDS = ("ok", "auth", "throttled", "unavailable", "disconnect", "error")
MARK = "miab-client-load"

STOP = threading.Event()
SETUP_SIGNAL = threading.Event()  # SIGUSR1: setup started
PHASE = {"name": "setup", "since": None}


def ts(t):
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + ".%03dZ" % int((t % 1) * 1000)


def sleep(seconds, jitter=0.3):
    STOP.wait(max(0.05, seconds * random.uniform(1 - jitter, 1 + jitter)))


def signature(client, detail):
    """The kind of a failure without numbers, ids and addresses."""
    d = re.sub(r"0x[0-9a-f]+|[0-9a-f]{8,}|\d+(\.\d+)*", "N", detail)
    return "%s: %s" % (client, d[:120])


class Stats:
    def __init__(self, log_path=None, verbose=True):
        self.lock = threading.Lock()
        self.verbose = verbose
        self.log = open(log_path, "a", buffering=1, encoding="utf-8") if log_path else None
        self.counts = collections.defaultdict(lambda: collections.Counter())  # (client, phase) -> kind
        self.outage = {}       # (client, user) -> start of the current run of "unavailable"
        self.longest = {}      # (client, user) -> (seconds, start)
        self.sigs = collections.defaultdict(lambda: collections.Counter())  # phase -> signature
        self.first = collections.defaultdict(list)  # (phase, kind) -> examples
        self.bad_seconds = collections.defaultdict(collections.Counter)
        self.latency = collections.defaultdict(list)  # (client, phase) -> ms of ok results

    def record(self, client, user, kind, detail="", ms=None):
        now = time.time()
        phase = PHASE["name"]
        detail = smoke.redact(detail)[:300]
        with self.lock:
            self.counts[(client, phase)][kind] += 1
            key = (client, user)
            if kind == "unavailable":
                start = self.outage.setdefault(key, now)
                if now - start > self.longest.get(key, (0, 0))[0]:
                    self.longest[key] = (now - start, start)
            elif kind == "ok":
                self.outage.pop(key, None)
                if ms is not None:
                    self.latency[(client, phase)].append(ms)
            if kind != "ok":
                self.sigs[phase][(kind, signature(client, detail))] += 1
                ex = self.first[(phase, kind)]
                if len(ex) < 8:
                    ex.append("%s %s %s %s" % (ts(now), client, user, detail[:160]))
                self.bad_seconds[int(now)]["%s:%s" % (client, kind)] += 1
                if self.verbose:
                    print("%s %-8s %-10s %-11s %s %s" % (ts(now), phase, client, kind, user, detail[:160]), flush=True)
            if self.log:
                rec = {"t": ts(now), "epoch": round(now, 3), "phase": phase, "client": client, "user": user,
                       "kind": kind}
                if ms is not None:
                    rec["ms"] = int(ms)
                if detail:
                    rec["detail"] = detail
                self.log.write(json.dumps(rec) + "\n")

    def mark(self, text):
        with self.lock:
            if self.log:
                self.log.write(json.dumps({"t": ts(time.time()), "epoch": round(time.time(), 3), "phase": PHASE["name"],
                                           "client": "control", "user": "-", "kind": "mark", "detail": text}) + "\n")
        print("%s %s" % (ts(time.time()), text), flush=True)


def timed(stats, client, user, fn, *a):
    """Run fn(*a) as one request: ok with its latency, or its failure."""
    t0 = time.time()
    try:
        detail = fn(*a)
        stats.record(client, user, "ok", detail or "", (time.time() - t0) * 1000)
        return True
    except Exception as e:
        stats.record(client, user, classify(e), "%s: %s" % (type(e).__name__, e), (time.time() - t0) * 1000)
        return False


# ---------------------------------------------------------------------------
# raw IMAP (login and IDLE) with classified answers
# ---------------------------------------------------------------------------

class Result(Exception):
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
            raise Result("unavailable", "greeting %r" % greeting[:80])

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
            raise Result("unavailable", "login: %s" % r[:120].decode(errors="replace"))
        if r.startswith(b"NO"):
            raise Result("auth", "login: %s" % r[:120].decode(errors="replace"))
        raise Result("error", "login: %s" % r[:120].decode(errors="replace"))

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def classify(e):
    if isinstance(e, Result):
        return e.kind
    if isinstance(e, eas.EASError):
        if e.kind == "provision":
            return "disconnect"
        if e.kind == "status":
            if (e.cmd, e.status) in RESYNC:
                return "disconnect"
            return "unavailable" if (e.cmd, e.status) in RETRY_LATER else "error"
        return e.kind
    if isinstance(e, smtplib.SMTPServerDisconnected):
        return "disconnect"
    kind = eas.classify_exception(e)
    return "error" if kind == "status" else kind


# What a phone does after these answers: it resyncs, it does not fail.
RESYNC = {("FolderSync", "9"), ("Sync", "3"), ("Sync", "12"), ("Ping", "7")}
# A server error that the client retries later: Z-Push answers a FolderSync
# with status 6 when the IMAP server gives no folder list, also after it
# connected again (B137; a service was restarting, like HTTP 503).
RETRY_LATER = {("FolderSync", "6")}


# ---------------------------------------------------------------------------
# ActiveSync
# ---------------------------------------------------------------------------

class Device:
    def __init__(self, args, net, user, pw, devid):
        self.c = eas.Client(args.hostname, user, pw, devid, addr=net.addr(443), timeout=90,
                            user_agent="miab-fork-client-load/2")
        self.user = user
        self.folders = []  # [(ServerId, Class)]
        self.ready = False

    def setup(self):
        self.c.provision()
        self.c.folder_sync()
        self.pick()

    def pick(self):
        want = [eas.TYPE_INBOX, eas.TYPE_CALENDAR, eas.TYPE_USER_CALENDAR, eas.TYPE_CONTACTS, eas.TYPE_USER_CONTACTS]
        self.folders = [(f["ServerId"], eas.CLASS_OF_TYPE[f["Type"]]) for f in self.c.folders if f.get("Type") in want]
        classes = {cls for _, cls in self.folders}
        if classes != {"Email", "Calendar", "Contacts"}:
            raise eas.EASError("error", "FolderSync: folders of %s only" % (",".join(sorted(classes)) or "none"))

    def sync_one(self, fid, cls):
        n = len(self.c.sync([fid])[fid])
        return "Sync %s%s" % (cls, " (%d new)" % n if n else "")


def eas_step(stats, client, dev, fn, *a, label=""):
    """One request of a device. Returns True if it worked; on a failure it
    decides what the device does next, as a phone would."""
    t0 = time.time()
    try:
        detail = fn(*a)
        stats.record(client, dev.user, "ok", detail or label, (time.time() - t0) * 1000)
        return True
    except eas.EASError as e:
        kind = classify(e)
        what = label or (e.cmd or "")
        stats.record(client, dev.user, kind, "%s: %s" % (what, e) if what and what not in str(e) else str(e),
                     (time.time() - t0) * 1000)
        if e.kind == "provision":
            dev.ready = False
        elif (e.cmd, e.status) == ("FolderSync", "9") or (e.cmd, e.status) in (("Sync", "12"), ("Ping", "7")):
            dev.c.folder_key = "0"
            dev.ready = False
        elif (e.cmd, e.status) == ("Sync", "3"):
            pass  # eas.py reset this folder's key; the next Sync starts it over
        else:
            dev.ready = False
        sleep(1.0 if kind in ("disconnect", "unavailable") else 3.0)
        return False
    except Exception as e:
        stats.record(client, dev.user, classify(e), "%s: %s: %s" % (label, type(e).__name__, e), (time.time() - t0) * 1000)
        dev.ready = False
        sleep(1.0)
        return False


def eas_ping_client(args, net, user, pw, devid, stats):
    dev = Device(args, net, user, pw, devid)
    changed = True
    while not STOP.is_set():
        if not dev.ready:
            if not eas_step(stats, "eas-ping", dev, dev.setup, label="Provision+FolderSync"):
                continue
            dev.ready = True
            changed = True
        # Sync what Ping reported as changed (all folders: cheap), and every
        # folder that starts over (no sync key: new, or reset by status 3).
        todo = [(fid, cls) for fid, cls in dev.folders if changed or fid not in dev.c.sync_keys]
        ok = True
        for fid, cls in todo:
            if STOP.is_set() or not eas_step(stats, "eas-ping", dev, dev.sync_one, fid, cls, label="Sync %s" % cls):
                ok = False
                break
        if not ok or not dev.ready or STOP.is_set():
            continue
        changed = False
        st = [None]

        def ping():
            st[0] = dev.c.ping(dev.folders, args.ping_heartbeat)
            return "Ping %s" % st[0]
        if eas_step(stats, "eas-ping", dev, ping, label="Ping"):
            changed = st[0] == "2"


def eas_sync_client(args, net, user, pw, devid, stats):
    dev = Device(args, net, user, pw, devid)
    while not STOP.is_set():
        if not dev.ready:
            if eas_step(stats, "eas-sync", dev, dev.setup, label="Provision+FolderSync"):
                dev.ready = True
        else:
            def fsync():
                dev.c.folder_sync(incremental=True)
                dev.pick()
                return "FolderSync"
            if eas_step(stats, "eas-sync", dev, fsync, label="FolderSync"):
                for fid, cls in dev.folders:
                    if STOP.is_set() or not eas_step(stats, "eas-sync", dev, dev.sync_one, fid, cls,
                                                     label="Sync %s" % cls):
                        break
        sleep(args.eas_interval)


# ---------------------------------------------------------------------------
# CalDAV / CardDAV
# ---------------------------------------------------------------------------

PROPFIND_HOME = ('<?xml version="1.0" encoding="utf-8"?><d:propfind xmlns:d="DAV:" '
                 'xmlns:cs="http://calendarserver.org/ns/"><d:prop><d:resourcetype/><d:displayname/>'
                 '<cs:getctag/><d:sync-token/></d:prop></d:propfind>')
REPORT_EVENTS = ('<?xml version="1.0" encoding="utf-8"?><c:calendar-query xmlns:d="DAV:" '
                 'xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop><d:getetag/></d:prop><c:filter>'
                 '<c:comp-filter name="VCALENDAR"><c:comp-filter name="VEVENT"/></c:comp-filter></c:filter>'
                 '</c:calendar-query>')
PROPFIND_ETAGS = ('<?xml version="1.0" encoding="utf-8"?><d:propfind xmlns:d="DAV:" '
                  'xmlns:cs="http://calendarserver.org/ns/"><d:prop><d:getetag/><cs:getctag/></d:prop></d:propfind>')


def check_http(r, what, want=(200, 207)):
    if r.status in want:
        return
    t = r.text()[:2000]
    if r.status == 429 or "TooManyRequests" in t:
        raise Result("throttled", "%s: HTTP %d TooManyRequests" % (what, r.status))
    if r.status in (401, 403):
        raise Result("auth", "%s: HTTP %d" % (what, r.status))
    if r.status in (502, 503, 504):
        raise Result("unavailable", "%s: HTTP %d%s" % (what, r.status, " (maintenance mode)" if "aintenance" in t else ""))
    m = re.search(r"<s:exception>([^<]+)</s:exception>", t)
    raise Result("error", "%s: HTTP %d%s" % (what, r.status, " " + m.group(1) if m else ""))


def dav_req(ctx, user, pw, method, path, body=None, depth="1", ctype="application/xml; charset=utf-8",
            want=(200, 207), extra=None):
    h = {"Depth": depth, "Content-Type": ctype}
    if extra:
        h.update(extra)
    r = smoke.http_req(ctx, method, path, auth=(user, pw), body=body, headers=h, timeout=60)
    what = "%s %s" % (method, re.sub(r"/[^/]*@[^/]*/", "/<user>/", path))
    check_http(r, what, want)
    return "%s: HTTP %d" % (what, r.status)


def dav_client(args, ctx, user, pw, stats):
    q = urllib.parse.quote(user)
    steps = [
        ("PROPFIND", "/cloud/remote.php/dav/calendars/%s/" % q, PROPFIND_HOME),
        ("REPORT", "/cloud/remote.php/dav/calendars/%s/personal/" % q, REPORT_EVENTS),
        ("PROPFIND", "/cloud/remote.php/dav/addressbooks/users/%s/contacts/" % q, PROPFIND_ETAGS),
        ("PROPFIND", "/caldav/calendars/%s/" % q, PROPFIND_HOME),
    ]
    i = 0
    while not STOP.is_set():
        method, path, body = steps[i % len(steps)]
        timed(stats, "dav", user, dav_req, ctx, user, pw, method, path, body)
        i += 1
        sleep(args.dav_interval / len(steps))


def seed(args, ctx, net, users, pw, stats):
    """One marked event, contact and mail per user (see the docstring)."""
    day = time.strftime("%Y%m%d", time.gmtime(time.time() + 86400))
    for user in users:
        q = urllib.parse.quote(user)
        short = re.sub(r"[^a-z0-9]", "", user.split("@")[0].lower())
        ev = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//%s//EN\r\nBEGIN:VEVENT\r\nUID:%s-event-%s\r\n"
              "DTSTAMP:%sT080000Z\r\nDTSTART:%sT090000Z\r\nDTEND:%sT100000Z\r\nSUMMARY:%s test event\r\n"
              "DESCRIPTION:X-Miab-Test 1\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n") % (MARK, MARK, short, day, day, day, MARK)
        vc = ("BEGIN:VCARD\r\nVERSION:3.0\r\nUID:%s-contact-%s\r\nFN:%s test contact\r\nN:contact;%s test;;;\r\n"
              "NOTE:X-Miab-Test 1\r\nEND:VCARD\r\n") % (MARK, short, MARK, MARK)
        # The first DAV request creates the user's Nextcloud account (user_external)
        # with its default calendar and address book.
        timed(stats, "seed", user, dav_req, ctx, user, pw, "PROPFIND", "/cloud/remote.php/dav/calendars/%s/" % q,
              PROPFIND_HOME)
        timed(stats, "seed", user, dav_req, ctx, user, pw, "PUT",
              "/cloud/remote.php/dav/calendars/%s/personal/%s-event.ics" % (q, MARK), ev, "0",
              "text/calendar; charset=utf-8", (201, 204, 412), {"If-None-Match": "*"})
        timed(stats, "seed", user, dav_req, ctx, user, pw, "PUT",
              "/cloud/remote.php/dav/addressbooks/users/%s/contacts/%s-contact.vcf" % (q, MARK), vc, "0",
              "text/vcard; charset=utf-8", (201, 204, 412), {"If-None-Match": "*"})

        def mail():
            h, p = net.addr(587)
            s = smtplib.SMTP(h, p, local_hostname="client-load.invalid", timeout=60)
            try:
                s.starttls(context=smoke.ssl_ctx())
                s.ehlo()
                s.login(user, pw)
                msg = ("From: <%s>\r\nTo: <%s>\r\nSubject: %s test mail\r\nX-Miab-Test: 1\r\n"
                       "Message-ID: <%s-%d@smoketest.invalid>\r\nDate: %s\r\n\r\nA test mail of %s.\r\n"
                       % (user, user, MARK, MARK, int(time.time() * 1000),
                          time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime()), MARK))
                s.sendmail(user, [user], msg)
            finally:
                try:
                    s.quit()
                except Exception:
                    pass
            return "mail sent"
        timed(stats, "seed", user, mail)


# ---------------------------------------------------------------------------
# IMAP, SMTP, Roundcube
# ---------------------------------------------------------------------------

def imap_login_client(args, net, user, pw, stats):
    def once():
        m = RawIMAP(net.addr(993), args.hostname, timeout=20)
        try:
            m.login(user, pw)
            r = m.cmd(b"SELECT INBOX")
            if not r.startswith(b"OK"):
                raise Result("error", "SELECT: %s" % r[:80].decode(errors="replace"))
            m.cmd(b"LOGOUT")
        finally:
            m.close()
    while not STOP.is_set():
        timed(stats, "imap-login", user, once)
        sleep(args.imap_interval)


def imap_idle_client(args, net, user, pw, stats):
    while not STOP.is_set():
        m = None
        t0 = time.time()
        try:
            m = RawIMAP(net.addr(993), args.hostname, timeout=20)
            m.login(user, pw)
            r = m.cmd(b"SELECT INBOX")
            if not r.startswith(b"OK"):
                raise Result("error", "SELECT: %s" % r[:80].decode(errors="replace"))
            stats.record("imap-idle", user, "ok", "connected", (time.time() - t0) * 1000)
            while not STOP.is_set():
                m.n += 1
                tag = b"c%d" % m.n
                m.sock.sendall(tag + b" IDLE\r\n")
                if not m.line().startswith(b"+"):
                    raise Result("error", "IDLE refused")
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
                stats.record("imap-idle", user, "ok", "IDLE renewed", (time.time() - started) * 1000)
            m.cmd(b"LOGOUT")
        except Exception as e:
            stats.record("imap-idle", user, classify(e), "%s: %s" % (type(e).__name__, e))
            sleep(1.0)
        finally:
            if m:
                m.close()


def smtp_client(args, net, user, pw, stats):
    def once():
        h, p = net.addr(587)
        try:
            s = smtplib.SMTP(h, p, local_hostname="client-load.invalid", timeout=30)
        except smtplib.SMTPConnectError as e:
            raise Result("unavailable", "connect: %s" % e)
        try:
            s.starttls(context=smoke.ssl_ctx())
            s.ehlo()
            try:
                s.login(user, pw)
            except smtplib.SMTPAuthenticationError as e:
                raise Result("unavailable" if 400 <= e.smtp_code < 500 else "auth",
                             "AUTH %d %s" % (e.smtp_code, e.smtp_error[:100].decode(errors="replace")))
        except smtplib.SMTPServerDisconnected as e:
            raise ConnectionResetError(str(e))
        except smtplib.SMTPResponseException as e:
            raise Result("unavailable" if 400 <= e.smtp_code < 500 else "error", "%d %s" % (e.smtp_code, e.smtp_error[:100]))
        finally:
            try:
                s.quit()
            except Exception:
                pass
    while not STOP.is_set():
        timed(stats, "smtp-auth", user, once)
        sleep(args.smtp_interval)


def roundcube_client(args, ctx, user, pw, stats):
    sess = {}

    def login():
        jar, cookie = smoke.roundcube_login(ctx, user)
        r = smoke.http_req(ctx, "GET", "/mail/?_task=mail&_mbox=INBOX", headers={"Cookie": cookie()}, timeout=60)
        check_http(r, "roundcube mailbox", (200,))
        m = re.search(r'"request_token":"([^"]+)"', r.text())
        if not m:
            raise Result("error", "no request token after the login")
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
                raise Result("auth" if "_task=login" in str(e) else "error", "login: %s" % e)
            return "login"
        # what the inbox view does every minute (refresh_interval)
        r = smoke.http_req(ctx, "POST", "/mail/?_task=mail&_action=refresh",
                           form={"_mbox": "INBOX", "_remote": "1", "_unlock": "0"},
                           headers={"Cookie": sess["cookie"](), "X-Roundcube-Request": sess["token"],
                                    "X-Requested-With": "XMLHttpRequest"}, timeout=60)
        eat(r)
        if r.status in (401, 403) or "session_error" in r.text() or "_task=login" in r.text():
            sess.clear()
            raise Result("error", "refresh: session lost (HTTP %d)" % r.status)
        check_http(r, "roundcube refresh", (200,))
        if "Connection to storage server failed" in r.text() or "storage_error" in r.text():
            raise Result("unavailable", "refresh: Roundcube could not reach IMAP")
        return "refresh"
    while not STOP.is_set():
        timed(stats, "roundcube", user, once)
        sleep(args.rc_interval)


# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------

def summarize(args, stats, clients, started, ended):
    out = []
    failed = []
    base_sigs = {sig for (kind, sig) in stats.sigs.get("baseline", {})}
    out.append("client load %s .. %s (%.0f s)%s" % (
        ts(started), ts(ended), ended - started,
        ", setup started %s" % ts(PHASE["since"]) if PHASE["since"] else
        (", no setup marker seen" if args.marker_file else "")))
    out.append("%-10s %-8s %7s %5s %9s %11s %10s %5s %8s" % ("CLIENT", "PHASE", "ok", "auth", "throttled",
                                                            "unavailable", "disconnect", "error", "ok ms p50"))
    for c in clients + (["seed"] if any(ck[0] == "seed" for ck in stats.counts) else []):
        for phase in ("baseline", "setup"):
            k = stats.counts.get((c, phase))
            if not k:
                continue
            lat = sorted(stats.latency.get((c, phase), []))
            out.append("%-10s %-8s %7d %5d %9d %11d %10d %5d %8s" % (
                c, phase, k["ok"], k["auth"], k["throttled"], k["unavailable"], k["disconnect"], k["error"],
                int(lat[len(lat) // 2]) if lat else "-"))
    for (c, phase), k in sorted(stats.counts.items()):
        if k["auth"] or k["throttled"]:
            failed.append("%s: %d auth, %d throttled (%s)" % (c, k["auth"], k["throttled"], phase))
    new_errors = collections.Counter()
    old_errors = collections.Counter()
    for (kind, sig), n in stats.sigs.get("setup", {}).items():
        if kind != "error":
            continue
        (old_errors if sig in base_sigs else new_errors)[sig] += n
    for sig, n in sorted(new_errors.items()):
        failed.append("error %dx: %s" % (n, sig))
    for (c, user), (secs, start) in sorted(stats.longest.items()):
        if secs > args.max_outage:
            failed.append("%s %s: unavailable for %.0f s from %s" % (c, user, secs, ts(start)))
    out.append("")
    out.append("longest outage per client and user (unavailable in a row):")
    for (c, user), (secs, start) in sorted(stats.longest.items(), key=lambda x: -x[1][0])[:12]:
        out.append("  %-10s %-36s %5.1f s from %s" % (c, user, secs, ts(start)))
    if old_errors:
        out.append("")
        out.append("errors that also occurred before setup (not counted):")
        for sig, n in sorted(old_errors.items()):
            out.append("  %5d  %s" % (n, sig))
    for phase in ("baseline", "setup"):
        for kind in ("auth", "throttled", "error", "unavailable", "disconnect"):
            ex = stats.first.get((phase, kind))
            if ex:
                out.append("")
                out.append("first %s results (%s):" % (kind, phase))
                out.extend("  " + e for e in ex)
    # windows: seconds with not-ok results, merged when less than 3 s apart
    win = []
    for s in sorted(stats.bad_seconds):
        if win and s - win[-1][1] < 3:
            win[-1][1] = s
            win[-1][2].update(stats.bad_seconds[s])
        else:
            win.append([s, s, collections.Counter(stats.bad_seconds[s])])
    out.append("")
    out.append("windows with failures (seconds less than 3 s apart merged; UTC):")
    for a, b, cc in win[:60]:
        out.append("  %s-%s (%3d s)  %s" % (time.strftime("%H:%M:%S", time.gmtime(a)), time.strftime("%H:%M:%S", time.gmtime(b)),
                                           b - a + 1, ", ".join("%s %d" % kv for kv in sorted(cc.items()))))
    if len(win) > 60:
        out.append("  ... %d more" % (len(win) - 60))
    out.append("")
    if failed:
        out.append("RESULT: FAIL")
        out.extend("  " + f for f in failed)
    else:
        out.append("RESULT: OK (at most short outages, disconnects and errors that occurred before setup too)")
    report = {"started": ts(started), "ended": ts(ended), "setup_started": ts(PHASE["since"]) if PHASE["since"] else None,
              "host": args.host, "hostname": args.hostname, "users": args.user, "clients": clients,
              "max_outage": args.max_outage, "result": "FAIL" if failed else "OK", "failed": failed,
              "counts": {"%s/%s" % ck: dict(v) for ck, v in stats.counts.items()},
              "errors_before_setup_too": dict(old_errors),
              "windows": [{"from": ts(a), "to": ts(b), "counts": dict(cc)} for a, b, cc in win]}
    return "\n".join(out) + "\n", report, not failed


CLIENTS = ["eas-ping", "eas-sync", "dav", "imap-login", "imap-idle", "smtp-auth", "roundcube"]


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
    ap.add_argument("--seed", action="store_true", help="put a marked event, contact and mail first (see above)")
    ap.add_argument("--duration", type=float, default=0, help="seconds to run (0: until a signal or --stop-file)")
    ap.add_argument("--stop-file", help="stop when this file exists")
    ap.add_argument("--marker-file", help="results before this file exists are the baseline (see above)")
    ap.add_argument("--max-outage", type=float, default=30,
                    help="longest acceptable run of 'unavailable' results of one client of one user, in seconds")
    ap.add_argument("--ping-devices", type=int, default=4, help="ActiveSync Ping devices per user")
    ap.add_argument("--sync-devices", type=int, default=2, help="ActiveSync Sync devices per user")
    ap.add_argument("--device-prefix", default=None, help="ActiveSync DeviceId prefix (default: miabload + a token)")
    ap.add_argument("--eas-interval", type=float, default=8.0)
    ap.add_argument("--ping-heartbeat", type=int, default=120, help="ActiveSync Ping heartbeat in seconds")
    ap.add_argument("--imap-interval", type=float, default=1.0)
    ap.add_argument("--smtp-interval", type=float, default=5.0)
    ap.add_argument("--dav-interval", type=float, default=4.0, help="seconds for the 4 DAV requests of a user")
    ap.add_argument("--rc-interval", type=float, default=5.0)
    ap.add_argument("--idle-renew", type=float, default=600, help="seconds before IDLE is renewed")
    ap.add_argument("--quiet", action="store_true", help="print only the summary, not each failure")
    ap.add_argument("--log", help="append every result (one JSON object per line) to this file")
    ap.add_argument("--report", help="write the JSON report (summary, windows) to this file")
    ap.add_argument("--summary", help="also write the text summary to this file")
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
    prefix = args.device_prefix or "miabload%04d" % (os.getpid() % 10000)
    if not re.fullmatch(r"[A-Za-z0-9]{1,24}", prefix):
        ap.error("--device-prefix: letters and digits only, at most 24")

    try:
        net = smoke.Net(args.host, args.hostname, args.jump)
    except Exception as e:
        print("cannot set up network path: %s" % smoke.redact(e), file=sys.stderr)
        return 2
    ctx = smoke.Ctx()
    ctx.net = net
    ctx.hostname = args.hostname
    ctx.user_pw = pw

    stats = Stats(args.log, verbose=not args.quiet)
    if args.marker_file:
        PHASE["name"] = "baseline"
    signal.signal(signal.SIGTERM, lambda *_: STOP.set())

    def setup_started(*_):
        if PHASE["name"] != "setup":
            PHASE["name"], PHASE["since"] = "setup", time.time()
            stats.mark("setup started")
    signal.signal(signal.SIGUSR1, lambda *_: SETUP_SIGNAL.set())

    if args.seed:
        seed(args, ctx, net, args.user, pw, stats)
    started = time.time()
    threads = []

    def start(fn, *a):
        t = threading.Thread(target=fn, args=a, daemon=True)
        t.start()
        threads.append(t)
        time.sleep(random.uniform(0.05, 0.3))  # spread the start
    stats.mark("client load started: %s for %s, %d+%d ActiveSync devices per user, prefix %s" % (
        ",".join(clients), ", ".join(args.user), args.ping_devices, args.sync_devices, prefix))
    for n, user in enumerate(args.user):
        if "eas-ping" in clients:
            for k in range(args.ping_devices):
                start(eas_ping_client, args, net, user, pw, "%sp%02d%02d" % (prefix, n, k), stats)
        if "eas-sync" in clients:
            for k in range(args.sync_devices):
                start(eas_sync_client, args, net, user, pw, "%ss%02d%02d" % (prefix, n, k), stats)
        if "dav" in clients:
            start(dav_client, args, ctx, user, pw, stats)
        if "imap-login" in clients:
            start(imap_login_client, args, net, user, pw, stats)
        if "imap-idle" in clients:
            start(imap_idle_client, args, net, user, pw, stats)
        if "smtp-auth" in clients:
            start(smtp_client, args, net, user, pw, stats)
        if "roundcube" in clients:
            start(roundcube_client, args, ctx, user, pw, stats)
    try:
        while not STOP.is_set():
            if args.duration and time.time() - started >= args.duration:
                break
            if args.stop_file and os.path.exists(args.stop_file):
                break
            if SETUP_SIGNAL.is_set() or (args.marker_file and PHASE["name"] != "setup"
                                          and os.path.exists(args.marker_file)):
                setup_started()
            STOP.wait(0.5)
    except KeyboardInterrupt:
        pass
    STOP.set()
    stats.mark("client load stopped")
    for t in threads:
        t.join(3)  # a Ping in flight is left behind (daemon thread)
    net.close()
    ended = time.time()
    with stats.lock:
        text, report, ok = summarize(args, stats, clients, started, ended)
        if stats.log:
            stats.log.close()
            stats.log = None
    print()
    sys.stdout.write(text)
    if args.summary:
        with open(args.summary, "w", encoding="utf-8") as f:
            f.write(text)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
            f.write("\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
