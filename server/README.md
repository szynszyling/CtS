# Run your own OCR server 🐳

The OCR server is the part of CtS that reads text from screenshots. Running it on your NAS lets your desktop app use that machine’s hardware.

The ready-made image is **`ghcr.io/szynszyling/cts-ocr:0.12.3`**. It includes the models and all runtime dependencies, so you do not need Python or a source build on the NAS. The image is currently **private** and supports Linux AMD64, including the tested Intel HD 630 server.

## What you need

- Docker with Docker Compose.
- A Linux machine with a working Vulkan GPU and `/dev/dri` render device.
- Access to the private GitHub container image.
- A copy of the Compose files and `.env.example` from this folder.

The desktop app itself still needs to be installed on your computer. This container only reads text; Google search results remain part of the desktop app.

## 1. Sign in to the image registry 🔑

On the NAS, run:

```sh
docker login ghcr.io --username szynszyling
```

At the password prompt, use a **GitHub personal access token (classic)** with **`read:packages`** and access to this package. Your normal GitHub password will not work. [GitHub’s instructions](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry#authenticating-with-a-personal-access-token-classic) explain how to create the token.

This registry token is different from the OCR token you will enter in CtS.

## 2. Fill in the server settings ⚙️

The commands below start from the main CtS project folder. Copy the example settings file once:

```sh
cp server/.env.example server/.env
chmod 600 server/.env
```

For an existing installation, keep your current `.env` instead of copying over it.

Generate an OCR token inside the image:

```sh
docker run --rm --entrypoint python ghcr.io/szynszyling/cts-ocr:0.12.3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Find the GPU’s render-group number:

```sh
stat -c %g /dev/dri/renderD128
```

Open `server/.env` in a text editor and fill in:

| Setting | What to enter |
| --- | --- |
| `CTS_OCR_SERVER_TOKEN` | The OCR token you just generated |
| `CTS_OCR_RENDER_GID` | The number printed by `stat` |
| `CTS_OCR_GPU_INDEX` | Usually `0`; see the device check below if you have several GPUs |

If the render device is missing, the GPU/driver needs attention before the container can use it.

## 3. Choose how you will connect 🌐

**Already use SWAG?** Follow the [SWAG setup guide](REMOTE_ACCESS.md). It works like other SWAG services: a shared Docker network and a small Nginx configuration. The existing container name can remain your upstream; the provided override also gives it the alias `cts-ocr` on port `8766`.

**Only need access at home?** Set `CTS_OCR_BIND` in `.env` to your NAS’s local IP address, then run:

```sh
docker compose --env-file server/.env -f server/compose.yaml pull
docker compose --env-file server/.env -f server/compose.yaml up -d
```

The default bind address is `127.0.0.1`, which only allows connections from the NAS itself. Use HTTPS or a VPN for access away from home.

To list available GPUs:

```sh
docker compose --env-file server/.env -f server/compose.yaml run --rm ocr --list-devices
```

To see whether the server started correctly:

```sh
docker compose --env-file server/.env -f server/compose.yaml logs --tail 30 ocr
```

## 4. Connect the desktop app ✅

In CtS open **⋮ → Text recognition → Self-hosted CtS server**.

1. Enter the server address: your HTTPS domain, or `http://YOUR-NAS-IP:8766` on your home network.
2. Enter the **OCR token** from `.env`.
3. Click **Check server connection**, then **Save**.
4. Close and reopen the overlay.

A successful connection reports the GPU in use. Screenshots and nearby selection crops are sent to your server for text recognition.

## Update the image

The Compose file pins a tested release. To choose another release, set `CTS_OCR_IMAGE` in `.env` to its full image name. You can choose `ghcr.io/szynszyling/cts-ocr:latest` if you prefer the newest tested release whenever you update.

Run the same Compose configuration you normally use:

```sh
docker compose --env-file server/.env -f server/compose.yaml pull
docker compose --env-file server/.env -f server/compose.yaml up -d
```

If you use the SWAG override, include `-f server/compose.swag.yaml` in **both** commands. Your GPU, OCR token and network settings stay in `.env`.

## If something goes wrong

| Message or symptom | What to check |
| --- | --- |
| Registry says “denied” | Run `docker login` with a GitHub classic token that has `read:packages`. |
| CtS reports HTTP 401 | Check the OCR token. Do not enter the GitHub registry token in CtS. |
| SWAG reports HTTP 502 | Check that SWAG and OCR share a Docker network and that the upstream name/port are correct. |
| Certificate warning | Use a hostname covered by the certificate. A DuckDNS wildcard certificate covers `cts.yourname.duckdns.org`, not necessarily `yourname.duckdns.org`. |
| The container is unhealthy or restarts | Read its logs. The recognition startup test must pass before it accepts images. |
| No GPU is found | Check `/dev/dri`, the render-group number and the selected GPU index. |

Local GPU setup on the desktop is available through **⋮ → Text recognition → Local GPU**. Developer API details, benchmarks, source builds and image publishing are in [DEVELOPMENT.md](DEVELOPMENT.md).
