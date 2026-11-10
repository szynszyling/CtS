"""Run the standalone Compose deployment from an otherwise empty directory.

Uses synthetic text and a private test token. CPU mode allows CI without a
render device; Vulkan mode exercises the production device/group settings.
"""

import argparse
import json
import secrets
import subprocess
import tempfile
import time
from pathlib import Path


def run(arguments, **kwargs):
    try:
        return subprocess.run(
            arguments, capture_output=True, text=True, check=True, timeout=120, **kwargs
        ).stdout.strip()
    except subprocess.CalledProcessError as error:
        raise RuntimeError(error.stderr.strip() or error.stdout.strip() or str(error)) from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="ghcr.io/szynszyling/cts-ocr:latest")
    parser.add_argument("--device", choices=("vulkan", "cpu"), default="vulkan")
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[2] / "compose.yaml"
    project = "cts-compose-smoke-" + secrets.token_hex(4)
    network = project + "-net"
    container = project + "-ocr"
    command = ["docker", "compose", "--project-name", project]
    created_network = False
    with tempfile.TemporaryDirectory(prefix=project) as directory:
        root = Path(directory)
        manifest = root / "compose.yaml"
        manifest.write_text(source.read_text())
        manifest.chmod(0o600)
        command += ["--file", str(manifest)]
        definition = json.loads(run([*command, "config", "--format", "json"], cwd=root))
        service = definition["services"]["ocr"]
        assert not service.get("build") and not service.get("env_file")
        assert (
            not service.get("volumes")
            and not definition.get("configs")
            and not definition.get("secrets")
        )
        assert not service.get("ports"), "The SWAG deployment must use its shared network."
        service["image"] = args.image
        service["container_name"] = container
        service["restart"] = "no"
        service["environment"]["CTS_OCR_SERVER_TOKEN"] = secrets.token_urlsafe(32)
        assert definition["networks"]["server"]["external"]
        assert set(service["networks"]) == {"server"}
        definition["networks"]["server"]["name"] = network
        if args.device == "cpu":
            service.pop("devices", None)
            service.pop("group_add", None)
            service["command"] = ["--host", "0.0.0.0", "--device", "cpu"]
            # Private-repository CI runners can have fewer CPUs than the NAS.
            service["cpus"] = 1
        else:
            nodes = sorted(Path("/dev/dri").glob("renderD*"))
            if not nodes:
                raise RuntimeError("No GPU render device is available.")
            service["group_add"] = [str(nodes[0].stat().st_gid)]
        # JSON is valid Compose/YAML too. The configured copy is the only file
        # beside the deployment; there is no .env, override or source folder.
        manifest.write_text(json.dumps(definition))
        assert [path.name for path in root.iterdir()] == ["compose.yaml"]
        try:
            run(["docker", "network", "create", network])
            created_network = True
            run([*command, "up", "-d", "--no-build", "--pull", "never"], cwd=root)
            deadline = time.monotonic() + 65
            while True:
                info = json.loads(run(["docker", "inspect", container]))[0]
                assert not any(mount["Type"] == "bind" for mount in info["Mounts"])
                health = info["State"].get("Health", {}).get("Status")
                if health == "healthy":
                    break
                if info["State"]["Status"] in ("exited", "dead") or time.monotonic() > deadline:
                    raise RuntimeError(
                        "Standalone container did not become healthy: "
                        + run(["docker", "logs", container])
                    )
                time.sleep(1)
            check = """
import io,json,os,urllib.request
from PIL import Image,ImageDraw,ImageFont
headers={'Authorization':'Bearer '+os.environ['CTS_OCR_SERVER_TOKEN']}
with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8766/v1/health',headers=headers)) as response:
    health=json.load(response)
print('Standalone backend:',health['device'],'accelerated:',health['accelerated'])
assert health['accelerated']==EXPECTED_GPU
image=Image.new('RGB',(640,120),'white')
ImageDraw.Draw(image).text((24,32),'Circle these words',font=ImageFont.load_default(size=32),fill='black')
buffer=io.BytesIO();image.save(buffer,format='PNG')
headers['Content-Type']='image/png'
request=urllib.request.Request('http://127.0.0.1:8766/v1/ocr?priority=interactive',data=buffer.getvalue(),headers=headers)
with urllib.request.urlopen(request,timeout=30) as response:result=json.load(response)
assert ''.join(g['text'] for g in result['glyphs']).replace(' ','')=='Circlethesewords'
print('Standalone authenticated OCR passed.')
""".replace("EXPECTED_GPU", str(args.device == "vulkan"))
            print(run(["docker", "exec", container, "python", "-c", check]), flush=True)
            print(
                "Only compose.yaml was present; no repository, environment file, bind mounts or build were needed.",
                flush=True,
            )
        finally:
            subprocess.run(
                [*command, "down", "--remove-orphans"], cwd=root, capture_output=True, timeout=60
            )
            if created_network:
                subprocess.run(
                    ["docker", "network", "rm", network], capture_output=True, timeout=30
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
