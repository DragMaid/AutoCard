"""Pytest bootstrap.

``core`` modules call ``logger.debugx``/``warningx``/``errorx``, which only exist
on :class:`core.logger.DebugLogger`. That class has to be registered before any
module creates its logger at import time — the same ordering ``main.py``
observes — so it is installed here, before pytest imports the test modules.
"""

import logging

from core.logger import DebugLogger

logging.setLoggerClass(DebugLogger)
