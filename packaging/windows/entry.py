"""Portable Windows executable entry point."""

import sys
from pathlib import Path


def main():
    arguments = sys.argv[1:]
    if arguments[:1] == ["--ocr-worker"]:
        from circle_to_search.platforms.windows.ocr_worker import main as worker

        return worker(arguments[1:])
    if arguments[:1] in (["--install"], ["--uninstall"]):
        from PySide6.QtWidgets import QApplication, QMessageBox

        from circle_to_search.platforms.windows.installer import shortcuts

        _app = QApplication([])
        remove = arguments[0] == "--uninstall"
        try:
            shortcuts(
                Path(sys.executable),
                ["--resident"],
                startup="--startup" in arguments,
                remove=remove,
            )
        except Exception as error:
            QMessageBox.critical(None, "Circle to Search", str(error))
            return 1
        QMessageBox.information(
            None,
            "Circle to Search",
            "Shortcuts removed." if remove else "Circle to Search was added to the Start menu.",
        )
        return 0
    from circle_to_search.app import main as desktop

    return desktop(["--resident", *arguments])


if __name__ == "__main__":
    raise SystemExit(main())
