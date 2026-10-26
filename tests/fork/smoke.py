#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smoke test for the Mail-in-a-Box fork (Ubuntu 26.04) -- python3 stdlib only.

Checks the "green criteria" of a box and prints a PASS/FAIL/SKIP table plus a
JSON report. Works against a fresh install (--mode fresh) or against a box that
received the user-data of a legacy box (--mode migrated --manifest FILE, the
manifest written by tests/fork/seed-legacy.sh).

Where it can run
  * from a workstation outside the test network: when the test VMs sit on a
    private bridge (e.g. 192.0.2.0/24), give --jump SSHHOST: all TCP ports are forwarded through that host and the box
    sees the jump host as client.
  * on another host on the same network, or on the box itself (then the box
    treats the client as mynetworks: no greylisting, no quota-status policy).

Remote commands (sa-learn --dump magic, fail2ban-client, ssh-keygen -r, sqlite3)
go through --ssh SSHHOST (or --ssh local when the script runs on the box), with
"sudo -n" for privileged commands.

Port-25 mail (and the fail2ban attack) can be sent from a second MIAB with
--peer-ssh SSHHOST (--peer IP for the IP the target sees). The snippet runs
there with "python3 -", so the target sees a real foreign MTA IP.

Typical runs from a workstation (credentials from --env-file, see below). The
examples use a legacy box 192.0.2.10 (ssh alias legacy-box), a new 26.04 box
192.0.2.11 (new-box) and the virtualization host as jump-host:

  T1 fresh 26.04 box, test accounts created by the script:
    tests/fork/smoke.py --host 192.0.2.11 --hostname box.fresh.example.net \\
        --mode fresh --provision --jump legacy-box --ssh new-box \\
        --peer 192.0.2.10 --peer-ssh legacy-box

  T2 migrated box (after restoring the legacy box's /home/user-data):
    scp legacy-box:/root/seed-manifest.json ...   (sudo cat)
    tests/fork/smoke.py --host 192.0.2.11 --hostname box.legacy.example.net \\
        --mode migrated --manifest seed-manifest.json --jump legacy-box \\
        --ssh new-box --peer 192.0.2.10 --peer-ssh legacy-box

  Baseline against the legacy box itself (22.04 / v74, Nextcloud 26):
    tests/fork/smoke.py --host 192.0.2.10 --hostname box.legacy.example.net \\
        --mode migrated --manifest seed-manifest.json --jump jump-host \\
        --ssh legacy-box --expect-nc 26

  Right after a setup run (an update), --only activesync checks within a
  minute that Nextcloud does not throttle the box's own services and that an
  ActiveSync account syncs its calendar and contacts.

  Add --fail2ban (last group, opt-in) to ban/unban the attacking IP. It refuses
  to run when the attack source would be the same IP the --ssh session uses.

Test mails: every mail this script sends has the header "X-Miab-Test: 1" and
a Message-ID @smoketest.invalid. The manifest comparison (mig-folders-*,
mig-pop3-uidl-*) ignores these mails and the automatic replies and bounces
to them (Auto-Submitted, with In-Reply-To, References or the returned
message pointing to a test mail), and reports how many it ignored. Any other
mail that is missing or new, and a seeded mail that is there twice, is a
FAIL. seed-legacy.sh leaves the same mails out of the manifest (in an older
manifest they are ignored as well; for POP3 only while they are still on the
box). Send your own mails to a box under test (vacation triggers, delivery
checks after a reboot) the same way, or add the header to them:

    tests/fork/smoke.py --host 192.0.2.11 --hostname box.legacy.example.net \\
        --jump legacy-box --send-test-mail bob@seed2.example.net \\
        carol@legacy.example.net --via 587

  --via 587 or 465 submits as FROM (TEST_USER_PW), --via 25 (the default)
  sends over port 25, from --peer-ssh if given. --test-subject sets the
  subject.

Passwords are read from --env-file / the environment and never printed. The
env file (KEY=VALUE lines) defaults to $MIAB_TEST_ENV, else to
tests/fork/credentials.env (ignored by git). Keys: TEST_USER_PW, FRESH_ADMIN,
FRESH_ADMIN_PW, LEGACY_ADMIN, LEGACY_ADMIN_PW, and optionally SEED2_DOMAIN /
SEED3_DOMAIN (default seed2.example.net / seed3.example.net; --seed2/--seed3
override them, a --manifest overrides all).
Exit code: 0 = no FAIL, 1 = at least one FAIL, 2 = usage error.
"""

import argparse
import atexit
import base64
import hashlib
import http.client
import imaplib
import json
import os
import poplib
import random
import re
import shlex
import smtplib
import socket
import ssl
import struct
import subprocess
import sys
import time
import urllib.parse
import uuid
from collections import Counter
from email import message_from_bytes
from email.policy import compat32
from email.utils import formatdate

if "MOVE" not in imaplib.Commands:
    imaplib.Commands["MOVE"] = ("SELECTED",)

DEFAULT_ENV_FILE = os.environ.get("MIAB_TEST_ENV") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "credentials.env")
GROUPS = ["login", "provision", "migrated", "admin", "api", "dns", "web", "activesync", "mail", "imapsieve", "fail2ban"]

SIEVE_FILTER_NAME = "seedfilter"
SIEVE_VACATION_NAME = "seedvacation"
SIEVE_FILTER = (
    'require ["fileinto", "mailbox"];\r\n'
    'if header :contains "subject" "[filtered]" {\r\n'
    '  fileinto :create "Filtered";\r\n'
    '  stop;\r\n'
    '}\r\n'
)
VACATION_SUBJECT = "Abwesend (seed)"


def sieve_vacation(carol):
    return (
        'require ["vacation"];\r\n'
        'vacation :days 1 :subject "%s" :addresses ["%s"]\r\n'
        '  "Carol ist nicht da (seed-vacation).";\r\n' % (VACATION_SUBJECT, carol)
    )


# ---------------------------------------------------------------------------
# result bookkeeping
# ---------------------------------------------------------------------------

RESULTS = []
SECRETS = set()


class Skip(Exception):
    pass


class Fail(Exception):
    pass


def redact(text):
    text = str(text)
    for s in SECRETS:
        if s and len(s) >= 4:
            text = text.replace(s, "***")
    return text


def run_check(name, fn, *a, **kw):
    t0 = time.time()
    value = None
    try:
        r = fn(*a, **kw)
        if isinstance(r, tuple) and len(r) == 2 and r[0] in ("PASS", "FAIL", "SKIP"):
            status, detail = r
        else:
            status, detail = "PASS", (r if r is not None else "")
            value = r
    except Skip as e:
        status, detail = "SKIP", str(e)
    except Fail as e:
        status, detail = "FAIL", str(e)
    except Exception as e:  # unexpected error = FAIL with type
        status, detail = "FAIL", "%s: %s" % (type(e).__name__, e)
    detail = redact(detail)
    RESULTS.append({"check": name, "status": status, "detail": detail,
                    "seconds": round(time.time() - t0, 1)})
    print("  %-4s %-38s %s" % (status, name, detail[:150]), flush=True)
    return status, value


def log(msg):
    print("[smoke] " + redact(msg), file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# credentials
# ---------------------------------------------------------------------------

def load_env_file(path):
    env = {}
    if not path or not os.path.exists(path):
        return env
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            if k.startswith("export "):
                k = k[len("export "):].strip()
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            env[k] = v
    return env


# ---------------------------------------------------------------------------
# network layer: direct, or every port forwarded through an ssh jump host
# ---------------------------------------------------------------------------

def ssl_ctx():
    c = ssl.create_default_context()
    c.check_hostname = False
    c.verify_mode = ssl.CERT_NONE  # test boxes use self-signed certificates
    return c


class Net:
    PORTS = [443, 25, 465, 587, 993, 995, 4190, 53]

    def __init__(self, host, hostname, jump=None):
        self.host = host
        self.hostname = hostname
        self.jump = jump
        self.map = {}
        self.proc = None
        if jump:
            self._start_tunnel()

    def _start_tunnel(self):
        argv = ["ssh", "-N", "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes",
                "-o", "ServerAliveInterval=15", "-o", "ConnectTimeout=20"]
        for p in self.PORTS:
            s = socket.socket()
            s.bind(("127.0.0.1", 0))
            lp = s.getsockname()[1]
            s.close()
            argv += ["-L", "127.0.0.1:%d:%s:%d" % (lp, self.host, p)]
            self.map[p] = ("127.0.0.1", lp)
        argv.append(self.jump)
        self.proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.PIPE)
        atexit.register(self.close)
        deadline = time.time() + 40
        while time.time() < deadline:
            if self.proc.poll() is not None:
                err = self.proc.stderr.read().decode(errors="replace")
                raise RuntimeError("ssh tunnel via %s exited: %s" % (self.jump, err.strip()))
            try:
                # probe the HTTPS forward only: a bare connect on 993/995/4190
                # would be logged as "no auth attempts" and feed fail2ban
                socket.create_connection(self.map[443], 2).close()
                return
            except OSError:
                time.sleep(0.5)
        raise RuntimeError("ssh tunnel via %s did not come up" % self.jump)

    def close(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except Exception:
                self.proc.kill()

    def addr(self, port):
        return self.map.get(port, (self.host, port))

    # protocol helpers ----------------------------------------------------
    def imap(self, timeout=30):
        h, p = self.addr(993)
        return imaplib.IMAP4_SSL(h, p, ssl_context=ssl_ctx(), timeout=timeout)

    def pop3(self, timeout=30):
        h, p = self.addr(995)
        return poplib.POP3_SSL(h, p, context=ssl_ctx(), timeout=timeout)

    def smtp_ssl(self, timeout=60):
        h, p = self.addr(465)
        return smtplib.SMTP_SSL(h, p, local_hostname="smoketest.invalid", context=ssl_ctx(), timeout=timeout)

    def smtp_starttls(self, timeout=60):
        h, p = self.addr(587)
        s = smtplib.SMTP(h, p, local_hostname="smoketest.invalid", timeout=timeout)
        s.starttls(context=ssl_ctx())
        s.ehlo()
        return s

    def sieve(self, timeout=30):
        h, p = self.addr(4190)
        return ManageSieve(h, p, self.hostname, timeout)


class _HTTPS(http.client.HTTPSConnection):
    def __init__(self, addr, sni, timeout):
        super().__init__(addr[0], addr[1], context=ssl_ctx(), timeout=timeout)
        self._sni = sni

    def connect(self):
        http.client.HTTPConnection.connect(self)
        self.sock = ssl_ctx().wrap_socket(self.sock, server_hostname=self._sni)


class HTTPResp:
    def __init__(self, status, headers, body):
        self.status = status
        self.headers = headers
        self.body = body

    def header(self, name):
        name = name.lower()
        return [v for k, v in self.headers if k.lower() == name]

    def text(self):
        return self.body.decode("utf-8", errors="replace")

    def json(self):
        return json.loads(self.body.decode("utf-8"))


def http_req(ctx, method, path, headers=None, body=None, auth=None, form=None, timeout=90):
    h = {"Host": ctx.hostname, "User-Agent": "miab-fork-smoke/1"}
    if headers:
        h.update(headers)
    if auth:
        h["Authorization"] = "Basic " + base64.b64encode(("%s:%s" % auth).encode()).decode()
    if form is not None:
        body = urllib.parse.urlencode(form)
        h.setdefault("Content-Type", "application/x-www-form-urlencoded")
    if isinstance(body, str):
        body = body.encode("utf-8")
    c = _HTTPS(ctx.net.addr(443), ctx.hostname, timeout)
    try:
        c.request(method, path, body=body, headers=h)
        r = c.getresponse()
        return HTTPResp(r.status, r.getheaders(), r.read())
    finally:
        c.close()


# ---------------------------------------------------------------------------
# ManageSieve (RFC 5804) minimal client
# ---------------------------------------------------------------------------

class SieveError(Exception):
    pass


class ManageSieve:
    def __init__(self, host, port, sni, timeout=30):
        self.sni = sni
        self.sock = socket.create_connection((host, port), timeout)
        self.f = self.sock.makefile("rb")
        self.caps, _ = self._response()

    def _readline(self):
        line = self.f.readline()
        if not line:
            raise SieveError("connection closed")
        return line.rstrip(b"\r\n")

    def _response(self):
        lines = []
        while True:
            line = self._readline()
            m = re.search(rb"\{(\d+)\+?\}$", line)
            if m:
                data = self.f.read(int(m.group(1)))
                rest = self._readline()
                lines.append(line[:m.start()] + data + rest)
                continue
            if line.startswith(b"OK"):
                return lines, line
            if line.startswith(b"NO") or line.startswith(b"BYE"):
                raise SieveError(line.decode(errors="replace"))
            lines.append(line)

    def cmd(self, raw):
        self.sock.sendall(raw + b"\r\n")
        return self._response()

    def starttls(self):
        self.cmd(b"STARTTLS")
        self.sock = ssl_ctx().wrap_socket(self.sock, server_hostname=self.sni)
        self.f = self.sock.makefile("rb")
        self.caps, _ = self._response()  # server re-announces capabilities

    def login(self, user, pw):
        if not any(c.upper().startswith(b'"STARTTLS"') for c in self.caps) and not isinstance(self.sock, ssl.SSLSocket):
            raise SieveError("server offers no STARTTLS")
        if not isinstance(self.sock, ssl.SSLSocket):
            self.starttls()
        cred = base64.b64encode(b"\0" + user.encode() + b"\0" + pw.encode())
        self.cmd(b'AUTHENTICATE "PLAIN" "' + cred + b'"')

    def listscripts(self):
        lines, _ = self.cmd(b"LISTSCRIPTS")
        out = []
        for line in lines:
            m = re.match(rb'^"((?:[^"\\]|\\.)*)"(\s+ACTIVE)?', line)
            if m:
                out.append((m.group(1).decode(), bool(m.group(2))))
        return out

    def putscript(self, name, text):
        data = text.encode("utf-8")
        self.sock.sendall(b'PUTSCRIPT "%s" {%d+}\r\n' % (name.encode(), len(data)) + data + b"\r\n")
        return self._response()

    def setactive(self, name):
        return self.cmd(b'SETACTIVE "%s"' % name.encode())

    def logout(self):
        try:
            self.cmd(b"LOGOUT")
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# minimal DNS client over TCP (works through the ssh port forward)
# ---------------------------------------------------------------------------

QTYPES = {"A": 1, "NS": 2, "SOA": 6, "MX": 15, "TXT": 16, "AAAA": 28, "SSHFP": 44,
          "RRSIG": 46, "DNSKEY": 48}
QTYPE_NAMES = {v: k for k, v in QTYPES.items()}


def _recvn(s, n):
    buf = b""
    while len(buf) < n:
        chunk = s.recv(n - len(buf))
        if not chunk:
            raise OSError("short DNS read")
        buf += chunk
    return buf


def _read_name(data, off):
    labels = []
    end = None
    hops = 0
    while True:
        ln = data[off]
        if ln & 0xC0 == 0xC0:
            if end is None:
                end = off + 2
            off = ((ln & 0x3F) << 8) | data[off + 1]
            hops += 1
            if hops > 50:
                raise ValueError("DNS name loop")
            continue
        if ln == 0:
            off += 1
            break
        labels.append(data[off + 1:off + 1 + ln].decode("ascii", "replace"))
        off += 1 + ln
    return ".".join(labels), (end if end is not None else off)


def dns_query(ctx, qname, qtype, do=True, timeout=15):
    tid = random.randint(0, 65535)
    msg = struct.pack(">HHHHHH", tid, 0, 1, 0, 0, 1 if do else 0)
    for label in qname.rstrip(".").split("."):
        msg += bytes([len(label)]) + label.encode("ascii")
    msg += b"\0" + struct.pack(">HH", QTYPES[qtype], 1)
    if do:
        msg += b"\0" + struct.pack(">HHIH", 41, 4096, 0x00008000, 0)
    with socket.create_connection(ctx.net.addr(53), timeout) as s:
        s.sendall(struct.pack(">H", len(msg)) + msg)
        ln = struct.unpack(">H", _recvn(s, 2))[0]
        data = _recvn(s, ln)
    rid, flags, qd, an, _ns, _ar = struct.unpack(">HHHHHH", data[:12])
    off = 12
    for _ in range(qd):
        _, off = _read_name(data, off)
        off += 4
    answers = []
    for _ in range(an):
        name, off = _read_name(data, off)
        rtype, _rclass, _ttl, rdlen = struct.unpack(">HHIH", data[off:off + 10])
        off += 10
        rdata = data[off:off + rdlen]
        rdoff = off
        off += rdlen
        tname = QTYPE_NAMES.get(rtype, str(rtype))
        if rtype == 16:
            parts, i = [], 0
            while i < len(rdata):
                n = rdata[i]
                parts.append(rdata[i + 1:i + 1 + n].decode("utf-8", "replace"))
                i += 1 + n
            value = "".join(parts)
        elif rtype == 44:
            value = (rdata[0], rdata[1], rdata[2:].hex().lower())
        elif rtype == 46:
            value = QTYPE_NAMES.get(struct.unpack(">H", rdata[:2])[0], "?")
        elif rtype == 15:
            value = _read_name(data, rdoff + 2)[0]
        elif rtype == 1:
            value = socket.inet_ntoa(rdata)
        else:
            value = rdata.hex()
        answers.append((name.lower(), tname, value))
    return {"rcode": flags & 0xF, "aa": bool(flags & 0x0400), "answers": answers}


# ---------------------------------------------------------------------------
# remote command runner (--ssh HOST | --ssh local)
# ---------------------------------------------------------------------------

class Remote:
    def __init__(self, spec):
        self.spec = spec

    def available(self):
        return bool(self.spec)

    def run(self, cmd, sudo=False, timeout=180, check=False):
        if not self.spec:
            raise Skip("needs --ssh")
        if sudo and not (self.spec == "local" and os.geteuid() == 0):
            cmd = "sudo -n " + cmd
        if self.spec == "local":
            argv = ["bash", "-c", cmd]
        else:
            argv = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", self.spec, cmd]
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        if check and p.returncode != 0:
            raise Fail("remote command failed (%d): %s %s" % (p.returncode, cmd, p.stderr.strip()[:300]))
        return p.returncode, p.stdout, p.stderr


def run_snippet(snippet, func, spec, ssh_host=None, timeout=900):
    """Run func(spec) from a self-contained snippet locally or on ssh_host via 'python3 -'."""
    if not ssh_host:
        ns = {"__name__": "smoke_snippet"}
        exec(snippet, ns)
        return ns[func](spec)
    arg = base64.b64encode(json.dumps(spec).encode()).decode()
    stub = ("\nif __name__ == '__main__':\n    import sys, json, base64\n"
            "    print(json.dumps(globals()[sys.argv[1]](json.loads(base64.b64decode(sys.argv[2])))))\n")
    p = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", ssh_host,
                        "python3 - %s %s" % (func, arg)],
                       input=snippet + stub, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise Fail("snippet on %s failed: %s" % (ssh_host, p.stderr.strip()[-400:]))
    return json.loads(p.stdout.strip().splitlines()[-1])


# Port-25 delivery; runs here or on the peer. No secrets in it.
SMTP_SNIPPET = r'''
import base64, os, smtplib, socket

def deliver(spec):
    out = {}
    for m in spec["messages"]:
        data = m.get("data")
        if data is None:
            blob = base64.encodebytes(os.urandom(m["gen_size"] * 3 // 4)).decode().replace("\n", "\r\n")
            data = m["gen_headers"] + "\r\n" + blob
        data = data.encode("utf-8")
        try:
            s = smtplib.SMTP(spec["host"], spec["port"], local_hostname=spec.get("helo", "smoketest.invalid"), timeout=300)
            try:
                s.ehlo()
                s.sendmail(m["from"], [m["rcpt"]], data)
                out[m["id"]] = [250, "accepted"]
            finally:
                try:
                    s.quit()
                except Exception:
                    pass
        except smtplib.SMTPRecipientsRefused as e:
            code, msg = list(e.recipients.values())[0]
            out[m["id"]] = [code, msg.decode("utf-8", "replace")]
        except smtplib.SMTPResponseException as e:
            msg = e.smtp_error.decode("utf-8", "replace") if isinstance(e.smtp_error, bytes) else str(e.smtp_error)
            out[m["id"]] = [e.smtp_code, msg]
        except Exception as e:
            out[m["id"]] = [0, "%s: %s" % (type(e).__name__, e)]
    return out

def source_ip(spec):
    u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        u.connect((spec["host"], spec.get("port", 25)))
        return u.getsockname()[0]
    finally:
        u.close()
'''

# fail2ban attack (wrong passwords); runs here or on the peer.
F2B_SNIPPET = r'''
import base64, imaplib, poplib, smtplib, socket, ssl, time
from concurrent.futures import ThreadPoolExecutor

USER = "f2btest-nouser@invalid.example"
PW = "definitely-wrong-password"

def _ctx():
    c = ssl.create_default_context()
    c.check_hostname = False
    c.verify_mode = ssl.CERT_NONE
    return c

def _rd(f):
    while True:
        l = f.readline()
        if not l:
            raise EOFError("closed")
        if l[:2] in (b"OK", b"NO") or l[:3] == b"BYE":
            return l

def one(proto, host, port):
    try:
        if proto == "imap":
            M = imaplib.IMAP4_SSL(host, port, ssl_context=_ctx(), timeout=20)
            try:
                M.login(USER, PW)
            except imaplib.IMAP4.error:
                pass
            try:
                M.logout()
            except Exception:
                pass
        elif proto == "pop3":
            P = poplib.POP3_SSL(host, port, context=_ctx(), timeout=20)
            try:
                P.user(USER)
                P.pass_(PW)
            except poplib.error_proto:
                pass
            try:
                P.quit()
            except Exception:
                pass
        elif proto in ("smtp587", "smtp465"):
            if proto == "smtp465":
                S = smtplib.SMTP_SSL(host, port, context=_ctx(), timeout=20)
            else:
                S = smtplib.SMTP(host, port, timeout=20)
                S.starttls(context=_ctx())
            S.ehlo()
            try:
                S.login(USER, PW)
            except smtplib.SMTPAuthenticationError:
                pass
            try:
                S.quit()
            except Exception:
                pass
        elif proto == "managesieve":
            s = socket.create_connection((host, port), 20)
            try:
                f = s.makefile("rb")
                _rd(f)
                s.sendall(b"STARTTLS\r\n")
                if _rd(f).startswith(b"OK"):
                    t = _ctx().wrap_socket(s)
                    f2 = t.makefile("rb")
                    _rd(f2)
                    cred = base64.b64encode(("\0%s\0%s" % (USER, PW)).encode())
                    t.sendall(b'AUTHENTICATE "PLAIN" "' + cred + b'"\r\n')
                    _rd(f2)
                    t.sendall(b"LOGOUT\r\n")
                    t.close()
            finally:
                s.close()
        return "ok"
    except (ConnectionRefusedError, ConnectionResetError, socket.timeout, TimeoutError) as e:
        return "blocked:" + type(e).__name__
    except Exception as e:
        return "error:%s" % type(e).__name__

def attack(spec):
    host, port, proto = spec["host"], spec["port"], spec["proto"]
    t0 = time.time()
    with ThreadPoolExecutor(spec.get("parallel", 8)) as ex:
        res = list(ex.map(lambda i: one(proto, host, port), range(spec["count"])))
    elapsed = time.time() - t0
    time.sleep(spec.get("settle", 5))
    probe = one(proto, host, port)
    summary = {}
    for r in res:
        k = r.split(":")[0]
        summary[k] = summary.get(k, 0) + 1
    return {"seconds": round(elapsed, 1), "summary": summary, "probe_after": probe}
'''


# ---------------------------------------------------------------------------
# context
# ---------------------------------------------------------------------------

class Ctx:
    pass


# Every mail of a test carries TEST_HEADER and a Message-ID in TEST_MSGID_DOMAIN
# (mkmsg; --send-test-mail for the testers' own mails). The manifest
# comparison ignores these mails and the automatic replies to them.
TEST_HEADER = "X-Miab-Test"
TEST_MSGID_DOMAIN = "smoketest.invalid"


def mkmsg(frm, to, subject, sid, body=None, extra=None):
    lines = ["From: %s" % frm, "To: %s" % to, "Subject: %s" % subject,
             "Date: %s" % formatdate(localtime=True),
             "Message-ID: <%s.%s@%s>" % (sid, uuid.uuid4().hex, TEST_MSGID_DOMAIN),
             "X-Smoke-Id: %s" % sid, "%s: 1" % TEST_HEADER, "MIME-Version: 1.0",
             "Content-Type: text/plain; charset=utf-8"]
    lines += extra or []
    if body is None:
        body = "Smoke test message %s.\r\nThis is a functional test of the mail flow.\r\n" % sid
    return "\r\n".join(lines) + "\r\n\r\n" + body


def qmb(name):
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


def imap_login(ctx, user):
    M = ctx.net.imap()
    M.login(user, ctx.user_pw)
    return M


LIST_RE = re.compile(r'^\((?P<flags>[^)]*)\) (?P<delim>"(?:[^"\\]|\\.)*"|NIL) (?P<name>.+)$')


def list_folders(M):
    typ, data = M.list()
    out = []
    for raw in data or []:
        if raw is None:
            continue
        if isinstance(raw, tuple):  # literal name
            line = raw[0].decode(errors="replace")
            name = raw[1].decode(errors="replace")
            m = LIST_RE.match(line.rsplit(" ", 1)[0] + " x")
            flags = m.group("flags") if m else ""
        else:
            line = raw.decode(errors="replace")
            m = LIST_RE.match(line)
            if not m:
                continue
            flags, name = m.group("flags"), m.group("name")
            if name.startswith('"'):
                name = name[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        if "\\noselect" in flags.lower() or "\\nonexistent" in flags.lower():
            continue
        out.append(name)
    return out


def folder_status(M, folder):
    typ, data = M.status(qmb(folder), "(MESSAGES UIDVALIDITY UIDNEXT)")
    if typ != "OK":
        return None
    s = data[0].decode(errors="replace")
    vals = dict(re.findall(r"(MESSAGES|UIDVALIDITY|UIDNEXT) (\d+)", s))
    return {k.lower(): int(v) for k, v in vals.items()}


def uid_search(M, folder, *criteria, readonly=True):
    typ, _ = M.select(qmb(folder), readonly=readonly)
    if typ != "OK":
        return []
    typ, data = M.uid("SEARCH", *criteria)
    if typ != "OK" or not data or not data[0]:
        return []
    return data[0].split()


def pop3_uidls(ctx, user):
    P = ctx.net.pop3()
    try:
        P.user(user)
        P.pass_(ctx.user_pw)
        _resp, lines, _ = P.uidl()
        return [l.decode().split(None, 1)[1] for l in lines]
    finally:
        try:
            P.quit()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# mailbox comparison with the manifest, test-aware
# ---------------------------------------------------------------------------

MSGID_RE = re.compile(r"<([^<>\s]+)>")


def parse_mail(raw):
    """A message (or only its header) as email.message.Message."""
    if isinstance(raw, str):
        raw = raw.encode("utf-8", "replace")
    return message_from_bytes(raw, policy=compat32)


def mail_id(msg):
    m = MSGID_RE.search(str(msg.get("Message-ID", "")))
    return m.group(1) if m else ""


def is_marked(msg):
    return str(msg.get(TEST_HEADER, "")).strip() == "1"


def mail_refs(msg):
    """Message-IDs a mail refers to: In-Reply-To, References and, in a
    delivery report (bounce), the Message-ID of the returned message."""
    refs = MSGID_RE.findall(str(msg.get("In-Reply-To", "")) + " " + str(msg.get("References", "")))
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct in ("message/rfc822", "message/rfc822-headers", "text/rfc822-headers"):
                payload = part.get_payload()
                if isinstance(payload, list):
                    for inner in payload:
                        refs += MSGID_RE.findall(str(inner.get("Message-ID", "")))
                else:
                    raw = payload if isinstance(payload, str) else ""
                    refs += MSGID_RE.findall(" ".join(re.findall(r"(?im)^message-id:\s*(.*)$", raw)))
    return refs


def test_mail_reason(msg, marked_ids):
    """Why a mail is a test mail ("marked", "auto-reply"), or None."""
    if is_marked(msg):
        return "marked"
    auto = str(msg.get("Auto-Submitted", "")).strip().lower()
    if auto.startswith("auto-replied") or auto.startswith("auto-generated"):
        for ref in mail_refs(msg):
            if ref in marked_ids or ref.lower().endswith("@" + TEST_MSGID_DOMAIN):
                return "auto-reply"
    return None


def needs_body(msg):
    """Whether the whole message is needed to classify it (a bounce)."""
    return bool(str(msg.get("Auto-Submitted", "")).strip()) and msg.get_content_maintype() == "multipart"


def compare_mails(want_ids, want_count, mails, marked_ids):
    """Compare the mails of a folder with the manifest. mails: Message objects.
    Test mails are ignored; anything else that is missing or extra, and a
    seeded mail that is there twice, is a problem.
    Returns (problems, ignored {reason: count})."""
    ignored, kept, test_ids = Counter(), [], set()
    for msg in mails:
        reason = test_mail_reason(msg, marked_ids)
        if reason:
            ignored[reason] += 1
            test_ids.add(mail_id(msg))
        else:
            kept.append(msg)
    problems = []
    have = Counter(mail_id(m) for m in kept)
    if want_ids is not None:
        # seed-legacy.sh leaves test mails out of the manifest; one written
        # before that may still list them (those that are gone count as ignored).
        want = Counter()
        for i in want_ids:
            if i and i in test_ids and not have[i]:
                continue
            if i.lower().endswith("@" + TEST_MSGID_DOMAIN):
                ignored["gone"] += 1
                continue
            want[i] += 1
        missing = want - have
        extra = have - want
        dup = {i: n for i, n in extra.items() if i in want}
        new = {i: n for i, n in extra.items() if i not in want}
        if missing:
            problems.append("%d missing (e.g. %s)" % (sum(missing.values()), sorted(missing)[:2]))
        if dup:
            problems.append("%d duplicates of seeded mails (e.g. %s)" % (sum(dup.values()), sorted(dup)[:2]))
        if new:
            subjects = [str(m.get("Subject", ""))[:40] for m in kept if mail_id(m) in new][:2]
            problems.append("%d new, not test mails (e.g. %s)" % (sum(new.values()), subjects))
    else:
        if len(kept) != want_count:
            problems.append("%d msgs != %s (%d test mails ignored)" % (len(kept), want_count, sum(ignored.values())))
        dup = {i: n for i, n in have.items() if i and n > 1}
        if dup:
            problems.append("%d mails with the same Message-ID (e.g. %s)" % (sum(dup.values()), sorted(dup)[:2]))
    return problems, ignored


def ignored_text(ignored):
    n = sum(ignored.values())
    if not n:
        return "no test mails"
    return "%d test mail%s ignored (%s)" % (n, "" if n == 1 else "s", ", ".join("%d %s" % (v, k) for k, v in sorted(ignored.items())))


def fetch_mails(M, folder):
    """The mails of a folder (headers; whole message for possible bounces)."""
    typ, _ = M.select(qmb(folder), readonly=True)
    if typ != "OK":
        return None
    typ, data = M.uid("SEARCH", "ALL")
    if typ != "OK" or not data or not data[0]:
        return []
    out = []
    typ, data = M.uid("FETCH", b",".join(data[0].split()).decode(), "(BODY.PEEK[HEADER])")
    for item in data or []:
        if not isinstance(item, tuple):
            continue
        msg = parse_mail(item[1])
        if needs_body(msg):
            m = re.search(rb"UID (\d+)", item[0])
            if m:
                typ, full = M.uid("FETCH", m.group(1).decode(), "(BODY.PEEK[])")
                for f in full or []:
                    if isinstance(f, tuple):
                        msg = parse_mail(f[1])
                        break
        out.append(msg)
    return out


def marked_ids(ctx):
    """Message-IDs of the marked test mails in all mailboxes of the manifest
    (an automatic reply lands in another mailbox than the mail it answers)."""
    if getattr(ctx, "marked_ids", None) is None:
        ids = set()
        for user, info in sorted(ctx.manifest.get("users", {}).items()):
            try:
                M = imap_login(ctx, user)
            except Exception:
                continue
            try:
                for folder in list_folders(M):
                    for msg in fetch_mails(M, folder) or []:
                        if is_marked(msg) and mail_id(msg):
                            ids.add(mail_id(msg))
            finally:
                M.logout()
        ctx.marked_ids = ids
    return ctx.marked_ids


def pop3_mails(ctx, user, uidls):
    """{uidl: Message} for the given POP3 UIDLs (TOP, which does not mark them read)."""
    P = ctx.net.pop3()
    out = {}
    try:
        P.user(user)
        P.pass_(ctx.user_pw)
        _resp, lines, _ = P.uidl()
        num = {}
        for line in lines:
            n, u = line.decode().split(None, 1)
            num[u] = n
        for u in uidls:
            if u in num:
                _resp, body, _ = P.top(num[u], 300)
                out[u] = parse_mail(b"\r\n".join(body) + b"\r\n")
    finally:
        try:
            P.quit()
        except Exception:
            pass
    return out


def sa_magic(ctx):
    rc, out, err = ctx.remote.run(ctx.args.sa_learn_cmd, sudo=False, timeout=120)
    vals = {}
    for line in out.splitlines():
        m = re.match(r"^\s*\S+\s+\S+\s+(\d+)\s+\S+\s+non-token data: (nspam|nham)\s*$", line)
        if m:
            vals[m.group(2)] = int(m.group(1))
    if "nspam" not in vals:
        raise Fail("could not parse sa-learn --dump magic (rc=%d): %s" % (rc, (err or out).strip()[:300]))
    return vals


def admin_api(ctx, method, path, form=None, auth=None, body=None, headers=None, timeout=90):
    auth = auth or ctx.admin_auth
    if not auth:
        raise Skip("no admin session (admin credentials missing or login failed)")
    return http_req(ctx, method, "/admin/" + path.lstrip("/"), form=form, auth=auth, body=body, headers=headers,
                    timeout=timeout)


def remove_test_mailbox(ctx, email):
    # Adding a user makes Dovecot create its mailbox (quota recalc), which
    # stays after the user is removed and is listed as an archived
    # (inactive) account. Remove it again for the test accounts of this run
    # (needs --ssh). Returns a note.
    local, domain = email.split("@", 1)
    if not re.fullmatch(r"smoke[a-z]*-[0-9a-f]{10}", local) or not re.fullmatch(r"[a-z0-9.-]+", domain) or ctx.tok not in local:
        raise Fail("not a test account of this run: %s" % email)
    if not ctx.remote.available():
        return "its archived mailbox stays (no --ssh)"
    cmd = ('root=$(sed -n "s/^STORAGE_ROOT=//p" /etc/mailinabox.conf | tail -n 1); '
           'd="$root/mail/mailboxes/%s/%s"; [ -n "$root" ] && [ ! -L "$d" ] && rm -rf -- "$d" && [ ! -e "$d" ]') % (domain, local)
    rc, out, err = ctx.remote.run("bash -c %s" % shlex.quote(cmd), sudo=True, timeout=60)
    if rc != 0:
        raise Fail("could not remove the archived mailbox of %s: %s" % (email, err.strip()[:120]))
    return "archived mailbox removed"


# ---------------------------------------------------------------------------
# checks: logins
# ---------------------------------------------------------------------------

def c_imap_login(ctx):
    M = imap_login(ctx, ctx.alice)
    typ, _ = M.select("INBOX", readonly=True)
    caps = " ".join(c if isinstance(c, str) else c.decode() for c in M.capabilities)
    M.logout()
    if typ != "OK":
        raise Fail("SELECT INBOX failed")
    return "login ok; caps incl. MOVE=%s QUOTA=%s" % ("MOVE" in caps, "QUOTA" in caps)


def c_pop3_login(ctx):
    u = pop3_uidls(ctx, ctx.alice)
    return "login ok, %d messages in INBOX" % len(u)


def c_sub465(ctx):
    s = ctx.net.smtp_ssl()
    try:
        s.login(ctx.alice, ctx.user_pw)
    finally:
        s.quit()
    return "AUTH ok"


def c_sub587(ctx):
    s = ctx.net.smtp_starttls()
    try:
        s.login(ctx.alice, ctx.user_pw)
    finally:
        s.quit()
    return "STARTTLS + AUTH ok"


def c_sieve_login(ctx):
    ms = ctx.net.sieve()
    try:
        ms.login(ctx.alice, ctx.user_pw)
        scripts = ms.listscripts()
    finally:
        ms.logout()
    ctx.alice_scripts = scripts
    return "login ok, scripts: %s" % (", ".join("%s%s" % (n, "*" if a else "") for n, a in scripts) or "none")


# The services of Mail-in-a-Box must be enabled, or they do not start after a
# reboot (the in-place upgrade of rc3 left Dovecot disabled, B67). The PHP-FPM
# unit is found, so that the baseline against an old box works too. Only the
# state on stdout counts: for a SysV service (postgrey on 22.04) systemctl
# prints a notice on stderr first.
CORE_UNITS = ["postfix", "dovecot", "nginx", "spampd", "opendkim", "opendmarc", "postgrey",
              "fail2ban", "nsd", "named", "munin-node", "mailinabox", "cron"]
UNIT_ENABLED_STATES = ("enabled", "static", "indirect", "generated", "alias")


def c_services_enabled(ctx):
    cmd = ("for u in %s $(cd /lib/systemd/system && ls php*-fpm.service 2>/dev/null); do "
           "printf '%%s ' \"${u%%.service}\"; systemctl is-enabled \"$u\" 2>/dev/null | head -n 1; echo; done"
           % " ".join(CORE_UNITS))
    rc, out, err = ctx.remote.run(cmd, timeout=60)
    states = {}
    for line in out.splitlines():
        unit, _, state = line.strip().partition(" ")
        if unit:
            states[unit] = state.strip()
    missing = [u for u in CORE_UNITS if u not in states]
    if missing:
        raise Fail("no answer for %s: %s" % (" ".join(missing), (err or out).strip()[:200]))
    bad = ["%s=%s" % (u, st) for u, st in sorted(states.items()) if st not in UNIT_ENABLED_STATES]
    if bad:
        raise Fail("not enabled (would not start after a reboot): %s" % ", ".join(bad))
    return "%d units enabled" % len(states)


def c_mail_log_logins(ctx):
    # The usage report (management/mail_log.py, run weekly by daily_tasks.sh) must
    # count the IMAP and POP3 logins just made (Dovecot 2.4 logs "Logged in:").
    rc, miab, _err = ctx.remote.run("awk '$1 == \"cd\" { print $2; exit }' /usr/local/bin/mailinabox")
    miab = miab.strip()
    if rc != 0 or not miab:
        raise Skip("Mail-in-a-Box checkout not found in /usr/local/bin/mailinabox")
    cmd = "cd %s && management/mail_log.py -l -v -t hour -u %s" % (shlex.quote(miab), shlex.quote(ctx.alice))
    rc, out, err = ctx.remote.run("bash -c %s" % shlex.quote(cmd), sudo=True, timeout=300)
    if rc != 0:
        raise Fail("mail_log.py rc=%d: %s" % (rc, (err or out).strip()[-200:]))
    counts = {p: sum(int(n) for n in re.findall(r"\b%s \S+: (\d+) times" % p, out)) for p in ("imap", "pop3")}
    missing = [p for p, n in counts.items() if not n]
    if missing:
        raise Fail("no %s logins of %s in the last hour counted" % ("/".join(missing), ctx.alice))
    return "logins of the last hour: imap %d, pop3 %d" % (counts["imap"], counts["pop3"])


# ---------------------------------------------------------------------------
# provisioning (fresh box): users, aliases, sieve scripts
# ---------------------------------------------------------------------------

def c_provision(ctx):
    done = []
    for email, quota in ((ctx.alice, "0"), (ctx.bob, "10M"), (ctx.carol, "0")):
        r = admin_api(ctx, "POST", "mail/users/add", form={"email": email, "password": ctx.user_pw, "quota": quota})
        if r.status == 200:
            done.append("+" + email)
        elif r.status == 400 and "already exists" in r.text():
            r2 = admin_api(ctx, "POST", "mail/users/password", form={"email": email, "password": ctx.user_pw})
            r3 = admin_api(ctx, "POST", "mail/users/quota", form={"email": email, "quota": quota})
            if r2.status != 200 or r3.status != 200:
                raise Fail("cannot reset %s: %s %s" % (email, r2.text()[:100], r3.text()[:100]))
        else:
            raise Fail("users/add %s: HTTP %d %s" % (email, r.status, r.text()[:200]))
    aliases = [
        ("info@" + ctx.domain, ctx.alice, ""),
        ("@" + ctx.seed2, ctx.bob, ""),
        ("@" + ctx.seed3, "@" + ctx.seed2, ""),
        ("team@" + ctx.domain, "%s,%s" % (ctx.alice, ctx.carol), ctx.alice),
    ]
    for addr, fwd, senders in aliases:
        r = admin_api(ctx, "POST", "mail/aliases/add", form={"address": addr, "forwards_to": fwd,
                                                             "permitted_senders": senders, "update_if_exists": "1"})
        if r.status != 200:
            raise Fail("aliases/add %s: HTTP %d %s" % (addr, r.status, r.text()[:200]))
    for user, name, text in ((ctx.alice, SIEVE_FILTER_NAME, SIEVE_FILTER),
                             (ctx.carol, SIEVE_VACATION_NAME, sieve_vacation(ctx.carol))):
        ms = ctx.net.sieve()
        try:
            ms.login(user, ctx.user_pw)
            ms.putscript(name, text)
            ms.setactive(name)
        finally:
            ms.logout()
    return "users/aliases/sieve ensured %s" % " ".join(done)


# ---------------------------------------------------------------------------
# checks: migrated mode (compare with manifest; run before new mail arrives)
# ---------------------------------------------------------------------------

def c_mig_users_aliases(ctx):
    man = ctx.manifest
    r = admin_api(ctx, "GET", "mail/users?format=json")
    if r.status != 200:
        raise Fail("users list HTTP %d" % r.status)
    users = {}
    for d in r.json():
        for u in d.get("users", []):
            users[u["email"]] = u
    problems = []
    for email, info in man.get("users", {}).items():
        if email not in users:
            problems.append("missing user " + email)
        elif str(users[email].get("quota", "0")) != str(info.get("quota", "0")):
            problems.append("%s quota %s != %s" % (email, users[email].get("quota"), info.get("quota")))
    r = admin_api(ctx, "GET", "mail/aliases?format=json")
    have = {}
    for d in r.json():
        for a in d.get("aliases", []):
            if not a.get("auto"):
                have[a["address"]] = (sorted(a.get("forwards_to") or []), sorted(a.get("permitted_senders") or []))
    for a in man.get("aliases", []):
        want = (sorted(a.get("forwards_to") or []), sorted(a.get("permitted_senders") or []))
        if a["address"] not in have:
            problems.append("missing alias " + a["address"])
        elif have[a["address"]] != want:
            problems.append("alias %s differs: %s != %s" % (a["address"], have[a["address"]], want))
    if problems:
        raise Fail("; ".join(problems))
    return "%d users, %d aliases match" % (len(man.get("users", {})), len(man.get("aliases", [])))


def c_mig_pop3(ctx, user):
    want = ctx.manifest["users"][user].get("pop3_uidls")
    if want is None:
        raise Skip("manifest has no POP3 UIDLs for " + user)
    have = pop3_uidls(ctx, user)
    if have == want:
        return "%d UIDLs identical, no test mails" % len(have)
    if sorted(have) != sorted(want) and sorted(x.lower() for x in have) == sorted(x.lower() for x in want):
        raise Fail("UIDLs differ only in letter case (e.g. %s vs %s): POP3 clients would re-download everything; "
                   "pop3_uidl_format must reproduce 2.3's %%08Xu%%08Xv (upper-case hex)" % (have[:1], want[:1]))
    wanted = set(want)
    new = [u for u in have if u not in wanted]
    mails = pop3_mails(ctx, user, new)
    seeded = set(ctx.manifest["users"][user].get("folders", {}).get("INBOX", {}).get("message_ids") or [])
    ignored, dup, other = Counter(), [], []
    for u in new:
        msg = mails.get(u)
        reason = test_mail_reason(msg, marked_ids(ctx)) if msg is not None else None
        if reason:
            ignored[reason] += 1
        elif msg is not None and mail_id(msg) in seeded:
            dup.append(u)
        else:
            other.append(u)
    kept = [u for u in have if u in wanted or u in dup or u in other]
    missing = [u for u in want if u not in set(have)]
    if kept == want:
        return "%d UIDLs identical, %s" % (len(want), ignored_text(ignored))
    problems = []
    if missing:
        problems.append("%d missing" % len(missing))
    if dup:
        problems.append("%d duplicates of seeded mails" % len(dup))
    if other:
        problems.append("%d new, not test mails" % len(other))
    if not problems:
        problems.append("order differs")
    raise Fail("UIDLs differ: %s (have %d, want %d, %s); sample have=%s want=%s"
               % (", ".join(problems), len(have), len(want), ignored_text(ignored), have[:2], want[:2]))


def c_mig_folders(ctx, user):
    want = ctx.manifest["users"][user].get("folders", {})
    marked = marked_ids(ctx)
    ignored = Counter()
    M = imap_login(ctx, user)
    try:
        problems = []
        have_folders = set(list_folders(M))
        for folder, info in want.items():
            if folder not in have_folders:
                problems.append("missing folder %s" % folder)
                continue
            st = folder_status(M, folder) or {}
            mails = fetch_mails(M, folder)
            if mails is None:
                problems.append("%s: cannot select" % folder)
                continue
            p, ign = compare_mails(info.get("message_ids"), info.get("messages"), mails, marked)
            ignored.update(ign)
            problems += ["%s: %s" % (folder, x) for x in p]
            if info.get("uidvalidity") and st.get("uidvalidity") != info["uidvalidity"]:
                problems.append("%s: UIDVALIDITY %s != %s (IMAP clients resync)" % (folder, st.get("uidvalidity"), info["uidvalidity"]))
    finally:
        M.logout()
    if problems:
        raise Fail("; ".join(problems) + "; " + ignored_text(ignored))
    return "%d folders match (%s), %s" % (len(want), ", ".join("%s=%d" % (k, v.get("messages", 0)) for k, v in want.items()),
                                          ignored_text(ignored))


def c_mig_sieve(ctx):
    problems, seen = [], []
    for user, info in ctx.manifest.get("sieve", {}).items():
        ms = ctx.net.sieve()
        try:
            ms.login(user, ctx.user_pw)
            scripts = ms.listscripts()
        finally:
            ms.logout()
        active = [n for n, a in scripts if a]
        seen.append("%s:%s" % (user.split("@")[0], ",".join(active) or "-"))
        if info.get("active") and info["active"] not in active:
            problems.append("%s active script %s not active (have %s)" % (user, info["active"], scripts))
    if problems:
        raise Fail("; ".join(problems))
    return " ".join(seen) or "manifest has no sieve info"


def c_mig_salearn(ctx):
    want = ctx.manifest.get("sa_learn") or {}
    if not want:
        raise Skip("manifest has no sa_learn counts")
    have = sa_magic(ctx)
    if have["nspam"] < want.get("nspam", 0) or have.get("nham", 0) < want.get("nham", 0):
        raise Fail("bayes counts dropped: now %s, manifest %s (bayes db not migrated?)" % (have, want))
    return "now %s, manifest %s" % (have, want)


def nc_userid(ctx, user):
    if user in ctx.nc_ids:
        return ctx.nc_ids[user]
    r = http_req(ctx, "GET", "/cloud/ocs/v1.php/cloud/user?format=json",
                 headers={"OCS-APIRequest": "true"}, auth=(user, ctx.user_pw))
    if r.status != 200:
        raise Fail("OCS user lookup HTTP %d" % r.status)
    uid = r.json()["ocs"]["data"]["id"]
    ctx.nc_ids[user] = uid
    return uid


def c_mig_nextcloud(ctx):
    nc = ctx.manifest.get("nextcloud") or {}
    if not nc or nc.get("skipped"):
        raise Skip("manifest has no Nextcloud items")
    user = nc.get("user", ctx.alice)
    auth = (user, ctx.user_pw)
    out = []
    for key, needle in (("event", "uid"), ("contact", "uid")):
        item = nc.get(key)
        if not item:
            continue
        r = http_req(ctx, "GET", item["path"], auth=auth)
        if r.status != 200 or item[needle] not in r.text():
            raise Fail("%s %s: HTTP %d, uid found=%s" % (key, item["path"], r.status, item[needle] in r.text()))
        out.append(key + " ok")
    f = nc.get("file")
    if f:
        r = http_req(ctx, "GET", f["path"], auth=auth)
        h = hashlib.sha256(r.body).hexdigest()
        if r.status != 200 or h != f["sha256"]:
            raise Fail("file %s: HTTP %d sha256 match=%s" % (f["path"], r.status, h == f["sha256"]))
        out.append("file ok")
    return ", ".join(out)


def c_mig_dns_custom(ctx):
    rec = ctx.manifest.get("dns_custom")
    if not rec:
        raise Skip("manifest has no custom DNS record")
    res = dns_query(ctx, rec["qname"], rec["rtype"], do=False)
    vals = [v for _n, t, v in res["answers"] if t == rec["rtype"]]
    if rec["value"] not in vals:
        raise Fail("%s %s: DNS answers %s, want %r" % (rec["qname"], rec["rtype"], vals, rec["value"]))
    if ctx.admin_auth:
        r = admin_api(ctx, "GET", "dns/custom")
        if not any(x["qname"] == rec["qname"] and x["value"] == rec["value"] for x in r.json()):
            raise Fail("record served by DNS but missing in /admin/dns/custom")
    return "%s TXT present" % rec["qname"]


def c_mig_dkim(ctx):
    d = ctx.manifest.get("dkim") or {}
    if not d.get("p"):
        raise Skip("manifest has no DKIM key")
    res = dns_query(ctx, "%s._domainkey.%s" % (d.get("selector", "mail"), ctx.domain), "TXT", do=False)
    txt = " ".join(v for _n, t, v in res["answers"] if t == "TXT").replace(" ", "")
    if d["p"].replace(" ", "") not in txt:
        raise Fail("DKIM public key changed (DKIM key not migrated): %s..." % txt[:60])
    return "DKIM key unchanged"


def roundcube_login(ctx, user):
    """Returns cookie jar dict after a successful login, raises Fail otherwise."""
    jar = {}

    def eat(resp):
        for v in resp.header("Set-Cookie"):
            k, _, rest = v.partition("=")
            jar[k.strip()] = rest.split(";", 1)[0]

    def cookie():
        return "; ".join("%s=%s" % kv for kv in jar.items() if kv[1] not in ("", "deleted"))

    r = http_req(ctx, "GET", "/mail/")
    eat(r)
    if r.status != 200:
        raise Fail("GET /mail/ HTTP %d" % r.status)
    m = re.search(r'name="_token" value="([^"]+)"', r.text())
    if not m:
        raise Fail("no login token on /mail/")
    r = http_req(ctx, "POST", "/mail/?_task=login", headers={"Cookie": cookie()}, form={
        "_token": m.group(1), "_task": "login", "_action": "login", "_timezone": "Europe/Berlin",
        "_url": "", "_user": user, "_pass": ctx.user_pw})
    eat(r)
    loc = (r.header("Location") or [""])[0]
    if r.status not in (301, 302) or "_task=login" in loc:
        raise Fail("login POST HTTP %d Location=%s" % (r.status, loc))
    return jar, cookie


def c_mig_roundcube_identity(ctx):
    rc = ctx.manifest.get("roundcube") or {}
    ident = rc.get("identity")
    if not ident:
        raise Skip("manifest: %s" % rc.get("skipped", "no roundcube identity"))
    if ctx.remote.available():
        q = ("SELECT count(*) FROM identities i JOIN users u ON u.user_id=i.user_id "
             "WHERE u.username='%s' AND i.name='%s' AND i.del=0 AND i.signature LIKE '%%%s%%';"
             % (ident["username"], ident["name"], ident["signature_marker"]))
        # as www-data: a root-owned -wal/-shm file would lock Roundcube out of its WAL database
        rc_, out, err = ctx.remote.run("sudo -n -u www-data sqlite3 -readonly %s %s"
                                       % (shlex.quote(ident["db"]), shlex.quote(q)))
        if rc_ == 0 and out.strip().isdigit():
            if int(out.strip()) >= 1:
                return "identity '%s' with signature present (sqlite)" % ident["name"]
            raise Fail("identity '%s' missing in %s" % (ident["name"], ident["db"]))
    _jar, cookie = roundcube_login(ctx, ident["username"])
    r = http_req(ctx, "GET", "/mail/?_task=settings&_action=identities", headers={"Cookie": cookie()})
    if ident["name"] in r.text():
        return "identity '%s' listed (web)" % ident["name"]
    raise Fail("identity '%s' not listed in Roundcube settings" % ident["name"])


# ---------------------------------------------------------------------------
# checks: admin API, backup
# ---------------------------------------------------------------------------

def c_admin_login(ctx):
    if not ctx.admin_user or not ctx.admin_pw:
        raise Skip("admin credentials not given")
    r = http_req(ctx, "POST", "/admin/login", auth=(ctx.admin_user, ctx.admin_pw))
    j = r.json() if r.status == 200 else {}
    if j.get("status") == "missing-totp-token":
        raise Skip("admin has TOTP enabled")
    if j.get("status") != "ok":
        raise Fail("login HTTP %d %s" % (r.status, j.get("reason", r.text()[:100])))
    SECRETS.add(j["api_key"])
    ctx.admin_auth = (ctx.admin_user, j["api_key"])
    return "session for %s, privileges %s" % (j["email"], j.get("privileges"))


def c_admin_tmp_user_alias(ctx):
    tmp = "smoketmp-%s@%s" % (ctx.tok, ctx.domain)
    tmpa = "smokealias-%s@%s" % (ctx.tok, ctx.domain)
    r = admin_api(ctx, "POST", "mail/users/add", form={"email": tmp, "password": ctx.user_pw})
    if r.status != 200:
        raise Fail("users/add HTTP %d %s" % (r.status, r.text()[:200]))
    try:
        r = admin_api(ctx, "POST", "mail/aliases/add", form={"address": tmpa, "forwards_to": tmp, "permitted_senders": ""})
        if r.status != 200:
            raise Fail("aliases/add HTTP %d %s" % (r.status, r.text()[:200]))
        r = admin_api(ctx, "GET", "mail/aliases?format=json")
        if not any(a["address"] == tmpa for d in r.json() for a in d["aliases"]):
            raise Fail("new alias not listed")
        r = admin_api(ctx, "POST", "mail/aliases/remove", form={"address": tmpa})
        if r.status != 200:
            raise Fail("aliases/remove HTTP %d" % r.status)
    finally:
        r = admin_api(ctx, "POST", "mail/users/remove", form={"email": tmp})
    if r.status != 200:
        raise Fail("users/remove HTTP %d %s" % (r.status, r.text()[:200]))
    return "add/list/remove of user and alias ok, %s" % remove_test_mailbox(ctx, tmp)


def c_backup_status(ctx):
    r = admin_api(ctx, "GET", "system/backup/status")
    if r.status != 200:
        raise Fail("HTTP %d" % r.status)
    j = r.json()
    if "error" in j:
        raise Fail("backup status error: %s" % j["error"][:200])
    b = j.get("backups") or []
    cfg = admin_api(ctx, "GET", "system/backup/config").json()
    last = b[0].get("date_str", b[0].get("date")) if b else None
    return "target=%s, %d backups, latest %s" % (cfg.get("target"), len(b), last)


def c_backup_saved(ctx):
    # The saved status (B125): a refresh in the background, polled until it
    # ends; the control panel answers meanwhile; the new status is saved.
    r = admin_api(ctx, "GET", "system/backup/status/saved")
    api_expect(r, 200, "application/json", "saved status")
    j = r.json()
    if j.get("status") == {}:
        return "backups are turned off"
    t0 = j.get("now") or 0
    r = admin_api(ctx, "POST", "system/backup/status/refresh")
    api_expect(r, 200, "application/json", "refresh")
    started = r.json().get("started")
    slowest, polls, deadline = 0.0, 0, time.time() + 900
    while True:
        a = time.time()
        api_expect(admin_api(ctx, "GET", "system/version"), 200, "text/html", "version during the refresh")
        r = admin_api(ctx, "GET", "system/backup/status/saved")
        slowest = max(slowest, time.time() - a)
        api_expect(r, 200, "application/json", "saved status")
        j = r.json()
        polls += 1
        if not j.get("refreshing"):
            break
        if time.time() > deadline:
            raise Fail("the refresh did not end within 900 s")
        time.sleep(2)
    ref = j.get("refresh") or {}
    if not ref.get("ok"):
        raise Fail("refresh failed: %s" % str(ref.get("error"))[:200])
    if not isinstance(j.get("status"), dict) or not isinstance(j["status"].get("backups"), list):
        raise Fail("no saved status after the refresh")
    if (j.get("time") or 0) < t0 - 1:
        raise Fail("the saved status is older than the refresh (%s)" % j.get("time_str"))
    return "refresh %s in %s s (%s), %d backups as of %s, slowest panel answer meanwhile %.1f s over %d polls" % (
        "started" if started else "already running", ref.get("seconds"), ref.get("by"), len(j["status"]["backups"]),
        j.get("time_str"), slowest, polls)


def c_fail2ban_api(ctx):
    # Read-only: status of the adaptive fail2ban (intrusion protection).
    r = admin_api(ctx, "GET", "system/fail2ban")
    if r.status != 200:
        raise Fail("HTTP %d %s" % (r.status, r.text()[:200]))
    j = r.json()
    if not j.get("running"):
        raise Fail("fail2ban not running: %s" % j.get("error"))
    names = {x["name"] for x in j["jails"]}
    s = j["settings"]
    want = {"dovecot", "miab-postfix587", "recidive"}
    if s.get("slow_jails"):
        want |= {"miab-slow-smtp", "miab-slow-dovecot"}
    if want - names:
        raise Fail("jails missing: %s" % sorted(want - names))
    if not j.get("config_current"):
        raise Fail("rendered jail file does not match the settings")
    if "client" not in j:
        raise Fail("no client address in the status (needed for the panel's allowlist hint)")
    return "%d jails, %d bans; adaptive=%s slow_jails=%s allowlist=%d" % (
        len(names), j.get("banned_entries", 0), s.get("adaptive"), s.get("slow_jails"), len(s.get("allowlist") or []))


def c_fail2ban_settings_roundtrip(ctx):
    # Changes only spray_min_ips (not part of the jail files, so no reload),
    # then restores it; an invalid allowlist must be refused without a change.
    cur = admin_api(ctx, "GET", "system/fail2ban/settings").json()["settings"]
    orig = cur["spray_min_ips"]
    new = orig + 1 if orig < 100000 else orig - 1
    try:
        r = admin_api(ctx, "POST", "system/fail2ban/settings", form={"spray_min_ips": str(new)})
        if r.status != 200 or r.json()["settings"]["spray_min_ips"] != new:
            raise Fail("set: HTTP %d %s" % (r.status, r.text()[:200]))
        if r.json().get("changed"):
            raise Fail("spray_min_ips changed the jail files")
        r = admin_api(ctx, "POST", "system/fail2ban/settings", form={"allowlist": "0.0.0.0/0"})
        if r.status != 400:
            raise Fail("allowlist 0.0.0.0/0 accepted: HTTP %d" % r.status)
        after = admin_api(ctx, "GET", "system/fail2ban/settings").json()["settings"]
        if after["allowlist"] != cur["allowlist"]:
            raise Fail("refused allowlist changed the settings")
    finally:
        admin_api(ctx, "POST", "system/fail2ban/settings", form={"spray_min_ips": str(orig)})
    if admin_api(ctx, "GET", "system/fail2ban/settings").json()["settings"]["spray_min_ips"] != orig:
        raise Fail("spray_min_ips not restored")
    return "set/restore ok, invalid allowlist refused (400)"


# Log lines for the installed fail2ban filters: (filter, line, expected host or
# None for no match). Client-chosen user names must neither move the host to a
# third-party address nor hide a real failure. Only fail2ban-regex runs: no
# login, no ban.
F2B_FILTER_CASES = [
    ("miab-postfix-submission",
     "2026-10-24T10:00:00.123456+02:00 box postfix/submission/smtpd[1234]: warning: unknown[203.0.113.5]: "
     "SASL LOGIN authentication failed: (reason unavailable), sasl_username=x[198.51.100.7]: x authentication failed",
     "203.0.113.5"),
    ("miab-postfix-submission",
     "2026-10-24T10:00:00.123456+02:00 box postfix/submission/smtpd[1234]: warning: mail.example.com[2001:db8::5]: "
     "SASL PLAIN authentication failed: (reason unavailable), sasl_username=bob@example.com",
     "2001:db8::5"),
    ("miab-dovecot-authfail",
     "2026-10-24T10:00:00.123456+02:00 box dovecot: imap-login: Info: Login aborted: Connection closed "
     "(auth failed, 3 attempts in 9 secs) (auth_failed): user=<admin@example.com (no auth attempts)>, method=PLAIN, "
     "rip=203.0.113.5, lip=192.0.2.11, TLS, session=<abc>",
     "203.0.113.5"),
    ("miab-dovecot-authfail",
     "2026-10-24T10:00:00.123456+02:00 box dovecot: imap-login: Info: Login aborted: Connection closed "
     "(no auth attempts in 0 secs) (no_auth_attempts): rip=203.0.113.9, lip=192.0.2.11, TLS, session=<abc>",
     None),
    ("dovecotimap",
     "2026-10-24T10:00:00.123456+02:00 box dovecot: imap-login: Info: Login aborted: Connection closed "
     "(no auth attempts in 0 secs) (no_auth_attempts): rip=203.0.113.9, lip=192.0.2.11, TLS, session=<abc>",
     "203.0.113.9"),
    # Through syslog (log_path=syslog, B85) Dovecot's lines have no "Info: ".
    ("dovecotimap",
     "2026-10-24T10:00:00.123456+02:00 box dovecot: pop3-login: Login aborted: Logged out "
     "(auth failed, 1 attempts in 2 secs) (auth_failed): user=<bob@example.com>, method=PLAIN, rip=203.0.113.6, "
     "lip=192.0.2.11, TLS, session=<abc>",
     "203.0.113.6"),
    ("miab-management-daemon",
     "2026-10-24T10:00:00.123456+02:00 box start[1234]: [2026-10-24 10:00:00,123] WARNING in daemon: "
     "Mail-in-a-Box Management Daemon: Failed login attempt from ip 203.0.113.5 - timestamp 1792844266.505317",
     "203.0.113.5"),
    ("miab-management-daemon",
     "2026-10-24T10:00:00.123456+02:00 box Mail-in-a-Box Management Daemon: Failed login attempt from ip 2001:db8::5 "
     "- timestamp 1792844266.505317",
     "2001:db8::5"),
    ("miab-management-daemon",
     "2026-10-24T10:00:00.123456+02:00 box postfix/submission/smtpd[1234]: warning: unknown[203.0.113.5]: "
     "SASL PLAIN authentication failed: (reason unavailable), sasl_username=Mail-in-a-Box Management Daemon: "
     "Failed login attempt from ip 198.51.100.7 - timestamp 1",
     None),
    ("miab-roundcube",
     "[24-Oct-2026 10:00:00 +0000]: <779ea5f1> IMAP Error: Login failed for bob@example.com against localhost "
     "from 203.0.113.5. AUTHENTICATE PLAIN: Authentication failed. in /usr/local/lib/roundcubemail/program/lib/"
     "Roundcube/rcube_imap.php on line 197 (POST /mail/?_task=login&_action=login)",
     "203.0.113.5"),
    ("miab-roundcube",
     "[24-Oct-2026 10:00:00 +0000]: <779ea5f1> IMAP Error: Login failed for \"x against localhost from 198.51.100.7. "
     "AUTHENTICATE PLAIN: x\"@example.com against localhost from 203.0.113.5. AUTHENTICATE PLAIN: Authentication "
     "failed. in /usr/local/lib/roundcubemail/program/lib/Roundcube/rcube_imap.php on line 197 "
     "(POST /mail/?_task=login&_action=login)",
     "203.0.113.5"),
]


def c_fail2ban_filters(ctx):
    if not ctx.remote.available():
        raise Skip("needs --ssh")
    for filt, line, want in F2B_FILTER_CASES:
        rc, out, err = ctx.remote.run("fail2ban-regex -o '<ip>' %s %s" % (shlex.quote(line), shlex.quote(filt)),
                                      sudo=True, timeout=60)
        if rc != 0:
            raise Fail("fail2ban-regex %s: exit %d %s" % (filt, rc, err.strip()[:200]))
        got = [x.strip() for x in out.splitlines() if x.strip()]
        if got != ([want] if want else []):
            raise Fail("%s: expected %s, got %s for: %s" % (filt, want or "no match", got or "no match", line[:120]))
    return "%d filter cases ok (no third-party host from user names)" % len(F2B_FILTER_CASES)


def c_fail2ban_panel(ctx):
    # The control panel page (System > Intrusion Protection) is part of index.html.
    r = http_req(ctx, "GET", "/admin/")
    if r.status != 200:
        raise Fail("HTTP %d" % r.status)
    page = r.text()
    missing = [m for m in ('id="panel_fail2ban"', 'href="#fail2ban"', "function show_fail2ban(") if m not in page]
    if missing:
        raise Fail("control panel lacks %s" % missing)
    return "Intrusion Protection page present"


def c_fail2ban_report(ctx):
    r = admin_api(ctx, "GET", "system/fail2ban/report")
    if r.status != 200:
        raise Fail("HTTP %d %s" % (r.status, r.text()[:200]))
    j = r.json()
    return "%d failed logins from %d IPs in %d h, %d flagged accounts, %d persistent IPs (%.1f s)" % (
        j["failures"], j["distinct_ips"], j["scan_hours"], len(j["flagged_accounts"]), j["persistent_total"], j["seconds"])


# ---------------------------------------------------------------------------
# checks: DNS
# ---------------------------------------------------------------------------

def c_dnssec(ctx, zone):
    res = dns_query(ctx, zone, "SOA", do=True)
    types = [t for _n, t, _v in res["answers"]]
    if res["rcode"] != 0 or "SOA" not in types:
        raise Fail("rcode=%d answers=%s" % (res["rcode"], types))
    sigs = [v for _n, t, v in res["answers"] if t == "RRSIG"]
    if "SOA" not in sigs:
        raise Fail("SOA not signed (no RRSIG); zone unsigned on this box")
    keys = dns_query(ctx, zone, "DNSKEY", do=True)
    if not any(t == "DNSKEY" for _n, t, _v in keys["answers"]):
        raise Fail("no DNSKEY")
    return "SOA+RRSIG, DNSKEY present (aa=%s)" % res["aa"]


def c_mx_dkim(ctx, domain):
    mx = [v for _n, t, v in dns_query(ctx, domain, "MX", do=False)["answers"] if t == "MX"]
    txt = [v for _n, t, v in dns_query(ctx, "mail._domainkey." + domain, "TXT", do=False)["answers"] if t == "TXT"]
    if not mx:
        raise Fail("no MX")
    if not any(v.replace(" ", "").startswith("v=DKIM1") and "p=" in v for v in txt):
        raise Fail("no DKIM TXT at mail._domainkey (have %s)" % txt)
    return "MX %s, DKIM TXT ok" % ",".join(mx)


def c_sshfp(ctx):
    res = dns_query(ctx, ctx.hostname, "SSHFP", do=False)
    dns = {v for _n, t, v in res["answers"] if t == "SSHFP"}
    if not dns:
        raise Fail("no SSHFP records for %s" % ctx.hostname)
    algs = sorted({a for a, _f, _p in dns})
    bad = [a for a in algs if a not in (1, 3, 4)]
    if bad:
        raise Fail("unexpected SSHFP algorithm numbers %s (IANA: 1=RSA 3=ECDSA 4=Ed25519)" % bad)
    if not ctx.remote.available():
        return ("PASS", "algorithms %s; key comparison skipped (needs --ssh)" % algs)
    rc, out, err = ctx.remote.run("ssh-keygen -r %s" % shlex.quote(ctx.hostname))
    box = set()
    for line in out.splitlines():
        p = line.split()
        if len(p) >= 6 and p[2] == "SSHFP" and p[4] == "2" and int(p[3]) in (1, 3, 4):
            box.add((int(p[3]), 2, p[5].lower()))
    if not box:
        raise Fail("ssh-keygen -r gave nothing: %s" % err.strip()[:200])
    if box != dns:
        raise Fail("DNS %s != host keys %s" % (sorted(dns), sorted(box)))
    return "%d records match host keys, algorithms %s" % (len(dns), algs)


def c_dns_custom_roundtrip(ctx):
    qname = "smoke-%s.%s" % (ctx.tok, ctx.domain)
    value = "smoke-%s" % ctx.tok
    r = admin_api(ctx, "PUT", "dns/custom/%s/TXT" % qname, body=value, headers={"Content-Type": "text/plain"})
    if r.status != 200:
        raise Fail("PUT HTTP %d %s" % (r.status, r.text()[:200]))
    try:
        deadline = time.time() + 60
        while True:
            vals = [v for _n, t, v in dns_query(ctx, qname, "TXT", do=False)["answers"] if t == "TXT"]
            if value in vals:
                break
            if time.time() > deadline:
                raise Fail("TXT not served by nsd after 60 s")
            time.sleep(3)
    finally:
        admin_api(ctx, "DELETE", "dns/custom/%s/TXT" % qname)
    return "custom TXT set, served, removed"


# ---------------------------------------------------------------------------
# checks: web (Nextcloud, Roundcube, Z-Push)
# ---------------------------------------------------------------------------

def c_nc_status(ctx):
    r = http_req(ctx, "GET", "/cloud/status.php")
    if r.status != 200:
        raise Fail("HTTP %d" % r.status)
    j = r.json()
    v = j.get("versionstring", "")
    bad = []
    if not j.get("installed"):
        bad.append("not installed")
    if j.get("maintenance"):
        bad.append("maintenance mode")
    if j.get("needsDbUpgrade"):
        bad.append("needsDbUpgrade")
    if not v.startswith(ctx.args.expect_nc + "."):
        bad.append("version %s, expected %s.x" % (v, ctx.args.expect_nc))
    if bad:
        raise Fail(", ".join(bad))
    return "Nextcloud %s" % v


def c_nc_dav(ctx, kind):
    uid = nc_userid(ctx, ctx.alice)
    path = {"caldav": "/cloud/remote.php/dav/calendars/%s/",
            "carddav": "/cloud/remote.php/dav/addressbooks/users/%s/",
            "webdav": "/cloud/remote.php/dav/files/%s/"}[kind] % urllib.parse.quote(uid)
    body = '<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/><d:displayname/></d:prop></d:propfind>'
    r = http_req(ctx, "PROPFIND", path, auth=(ctx.alice, ctx.user_pw), body=body,
                 headers={"Depth": "1", "Content-Type": "application/xml"})
    if r.status != 207:
        raise Fail("PROPFIND %s HTTP %d" % (path, r.status))
    n = r.text().count("<d:response>")
    return "207, %d entries (user id %s)" % (n, uid)


def nc_user_info(ctx, user, pw):
    r = http_req(ctx, "GET", "/cloud/ocs/v1.php/cloud/user?format=json",
                 headers={"OCS-APIRequest": "true"}, auth=(user, pw))
    if r.status != 200:
        raise Fail("OCS user lookup for %s: HTTP %d" % (user, r.status))
    return r.json()["ocs"]["data"]


def nc_sharees(ctx, user, pw, search):
    """User ids and group ids the share dialog offers to user for search."""
    q = urllib.parse.urlencode([("search", search), ("itemType", "file"), ("perPage", "50"),
                                ("format", "json"), ("shareType[]", "0"), ("shareType[]", "1")])
    r = http_req(ctx, "GET", "/cloud/ocs/v2.php/apps/files_sharing/api/v1/sharees?" + q,
                 headers={"OCS-APIRequest": "true"}, auth=(user, pw))
    if r.status != 200:
        raise Fail("sharee search as %s: HTTP %d" % (user, r.status))
    d = r.json()["ocs"]["data"]
    exact = d.get("exact") or {}
    users = {e["value"]["shareWith"] for e in (d.get("users") or []) + (exact.get("users") or [])}
    groups = {e["value"]["shareWith"] for e in (d.get("groups") or []) + (exact.get("groups") or [])}
    return users, groups


def nc_share_scope_sync(ctx):
    """With --ssh: run the cron job of tools/nextcloud-share-scope.sh (admins into
    the domain groups that first logins just created) and fill the system
    address book. Returns False without --ssh or without that cron job."""
    if not ctx.remote.available():
        return False
    rc, out, _ = ctx.remote.run("grep -o '(cd .*nextcloud-share-scope.sh --cron)' /etc/cron.d/mailinabox-nextcloud")
    line = out.strip().splitlines()[0] if rc == 0 and out.strip() else ""
    if not line:
        return False
    m = re.search(r"PHP_VER=(\S+)", line)
    for cmd, sudo in (("bash -c " + shlex.quote(line), True),
                      ("sudo -n -u www-data php%s /usr/local/lib/owncloud/occ dav:sync-system-addressbook"
                       % (m.group(1) if m else ""), False)):
        # Nextcloud on SQLite: its own cron.php (every 5 minutes) can hold the
        # database for a while, and occ then fails with "database is locked".
        for attempt in range(3):
            rc, out, err = ctx.remote.run(cmd, sudo=sudo, timeout=300)
            if rc == 0:
                break
            if "database is locked" not in out + err or attempt == 2:
                raise Fail("remote command failed (%d): %s %s" % (rc, cmd, (err or out).strip()[-300:]))
            time.sleep(15)
    return True


def c_nc_share_scope(ctx):
    """NEXTCLOUD_SHARE_SCOPE: alice (domain A) finds carol (A), not bob (domain B); a Nextcloud admin finds both."""
    scope = "domain"
    if ctx.remote.available():
        rc, out, _ = ctx.remote.run("sed -n 's/^NEXTCLOUD_SHARE_SCOPE=//p' /etc/mailinabox.conf")
        if rc == 0 and out.strip():
            scope = out.strip()
    # Log every account in once, so that Nextcloud knows it (the first login
    # creates the user and, with groupDomain, its domain group membership).
    alice, bob, carol = (nc_userid(ctx, u) for u in (ctx.alice, ctx.bob, ctx.carol))
    pw = ctx.user_pw
    out = ["scope " + scope]
    synced = scope == "domain" and nc_share_scope_sync(ctx)
    if scope == "domain":
        groups = nc_user_info(ctx, ctx.alice, pw).get("groups") or []
        if ctx.domain.lower() not in groups:
            raise Fail("alice is not in the group %s (groups: %s)" % (ctx.domain.lower(), ", ".join(groups) or "none"))
    found, _ = nc_sharees(ctx, ctx.alice, pw, "carol")
    if carol not in found:
        raise Fail("alice does not find carol (same domain)")
    found_b, groups_b = set(), set()
    for term in ("bob", ctx.bob):
        u, g = nc_sharees(ctx, ctx.alice, pw, term)
        found_b |= u
        groups_b |= g
    if scope == "domain":
        if bob in found_b:
            raise Fail("alice finds bob of %s in the share dialog" % ctx.seed2)
        u, g = nc_sharees(ctx, ctx.alice, pw, ctx.seed2)
        if bob in u or ctx.seed2 in g:
            raise Fail("alice finds the domain %s (users %s, groups %s)" % (ctx.seed2, sorted(u), sorted(g)))
        # The system address book over CardDAV must not list bob either.
        path = "/cloud/remote.php/dav/addressbooks/users/%s/z-server-generated--system/" % urllib.parse.quote(alice)
        body = '<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:getetag/></d:prop></d:propfind>'
        r = http_req(ctx, "PROPFIND", path, auth=(ctx.alice, pw), body=body,
                     headers={"Depth": "1", "Content-Type": "application/xml"})
        if r.status == 207:
            hrefs = urllib.parse.unquote(r.text())
            if ":" + bob + ".vcf" in hrefs:
                raise Fail("the system address book of alice lists bob")
            # Positive control: without carol's card the check above proves nothing.
            # Cards of user_external accounts appear only after a sync (--ssh).
            if ":" + carol + ".vcf" in hrefs:
                out.append("system address book %d cards, carol but not bob" % r.text().count(".vcf<"))
            elif synced:
                raise Fail("the system address book of alice does not list carol (same domain)")
            else:
                out.append("system address book not checked (no card of carol yet, needs --ssh)")
        elif r.status == 404:
            out.append("system address book not checked (not exposed, HTTP 404)")
        else:
            raise Fail("PROPFIND %s HTTP %d" % (path, r.status))
        out.append("alice finds carol, not bob")
    else:
        if bob not in found_b:
            raise Fail("scope all: alice does not find bob of %s" % ctx.seed2)
        out.append("alice finds carol and bob")
    # A member of the Nextcloud group admin sees every domain.
    if not ctx.admin_user or not ctx.admin_pw:
        out.append("admin part skipped (no admin credentials)")
        return "; ".join(out)
    info = nc_user_info(ctx, ctx.admin_user, ctx.admin_pw)
    if "admin" not in (info.get("groups") or []):
        out.append("admin part skipped (%s is not in the Nextcloud group admin, see tools/owncloud-unlockadmin.sh)"
                   % ctx.admin_user)
        return "; ".join(out)
    if scope == "domain":
        # Admins are put into the domain groups by the cron job; a group that a
        # first login above created only has them after its next run (--ssh runs it).
        lacking = [d for d in (ctx.domain.lower(), ctx.seed2.lower()) if d not in (info.get("groups") or [])]
        if lacking and synced:
            raise Fail("the Nextcloud admin %s is not in the group(s) %s after the cron job"
                       % (ctx.admin_user, ", ".join(lacking)))
        if lacking:
            out.append("admin part skipped (%s not yet in the group(s) %s, cron job pending; --ssh runs it)"
                       % (ctx.admin_user, ", ".join(lacking)))
            return "; ".join(out)
    missing = [who for who, uid, term in (("bob", bob, ctx.bob), ("carol", carol, ctx.carol))
               if uid not in nc_sharees(ctx, ctx.admin_user, ctx.admin_pw, term)[0]]
    if missing:
        raise Fail("the Nextcloud admin %s does not find %s" % (ctx.admin_user, ", ".join(missing)))
    out.append("admin finds bob and carol")
    return "; ".join(out)


def c_roundcube(ctx):
    r = http_req(ctx, "GET", "/mail/")
    if r.status != 200 or 'name="_user"' not in r.text():
        raise Fail("login page HTTP %d" % r.status)
    _jar, cookie = roundcube_login(ctx, ctx.alice)
    r = http_req(ctx, "GET", "/mail/?_task=mail&_mbox=INBOX", headers={"Cookie": cookie()})
    if r.status != 200 or 'name="_pass"' in r.text():
        raise Fail("after login: HTTP %d, still login form=%s" % (r.status, 'name="_pass"' in r.text()))
    return "login page 200, login + mailbox view ok"


def c_zpush_options(ctx):
    r = http_req(ctx, "OPTIONS", "/Microsoft-Server-ActiveSync", auth=(ctx.alice, ctx.user_pw))
    v = r.header("MS-ASProtocolVersions")
    if r.status != 200 or not v:
        raise Fail("HTTP %d, MS-ASProtocolVersions=%s, body=%s" % (r.status, v, r.text()[:150]))
    return "versions %s; commands %s" % (v[0], (r.header("MS-ASProtocolCommands") or ["?"])[0][:60])


def c_nc_bruteforce_loopback(ctx):
    # A check of Nextcloud's brute-force bypass list (B121): setup/nextcloud.sh
    # puts 127.0.0.1 (the box's own services, Z-Push above all) on it, once.
    # Nextcloud reports no attempts for a listed address at all, so this only
    # proves the address is listed (and was not added twice by repeated
    # setup runs). ::1 is shown, not required: no service of the box uses it.
    occ = "cd / && sudo -n -u www-data php /usr/local/lib/owncloud/occ "
    out = []
    bad = []
    for ip in ("127.0.0.1", "::1"):
        rc, so, se = ctx.remote.run(occ + "security:bruteforce:attempts %s --output=json" % ip, timeout=120)
        if rc != 0:
            raise Fail("occ security:bruteforce:attempts %s: exit %d %s" % (ip, rc, se.strip()[:200]))
        try:
            j = json.loads(so.strip().splitlines()[-1])
        except (ValueError, IndexError):
            raise Fail("unexpected output for %s: %s" % (ip, so.strip()[:200]))
        out.append("%s bypass-listed=%s" % (ip, j.get("bypass-listed")))
        if ip == "127.0.0.1" and j.get("bypass-listed") is not True:
            bad.append(out[-1])
    rc, so, se = ctx.remote.run(occ + "config:list bruteForce", timeout=120)
    if rc != 0:
        raise Fail("occ config:list bruteForce: exit %d %s" % (rc, se.strip()[:200]))
    try:
        keys = json.loads(so).get("apps", {}).get("bruteForce") or {}
    except ValueError:
        raise Fail("unexpected output of occ config:list bruteForce: %s" % so.strip()[:200])
    entries = [str(v).strip() for k, v in sorted(keys.items()) if k.startswith("whitelist_")]
    dup = [e for e in set(entries) if entries.count(e) > 1]
    out.append("%d bypass entries" % len(entries))
    if dup:
        bad.append("listed more than once: %s" % ", ".join(sorted(dup)))
    if bad:
        raise Fail("; ".join(bad))
    return "; ".join(out)


XFF_USER = "xfftest-nouser@invalid.example"


def c_nc_forwarded_for(ctx):
    # The proxy of /caldav, /carddav and /webdav connects to Nextcloud from
    # 127.0.0.1, which is on the brute-force bypass list (B121): it must pass
    # the client's address (X-Forwarded-For, trusted from 127.0.0.1 only), or
    # every client on the Internet would skip the throttle there. One failed
    # login of a user that does not exist, from the box's public address
    # (fail2ban ignores it), to /webdav/: Nextcloud must log it and count it
    # for that address, not for 127.0.0.1. Its attempts are reset afterwards.
    occ = "sudo -n -u www-data php /usr/local/lib/owncloud/occ"
    script = r"""
set -u
. /etc/mailinabox.conf
cd /
log="$STORAGE_ROOT/owncloud/nextcloud.log"
before=$(sudo -n stat -c %%s "$log" 2> /dev/null || echo 0)
code=$(curl -sk -o /dev/null -w '%%{http_code}' --max-time 60 --resolve "$PRIMARY_HOSTNAME:443:$PUBLIC_IP" \
    -u '%(user)s:not-the-password' -X PROPFIND -H 'Depth: 0' "https://$PRIMARY_HOSTNAME/webdav/")
echo "http=$code"
echo "public=$PUBLIC_IP"
for i in 1 2 3 4 5 6 7 8 9 10; do
    line=$(sudo -n tail -c +$((before + 1)) "$log" | grep -F "Login failed: '%(user)s'" | tail -1)
    [ -n "$line" ] && break
    sleep 1
done
echo "log=$line"
echo "pub=$(%(occ)s security:bruteforce:attempts "$PUBLIC_IP" --output=json 2>&1 | tail -1)"
%(occ)s security:bruteforce:reset "$PUBLIC_IP" > /dev/null 2>&1
echo "reset=$?"
""" % {"user": XFF_USER, "occ": occ}
    rc, so, se = ctx.remote.run("bash -c %s" % shlex.quote(script), timeout=300)
    vals = dict(l.split("=", 1) for l in so.splitlines() if "=" in l)
    public = vals.get("public", "")
    if vals.get("http") != "401":
        raise Fail("PROPFIND /webdav/ with a wrong login: HTTP %s (expected 401)" % vals.get("http"))
    try:
        remote = json.loads(vals.get("log", "")).get("remoteAddr")
    except ValueError:
        raise Fail("no 'Login failed' line for the test login in nextcloud.log")
    try:
        pub = json.loads(vals.get("pub", ""))
        attempts, listed = pub.get("attempts"), pub.get("bypass-listed")
    except (ValueError, AttributeError):
        raise Fail("occ security:bruteforce:attempts %s: %s" % (public, vals.get("pub", "")[:200]))
    if vals.get("reset") != "0":
        raise Fail("occ security:bruteforce:reset %s failed" % public)
    if remote != public:
        raise Fail("Nextcloud saw the login from %s, not from the client %s (X-Forwarded-For through the "
                   "/webdav proxy, trusted_proxies)" % (remote, public))
    if listed is True:
        # An entry of the bypass list covers the box's own address (e.g. an
        # administrator's private range): Nextcloud counts nothing for it.
        return "remoteAddr %s (the address is on the bypass list, attempts not counted)" % remote
    if not attempts:
        raise Fail("Nextcloud counted no attempt for %s" % public)
    return "remoteAddr %s, attempts %s (reset)" % (remote, attempts)


def _load_eas():
    # tests/fork/eas.py, next to this script (also when run with python3 -I)
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import eas
    return eas


def c_zpush_sync(ctx):
    # An ActiveSync account as a phone sets it up: Provision, FolderSync, and
    # a Sync of the calendars and the address books, which Z-Push reads from
    # Nextcloud over CalDAV/CardDAV from 127.0.0.1 (B99, B120). A marked event
    # and contact, put into Nextcloud over DAV first, must arrive.
    eas = _load_eas()
    uid = urllib.parse.quote(nc_userid(ctx, ctx.alice))
    auth = (ctx.alice, ctx.user_pw)
    mark = "miab-smoke-%s" % ctx.tok
    cal_home = "/cloud/remote.php/dav/calendars/%s/" % uid
    r = http_req(ctx, "PROPFIND", cal_home, auth=auth, headers={"Depth": "1", "Content-Type": "application/xml"},
                 body='<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/></d:prop></d:propfind>')
    if r.status != 207:
        raise Fail("PROPFIND %s HTTP %d" % (cal_home, r.status))
    event = cal_home + "personal/%s.ics" % mark
    card = "/cloud/remote.php/dav/addressbooks/users/%s/contacts/%s.vcf" % (uid, mark)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    start = time.strftime("%Y%m%dT%H0000Z", time.gmtime(time.time() + 86400))
    end = time.strftime("%Y%m%dT%H3000Z", time.gmtime(time.time() + 86400))
    ics = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//miab-fork-smoke//EN\r\nBEGIN:VEVENT\r\nUID:%s\r\n"
           "DTSTAMP:%s\r\nDTSTART:%s\r\nDTEND:%s\r\nSUMMARY:%s event\r\nDESCRIPTION:X-Miab-Test 1\r\n"
           "END:VEVENT\r\nEND:VCALENDAR\r\n" % (mark, stamp, start, end, mark))
    vcf = ("BEGIN:VCARD\r\nVERSION:3.0\r\nUID:%s\r\nFN:%s contact\r\nN:%s;Smoke;;;\r\n"
           "NOTE:X-Miab-Test 1\r\nEND:VCARD\r\n" % (mark, mark, mark))
    created = []
    try:
        for path, body, ctype in ((event, ics, "text/calendar; charset=utf-8"),
                                  (card, vcf, "text/vcard; charset=utf-8")):
            for attempt in range(3):
                # Nextcloud on SQLite answers 500 ("database is locked")
                # while its cron job or a user's first login writes
                r = http_req(ctx, "PUT", path, auth=auth, body=body, headers={"Content-Type": ctype})
                if r.status not in (500, 503):
                    break
                time.sleep(10)
            if r.status not in (201, 204):
                raise Fail("PUT %s HTTP %d" % (path, r.status))
            created.append(path)
        devid = "miabsmoke" + ctx.tok
        c = eas.Client(ctx.hostname, ctx.alice, ctx.user_pw, devid, addr=ctx.net.addr(443),
                       user_agent="miab-fork-smoke/1")
        try:
            c.provision()
            c.folder_sync()
            cals = c.folders_of(eas.TYPE_CALENDAR, eas.TYPE_USER_CALENDAR)
            cons = c.folders_of(eas.TYPE_CONTACTS, eas.TYPE_USER_CONTACTS)
            if not cals or not cons:
                raise Fail("FolderSync: %d calendar and %d contact folders" % (len(cals), len(cons)))
            adds = c.sync([f["ServerId"] for f in cals + cons])
        except eas.EASError as e:
            raise Fail("%s (%s)" % (e, e.kind))
        finally:
            if ctx.remote.available():
                # as www-data: Z-Push's state files belong to it
                ctx.remote.run("cd / && sudo -n -u www-data php /usr/local/lib/z-push/z-push-admin.php -a remove -u %s -d %s"
                               % (shlex.quote(ctx.alice), devid), timeout=120)

        def found(folders):
            return any(mark in " ".join(eas.flat_strings(a)) for f in folders for a in adds.get(f["ServerId"], []))
        missing = [what for what, folders in (("event", cals), ("contact", cons)) if not found(folders)]
        if missing:
            raise Fail("Sync ok, but the marked %s did not arrive (adds: %s)" % (
                " and ".join(missing), {f.get("DisplayName"): len(adds.get(f["ServerId"], [])) for f in cals + cons}))
        return "Provision, FolderSync (%d calendar, %d contact folders), Sync: event and contact arrived" % (
            len(cals), len(cons))
    finally:
        for path in created:
            http_req(ctx, "DELETE", path, auth=auth)


def c_zpush_autodiscover(ctx):
    body = ('<?xml version="1.0" encoding="utf-8"?>'
            '<Autodiscover xmlns="http://schemas.microsoft.com/exchange/autodiscover/mobilesync/requestschema/2006">'
            '<Request><EMailAddress>%s</EMailAddress>'
            '<AcceptableResponseSchema>http://schemas.microsoft.com/exchange/autodiscover/mobilesync/responseschema/2006'
            '</AcceptableResponseSchema></Request></Autodiscover>' % ctx.alice)
    r = http_req(ctx, "POST", "/autodiscover/autodiscover.xml", auth=(ctx.alice, ctx.user_pw), body=body,
                 headers={"Content-Type": "text/xml"})
    t = r.text()
    if r.status != 200 or "<Autodiscover" not in t or ("MobileSync" not in t and "<Url>" not in t):
        raise Fail("HTTP %d body=%s" % (r.status, t[:200]))
    m = re.search(r"<Url>([^<]+)</Url>", t)
    return "XML ok, Url=%s" % (m.group(1) if m else "?")


# ---------------------------------------------------------------------------
# checks: mail flow
# ---------------------------------------------------------------------------

def smtp_batch(ctx, msgs):
    """Send port-25 messages, retrying greylisted (4xx) ones. Returns {id: [code, text, attempts]}."""
    final = {}
    pending = list(msgs)
    where = ctx.args.peer_ssh
    if where:
        target = (ctx.args.host, 25)
    else:
        target = ctx.net.addr(25)
    for attempt in range(ctx.args.greylist_retries + 1):
        res = run_snippet(SMTP_SNIPPET, "deliver",
                          {"host": target[0], "port": target[1], "messages": pending}, ssh_host=where)
        for m in pending:
            code, text = res[m["id"]]
            final[m["id"]] = [code, text, attempt + 1]
        deferred = [m for m in pending if 400 <= res[m["id"]][0] < 500]
        if not deferred:
            break
        if attempt < ctx.args.greylist_retries:
            log("%d message(s) deferred (%s), waiting %d s for greylisting"
                % (len(deferred), res[deferred[0]["id"]][1][:60], ctx.args.greylist_wait))
            time.sleep(ctx.args.greylist_wait)
        pending = deferred
    return final


def submit(ctx, port, login_user, mail_from, rcpt, data):
    s = ctx.net.smtp_ssl() if port == 465 else ctx.net.smtp_starttls()
    try:
        s.login(login_user, ctx.user_pw)
        s.sendmail(mail_from, [rcpt], data.encode())
        return [250, "accepted"]
    except smtplib.SMTPRecipientsRefused as e:
        code, msg = list(e.recipients.values())[0]
        return [code, msg.decode(errors="replace")]
    except smtplib.SMTPResponseException as e:
        return [e.smtp_code, e.smtp_error.decode(errors="replace") if isinstance(e.smtp_error, bytes) else str(e.smtp_error)]
    finally:
        try:
            s.quit()
        except Exception:
            pass


def wait_for(ctx, expectations, timeout):
    """expectations: list of dicts {key, user, folders:[...], criteria:(...)}; returns {key: folder or None}."""
    found = {e["key"]: None for e in expectations}
    deadline = time.time() + timeout
    while True:
        by_user = {}
        for e in expectations:
            if found[e["key"]] is None:
                by_user.setdefault(e["user"], []).append(e)
        if not by_user:
            break
        for user, exps in by_user.items():
            M = imap_login(ctx, user)
            try:
                for e in exps:
                    for folder in e["folders"]:
                        if uid_search(M, folder, *e["criteria"]):
                            found[e["key"]] = folder
                            break
            finally:
                M.logout()
        if time.time() > deadline or all(v is not None for v in found.values()):
            break
        time.sleep(5)
    return found


def c_mail_flow(ctx):
    """Sends everything at once (greylisting costs one wait) and records sub-results."""
    tok, P, s2, s3 = ctx.tok, ctx.domain, ctx.seed2, ctx.seed3
    sender = "smoke-%s@%s" % (tok, s2)
    msgs = []

    def add(mid, rcpt, subject, frm=None, extra=None, to_hdr=None):
        sid = "smk-%s-%s" % (tok, mid)
        msgs.append({"id": mid, "from": frm or sender, "rcpt": rcpt,
                     "data": mkmsg(frm or sender, to_hdr or rcpt, subject, sid, extra=extra)})
        return sid

    ids = {}
    ids["direct"] = add("direct", ctx.alice, "smoke direct %s" % tok)
    ids["alias"] = add("alias", "info@" + P, "smoke alias %s" % tok)
    ids["catchall"] = add("catchall", "nobody-%s@%s" % (tok, s2), "smoke catch-all %s" % tok)
    ids["domalias_ca"] = add("domalias_ca", "nobody-%s@%s" % (tok, s3), "smoke domain alias %s" % tok)
    ids["domalias_user"] = add("domalias_user", "bob@" + s3, "smoke domain alias user %s" % tok)
    ids["filtered"] = add("filtered", ctx.alice, "[filtered] smoke %s" % tok)
    vac_sender = "vac-%s@%s" % (tok, s2)
    ids["vacation"] = add("vacation", ctx.carol, "smoke vacation %s" % tok, frm=vac_sender)
    oq_sender = "oq-%s@%s" % (tok, s2)
    oq_sid = "smk-%s-overquota" % tok
    hdr = mkmsg(oq_sender, ctx.bob, "smoke over quota %s" % tok, oq_sid, body="")
    hdr = hdr[:-2] if hdr.endswith("\r\n\r\n") else hdr  # gen_headers ends with one CRLF
    msgs.append({"id": "overquota", "from": oq_sender, "rcpt": ctx.bob, "data": None,
                 "gen_size": int(ctx.args.overquota_mb * 1024 * 1024), "gen_headers": hdr})

    # submission (465 / 587, sender login maps)
    sub = {}
    sub["s465"] = submit(ctx, 465, ctx.alice, ctx.alice, ctx.alice,
                         mkmsg(ctx.alice, ctx.alice, "smoke 465 %s" % tok, "smk-%s-s465" % tok))
    sub["s587"] = submit(ctx, 587, ctx.alice, ctx.alice, ctx.alice,
                         mkmsg(ctx.alice, ctx.alice, "smoke 587 %s" % tok, "smk-%s-s587" % tok))
    sub["team_ok"] = submit(ctx, 587, ctx.alice, "team@" + P, ctx.alice,
                            mkmsg("team@" + P, ctx.alice, "smoke team %s" % tok, "smk-%s-team" % tok))
    sub["team_denied"] = submit(ctx, 587, ctx.bob, "team@" + P, ctx.alice,
                                mkmsg("team@" + P, ctx.alice, "smoke team denied %s" % tok, "smk-%s-teamdeny" % tok))

    smtp = smtp_batch(ctx, msgs)
    ctx.flow = {"smtp": smtp, "sub": sub, "ids": ids, "tok": tok}

    exp = []

    def expect(key, user, folders, criteria):
        exp.append({"key": key, "user": user, "folders": folders, "criteria": criteria})

    allf = ["INBOX", "Spam", "Filtered", "Archive"]
    for k, user in (("direct", ctx.alice), ("alias", ctx.alice), ("catchall", ctx.bob),
                    ("domalias_ca", ctx.bob), ("domalias_user", ctx.bob), ("filtered", ctx.alice),
                    ("vacation", ctx.carol)):
        if smtp[k][0] == 250:
            expect(k, user, allf, ("HEADER", "X-Smoke-Id", ids[k]))
    for k in ("s465", "s587", "team_ok"):
        if sub[k][0] == 250:
            expect(k, ctx.alice, allf, ("HEADER", "X-Smoke-Id", "smk-%s-%s" % (tok, {"team_ok": "team"}.get(k, k))))
    expect("vacation_reply", ctx.bob, ["INBOX", "Spam"], ("TO", '"%s"' % vac_sender))
    if smtp["overquota"][0] == 250:
        expect("overquota_delivered", ctx.bob, ["INBOX", "Spam"], ("HEADER", "X-Smoke-Id", oq_sid))
        expect("overquota_bounce", ctx.bob, ["INBOX", "Spam"], ("TO", '"%s"' % oq_sender))
    # the over-quota "delivered"/"bounce" keys are exclusive; give them the normal window
    ctx.flow["found"] = wait_for(ctx, exp, ctx.args.deliver_timeout)
    return "sent %d via port 25 (%s), 4 submissions; results recorded" % (
        len(msgs), "peer " + ctx.args.peer_ssh if ctx.args.peer_ssh else ("jump " + ctx.args.jump if ctx.args.jump else "direct"))


def _flow(ctx):
    if not getattr(ctx, "flow", None):
        raise Skip("mail flow not run")
    return ctx.flow


def c_delivery(ctx, key, want_folder, label):
    f = _flow(ctx)
    code, text, attempts = f["smtp"][key]
    if code != 250:
        raise Fail("%s rejected at SMTP: %s %s (attempt %d)" % (label, code, text[:120], attempts))
    where = f["found"].get(key)
    if where is None:
        raise Fail("%s accepted but not found in mailbox within %d s" % (label, ctx.args.deliver_timeout))
    if where != want_folder:
        raise Fail("%s landed in %s, expected %s" % (label, where, want_folder))
    return "accepted (attempt %d) and in %s" % (attempts, where)


def c_submission_delivery(ctx, key, label):
    f = _flow(ctx)
    code, text = f["sub"][key]
    if code != 250:
        raise Fail("%s refused: %s %s" % (label, code, text[:150]))
    where = f["found"].get(key)
    if where != "INBOX":
        raise Fail("%s accepted but found in %s" % (label, where))
    return "submitted and delivered to INBOX"


def c_sender_denied(ctx):
    f = _flow(ctx)
    code, text = f["sub"]["team_denied"]
    if 500 <= code < 600:
        return "bob may not send as team@: %d %s" % (code, text[:80])
    raise Fail("bob could send as team@ (not a permitted sender): %s %s" % (code, text[:100]))


def c_no_quota_reject_alias(ctx):
    f = _flow(ctx)
    bad = []
    for k in ("alias", "catchall", "domalias_ca", "domalias_user"):
        code, text, _a = f["smtp"][k]
        if code != 250:
            bad.append("%s: %d %s" % (k, code, text[:60]))
    if bad:
        raise Fail("; ".join(bad))
    if not ctx.args.peer_ssh and not ctx.args.jump and ctx.args.host in ("127.0.0.1", "::1"):
        return ("PASS", "accepted, but sent from mynetworks (policy service not consulted)")
    return "alias, catch-all and domain-alias recipients accepted at RCPT"


def c_overquota(ctx):
    f = _flow(ctx)
    code, text, attempts = f["smtp"]["overquota"]
    if 500 <= code < 600:
        return "%d MB mail rejected at SMTP: %d %s" % (ctx.args.overquota_mb, code, text[:80])
    if code != 250:
        raise Fail("unexpected SMTP result %d %s" % (code, text[:100]))
    if f["found"].get("overquota_delivered"):
        raise Fail("%d MB mail was ACCEPTED and DELIVERED into bob's 10M mailbox "
                   "(check quota_storage_grace: 2.4 takes an absolute size, 22.04 MIAB used 10%%)" % ctx.args.overquota_mb)
    if f["found"].get("overquota_bounce"):
        return ("FAIL" if (ctx.args.peer_ssh or ctx.args.jump) else "PASS",
                "accepted at SMTP, LMTP refused, bounce generated (quota-status policy did not reject at RCPT)")
    raise Fail("accepted at SMTP, neither delivered nor bounced within the wait window")


def c_quotaroot(ctx):
    M = imap_login(ctx, ctx.bob)
    try:
        typ, data = M.getquotaroot("INBOX")
    finally:
        M.logout()
    flat = " ".join(x.decode(errors="replace") if isinstance(x, bytes) else str(x)
                    for part in data for x in (part if isinstance(part, list) else [part]))
    m = re.search(r"STORAGE (\d+) (\d+)", flat)
    if typ != "OK" or not m:
        raise Fail("GETQUOTAROOT: %s %s" % (typ, flat[:200]))
    used, limit = int(m.group(1)), int(m.group(2))
    if limit != 10240:
        raise Fail("bob limit %d KiB, expected 10240 (10M)" % limit)
    return "bob STORAGE %d / %d KiB" % (used, limit)


GREYLIST_BYPASS = "/etc/postfix/greylist_bypass_senders"


def c_greylist_bypass(ctx):
    # prepare-testenv.sh whitelists the peers in postgrey, so greylisting cannot
    # be watched on port 25 here: check what setup/mail-postfix.sh configured.
    has_file = ctx.remote.run("test -f %s" % GREYLIST_BYPASS)[0] == 0
    rc, out, err = ctx.remote.run("postconf -h smtpd_recipient_restrictions", timeout=60)
    items = [i.strip() for i in out.strip().split(",")]
    bypass = "check_sender_access hash:" + GREYLIST_BYPASS
    grey = "check_policy_service inet:127.0.0.1:10023"
    quota = "check_policy_service inet:127.0.0.1:12340"
    if not has_file:
        # The test boxes have no such file: then the restrictions end as upstream's.
        if bypass in items:
            raise Fail("%r is set, but %s is missing: %s" % (bypass, GREYLIST_BYPASS, out.strip()[:200]))
        if items[-2:] != [grey, quota]:
            raise Fail("without %s the restrictions should end with postgrey, then the quota check: %s"
                       % (GREYLIST_BYPASS, out.strip()[:200]))
        return "no %s: postgrey, then the quota check (as upstream)" % GREYLIST_BYPASS
    for item in (bypass, grey, quota):
        if item not in items:
            raise Fail("%r missing in smtpd_recipient_restrictions: %s" % (item, out.strip()[:200]))
    if not items.index(quota) < items.index(bypass) == items.index(grey) - 1:
        raise Fail("order should be quota check, sender bypass, postgrey: %s" % out.strip()[:200])
    rc, key, _err = ctx.remote.run("sed -n 's/^\\([^#[:space:]][^[:space:]]*\\).*/\\1/p' %s" % GREYLIST_BYPASS)
    key = (key.split() or [""])[0]
    if not key:
        return ("PASS", "restrictions ok; the file has no entries")
    rc, val, err = ctx.remote.run("postmap -q %s hash:%s" % (shlex.quote(key), GREYLIST_BYPASS), sudo=True, timeout=60)
    if rc != 0:
        raise Fail("postmap -q %s gives nothing (is the .db older than the file?) %s" % (key, err.strip()[:150]))
    return "quota check, then %s (%s -> %s), then postgrey" % (bypass, key, val.strip()[:20])


def c_root_mail(ctx):
    # Mail of cron and root goes to root@ + /etc/mailname (myorigin); setup sets
    # /etc/mailname to PRIMARY_HOSTNAME and makes root@ an automatic alias.
    rc, out, err = ctx.remote.run("cat /etc/mailname")
    if rc != 0 or out.strip() != ctx.hostname:
        raise Fail("/etc/mailname is %r, expected %s" % (out.strip()[:80], ctx.hostname))
    root = "root@" + ctx.hostname
    rc, out, err = ctx.remote.run("postmap -q %s sqlite:/etc/postfix/virtual-alias-maps.cf" % shlex.quote(root),
                                  sudo=True, timeout=60)
    if rc != 0 or not out.strip():
        raise Fail("%s is no alias, system mail would bounce (rc=%d %s)" % (root, rc, err.strip()[:120]))
    return "/etc/mailname ok, %s -> %s" % (root, out.strip()[:60])


def c_munin_contact(ctx):
    # Munin's alerts (B80): the contact "admin" is defined before the host tree
    # (lines after a [host] line belong to that host), its command exists, and
    # always_send (a mail every 5 minutes while a warning lasts) is not set.
    # Alerts that the admin panel turned off pass.
    cmd = ("awk '/^\\[/ { host = 1 } /^contact\\.admin\\./ { print (host ? \"host\" : \"global\"), $0 }' "
           "/etc/munin/munin.conf")
    rc, out, err = ctx.remote.run(cmd, sudo=True, timeout=60)
    if rc != 0:
        raise Fail("cannot read /etc/munin/munin.conf: %s" % (err or out).strip()[:120])
    lines = [line.split(" ", 1) for line in out.splitlines() if line.strip()]
    misplaced = [rest for where, rest in lines if where != "global"]
    if misplaced:
        raise Fail("contact lines inside the host tree (munin-limits ignores them): %s" % misplaced[0][:80])
    command = [rest.split(None, 1)[1] for where, rest in lines if rest.startswith("contact.admin.command ")]
    if not command:
        # Turned off in the admin panel (rc7): no contact, "contacts none".
        rc, out, err = ctx.remote.run("grep -qx 'contacts none' /etc/munin/munin.conf", sudo=True, timeout=60)
        if rc == 0 and ctx.admin_auth:
            r = admin_api(ctx, "GET", "system/munin/alerts")
            if r.status == 200 and r.json().get("recipient") == "off":
                return "alerts turned off in the admin panel (contacts none)"
        raise Fail("no contact.admin.command, Munin sends no alerts")
    if any(rest.startswith("contact.admin.always_send") for where, rest in lines):
        raise Fail("contact.admin.always_send is set (a mail every run while a warning lasts)")
    prog = command[0].split()[0]
    rc, out, err = ctx.remote.run("test -x %s" % shlex.quote(prog))
    if rc != 0:
        raise Fail("the contact's command %s is missing or not executable" % prog)
    return "contact admin -> %s" % command[0][:60]


def c_vacation(ctx):
    f = _flow(ctx)
    if f["smtp"]["vacation"][0] != 250:
        raise Fail("mail to carol rejected: %s" % f["smtp"]["vacation"][:2])
    if not f["found"].get("vacation"):
        raise Fail("mail to carol not delivered")
    if not f["found"].get("vacation_reply"):
        raise Fail("no vacation auto-reply to %s within %d s (carol's active script: vacation?)"
                   % ("vac-%s@%s" % (ctx.tok, ctx.seed2), ctx.args.deliver_timeout))
    return "auto-reply arrived via catch-all in bob's %s" % f["found"]["vacation_reply"]


def c_vacation_no_phantom_folders(ctx):
    # Dovecot 2.4 kept the lock files of the duplicate database (vacation,
    # redirect) in .dovecot.lda-dupes.locks in the Maildir, which IMAP listed as
    # folders "dovecot", "dovecot.lda-dupes" and "dovecot.lda-dupes.locks" (B66).
    # \Noselect entries count too. The parent "dovecot" alone is not counted:
    # a user may have a real folder of that name.
    f = _flow(ctx)
    if not f["found"].get("vacation_reply"):
        raise Skip("no vacation reply, so the duplicate database was not used")
    M = imap_login(ctx, ctx.carol)
    try:
        typ, data = M.list()
    finally:
        M.logout()
    names = []
    for raw in data or []:
        if raw is None:
            continue
        if isinstance(raw, tuple):
            names.append(raw[1].decode(errors="replace"))
            continue
        m = LIST_RE.match(raw.decode(errors="replace"))
        if m:
            name = m.group("name")
            names.append(name[1:-1] if name.startswith('"') else name)
    phantom = [n for n in names if re.match(r"(?i)^dovecot[./]lda-dupes($|[./]locks$)", n)]
    if phantom:
        raise Fail("%s has the folders %s" % (ctx.carol, ", ".join(sorted(phantom))))
    return "%d folders of %s, none from Dovecot's duplicate database" % (len(names), ctx.carol)


# ---------------------------------------------------------------------------
# checks: IMAPSieve -> sa-learn
# ---------------------------------------------------------------------------

def c_imapsieve(ctx):
    before = sa_magic(ctx)
    sid = "smk-%s-imapsieve" % ctx.tok
    words = " ".join(random.choice(["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf",
                                    "hotel", "india", "juliet", "kilo", "lima", "mike", "november"])
                     + str(random.randint(0, 99999)) for _ in range(150))
    msg = mkmsg("sender-%s@%s" % (ctx.tok, ctx.seed2), ctx.alice, "smoke imapsieve %s" % ctx.tok, sid,
                body=words + "\r\n")
    M = imap_login(ctx, ctx.alice)
    out = {}
    try:
        typ, _ = M.append("INBOX", None, None, msg.encode())
        if typ != "OK":
            raise Fail("APPEND failed")
        uids = uid_search(M, "INBOX", "HEADER", "X-Smoke-Id", sid, readonly=False)
        if not uids:
            raise Fail("appended message not found")
        typ, data = M.uid("MOVE", uids[-1].decode(), "Spam")
        if typ != "OK":
            raise Fail("MOVE to Spam: %s %s" % (typ, data))
        out["spam"] = _poll_magic(ctx, lambda m: m["nspam"] > before["nspam"])
        after_spam = out["spam"] or sa_magic(ctx)
        uids = uid_search(M, "Spam", "HEADER", "X-Smoke-Id", sid, readonly=False)
        if not uids:
            raise Fail("message not in Spam after MOVE")
        typ, data = M.uid("MOVE", uids[-1].decode(), "INBOX")
        if typ != "OK":
            raise Fail("MOVE out of Spam: %s %s" % (typ, data))
        out["ham"] = _poll_magic(ctx, lambda m: m.get("nham", 0) > after_spam.get("nham", 0))
    finally:
        M.logout()
    ctx.imapsieve = {"before": before, **out}
    return "before %s, after spam-move %s, after ham-move %s" % (before, out.get("spam"), out.get("ham"))


def c_fts(ctx):
    """Full-text search: a body-only word must be found by IMAP SEARCH and by the fts_xapian index."""
    word = "ftsprobe%s%d" % (ctx.tok.replace("-", ""), random.randint(1000, 9999))
    sid = "smk-%s-fts" % ctx.tok
    msg = mkmsg("sender-%s@%s" % (ctx.tok, ctx.seed2), ctx.alice, "smoke fts %s" % ctx.tok, sid,
                body="The quick brown fox mentions %s only in the body.\r\n" % word)
    M = imap_login(ctx, ctx.alice)
    try:
        typ, _ = M.append("INBOX", None, None, msg.encode())
        if typ != "OK":
            raise Fail("APPEND failed")
        uids = []
        for _ in range(15):
            uids = uid_search(M, "INBOX", "BODY", word)
            if uids:
                break
            time.sleep(2)
        if not uids:
            raise Fail("IMAP SEARCH BODY %s found nothing" % word)
    finally:
        M.logout()
    # Make sure the hit came from the Xapian index and not from a slow scan.
    # Indexing runs asynchronously in the indexer, so give it a moment.
    for _ in range(15):
        rc, out, err = ctx.remote.run("doveadm fts lookup -u %s mailbox INBOX body %s" % (ctx.alice, word),
                                      sudo=True, timeout=120)
        if rc == 0 and re.search(r"INBOX: \d", out):
            break
        time.sleep(2)
    if rc != 0 or not re.search(r"INBOX: \d", out):
        raise Fail("doveadm fts lookup rc=%d: %s" % (rc, (err or out).strip()[:300]))
    return "IMAP SEARCH found uid %s, fts index: %s" % (uids[-1].decode(), out.strip().splitlines()[0][:80])


def _poll_magic(ctx, cond, timeout=45):
    deadline = time.time() + timeout
    while time.time() < deadline:
        m = sa_magic(ctx)
        if cond(m):
            return m
        time.sleep(3)
    return None


def c_imapsieve_result(ctx, which):
    r = getattr(ctx, "imapsieve", None)
    if r is None:
        raise Skip("IMAPSieve test did not run")
    if not r.get(which):
        raise Fail("n%s did not increase after MOVE %s Spam (before %s)" % (which, "into" if which == "spam" else "out of", r["before"]))
    return "n%s %d -> %d" % (which, r["before"].get("n" + which, 0), r[which]["n" + which])


# ---------------------------------------------------------------------------
# cleanup
# ---------------------------------------------------------------------------

def c_cleanup(ctx):
    n = 0
    for user in (ctx.alice, ctx.bob, ctx.carol):
        try:
            M = imap_login(ctx, user)
        except Exception:
            continue
        try:
            for folder in list_folders(M):
                uids = uid_search(M, folder, "TEXT", '"%s"' % ctx.tok, readonly=False)
                if uids:
                    M.uid("STORE", b",".join(uids).decode(), "+FLAGS.SILENT", "(\\Deleted)")
                    M.expunge()
                    n += len(uids)
        finally:
            M.logout()
    return "removed %d test messages" % n


# ---------------------------------------------------------------------------
# fail2ban (opt-in)
# ---------------------------------------------------------------------------

def f2b_banned(ctx, jail):
    rc, out, err = ctx.remote.run("fail2ban-client status %s" % shlex.quote(jail), sudo=True)
    if rc != 0:
        return None
    m = re.search(r"Banned IP list:\s*(.*)", out)
    return set(m.group(1).split()) if m else set()


def f2b_unban(ctx, ip):
    for jail in ("dovecot", "miab-postfix587", "miab-postfix465", "postfix-sasl", "recidive"):
        ctx.remote.run("fail2ban-client set %s unbanip %s" % (jail, shlex.quote(ip)), sudo=True)
    ctx.remote.run("fail2ban-client unban %s" % shlex.quote(ip), sudo=True)


def f2b_prepare(ctx):
    if not ctx.remote.available() or ctx.remote.spec == "local":
        raise Skip("needs --ssh to the box (not 'local': the box ignores its own IPs)")
    rc, out, _ = ctx.remote.run("echo $SSH_CONNECTION")
    ssh_src = out.split()[0] if out.split() else None
    if ctx.args.peer_ssh:
        attack_src = run_snippet(SMTP_SNIPPET, "source_ip", {"host": ctx.args.host, "port": 993},
                                 ssh_host=ctx.args.peer_ssh)
    elif ctx.args.fail2ban_force:
        attack_src = None
    else:
        raise Skip("attacks would come from this machine / the jump host; use --peer-ssh, or --fail2ban-force "
                   "if you are sure the --ssh session uses another source IP")
    if attack_src and ssh_src and attack_src == ssh_src:
        raise Skip("attack source %s equals the ssh source; a dovecot ban (all ports) would lock us out" % attack_src)
    ctx.f2b = {"ssh_src": ssh_src, "attack_src": attack_src}
    return "attack source %s, ssh source %s" % (attack_src or "unknown", ssh_src)


F2B_ROTATE_SCRIPT = r"""
set -u
tok=$1
# One rotation of rsyslog's logs, as the weekly logrotate run does it (with the su line of logrotate.conf).
su=$(grep -m1 '^su ' /etc/logrotate.conf || echo 'su root adm')
logger -p mail.info "smoke-before-rotation-$tok"; sleep 1
ino=$(stat -c %i /var/log/mail.log)
conf=$(mktemp /root/smoke-rotate.XXXXXX)
printf '%s\ninclude /etc/logrotate.d/rsyslog\n' "$su" > "$conf"
logrotate -f "$conf"; rc=$?; rm -f "$conf"
[ $rc = 0 ] || { echo "logrotate rc=$rc"; exit 1; }
[ ! -e /var/log/mail.log ] || [ "$(stat -c %i /var/log/mail.log)" != "$ino" ] || { echo "mail.log was not rotated"; exit 1; }
logger -p mail.info "smoke-rotation-$tok"
# Up to rc5 (and in test versions of rc6) Dovecot wrote mail.log itself (log_path): it must then
# write the new file. With log_path=syslog no Dovecot process may hold a file in
# /var/log (rsyslog writes Dovecot's lines).
lp=$(doveconf -h log_path 2> /dev/null)
for i in $(seq 40); do
	w=$(for p in $(pgrep -f '^dovecot/|/usr/sbin/dovecot'); do ls -l /proc/$p/fd 2> /dev/null | grep -o '/var/log/[^ ]*'; done | sort -u | tr '\n' ' ')
	r=$(grep -c "smoke-rotation-$tok" /var/log/mail.log 2> /dev/null)
	if [ "$lp" = syslog ]; then [ "${r:-0}" -ge 1 ] && break
	else [ "$w" = "/var/log/mail.log " ] && [ "${r:-0}" -ge 1 ] && break; fi
	sleep 0.5
done
echo "log_path=${lp:-unknown} dovecot=${w:-none} rsyslog=${r:-0} owner=$(stat -c '%U:%G %a' /var/log/mail.log 2> /dev/null)"
"""


def c_fail2ban_log_rotation(ctx):
    # The jails read /var/log/mail.log. After a rotation of it Dovecot's lines
    # must go to the new file at once; otherwise the Dovecot jails see no failed
    # login until Dovecot restarts (B85). Dovecot logs through syslog
    # (log_path=syslog), so rsyslog writes them and no Dovecot process may hold
    # a file in /var/log; with Dovecot's own log_path (up to rc5) it
    # must hold the new mail.log. So rotate once before the attacks: a jail that
    # went blind after a rotation then fails.
    if not getattr(ctx, "f2b", None):
        raise Skip("fail2ban preparation skipped")
    rc, out, err = ctx.remote.run("bash -c %s smoke %s" % (shlex.quote(F2B_ROTATE_SCRIPT), ctx.tok), sudo=True, timeout=120)
    out = out.strip()
    if rc != 0:
        raise Fail("rotation of mail.log failed: %s %s" % (out[:200], err.strip()[:200]))
    m = re.search(r"log_path=(\S*)\s+dovecot=(.*?)\s+rsyslog=(\d+)\s+owner=(.*)$", out)
    if not m:
        raise Fail("unexpected output: %s" % out[:200])
    lp, dov, rs, owner = m.group(1), m.group(2).strip(), int(m.group(3)), m.group(4)
    if lp == "syslog":
        if dov != "none":
            raise Fail("Dovecot logs through syslog, but its processes hold %s" % dov)
    elif dov != "/var/log/mail.log":
        raise Fail("20 s after a rotation Dovecot (log_path=%s) still writes %s, not the new /var/log/mail.log "
                   "(the Dovecot jails would see no failed login, B85)" % (lp, dov or "nothing"))
    if rs < 1:
        raise Fail("rsyslog did not write the new /var/log/mail.log after the rotation (owner %s)" % owner)
    return "rotated; log_path=%s, rsyslog writes the new mail.log (%s)" % (lp, owner)


def c_fail2ban_adaptive_toggle(ctx):
    # Turning adaptive banning off must take effect in the running jails (a
    # plain "fail2ban-client reload" left bantime.increment on), and on again.
    # Restarts the jails twice; the original setting is restored.
    if not ctx.remote.available():
        raise Skip("needs --ssh")

    def increment():
        rc, out, err = ctx.remote.run("fail2ban-client get sshd bantime.increment", sudo=True, timeout=60)
        if rc != 0:
            raise Fail("fail2ban-client get sshd bantime.increment: %s" % err.strip()[:200])
        return out.strip()

    def post(value):
        r = admin_api(ctx, "POST", "system/fail2ban/settings", form={"adaptive": value})
        if r.status != 200:
            raise Fail("set adaptive=%s: HTTP %d %s" % (value, r.status, r.text()[:200]))
        return r.json()

    orig = admin_api(ctx, "GET", "system/fail2ban/settings").json()["settings"]["adaptive"]
    seen = []
    try:
        # Off, a restarted jail has no bantime.increment at all ("None", as
        # with upstream's configuration); "False" would be a leftover value.
        steps = [("0", ("None", "False")), ("1", ("True",))]
        for value, want in (steps if orig else steps[::-1]):
            j = post(value)
            if not j.get("restarted"):
                raise Fail("adaptive=%s: jails not restarted (%s)" % (value, j))
            got = increment()
            seen.append(got)
            if got not in want:
                raise Fail("adaptive=%s: sshd bantime.increment is %s, expected %s" % (value, got, " or ".join(want)))
    finally:
        post("1" if orig else "0")
    return "increment %s, restored adaptive=%s" % (" -> ".join(seen), orig)


def c_fail2ban(ctx, proto, jails, port):
    if not getattr(ctx, "f2b", None):
        raise Skip("fail2ban preparation skipped")
    # Attempts of the previous protocol that were still in flight can re-ban the
    # source right after its unban (postfix-sasl covers 465 and 587), so start
    # from a clean state: unban, let fail2ban process the backlog, unban again.
    src = ctx.f2b.get("attack_src")
    if src:
        f2b_unban(ctx, src)
        time.sleep(5)
        f2b_unban(ctx, src)
    before = {j: f2b_banned(ctx, j) for j in jails}
    if all(v is None for v in before.values()):
        raise Fail("none of the jails %s exist" % jails)
    if ctx.args.peer_ssh:
        spec = {"host": ctx.args.host, "port": port, "proto": proto, "count": ctx.args.fail2ban_count,
                "parallel": ctx.args.fail2ban_parallel}
        res = run_snippet(F2B_SNIPPET, "attack", spec, ssh_host=ctx.args.peer_ssh)
    else:
        h, p = ctx.net.addr(port)
        res = run_snippet(F2B_SNIPPET, "attack", {"host": h, "port": p, "proto": proto,
                                                  "count": ctx.args.fail2ban_count,
                                                  "parallel": ctx.args.fail2ban_parallel})
    new = set()
    deadline = time.time() + 30
    while time.time() < deadline:
        for j in jails:
            now = f2b_banned(ctx, j)
            if now is not None:
                new |= {(j, ip) for ip in now - (before[j] or set())}
        if new:
            break
        time.sleep(3)
    for _j, ip in new:
        f2b_unban(ctx, ip)
    rec = f2b_banned(ctx, "recidive") or set()
    for ip in rec:
        if ip == ctx.f2b.get("attack_src") or any(ip == x for _j, x in new):
            f2b_unban(ctx, ip)
    time.sleep(ctx.args.fail2ban_pause)
    for _j, ip in new:
        f2b_unban(ctx, ip) # late re-bans from attempts that were still in flight
    if not new:
        raise Fail("no ban after %d failed %s logins in %.0f s (%s); jail filter does not match the log "
                   "format?" % (ctx.args.fail2ban_count, proto, res["seconds"], res["summary"]))
    src = ctx.f2b.get("attack_src")
    ips = sorted({ip for _j, ip in new})
    if src and src not in ips:
        raise Fail("banned %s but attack source was %s" % (ips, src))
    return "banned %s in %s (probe after: %s), unbanned" % (ips, sorted({j for j, _ in new}), res["probe_after"])


def send_test_mail(ctx):
    """--send-test-mail FROM TO: one marked test mail, for the testers' own mails
    (vacation triggers, delivery tests after a reboot)."""
    frm, to = ctx.args.send_test_mail
    sid = "test-%s" % ctx.tok
    data = mkmsg(frm, to, ctx.args.test_subject or "test mail %s" % ctx.tok, sid)
    msgid = mail_id(parse_mail(data))
    if ctx.args.via == "25":
        res = smtp_batch(ctx, [{"id": "t", "from": frm, "rcpt": to, "data": data}])
        code, text = res["t"][0], res["t"][1]
        how = "port 25 from " + (ctx.args.peer_ssh or "here")
    else:
        code, text = submit(ctx, int(ctx.args.via), frm, frm, to, data)
        how = "submission %s as %s" % (ctx.args.via, frm)
    print("%s: %s %s, Message-ID <%s>" % (how, code, redact(str(text))[:120], msgid))
    return 0 if code == 250 else 1


# ---------------------------------------------------------------------------
# checks: management API (group api), as api/mailinabox.yml documents it
# ---------------------------------------------------------------------------

# Every documented operation is in exactly one of these lists;
# tests/fork/api-routes.py checks that against api/mailinabox.yml (and the
# content types of API_READ_ONLY against the documented 200 answers).
#
# Read-only: (method, documented path, content type of the 200 answer).
API_READ_ONLY = [
    ("GET", "/system/version", "text/html"),
    ("POST", "/system/latest-upstream-version", "text/html"),
    ("POST", "/system/status", "application/json"),
    ("GET", "/system/updates", "text/html"),
    ("GET", "/system/privacy", "application/json"),
    ("GET", "/system/reboot", "application/json"),
    ("GET", "/system/backup/status", "application/json"),
    ("GET", "/system/backup/status/saved", "application/json"),
    ("GET", "/system/backup/config", "application/json"),
    ("GET", "/system/fail2ban", "application/json"),
    ("GET", "/system/fail2ban/settings", "application/json"),
    ("GET", "/system/fail2ban/report", "application/json"),
    ("GET", "/system/munin/alerts", "application/json"),
    ("GET", "/ssl/status", "application/json"),
    ("POST", "/ssl/csr/{domain}", "text/html"),
    ("GET", "/dns/zones", "application/json"),
    ("GET", "/dns/zonefile/{zone}", "text/plain"),
    ("GET", "/dns/custom", "application/json"),
    ("GET", "/dns/custom/{qname}", "application/json"),
    ("GET", "/dns/custom/{qname}/{rtype}", "application/json"),
    ("GET", "/dns/dump", "application/json"),
    ("GET", "/dns/secondary-nameserver", "application/json"),
    ("GET", "/mail/users", "application/json"),
    ("GET", "/mail/users/privileges", "text/html"),
    ("GET", "/mail/users/quota", "application/json"),
    ("GET", "/mail/domains", "text/html"),
    ("GET", "/mail/aliases", "application/json"),
    ("GET", "/web/domains", "application/json"),
    ("POST", "/mfa/status", "application/json"),
    ("GET", "/munin/", "text/html"),
]

# Called by the auth check, the write round trip, the Munin checks and the
# check of the saved backup status (admin-backup-saved).
API_WRITES = [
    ("POST", "/system/backup/status/refresh"),
    ("POST", "/login"),
    ("POST", "/logout"),
    ("POST", "/mail/users/add"),
    ("POST", "/mail/users/password"),
    ("POST", "/mail/users/quota"),
    ("POST", "/mail/users/privileges/add"),
    ("POST", "/mail/users/privileges/remove"),
    ("POST", "/mail/users/remove"),
    ("POST", "/mail/aliases/add"),
    ("POST", "/mail/aliases/remove"),
    ("POST", "/dns/custom/{qname}/{rtype}"),
    ("PUT", "/dns/custom/{qname}/{rtype}"),
    ("DELETE", "/dns/custom/{qname}/{rtype}"),
    ("POST", "/system/privacy"),
    ("POST", "/system/munin/alerts"),
    ("POST", "/system/munin/alerts/test"),
]

# Not called: (method, documented path, reason).
API_NOT_CALLED = [
    ("POST", "/system/reboot", "reboots the box"),
    ("POST", "/system/update-packages", "installs package updates"),
    ("POST", "/ssl/provision", "requests certificates from Let's Encrypt"),
    ("POST", "/ssl/install", "replaces a certificate"),
    ("POST", "/web/update", "rewrites the nginx configuration and reloads nginx"),
    ("POST", "/system/backup/config", "changes the backup target and its credentials"),
    ("POST", "/mfa/totp/enable", "turns on MFA for the admin"),
    ("POST", "/mfa/disable", "removes MFA from an account"),
    ("POST", "/dns/update", "rewrites all zones (the custom record round trip updates them)"),
    ("POST", "/dns/secondary-nameserver", "changes the zones and nsd's transfer settings"),
    ("POST", "/system/fail2ban/settings", "group admin (admin-fail2ban-settings) sets and restores it"),
    ("POST", "/system/fail2ban/unban", "releases real bans (group fail2ban unbans its own)"),
    ("POST", "/system/fail2ban/unban-all", "releases real bans"),
    ("POST", "/dns/custom/{qname}", "the view of /dns/custom/{qname}/{rtype} with type A, which needs an address"),
    ("PUT", "/dns/custom/{qname}", "the view of /dns/custom/{qname}/{rtype} with type A, which needs an address"),
    ("DELETE", "/dns/custom/{qname}", "the view of /dns/custom/{qname}/{rtype} with type A: would delete real A records"),
]

MUNIN_NOTIFY = "/usr/local/lib/mailinabox/munin-notify"


def api_ctype(r):
    v = r.header("Content-Type")
    return v[0].split(";")[0].strip().lower() if v else ""


def api_expect(r, status, ctype, what):
    # status and content type, or Fail with a short excerpt (never the body
    # of an answer that can hold secrets: the caller passes what=... only)
    if r.status != status:
        raise Fail("%s: HTTP %d, expected %d: %s" % (what, r.status, status, r.text()[:120].strip()))
    if ctype and api_ctype(r) != ctype:
        raise Fail("%s: content type %s, expected %s" % (what, api_ctype(r) or "none", ctype))


def c_api_auth(ctx):
    # Exactly two failed logins (the wrong password and the key after its
    # logout), far below the miab-management jail (20 within 30 s). Requests
    # without an Authorization header are not logged as failed logins.
    if not ctx.admin_auth:
        raise Skip("no admin session (admin credentials missing or login failed)")
    notes = []
    r = http_req(ctx, "GET", "/admin/system/version")
    api_expect(r, 401, "text/plain", "no credentials")
    if not r.header("WWW-Authenticate") or not r.header("X-Reason"):
        raise Fail("no credentials: 401 without WWW-Authenticate or X-Reason")
    r = http_req(ctx, "GET", "/admin/system/version", headers={"Accept": "application/json"})
    api_expect(r, 401, "application/json", "no credentials, Accept JSON")
    if r.json().get("status") != "error" or not r.json().get("reason"):
        raise Fail("no credentials, Accept JSON: body %s" % r.text()[:100])
    r = http_req(ctx, "GET", "/admin/system/version", headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"})
    api_expect(r, 403, "application/json", "no credentials, XMLHttpRequest")
    notes.append("no credentials 401/401/403")
    wrong = "wrong-%s" % ctx.tok
    r = http_req(ctx, "GET", "/admin/system/version", auth=(ctx.admin_user, wrong))
    api_expect(r, 401, "text/plain", "wrong password")
    notes.append("wrong password 401")
    r = admin_api(ctx, "GET", "system/version")
    api_expect(r, 200, "text/html", "API key")
    # A second session: its key works until logout, then it gets 401.
    r = http_req(ctx, "POST", "/admin/login", auth=(ctx.admin_user, ctx.admin_pw))
    api_expect(r, 200, "application/json", "second login")
    j = r.json()
    if j.get("status") != "ok" or not j.get("api_key") or j.get("email") != ctx.admin_user or "admin" not in (j.get("privileges") or []):
        raise Fail("second login: status %s" % j.get("status"))
    key2 = j["api_key"]
    SECRETS.add(key2)
    if key2 == ctx.admin_auth[1]:
        raise Fail("second login gave the same key")
    api_expect(http_req(ctx, "GET", "/admin/system/version", auth=(ctx.admin_user, key2)), 200, "text/html", "second key")
    r = http_req(ctx, "POST", "/admin/logout", auth=(ctx.admin_user, key2))
    api_expect(r, 200, "application/json", "logout")
    if r.json().get("status") != "ok":
        raise Fail("logout: %s" % r.text()[:100])
    api_expect(http_req(ctx, "GET", "/admin/system/version", auth=(ctx.admin_user, key2)), 401, "text/plain", "key after logout")
    notes.append("login/key/logout ok, key after logout 401")
    api_expect(admin_api(ctx, "GET", "system/version"), 200, "text/html", "first key after the other logout")
    return "; ".join(notes) + " (2 failed logins)"


def _is_str_list(x):
    return isinstance(x, list) and all(isinstance(v, str) for v in x)


def _need(cond, what):
    if not cond:
        raise Fail(what)


def api_shape(ctx, path, r):
    # The documented shape of each read-only answer (api/mailinabox.yml).
    # Returns a short note. Never puts the body of /mfa/status into a message.
    if api_ctype(r) == "application/json":
        j = r.json()
    t = r.text()
    if path == "/system/version":
        _need(t.strip() and "\n" not in t.strip(), "version: %r" % t[:60])
        return t.strip()
    if path == "/system/latest-upstream-version":
        _need(t.strip() and "\n" not in t.strip(), "latest version: %r" % t[:60])
        return "latest " + t.strip()
    if path == "/system/status":
        _need(isinstance(j, list) and j, "status: not a non-empty list")
        for e in j:
            _need(isinstance(e, dict) and e.get("type") in ("heading", "ok", "error", "warning")
                  and isinstance(e.get("text"), str) and isinstance(e.get("extra"), list), "status entry %r" % str(e)[:80])
        c = Counter(e["type"] for e in j)
        return "%d ok, %d warnings, %d errors" % (c["ok"], c["warning"], c["error"])
    if path == "/system/updates":
        bad = [x for x in t.splitlines() if x and not re.match(r"^\S+ \(.+\)$", x)]
        _need(not bad, "updates: line %r" % (bad[:1],))
        return "%d updates" % len(t.splitlines())
    if path in ("/system/privacy", "/system/reboot"):
        _need(isinstance(j, bool), "%s: not a boolean" % path)
        return str(j).lower()
    if path == "/system/backup/status":
        _need(isinstance(j, dict) and (isinstance(j.get("backups"), list) or isinstance(j.get("error"), str)),
              "backup status: no backups list and no error")
        return "error" if "error" in j else "%d backups" % len(j["backups"])
    if path == "/system/backup/status/saved":
        _need(isinstance(j, dict) and "status" in j and isinstance(j.get("refreshing"), bool)
              and (j["status"] is None or isinstance(j["status"], dict)), "saved backup status: keys missing")
        return "none saved" if j["status"] is None else "as of %s" % j.get("time_str")
    if path == "/system/backup/config":
        _need(isinstance(j, dict) and isinstance(j.get("target"), str), "backup config: no target")
        return "target " + j["target"].split(":", 1)[0]
    if path == "/system/fail2ban":
        _need(isinstance(j.get("running"), bool) and isinstance(j.get("jails"), list) and isinstance(j.get("settings"), dict)
              and isinstance(j.get("config_current"), bool), "fail2ban status: keys missing")
        return "%d jails" % len(j["jails"])
    if path == "/system/fail2ban/settings":
        _need(isinstance(j.get("settings"), dict) and isinstance(j.get("defaults"), dict) and isinstance(j.get("warnings"), list),
              "fail2ban settings: keys missing")
        return "ok"
    if path == "/system/fail2ban/report":
        _need(isinstance(j.get("failures"), int) and isinstance(j.get("distinct_ips"), int) and _is_str_list(j.get("flagged_accounts")),
              "fail2ban report: keys missing")
        return "%d failures" % j["failures"]
    if path == "/system/munin/alerts":
        _need(j.get("recipient") in ("admin", "custom", "off") and j.get("level") in ("warning", "critical")
              and isinstance(j.get("address"), str) and isinstance(j.get("warnings"), list), "munin alerts: keys missing")
        _need(j.get("default_address") == "administrator@" + ctx.hostname, "munin alerts: default_address %s" % j.get("default_address"))
        _need(j.get("config_current") is True, "munin alerts: munin.conf does not match the setting")
        return "%s/%s" % (j["recipient"], j["level"])
    if path == "/ssl/status":
        _need(_is_str_list(j.get("can_provision")) and isinstance(j.get("status"), list)
              and all({"domain", "status", "text"} <= set(e) for e in j["status"]), "ssl status: keys missing")
        return "%d domains" % len(j["status"])
    if path == "/ssl/csr/{domain}":
        _need(t.startswith("-----BEGIN CERTIFICATE REQUEST-----"), "csr: not a PEM certificate request")
        return "CSR"
    if path == "/dns/zones":
        _need(_is_str_list(j) and j, "zones: not a non-empty list of names")
        return "%d zones" % len(j)
    if path == "/dns/zonefile/{zone}":
        _need(re.search(r"\sSOA\s", t), "zone file without SOA")
        return "%d lines" % len(t.splitlines())
    if path.startswith("/dns/custom"):
        _need(isinstance(j, list) and all({"qname", "rtype", "value", "sort-order"} <= set(e) for e in j), "custom records: keys missing")
        return "%d records" % len(j)
    if path == "/dns/dump":
        _need(isinstance(j, list) and j and all(isinstance(z, list) and len(z) == 2 and isinstance(z[1], list)
                                              and all({"qname", "rtype", "value", "explanation"} <= set(x) for x in z[1]) for z in j),
              "dns dump: not a list of [zone, records]")
        return "%d zones" % len(j)
    if path == "/dns/secondary-nameserver":
        _need(_is_str_list(j.get("hostnames")), "secondary nameserver: no hostnames list")
        return "%d hostnames" % len(j["hostnames"])
    if path == "/mail/users":
        _need(isinstance(j, list) and all(isinstance(d.get("domain"), str) and isinstance(d.get("users"), list) for d in j),
              "users: not a list of domains with users")
        users = {u.get("email"): u for d in j for u in d["users"]}
        _need(all({"email", "privileges", "status"} <= set(u) for u in users.values()), "users: keys missing")
        _need("admin" in (users.get(ctx.admin_user) or {}).get("privileges", []), "users: %s is not listed as admin" % ctx.admin_user)
        return "%d users" % len(users)
    if path == "/mail/users/privileges":
        _need("admin" in t.split("\n"), "privileges of the admin: %r" % t[:60])
        return "admin"
    if path == "/mail/users/quota":
        _need(j.get("email") == ctx.admin_user and isinstance(j.get("quota"), str), "quota: %r" % str(j)[:80])
        return "quota " + j["quota"]
    if path == "/mail/domains":
        _need(ctx.domain in t.split("\n"), "domains: %s missing" % ctx.domain)
        return "%d domains" % len(t.split())
    if path == "/mail/aliases":
        _need(isinstance(j, list) and all(isinstance(d.get("domain"), str) and isinstance(d.get("aliases"), list) for d in j)
              and all({"address", "forwards_to", "permitted_senders", "auto"} <= set(a) for d in j for a in d["aliases"]),
              "aliases: not a list of domains with aliases")
        return "%d aliases" % sum(len(d["aliases"]) for d in j)
    if path == "/web/domains":
        _need(isinstance(j, list) and j and all({"domain", "root", "custom_root", "ssl_certificate"} <= set(d) for d in j),
              "web domains: keys missing")
        return "%d domains" % len(j)
    if path == "/mfa/status":
        _need(isinstance(j.get("enabled_mfa"), list) and isinstance((j.get("new_mfa") or {}).get("totp"), dict),
              "mfa status: enabled_mfa or new_mfa.totp missing")
        SECRETS.add(j["new_mfa"]["totp"].get("secret", ""))
        return "%d MFA" % len(j["enabled_mfa"])
    if path == "/munin/":
        _need(t.strip() == "OK" and any("session=" in c for c in r.header("Set-Cookie")), "munin start: no session cookie")
        return "cookie"
    raise Fail("no shape check for %s" % path)


def api_request(ctx, method, path):
    # The request for a documented read-only path, with real parameters.
    zones = getattr(ctx, "api_zones", None) or [ctx.domain]
    real = (path.replace("{domain}", ctx.hostname).replace("{zone}", zones[0])
            .replace("{qname}", ctx.hostname).replace("{rtype}", "A"))
    form = None
    if path == "/mail/users" or path == "/mail/aliases":
        real += "?format=json"
    elif path in ("/mail/users/privileges", "/mail/users/quota"):
        real += "?" + urllib.parse.urlencode({"email": ctx.admin_user})
    elif path == "/ssl/csr/{domain}":
        form = {"countrycode": "US"}
    elif method == "POST":
        form = {}
    # system/status runs all status checks, system/updates apt-get update
    timeout = 300 if path in ("/system/status", "/system/updates") else 90
    return admin_api(ctx, method, real, form=form, timeout=timeout)


def c_api_read_only(ctx):
    notes, fails = [], []
    r = admin_api(ctx, "GET", "dns/zones")
    ctx.api_zones = r.json() if r.status == 200 else None
    for method, path, ctype in API_READ_ONLY:
        try:
            r = api_request(ctx, method, path)
            if path == "/system/latest-upstream-version" and r.status == 503:
                notes.append("%s 503 (documented: not reachable)" % path)
                continue
            api_expect(r, 200, ctype, "%s %s" % (method, path))
            notes.append("%s %s" % (path, api_shape(ctx, path, r)))
        except Fail as e:
            fails.append(str(e))
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            fails.append("%s %s: %s %s" % (method, path, type(e).__name__, str(e)[:80]))
    # The plain text forms of the user and alias lists.
    r = admin_api(ctx, "GET", "mail/users")
    if r.status != 200 or api_ctype(r) != "text/html" or ctx.admin_user not in r.text().split("\n"):
        fails.append("GET /mail/users (text): HTTP %d %s" % (r.status, api_ctype(r)))
    r = admin_api(ctx, "GET", "mail/aliases")
    if r.status != 200 or api_ctype(r) != "text/html":
        fails.append("GET /mail/aliases (text): HTTP %d %s" % (r.status, api_ctype(r)))
    if fails:
        raise Fail("%d of %d: %s" % (len(fails), len(API_READ_ONLY), "; ".join(fails)))
    return "%d endpoints: %s" % (len(API_READ_ONLY), ", ".join(n for n in notes))


def api_snapshot(ctx):
    # The lists that the write round trip must leave as they were.
    users = admin_api(ctx, "GET", "mail/users?format=json")
    aliases = admin_api(ctx, "GET", "mail/aliases?format=json")
    custom = admin_api(ctx, "GET", "dns/custom")
    for r, what in ((users, "users"), (aliases, "aliases"), (custom, "custom records")):
        api_expect(r, 200, "application/json", what)
    # mailbox sizes change with deliveries; compare the accounts only
    u = sorted((x["email"], tuple(x["privileges"]), x["status"], x.get("quota")) for d in users.json() for x in d["users"])
    return {"users": u, "aliases": aliases.json(), "custom": custom.json(),
            "privacy": admin_api(ctx, "GET", "system/privacy").json()}


def c_api_write_roundtrip(ctx):
    if not ctx.user_pw:
        raise Skip("TEST_USER_PW missing")
    before = api_snapshot(ctx)
    user = "smokeapi-%s@%s" % (ctx.tok, ctx.domain)
    alias = "smokeapialias-%s@%s" % (ctx.tok, ctx.domain)
    qname = "smokeapi-%s.%s" % (ctx.tok, ctx.domain)
    v1, v2 = "smokeapi-%s-1" % ctx.tok, "smokeapi-%s-2" % ctx.tok
    pw2 = "Smk-%s" % uuid.uuid4().hex
    SECRETS.add(pw2)
    steps = []
    txt = {"Content-Type": "text/plain"}

    def records():
        r = admin_api(ctx, "GET", "dns/custom/%s/TXT" % qname)
        api_expect(r, 200, "application/json", "GET custom TXT")
        return sorted(x["value"] for x in r.json())

    try:
        api_expect(admin_api(ctx, "POST", "mail/users/add", form={"email": user, "password": ctx.user_pw}), 200, "text/html", "users/add")
        api_expect(admin_api(ctx, "POST", "mail/users/password", form={"email": user, "password": pw2}), 200, "text/html", "users/password")
        for form in ({"email": user, "quota": "1.5G"}, {"email": user}):
            r = admin_api(ctx, "POST", "mail/users/quota", form=form)
            _need(r.status == 400, "users/quota %s: HTTP %d, expected 400" % (form.get("quota", "(none)"), r.status))
        api_expect(admin_api(ctx, "POST", "mail/users/quota", form={"email": user, "quota": "1G"}), 200, "text/html", "users/quota")
        r = admin_api(ctx, "GET", "mail/users/quota?" + urllib.parse.urlencode({"email": user}))
        api_expect(r, 200, "application/json", "GET quota")
        _need(r.json().get("quota") == "1G", "quota after set: %s" % r.json().get("quota"))
        r = admin_api(ctx, "GET", "mail/users/quota?" + urllib.parse.urlencode({"email": "nobody-%s@%s" % (ctx.tok, ctx.domain)}))
        _need(r.status == 400, "GET quota of a non-user: HTTP %d, expected 400" % r.status)
        steps.append("user, password, quota (and two refused)")
        api_expect(admin_api(ctx, "POST", "mail/users/privileges/add", form={"email": user, "privilege": "admin"}), 200, "text/html", "privileges/add")
        _need("admin" in admin_api(ctx, "GET", "mail/users/privileges?" + urllib.parse.urlencode({"email": user})).text().split("\n"),
              "admin privilege not listed")
        api_expect(admin_api(ctx, "POST", "mail/users/privileges/remove", form={"email": user, "privilege": "admin"}), 200, "text/html", "privileges/remove")
        _need("admin" not in admin_api(ctx, "GET", "mail/users/privileges?" + urllib.parse.urlencode({"email": user})).text().split("\n"),
              "admin privilege still listed")
        steps.append("admin privilege")
        api_expect(admin_api(ctx, "POST", "mail/aliases/add", form={"address": alias, "forwards_to": user, "permitted_senders": ""}),
                   200, "text/html", "aliases/add")
        r = admin_api(ctx, "GET", "mail/aliases?format=json")
        _need(any(a["address"] == alias and a["forwards_to"] == [user] for d in r.json() for a in d["aliases"]), "new alias not listed")
        api_expect(admin_api(ctx, "POST", "mail/aliases/remove", form={"address": alias}), 200, "text/html", "aliases/remove")
        steps.append("alias")
        api_expect(admin_api(ctx, "POST", "dns/custom/%s/TXT" % qname, body=v1, headers=txt), 200, "text/html", "POST custom TXT")
        _need(records() == [v1], "after POST: %s" % records())
        api_expect(admin_api(ctx, "POST", "dns/custom/%s/TXT" % qname, body=v2, headers=txt), 200, "text/html", "POST second TXT")
        _need(records() == sorted([v1, v2]), "after second POST: %s" % records())
        api_expect(admin_api(ctx, "PUT", "dns/custom/%s/TXT" % qname, body=v1, headers=txt), 200, "text/html", "PUT custom TXT")
        _need(records() == [v1], "after PUT: %s" % records())
        api_expect(admin_api(ctx, "DELETE", "dns/custom/%s/TXT" % qname, body=v1, headers=txt), 200, "text/html", "DELETE custom TXT")
        _need(records() == [], "after DELETE: %s" % records())
        steps.append("custom TXT post/put/delete")
        cur = before["privacy"]
        api_expect(admin_api(ctx, "POST", "system/privacy", form={"value": "private" if cur else "off"}), 200, "text/html", "privacy")
        steps.append("privacy (same value)")
    finally:
        admin_api(ctx, "DELETE", "dns/custom/%s/TXT" % qname)
        admin_api(ctx, "POST", "mail/aliases/remove", form={"address": alias})
        r = admin_api(ctx, "POST", "mail/users/remove", form={"email": user})
        # Also when a step above failed: its archived mailbox would stay as an
        # inactive account. An error here must not hide the step's own.
        try:
            mailbox = remove_test_mailbox(ctx, user)
        except Exception as e:
            mailbox = e
    api_expect(r, 200, "text/html", "users/remove")
    if isinstance(mailbox, Exception):
        raise mailbox
    steps.append("user removed, " + mailbox)
    after = api_snapshot(ctx)
    if not ctx.remote.available():
        # without --ssh the archived mailbox of the test user stays
        after["users"] = [u for u in after["users"] if u[0] != user]
    diff = [k for k in before if before[k] != after[k]]
    if diff:
        raise Fail("not the same afterwards: %s" % ", ".join(diff))
    return "%s; users, aliases, custom records and privacy the same afterwards" % ", ".join(steps)


def munin_conf_contact(ctx):
    # (contact lines before the host tree, "contacts" of the host tree)
    rc, out, err = ctx.remote.run("cat /etc/munin/munin.conf", sudo=True, timeout=60)
    if rc != 0:
        raise Fail("cannot read /etc/munin/munin.conf: %s" % (err or out).strip()[:120])
    contact, host, contacts = [], False, []
    for line in out.splitlines():
        if line.startswith("["):
            host = True
        elif line.startswith("contact.") and not host:
            contact.append(line)
        elif host and line.startswith("contacts "):
            contacts.append(line.split(None, 1)[1].strip())
    return contact, contacts, hashlib.sha256(out.encode()).hexdigest()


def munin_set(ctx, form, what):
    r = admin_api(ctx, "POST", "system/munin/alerts", form=form)
    api_expect(r, 200, "application/json", what)
    j = r.json()
    _need(j.get("status") == "ok" and j.get("config_current") is True, "%s: %s" % (what, r.text()[:150]))
    return j


def munin_test_mail_arrived(ctx, user, since_uidnext, timeout=90):
    # The test notification in user's INBOX: subject, marker, sender.
    deadline = time.time() + timeout
    while True:
        M = imap_login(ctx, user)
        try:
            uids = uid_search(M, "INBOX", "UID", "%d:*" % since_uidnext, "SUBJECT", '"Munin test notification"',
                              "HEADER", TEST_HEADER, "1", readonly=False)
            uids = [u for u in uids if int(u) >= since_uidnext]
            if uids:
                typ, data = M.uid("FETCH", uids[-1].decode(), "(BODY.PEEK[HEADER])")
                msg = parse_mail(data[0][1])
                M.uid("STORE", b",".join(uids).decode(), "+FLAGS.SILENT", "(\\Deleted)")
                M.expunge()
                return msg, len(uids)
        finally:
            M.logout()
        if time.time() > deadline:
            raise Fail("no test notification in %s's INBOX after %d s" % (user, timeout))
        time.sleep(5)


def c_api_munin_alerts(ctx):
    # The setting of Munin's alerts: invalid input refused, the three modes
    # in munin.conf (with --ssh), the test mail to a test mailbox (alice,
    # with TEST_USER_PW), and the old setting and file restored exactly.
    r = admin_api(ctx, "GET", "system/munin/alerts")
    api_expect(r, 200, "application/json", "GET munin alerts")
    orig = r.json()
    keep = {k: orig[k] for k in ("recipient", "address", "level")}
    conf0 = munin_conf_contact(ctx) if ctx.remote.available() else None
    notes = []
    try:
        for bad in ({"recipient": "custom", "address": "a@b.example\nBcc: x@example.com"},
                    {"recipient": "custom", "address": "-oQ/tmp/x@example.com"},
                    {"recipient": "custom", "address": "a b@example.com"},
                    {"recipient": "custom", "address": "$(id)@example.com"},
                    {"recipient": "custom", "address": ""},
                    {"recipient": "everyone"}, {"level": "info"}):
            r = admin_api(ctx, "POST", "system/munin/alerts", form=bad)
            _need(r.status == 400, "invalid %r accepted: HTTP %d" % (bad, r.status))
        now = admin_api(ctx, "GET", "system/munin/alerts").json()
        _need({k: now[k] for k in keep} == keep, "a refused value changed the setting")
        notes.append("7 invalid values refused")

        users = admin_api(ctx, "GET", "mail/users").text().split("\n")
        mailbox = ctx.user_pw and ctx.alice in users
        target = ctx.alice if mailbox else ctx.admin_user
        j = munin_set(ctx, {"recipient": "custom", "address": target, "level": "critical"}, "set custom/critical")
        _need(j["to"] == target and j["level"] == "critical", "custom: to=%s level=%s" % (j["to"], j["level"]))
        if conf0:
            contact, contacts, _ = munin_conf_contact(ctx)
            _need("contact.admin.command %s --to %s" % (MUNIN_NOTIFY, target) in contact, "custom: command %s" % contact[:1])
            _need(any(c.startswith("contact.admin.text ${if:cfields ") for c in contact), "critical: no contact.admin.text")
            _need(not any("always_send" in c for c in contact), "always_send set")
            _need(contacts == ["admin"], "custom: contacts %s" % contacts)
        if mailbox:
            M = imap_login(ctx, target)
            try:
                uidnext = folder_status(M, "INBOX")["uidnext"]
            finally:
                M.logout()
            r = admin_api(ctx, "POST", "system/munin/alerts/test")
            api_expect(r, 200, "application/json", "test mail")
            _need(r.json().get("to") == target, "test mail to %s" % r.json().get("to"))
            msg, n = munin_test_mail_arrived(ctx, target, uidnext)
            _need(n == 1, "%d test notifications arrived" % n)
            frm = msg.get("From", "")
            _need("administrator@" + ctx.hostname in frm, "test mail From: %s" % frm)
            _need(msg.get("Auto-Submitted") == "auto-generated", "test mail without Auto-Submitted")
            notes.append("test mail arrived in %s's INBOX (deleted)" % target.split("@")[0])
        else:
            notes.append("test mail not sent (no test mailbox %s)" % ctx.alice)

        j = munin_set(ctx, {"recipient": "off"}, "set off")
        _need(j["to"] is None and j["address"] == "", "off: to=%s address=%s" % (j["to"], j["address"]))
        r = admin_api(ctx, "POST", "system/munin/alerts/test")
        _need(r.status == 400, "test mail with alerts off: HTTP %d, expected 400" % r.status)
        if conf0:
            contact, contacts, _ = munin_conf_contact(ctx)
            _need(contact == [] and contacts == ["none"], "off: contact %s, contacts %s" % (contact[:1], contacts))

        j = munin_set(ctx, {"recipient": "admin", "level": "warning"}, "set admin/warning")
        _need(j["to"] == "administrator@" + ctx.hostname, "admin: to=%s" % j["to"])
        if conf0:
            contact, contacts, _ = munin_conf_contact(ctx)
            _need(contact == ["contact.admin.command %s" % MUNIN_NOTIFY] and contacts == ["admin"],
                  "admin/warning: contact %s, contacts %s" % (contact, contacts))
            notes.append("munin.conf right for custom/critical, off, admin/warning")
    finally:
        r = admin_api(ctx, "POST", "system/munin/alerts", form=keep)
    api_expect(r, 200, "application/json", "restore")
    after = admin_api(ctx, "GET", "system/munin/alerts").json()
    if after != orig:
        raise Fail("setting not restored: %s" % [k for k in orig if orig.get(k) != after.get(k)])
    if conf0 and munin_conf_contact(ctx)[2] != conf0[2]:
        raise Fail("munin.conf not restored byte for byte")
    notes.append("setting%s restored" % (" and munin.conf" if conf0 else ""))
    return "; ".join(notes)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="MIAB fork smoke test", formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__)
    ap.add_argument("--host", required=True, help="IP of the box as reachable from here / the jump host / the peer")
    ap.add_argument("--hostname", required=True, help="PRIMARY_HOSTNAME (TLS SNI, HTTP Host, SSHFP owner)")
    ap.add_argument("--mode", choices=["fresh", "migrated"], help="required, except with --send-test-mail")
    ap.add_argument("--manifest", help="seed manifest JSON (required for --mode migrated)")
    ap.add_argument("--domain", help="primary mail domain (default: manifest, else hostname without first label)")
    ap.add_argument("--seed2", help="second seed domain (default SEED2_DOMAIN, else seed2.example.net)")
    ap.add_argument("--seed3", help="third seed domain (default SEED3_DOMAIN, else seed3.example.net)")
    ap.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    ap.add_argument("--admin-user", help="admin e-mail (default FRESH_ADMIN / LEGACY_ADMIN by mode)")
    ap.add_argument("--admin-pw-var", help="env var holding the admin password (default FRESH_ADMIN_PW / LEGACY_ADMIN_PW)")
    ap.add_argument("--user-pw-var", default="TEST_USER_PW")
    ap.add_argument("--jump", help="ssh host to forward all ports through (needed from outside the test network)")
    ap.add_argument("--ssh", help="ssh host of the box for remote checks, or 'local'")
    ap.add_argument("--peer", help="IP of the peer MIAB as the target sees it (informational/safety)")
    ap.add_argument("--peer-ssh", help="ssh host of a second MIAB: port-25 mail and fail2ban attacks are sent from there")
    ap.add_argument("--provision", action="store_true", help="create alice/bob/carol, aliases and sieve scripts via API")
    ap.add_argument("--fail2ban", action="store_true", help="run the fail2ban ban/unban test (opt-in)")
    ap.add_argument("--fail2ban-force", action="store_true", help="allow attacks from here/the jump host")
    ap.add_argument("--fail2ban-count", type=int, default=26, help="failed logins per protocol (maxretry is 20)")
    ap.add_argument("--fail2ban-parallel", type=int, default=13,
                    help="concurrent attempts: Dovecot delays each failure (auth penalty), findtime is 30 s")
    ap.add_argument("--fail2ban-pause", type=int, default=32, help="seconds between jails (findtime is 30)")
    ap.add_argument("--greylist-wait", type=int, default=200)
    ap.add_argument("--greylist-retries", type=int, default=2)
    ap.add_argument("--deliver-timeout", type=int, default=150)
    ap.add_argument("--overquota-mb", type=float, default=12)
    ap.add_argument("--expect-nc", default="34", help="expected Nextcloud major version")
    ap.add_argument("--sa-learn-cmd", default="cd / && sudo -n -u spampd -H /usr/bin/sa-learn --dump magic")
    ap.add_argument("--skip", default="", help="comma list of groups to skip: " + ",".join(GROUPS))
    ap.add_argument("--only", default="", help="comma list of groups to run")
    ap.add_argument("--no-cleanup", action="store_true")
    ap.add_argument("--report", help="write the JSON report to this file as well")
    ap.add_argument("--send-test-mail", nargs=2, metavar=("FROM", "TO"),
                    help="only send one test mail (marked, so that the manifest comparison ignores it and its "
                         "automatic replies), then exit")
    ap.add_argument("--via", choices=["25", "465", "587"], default="25",
                    help="--send-test-mail: port 25 (from --peer-ssh if given) or submission as FROM (TEST_USER_PW)")
    ap.add_argument("--test-subject", help="--send-test-mail: the subject")
    args = ap.parse_args()

    if not args.mode and not args.send_test_mail:
        ap.error("--mode is required")
    if args.mode == "migrated" and not args.manifest:
        ap.error("--mode migrated needs --manifest")
    skip = {g for g in args.skip.split(",") if g}
    only = {g for g in args.only.split(",") if g}

    def want(group):
        if group == "fail2ban" and not args.fail2ban:
            return False
        if group == "provision" and not args.provision:
            return False
        if group == "migrated" and args.mode != "migrated":
            return False
        return group not in skip and (not only or group in only)

    env = load_env_file(args.env_file)
    env.update({k: v for k, v in os.environ.items() if k in (
        "TEST_USER_PW", "FRESH_ADMIN", "FRESH_ADMIN_PW", "LEGACY_ADMIN", "LEGACY_ADMIN_PW",
        "SEED2_DOMAIN", "SEED3_DOMAIN")})
    if args.admin_pw_var:
        env.setdefault(args.admin_pw_var, os.environ.get(args.admin_pw_var, ""))

    ctx = Ctx()
    ctx.args = args
    ctx.hostname = args.hostname
    ctx.manifest = None
    if args.manifest:
        with open(args.manifest, encoding="utf-8") as f:
            ctx.manifest = json.load(f)
    ctx.domain = args.domain or (ctx.manifest or {}).get("primary_domain") or args.hostname.split(".", 1)[1]
    ctx.seed2 = (ctx.manifest or {}).get("seed2", args.seed2 or env.get("SEED2_DOMAIN") or "seed2.example.net")
    ctx.seed3 = (ctx.manifest or {}).get("seed3", args.seed3 or env.get("SEED3_DOMAIN") or "seed3.example.net")
    ctx.alice = "alice@" + ctx.domain
    ctx.bob = "bob@" + ctx.seed2
    ctx.carol = "carol@" + ctx.domain
    ctx.user_pw = env.get(args.user_pw_var, "")
    prefix = "FRESH" if args.mode == "fresh" else "LEGACY"
    ctx.admin_user = args.admin_user or env.get(prefix + "_ADMIN")
    ctx.admin_pw = env.get(args.admin_pw_var or prefix + "_ADMIN_PW")
    ctx.admin_auth = None
    ctx.nc_ids = {}
    ctx.tok = uuid.uuid4().hex[:10]
    ctx.remote = Remote(args.ssh)
    SECRETS.update({ctx.user_pw, ctx.admin_pw or ""})
    if not ctx.user_pw and not (args.send_test_mail and args.via == "25"):
        print("TEST_USER_PW missing (env or --env-file %s)" % args.env_file, file=sys.stderr)
        return 2

    print("MIAB fork smoke test: host=%s hostname=%s mode=%s domain=%s token=%s"
          % (args.host, args.hostname, args.mode, ctx.domain, ctx.tok))
    try:
        ctx.net = Net(args.host, args.hostname, args.jump)
    except Exception as e:
        print("cannot set up network path: %s" % redact(e), file=sys.stderr)
        return 2
    if args.send_test_mail:
        try:
            return send_test_mail(ctx)
        finally:
            ctx.net.close()

    if want("admin") or want("api") or want("provision") or want("migrated") or want("dns"):
        print("== admin")
        run_check("admin-api-login", c_admin_login, ctx)
    if want("provision"):
        print("== provision")
        run_check("provision-test-accounts", c_provision, ctx)
    if want("login"):
        print("== login")
        run_check("imaps-993-login", c_imap_login, ctx)
        run_check("pop3s-995-login", c_pop3_login, ctx)
        run_check("submission-465-login", c_sub465, ctx)
        run_check("submission-587-login", c_sub587, ctx)
        run_check("managesieve-4190-login", c_sieve_login, ctx)
        run_check("mail-log-logins", c_mail_log_logins, ctx)
        run_check("services-enabled", c_services_enabled, ctx)
    if want("migrated"):
        print("== migrated (manifest comparison, before new mail)")
        run_check("mig-users-aliases", c_mig_users_aliases, ctx)
        for user in sorted(ctx.manifest.get("users", {})):
            short = user.split("@")[0]
            run_check("mig-pop3-uidl-" + short, c_mig_pop3, ctx, user)
            run_check("mig-folders-" + short, c_mig_folders, ctx, user)
        run_check("mig-sieve-active", c_mig_sieve, ctx)
        run_check("mig-sa-learn-counts", c_mig_salearn, ctx)
        run_check("mig-nextcloud-items", c_mig_nextcloud, ctx)
        run_check("mig-dns-custom-txt", c_mig_dns_custom, ctx)
        run_check("mig-dkim-key", c_mig_dkim, ctx)
        run_check("mig-roundcube-identity", c_mig_roundcube_identity, ctx)
    if want("admin"):
        run_check("admin-api-tmp-user-alias", c_admin_tmp_user_alias, ctx)
        run_check("admin-backup-status", c_backup_status, ctx)
        run_check("admin-backup-saved", c_backup_saved, ctx)
        run_check("admin-fail2ban-status", c_fail2ban_api, ctx)
        run_check("admin-fail2ban-settings", c_fail2ban_settings_roundtrip, ctx)
        run_check("admin-fail2ban-report", c_fail2ban_report, ctx)
        run_check("admin-fail2ban-filters", c_fail2ban_filters, ctx)
        run_check("admin-fail2ban-panel", c_fail2ban_panel, ctx)
    if want("api"):
        print("== api (management API as api/mailinabox.yml documents it)")
        run_check("api-auth", c_api_auth, ctx)
        run_check("api-read-only", c_api_read_only, ctx)
        run_check("api-write-roundtrip", c_api_write_roundtrip, ctx)
        run_check("api-munin-alerts", c_api_munin_alerts, ctx)
    if want("dns"):
        print("== dns")
        for zone in (ctx.domain, ctx.seed2, ctx.seed3):
            run_check("dnssec-" + zone, c_dnssec, ctx, zone)
            run_check("mx-dkim-" + zone, c_mx_dkim, ctx, zone)
        run_check("sshfp-vs-hostkeys", c_sshfp, ctx)
        if args.mode == "fresh":
            run_check("dns-custom-roundtrip", c_dns_custom_roundtrip, ctx)
    if want("web"):
        print("== web")
        run_check("nextcloud-status", c_nc_status, ctx)
        run_check("nextcloud-caldav-propfind", c_nc_dav, ctx, "caldav")
        run_check("nextcloud-carddav-propfind", c_nc_dav, ctx, "carddav")
        run_check("nextcloud-webdav-propfind", c_nc_dav, ctx, "webdav")
        run_check("nextcloud-share-scope", c_nc_share_scope, ctx)
        run_check("roundcube-login", c_roundcube, ctx)
        run_check("zpush-options", c_zpush_options, ctx)
        run_check("zpush-autodiscover", c_zpush_autodiscover, ctx)
    if want("activesync"):
        # Quick enough to run right after a setup run: --only activesync
        print("== activesync (calendars and contacts through Z-Push and Nextcloud)")
        run_check("nextcloud-bruteforce-loopback", c_nc_bruteforce_loopback, ctx)
        run_check("nextcloud-forwarded-for", c_nc_forwarded_for, ctx)
        run_check("zpush-sync", c_zpush_sync, ctx)
    if want("mail"):
        print("== mail flow")
        st, _ = run_check("mail-flow-send", c_mail_flow, ctx)
        run_check("smtp25-direct-delivery", c_delivery, ctx, "direct", "INBOX", "direct mail")
        run_check("smtp25-alias", c_delivery, ctx, "alias", "INBOX", "info@ alias")
        run_check("smtp25-catch-all", c_delivery, ctx, "catchall", "INBOX", "catch-all @seed2")
        run_check("smtp25-domain-alias", c_delivery, ctx, "domalias_ca", "INBOX", "domain alias @seed3")
        run_check("smtp25-domain-alias-user", c_delivery, ctx, "domalias_user", "INBOX", "bob@seed3")
        run_check("no-quota-reject-for-aliases", c_no_quota_reject_alias, ctx)
        run_check("overquota-reject-bob", c_overquota, ctx)
        run_check("imap-getquotaroot-bob", c_quotaroot, ctx)
        run_check("greylist-bypass-config", c_greylist_bypass, ctx)
        run_check("root-mail-alias", c_root_mail, ctx)
        run_check("munin-alert-contact", c_munin_contact, ctx)
        run_check("sieve-filter-filtered", c_delivery, ctx, "filtered", "Filtered", "[filtered] mail")
        run_check("sieve-vacation-reply", c_vacation, ctx)
        run_check("sieve-vacation-no-phantom-folders", c_vacation_no_phantom_folders, ctx)
        run_check("submission-465-delivery", c_submission_delivery, ctx, "s465", "465 submission")
        run_check("submission-587-delivery", c_submission_delivery, ctx, "s587", "587 submission")
        run_check("permitted-sender-allowed", c_submission_delivery, ctx, "team_ok", "alice as team@")
        run_check("permitted-sender-denied", c_sender_denied, ctx)
    if want("imapsieve"):
        print("== imapsieve")
        run_check("imapsieve-move-run", c_imapsieve, ctx)
        run_check("imapsieve-spam-learn", c_imapsieve_result, ctx, "spam")
        run_check("imapsieve-ham-learn", c_imapsieve_result, ctx, "ham")
        run_check("fts-search", c_fts, ctx)
    if not args.no_cleanup and (want("mail") or want("imapsieve")):
        run_check("cleanup-test-mail", c_cleanup, ctx)
    if want("fail2ban"):
        print("== fail2ban (bans and unbans the attacking IP)")
        run_check("fail2ban-adaptive-toggle", c_fail2ban_adaptive_toggle, ctx)
        st, _ = run_check("fail2ban-prepare", f2b_prepare, ctx)
        if st == "PASS":
            # The slow jails (on by default) count the failures of all
            # Dovecot (SMTP) protocols together over hours, so after the
            # first protocol they can ban the source before the fast jail.
            dovecot = ["dovecot", "miab-slow-dovecot"]
            smtp = ["postfix-sasl", "miab-slow-smtp"]
            run_check("fail2ban-log-rotation", c_fail2ban_log_rotation, ctx)
            run_check("fail2ban-imap", c_fail2ban, ctx, "imap", dovecot, 993)
            run_check("fail2ban-pop3", c_fail2ban, ctx, "pop3", dovecot, 995)
            run_check("fail2ban-managesieve", c_fail2ban, ctx, "managesieve", dovecot, 4190)
            run_check("fail2ban-smtp587", c_fail2ban, ctx, "smtp587", ["miab-postfix587"] + smtp, 587)
            run_check("fail2ban-smtp465", c_fail2ban, ctx, "smtp465", ["miab-postfix465"] + smtp, 465)

    ctx.net.close()
    summary = {}
    for r in RESULTS:
        summary[r["status"]] = summary.get(r["status"], 0) + 1
    report = {"meta": {"host": args.host, "hostname": args.hostname, "mode": args.mode, "domain": ctx.domain,
                       "token": ctx.tok, "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                       "path": "peer " + args.peer_ssh if args.peer_ssh else ("jump " + args.jump if args.jump else "direct")},
              "summary": summary, "results": RESULTS}
    print()
    print("%-4s  %-38s %s" % ("STAT", "CHECK", "DETAIL"))
    print("-" * 110)
    for r in RESULTS:
        print("%-4s  %-38s %s" % (r["status"], r["check"], r["detail"][:200]))
    print("-" * 110)
    print("summary: " + ", ".join("%s=%d" % kv for kv in sorted(summary.items())))
    text = redact(json.dumps(report, indent=2, ensure_ascii=False))
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    print("JSON-REPORT-BEGIN")
    print(text)
    print("JSON-REPORT-END")
    return 1 if summary.get("FAIL") else 0


if __name__ == "__main__":
    sys.exit(main())
