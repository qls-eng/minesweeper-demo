"""扫雷核心逻辑。

本模块刻意不 import pygame：只做纯数据的规则计算。
这样它可以被单元测试直接覆盖，也能复用到终端版 / 后续的网页版，
渲染层的改动永远不会污染规则层。
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum

from .config import LevelConfig


class CellState(Enum):
    HIDDEN = "hidden"
    REVEALED = "revealed"
    FLAGGED = "flagged"


class GameStatus(Enum):
    READY = "ready"      # 还没点第一下，雷尚未生成
    PLAYING = "playing"
    WON = "won"
    LOST = "lost"


@dataclass
class Cell:
    has_mine: bool = False
    adjacent: int = 0
    state: CellState = CellState.HIDDEN


class Board:
    """棋盘：布雷、翻开、插旗、胜负判定。

    关键设计：
    1. 延迟布雷 —— 首次点击之后才生成雷，保证第一下永远不会踩雷；
    2. 空白区域用显式栈做洪水填充（迭代，不用递归），避免大盘面递归过深；
    3. 所有对外方法都只改状态、不碰界面，方便单测。
    """

    def __init__(self, level: LevelConfig, rng: random.Random | None = None) -> None:
        if level.rows <= 0 or level.cols <= 0:
            raise ValueError("棋盘行数和列数必须为正数")

        total = level.rows * level.cols
        if not 0 < level.mines < total:
            raise ValueError(f"雷数必须在 1 与 {total - 1} 之间，当前为 {level.mines}")

        self.level = level
        self.rows = level.rows
        self.cols = level.cols
        self.mine_count = level.mines
        self.status = GameStatus.READY

        self._rng = rng if rng is not None else random.Random()
        self._mines_placed = False
        self.cells: list[list[Cell]] = [
            [Cell() for _ in range(self.cols)] for _ in range(self.rows)
        ]

    # ---------- 查询 ----------

    def in_bounds(self, row: int, col: int) -> bool:
        return 0 <= row < self.rows and 0 <= col < self.cols

    def neighbors(self, row: int, col: int):
        """生成八邻域坐标（越界的自动跳过）。"""
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = row + dr, col + dc
                if self.in_bounds(nr, nc):
                    yield nr, nc

    @property
    def flag_count(self) -> int:
        return sum(
            1
            for row_cells in self.cells
            for cell in row_cells
            if cell.state is CellState.FLAGGED
        )

    @property
    def mines_left(self) -> int:
        """HUD 上显示的“剩余雷数”，可以为负（旗插多了）。"""
        return self.mine_count - self.flag_count

    @property
    def is_over(self) -> bool:
        return self.status in (GameStatus.WON, GameStatus.LOST)

    def wrong_flags(self) -> list[tuple[int, int]]:
        """插在非雷格上的旗（F-14）。

        放在规则层而不是画图时的临时判断，是为了能单测：
        界面只消费这个结果，不用自己重算"这面旗对不对"。
        """
        return [
            (row, col)
            for row in range(self.rows)
            for col in range(self.cols)
            if self.cells[row][col].state is CellState.FLAGGED
            and not self.cells[row][col].has_mine
        ]

    # ---------- 交互 ----------

    def reveal(self, row: int, col: int) -> None:
        """翻开一格。踩雷即失败，空白则连锁展开。"""
        if self.is_over or not self.in_bounds(row, col):
            return

        cell = self.cells[row][col]
        if cell.state is not CellState.HIDDEN:
            return

        if not self._mines_placed:
            self._place_mines(row, col)   # 第一下：先定点，再布雷
        self.status = GameStatus.PLAYING

        if cell.has_mine:
            cell.state = CellState.REVEALED
            self.status = GameStatus.LOST
            self._reveal_all_mines()
            return

        self._flood_reveal(row, col)

        if self._all_safe_cells_open():
            self.status = GameStatus.WON

    def toggle_flag(self, row: int, col: int) -> None:
        """未翻开的格子：空 -> 插旗 -> 空，循环切换。"""
        if self.is_over or not self.in_bounds(row, col):
            return
        cell = self.cells[row][col]
        if cell.state is CellState.HIDDEN:
            cell.state = CellState.FLAGGED
        elif cell.state is CellState.FLAGGED:
            cell.state = CellState.HIDDEN

    def chord(self, row: int, col: int) -> bool:
        """双击和弦：在已翻开的数字格上，按周围旗数一次翻开其余邻格（F-12）。

        返回是否执行了操作。前置条件不满足时（不是已翻开的数字格、旗数与数字不等、
        没有可翻的邻格）返回 False，方便 UI 与测试区分"没用"和"用了但踩雷"。

        注意：旗插错时和弦会踩雷，这是经典规则的正常结果，这里刻意不做保护，
        否则插旗就失去了信息标记的意义。
        """
        if self.is_over or not self.in_bounds(row, col):
            return False

        cell = self.cells[row][col]
        if cell.has_mine or cell.state is not CellState.REVEALED or cell.adjacent == 0:
            return False

        flagged = sum(
            1
            for nr, nc in self.neighbors(row, col)
            if self.cells[nr][nc].state is CellState.FLAGGED
        )
        if flagged != cell.adjacent:
            return False

        targets = [
            (nr, nc)
            for nr, nc in self.neighbors(row, col)
            if self.cells[nr][nc].state is CellState.HIDDEN
        ]
        if not targets:
            return False

        # 复用 reveal：踩雷判定、连锁展开、胜利判定都走同一条路径，不另写一套
        for nr, nc in targets:
            self.reveal(nr, nc)
            if self.is_over:
                break
        return True

    # ---------- 内部实现 ----------

    def _place_mines(self, safe_row: int, safe_col: int) -> None:
        """在首次点击周围留出安全区后随机布雷。"""
        reserved = {(safe_row, safe_col)}
        reserved.update(self.neighbors(safe_row, safe_col))

        # 安全区大到放不下雷时，退化为只保护点击的那一格
        if self.rows * self.cols - len(reserved) < self.mine_count:
            reserved = {(safe_row, safe_col)}

        candidates = [
            (r, c)
            for r in range(self.rows)
            for c in range(self.cols)
            if (r, c) not in reserved
        ]
        for r, c in self._rng.sample(candidates, self.mine_count):
            self.cells[r][c].has_mine = True

        self._recount_adjacent()
        self._mines_placed = True

    def _recount_adjacent(self) -> None:
        """重算每格的地雷计数（布雷后 / 测试构造棋局时都要用）。"""
        for r in range(self.rows):
            for c in range(self.cols):
                cell = self.cells[r][c]
                if cell.has_mine:
                    cell.adjacent = 0
                    continue
                cell.adjacent = sum(
                    1 for nr, nc in self.neighbors(r, c) if self.cells[nr][nc].has_mine
                )

    def _flood_reveal(self, row: int, col: int) -> None:
        """从点击点扩散：数字格只翻自己，0 格继续向八邻域扩散。

        用显式栈而不是递归，16x30 大盘面也不会碰到递归深度限制。
        插了旗的格子会被跳过（state 不是 HIDDEN）。
        """
        stack = [(row, col)]
        while stack:
            r, c = stack.pop()
            cell = self.cells[r][c]
            if cell.state is not CellState.HIDDEN:
                continue
            cell.state = CellState.REVEALED
            if cell.adjacent == 0:
                for nr, nc in self.neighbors(r, c):
                    if self.cells[nr][nc].state is CellState.HIDDEN:
                        stack.append((nr, nc))

    def _reveal_all_mines(self) -> None:
        """失败时把所有雷亮出来，方便复盘。"""
        for r in range(self.rows):
            for c in range(self.cols):
                if self.cells[r][c].has_mine:
                    self.cells[r][c].state = CellState.REVEALED

    def _all_safe_cells_open(self) -> bool:
        """所有非雷格都翻开即胜利。"""
        for r in range(self.rows):
            for c in range(self.cols):
                cell = self.cells[r][c]
                if not cell.has_mine and cell.state is not CellState.REVEALED:
                    return False
        return True
