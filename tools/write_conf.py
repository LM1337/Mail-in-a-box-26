#!/usr/bin/python3
#
# Write a configuration file for setup: tools/write_conf.py FILE [MODE] < CONTENT
#
# The file is replaced only when its content changes, and then atomically:
# the new content goes into a new file in the same directory, which is
# renamed over the old one. A service that reads its configuration at any
# moment sees the old file or the new one, never an empty or half-written
# one. Dovecot's config process, for example, starts on demand and parses all
# files at that moment; it once read auth-sql.conf.ext while setup had just
# truncated it, and Dovecot ran without a passdb (B120).
#
# An existing file keeps its owner and mode; a new one belongs to root with
# MODE (octal, default 644). The path is opened one directory at a time,
# without following a symbolic link that another account could have put
# there: a link (in the directories on the way, or at FILE) is followed only
# where it sits in a directory of root's own that no group or other account
# may write, and refused anywhere else. The new file is created with O_EXCL
# and written through its descriptor, and the old one is only renamed over.
#
# This does not make a directory that another account may write safe to
# write into: that account can still change what is in it (and so what the
# service reads). Setup's own configuration directories belong to root
# (setup/mail-dovecot.sh gives /etc/dovecot back to root with --own-tree).
#
# tools/write_conf.py --own-tree DIR USER GROUP
#   gives DIR and everything below it to USER:GROUP and takes away the
#   write permission of the group and every permission of others (mode
#   & ~027). Top down: a directory is changed through its open descriptor
#   before what is in it is looked at, so an account that owned it can no
#   longer change it from then on. Symbolic links are not followed (only
#   their own owner changes); a regular file with more than one hard link
#   and anything that is not a directory, regular file or link are left
#   alone with a warning.
#
# tools/write_conf.py --own-tree DIR USER GROUP FILEMODE DIRMODE
#   the same, but regular files get FILEMODE and directories DIRMODE (octal).
#
# tools/write_conf.py --own PATH USER GROUP MODE
#   gives PATH itself to USER:GROUP with MODE (octal), through a descriptor:
#   for a file or directory in a directory that another account may write,
#   where chown and chmod by path would follow a symbolic link (or change a
#   hard link to another file) that that account put there (B147). The path
#   is opened as above; PATH must be a directory or a regular file with one
#   hard link, and a symbolic link or anything else is refused.
#
# tools/write_conf.py --own-root-only PATH USER GROUP MODE
#   the same, but PATH must belong to root already (checked through the
#   descriptor): for a file or directory of root's in a directory that another
#   account owns ($STORAGE_ROOT/mail and users.sqlite in the storage user's
#   home), which that account could have replaced with one of its own; --own
#   would make that one root's.
#
# tools/write_conf.py --check-own PATH...
#   changes nothing: prints "PATH: why" for each PATH that --own would refuse
#   (a missing PATH is fine) and exits 1 if there is one. setup/start.sh runs
#   it before setup changes anything (B147).
#
# tools/write_conf.py --check-own-root-only PATH...
#   the same for --own-root-only: also a PATH that does not belong to root
#   (B210).
#
# Exit code 0 (also when nothing changed), 1 on an error.

import grp
import os
import pwd
import stat
import sys

MAX_LINKS = 40
ROOT_UID = 0 # the owner that --own-root-only requires (a test may set another)


def _root_only(st):
	"""A directory that only root may change."""
	return st.st_uid == 0 and not st.st_mode & 0o022


def open_dir(path):
	"""Open the directory `path` and return its descriptor, one component at
	a time from /, with O_NOFOLLOW. A symbolic link on the way is resolved
	only when the directory that holds it is root's own (_root_only), as
	the kernel would; anywhere else it raises OSError."""
	if not os.path.isabs(path):
		path = os.path.join(os.getcwd(), path)
	stack = [os.open("/", os.O_RDONLY | os.O_DIRECTORY)]
	todo = [c for c in path.split("/") if c not in ("", ".")]
	links = 0
	try:
		while todo:
			name = todo.pop(0)
			if name == "..":
				if len(stack) > 1:
					os.close(stack.pop())
				continue
			st = os.stat(name, dir_fd=stack[-1], follow_symlinks=False)
			if stat.S_ISLNK(st.st_mode):
				if not _root_only(os.fstat(stack[-1])):
					raise OSError("%s: the symbolic link %s is in a directory that another account may write"
						% (path, name))
				links += 1
				if links > MAX_LINKS:
					raise OSError("%s: too many levels of symbolic links" % path)
				target = os.readlink(name, dir_fd=stack[-1])
				if target.startswith("/"):
					while len(stack) > 1:
						os.close(stack.pop())
				todo[:0] = [c for c in target.split("/") if c not in ("", ".")]
				continue
			if not stat.S_ISDIR(st.st_mode):
				raise NotADirectoryError("%s: %s is not a directory" % (path, name))
			stack.append(os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=stack[-1]))
		fd = stack.pop()
		return fd
	finally:
		for fd in stack:
			os.close(fd)


def write_if_changed(path, data, new_mode=0o644, _depth=0):
	"""Write data (bytes) to path if it differs; returns True if it wrote."""
	directory, name = os.path.split(os.path.abspath(path))
	dfd = open_dir(directory)
	try:
		try:
			st = os.stat(name, dir_fd=dfd, follow_symlinks=False)
		except FileNotFoundError:
			st = None
		if st is not None and stat.S_ISLNK(st.st_mode):
			# A link that only root could have put there is followed, as the
			# plain write of earlier versions did.
			if not _root_only(os.fstat(dfd)):
				raise OSError("%s is a symbolic link in a directory that another account may write" % path)
			if _depth >= MAX_LINKS:
				raise OSError("%s: too many levels of symbolic links" % path)
			return write_if_changed(os.path.join(directory, os.readlink(name, dir_fd=dfd)), data, new_mode, _depth + 1)
		if st is not None:
			if not stat.S_ISREG(st.st_mode):
				raise OSError("%s is not a regular file" % path)
			fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dfd)
			with os.fdopen(fd, "rb") as f:
				if f.read() == data:
					return False
		for i in range(100):
			tmp = ".%s.%s.%d" % (name, os.urandom(6).hex(), i)
			try:
				fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=dfd)
				break
			except FileExistsError:
				continue
		else:
			raise OSError("could not create a temporary file in %s" % directory)
		try:
			with os.fdopen(fd, "wb") as f:
				f.write(data)
				f.flush()
				if st is not None:
					os.fchown(f.fileno(), st.st_uid, st.st_gid)
					os.fchmod(f.fileno(), stat.S_IMODE(st.st_mode))
				else:
					os.fchmod(f.fileno(), new_mode)
			os.rename(tmp, name, src_dir_fd=dfd, dst_dir_fd=dfd)
		except BaseException:
			try:
				os.unlink(tmp, dir_fd=dfd)
			except OSError:
				pass
			raise
		return True
	finally:
		os.close(dfd)


def own_tree(path, uid, gid, warn=print, file_mode=None, dir_mode=None):
	"""See --own-tree in the header."""
	dfd = open_dir(path)
	try:
		_own_dir(dfd, path.rstrip("/") or "/", uid, gid, warn, file_mode, dir_mode)
	finally:
		os.close(dfd)


def _new_mode(st, mode):
	return stat.S_IMODE(st.st_mode) & ~0o027 if mode is None else mode


def _own_dir(dfd, label, uid, gid, warn, file_mode=None, dir_mode=None):
	st = os.fstat(dfd)
	os.fchown(dfd, uid, gid)
	os.fchmod(dfd, _new_mode(st, dir_mode))
	for name in sorted(os.listdir(dfd)):
		where = "%s/%s" % (label, name)
		st = os.stat(name, dir_fd=dfd, follow_symlinks=False)
		if stat.S_ISLNK(st.st_mode):
			os.chown(name, uid, gid, dir_fd=dfd, follow_symlinks=False)
		elif stat.S_ISDIR(st.st_mode):
			fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dfd)
			try:
				_own_dir(fd, where, uid, gid, warn, file_mode, dir_mode)
			finally:
				os.close(fd)
		elif stat.S_ISREG(st.st_mode):
			fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_NOCTTY, dir_fd=dfd)
			try:
				fst = os.fstat(fd)
				if not stat.S_ISREG(fst.st_mode):
					warn("write_conf.py: %s changed while it was looked at, left alone" % where)
				elif fst.st_nlink > 1:
					warn("write_conf.py: %s has %d hard links, left alone" % (where, fst.st_nlink))
				else:
					os.fchown(fd, uid, gid)
					os.fchmod(fd, _new_mode(fst, file_mode))
			finally:
				os.close(fd)
		else:
			warn("write_conf.py: %s is not a directory, regular file or link, left alone" % where)


def _own_refuses(path, st):
	"""Why --own refuses PATH with the lstat result st, or None."""
	if stat.S_ISLNK(st.st_mode):
		return "%s is a symbolic link" % path
	if not (stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode)):
		return "%s is not a directory or regular file" % path
	if stat.S_ISREG(st.st_mode) and st.st_nlink > 1:
		return "%s has %d hard links" % (path, st.st_nlink)
	return None


def _not_root_refusal(path, uid):
	return ("%s belongs to uid %d, not to root, and is not taken over: another "
		"account may have put it there. Check it, and give it to root (chown root:root) "
		"if it is the box's own" % (path, uid))


def check_own(path, root_only=False):
	"""See --check-own and --check-own-root-only in the header: why --own
	(--own-root-only) would refuse PATH, or None."""
	directory, name = os.path.split(os.path.abspath(path))
	try:
		dfd = open_dir(directory)
	except FileNotFoundError:
		return None
	except OSError as e:
		return str(e)
	try:
		try:
			st = os.stat(name, dir_fd=dfd, follow_symlinks=False)
		except FileNotFoundError:
			return None
		why = _own_refuses(path, st)
		if why is None and root_only and st.st_uid != ROOT_UID:
			why = _not_root_refusal(path, st.st_uid)
		return why
	finally:
		os.close(dfd)


def own(path, uid, gid, mode, root_only=False):
	"""See --own and --own-root-only in the header."""
	directory, name = os.path.split(os.path.abspath(path))
	dfd = open_dir(directory)
	try:
		st = os.stat(name, dir_fd=dfd, follow_symlinks=False)
		if stat.S_ISLNK(st.st_mode) or not (stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode)):
			raise OSError(_own_refuses(path, st))
		fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_NOCTTY, dir_fd=dfd)
	finally:
		os.close(dfd)
	try:
		fst = os.fstat(fd)
		if (fst.st_dev, fst.st_ino) != (st.st_dev, st.st_ino):
			raise OSError("%s changed while it was looked at" % path)
		if stat.S_ISREG(fst.st_mode) and fst.st_nlink > 1:
			raise OSError("%s has %d hard links" % (path, fst.st_nlink))
		if root_only and fst.st_uid != ROOT_UID:
			raise OSError(_not_root_refusal(path, fst.st_uid))
		os.fchown(fd, uid, gid)
		os.fchmod(fd, mode)
	finally:
		os.close(fd)


if __name__ == "__main__":
	try:
		if len(sys.argv) in (5, 7) and sys.argv[1] == "--own-tree":
			modes = [int(m, 8) for m in sys.argv[5:7]] or [None, None]
			own_tree(sys.argv[2], pwd.getpwnam(sys.argv[3]).pw_uid, grp.getgrnam(sys.argv[4]).gr_gid,
				file_mode=modes[0], dir_mode=modes[1])
			sys.exit(0)
		if len(sys.argv) >= 3 and sys.argv[1] in ("--check-own", "--check-own-root-only"):
			root_only = sys.argv[1] == "--check-own-root-only"
			problems = list(dict.fromkeys(p for p in (check_own(a, root_only) for a in sys.argv[2:]) if p))
			for p in problems:
				print(p)
			sys.exit(1 if problems else 0)
		if len(sys.argv) == 6 and sys.argv[1] in ("--own", "--own-root-only"):
			own(sys.argv[2], pwd.getpwnam(sys.argv[3]).pw_uid, grp.getgrnam(sys.argv[4]).gr_gid, int(sys.argv[5], 8),
				root_only=sys.argv[1] == "--own-root-only")
			sys.exit(0)
		if len(sys.argv) not in (2, 3) or sys.argv[1].startswith("--"):
			print("usage: tools/write_conf.py FILE [MODE] < CONTENT\n"
				"       tools/write_conf.py --own-tree DIR USER GROUP [FILEMODE DIRMODE]\n"
				"       tools/write_conf.py --own PATH USER GROUP MODE\n"
				"       tools/write_conf.py --own-root-only PATH USER GROUP MODE\n"
				"       tools/write_conf.py --check-own PATH...\n"
				"       tools/write_conf.py --check-own-root-only PATH...", file=sys.stderr)
			sys.exit(1)
		mode = int(sys.argv[2], 8) if len(sys.argv) == 3 else 0o644
		write_if_changed(sys.argv[1], sys.stdin.buffer.read(), mode)
	except (OSError, ValueError, KeyError) as e:
		args = sys.argv[2:3] if sys.argv[1:2] in (["--own-tree"], ["--own"], ["--own-root-only"]) else sys.argv[1:2]
		print("write_conf.py: %s: %s" % ("".join(args), e), file=sys.stderr)
		sys.exit(1)
