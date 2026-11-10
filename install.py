#!/usr/bin/env python3
"""Install Circle to Search for the current desktop platform."""

import sys


def main():
    if sys.platform == "win32":
        from circle_to_search.platforms.windows.installer import main as install_windows

        return install_windows()
    if not sys.platform.startswith("linux"):
        raise SystemExit("The desktop installer supports Windows and Linux with KDE Plasma.")
    from circle_to_search.platforms.linux.kde.installer import main as install_kde

    install_kde()


if __name__ == "__main__":
    main()
