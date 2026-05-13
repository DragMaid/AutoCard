from uuid import uuid4
from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional, Tuple


class CardType(str, Enum):
    MONSTER = "MONSTER"
    SPELL = "SPELL"
    TRAP = "TRAP"


class Card(BaseModel):
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
