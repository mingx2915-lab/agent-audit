# F-053 本地脱敏诊断包

- 状态：Completed
- 所属里程碑：M6
- 负责人：主代理
- 相关决定：执行 `docs/NEXT_AUTOMATED_DELIVERY_PLAN.md` 的 P2

## 用户价值

企业用户在不联网、不上传业务数据的前提下，导出一份可交给内部运维或研发的诊断 ZIP，用于定位 Desktop、Sidecar、API 和 Provider 调用失败。诊断证据不代替 Trace/Finding，也不构成业务根因结论。

## 公共契约

- API 为 `GET /api/diagnostics/preview` 与 `POST /api/diagnostics/export`；
- Preview 只返回将包含的相对类别、明确排除项、本地处理声明和建议文件名，不扫描任意用户目录；
- Export 返回内存中构建的 ZIP bytes；Web 浏览器使用标准下载，Desktop 通过原生保存对话框写入用户明确选择的目标；
- 每个 HTTP 请求产生一个无业务语义的 operation ID，以 `X-AgentAudit-Operation-Id` 响应头和结构化日志关联；不使用 Secret、Prompt 或文档内容生成 ID；
- 日志写入 `AppPaths.logs_dir`，单文件大小和保留数量有确定上限；
- ZIP 仅使用相对成员名，同一份事实投影为 `manifest.json` 和可读 Markdown。

## 范围

- 本地滚动结构化日志；
- operation ID 从 HTTP 边界进入 API/Provider 可诊断日志；
- 诊断 Preview、导出 API、Web 包含/排除清单与 Desktop 原生保存；
- 只收集允许清单内的运行元数据、脱敏日志、Sidecar 状态和 Workspace manifest 元数据；
- 针对 Credential、环境 Secret、绝对用户路径、完整 Prompt/文档正文和 SQLite/业务 JSON 的脱敏与排除测试。

## 非目标

- 不上传诊断包，不调用 telemetry 或外部工单系统；
- 不导出 Workspace 备份、SQLite、完整 Trace、Prompt、文档或 Provider 响应正文；
- 不把日志文本解释成自动根因或安全结论；
- 不扫描任意磁盘、浏览器、系统日志或其他企业应用。

## 安全边界

- 日志事件使用固定字段和类型，不写 request/response body；
- 仅从 `AppPaths.logs_dir`、Sidecar status 精确路径和 active Workspace manifest 允许字段读取；
- 导出前对所有文本成员再执行统一脱敏；检测到绝对用户路径、常见 Credential 形态或未允许字段时导出失败，不降级为原文包；
- ZIP 构建失败不写部分目标文件；Desktop 原生写入使用临时文件后原子替换。

## 实施任务

- [x] 冻结 Preview/Export DTO、ZIP manifest 与脱敏规则；
- [x] 实现有界日志、operation ID 中间件和 Provider 事件；
- [x] 实现诊断允许清单收集与 ZIP 原子生成；
- [x] 接入 Web Preview 与 Desktop 保存对话框；
- [x] 增加 Secret/正文/路径泄露、ZIP 路径与写入失败测试；
- [x] 在隔离 `AGENT_AUDIT_HOME` 实际产生 ZIP 并复核全部成员。

## 验收标准

- [x] 日志轮转上限和 operation ID 关联可重复验证；
- [x] 页面在导出前显示包含/排除项与本地处理边界；
- [x] ZIP 不含 Credential、环境 Secret、完整业务正文、SQLite 或绝对用户路径；
- [x] ZIP 包含脱敏日志、运行环境、Sidecar/Workspace 元数据和相对成员清单；
- [x] 导出不发起任何非 loopback 网络请求，取消保存时不写入；
- [x] JSON/Markdown 同源，不声称自动根因或 Finding 结论；
- [x] 定向测试、E2E、typecheck/build、Python/Rust 回归与 diff-check 通过。

## 验证证据

- Python 全量：`.venv\\Scripts\\python.exe -m pytest -q` → `769 passed, 9 skipped, 1 warning`；
- Browser E2E：`npx playwright test --reporter=line` → `36 passed`；F-053 定向 `2 passed`；
- Web/Contracts/Desktop TypeScript：`npm run typecheck` 通过；生产 Web build 通过（仅既有 chunk size warning）；
- Rust：`cargo test --lib` → `8 passed`，`cargo check` 与 `rustfmt --check` 通过；
- 冻结 Sidecar：SHA-256 `631FBFC5587DBB3E43B8BD07D176FED0D31696FF7697D7FCD64E654C474B5DB3`；隔离 home 启动后 `ready`，health/preview/export 均为 200，ZIP 版本 `0.1.1`，进程残留 `0`；
- Windows release：`.tools/cargo-target-release-f053/release/agent-audit-desktop.exe` 真实启动、Workspace 创建、诊断导出与精确进程树清理通过；NSIS 为 `.tools/cargo-target-release-f053/release/bundle/nsis/知盾 AgentAudit_0.1.1_x64-setup.exe`，SHA-256 `DF28BD71E7C5EA2491884D7B680D105913F31BAB8B1677814251A2726C388CA8`；
- 真实冻结验收曾暴露 FastAPI lifespan 覆盖旧 startup hook，导致 status 永久 `starting`；已修为组合 lifespan，并在 Rust 壳强制本次端口 ready-file 与 health 双门验收。
