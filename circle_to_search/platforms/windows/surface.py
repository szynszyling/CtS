"""A frameless tool surface with native transitions disabled before mapping."""

import ctypes

from PySide6.QtCore import QEvent, QObject, Qt

from .native import libraries


class WindowsSurface(QObject):
    def __init__(self, widget):
        super().__init__(widget)
        widget.setWindowFlag(Qt.WindowType.Tool, True)
        self.widget = widget
        widget.installEventFilter(self)
        self.apply()

    def apply(self):
        _, _, dwm = libraries()
        handle = int(self.widget.winId())
        disabled = ctypes.c_int(1)
        dwm.DwmSetWindowAttribute(handle, 3, ctypes.byref(disabled), ctypes.sizeof(disabled))
        # Windows 11 should not round the corners of the full-monitor overlay.
        dwm.DwmSetWindowAttribute(handle, 33, ctypes.byref(disabled), ctypes.sizeof(disabled))

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.WinIdChange and watched.internalWinId():
            self.apply()
        return False
