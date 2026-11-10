"""Read Plasma's actual window colors and watch its configuration files."""

import configparser
import os
from pathlib import Path

from PySide6.QtGui import QColor

from ...base import ThemeSource


def read_config(path):
    config = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        config.read(path, encoding="utf-8")
    except (OSError, configparser.Error, UnicodeError):
        pass
    return config


def background_color(config):
    raw = config.get("Colors:Window", "BackgroundNormal", fallback="").strip()
    if "," in raw:
        try:
            channels = [int(value) for value in raw.split(",")[:3]]
            if len(channels) == 3 and all(0 <= value <= 255 for value in channels):
                return QColor(*channels)
        except ValueError:
            pass
    color = QColor(raw)
    return color if color.isValid() else None


class PlasmaThemeSource(ThemeSource):
    label = "Plasma"

    def __init__(self, path=None, data_dirs=None):
        super().__init__()
        self.path = (
            Path(path)
            if path
            else Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "kdeglobals"
        )
        self.data_dirs = data_dirs

    @property
    def watch_paths(self):
        # Atomic replacements require watching the parent as well as the file.
        return self.path, self.path.parent

    def is_dark(self):
        config = read_config(self.path)
        color = background_color(config)
        if color is None:
            scheme = config.get("General", "ColorScheme", fallback="")
            if scheme and Path(scheme).name == scheme:
                directories = self.data_dirs
                if directories is None:
                    directories = [
                        Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
                    ]
                    directories += [
                        Path(p)
                        for p in os.environ.get(
                            "XDG_DATA_DIRS", "/usr/local/share:/usr/share"
                        ).split(":")
                        if p
                    ]
                for directory in directories:
                    color = background_color(
                        read_config(Path(directory) / "color-schemes" / (scheme + ".colors"))
                    )
                    if color is not None:
                        break
        return color is not None and color.lightnessF() < 0.5
