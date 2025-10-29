import pygame
import math


class DragArrow:
    def __init__(self, color=(0, 255, 0), stripe_color=(0, 200, 0), stripe_width=5):
        self.start_pos = None
        self.end_pos = None
        self.dragging = False
        self.color = color
        self.stripe_color = stripe_color
        self.stripe_width = stripe_width
        self.targets = [None, None]

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION and self.dragging:
            self.end_pos = event.pos

        # elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            # self.dragging = False
            # self.end_pos = event.pos

    def draw(self, surface):
        if not self.start_pos or not self.end_pos:
            return

        if self.dragging:
            # Draw dashed / stripe line while dragging
            self.draw_stripe_line(
                surface, self.start_pos, self.end_pos, self.stripe_color, self.stripe_width)
        else:
            # Draw normal solid line when released
            pygame.draw.line(surface, self.color,
                             self.start_pos, self.end_pos, 3)

        # Draw arrowhead
        self.draw_arrowhead(surface, self.end_pos,
                            self.start_pos, 15, 7, self.color)

    @staticmethod
    def draw_stripe_line(surface, start, end, color, width):
        # Draw a dashed line as stripes
        total_length = math.hypot(end[0]-start[0], end[1]-start[1])
        if total_length <= 0:
            return
        dash_length = 10
        dx = (end[0]-start[0])/total_length
        dy = (end[1]-start[1])/total_length
        for i in range(0, int(total_length/dash_length), 2):
            x1 = start[0] + dx*i*dash_length
            y1 = start[1] + dy*i*dash_length
            x2 = start[0] + dx*(i+1)*dash_length
            y2 = start[1] + dy*(i+1)*dash_length
            pygame.draw.line(surface, color, (x1, y1), (x2, y2), width)

    @staticmethod
    def draw_arrowhead(surface, tip, tail, length=15, width=7, color=(0, 255, 0)):
        angle = math.atan2(tip[1]-tail[1], tip[0]-tail[0])
        left = (tip[0] - length*math.cos(angle) + width*math.sin(angle),
                tip[1] - length*math.sin(angle) - width*math.cos(angle))
        right = (tip[0] - length*math.cos(angle) - width*math.sin(angle),
                 tip[1] - length*math.sin(angle) + width*math.cos(angle))
        pygame.draw.polygon(surface, color, [tip, left, right])