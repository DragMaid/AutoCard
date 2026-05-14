from pathlib import Path

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


config = Config()
