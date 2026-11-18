"""对局状态机：管理计时与重开，UI 只关心“展示什么、点了怎么办”。

把计时这类有状态的逻辑收在这里，Board 保持纯规则，职责边界更清楚。
"""

from __future__ import annotations

import random
import time

from .config import LevelConfig
from .core import Board, GameStatus


class Game:
    def __init__(self, level: LevelConfig, seed: int | None = None) -> None:
        self.level = level
        self.seed = seed
        self.board: Board = Board(level)
        self._started_at: float | None = None
        self._final_elapsed: float | None = None
        self.restart()

    # ---------- 生命周期 ----------

    def restart(self) -> None:
        """重开一局。给了 seed 时局面可复现，方便调试和写测试。"""
        rng = random.Random(self.seed) if self.seed is not None else random.Random()
        self.board = Board(self.level, rng=rng)
        self._started_at = None
        self._final_elapsed = None

    # ---------- 只读状态 ----------

    @property
    def status(self) -> GameStatus:
        return self.board.status

    @property
    def mines_left(self) -> int:
        return self.board.mines_left

    @property
    def elapsed(self) -> float:
        """已用时（秒）。第一下点击才开始计时，结束后停止。"""
        if self._final_elapsed is not None:
            return self._final_elapsed
        if self._started_at is None:
            return 0.0
        return time.monotonic() - self._started_at

    @property
    def elapsed_text(self) -> str:
        total = int(self.elapsed)
        return f"{total // 60:02d}:{total % 60:02d}"

    # ---------- 操作 ----------

    def reveal(self, row: int, col: int) -> None:
        before = self.board.status
        self.board.reveal(row, col)
        self._sync_timer(before)

    def toggle_flag(self, row: int, col: int) -> None:
        before = self.board.status
        self.board.toggle_flag(row, col)
        self._sync_timer(before)

    def chord(self, row: int, col: int) -> bool:
        """双击和弦，返回是否真正执行了翻开动作。"""
        before = self.board.status
        changed = self.board.chord(row, col)
        self._sync_timer(before)
        return changed

    # ---------- 内部 ----------

    def _sync_timer(self, before: GameStatus) -> None:
        """状态迁移时补上计时：READY->PLAYING 开始计时，进入终局冻结用时。"""
        now_status = self.board.status
        if now_status is GameStatus.PLAYING and before is GameStatus.READY:
            self._started_at = time.monotonic()
        if now_status in (GameStatus.WON, GameStatus.LOST) and self._final_elapsed is None:
            if self._started_at is None:
                self._final_elapsed = 0.0
            else:
                self._final_elapsed = time.monotonic() - self._started_at
