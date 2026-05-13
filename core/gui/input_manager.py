import pygame
from gui.arrow import DragArrow
from core.cards.monster_card import MonsterCard

LEFT_CLICK = 1
RIGHT_CLICK = 3


class InputManager:
    def __init__(self, matrix, game_engine, render_engine):
        self.matrix = matrix
        self.game_engine = game_engine
        self.render_engine = render_engine
        self.dragging_card = None
        self.drag_arrow = None

        self.INPUT_MAP = {
            pygame.MOUSEBUTTONDOWN: self._handle_mouse_down,
            pygame.MOUSEMOTION: self._handle_mouse_motion,
            pygame.MOUSEBUTTONUP: self._handle_mouse_up
        }

    def handle_event(self, event):
        if self.game_engine.turn_manager.is_trap_stage() and \
                not self.game_engine.is_local_turn():
            return
        self.INPUT_MAP[event.type](event)

    def draw(self, screen):
        if self.drag_arrow:
            self.drag_arrow.draw(screen)

    def _handle_mouse_down(self, event):
        if event.button == LEFT_CLICK:
            self._handle_trap_activation(event)
            if not self.dragging_card:
                self._try_start_drag_card(event.pos)
            if not self.drag_arrow:
                self._try_start_drag_arrow(event.pos)
            self._handle_click_card(event.pos)
        elif event.button == RIGHT_CLICK:
            self._handle_right_click(event.pos)

    def _handle_mouse_motion(self, event):
        if self.dragging_card:
            self.dragging_card.on_drag(event.pos)
        elif self.drag_arrow and self.drag_arrow.dragging:
            self.drag_arrow.end_pos = event.pos
        self._handle_trap_activation(event)

    def _handle_mouse_up(self, event):
        if event.button == LEFT_CLICK:
            if self.dragging_card:
                self.dragging_card.on_drop(self.matrix, self.game_engine)
                self.dragging_card = None
                self.render_engine.align_cards(self.matrix)
            if self.drag_arrow:
                self._finish_drag_arrow(event.pos)
                self.drag_arrow = None

    def _handle_trap_activation(self, event):
        """Toggle trap activation when its button is pressed. Returns True if handled."""
        for trap_id in self.game_engine.game_state.triggerable_traps:
            trap_ui = self.render_engine.sprite_manager.get_sprite(trap_id)
            if not trap_ui:
                continue

            activate_btn = getattr(trap_ui, "activate_button", None)
            if not activate_btn or not trap_ui.triggerable:
                continue

            if not activate_btn.handle_event(event):
                continue

            trap_ui.activated = not trap_ui.activated
            self.game_engine.toggle_trap_activation(
                trap_id, activated=trap_ui.activated)
            return True

        return False

    def _try_start_drag_card(self, pos):
        """Pick up the top-most draggable hand card under pos."""
        for hand in reversed(self.matrix.hands):
            for card_id in hand.hand_info.cards:
                card = self.render_engine.sprite_manager.get_sprite(card_id)
                if not card:
                    continue
                owner = self.game_engine.game_state.players_lookup[card.logic_card.owner_id]
                if card.rect.collidepoint(pos) and card.is_draggable and not owner.is_opponent:
                    self.dragging_card = card
                    card.on_drag_start()
                    return

    def _try_start_drag_arrow(self, pos):
        """Begin dragging an attack arrow from a valid attacker under pos."""
        current_player_id = self.game_engine.turn_manager.get_current_player().id

        for card_id in self._iter_field_card_ids():
            card_info = self.game_engine.game_state.get_card_by_id(card_id)
            card = self.render_engine.sprite_manager.get_sprite(card_id)
            owner = self.game_engine.game_state.players_lookup[card_info.owner_id]

            if (
                card
                and card.rect.collidepoint(pos)
                and card_info.ctype == "monster"
                and card_info.mode == "attack"
                and card_info.owner_id == current_player_id
                and not owner.is_opponent
            ):
                self.drag_arrow = DragArrow()
                self.drag_arrow.targets[0] = card_info
                self.drag_arrow.start_pos = card.rect.center
                self.drag_arrow.end_pos = card.rect.center
                self.drag_arrow.dragging = True
                return

    def _finish_drag_arrow(self, pos):
        """Resolve an arrow drop: attack a field card, merge, or hit the opponent directly."""
        self.drag_arrow.dragging = False

        if self._try_resolve_arrow_on_field(pos):
            return
        self._try_resolve_arrow_on_player(pos)

    def _try_resolve_arrow_on_field(self, pos):
        """
        Returns True if the arrow landed on a field card and an action was taken.
        """
        attacker = self.drag_arrow.targets[0]
        current_player_id = self.game_engine.turn_manager.get_current_player().id
        next_player_id = self.game_engine.turn_manager.get_next_player().id

        for card_id in self._iter_field_card_ids():
            card = self.render_engine.sprite_manager.get_sprite(card_id)
            if not card.rect.collidepoint(pos):
                continue

            card_info = self.game_engine.game_state.get_card_by_id(card_id)
            self.drag_arrow.end_pos = card.rect.center
            self.drag_arrow.targets[1] = card_info

            if card_info.owner_id != attacker.owner_id:
                self.game_engine.attack(
                    current_player_id, next_player_id,
                    attacker.id, card_info.id,
                )
                return True

            # Same owner — attempt a merge if both are monsters
            if isinstance(card.logic_card, MonsterCard):
                self.game_engine.upgrade_monster(
                    current_player_id,
                    attacker.id,
                    card_info.id,
                )
                return True

        return False

    def _try_resolve_arrow_on_player(self, pos):
        """Direct attack on the opponent when the arrow is dropped on their hand area."""
        opponent_hand = self.matrix.areas["opponent_hand_area"]
        if not opponent_hand.rect.collidepoint(pos):
            return

        current_player = self.game_engine.turn_manager.get_current_player()
        next_player = self.game_engine.turn_manager.get_next_player()

        self.drag_arrow.end_pos = opponent_hand.rect.center
        self.drag_arrow.targets[1] = next_player

        self.game_engine.attack(
            current_player.id, next_player.id,
            self.drag_arrow.targets[0].id, next_player.id,
            target_is_player=True,
        )

    def _handle_right_click(self, pos):
        for card_id in self._iter_field_card_ids():
            card = self.render_engine.sprite_manager.get_sprite(card_id)
            if not card.rect.collidepoint(pos):
                continue
            on_toggle = getattr(card, "on_toggle", None)
            if callable(on_toggle):
                on_toggle(self.game_engine)
            return

    def _handle_click_card(self, pos):
        preview = self.matrix.areas["preview_card_table"]

        for card_ui in self.render_engine.sprite_manager.sprites["matrix"].values():
            if card_ui.rect.collidepoint(pos):
                preview.set_card(card_ui, self.game_engine.game_state)
                return

        for card_ui in self.render_engine.sprite_manager.sprites["hand"].values():
            if card_ui.rect.collidepoint(pos):
                preview.set_card(card_ui, self.game_engine.game_state)
                return

    def _iter_field_card_ids(self):
        """Yield every non-empty card_id from the field matrix."""
        for row in self.game_engine.game_state.field_matrix:
            for card_id in row:
                if card_id:
                    yield card_id
