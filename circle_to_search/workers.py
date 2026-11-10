from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class Signals(QObject):
    done = Signal(object)
    failed = Signal(str)


class Task(QRunnable):
    def __init__(self, function, *args):
        super().__init__()
        self.function, self.args = function, args
        self.signals = Signals()

    @Slot()
    def run(self):
        try:
            result = self.function(*self.args)
        except Exception as exc:
            self.signals.failed.emit(str(exc))
        else:
            self.signals.done.emit(result)
