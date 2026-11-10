"""Follow Windows' application theme without changing the system preference."""

from PySide6.QtCore import QTimer

from ..base import ThemeSource


def apps_use_dark_theme():
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False


class WindowsThemeSource(ThemeSource):
    label = "Windows"

    def __init__(self):
        super().__init__()
        self.last = self.is_dark()
        self.timer = QTimer(self)
        self.timer.setInterval(1500)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()

    def is_dark(self):
        return apps_use_dark_theme()

    def refresh(self):
        value = self.is_dark()
        if value != self.last:
            self.changed.emit()
        self.last = value
