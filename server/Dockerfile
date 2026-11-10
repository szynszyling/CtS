# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    XDG_CACHE_HOME=/tmp/cts-cache \
    CTS_OCR_MODELS=/opt/cts-models

RUN apt-get update \
    && apt-get install -y --no-install-recommends libvulkan1 mesa-vulkan-drivers libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 cts \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin cts

WORKDIR /opt/cts-ocr
COPY server/requirements.lock /tmp/requirements.lock
RUN python -m pip install --no-cache-dir --require-hashes -r /tmp/requirements.lock
COPY server/pyproject.toml server/THIRD_PARTY.md server/README.md ./
COPY server/cts_ocr_server ./cts_ocr_server
RUN python -m pip install --no-cache-dir --no-deps . \
    && python -m cts_ocr_server --download-models --model-dir /opt/cts-models \
    && chmod -R a=rX /opt/cts-models

USER 10001:10001
EXPOSE 8766
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-m", "cts_ocr_server.healthcheck"]
ENTRYPOINT ["cts-ocr-server"]
CMD ["--host", "0.0.0.0"]

FROM runtime AS test
USER root
RUN python -m pip install --no-cache-dir httpx==0.28.1
COPY server/tests /opt/tests
USER 10001:10001
RUN python -m unittest discover -s /opt/tests -q
RUN cts-ocr-server --device cpu --self-test

FROM runtime AS final
