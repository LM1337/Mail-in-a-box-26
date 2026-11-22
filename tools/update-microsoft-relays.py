#!/usr/bin/env python3
"""Refresh conf/fail2ban/microsoft-relays.txt from Microsoft's published lists.

The control panel (System > Intrusion Detection and Prevention) recognises a banned
address of the servers through which Outlook for iOS and Android syncs an
Exchange ActiveSync account (management/cloud_relays.py, B126). Microsoft
names them for an on-premises ActiveSync endpoint ("Using Basic
authentication with Outlook for iOS and Android", Connectivity
Requirements):

  * all IP ranges of Exchange Online in the Microsoft 365 IP Address and
    URL web service (service area "Exchange", instance Worldwide), which
    this tool downloads:
    https://endpoints.office.com/endpoints/Worldwide?ServiceAreas=Exchange&clientrequestid=<GUID>
  * the ranges of the AutoDetect service, which are not in the web service
    but on the page "Other endpoints not included in the Microsoft 365 IP
    Address and URL Web service" (row 10), AUTODETECT below: compare them
    with the page before a release and change them here when the page
    changes:
    https://learn.microsoft.com/en-us/microsoft-365/enterprise/additional-office365-ip-addresses-and-urls

The file gets the source URLs, the web service's version, the date, the
SHA256 of the downloaded answer and the SHA256 of the network lines; the
daemon does not use a file whose networks do not match that last sum. The
box never downloads the lists itself: the file is part of the repository
and reaches a box with an update.

Run it on a development machine, from the repository, and commit the file
with a CHANGELOG-fork.md entry:

  python3 -I tools/update-microsoft-relays.py           # download, write the file
  python3 -I tools/update-microsoft-relays.py --check   # check the file (exit 1 on a problem)
  python3 -I tools/update-microsoft-relays.py --from-json ANSWER --version V
                                                        # build it from a saved answer

Only the Python standard library is needed.
"""
import argparse
import datetime
import hashlib
import importlib.util
import ipaddress
import json
import os
import sys
import tempfile
import urllib.request
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
OUT = os.path.join(ROOT, "conf", "fail2ban", "microsoft-relays.txt")

ENDPOINTS = "https://endpoints.office.com/endpoints/Worldwide?ServiceAreas=Exchange&clientrequestid={}"
VERSION = "https://endpoints.office.com/version/Worldwide?clientrequestid={}"
OTHER_PAGE = "https://learn.microsoft.com/en-us/microsoft-365/enterprise/additional-office365-ip-addresses-and-urls"
# Row 10 of OTHER_PAGE: "The AutoDetect service is used in Exchange Hybrid
# scenarios with Hybrid Modern Authentication with Outlook for iOS and
# Android", inbound to the customer's on-premises Exchange server on TCP 443
# (as of the page's update of 2026-10-30).
AUTODETECT = ["52.125.128.0/20", "52.127.96.0/23"]
AUTODETECT_AS_OF = "2026-10-30"


def cloud_relays():
	spec = importlib.util.spec_from_file_location("cloud_relays", os.path.join(ROOT, "management", "cloud_relays.py"))
	mod = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(mod)
	return mod


def fetch(url):
	req = urllib.request.Request(url, headers={"User-Agent": "mailinabox-fork-update-microsoft-relays/1"})
	with urllib.request.urlopen(req, timeout=60) as r:
		if r.status != 200:
			raise RuntimeError(f"{url}: HTTP {r.status}")
		return r.read()


def exchange_networks(answer):
	# The IP ranges of the web service's answer in the service area
	# Exchange, normalized, without duplicates, IPv4 first.
	data = json.loads(answer)
	if not isinstance(data, list):
		raise ValueError("the answer is not a list of endpoint sets")
	nets = set()
	for e in data:
		if not isinstance(e, dict) or e.get("serviceArea") != "Exchange":
			continue
		for ip in e.get("ips") or []:
			nets.add(ipaddress.ip_network(str(ip), strict=True))
	if not nets:
		raise ValueError("the answer has no IP ranges of the service area Exchange")
	return nets


def render(answer, version, retrieved):
	nets = exchange_networks(answer) | {ipaddress.ip_network(n) for n in AUTODETECT}
	nets = sorted(nets, key=lambda n: (n.version, n))
	lines = [str(n) for n in nets]
	cr = cloud_relays()
	head = [
		"# The servers through which Outlook for iOS and Android syncs Exchange",
		"# ActiveSync accounts (Microsoft's published IP ranges), for the hint of",
		"# System > Intrusion Detection and Prevention at a banned address (management/cloud_relays.py).",
		"# Made by tools/update-microsoft-relays.py; do not edit by hand: a file whose",
		"# networks do not match networks-sha256 is not used.",
		"#",
		"# Microsoft lists for an on-premises ActiveSync endpoint all Exchange Online",
		"# ranges and the AutoDetect ranges (learn.microsoft.com, \"Using Basic",
		"# authentication with Outlook for iOS and Android\", Connectivity Requirements).",
		"#",
		"# source: " + ENDPOINTS.format("<GUID>") + " (service area Exchange, all IDs)",
		"# source-version: " + version,
		"# source-sha256: " + hashlib.sha256(answer).hexdigest(),
		"# extra-source: " + OTHER_PAGE + " (row 10, AutoDetect, as of " + AUTODETECT_AS_OF + ")",
		"# extra-networks: " + " ".join(AUTODETECT),
		"# retrieved: " + retrieved,
		"# networks-sha256: " + cr.networks_sha256(lines),
	]
	text = "\n".join(head) + "\n" + "".join(n + "\n" for n in lines)
	cr.parse(text)  # the same check as the daemon's
	return text


def write(path, text):
	d = os.path.dirname(path)
	fd, tmp = tempfile.mkstemp(dir=d, prefix=".microsoft-relays.")
	try:
		with os.fdopen(fd, "w", encoding="ascii") as f:
			f.write(text)
		os.chmod(tmp, 0o644)
		os.replace(tmp, path)
	except BaseException:
		os.unlink(tmp)
		raise


def main():
	ap = argparse.ArgumentParser(description="Refresh " + os.path.relpath(OUT, ROOT) + " from Microsoft's published lists.")
	ap.add_argument("--check", action="store_true", help="only check the file")
	ap.add_argument("--from-json", metavar="ANSWER", help="build the file from a saved answer of the web service")
	ap.add_argument("--version", help="the web service's version for --from-json")
	ap.add_argument("--retrieved", help="the date for --from-json (default: today)")
	ap.add_argument("--out", default=OUT, help="the file to write or check")
	args = ap.parse_args()

	if args.check:
		with open(args.out, encoding="ascii") as f:
			header, nets = cloud_relays().parse(f.read())
		print("%s: %d networks (%d IPv4, %d IPv6), version %s, retrieved %s" % (
			os.path.relpath(args.out, ROOT), len(nets), sum(n.version == 4 for n in nets),
			sum(n.version == 6 for n in nets), header.get("source-version"), header.get("retrieved")))
		return 0

	if args.from_json:
		if not args.version:
			ap.error("--from-json needs --version")
		with open(args.from_json, "rb") as f:
			answer = f.read()
		version, retrieved = args.version, args.retrieved or datetime.date.today().isoformat()
	else:
		guid = str(uuid.uuid4())
		version = str(json.loads(fetch(VERSION.format(guid))).get("latest"))
		answer = fetch(ENDPOINTS.format(guid))
		retrieved = datetime.date.today().isoformat()
	text = render(answer, version, retrieved)
	old = None
	if os.path.exists(args.out):
		with open(args.out, encoding="ascii") as f:
			old = f.read()
	write(args.out, text)
	print("%s: written (version %s)%s" % (os.path.relpath(args.out, ROOT), version,
		", networks unchanged" if old and cloud_relays().parse(old)[1] == cloud_relays().parse(text)[1] else ""))
	return 0


if __name__ == "__main__":
	sys.exit(main())
