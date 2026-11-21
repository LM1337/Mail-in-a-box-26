# A mail user changes their own password: POST /me/password (B210).
#
# Roundcube's password plugin wrote users.sqlite itself, as www-data, with
# SQL ("UPDATE users SET password=%P WHERE email=%u"). For that the database
# was root:www-data 0664 in a directory that www-data could write, so any
# code running as www-data (a hole in Roundcube, Nextcloud, Z-Push or PHP)
# could rewrite the whole user database: set the password of any account,
# also an administrator's, give itself the admin privilege, or add an alias
# that forwards a user's mail elsewhere; and every local account could read
# all password hashes. Now the management daemon, which runs as root, is the
# only writer, and Roundcube's driver (conf/roundcube-password-mailinabox.php,
# installed as plugins/password/drivers/mailinabox.php) calls this endpoint on
# 127.0.0.1:10222.
#
# The caller proves who they are with their current password (HTTP Basic
# authentication, "email:current password", as for /login) and, when the
# account has two-factor authentication, its code in X-Auth-Token, exactly as
# the control panel's login checks them (auth.AuthService.check_user_auth).
# No session key and no API key: the endpoint changes only the password of
# the account whose current password was given. The new password goes
# through the daemon's own policy and hash (mailconfig.set_mail_password, as
# POST /mail/users/password). Failed attempts are logged as failed logins,
# so that fail2ban's miab-management jail bans the address (Roundcube's driver
# passes the client's address in X-Forwarded-For; nginx answers
# /admin/me/password with 404, so only local callers reach the endpoint),
# and after a few failures for an account or an address, more attempts are
# refused for a while, also from 127.0.0.1, which fail2ban does not ban.

import base64
import time

# Failures that refuse more attempts for WINDOW seconds: per account (any
# caller, so that this endpoint is no way to guess one account's password at
# full speed) and per client address. Only accounts that exist are counted:
# failures for made-up names would fill the limiter and push out the
# failures of a real account (the endpoint is local only, so telling which
# accounts exist reveals nothing to the Internet). It does not bound local
# guessing as a whole: Dovecot answers failed logins from 127.0.0.1 at once (B126, over
# IMAP, POP3, ManageSieve and SMTP submission; README-fork.md, "Known
# issues").
MAX_FAILURES_ACCOUNT = 5
MAX_FAILURES_ADDRESS = 10
WINDOW = 600

MSG_BAD_LOGIN = "Incorrect email address or password."
# Only an administrator can change it there (Mail & Users > Users); the
# control panel has no password form for other users.
MSG_MFA = ("This account uses two-factor authentication, so its password "
	"cannot be changed here. An administrator changes it in the control "
	"panel (Mail & Users > Users).")
MSG_LIMIT = "Too many failed attempts. Try again in a few minutes."


def parse_basic_auth(header):
	# (username, password) of an HTTP Basic Authorization header, or
	# (None, None). UTF-8, else Latin-1, as auth.py reads it (B175).
	if not header or " " not in header:
		return None, None
	scheme, credentials = header.split(None, 1)
	if scheme != "Basic":
		return None, None
	try:
		raw = base64.b64decode(credentials.strip().encode("ascii"), validate=True)
	except (ValueError, UnicodeEncodeError):
		return None, None
	try:
		text = raw.decode("utf-8")
	except UnicodeDecodeError:
		text = raw.decode("latin-1")
	if ":" not in text:
		return None, None
	return tuple(text.split(":", 1))


class FailureLimiter:
	# Failures per key within the last `window` seconds, in memory (the daemon
	# runs one gunicorn worker). A key with `limit` failures is refused until
	# the oldest of them is older than the window.
	def __init__(self, window=WINDOW, clock=time.monotonic, max_keys=4096):
		self.window = window
		self.clock = clock
		self.max_keys = max_keys
		self.failures = {}

	def _recent(self, key):
		now = self.clock()
		times = [t for t in self.failures.get(key, ()) if now - t < self.window]
		if times:
			self.failures[key] = times
		else:
			self.failures.pop(key, None)
		return times

	def blocked(self, key, limit):
		return len(self._recent(key)) >= limit

	def add(self, key):
		times = self._recent(key)
		times.append(self.clock())
		self.failures[key] = times[-64:]
		if len(self.failures) > self.max_keys:
			# Drop the keys whose newest failure is oldest, those of addresses
			# first: a caller that forges new addresses must not flush the
			# failures of an account (and accounts count only when they
			# exist, see change_own_password).
			for k in sorted(self.failures, key=lambda k: (k.startswith("account:"), self.failures[k][-1]))[:len(self.failures) - self.max_keys]:
				del self.failures[k]

	def reset(self, key):
		self.failures.pop(key, None)


def client_address(request):
	# The address that the failed-login line names (as log_failed_login in
	# daemon.py does): the first X-Forwarded-For value, else the connection.
	xff = request.headers.getlist("X-Forwarded-For") if hasattr(request.headers, "getlist") else []
	return xff[0].strip() if xff else (request.remote_addr or "")


def change_own_password(request, env, check_user_auth, set_mail_password, limiter, log_failure, account_exists):
	# Returns (body, HTTP status). check_user_auth(email, password, request,
	# env) raises ValueError (auth.AuthService.check_user_auth);
	# set_mail_password(email, password, env) returns "OK" or (message,
	# status) and raises ValueError for a password that the policy refuses;
	# log_failure(request) writes the failed-login line for fail2ban;
	# account_exists(email, env) tells whether a failure counts for the
	# account too (only after a failure, so a right password costs nothing
	# more).
	email, current = parse_basic_auth(request.headers.get("Authorization", ""))
	new = request.form.get("password", "")
	if not email or not current:
		return ("Give the email address and the current password (HTTP Basic authentication).", 401)
	address = client_address(request)
	account_key = "account:" + email.lower()
	address_key = "address:" + address
	if limiter.blocked(account_key, MAX_FAILURES_ACCOUNT) or limiter.blocked(address_key, MAX_FAILURES_ADDRESS):
		log_failure(request)
		return (MSG_LIMIT, 429)
	try:
		check_user_auth(email, current, request, env)
	except ValueError as e:
		reason = str(e)
		if reason == "missing-totp-token":
			# The password was right; this endpoint cannot ask for the code.
			return (MSG_MFA, 403)
		if account_exists(email, env):
			limiter.add(account_key)
		limiter.add(address_key)
		log_failure(request)
		if "invalid-totp-token" in reason:
			return ("The two-factor authentication code is not valid.", 403)
		return (MSG_BAD_LOGIN, 403)
	limiter.reset(account_key)
	if not new:
		return ("No password provided.", 400)
	try:
		result = set_mail_password(email, new, env)
	except ValueError as e:
		return (str(e), 400)
	if isinstance(result, tuple):
		return result
	return (result, 200)
