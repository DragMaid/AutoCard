import pygame
from gui.gui_info.game_area import GameArea
from gui.cache import load_image


class CollectionInfo:
    def __init__(self, cards, player_id):
        self.cards = cards # List of card IDs
        self.player_id = player_id

    def __len__(self):
        return len(self.cards)

    def __iter__(self):
        return iter(self.cards)

    def add(self, card_id):
        self.cards.append(card_id)

    def remove(self, card_id):
        self.cards.remove(card_id)


class HandUI(GameArea):
    def __init__(self, player_id, hand_info, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.hand_info = hand_info
        self.player_id = player_id
        self.last_count = len(self.hand_info.cards)

        image_path = "assets/deck.png"
        self.image = load_image(image_path).convert_alpha()
        self.image = pygame.transform.scale(self.image, self.rect.size)

    def draw(self, screen):
        screen.blit(self.image, self.rect)

    def align(self, sprites, check=False):
        # Skip if no card count change
        if check and len(self.hand_info.cards) == self.last_count:
            return

        for idx, card_id in enumerate(self.hand_info.cards):
            sprite = sprites.get(card_id)
            if not sprite:
                continue

            sprite.rect.topleft = (
                self.rect.x + idx * sprite.rect.w,
                self.rect.y
            )

        self.last_count = len(self.hand_info.cards)
