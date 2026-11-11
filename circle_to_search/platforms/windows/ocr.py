"""Run the shared Vulkan OCR engine in a private, managed Windows process."""

import atexit
import importlib.util
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import replace
from pathlib import Path

from ...languages import selected_models
from ...ocr_backend import check_server

_LOCK = threading.Lock()
_PROCESS = None
_CONNECTION = None
_GPU = None
_LANGUAGES = None


def available():
    return getattr(sys, "frozen", False) or importlib.util.find_spec("cts_ocr_server") is not None


def worker_command():
    if getattr(sys, "frozen", False):
        return [sys.executable, "--ocr-worker"]
    return [sys.executable, "-m", "circle_to_search.platforms.windows.ocr_worker"]


def stop_worker():
    global _PROCESS, _CONNECTION, _GPU, _LANGUAGES
    process = _PROCESS
    _PROCESS = _CONNECTION = _GPU = _LANGUAGES = None
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(5)


atexit.register(stop_worker)


def prepare_model_selection(root, codes):
    from cts_ocr_server import __version__ as backend_version
    from cts_ocr_server.bundle import prepare_models, ready_bundle
    from cts_ocr_server.gpu_models import LANGUAGES

    if not codes or not set(codes) <= set(LANGUAGES):
        raise RuntimeError("Choose supported OCR languages in the CtS language settings.")
    cache = root / "models" / backend_version
    directory = cache / "+".join(codes)
    if ready_bundle(directory, codes):
        return directory
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="preparing-", dir=cache) as temporary:
        prepared = prepare_models(Path(temporary), codes)
        directory.mkdir(exist_ok=True)
        # Publish the manifest last, after every model file has been replaced.
        for path in prepared.iterdir():
            if path.name != "bundle.json":
                path.replace(directory / path.name)
        (prepared / "bundle.json").replace(directory / "bundle.json")
    return directory


def start_worker(config, root, models, codes):
    global _PROCESS, _CONNECTION, _GPU, _LANGUAGES

    if not available():
        raise RuntimeError(
            "Install the Windows OCR backend with `python -m pip install ./server` or use the Windows release bundle."
        )
    root.mkdir(parents=True, exist_ok=True)
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
            _CONNECTION, _GPU, _LANGUAGES = connection, config.local_gpu_name, codes
            return connection, info
        detail = log_path.read_text(encoding="utf-8", errors="replace").strip()[-600:]
        raise RuntimeError(
            "Windows GPU OCR could not start. Check the Vulkan driver and GPU name. " + detail
        )
    except BaseException:
        stop_worker()
        raise


def ensure_local(config, languages=None):
    from . import WindowsBackend

    with _LOCK:
        codes = tuple(sorted(set(languages or selected_models())))
        if (
            _CONNECTION is not None
            and _PROCESS.poll() is None
            and _GPU == config.local_gpu_name
            and _LANGUAGES == codes
        ):
            return replace(_CONNECTION, timeout=config.timeout)
        if not available():
            raise RuntimeError("Install the Windows CtS OCR backend before using local GPU mode.")
        root = WindowsBackend().instance_lock_path().parent / "ocr"
        try:
            models = prepare_model_selection(root, codes)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            raise RuntimeError(
                "Could not prepare the selected GPU models. " + str(error)
            ) from error
        stop_worker()
        return start_worker(config, root, models, codes)[0]


def prepare_local(config, languages=None):
    connection = ensure_local(config, languages)
    return check_server(connection)
