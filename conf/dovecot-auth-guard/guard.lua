-- Mail-in-a-Box: a limit of failed logins per account for the logins that
-- come from the box itself (127.0.0.1 and ::1: Z-Push's ActiveSync and
-- Autodiscover, Roundcube, Nextcloud's IMAP login, and anything else that
-- runs on the box). setup/mail-users.sh installs this file in
-- /usr/local/lib/mailinabox/dovecot-auth-guard/, with check.lua and
-- count.lua, the two passdbs that use it. Do not edit: setup writes it again on every run.
--
-- count.lua (the last passdb, reached only by a failed login) answers a
-- failed login from the box at once, without Dovecot's delay and penalty
-- (B126: the penalty belongs to the address 127.0.0.1, so it slowed down
-- the logins of all users of these services), and records it for the
-- account name. check.lua (the first passdb, deny = yes) refuses every
-- login from the box for a name with LIMIT failed logins within WINDOW
-- seconds, before the password is checked: guesses stop telling right from
-- wrong, and nothing raises the penalty of 127.0.0.1, so the other accounts
-- are not slowed down. Only the failures of the name itself count: made-up
-- names cannot lower the limit of a real account. Logins from other
-- addresses are left to Dovecot as before.
--
-- The state is in DIR (tmpfs, 0700, the account dovecot: the auth process
-- runs as dovecot, /etc/tmpfiles.d/miab-auth-guard.conf creates it), so
-- that both passdbs see it (each passdb has a Lua state of its own) and no
-- other account can change it. A file per name, one line per failed login
-- (its time). count.lua tracks at most MAX_NAMES names; beyond that it drops
-- the names with the fewest failures (made-up names have one), never a
-- locked one. management/auth_guard.py
-- reads it, removes the files of names without failures in the window and
-- mails the events. If the state cannot be written, failed logins get
-- Dovecot's delay and penalty again (as before B126), never no limit.

local M = {}

M.DIR = "/run/miab-auth-guard"
M.WINDOW = 1800      -- seconds
M.LIMIT = 100        -- failed logins of one name within WINDOW
M.MAX_NAMES = 10000  -- names that count.lua tracks at once
M.MAX_EVENTS = 1048576 -- bytes of the events file

function M.from_box(req)
	local ip = req.remote_ip
	return ip == "127.0.0.1" or ip == "::1"
end

-- 64-bit FNV-1a (Lua 5.4 integers wrap around), for names too long to be
-- a file name when escaped.
local function fnv1a(s)
	local h = -3750763034362895579 -- 0xcbf29ce484222325
	for i = 1, #s do
		h = h ~ s:byte(i)
		h = h * 1099511628211
	end
	return string.format("%016x", h)
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
	return "h-" .. fnv1a(u) .. "-" .. #u
end

function M.path(key)
	return M.DIR .. "/" .. key
end

-- Failed logins of a name within WINDOW, and the lines of its file.
function M.recent(path, now)
	local f = io.open(path, "r")
	if not f then
		return 0, 0
	end
	local n, all = 0, 0
	for line in f:lines() do
		all = all + 1
		local t = tonumber(line)
		if t and now - t < M.WINDOW and t <= now + 60 then
			n = n + 1
		end
	end
	f:close()
	return n, all
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

-- Records a failed login of a name; returns its failed logins within
-- WINDOW, or nil when the state cannot be written.
function M.add(path, now)
	local n, all = M.recent(path, now)
	if all - n > 20 then
		-- Drop the old lines.
		local keep = {}
		local f = io.open(path, "r")
		if f then
			for line in f:lines() do
				local t = tonumber(line)
				if t and now - t < M.WINDOW and t <= now + 60 then
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
	local ok = a:write(now, "\n")
	a:close()
	if not ok then
		return nil
	end
	return n + 1
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
