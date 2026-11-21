#!/usr/bin/env python3
"""Offline test of the HSTS header in the nginx configuration (B180).

management/web_update.py builds /etc/nginx/conf.d/local.conf from the
templates in conf/ and adds the HSTS header (Strict-Transport-Security) to
each HTTPS server, as the setting "hsts" of the domain in
$STORAGE_ROOT/www/custom.yaml says ("yes", the default, "preload", or
anything else for none). nginx inherits the add_header directives of a
server only into the locations that have no add_header of their own, so
the control panel's location /admin/ (conf/nginx-primaryonly.conf) sent no
HSTS header. This test builds the configuration of the box's own name and of
another domain for each setting and checks that every block of the HTTPS
server that has add_header directives of its own also has the server's HSTS
line, and that no block has one when HSTS is off.

No box needed: the modules that web_update.py imports are replaced by
stand-ins, and the certificate files are temporary files.

Usage: python3 -I tests/fork/nginx-hsts.py
Exit code 0 when every check passed.
"""
import importlib.util
import os
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
MGMT = os.path.join(ROOT, "management")
CONF = os.path.join(ROOT, "conf")

HSTS = {
	"yes": 'add_header Strict-Transport-Security "max-age=15768000" always',
	"preload": 'add_header Strict-Transport-Security "max-age=15768000; includeSubDomains; preload" always',
	"off": None,
}

CUSTOM = {}


def load(certs):
	rtyaml = types.ModuleType("rtyaml")
	rtyaml.load = lambda f: CUSTOM
	stubs = {
		"rtyaml": rtyaml,
		"mailconfig": types.ModuleType("mailconfig"),
		"dns_update": types.ModuleType("dns_update"),
		"ssl_certificates": types.ModuleType("ssl_certificates"),
		"utils": types.ModuleType("utils"),
	}
	stubs["mailconfig"].get_mail_domains = lambda env: set()
	stubs["dns_update"].get_custom_dns_config = lambda env: []
	stubs["dns_update"].get_dns_zones = lambda env: []
	stubs["ssl_certificates"].get_ssl_certificates = lambda env: {}
	stubs["ssl_certificates"].get_domain_ssl_files = lambda domain, certs_, env, **kw: certs
	stubs["ssl_certificates"].check_certificate = lambda *a, **k: ("OK", "")
	stubs["utils"].shell = lambda *a, **k: ""
	stubs["utils"].safe_domain_name = lambda name: name
	stubs["utils"].sort_domains = lambda domains, env: sorted(domains)
	sys.modules.update(stubs)
	spec = importlib.util.spec_from_file_location("web_update", os.path.join(MGMT, "web_update.py"))
	mod = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(mod)
	return mod


def tokens(text):
	# nginx's tokens: words, quoted strings (kept with their quotes), ";", "{"
	# and "}"; comments are left out.
	i, n = 0, len(text)
	while i < n:
		c = text[i]
		if c.isspace():
			i += 1
		elif c == "#":
			while i < n and text[i] != "\n":
				i += 1
		elif c in ";{}":
			yield c
			i += 1
		elif c in "\"'":
			j = i + 1
			while j < n and text[j] != c:
				j += 2 if text[j] == "\\" else 1
			yield text[i:j + 1]
			i = j + 1
		else:
			j = i
			while j < n and not text[j].isspace() and text[j] not in ";{}\"'":
				j += 1
			yield text[i:j]
			i = j


def parse(text):
	# A list of blocks: (name, directives, children); a directive is the
	# words of one statement joined by single spaces.
	stack = [("top", [], [])]
	words = []
	for t in tokens(text):
		if t == ";":
			stack[-1][1].append(" ".join(words))
			words = []
		elif t == "{":
			block = (" ".join(words), [], [])
			stack[-1][2].append(block)
			stack.append(block)
			words = []
		elif t == "}":
			stack.pop()
		else:
			words.append(t)
	return stack[0]


def walk(block, path=()):
	yield path + (block[0],), block
	for child in block[2]:
		yield from walk(child, path + (block[0],))


def check(conf, setting, desc):
	errs = []
	want = HSTS[setting]
	servers = [b for b in parse(conf)[2] if b[0] == "server" and any(d.startswith("listen 443") for d in b[1])]
	if not servers:
		return ["%s: no HTTPS server block" % desc]
	for server in servers:
		own = [d for d in server[1] if d.startswith("add_header Strict-Transport-Security")]
		if want and own != [want]:
			errs.append("%s: the server's HSTS lines are %r, expected %r" % (desc, own, want))
		if not want and own:
			errs.append("%s: HSTS is off, but the server has %r" % (desc, own))
		for path, block in walk(server):
			headers = [d for d in block[1] if d.startswith("add_header ")]
			hsts = [d for d in headers if d.startswith("add_header Strict-Transport-Security")]
			if not headers:
				continue  # inherits the server's (or its parent's) headers
			if want and hsts != [want]:
				errs.append("%s: %s has add_header of its own but HSTS %r" % (desc, " > ".join(path[1:]), hsts))
			if not want and hsts:
				errs.append("%s: HSTS is off, but %s has %r" % (desc, " > ".join(path[1:]), hsts))
	if "# HSTS HEADER HERE" in conf:
		errs.append("%s: the placeholder is left in the configuration" % desc)
	return errs


def main():
	bad = 0
	checks = 0
	with tempfile.TemporaryDirectory() as tmp:
		key = os.path.join(tmp, "key.pem")
		cert = os.path.join(tmp, "cert.pem")
		for p in (key, cert):
			with open(p, "w") as f:
				f.write("test\n")
		os.makedirs(os.path.join(tmp, "www", "default"))
		custom = os.path.join(tmp, "www", "custom.yaml")
		env = {"STORAGE_ROOT": tmp, "PRIMARY_HOSTNAME": "box.example.com", "PUBLIC_IP": "192.0.2.1"}
		wu = load({"private-key": key, "certificate": cert})

		def read(fn):
			with open(os.path.join(CONF, fn), encoding="utf-8") as f:
				return f.read()
		t0, t1, t2 = read("nginx.conf"), read("nginx-alldomains.conf"), read("nginx-primaryonly.conf")
		if "# HSTS HEADER HERE" not in t2:
			print("FAIL conf/nginx-primaryonly.conf has no HSTS placeholder in /admin/")
			bad += 1

		for setting in ("yes", "preload", "off"):
			for domain, templates in (("box.example.com", [t0, t1, t2]), ("other.example.net", [t0, t1])):
				CUSTOM.clear()
				if os.path.exists(custom):
					os.unlink(custom)
				if setting != "yes":
					# "yes" is also the default without custom.yaml.
					CUSTOM[domain] = {"hsts": setting}
					with open(custom, "w") as f:
						f.write("x\n")
				desc = "%s, hsts %s" % (domain, setting)
				conf = wu.make_domain_config(domain, templates, {}, env)
				errs = check(conf, setting, desc)
				checks += 1
				if domain == "box.example.com":
					admin = [b for p, b in walk(parse(conf)) if b[0] == "location /admin/"]
					if len(admin) != 1:
						errs.append("%s: %d locations /admin/" % (desc, len(admin)))
				for e in errs:
					print("FAIL " + e)
				if errs:
					bad += 1
				else:
					print("ok   " + desc)

		# The check itself: the configuration as it was before the fix (no
		# placeholder) must fail.
		CUSTOM.clear()
		if os.path.exists(custom):
			os.unlink(custom)
		old = wu.make_domain_config("box.example.com", [t0, t1, t2.replace("# HSTS HEADER HERE", "# (removed)")], {}, env)
		checks += 1
		if any("location /admin/" in e for e in check(old, "yes", "old")):
			print("ok   the configuration without the placeholder fails the check")
		else:
			print("FAIL the configuration without the placeholder passes the check")
			bad += 1

	print("%d of %d checks passed" % (checks - bad, checks) if bad else "all %d checks passed" % checks)
	return 1 if bad else 0


if __name__ == "__main__":
	sys.exit(main())
