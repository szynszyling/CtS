"""Windows process entry point for the shared OCR server."""

import gc
import os
import sys


def main(argv=None):
    if sys.stdout is None:
        sys.stdout = open(
            os.environ.get("CTS_OCR_WORKER_LOG", os.devnull), "a", encoding="utf-8", buffering=1
        )
    if sys.stderr is None:
        sys.stderr = sys.stdout
    from cts_ocr_server.__main__ import main as server_main

    try:
        return server_main(argv)
    finally:
        # Release nets before the Vulkan loader is torn down by Python.
        import ncnn

        gc.collect()
        ncnn.destroy_gpu_instance()


if __name__ == "__main__":
    raise SystemExit(main())
