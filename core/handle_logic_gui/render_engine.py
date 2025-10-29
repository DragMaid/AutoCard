import pygame
from collections import defaultdict
from gui.cards_gui.card_gui import CardGUI
from gui.cards_gui.monster_card import MonsterCardGUI
from gui.cards_gui.spell_card import SpellCardGUI
from gui.cards_gui.trap_card import TrapCardGUI
from gui.cards_gui.stat_overlay import CardStatOverlay
from gui.animations.manager import AnimationManager
from gui.utils import random_color
from core.game_info.events import (
    AttackEvent, TrapTriggerEvent, ToggleEvent,
    SpellActiveEvent, MergeEvent
)
from gui.sprite_manager import SpriteManager


class RenderEngine:
    def __init__(self, field_matrix, screen, train_mode=False, player_idx=0):
        self.screen = screen
        self.field_matrix = field_matrix
        self.sprite_manager = SpriteManager()
        self.exisiting_colors = defaultdict(dict)
        self.pending_merges = []
        self.animation_mgr = AnimationManager(train_mode=train_mode)

    def reset(self):
        for value in self.sprite_manager.sprites.values():
            value.clear()
        self.exisiting_colors = defaultdict(dict)
        self.pending_merges.clear()

    def update(self, game_state, matrix, events):
        self.handle_events(game_state, matrix, events)
        self.register_cards(game_state, matrix)
        self.handle_merge(game_state)
        self.process_pending_merges()

    def handle_merge(self, game_state):
        for player in game_state.players:
            groups = game_state.get_mergeable_groups(player.id)
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

    def register_cards(self, game_state, matrix):
        self.register_hand(game_state, matrix)
        self.register_matrix(game_state, matrix,
                             self.animation_mgr.create_place_animation)

    def handle_events(self, game_state, matrix, events):
        try:
            for event in events.get_events():
                et = type(event)

                if et is AttackEvent:
                    card = self.sprite_manager.get_sprite(event.card_id)
                    if not card:
                        continue

                    if event.target_is_player:
                        opponent_hand = next(
                            (h for h in getattr(self.field_matrix, "hands", [])
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
                        matrix.areas["preview_card_table"].set_card(trap)

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

            events.clear_events()
        except Exception as e:
            print(f"[ERROR] handle_events failed: {e}")

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

        if align_fn and (to_add or to_remove):
            align_fn()

        if add_animation and to_add:
            for cid in to_add:
                if not self.is_pending_merge(cid):
                    add_animation(sprite_dict[cid])

    def create_gui_card(self, card, matrix):
        """Create GUI card with proper orientation"""
        if card.ctype == "monster":
            card_gui = CardStatOverlay(MonsterCardGUI(card, size=(
                matrix.grid["slot_width"] / 2,
                matrix.grid["slot_height"]
            )))
        elif card.ctype == "spell":
            card_gui = SpellCardGUI(card, size=(
                matrix.grid["slot_width"] / 2,
                matrix.grid["slot_height"]
            ))
        elif card.ctype == "trap":
            card_gui = TrapCardGUI(card, size=(
                matrix.grid["slot_width"] / 2,
                matrix.grid["slot_height"]
            ))
        else:
            card_gui = CardGUI(card, size=(
                matrix.grid["slot_width"] / 2,
                matrix.grid["slot_height"]
            ))

        return card_gui

    def register_hand(self, game_state, matrix):
        current_cards = []
        for player in game_state.players:
            held_cards = game_state.player_info[player.id]["held_cards"]
            for cid in held_cards.cards:
                card = game_state.get_card_by_id(cid)
                if card:
                    current_cards.append(card)

            # player_idx = 0 if player.id == game_state.players[0].id else 1
            # is_local = (player_idx == self.render_adapter.player_idx)

            # hand_area_key = self.render_adapter.get_hand_position(is_local)
            # if hand_area_key in self.field_matrix.areas:
                # self.field_matrix.areas[hand_area_key].hand_info = held_cards

        def make_hand_sprite(card):
            sprite = self.create_gui_card(card, matrix)
            return sprite

        self.sync_sprites(
            desired_set=current_cards,
            zone="hand",
            create_sprite=make_hand_sprite,
            add_animation=lambda sprite: self.animation_mgr.create_draw_animation(
                matrix, sprite),
            align_fn=lambda: self.align_cards(matrix, check=False)
        )

    def register_matrix(self, game_state, matrix, animation=None):
        current_cards = {
            game_state.get_card_by_id(card_id) 
            for row in game_state.field_matrix 
            for card_id in row if card_id
        }
        current_cards = {c for c in current_cards if c is not None}

        def make_matrix_sprite(card):
            sprite = self.create_gui_card(card, matrix)

            # Use render adapter to get visual position
            # visual_row, visual_col = self.render_adapter.transform_position(
                # *card.pos_in_matrix
            # )

            # sprite.rect.center = matrix.get_slot_rect(
                # visual_row, visual_col).center
            sprite.placed_pos = sprite.rect.center

            owner_idx = 0 if card.owner_id == game_state.players[0].id else 1

            if isinstance(sprite, TrapCardGUI):
                # sprite.is_face_down = self.render_adapter.is_card_face_down_for_viewer(
                    # card, owner_idx
                # )
                if sprite.is_face_down:
                    sprite.card_surface = pygame.transform.smoothscale(
                        sprite.image_face_down.copy(), sprite.display_size)
                else:
                    sprite._render_card_with_text()
                sprite.update()
            else:
                sprite.is_face_down = False
                sprite._render_card_with_text()

                # Flip opponent cards
                # if self.render_adapter.should_flip_card_image(owner_idx):
                    # sprite.card_surface = pygame.transform.flip(
                        # sprite.card_surface, False, True)
                sprite.update()

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
