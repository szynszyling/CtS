"""Local OCR with character boxes, including Japanese horizontal/vertical text."""

import re
import shutil
import subprocess
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import QImage

from .geometry import selection_bounds

MODEL_DIR = Path(__file__).with_name("tessdata")


def is_cjk(text: str) -> bool:
    return any(
        "\u3040" <= c <= "\u30ff"
        or "\u3400" <= c <= "\u9fff"
        or "\uff66" <= c <= "\uff9f"
        or ord(c) >= 0x20000
        for c in text
    )


def default_languages() -> str:
    return "jpn+eng"


def gesture_region(points, viewport: QRectF, vertical=False) -> QRectF:
    """Keep whole nearby words/characters while avoiding a screen-wide scan."""
    if not points:
        return QRectF()
    bounds = selection_bounds(points, viewport)
    # Leave context along the reading direction so a tap can select a whole
    # word and handles can extend beyond the original stroke. This also keeps
    # an underline's zero-height bounds from clipping the actual text.
    horizontal, vertical_padding = (64, 160) if vertical else (160, 64)
    return bounds.adjusted(
        -horizontal, -vertical_padding, horizontal, vertical_padding
    ).intersected(viewport)


@dataclass(frozen=True)
class Glyph:
    text: str
    rect: QRectF
    line: str
    word: str
    confidence: float = 100


@dataclass
class Document:
    glyphs: list[Glyph]
    error: str = ""

    def text(self, indices=None) -> str:
        indices = range(len(self.glyphs)) if indices is None else sorted(set(indices))
        result = ""
        previous = None
        for index in indices:
            glyph = self.glyphs[index]
            if previous:
                if glyph.line != previous.line:
                    result += "\n"
                elif glyph.word != previous.word and not is_cjk(previous.text + glyph.text):
                    result += " "
            result += glyph.text
            previous = glyph
        return result

    def bounds(self, indices) -> QRectF:
        rect = QRectF()
        for index in indices:
            rect = rect.united(self.glyphs[index].rect)
        return rect

    def highlights(self, indices) -> list[QRectF]:
        lines = {}
        for index in sorted(indices):
            glyph = self.glyphs[index]
            lines[glyph.line] = lines.get(glyph.line, QRectF()).united(glyph.rect)
        return [rect.adjusted(-2, -2, 2, 2) for rect in lines.values()]

    def expand_words(self, indices) -> list[int]:
        selected = set(indices)
        words = {self.glyphs[i].word for i in selected if not is_cjk(self.glyphs[i].text)}
        return [
            i
            for i, glyph in enumerate(self.glyphs)
            if i in selected or (glyph.word in words and not is_cjk(glyph.text))
        ]


class HocrParser(HTMLParser):
    def __init__(self, sx=1.0, sy=1.0):
        super().__init__(convert_charrefs=True)
        self.sx, self.sy = sx, sy
        self.line, self.word = "", ""
        self.stack = []
        self.glyphs = []
        self.line_bounds = {}

    def handle_starttag(self, tag, attrs):
        if tag != "span":
            return
        attrs = dict(attrs)
        kind = attrs.get("class", "")
        self.stack.append((kind, self.line, self.word, attrs))
        if kind in ("ocr_line", "ocrx_line"):
            self.line = attrs.get("id", "")
            box = re.search(r"bbox (\d+) (\d+) (\d+) (\d+)", attrs.get("title", ""))
            if box:
                x1, y1, x2, y2 = map(int, box.groups())
                self.line_bounds[self.line] = QRectF(
                    x1 / self.sx, y1 / self.sy, (x2 - x1) / self.sx, (y2 - y1) / self.sy
                )
        elif kind == "ocrx_word":
            self.word = attrs.get("id", "")

    def handle_endtag(self, tag):
        if tag == "span" and self.stack:
            _, self.line, self.word, _ = self.stack.pop()

    def handle_data(self, data):
        if not self.stack or self.stack[-1][0] != "ocrx_cinfo" or not data.strip():
            return
        title = self.stack[-1][3].get("title", "")
        match = re.search(r"x_bboxes (\d+) (\d+) (\d+) (\d+)", title)
        if not match:
            return
        x1, y1, x2, y2 = map(int, match.groups())
        confidence = re.search(r"x_conf ([\d.]+)", title)
        self.glyphs.append(
            Glyph(
                data,
                QRectF(x1 / self.sx, y1 / self.sy, (x2 - x1) / self.sx, (y2 - y1) / self.sy),
                self.line,
                self.word,
                float(confidence[1]) if confidence else 100,
            )
        )


def encode_png(image: QImage) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise RuntimeError("Could not encode the selected image.")
    return bytes(data)


def repair_vertical_boxes(document: Document, image: QImage, line_bounds) -> Document:
    """Tesseract 5 can emit zero-width vertical character boxes.

    The line boxes and recognized text are correct. Locate the ink runs within
    each column to recover usable character positions in the original image.
    """
    result = list(document.glyphs)
    for line, rect in line_bounds.items():
        indices = [i for i, g in enumerate(result) if g.line == line]
        if not indices or all(result[i].rect.width() > 0 for i in indices):
            continue
        clipped = rect.toAlignedRect().intersected(image.rect())
        column = image.copy(clipped).convertToFormat(QImage.Format.Format_Grayscale8)
        raw = column.constBits()
        stride = column.bytesPerLine()
        samples = [
            raw[y * stride + x]
            for y in range(0, column.height(), 3)
            for x in range(0, column.width(), 3)
        ]
        background = sorted(samples)[len(samples) // 2] if samples else 255
        rows = [
            y
            for y in range(column.height())
            if any(abs(raw[y * stride + x] - background) > 65 for x in range(column.width()))
        ]
        runs = []
        for y in rows:
            if runs and y - runs[-1][1] <= 3:
                runs[-1][1] = y
            else:
                runs.append([y, y])
        if len(runs) != len(indices):
            runs = [
                [
                    round(n * column.height() / len(indices)),
                    round((n + 1) * column.height() / len(indices)) - 1,
                ]
                for n in range(len(indices))
            ]
        for i, (top, bottom) in zip(indices, runs):
            glyph = result[i]
            box = QRectF(clipped.x(), clipped.y() + top, clipped.width(), max(1, bottom - top + 1))
            result[i] = Glyph(glyph.text, box, glyph.line, glyph.word, glyph.confidence)
    return Document(result)


def recognize_tesseract(
    image: QImage, language: str | None = None, vertical: bool = False
) -> Document:
    if not shutil.which("tesseract"):
        raise RuntimeError("Install Tesseract to select text. Image search is still available.")
    language = language or default_languages()
    if vertical:
        language = "jpn_vert"
    # Small desktop glyphs need more pixels for Japanese strokes. Work at 2x
    # where possible, without making a large multi-monitor capture enormous.
    scale = min(3.0, max(1.0, 3600 / max(image.width(), image.height())))
    prepared = image.convertToFormat(QImage.Format.Format_Grayscale8)
    if scale > 1:
        prepared = prepared.scaled(
            round(image.width() * scale),
            round(image.height() * scale),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    prepared.setDotsPerMeterX(11811)
    prepared.setDotsPerMeterY(11811)
    command = [
        "tesseract",
        "stdin",
        "stdout",
        "-l",
        language,
        "--oem",
        "1",
        "--psm",
        "5" if vertical else "11",
        "-c",
        "hocr_char_boxes=1",
    ]
    requested = language.split("+")
    if all((MODEL_DIR / f"{name}.traineddata").exists() for name in requested):
        command.extend(["--tessdata-dir", str(MODEL_DIR)])
    else:
        available = subprocess.run(
            ["tesseract", "--list-langs"], capture_output=True, text=True, timeout=10
        ).stdout.splitlines()[1:]
        missing = set(requested) - set(available)
        if missing:
            raise RuntimeError(
                "OCR language data is missing: "
                + ", ".join(sorted(missing))
                + ". Reinstall Circle to Search or install the matching Tesseract language packs."
            )
    # Use the output switch, rather than a system hocr config file, so bundled
    # model directories work on distributions that keep configs elsewhere.
    command.extend(["-c", "tessedit_create_hocr=1"])
    try:
        result = subprocess.run(
            command, input=encode_png(prepared), capture_output=True, timeout=35
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Text recognition took too long. Try a smaller selection.") from exc
    if result.returncode:
        detail = result.stderr.decode(errors="replace").strip()[-450:]
        raise RuntimeError(
            f"Could not read text with {language}. Check the OCR language models. {detail}"
        )
    parser = HocrParser(prepared.width() / image.width(), prepared.height() / image.height())
    parser.feed(result.stdout.decode("utf-8", errors="replace"))
    document = Document(parser.glyphs)
    return repair_vertical_boxes(document, image, parser.line_bounds) if vertical else document


def recognize_document(
    image: QImage, language: str | None = None, vertical: bool = False, priority="background"
) -> Document:
    if image.isNull():
        return Document([])
    from .ocr_backend import current_config, recognize_remote

    config = current_config()
    fallback = config.fallback
    if config.backend in ("gpu", "server"):
        try:
            if config.backend == "gpu":
                from .platforms import get_backend

                config = get_backend().ensure_local_ocr(config)
            return recognize_remote(
                image, language or default_languages(), vertical, priority, config
            )
        except RuntimeError:
            if not fallback:
                raise
    return recognize_tesseract(image, language, vertical)
