# Circle to Search on Windows 🪟

Download and run **CtS-0.14.0-windows-x64-setup.exe** from [GitHub Releases](https://github.com/szynszyling/CtS/releases/latest). Setup installs for your Windows user and adds a Start menu entry. You can also enable startup at sign-in during setup.

Setup downloads the full app from GitHub during installation. The public release needs no sign-in. If you already have the original release ZIP, place it next to Setup to skip the download. Setup verifies the ZIP before installing.

For a portable copy, download the **Windows x64 ZIP**, extract the whole folder, then open **Circle to Search.exe**. Keep the executable and its `_internal` folder together. Python is included.

Press **Win + Shift + G** to open the selection overlay. After you close it, CtS stays in the notification area so the shortcut keeps working. Right-click the tray icon to change the shortcut, start a selection or quit. Windows may put the icon behind the arrow for hidden icons.

## Text recognition ⚡

- **Local GPU** runs the Vulkan OCR worker on Windows without Docker. The bundle includes the models. Use the GPU name field to select a particular device, such as `AMD` or `NVIDIA`.
- **Local Tesseract** uses the CPU. Install Tesseract for Windows separately, for example with `scoop install tesseract`. The app includes the English and Japanese language data. It can find Tesseract on `PATH` or in common install locations.
- **Self-hosted server** connects to the same CtS OCR Docker server used by the Linux desktop app.

Select a backend under **⋮ → Text recognition**. Automatic appearance follows the Windows app theme. Protected video, the lock screen and the secure desktop may not be captured.

## Updating and uninstalling

Quit CtS from the tray before updating. For a Setup installation, run the newer Setup to update, or remove **Circle to Search** in Windows **Settings → Apps → Installed apps**. Settings and browser data live separately from the installed program files.

## Optional shortcuts for portable copies

From the extracted folder, run in PowerShell:

```powershell
& '.\Circle to Search.exe' --install
```

Add `--startup` to also start the tray at sign-in. To remove the shortcuts, use `--uninstall`. To remove the portable app, quit it from the tray and delete its extracted folder. User preferences and browser data live in Windows user data folders.

## Build from source

Use 64-bit Python 3.12 on Windows:

```powershell
python -m pip install '.[dev]' ./server pyinstaller
python tools/fetch_models.py
python tools/fetch_test_font.py
python -m circle_to_search --resident
```

Run `python install.py` for a per-user source install, `python install.py --startup` for sign-in startup, and `python install.py --uninstall` to remove that installation. Quit the tray before updating or uninstalling. This does not remove the checkout or user data.

`python packaging/windows/build.py` creates the versioned ZIP and its SHA-256 checksum under `dist/`. Qt and Python dependencies are bundled alongside the executable. See [third-party notices](https://github.com/szynszyling/CtS/blob/main/THIRD_PARTY.md) for the upstream terms.

With Inno Setup 6.7.4 or later, build the small Setup executable against the exact ZIP uploaded to the matching GitHub release:

```powershell
python packaging/windows/build_setup.py dist/CtS-0.14.0-windows-x64.zip --compiler 'C:\Path\To\ISCC.exe'
```
