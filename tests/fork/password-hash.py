#!/usr/bin/env python3
"""Checks management/password_hash.py (B127), the SHA-512 crypt of the control panel.

Without options (no box needed): the test vectors of the specification
(https://www.akkadia.org/drepper/SHA-crypt.txt), the forms of stored hashes it
checks itself, passwords stored in plain text ({PLAIN}, {CLEARTEXT},
{PLAIN-TRUNC}, with HEX and B64 encodings; compared without doveadm) and the
limits (null character, 512 bytes).

With --doveadm (on a box, as root): random passwords (ASCII and UTF-8, 8 to 511
bytes; line breaks are tested offline only, as doveadm reads its standard
input only up to one) against Dovecot's own 'doveadm pw': each hash of
hash_password() verified by 'doveadm pw -t', each hash of 'doveadm pw' (default
rounds and -r) by verify_password(), wrong passwords refused by both, and
other schemes (BLF-CRYPT, ARGON2ID, ...) through the doveadm fallback, and the
plain-text schemes compared with doveadm's own result. The random passwords
go to doveadm on its standard input, never in its arguments, and are not
printed (the plain-text cases give doveadm a fixed test password as the
stored value, which is the point of not doing so in verify_password).

Usage: python3 -I tests/fork/password-hash.py [--doveadm [--count N]]
Exit code 0 when every check passed.
"""
import argparse
import os
import random
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "management"))
import password_hash as ph  # noqa: E402

# (salt, rounds, password, result) from the specification. Salts longer than
# 16 characters are cut there; here they are given cut.
VECTORS = [
	("saltstring", None, "Hello world!",
		"$6$saltstring$svn8UoSVapNtMuq1ukKS4tPQd8iKwSMHWjl/O817G3uBnIFNjnQJuesI68u4OTLiBFdcbYEdFCoEOfaS35inz1"),
	("saltstringsaltst", 10000, "Hello world!",
		"$6$rounds=10000$saltstringsaltst$OW1/O6BYHV6BcXZu8QVeXbDWra3Oeqh0sbHbbMCVNSnCM/UrjmM0Dp8vOuZeHBy/YTBmSK6H9qs/y3RnOaw5v."),
	("toolongsaltstrin", 5000, "This is just a test",
		"$6$rounds=5000$toolongsaltstrin$lQ8jolhgVRVhY4b5pZKaysCLi0QBxGoNeKQzQ3glMhwllF7oGDZxUhx1yxdYcz/e1JSbq3y6JMxxl8audkUEm0"),
	("anotherlongsalts", 1400, "a very much longer text to encrypt.  This one even stretches over morethan one line.",
		"$6$rounds=1400$anotherlongsalts$POfYwTEok97VWcjxIiSOjiykti.o/pQs.wPvMxQ6Fm7I6IoYN3CmLs66x9t0oSwbtEW7o7UmJEiDwGqd8p4ur1"),
	("short", 77777, "we have a short salt string but not a short password",
		"$6$rounds=77777$short$WuQyW2YR.hBNpjjRhpYD/ifIw05xdfeEyQoMxIXbkvr0gge1a1x3yRULJ5CCaUeOxFmtlcGZelFl5CxtgfiAc0"),
	("asaltof16chars..", 123456, "a short string",
		"$6$rounds=123456$asaltof16chars..$BtCwjqMJGx5hrJhZywWvt0RLE8uZ4oPwcelCjmw2kSYu.Ec6ycULevoBK25fs2xXgMNrCzIMVcgEJAstJeonj1"),
	("roundstoolow", 1000, "the minimum number is still observed",
		"$6$rounds=1000$roundstoolow$kUMsbe306n21p9R.FRkW3IGn.S9NPN0x50YhH1xhLsPuWGsUSklZt58jaTfF4ZEQpyUNGc0dqbpBYYBaHHrsX."),
]

FAILS = []

def check(name, ok, detail=""):
	print("%s %s%s" % ("PASS" if ok else "FAIL", name, (": " + detail) if detail else ""))
	if not ok:
		FAILS.append(name)

def offline():
	for i, (salt, rounds, pw, want) in enumerate(VECTORS, 1):
		check("vector-%d" % i, ph.sha512_crypt(pw.encode(), salt, rounds) == want)
		if rounds is None or rounds <= ph.ROUNDS_MAX_PYTHON:
			check("vector-%d-verify" % i, ph.verify_password(pw, "{SHA512-CRYPT}" + want)
				and not ph.verify_password(pw + " ", "{SHA512-CRYPT}" + want))
	h = ph.hash_password("Correct horse 1")
	check("hash-form", h.startswith("{SHA512-CRYPT}$6$") and len(h) == 120 and "rounds=" not in h, "length %d" % len(h))
	check("hash-salt-random", ph.hash_password("Correct horse 1") != h)
	check("verify-right", ph.verify_password("Correct horse 1", h))
	check("verify-wrong", not ph.verify_password("Correct horse 2", h))
	bare = h[len("{SHA512-CRYPT}"):]
	check("verify-no-prefix", ph.verify_password("Correct horse 1", bare))
	check("verify-crypt-prefix", ph.verify_password("Correct horse 1", "{CRYPT}" + bare))
	check("verify-prefix-case", ph.verify_password("Correct horse 1", "{sha512-crypt}" + bare))
	pw = "line one\nline two\r\tand more"
	check("verify-line-breaks", ph.verify_password(pw, ph.hash_password(pw)))
	pw = "Grüße, 😀 中文 ok"
	check("verify-utf8", ph.verify_password(pw, ph.hash_password(pw)))
	check("verify-not-a-hash", not ph.verify_password("x" * 10, None) and not ph.verify_password("x" * 10, ""))
	try:
		ph.hash_password("abc\0defgh")
		check("refuse-null", False)
	except ValueError:
		check("refuse-null", True)
	try:
		ph.hash_password("a" * 512)
		check("refuse-512-bytes", False)
	except ValueError:
		check("refuse-512-bytes", True)
	check("hash-511-bytes", ph.verify_password("ü" * 255 + "a", ph.hash_password("ü" * 255 + "a")))
	check("verify-512-bytes", not ph.verify_password("a" * 512, "{SHA512-CRYPT}" + ph.sha512_crypt(b"a" * 512, "abc")))
	check("dummy-hash", ph.DUMMY_HASH.startswith("{SHA512-CRYPT}$6$") and not ph.verify_password("Correct horse 1", ph.DUMMY_HASH))
	plain()

# (stored value, password, expected) for the plain-text schemes, as Dovecot compares them.
PLAIN_CASES = [
	("{PLAIN}Plain pw 1", "Plain pw 1", True),
	("{PLAIN}Plain pw 1", "Plain pw 2", False),
	("{PLAIN}Plain pw 1", "Plain pw 1 ", False),
	("{plain}Plain pw 1", "Plain pw 1", True),
	("{CLEARTEXT}Plain pw 1", "Plain pw 1", True),
	("{CLEARTEXT}Plain pw 1", "Plain pw", False),
	("{PLAIN}Grüße 😀", "Grüße 😀", True),
	("{PLAIN.B64}UGxhaW4gcHcgMQ==", "Plain pw 1", True),
	("{PLAIN.BASE64}UGxhaW4gcHcgMQ==", "Plain pw 2", False),
	("{PLAIN.HEX}506c61696e2070772031", "Plain pw 1", True),
	("{PLAIN.HEX}zz", "Plain pw 1", False),
	("{PLAIN-TRUNC}5-Plain", "Plain pw 1", True),
	("{PLAIN-TRUNC}5-Plain", "Plai", False),
	("{PLAIN-TRUNC}5-Plain", "Other pw 1", False),
	("{PLAIN-TRUNC}20-Plain pw 1", "Plain pw 1", True),
	("{PLAIN-TRUNC}20-Plain pw 1", "Plain pw 12", False),
	("{PLAIN-TRUNC}Plain pw 1", "Plain pw 1", False),
	("{PLAIN.XYZ}Plain pw 1", "Plain pw 1", False),
	("Plain pw 1", "Plain pw 1", False),
]

def plain():
	# The plain-text schemes are compared in Python; doveadm, which would have the
	# stored password in its arguments, must not be called for them.
	called = []
	saved = ph._doveadm_verify
	ph._doveadm_verify = lambda pwb, stored: called.append(stored) or False
	try:
		bad = [i for i, (stored, pw, want) in enumerate(PLAIN_CASES) if ph.verify_password(pw, stored) is not want]
	finally:
		ph._doveadm_verify = saved
	check("plain-schemes-%d" % len(PLAIN_CASES), not bad, "cases %s" % bad if bad else "")
	check("plain-schemes-no-doveadm", not called, "%d doveadm call(s)" % len(called))

def doveadm(args, stdin):
	# doveadm reads the password from standard input (not a terminal) up to a line break.
	p = subprocess.run(["/usr/bin/doveadm", "pw", *args], input=stdin, capture_output=True, timeout=60)
	return p.returncode, p.stdout.decode(errors="replace").strip()

def with_doveadm(count):
	rnd = random.SystemRandom()
	alpha = [chr(c) for c in range(32, 127)] + list("äöüßéł€😀中")
	bad = 0
	for i in range(count):
		pw = "".join(rnd.choice(alpha) for _ in range(rnd.choice([8, 12, 63, 64, 65, 127, 128, 200, 255, 256, 300, 511])))
		while len(pw.encode()) > ph.PASSWORD_MAX_BYTES:
			pw = pw[:-1]
		pwb = pw.encode()
		ours = ph.hash_password(pw)
		rc_ok, _ = doveadm(["-t", ours], pwb + b"\n")
		rc_bad, _ = doveadm(["-t", ours], pwb + b"x\n")
		rounds = rnd.choice([None, None, 1000, 5000, 20000])
		rc, theirs = doveadm(["-s", "SHA512-CRYPT"] + (["-r", str(rounds)] if rounds else []), pwb + b"\n" + pwb + b"\n")
		ok = (rc_ok == 0 and rc_bad != 0 and rc == 0 and theirs.startswith("{SHA512-CRYPT}$6$")
			and ph.verify_password(pw, theirs) and not ph.verify_password(pw[:-1], theirs))
		if not ok:
			bad += 1
			print("  case %d failed: length %d bytes, rounds %s, doveadm -t ours %d/%d, doveadm hash rc %d"
				% (i, len(pwb), rounds, rc_ok, rc_bad, rc))
	check("doveadm-random-%d" % count, bad == 0, "%d failed" % bad)
	pw = "line\nbreak-pw"
	check("doveadm-line-break-not-cut", not ph.verify_password("line", ph.hash_password(pw)))
	for scheme in ("BLF-CRYPT", "SHA256-CRYPT", "MD5-CRYPT", "ARGON2ID", "SSHA512", "CRAM-MD5"):
		rc, h = doveadm(["-s", scheme], b"Fallback pw 1\nFallback pw 1\n")
		if rc != 0:
			print("SKIP fallback-%s: doveadm has no such scheme" % scheme)
			continue
		check("fallback-" + scheme, ph.verify_password("Fallback pw 1", h) and not ph.verify_password("Fallback pw 2", h))
	rc, h = doveadm(["-s", "SHA512-CRYPT", "-r", str(ph.ROUNDS_MAX_PYTHON * 2)], b"Fallback pw 1\nFallback pw 1\n")
	check("fallback-many-rounds", rc == 0 and ph.verify_password("Fallback pw 1", h) and not ph.verify_password("Fallback pw 2", h))
	# Plain-text schemes: our result must be doveadm's (here doveadm gets the fixed test value as its argument).
	diff = []
	for i, (stored, pw, want) in enumerate(PLAIN_CASES):
		if not stored.startswith("{"):
			continue
		rc, _ = doveadm(["-t", stored], pw.encode() + b"\n")
		if (rc == 0) is not ph.verify_password(pw, stored):
			diff.append(i)
	check("plain-schemes-as-doveadm", not diff, "cases %s differ" % diff if diff else "")

def main():
	ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	ap.add_argument("--doveadm", action="store_true", help="also compare with doveadm pw (on a box, as root)")
	ap.add_argument("--count", type=int, default=100, help="random passwords with --doveadm")
	args = ap.parse_args()
	offline()
	if args.doveadm:
		with_doveadm(args.count)
	print("RESULT %s (%d failed)" % ("FAIL" if FAILS else "PASS", len(FAILS)))
	return 1 if FAILS else 0

if __name__ == "__main__":
	sys.exit(main())
