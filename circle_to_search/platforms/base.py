"""The OS-dependent services used by the shared Qt application."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from ..ocr_backend import OcrConfig

from PySide6.QtCore import QObject, QRectF, Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QWidget


@dataclass
class Capture:
    image: QImage
    geometry: QRectF
    # Individual captures keyed by the monitor origin in Qt's desktop space.
    screen_images: dict[tuple[int, int], QImage] = field(default_factory=dict)


class ThemeSource(QObject):
    """Read the real OS preference; native ports can emit changed directly."""

    changed = Signal()
    label = "System"

    @property
    def watch_paths(self) -> tuple[Path, ...]:
        return ()

    def is_dark(self) -> bool:
        raise NotImplementedError


class DesktopBackend(Protocol):
    name: str
    gpu_description: str

    def prepare_qt(self) -> None: ...

    def capture_desktop(self, workspace: QRectF, current_screen: QRectF) -> Capture: ...

    def configure_overlay(self, widget: QWidget) -> object | None: ...

    def theme_source(self) -> ThemeSource: ...

    def instance_lock_path(self) -> Path: ...

    def ensure_local_ocr(self, config: OcrConfig) -> OcrConfig: ...

    def prepare_local_ocr(self, config: OcrConfig) -> dict: ...


class UnsupportedPlatform(RuntimeError):
    """The selected OS does not yet have a desktop implementation."""
