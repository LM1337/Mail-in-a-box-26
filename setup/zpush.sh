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
# Each line starts with the user names in brackets ("[<user>]", or
# "[<user>#<user of the URL>]"), as the client sent them. With a "]" in them
# the jail's filter could not tell where the brackets end, and a warning that
# ends in text from a client could pass for a failed login with any address.
# Escape "]" and "\" there (as "\]" and "\\"), so that the first unescaped "]"
# ends the user names, and the filter requires the message that follows to be
# the failed login of that same user (B126).
IFS= read -r ZPUSH_PREFIX_SAME <<'PHP'
                $log .= ' ['. addcslashes($this->GetUser(), '\\]') .']'; // MIAB-B126: the user names escaped
PHP
IFS= read -r ZPUSH_PREFIX_BOTH <<'PHP'
                $log .= ' ['. addcslashes($this->GetAuthUser() . Request::IMPERSONATE_DELIM . $this->GetUser(), '\\]') .']'; // MIAB-B126: the user names escaped
PHP
if ! grep -qF "MIAB-B126: the user names escaped" "$ZPUSH_FILELOG"; then
	sed -f <(cat <<'SED'
s/^                \$log \.= ' \['\. \$this->GetUser() \.'\]';$/                $log .= ' ['. addcslashes($this->GetUser(), '\\\\]') .']'; \/\/ MIAB-B126: the user names escaped/
s/^                \$log \.= ' \['\. \$this->GetAuthUser() \. Request::IMPERSONATE_DELIM \. \$this->GetUser() \.'\]';$/                $log .= ' ['. addcslashes($this->GetAuthUser() . Request::IMPERSONATE_DELIM . $this->GetUser(), '\\\\]') .']'; \/\/ MIAB-B126: the user names escaped/
SED
) "$ZPUSH_FILELOG" | tools/write_conf.py "$ZPUSH_FILELOG"
fi
[ "$(grep -cxF "$ZPUSH_PREFIX_SAME" "$ZPUSH_FILELOG")" = 1 ] && [ "$(grep -cxF "$ZPUSH_PREFIX_BOTH" "$ZPUSH_FILELOG")" = 1 ] \
	&& ! grep -qE "' \\['\\. \\\$this->Get(Auth)?User\\(\\)" "$ZPUSH_FILELOG" \
	|| { echo "Could not patch $ZPUSH_FILELOG (Z-Push $VERSION); the user names at the start of its log lines would not be escaped."; exit 1; }

# Z-Push logs a failed ActiveSync login as "[<user>] IP: <address> failed to
# authenticate user '<user>'": text that the client chooses on both sides of
# the address, so no filter can tell which address Z-Push wrote. Put the
# address last, as in the autodiscover message, where the jail's filter
# anchors it at the end of the line (B126). Only the format string changes:
# its arguments stay the same, in their positions (%1$s, %2$s).
# Z-Push also writes that line for a request without a password (with the
# user name of the URL, "User=", or "unknown"): a phone sends its first
# request without credentials and waits for the login prompt, so each sync
# of a phone would count as a failed login. Write it only when the request
# had a user name and a password, i.e. when Z-Push checked a password.
ZPUSH_INDEX=/usr/local/lib/z-push/index.php
ZPUSH_AUTHFAIL_FORMAT="\"Failed to authenticate user '%2\\\$s' from IP %1\\\$s.\""
ZPUSH_AUTHFAIL_IF="if (defined('LOGAUTHFAIL') && LOGAUTHFAIL != false && Request::HasAuthenticationInfo()) // MIAB-B126"
if ! grep -qF "$ZPUSH_AUTHFAIL_FORMAT" "$ZPUSH_INDEX" || ! grep -qF "$ZPUSH_AUTHFAIL_IF" "$ZPUSH_INDEX"; then
	sed -f <(cat <<'SED'
s/sprintf("IP: %s failed to authenticate user '%s'",/sprintf("Failed to authenticate user '%2\\$s' from IP %1\\$s.",/
s/^            if (defined('LOGAUTHFAIL') && LOGAUTHFAIL != false)$/            if (defined('LOGAUTHFAIL') \&\& LOGAUTHFAIL != false \&\& Request::HasAuthenticationInfo()) \/\/ MIAB-B126: only when a password was sent/
SED
) "$ZPUSH_INDEX" | tools/write_conf.py "$ZPUSH_INDEX"
fi
grep -qF "$ZPUSH_AUTHFAIL_FORMAT" "$ZPUSH_INDEX" && [ "$(grep -cF "$ZPUSH_AUTHFAIL_IF" "$ZPUSH_INDEX")" = 1 ] \
	|| { echo "Could not patch $ZPUSH_INDEX (Z-Push $VERSION); the miab-zpush jail would not see the failed ActiveSync logins, or would count requests without a password."; exit 1; }

# A login that fails because Dovecot or Nextcloud cannot check the password
# at that moment (Dovecot answers "[UNAVAILABLE] Temporary authentication
# failure" while users.sqlite is locked, closes the connection, or does not
# run) is no wrong password, but Z-Push reported it as one: HTTP 401, which
# makes a phone ask for its password, and the failed-login line that the
# miab-zpush jail counts. Every user behind one address (a NAT, or the few
# relays of the Outlook app) could be banned so in such a window (B126).
# Z-Push answers it with 503 and Retry-After instead, which a client retries
# later, and logs no failed login. A wrong password is what Dovecot answers
# with "[AUTHENTICATIONFAILED]" (on any of c-client's tries); any other IMAP
# failure is temporary. When IMAP accepted the password, a failed CalDAV or
# CardDAV login (Nextcloud) is temporary too.
ZPUSH_IMAP=/usr/local/lib/z-push/backend/imap/imap.php
ZPUSH_COMBINED=/usr/local/lib/z-push/backend/combined/combined.php
ZPUSH_IMAP_TEMPFAIL="            if (strpos(implode(' ', (array) imap_errors()), '[AUTHENTICATIONFAILED]') === false) throw new ServiceUnavailableException(\"BackendIMAP->Logon(): Dovecot did not check the password (a temporary failure, not a wrong password)\"); // MIAB-B126"
ZPUSH_COMBINED_TEMPFAIL="                if (\$i !== array_key_first(\$this->backends)) throw new ServiceUnavailableException(sprintf(\"Combined->Logon(): %s failed after the password was accepted (a temporary failure, not a wrong password)\", \$this->config['backends'][\$i]['name'])); // MIAB-B126"
if ! grep -qF "// MIAB-B126" "$ZPUSH_IMAP"; then
	sed "s|^\(            ZLog::Write(LOGLEVEL_ERROR, sprintf(\"BackendIMAP->Logon(): can't connect as user .*\)\$|\1\n$ZPUSH_IMAP_TEMPFAIL|" "$ZPUSH_IMAP" \
		| tools/write_conf.py "$ZPUSH_IMAP"
fi
if ! grep -qF "// MIAB-B126" "$ZPUSH_COMBINED"; then
	sed "s|^\(                ZLog::Write(LOGLEVEL_DEBUG, sprintf(\"Combined->Logon() failed on %s \".*\)\$|\1\n$ZPUSH_COMBINED_TEMPFAIL|" "$ZPUSH_COMBINED" \
		| tools/write_conf.py "$ZPUSH_COMBINED"
fi
[ "$(grep -cxF "$ZPUSH_IMAP_TEMPFAIL" "$ZPUSH_IMAP")" = 1 ] && [ "$(grep -cF "MIAB-B126" "$ZPUSH_IMAP")" = 1 ] \
	&& [ "$(grep -cxF "$ZPUSH_COMBINED_TEMPFAIL" "$ZPUSH_COMBINED")" = 1 ] && [ "$(grep -cF "MIAB-B126" "$ZPUSH_COMBINED")" = 1 ] \
	|| { echo "Could not patch $ZPUSH_IMAP and $ZPUSH_COMBINED (Z-Push $VERSION); a temporary login failure would count as a failed login."; exit 1; }

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
