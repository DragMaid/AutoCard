import pygame
from gui.arrow import DragArrow
from core.cards.monster_card import MonsterCard


class InputManager:
    def __init__(self, matrix, game_engine, render_engine):
        self.matrix = matrix
        self.game_engine = game_engine
        self.dragging_card = None
        self.drag_arrow = None
        self.render_engine = render_engine

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:  # left click → start drag or activate trap
                # Check for trap activation first
                self._handle_left_click(event.pos)
                self._handle_left_click_arrow(event.pos)
                self.handle_click_card(event.pos)
            elif event.button == 3:  # right click → toggle
                self._handle_right_click(event.pos)

        elif event.type == pygame.MOUSEMOTION:
            if self.dragging_card:
                self.dragging_card.on_drag(event.pos)
            elif self.drag_arrow and self.drag_arrow.dragging:
                self.drag_arrow.end_pos = event.pos

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1 and self.dragging_card:
                _ = self.dragging_card.on_drop(
                    self.matrix, self.game_engine)
                self.dragging_card = None
                self.render_engine.align_cards(self.matrix)

            self._handle_release_arrow(event.pos)

    # TODO: this doesnt do anything yet
    # def _handle_trap_activation(self, pos):
        # """Check if a trap activation button was clicked. Returns True if activated."""
        # # Check all trap sprites on matrix
        # for card_id, sprite in self.render_engine.sprite_manager.sprites.get("matrix", {}).items():
            # from gui.cards_gui.trap_card import TrapCardGUI
            # if isinstance(sprite, TrapCardGUI) and sprite.activate_button_rect:
                # if sprite.activate_button_rect.collidepoint(pos):
                    # # Activate the trap
                    # sprite.on_activate(self.game_engine)
                    # return True

        # return False

    def _handle_left_click(self, pos):
        # Check hands from top-most first
        for hand in reversed(self.matrix.hands):
            for card_id in hand.hand_info.cards:
                card = self.render_engine.sprite_manager.get_sprite(
                    card_id)
                if not card:
                    continue

                owner = self.game_engine.game_state.players_lookup[card.logic_card.owner_id]
                if card.rect.collidepoint(pos) \
                        and card.is_draggable \
                        and not owner.is_opponent:
                    self.dragging_card = card
                    card.on_drag_start()
                    return  # stop after first draggable card is

    def _handle_release_arrow(self, pos):
        if self.drag_arrow and self.drag_arrow.dragging:
            self.drag_arrow.dragging = False
            success = False
            # Checking for cards in field matrix
            for row in self.game_engine.game_state.field_matrix:
                for card_id in row:
                    if not card_id:
                        continue

                    card = self.render_engine.sprite_manager.get_sprite(
                        card_id)
                    card_info = self.game_engine.game_state.get_card_by_id(
                        card_id)

                    if not card.rect.collidepoint(pos):
                        continue

                    if card_info.owner_id != self.drag_arrow.targets[0].owner_id:
                        self.drag_arrow.end_pos = card.rect.center
                        self.drag_arrow.targets[1] = card_info
                        success = self.game_engine.attack(
                            self.game_engine.turn_manager.get_current_player().id,
                            self.game_engine.turn_manager.get_next_player().id,
                            self.drag_arrow.targets[0].id,
                            self.drag_arrow.targets[1].id,
                        )
                        break
                    if card_info.owner_id == self.drag_arrow.targets[0].owner_id:
                        self.drag_arrow.end_pos = card.rect.center
                        self.drag_arrow.targets[1] = card_info

                        # Use logic_card to check type
                        if isinstance(card.logic_card, MonsterCard):
                            _ = self.game_engine.upgrade_monster(
                                self.game_engine.turn_manager.get_current_player().id,
                                # attacking/dragging monster
                                self.drag_arrow.targets[0].id,
                                # target monster to merge with
                                self.drag_arrow.targets[1].id,
                            )
                            break   # stop after successful merge

            # Checking for player hitbox
            if self.drag_arrow:
                self._handle_arrow_drop_player_hitbox(pos)
                self.drag_arrow = None

    def _handle_arrow_drop_player_hitbox(self, pos):
        opponent_hand = self.matrix.areas["opponent_hand_area"]

        if (opponent_hand.rect.collidepoint(pos)):
            self.drag_arrow.end_pos = opponent_hand.rect.center
            self.drag_arrow.targets[1] = self.game_engine.turn_manager.get_next_player(
            )
            _ = self.game_engine.attack(
                self.game_engine.turn_manager.get_current_player().id,
                self.game_engine.turn_manager.get_next_player().id,
                self.drag_arrow.targets[0].id,
                self.drag_arrow.targets[1].id,
                target_is_player=True
            )

    def _handle_left_click_arrow(self, pos):
        for row in self.game_engine.game_state.field_matrix:
            for card_id in row:
                if not card_id:
                    continue
                card_info = self.game_engine.game_state.get_card_by_id(card_id)
                card = self.render_engine.sprite_manager.get_sprite(
                    card_id)
                owner = self.game_engine.game_state.players_lookup[card_info.owner_id]
                if (
                    card
                    and card.rect.collidepoint(pos)
                    and card_info.ctype == "monster"
                    and card_info.mode == "attack"
                    and card_info.owner_id == self.game_engine.turn_manager.get_current_player().id
                    and not owner.is_opponent
                ):
                    self.drag_arrow = DragArrow()
                    self.drag_arrow.targets[0] = card_info
                    self.drag_arrow.start_pos = card.rect.center
                    self.drag_arrow.end_pos = card.rect.center
                    self.drag_arrow.dragging = True
                    return

    def _handle_right_click(self, pos):
        # Check all cards on the field
        for row in self.game_engine.game_state.field_matrix:
            for card_id in row:
                if not card_id:
                    continue
                card = self.render_engine.sprite_manager.get_sprite(
                    card_id)
                if card.rect.collidepoint(pos):
                    # Only call on_toggle when the sprite implements it.
                    # MonsterCardGUI implements on_toggle; generic CardGUI does not.
                    on_toggle = getattr(card, "on_toggle", None)
                    if callable(on_toggle):
                        on_toggle(self.game_engine)

                    return

    def handle_click_card(self, pos):
        for card_ui in self.render_engine.sprite_manager.sprites["matrix"].values():
            if card_ui.rect.collidepoint(pos):
                self.matrix.areas["preview_card_table"].set_card(
                    card_ui, self.game_engine.game_state)
                return  # stop after first match

        for card_ui in self.render_engine.sprite_manager.sprites["hand"].values():
            if card_ui.rect.collidepoint(pos):
                self.matrix.areas["preview_card_table"].set_card(
                    card_ui, self.game_engine.game_state)
                return

    def draw(self, screen):
        if self.drag_arrow:
            self.drag_arrow.draw(screen)
