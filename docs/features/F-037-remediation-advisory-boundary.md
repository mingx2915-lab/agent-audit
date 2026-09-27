# F-037 修复参考与模拟复测边界

- 状态：Done
- 所属里程碑：M6 本地双平台产品化
- 相关功能：F-009、F-011、F-021、F-025

## 用户价值

避免企业用户把 AgentAudit 的 Contract-based remediation 当成生产故障根因、自动修复结果或可直接上线的配置指令。用户仍能看到具体控制项和 Before/After Trace，但必须知道它只是基于当前 Security Contract 与合成靶场的验证参考。

## 范围

- 将用户界面的“修复配置/修复项”收敛为“修复参考/模拟复测”；
- 在 Guided Replay、历史 Replay、Acceptance Run 与攻击链报告中显示同一条边界说明；
- 导出的 Markdown 报告必须保留“仅供参考、未修改企业系统、不替代根因分析和变更审批”；
- 保持 Replay 的确定性执行、API DTO、Finding 与 Security Contract 判定不变。

## 非目标

- 不新增自动根因分析；
- 不连接或修改企业生产配置；
- 不自动生成可执行脚本、补丁或部署指令；
- 不把 LLM 建议提升为确定性安全结论；
- 不改变现有 Replay 只切换到内置 `secure` Profile 的事实。

## 验收标准

- [x] ~~Guided 主线明确显示“仅供参考”及模拟复测边界~~；
- [x] ~~高级历史、Acceptance Run 和攻击链报告使用一致语义~~；
- [x] ~~Markdown 导出保留免责声明~~；
- [x] ~~Replay、报告与现有 E2E 不回归~~；
- [x] ~~typecheck、build、相关 Python 测试和 E2E 通过~~。

## 验证证据

- Replay/Reporting 定向：14 passed，1 个既有 Starlette/httpx deprecation warning；
- Python 全量：622 passed、6 skipped、1 个既有 warning；
- Playwright：主线定向 4 passed，全量 20 passed；
- Web：typecheck 与 production build 通过，仅保留既有 Vite chunk-size warning；
- 行为边界：提示在运行 Replay 前即可见；结果、历史、Acceptance Run、攻击链页面和 Markdown 导出均明确“仅供参考、不修改企业系统、不替代根因分析与变更审批”；
- Replay 实现、active Contract、Finding 和 API DTO 未改变。
