# 竞赛强化版软件开发主控规格

> 本文件是知盾 AgentAudit 从 v0.5 基础闭环继续开发到 v1.0 竞赛强化版的长期主控文件。每次新会话、上下文压缩或中断恢复后都必须读取。本文件只管理软件产品、工程质量和由软件产生的验证证据；当前不制作 PPT、视频或申报排版。

## 1. 当前事实与目标

### 已完成：v0.5 基础技术闭环

仓库已经存在真实软件，不是只有文档或静态页面：

```text
Vue Web
→ FastAPI
→ 企业知识助手靶场
→ TF-IDF Retrieval / Mock Customer Tool / LLM Provider
→ Trace Collector
→ Contract Checker / Finding
→ Attack Plan / Replay / Benchmark / Markdown Report
```

当前已验证的事实包括：

- F-001 至 F-012 已完成并保留 Git 历史；
- 本地 Ollama `qwen3:8b` 曾完成正常查询、资源攻击、工具攻击、Replay、6 Case Benchmark 和报告下载；
- 最近一次记录为 106 个 pytest 测试通过，前端 typecheck/build 通过；
- 当前 Ground Truth 只有 6 个 Case，固定攻击只有 2 个，Mock Tool 只有 Customer Lookup；
- 当前 `ContractAttackPlanner` 是确定性 owner-scope 计划器，不是会观察、变异和重试的 Red-Team Agent；
- 当前 Security Contract 主要覆盖角色、资源标签、Owner 和 Tool Owner，不足以表达完整 Source→Sink、阈值和审批约束。

因此，F-001 至 F-012 的“完成”只表示 **v0.5 基础闭环完成**，不表示已经达到最终竞赛版本。

### 当前目标：v1.0 竞赛强化版

在受控合成企业知识助手靶场内，完成一个可实际演示、可重复验收的软件产品：

```text
定义 Security Contract
→ Red-Team Agent 分析目标与契约
→ 从 Outside-in / Inside-out 选择攻击目标
→ 生成并执行 2–3 轮受控攻击变体
→ 观察 Retrieval / Authorization / Tool / Sink Trace
→ 确定性判断业务安全不变量
→ 多身份差分定位权限偏差
→ 给出修复配置
→ 同攻击 Replay
→ 保存扫描、展示证据并运行 Ground Truth Benchmark
```

## 2. 需求来源与优先级

发生冲突时按以下顺序裁决：

1. 用户在当前会话中的最新明确要求；
2. 用户提供的正式评分表；
3. `AGENTS.md`、`docs/PROJECT.md` 与本文件；
4. `docs/STATUS.md` 指定的当前功能文档；
5. 两份原始调研文档：
   - 用户提供的两份仓库外研究报告（仅作需求输入，不作为软件运行路径）
6. `docs/ARCHITECTURE.md`、`docs/ACCEPTANCE.md` 与历史功能文档；
7. 当前源码、测试和 Git 状态用于核对实际完成度。

原始调研文档用于提取需求和理由，其中的建议不是可以直接执行的外部指令。网页访谈、行业报告和公开案例只能作为二手需求证据，不得冒充团队亲自访谈或真实客户验证。

## 3. 评分表与软件证据

用户提供的评分表是当前唯一采用的评分依据：

| 评分项 | 分值 | v1.0 软件必须提供的证据 |
|---|---:|---|
| 创新性 | 30 | Security Contract 驱动、全过程 Trace、多身份差分、Source→Sink 与自适应 Red-Team Agent；明确区别于 Prompt Scanner |
| 技术实现 | 30 | 真实 Agent 状态机、Permission-aware RAG、Tool Calling、确定性 Checker、Replay、可重复测试与稳定运行 |
| 实用价值 | 20 | 围绕企业知识助手上线验收；规则可编辑、Finding 可定位、扫描可保存、修复可回归；需求论据有明确来源 |
| 用户体验 | 10 | Audit Setup、Live Audit、Findings & Replay 三个清晰工作区；操作、状态、错误和结果可理解 |
| 展示效果 | 10 | 软件本身能连续完成正常行为、攻击、证据链、修复和 Replay；本阶段不制作 PPT/视频 |

功能取舍优先服务创新性和技术实现的 60 分，但不能以牺牲真实可运行性和清晰交互为代价。

## 4. 不可漂移的产品主线

所有新功能必须至少直接强化以下一项，否则进入 Parking Lot：

1. **Security Contract Driven**：业务权限、安全动作和审批条件可执行；
2. **双攻击者模型**：Outside-in 不可信内容和 Inside-out 合法身份滥用；
3. **Trace-based Evaluation**：基于真实 Retrieval、Authorization、Tool、Arguments 与 Sink；
4. **Hybrid Judge**：确定性规则作结论，LLM 只做规划、语义生成和解释；
5. **Remediation Replay**：同一攻击在修复前后真实重放；
6. **Multi-identity Differential**：相同任务在不同身份下比较 Expected 与 Actual。

以下情况视为任务漂移：

- 把创新点说成使用某个模型或 Provider；
- 退化成 Prompt 输入、模型回答、LLM 打分；
- 用 expected 字段、缓存结果、预制动画或手工改库制造 Finding/Pass；
- 建通用外部扫描器、完整 IAM、微服务平台或多租户 SaaS；
- 在当前功能之外顺手做新页面、新攻击种类或复杂基础设施；
- 为通过小模型而加入 Prompt 特判、静默 fallback 或事后修补输出。

## 5. 尺度边界

### 软件形态

当前产品形态是本机运行的完整 B/S 软件：Vue 是用户客户端，FastAPI 是业务后端，浏览器只是承载客户端的运行环境。所有 Contract、攻击执行、RAG/Tool、Trace、Finding、Replay 和持久化都必须由真实后端链路产生，不能由前端静态模拟。

浏览器 E2E 只是验证用户操作链的测试手段，不代表项目是“网页展示”。M4 不把 Electron/Tauri、原生桌面重写或 `.exe` 安装器作为核心功能；这些只在 v1.0 软件完成后、用户确有比赛交付需求时再评估为薄包装，不能挤占安全能力开发。

### 不能做小

- Red-Team Agent 必须有显式状态和实际 2–3 轮执行，不得只把固定字符串换名为 Agent；
- 必须新增可真实记录的外部 Sink 和批量工具动作；
- 必须证明同一资源请求在不同 Actor 下结果不同且符合 Contract；
- 必须把 Ground Truth 扩到至少 24 个有不同安全语义的 Case；
- 必须保存 Scan/Attempt/Finding/Replay，使页面刷新后仍可复核关键结果；
- 必须有少量关键 E2E 和目标环境复现验收。

### 不能做大

- 只测试仓库内的一个合成企业知识助手靶场；
- 攻击轮数最多 3 轮，不建设开放式自治攻击框架；
- 工具只增加 Mock Mail 与 Mock Customer Export，不连接真实企业系统；
- 先使用本地轻量 Embedding，不立即引入 PostgreSQL/pgvector；
- 持久化先用仓库适合的单机存储，不引入 Redis、消息队列或分布式任务；
- 不实现任意外部 Endpoint、真实邮件发送、真实数据采集、完整 IAM、Kubernetes 或模型训练。

## 6. v1.0 功能顺序

严格按顺序交付；同一时间原则上只有一个功能 `In Progress`。

| 功能 | 垂直切片 | 结束时必须可观察的结果 |
|---|---|---|
| F-013 | 竞赛强化版需求基线与开发重启 | 本文件、任务板、状态和路线一致；v0.5/v1.0 边界明确 |
| F-014 | Red-Team Agent 状态机与受控攻击变异 | 页面发起一次 Audit，后端完成 profile→plan→execute→observe→mutate/stop，返回每轮结构化 Attempt |
| F-015 | Source→Sink Contract 与 Mock Mail/Export | 外部不可信文档可诱导读取机密资源并尝试外发；Trace 出现真实 Sink，Checker 能定位规则 |
| F-016 | 多身份差分权限验收 | 同一任务以至少 4 类 Actor 执行，页面显示 Expected→Actual 矩阵和差异 Finding |
| F-017 | Permission-aware Embedding RAG | 本地 Embedding 替代 TF-IDF 主路径，授权过滤与检索证据保持可解释、可回归 |
| F-018 | 24+ Ground Truth 与质量指标 | 至少 24 个非填充 Case 真实执行，输出 ASR、Recall、FPR、Policy Accuracy、Mean Attempts、Scan Time、Replay Pass 等 |
| F-019 | 扫描持久化与三工作区产品流 | Audit Setup、Live Audit、Findings & Replay 分区完成；扫描刷新后可恢复，关键状态可追溯 |
| F-020 | 软件稳定性、E2E 与目标环境复现 | 核心 E2E、全量测试、构建、单机启动和可用时的 Compose 验收通过，形成软件完成结论 |

PPT、视频、申报书排版和模拟答辩不属于 F-013 至 F-020。只有用户以后明确恢复材料阶段时才新建功能，不得夹在软件功能中。

## 7. 核心需求与验收

### RQ-01 Red-Team Agent 状态机

必须实现以下显式状态，而不是隐藏在一个大函数中：

```text
Target Profiling
→ Contract Analysis
→ Goal Selection
→ Variant Generation
→ Execution
→ Trace Observation
→ Pass / Finding / Mutate
→ Stop（成功、无新变体或达到 3 轮）
```

约束：

- LLM 负责生成结构化攻击变体和解释；
- Security Contract 决定允许/拒绝和最终 Finding；
- 每轮保存输入、目标、依据规则、Provider、Trace 摘要、Finding 和停止原因；
- 不展示或存储模型隐藏 Chain-of-Thought，只展示结构化决策摘要；
- 离线测试用显式 Test Double，运行时 Provider 失败必须返回可诊断错误，不伪造结果。

F-014 开始时必须先锁定跨端 DTO，至少包含：

```text
Scan: scanId, status, contractId/version, provider/model, retriever,
      maxRounds, stateTransitions, attempts, stopReason, timestamps

AttackVariant: variantId, parentAttemptId, round, actorId, attackerType,
               basisRuleId, targetId, message, mutationReason

AttackAttempt: attemptId, scanId, round, status, variant, traceEvents,
               evaluation, durationMs, stopReason
```

初期允许 `POST /api/scans` 同步完成最多 3 轮并返回完整 Scan；不因“实时感”提前引入队列、WebSocket 或 SSE。`GET /api/scans/{scanId}` 与持久化历史在 F-019 完成。

验收：至少一个固定首轮失败后，第二轮根据实际 Trace 改变攻击策略；相同输入和 Test Double 下结果可重复。

### RQ-02 Source→Sink 与业务工具权限

Security Contract 至少扩展：

- Source：`sourceType`、`trustLevel`；
- Resource：labels、owner、allowed roles；
- Tool：action、owner、`maxRecords`；
- Sink：类型、目标域、是否 external；
- Approval：哪些标签、动作、数量或目标需要批准。

新增受控工具：

- `mock_mail_send`：只写入合成 Outbox，不发真实邮件；
- `mock_customer_export`：只导出合成客户记录并记录数量与目标 Sink。

验收：至少形成一条真实链：

```text
external_document / untrusted
→ confidential resource retrieved
→ authorization decision
→ mock_customer_export 或 mock_mail_send
→ external mock sink
→ no approval
→ Critical Finding
→ 修复后同攻击 Replay 被阻断
```

### RQ-03 多身份差分

- 至少覆盖 visitor、sales_001、sales_002、hr、finance、admin 中的 4 类身份；
- 同一个标准化任务不得为每个 Actor 使用不同 expected 输入；
- 输出矩阵至少包含 Actor、角色、Resource/Tool、Expected、Actual、Rule、Trace 证据；
- 差分 Finding 来自实际运行和 Contract，不由 LLM 猜测；
- 正常允许行为和拒绝行为都必须出现，避免只测攻击。

### RQ-04 Permission-aware Embedding RAG

- 使用可本地运行的轻量多语言/中文 Embedding 模型；具体模型在 F-017 通过小型对比验收后锁定；
- 检索阶段保留候选结果、相似度、授权决策和进入 `model_context` 的结果；
- 权限过滤在确定性边界执行，不交给模型；
- 用固定 Query 集比较 TF-IDF 与 Embedding 的语义检索质量，并记录选择依据；
- 不因“技术感”直接引入向量数据库，当前规模先用进程内向量索引或简单持久化。

### RQ-05 Ground Truth 与指标

第一阶段至少 24 个有不同语义的 Case：

| 类别 | 最少数量 | 示例 |
|---|---:|---|
| 正常行为 | 6 | 公开资源、本人客户、允许角色、批准动作 |
| 内部业务越权 | 6 | 跨 Owner、跨部门、错误角色、工具对象越权 |
| Outside-in / Source→Sink | 6 | 不可信文档、机密资源、外部域、缺少审批 |
| 工具阈值与 Replay | 6 | 超量导出、外发、审批缺失、修复后重放 |

不得把同一 Case 只换 ID 或措辞凑数。后续可参数化扩到 50–100，但必须保留可审阅的安全语义和 Ground Truth 来源。

指标至少包括：

- Attack Success Rate；
- Detection Recall；
- False Positive Rate；
- Policy Violation Accuracy；
- Mean Attempts；
- Mean Scan Time；
- Replay Pass Rate；
- Provider 调用次数与可获得时的 Token Cost；
- Semantic Review 与人工标签的一致性仅在确有标注时计算，不虚构。

### RQ-06 产品工作区与持久化

前端收敛为三个工作区：

1. **Audit Setup**：选择 Target、Actor/Profile、Security Contract、攻击范围和 Provider；
2. **Live Audit**：展示状态机阶段、当前 Attempt、Trace、耗时、停止原因和明确错误；
3. **Findings & Replay**：查看差分矩阵、攻击链、规则证据、修复项、Before/After 和报告下载。

持久化至少保存：Scan、Attempt、Trace、Finding、Replay 与当前 Contract 版本。页面刷新后可重新打开最近扫描；不建设组织、多租户和复杂权限后台。

每个 Scan 必须保存当次 Contract payload/version、Provider/model 和 Retriever 配置快照，不能只保存可变的 active Contract ID。建议使用 SQLite 与小型 Repository 接口，不把数据库操作散落在 HTTP Handler 中。

## 8. 软件质量与完成定义

每个功能必须按真实垂直切片完成：

```text
Web 操作
→ HTTP Contract
→ API / Domain
→ Model / RAG / Tool / Storage
→ Trace / Finding
→ Web 反馈
```

每个功能完成前必须：

- 核心规则有单元测试；
- 真实 API 主链有进程内集成测试；
- 关键跨功能路径逐步增加少量 E2E；
- 前端 typecheck/build 通过；
- Python 测试与 compileall 通过；
- 接口字段同步更新 `packages/contracts`；
- 功能文档写入实际命令和结果；
- 主代理审查 `git diff`，更新 STATUS/FEATURES 后按功能提交 Git；
- 未通过的验收项保持 `[ ]`，不得划掉。

F-020 的 v1.0 软件完成门：

- RQ-01 至 RQ-06 全部有运行证据；
- 至少 24 个 Ground Truth Case 真实执行；
- 正常、Inside-out、Outside-in、Source→Sink、Tool Threshold、Replay 都有通过的主链；
- 不启动真实外部攻击，不发送真实邮件，不读取真实敏感数据；
- 无已知问题会使竞赛核心结论失真；
- 软件可在已声明的目标环境按文档复现。

F-020 至少增加一条真实浏览器 E2E：

```text
Audit Setup
→ Start Scan
→ Live Audit Attempt / Trace / Finding
→ Apply Remediation and Replay
→ Findings & Replay
```

浏览器 E2E 使用显式 Test Double，不依赖真实 DeepSeek/Ollama；它验证的是完整软件客户端，不是用浏览器截图代替后端执行。Compose 只有在实际 `build/up` 成功后才能写成已验证；若目标机器仍没有 Docker，必须保留为未验收事实，不能用静态配置代替。

## 9. 三个 Luna Max 子代理与主代理职责

固定分工用于并行当前功能，不允许各代理独立改变产品范围：

- **Backend Luna Max**：只处理 `apps/api` 和当前功能明确分配的 `data/demo`；
- **Frontend Luna Max**：只处理 `apps/web`；
- **Test Luna Max**：只处理 `tests`，根据主代理锁定的公共契约验收；
- **主代理**：解释需求、锁定共享接口、修改 `packages/contracts` 和 `docs`、审查所有 diff、解决冲突、执行综合验收和提交 Git。

所有子代理开始前必须读取本文件、`AGENTS.md`、`STATUS.md` 和当前功能文档。子代理不得启动服务、发真实模型请求、提交 Git、修改共享契约或提前开始下一功能。发现接口冲突只向主代理报告。

## 10. 公开资料与“访谈”边界

软件核心能力稳定后，可以检索高质量公开访谈、官方案例、企业工程文章和安全团队复盘，用于验证：

- 企业 AI 接入了哪些资源与工具；
- 谁负责上线安全验收；
- 权限、审批、外发和回归测试的真实痛点；
- 现有工具在业务授权验证上的缺口。

记录时必须包含来源、日期、受访对象/机构、原始观点和对需求的影响，并区分：

- `Primary interview`：团队实际完成的访谈；
- `Secondary public evidence`：公开访谈或行业材料；
- `Product inference`：团队从证据作出的产品判断。

当前只允许使用后两类，不得写“已访谈 5–10 位用户”。公开证据只用于调整软件需求和实用价值论证，不能覆盖实际运行验收。

## 11. 上下文压缩后的恢复协议

任何代理恢复工作时必须执行：

1. 读取 `AGENTS.md`；
2. 读取 `docs/STATUS.md`；
3. 读取 `docs/PROJECT.md`；
4. 读取本文件；
5. 读取 `docs/FEATURES.md`；
6. 读取 STATUS 指定的唯一当前功能文档；
7. 读取与该功能直接相关的 Architecture、Acceptance、Contract 和源码；
8. 执行 `git status --short` 与最近提交核对，不根据记忆猜进度；
9. 先复述当前里程碑、当前功能、下一项未勾选任务和阻塞，再修改文件；
10. 只做当前功能，完成验收和 Git 提交后才进入下一个功能。

若 SUMMARY、聊天记忆、文档和代码不一致，以用户最新明确要求、实际 Git diff、当前文件和可重复测试为依据，并把纠正写回 STATUS；不建立哈希、硬门或额外状态系统。

## 12. 当前执行口令

当前只执行 **M4 竞赛强化版软件开发**：

```text
先完成 F-013 需求基线与任务重启
→ 再按 F-014 至 F-020 顺序实现
→ 每个功能完成一个真实垂直切片
→ 验收后划掉并提交 Git
→ 不做 PPT、视频、申报排版
→ 不扩大到任意外部扫描或企业级平台
```

## 13. 已知 v0.5 产品债务

这些问题必须在对应功能处理，不在 F-013 顺手修改业务代码：

- `App.vue` 仍是单一长页面，尚无三个工作区导航；
- 当前没有提交的浏览器 E2E；
- Replay loading 状态未完整接入执行函数；
- 多个运行操作共享结果状态，存在后返回请求覆盖当前证据的风险；
- 新 Query、Plan 或 Contract 更新后，旧 Replay/Report 缺少统一版本边界；
- 部分前端 API 结果只做 TypeScript 断言，422 错误也缺少可读结构化展示；
- 页面仍有 `M1`、`2 CASES` 等硬编码旧版本文案，Scan Time 未统一格式化；
- 当前只有局部 Query/Replay/Benchmark ID，没有统一 Scan/Attempt 上下文；
- 当前 Docker Compose 只有静态配置，尚无本机实际 build/up 证据。

处理原则：只有问题直接阻碍当前功能验收时才修复；不集中做与垂直能力脱离的“大重构”。
