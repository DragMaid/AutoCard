from pathlib import Path


class Config:
    ASSET_DIR = Path('assets')
    SCREEN_SIZE = (1280, 720)
    MAX_HAND_CARDS = 10
    MAX_STATS = 9999


config = Config()
