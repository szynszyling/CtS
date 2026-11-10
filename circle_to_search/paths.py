"""User-specific paths shared by desktop ports, independent of Qt app startup."""

from pathlib import Path

from PySide6.QtCore import QStandardPaths


def config_directory() -> Path:
    root = QStandardPaths.writableLocation(QStandardPaths.GenericConfigLocation)
    if not root:
        raise RuntimeError("The operating system did not provide a configuration directory.")
    return Path(root) / "circle-to-search"
