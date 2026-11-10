"""Select a desktop backend without importing another OS's native libraries."""

import sys

from .base import DesktopBackend, UnsupportedPlatform


def get_backend(platform_name: str | None = None) -> DesktopBackend:
    platform_name = platform_name or sys.platform
    if platform_name.startswith("linux"):
        from .linux.kde import KdeBackend

        return KdeBackend()
    raise UnsupportedPlatform(
        "The desktop app currently supports Linux with KDE Plasma. "
        "Windows and macOS ports are not available yet."
    )
