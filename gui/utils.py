import random
from typing import Tuple


def random_color() -> Tuple[int, int, int]:
    """Generates a random RGB color.

    Returns:
        Tuple[int, int, int]: A tuple representing the (R, G, B) color.
    """
    return (random.randint(0, 255),  # Red
            random.randint(0, 255),  # Green
            random.randint(0, 255))  # Blue
