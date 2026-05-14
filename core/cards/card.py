from uuid import uuid4
from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional, Tuple


class CardType(str, Enum):
    MONSTER = "MONSTER"
    SPELL = "SPELL"
    TRAP = "TRAP"


class Card(BaseModel):
    """Represents a generic card in the game.

    Attributes:
        id: Unique identifier for the card.
        name: Name of the card.
        description: Description text of the card.
        card_type: Category of the card (e.g., MONSTER, SPELL).
        owner_id: ID of the player who owns this card.
        image_path: Optional path to the card's visual asset.
        is_placed: Indicates if the card is currently on the field.
        is_face_down: Indicates if the card is face-down.
        is_opponent: Indicates if the card belongs to the opponent.
        pos_in_matrix: Position of the card on the field as (col, row).
    """
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    description: str

    card_type: CardType
    owner_id: str
    image_path: Optional[str] = None

    is_placed: bool = False
    is_face_down: bool = False
    is_opponent: bool = False
    pos_in_matrix: Optional[Tuple[int, int]] = None
