import uuid


class Player:
    def __init__(self,
                 player_index: int,
                 name: str,
                 life_points: int = 8000,
                 is_opponent: bool = False,
                 id=None
                 ):
        self.id = str(id) if id else str(uuid.uuid4())
        self.player_index = player_index
        self.name = name
        self.life_points = life_points
        self.original_life_points = life_points
        self.max_life_points = life_points
        self.is_opponent = is_opponent

    def reset(self):
        self.life_points = self.original_life_points

    def __str__(self):
        return f"Name: {self.name} \
                 Life-point: {self.life_points} \
                 Is-Opponent: {self.is_opponent} \
                 Index: {self.player_index}"
