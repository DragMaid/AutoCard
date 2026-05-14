import pygame
import logging
from typing import Dict, List, Optional, Callable, Any, Set
from collections import defaultdict
from gui.cards.monster_card import MonsterCardGUI
from gui.cards.spell_card import SpellCardGUI
from gui.cards.trap_card import TrapCardGUI
from gui.cards.stat_overlay import CardStatOverlay
from gui.animations.manager import AnimationManager
from gui.animations.toggle import ToggleRotateAnimation
from gui.utils import random_color
from gui.screen.arrow import DragArrow
from gui.sprites.sprite_manager import SpriteManager
from core.gui.event_handler import EventHandler
from core.cards.card import CardType, Card
from core.cards.monster_card import CardMode
from gui.background.matrix_field import Matrix
from core.data.game_state import GameState
from core.data.events import EventLogger
from core.logic.turn_manager import TurnManager
from gui.sprites.sprite import Sprite

logger = logging.getLogger(__name__)


class RenderEngine:
    """Engine responsible for rendering game components and handling GUI logic."""

    def __init__(
        self,
        *,
        matrix: Matrix,
        screen: pygame.Surface,
        game_state: GameState,
        event_logger: EventLogger,
        turn_manager: TurnManager,
        train_mode: bool = False,
    ):
        """Initializes the RenderEngine.

        Args:
            matrix: The game board matrix field.
            screen: The pygame surface to render to.
            game_state: The current state of the game.
            event_logger: Logger for game events.
            turn_manager: Manager for game turns.
            train_mode: Boolean flag for training mode.
        """
        self.screen = screen
        self.matrix = matrix
        self.sprite_manager = SpriteManager()
        self.exisiting_colors: Dict[str, Dict[str, Any]] = defaultdict(dict)
        self.pending_merges: List[Any] = []
        self.game_state = game_state
        self.turn_manager = turn_manager
        self.event_logger = event_logger
        self.animation_mgr = AnimationManager(
            train_mode=train_mode, game_state=game_state)
        self.sprite_lookup: Dict[str, Sprite] = {}
        self.event_handler = EventHandler(
            self.sprite_manager,
            self.animation_mgr,
            self.matrix,
            self.game_state,
            self.event_logger
        )

        self.last_triggered_count = 0
        self.attack_indicators: List[DragArrow] = []

    def reset(self) -> None:
        """Resets the rendering engine state."""
        for value in self.sprite_manager.sprites.values():
            value.clear()
        self.exisiting_colors = defaultdict(dict)
        self.pending_merges.clear()

    def update(self) -> None:
        """Updates the game state for rendering."""
        self.event_handler.handle_events()
        self.register_cards()
        self.handle_merge()
        self.process_pending_merges()
        self.handle_attack_queue()

    def handle_attack_queue(self) -> None:
        """Processes the attack queue and updates attack indicators."""
        self.attack_indicators.clear()
        for attack in self.game_state.attack_queue:
            attack_indicator = DragArrow(color=(255, 0, 0))
            source_id, target_id = attack.card_id, attack.target_id

            if attack.target_is_player:
                target_ui = next(
                    (h for h in getattr(self.matrix, "hands", [])
                     if getattr(h, "player_id") == target_id),
                    None
                )
            else:
                target_ui = self.sprite_manager.get_sprite(target_id)

            source_ui = self.sprite_manager.get_sprite(source_id)
            if source_ui and target_ui:
                attack_indicator.start_pos = source_ui.rect.center
                attack_indicator.end_pos = target_ui.rect.center
                self.attack_indicators.append(attack_indicator)

    def handle_merge(self) -> None:
        """Handles mergeable groups by highlighting cards."""
        for player in self.game_state.players:
            groups = self.game_state.get_mergeable_groups(player.id)
            extc = self.exisiting_colors[player.id]

            for key, group in groups.items():
                if len(group) < 2:
                    continue

                color = extc.get(key, None)
                if color is None:
                    color = random_color()
                    while color in extc.values():
                        color = random_color()
                    extc[key] = color

                for card in group:
                    card_ui = self.sprite_manager.get_sprite(card.id)
                    if card_ui:
                        card_ui.highlight = True
                        card_ui.highlight_color = color

            removed = [key for key in list(extc.keys()) if key not in groups]
            for key in removed:
                extc.pop(key, None)

    def register_cards(self) -> None:
        """Registers all cards in the hand and matrix."""
        self.register_hand(self.game_state, self.matrix)
        self.register_matrix(self.game_state, self.matrix,
                             self.animation_mgr.create_place_animation)

    def process_pending_merges(self) -> None:
        """Processes pending merge events."""
        still_pending = []
        for event in self.pending_merges:
            card_id = event.card_id
            target_id = event.target_id
            result_id = event.result_card_id

            if (card_id in self.sprite_manager.sprites["matrix"] and
                    target_id in self.sprite_manager.sprites["matrix"] and
                    result_id in self.sprite_manager.sprites["matrix"]):
                card = self.sprite_manager.get_sprite(card_id)
                target = self.sprite_manager.get_sprite(target_id)
                result = self.sprite_manager.get_sprite(result_id)
                self.animation_mgr.create_merge_animation(card, target, result)
            else:
                still_pending.append(event)

        self.pending_merges = still_pending

    def is_pending_merge(self, card_id: str) -> bool:
        """Checks if a card is part of a pending merge.

        Args:
            card_id: The ID of the card.

        Returns:
            True if pending merge, False otherwise.
        """
        for event in self.pending_merges:
            if card_id in (event.card_id, event.target_id, event.result_card_id):
                return True
        return False

    def sync_sprites(
        self,
        desired_set: List[Card],
        zone: str,
        create_sprite: Callable[[Card], Sprite],
        add_animation: Optional[Callable[[Sprite], None]] = None,
        align_fn: Optional[Callable[[], None]] = None
    ) -> None:
        """Synchronizes sprites in a zone with the desired set of cards.

        Args:
            desired_set: List of cards to be present.
            zone: The zone name (e.g., "hand", "matrix").
            create_sprite: Factory function to create a new sprite.
            add_animation: Optional function for animation when a sprite is added.
            align_fn: Optional function to align sprites in the zone.
        """
        sprite_dict = self.sprite_manager.sprites[zone]
        existing_ids = set(sprite_dict.keys())
        desired_ids = {card.id for card in desired_set}

        to_add = desired_ids - existing_ids
        to_remove = existing_ids - desired_ids

        for cid in to_remove:
            if not self.is_pending_merge(cid):
                self.animation_mgr.create_death_animation(
                    cid, zone, self.sprite_manager)

        for card in desired_set:
            if card.id in to_add:
                sprite = create_sprite(card)
                self.sprite_manager.add_sprite(card, sprite, zone)
            else:
                sprite = sprite_dict.get(card.id)
                if sprite:
                    if hasattr(sprite, "logic_card"):
                        sprite.logic_card = card
                    elif hasattr(sprite, "_card") and hasattr(sprite._card, "logic_card"):
                        sprite._card.logic_card = card

                    if not self.animation_mgr.is_animating(sprite, ToggleRotateAnimation):
                        if hasattr(card, "mode"):
                            sprite.angle = 90 if card.mode == CardMode.DEFEND else 0

        if align_fn and (to_add or to_remove):
            align_fn()

        if add_animation and to_add:
            for cid in to_add:
                if not self.is_pending_merge(cid):
                    add_animation(sprite_dict[cid])

    def create_gui_card(self, card: Card, matrix: Matrix, flip: bool = False) -> Any:
        """Create GUI card with proper orientation.

        Args:
            card: The logic card to create a GUI representation for.
            matrix: The matrix context.
            flip: Whether the card should be flipped.

        Returns:
            The GUI card component.
        """
        is_opponent = self.game_state.players_lookup[card.owner_id].is_opponent

        if card.card_type == CardType.MONSTER:
            card_gui = CardStatOverlay(MonsterCardGUI(
                monster_info=card,
                size=(
                    matrix.grid["slot_width"] / 2,
                    matrix.grid["slot_height"]
                )),
                game_state=self.game_state,
                position="top" if is_opponent else "bottom")
        elif card.card_type == CardType.SPELL:
            card_gui = SpellCardGUI(card, size=(
                matrix.grid["slot_width"] / 2,
                matrix.grid["slot_height"]
            ))
        elif card.card_type == CardType.TRAP:
            card_gui = TrapCardGUI(card, size=(
                matrix.grid["slot_width"] / 2,
                matrix.grid["slot_height"]
            ))
        else:
            raise ValueError(f"Unknown card type: {card.card_type}")

        if flip:
            card_gui.flip = True

        return card_gui

    def register_hand(self, game_state: GameState, matrix: Matrix) -> None:
        """Registers cards currently in the player's hand.

        Args:
            game_state: Current game state.
            matrix: The matrix context.
        """
        current_cards = []
        for player in game_state.players:
            held_cards = game_state.player_info[player.id].held_cards
            for cid in held_cards.card_ids:
                card = game_state.get_card_by_id(cid)
                if card:
                    current_cards.append(card)

        def make_hand_sprite(card: Card) -> Sprite:
            is_opponent = game_state.players_lookup[card.owner_id].is_opponent
            card.is_face_down = is_opponent
            sprite = self.create_gui_card(card, matrix, flip=is_opponent)
            return sprite

        self.sync_sprites(
            desired_set=current_cards,
            zone="hand",
            create_sprite=make_hand_sprite,
            add_animation=lambda sprite: self.animation_mgr.create_draw_animation(
                matrix, sprite),
            align_fn=lambda: self.align_cards(matrix, check=False)
        )

    def register_matrix(
        self,
        game_state: GameState,
        matrix: Matrix,
        animation: Optional[Callable[[Sprite], None]] = None
    ) -> None:
        """Registers cards currently on the matrix board.

        Args:
            game_state: Current game state.
            matrix: The matrix context.
            animation: Optional animation function for new cards.
        """
        current_cards = [
            game_state.get_card_by_id(str(card_id))
            for row in game_state.field_matrix
            for card_id in row if card_id
        ]

        def make_matrix_sprite(card: Card) -> Sprite:
            is_opponent = game_state.players_lookup[card.owner_id].is_opponent
            card.is_face_down = card.card_type == CardType.TRAP
            sprite = self.create_gui_card(card, matrix, flip=is_opponent)

            if hasattr(card, "mode") and card.mode == CardMode.DEFEND:
                sprite.angle = 90

            row, col = card.pos_in_matrix
            sprite.rect.center = matrix.get_slot_rect(row, col).center
            sprite.placed_pos = sprite.rect.center
            return sprite

        self.sync_sprites(
            desired_set=current_cards,
            zone="matrix",
            add_animation=animation,
            create_sprite=make_matrix_sprite
        )

    def align_cards(self, matrix: Matrix, check: bool = False) -> None:
        """Aligns cards in the matrix hands.

        Args:
            matrix: The matrix context.
            check: Whether to perform an alignment check.
        """
        for hand in matrix.hands:
            hand.align(self.sprite_manager.sprites["hand"], check=check)

    def draw(self) -> None:
        """Draws all sprites and indicators to the screen."""
        for group in self.sprite_manager.sprites.values():
            for sprite in group.values():
                sprite.draw(self.screen)

        for arrow in self.attack_indicators:
            arrow.draw(self.screen)
