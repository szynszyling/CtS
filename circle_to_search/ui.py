"""The frozen-screen interaction: gesture, selection handles and result sheet."""

import time

from PySide6.QtCore import QEasingCurve,QPoint,QPointF,QRectF,Qt,QThreadPool,QTimer,QUrl,QVariantAnimation,Signal
from PySide6.QtGui import QActionGroup,QColor,QFont,QImage,QKeySequence,QLinearGradient,QPainter,QPainterPath,QPen,QShortcut
from PySide6.QtWidgets import QApplication,QDialog,QFileDialog,QLabel,QMenu,QWidget

from .geometry import pixel_bounds
from .desktop import configure_overlay
from .gestures import Selection, resolve_gesture
from .ocr import Document, Glyph, default_languages, encode_png, gesture_region, recognize_document
from .results import ResultSheet, create_browser
from .search import text_search_url, translation_url, upload_to_lens
from .widgets import IconButton, SearchPill, TextActions, stylesheet
from .workers import Task
from .motion import fade,move
from .appearance import current_theme,theme_manager

png_bytes = encode_png


class SelectionOverlay(QWidget):
    selected = Signal(object, object)  # cropped QImage, global QRectF
    cancelled = Signal()
    dismissed = Signal()
    externalRequested=Signal(QUrl)
    ocrSettingsChanged=Signal()

    def __init__(self, image: QImage, screen, mode="circle", *, document=None, start_ocr=True,
                 auto_search=True, browser_factory=create_browser, language=None, external=False):
        super().__init__()
        self.image = image
        self.mode = mode
        self.language = language or default_languages()
        self.external = external
        self.auto_search = auto_search
        self.document = document or Document([])
        self.full_document = document
        self.document_is_regional = False
        self.region_token = None
        self.ocr_pending = start_ocr and document is None
        self.recognition_enabled = start_ocr and document is None
        self.vertical = False
        self.ocr_generation = 0
        self.pending_gesture = None
        self.points = []
        self.dragging = False
        self.box_drag = False
        self.selection = None
        self.drag_handle = None
        self.tasks = set()
        self.generation = 0
        self.bar_at_top = False
        self.bar_left=None
        self.bar_top=None
        self.created_at = time.monotonic()
        self.closing=False
        self.ocr_settings_panel=None
        self.overlay_progress=1.0
        self.selection_progress=1.0
        self.reveal=QVariantAnimation(self)
        self.reveal.setEasingCurve(QEasingCurve.OutCubic)
        self.reveal.valueChanged.connect(self.set_overlay_progress)
        self.reveal.finished.connect(self.reveal_finished)
        self.selection_reveal=QVariantAnimation(self)
        self.selection_reveal.setDuration(140)
        self.selection_reveal.setEasingCurve(QEasingCurve.OutCubic)
        self.selection_reveal.valueChanged.connect(self.set_selection_progress)
        self.setWindowTitle("Circle to Search")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet(stylesheet(current_theme()))
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self.setScreen(screen)
        self.setGeometry(screen.geometry())
        self.close_button = IconButton("close", "Close Circle to Search (Esc)", self, light=True)
        self.close_button.clicked.connect(self.cancelled.emit)
        self.wordmark = QLabel("Google", self)
        self.wordmark.setStyleSheet("color:white; background:transparent; font-size:23px; font-weight:500;")
        self.wordmark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.more_button = IconButton("dots", "More options", self, light=True)
        self.more_button.clicked.connect(self.show_menu)
        self.bar = SearchPill(self)
        self.bar.enable_dragging()
        self.bar.dragged.connect(self.shift_search_bar)
        self.bar.submitted.connect(self.submit)
        self.bar.imageRequested.connect(self.search_image)
        self.bar.translateRequested.connect(self.translate)
        self.hint = QLabel("Circle, highlight, scribble or tap to search", self)
        self.hint.setObjectName("hint")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint.adjustSize()
        self.text_actions = TextActions(self)
        self.text_actions.copyRequested.connect(self.copy_text)
        self.text_actions.translateRequested.connect(self.translate)
        self.sheet = ResultSheet(self, browser_factory)
        self.sheet.cleared.connect(self.clear_selection)
        self.sheet.presented.connect(self.raise_floating_controls)
        self.sheet.externalRequested.connect(self.externalRequested.emit)
        self.sheet.bar.submitted.connect(self.submit)
        self.sheet.bar.imageRequested.connect(self.search_image)
        self.sheet.bar.translateRequested.connect(self.translate)
        self.escape = QShortcut(QKeySequence("Escape"), self)
        self.escape.activated.connect(self.back)
        self.search_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        self.search_shortcut.activated.connect(lambda: self.submit(self.sheet.bar.query.text()))
        self.vertical_shortcut = QShortcut(QKeySequence("V"), self)
        self.vertical_shortcut.activated.connect(self.toggle_vertical)
        self.vertical_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        self.glow_timer = QTimer(self)
        self.glow_timer.timeout.connect(self.animate_glow)
        self.glow_timer.start(30)
        if self.ocr_pending:
            QTimer.singleShot(0, self.start_recognition)
        self.layer_surface = None
        if theme_manager():theme_manager().changed.connect(self.apply_theme)

    def apply_theme(self,theme):
        self.setStyleSheet(stylesheet(theme))
        self.update()
        for control in self.findChildren(QWidget):control.update()

    def show_overlay(self):
        # configure_overlay prepares the final graphics surface before mapping
        # the layer, so lazy browser creation cannot replace its native window.
        self.setFixedSize(self.screen().geometry().size())
        self.setGeometry(self.screen().geometry())
        if self.layer_surface is None:
            self.layer_surface = configure_overlay(self)
        self.created_at=time.monotonic()
        self.overlay_progress=0.0
        for control in self.chrome_controls():
            fade(control,False,False)
        if self.layer_surface is not None:
            self.show()
        else:
            self.showFullScreen()
        self.reveal.setDuration(180)
        self.reveal.setStartValue(0.0)
        self.reveal.setEndValue(1.0)
        self.reveal.start()
        for control in self.chrome_controls():fade(control,True,duration=180)
        destination=self.bar.pos()
        self.bar.move(destination+QPoint(0,12))
        move(self.bar,destination,duration=220)

    def chrome_controls(self):
        return [self.close_button,self.wordmark,self.more_button,self.bar,self.hint]

    def set_overlay_progress(self,value):
        self.overlay_progress=float(value)
        self.update()

    def set_selection_progress(self,value):
        self.selection_progress=float(value)
        self.update()

    def reveal_finished(self):
        if self.closing:
            self.hide()
            self.dismissed.emit()

    def dismiss(self):
        if self.closing:return
        self.closing=True
        self.generation+=1
        self.ocr_generation+=1
        self.region_token=None
        self.pending_gesture=None
        self.setAttribute(Qt.WA_TransparentForMouseEvents,True)
        for control in self.chrome_controls():fade(control,False,duration=160)
        self.text_actions.dismiss(duration=160)
        self.sheet.stop(animate=True)
        self.reveal.stop()
        self.reveal.setDuration(180)
        self.reveal.setStartValue(self.overlay_progress)
        self.reveal.setEndValue(0.0)
        self.reveal.start()

    def run_task(self, function, args, done, failed):
        task = Task(function, *args)
        self.tasks.add(task)
        task.signals.done.connect(done)
        task.signals.failed.connect(failed)
        task.signals.done.connect(lambda _: self.tasks.discard(task))
        task.signals.failed.connect(lambda _: self.tasks.discard(task))
        QThreadPool.globalInstance().start(task)

    def start_recognition(self):
        self.ocr_pending = True
        self.ocr_generation += 1
        self.full_document = None
        self.document = Document([])
        self.document_is_regional = False
        self.region_token = None
        generation = self.ocr_generation
        self.run_task(recognize_document, (self.image, self.language, self.vertical),
                      lambda doc: self.recognition_ready(doc, generation),
                      lambda message: self.recognition_failed(message, generation))

    def map_document(self,document,origin=QPointF()):
        sx, sy = self.width() / self.image.width(), self.height() / self.image.height()
        return Document([Glyph(g.text,QRectF((g.rect.x()+origin.x())*sx,(g.rect.y()+origin.y())*sy,
                                             g.rect.width()*sx,g.rect.height()*sy),g.line,g.word,g.confidence)
                         for g in document.glyphs],document.error)

    def recognition_ready(self, document, generation):
        if generation != self.ocr_generation:
            return
        self.full_document = self.map_document(document)
        self.ocr_pending = False
        if self.pending_gesture:
            self.region_token = None
            self.document = self.full_document
            self.document_is_regional = False
            points, box = self.pending_gesture
            self.pending_gesture = None
            self.finish_gesture(points, box)
        elif self.document_is_regional:
            self.promote_document()
        else:
            self.document = self.full_document

    def start_region_recognition(self,points):
        region=gesture_region(points,QRectF(self.rect()),self.vertical)
        pixels=pixel_bounds(region,QRectF(self.rect()),self.image.size())
        if self.ocr_pending and pixels.width()*pixels.height()>=self.image.width()*self.image.height()*.65:
            return  # the existing scan already covers a gesture this large
        token=(self.ocr_generation,self.generation)
        self.region_token=token
        self.run_task(recognize_document,(self.image.copy(pixels),self.language,self.vertical,"interactive"),
                      lambda doc:self.region_ready(doc,pixels.topLeft(),token),
                      lambda message:self.region_failed(message,token))

    def region_ready(self,document,origin,token):
        if token!=self.region_token or not self.pending_gesture:
            return
        self.region_token=None
        regional_document=self.map_document(document,origin)
        points,box=self.pending_gesture
        candidate=resolve_gesture(points,QRectF(self.rect()),regional_document,box)
        if self.ocr_pending and (candidate is None or candidate.kind!="text"):
            # Missing local text must not turn into an image search while the
            # more complete background recognition can still resolve it.
            return
        self.document=regional_document
        self.document_is_regional=True
        self.pending_gesture=None
        self.finish_gesture(points,box)

    def region_failed(self,message,token):
        if token!=self.region_token or not self.pending_gesture:
            return
        self.region_token=None
        if not self.ocr_pending:
            self.recognition_failed(message,self.ocr_generation)

    def promote_document(self):
        """Extend handle coverage without changing an already selected phrase."""
        if self.full_document is None or self.drag_handle is not None:
            return
        if self.selection and self.selection.kind=="text":
            bounds=self.selection.bounds.adjusted(-2,-2,2,2)
            indices=[i for i,g in enumerate(self.full_document.glyphs) if bounds.contains(g.rect.center())]
            if self.full_document.text(indices)!=self.selection.text:
                return
            self.selection=Selection("text",self.full_document.bounds(indices),indices,self.selection.text)
        self.document=self.full_document
        self.document_is_regional=False
        self.position_text_actions()
        self.update()

    def recognition_failed(self, message, generation):
        if generation != self.ocr_generation:
            return
        self.ocr_pending = False
        # A local gesture scan may still succeed even if the larger scan
        # times out. Let that worker finish rather than selecting an image.
        if self.region_token is not None or (self.document_is_regional and self.selection is not None):
            return
        self.document = Document([], error=message)
        self.hint.setText(message)
        self.hint.adjustSize()
        if self.pending_gesture:
            points, box = self.pending_gesture
            self.pending_gesture = None
            self.finish_gesture(points, box)

    def toggle_vertical(self):
        self.vertical = not self.vertical
        self.clear_selection()
        self.hint.setText("Vertical Japanese text — draw across or along the characters" if self.vertical else "Circle, highlight, scribble or tap to search")
        self.hint.adjustSize()
        self.start_recognition()

    def animate_glow(self):
        if time.monotonic() - self.created_at >= .85:
            self.glow_timer.stop()
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not hasattr(self, "bar"):
            return
        self.close_button.move(18, 18)
        self.more_button.move(self.width() - 58, 18)
        self.wordmark.setGeometry(self.width() // 2 - 80, 20, 160, 38)
        bar_width = min(640, self.width() - 48)
        bar_y=(84 if self.bar_at_top else self.height()-86) if self.bar_top is None else max(84,min(self.bar_top,self.height()-80))
        self.bar.resize(bar_width,56)
        left=(self.width()-bar_width)//2 if self.bar_left is None else max(24,min(self.bar_left,self.width()-bar_width-24))
        move(self.bar,QPoint(left,bar_y),animate=False)
        self.position_hint()
        if self.sheet.isVisible() and not self.sheet.dismissing:
            self.sheet.show_sheet(False)
        self.position_text_actions()
        if self.ocr_settings_panel is not None:
            self.ocr_settings_panel.setGeometry(self.rect())
            self.ocr_settings_panel.raise_()

    def position_hint(self):
        self.hint.adjustSize()
        left=max(12,min(self.bar.geometry().center().x()-self.hint.width()//2,self.width()-self.hint.width()-12))
        self.hint.move(left,self.bar.y()+70 if self.bar.y()<128 else self.bar.y()-48)

    def shift_search_bar(self,dx,dy):
        if self.closing:return
        self.bar_left=max(24,min(round(self.bar.x()+dx),self.width()-self.bar.width()-24))
        self.bar_top=max(84,min(round(self.bar.y()+dy),self.height()-80))
        move(self.bar,QPoint(self.bar_left,self.bar_top),animate=False)
        self.position_hint()

    def selection_obscured(self,point):
        if self.ocr_settings_panel is not None and self.ocr_settings_panel.isVisible():return True
        if self.sheet.blocks_selection(point):return True
        return any(control.isVisible() and control.geometry().contains(point.toPoint())
                   for control in self.chrome_controls()+[self.text_actions])

    def raise_floating_controls(self):
        self.text_actions.raise_()
        if self.ocr_settings_panel is not None and self.ocr_settings_panel.isVisible():
            self.ocr_settings_panel.raise_()

    def position_text_actions(self):
        if self.ocr_settings_panel is not None and self.ocr_settings_panel.isVisible():
            self.text_actions.dismiss()
            return
        if not self.selection or self.selection.kind != "text":
            self.text_actions.dismiss()
            return
        self.text_actions.adjustSize()
        bounds = self.selection.bounds
        x = min(self.width() - self.text_actions.width() - 12, max(12, int(bounds.center().x() - self.text_actions.width() / 2)))
        y = int(bounds.top() - self.text_actions.height() - 15)
        if y < 72:
            y = int(bounds.bottom() + 20)
        self.text_actions.show_at(QPoint(x,y),animate=self.drag_handle is None)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        target = QRectF(self.rect())
        painter.drawImage(target, self.image)
        shade = QPainterPath()
        shade.addRect(target)
        if self.selection:
            clear = QPainterPath()
            if self.selection.kind == "image":
                clear.addRoundedRect(self.selection.bounds, 10, 10)
            else:
                for rect in self.document.highlights(self.selection.indices):
                    clear.addRoundedRect(rect, 3, 3)
            shade = shade.subtracted(clear)
        painter.fillPath(shade, QColor(0,0,0,round(86*self.overlay_progress)))
        if self.selection:
            painter.fillPath(clear,QColor(0,0,0,round(86*self.overlay_progress*(1-self.selection_progress))))
        self.paint_activation(painter)
        if self.selection:
            painter.save()
            painter.setOpacity(self.overlay_progress*self.selection_progress)
            if self.selection.kind == "text":
                for rect in self.document.highlights(self.selection.indices):
                    painter.setPen(Qt.PenStyle.NoPen)
                    highlight=QColor(current_theme().accent)
                    highlight.setAlpha(110)
                    painter.setBrush(highlight)
                    painter.drawRoundedRect(rect, 3, 3)
                self.paint_text_handles(painter)
            else:
                self.paint_image_handles(painter)
            painter.restore()
        if self.points:
            painter.save()
            painter.setOpacity(self.overlay_progress)
            path = QPainterPath(self.points[0])
            if self.box_drag:
                path.addRoundedRect(QRectF(self.points[0], self.points[-1]).normalized(), 8, 8)
            else:
                for point in self.points[1:]:
                    path.lineTo(point)
            painter.setPen(QPen(QColor(0, 0, 0, 35), 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawPath(path)
            painter.setPen(QPen(Qt.GlobalColor.white, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawPath(path)
            painter.restore()

    def paint_activation(self, painter):
        age = time.monotonic() - self.created_at
        if age > .85:
            return
        alpha = int(65 * (1 - age / .85)*self.overlay_progress)
        # A short Google-color edge glow on activation, never a tinted scrim.
        for x, color in [(0, QColor(66, 133, 244, alpha)), (self.width(), QColor(52, 168, 83, alpha))]:
            grad = QLinearGradient(x, 0, x + (95 if x == 0 else -95), 0)
            grad.setColorAt(0, color)
            grad.setColorAt(1, QColor(0, 0, 0, 0))
            painter.fillRect(self.rect(), grad)

    def text_handle_positions(self):
        if not self.selection or not self.selection.indices:
            return []
        first = self.document.glyphs[self.selection.indices[0]].rect
        last = self.document.glyphs[self.selection.indices[-1]].rect
        return [QPointF(first.left(), first.bottom() + 9), QPointF(last.right(), last.bottom() + 9)]

    def paint_text_handles(self, painter):
        painter.setPen(QPen(QColor(current_theme().accent), 2))
        painter.setBrush(QColor(current_theme().accent))
        for i, point in enumerate(self.text_handle_positions()):
            painter.drawLine(point, point - QPointF(0, 10))
            painter.drawEllipse(point + QPointF(-5 if i == 0 else 5, 0), 7, 7)

    def image_handle_positions(self):
        r = self.selection.bounds
        return [r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft()]

    def paint_image_handles(self, painter):
        r = self.selection.bounds
        painter.setPen(QPen(Qt.GlobalColor.white, 3.3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        length = min(22, r.width() / 3, r.height() / 3)
        for corner, dx, dy in [(r.topLeft(),1,1),(r.topRight(),-1,1),(r.bottomRight(),-1,-1),(r.bottomLeft(),1,-1)]:
            path = QPainterPath(corner + QPointF(0, dy * length))
            path.lineTo(corner + QPointF(0, dy * 7))
            path.quadTo(corner, corner + QPointF(dx * 7, 0))
            path.lineTo(corner + QPointF(dx * length, 0))
            painter.drawPath(path)

    def handle_at(self, point):
        if not self.selection:
            return None
        handles = self.text_handle_positions() if self.selection.kind == "text" else self.image_handle_positions()
        for i, handle in enumerate(handles):
            if (point - handle).manhattanLength() < 22:
                return i
        if self.selection.kind == "image" and self.selection.bounds.contains(point):
            return "move"
        return None

    def mousePressEvent(self, event):
        if self.closing:return
        if self.selection_obscured(event.position()):
            event.accept()
            return
        if event.button() == Qt.MouseButton.RightButton:
            self.cancelled.emit()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.setFocus()
        self.drag_handle = self.handle_at(event.position())
        if self.drag_handle is not None:
            self.drag_origin = event.position()
            self.original_bounds = QRectF(self.selection.bounds)
            self.original_indices = list(self.selection.indices)
            return
        self.clear_selection()
        self.points = [event.position()]
        self.box_drag = self.mode == "box" or bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        self.dragging = True
        fade(self.hint,False)
        self.update()

    def mouseMoveEvent(self, event):
        if self.drag_handle is not None:
            self.adjust_selection(event.position())
        elif self.dragging:
            if (event.position() - self.points[-1]).manhattanLength() >= 2:
                self.points.append(event.position())
            self.update()
        else:
            if self.selection_obscured(event.position()):
                self.setCursor(Qt.ArrowCursor)
                event.accept()
                return
            self.setCursor(Qt.CursorShape.SizeAllCursor if self.handle_at(event.position()) is not None else Qt.CursorShape.CrossCursor)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self.drag_handle is not None:
            self.adjust_selection(event.position())
            self.drag_handle = None
            self.accept_selection(self.selection)
            if self.document_is_regional:
                self.promote_document()
        elif self.dragging:
            self.dragging = False
            self.points.append(event.position())
            if (self.ocr_pending or (self.recognition_enabled and self.full_document is None)) and not self.box_drag:
                self.pending_gesture = (list(self.points), self.box_drag)
                self.hint.setText("Selecting…")
                self.hint.adjustSize()
                fade(self.hint,True)
                self.start_region_recognition(self.points)
            else:
                self.finish_gesture(self.points, self.box_drag)

    def finish_gesture(self, points, box):
        selection = resolve_gesture(points, QRectF(self.rect()), self.document, box)
        self.points = []
        if selection:
            self.accept_selection(selection)
        self.update()

    def adjust_selection(self, point):
        if self.selection.kind == "text":
            if not self.document.glyphs:
                return
            nearest = min(range(len(self.document.glyphs)), key=lambda i: (self.document.glyphs[i].rect.center() - point).manhattanLength())
            anchor = self.original_indices[-1] if self.drag_handle == 0 else self.original_indices[0]
            indices = self.document.expand_words(range(min(nearest, anchor), max(nearest, anchor) + 1))
            self.selection = Selection("text", self.document.bounds(indices), indices, self.document.text(indices))
        else:
            rect = QRectF(self.original_bounds)
            if self.drag_handle == "move":
                rect.translate(point - self.drag_origin)
                rect.moveLeft(max(0, min(rect.left(), self.width() - rect.width())))
                rect.moveTop(max(0, min(rect.top(), self.height() - rect.height())))
            else:
                opposite = [rect.bottomRight(), rect.bottomLeft(), rect.topLeft(), rect.topRight()][self.drag_handle]
                rect = QRectF(opposite, point).normalized().intersected(QRectF(self.rect()))
                if min(rect.width(), rect.height()) < 8:
                    return
            self.selection = Selection("image", rect)
        self.position_text_actions()
        self.update()

    def crop(self):
        if not self.selection:
            return QImage()
        return self.image.copy(pixel_bounds(self.selection.bounds, QRectF(self.rect()), self.image.size()))

    def accept_selection(self, selection):
        if self.closing:return
        if self.selection is None or self.selection.kind!=selection.kind:
            self.selection_reveal.stop()
            self.selection_progress=0.0
            self.selection_reveal.setStartValue(0.0)
            self.selection_reveal.setEndValue(1.0)
            self.selection_reveal.start()
        self.generation += 1
        self.selection = selection
        self.points = []
        fade(self.hint,False)
        crop = self.crop()
        fade(self.bar,False)
        self.sheet.bar.set_selection(crop if selection.kind == "image" else None, selection.text)
        self.position_text_actions()
        self.sheet.loading("Searching…" if self.auto_search else "Selection ready. Press Enter to search.")
        self.selected.emit(crop, selection.bounds.translated(QPointF(self.screen().geometry().topLeft())))
        self.update()
        if self.auto_search:
            self.submit(selection.text)

    def submit(self, query):
        if not query and (self.selection is None or self.selection.kind == "text"):
            return
        self.generation += 1
        fade(self.bar,False)
        if not self.selection or self.selection.kind == "text":
            if query:
                self.sheet.bar.set_selection(text=query)
                self.sheet.loading()
                self.display_url(text_search_url(query))
            return
        generation = self.generation
        self.sheet.loading("Searching with Google Lens…")
        self.sheet.bar.query.setText(query)
        if not self.external:
            self.sheet.search_image(encode_png(self.crop()),query)
            return
        self.run_task(upload_to_lens, (encode_png(self.crop()), query),
                      lambda url: self.display_url(url) if generation == self.generation else None,
                      lambda error: self.sheet.error(error) if generation == self.generation else None)

    def display_url(self, url):
        if self.external:
            self.sheet.current_url = url
            self.sheet.external.setEnabled(True)
            self.externalRequested.emit(QUrl(url))
        else:
            self.sheet.load_url(url)

    def search_image(self):
        if self.selection:
            self.selection = Selection("image", self.selection.bounds)
            self.sheet.bar.set_selection(self.crop())
            self.text_actions.dismiss()
            self.submit("")
            self.update()

    def translate(self):
        text = self.selection.text if self.selection and self.selection.kind == "text" else self.document.text()
        if text:
            self.generation += 1
            fade(self.bar,False)
            self.sheet.loading("Translating…")
            self.display_url(translation_url(text,"en"))

    def copy_text(self):
        if self.selection and self.selection.kind == "text":
            QApplication.clipboard().setText(self.selection.text)

    def copy_image(self):
        if self.selection:
            QApplication.clipboard().setImage(self.crop())

    def save_image(self):
        if not self.selection:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save selected image", "selection.png", "PNG image (*.png)")
        if path and not self.crop().save(path, "PNG"):
            self.sheet.error("Could not save the image. Choose a writable location.")

    def clear_selection(self):
        self.generation += 1
        self.region_token = None
        if self.document_is_regional:
            self.document=self.full_document if self.full_document is not None else Document([])
            self.document_is_regional=False
        self.pending_gesture = None
        self.dragging = False
        self.drag_handle = None
        self.selection = None
        self.points = []
        self.selection_reveal.stop()
        self.sheet.stop(animate=True)
        self.text_actions.dismiss()
        self.bar.set_selection()
        fade(self.bar,True)
        self.hint.setText("Circle, highlight, scribble or tap to search")
        self.hint.adjustSize()
        fade(self.hint,True)
        self.resizeEvent(None)
        self.update()

    def back(self):
        if self.closing:return
        if self.ocr_settings_panel is not None:
            self.ocr_settings_panel.dialog.reject()
            return
        if self.selection or (self.sheet.isVisible() and not self.sheet.dismissing) or self.pending_gesture:
            self.clear_selection()
        else:
            self.cancelled.emit()

    def edit_ocr_settings(self):
        if self.ocr_settings_panel is not None:
            self.ocr_settings_panel.raise_()
            return
        from .ocr_settings import OcrSettingsPanel
        self.dragging=False
        self.drag_handle=None
        self.points=[]
        panel=OcrSettingsPanel(self)
        self.ocr_settings_panel=panel
        panel.finished.connect(self.ocr_settings_finished)
        self.search_shortcut.setEnabled(False)
        self.vertical_shortcut.setEnabled(False)
        self.text_actions.dismiss()
        panel.present()

    def ocr_settings_finished(self,result):
        panel=self.ocr_settings_panel
        self.ocr_settings_panel=None
        self.search_shortcut.setEnabled(True)
        self.vertical_shortcut.setEnabled(True)
        self.setFocus(Qt.OtherFocusReason)
        self.position_text_actions()
        if result==QDialog.DialogCode.Accepted:self.ocrSettingsChanged.emit()

    def show_menu(self):
        menu = QMenu(self)
        menu.addAction("New selection", self.clear_selection)
        menu.addAction("Copy text", self.copy_text).setEnabled(bool(self.selection and self.selection.kind == "text"))
        menu.addAction("Copy image", self.copy_image).setEnabled(self.selection is not None)
        menu.addAction("Save image…", self.save_image).setEnabled(self.selection is not None)
        menu.addSeparator()
        manager=theme_manager()
        if manager:
            themes=menu.addMenu("Theme")
            group=QActionGroup(themes)
            group.setExclusive(True)
            for mode,label in (("auto","Automatic (Plasma)"),("light","Light"),("dark","Dark")):
                action=themes.addAction(label)
                action.setCheckable(True)
                action.setChecked(manager.mode==mode)
                group.addAction(action)
                action.triggered.connect(lambda checked,mode=mode:manager.set_mode(mode))
            menu.addSeparator()
        automatic = menu.addAction("Search automatically after selecting")
        automatic.setCheckable(True)
        automatic.setChecked(self.auto_search)
        automatic.toggled.connect(lambda value: setattr(self, "auto_search", value))
        menu.addAction("Text recognition…",self.edit_ocr_settings)
        vertical = menu.addAction("Vertical Japanese text")
        vertical.setCheckable(True)
        vertical.setChecked(self.vertical)
        vertical.triggered.connect(self.toggle_vertical)
        move = menu.addAction("Move search bar to bottom" if self.bar_at_top else "Move search bar to top")
        def move_bar():
            previous=self.bar.pos()
            previous_hint=self.hint.pos()
            self.bar_at_top = not self.bar_at_top
            self.bar_top=None
            self.resizeEvent(None)
            destination=self.bar.pos()
            self.bar.move(previous)
            move(self.bar,destination)
            hint_destination=self.hint.pos()
            self.hint.move(previous_hint)
            move(self.hint,hint_destination)
        move.triggered.connect(move_bar)
        menu.addSeparator()
        menu.addAction("Open Google Lens", lambda: self.externalRequested.emit(QUrl("https://www.google.com/imghp")))
        menu.addAction("Close", self.cancelled.emit)
        menu.popup(self.more_button.mapToGlobal(self.more_button.rect().bottomRight()))

    def closeEvent(self, event):
        event.ignore()
        self.cancelled.emit()
