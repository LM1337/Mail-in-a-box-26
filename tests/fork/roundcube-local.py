#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Offline test of the report of local Roundcube changes in the in-place
upgrade and the migration -- python3 stdlib only, no box needed (B200).

tools/upgrade-in-place-to-2604.sh and tools/migrate-to-2604.sh carry the
same Python code (ROUNDCUBE_PY) that compares an old Roundcube with what
setup installs and writes ("check", the preflight) and with the Roundcube
after setup ("verify", which writes local-changes.json for System Status).
This test checks:

  * both tools carry the same code;
  * its idea of setup's settings is the configuration that setup/webmail.sh
    writes, and setup's own plugins count as installed by setup;
  * an unchanged configuration (of this fork, or of upstream, which has
    another support link and no quota_zero_as_unlimited before v74) gives
    nothing;
  * extra plugin directories, plugins added to or left out of the list (also
    with $config['plugins'][] = ...), changed values of setup's settings,
    settings set by hand (by name only: a value may be a password), parts
    of a setting ($config['x']['y']) and other statements are named;
  * comments and strings with ";" or "?>" do not cut a statement, and a file
    that cannot be read completely is named as such;
  * names and values with control characters are shown with "?" or escaped;
  * "verify" names only what the Roundcube after setup does not have, writes
    local-changes.json (0600) with the open items and removes it when
    nothing is open;
  * "verify" names a local plugin of the new Roundcube that the web server
    (www-data) cannot read completely, also when the names of the new
    plugin directories come through a pipe as the tools pass them, and
    the in-place tool keeps the plugin copies with their modes, so that
    "cp -a" brings back a readable plugin (B186);
  * the preflight reports of both tools run under "set -euo pipefail"
    before anything else of the tool (B185: no unbound variable);
  * System Status (management/status_checks.py) shows that file as a
    warning with the items as extra lines, and ignores a link, a file that
    another account could write, or a missing file.

  tests/fork/roundcube-local.py

Exit code: 0 = all cases pass, 1 = a case failed (printed).
"""

import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
TOOLS = ["tools/upgrade-in-place-to-2604.sh", "tools/migrate-to-2604.sh"]
FAILED = []


def check(name, cond, detail=""):
	print("%s %s%s" % ("ok  " if cond else "FAIL", name, "" if cond else ": " + detail))
	if not cond:
		FAILED.append(name)


def embedded(path):
	s = open(os.path.join(ROOT, path), encoding="utf-8").read()
	m = re.search(r"\nROUNDCUBE_PY=\$\(cat <<'EOF'\n(.*?)\nEOF\n\)\n", s, re.S)
	return m.group(1) if m else None


def template():
	# The configuration that setup/webmail.sh writes, with example values.
	s = open(os.path.join(ROOT, "setup/webmail.sh"), encoding="utf-8").read()
	m = re.search(r'cat > "\$RCM_CONFIG" <<EOF;\n(.*?)\nEOF\n', s, re.S)
	t = m.group(1).replace("\\$", "$")
	for k, v in {"$STORAGE_ROOT": "/home/user-data", "$PRIMARY_HOSTNAME": "box.example.com",
			"$SECRET_KEY": "c2VjcmV0a2V5c2VjcmV0a2V5c2VjcmV0a2V5MTIz",
			"$RCM_FAVICON_CONFIG": "$config['skin_logo'] = array('elastic:[favicon]' => 'mailinabox-favicon.ico');"}.items():
		t = t.replace(k, v)
	return t + "\n"


def setup_plugin_clones():
	s = open(os.path.join(ROOT, "setup/webmail.sh"), encoding="utf-8").read()
	return set(re.findall(r'"\$\{RCM_BUILD\}/plugins/([a-z0-9_]+)"', s)) | {"carddav"}


class Run:
	def __init__(self, code):
		self.code = code
		self.dir = tempfile.mkdtemp()
		self.n = 0

	def file(self, text):
		self.n += 1
		p = os.path.join(self.dir, "f%d" % self.n)
		with open(p, "w", encoding="utf-8") as f:
			f.write(text)
		return p

	def __call__(self, *args):
		r = subprocess.run([sys.executable, "-I", "-c", self.code] + list(args), capture_output=True, text=True)
		if r.returncode != 0:
			return None, r.stderr
		return [l for l in r.stdout.split("\n") if l], r.stderr


def load_status_checks():
	stubs = ["dateutil", "dateutil.parser", "dateutil.relativedelta", "dateutil.tz",
		"dns", "dns.exception", "dns.name", "dns.reversename", "dns.resolver", "idna", "psutil",
		"postfix_mta_sts_resolver", "postfix_mta_sts_resolver.resolver",
		"dns_update", "web_update", "ssl_certificates", "mailconfig", "utils",
		"backup", "fail2ban_admin"]

	class Anything(types.ModuleType):
		def __getattr__(self, name):
			if name.startswith("__"):
				raise AttributeError(name)
			return lambda *a, **k: None
	for name in stubs:
		sys.modules[name] = Anything(name)
	spec = importlib.util.spec_from_file_location("status_checks", os.path.join(ROOT, "management", "status_checks.py"))
	mod = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(mod)
	return mod


class Rec:
	def __init__(self):
		self.calls = []

	def __getattr__(self, name):
		return lambda *a, **k: self.calls.append((name, a))


def main():
	codes = [embedded(t) for t in TOOLS]
	check("both tools carry ROUNDCUBE_PY", all(codes), str([c is not None for c in codes]))
	if not all(codes):
		return 1
	check("the two copies are the same", codes[0] == codes[1])
	run = Run(codes[0])
	ns = {}
	exec(compile(codes[0].replace("sys.exit(main(sys.argv[1:]))", ""), "ROUNDCUBE_PY", "exec"), ns)

	# Setup's settings and plugins.
	tpl = template()
	cfg = ns["read_config"](run.file(tpl))
	check("setup's configuration is read without error", cfg and not cfg["error"], str(cfg and cfg["error"]))
	fixed = {k: v for k, v in ns["SETUP_SETTINGS"].items() if v is not None}
	check("SETUP_SETTINGS has the keys that setup writes", set(cfg["settings"]) == set(ns["SETUP_SETTINGS"]),
		str(set(cfg["settings"]) ^ set(ns["SETUP_SETTINGS"])))
	diff = {k: (v, cfg["settings"].get(k)) for k, v in fixed.items() if cfg["settings"].get(k) != v}
	check("SETUP_SETTINGS has the values that setup writes", not diff, str(diff))
	check("no other statements in setup's configuration", cfg["other"] == [], str(cfg["other"]))
	clones = setup_plugin_clones()
	check("setup's own plugins count as installed by setup", clones <= ns["SETUP_PLUGIN_DIRS"] and len(clones) == 3,
		str(clones))
	check("setup's plugin list is read", cfg["plugins"] == ns["plugin_list"](ns["SETUP_SETTINGS"]["plugins"])
		and "carddav" in cfg["plugins"], str(cfg["plugins"]))

	core = run.file("acl\narchive\ncarddav\nhtml5_notifier\nmanagesieve\npassword\npersistent_login\nzipdownload\njqueryui\nmarkdown_editor\n")
	out, err = run("check", run.file(tpl), core)
	check("unchanged configuration of the fork: nothing", out == [], str(out) + err)
	upstream = tpl.replace("https://github.com/LM1337/Mail-in-a-box-26", "https://mailinabox.email/")
	upstream = re.sub(r"\$config\['skin_logo'\].*\n", "", upstream)
	upstream = upstream.replace("$config['quota_zero_as_unlimited'] = true;\n", "")
	out, err = run("check", run.file(upstream), core)
	check("unchanged configuration of upstream (v60 to v73): nothing", out == [], str(out) + err)
	out, err = run("check", os.path.join(run.dir, "missing.php"), run.file(""))
	check("no Roundcube at all: nothing", out == [], str(out) + err)

	# A configuration changed by hand.
	mod = upstream.replace("'jqueryui', ", "'jqueryui', 'contextmenu', ").replace("'zipdownload', ", "")
	mod = mod.replace("'elastic'", "'larry'")
	mod = mod.replace("?>", "$config['ldap_public']['corp'] = array('bind_pass' => 'S3cret;?>x');\n"
		"$config['plugins'][] = 'twofactor_gauthenticator';\n"
		"$config['draft_autosave'] = 60; // every minute; really ?\n"
		"/* a comment; with ; */ $config['smtp_pass'] = \"p@ss;word\";\n"
		"include '/etc/roundcube/extra.php';\n?>")
	dirs = run.file("acl\narchive\ncarddav\ncontextmenu\ntwofactor_gauthenticator\nbad\x1b]0;x\x07name\n")
	out, err = run("check", run.file(mod), dirs)
	want = [
		"plugin directory plugins/'bad\\x1b]0;x\\x07name': setup does not install it",
		"plugin directory plugins/contextmenu: setup does not install it",
		"plugin directory plugins/twofactor_gauthenticator: setup does not install it",
		"plugin list: contextmenu (setup's list does not have it)",
		"plugin list: twofactor_gauthenticator (setup's list does not have it)",
		"plugin list: zipdownload is on again (the old list left it out)",
		"setting draft_autosave: set by hand (setup does not write it)",
		"setting ldap_public: set by hand (setup does not write it)",
		"setting skin: 'larry' (setup writes 'elastic')",
		"setting smtp_pass: set by hand (setup does not write it)",
		"1 statement(s) that are not settings, setup does not write them (line %d of the old file)"
			% (mod.split("\n").index("include '/etc/roundcube/extra.php';") + 1),
	]
	check("changed configuration: every change named", out == want, "\n  got  %s\n  want %s" % (out, want))
	check("no value of a setting set by hand is shown", out is not None and not any("S3cret" in l or "p@ss" in l for l in out))
	check("no control character in the output", out is not None and not any(re.search(r"[\x00-\x1f\x7f]", l) for l in out))

	# Files that cannot be read completely.
	for name, text in [("heredoc", "<?php\n$config['x'] = <<<EOT\nabc\nEOT;\n"),
			("unterminated string", "<?php\n$config['skin'] = 'elastic;\n"),
			("unterminated comment", "<?php\n/* abc\n"),
			("statement without end", "<?php\n$config['skin'] = 'elastic'\n")]:
		out, err = run("check", run.file(text), run.file(""))
		check("unreadable file (%s) is named" % name, out is not None and len(out) == 1
			and out[0].startswith("config/config.inc.php could not be read completely"), str(out) + err)
	out, err = run("check", run.file("<?php\n$config['plugins'] = array_merge($a, $b);\n"), run.file(""))
	check("a plugin list that is no list of names", out == ["plugin list: changed by hand in a form that this check does not read"], str(out))

	# extra: the copies to keep.
	out, err = run("extra", dirs)
	check("extra lists the directories to keep (valid names only)", out == ["contextmenu", "twofactor_gauthenticator"], str(out))

	# verify: against the Roundcube after setup.
	j = os.path.join(run.dir, "local-changes.json")
	old_cfg, new_cfg = run.file(mod), run.file(tpl)
	new_dirs = run.file("acl\narchive\ncarddav\ncontextmenu\nmarkdown_editor\n")
	out, err = run("verify", old_cfg, dirs, new_cfg, new_dirs, "--json", j, "upgrade-in-place-to-2604.sh",
		"/root/upgrade-2604/upgrade-in-place-to-2604.sh --ack-local")
	want = [
		"plugin directory plugins/'bad\\x1b]0;x\\x07name': missing now (only in the old Roundcube)",
		"plugin directory plugins/twofactor_gauthenticator: missing now (only in the old Roundcube)",
		"plugin list: contextmenu (the list now does not have it)",
		"plugin list: twofactor_gauthenticator (the list now does not have it)",
		"plugin list: zipdownload is on again (the old list left it out)",
		"setting draft_autosave: set by hand, missing now",
		"setting ldap_public: set by hand, missing now",
		"setting skin: 'larry' before, 'elastic' now",
		"setting smtp_pass: set by hand, missing now",
		"1 statement(s) that are not settings, missing now (line %d of the old file)"
			% (mod.split("\n").index("include '/etc/roundcube/extra.php';") + 1),
	]
	check("verify names what the new Roundcube does not have", out == want, "\n  got  %s\n  want %s" % (out, want))
	try:
		st = os.lstat(j)
		doc = json.load(open(j, encoding="utf-8"))
	except (OSError, ValueError) as e:
		st, doc = None, None
		check("local-changes.json written", False, str(e))
	if st:
		check("local-changes.json is 0600", stat.S_IMODE(st.st_mode) == 0o600, oct(st.st_mode))
		check("local-changes.json has the items", doc.get("items") == want and doc.get("tool") == "upgrade-in-place-to-2604.sh"
			and doc.get("ack") == "/root/upgrade-2604/upgrade-in-place-to-2604.sh --ack-local", str(doc))
		check("no temporary file left", sorted(x for x in os.listdir(run.dir) if x.startswith(".")) == [])
	# A hook brought everything back: the file goes.
	back = tpl.replace("'jqueryui', ", "'jqueryui', 'contextmenu', 'twofactor_gauthenticator', ").replace("'zipdownload', ", "")
	back = back.replace("'elastic'", "'larry'").replace("?>", "$config['ldap_public']['corp'] = array('bind_pass' => 'S3cret;?>x');\n"
		"$config['draft_autosave'] = 60;\n$config['smtp_pass'] = \"p@ss;word\";\ninclude '/etc/roundcube/extra.php';\n?>")
	out, err = run("verify", old_cfg, run.file("acl\ncontextmenu\ntwofactor_gauthenticator\n"), run.file(back),
		run.file("acl\ncontextmenu\ntwofactor_gauthenticator\n"), "--json", j, "x", "/x --ack-local")
	check("all brought back: nothing open", out == [], str(out) + err)
	check("all brought back: local-changes.json removed", not os.path.exists(j))
	out, err = run("verify", run.file(upstream), core, run.file(tpl), core, "--json", j, "x", "/x --ack-local")
	check("unchanged upstream box after setup: nothing, no file", out == [] and not os.path.exists(j), str(out) + err)

	# B186: a plugin brought back with the modes of a root-only copy cannot
	# be read by the web server; verify names it (and keeps the file).
	rc = os.path.join(tempfile.mkdtemp(), "roundcubemail")
	os.makedirs(os.path.join(rc, "config"))
	with open(os.path.join(rc, "config", "config.inc.php"), "w", encoding="utf-8") as f:
		f.write(back)
	names = run.file("acl\ncontextmenu\ntwofactor_gauthenticator\n")
	for pl in ("acl", "contextmenu", "twofactor_gauthenticator"):
		os.makedirs(os.path.join(rc, "plugins", pl, "lib"))
		for fn in (pl + ".php", "lib/x.php"):
			with open(os.path.join(rc, "plugins", pl, fn), "w") as f:
				f.write("<?php\n")
	os.chmod(os.path.join(rc, "plugins", "contextmenu"), 0o700)
	os.chmod(os.path.join(rc, "plugins", "contextmenu", "contextmenu.php"), 0o600)
	os.chmod(os.path.join(rc, "plugins", "twofactor_gauthenticator", "lib", "x.php"), 0o640)
	out, err = run("verify", old_cfg, names, os.path.join(rc, "config", "config.inc.php"), names, "--json", j, "x", "/x --ack-local")
	check("B186: unreadable plugin copies named (2 entries, 1 entry), setup's acl not looked at",
		out == ["plugin directory plugins/contextmenu: the web server (www-data) cannot read 2 of its files and directories (contextmenu, ...), so Roundcube does not load it",
			"plugin directory plugins/twofactor_gauthenticator: the web server (www-data) cannot read 1 of its files and directories (twofactor_gauthenticator/lib/x.php), so Roundcube does not load it"]
		and os.path.exists(j), str(out) + err)
	# The tools pass NEW_DIRS as a pipe, <(roundcube_plugin_dirs ...), which
	# can be read only once: the same case through bash's process substitution.
	r = subprocess.run(["bash", "-c", 'exec "$0" -I -c "$1" verify "$2" "$3" "$4" <(cat "$3") --json "$5" x "/x --ack-local"',
		sys.executable, run.code, old_cfg, names, os.path.join(rc, "config", "config.inc.php"), j], capture_output=True, text=True)
	piped = [l for l in r.stdout.split("\n") if l]
	check("B186: NEW_DIRS as a pipe (as the tools pass it): the same items",
		r.returncode == 0 and len(piped) == 2 and all("cannot read" in x for x in piped), str(piped) + r.stderr)
	for dp, dn, fn in os.walk(os.path.join(rc, "plugins")):
		os.chmod(dp, 0o755)
		for x in fn:
			os.chmod(os.path.join(dp, x), 0o644)
	out, err = run("verify", old_cfg, names, os.path.join(rc, "config", "config.inc.php"), names, "--json", j, "x", "/x --ack-local")
	check("B186: readable plugins: nothing open", out == [] and not os.path.exists(j), str(out) + err)

	# B186: the in-place tool keeps the plugin copies with their modes (root's
	# only is old-roundcube/ itself and the old config.inc.php).
	check("B186: save_old_roundcube keeps the plugins' modes", *save_old_roundcube_modes())
	for tool in TOOLS:
		src = open(os.path.join(ROOT, tool), encoding="utf-8").read()
		fn = re.search(r"\nsave_old_roundcube\(\) \{.*?\n\}\n", src, re.S).group(0)
		check("B186: %s: no chmod -R go= of the kept copy" % tool,
			'\tchmod -R go= "$OLD_RC.new"' not in fn and '\tchmod go= "$OLD_RC.new" "$OLD_RC.new/plugins.txt"' in fn)

	# System Status.
	sc = load_status_checks()
	sc.LOCAL_CHANGES_OWNER = os.getuid()
	d = tempfile.mkdtemp()
	os.chmod(d, 0o700)
	sc.LOCAL_CHANGES_FILES = [(d, "The in-place upgrade to this fork", "/root/upgrade-2604/upgrade-in-place-to-2604.sh --ack-local")]
	rec = Rec()
	sc.check_local_changes_after_upgrade({}, rec)
	check("no file: no warning", rec.calls == [], str(rec.calls))
	p = os.path.join(d, "local-changes.json")
	with open(p, "w", encoding="utf-8") as f:
		json.dump({"version": 1, "tool": "t", "ack": "/root/upgrade-2604/upgrade-in-place-to-2604.sh --ack-local",
			"created": "2026-11-20T10:00:00Z", "items": ["plugin directory plugins/x: missing now", "a\x1b[2Jb"]}, f)
	os.chmod(p, 0o600)
	rec = Rec()
	sc.check_local_changes_after_upgrade({}, rec)
	names = [c[0] for c in rec.calls]
	check("file: a warning with the items as extra lines", names == ["print_warning", "print_line", "print_line"], str(rec.calls))
	if names[:1] == ["print_warning"]:
		msg = rec.calls[0][1][0]
		check("the warning names the date, the ack command and the file",
			"(2026-11-20T10:00:00Z)" in msg and "--ack-local" in msg and p in msg, msg)
		check("control characters of an item are replaced", rec.calls[2][1][0] == "a?[2Jb", str(rec.calls[2]))
	os.chmod(p, 0o622)
	rec = Rec()
	sc.check_local_changes_after_upgrade({}, rec)
	check("a file that others can write is ignored", rec.calls == [], str(rec.calls))
	os.chmod(p, 0o600)
	os.rename(p, p + ".real")
	os.symlink(p + ".real", p)
	rec = Rec()
	sc.check_local_changes_after_upgrade({}, rec)
	check("a link is not followed", rec.calls == [], str(rec.calls))
	os.unlink(p)
	with open(p, "w") as f:
		f.write("not json")
	os.chmod(p, 0o600)
	rec = Rec()
	sc.check_local_changes_after_upgrade({}, rec)
	check("a file that is no JSON still warns", [c[0] for c in rec.calls] == ["print_warning", "print_line"], str(rec.calls))
	os.chmod(d, 0o777)
	rec = Rec()
	sc.check_local_changes_after_upgrade({}, rec)
	check("a directory that others can write is ignored", rec.calls == [], str(rec.calls))

	# The preflight reports of both tools, run as bash with "set -euo
	# pipefail" as in the tools, with local changes, before anything else of
	# the tool has run (B185: the migration tool's report named
	# $STORAGE_ROOT, which preflight does not set yet, and stopped with
	# "unbound variable").
	for tool, fn in (("tools/migrate-to-2604.sh", "report_old_roundcube"), ("tools/upgrade-in-place-to-2604.sh", "report_roundcube")):
		check("preflight report (%s): local changes named, exit 0, no unbound variable (B185)" % tool, *preflight_report(tool, fn))

	print()
	print("%d failed" % len(FAILED) if FAILED else "all passed")
	return 1 if FAILED else 0


def save_old_roundcube_modes():
	tool = "tools/upgrade-in-place-to-2604.sh"
	src = open(os.path.join(ROOT, tool), encoding="utf-8").read()
	py = re.search(r"\nROUNDCUBE_PY=\$\(cat <<'EOF'\n.*?\nEOF\n\)\n", src, re.S).group(0)
	funcs = "".join(re.search(r"\n%s\(\) \{.*?\n\}\n" % n, src, re.S).group(0) for n in ("save_old_roundcube", "roundcube_plugin_dirs"))
	d = tempfile.mkdtemp()
	rc = os.path.join(d, "roundcubemail")
	os.makedirs(os.path.join(rc, "config"))
	os.makedirs(os.path.join(rc, "plugins", "archive"))
	os.makedirs(os.path.join(rc, "plugins", "contextmenu", "skins"))
	os.chmod(os.path.join(rc, "plugins", "contextmenu"), 0o755)
	with open(os.path.join(rc, "config", "config.inc.php"), "w") as f:
		f.write(template())
	os.chmod(os.path.join(rc, "config", "config.inc.php"), 0o640)
	for fn in ("contextmenu.php", "skins/a.css"):
		with open(os.path.join(rc, "plugins", "contextmenu", fn), "w") as f:
			f.write("x\n")
		os.chmod(os.path.join(rc, "plugins", "contextmenu", fn), 0o644)
	old_rc = os.path.join(d, "state", "old-roundcube")
	os.makedirs(os.path.dirname(old_rc))
	script = "set -euo pipefail\n" + py + """
say() { echo "$*"; }
die() { echo "DIE $*"; exit 1; }
state_get() { echo; }
state_set() { :; }
RC_DIR=%s
OLD_RC=%s
""" % (rc, old_rc) + funcs + "\nsave_old_roundcube\n"
	r = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
	if r.returncode != 0:
		return False, r.stdout + r.stderr
	modes = {}
	for rel in ("", "plugins.txt", "config.inc.php", "plugins/contextmenu", "plugins/contextmenu/contextmenu.php", "plugins/contextmenu/skins/a.css"):
		modes[rel] = oct(stat.S_IMODE(os.stat(os.path.join(old_rc, rel)).st_mode))
	want = {"": "0o700", "plugins.txt": "0o600", "config.inc.php": "0o600", "plugins/contextmenu": "0o755",
		"plugins/contextmenu/contextmenu.php": "0o644", "plugins/contextmenu/skins/a.css": "0o644"}
	return modes == want, repr(modes)


def preflight_report(tool, fn):
	src = open(os.path.join(ROOT, tool), encoding="utf-8").read()
	py = re.search(r"\nROUNDCUBE_PY=\$\(cat <<'EOF'\n.*?\nEOF\n\)\n", src, re.S)
	funcs = []
	for name in (fn, "roundcube_plugin_dirs"):
		m = re.search(r"\n%s\(\) \{.*?\n\}\n" % name, src, re.S)
		if m:
			funcs.append(m.group(0))
	if not py or not funcs:
		return False, "function or ROUNDCUBE_PY not found"
	d = tempfile.mkdtemp()
	rc = os.path.join(d, "roundcubemail")
	os.makedirs(os.path.join(rc, "config"))
	for p in ("archive", "password", "contextmenu"):
		os.makedirs(os.path.join(rc, "plugins", p))
	with open(os.path.join(rc, "config", "config.inc.php"), "w", encoding="utf-8") as f:
		t = template().replace("'carddav')", "'carddav','contextmenu')")
		i = t.rfind("?>")
		f.write((t[:i] + "$config['draft_autosave'] = 120;\n" + t[i:]) if i >= 0 else t + "$config['draft_autosave'] = 120;\n")
	script = "set -euo pipefail\nunset STORAGE_ROOT\n" + py.group(0) + """
section() { echo "== $*"; }
say() { echo "$*"; }
warn() { echo "WARNING: $*"; }
state_get() { echo; }
remote() { bash -c "$1"; }
declare -A OLD=([CONF_STORAGE_ROOT]=/home/user-data)
RC_DIR=%s
OLD_RC=/root/x/old-roundcube
SELF=%s
HOOK_DIR=/etc/mailinabox/upgrade-2604.d
""" % (rc, os.path.basename(tool)) + "".join(funcs) + "\n%s\n" % fn
	r = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
	out = r.stdout + r.stderr
	ok = (r.returncode == 0 and "unbound variable" not in out and "plugin directory plugins/contextmenu" in out
		and "setting draft_autosave" in out)
	return ok, "exit %d: %s" % (r.returncode, out[:1500])


sys.exit(main())
