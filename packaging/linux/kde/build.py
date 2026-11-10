"""Build the small, standalone KDE installer from tracked project files."""

import runpy
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ENTRY = """import importlib.util
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

if not sys.platform.startswith("linux"):
    raise SystemExit("This installer requires Linux with KDE Plasma.")
if sys.argv[1:] not in (["--help"], ["-h"]):
    missing = [module for module in ("PySide6", "dbus") if not importlib.util.find_spec(module)]
    if missing:
        raise SystemExit(
            "Install the KDE dependencies first: "
            "https://github.com/szynszyling/CtS/blob/main/docs/INSTALL.md"
        )
with tempfile.TemporaryDirectory(prefix="cts-kde-setup-") as directory:
    with zipfile.ZipFile(sys.argv[0]) as archive:
        archive.extractall(directory)
    raise SystemExit(subprocess.call(
        [sys.executable, str(Path(directory) / "install.py"), *sys.argv[1:]]
    ))
"""


def main():
    version = runpy.run_path(str(ROOT / "circle_to_search/__init__.py"))["__version__"]
    output = ROOT / "dist" / f"CtS-{version}-linux-kde-setup.pyz"
    output.parent.mkdir(exist_ok=True)
    tracked = subprocess.check_output(
        [
            "git", "ls-files", "-z", "--", "circle_to_search", "server", "assets",
            "install.py", "LICENSE", "THIRD_PARTY.md", "tools/__init__.py",
            "tools/fetch_models.py", "packaging/linux/kde/circle-to-search.desktop.in",
        ],
        cwd=ROOT,
    ).decode().split("\0")
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("__main__.py", ENTRY)
        for name in filter(None, tracked):
            if not name.endswith(".traineddata"):
                archive.write(ROOT / name, name)
    print(f"{output} ({output.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
