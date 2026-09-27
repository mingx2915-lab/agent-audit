# F-064 权限拦截执行结果

- 状态：Done
- 所属里程碑：M6
- 相关决定：用户要求修复固定 Case/Plan 的权限拒绝被显示为程序报错的问题；本轮优先处理，F-063 安装验收仍待完成。

## 用户价值
权限拒绝后仍能查看已经发生的过程和安全判定，区分工具拦截与先前资源越权。

## 范围
固定 Case 和 Plan HTTP 执行接口、共享 Contracts、设置页执行结果。

## 非目标
不放宽权限，不伪造回答，不改变 Benchmark 判分或内部执行器的异常契约，不重试至成功。

## 前后端与数据影响
- API：权限拒绝返回结构化 blocked 结果及拒绝前 Trace、确定性 Evaluation。
- Web：显示拦截状态、风险判定和可展开的执行证据。
- Contracts：执行结果支持 queryResult=null 的 blocked 分支。
- 数据/模型/工具：无权限规则与持久化变更。

## 验收标准
- [x] 拒绝返回 HTTP 200 的执行结果，服务故障仍返回错误。
- [x] 拒绝前越权仍可被检测，不自动宣称测试通过。
- [x] 页面显示中文拦截结果及 Trace，不显示旧红色异常条。

## 验证证据
- `.venv/Scripts/python.exe -m pytest tests -q`：891 passed、10 skipped。
- `npm run typecheck`：Contracts/Web/Desktop 通过。
- `npx playwright test --config output/provider-scroll-20260909/playwright.config.ts tests/e2e/blocked_execution.spec.ts`：2/2 通过；使用隔离服务与浏览器响应样本验证 UI，后端另有 4 项真实规则回归。
- 本机 qwen3:8b + BGE，真实固定 Case 返回 200/blocked，11 步 Trace、1 项 resource_authorization_bypass（证据步骤 5、10）。见 `output/blocked-result-20260909/real-case.json`。
- 用户 8000 后端已重启，重启前契约已读取并比对保留；5173 前端已热更新。
- 未改变内部 Executor、Replay、Benchmark 的既有语义，未宣称此前 22/24 的固定验收已变为通过。

## API 或交互契约

`POST /api/attack-cases/{case_id}/execute` 与 `POST /api/attack-plans/{plan_id}/execute`：原完成分支不变；权限拒绝分支返回 HTTP 200，包含原 case/plan、`executionStatus: blocked`、`queryResult: null`、`blockedReason`、`traceEvents`、`evaluation`。客户端用 queryResult 区分是否存在完整助手回答。连接/响应错误保留原有 HTTP 错误语义。

设置页显示独立权限拦截卡、已发生的风险及其证据编号，可展开原始 Trace。执行被拦截后自动定位结果卡，不虚构模型回答，不自动重试。
