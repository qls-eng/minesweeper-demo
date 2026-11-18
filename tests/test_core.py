"""core.py 的单元测试（不依赖 pygame，纯逻辑回归）。

运行：
    python -m unittest discover -s tests -t . -v
"""

from __future__ import annotations

import random
import unittest

from minesweeper.config import (
    LevelConfig,
    find_level,
    load_levels,
    make_custom_level,
    validate_level,
)
from minesweeper.core import Board, CellState, GameStatus
from minesweeper.game import Game


def make_level(rows: int = 9, cols: int = 9, mines: int = 10) -> LevelConfig:
    return LevelConfig("test", "Test", rows, cols, mines)


def make_pattern_board(rows: int, cols: int, mine_positions) -> Board:
    """手工构造一个有雷的棋盘：绕过随机布雷，方便断言具体数字。

    这里访问了私有方法 / 字段，属于同包内测试的常规做法：
    目的是把随机性排除掉，只验证计数与展开逻辑本身。
    """
    board = Board(make_level(rows, cols, len(mine_positions)))
    for row, col in mine_positions:
        board.cells[row][col].has_mine = True
    board._recount_adjacent()
    board._mines_placed = True
    return board


def revealed_count(board: Board) -> int:
    return sum(
        1
        for row_cells in board.cells
        for cell in row_cells
        if cell.state is CellState.REVEALED
    )


class BoardInitTest(unittest.TestCase):
    def test_dimensions_and_initial_state(self):
        board = Board(make_level(9, 9, 10))
        self.assertEqual(len(board.cells), 9)
        self.assertEqual(len(board.cells[0]), 9)
        self.assertEqual(board.status, GameStatus.READY)
        self.assertEqual(board.flag_count, 0)
        self.assertEqual(board.mines_left, 10)

    def test_invalid_mine_count_raises(self):
        with self.assertRaises(ValueError):
            Board(make_level(5, 5, 0))
        with self.assertRaises(ValueError):
            Board(make_level(5, 5, 25))

    def test_invalid_size_raises(self):
        with self.assertRaises(ValueError):
            Board(make_level(0, 5, 1))


class FirstClickTest(unittest.TestCase):
    def test_first_click_never_hits_mine(self):
        """核心体验保证：连点 50 个种子，第一下都不可能踩雷。"""
        for seed in range(50):
            board = Board(make_level(9, 9, 10), rng=random.Random(seed))
            board.reveal(4, 4)
            self.assertEqual(board.status, GameStatus.PLAYING, f"seed={seed} 第一下就踩雷了")

    def test_first_click_opens_an_area(self):
        """点击格在安全区内，adjacent 必为 0，因此至少展开一小片。"""
        board = Board(make_level(9, 9, 10), rng=random.Random(3))
        board.reveal(4, 4)
        self.assertGreaterEqual(revealed_count(board), 4)

    def test_exact_mine_count_after_first_click(self):
        for seed in range(10):
            board = Board(make_level(9, 9, 10), rng=random.Random(seed))
            board.reveal(0, 0)
            mines = sum(1 for row in board.cells for cell in row if cell.has_mine)
            self.assertEqual(mines, 10, f"seed={seed} 雷数不对")


class AdjacentCountTest(unittest.TestCase):
    def test_corner_mine_counts(self):
        board = make_pattern_board(5, 5, [(0, 0)])
        self.assertEqual(board.cells[1][1].adjacent, 1)
        self.assertEqual(board.cells[0][1].adjacent, 1)
        self.assertEqual(board.cells[1][0].adjacent, 1)
        self.assertEqual(board.cells[3][3].adjacent, 0)

    def test_counts_match_brute_force(self):
        """与暴力双重循环独立算一遍的结果逐格比对。"""
        mines = [(0, 0), (2, 3), (4, 4), (1, 4)]
        board = make_pattern_board(5, 5, mines)
        mine_set = set(mines)
        for row in range(5):
            for col in range(5):
                if (row, col) in mine_set:
                    continue
                expected = sum(
                    1
                    for dr in (-1, 0, 1)
                    for dc in (-1, 0, 1)
                    if (dr, dc) != (0, 0)
                    and 0 <= row + dr < 5
                    and 0 <= col + dc < 5
                    and (row + dr, col + dc) in mine_set
                )
                self.assertEqual(board.cells[row][col].adjacent, expected)


class FlagTest(unittest.TestCase):
    def test_toggle_flag_cycles(self):
        board = Board(make_level(9, 9, 10))
        board.toggle_flag(0, 0)
        self.assertEqual(board.cells[0][0].state, CellState.FLAGGED)
        self.assertEqual(board.mines_left, 9)
        board.toggle_flag(0, 0)
        self.assertEqual(board.cells[0][0].state, CellState.HIDDEN)
        self.assertEqual(board.mines_left, 10)

    def test_flagged_cell_cannot_be_revealed(self):
        board = Board(make_level(9, 9, 10), rng=random.Random(1))
        board.toggle_flag(0, 0)
        board.reveal(0, 0)
        self.assertEqual(board.cells[0][0].state, CellState.FLAGGED)

    def test_flag_is_skipped_by_flood(self):
        board = make_pattern_board(5, 5, [(1, 1), (1, 2), (1, 3)])
        board.toggle_flag(2, 4)
        board.reveal(3, 0)
        self.assertEqual(board.cells[2][4].state, CellState.FLAGGED)


class FloodTest(unittest.TestCase):
    def test_flood_stops_at_number_wall(self):
        """一行 3 颗雷在 5x5 里形成数字墙：上两行不会被展开。

        手工推演：从 (3,0) 展开后，第 2~4 行共 15 格全开，
        第 0 行（数字 1~2）与第 1 行（雷 / 数字 1）保持隐藏。
        """
        board = make_pattern_board(5, 5, [(1, 1), (1, 2), (1, 3)])
        board.reveal(3, 0)
        self.assertEqual(revealed_count(board), 15)
        self.assertEqual(board.status, GameStatus.PLAYING)
        for col in range(5):
            self.assertEqual(board.cells[0][col].state, CellState.HIDDEN)

    def test_zero_cell_neighbors_are_opened(self):
        board = make_pattern_board(5, 5, [(0, 0)])
        board.reveal(3, 3)
        # 只有一个雷，除雷格外其它格都会被连锁展开
        self.assertEqual(revealed_count(board), 24)
        self.assertEqual(board.cells[0][0].state, CellState.HIDDEN)


class ChordTest(unittest.TestCase):
    """F-12 双击和弦。"""

    def test_chord_opens_remaining_neighbors_when_flags_match(self):
        board = make_pattern_board(5, 5, [(0, 0)])
        board.reveal(1, 1)                     # 该格 adjacent = 1
        board.toggle_flag(0, 0)                # 旗插对
        self.assertTrue(board.chord(1, 1))
        # (0,0) 是雷，保持插旗状态；其余邻格都该被翻开
        self.assertEqual(board.cells[0][0].state, CellState.FLAGGED)
        for row, col in [(0, 1), (0, 2), (1, 0), (1, 2), (2, 0), (2, 1), (2, 2)]:
            self.assertEqual(board.cells[row][col].state, CellState.REVEALED)

    def test_chord_does_nothing_when_flag_count_mismatch(self):
        board = make_pattern_board(5, 5, [(0, 0)])
        board.reveal(1, 1)
        self.assertFalse(board.chord(1, 1))    # 一面旗都没有，不该有动作

    def test_chord_on_hidden_cell_is_ignored(self):
        board = make_pattern_board(5, 5, [(0, 0)])
        self.assertFalse(board.chord(3, 3))

    def test_chord_on_zero_cell_is_ignored(self):
        board = make_pattern_board(5, 5, [(0, 0)])
        board.reveal(3, 3)                     # adjacent = 0 的已翻开格
        self.assertFalse(board.chord(3, 3))

    def test_chord_with_wrong_flag_loses(self):
        """旗插错时和弦会踩雷，这是经典规则，不做额外保护。"""
        board = make_pattern_board(5, 5, [(0, 0)])
        board.reveal(1, 1)
        board.toggle_flag(1, 2)                # 旗插在非雷格：数量对上了，位置错了
        self.assertTrue(board.chord(1, 1))
        self.assertEqual(board.status, GameStatus.LOST)
        self.assertEqual(board.cells[0][0].state, CellState.REVEALED)

    def test_chord_ignored_after_game_over(self):
        board = make_pattern_board(5, 5, [(0, 0)])
        board.reveal(1, 1)
        board.toggle_flag(0, 0)
        board.toggle_flag(0, 0)                # 取消旗
        board.reveal(0, 0)                     # 踩雷，进入终局
        self.assertEqual(board.status, GameStatus.LOST)
        self.assertFalse(board.chord(1, 1))


class WrongFlagTest(unittest.TestCase):
    """F-14 错旗打叉的规则层支撑。"""

    def test_lists_only_flagged_non_mines(self):
        board = make_pattern_board(5, 5, [(0, 0)])
        board.toggle_flag(0, 0)    # 插对的旗
        board.toggle_flag(2, 2)    # 插错的旗
        self.assertEqual(board.wrong_flags(), [(2, 2)])

    def test_empty_when_all_flags_correct(self):
        board = make_pattern_board(5, 5, [(0, 0)])
        board.toggle_flag(0, 0)
        self.assertEqual(board.wrong_flags(), [])

    def test_revealed_cells_never_count_as_wrong_flag(self):
        board = make_pattern_board(5, 5, [(0, 0)])
        board.reveal(3, 3)         # 已翻开格无法插旗
        board.toggle_flag(3, 3)
        self.assertEqual(board.wrong_flags(), [])


class AutoFlagTest(unittest.TestCase):
    """F-16 双击自动插旗：未翻开邻格数 == 数字 时，这些格必然是雷。"""

    def _board_with_exact_hidden(self) -> Board:
        # 5x5，顶排三颗雷；把中心格 (1,1) 和它的非雷邻格标成已翻开，
        # 于是 (1,1) 显示 3，且周围正好剩 3 个未翻开格（就是那三颗雷）。
        # 这里直接改 state 而不是逐个 reveal，是为了避开连锁展开把整盘翻完导致提前胜利。
        board = make_pattern_board(5, 5, [(0, 0), (0, 1), (0, 2)])
        for r, c in ((1, 1), (1, 0), (1, 2), (2, 0), (2, 1), (2, 2)):
            board.cells[r][c].state = CellState.REVEALED
        board.status = GameStatus.PLAYING   # status 是状态字段，只有走 reveal 才会推进，这里手动补上
        hidden = [
            (nr, nc)
            for nr, nc in board.neighbors(1, 1)
            if board.cells[nr][nc].state is CellState.HIDDEN
        ]
        self.assertEqual(len(hidden), 3, "用例前提：中心格周围应只剩 3 个未翻开格")
        self.assertEqual(board.cells[1][1].adjacent, 3, "用例前提：中心格应显示 3")
        self.assertIs(board.status, GameStatus.PLAYING, "用例前提：局面还没结束")
        return board

    def test_flags_all_hidden_neighbours(self):
        board = self._board_with_exact_hidden()
        self.assertTrue(board.auto_flag(1, 1))
        for r, c in ((0, 0), (0, 1), (0, 2)):
            self.assertIs(board.cells[r][c].state, CellState.FLAGGED)

    def test_returns_false_when_counts_do_not_match(self):
        # 5x5 只有一颗雷，中心格显示 1 但周围 8 格全未翻开：推不出结论，不插旗
        board = make_pattern_board(5, 5, [(0, 0)])
        board.reveal(2, 2)
        before = sum(
            1 for row in board.cells for cell in row if cell.state is CellState.FLAGGED
        )
        self.assertFalse(board.auto_flag(2, 2))
        after = sum(
            1 for row in board.cells for cell in row if cell.state is CellState.FLAGGED
        )
        self.assertEqual(before, after)

    def test_no_flag_on_zero_cell_or_hidden_cell(self):
        board = self._board_with_exact_hidden()
        self.assertFalse(board.auto_flag(2, 0))   # 数字格之外：0 格没有推理基础
        self.assertFalse(board.auto_flag(0, 0))   # 未翻开的格（还是颗雷）

    def test_no_flag_after_game_over(self):
        board = self._board_with_exact_hidden()
        board.reveal(0, 0)                        # 踩雷
        self.assertIs(board.status, GameStatus.LOST)
        self.assertFalse(board.auto_flag(1, 1))

    def test_existing_flags_are_subtracted(self):
        """回归：已有旗时不能只看"未翻开格数 == 数字"。

        数字 3、周围已有 2 面旗（都插在真雷上），还剩 3 个未翻开格但真实只有 1 颗雷。
        旧实现会把这 3 格全插上，导致 3 周围出现 5 面旗、其中 2 格不是雷。
        正确条件是"未翻开格数 == 数字 - 已有旗数"，这里 3 != 1，应当拒绝。
        """
        board = make_pattern_board(5, 5, [(0, 0), (0, 1), (0, 2)])
        for r, c in ((1, 1), (1, 0), (1, 2), (2, 1)):
            board.cells[r][c].state = CellState.REVEALED
        board.cells[0][0].state = CellState.FLAGGED      # 两面旗都插在真雷上
        board.cells[0][1].state = CellState.FLAGGED
        board.status = GameStatus.PLAYING

        hidden = [
            (nr, nc)
            for nr, nc in board.neighbors(1, 1)
            if board.cells[nr][nc].state is CellState.HIDDEN
        ]
        self.assertEqual(len(hidden), 3, "用例前提：还剩 3 个未翻开格")
        self.assertEqual(board.cells[1][1].adjacent, 3, "用例前提：中心格显示 3")
        self.assertEqual(board.cells[1][1].adjacent - 2, 1, "用例前提：剩余待标雷数只有 1")

        self.assertFalse(board.auto_flag(1, 1))
        wrong = [
            (nr, nc)
            for nr, nc in board.neighbors(1, 1)
            if board.cells[nr][nc].state is CellState.FLAGGED
            and not board.cells[nr][nc].has_mine
        ]
        self.assertEqual(wrong, [])

    def test_flags_remaining_when_requirement_matches(self):
        # 数字 3、已有 1 面旗（真雷）、剩 2 个未翻开格且都是雷：条件成立，应该插上这 2 格
        board = make_pattern_board(5, 5, [(0, 0), (0, 1), (0, 2)])
        for r, c in ((1, 1), (1, 0), (1, 2), (2, 0), (2, 1), (2, 2)):
            board.cells[r][c].state = CellState.REVEALED
        board.cells[0][0].state = CellState.FLAGGED
        board.status = GameStatus.PLAYING

        self.assertTrue(board.auto_flag(1, 1))
        for r, c in ((0, 1), (0, 2)):
            self.assertIs(board.cells[r][c].state, CellState.FLAGGED)
        self.assertEqual(
            sum(1 for nr, nc in board.neighbors(1, 1) if board.cells[nr][nc].state is CellState.FLAGGED),
            3,
            "周围旗数应等于数字 3",
        )


class EndGameTest(unittest.TestCase):
    def test_mine_click_loses_and_exposes_all_mines(self):
        board = Board(make_level(9, 9, 10), rng=random.Random(5))
        board.reveal(4, 4)
        self.assertEqual(board.status, GameStatus.PLAYING)

        mine = next(
            (r, c)
            for r in range(9)
            for c in range(9)
            if board.cells[r][c].has_mine
        )
        board.reveal(*mine)
        self.assertEqual(board.status, GameStatus.LOST)
        for row in board.cells:
            for cell in row:
                if cell.has_mine:
                    self.assertEqual(cell.state, CellState.REVEALED)

    def test_reveal_all_safe_cells_wins(self):
        board = Board(make_level(9, 9, 10), rng=random.Random(7))
        board.reveal(4, 4)
        for row in range(9):
            for col in range(9):
                if not board.cells[row][col].has_mine:
                    board.reveal(row, col)
        self.assertEqual(board.status, GameStatus.WON)

    def test_no_input_after_game_over(self):
        board = Board(make_level(9, 9, 10), rng=random.Random(9))
        board.reveal(4, 4)
        mine = next(
            (r, c) for r in range(9) for c in range(9) if board.cells[r][c].has_mine
        )
        board.reveal(*mine)
        before = revealed_count(board)
        board.reveal(0, 0)
        board.toggle_flag(0, 8)
        self.assertEqual(revealed_count(board), before)
        self.assertEqual(board.flag_count, 0)


class GameTest(unittest.TestCase):
    def test_restart_resets_board(self):
        game = Game(make_level(9, 9, 10), seed=11)
        game.reveal(4, 4)
        self.assertEqual(game.status, GameStatus.PLAYING)
        game.restart()
        self.assertEqual(game.status, GameStatus.READY)
        self.assertEqual(game.elapsed, 0.0)

    def test_timer_starts_on_first_click(self):
        game = Game(make_level(9, 9, 10), seed=12)
        self.assertEqual(game.elapsed_text, "00:00")
        game.reveal(4, 4)
        self.assertGreaterEqual(game.elapsed, 0.0)

    def test_seed_is_reproducible(self):
        first = Game(make_level(9, 9, 10), seed=123)
        second = Game(make_level(9, 9, 10), seed=123)
        first.reveal(4, 4)
        second.reveal(4, 4)
        layout_a = [[cell.has_mine for cell in row] for row in first.board.cells]
        layout_b = [[cell.has_mine for cell in row] for row in second.board.cells]
        self.assertEqual(layout_a, layout_b)


class ConfigTest(unittest.TestCase):
    def test_levels_loaded_from_json(self):
        levels = load_levels()
        self.assertEqual(len(levels), 3)
        self.assertEqual(find_level(levels, "beginner").rows, 9)
        self.assertEqual(find_level(levels, "expert").mines, 99)

    def test_unknown_level_raises(self):
        with self.assertRaises(KeyError):
            find_level(load_levels(), "nightmare")


class CustomLevelTest(unittest.TestCase):
    """F-17：自定义难度的区间校验与构造。"""

    def test_valid_level_has_no_errors(self):
        self.assertEqual(validate_level(20, 20, 80), [])

    def test_rows_and_cols_bounds(self):
        self.assertTrue(any("行数" in e for e in validate_level(3, 20, 10)))
        self.assertTrue(any("行数" in e for e in validate_level(41, 20, 10)))
        self.assertTrue(any("列数" in e for e in validate_level(20, 4, 10)))
        self.assertTrue(any("列数" in e for e in validate_level(20, 61, 10)))

    def test_mines_bounds_leave_room_for_safe_zone(self):
        # 9x9 最多 81-9=72 颗雷：再多就放不下首点 3x3 安全区
        self.assertEqual(validate_level(9, 9, 72), [])
        self.assertTrue(any("雷数最多 72" in e for e in validate_level(9, 9, 73)))
        self.assertTrue(any("至少为 1" in e for e in validate_level(9, 9, 0)))

    def test_make_custom_level_fields(self):
        level = make_custom_level(12, 20, 45)
        self.assertEqual((level.rows, level.cols, level.mines), (12, 20, 45))
        self.assertEqual(level.key, "custom")
        self.assertEqual(level.name, "Custom 20×12")

    def test_make_custom_level_rejects_invalid(self):
        with self.assertRaises(ValueError):
            make_custom_level(3, 3, 1)


if __name__ == "__main__":
    unittest.main()
