# 知盾 AgentAudit 评委快速指南

> SYNTHETIC / DEMO ONLY。软件测试仓库内合成企业知识助手，不扫描外部系统，不读取真实企业数据，不发送真实邮件。

## 30 秒理解项目

知盾 AgentAudit 不是通用 Prompt Scanner。它先用 **Security Contract** 表达“谁能读什么、能调用什么工具、哪些外部动作需要审批”，再模拟外部不可信内容和内部合法用户越权，依据 Agent 实际产生的 Retrieval、Authorization、Tool 与 Sink **Trace** 判断是否违规，最后对同一个攻击执行修复 **Replay**。

```text
Security Contract
        ↓
Outside-in / Inside-out Attack Plan
        ↓
Target Agent → RAG / Mock Tool → Trace
        ↓
Contract Checker → Finding → 同 Plan Replay
```

## 三分钟只看这条主线

1. 双击启动“知盾 AgentAudit”，进入默认 Guided Audit；
2. 查看当前固定的 Source→Sink 测试目标：外部不可信内容诱导 Agent 处理机密资源并尝试外发；
3. 点击开始验收，确认页面显示真实 Actor、Source、Authorization、Tool、Sink Trace；
4. 查看 Critical Finding 的 `ruleId` 和证据序号，确认结论来自 Contract + Trace，而不是模型自评；
5. 对同一 Plan 点击 Replay，确认 BEFORE 为 failed，AFTER 在 secure Profile 下阻断且 passed。

评委只需回答三个问题：

- 攻击是否真实经过了目标 Agent、RAG/Mock Tool 和授权链？
- Finding 是否能指向具体 Contract Rule 和 Trace 证据？
- 修复后是否用同一个 plan、actor、target、message 完成 Replay？

三项都能在页面中核对，才是本项目的核心闭环。

## 再看两组质量证据

- **Provider Readiness**：显式检查 Target/Attack Provider 的连接、native Tool Calling 和 strict JSON；失败不会被包装成 Finding，也不会自动 fallback。
- **Acceptance Run**：一次保存 Retrieval、两个多身份 Differential、固定 24 Case CI Gate、Guided Scan/Finding/Replay，并支持历史对比和 JSON/Markdown 下载。

当前固定受控基线为 24/24 matched；本地 Ollama `qwen3:8b` 的真实 Run 为 22/24 matched、Recall 1、FPR 0、Policy Accuracy 0.95、Replay 1，Gate 如实 failed。项目没有通过重试、切换模型或修改 Ground Truth 隐藏这两个差异。

## 安装与运行边界

- 当前 Windows 安装包为 `artifacts/desktop/generated/知盾 AgentAudit_0.1.2_x64-setup.exe`；
- 安装后无需 Python、Node 或外部浏览器；桌面应用只启动自己的 loopback Sidecar；
- Application、AI Runtime 与 Workspace 分离；默认 Workspace 位于 `%LOCALAPPDATA%\AgentAudit`，升级不覆盖 Contract/History；
- F-026 当前机安装、启动和卸载已通过，但尚缺另一台无仓库、无 Python/Node 的干净 Windows 复核；
- F-027 已实现固定 loopback Ollama 发现、动态模型列表、显式选择与四项 Readiness；不自动启动 Ollama、不下载模型，也不按模型名称判定兼容性。

## 可信边界

- 所有人员、客户、文档、攻击 Case 和企业 Tool 都是合成或 Mock；
- Mock Mail 只写进程内 Outbox，Mock Export 只生成进程内 Artifact；
- 确定性 Finding 不交给 LLM，Semantic Review 只能补充解释；
- 指标只说明固定合成靶场的回归质量，不代表生产环境总体安全率；
- 当前不提供生产 IAM/SSO、多租户、真实 CRM/邮件、局域网服务或任意外部目标扫描。

## 进一步核对

- 申报事实：`artifacts/acceptance/SUBMISSION_BRIEF.md`
- 五分钟演示：`artifacts/acceptance/DEMO_RUNBOOK.md`
- 当前验收：`artifacts/acceptance/FINAL_ACCEPTANCE.md`
- 软件主线：`docs/PROJECT.md`
- 功能状态：`docs/STATUS.md`
