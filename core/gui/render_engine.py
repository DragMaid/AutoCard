import logging
from collections import defaultdict
from gui.cards.monster_card import MonsterCardGUI
from gui.cards.spell_card import SpellCardGUI
from gui.cards.trap_card import TrapCardGUI
from gui.cards.stat_overlay import CardStatOverlay
from gui.animations.manager import AnimationManager
from gui.animations.toggle import ToggleRotateAnimation
from gui.utils import random_color
from core.data.events import (
    AttackEvent, TrapTriggerEvent, ToggleEvent,
    SpellActiveEvent, MergeEvent, TrapTriggerableEvent
)
from gui.screen.arrow import DragArrow
from gui.sprites.sprite_manager import SpriteManager
from core.cards.card import CardType
from core.cards.monster_card import CardMode

logger = logging.getLogger(__name__)


class RenderEngine:
    def __init__(
        self,
        *,
        matrix,
        screen,
        game_state,
        event_logger,
        turn_manager,
        train_mode=False,
    ):
        self.screen = screen
        self.matrix = matrix
        self.sprite_manager = SpriteManager()
        self.exisiting_colors = defaultdict(dict)
        self.pending_merges = []
        self.game_state = game_state
        self.turn_manager = turn_manager
        self.event_logger = event_logger
        self.animation_mgr = AnimationManager(
            train_mode=train_mode, game_state=game_state)
        self.sprite_lookup = {}

        self.last_triggered_count = 0
        self.attack_indicators = []

    def reset(self):
        for value in self.sprite_manager.sprites.values():
            value.clear()
        self.exisiting_colors = defaultdict(dict)
        self.pending_merges.clear()

    def update(self):
        self.handle_events()
        self.register_cards()
        self.handle_merge()
        self.process_pending_merges()
        self.handle_attack_queue()

    def handle_attack_queue(self):
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
            attack_indicator.start_pos = source_ui.rect.center
            attack_indicator.end_pos = target_ui.rect.center
            self.attack_indicators.append(attack_indicator)

    def handle_merge(self):
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

    def register_cards(self):
        self.register_hand(self.game_state, self.matrix)
        self.register_matrix(self.game_state, self.matrix,
                             self.animation_mgr.create_place_animation)

    # TODO: refactor this to policy based
    def handle_events(self):
        try:
            for event in self.event_logger.get_events():
                et = type(event)

                if et is AttackEvent:
                    card = self.sprite_manager.get_sprite(event.card_id)
                    if not card:
                        continue

                    if event.target_is_player:
                        opponent_hand = next(
                            (h for h in getattr(self.matrix, "hands", [])
                             if getattr(h, "player_id") == event.target_id),
                            None
                        )
                        if opponent_hand:
                            self.animation_mgr.create_attack_player_animation(
                                card, opponent_hand)
                    else:
                        target = self.sprite_manager.get_sprite(
                            event.target_id)
                        if target:
                            self.animation_mgr.create_attack_animation(
                                card, target)

                elif et is TrapTriggerEvent:
                    trap = self.sprite_manager.get_sprite(event.card_id)
                    if trap:
                        self.animation_mgr.create_trigger_animation(trap)
                        self.matrix.areas["preview_card_table"].set_card(
                            trap, self.game_state)

                elif et is TrapTriggerableEvent:
                    trap = self.sprite_manager.get_sprite(event.card_id)
                    if trap:
                        self.animation_mgr.create_triggerable_animation(trap)

                elif et is ToggleEvent:
                    card = self.sprite_manager.get_sprite(event.card_id)
                    if card:
                        self.animation_mgr.create_toggle_animation(
                            card, event.mode)

                elif et is SpellActiveEvent:
                    spell = self.sprite_manager.get_sprite(event.spell_id)
                    if spell:
                        self.animation_mgr.create_spell_animation(spell)

                elif et is MergeEvent:
                    self.pending_merges.append(event)

            self.event_logger.clear_events()
        except Exception as e:
            logger.error(f"[ERROR] handle_events failed: {e}")

    def process_pending_merges(self):
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

    def is_pending_merge(self, card_id):
        for event in self.pending_merges:
            if card_id in (event.card_id, event.target_id, event.result_card_id):
                return True
        return False

    # TODO: maybe doing an event based manager is more efficient ?
    def sync_sprites(self, desired_set, zone, create_sprite,
                     add_animation=None, align_fn=None):
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
            # TODO: this not a very smart way to handle it, make gui card hold card_id instead
            else:
                # Update the logic card reference for existing sprites
                sprite = sprite_dict.get(card.id)
                if sprite:
                    # Handle both raw CardGUI and CardStatOverlay (which delegates to _card)
                    if hasattr(sprite, "logic_card"):
                        sprite.logic_card = card
                    elif hasattr(sprite, "_card") and hasattr(sprite._card, "logic_card"):
                        sprite._card.logic_card = card

                    # Sync visual state if not animating
                    if not self.animation_mgr.is_animating(sprite, ToggleRotateAnimation):
                        if hasattr(card, "mode"):
                            sprite.angle = 90 if card.mode == CardMode.DEFEND else 0

        if align_fn and (to_add or to_remove):
            align_fn()

        if add_animation and to_add:
            for cid in to_add:
                if not self.is_pending_merge(cid):
                    add_animation(sprite_dict[cid])

    def create_gui_card(self, card, matrix, flip=False):
        """Create GUI card with proper orientation"""
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
            raise

        if flip:
            card_gui.flip = True

        return card_gui

    def register_hand(self, game_state, matrix):
        current_cards = []
        for player in game_state.players:
            held_cards = game_state.player_info[player.id].held_cards
            for cid in held_cards.card_ids:
                card = game_state.get_card_by_id(cid)
                if card:
                    current_cards.append(card)

        def make_hand_sprite(card):
            # NOTE: the gui card will sync display with state of the logic card
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

    # TODO: add type hint after
    def register_matrix(self, game_state, matrix, animation=None):
        current_cards = [
            game_state.get_card_by_id(str(card_id))
            for row in game_state.field_matrix
            for card_id in row if card_id
        ]

        def make_matrix_sprite(card):
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

    def align_cards(self, matrix, check=False):
        for hand in matrix.hands:
            hand.align(self.sprite_manager.sprites["hand"], check=check)

    def draw(self):
        for group in self.sprite_manager.sprites.values():
            for sprite in group.values():
                sprite.draw(self.screen)

        for arrow in self.attack_indicators:
            arrow.draw(self.screen)
