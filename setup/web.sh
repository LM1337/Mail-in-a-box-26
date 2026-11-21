#!/bin/bash
# HTTP: Turn on a web server serving static files
#################################################

source setup/functions.sh # load our functions
source /etc/mailinabox.conf # load global vars

# Some Ubuntu images start off with Apache. Remove it since we
# will use nginx. Use autoremove to remove any Apache dependencies.
if [ -f /usr/sbin/apache2 ]; then
	echo "Removing apache..."
	apt_get_quiet purge 'apache2' 'apache2-*'
	apt_get_quiet --purge autoremove
fi

# Install nginx and a PHP FastCGI daemon.
#
# Turn off nginx's default website.

echo "Installing Nginx (web server)..."

apt_install nginx php"${PHP_VER}"-cli php"${PHP_VER}"-fpm idn2

rm -f /etc/nginx/sites-enabled/default

# Copy in a nginx configuration file for common and best-practices
# SSL settings from @konklone. Replace STORAGE_ROOT so it can find
# the DH params.
rm -f /etc/nginx/nginx-ssl.conf # we used to put it here
sed "s#STORAGE_ROOT#$STORAGE_ROOT#" \
	conf/nginx-ssl.conf > /etc/nginx/conf.d/ssl.conf

# Fix some nginx defaults.
#
# The server_names_hash_bucket_size seems to prevent long domain names!
# The default, according to nginx's docs, depends on "the size of the
# processor’s cache line." It could be as low as 32. We fixed it at
# 64 in 2014 to accommodate a long domain name (20 characters?). But
# even at 64, a 58-character domain name won't work (#93), so now
# we're going up to 128.
#
# Drop TLSv1.0, TLSv1.1, following the Mozilla "Intermediate" recommendations
# at https://ssl-config.mozilla.org/#server=nginx&server-version=1.17.0&config=intermediate&openssl-version=1.1.1.
tools/editconf.py /etc/nginx/nginx.conf -s \
	server_names_hash_bucket_size="128;" \
	ssl_protocols="TLSv1.2 TLSv1.3;"

# Tell PHP not to expose its version number in the X-Powered-By header.
tools/editconf.py /etc/php/"$PHP_VER"/fpm/php.ini -c ';' \
	expose_php=Off

# Set PHPs default charset to UTF-8, since we use it. See #367.
tools/editconf.py /etc/php/"$PHP_VER"/fpm/php.ini -c ';' \
        default_charset="UTF-8"

# Configure the path environment for php-fpm
tools/editconf.py /etc/php/"$PHP_VER"/fpm/pool.d/www.conf -c ';' \
	env[PATH]=/usr/local/bin:/usr/bin:/bin \

# A reload of PHP-FPM (load_php_fpm in setup/functions.sh) lets the running
# requests finish for up to 5 seconds before it ends them; with the
# package's 0 it ends them at once, as a restart does (B122). New requests
# wait meanwhile, so the time is short. (The line goes in the [global]
# section, after the package's commented ";process_control_timeout = 0".)
tools/editconf.py /etc/php/"$PHP_VER"/fpm/php-fpm.conf -c ';' \
	process_control_timeout=5s

# Configure php-fpm based on the amount of memory the machine has
# This is based on the nextcloud manual for performance tuning: https://docs.nextcloud.com/server/17/admin_manual/installation/server_tuning.html
# Some synchronisation issues can occur when many people access the site at once.
# The pm=ondemand setting is used for memory constrained machines < 2GB, this is copied over from PR: 1216
TOTAL_PHYSICAL_MEM=$(head -n 1 /proc/meminfo | awk '{print $2}' || /bin/true)
if [ "$TOTAL_PHYSICAL_MEM" -lt 1000000 ]
then
        tools/editconf.py /etc/php/"$PHP_VER"/fpm/pool.d/www.conf -c ';' \
                pm=ondemand \
                pm.max_children=8 \
                pm.start_servers=2 \
                pm.min_spare_servers=1 \
                pm.max_spare_servers=3
elif [ "$TOTAL_PHYSICAL_MEM" -lt 2000000 ]
then
        tools/editconf.py /etc/php/"$PHP_VER"/fpm/pool.d/www.conf -c ';' \
                pm=ondemand \
                pm.max_children=16 \
                pm.start_servers=4 \
                pm.min_spare_servers=1 \
                pm.max_spare_servers=6
elif [ "$TOTAL_PHYSICAL_MEM" -lt 3000000 ]
then
        tools/editconf.py /etc/php/"$PHP_VER"/fpm/pool.d/www.conf -c ';' \
                pm=dynamic \
                pm.max_children=60 \
                pm.start_servers=6 \
                pm.min_spare_servers=3 \
                pm.max_spare_servers=9
else
        tools/editconf.py /etc/php/"$PHP_VER"/fpm/pool.d/www.conf -c ';' \
                pm=dynamic \
                pm.max_children=120 \
                pm.start_servers=12 \
                pm.min_spare_servers=6 \
                pm.max_spare_servers=18
fi

# The proof of nginx's own /caldav, /carddav and /webdav proxy to Nextcloud
# (B213). The proxy connects to /cloud from 127.0.0.1 and passes the client's
# address in X-Forwarded-For, which Nextcloud takes from 127.0.0.1
# (trusted_proxies, setup/nextcloud.sh, B121). Any other process on the box
# could send that header too, from 127.0.0.1, and make Nextcloud log a failed
# login under another address, which the miab-owncloud jail then bans. So the
# proxy also sends a secret header, and nginx gives X-Forwarded-For to
# Nextcloud's PHP only with that secret (conf/nginx-primaryonly.conf includes
# this file in the box's server block); PHP never sees the secret itself.
# Only root may read the file (nginx reads its configuration as root); the
# secret is made once and kept on later runs, so that the configuration does
# not change. It is compared with "if (... = ...)" in the server block, a
# plain comparison of strings: a map would need a regular expression for a
# key this long (map_hash_bucket_size), and a map's regular expression run
# while the FastCGI parameters are built replaces the captures of the PHP
# location ($1, $2, $3), which then gave "fastcgi request length mismatch"
# and HTTP 500 (both found in the lab).
nc_proxy_conf=/etc/nginx/miab-nextcloud-proxy.conf
# shellcheck disable=SC2016 # the $ is nginx's, in the line that sed reads
nc_proxy_secret=$(sed -n 's/^set \$miab_nc_proxy_secret "\([0-9a-f]\{64\}\)";$/\1/p' "$nc_proxy_conf" 2> /dev/null | head -n 1 || true)
if [ -z "$nc_proxy_secret" ]; then
	nc_proxy_secret=$(openssl rand -hex 32)
fi
tools/write_conf.py "$nc_proxy_conf" 600 << EOF;
# Written by Mail-in-a-Box setup (setup/web.sh, B213). Do not edit.
# Included in the server block of the box's own name: the secret header of the
# proxy of /caldav, /carddav and /webdav, and the X-Forwarded-For that
# Nextcloud gets, only from that proxy.
set \$miab_nc_proxy_secret "$nc_proxy_secret";
set \$miab_nc_forwarded_for "";
if (\$http_x_miab_nextcloud_proxy = "$nc_proxy_secret") {
	set \$miab_nc_forwarded_for \$http_x_forwarded_for;
}
EOF
tools/write_conf.py --own "$nc_proxy_conf" root root 600

# Other nginx settings will be configured by the management service
# since it depends on what domains we're serving, which we don't know
# until mail accounts have been created.

# Create the iOS/OS X Mobile Configuration file which is exposed via the
# nginx configuration at /mailinabox-mobileconfig.
mkdir -p /var/lib/mailinabox
chmod a+rx /var/lib/mailinabox
cat conf/ios-profile.xml \
	| sed "s/PRIMARY_HOSTNAME/$PRIMARY_HOSTNAME/" \
	| sed "s/UUID1/$(cat /proc/sys/kernel/random/uuid)/" \
	| sed "s/UUID2/$(cat /proc/sys/kernel/random/uuid)/" \
	| sed "s/UUID3/$(cat /proc/sys/kernel/random/uuid)/" \
	| sed "s/UUID4/$(cat /proc/sys/kernel/random/uuid)/" \
	 > /var/lib/mailinabox/mobileconfig.xml
chmod a+r /var/lib/mailinabox/mobileconfig.xml

# Create the Mozilla Auto-configuration file which is exposed via the
# nginx configuration at /.well-known/autoconfig/mail/config-v1.1.xml.
# The format of the file is documented at:
# https://wiki.mozilla.org/Thunderbird:Autoconfiguration:ConfigFileFormat
# and https://developer.mozilla.org/en-US/docs/Mozilla/Thunderbird/Autoconfiguration/FileFormat/HowTo.
cat conf/mozilla-autoconfig.xml \
	| sed "s/PRIMARY_HOSTNAME/$PRIMARY_HOSTNAME/" \
	 > /var/lib/mailinabox/mozilla-autoconfig.xml
chmod a+r /var/lib/mailinabox/mozilla-autoconfig.xml

# Create a generic mta-sts.txt file which is exposed via the
# nginx configuration at /.well-known/mta-sts.txt
# more documentation is available on:
# https://www.uriports.com/blog/mta-sts-explained/
# default mode is "enforce". In /etc/mailinabox.conf change
# "MTA_STS_MODE=testing" which means "Messages will be delivered
# as though there was no failure but a report will be sent if
# TLS-RPT is configured" if you are not sure you want this yet. Or "none".
PUNY_PRIMARY_HOSTNAME=$(echo "$PRIMARY_HOSTNAME" | idn2)
cat conf/mta-sts.txt \
        | sed "s/MODE/${MTA_STS_MODE}/" \
        | sed "s/PRIMARY_HOSTNAME/$PUNY_PRIMARY_HOSTNAME/" \
         > /var/lib/mailinabox/mta-sts.txt
chmod a+r /var/lib/mailinabox/mta-sts.txt

# make a default homepage
if [ -d "$STORAGE_ROOT/www/static" ]; then mv "$STORAGE_ROOT/www/static" "$STORAGE_ROOT/www/default"; fi # migration #NODOC
mkdir -p "$STORAGE_ROOT/www/default"
if [ ! -f "$STORAGE_ROOT/www/default/index.html" ]; then
	# Not with cp by path: the storage user owns www/ and could have put a
	# symbolic link there, which cp writes through (B147).
	tools/write_conf.py "$STORAGE_ROOT/www/default/index.html" < conf/www_default.html
fi
chown -R "$STORAGE_USER" "$STORAGE_ROOT/www"

# Start services.
reload_nginx
restart_php_fpm

# Open ports.
ufw_allow http
ufw_allow https
