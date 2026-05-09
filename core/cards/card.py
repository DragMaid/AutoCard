from typing import Literal, Optional, Tuple
import uuid

cardType = Literal["monster", "spell", "trap"]


class Card:
    def __init__(
        self,
            name: str,
            description: str,
            ctype: cardType,
            ability: str,
            owner_id: str,
            is_placed: bool = False,
            is_face_down: bool = False,
            is_opponent: bool = False,
            id=None,
            pos_in_matrix: Optional[Tuple[int, int]] = None
    ):
        self.id = str(id) if id else str(uuid.uuid4())
        self.name = name
        self.description = description
        self.ability = ability
        self.ctype = ctype
        self.owner_id = owner_id
        self.is_placed = is_placed
        self.is_face_down = is_face_down
        self.pos_in_matrix = pos_in_matrix
        self.is_opponent = is_opponent
