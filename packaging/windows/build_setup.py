"""Build a small Windows installer for an existing portable release ZIP."""

import argparse
import hashlib
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, help="The versioned Windows release ZIP")
    parser.add_argument("--compiler", default="ISCC.exe", help="Path to the Inno Setup compiler")
    args = parser.parse_args()
    bundle = args.bundle.resolve()
    prefix, suffix = "CtS-", "-windows-x64.zip"
    version = bundle.name.removeprefix(prefix).removesuffix(suffix)
    if (
        bundle.name != prefix + version + suffix
        or len(version.split(".")) != 3
        or not all(part.isascii() and part.isdecimal() for part in version.split("."))
    ):
        parser.error("Expected a bundle named CtS-X.Y.Z-windows-x64.zip.")
    digest = hashlib.sha256()
    with bundle.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    subprocess.run(
        [
            args.compiler,
            f"/DAppVersion={version}",
            f"/DBundleHash={digest.hexdigest()}",
            f"/O{bundle.parent}",
            str(Path(__file__).with_name("setup.iss")),
        ],
        check=True,
    )


if __name__ == "__main__":
    main()
