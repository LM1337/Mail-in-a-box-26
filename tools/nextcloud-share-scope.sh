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
#   core shareapi_allow_share_dialog_user_enumeration yes
#   core shareapi_restrict_user_enumeration_to_group yes
#   circles search_from_collaborator                 1  (team member search
#                                                       uses the same rules)
#
# user_external puts a new user into the group of the domain at the first
# login (groupDomain, the 6th IMAP backend argument in setup/nextcloud.sh), but
# only at that first login. This script adds everyone else (users from before,
# addresses typed with capitals at the first login) and puts the members of
# the group "admin" into every domain group. Nextcloud cannot exempt admins
# from the rule, so membership in all domain groups is what lets them see
# everyone.
#
# Setup runs this script; cron runs it every hour with --cron (groups only), so
# new domains, new users and new admins are picked up without a setup run.
# It never removes anyone from a group: with "share only with group members"
# on, Nextcloud deletes the shares of a user who leaves a group and then has
# no group in common with the other side.
#
# Switching to "all" (in /etc/mailinabox.conf, then run setup) removes the
# settings above once. The domain groups stay, so do shares made to them.

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
# "all" removes the settings once and leaves later changes of the admin alone.
MARKER=mailinabox_share_scope
SETTINGS=(
	"core shareapi_only_share_with_group_members yes"
	"core shareapi_allow_share_dialog_user_enumeration yes"
	"core shareapi_restrict_user_enumeration_to_group yes"
	"circles search_from_collaborator 1"
)

if [ $CRON = 1 ] && [ "$SCOPE" != domain ]; then
	exit 0
fi

# One run at a time (setup and the hourly cron job).
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

if [ $CRON = 0 ]; then
	if [ "$SCOPE" = domain ]; then
		for s in "${SETTINGS[@]}"; do
			read -r app key value <<< "$s"
			occ config:app:set "$app" "$key" --value "$value" > /dev/null
		done
		occ config:app:set core "$MARKER" --value domain > /dev/null
	else
		if [ "$(occ config:app:get core "$MARKER" 2> /dev/null || true)" = domain ]; then
			for s in "${SETTINGS[@]}"; do
				read -r app key value <<< "$s"
				occ config:app:delete "$app" "$key" > /dev/null
			done
			occ config:app:delete core "$MARKER" > /dev/null
			echo "Nextcloud sharing: restriction to the own mail domain removed (NEXTCLOUD_SHARE_SCOPE=all). The domain groups were kept."
		fi
		exit 0
	fi
fi

# Domain groups: work out which users are missing in which group.
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
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
quiet = sys.argv[3] == "1"   # cron: no hourly warnings

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

added=0
while IFS=$'\t' read -r -a line; do
	case "${line[0]}" in
		group)
			occ group:add "${line[1]}" > /dev/null
			;;
		add)
			occ group:adduser "${line[1]}" "${line[@]:2}" > /dev/null
			added=$((added + ${#line[@]} - 2))
			;;
		summary)
			domains=${line[1]} admins=${line[2]}
			;;
	esac
done < "$TMP/plan"

if [ $CRON = 0 ]; then
	echo "Nextcloud sharing: limited to the own mail domain ($domains domain groups, admins in all of them: $admins, memberships added: $added)."
fi
