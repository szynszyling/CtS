"""Windows desktop integration; native libraries are loaded only when needed."""

import os
import tempfile
from pathlib import Path


class WindowsBackend:
    name = "Windows"
    gpu_description = "Local GPU mode runs a native Vulkan OCR worker on this computer. First-time setup may download the models."

    def prepare_qt(self):
        from .native import libraries

        user, _, _ = libraries()
        # Qt also enables per-monitor DPI awareness. Set it before creating
        # any native windows so captures use physical, non-virtualized pixels.
        user.SetProcessDpiAwarenessContext(-4)

    def capture_desktop(self, workspace, current_screen):
        from .capture import capture_desktop

        return capture_desktop(workspace, current_screen)

    def configure_overlay(self, widget):
        from .surface import WindowsSurface

        return WindowsSurface(widget)

    def theme_source(self):
        from .theme import WindowsThemeSource

        return WindowsThemeSource()

    def instance_lock_path(self):
        root = Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()) / "CircleToSearch"
        root.mkdir(parents=True, exist_ok=True)
        return root / "instance.lock"

    def ensure_local_ocr(self, config):
        from .ocr import ensure_local

        return ensure_local(config)

    def prepare_local_ocr(self, config):
        from .ocr import prepare_local

        return prepare_local(config)
