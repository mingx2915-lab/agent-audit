# F-036 桌面软件极端稳定性与可用性验收

- 状态：Done（当前 Windows artifact 与确定性链路验收完成；Linux、真实模型和 F-035 外部用户证据不在本功能完成结论内）
- 所属里程碑：M6 本地双平台产品化
- 负责人：主代理监督；Core、Desktop、Test 三名 Luna Max 分工实现
- 相关决定：`docs/SOFTWARE_ENGINEERING_QUALITY_ASSESSMENT.md`、F-019、F-025、F-026、F-029、F-035

## 用户价值

让小企业管理员和比赛评委看到：软件不只能够成功运行一次，还能在重复执行、模型故障、进程退出、文件边界和历史增长时保持明确失败、数据一致、可恢复且不遗留进程。

本功能不增加新的安全扫描能力。它建立可重复的质量证据，并只修复测试实际暴露的问题。

## 核心原则

1. 所有破坏性或高负载测试只使用隔离 `AGENT_AUDIT_HOME`、临时 Workspace 和合成数据；
2. 只结束本轮由测试启动且可精确识别的进程，不扫描或终止用户其他进程；
3. Test Provider 与本地真实模型结果分开记录，Test Double 不冒充真实模型稳定性；
4. 第一轮先测量性能和资源，不为了漂亮数字预设任意阈值；
5. 正确性、数据一致性、无孤儿进程可以作为确定性 Gate；时间和内存先作为 Observation；
6. 不引入自动重试、静默 fallback、云 Telemetry、微服务或新的扫描类型；
7. F-035 陌生用户任务仍需真实人员完成，本功能不让 AI 或自动化脚本冒充用户研究。

## 范围

### 1. 稳定性 Runner 与证据工件

- 新增显式运行的本地质量 Runner；
- 默认不随应用启动，不在普通 pytest 中自动执行长任务；
- 使用现有生产业务链和受控 Test Provider 连续执行 Guided Scan → Finding → Replay；
- 记录每轮状态、耗时、History 数量、错误、Python 内存观察值与最终一致性；
- 输出一个结构化 JSON 和一个人可读 Markdown；
- 输出只进入 `artifacts/acceptance/generated/` 或用户显式指定目录；
- 工件不包含 Credential、绝对企业来源路径或完整 Secret。

### 2. Desktop/Sidecar 生命周期

- 对真实 Desktop artifact 或显式 Sidecar artifact 执行隔离启停循环；
- 每轮等待真实 ready/health，不以进程存在代替 ready；
- 正常退出后验证本轮 Desktop/Sidecar 无残留、端口释放、Workspace 可重新打开；
- 支持一次显式 crash-recovery 场景，只终止测试自己启动的精确进程树；
- 无 artifact 时明确 skip/unsupported，不用源码静态检查冒充真实进程证据。

### 3. 故障恢复与数据一致性

- Provider connection refused、timeout、401/403/429/5xx、HTML/空响应、非法 JSON 与非法 Tool Call；
- Preview、candidate index、Workspace 写入、History/Acceptance 写入失败；
- SQLite 锁定、只读目录、损坏 manifest/JSON 的可读诊断；
- 失败后旧 catalog、Retriever、Contract 和 History 保持一致；
- Provider 故障不转换成 Finding，不重试，不跨 Provider fallback。

### 4. 容量与资源测量

- 50 项混合文件批量 Preview/Commit；
- 连续工作流与 History 增长；
- Desktop/API 启动时间、工作流耗时、内存或工作集观察值；
- 记录测试环境和数据规模；
- 不在第一轮用未验证阈值阻断发布，先建立基线并识别异常增长。

### 5. 可用性与误操作

- 快速双击主操作、运行中刷新/取消/切换工作区；
- 长模型名、长文件名、长错误文本；
- 1366×768、Windows 125%/150%/200% DPI 的真实或明确标注人工检查；
- 键盘焦点和主任务可达性；
- F-035 陌生用户五分钟任务继续单独记录，不用 Playwright 代替。

## 非目标

- 新攻击类型、任意网络扫描、企业 Connector、真实邮件、真实 CRM/ERP；
- 以压力测试为理由填满系统盘、破坏真实 Workspace 或强杀不相关进程；
- 建设云监控、完整 APM、SRE 平台或远程 Telemetry；
- 自动性能调优、隐藏失败、无限重试或修改 Ground Truth；
- 把一次本地运行写成所有企业机器上的性能保证；
- 在没有 Linux 主机时宣称 Linux artifact 已通过；
- 把 AI 模拟操作写成真实陌生用户访谈。

## 前后端与数据影响

- Web：只在测试暴露真实误操作问题时做最小修复；不新增大型 Dashboard；
- API：优先复用现有 `create_app`、Scan、Replay、History、Acceptance 与 Workspace 接口；只有 Runner 需要稳定公共边界时才增加小型模块；
- Desktop：增加显式、隔离、可清理的生命周期测试脚本；生产生命周期只修复真实竞态或残留；
- Contracts：没有跨端展示需求时不增加 DTO；
- Data/Model/Tool：只使用合成数据、Mock Tool 和显式 Test Provider；真实本地模型另行小样本运行；
- Artifacts：JSON/Markdown 记录环境、输入规模、结果、Observation 与未覆盖边界。

## 稳定性证据契约

最小 JSON 结构应表达：

```json
{
  "id": "stability_<id>",
  "startedAt": "...",
  "completedAt": "...",
  "status": "passed | failed",
  "environment": {
    "platform": "...",
    "python": "...",
    "artifact": null
  },
  "checks": [
    {
      "id": "workflow_soak",
      "status": "passed | failed | skipped",
      "iterations": 100,
      "completedIterations": 100,
      "failures": []
    }
  ],
  "observations": {
    "durationMs": 0,
    "memoryStartBytes": null,
    "memoryEndBytes": null,
    "historyCount": 0
  },
  "limitations": []
}
```

- `status=passed` 只表示本次声明的确定性 Gate 通过；
- `skipped` 必须说明环境条件，不能计入 passed；
- Observation 允许 `null`，不得伪造；
- 失败列表保留轮次和稳定错误类别，不保存 Secret；
- Markdown 只投影同一 JSON，不重新计算结论。

## 计划执行矩阵

| 检查 | 自动/人工 | 第一轮目标 | Gate/Observation |
|---|---|---:|---|
| deterministic Guided Scan → Finding → Replay | 自动 | 100 轮 | Gate |
| Desktop/Sidecar 正常启停 | 自动，需 artifact | 30 轮 | Gate |
| Desktop/Sidecar crash recovery | 自动，需 artifact | 1-3 场景 | Gate |
| Provider 故障矩阵 | 自动 | 固定受控响应 | Gate |
| 50 项混合文档 | 自动 | 1 批 + 重复导入 | Gate + 耗时 |
| History/Acceptance 增长 | 自动 | 100/1,000 条读取 | Gate + 耗时 |
| 内存/工作集 | 自动 | 前后采样 | Observation |
| DPI/键盘/误操作 | 自动 + 人工 | 声明的环境 | Gate/人工证据 |
| 陌生用户五分钟任务 | 人工 | 至少 1 人 | F-035 外部证据 |
| 真实本地模型重复运行 | 显式人工/自动 | 5-10 轮 | 单独报告 |

目标数字在未执行前不是已达到结果。若当前机器运行时间不合理，可在文档中记录实际规模和原因，不偷偷降低后仍宣称原目标通过。

## 实施任务

- [x] ~~主代理冻结范围、状态与证据契约~~
- [x] ~~Core Luna Max 实现稳定性 Runner、确定性 workflow soak 与 JSON/Markdown 工件~~；
- [x] ~~Desktop Luna Max 实现安全的 artifact 生命周期/资源测量脚本与真实进程证据~~；
- [x] ~~Test Luna Max 实现故障恢复、50 项容量、History 增长与误操作回归~~；
- [x] ~~主代理审查进程/路径安全、Test Double 边界和不伪造指标~~；
- [x] ~~执行定向、全量、长任务和真实 artifact 验收~~；
- [x] ~~只修复实际暴露的问题，并复跑相关证据~~；
- [x] ~~更新本功能、STATUS、FEATURES 与 ACCEPTANCE~~；

## 验收标准

- [x] ~~稳定性 Runner 显式运行并输出同源 JSON/Markdown~~；
- [x] ~~deterministic 核心工作流完成声明轮数，Finding/Replay/History 不串线~~；
- [x] ~~Provider 故障不重试、不 fallback、不生成伪 Finding~~；
- [x] ~~50 项混合导入保持逐项状态、原子 Commit 与可立即检索~~；
- [x] ~~History/Acceptance 增长后可读取，记录真实耗时而不伪造性能结论~~；
- [x] ~~指定真实 Desktop artifact 时完成声明启停轮数，退出后无本轮孤儿进程~~；
- [x] ~~crash-recovery 只影响隔离 Workspace，重启后 manifest/SQLite 可读~~；
- [x] ~~无 artifact、无 Linux 或无法采样时明确 skipped/limitation~~；
- [x] ~~普通 pytest/E2E 不因长任务默认变慢~~；
- [x] ~~现有 Python、Playwright 与未改动的 Rust 原生解析基线不回归~~；
- [x] ~~没有新扫描类型、云 Telemetry、静默 fallback 或破坏真实用户数据~~；
- [x] ~~未完成的 F-035 人工用户证据继续保持未完成~~。

## 验证证据

- 短测试：默认全量 `pytest -q` 为 622 passed、6 skipped、1 个既有 Starlette/httpx deprecation warning；F-036 最新定向为 34 passed、2 skipped；全量 Playwright 为 20 passed；`compileall`、`pip check`、根 typecheck/build 与 `git diff --check` 通过；
- 长任务：Core Runner 在隔离临时 Workspace 中完成 100/100 次真实 Scan → `external_sink_policy_violation` Finding → 同 Plan Replay → SQLite read-back；100 个 Finding、100 个 Replay pass、History 100，使用明确标记的 `deterministic_test_provider` 与 `tfidf_test_retriever`；同源工件位于 `artifacts/acceptance/generated/f036-core-final/`；
- 容量：显式长测写入并读取 1,000 条 Scan History 与 1,000 条 Acceptance Run；list/get 耗时只作为当前机 Observation，不设未经验证的性能门槛；
- Desktop artifact：对当前 Windows debug Desktop artifact 完成 30/30 次 ready/health/正常退出和 1/1 次精确进程树 crash-recovery；端口占用 0，最终孤儿进程 0；同源工件位于 `artifacts/acceptance/generated/f036-desktop-30-final/`；
- 资源观察：30 轮分别启动的新进程树首尾 working set 差为 +125,251,584 bytes；该采样不能证明单进程泄漏，因此不作为 Gate 或“无泄漏”结论；
- 真实本地模型：本功能未执行，确定性 Test Provider 结果不得外推为 Ollama、DeepSeek 或企业 Runtime 稳定性；
- 平台与人工可用性：F-036 完成时只执行 Windows artifact；后续 F-055 已补齐 Linux artifact。DPI/键盘人工复核、F-035 未读源码用户五分钟任务与真实原生错误路径仍是独立外部验收债务；本轮用户明确暂不执行陌生用户任务。

## 实施记录

- 2026-08-28：依据 `SOFTWARE_ENGINEERING_QUALITY_ASSESSMENT.md` 启动。F-035 软件实现转为 External Validation Pending，未完成的陌生用户和真实原生错误人工证据不勾选、不由自动化替代。
- 2026-08-28：Runner 的真实失败暴露三类验收工具问题：PowerShell 对中文仓库路径的输出编码、一次性窗口关闭等待不足、退出瞬间的进程采样过早。修复均限定在显式 Desktop Runner，并通过最终 30/30 + crash-recovery 复跑；没有据此推测性重写生产 Rust 生命周期。
- 2026-08-28：Provider retry 契约暴露 DeepSeek Adapter 未显式关闭 SDK retry，已最小修正为 `max_retries=0`，与 Ollama/OpenAI-compatible 的“不重试、不 fallback”边界一致。
