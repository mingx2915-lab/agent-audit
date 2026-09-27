# 关键决定记录

这里只记录会影响多个功能或长期维护的决定，不记录普通实现细节。

| 编号 | 决定 | 状态 | 原因 |
|---|---|---|---|
| D-001 | 产品收敛为企业 Agent 权限边界验收，而非通用 AI 红队平台 | Accepted | 保持比赛创新主线并避免与成熟扫描器同质化 |
| D-002 | 使用单仓库与模块化单体，目录为 `apps/web`、`apps/api`、`packages/contracts` | Accepted | 支持真实前后端协作，同时控制本科比赛工程复杂度 |
| D-003 | 按垂直切片交付，每个切片包含页面、API、业务和验收 | Accepted | 提前暴露集成问题并持续产生可演示版本 |
| D-004 | 违规结论以 Security Contract、资源属性、授权结果和 Trace 为主，LLM 不作唯一裁决 | Accepted | 结果需要可复现、可解释并降低 LLM Judge 误判影响 |
| D-005 | 使用 Markdown、可读编号和 Git 记录进度，不使用文档哈希或复杂硬门 | Accepted | 满足跨上下文恢复需求，同时避免管理机制侵入业务实现 |
| D-006 | 正式名称改为“知盾 AgentAudit——企业知识助手业务权限安全验收与自动化红队系统” | Accepted | 与新框架和比赛叙事统一，停止使用 AegisAC 等旧名称 |
| D-007 | 产品差异固定为 Security Contract、双攻击者、全过程 Trace 与修复 Replay | Accepted | 避免退化为 Prompt Scanner 或通用 AI 红队平台 |
| D-008 | MVP 技术基线采用 Vue 3/TypeScript、FastAPI/Python、PostgreSQL/pgvector、Docker Compose、pytest/Playwright | Accepted | 形成真实前后端产品，同时控制一个月开发规模 |
| D-009 | MVP 只运行受控企业知识助手靶场、合成数据和 Mock Tools，不支持任意外部目标 | Accepted | 保持授权测试与比赛演示边界，避免为外部扫描增加复杂硬门 |
| D-010 | 模型通过 Provider Adapter 接入，具体供应商与版本不作为长期主约束 | Accepted | 模型能力、价格和接口会变化，项目创新位于安全测试系统 |
| D-011 | 首个 Provider 使用 DeepSeek `deepseek-v4-flash`，通过 OpenAI-compatible API 调用并显式禁用 thinking | Accepted | 符合用户指定；保持 Provider Adapter 以便后续替换 |
| D-012 | 软件接近可运行闭环前不启动服务、不发真实模型请求；首次启动前必须告知用户 | Accepted | 避免未完成状态消耗 API、暴露密钥或形成错误演示结论 |
| D-013 | F-008 Planner 由 active Security Contract 与合成资产确定性生成 owner-scope 测试，不调用 LLM | Accepted | 让测试目标可追溯、可复现，避免第二套 Prompt 库与规则漂移；语义生成和大规模变异不属于比赛 MVP 当前范围 |
| D-014 | F-009 修复只把同一攻击计划从漏洞 Target Profile 切换到 secure Profile，并以两次真实 Trace 的 ContractChecker 结果判定 Replay | Accepted | Security Contract 本身表达正确业务规则，漏洞是 Target 未执行 denied；禁止通过改攻击、删 Case、缓存模型响应或预制 Pass 伪造修复闭环 |
| D-015 | F-010 Ground Truth 只登记期望并在真实执行后计算指标，不参与 Trace、Finding 或 Replay 判定 | Accepted | 防止把标准答案复制为实际结果；用少量可审阅 Case 同时验证检出、误报、分类和 Replay 质量 |
| D-016 | F-011 报告只格式化已完成 ReplayResult，不为报告重新执行模型或攻击，也不持久化 | Accepted | 保持报告与真实证据一致，避免模型波动、额外成本和隐藏状态；Markdown 可直接用于比赛复核 |
| D-017 | F-012 只整理可复现运行、五分钟演示和证据材料，现场启动前必须通过用户确认门 | Accepted | 比赛交付应证明现有主线而不是继续扩功能；先完成离线验收，再以一次受控现场走查验证真实链路 |
| D-018 | 首次现场验收显式选择本机 Ollama `qwen3:8b`，DeepSeek 保持默认且不做自动回退 | Accepted | 本地 Provider 可零付费验证真实全栈链路；显式选择避免运行结果来源不清，8B 能力不足时报告并升级模型而非加入特判 |
| D-019 | F-001 至 F-012 重新表述为 v0.5 基础闭环，并按正式评分表开启 M4 v1.0 软件强化 | Accepted | 当前实现是真实软件但 Red-Team Agent、Source→Sink、多身份差分和数据规模仍不足以代表最终竞赛版；保留历史同时避免虚报完成度 |
| D-020 | M4 只做软件与软件运行证据，PPT、视频和申报排版暂停；公开访谈只登记为二手证据 | Accepted | 用户要求当前继续开发软件，并允许以高质量公开访谈作为需求参考，但不能把公开材料冒充团队亲访 |
| D-021 | M4 保持本地 B/S 全栈软件，浏览器只作为客户端与 E2E 环境，不提前改为 Electron/Tauri 桌面壳 | Accepted | 当前 Vue+FastAPI 已是真实软件；原生打包不强化核心安全能力，待 v1.0 完成且确有交付需求时再评估薄包装 |
| D-022 | F-014 使用同步、最多三轮的显式 Red-Team Scan；LLM 只生成严格 JSON 消息变体，执行与 Finding 复用既有 Plan Executor/Contract Checker | Accepted | 在不引入队列和开放式攻击的前提下体现 AI 规划与 Trace 驱动变异，同时保持目标受控、结论确定性和可重复验收 |
| D-023 | F-015 将 Tool 业务授权与最终 Sink 授权分层记录，只使用纯内存 Mock Mail/Export 产生可验证副作用 | Accepted | 区分“工具可调用”、“参数符合业务阈值”与“数据可到该 Sink”，用真实 Trace 证明业务风险，同时避免连接真实邮件、CRM 或文件系统 |
| D-024 | F-016 多身份差分只运行两个服务端固定任务，Expected 从 active Contract 计算，Actual 只投影每个 Actor 的真实 Trace | Accepted | 保证同一 Message/Target 下的身份差异可复核，避免前端 expected、最终回答或 LLM 判断污染验收结论，也不扩大为通用 IAM 平台 |
| D-025 | F-017 主路径使用 FastEmbed `BAAI/bge-small-zh-v1.5` 的本地 512 维 ONNX Embedding，TF-IDF 只保留为显式对照与测试注入 | Accepted | 锁定的 6 条中文语义 Query 中 Embedding Top-1 6/6、MRR 1.0，TF-IDF Top-1 1/6、MRR 0.555556；模型仅 24M 参数/约 90 MB，适合本地 CPU 且无需向量数据库 |
| D-026 | F-018 固定为四类各 6 个、共 24 个不同业务语义的 Ground Truth；Runner 真实执行 Assistant/Plan/Replay，并把正确阻断、Attempts 和可获得的 Provider Token usage 纳入结果 | Accepted | 增加覆盖规模必须同时保持可审阅语义和 expected 独立性；未知 Token usage/价格返回 null，避免用重复 Case、估算 Token 或预制结果制造质量证据 |
| D-027 | F-019 使用单机 SQLite Repository 保存不可变 Scan/Contract/Plan/Profile/Runtime Snapshot，并在关联表只追加 Replay；前端收敛为 Setup、Live、Findings & Replay 三工作区 | Accepted | 页面刷新和进程重启后仍可追溯原始证据，同时避免内存 fallback、SQL 散落、队列、多租户和云基础设施扩张 |
| D-028 | F-020 使用真实 Playwright 浏览器驱动 Vue→FastAPI→生产 Scan/Trace/Checker/SQLite/Replay 主链，只有外部模型与检索波动由 tests/e2e 显式 Test Double 替代 | Accepted | 验证完整软件客户端且不消耗真实模型；禁止 route mock 核心结果、production 测试模式或静态页面冒充执行证据，并把本地 Windows 作为实际目标环境、Docker 保持未验证事实 |

新增决定格式：

```markdown
| D-xxx | 决定内容 | Proposed/Accepted/Superseded | 原因与影响 |
```
