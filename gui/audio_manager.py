import pygame
import time


class AudioManager:
    train_mode = False
    sounds = {}
    channels = {}
    last_played = {}
    cooldown = 0.08

    @classmethod
    def set_train_mode(cls, value: bool):
        cls.train_mode = value

    @classmethod
    def play_sound(cls, file: str):
        # Skip audio if in train mode
        if cls.train_mode:
            return

        now = time.time()

        last_time = cls.last_played.get(file, 0)
        if now - last_time < cls.cooldown:
            return

        cls.last_played[file] = now

        if file not in cls.sounds:
            sound = pygame.mixer.Sound(file)
            sound.set_volume(0.3)
            cls.sounds[file] = sound

        sound = cls.sounds[file]
        if file not in cls.channels:
            channel = pygame.mixer.find_channel()
            if channel is None:
                return

            cls.channels[file] = channel

        channel = cls.channels[file]

        # prevent stacking same sound
        if not channel.get_busy():
            channel.play(sound)
