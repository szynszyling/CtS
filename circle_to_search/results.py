"""Google results in a resizable bottom sheet; the desktop stays visible."""

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedLayout,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import delete, isValid

from .appearance import current_theme, theme_manager
from .languages import GOOGLE_LANGUAGES, display_language, tr
from .search import (
    LENS_UPLOAD_URL,
    browser_search_url,
    external_navigation,
    lens_upload_data,
    normalize_search_url,
    search_tab,
    search_tab_url,
)
from .web_scripts import SEARCH_CHROME, SERVICE_THEME, TRANSLATE_CHROME
from .widgets import IconButton, SearchPill, SearchTabs, SheetHandle


def close_browser_profile(app):
    profile = getattr(app, "_cts_browser_profile", None)
    if profile is not None:
        for widget in app.allWidgets():
            if isValid(widget) and getattr(widget, "profile", None) is profile:
                delete(widget)
        delete(profile)
        app._cts_browser_profile = None


def create_browser(parent):
    # Lazy import: selection and offline copy also work without Qt WebEngine.
    from PySide6.QtNetwork import QNetworkCookie
    from PySide6.QtWebEngineCore import (
        QWebEngineHttpRequest,
        QWebEnginePage,
        QWebEngineProfile,
        QWebEngineScript,
        QWebEngineSettings,
    )
    from PySide6.QtWebEngineWidgets import QWebEngineView

    class Browser(QWebEngineView):
        externalRequested = Signal(QUrl)

        def __init__(self, parent):
            super().__init__(parent)
            self.cookie_ready = False
            self.pending_url = None
            self.image_query = None
            self.cookie_timer = QTimer(self)
            self.cookie_timer.setSingleShot(True)
            self.cookie_timer.timeout.connect(self.load_pending)

        def load(self, url):
            self.profile.setHttpAcceptLanguage(GOOGLE_LANGUAGES[display_language()])
            self.pending_url = url
            if self.cookie_ready:
                self.load_pending()
            else:
                self.cookie_timer.start(1500)

        def load_pending(self):
            self.cookie_timer.stop()
            if self.pending_url is not None:
                url, self.pending_url = self.pending_url, None
                super().load(url)

        def cookie_added(self, cookie):
            if bytes(cookie.name()) == b"SOCS":
                self.cookie_ready = True
                self.load_pending()

        def stop(self):
            self.cookie_timer.stop()
            self.pending_url = None
            super().stop()

        def upload_image(self, png, query=""):
            self.image_query = query
            body, content_type = lens_upload_data(png)
            request = QWebEngineHttpRequest(
                QUrl(LENS_UPLOAD_URL + "?hl=" + display_language() + "&ep=ccm&s=csp")
            )
            request.setMethod(QWebEngineHttpRequest.Method.Post)
            request.setHeader(b"Content-Type", content_type.encode())
            request.setPostData(body)
            self.load(request)

        def apply_theme(self, theme):
            self.page().setBackgroundColor(QColor(theme.background))
            # Reapply preferences after QStyleHints updates Chromium NativeTheme.
            # This uses Google's own dark UI, preserving images and video colors.
            self.settings().setAttribute(QWebEngineSettings.WebAttribute.ForceDarkMode, False)

        def preferred_results_url(self):
            url = normalize_search_url(self.url().toString())
            if self.image_query is not None and self.url().path() == "/search":
                if self.image_query:
                    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

                    parts = urlsplit(url)
                    params = dict(parse_qsl(parts.query, keep_blank_values=True))
                    params.update(q=self.image_query, udm="24", lns_mode="mu")
                    url = urlunsplit(parts._replace(query=urlencode(params)))
                self.image_query = None
            return QUrl(url)

    class Page(QWebEnginePage):
        def __init__(self, profile, parent, new_window=False):
            super().__init__(profile, parent)
            self.new_window = new_window

        def acceptNavigationRequest(self, url, kind, main_frame):
            if main_frame and external_navigation(url.toString(), self.new_window):
                # Reject this navigation before dismissing/stopping its view.
                # Stopping Chromium reentrantly inside this callback can crash.
                QTimer.singleShot(
                    0, view, lambda target=QUrl(url): view.externalRequested.emit(target)
                )
                if self.new_window:
                    self.deleteLater()
                return False
            return True

        def createWindow(self, kind):
            return Page(self.profile(), self, new_window=True)

    theme = current_theme()
    app = QApplication.instance()
    app.styleHints().setColorScheme(Qt.ColorScheme.Dark if theme.dark else Qt.ColorScheme.Light)
    view = Browser(parent)
    profile = getattr(app, "_cts_browser_profile", None)
    first_view = profile is None
    if first_view:
        # A dismissed tray session can outlive its overlay while OCR finishes.
        # All views must share the one profile for this on-disk storage name.
        profile = QWebEngineProfile("circle-to-search", app)
        app._cts_browser_profile = profile
        profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies
        )
        profile.setHttpAcceptLanguage(GOOGLE_LANGUAGES[display_language()])
        profile.settings().setUnknownUrlSchemePolicy(
            QWebEngineSettings.AllowUnknownUrlSchemesFromUserInteraction
        )
    page = Page(profile, view)
    page.setBackgroundColor(QColor(theme.background))
    page.settings().setAttribute(QWebEngineSettings.WebAttribute.ForceDarkMode, False)
    # The native sheet supplies the search field. Remove only Google's duplicate
    # search header; Google's actual results, links and consent UI remain intact.
    script = QWebEngineScript()
    script.setName("circle-to-search-header")
    script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
    script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
    script.setSourceCode(SEARCH_CHROME + "\n" + TRANSLATE_CHROME + "\n" + SERVICE_THEME)
    page.scripts().insert(script)
    navigation_script = QWebEngineScript()
    navigation_script.setName("circle-to-search-tab-preferences")
    navigation_script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
    navigation_script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
    navigation_script.setSourceCode("""window.addEventListener('click',event=>{
        if (event.button!==0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        const link=event.target.closest && event.target.closest('a[href]');
        if (!link || link.target==='_blank') return;
        const url=new URL(link.href,location.href);
        if (!['www.google.com','google.com','lens.google.com'].includes(url.hostname) || url.pathname!=='/search') return;
        for (const key of ['cs','gl','gsc','lr']) url.searchParams.delete(key);
        url.searchParams.set('hl', new URL(location.href).searchParams.get('hl') || navigator.language.split('-')[0]);
        event.preventDefault(); event.stopImmediatePropagation();
        location.assign(url.href);
    },true);""")
    page.scripts().insert(navigation_script)
    view.setPage(page)
    view.profile = profile
    if first_view:
        cookie = QNetworkCookie(b"SOCS", b"CAI")
        cookie.setDomain(".google.com")
        cookie.setPath("/")
        profile.cookieStore().cookieAdded.connect(view.cookie_added)
        profile.cookieStore().setCookie(cookie, QUrl("https://www.google.com"))
    else:
        view.cookie_ready = True
    return view


class ResultSheet(QFrame):
    cleared = Signal()
    urlChanged = Signal(str)
    presented = Signal()
    externalRequested = Signal(QUrl)

    def __init__(self, parent, browser_factory=create_browser):
        super().__init__(parent)
        self.load_deadline = QTimer(self)
        self.load_deadline.setSingleShot(True)
        self.load_deadline.setInterval(25000)
        self.load_deadline.timeout.connect(self.load_timed_out)
        self.load_expired = False
        self.setObjectName("sheet")
        self.setAttribute(Qt.WA_NoMousePropagation)
        self.theme = current_theme()
        self.browser_factory = browser_factory
        self.browser = None
        self.current_url = ""
        self.last_error_code = 0
        self.preferred_redirects = set()
        self.display_generation = 0
        self.navigation_in_progress = False
        self.theme_reload_pending = False
        self.expanded = False
        self.user_resized = False
        self.dismissing = False
        self.sheet_height = min(470, round(parent.height() * 0.44))
        self.left_position = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 12)
        layout.setSpacing(8)
        handle_row = QHBoxLayout()
        handle_row.setSpacing(0)
        self.back = IconButton("back", tr("Back to selection"))
        self.back.clicked.connect(self.cleared.emit)
        handle_row.addWidget(self.back)
        self.handle = SheetHandle()
        self.handle.dragged.connect(self.move_and_resize)
        self.handle.clicked.connect(self.toggle)
        handle_row.addWidget(self.handle, 1)
        self.external = IconButton("external", tr("Open results in your browser"))
        self.external.setEnabled(False)
        self.external.clicked.connect(self.open_external)
        handle_row.addWidget(self.external)
        layout.addLayout(handle_row)
        self.bar = SearchPill()
        self.bar.enable_dragging()
        self.bar.dragged.connect(self.move_and_resize)
        layout.addWidget(self.bar)
        self.tabs = SearchTabs()
        self.tabs.requested.connect(self.navigate_tab)
        self.tabs.filterRequested.connect(self.filter_time)
        layout.addWidget(self.tabs)
        self.verification = QLabel(tr("Complete Google's verification below to continue."))
        self.verification.setObjectName("status")
        self.verification.setWordWrap(True)
        self.verification.hide()
        layout.addWidget(self.verification)
        self.content = QStackedWidget()
        # Keep Chromium rendering beneath an opaque cover. Hiding the view
        # leaves its previous (possibly dark) frame cached until it is shown.
        self.content.layout().setStackingMode(QStackedLayout.StackingMode.StackAll)
        self.content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        self.message_page = QWidget()
        self.message_page.setObjectName("loadingCover")
        self.message_page.setStyleSheet(
            "QWidget#loadingCover { background: " + self.theme.background + "; }"
        )
        messages = QVBoxLayout(self.message_page)
        messages.addStretch()
        self.message = QLabel(tr("Searching…"))
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message.setWordWrap(True)
        self.message.setObjectName("status")
        messages.addWidget(self.message)
        self.fallback = QPushButton(tr("Open in browser"))
        self.fallback.clicked.connect(self.open_external)
        self.fallback.hide()
        messages.addWidget(self.fallback, alignment=Qt.AlignmentFlag.AlignCenter)
        messages.addStretch()
        self.content.addWidget(self.message_page)
        layout.addWidget(self.content, 1)
        self.animation = QPropertyAnimation(self, b"geometry", self)
        self.animation.setDuration(220)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.finished.connect(self.finish_motion)
        self.hide()
        manager = theme_manager()
        if manager:
            manager.aboutToChange.connect(self.cover_theme_change)
            manager.changed.connect(self.apply_theme)

    def cover_theme_change(self, theme):
        self.display_generation += 1
        self.theme = theme
        self.message_page.setStyleSheet(
            "QWidget#loadingCover { background: " + theme.background + "; }"
        )
        self.content.setCurrentWidget(self.message_page)

    def apply_theme(self, theme):
        self.tabs.apply_theme(theme)
        if not self.browser:
            return
        if hasattr(self.browser, "apply_theme"):
            self.browser.apply_theme(theme)
        if not self.isVisible():
            return
        if self.verification.isVisible():
            # Never reload or hide an in-progress challenge. Its isolated
            # verification frame may retain Google's own fixed colors.
            self.content.setCurrentWidget(self.browser)
            return
        url = self.browser.url() if callable(getattr(self.browser, "url", None)) else QUrl()
        google = url.host() in (
            "www.google.com",
            "google.com",
            "lens.google.com",
            "translate.google.com",
        )
        if google:
            # Search renders some colors on the server. Preserve the complete
            # URL/profile, including Lens session parameters, when reloading.
            if self.navigation_in_progress:
                self.theme_reload_pending = True
            else:
                self.browser.reload()
        elif not self.navigation_in_progress:
            QTimer.singleShot(100, self.reveal_themed_page)

    def target_geometry(self):
        parent = self.parentWidget()
        if not self.expanded and not self.user_resized:
            self.sheet_height = min(470, round(parent.height() * 0.44))
        width = min(760, parent.width() - 32)
        height = min(self.sheet_height, parent.height() - 84)
        left = (
            (parent.width() - width) // 2
            if self.left_position is None
            else max(16, min(self.left_position, parent.width() - width - 16))
        )
        return QRect(left, parent.height() - height, width, height)

    def shift_by(self, delta):
        if self.dismissing:
            return
        running = self.animation.state() == QPropertyAnimation.Running
        remaining = max(1, self.animation.duration() - self.animation.currentTime())
        self.left_position = max(
            16, min(round(self.x() + delta), self.parentWidget().width() - self.width() - 16)
        )
        self.animation.stop()
        self.move(self.left_position, self.y())
        if running:
            self.animation.setDuration(remaining)
            self.animation.setStartValue(self.geometry())
            self.animation.setEndValue(self.target_geometry())
            self.animation.start()

    def blocks_selection(self, point):
        if not self.isVisible():
            return False
        bounds = self.geometry()
        if not self.dismissing and self.animation.state() == QPropertyAnimation.Running:
            bounds = bounds.united(self.animation.endValue())
        return bounds.contains(point.toPoint())

    def show_sheet(self, animate=True):
        target = self.target_geometry()
        was_visible = self.isVisible()
        was_dismissing = self.dismissing
        self.dismissing = False
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        if (
            animate
            and was_visible
            and not was_dismissing
            and self.animation.state() == QPropertyAnimation.Running
            and self.animation.endValue() == target
        ):
            return  # loading and load_url may request the same presentation
        if not animate:
            self.animation.stop()
            self.setGeometry(target)
            self.show()
            self.raise_()
            self.presented.emit()
            return
        self.animation.stop()
        if not was_visible:
            self.setGeometry(target.translated(0, target.height()))
        self.show()
        self.raise_()
        self.presented.emit()
        self.animation.setDuration(220)
        self.animation.setStartValue(self.geometry())
        self.animation.setEndValue(target)
        self.animation.start()

    def finish_motion(self):
        if self.dismissing:
            self.hide()
            self.dismissing = False

    def resize_by(self, delta):
        self.move_and_resize(0, -delta)

    def move_and_resize(self, dx, dy):
        if self.dismissing:
            return
        if not dy:
            self.shift_by(dx)
            return
        self.animation.stop()
        self.user_resized = True
        self.left_position = max(
            16, min(round(self.x() + dx), self.parentWidget().width() - self.width() - 16)
        )
        self.sheet_height = max(
            220, min(self.parentWidget().height() - 84, round(self.height() - dy))
        )
        self.setGeometry(self.target_geometry())

    def toggle(self):
        self.expanded = not self.expanded
        self.user_resized = False
        self.sheet_height = (
            self.parentWidget().height() - 84
            if self.expanded
            else min(470, round(self.parentWidget().height() * 0.44))
        )
        self.show_sheet(True)

    def loading(self, text=None):
        self.load_expired = False
        self.display_generation += 1
        self.current_url = ""
        self.last_error_code = 0
        self.theme_reload_pending = False
        self.preferred_redirects.clear()
        self.verification.hide()
        self.external.setEnabled(False)
        self.tabs.setEnabled(bool(self.bar.query.text().strip()))
        self.tabs.show()
        self.message.setText(text or tr("Searching…"))
        self.fallback.hide()
        self.content.setCurrentWidget(self.message_page)
        self.show_sheet()

    def error(self, text):
        self.load_deadline.stop()
        self.message.setText(text)
        self.fallback.setVisible(bool(self.current_url))
        self.content.setCurrentWidget(self.message_page)

    def load_url(self, url):
        self.load_expired = False
        url = normalize_search_url(url)
        self.current_url = url
        self.last_error_code = 0
        self.external.setEnabled(True)
        self.tabs.set_active(search_tab(url))
        self.tabs.setEnabled(True)
        self.tabs.setVisible(
            QUrl(url).host() in ("www.google.com", "google.com", "lens.google.com")
            and QUrl(url).path() == "/search"
        )
        self.urlChanged.emit(url)
        try:
            self.ensure_browser()
            self.content.setCurrentWidget(self.message_page)
            self.load_deadline.start()
            self.browser.load(QUrl(url))
        except ImportError:
            self.error(
                "Install Qt WebEngine for results here, or open this search in your browser."
            )
        self.show_sheet()

    def ensure_browser(self):
        if self.browser is None:
            self.browser = self.browser_factory(self.content)
            if hasattr(self.browser, "externalRequested"):
                self.browser.externalRequested.connect(self.externalRequested.emit)
            self.browser.loadFinished.connect(self.loaded)
            if hasattr(self.browser, "loadStarted"):
                self.browser.loadStarted.connect(self.navigation_started)
            self.browser.page().loadingChanged.connect(self.loading_info)
            if hasattr(self.browser, "urlChanged"):
                self.browser.urlChanged.connect(self.browser_url_changed)
            self.content.addWidget(self.browser)

    def browser_url_changed(self, url):
        if url.host() in ("www.google.com", "lens.google.com") and url.path() == "/search":
            self.current_url = url.toString()
            self.external.setEnabled(True)
            self.tabs.set_active(search_tab(url.toString()))
            self.tabs.setEnabled(True)
            preferred = QUrl(normalize_search_url(url.toString()))
            if (
                not self.navigation_in_progress
                and preferred != url
                and preferred.toString() not in self.preferred_redirects
            ):
                # Google can change tabs through history.pushState instead of
                # a full navigation. Cover that transition as soon as its URL
                # changes; loaded() will normalize ordinary redirects.
                self.display_generation += 1
                self.content.setCurrentWidget(self.message_page)
                self.preferred_redirects.add(preferred.toString())
                self.navigation_in_progress = True
                self.load_deadline.start()
                QTimer.singleShot(0, lambda: self.browser.load(preferred))

    def navigate_tab(self, tab):
        url = search_tab_url(self.current_url, tab, self.bar.query.text().strip())
        self.loading()
        self.load_url(url)

    def filter_time(self, period):
        from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

        parts = urlsplit(
            self.current_url or search_tab_url("", "all", self.bar.query.text().strip())
        )
        params = dict(parse_qsl(parts.query, keep_blank_values=True))
        params.pop("start", None)
        if period:
            params["tbs"] = "qdr:" + period
        else:
            params.pop("tbs", None)
        url = urlunsplit(parts._replace(query=urlencode(params)))
        self.loading()
        self.load_url(url)

    def search_image(self, png, query=""):
        self.loading(tr("Searching with Google Lens…"))
        try:
            self.ensure_browser()
            self.content.setCurrentWidget(self.message_page)
            # The upload and resulting search use the same browser profile,
            # verification cookies and connection, preserving the Lens session.
            self.load_deadline.start()
            self.browser.upload_image(png, query)
        except ImportError:
            self.error("Install Qt WebEngine for image search here, or use --external.")

    def loaded(self, ok):
        if self.dismissing or self.load_expired:
            return
        self.navigation_in_progress = False
        if ok and self.browser:
            if self.theme_reload_pending:
                self.theme_reload_pending = False
                if self.browser.url().path() == "/search" and not self.verification.isVisible():
                    self.browser.reload()
                    return
            if hasattr(self.browser, "preferred_results_url"):
                preferred = self.browser.preferred_results_url()
                if (
                    preferred != self.browser.url()
                    and preferred.toString() not in self.preferred_redirects
                ):
                    self.preferred_redirects.add(preferred.toString())
                    self.navigation_in_progress = True
                    self.browser.load(preferred)
                    return
            self.verification.hide()
            self.reveal_themed_page()
        elif self.isVisible():
            # loadFinished(False) can mean an HTTP 429 page containing an
            # interactive Google CAPTCHA. loadingChanged supplies the status
            # after this signal; wait before choosing an error presentation.
            QTimer.singleShot(0, self.handle_failed_load)

    def navigation_started(self):
        self.load_expired = False
        if not self.load_deadline.isActive():
            self.load_deadline.start()
        self.navigation_in_progress = True
        self.display_generation += 1
        self.last_error_code = 0
        self.content.setCurrentWidget(self.message_page)

    def reveal_themed_page(self, attempt=0):
        generation = self.display_generation

        def reveal():
            if isValid(self) and generation == self.display_generation and self.isVisible():
                self.load_deadline.stop()
                self.content.setCurrentWidget(self.browser)

        if not hasattr(self.browser.page(), "runJavaScript"):
            reveal()
            return

        def checked(matches):
            if not isValid(self) or generation != self.display_generation or not self.isVisible():
                return
            if matches is True:
                # Let the visible Chromium view repaint beneath the cover.
                QTimer.singleShot(50, reveal)
            elif attempt < 160:

                def retry():
                    if isValid(self) and generation == self.display_generation:
                        self.reveal_themed_page(attempt + 1)

                QTimer.singleShot(50, retry)
            else:
                self.error(
                    "Google's results page did not finish applying the selected theme. Try the search again or open it in your browser."
                )

        self.browser.page().runJavaScript(
            """(() => {
            const dark=THEME_DARK;
            if (!document.body) return false;
            for (const element of [document.body,document.documentElement]) {
                const color=getComputedStyle(element).backgroundColor;
                const channels=color.match(/[\\d.]+/g);
                if (channels && (channels.length<4 || Number(channels[3])>0))
                    return (channels.slice(0,3).reduce((sum,c)=>sum+Number(c),0)<384)===dark;
            }
            return true;
        })()""".replace("THEME_DARK", "true" if self.theme.dark else "false"),
            checked,
        )

    def handle_failed_load(self):
        if not self.isVisible() or self.load_expired:
            return
        if self.last_error_code == -3:  # a previous navigation was superseded
            return
        if self.last_error_code >= 400 and self.browser:
            self.show_http_status(self.last_error_code)
        else:
            self.error(
                tr("Google could not load these results. Try opening the search in your browser.")
            )

    def loading_info(self, info):
        if self.load_expired:
            return
        self.last_error_code = info.errorCode()
        if info.errorCode() >= 400 and self.browser:
            # Rate-limit responses may carry real verification forms. A plain
            # access-denied response needs a different, truthful explanation.
            self.show_http_status(info.errorCode())

    def show_http_status(self, code):
        self.load_deadline.stop()
        self.theme_reload_pending = False
        if code == 429:
            self.content.setCurrentWidget(self.browser)
            self.verification.setText(
                tr(
                    "Google is limiting searches. Complete any verification shown below, or open this search in your browser."
                )
            )
        elif code == 403:
            self.verification.hide()
            self.error(
                tr(
                    "Google denied this embedded search (HTTP 403). Open the search in your normal browser to use its existing session."
                )
            )
            return
        else:
            self.content.setCurrentWidget(self.browser)
            self.verification.setText(
                f"Google returned HTTP {code}. Try again later or open this search in your browser."
            )
        self.verification.show()

    def open_external(self):
        if self.current_url:
            self.externalRequested.emit(QUrl(browser_search_url(self.current_url)))

    def load_timed_out(self):
        self.load_expired = True
        self.display_generation += 1
        self.navigation_in_progress = False
        self.theme_reload_pending = False
        self.browser.stop()
        self.error(
            tr("Google took too long to respond. Try again or open the search in your browser.")
        )

    def stop(self, animate=False):
        self.load_deadline.stop()
        self.theme_reload_pending = False
        self.display_generation += 1
        if self.browser:
            self.browser.stop()
        self.current_url = ""
        self.external.setEnabled(False)
        if animate and self.isVisible():
            if self.dismissing:
                return
            self.animation.stop()
            self.dismissing = True
            self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self.animation.setDuration(180)
            self.animation.setStartValue(self.geometry())
            self.animation.setEndValue(
                self.geometry().translated(0, self.parentWidget().height() - self.y())
            )
            self.animation.start()
        else:
            self.animation.stop()
            self.dismissing = False
            self.hide()
