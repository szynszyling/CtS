"""Authenticated, bounded OCR API with a persistent inference worker."""

import asyncio
import hmac
import logging
import threading
import time
from concurrent.futures import Future
from contextlib import asynccontextmanager
from io import BytesIO
from itertools import count
from queue import Empty, Full, PriorityQueue

from fastapi import FastAPI, HTTPException, Request
from PIL import Image, UnidentifiedImageError

from . import __version__

MAX_BYTES = 16 * 1024 * 1024
MAX_PIXELS = 24_000_000
API_VERSION = 1


class InferenceWorker:
    def __init__(self, engine):
        self.engine = engine
        self.queue = PriorityQueue(maxsize=8)
        self.counter = count()
        self.thread = threading.Thread(target=self.run, name="cts-ocr-inference", daemon=True)
        self.thread.start()

    def submit(self, image, vertical, interactive, language=None):
        future = Future()
        self.queue.put_nowait(
            (
                0 if interactive else 10,
                next(self.counter),
                (future, image, vertical, language, time.monotonic()),
            )
        )
        return future

    def execute(self, job, interactive):
        future, image, vertical, language, submitted = job
        if not future.set_running_or_notify_cancel():
            return
        started = time.monotonic()
        try:
            glyphs = self.engine.recognize(
                image,
                vertical,
                on_yield=None if interactive else self.interrupt_background,
                language=language,
            )
            result = {
                "service": "circle-to-search-ocr",
                "api_version": API_VERSION,
                "width": image.width,
                "height": image.height,
                "glyphs": glyphs,
                "engine": "ppocrv5-ncnn",
                "device": self.engine.device_name,
                "accelerated": self.engine.device == "vulkan",
                "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
                "queue_ms": round((started - submitted) * 1000, 2),
            }
        except Exception as error:
            logging.getLogger(__name__).exception("OCR inference failed")
            future.set_exception(error)
        else:
            future.set_result(result)

    def interrupt_background(self):
        # Yield at a model boundary, never during a Vulkan submission. Process
        # one gesture crop, then advance the background scan by another line.
        with self.queue.mutex:
            if not self.queue.queue or self.queue.queue[0][0] != 0:
                return
            _, _, job = self.queue._get()
            self.queue.not_full.notify()
        try:
            if job is not None:
                self.execute(job, interactive=True)
        finally:
            self.queue.task_done()

    def run(self):
        while True:
            priority, _, job = self.queue.get()
            try:
                if job is None:
                    return
                self.execute(job, interactive=priority == 0)
            finally:
                self.queue.task_done()

    def close(self):
        # Cancel queued requests; finish the current inference before unloading.
        while True:
            try:
                _, _, job = self.queue.get_nowait()
            except Empty:
                break
            if job is not None:
                job[0].cancel()
            self.queue.task_done()
        self.queue.put((100, next(self.counter), None))
        self.thread.join(timeout=30)


def create_app(engine, token=""):
    if not engine.self_test_passed:
        raise RuntimeError(
            "The OCR engine must pass its recognition self-test before serving requests."
        )
    languages = frozenset(engine.languages)
    default_language = "+".join(code for code in ("jpn", "eng") if code in languages)
    default_language = default_language or engine.languages[0]
    worker = InferenceWorker(engine)

    @asynccontextmanager
    async def lifespan(app):
        yield
        worker.close()

    app = FastAPI(
        title="Circle to Search OCR",
        version=__version__,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    def authorize(request):
        if token and not hmac.compare_digest(
            request.headers.get("Authorization", "").encode("utf-8"),
            ("Bearer " + token).encode("utf-8"),
        ):
            raise HTTPException(401, "The OCR server token is missing or incorrect.")

    @app.get("/v1/health")
    async def health(request: Request):
        authorize(request)
        return {
            "service": "circle-to-search-ocr",
            "api_version": API_VERSION,
            "status": "ready",
            "engine": "ppocrv5-ncnn",
            "version": __version__,
            "precision": engine.precision,
            "self_test_passed": engine.self_test_passed,
            "detector_scale": engine.detector_scale,
            "device": engine.device_name,
            "gpu_index": engine.gpu_index,
            "accelerated": engine.device == "vulkan",
            "queued": worker.queue.qsize(),
            "languages": sorted(languages),
            "profile": engine.profile,
            "character_boxes": True,
        }

    @app.post("/v1/ocr")
    async def ocr(
        request: Request,
        language: str | None = None,
        vertical: bool = False,
        priority: str = "background",
    ):
        authorize(request)
        codes = tuple(
            dict.fromkeys((default_language if language is None else language).split("+"))
        )
        if not set(codes) <= languages:
            raise HTTPException(422, "One or more requested OCR languages are unavailable.")
        if vertical and "jpn_vert" in languages:
            codes = ("jpn_vert",)
        vertical = vertical or codes == ("jpn_vert",)
        language = "+".join(codes)
        if priority not in ("background", "interactive"):
            raise HTTPException(422, "Unknown request priority.")
        if request.headers.get("Content-Type", "").split(";")[0] != "image/png":
            raise HTTPException(415, "Send an image/png request body.")
        body = bytearray()
        async for part in request.stream():
            body.extend(part)
            if len(body) > MAX_BYTES:
                raise HTTPException(413, "OCR image exceeds the 16 MiB upload limit.")
        try:
            with Image.open(BytesIO(body)) as opened:
                if opened.format != "PNG":
                    raise HTTPException(415, "Only PNG images are accepted.")
                if opened.width * opened.height > MAX_PIXELS:
                    raise HTTPException(413, "OCR image exceeds the pixel limit.")
                image = opened.convert("RGB")
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as error:
            raise HTTPException(400, "The image could not be decoded.") from error
        try:
            future = worker.submit(image, vertical, priority == "interactive", language)
        except Full:
            raise HTTPException(503, "The OCR queue is full. Try again shortly.")
        try:
            return await asyncio.wait_for(asyncio.wrap_future(future), timeout=60)
        except asyncio.TimeoutError:
            future.cancel()
            raise HTTPException(504, "OCR exceeded the server deadline.")
        except asyncio.CancelledError:
            future.cancel()
            raise
        except Exception as error:
            # Do not return tracebacks, file paths or screen contents to clients.
            raise HTTPException(500, "OCR inference failed. Check the server log.") from error

    return app
