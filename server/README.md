# CtS GPU OCR server

A headless PP-OCRv5 service using ncnn/Vulkan for neural-network inference. It keeps its detector and recognizer loaded and returns character positions for English, Japanese kana/kanji and Chinese. It needs no Qt, Tesseract, desktop session, CUDA or ROCm installation.

The local Radeon 610M (RADV RAPHAEL_MENDOCINO) has been tested with actual GPU inference, 14px kana/kanji on light and dark backgrounds, vertical Japanese and character selection through the HTTP client. The Intel HD 630 is an intended deployment target; it still needs to be checked on your server with its own Vulkan driver. Software Vulkan devices are rejected. GPU mode does not silently replace an unavailable GPU with a CPU pipeline. Image decoding, geometry and some utility operators run on the CPU.

## Docker on the desktop

From the project root:

```sh
python3 tools/setup_ocr_docker.py --gpu-name AMD --client
```

The helper builds the image, enumerates devices inside it, selects the requested GPU, generates a private token, starts a persistent container, checks readiness, then saves the connection in CtS. It binds only to localhost. Use `--replace` to update a container previously created by this helper. It never replaces a differently named/image container.

Reopen CtS with **Meta+Shift+G**. **⋮ → Text recognition…** offers **Local GPU (managed by CtS)**, **Self-hosted CtS server**, and **Local Tesseract (CPU)**. Saving Local GPU sets up the bundled CtS backend if necessary; later launches reuse or start its container. Server mode uses a separate address/token without changing the local GPU configuration. Local fallback is an explicit option. The check sends no screen image.

```sh
docker logs --tail 30 circle-to-search-ocr
docker inspect --format '{{.State.Health.Status}}' circle-to-search-ocr
docker stop circle-to-search-ocr
docker start circle-to-search-ocr
```

The helper stores server environment settings and a bearer token in `~/.config/circle-to-search/ocr-server.env`, mode `0600`. Desktop connection settings are in `ocr.json` beside it, also mode `0600`. These paths follow `XDG_CONFIG_HOME`.

## Self-host on the Intel server

Install Docker and the host's Intel graphics/Vulkan driver. The container supplies its own Mesa Vulkan userspace drivers; the host must expose a working `/dev/dri/renderD*` device. No display server is required.

```sh
cp server/.env.example server/.env
chmod 600 server/.env
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
stat -c %g /dev/dri/renderD128
```

Put the generated token and render-node group ID in `server/.env`. The file is gitignored. Build and enumerate the container's devices:

```sh
docker build -f server/Dockerfile -t circle-to-search-ocr:0.12.1 .
docker run --rm --device /dev/dri --group-add YOUR_RENDER_GID \
  circle-to-search-ocr:0.12.1 --list-devices
```

Set `CTS_OCR_GPU_INDEX` to the HD 630's index. For direct LAN access, set `CTS_OCR_BIND` to the server's LAN IP. The default is `127.0.0.1` for an SSH tunnel:

```sh
docker compose --env-file server/.env -f server/compose.yaml up -d --build
ssh -N -L 8766:127.0.0.1:8766 user@your-server
```

In CtS select **Self-hosted CtS server**, enter `http://127.0.0.1:8766` when using the tunnel, and paste the token. A direct LAN connection uses `http://your-server:8766`. Use an SSH tunnel or HTTPS reverse proxy when the network is not trusted: a bearer token authenticates requests but HTTP does not encrypt screenshots.

The Compose service uses a non-root user, the render-device group, a read-only root filesystem, temporary cache storage, a health check, bounded memory/processes and no Linux capabilities. Model files are downloaded at build time from a pinned upstream revision and checked against committed SHA-256 values. The running image can perform OCR offline. It contains neither the desktop client nor your screen captures.

### Updating and diagnosing repeated letters

From the checkout on the server, keeping your existing `server/.env`:

```sh
git pull --ff-only
docker compose --env-file server/.env -f server/compose.yaml up -d --build
docker compose --env-file server/.env -f server/compose.yaml logs --tail 40 ocr
```

Version 0.12.0 was observed returning hundreds of `Y` characters at 100% confidence from unrelated images on an Intel HD 630. Version 0.12.1 forces FP32 tensor storage and arithmetic before loading both networks, while retaining Vulkan GPU execution. It rejects non-finite/out-of-range model probabilities and invalid CTC distributions instead of converting corrupt values into selectable letters. ncnn documents reduced-precision inference as a possible source of incorrect or non-finite output; see its [troubleshooting guide](https://github.com/Tencent/ncnn/wiki/FAQ-ncnn-produce-wrong-result) and [Vulkan precision settings](https://github.com/Tencent/ncnn/wiki/vulkan-notes).

Every startup now recognizes two different known text images and checks a blank image. The server accepts requests only after this passes. Health reports `version`, `precision: "fp32"` and `self_test_passed: true`. A passing smoke test is a basic model/driver check, not a guarantee of accuracy on every screenshot. You can also run the check independently, without starting another HTTP listener:

```sh
docker compose --env-file server/.env -f server/compose.yaml run --rm ocr --gpu-index 0 --self-test
# Reference run with exactly the same models, without Vulkan:
docker compose --env-file server/.env -f server/compose.yaml run --rm ocr --device cpu --self-test
```

Use your configured GPU index in the first command. If the CPU check passes but the Vulkan check fails, keep the failed GPU service stopped and check/update the graphics driver or container Mesa package. CPU reference mode is available explicitly; the app never silently claims CPU inference is GPU acceleration.

## Direct Python deployment

Python 3.10+ with matching ncnn wheels and a working Vulkan driver:

```sh
python3 -m venv .venv-ocr
.venv-ocr/bin/pip install --require-hashes -r server/requirements.lock
.venv-ocr/bin/pip install --no-deps ./server
.venv-ocr/bin/cts-ocr-server --list-devices
.venv-ocr/bin/cts-ocr-server --gpu-name Intel --token-file /path/to/private/token
```

The service defaults to `127.0.0.1:8766`. Listening beyond localhost requires a token (`--token-file` or `CTS_OCR_SERVER_TOKEN`). `--device cpu` is an explicit reference/testing mode, reported as non-accelerated by the API and connection dialog.

## API

Both endpoints accept `Authorization: Bearer TOKEN` when authentication is enabled.

- `GET /v1/health`: API/server versions, readiness after the startup recognition test, precision, actual selected device, acceleration state, supported languages and character-box capability.
- `POST /v1/ocr?language=jpn%2Beng&vertical=false&priority=interactive`: raw `image/png` body. Priority is `interactive` or `background`.

The CtS-specific response contains `service: "circle-to-search-ocr"`, `api_version: 1`, original pixel `width`/`height`, `glyphs`, `engine`, `device`, `accelerated`, `elapsed_ms` and `queue_ms`. Each glyph has `text`, `bbox: [x,y,width,height]`, `line`, `word` and a 0–100 `confidence`. Coordinates refer to the submitted image, before desktop display scaling. Recognition uses CTC timestep positions mapped through the actual recognition crop; kana and kanji are individually selectable. Latin word IDs preserve word snapping and spaces.

The client applies physical crop offsets and display scaling exactly once. Existing generation tokens discard stale results after a new selection or language/backend change. The server holds at most eight queued requests, prioritizes queued gesture work over background scans and serializes GPU execution. An active background scan yields at model boundaries so a queued gesture crop can run before the next text line; it does not interrupt a Vulkan submission already in progress. Uploads are limited to 16 MiB / 24 million pixels. The service does not save uploads or log their contents.

Server mode sends the frozen monitor image and regional crops to the configured server. Google still receives only the selection when a search or translation is requested. Selecting local Tesseract keeps OCR on the desktop.

## Verification

```sh
# API, authentication, queue priority, failure paths and geometry tests in Docker
docker build --target test -f server/Dockerfile -t circle-to-search-ocr:test .
# Actual GPU/container/client checks; uses synthetic images only
python3 tools/ocr_server_smoke.py --docker circle-to-search-ocr:0.12.1 --gpu-name AMD
# Explicit CPU reference integration check
python3 tools/ocr_server_smoke.py --docker circle-to-search-ocr:0.12.1 --device cpu
```

The FP32 Radeon container check measured roughly 65–90 ms per request across these synthetic 900×160 / 180×500 fixtures. The same models in explicit CPU reference mode on the 7800X3D measured roughly 35–51 ms. Full precision costs time compared with the previous reduced-precision run (about 45–60 ms), and this small Radeon is not faster than that CPU on these inputs. These are synthetic checks, not guarantees for full-screen captures, arbitrary fonts or remote-network latency. Successful FP32 HD 630 inference and its performance still need verification on the server.

See [third-party sources and licenses](THIRD_PARTY.md).
