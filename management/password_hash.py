#!/usr/local/lib/mailinabox/env/bin/python
# Password hashes of mail users, without the password on a command line (B127).
#
# Mail-in-a-Box has always stored Dovecot-style SHA512-CRYPT hashes,
# "{SHA512-CRYPT}$6$salt$hash" (written by 'doveadm pw' and by Roundcube's
# password plugin, the latter with "$6$rounds=N$" when it is configured with
# rounds). The management daemon used to hash and check passwords by running
# 'doveadm pw -p PASSWORD', which put the plain password in the process
# arguments (readable by every local process in /proc/PID/cmdline), and the
# check printed the hash and "(verified)" into the daemon's journal.
#
# Python 3.13 removed the crypt module, so SHA-512 crypt is implemented here
# with hashlib, as specified in https://www.akkadia.org/drepper/SHA-crypt.txt
# (the algorithm of glibc and libxcrypt, which Dovecot uses). Hashes of any
# other form (another scheme set by hand, an unusual salt, very many rounds)
# are checked by 'doveadm pw -t' with the password on its standard input and
# its output discarded.

import hashlib
import hmac
import re
import secrets
import subprocess

_B64 = "./0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

# libxcrypt (crypt(3) of Ubuntu, which Dovecot uses) refuses passwords of
# 512 bytes or more: 'doveadm pw' then wrote "{SHA512-CRYPT}*0", a hash that
# no password matches.
PASSWORD_MAX_BYTES = 511

ROUNDS_DEFAULT = 5000
ROUNDS_MIN = 1000
# Hashes with more rounds than this are checked by doveadm (in C): in Python
# 5000 rounds take a few milliseconds, a million would block the daemon.
ROUNDS_MAX_PYTHON = 100000

# "{SHA512-CRYPT}" (what MIAB writes), "{CRYPT}" (crypt(3) of any kind) or no
# prefix (Dovecot's default_password_scheme in MIAB is SHA512-CRYPT), then the
# crypt string in the form glibc and libxcrypt write it. Anything else goes to
# doveadm.
# (Dovecot takes the scheme name in any case; crypt(3) the rest as written.)
_RE_SHA512_CRYPT = re.compile(
	r"(?i:\{(?:SHA512-CRYPT|CRYPT)\})?"
	r"(\$6\$(?:rounds=([1-9][0-9]{0,8})\$)?([./0-9A-Za-z]{1,16})\$[./0-9A-Za-z]{86})",
	re.ASCII)

def _b64_from_24bit(b2, b1, b0, n):
	w = (b2 << 16) | (b1 << 8) | b0
	out = []
	for _ in range(n):
		out.append(_B64[w & 0x3f])
		w >>= 6
	return "".join(out)

def _repeat(digest, length):
	# The digest repeated up to length bytes.
	return (digest * (length // len(digest) + 1))[:length]

def sha512_crypt(pw, salt, rounds=None):
	# The "$6$..." string of crypt(3) for the password (bytes), the salt (str of
	# at most 16 characters from _B64) and the rounds (None: the default 5000,
	# not written into the result, like crypt(3) does without "rounds=").
	if rounds is None:
		rounds_text = ""
		rounds = ROUNDS_DEFAULT
	else:
		if not ROUNDS_MIN <= rounds <= 999999999:
			raise ValueError("rounds out of range")
		rounds_text = f"rounds={rounds}$"
	salt_b = salt.encode("ascii")
	if not 1 <= len(salt_b) <= 16:
		raise ValueError("bad salt length")
	sha = hashlib.sha512

	b = sha(pw + salt_b + pw).digest()
	a = sha(pw + salt_b)
	a.update(_repeat(b, len(pw)))
	n = len(pw)
	while n > 0:
		a.update(b if n & 1 else pw)
		n >>= 1
	c = a.digest()

	p = _repeat(sha(pw * len(pw)).digest(), len(pw))
	s = _repeat(sha(salt_b * (16 + c[0])).digest(), len(salt_b))

	for i in range(rounds):
		c = sha((p if i & 1 else c) + (s if i % 3 else b"") + (p if i % 7 else b"") + (c if i & 1 else p)).digest()

	out = []
	for i in range(21):
		x, y, z = c[i], c[i + 21], c[i + 42]
		if i % 3 == 0:
			out.append(_b64_from_24bit(x, y, z, 4))
		elif i % 3 == 1:
			out.append(_b64_from_24bit(y, z, x, 4))
		else:
			out.append(_b64_from_24bit(z, x, y, 4))
	out.append(_b64_from_24bit(0, 0, c[63], 2))
	return f"$6${rounds_text}{salt}$" + "".join(out)

def _password_bytes(pw):
	# The bytes that 'doveadm pw -p' got as its argument (Python encodes
	# arguments with the file system encoding, UTF-8, and surrogateescape).
	return pw.encode("utf-8", "surrogateescape")

def hash_password(pw):
	# The plain password as a Dovecot-format hash, "{SHA512-CRYPT}$6$salt$hash",
	# with a random 16-character salt and the default 5000 rounds: the form
	# 'doveadm pw -s SHA512-CRYPT' writes. Raises ValueError for a password
	# that Dovecot could not check (a null character ends it in crypt(3), and
	# crypt(3) refuses one of 512 bytes or more).
	pwb = _password_bytes(pw)
	if b"\0" in pwb:
		raise ValueError("Passwords cannot contain a null character.")
	if len(pwb) > PASSWORD_MAX_BYTES:
		raise ValueError(f"Passwords cannot be longer than {PASSWORD_MAX_BYTES} bytes.")
	salt = "".join(secrets.choice(_B64) for _ in range(16))
	return "{SHA512-CRYPT}" + sha512_crypt(pwb, salt)

def verify_password(pw, stored):
	# True when the plain password matches the stored Dovecot-format hash.
	# Prints and logs nothing.
	if not isinstance(stored, str):
		return False
	try:
		pwb = _password_bytes(pw)
	except UnicodeEncodeError:
		return False
	if b"\0" in pwb or len(pwb) > PASSWORD_MAX_BYTES:
		# What crypt(3) cannot hash, Dovecot does not accept either.
		return False
	m = _RE_SHA512_CRYPT.fullmatch(stored)
	if m:
		rounds = int(m.group(2)) if m.group(2) else None
		if rounds is None or ROUNDS_MIN <= rounds <= ROUNDS_MAX_PYTHON:
			computed = sha512_crypt(pwb, m.group(3), rounds)
			return hmac.compare_digest(computed.encode("ascii"), m.group(1).encode("ascii"))
	return _doveadm_verify(pwb, stored)

def _doveadm_verify(pwb, stored):
	# Any other scheme: 'doveadm pw -t' reads the password from its standard
	# input when that is not a terminal, up to the first line break. A
	# password with a line break cannot be checked that way (it would be
	# shortened), so it fails. doveadm prints the hash with "(verified)", or
	# an error; both are discarded, only the exit code counts. The hash
	# itself is in doveadm's arguments for that moment (not the password).
	if b"\n" in pwb or b"\r" in pwb:
		return False
	try:
		p = subprocess.run(["/usr/bin/doveadm", "pw", "-t", stored],
			input=pwb + b"\n", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
			timeout=60, cwd="/", env={ "PATH": "/sbin:/bin:/usr/sbin:/usr/bin" })
	except (OSError, subprocess.SubprocessError):
		return False
	return p.returncode == 0

# For a login with an address that is no user: checked against this hash, so
# that it takes as long as a wrong password of a user.
DUMMY_HASH = "{SHA512-CRYPT}" + sha512_crypt(secrets.token_bytes(16), "".join(secrets.choice(_B64) for _ in range(16)))
