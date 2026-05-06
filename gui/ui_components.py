import pygame
from gui.cache import get_font


class UIComponent:
    def __init__(self, rect):
        self.rect = pygame.Rect(rect)
        self.is_hovered = False
        self.is_focused = False

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.is_hovered = self.rect.collidepoint(event.pos)

        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                self.is_focused = self.rect.collidepoint(event.pos)
        return False

    def update(self, dt):
        pass

    def draw(self, screen):
        pass


class Button(UIComponent):
    def __init__(self, rect, text, font_size=32, color=(50, 50, 50), hover_color=(80, 80, 80), text_color=(255, 255, 255), callback=None):
        super().__init__(rect)
        self.text = text
        self.font = get_font(font_size)
        self.color = color
        self.hover_color = hover_color
        self.text_color = text_color
        self.callback = callback

    def handle_event(self, event):
        super().handle_event(event)
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1 and self.is_hovered:
                if self.callback:
                    self.callback()
                return True
        return False

    def draw(self, screen):
        color = self.hover_color if self.is_hovered else self.color
        pygame.draw.rect(screen, color, self.rect, border_radius=5)
        pygame.draw.rect(screen, (200, 200, 200),
                         self.rect, 2, border_radius=5)

        text_surf = self.font.render(self.text, True, self.text_color)
        text_rect = text_surf.get_rect(center=self.rect.center)
        screen.blit(text_surf, text_rect)


class InputBox(UIComponent):
    def __init__(self, rect, text='', placeholder='', font_size=32, numeric=False):
        super().__init__(rect)
        self.text = text
        self.placeholder = placeholder
        self.font = get_font(font_size)
        self.numeric = numeric
        self.color = (40, 40, 40)
        self.border_color = (100, 100, 100)
        self.focus_color = (50, 150, 250)
        self.cursor_visible = True
        self.cursor_timer = 0

    def handle_event(self, event):
        super().handle_event(event)
        if self.is_focused:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_BACKSPACE:
                    self.text = self.text[:-1]
                elif event.key == pygame.K_RETURN:
                    self.is_focused = False
                else:
                    if self.numeric:
                        if event.unicode.isdigit():
                            self.text += event.unicode
                    else:
                        self.text += event.unicode
                return True
        return False

    def update(self, dt):
        if self.is_focused:
            self.cursor_timer += dt
            if self.cursor_timer >= 0.5:
                self.cursor_visible = not self.cursor_visible
                self.cursor_timer = 0
        else:
            self.cursor_visible = False

    def draw(self, screen):
        pygame.draw.rect(screen, self.color, self.rect, border_radius=5)
        border_color = self.focus_color if self.is_focused else self.border_color
        pygame.draw.rect(screen, border_color, self.rect, 2, border_radius=5)

        display_text = self.text
        if self.cursor_visible:
            display_text += '|'

        if not display_text and not self.is_focused:
            text_surf = self.font.render(
                self.placeholder, True, (120, 120, 120))
        else:
            text_surf = self.font.render(display_text, True, (255, 255, 255))

        # Clipping: if text is wider than box, only show the end
        text_rect = text_surf.get_rect(
            midleft=(self.rect.left + 10, self.rect.centery))

        if text_rect.width > self.rect.width - 20:
            # Create a subsurface for clipping
            clip_rect = pygame.Rect(
                0, 0, self.rect.width - 20, self.rect.height)
            temp_surf = pygame.Surface(
                (text_rect.width, text_rect.height), pygame.SRCALPHA)
            temp_surf.blit(text_surf, (0, 0))

            # Draw only the rightmost part of the text
            crop_rect = pygame.Rect(
                text_rect.width - (self.rect.width - 20), 0, self.rect.width - 20, text_rect.height)
            screen.blit(temp_surf, (self.rect.left + 10,
                        self.rect.centery - text_rect.height // 2), crop_rect)
        else:
            screen.blit(text_surf, text_rect)


class ScrollList(UIComponent):
    def __init__(self, rect, items, item_height=50):
        super().__init__(rect)
        # List of dicts: {'name': str, 'password': bool, 'data': any}
        self.items = items
        self.item_height = item_height
        self.scroll_y = 0
        self.selected_index = -1
        self.font = get_font(28)
        self.item_color = (45, 45, 45)
        self.selected_color = (60, 100, 150)
        self.hover_index = -1

    def handle_event(self, event):
        super().handle_event(event)
        if event.type == pygame.MOUSEWHEEL:
            if self.rect.collidepoint(pygame.mouse.get_pos()):
                self.scroll_y += event.y * 20
                # Limit scrolling
                max_scroll = max(0, len(self.items) *
                                 self.item_height - self.rect.height)
                self.scroll_y = max(-max_scroll, min(0, self.scroll_y))
                return True

        if event.type == pygame.MOUSEMOTION:
            if self.rect.collidepoint(event.pos):
                rel_y = event.pos[1] - self.rect.top - self.scroll_y
                self.hover_index = int(rel_y // self.item_height)
                if self.hover_index < 0 or self.hover_index >= len(self.items):
                    self.hover_index = -1
            else:
                self.hover_index = -1

        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1 and self.hover_index != -1:
                self.selected_index = self.hover_index
                return True
        return False

    def draw(self, screen):
        pygame.draw.rect(screen, (35, 35, 35), self.rect, border_radius=5)
        pygame.draw.rect(screen, (80, 80, 80), self.rect, 2, border_radius=5)

        # Create a surface for the list to handle clipping
        list_surf = pygame.Surface((self.rect.width - 4, self.rect.height - 4))
        list_surf.fill((35, 35, 35))

        for i, item in enumerate(self.items):
            item_rect = pygame.Rect(
                0, i * self.item_height + self.scroll_y, self.rect.width - 4, self.item_height)

            # Optimization: only draw visible items
            if item_rect.bottom < 0 or item_rect.top > self.rect.height:
                continue

            color = self.item_color
            if i == self.selected_index:
                color = self.selected_color
            elif i == self.hover_index:
                color = (55, 55, 55)

            pygame.draw.rect(list_surf, color, item_rect)
            pygame.draw.line(list_surf, (60, 60, 60),
                             item_rect.bottomleft, item_rect.bottomright)

            # Draw item content
            name_surf = self.font.render(item['name'], True, (255, 255, 255))
            list_surf.blit(name_surf, (item_rect.left + 10,
                           item_rect.centery - name_surf.get_height() // 2))

            if item.get('password'):
                lock_surf = self.font.render("[LOCKED]", True, (200, 150, 50))
                list_surf.blit(lock_surf, (item_rect.right - 110,
                               item_rect.centery - lock_surf.get_height() // 2))

        screen.blit(list_surf, (self.rect.left + 2, self.rect.top + 2))
