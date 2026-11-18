"""core.py 的单元测试（不依赖 pygame，纯逻辑回归）。

运行：
    python -m unittest discover -s tests -t . -v
"""

from __future__ import annotations

import random
import unittest

from minesweeper.config import LevelConfig, find_level, load_levels
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


if __name__ == "__main__":
    unittest.main()
