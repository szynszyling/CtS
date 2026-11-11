"""KDE Plasma capture, overlay role and system appearance."""

import os
import tempfile
from pathlib import Path

from .capture import capture_desktop
from .surface import configure_overlay
from .theme import PlasmaThemeSource


class KdeBackend:
    name = "KDE Plasma"
    gpu_description = "Local GPU mode keeps OCR on this computer. CtS uses Docker to install and start its backend; first-time setup downloads the models."
    capture_desktop = staticmethod(capture_desktop)
    configure_overlay = staticmethod(configure_overlay)

    def prepare_qt(self):
        # Qt's KDE plugin ignores app-local color-scheme overrides; the GTK3
        # plugin implements them and updates WebEngine's media preference.
        os.environ["QT_QPA_PLATFORMTHEME"] = "gtk3"

    def theme_source(self):
        return PlasmaThemeSource()

    def instance_lock_path(self):
        runtime = Path(os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir())
        return runtime / f"circle-to-search-{os.getuid()}.lock"

    def ensure_local_ocr(self, config):
        from ..ocr import ensure_local

        return ensure_local(config)

    def prepare_local_ocr(self, config, languages=None):
        from ..ocr import prepare_local

        return prepare_local(config, languages)
