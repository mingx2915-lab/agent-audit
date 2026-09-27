# F-022 模型兼容性与运行就绪验收

- 状态：Completed
- 所属里程碑：M5
- 负责人：主代理监督；Backend/Frontend/Test Luna Max 按互斥范围实现
- 相关决定：`docs/M5_SOFTWARE_PRODUCTIZATION_PLAN.md`、D-004、D-009

## 用户价值

在正式 Scan 前明确回答“当前模型是否真的适合这个靶场”：Target Provider 是否能稳定返回文本和原生 Tool Calling，Attack Provider 是否能返回严格 JSON。评委和操作者能区分模型兼容性失败与安全 Finding，避免把 Provider 能力缺口误解为系统漏洞或静默伪造成成功结果。

## 范围

- 新增显式运行的 Provider Readiness API，不在页面加载时自动调用模型；
- 分别展示 Target Provider 与 Attack Provider 的名称、模型、职责和探针结果；
- Target 探针覆盖 connectivity/text 与原生 Tool Calling；
- Attack 探针覆盖 connectivity/text 与严格 JSON；
- 严格 JSON 只接受无 code fence、无额外字段、字段值完全匹配的 JSON Object；
- Tool Calling 只接受指定 Probe Tool 的一次原生 Tool Call 和完全匹配的参数；
- 从 active Contract 派生的四类 Plan 形成兼容矩阵，并明确列出其依赖的已执行探针；
- 首页显示 `READY / PARTIAL / UNAVAILABLE` 摘要，高级区可查看每项原始诊断；
- 使用本地 Ollama 进行一次显式真实验收；不调用 DeepSeek。

## 非目标

- 不自动重试、自动 fallback、模型探测、JSON 修补、code fence 剥离或宽松字段猜测；
- 不因 Readiness 结果自动阻止用户运行 Scan；它是可观察证据，不是新的硬门；
- 不把四个 Plan 全部执行一遍，不产生真实邮件或企业动作；
- 不把模型兼容性失败写成 Finding；
- 不允许浏览器读取或提交 API Key、Authorization header、Base URL 密钥参数；
- 不建设多模型路由、模型市场、自动评分排行榜或性能压测平台。

## 前后端与数据影响

- Web：新增 Provider Readiness 组件和显式检查按钮，在核心页显示最近一次结果；
- API：新增 `POST /api/provider-readiness`，请求体必须为空 Object；
- Contracts：新增 Readiness Result、Provider Role、Probe、Plan Compatibility DTO；
- Provider：只调用既有 `LLMProvider.complete`，不改变 Adapter 行为；
- Data/Tool：使用仅存在于请求中的合成 Probe Tool Schema，不执行 Mock Enterprise Tool；
- Persistence：本功能不持久化 Readiness，刷新后需用户重新显式检查；统一保存属于 F-025。

## API 或交互契约

### 请求

```http
POST /api/provider-readiness
Content-Type: application/json

{}
```

额外字段返回 422。页面加载、刷新、切换工作区均不得自动 POST。

### 响应结构

```text
ProviderReadinessResult
├─ id / checkedAt / status
├─ targetProvider
│  ├─ role=target
│  ├─ provider / model / status
│  └─ probes: connectivity, tool_calling
├─ attackProvider
│  ├─ role=attack
│  ├─ provider / model / status
│  └─ probes: connectivity, strict_json
└─ planCompatibility[]
   ├─ planId / basisType
   ├─ status compatible|incompatible
   ├─ requiredProbeIds[]
   └─ failedProbeIds[]
```

- `ready`：该角色的所有必需探针通过；
- `partial`：至少一个探针通过且至少一个失败；
- `unavailable`：所有探针失败；
- 总状态由两个角色状态确定，不允许模型自行填写；
- Plan 兼容性只由固定需求映射与本次真实 Probe 结果派生，不读取 expected Finding；
- Probe failure 记录安全、可读的 Provider 错误，不包含 credential 或请求头；
- Readiness 失败正常返回结构化 200 结果；API 自身契约错误仍返回 422，非 Provider 的未预期错误直接暴露为 500。

## 实施任务

- [x] ~~主代理锁定角色、探针、严格验证、Plan 映射和无 fallback 边界~~
- [x] ~~Backend Luna Max 实现 DTO、Readiness Runner 与 API~~
- [x] ~~Frontend Luna Max 实现就绪摘要、探针详情和 Plan 兼容矩阵~~
- [x] ~~Test Luna Max 覆盖严格 JSON、Tool Call、角色隔离、错误诊断和 API 行为~~
- [x] ~~主代理集成首页入口，审查不自动调用、不含密钥、不成为 Scan 硬门~~
- [x] ~~主代理运行全量自动验收与本地 Ollama 显式检查~~
- [x] ~~更新文档并提交 Git~~

## 验收标准

- [x] ~~页面加载和刷新不调用 Provider；只在用户点击后执行一次 Readiness；~~
- [x] ~~Target 与 Attack 使用各自注入的 Provider，调用和结果不串用；~~
- [x] ~~connectivity 接受非空文本响应，空响应沿用 ProviderResponseError；~~
- [x] ~~strict_json 拒绝 code fence、缺字段、额外字段、错误值和 Tool Call；~~
- [x] ~~tool_calling 拒绝纯文本、错误工具、多个调用、缺失/额外/错误参数；~~
- [x] ~~单项失败被记录为 failed，不触发 retry/fallback 或伪造 passed；~~
- [x] ~~四类 active Plan 均出现在矩阵中，兼容性可追溯到本次 Probe；~~
- [x] ~~Provider Configuration/Unavailable/Response 错误有可读诊断且不泄漏密钥；~~
- [x] ~~页面能区分 READY、PARTIAL、UNAVAILABLE，不把它们展示为 Finding；~~
- [x] ~~现有 Scan、Replay、Benchmark、Differential 和 Guided Audit 行为不回退；~~
- [x] ~~pytest、compileall、pip check、typecheck、build、E2E、diff check 通过；~~
- [x] ~~本地 Ollama 实际 Readiness 结果如实记录，不因比赛展示需要改写失败项。~~

## 验证证据

- 测试命令：`.venv\\Scripts\\python.exe -m pytest -q`、`npm run typecheck --workspace @agent-audit/web`、`npm run build --workspace @agent-audit/web`、`npm run test:e2e`、Python compileall、pip check、`git diff --check`。
- 自动结果：300 passed；3 Playwright E2E passed；compileall、pip check、typecheck、production build 与 diff check 通过。保留一个既有 Starlette/httpx deprecation warning 和 Vite chunk-size warning，不影响本功能结论。
- 本地模型结果：Ollama `qwen3:8b` 在真实 API 与核心页显式执行两次，Target connectivity、Target native Tool Calling、Attack connectivity、Attack strict JSON 四项均 passed；Target/Attack 均 READY，四类 active Plan 均 compatible。首次 API 四项耗时约 4230.01 / 1044.77 / 533.80 / 650.87 ms；页面复核四项约 774.69 / 887.99 / 652.75 / 631.55 ms。
- 边界：未调用 DeepSeek；Readiness 没有自动运行、没有写入 Finding、没有成为 Scan 硬门，也没有持久化。

## 实施记录

- 2026-08-27：用户确认 F-021 基本达到预期，并授权连续完成后续软件功能，不再逐项等待确认。
- 2026-08-27：三个 Luna Max 完成后端、前端和测试互斥切片；主代理完成接口/UI 集成、全量回归、浏览器复核和本地 Ollama 真实验收。
