"""Only explicit search actions send data to a search provider."""

import secrets
import urllib.error
import urllib.parse
import urllib.request

LENS_UPLOAD_URL = "https://lens.google.com/v3/upload"

SEARCH_MODES = {
    "ai": "50",
    "images": "2",
    "videos": "7",
    "shopping": "28",
    "forums": "18",
    "web": "14",
}


def external_navigation(url: str, new_window=False) -> bool:
    """Keep search controls embedded while sending destinations to the desktop."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return bool(parts.scheme) and parts.scheme not in (
            "about",
            "data",
            "blob",
            "javascript",
            "file",
            "qrc",
            "chrome",
            "devtools",
        )
    if new_window:
        return True
    if parts.hostname in ("accounts.google.com", "consent.google.com", "lens.google.com"):
        return False
    if parts.hostname == "translate.google.com" and parts.path in ("", "/", "/m"):
        return False
    if parts.hostname in ("google.com", "www.google.com"):
        return not (
            parts.path
            in ("", "/", "/search", "/webhp", "/imgres", "/imghp", "/preferences", "/setprefs")
            or parts.path.startswith("/sorry/")
        )
    return True


def search_tab(url: str) -> str:
    params = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
    legacy = {"isch": "images", "vid": "videos", "nws": "news", "shop": "shopping", "bks": "books"}
    if params.get("tbm") in legacy:
        return legacy[params["tbm"]]
    return {mode: tab for tab, mode in SEARCH_MODES.items()}.get(params.get("udm"), "all")


def search_tab_url(url: str, tab: str, query: str = "") -> str:
    """Change the search view without replacing its query or Lens session."""
    parts = urllib.parse.urlsplit(url or text_search_url(query))
    if (
        parts.hostname not in ("www.google.com", "google.com", "lens.google.com")
        or parts.path != "/search"
    ):
        parts = urllib.parse.urlsplit(text_search_url(query))
    params = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
    for name in ("udm", "tbm", "start"):
        params.pop(name, None)
    if tab in SEARCH_MODES:
        params["udm"] = SEARCH_MODES[tab]
    elif tab == "news":
        params["tbm"] = "nws"
    elif tab == "books":
        params["tbm"] = "bks"
    elif tab == "all" and ("vsrid" in params or "lsessionid" in params):
        params["udm"] = "24" if params.get("q") else "26"
    return normalize_search_url(
        urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(params)))
    )


def normalize_search_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    if (
        parts.hostname not in ("www.google.com", "google.com", "lens.google.com")
        or parts.path != "/search"
    ):
        return url
    params = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
    # Use the public Search route. Chrome's side-panel parameters can receive
    # access-denied responses in an embedded browser. The color scheme comes from
    # the app's browser theme rather than a special Google rendering mode.
    for key in ("cs", "gl", "gsc", "lr"):
        params.pop(key, None)
    params["hl"] = "en"
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(params)))


def browser_search_url(url: str) -> str:
    """Use the normal web route when handing a denied request to a browser."""
    parts = urllib.parse.urlsplit(url)
    if (
        parts.hostname not in ("www.google.com", "google.com", "lens.google.com")
        or parts.path != "/search"
    ):
        return url
    params = [
        (key, value)
        for key, value in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        if key != "gsc"
    ]
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(params)))


def lens_upload_data(png: bytes):
    boundary = "----CircleToSearch" + secrets.token_hex(16)
    body = (
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="encoded_image"; filename="selection.png"\r\n'
            "Content-Type: image/png\r\n\r\n"
        ).encode()
        + png
        + f"\r\n--{boundary}--\r\n".encode()
    )
    return body, f"multipart/form-data; boundary={boundary}"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # The result belongs in the user's browser, not this HTTP client.
        return None


def valid_results_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlsplit(url)
        return (
            parsed.scheme == "https"
            and parsed.hostname
            in {
                "google.com",
                "www.google.com",
                "lens.google.com",
            }
            and parsed.username is None
            and parsed.password is None
            and parsed.port in (None, 443)
        )
    except ValueError:
        return False


def upload_to_lens(png: bytes, query: str = "") -> str:
    """Upload one crop and return Google's redirect without scraping results.

    This is Google's web upload endpoint, not a supported public Lens API.
    The UI offers save/open fallback if Google changes it or rejects the request.
    """
    body, content_type = lens_upload_data(png)
    request = urllib.request.Request(
        LENS_UPLOAD_URL + "?ep=ccm&s=csp",
        data=body,
        headers={
            "Content-Type": content_type,
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
            # Reject optional cookies for this stateless request. Without this,
            # EU uploads can redirect to consent before processing the image.
            "Cookie": "SOCS=CAI",
        },
    )
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=25):
            raise RuntimeError(
                "Google did not return a results link. Save the crop and open Lens manually."
            )
    except urllib.error.HTTPError as exc:
        try:
            if exc.code in (301, 302, 303):
                url = urllib.parse.urljoin(LENS_UPLOAD_URL, exc.headers.get("Location", ""))
                if valid_results_url(url) and urllib.parse.urlsplit(url).path not in (
                    "",
                    "/v3/upload",
                ):
                    if query:
                        parts = urllib.parse.urlsplit(url)
                        parameters = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
                        parameters = [(key, value) for key, value in parameters if key != "q"] + [
                            ("q", query)
                        ]
                        url = urllib.parse.urlunsplit(
                            parts._replace(query=urllib.parse.urlencode(parameters))
                        )
                    return normalize_search_url(url)
            raise RuntimeError(
                f"Google Lens could not complete the upload (HTTP {exc.code}). "
                "Save the crop and use Open Lens instead."
            ) from exc
        finally:
            exc.close()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(
            "Could not reach Google Lens. Check your connection or use Open Lens."
        ) from exc


def text_search_url(text: str) -> str:
    return normalize_search_url(
        "https://www.google.com/search?" + urllib.parse.urlencode({"q": text})
    )


def translation_url(text: str, target: str = "en") -> str:
    return "https://translate.google.com/?" + urllib.parse.urlencode(
        {"sl": "auto", "tl": target, "hl": "en", "text": text, "op": "translate"}
    )
