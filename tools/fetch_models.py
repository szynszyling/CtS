"""Download the default or selected official OCR models."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from circle_to_search.models import DEFAULT_MODELS, MODEL_DIR, fetch_models, model_manifest

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", nargs="?", type=Path, default=MODEL_DIR)
    parser.add_argument(
        "--models",
        nargs="+",
        choices=[item["name"] for item in model_manifest()["models"]],
        default=DEFAULT_MODELS,
    )
    args = parser.parse_args()
    fetch_models(args.destination, args.models)
    print("Selected OCR models are ready.")
