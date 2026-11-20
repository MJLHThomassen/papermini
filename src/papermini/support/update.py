"""The constants of the standalone app's updates: the repository and its links, the
files of a release, the release key and the environment variables for trying updates.

``UpdateService`` checks GitHub for a newer release, downloads and verifies it in the
background, and installs it when the app closes. Every release has a ``SHA256SUMS.txt``
with the checksum of each download, signed by the release workflow with a private
Ed25519 key (``SHA256SUMS.txt.sig``). The app has the public key built in
(``PUBLIC_KEY``) and installs a download only when that signature and its checksum
match. Only the standalone app updates itself; run from source, papermini just reports a
newer version. A papermini installed with the Windows installer updates by running the
new version's installer silently; the other copies replace their folder (or
papermini.app) with the new archive's.

For trying updates locally (see scripts/fake_update.py), three environment variables
stand in for the real thing: PAPERMINI_UPDATE_FEED (a release description in GitHub's
format, as a file or a link), PAPERMINI_UPDATE_KEY (the public key to trust) and
PAPERMINI_UPDATE_INSTALL (a pretend installed papermini, so a run from source updates it).
"""

from __future__ import annotations

REPO = "MJLHThomassen/papermini"
GITHUB = f"https://github.com/{REPO}"
RELEASES = f"{GITHUB}/releases"
NEW_ISSUE = f"{GITHUB}/issues/new"
LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
CHECKSUMS = "SHA256SUMS.txt"
SIGNATURE = CHECKSUMS + ".sig"

# the release workflow's public signing key, base64 (scripts/release_key.py sets it)
PUBLIC_KEY = "1tcgNayNKgRQi2eWKy0RMuAC4vx9R/ovBGmproIi0AQ="
READY = "READY"  # marks a downloaded, verified and unpacked update

FEED_ENV, KEY_ENV, INSTALL_ENV = (
    "PAPERMINI_UPDATE_FEED",
    "PAPERMINI_UPDATE_KEY",
    "PAPERMINI_UPDATE_INSTALL",
)

# the installer's entry in Apps & features (per user; the AppId in packaging/papermini.iss)
SETUP_KEY = (
    r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
    r"\{8ABD2E9A-F789-4350-88F8-2565C60699F0}_is1"
)
