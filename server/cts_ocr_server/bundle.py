"""Build the selected ncnn model bundle from pinned upstream assets."""

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import zipfile
from pathlib import Path

from .engine import fetch_models, verified_download
from .gpu_models import LANGUAGES, recognizer_groups

UPSTREAM = "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0"
PNNX_URL = (
    "https://files.pythonhosted.org/packages/5c/b7/9665ea73f6503fea4f30abbd3eebcea1c8500095496167761a15482354bc/"
    "pnnx-20261020-py3-none-manylinux2014_x86_64.manylinux_2_17_x86_64.whl"
)
PNNX_SHA256 = "d50d921e5897293d616444191c1a2dc5366423c81bdb4bd22a985fe8071cf17c"
WINDOWS_PNNX_URL = (
    "https://files.pythonhosted.org/packages/e8/51/1b30523f85f9482f55f3f4f11ad8f4a37db7c8773d66625cceb2973c5c60/"
    "pnnx-20261020-py3-none-win_amd64.whl"
)
WINDOWS_PNNX_SHA256 = "cde5381cdebbef5d3e0e796e824ed02e2e1dfd075731921a3b3653514c518309"
ASSETS = {
    "latin": (
        "6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884",
        "b5f2bfe2bdd9448429e3e82b51c789775d9b42f2403d082b00662eb77e401c5d",
    ),
    "cyrillic": (
        "90f761b4bfcce0c8c561c0cb5c887b0971d3ec01c32164bdf7374a35b0982711",
        "db40aa52ceb112055be80c694afdf655d5d2c4f7873704524cc16a447ca913ba",
    ),
    "korean": (
        "cd6e2ea50f6943ca7271eb8c56a877a5a90720b7047fe9c41a2e541a25773c9b",
        "a88071c68c01707489baa79ebe0405b7beb5cca229f4fc94cc3ef992328802d7",
    ),
    "el": (
        "b4368bccd557123c702b7549fee6cd1e94b581337d1c9b65310f109131542b7f",
        "31defc62c0c3ad3674a82da6192226a2ba98ef4ff014a7045cb88d59f9c3de31",
    ),
}


def convert_recognizers(directory, groups):
    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        wheel = work / "pnnx.whl"
        url, digest = PNNX_URL, PNNX_SHA256
        executable = "pnnx"
        options = {}
        if os.name == "nt":
            url, digest = WINDOWS_PNNX_URL, WINDOWS_PNNX_SHA256
            executable += ".exe"
            options["creationflags"] = subprocess.CREATE_NO_WINDOW
        verified_download(wheel, url, digest)
        converter = work / executable
        with zipfile.ZipFile(wheel) as archive:
            converter.write_bytes(archive.read("pnnx/" + executable))
        converter.chmod(0o700)
        for group in groups:
            version = "PP-OCRv5"
            name = group + "_PP-OCRv5_rec_mobile"
            dict_name = f"ppocrv5_{group}_dict.txt"
            if group == "latin":
                version = "PP-OCRv6"
                name = "PP-OCRv6_rec_small"
                dict_name = "ppocrv6_dict.txt"
            model_hash, dict_hash = ASSETS[group]
            source = work / f"{group}.onnx"
            verified_download(source, f"{UPSTREAM}/onnx/{version}/rec/{name}.onnx", model_hash)
            verified_download(
                directory / f"{group}.txt",
                f"{UPSTREAM}/paddle/{version}/rec/{name}/{dict_name}",
                dict_hash,
            )
            subprocess.run(
                [
                    str(converter),
                    source.name,
                    "inputshape=[1,3,48,160]",
                    "inputshape2=[1,3,48,256]",
                    "fp16=0",
                    f"ncnnparam={directory / group}.ncnn.param",
                    f"ncnnbin={directory / group}.ncnn.bin",
                ],
                cwd=work,
                check=True,
                timeout=120,
                **options,
            )


def prepare_models(directory, codes, profile="local"):
    codes = tuple(dict.fromkeys(codes))
    if (
        profile not in ("local", "server")
        or not codes
        or any(code not in LANGUAGES for code in codes)
    ):
        raise ValueError("Choose supported CtS OCR languages and a local or server profile.")
    directory = Path(directory).resolve()
    groups = recognizer_groups(codes)
    fetch_models(directory, detector_only="base" not in groups)
    extra = [group for group in groups if group != "base"]
    if extra:
        convert_recognizers(directory, extra)
    (directory / "bundle.json").write_text(
        json.dumps(
            {
                "profile": profile,
                "languages": codes,
                "recognizers": groups,
                "files": {
                    path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in directory.iterdir()
                    if path.is_file() and path.name != "bundle.json"
                },
            }
        )
        + "\n"
    )
    return directory


def ready_bundle(directory, codes):
    try:
        manifest = json.loads((directory / "bundle.json").read_text())
        return (
            manifest["profile"] == "local"
            and set(manifest["languages"]) == set(codes)
            and bool(manifest["files"])
            and all(
                Path(name).name == name
                and hashlib.sha256((directory / name).read_bytes()).hexdigest() == digest
                for name, digest in manifest["files"].items()
            )
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--profile", choices=("local", "server"), required=True)
    parser.add_argument("--languages", default="")
    args = parser.parse_args()
    if args.profile == "server":
        if args.languages:
            parser.error("The server profile includes every language.")
        codes = tuple(LANGUAGES)
    else:
        codes = tuple(dict.fromkeys(args.languages.split("+")))
        if any(code not in LANGUAGES for code in codes):
            parser.error("The local profile requires supported language codes separated by '+'.")
    prepare_models(args.directory, codes, args.profile)


if __name__ == "__main__":
    main()
