# OCR server: one Compose file 🐳

Your NAS needs only **[compose.yaml](../compose.yaml)** and the image Docker pulls. No repository clone, Python installation, source build, `.env` file or extra application configuration files are needed.

The server image includes GPU recognizers for all 19 CtS language choices and runs OCR offline after the image is pulled. Polish, Cyrillic, Greek, Korean, Japanese and Chinese all use Vulkan. The image supports Linux AMD64 with a Vulkan GPU. The earlier engine was tested on Intel HD 630, and the multilingual engine is tested on AMD Radeon.

## 1. Save the file 📄

Make any folder on your NAS, such as `~/docker/cts-ocr`, and save the linked file there as **`compose.yaml`**. You can use GitHub’s Raw/Download button or copy its contents into a text editor.

## 2. Fill in two values ⚙️

Edit that same file:

| Field | What to enter |
| --- | --- |
| `CTS_OCR_SERVER_TOKEN` | Your existing OCR token, between the quotes. The server refuses to start while this is empty. |
| `group_add` | Replace `RENDER_GROUP_ID` with the number from `stat -c %g /dev/dri/renderD128`. |

The file joins the existing external network **`server`**, which must also be used by SWAG:

```yaml
networks:
  server:
    external: true
```

You can leave the GPU index at `0` when the correct GPU is the first one. The default detector scale is `2`.

If you need a new OCR token, generate one with:

```sh
openssl rand -hex 32
```

Keep `compose.yaml` private because it contains your OCR token. You can restrict access with `chmod 600 compose.yaml`.

## 3. Start ✅

The image is public. No GitHub account, registry login or GitHub access token is needed. The OCR token in your Compose file still protects your running server.

From the folder containing your `compose.yaml`:

```sh
docker compose up -d
```

Docker downloads `ghcr.io/szynszyling/cts-ocr:latest` and starts the container. No project checkout is involved.

## 4. Point SWAG at it 🌐

Use the same setup as your other SWAG services:

- **Upstream app:** `cts-ocr`
- **Upstream port:** `8766`
- **Upstream protocol:** `http`
- **Subdomain:** `cts`

SWAG and CtS share the existing `server` network. SWAG supplies HTTPS using its existing certificate. The Compose file does not publish the OCR port on the host.

See the [SWAG guide](REMOTE_ACCESS.md) for a copyable Nginx config. If you already have a working CtS proxy, change its upstream name to `cts-ocr` and reload Nginx.

In the desktop app, choose **⋮ → Text recognition → Self-hosted CtS server**. Enter your HTTPS address and the OCR token, then check the connection and save.

Open **⋮ → OCR languages…** and select the languages you want recognized. The server retains every recognizer and runs the ones your request needs. Languages from the same group share a recognizer. Choosing a small set of groups reduces recognition work.

## Local GPU on your computer 💻

Choose **⋮ → Text recognition → Local GPU** in CtS on Linux, then select your languages under **⋮ → OCR languages…**. CtS builds a `local` profile containing only the required recognizers. It manages the Docker container, localhost connection and token.

The published image uses the `server` profile with all recognizers. Server deployment keeps using the single Compose file above. Source-build options are in the [developer guide](DEVELOPMENT.md).

Windows uses a native worker with the same selected recognizers and verified downloader. Choose languages in the desktop app to prepare that worker. The [Windows guide](../packaging/windows/README.md) covers its installer and GPU setup.

## Updating and checking it

From the same folder:

```sh
docker compose pull
docker compose up -d
```

`latest` points to the most recent tested release. To pin a particular release, change the image line to a version such as `ghcr.io/szynszyling/cts-ocr:0.14.0`.

Useful commands:

```sh
docker compose ps
docker compose logs --tail 30 ocr
docker compose run --rm ocr --list-devices
docker compose down
```

## Moving from the old checkout-based setup

Copy your current OCR token and render-group number into the single file. Make sure SWAG uses the existing `server` network. Start the new stack, update the SWAG upstream to `cts-ocr`, and check the desktop connection. After that succeeds, stop the old `server-ocr-1` container. The new deployment does not depend on the old checkout.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Registry says “denied” | Check the image name. Public pulls need no login; an expired saved registry login may need refreshing or removing. |
| The external network is not found | Check that the existing `server` Docker network is present and SWAG uses it. |
| The render group is not found | Replace the group placeholder with the numeric render-group ID. |
| CtS reports HTTP 401 | Check the OCR token; it is not the GitHub registry token. |
| SWAG reports HTTP 502 | Check the shared network, upstream `cts-ocr:8766` and container logs. |
| The container is unhealthy or restarts | Read its logs. GPU initialization and the recognition startup test must succeed. |

The desktop app runs on your computer. This container only reads text from screenshots. Developer API details, source builds and image publishing are in [DEVELOPMENT.md](DEVELOPMENT.md).
