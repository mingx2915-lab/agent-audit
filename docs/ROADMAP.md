# 路线图

路线图用于控制顺序，不作为代码中的硬状态机。里程碑可以根据真实证据调整，但调整必须记录原因和影响。

## M0 项目基线与框架收敛 — 已完成

目标：建立主线、目录、任务记录和验收方法，使项目能够在跨会话与上下文压缩后继续。

完成条件：

- 项目范围与非目标明确；
- 前后端目录和命名明确；
- 功能任务有 Markdown 状态记录；
- 完成项有勾选、删除线和验收证据。
- 产品名称、四条核心主张、MVP边界和全栈技术基线已统一。

## M1 最小可运行产品 — 已完成

目标：形成真实前后端、企业知识助手靶场、Security Contract、Trace 和 Hybrid Judge 闭环。

阶段成果：

```text
Web → API → Enterprise Agent → RAG/Mock Tool → Trace → Contract Result → Web
```

结束条件：角色、资源、标签和工具规则能够进入可执行契约；错误配置能够被检出，正确配置能够通过，结果可在页面中解释并重复执行。

## M2 核心差异化能力 — 已完成

目标：证明知盾 AgentAudit 与通用 Prompt Scanner 的差异。

结束条件：系统能够从 Security Contract 生成测试，分别执行外部不可信内容和内部员工滥用场景；能够根据 Source→Retrieval→Authorization→Tool→Sink Trace 定位违规，并以同一攻击完成修复 Replay。

## M3 比赛交付 — 已完成

目标：把可运行产品转化为可评分、可复现的比赛作品。

结束条件：固定 Ground Truth 基准集、Dashboard、五分钟 Runbook、申报事实底稿、答辩材料和演示备份一致；所有对外能力主张都有实际证据。未收到比赛 PPT/视频/表单模板时不臆造格式交付物，后续只按用户提供的模板适配。

> M3 完成的是 v0.5 基础闭环及当时范围内的交付准备。用户提供正式评分表并重新要求继续软件开发后，不再把 M3 视为最终竞赛完成状态。

## M4 竞赛强化版软件开发 — 已完成

目标：把 v0.5 的确定性测试闭环强化为真正可评分的 v1.0 软件产品，使 AI 深度体现在攻击规划、受控变异和 Trace 观察中，同时补齐 Source→Sink、多身份差分、Permission-aware Embedding RAG、24+ Ground Truth、持久化产品流和软件质量证据。

顺序：

```text
F-013 需求基线
→ F-014 Red-Team Agent 状态机
→ F-015 Source→Sink 与 Mock Mail/Export
→ F-016 多身份差分
→ F-017 Embedding RAG
→ F-018 24+ Ground Truth
→ F-019 持久化与三工作区
→ F-020 E2E、稳定性与目标环境复现
```

结束条件见 `docs/COMPETITION_V1_DEVELOPMENT.md`。M4 只做软件和软件运行证据，PPT、视频、申报排版不在当前路线内。

## M5 软件产品化与评委体验 — 已完成

目标：不扩张安全测试范围，优先让评委在第一屏看懂测试目标、真实攻击链、确定性 Finding 和同攻击修复 Replay，再补齐模型就绪、Contract 编辑、CLI/CI 与统一验收历史。

顺序：

```text
F-021 评委导向的信息架构与攻击链可视化
→ F-022 模型兼容性与运行就绪验收
→ F-023 可视化 Security Contract 编辑器
→ F-024 最小 CLI / CI 安全门
→ F-025 统一 Acceptance Run 与历史对比
```

完整范围和完成证据见 `docs/M5_SOFTWARE_PRODUCTIZATION_PLAN.md` 与 `docs/features/F-021-*` 至 `F-025-*`。F-021 至 F-025 已按顺序完成；当前冻结软件范围，等待用户检查，不自动进入材料制作或新的功能里程碑。

## M6 本地双平台产品化 — 进行中

目标：把现有 Contract → Trace → Finding → Replay 软件主链打包为无需外部浏览器、Python/Node 命令和仓库目录的本地桌面软件；保持单一业务权限安全验收产品，将 Application、AI Runtime 与 Audit Workspace 分离，并由同一代码库交付 Windows 与 Linux。

```text
F-026 Windows 桌面壳与可移植 Workspace 基础
→ F-027 首次启动与本地/内网模型连接
→ F-028 企业 Workspace 与资料导入
→ F-029 Windows/Linux 安装、迁移与本地运维
```

F-026 的历史范围见 `docs/M6_SMALL_BUSINESS_DESKTOP_PLAN.md`，后续权威范围见 `docs/M6_LOCAL_DUAL_PLATFORM_PRODUCT_PLAN.md`。F-026 已完成当前 Windows 环境的 Desktop、Sidecar、Workspace、真实 release 与 NSIS 安装/卸载实现，另一台干净 Windows 的复核仍是未完成外部证据。当前活动功能为 F-035；软件实现和自动化验收已通过，但真实 Windows 文件对话框与未读源码用户五分钟任务尚未完成，因此不得勾选。

## 四周参考节奏

以下节奏以三人并行开发为参考，不是代码硬门；团队规模或截止日期变化时按同一里程碑顺序缩放。

| 周次 | 必须形成的可运行结果 |
|---|---|
| 第 1 周 | 身份 → 企业知识助手 → RAG/Mock Tool → 完整 Trace；不做大屏 |
| 第 2 周 | Security Contract、Contract Checker 和首批固定 Case 能自动运行 |
| 第 3 周 | 双攻击者、Hybrid Judge、Finding 与同攻击 Replay 闭环 |
| 第 4 周 | Ground Truth 评测、Dashboard、Docker 演示和比赛材料 |

若资源不足，优先砍掉复杂多轮攻击、PDF 自动导出、多模型和复杂图表，保留一个靶场、三至四类场景、Security Contract、Trace、Finding、Replay 和清晰前端。

上表是历史 v0.5 参考节奏。M4 以功能验收而非原四周表判断进度；Red-Team Agent、多身份差分和真实 Source→Sink 已成为 v1.0 必需项，不再按历史建议直接砍除。
