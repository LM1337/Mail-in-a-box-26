#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Minimal Exchange ActiveSync client (protocol 14.0) for the fork's tests --
python3 stdlib only. Used by smoke.py (zpush-sync) and client-load.py, and on
its own:

    EAS_USER=alice@example.net EAS_PW=... tests/fork/eas.py box.example.net \\
        [--connect 192.0.2.11] [--ping SECONDS]

It does what a phone does on a new account: Provision (twice, the second
acknowledges the policy), FolderSync, an initial Sync and a Sync with
GetChanges of the default calendar and the contacts folder, and optionally a
Ping (the long poll) on both. Z-Push serves calendars and contacts from
Nextcloud over CalDAV/CardDAV (from 127.0.0.1), with the user's password, so
this also exercises Nextcloud's login of the box's own services.

The password is read from the environment and never printed. Exit code 0 if
every step answered with status 1, 1 otherwise.
"""

import argparse
import base64
import http.client
import os
import socket
import ssl
import sys
import time
import urllib.parse

# WBXML code pages (MS-ASWBXML), only the tags these requests and their
# answers use. Unknown tags decode as "page:token".
PAGES = {
    0: {0x05: "Sync", 0x06: "Responses", 0x07: "Add", 0x08: "Change", 0x09: "Delete", 0x0A: "Fetch",
        0x0B: "SyncKey", 0x0C: "ClientId", 0x0D: "ServerId", 0x0E: "Status", 0x0F: "Collection",
        0x10: "Class", 0x12: "CollectionId", 0x13: "GetChanges", 0x14: "MoreAvailable", 0x15: "WindowSize",
        0x16: "Commands", 0x17: "Options", 0x18: "FilterType", 0x1C: "Collections", 0x1D: "ApplicationData",
        0x1E: "DeletesAsMoves", 0x20: "Supported", 0x21: "SoftDelete", 0x22: "MIMESupport",
        0x23: "MIMETruncation", 0x24: "Wait", 0x25: "Limit", 0x26: "Partial"},
    7: {0x05: "Folders", 0x06: "Folder", 0x07: "DisplayName", 0x08: "ServerId", 0x09: "ParentId", 0x0A: "Type",
        0x0C: "Status", 0x0E: "Changes", 0x0F: "Add", 0x10: "Delete", 0x11: "Update", 0x12: "SyncKey",
        0x16: "FolderSync", 0x17: "Count"},
    13: {0x05: "Ping", 0x06: "AutdState", 0x07: "Status", 0x08: "HeartbeatInterval", 0x09: "Folders",
         0x0A: "Folder", 0x0B: "Id", 0x0C: "Class", 0x0D: "MaxFolders"},
    14: {0x05: "Provision", 0x06: "Policies", 0x07: "Policy", 0x08: "PolicyType", 0x09: "PolicyKey",
         0x0A: "Data", 0x0B: "Status", 0x0C: "RemoteWipe", 0x0D: "EASProvisionDoc"},
}
TOKENS = {}
for _page, _tags in PAGES.items():
    for _tok, _name in _tags.items():
        TOKENS.setdefault(_name, {})[_page] = _tok

# FolderSync folder types (MS-ASCMD 2.2.3.186.3)
TYPE_CALENDAR = "8"
TYPE_CONTACTS = "9"
TYPE_USER_CALENDAR = "13"
TYPE_USER_CONTACTS = "14"
CLASS_OF_TYPE = {TYPE_CALENDAR: "Calendar", TYPE_USER_CALENDAR: "Calendar",
                 TYPE_CONTACTS: "Contacts", TYPE_USER_CONTACTS: "Contacts"}


def encode(page, tree):
    """WBXML for tree = (name, None | str | [children]); names are looked up
    in `page` first, then in any page."""
    out = bytearray(b"\x03\x01\x6a\x00")  # WBXML 1.3, unknown public id, UTF-8, no string table
    cur = [0]

    def node(n):
        name, val = n
        pages = TOKENS[name]
        p = page if page in pages else sorted(pages)[0]
        if p != cur[0]:
            out.extend(bytes([0x00, p]))
            cur[0] = p
        tok = pages[p]
        if val is None:
            out.append(tok)
            return
        out.append(tok | 0x40)
        if isinstance(val, str):
            out.extend(b"\x03" + val.encode("utf-8") + b"\x00")
        else:
            for c in val:
                node(c)
        out.append(0x01)

    node(tree)
    return bytes(out)


def decode(data):
    """Tree ("root", [children]) of (name, [children | str | bytes])."""
    i = 0

    def mbint():
        nonlocal i
        v = 0
        while True:
            b = data[i]
            i += 1
            v = (v << 7) | (b & 0x7F)
            if not b & 0x80:
                return v

    i = 1  # version
    mbint()  # public id
    mbint()  # charset
    n = mbint()  # length of the string table (none is used)
    i += n
    page = 0
    root = ("root", [])
    stack = [root]
    while i < len(data):
        b = data[i]
        i += 1
        if b == 0x00:
            page = data[i]
            i += 1
        elif b == 0x01:
            if len(stack) > 1:
                stack.pop()
        elif b == 0x03:
            j = data.index(b"\x00", i)
            stack[-1][1].append(data[i:j].decode("utf-8", "replace"))
            i = j + 1
        elif b == 0xC3:
            n = mbint()
            stack[-1][1].append(bytes(data[i:i + n]))
            i += n
        else:
            name = PAGES.get(page, {}).get(b & 0x3F, "%d:%#x" % (page, b & 0x3F))
            el = (name, [])
            stack[-1][1].append(el)
            if b & 0x40:
                stack.append(el)
    return root


def find(tree, name):
    if isinstance(tree, tuple):
        if tree[0] == name:
            yield tree
        for c in tree[1]:
            yield from find(c, name)


def text(el):
    return "".join(c for c in el[1] if isinstance(c, str))


def first(tree, name, default=None):
    for el in find(tree, name) if tree else ():
        return text(el)
    return default


class _HTTPS(http.client.HTTPSConnection):
    # Connects to addr (the box, a tunnel or 127.0.0.1) with the box's name as SNI.
    def __init__(self, addr, sni, timeout):
        super().__init__(addr[0], addr[1], context=ssl_ctx(), timeout=timeout)
        self._sni = sni

    def connect(self):
        http.client.HTTPConnection.connect(self)
        self.sock = ssl_ctx().wrap_socket(self.sock, server_hostname=self._sni)


def ssl_ctx():
    c = ssl.create_default_context()
    c.check_hostname = False
    c.verify_mode = ssl.CERT_NONE  # test boxes use self-signed certificates
    return c


class EASError(Exception):
    """A request that did not succeed. kind: "auth" (HTTP 401: the server
    refused the login), "unavailable" (no connection, HTTP 5xx), "disconnect"
    (the connection broke during a request), "status" (an EAS status other
    than success), "error" (anything else)."""

    def __init__(self, kind, msg):
        super().__init__(msg)
        self.kind = kind


def classify_exception(e):
    if isinstance(e, EASError):
        return e.kind
    if isinstance(e, (ConnectionRefusedError, socket.gaierror)):
        return "unavailable"
    if isinstance(e, (ConnectionResetError, BrokenPipeError, http.client.RemoteDisconnected,
                      http.client.IncompleteRead, ssl.SSLError)):
        return "disconnect"
    if isinstance(e, (TimeoutError, socket.timeout)):
        return "disconnect"
    if isinstance(e, OSError):
        return "unavailable"
    return "error"


class Client:
    def __init__(self, hostname, user, password, device_id, addr=None, timeout=60,
                 device_type="SmartPhone", user_agent="miab-fork-eas/1"):
        self.hostname = hostname
        self.user = user
        self.password = password
        self.device_id = device_id
        self.addr = addr or (hostname, 443)
        self.timeout = timeout
        self.device_type = device_type
        self.user_agent = user_agent
        self.policy_key = "0"
        self.folders = []
        self.sync_keys = {}

    def request(self, cmd, body, timeout=None):
        """POST one command; returns the decoded answer (or None if empty)."""
        conn = _HTTPS(self.addr, self.hostname, timeout or self.timeout)
        auth = base64.b64encode(("%s:%s" % (self.user, self.password)).encode()).decode()
        q = "/Microsoft-Server-ActiveSync?Cmd=%s&User=%s&DeviceId=%s&DeviceType=%s" % (
            cmd, urllib.parse.quote(self.user), self.device_id, self.device_type)
        try:
            conn.request("POST", q, body=body, headers={
                "Host": self.hostname, "Authorization": "Basic " + auth, "MS-ASProtocolVersion": "14.0",
                "Content-Type": "application/vnd.ms-sync.wbxml", "X-MS-PolicyKey": self.policy_key,
                "User-Agent": self.user_agent})
            r = conn.getresponse()
            data = r.read()
        finally:
            conn.close()
        if r.status == 401:
            raise EASError("auth", "%s: HTTP 401 (login refused)" % cmd)
        if r.status in (502, 503, 504):
            raise EASError("unavailable", "%s: HTTP %d" % (cmd, r.status))
        if r.status != 200:
            raise EASError("error", "%s: HTTP %d" % (cmd, r.status))
        return decode(data) if data else None

    def provision(self):
        pt = "MS-EAS-Provisioning-WBXML"
        t = self.request("Provision", encode(14, ("Provision", [("Policies", [("Policy", [("PolicyType", pt)])])])))
        key = first(t, "PolicyKey")
        if not key:
            raise EASError("status", "Provision: no policy key (status %s)" % first(t, "Status"))
        self.policy_key = key
        t = self.request("Provision", encode(14, ("Provision", [("Policies", [("Policy", [
            ("PolicyType", pt), ("PolicyKey", key), ("Status", "1")])])])))
        key = first(t, "PolicyKey")
        if key:
            self.policy_key = key
        return self.policy_key

    def folder_sync(self):
        t = self.request("FolderSync", encode(7, ("FolderSync", [("SyncKey", "0")])))
        st = first(t, "Status")
        if st != "1":
            raise EASError("status", "FolderSync status %s" % st)
        self.folders = []
        for f in find(t, "Add"):
            self.folders.append({c[0]: text(c) for c in f[1] if isinstance(c, tuple)})
        return self.folders

    def folder(self, ftype):
        for f in self.folders:
            if f.get("Type") == ftype:
                return f
        return None

    def folders_of(self, *ftypes):
        return [f for f in self.folders if f.get("Type") in ftypes]

    def sync(self, folder_ids, rounds=20):
        """Sync each folder: the initial Sync (SyncKey 0) on the first call,
        then GetChanges until nothing more is available. Returns {folder_id:
        [the Add commands]}. Later calls fetch only the changes."""
        return {fid: self._sync_folder(fid, rounds) for fid in folder_ids}

    def _sync_folder(self, fid, rounds):
        adds = []
        key = self.sync_keys.get(fid, "0")
        for _ in range(rounds):
            c = [("SyncKey", key), ("CollectionId", fid)]
            if key != "0":
                c.append(("GetChanges", None))
            t = self.request("Sync", encode(0, ("Sync", [("Collections", [("Collection", c)])])))
            if t is None:
                break  # an empty answer: no changes
            col = next(find(t, "Collection"), None)
            st = first(col, "Status") if col else first(t, "Status")
            if st != "1":
                raise EASError("status", "Sync of folder %s: status %s" % (fid, st))
            adds.extend(find(col, "Add"))
            initial = key == "0"
            key = first(col, "SyncKey") or key
            self.sync_keys[fid] = key
            if not initial and not any(True for _ in find(col, "MoreAvailable")):
                break
        return adds

    def ping(self, folders, heartbeat):
        """folders: [(id, class)]. Returns the Ping status (1: no changes in
        the heartbeat, 2: changes)."""
        t = self.request("Ping", encode(13, ("Ping", [("HeartbeatInterval", str(heartbeat)), ("Folders", [
            ("Folder", [("Id", fid), ("Class", cls)]) for fid, cls in folders])])), timeout=heartbeat + 120)
        st = first(t, "Status")
        if st not in ("1", "2"):
            raise EASError("status", "Ping status %s" % st)
        return st


def flat_strings(el):
    out = []
    for c in el[1]:
        if isinstance(c, str):
            out.append(c)
        elif isinstance(c, tuple):
            out.extend(flat_strings(c))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("hostname", help="the box's name (TLS SNI and HTTP Host)")
    ap.add_argument("--connect", help="address to connect to (default: the hostname)")
    ap.add_argument("--port", type=int, default=443)
    ap.add_argument("--device-id", default="miabforktest%04d" % (os.getpid() % 10000))
    ap.add_argument("--ping", type=int, default=0, metavar="SECONDS", help="also run one Ping with this heartbeat")
    args = ap.parse_args()
    user, pw = os.environ.get("EAS_USER"), os.environ.get("EAS_PW")
    if not user or not pw:
        print("EAS_USER and EAS_PW must be set", file=sys.stderr)
        return 2
    c = Client(args.hostname, user, pw, args.device_id, addr=(args.connect or args.hostname, args.port))

    def log(*a):
        print(time.strftime("%H:%M:%S"), *a, flush=True)

    try:
        log("provision", c.provision() != "0")
        folders = c.folder_sync()
        log("foldersync", [(f.get("DisplayName"), f.get("Type")) for f in folders])
        cals = c.folders_of(TYPE_CALENDAR, TYPE_USER_CALENDAR)
        cons = c.folders_of(TYPE_CONTACTS, TYPE_USER_CONTACTS)
        if not cals or not cons:
            log("missing folders: %d calendar, %d contact folders" % (len(cals), len(cons)))
            return 1
        adds = c.sync([f["ServerId"] for f in cals + cons])
        log("sync", {fid: len(v) for fid, v in adds.items()})
        if args.ping:
            log("ping", c.ping([(f["ServerId"], CLASS_OF_TYPE[f["Type"]]) for f in cals + cons], args.ping))
    except Exception as e:
        log("failed (%s): %s" % (classify_exception(e), e))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
