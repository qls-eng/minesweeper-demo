"""UI 层黑盒测试：只通过"事件 + 观察结果"驱动，不直接改内部状态。

原则：模拟真实玩家能做到的操作（按下、松开、拖出、右键、双击、按键），
然后检查棋盘状态、窗口几何、像素颜色这些"玩家能看到的东西"。
测试跑在 dummy 视频驱动上，不需要真的弹窗。
"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from minesweeper import theme
from minesweeper.config import LevelConfig, make_custom_level, load_levels
from minesweeper.core import CellState, GameStatus
from minesweeper.ui import App


def key(code: int) -> pygame.event.Event:
    return pygame.event.Event(pygame.KEYDOWN, {"key": code, "unicode": "", "mod": 0})


def down(pos, button: int = 1) -> pygame.event.Event:
    return pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": pos, "button": button})


def up(pos, button: int = 1) -> pygame.event.Event:
    return pygame.event.Event(pygame.MOUSEBUTTONUP, {"pos": pos, "button": button})


def motion(pos) -> pygame.event.Event:
    return pygame.event.Event(pygame.MOUSEMOTION, {"pos": pos, "rel": (0, 0), "buttons": (1, 0, 0)})


class UITestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pygame.init()

    @classmethod
    def tearDownClass(cls) -> None:
        pygame.quit()

    def make_app(self, level: str = "beginner", seed: int = 42, **kwargs) -> App:
        return App(load_levels(), level, seed=seed, **kwargs)

    # ---------- 操作封装（等价于玩家动手） ----------

    def click(self, app: App, cell: tuple[int, int], button: int = 1) -> None:
        pos = app._cell_rect(*cell).center
        app.handle_event(down(pos, button))
        app.handle_event(up(pos, button))

    def double_click(self, app: App, cell: tuple[int, int]) -> None:
        """两次完整的按下/松开；靠 pygame 时间戳判定成双击。"""
        self.click(app, cell)
        self.click(app, cell)

    def press_enter(self, app: App) -> None:
        app.handle_event(key(pygame.K_RETURN))

    def type_number(self, app: App, digits: str) -> None:
        for _ in range(4):
            app.handle_event(key(pygame.K_BACKSPACE))
        for ch in digits:
            app.handle_event(key(pygame.K_0 + int(ch)))

    # ---------- 观察封装 ----------

    def flags(self, app: App) -> list[tuple[int, int]]:
        board = app.game.board
        return [
            (r, c)
            for r in range(board.rows)
            for c in range(board.cols)
            if board.cells[r][c].state is CellState.FLAGGED
        ]

    def revealed_count(self, app: App) -> int:
        board = app.game.board
        return sum(
            1
            for r in range(board.rows)
            for c in range(board.cols)
            if board.cells[r][c].state is CellState.REVEALED
        )

    def find_revealed_number(self, app: App, minimum: int = 1) -> tuple[int, int]:
        board = app.game.board
        for r in range(board.rows):
            for c in range(board.cols):
                cell = board.cells[r][c]
                if (
                    cell.state is CellState.REVEALED
                    and not cell.has_mine
                    and cell.adjacent >= minimum
                ):
                    return (r, c)
        raise AssertionError("局面里没有已翻开的数字格，用例前提不成立")


class LayoutTest(UITestBase):
    """窗口几何：三档预设用固定格子尺寸，自定义大盘面自动缩小。"""

    def test_preset_levels_use_default_cell_size(self):
        for level_key in ("beginner", "intermediate", "expert"):
            app = self.make_app(level_key)
            self.assertEqual(app.cell, theme.CELL_SIZE, level_key)
            self.assertEqual(app.width, app.board_w + theme.MARGIN * 2, level_key)
            self.assertEqual(
                app.height,
                app.board_y + app.board_h + theme.MARGIN,
                level_key,
            )

    def test_custom_board_shrinks_cell_to_fit(self):
        level = make_custom_level(40, 60, 200)
        app = self.make_app(custom_level=level)
        self.assertEqual(app.game.level.name, "Custom 60×40")
        self.assertLess(app.cell, theme.CELL_SIZE)
        self.assertGreaterEqual(app.cell, theme.MIN_CELL_SIZE)
        self.assertLessEqual(app.board_w, theme.MAX_BOARD_W)
        self.assertLessEqual(app.board_h, theme.MAX_BOARD_H)
        self.assertEqual(app.width, app.board_w + theme.MARGIN * 2)

    def test_cells_tile_board_without_gaps(self):
        app = self.make_app("intermediate")
        last = app._cell_rect(app.game.level.rows - 1, app.game.level.cols - 1)
        self.assertEqual(last.right, app.board_x + app.board_w - 1)
        self.assertEqual(last.bottom, app.board_y + app.board_h - 1)


class ClickSemanticsTest(UITestBase):
    """按下/松开/拖出：F-13 定义的行为。"""

    def test_click_reveals_covered_cell(self):
        app = self.make_app()
        before = self.revealed_count(app)
        self.click(app, (4, 4))
        self.assertGreater(self.revealed_count(app), before)
        self.assertIs(app.game.status, GameStatus.PLAYING)

    def test_drag_off_cell_cancels_reveal(self):
        app = self.make_app()
        start = app._cell_rect(0, 0).center
        app.handle_event(down(start))
        app.handle_event(motion(app._cell_rect(1, 1).center))   # 拖出该格
        app.handle_event(up(app._cell_rect(1, 1).center))
        self.assertEqual(self.revealed_count(app), 0, "拖出后松开不应翻开任何格")

    def test_right_click_toggles_flag_only_on_covered(self):
        app = self.make_app()
        self.click(app, (4, 4), button=3)
        self.assertEqual(self.flags(app), [(4, 4)])
        self.click(app, (4, 4), button=3)
        self.assertEqual(self.flags(app), [])

        app.handle_event(key(pygame.K_r))
        covered = (4, 4)
        self.click(app, covered)                     # 翻开（一定是安全区中心）
        self.assertEqual(self.flags(app), [])
        self.click(app, covered, button=3)           # 已翻开格上右键无效
        self.assertEqual(self.flags(app), [])

    def test_left_click_on_revealed_cell_does_nothing(self):
        app = self.make_app()
        self.click(app, (4, 4))
        before = self.revealed_count(app)
        self.click(app, (4, 4))
        self.assertEqual(self.revealed_count(app), before)
        self.assertEqual(self.flags(app), [])


class DoubleClickTest(UITestBase):
    """双击：和弦 / 自动插旗 / 提示 三级顺序，以及时效判定。"""

    def _reveal_then_double(self, app: App, cell: tuple[int, int]) -> None:
        self.click(app, cell)          # 第一次是翻开
        self.click(app, cell)          # 第二次落在"刚好翻开"的格上，不算双击
        app.draw()

    def test_fresh_reveal_does_not_trigger_double_click_action(self):
        app = self.make_app()
        cell = (4, 4)
        self.click(app, cell)
        self.click(app, cell)
        self.assertEqual(self.flags(app), [], "刚翻开的格子不该被当成双击而自动插旗")
        self.assertIsNone(app._hint, "刚翻开的格子也不该闪提示框")

    def test_slow_second_click_is_not_double_click(self):
        app = self.make_app()
        self.click(app, (4, 4))                      # 先翻开一片，才有数字格可点
        cell = self.find_revealed_number(app, minimum=1)
        self.click(app, cell)
        app._last_click_time -= App.DOUBLE_CLICK_MS + 50    # 把上次点击推到很久以前
        before = self.revealed_count(app)
        self.click(app, cell)
        self.assertEqual(self.revealed_count(app), before)
        self.assertEqual(self.flags(app), [])
        self.assertIsNone(app._hint)

    def test_double_click_chord_reveals_neighbours_when_flags_match(self):
        app = self.make_app()
        self.click(app, (4, 4))
        cell = self.find_revealed_number(app, minimum=1)
        board = app.game.board
        mines = [n for n in board.neighbors(*cell) if board.cells[n[0]][n[1]].has_mine]
        self.assertTrue(mines, "用例前提：该数字格周围应有雷")
        for mine in mines:
            self.click(app, mine, button=3)          # 用右键把雷标出来
        # 只要是靠右键标旗，可见状态里不会自己变成双击
        app._reset_click_state()
        before = self.revealed_count(app)
        self.double_click(app, cell)
        self.assertGreater(self.revealed_count(app), before, "和弦应翻开其余邻格")

    def test_double_click_on_covered_cell_reveals_instead_of_flagging(self):
        app = self.make_app()
        cell = (4, 4)
        self.double_click(app, cell)
        self.assertEqual(self.flags(app), [])
        self.assertIs(app.game.status, GameStatus.PLAYING)


class KeyboardTest(UITestBase):
    """键盘：重开、切难度、面板开关、Esc 的两种含义。"""

    def test_r_restarts_and_clears_marks(self):
        app = self.make_app()
        self.click(app, (2, 2), button=3)
        self.assertEqual(len(self.flags(app)), 1)
        app.handle_event(key(pygame.K_r))
        self.assertEqual(self.flags(app), [])
        self.assertEqual(self.revealed_count(app), 0)
        self.assertIsNone(app._hint)
        self.assertEqual(app.game.elapsed_text, "00:00")

    def test_number_keys_switch_level(self):
        app = self.make_app("beginner")
        app.handle_event(key(pygame.K_2))
        self.assertEqual(app.game.level.key, "intermediate")
        self.assertEqual(app.game.level.rows, 16)
        app.handle_event(key(pygame.K_3))
        self.assertEqual(app.game.level.key, "expert")
        self.assertEqual(app.game.level.cols, 30)

    def test_escape_exits_only_when_panel_closed(self):
        app = self.make_app()
        app.handle_event(key(pygame.K_c))
        self.assertTrue(app.custom_open)
        self.assertTrue(app.handle_event(key(pygame.K_ESCAPE)), "面板打开时 Esc 只关面板")
        self.assertFalse(app.custom_open)
        self.assertFalse(app.handle_event(key(pygame.K_ESCAPE)), "面板关闭后 Esc 才是退出")

    def test_keys_are_swallowed_while_panel_open(self):
        app = self.make_app()
        app.handle_event(key(pygame.K_c))
        before_level = app.game.level.key
        app.handle_event(key(pygame.K_r))
        app.handle_event(key(pygame.K_2))
        self.assertEqual(app.game.level.key, before_level)
        self.assertTrue(app.custom_open, "游戏按键不应关掉面板")

    def test_mouse_is_ignored_while_panel_open(self):
        app = self.make_app()
        app.handle_event(key(pygame.K_c))
        self.click(app, (4, 4), button=3)      # 面板打开时点/右键都不该动棋盘
        self.assertEqual(self.flags(app), [])
        self.assertEqual(self.revealed_count(app), 0)


class CustomPanelTest(UITestBase):
    """自定义难度面板：预填、校验、应用、取消。"""

    def test_panel_prefills_current_level(self):
        app = self.make_app("expert")
        app.handle_event(key(pygame.K_c))
        self.assertEqual(app.custom_fields, ["16", "30", "99"])

    def test_valid_input_applies_new_board(self):
        app = self.make_app()
        app.handle_event(key(pygame.K_c))
        self.type_number(app, "10")
        app.handle_event(key(pygame.K_TAB))
        self.type_number(app, "14")
        app.handle_event(key(pygame.K_TAB))
        self.type_number(app, "30")
        self.press_enter(app)
        self.assertFalse(app.custom_open)
        self.assertEqual(
            (app.game.level.rows, app.game.level.cols, app.game.level.mines), (10, 14, 30)
        )
        self.assertEqual(app.game.level.name, "Custom 14×10")
        self.assertEqual(app.width, 14 * app.cell + theme.MARGIN * 2)

    def test_invalid_input_keeps_panel_and_current_game(self):
        app = self.make_app("beginner")
        app.handle_event(key(pygame.K_c))
        self.type_number(app, "3")
        app.handle_event(key(pygame.K_TAB))
        self.type_number(app, "3")
        app.handle_event(key(pygame.K_TAB))
        self.type_number(app, "1")
        self.press_enter(app)
        self.assertTrue(app.custom_open, "非法输入不应用，面板保持打开")
        self.assertTrue(app.custom_error)
        self.assertEqual(app.game.level.key, "beginner", "当前这一局不应被破坏")

    def test_error_is_cleared_after_valid_apply(self):
        app = self.make_app()
        app.handle_event(key(pygame.K_c))
        self.type_number(app, "99")
        self.press_enter(app)                      # 先制造一次错误（行数超范围）
        self.assertTrue(app.custom_error)
        self.type_number(app, "9")                 # 把行数改回合法
        app.handle_event(key(pygame.K_TAB))
        self.type_number(app, "9")
        app.handle_event(key(pygame.K_TAB))
        self.type_number(app, "10")
        self.press_enter(app)
        self.assertFalse(app.custom_open)
        self.assertEqual(app.custom_error, "")


class RenderTest(UITestBase):
    """渲染：只看像素，不看内部字段。"""

    def _pixel(self, app: App, cell: tuple[int, int]) -> tuple[int, int, int]:
        rect = app._cell_rect(*cell)
        return app.screen.get_at(rect.center)[:3]

    def test_cell_states_use_distinct_colours(self):
        app = self.make_app()
        app.draw()
        covered = self._pixel(app, (0, 8))
        self.click(app, (4, 4))
        app.draw()
        opened = self._pixel(app, (4, 4))
        self.assertNotEqual(covered, opened)

        app.handle_event(key(pygame.K_r))
        app.handle_event(motion(app._cell_rect(0, 8).center))
        app.draw()
        hovered = self._pixel(app, (0, 8))
        self.assertEqual(hovered, theme.CELL_COVERED_HOVER)

        start = app._cell_rect(0, 8).center
        app.handle_event(down(start))
        app.draw()
        pressed = self._pixel(app, (0, 8))
        self.assertNotEqual(pressed, hovered, "按下时应比悬停更暗（F-13 凹陷感）")

    def test_number_colour_matches_theme(self):
        app = self.make_app()
        self.click(app, (4, 4))
        cell = self.find_revealed_number(app, minimum=1)
        app.draw()
        rect = app._cell_rect(*cell)
        expected = theme.NUMBER_COLORS[app.game.board.cells[cell[0]][cell[1]].adjacent]
        found = False
        for x in range(rect.left + 2, rect.right - 2):
            for y in range(rect.top + 2, rect.bottom - 2):
                if app.screen.get_at((x, y))[:3] == expected:
                    found = True
                    break
            if found:
                break
        self.assertTrue(found, f"数字 {cell} 应使用主题色 {expected}")

    def test_banner_and_panel_are_drawn_last(self):
        app = self.make_app()
        app.handle_event(key(pygame.K_c))
        app.draw()
        rect = pygame.Rect(0, 0, app.width - 24 if app.width - 24 < 340 else 340, 190)
        rect.center = (app.board_x + app.board_w // 2, app.board_y + app.board_h // 2)
        self.assertEqual(app.screen.get_at(rect.center)[:3], theme.PANEL)

    def test_hud_shows_mines_left(self):
        app = self.make_app()
        self.click(app, (2, 2), button=3)
        app.draw()
        hud = app.restart_rect
        # 剩余雷数画在 HUD 左侧，取左侧区域里是否存在深色文字像素即可
        found_text = False
        for x in range(hud.left - 120, hud.left):
            for y in range(hud.top, hud.bottom):
                if app.screen.get_at((x, y))[:3] == theme.TEXT:
                    found_text = True
                    break
            if found_text:
                break
        self.assertTrue(found_text, "HUD 左侧应画出剩余雷数")


class EndGameTest(UITestBase):
    """终局：胜利/失败后的画面与"点了也不动"。"""

    def test_click_after_loss_is_ignored(self):
        app = self.make_app(seed=7)
        board = app.game.board
        first = (4, 4)
        self.click(app, first)
        mine = next(
            (r, c)
            for r in range(board.rows)
            for c in range(board.cols)
            if board.cells[r][c].has_mine
        )
        self.click(app, mine)
        self.assertIs(app.game.status, GameStatus.LOST)
        revealed = self.revealed_count(app)
        self.click(app, mine)
        self.assertEqual(self.revealed_count(app), revealed, "终局后点击不应再改变盘面")
        self.assertEqual(self.flags(app), [], "终局后右键也不应插旗")

        app.draw()
        hud_band = [
            app.screen.get_at((x, y))[:3]
            for x in range(app.board_x, app.board_x + app.board_w, 12)
            for y in range(theme.MARGIN + 2, app.board_y - 2, 6)
        ]
        self.assertIn(theme.PANEL, hud_band, "终局卡片只盖住棋盘，HUD 卡片应仍然可见")

    def test_restart_button_resets_board(self):
        app = self.make_app()
        self.click(app, (4, 4))
        self.assertGreater(self.revealed_count(app), 0)
        pos = app.restart_rect.center
        app.handle_event(down(pos))
        app.handle_event(up(pos))
        self.assertEqual(self.revealed_count(app), 0)
        self.assertEqual(self.flags(app), [])




    def test_click_on_hud_does_not_reveal(self):
        """HUD 区域的 x 落在盘面范围内，但 y 在盘面上方，不应被当成格子。"""
        app = self.make_app()
        pos = (app.board_x + 5, theme.MARGIN + 5)
        app.handle_event(down(pos))
        app.handle_event(up(pos))
        self.assertEqual(self.revealed_count(app), 0)
        self.assertEqual(self.flags(app), [])

    def test_double_click_without_enough_information_hints_red(self):
        app = self.make_app()
        self.click(app, (4, 4))
        board = app.game.board
        target = None
        for r in range(board.rows):
            for c in range(board.cols):
                cell = board.cells[r][c]
                if (
                    cell.state is CellState.REVEALED
                    and not cell.has_mine
                    and cell.adjacent > 0
                ):
                    hidden = [
                        n for n in board.neighbors(r, c)
                        if board.cells[n[0]][n[1]].state is CellState.HIDDEN
                    ]
                    if len(hidden) != cell.adjacent:
                        target = (r, c)
                        break
            if target:
                break
        self.assertIsNotNone(target, "用例前提：应存在推不出来的数字格")
        app._reset_click_state()
        self.double_click(app, target)
        app.draw()
        rect = app._cell_rect(*target)
        reds = sum(
            1
            for y in range(rect.top, rect.bottom)
            for x in range(rect.left, rect.right)
            if app.screen.get_at((x, y))[:3] == theme.FLAG_RED
        )
        self.assertGreater(reds, 0, "条件不足时该格应闪红框")


class EdgeCaseUiTest(UITestBase):
    """边界事件：点空白处、中键、退出、面板打开时的鼠标、终局渲染、自检。"""

    def test_click_outside_board_is_ignored(self):
        app = self.make_app()
        app.handle_event(down((1, 1)))          # 棋盘左上方边距
        app.handle_event(up((1, 1)))
        app.handle_event(down((app.width - 2, app.height - 2)))
        app.handle_event(up((app.width - 2, app.height - 2)))
        self.assertEqual(self.revealed_count(app), 0)
        self.assertEqual(self.flags(app), [])

    def test_middle_button_is_ignored(self):
        app = self.make_app()
        pos = app._cell_rect(4, 4).center
        app.handle_event(down(pos, button=2))
        app.handle_event(up(pos, button=2))
        self.assertEqual(self.revealed_count(app), 0)
        self.assertEqual(self.flags(app), [])

    def test_quit_event_stops_the_loop(self):
        app = self.make_app()
        self.assertFalse(app.handle_event(pygame.event.Event(pygame.QUIT)))

    def test_hover_is_frozen_while_panel_open(self):
        app = self.make_app()
        app.handle_event(key(pygame.K_c))
        app.handle_event(motion(app._cell_rect(3, 3).center))
        self.assertIsNone(app.hover, "面板打开时鼠标移动不应更新悬停格")

    def test_won_board_draws_card_and_win_label(self):
        app = self.make_app()
        board = app.game.board
        self.click(app, (4, 4))
        for r in range(board.rows):
            for c in range(board.cols):
                if not board.cells[r][c].has_mine:
                    app.game.reveal(r, c)
        self.assertIs(app.game.status, GameStatus.WON)
        app.draw()
        center = (app.board_x + app.board_w // 2, app.board_y + app.board_h // 2)
        self.assertEqual(app.screen.get_at(center)[:3], theme.PANEL, "胜利应画出居中卡片")
        label_zone = [
            app.screen.get_at((x, y))[:3]
            for x in range(app.restart_rect.left, app.restart_rect.right)
            for y in range(app.restart_rect.top, app.restart_rect.bottom)
        ]
        self.assertIn(theme.WON_GREEN, label_zone, "HUD 按钮应变绿并显示 WIN")

    def test_lost_board_draws_cross_on_wrong_flag(self):
        app = self.make_app()
        board = app.game.board
        self.click(app, (4, 4))
        wrong = next(
            (r, c)
            for r in range(board.rows)
            for c in range(board.cols)
            if board.cells[r][c].state is CellState.HIDDEN and not board.cells[r][c].has_mine
        )
        self.click(app, wrong, button=3)                # 故意插错旗
        mine = next(
            (r, c)
            for r in range(board.rows)
            for c in range(board.cols)
            if board.cells[r][c].state is CellState.HIDDEN and board.cells[r][c].has_mine
        )
        self.click(app, mine)                           # 踩雷
        self.assertIs(app.game.status, GameStatus.LOST)
        app.draw()          # 先走一次完整绘制，让错旗快照生成
        # 单独重画盘面（不含终局蒙层），这样颜色不会被白色蒙层冲淡
        app.screen.fill(theme.BG)
        app._draw_board()
        rect = app._cell_rect(*wrong)
        reds = sum(
            1
            for x in range(rect.left, rect.right)
            for y in range(rect.top, rect.bottom)
            if app.screen.get_at((x, y))[:3] == theme.LOST_RED
        )
        self.assertGreater(reds, 0, "错旗格应画红色叉")

    def test_auto_flag_shows_green_hint(self):
        app = self.make_app()
        board = app.game.board
        self.click(app, (4, 4))
        # 构造"未翻开格数 == 剩余雷数"的局面：手里一个数字格、周围全都能推出
        target = None
        for r in range(board.rows):
            for c in range(board.cols):
                cell = board.cells[r][c]
                if cell.state is CellState.REVEALED and not cell.has_mine and cell.adjacent > 0:
                    hidden = [
                        (nr, nc)
                        for nr, nc in board.neighbors(r, c)
                        if board.cells[nr][nc].state is CellState.HIDDEN
                    ]
                    if len(hidden) == cell.adjacent:
                        target = (r, c)
                        break
            if target:
                break
        if target is None:
            self.skipTest("这一局没有现成的可自动插旗局面")
        app._reset_click_state()
        self.click(app, target)
        app._reset_click_state()
        self.double_click(app, target)
        app.draw()
        rect = app._cell_rect(*target)
        greens = sum(
            1
            for y in range(rect.top, rect.bottom)
            for x in range(rect.left, rect.right)
            if app.screen.get_at((x, y))[:3] == theme.WON_GREEN
        )
        self.assertGreater(greens, 0, "自动插旗后应闪绿框")

    def test_panel_shows_error_text_in_red(self):
        app = self.make_app()
        app.handle_event(key(pygame.K_c))
        self.type_number(app, "99")
        self.press_enter(app)
        app.draw()
        reds = sum(
            1
            for x in range(app.board_x, app.board_x + app.board_w)
            for y in range(app.board_y, app.board_y + app.board_h)
            if app.screen.get_at((x, y))[:3] == theme.LOST_RED
        )
        self.assertGreater(reds, 0, "非法输入应在面板上用红字提示")

    def test_smoke_writes_screenshot(self):
        import tempfile
        from pathlib import Path
        app = self.make_app(seed=5)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "smoke.png"
            app.smoke(shot_path=out)
            self.assertTrue(out.exists(), "自检应产出截图")
            self.assertGreater(out.stat().st_size, 0)

    def test_run_loop_exits_on_quit(self):
        app = self.make_app()
        pygame.event.post(pygame.event.Event(pygame.QUIT))
        app.run()
        pygame.init()          # run() 里有 pygame.quit()，后面的用例还要用


if __name__ == "__main__":
    unittest.main()
