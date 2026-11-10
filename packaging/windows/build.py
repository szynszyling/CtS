"""Build a versioned, portable Windows x64 release with PyInstaller."""

import importlib.metadata
import os
import shutil
import sys
import sysconfig
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from circle_to_search import __version__
from tools.fetch_models import fetch_models as fetch_tesseract


def copy_notices(bundle):
    for name in ("LICENSE", "THIRD_PARTY.md"):
        shutil.copyfile(ROOT / name, bundle / name)
    for name in ("LICENSE", "THIRD_PARTY.md", "licenses/Apache-2.0.txt"):
        target = bundle / "server" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "server" / name, target)
    shutil.copyfile(ROOT / "packaging/windows/README.md", bundle / "README.md")
    for distribution in importlib.metadata.distributions():
        for entry in distribution.files or ():
            parts = Path(entry).parts
            if not parts or not parts[0].endswith(".dist-info") or len(parts) < 2:
                continue
            if "licenses" not in parts[1:] and not parts[-1].upper().startswith(
                ("LICENSE", "NOTICE", "COPYING")
            ):
                continue
            source = distribution.locate_file(entry)
            if source.is_file():
                target = bundle / "licenses" / Path(*parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
    qt = bundle / "licenses/Qt"
    qt.mkdir(parents=True, exist_ok=True)
    for name in ("lgpl-3.0", "gpl-3.0"):
        with urlopen(f"https://www.gnu.org/licenses/{name}.txt", timeout=30) as response:
            (qt / (name + ".txt")).write_bytes(response.read())
    version = importlib.metadata.version("PySide6")
    (qt / "SOURCE.txt").write_text(
        f"Qt/PySide6 {version} is supplied as replaceable shared libraries under its upstream LGPLv3/GPL terms.\n"
        "Qt sources: https://download.qt.io/official_releases/qt/\n"
        f"PySide6 sources: https://code.qt.io/cgit/pyside/pyside-setup.git/tag/?h=v{version}\n"
        "Qt WebEngine notices: https://doc.qt.io/qt-6/qtwebengine-licensing.html\n",
        encoding="utf-8",
    )


def main():
    if sys.platform != "win32" or sysconfig.get_platform() != "win-amd64":
        raise SystemExit("Build the Windows x64 bundle with 64-bit Python on Windows.")
    import PyInstaller.__main__
    from cts_ocr_server.engine import fetch_models as fetch_vulkan

    out = ROOT / "dist"
    work = ROOT / "build/windows"
    work.mkdir(parents=True, exist_ok=True)
    fetch_tesseract()
    models = fetch_vulkan(work / "ocr-models")
    name = "Circle to Search"
    bundle = out / name
    if out.resolve().parent != ROOT or bundle.resolve().parent != out.resolve():
        raise RuntimeError("The Windows build output points outside the repository.")
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    icon = work / "CircleToSearch.ico"
    image = QImage(256, 256, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    QSvgRenderer(str(ROOT / "assets/circle-to-search.svg")).render(painter)
    painter.end()
    if not image.save(str(icon), "ICO"):
        raise RuntimeError("Could not build the Windows application icon.")
    data = [
        (ROOT / "circle_to_search/icons", "circle_to_search/icons"),
        (ROOT / "circle_to_search/tessdata", "circle_to_search/tessdata"),
        (models, "ocr-models"),
    ]
    arguments = [
        "--noconfirm",
        "--windowed",
        "--onedir",
        "--name",
        name,
        "--distpath",
        str(out),
        "--workpath",
        str(work / "pyinstaller"),
        "--specpath",
        str(work),
        "--paths",
        str(ROOT),
        "--noupx",
        "--icon",
        str(icon),
        "--collect-data",
        "cts_ocr_server",
        "--collect-submodules",
        "uvicorn",
        "--copy-metadata",
        "circle-to-search-ocr-server",
        "--copy-metadata",
        "ncnn",
    ]
    for source, destination in data:
        arguments.extend(["--add-data", f"{source}{os.pathsep}{destination}"])
    PyInstaller.__main__.run([*arguments, str(Path(__file__).with_name("entry.py"))])
    copy_notices(bundle)
    stem = f"CtS-{__version__}-windows-x64"
    archive = Path(shutil.make_archive(str(out / stem), "zip", root_dir=out, base_dir=name))
    installed = sum(path.stat().st_size for path in bundle.rglob("*") if path.is_file())
    print(
        f"Built {archive.name}: {archive.stat().st_size / 1e6:.1f} MB download, {installed / 1e6:.1f} MB extracted."
    )


if __name__ == "__main__":
    main()
