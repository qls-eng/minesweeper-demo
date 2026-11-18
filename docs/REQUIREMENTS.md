# 需求规格说明（SRS）

| 项 | 内容 |
| --- | --- |
| 项目 | Minesweeper Demo（Python + pygame） |
| 版本 | v0.1 |
| 日期 | 2026-11-18 |
| 状态 | 基线版，改动需走变更记录 |

> 说明：本文档是这个项目的**第一份产物**。先定"做什么、怎么算做完、明确不做什么"，再谈架构和代码。
> 迭代时新需求先进这里，再进 `DEV_PLAN.md` 排期。

---

## 1. 背景与目标

### 1.1 背景

- 个人技术练习：Python + pygame 是从未接触过的技术组合，需要一个规则清晰、可快速验证的项目上手；
- 作品集用途：作为"经典算法 Demo"之一，用来展示**分层设计与可测试性**，不作为主打项目。

### 1.2 可衡量的目标

| 编号 | 目标 | 判定方式 |
| --- | --- | --- |
| G1 | 能完整玩一局，操作无明显卡顿 | 9×9 与 16×30 各手动玩一局，点击响应 < 100ms |
| G2 | 规则与渲染解耦 | `core.py` 中不出现 `import pygame`；规则层单测 ≥ 15 条 |
| G3 | 换难度 / 换配色不需要改逻辑代码 | 只改 `config/levels.json` 与 `theme.py` 即可生效 |
| G4 | 零版权风险 | 仓库内无第三方图片/音频/字体文件 |

### 1.3 非目标

本项目不追求完整商业游戏的体验（动画、音效、美术、成就系统），也不追求玩法创新。

---

## 2. 用户与使用场景

| 角色 | 场景 | 关注点 |
| --- | --- | --- |
| 本人（开发者） | 本地运行，练习与调试 | 逻辑可测、易改 |
| 面试官 / 同学 | 打开仓库看 demo 与代码 | 结构是否清楚、能不能讲出设计理由 |

运行环境：单人、离线、鼠标 + 键盘，桌面端。

---

## 3. 功能需求

优先级采用 MoSCoW：Must 必须实现，Should 应该实现，Could 可选。

| 编号 | 需求 | 优先级 | 验收标准（可测试） |
| --- | --- | --- | --- |
| F-01 | 支持三档难度并可通过启动参数选择 | Must | `--level beginner/intermediate/expert` 均可启动；棋盘尺寸与雷数与配置一致 |
| F-02 | 首次点击必不踩雷 | Must | 任意随机种子下，第一次 `reveal` 后状态为 PLAYING；连测 50 个种子不失败 |
| F-03 | 点到空白格时连锁展开连通空白区域 | Must | 构造"数字墙"棋局后展开区域格数符合人工推演；展开过程不使用递归 |
| F-04 | 右键插旗 / 取消旗 | Must | 旗格不可被翻开；旗格不被连锁展开；剩余雷数随旗数变化 |
| F-05 | 计时 | Should | 未开始显示 00:00；首点后开始计时；终局后数值冻结 |
| F-06 | 胜负判定 | Must | 非雷格全开即胜；踩雷即负并亮出全部雷 |
| F-07 | 一键重开 | Must | 重开后状态回 READY，棋盘与计时清零 |
| F-08 | 难度参数外置为配置 | Should | 修改 JSON 后重启生效，无需改 `.py` |
| F-09 | 无窗口自检 | Should | `--smoke` 在无显示器环境可跑完并产出截图，退出码为 0 |
| F-10 | HUD 显示剩余雷数与用时 | Must | 两处数值随操作实时更新 |
| F-11 | 结束状态给出明确反馈 | Could | 胜利/失败有遮罩与提示文案 |

---

## 4. 非功能需求

| 编号 | 类别 | 要求 |
| --- | --- | --- |
| N-01 | 性能 | 9×9 与 16×30 均稳定 60 FPS；16×30 单次洪水填充 < 5 ms |
| N-02 | 可测试性 | 规则层不依赖 GUI；单测总耗时 < 1 s，可在 CI 直接跑 |
| N-03 | 可维护性 | 单个源文件建议 < 250 行；`ui.py` 中不出现规则判断（如"是不是雷"） |
| N-04 | 兼容性 | Windows / macOS / Linux 均可运行；Python ≥ 3.10 |
| N-05 | 合规性 | 不含第三方素材；README 声明"学习演示、不商用" |
| N-06 | 可移植性 | 规则层可被其他前端（终端 / Web）直接复用 |

---

## 5. 约束

| 类型 | 约束 | 来源 |
| --- | --- | --- |
| 技术栈 | Python + pygame | 本人选定"方案3"，首次尝试该技术栈 |
| 人力 | 单人开发，业余时间 | — |
| 依赖 | 仅 pygame 一个第三方运行时依赖 | 降低环境问题 |
| 素材 | 只能使用自绘图形或明确可商用素材 | 版权红线 |
| 无联网 | 不做账号、云存档、联机 | 范围控制 |

---

## 6. 明确不做（范围外）

写清"不做什么"和写清"做什么"同样重要，避免范围蔓延：

- 联机对战 / 云端排行榜
- AI 自动求解、智能提示
- 移动端移植
- 皮肤商店、成就系统、关卡编辑器
- 复杂动画与音效（首版）
- 直接复刻原作的美术风格或界面布局

---

## 7. 需求追踪矩阵

需求 → 实现位置 → 守它的测试。任何一个 Must 需求如果右边一栏为空，说明还没被验证。

| 需求 | 实现位置 | 测试 / 验证手段 |
| --- | --- | --- |
| F-01 | `config/levels.json`、`config.load_levels` | `ConfigTest.test_levels_loaded_from_json` |
| F-02 | `core.Board._place_mines` | `FirstClickTest.test_first_click_never_hits_mine`（50 种子） |
| F-03 | `core.Board._flood_reveal` | `FloodTest.test_flood_stops_at_number_wall`、`test_zero_cell_neighbors_are_opened` |
| F-04 | `core.Board.toggle_flag` | `FlagTest` 三条用例 |
| F-05 | `game.Game.elapsed` / `_sync_timer` | `GameTest.test_timer_starts_on_first_click` |
| F-06 | `core.Board.reveal`、`_reveal_all_mines`、`_all_safe_cells_open` | `EndGameTest` 三条用例 |
| F-07 | `game.Game.restart` | `GameTest.test_restart_resets_board` |
| F-08 | `config.load_levels`（读取 JSON） | `ConfigTest.test_levels_loaded_from_json` |
| F-09 | `ui.App.smoke` + `main.py --smoke` | 每次提交前手动执行 `python main.py --smoke` |
| F-10 | `ui.App._draw_hud` | `--smoke` 截图目视 + `Game.mines_left` 用例 |
| F-11 | `ui.App._draw_banner` | `--smoke` 构造终局截图目视 |
| N-01 | `ui.App.FPS`、`core._flood_reveal` | expert 档手动实测 |
| N-02 | `core.py` 无 pygame 依赖 | `python -m unittest discover -s tests -t . -v` |
| N-03 | 分层结构 | 提交前自查 + code review 清单 |
| N-04 | 无平台相关硬编码（DPI 调用已 try/except 包裹） | 手动在 Windows 验证 |
| N-05 | `assets/README.md` 声明 | 目视检查仓库内容 |
| N-06 | 规则层仅依赖 `config.LevelConfig` | 分层自查 |

---

## 8. 假设与风险

| 风险 | 影响 | 应对 |
| --- | --- | --- |
| pygame 在小屏幕上窗口过大（expert 30 列） | 操作不便 | 允许后续加窗口缩放或滚动；当前先接受 |
| 手感类需求（点击反馈、和弦）难以自动化验证 | 只能人工确认 | 手感调整放在 v0.2，验收靠人工玩三局 |
| 单人项目容易范围蔓延 | 项目做不完 | 本文档第 6 节作为边界，新功能先入需求再排期 |

---

## 9. 变更记录

| 日期 | 版本 | 变更 | 原因 |
| --- | --- | --- | --- |
| 2026-11-18 | v0.1 | 建立需求基线：11 条功能需求 + 6 条非功能需求 + 追踪矩阵 | 补齐工程流程中缺失的需求分析环节 |
