"""Optional OCR models from a pinned Tesseract release tree."""

import hashlib
import json
import tempfile
from pathlib import Path
from urllib.request import urlopen

MODEL_DIR = Path(__file__).with_name("tessdata")
DEFAULT_MODELS = ("eng", "jpn", "jpn_vert")


def model_manifest():
    return json.loads((MODEL_DIR / "models.json").read_text(encoding="utf-8"))


def fetch_models(destination=MODEL_DIR, codes=DEFAULT_MODELS):
    manifest = model_manifest()
    models = {item["name"]: item for item in manifest["models"]}
    codes = tuple(dict.fromkeys(codes))
    if not codes or any(code not in models for code in codes):
        raise ValueError("Select one or more supported OCR models.")
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for code in codes:
        entry = models[code]
        output = destination / f"{code}.traineddata"
        source = MODEL_DIR / output.name
        expected = entry["sha256"]
        if output.is_file() and hashlib.sha256(output.read_bytes()).hexdigest() == expected:
            continue
        data = source.read_bytes() if source.is_file() else b""
        if hashlib.sha256(data).hexdigest() != expected:
            revision = manifest["revision"]
            url = f"https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/{revision}/{output.name}"
            with urlopen(url, timeout=45) as response:
                data = response.read(entry["bytes"] + 1)
        if len(data) != entry["bytes"] or hashlib.sha256(data).hexdigest() != expected:
            raise RuntimeError(f"OCR model checksum did not match: {code}")
        with tempfile.NamedTemporaryFile(dir=destination, delete=False) as stream:
            temporary = Path(stream.name)
            try:
                stream.write(data)
                stream.close()
                temporary.replace(output)
            finally:
                temporary.unlink(missing_ok=True)
