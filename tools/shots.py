"""批量生成 README 用的预览图，不需要显示器。

用法：
    python tools/shots.py

输出到 docs/：
    preview.png                beginner 进行中
    preview-intermediate.png   intermediate 进行中
    preview-expert.png         expert 进行中
    preview-win.png            胜利画面
    preview-lost.png           失败画面

放在仓库里的意义：README 截图不再手工截、不会随时间过期，
改配色后跑一次就能把全套图刷新。
"""

from __future__ import annotations

import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 必须在 pygame 初始化前设置，才能走无窗口驱动
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from minesweeper.config import load_levels  # noqa: E402
from minesweeper.core import CellState, GameStatus  # noqa: E402
from minesweeper.ui import App  # noqa: E402

DOCS = ROOT / "docs"


def _revealed_cells(board):
    return sum(1 for row in board.cells for cell in row if cell.state is CellState.REVEALED)


def stage_playing(app: App, reveal_count: int = 4, flag_count: int = 2, seed: int = 7) -> None:
    """模拟一局进行中的画面：中心起手 + 再翻几格 + 插两面旗。"""
    rng = random.Random(seed)
    level = app.game.level
    app.game.reveal(level.rows // 2, level.cols // 2)

    board = app.game.board
    safe = [
        (r, c)
        for r in range(level.rows)
        for c in range(level.cols)
        if board.cells[r][c].state is CellState.HIDDEN and not board.cells[r][c].has_mine
    ]
    for r, c in rng.sample(safe, min(reveal_count, len(safe))):
        app.game.reveal(r, c)

    hidden = [
        (r, c)
        for r in range(level.rows)
        for c in range(level.cols)
        if board.cells[r][c].state is CellState.HIDDEN
    ]
    for r, c in hidden[:flag_count]:
        app.game.toggle_flag(r, c)


def stage_lost(app: App, seed: int = 7) -> None:
    stage_playing(app, seed=seed)
    board = app.game.board
    # 必须挑一个"还没插旗"的雷，否则 reveal 会被跳过，画面仍是进行中
    mine = next(
        (r, c)
        for r in range(app.game.level.rows)
        for c in range(app.game.level.cols)
        if board.cells[r][c].has_mine and board.cells[r][c].state is CellState.HIDDEN
    )
    app.game.reveal(*mine)
    assert app.game.status is GameStatus.LOST, "失败画面没进入 LOST，检查挑雷逻辑"


def stage_won(app: App, seed: int = 7) -> None:
    stage_playing(app, seed=seed)
    board = app.game.board
    for r in range(app.game.level.rows):
        for c in range(app.game.level.cols):
            if not board.cells[r][c].has_mine:
                app.game.reveal(r, c)
    assert app.game.status is GameStatus.WON, "胜利画面没进入 WON，检查翻格逻辑"


def stage_pressed(app: App, seed: int = 7, cell: tuple[int, int] | None = None) -> None:
    """按下未松开的状态：给一个覆盖格做凹陷，验证 F-13 的视觉。"""
    stage_playing(app, seed=seed)
    board = app.game.board
    target = cell or next(
        (r, c)
        for r in range(app.game.level.rows)
        for c in range(app.game.level.cols)
        if board.cells[r][c].state is CellState.HIDDEN
    )
    app.hover = target
    app.pressed_cell = target
    assert app.pressed_cell is not None


def stage_wrong_flag(app: App, seed: int = 7) -> None:
    """失败画面里同时有插对的旗和插错的旗，验证 F-14 的叉。"""
    stage_playing(app, seed=seed, flag_count=0)
    board = app.game.board
    level = app.game.level

    # 故意在非雷格插一面错旗
    wrong = next(
        (r, c)
        for r in range(level.rows)
        for c in range(level.cols)
        if board.cells[r][c].state is CellState.HIDDEN and not board.cells[r][c].has_mine
    )
    app.game.toggle_flag(*wrong)

    # 再在真雷上插一面对的旗做对照
    right = next(
        (r, c)
        for r in range(level.rows)
        for c in range(level.cols)
        if board.cells[r][c].has_mine and board.cells[r][c].state is CellState.HIDDEN
    )
    app.game.toggle_flag(*right)

    # 踩另一颗雷结束
    mine = next(
        (r, c)
        for r in range(level.rows)
        for c in range(level.cols)
        if board.cells[r][c].has_mine and board.cells[r][c].state is CellState.HIDDEN
    )
    app.game.reveal(*mine)
    assert app.game.status is GameStatus.LOST, "错旗画面没进入 LOST"
    assert board.wrong_flags(), "错旗画面里没有错旗，检查挑格逻辑"


def save(app: App, name: str) -> Path:
    path = DOCS / name
    app.draw()
    import pygame

    pygame.image.save(app.screen, str(path))
    return path


def main() -> int:
    DOCS.mkdir(parents=True, exist_ok=True)
    levels = load_levels()

    beginner = App(levels, "beginner", seed=42)
    stage_playing(beginner, seed=42)
    save(beginner, "preview.png")

    intermediate = App(levels, "intermediate", seed=9)
    stage_playing(intermediate, seed=9)
    save(intermediate, "preview-intermediate.png")

    expert = App(levels, "expert", seed=3)
    stage_playing(expert, seed=3)
    save(expert, "preview-expert.png")

    won = App(levels, "beginner", seed=42)
    stage_won(won, seed=42)
    save(won, "preview-win.png")

    lost = App(levels, "beginner", seed=42)
    stage_lost(lost, seed=42)
    save(lost, "preview-lost.png")

    pressed = App(levels, "beginner", seed=42)
    stage_pressed(pressed, seed=42)
    save(pressed, "preview-pressed.png")

    wrong_flag = App(levels, "beginner", seed=42)
    stage_wrong_flag(wrong_flag, seed=42)
    save(wrong_flag, "preview-wrongflag.png")

    import pygame

    pygame.quit()
    for name in ("preview.png", "preview-intermediate.png", "preview-expert.png",
                 "preview-win.png", "preview-lost.png", "preview-pressed.png",
                 "preview-wrongflag.png"):
        print(f"docs/{name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
