import uuid
from pydantic import BaseModel, Field


class Player(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    player_index: int
    name: str
    life_points: int = 8000
    original_life_points: int = life_points
    max_life_points: int = life_points
    is_opponent: bool = False

    def reset(self) -> None:
        """Reset player life points back to its original value."""
        self.life_points = self.original_life_points
