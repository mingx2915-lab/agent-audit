# F-009 修复建议与同攻击 Replay 回归

- 状态：Done
- 所属里程碑：M2
- 负责人：主代理监督；Backend/Frontend/Test Luna 分工实现
- 相关决定：D-002、D-003、D-004、D-007、D-009、D-014

## 用户价值

让用户在同一页面看到一次真实失败如何通过明确的 Target Profile 配置修复，并用完全相同的攻击计划重新执行后证明违规链消失，形成“发现 → 定位 → 修复配置 → Replay”的比赛核心闭环。

## 范围

- 定义 `RemediationRecommendation`、`ReplayAttempt` 与 `ReplayResult` 共享契约；
- 根据 `AttackPlan.basisType` 生成确定性、可执行的最小修复建议：
  - Resource owner-scope：`targetProfile.enforceResourceAuthorization: false → true`；
  - Tool owner-scope：`targetProfile.enforceToolAuthorization: false → true`；
- 实现 `ReplayExecutor`，先按计划原有漏洞 Profile 执行，再只把同一计划的 `targetProfileId` 改为 `secure` 执行；
- before/after 必须保持 plan ID、Actor、message、target 与 active Security Contract 一致；
- 两次执行都复用 F-008 `AttackPlanExecutor`、F-007 `AttackCaseExecutor`、Target Agent、Provider、TraceCollector 与 HybridJudge；
- secure 工具执行若在 denied Authorization 后、实际 Tool Call 前被阻断，保留该真实 Trace，并由 ContractChecker 得出无绕过 Finding；不伪造 QueryResult 或模型回答；
- Replay 通过条件固定为：before Evaluation 为 `failed` 且 after Evaluation 为 `passed`；
- 新增 `POST /api/attack-plans/{planId}/replay`，Plan 必须从请求时 active Contract 重新派生；未知或已失效 Plan 返回 404；
- 前端为 Contract-driven Plan 提供单 Plan Replay 操作，展示修复字段、before/after Profile、执行状态、Finding 数和通过结论；保留两侧 Trace 的可读事件摘要；
- 单元测试、API 进程内集成测试和前端 typecheck/build。

## 非目标

- 自动修改 active Security Contract、写回 JSON 文件、任意代码修复或 LLM 生成补丁；
- 通过改攻击 message、Actor、target、Contract 或删除计划让 Replay 通过；
- Replay 重试、缓存 Provider 响应、强制复用模型输出或为模型差异做结果修补；
- 批量 Replay、持久化历史、数据库、Scan、队列、Dashboard 或报告导出；
- 真实邮件、外部 Endpoint 或真实企业系统；
- 自动 Semantic Review；
- 启动服务或发送真实 DeepSeek 请求。

## 前后端与数据影响

- Web：Plan 区新增“修复并 Replay”；新增 before/after 对比区和两侧 Trace 摘要；
- API：新增单计划 Replay 端点；现有查询、固定 Case、Plan Execute 和 Contract API 不变；
- Contracts：新增修复建议、单次 Replay Attempt 和 Replay Result 类型；
- Data/Model/Tool：复用已有漏洞/secure Profile 与 Mock 数据，不新增外部资源。

## API 或交互契约

### `RemediationRecommendation`

字段：`id`、`title`、`summary`、`configurationPath`、`beforeValue`、`afterValue`。本功能中值均为 boolean，且只允许上述两个 `targetProfile.enforce*Authorization` 路径。

### `ReplayAttempt`

```json
{
  "profileId": "secure",
  "executionStatus": "blocked",
  "queryResult": null,
  "traceEvents": [],
  "evaluation": {},
  "blockedReason": "actor is not authorized to use Mock Customer Tool"
}
```

`executionStatus` 只允许 `completed` / `blocked`。完成执行时 `queryResult` 非空、`blockedReason=null`；授权阻断时 `queryResult=null`、`blockedReason` 非空，但 `traceEvents` 必须含真实 denied Authorization。

### `ReplayResult`

```json
{
  "id": "replay_plan_tool_customer_owner_read",
  "plan": {},
  "remediation": {},
  "before": {},
  "after": {},
  "status": "passed"
}
```

### `POST /api/attack-plans/{planId}/replay`

无请求体。返回上述 `ReplayResult`。请求时从 active Contract 重新派生 Plan；未知或已失效 Plan 返回 404。

执行不变量：

1. before 使用原 `targetProfileId`，after 只替换为 `secure`；其他 Plan 字段逐项一致；
2. before/after 使用同一个 Provider 实例，但各自执行真实请求，不缓存或回放模型响应；
3. Resource Replay 的 after Trace 中 denied 目标不得进入 `model_context`；
4. Tool Replay 的 after Trace 中必须有 denied Authorization，且不得出现对应 `tool_call` / `tool_result`；
5. blocked Attempt 的 Evaluation 根据捕获 Trace 真实计算，不靠阻断异常直接写 `passed`；
6. `status=passed` 只由 before failed + after passed 得出；修复建议、期望类别不能覆盖结论；
7. Replay 不修改 active Contract、固定 Case、Attack Plan 数据或 Target Profile 文件。

### Python 公共接口

- 模块：`agent_audit_api.replay`；
- `build_remediation(plan: AttackPlan) -> RemediationRecommendation`；
- `ReplayExecutor(*, plan_executor: AttackPlanExecutor, contract: SecurityContract)`；
- `async replay(plan: AttackPlan) -> ReplayResult`；
- `ToolAuthorizationError.trace_events: tuple[TraceEvent, ...]`：只承载抛出前已记录的事实，原错误文本与现有 API 403 行为不变。

## 实施任务

- [x] ~~主代理建立 Replay 共享契约与阻断 Trace 边界~~
- [x] ~~Backend Luna 实现修复建议、ReplayExecutor、阻断 Trace 与 API~~
- [x] ~~Frontend Luna 实现单计划 Replay 操作和 before/after 对比~~
- [x] ~~Test Luna 实现资源/工具 Replay、不变量与 API 测试~~
- [x] ~~主代理审查同一攻击字段、真实阻断 Trace 和判定来源~~
- [x] ~~执行编译、测试、typecheck 与 build，不启动服务~~
- [x] ~~记录验收证据并更新状态~~

## 验收标准

- [x] ~~Resource Plan Replay 的 before 产生资源 Finding，after denied 文档不进 context 且 Evaluation passed；~~
- [x] ~~Tool Plan Replay 的 before 产生工具 Finding，after 在 denied 后阻断且无 tool_call/tool_result，Evaluation passed；~~
- [x] ~~before/after 除 `targetProfileId` 外的 Plan 字段完全一致；~~
- [x] ~~blocked Attempt 保留真实 Trace、无伪造 QueryResult，Evaluation 由 ContractChecker 计算；~~
- [x] ~~修复建议准确对应资源或工具 enforcement 配置 false→true；~~
- [x] ~~修改修复建议、期望类别或显示字段不能改变 Replay 结论；~~
- [x] ~~Replay 不修改 active Contract，执行后计划预览保持一致；~~
- [x] ~~未知或已失效 Plan 返回 404；~~
- [x] ~~前端能执行单计划 Replay 并清楚展示 before/after 状态、Finding 与 Trace 摘要；~~
- [x] ~~没有自动写配置、LLM 补丁、重试/缓存、批量 Scan、持久化、Dashboard 或 F-010+ 能力；~~
- [x] ~~所有非启动验收通过，未监听端口、未发送真实模型请求。~~

## 验证证据

- 测试命令：`.venv\Scripts\python.exe -m pytest -q`
- 结果：84 passed；仅有 FastAPI TestClient 上游弃用提示
- 编译命令：`.venv\Scripts\python.exe -m compileall -q apps/api/src tests`
- 类型检查：`npm run typecheck`
- 前端构建：`npm run build`；构建成功，仅有 Vite chunk size 提示
- 人工步骤：不启动服务；由类型检查、构建与 API 进程内测试验证
- 启动状态：未启动服务，未发送真实 API 请求

## 实施记录

- 2026-08-26：F-008 验收并提交后开始 F-009。修复限定为 Target Profile enforcement 开关；不改 Security Contract，因为 Contract 表达的是正确业务规则，漏洞位于 Target Agent 未执行 denied 结果。
- 2026-08-26：工具 secure Replay 的正常结果是授权层在 Tool Call 前阻断；Replay 层记录真实 denied Trace 并评估，而不是伪造一个模型拒绝回答。
- 2026-08-26：完成确定性修复建议、`ReplayExecutor`、单计划 Replay API 与前端 before/after 对比；普通 secure Assistant API 仍保持原 403 行为。
- 2026-08-26：资源 Replay 的 after 仍记录 denied，但目标文档不进入 context；工具 Replay 的 after 在 denied 后 blocked，`queryResult=null` 且无 tool_call/tool_result。
- 2026-08-26：确认 Replay status 只由两次实际 Evaluation 的 failed→passed 决定；篡改修复建议、期望类别和显示字段不能改变结论，active Contract 与 Plan 列表不变。
