# Contributing

Mail-in-a-Box is an open source project. Your contributions and pull requests are welcome.

## This fork (Ubuntu 26.04)

This repository is an unofficial fork of Mail-in-a-Box for Ubuntu 26.04. For changes to the fork:

* Clone https://github.com/LM1337/Mail-in-a-box-26 and send pull requests and issues to this repository, not to upstream.
* Fixes that also apply to upstream Mail-in-a-Box (Ubuntu 22.04) are welcome upstream as well, at https://github.com/mail-in-a-box/mailinabox.
* Describe user-visible changes in CHANGELOG-fork.md (section "Unreleased"), and bugs with symptom, cause and affected versions in BUGS-fork.md.
* Test on a fresh Ubuntu 26.04 machine or VM, and for the migration and in-place tools on a copy of a real box. `tests/fork/smoke.py` checks a box from outside (see its `--help`); `tests/fork/seed-legacy.sh` fills an old box with test data; `tests/fork/prepare-testenv.sh` adapts a test VM. Keep credentials and the addresses of your test network in an env file outside the repository (`MIAB_TEST_ENV`).
* The public domain dedication below (CC0) applies to all contributions to this fork as well.

### Versioning

Release tags have the form `v<upstream>-r<ubuntu>.<n>[-rc<m>]`, for example `v78-r2604.0-rc3`:

| Part | Meaning |
|---|---|
| `v78` | The upstream Mail-in-a-Box release the fork is based on. It is not a version number of its own: the fork never uses an upstream number that upstream has not released (no `v79` before upstream's v79). |
| `r2604` | The fork line for Ubuntu 26.04 (a line for Ubuntu 28.04 would be `r2804`). |
| `.0`, `.1`, … | The fork's own releases on that base. Every release counts up, whether it fixes bugs or adds features. |
| `-rc1`, `-rc2`, … | Release candidates before a release. |

When upstream publishes a new release and the fork takes it over, the base changes and the counter starts again: `v78-r2604.3` → `v79-r2604.0`.

Keep the `v<upstream>` prefix. The setup, migration and in-place tools compare Mail-in-a-Box versions numerically (for example "v68 or later"), and `git describe` must show which upstream code a box runs. A release is tagged with an annotated tag, `TAG=` in `setup/bootstrap.sh` and `DEFAULT_TAG` in `tools/migrate-to-2604.sh` and `tools/upgrade-in-place-to-2604.sh` are set to it in the same commit, and the GitHub release may carry a readable title such as "Mail-in-a-box-26 r2604.0 (based on Mail-in-a-Box v78)".

Boxes installed with rc1 to rc3 were cloned from the fork's previous home, and their status checks read the latest release from `setup/bootstrap.sh` on the branch `main` there. As long as such boxes exist, keep `main` of the previous home up to date with every release (at least the `TAG=` line of `setup/bootstrap.sh`), so that they report the new release; updating them needs the `git remote set-url` step described in README-fork.md ("Updating the fork").

The rest of this file is upstream's text, with the clone URL changed to this fork. The Vagrantfile already uses an Ubuntu 26.04 image.

## Development

To start developing this fork, [clone the repository](https://github.com/LM1337/Mail-in-a-box-26) and familiarize yourself with the code.

    $ git clone https://github.com/LM1337/Mail-in-a-box-26

### Vagrant and VirtualBox

We recommend you use [Vagrant](https://www.vagrantup.com/intro/getting-started/install.html) and [VirtualBox](https://www.virtualbox.org/wiki/Downloads) for development. Please install them first.

With Vagrant set up, the following should boot up Mail-in-a-Box inside a virtual machine:

    $ vagrant up --provision

_If you're seeing an error message about your *IP address being listed in the Spamhaus Block List*, simply uncomment the `export SKIP_NETWORK_CHECKS=1` line in `Vagrantfile`. It's normal, you're probably using a dynamic IP address assigned by your Internet provider–they're almost all listed._

### Modifying your `hosts` file

After a while, Mail-in-a-Box will be available at `192.168.56.4` (unless you changed that in your `Vagrantfile`). To be able to use the web-based bits, we recommend to add a hostname to your `hosts` file:

    $ echo "192.168.56.4 mailinabox.lan" | sudo tee -a /etc/hosts

You should now be able to navigate to https://mailinabox.lan/admin using your browser. There should be an initial admin user with the name `me@mailinabox.lan` and the password `12345678`.

### Making changes

Your working copy of Mail-in-a-Box will be mounted inside your VM at `/vagrant`. Any change you make locally will appear inside your VM automatically.

Running `vagrant up --provision` again will repeat the installation with your modifications.

Alternatively, you can also ssh into the VM using:

    $ vagrant ssh

Once inside the VM, you can re-run individual parts of the setup like in this example:

    vm$ cd /vagrant
    vm$ sudo setup/owncloud.sh # replace with script you'd like to re-run

### Tests

Mail-in-a-Box needs more tests. If you're still looking for a way to help out, writing and contributing tests would be a great start!

## Public domain

This project is in the public domain. Copyright and related rights in the work worldwide are waived through the [CC0 1.0 Universal public domain dedication][CC0]. See the LICENSE file in this directory.

All contributions to this project must be released under the same CC0 wavier. By submitting a pull request or patch, you are agreeing to comply with this waiver of copyright interest.

[CC0]: http://creativecommons.org/publicdomain/zero/1.0/

## Code of Conduct

This project has a [Code of Conduct](CODE_OF_CONDUCT.md). Please review it when joining our community.
