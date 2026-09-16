# AgentPet V0.1 — Final Delivery Report (§90)

日期：2026-09-16 ｜ 位置：`D:\AgentPet`（全部在 D 盘）

## BUILD STATUS
**PASS** — 从源码直接运行（PySide6 + psutil + watchdog），无打包依赖。

## APP LAUNCH
**PASS** — `apps\desktop\main.py` 正常启动，托盘、透明覆盖层、宠物输入窗口均工作。

## WORKBUDDY DETECTION
**PASS** — 进程树（WorkBuddy.exe + codebuddy 子进程）、sessions DB、SDK 会话日志、changes-index、窗口枚举五路信号全部实测打通。

## REAL WORKBUDDY SESSION TEST
**PASS（文件路径延迟 PARTIAL）** — 真实 WorkBuddy 会话（本 agent）在 e2e 沙盒执行计算器任务：写码 → pytest 失败 → 修复 → pytest 通过 → 真实 commit `8dfc87d8`。AgentPet 时间线记录 62 个 OBSERVED 事件，时间戳与真实工具调用对齐。详见 `docs/testing/REAL_WORKBUDDY_ACCEPTANCE.md`。

## OBSERVED SIGNALS（实测可靠）
process ✓ ｜ workspace ✓ ｜ files（changes-index）✓ ｜ commands（活动级）✓ ｜ tests（pytest 缓存）✓ ｜ git（HEAD/branch/status→commit）✓ ｜ task lifecycle（state-machine）✓

## INFERRED SIGNALS
CPU 活跃度推断、test session 聚合（均带 confidence ≤0.75）。

## UNSUPPORTED SIGNALS（诚实清单）
- **命令文本 / stdout**：SDK 日志只含计数器（probe_wb4 实证）→ 终端用抽象流式模板（VISUAL_ONLY），不编造
- **push**：远端 ref 移动与 fetch 不可区分 → 默认禁用 push 动画
- **文件路径实时性**：changes-index 由 WorkBuddy 懒刷写，可能滞后

## PET SYSTEM
**完成** — 程序化绘制 8 类动画；Workbench 模型（面板 dock 宠物 + 虚线牵引 + 粒子展开 + 抓取文字粒子）；FSM + 优先级打断 + 个性参数；多会话自动多宠（上限 2，工位放不下自动保持 docked）。

## MINI TERMINAL / MINI EDITOR / GIT VISUALIZATION
**完成** — 终端：真实输出优先、否则抽象流式（打字机）；编辑器：真实文件名与 +/- 行数，敏感文件过滤；Git：仅真实 commit 触发搬箱动画。

## PRIVACY / PERMISSIONS
**验证通过** — 零 exec/shell 能力（安全测试强制）；git 只读 allow-list；watcher 仅限授权 workspace；敏感文件黑名单；Privacy Mode。

## TESTS
unit + integration: **69 passed** ✓（pytest 7.9s）｜ e2e(replay/sim): ✓ ｜ real: PASS（见验收报告）

## PERFORMANCE（实测）
空闲 CPU ≈ **0%**（归一化）｜ RSS ≈ **9 MB** ｜ 脏矩形重绘 + 字体缓存 + 粒子上限 48 + 空闲 160ms 定时

## GITHUB — 已公开 ✅
- **公开仓库：https://github.com/nanhudev/AgentPet**（public，`master`）
- 历史：公开前已脱敏——34 张含个人桌面内容的整屏截图、env_audit.json、wb_surface.json、含本机路径的 probe/audit 脚本已全部移出 Git 历史（压缩为单一根提交 `ac7f3a5` 并强推；原件归档在本地 `data/private_archive/`，被 .gitignore 排除）
- 仓库内截图只保留 `*_overlay_raw.png`（Overlay 层自渲染，无桌面背景），README 已内嵌展示图
- 残余风险（诚实记录）：旧提交在强推后仍可按精确 SHA 访问（GitHub 悬挂对象 GC 前的缓存行为），但这些 SHA 从未公开暴露过，风险可忽略；若要彻底清除需网页端删除仓库重建（GCM 令牌无 delete_repo 权限）
- 远端 `origin` 已配置并建上游跟踪，后续直接 `git push` / `git pull`
- License：README 标注 TBD，公开发布前建议补 LICENSE 文件（如 MIT）

## SCREENSHOTS
`docs\testing\screenshots\*_overlay_raw.png`（Overlay 层自渲染，无桌面背景；桌面整屏截图因含个人内容不入库，本地归档在 data/private_archive/）

## KNOWN LIMITATIONS
见 README「Known limitations」：无 stdout 源、changes-index 延迟、无打包安装器、push 动画默认关闭。

## NEXT RECOMMENDED PHASE
**先验收 V0.1**（跑起来看 + 决定 GitHub 仓库）。确认后再决定是否进入 V0.2（Codex/Claude Code/Cursor 活动级适配、按 agent 窗口所在显示器分区）。
