#!/bin/bash
# Nextcloud
##########################

source setup/functions.sh # load our functions
source /etc/mailinabox.conf # load global vars

# ### Installing Nextcloud

echo "Installing Nextcloud (contacts/calendar)..."

# Nextcloud core and app (plugin) versions to install.
# With each version we store a hash to ensure we install what we expect.

# Nextcloud core
# --------------
# * See https://nextcloud.com/changelog for the latest version.
# * Check https://docs.nextcloud.com/server/latest/admin_manual/installation/system_requirements.html
#   for whether it supports the version of PHP available on this machine.
# * Since Nextcloud only supports upgrades from consecutive major versions,
#   we automatically install intermediate versions as needed.
# * The hash is the SHA256 hash of the ZIP package. Nextcloud publishes it next to the download
#   (https://download.nextcloud.com/server/releases/nextcloud-<ver>.zip.sha256; there is no .sha1).
#   Check it against the hash this script prints when it doesn't match what is below.
nextcloud_ver=34.0.5
nextcloud_hash=d077fdca3dc78ef60b5bbc51182f2a1737aa01e2044d6c23f4e7b72146f5239a

# Nextcloud apps
# --------------
# * Find the most recent tag that is compatible with the Nextcloud version above by:
#   https://github.com/nextcloud-releases/contacts/tags
#   https://github.com/nextcloud-releases/calendar/tags
#   https://github.com/nextcloud-releases/user_external/tags
#
# * For these three packages, contact, calendar and user_external, the hash is the SHA256 hash of
# the release tarball (from the releases/download URL, not the source archive). GitHub shows it as
# the asset "digest" on https://github.com/nextcloud-releases/<app>/releases/expanded_assets/v<ver>
# (the unauthenticated API is rate-limited). Cross-check with: curl -sL <url> | sha256sum
# (wget_verify still accepts 40-char SHA1 hashes, but don't add new ones.)

# Always ensure the versions are supported, see https://apps.nextcloud.com/apps/contacts
contacts_ver=8.9.2
contacts_hash=92f7c79c411273045ed6346f6988c05af673c3170a3adaba91a15066b8dce7c5

# Always ensure the versions are supported, see https://apps.nextcloud.com/apps/calendar
calendar_ver=6.6.3
calendar_hash=bda8f38c609b2182533887f67eacb543edf437066d0356912ac6324c94743080

# Always ensure the versions are supported, see https://apps.nextcloud.com/apps/user_external
# user_external 4.0.0 declares nextcloud min-version=31 max-version=34 and there is no release
# for Nextcloud 35 yet (checked 2026-10-22), so Nextcloud 34 is the ceiling for now.
user_external_ver=4.0.0
user_external_hash=f1f98c577bd02177fe74e9199f8e50d0c288ffa94bb50a227101a5ba0633c529

# Developer advice (test plan)
# ----------------------------
# When upgrading above versions, how to test?
#
# 1. Enter your server instance (or on the Vagrant image)
# 1. Git clone <your fork>
# 2. Git checkout <your fork>
# 3. Run `sudo ./setup/nextcloud.sh`
# 4. Ensure the installation completes. If any hashes mismatch, correct them.
# 5. Enter nextcloud web, run following tests:
# 5.1 You still can create, edit and delete contacts
# 5.2 You still can create, edit and delete calendar events
# 5.3 You still can create, edit and delete users
# 5.4 Go to Administration > Logs and ensure no new errors are shown

# Clear prior packages and install dependencies from apt.
apt-get purge -qq -y owncloud* # we used to use the package manager

apt_install curl php"${PHP_VER}" php"${PHP_VER}"-fpm \
	php"${PHP_VER}"-cli php"${PHP_VER}"-sqlite3 php"${PHP_VER}"-gd php"${PHP_VER}"-imap php"${PHP_VER}"-curl \
	php"${PHP_VER}"-dev php"${PHP_VER}"-gd php"${PHP_VER}"-xml php"${PHP_VER}"-mbstring php"${PHP_VER}"-zip php"${PHP_VER}"-apcu \
	php"${PHP_VER}"-intl php"${PHP_VER}"-imagick php"${PHP_VER}"-gmp php"${PHP_VER}"-bcmath

# Enable APC before Nextcloud tools are run.
tools/editconf.py /etc/php/"$PHP_VER"/mods-available/apcu.ini -c ';' \
	apc.enabled=1 \
	apc.enable_cli=1

InstallNextcloud() {

	version=$1
	hash=$2
	version_contacts=$3
	hash_contacts=$4
	version_calendar=$5
	hash_calendar=$6
	version_user_external=${7:-}
	hash_user_external=${8:-}

	echo
	echo "Upgrading to Nextcloud version $version"
	echo

	# Download and verify
	wget_verify "https://download.nextcloud.com/server/releases/nextcloud-$version.zip" "$hash" /tmp/nextcloud.zip

	# Remove the current owncloud/Nextcloud
	rm -rf /usr/local/lib/owncloud

	# Extract ownCloud/Nextcloud
	unzip -q /tmp/nextcloud.zip -d /usr/local/lib
	mv /usr/local/lib/nextcloud /usr/local/lib/owncloud
	rm -f /tmp/nextcloud.zip

	# The two apps we actually want are not in Nextcloud core. Download the releases from
	# their github repositories.
	mkdir -p /usr/local/lib/owncloud/apps

	wget_verify "https://github.com/nextcloud-releases/contacts/releases/download/v$version_contacts/contacts-v$version_contacts.tar.gz" "$hash_contacts" /tmp/contacts.tgz
	tar xf /tmp/contacts.tgz -C /usr/local/lib/owncloud/apps/
	rm /tmp/contacts.tgz

	wget_verify "https://github.com/nextcloud-releases/calendar/releases/download/v$version_calendar/calendar-v$version_calendar.tar.gz" "$hash_calendar" /tmp/calendar.tgz
	tar xf /tmp/calendar.tgz -C /usr/local/lib/owncloud/apps/
	rm /tmp/calendar.tgz

	# Starting with Nextcloud 15, the app user_external is no longer included in Nextcloud core,
	# we will install from their github repository.
	if [ -n "$version_user_external" ]; then
		wget_verify "https://github.com/nextcloud-releases/user_external/releases/download/v$version_user_external/user_external-v$version_user_external.tar.gz" "$hash_user_external" /tmp/user_external.tgz
		tar -xf /tmp/user_external.tgz -C /usr/local/lib/owncloud/apps/
		rm /tmp/user_external.tgz
	fi

	# Fix weird permissions.
	chmod 750 /usr/local/lib/owncloud/{apps,config}

	# Create a symlink to the config.php in STORAGE_ROOT (for upgrades we're restoring the symlink we previously
	# put in, and in new installs we're creating a symlink and will create the actual config later).
	ln -sf "$STORAGE_ROOT/owncloud/config.php" /usr/local/lib/owncloud/config/config.php

	# Make sure permissions are correct or the upgrade step won't run.
	# $STORAGE_ROOT/owncloud may not yet exist, so use -f to suppress
	# that error.
	chown -f -R www-data:www-data "$STORAGE_ROOT/owncloud" /usr/local/lib/owncloud || /bin/true

	# If this isn't a new installation, immediately run the upgrade script.
	# Then check for success (0=ok and 3=no upgrade needed, both are success).
	if [ -e "$STORAGE_ROOT/owncloud/owncloud.db" ]; then
		# ownCloud 8.1.1 broke upgrades. It may fail on the first attempt, but
		# that can be OK.
		if [[ ${CURRENT_NEXTCLOUD_VER} =~ ^2[6789] || ${CURRENT_NEXTCLOUD_VER} =~ ^3[01] ]]; then
            #
            # CURRENT_NEXTCLOUD_VER is still the version *before* this step, while occ runs the code
            # of the version just unpacked. CURRENT 26..31 means we are installing 27..32, which need
            # PHP 8.2 (lib/versioncheck.php: NC 27 < 8.3, NC 30 < 8.4, NC 31 and 32 < 8.5).
            # CURRENT 32 and later means installing 33/34, which accept 8.2 to 8.5, so they use PHP 8.5.
            # Older versions never get here (see the "not supported" branches below).
            #
            echo "Installing Legacy PHP version for Nextcloud upgrade..."

            apt_install php"${PHP_LEGACY_VER}"-cli php"${PHP_LEGACY_VER}"-sqlite3 \
	            php"${PHP_LEGACY_VER}"-gd php"${PHP_LEGACY_VER}"-imap php"${PHP_LEGACY_VER}"-curl php"${PHP_LEGACY_VER}"-dev php"${PHP_LEGACY_VER}"-gd \
	            php"${PHP_LEGACY_VER}"-xml php"${PHP_LEGACY_VER}"-mbstring php"${PHP_LEGACY_VER}"-zip php"${PHP_LEGACY_VER}"-apcu \
	            php"${PHP_LEGACY_VER}"-intl php"${PHP_LEGACY_VER}"-imagick php"${PHP_LEGACY_VER}"-gmp php"${PHP_LEGACY_VER}"-bcmath

            tools/editconf.py /etc/php/"$PHP_LEGACY_VER"/mods-available/apcu.ini -c ';' \
	            apc.enabled=1 \
	            apc.enable_cli=1

            sudo -u www-data php"$PHP_LEGACY_VER" /usr/local/lib/owncloud/occ upgrade
    		E=$?
    		if [ $E -ne 0 ] && [ $E -ne 3 ]; then
    			echo "Trying ownCloud upgrade again to work around ownCloud upgrade bug..."
    			sudo -u www-data php"$PHP_LEGACY_VER" /usr/local/lib/owncloud/occ upgrade
    			E=$?
    			if [ $E -ne 0 ] && [ $E -ne 3 ]; then exit 1; fi
    			sudo -u www-data php"$PHP_LEGACY_VER" /usr/local/lib/owncloud/occ maintenance:mode --off
    			echo "...which seemed to work."
    		fi

    		# Add missing indices. NextCloud didn't include this in the normal upgrade because it might take some time.
    		sudo -u www-data php"$PHP_LEGACY_VER" /usr/local/lib/owncloud/occ db:add-missing-indices
    		sudo -u www-data php"$PHP_LEGACY_VER" /usr/local/lib/owncloud/occ db:add-missing-primary-keys

    		# Run conversion to BigInt identifiers, this process may take some time on large tables.
    		sudo -u www-data php"$PHP_LEGACY_VER" /usr/local/lib/owncloud/occ db:convert-filecache-bigint --no-interaction

        else
            #
            # Upgrade using 8.5
            #
            sudo -u www-data php"$PHP_VER" /usr/local/lib/owncloud/occ upgrade
    		E=$?
    		if [ $E -ne 0 ] && [ $E -ne 3 ]; then
    			echo "Trying ownCloud upgrade again to work around ownCloud upgrade bug..."
    			sudo -u www-data php"$PHP_VER" /usr/local/lib/owncloud/occ upgrade
    			E=$?
    			if [ $E -ne 0 ] && [ $E -ne 3 ]; then exit 1; fi
    			sudo -u www-data php"$PHP_VER" /usr/local/lib/owncloud/occ maintenance:mode --off
    			echo "...which seemed to work."
    		fi

    		# Add missing indices. NextCloud didn't include this in the normal upgrade because it might take some time.
    		sudo -u www-data php"$PHP_VER" /usr/local/lib/owncloud/occ db:add-missing-indices
    		sudo -u www-data php"$PHP_VER" /usr/local/lib/owncloud/occ db:add-missing-primary-keys

    		# Run conversion to BigInt identifiers, this process may take some time on large tables.
    		sudo -u www-data php"$PHP_VER" /usr/local/lib/owncloud/occ db:convert-filecache-bigint --no-interaction
        fi
	fi
}

# Current Nextcloud Version, #1623
# Checking /usr/local/lib/owncloud/version.php shows version of the Nextcloud application, not the DB
# $STORAGE_ROOT/owncloud is kept together even during a backup. It is better to rely on config.php than
# version.php since the restore procedure can leave the system in a state where you have a newer Nextcloud
# application version than the database.

# If config.php exists, get version number, otherwise CURRENT_NEXTCLOUD_VER is empty.
if [ -f "$STORAGE_ROOT/owncloud/config.php" ]; then
	CURRENT_NEXTCLOUD_VER=$(php"$PHP_VER" -r "include(\"$STORAGE_ROOT/owncloud/config.php\"); echo(\$CONFIG['version']);")
else
	CURRENT_NEXTCLOUD_VER=""
fi

# If the Nextcloud directory is missing (never been installed before, or the nextcloud version to be installed is different
# from the version currently installed, do the install/upgrade
if [ ! -d /usr/local/lib/owncloud/ ] || [[ ! ${CURRENT_NEXTCLOUD_VER} =~ ^$nextcloud_ver ]]; then

	# Stop php-fpm if running. If they are not running (which happens on a previously failed install), dont bail.
	service php"$PHP_VER"-fpm stop &> /dev/null || /bin/true

	# Backup the existing ownCloud/Nextcloud.
	# Create a backup directory to store the current installation and database to
	BACKUP_DIRECTORY=$STORAGE_ROOT/owncloud-backup/$(date +"%Y-%m-%d-%T")
	mkdir -p "$BACKUP_DIRECTORY"
	if [ -d /usr/local/lib/owncloud/ ]; then
		echo "Upgrading Nextcloud --- backing up existing installation, configuration, and database to directory to $BACKUP_DIRECTORY..."
		cp -r /usr/local/lib/owncloud "$BACKUP_DIRECTORY/owncloud-install"
	fi
	if [ -e "$STORAGE_ROOT/owncloud/owncloud.db" ]; then
		cp "$STORAGE_ROOT/owncloud/owncloud.db" "$BACKUP_DIRECTORY"
	fi
	if [ -e "$STORAGE_ROOT/owncloud/config.php" ]; then
		cp "$STORAGE_ROOT/owncloud/config.php" "$BACKUP_DIRECTORY"
	fi

	# If ownCloud or Nextcloud was previously installed....
	if [ -n "${CURRENT_NEXTCLOUD_VER}" ]; then
		# Database migrations from ownCloud are no longer possible because ownCloud cannot be run under
		# PHP 7.

		if [ -e "$STORAGE_ROOT/owncloud/config.php" ]; then
			# Remove the read-onlyness of the config, which is needed for migrations, especially for v24
			sed -i -e '/config_is_read_only/d' "$STORAGE_ROOT/owncloud/config.php"
		fi

		if [[ ${CURRENT_NEXTCLOUD_VER} =~ ^[89] ]]; then
			echo "Upgrades from Mail-in-a-Box prior to v0.28 (dated July 30, 2018) with Nextcloud < 13.0.6 (you have ownCloud 8 or 9) are not supported. Upgrade to Mail-in-a-Box version v0.30 first. Setup will continue, but skip the Nextcloud migration."
			return 0
		elif [[ ${CURRENT_NEXTCLOUD_VER} =~ ^1[012] ]]; then
			echo "Upgrades from Mail-in-a-Box prior to v0.28 (dated July 30, 2018) with Nextcloud < 13.0.6 (you have ownCloud 10, 11 or 12) are not supported. Upgrade to Mail-in-a-Box version v0.30 first. Setup will continue, but skip the Nextcloud migration."
			return 0
		elif [[ ${CURRENT_NEXTCLOUD_VER} =~ ^1[3456789] ]]; then
			echo "Upgrades from Mail-in-a-Box prior to v60 with Nextcloud 19 or earlier are not supported. Upgrade to the latest Mail-in-a-Box version supported on your machine first. Setup will continue, but skip the Nextcloud migration."
			return 0
		elif [[ ${CURRENT_NEXTCLOUD_VER} =~ ^2[012345] ]]; then
			# The upgrade chain starts at Nextcloud 26. Nextcloud 20-23 need PHP <= 8.0 and 24/25 need
			# PHP <= 8.1 (lib/versioncheck.php); this release only provides PHP 8.5 and, for the chain, 8.2.
			echo "Upgrades from Nextcloud 25 or earlier are not supported on this version of Mail-in-a-Box. Upgrade to Mail-in-a-Box v68 or later on Ubuntu 22.04 first (Nextcloud 26). Setup will continue, but skip the Nextcloud migration."
			return 0
		fi

		# Hint: whenever you bump, remember this:
		# - Run a server with the previous version
		# - On a new if-else block, copy the versions/hashes from the previous version
		# - Run sudo ./setup/start.sh on the new machine. Upon completion, test its basic functionalities.
		# Each step uses the newest patch release of its major and the newest app releases whose
		# appinfo/info.xml accepts that major (and the PHP version the step runs with). All hashes are SHA256.

		if [[ ${CURRENT_NEXTCLOUD_VER} =~ ^26 ]]; then
			# runs with PHP 8.2 (NC 27: PHP 8.0-8.2)
			InstallNextcloud 27.1.11 ffbfd9857bcaaacaea97d709063b7d81132feb41051063ab6c171c95c6daf142 5.5.4 178aa6ec0b06d6bd72ff8eb87ac32ff267e97ccd93246b1eae1b5bb5263a61b0 4.7.20 f62b43853dfc1fc971b4ffe5992cedc499e8ed7dc118265cfdfe8c1531d4a912 3.4.0 5a7fbed5da3cbe335f753027b662179c92c17fb37babc875e9e285d8a13d47f3
			CURRENT_NEXTCLOUD_VER="27.1.11"
		fi
		if [[ ${CURRENT_NEXTCLOUD_VER} =~ ^27 ]]; then
			# runs with PHP 8.2
			InstallNextcloud 28.0.14 593f174f5098c793fb0314fd5847d891ed4e4db908ceba0d4e571544ac855c2d 5.5.4 178aa6ec0b06d6bd72ff8eb87ac32ff267e97ccd93246b1eae1b5bb5263a61b0 4.7.20 f62b43853dfc1fc971b4ffe5992cedc499e8ed7dc118265cfdfe8c1531d4a912 3.4.0 5a7fbed5da3cbe335f753027b662179c92c17fb37babc875e9e285d8a13d47f3
			CURRENT_NEXTCLOUD_VER="28.0.14"
		fi
		if [[ ${CURRENT_NEXTCLOUD_VER} =~ ^28 ]]; then
			# runs with PHP 8.2
			InstallNextcloud 29.0.16 6221c764b63369be6122bc414ee26a25bd9ce466f7d9ab29cd5ddb0c124c8eeb 6.0.7 29b4942b9b224dcb7e7528fafb6a6094e45593e893dff61e519c34b19bed29a6 4.7.20 f62b43853dfc1fc971b4ffe5992cedc499e8ed7dc118265cfdfe8c1531d4a912 3.4.0 5a7fbed5da3cbe335f753027b662179c92c17fb37babc875e9e285d8a13d47f3
			CURRENT_NEXTCLOUD_VER="29.0.16"
		fi
		if [[ ${CURRENT_NEXTCLOUD_VER} =~ ^29 ]]; then
			# runs with PHP 8.2 (NC 30: PHP 8.1-8.3)
			# No user_external release covers Nextcloud 30 (3.4.0 has max-version 29, 4.0.0 has
			# min-version 31), so occ upgrade disables it on this step; the 31 step installs 4.0.0
			# and the app:enable user_external further below turns it back on.
			InstallNextcloud 30.0.17 da51e17762785a36c1cf3fe2dc96cb356870695e384485e5980395493c15caf9 7.3.19 568472420cf212ceeb1dccc044c0bdaa83504ef15251a2c6e39b22b6064a3ab8 5.5.24 9a4e1b869aa478317363cb0876a5d128aa584e427216d2cbfb808215f5c296a8 3.4.0 5a7fbed5da3cbe335f753027b662179c92c17fb37babc875e9e285d8a13d47f3
			CURRENT_NEXTCLOUD_VER="30.0.17"
		fi
		if [[ ${CURRENT_NEXTCLOUD_VER} =~ ^30 ]]; then
			# runs with PHP 8.2
			InstallNextcloud 31.0.14 6f34d623f7c24c5ecb3c165083ddb5d6a10186dbc2fa73a23efda26ec92091a7 7.3.19 568472420cf212ceeb1dccc044c0bdaa83504ef15251a2c6e39b22b6064a3ab8 5.5.24 9a4e1b869aa478317363cb0876a5d128aa584e427216d2cbfb808215f5c296a8 4.0.0 f1f98c577bd02177fe74e9199f8e50d0c288ffa94bb50a227101a5ba0633c529
			CURRENT_NEXTCLOUD_VER="31.0.14"
		fi
		if [[ ${CURRENT_NEXTCLOUD_VER} =~ ^31 ]]; then
			# runs with PHP 8.2 (NC 32: PHP 8.1-8.4)
			InstallNextcloud 32.0.15 33e7adbe81c1ad0be61123a0fadc63ae2e392759f0c2557e008863eb69c6453d 8.3.21 45d12ff526515ce5efc52d8e0d42bd3446a66b9a423ee4eb92ebd44a6b5974c3 6.6.3 bda8f38c609b2182533887f67eacb543edf437066d0356912ac6324c94743080 4.0.0 f1f98c577bd02177fe74e9199f8e50d0c288ffa94bb50a227101a5ba0633c529
			CURRENT_NEXTCLOUD_VER="32.0.15"
		fi
		if [[ ${CURRENT_NEXTCLOUD_VER} =~ ^32 ]]; then
			# runs with PHP 8.5 (NC 33: PHP 8.2-8.5)
			InstallNextcloud 33.0.10 ff602a1f1ba202f2137f10eecd201d3e80c5d94fd17ab984c688fb1bcb290645 8.9.2 92f7c79c411273045ed6346f6988c05af673c3170a3adaba91a15066b8dce7c5 6.6.3 bda8f38c609b2182533887f67eacb543edf437066d0356912ac6324c94743080 4.0.0 f1f98c577bd02177fe74e9199f8e50d0c288ffa94bb50a227101a5ba0633c529
			CURRENT_NEXTCLOUD_VER="33.0.10"
		fi
		##
		# Placeholder for the move to Nextcloud 35. Not active: user_external (IMAP login) has no
		# release for Nextcloud 35 yet (4.0.0 has max-version 34, checked 2026-10-22). Today the
		# 33 -> 34 step is the final InstallNextcloud call below. Once user_external supports 35,
		# enable this explicit 33 -> 34 step (same values as nextcloud_ver/contacts/calendar today)
		# and move nextcloud_ver and the app pins at the top of this file to 35.
		# if [[ ${CURRENT_NEXTCLOUD_VER} =~ ^33 ]]; then
		#	# runs with PHP 8.5
		#	InstallNextcloud 34.0.5 d077fdca3dc78ef60b5bbc51182f2a1737aa01e2044d6c23f4e7b72146f5239a 8.9.2 92f7c79c411273045ed6346f6988c05af673c3170a3adaba91a15066b8dce7c5 6.6.3 bda8f38c609b2182533887f67eacb543edf437066d0356912ac6324c94743080 4.0.0 f1f98c577bd02177fe74e9199f8e50d0c288ffa94bb50a227101a5ba0633c529
		#	CURRENT_NEXTCLOUD_VER="34.0.5"
		# fi
		##
	fi

	InstallNextcloud $nextcloud_ver $nextcloud_hash $contacts_ver $contacts_hash $calendar_ver $calendar_hash $user_external_ver $user_external_hash
fi

# ### Configuring Nextcloud

# Setup Nextcloud if the Nextcloud database does not yet exist. Running setup when
# the database does exist wipes the database and user data.
if [ ! -f "$STORAGE_ROOT/owncloud/owncloud.db" ]; then
	# Create user data directory
	mkdir -p "$STORAGE_ROOT/owncloud"

	# Create an initial configuration file.
	instanceid=oc$(echo "$PRIMARY_HOSTNAME" | sha1sum | fold -w 10 | head -n 1)
	cat > "$STORAGE_ROOT/owncloud/config.php" <<EOF;
<?php
\$CONFIG = array (
  'datadirectory' => '$STORAGE_ROOT/owncloud',

  'instanceid' => '$instanceid',

  'forcessl' => true, # if unset/false, Nextcloud sends a HSTS=0 header, which conflicts with nginx config

  'overwritewebroot' => '/cloud',
  'overwrite.cli.url' => '/cloud',
  'user_backends' => array(
    array(
      'class' => '\OCA\UserExternal\IMAP',
      'arguments' => array(
        '127.0.0.1', 143, null, null, false, false
       ),
    ),
  ),
  'memcache.local' => '\OC\Memcache\APCu',
);
?>
EOF

	# Create an auto-configuration file to fill in database settings
	# when the install script is run. Make an administrator account
	# here or else the install can't finish.
	adminpassword=$(dd if=/dev/urandom bs=1 count=40 2>/dev/null | sha1sum | fold -w 30 | head -n 1)
	cat > /usr/local/lib/owncloud/config/autoconfig.php <<EOF;
<?php
\$AUTOCONFIG = array (
  # storage/database
  'directory' => '$STORAGE_ROOT/owncloud',
  'dbtype' => 'sqlite3',

  # create an administrator account with a random password so that
  # the user does not have to enter anything on first load of Nextcloud
  'adminlogin'    => 'root',
  'adminpass'     => '$adminpassword',
);
?>
EOF

	# Set permissions
	chown -R www-data:www-data "$STORAGE_ROOT/owncloud" /usr/local/lib/owncloud

	# Execute Nextcloud's setup step, which creates the Nextcloud sqlite database.
	# It also wipes it if it exists. And it updates config.php with database
	# settings and deletes the autoconfig.php file.
	(cd /usr/local/lib/owncloud || exit; sudo -u www-data php"$PHP_VER" /usr/local/lib/owncloud/index.php;)
fi

# Update config.php.
# * trusted_domains is reset to localhost by autoconfig starting with ownCloud 8.1.1,
#   so set it here. It also can change if the box's PRIMARY_HOSTNAME changes, so
#   this will make sure it has the right value.
# * Some settings weren't included in previous versions of Mail-in-a-Box.
# * We need to set the timezone to the system timezone to allow fail2ban to ban
#   users within the proper timeframe
# * We need to set the logdateformat to something that will work correctly with fail2ban
# * mail_domain' needs to be set every time we run the setup. Making sure we are setting
#   the correct domain name if the domain is being change from the previous setup.
# Use PHP to read the settings file, modify it, and write out the new settings array.
TIMEZONE=$(timedatectl show -p Timezone --value)
CONFIG_TEMP=$(/bin/mktemp)
php"$PHP_VER" <<EOF > "$CONFIG_TEMP" && mv "$CONFIG_TEMP" "$STORAGE_ROOT/owncloud/config.php";
<?php
include("$STORAGE_ROOT/owncloud/config.php");

\$CONFIG['config_is_read_only'] = false;
\$CONFIG['appstoreenabled'] = false; # https://discourse.mailinabox.email/t/problems-with-z-push-and-nextcloud-likely-after-package-updates-today/16460/21

\$CONFIG['trusted_domains'] = array('$PRIMARY_HOSTNAME');

\$CONFIG['memcache.local'] = '\OC\Memcache\APCu';
\$CONFIG['overwrite.cli.url'] = 'https://${PRIMARY_HOSTNAME}/cloud';

\$CONFIG['logtimezone'] = '$TIMEZONE';
\$CONFIG['logdateformat'] = 'Y-m-d H:i:s';

\$CONFIG['user_backends'] = array(
  array(
    'class' => '\OCA\UserExternal\IMAP',
    'arguments' => array(
      '127.0.0.1', 143, null, null, false, false
    ),
  ),
);

\$CONFIG['mail_domain'] = '$PRIMARY_HOSTNAME';
\$CONFIG['mail_from_address'] = 'administrator'; # just the local part, matches the required administrator alias on mail_domain/$PRIMARY_HOSTNAME
\$CONFIG['mail_smtpmode'] = 'sendmail';
\$CONFIG['mail_smtpauth'] = true; # if smtpmode is smtp
\$CONFIG['mail_smtphost'] = '127.0.0.1'; # if smtpmode is smtp
\$CONFIG['mail_smtpport'] = '587'; # if smtpmode is smtp
\$CONFIG['mail_smtpsecure'] = ''; # if smtpmode is smtp, must be empty string
\$CONFIG['mail_smtpname'] = ''; # if smtpmode is smtp, set this to a mail user
\$CONFIG['mail_smtppassword'] = ''; # if smtpmode is smtp, set this to the user's password

echo "<?php\n\\\$CONFIG = ";
var_export(\$CONFIG);
echo ";";
?>
EOF
chown www-data:www-data "$STORAGE_ROOT/owncloud/config.php"

# Enable/disable apps. Note that this must be done after the Nextcloud setup.
# The firstrunwizard gave Josh all sorts of problems, so disabling that.
# user_external is what allows Nextcloud to use IMAP for login. The contacts
# and calendar apps are the extensions we really care about here.
hide_output sudo -u www-data php"$PHP_VER" /usr/local/lib/owncloud/console.php app:disable firstrunwizard
hide_output sudo -u www-data php"$PHP_VER" /usr/local/lib/owncloud/console.php app:enable user_external
hide_output sudo -u www-data php"$PHP_VER" /usr/local/lib/owncloud/console.php app:enable contacts
hide_output sudo -u www-data php"$PHP_VER" /usr/local/lib/owncloud/console.php app:enable calendar

# When upgrading, run the upgrade script again now that apps are enabled. It seems like
# the first upgrade at the top won't work because apps may be disabled during upgrade?
# Check for success (0=ok, 3=no upgrade needed).
sudo -u www-data php"$PHP_VER" /usr/local/lib/owncloud/occ upgrade
E=$?
if [ $E -ne 0 ] && [ $E -ne 3 ]; then exit 1; fi

# Disable default apps that we don't support
sudo -u www-data \
	php"$PHP_VER" /usr/local/lib/owncloud/occ app:disable photos dashboard activity \
	| (grep -v "No such app enabled" || /bin/true)

# Set PHP FPM values to support large file uploads
# (semicolon is the comment character in this file, hashes produce deprecation warnings)
tools/editconf.py /etc/php/"$PHP_VER"/fpm/php.ini -c ';' \
	upload_max_filesize=16G \
	post_max_size=16G \
	output_buffering=16384 \
	memory_limit=512M \
	max_execution_time=600 \
	short_open_tag=On

# Set Nextcloud recommended opcache settings
tools/editconf.py /etc/php/"$PHP_VER"/cli/php.ini -c ';' \
	opcache.enable=1 \
	opcache.enable_cli=1 \
	opcache.interned_strings_buffer=8 \
	opcache.max_accelerated_files=10000 \
	opcache.memory_consumption=128 \
	opcache.save_comments=1 \
	opcache.revalidate_freq=1

# Migrate users_external data from <0.6.0 to version 3.0.0
# (see https://github.com/nextcloud/user_external).
# This version was probably in use in Mail-in-a-Box v0.41 (February 26, 2019) and earlier.
# We moved to v0.6.3 in 193763f8. Ignore errors - maybe there are duplicated users with the
# correct backend already.
sqlite3 "$STORAGE_ROOT/owncloud/owncloud.db" "UPDATE oc_users_external SET backend='127.0.0.1';" || /bin/true

# Set up a general cron job for Nextcloud.
# Also add another job for Calendar updates, per advice in the Nextcloud docs
# https://docs.nextcloud.com/server/24/admin_manual/groupware/calendar.html#background-jobs
cat > /etc/cron.d/mailinabox-nextcloud << EOF;
#!/bin/bash
# Mail-in-a-Box
*/5 * * * *	www-data	php$PHP_VER -f /usr/local/lib/owncloud/cron.php
*/5 * * * *	www-data	php$PHP_VER -f /usr/local/lib/owncloud/occ dav:send-event-reminders
EOF
chmod +x /etc/cron.d/mailinabox-nextcloud

# We also need to change the sending mode from background-job to occ.
# Or else the reminders will just be sent as soon as possible when the background jobs run.
hide_output sudo -u www-data php"$PHP_VER" -f /usr/local/lib/owncloud/occ config:app:set dav sendEventRemindersMode --value occ

# Now set the config to read-only.
# Do this only at the very bottom when no further occ commands are needed.
sed -i'' "s/'config_is_read_only'\s*=>\s*false/'config_is_read_only' => true/" "$STORAGE_ROOT/owncloud/config.php"

# Rotate the nextcloud.log file
cat > /etc/logrotate.d/nextcloud <<EOF
# Nextcloud logs
$STORAGE_ROOT/owncloud/nextcloud.log {
		size 10M
		create 640 www-data www-data
		rotate 30
		copytruncate
		missingok
		compress
}
EOF

# There's nothing much of interest that a user could do as an admin for Nextcloud,
# and there's a lot they could mess up, so we don't make any users admins of Nextcloud.
# But if we wanted to, we would do this:
# ```
# for user in $(management/cli.py user admins); do
#	 sqlite3 $STORAGE_ROOT/owncloud/owncloud.db "INSERT OR IGNORE INTO oc_group_user VALUES ('admin', '$user')"
# done
# ```

# Cleanup Legacy PHP Version
echo "Cleaning up legacy php version"
hide_output apt-get purge -y "php${PHP_LEGACY_VER}*"
rm -rf /etc/php/"$PHP_LEGACY_VER"

# Enable PHP modules and restart PHP.
restart_service php"$PHP_VER"-fpm
