import pygame
from pygame.draw import rect
from typing import Tuple
from gui.sprite import Sprite
from gui.draggable import Draggable
from gui.cache import get_font


class CardGUI(Sprite, Draggable):
    BASE_SIZE = (64, 81)

    def __init__(self,
                 logic_card,
                 pos: Tuple[float, float] = (0, 0),
                 size: Tuple[int, int] = None):
        if size is None:
            size = self.BASE_SIZE

        Sprite.__init__(self, pos=pos, size=size,
                        image_path=logic_card.image_path)
        Draggable.__init__(self, self.rect)
        self.logic_card = logic_card
        self.is_selected = False
        self.highlight = False
        self.highlight_color = (255, 255, 0)

        self.display_size = size
        self.scale_x = self.display_size[0] / self.BASE_SIZE[0]
        self.scale_y = self.display_size[1] / self.BASE_SIZE[1]

        # Fonts scaled according to card height
        self.name_font = get_font(max(8, int(14 * self.scale_y)))
        self.desc_font = get_font(max(6, int(12 * self.scale_y)))

        self.card_surface = None

        self.image_face_down = pygame.image.load("assets/card-back.png")
        self.is_face_down = False
        self.show_text = False
        self.flip = False

        # Animation attributes
        self.angle = 0
        self.scale_factor_x = 1.0
        self.scale_factor_y = 1.0
        self.alpha = 255
        self.offset_y = 0
        self._last_offset_y = 0

        self.annotated_image = self._render_card_with_text()
        self.update()

    def _render_card_with_text(self, padding=4):
        w, h = self.display_size
        # padding = h * padding
        annotated_image = pygame.transform.smoothscale(
            self.original_image, self.display_size).copy()

        # Textbox dimensions relative to card size
        textbox_width = int(w * 62 / self.BASE_SIZE[0])
        textbox_height = int(h * 17 / self.BASE_SIZE[1])
        textbox_bottom_offset = int(h * 4 / self.BASE_SIZE[1])
        textbox_x = (w - textbox_width) // 2
        textbox_y = h - textbox_height - textbox_bottom_offset
        textbox_rect = pygame.Rect(
            textbox_x, textbox_y, textbox_width, textbox_height
        )

        # Apply padding to description box
        inner_textbox = pygame.Rect(
            textbox_rect.left + padding,
            textbox_rect.top + padding,
            textbox_rect.width - 2 * padding,
            textbox_rect.height - 2 * padding,
        )

        # Draw description in padded textbox
        description = getattr(self.logic_card, "description", "")
        level_star = getattr(self.logic_card, "level_star", None)
        monster_type = getattr(self.logic_card, "type", None)

        if level_star and monster_type:
            description = (
                f"Type: {monster_type}\n"
                f"Level: {level_star}*\n"
                f"Description: {description}"
            )
        else:
            description = f"Description: {description}"
        if description:
            self._render_wrapped_text(annotated_image, description, inner_textbox)

        # Draw name above textbox (with horizontal padding)
        name = getattr(self.logic_card, "name", "Unknown")
        max_name_width = w - 2 * padding  # respect left/right padding
        name_font_size = max(6, int(14 * self.scale_y))
        font = get_font(name_font_size)
        name_surface = font.render(name, True, (255, 255, 255))

        # Dynamically shrink font if name too wide
        while name_surface.get_width() > max_name_width and font.get_height() > 6:
            name_font_size -= 1
            font = get_font(name_font_size)
            name_surface = font.render(name, True, (255, 255, 255))

        name_rect = name_surface.get_rect(
            centerx=w // 2, bottom=textbox_rect.top - padding
        )

        # Draw shadow for name
        shadow_surface = font.render(name, True, (0, 0, 0))
        shadow_rect = shadow_surface.get_rect(
            centerx=w // 2 + 1, bottom=name_rect.bottom + 1
        )
        annotated_image.blit(shadow_surface, shadow_rect)
        annotated_image.blit(name_surface, name_rect)
        return annotated_image

    def _render_wrapped_text(self, annotated_image, text, rect):
        """Render description inside textbox dynamically"""
        paragraphs = text.splitlines()
        font = self.desc_font
        # Function to wrap text for a given font

        def wrap_text_for_font(fnt):
            wrapped_lines = []
            for paragraph in paragraphs:
                words = paragraph.split(" ")
                current_line = []
                for word in words:
                    test_line = current_line + [word]
                    test_text = " ".join(test_line)
                    if fnt.size(test_text)[0] > rect.width:
                        if current_line:
                            wrapped_lines.append(" ".join(current_line))
                            current_line = [word]
                        else:
                            wrapped_lines.append(word)
                            current_line = []
                    else:
                        current_line = test_line
                if current_line:
                    wrapped_lines.append(" ".join(current_line))
            return wrapped_lines

        # Try shrinking font until it fits vertically
        while True:
            lines = wrap_text_for_font(font)
            line_height = font.get_height()
            max_lines = rect.height // line_height

            if len(lines) <= max_lines:
                break  # Fits within textbox
            font_size = font.get_height()
            if font_size <= 6:
                break  # Stop shrinking
            font = get_font(font_size - 1)

        # Draw text lines
        y_offset = rect.top
        for line in lines[:max_lines]:
            text_surface = font.render(line, True, (0, 0, 0))
            annotated_image.blit(text_surface, (rect.left + 1, y_offset))
            y_offset += font.get_height()

    def update(self):
        if self.logic_card.is_face_down:
            surface = pygame.transform.smoothscale(
                self.image_face_down, self.display_size
            )
        else:
            # use the already-rendered card with text
            surface = self.annotated_image.copy()

        if self.flip:
            surface = pygame.transform.flip(
                surface, False, True)

        # Apply animations
        if self.scale_factor_x != 1.0 or self.scale_factor_y != 1.0:
            new_w = int(self.display_size[0] * self.scale_factor_x)
            new_h = int(self.display_size[1] * self.scale_factor_y)
            surface = pygame.transform.smoothscale(surface, (new_w, new_h))

        if self.angle != 0:
            surface = pygame.transform.rotate(surface, -self.angle)

        if self.alpha != 255:
            surface.set_alpha(self.alpha)

        self.image = surface
        # Remove last offset from center to prevent accumulation
        cx, cy = self.rect.center
        cy -= self._last_offset_y
        self.rect = self.image.get_rect(center=(cx, cy))
        self.rect.y += self.offset_y
        self._last_offset_y = self.offset_y

        if self.is_selected:
            rect(self.image, self.highlight_color, self.image.get_rect(), 2)

    def draw(self, surface):
        self.update()
        surface.blit(self.image, self.rect)
        if self.highlight:
            pygame.draw.rect(surface, self.highlight_color, self.rect, 5)

    def on_drag_start(self):
        self.is_selected = True

    def on_drag(self, pos):
        self.rect.center = pos

    def on_drop(self, matrix, game_engine):
        cell = matrix.get_slot_at_pos(self.rect.center)
        success = False
        if cell and self.logic_card.owner_id:
            if game_engine.game_state.field_matrix_ownership[cell[0]][cell[1]] == self.logic_card.owner_id:
                success = game_engine.summon_card(
                    self.logic_card.owner_id, self.logic_card.id, cell)
                if success:
                    self.is_draggable = False
        self.is_selected = False
        return success
