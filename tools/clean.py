"""Remove generated build/cache files, preserving settings and downloaded models."""

import argparse
import shutil
from pathlib import Path


def generated_paths(root: Path) -> list[Path]:
    paths = []
    for project in (root, root / "server"):
        paths.extend(
            project / name
            for name in ("build", "dist", ".ruff_cache", ".pytest_cache", "__pycache__")
        )
        paths.extend(project.glob("*.egg-info"))
    for name in ("circle_to_search", "server", "tests", "tools"):
        for cache in (root / name).rglob("__pycache__"):
            if any(part.startswith(".") for part in cache.relative_to(root).parts):
                continue
            paths.append(cache)
    candidates = sorted(
        {path for path in paths if path.exists() or path.is_symlink()},
        key=lambda path: len(path.parts),
    )
    selected = []
    for path in candidates:
        if not any(parent in selected for parent in path.parents):
            selected.append(path)
    return selected


def clean(root: Path, dry_run=False) -> list[Path]:
    paths = generated_paths(root)
    for path in paths:
        if dry_run:
            continue
        if path.is_symlink() or path.is_file():
            path.unlink()
        else:
            shutil.rmtree(path)
    return paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="List generated files without deleting them"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    paths = clean(root, args.dry_run)
    for path in paths:
        print(("Would remove: " if args.dry_run else "Removed: ") + str(path.relative_to(root)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
