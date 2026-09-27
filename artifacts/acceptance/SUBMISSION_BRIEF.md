# 申报事实底稿

> 本文是适配不同比赛表单、PPT 和视频文案的事实源，不代表任何特定主办方格式。

## 项目名称

**知盾 AgentAudit——企业知识助手业务权限安全验收与自动化红队系统**

## 一句话介绍

面向准备上线企业知识助手或 Agent 的开发与安全团队，从 Security Contract 自动派生授权边界测试，执行 Outside-in 与 Inside-out 攻击，并依据 Retrieval、Authorization、Tool、Sink 全过程 Trace 生成 Finding 和同攻击修复 Replay 证据。

## 解决的问题

企业已有角色、资源归属与工具权限规则，但 Agent 接入 RAG 和 Tool Calling 后，可能发生“授权判断为 denied，资源仍进入模型上下文”或“工具参数越过对象归属范围”等组合问题。只检查最终回答或 Prompt 文本无法可靠定位这些中间过程违规。

## 核心方法

1. **Security Contract Driven**：用角色、资源标签/归属、工具动作和 owner-match 表达业务安全不变量。
2. **双攻击者**：固定 Outside-in 不可信文档场景与 Inside-out 合法员工越权场景。
3. **Permission-aware Embedding RAG**：本地 BGE Embedding 是主路径，检索候选仍经过确定性授权过滤；TF-IDF 只作为显式对照，不自动 fallback。
4. **Trace-based Evaluation**：记录 input、source、retrieval、authorization、tool_call、tool_result、sink 和 model_response。
5. **Hybrid Judge**：Contract Checker 对结构化 Trace 确定性判定；LLM Semantic Review 仅可选补充。
6. **Remediation Replay**：对同一个 plan、actor、target 和 message，在漏洞与 secure Profile 下各执行一次，证明修复是否真正阻断原攻击。

## 真实实现边界

| 层 | 当前实现 | 不应声称 |
|---|---|---|
| Web | Vue 3、TypeScript、Element Plus，真实调用 FastAPI；Audit Setup、Live Audit、Findings & Replay 三个工作区 | 不是静态大屏；不是生产级多租户管理后台 |
| API/History | FastAPI 模块化单体；SQLite 保存 Scan/Attempt/Trace/Finding/Replay、Acceptance Run 和不可变配置快照；CLI Gate 与 HTTP 复用同一 Runtime | 不是生产级多租户、云端分布式服务或企业 IAM |
| RAG | 仓库合成文档上的 BGE Embedding（`BAAI/bge-small-zh-v1.5`）Permission-aware 主路径；TF-IDF 仅显式对照/测试注入 | 不是大规模向量数据库或生产知识库 |
| Tool | Mock Customer Lookup、Mock Mail、Mock Customer Export；真实参数解析、授权、Tool/Source→Sink Trace | 不连接真实 CRM，不发送真实邮件，不读取真实客户数据 |
| Provider | 默认 DeepSeek Adapter；可显式选择本地 Ollama；可测试注入 Test Double | 不自动发现、下载、重试或 fallback；供应商/模型版本不是创新点 |
| Judge | 确定性 Contract Checker + 可选 Semantic Review | LLM 不能覆盖确定性 Finding |
| 部署 | Tauri Desktop + PyInstaller FastAPI Sidecar + NSIS current-user 安装包已在当前 Windows 机验证；Sidecar 仅 loopback，Workspace 使用 `%LOCALAPPDATA%\AgentAudit` 边界 | 尚未在无仓库、无 Python/Node 的干净 Windows 复核；Docker build/up、Linux/macOS 安装包未完成 |

## 评分证据映射

| 评分方向 | 分值 | 可验证主张 | 仓库证据 |
|---|---:|---|---|
| 创新性 | 30 | Contract-derived 测试、双攻击者、Permission-aware RAG 与业务权限全过程 Trace，而非通用 Prompt 分类 | `security_contract.py`、`planning.py`、`trace.py`、F-008/F-015/F-017/F-018 测试 |
| 技术实现 | 30 | Red-Team Agent、Retriever/Authorization/Tool/Provider 真实链路、确定性 Checker、Replay、SQLite History 与可重复验收 | `services/assistant.py`、`attack_cases.py`、`replay.py`、F-019/F-024/F-025/F-026 验证 |
| 实用价值 | 20 | Finding 指向 ruleId 和 evidence sequence；Contract 可编辑，扫描可保存，Acceptance Run/CLI Gate 可复核，修复可 Replay | `evaluation.py`、`replay.py`、`App.vue`、F-023/F-025 测试 |
| 用户体验 | 10 | 三个工作区显示 Contract、计划、Trace、Finding、before/after、历史和可读错误；当前机可由桌面窗口启动 | `App.vue`、`AttackChainReportView.vue`、7 个 Playwright E2E、F-026 验证 |
| 展示效果 | 10 | 软件本身可连续展示正常行为、攻击、定位、修复、Replay、报告和质量证据 | `DEMO_RUNBOOK.md`、`reporting.py`、`benchmark.py`、Acceptance Run 记录 |

## 当前质量证据

- 固定 Ground Truth：24 Case，四类各 6 个：正常行为、内部业务越权、Outside-in / Source→Sink、工具阈值与 Replay。
- RAG 对比验收：固定 6 Query 的 BGE Top-1 为 6/6、MRR = 1.0；TF-IDF 为 1/6、MRR = 0.555556。TF-IDF 保留为显式对照，不作为 BGE 失败时的自动 fallback。
- 当前全量自动验收：Python `416 passed, 1 skipped`；指定本次 release `.exe` 后 Desktop 配置与真实启动 smoke 为 `7 passed`；Playwright E2E 为 `7 passed`。`compileall`、`pip check`、TypeScript typecheck、Vite production build、Rust `cargo check`、`rustfmt` 和 diff check 通过。
- SQLite 已保存 Acceptance Run 历史、Scan/Attempt/Trace/Finding/Replay 及 Contract/Plan/Profile/Runtime 快照；CLI Gate 固定运行仓库 24 Case，并与 HTTP 复用同一 Runtime。
- 本地 Ollama `qwen3:8b` 的真实 Acceptance Run：Readiness = ready，22/24 matched，Detection Recall = 1、FPR = 0、Policy Violation Accuracy = 0.95、Replay Pass Rate = 1；Gate 如实为 `failed`。两个差异是实际 Tool Authorization 为 `blocked` 而 expected 为 `completed`，未通过重试、fallback 或修改 Ground Truth 隐藏。

上述指标只说明当前固定合成 Case 的回归质量，不能外推为所有行业、所有 Prompt 或生产环境的总体准确率。

## 数据与安全声明

- 所有角色、文档、客户和攻击 Case 为仓库合成数据；
- 不扫描任意外部 Endpoint，不发送真实邮件，不访问真实 CRM；
- DeepSeek 密钥仅从后端 `DEEPSEEK_API_KEY` 读取；本地 Ollama 路径不读取该密钥。二者均不把密钥放入浏览器、仓库或报告；
- SQLite 只保存本地合成靶场的 Acceptance Run/Scan/Attempt/Trace/Finding/Replay 和配置快照；报告下载只格式化既有结果，不增加模型调用。
- Tauri Desktop 的 Sidecar 仅监听 `127.0.0.1`；当前机 NSIS 安装、启动、Workspace seed、退出和卸载已验证，不代表干净目标机已复现。

## 已知局限与后续方向

比赛 MVP 仍只覆盖固定 Contract、合成资产、Mock Tools 和单机本地运行。当前 BGE Embedding 是主路径，TF-IDF 仅为显式对照；SQLite 已提供本地 History，但不是生产级数据库、多租户或云端服务。F-026 仍因缺少另一台无仓库、无 Python/Node 的干净 Windows 复核而保持 In Progress；F-027 首次启动模型发现、F-028 企业资料导入、F-029 安装/迁移/运维，以及 Docker build/up 均未完成。企业 IAM/Connector、生产向量库和更丰富合规规则仍是后续方向，不属于当前完成度声明。
