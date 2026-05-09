class Animation:
    def __init__(self, locks, duration):
        self.locks = locks  # set of sprites this animation controls
        self.duration = duration
        self.elapsed = 0
        self.is_finished = False

    def update(self, dt):
        self.elapsed += dt
        if self.duration <= 0:
            t = 1.0
        else:
            t = min(self.elapsed / self.duration, 1.0)
        self._apply(t)
        if t >= 1.0:
            self.is_finished = True
        return self.is_finished

    def _apply(self, t):
        raise NotImplementedError
