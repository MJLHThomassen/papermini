"""Sign a release's checksum file for the app's automatic updates.

    RELEASE_SIGNING_KEY=... python scripts/sign_release.py out/SHA256SUMS.txt

Writes FILE.sig: the base64 Ed25519 signature of FILE, made with the private key in
the environment variable RELEASE_SIGNING_KEY (see scripts/release_key.py). The app
checks it with the public key in src/papermini/update.py before installing an update,
so this script checks the new signature with that key too, and fails when the secret
does not belong to it (a release the app would refuse to install).
"""

from __future__ import annotations

import argparse
import base64
import os
import re
import sys
from pathlib import Path

UPDATE_PY = Path(__file__).resolve().parent.parent / "src" / "papermini" / "update.py"


def sign(data: bytes, private_key_b64: str) -> bytes:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(private_key_b64.strip()))
    return base64.b64encode(key.sign(data))


def app_public_key() -> str:
    """The public key built into the app (PUBLIC_KEY in src/papermini/update.py)."""
    m = re.search(r'^PUBLIC_KEY = "(.*)"$', UPDATE_PY.read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else ""


def check(data: bytes, signature: bytes, public_key_b64: str) -> bool:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64)).verify(
            base64.b64decode(signature), data)
        return True
    except (InvalidSignature, ValueError):
        return False


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("file", type=Path)
    args = ap.parse_args()
    key = os.environ.get("RELEASE_SIGNING_KEY", "")
    if not key.strip():
        sys.exit("RELEASE_SIGNING_KEY is not set: add the repository secret "
                 "(see scripts/release_key.py)")
    data = args.file.read_bytes()
    signature = sign(data, key)
    public = app_public_key()
    if not public:
        sys.exit(f"no PUBLIC_KEY in {UPDATE_PY}: run scripts/release_key.py first")
    if not check(data, signature, public):
        sys.exit("RELEASE_SIGNING_KEY does not belong to the public key in "
                 f"{UPDATE_PY.name}: the app would refuse this release's updates")
    out = args.file.with_name(args.file.name + ".sig")
    out.write_bytes(signature + b"\n")
    print(f"wrote {out} (checked with the app's public key)")


if __name__ == "__main__":
    main()
