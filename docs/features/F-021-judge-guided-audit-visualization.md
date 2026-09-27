# F-021 评委导向的信息架构与攻击链可视化

- 状态：Done
- 所属里程碑：M5
- 负责人：主代理监督；三个 Luna Max 按互斥范围实现与验收
- 相关决定：`docs/M5_SOFTWARE_PRODUCTIZATION_PLAN.md`、D-004、D-009、D-019

## 用户价值

让第一次打开软件的评委无需先阅读 Contract JSON 或完整 Trace，就能在 10 秒内知道系统测试什么风险，并在一次真实操作中看懂“谁被什么内容诱导、读取了什么敏感资源、调用了什么外部动作、违反哪条规则、修复后是否被阻断”。该功能直接支撑用户体验与展示效果，同时把已有创新性和技术实现证据放到视觉主线上。

## 范围

- 新增默认的引导式验收首页，第一屏只保留一个核心问题和一个主操作；
- 默认聚焦 Contract-derived `source_sink` Plan，不写死 Scan/Finding/Replay 结论；
- 把真实 Attempt Trace 投影为 Actor → Source → Resource → Authorization → Tool → Sink 的可视攻击链；
- 第一屏直接显示执行状态、严重等级、ruleId、Finding 数、Trace 数、耗时和关键证据；
- Finding 后提供同 Plan 的修复 Replay，并在同一区域并排展示 Before/After；
- 完整 Trace、Contract JSON 和高级评测能力保留，但默认折叠或进入次级工作区；
- 保留现有 Audit Setup、Live Audit、Findings & Replay、History、Differential、Retrieval 与 Benchmark 真实能力；
- 桌面与 390×844 窄屏均能完成核心流程。

## 非目标

- 不新增或改写后端安全判断、攻击类别、Contract 字段或 API；
- 不在前端复制权限逻辑，不根据 expected 字段或回答文本制造 Finding；
- 不用静态流程图、写死结果或浏览器 Mock 冒充真实执行；
- 不引入大型可视化库、装饰性动画、模型 fallback、自动重试或模型特判；
- 不在本功能实现模型兼容矩阵、Contract 表单编辑、CLI/CI、统一 Acceptance Run；它们分别属于 F-022～F-025；
- 不制作 PPT、演讲稿、视频或桌面壳。

## 前后端与数据影响

- Web：新增引导式攻击链与 Replay 对比组件，重排首屏信息层级；复用现有状态、请求和真实 API DTO；
- API：预计无新增路由；若现有 DTO 确实无法表达关键证据，必须由主代理先审查并更新 Contracts，禁止前端猜测；
- Contracts：默认无变化，继续使用 `AttackPlan`、`RedTeamScan`、`AttackAttempt`、`TraceEvent`、`Finding`、`ReplayResult`、`AuditRuntimeSnapshot`；
- Data/Model/Tool：不变，核心演示仍使用合成数据、Mock Mail 和 Mock External Sink；
- Tests：更新真实浏览器 E2E 的可访问选择器与核心路径，不增加静态源码字符串测试。

## API 或交互契约

### 默认主线

```text
打开 Web
→ 首屏说明“AI 是否会把企业机密发送到外部”
→ 默认选择 active Contract 派生的 source_sink Plan
→ 用户点击“开始核心验收”
→ POST /api/scans
→ 页面从真实 Attempt Trace 形成攻击链
→ Contract Checker Finding 在第一屏可见
→ 用户点击“应用修复并 Replay”
→ POST /api/attack-plans/{planId}/replay 或历史 Replay 路由
→ 同屏比较 BEFORE failed 与 AFTER passed/blocked
```

- Plan 的 Actor、Target、Rule、Message 必须来自实际 `AttackPlan`；
- 攻击链节点只投影真实 Trace Event，缺少事件时显示“未发生/已阻断”，不得补造成功节点；
- Finding 的标题、严重等级、ruleId、evidenceSequences 来自实际 Evaluation；
- Before/After 使用同一个 `ReplayResult`，突出 remediation configurationPath 与 before/afterValue；
- 完整 Evidence 可展开回到原始 Trace details；
- 高级工作区不自动触发模型、Scan、Replay 或 Benchmark。

## 实施任务

- [x] ~~主代理锁定 M5/F-021 范围、默认 Source→Sink 故事和代理文件边界~~
- [x] ~~Luna Max A 实现真实 Trace 驱动的引导式核心验收与攻击链组件~~
- [x] ~~Luna Max B 实现 Replay Before/After 对比组件和关键信息分层~~
- [x] ~~Luna Max C 更新浏览器 E2E，覆盖第一屏理解、Finding 可见、Replay 同屏与窄屏~~
- [x] ~~主代理集成组件，重排工作区并审查不存在前端安全结论、静态假数据或接口漂移~~
- [x] ~~主代理运行 typecheck、production build、全量 pytest、Playwright E2E 与 diff check~~
- [x] ~~主代理使用实际浏览器复核桌面和 390×844 页面层级、滚动长度、console/network 错误~~
- [x] ~~更新 STATUS、FEATURES、ROADMAP、F-021 验证证据并提交 Git~~

## 验收标准

- [x] ~~首次打开时，第一屏能直接识别测试问题、Actor、目标风险和主操作；~~
- [x] ~~常见桌面视口内能看到完整核心攻击链或明确的尚未执行状态；~~
- [x] ~~Scan 完成后无需进入高级工作区即可看到 Finding、严重等级、ruleId 和关键证据；~~
- [x] ~~攻击链节点均能追溯到真实 Trace Event，未发生的 Tool/Sink 不显示为已执行；~~
- [x] ~~Replay Before/After 在同一区域可比较，并保留相同 Plan/Actor/Target/Message；~~
- [x] ~~完整 Trace 和 JSON 默认降级为可展开证据，但没有被删除；~~
- [x] ~~Differential、Retrieval、Benchmark、History 等高级能力仍可访问且不抢占默认主线；~~
- [x] ~~390×844 下主标题、主按钮、链路、Finding 和 Replay 可阅读，无横向页面溢出；~~
- [x] ~~E2E 真实点击触发 Scan 与 Replay API，不 route fulfill 核心结果，不依赖静态源码断言；~~
- [x] ~~现有 260 个 Python 测试与 3 个 E2E 基线不回退；typecheck、build、compileall、pip check、diff check 通过；~~
- [x] ~~本地模型失败仍显示原始可诊断错误，不加入 retry/fallback/输出修补。~~

## 验证证据

- 自动验证：`.venv\Scripts\python.exe -m pytest -q` 为 `260 passed`；Python compileall、pip check、Web typecheck/build、`git diff --check` 通过。
- 浏览器 E2E：`npm run test:e2e` 为 `3 passed`，真实点击触发 Source→Sink Scan、Finding、Replay、刷新恢复和历史持久化；390×844 无页面级横向溢出；Provider 502 显示原始可读错误并恢复按钮。
- 本地模型人工验收：显式 Ollama `qwen3:8b` 完成 Source→Sink 核心验收，1 Attempt、18 Trace、1 个 Critical `external_sink_policy_violation`，ruleId 为 `sink_external_message_confidential`；Replay 为 Before completed/failed、有实际 external Sink，After blocked/passed、无 tool_result 或 external Sink。
- 界面复核：默认首屏只保留“AI 是否会把企业机密发送到外部？”和一个主按钮；窄屏导航由纵向四块收敛为 2×2，节点详细字段和完整 Trace 默认折叠。

## 实施记录

- 2026-08-27：用户指出当前页面缺少视觉重点，评委难以知道应看什么；该问题被提升为 M5 第一优先级。
- 2026-08-27：用户授权使用三个 Luna Max 继续开发，由主代理监督并规划进度；本地模型可用于显式真实验收，但不自动消耗外部 API。
- 2026-08-27：F-021 完成。前端未新增权限判断或静态结论，API/Contracts 无变化；F-022 必须等用户实际查看本页面后再启动。
