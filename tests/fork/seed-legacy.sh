#!/bin/bash
# Seed a Mail-in-a-Box with test data and write a manifest for the migration test.
#
# Runs ON the box as root. Idempotent: users/aliases/sieve/DNS/Nextcloud items are
# (re)set, the mail stage is skipped when seed mail already exists (SEED_FORCE_MAIL=1
# delivers again), and the manifest is always rewritten from the current state.
#
# Creates
#   domains   $SEED_PRIMARY_DOMAIN (default: PRIMARY_HOSTNAME without its first label),
#             $SEED2_DOMAIN, $SEED3_DOMAIN (domain alias @seed3 -> @seed2)
#   users     alice@<primary> (quota 0), bob@seed2 (quota 10M), carol@<primary>
#   aliases   info@<primary> -> alice, catch-all @seed2 -> bob, @seed3 -> @seed2,
#             team@<primary> -> alice,carol with permitted sender alice
#   sieve     alice: "[filtered]" -> folder Filtered; carol: vacation (ManageSieve 4190)
#   mail      20 mails over port 25 (incl. GTUBE -> Spam, filtered, alias, catch-all,
#             domain alias), IMAP APPEND into Archive, IMAP MOVE into Spam/Archive
#   nextcloud event (CalDAV), contact (CardDAV), file (WebDAV) as alice
#   dns       custom TXT seedtest.<primary>
#   roundcube identity with signature for alice (logs in once if needed)
#   backup    one local backup run (management/backup.py)
# and writes $SEED_MANIFEST (default /root/seed-manifest.json): POP3 UIDLs, per-folder
# counts/UIDVALIDITY/Message-IDs, sa-learn magic counts, sieve, NC items, DKIM key ...
#
# Environment
#   TEST_USER_PW         password for alice/bob/carol (required)
#   SEED_ENV_FILE        optional KEY=VALUE file to source first (e.g. credentials.env)
#   SEED_PRIMARY_DOMAIN  primary mail domain (default derived from PRIMARY_HOSTNAME)
#   SEED2_DOMAIN / SEED3_DOMAIN   (default seed2.example.net / seed3.example.net;
#                        set them to test domains you control if the box refuses those)
#   ADMIN_EMAIL/ADMIN_PW or LEGACY_ADMIN/LEGACY_ADMIN_PW
#                        only used when /var/lib/mailinabox/api.key is not readable
#   SEED_MANIFEST        manifest path (default /root/seed-manifest.json)
#   SEED_FORCE_MAIL=1    deliver the mail set again even if seed mail exists
#   SEED_SKIP_BACKUP=1, SEED_SKIP_NEXTCLOUD=1, SEED_SKIP_ROUNDCUBE=1
#   SEED_BACKUP_ANY_TARGET=1   also run the backup when the target is not "local"
#
# Invocation from a workstation (password never on a command line; MIAB_TEST_ENV
# is the local credentials file, see tests/fork/smoke.py):
#   scp tests/fork/seed-legacy.sh legacy-box:/tmp/
#   ssh legacy-box 'umask 077; cat > /tmp/seed.env' < "$MIAB_TEST_ENV"
#   ssh legacy-box 'sudo SEED_ENV_FILE=/tmp/seed.env bash /tmp/seed-legacy.sh; rm -f /tmp/seed.env'
#   ssh legacy-box 'sudo cat /root/seed-manifest.json' > seed-manifest.json

set -euo pipefail

log()  { echo "[seed] $*"; }
warn() { echo "[seed] WARNING: $*" >&2; }
die()  { echo "[seed] ERROR: $*" >&2; exit 1; }

[ "$(id -u)" = 0 ] || die "run as root"
[ -f /etc/mailinabox.conf ] || die "/etc/mailinabox.conf not found - not a Mail-in-a-Box?"

if [ -n "${SEED_ENV_FILE:-}" ]; then
	[ -r "$SEED_ENV_FILE" ] || die "SEED_ENV_FILE $SEED_ENV_FILE not readable"
	set -a
	# shellcheck disable=SC1090
	. "$SEED_ENV_FILE"
	set +a
fi

# shellcheck disable=SC1091
source /etc/mailinabox.conf   # PRIMARY_HOSTNAME, STORAGE_ROOT, PUBLIC_IP ...

: "${TEST_USER_PW:?TEST_USER_PW must be set}"
P="${SEED_PRIMARY_DOMAIN:-${PRIMARY_HOSTNAME#*.}}"
S2="${SEED2_DOMAIN:-seed2.example.net}"
S3="${SEED3_DOMAIN:-seed3.example.net}"
ALICE="alice@$P"
BOB="bob@$S2"
CAROL="carol@$P"
MANIFEST="${SEED_MANIFEST:-/root/seed-manifest.json}"
H="$PRIMARY_HOSTNAME"
RCDB="$STORAGE_ROOT/mail/roundcube/roundcube.sqlite"

for bin in curl python3 sqlite3; do
	command -v "$bin" >/dev/null || die "$bin missing"
done

WORK=$(mktemp -d /root/.miab-seed.XXXXXX)
chmod 700 "$WORK"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/parts"

# ---------------------------------------------------------------- curl helpers
# Credentials go into curl config files (mode 600), never onto the command line.
curl_cred() { # name user password
	local u p
	u=$(printf '%s' "$2" | sed 's/\\/\\\\/g; s/"/\\"/g')
	p=$(printf '%s' "$3" | sed 's/\\/\\\\/g; s/"/\\"/g')
	( umask 077; printf 'user = "%s:%s"\n' "$u" "$p" > "$WORK/$1.cred" )
}

# http CRED METHOD URL [curl args...]  -> body in $WORK/body, status in $HTTP_CODE
http() {
	local cred=$1 method=$2 url=$3
	shift 3
	local credargs=()
	[ "$cred" != "-" ] && credargs=(-K "$WORK/$cred.cred")
	HTTP_CODE=$(curl -sS -k --max-time 600 --resolve "$H:443:127.0.0.1" "${credargs[@]}" \
		-X "$method" -o "$WORK/body" -w '%{http_code}' "$@" "$url" 2>"$WORK/curl.err") || HTTP_CODE=000
}
body() { cat "$WORK/body"; }

api() { # METHOD path [curl args...]
	local method=$1 path=$2
	shift 2
	http admin "$method" "https://$H/admin/$path" "$@"
}

if [ -r /var/lib/mailinabox/api.key ]; then
	curl_cred admin "$(cat /var/lib/mailinabox/api.key)" ""
else
	ADMIN_EMAIL="${ADMIN_EMAIL:-${LEGACY_ADMIN:-}}"
	ADMIN_PW="${ADMIN_PW:-${LEGACY_ADMIN_PW:-}}"
	[ -n "$ADMIN_EMAIL" ] && [ -n "$ADMIN_PW" ] || die "no API key and no admin credentials"
	curl_cred admin "$ADMIN_EMAIL" "$ADMIN_PW"
fi
curl_cred alice "$ALICE" "$TEST_USER_PW"

api GET system/version
[ "$HTTP_CODE" = 200 ] || die "admin API not reachable (HTTP $HTTP_CODE): $(cat "$WORK/curl.err")"
MIAB_VERSION=$(body | tr -d '\n')
log "box $H, Mail-in-a-Box $MIAB_VERSION, primary domain $P"

# ---------------------------------------------------------------- python helper
cat > "$WORK/seedlib.py" <<'PYEOF'
import base64, imaplib, json, os, poplib, re, smtplib, socket, ssl, subprocess, sys, time, uuid
from email.utils import formatdate

if "MOVE" not in imaplib.Commands:
    imaplib.Commands["MOVE"] = ("SELECTED",)

PW = os.environ["SEED_PW"]
HOSTNAME = os.environ["SEED_HOSTNAME"]
GTUBE = "XJS*C4JDBQADN1.NSBN3*2IDNEN*GTUBE-STANDARD-ANTI-UBE-TEST-EMAIL*C.34X"

def ctx():
    c = ssl.create_default_context()
    c.check_hostname = False
    c.verify_mode = ssl.CERT_NONE   # local connection, self-signed on test boxes
    return c

def q(name):
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'

def imap(user):
    M = imaplib.IMAP4_SSL("127.0.0.1", 993, ssl_context=ctx())
    M.login(user, PW)
    return M

LIST_RE = re.compile(r'^\((?P<flags>[^)]*)\) (?P<delim>"(?:[^"\\]|\\.)*"|NIL) (?P<name>.+)$')

def folders(M):
    typ, data = M.list()
    out = []
    for raw in data or []:
        if raw is None:
            continue
        if isinstance(raw, tuple):
            name = raw[1].decode(errors="replace")
            flags = raw[0].decode(errors="replace")
        else:
            m = LIST_RE.match(raw.decode(errors="replace"))
            if not m:
                continue
            flags, name = m.group("flags"), m.group("name")
            if name.startswith('"'):
                name = name[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        if "\\noselect" in flags.lower() or "\\nonexistent" in flags.lower():
            continue
        out.append(name)
    return out

def search(M, folder, *crit, readonly=True):
    typ, _ = M.select(q(folder), readonly=readonly)
    if typ != "OK":
        return []
    typ, data = M.uid("SEARCH", *crit)
    return data[0].split() if typ == "OK" and data and data[0] else []

def message_ids(M, folder):
    typ, _ = M.select(q(folder), readonly=True)
    if typ != "OK":
        return []
    typ, data = M.search(None, "ALL")
    if typ != "OK" or not data[0]:
        return []
    typ, data = M.fetch(b"1:*", "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])")
    ids = []
    for item in data:
        if isinstance(item, tuple):
            m = re.search(rb"<([^>]+)>", item[1])
            ids.append(m.group(1).decode(errors="replace") if m else "")
    return sorted(ids)

def msg(frm, to, subject, n, body=None, extra=()):
    lines = ["From: %s" % frm, "To: %s" % to, "Subject: %s" % subject,
             "Date: %s" % formatdate(localtime=True),
             "Message-ID: <seed-%d.%s@miab-seed.invalid>" % (n, uuid.uuid4().hex),
             "X-MIAB-Seed: 1", "MIME-Version: 1.0", "Content-Type: text/plain; charset=utf-8"]
    lines += list(extra)
    return ("\r\n".join(lines) + "\r\n\r\n" + (body or "Seed message %d for the migration test.\r\n" % n)).encode()

# ---- ManageSieve (STARTTLS on 4190, AUTHENTICATE PLAIN) ---------------------
class Sieve:
    def __init__(self):
        self.s = socket.create_connection(("127.0.0.1", 4190), 30)
        self.f = self.s.makefile("rb")
        self.resp()
    def line(self):
        l = self.f.readline()
        if not l:
            raise RuntimeError("ManageSieve connection closed")
        return l.rstrip(b"\r\n")
    def resp(self):
        lines = []
        while True:
            l = self.line()
            m = re.search(rb"\{(\d+)\+?\}$", l)
            if m:
                data = self.f.read(int(m.group(1)))
                lines.append(l[:m.start()] + data + self.line())
                continue
            if l.startswith(b"OK"):
                return lines
            if l.startswith(b"NO") or l.startswith(b"BYE"):
                raise RuntimeError("ManageSieve: " + l.decode(errors="replace"))
            lines.append(l)
    def cmd(self, raw):
        self.s.sendall(raw + b"\r\n")
        return self.resp()
    def login(self, user):
        self.cmd(b"STARTTLS")
        self.s = ctx().wrap_socket(self.s, server_hostname=HOSTNAME)
        self.f = self.s.makefile("rb")
        self.resp()
        cred = base64.b64encode(b"\0" + user.encode() + b"\0" + PW.encode())
        self.cmd(b'AUTHENTICATE "PLAIN" "' + cred + b'"')
    def put(self, name, text):
        data = text.encode()
        self.s.sendall(b'PUTSCRIPT "%s" {%d+}\r\n' % (name.encode(), len(data)) + data + b"\r\n")
        self.resp()
        self.cmd(b'SETACTIVE "%s"' % name.encode())
    def list(self):
        out = []
        for l in self.cmd(b"LISTSCRIPTS"):
            m = re.match(rb'^"((?:[^"\\]|\\.)*)"(\s+ACTIVE)?', l)
            if m:
                out.append({"name": m.group(1).decode(), "active": bool(m.group(2))})
        return out
    def close(self):
        try:
            self.cmd(b"LOGOUT")
        except Exception:
            pass

def cmd_sieve(user, name, path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    s = Sieve()
    s.login(user)
    s.put(name, text)
    scripts = s.list()
    s.close()
    print(json.dumps(scripts))

def cmd_sievelist(*users):
    out = {}
    for u in users:
        s = Sieve()
        s.login(u)
        scripts = s.list()
        s.close()
        active = [x["name"] for x in scripts if x["active"]]
        out[u] = {"scripts": [x["name"] for x in scripts], "active": active[0] if active else None}
    print(json.dumps(out))

# ---- mail stage ---------------------------------------------------------------
def count_seed(user, flds):
    M = imap(user)
    try:
        return {f: len(search(M, f, "HEADER", "X-MIAB-Seed", "1")) for f in flds}
    finally:
        M.logout()

def cmd_mail(P, S2, S3, force):
    alice, bob, carol = "alice@" + P, "bob@" + S2, "carol@" + P
    have = count_seed(alice, ["INBOX", "Filtered", "Spam", "Archive"])
    if sum(have.values()) and force != "1":
        print("seed mail already present for %s %s - skipping mail stage (SEED_FORCE_MAIL=1 to redo)" % (alice, have))
        return
    sender = "seed-sender@" + S2
    plan = []
    for i in range(1, 7):
        plan.append((alice, alice, "Seed alice #%d" % i, None))
    plan.append((alice, alice, "[filtered] Seed alice filtered #1", None))
    plan.append((alice, alice, "[filtered] Seed alice filtered #2", None))
    plan.append((alice, alice, "Seed alice GTUBE", "This must be filed as spam.\r\n" + GTUBE + "\r\n"))
    for i in range(1, 4):
        plan.append(("info@" + P, "info@" + P, "Seed info alias #%d" % i, None))
    plan.append(("random1@" + S2, "random1@" + S2, "Seed catch-all #1", None))
    plan.append(("random2@" + S2, "random2@" + S2, "Seed catch-all #2", None))
    plan.append(("x@" + S3, "x@" + S3, "Seed domain alias #1", None))
    plan.append(("bob@" + S3, "bob@" + S3, "Seed domain alias user #1", None))
    plan.append((carol, carol, "Seed carol #1 (vacation)", None))
    plan.append((carol, carol, "Seed carol #2 (vacation)", None))
    plan.append((bob, bob, "Seed bob #1", None))
    plan.append((bob, bob, "Seed bob #2", None))
    s = smtplib.SMTP("127.0.0.1", 25, local_hostname="seed.invalid", timeout=120)
    for n, (rcpt, to_hdr, subj, body) in enumerate(plan, 1):
        refused = s.sendmail(sender, [rcpt], msg(sender, to_hdr, subj, n, body))
        if refused:
            raise RuntimeError("refused %s: %s" % (rcpt, refused))
    s.quit()
    print("sent %d mails via 127.0.0.1:25" % len(plan))

    # wait for delivery (spampd + sieve)
    want = {alice: 12, bob: 6, carol: 2}
    deadline = time.time() + 240
    while True:
        got = {u: sum(count_seed(u, ["INBOX", "Filtered", "Spam"]).values()) for u in want}
        if all(got[u] >= want[u] for u in want) or time.time() > deadline:
            break
        time.sleep(5)
    print("delivered (seed mails per user): %s, wanted %s" % (got, want))
    if not all(got[u] >= want[u] for u in want):
        print("WARNING: not all seed mails arrived within 240 s", file=sys.stderr)

    # IMAP: APPEND 2 into Archive, MOVE "#1"/"#2" into Spam and "#3" into Archive
    M = imap(alice)
    try:
        for i in (1, 2):
            M.append("Archive", "(\\Seen)", None, msg(alice, alice, "Seed archived (APPEND) #%d" % i, 100 + i))
        for subj, dest in (("Seed alice #1", "Spam"), ("Seed alice #2", "Spam"), ("Seed alice #3", "Archive")):
            uids = search(M, "INBOX", "SUBJECT", q(subj), readonly=False)
            uids = [u for u in uids]
            if not uids:
                print("WARNING: %s not found in INBOX" % subj, file=sys.stderr)
                continue
            typ, data = M.uid("MOVE", uids[0].decode(), dest)
            print("MOVE %s -> %s: %s" % (subj, dest, typ))
            time.sleep(1)
    finally:
        M.logout()
    # vacation reply (to seed-sender@S2 -> catch-all -> bob)
    deadline = time.time() + 60
    while time.time() < deadline:
        M = imap(bob)
        n = len(search(M, "INBOX", "SUBJECT", q("Abwesend (seed)")))
        M.logout()
        if n:
            break
        time.sleep(5)
    print("vacation replies in bob's INBOX: %d" % n)

# ---- manifest parts --------------------------------------------------------------
def cmd_mailstate(*users):
    out = {}
    for u in users:
        M = imap(u)
        fl = {}
        try:
            for f in folders(M):
                typ, data = M.status(q(f), "(MESSAGES UIDVALIDITY UIDNEXT)")
                vals = dict(re.findall(r"(MESSAGES|UIDVALIDITY|UIDNEXT) (\d+)", data[0].decode(errors="replace")))
                fl[f] = {k.lower(): int(v) for k, v in vals.items()}
                fl[f]["message_ids"] = message_ids(M, f)
        finally:
            M.logout()
        P3 = poplib.POP3_SSL("127.0.0.1", 995, context=ctx())
        P3.user(u)
        P3.pass_(PW)
        _r, lines, _o = P3.uidl()
        P3.quit()
        out[u] = {"folders": fl, "pop3_uidls": [l.decode().split(None, 1)[1] for l in lines]}
    print(json.dumps(out))

def cmd_salearn():
    for argv in (["runuser", "-u", "spampd", "--", "/usr/bin/sa-learn", "--dump", "magic"],
                 ["/usr/bin/sa-learn", "--dump", "magic"]):
        p = subprocess.run(argv, capture_output=True, text=True)
        vals = {}
        for line in p.stdout.splitlines():
            m = re.match(r"^\s*\S+\s+\S+\s+(\d+)\s+\S+\s+non-token data: (nspam|nham)\s*$", line)
            if m:
                vals[m.group(2)] = int(m.group(1))
        if "nspam" in vals:
            vals["as"] = argv[0]
            print(json.dumps(vals))
            return
    print(json.dumps({"error": "sa-learn --dump magic gave no counts"}))

def cmd_jsonget(path, *keys):
    with open(path, encoding="utf-8") as f:
        v = json.load(f)
    for k in keys:
        v = v[int(k)] if isinstance(v, list) else v[k]
    print(v if not isinstance(v, (dict, list)) else json.dumps(v))

def cmd_aliases(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    out = []
    for d in data:
        for a in d.get("aliases", []):
            if not a.get("auto"):
                out.append({"address": a["address"], "forwards_to": sorted(a.get("forwards_to") or []),
                            "permitted_senders": sorted(a.get("permitted_senders") or [])})
    print(json.dumps(out))

def cmd_assemble(parts_dir, out_path):
    man = {}
    for name in sorted(os.listdir(parts_dir)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(parts_dir, name), encoding="utf-8") as f:
            txt = f.read().strip()
        key = name[:-5]
        try:
            val = json.loads(txt) if txt else None
        except ValueError:
            val = txt
        if key == "meta":
            man.update(val)
        else:
            man[key] = val
    # merge per-user mail state and quotas into man["users"]
    users = {}
    for u, st in (man.pop("mailstate", None) or {}).items():
        users[u] = st
    for u, quota in (man.pop("quotas", None) or {}).items():
        users.setdefault(u, {})["quota"] = quota
    man["users"] = users
    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(man, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, out_path)
    print("manifest written: %s (%d users)" % (out_path, len(users)))

if __name__ == "__main__":
    fn = globals()["cmd_" + sys.argv[1]]
    fn(*sys.argv[2:])
PYEOF

export SEED_PW="$TEST_USER_PW" SEED_HOSTNAME="$H"
py() { python3 -I "$WORK/seedlib.py" "$@"; }
part() { cat > "$WORK/parts/$1.json"; }   # part NAME < json

# ---------------------------------------------------------------- users
ensure_user() { # email quota
	local email=$1 quota=$2
	api GET mail/users
	if grep -qxF "$email" "$WORK/body"; then
		api POST mail/users/password --data-urlencode "email=$email" --data-urlencode "password@$WORK/pw"
		[ "$HTTP_CODE" = 200 ] || die "set password $email: HTTP $HTTP_CODE $(body)"
		api POST mail/users/quota --data-urlencode "email=$email" --data-urlencode "quota=$quota"
		[ "$HTTP_CODE" = 200 ] || die "set quota $email: HTTP $HTTP_CODE $(body)"
		log "user $email exists (password/quota $quota reset)"
	else
		api POST mail/users/add --data-urlencode "email=$email" --data-urlencode "password@$WORK/pw" \
			--data-urlencode "quota=$quota"
		[ "$HTTP_CODE" = 200 ] || die "add user $email: HTTP $HTTP_CODE $(body)"
		log "user $email added (quota $quota)"
	fi
}
( umask 077; printf '%s' "$TEST_USER_PW" > "$WORK/pw" )
ensure_user "$ALICE" 0
ensure_user "$BOB" 10M
ensure_user "$CAROL" 0

# ---------------------------------------------------------------- aliases
ensure_alias() { # address forwards_to permitted_senders
	api POST mail/aliases/add --data-urlencode "address=$1" --data-urlencode "forwards_to=$2" \
		--data-urlencode "permitted_senders=$3" -d update_if_exists=1
	[ "$HTTP_CODE" = 200 ] || die "alias $1: HTTP $HTTP_CODE $(body)"
	log "alias $1 -> $2 ${3:+(senders: $3)}: $(body | head -1)"
}
ensure_alias "info@$P" "$ALICE" ""
ensure_alias "@$S2" "$BOB" ""
ensure_alias "@$S3" "@$S2" ""
ensure_alias "team@$P" "$ALICE,$CAROL" "$ALICE"

# ---------------------------------------------------------------- sieve (ManageSieve)
cat > "$WORK/filter.sieve" <<'EOF'
require ["fileinto", "mailbox"];
if header :contains "subject" "[filtered]" {
  fileinto :create "Filtered";
  stop;
}
EOF
cat > "$WORK/vacation.sieve" <<EOF
require ["vacation"];
vacation :days 1 :subject "Abwesend (seed)" :addresses ["$CAROL"]
  "Carol ist nicht da (seed-vacation).";
EOF
OUT=$(py sieve "$ALICE" seedfilter "$WORK/filter.sieve") || die "ManageSieve upload for $ALICE failed"
log "sieve alice: $OUT"
OUT=$(py sieve "$CAROL" seedvacation "$WORK/vacation.sieve") || die "ManageSieve upload for $CAROL failed"
log "sieve carol: $OUT"
for u in "$ALICE" "$CAROL"; do
	d=${u#*@}; n=${u%@*}
	if [ -L "$STORAGE_ROOT/mail/sieve/$d/$n.sieve" ]; then
		log "active link $STORAGE_ROOT/mail/sieve/$d/$n.sieve -> $(readlink "$STORAGE_ROOT/mail/sieve/$d/$n.sieve")"
	else
		warn "no active-script symlink at $STORAGE_ROOT/mail/sieve/$d/$n.sieve"
	fi
done

# ---------------------------------------------------------------- mail
SA_BEFORE=$(py salearn)
log "sa-learn before: $SA_BEFORE"
py mail "$P" "$S2" "$S3" "${SEED_FORCE_MAIL:-0}" | sed 's/^/[seed] /'
SA_AFTER=$(py salearn)
log "sa-learn after:  $SA_AFTER"
printf '%s\n' "$SA_AFTER" | part sa_learn

# ---------------------------------------------------------------- Nextcloud
nc_put() { # path content-type file -> sets HTTP_CODE
	http alice PUT "https://$H$1" -H "Content-Type: $2" --data-binary "@$3"
}
if [ "${SEED_SKIP_NEXTCLOUD:-0}" = 1 ]; then
	echo '{"skipped": "SEED_SKIP_NEXTCLOUD=1"}' | part nextcloud
else
	http - GET "https://$H/cloud/status.php"
	NC_VERSION=$(py jsonget "$WORK/body" versionstring 2>/dev/null || echo unknown)
	http alice GET "https://$H/cloud/ocs/v1.php/cloud/user?format=json" -H "OCS-APIRequest: true"
	if [ "$HTTP_CODE" != 200 ]; then
		warn "Nextcloud login as $ALICE failed (HTTP $HTTP_CODE) - skipping Nextcloud items"
		printf '{"skipped": "OCS login HTTP %s", "version": "%s"}\n' "$HTTP_CODE" "$NC_VERSION" | part nextcloud
	else
		NCUID=$(py jsonget "$WORK/body" ocs data id)
		NCU=$(python3 -I -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$NCUID")
		log "Nextcloud $NC_VERSION, user id $NCUID"
		CAL="/cloud/remote.php/dav/calendars/$NCU/seed-calendar/"
		ABK="/cloud/remote.php/dav/addressbooks/users/$NCU/seed-contacts/"
		DIR="/cloud/remote.php/dav/files/$NCU/seed/"
		http alice PROPFIND "https://$H$CAL" -H "Depth: 0"
		if [ "$HTTP_CODE" = 404 ]; then
			http alice MKCALENDAR "https://$H$CAL" -H "Content-Type: application/xml" --data-binary \
'<?xml version="1.0" encoding="utf-8"?><c:mkcalendar xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:set><d:prop><d:displayname>Seed Calendar</d:displayname><c:supported-calendar-component-set><c:comp name="VEVENT"/></c:supported-calendar-component-set></d:prop></d:set></c:mkcalendar>'
			[ "$HTTP_CODE" = 201 ] || die "MKCALENDAR: HTTP $HTTP_CODE $(body | head -c 300)"
		fi
		http alice PROPFIND "https://$H$ABK" -H "Depth: 0"
		if [ "$HTTP_CODE" = 404 ]; then
			http alice MKCOL "https://$H$ABK" -H "Content-Type: application/xml" --data-binary \
'<?xml version="1.0" encoding="utf-8"?><d:mkcol xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav"><d:set><d:prop><d:resourcetype><d:collection/><card:addressbook/></d:resourcetype><d:displayname>Seed Contacts</d:displayname></d:prop></d:set></d:mkcol>'
			[ "$HTTP_CODE" = 201 ] || die "MKCOL addressbook: HTTP $HTTP_CODE $(body | head -c 300)"
		fi
		EV_UID="seed-event-1@$P"
		CT_UID="seed-contact-1@$P"
		printf 'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//MIAB fork seed//EN\r\nBEGIN:VEVENT\r\nUID:%s\r\nDTSTAMP:20261022T100000Z\r\nDTSTART:20261201T090000Z\r\nDTEND:20261201T100000Z\r\nSUMMARY:Seed event\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n' "$EV_UID" > "$WORK/event.ics"
		printf 'BEGIN:VCARD\r\nVERSION:3.0\r\nUID:%s\r\nFN:Seed Contact\r\nN:Contact;Seed;;;\r\nEMAIL;TYPE=INTERNET:seed.contact@example.org\r\nEND:VCARD\r\n' "$CT_UID" > "$WORK/contact.vcf"
		printf 'MIAB fork seed file for %s\n' "$P" > "$WORK/seedfile.txt"
		nc_put "${CAL}seed-event-1.ics" "text/calendar; charset=utf-8" "$WORK/event.ics"
		case $HTTP_CODE in 201|204) ;; *) die "PUT event: HTTP $HTTP_CODE $(body | head -c 300)";; esac
		nc_put "${ABK}seed-contact-1.vcf" "text/vcard; charset=utf-8" "$WORK/contact.vcf"
		case $HTTP_CODE in 201|204) ;; *) die "PUT contact: HTTP $HTTP_CODE $(body | head -c 300)";; esac
		http alice MKCOL "https://$H$DIR"
		case $HTTP_CODE in 201|405) ;; *) die "MKCOL $DIR: HTTP $HTTP_CODE";; esac
		nc_put "${DIR}seedfile.txt" "text/plain" "$WORK/seedfile.txt"
		case $HTTP_CODE in 201|204) ;; *) die "PUT file: HTTP $HTTP_CODE $(body | head -c 300)";; esac
		SHA=$(sha256sum "$WORK/seedfile.txt" | cut -d' ' -f1)
		log "Nextcloud event, contact and file stored"
		python3 -I - "$NC_VERSION" "$ALICE" "$NCUID" "${CAL}seed-event-1.ics" "$EV_UID" \
			"${ABK}seed-contact-1.vcf" "$CT_UID" "${DIR}seedfile.txt" "$SHA" <<'EOF' | part nextcloud
import json, sys
v, user, uid, ev, evuid, ct, ctuid, fp, sha = sys.argv[1:]
print(json.dumps({"version": v, "user": user, "nc_uid": uid,
                  "event": {"path": ev, "uid": evuid}, "contact": {"path": ct, "uid": ctuid},
                  "file": {"path": fp, "sha256": sha}}))
EOF
	fi
fi

# ---------------------------------------------------------------- custom DNS + DKIM
api PUT "dns/custom/seedtest.$P/TXT" -H "Content-Type: text/plain" --data-binary "miab-seed-txt-v1"
[ "$HTTP_CODE" = 200 ] || die "custom DNS: HTTP $HTTP_CODE $(body)"
log "custom DNS seedtest.$P TXT: $(body | head -1)"
printf '{"qname": "seedtest.%s", "rtype": "TXT", "value": "miab-seed-txt-v1"}\n' "$P" | part dns_custom

DKIM_TXT="$STORAGE_ROOT/mail/dkim/mail.txt"
if [ -s "$STORAGE_ROOT/mail/dkim/mail.private" ] && [ -s "$DKIM_TXT" ]; then
	DKIM_P=$(tr -d '\n\t"() ' < "$DKIM_TXT" | sed -n 's/.*p=\([A-Za-z0-9+\/=]*\).*/\1/p')
	log "DKIM key present (p=${DKIM_P:0:24}...)"
	printf '{"selector": "mail", "p": "%s"}\n' "$DKIM_P" | part dkim
else
	warn "DKIM key missing in $STORAGE_ROOT/mail/dkim"
	echo '{"error": "missing"}' | part dkim
fi

# ---------------------------------------------------------------- Roundcube identity
rc_sql() { sudo -u www-data sqlite3 "$RCDB" "$1" || warn "sqlite3 failed: $1"; }
rc_login() {
	local jar="$WORK/rc.jar" token
	http - GET "https://$H/mail/" -c "$jar" -b "$jar"
	token=$(grep -o 'name="_token" value="[^"]*"' "$WORK/body" | head -1 | sed 's/.*value="//; s/"$//')
	[ -n "$token" ] || { warn "no Roundcube login token"; return 1; }
	http - POST "https://$H/mail/?_task=login" -c "$jar" -b "$jar" \
		--data-urlencode "_token=$token" -d _task=login -d _action=login \
		-d _timezone=Europe/Berlin -d _url= \
		--data-urlencode "_user=$ALICE" --data-urlencode "_pass@$WORK/pw"
	[ "$HTTP_CODE" = 302 ]
}
if [ "${SEED_SKIP_ROUNDCUBE:-0}" = 1 ]; then
	echo '{"skipped": "SEED_SKIP_ROUNDCUBE=1"}' | part roundcube
elif [ ! -f "$RCDB" ]; then
	warn "Roundcube database $RCDB not found - skipping identity"
	echo '{"skipped": "no roundcube.sqlite"}' | part roundcube
else
	RC_UID=$(rc_sql "SELECT user_id FROM users WHERE username='$ALICE' LIMIT 1;")
	if [ -z "$RC_UID" ]; then
		log "no Roundcube user row for $ALICE yet - logging in once"
		rc_login && log "Roundcube login ok" || warn "Roundcube login failed (HTTP $HTTP_CODE)"
		RC_UID=$(rc_sql "SELECT user_id FROM users WHERE username='$ALICE' LIMIT 1;")
	fi
	if [ -z "$RC_UID" ]; then
		warn "Roundcube user row for $ALICE still missing - identity skipped"
		echo '{"skipped": "no roundcube user row for alice after login attempt"}' | part roundcube
	else
		N=$(rc_sql "SELECT count(*) FROM identities WHERE user_id=$RC_UID AND name='Alice Seed' AND del=0;")
		if [ "$N" = 0 ]; then
			rc_sql "INSERT INTO identities (user_id, changed, del, standard, name, organization, email, \"reply-to\", bcc, signature, html_signature) VALUES ($RC_UID, datetime('now'), 0, 0, 'Alice Seed', 'MIAB Seed', 'info@$P', '', '', 'Gruss, Alice -- seed-signature-marker', 0);"
			log "Roundcube identity 'Alice Seed' inserted for user_id $RC_UID"
		else
			log "Roundcube identity 'Alice Seed' already present"
		fi
		printf '{"user_id": %s, "identity": {"username": "%s", "name": "Alice Seed", "email": "info@%s", "signature_marker": "seed-signature-marker", "db": "%s"}}\n' \
			"$RC_UID" "$ALICE" "$P" "$RCDB" | part roundcube
	fi
fi

# ---------------------------------------------------------------- manifest data
api GET "mail/aliases?format=json"
cp "$WORK/body" "$WORK/aliases.json"
py aliases "$WORK/aliases.json" | part aliases
py sievelist "$ALICE" "$CAROL" | part sieve
py mailstate "$ALICE" "$BOB" "$CAROL" | part mailstate
{
	printf '{'
	first=1
	for u in "$ALICE" "$BOB" "$CAROL"; do
		api GET "mail/users/quota?email=$u&text=1"
		[ $first = 1 ] || printf ', '
		first=0
		printf '"%s": "%s"' "$u" "$(body | tr -d '\n')"
	done
	printf '}\n'
} | part quotas
for u in "$ALICE" "$BOB" "$CAROL"; do
	log "doveadm quota $u: $(doveadm quota get -u "$u" 2>&1 | awk 'NR==2{print $3"/"$4" "$5}')"
done

# ---------------------------------------------------------------- backup
BACKUP_JSON='{"skipped": "SEED_SKIP_BACKUP=1"}'
if [ "${SEED_SKIP_BACKUP:-0}" != 1 ]; then
	api GET system/backup/config
	TARGET=$(py jsonget "$WORK/body" target 2>/dev/null || echo unknown)
	if [ "$TARGET" = off ]; then
		api POST system/backup/config -d target=local -d target_user= -d target_pass= -d min_age=3
		log "backup target was 'off', set to local: $(body | head -1)"
		TARGET=local
	fi
	MIABDIR=$(sed -n 's|^export PYTHONPATH=\(.*\)/management$|\1|p' /usr/local/lib/mailinabox/start | head -1)
	if [ "$TARGET" != local ] && [ "${SEED_BACKUP_ANY_TARGET:-0}" != 1 ]; then
		warn "backup target is '$TARGET', not local - backup run skipped (SEED_BACKUP_ANY_TARGET=1 to force)"
		BACKUP_JSON=$(printf '{"skipped": "target %s"}' "$TARGET")
	elif [ -z "$MIABDIR" ] || [ ! -f "$MIABDIR/management/backup.py" ]; then
		warn "management/backup.py not found (start script: /usr/local/lib/mailinabox/start)"
		BACKUP_JSON='{"skipped": "backup.py not found"}'
	else
		log "running $MIABDIR/management/backup.py (stops/starts mail services briefly) ..."
		if (cd "$MIABDIR" && /usr/local/lib/mailinabox/env/bin/python management/backup.py) > "$WORK/backup.log" 2>&1; then
			log "backup ok"
		else
			warn "backup failed: $(tail -5 "$WORK/backup.log")"
		fi
		api GET system/backup/status
		cp "$WORK/body" "$WORK/backup-status.json"
		BACKUP_JSON=$(python3 -I - "$WORK/backup-status.json" "$TARGET" <<'EOF'
import json, sys
try:
    j = json.load(open(sys.argv[1]))
except Exception as e:
    j = {"error": str(e)}
b = j.get("backups") or []
print(json.dumps({"target": sys.argv[2], "error": j.get("error"), "count": len(b),
                  "latest": (b[0].get("date_str") or b[0].get("date")) if b else None}))
EOF
)
		log "backup status: $BACKUP_JSON"
	fi
fi
printf '%s\n' "$BACKUP_JSON" | part backup

# ---------------------------------------------------------------- assemble
python3 -I - "$H" "$P" "$S2" "$S3" "$MIAB_VERSION" "${NC_VERSION:-}" <<'EOF' | part meta
import json, sys, time
h, p, s2, s3, v, nc = sys.argv[1:]
print(json.dumps({"created": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "hostname": h, "primary_domain": p,
                  "seed2": s2, "seed3": s3, "miab_version": v, "nextcloud_version": nc,
                  "generator": "tests/fork/seed-legacy.sh"}))
EOF
py assemble "$WORK/parts" "$MANIFEST" | sed 's/^/[seed] /'
log "done"
