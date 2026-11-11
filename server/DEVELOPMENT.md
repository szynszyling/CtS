# OCR backend development

The service is independent of Qt and the desktop platform adapters. It uses ncnn/Vulkan for all 19 language choices, with CTC-aligned character boxes. CPU reference mode is available through `--device cpu`.

## Models and inference

`cts_ocr_server/models.json` pins the original PP-OCRv5 detector and CJK recognizer. The shared `cts_ocr_server/bundle.py` downloader pins the RapidOCR ONNX exports, dictionaries and Linux/Windows pnnx converters by SHA-256. It converts the multilingual PP-OCRv6 small model for Latin languages and PP-OCRv5 recognizers for Cyrillic, Greek and Korean to ncnn FP32. `build_models.py` calls this downloader for Docker builds. Sources and licenses are listed in [THIRD_PARTY.md](THIRD_PARTY.md).

Docker build arguments choose the bundle. `OCR_PROFILE=server` is the default and includes all recognizers. `OCR_PROFILE=local` requires `OCR_LANGUAGES` with CtS codes separated by `+`.

```sh
docker build -f server/Dockerfile --target final --build-arg OCR_PROFILE=local --build-arg OCR_LANGUAGES=eng+pol -t cts-ocr:local .
```

The local image in this example contains the shared detector and the multilingual Latin recognizer. Languages that share a recognizer reuse its files. `bundle.json` records the profile, enabled language codes, included recognizers and file hashes. The runtime reads this bundle without downloading additional models. Health reports its profile and enabled languages. Windows uses the same downloader to prepare a selected model bundle for its native worker.

Requests run each required recognizer on a detected line and keep the highest-confidence result for that line. Selecting multiple scripts increases inference work. A line containing several scripts may need a recognizer trained to cover that combination.

Both networks use FP32 storage/arithmetic. Reduced precision produced corrupt results on the tested Intel HD 630; keep FP32 unless a separately tested implementation replaces it. Non-finite or invalid probability distributions are rejected before decoding. A startup test recognizes two known text images and checks a blank image before the API becomes ready.

The detector uses a 1600-pixel side cap. `CTS_OCR_DETECTOR_SCALE` / `--detector-scale` controls small-image enlargement from 1 to 2, defaulting to 2. Smaller values trade detection accuracy for speed; the recognizer still uses the original crop. Health reports the selected scale.

## API

Authenticate with `Authorization: Bearer TOKEN` when a token is configured. Binding beyond localhost requires one. HTTP headers carry authentication; credentials are not URL parameters.

- `GET /v1/health` reports readiness, API/server versions, device, acceleration state, precision, scale, supported languages and character-box support.
- `POST /v1/ocr?language=jpn%2Beng&vertical=false&priority=interactive` accepts a raw `image/png` body. Priority is `interactive` or `background`.

Responses identify `service: "circle-to-search-ocr"` and `api_version: 1`. OCR responses contain original pixel `width`/`height`, `glyphs`, engine/device information, `elapsed_ms` and `queue_ms`. Each glyph has `text`, `bbox: [x,y,width,height]`, line/word IDs and a 0–100 confidence.

Character coordinates refer to the original uploaded image. The desktop applies crop offsets and display scaling exactly once. CTC timestep positions map through the recognizer’s perspective transform; Latin word IDs preserve word snapping, while kana/kanji remain individually selectable.

The bounded queue holds at most eight pending requests and serializes GPU submissions. Interactive crops take priority. An active background scan yields between model calls so a gesture need not wait for every line in a screen scan. Uploads are limited to 16 MiB / 24 million pixels. Uploads are neither saved nor logged.

## Build and test

From the repository root:

Production users copy only the root `compose.yaml`. The `server/compose*.yaml` files below are optional source-checkout/development configurations, not deployment prerequisites.

```sh
docker build --target test -f server/Dockerfile -t circle-to-search-ocr:test .
docker compose --env-file server/.env -f server/compose.yaml -f server/compose.build.yaml build
python3 tools/smoke/ocr_server.py --docker circle-to-search-ocr:0.14.0 --gpu-name AMD
python3 tools/smoke/ocr_server.py --docker circle-to-search-ocr:0.14.0 --device cpu
python3 tools/smoke/ocr_server.py --docker circle-to-search-ocr:0.14.0 --gpu-name AMD --detector-scale 1.5
python3 tools/smoke/ocr_https.py --image circle-to-search-ocr:0.14.0
python3 tools/smoke/compose.py --image circle-to-search-ocr:0.14.0
```

The tests use generated text, including 14px light/dark Japanese and vertical character selection. The HTTPS check uses an isolated Docker network, the exact SWAG virtual host, a temporary trusted test certificate and a CPU reference backend. It checks bearer forwarding, rejection of an invalid token, upload limits and rejection of an untrusted TLS certificate. It does not change a working SWAG container or desktop configuration.

## Performance reference

The multilingual Radeon fixture run measured roughly 43–56 ms with one script group requested and 78–127 ms with every group requested. The Polish sample `Zażółć gęślą jaźń` matched exactly. A Czech sample lost the accent on `ť`, so recognition accuracy still depends on the input. Earlier CJK measurements on the remote HD 630 were roughly 310–440 ms including LAN round trips. These are synthetic fixture measurements.

Measure the actual device, fonts, image sizes and transport before changing defaults. Do not present a CPU path as GPU acceleration or assume a GPU is faster for every small request.

## Publish a public release

Update the server version in `pyproject.toml`, `cts_ocr_server/__init__.py`, Docker/image defaults and documentation, then commit and push. Create a matching tag such as `ocr-v0.14.0`.

The release workflow gates publishing on desktop/backend tests, model self-tests and real HTTPS/OCR integration. It tags the exact tested image and publishes version, source-commit and `latest` tags to GHCR using the repository’s temporary `GITHUB_TOKEN`, then pulls it back. OCI labels identify its source, version and revision.

The release workflow requires the existing package to be public. Set its visibility in GitHub's package settings before tagging the release; the helper verifies visibility and the linked repository before publishing and checks again before updating `latest`. It never changes visibility. For a separate private deployment, the helper supports `--visibility private`. Normal main/PR builds only test. Use a digest for an immutable deployment reference.
