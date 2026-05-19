from typing import Tuple
from ml.trainer.trainer import Trainer
from ml.environment.environment import GameEnv
from core.logic.game_engine import GameEngine
from core.data.player import Player
from ml.config import Config


def new_players() -> Tuple[Player, Player]:
    """Creates initial players.

    Returns:
        Tuple[Player, Player]: A tuple containing the two players.
    """
    p1 = Player(player_index=0, name="p1")
    p2 = Player(player_index=1, name="p2", is_opponent=True)
    return p1, p2


def run(args):
    engine = GameEngine(players=new_players())
    env = GameEnv(engine=engine, render=args.render)
    trainer = Trainer(env, args.device, args.mlflow)
    if args.checkpoint:
        trainer.load_checkpoint(args.checkpoint)
    elif args.resume:
        trainer.load_checkpoint(Config.CHECKPOINT_PATH)
    trainer.train()
