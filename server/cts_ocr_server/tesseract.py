"""Read bundled Tesseract models and return boxes in the upload's coordinates."""

import os
import shutil
import subprocess
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree

from PIL import Image


class TesseractEngine:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.binary = shutil.which("tesseract")
        if not self.binary:
            raise RuntimeError("Install Tesseract to use the bundled language packs.")
        self.languages = frozenset(path.stem for path in self.directory.glob("*.traineddata"))
        if not self.languages:
            raise RuntimeError("No Tesseract models found in the configured directory.")

    def recognize(self, image, language, vertical):
        scale = min(3.0, max(1.0, 3600 / max(image.size)))
        prepared = image.convert("L").resize(
            (round(image.width * scale), round(image.height * scale)),
            Image.Resampling.LANCZOS,
        )
        buffer = BytesIO()
        prepared.save(buffer, format="PNG", dpi=(300, 300))
        result = subprocess.run(
            [
                self.binary,
                "stdin",
                "stdout",
                "--tessdata-dir",
                str(self.directory),
                "-l",
                language,
                "--oem",
                "1",
                "--psm",
                "5" if vertical else "11",
                "-c",
                "hocr_char_boxes=1",
                "-c",
                "tessedit_create_hocr=1",
            ],
            input=buffer.getvalue(),
            capture_output=True,
            timeout=35,
            check=True,
            env={**os.environ, "OMP_THREAD_LIMIT": "2"},
        )
        return glyph_boxes(result.stdout, image.size, prepared.size)


def glyph_boxes(hocr, image_size, prepared_size):
    spans = ElementTree.fromstring(hocr).findall(".//{*}span")
    sx, sy = (original / prepared for original, prepared in zip(image_size, prepared_size))
    line = word = ""
    glyphs = []
    for span in spans:
        kind = span.get("class", "")
        if kind in {"ocr_line", "ocr_caption", "ocr_header", "ocr_textfloat"}:
            line = span.attrib["id"]
        elif kind == "ocrx_word":
            word = span.attrib["id"]
        elif kind == "ocrx_cinfo" and span.text:
            fields = dict(part.strip().split(" ", 1) for part in span.attrib["title"].split(";"))
            x1, y1, x2, y2 = map(int, fields["x_bboxes"].split())
            if x2 > x1 and y2 > y1:
                glyphs.append(
                    {
                        "text": span.text,
                        "bbox": [x1 * sx, y1 * sy, (x2 - x1) * sx, (y2 - y1) * sy],
                        "line": line,
                        "word": word,
                        "confidence": min(100.0, max(0.0, float(fields["x_conf"]))),
                    }
                )
    return glyphs
