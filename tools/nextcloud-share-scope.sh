#!/bin/bash
#
# Nextcloud: who may see and share with whom
# ------------------------------------------
#
# NEXTCLOUD_SHARE_SCOPE in /etc/mailinabox.conf:
#
#   domain (default)  Users only see and share with the accounts of their own
#                     mail domain: share dialog, contacts menu, the system
#                     address book over CardDAV, calendar sharing and team
#                     member search. Members of the Nextcloud group "admin"
#                     see and share with everyone.
#   all               Upstream behaviour: everyone sees everyone.
#
# Nextcloud has no setting for "same mail domain", so every mail domain becomes
# a Nextcloud group with the domain as its name, and Nextcloud is told to let
# users share only with members of their own groups:
#
#   core shareapi_only_share_with_group_members      yes
#   core shareapi_restrict_user_enumeration_to_group yes
#   circles search_from_collaborator                 1  (team member search
#                                                       uses the same rules)
#
# Every setup run sets them again. Autocompletion in the share dialog
# (shareapi_allow_share_dialog_user_enumeration) is left as the admin set it:
# turned off, users only find exact matches of their own domain.
#
# user_external puts a new user into the group of the domain at the first
# login (groupDomain, the 6th IMAP backend argument in setup/nextcloud.sh), but
# only at that first login. This script adds everyone else (users from before,
# addresses typed with capitals at the first login) and puts the members of
# the group "admin" into every domain group. Nextcloud cannot exempt admins
# from the rule, so membership in all domain groups is what lets them see
# everyone.
#
# Setup runs this script; cron runs it every 5 minutes with --cron (groups
# only), so new domains, new users and new admins are picked up without a setup
# run. Until then the admins do not see a domain whose first user just logged
# in.
# It never removes anyone from a group: with "share only with group members"
# on, Nextcloud deletes the shares of a user who leaves a group and then has
# no group in common with the other side.
#
# Switching to "all" (in /etc/mailinabox.conf, then run setup) puts the
# settings above back once to what they were before this script first set
# them. The domain groups stay, so do shares made to them.

set -euo pipefail

if [ "$(id -u)" != 0 ]; then
	echo "Run this script as root." >&2
	exit 1
fi

source /etc/mailinabox.conf # load global vars
PHP_VER=${PHP_VER:-8.5} # keep in sync with setup/functions.sh (not in /etc/mailinabox.conf)

CRON=0
if [ "${1:-}" = "--cron" ]; then
	CRON=1
elif [ -n "${1:-}" ]; then
	echo "Usage: $0 [--cron]" >&2
	exit 2
fi

SCOPE=${NEXTCLOUD_SHARE_SCOPE:-domain}
if [ "$SCOPE" != domain ] && [ "$SCOPE" != all ]; then
	echo "NEXTCLOUD_SHARE_SCOPE=$SCOPE in /etc/mailinabox.conf is neither 'domain' nor 'all', using 'domain'." >&2
	SCOPE=domain
fi

function occ {
	sudo -u www-data "php$PHP_VER" /usr/local/lib/owncloud/occ "$@"
}

# The key that remembers that this script turned the restriction on, so that
# "all" undoes the settings once and leaves later changes of the admin alone,
# and the key with the values from before (JSON, null = was not set).
MARKER=mailinabox_share_scope
PREV=mailinabox_share_scope_prev
SETTINGS=(
	"core shareapi_only_share_with_group_members yes"
	"core shareapi_restrict_user_enumeration_to_group yes"
	"circles search_from_collaborator 1"
)

if [ $CRON = 1 ] && [ "$SCOPE" != domain ]; then
	exit 0
fi

# One run at a time (setup and the cron job).
exec 9> /run/mailinabox-nextcloud-share-scope.lock
if [ $CRON = 1 ]; then
	flock -n 9 || exit 0
else
	flock 9
fi

# Nextcloud must be installed and not in maintenance mode or halfway through
# an upgrade. Cron skips quietly, e.g. while setup upgrades Nextcloud.
STATUS=$(occ status --output=json 2> /dev/null || true)
if ! python3 -I -c '
import json, sys
try:
	s = json.loads(sys.argv[1])
except ValueError:
	sys.exit(1)
sys.exit(0 if s.get("installed") and not s.get("maintenance") and not s.get("needsDbUpgrade") else 1)
' "$STATUS"; then
	[ $CRON = 1 ] && exit 0
	echo "Nextcloud is not ready (not installed, maintenance mode or upgrade needed), sharing scope not applied." >&2
	exit 1
fi

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

if [ $CRON = 0 ]; then
	marker=$(occ config:app:get core "$MARKER" 2> /dev/null || true)
	if [ "$SCOPE" = domain ]; then
		if [ "$marker" != domain ]; then
			# First time: save the values from before, then the marker, and only
			# then change anything. An interrupted run is thus undone by "all".
			for s in "${SETTINGS[@]}"; do
				read -r app key value <<< "$s"
				if v=$(occ config:app:get "$app" "$key" 2> /dev/null); then
					printf '%s\t%s\t1\t%s\n' "$app" "$key" "$v"
				else
					printf '%s\t%s\t0\t\n' "$app" "$key"
				fi
			done > "$TMP/prev"
			prev=$(python3 -I -c '
import json, sys
d = {}
for line in open(sys.argv[1], encoding="utf-8"):
	app, key, isset, value = line.rstrip("\n").split("\t", 3)
	d[app + " " + key] = value if isset == "1" else None
print(json.dumps(d))
' "$TMP/prev")
			occ config:app:set core "$PREV" --value "$prev" > /dev/null
			occ config:app:set core "$MARKER" --value domain > /dev/null
		fi
		for s in "${SETTINGS[@]}"; do
			read -r app key value <<< "$s"
			occ config:app:set "$app" "$key" --value "$value" > /dev/null
		done
	else
		if [ "$marker" = domain ]; then
			# Put back what was there before; without a saved value, delete.
			prev=$(occ config:app:get core "$PREV" 2> /dev/null || true)
			for s in "${SETTINGS[@]}"; do
				read -r app key value <<< "$s"
				printf '%s %s\n' "$app" "$key"
			done | python3 -I -c '
import json, sys
try:
	prev = json.loads(sys.argv[1])
except ValueError:
	prev = {}
if not isinstance(prev, dict):
	prev = {}
for line in sys.stdin:
	k = line.rstrip("\n")
	v = prev.get(k)
	print(k.replace(" ", "\t", 1) + ("\tdelete\t" if not isinstance(v, str) else "\tset\t" + v))
' "$prev" > "$TMP/restore"
			while IFS=$'\t' read -r app key action value; do
				if [ "$action" = set ]; then
					occ config:app:set "$app" "$key" --value "$value" > /dev/null
				else
					occ config:app:delete "$app" "$key" > /dev/null
				fi
			done < "$TMP/restore"
			occ config:app:delete core "$PREV" > /dev/null
			occ config:app:delete core "$MARKER" > /dev/null
			echo "Nextcloud sharing: restriction to the own mail domain removed (NEXTCLOUD_SHARE_SCOPE=all), earlier sharing options restored. The domain groups were kept."
		fi
		exit 0
	fi
fi

# Domain groups: work out which users are missing in which group.
occ user:list --limit 0 --output=json > "$TMP/users.json"
occ group:list --limit 1000000 --output=json > "$TMP/groups.json"
python3 -I - "$TMP/users.json" "$TMP/groups.json" "$CRON" > "$TMP/plan" << 'EOF'
import json, sys

def load(path):
	# occ prints [] instead of {} when there is nothing to list.
	with open(path, encoding="utf-8") as f:
		d = json.load(f)
	return d if isinstance(d, dict) else {}

users = load(sys.argv[1])    # user id -> display name
groups = load(sys.argv[2])   # group id -> [user ids]
quiet = sys.argv[3] == "1"   # cron: no warnings every few minutes

members = {}
for uid in users:
	uid = str(uid)
	if "@" not in uid:
		continue # e.g. the local Nextcloud account "root"
	domain = uid.rsplit("@", 1)[1].lower()
	if "." not in domain or domain == "admin":
		continue
	if len(domain) > 64:
		# Nextcloud stores longer group names under a hash; occ cannot find
		# such a group by its name again.
		if not quiet:
			print("Nextcloud sharing: mail domain %s is longer than 64 characters, no group for %s."
				% (domain, uid), file=sys.stderr)
		continue
	members.setdefault(domain, set()).add(uid)

# Members of "admin" that are mail accounts (not "root") see all domains.
admins = {str(u) for u in groups.get("admin", []) if "@" in str(u)}

for domain in sorted(members):
	missing = sorted((members[domain] | admins) - {str(u) for u in groups.get(domain, [])})
	if domain not in groups:
		print("group\t" + domain)
	if missing:
		print("add\t" + domain + "\t" + "\t".join(missing))
print("summary\t%d\t%d" % (len(members), len(admins)))
EOF

# The plan comes from a snapshot: a first login may create a group in the
# meantime (group:add then fails) and a user may be deleted (group:adduser
# fails for the whole call, but adds the others). Neither may stop setup;
# cron only warns at setup, not every few minutes.
function warn {
	[ $CRON = 1 ] || echo "Nextcloud sharing: $*" >&2
}
added=0
while IFS=$'\t' read -r -a line; do
	case "${line[0]}" in
		group)
			if ! occ group:add "${line[1]}" > /dev/null 2>&1 \
				&& ! occ group:info "${line[1]}" > /dev/null 2>&1; then
				warn "could not create the group ${line[1]}."
			fi
			;;
		add)
			if occ group:adduser "${line[1]}" "${line[@]:2}" > /dev/null 2>&1; then
				added=$((added + ${#line[@]} - 2))
			else
				warn "not all of ${line[*]:2} could be added to the group ${line[1]} (deleted meanwhile?)."
			fi
			;;
		summary)
			domains=${line[1]} admins=${line[2]}
			;;
	esac
done < "$TMP/plan"

if [ $CRON = 0 ]; then
	echo "Nextcloud sharing: limited to the own mail domain ($domains domain groups, admins in all of them: $admins, memberships added: $added)."
fi
