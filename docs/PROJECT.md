# 项目主线

## 项目名称

**知盾 AgentAudit——企业知识助手业务权限安全验收与自动化红队系统**

对外简称统一使用 **知盾 AgentAudit**，英文代码标识统一使用 `agent-audit` / `agent_audit`。未经明确变更决定，不再恢复 AegisAC、AgentSec、AI 安全平台或 AI 版 Burp Suite 等旧命名和泛化定位。

## 一句话定义

知盾 AgentAudit 面向准备上线企业知识助手或 Agent 的开发与安全团队，自动模拟外部攻击者和内部越权用户，验证 AI 在身份、RAG、敏感数据、工具调用和外部动作上是否遵守企业 Security Contract，并生成可复现的攻击链与修复 Replay 结果。

## 目标用户

- 企业 AI 开发与平台团队；
- AppSec、安全测试和 AI 治理人员；
- 负责知识助手上线验收与权限治理的系统管理员。

## 核心问题

企业已有 IAM、RBAC、ACL 和业务规则，但 Agent 接入 RAG、外部内容和 Tool Calling 后，可能出现身份传递错误、对象级越权、敏感数据进入外部 Sink、工具参数超出业务授权等组合风险。知盾 AgentAudit 不替企业设计 ACL，而是验证 AI 接入后是否忠实执行既有权限和额外业务安全规则。

## 不可漂移的产品主张

1. **Security Contract Driven**：以角色、资源归属、敏感等级、工具、动作和审批条件描述业务安全不变量，并据此生成测试目标和判定条件。
2. **双攻击者模型**：同时覆盖 Outside-in（恶意文档/邮件等不可信来源）和 Inside-out（合法员工诱导越权查询、导出或调用工具）。
3. **Trace-based Evaluation**：观察 Actor、Source、Retrieval、Authorization、Tool Call、Arguments、Sink 与 Final Response，不只判断最终回答。
4. **Hybrid Judge**：确定性 Contract Checker 负责结构化规则，LLM 仅辅助语义风险理解，不能成为唯一裁决者。
5. **Remediation Replay**：对同一攻击 Case 展示漏洞版本失败、修复配置生效和 Replay 通过，形成检测—定位—修复—回归闭环。

## 比赛价值映射

| 评分方向 | 项目应提供的证据 |
|---|---|
| 创新性 | Security Contract + 业务权限 Trace，而非通用 Prompt 扫描 |
| 技术实现 | Red-Team Agent、RAG/Tool 靶场、Contract Checker、Hybrid Judge 与 Replay 闭环 |
| 实用价值 | 对企业知识助手执行上线前安全验收并定位配置根因 |
| 用户体验 | 非安全专家能够理解 Actor、Source、Resource、Tool、Sink 和违规规则 |
| 展示效果 | 五分钟内完成正常使用、自动攻击、发现链路、修复和同攻击 Replay |

## 当前范围

以下范围分为两个版本：v0.5 是已实现基础，v1.0 是当前开发目标。不得把目标能力写成已完成事实。

### v0.5 已实现基础

- 一个虚构企业知识助手靶场；
- 两类已闭环测试：对象级资源越权和单条客户查询工具越权；另有固定 Outside-in 不可信文档 Case，但尚未形成外部 Sink；
- 由角色、资源标签、资源归属、工具名称/动作和 Tool Owner 组成的基础 Security Contract；
- TF-IDF RAG、model_context/actor_response Sink 和一个可控 Mock Customer Tool；
- Outside-in 与 Inside-out 两类攻击 Case；
- 漏洞配置与修复配置两个可复现版本；
- Web Dashboard、后端 API、请求级 Trace/Finding、进程内 Contract 状态和 Replay 工件；
- 使用合成数据构建的固定 Ground Truth 测试集。

### v1.0 当前开发目标

- 显式 Red-Team Agent 状态机和最多 3 轮受控攻击变异；
- Source trust、Sink destination、批量阈值和审批条件可执行的 Security Contract；
- Mock Mail 与 Mock Customer Export 形成完整 Source→Sink 事实链；
- 至少 4 类 Actor 的同任务多身份差分验收；
- 本地 Permission-aware Embedding RAG；
- 至少 24 个非填充 Ground Truth Case 与扩展质量指标；
- Scan/Attempt/Finding/Replay 持久化和三个前端工作区；
- 关键 E2E、稳定性与目标环境复现验收。

详细需求、顺序和验收以 `docs/COMPETITION_V1_DEVELOPMENT.md` 为准。

## 明确非目标

- 通用 AI 红队平台；
- 覆盖所有 OWASP 风险；
- 扫描任意外部或未经授权的 AI Endpoint；
- 完整企业 IAM、Active Directory、SAP 或真实邮件系统；
- 发送真实邮件、访问真实企业文件或收集真实员工数据；
- 自研或训练大模型；
- 生产级多租户安全平台；
- 依赖 LLM-as-a-Judge 作为唯一裁决；
- Runtime Firewall、完整 MCP 生态或真实企业 Connector；
- 为尚未出现的规模问题预先建设微服务和复杂基础设施。

## 产品原则

- 先做“企业靶场 + RAG/Tool + 完整 Trace”，再做攻击生成和 Dashboard。
- 真实前后端调用、真实状态流转和真实 Trace 优先于视觉模拟。
- Security Contract 与确定性证据优先于模型主观判断。
- 一个新功能必须替项目主张服务，并有明确验收方法。
- 比赛版本追求完整、稳定、可解释，而不是功能数量。
- 所有比赛数据使用合成数据并明确标注 `SYNTHETIC / DEMO ONLY`。
- 模型是可替换基础设施，具体供应商和版本不构成项目创新点。

## 实施优先级

```text
v0.5 企业知识助手靶场与基础闭环（已完成）
→ v1.0 Red-Team Agent 状态机
→ Source→Sink 与业务工具约束
→ 多身份差分
→ Permission-aware Embedding RAG
→ 24+ Ground Truth
→ 持久化三工作区
→ 软件质量与目标环境复现
```

第一阶段若无法形成“带身份 + RAG 权限/归属 + Tool Trace”的真实靶场，应缩减攻击种类和展示功能；不得退化成“Prompt → Model → Judge → 风险分数”的通用扫描器。
