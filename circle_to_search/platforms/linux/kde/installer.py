#!/usr/bin/env python3
"""Install a self-contained user launcher using the current Python interpreter."""

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from ....models import DEFAULT_MODELS, model_manifest

DESKTOP_ID = "io.github.circle_to_search.desktop"
SOURCE = Path(__file__).resolve().parents[4]


def desktop_quote(value):
    # Desktop Exec has its own escaping, separate from shell quoting.
    value = str(value).replace("%", "%%")
    for char in ("\\", '"', "`", "$"):
        value = value.replace(char, "\\" + char)
    return '"' + value + '"'


def register_shortcut(shortcut):
    """Register the desktop launcher with the running KDE accelerator service."""
    try:
        import dbus
        from PySide6.QtGui import QKeySequence

        bus = dbus.SessionBus()
        proxy = bus.get_object("org.kde.kglobalaccel", "/kglobalaccel")
        accel = dbus.Interface(proxy, "org.kde.KGlobalAccel")
        action = dbus.Array(
            [DESKTOP_ID, "_launch", "Circle to Search", "Circle to Search"], signature="s"
        )
        current = accel.shortcut(action)
        if current:
            sequence = QKeySequence(int(current[0])).toString()
            print(f"Kept existing shortcut: {sequence}")
            return
        key = QKeySequence(shortcut)[0].toCombined()
        if not accel.isGlobalShortcutAvailable(dbus.Int32(key), DESKTOP_ID):
            print(
                f"{shortcut} is already assigned. Choose a shortcut in System Settings → Keyboard → Shortcuts."
            )
            return
        accel.doRegister(action)
        result = accel.setShortcut(action, dbus.Array([key], signature="i"), dbus.UInt32(2 | 4))
        if key not in result:
            raise RuntimeError("KDE did not accept the shortcut")
        print(f"Global shortcut registered: {shortcut}")
    except Exception as exc:
        print(
            f"Set a shortcut in System Settings → Keyboard → Shortcuts → Circle to Search ({exc})."
        )


def install(prefix=None, shortcut="Meta+Shift+G", models=DEFAULT_MODELS):
    from PySide6.QtCore import __version__ as qt_version

    print(f"Using Python {sys.version.split()[0]} and PySide6 {qt_version}")
    if prefix:
        prefix = Path(prefix).expanduser().resolve()
        data, binary = prefix / "share", prefix / "bin"
    else:
        data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
        binary = Path.home() / ".local/bin"
    target = data / "circle-to-search"
    target.mkdir(parents=True, exist_ok=True)
    for name in ("LICENSE", "THIRD_PARTY.md"):
        shutil.copyfile(SOURCE / name, target / name)
    # Installed package code and icons are managed files. Remove modules
    # deleted or moved in the source tree instead of accumulating old versions.
    # User settings, WebEngine data, downloaded models and server .env files
    # are outside these managed file sets and stay intact.
    for package in ("circle_to_search", "server/cts_ocr_server", "server/tests"):
        source = SOURCE / package
        destination = target / package
        for existing in destination.rglob("*.py"):
            if not (source / existing.relative_to(destination)).is_file():
                existing.unlink()
        for cache in destination.rglob("__pycache__"):
            shutil.rmtree(cache)
    icons = target / "circle_to_search/icons"
    for existing in icons.glob("*"):
        if existing.is_file() and not (SOURCE / "circle_to_search/icons" / existing.name).is_file():
            existing.unlink()
    shutil.copytree(
        SOURCE / "circle_to_search",
        target / "circle_to_search",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copytree(
        SOURCE / "server",
        target / "server",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".env*", ".venv", "models"),
    )
    from tools.fetch_models import fetch_models

    fetch_models(target / "circle_to_search/tessdata", models)
    binary.mkdir(parents=True, exist_ok=True)
    launcher = binary / "circle-to-search"
    launcher.write_text(
        "#!/bin/sh\n"
        + "exec "
        + shlex.quote(sys.executable)
        + " -c "
        + shlex.quote(
            "import sys; sys.path.insert(0, "
            + repr(str(target))
            + "); from circle_to_search.app import main; raise SystemExit(main())"
        )
        + ' "$@"\n'
    )
    launcher.chmod(0o755)
    icon = data / "icons/hicolor/scalable/apps/circle-to-search.svg"
    icon.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SOURCE / "assets/circle-to-search.svg", icon)
    desktop = data / "applications" / DESKTOP_ID
    desktop.parent.mkdir(parents=True, exist_ok=True)
    template = (SOURCE / "packaging/linux/kde/circle-to-search.desktop.in").read_text()
    desktop.write_text(template.replace("@LAUNCHER@", desktop_quote(launcher)))
    print(f"Installed launcher: {launcher}")
    print(f"Installed desktop entry: {desktop}")
    if not prefix:
        if models != DEFAULT_MODELS:
            from ....languages import set_selected_models

            set_selected_models(models)
        builder = shutil.which("kbuildsycoca6")
        if builder:
            subprocess.run([builder, "--noincremental"], check=False, timeout=30)
        register_shortcut(shortcut)
    return launcher


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prefix", type=Path, help="Stage files in this prefix without changing desktop settings"
    )
    parser.add_argument(
        "--shortcut",
        default="Meta+Shift+G",
        help="Default global shortcut (existing bindings are preserved)",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        choices=[item["name"] for item in model_manifest()["models"]],
        help="OCR models to install, for example --models eng pol ukr",
    )
    args = parser.parse_args()
    install(args.prefix, args.shortcut, tuple(args.models) if args.models else DEFAULT_MODELS)


if __name__ == "__main__":
    main()
