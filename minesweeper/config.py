"""难度配置：把棋盘参数外置到 JSON，代码里不再硬编码。

好处：加一档难度、调一次雷数，只改数据文件，不用碰逻辑或渲染代码。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "levels.json"


@dataclass(frozen=True)
class LevelConfig:
    """一档难度：棋盘尺寸 + 雷数。"""

    key: str
    name: str
    rows: int
    cols: int
    mines: int


# 配置文件缺失时的兜底，保证程序永远能跑起来
FALLBACK_LEVELS: tuple[LevelConfig, ...] = (
    LevelConfig("beginner", "Beginner", 9, 9, 10),
    LevelConfig("intermediate", "Intermediate", 16, 16, 40),
    LevelConfig("expert", "Expert", 16, 30, 99),
)


def load_levels(path: str | Path | None = None) -> list[LevelConfig]:
    """读取难度配置；文件不存在时回退到内置配置。"""
    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if not config_path.exists():
        return list(FALLBACK_LEVELS)

    with config_path.open(encoding="utf-8") as fh:
        raw = json.load(fh)

    levels = [LevelConfig(**item) for item in raw["levels"]]
    if not levels:
        raise ValueError(f"配置文件 {config_path} 中没有任何关卡")
    return levels


def find_level(levels: list[LevelConfig], key: str) -> LevelConfig:
    """按 key 找难度，找不到就抛出 KeyError，由调用方给人话提示。"""
    for level in levels:
        if level.key == key:
            return level
    raise KeyError(key)
