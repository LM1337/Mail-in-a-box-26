#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Static check of the control panel's HTML fragments -- python3 stdlib only,
no box needed.

Since jQuery 3.5, $(html) no longer expands a self-closing tag of an element
that is not void ("<div/>") into "<div></div>". The browser's HTML parser
reads "<div/>" as an opening tag, so everything that follows in the same
fragment ends up inside that element (B178: the "show more" link of the
status checks sat in the hidden div.extra, and the TLS page's result went
into the h4 and was removed with its text()).

A fragment of a single element ($('<td class="num"/>')) is not affected,
nor a self-closing tag followed directly by the closing tag of its parent
("<td><tt/></td>"). This check reports every JavaScript string literal in
management/templates/*.html with a self-closing tag of a non-void element
that is followed by more markup or text in the same literal. Fragments
built from several literals ("<td/>" + x + "<td/>") are not seen.

  tests/fork/panel-fragments.py [TEMPLATE_DIR]

Exit code: 0 = none found, 1 = found (printed), 2 = no templates found.
"""

import glob
import os
import re
import sys

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
	"meta", "param", "source", "track", "wbr"}

LITERAL = re.compile(r""""((?:[^"\\\n]|\\.)*)"|'((?:[^'\\\n]|\\.)*)'""")
SELF_CLOSING = re.compile(r"<([a-zA-Z][a-zA-Z0-9]*)\b[^<>]*/>")


def problems(path):
	with open(path, encoding="utf-8") as f:
		for lineno, line in enumerate(f, 1):
			for m in LITERAL.finditer(line):
				s = m.group(1) if m.group(1) is not None else m.group(2)
				if "<" not in s:
					continue
				for t in SELF_CLOSING.finditer(s):
					if t.group(1).lower() in VOID:
						continue
					rest = s[t.end():]
					if rest and not rest.startswith("</"):
						yield lineno, t.group(0), s


def main():
	here = os.path.dirname(os.path.abspath(__file__))
	tdir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "..", "..", "management", "templates")
	files = sorted(glob.glob(os.path.join(tdir, "*.html")))
	if not files:
		print(f"No templates in {tdir}.", file=sys.stderr)
		return 2
	found = 0
	for path in files:
		for lineno, tag, s in problems(path):
			found += 1
			print(f"{os.path.basename(path)}:{lineno}: {tag} is followed by more markup (write <x></x>): {s}")
	print(f"{len(files)} templates, {found} problem{'' if found == 1 else 's'}.")
	return 1 if found else 0


if __name__ == "__main__":
	sys.exit(main())
