-- Mail-in-a-Box: the last passdb of setup/mail-users.sh, reached only when
-- the passdbs before it did not accept the login. For a login from the box
-- itself it records the failure for the account name with the tag of the
-- wrong password (guard.lua; a password sent again counts once) and
-- answers it at once, without Dovecot's delay and penalty; it can accept no
-- password (it returns none). Do not edit: setup writes it again on every
-- run.

local G = dofile("/usr/local/lib/mailinabox/dovecot-auth-guard/guard.lua")

local SALT = G.salt() -- for the tags of the wrong passwords, never written
local names, nnames = {}, 0 -- key -> { failures within the window, last time }
local warned_state, warned_full = false, false

-- When MAX_NAMES names are tracked: forget the names without a failure in
-- the window, then, if that is not enough, the tenth with the fewest
-- failures (made-up names have one or two). A name at the limit is never
-- dropped, so a lock cannot be flushed with made-up names.
local function make_room(now)
	for k, v in pairs(names) do
		if now - v[2] >= G.WINDOW then
			os.remove(G.path(k))
			names[k] = nil
			nnames = nnames - 1
		end
	end
	if nnames < G.MAX_NAMES then
		return
	end
	local list = {}
	for k, v in pairs(names) do
		if v[1] < G.LIMIT then
			list[#list + 1] = k
		end
	end
	table.sort(list, function(a, b)
		local x, y = names[a], names[b]
		if x[1] ~= y[1] then return x[1] < y[1] end
		return x[2] < y[2]
	end)
	for i = 1, math.min(#list, G.MAX_NAMES // 10) do
		os.remove(G.path(list[i]))
		names[list[i]] = nil
		nnames = nnames - 1
	end
end

function auth_passdb_lookup(req)
	if not G.from_box(req) then
		return dovecot.auth.PASSDB_RESULT_USER_UNKNOWN, "not from the box itself"
	end
	local now = os.time()
	local key = G.key(req.user)
	if names[key] == nil then
		if nnames >= G.MAX_NAMES then
			make_room(now)
			if not warned_full then
				G.event(now, "names", G.MAX_NAMES, "-")
				req:log_warning(string.format("miab-auth-guard: failed logins of more than %d account names from the box itself in %d s; the names with the fewest failures are forgotten", G.MAX_NAMES, G.WINDOW))
				warned_full = true
			end
		end
		if nnames >= G.MAX_NAMES then
			-- Every tracked name is at the limit: this one is answered at
			-- once but not counted (no global penalty either way).
			return dovecot.auth.PASSDB_RESULT_OK, { nodelay = "yes" }
		end
		names[key] = { 0, now }
		nnames = nnames + 1
	end
	local n, new = G.add(G.path(key), now, G.tag(SALT, req.password))
	if n == nil then
		-- Without its state the limit cannot work: Dovecot's delay and
		-- penalty, as before B126, never no limit.
		if not warned_state then
			req:log_error("miab-auth-guard: cannot write " .. G.DIR .. "; failed logins from the box itself get Dovecot's delay")
			warned_state = true
		end
		return dovecot.auth.PASSDB_RESULT_USER_UNKNOWN, "no state"
	end
	warned_state = false
	names[key] = { n, now }
	if new and n == G.LIMIT then
		G.event(now, "locked", n, key)
		req:log_warning(string.format("miab-auth-guard: %d different wrong passwords of this account from the box itself in %d s; logins from the box itself are refused for it until they are fewer", n, G.WINDOW))
	end
	-- No password: the login fails, at once.
	return dovecot.auth.PASSDB_RESULT_OK, { nodelay = "yes" }
end
