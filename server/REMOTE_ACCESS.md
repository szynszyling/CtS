# Public HTTPS through your existing SWAG

CtS supports a domain, a trusted HTTPS certificate and its existing bearer token. This deployment reuses SWAG for TLS; the OCR container handles recognition and authentication. No second proxy, public OCR port or browser login is needed.

Use a subdomain such as **`cts.yourname.duckdns.org`**. A certificate for `*.yourname.duckdns.org` covers this hostname, but does not cover `yourname.duckdns.org` itself. This distinction matters for DuckDNS's wildcard certificate mode; see [SWAG's certificate documentation](https://docs.linuxserver.io/images/docker-swag/#validation-and-initial-setup).

## Connect the containers

Run these commands on the server, from the CtS checkout. The existing SWAG container is called `swag` below; substitute its actual name if different. Keep your current `server/.env` and token. Docker Compose 2.24.4+ is required for the port-reset override.

```sh
git pull --ff-only
docker build -f server/Dockerfile -t circle-to-search-ocr:0.12.2 .
docker network create cts-proxy
docker network connect cts-proxy swag
docker compose --env-file server/.env -f server/compose.yaml -f server/compose.swag.yaml up -d
```

Create/connect the network once; skip those two commands if it already exists and SWAG is attached. `CTS_OCR_PROXY_NETWORK` in `server/.env` can select another existing Docker network. The OCR service receives the network alias `cts-ocr`, which the supplied Nginx configuration resolves at request time.

The override removes all OCR host-port mappings. Your old LAN address on port 8766 will stop working; use the HTTPS address after enabling the route. To persist SWAG's network attachment when its container is **recreated**, add the external network to SWAG's own Compose service as well:

```yaml
services:
  swag:
    # Keep your existing image, volumes, ports and environment here.
    networks:
      # Keep any other networks you already use.
      cts-proxy: {}
networks:
  cts-proxy:
    external: true
```

If SWAG previously used the implicit default network, explicitly retain `default: {}` under its service's `networks` along with `cts-proxy: {}`. Otherwise its existing upstream services could lose connectivity.

## Enable the SWAG route

The supplied virtual host uses `server_name cts.*` and SWAG's existing `/config/nginx/ssl.conf`. It forwards the bearer header unchanged, permits the API's 16 MiB image limit and avoids writing uploaded PNGs to proxy request-buffer files. It deliberately uses its own API proxy settings rather than including SWAG's general `proxy.conf`, which could define conflicting timeouts.

Copy the file to SWAG's persistent configuration directory. If a `cts.subdomain.conf` already exists, review/back it up before replacing it.

```sh
docker cp server/swag/cts.subdomain.conf.sample swag:/config/nginx/proxy-confs/cts.subdomain.conf
docker exec swag nginx -t
docker exec swag nginx -s reload
```

Reload only after the syntax check succeeds. Standard SWAG installations already include `*.subdomain.conf` from their default site configuration. A customized installation must retain that include.

Make sure the hostname resolves to your home connection and the router forwards **TCP 443 to SWAG's HTTPS port**. Keep your existing certificate-validation forwarding/settings: HTTP validation normally also uses port 80, while DNS validation does not need it. Do not forward port 8766. If the router lacks NAT loopback, use local/split DNS so this same hostname resolves to the NAS at home.

In CtS open **⋮ → Text recognition → Self-hosted CtS server** and enter:

- Server address: `https://cts.yourname.duckdns.org`
- Server token: your existing OCR token

Click **Check server connection**, save, and reopen the overlay. A normal browser request to `/v1/health` without a token should return **401**. An authenticated CtS connection should report your GPU. A welcome page/HTML response means the request reached SWAG's default site rather than this OCR route. A **502** means SWAG could not reach the backend; check the shared network and the OCR container's startup test/logs.

The API uses bearer authentication. Do not put an additional Basic-auth or interactive SSO login in front of this virtual host: CtS sends its own Authorization header and cannot complete a browser login. The desktop verifies the HTTPS hostname and certificate chain; a hostname mismatch must be fixed at the certificate/URL, without disabling verification.

## Faster recognition

Regional crops already avoid waiting for an entire screen scan. On the tested HD 630, identical Japanese text took roughly **393 ms** in a 900×160 image and **193 ms** in a tight 310×45 crop, with about 10–13 ms outside server inference. These are three-request medians on the home LAN, not an off-site latency guarantee.

The default detector enlargement remains `2`, preserving the tested small-text behavior. For an optional speed/accuracy tradeoff, set this in `server/.env` and recreate the service with both Compose files:

```dotenv
CTS_OCR_DETECTOR_SCALE=1.5
```

Lower enlargement reduces detector work on small crops; it may miss tiny text. Character recognition still uses its original full-resolution crop and FP32 Vulkan inference. Startup self-tests run with the selected scale, and health reports `detector_scale`. Test your fonts, kana/kanji and vertical selections before keeping it. `1` is the minimum and `2` the maximum; large captures still have a 1600-pixel detector-side cap. Restore `2` if detection worsens. This does not re-enable the reduced precision that broke HD 630 inference.

Scale `1.5` passed the container/client integration checks on the Radeon 610M, including 14px light/dark Japanese and vertical character selection. Sample requests took about 49–77 ms, compared with 65–90 ms in the earlier scale-2 run. These separate runs are indicative rather than a controlled speedup measurement; scale `1.5` still needs checking on the HD 630.
