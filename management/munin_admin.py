#!/usr/local/lib/mailinabox/env/bin/python3
#
# Munin's alerts (fork).
#
# munin-limits (user munin, after each munin-update run) mails each change of
# state of a watched value through the contact "admin" of /etc/munin/munin.conf.
# Its command is munin-notify (management/munin_notify.sh), which sends the
# text with /usr/sbin/sendmail. The setting "munin_alerts" in
# $STORAGE_ROOT/settings.yaml chooses:
#
#   recipient  "admin":  administrator@PRIMARY_HOSTNAME (the default),
#              "custom": the address in "address",
#              "off":    no alerts (the host tree gets "contacts none"),
#   level      "warning":  warning and critical (the default),
#              "critical": only values that are critical (a text template that
#                          leaves out the services without a critical value;
#                          munin-notify sends nothing for an empty text).
#
# Only values that differ from DEFAULTS are stored. Without the setting
# munin.conf is exactly the file of rc6. render_config() makes the whole file:
# setup/munin.sh writes it with --setup, the daemon with apply_config(), so
# both write the same file. Munin reads munin.conf on every run (every 5
# minutes), nothing needs a restart. There is no always_send: a value that
# stays in warning or critical is not mailed again.
#
# The custom address is put on munin-notify's command line, which
# munin-limits execs without a shell when the line has no shell characters.
# So it is checked strictly (ADDRESS_RE: no spaces, quotes, line breaks,
# "$" or other shell characters), and munin-notify checks it again and hands
# it to sendmail as a separate argument after "--".
#
# Command line (as root, from the Mail-in-a-Box directory):
#   management/munin_admin.py --setup   write /etc/munin/munin.conf (setup/munin.sh)
#   management/munin_admin.py --print   show the file that would be written
#   management/munin_admin.py --test    send a test notification

import os, os.path, re, sys, subprocess, tempfile, contextlib

import utils

CONF_FILE = "/etc/munin/munin.conf"
NOTIFY = "/usr/local/lib/mailinabox/munin-notify"
RUNUSER = "/usr/sbin/runuser"

DEFAULTS = {
	"recipient": "admin",   # admin | custom | off
	"address": "",          # for recipient "custom"
	"level": "warning",     # warning (warning and critical) | critical
}
RECIPIENTS = ("admin", "custom", "off")
LEVELS = ("warning", "critical")

# A deliberately narrow form of an address: ASCII letters, digits and
# "_ + - ." in the local part ("+", "-" and "." not first, no ".."), a
# domain of at least two labels. munin_notify.sh checks the same form.
ADDRESS_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_+-]*(\.[A-Za-z0-9_+-]+)*@([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])$")

# munin-limits' own text for one service, restricted to the critical values.
# A service without a critical value gives an empty text. (Munin's template
# language; munin-limits turns \n and \t into a line break and a tab.)
CRITICAL_TEXT = (r"${if:cfields ${var:group} :: ${var:host} :: ${var:graph_title}\n\tCRITICALs:"
	r"${loop<,>:cfields  ${var:label} is ${var:value} (outside range [${var:crange}])"
	r"${if:extinfo : ${var:extinfo}}}.\n}")

def default_address(env):
	return "administrator@" + env["PRIMARY_HOSTNAME"]

def validate_address(address):
	address = (address or "").strip()
	if address == "":
		raise ValueError("Enter the address for Munin's alerts.")
	if len(address) > 254 or not ADDRESS_RE.fullmatch(address):
		raise ValueError("The address for Munin's alerts must be a plain address like name@example.com "
			"(letters, digits and _ + - . before the @, no spaces, quotes or names).")
	return address

def validate_settings(values):
	# Returns the full, checked settings; raises ValueError.
	s = dict(DEFAULTS)
	s.update({ k: v for k, v in values.items() if k in DEFAULTS and v is not None })
	for k in DEFAULTS:
		if not isinstance(s[k], str):
			raise ValueError(f"Munin alert setting {k}: must be a string.")
		s[k] = s[k].strip()
	if s["recipient"] not in RECIPIENTS:
		raise ValueError("Munin alert setting recipient: must be one of " + ", ".join(RECIPIENTS) + ".")
	if s["level"] not in LEVELS:
		raise ValueError("Munin alert setting level: must be one of " + ", ".join(LEVELS) + ".")
	if s["recipient"] == "custom":
		s["address"] = validate_address(s["address"])
	else:
		s["address"] = ""
	return s

def get_settings(env):
	# The stored settings. A broken value falls back to the defaults (warning
	# returned), so that setup never fails on it.
	stored = utils.load_settings(env).get("munin_alerts") or {}
	if not isinstance(stored, dict):
		stored = {}
	try:
		return validate_settings(stored), None
	except ValueError as e:
		return dict(DEFAULTS), f"{e} Using the defaults."

def save_settings(env, settings):
	config = utils.load_settings(env)
	diff = { k: v for k, v in settings.items() if k in DEFAULTS and v != DEFAULTS[k] }
	if diff:
		config["munin_alerts"] = diff
	else:
		config.pop("munin_alerts", None)
	utils.write_settings(config, env)

def recipient_address(env, settings):
	# The address the alerts go to, None when they are off.
	if settings["recipient"] == "off":
		return None
	if settings["recipient"] == "custom":
		return settings["address"]
	return default_address(env)

def notify_argv(env, settings):
	# The contact's command as an argument list. Without a custom address it
	# is the bare command of rc6.
	argv = [NOTIFY]
	if settings["recipient"] == "custom":
		argv += ["--to", validate_address(settings["address"])]
	return argv

def render_config(env, settings):
	host = env["PRIMARY_HOSTNAME"]
	to = recipient_address(env, settings)
	ret = f"""dbdir /var/lib/munin
htmldir /var/cache/munin/www
logdir /var/log/munin
rundir /var/run/munin
tmpldir /etc/munin/templates

includedir /etc/munin/munin-conf.d

# path dynazoom uses for requests
cgiurl_graph /admin/munin/cgi-graph

"""
	if to is None:
		ret += """# Alerts: off (admin panel, Munin Monitoring). No contact is defined, and
# the host tree below says "contacts none".

"""
		contacts = "none"
	else:
		if settings["level"] == "critical":
			what = "each change of state of a plugin that has a\n# critical value"
		else:
			what = "each change of state (ok, warning, critical,\n# unknown)"
		ret += f"""# Alerts: munin-limits mails {what} to {to}, one mail per run with changes.
# The contact must come before the host tree: the lines after a [host] line
# belong to that host, and munin-limits finds no contact there.
contact.admin.command {" ".join(notify_argv(env, settings))}
"""
		if settings["level"] == "critical":
			ret += "# Only critical values (admin panel, Munin Monitoring).\n"
			ret += f"contact.admin.text {CRITICAL_TEXT}\n"
		ret += "\n"
		contacts = "admin"
	ret += f"""# a simple host tree
[{host}]
address 127.0.0.1
contacts {contacts}
"""
	return ret

def _read(path):
	try:
		with open(path, encoding="utf-8") as f:
			return f.read()
	except FileNotFoundError:
		return None

def _write(path, content):
	# /etc/munin belongs to root: a new file next to the old one, then rename.
	fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".munin.conf.")
	try:
		with os.fdopen(fd, "w", encoding="utf-8") as f:
			f.write(content)
			os.fchmod(f.fileno(), 0o644)
		os.replace(tmp, path)
	except BaseException:
		with contextlib.suppress(OSError):
			os.unlink(tmp)
		raise

def config_is_current(env, settings=None):
	if settings is None:
		settings, _ = get_settings(env)
	return _read(CONF_FILE) == render_config(env, settings)

def apply_config(env, settings=None):
	# Writes munin.conf if it differs. Returns whether it changed.
	if settings is None:
		settings, _ = get_settings(env)
	content = render_config(env, settings)
	if _read(CONF_FILE) == content:
		return False
	_write(CONF_FILE, content)
	return True

def update_settings(env, values):
	# Validate and store new values (a partial dict; fields that are not given
	# keep their value) and apply them. On a failed write the previous
	# settings are restored.
	old, _ = get_settings(env)
	merged = dict(old)
	merged.update({ k: v for k, v in values.items() if v is not None })
	new = validate_settings(merged)
	save_settings(env, new)
	try:
		changed = apply_config(env, new)
	except Exception:
		save_settings(env, old)
		raise
	return { "settings": new, "changed": changed }

def status(env):
	settings, warning = get_settings(env)
	ret = dict(settings)
	ret.update({
		"default_address": default_address(env),
		"to": recipient_address(env, settings),
		"config_current": config_is_current(env, settings),
		"warnings": [warning] if warning else [],
	})
	return ret

def send_test(env):
	# One notification through the contact's own command, as user munin like
	# munin-limits, with the test marker (munin-notify --test). Returns the
	# address. Raises ValueError when the alerts are off, RuntimeError when
	# munin-notify failed.
	settings, _ = get_settings(env)
	to = recipient_address(env, settings)
	if to is None:
		raise ValueError("Munin's alerts are off, there is nobody to send a test mail to.")
	level = "critical values only" if settings["level"] == "critical" else "warnings and critical values"
	text = (f"This is a test of Munin's alerts on {env['PRIMARY_HOSTNAME']}, sent from the admin panel.\n"
		f"Munin mails changes of state ({level}) to {to}.\n")
	argv = [RUNUSER, "-u", "munin", "--", *notify_argv(env, settings), "--test"]
	try:
		p = subprocess.run(argv, input=text, capture_output=True, text=True, timeout=60, cwd="/",
			env={ "PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C.UTF-8" })
	except (OSError, subprocess.TimeoutExpired) as e:
		raise RuntimeError(f"munin-notify could not be run: {e}") from None
	if p.returncode != 0:
		msg = (p.stderr.strip() or p.stdout.strip() or f"exit code {p.returncode}").splitlines()[-1]
		raise RuntimeError(f"munin-notify failed: {msg}")
	return to

if __name__ == "__main__":
	env = utils.load_environment()
	args = sys.argv[1:]
	if args == ["--setup"]:
		settings, warning = get_settings(env)
		if warning:
			print(warning)
		apply_config(env, settings)
	elif args == ["--print"]:
		settings, warning = get_settings(env)
		if warning:
			print("#", warning)
		print(render_config(env, settings), end="")
	elif args == ["--test"]:
		try:
			print("Test notification sent to", send_test(env))
		except (ValueError, RuntimeError) as e:
			print(e, file=sys.stderr)
			sys.exit(1)
	else:
		print("usage: munin_admin.py --setup | --print | --test", file=sys.stderr)
		sys.exit(2)
