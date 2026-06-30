"""Application entry point for the Video Download Manager.

Run with either:

    python -m app.main

or via the console flow described in the README.
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .gui import MainWindow
from .logger import logger


def main() -> int:
    """Create the Qt application, show the main window and run the event loop."""
    logger.info("Starting Video Download Manager.")
    app = QApplication(sys.argv)
    app.setApplicationName("Video Download Manager")

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
