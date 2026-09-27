# F-051 一键验收与发布证据包

- 状态：Completed
- 所属里程碑：M6
- 负责人：主代理
- 相关决定：执行 `docs/NEXT_AUTOMATED_DELIVERY_PLAN.md` 的 P0；P1–P5 只记录、不并行实现

## 用户价值

用一条显式命令生成与当前版本一致、可离线打开、可追溯且诚实标注边界的比赛验收证据，减少人工整理数字、截图和报告造成的漂移。

## 范围

- 新增版本化 Release Evidence manifest、runner/CLI 与同源 JSON、Markdown、HTML；
- 索引明确提供的测试结果、截图和桌面构建产物，并在隔离 Workspace 中生成受控 Acceptance/Finding/Replay 证据；
- 对证据包内文件生成 SHA-256；
- 自动标注 real、controlled_test、not_provided、not_verified 等 provenance；
- 增加隔离的 Playwright 证据截图用例，不修改业务结论。

## 非目标

- 不自动调用真实模型、企业 Gateway 或外部目标；
- 不自动安装/卸载软件；P1 留给 F-052；
- 不实现日志诊断包、schema migration、Linux 发布或 SBOM；
- 不把 Test-only Provider、配置字符串或图片当成真实业务验收；
- 不制作 PPT、视频或宣传文案。

## 前后端与数据影响

- Web：只增加 test-only 截图定位或必要的可访问选择器，不新增用户业务入口；
- API/CLI：新增离线证据生成模块与显式 CLI；
- Contracts：只有跨语言证据 manifest 确有需要时才增加；优先使用 Python DTO；
- Data/Model/Tool：只读显式工件并使用 Runner 创建的隔离 Workspace；只触发显式标记的 Test-only Provider、合成数据与 Mock Tool，不读取默认用户 Workspace，不请求真实模型或外部系统。

## API 或交互契约

- 建议 CLI：`agent-audit release-evidence --output-dir <dir> [--input-manifest <json>]`；
- 输出目录为 `<output-dir>/<run-id>/`，不得覆盖既有非空 run；
- `summary.json` 是唯一结构化事实源，HTML/Markdown 必须从同一对象生成；
- 缺失项使用显式状态，不得推断；错误返回非零退出码且保留可读诊断，不写伪完成 summary；
- 输入 manifest 中所有文件必须显式列出，禁止递归抓取用户目录。

## 实施任务

- [x] 冻结 DTO、provenance、CLI 和目录契约；
- [x] 实现隔离 runner、同源三格式渲染和 checksum；
- [x] 增加截图证据与业务工件索引；
- [x] 增加 Secret、绝对用户路径、缺失工件和不可变目录测试；
- [x] 生成当前 Windows release 的实际证据包并复核；
- [x] 更新项目状态和验收证据。

## 验收标准

- [x] 同一 run 的 JSON/Markdown/HTML 数字、状态和 provenance 一致；
- [x] 未提供真实模型、Linux、企业 Gateway 或安装证据时明确显示未验证；
- [x] 生成过程不发真实/外部 Provider 请求、不修改默认 Workspace、不覆盖旧 run；受控 Provider 在 provenance 中明确标为 `controlled_test`；
- [x] Secret、认证 Header、完整正文、用户主目录和来源绝对路径不进入输出；
- [x] 截图来自专用 Playwright 运行且对应真实页面状态，不使用静态假截图；
- [x] checksums 可复算，manifest 只索引当前 run 的相对路径；
- [x] Python、Playwright、typecheck/build、Desktop 相关回归和 diff-check 通过。

## 验证证据

- 一键命令：`.venv\\Scripts\\python.exe apps/api/scripts/build_release_evidence.py --output-dir artifacts/release-evidence --run-id f051-windows-20260830 --cargo .tools/rust-standalone/Rust/bin/cargo.exe --desktop-artifact .tools/cargo-target-release-f050/release/agent-audit-desktop.exe --installer-artifact .tools/cargo-target-release-f050/release/bundle/nsis/知盾 AgentAudit_0.1.0_x64-setup.exe --sidecar-artifact apps/desktop/src-tauri/binaries/agent-audit-sidecar-x86_64-pc-windows-msvc.exe`
- 结果：`artifacts/release-evidence/f051-windows-20260830/summary.json` 为 `passed`，14/14 证据项通过；包含 Python、typecheck/build、专用 Playwright、Cargo check/test、四张真实页面截图、Desktop EXE、NSIS、Sidecar 与真实 Desktop smoke。
- 独立复核：19 个 `checksums.txt` 条目重算零差异；证据文本中当前用户主目录与常见 Secret 模式命中均为 0；验收后无 `agent-audit*` 进程残留。
- 定向自动测试：F-051 unit/CLI/orchestrator `33 passed, 2 skipped`；两个 skip 均为当前 Windows 权限不允许创建 symlink 的诚实环境 skip；专用截图 Playwright `3 passed`。
- P0–P5 闭环补齐后，显式 Test-only Release Evidence Provider 实际执行生产 Scan → 1 个 Critical Finding → 同 Plan Replay passed，再运行真实 `AcceptanceRunner` 24 Case，从同一 SQLite 读回 Scan/Replay/Acceptance。证据包现在包含 `findings/`、`replay/`、`acceptance/` 下共 6 份最小 JSON/Markdown，不包含消息正文、Tool 参数或完整 Trace。
- 闭环预演：`artifacts/release-evidence/p0-p5-closure-preflight-20260831/summary.json` 共 21 项，20 项 passed；唯一非 passed 为真实 F-056 供应链摘要仍有 `findings`，因此总结果诚实为 `failed`，而非证据生成器故障。
- 本轮全量回归：Python `867 passed, 10 skipped, 1 warning`，Playwright `36 passed`，根 typecheck/build、Rust check/10 tests/rustfmt、compileall 与 diff-check 通过。

## 实施记录

- F-051 只做 P0。Windows 安装生命周期、诊断包、迁移、Linux 和 SBOM 分别保留给 F-052 至 F-056。
