import pygame
from gui.gui_info.game_area import GameAreaConfig
from gui.gui_info.hand import HandUI
from gui.gui_info.text_area import TextArea
from gui.gui_info.preview_card_table import CardPreview
from gui.gui_info.deck_area import DeckArea
from gui.cache import load_image


class TileSpriteManager:
    """Manages loading, caching, and retrieval of tile sprites"""

    def __init__(self):
        self.sprites = {}
        self.sprite_paths = {}

    def register_sprite(self, name, path):
        """Register a sprite path with a name"""
        self.sprite_paths[name] = path

    def load_sprites(self, slot_width, slot_height):
        """Load and scale all registered sprites"""
        self.sprites.clear()

        for name, path in self.sprite_paths.items():
            try:
                sprite = load_image(path)
                self.sprites[name] = pygame.transform.scale(
                    sprite, (slot_width, slot_height)
                )
            except pygame.error as e:
                print(f"Warning: Could not load sprite '{
                      name}' from {path}: {e}")
                self.sprites[name] = self._create_fallback_sprite(
                    slot_width, slot_height
                )

    def _create_fallback_sprite(self, width, height):
        """Create a colored rectangle as fallback"""
        surface = pygame.Surface((width, height))
        surface.fill((50, 50, 70))
        return surface

    def get_sprite(self, name):
        """Get a loaded sprite by name"""
        return self.sprites.get(name)


class TileRenderer:
    """Handles rendering of the game grid tiles"""

    def __init__(self, rows, cols, grid_info, sprite_manager):
        self.rows = rows
        self.cols = cols
        self.grid = grid_info
        self.sprite_manager = sprite_manager
        self.show_grid_lines = False
        self.tile_map = {}

    def set_tile_mapping(self, tile_map):
        """
        Set which sprite to use for which tiles
        tile_map format: {(row, col): 'sprite_name', ...}
        or: {'rows': {0: 'sprite1', 1: 'sprite1', 2: 'sprite2', ...}}
        """
        self.tile_map = tile_map

    def get_tile_sprite_name(self, row, col):
        """Determine which sprite to use for a given tile"""
        if 'rows' in self.tile_map:
            return self.tile_map['rows'].get(row, 'default')

        return self.tile_map.get((row, col), 'default')

    def draw_tiles(self, screen):
        """Draw all tile sprites"""
        for row in range(self.rows):
            for col in range(self.cols):
                sprite_name = self.get_tile_sprite_name(row, col)
                sprite = self.sprite_manager.get_sprite(sprite_name)

                if sprite:
                    x = self.grid['origin_x'] + col * self.grid['slot_width']
                    y = self.grid['origin_y'] + row * self.grid['slot_height']
                    screen.blit(sprite, (x, y))

    def draw_grid_lines(self, screen, color, line_width):
        """Draw grid lines over the tiles"""
        if not self.show_grid_lines:
            return

        grid = self.grid

        for col in range(self.cols + 1):
            x = grid['origin_x'] + col * grid['slot_width']
            pygame.draw.line(
                screen, color,
                (x, grid['origin_y']),
                (x, grid['origin_y'] + grid['height']),
                line_width
            )

        for row in range(self.rows + 1):
            y = grid['origin_y'] + row * grid['slot_height']
            pygame.draw.line(
                screen, color,
                (grid['origin_x'], y),
                (grid['origin_x'] + grid['width'], y),
                line_width
            )

    def toggle_grid_lines(self):
        """Toggle grid line visibility"""
        self.show_grid_lines = not self.show_grid_lines


class Matrix:
    def __init__(self, screen, game_state, rows=4, cols=5):
        self.screen = screen
        self.rows = rows
        self.cols = cols
        self.game_state = None
        self.config = GameAreaConfig()

        self.areas = {}
        self.sprite_manager = TileSpriteManager()

        self._setup_default_sprites()
        self.set_game_state(game_state)

    def reset(self, game_state):
        self.set_game_state(game_state)

    def _setup_zones(self):
        self.hands = [self.areas["my_hand_area"],
                      self.areas["opponent_hand_area"]]

        self.player_zones = {
            self.game_state.players[0].id: {
                "hand": self.areas["my_hand_area"],
                "deck": self.areas["my_deck"],
                "lp": self.areas["my_lp_area"],
            },
            self.game_state.players[1].id: {
                "hand": self.areas["opponent_hand_area"],
                "deck": self.areas["opponent_deck"],
                "lp": self.areas["opponent_lp_area"],
            },
        }

    def _setup_default_sprites(self):
        """Register default sprite paths"""
        self.sprite_manager.register_sprite(
            'opponent_tile', 'assets/tile1.png')
        self.sprite_manager.register_sprite(
            'player_tile', 'assets/tile2.png')
        self.sprite_manager.register_sprite(
            'default', 'assets/tile1.png')

    def _setup_tile_mapping(self):
        """Configure which sprites are used for which rows"""
        tile_mapping = {
            'rows': {
                0: 'opponent_tile',
                1: 'opponent_tile',
                2: 'player_tile',
                3: 'player_tile'
            }
        }
        self.tile_renderer.set_tile_mapping(tile_mapping)

    def set_game_state(self, gs, force=False):
        if gs and gs is not self.game_state or force:
            self.game_state = gs
            self.update_dimensions()
            self.tile_renderer = TileRenderer(
                self.rows, self.cols, self.grid, self.sprite_manager)
            self._setup_tile_mapping()
            self._setup_zones()

    def register_tile_sprite(self, name, path):
        """Register a new tile sprite"""
        self.sprite_manager.register_sprite(name, path)
        self.sprite_manager.load_sprites(
            self.grid['slot_width'],
            self.grid['slot_height']
        )

    def set_tile_mapping(self, tile_map):
        """Update the tile mapping"""
        self.tile_renderer.set_tile_mapping(tile_map)

    def toggle_grid_lines(self):
        """Toggle grid line visibility"""
        self.tile_renderer.toggle_grid_lines()

    def update_dimensions(self):
        """Calculate all dimensions and create game areas"""
        screen_width, screen_height = self.screen.get_size()
        margins = self._calculate_margins(screen_width, screen_height)
        grid_info = self._calculate_grid_dimensions(
            screen_width, screen_height, margins)

        self.grid = grid_info
        self._create_game_areas(screen_width, screen_height, margins)

        if hasattr(self, 'sprite_manager'):
            self.sprite_manager.load_sprites(
                self.grid['slot_width'],
                self.grid['slot_height']
            )

    def _calculate_margins(self, screen_width, screen_height):
        """Calculate margin sizes based on screen dimensions"""
        return {
            'left': int(screen_width * self.config.LEFT_RATIO),
            'right': int(screen_width * self.config.RIGHT_RATIO),
            'top': int(screen_height * self.config.TOP_RATIO),
            'bottom': int(screen_height * self.config.BOTTOM_RATIO)
        }

    def _calculate_grid_dimensions(self, screen_width, screen_height, margins):
        """Calculate grid layout information"""
        avail_width = screen_width - (margins['left'] + margins['right'])
        avail_height = screen_height - (margins['top'] + margins['bottom'])

        slot_width = avail_width // self.cols
        slot_height = avail_height // self.rows

        grid_width = self.cols * slot_width
        grid_height = self.rows * slot_height

        origin_x = margins['left'] + (avail_width - grid_width) // 2
        origin_y = margins['top'] + (avail_height - grid_height) // 2

        return {
            'origin_x': origin_x,
            'origin_y': origin_y,
            'width': grid_width,
            'height': grid_height,
            'slot_width': slot_width,
            'slot_height': slot_height
        }

    def _calculate_area_dimensions(self, margins):
        """Calculate dimensions for deck/graveyard areas"""
        deck_width = margins['left'] - (2 * self.config.AREA_PADDING)

        return {
            'deck_width': max(0, deck_width),
            'top_height': margins['top'] - (2 * self.config.AREA_PADDING),
            'bottom_height': margins['bottom'] - (2 * self.config.AREA_PADDING)
        }

    def _create_game_areas(self, screen_width, screen_height, margins):
        """Create all game areas (decks, graveyards, etc.)"""
        area_dims = self._calculate_area_dimensions(margins)
        padding = self.config.AREA_PADDING

        p1 = self.game_state.players[0]
        p2 = self.game_state.players[1]

        if p1.is_opponent:
            opponent = p1
            ally = p2
        else:
            opponent = p2
            ally = p1

        self.areas = {
            'opponent_deck': DeckArea(
                area_dims['deck_width']/1.8, padding,
                area_dims['deck_width']/2, area_dims['top_height'],
                self.config.OPPONENT_COLOR, self.config.AREA_BORDER_WIDTH
            ),
            'opponent_lp_area': TextArea(
                opponent,
                padding, padding,
                area_dims['deck_width']/2, area_dims['top_height'],
                self.config.OPPONENT_COLOR, self.config.AREA_BORDER_WIDTH
            ),
            'opponent_hand_area': HandUI(
                opponent.id,
                self.game_state.player_info[opponent.id]["held_cards"],
                self.grid['origin_x'], padding,
                self.grid['width'], margins['top'] - (2 * padding),
                self.config.OPPONENT_COLOR, self.config.AREA_BORDER_WIDTH
            ),

            'my_deck': DeckArea(
                padding*16.5, screen_height - margins['bottom'] + padding,
                area_dims['deck_width']/2, area_dims['bottom_height'],
                self.config.PLAYER_COLOR, self.config.AREA_BORDER_WIDTH
            ),
            'my_lp_area': TextArea(
                p1,
                padding, screen_height - margins['bottom'] + padding,
                area_dims['deck_width']/2, area_dims['bottom_height'],
                self.config.PLAYER_COLOR, self.config.AREA_BORDER_WIDTH
            ),
            'my_hand_area': HandUI(
                ally.id,
                self.game_state.player_info[ally.id]["held_cards"],
                self.grid['origin_x'],
                screen_height - margins['bottom'] + padding,
                self.grid['width'], area_dims['bottom_height'],
                self.config.PLAYER_COLOR, self.config.AREA_BORDER_WIDTH
            ),

            'preview_card_table': CardPreview(
                padding*4 - 25, padding*13,
                self.grid['width']/3.5 + 25,
                self.grid['height'] * 1,
                self.config.CARD_COLOR, self.config.AREA_BORDER_WIDTH
            ),
        }

    def draw(self):
        """Draw the entire game matrix"""
        self.tile_renderer.draw_tiles(self.screen)
        self.tile_renderer.draw_grid_lines(
            self.screen,
            self.config.GRID_COLOR,
            self.config.GRID_LINE_WIDTH
        )
        self._draw_areas()
        self.areas["preview_card_table"].draw(self.screen)

    def _draw_areas(self):
        """Draw all game areas except hands"""
        for area in self.areas.values():
            area.draw(self.screen)

    def _draw_hands(self):
        """Draw player hands"""
        for area_name, hand in self.hands.values():
            hand.draw(self.screen)

    def get_slot_at_pos(self, pos):
        """Get the (row, col) of the grid slot at the given position"""
        x, y = pos
        grid = self.grid

        if (grid['origin_x'] <= x < grid['origin_x'] + grid['width'] and
                grid['origin_y'] <= y < grid['origin_y'] + grid['height']):

            col = (x - grid['origin_x']) // grid['slot_width']
            row = (y - grid['origin_y']) // grid['slot_height']
            return row, col

        return None

    def get_slot_rect(self, row, col):
        """Get the pygame.Rect for a specific grid slot"""
        if not (0 <= row < self.rows and 0 <= col < self.cols):
            return None

        grid = self.grid
        x = grid['origin_x'] + col * grid['slot_width']
        y = grid['origin_y'] + row * grid['slot_height']

        return pygame.Rect(x, y, grid['slot_width'], grid['slot_height'])

    def get_area_at_pos(self, pos):
        """Determine which area was clicked"""
        slot = self.get_slot_at_pos(pos)
        if slot:
            return {"type": "field", "row": slot[0], "col": slot[1]}

        for area_name, area in self.areas.items():
            if area.contains_point(pos):
                clean_name = area_name.replace('_area', '')
                return {"type": clean_name}

        return None
