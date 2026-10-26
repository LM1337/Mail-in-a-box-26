#!/usr/bin/python3
#
# Apply the fork's changes to a third-party source tree that setup installs
# (such as Z-Push in /usr/local/lib/z-push), for setup:
#
#   tools/patch_source.py DIR PATCHFILE
#
# PATCHFILE holds blocks of exact text replacements, each for a file below
# DIR (lines starting with "#" outside a block are comments):
#
#   @@ relative/path/of/the/file.php
#   <<<
#   the old text, line by line, exactly as in the file
#   ===
#   the new text
#   >>>
#
# A block is applied when its old text occurs exactly once in the file. It
# counts as applied already when its new text occurs exactly once and the old
# text does not occur, so setup can run this on every run: an installation
# from before the change is changed, one with the change is left alone. Any
# other state (the old text missing or found twice, e.g. after a version
# change of the third-party code) is an error, and no file is written: every
# file is checked before the first one is written, and setup stops instead of
# running code that the fork has not checked.
#
# Files are read and written as tools/write_conf.py does: the path is opened
# one directory at a time without following a symbolic link that another
# account could have put there, and a changed file is replaced atomically (a
# new file in the same directory, renamed over it), keeping owner and mode.
# Each file must be in a directory of root's own (no write permission for a
# group or others): this is for code that root installed.
#
# Prints one line per changed file. Exit code 0 (also when nothing changed),
# 1 on an error.

import os
import stat
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import write_conf  # noqa: E402


def parse(text):
	"""[(path, old, new)] from the text of a patch file."""
	blocks = []
	path = None
	state = None  # None, "old", "new"
	old, new = [], []
	for n, line in enumerate(text.split("\n"), 1):
		if state is None:
			if line.startswith("@@ "):
				path = line[3:].strip()
			elif line == "<<<":
				if not path:
					raise ValueError("line %d: a block without a file (@@ path)" % n)
				state, old, new = "old", [], []
			elif line.strip() == "" or line.startswith("#"):
				pass
			else:
				raise ValueError("line %d: unexpected text outside a block" % n)
		elif state == "old":
			if line == "===":
				state = "new"
			else:
				old.append(line)
		else:
			if line == ">>>":
				if not old:
					raise ValueError("line %d: a block with an empty old text" % n)
				blocks.append((path, "\n".join(old) + "\n", "\n".join(new) + "\n" if new else ""))
				state = None
			else:
				new.append(line)
	if state is not None:
		raise ValueError("the last block is not closed (>>>)")
	return blocks


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
			return f.read()
	finally:
		os.close(dfd)


def apply(directory, blocks):
	"""Apply the blocks to the files below directory; every file is checked
	before the first one is written."""
	files = []
	for path, _, _ in blocks:
		if path not in files:
			files.append(path)
	result = []
	for rel in files:
		if rel.startswith("/") or ".." in rel.split("/"):
			raise ValueError("%s: the path must be relative and stay below %s" % (rel, directory))
		full = os.path.join(directory, rel)
		data = read_file(full).decode("utf-8")
		for n, (path, old, new) in enumerate(blocks, 1):
			if path != rel:
				continue
			if new and data.count(new) == 1 and old not in data:
				continue
			if data.count(old) != 1:
				raise ValueError("%s: change %d does not apply (its old text is found %d times, its new text %d times)"
					% (full, n, data.count(old), data.count(new) if new else 0))
			data = data.replace(old, new)
		result.append((full, data.encode("utf-8")))
	for full, data in result:
		if write_conf.write_if_changed(full, data):
			print("patched %s" % full)


if __name__ == "__main__":
	if len(sys.argv) != 3:
		print("usage: tools/patch_source.py DIR PATCHFILE", file=sys.stderr)
		sys.exit(1)
	try:
		with open(sys.argv[2], encoding="utf-8") as f:
			blocks = parse(f.read())
		apply(sys.argv[1], blocks)
	except (OSError, ValueError, UnicodeDecodeError) as e:
		print("patch_source.py: %s" % e, file=sys.stderr)
		sys.exit(1)
