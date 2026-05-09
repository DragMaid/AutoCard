import pygame
import math


class DragArrow:
    def __init__(self, color=(0, 255, 0), width=5):
        self.start_pos = None
        self.end_pos = None
        self.dragging = False
        self.color = color
        self.width = width
        self.targets = [None, None]

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION and self.dragging:
            self.end_pos = event.pos

    def draw(self, surface):
        if not self.start_pos or not self.end_pos:
            return
        self.draw_stripe_curve(
            surface, self.start_pos, self.end_pos, self.color, self.width)
        self.draw_arrowhead(
            surface, self.end_pos, self.start_pos, 15, 7, self.color)

    @staticmethod
    def draw_stripe_curve(surface, start, end, color, width, height=80):
        """
        Draw a dashed curved arrow/parabola between start and end.

        Args:
            surface: pygame surface
            start: (x, y)
            end: (x, y)
            color: line color
            width: line width
            height: curve height (positive = upward arc)
        """
        # Number of samples along the curve
        steps = 60
        dash_skip = 2  # every other segment becomes a gap

        sx, sy = start
        ex, ey = end

        # Midpoint
        mx = (sx + ex) / 2
        my = (sy + ey) / 2

        # Perpendicular direction for curve offset
        dx = ex - sx
        dy = ey - sy
        length = math.hypot(dx, dy)

        if length == 0:
            return

        # Normalize perpendicular vector
        px = -dy / length
        py = dx / length

        # Control point for quadratic Bézier
        cx = mx + px * height
        cy = my + py * height

        def bezier(t):
            """Quadratic Bézier point."""
            x = (1 - t) ** 2 * sx + 2 * (1 - t) * t * cx + t ** 2 * ex
            y = (1 - t) ** 2 * sy + 2 * (1 - t) * t * cy + t ** 2 * ey
            return x, y

        # Generate curve points
        points = [bezier(i / steps) for i in range(steps + 1)]

        # Draw dashed curve
        for i in range(0, len(points) - 1, dash_skip):
            if i + 1 < len(points):
                pygame.draw.line(
                    surface, color, points[i], points[i + 1], width)

    @staticmethod
    def draw_arrowhead(surface, tip, tail, length=15, width=7, color=(0, 255, 0)):
        angle = math.atan2(tip[1]-tail[1], tip[0]-tail[0])
        left = (tip[0] - length*math.cos(angle) + width*math.sin(angle),
                tip[1] - length*math.sin(angle) - width*math.cos(angle))
        right = (tip[0] - length*math.cos(angle) - width*math.sin(angle),
                 tip[1] - length*math.sin(angle) + width*math.cos(angle))
        pygame.draw.polygon(surface, color, [tip, left, right])
