# Windows packaging — planned

No Windows application or installer is shipped yet. This directory is reserved for native installer/build definitions when the Windows desktop adapter exists.

Before enabling a Windows release:

- Implement the `DesktopBackend` contract in `circle_to_search/platforms/windows/`.
- Provide native screen capture and permission/error handling, monitor/DPI mapping, overlay placement, appearance notifications and single-instance handling.
- Support launching and the global shortcut using Windows integration.
- Use the shared Qt selection UI, OCR client and search code.
- Test native capture, text/image selection, browser rendering and link handoff on Windows.
- Add the installer, update/uninstall behavior and a Windows CI/release job here.

The Linux Docker OCR server can be used remotely by a future Windows client; Windows GPU-container setup is a separate feature and must not inherit `/dev/dri` assumptions.
