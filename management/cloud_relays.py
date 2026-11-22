# Cloud servers that relay ActiveSync logins (fork; for System > Intrusion
# Protection, fail2ban_admin.py).
#
# Outlook for iOS and Android syncs an Exchange ActiveSync account through
# Microsoft's servers: the box sees the logins of all users of the app from
# the same few addresses, so a few wrong passwords there (by mistake, or by
# anyone on purpose) get these addresses banned by miab-zpush for all of
# them (B126). The control panel shows a hint at a banned address that
# belongs to these servers and offers to put its network on the allowlist;
# the administrator decides, nothing is allowlisted on its own.
#
# Which addresses: Microsoft's own published list, not reverse DNS (whoever
# owns an address sets its PTR record). Microsoft names, for the servers that
# connect to an on-premises ActiveSync endpoint for Outlook for iOS and
# Android ("Using Basic authentication with Outlook for iOS and Android",
# Connectivity Requirements), "all Exchange Online FQDNs and IP subnet
# ranges" of the Microsoft 365 IP Address and URL web service and the
# AutoDetect ranges of "Other endpoints not included in the web service"
# (row 10). tools/update-microsoft-relays.py downloads them into DATA_FILE,
# with the source, its version, the date and SHA256 sums; this module only
# reads that file, it never downloads anything. A file whose networks do not
# match its "networks-sha256" line (edited by hand, or cut short) is not used.
#
# A banned address in these networks gets the PTR name of the address as
# extra information, only if the name resolves back to the same address
# (forward-confirmed reverse DNS); the name decides nothing.

import concurrent.futures, hashlib, ipaddress, os.path, re

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "conf", "fail2ban", "microsoft-relays.txt")

PROVIDER = "Microsoft"
SERVICE = "Outlook for iOS and Android (Exchange Online and its AutoDetect service)"

MAX_LOOKUPS = 16      # FCrDNS lookups per status request
LOOKUP_TIMEOUT = 2    # seconds per DNS query

RE_HEADER = re.compile(r"^# ([a-z0-9-]+): (.*)$")
RE_NETWORK = re.compile(r"^[0-9A-Fa-f:.]+/\d{1,3}$")
RE_HOSTNAME = re.compile(r"^(?=.{1,253}$)([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")

def networks_sha256(networks):
	# The SHA256 of the network lines as the file has them, one per line.
	return hashlib.sha256("".join(n + "\n" for n in networks).encode("ascii")).hexdigest()

def parse(text):
	# The header fields and the networks of a data file. Raises ValueError
	# for anything else than "# key: value" lines, comments, empty lines and
	# networks in CIDR notation, and when the networks do not match their
	# SHA256 line.
	header, networks = {}, []
	for n, line in enumerate(text.splitlines(), 1):
		m = RE_HEADER.match(line)
		if m:
			header.setdefault(m.group(1), m.group(2).strip())
		elif line.startswith("#") or not line.strip():
			continue
		elif RE_NETWORK.match(line):
			try:
				ipaddress.ip_network(line, strict=True)
			except ValueError:
				raise ValueError(f"line {n} is not a network") from None
			networks.append(line)
		else:
			raise ValueError(f"line {n} is not a network")
	if not networks:
		raise ValueError("it lists no networks")
	if header.get("networks-sha256") != networks_sha256(networks):
		raise ValueError("its networks do not match its networks-sha256 line")
	return header, [ipaddress.ip_network(n) for n in networks]

_cache = {}

def load(path=DATA_FILE):
	# parse() of the file, read again only when it changed (an update of the
	# Mail-in-a-Box checkout replaces it).
	st = os.stat(path)
	key = (path, st.st_mtime_ns, st.st_size)
	if key not in _cache:
		with open(path, encoding="ascii") as f:
			_cache.clear()
			_cache[key] = parse(f.read())
	return _cache[key]

def match(ip, networks):
	# The most specific of the networks that contains the address, or None.
	try:
		a = ipaddress.ip_address(ip)
	except ValueError:
		return None
	if a.version == 6 and a.ipv4_mapped:
		a = a.ipv4_mapped
	hits = [n for n in networks if n.version == a.version and a in n]
	return max(hits, key=lambda n: n.prefixlen) if hits else None

def fcrdns(ip, ptr_lookup, addr_lookup):
	# The first PTR name of the address that resolves back to it (A or AAAA),
	# or None. ptr_lookup(ip) gives the PTR names, addr_lookup(name, rtype)
	# the addresses of a name; either may raise, which counts as no name.
	a = ipaddress.ip_address(ip)
	try:
		names = list(ptr_lookup(str(a)))[:5]
	except Exception:
		return None
	for name in names:
		name = str(name).rstrip(".")
		if not RE_HOSTNAME.match(name):
			continue
		try:
			addrs = addr_lookup(name, "A" if a.version == 4 else "AAAA")
		except Exception:
			continue
		for x in addrs:
			try:
				if ipaddress.ip_address(str(x)) == a:
					return name.lower()
			except ValueError:
				continue
	return None

def dns_lookups():
	# ptr_lookup and addr_lookup for fcrdns() with dnspython and the box's
	# resolver.
	import dns.resolver, dns.reversename
	resolver = dns.resolver.Resolver()
	resolver.timeout = resolver.lifetime = LOOKUP_TIMEOUT
	def ptr_lookup(ip):
		return [r.target.to_text(omit_final_dot=True) for r in resolver.resolve(dns.reversename.from_address(ip), "PTR")]
	def addr_lookup(name, rtype):
		return [r.to_text() for r in resolver.resolve(name + ".", rtype)]
	return ptr_lookup, addr_lookup

def relay_hints(ips, path=DATA_FILE, lookups=None, names=True):
	# {ip: hint} for the addresses that are in the networks of the data file:
	# the provider, the service, the network (for the allowlist button) and
	# the forward-confirmed PTR name or None (always None with names=False:
	# no DNS lookups). Also the source of the list.
	header, networks = load(path)
	found = {}
	for ip in sorted(set(ips)):
		net = match(ip, networks)
		if net is not None:
			found[ip] = { "provider": PROVIDER, "service": SERVICE, "network": str(net), "name": None }
	todo = sorted(found)[:MAX_LOOKUPS] if names else []
	if todo:
		if lookups is None:
			try:
				lookups = dns_lookups()
			except Exception:
				lookups = None
		if lookups is not None:
			with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
				for ip, name in zip(todo, pool.map(lambda ip: fcrdns(ip, *lookups), todo)):
					found[ip]["name"] = name
	source = { "version": header.get("source-version"), "retrieved": header.get("retrieved"), "networks": len(networks) }
	return found, source
