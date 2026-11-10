"""Exercise the supplied SWAG virtual host with real TLS and a CtS container.

Uses an isolated Docker network, loopback-only HTTPS port, temporary test CA
and synthetic text. Does not use or change your OCR settings/SWAG container.
"""

import argparse
from dataclasses import replace
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from circle_to_search.ocr_backend import OcrConfig,check_server,recognize_remote,server_request
from tools.ocr_server_smoke import fixture


def docker(*arguments,**kwargs):
    return subprocess.run(['docker',*arguments],check=True,capture_output=True,text=True,timeout=120,**kwargs).stdout.strip()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',default='circle-to-search-ocr:0.12.3')
    parser.add_argument('--nginx-image',default='nginx:stable-alpine')
    args=parser.parse_args()
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    app=QApplication([])
    prefix='cts-https-smoke-'+secrets.token_hex(4)
    network=prefix+'-net';backend=prefix+'-ocr';proxy=prefix+'-proxy'
    previous_ca=os.environ.get('SSL_CERT_FILE')
    containers=[];network_created=False
    with tempfile.TemporaryDirectory(prefix=prefix) as directory:
        root=Path(directory)
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1',
                        '-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost',
                        '-keyout',str(root/'key.pem'),'-out',str(root/'cert.pem')],
                       check=True,capture_output=True,timeout=30)
        (root/'ssl.conf').write_text('ssl_certificate /config/nginx/cert.pem;\nssl_certificate_key /config/nginx/key.pem;\n')
        (root/'resolver.conf').write_text('resolver 127.0.0.11 valid=5s;\n')
        source=Path(__file__).resolve().parents[1]/'server/swag/cts.subdomain.conf.sample'
        with socket.socket() as handle:
            handle.bind(('127.0.0.1',0));port=handle.getsockname()[1]
        token=secrets.token_urlsafe(32)
        environment=os.environ.copy();environment['CTS_OCR_SERVER_TOKEN']=token
        config=OcrConfig('server',f'https://localhost:{port}',token,3)
        try:
            docker('network','create',network);network_created=True
            docker('run','-d','--rm','--name',backend,'--network',network,'--network-alias','cts-ocr',
                   '--env','CTS_OCR_SERVER_TOKEN','--read-only','--tmpfs','/tmp:size=256m',
                   '--cap-drop','ALL','--security-opt','no-new-privileges:true',
                   args.image,'--host','0.0.0.0','--device','cpu',env=environment)
            containers.append(backend)
            docker('run','-d','--rm','--name',proxy,'--network',network,'--read-only',
                   '--tmpfs','/var/cache/nginx','--tmpfs','/var/run',
                   '--publish',f'127.0.0.1:{port}:443',
                   '--mount',f'type=bind,source={root},target=/config/nginx,readonly',
                   '--mount',f'type=bind,source={source},target=/etc/nginx/conf.d/default.conf,readonly',
                   '--entrypoint','nginx',args.nginx_image,'-g','daemon off;')
            containers.append(proxy)
            os.environ['SSL_CERT_FILE']=str(root/'cert.pem')
            deadline=time.monotonic()+45
            while True:
                try:health=check_server(config);break
                except RuntimeError:
                    if time.monotonic()>deadline:raise
                    time.sleep(.15)
            assert health['self_test_passed'] and not health['accelerated']
            print('Trusted HTTPS -> exact SWAG virtual host -> CtS container: ready.',flush=True)
            docker('exec',proxy,'nginx','-t')
            document=recognize_remote(fixture('日本語かな漢字',18),'jpn+eng',False,'interactive',config)
            assert document.text()=='日本語かな漢字',document.text()
            print('Real Japanese OCR and bearer header forwarding passed.',flush=True)
            try:check_server(replace(config,token='wrong'))
            except RuntimeError as error:assert 'token' in str(error)
            else:raise AssertionError('Wrong token was accepted.')
            try:server_request(config,'/v1/ocr',b'x'*(16*1024*1024+1))
            except RuntimeError as error:assert 'too large' in str(error)
            else:raise AssertionError('Proxy accepted an oversized image.')
            if previous_ca is None:os.environ.pop('SSL_CERT_FILE',None)
            else:os.environ['SSL_CERT_FILE']=previous_ca
            try:check_server(config)
            except RuntimeError as error:assert 'HTTPS certificate' in str(error),str(error)
            else:raise AssertionError('An untrusted HTTPS certificate was accepted.')
            print('Invalid token, 16 MiB limit and TLS certificate verification passed.',flush=True)
        except Exception:
            for container in containers:
                try:print(container,docker('logs','--tail','25',container),file=sys.stderr)
                except subprocess.SubprocessError:pass
            raise
        finally:
            if previous_ca is None:os.environ.pop('SSL_CERT_FILE',None)
            else:os.environ['SSL_CERT_FILE']=previous_ca
            for container in reversed(containers):
                subprocess.run(['docker','rm','-f',container],capture_output=True,timeout=30)
            if network_created:
                subprocess.run(['docker','network','rm',network],capture_output=True,timeout=30)
    return 0


if __name__=='__main__':raise SystemExit(main())
