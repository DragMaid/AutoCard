from typing import Tuple
from ml.config import Config
from ml.trainer.trainer import Trainer
from ml.environment.environment import GameEnv
from core.logic.game_engine import GameEngine
from core.data.player import Player


def new_players() -> Tuple[Player, Player]:
    """Creates initial players.

    Returns:
        Tuple[Player, Player]: A tuple containing the two players.
    """
    p1 = Player(player_index=0, name="p1")
    p2 = Player(player_index=1, name="p2", is_opponent=True)
    return p1, p2


if __name__ == "__main__":
    cfg = Config()
    engine = GameEngine(players=new_players())
    env = GameEnv(engine=engine, render=True)
    trainer = Trainer(env, cfg)
    trainer.train()
