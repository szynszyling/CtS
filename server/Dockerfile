# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm AS language-models

WORKDIR /build
COPY server/cts_ocr_server/__init__.py server/cts_ocr_server/bundle.py server/cts_ocr_server/engine.py server/cts_ocr_server/gpu_models.py server/cts_ocr_server/models.json ./cts_ocr_server/
COPY server/build_models.py ./
ARG OCR_PROFILE=server
ARG OCR_LANGUAGES=
RUN python build_models.py /opt/cts-models --profile "$OCR_PROFILE" --languages "$OCR_LANGUAGES" \
    && chmod -R a=rX /opt/cts-models

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
COPY server/pyproject.toml server/LICENSE server/THIRD_PARTY.md server/README.md ./
COPY server/licenses ./licenses
COPY server/cts_ocr_server ./cts_ocr_server
RUN python -m pip install --no-cache-dir --no-deps .
COPY --from=language-models /opt/cts-models /opt/cts-models

USER 10001:10001
EXPOSE 8766
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-m", "cts_ocr_server.healthcheck"]
ENTRYPOINT ["cts-ocr-server"]
CMD ["--host", "0.0.0.0"]

FROM runtime AS test
USER root
RUN python -m pip install --no-cache-dir httpx==0.28.1 \
    && apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*
COPY server/tests /opt/tests
USER 10001:10001
RUN python -m unittest discover -s /opt/tests -q
RUN cts-ocr-server --device cpu --self-test

FROM runtime AS final
ARG VERSION=0.14.0
ARG VCS_REF=unknown
LABEL org.opencontainers.image.title="CtS OCR backend" \
    org.opencontainers.image.licenses="MIT" \
    org.opencontainers.image.description="Vulkan-accelerated multilingual character recognition for Circle to Search" \
    org.opencontainers.image.source="https://github.com/szynszyling/CtS" \
    org.opencontainers.image.documentation="https://github.com/szynszyling/CtS/blob/main/server/README.md" \
    org.opencontainers.image.version="${VERSION}" \
    org.opencontainers.image.revision="${VCS_REF}"
