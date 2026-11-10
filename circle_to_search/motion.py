"""Small interruptible transitions for native controls, excluding web surfaces."""

from PySide6.QtCore import QEasingCurve,QObject,QPropertyAnimation,Qt
from PySide6.QtWidgets import QGraphicsOpacityEffect


class Fade(QObject):
    def __init__(self,widget):
        super().__init__(widget)
        self.widget=widget
        self.shown=not widget.isHidden()
        self.effect=QGraphicsOpacityEffect(widget)
        self.effect.setOpacity(1 if self.shown else 0)
        widget.setGraphicsEffect(self.effect)
        self.animation=QPropertyAnimation(self.effect,b'opacity',self)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)
        self.animation.finished.connect(self.finished)

    def finished(self):
        if not self.shown:self.widget.hide()

    def set_visible(self,shown,animate=True,duration=140):
        self.animation.stop()
        self.shown=shown
        self.widget.setAttribute(Qt.WA_TransparentForMouseEvents,not shown)
        if shown:self.widget.show()
        target=1.0 if shown else 0.0
        if not animate:
            self.effect.setOpacity(target)
            self.finished()
        elif self.effect.opacity()!=target:
            self.animation.setDuration(duration)
            self.animation.setStartValue(self.effect.opacity())
            self.animation.setEndValue(target)
            self.animation.start()
        else:self.finished()


def fade(widget,shown,animate=True,duration=140):
    if not hasattr(widget,'_fade'):
        widget._fade=Fade(widget)
    widget._fade.set_visible(shown,animate,duration)


def move(widget,position,animate=True,duration=220):
    if not hasattr(widget,'_move'):
        widget._move=QPropertyAnimation(widget,b'pos',widget)
        widget._move.setEasingCurve(QEasingCurve.OutCubic)
    widget._move.stop()
    if animate and widget.pos()!=position:
        widget._move.setDuration(duration)
        widget._move.setStartValue(widget.pos())
        widget._move.setEndValue(position)
        widget._move.start()
    else:widget.move(position)
