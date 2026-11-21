-- Mail-in-a-Box: the first passdb (deny = yes) of setup/mail-users.sh. It
-- refuses every login from the box itself for an account name with too many
-- different wrong passwords from the box (guard.lua), before the password is
-- checked, at once and without Dovecot's penalty. Do not edit: setup writes
-- it again.
--
-- The passwords are checked in Dovecot's auth workers, in parallel, and a
-- failure is recorded only after its check (count.lua): many logins of one
-- name at the same moment would all pass here before the first failure is
-- recorded. So the logins that this passdb let through for a name within
-- the last second, less the failures recorded in that second, count as
-- well: a name is refused when its recorded wrong passwords and those
-- logins reach the limit (with no wrong password recorded, a name may log
-- in 30 times a second at the default limit).

local G = dofile("/usr/local/lib/mailinabox/dovecot-auth-guard/guard.lua")

local passed, npassed = {}, 0 -- key -> times (seconds) of the logins let through

local function prune(now)
	for k, list in pairs(passed) do
		if list[#list] < now - 1 then
			passed[k] = nil
			npassed = npassed - 1
		end
	end
end

function auth_passdb_lookup(req)
	-- A deny passdb refuses the login when it finds the user; "user unknown"
	-- goes on to the next passdb.
	if not G.from_box(req) then
		return dovecot.auth.PASSDB_RESULT_USER_UNKNOWN, "not from the box itself"
	end
	G.load()
	local now = os.time()
	local key = G.key(req.user)
	local n, _, _, fresh = G.recent(G.path(key), now)
	local list = passed[key]
	local inflight = 0
	if list then
		for _, t in ipairs(list) do
			if t >= now - 1 then
				inflight = inflight + 1
			end
		end
	end
	-- Logins let through in the last second whose failure is recorded by
	-- now are in n already.
	inflight = math.max(0, inflight - fresh)
	if n >= G.LIMIT or n + inflight >= G.LIMIT then
		return dovecot.auth.PASSDB_RESULT_OK, {
			nodelay = "yes",
			reason = "Too many failed logins, try again later.",
		}
	end
	if list == nil then
		if npassed > 10000 then
			prune(now)
		end
		list = {}
		passed[key] = list
		npassed = npassed + 1
	end
	-- Keep only the last second.
	local keep = {}
	for _, t in ipairs(list) do
		if t >= now - 1 then
			keep[#keep + 1] = t
		end
	end
	keep[#keep + 1] = now
	passed[key] = keep
	return dovecot.auth.PASSDB_RESULT_USER_UNKNOWN, "not limited"
end
