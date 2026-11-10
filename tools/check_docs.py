"""Check that rendered local links in repository Markdown point to real files."""

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit


def broken_links(root: Path) -> list[str]:
    failures = []
    for document in root.rglob("*.md"):
        relative = document.relative_to(root)
        if any(part.startswith(".") or part in {"build", "dist"} for part in relative.parts):
            continue
        content = document.read_text(encoding="utf-8")
        content = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
        content = re.sub(r"^```[^\n]*\n.*?^```\s*$", "", content, flags=re.MULTILINE | re.DOTALL)
        links = re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", content)
        links += re.findall(r'(?:href|src)="([^"]+)"', content)
        for link in links:
            parsed = urlsplit(link)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            target = (
                root / parsed.path.lstrip("/")
                if parsed.path.startswith("/")
                else document.parent / unquote(parsed.path)
            )
            if not target.exists():
                failures.append(f"{relative}: missing {link}")
    return failures


def main():
    root = Path(__file__).resolve().parents[1]
    failures = broken_links(root)
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print("Local documentation links are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
