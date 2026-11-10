"""Shared palettes and theme transitions, supplied with a platform theme source."""

from dataclasses import dataclass

from PySide6.QtCore import (
    QCoreApplication,
    QFileSystemWatcher,
    QObject,
    QSettings,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from .platforms import get_backend
from .platforms.base import ThemeSource


@dataclass(frozen=True)
class Theme:
    name: str
    background: str
    surface: str
    text: str
    muted: str
    disabled: str
    border: str
    hover: str
    pressed: str
    accent: str
    selection: str
    selection_text: str

    @property
    def dark(self):
        return self.name == "dark"


LIGHT = Theme(
    "light",
    "#ffffff",
    "#f1f3f4",
    "#202124",
    "#5f6368",
    "#9aa0a6",
    "#dadce0",
    "#f1f3f4",
    "#e8eaed",
    "#4285f4",
    "#a8c7fa",
    "#202124",
)
DARK = Theme(
    "dark",
    "#22242a",
    "#303134",
    "#e8eaed",
    "#bdc1c6",
    "#80868b",
    "#3c4043",
    "#3c4043",
    "#45464a",
    "#8ab4f8",
    "#394f73",
    "#e8eaed",
)


def prepare_qt():
    get_backend().prepare_qt()
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)


def theme_manager():
    return getattr(QApplication.instance(), "_cts_appearance", None)


def current_theme():
    manager = theme_manager()
    return manager.theme if manager else LIGHT


def apply_palette(app, theme):
    palette = QPalette()
    roles = {
        "Window": theme.background,
        "Base": theme.background,
        "AlternateBase": theme.surface,
        "Button": theme.surface,
        "ToolTipBase": theme.surface,
        "WindowText": theme.text,
        "Text": theme.text,
        "ButtonText": theme.text,
        "ToolTipText": theme.text,
        "PlaceholderText": theme.muted,
        "Highlight": theme.selection,
        "HighlightedText": theme.selection_text,
        "Link": theme.accent,
        "LinkVisited": theme.accent,
        "Light": theme.border,
        "Midlight": theme.border,
        "Mid": theme.border,
        "Dark": theme.border,
        "Shadow": "#000000",
    }
    for role, color in roles.items():
        palette.setColor(getattr(QPalette.ColorRole, role), QColor(color))
    for role in ("WindowText", "Text", "ButtonText"):
        palette.setColor(
            QPalette.ColorGroup.Disabled, getattr(QPalette.ColorRole, role), QColor(theme.disabled)
        )
    app.styleHints().setColorScheme(Qt.ColorScheme.Dark if theme.dark else Qt.ColorScheme.Light)
    app.setPalette(palette)


class ThemeManager(QObject):
    aboutToChange = Signal(object)
    changed = Signal(object)
    modeChanged = Signal(str)
    MODES = ("auto", "light", "dark")

    def __init__(
        self, app, mode=None, *, settings=None, source: ThemeSource | None = None, watch=True
    ):
        super().__init__(app)
        self.app = app
        self.settings = (
            settings if settings is not None else QSettings("circle-to-search", "appearance")
        )
        saved = self.settings.value("theme", "auto")
        self.mode = mode if mode in self.MODES else saved if saved in self.MODES else "auto"
        self.source = source or get_backend().theme_source()
        self.source.setParent(self)
        self.theme = self.resolve_theme()
        app._cts_appearance = self
        apply_palette(app, self.theme)
        self.watch_enabled = watch
        self.watcher = QFileSystemWatcher(self)
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.timeout.connect(self.refresh)
        if watch:
            self.source.changed.connect(self.schedule_refresh)
            self.watcher.fileChanged.connect(self.schedule_refresh)
            self.watcher.directoryChanged.connect(self.schedule_refresh)
            self.watch_paths()

    def watch_paths(self):
        if not self.watch_enabled:
            return
        paths = self.source.watch_paths
        existing = set(self.watcher.files() + self.watcher.directories())
        for path in paths:
            if path.exists() and str(path) not in existing:
                self.watcher.addPath(str(path))

    def resolve_theme(self):
        if self.mode == "auto":
            return DARK if self.source.is_dark() else LIGHT
        return DARK if self.mode == "dark" else LIGHT

    def schedule_refresh(self, *_):
        self.debounce.start(120)

    def refresh(self):
        self.watch_paths()
        target = self.resolve_theme()
        if target == self.theme:
            return
        self.aboutToChange.emit(target)
        self.theme = target
        apply_palette(self.app, target)
        self.changed.emit(target)

    def set_mode(self, mode):
        if mode not in self.MODES:
            raise ValueError("Unknown appearance mode: " + str(mode))
        self.mode = mode
        self.settings.setValue("theme", mode)
        self.settings.sync()
        self.refresh()
        self.modeChanged.emit(mode)
