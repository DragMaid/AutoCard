import logging
import builtins


def disable_print():
    builtins.print = lambda *a, **k: None


def setup_silent_logger(log_path: str = "logs/game_engine.log", level=logging.DEBUG):
    """Redirect all print() calls to a file-based logger instead of stdout."""
    import os
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    logger = logging.getLogger("GameEngine")
    logger.setLevel(level)

    # Avoid adding multiple handlers (happens when reloading engine)
    if not logger.handlers:
        handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.propagate = False

    # Redirect built-in print() to logger.info()
    builtins.print = lambda *a, **k: logger.info(" ".join(str(x) for x in a))

    return logger
