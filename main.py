"""程序入口：解析参数 -> 载入配置 -> 启动界面。

用法：
    python main.py                       # 默认 beginner
    python main.py --level intermediate  # 换难度
    python main.py --seed 42             # 固定局面，便于复现 bug
    python main.py --list-levels         # 只列难度
    python main.py --smoke               # 无窗口自检 + 截图
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from minesweeper.config import find_level, load_levels


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="minesweeper-demo",
        description="扫雷 Demo（Python + pygame），逻辑与渲染分层实现",
    )
    parser.add_argument("--level", default="beginner", help="难度 key，见 config/levels.json")
    parser.add_argument("--seed", type=int, default=None, help="随机种子，指定后局面可复现")
    parser.add_argument("--list-levels", action="store_true", help="列出全部难度后退出")
    parser.add_argument("--smoke", action="store_true", help="无窗口渲染一帧做自检")
    parser.add_argument("--shot", default="docs/preview.png", help="自检截图的保存路径")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    levels = load_levels()

    if args.list_levels:
        for index, level in enumerate(levels, start=1):
            print(f"{index}. {level.key:<12} {level.name:<14} {level.rows}x{level.cols} / {level.mines} 雷")
        return 0

    try:
        find_level(levels, args.level)
    except KeyError:
        print(f"未知难度: {args.level}，可用值见 --list-levels", file=sys.stderr)
        return 2

    # 自检模式必须在 pygame 初始化前切到 dummy 视频驱动，否则会真的弹窗
    if args.smoke:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

    from minesweeper.ui import App  # 延迟导入：--list-levels 时不需要加载 pygame

    shot_path = Path(args.shot)
    shot_path.parent.mkdir(parents=True, exist_ok=True)
    app = App(levels, args.level, seed=args.seed)

    if args.smoke:
        status = app.smoke(shot_path=shot_path, seed=args.seed or 7)
        print(f"smoke ok (status={status}) -> {shot_path.resolve()}")
        return 0

    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
