import pygame


class AudioManager:
    train_mode = False

    @classmethod
    def set_train_mode(cls, value: bool):
        cls.train_mode = value

    @classmethod
    def play_sound(cls, file: str):
        # Skip audio if in train mode
        if cls.train_mode:
            return
        sound = pygame.mixer.Sound(file)
        sound.play()
