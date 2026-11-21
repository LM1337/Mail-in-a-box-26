-- Mail-in-a-Box: the last passdb of setup/mail-users.sh, reached only when
-- the passdbs before it did not accept the login. For a login from the box
-- itself it records the failure of a real account (guard.lua's list of
-- accounts) with the tag of the wrong password (a password sent again
-- counts once), and answers it at once, without Dovecot's delay and
-- penalty; it can accept no password (it returns none). A name that is not
-- on the list of accounts is counted in a small pool of its own (see
-- below), so made-up names cannot crowd out the accounts.
-- Do not edit: setup writes it again on every run.

local G = dofile("/usr/local/lib/mailinabox/dovecot-auth-guard/guard.lua")

local SALT = G.salt() -- for the tags of the wrong passwords, never written
-- Only without the list of accounts: the names counted (key -> time of the
-- last failure), at most MAX_NAMES; a name is forgotten only when it had no
-- failure in the window, never to make room.
local names, nnames = {}, 0
local warned_state, warned_full, warned_list = false, false, false

local pool, npool = {}, 0 -- names not on the list (key -> time of the last failure)

local function prune_pool(now)
	for k, t in pairs(pool) do
		if now - t >= G.WINDOW then
			os.remove(G.path(k))
			pool[k] = nil
			npool = npool - 1
		end
	end
end

local function prune(now)
	for k, t in pairs(names) do
		if now - t >= G.WINDOW then
			os.remove(G.path(k))
			names[k] = nil
			nnames = nnames - 1
		end
	end
end

function auth_passdb_lookup(req)
	if not G.from_box(req) then
		return dovecot.auth.PASSDB_RESULT_USER_UNKNOWN, "not from the box itself"
	end
	G.load()
	local now = os.time()
	local key = G.key(req.user)
	local accounts = G.accounts(now)
	if accounts then
		warned_list = false
		if not accounts[key] then
			-- Not on the list: most likely a made-up name, but it may be an
			-- account added since the list was written (if writing it
			-- failed). Counted in a pool of its own (POOL names, forgotten
			-- only without failures in the window), which cannot touch the
			-- accounts on the list; when the pool is full, answered at once
			-- and not counted (no penalty for the others either).
			if pool[key] == nil then
				if npool >= G.POOL then
					prune_pool(now)
				end
				if npool >= G.POOL then
					return dovecot.auth.PASSDB_RESULT_OK, { nodelay = "yes" }
				end
				npool = npool + 1
			end
			pool[key] = now
		end
	else
		if not warned_list then
			req:log_warning("miab-auth-guard: no list of accounts (" .. G.ACCOUNTS .. "); every name is counted, at most " .. G.MAX_NAMES)
			warned_list = true
		end
		if names[key] == nil then
			if nnames >= G.MAX_NAMES then
				prune(now)
			end
			if nnames >= G.MAX_NAMES then
				-- No room: Dovecot's delay and penalty (as before B126),
				-- never no limit and never a lock forgotten.
				if not warned_full then
					req:log_warning(string.format("miab-auth-guard: failed logins of more than %d names from the box itself in %d s; new names get Dovecot's delay", G.MAX_NAMES, G.WINDOW))
					warned_full = true
				end
				return dovecot.auth.PASSDB_RESULT_USER_UNKNOWN, "no room"
			end
			nnames = nnames + 1
			warned_full = false
		end
		names[key] = now
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
	if new and n == G.LIMIT then
		G.event(now, "locked", n, key)
		req:log_warning(string.format("miab-auth-guard: %d different wrong passwords of this account from the box itself in %d s; logins from the box itself are refused for it until they are fewer", n, G.WINDOW))
	end
	-- No password: the login fails, at once.
	return dovecot.auth.PASSDB_RESULT_OK, { nodelay = "yes" }
end
