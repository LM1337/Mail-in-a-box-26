#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TEST ENVIRONMENT ONLY. Moves a test mail of its own into Spam and back, as a
user's mail client does, so that IMAPSieve runs sa-learn for the user (the
state that a box has after its users trained the spam filter; B155 created a
folder "spamassassin" then).

The seeded mails are left alone: a mail that is moved gets a new UID in
the folder it comes back to, and so a new POP3 UIDL, which the manifest of
tests/fork/seed-legacy.sh would no longer match (mig-pop3-uidl-<user>).
So the script APPENDs a marked test mail (header "X-Miab-Test: 1", a
Message-ID @smoketest.invalid, as tests/fork/smoke.py sends them) to the
INBOX, moves that one to Spam and back, and deletes it again. It checks
before and after that the UIDs of the other mails in INBOX and Spam are
unchanged.

Run it on the box (or anywhere that reaches its port 993); the password is
read from standard input:

  echo "$TEST_USER_PW" | python3 -I tests/fork/spam-move.py alice@example.net [HOST]

HOST defaults to 127.0.0.1; the certificate is not checked (test boxes).
Exit code: 0 = done, 1 = failed (printed).
"""

import email.utils
import imaplib
import ssl
import sys
import time

TEST_MSGID_DOMAIN = "smoketest.invalid"


def uids(M, folder):
	typ, _ = M.select('"%s"' % folder)
	if typ != "OK":
		raise RuntimeError("cannot select " + folder)
	typ, d = M.uid("SEARCH", None, "ALL")
	return [int(x) for x in d[0].split()] if typ == "OK" and d and d[0] else []


def find(M, folder, msgid):
	M.select('"%s"' % folder)
	typ, d = M.uid("SEARCH", None, "HEADER", "Message-ID", msgid)
	found = [int(x) for x in d[0].split()] if typ == "OK" and d and d[0] else []
	return found[0] if len(found) == 1 else None


def main(argv):
	if len(argv) not in (2, 3):
		print("usage: echo PASSWORD | spam-move.py USER [HOST]", file=sys.stderr)
		return 1
	user, host = argv[1], argv[2] if len(argv) == 3 else "127.0.0.1"
	pw = sys.stdin.readline().rstrip("\n")
	ctx = ssl.create_default_context()
	ctx.check_hostname = False
	ctx.verify_mode = ssl.CERT_NONE
	M = imaplib.IMAP4_SSL(host, 993, ssl_context=ctx)
	M.login(user, pw)
	try:
		before = {f: uids(M, f) for f in ("INBOX", "Spam")}
		msgid = "<spam-move-%d.%d@%s>" % (int(time.time()), id(M) % 100000, TEST_MSGID_DOMAIN)
		msg = ("From: Spam move test <%s>\r\nTo: %s\r\nSubject: spam-move test mail\r\nDate: %s\r\n"
			"Message-ID: %s\r\nX-Miab-Test: 1\r\n\r\nA test mail of tests/fork/spam-move.py; it is deleted again.\r\n"
			% (user, user, email.utils.formatdate(), msgid))
		typ, d = M.append("INBOX", None, imaplib.Time2Internaldate(time.time()), msg.encode())
		if typ != "OK":
			raise RuntimeError("APPEND failed: %s" % d)
		u = find(M, "INBOX", msgid)
		if u is None:
			raise RuntimeError("the test mail is not in INBOX after APPEND")
		M.select("INBOX")
		print("move test mail to Spam:", M.uid("MOVE", str(u), "Spam")[0])
		s = find(M, "Spam", msgid)
		if s is None:
			raise RuntimeError("the test mail is not in Spam")
		M.select("Spam")
		print("move test mail back to INBOX:", M.uid("MOVE", str(s), "INBOX")[0])
		u = find(M, "INBOX", msgid)
		if u is None:
			raise RuntimeError("the test mail did not come back to INBOX")
		M.select("INBOX")
		M.uid("STORE", str(u), "+FLAGS.SILENT", r"(\Deleted)")
		typ, d = M.uid("EXPUNGE", str(u)) if "UIDPLUS" in M.capabilities else M.expunge()
		print("delete test mail:", typ)
		after = {f: uids(M, f) for f in ("INBOX", "Spam")}
	finally:
		M.logout()
	if after != before:
		print("FAILED: the UIDs of the other mails changed: before %s, after %s" % (before, after))
		return 1
	print("ok: %s, INBOX %d and Spam %d other mails with the same UIDs" % (user, len(before["INBOX"]), len(before["Spam"])))
	return 0


if __name__ == "__main__":
	try:
		sys.exit(main(sys.argv))
	except (imaplib.IMAP4.error, OSError, RuntimeError) as e:
		print("FAILED: %s" % e)
		sys.exit(1)
