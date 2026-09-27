# F-019 扫描持久化与三工作区产品流

- 状态：Done
- 所属里程碑：M4
- 负责人：主代理监督；Backend/Frontend/Test Luna Max 按互斥范围实现
- 相关决定：D-016、D-019、D-021、D-022、D-027

## 用户价值

让企业 AI 开发、安全和评审人员不再依赖一次性页面状态：一次真实 Red-Team Scan 完成后，即使刷新页面或重启本地应用，也能重新打开当时的 Contract、Plan、Profile、Provider/Retriever、Attempt、Trace 和 Finding，并在同一历史记录下执行、保存和复核 Replay。界面收敛为“设置 → 运行 → 结果与回归”三个工作区，使非安全专业用户能顺着一条产品主线完成验收。

## 范围

- 使用 Python 标准库 SQLite，在单机保存成功完成的 Red-Team Scan 及其不可变执行快照；
- 保存完整 Scan，因此 Attempt、Trace 和 Finding 随 Scan 一并持久化；
- 保存当次完整 Security Contract、Attack Plan、Target Profile 和 Provider/Retriever 元数据快照，不只保存可变 ID；
- 为一个已保存 Scan 执行 Replay，使用该 Scan 保存的 Plan/Contract 快照与当前明确配置的 Provider/Retriever，结果追加到该 Scan 的 Replay 历史；
- 新增最近扫描列表、扫描详情和扫描内 Replay API；
- Web 收敛为 Audit Setup、Live Audit、Findings & Replay 三个互斥工作区；
- 刷新后从后端恢复最近历史，选择一条记录可恢复完整 Scan 证据与 Replay 历史。

## 非目标

- 不持久化任意普通 Assistant Query、Differential 或 Benchmark 运行；
- 不保存模型密钥、Authorization header、真实企业数据或浏览器本地伪造历史；
- 不做登录、组织、多租户、RBAC 后台、云数据库、Redis、队列、WebSocket、SSE 或后台任务；
- 不做删除、编辑、覆盖历史 Scan 或 Replay 的管理功能；
- 不把旧 Scan 按当前 active Contract 重新解释或改写 Finding；
- 不新增攻击类型、修复算法、报告格式、PPT、视频或桌面壳；
- 不为数据库故障静默退回内存存储。

## 前后端与数据影响

- Web：增加三工作区导航、最近 Scan 列表、历史详情恢复和扫描内 Replay；既有真实 API 面板按职责归入三个工作区，不复制后端状态或 Finding 计算；
- API：保留 `POST /api/scans` 响应为 `RedTeamScan`，成功后原子保存；新增历史列表、详情和扫描内 Replay 路由；
- Contracts：新增 TargetProfileSnapshot、AuditRuntimeSnapshot、AuditRunSummary、PersistedReplay、AuditRunDetail；
- Data：默认数据库为 `data/runtime/agent_audit.sqlite3`，由 `.gitignore` 的 `*.sqlite3` 排除；测试显式注入临时 SQLite Repository；
- Model/Tool：不改变 Provider、Retriever、Planner、Executor、Checker 和 Replay 算法；数据库只保存它们已经产生的结构化工件。

## API 或交互契约

### 持久化快照

```text
TargetProfileSnapshot:
  id / name
  enforceResourceAuthorization
  enforceToolAuthorization
  enforceSinkAuthorization

AuditRuntimeSnapshot:
  provider / model
  retrieverEngine / retrieverModel
  retrieverDimensions / indexedDocumentCount

PersistedReplay:
  id / createdAt
  replay: ReplayResult

AuditRunDetail:
  scan: RedTeamScan
  planSnapshot: AttackPlan
  contractSnapshot: SecurityContract
  targetProfileSnapshot: TargetProfileSnapshot
  runtimeSnapshot: AuditRuntimeSnapshot
  replays: PersistedReplay[]
```

- Scan、Plan、Contract、Profile 和 Runtime Snapshot 在首次保存后不可被 active Contract、前端显示或后续请求改写；
- Replay 只追加，不覆盖 Scan 或已有 Replay；
- `findingCount` 是所有 Attempt 的实际 `evaluation.findings` 数量之和，不从 expected 或名称推断；
- SQLite Repository 负责 schema、序列化和查询，HTTP Handler 不直接执行 SQL。

### API

```text
POST /api/scans
  request:  StartScanRequest
  response: RedTeamScan
  side effect: 仅在 Scan 完整成功后保存 AuditRunDetail

GET /api/scans?limit=20
  response: AuditRunSummary[]
  order: completedAt descending
  limit: 1..100，默认 20

GET /api/scans/{scanId}
  response: AuditRunDetail
  unknown: 404

GET /api/runtime
  response: AuditRuntimeSnapshot
  behavior: 只读取当前显式 Provider 与共享 Retriever 元数据，不触发模型或检索

POST /api/scans/{scanId}/replays
  request: {}（严格空对象，不接受额外字段）
  response: PersistedReplay
  behavior: 从历史 Detail 读取原 Plan/Contract Snapshot，真实执行 Replay，成功后追加保存
  unknown scan: 404
```

`AuditRunSummary` 固定包含：`scanId`、`planId`、`contractId`、`contractVersion`、`targetProfileId`、`status`、`stopReason`、`attemptCount`、`findingCount`、`replayCount`、`startedAt`、`completedAt`、`durationMs` 和 `runtimeSnapshot`。

Repository 公共接口固定为：

```text
AuditRunRepository.save(detail)
AuditRunRepository.list(limit=20)
AuditRunRepository.get(scan_id)
AuditRunRepository.append_replay(scan_id, persisted_replay)

SQLiteAuditRunRepository(path)
```

`create_app(..., history_repository=None)` 支持测试注入；未注入时使用 `AGENT_AUDIT_DB_PATH`，默认 `data/runtime/agent_audit.sqlite3`。Repository 构造不创建文件，首次历史读写时初始化 schema。

### 三工作区

1. **Audit Setup**：通过真实 API 展示 active Contract、当前 Provider/Retriever、Contract-derived Plan、目标 Profile 和最大轮数；从这里发起 Scan；
2. **Live Audit**：展示当前或已恢复 Scan 的状态流、Attempt、Trace、耗时、停止原因与最近历史；刷新后自动加载最近历史，但不自动重跑；
3. **Findings & Replay**：展示所选历史 Scan 的 Finding/Rule/Trace 证据、Contract/Plan/Profile/Runtime Snapshot、Replay 按钮与已保存 Before/After 历史；现有 Differential、Retrieval Evaluation、Benchmark 和报告入口可作为同工作区的质量证据区保留。

任一时刻只显示一个主工作区；运行成功后切到 Live Audit，选择历史记录恢复 Scan；执行 Replay 后停留在 Findings & Replay。前端不使用 `localStorage` 保存审计结论。

## 实施任务

- [x] ~~主代理锁定 SQLite、不可变快照、历史 API 和三工作区契约~~
- [x] ~~Backend Luna Max 实现 DTO、SQLite Repository、Scan 保存、历史查询与扫描内 Replay~~
- [x] ~~Frontend Luna Max 实现三工作区、历史恢复与持久化 Replay 交互~~
- [x] ~~Test Luna Max 验证跨 App 重启、快照不可变、真实工件保存、Replay 追加与 API 错误边界~~
- [x] ~~主代理审查无模型密钥/敏感头持久化、无 expected 污染、无内存 fallback 和无 SQL 散落~~
- [x] ~~运行 pytest、compileall、typecheck、build、pip check 与 diff check~~
- [x] ~~使用临时本地 SQLite 执行 Scan→重建 App→恢复→Replay→再次恢复的完整链路~~
- [x] ~~更新状态、架构、README、任务板并提交 Git~~

## 验收标准

- [x] ~~`POST /api/scans` 成功返回的完整 Scan 可从历史详情逐字段恢复，Attempt/Trace/Finding 不丢失；~~
- [x] ~~同一 SQLite 文件重建 `create_app` 后，`GET /api/scans` 和详情仍能读取历史，不依赖原进程内对象；~~
- [x] ~~历史 Detail 保存完整 Contract/Plan/Profile/Runtime Snapshot；active Contract 更新后历史内容和 Finding 不变；~~
- [x] ~~列表按完成时间倒序，`limit` 边界有效，summary counts 只来自持久化实际工件；~~
- [x] ~~历史 Scan 的 Replay 使用保存的 Plan/Contract，真实生成 Before/After Trace 与 Finding，追加后跨重启仍可恢复；~~
- [x] ~~重复 Replay 产生不同 PersistedReplay ID 并按创建顺序保存，不覆盖旧结果，也不改写真实 ReplayResult ID；~~
- [x] ~~未知 Scan 为 404，非法 limit/body 为 422，Repository 读写失败返回明确错误且不伪造内存结果；~~
- [x] ~~数据库不包含模型 API Key、Authorization header 或环境变量值；~~
- [x] ~~Web 三工作区互斥可见，能完成 Setup→Live→History restore→Findings→Replay；刷新不自动重新调用模型；~~
- [x] ~~现有 F-003–F-018 行为和测试不回归。~~

## 验证证据

- 自动验收：`.venv\Scripts\python.exe -m pytest -q` 为 `260 passed`；Python `compileall`、`pip check`、前端 `typecheck` / `build` 与 `git diff --check` 均通过。前端构建仅保留既有的大 bundle 警告。
- 定向证据：Repository/API/Scan/Source→Sink 共 47 项通过；默认运行数据库在全量测试前后时间戳未变化，旧测试均显式注入临时 Repository。
- 人工主链：使用临时 SQLite、默认本地 `BAAI/bge-small-zh-v1.5` 与受控 Provider Test Double 完成 Scan→重建 App→恢复→Replay→再次重建 App；Scan `completed`、1 Attempt、1 Finding，历史快照 Retriever 为 `embedding`，Replay 为 before `failed` / after `passed`，第二次重建恢复 1 条 Replay，外层 PersistedReplay ID 与内层 ReplayResult ID 相互独立。
- 边界：未启动监听服务，未调用 DeepSeek/Ollama，临时数据库随验收目录清理；开发早期产生的默认 `data/runtime/agent_audit.sqlite3` 已被 Git 忽略，不属于提交工件。

## 实施记录

- SQLite 只承担单机 Demo 的 Run History，不改变同步最多三轮的 Red-Team 状态机，也不引入后台执行基础设施。
- 历史 Scan 以保存时的结构化工件为事实；页面展示 active Contract 时必须与历史 Contract Snapshot 明确区分。
- `POST /api/scans` 只在完整 Scan 成功后保存；Repository 失败显式返回错误，不产生内存替代历史。Replay 使用保存的 Plan/Contract/Profile 快照并只追加到独立关联表。
