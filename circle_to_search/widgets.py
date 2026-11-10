"""Small native controls matching Circle to Search's neutral Google styling."""

from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QToolButton,
    QWidget,
)

from .appearance import current_theme
from .motion import fade, move


def stylesheet(theme):
    style = """
QWidget { color: @text@; font-family: 'Roboto', 'Noto Sans', sans-serif; font-size: 14px; }
QFrame#sheet { background: @background@; border: none; border-top-left-radius: 26px; border-top-right-radius: 26px; }
QFrame#searchPill { background: @surface@; border: none; border-radius: 28px; }
QLineEdit { background: transparent; border: none; color: @text@; padding: 0; selection-background-color: @selection@; selection-color: @selection_text@; }
QPushButton { background: @background@; border: 1px solid @border@; border-radius: 18px; padding: 8px 16px; color: @text@; }
QPushButton:hover { background: @hover@; }
QPushButton:pressed { background: @pressed@; }
QPushButton:disabled { color: @disabled@; }
QFrame#textActions { background: @background@; border: none; border-radius: 20px; }
QFrame#textActions QPushButton { border: none; padding: 10px 15px; background: transparent; }
QFrame#textActions QPushButton:hover { background: @hover@; }
QFrame#textActions QPushButton:pressed { background: @pressed@; }
QFrame#textActionDivider { background: @border@; border: none; }
QLabel#hint { color: white; background: rgba(32,33,36,210); border-radius: 14px; padding: 8px 16px; }
QToolTip { background: @surface@; color: @text@; border: 1px solid @border@; padding: 5px; }
QLabel#status { color: @muted@; background: transparent; }
QMenu { background: @background@; color: @text@; border: 1px solid @border@; padding: 6px; }
QMenu::item { padding: 9px 20px; border-radius: 6px; }
QMenu::item:selected { background: @selection@; color: @text@; }
QMenu::separator { height: 1px; background: @border@; margin: 5px; }
"""
    for name, value in vars(theme).items():
        style = style.replace("@" + name + "@", value)
    return style


ICON_DIRECTORY = Path(__file__).resolve().parent / "icons"


def paint_svg(painter, renderer, bounds):
    size = renderer.viewBoxF().size()
    size.scale(bounds.size(), Qt.KeepAspectRatio)
    target = QRectF(QPointF(), size)
    target.moveCenter(bounds.center())
    renderer.render(painter, target)


class TextActions(QFrame):
    copyRequested = Signal()
    translateRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("textActions")
        self.setAttribute(Qt.WA_NoMousePropagation)
        self.visible_goal = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(7, 2, 7, 2)
        layout.setSpacing(0)
        self.copy_button = QPushButton("Copy")
        self.copy_button.clicked.connect(self.copyRequested.emit)
        layout.addWidget(self.copy_button)
        self.divider = QFrame()
        self.divider.setObjectName("textActionDivider")
        self.divider.setFixedSize(1, 20)
        self.divider.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(self.divider, alignment=Qt.AlignVCenter)
        self.translate_button = QPushButton("Translate")
        self.translate_button.clicked.connect(self.translateRequested.emit)
        layout.addWidget(self.translate_button)
        self.hide()

    def show_at(self, position, animate=True):
        if not self.visible_goal:
            self.visible_goal = True
            if self.isHidden():
                self.move(position + QPoint(0, 6) if animate else position)
            fade(self, True, animate, duration=150)
        if not (
            animate
            and hasattr(self, "_move")
            and self._move.state() == QPropertyAnimation.Running
            and self._move.endValue() == position
        ):
            move(self, position, animate, duration=150)
        self.raise_()

    def dismiss(self, duration=140):
        if not self.visible_goal:
            return
        self.visible_goal = False
        move(self, self.pos() + QPoint(0, 6), duration=duration)
        fade(self, False, duration=duration)


class IconButton(QToolButton):
    def __init__(self, symbol, tooltip, parent=None, light=False):
        super().__init__(parent)
        self.symbol, self.light = symbol, light
        if symbol == "lens":
            self.svg = QSvgRenderer(str(ICON_DIRECTORY / "lens.svg"), self)
        self.setToolTip(tooltip)
        self.setAccessibleName(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(40, 40)
        self.setStyleSheet(
            "QToolButton {background: transparent; border: none; border-radius:20px;} QToolButton:hover {background:rgba(128,128,128,35);}"
        )

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.translate(self.width() / 2, self.height() / 2)
        color = QColor(
            "white"
            if self.light
            else current_theme().muted
            if self.isEnabled()
            else current_theme().disabled
        )
        p.setPen(
            QPen(
                color,
                1.9,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )
        s = self.symbol
        if s == "close":
            p.drawLine(QPointF(-6, -6), QPointF(6, 6))
            p.drawLine(QPointF(-6, 6), QPointF(6, -6))
        elif s == "dots":
            p.setBrush(color)
            p.setPen(Qt.PenStyle.NoPen)
            for y in [-6, 0, 6]:
                p.drawEllipse(QPointF(0, y), 1.6, 1.6)
        elif s == "search":
            p.drawEllipse(QPointF(-2, -2), 6, 6)
            p.drawLine(QPointF(3, 3), QPointF(8, 8))
        elif s == "external":
            p.drawLine(QPointF(-5, 5), QPointF(7, -7))
            p.drawLine(QPointF(0, -7), QPointF(7, -7))
            p.drawLine(QPointF(7, -7), QPointF(7, 0))
            path = QPainterPath(QPointF(-1, -6))
            path.lineTo(-7, -6)
            path.lineTo(-7, 7)
            path.lineTo(6, 7)
            path.lineTo(6, 2)
            p.drawPath(path)
        elif s == "back":
            p.drawLine(QPointF(6, 0), QPointF(-7, 0))
            p.drawLine(QPointF(-7, 0), QPointF(-1, -6))
            p.drawLine(QPointF(-7, 0), QPointF(-1, 6))
        elif s == "translate":
            p.setFont(QFont("Noto Sans", 11, QFont.Weight.Medium))
            p.drawText(QRectF(-12, -13, 18, 22), Qt.AlignmentFlag.AlignCenter, "文")
            p.setFont(QFont("Noto Sans", 9, QFont.Weight.Medium))
            p.drawText(QRectF(0, -1, 14, 16), Qt.AlignmentFlag.AlignCenter, "A")
        elif s == "lens":
            paint_svg(p, self.svg, QRectF(-12, -12, 24, 24))
        elif s == "expand":
            p.drawLine(QPointF(-6, 3), QPointF(0, -3))
            p.drawLine(QPointF(0, -3), QPointF(6, 3))


class GoogleG(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(30, 32)
        self.source = QPixmap(str(ICON_DIRECTORY / "google.png"))
        self.icon_dpr = None
        self.scaled_icon = None

    def paintEvent(self, event):
        dpr = self.devicePixelRatioF()
        if self.icon_dpr != dpr:
            edge = round(28 * dpr)
            self.scaled_icon = self.source.scaled(
                edge, edge, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.scaled_icon.setDevicePixelRatio(dpr)
            self.icon_dpr = dpr
        size = self.scaled_icon.deviceIndependentSize()
        # Align the bitmap to physical pixels, including fractional scaling.
        x = round((self.width() - size.width()) * 0.5 * dpr) / dpr
        y = round((self.height() - size.height()) * 0.5 * dpr) / dpr
        painter = QPainter(self)
        painter.drawPixmap(QPointF(x, y), self.scaled_icon)


class DragControl(QObject):
    moved = Signal(float, float)

    def __init__(self, parent, targets):
        super().__init__(parent)
        self.origin = None
        self.active = False
        for target in targets:
            target.installEventFilter(self)
            target.setCursor(Qt.OpenHandCursor)
            target.setToolTip("Drag to move the search bar; in results, drag up/down to resize")

    def update_drag(self, position):
        delta = position - self.origin
        if (
            not self.active
            and max(abs(delta.x()), abs(delta.y())) >= QApplication.startDragDistance()
        ):
            self.active = True
        if self.active:
            movement = position - self.last
            self.moved.emit(movement.x(), movement.y())
            self.last = position

    def eventFilter(self, target, event):
        if event.type() in (QEvent.UngrabMouse, QEvent.Hide, QEvent.WindowDeactivate):
            self.origin = None
            self.active = False
            target.setCursor(Qt.OpenHandCursor)
            return False
        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            self.origin = event.globalPosition()
            self.last = self.origin
            self.active = False
            target.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return True
        if self.origin is not None and event.type() in (
            QEvent.MouseMove,
            QEvent.MouseButtonRelease,
        ):
            if event.type() == QEvent.MouseButtonRelease and event.button() != Qt.LeftButton:
                return False
            self.update_drag(event.globalPosition())
            if event.type() == QEvent.MouseButtonRelease:
                self.origin = None
                target.setCursor(Qt.OpenHandCursor)
            event.accept()
            return True
        return False


class SearchPill(QFrame):
    submitted = Signal(str)
    translateRequested = Signal()
    imageRequested = Signal()
    dragged = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("searchPill")
        self.setAttribute(Qt.WA_NoMousePropagation)
        self.setFixedHeight(56)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 4, 9, 4)
        layout.setSpacing(8)
        self.logo = GoogleG()
        layout.addWidget(self.logo)
        self.thumbnail = QLabel()
        self.thumbnail.setFixedSize(32, 32)
        self.thumbnail.hide()
        layout.addWidget(self.thumbnail)
        self.query = QLineEdit()
        self.query.setPlaceholderText("Search")
        self.query.setAccessibleName("Search or add to your image search")
        self.query.returnPressed.connect(self.submit)
        layout.addWidget(self.query, 1)
        self.go = IconButton("search", "Search")
        self.go.clicked.connect(self.submit)
        layout.addWidget(self.go)
        self.translate = IconButton("translate", "Translate selected text")
        self.translate.clicked.connect(self.translateRequested.emit)
        layout.addWidget(self.translate)
        self.lens = IconButton("lens", "Search selected image")
        self.lens.clicked.connect(self.imageRequested.emit)
        layout.addWidget(self.lens)

    def enable_dragging(self):
        if hasattr(self, "drag_controller"):
            return
        self.drag_controller = DragControl(self, [self, self.logo, self.thumbnail])
        self.drag_controller.moved.connect(self.dragged.emit)

    def submit(self):
        self.submitted.emit(self.query.text().strip())

    def set_selection(self, image=None, text=""):
        self.query.setText(text)
        self.query.setPlaceholderText(
            "Add to your search" if image is not None and not text else "Search"
        )
        self.thumbnail.setVisible(image is not None and not text)
        if image is not None:
            self.thumbnail.setPixmap(
                QPixmap.fromImage(image).scaled(
                    32,
                    32,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )


class SearchTabs(QFrame):
    requested = Signal(str)
    filterRequested = Signal(str)
    LABELS = (
        ("ai", "AI Mode"),
        ("all", "All"),
        ("images", "Images"),
        ("videos", "Videos"),
        ("shopping", "Shopping"),
        ("news", "News"),
        ("forums", "Forums"),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("searchTabs")
        self.setFixedHeight(43)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 4, 0)
        layout.setSpacing(1)
        self.group = QButtonGroup(self)
        self.buttons = {}
        for key, text in self.LABELS:
            control = QToolButton()
            control.setText(text)
            control.setCheckable(True)
            control.setCursor(Qt.CursorShape.PointingHandCursor)
            control.setAccessibleName(text + " search tab")
            self.group.addButton(control)
            self.buttons[key] = control
            control.clicked.connect(lambda checked, tab=key: self.requested.emit(tab))
            layout.addWidget(control)
        self.more = QToolButton()
        self.more.setText("More ▾")
        self.more.setCheckable(True)
        self.group.addButton(self.more)
        menu = QMenu(self.more)
        for key, text in [("web", "Web"), ("books", "Books")]:
            menu.addAction(text, lambda tab=key: self.requested.emit(tab))
        self.more.setMenu(menu)
        menu.aboutToHide.connect(lambda: self.set_active(self.active_key))
        self.more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        layout.addWidget(self.more)
        layout.addStretch(1)
        self.tools = QToolButton()
        self.tools.setText("Tools")
        filters = QMenu(self.tools)
        for value, text in [
            ("", "Any time"),
            ("h", "Past hour"),
            ("d", "Past day"),
            ("w", "Past week"),
            ("m", "Past month"),
            ("y", "Past year"),
        ]:
            filters.addAction(text, lambda period=value: self.filterRequested.emit(period))
        self.tools.setMenu(filters)
        self.tools.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        layout.addWidget(self.tools)
        self.indicator = QWidget(self)
        self.indicator.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.indicator.setStyleSheet("background:#202124;border:none;")
        self.indicator_animation = QPropertyAnimation(self.indicator, b"geometry", self)
        self.indicator_animation.setDuration(180)
        self.indicator_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.indicator_layout = QTimer(self)
        self.indicator_layout.setSingleShot(True)
        self.indicator_layout.timeout.connect(lambda: self.position_indicator(False))
        self.set_active("all")
        self.apply_theme(current_theme())

    def apply_theme(self, theme):
        self.setStyleSheet(
            """
            QFrame#searchTabs {background:BACKGROUND; border-bottom:1px solid BORDER;}
            QToolButton {background:transparent; color:MUTED; border:none; border-bottom:2px solid transparent;
                         border-radius:0; padding:11px 10px 9px; font-size:13px;}
            QToolButton:hover {color:TEXT;}
            QToolButton:checked {color:TEXT; font-weight:600;}
            QToolButton::menu-indicator {image:none;}
        """.replace("BACKGROUND", theme.background)
            .replace("BORDER", theme.border)
            .replace("MUTED", theme.muted)
            .replace("TEXT", theme.text)
        )
        self.indicator.setStyleSheet("background:" + theme.text + ";border:none;")

    def set_active(self, key):
        self.active_key = key
        self.buttons.get(key, self.more).setChecked(True)
        self.position_indicator(self.isVisible())

    def position_indicator(self, animate):
        control = self.buttons.get(self.active_key, self.more)
        target = QRect(control.x(), self.height() - 2, control.width(), 2)
        self.indicator_animation.stop()
        if animate and self.indicator.geometry() != target:
            self.indicator_animation.setStartValue(self.indicator.geometry())
            self.indicator_animation.setEndValue(target)
            self.indicator_animation.start()
        else:
            self.indicator.setGeometry(target)
        self.indicator.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "indicator_layout"):
            self.indicator_layout.start(0)


class SheetHandle(QWidget):
    dragged = Signal(float, float)
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(27)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setAccessibleName(
            "Drag to move and resize results together; click to expand or collapse"
        )
        self.setToolTip("Drag diagonally to move and resize results together")
        self.origin = None

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#5f6368" if current_theme().dark else current_theme().border))
        p.drawRoundedRect(QRectF(self.width() / 2 - 18, 10, 36, 4), 2, 2)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        self.origin = event.globalPosition()
        self.last = self.origin
        self.dragging = False
        event.accept()

    def event(self, event):
        if event.type() in (QEvent.UngrabMouse, QEvent.Hide, QEvent.WindowDeactivate):
            self.origin = None
        return super().event(event)

    def update_drag(self, position):
        delta = position - self.origin
        if (
            not self.dragging
            and max(abs(delta.x()), abs(delta.y())) >= QApplication.startDragDistance()
        ):
            self.dragging = True
        if self.dragging:
            movement = position - self.last
            self.dragged.emit(movement.x(), movement.y())
            self.last = position

    def mouseMoveEvent(self, event):
        if self.origin is not None:
            self.update_drag(event.globalPosition())
            event.accept()

    def mouseReleaseEvent(self, event):
        if self.origin is None or event.button() != Qt.LeftButton:
            return
        self.update_drag(event.globalPosition())
        if not self.dragging:
            self.clicked.emit()
        self.origin = None
        event.accept()
