import threading
import pygame
from enum import Enum, auto
from gui.cache import get_font
from core.network.discovery import DiscoveryClient
from core.config import config
from .components import Button, InputBox, ScrollList


class ScreenState(Enum):
    MENU = auto()
    HOST = auto()
    JOIN = auto()
    WAITING = auto()
    AI = auto()
    START_GAME = auto()
    EXIT = auto()


class MatchmakingScreen:
    def __init__(self, screen):
        self.screen = screen
        self.state = ScreenState.MENU
        self.font_large = get_font(64)
        self.font_medium = get_font(40)
        self.font_small = get_font(24)
        self.result = None

        self.discovery_client = DiscoveryClient()
        self.is_scanning = False
        self.scan_timer = 0
        self.error_msg = ""
        self.error_timer = 0.0

        self._init_menu()
        self._init_host()
        self._init_join()
        self._init_waiting()

    def _init_menu(self):
        center_x = self.screen.get_width() // 2
        self.menu_buttons = []

        btn_width = 300
        btn_height = 60
        start_y = 250
        spacing = 80

        host_btn = Button((center_x - btn_width // 2, start_y,
                          btn_width, btn_height), "Host Game")
        host_btn.callback = lambda: self.set_state(ScreenState.HOST)
        self.menu_buttons.append(host_btn)

        join_btn = Button((center_x - btn_width // 2, start_y +
                          spacing, btn_width, btn_height), "Join Game")
        join_btn.callback = lambda: self.set_state(ScreenState.JOIN)
        self.menu_buttons.append(join_btn)

        ai_btn = Button((center_x - btn_width // 2, start_y +
                        spacing * 2, btn_width, btn_height), "Play vs AI")
        ai_btn.callback = lambda: self.set_state(ScreenState.AI)
        self.menu_buttons.append(ai_btn)

        quit_btn = Button((center_x - btn_width // 2, start_y +
                          spacing * 3, btn_width, btn_height), "Quit Game",
                          color=(100, 50, 50), hover_color=(130, 70, 70))
        quit_btn.callback = lambda: self.set_state(ScreenState.EXIT)
        self.menu_buttons.append(quit_btn)

    def _init_host(self):
        center_x = self.screen.get_width() // 2
        self.host_components = []

        self.room_name_input = InputBox(
            (center_x - 150, 220, 300, 50), text="My Room", placeholder="Room Name")
        self.host_components.append(self.room_name_input)

        self.port_input = InputBox(
            (center_x - 100, 320, 200, 50), text=f"{config.DEFAULT_PORT}", placeholder="Port", numeric=True)
        self.host_components.append(self.port_input)

        self.password_input = InputBox(
            (center_x - 150, 420, 300, 50), placeholder="Password (Optional)")
        self.host_components.append(self.password_input)

        start_btn = Button((center_x - 150, 550, 300, 60), "Start Hosting",
                           color=(50, 150, 50), hover_color=(70, 180, 70))
        start_btn.callback = self._on_start_hosting
        self.host_components.append(start_btn)

        back_btn = Button((50, 50, 100, 40), "Back", font_size=24)
        back_btn.callback = lambda: self.set_state(ScreenState.MENU)
        self.host_components.append(back_btn)

    def _init_join(self):
        center_x = self.screen.get_width() // 2
        self.join_components = []

        self.room_list = ScrollList((center_x - 300, 200, 600, 300), [])
        self.join_components.append(self.room_list)

        self.join_password_input = InputBox(
            (center_x - 150, 520, 300, 40), placeholder="Room Password")
        self.join_components.append(self.join_password_input)

        join_btn = Button((center_x - 210, 600, 200, 50), "Join",
                          color=(50, 100, 200), hover_color=(70, 120, 230))
        join_btn.callback = self._on_join_game
        self.join_components.append(join_btn)

        refresh_btn = Button((center_x + 10, 600, 200, 50), "Refresh",
                             color=(100, 100, 100), hover_color=(130, 130, 130))
        refresh_btn.callback = self._start_scan
        self.join_components.append(refresh_btn)

        back_btn = Button((50, 50, 100, 40), "Back", font_size=24)
        back_btn.callback = lambda: self.set_state(ScreenState.MENU)
        self.join_components.append(back_btn)

        self.error_msg = ""
        self.error_timer = 0

    def _init_waiting(self):
        center_x = self.screen.get_width() // 2
        self.waiting_components = []

        cancel_btn = Button((center_x - 100, 500, 200, 50), "Cancel",
                            color=(150, 50, 50), hover_color=(180, 70, 70))
        cancel_btn.callback = self._on_cancel_waiting
        self.waiting_components.append(cancel_btn)

        self.waiting_msg = "Waiting for players..."

    def set_state(self, state):
        self.state = state
        if state == ScreenState.JOIN:
            self._start_scan()
        if state == ScreenState.AI:
            self.result = ("AI",)
            self.state = ScreenState.START_GAME

    def _start_scan(self):
        if not self.is_scanning:
            self.is_scanning = True
            self.discovery_client.clear()
            threading.Thread(target=self._scan_thread, daemon=True).start()

    def _scan_thread(self):
        self.discovery_client.scan(timeout=1.5)
        self.is_scanning = False
        self.room_list.items = self.discovery_client.get_servers()

    def _on_start_hosting(self):
        port_text = self.port_input.text
        if not port_text or not (1024 <= int(port_text) <= 65535):
            self.show_error("Invalid Port (1024-65535)")
            return

        self.result = ("SERVER", int(port_text),
                       self.password_input.text, self.room_name_input.text)
        self.set_state(ScreenState.WAITING)
        self.waiting_msg = f"Hosting on port {port_text}..."

    def _on_join_game(self):
        if self.room_list.selected_index == -1:
            self.show_error("Select a room first")
            return

        room = self.room_list.items[self.room_list.selected_index]
        self.result = ("CLIENT", room['host'],
                       room['port'], self.join_password_input.text)
        self.set_state(ScreenState.WAITING)
        self.waiting_msg = f"Connecting to {room['name']}..."

    def _on_cancel_waiting(self):
        self.result = None
        self.set_state(ScreenState.MENU)

    def show_error(self, msg):
        self.error_msg = msg
        self.error_timer = 3.0

    def handle_event(self, event):
        if event.type == pygame.QUIT:
            self.state = ScreenState.EXIT
            return True

        state_to_component = {
            ScreenState.MENU: self.menu_buttons,
            ScreenState.HOST: self.host_components,
            ScreenState.JOIN: self.join_components,
            ScreenState.WAITING: self.waiting_components,
        }
        comps = state_to_component.get(self.state)
        if not comps:
            return False

        for comp in comps:
            if comp.handle_event(event):
                return True

        return False

    def update(self, dt):
        components = []
        if self.state == ScreenState.MENU:
            components = self.menu_buttons
        elif self.state == ScreenState.HOST:
            components = self.host_components
        elif self.state == ScreenState.JOIN:
            components = self.join_components
        elif self.state == ScreenState.WAITING:
            components = self.waiting_components

        for comp in components:
            comp.update(dt)

        if self.error_timer > 0:
            self.error_timer -= dt

    def draw(self, screen):
        screen.fill((20, 20, 25))

        title_text = "AutoCard Matchmaking"
        if self.state == ScreenState.HOST:
            title_text = "Host Game"
        elif self.state == ScreenState.JOIN:
            title_text = "Join Game"
        elif self.state == ScreenState.WAITING:
            title_text = "Waiting"

        title_surf = self.font_large.render(title_text, True, (200, 200, 255))
        title_rect = title_surf.get_rect(center=(screen.get_width() // 2, 100))
        screen.blit(title_surf, title_rect)

        components = []
        if self.state == ScreenState.MENU:
            components = self.menu_buttons
        elif self.state == ScreenState.HOST:
            components = self.host_components

            labels = [
                ("Room Name:", self.room_name_input),
                ("Port Number:", self.port_input),
                ("Room Password:", self.password_input)
            ]
            for label, comp in labels:
                surf = self.font_small.render(label, True, (180, 180, 180))
                screen.blit(surf, (comp.rect.left, comp.rect.top - 30))

        elif self.state == ScreenState.JOIN:
            components = self.join_components

            list_label_text = "Available Rooms:" + \
                (" (Scanning...)" if self.is_scanning else "")
            list_label = self.font_small.render(
                list_label_text, True, (180, 180, 180))
            screen.blit(list_label, (self.room_list.rect.left,
                        self.room_list.rect.top - 30))

        elif self.state == ScreenState.WAITING:
            components = self.waiting_components
            msg_surf = self.font_medium.render(
                self.waiting_msg, True, (255, 255, 255))
            msg_rect = msg_surf.get_rect(center=(screen.get_width() // 2, 300))
            screen.blit(msg_surf, msg_rect)

        for comp in components:
            comp.draw(screen)

        if self.error_timer > 0:
            err_surf = self.font_small.render(
                self.error_msg, True, (255, 80, 80))
            err_rect = err_surf.get_rect(
                center=(screen.get_width() // 2, screen.get_height() - 50))
            screen.blit(err_surf, err_rect)

        pygame.display.flip()
