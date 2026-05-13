import pygame


class Draggable:
    def __init__(self, dst: pygame.Rect, is_draggable: bool = True):
        self.dst = dst
        self.is_draggable = is_draggable
        self.is_dragging = False
        self.is_dropped = False
        self._dx = 0
        self._dy = 0

    def start_drag(self, mouse_pos):
        """Called by InputManager when drag begins."""
        if self.is_draggable:
            self.is_dragging = True
            self.is_dropped = False
            self._dx = self.dst.x - mouse_pos[0]
            self._dy = self.dst.y - mouse_pos[1]

    def update_drag(self, mouse_pos):
        """Called while dragging."""
        if self.is_dragging:
            self.dst.x = mouse_pos[0] + self._dx
            self.dst.y = mouse_pos[1] + self._dy

    def stop_drag(self):
        """Called by InputManager when drag ends."""
        if self.is_dragging:
            self.is_dragging = False
            self.is_dropped = True
