-- Mail-in-a-Box: the first passdb (deny = yes) of setup/mail-users.sh. It
-- refuses every login from the box itself for an account name with too many
-- failed logins from the box (guard.lua), before the password is checked,
-- at once and without Dovecot's penalty. Do not edit: setup writes it again.

local G = dofile("/usr/local/lib/mailinabox/dovecot-auth-guard/guard.lua")

function auth_passdb_lookup(req)
	-- A deny passdb refuses the login when it finds the user; "user unknown"
	-- goes on to the next passdb.
	if not G.from_box(req) then
		return dovecot.auth.PASSDB_RESULT_USER_UNKNOWN, "not from the box itself"
	end
	local now = os.time()
	local n = G.recent(G.path(G.key(req.user)), now)
	if n >= G.LIMIT then
		return dovecot.auth.PASSDB_RESULT_OK, {
			nodelay = "yes",
			reason = "Too many failed logins, try again later.",
		}
	end
	return dovecot.auth.PASSDB_RESULT_USER_UNKNOWN, "not limited"
end
