"""Select a desktop backend without importing another OS's native libraries."""

import sys

from .base import DesktopBackend, UnsupportedPlatform


def get_backend(platform_name: str | None = None) -> DesktopBackend:
    platform_name = platform_name or sys.platform
    if platform_name.startswith("linux"):
        from .linux.kde import KdeBackend

        return KdeBackend()
    if platform_name == "win32":
        from .windows import WindowsBackend

        return WindowsBackend()
    raise UnsupportedPlatform(
        "The desktop app supports Windows and Linux with KDE Plasma. "
        "The macOS port is not available yet."
    )
