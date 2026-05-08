import pygame
from gui.cache import get_font
from gui.ui_components import Button


# TODO: move these to config
SCREEN_SIZE = (1280, 720)


class GameHUD:
    """Draws the turn info panel, end-turn and surrender buttons."""

    def __init__(self, game_engine, on_end_turn, on_surrender):
        self.game_engine = game_engine

        self.end_turn_button = Button(
            pygame.Rect(15, SCREEN_SIZE[1] - 60, 150, 50),
            "End Turn",
            font_size=28,
            color=(50, 100, 50),
            hover_color=(70, 130, 70),
            callback=on_end_turn,
        )
        self.surrender_button = Button(
            pygame.Rect(15, SCREEN_SIZE[1] - 110, 150, 40),
            "Surrender",
            font_size=20,
            color=(80, 30, 30),
            hover_color=(120, 40, 40),
            callback=on_surrender,
        )

    def set_local_turn(self, is_local_turn: bool):
        self.end_turn_button.enabled = is_local_turn

    def handle_event(self, event):
        self.end_turn_button.handle_event(event)
        self.surrender_button.handle_event(event)

    def draw(self, screen):
        self._draw_panel(screen)
        self.end_turn_button.draw(screen)
        self.surrender_button.draw(screen)

    def _draw_panel(self, screen):
        font = get_font(24)
        turn_count = self.game_engine.turn_manager.turn_count
        is_local_turn = self.game_engine.is_local_turn()
        is_trap_stage = self.game_engine.turn_manager.is_trap_stage()

        if is_trap_stage:
            player_label = "Your Trap" if is_local_turn else "Enemy Trap"
            label_color = (255, 200, 0)  # Golden/Yellow for traps
        else:
            player_label = "Your Turn" if is_local_turn else "Opponent Turn"
            label_color = (100, 255, 100) if is_local_turn else (255, 100, 100)

        panel_rect = pygame.Rect(10, SCREEN_SIZE[1] - 235, 160, 235)
        panel_surf = pygame.Surface(
            (panel_rect.width, panel_rect.height), pygame.SRCALPHA)
        panel_surf.set_alpha(175)
        pygame.draw.rect(panel_surf, (20, 20, 30, 200),
                         panel_surf.get_rect(), border_radius=10)
        pygame.draw.rect(panel_surf, (100, 100, 150),
                         panel_surf.get_rect(), 2, border_radius=10)
        screen.blit(panel_surf, panel_rect)

        turn_surf = font.render(f"Turn: {turn_count}", True, (220, 220, 255))
        screen.blit(turn_surf, turn_surf.get_rect(
            center=(panel_rect.centerx, panel_rect.top + 35)))

        player_surf = font.render(player_label, True, label_color)
        screen.blit(player_surf, player_surf.get_rect(
            center=(panel_rect.centerx, panel_rect.top + 75)))


class TrapStageOverlay:
    """Overlay shown when waiting for the opponent to resolve traps."""

    def __init__(self, screen_size):
        self.screen_size = screen_size
        self.visible = False

    def show(self):
        self.visible = True

    def hide(self):
        self.visible = False

    def draw(self, screen):
        if not self.visible:
            return
        overlay = pygame.Surface(self.screen_size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 120))
        screen.blit(overlay, (0, 0))

        font = get_font(48)
        text_surf = font.render(
            "Opponent Resolving Traps...", True, (255, 255, 255))
        screen.blit(text_surf, text_surf.get_rect(
            center=(self.screen_size[0] // 2, self.screen_size[1] // 2)))


class SurrenderOverlay:
    """Confirmation dialog shown when the player tries to surrender."""

    def __init__(self, screen_size, on_confirm, on_cancel):
        self.screen_size = screen_size
        self.visible = False

        self.yes_button = Button(
            pygame.Rect(530, 380, 100, 40), "Yes",
            color=(120, 30, 30), callback=on_confirm,
        )
        self.no_button = Button(
            pygame.Rect(650, 380, 100, 40), "No",
            color=(30, 100, 30), callback=on_cancel,
        )

    def show(self):
        self.visible = True

    def hide(self):
        self.visible = False

    def handle_event(self, event):
        if self.visible:
            self.yes_button.handle_event(event)
            self.no_button.handle_event(event)

    def draw(self, screen):
        if not self.visible:
            return
        overlay = pygame.Surface(self.screen_size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 200))
        screen.blit(overlay, (0, 0))

        font = get_font(36)
        text_surf = font.render("Surrender?", True, (255, 255, 255))
        screen.blit(text_surf, text_surf.get_rect(
            center=(self.screen_size[0] // 2, 340)))

        self.yes_button.draw(screen)
        self.no_button.draw(screen)


class GameOverOverlay:
    """Victory / Defeat screen with a continue button."""

    def __init__(self, screen_size, on_continue):
        self.screen_size = screen_size
        self.visible = False
        self.winner_text = ""

        self.continue_button = Button(
            pygame.Rect(540, 400, 200, 50),
            "Continue",
            callback=on_continue,
        )

    def show(self, winner_text: str):
        self.winner_text = winner_text
        self.visible = True

    def handle_event(self, event):
        if self.visible:
            self.continue_button.handle_event(event)

    def draw(self, screen):
        if not self.visible:
            return
        overlay = pygame.Surface(self.screen_size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        screen.blit(overlay, (0, 0))

        font = get_font(72)
        color = (50, 250, 50) if self.winner_text == "VICTORY" else (250, 50, 50)
        text_surf = font.render(self.winner_text, True, color)
        screen.blit(text_surf, text_surf.get_rect(
            center=(self.screen_size[0] // 2, 300)))

        self.continue_button.draw(screen)
