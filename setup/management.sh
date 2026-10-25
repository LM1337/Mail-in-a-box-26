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

# Make sure we have the directory to save to.
assets_dir=$inst_dir/vendor/assets
rm -rf $assets_dir
mkdir -p $assets_dir

# jQuery CDN URL
jquery_version=3.7.1 # newest 3.x; Bootstrap 3 JS refuses jQuery >= 4
jquery_url=https://code.jquery.com

# Get jQuery
# SHA256; matches the official SRI sha256-/JqT3SQfawRcv/BIHPThkBvs0OEvtFFmqPF/lYI/Cxo=
wget_verify $jquery_url/jquery-$jquery_version.min.js fc9a93dd241f6b045cbff0481cf4e1901becd0e12fb45166a8f17f95823f0b1a $assets_dir/jquery.min.js

# Bootstrap CDN URL
# Bootstrap 3.4.1 is the final 3.x release (EOL since 2019). The admin templates depend on
# Bootstrap 3 (glyphicons, panels, bootstrap-theme.css); 5.x would need a template rewrite.
bootstrap_version=3.4.1
bootstrap_url=https://github.com/twbs/bootstrap/releases/download/v$bootstrap_version/bootstrap-$bootstrap_version-dist.zip

# Get Bootstrap (into a directory of root's own, not under a fixed name in /tmp, B97)
bootstrap_tmp=$(mktemp -d)
wget_verify $bootstrap_url d49793cf773cbd393ac2cf340c3b4ddab5365fa7c292098ac07e12eab3efd92e "$bootstrap_tmp/bootstrap.zip" # SHA256 (no digest published for this asset)
unzip -q "$bootstrap_tmp/bootstrap.zip" -d $assets_dir
mv $assets_dir/bootstrap-$bootstrap_version-dist $assets_dir/bootstrap
rm -rf "$bootstrap_tmp"

# The fork's favicons and icon (from branding/), served as /admin/assets/branding/ and as
# the fallback /favicon.ico of the box's web domains (see conf/nginx-alldomains.conf).
mkdir -p $assets_dir/branding
cp branding/icon.svg branding/favicon.ico branding/favicon-16.png branding/favicon-32.png \
	branding/apple-touch-icon.png $assets_dir/branding/
chmod a+r $assets_dir/branding/*

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

# Start the management server.
restart_service mailinabox
