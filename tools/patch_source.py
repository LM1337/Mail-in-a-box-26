#!/usr/bin/python3
#
# Apply the fork's changes to a third-party source tree that setup installs
# (such as Z-Push, before setup/zpush.sh moves it to /usr/local/lib/z-push),
# or check that a tree has them:
#
#   tools/patch_source.py DIR PATCHFILE           apply the changes
#   tools/patch_source.py --check DIR PATCHFILE   check, write nothing
#   tools/patch_source.py --digest PATCHFILE      print a checksum of the
#                                                 changes (SHA-256, hex)
#
# PATCHFILE holds blocks, each for a file below DIR (lines starting with "#"
# outside a block are comments). A replacement of exact text:
#
#   @@ relative/path/of/the/file.php
#   <<<
#   the old text, line by line, exactly as in the file
#   ===
#   the new text
#   >>>
#
# and text that must not be in the file once all its replacements are made,
# one piece of text per line (to make sure that no other copy of a line that
# a replacement changes is left, e.g. in a later version of the code):
#
#   @@ relative/path/of/the/file.php
#   !!!
#   text that must not occur
#   >>>
#
# The new text of a replacement must not be empty: a block that only deletes
# text could not be told apart from the original once it is applied. Keep a
# comment in its place (such as "// MIAB-Bnnn: ... removed").
#
# --digest hashes the blocks as parsed (paths, old, new and forbidden text),
# not the file: comments and empty lines between the blocks do not change
# it. setup/zpush.sh marks the installed tree with it, so that only a change
# of the changes themselves makes every box install Z-Push again.
#
# A replacement is applied when its old text occurs exactly once in the file.
# It counts as applied already when its new text occurs exactly once and the
# old text occurs no more often than within the new text, so a second run
# leaves a changed tree alone. Any other state (the old text missing or found
# twice, e.g. after a version change of the third-party code), and text that
# must not occur, is an error, and no file is written: every file is checked
# before the first one is written, and setup stops instead of running code
# that the fork has not checked. --check succeeds only when every replacement
# counts as applied and no text that must not occur is found.
#
# Files are read and written as tools/write_conf.py does: the path is opened
# one directory at a time without following a symbolic link that another
# account could have put there, and a changed file is replaced atomically (a
# new file in the same directory, renamed over it), keeping owner and mode.
# Each file must be a regular file in a directory of root's own (no write
# permission for a group or others): this is for code that root installed.
#
# Prints one line per changed file (with --check: per block that is not
# applied). Exit code 0 (also when nothing changed), 1 on an error or, with
# --check, when the tree does not have every change.

import hashlib
import json
import os
import stat
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import write_conf  # noqa: E402


def parse(text):
	"""[(path, old, new)] and [(path, forbidden text)] from the text of a
	patch file."""
	blocks, forbidden = [], []
	path = None
	state = None  # None, "old", "new", "forbid"
	old, new = [], []
	for n, line in enumerate(text.split("\n"), 1):
		if state is None:
			if line.startswith("@@ "):
				path = line[3:].strip()
			elif line in ("<<<", "!!!"):
				if not path:
					raise ValueError("line %d: a block without a file (@@ path)" % n)
				state, old, new = ("old" if line == "<<<" else "forbid"), [], []
			elif line.strip() == "" or line.startswith("#"):
				pass
			else:
				raise ValueError("line %d: unexpected text outside a block" % n)
		elif state == "forbid":
			if line == ">>>":
				state = None
			elif line == "":
				raise ValueError("line %d: an empty line in a block of text that must not occur" % n)
			else:
				forbidden.append((path, line))
		elif state == "old":
			if line == "===":
				state = "new"
			else:
				old.append(line)
		else:
			if line == ">>>":
				if not old:
					raise ValueError("line %d: a block with an empty old text" % n)
				if not "".join(new).strip():
					raise ValueError("line %d: a block with an empty new text (a deletion cannot be told apart "
						"from the original once it is applied: keep a comment in its place)" % n)
				blocks.append((path, "\n".join(old) + "\n", "\n".join(new) + "\n"))
				state = None
			else:
				new.append(line)
	if state is not None:
		raise ValueError("the last block is not closed (>>>)")
	return blocks, forbidden


def digest(blocks, forbidden):
	"""SHA-256 (hex) of the changes as parsed: the same for two patch files
	that differ only in comments or empty lines between the blocks."""
	data = json.dumps({"blocks": blocks, "forbidden": forbidden}, ensure_ascii=False, separators=(",", ":"))
	return hashlib.sha256(data.encode("utf-8")).hexdigest()


def read_file(path):
	"""The content of the regular file `path`, in a directory of root's own."""
	directory, name = os.path.split(os.path.abspath(path))
	dfd = write_conf.open_dir(directory)
	try:
		if not write_conf._root_only(os.fstat(dfd)):
			raise OSError("%s: not a directory of root's own" % directory)
		st = os.stat(name, dir_fd=dfd, follow_symlinks=False)
		if not stat.S_ISREG(st.st_mode):
			raise OSError("%s is not a regular file" % path)
		fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dfd)
		with os.fdopen(fd, "rb") as f:
			if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
				raise OSError("%s is not a regular file" % path)
			return f.read()
	finally:
		os.close(dfd)


def applied(data, old, new):
	"""Whether the replacement old -> new is made in data."""
	return data.count(new) == 1 and data.count(old) == new.count(old)


def run(directory, blocks, forbidden, check=False):
	"""Apply the blocks to the files below directory (every file is checked
	before the first one is written), or with check=True only report the
	blocks that are not applied. Returns the list of problems (check) or
	raises ValueError."""
	files = []
	for path, _, _ in blocks:
		if path not in files:
			files.append(path)
	for path, _ in forbidden:
		if path not in files:
			files.append(path)
	result, problems = [], []
	for rel in files:
		if rel.startswith("/") or ".." in rel.split("/"):
			raise ValueError("%s: the path must be relative and stay below %s" % (rel, directory))
		full = os.path.join(directory, rel)
		data = read_file(full).decode("utf-8")
		for n, (path, old, new) in enumerate(blocks, 1):
			if path != rel or applied(data, old, new):
				continue
			if check:
				problems.append("%s: change %d is not applied" % (full, n))
				continue
			if data.count(old) != 1:
				raise ValueError("%s: change %d does not apply (its old text is found %d times, its new text %d times)"
					% (full, n, data.count(old), data.count(new)))
			data = data.replace(old, new)
		for path, text in forbidden:
			if path == rel and text in data:
				msg = "%s: still has text that the fork's changes must remove or replace: %s" % (full, text.strip())
				if check:
					problems.append(msg)
				else:
					raise ValueError(msg)
		result.append((full, data.encode("utf-8")))
	if check:
		return problems
	for full, data in result:
		if write_conf.write_if_changed(full, data):
			print("patched %s" % full)
	return []


if __name__ == "__main__":
	args = sys.argv[1:]
	mode = args[0] if args[:1] in (["--check"], ["--digest"]) else None
	if mode:
		args = args[1:]
	if len(args) != (1 if mode == "--digest" else 2) or any(a.startswith("-") for a in args):
		print("usage: tools/patch_source.py [--check] DIR PATCHFILE | --digest PATCHFILE", file=sys.stderr)
		sys.exit(1)
	try:
		with open(args[-1], encoding="utf-8") as f:
			blocks, forbidden = parse(f.read())
		if mode == "--digest":
			print(digest(blocks, forbidden))
			sys.exit(0)
		problems = run(args[0], blocks, forbidden, mode == "--check")
	except (OSError, ValueError, UnicodeDecodeError) as e:
		print("patch_source.py: %s" % e, file=sys.stderr)
		sys.exit(1)
	for p in problems:
		print("patch_source.py: %s" % p, file=sys.stderr)
	sys.exit(1 if problems else 0)
