# F-024 最小 CLI / CI 安全门

- 状态：Completed
- 所属里程碑：M5
- 负责人：主代理监督；Core/CLI/Test Luna Max 按互斥范围实现
- 相关决定：`docs/M5_SOFTWARE_PRODUCTIZATION_PLAN.md`、D-004、D-009

## 用户价值

将现有 24 Case 合成靶场 Benchmark 变成上线前可以重复运行的工程验收命令。开发者或 CI 能得到明确的 0/非 0 退出码、机器可读 JSON 和人类可读 Markdown，并知道是哪个确定性指标或 Case 回退，而不是只在网页里人工观察。

## 范围

- 新增仓库内 CLI：`agent-audit ci-gate --output-dir <dir>`，等价支持 `python -m agent_audit_api.cli ci-gate ...`；
- 每次实际执行固定 24 个 Ground Truth Case，复用现有 Contract、Provider、Retriever、Assistant、Planner、Replay 和 Benchmark Runner；
- 固定 Gate 检查：全部 Case matched、Detection Recall=1、False Positive Rate=0、Policy Violation Accuracy=1、Replay Pass Rate=1；
- Benchmark 完成后始终生成 `ci-gate.json` 与 `ci-gate.md`，Gate passed 返回 0，指标回退返回 1；配置、Provider、Retriever 或文件边界错误返回 2 并输出可诊断错误；
- 结果包含 Contract id/version、Runtime Provider/Model/Retriever、24 Case 的 expected/actual、Finding categories、Replay outcome/status、Provider usage 和全部指标；
- HTTP Benchmark 与 CLI 复用同一 Benchmark Runtime 组装函数，避免两套业务链；
- Provider 与 Retriever 继续由现有本地环境显式配置，不自动 fallback；本机真实验收使用 Ollama `qwen3:8b`，不调用 DeepSeek。

## 非目标

- 不扫描任意 URL、仓库、Prompt 文件、线上 Agent 或外部 Endpoint；
- 不允许 CLI 输入任意 Case、任意 Contract、任意阈值来绕过固定门槛；
- 不建设 CI 平台、队列、Dashboard、Webhook、GitHub App 或云端历史；
- 不把 LLM 主观评分作为 Gate 条件，不在失败后重试或修补模型输出；
- 不将 token/cost 未知当作失败，不虚构价格或使用量；
- 不把 JSON/Markdown 摘要当作完整生产安全保证。

## 前后端与数据影响

- CLI：新增 `ci-gate` 命令、固定退出码和标准输出摘要；
- Core：新增 `CIGateResult`、固定 `CIGateCheck`、Markdown Renderer 与 Artifact Writer；
- API：Benchmark route 复用共享 Runtime 组装函数，响应契约不变；
- Web：本功能不新增页面；F-025 再把 CLI/Acceptance Run 统一进历史 UI；
- Data：只读取现有 `data/demo` 24 Case、Contract 和合成资产；
- Provider/Tool/Sink：执行现有受控 Mock Tool/Mock Sink，不访问真实企业系统或真实邮件。

## CLI 与工件契约

```powershell
$env:AGENT_AUDIT_LLM_PROVIDER = "ollama"
$env:OLLAMA_MODEL = "qwen3:8b"
agent-audit ci-gate --output-dir artifacts/acceptance/generated/ci-gate
```

固定输出：

```text
<output-dir>/ci-gate.json
<output-dir>/ci-gate.md
```

`CIGateResult`：

```text
id / generatedAt / status=passed|failed
contractId / contractVersion
runtimeSnapshot
checks[]: id / actual / expected / passed
failedCheckIds[]
benchmark: BenchmarkResult
```

退出码：

- `0`：Benchmark 完成且固定 Gate 全部通过；
- `1`：Benchmark 完成但至少一个固定 Gate 失败；
- `2`：参数、Provider、Retriever、数据或工件写入错误，无法形成有效 Gate 结论。

JSON 必须是 `CIGateResult` 的 camelCase 序列化；Markdown 只能从同一个 Result 纯生成，不能重新判断。输出目录可以创建，但不得删除目录内其他文件。

## 实施任务

- [x] ~~主代理锁定固定命令、Gate 指标、退出码、工件和无外部扫描边界~~
- [x] ~~Core Luna Max 实现共享 Benchmark Runtime、Gate DTO/判断、JSON/Markdown 工件~~
- [x] ~~CLI Luna Max 实现 argparse 入口、console script 与真实运行接线~~
- [x] ~~Test Luna Max 覆盖 pass/fail/error、工件一致性、真实 Runner 注入与既有 API 回归~~
- [x] ~~主代理审查无任意输入/阈值绕过、无 fallback，并运行本地 Ollama 真实 CLI~~
- [x] ~~主代理运行全量自动验收与 CLI subprocess 验收~~
- [x] ~~更新 README、功能/状态/架构/验收文档并提交 Git~~

## 验收标准

- [x] CLI 只接受 `ci-gate` 与输出目录，不接受 URL、任意 Case、Contract 或阈值；
- [x] CLI 与 `/api/benchmarks/run` 复用同一 Runtime 组装函数和真实 24 Case Runner；
- [x] 五项固定 Check 只从实际 `BenchmarkResult` 计算，expected 字段不能直接决定 Gate；
- [x] 全部通过返回 0；任一 Check 回退返回 1，并列出精确 failedCheckIds；
- [x] 运行边界错误返回 2，不自动重试、不 fallback、不生成伪造 passed 工件；
- [x] JSON 可重新验证为 `CIGateResult`，Markdown 的状态、Contract、Runtime、指标、Case 与 JSON 一致；
- [x] 结果包含实际 Finding categories 与 Replay Case outcome/status；
- [x] 输出目录创建不删除或覆盖目录内无关文件；本次两个固定文件可由用户明确重跑覆盖；
- [x] Provider usage 缺失时 token/cost 保持 null，Gate 不因未知成本失败；
- [x] 本地 Ollama 实跑生成两个工件，退出码和内容如实记录；不调用 DeepSeek；
- [x] 现有 API/Web/Guided/Readiness/Contract Editor/Benchmark 行为不回退；
- [x] pytest、compileall、pip check、typecheck、build、E2E、diff check 通过。

## 验证证据

- F-024 定向：`25 passed`；全量 Python：`335 passed`（仅 1 个已知 Starlette/httpx 弃用警告）；
- Browser E2E：`5 passed`；Python `compileall`、`pip check`、contracts/web `typecheck`、Web production build 与 `git diff --check` 通过；
- console script 以 editable install 实际注册，`agent-audit ci-gate --help` 通过；module subprocess、退出码 0/1/2、固定工件和禁止任意输入均有自动验收；
- 本地 Ollama `qwen3:8b` + BGE 真实 CLI 生成 `artifacts/acceptance/generated/ci-gate/ci-gate.json` 与 `ci-gate.md`，退出码为 `1`；22/24 matched，Detection Recall=1、FPR=0、Policy Violation Accuracy=0.95、Replay Pass Rate=1，38 次 Provider 调用、21821 tokens，成本保持 null；
- 两个 mismatch 均已正确产生 `resource_authorization_bypass` Finding，且 outcome 正确；差异是模型额外触发了被 Tool Authorization 阻断的调用，使 actual execution status 为 `blocked` 而非 Ground Truth 的 `completed`。系统未重试、未 fallback、未改 expected 来伪造通过，且未调用 DeepSeek。

## 实施记录

- 2026-08-27：F-023 完成后按用户授权直接进入；F-024 只把现有合成验收工程化，不扩大扫描目标。
- 2026-08-27：共享 Benchmark Runtime、固定五项 Gate、CLI、JSON/Markdown 工件、API 回归与真实 Ollama 验收完成；真实模型回退被安全门如实拦截并保留证据。
