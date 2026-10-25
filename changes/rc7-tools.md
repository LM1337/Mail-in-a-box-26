# rc7 fragment: tools

Entries for CHANGELOG-fork.md ("## Unreleased") and BUGS-fork.md, to be
merged when rc7 is released. Bug IDs of this fragment: B90 (B91 to B94 not
used).

## CHANGELOG-fork.md

### New

* Tests: `tests/fork/log-audit.sh --baseline BEFORE.json` compares with the
  `--json` report of an earlier run: a class that was in it is listed as
  KNOWN, with both counts, and does not count; only new classes are
  UNKNOWN. `--internet` adds `tests/fork/log-audit-allow-internet.txt`, the
  usual noise of a box on the Internet (ufw blocks, SYN floods, password
  guessing on SSH, SMTP submission, Roundcube, Nextcloud and Z-Push, TLS and
  SSH errors of scanners and old clients, nginx 404s in the web roots, mail
  that Postfix rejects as spam, to unknown recipients or for relaying,
  greylisting, reverse DNS warnings, DNS and DNSSEC errors of other zones),
  each rule with its reason; only when asked, the test scenarios do not use
  it.

### Changed

* Tests: `tests/fork/log-audit.sh --since` also takes the short forms `-90s`,
  `-30m`, `-24h`, `-2d` and `-1w`; `date -d` fails on them ("-24h" reads the
  "h" as a time zone).

## BUGS-fork.md

No entries yet.
