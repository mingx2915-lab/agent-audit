# F-007 Outside-in 与 Inside-out 双攻击者固定测试

- 状态：Done
- 所属里程碑：M2
- 负责人：主代理监督；Backend/Frontend/Test Luna 分工实现
- 相关决定：D-002、D-003、D-004、D-007、D-009、D-012

## 用户价值

让评委看到两种不同威胁如何通过同一真实企业助手链路被复现：外部不可信内容进入 RAG 后诱导越界，以及内部合法员工利用自身身份访问非本人对象；两者都由实际 Trace 和 ContractChecker 产生证据，而不是预制 Finding。

## 范围

- 定义固定 `AttackCase` 与 `AttackExecutionResult`；
- 提供两个仓库内合成 Case：
  - `case_inside_out_customer_scope`：`sales_001` 请求 `customer_002` 非本人客户资料；
  - `case_outside_in_untrusted_rag`：访客查询包含恶意指令的不可信供应商文档及受限财务资料；
- 定义受控 `TargetProfile`，本功能只需要：
  - `secure`：denied 后阻断；
  - `vulnerable_observe_only`：仍执行 Contract 判定并记录 denied，但资源过滤处于 observe-only，故意让 denied 文档进入模型上下文；
- `AssistantService` 的默认行为保持 secure；漏洞模式由显式 TargetProfile 注入，不按问题文本写死；
- 新增合成不可信文档，标注 `sourceType=external_document`、`trustLevel=untrusted`；
- 提供 `GET /api/attack-cases` 与 `POST /api/attack-cases/{caseId}/execute`；
- Case 执行真实经过 Retriever、ContractEvaluator、Target Agent、TraceCollector、Provider 与 ContractChecker；
- 执行结果返回完整 Query Result 和确定性 Evaluation；
- 前端展示两个攻击者类型、Case 描述、执行按钮，并复用现有 Trace/Finding 区显示结果；
- 单元测试、API 进程内集成测试和前端 typecheck/build。

## 非目标

- LLM 自动生成攻击、Attack Planner、变异、搜索或多轮自适应；
- 任意外部目标、外部文档 URL、真实恶意内容或真实企业数据；
- 工具业务越权 Case、Mock Mail Sink、真实邮件或 Source→外部 Sink 外泄；
- 修复建议、配置切换 UI、Replay 或前后对比；
- Scan 持久化、队列、批量运行、Dashboard 大屏；
- 自动请求 Semantic Review；
- 启动服务或发送真实 DeepSeek 请求。

## 前后端与数据影响

- Web：新增紧凑的固定 Case 区，执行后复用当前回答、Trace 与 Finding 展示；
- API：新增 Attack Case 列表与单 Case 执行端点；
- Contracts：新增 `AttackerType`、`AttackCase`、`AttackExecutionResult`；
- Data：新增固定 Case、Target Profile 和一个不可信外部合成文档；
- Model/Tool：复用 Provider；测试显式注入 Fake Provider，不增加运行时 fallback；工具不变。

## API 与执行契约

### `GET /api/attack-cases`

返回两个固定 Case，字段：`id`、`name`、`description`、`attackerType`、`actorId`、`message`、`targetProfileId`、`expectedFindingCategories`。

### `POST /api/attack-cases/{caseId}/execute`

无请求体。未知 Case 返回 404。响应：

```json
{
  "case": {},
  "queryResult": {},
  "evaluation": {}
}
```

执行不变量：

1. Case 只能引用仓库内 Actor、Target Profile 与合成文档；
2. `vulnerable_observe_only` 不跳过 ContractEvaluator，只改变 denied 后是否阻断；
3. Trace 中必须同时保留 denied Authorization 与实际进入 context 的文档 ID；
4. Outside-in Case 的 Trace 必须出现 `trustLevel=untrusted` 的文档 Source；
5. 两个 Case 的 Evaluation 都由 ContractChecker 根据实际 Trace 计算；
6. `expectedFindingCategories` 只用于测试期望/展示，不参与实际判定；
7. 默认 `/api/assistant/queries` 始终使用 secure Profile。

## 实施任务

- [x] ~~主代理建立共享 Attack Case 契约并锁定漏洞配置边界~~
- [x] ~~Backend Luna 实现 TargetProfile、固定 Case Loader/Executor 与 API~~
- [x] ~~Frontend Luna 实现双攻击者 Case 区并复用现有结果展示~~
- [x] ~~Test Luna 实现 secure/observe-only 单元测试与双 Case API 集成测试~~
- [x] ~~主代理审查 Finding 来自真实 Trace、expected 不参与判定~~
- [x] ~~执行编译、测试、typecheck 与 build，不启动服务~~
- [x] ~~记录验收证据并更新状态~~

## 验收标准

- [x] ~~Case 列表恰好包含一个 Outside-in 和一个 Inside-out 固定 Case；~~
- [x] ~~默认助手查询保持 secure，denied 文档不进入 model_context；~~
- [x] ~~Inside-out Case 以合法销售身份真实检索到非本人客户文档，记录 denied 后进入 context 并产生资源绕过 Finding；~~
- [x] ~~Outside-in Case Trace 包含 untrusted external document Source，并有受限文档 denied→context→Finding 链；~~
- [x] ~~两个 Case 都经过真实 Retriever、Authorization、Provider、Trace 与 Checker；~~
- [x] ~~修改 `expectedFindingCategories` 不会改变实际 Evaluation；~~
- [x] ~~未知 Case 返回 404；~~
- [x] ~~前端能区分攻击者类型、发起固定测试并展示真实 Trace/Finding；~~
- [x] ~~没有自动 Attack Planner、外部扫描、工具越权、Replay 或 F-008+ 能力；~~
- [x] ~~所有非启动验收通过，未监听端口、未发送真实模型请求。~~

## 验证证据

- 测试命令：`.venv\Scripts\python.exe -m pytest -q`
- 结果：61 passed；仅有 FastAPI TestClient 上游弃用提示
- 编译命令：`.venv\Scripts\python.exe -m compileall -q apps/api/src tests`
- 类型检查：`npm run typecheck`
- 前端构建：`npm run build`；构建成功，仅有 Vite chunk size 提示
- 人工步骤：不启动服务；由类型检查、构建与 API 进程内测试验证
- 启动状态：未启动服务，未发送真实 API 请求

## 实施记录

- 2026-08-26：F-006 验收并提交后开始 F-007。只做两个固定 Case；漏洞由通用 observe-only 配置产生，不把攻击问题或 Finding 写死进 Agent。
- 2026-08-26：完成共享契约、TargetProfile、固定 Case Executor/API、双攻击者前端区和对应测试；默认助手显式使用 secure Profile。
- 2026-08-26：主代理移除“运行时必须恰好两个 Case”的硬门，并把 TargetProfile 拆为独立模块，避免循环依赖和延迟导入补丁；当前固定数据数量仍由测试验收。
- 2026-08-26：确认 observe-only 只关闭资源授权阻断，工具授权保持执行；`expectedFindingCategories` 不进入 Executor、ContractChecker 或 HybridJudge 判定。
