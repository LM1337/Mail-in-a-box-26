#!/bin/bash
#
# Z-Push: The Microsoft Exchange protocol server
# ----------------------------------------------
#
# Mostly for use on iOS which doesn't support IMAP IDLE.
#
# Although Ubuntu ships Z-Push (as d-push) it has a dependency on Apache
# so we won't install it that way.
#
# Thanks to http://frontender.ch/publikationen/push-mail-server-using-nginx-and-z-push.html.

source setup/functions.sh # load our functions
source /etc/mailinabox.conf # load global vars

# Prereqs.

echo "Installing Z-Push (Exchange/ActiveSync server)..."
apt_install \
       php"${PHP_VER}"-soap php"${PHP_VER}"-imap libawl-php php"$PHP_VER"-xml php"${PHP_VER}"-intl

phpenmod -v "$PHP_VER" imap

# Copy Z-Push into place.
VERSION=2.7.7
TARGETHASH=7a8e0094adf216521ee491078f78e709cd68257d05a868b3992d5665c01d8790 # SHA256 of the GitHub tag archive (no upstream checksum published)
# Every change of the fork to Z-Push's code is a block of
# conf/zpush/z-push.patches (B126, B128; tools/patch_source.py). They are
# applied to a fresh copy of Z-Push before it is moved into place, and the
# installed tree is marked with the version and the checksum of that file. A
# tree with another mark (another version, another revision of the patch
# file, or none: Z-Push as installed up to rc7), or one that no longer has
# every change (a file changed by hand), is replaced by a fresh copy: a
# block is always applied to Z-Push's original text.
ZPUSH_PATCHES=conf/zpush/z-push.patches
ZPUSH_STAMP="$VERSION+patches-$(sha256sum "$ZPUSH_PATCHES" | cut -c1-16)"
needs_update=0 #NODOC
if [ ! -f /usr/local/lib/z-push/version ]; then
	needs_update=1 #NODOC
elif [[ $ZPUSH_STAMP != $(cat /usr/local/lib/z-push/version) ]]; then
	# checks if the version (or the fork's patch file) changed
	needs_update=1 #NODOC
elif ! tools/patch_source.py --check /usr/local/lib/z-push "$ZPUSH_PATCHES"; then
	echo "Z-Push in /usr/local/lib/z-push does not have all of the fork's changes; installing it again."
	needs_update=1 #NODOC
fi
if [ $needs_update == 1 ]; then
	# Download, extract and patch in a directory of root's own (mktemp -d:
	# root, 0700), not under a fixed name in /tmp that another local user
	# could create first (B97), and nowhere another account can write. It is
	# made next to /usr/local/lib/z-push, on the same file system, so that
	# moving the tree into place is a rename: from /tmp (a tmpfs) mv copied
	# it file by file, and Z-Push's requests in that second found its
	# directories still without permissions for www-data (seen in the update
	# test under client load: "Permission denied" for include/z_carddav.php).
	if [ -z "$(find /usr/local/lib -maxdepth 0 -user root ! -perm /022)" ]; then
		echo "/usr/local/lib is not a directory of root's own."
		exit 1
	fi
	ZPUSH_TMP=$(mktemp -d /usr/local/lib/.z-push-new.XXXXXXXX)
	wget_verify "https://github.com/Z-Hub/Z-Push/archive/refs/tags/$VERSION.zip" $TARGETHASH "$ZPUSH_TMP/z-push.zip"
	unzip -q "$ZPUSH_TMP/z-push.zip" -d "$ZPUSH_TMP/z-push"
	ZPUSH_SRC="$ZPUSH_TMP/z-push/Z-Push-$VERSION/src"
	if [ -L "$ZPUSH_SRC" ] || [ ! -d "$ZPUSH_SRC" ]; then
		echo "The Z-Push $VERSION archive has no directory Z-Push-$VERSION/src."
		rm -rf "$ZPUSH_TMP"
		exit 1
	fi

	# The fork's changes (see above and conf/zpush/z-push.patches). Setup
	# stops if one does not apply, instead of running code that the fork has
	# not checked: the miab-zpush jail relies on the changes of B126.
	if ! tools/patch_source.py "$ZPUSH_SRC" "$ZPUSH_PATCHES" > /dev/null \
		|| ! tools/patch_source.py --check "$ZPUSH_SRC" "$ZPUSH_PATCHES"; then
		echo "Could not apply $ZPUSH_PATCHES to Z-Push $VERSION."
		rm -rf "$ZPUSH_TMP"
		exit 1
	fi
	echo "$ZPUSH_STAMP" > "$ZPUSH_SRC/version"

	# Move the patched tree into place. The old one is renamed away first and
	# removed after, so that Z-Push is missing only between two renames (in
	# the same directory). A temporary directory that an earlier run left
	# behind (setup stopped there) is removed as well.
	rm -rf /usr/local/lib/z-push.old
	if [ -e /usr/local/lib/z-push ]; then
		mv /usr/local/lib/z-push /usr/local/lib/z-push.old
	fi
	mv "$ZPUSH_SRC" /usr/local/lib/z-push
	rm -rf /usr/local/lib/z-push.old "$ZPUSH_TMP"
	find /usr/local/lib -maxdepth 1 -name '.z-push-new.*' -type d -user root -exec rm -rf -- {} +

	# Create admin and top scripts with PHP_VER  
	rm -f /usr/sbin/z-push-{admin,top}
    echo '#!/bin/bash' > /usr/sbin/z-push-admin
    echo php"$PHP_VER" /usr/local/lib/z-push/z-push-admin.php '"$@"' >> /usr/sbin/z-push-admin
    chmod 755 /usr/sbin/z-push-admin
    echo '#!/bin/bash' > /usr/sbin/z-push-top
    echo php"$PHP_VER" /usr/local/lib/z-push/z-push-top.php '"$@"' >> /usr/sbin/z-push-top
    chmod 755 /usr/sbin/z-push-top
fi

# Configure default config.
sed -i "s^define('TIMEZONE', .*^define('TIMEZONE', '$(timedatectl show -p Timezone --value)');^" /usr/local/lib/z-push/config.php
sed -i "s/define('BACKEND_PROVIDER', .*/define('BACKEND_PROVIDER', 'BackendCombined');/" /usr/local/lib/z-push/config.php
sed -i "s/define('USE_FULLEMAIL_FOR_LOGIN', .*/define('USE_FULLEMAIL_FOR_LOGIN', true);/" /usr/local/lib/z-push/config.php
sed -i "s/define('LOGLEVEL', .*/define('LOGLEVEL', LOGLEVEL_ERROR);/" /usr/local/lib/z-push/config.php
# Log failed logins ("Failed to authenticate user '...' from IP ...", the
# message as conf/zpush/z-push.patches changes it) for the miab-zpush jail
# (B126). They are warnings: Z-Push writes warnings and errors
# to z-push-error.log whatever LOGLEVEL is, so z-push.log stays as quiet as
# before. autodiscover/config.php sets the same.
sed -i "s/define('LOGAUTHFAIL', .*/define('LOGAUTHFAIL', true);/" /usr/local/lib/z-push/config.php
grep -qF "define('LOGAUTHFAIL', true);" /usr/local/lib/z-push/config.php \
	|| { echo "Z-Push's config.php has no LOGAUTHFAIL setting; the miab-zpush jail would see no failed login."; exit 1; }

# Longest Ping (push long poll) a phone may ask for: 3540 s (59 min), Z-Push's
# own maximum and the server heartbeat Apple advises. A longer request gets
# status 5 with this bound at once, and the phone pings with it. Without a
# bound Z-Push keeps any heartbeat open, beyond nginx's fastcgi_read_timeout
# for /Microsoft-Server-ActiveSync (3660 s, conf/nginx-alldomains.conf), which
# must stay longer than this (it was 630 s, and iPhones got 504 after 10.5
# minutes for every Ping, B129).
sed -i "s/define('PING_HIGHER_BOUND_LIFETIME', .*/define('PING_HIGHER_BOUND_LIFETIME', 3540);/" /usr/local/lib/z-push/config.php
# The sed does nothing if a new Z-Push changes or drops that line. Setup goes
# on (nginx's 3660 s still cover heartbeats up to about an hour), but says so.
if ! grep -q "^[[:space:]]*define('PING_HIGHER_BOUND_LIFETIME', 3540);" /usr/local/lib/z-push/config.php; then
	echo "WARNING: Z-Push's config.php has no PING_HIGHER_BOUND_LIFETIME line to set: phones may ask for Pings longer than nginx's limit for ActiveSync (B129)."
fi

# Configure BACKEND
rm -f /usr/local/lib/z-push/backend/combined/config.php
cp conf/zpush/backend_combined.php /usr/local/lib/z-push/backend/combined/config.php

# Configure IMAP
rm -f /usr/local/lib/z-push/backend/imap/config.php
cp conf/zpush/backend_imap.php /usr/local/lib/z-push/backend/imap/config.php
sed -i "s%STORAGE_ROOT%$STORAGE_ROOT%" /usr/local/lib/z-push/backend/imap/config.php

# Configure CardDav
rm -f /usr/local/lib/z-push/backend/carddav/config.php
cp conf/zpush/backend_carddav.php /usr/local/lib/z-push/backend/carddav/config.php

# Configure CalDav
rm -f /usr/local/lib/z-push/backend/caldav/config.php
cp conf/zpush/backend_caldav.php /usr/local/lib/z-push/backend/caldav/config.php

# Configure Autodiscover
rm -f /usr/local/lib/z-push/autodiscover/config.php
cp conf/zpush/autodiscover_config.php /usr/local/lib/z-push/autodiscover/config.php
sed -i "s/PRIMARY_HOSTNAME/$PRIMARY_HOSTNAME/" /usr/local/lib/z-push/autodiscover/config.php
sed -i "s^define('TIMEZONE', .*^define('TIMEZONE', '$(timedatectl show -p Timezone --value)');^" /usr/local/lib/z-push/autodiscover/config.php

# Some directories it will use.

mkdir -p /var/lib/z-push
chmod 750 /var/lib/z-push
chown www-data:www-data /var/lib/z-push

# The log directory belongs to root, group www-data, which may read it but not
# change its entries (B126). fail2ban (root) opens the error logs by path, so
# www-data, the account of Roundcube, Nextcloud and Z-Push, must not be able to
# replace them with a symbolic link or a FIFO (which would stall all jails).
# Before, the directory belonged to www-data: setup removes what is not a
# regular file in it. Z-Push writes into its four log files, which therefore
# must exist (it cannot create them any more): setup and logrotate create them
# as root, in this directory of root's own, and give them to www-data.
mkdir -p /var/log/z-push
if [ -L /var/log/z-push ] || [ ! -d /var/log/z-push ]; then
	echo "/var/log/z-push is not a directory."; exit 1
fi
chown root:www-data /var/log/z-push
chmod 750 /var/log/z-push
find /var/log/z-push -mindepth 1 -maxdepth 1 ! -type f -exec rm -rf -- {} +
# A file with more than one link may be a hard link that www-data made to a
# file of another account: the chown and chmod below would change that file
# (only fs.protected_hardlinks prevents such a link). Remove the name; the
# loop creates the log file again (B126).
find /var/log/z-push -mindepth 1 -maxdepth 1 -type f -links +1 -delete
for f in z-push.log z-push-error.log autodiscover.log autodiscover-error.log; do
	[ -f "/var/log/z-push/$f" ] || install -o www-data -g www-data -m 640 /dev/null "/var/log/z-push/$f"
	chown -h www-data:www-data "/var/log/z-push/$f"
	chmod 640 "/var/log/z-push/$f"
done

# Add log rotation

# logrotate works as root, in a directory that only root may change. "create"
# puts an empty file in place at once, for Z-Push (which cannot create it) and
# for fail2ban (miab-zpush).
tools/write_conf.py /etc/logrotate.d/z-push <<EOF;
/var/log/z-push/*.log {
	weekly
	missingok
	rotate 52
	compress
	delaycompress
	notifempty
	create 0640 www-data www-data
}
EOF

# Restart service.

restart_php_fpm

# Fix states after upgrade

if [ $needs_update == 1 ]; then
	hide_output php"$PHP_VER" /usr/local/lib/z-push/z-push-admin.php -a fixstates
fi
