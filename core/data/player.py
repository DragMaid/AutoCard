import uuid
from pydantic import BaseModel, Field
from core.config import Config


class Player(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    player_index: int
    name: str
    life_points: int = Config.MAX_LIFE_POINTS
    original_life_points: int = life_points
    max_life_points: int = life_points
    is_opponent: bool = False

    def reset(self) -> None:
        """Resets player life points back to their original value."""
        self.life_points = self.original_life_points
