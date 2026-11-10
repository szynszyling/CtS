# KDE Plasma desktop packaging

The supported desktop installer is `python3 install.py` at the repository root. Its implementation is in `circle_to_search/platforms/linux/kde/installer.py`.

This directory contains the Linux desktop-entry template. The shared application icon is in `assets/`. Generated launchers, downloaded models and build outputs do not belong here.

Future Linux package definitions should reuse the shared Python application and this desktop metadata, with distribution-specific dependencies documented explicitly.
