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
needs_update=0 #NODOC
if [ ! -f /usr/local/lib/z-push/version ]; then
	needs_update=1 #NODOC
elif [[ $VERSION != $(cat /usr/local/lib/z-push/version) ]]; then
	# checks if the version
	needs_update=1 #NODOC
fi
if [ $needs_update == 1 ]; then
	# Download into a directory of root's own, not under a fixed name in /tmp
	# that another local user could create first (B97).
	ZPUSH_TMP=$(mktemp -d)
	wget_verify "https://github.com/Z-Hub/Z-Push/archive/refs/tags/$VERSION.zip" $TARGETHASH "$ZPUSH_TMP/z-push.zip"

	# Extract into place.
	rm -rf /usr/local/lib/z-push
	unzip -q "$ZPUSH_TMP/z-push.zip" -d "$ZPUSH_TMP/z-push"
	mv "$ZPUSH_TMP"/z-push/*/src /usr/local/lib/z-push
	rm -rf "$ZPUSH_TMP"

	# Create admin and top scripts with PHP_VER  
	rm -f /usr/sbin/z-push-{admin,top}
    echo '#!/bin/bash' > /usr/sbin/z-push-admin
    echo php"$PHP_VER" /usr/local/lib/z-push/z-push-admin.php '"$@"' >> /usr/sbin/z-push-admin
    chmod 755 /usr/sbin/z-push-admin
    echo '#!/bin/bash' > /usr/sbin/z-push-top
    echo php"$PHP_VER" /usr/local/lib/z-push/z-push-top.php '"$@"' >> /usr/sbin/z-push-top
    chmod 755 /usr/sbin/z-push-top
	
	echo $VERSION > /usr/local/lib/z-push/version
fi

# Configure default config.
sed -i "s^define('TIMEZONE', .*^define('TIMEZONE', '$(timedatectl show -p Timezone --value)');^" /usr/local/lib/z-push/config.php
sed -i "s/define('BACKEND_PROVIDER', .*/define('BACKEND_PROVIDER', 'BackendCombined');/" /usr/local/lib/z-push/config.php
sed -i "s/define('USE_FULLEMAIL_FOR_LOGIN', .*/define('USE_FULLEMAIL_FOR_LOGIN', true);/" /usr/local/lib/z-push/config.php
sed -i "s/define('LOGLEVEL', .*/define('LOGLEVEL', LOGLEVEL_ERROR);/" /usr/local/lib/z-push/config.php
# Log failed logins ("Failed to authenticate user '...' from IP ...", see
# below) for the miab-zpush jail (B126). They are warnings: Z-Push writes warnings and errors
# to z-push-error.log whatever LOGLEVEL is, so z-push.log stays as quiet as
# before. autodiscover/config.php sets the same.
sed -i "s/define('LOGAUTHFAIL', .*/define('LOGAUTHFAIL', true);/" /usr/local/lib/z-push/config.php
grep -qF "define('LOGAUTHFAIL', true);" /usr/local/lib/z-push/config.php \
	|| { echo "Z-Push's config.php has no LOGAUTHFAIL setting; the miab-zpush jail would see no failed login."; exit 1; }

# Z-Push writes text that a client chooses (the user name of the Authorization
# header, the e-mail address of an autodiscover request) unescaped into its
# logs. With a line break in it, a client could add a whole line of its own,
# with any address in it, to the log that the miab-zpush jail reads (B126).
# Escape the control characters of each log line (a line break becomes "\n").
# The file belongs to root, in a directory of root's own.
ZPUSH_FILELOG=/usr/local/lib/z-push/lib/log/filelog.php
if ! grep -qF "MIAB-B126" "$ZPUSH_FILELOG"; then
	sed 's/^        return \$log;$/        return addcslashes($log, "\\0..\\37\\177"); \/\/ MIAB-B126: no line breaks from clients/' "$ZPUSH_FILELOG" \
		| tools/write_conf.py "$ZPUSH_FILELOG"
fi
grep -qF 'return addcslashes($log, "\0..\37\177"); // MIAB-B126' "$ZPUSH_FILELOG" \
	|| { echo "Could not patch $ZPUSH_FILELOG (Z-Push $VERSION); its log lines would not be escaped."; exit 1; }

# Z-Push logs a failed ActiveSync login as "[<user>] IP: <address> failed to
# authenticate user '<user>'": text that the client chooses on both sides of
# the address, so no filter can tell which address Z-Push wrote. Put the
# address last, as in the autodiscover message, where the jail's filter
# anchors it at the end of the line (B126). Only the format string changes:
# its arguments stay the same, in their positions (%1$s, %2$s).
ZPUSH_INDEX=/usr/local/lib/z-push/index.php
ZPUSH_AUTHFAIL_FORMAT="\"Failed to authenticate user '%2\\\$s' from IP %1\\\$s.\""
if ! grep -qF "$ZPUSH_AUTHFAIL_FORMAT" "$ZPUSH_INDEX"; then
	sed -f <(cat <<'SED'
s/sprintf("IP: %s failed to authenticate user '%s'",/sprintf("Failed to authenticate user '%2\\$s' from IP %1\\$s.",/
SED
) "$ZPUSH_INDEX" | tools/write_conf.py "$ZPUSH_INDEX"
fi
grep -qF "$ZPUSH_AUTHFAIL_FORMAT" "$ZPUSH_INDEX" \
	|| { echo "Could not patch $ZPUSH_INDEX (Z-Push $VERSION); the miab-zpush jail would see no failed ActiveSync login."; exit 1; }

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

mkdir -p /var/log/z-push
mkdir -p /var/lib/z-push
chmod 750 /var/log/z-push
chmod 750 /var/lib/z-push
chown www-data:www-data /var/log/z-push
chown www-data:www-data /var/lib/z-push

# Add log rotation

# The directory belongs to www-data: logrotate works there as www-data (su),
# not as root by path. "create" puts an empty file in place at once, so that
# fail2ban (miab-zpush) finds its log files also before Z-Push's next request.
tools/write_conf.py /etc/logrotate.d/z-push <<EOF;
/var/log/z-push/*.log {
	su www-data www-data
	weekly
	missingok
	rotate 52
	compress
	delaycompress
	notifempty
	create 0640 www-data www-data
}
EOF

# The miab-zpush jail reads the error logs, and fail2ban does not start a
# jail whose log files do not exist. Created as www-data, in its directory.
sudo -u www-data touch /var/log/z-push/z-push-error.log /var/log/z-push/autodiscover-error.log

# Restart service.

restart_php_fpm

# Fix states after upgrade

if [ $needs_update == 1 ]; then
	hide_output php"$PHP_VER" /usr/local/lib/z-push/z-push-admin.php -a fixstates
fi
