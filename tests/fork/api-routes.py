#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Static check of the management API's documentation -- python3 stdlib only,
no box needed.

  * Every route of management/daemon.py (@app.route, per method) is
    documented in api/mailinabox.yml, and every documented operation has a
    route. Path parameters are compared without their names and converters
    (<qname>, <path:filename> and {qname} are all "{}").
  * Every documented operation is in exactly one of the lists of the API
    test (tests/fork/smoke.py, group "api"): API_READ_ONLY, API_WRITES or
    API_NOT_CALLED. A new endpoint therefore needs a test or a reason.
    This checks the lists only: smoke.py calls each entry of API_READ_ONLY
    in a loop, but API_WRITES is a declaration of what its write checks
    (c_api_*) call; that they really call it is not verified here.
  * The content type that the API test expects for a read-only endpoint is
    the one documented for its 200 answer.

Routes that are not part of the API (the control panel page, Munin's pages
and graphs behind the session cookie) are listed in NOT_API with the reason.

  tests/fork/api-routes.py [--verbose]

Exit code: 0 = no drift, 1 = drift found (printed), 2 = a file could not be
read or parsed.
"""

import ast
import importlib.util
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
DAEMON = os.path.join(REPO, "management", "daemon.py")
SPEC = os.path.join(REPO, "api", "mailinabox.yml")
SMOKE = os.path.join(HERE, "smoke.py")

METHODS = ("get", "post", "put", "delete", "patch")

# (method, normalised path): reason
NOT_API = {
    ("GET", "/"): "the control panel page (index.html)",
    ("GET", "/munin/{}"): "Munin's pages, behind the session cookie of GET /munin/",
    ("GET", "/munin/cgi-graph/{}"): "Munin's graphs, behind the session cookie of GET /munin/",
}


def norm(path):
    # /dns/custom/<qname>/<rtype>, /munin/<path:filename>, /ssl/csr/{domain} -> {}
    path = re.sub(r"<[^>]*>", "{}", path)
    path = re.sub(r"\{[^}]*\}", "{}", path)
    return path


def daemon_routes(path):
    # (METHOD, normalised path) -> "file:line" of the view function
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), path)
    ret = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for d in node.decorator_list:
            if not (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "route"
                    and isinstance(d.func.value, ast.Name) and d.func.value.id == "app"):
                continue
            route = d.args[0].value
            methods = ["GET"]
            for kw in d.keywords:
                if kw.arg == "methods":
                    methods = [m.value.upper() for m in kw.value.elts]
            for m in methods:
                ret[(m, norm(route))] = "daemon.py:%d %s()" % (d.lineno, node.name)
    return ret


def spec_operations(path):
    # A small reader for the parts of api/mailinabox.yml that matter here
    # (paths, their methods and the content types of their 200 answers). The
    # file's layout is regular: paths at indent 2 under "paths:", methods at
    # 4, "responses:" at 6, the status at 8, "content:" at 10 and the media
    # types at 12. Block scalars (descriptions) are indented deeper and never
    # look like these keys at these indents.
    ops = {}
    in_paths = False
    cur_path = cur_method = None
    in_responses = False
    status = None
    in_content = False
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    for n, line in enumerate(lines, 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        text = line.strip()
        if indent == 0:
            in_paths = (text == "paths:")
            cur_path = cur_method = None
            continue
        if not in_paths:
            continue
        if indent == 2 and text.endswith(":"):
            cur_path = text[:-1].strip("'\"")
            cur_method = None
            continue
        if indent == 4 and text.endswith(":"):
            m = text[:-1]
            cur_method = m if m in METHODS else None
            in_responses = False
            if cur_method:
                key = (cur_method.upper(), norm(cur_path))
                if key in ops:
                    raise ValueError("%s:%d: %s %s documented twice" % (path, n, key[0], cur_path))
                ops[key] = {"path": cur_path, "line": n, "types": {}}
            continue
        if not cur_method:
            continue
        if indent == 6:
            in_responses = (text == "responses:")
            status = None
            continue
        if in_responses and indent == 8 and text.endswith(":"):
            status = text[:-1].strip("'\"")
            in_content = False
            continue
        if in_responses and status and indent == 10:
            in_content = (text == "content:")
            continue
        if in_responses and status and in_content and indent == 12 and text.endswith(":"):
            ops[(cur_method.upper(), norm(cur_path))]["types"].setdefault(status, []).append(text[:-1])
    return ops


def smoke_lists(path):
    spec = importlib.util.spec_from_file_location("smoke", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.API_READ_ONLY, mod.API_WRITES, mod.API_NOT_CALLED


def main():
    verbose = "--verbose" in sys.argv[1:]
    try:
        routes = daemon_routes(DAEMON)
        ops = spec_operations(SPEC)
        read_only, writes, not_called = smoke_lists(SMOKE)
    except (OSError, SyntaxError, ValueError, AttributeError) as e:
        print("api-routes: %s" % e, file=sys.stderr)
        return 2

    problems = []
    for key, where in sorted(routes.items()):
        if key in NOT_API:
            continue
        if key not in ops:
            problems.append("route not documented in api/mailinabox.yml: %s %s (%s)" % (key[0], key[1], where))
    for key, op in sorted(ops.items()):
        if key in NOT_API:
            problems.append("documented, but listed as not part of the API: %s %s" % (key[0], op["path"]))
        if key not in routes:
            problems.append("documented without a route in daemon.py: %s %s (mailinabox.yml:%d)"
                            % (key[0], op["path"], op["line"]))
    for key in NOT_API:
        if key not in routes:
            problems.append("NOT_API lists a route that daemon.py does not have: %s %s" % key)

    # Coverage by the API test.
    lists = {}
    for name, entries in (("API_READ_ONLY", [(e[0], e[1]) for e in read_only]),
                          ("API_WRITES", writes), ("API_NOT_CALLED", [(e[0], e[1]) for e in not_called])):
        for m, p in entries:
            lists.setdefault((m, norm(p)), []).append(name)
    for key, op in sorted(ops.items()):
        where = lists.get(key, [])
        if not where:
            problems.append("smoke.py (group api) neither calls nor excludes %s %s" % (key[0], op["path"]))
        elif len(where) > 1:
            problems.append("smoke.py lists %s %s more than once: %s" % (key[0], op["path"], ", ".join(where)))
    for key in sorted(lists):
        if key not in ops:
            problems.append("smoke.py lists %s %s, which is not documented" % key)

    # Content types of the read-only endpoints.
    for m, p, ctype in read_only:
        op = ops.get((m, norm(p)))
        if not op:
            continue
        doc = op["types"].get("200", [])
        if ctype not in doc:
            problems.append("%s %s: smoke.py expects %s, mailinabox.yml documents %s for 200"
                            % (m, p, ctype, ", ".join(doc) or "nothing"))

    if verbose:
        for key, op in sorted(ops.items()):
            print("%-6s %-40s %-14s %s" % (key[0], op["path"], ",".join(lists.get(key, ["-"])),
                                          " ".join("%s=%s" % (s, "/".join(t)) for s, t in sorted(op["types"].items()))))
    for p in problems:
        print("DRIFT " + p)
    print("api-routes: %d routes in daemon.py (%d not API), %d documented operations, %d problems"
          % (len(routes), len(NOT_API), len(ops), len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
