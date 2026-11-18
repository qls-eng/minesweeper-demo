"""界面猴测：随机混合发送真实事件，看会不会崩、会不会画出不一致的状态。

和 tools/stress.py 的分工：
  stress.py  只走规则层（Board），验证逻辑不变量
  ui_soak.py 只走界面层（App.handle_event + draw），验证交互与渲染不炸

用法：
    python tools/ui_soak.py --episodes 60 --events 80
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from minesweeper import theme
from minesweeper.config import load_levels, make_custom_level
from minesweeper.core import CellState, GameStatus
from minesweeper.ui import App


def key(code: int) -> pygame.event.Event:
    return pygame.event.Event(pygame.KEYDOWN, {"key": code, "unicode": "", "mod": 0})


def down(pos, button: int = 1) -> pygame.event.Event:
    return pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": pos, "button": button})


def up(pos, button: int = 1) -> pygame.event.Event:
    return pygame.event.Event(pygame.MOUSEBUTTONUP, {"pos": pos, "button": button})


def motion(pos) -> pygame.event.Event:
    return pygame.event.Event(pygame.MOUSEMOTION, {"pos": pos, "rel": (0, 0), "buttons": (0, 0, 0)})


def check_geometry(app: App) -> None:
    level = app.game.level
    if app.width != app.board_w + theme.MARGIN * 2:
        raise AssertionError(f"窗口宽度与盘面不一致：{app.width} vs {app.board_w}")
    if app.height != app.board_y + app.board_h + theme.MARGIN:
        raise AssertionError(f"窗口高度与盘面不一致：{app.height}")
    if app.board_w != level.cols * app.cell or app.board_h != level.rows * app.cell:
        raise AssertionError("盘面尺寸与行列数不一致")
    if app.cell < theme.MIN_CELL_SIZE:
        raise AssertionError(f"格子被压到 {app.cell}px，低于下限")
    if app.game.board.cols != level.cols or app.game.board.rows != level.rows:
        raise AssertionError("Game 与 level 行列不一致")


def check_board(app: App, last: dict) -> dict:
    board = app.game.board
    key_id = (app.game.level.key, board.rows, board.cols)
    if last.get("key") != key_id:
        last.clear()
        last["key"] = key_id
        last["revealed"] = 0
        last["status"] = GameStatus.READY

    if board.status is not GameStatus.READY:
        mines = sum(
            1 for r in range(board.rows) for c in range(board.cols) if board.cells[r][c].has_mine
        )
        if mines != board.mine_count:
            raise AssertionError(f"雷数 {mines} 与配置 {board.mine_count} 不一致")

    revealed = sum(
        1
        for r in range(board.rows)
        for c in range(board.cols)
        if board.cells[r][c].state is CellState.REVEALED
    )
    if revealed < last.get("revealed", 0):
        raise AssertionError(f"已翻开数回退 {last.get('revealed')} → {revealed}")
    last["revealed"] = revealed

    order = {GameStatus.READY: 0, GameStatus.PLAYING: 1, GameStatus.WON: 2, GameStatus.LOST: 2}
    if order[board.status] < order[last["status"]]:
        raise AssertionError(f"状态回退 {last['status']} → {board.status}")
    last["status"] = board.status

    if not (0 <= app.game.mines_left <= board.mine_count):
        raise AssertionError(f"剩余雷数越界：{app.game.mines_left}")
    return last


def random_event(app: App, rng: random.Random) -> bool:
    """随机造一个"玩家可能做出来的"事件。

    返回 True 表示这次操作可能把对局重置了（重开/换难度/应用自定义），
    调用方据此重置"单调递增"类的统计。
    """
    pick = rng.random()
    if pick < 0.45:
        r = rng.randrange(app.game.board.rows)
        c = rng.randrange(app.game.board.cols)
        pos = app._cell_rect(r, c).center
        button = 3 if rng.random() < 0.3 else 1
        if rng.random() < 0.45:
            # 双击：连发两轮按下/松开
            app.handle_event(down(pos, button))
            app.handle_event(up(pos, button))
            app.handle_event(down(pos, button))
            app.handle_event(up(pos, button))
        else:
            app.handle_event(down(pos, button))
            if rng.random() < 0.35:
                # 拖到别处再松开（取消操作）
                rr, cc = rng.randrange(app.game.board.rows), rng.randrange(app.game.board.cols)
                app.handle_event(motion(app._cell_rect(rr, cc).center))
                app.handle_event(up(app._cell_rect(rr, cc).center, button))
            else:
                app.handle_event(up(pos, button))
    elif pick < 0.55:
        app.handle_event(key(rng.choice([pygame.K_r, pygame.K_1, pygame.K_2, pygame.K_3])))
        return True
    elif pick < 0.75:
        # 打开面板 → 乱按几个键 → 有时回车应用、有时 Esc 关掉
        app.handle_event(key(pygame.K_c))
        for _ in range(rng.randrange(1, 8)):
            app.handle_event(
                key(
                    rng.choice(
                        [
                            pygame.K_TAB,
                            pygame.K_UP,
                            pygame.K_DOWN,
                            pygame.K_BACKSPACE,
                            pygame.K_0,
                            pygame.K_1,
                            pygame.K_4,
                            pygame.K_9,
                            pygame.K_RETURN,
                        ]
                    )
                )
            )
        if app.custom_open:
            app.handle_event(key(rng.choice([pygame.K_ESCAPE, pygame.K_c, pygame.K_RETURN])))
        return True        # C / Enter 都可能换成新的一局
    elif pick < 0.85:
        # 点重开按钮
        pos = app.restart_rect.center
        app.handle_event(down(pos))
        app.handle_event(up(pos))
        return True
    else:
        # 点棋盘外 / HUD
        app.handle_event(down((1, 1)))
        app.handle_event(up((1, 1)))
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=60)
    ap.add_argument("--events", type=int, default=80)
    ap.add_argument("--seed", type=int, default=3)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    pygame.init()
    levels = load_levels()

    stats: dict[str, int] = {}
    for episode in range(args.episodes):
        custom = None
        if episode % 6 == 5:
            custom = make_custom_level(
                rng.choice([5, 9, 16, 40]),
                rng.choice([5, 12, 30, 60]),
                rng.randint(1, 40),
            )
        app = App(levels, rng.choice(["beginner", "intermediate", "expert"]), seed=episode, custom_level=custom)
        last: dict = {}
        for i in range(args.events):
            if random_event(app, rng):
                last.clear()          # 可能换了新局，重置单调性统计
            check_geometry(app)
            last = check_board(app, last)
            app.draw()            # 每步都画一遍，渲染路径也要被压到
            status = app.game.status.name
            stats[status] = stats.get(status, 0) + 1
        # 终局冻结：再点几下，盘面不能变
        if app.game.status in (GameStatus.WON, GameStatus.LOST):
            before = check_board(app, last)["revealed"]
            for _ in range(5):
                app.handle_event(down(app._cell_rect(0, 0).center))
                app.handle_event(up(app._cell_rect(0, 0).center))
                app.handle_event(down(app._cell_rect(0, 0).center, 3))
                app.handle_event(up(app._cell_rect(0, 0).center, 3))
            if check_board(app, last)["revealed"] != before:
                raise AssertionError("终局后盘面还在变")

    pygame.quit()
    print(f"猴测完成：{args.episodes} 局 × {args.events} 个事件，seed={args.seed}")
    print("  结束时各状态分布：" + "，".join(f"{k}={v}" for k, v in sorted(stats.items())))
    print("几何、状态机、终局冻结、渲染全程无异常")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
