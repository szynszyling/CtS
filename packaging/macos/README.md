# macOS packaging — planned

No macOS application or installer is shipped yet. This directory is reserved for the app-bundle/build definitions when the macOS desktop adapter exists.

Before enabling a macOS release:

- Implement the `DesktopBackend` contract in `circle_to_search/platforms/macos/`.
- Provide native screen capture, Screen Recording permission handling, Retina/multi-monitor mapping, overlay placement, appearance notifications and single-instance handling.
- Support app launching and a global shortcut using macOS integration.
- Use the shared Qt selection UI, OCR client and search code.
- Test native capture, text/image selection, browser rendering and link handoff on macOS.
- Add the app bundle, permissions metadata, signing/notarization, update/uninstall behavior and macOS CI/release job here.

The Linux Docker OCR server can be used remotely by a future macOS client; Linux Vulkan device mapping is not a macOS GPU backend.
