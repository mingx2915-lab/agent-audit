# F-005 Trace Collector 与 Source→Sink 运行详情

- 状态：Done
- 所属里程碑：M1
- 负责人：主代理监督；Backend/Frontend/Test Luna 分工实现
- 相关决定：D-002、D-003、D-004、D-007、D-009

## 用户价值

让开发与安全人员不只看到一串日志，而能沿一次真实助手查询识别输入和检索内容来自哪里、哪些数据进入了模型或工具、最终输出流向哪里，为后续 Contract Checker 判断“Trace 已越界但回答可能拒绝”等问题提供结构化证据。

## 范围

- 建立独立、请求级 `TraceCollector`，统一分配 sequence 和时间并返回不可变顺序快照；
- 扩展 Trace 类型为 `source` 与 `sink`，保留 F-003/F-004 现有事件；
- 知识文档增加 `sourceId`、`sourceType`、`trustLevel` 资源来源属性；
- 输入 Source 记录 Actor，检索 Source 记录文档来源与 trust level；
- 模型调用前记录 `model_context` Sink，只列真正通过授权进入上下文的文档；
- 工具结果再次进入模型时记录对应 `model_context` Sink；
- 最终回答记录 `actor_response` Sink；
- 页面用明确中文标签和简短流向摘要展示 Source/Sink 事件，完整 details 仍可查看；
- 单元测试、API 进程内集成测试和前端 typecheck/build。

## 非目标

- 判断 Source→Sink 是否违规、生成 Finding 或风险分数；
- Outside-in/Inside-out 攻击生成与执行；
- 真实或 Mock Mail 发送、任意外部 Sink；
- Scan/Trace 数据库持久化、查询历史列表或分布式采集；
- OpenTelemetry、消息队列、事件总线、哈希证明链；
- 修复建议、Replay、Dashboard 大屏；
- 启动服务或发送真实 DeepSeek 请求。

## 前后端与数据影响

- Web：扩展 Trace 标签与 Source→Sink 可读摘要，不新增独立 Dashboard 或路由；
- API：助手查询响应结构不变，只扩展 `TraceEvent.type/details`；
- Contracts：`TraceEventType` 新增 `source`、`sink`；details 继续使用开放对象，由本功能固定公共键；
- Data：每个知识文档新增稳定来源属性；
- Model/Tool：Provider 与工具能力不变，只记录数据进入模型上下文和 Actor 响应的 Sink 事实。

## Trace 公共语义

- 输入 `source` details：`sourceId`、`sourceType=user_input`、`actorId`、`trustLevel=trusted`；
- 检索文档 `source` details：`sourceId`、`sourceType`、`trustLevel`、`documentId`；每个检索结果一条；
- 模型上下文 `sink` details：`sinkId=model_context`、`sinkType=model_context`、`documentIds`、`includesToolResult`；
- Actor 响应 `sink` details：`sinkId=actor_response`、`sinkType=actor_response`、`actorId`；
- Source/Sink 只陈述实际数据流，不在本功能写 `violation`、`risk` 或 Finding；
- `TraceCollector` 只负责顺序、时间和事件集合，不负责授权或规则判断。

## 实施任务

- [x] 主代理更新共享 Trace 类型并锁定 Source/Sink details
- [x] Backend Luna 实现 TraceCollector、文档来源属性和真实 Source/Sink 记录
- [x] Frontend Luna 增加 Source/Sink 标签与流向摘要
- [x] Test Luna 实现 Collector 单元测试与 API Trace 数据流集成测试
- [x] 主代理审查事实记录与安全判断职责分离
- [x] 执行编译、测试、typecheck 与 build，不启动服务
- [x] 记录验收证据并更新状态

## 验收标准

- [x] TraceCollector 自动生成连续 sequence，并按记录顺序返回事件；
- [x] 用户输入和每个实际检索结果都有 Source Event；
- [x] 只有授权通过的文档 ID 进入首个 `model_context` Sink；
- [x] 工具执行路径能区分包含工具结果的第二次 `model_context` Sink；
- [x] 最终回答有明确 `actor_response` Sink；
- [x] 前端能区分 Source、Authorization、Tool、Sink 和 Model Response；
- [x] Source/Sink details 字段与功能文档一致，原有 Trace sequence 仍连续；
- [x] TraceCollector 不执行 Security Contract 判定，F-005 不生成 Finding；
- [x] 没有真实邮件、任意外部 Sink、数据库或后续功能；
- [x] 所有非启动验收通过，未监听端口、未发送真实模型请求。

## 验证证据

- 后端测试：`.venv\\Scripts\\python.exe -m pytest -q`，结果 `33 passed`；存在一条上游 `fastapi.testclient` deprecation warning，不影响本功能行为
- Python 编译：`.venv\\Scripts\\python.exe -m compileall -q apps/api/src tests`，通过
- 前端检查：`npm run typecheck`，通过；`npm run build`，通过；Vite 仅有既存 chunk size 提示
- Trace 检查：单元测试覆盖连续 sequence、独立 Collector、快照和 UTC；API 进程内测试覆盖输入/文档 Source、授权文档 context Sink、工具结果二次 context Sink 与最终 Actor Sink
- 职责检查：代码审查确认 TraceCollector 不导入或调用 Security Contract；Source/Sink details 不包含 violation、risk 或 Finding
- 人工步骤：按启动限制未运行浏览器页面；前端展示由共享 Type、代码审查、typecheck 和 production build 验证
- 启动状态：未启动服务，未发送真实 API 请求

## 实施记录

- 2026-08-26：F-004 验收并提交后开始 F-005。Source/Sink 仅记录事实，违规判断留给 F-006。
- 2026-08-26：三个 Luna 分别完成 Backend、Frontend 与 Test 范围；主代理移除来源字段的 `unknown_*` 默认与前端 unknown 展示兜底后统一验收，确保缺失来源不会被伪装成事实。
