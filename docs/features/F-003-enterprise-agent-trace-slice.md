# F-003 企业知识助手靶场与最小全栈 Trace 闭环

- 状态：Done
- 所属里程碑：M1
- 负责人：主代理监督；Backend/Frontend/Test Luna 分工实现
- 相关决定：D-002、D-003、D-008、D-009、D-010、D-011、D-012

## 用户价值

让评委和开发者能够以一个明确员工身份向企业知识助手提问，并看到后端真实执行的 Retrieval、Authorization、Tool Call 和 Final Response Trace，为后续 Security Contract 判定建立可信底座。

## 范围

- Vue 3 + TypeScript 的最小真实页面；
- FastAPI 模块化单体；
- 受控的“星云科技”合成角色、知识文档和一个 Mock Customer Tool；
- 基于文档内容的通用检索算法，不按固定问题写死答案；
- DeepSeek `deepseek-v4-flash` Provider Adapter，thinking disabled；
- Target Agent 能执行一次检索或一次 Mock Tool 调用，并记录结构化 Trace；
- 页面展示 Actor、问题、回答以及按时间排序的 Trace Event；
- 单元测试、API 进程内集成测试和前端静态构建。

## 非目标

- Security Contract 规则编辑和违规判定；
- Outside-in/Inside-out 攻击生成；
- Finding、风险评分、修复建议和 Replay；
- PostgreSQL、pgvector、Docker 或部署；
- 任意外部目标；
- 启动前后端服务或发送真实 DeepSeek 请求；
- 漂亮大屏、复杂图表、登录和完整 IAM。

## 前后端与数据影响

- Web：身份选择、问题输入、提交状态、回答和 Trace 时间线；
- API：健康信息（纯函数/路由定义）、角色列表、一次助手查询；
- Contracts：Actor、AssistantQueryRequest、AssistantQueryResult、TraceEvent；
- Data：合成角色、知识文档、客户记录；
- Model/Tool：DeepSeek Provider Adapter、Test Double、Mock Customer Tool。

## API 与交互契约

### `GET /api/demo/actors`

返回可选 Demo Actor：

```json
[
  {
    "id": "sales_001",
    "displayName": "张三",
    "role": "sales"
  }
]
```

### `POST /api/assistant/queries`

请求：

```json
{
  "actorId": "sales_001",
  "message": "总结我的客户合同"
}
```

响应：

```json
{
  "queryId": "query_...",
  "actor": {
    "id": "sales_001",
    "displayName": "张三",
    "role": "sales"
  },
  "answer": "...",
  "traceEvents": [
    {
      "sequence": 1,
      "type": "retrieval",
      "summary": "Retrieved customer contract",
      "details": {},
      "occurredAt": "2026-08-26T00:00:00Z"
    }
  ]
}
```

错误只处理真实边界：未知 Actor、空消息、Provider 响应无效和 Mock Tool 参数无效。

## 实施任务

- [x] 主代理建立共享契约和根级工作区配置
- [x] Backend Luna 实现 FastAPI、合成数据、Retriever、Mock Tool、Provider Adapter 与 Trace
- [x] Frontend Luna 实现身份选择、提问和 Trace 时间线
- [x] Test Luna 实现后端规则/API测试与前端关键测试建议
- [x] 主代理整合前后端契约并审查范围
- [x] 执行静态检查、编译和不启动服务的测试
- [x] 记录验收证据并更新状态

## 验收标准

- [x] 后端能从合成数据返回 Demo Actor；
- [x] 查询链路由真实模块执行，不从静态响应文件读取最终结果；
- [x] Retriever 对文档集合执行通用排序并记录检索文档；
- [x] Mock Customer Tool 可通过 Target Agent 编排执行并记录工具名、参数和结果摘要；
- [x] DeepSeek Provider 只读取 `DEEPSEEK_API_KEY`，模型为 `deepseek-v4-flash`，thinking 显式关闭；
- [x] 前端通过 API 契约展示 Actor、回答和 Trace 时间线；
- [x] Test Double 只存在于测试注入，不成为运行时自动降级路径；
- [x] 没有启动服务、监听端口或发送真实模型请求；
- [x] 相关静态检查、编译和测试通过；
- [x] 未提前实现 F-004 及以后功能。

## 验证证据

- 环境：Node 18.20.8、npm 10.8.2、Python 3.11.9；Docker/uv 当前未安装
- 依赖准备：根目录 `npm install`；本地 `.venv` 中安装 `-e apps/api`、`pytest` 与 `httpx`
- 后端命令：`.venv\\Scripts\\python.exe -m pytest -q`，结果 `16 passed`；存在一条上游 `fastapi.testclient` deprecation warning，不影响本功能行为
- Python 编译：`.venv\\Scripts\\python.exe -m compileall -q apps/api/src tests`，通过
- 前端命令：`npm run typecheck`，通过；`npm run build`，通过
- 集成检查：FastAPI `TestClient` 进程内覆盖 Actor、检索、授权、工具调用、Trace、错误响应和显式 Test Provider 注入；未监听端口
- Provider 检查：注入 Recording Client，确认请求使用 `deepseek-v4-flash` 与 `thinking.type=disabled`，未访问网络
- 启动状态：未启动服务，未发送真实 API 请求

## 实施记录

- 2026-08-26：F-003 开始。用户要求使用 DeepSeek Flash、关闭 thinking，并在软件接近完成前禁止启动；启动前必须再次告知。
- 2026-08-26：三个 Luna 分别完成 Backend、Frontend 与 Test 范围；主代理修正展示名测试契约、补充 Provider 配置测试并完成统一验收。F-003 未引入 Security Contract、Finding、Replay 或任意外部目标能力。
