from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]


class Config:
    ASSET_DIR = ROOT_DIR / 'assets'
    SCREEN_SIZE = (1280, 720)
    MAX_HAND_CARDS = 10
    MAX_STATS = 9999
    COLS = 5
    ROWS = 4


config = Config()
