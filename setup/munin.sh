#!/bin/bash
# Munin: resource monitoring tool
#################################################

source setup/functions.sh # load our functions
source /etc/mailinabox.conf # load global vars

# install Munin
echo "Installing Munin (system monitoring)..."
apt_install munin munin-node libcgi-fast-perl
# libcgi-fast-perl is needed by /usr/lib/munin/cgi/munin-cgi-graph

# Write munin.conf. management/munin_admin.py makes the whole file, with the
# contact for Munin's alerts from the admin panel's setting ("munin_alerts" in
# settings.yaml): by default munin-limits mails each change of state to
# administrator@$PRIMARY_HOSTNAME. The management daemon writes the same file
# when the setting changes. (The management venv exists: management.sh ran.)
management/munin_admin.py --setup

# The command of the contact above. It sends the alert with /usr/sbin/sendmail;
# Ubuntu has no "mail" command unless a mail client is installed. munin-limits
# runs it as user munin.
install -o root -g root -m 0755 management/munin_notify.sh /usr/local/lib/mailinabox/munin-notify

# The Debian installer touches these files and chowns them to www-data:adm for use with spawn-fcgi
# /var/log/munin belongs to munin, so a file there may be a symbolic link that munin
# made: -h changes the owner of the link itself and never of what it points to (B86).
chown -h munin /var/log/munin/munin-cgi-html.log /var/log/munin/munin-cgi-graph.log

# ensure munin-node knows the name of this machine
# and reduce logging level to warning
tools/editconf.py /etc/munin/munin-node.conf -s \
	host_name="$PRIMARY_HOSTNAME" \
	log_level=1

# Update the activated plugins through munin's autoconfiguration.
munin-node-configure --shell --remove-also 2>/dev/null | sh || /bin/true

# Deactivate monitoring of NTP peers. Not sure why anyone would want to monitor a NTP peer. The addresses seem to change
# (which is taken care of my munin-node-configure, but only when we re-run it.)
find /etc/munin/plugins/ -lname /usr/share/munin/plugins/ntp_ -print0 | xargs -0 /bin/rm -f

# Deactivate monitoring of network interfaces that are not up. Otherwise we can get a lot of empty charts.
# Also of the veth interfaces of containers (Docker): they get a new name at each start of
# their container, and the plugin of the old name then reports "unknown" for ever, which
# munin-limits mails as an alert (B80).
for f in $(find /etc/munin/plugins/ \( -lname /usr/share/munin/plugins/if_ -o -lname /usr/share/munin/plugins/if_err_ -o -lname /usr/share/munin/plugins/bonding_err_ \)); do
	IF=$(echo "$f" | sed s/.*_//);
	if [[ $IF == veth* ]] || ! grep -qFx up "/sys/class/net/$IF/operstate" 2>/dev/null; then
		rm "$f";
	fi;
done

# Create a 'state' directory. Not sure why we need to do this manually.
mkdir -p /var/lib/munin-node/plugin-state/

# Create a systemd service for munin.
ln -sf "$PWD/management/munin_start.sh" /usr/local/lib/mailinabox/munin_start.sh
chmod 0744 /usr/local/lib/mailinabox/munin_start.sh
install_unit munin.service

# Restart services.
restart_service munin
restart_service munin-node

# generate initial statistics so the directory isn't empty
# (We get "Pango-WARNING **: error opening config file '/root/.config/pango/pangorc': Permission denied"
# if we don't explicitly set the HOME directory when sudo'ing.)
# We check to see if munin-cron is already running, if it is, there is no need to run it simultaneously
# generating an error.
if [ ! -f /var/run/munin/munin-update.lock ]; then
	sudo -H -u munin munin-cron
fi
