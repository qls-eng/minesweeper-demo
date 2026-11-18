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


# ---------- 自定义难度（F-17）----------

# 合法区间：上界按"1080p 屏上还看得清"来定，下界保证能摆下首点安全区
ROWS_RANGE = (5, 40)
COLS_RANGE = (5, 60)
SAFE_ZONE_CELLS = 9   # 首点安全区 3×3，雷必须放得下


def validate_level(rows: int, cols: int, mines: int) -> list[str]:
    """校验自定义盘面，返回错误说明列表（空列表表示合法）。

    放在 config 层而不是 UI：这样规则能单测，UI 只负责把错误文案画出来。
    """
    errors: list[str] = []

    if not (ROWS_RANGE[0] <= rows <= ROWS_RANGE[1]):
        errors.append(f"行数需在 {ROWS_RANGE[0]}–{ROWS_RANGE[1]} 之间（当前 {rows}）")
    if not (COLS_RANGE[0] <= cols <= COLS_RANGE[1]):
        errors.append(f"列数需在 {COLS_RANGE[0]}–{COLS_RANGE[1]} 之间（当前 {cols}）")

    if rows > 0 and cols > 0:
        max_mines = rows * cols - SAFE_ZONE_CELLS
        if mines < 1:
            errors.append("雷数至少为 1")
        elif mines > max_mines:
            errors.append(f"雷数最多 {max_mines}（要留出首点 3×3 安全区，当前 {mines}）")
    return errors


def make_custom_level(rows: int, cols: int, mines: int) -> LevelConfig:
    """校验通过则返回一档自定义难度；不通过抛出 ValueError（带全部原因）。"""
    errors = validate_level(rows, cols, mines)
    if errors:
        raise ValueError("；".join(errors))
    return LevelConfig("custom", f"Custom {cols}×{rows}", rows, cols, mines)
