r"""Create the key pair that signs releases, for the app's automatic updates.

    python scripts/release_key.py [PRIVATE_KEY_FILE]

Writes the private key (base64) to PRIVATE_KEY_FILE, by default
~/.papermini-release-key, and puts the public key in src/papermini/update.py
(PUBLIC_KEY). Then store the private key as the repository secret
RELEASE_SIGNING_KEY, which the release workflow signs with:

    gh secret set RELEASE_SIGNING_KEY < ~/.papermini-release-key        # bash, zsh
    Get-Content -Raw "$HOME\.papermini-release-key" | gh secret set RELEASE_SIGNING_KEY  # PowerShell

Keep the private key file out of the repository and safe: whoever has it can sign
updates that every installed papermini accepts. Making a new key pair means that
versions with the old public key no longer update themselves.
"""

from __future__ import annotations

import argparse
import base64
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UPDATE_PY = ROOT / "src" / "papermini" / "update.py"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("private_key", nargs="?", type=Path,
                    default=Path.home() / ".papermini-release-key")
    ap.add_argument("--force", action="store_true", help="replace an existing key file")
    args = ap.parse_args()

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    if args.private_key.exists() and not args.force:
        sys.exit(f"{args.private_key} exists; pass --force to replace it (old versions of "
                 "papermini would then no longer accept updates)")
    key = Ed25519PrivateKey.generate()
    raw = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                            serialization.NoEncryption())
    pub = key.public_key().public_bytes(serialization.Encoding.Raw,
                                        serialization.PublicFormat.Raw)
    args.private_key.write_text(base64.b64encode(raw).decode() + "\n", encoding="utf-8")
    try:
        os.chmod(args.private_key, 0o600)  # (only you can read it, where supported)
    except OSError:
        pass
    text = UPDATE_PY.read_text(encoding="utf-8")
    new, n = re.subn(r'^PUBLIC_KEY = ".*"$', f'PUBLIC_KEY = "{base64.b64encode(pub).decode()}"',
                     text, count=1, flags=re.M)
    if n != 1:
        sys.exit(f"PUBLIC_KEY not found in {UPDATE_PY}")
    UPDATE_PY.write_text(new, encoding="utf-8", newline="\n")
    print(f"private key: {args.private_key}")
    print(f"public key:  written to {UPDATE_PY.relative_to(ROOT)}")
    print()
    print("Store the private key as the repository secret RELEASE_SIGNING_KEY:")
    if sys.platform == "win32":
        print(f'  Get-Content -Raw "{args.private_key}" | gh secret set RELEASE_SIGNING_KEY')
    else:
        print(f"  gh secret set RELEASE_SIGNING_KEY < '{args.private_key}'")


if __name__ == "__main__":
    main()
