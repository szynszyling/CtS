"""Publish a tested container without changing its private package visibility."""

import argparse
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request


def package_info(image,token):
    registry,owner,name=image.split('/',2)
    if registry!='ghcr.io':raise ValueError('Only GitHub Container Registry is supported.')
    url='https://api.github.com/users/'+owner+'/packages/container/'+urllib.parse.quote(name,safe='')
    request=urllib.request.Request(url,headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json'})
    try:
        with urllib.request.urlopen(request,timeout=20) as response:return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code==404:return None
        raise RuntimeError(f'Could not verify container package visibility (HTTP {error.code}).') from error


def require_private(info,repository):
    if info is None:return  # GitHub creates new container packages as private.
    if info.get('visibility')!='private':
        raise RuntimeError('Refusing to publish to a non-private package. Package visibility must stay private.')
    linked=(info.get('repository') or {}).get('full_name')
    if linked and linked.lower()!=repository.lower():
        raise RuntimeError('The container package belongs to another repository.')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',required=True)
    parser.add_argument('--version',required=True)
    parser.add_argument('--source',default='cts-ocr:ci')
    args=parser.parse_args(argv)
    if not re.fullmatch(r'ghcr\.io/[a-z0-9-]+/[a-z0-9._-]+',args.image):parser.error('Invalid image name.')
    if not re.fullmatch(r'\d+\.\d+\.\d+',args.version):parser.error('Invalid release version.')
    token=os.environ['GHCR_TOKEN'];repository=os.environ['GITHUB_REPOSITORY']
    revision=os.environ['GITHUB_SHA'];actor=os.environ['GITHUB_ACTOR']
    require_private(package_info(args.image,token),repository)
    # The exact image that passed tests is tagged, rather than being rebuilt.
    subprocess.run(['docker','login','ghcr.io','--username',actor,'--password-stdin'],input=token,text=True,check=True)
    try:
        tags=(args.version,'sha-'+revision,'latest')
        for tag in tags:
            subprocess.run(['docker','tag',args.source,args.image+':'+tag],check=True)
        subprocess.run(['docker','push',args.image+':'+args.version],check=True)
        for attempt in range(10):
            info=package_info(args.image,token)
            if info is not None:break
            time.sleep(1)
        if info is None:raise RuntimeError('Published package metadata is not available yet; latest was not updated.')
        require_private(info,repository)
        for tag in tags[1:]:subprocess.run(['docker','push',args.image+':'+tag],check=True)
        subprocess.run(['docker','pull',args.image+':'+args.version],check=True)
    finally:
        subprocess.run(['docker','logout','ghcr.io'],check=False)
    print('Published private image:',args.image+':'+args.version,flush=True)
    summary=os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary,'a') as output:output.write(f'Published private `{args.image}:{args.version}`, `sha-{revision}` and `latest`.\n')
    return 0


if __name__=='__main__':raise SystemExit(main())
