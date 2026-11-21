#!/usr/bin/env python3
"""Offline check of the control panel's assets (/admin/assets/).

The control panel's templates (management/templates/*.html) load their
scripts, styles and icons from /admin/assets/, which nginx serves from
/usr/local/lib/mailinabox/vendor/assets (conf/nginx-primaryonly.conf).
setup/management.sh fills that directory: jQuery, Bootstrap's release
archive and the fork's icons from branding/. This check reads the three and
reports every asset that a template asks for and setup does not install
(the browser gets 404), and every icon that setup copies but the repository
does not have (setup would stop at the copy).

No box needed. Bootstrap's archive is not read (setup downloads it); its
files are taken from the list of the 3.4.1 release below.

Usage: python3 -I tests/fork/panel-assets.py
Exit code 0 when every check passed.
"""
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))

# The files of bootstrap-3.4.1-dist.zip that a template may name (the
# archive has more: the unminified files, the maps and the fonts).
BOOTSTRAP_341 = {
	"css/bootstrap.min.css", "css/bootstrap-theme.min.css", "css/bootstrap.css",
	"css/bootstrap-theme.css", "js/bootstrap.min.js", "js/bootstrap.js", "js/npm.js",
	"fonts/glyphicons-halflings-regular.eot", "fonts/glyphicons-halflings-regular.svg",
	"fonts/glyphicons-halflings-regular.ttf", "fonts/glyphicons-halflings-regular.woff",
	"fonts/glyphicons-halflings-regular.woff2",
}


def read(*path):
	with open(os.path.join(ROOT, *path), encoding="utf-8") as f:
		return f.read()


def installed(sh):
	# The paths below vendor/assets that setup/management.sh puts there, from
	# its own lines: what it downloads to "$assets_new/<name>", Bootstrap's
	# archive, and the files of its cp into "$assets_new/branding/".
	ret = {}
	for m in re.finditer(r'"\$assets_new/([A-Za-z0-9._-]+)"', sh):
		ret[m.group(1)] = "download"
	m = re.search(r'bootstrap_version=(\S+)', sh)
	if m and m.group(1) == "3.4.1" and re.search(r'mv "\$assets_new/bootstrap-\$bootstrap_version-dist" "\$assets_new/bootstrap"', sh):
		for p in BOOTSTRAP_341:
			ret["bootstrap/" + p] = "bootstrap"
	m = re.search(r'^cp ((?:[^\n]|\\\n)*?)"\$assets_new/branding/"', sh, re.M)
	if m:
		for src in m.group(1).replace("\\\n", " ").split():
			if src.startswith("branding/"):
				ret["branding/" + src[len("branding/"):]] = src
	return ret


def main():
	bad = []
	sh = read("setup", "management.sh")
	nginx = read("conf", "nginx-primaryonly.conf")

	# nginx serves /admin/assets from the directory that setup fills.
	m = re.search(r"location /admin/assets \{\s*alias (\S+);", nginx)
	inst = re.search(r"^inst_dir=(\S+)$", sh, re.M)
	assets_dir = re.search(r'^assets_dir=(\S+)$', sh, re.M)
	if not m or not inst or not assets_dir:
		bad.append("could not find the alias of /admin/assets or the assets directory of setup/management.sh")
	elif assets_dir.group(1).replace("$inst_dir", inst.group(1)) != m.group(1):
		bad.append("nginx serves /admin/assets from %s, setup fills %s" % (m.group(1), assets_dir.group(1)))

	files = installed(sh)
	if not any(v.startswith("branding/") for v in files.values()):
		bad.append("found no copy of branding/ in setup/management.sh")
	for path, src in sorted(files.items()):
		if src.startswith("branding/") and not os.path.isfile(os.path.join(ROOT, src)):
			bad.append("setup/management.sh copies %s, which is not in the repository" % src)

	refs = {}
	for fn in sorted(glob.glob(os.path.join(ROOT, "management", "templates", "*.html"))):
		with open(fn, encoding="utf-8") as f:
			for m in re.finditer(r"/admin/assets/([^\"'\s?#)]+)", f.read()):
				refs.setdefault(m.group(1), set()).add(os.path.basename(fn))
	if "branding/favicon.ico" not in refs:
		bad.append("no template names branding/favicon.ico (the check would not see it)")
	for path, names in sorted(refs.items()):
		if path not in files:
			bad.append("%s asks for /admin/assets/%s, which setup does not install" % (", ".join(sorted(names)), path))

	# The check itself: without favicon.ico in setup's copy (the planned item
	# of rc7 to v78-r2604.4), the template's reference must be reported.
	reduced = installed(sh.replace(" branding/favicon.ico ", " ", 1))
	if "branding/favicon.ico" in reduced or "branding/favicon.ico" not in files:
		bad.append("the check does not see a favicon.ico that setup does not copy")

	for b in bad:
		print("FAIL " + b)
	print("%d assets named by the templates, %d installed by setup: %s" % (
		len(refs), len(files), "%d problems" % len(bad) if bad else "all checks passed"))
	return 1 if bad else 0


if __name__ == "__main__":
	sys.exit(main())
