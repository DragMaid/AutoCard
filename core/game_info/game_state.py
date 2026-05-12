from typing import Tuple, List, Optional, Literal
from random import choice
from core.player import Player
from core.cards.card import Card
from core.cards.monster_card import MonsterCard
from gui.gui_info.hand import CollectionInfo
from core.cards.trap_card import ActivateCondition
from core.utils import get_logger

ModifyMode = Literal["add", "remove"]


class GameState:
    def __init__(self, players: List[Player], rows: int = 4, cols: int = 5):
        self.players: List[Player] = players
        self.players_lookup: dict[str, Player] = {p.id: p for p in players}
        self.max_cards: int = 10
        self.game_over: bool = False
        self.entity_lookup: dict = {}

        self.logger = get_logger()
        self.rows = rows
        self.cols = cols

        self.reset()
        self.logger.info(f"GameState initialized: {rows}x{
                         cols} field, {len(players)} players")

    def reset(self):
        # Initialize player-related info
        self.player_info = {
            player.id: {
                "has_summoned_trap": False,
                "has_summoned_monster": False,
                "has_toggled": False,
                "held_cards": CollectionInfo([], player.id),
                "graveyard_cards": CollectionInfo([], player.id),
                "deck_cards": CollectionInfo([], player.id),
                "active_traps": [],
            }
            for player in self.players
        }
        self.game_over = False

        # Initialize the field
        self.entity_lookup = {}
        self.field_matrix: List[List[Optional[str]]] = [
            [None for _ in range(self.cols)] for _ in range(self.rows)]

        # Ownership matrix (top half = players[1], bottom half = players[0])
        self.field_matrix_ownership: List[List[str]] = [
            [self.players[1].id for _ in range(self.cols)] for _ in range(self.rows // 2)
        ] + [
            [self.players[0].id for _ in range(self.cols)] for _ in range(self.rows // 2)
        ]

        # Track which cards each player has on the field
        self._player_cards: dict[str, List[str]] = {
            player.id: [] for player in self.players}

        # Track traps that can be triggered this phase (trap_id -> trigger context)
        # Context includes: {'trigger_type': 'attack'|'summon'|'toggle', 'attacker_id': str, 'defender_id': str}
        self.triggerable_traps: dict[str, dict] = {}

        # Track which traps the player has chosen to activate in current phase
        self.activated_traps: set[str] = set()

        # Attack queue which wait for any trap resolve to run before processing
        self.attack_queue: list[dict] = []

    def is_game_over(self) -> bool:
        """Check if any player's life points reached 0 and mark the game as over."""
        for player in self.players:
            if player.life_points <= 0:
                self.game_over = True
                self.logger.info(
                    f"GAME OVER! {player.name} defeated (LP: {player.life_points})")

                # Log winner
                winner = [p for p in self.players if p != player][0] if len(
                    self.players) == 2 else None
                if winner:
                    self.logger.info(
                        f"Winner: {winner.name} (LP: {winner.life_points})")
                break
        return self.game_over

    def modify_field(self, mode: ModifyMode, card: Card, pos: Tuple[int, int]) -> None:
        """Add or remove a card from the field."""
        row, col = pos

        if mode == "add":
            # Validation checks with logging
            if not (0 <= row < self.rows and 0 <= col < self.cols):
                self.logger.error(f"FIELD MODIFY FAILED: Invalid position {
                                  pos} for field size {self.rows}x{self.cols}")
                return

            if self.field_matrix[row][col] is not None:
                existing_id = self.field_matrix[row][col]
                existing = self.entity_lookup.get(existing_id)
                self.logger.warning(f"FIELD MODIFY WARNING: Position {pos} already occupied by {
                                    existing.name if existing else existing_id}")
                return

            # Check ownership
            expected_owner_id = self.field_matrix_ownership[row][col]
            if card.owner_id != expected_owner_id:
                self.logger.error(f"FIELD MODIFY FAILED: {card.owner_id} trying to place {
                                  card.name} at {pos}, but position belongs to {expected_owner_id}")
                return

            self.field_matrix[row][col] = card.id
            self._player_cards[card.owner_id].append(card.id)
            self.entity_lookup[card.id] = card
            card.pos_in_matrix = pos

            self.logger.info(f"Field modified: {card.name} placed at {
                             pos} by {card.owner_id}")

        elif mode == "remove":
            if not (0 <= row < self.rows and 0 <= col < self.cols):
                self.logger.error(f"FIELD MODIFY FAILED: Invalid position {
                                  pos} for removal")
                return

            existing_card_id = self.field_matrix[row][col]
            if existing_card_id:
                existing_card = self.entity_lookup.get(existing_card_id)
                if existing_card:
                    try:
                        self._player_cards[existing_card.owner_id].remove(
                            existing_card_id)
                        self.logger.info(f"Field modified: {existing_card.name} removed from {
                                         pos} (Owner: {existing_card.owner_id})")
                    except ValueError:
                        self.logger.error(f"FIELD MODIFY ERROR: {existing_card.name} at {
                                          pos} not found in {existing_card.owner_id}'s field cards")
                    existing_card.pos_in_matrix = None
                else:
                    self.logger.error(
                        f"FIELD MODIFY ERROR: Card ID {existing_card_id} at {pos} not found in entity_lookup")

            self.field_matrix[row][col] = None

    def get_player_cards(self, player_id: str) -> List[Card]:
        """Return all cards a player currently has on the field."""
        card_ids = self._player_cards.get(player_id, [])
        return [self.entity_lookup[cid] for cid in card_ids if cid in self.entity_lookup]

    def get_random_empty_slot(self, player_id: str) -> Optional[Tuple[int, int]]:
        """Return a random empty slot in the field owned by the player, or None if full."""
        empty_slots = [
            (r, c)
            for r in range(self.rows)
            for c in range(self.cols)
            if self.field_matrix[r][c] is None and self.field_matrix_ownership[r][c] == player_id
        ]

        if not empty_slots:
            self.logger.warning(
                f"No empty slots available for {player_id}")
            return None

        slot = choice(empty_slots)
        self.logger.debug(f"Random empty slot selected for {player_id}: {
                          slot} (from {len(empty_slots)} available)")
        return slot

    def get_opponent_id(self, player_id: str) -> Optional[str]:
        """Get the opponent ID of the given player ID."""
        for pid in self.player_info.keys():
            if pid != player_id:
                return pid
        return None

    def get_cards_typed(self, player_id: str, ctype: str) -> List[Card]:
        """Get all cards of a specific type for a player."""
        cards = [card for card in self.get_player_cards(
            player_id) if card.ctype == ctype]
        return cards

    def get_field_summary(self, player_id: str) -> dict:
        """Get a summary of a player's field state for logging."""
        from core.cards.monster_card import MonsterCard
        from core.cards.trap_card import TrapCard

        cards = self.get_player_cards(player_id)
        monsters = [c for c in cards if isinstance(c, MonsterCard)]
        traps = [c for c in cards if isinstance(c, TrapCard)]

        return {
            "total_cards": len(cards),
            "monsters": len(monsters),
            "traps": len(traps),
            "hand_size": len(self.player_info[player_id]["held_cards"].cards),
            "graveyard_size": len(self.player_info[player_id]["graveyard_cards"].cards),
            "has_summoned_monster": self.player_info[player_id]["has_summoned_monster"],
            "has_summoned_trap": self.player_info[player_id]["has_summoned_trap"],
            "has_toggled": self.player_info[player_id]["has_toggled"],
        }

    def log_field_state(self):
        """Log the current field state in a readable format."""
        self.logger.info("FIELD STATE")

        for r in range(self.rows):
            row_str = []
            for c in range(self.cols):
                card_id = self.field_matrix[r][c]
                owner_id = self.field_matrix_ownership[r][c]
                card = self.entity_lookup.get(card_id)
                if card:
                    row_str.append(f"[{card.name[:10]:10s}|{owner_id}]")
                else:
                    row_str.append(f"[{'Empty':10s}|{owner_id}]")
            self.logger.info(f"Row {r}: {' '.join(row_str)}")

    def validate_card_placement(self, card: Card, pos: Tuple[int, int]) -> Tuple[bool, str]:
        """Validate if a card can be placed at a given position. Returns (valid, reason)."""
        row, col = pos

        # Check bounds
        if not (0 <= row < self.rows and 0 <= col < self.cols):
            return False, f"Position {pos} out of bounds (field size: {self.rows}x{self.cols})"

        # Check if slot is empty
        if self.field_matrix[row][col] is not None:
            existing_id = self.field_matrix[row][col]
            existing = self.entity_lookup.get(existing_id)
            return False, f"Position {pos} occupied by {existing.name if existing else existing_id} (Owner: {self.field_matrix_ownership[row][col]})"

        # Check ownership
        expected_owner_id = self.field_matrix_ownership[row][col]
        if card.owner_id != expected_owner_id:
            return False, f"Position {pos} belongs to {expected_owner_id}"

        # Check if player has reached max cards
        player_card_count = len(self._player_cards.get(card.owner_id, []))
        if player_card_count >= self.max_cards:
            return False, f"{card.owner_id} already has max cards on field ({player_card_count}/{self.max_cards})"

        return True, "Valid placement"

    def has_slot_available(self, player_id: str) -> bool:
        return len(self._player_cards.get(player_id, [])) < self.max_cards

    def get_card_by_id(self, id: str) -> Optional[Card]:
        return self.entity_lookup.get(id)

    def get_mergeable_groups(self, player_id: str):
        """Get groups of monsters that can be merged for upgrades."""
        monsters = self.get_player_cards(player_id)

        if not monsters:
            return {}

        # Group monsters by type and level
        groups = {}
        for monster in monsters:
            if isinstance(monster, MonsterCard):
                key = (player_id, monster.type, monster.level_star)
                if key not in groups:
                    groups[key] = []
                groups[key].append(monster)
        return groups

    def serialize(self):
        content = {}

        players = []
        for p in self.players:
            p = vars(p).copy()
            del p["original_life_points"]
            del p["max_life_points"]
            players.append(p)

        content["players"] = players
        content["player_info"] = self.player_info

        content["player_info"] = {
            k: {
                "has_summoned_trap": v["has_summoned_trap"],
                "has_summoned_monster": v["has_summoned_monster"],
                "has_toggled": v["has_toggled"],
                "held_cards": vars(v["held_cards"]),
                "graveyard_cards": vars(v["graveyard_cards"]),
                "deck_cards": vars(v["deck_cards"]),
                "active_traps": v["active_traps"]
            }
            for k, v in self.player_info.items()
        }
        content["game_over"] = self.game_over
        content["entity_lookup"] = {k: vars(v)
                                    for k, v in self.entity_lookup.items()}
        content["field_matrix"] = self.field_matrix
        content["field_matrix_ownership"] = self.field_matrix_ownership
        content["player_cards"] = self._player_cards

        content["max_cards"] = self.max_cards
        content["rows"] = self.rows
        content["cols"] = self.cols

        content["triggerable_traps"] = self.triggerable_traps
        for v in content["triggerable_traps"].values():
            raw = v["trigger_type"]
            v["trigger_type"] = (
                raw if isinstance(raw, str)
                else raw.value
            )
        content["activated_traps"] = list(self.activated_traps)
        content["attack_queue"] = self.attack_queue

        return content

    def deserialize(self, content):
        from core.player import Player

        players = []
        for p in content["players"]:
            p["is_opponent"] = not p["is_opponent"]
            players.append(Player(**p))
        self.players = players
        self.players_lookup = {p.id: p for p in self.players}

        self.player_info = {
            k: {
                "has_summoned_trap": v["has_summoned_trap"],
                "has_summoned_monster": v["has_summoned_monster"],
                "has_toggled": v["has_toggled"],
                "held_cards": CollectionInfo(**v["held_cards"]),
                "graveyard_cards": CollectionInfo(**v["graveyard_cards"]),
                "deck_cards": CollectionInfo(**v["deck_cards"]),
                "active_traps": v["active_traps"]
            }
            for k, v in content["player_info"].items()
        }
        self.game_over = content["game_over"]

        self.max_cards = content["max_cards"]
        self.rows = content["rows"]
        self.cols = content["cols"]

        # NOTE: Deserializing card must be done after the players
        self.entity_lookup = {k: self._deserialize_card(
            v) for k, v in content["entity_lookup"].items()}

        self.field_matrix = self._deserialize_2d_matrix(
            content["field_matrix"])

        # Update new flipped position
        for i in range(len(self.field_matrix)):
            for j in range(len(self.field_matrix[i])):
                card_id = self.field_matrix[i][j]
                if card_id:
                    self.entity_lookup[card_id].pos_in_matrix = [i, j]

        self.field_matrix_ownership = self._deserialize_2d_matrix(
            content["field_matrix_ownership"])
        self._player_cards = content["player_cards"]
        self.triggerable_traps = content.get("triggerable_traps", {})

        for v in self.triggerable_traps.values():
            v["trigger_type"] = ActivateCondition(v["trigger_type"])

        self.activated_traps = set(content.get("activated_traps", []))
        self.attack_queue = content.get("attack_queue", [])

    @staticmethod
    def _deserialize_card(card_dict):
        from core.cards.monster_card import MonsterCard
        from core.cards.spell_card import SpellCard
        from core.cards.trap_card import TrapCard

        card_map = {
            "monster": MonsterCard,
            "spell": SpellCard,
            "trap": TrapCard
        }

        card_dict["is_opponent"] = not card_dict["is_opponent"]
        ctype = card_dict["ctype"]
        if card_dict['is_opponent']:
            card_dict["is_face_down"] = ctype == "trap" or not isinstance(
                card_dict["pos_in_matrix"], list)
        else:
            card_dict["is_face_down"] = ctype == "trap" and isinstance(
                card_dict["pos_in_matrix"], list)
        card = card_map[ctype](**card_dict)
        return card

    @staticmethod
    def _deserialize_2d_matrix(matrix):
        # Flip matrix 180 degrees (both axes)
        return [row[::-1] for row in matrix[::-1]]
