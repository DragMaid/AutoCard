import logging

def setup_logger(log_path: str | None = None, console=True, level=logging.DEBUG):
    logger = logging.getLogger("GameEngine")
    logger.setLevel(level)

    # Avoid adding multiple handlers (happens when reloading engine)
    if not logger.handlers:
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
        )

        if console:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)

        if log_path:
            import os
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            log_handler = logging.FileHandler(
                log_path, mode="a", encoding="utf-8")
            log_handler.setFormatter(formatter)
            logger.addHandler(log_handler)

        logger.propagate = False

    return logger
