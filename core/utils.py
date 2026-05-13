import random
import logging
from core.cards.monster_card import MonsterType, MonsterCard
from core.factory.base_factory import BaseFactory
from typing import Optional


# TODO: fix this later
def get_logger(name="GameEngine"):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    return logger


# def setup_logger(log_path: str | None = None, console=True, level=logging.DEBUG):
    # logger = get_logger()
    # logger.setLevel(level)

    # # Avoid adding multiple handlers (happens when reloading engine)
    # if not logger.handlers:
        # formatter = logging.Formatter(
            # "%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
        # )

        # if console:
            # console_handler = logging.StreamHandler()
            # console_handler.setFormatter(formatter)
            # logger.addHandler(console_handler)

        # if log_path:
            # import os
            # os.makedirs(os.path.dirname(log_path), exist_ok=True)
            # log_handler = logging.FileHandler(
                # log_path, mode="a", encoding="utf-8")
            # log_handler.setFormatter(formatter)
            # logger.addHandler(log_handler)

        # logger.propagate = True

    # return logger


def load_by_type_and_level(
    factory: BaseFactory,
    player_id: str,
    monster_type: MonsterType,
    star: int
) -> Optional[MonsterCard]:
    """Specific loader for monsters filtering by type and level."""
    candidates = [
        name for name, info in factory.get_cards().items()
        if info.get("monster_type") == monster_type
        and info.get("star") == star
    ]

    if not candidates:
        return None

    selected_name = random.choice(candidates)
    return factory.load(player_id, name=selected_name)
