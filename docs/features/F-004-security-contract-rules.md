# F-004 Security Contract 与角色/资源/工具规则

- 状态：Done
- 所属里程碑：M1
- 负责人：主代理监督；Backend/Frontend/Test Luna 分工实现
- 相关决定：D-002、D-003、D-004、D-005、D-007、D-009

## 用户价值

让开发与安全人员用一份可读、可编辑、可执行的 Security Contract 明确“哪些角色可以访问哪些标签资源、执行哪些工具动作，以及是否必须满足对象归属”，并让企业知识助手的现有 Authorization Trace 真正由该契约驱动。

## 范围

- 定义最小 `SecurityContract`：基础信息、角色、资源规则和工具动作规则；
- 资源规则按 `matchLabels` 匹配，声明 `allowedRoles` 与 `requireOwnerMatch`；
- 工具规则按 `toolName + action` 匹配，声明 `allowedRoles` 与 `requireOwnerMatch`；
- 多条匹配规则采用“任一完整满足则允许”，无匹配规则默认拒绝；
- 将 F-003 文档和 Mock Customer Tool 的授权从嵌入数据/硬编码角色改为 Contract Evaluator；
- 提供 `GET`/`PUT` API，在当前进程内读取和更新 Demo Contract；
- Vue 页面能够读取、编辑并保存完整 Contract JSON，并清楚标注 Demo 进程内状态；
- 使用固定合成 Contract 作为每次应用创建时的初始配置；
- 单元测试、API 进程内集成测试和前端 typecheck/build。

## 非目标

- Finding、风险评分、Contract violation 报告或 Hybrid Judge；
- Attack Planner、Outside-in/Inside-out 攻击执行；
- Contract 版本比较、审批流、多人冲突处理、RBAC 管理后台；
- 数据库持久化、文件回写、文档哈希、ETag 或复杂状态门；
- 自动修复、Replay、Dashboard 大屏；
- 启动服务或发送真实 DeepSeek 请求。

## 前后端与数据影响

- Web：增加一个紧凑的 Security Contract 查看/JSON 编辑区，支持加载、编辑、保存和显示边界错误；
- API：新增 `GET /api/security-contract` 与 `PUT /api/security-contract`；现有查询链路注入当前 Contract；
- Contracts：新增 `SecurityContract`、`ContractRole`、`ResourceRule`、`ToolRule`；
- Data：新增 `data/demo/security_contract.json`；知识文档只保留资源属性，不再自行携带授权角色；
- Model/Tool：Provider 不变；工具是否暴露及能否执行由 Contract Evaluator 判定。

## API 与确定性语义

### Contract Schema

```json
{
  "id": "contract_nebula_default",
  "name": "星云科技默认 Security Contract",
  "version": 1,
  "roles": [
    {"id": "sales", "displayName": "销售"}
  ],
  "resourceRules": [
    {
      "id": "resource_customer_owner",
      "description": "销售只能读取本人客户资料",
      "matchLabels": ["customer", "confidential"],
      "allowedRoles": ["sales"],
      "requireOwnerMatch": true
    }
  ],
  "toolRules": [
    {
      "id": "tool_customer_owner_read",
      "description": "销售只能读取本人客户记录",
      "toolName": "mock_customer_lookup",
      "action": "read",
      "allowedRoles": ["sales"],
      "requireOwnerMatch": true
    }
  ]
}
```

规则语义固定为：

1. `matchLabels` 必须全部存在于资源标签才算匹配；
2. 匹配规则中，Actor role 必须属于 `allowedRoles`；
3. `requireOwnerMatch=true` 时，Actor ID 必须等于资源/工具目标的 owner ID；
4. 多条规则中任一条完整满足即 `allowed`；没有规则完整满足即 `denied`；
5. 管理员豁免不写死在代码里，而由独立的 admin 规则表达。

### `GET /api/security-contract`

返回当前进程使用的完整 Security Contract。

### `PUT /api/security-contract`

请求和响应均为完整 Security Contract。API 在边界验证字段、唯一 rule ID 和 role 引用；成功后，后续助手查询立即使用新 Contract。应用重建后恢复固定 Demo Contract，不承诺跨进程持久化。

## 实施任务

- [x] 主代理建立共享 TypeScript 契约并锁定确定性规则语义
- [x] Backend Luna 实现 Contract Schema、Loader、Evaluator、GET/PUT API 与查询链路注入
- [x] Frontend Luna 实现 Contract 加载、JSON 编辑、保存和状态反馈
- [x] Test Luna 实现 Contract 规则单元测试与 API 更新后行为集成测试
- [x] 主代理整合契约、审查单一授权来源和范围
- [x] 执行编译、测试、typecheck 与 build，不启动服务
- [x] 记录验收证据并更新状态

## 验收标准

- [x] 默认合成 Contract 能通过 GET API 和前端读取；
- [x] 合法完整 Contract 能通过 PUT 更新，未知 role 引用或重复 rule ID 被边界校验拒绝；
- [x] Resource Rule 的标签、角色和 owner 条件按上述算法确定性判定；
- [x] Tool Rule 的工具名、动作、角色和 owner 条件按上述算法确定性判定；
- [x] 后续助手查询立即使用更新后的 Contract，并在 Authorization Trace 中体现 decision 与 rule ID；
- [x] 文档数据不再通过 `allowedRoles` 自行携带第二套授权真相；
- [x] 工具暴露与工具执行不再硬编码 `sales/admin`，管理员能力来自 Contract；
- [x] 前端能够展示、编辑、保存 Contract，并明确这是 Demo 进程内状态；
- [x] 没有实现 Finding、攻击生成、Replay 或其他 F-005+ 能力；
- [x] 所有非启动验收通过，未监听端口、未发送真实模型请求。

## 验证证据

- 后端测试：`.venv\\Scripts\\python.exe -m pytest -q`，结果 `28 passed`；存在一条上游 `fastapi.testclient` deprecation warning，不影响本功能行为
- Python 编译：`.venv\\Scripts\\python.exe -m compileall -q apps/api/src tests`，通过
- 前端检查：`npm run typecheck`，通过；`npm run build`，通过；Vite 仅提示单页 Element Plus chunk 较大，本功能不提前做拆包工程
- 契约检查：API 进程内测试覆盖默认 GET、合法 PUT 后即时生效、重复 rule ID、未知 role、Resource/Tool 规则与 Trace `ruleId`
- 单一来源检查：`rg` 确认知识文档和 Agent 编排不再包含 `allowedRoles` 或 `sales/admin` 授权特判
- 人工步骤：按启动限制未运行浏览器页面；前端交互由共享 Type、代码审查、typecheck 和 production build 验证
- 启动状态：未启动服务，未发送真实 API 请求

## 实施记录

- 2026-08-26：F-003 验收并提交后开始 F-004。选择最小可执行 Contract，不引入数据库、审批流、版本冲突门或 Finding。
- 2026-08-26：三个 Luna 分别完成 Backend、Frontend 与 Test 范围；主代理修正 F-003 旧 Trace 断言并统一验收。当前 Contract 是资源与工具授权的单一来源，更新只保存在 Demo 进程内。
