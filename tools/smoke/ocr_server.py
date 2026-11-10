"""Verify the real headless OCR service using synthetic desktop text only."""

import argparse
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter
from PySide6.QtWidgets import QApplication

from circle_to_search.gestures import resolve_gesture
from circle_to_search.ocr_backend import OcrConfig, check_server, recognize_remote


def fixture(text, size=18, dark=False, vertical=False):
    image = QImage(900 if not vertical else 180, 160 if not vertical else 500, QImage.Format_RGB32)
    image.fill(QColor("#22242a") if dark else Qt.white)
    painter = QPainter(image)
    font = QFont("Noto Sans CJK JP")
    font.setPixelSize(size)
    painter.setFont(font)
    painter.setPen(Qt.white if dark else Qt.black)
    if vertical:
        for index, char in enumerate(text):
            painter.drawText(65, 35 + index * (size + 7), char)
    else:
        painter.drawText(25, 70, text)
    painter.end()
    return image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument(
        "--docker", help="Test a built container image instead of a Python environment"
    )
    parser.add_argument("--model-dir", type=Path, default=Path("/tmp/cts-gpu-models"))
    parser.add_argument("--device", choices=("vulkan", "cpu"), default="vulkan")
    parser.add_argument("--gpu-name", default="AMD")
    parser.add_argument("--detector-scale", type=float, default=2.0)
    args = parser.parse_args()
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _app = QApplication([])
    with tempfile.TemporaryDirectory(prefix="cts-ocr-smoke-") as directory:
        root = Path(directory)
        token = secrets.token_urlsafe(32)
        token_file = root / "token"
        token_file.write_text(token)
        token_file.chmod(0o600)
        with socket.socket() as handle:
            handle.bind(("127.0.0.1", 0))
            port = handle.getsockname()[1]
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "server")
        environment["VK_LOADER_LAYERS_DISABLE"] = "VK_LAYER_LSFGVK_frame_generation"
        command = [
            args.python,
            "-m",
            "cts_ocr_server",
            "--device",
            args.device,
            "--gpu-name",
            args.gpu_name,
            "--model-dir",
            str(args.model_dir),
            "--port",
            str(port),
            "--token-file",
            str(token_file),
            "--detector-scale",
            str(args.detector_scale),
        ]
        if args.device == "cpu":
            index = command.index("--gpu-name")
            del command[index : index + 2]
        container_name = None
        if args.docker:
            container_name = "cts-ocr-smoke-" + secrets.token_hex(4)
            environment["CTS_OCR_SERVER_TOKEN"] = token
            command = [
                "docker",
                "run",
                "--rm",
                "--name",
                container_name,
                "--read-only",
                "--tmpfs",
                "/tmp:size=256m",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "--env",
                "CTS_OCR_SERVER_TOKEN",
                "--publish",
                f"127.0.0.1:{port}:8766",
            ]
            if args.device == "vulkan":
                nodes = sorted(Path("/dev/dri").glob("renderD*"))
                if not nodes:
                    raise RuntimeError("No render device is available for the GPU container.")
                command += ["--device", "/dev/dri", "--group-add", str(nodes[0].stat().st_gid)]
            command += [args.docker, "--host", "0.0.0.0", "--device", args.device]
            command += ["--detector-scale", str(args.detector_scale)]
            if args.device == "vulkan":
                command += ["--gpu-name", args.gpu_name]
        log = (root / "server.log").open("w+")
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, env=environment)
        config = OcrConfig("server", f"http://127.0.0.1:{port}", token, 30)
        try:
            deadline = time.monotonic() + 45
            while True:
                try:
                    health = check_server(config)
                    break
                except RuntimeError:
                    if process.poll() is not None or time.monotonic() > deadline:
                        log.seek(0)
                        raise RuntimeError("Server startup failed: " + log.read()[-4500:])
                    time.sleep(0.1)
            assert health["accelerated"] == (args.device == "vulkan")
            assert health["precision"] == "fp32" and health["self_test_passed"]
            assert health["detector_scale"] == args.detector_scale
            if args.device == "vulkan":
                assert args.gpu_name.lower() in health["device"].lower()
            print("Actual backend:", json.dumps(health), flush=True)
            cases = [
                ("English", "Circle these words", 18, False, False),
                ("Japanese kana/kanji", "ひらがなカタカナ漢字", 18, False, False),
                ("Small Japanese", "日本語の文字を選択します", 14, False, False),
                ("Dark Japanese", "日本語の文字を選択します", 14, True, False),
                ("Vertical Japanese", "日本語の文字", 22, False, True),
            ]
            latencies = []
            for label, text, size, dark, vertical in cases:
                image = fixture(text, size, dark, vertical)
                started = time.perf_counter()
                document = recognize_remote(image, "jpn+eng", vertical, "interactive", config)
                elapsed = time.perf_counter() - started
                recognized = document.text()
                print(label, repr(recognized), round(elapsed * 1000, 1), "ms", flush=True)
                assert recognized == text, (label, recognized, text)
                assert all(g.rect.width() > 0 and g.rect.height() > 0 for g in document.glyphs)
                if "Japanese" in label:
                    # Select an actual interior character through its returned
                    # geometry, including vertical and dark-background fixtures.
                    index = 2
                    point = document.glyphs[index].rect.center()
                    selected = resolve_gesture([point], QRectF(image.rect()), document, False)
                    assert selected.kind == "text" and document.glyphs[index].text in selected.text
                latencies.append(elapsed)
            try:
                check_server(OcrConfig("server", config.server_url, "wrong", 3))
            except RuntimeError as error:
                assert "token" in str(error)
            else:
                raise AssertionError("An incorrect token was accepted.")
            print(
                "Real GPU inference, remote protocol, kana/kanji character selection, vertical text and authentication passed."
                if args.device == "vulkan"
                else "CPU reference service/protocol passed.",
                flush=True,
            )
        finally:
            if container_name:
                subprocess.run(
                    ["docker", "stop", "--time", "5", container_name],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=15,
                )
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            log.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
