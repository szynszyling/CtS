"""Tray launcher, configurable global hotkey and activation of a running copy."""

from ctypes import wintypes as w

from PySide6.QtCore import QAbstractNativeEventFilter, QSettings, QThreadPool, QTimer
from PySide6.QtGui import QKeySequence
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QKeySequenceEdit,
    QMenu,
    QMessageBox,
    QSystemTrayIcon,
    QVBoxLayout,
)

from .native import libraries


def hotkey_values(sequence):
    from PySide6.QtCore import Qt

    sequence = QKeySequence(sequence.replace("Win+", "Meta+"))
    if sequence.count() != 1:
        raise ValueError("Choose one shortcut, such as Win+Shift+G or Ctrl+Alt+G.")
    combination = sequence[0]
    modifiers = combination.keyboardModifiers()
    flags = 0x4000  # MOD_NOREPEAT
    for modifier, flag in [
        (Qt.ControlModifier, 2),
        (Qt.AltModifier, 1),
        (Qt.ShiftModifier, 4),
        (Qt.MetaModifier, 8),
    ]:
        if modifiers & modifier:
            flags |= flag
    key = combination.key()
    if Qt.Key_A <= key <= Qt.Key_Z or Qt.Key_0 <= key <= Qt.Key_9:
        virtual_key = int(key)
    elif Qt.Key_F1 <= key <= Qt.Key_F24:
        virtual_key = 0x70 + int(key) - int(Qt.Key_F1)
    else:
        raise ValueError("Use a letter, number or F1–F24 with Ctrl, Alt, Shift or Win.")
    if flags & (1 | 2 | 8) == 0:
        raise ValueError("Include Ctrl, Alt or Win in the shortcut.")
    return flags, virtual_key


class NativeHotkey(QAbstractNativeEventFilter):
    def __init__(self, app, callback):
        super().__init__()
        self.app, self.callback = app, callback
        self.registered = False
        self.identifier = 0x4354
        self.sequence = None
        app.installNativeEventFilter(self)

    def set_sequence(self, sequence):
        user, _, _ = libraries()
        flags, key = hotkey_values(sequence)
        if self.registered and self.sequence == (flags, key):
            return
        # Register the replacement first, so a conflict cannot lose the old shortcut.
        identifier = 0x4355 if self.identifier == 0x4354 else 0x4354
        if not user.RegisterHotKey(None, identifier, flags, key):
            raise RuntimeError(
                "That shortcut is already in use. Choose another shortcut from the tray menu."
            )
        if self.registered:
            user.UnregisterHotKey(None, self.identifier)
        self.identifier, self.registered = identifier, True
        self.sequence = flags, key

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            event = w.MSG.from_address(int(message))
            if event.message == 0x0312 and event.wParam == self.identifier:
                QTimer.singleShot(0, self.callback)
                return True, 0
        return False, 0

    def close(self):
        if self.registered:
            libraries()[0].UnregisterHotKey(None, self.identifier)
            self.registered = False
        self.app.removeNativeEventFilter(self)


def activation_name():
    import getpass
    import hashlib

    user = hashlib.sha256(getpass.getuser().encode()).hexdigest()[:16]
    return "circle-to-search-windows-" + user


def activate_existing():
    connection = QLocalSocket()
    connection.connectToServer(activation_name())
    if not connection.waitForConnected(1000):
        return False
    connection.write(b"activate")
    connection.flush()
    connection.waitForBytesWritten(1000)
    connection.disconnectFromServer()
    return True


class Resident:
    def __init__(self, app, args):
        self.app, self.args = app, args
        self.controller = None
        self.retired = []
        self.exiting = False
        self.settings = QSettings("circle-to-search", "windows")
        self.hotkey = NativeHotkey(app, lambda: self.activate(toggle=True))
        self.tray = QSystemTrayIcon(app.windowIcon(), app)
        self.tray.setToolTip("Circle to Search")
        self.menu = QMenu()
        self.search_action = self.menu.addAction("Circle to Search", lambda: self.activate())
        self.menu.addAction("Change shortcut…", self.change_shortcut)
        self.menu.addSeparator()
        self.menu.addAction("Quit Circle to Search", self.quit)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self.tray_activated)
        self.tray.show()
        self.server = QLocalServer(app)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        if not self.server.listen(activation_name()):
            raise RuntimeError("Could not start the local CtS activation service.")
        self.server.newConnection.connect(self.connected)
        self.cleanup_timer = QTimer(app)
        self.cleanup_timer.setInterval(500)
        self.cleanup_timer.timeout.connect(self.cleanup)
        self.cleanup_timer.start()
        app.aboutToQuit.connect(self.close)
        shortcut = args.hotkey or self.settings.value("shortcut", "Meta+Shift+G")
        try:
            self.hotkey.set_sequence(shortcut)
            self.search_action.setText(
                "Circle to Search (" + QKeySequence(shortcut).toString() + ")"
            )
        except (ValueError, RuntimeError) as error:
            self.tray.showMessage("Circle to Search", str(error))

    def connected(self):
        while self.server.hasPendingConnections():
            connection = self.server.nextPendingConnection()
            connection.close()
            connection.deleteLater()
        self.activate()

    def tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.activate()

    def activate(self, *, toggle=False):
        if self.exiting:
            return
        if self.controller is not None:
            if self.controller.overlays and not self.controller.closing:
                if toggle:
                    self.controller.quit()
                else:
                    active = next(
                        (
                            item
                            for item in self.controller.overlays
                            if item.screen() == self.controller.current
                        ),
                        self.controller.overlays[0],
                    )
                    active.raise_()
                    active.activateWindow()
            return
        # A tray menu must disappear before the desktop is frozen.
        self.menu.hide()
        from ...app import Controller

        self.controller = Controller(self.app, self.args, quit_on_close=False)
        self.controller.finished.connect(self.session_finished)
        QTimer.singleShot(100, self.controller.start)

    def session_finished(self):
        if self.controller is not None:
            self.retired.append(self.controller)
        self.controller = None
        self.cleanup()
        if self.exiting:
            self.app.quit()

    def cleanup(self):
        # Keep callback receivers alive until OCR tasks have finished. Closing
        # already invalidates their generations, so stale results are ignored.
        if QThreadPool.globalInstance().activeThreadCount():
            return
        for controller in self.retired:
            for overlay in controller.overlays:
                overlay.deleteLater()
            controller.deleteLater()
        self.retired.clear()

    def change_shortcut(self):
        dialog = QDialog()
        dialog.setWindowTitle("Circle to Search shortcut")
        layout = QVBoxLayout(dialog)
        editor = QKeySequenceEdit(QKeySequence(self.settings.value("shortcut", "Meta+Shift+G")))
        editor.setMaximumSequenceLength(1)
        layout.addWidget(editor)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        layout.addWidget(buttons)

        def save():
            try:
                sequence = editor.keySequence().toString()
                self.hotkey.set_sequence(sequence)
            except (ValueError, RuntimeError) as error:
                QMessageBox.warning(dialog, "Shortcut unavailable", str(error))
                return
            self.settings.setValue("shortcut", sequence)
            self.settings.sync()
            self.search_action.setText("Circle to Search (" + sequence + ")")
            dialog.accept()

        buttons.accepted.connect(save)
        buttons.rejected.connect(dialog.reject)
        dialog.exec()

    def quit(self):
        self.exiting = True
        if self.controller is not None:
            self.controller.quit()
        else:
            self.app.quit()

    def close(self):
        self.hotkey.close()
        self.server.close()
        self.tray.hide()
