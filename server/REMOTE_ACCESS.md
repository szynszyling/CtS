# CtS through your existing SWAG 🌐

CtS works like other SWAG services: one container on the same Docker network, plus a normal Nginx proxy config. Deploy the backend using just **[compose.yaml](../compose.yaml)** in any folder on your NAS; follow the [single-file setup guide](README.md).

Both CtS and SWAG must use the existing external Docker network **`server`**. The upstream is **`cts-ocr:8766`**, using HTTP inside the Docker network. SWAG handles public HTTPS.

## Nginx configuration

Save this as `/config/nginx/proxy-confs/cts.subdomain.conf` inside SWAG’s existing persistent configuration folder:

```nginx
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name cts.*;

    include /config/nginx/ssl.conf;
    client_max_body_size 16m;

    location / {
        include /config/nginx/resolver.conf;
        set $upstream_app cts-ocr;
        proxy_pass http://$upstream_app:8766;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Authorization $http_authorization;
        proxy_connect_timeout 5s;
        proxy_send_timeout 65s;
        proxy_read_timeout 65s;
        proxy_next_upstream off;
        proxy_request_buffering off;
        proxy_buffering off;
    }
}
```

The same config is also available as [cts.subdomain.conf.sample](swag/cts.subdomain.conf.sample). Download/copy that file directly if preferred; no repository clone is needed.

Check and reload SWAG, substituting its actual container name if different:

```sh
docker exec swag nginx -t
docker exec swag nginx -s reload
```

Reload after the syntax check succeeds. Standard SWAG installations already load `*.subdomain.conf` from this folder. An existing working CtS config only needs its upstream changed to `cts-ocr`.

## Domain and certificate

Use a hostname such as **`cts.yourname.duckdns.org`**. A certificate for `*.yourname.duckdns.org` covers that hostname, but not `yourname.duckdns.org` itself. See [SWAG’s DuckDNS certificate documentation](https://docs.linuxserver.io/images/docker-swag/#validation-and-initial-setup).

Keep the router’s existing TCP 443 forwarding to SWAG. CtS does not need its own forwarded port. Retain SWAG’s current certificate-renewal settings. If the router lacks NAT loopback, local/split DNS can resolve the same hostname to the NAS while at home.

## Connect CtS

In the desktop app, choose **Self-hosted CtS server**, enter your HTTPS address and the OCR token from your single Compose file, then check the connection and save.

An unauthenticated browser request to `/v1/health` should return **401**. An authenticated desktop check reports the actual GPU. A welcome page means Nginx selected its default site; a **502** means it could not reach the backend.

CtS uses bearer authentication. An extra Basic-auth or interactive SSO login would conflict with the API’s Authorization header. The desktop verifies the HTTPS hostname and certificate chain.

## Optional speed setting

The standalone file contains `CTS_OCR_DETECTOR_SCALE: "2"`. You can try `"1.5"`, then run `docker compose up -d` to recreate the service. Lower enlargement reduces detector work on small crops but can miss tiny text. FP32 Vulkan recognition remains enabled. Restore `"2"` if detection worsens.
