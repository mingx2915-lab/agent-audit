# F-023 可视化 Security Contract 编辑器

- 状态：Completed
- 所属里程碑：M5
- 负责人：主代理监督；Backend/Frontend/Test Luna Max 按互斥范围实现
- 相关决定：`docs/M5_SOFTWARE_PRODUCTIZATION_PLAN.md`、D-004、D-009

## 用户价值

让非安全专业用户直接理解并维护“谁能访问什么、能调用什么、哪些外部动作需要审批”。保存前同时看到规则字段变化与 Contract-derived Attack Plan 的新增、删除或变化，避免盲改 JSON 后才发现验收范围被改变。

## 范围

- 在高级设置工作区以 Visual 模式作为默认 Contract 编辑入口；
- 支持编辑当前 Contract 已有字段：角色显示名、资源标签/允许角色/owner-match、Tool/action/允许角色/owner-match/maxRecords/approval、Sink type/标签/允许角色/allowExternal/approval/blocked source trust levels；
- Visual 与 Advanced JSON 使用同一 `SecurityContract` Draft，可在两种模式间切换且不丢失未保存修改；
- 新增无副作用 Preview API，以 active Contract 和候选 Contract 计算字段变化与 Planner 派生 Plan 变化；
- 只有用户明确确认保存才调用既有 PUT；Preview 不修改 active Contract、Plan、历史或模型；
- 保存成功后重新加载 active Contract 与 Plans，并展示本次实际修改的字段；
- Replay 修复仍由现有系统执行；编辑器只突出规则影响，不自动写入任何生产系统。

## 非目标

- 不设计通用策略 DSL、条件表达式语言或任意 JSON Schema Builder；
- 不新增 IAM、SSO、用户生命周期、云同步、多租户或生产配置下发；
- 不允许新增/删除角色 ID、规则 ID 或改变当前 DTO 之外的权限语义；
- 不自动保存、不自动运行 Scan/Replay/Benchmark，不把 Preview 当安全 Finding；
- 不在前端复制 Planner、Security Contract Checker 或授权判定；
- 不用 hash、hard gate、回退、启发式 diff 或字符串比较代替结构化比较。

## 前后端与数据影响

- Web：新增 Visual Contract Editor；保留 Advanced JSON；显示 Unsaved Changes、结构化 Diff 与 Plan Impact；
- API：新增 `POST /api/security-contract/previews`，请求体为完整候选 `SecurityContract`；
- Contracts：新增 `SecurityContractPreview`、`ContractFieldChange`、`AttackPlanChange`；
- Planner：Preview 复用现有 `ContractAttackPlanner`，不得修改 active Contract；
- Persistence：仍为 Demo 进程内 active Contract；F-025 才统一保存 Acceptance Run；
- Provider/Model/Tool：本功能不调用 Provider、不执行 Tool、不访问外部网络。

## API 或交互契约

### Preview

```http
POST /api/security-contract/previews
Content-Type: application/json

<完整 SecurityContract DTO>
```

响应：

```text
SecurityContractPreview
├─ contractId / activeVersion / candidateVersion
├─ fieldChanges[]
│  ├─ path
│  ├─ kind=added|removed|changed
│  └─ beforeValue / afterValue
├─ planChanges[]
│  ├─ planId
│  ├─ kind=added|removed|changed
│  └─ basisType / basisRuleId
├─ currentPlans[]
└─ candidatePlans[]
```

- `fieldChanges` 只比较当前 DTO 的结构化字段，顺序稳定；
- `planChanges` 以 Planner 实际输出比较，不由前端猜测；
- 无变化时两个 changes 数组为空；
- 候选 DTO 非法或含额外字段返回 422；
- Preview 必须是纯读取计算，完成后 GET Contract 与 GET Plans 结果不变。

### Visual editor

- 默认只读摘要；点击“可视化编辑”后进入 Visual Draft；
- Visual/Advanced JSON 切换共享同一个 Draft；JSON 解析失败时保持原文并阻止 Preview/Save；
- 点击“预览影响”后才调用 Preview API；任何 Draft 改动都会使旧 Preview 标记为过期；
- 保存按钮只在当前 Draft 已成功 Preview 且 Preview 对应当前 Draft 时可用；这是用户确认流程，不是文档 hash 或安全硬门；
- 保存成功后退出编辑态，刷新 Contract/Plan，并显示已保存字段与 Plan 影响；
- 取消恢复 active Contract，不发 PUT；页面加载与刷新不发 Preview/PUT。

## 实施任务

- [x] ~~主代理锁定 Visual/JSON 共用 Draft、Preview API、结构化 Diff 与无副作用边界~~
- [x] ~~Backend Luna Max 实现 Preview DTO、稳定结构化比较与只读 API~~
- [x] ~~Frontend Luna Max 实现 Visual/JSON 编辑、字段控件、Diff 与 Plan Impact~~
- [x] ~~Test Luna Max 覆盖 Preview 纯函数/API、编辑状态、无自动写入和旧功能回归~~
- [x] ~~主代理集成 App、审查不复制权限逻辑并完成浏览器验收~~
- [x] ~~主代理运行全量自动验收与本地 UI 人工复核~~
- [x] ~~更新文档并提交 Git~~

## 验收标准

- [x] ~~角色、ResourceRule、ToolRule、SinkRule 当前全部字段均可视化显示并按类型编辑；~~
- [x] ~~allowedRoles 使用当前 Contract 角色的多选，boolean 使用明确开关，maxRecords 使用 number/null 语义；~~
- [x] ~~Visual 与 Advanced JSON 共用 Draft，来回切换不丢失有效修改；~~
- [x] ~~Preview 返回稳定字段路径、before/after 与 added/removed/changed 类型；~~
- [x] ~~Preview 的 Plan Impact 来自真实 Planner，规则开关变化能显示对应 Plan 的新增/删除/变化；~~
- [x] ~~Preview 前后 active Contract、active Plans、历史与 Provider calls 不变；~~
- [x] ~~保存前页面明确显示字段变化和 Plan 变化；取消不 PUT；保存只 PUT 一次；~~
- [x] ~~保存后 GET Contract/Plans 与页面一致，版本和规则影响可见；~~
- [x] ~~JSON 非法、DTO 非法、额外字段和 API 失败有可读错误且不静默修补；~~
- [x] ~~页面加载/刷新不 Preview、不 PUT、不调用 Provider；~~
- [x] ~~390×844 可完成 Visual edit → Preview → Save，无页面级横向溢出；~~
- [x] ~~现有 Guided Audit、Readiness、Scan、Replay、Benchmark、Differential 行为不回退；~~
- [x] ~~pytest、compileall、pip check、typecheck、build、E2E、diff check 通过。~~

## 验证证据

- 测试命令：`.venv\\Scripts\\python.exe -m pytest -q`、Python compileall、pip check、`npm run typecheck --workspace @agent-audit/web`、`npm run build --workspace @agent-audit/web`、`npm run test:e2e`、`git diff --check`。
- 自动结果：310 passed；5 Playwright E2E passed；compileall、pip check、typecheck、production build 与 diff check 通过。保留一个既有 Starlette/httpx deprecation warning 和 Vite chunk-size warning。
- 浏览器人工验收：取消一个改名 Draft 后页面和 GET Contract 保持默认；将 `resourceRules[resource_customer_owner].requireOwnerMatch` 从 true 改为 false 后，Preview 显示 1 个字段变化、4→3 Plans，并由真实 Planner 标记删除 `plan_resource_customer_owner`；保存只 PUT 一次，随后页面退出编辑态并显示实际字段路径和 Plan 变化 1 项。
- 边界：本功能未调用 Provider/DeepSeek/Ollama，Preview 不写 active state，所有保存仅作用于 Demo 进程；人工验收进程停止后恢复默认 Contract。

## 实施记录

- 2026-08-27：F-022 完成后按用户授权直接进入；不增加策略语义，只把现有 Contract 变成可维护产品界面。
- 2026-08-27：三个 Luna Max 完成 Preview 后端、Visual Editor 和测试互斥切片；主代理完成 App 集成、保存态修正、全量回归与浏览器人工验收。
