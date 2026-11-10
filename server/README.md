# OCR server: one Compose file 🐳

Your NAS needs only **[compose.yaml](../compose.yaml)** and the image Docker pulls. No repository clone, Python installation, source build, `.env` file or extra application configuration files are needed.

The image includes the OCR models and runtime dependencies. It supports Linux AMD64 with a Vulkan GPU, including the tested Intel HD 630.

## 1. Save the file 📄

Make any folder on your NAS, such as `~/docker/cts-ocr`, and save the linked file there as **`compose.yaml`**. You can use GitHub’s Raw/Download button or copy its contents into a text editor.

## 2. Fill in three values ⚙️

Edit that same file:

| Field | What to enter |
| --- | --- |
| `CTS_OCR_SERVER_TOKEN` | Your existing OCR token, between the quotes. The server refuses to start while this is empty. |
| `group_add` | Replace `RENDER_GROUP_ID` with the number from `stat -c %g /dev/dri/renderD128`. |
| Network `name` | Replace `SWAG_NETWORK_NAME` with the existing Docker network used by SWAG. |

You can leave the GPU index at `0` when the correct GPU is the first one. The default detector scale is `2`.

If you need a new OCR token, generate one with:

```sh
openssl rand -hex 32
```

Keep `compose.yaml` private because it contains your OCR token. You can restrict access with `chmod 600 compose.yaml`.

## 3. Log in and start ✅

The image is currently private. Log in once on the NAS:

```sh
docker login ghcr.io --username szynszyling
```

Use a GitHub **personal access token (classic)** with **`read:packages`** as the password. This registry credential is separate from the OCR token in your Compose file. [GitHub’s instructions](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry#authenticating-with-a-personal-access-token-classic) explain how to create it.

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

SWAG and CtS share the network you entered above. SWAG supplies HTTPS using its existing certificate. The Compose file does not publish the OCR port on the host.

See the [SWAG guide](REMOTE_ACCESS.md) for a copyable Nginx config. If you already have a working CtS proxy, change its upstream name to `cts-ocr` and reload Nginx.

In the desktop app, choose **⋮ → Text recognition → Self-hosted CtS server**. Enter your HTTPS address and the OCR token, then check the connection and save.

## Updating and checking it

From the same folder:

```sh
docker compose pull
docker compose up -d
```

`latest` points to the most recent tested release. To pin a particular release, change the image line to a version such as `ghcr.io/szynszyling/cts-ocr:0.12.3`.

Useful commands:

```sh
docker compose ps
docker compose logs --tail 30 ocr
docker compose run --rm ocr --list-devices
docker compose down
```

## Moving from the old checkout-based setup

Copy your current OCR token, render-group number and SWAG network into the single file. Start the new stack, update the SWAG upstream to `cts-ocr`, and check the desktop connection. After that succeeds, stop the old `server-ocr-1` container. The new deployment does not depend on the old checkout.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Registry says “denied” | Run `docker login` with a GitHub classic token that has `read:packages`. |
| The external network is not found | Enter the name of SWAG’s existing network in `compose.yaml`. |
| The render group is not found | Replace the group placeholder with the numeric render-group ID. |
| CtS reports HTTP 401 | Check the OCR token; it is not the GitHub registry token. |
| SWAG reports HTTP 502 | Check the shared network, upstream `cts-ocr:8766` and container logs. |
| The container is unhealthy or restarts | Read its logs. GPU initialization and the recognition startup test must succeed. |

The desktop app runs on your computer. This container only reads text from screenshots. Developer API details, source builds and image publishing are in [DEVELOPMENT.md](DEVELOPMENT.md).
