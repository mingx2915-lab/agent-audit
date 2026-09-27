# F-011 攻击链 Dashboard 与 Markdown 报告

- 状态：Done
- 所属里程碑：M3
- 负责人：主代理监督；Backend/Frontend/Test Luna 分工实现
- 相关决定：D-002、D-003、D-004、D-007、D-009、D-016

## 用户价值

把一次已完成的真实 Replay 整理为非安全专家也能快速阅读的 before/after 攻击链，并下载包含 Actor、Source、Resource、Authorization、Tool、Sink、Rule、Finding 与修复证据的 Markdown 报告，直接服务五分钟比赛演示和评委复核。

## 范围

- 定义 `AttackChainReport`，完整包含原 `ReplayResult`、生成时间、标题、执行摘要和 Markdown；
- 实现纯 `build_attack_chain_report(replay)`：只读取提交的 Replay 工件，不调用 Provider、Retriever、Tool、Checker 或 ReplayExecutor；
- 新增 `POST /api/attack-chain-reports`，请求体为现有 `ReplayResult`，响应为 `AttackChainReport`；
- Markdown 报告固定包含：
  - `SYNTHETIC / DEMO ONLY` 声明；
  - Plan、Actor、攻击者类型、Rule basis、Target；
  - before/after Profile、execution/evaluation 状态与 Finding 数；
  - 实际 Finding 的 category、ruleId、证据 sequence；
  - 修复 configuration path 与 false→true；
  - before/after 完整 Trace，保留 sequence、type、summary、details；
  - Replay 最终结论；
- 前端在已有 Replay 完成后才允许“生成攻击链报告”；
- 新增独立 `AttackChainReportView` 组件，显示执行摘要、修复项、before/after 双栏 Trace 链、实际 Finding，并提供 Markdown 下载；
- 双栏链只用 Vue/CSS 与已有 Element Plus，不为一张图引入 ECharts 或其他可视化依赖；
- 后端单元/API 进程内集成测试与前端 typecheck/build。

## 非目标

- 重新执行攻击、Replay、Benchmark 或任何模型请求；
- 从 Ground Truth expected、Plan expected 或展示字段重新计算实际结论；
- 把用户提交的报告工件作为服务端持久化审计记录；
- 数据库、历史列表、趋势图、团队分享、PDF/DOCX、邮件发送或云存储；
- LLM 总结、自动改写、风险打分或第二套 Finding；
- 新攻击能力、外部扫描、真实企业数据；
- 启动服务或发送真实 DeepSeek 请求。

## 前后端与数据影响

- Web：新增报告生成按钮和独立攻击链报告组件；浏览器按用户点击下载 `.md`；
- API：新增纯报告生成端点；现有执行端点不变；
- Contracts：新增 `AttackChainReport`；
- Data/Model/Tool：无变化，报告完全来自请求中的 ReplayResult。

## API 或交互契约

### `AttackChainReport`

```json
{
  "id": "report_replay_plan_resource_customer_owner",
  "generatedAt": "2026-08-26T00:00:00Z",
  "title": "资源 owner-scope 攻击链 Replay 报告",
  "executiveSummary": "漏洞配置下发现 1 个 Finding；切换 secure 后通过 Replay。",
  "replay": {},
  "markdown": "# ..."
}
```

### `POST /api/attack-chain-reports`

- 请求体：完整 `ReplayResult`；
- 响应：`AttackChainReport`；
- Pydantic 信任边界校验失败返回 422；
- 不读取或修改 active Contract/app state，不调用 Provider，因此报告生成不会增加模型调用次数。

## Python 公共接口

- 模块：`agent_audit_api.reporting`；
- `AttackChainReport(CamelModel)`：字段严格为 `id`、`generated_at`、`title`、`executive_summary`、`replay`、`markdown`；
- `build_attack_chain_report(replay: ReplayResult) -> AttackChainReport`。

## 执行不变量

1. `report.replay` 与请求 ReplayResult 结构相等，Builder 不修改输入；
2. 报告结论只展示 `ReplayResult.status` 与两侧实际 Evaluation，不重新判定；
3. Ground Truth/Plan 的 expected Finding 不进入执行摘要、实际 Finding 或结论；
4. Trace 按 sequence 稳定排序；报告保留原 event details，不删除 denied、blocked 或空 QueryResult 事实；
5. blocked after 必须明确写明无模型回答，并保留 `blockedReason`；
6. Markdown 下载由用户点击触发，文件名仅使用稳定 report ID；
7. 不产生服务端文件、数据库记录或隐藏状态。

## 实施任务

- [x] ~~主代理建立报告共享契约和内容边界~~
- [x] ~~Backend Luna 实现纯 Report Builder 与 API~~
- [x] ~~Frontend Luna 实现攻击链报告组件与 Markdown 下载~~
- [x] ~~Test Luna 实现内容完整性、判定独立性与零 Provider 调用测试~~
- [x] ~~主代理审查报告不重新判定、不丢失关键 Trace~~
- [x] ~~执行编译、测试、typecheck 与 build，不启动服务~~
- [x] ~~记录验收证据并更新状态~~

## 验收标准

- [x] ~~真实 Resource Replay 可生成报告，包含 denied→context Finding 与 secure after 不进 context 的两侧 Trace；~~
- [x] ~~真实 Tool Replay 可生成报告，before 含 denied→tool_call→tool_result，after blocked 且无 tool_call/result；~~
- [x] ~~报告明确展示 Actor、Source、Resource、Authorization、Tool、Sink、Rule、Finding、修复与 Replay；~~
- [x] ~~report.replay 与输入结构相等，输入对象未被修改；~~
- [x] ~~篡改 expected/display 字段不能改变报告中的实际 Evaluation/Finding/Replay 结论；~~
- [x] ~~报告生成期间 Provider 调用数不增加，也不访问 active Contract；~~
- [x] ~~无效 ReplayResult 请求返回 422；~~
- [x] ~~前端只能在已有 Replay 后生成报告，能双栏阅读 Trace，并下载内容一致的 Markdown；~~
- [x] ~~没有重新执行、LLM 总结、持久化、历史、趋势图、PDF/DOCX、分享或 F-012 能力；~~
- [x] ~~所有非启动验收通过，未监听端口、未发送真实模型请求。~~

## 验证证据

- 测试命令：`.venv\Scripts\python.exe -m pytest -q`；`.venv\Scripts\python.exe -m compileall -q apps/api/src tests`；`npm run typecheck`；`npm run build`；`git diff --check`
- 结果：103 tests passed；Python compileall、Vue typecheck、Vite production build 与 diff check 通过。仅保留 TestClient 上游弃用提示和 Vite chunk size 提示。
- 人工步骤：主代理逐项核对 API、Builder、Vue 触发条件与下载函数；确认 Markdown 来源为当前 `report.markdown`、文件名为稳定 report ID。未启动服务；实际浏览器点击与视觉节奏留到获准首次启动后的演示验收。
- 启动状态：未启动服务，未发送真实 API 请求

## 实施记录

- 2026-08-26：F-010 验收并提交后开始 F-011。报告以现有 ReplayResult 为唯一事实输入，不为报告重新执行攻击或模型。
- 2026-08-26：当前不安装 ECharts；before/after Trace 用紧凑双栏链即可清楚表达，减少依赖和包体积。
- 2026-08-26：完成纯 Report Builder 与进程内 API。Resource/Tool Replay 测试证明两侧完整 Trace、实际 Finding、blockedReason 与空 QueryResult 均被保留，报告生成不增加 Provider 调用且不读取 active Contract。
- 2026-08-26：完成独立 `AttackChainReportView`，用 Vue/CSS 双栏展示 before/after，并仅在已有 Replay 时允许生成和手动下载 Markdown；未引入图表、持久化、LLM 总结或 F-012 能力。
