# 架构边界

当前采用单仓库、模块化单体结构，优先保证真实前后端协作、攻击执行过程可观察和比赛环境可复现。

## MVP 技术基线

| 层 | 基线 |
|---|---|
| Web | Vue 3 + TypeScript + Element Plus；当前不引入 ECharts |
| API | FastAPI + Python |
| Agent 编排 | 自定义显式 Red-Team Scan 状态机，最多 3 轮；不引入 LangGraph |
| 数据与 RAG | 合成 JSON + 本地 FastEmbed `BAAI/bge-small-zh-v1.5`；TF-IDF 仅用于显式对照，暂不引入向量数据库 |
| 测试 | pytest 单元/进程内集成 + Vue typecheck/build + Playwright 真实浏览器关键路径验收 |
| 部署 | Tauri v2 Windows Desktop + PyInstaller FastAPI Sidecar 为小企业默认交付路径；Python/Node 与浏览器入口保留用于开发；Docker Compose 已准备但尚未构建；不使用 Kubernetes |
| 模型 | 保留历史 DeepSeek 环境入口；桌面设置可显式选择本地 Ollama 或用户填写的单一 OpenAI-compatible Runtime，禁止扫网、自动重试与静默回退 |

## 顶层结构

```text
apps/web
  默认 Guided Audit 主线 + Security Contract、完整 Trace、Finding、Replay 与高级评测工作区

apps/api
  HTTP API、Red-Team 编排、企业靶场、Trace、Contract Checker 与报告逻辑

apps/desktop
  Tauri 独立窗口、Sidecar 生命周期、本机 API Base、系统文件对话框与 Windows bundle

packages/contracts
  API Schema、共享枚举和前后端数据契约

data/demo
  合成企业资源、角色和工具 Seed；桌面首次运行复制到用户 Workspace，之后不覆盖

tests
  单元、集成、E2E 和固定测试数据

artifacts/acceptance
  人可读的验收结果、截图索引和可复现说明
```

## 目标运行链路

```text
Web Dashboard
   ↓ HTTP
FastAPI Application
   ├─ Red-Team Orchestrator
   │    ├─ Target Profiler
   │    ├─ Attack Planner / Generator
   │    └─ Attack Executor
   ├─ Enterprise Knowledge Agent Target
   │    ├─ RAG Retriever
   │    └─ Mock Enterprise Tools
   ├─ Trace Collector
   ├─ Security Contract Checker
   ├─ Hybrid Judge
   ├─ Finding / Report Builder
   └─ Remediation Replay
          ↓
Synthetic JSON + Model Provider Adapter
```

## F-026 桌面与 Workspace 边界

```text
知盾 AgentAudit Desktop (Tauri/WebView)
   ├─ 启动并持有本次 Sidecar 进程树
   ├─ 动态选择本机端口，只连接 127.0.0.1
   └─ Vue Renderer 通过 Desktop 提供的 API Base 调用
          ↓
PyInstaller FastAPI Sidecar
   ├─ packaged demo-seed（只在首次创建时读取）
   └─ %LOCALAPPDATA%\AgentAudit\workspaces\default
          ├─ documents / contract / cases
          ├─ history / agent_audit.sqlite3
          └─ exports
```

- Application、AI Runtime 和 Audit Workspace 是三个边界：安装文件不保存企业 Workspace，Workspace manifest 只写相对目录，Ollama/DeepSeek 仍通过 Provider Adapter 显式配置；
- 桌面壳不复制 Security Contract、Planner 或 Finding 逻辑，只负责窗口、本机 Sidecar 和系统交互；
- Sidecar 生产入口必须从同一个 `AuditWorkspace` 装载 actors、documents、customers、Contract、Cases、Profiles、Ground Truth、History 与 Benchmark Runtime；
- 首次启动从安装包内只读 `demo-seed` 创建默认 Workspace；存在有效 manifest 时直接打开且不覆盖 Contract/History；非空但无有效 manifest 的目录直接报错；
- Web 开发模式继续使用同源 `/api`，Desktop 模式等待 Sidecar ready 后使用动态 loopback origin；失败不回退到开发服务器；
- Windows 关闭 Desktop 时按它创建的 PID 结束整个 PyInstaller 进程树，不操作外部 Ollama。

## F-028 企业资料导入边界

```text
Tauri explicit file/folder picker
  └─ relative name + UTF-8 text + diagnostic (no absolute path)
       ↓
DocumentImport Preview + active Security Contract authorization matrix
       ↓ explicit metadata confirmation
Workspace knowledge_documents.json atomic snapshot
       ↓
ReloadableRetriever stable slot → existing Assistant / Scan / Replay services
```

- 原生层只读取用户本次明确选择的文件；单次最多 50 项、单项最多 2 MiB，只真实支持 UTF-8 `.txt`/`.md`；
- Preview 不写 Workspace、不调用 Provider，也不自动修改 Contract；资源标签、Owner 和来源可信度由用户显式确认；
- API 只接收相对路径与文本，不接收本机绝对路径；Workspace catalog、History、日志和导出不保存选择来源绝对路径；
- 候选 Retriever 在发布前完成索引构建，文档目录通过同目录临时文件原子替换；成功后稳定身份 `ReloadableRetriever` 让既有主链立即看到新文档；
- 文件夹选择同样生成可移动快照，不建立持续同步、目录监视或外部路径依赖。

## F-029 Workspace 备份恢复与双平台边界

```text
active AuditWorkspace
  └─ WorkspaceArchiveService
       ├─ metadata.json
       └─ workspace/ complete portable snapshot
            ↓ Preview (read-only)
       temporary sibling → WorkspaceService.open → atomic rename
            ↓
       restored-<id> (non-active)
            ↓ explicit Desktop activate
       relative active pointer → owned Sidecar restart → Renderer reload
```

- 归档只包含相对 ZIP member；不包含选择来源路径、开发机路径、Secret、SQLite WAL/SHM 或安装目录；
- History 主库通过 SQLite online backup 生成一致快照，Contract、Cases、Profiles、Ground Truth、文档、History 与 exports 一起迁移；
- Preview 不落盘、不调用 Provider；Restore 始终创建新 Workspace，先在同级临时目录完成写入和普通 Workspace 校验，再原子移动，绝不覆盖 active Workspace；
- API 只返回 `workspaces/` 下单一相对子目录名；Rust 再校验 manifest 和 canonical parent，active pointer 也只保存相对目录；
- Windows 使用 `%LOCALAPPDATA%/AgentAudit`，Linux 的 Desktop 与 Python Core 统一使用 XDG data 下小写 `agent-audit`；
- `tauri.conf.json` 保持通用，Windows config 只选择 current-user NSIS，Linux config 只选择 `.deb`/AppImage；PyInstaller Sidecar 必须在各自目标平台构建，不进行假交叉编译；
- Linux 真实安装工件和关闭 smoke 只能在 Linux x86_64 环境形成证据；当前 Windows 的配置、cargo check 和静态测试不替代该证据。

## F-031 企业 AI Runtime 连接边界

```text
自动查找本机
  └─ fixed 127.0.0.1:11434 /api/tags
       ↓ 显式选模型
Provider Readiness → Confirm

连接企业地址
  └─ one explicit origin /v1/models
       └─ none | bearer (transient only)
            ↓ 模型枚举或手填 model ID
Provider Readiness → Confirm
```

- `ProviderConnectionSettings` 只包含 `kind/baseUrl/model/authMode`；`credentialConfigured` 是布尔状态，Secret 不属于跨端 DTO；
- 企业连接不向用户暴露 vLLM、TGI、NIM 或 Gateway 厂商选择；只验证 OpenAI-compatible `/v1/models` 与真实 Chat Completions 能力，不根据端口、Header 或错误文本猜厂商；
- Endpoint inspection 只访问用户明确填写的单一 origin，不跟随跨 origin redirect，不扫描局域网；列表失败可手填模型，但只有四项 Readiness 为 READY 才能确认；
- `OpenAICompatibleProvider` 与 `OllamaProvider` 都关闭 SDK 自动重试；Provider 失败不 fallback、不修补响应，Readiness 不转换为 Finding；
- Windows 使用 Credential Manager，Linux 使用 Secret Service/libsecret；Desktop 只将已存在的密钥注入它创建的 Sidecar 进程，新连接的一次性 Secret 只用于 inspection/readiness/confirm；
- 新 `kind/baseUrl/authMode` 不复用旧连接的 Sidecar 环境密钥；Provider JSON、Workspace、SQLite、History、Trace、日志、导出与错误不保存 Secret；
- 前端首载和刷新只 GET 已确认的非 Secret 状态，发现、检查、Readiness 与保存都由用户显式触发。

## 最小领域对象

- `SecurityContract`：角色、资源、归属、标签、工具、动作、阈值、审批条件和 SinkRule；
- `GroundTruthCase`：带 expected 的固定测试目标，expected 仅用于执行后匹配；
- `AttackCase` / `AttackPlan`：固定或由 Contract 派生的具体攻击目标；
- `RedTeamScan` / `AttackVariant` / `AttackAttempt`：一次受控多轮扫描、模型生成的受限消息变体和每轮真实执行证据；
- `TraceEvent`：检索、授权、工具调用、Sink 和模型响应事件；
- `Finding`：违反的 Contract Rule、证据链、风险和修复建议；
- `ReplayResult`：同一 Case 在修复配置上的回归结果。
- `DifferentialTask` / `DifferentialAuditResult`：服务端固定的同任务多身份验收定义，以及由 active Contract Expected 与每行真实 Trace Actual 组成的差分矩阵。

核心 Trace 至少表达：

```text
actor
source
input
retrievedResources
resourceLabels
authorizationResult
toolCalls / toolArguments
sink
modelOutput
contractViolations
timestamp
```

## 模块原则

- `web` 不复制后端权限判定；只展示后端返回的结构化结果。
- F-021 的默认 Guided Audit 只把 `AttackPlan`、`RedTeamScan`、真实 Trace/Finding 与 `ReplayResult` 投影为可读攻击链；Source/Authorization/External Sink 优先显示关键事件，完整 Event details 仍可展开。旧 Setup、Live、History、Differential、Retrieval 和 Benchmark 保留为高级工作区，不新增后端 API。
- F-022 的 Provider Readiness 是显式、非持久化兼容性证据：Target 与 Attack Provider 分角色执行 connectivity、native Tool Calling 和 strict JSON 四项单次探针，再由固定映射计算 Contract-derived Plan compatibility。探针失败不重试、不 fallback、不转为 Finding，也不阻止 Scan。
- F-023 的 Visual 与 Advanced JSON 编辑器共用一个 `SecurityContract` Draft；前端不计算权限或 Plan。`POST /api/security-contract/previews` 以规则 ID 生成稳定字段差异，并分别对 active/candidate Contract 运行既有 Planner 后比较完整 Plan DTO。Preview 纯计算且无副作用，只有用户确认保存才调用既有 PUT。
- F-024 的 HTTP Benchmark 与 CLI 共用 `BenchmarkRuntime`组装真实 Contract、Retriever、四类 Profile、Plan、Replay 和固定 24 Case。`agent-audit ci-gate` 不接受任意目标、Case、Contract 或阈值；它只从完成的 `BenchmarkResult` 计算五项固定 Gate，再将同一 `CIGateResult` 纯投影为 JSON/Markdown。Provider 失败或 Gate 回退不重试、不 fallback、不改写 Ground Truth。
- F-025 的 `AcceptanceRunner` 在开始时固定 Contract、Plan、Profile 与 Runtime snapshot，串行复用既有 Readiness、Retrieval、Differential、Benchmark/CI Gate、Scan 与 Replay 主链；verdict 只等于确定性 `ciGate.status`。完整 Run 才追加到与 F-019 共用 SQLite 文件的独立表，历史对比和 JSON/Markdown 导出只读取已保存 DTO，不重跑 Provider 或读取 active Contract。
- F-028 的原生选择器只负责显式文件读取；业务层以 `DocumentImportDraft` 同时接收相对来源和用户确认的元数据。Preview 由 active Contract 确定性计算角色授权，Commit 只写 active Workspace 并热替换共享 Retriever，不调用 LLM 或复制权限判断到 Web/Rust。
- `api` 保持模块化单体；Orchestrator、Target、Trace、Contract、Judge、Finding 和 Replay 可分模块，但暂不拆服务。
- `contracts` 只放跨端真正共享的契约，不放通用工具杂物。
- 企业靶场、RAG、Mock Tool 和数据全部在受控 Demo 环境；不实现任意外部目标扫描。
- Demo 企业资源使用合成数据，但访问动作必须经过后端并产生真实 Trace。
- 模型供应商通过小型 Adapter 隔离，不建设抽象度过高的多模型平台。
- Red-Team 生成器只能修改消息与结构化 mutation reason；Actor、Rule、Target 与 Profile 来自 Contract-derived Plan，执行复用 `AttackPlanExecutor`。
- F-014 的 `POST /api/scans` 同步返回完整 Scan；跨重启存取、Contract 快照与历史查询留给 F-019。
- F-015 将 Tool 可见性、Tool 业务授权和最终 Sink 授权作为三个独立事实；`mock_mail_send` 只写进程内 Outbox，`mock_customer_export` 只生成进程内 Artifact，两者均不访问真实网络或文件系统。
- F-016 的标准化差分任务不保存 Expected；Runner 每次从 active Contract 重算 Expected，并只从目标文档进入 `model_context` 或目标 Tool Result 的实际 Trace 投影 Actual。各 Actor 使用同一 Message/Target 且 Trace 隔离。
- F-017 的正常运行只创建一个共享 `EmbeddingRetriever`，Assistant、Attack、Scan、Replay、Benchmark 与 Differential 都复用该实例；Retrieval Trace 先记录语义候选与模型元数据，Security Contract 再独立决定 Candidate 是否进入 `model_context`。TF-IDF 只用于固定对比和显式测试注入，Embedding 出错不自动降级。
- F-018 的固定 Benchmark 由 24 个仓库内 Case 组成，四类各 6；Runner 复用真实 Assistant、Plan 与 Replay 链，expected 只在执行后匹配 outcome、Finding category 与 execution status。Provider usage 由同一 Adapter 包装器按实际调用计数；只有全部响应都提供 usage 才聚合 Token，成本在没有锁定价格表时保持未知。
- F-019 以 `AuditRunRepository` 隔离单机 SQLite：首次读写才建库，Scan 完整成功后写入不可变 Scan/Plan/Contract/Profile/Runtime Snapshot，Replay 以独立持久化 ID 只追加。历史读取与写入失败显式报错，不退回进程内存；HTTP Handler 不直接执行 SQL，浏览器刷新只读历史、不自动重跑模型。
- F-020 的浏览器 E2E 启动真实 Vue/Vite 与 FastAPI `create_app`，只在 `tests/e2e` 替换外部模型和 Retriever 波动；Planner、Target、Trace、Checker、SQLite 与 Replay 继续运行生产代码。E2E 单 worker、零重试、不复用未知服务，失败证据写入 Git 忽略的 acceptance generated 目录。
- Source→Sink 的 Finding 由 denied Sink Authorization 与后续同 destination 实际 Sink 关联而来；Tool 业务 Finding 还校验 approved 和 Tool 实际参数派生的 recordCount，不使用 expected 作判定。
- 决定性 Contract Rule 不调用 LLM；语义 Judge 只补充无法由结构化 Trace 直接判断的内容。
- Mock/缓存模式用于离线演示稳定性，不得伪装成真实在线模型执行结果。
- 运行时优先简单、可靠、可迁移，不引入 Redis、消息队列或微服务。

## 比赛后候选方向

- 经授权的真实企业 Contract 与 Ground Truth 扩充；
- Embedding/向量数据库与持久化 Scan/Trace 的需求边界；
- IAM/企业 Connector 的最小可信接入方式；
- Docker Compose 在比赛目标机上的实际构建与运行验证。

这些方向不属于当前 MVP 完成度；只有出现真实需求时才进入后续功能，不为完整性提前增加抽象。
