import argparse
import os
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Persistent Vulkan OCR service for Circle to Search"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument(
        "--device",
        choices=("vulkan", "cpu"),
        default="vulkan",
        help="CPU is an explicit development/reference mode",
    )
    parser.add_argument("--gpu-index", type=int, default=0)
    parser.add_argument("--gpu-name", help="Select a unique GPU by a substring of its name")
    parser.add_argument(
        "--detector-scale",
        type=float,
        default=os.environ.get("CTS_OCR_DETECTOR_SCALE", "2"),
        help="Small-image detector enlargement, 1–2; lower is faster but may miss small text (default: 2)",
    )
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=Path(
            os.environ.get("CTS_OCR_MODELS", Path.home() / ".cache/circle-to-search/ocr-models")
        ),
    )
    parser.add_argument("--download-models", action="store_true")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Recognize bundled-font fixtures on the selected device, then exit",
    )
    parser.add_argument("--token-file", type=Path)
    args = parser.parse_args(argv)
    if not 1 <= args.detector_scale <= 2:
        parser.error("--detector-scale must be between 1 and 2.")
    from .engine import NcnnEngine, fetch_models

    if args.list_devices:
        import ncnn

        for index in range(ncnn.get_gpu_count()):
            print(index, ncnn.get_gpu_info(index).device_name())
        return 0
    if args.download_models:
        fetch_models(args.model_dir)
        print("Verified models:", args.model_dir)
        return 0
    token = os.environ.get("CTS_OCR_SERVER_TOKEN", "")
    if args.token_file:
        token = args.token_file.read_text().strip()
    if not args.self_test and args.host not in ("127.0.0.1", "::1", "localhost") and not token:
        parser.error(
            "A token file or CTS_OCR_SERVER_TOKEN is required when listening beyond localhost."
        )
    if args.gpu_name:
        import ncnn

        matches = [
            index
            for index in range(ncnn.get_gpu_count())
            if args.gpu_name.lower() in ncnn.get_gpu_info(index).device_name().lower()
        ]
        if len(matches) != 1:
            parser.error("GPU name must match exactly one device; use --list-devices.")
        args.gpu_index = matches[0]
    engine = NcnnEngine(args.model_dir, args.device, args.gpu_index, args.detector_scale)
    try:
        engine.self_test()
    except RuntimeError as error:
        parser.exit(
            1,
            f"OCR startup test failed on {engine.device_name}: {error}\n"
            "No requests will be accepted. Check the Vulkan driver, or compare using --device cpu --self-test.\n",
        )
    print(
        f"OCR self-test passed: {engine.device_name}; backend={args.device}; precision={engine.precision}; GPU index={args.gpu_index}; detector scale={engine.detector_scale}",
        flush=True,
    )
    if args.self_test:
        return 0
    import uvicorn

    from .service import create_app

    uvicorn.run(
        create_app(engine, token),
        host=args.host,
        port=args.port,
        access_log=False,
        timeout_keep_alive=10,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
