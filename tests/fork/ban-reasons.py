#!/usr/bin/env python3
"""Checks the reasons of bans in management/fail2ban_admin.py (System > Intrusion Protection).

No box needed. Each case is a log line of a kind that a jail's filter
matches, with a user name that is an account of the box or not. A name that
is not an account must not appear anywhere in the text shown (apart from
case), also where the line repeats it (Z-Push's brackets, Nextcloud's URL),
also when it has a space (sshd, nginx and Postfix log it so), and a line of
Nextcloud's log that is not valid JSON shows no more than its login message;
an account is shown and named as the line's account. A short name hits no
other word of the line. Also the summary of a
ban (_reason) from the data that fail2ban keeps, and a ban by hand.

Usage: python3 -I tests/fork/ban-reasons.py
Exit code 0 when every check passed.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "management"))
import fail2ban_admin as f  # noqa: E402

KNOWN = {"bob@example.com", "carol@example.com"}
SECRET = "Hunter2-Secret"

def nc(user, url="/cloud/remote.php/dav/principals/users/%s/", message=None, ua="SomeDAVClient/1.0 (%s)"):
    return json.dumps({
        "reqId": "abc", "level": 2, "time": "2026-10-26 13:00:00", "remoteAddr": "192.0.2.1", "user": "--",
        "app": "core", "method": "PROPFIND", "url": url % user if "%s" in url else url, "scriptName": "/cloud/remote.php",
        "message": message if message is not None else "Login failed: '%s' (Remote IP: '192.0.2.1')" % user,
        "userAgent": ua % user if "%s" in ua else ua, "version": "34.0.6.2",
    }).encode()

# (description, line, secret that must not be shown or None, expected account or None)
CASES = [
    ("dovecot, unknown name", b"2026-10-26T13:00:00+01:00 box dovecot: imap-login: Login aborted: Logged out (auth failed, 1 attempts in 2 secs) (auth_failed): user=<%s>, method=PLAIN, rip=192.0.2.9, lip=10.0.0.1, TLS, session=<x>" % SECRET.encode(), SECRET, None),
    ("dovecot, account", b"2026-10-26T13:00:00+01:00 box dovecot: imap-login: Login aborted: Logged out (auth failed, 1 attempts in 2 secs) (auth_failed): user=<bob@example.com>, method=PLAIN, rip=192.0.2.9, lip=10.0.0.1, TLS, session=<x>", None, "bob@example.com"),
    ("dovecot, tried to use", b"2026-10-26T13:00:00+01:00 box dovecot: imap-login: Login aborted: Logged out (tried to use disallowed plaintext auth) (tls_required): user=<%s>, rip=192.0.2.9, lip=10.0.0.1, session=<x>" % SECRET.encode(), SECRET, None),
    ("dovecot, no auth attempts with a user", b"2026-10-26T13:00:00+01:00 box dovecot: pop3-login: Disconnected (no auth attempts in 0 secs): user=<%s>, rip=192.0.2.9, lip=10.0.0.1, session=<x>" % SECRET.encode(), SECRET, None),
    ("smtp, unknown name", b"2026-10-26T13:00:00+01:00 box postfix/submission/smtpd[123]: warning: unknown[192.0.2.1]: SASL LOGIN authentication failed: (reason), sasl_username=%s" % SECRET.encode(), SECRET, None),
    ("smtp, account", b"2026-10-26T13:00:00+01:00 box postfix/submission/smtpd[123]: warning: unknown[192.0.2.1]: SASL LOGIN authentication failed: (reason), sasl_username=bob@example.com", None, "bob@example.com"),
    ("z-push, unknown name in brackets and message", b"26/10/2026 13:00:00 [12345] [WARN] [%s] Failed to authenticate user '%s' from IP 192.0.2.1." % (SECRET.encode(), SECRET.lower().encode()), SECRET, None),
    ("z-push, account with an unknown user of the request", b"26/10/2026 13:00:00 [12345] [WARN] [bob@example.com#%s] Failed to authenticate user 'bob@example.com' from IP 192.0.2.1." % SECRET.encode(), SECRET, "bob@example.com"),
    ("autodiscover, unknown address", b"26/10/2026 13:00:00 [12345] [WARN] [#unknown] Unable to complete autodiscover because login failed for user with email '%s@example.net' from IP 192.0.2.1." % SECRET.encode(), SECRET, None),
    ("roundcube, unknown name", b"[26-Oct-2026 13:00:00 +0100]: <abc> IMAP Error: Login failed for %s against localhost from 192.0.2.1. AUTHENTICATE PLAIN: Authentication failed. in /x.php on line 1 (POST /mail/?_task=login&_action=login)" % SECRET.encode(), SECRET, None),
    ("munin, unknown Basic user", b'192.0.2.1 - %s [26/Oct/2026:13:00:00 +0100] "GET /admin/munin/ HTTP/2.0" 401 0 "-" "curl"' % SECRET.encode(), SECRET, None),
    ("sshd, invalid user", b"2026-10-26T13:00:00+01:00 box sshd-session[1]: Invalid user %s from 192.0.2.1 port 5555" % SECRET.encode(), SECRET, None),
    ("nextcloud, unknown name (URL and user agent)", nc(SECRET), SECRET, None),
    ("nextcloud, account", nc("bob@example.com"), None, "bob@example.com"),
    ("nextcloud, other message with a name in the URL", nc(SECRET, message="Trusted domain error.", ua="curl/8"), SECRET, None),
    ("sshd, invalid user with a space", b"2026-10-26T13:00:00+01:00 box sshd-session[1]: Invalid user my %s from 192.0.2.1 port 5555" % SECRET.encode(), SECRET, None),
    ("sshd, failed password of an invalid user with a space", b"2026-10-26T13:00:00+01:00 box sshd-session[1]: Failed password for invalid user my %s from 192.0.2.1 port 5555 ssh2" % SECRET.encode(), SECRET, None),
    ("munin, Basic user with a space", b'192.0.2.1 - my %s [26/Oct/2026:13:00:00 +0100] "GET /admin/munin/ HTTP/2.0" 401 0 "-" "curl"' % SECRET.encode(), SECRET, None),
    ("smtp, name with a space", b"2026-10-26T13:00:00+01:00 box postfix/submission/smtpd[123]: warning: unknown[192.0.2.1]: SASL LOGIN authentication failed: (reason), sasl_username=my %s" % SECRET.encode(), SECRET, None),
    ("nextcloud, not valid JSON, unknown name", b'{"reqId":"abc","level":2,"time":"2026-10-26 13:00:00","remoteAddr":"192.0.2.1","url":"/cloud/remote.php/dav/principals/users/%s/","message":"Login failed: \'%s\' (Remote IP: \'192.0.2.1\')","userAgent":"x' % (SECRET.encode(), SECRET.encode()), SECRET, None),
    ("nextcloud, not valid JSON, account", b'{"reqId":"abc","level":2,"time":"2026-10-26 13:00:00","remoteAddr":"192.0.2.1","message":"Login failed: \'bob@example.com\' (Remote IP: \'192.0.2.1\')","userAgent":"x', None, "bob@example.com"),
    ("nextcloud, not valid JSON, no login message", b'{"reqId":"abc","level":2,"time":"2026-10-26 13:00:00","url":"/cloud/remote.php/dav/principals/users/%s/","message":"something' % SECRET.encode(), SECRET, None),
    ("name that is in the replacement text", b"2026-10-26T13:00:00+01:00 box dovecot: imap-login: Login aborted: Logged out (auth failed, 1 attempts in 2 secs) (auth_failed): user=<name>, method=PLAIN, rip=192.0.2.9, lip=10.0.0.1, TLS, session=<x>", None, None),
    ("short unknown name", b"2026-10-26T13:00:00+01:00 box dovecot: imap-login: Login aborted: Logged out (auth failed, 1 attempts in 2 secs) (auth_failed): user=<1>, method=PLAIN, rip=192.0.2.9, lip=10.0.0.1, TLS, session=<x>", None, None),
]

def main():
    bad = 0
    for desc, line, secret, account in CASES:
        text, acc, masked = f._reason_line(line, KNOWN)
        errs = []
        if secret and secret.lower() in text.lower():
            errs.append("the name is shown")
        if secret and not masked and "other message" not in desc:
            errs.append("not marked as masked")
        if acc != account:
            errs.append("account %r, expected %r" % (acc, account))
        if account and account not in text:
            errs.append("the account is not shown")
        if desc == "short unknown name" and ("2026-10-26T13:00:00" not in text or "user=<[unknown name]>" not in text or "(auth failed, 1 attempts" not in text):
            errs.append("a short name garbles the line: %s" % text)
        if desc == "name that is in the replacement text" and ("user=<[unknown name]>" not in text or "[[" in text):
            errs.append("the replacement was replaced again: %s" % text)
        if desc.startswith("nextcloud, not valid JSON") and "/principals/" in text:
            errs.append("the URL is shown: %s" % text)
        if "with a space" in desc and "my " in text.lower():
            errs.append("part of the name is shown: %s" % text)
        if desc == "autodiscover, unknown address" and "[#unknown]" not in text:
            errs.append("Autodiscover's placeholder [#unknown] was changed: %s" % text)
        if desc == "nextcloud, account" and "/principals/users/bob@example.com/" not in text:
            errs.append("the URL of an account is missing")
        print("%s  %-50s %s" % ("FAIL" if errs else "ok  ", desc, "; ".join(errs) or text[:90]))
        bad += bool(errs)

    # Long lines (16 KB) of the kinds that made a regex take time growing
    # with the square of the line: each must take well under 0.1 s, in the
    # reasons and in the failed-login report's SMTP regex.
    import time
    pre = b"2026-10-26T13:00:00+01:00 box "
    n = 16000
    long_lines = {
        "sasl_username with a run of spaces": pre + b"postfix/submission/smtpd[1]: warning: unknown[192.0.2.1]: SASL LOGIN authentication failed: (r), sasl_username=x" + b" " * n + b"y",
        "SMTP failure with a run of spaces": pre + b"postfix/submission/smtpd[1]: warning: unknown[192.0.2.1]: SASL LOGIN authentication failed: " + b" " * n + b"y",
        "many user=<": pre + b"dovecot: imap-login: Login aborted: (auth failed) " + b"user=<" * (n // 6) + b"x",
        "user=< with a run of spaces": pre + b"dovecot: imap-login: Login aborted: Logged out (auth failed, 1 attempts in 2 secs) (auth_failed): user=<" + b" " * n + b">",
        "invalid user with many from": pre + b"sshd-session[1]: Invalid user " + b" from " * (n // 6) + b"x",
        "nginx with many brackets": b"192.0.2.1 - " + b" [" * (n // 2) + b"x",
        "z-push with many escapes": b"26/10/2026 13:00:00 [1] [WARN] [" + b"\\]" * (n // 2) + b"x",
    }
    for desc, line in long_lines.items():
        t = time.time()
        f._reason_line(line, KNOWN)
        m = f.RE_SMTP.search(line)
        if m:
            f.smtp_user(m)
        d = time.time() - t
        ok = d < 0.1
        print("%s  %-50s %.3f s" % ("ok  " if ok else "FAIL", "long line: " + desc, d))
        bad += not ok
    m = f.RE_SMTP.search(b"postfix/submission/smtpd[1]: warning: unknown[192.0.2.1]: SASL LOGIN authentication failed: (r), sasl_username=my name  \n")
    ok = m is not None and f.smtp_user(m)[0] == b"my name"
    print("%s  %-50s %s" % ("ok  " if ok else "FAIL", "SMTP user of the failed-login report", f.smtp_user(m)[0] if m else None))
    bad += not ok

    data = json.dumps({"matches": [CASES[0][1].decode(), CASES[1][1].decode(), CASES[6][1].decode()], "failures": 20}).encode()
    r = f._reason(data, KNOWN)
    ok = (r["failures"] == 20 and r["accounts"] == ["bob@example.com"] and r["unknown_names"] == 2
          and not r["manual"] and len(r["lines"]) == 3 and not any(SECRET.lower() in l.lower() for l in r["lines"]))
    print("%s  %-50s %s" % ("ok  " if ok else "FAIL", "summary of a ban", r if not ok else ""))
    bad += not ok
    r = f._reason(b'{"matches": [], "failures": 0}', KNOWN)
    ok = r["manual"] and r["lines"] == [] and r["failures"] == 0
    print("%s  %-50s %s" % ("ok  " if ok else "FAIL", "ban by hand", r if not ok else ""))
    bad += not ok
    print("%d of %d checks failed" % (bad, len(CASES) + 2 + len(long_lines) + 1))
    return 1 if bad else 0

if __name__ == "__main__":
    sys.exit(main())
