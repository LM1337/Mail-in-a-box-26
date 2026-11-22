#!/usr/local/lib/mailinabox/env/bin/python

# Reads in STDIN. If the stream is not empty, mail it to the system administrator:
# to the report recipient of System > Notifications (admin_mail.py),
# administrator@PRIMARY_HOSTNAME unless another address is set there.

import sys

import html
import smtplib

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# In Python 3.6:
#from email.message import Message

from utils import load_environment

# Load system environment info.
env = load_environment()

# Process command line args.
subject = sys.argv[1]

# Administrator's email address (the sender), and the recipient.
admin_addr = "administrator@" + env['PRIMARY_HOSTNAME']
try:
    from admin_mail import report_address
    to_addr = report_address(env)
except Exception as e: # a broken settings.yaml must not lose the report
    print(f"email_administrator: the report recipient could not be read ({e}); sending to {admin_addr}.", file=sys.stderr)
    to_addr = admin_addr

# Read in STDIN.
content = sys.stdin.read().strip()

# If there's nothing coming in, just exit.
if content == "":
    sys.exit(0)

# create MIME message
msg = MIMEMultipart('alternative')

# In Python 3.6:
#msg = Message()

msg['From'] = '"{}" <{}>'.format(env['PRIMARY_HOSTNAME'], admin_addr)
msg['To'] = to_addr
msg['Subject'] = "[{}] {}".format(env['PRIMARY_HOSTNAME'], subject)

content_html = f'<html><body><pre style="overflow-x: scroll; white-space: pre;">{html.escape(content)}</pre></body></html>'

msg.attach(MIMEText(content, 'plain'))
msg.attach(MIMEText(content_html, 'html'))

# In Python 3.6:
#msg.set_content(content)
#msg.add_alternative(content_html, "html")

# send, through Postfix's listener of the box's own reports (127.0.0.1:10587,
# setup/mail-postfix.sh), which does not pass the milter of the sending
# limit, so that the report arrives also while that milter is down;
# port 25 where there is no such listener (an older setup).
try:
    from admin_mail import admin_smtp
    smtpclient = admin_smtp(timeout=120)
except ImportError: # admin_mail.py cannot be loaded: the report must not be lost
    smtpclient = smtplib.SMTP('127.0.0.1', 25)
smtpclient.ehlo()
smtpclient.sendmail(
        admin_addr, # MAIL FROM
        to_addr, # RCPT TO
        msg.as_string())
smtpclient.quit()
