#!/bin/bash
# Webmail with Roundcube
# ----------------------

source setup/functions.sh # load our functions
source /etc/mailinabox.conf # load global vars

# ### Installing Roundcube

# We install Roundcube from sources, rather than from Ubuntu, because:
#
# 1. Ubuntu's `roundcube-core` package has dependencies on Apache & MySQL, which we don't want.
#
# 2. The Roundcube shipped with Ubuntu is consistently out of date.
#
# 3. It's packaged incorrectly --- it seems to be missing a directory of files.
#
# So we'll use apt-get to manually install the dependencies of roundcube that we know we need,
# and then we'll manually install roundcube from source.

# These dependencies are from `apt-cache showpkg roundcube-core`.
echo "Installing Roundcube (webmail)..."
apt_install \
	dbconfig-common \
	php"${PHP_VER}"-cli php"${PHP_VER}"-sqlite3 php"${PHP_VER}"-intl php"${PHP_VER}"-common php"${PHP_VER}"-curl php"${PHP_VER}"-imap \
	php"${PHP_VER}"-gd php"${PHP_VER}"-pspell php"${PHP_VER}"-mbstring php"${PHP_VER}"-xml libjs-jquery libjs-jquery-mousewheel libmagic1 \
	sqlite3

# Install Roundcube from source if it is not already present or if it is out of date.
# Combine the Roundcube version number with the commit hash of plugins to track
# whether we have the latest version of everything.
# For the latest versions, see:
#   https://github.com/roundcube/roundcubemail/releases
#   https://github.com/mfreiholz/persistent_login/commits/master
#   https://github.com/stremlau/html5_notifier/commits/master
#   https://github.com/mstilkerich/rcmcarddav/releases
# The package hashes are SHA256 (wget_verify still accepts legacy 40-char SHA1). Roundcube
# publishes SHA256 on https://roundcube.net/download/ and as the GitHub release asset digest,
# rcmcarddav as the GitHub asset digest. Check them against the hash in this script's error message.
VERSION=1.7.6
HASH=0168085bf0bfeeb5d4eca3b9730effbe610dbdb380a68567d292fec51f09db36
PERSISTENT_LOGIN_VERSION=bde7b6840c7d91de627ea14e81cf4133cbb3c07a # version 5.3
HTML5_NOTIFIER_VERSION=5d85947e16ea9cac4544c59666fe0ff13ba2a44a # master 2023-06-28 (0.6.4+, newest commit; last tag v0.6.4 is older)
CARDDAV_VERSION=5.1.5
CARDDAV_HASH=aea05586822848d9b2f2cdac6b59bdd500d3f93b1b0eeba0295a4aaeb335ad18
# SHA256 of skins/elastic/images/favicon.ico in Roundcube 1.7.5 and 1.7.6, for installs
# from before setup recorded it in elastic-favicon.sha256 (see below; a new
# VERSION is installed again and gets the record).
ELASTIC_FAVICON_HASH=7b30e499996ec4631848d3509d803d9311f5d71999212f2f4c1ca7af8f24eb69

UPDATE_KEY=$VERSION:$PERSISTENT_LOGIN_VERSION:$HTML5_NOTIFIER_VERSION:$CARDDAV_VERSION

# paths that are often reused.
RCM_DIR=/usr/local/lib/roundcubemail

needs_update=0 #NODOC
if [ ! -f /usr/local/lib/roundcubemail/version ]; then
	# not installed yet #NODOC
	needs_update=1 #NODOC
elif [[ "$UPDATE_KEY" != $(cat /usr/local/lib/roundcubemail/version) ]]; then
	# checks if the version is what we want
	needs_update=1 #NODOC
fi

# The tree that the configuration below goes into: the installed one, or on
# an update a new one, built next to it, which replaces it only when it is
# complete with its plugins and configuration. Up to v78-r2604.1 the installed
# tree was removed first, and a failed download (a plugin) left webmail
# without plugins and configuration until a later run (B157). A directory
# that an earlier run left behind (setup stopped in the middle of an update)
# is removed, only from a /usr/local/lib of root's own (as in zpush.sh).
RCM_BUILD=$RCM_DIR
RCM_TMP=
if [ -n "$(find /usr/local/lib -maxdepth 0 -user root ! -perm /022)" ]; then
	find /usr/local/lib -maxdepth 1 -name '.roundcubemail-new.*' -type d -user root -exec rm -rf -- {} +
fi
if [ $needs_update == 1 ]; then
  # if upgrading from 1.3.x, clear the temp_dir
  if [ -f /usr/local/lib/roundcubemail/version ]; then
    if [ "$(cat /usr/local/lib/roundcubemail/version | cut -c1-3)" == '1.3' ]; then
      find /var/tmp/roundcubemail/ -type f ! -name 'RCMTEMP*' -delete
    fi
  fi

	# install roundcube, in a directory of root's own (mktemp -d: root, 0700)
	# next to the installed tree, on the same file system, so that it goes into
	# place by a rename; not under fixed names in /tmp that another local user
	# could create first (B97)
	if [ -z "$(find /usr/local/lib -maxdepth 0 -user root ! -perm /022)" ]; then
		echo "/usr/local/lib is not a directory of root's own."
		exit 1
	fi
	RCM_TMP=$(mktemp -d /usr/local/lib/.roundcubemail-new.XXXXXXXX)
	wget_verify \
		https://github.com/roundcube/roundcubemail/releases/download/$VERSION/roundcubemail-$VERSION-complete.tar.gz \
		$HASH \
		"$RCM_TMP/roundcube.tgz"
	tar -C "$RCM_TMP" --no-same-owner -zxf "$RCM_TMP/roundcube.tgz"
	rm -f "$RCM_TMP/roundcube.tgz"
	RCM_BUILD=$RCM_TMP/roundcubemail-$VERSION
	if [ -L "$RCM_BUILD" ] || [ ! -d "$RCM_BUILD" ]; then
		echo "The Roundcube $VERSION archive has no directory roundcubemail-$VERSION."
		rm -rf "$RCM_TMP"
		exit 1
	fi
	# The skin's own favicon as released, to tell it from one replaced by hand.
	sha256sum 2> /dev/null < "${RCM_BUILD}/skins/elastic/images/favicon.ico" | cut -d" " -f1 > "${RCM_BUILD}/elastic-favicon.sha256" || true

	# install roundcube persistent_login plugin
	git_clone https://github.com/mfreiholz/Roundcube-Persistent-Login-Plugin.git $PERSISTENT_LOGIN_VERSION '' "${RCM_BUILD}/plugins/persistent_login"

	# install roundcube html5_notifier plugin
	# (github.com/kitist/html5_notifier is a 301 redirect to stremlau/html5_notifier)
	git_clone https://github.com/stremlau/html5_notifier.git $HTML5_NOTIFIER_VERSION '' "${RCM_BUILD}/plugins/html5_notifier"
	# Roundcube 1.7 is served from public_html/, plugin assets are only reachable via static.php/.
	# Use rcmail.assets_path() for the notification icon (same as unmerged upstream PR #59).
	sed -i "s#'./plugins/html5_notifier/images/new_mail.png'#rcmail.assets_path('plugins/html5_notifier/images/new_mail.png')#" \
		"${RCM_BUILD}/plugins/html5_notifier/html5_notifier.js"

	# download and verify the full release of the carddav plugin
	wget_verify \
		https://github.com/mstilkerich/rcmcarddav/releases/download/v${CARDDAV_VERSION}/carddav-v${CARDDAV_VERSION}.tar.gz \
		$CARDDAV_HASH \
		"$RCM_TMP/carddav.tar.gz"

	# unzip and cleanup
	tar -C "${RCM_BUILD}/plugins" -zxf "$RCM_TMP/carddav.tar.gz"
	rm -f "$RCM_TMP/carddav.tar.gz"

	# record the version we've installed
	echo $UPDATE_KEY > "${RCM_BUILD}/version"
fi
RCM_PLUGIN_DIR=${RCM_BUILD}/plugins
RCM_CONFIG=${RCM_BUILD}/config/config.inc.php

# ### Configuring Roundcube

# The secret key of Roundcube's encryption (des_key: the IMAP password in each
# session, the persistent_login cookie) is the one of the installed
# configuration. Setup wrote a new one on every run, which logged out every
# webmail user and ended their "remember me" logins (B172). Read with sed, not
# by running the file (it is root's, in a directory of root's), and taken only
# when it has the characters of a key that setup made (base64), since it goes
# into a PHP string below.
SECRET_KEY=$(sed -nE "/^[\$]config\['des_key'\] = '([A-Za-z0-9+\/]{24,})';.*/{s//\1/p;q}" "$RCM_DIR/config/config.inc.php" 2> /dev/null || true)
if [ -z "$SECRET_KEY" ]; then
	# Generate a secret key of PHP-string-safe characters appropriate
	# for the cipher algorithm selected below.
	SECRET_KEY=$(dd if=/dev/urandom bs=1 count=32 2>/dev/null | base64 | sed s/=//g)
fi

# The fork's favicon (branding/favicon.ico, see branding/README.md) for the
# Elastic skin, through Roundcube's skin_logo option and a file in Roundcube's
# directory (which static.php serves; a Roundcube update replaces the
# directory, setup puts the file back). Not with FAVICON=off in
# /etc/mailinabox.conf, and not when the skin's own favicon.ico was replaced
# (its SHA256 is not the one of the release): Roundcube then shows that one.
# Other skins keep their own favicons.
RCM_FAVICON_CONFIG=
rm -f "${RCM_BUILD}/mailinabox-favicon.ico"
if [ "${FAVICON:-on}" != off ]; then
	rcm_favicon=$(sha256sum 2> /dev/null < "${RCM_BUILD}/skins/elastic/images/favicon.ico" | cut -d" " -f1 || true)
	if [ "$rcm_favicon" = "$(cat "${RCM_BUILD}/elastic-favicon.sha256" 2> /dev/null || echo $ELASTIC_FAVICON_HASH)" ]; then
		install -m 644 branding/favicon.ico "${RCM_BUILD}/mailinabox-favicon.ico"
		RCM_FAVICON_CONFIG="\$config['skin_logo'] = array('elastic:[favicon]' => 'mailinabox-favicon.ico');"
	else
		echo "Roundcube: the favicon of the Elastic skin was replaced by hand, so it is kept."
	fi
fi

# Create a configuration file.
#
# For security, temp and log files are not stored in the default locations
# which are inside the roundcube sources directory. We put them instead
# in normal places.
cat > "$RCM_CONFIG" <<EOF;
<?php
/*
 * Do not edit. Written by Mail-in-a-Box. Regenerated on updates.
 */
\$config = array();
\$config['log_dir'] = '/var/log/roundcubemail/';
\$config['temp_dir'] = '/var/tmp/roundcubemail/';
\$config['db_dsnw'] = 'sqlite:///$STORAGE_ROOT/mail/roundcube/roundcube.sqlite?mode=0640';
\$config['imap_host'] = 'ssl://localhost:993';
\$config['imap_conn_options'] = array(
  'ssl'         => array(
     'verify_peer'  => false,
     'verify_peer_name'  => false,
   ),
 );
\$config['imap_timeout'] = 15;
\$config['smtp_host'] = 'tls://127.0.0.1';
\$config['smtp_conn_options'] = array(
  'ssl'         => array(
     'verify_peer'  => false,
     'verify_peer_name'  => false,
   ),
 );
\$config['support_url'] = 'https://github.com/LM1337/Mail-in-a-box-26';
\$config['product_name'] = '$PRIMARY_HOSTNAME Webmail';
\$config['cipher_method'] = 'AES-256-CBC'; # persistent login cookie and potentially other things
\$config['des_key'] = '$SECRET_KEY'; # 37 characters -> ~256 bits for AES-256, see above
\$config['plugins'] = array('html5_notifier', 'archive', 'zipdownload', 'password', 'managesieve', 'jqueryui', 'persistent_login', 'carddav');
\$config['skin'] = 'elastic';
\$config['login_autocomplete'] = 2;
\$config['login_username_filter'] = 'email';
\$config['password_charset'] = 'UTF-8';
\$config['junk_mbox'] = 'Spam';
/* ensure roudcube session id's aren't leaked to other parts of the server */
\$config['session_path'] = '/mail/';
/* prevent CSRF, requires php 7.3+ */
\$config['session_samesite'] = 'Strict';
\$config['quota_zero_as_unlimited'] = true;
$RCM_FAVICON_CONFIG
?>
EOF

# Configure CardDav
# Since 5.1.5 the plugin does not download photos that a vCard only references
# by URI (the server would fetch any address a contact names); its admin
# setting download_photos turns that on again. It is not set here, so that
# secure default stays.
cat > "${RCM_PLUGIN_DIR}/carddav/config.inc.php" <<EOF;
<?php
/* Do not edit. Written by Mail-in-a-Box. Regenerated on updates. */
\$prefs['_GLOBAL']['hide_preferences'] = true;
/* carddav 5.x preset format: 'url' became 'discovery_url' and 'preemptive_auth' became
   'preemptive_basic_auth'; unknown keys are silently dropped. discovery_url is fixed so
   that accounts migrated from 4.x also get it on their next login. */
\$prefs['ownCloud'] = array(
	 'accountname'  =>  'ownCloud',
	 'name'         =>  '%a (%N)', // account name and server-side addressbook name, as in 4.x
	 'username'     =>  '%u', // login username
	 'password'     =>  '%p', // login password
	 'discovery_url' => 'https://${PRIMARY_HOSTNAME}/cloud/remote.php/dav/addressbooks/users/%u/contacts/',
	 'active'       =>  true,
	 'readonly'     =>  false,
	 'refresh_time' => '02:00:00',
	 'fixed'        =>  array('username','password','discovery_url','preemptive_basic_auth'),
	 'preemptive_basic_auth' => true,
	 'hide'        =>  false,
);
?>
EOF

# Create writable directories.
mkdir -p /var/log/roundcubemail /var/tmp/roundcubemail "$STORAGE_ROOT/mail/roundcube"
chown -R www-data:www-data /var/log/roundcubemail /var/tmp/roundcubemail "$STORAGE_ROOT/mail/roundcube"

# Ensure the log file monitored by fail2ban exists, or else fail2ban can't start.
sudo -u www-data touch /var/log/roundcubemail/errors.log

# Password changing plugin settings
# The config comes empty by default, so we need the settings
# we're not planning to change in config.inc.dist...
cp "${RCM_PLUGIN_DIR}/password/config.inc.php.dist" \
	"${RCM_PLUGIN_DIR}/password/config.inc.php"

# The fork's driver (conf/roundcube-password-mailinabox.php): a password is
# changed through the management daemon, which checks the current password
# and applies the box's password policy and hash (POST /me/password, B210).
# Up to v78-r2604.4 the plugin's sql driver wrote users.sqlite itself as
# www-data ("UPDATE users SET password=%P WHERE email=%u"), so the user
# database and its directory had to be writable by www-data, and any code
# running as www-data could rewrite every account (setup/mail-users.sh).
# Roundcube itself still checks the current password against the session's
# and the length of the new one, with its own messages, before the driver
# runs.
install -m 644 conf/roundcube-password-mailinabox.php "${RCM_PLUGIN_DIR}/password/drivers/mailinabox.php"
tools/editconf.py "${RCM_PLUGIN_DIR}/password/config.inc.php" \
	"\$config['password_driver']='mailinabox';" \
	"\$config['password_confirm_current']=true;" \
	"\$config['password_minimum_length']=8;"

# so PHP can use doveadm, for the password changing plugin
# (upstream, for the plugin's password_algorithm "dovecot", which no version
# of this fork uses; kept for now, see "Planned" in CHANGELOG-fork.md)
usermod -a -G dovecot www-data

# Fix Carddav permissions: root's, read-only for everyone else (directories 755,
# files 644). Upstream (#1029, 2017) gave the plugin to root:www-data with mode
# 774 ("root:www-data need all permissions") without saying why. Neither
# Roundcube nor the plugin writes into its directory (the plugin logs into
# Roundcube's log_dir and keeps its data in Roundcube's database), and PHP
# code that www-data may change is code that a hole in a web app could change
# for good (B147). The owner first: from then on www-data cannot change the
# tree that find walks.
chown -f -R root:root "${RCM_PLUGIN_DIR}/carddav"
find "${RCM_PLUGIN_DIR}/carddav" \( -type d -exec chmod 755 {} + \) -o \( -type f -exec chmod 644 {} + \)

# Patch the Roundcube code to eliminate an issue that causes postfix to reject our sqlite
# user database (see https://github.com/mail-in-a-box/mailinabox/issues/2185)
sed -i.miabold 's/^[^#]\+.\+PRAGMA journal_mode = WAL.\+$/#&/' \
	"${RCM_BUILD}/program/lib/Roundcube/db/sqlite.php"

# A new tree goes into place now (see above). The installed one is renamed
# away first and removed after, so that Roundcube is missing only between
# two renames in the same directory (as Z-Push in zpush.sh).
if [ "$RCM_BUILD" != "$RCM_DIR" ]; then
	rm -rf ${RCM_DIR}.old
	if [ -e $RCM_DIR ]; then
		mv $RCM_DIR ${RCM_DIR}.old
	fi
	mv "$RCM_BUILD" $RCM_DIR
	rm -rf ${RCM_DIR}.old "$RCM_TMP"
	RCM_BUILD=$RCM_DIR
	RCM_PLUGIN_DIR=${RCM_DIR}/plugins
	RCM_CONFIG=${RCM_DIR}/config/config.inc.php
fi

# Run Roundcube database migration script (database is created if it does not exist)
# As www-data, which owns the database and its directory: as root, PHP opened
# (or created) roundcube.sqlite by path, through a symbolic link that www-data
# could have put there (B147). A database of root's from an earlier run is
# given to www-data first.
if [ -e "$STORAGE_ROOT/mail/roundcube/roundcube.sqlite" ]; then
	tools/write_conf.py --own "$STORAGE_ROOT/mail/roundcube/roundcube.sqlite" www-data www-data 664
fi
(cd "$RCM_DIR" && sudo -u www-data php"$PHP_VER" ${RCM_DIR}/bin/updatedb.sh --dir ${RCM_DIR}/SQL --package roundcube)
# www-data owns the directory of roundcube.sqlite, which it may write (B147).
tools/write_conf.py --own "$STORAGE_ROOT/mail/roundcube/roundcube.sqlite" www-data www-data 664

# Because Roundcube wants to set the PRAGMA we just deleted from the source, we apply it here
# to the roundcube database (see https://github.com/roundcube/roundcubemail/issues/8035)
# Database should exist, created by migration script. As www-data (see above).
hide_output sudo -u www-data sqlite3 "$STORAGE_ROOT/mail/roundcube/roundcube.sqlite" 'PRAGMA journal_mode=WAL;'

# Enable PHP modules.
phpenmod -v "$PHP_VER" imap
restart_php_fpm
