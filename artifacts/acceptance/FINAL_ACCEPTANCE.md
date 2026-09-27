# 最终验收摘要

- 项目：知盾 AgentAudit
- 数据边界：SYNTHETIC / DEMO ONLY；仅覆盖仓库内受控企业知识助手靶场
- 当前功能：F-026 桌面壳与可移植 Workspace 基础（仍为 `In Progress`）
- 验收日期：2026-08-27
- 当前结论：F-026 的当前 Windows 构建机实现、release Desktop、Sidecar 与 NSIS current-user 安装路径已有真实证据；另一台无仓库、无 Python/Node 的干净 Windows 尚未验证，因此不能宣称 F-026 已完成，F-027 未启动。
- 本次记录更新只整理既有验收事实，不执行新的模型 Run，不生成或替换截图。

## 当前机自动与静态验收

| 检查 | 命令/对象 | 当前结果 |
|---|---|---|
| Python 全量测试 | `.venv\Scripts\python.exe -m pytest -q` | `416 passed, 1 skipped`；未指定真实桌面 artifact 时的 1 个 skip 是诚实的 Windows bundle smoke 边界 |
| Playwright 浏览器 E2E | `npm run test:e2e` | `7 passed`；覆盖 Guided 主链、Finding/Replay、Contract、Acceptance、窄屏和 Provider 错误路径 |
| Python 编译 | `.venv\Scripts\python.exe -m compileall -q apps/api/src tests` | 通过 |
| Python 依赖一致性 | `.venv\Scripts\python.exe -m pip check` | `No broken requirements found` |
| TypeScript/Vue | `npm run typecheck` | 通过 |
| Web production build | `npm run build` | 通过；保留既有 Vite 大 chunk warning，不影响构建 |
| Rust 检查 | 项目内 Rust/MSVC 工具链 `cargo check` | 通过 |
| Rust 格式 | 项目内 `rustfmt --check` | 通过 |
| Diff 格式 | `git diff --check` | 通过 |

自动测试主要使用进程内 Test Double；E2E 真实启动 Web/API/SQLite，只替代外部模型和检索波动，不读取真实模型密钥。以上数字是当前 F-026 工作树基线，不代表任意生产 Agent 或真实企业系统的安全保证。

## 当前机 Desktop / Sidecar / 安装器证据

以下均为当前 Windows 构建机已执行的证据，不是静态配置推断：

- 指定本次 release Desktop `.exe` 后，Desktop 配置与真实启动 smoke 为 `7/7 passed`；未指定 artifact 时的 skip 不被冒充为通过。
- PyInstaller one-file Sidecar 真实启动后进入 `ready`；`GET /api/health` 返回 `200`；packaged `demo-seed` 首次创建完整默认 Workspace 和 manifest。
- Sidecar 只监听 `127.0.0.1`；按所属 PID 执行 tree-kill 后无 Sidecar 残留，且不会关闭外部 Ollama。
- release Desktop 启动后创建默认 manifest 并保持运行；关闭窗口后 Desktop 与 Sidecar 均无残留。
- NSIS current-user 安装包在当前用户环境完成安装、启动、首次 Workspace seed、退出和卸载；安装目录与注册表项清理完成。
- 可交付安装包副本：`artifacts/desktop/generated/知盾 AgentAudit_0.1.0_x64-setup.exe`。该目录和 Sidecar 二进制为可重建产物，不提交 Git。

当前 Windows 的默认数据边界为 `%LOCALAPPDATA%\AgentAudit`，默认 Workspace 为 `%LOCALAPPDATA%\AgentAudit\workspaces\default`；本次 F-026 桌面路径不依赖开发仓库固定盘符。

## 已保存的真实 Ollama 质量证据

以下是此前已保存的本地 Ollama `qwen3:8b` Acceptance Run，本次文档更新没有重新执行：

| 证据 | 结果 |
|---|---|
| Run | `acceptance_76401aeb7592` |
| Provider Readiness | `ready` |
| 固定 Ground Truth | `22/24 matched` |
| Detection Recall | `1` |
| False Positive Rate | `0` |
| Policy Violation Accuracy | `0.95` |
| Replay Pass Rate | `1` |
| Provider calls / tokens | `39` / `21,870` |
| Gate / verdict | `failed` |

`22/24` 与 `Gate failed` 是真实小模型边界，必须原样保留。两个差异是实际 Tool Authorization 为 `blocked`，而 expected outcome 为 `completed`；Finding 与实际安全结论仍按真实 Trace 记录。没有通过重试、fallback、修改 Ground Truth 或调用 DeepSeek 隐藏差异。

Provider Readiness 是兼容性证据，不直接成为 Finding 或 Gate verdict；固定 24 Case Acceptance 是高级质量证据，不能替代五分钟 Guided Source→Sink → Critical Finding → 同 Plan Replay 主线。

## 当前验收清单

- [x] 当前 Windows 构建机完成 Python `416 passed, 1 skipped`、7 个 Playwright E2E、compileall、pip check、typecheck、production build、cargo check、rustfmt 和 diff check。
- [x] 指定真实 release `.exe` 后完成 Desktop artifact `7/7` 启动 smoke。
- [x] 完成 Sidecar ready/health、packaged seed、Workspace manifest、tree-kill 和无残留检查。
- [x] 完成 NSIS 当前用户安装、启动、首次 Workspace seed、退出和卸载；安装目录与注册表项清理。
- [x] 保留此前本地 Ollama `qwen3:8b` 的 `22/24 matched` 与 `Gate failed` 原始边界。
- [ ] 在另一台无仓库、无 Python/Node 的干净 Windows 安装并复核；当前没有可用 Windows Sandbox 或第二台目标机。
- [ ] F-026 完成标记；在干净 Windows 证据补齐前不得勾选，不启动 F-027。

## 截图与历史工件

本次更新不新增、不替换截图。以下文件是此前本地 Ollama 现场的历史证据，不能当作当前干净 Windows 或新一轮桌面运行截图：

1. `artifacts/acceptance/generated/2026-08-26-ollama-resource-replay.png`：资源 Replay 的历史 failed → passed 与 Finding 证据；
2. `artifacts/acceptance/generated/2026-08-26-ollama-replay-report.png`：历史 AttackChainReport 摘要与下载入口；
3. `artifacts/acceptance/generated/2026-08-26-ollama-tool-trace.png`：历史工具授权与 Tool Call Trace；
4. `artifacts/acceptance/generated/2026-08-26-ollama-benchmark.png`：历史固定 Case 与指标。

截图不得包含模型密钥、真实个人信息或其他应用窗口。不存在当前干净 Windows 的新截图，不以静态图片替代目标机安装证据。

## 未验证与不声明事项

- 尚未在第二台无仓库、无 Python/Node 的干净 Windows 重做安装、首次 Workspace、桌面启动和退出清理；因此 F-026 仍为 `In Progress`，不能宣称桌面交付已完成。
- F-027 首次启动向导、Ollama 自动发现、模型选择/下载尚未实现；F-026 仍要求本地 Ollama 显式 Provider 配置，不自动探测、不 retry/fallback。
- 当前开发机没有 Docker CLI，Compose 尚未实际 build/up；
- 未发送真实 DeepSeek 请求；本地 Ollama 22/24 只适用于固定合成靶场；
- 不声明 PostgreSQL/pgvector、真实 IAM/CRM、任意外部扫描、真实邮件发送、真实企业数据读取或生产级性能；
- 不把历史 24 Case 受控 Test Double 结果、历史 Ollama 运行或截图说成当前干净 Windows 的实时结果。
