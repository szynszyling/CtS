"""OCR backend settings and the bounded, versioned self-hosted client."""

import json
import math
import os
import socket
import ssl
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from PySide6.QtCore import QRectF

from .paths import config_directory

MAX_RESPONSE = 8 * 1024 * 1024
_LOCK = threading.Lock()
_CURRENT = None


def settings_path():
    return config_directory() / "ocr.json"


@dataclass(frozen=True)
class OcrConfig:
    backend: str = "local"
    server_url: str = "http://127.0.0.1:8766"
    token: str = ""
    timeout: float = 15
    fallback: bool = False
    local_gpu_name: str = ""

    def validated(self):
        if self.backend not in ("local", "gpu", "server"):
            raise ValueError("Choose local GPU, local Tesseract, or server OCR.")
        if not isinstance(self.local_gpu_name, str) or len(self.local_gpu_name) > 200:
            raise ValueError("Enter a valid GPU name.")
        if not isinstance(self.server_url, str):
            raise ValueError("Enter a server URL.")
        if not isinstance(self.fallback, bool):
            raise ValueError("Local fallback must be enabled or disabled.")
        if self.backend == "server":
            parts = urllib.parse.urlsplit(self.server_url)
            if (
                parts.scheme not in ("http", "https")
                or not parts.hostname
                or parts.username
                or parts.password
                or parts.query
                or parts.fragment
            ):
                raise ValueError(
                    "Enter an HTTP(S) server URL without a password, query or fragment."
                )
            try:
                parts.port
            except ValueError as error:
                raise ValueError("The server port is invalid.") from error
        try:
            timeout = float(self.timeout)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError("OCR timeout must be a number between 1 and 120 seconds.") from error
        if isinstance(self.timeout, bool) or not math.isfinite(timeout) or not 1 <= timeout <= 120:
            raise ValueError("OCR timeout must be between 1 and 120 seconds.")
        if (
            not isinstance(self.token, str)
            or not self.token.isascii()
            or "\n" in self.token
            or "\r" in self.token
        ):
            raise ValueError("The server token is invalid.")
        return replace(self, server_url=self.server_url.rstrip("/"), timeout=timeout)

    @classmethod
    def load(cls, path=None):
        path = Path(path) if path else settings_path()
        try:
            data = json.loads(path.read_text())
        except FileNotFoundError:
            data = {}
        except (OSError, ValueError) as error:
            raise ValueError("Could not read OCR settings: " + str(error)) from error
        if not isinstance(data, dict):
            raise ValueError("OCR settings must contain an object.")
        fields = {key: value for key, value in data.items() if key in cls.__dataclass_fields__}
        for env, key in (
            ("CTS_OCR_BACKEND", "backend"),
            ("CTS_OCR_SERVER", "server_url"),
            ("CTS_OCR_TOKEN", "token"),
        ):
            if env in os.environ:
                fields[key] = os.environ[env]
        return cls(**fields).validated()

    def save(self, path=None):
        config = self.validated()
        path = Path(path) if path else settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, "w") as output:
                json.dump(asdict(config), output, indent=2)
            temporary.replace(path)
        finally:
            if temporary.exists():
                temporary.unlink()


def configure_ocr(config):
    global _CURRENT
    config = config.validated()
    with _LOCK:
        _CURRENT = config


def current_config():
    with _LOCK:
        return _CURRENT or OcrConfig()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RuntimeError("The OCR server redirected the request. Enter its final URL instead.")


def server_request(config, route, body=None, query=None):
    config = replace(config, backend="server").validated()
    url = config.server_url + route
    if query:
        url += "?" + urllib.parse.urlencode(query)
    headers = {"Accept": "application/json", "User-Agent": "CircleToSearch/0.12"}
    if config.token:
        headers["Authorization"] = "Bearer " + config.token
    if body is not None:
        headers["Content-Type"] = "image/png"
    request = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.build_opener(NoRedirect).open(
            request, timeout=config.timeout
        ) as response:
            data = response.read(MAX_RESPONSE + 1)
    except urllib.error.HTTPError as error:
        message = {
            401: "The OCR server token is missing or incorrect.",
            413: "The OCR image is too large for this server.",
            422: "The OCR server does not support the requested language or options.",
            503: "The OCR server is busy. Try again shortly.",
            504: "The OCR server timed out.",
        }.get(error.code, f"The OCR server returned HTTP {error.code}.")
        raise RuntimeError(message) from error
    except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as error:
        if isinstance(error, ssl.SSLCertVerificationError) or isinstance(
            getattr(error, "reason", None), ssl.SSLCertVerificationError
        ):
            raise RuntimeError(
                "The OCR server HTTPS certificate could not be verified. Check the hostname, certificate chain and expiry."
            ) from error
        raise RuntimeError(
            "Could not reach the OCR server. Check its address and connection, or switch to local OCR."
        ) from error
    if len(data) > MAX_RESPONSE:
        raise RuntimeError("The OCR response exceeded the size limit.")
    try:
        result = json.loads(data)
    except (ValueError, UnicodeError) as error:
        raise RuntimeError("The OCR server returned invalid JSON.") from error
    if (
        not isinstance(result, dict)
        or type(result.get("api_version")) is not int
        or result.get("api_version") != 1
        or result.get("service") != "circle-to-search-ocr"
    ):
        raise RuntimeError("The OCR server uses an incompatible API version.")
    return result


def check_server(config):
    result = server_request(config, "/v1/health")
    if result.get("status") != "ready" or result.get("character_boxes") is not True:
        raise RuntimeError("The OCR server is not ready or cannot return character boxes.")
    return result


def recognize_remote(image, language, vertical, priority, config):
    from .ocr import Document, Glyph, encode_png

    result = server_request(
        config,
        "/v1/ocr",
        encode_png(image),
        {"language": language, "vertical": "true" if vertical else "false", "priority": priority},
    )
    if (result.get("width"), result.get("height")) != (image.width(), image.height()):
        raise RuntimeError("The OCR response uses the wrong image dimensions.")
    items = result.get("glyphs")
    if not isinstance(items, list) or len(items) > 50000:
        raise RuntimeError("The OCR server returned invalid character data.")
    bounds = QRectF(0, 0, image.width(), image.height())
    glyphs = []
    for item in items:
        try:
            text = item["text"]
            box = item["bbox"]
            confidence = float(item.get("confidence", 100))
            if (
                not isinstance(text, str)
                or not 1 <= len(text) <= 16
                or not isinstance(box, list)
                or len(box) != 4
            ):
                raise ValueError()
            if any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                for value in box
            ):
                raise ValueError()
            if (
                box[2] <= 0
                or box[3] <= 0
                or not math.isfinite(confidence)
                or not 0 <= confidence <= 100
            ):
                raise ValueError()
            line, word = item["line"], item["word"]
            if (
                not isinstance(line, str)
                or not isinstance(word, str)
                or len(line) > 128
                or len(word) > 128
            ):
                raise ValueError()
            rect = QRectF(*box).intersected(bounds)
            if rect.isEmpty():
                raise ValueError()
        except (KeyError, TypeError, ValueError, OverflowError) as error:
            raise RuntimeError("The OCR server returned an invalid character box.") from error
        glyphs.append(Glyph(text, rect, line, word, confidence))
    return Document(glyphs)
