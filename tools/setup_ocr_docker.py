"""Set up CtS's managed local GPU backend from a checkout."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    from circle_to_search.managed_ocr import ensure_local
    from circle_to_search.ocr_backend import OcrConfig,check_server
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gpu-name',default='AMD')
    parser.add_argument('--port',type=int,default=8766)
    parser.add_argument('--client',action='store_true')
    parser.add_argument('--replace',action='store_true')
    parser.add_argument('--skip-build',action='store_true',help='Retained for compatibility; existing images are always reused')
    args=parser.parse_args()
    if not 1<=args.port<=65535:parser.error('Port must be between 1 and 65535.')
    config=OcrConfig(backend='gpu',local_gpu_name=args.gpu_name)
    connection=ensure_local(config,setup=True,replace_existing=args.replace,port=args.port)
    info=check_server(connection)
    if args.client:config.save()
    print('Local CtS GPU backend ready:',info['device'])
    print('Connection:',connection.server_url)
    print('Local GPU selected in CtS.' if args.client else 'Select Local GPU under More → Text recognition.')
    return 0


if __name__=='__main__':raise SystemExit(main())
