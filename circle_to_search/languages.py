"""Display and OCR preferences, saved independently."""

from functools import lru_cache

from PySide6.QtCore import QSettings

DISPLAY_LANGUAGES = {"en": "English", "pl": "Polski"}
GOOGLE_LANGUAGES = {"en": "en-US,en;q=0.9", "pl": "pl-PL,pl;q=0.9,en;q=0.5"}
DEFAULT_OCR = ("jpn", "eng", "jpn_vert")


def settings():
    return QSettings("circle-to-search", "languages")


@lru_cache(maxsize=1)
def display_language():
    code = settings().value("display", "en", type=str)
    return code if code in DISPLAY_LANGUAGES else "en"


def set_display_language(code):
    if code not in DISPLAY_LANGUAGES:
        raise ValueError(code)
    preferences = settings()
    preferences.setValue("display", code)
    preferences.sync()
    display_language.cache_clear()


def selected_models():
    return tuple(settings().value("ocr", "+".join(DEFAULT_OCR), type=str).split("+"))


def set_selected_models(codes):
    preferences = settings()
    preferences.setValue("ocr", "+".join(codes))
    preferences.sync()


def tr(message):
    if display_language() == "pl":
        from .polish import POLISH

        return POLISH.get(message, message)
    return message


def retranslate_widgets(root, previous):
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QAbstractButton, QLabel, QLineEdit, QMenu, QWidget

    from .polish import POLISH

    reverse = {value: key for key, value in POLISH.items()} if previous == "pl" else {}

    def update(widget, getter, setter):
        value = getter()
        translated = tr(reverse.get(value, value))
        if translated != value:
            setter(translated)

    for widget in root.findChildren(QWidget):
        update(widget, widget.toolTip, widget.setToolTip)
        update(widget, widget.accessibleName, widget.setAccessibleName)
        if isinstance(widget, (QLabel, QAbstractButton)):
            update(widget, widget.text, widget.setText)
        if isinstance(widget, QLineEdit):
            update(widget, widget.placeholderText, widget.setPlaceholderText)
        if isinstance(widget, QMenu):
            update(widget, widget.title, widget.setTitle)
    for action in root.findChildren(QAction):
        update(action, action.text, action.setText)
