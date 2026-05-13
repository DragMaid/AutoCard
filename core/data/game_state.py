from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field
from core.cards.card import Card
from core.cards.monster_card import MonsterCard
from core.cards.trap_card import ActivateCondition
from core.data.player import Player
from core.utils import get_logger
from gui.background.hand import CollectionInfo
from core.config import config


class ModifyMode(str, Enum):
    ADD = "add"
    REMOVE = "remove"


class PlayerInfo(BaseModel):
    has_summoned_trap: bool = False
    has_summoned_monster: bool = False
    has_toggled: bool = False
    held_cards: CollectionInfo
    graveyard_cards: CollectionInfo
    deck_cards: CollectionInfo
    active_traps: List[str] = Field(default_factory=list)


class TrapContext(BaseModel):
    trigger_type: ActivateCondition
    attacker_id: Optional[str] = None
    defender_id: Optional[str] = None


class AttackEntry(BaseModel):
    attacker_id: str
    defender_id: str
    extra: Dict[str, Any] = Field(default_factory=dict)


class GameState(BaseModel):
    players: List[Player]

    game_over: bool = False
    player_info: Dict[str, PlayerInfo] = Field(default_factory=dict)
    entity_lookup: Dict[str, Card] = Field(default_factory=dict)
    field_matrix: List[List[Optional[str]]] = Field(default_factory=list)
    field_matrix_ownership: List[List[str]] = Field(default_factory=list)
    triggerable_traps: Dict[str, TrapContext] = Field(default_factory=dict)
    activated_traps: List[str] = Field(default_factory=list)
    attack_queue: List[AttackEntry] = Field(default_factory=list)

    @property
    def players_lookup(self) -> Dict[str, Player]:
        return {p.id: p for p in self.players}

    def model_post_init(self, __context: Any) -> None:
        self._logger = get_logger()

    # TODO: refactor this function a bit into smaller components
    def reset(self) -> None:
        """Reset the game state instance to its original state."""
        for player in self.players:
            player.reset()

        self.player_info = {
            player.id: PlayerInfo(
                held_cards=CollectionInfo([], player.id),
                graveyard_cards=CollectionInfo([], player.id),
                deck_cards=CollectionInfo([], player.id),
            )
            for player in self.players
        }
        self.game_over = False
        self.entity_lookup = {}
        self.field_matrix = \
            [[None for _ in range(config.COLS)] for _ in range(config.ROWS)]

        enemy_rows: List[List[str]] = \
            [[self.players[1].id] *
                config.COLS for _ in range(config.ROWS // 2)]
        player_rows: List[List[str]] = \
            [[self.players[0].id] *
                config.COLS for _ in range(config.ROWS // 2)]
        self.field_matrix_ownership = enemy_rows + player_rows

        self.triggerable_traps = {}
        self.activated_traps = []
        self.attack_queue = []

    def is_game_over(self) -> bool:
        """Returns a boolean indicating if one player is dead."""
        for player in self.players:
            if player.life_points <= 0:
                self.game_over = True
                break
        return self.game_over

    def modify_field(self, mode: ModifyMode, card: Card, pos: Tuple[int, int]) -> None:
        """Perform action validation before adding / removing card from field slots."""
        row, col = pos

        if mode is ModifyMode.ADD:
            if not (0 <= row < config.ROWS and 0 <= col < config.COLS):
                self._logger.error(
                    "Field modify failed",
                    extra={
                        "reason": "Invalid position",
                        "pos": pos,
                        "fieldSize": f"{config.ROWS}x{config.COLS}",
                    },
                )
                return

            if self.field_matrix[row][col] is not None:
                existing = self.entity_lookup.get(self.field_matrix[row][col])
                self._logger.warning(
                    "Field modify warning",
                    extra={
                        "reason": "Position already occupied",
                        "pos": pos,
                        "occupant": existing.name if existing else self.field_matrix[row][col],
                    },
                )
                return

            expected_owner_id = self.field_matrix_ownership[row][col]
            if card.owner_id != expected_owner_id:
                self._logger.error(
                    "Field modify failed",
                    extra={
                        "reason": "Ownership mismatch",
                        "cardName": card.name,
                        "ownerId": card.owner_id,
                        "pos": pos,
                        "expectedOwner": expected_owner_id,
                    },
                )
                return

            self.field_matrix[row][col] = card.id
            self.entity_lookup[card.id] = card
            card.pos_in_matrix = pos

            self._logger.info(
                "Field modified: card placed",
                extra={
                    "cardName": card.name,
                    "pos": pos,
                    "ownerId": card.owner_id,
                },
            )

        elif mode is ModifyMode.REMOVE:
            if not (0 <= row < config.ROWS and 0 <= col < config.COLS):
                self._logger.error(
                    "Field modify failed",
                    extra={
                        "reason": "Invalid position for removal",
                        "pos": pos,
                    },
                )
                return

            existing_card_id = self.field_matrix[row][col]
            if existing_card_id:
                existing_card = self.entity_lookup.get(existing_card_id)
                if existing_card:
                    try:
                        self._logger.info(
                            "Field modified: card removed",
                            extra={
                                "cardName": existing_card.name,
                                "pos": pos,
                                "ownerId": existing_card.owner_id,
                            },
                        )
                    except ValueError:
                        self._logger.error(
                            "Field modify error",
                            extra={
                                "reason": "Card not found in player's field list",
                                "cardName": existing_card.name,
                                "pos": pos,
                                "ownerId": existing_card.owner_id,
                            },
                        )
                    existing_card.pos_in_matrix = None
                else:
                    self._logger.error(
                        "Field modify error",
                        extra={
                            "reason": "Card ID not found in entity_lookup",
                            "cardId": existing_card_id,
                            "pos": pos,
                        },
                    )

            self.field_matrix[row][col] = None

    def get_card_by_id(self, card_id: str) -> Optional[Card]:
        """Helper function to get all logic card stored via its ID."""
        return self.entity_lookup.get(card_id)

    def get_player_field_cards(self, player_id: str) -> List[Card]:
        """Return a list of player's cards currently on the field."""
        return [
            self.entity_lookup[self.field_matrix[r][c]]
            for r in range(config.ROWS)
            for c in range(config.COLS)
            if self.field_matrix[r][c] is not None
            and self.field_matrix_ownership[r][c] == player_id
        ]

    def get_player_held_cards(self, player_id: str) -> List[Card]:
        return self.player_info[player_id].held_cards.cards

    def get_empty_slots(self, player_id: str) -> Optional[Tuple[int, int]]:
        """Return row, col tuples of all empty slots owned by user."""
        empty_slots = [
            (r, c)
            for r in range(config.ROWS)
            for c in range(config.COLS)
            if self.field_matrix[r][c] is None
            and self.field_matrix_ownership[r][c] == player_id
        ]
        return empty_slots

    def get_opponent_id(self, player_id: str) -> Optional[str]:
        """Get ID of the first player that is not the user."""
        for pid in self.player_info:
            if pid != player_id:
                return pid
        return None

    def get_mergeable_groups(self, player_id: str) -> Dict[Tuple, List[MonsterCard]]:
        """Returns a dict of tuple for keys and list of MonsterCard that are mergeable."""
        groups: Dict[Tuple, List[MonsterCard]] = {}
        for card in self.get_player_field_cards(player_id):
            if isinstance(card, MonsterCard):
                key = (player_id, card.type, card.level_star)
                groups.setdefault(key, []).append(card)
        return groups
