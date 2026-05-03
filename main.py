import pygame
# from threading import Thread
from ml.environment.environment import GameEnv
# from ml.ai_opponent import AIOpponent, HumanVsAIManager
from ml.config import Config
from core.player import Player
from core.handle_game_logic.game_engine import GameEngine
from core.handle_logic_gui.input_manager import InputManager
from gui.gui_info.matrix_field import Matrix
from core.handle_logic_gui.render_engine import RenderEngine
from gui.effects.manager import EffectManager
from gui.cache import load_image

config = Config()

pygame.init()
screen_size = (1280, 720)
screen = pygame.display.set_mode(screen_size)
clock = pygame.time.Clock()
running = True
dt = 0

# Players creation
player1 = Player(0, 'Binh')
player2 = Player(1, 'AI', is_opponent=True)

game_engine = GameEngine([player1, player2], verbose=True, log_to_file=False)
env = GameEnv(engine=game_engine, render=False)
game_engine.start_game()

# ai = AIOpponent(env, config, config.CHECKPOINT_PATH,
                # agent_id=1, device=config.DEVICE)
# ai_manager = HumanVsAIManager(game_engine, env, ai, human_player_idx=0)

# GUI handler - separated from logic
field_matrix = Matrix(screen, game_engine.game_state)
render_engine = RenderEngine(field_matrix, screen, game_engine.game_state)

input_manager = InputManager(field_matrix, game_engine, render_engine)

image_path = "assets/background.png"
background = load_image(image_path)
background = pygame.transform.scale(background, screen_size)

ai_state = {"running": False}
ai_thread = None

while running:
    print(game_engine.serialize())
    current_player = game_engine.turn_manager.get_current_player()
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        input_manager.handle_event(event)

        # TODO: change this with a real turn end button
        if (event.type == pygame.KEYDOWN
                and event.key == pygame.K_SPACE
                and current_player == player1):
            game_engine.end_turn()

    # if current_player == player2 and not ai_state["running"]:
        # ai_state["running"] = True
        # ai_thread = Thread(
            # target=ai_manager.execute_ai_turn,
            # kwargs={"on_complete": lambda: ai_state.update({"running": False}),
                    # "callback": lambda: render_engine.align_cards(field_matrix)}
        # )
        # ai_thread.start()

    screen.blit(background, background.get_rect())

    field_matrix.areas["preview_card_table"].draw(screen)
    field_matrix.draw()

    input_manager.draw(screen)

    render_engine.update(game_engine.game_state,
                         field_matrix,
                         game_engine.event_logger)
    render_engine.animation_mgr.update(dt)
    render_engine.draw()

    EffectManager.update()
    EffectManager.draw(screen)

    pygame.display.flip()

    # Delta time for rate limit
    dt = clock.tick(60) / 1000

    if game_engine.game_state.is_game_over():
        pygame.time.wait(1000)  # pause to show message
        running = False

pygame.quit()
