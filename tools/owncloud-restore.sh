#!/bin/bash
#
# This script will restore the backup made during an installation
source /etc/mailinabox.conf # load global vars
PHP_VER=8.5 # keep in sync with setup/functions.sh (not in /etc/mailinabox.conf)

if [ -z "$1" ]; then
	echo "Usage: owncloud-restore.sh <backup directory>"
	echo
	echo "WARNING: This will restore the database to the point of the installation!"
	echo "         This means that you will lose all changes made by users after that point"
	echo
	echo
	echo "Backups are stored here: $STORAGE_ROOT/owncloud-backup/"
	echo
	echo "Available backups:"
	echo
	find "$STORAGE_ROOT/owncloud-backup/"* -maxdepth 0 -type d
	echo
	echo "Supply the directory that was created during the last installation as the only commandline argument"
	exit
fi

if [ ! -f "$1/config.php" ] || [ ! -f "$1/owncloud.db" ]; then
	echo "This isn't a valid backup location"
	exit 1
fi

echo "Restoring backup from $1"
service php"$PHP_VER"-fpm stop

# The Nextcloud version the backup was taken from.
BACKUP_NC_VER=$(php"$PHP_VER" -r "include(\"$1/config.php\"); echo(\$CONFIG['version']);")
BACKUP_NC_MAJOR=${BACKUP_NC_VER%%.*}

# remove the current ownCloud/Nextcloud installation
rm -rf /usr/local/lib/owncloud/

cp "$1/owncloud.db" "$STORAGE_ROOT/owncloud/"
cp "$1/config.php" "$STORAGE_ROOT/owncloud/"
chown -f -R www-data:www-data "$STORAGE_ROOT/owncloud"

# Restore the ownCloud/Nextcloud application only if the backup has it and it can run on
# PHP $PHP_VER (Nextcloud 33 and later). Older code, e.g. from before the upgrade chain on a
# box migrated from Ubuntu 22.04, needs PHP 8.2 or earlier. Then leave the application
# directory absent, so that setup installs Nextcloud again and walks the upgrade chain from
# the restored database.
RESTORED_CODE=
if [ -d "$1/owncloud-install" ] && [ "${BACKUP_NC_MAJOR:-0}" -ge 33 ] 2>/dev/null; then
	cp -r "$1/owncloud-install" /usr/local/lib/owncloud

	# restore access rights
	chmod 750 /usr/local/lib/owncloud/{apps,config}

	ln -sf "$STORAGE_ROOT/owncloud/config.php" /usr/local/lib/owncloud/config/config.php
	chown -f -R www-data:www-data /usr/local/lib/owncloud

	sudo -u www-data php"$PHP_VER" /usr/local/lib/owncloud/occ maintenance:mode --off
	RESTORED_CODE=1
fi

# php-fpm also serves Roundcube and Z-Push, so always start it again.
service php"$PHP_VER"-fpm start
if [ -n "$RESTORED_CODE" ]; then
	echo "Done"
else
	echo "Restored only the database and configuration of Nextcloud $BACKUP_NC_VER."
	echo "The backup has no Nextcloud application, or one that cannot run on PHP $PHP_VER."
	echo "Run 'sudo mailinabox' to install Nextcloud again and upgrade the restored database."
fi
