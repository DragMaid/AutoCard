from .death import DeathAnimation


class AnimationQueue:
    def __init__(self):
        self.queue = []

    def add(self, animation):
        if self.queue and isinstance(self.queue[-1], DeathAnimation):
            return
        self.queue.append(animation)

    def peek(self):
        return self.queue[0] if self.queue else None

    def pop(self):
        return self.queue.pop(0) if self.queue else None

    def __len__(self):
        return len(self.queue)
