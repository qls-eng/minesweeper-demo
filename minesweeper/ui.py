"""渲染 / 输入层（pygame）。

约定：
1. 所有图形都用 pygame 的基础几何图元绘制，仓库内不含任何外部图片素材，
   既避免版权问题，也让代码本身可读；
2. 本层只负责“把状态画出来”和“把操作转成 Game 的方法调用”，
   不参与任何规则判断（规则全在 core.py）。

操作说明：
    左键点击  翻开
    左键双击  在已翻开的数字格上和弦（周围旗数等于该数字时一次翻开其余邻格）
    右键点击  插旗 / 取消旗
    R        重开
    1 / 2 / 3 切换难度
    ESC      退出
"""

from __future__ import annotations

import random
import sys

import pygame

from . import theme
from .config import (
    COLS_RANGE,
    ROWS_RANGE,
    SAFE_ZONE_CELLS,
    LevelConfig,
    find_level,
    make_custom_level,
    validate_level,
)
from .core import CellState, GameStatus
from .game import Game


def _system_double_click_ms() -> int:
    """双击判定窗口跟随系统设置。

    Windows 默认是 500ms，写死 400ms 会让"稍慢一点的双击"被判成两次单击，
    表现就是"双击没反应"。取不到系统值（非 Windows / 调用失败）时退回 500ms。
    """
    try:
        import ctypes

        value = int(ctypes.windll.user32.GetDoubleClickTime())
        if 200 <= value <= 900:      # 合理区间，防止读到异常值
            return value
    except Exception:
        pass
    return 500


class App:
    FPS = 60
    RESTART_SIZE = (108, 34)
    DOUBLE_CLICK_MS = _system_double_click_ms()   # 双击判定窗口（毫秒，跟随系统）
    CHORD_HINT_MS = 180                           # 和弦条件不满足时的边框闪烁时长

    def __init__(
        self,
        levels: list[LevelConfig],
        level_key: str,
        seed: int | None = None,
        custom_level: LevelConfig | None = None,
    ) -> None:
        self._enable_dpi_awareness()

        pygame.init()
        self._fonts: dict[int, pygame.font.Font] = {}
        self._clock = pygame.time.Clock()
        self.levels = levels
        self.seed = seed
        self.hover: tuple[int, int] | None = None
        self._reset_click_state()

        # 自定义难度面板（F-17）
        self.custom_open = False
        self.custom_error = ""
        self.custom_index = 0
        self.custom_fields = ["", "", ""]     # 行 / 列 / 雷

        if custom_level is not None:
            self.level_index = -1
            self.custom_level = custom_level
            self._start_level(custom_level)
        else:
            self.custom_level = None
            self.level_index = levels.index(find_level(levels, level_key))
            self._start_level(self.levels[self.level_index])

    # ---------- 初始化辅助 ----------

    @staticmethod
    def _enable_dpi_awareness() -> None:
        """Windows 高分屏下避免窗口被系统拉伸导致模糊。"""
        if sys.platform == "win32":
            try:
                import ctypes

                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass

    def _load_level(self, index: int) -> None:
        """切到预设难度（1/2/3 键）。"""
        self.level_index = index
        self.custom_level = None
        self._start_level(self.levels[index])

    def _start_level(self, level: LevelConfig) -> None:
        self.game = Game(level, seed=self.seed)
        self.hover = None
        self._wrong_flags: set[tuple[int, int]] = set()
        self._hint: tuple[tuple[int, int], int, tuple[int, int, int]] | None = None  # (格, 到期, 颜色)
        self._reset_click_state()
        self._layout()
        self.screen = pygame.display.set_mode((self.width, self.height))
        pygame.display.set_caption(f"Minesweeper Demo - {level.name}")

    def _reset_click_state(self) -> None:
        """清空点击/按下状态（重开、切难度、双击消费后都要调，避免跨局误触发）。"""
        self._last_click_cell: tuple[int, int] | None = None
        self._last_click_time = -9999
        self.pressed_cell: tuple[int, int] | None = None

    def _layout(self) -> None:
        """按棋盘尺寸算出窗口几何，切难度时自动重算。

        自定义大盘面（比如 40×60）会超出屏幕，这里按格子数自动缩小单元格，
        保证窗口不会长到屏幕外；预设三档的格子尺寸仍是 CELL_SIZE。
        """
        level = self.game.level
        self.cell = min(
            theme.CELL_SIZE,
            theme.MAX_BOARD_W // level.cols,
            theme.MAX_BOARD_H // level.rows,
        )
        self.cell = max(self.cell, theme.MIN_CELL_SIZE)
        self.board_x = theme.MARGIN
        self.board_y = theme.MARGIN + theme.HUD_HEIGHT + theme.MARGIN
        self.board_w = level.cols * self.cell
        self.board_h = level.rows * self.cell
        self.width = self.board_w + theme.MARGIN * 2
        self.height = self.board_y + self.board_h + theme.MARGIN

        self.hud_rect = pygame.Rect(
            theme.MARGIN, theme.MARGIN, self.width - theme.MARGIN * 2, theme.HUD_HEIGHT
        )
        self.restart_rect = pygame.Rect((0, 0), self.RESTART_SIZE)
        self.restart_rect.center = (self.width // 2, theme.MARGIN + theme.HUD_HEIGHT // 2)

    # ---------- 自定义难度面板（F-17） ----------

    CUSTOM_LABELS = ("行", "列", "雷")

    def _open_custom_panel(self) -> None:
        """打开面板时用当前盘面回填，玩家改一两个数就行。"""
        level = self.game.level
        self.custom_fields = [str(level.rows), str(level.cols), str(level.mines)]
        self.custom_index = 0
        self.custom_error = ""
        self.custom_open = True

    def _close_custom_panel(self) -> None:
        self.custom_open = False
        self.custom_error = ""

    def _handle_custom_key(self, event: pygame.event.Event) -> bool:
        if event.key in (pygame.K_ESCAPE, pygame.K_c):
            self._close_custom_panel()
        elif event.key == pygame.K_RETURN:
            self._apply_custom()
        elif event.key in (pygame.K_TAB, pygame.K_UP, pygame.K_DOWN):
            step = -1 if event.key == pygame.K_UP else 1
            self.custom_index = (self.custom_index + step) % len(self.custom_fields)
        elif event.key == pygame.K_BACKSPACE:
            self.custom_fields[self.custom_index] = self.custom_fields[self.custom_index][:-1]
        elif pygame.K_0 <= event.key <= pygame.K_9:
            digit = str(event.key - pygame.K_0)
            current = self.custom_fields[self.custom_index]
            if len(current) < 3:
                merged = (current + digit).lstrip("0")
                self.custom_fields[self.custom_index] = merged or "0"
        return True

    def _apply_custom(self) -> None:
        """校验并应用自定义盘面；不合法只在面板上提示，不破坏当前这一局。"""
        try:
            rows, cols, mines = (int(field or 0) for field in self.custom_fields)
        except ValueError:
            self.custom_error = "三个字段都必须是数字"
            return

        errors = validate_level(rows, cols, mines)
        if errors:
            self.custom_error = errors[0]     # 面板只放得下一行，优先报第一条
            return

        level = make_custom_level(rows, cols, mines)
        self.custom_level = level
        self.level_index = -1
        self.custom_open = False
        self.custom_error = ""
        self._start_level(level)

    # ---------- 坐标换算 ----------

    def _cell_rect(self, row: int, col: int) -> pygame.Rect:
        return pygame.Rect(
            self.board_x + col * self.cell + 1,
            self.board_y + row * self.cell + 1,
            self.cell - 2,
            self.cell - 2,
        )

    def _cell_at(self, pos: tuple[int, int]) -> tuple[int, int] | None:
        x, y = pos
        if not (self.board_x <= x < self.board_x + self.board_w):
            return None
        if not (self.board_y <= y < self.board_y + self.board_h):
            return None
        return (y - self.board_y) // self.cell, (x - self.board_x) // self.cell

    # ---------- 事件 ----------

    def handle_event(self, event: pygame.event.Event) -> bool:
        """返回 False 表示要退出主循环。"""
        if event.type == pygame.QUIT:
            return False

        if event.type == pygame.KEYDOWN:
            if self.custom_open:
                return self._handle_custom_key(event)
            if event.key == pygame.K_ESCAPE:
                return False
            if event.key == pygame.K_r:
                self.game.restart()
                self._reset_click_state()
            elif event.key == pygame.K_c:
                self._open_custom_panel()
            elif pygame.K_1 <= event.key <= pygame.K_9:
                index = event.key - pygame.K_1
                if index < len(self.levels):
                    self._load_level(index)
            return True

        if event.type == pygame.MOUSEMOTION:
            self.hover = self._cell_at(event.pos)
            if self.pressed_cell is not None and self.hover != self.pressed_cell:
                self.pressed_cell = None   # 按下后拖出该格，松开时不翻（取消操作）
            return True

        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1 and self.restart_rect.collidepoint(event.pos):
                self.game.restart()
                self._reset_click_state()
                return True

            cell = self._cell_at(event.pos)
            if cell is None:
                return True

            if event.button == 1:
                # 只记录"按下"，真正翻开在松开时做（F-13）
                if self.game.status not in (GameStatus.WON, GameStatus.LOST):
                    self.pressed_cell = cell
            elif event.button == 3:
                self.game.toggle_flag(*cell)
            return True

        if event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1 and self.pressed_cell is not None:
                pressed = self.pressed_cell
                self.pressed_cell = None
                cell = self._cell_at(event.pos)
                if cell is not None and cell == pressed:
                    self._on_left_click(cell)
            return True
        return True

    def _on_left_click(self, cell: tuple[int, int]) -> None:
        """左键：覆盖格直接翻开；已翻开的数字格双击触发和弦（F-12）。

        双击判定只在"点击前就已经是已翻开状态"的格子上生效，
        避免刚翻开的格子被连点误判成和弦。
        """
        row, col = cell
        state = self.game.board.cells[row][col].state

        if state is not CellState.REVEALED:
            self._last_click_cell = None
            self.game.reveal(row, col)
            return

        now = pygame.time.get_ticks()
        is_double_click = (
            self._last_click_cell == cell
            and now - self._last_click_time <= self.DOUBLE_CLICK_MS
        )
        if is_double_click:
            self._reset_click_state()   # 只消费一次，三连击不会连续和弦
            if not self.game.chord(row, col):
                # 和弦条件不满足，先试"自动插旗"（F-16）：
                # 周围未翻开格数正好等于数字时，它们必然是雷，直接标上
                if self.game.auto_flag(row, col):
                    self._set_hint(cell, theme.WON_GREEN)    # 绿框＝已自动插旗
                else:
                    # 都推不出来：红框提示"双击被识别了，只是条件不够"（F-15）
                    self._set_hint(cell, theme.FLAG_RED)
        else:
            self._last_click_cell = cell
            self._last_click_time = now

    def _set_hint(self, cell: tuple[int, int], color: tuple[int, int, int]) -> None:
        """给某格挂一个短暂的高亮边框（自动插旗 / 条件不足的反馈）。"""
        self._hint: tuple[tuple[int, int], int, tuple[int, int, int]] | None = (
            cell,
            pygame.time.get_ticks() + self.CHORD_HINT_MS,
            color,
        )

    # ---------- 绘制 ----------

    def draw(self) -> None:
        self.screen.fill(theme.BG)
        # 错旗只在失败时算一次，避免逐格重复判断
        self._wrong_flags = (
            set(self.game.board.wrong_flags())
            if self.game.status is GameStatus.LOST
            else set()
        )
        self._draw_board()
        self._draw_hud()
        if self.game.status is GameStatus.LOST:
            self._draw_banner(won=False)
        elif self.game.status is GameStatus.WON:
            self._draw_banner(won=True)
        if self.custom_open:
            self._draw_custom_panel()
        pygame.display.flip()

    def _draw_board(self) -> None:
        for row in range(self.game.level.rows):
            for col in range(self.game.level.cols):
                self._draw_cell(row, col)

    def _draw_cell(self, row: int, col: int) -> None:
        rect = self._cell_rect(row, col)
        cell = self.game.board.cells[row][col]

        if cell.state is CellState.REVEALED:
            pygame.draw.rect(self.screen, theme.CELL_OPEN, rect)
            pygame.draw.rect(self.screen, theme.CELL_OPEN_EDGE, rect, width=1)
            if cell.has_mine:
                self._draw_mine(rect.center)
            elif cell.adjacent > 0:
                color = theme.NUMBER_COLORS.get(cell.adjacent, theme.TEXT)
                self._text(str(cell.adjacent), int(self.cell * 0.62), color, rect.center)
            # 和弦条件不满足时闪一下边框（F-15），提示"双击被识别了，只是旗数不够"
            if (
                self._hint is not None
                and self._hint[0] == (row, col)
                and pygame.time.get_ticks() < self._hint[1]
            ):
                pygame.draw.rect(self.screen, self._hint[2], rect, width=2)
            return

        pressed = self.pressed_cell == (row, col)
        if pressed:
            # 反转立体：上/左投影、下/右高光，视觉上"按下去"（F-13）
            pygame.draw.rect(self.screen, theme.CELL_COVERED_SHADOW, rect)
            pygame.draw.line(self.screen, theme.CELL_COVERED_SHADOW, rect.topleft, rect.topright)
            pygame.draw.line(self.screen, theme.CELL_COVERED_SHADOW, rect.topleft, rect.bottomleft)
            pygame.draw.line(self.screen, theme.CELL_COVERED_LIGHT, rect.bottomleft, rect.bottomright)
            pygame.draw.line(self.screen, theme.CELL_COVERED_LIGHT, rect.topright, rect.bottomright)
        else:
            hovered = self.hover == (row, col)
            base = theme.CELL_COVERED_HOVER if hovered else theme.CELL_COVERED
            pygame.draw.rect(self.screen, base, rect)
            # 上/左高光 + 下/右投影，做出微微凸起的手感，不需要任何贴图
            pygame.draw.line(self.screen, theme.CELL_COVERED_LIGHT, rect.topleft, rect.topright)
            pygame.draw.line(self.screen, theme.CELL_COVERED_LIGHT, rect.topleft, rect.bottomleft)
            pygame.draw.line(self.screen, theme.CELL_COVERED_SHADOW, rect.bottomleft, rect.bottomright)
            pygame.draw.line(self.screen, theme.CELL_COVERED_SHADOW, rect.topright, rect.bottomright)

        if cell.state is CellState.FLAGGED or (
            self.game.status is GameStatus.WON and cell.has_mine
        ):
            # 胜利时把没插旗的雷也画成旗子，避免终局画面留一堆灰块像没玩完
            self._draw_flag(rect)
            if (row, col) in self._wrong_flags:
                self._draw_cross(rect)   # 失败的错旗（F-14）

    def _draw_cross(self, rect: pygame.Rect) -> None:
        inset = int(rect.width * 0.12)
        pygame.draw.line(
            self.screen,
            theme.LOST_RED,
            (rect.left + inset, rect.top + inset),
            (rect.right - inset, rect.bottom - inset),
            3,
        )
        pygame.draw.line(
            self.screen,
            theme.LOST_RED,
            (rect.right - inset, rect.top + inset),
            (rect.left + inset, rect.bottom - inset),
            3,
        )

    def _draw_flag(self, rect: pygame.Rect) -> None:
        scale = self.cell / 34.0
        cx, cy = rect.center
        pole_x = cx + int(3 * scale)
        top = cy - int(9 * scale)
        bottom = cy + int(10 * scale)

        pygame.draw.line(self.screen, theme.TEXT_DIM, (pole_x, top), (pole_x, bottom), 2)
        pygame.draw.line(
            self.screen,
            theme.TEXT_DIM,
            (pole_x - int(6 * scale), bottom),
            (pole_x + int(6 * scale), bottom),
            2,
        )
        triangle = [
            (pole_x, top),
            (pole_x - int(11 * scale), top + int(5 * scale)),
            (pole_x, top + int(10 * scale)),
        ]
        pygame.draw.polygon(self.screen, theme.FLAG_RED, triangle)

    def _draw_mine(self, center: tuple[int, int]) -> None:
        radius = max(4, self.cell // 6)
        pygame.draw.circle(self.screen, theme.MINE_RED, center, radius)
        # 八向短刺，一眼能看出是雷
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
            start = (center[0] + dx * radius, center[1] + dy * radius)
            end = (center[0] + dx * (radius + 4), center[1] + dy * (radius + 4))
            pygame.draw.line(self.screen, theme.MINE_RED, start, end, 2)

    def _draw_hud(self) -> None:
        pygame.draw.rect(self.screen, theme.PANEL, self.hud_rect, border_radius=10)
        pygame.draw.rect(self.screen, theme.PANEL_EDGE, self.hud_rect, width=1, border_radius=10)

        center_y = self.hud_rect.centery
        left_x = self.hud_rect.x + 64
        self._text("MINES", 15, theme.TEXT_DIM, (left_x, center_y - 14))
        self._text(str(self.game.mines_left), 24, theme.TEXT, (left_x, center_y + 9))

        right_x = self.hud_rect.right - 64
        self._text("TIME", 15, theme.TEXT_DIM, (right_x, center_y - 14))
        self._text(self.game.elapsed_text, 24, theme.TEXT, (right_x, center_y + 9))

        status = self.game.status
        edge = theme.ACCENT
        label = "RESTART"
        if status is GameStatus.WON:
            edge, label = theme.WON_GREEN, "WIN"
        elif status is GameStatus.LOST:
            edge, label = theme.LOST_RED, "BOOM"

        button = self.restart_rect
        pygame.draw.rect(self.screen, theme.BG, button, border_radius=8)
        pygame.draw.rect(self.screen, edge, button, width=1, border_radius=8)
        self._text(label, 18, edge, button.center)

    def _draw_banner(self, won: bool) -> None:
        """终局提示：整体只做轻微蒙层，正文放居中卡片里。

        不用大面积遮挡，是为了让玩家失败后仍能看清雷的位置与数字，方便复盘。
        """
        area = pygame.Rect(self.board_x, self.board_y, self.board_w, self.board_h)
        overlay = pygame.Surface(area.size, pygame.SRCALPHA)
        overlay.fill((255, 255, 255, 96))
        self.screen.blit(overlay, area.topleft)

        color = theme.WON_GREEN if won else theme.LOST_RED
        card = pygame.Rect(0, 0, min(int(self.board_w * 0.88), 310), 152)
        card.center = area.center
        pygame.draw.rect(self.screen, theme.PANEL, card, border_radius=14)
        pygame.draw.rect(self.screen, color, card, width=2, border_radius=14)

        title = "YOU WIN" if won else "BOOM"
        self._text(title, 44, color, (card.centerx, card.y + 48))
        self._text(
            f"{self.game.level.name}   {self.game.elapsed_text}",
            20,
            theme.TEXT_DIM,
            (card.centerx, card.y + 90),
        )
        self._text("press R to restart", 18, theme.TEXT_DIM, (card.centerx, card.y + 120))

    def _draw_custom_panel(self) -> None:
        """自定义难度面板：轻蒙层 + 居中卡片，三个数字框，当前字段高亮。"""
        area = pygame.Rect(self.board_x, self.board_y, self.board_w, self.board_h)
        veil = pygame.Surface(area.size, pygame.SRCALPHA)
        veil.fill((255, 255, 255, 120))
        self.screen.blit(veil, area.topleft)

        # 卡片宽度同时受窗口和盘面约束：5×5 这种小盘面也不能让卡片露出窗口
        card_w = min(340, self.width - 24)
        card = pygame.Rect(0, 0, card_w, 190)
        card.center = area.center
        pygame.draw.rect(self.screen, theme.PANEL, card, border_radius=14)
        pygame.draw.rect(self.screen, theme.ACCENT, card, width=2, border_radius=14)

        self._text("自定义难度", 30, theme.TEXT, (card.centerx, card.y + 28))
        hint_size = 16 if card_w >= 300 else 13

        for index, label in enumerate(self.CUSTOM_LABELS):
            row_y = card.y + 66 + index * 30
            self._text(label, 20, theme.TEXT_DIM, (card.x + 34, row_y))
            box = pygame.Rect(0, 0, 96, 26)
            box.left = card.x + 62
            box.centery = row_y
            active = index == self.custom_index
            pygame.draw.rect(self.screen, theme.CELL_OPEN, box, border_radius=6)
            pygame.draw.rect(
                self.screen,
                theme.ACCENT if active else theme.PANEL_EDGE,
                box,
                width=2 if active else 1,
                border_radius=6,
            )
            self._text(self.custom_fields[index] or "—", 20, theme.TEXT, box.center)

        if self.custom_error:
            self._text(self.custom_error, hint_size, theme.LOST_RED, (card.centerx, card.y + 148))
        else:
            self._text("Tab 切换 · Enter 应用", hint_size, theme.TEXT_DIM, (card.centerx, card.y + 148))
        self._text(
            f"行 {ROWS_RANGE[0]}-{ROWS_RANGE[1]} 列 {COLS_RANGE[0]}-{COLS_RANGE[1]} 雷 1~行×列-{SAFE_ZONE_CELLS}",
            max(11, hint_size - 2),
            theme.TEXT_DIM,
            (card.centerx, card.y + 172),
        )

    # ---------- 文本 ----------
    def _font(self, size: int) -> pygame.font.Font:
        if size not in self._fonts:
            self._fonts[size] = pygame.font.Font(None, size)
        return self._fonts[size]

    def _text(
        self,
        text: str,
        size: int,
        color: tuple[int, int, int],
        center: tuple[int, int],
    ) -> None:
        surface = self._font(size).render(text, True, color)
        self.screen.blit(surface, surface.get_rect(center=center))

    # ---------- 主循环 ----------

    def run(self) -> None:
        running = True
        while running:
            for event in pygame.event.get():
                running = self.handle_event(event)
                if not running:
                    break
            self.draw()
            self._clock.tick(self.FPS)
        pygame.quit()

    # ---------- 无窗口自检 ----------

    def smoke(self, shot_path=None, seed: int = 7) -> str:
        """不开窗口跑一遍渲染：用于 CI / 交付前自检，顺带产出 README 预览图。"""
        assert self.screen is not None, "screen 未初始化"
        rng = random.Random(seed)
        level = self.game.level

        self.game.reveal(level.rows // 2, level.cols // 2)

        board = self.game.board
        safe = [
            (r, c)
            for r in range(level.rows)
            for c in range(level.cols)
            if board.cells[r][c].state is CellState.HIDDEN and not board.cells[r][c].has_mine
        ]
        for r, c in rng.sample(safe, min(4, len(safe))):
            self.game.reveal(r, c)

        hidden = [
            (r, c)
            for r in range(level.rows)
            for c in range(level.cols)
            if board.cells[r][c].state is CellState.HIDDEN
        ]
        for r, c in hidden[:2]:
            self.game.toggle_flag(r, c)

        self.draw()
        if shot_path is not None:
            pygame.image.save(self.screen, str(shot_path))
        status = self.game.status.value
        pygame.quit()
        return status
