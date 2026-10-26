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
# MODE (octal, default 644). The new file is created with O_EXCL and written
# through its descriptor, and the old one is only renamed over, so no symbolic
# link is followed in a directory that another account may write (such as
# /etc/dovecot, which belongs to mail): a symbolic link at FILE is refused
# there, and followed only in a directory of root's own.
#
# Exit code 0 (also when nothing changed), 1 on an error.

import os
import stat
import sys


def write_if_changed(path, data, new_mode=0o644, _depth=0):
	"""Write data (bytes) to path if it differs; returns True if it wrote."""
	directory = os.path.dirname(os.path.abspath(path))
	name = os.path.basename(path)
	dfd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
	try:
		try:
			st = os.stat(name, dir_fd=dfd, follow_symlinks=False)
		except FileNotFoundError:
			st = None
		if st is not None and stat.S_ISLNK(st.st_mode):
			# A link that only root could have put there (the directory is
			# root's own and not writable by group or others) is followed, as
			# the plain write of earlier versions did.
			dst = os.fstat(dfd)
			if dst.st_uid != 0 or dst.st_mode & 0o022:
				raise OSError("%s is a symbolic link in a directory that another account may write" % path)
			if _depth >= 8:
				raise OSError("%s: too many levels of symbolic links" % path)
			return write_if_changed(os.path.join(directory, os.readlink(name, dir_fd=dfd)), data, new_mode, _depth + 1)
		if st is not None:
			if not stat.S_ISREG(st.st_mode):
				raise OSError("%s is not a regular file" % path)
			fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dfd)
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


if __name__ == "__main__":
	if len(sys.argv) not in (2, 3):
		print("usage: tools/write_conf.py FILE [MODE] < CONTENT", file=sys.stderr)
		sys.exit(1)
	try:
		mode = int(sys.argv[2], 8) if len(sys.argv) == 3 else 0o644
		write_if_changed(sys.argv[1], sys.stdin.buffer.read(), mode)
	except (OSError, ValueError) as e:
		print("write_conf.py: %s: %s" % (sys.argv[1], e), file=sys.stderr)
		sys.exit(1)
