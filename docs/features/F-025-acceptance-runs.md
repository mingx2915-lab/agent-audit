# F-025 统一 Acceptance Run 与历史对比

- 状态：Completed
- 所属里程碑：M5
- 负责人：主代理监督；Backend/Frontend/Test Luna Max 按互斥范围实现
- 相关决定：`docs/M5_SOFTWARE_PRODUCTIZATION_PLAN.md`、D-004、D-009

## 用户价值

把 Provider Readiness、Retrieval Evaluation、Multi-Identity Differential、24 Case Benchmark、核心 Source→Sink Scan/Finding/Replay 组织成一次可保存、回看、对比和导出的上线前验收记录。开发、安全和评委能回答“当时用了什么 Contract/模型，真实跑了什么，哪些指标或 Case 变好/变差，证据能否交付”，而不需从多个临时页面手工拼接。

## 范围

- 新增用户显式发起的固定 Acceptance Run，串行执行当前 Runtime/Contract 下的 Provider Readiness、固定 Retrieval Evaluation、两个标准 Differential 任务的默认 Profile、固定 24 Case Benchmark/CI Gate、固定 `plan_sink_confidential_external` Scan 和同 Plan Replay；
- 一次执行全部使用同一 active Contract 快照、同一组 Contract-derived Plan 快照、同一 Target/Attack Provider 配置和同一 Retriever；
- Provider Readiness 仍是兼容性证据，不作安全硬门；Acceptance verdict 直接复用 F-024 `CIGateResult.status`，不新增 LLM 主观分数；
- 完整成功后才以 append-only 方式写入本地 SQLite；任一必需步骤异常都显式返回错误且不保存半成品；
- 历史按完成时间倒序查询，可查看完整不可变快照，并与上一次历史 Run 作确定性对比；
- 对比至少包含 Contract/Runtime/Readiness/Gate 状态变化、五项 Gate 指标变化、新增/解决的 mismatch Case、failed Check 和 Finding category；
- 每个 Run 提供 JSON 与 Markdown 两个固定证据导出；Markdown 仅从已保存 Run 纯生成，不重跑 Provider 或重新判定；
- Web 在“高级验收 / 证据与评测”区提供明确的“运行完整验收”、历史列表、本次摘要、上次对比和两种下载，不抢占 Guided Audit 首屏主线。

## 非目标

- 不建调度器、队列、后台任务、WebSocket/SSE、定时扫描或云端同步；
- 不支持任意 Endpoint、Case、Contract、Plan、Profile、阈值或证据目录输入；
- 不把 Readiness 失败转换成 Finding，不把未知 token/cost 当作 Gate 失败；
- 不为小模型增加重试、fallback、Prompt 特判、JSON 修复或事后改结论；
- 不保存 credential、API Key、隐藏 Chain-of-Thought、真实邮件或真实企业数据；
- 不做多租户、账号权限、云存储、签名/哈希证明、复杂工件管理或 PPT/视频。

## 前后端与数据影响

- Web：新增独立高级验收区组件，只在用户点击时 POST；首载/刷新只 GET 历史；
- API：新增固定 Acceptance Runner、SQLite Repository、对比/渲染纯函数与五个历史/导出路由；
- Contracts：同步 Acceptance Run/Summary/Comparison DTO，不复制既有子结果契约；
- Data/Model/Tool：仅读取现有合成资产与 24 Case，调用已选 Provider、共享 BGE Retriever 和进程内 Mock Tool/Sink；
- Storage：复用 F-019 同一 SQLite 文件，新增独立 Acceptance Run 表，不改写已存 Scan History。

## API 或交互契约

### 固定 API

- `POST /api/acceptance-runs`：无 body 或 `{}`；执行一次完整验收并返回已持久化 `AcceptanceRun`；额外字段 422；
- `GET /api/acceptance-runs?limit=20`：最近历史摘要，`limit` 仅允许 1–100；
- `GET /api/acceptance-runs/{runId}`：返回完整不可变 Run，未知 ID 404；
- `GET /api/acceptance-runs/{runId}/comparison`：与该 Run 的前一个历史 Run 比较；首个 Run 的 `previous=null` 且变化集为空；
- `GET /api/acceptance-runs/{runId}/evidence.json` 与 `.md`：只投影已保存 Run，设置稳定文件名与 media type，不调 Provider。

### 领域契约

`AcceptanceRun` 至少包含：

```text
id / startedAt / completedAt / durationMs / status=completed
verdict=passed|failed
contractSnapshot / planSnapshots[] / profileSnapshots[] / runtimeSnapshot
providerReadiness
retrievalEvaluation
differentialAudits[]            # 固定两个任务，各用 defaultTargetProfileId
ciGate                           # 其 benchmark 字段是本次权威 BenchmarkResult
guidedScan                       # 固定 plan_sink_confidential_external
guidedReplay                     # 与 guidedScan 同 Plan
findingCategories[]              # 从实际 Differential/Benchmark/Scan/Replay 去重汇总
```

`AcceptanceRunSummary` 包含 Run/Contract/Runtime、Readiness/Gate/Verdict、Benchmark matched/case count、Finding 数/类别和 guided Replay status。`AcceptanceRunComparison` 包含 current/previous Summary、五项固定 Gate 指标 delta，以及 added/resolved failed Check IDs、mismatched Case IDs 和 Finding categories。对比不读 active Contract 也不调 Provider。

## 执行与错误边界

1. POST 开始时深拷贝 active Contract、Contract-derived Plans、Profiles 和 Runtime；
2. 所有子验收都使用该快照，不在中途重读可变 active Contract；
3. 必需 Source→Sink Plan 缺失时显式 422，不用其他 Plan 替代；
4. Provider/strict JSON 等边界保持既有 502/503 语义，Retriever 错误 503，Repository 错误 500；
5. 任一必需子验收异常时不写入 Acceptance History；Readiness 自身的结构化 failed Probe 是完整证据，不是异常；
6. 只保存 DTO 明文快照，不保存环境变量、credential 或隐藏思考。

## 实施任务

- [x] ~~主代理锁定固定子验收、DTO、持久化、对比、导出和无自动执行边界~~
- [x] ~~Backend Luna Max 实现 Acceptance Runner、SQLite Repository、对比/导出与 API~~
- [x] ~~Frontend Luna Max 实现高级验收历史、摘要、对比和下载交互~~
- [x] ~~Test Luna Max 覆盖不可变 Repository、真实固定 Runner、API、E2E、错误和旧主线回归~~
- [x] ~~主代理审查不重复判定、不自动执行、不保存半成品/凭据与不扩大扫描边界~~
- [x] ~~主代理运行全量自动验收，再用本地 Ollama 显式发起一次真实 Acceptance Run~~
- [x] ~~更新 README、功能/状态/架构/验收文档并分别提交 Git~~

## 验收标准

- [x] 用户显式点击一次后，后端真实完成全部固定子验收并仅追加一个 Run；页面首载/刷新不发 Provider 请求；
- [x] Run 保存 active Contract、Plans、Profiles、Runtime 与所有子结果快照，修改 active Contract 不改写历史；
- [x] Provider Readiness 结果可查看但不直接决定 verdict；verdict 与已保存 `ciGate.status` 一致；
- [x] Retrieval Evaluation 固定 6 Query、两个 Differential 任务、24 Case Benchmark、固定 Source→Sink Scan 和同 Plan Replay 全部来自真实现有链路；
- [x] Finding category 从实际结果汇总，expected/display 字段修改不能改写 actual 结论；
- [x] 重启 App 后可读取完整 Run；重复 ID 不覆盖，历史记录不可修改，SQLite 不含 credential；
- [x] 首个 Run 没有伪造 baseline；后续 Run 可确定性显示指标 delta、新增/解决 mismatch、failed Check 和 Finding category；
- [x] JSON 可重新验证为 `AcceptanceRun`，Markdown 与同一历史 Run 的 Contract/Runtime/Readiness/Gate/Case/Finding/Replay 一致，导出不增加 Provider 调用；
- [x] 任一必需步骤异常不保存半成品；错误可诊断，无重试、fallback 或伪造 passed；
- [x] Web 能运行、回看、选择历史、查看对比和下载 JSON/Markdown，390×844 可用且不破坏 Guided Audit 首屏；
- [x] pytest、compileall、pip check、typecheck、production build、Playwright E2E、diff check 通过；
- [x] 本地 Ollama 真实 Run 的状态、调用量、指标和差异如实记录，不调用 DeepSeek。

## 验证证据

- `.venv\Scripts\python.exe -m pytest -q`：373 passed，1 个既有 Starlette/httpx deprecation warning；
- `.venv\Scripts\python.exe -m compileall -q apps/api/src tests`、`.venv\Scripts\python.exe -m pip check`、`npm run typecheck`、`npm run build --workspace apps/web`、`git diff --check`：通过；production build 仅有既有的 Vite chunk-size warning；
- `npm run test:e2e`：7 passed，覆盖 Acceptance Run 显式执行、历史/详情/对比/下载、390×844，以及既有 Guided Audit、Readiness、Contract Editor 与 Provider 502 回归；
- 本地 Ollama `qwen3:8b` 单次真实 Run `acceptance_76401aeb7592` 已持久化：Readiness `ready`、24 Case 中 22 matched、Recall 1、FPR 0、Policy Accuracy 0.95、Replay Pass Rate 1、Guided Replay `passed`、39 次 Provider 调用、21,870 tokens、耗时 111,203.49 ms；
- 该真实 Run 的 Gate/verdict 均为 `failed`，失败检查为 `all_cases_matched` 与 `policy_violation_accuracy`。两个 mismatch 的 actual Finding/outcome 正确，但模型额外触发 Tool Call，导致实际执行状态为 `blocked` 而非 Ground Truth 的 `completed`；系统未重试、fallback、修改 Ground Truth 或伪造通过；
- JSON/Markdown 下载均从同一保存 Run 生成并返回稳定附件名；首个真实 Run 的 `previous=null`，未伪造 baseline；全程显式选择 Ollama，未调用 DeepSeek。

## 实施记录

- 2026-08-27：F-024 完成后按用户授权直接进入。F-025 只整合已有证据链，不新增攻击类别、外部目标或新的安全判定。
- 2026-08-27：Backend、Frontend、Test 三个 Luna Max 按互斥范围完成实现，主代理完成接口收敛、全量回归、真实本地模型运行和 Git 收口。M5 软件产品化计划至此完成。
