"""Manage CtS's local GPU container without exposing it beyond localhost."""

import os
import re
import secrets
import shutil
import site
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import replace
from pathlib import Path

from ...languages import selected_models
from ...models import model_manifest
from ...ocr_backend import check_server, settings_path

IMAGE = "circle-to-search-ocr:0.14.0"
NAME = "circle-to-search-ocr"
_LOCK = threading.Lock()
_CONNECTION = None
_GPU_NAME = None


def command(arguments, *, check=True, environment=None, timeout=120):
    try:
        result = subprocess.run(
            arguments, env=environment, capture_output=True, text=True, timeout=timeout
        )
    except FileNotFoundError as error:
        raise RuntimeError(
            "Install Docker to use local GPU OCR, or choose local Tesseract / your own server."
        ) from error
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("The local OCR setup timed out. Check Docker and try again.") from error
    if check and result.returncode:
        raise RuntimeError(
            "Local GPU OCR could not run Docker. " + (result.stderr or result.stdout)[-1800:]
        )
    return result


def deployment_directory():
    candidates = (
        Path(__file__).resolve().parents[3] / "server",
        Path(sys.prefix) / "share/circle-to-search/server",
        Path(site.getuserbase()) / "share/circle-to-search/server",
    )
    for path in candidates:
        if (path / "Dockerfile").is_file():
            return path
    raise RuntimeError(
        "The local backend files are missing. Reinstall CtS or choose your own OCR server."
    )


def image_for_languages(languages):
    return IMAGE + "-local-" + "-".join(sorted(languages))


def build_image(languages=None):
    languages = tuple(languages or selected_models())
    available = {entry["name"] for entry in model_manifest()["models"]}
    if not languages or not set(languages) <= available:
        raise RuntimeError("Choose supported OCR languages in the CtS language settings.")
    source = deployment_directory()
    with tempfile.TemporaryDirectory(prefix="cts-local-ocr-build-") as directory:
        destination = Path(directory) / "server"
        destination.mkdir()
        # Include only backend source and the pinned language download inputs.
        for name in (
            "Dockerfile",
            "pyproject.toml",
            "requirements.lock",
            "README.md",
            "LICENSE",
            "THIRD_PARTY.md",
            "build_models.py",
        ):
            shutil.copyfile(source / name, destination / name)
        (destination / "licenses").mkdir()
        for path in (source / "licenses").glob("*.txt"):
            shutil.copyfile(path, destination / "licenses" / path.name)
        for name in ("cts_ocr_server", "tests"):
            target = destination / name
            target.mkdir()
            for path in (source / name).iterdir():
                if path.is_file() and path.suffix in (".py", ".json"):
                    shutil.copyfile(path, target / path.name)
        command(
            [
                "docker",
                "build",
                "--build-arg",
                "OCR_PROFILE=local",
                "--build-arg",
                "OCR_LANGUAGES=" + "+".join(languages),
                "-f",
                str(destination / "Dockerfile"),
                "-t",
                image_for_languages(languages),
                directory,
            ],
            timeout=600,
        )


def private_environment(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".")
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w") as stream:
            for key, value in values.items():
                stream.write(key + "=" + str(value) + "\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def connection_for(token, port, config):
    return replace(
        config, backend="server", server_url=f"http://127.0.0.1:{port}", token=token, fallback=False
    )


def wait_ready(connection, gpu_name):
    deadline = time.monotonic() + 40
    while True:
        try:
            info = check_server(replace(connection, timeout=2))
        except RuntimeError as error:
            if time.monotonic() > deadline:
                raise RuntimeError(
                    "Local GPU OCR did not become ready. Check the CtS OCR container log."
                ) from error
            time.sleep(0.15)
            continue
        if info.get("accelerated") is not True:
            raise RuntimeError("The local backend did not activate GPU acceleration.")
        if gpu_name and gpu_name.lower() not in info.get("device", "").lower():
            raise RuntimeError(
                "The local backend uses a different GPU. Run local setup again to change it."
            )
        return info


def ensure_local(config, *, setup=False, replace_existing=False, port=None, languages=None):
    global _CONNECTION, _GPU_NAME
    with _LOCK:
        languages = tuple(sorted(set(languages or selected_models())))
        image_name = image_for_languages(languages)
        identity = (config.local_gpu_name, languages)
        if not setup and _CONNECTION is not None and _GPU_NAME == identity:
            return replace(_CONNECTION, timeout=config.timeout)
        path = settings_path().with_name("ocr-server.env")
        try:
            values = dict(
                line.split("=", 1) for line in path.read_text().splitlines() if "=" in line
            )
        except FileNotFoundError:
            values = {}
        if port is None:
            port = int(values.get("CTS_OCR_PORT", "8766"))
        found = command(
            [
                "docker",
                "container",
                "inspect",
                "--format",
                "{{.Config.Image}} {{.State.Running}}",
                NAME,
            ],
            check=False,
        )
        exists = found.returncode == 0
        if exists and not found.stdout.startswith("circle-to-search-ocr:"):
            raise RuntimeError("The local OCR container name belongs to another application.")
        if (
            exists
            and not replace_existing
            and found.stdout.startswith(image_name + " ")
            and values.get("CTS_OCR_SERVER_TOKEN")
        ):
            current_port = int(values.get("CTS_OCR_PORT", "8766"))
            connection = connection_for(values["CTS_OCR_SERVER_TOKEN"], current_port, config)
            if found.stdout.strip().endswith("false"):
                command(["docker", "start", NAME])
            try:
                wait_ready(connection, config.local_gpu_name)
                _CONNECTION = connection
                _GPU_NAME = identity
                return connection
            except RuntimeError:
                if not setup:
                    raise
        image = command(["docker", "image", "inspect", image_name], check=False)
        if image.returncode:
            if not setup:
                raise RuntimeError("Set up local GPU OCR in More → Text recognition first.")
            build_image(languages)
        nodes = sorted(Path("/dev/dri").glob("renderD*"))
        if not nodes:
            raise RuntimeError("No GPU render device is available. Check the graphics driver.")
        gid = str(nodes[0].stat().st_gid)
        listing = command(
            [
                "docker",
                "run",
                "--rm",
                "--device",
                "/dev/dri",
                "--group-add",
                gid,
                image_name,
                "--list-devices",
            ]
        )
        devices = [
            (index, name)
            for index, name in re.findall(r"^(\d+) (.+)$", listing.stdout, re.MULTILINE)
            if not config.local_gpu_name or config.local_gpu_name.lower() in name.lower()
        ]
        devices = [
            item
            for item in devices
            if not any(s in item[1].lower() for s in ("llvmpipe", "lavapipe", "swiftshader"))
        ]
        if not devices or (config.local_gpu_name and len(devices) != 1):
            raise RuntimeError(
                "Choose a unique GPU name. Available devices: " + listing.stdout.strip()
            )
        index, device_name = devices[0]
        token = secrets.token_urlsafe(32)
        environment = os.environ.copy()
        environment["CTS_OCR_SERVER_TOKEN"] = token
        backup = NAME + "-previous-" + secrets.token_hex(4) if exists else None
        if backup:
            command(["docker", "rename", NAME, backup])
        _CONNECTION = None
        try:
            if backup:
                command(["docker", "stop", backup])
            command(
                [
                    "docker",
                    "run",
                    "--detach",
                    "--name",
                    NAME,
                    "--restart",
                    "unless-stopped",
                    "--device",
                    "/dev/dri",
                    "--group-add",
                    gid,
                    "--read-only",
                    "--tmpfs",
                    "/tmp:size=256m,mode=1777",
                    "--cap-drop",
                    "ALL",
                    "--security-opt",
                    "no-new-privileges:true",
                    "--pids-limit",
                    "128",
                    "--memory",
                    "2g",
                    "--cpus",
                    "4",
                    "--env",
                    "CTS_OCR_SERVER_TOKEN",
                    "--publish",
                    f"127.0.0.1:{port}:8766",
                    image_name,
                    "--host",
                    "0.0.0.0",
                    "--gpu-index",
                    index,
                ],
                environment=environment,
            )
            connection = connection_for(token, port, config)
            wait_ready(connection, config.local_gpu_name)
            private_environment(
                path,
                {
                    "CTS_OCR_SERVER_TOKEN": token,
                    "CTS_OCR_RENDER_GID": gid,
                    "CTS_OCR_GPU_INDEX": index,
                    "CTS_OCR_PORT": port,
                },
            )
        except BaseException:
            command(["docker", "rm", "--force", NAME], check=False)
            if backup:
                command(["docker", "rename", backup, NAME])
                command(["docker", "start", NAME])
            raise
        if backup:
            command(["docker", "rm", backup], check=False)
        _CONNECTION = connection
        _GPU_NAME = identity
        return connection


def prepare_local(config, languages=None):
    return check_server(ensure_local(config, setup=True, languages=languages))
