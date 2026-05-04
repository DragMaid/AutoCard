from ml.config import Config
from ml.trainer.trainer import Trainer
from ml.environment.environment import GameEnv
from core.handle_game_logic.game_engine import GameEngine
from core.player import Player
from typing import Tuple


def new_players() -> Tuple[Player, Player]:
    p1 = Player(0, "p1")
    p2 = Player(1, "p2", is_opponent=True)
    return p1, p2


if __name__ == "__main__":
    cfg = Config()
    engine = GameEngine(players=new_players(), verbose=True, log_to_file=True)
    env = GameEnv(engine=engine, render=True)
    trainer = Trainer(env, cfg)
    trainer.train()
