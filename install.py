#!/usr/bin/env python3
"""Install the supported KDE Plasma desktop application."""

import sys


def main():
    if not sys.platform.startswith("linux"):
        raise SystemExit("The desktop installer currently supports Linux with KDE Plasma only.")
    from circle_to_search.platforms.linux.kde.installer import main as install_kde

    install_kde()


if __name__ == "__main__":
    main()
