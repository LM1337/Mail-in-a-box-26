#!/bin/bash

source setup/functions.sh
source /etc/mailinabox.conf # load global vars

echo "Installing Mail-in-a-Box system management daemon..."

# DEPENDENCIES

# duplicity is used to make backups of user data.
#
# virtualenv is used to isolate the Python 3 packages we
# install via pip from the system-installed packages.
#
# certbot installs EFF's certbot which we use to
# provision free TLS certificates.
apt_install duplicity python3-gnupg python3-pip virtualenv python3-b2sdk python3-boto3 certbot rsync

# b2sdk is used for backblaze backups.
# boto3 is used for amazon aws backups.
# Both are installed outside the pipenv, so they can be used by duplicity
## TEST: hide_output pip3 install --upgrade b2sdk boto3

# Create a virtualenv for the installation of Python 3 packages
# used by the management daemon.
inst_dir=/usr/local/lib/mailinabox
mkdir -p $inst_dir
venv=$inst_dir/env
# A venv is bound to the interpreter it was made with. After a release upgrade
# (e.g. Python 3.12 -> 3.14) recreate it instead of keeping a broken one.
# The check runs the interpreter instead of testing for an executable: after a
# release upgrade bin/python3 is a dangling link to the removed python3.X, and a
# venv made with it would be kept and break pip below (In-Place 4).
if [ -d $venv ] && [ "$($venv/bin/python3 -c 'import sys; print(sys.version_info[:2])' 2>/dev/null)" != "$(python3 -c 'import sys; print(sys.version_info[:2])')" ]; then
	rm -rf $venv
fi
if [ ! -d $venv ]; then
	# A bug specific to Ubuntu 22.04 and Python 3.10 requires
	# forcing a virtualenv directory layout option (see #2335
	# and https://github.com/pypa/virtualenv/pull/2415). In
	# our issue, reportedly installing python3-distutils didn't
	# fix the problem.)
	export DEB_PYTHON_INSTALL_LAYOUT='deb'
	hide_output virtualenv -ppython3 $venv
fi

# Upgrade pip because the Ubuntu-packaged version is out of date.
hide_output $venv/bin/pip install --upgrade pip

# Install other Python 3 packages used by the management daemon.
# The first line is the packages that Josh maintains himself!
# NOTE: email_validator is repeated in setup/questions.sh (Ubuntu's python3-email-validator,
# 2.2.x on 26.04), so keep both on the same major. mailconfig.py only uses
# validate_email(email, allow_smtputf8=, check_deliverability=, allow_empty_local=).
# Everything floats to the newest release, with these bounds:
# * cryptography: newest 50.x. The code needs >= 42 (not_valid_*_utc); the upper bound keeps
#   a new major (they remove APIs and tighten parsing) from arriving unreviewed. Bump it when
#   the fork is updated. (It was pinned to 37.0.2 from 2022, with 22 known advisories.)
# * b2sdk/boto3 floors: without them a resolver may satisfy "python-dateutil" (3.x) by
#   backtracking to an ancient boto3; botocore requires python-dateutil<3, so 2.9.x is used.
# * email_validator 2.x (positional-only email argument), idna >= 3.20.
# Checked on Python 3.14 (2026-10-22): pip 26.2.2 resolves cryptography 50.0.2, b2sdk 2.13.2,
# boto3 1.43.118, python-dateutil 2.9.0.post0, flask 3.1.3, gunicorn 26.2.0, pip check clean.
hide_output $venv/bin/pip install --upgrade \
	rtyaml "email_validator>=2.3.0,<3" "exclusiveprocess" \
	flask dnspython python-dateutil expiringdict gunicorn \
	"qrcode[pil]" pyotp \
	"idna>=3.20" "cryptography>=50.0.2,<51" psutil postfix-mta-sts-resolver \
	"b2sdk>=2.13" "boto3>=1.43"

# CONFIGURATION

# Create a backup directory and a random key for encrypting backups.
mkdir -p "$STORAGE_ROOT/backup"
if [ ! -f "$STORAGE_ROOT/backup/secret_key.txt" ]; then
	(umask 077; openssl rand -base64 2048 > "$STORAGE_ROOT/backup/secret_key.txt")
fi


# Download jQuery and Bootstrap local files

# Into a new directory next to the installed one, which replaces it only when
# it is complete: up to v78-r2604.1 the installed one was emptied first, and
# a failed download left the control panel without jQuery and Bootstrap
# until a later run (B157). A directory of root's own (mktemp -d), not a
# fixed name in /tmp that another local user could create first (B97); one
# that an earlier run left behind is removed.
assets_dir=$inst_dir/vendor/assets
mkdir -p "$inst_dir/vendor"
find "$inst_dir/vendor" -maxdepth 1 -name '.assets-new.*' -type d -user root -exec rm -rf -- {} +
assets_tmp=$(mktemp -d "$inst_dir/vendor/.assets-new.XXXXXXXX")
assets_new=$assets_tmp/assets
mkdir "$assets_new"

# jQuery CDN URL
jquery_version=3.7.1 # newest 3.x; Bootstrap 3 JS refuses jQuery >= 4
jquery_url=https://code.jquery.com

# Get jQuery
# SHA256; matches the official SRI sha256-/JqT3SQfawRcv/BIHPThkBvs0OEvtFFmqPF/lYI/Cxo=
wget_verify $jquery_url/jquery-$jquery_version.min.js fc9a93dd241f6b045cbff0481cf4e1901becd0e12fb45166a8f17f95823f0b1a "$assets_new/jquery.min.js"

# Bootstrap CDN URL
# Bootstrap 3.4.1 is the final 3.x release (EOL since 2019). The admin templates depend on
# Bootstrap 3 (glyphicons, panels, bootstrap-theme.css); 5.x would need a template rewrite.
bootstrap_version=3.4.1
bootstrap_url=https://github.com/twbs/bootstrap/releases/download/v$bootstrap_version/bootstrap-$bootstrap_version-dist.zip

# Get Bootstrap
wget_verify $bootstrap_url d49793cf773cbd393ac2cf340c3b4ddab5365fa7c292098ac07e12eab3efd92e "$assets_tmp/bootstrap.zip" # SHA256 (no digest published for this asset)
unzip -q "$assets_tmp/bootstrap.zip" -d "$assets_new"
mv "$assets_new/bootstrap-$bootstrap_version-dist" "$assets_new/bootstrap"

# The fork's favicons and icon (from branding/), served as /admin/assets/branding/ and as
# the fallback /favicon.ico of the box's web domains (see conf/nginx-alldomains.conf).
mkdir -p "$assets_new/branding"
cp branding/icon.svg branding/favicon.ico branding/favicon-16.png branding/favicon-32.png \
	branding/apple-touch-icon.png "$assets_new/branding/"
chmod a+r "$assets_new"/branding/*

# The new directory goes into place: the installed one is renamed away first
# and removed after, so that the assets are missing only between two renames.
rm -rf "$assets_dir.old"
if [ -e "$assets_dir" ]; then
	mv "$assets_dir" "$assets_dir.old"
fi
mv "$assets_new" "$assets_dir"
rm -rf "$assets_dir.old" "$assets_tmp"

# Create an init script to start the management daemon and keep it
# running after a reboot.
# Set a long timeout since some commands take a while to run, matching
# the timeout we set for PHP (fastcgi_read_timeout in the nginx confs).
# Note: Authentication currently breaks with more than 1 gunicorn worker.
cat > $inst_dir/start <<EOF;
#!/bin/bash
# Set character encoding flags to ensure that any non-ASCII don't cause problems.
export LANGUAGE=en_US.UTF-8
export LC_ALL=en_US.UTF-8
export LANG=en_US.UTF-8
export LC_TYPE=en_US.UTF-8

mkdir -p /var/lib/mailinabox
tr -cd '[:xdigit:]' < /dev/urandom | head -c 32 > /var/lib/mailinabox/api.key
chmod 640 /var/lib/mailinabox/api.key

source $venv/bin/activate
export PYTHONPATH=$PWD/management
exec gunicorn -b 127.0.0.1:10222 -w 1 --timeout 630 wsgi:app
EOF
chmod +x $inst_dir/start
install_unit mailinabox.service

# Perform nightly tasks at 3am in system time: take a backup, run
# status checks and email the administrator any changes.

minute=$((RANDOM % 60))  # avoid overloading mailinabox.email
cat > /etc/cron.d/mailinabox-nightly << EOF;
# Mail-in-a-Box --- Do not edit / will be overwritten on update.
# Run nightly tasks: backup, status checks.
$minute 1 * * *	root	(cd $PWD && management/daily_tasks.sh)
EOF

# Mail the accounts that Dovecot refuses for logins from the box itself after
# too many failed logins, and remove the counts of names without failures
# (management/auth_guard.py, setup/mail-users.sh).
tools/write_conf.py /etc/cron.d/mailinabox-auth-guard << EOF;
# Mail-in-a-Box --- Do not edit / will be overwritten on update.
# Dovecot's limit of failed logins from the box itself: mail new locks.
*/10 * * * *	root	(cd $PWD && test -x management/auth_guard.py && management/auth_guard.py --notify)
EOF
# Its limit and window, as System > Intrusion Detection and Prevention set them in
# settings.yaml (also after a migration), for the Lua code of Dovecot.
management/auth_guard.py --apply

# The sending limit (management/send_limit.py, setup/mail-postfix.sh): mail
# the minutes in which outgoing mail had to wait, and write the settings file
# of its milter from settings.yaml. The jobs check that the program is there:
# after a downgrade to a release without it, they stay quiet instead of
# mailing an error to root every few minutes.
tools/write_conf.py /etc/cron.d/mailinabox-send-limit << EOF;
# Mail-in-a-Box --- Do not edit / will be overwritten on update.
# The sending limit of the box: mail the minutes in which mail had to wait.
*/5 * * * *	root	(cd $PWD && test -x management/send_limit.py && management/send_limit.py --notify)
EOF
# When the brake of the sending limit goes on, its release service starts
# this unit, so the administrator is mailed at once, not at the next cron run.
tools/write_conf.py /etc/systemd/system/miab-sendlimit-notify.service << EOF;
# Mail-in-a-Box --- Do not edit / will be overwritten on update.
[Unit]
Description=Mail-in-a-Box sending limit: mail the administrator (management/send_limit.py --notify)

[Service]
Type=oneshot
WorkingDirectory=$PWD
ExecStart=$PWD/management/send_limit.py --notify
EOF
hide_output systemctl daemon-reload
management/send_limit.py --apply

# Start the management server, or restart it when its code, its start script
# and unit, /etc/mailinabox.conf (read when it starts) or the packages of its
# virtualenv changed (restart_on_change; its own replaced library files are
# checked too). A restart makes the control panel answer 502 for a moment.
venv_packages=()
for d in "$venv"/lib/python3*/site-packages; do venv_packages+=("dir:$d"); done
restart_on_change mailinabox "" "tree:$PWD/management" "$inst_dir/start" \
	/lib/systemd/system/mailinabox.service tree:/etc/systemd/system/mailinabox.service.d \
	/etc/mailinabox.conf "stat:$venv/bin/python3" "dir:$venv/bin" "${venv_packages[@]}"
