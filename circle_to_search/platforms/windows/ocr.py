"""Run the shared Vulkan OCR engine in a private, managed Windows process."""

import atexit
import importlib.util
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path

from ...ocr_backend import check_server

_LOCK = threading.Lock()
_PROCESS = None
_CONNECTION = None
_GPU = None


def available():
    return getattr(sys, "frozen", False) or importlib.util.find_spec("cts_ocr_server") is not None


def worker_command():
    if getattr(sys, "frozen", False):
        return [sys.executable, "--ocr-worker"]
    return [sys.executable, "-m", "circle_to_search.platforms.windows.ocr_worker"]


def stop_worker():
    global _PROCESS, _CONNECTION, _GPU
    process = _PROCESS
    _PROCESS = _CONNECTION = _GPU = None
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(5)


atexit.register(stop_worker)


def start_worker(config):
    global _PROCESS, _CONNECTION, _GPU
    from . import WindowsBackend

    if not available():
        raise RuntimeError(
            "Install the Windows OCR backend with `python -m pip install ./server` or use the Windows release bundle."
        )
    root = WindowsBackend().instance_lock_path().parent / "ocr"
    root.mkdir(parents=True, exist_ok=True)
    bundled = Path(getattr(sys, "_MEIPASS", "")) / "ocr-models"
    models = bundled if getattr(sys, "frozen", False) and bundled.is_dir() else root / "models"
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    token = secrets.token_urlsafe(32)
    connection = replace(
        config, backend="server", server_url=f"http://127.0.0.1:{port}", token=token, fallback=False
    )
    command = [
        *worker_command(),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--model-dir",
        str(models),
    ]
    if config.local_gpu_name:
        command.extend(["--gpu-name", config.local_gpu_name])
    log_path = root / "worker.log"
    environment = {
        **os.environ,
        "CTS_OCR_SERVER_TOKEN": token,
        "PYTHONUTF8": "1",
        "PYTHONUNBUFFERED": "1",
        "CTS_OCR_WORKER_LOG": str(log_path),
    }
    with log_path.open("wb") as log:
        _PROCESS = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            env=environment,
            cwd=None if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[3],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    deadline = time.monotonic() + 55
    try:
        while _PROCESS.poll() is None and time.monotonic() < deadline:
            try:
                info = check_server(replace(connection, timeout=1))
            except RuntimeError:
                time.sleep(0.15)
                continue
            if info.get("accelerated") is not True:
                raise RuntimeError("The OCR worker did not activate Vulkan.")
            _CONNECTION, _GPU = connection, config.local_gpu_name
            return connection, info
        detail = log_path.read_text(encoding="utf-8", errors="replace").strip()[-600:]
        raise RuntimeError(
            "Windows GPU OCR could not start. Check the Vulkan driver and GPU name. " + detail
        )
    except BaseException:
        stop_worker()
        raise


def ensure_local(config):
    with _LOCK:
        if _CONNECTION is not None and _PROCESS.poll() is None and _GPU == config.local_gpu_name:
            return replace(_CONNECTION, timeout=config.timeout)
        stop_worker()
        return start_worker(config)[0]


def prepare_local(config):
    connection = ensure_local(config)
    return check_server(connection)
