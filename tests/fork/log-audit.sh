#!/bin/bash
# Log audit of a Mail-in-a-Box box under test. Read-only: it only reads logs,
# the journal and the user database, and writes nothing on the box (except the
# --json report, if asked for).
#
# Collects warnings and errors since a point in time from the journal and the
# log files of the services, reduces each line to a message class (timestamps,
# PIDs, queue IDs, IP addresses, hex IDs, numbers, the box's host name, its
# mail domains and users are replaced by placeholders), counts the lines per
# class and compares the classes with an allowlist. A class that the allowlist
# does not explain is UNKNOWN: look at it, then fix the cause or, if it is
# harmless, add it to the allowlist with the reason.
#
# Sources:
#   * journal: everything at priority warning or higher; for the core units
#     (postfix, dovecot, nginx, php-fpm, spampd, opendkim, opendmarc, postgrey,
#     fail2ban, nsd, named, munin-node, mailinabox, cron, systemd itself) also
#     lower priorities with error words; kernel errors (BUG, Oops, hung tasks,
#     I/O errors, OOM, segfaults, AppArmor denials)
#   * systemctl --failed
#   * /var/log/mail.log, mail.err, nginx/error.log, php*-fpm.log, fail2ban.log,
#     syslog (kernel errors), cloud-init.log, apt/term.log and history.log,
#     munin/*.log, roundcubemail/errors.log, z-push/*.log, Nextcloud's log
#     (level >= 2, the logfile of config.php or $STORAGE_ROOT/owncloud/
#     nextcloud.log), the logs of tools/migrate-to-2604.sh and
#     tools/upgrade-in-place-to-2604.sh, and the logs given with --setup-log.
#     Rotated files (.1, .N.gz) are read when they changed in the window.
#
# In-place upgrades: what the box logs between stopping mail and the start of
# setup (the old releases, the release upgrades and their reboots) gets the
# phase of tools/upgrade-in-place-to-2604.sh as a prefix of its class, e.g.
# "[in-place:release_2604] systemd: ...", from the times in the tool's state
# file (upgrade.log, which has no time stamps, by its section headings). The
# allowlist rules that start with "^\[in-place" accept such classes only with
# that prefix; the other rules apply in every phase.
#
# Allowlist (default: log-audit-allow.txt next to this script): one Python
# regular expression per line, searched in the message class as the report
# prints it, then " # " and the reason (mandatory). The regex itself must not
# contain " # " (write [#] instead). Empty lines and lines starting with "#"
# are comments. --allow replaces the default list, --allow-extra adds a list
# (e.g. one for the local additions of a test lab); both can be repeated.
# --internet adds log-audit-allow-internet.txt (next to this script): the
# usual noise of a box on the Internet (firewall blocks, scanners, password
# guessing, TLS errors of bad clients), for a production box; the tests do
# not use it.
#
# Baseline: --baseline BEFORE.json takes the --json report of an earlier run
# (e.g. before an update, see tools/update-check.sh). A class that was in it
# (UNKNOWN or allowed) is listed as KNOWN with both counts and is not an
# UNKNOWN; only the classes that are new against the baseline count.
#
# Usage (as root on the box):
#   tests/fork/log-audit.sh [--since TIME] [--allow FILE]... [--allow-extra FILE]...
#                           [--internet] [--baseline BEFORE.json]
#                           [--json OUT] [--setup-log FILE]... [--examples N]
#   TIME: anything "date -d" understands ("2026-10-25 08:15", "-2 hours",
#         "24 hours ago", "@1793000000"), the short forms -90s, -30m, -24h,
#         -2d and -1w, or "boot" (the default: since the last boot; files
#         that changed since then are read, lines older than it are skipped).
#         For a test, give the time the scenario started.
#   --setup-log FILE  also read a saved setup output (lines without time stamps
#         are read if the file changed in the window)
#   --examples N      example lines per class (default 2, secrets masked)
#
# Exit code: 0 no UNKNOWN class, 1 at least one UNKNOWN class, 2 usage error.
set -euo pipefail

usage() { sed -n '2,/^set -euo/{/^set -euo/d;s/^# \{0,1\}//;p}' "${BASH_SOURCE[0]}"; }

SINCE=boot
ALLOW=()
ALLOW_EXTRA=()
INTERNET=
BASELINE=
JSON_OUT=
EXAMPLES=2
SETUP_LOGS=()
while [ $# -gt 0 ]; do
	case "$1" in
		--since) SINCE=${2:?--since needs a value}; shift 2 ;;
		--allow) ALLOW+=("${2:?--allow needs a file}"); shift 2 ;;
		--allow-extra) ALLOW_EXTRA+=("${2:?--allow-extra needs a file}"); shift 2 ;;
		--internet) INTERNET=1; shift ;;
		--baseline) BASELINE=${2:?--baseline needs a file}; shift 2 ;;
		--json) JSON_OUT=${2:?--json needs a file}; shift 2 ;;
		--setup-log) SETUP_LOGS+=("${2:?--setup-log needs a file}"); shift 2 ;;
		--examples) EXAMPLES=${2:?--examples needs a number}; shift 2 ;;
		-h|--help) usage; exit 0 ;;
		*) echo "log-audit.sh: unknown option $1 (see --help)" >&2; exit 2 ;;
	esac
done

if [ "$(id -u)" != 0 ]; then
	echo "log-audit.sh: run it as root (it reads the logs of all services)." >&2
	exit 2
fi
if [ ${#ALLOW[@]} = 0 ]; then
	if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "$(dirname "${BASH_SOURCE[0]}")/log-audit-allow.txt" ]; then
		ALLOW=("$(dirname "${BASH_SOURCE[0]}")/log-audit-allow.txt")
	else
		echo "log-audit.sh: no allowlist found next to the script, give --allow FILE." >&2
		exit 2
	fi
fi
if [ -n "$INTERNET" ]; then
	if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "$(dirname "${BASH_SOURCE[0]}")/log-audit-allow-internet.txt" ]; then
		ALLOW+=("$(dirname "${BASH_SOURCE[0]}")/log-audit-allow-internet.txt")
	else
		echo "log-audit.sh: --internet: no log-audit-allow-internet.txt next to the script, give --allow-extra FILE." >&2
		exit 2
	fi
fi
ALLOW+=("${ALLOW_EXTRA[@]+"${ALLOW_EXTRA[@]}"}")
if [ -n "$BASELINE" ] && [ ! -r "$BASELINE" ]; then
	echo "log-audit.sh: cannot read the baseline $BASELINE." >&2
	exit 2
fi
for f in "${ALLOW[@]}"; do
	if [ ! -r "$f" ]; then
		echo "log-audit.sh: cannot read the allowlist $f." >&2
		exit 2
	fi
done
case "$EXAMPLES" in ''|*[!0-9]*) echo "log-audit.sh: --examples needs a number." >&2; exit 2 ;; esac

if [ "$SINCE" = boot ]; then
	SINCE_EPOCH=$(awk '/^btime /{print $2}' /proc/stat)
	SINCE_LABEL="last boot"
else
	# The short forms (-24h): date -d reads "h" as a time zone and fails.
	since_d=$SINCE
	if [[ $SINCE =~ ^-([0-9]+)[[:space:]]*(s|m|min|h|d|w)$ ]]; then
		case "${BASH_REMATCH[2]}" in
			s) since_d="${BASH_REMATCH[1]} seconds ago" ;;
			m | min) since_d="${BASH_REMATCH[1]} minutes ago" ;;
			h) since_d="${BASH_REMATCH[1]} hours ago" ;;
			d) since_d="${BASH_REMATCH[1]} days ago" ;;
			w) since_d="${BASH_REMATCH[1]} weeks ago" ;;
		esac
	fi
	if ! SINCE_EPOCH=$(date -d "$since_d" +%s 2>/dev/null); then
		echo "log-audit.sh: cannot parse --since \"$SINCE\"." >&2
		exit 2
	fi
	SINCE_LABEL=$SINCE
fi

STORAGE_ROOT=/home/user-data
PRIMARY_HOSTNAME=$(hostname -f 2>/dev/null || hostname)
if [ -r /etc/mailinabox.conf ]; then
	STORAGE_ROOT=$(sed -n 's/^STORAGE_ROOT=//p' /etc/mailinabox.conf | tail -n 1)
	PRIMARY_HOSTNAME=$(sed -n 's/^PRIMARY_HOSTNAME=//p' /etc/mailinabox.conf | tail -n 1)
fi

LA_ALLOW=$(printf '%s\n' "${ALLOW[@]}")
export LA_SINCE_EPOCH=$SINCE_EPOCH LA_SINCE_LABEL=$SINCE_LABEL LA_ALLOW \
	LA_JSON=$JSON_OUT LA_EXAMPLES=$EXAMPLES LA_STORAGE_ROOT=$STORAGE_ROOT \
	LA_HOSTNAME=$PRIMARY_HOSTNAME LA_BASELINE=$BASELINE
LA_SETUP_LOGS=$(printf '%s\n' "${SETUP_LOGS[@]+"${SETUP_LOGS[@]}"}")
export LA_SETUP_LOGS
export LC_ALL=C.UTF-8

exec python3 -I - <<'PY'
import calendar, collections, glob, gzip, json, os, re, sqlite3, subprocess, sys, time

SINCE = int(os.environ["LA_SINCE_EPOCH"])
EXAMPLES = int(os.environ["LA_EXAMPLES"])
STORAGE_ROOT = os.environ["LA_STORAGE_ROOT"]
HOSTNAME = os.environ["LA_HOSTNAME"]
SETUP_LOGS = [p for p in os.environ.get("LA_SETUP_LOGS", "").split("\n") if p]

# --------------------------------------------------------------- allowlist

def load_allow(path, rules):
    for n, raw in enumerate(open(path, encoding="utf-8"), 1):
        line = raw.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if " # " not in line:
            sys.exit("log-audit.sh: %s:%d: no \" # reason\" after the regex" % (path, n))
        rx, reason = line.split(" # ", 1)
        rx, reason = rx.strip(), reason.strip()
        if not rx or not reason:
            sys.exit("log-audit.sh: %s:%d: empty regex or reason" % (path, n))
        try:
            rules.append({"file": path, "line": n, "regex": rx, "re": re.compile(rx), "reason": reason, "hits": 0,
                          "tagged": rx.startswith(r"^\[in-place")})
        except re.error as e:
            sys.exit("log-audit.sh: %s:%d: bad regex: %s" % (path, n, e))

RE_TAG = re.compile(r"^\[in-place:[a-z0-9_]+\] ")
ALLOW_FILES = [p for p in os.environ["LA_ALLOW"].split("\n") if p]
RULES = []
try:
    for path in ALLOW_FILES:
        load_allow(path, RULES)
except SystemExit as e:
    print(e, file=sys.stderr)
    sys.exit(2)

# The classes of an earlier report (--baseline), without the phase prefix,
# with their counts there.
BASELINE_FILE = os.environ.get("LA_BASELINE", "")
BASELINE = {}
BASELINE_LABEL = ""
if BASELINE_FILE:
    try:
        with open(BASELINE_FILE, encoding="utf-8") as f:
            b = json.load(f)
        for item in b.get("unknown", []) + b.get("allowed", []) + b.get("known", []):
            BASELINE[RE_TAG.sub("", item["class"], count=1)] = int(item.get("count", 0))
        BASELINE_LABEL = "%s since %s" % (b.get("host", "?"), b.get("since_label", "?"))
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        print("log-audit.sh: cannot read the baseline %s: %s" % (BASELINE_FILE, e), file=sys.stderr)
        sys.exit(2)

# ------------------------------------------------------------ normalizing

def box_names():
    """The box's host name, mail domains and users: replaced by placeholders."""
    users, domains = set(), set()
    db = os.path.join(STORAGE_ROOT, "mail/users.sqlite")
    try:
        con = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
        for (email,) in con.execute("SELECT email FROM users"):
            users.add(email.lower())
        for (src,) in con.execute("SELECT source FROM aliases"):
            if src.startswith("@"):
                domains.add(src[1:].lower())
            else:
                users.add(src.lower())
        con.close()
    except sqlite3.Error:
        pass
    for u in users:
        if "@" in u:
            domains.add(u.split("@", 1)[1])
    if HOSTNAME:
        domains.add(HOSTNAME.lower())
        parts = HOSTNAME.lower().split(".")
        if len(parts) > 2:
            domains.add(".".join(parts[1:]))
    return sorted(users, key=len, reverse=True), sorted(domains, key=len, reverse=True)

USERS, DOMAINS = box_names()

def alt(words):
    return re.compile("|".join(re.escape(w) for w in words), re.I) if words else None

RE_USERS = alt(USERS)
RE_HOST = alt([HOSTNAME]) if HOSTNAME else None
RE_DOMAINS = alt(DOMAINS)

SECRET_RES = [
    (re.compile(r"(?i)\b(pass(?:word|wd)?|pw|secret|token|api[_-]?key|auth[_-]?token|apppassword)(\s*[=:]\s*|\"\s*:\s*\")([^\s,;&\"']+)"), r"\1\2***"),
    (re.compile(r"(?i)\b(AUTH\s+(?:PLAIN|LOGIN|XOAUTH2|OAUTHBEARER))\s+\S+"), r"\1 ***"),
    (re.compile(r"(?i)\b(Authorization:?\s*(?:Basic|Bearer)?)\s+\S+"), r"\1 ***"),
]

def mask(s):
    for rx, rep in SECRET_RES:
        s = rx.sub(rep, s)
    return s

RE_UUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
RE_IPV4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w])")
RE_IPV6 = re.compile(r"(?<![\w:.])(?:(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}|"
                     r"(?=[0-9a-fA-F:]*::)(?:[0-9a-fA-F]{1,4}:){0,7}:(?::?[0-9a-fA-F]{1,4}){0,7})(?:/\d+)?(?![\w:])")
RE_SESS = re.compile(r"<[A-Za-z0-9+/=:]{12,}>")
RE_HEX = re.compile(r"(?<![0-9A-Za-z])(?=[0-9a-fA-F]*\d)(?=[0-9a-fA-F]*[a-fA-F])[0-9a-fA-F]{6,}(?![0-9A-Za-z])")
RE_B64 = re.compile(r"(?<![\w/+.])(?=[A-Za-z0-9+/]*\d)(?=[A-Za-z0-9+/]*[A-Z])(?=[A-Za-z0-9+/]*[a-z])[A-Za-z0-9+/]{24,}={0,2}")
RE_RRD = re.compile(r"/var/lib/munin/\S+?\.rrd")
RE_MAILDIR = re.compile(r"(mailboxes/<domain>/)[^/\s']+")
RE_NUM = re.compile(r"(?<![A-Za-z])\d+|\d+(?![A-Za-z])")
RE_WS = re.compile(r"\s+")

def normalize(s):
    s = mask(s)
    s = RE_SESS.sub("<sess>", s)
    if RE_USERS:
        s = RE_USERS.sub("<user>", s)
    if RE_HOST:
        s = RE_HOST.sub("<hostname>", s)
    if RE_DOMAINS:
        s = RE_DOMAINS.sub("<domain>", s)
    s = RE_MAILDIR.sub(r"\1<user>", s)
    s = RE_RRD.sub("<munin-rrd>", s)
    s = RE_UUID.sub("<uuid>", s)
    s = RE_IPV6.sub("<ip>", s)
    s = RE_IPV4.sub("<ip>", s)
    s = RE_HEX.sub("<hex>", s)
    s = RE_B64.sub("<blob>", s)
    s = RE_NUM.sub("N", s)
    s = RE_WS.sub(" ", s).replace("[ ", "[").strip()
    return s[:400]

def prog_name(p):
    """postfix/smtpd[123] -> postfix/smtpd, imap(u@x)<12><ab> -> imap"""
    p = re.sub(r"\(.*?\)|<.*?>|\[.*?\]", "", p)
    return p.strip()

# ------------------------------------------------- in-place upgrade phases
# Between stopping mail and the start of setup, tools/upgrade-in-place-to-2604.sh
# runs the old releases, the release upgrades and their reboots. What the box
# logs then (old systemd with new unit files, dpkg, the old services) is
# prefixed with the phase, e.g. "[in-place:release_2604] ", so that the
# allowlist can accept it for that phase only. The times come from the tool's
# state file; upgrade.log has no time stamps and is split by its section
# headings instead.

INPLACE_STATE = "/root/upgrade-2604/state"
INPLACE_LOG = "/root/upgrade-2604/upgrade.log"

def inplace_phases():
    st = {}
    try:
        for line in open(INPLACE_STATE, encoding="utf-8", errors="replace"):
            k, sep, v = line.rstrip("\n").partition("=")
            if sep:
                st[k] = v
    except OSError:
        return [], None
    def num(k):
        try:
            return int(st.get(k, ""))
        except ValueError:
            return None
    starts = []
    q = num("QUIESCED_EPOCH") or num("START_quiesce")
    if q is not None:
        starts.append((q, "quiesce"))
    for ph in ("prepare_release", "release_2404", "release_2604", "cleanup_etc"):
        t = num("START_" + ph)
        if t is not None:
            starts.append((t, ph))
    if not any(ph.startswith("release_") for _t, ph in starts):
        return [], None
    starts.sort()
    end = num("START_setup")
    return starts, end

INPLACE_STARTS, INPLACE_END = inplace_phases()

def phase_tag(ts):
    if ts is None or not INPLACE_STARTS or ts < INPLACE_STARTS[0][0]:
        return ""
    if INPLACE_END is not None and ts >= INPLACE_END:
        return ""
    label = ""
    for t, ph in INPLACE_STARTS:
        if ts >= t:
            label = ph
    return "in-place:" + label if label else ""

# Section headings of upgrade.log (section() of the tool) -> phase; other
# headings end the tagged part. "Rebooting: ..." keeps the phase before it.
INPLACE_HEADINGS = [
    (re.compile(r"^(Pausing the backups|Stopping mail)\b"), "quiesce"),
    (re.compile(r"^Preparing the packages for the release upgrade$"), "prepare_release"),
    (re.compile(r"^Release upgrade: Ubuntu \S+ -> 24\.04$"), "release_2404"),
    (re.compile(r"^Release upgrade: Ubuntu \S+ -> 26\.04$"), "release_2604"),
    (re.compile(r"^Cleaning up for Ubuntu 26\.04 \(before setup\)$"), "cleanup_etc"),
    (re.compile(r"^Rebooting: "), None),
]
RULER = "-----------------------------------------------"

# ---------------------------------------------------------------- results

classes = {}          # class text -> {"sources": Counter, "examples": [...]}
source_stats = []     # [{"source", "status", "lines"}]

def add(source, ident, msg, raw, tag=""):
    text = normalize(msg)
    if not text:
        return
    key = "%s: %s" % (ident, text) if ident else text
    if tag:
        key = "[%s] %s" % (tag, key)
    c = classes.setdefault(key, {"sources": collections.Counter(), "examples": []})
    c["sources"][source] += 1
    if len(c["examples"]) < EXAMPLES:
        ex = mask(raw.strip())[:300]
        if ex not in c["examples"]:
            c["examples"].append(ex)

# ---------------------------------------------------------------- journal

ERR_WORDS = re.compile(r"(?i)\b(errors?|warning|fatal|panic|critical|failed|failure|traceback|exception|denied|segfault|timed out)\b")
KERNEL_ERR = re.compile(r"(?i)\bBUG\b|\bOops\b|hung task|blocked for more than|I/O error|Out of memory|oom-kill|oom_reaper|"
                        r"segfault|general protection|Call Trace|soft lockup|hard LOCKUP|EXT4-fs error|Buffer I/O|"
                        r"blk_update_request|critical medium error|\bMCE\b|Machine check|apparmor=\"DENIED\"")
# systemd itself: failures only (unit descriptions often contain "failed" or "error")
SYSTEMD_ERR = re.compile(r"Failed with result|Failed to |[Dd]ependency failed|status=\d+/(?!SUCCESS)[A-Z]|"
                         r"Start request repeated|[Tt]imed out|[Ww]atchdog|core dumped|Assertion|OnFailure=|"
                         r"Referenced but unset|[Ff]reezing execution")
CORE_UNITS = ["postfix*", "dovecot*", "nginx*", "php*-fpm*", "spampd*", "opendkim*", "opendmarc*", "postgrey*",
              "fail2ban*", "nsd*", "named*", "bind9*", "munin-node*", "mailinabox*", "cron*"]

def journal(args):
    cmd = ["journalctl", "--no-pager", "-q", "-o", "json", "--since", "@%d" % SINCE,
           "--output-fields=MESSAGE,SYSLOG_IDENTIFIER,_COMM,_SYSTEMD_UNIT,PRIORITY,_TRANSPORT"] + args
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except OSError:
        return
    for line in p.stdout:
        try:
            yield json.loads(line)
        except ValueError:
            continue
    p.wait()

# Dovecot logs through syslog (log_path=syslog, B85): "dovecot: imap(u)<1><s>:
# Warning: ...". Its process is the program, as in the lines that Dovecot wrote
# into mail.log itself before (and still in older files), so that one rule
# covers both.
RE_DOVECOT_INNER = re.compile(r"^(?P<prog>[a-z][\w-]*(?:\([^)\s]*\)|<[^>\s]*>|\[\d+\])*):\s(?P<msg>.*)$")

def dovecot_inner(ident, msg):
    if ident == "dovecot":
        m = RE_DOVECOT_INNER.match(msg)
        if m:
            return prog_name(m.group("prog")), m.group("msg")
    return ident, msg

def jmsg(e):
    m = e.get("MESSAGE", "")
    if isinstance(m, list):
        m = bytes(m).decode("utf-8", "replace")
    return m or ""

def scan_journal():
    seen, n = set(), 0
    queries = [(["-p", "warning"], None),
               (sum((["-u", u] for u in CORE_UNITS), []), ERR_WORDS),
               (["_PID=1"], SYSTEMD_ERR),
               (["_TRANSPORT=kernel"], KERNEL_ERR)]
    for args, rx in queries:
        for e in journal(args):
            cur = e.get("__CURSOR")
            if cur in seen:
                continue
            msg = jmsg(e)
            if rx is not None and not rx.search(msg):
                continue
            ident = e.get("SYSLOG_IDENTIFIER") or e.get("_COMM") or e.get("_SYSTEMD_UNIT") or ""
            # Dovecot's own syslog lines carry its level as the priority; below
            # warning they are not findings (failed logins of clients, "auth
            # failed"), as when Dovecot wrote mail.log itself. Its output on
            # stderr (transport stdout) still goes through the error words.
            if rx is not None and ident == "dovecot" and e.get("_TRANSPORT") == "syslog" \
                    and str(e.get("PRIORITY", "6")).isdigit() and int(e.get("PRIORITY", "6")) > 4:
                continue
            seen.add(cur)
            ident, msg = dovecot_inner(ident, msg)
            ts = int(e.get("__REALTIME_TIMESTAMP", "0")) // 1000000
            add("journal", ident, msg, "%s %s: %s" % (time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(ts)), ident, msg),
                phase_tag(ts))
            n += 1
    source_stats.append({"source": "journal", "status": "read", "lines": n})

def scan_failed_units():
    try:
        out = subprocess.run(["systemctl", "list-units", "--failed", "--no-legend", "--plain", "--all"],
                             capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        source_stats.append({"source": "systemctl --failed", "status": "error", "lines": 0})
        return
    n = 0
    for line in out.splitlines():
        if line.strip():
            unit = line.split()[0]
            add("systemctl --failed", "systemd", "unit %s is failed" % unit, line)
            n += 1
    source_stats.append({"source": "systemctl --failed", "status": "read", "lines": n})

# ------------------------------------------------------------------ files

MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}

def local_ts(y, mo, d, h, mi, s):
    return int(time.mktime((y, mo, d, h, mi, s, 0, 0, -1)))

def iso_ts(s):
    """2026-10-25T08:36:01.635571+00:00 / 2026-10-25 08:36:01,123 / ...+0000"""
    m = re.match(r"(\d{4})-(\d\d)-(\d\d)[T ]\s*(\d\d):(\d\d):(\d\d)(?:[.,]\d+)?\s*(Z|[+-]\d\d:?\d\d)?", s)
    if not m:
        return None
    y, mo, d, h, mi, se = (int(x) for x in m.groups()[:6])
    tz = m.group(7)
    if tz:
        off = 0 if tz == "Z" else (1 if tz[0] == "+" else -1) * (int(tz[1:3]) * 3600 + int(tz[-2:]) * 60)
        return calendar.timegm((y, mo, d, h, mi, se, 0, 0, 0)) - off
    return local_ts(y, mo, d, h, mi, se)

TS_PATTERNS = [
    # RFC 3339 (rsyslog on 24.04+), fail2ban, cloud-init, apt
    (re.compile(r"^(\d{4}-\d\d-\d\d[T ]\s*\d\d:\d\d:\d\d(?:[.,]\d+)?(?:Z|[+-]\d\d:?\d\d)?)\s*"), lambda m: iso_ts(m.group(1))),
    # classic syslog / dovecot: Oct 25 08:36:01
    (re.compile(r"^([A-Z][a-z]{2})\s+(\d{1,2}) (\d\d):(\d\d):(\d\d)\s+"), "syslog"),
    # nginx, munin: 2026/10/25 08:36:01
    (re.compile(r"^(\d{4})/(\d\d)/(\d\d) (\d\d):(\d\d):(\d\d)\s+"), "slash"),
    # php-fpm, Roundcube: [25-Oct-2026 08:36:01] or [25-Oct-2026 08:36:01 +0000]:
    (re.compile(r"^\[(\d\d)-([A-Z][a-z]{2})-(\d{4}) (\d\d):(\d\d):(\d\d)(?: ([+-]\d{4}))?\]:?\s*"), "bracket"),
    # z-push: 25/10/2026 08:36:01
    (re.compile(r"^(\d\d)/(\d\d)/(\d{4}) (\d\d):(\d\d):(\d\d)\s+"), "dmy"),
]
NOW = time.time()

def line_ts(line):
    """(epoch or None, rest of the line without the timestamp)"""
    for rx, kind in TS_PATTERNS:
        m = rx.match(line)
        if not m:
            continue
        g = m.groups()
        try:
            if callable(kind):
                ts = kind(m)
            elif kind == "syslog":
                y = time.localtime(NOW).tm_year
                ts = local_ts(y, MONTHS[g[0]], int(g[1]), int(g[2]), int(g[3]), int(g[4]))
                if ts > NOW + 86400:
                    ts = local_ts(y - 1, MONTHS[g[0]], int(g[1]), int(g[2]), int(g[3]), int(g[4]))
            elif kind == "slash":
                ts = local_ts(*(int(x) for x in g))
            elif kind == "bracket":
                args = (int(g[2]), MONTHS[g[1]], int(g[0]), int(g[3]), int(g[4]), int(g[5]))
                if g[6]:
                    off = (1 if g[6][0] == "+" else -1) * (int(g[6][1:3]) * 3600 + int(g[6][3:5]) * 60)
                    ts = calendar.timegm(args + (0, 0, 0)) - off
                else:
                    ts = local_ts(*args)
            else:
                ts = local_ts(int(g[2]), int(g[1]), int(g[0]), int(g[3]), int(g[4]), int(g[5]))
        except (KeyError, ValueError, OverflowError):
            ts = None
        return ts, line[m.end():]
    return None, line

RE_SYSLOG_HEAD = re.compile(r"^(?:(?P<host>[^\s:\[(<]+)\s+)?"
                            r"(?P<prog>[^\s:\[(<]+(?:\([^)\s]*\)|<[^>\s]*>|\[\d+\])*):\s(?P<msg>.*)$")

# rsyslog ($RepeatedMsgReduction on) writes a line that repeats the one before
# it as "message repeated N times: [ <the line> ]": that is the line's class.
RE_REPEATED = re.compile(r"^message repeated \d+ times: \[ ?(?P<msg>.*?) ?\]$")

def split_prog(rest):
    """host prog[pid]: msg / prog(user)<pid>: msg -> (prog, msg)"""
    m = RE_SYSLOG_HEAD.match(rest)
    if not m:
        return "", rest
    msg = m.group("msg")
    r = RE_REPEATED.match(msg)
    if r:
        msg = r.group("msg")
    return dovecot_inner(prog_name(m.group("prog")), msg)

def files_of(path):
    """path plus its rotated files that changed in the window, oldest first"""
    out = []
    for p in sorted(glob.glob(path + ".[0-9]*"), key=lambda p: -os.path.getmtime(p)) + [path]:
        try:
            if os.path.getmtime(p) >= SINCE:
                out.append(p)
        except OSError:
            pass
    return out

def read_lines(p):
    opener = gzip.open if p.endswith(".gz") else open
    with opener(p, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            yield line.rstrip("\n")

def scan_file(path, label, select, syslog=False, block_start=None):
    """select(line, rest) -> True if the line is a finding. Lines without a
    timestamp inherit the last one (continuation lines); block_start is a regex
    whose timestamp (group 1) applies to the lines up to the next block (apt)."""
    paths = files_of(path)
    if not os.path.exists(path) and not paths:
        source_stats.append({"source": label, "status": "missing", "lines": 0})
        return
    if not paths:
        source_stats.append({"source": label, "status": "unchanged", "lines": 0})
        return
    n = 0
    headings = path == INPLACE_LOG
    for p in paths:
        last = None
        section_tag, prev, prev2 = "", None, None
        try:
            for line in read_lines(p):
                if headings:
                    # A heading is the line between two rulers: seen when the
                    # second ruler comes, so look two lines back.
                    if line == RULER and prev2 == RULER and prev is not None:
                        for rx, ph in INPLACE_HEADINGS:
                            if rx.search(prev):
                                if ph is not None:
                                    section_tag = "in-place:" + ph
                                break
                        else:
                            section_tag = ""
                    elif line.startswith("=== upgrade-in-place-to-2604.sh "):
                        section_tag = ""
                    prev2, prev = prev, line
                if block_start is not None:
                    m = block_start.match(line)
                    if m:
                        last = iso_ts(m.group(1))
                        continue
                    ts, rest = None, line
                else:
                    ts, rest = line_ts(line)
                    if ts is not None:
                        last = ts
                if last is not None and last < SINCE:
                    continue
                if last is None and os.path.getmtime(p) < SINCE:
                    continue
                if not select(line, rest):
                    continue
                prog, msg = split_prog(rest) if syslog else ("", rest)
                add(label, prog, msg, line, section_tag if headings else phase_tag(last))
                n += 1
        except OSError as e:
            source_stats.append({"source": p, "status": "error: %s" % e.strerror, "lines": 0})
            continue
    source_stats.append({"source": label, "status": "read", "lines": n})

def rx_select(rx):
    return lambda line, rest: bool(rx.search(rest))

MAIL_RX = re.compile(r"(?i)\b(warning|error|fatal|panic|critical)\b|\breject(ed)?\b|status=(deferred|bounced)|Traceback")
NGINX_RX = re.compile(r"\[(warn|error|crit|alert|emerg)\]")
FPM_RX = re.compile(r"^(WARNING|ERROR|ALERT|EMERG|CRITICAL)\b")
F2B_RX = re.compile(r"\b(ERROR|WARNING|CRITICAL)\b")
CLOUD_RX = re.compile(r"\[(WARNING|ERROR|CRITICAL)\]")
MUNIN_RX = re.compile(r"\[(ERROR|FATAL|WARNING|WARN|CRITICAL)\]")
ZPUSH_RX = re.compile(r"\[(ERROR|FATAL|WARN|WARNING|CRITICAL)\]")
APT_RX = re.compile(r"^(E|W|Err): |dpkg: (warning|error)|Errors were encountered|returned error exit status|"
                    r"returned an error code|\b(ERROR|FATAL|Traceback)\b|^(Error|Warning|WARNING):|\bfailed\b")
SETUP_RX = re.compile(r"^(E|W): |dpkg: (warning|error)|Errors were encountered|returned (an )?error|"
                      r"\b(ERROR|FATAL|FAILED|WARNING|Traceback)\b|^(Error|Warning|error|warning)\b|\b(fatal|panic):")

def kernel_select(line, rest):
    prog, msg = split_prog(rest)
    return prog == "kernel" and bool(KERNEL_ERR.search(msg))

def scan_nextcloud():
    path = os.path.join(STORAGE_ROOT, "owncloud/nextcloud.log")
    for cfg in ("/usr/local/lib/owncloud/config/config.php", os.path.join(STORAGE_ROOT, "owncloud/config.php")):
        try:
            m = re.search(r"'logfile'\s*=>\s*'([^']+)'", open(cfg, encoding="utf-8", errors="replace").read())
        except OSError:
            continue
        if m:
            path = m.group(1)
            break
    label = "nextcloud.log"
    paths = files_of(path)
    if not paths:
        source_stats.append({"source": label, "status": "missing" if not os.path.exists(path) else "unchanged", "lines": 0})
        return
    n = 0
    for p in paths:
        for line in read_lines(p):
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if not isinstance(e, dict) or int(e.get("level", 0)) < 2:
                continue
            ts = iso_ts(str(e.get("time", "")))
            if ts is not None and ts < SINCE:
                continue
            msg = str(e.get("message", ""))
            exc = e.get("exception")
            if isinstance(exc, dict) and exc.get("Message") and exc.get("Message") not in msg:
                msg += " (%s: %s)" % (exc.get("Exception", ""), exc.get("Message"))
            add(label, "nextcloud[%s] level %s" % (e.get("app", "?"), e.get("level")), msg,
                "%s %s %s: %s" % (e.get("time"), e.get("app"), e.get("level"), msg))
            n += 1
    source_stats.append({"source": label, "status": "read", "lines": n})

def everything(line, rest):
    return bool(rest.strip())

def main():
    scan_journal()
    scan_failed_units()
    scan_file("/var/log/mail.log", "mail.log", rx_select(MAIL_RX), syslog=True)
    scan_file("/var/log/mail.err", "mail.err", everything, syslog=True)
    scan_file("/var/log/syslog", "syslog (kernel)", kernel_select, syslog=True)
    scan_file("/var/log/nginx/error.log", "nginx/error.log", rx_select(NGINX_RX))
    for p in sorted(glob.glob("/var/log/php*-fpm.log")):
        scan_file(p, os.path.basename(p), rx_select(FPM_RX))
    scan_file("/var/log/fail2ban.log", "fail2ban.log", rx_select(F2B_RX))
    scan_file("/var/log/cloud-init.log", "cloud-init.log", rx_select(CLOUD_RX))
    scan_file("/var/log/apt/term.log", "apt/term.log", rx_select(APT_RX),
              block_start=re.compile(r"^Log started: (\d{4}-\d\d-\d\d\s+\d\d:\d\d:\d\d)"))
    scan_file("/var/log/apt/history.log", "apt/history.log", lambda l, r: r.startswith("Error:"),
              block_start=re.compile(r"^Start-Date: (\d{4}-\d\d-\d\d\s+\d\d:\d\d:\d\d)"))
    for p in sorted(glob.glob("/var/log/munin/*.log")):
        scan_file(p, "munin/" + os.path.basename(p), rx_select(MUNIN_RX))
    scan_file("/var/log/roundcubemail/errors.log", "roundcubemail/errors.log", everything)
    for p in sorted(glob.glob("/var/log/z-push/*.log")):
        name = os.path.basename(p)
        scan_file(p, "z-push/" + name, everything if name.endswith("-error.log") else rx_select(ZPUSH_RX))
    scan_nextcloud()
    for p in ["/root/migration/migrate.log", "/root/upgrade-2604/upgrade.log"] + SETUP_LOGS:
        if p in SETUP_LOGS or os.path.exists(p):
            scan_file(p, p, rx_select(SETUP_RX))

    unknown, allowed = [], []
    for key, c in classes.items():
        item = {"class": key, "count": max(c["sources"].values()), "sources": dict(c["sources"]),
                "examples": c["examples"]}
        # A rule without a phase prefix applies in every phase.
        plain = RE_TAG.sub("", key, count=1)
        for r in RULES:
            if r["re"].search(key) or (plain != key and not r["tagged"] and r["re"].search(plain)):
                r["hits"] += 1
                item["reason"] = r["reason"]
                item["allow_line"] = r["line"]
                item["allow_file"] = r["file"]
                item["allow_index"] = RULES.index(r)
                allowed.append(item)
                break
        else:
            unknown.append(item)
    known = []
    if BASELINE_FILE:
        for item in unknown:
            plain = RE_TAG.sub("", item["class"], count=1)
            if plain in BASELINE:
                item["baseline_count"] = BASELINE[plain]
                known.append(item)
        unknown = [i for i in unknown if "baseline_count" not in i]
    known.sort(key=lambda i: (-i["count"], i["class"]))
    unknown.sort(key=lambda i: (-i["count"], i["class"]))
    allowed.sort(key=lambda i: (i["allow_index"], -i["count"]))
    for item in allowed:
        del item["allow_index"]

    w = sys.stdout.write
    w("log-audit on %s since %s (%s)\n" % (HOSTNAME, os.environ["LA_SINCE_LABEL"],
                                           time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime(SINCE))))
    w("allowlist: %s (%d rules)\n" % (", ".join(ALLOW_FILES), len(RULES)))
    if BASELINE_FILE:
        w("baseline: %s (%s, %d classes)\n" % (BASELINE_FILE, BASELINE_LABEL, len(BASELINE)))
    if INPLACE_STARTS:
        w("in-place upgrade phases (prefix [in-place:PHASE]): %s, until %s\n" % (
            ", ".join("%s %s" % (ph, time.strftime("%H:%M:%S", time.localtime(t))) for t, ph in INPLACE_STARTS),
            time.strftime("%H:%M:%S", time.localtime(INPLACE_END)) if INPLACE_END else "now"))
    w("\nSources:\n")
    for s in source_stats:
        w("  %-32s %-10s %d\n" % (s["source"], s["status"], s["lines"]))

    def show(item):
        src = ", ".join("%s %d" % kv for kv in sorted(item["sources"].items()))
        w("  [%d] %s\n      sources: %s\n" % (item["count"], item["class"], src))
        if "reason" in item:
            w("      reason: %s (%s:%d)\n" % (item["reason"], os.path.basename(item["allow_file"]), item["allow_line"]))
        if "baseline_count" in item:
            w("      in the baseline: %d lines\n" % item["baseline_count"])
        for ex in item["examples"]:
            w("      e.g. %s\n" % ex)

    w("\nUNKNOWN (%d classes%s):\n" % (len(unknown), ", new against the baseline" if BASELINE_FILE else ""))
    for item in unknown:
        show(item)
    if BASELINE_FILE:
        w("\nKNOWN from the baseline, not on the allowlist (%d classes):\n" % len(known))
        for item in known:
            show(item)
    w("\nALLOWED (%d classes):\n" % len(allowed))
    for item in allowed:
        show(item)
    unused = [r for r in RULES if not r["hits"]]
    if unused:
        w("\nAllowlist rules without a match here (%d): lines %s\n"
          % (len(unused), ", ".join("%s:%d" % (os.path.basename(r["file"]), r["line"]) for r in unused)))
    w("\nRESULT: %s - %d unknown, %s%d allowed classes\n"
      % ("OK" if not unknown else "UNKNOWN", len(unknown),
         "%d known from the baseline, " % len(known) if BASELINE_FILE else "", len(allowed)))

    out = os.environ.get("LA_JSON")
    if out:
        report = {"host": HOSTNAME, "since": SINCE, "since_label": os.environ["LA_SINCE_LABEL"],
                  "allowlist": ALLOW_FILES, "sources": source_stats,
                  "inplace_phases": [{"phase": ph, "start": t} for t, ph in INPLACE_STARTS],
                  "inplace_setup_start": INPLACE_END,
                  "baseline": BASELINE_FILE or None,
                  "unknown": unknown, "known": known, "allowed": allowed,
                  "unused_rules": [{"file": r["file"], "line": r["line"], "regex": r["regex"]} for r in unused],
                  "result": "OK" if not unknown else "UNKNOWN"}
        with open(out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=1, ensure_ascii=False)
            f.write("\n")
    sys.exit(0 if not unknown else 1)

main()
PY
