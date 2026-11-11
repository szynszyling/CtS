# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm AS language-models

WORKDIR /models
COPY circle_to_search/__init__.py circle_to_search/models.py ./circle_to_search/
COPY circle_to_search/tessdata/models.json ./circle_to_search/tessdata/
RUN python -c 'from circle_to_search.models import fetch_models, model_manifest; fetch_models("/opt/cts-tessdata", [entry["name"] for entry in model_manifest()["models"]])' \
    && chmod -R a=rX /opt/cts-tessdata

FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    XDG_CACHE_HOME=/tmp/cts-cache \
    CTS_OCR_MODELS=/opt/cts-models \
    CTS_OCR_TESSDATA=/opt/cts-tessdata

RUN apt-get update \
    && apt-get install -y --no-install-recommends libvulkan1 mesa-vulkan-drivers libgomp1 tesseract-ocr \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 cts \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin cts

WORKDIR /opt/cts-ocr
COPY server/requirements.lock /tmp/requirements.lock
RUN python -m pip install --no-cache-dir --require-hashes -r /tmp/requirements.lock
COPY server/pyproject.toml server/LICENSE server/THIRD_PARTY.md server/README.md ./
COPY server/licenses ./licenses
COPY server/cts_ocr_server ./cts_ocr_server
RUN python -m pip install --no-cache-dir --no-deps . \
    && python -m cts_ocr_server --download-models --model-dir /opt/cts-models \
    && chmod -R a=rX /opt/cts-models
COPY --from=language-models /opt/cts-tessdata /opt/cts-tessdata
COPY circle_to_search/tessdata/models.json /opt/cts-tessdata/models.json

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
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
COPY server/tests /opt/tests
USER 10001:10001
RUN python -m unittest discover -s /opt/tests -q
RUN cts-ocr-server --device cpu --self-test

FROM runtime AS final
ARG VERSION=0.13.0
ARG VCS_REF=unknown
LABEL org.opencontainers.image.title="CtS OCR backend" \
    org.opencontainers.image.licenses="MIT" \
    org.opencontainers.image.description="Self-hosted character recognition for Circle to Search with Vulkan inference and 19 Tesseract language packs" \
    org.opencontainers.image.source="https://github.com/szynszyling/CtS" \
    org.opencontainers.image.documentation="https://github.com/szynszyling/CtS/blob/main/server/README.md" \
    org.opencontainers.image.version="${VERSION}" \
    org.opencontainers.image.revision="${VCS_REF}"
