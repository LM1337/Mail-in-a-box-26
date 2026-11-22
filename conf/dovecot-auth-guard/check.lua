-- Mail-in-a-Box: the first passdb (deny = yes) of setup/mail-users.sh. It
-- refuses every login from the box itself for an account name with too many
-- different wrong passwords from the box (guard.lua), before the password is
-- checked, at once and without Dovecot's penalty. Only wrong passwords
-- count; a login with the right password never does. Do not edit: setup
-- writes it again.

local G = dofile("/usr/local/lib/mailinabox/dovecot-auth-guard/guard.lua")

function auth_passdb_lookup(req)
	-- A deny passdb refuses the login when it finds the user; "user unknown"
	-- goes on to the next passdb.
	if not G.from_box(req) then
		return dovecot.auth.PASSDB_RESULT_USER_UNKNOWN, "not from the box itself"
	end
	G.load()
	local now = os.time()
	local key = G.key(req.user)
	local path = G.path(key)
	local n, _, _, refused = G.recent(path, now)
	if refused then
		return dovecot.auth.PASSDB_RESULT_OK, {
			nodelay = "yes",
			reason = "Too many failed logins, try again later.",
		}
	end
	-- count.lua counts a name that is not on the list of accounts in a pool
	-- of its own; when the pool is full, it cannot count a new one, so such
	-- a name is refused here while the pool is full (an account added while
	-- the list could not be written waits for the next list, at most 10
	-- minutes).
	local accounts = G.accounts(now)
	if accounts and not accounts[key] and n == 0 and G.pool_full(now) then
		return dovecot.auth.PASSDB_RESULT_OK, {
			nodelay = "yes",
			reason = "Too many failed logins, try again later.",
		}
	end
	return dovecot.auth.PASSDB_RESULT_USER_UNKNOWN, "not limited"
end
