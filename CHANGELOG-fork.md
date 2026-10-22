# Changelog of the Ubuntu 26.04 fork

Changes of this fork compared with upstream Mail-in-a-Box v78. The fork is
upstream PR #2603 (Ubuntu 26.04 port) merged with v78, plus the fixes below.
See CHANGELOG.md for upstream's own history.

## Unreleased

### Fixes

* Bootstrap accepts Ubuntu 26.04 and installs from the fork.
* Dovecot: quota-status answers DUNNO, per-user quota comes from the userdb.
* Dovecot: `$STORAGE_ROOT` is expanded in `99-local-sieve.conf`.
* DNS: SSHFP records keep the IANA algorithm numbers.
* TLS: back to MIAB's `dh2048.pem`.

### Setup and supply chain

* `wget_verify` picks the hash algorithm by length (64 hex = SHA256,
  128 = SHA512, 40 = SHA1 kept for compatibility). Every active pin is now
  SHA256 and was checked against the upstream checksum where one is
  published (Nextcloud `.sha256`, GitHub release digest, roundcube.net).
* The Nextcloud upgrade chain starts at Nextcloud 26. Installs with
  Nextcloud 20-25 skip the migration with a message (they need PHP <= 8.1).
* packages.sury.org is pinned to what Ubuntu 26.04 lacks (php-common,
  php8.2, php8.2-*, php8.5-imap); its keyring is checked against key
  `15058500A0235D97F5D10063B188E2B695BD4743` and no longer trusted globally.
* The management venv is recreated when the system Python version changes.
* `ssl_certificates.py` uses the timezone-aware `not_valid_*_utc` properties.
* The html5_notifier icon is resolved through `rcmail.assets_path()` so it
  works with Roundcube 1.7's `public_html` docroot.

### Version updates

| Component | Old | New | SHA256 of the new artifact |
|---|---|---|---|
| Nextcloud (fresh install / final step) | 34.0.3 | 34.0.5 | `d077fdca3dc78ef60b5bbc51182f2a1737aa01e2044d6c23f4e7b72146f5239a` |
| Nextcloud chain step to 33 | 33.0.7 | 33.0.10 | `ff602a1f1ba202f2137f10eecd201d3e80c5d94fd17ab984c688fb1bcb290645` |
| Nextcloud chain step to 32 | 32.0.10 | 32.0.15 | `33e7adbe81c1ad0be61123a0fadc63ae2e392759f0c2557e008863eb69c6453d` |
| Nextcloud chain step to 31 | 31.0.14 | 31.0.14 (re-pinned) | `6f34d623f7c24c5ecb3c165083ddb5d6a10186dbc2fa73a23efda26ec92091a7` |
| Nextcloud chain step to 30 | 30.0.17 | 30.0.17 (re-pinned) | `da51e17762785a36c1cf3fe2dc96cb356870695e384485e5980395493c15caf9` |
| Nextcloud chain step to 29 | 29.0.16 | 29.0.16 (re-pinned) | `6221c764b63369be6122bc414ee26a25bd9ce466f7d9ab29cd5ddb0c124c8eeb` |
| Nextcloud chain step to 28 | 28.0.14 | 28.0.14 (re-pinned) | `593f174f5098c793fb0314fd5847d891ed4e4db908ceba0d4e571544ac855c2d` |
| Nextcloud chain step to 27 | 27.1.11 | 27.1.11 (re-pinned) | `ffbfd9857bcaaacaea97d709063b7d81132feb41051063ab6c171c95c6daf142` |
| Nextcloud chain steps to 21-26 | 21.0.7 ... 26.0.13 | removed | - |
| contacts (fresh install, steps to 33/34) | 8.8.0 | 8.9.2 | `92f7c79c411273045ed6346f6988c05af673c3170a3adaba91a15066b8dce7c5` |
| contacts (step to 32) | 8.3.19 | 8.3.21 | `45d12ff526515ce5efc52d8e0d42bd3446a66b9a423ee4eb92ebd44a6b5974c3` |
| contacts (steps to 30/31) | 7.3.19 | 7.3.19 (re-pinned) | `568472420cf212ceeb1dccc044c0bdaa83504ef15251a2c6e39b22b6064a3ab8` |
| contacts (step to 29) | 6.0.7 | 6.0.7 (re-pinned) | `29b4942b9b224dcb7e7528fafb6a6094e45593e893dff61e519c34b19bed29a6` |
| contacts (steps to 27/28) | 5.5.4 | 5.5.4 (re-pinned) | `178aa6ec0b06d6bd72ff8eb87ac32ff267e97ccd93246b1eae1b5bb5263a61b0` |
| calendar (fresh install, steps to 32/33/34) | 6.5.4 | 6.6.3 | `bda8f38c609b2182533887f67eacb543edf437066d0356912ac6324c94743080` |
| calendar (steps to 30/31) | 5.5.23 | 5.5.24 | `9a4e1b869aa478317363cb0876a5d128aa584e427216d2cbfb808215f5c296a8` |
| calendar (steps to 27-29) | 4.7.20 | 4.7.20 (re-pinned) | `f62b43853dfc1fc971b4ffe5992cedc499e8ed7dc118265cfdfe8c1531d4a912` |
| user_external (fresh install, steps to 31-34) | 4.0.0 | 4.0.0 (re-pinned) | `f1f98c577bd02177fe74e9199f8e50d0c288ffa94bb50a227101a5ba0633c529` |
| user_external (steps to 27-30) | 3.4.0 | 3.4.0 (re-pinned) | `5a7fbed5da3cbe335f753027b662179c92c17fb37babc875e9e285d8a13d47f3` |
| Roundcube | 1.7.5 | 1.7.5 (re-pinned) | `93a66c94e3efff7db93187c1c9d7f35546647a3e1e7b9327cc87911564edf9d1` |
| Roundcube plugin rcmcarddav | 5.1.3 | 5.1.4 | `0ffa55ec6da5671d6c413a27d2511e903cd4e63de03c3e9480038844fa4625eb` |
| Roundcube plugin html5_notifier | git 68d9ca1 (kitist URL) | git 5d85947 (stremlau URL) | git commit pin |
| Z-Push | 2.7.7 | 2.7.7 (re-pinned) | `7a8e0094adf216521ee491078f78e709cd68257d05a868b3992d5665c01d8790` |
| jQuery (admin panel) | 2.2.4 | 3.7.1 | `fc9a93dd241f6b045cbff0481cf4e1901becd0e12fb45166a8f17f95823f0b1a` |
| Bootstrap (admin panel) | 3.4.1 | 3.4.1 (re-pinned) | `d49793cf773cbd393ac2cf340c3b4ddab5365fa7c292098ac07e12eab3efd92e` |
| pip: cryptography | ==37.0.2 | >=50.0.2,<51 (50.0.2) | wheel cp311-abi3-manylinux_2_34_x86_64 `9dab55f57c74c3cad24c323bacbbd04be4705ba6eb0d92e920b1fc4837ed5079` |
| pip: email_validator | >=1.0.0 | >=2.3.0,<3 (2.3.0) | `80f13f623413e6b197ae73bb10bf4eb0908faf509ad8362c5edeb0be7fd450b4` |
| pip: idna | >=2.0.0 | >=3.20 (3.20) | `ab7ae7122974553370f0bdb919e1a960b2cd1bc1ef0276416d896db81c14582c` |
| pip: b2sdk | unbounded | >=2.13 (2.13.2) | `f2d7663392d869c17d44b7304bae6e06ecefda18742b197a693a93298943310d` |
| pip: boto3 | unbounded | >=1.43 (1.43.118) | `ab8f3d2c622ef039338b4f228d97ea55f1abd573d84bb9b9a5ee8cb6780c0ccd` |
| sury keyring (debsuryorg-archive-keyring) | 2025.11.18, unchecked | 2025.11.18, key fingerprint checked | `.deb` `7511384559c9ddf1d5ce5f60be429ae9d4e7d01d9480d6f1b7a30c0810cf8b60` (not pinned, rotates in place) |
| Docs tool: Bootstrap (readable_bash.py) | 3.2.0 | 3.4.1 | SRI sha384 in the page |
| Docs tool: jQuery (readable_bash.py) | 1.10.1 | 3.7.1 | SRI sha384 in the page |
| Test tooling: dnspython | dnspython3 (1.15.0) | >=2.9,<3 (2.9.0) | `9a4aedb833c3c1b49214d04d44d3032ab7a9135f7c1d29a549b4ff78fd82fda9` |
| API docs: renderer | redoc-cli (0.13.21) | @redocly/cli 2.69.0 | npm integrity `sha512-un2CnJ+2OO82wArjuH132mD9lHs2oNJL8DtX50aCt6YrFTWIMWywCBRgxjznHdJ1lJAgck1giQgMc6yUL4kD0A==` |

Unchanged because they are already the newest compatible release:
Bootstrap 3.4.1 (final 3.x; 5.x needs an admin template rewrite),
persistent_login 5.3.0, Z-Push 2.7.7, Roundcube 1.7.5, Nextcloud 27.1.11,
28.0.14, 29.0.16, 30.0.17 and 31.0.14 (last patch of each major).
Nextcloud stays on 34: user_external has no release for Nextcloud 35 yet.
