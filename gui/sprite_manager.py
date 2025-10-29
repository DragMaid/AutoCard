class SpriteManager:
    def __init__(self):
        self.sprites = {
            "hand": {},
            "matrix": {},
        }
        self._sprites = {}

    def add_sprite(self, card, sprite, zone):
        self.sprites[zone][card.id] = sprite
        self._sprites[card.id] = sprite

    def remove_sprite(self, card_id, zone=None):
        zones = [self.sprites[zone]] if zone else self.sprites.values()
        for z in zones:
            z.pop(card_id, None)

        # Only remove from global dict if card is gone from all zones
        still_exists = any(card_id in z for z in self.sprites.values())
        if not still_exists:
            self._sprites.pop(card_id, None)

    def get_sprite(self, card_id):
        """Global sprite lookup (any zone)."""
        return self._sprites.get(card_id)

    def get_zone(self, card_id):
        """Return which zone the card currently belongs to."""
        for zone_name, zone in self.sprites.items():
            if card_id in zone:
                return zone_name
        return None
