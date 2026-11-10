"""Container readiness probe without importing any inference libraries."""

import json
import os
import urllib.request


def main():
    request=urllib.request.Request('http://127.0.0.1:8766/v1/health')
    token=os.environ.get('CTS_OCR_SERVER_TOKEN','')
    if token:request.add_header('Authorization','Bearer '+token)
    with urllib.request.urlopen(request,timeout=4) as response:
        payload=json.load(response)
    return 0 if payload.get('api_version')==1 and payload.get('status')=='ready' else 1


if __name__=='__main__':raise SystemExit(main())
