-- Mail-in-a-Box: a limit of failed logins per account for the logins that
-- come from the box itself (127.0.0.1 and ::1: Z-Push's ActiveSync and
-- Autodiscover, Roundcube, Nextcloud's IMAP login, and anything else that
-- runs on the box). setup/mail-users.sh installs this file in
-- /usr/local/lib/mailinabox/dovecot-auth-guard/, with check.lua and
-- count.lua, the two passdbs that use it. Do not edit: setup writes it
-- again on every run.
--
-- count.lua (the last passdb, reached only by a failed login) answers a
-- failed login from the box at once, without Dovecot's delay and penalty
-- (B126: the penalty belongs to the address 127.0.0.1, so it slowed down
-- the logins of all users of these services), and records it for the
-- account name. check.lua (the first passdb, deny = yes) refuses every
-- login from the box for a name with LIMIT different wrong passwords
-- within WINDOW seconds (30 in 30 minutes unless the control panel sets
-- others, see M.load), before the password is checked: guesses stop
-- telling right from wrong, and nothing raises the penalty of 127.0.0.1,
-- so the other accounts are not slowed down.
--
-- Only different wrong passwords count, as with Dovecot's own penalty: a
-- phone that keeps sending an old password, or a typo sent again, counts
-- once, so it cannot lock its own account; someone who guesses has to try
-- different passwords, and each one counts. The password itself is never
-- written: only a tag of 16 bits of a hash of it with a random salt that
-- count.lua chooses when it starts (65536 values: two different guesses
-- seldom share one, and a tag tells nothing about the password).
--
-- Only the failures of the account itself count, and only real accounts
-- are counted: made-up names cannot lower the limit of a real account,
-- crowd out its count, or fill the state. "From the box itself" is every
-- address of 127.0.0.0/8, ::1 and the box's own addresses (M.from_box).
-- Logins from other addresses are left to Dovecot as before.
--
-- The state is in DIR (tmpfs, 0700, the account dovecot: the auth process
-- runs as dovecot, /etc/tmpfiles.d/miab-auth-guard.conf creates it), so
-- that both passdbs see it (each passdb has a Lua state of its own) and no
-- other account can change it. A file per name, a line "<time> <tag>" per
-- failed login with a new tag, for the accounts on the list (M.accounts)
-- and a pool of other names.
-- management/auth_guard.py reads the state,
-- removes the files of names without failures in the window and mails the
-- events. If the state cannot be written, failed logins get Dovecot's delay
-- and penalty again (as before B126), never no limit.

local M = {}

M.DIR = "/run/miab-auth-guard"
M.DEFAULT_LIMIT = 30    -- different wrong passwords of one account within the window
M.DEFAULT_WINDOW = 1800 -- seconds
M.MAX_NAMES = 2000      -- names tracked without the list of accounts (see M.accounts)
M.POOL = 500            -- names not on the list that are tracked (count.lua)
M.MAX_EVENTS = 1048576  -- bytes of the events file

-- The limit, the window and the box's own addresses: System > Intrusion
-- Protection in the control panel sets the first two, setup the addresses
-- (management/auth_guard.py writes SETTINGS: "limit N", "window SECONDS",
-- "span N",
-- "local ADDRESS" per address of the box, from /etc/mailinabox.conf). Read
-- on every login from the box, so a change applies at once, without a
-- reload of Dovecot. A missing file or a value out of range means the
-- default.
M.SETTINGS = "/usr/local/lib/mailinabox/dovecot-auth-guard/settings"
M.LIMIT_MIN, M.LIMIT_MAX = 3, 1000
M.WINDOW_MIN, M.WINDOW_MAX = 60, 86400
M.DEFAULT_SPAN = 4
M.SPAN_MIN, M.SPAN_MAX = 1, 4
M.LIMIT, M.WINDOW, M.SPAN, M.LOCAL = M.DEFAULT_LIMIT, M.DEFAULT_WINDOW, M.DEFAULT_SPAN, {}

function M.load()
	local limit, window, span, addrs = M.DEFAULT_LIMIT, M.DEFAULT_WINDOW, M.DEFAULT_SPAN, {}
	local f = io.open(M.SETTINGS, "r")
	if f then
		for line in f:lines() do
			local k, v = line:match("^(%a+) (%S+)$")
			local n = tonumber(v)
			if k == "limit" and n and n >= M.LIMIT_MIN and n <= M.LIMIT_MAX then
				limit = n
			elseif k == "window" and n and n >= M.WINDOW_MIN and n <= M.WINDOW_MAX then
				window = n
			elseif k == "span" and n and n >= M.SPAN_MIN and n <= M.SPAN_MAX and n == math.floor(n) then
				span = math.floor(n)
			elseif k == "local" and v:match("^[%x:.]+$") and #v <= 45 then
				addrs[string.lower(v)] = true
			end
		end
		f:close()
	end
	M.LIMIT, M.WINDOW, M.SPAN, M.LOCAL = limit, window, span, addrs
end

-- A login from the box itself: any address of 127.0.0.0/8 (a process on the
-- box can use any of them), ::1, their IPv4-mapped forms, every address of
-- the box's interfaces (setup and the cron job of auth_guard.py write them
-- as "local" lines, link-local ones included; their scope "%eth0" is
-- dropped here), and any connection whose source is its destination (a
-- process on the box that connects to one of the box's addresses). fail2ban
-- ignores all of these.
local function plain(ip)
	ip = string.lower(ip or "")
	ip = ip:gsub("%%.*$", "")
	local v4 = ip:match("^::ffff:(%d+%.%d+%.%d+%.%d+)$")
	return v4 or ip
end
function M.from_box(req)
	local ip = plain(req.remote_ip)
	return ip:match("^127%.%d+%.%d+%.%d+$") ~= nil or ip == "::1"
		or ip == "0:0:0:0:0:0:0:1" or M.LOCAL[ip] == true
		or (ip ~= "" and ip == plain(req.local_ip))
end

-- The list of accounts (management/auth_guard.py writes ACCOUNTS, one key
-- per line, root:dovecot 0640, whenever accounts change and every 10
-- minutes): the accounts on it are always counted; names that are not on
-- it share a pool of POOL (count.lua), so made-up names cannot crowd out
-- or flush the count of an account. Read again at most every 10 seconds. nil when the list is
-- missing: then every name is counted, at most MAX_NAMES at once.
M.ACCOUNTS = "/usr/local/lib/mailinabox/dovecot-auth-guard/accounts"
local accounts, accounts_time = nil, -1000
function M.accounts(now)
	if now - accounts_time < 10 then
		return accounts
	end
	accounts_time = now
	local f = io.open(M.ACCOUNTS, "r")
	if not f then
		accounts = nil
		return nil
	end
	local list = {}
	for line in f:lines() do
		if line:match("^[ah]%-") then
			list[line] = true
		end
	end
	f:close()
	accounts = list
	return list
end

-- 64-bit FNV-1a (Lua 5.4 integers wrap around).
local function fnv1a(s)
	local h = -3750763034362895579 -- 0xcbf29ce484222325
	for i = 1, #s do
		h = h ~ s:byte(i)
		h = h * 1099511628211
	end
	return h
end

-- The tag of a password: 16 bits of FNV-1a of salt .. password .. salt.
function M.tag(salt, password)
	return string.format("%04x", fnv1a(salt .. (password or "") .. salt) & 0xffff)
end

-- A random salt (/dev/urandom; the time and an address of this Lua state
-- if it cannot be read).
function M.salt()
	local f = io.open("/dev/urandom", "rb")
	if f then
		local s = f:read(16)
		f:close()
		if s and #s == 16 then
			return s
		end
	end
	return tostring(os.time()) .. tostring({}) .. tostring(os.clock())
end

-- The file name of an account name: "a-" and the lower-case name with
-- every byte other than a-z 0-9 @ . _ + - as %XX (no "/", no name that is
-- only dots), or "h-" and a hash for a long name. The same in
-- management/auth_guard.py.
function M.key(user)
	local u = string.lower(user or "")
	local e = u:gsub("[^a-z0-9@._+-]", function(c) return string.format("%%%02X", c:byte()) end)
	if #e <= 200 then
		return "a-" .. e
	end
	return "h-" .. string.format("%016x", fnv1a(u)) .. "-" .. #u
end

function M.path(key)
	return M.DIR .. "/" .. key
end

-- The lines of a name's file are kept for SPAN windows (4 unless the
-- control panel sets 1 to 4, see M.load). A burst of guesses at the same
-- moment is checked in parallel and can pass check.lua before the first
-- failure is recorded, so it can record more than LIMIT; such a burst then
-- counts against the following windows too: a name is refused while the
-- different wrong passwords of the last k windows reach k times LIMIT, for
-- k = 1 to SPAN. So over time only a little more than LIMIT per window
-- gets through: a burst that fills fewer than SPAN windows can be repeated
-- as soon as it leaves them (bursts of 100 at a LIMIT of 30: 100 every 3
-- windows, 33 a window); a lock after a normal attack (it stops
-- at LIMIT) still ends one window after it. Only wrong passwords count, a
-- right one never.

local function parse(line, now)
	local t, tag = line:match("^(%d+) (%x%x%x%x)$")
	t = tonumber(t)
	if t and now - t < M.SPAN * M.WINDOW and t <= now + 60 then
		return t, tag
	end
	return nil
end

-- The different tags of a name within WINDOW, whether tag is one of them
-- within the SPAN windows, the lines of its file, and whether the name is
-- refused (see above).
function M.recent(path, now, tag)
	local f = io.open(path, "r")
	if not f then
		return 0, false, 0, false
	end
	local first = {} -- tag -> its newest time
	local all, has = 0, false
	for line in f:lines() do
		all = all + 1
		local t, tg = parse(line, now)
		if t then
			if first[tg] == nil or t > first[tg] then
				first[tg] = t
			end
			if tg == tag then
				has = true
			end
		end
	end
	f:close()
	local counts = {}
	for k = 1, M.SPAN do
		counts[k] = 0
	end
	for _, t in pairs(first) do
		local age = now - t
		for k = 1, M.SPAN do
			if age < k * M.WINDOW then
				counts[k] = counts[k] + 1
			end
		end
	end
	local refused = false
	for k = 1, M.SPAN do
		if counts[k] >= k * M.LIMIT then
			refused = true
		end
	end
	return counts[1], has, all, refused
end

local function write_file(path, text)
	local tmp = path .. ".tmp"
	local f = io.open(tmp, "w")
	if not f then
		return false
	end
	local ok = f:write(text)
	f:close()
	if not ok then
		os.remove(tmp)
		return false
	end
	return os.rename(tmp, path) and true or false
end

-- Records a failed login of a name with the tag of its password; returns
-- the number of different tags within WINDOW, whether this one is new,
-- whether the name is refused now and whether it was before, or nil when
-- the state cannot be written.
function M.add(path, now, tag)
	-- A tag seen within the SPAN windows is not written again: it counts
	-- once.
	local n, has, all, refused = M.recent(path, now, tag)
	if has then
		return n, false, refused, refused
	end
	if all > 4 * M.SPAN_MAX * M.LIMIT + 20 then
		-- Drop the lines older than the SPAN windows.
		local keep, seen = {}, {}
		local f = io.open(path, "r")
		if f then
			for line in f:lines() do
				local t, tg = parse(line, now)
				if t and not seen[tg] then
					seen[tg] = true
					keep[#keep + 1] = line .. "\n"
				end
			end
			f:close()
		end
		if not write_file(path, table.concat(keep)) then
			return nil
		end
	end
	local a = io.open(path, "a")
	if not a then
		return nil
	end
	local ok = a:write(now, " ", tag, "\n")
	a:close()
	if not ok then
		return nil
	end
	local n2, _, _, refused2 = M.recent(path, now, tag)
	return n2, true, refused2, refused
end

-- count.lua's pool of names not on the list is full: a flag file with its
-- time, so that check.lua sees it. count.lua sets it when the pool fills
-- and removes it when pruning frees room, and removes a flag left behind
-- when it starts (its pool is empty then). A flag older than WINDOW does
-- not count (if count.lua could not remove it).
function M.pool_full(now)
	local f = io.open(M.path("pool-full"), "r")
	if not f then
		return false
	end
	local t = tonumber(f:read("l") or "")
	f:close()
	return t ~= nil and now - t < M.WINDOW and t <= now + 60
end

function M.set_pool_full(full, now)
	if full then
		write_file(M.path("pool-full"), tostring(now) .. "\n")
	else
		os.remove(M.path("pool-full"))
	end
end

-- An event for management/auth_guard.py: "<time> <kind> <count> <key>".
function M.event(now, kind, count, key)
	local f = io.open(M.path("events"), "a")
	if not f then
		return
	end
	if f:seek("end") < M.MAX_EVENTS then
		f:write(string.format("%d %s %d %s\n", now, kind, count, key))
	end
	f:close()
end

return M
