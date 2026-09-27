# 模拟答辩问题与事实回答

## 1. 这和 Prompt 注入检测器有什么区别？

Prompt 注入只是可能的输入手段。AgentAudit 的判定对象是业务安全不变量：谁访问了什么资源、授权结果是什么、资源是否进入模型上下文、工具用什么参数调用、结果流向哪里。Finding 来自 Security Contract 与实际 Trace，不靠关键词分类。

## 2. 为什么需要 Security Contract，企业不是已经有 RBAC 吗？

项目不替代 RBAC。Security Contract 把已有角色、资源归属、标签和工具动作转成可执行验收条件，用来测试 Agent 是否正确传递并执行这些规则，尤其是对象级 owner-match 和 Tool Calling 组合边界。

## 3. Planner 会不会把答案写进测试，导致自证正确？

Planner 只从 active Contract 和合成资产派生 actor、target、basisRuleId 与执行消息。Ground Truth 的 expected 只在执行后对比，不进入 Trace、Finding 或 Replay 判定；测试还会篡改 expected，验证实际结果不变。

## 4. Finding 是 LLM 判的吗？

结构化 Finding 由 Contract Checker 确定性判定，例如 denied 资源随后进入 model_context，或 denied 工具随后出现 tool_call/tool_result。Semantic Review 默认可关闭，只能补充解释，不能删除或覆盖确定性 Finding。

## 5. 最终回答没有泄密，为什么仍可能失败？

因为敏感资源可能已经被检索并送入模型上下文，或工具已经执行。只看最终文本会漏掉中间过程风险。项目保留 Authorization 和 Sink/Tool Trace，用实际信息流判断。

## 6. Outside-in 与 Inside-out 分别是什么？

Outside-in 是不可信外部文档诱导 Agent 读取受限资源；Inside-out 是具有合法身份的内部用户诱导 Agent 越过本人客户等对象范围。两类 Case 都只针对仓库内合成靶场。

## 7. Replay 为什么可信？

Replay 保持同一个 plan、actor、target 和 message，只把 Target Profile 中对应 enforcement 从 false 切换为 true。BEFORE 与 AFTER 都真实重新经过 Target Agent 并生成 Trace；通过条件是 BEFORE failed 且 AFTER passed。

## 8. 为什么修复不是修改 Security Contract？

当前 Contract 表达的是正确业务规则，漏洞在 Target 收到 denied 后仍继续进入 context 或执行工具。修复是让 Target 执行既有 Contract，而不是放宽规则或删除测试。

## 9. 报告会不会再次调用模型总结，从而改变结论？

不会。Report Builder 的唯一输入是完成的 ReplayResult，只格式化实际 Evaluation、Finding、Trace 和 remediation；API 测试验证报告前后 Provider 调用数、active Contract 和 Plan 都不变。

## 10. 当前指标怎么计算？

固定 24 Case，正常行为、内部业务越权、Outside-in / Source→Sink、工具阈值与 Replay 四类各 6 个。Recall 关注预期违规是否被检出；FPR 关注正常 Case 是否误报；Policy Violation Accuracy 关注违规结果和类别是否匹配；Replay Pass Rate 关注修复回归。`expected` 只用于执行后的匹配，不参与 Trace、Finding 或 Replay 判定。

## 11. Recall=1、FPR=0 是否说明系统已经达到生产水平？

不能。它只说明当前固定合成 Ground Truth 的回归结果正确。Case 数量小、场景受控，不能外推到所有企业数据、模型和攻击。

## 12. 为什么 RAG 没用向量数据库？

当前主路径已经是本地 BGE Embedding（`BAAI/bge-small-zh-v1.5`）的 Permission-aware RAG；TF-IDF 只保留为显式对照和测试注入，不自动 fallback。固定 6 Query 对比中，BGE Top-1 为 6/6、MRR = 1.0，TF-IDF 为 1/6、MRR = 0.555556。比赛 MVP 规模先验证权限链和可解释证据，不宣称大规模向量数据库或生产知识库。

## 13. Mock Tool 算不算假功能？

外部系统是 Mock，但调用链不是静态动画：模型产生 Tool Call，后端解析参数、Contract 授权、执行合成 Customer Lookup/Customer Export 或 Mail Tool，并记录 tool_call、tool_result、Sink Trace。这样既能测试真实状态流，又不会发送真实邮件或访问真实客户数据。

## 14. Provider 不可用怎么办？

产品路径返回可读错误，不静默重试、fallback 或伪造结果。默认是 DeepSeek Adapter，也可显式选择本地 Ollama；自动测试用显式注入的 Test Double 验证确定性业务链。现场若 Provider 不可用，只能展示标注为预跑的实际证据，不能冒充实时调用。

## 15. 当前最主要的工程局限是什么？

产品只覆盖仓库内固定合成靶场和单机本地运行；SQLite 已保存 Acceptance Run/Scan/Attempt/Trace/Finding/Replay，但不是生产级多租户数据库。当前机的 Tauri Desktop、PyInstaller Sidecar 和 NSIS 安装已验证，尚缺另一台无仓库、无 Python/Node 的干净 Windows 复核；F-027/F-028/F-029 与 Docker build/up 也未完成。没有生产 IAM、真实 Connector 或真实数据访问。

## 16. 为什么没有做任意 Endpoint 扫描？

因为项目目标是有授权、可控、可解释的企业 Agent 上线验收。任意扫描既偏离 Security Contract 主线，也会引入授权与安全风险，因此被明确列为非目标。

## 17. 如何证明前后端不是静态演示？

Web 的三个工作区通过 `/api` 获取 Contract/Plan 并触发 Query、Attack、Replay、Acceptance Run 和 Report；FastAPI 集成测试走相同路由，断言实际 BGE Retriever、Tool、Trace、Finding 和 Provider 调用行为。CLI Gate 与 HTTP 复用同一 Runtime。桌面路径还会启动真实 PyInstaller Sidecar，并由当前机 NSIS 安装/启动/退出/卸载 smoke 证明链路；干净 Windows 复核仍未完成。

## 18. 下一步最值得做什么？

先完成 F-026 所缺的另一台无仓库、无 Python/Node 干净 Windows 安装复核；通过后才启动 F-027 首次启动向导与模型发现。F-028 企业资料导入、F-029 安装/迁移/运维和 Docker 仍未完成。更长期再用真实获授权的企业权限样例扩充 Contract/Ground Truth，并评估 IAM、生产向量库和 Connector。

## 19. 当前自动化质量证据是什么？

全量 Python 为 `416 passed, 1 skipped`；指定本次 release `.exe` 后 Desktop 配置与真实启动 smoke 为 `7 passed`，Playwright E2E 为 `7 passed`。`compileall`、`pip check`、前端 typecheck/build、`cargo check`、`rustfmt` 和 diff check 也通过。唯一 skip 是未指定真实 `.exe` 时不冒充 bundle smoke。

## 20. Ollama `qwen3:8b` 的真实 Acceptance 结果如何？

真实 Run 的 Readiness = ready，22/24 matched；Recall = 1、FPR = 0、Policy Violation Accuracy = 0.95、Replay Pass Rate = 1，但 Gate 如实为 `failed`。两个差异是模型实际触发 Tool Authorization `blocked`，而 expected 为 `completed`；没有重试、fallback、修改 Ground Truth 或改用 DeepSeek 隐藏差异。

## 21. SQLite History、Acceptance Run 和 CLI Gate 分别证明什么？

SQLite 保存完整 Run 及 Contract/Plan/Profile/Runtime 快照，刷新或重建应用后仍可回看并复核 Replay；Acceptance Run 只有完整执行后才追加历史；CLI Gate 固定运行仓库 24 Case，和 HTTP 使用同一 Runtime，并以退出码和 JSON/Markdown 工件如实报告是否通过。

## 22. 桌面安装是否已经证明可以在任何 Windows 电脑运行？

没有。Tauri Desktop、PyInstaller FastAPI Sidecar 和 NSIS current-user 包已在当前 Windows 机完成安装、启动、Workspace 首次 seed、退出和卸载 smoke；当前没有可用 Windows Sandbox 或第二台无仓库、无 Python/Node 的干净 Windows，因此 F-026 仍是 `In Progress`，不能扩大成“任意 Windows 已验证”。
