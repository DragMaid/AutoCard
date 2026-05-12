from uuid import UUID, uuid4
from pydantic import BaseModel, Field
from enum import Enum


class CardType(Enum):
    MONSTER = "MONSTER"
    SPELL = "SPELL"
    TRAP = "TRAP"


class Card(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    description: str

    card_type: CardType
    owner_id: str

    is_placed: bool = False
    is_face_down: bool = False
    is_opponent: bool = False
