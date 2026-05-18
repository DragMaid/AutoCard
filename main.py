def parse_args():
    from argparse import ArgumentParser
    p = ArgumentParser()
    p.add_argument("--device",     type=str, default="cpu")
    p.add_argument("--checkpoint", type=str)
    p.add_argument("--mlflow",     action="store_true")
    p.add_argument("--resume",     action="store_true")
    p.add_argument("--train",      action="store_true")
    p.add_argument("--render",     action="store_true")
    p.add_argument("--client",     action="store_true")
    p.add_argument("--server",     action="store_true")
    p.add_argument("--ai",         action="store_true")
    p.add_argument("--host",       type=str, default="localhost")
    p.add_argument("--port",       type=int, default=5555)
    return p.parse_args()


if __name__ == "__main__":
    import logging
    from datetime import datetime
    from core.logger import setup_logging
    from ml.config import Config

    # NOTE: custom logger, need to be above all other modules
    timestamp = datetime.now().strftime("%Y%m%d_%H-%M-%S")
    file = Config.LOG_FOLDER / f"main_{timestamp}.log"
    setup_logging(file, logging.INFO)

    args = parse_args()
    if args.client or args.server or args.ai:
        from gui.screen.menu import run_headless_game
        run_headless_game(args)
    elif args.train:
        from ml.train import run
        run(args)
    else:
        from gui.screen.menu import GameApp
        GameApp().run()
