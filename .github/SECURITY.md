# Security policy of the Ubuntu 26.04 fork

This repository is an unofficial fork of Mail-in-a-Box for Ubuntu 26.04. It is
not maintained by the Mail-in-a-Box project.

## Supported versions

Only the latest release tag (currently `v78-r2604.0`, the first release) and
the branch `main` receive fixes. The release candidates (`v78-r2604.0-rc1` to
`-rc7`) are no longer supported: update them to the latest release.

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Report it privately through
[GitHub private vulnerability reporting](https://github.com/LM1337/Mail-in-a-box-26/security/advisories/new)
(the "Report a vulnerability" button on the Security tab), or by email to
[LM1337@networkx.eu](mailto:LM1337@networkx.eu). Please include the
release tag or commit, the Ubuntu release, and steps to reproduce. You get an
answer there; fixes are published as a new release tag with a note in
CHANGELOG-fork.md.

This covers the fork's own code and changes, for example
`tools/migrate-to-2604.sh`, `tools/upgrade-in-place-to-2604.sh`, the Dovecot
2.4 configuration and everything else listed in CHANGELOG-fork.md.

If the problem also exists in upstream Mail-in-a-Box v78 (Ubuntu 22.04),
please report it to the upstream project as well, as described in its
[security guide](../security.md). Do not send reports about the fork's own code
to the upstream maintainer.

Vulnerabilities in the programs that setup installs (Postfix, Dovecot,
Nextcloud, Roundcube, Z-Push and others) belong to those projects; tell us too
if the fork's configuration makes them worse.

## Threat model

The fork keeps upstream's security posture. It is described in
[security.md](../security.md) (written by upstream for Ubuntu 22.04; it also
applies to this fork unless CHANGELOG-fork.md says otherwise).
