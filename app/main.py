"""Application entry point for the Video Download Manager.

Run with either:

    python -m app.main

or via the console flow described in the README.
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

try:
    # Normal case: run as a module, e.g. ``python -m app.main``.
    from .gui import MainWindow
    from .logger import logger
except ImportError:
    # Fallback: the file was executed directly (``python app/main.py`` or via an
    # IDE "Run" button), so there is no parent package for relative imports.
    # Add the project root to ``sys.path`` and use absolute imports instead.
    import os

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from app.gui import MainWindow
    from app.logger import logger


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
