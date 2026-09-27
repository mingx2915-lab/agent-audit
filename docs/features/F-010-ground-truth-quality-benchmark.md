# F-010 Ground Truth 基准集与质量验收

- 状态：Done
- 所属里程碑：M3
- 负责人：主代理监督；Backend/Frontend/Test Luna 分工实现
- 相关决定：D-002、D-003、D-004、D-007、D-009、D-015

## 用户价值

让团队和评委用一组可审阅、可重复的正常/漏洞/Replay Case 检查系统是否既能发现真实违规、又不会把正常行为误报，并用统一指标证明当前实现质量，而不是只展示挑选过的单次成功结果。

## 范围

- 定义仓库内固定 `GroundTruthCase`，只使用合成 Actor、数据、Plan 与 Mock Tool；
- 默认基准集包含 6 个 Case：
  - 正常公开文档查询（secure，预期 Evaluation passed）；
  - 正常本人客户工具查询（secure，预期 Evaluation passed）；
  - Resource owner-scope Plan 执行（预期 Evaluation failed + resource Finding）；
  - Tool owner-scope Plan 执行（预期 Evaluation failed + tool Finding）；
  - Resource Plan Replay（预期 replay passed，before 含 resource Finding）；
  - Tool Plan Replay（预期 replay passed，before 含 tool Finding）；
- Ground Truth 只在执行完成后比较 `expectedOutcome` / `expectedFindingCategories`，不得传入 ContractChecker、HybridJudge、Executor 或 Replay 判定；
- 实现 `GroundTruthRunner`，复用 secure `AssistantService`、`AttackPlanExecutor` 与 `ReplayExecutor`；
- 记录每个 Case 的实际 outcome、实际 Finding 类别、是否匹配和耗时；
- 计算 0–1 比率：Detection Recall、False Positive Rate、Policy Violation Accuracy、Replay Pass Rate；记录总 `scanTimeMs`；
- 某项没有适用 Case 时比率为 `null`，不以 0 或 1 代替；
- 新增 `GET /api/ground-truth-cases` 与 `POST /api/benchmarks/run`；
- 前端提供简洁的质量验收区：运行按钮、五项指标、Case 结果表；不提前做 Dashboard 图表或报告导出；
- 单元测试、API 进程内集成测试和前端 typecheck/build。

## 非目标

- 大规模数据集、随机 Case、LLM 生成 Ground Truth、人工标注平台或数据版本系统；
- 把期望 Finding 复制为实际 Finding，或用 Case ID/名称写死实际判定；
- 独立于现有链路的第二套 Retriever、Tool、Checker、Replay 或 Provider；
- 基于单次运行调参、重试失败 Case、隐藏失败或后处理结果；
- 数据库持久化、历史趋势、Dashboard 图表、PDF/Markdown 报告或比赛材料；
- 真实邮件、外部 Endpoint 或真实企业系统；
- 自动 Semantic Review；
- 启动服务或发送真实 DeepSeek 请求。

## 前后端与数据影响

- Web：新增基准运行区、指标卡和 Case 结果表；
- API：新增固定 Ground Truth 列表与一次完整基准运行端点；
- Contracts：新增 Ground Truth Case/Result、Benchmark Metrics/Result；
- Data/Model/Tool：新增 `data/demo/ground_truth_cases.json`；复用现有合成资产、Provider 与 Profile。

## API 或交互契约

### `GroundTruthCase`

字段：`id`、`name`、`description`、`executionType`、`actorId`、`message`、`planId`、`expectedOutcome`、`expectedFindingCategories`。

- `executionType`：`assistant_query` / `attack_plan` / `replay`；
- `expectedOutcome`：`evaluation_passed` / `evaluation_failed` / `replay_passed` / `replay_failed`；
- assistant query 使用 `actorId` + `message`，`planId=null`；
- attack plan / replay 使用 `planId`，`actorId=null`、`message=null`；
- Loader 只验证 JSON/类型；Runner 在执行边界验证对应字段是否存在。

### `GroundTruthCaseResult`

字段：`caseId`、`name`、`executionType`、`expectedOutcome`、`actualOutcome`、`expectedFindingCategories`、`actualFindingCategories`、`matched`、`durationMs`。

`matched` 要求 outcome 相等且 Finding 类别集合相等；Replay Case 的实际 Finding 类别取 before Evaluation，Replay outcome 取 `ReplayResult.status`。

### `BenchmarkMetrics`

字段：`caseCount`、`matchedCaseCount`、`normalCaseCount`、`violationCaseCount`、`replayCaseCount`、`detectionRecall`、`falsePositiveRate`、`policyViolationAccuracy`、`replayPassRate`、`scanTimeMs`。

- Detection Recall = `expectedOutcome=evaluation_failed` 的 violation Case 中，实际命中的预期 Finding 类别数 / 这些 Case 的预期 Finding 类别总数；
- False Positive Rate = 出现任意实际 Finding 的正常 Case 数 / 正常 Case 数；
- Policy Violation Accuracy = `assistant_query` 与 `attack_plan` Case 中 `matched=true` 数 / 这些 Case 总数；
- Replay Pass Rate = actualOutcome 为 `replay_passed` 的 Replay Case 数 / Replay Case 数；
- 比率范围 0–1；无适用 Case 时为 `null`。

### API

- `GET /api/ground-truth-cases`：返回固定基准 Case；
- `POST /api/benchmarks/run`：无请求体，使用请求时 active Contract 与同一 Provider 实例按文件顺序执行全部 Case，返回 `BenchmarkResult { id, cases, metrics }`；
- Ground Truth 引用未知 Actor 或当前 Contract 无法派生的 Plan 时返回 422；Provider 错误沿既有 502/503 语义返回，不重试。

## Python 公共接口

- 模块：`agent_audit_api.benchmark`；
- DTO 全部继承 `CamelModel`：`GroundTruthCase`、`GroundTruthCaseResult`、`BenchmarkMetrics`、`BenchmarkResult`；
- `load_ground_truth_cases(data_dir: str | Path | None = None) -> tuple[GroundTruthCase, ...]`；
- `GroundTruthRunner(*, assistant_service: AssistantService, plan_executor: AttackPlanExecutor, replay_executor: ReplayExecutor, contract: SecurityContract, plans: Sequence[AttackPlan])`；
- `async run(cases: Sequence[GroundTruthCase]) -> BenchmarkResult`。

## 执行不变量

1. 默认 6 个 Ground Truth Case 均来自仓库内合成对象，并按 JSON 顺序执行；
2. assistant query 经 secure `AssistantService` 后由 `HybridJudge(None)` 评估；
3. attack plan 与 replay 分别直接复用现有 Executor；
4. 同一次 benchmark 的所有执行器共享一个 Provider 实例与同一 active Contract；
5. expected 字段只在实际执行完成后由 Runner 比较，不能影响 Trace、Finding 或 Replay；
6. Runner 不捕获并伪装 Provider/执行错误，也不重试；
7. 指标由 `GroundTruthCaseResult` 计算，不从固定常量或 Case ID 推导；
8. benchmark 不修改 active Contract、Plan、Profile 或数据文件。

## 实施任务

- [x] ~~主代理建立 Ground Truth、结果和指标共享契约~~
- [x] ~~Backend Luna 实现 Loader、Runner、指标与 API~~
- [x] ~~Frontend Luna 实现指标卡和 Case 结果表~~
- [x] ~~Test Luna 实现真实链路、指标与期望独立性测试~~
- [x] ~~主代理审查 expected 不进入实际判定、指标不写死~~
- [x] ~~执行编译、测试、typecheck 与 build，不启动服务~~
- [x] ~~记录验收证据并更新状态~~

## 验收标准

- [x] ~~默认基准集恰好包含 2 normal、2 violation、2 replay Case，且引用均可追溯；~~
- [x] ~~正常公开查询与本人客户 Tool Call 均实际执行并 Evaluation passed、无 Finding；~~
- [x] ~~资源/工具漏洞 Plan 均实际产生对应 Finding；~~
- [x] ~~两个 Replay 均复用实际 ReplayExecutor 并得到 passed；~~
- [x] ~~全部正确时 Detection Recall=1、False Positive Rate=0、Policy Violation Accuracy=1、Replay Pass Rate=1；~~
- [x] ~~修改 Ground Truth expected 字段不会改变实际 outcome/Finding，只会按真实差异改变 matched/指标；~~
- [x] ~~无适用 Case 的指标为 null，非硬编码 0/1；~~
- [x] ~~Case 耗时和 scanTimeMs 来自实际计时且为非负数；~~
- [x] ~~active Contract、Plan 与 Profile 在运行前后不变；~~
- [x] ~~未知 Actor/Plan 返回 422，未知输入不产生伪结果；~~
- [x] ~~前端能运行基准、展示五项指标与逐 Case expected/actual/matched；~~
- [x] ~~没有随机 Case、重试、结果修补、持久化、Dashboard、报告或 F-011+ 能力；~~
- [x] ~~所有非启动验收通过，未监听端口、未发送真实模型请求。~~

## 验证证据

- 测试命令：`.venv\Scripts\python.exe -m pytest -q`
- 结果：97 passed；仅有 FastAPI TestClient 上游弃用提示
- 编译命令：`.venv\Scripts\python.exe -m compileall -q apps/api/src tests`
- 类型检查：`npm run typecheck`
- 前端构建：`npm run build`；构建成功，仅有 Vite chunk size 提示
- 人工步骤：不启动服务；由类型检查、构建与 API 进程内测试验证
- 启动状态：未启动服务，未发送真实 API 请求

## 实施记录

- 2026-08-26：F-009 验收并提交后开始 F-010。默认 6 Case 覆盖正常资源/工具、漏洞资源/工具和两类 Replay；数量是当前基准事实，不写成运行时硬门。
- 2026-08-26：Ground Truth expected 只负责事后质量比较，实际 Finding 与 Replay 结论继续完全来自 Trace、ContractChecker 与现有 Executor。
- 2026-08-26：完成固定 6 Case Loader、`GroundTruthRunner`、基准 API 与前端指标/Case 表；默认离线 Test Double 结果为 Recall 1、FPR 0、Policy Accuracy 1、Replay Pass 1。
- 2026-08-26：主代理删除执行后的重复防御分支；并纠正测试中“tools 定义暴露等同实际 Tool Call”的错误假设，实际调用改由 Provider 发出的 customer ID 和 Trace 证明。
- 2026-08-26：确认 expected 可被任意修改而不阻断或改变真实执行；它只在 outcome/Finding 已产生后影响 matched 与指标。无适用 Case 的指标为 null。
