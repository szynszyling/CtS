# Development and repository layout

## Layout

```text
compose.yaml                    Standalone production deployment; image only
circle_to_search/                Shared Qt UI, gestures, OCR clients and search
  platforms/
    base.py                     DesktopBackend and ThemeSource contracts
    linux/
      kde/                      Spectacle, LayerShellQt, Plasma and installer
      ocr.py                    Linux Docker/Vulkan container management
assets/                         Shared application artwork
packaging/
  linux/kde/                    Desktop-entry template and packaging notes
  windows/                      Windows port/release checklist
  macos/                        macOS port/release checklist
server/                         Independent, Qt-free Docker OCR service
tests/                          Desktop and shared-code regression tests
tools/
  smoke/                        Native UI, browser and container checks
  benchmarks/                   Synthetic performance measurements
docs/screenshots/               Screenshots used in the README
```

The public launcher remains `python3 -m circle_to_search`. The root `install.py` is a small entry point for the supported KDE installer. The Python distribution is named `circle-to-search-desktop`; its version comes from `circle_to_search/__init__.py`.

## Work on the desktop app

Use a Python 3.10+ development environment with the desktop dependencies from the [installation guide](INSTALL.md). Install editable development dependencies in that environment:

```sh
python3 -m pip install -e '.[dev]'
python3 tools/fetch_models.py
python3 -m circle_to_search
```

Do not replace a distribution-managed Qt installation with a mismatched wheel in the system Python. For KDE/Wayland integration checks, use Qt/PySide6 and LayerShellQt built for compatible Qt versions.

## Checks

```sh
ruff check .
ruff format --check .
python3 tools/check_docs.py
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v
```

Native smoke checks require a running KDE Plasma session. They use synthetic fixtures unless noted:

```sh
python3 tools/smoke/desktop.py
python3 tools/smoke/motion.py
python3 tools/smoke/interaction.py
python3 tools/smoke/ocr_settings.py
python3 tools/smoke/text_actions.py
python3 tools/smoke/theme.py
python3 tools/smoke/selection.py --japanese
```

Check each script’s options before using it. `web.py` and `ai.py` are live Google checks and make network requests; Google may require verification. `tools/preview.py` renders synthetic preview images. OCR container verification and release instructions are in [server development](../server/DEVELOPMENT.md).

## Add another operating system

Add an implementation under `circle_to_search/platforms/<os>/`, then register it in `get_backend()` in `platforms/__init__.py`. Keep OS-specific imports in that implementation. Shared modules must not import a concrete desktop backend.

The `DesktopBackend` interface covers:

- Preparing native Qt integration before `QApplication` is created.
- Capturing an image together with the logical desktop rectangle it represents.
- Assigning the overlay’s native window role before showing it.
- Providing a `ThemeSource` and a per-user instance-lock path.
- Setting up/checking local GPU OCR, or reporting that users should choose local CPU/server OCR instead.

`ThemeSource` reads the real system appearance. File-based integrations can expose `watch_paths`; native integrations can emit its `changed` signal. Do not derive the OS preference from the app-local palette, which the app changes itself.

`paths.py` uses Qt’s standard user configuration location. Per-monitor geometry, OCR character coordinates, selection, UI motion and Google navigation stay shared. Do not copy the entire UI for each OS. The server remains a separate Linux Docker application that any future desktop client can call over the same versioned API.

Platform installers/build definitions belong in `packaging/<os>/`. The [Windows guide](../packaging/windows/README.md) covers the native backend, test dependencies and portable release build. The [macOS checklist](../packaging/macos/README.md) describes that planned port.

## Releases and generated files

The desktop and server have independent versions. Desktop ports share the desktop version, with platform-specific release artifacts when those ports exist. Backend releases use matching `ocr-vX.Y.Z` Git tags and publish a public GHCR image after tests pass.

Generated `build/`, `dist/`, `*.egg-info`, Python/Ruff caches, credentials and downloaded model weights are ignored. Keep model manifests and licenses in Git. Keep browser sessions and user settings out of source/build contexts. Installer updates prune obsolete managed Python modules and icons while preserving user data.

Before building a distributable, run `python3 tools/clean.py` to avoid packaging modules left by an older build. `--dry-run` previews the paths. This targets generated build/cache directories for both projects and preserves model weights, `.env` files and development environments; do not replace it with a blanket removal of all ignored files. Build wheels into a separate output folder after cleaning.

User-facing behavior and visual references are documented in [REFERENCE.md](REFERENCE.md). Instructions for adding real screenshots are in [screenshots/README.md](screenshots/README.md).

## Advanced launch options

```sh
python3 -m circle_to_search --no-auto-search
python3 -m circle_to_search --vertical
python3 -m circle_to_search --external
python3 -m circle_to_search --theme dark
python3 -m circle_to_search --mode box
python3 -m circle_to_search --ocr-language eng+pol
python3 -m circle_to_search --image /path/to/picture.png
python3 -m circle_to_search --ocr-backend server --ocr-server https://your-server --ocr-token-file /path/to/token
```

English/Japanese are bundled; other Tesseract languages require matching installed language packs. Run `--help` for all options.
