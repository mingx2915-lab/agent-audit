# M5 软件产品化与评委体验改进计划

> 项目：知盾 AgentAudit——企业知识助手业务权限安全验收与自动化红队系统  
> 状态：Completed（F-021 至 F-025 已完成）
> 范围：只继续完善软件；暂不制作 PPT、演讲稿、宣传视频  
> 基线：F-001～F-020 已完成，现有 v1.0 能真实执行 Contract → Plan → Trace → Finding → Replay 主链

## 1. 结论

当前软件不是“功能不够”，而是“重点没有被看见”。页面把测试入口、Security Contract、完整 Trace、Finding、Replay、Differential、Retrieval Evaluation、Benchmark 和历史记录放在同一条很长的信息流里。熟悉项目的人能够理解，但首次打开的评委很难在短时间内回答三个问题：

1. 这个系统正在测试什么风险？
2. AI Agent 到底在哪一步做错了？
3. 修复后，同一个攻击是否真的被阻断？

下一阶段首先重做信息架构和核心攻击链可视化，而不是继续增加攻击数量或堆新功能。默认演示主线固定为：

**外部不可信文档诱导 Agent 读取机密资源并尝试发送到外部 Sink，系统依据 Security Contract 和真实 Trace 发现违规，再对同一攻击执行修复后 Replay。**

页面的第一屏必须让评委看到风险、证据、违反的规则和修复结果；原始 JSON 与完整 Trace 仍然保留，但降为可展开的审计证据。

## 2. 不变的项目主线

后续开发仍只服务于四条核心主张：

1. 用 Security Contract 描述身份、资源、敏感等级、工具动作、审批、阈值和 Sink 约束；
2. 同时覆盖 Outside-in 外部不可信内容与 Inside-out 内部合法用户滥用；
3. 根据 Retrieval、Authorization、Tool Call、Sink 的全过程 Trace 判断业务安全不变量；
4. 对同一攻击完成“发现 → 定位 → 修复配置 → Replay”的可验证闭环。

以下内容不得作为实际安全结论：模型自评、页面静态文案、Ground Truth 的 expected 字段、人工伪造的流程图。Finding 必须继续由 active Contract 与真实 Trace 的确定性检查产生。

## 3. 当前页面的主要问题

### 3.1 第一屏没有唯一主任务

固定 Case、Contract 计划、自由查询、Provider 状态、Contract JSON 等入口同时竞争注意力。用户看见很多可操作内容，却不知道应该先按哪里，也不知道系统最重要的价值是什么。

### 3.2 核心证据被长文本淹没

一次真实攻击可能产生十几个 Trace Event。当前信息更接近开发调试页面：字段完整，但 Actor、Source、敏感资源、Authorization、Tool/Sink 和 Finding 之间的因果关系不够直观。

### 3.3 Finding 出现得太晚

最重要的 Critical Finding、违反的 ruleId、证据序列和修复建议，需要经过较长滚动才能看见。对评委而言，这会造成“系统只是展示日志”的第一印象。

### 3.4 Before/After 没形成强对比

Replay 已经真实完成漏洞前后对照，但页面没有把“修复前实际外发”和“修复后在外发前阻断”组织成一个一眼可比较的结果。

### 3.5 高级能力与主线混在一起

Multi-identity Differential、Embedding Retrieval Evaluation、24 Case Benchmark、History 都有价值，但不应该在首次体验中与核心攻击闭环争夺视觉中心。

### 3.6 语言与层级不够面向非技术评委

英文技术名词、内部状态、细小字段和大块 JSON 过多。应保留必要术语，但先用业务语言解释“谁、读了什么、想发到哪里、为什么违规、修复是否有效”。

## 4. 锁定的评委浏览主线

软件默认采用四段式引导：

1. **测试目标**：我们要验证什么业务风险；
2. **实时执行**：Agent 当前经过了哪些关键节点；
3. **违规定位**：哪条 Contract 规则被违反，证据是什么；
4. **修复验证**：同一攻击在修复后是否被提前阻断。

建议的桌面端第一屏结构：

```text
┌──────────────────────────────────────────────────────────────────┐
│ 知盾 AgentAudit   Target / Provider / Contract / 当前状态         │
├──────────────────────────────────────────────────────────────────┤
│ AI 是否会把企业机密发送到外部？                       [开始验收] │
│ 合成靶场 · Source→Sink · 不会连接真实邮箱或企业数据                │
├──────────────────────────────────────────────────────────────────┤
│ Actor → 不可信 Source → 机密资源 → Authorization → Tool → Sink   │
│ 访客      外部文档          财务预算        DENIED       邮件    外部 │
│                                                │                  │
│                                      Critical Finding             │
├───────────────────────────────────┬──────────────────────────────┤
│ 结论：发现外发策略违规             │ 1 次攻击 / 18 Trace / 5.4s   │
│ 规则：sink-approval-required       │ 严重等级：Critical            │
│ 证据：[查看关键证据]               │ [完整 Trace] [高级信息]       │
├───────────────────────────────────┴──────────────────────────────┤
│ [应用修复并 Replay]                                             │
│ BEFORE：已执行外发 / Failed  | 规则变更 | AFTER：外发前阻断 / Passed │
└──────────────────────────────────────────────────────────────────┘
```

Contract、完整 Trace、Differential、Retrieval、Benchmark、History 放入次级页签或抽屉。它们不是删除，而是按“先结论、后证据、再高级能力”的顺序展示。

## 5. 后续功能顺序

### F-021 评委导向的信息架构与攻击链可视化（最高优先级）

**目标**：让第一次使用的人在 10 秒内知道测什么，在一次演示中看懂 Agent 如何违规，以及修复是否有效。

**实现范围**：

- 新增默认的“引导式验收”首页，只保留一个主操作：开始核心验收；
- 默认选择 Source→Sink Case，清楚标注合成靶场和 Mock 外部 Sink；
- 把真实 Trace 映射为 Actor → Source → Retrieval → Resource → Authorization → Tool → Sink 的攻击链；
- 关键节点按允许、拒绝、已执行、已阻断和 Finding 使用稳定视觉状态；
- 第一屏显示结论、严重等级、ruleId、关键证据、耗时和执行次数；
- Finding 出现后直接提供“应用修复并 Replay”主操作；
- Before/After 并排展示：目标、消息和 Actor 保持一致，只突出 Contract/Profile 变化与实际结果差异；
- 完整 Trace、原始 JSON、Contract 全文默认折叠；
- Differential、Retrieval、Benchmark、History 移到“高级验收”区域；
- 统一中文业务文案，必要的 Security Contract、Trace、Finding、Replay 保留英文术语。

**非目标**：

- 不改写后端安全判断；
- 不在前端复制权限规则；
- 不用静态图冒充真实执行；
- 不为了炫技引入大型图表库或无意义动画；
- 不新增攻击类别。

**验收标准**：

- 评委在不阅读项目文档时，10 秒内能指出测试目标、当前 Actor、敏感资源和风险动作；
- 运行后无需长距离滚动即可看到 Finding、违反规则和关键证据；
- Source→Sink 核心链在常见桌面视口内完整可见；
- Replay 的 Before/After 在同一区域内可比较；
- 18 条完整 Trace 默认收起，但任一关键节点都能展开到真实 Event details；
- 页面数据全部来自 API 的真实 DTO，刷新或切换结果不会使用写死结论；
- 390×844 移动视口仍可完成核心流程；
- 增补关键 E2E：开始验收 → 看到 Finding → Replay → 看到 After Passed；
- 保持现有后端测试、前端 typecheck/build 与 E2E 全部通过。

### F-022 模型兼容性与运行就绪验收

**目标**：避免演示时模型虽然能对话，却不能稳定完成严格 JSON 或 Tool Calling，导致错误看起来像系统漏洞。

**实现范围**：

- 明确区分 Target Provider 与 Attack Provider 的状态和用途；
- 增加只读就绪检查：连通性、严格 JSON 输出、Tool Calling、响应耗时；
- 用四类固定 Plan 形成兼容性矩阵，记录成功、失败及原始错误；
- 在首页用“已就绪 / 部分兼容 / 不可用”解释运行状态；
- 配置继续由本地环境提供，浏览器不接触 API Key。

**约束**：不做自动重试、静默 fallback、修补输出、宽松 JSON 猜测或为某个模型写特殊捷径。失败必须保留为真实兼容性证据。

### F-023 可视化 Security Contract 编辑器

**目标**：让非安全专业用户能理解并修改“谁能访问什么、能调用什么、何时需要审批”。

**实现范围**：

- 为角色、资源标签、owner-match、工具、maxRecords、approved、Sink 和 trust level 提供结构化表单；
- 保留高级 JSON 模式，二者使用同一 Contract DTO；
- 保存前显示规则变化和由现有 Planner 派生出的 Plan 变化；
- Replay 时突出实际修改的规则字段，不自动写入生产系统。

**约束**：只表达当前项目已有规则，不做通用策略 DSL，不扩展为 IAM/SSO 管理平台。

### F-024 最小 CLI / CI 安全门

**目标**：把竞赛演示能力转化为上线前可重复执行的工程验收。

**实现范围**：

- CLI 只运行仓库内受控合成靶场与固定 Benchmark；
- 输出 JSON 和 Markdown 摘要；
- 当确定性安全指标回退时返回非零退出码；
- 结果包含 Contract version、Provider、Case、Finding、Replay 和指标。

**约束**：不扫描任意 URL，不建设完整 CI 平台，不调用真实企业系统，不把模型主观评分作为阻断条件。

### F-025 统一 Acceptance Run 与历史对比

**目标**：把一次完整验收保存为可以复查、比较和交付的审计工件。

**实现范围**：

- 一个 Acceptance Run 关联 Runtime、Contract、Provider Readiness、Retrieval Evaluation、Differential、Benchmark、Scan、Finding 和 Replay；
- 支持查看本次结果与上一次结果的差异；
- 保存当时的 Contract、Plan、Profile 和 Runtime snapshot；
- 导出结构化证据包，供后续报告或申报材料使用。

**约束**：延续本地 SQLite 和不可变追加记录，不做多租户、云同步、复杂权限系统。

## 6. 开发次序与停检点

固定顺序：

1. F-021 信息架构与攻击链可视化；
2. 用户实际查看 F-021，确认评委能快速看懂；
3. F-022 模型兼容性与运行就绪验收；
4. F-023 可视化 Security Contract 编辑器；
5. F-024 最小 CLI / CI 安全门；
6. F-025 Acceptance Run 与历史对比。

F-021 完成后必须暂停继续扩展，由用户实际体验页面。若核心闭环仍需依赖讲解才能看懂，继续修正信息架构，不提前进入 F-022。

每个功能启动时，仍需单独创建 `docs/features/F-xxx-*.md`，更新 `docs/STATUS.md`，完成真实前后端垂直切片、测试和验收后才能划掉并提交 Git。

## 7. 与竞赛评分的对应关系

| 功能 | 主要评分项 | 提供的直接证据 |
|---|---|---|
| F-021 | 用户体验 10、展示效果 10 | 评委能直接看懂攻击链、Finding 和 Replay，不依赖口头补充 |
| F-022 | 技术实现 30、展示稳定性 | 证明本地/外部模型是否具备结构化输出和 Tool Calling 能力，失败可诊断 |
| F-023 | 实用价值 20、用户体验 10 | 非安全人员可以维护业务权限约束，并看到规则对测试计划的影响 |
| F-024 | 技术实现 30、实用价值 20 | 可作为上线前自动验收门，产生可重复的机器可读结果 |
| F-025 | 实用价值 20、展示效果 10 | 审计结果可保存、回看、比较和交付 |

创新性仍由现有核心能力支撑：Contract-driven、多身份差分、Outside-in/Inside-out 双视角、基于真实行为 Trace 的确定性 Finding，以及同一攻击的修复后 Replay。下一阶段不靠增加 Prompt 数量来制造创新感。

## 8. 明确不做

- 不增加大而全的 OWASP/Prompt 攻击库；
- 不支持任意外部 Endpoint 扫描；
- 不接真实邮箱、CRM、IAM、SSO 或生产数据；
- 不引入微服务、消息队列、Redis、Kubernetes、向量数据库迁移；
- 不做多租户平台、Runtime Firewall、通用 MCP 安全网关；
- 不训练自有模型，不把 LLM 作为最终裁决者；
- 不做 Electron/Tauri 桌面封装，除非用户后续单独授权且确有交付需要；
- 本阶段不做 PPT、演讲稿或演示视频。

## 9. 质量与防漂移规则

- 当前 v1.0 基线继续保留，任何新功能不得破坏已有 Contract → Trace → Finding → Replay 逻辑；
- 页面只呈现真实运行数据，不写死“通过”“发现漏洞”等结果；
- 权限和安全结论只在后端依据 Contract 与 Trace 计算；
- 核心规则补单元测试，API 主链补集成测试，评委核心路径补少量 E2E；
- 不为通过测试加入 fallback、重试、模型专用分支或输出后处理补丁；
- 不增加文档哈希、复杂硬门或重复状态系统；
- 一次只允许一个功能 In Progress，完成一个再划掉一个；
- 每次上下文压缩或新会话恢复，先按 `AGENTS.md` 顺序读取主控文档和当前功能文档；
- 当前 `docs/ROADMAP.md` 中 M4 状态若仍标为进行中，应在正式启动 M5 时与 `docs/STATUS.md` 一并校正，不在本提案阶段伪造进度。

## 10. 完成状态与后续边界

F-021 至 F-025 已按顺序完成。当前软件已经具备评委导向 Guided Audit、Provider Readiness、可视化 Contract 编辑与 Preview、固定 CLI/CI Gate，以及可持久化和对比的统一 Acceptance Run。

M5 完成不代表本地任意模型都能通过质量门。2026-08-27 的 Ollama `qwen3:8b` 真实 Acceptance Run 为 22/24 matched，Gate 如实失败；自动化受控 Provider 基线为 24/24。后续应先由用户检查软件体验与真实模型表现，未获得新的明确授权前不新增 F-026、不扩大攻击面，也不自动进入 PPT、演讲或视频制作。
