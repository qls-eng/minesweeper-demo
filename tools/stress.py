"""随机打压测试：连续跑很多局，每一步都校验"不该被破坏的性质"。

和单元测试的区别：单元测试固定局面，这里靠随机探索把罕见组合撞出来。
任何一步破坏不变量就立即记录现场（局号、步号、局面快照）并退出，方便复现。

用法：
    python tools/stress.py            # 默认档
    python tools/stress.py --games 200
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from minesweeper.config import load_levels, make_custom_level
from minesweeper.core import Board, CellState, GameStatus


def recount(board: Board) -> list[str]:
    """把邻雷数全部重算一遍，和存着的值比对。"""
    problems = []
    for r in range(board.rows):
        for c in range(board.cols):
            if board.cells[r][c].has_mine:
                want = 0      # 雷格自己的计数恒为 0，不参与"周围有几颗雷"
            else:
                want = sum(
                    1
                    for nr, nc in board.neighbors(r, c)
                    if board.cells[nr][nc].has_mine
                )
            got = board.cells[r][c].adjacent
            if want != got:
                problems.append(f"({r},{c}) 存 {got} 实 {want}")
    return problems


class Checker:
    """不变量集合。每条都返回违规描述，空列表表示通过。"""

    def __init__(self, board: Board) -> None:
        self.board = board
        self.revealed_seen = 0
        self.last_status = board.status
        self.violations: list[str] = []

    def check(self, step: int, tag: str) -> None:
        b = self.board
        self.violations = []

        mines = sum(
            1 for r in range(b.rows) for c in range(b.cols) if b.cells[r][c].has_mine
        )
        if b.status is not GameStatus.READY and mines != b.mine_count:
            self.violations.append(f"雷数 {mines} != 配置 {b.mine_count}")

        revealed = sum(
            1
            for r in range(b.rows)
            for c in range(b.cols)
            if b.cells[r][c].state is CellState.REVEALED
        )
        if revealed < self.revealed_seen:
            self.violations.append(f"已翻开数回退 {self.revealed_seen} → {revealed}")
        self.revealed_seen = revealed

        flags = [
            (r, c)
            for r in range(b.rows)
            for c in range(b.cols)
            if b.cells[r][c].state is CellState.FLAGGED
        ]
        # 已翻开数字格周围的旗数不应超过该数字
        # 前提是"旗都插在真雷上"：玩家自己插错旗（含插超过雷数的旗）时这条必然不成立，
        # 那是玩法允许的失误，不算规则层的问题。
        wrong_flags = [
            (r, c)
            for r, c in flags
            if not b.cells[r][c].has_mine
        ]
        if not wrong_flags:
            if b.mine_count - len(flags) < 0:
                self.violations.append(f"剩余雷数变负：{b.mine_count} - {len(flags)}")
            if b.status is not GameStatus.READY:
                for r in range(b.rows):
                    for c in range(b.cols):
                        cell = b.cells[r][c]
                        if (
                            cell.state is CellState.REVEALED
                            and not cell.has_mine
                            and cell.adjacent > 0
                        ):
                            fc = sum(
                                1
                                for nr, nc in b.neighbors(r, c)
                                if b.cells[nr][nc].state is CellState.FLAGGED
                            )
                            if fc > cell.adjacent:
                                self.violations.append(
                                    f"({r},{c}) 数字 {cell.adjacent} 周围有 {fc} 面旗"
                                )

        # 胜负与盘面一致性
        if b.status is GameStatus.WON:
            if revealed != b.rows * b.cols - b.mine_count:
                self.violations.append(
                    f"判胜但还有格未翻开：{revealed}/{b.rows*b.cols - b.mine_count}"
                )
        if b.status is GameStatus.LOST:
            unrevealed_mines = [
                (r, c)
                for r in range(b.rows)
                for c in range(b.cols)
                if b.cells[r][c].has_mine and b.cells[r][c].state is not CellState.REVEALED
            ]
            if unrevealed_mines:
                self.violations.append(f"判负但有 {len(unrevealed_mines)} 颗雷没亮出来")

        # 状态只能往前走
        order = {
            GameStatus.READY: 0,
            GameStatus.PLAYING: 1,
            GameStatus.WON: 2,
            GameStatus.LOST: 2,
        }
        if order[b.status] < order[self.last_status]:
            self.violations.append(f"状态回退 {self.last_status} → {b.status}")
        self.last_status = b.status

        if self.violations:
            raise AssertionError(
                f"[{tag}] 第 {step} 步出现 {len(self.violations)} 处违规：" + "；".join(self.violations)
            )


def first_reveal(board: Board, rng: random.Random) -> None:
    """第一下永远点未翻开格：验证"首点必安全"。"""
    covered = [
        (r, c)
        for r in range(board.rows)
        for c in range(board.cols)
        if board.cells[r][c].state is CellState.HIDDEN
    ]
    target = rng.choice(covered)
    board.reveal(*target)
    cell = board.cells[target[0]][target[1]]
    if cell.has_mine:
        raise AssertionError(f"首点踩雷：{target} 在 seed 录下的局面里是雷")
    safe_zone = [(target[0], target[1])] + list(board.neighbors(*target))
    for r, c in safe_zone:
        if board.cells[r][c].has_mine:
            raise AssertionError(f"首点 3×3 内出现雷：{(r, c)}")


def full_game(
    board: Board,
    rng: random.Random,
    style: str,
    steps: int = 260,
) -> tuple[GameStatus, int]:
    """跑一局。

    style:
      solver   —— 只用规则能推出的结论（旗数==数字则和弦，未翻开==剩余雷则插旗），
                  理论上永不踩雷，是最强的白盒校验
      mixed    —— 随机点、随机插旗（可能插错、可能踩雷），用来撞边界组合
    """
    checker = Checker(board)
    first_reveal(board, rng)

    for step in range(steps):
        if board.status in (GameStatus.WON, GameStatus.LOST):
            checker.check(step, style)
            return board.status, step

        nums = [
            (r, c)
            for r in range(board.rows)
            for c in range(board.cols)
            if board.cells[r][c].state is CellState.REVEALED
            and not board.cells[r][c].has_mine
            and board.cells[r][c].adjacent > 0
        ]
        covered = [
            (r, c)
            for r in range(board.rows)
            for c in range(board.cols)
            if board.cells[r][c].state is CellState.HIDDEN
        ]

        if style == "solver":
            # 反复套用两条能推理的规则，直到一轮下来没有任何进展
            if not nums:
                break
            progress = False
            for cell in nums:
                if board.chord(*cell) or board.auto_flag(*cell):
                    progress = True
            if not progress:
                break
            if board.status is GameStatus.LOST:
                raise AssertionError("只做逻辑推理却踩雷了：自动插旗插到了非雷格")
        else:
            roll = rng.random()
            if roll < 0.55 and nums:
                target = rng.choice(nums)
                if rng.random() < 0.5:
                    board.chord(*target)
                else:
                    board.auto_flag(*target)
            elif roll < 0.75 and covered:
                board.toggle_flag(*rng.choice(covered))
            elif covered:
                board.reveal(*rng.choice(covered))

        checker.check(step, style)
        if step % 40 == 0 and board.status is not GameStatus.READY:
            # READY 阶段还没布雷（延迟布雷），此时比对没有意义
            problems = recount(board)
            if problems:
                raise AssertionError(f"[{style}] 第 {step} 步邻雷数不一致：{problems[:3]}")

    return board.status, steps


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=120)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    # 除了三档预设，再加"极小但雷挤满"和"极大"两种极端盘面
    deck = list(load_levels()) + [
        make_custom_level(12, 20, 40),
        make_custom_level(5, 5, 16),      # 5×5 允许的最大雷数（25-9=16）
        make_custom_level(40, 60, 200),
    ]

    stats: dict[str, dict[str, int]] = {}
    for i in range(args.games):
        level = deck[i % len(deck)]
        style = "solver" if i % 2 == 0 else "mixed"
        board = Board(level, rng=random.Random(rng.randrange(10**6)))
        status, steps = full_game(board, rng, style, steps=400 if level.rows <= 20 else 120)
        bucket = stats.setdefault(style, {})
        bucket[status.name] = bucket.get(status.name, 0) + 1

    print(f"打压完成：{args.games} 局，seed={args.seed}")
    for style, bucket in stats.items():
        won = bucket.get("WON", 0)
        lost = bucket.get("LOST", 0)
        left = bucket.get("PLAYING", 0) + bucket.get("READY", 0)
        print(f"  {style:7s} 胜 {won:3d} 负 {lost:3d} 逻辑耗尽未结束 {left:3d}")
        if style == "solver" and lost:
            raise AssertionError("只做逻辑推理却输了一局")
    print("所有不变量全程未破坏")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
