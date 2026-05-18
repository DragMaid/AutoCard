import sys
import logging
from pathlib import Path
from typing import Optional
from logging.handlers import RotatingFileHandler


class DebugLogger(logging.Logger):
    """Debugger logger specifically for game modules."""

    def _log_with_extra(self, level, msg, extra, *args, **kwargs):
        if extra is not None:
            kwargs = dict(kwargs)  # avoid mutating caller dict
            kwargs["extra"] = kwargs.get("extra", {})
            kwargs["extra"]["_extra"] = extra
        self.log(level, msg, *args, **kwargs)

    def debugx(self, msg, extra=None, *args, **kwargs):
        self._log_with_extra(logging.DEBUG, msg, extra, *args, **kwargs)

    def warningx(self, msg, extra=None, *args, **kwargs):
        self._log_with_extra(logging.WARNING, msg, extra, *args, **kwargs)

    def errorx(self, msg, extra=None, *args, **kwargs):
        self._log_with_extra(logging.ERROR, msg, extra, *args, **kwargs)


class DictFormatter(logging.Formatter):
    """Formatter for handlng debug loggers."""

    def format(self, record):
        base = super().format(record)
        extra = getattr(record, "_extra", None)
        if extra:
            base += " | " + " ".join(
                f"{k}={v}" for k, v in extra.items()
            )

        return base


def enable_console(name: str, level=logging.INFO):
    logger = logging.getLogger(__name__)
    logger.setLevel(level)
    logger.propagate = False

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    console_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    return logger


def setup_logging(file: Optional[str] = None, level=logging.INFO, console: bool = True) -> None:
    """Configures logging for the application.

    Args:
        file: Optional path to a log file.
        debug: If True, sets log level to DEBUG.
    """
    logging.setLoggerClass(DebugLogger)

    formatter = DictFormatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    logging.shutdown()
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    # Console output
    if console:
        console = logging.StreamHandler()
        console.setLevel(level)
        console.setFormatter(formatter)
        root.addHandler(console)

    # File output
    if file is not None:
        Path(file).parent.mkdir(exist_ok=True, parents=True)
        file_handler = RotatingFileHandler(file, maxBytes=5_000_000)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    logging.captureWarnings(True)


setup_logging(file=None, level=logging.INFO)
