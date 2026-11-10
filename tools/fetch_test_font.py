"""Fetch the exact Noto Japanese font used by OCR fixture tests on Windows."""

import hashlib
from pathlib import Path
from urllib.request import urlopen

FONT = Path(__file__).resolve().parents[1] / "build/test-fonts/NotoSansCJKjp-Regular.otf"
SHA256 = "68a3fc98800b2a27b371f2fb79991daf3633bd89309d4ffaa6946fd587f375b5"
URL = (
    "https://raw.githubusercontent.com/notofonts/noto-cjk/Sans2.004/Sans/OTF/Japanese/" + FONT.name
)


def fetch():
    if FONT.is_file() and hashlib.sha256(FONT.read_bytes()).hexdigest() == SHA256:
        return FONT
    with urlopen(URL, timeout=90) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise RuntimeError("The Japanese OCR test font did not match its pinned checksum.")
    FONT.parent.mkdir(parents=True, exist_ok=True)
    FONT.write_bytes(data)
    return FONT


if __name__ == "__main__":
    print(fetch())
