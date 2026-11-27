# Security policy

The standalone papermini updates itself. It downloads new releases from this
repository and installs any download whose checksum list is signed with the
release key. The update path is what this policy cares about most, but report
any security problem you find in papermini.

## Reporting a vulnerability

Report it privately, not in a public issue. Open the repository's
[Security tab](https://github.com/MJLHThomassen/papermini/security) and click
**Report a vulnerability**. This opens a private security advisory that only you
and the maintainer can see.

Say what the problem is, which version of papermini you used, and how to
reproduce it.

What happens next:

- The maintainer replies in the advisory and works out the fix with you there.
- The fix comes out in a new release. Standalone copies of papermini pick it up
  through their automatic update.
- Once the release is out, the advisory is published, crediting you unless you
  ask not to be named.

## Supported versions

Only the latest release gets security fixes. A fix comes out as a new release,
not as a patch for an older version.

## If the release key leaks

The private release key is the repository secret `RELEASE_SIGNING_KEY`. Whoever
has it can sign an update that every installed papermini accepts. If it leaks,
the maintainer:

1. Makes a new key pair with `just release-key --force` (`scripts/release_key.py`).
   This writes the new public key into `src/papermini/support/update.py`.
2. Merges that change into `main`.
3. Replaces the secret `RELEASE_SIGNING_KEY` with the new private key. The
   release workflow stops when the secret does not belong to the public key in
   the code.
4. Releases a new version, and publishes a security advisory that explains what
   happened.

Copies of papermini that have the old public key no longer update themselves:
they refuse the new release because its signature does not match. Users of those
copies download the new version once by hand from the
[releases page](https://github.com/MJLHThomassen/papermini/releases/latest).
After that, the updates work as before.
