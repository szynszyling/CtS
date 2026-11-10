"""Fetch pinned official Tesseract models and verify their SHA-256 digests."""

import hashlib
import json
import sys
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1] / "circle_to_search/tessdata"


def fetch_models(destination=ROOT):
    destination = Path(destination)
    manifest = json.loads((ROOT / "models.json").read_text())
    destination.mkdir(parents=True, exist_ok=True)
    for model in manifest["models"]:
        output = destination / (model["name"] + ".traineddata")
        if output.exists() and hashlib.sha256(output.read_bytes()).hexdigest() == model["sha256"]:
            continue
        url = f'https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/{manifest["revision"]}/{model["name"]}.traineddata'
        print("Downloading official OCR model:", model["name"], flush=True)
        with urlopen(url, timeout=90) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != model["sha256"]:
            raise RuntimeError("OCR model checksum did not match: " + model["name"])
        temporary = output.with_suffix(".part")
        temporary.write_bytes(data)
        temporary.replace(output)
    print("English, Japanese and vertical Japanese OCR models are ready.")


if __name__ == "__main__":
    fetch_models(Path(sys.argv[1]) if len(sys.argv)>1 else ROOT)
