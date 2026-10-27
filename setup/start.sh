#!/bin/bash
# This is the entry point for configuring the system.
#####################################################

source setup/functions.sh # load our functions

# Check system setup: Are we running as root on Ubuntu 18.04 on a
# machine with enough memory? Is /tmp mounted with exec.
# If not, this shows an error and exits.
source setup/preflight.sh

# No cron jobs while setup runs: they would run against half-configured
# services (Nextcloud's cron.php during its upgrade steps, Munin during its
# installation), and their mail to root bounces until setup has written the
# root@ alias at its end (B82). Stop cron for the run and start it again when
# setup ends, also when it fails. A cron that is already stopped (the
# in-place upgrade and migration tools stop it themselves) is left alone.
#
# The start and the end of the run are marked in the journal (identifier
# mailinabox-setup): tests/fork/log-audit.sh accepts what the restarts of the
# services make clients and services log (cut connections) only in between.
#
# Stopping cron was not enough: when setup's apt-get upgrade replaced a
# library that a job still running from before setup used (cron's KillMode
# is "process", a stop leaves its jobs running), needrestart started
# cron.service again in the middle of setup (B138). Setup also masks cron in
# /run (gone at the next boot) while it runs; the marker file in /run tells
# a later run that a run that was killed before it could unmask cron left the
# mask behind.
SETUP_CRON_MASK_MARKER=/run/mailinabox-setup-masked-cron
logger -t mailinabox-setup "Mail-in-a-Box setup started" 2> /dev/null || true
SETUP_STOPPED_CRON=
SETUP_MASKED_CRON=
if [ -e "$SETUP_CRON_MASK_MARKER" ]; then
	systemctl unmask --runtime --quiet cron.service 2> /dev/null || true
	rm -f "$SETUP_CRON_MASK_MARKER"
	SETUP_STOPPED_CRON=1
fi
if systemctl is-active --quiet cron.service 2> /dev/null; then
	systemctl stop cron.service
	SETUP_STOPPED_CRON=1
fi
if [ -n "$SETUP_STOPPED_CRON" ] && [ "$(systemctl is-enabled cron.service 2> /dev/null)" != masked-runtime ]; then
	: > "$SETUP_CRON_MASK_MARKER"
	if systemctl mask --runtime --quiet cron.service 2> /dev/null; then
		SETUP_MASKED_CRON=1
	else
		rm -f "$SETUP_CRON_MASK_MARKER"
	fi
fi
function setup_ended {
	local rc=$?
	if [ -n "$SETUP_MASKED_CRON" ]; then
		systemctl unmask --runtime --quiet cron.service 2> /dev/null || true
		rm -f "$SETUP_CRON_MASK_MARKER"
	fi
	if [ -n "$SETUP_STOPPED_CRON" ]; then
		systemctl start cron.service 2> /dev/null || true
	fi
	logger -t mailinabox-setup "Mail-in-a-Box setup ended (exit code $rc)" 2> /dev/null || true
}
trap setup_ended EXIT

# Ensure Python reads/writes files in UTF-8. If the machine
# triggers some other locale in Python, like ASCII encoding,
# Python may not be able to read/write files. This is also
# in the management daemon startup script and the cron script.

if ! locale -a | grep en_US.utf8 > /dev/null; then
    # Generate locale if not exists
    hide_output locale-gen en_US.UTF-8
fi

export LANGUAGE=en_US.UTF-8
export LC_ALL=en_US.UTF-8
export LANG=en_US.UTF-8
export LC_TYPE=en_US.UTF-8

# Fix so line drawing characters are shown correctly in Putty on Windows. See #744.
export NCURSES_NO_UTF8_ACS=1

# Recall the last settings used if we're running this a second time.
if [ -f /etc/mailinabox.conf ]; then
	# Run any system migrations before proceeding. Since this is a second run,
	# we assume we have Python already installed.
	setup/migrate.py --migrate || exit 1

	# Load the old .conf file to get existing configuration options loaded
	# into variables with a DEFAULT_ prefix. Read through a pipe, not a file
	# with a fixed name in /tmp: another local user could create a file of
	# their own under that name first, which root would fail to overwrite and
	# then source (B89).
	# shellcheck source=/dev/null # generated from /etc/mailinabox.conf
	source <(sed s/^/DEFAULT_/ /etc/mailinabox.conf)
else
	FIRST_TIME_SETUP=1
fi

# Put a start script in a global location. We tell the user to run 'mailinabox'
# in the first dialog prompt, so we should do this before that starts.
cat > /usr/local/bin/mailinabox << EOF;
#!/bin/bash
cd $PWD
source setup/start.sh
EOF
chmod +x /usr/local/bin/mailinabox

# Ask the user for the PRIMARY_HOSTNAME, PUBLIC_IP, and PUBLIC_IPV6,
# if values have not already been set in environment variables. When running
# non-interactively, be sure to set values for all! Also sets STORAGE_USER and
# STORAGE_ROOT.
source setup/questions.sh

# Run some network checks to make sure setup on this machine makes sense.
# Skip on existing installs since we don't want this to block the ability to
# upgrade, and these checks are also in the control panel status checks.
if [ -z "${DEFAULT_PRIMARY_HOSTNAME:-}" ]; then
if [ -z "${SKIP_NETWORK_CHECKS:-}" ]; then
	source setup/network-checks.sh
fi
fi

# Create the STORAGE_USER and STORAGE_ROOT directory if they don't already exist.
#
# Set the directory and all of its parent directories' permissions to world
# readable since it holds files owned by different processes.
#
# If the STORAGE_ROOT is missing the mailinabox.version file that lists a
# migration (schema) number for the files stored there, assume this is a fresh
# installation to that directory and write the file to contain the current
# migration number for this version of Mail-in-a-Box.
if ! id -u "$STORAGE_USER" >/dev/null 2>&1; then
	useradd -m "$STORAGE_USER"
fi
if [ ! -d "$STORAGE_ROOT" ]; then
	mkdir -p "$STORAGE_ROOT"
fi
f=$STORAGE_ROOT
while [[ $f != / ]]; do chmod a+rx "$f"; f=$(dirname "$f"); done;
if [ ! -f "$STORAGE_ROOT/mailinabox.version" ]; then
	setup/migrate.py --current > "$STORAGE_ROOT/mailinabox.version"
	chown "$STORAGE_USER:$STORAGE_USER" "$STORAGE_ROOT/mailinabox.version"
fi

# Save the global options in /etc/mailinabox.conf so that standalone
# tools know where to look for data. The default MTA_STS_MODE setting
# is blank unless set by an environment variable, but see web.sh for
# how that is interpreted. FTS (full-text search in Dovecot) is "xapian"
# unless set to "off", see mail-dovecot.sh. NEXTCLOUD_SHARE_SCOPE is "domain"
# (Nextcloud users only see and share with their own mail domain) unless set
# to "all", see tools/nextcloud-share-scope.sh. FAVICON is "on" (the fork's
# favicon in Roundcube and Nextcloud) unless set to "off", see webmail.sh and
# nextcloud.sh.
cat > /etc/mailinabox.conf << EOF;
STORAGE_USER=$STORAGE_USER
STORAGE_ROOT=$STORAGE_ROOT
PRIMARY_HOSTNAME=$PRIMARY_HOSTNAME
PUBLIC_IP=$PUBLIC_IP
PUBLIC_IPV6=$PUBLIC_IPV6
PRIVATE_IP=$PRIVATE_IP
PRIVATE_IPV6=$PRIVATE_IPV6
MTA_STS_MODE=${DEFAULT_MTA_STS_MODE:-enforce}
FTS=${FTS:-${DEFAULT_FTS:-xapian}}
NEXTCLOUD_SHARE_SCOPE=${NEXTCLOUD_SHARE_SCOPE:-${DEFAULT_NEXTCLOUD_SHARE_SCOPE:-domain}}
FAVICON=${FAVICON:-${DEFAULT_FAVICON:-on}}
EOF
# PROBE_ADDRESS, the probe address of "tools/update-check.sh mailcheck", is
# kept when it is set (a plain address only: the file is sourced as root);
# setup itself does not use it.
PROBE_ADDRESS=${PROBE_ADDRESS:-${DEFAULT_PROBE_ADDRESS:-}}
if [[ $PROBE_ADDRESS =~ ^[A-Za-z0-9._%+=-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$ ]]; then
	echo "PROBE_ADDRESS=$PROBE_ADDRESS" >> /etc/mailinabox.conf
elif [ -n "$PROBE_ADDRESS" ]; then
	echo "PROBE_ADDRESS=$PROBE_ADDRESS is not a plain mail address; it is left out of /etc/mailinabox.conf."
fi

# Start service configuration. PHP-FPM is restarted once, after zpush.sh, not
# by each script that changes its configuration (restart_php_fpm in
# setup/functions.sh).
PHP_FPM_RESTART=later
source setup/system.sh
source setup/ssl.sh
source setup/dns.sh
source setup/mail-postfix.sh
source setup/mail-dovecot.sh
source setup/mail-users.sh
source setup/dkim.sh
source setup/spamassassin.sh
source setup/web.sh
source setup/webmail.sh
source setup/nextcloud.sh
source setup/zpush.sh
PHP_FPM_RESTART=
restart_php_fpm
source setup/management.sh
source setup/munin.sh

# Wait for the management daemon to start...
until nc -z -w 4 127.0.0.1 10222
do
	echo "Waiting for the Mail-in-a-Box management daemon to start..."
	sleep 2
done

# ...and then have it write the DNS and nginx configuration files and start those
# services.
tools/dns_update
tools/web_update

# Write the adaptive fail2ban configuration (repeat offenders get longer bans,
# slow jails, allowlist) from the "fail2ban" settings in settings.yaml. It is
# written here and not in system.sh because it needs the management venv and
# the log files of the slow jails. Exit code 3: the bantime.* options changed,
# and the jails must be restarted to drop removed ones.
f2b_setup_rc=0
management/fail2ban_admin.py --setup || f2b_setup_rc=$?

# Load fail2ban's configuration (system.sh and the adaptive one). The log files
# may not all have been present when fail2ban was first configured, but they
# should exist now. A reload keeps the bans; fail2ban is restarted only when it
# does not run (B122).
if [ "$f2b_setup_rc" = 3 ]; then
	reload_fail2ban --restart
elif [ "$f2b_setup_rc" = 0 ]; then
	reload_fail2ban
else
	exit "$f2b_setup_rc"
fi

# If there aren't any mail users yet, create one.
source setup/firstuser.sh

# Write the automatic aliases (hostmaster@, postmaster@, root@PRIMARY_HOSTNAME, ...)
# again. The management daemon only does this when users or aliases change, so an
# alias that an update makes required would otherwise not exist yet.
management/mailconfig.py update-auto-aliases

# Register with Let's Encrypt, including agreeing to the Terms of Service.
# We'd let certbot ask the user interactively, but when this script is
# run in the recommended curl-pipe-to-bash method there is no TTY and
# certbot will fail if it tries to ask.
if [ ! -d "$STORAGE_ROOT/ssl/lets_encrypt/accounts/acme-v02.api.letsencrypt.org/" ]; then
echo
echo "-----------------------------------------------"
echo "Mail-in-a-Box uses Let's Encrypt to provision free SSL/TLS certificates"
echo "to enable HTTPS connections to your box. We're automatically"
echo "agreeing you to their subscriber agreement. See https://letsencrypt.org."
echo
certbot register --register-unsafely-without-email --agree-tos --config-dir "$STORAGE_ROOT/ssl/lets_encrypt"
fi

# Done.
echo
echo "-----------------------------------------------"
echo
echo "Your Mail-in-a-Box is running."
echo
echo "Please log in to the control panel for further instructions at:"
echo
if management/status_checks.py --check-primary-hostname; then
	# Show the nice URL if it appears to be resolving and has a valid certificate.
	echo "https://$PRIMARY_HOSTNAME/admin"
	echo
	echo "If you have a DNS problem put the box's IP address in the URL"
	echo "(https://$PUBLIC_IP/admin) but then check the TLS fingerprint:"
	openssl x509 -in "$STORAGE_ROOT/ssl/ssl_certificate.pem" -noout -fingerprint -sha256\
        	| sed "s/SHA256 Fingerprint=//i"
else
	echo "https://$PUBLIC_IP/admin"
	echo
	echo "You will be alerted that the website has an invalid certificate. Check that"
	echo "the certificate fingerprint matches:"
	echo
	openssl x509 -in "$STORAGE_ROOT/ssl/ssl_certificate.pem" -noout -fingerprint -sha256\
        	| sed "s/SHA256 Fingerprint=//i"
	echo
	echo "Then you can confirm the security exception and continue."
	echo
fi
