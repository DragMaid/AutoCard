from pathlib import Path
from typing import Tuple

ROOT_DIR = Path(__file__).resolve().parents[1]


class Config:
    """Game configuration parameters.

    Attributes:
        ASSET_DIR: Path to the assets directory.
        SCREEN_SIZE: Resolution of the game screen (width, height).
        MAX_HAND_CARDS: Maximum number of cards allowed in the hand.
        MAX_STATS: Maximum value a stat can have.
        COLS: Number of columns in the field matrix.
        ROWS: Number of rows in the field matrix.
    """
    ASSET_DIR: Path = ROOT_DIR / 'assets'
    SCREEN_SIZE: Tuple[int, int] = (1280, 720)
    MAX_HAND_CARDS: int = 10
    MAX_STATS: int = 9999
    COLS: int = 5
    ROWS: int = 4

    # ML Encoder Config
    MAX_EFFECTS: int = 4
    VALUE_NORM: float = 1000.0
    DURATION_NORM: float = 10.0
    MAX_ATTACK: float = 5000.0
    MAX_DEFEND: float = 5000.0
    MAX_STAR: int = 10
    MAX_LIFE_POINTS: int = 8000


config = Config()
