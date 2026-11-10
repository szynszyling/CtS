# Install Circle to Search

The desktop app currently supports **Linux with KDE Plasma 6**. Windows and macOS editions are not ready yet.

## Arch Linux

1. Download this repository using **Code → Download ZIP**, or clone it if you use Git.
2. Extract it and open a terminal in the project folder.
3. Install the required software, then run the installer:

```sh
sudo pacman -S --needed pyside6 qt6-webengine qt6-svg spectacle tesseract layer-shell-qt python-dbus
python3 install.py
```

The installer uses your normal user account. Only the package-installation command needs `sudo`.

The first installation downloads verified English, Japanese and vertical Japanese recognition models. When it finishes, launch **Circle to Search** from your application menu or press **Meta + Shift + G**. Meta is usually the Windows/Super key on your keyboard.

## Other KDE Linux distributions

Use your distribution’s package manager to install:

- Python 3.10 or newer.
- PySide6 / Qt 6.8 or newer, including **Qt WebEngine** and **Qt SVG**.
- KDE Spectacle, Tesseract, LayerShellQt and Python D-Bus bindings.

Package names vary by distribution. Prefer the distribution’s matching Qt/PySide6 packages, then run `python3 install.py` from the project folder. Arch Linux is the currently tested desktop installation; other distributions may need additional setup.

## Update

Download the new version, or run this from an existing Git checkout:

```sh
git pull --ff-only
python3 install.py
```

Close an already-open CtS overlay and launch it again. The installer refreshes the app’s code and icons, removes obsolete Python modules, and keeps your saved settings, server token, browser session and existing shortcut.

## Troubleshooting

| Problem | What to try |
| --- | --- |
| The shortcut does nothing | Open **Circle to Search** from the application menu. Set its shortcut in **System Settings → Keyboard → Shortcuts**. Another application may already use the default shortcut. |
| The screen cannot be captured | Open Spectacle normally and check that it can take a screenshot. |
| A normal window-opening animation appears | Check that `layer-shell-qt` is installed and you are using a KDE Plasma Wayland session. |
| Text is not recognized | Open **⋮ → Text recognition** and check the selected backend. For vertical Japanese, enable **Vertical Japanese text**. |
| Results cannot load | Check the network connection. Complete any Google verification, or click **Open in browser**. |
| Results are blocked with HTTP 403 | Open them in your normal browser. Signing into the embedded browser does not guarantee that Google will remove the block. |
| The OCR server does not connect | Check its address, OCR token and **Check server connection** result. The GitHub registry token and OCR token are different. |

## Where the app keeps things

On the current Linux installation:

| Item | Location |
| --- | --- |
| App files | `~/.local/share/circle-to-search/` |
| Launcher | `~/.local/bin/circle-to-search` |
| OCR settings | `~/.config/circle-to-search/ocr.json` |
| Appearance preference | `~/.config/circle-to-search/appearance.conf` |

Custom XDG locations are respected. Browser data and cached files use Qt’s application data/cache locations. Updating the application does not clear that data.
