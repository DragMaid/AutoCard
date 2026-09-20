"""Entry point: ``python -m engine``.

``core`` modules call ``logger.debugx`` / ``warningx`` / ``errorx``, which exist
only on :class:`core.logger.DebugLogger`. Loggers are created at import time, so
the class has to be registered before anything under ``core`` is imported — the
same ordering ``main.py`` and ``conftest.py`` observe.
"""

import logging

from core.logger import DebugLogger, setup_logging

logging.setLoggerClass(DebugLogger)

if __name__ == "__main__":
    from datetime import datetime

    from ml.config import Config

    timestamp = datetime.now().strftime("%Y%m%d_%H-%M-%S")
    Config.LOG_FOLDER.mkdir(parents=True, exist_ok=True)
    setup_logging(Config.LOG_FOLDER / f"engine_{timestamp}.log", logging.INFO)

    from engine.service import main

    main()
