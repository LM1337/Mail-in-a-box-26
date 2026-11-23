#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Offline test of the comparison of tools/update-check.sh after -- python3
stdlib only, no box needed (B201).

"update-check.sh after" compares the files of before/ and after/ with the
rules of tools/expected-changes/. This test runs its Python part
(compare_states) on states in a temporary directory and checks:

  * the Postfix parameters it records include tls_eecdh_auto_curves and
    tls_ffdhe_auto_groups;
  * a key of postconf.txt or doveconf.txt that only after/ has (recorded by
    a newer version of the tool) is "newly recorded (not judged)": no
    unexpected change, counted in the RESULT line, exit code 0;
  * a changed value of a key that both records have is still judged
    (unexpected without a rule, expected with one);
  * in other files a new line is still unexpected;
  * without anything new the RESULT line is the same as before;
  * every systemd drop-in that setup writes (a literal path in setup/*.sh
    that is not only removed there) is accepted as new by a "dropins.txt +"
    rule of tools/expected-changes/ (T5b of v78-r2604.5: the drop-in of
    spampd's restart record was missing, so "after" ended "CHANGED");
  * after a change of the Ubuntu release, the log audit of "after" adds
    tests/fork/log-audit-allow-old-box.txt (B187).

  tests/fork/update-check-compare.py

Exit code: 0 = all cases pass, 1 = a case failed (printed).
"""

import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "..", "tools", "update-check.sh")
FAILED = []


def check(name, cond, detail=""):
	print("%s %s%s" % ("ok  " if cond else "FAIL", name, "" if cond else ": " + detail))
	if not cond:
		FAILED.append(name)


def write(d, name, lines):
	os.makedirs(d, exist_ok=True)
	with open(os.path.join(d, name), "w", encoding="utf-8") as f:
		f.write("".join(l + "\n" for l in lines))


def run(code, before, after, rules=()):
	env = dict(os.environ, UC_INFO_FILES="queue.txt", UC_STATUS_UNFINISHED="(the status checks did not finish)")
	env.pop("UC_NOT_JUDGED", None)
	r = subprocess.run([sys.executable, "-I", "-", before, after] + list(rules), input=code, capture_output=True,
		text=True, env=env)
	return r.returncode, r.stdout, r.stderr


def main():
	src = open(TOOL, encoding="utf-8").read()
	m = re.search(r"\ncompare_states\(\) \{[^\n]*\n\tpython3 -I - \"\$@\" <<'PY'\n(.*?)\nPY\n\}", src, re.S)
	check("compare_states found in update-check.sh", m is not None)
	if not m:
		return 1
	code = m.group(1)
	m2 = re.search(r"\nrecord_postconf\(\) \{\n(.*?)\n\}", src, re.S)
	keys = set(re.findall(r"[a-z0-9_]+", m2.group(1))) if m2 else set()
	check("record_postconf records tls_eecdh_auto_curves and tls_ffdhe_auto_groups",
		{"tls_eecdh_auto_curves", "tls_ffdhe_auto_groups"} <= keys)

	t = tempfile.mkdtemp()
	pc_before = ["myhostname = box.example.com", "smtpd_tls_protocols = !SSLv2,!SSLv3"]
	pc_after_new = pc_before + ["tls_eecdh_auto_curves = X25519MLKEM768 x25519 prime256v1", "tls_ffdhe_auto_groups = ffdhe2048 ffdhe3072"]

	# 1. Only newly recorded keys.
	b, a = os.path.join(t, "1", "before"), os.path.join(t, "1", "after")
	write(b, "postconf.txt", pc_before)
	write(a, "postconf.txt", pc_after_new)
	write(b, "doveconf.txt", ["protocols = imap, pop3"])
	write(a, "doveconf.txt", ["protocols = imap, pop3", "mail_driver = maildir"])
	rc, out, err = run(code, b, a)
	check("newly recorded keys: exit code 0", rc == 0, "%d %s" % (rc, err))
	check("newly recorded keys: section lists all three", out.count("newly recorded") >= 1
		and "tls_eecdh_auto_curves = X25519MLKEM768" in out and "tls_ffdhe_auto_groups" in out and "mail_driver = maildir" in out, out)
	check("newly recorded keys: RESULT counts them, nothing unexpected",
		"RESULT: OK - 0 unexpected, 0 expected changes, 3 newly recorded (not judged)" in out, out)
	check("newly recorded keys: UNEXPECTED (0)", "UNEXPECTED changes (0):" in out, out)

	# 2. A changed value of a key that both have is judged.
	b, a = os.path.join(t, "2", "before"), os.path.join(t, "2", "after")
	write(b, "postconf.txt", pc_before + ["tls_eecdh_auto_curves = x25519 prime256v1"])
	write(a, "postconf.txt", pc_after_new)
	rc, out, err = run(code, b, a)
	check("changed value of a key in both: unexpected without a rule", rc == 1
		and "RESULT: CHANGED - 2 unexpected, 0 expected changes, 1 newly recorded (not judged)" in out, out + err)
	rules = os.path.join(t, "rules.txt")
	with open(rules, "w", encoding="utf-8") as f:
		f.write("postconf.txt ~ ^tls_eecdh_auto_curves = # the post-quantum key exchange\n")
	rc, out, err = run(code, b, a, [rules])
	check("changed value of a key in both: expected with a rule", rc == 0
		and "RESULT: OK - 0 unexpected, 2 expected changes, 1 newly recorded (not judged)" in out, out + err)

	# 3. Other files: a new line is still unexpected.
	b, a = os.path.join(t, "3", "before"), os.path.join(t, "3", "after")
	write(b, "postconf.txt", pc_before)
	write(a, "postconf.txt", pc_before)
	write(b, "units.txt", ["postfix.service enabled active"])
	write(a, "units.txt", ["postfix.service enabled active", "evil.service enabled active"])
	rc, out, err = run(code, b, a)
	check("a new line in units.txt stays unexpected", rc == 1
		and "RESULT: CHANGED - 1 unexpected, 0 expected changes\n" in out and "newly recorded (not judged)\n" not in out.split("RESULT")[1], out)

	# 4. Nothing changed: the RESULT line as before.
	b, a = os.path.join(t, "4", "before"), os.path.join(t, "4", "after")
	write(b, "postconf.txt", pc_after_new)
	write(a, "postconf.txt", pc_after_new)
	rc, out, err = run(code, b, a)
	check("nothing changed: RESULT line unchanged", rc == 0 and "RESULT: OK - 0 unexpected, 0 expected changes\n" in out, out)

	# 6. B187: after a change of the Ubuntu release (the in-place upgrade),
	# the log audit of "after" adds log-audit-allow-old-box.txt.
	m3 = re.search(r"\nrun_log_audit\(\) \{.*?\n\}\n", src, re.S)
	body = m3.group(0) if m3 else ""
	check("run_log_audit adds log-audit-allow-old-box.txt when UC_RELEASE_CHANGED is set (B187)",
		'log-audit-allow-old-box.txt' in body and 'UC_RELEASE_CHANGED' in body)
	m4 = re.search(r'if \[ "\$ub_before" != "\$ub_after" \]; then\n(.*?)\n\telif', src, re.S)
	check("after sets UC_RELEASE_CHANGED when the Ubuntu release changed (B187)", bool(m4) and "UC_RELEASE_CHANGED=1" in m4.group(1))
	m5 = re.search(r"\nlog_audit_path\(\) \{.*?\n\}\n", src, re.S)
	check("a downloaded log audit gets log-audit-allow-old-box.txt too (B187)", bool(m5) and "log-audit-allow-old-box.txt" in m5.group(0))

	# 5. Every drop-in that setup writes is in a list of expected changes.
	root = os.path.join(HERE, "..", "..")
	lists = os.path.join(root, "tools", "expected-changes")
	plus = []
	for n in sorted(os.listdir(lists)):
		for line in open(os.path.join(lists, n), encoding="utf-8"):
			m = re.match(r"dropins\.txt \+ (.+?) # ", line)
			if m:
				plus.append(re.compile(m.group(1)))
	written = set()
	setup = os.path.join(root, "setup")
	rx = re.compile(r"/etc/systemd/system/[A-Za-z0-9@._-]+\.d/[A-Za-z0-9._-]+\.conf")
	for n in sorted(os.listdir(setup)):
		if not n.endswith(".sh"):
			continue
		for line in open(os.path.join(setup, n), encoding="utf-8"):
			if line.lstrip().startswith("#"):
				continue
			for p in rx.findall(line):
				if not re.search(r"\brm -f\b|^\s*if \[ -e ", line):
					written.add(p)
	check("setup writes drop-ins (found in setup/*.sh)", len(written) >= 3, repr(sorted(written)))
	for p in sorted(written):
		# A line of dropins.txt is the path and the checksum of the file.
		line = p + " " + "0123456789abcdef" * 4
		check("drop-in %s is an expected new file" % p, any(r.search(line) for r in plus))

	print()
	print("%d failed" % len(FAILED) if FAILED else "all passed")
	return 1 if FAILED else 0


sys.exit(main())
