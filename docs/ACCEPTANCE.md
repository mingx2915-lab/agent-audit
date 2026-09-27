# 验收规则

验收的目的不是制造流程负担，而是保证“实现完成”有真实证据。

## 通用完成定义

一个功能只有同时满足以下条件才能在 `docs/FEATURES.md` 中勾选并划掉：

- 功能文档中的范围已完成；
- 所有必需验收条件通过；
- 相关自动测试或明确的人工验收已执行；
- 前后端实际行为与接口契约一致；
- 没有遗留会使核心结论失真的已知问题；
- 功能文档记录了验证命令、结果或可复现步骤；
- `docs/STATUS.md` 已更新。

## 测试分层

| 层级 | 重点 | 不要求 |
|---|---|---|
| 单元测试 | Security Contract、Trace 解析、确定性业务规则 | 简单 getter、纯数据声明 |
| 集成测试 | API、数据库、RAG/Tool/Model Adapter、Scan 与 Replay 状态 | 穷举所有外部失败组合 |
| E2E | 比赛关键用户链路 | 每个页面和视觉细节全自动化 |
| 人工验收 | 可理解性、演示节奏、修复复测 | 用主观判断替代核心规则测试 |

## v1.0 核心产品验收

以下是 M4 结束时必须证明的最终条件，不是 v0.5 当前已完成清单：

1. 企业知识助手能够按用户身份正常检索允许资源并执行允许工具；
2. 非本人客户访问等对象级内部越权能够被 Security Contract 检出；
3. 外部不可信文档引导 Agent 读取敏感资源并调用外部 Sink 时能够形成完整攻击链；
4. 工具调用技术上成功、但参数超过业务授权阈值时能够判定为业务安全违规；
5. 最终回答拒绝但 Trace 已读取或调用受限资源时仍能给出 Finding；
6. 结构化规则由 Contract Checker 确定性判断，LLM Judge 不覆盖确定性结论；
7. 风险详情能说明 Actor、Source、Resource、Authorization、Tool、Sink 和违反的 Contract Rule；
8. 对同一攻击切换到修复配置后，Replay 能证明该攻击被阻断；
9. 固定 Ground Truth Case 能区分正常行为与植入漏洞，不依赖手工改库制造结果；
10. 所有比赛数据为合成数据，Mock Mail 不发送真实邮件，系统不扫描任意外部目标。

## 验收证据

证据使用简单、可读、可复现的形式：

- 测试命令与摘要；
- API 请求/响应示例；
- 运行记录或 Trace JSON；
- 页面截图索引；
- 演示复现步骤。

评测指标根据完成的 Ground Truth Case 计算，至少保留 Detection Recall、False Positive Rate、Policy Violation Accuracy、Scan Time 与 Replay Pass Rate。Case 数量按真实完成度递增，不为满足一个预设数字伪造覆盖面。

不使用工件哈希作为完成条件，也不建立复杂的签名或证明链。

## v1.0 软件完成证据

M4 F-013 至 F-020 已完成，RQ-01 至 RQ-06 的实际证据索引见 `artifacts/acceptance/V1_SOFTWARE_ACCEPTANCE.md`。当前自动基线为 260 个 Python 单元/进程内集成测试与 3 个 Playwright 浏览器 E2E；该结论只覆盖仓库内合成靶场和声明的本地 Windows 环境，不代表任意生产 Agent、真实企业数据或外部目标的安全保证。

M5 F-021 未扩大安全结论范围，只重排真实证据的展示顺序。3 个 Playwright E2E 现覆盖默认 Source→Sink Guided Audit、Critical Finding、同 Plan Replay、刷新后历史恢复、390×844 无页面级横向溢出和 Provider 502 错误恢复；核心 Scan/Trace/Finding/Replay 仍运行生产代码。

M5 F-022 新增显式 Provider Readiness 证据，但不改变安全判定。自动基线为 300 个 Python 测试与 3 个 Playwright E2E；本地 Ollama `qwen3:8b` 的 Target connectivity、native Tool Calling、Attack connectivity、strict JSON 四项真实探针均通过，四类 active Plan 均 compatible。页面加载与刷新不自动调用 Provider，Readiness 失败不转换成 Finding，也不成为 Scan 硬门。

M5 F-023 将 JSON-only Contract 编辑替换为 Visual/Advanced 共用 Draft，并在保存前展示后端结构化 Field Diff 与真实 Planner Plan Impact。自动基线为 310 个 Python 测试与 5 个 Playwright E2E；覆盖 Preview 无副作用、Visual↔JSON、过期 Preview、Cancel 无 PUT、Save 单 PUT、Plan 刷新和 390×844。人工浏览器验收证明关闭 `resource_customer_owner` owner-match 会显示对应字段变化并将 Planner 输出从 4 个 Plan 减为 3 个，保存后页面与 active Contract/Plans 一致。

M5 F-024 将固定 24 Case Benchmark 变为可在本地或 CI 运行的确定性安全门，CLI 与 HTTP 复用同一真实 Runtime，并输出可重新验证的 JSON/Markdown。自动基线为 335 个 Python 测试与 5 个 Playwright E2E。本地 Ollama `qwen3:8b` 的真实运行为 22/24 matched、Recall 1、FPR 0、Policy Accuracy 0.95、Replay 1；两个差异都是实际执行状态由 expected `completed` 变为 Tool Authorization `blocked`，Finding 与 outcome 仍正确。CLI 因此如实返回 1，没有用重试、fallback 或改 Ground Truth 制造通过。

M5 F-025 将现有子验收统一成用户显式发起、完整成功后才追加保存的 Acceptance Run，并提供历史详情、与上一 Run 的确定性对比和 JSON/Markdown 证据下载。自动基线为 373 个 Python 测试与 7 个 Playwright E2E；覆盖首载不 POST、真实固定 Runner、不可变 SQLite、无半成品、无伪造 baseline、下载不增加 Provider 调用和 390×844。Ollama `qwen3:8b` 真实 Run `acceptance_76401aeb7592` 为 Readiness ready、22/24 matched、Recall 1、FPR 0、Policy Accuracy 0.95、Replay 1、39 次调用、21,870 tokens，Gate/verdict 如实 failed；没有重试、fallback、改 Ground Truth 或调用 DeepSeek。

## M6 F-026 当前验收边界

F-026 已在当前 Windows 环境实现 Tauri 独立窗口、PyInstaller FastAPI Sidecar、loopback 生命周期、portable Workspace 和 NSIS current-user 安装包。自动基线为 416 个 Python 测试与 7 个 Playwright E2E；未指定真实 `.exe` 时另有 1 个 Desktop artifact smoke 明确跳过，指定本次 release `.exe` 后 Desktop 配置与真实启动测试为 7/7 通过。`compileall`、`pip check`、根 `typecheck`、production build、`cargo check`、`rustfmt --check` 与 `git diff --check` 通过。

当前机器上的真实证据包括：Sidecar 从 packaged `demo-seed` 首次创建完整 Workspace、`/api/health` 返回 200、Desktop 启动后创建默认 manifest 且保持运行、退出后 Desktop/Sidecar 无进程残留，以及 NSIS 安装、启动、退出、卸载后安装目录和注册表项清理。该证据证明当前构建机路径可用，不等于干净目标机复现；由于当前机器没有可用 Windows Sandbox，也没有第二台无仓库、无 Python/Node 的 Windows 环境，F-026 仍为 In Progress。用户已将这项外部证据转为不阻塞代码演进的验收债务，F-027 与 F-028 已继续完成，但不得反向宣称 F-026 已在干净机验证。

## M6 F-027 与 F-028 软件证据

F-027 已完成固定 loopback Ollama 发现、手动单地址连接、候选 Provider Readiness、非 Secret 设置持久化与立即 Runtime 切换。本地 `qwen3:8b` 的四项真实探针均通过；发现与探针只在用户显式点击时运行，不静默下载、不 fallback、不调用 DeepSeek。

F-028 已完成原生文件/文件夹选择接口、UTF-8 `.txt`/`.md` 解析、显式权限元数据、Contract 授权 Preview、Workspace 快照追加和 Retriever 热替换。自动基线为 487 个 Python tests 与 10 个 Playwright E2E，另有 1 个只在未提供真实 Desktop artifact 时诚实 skip；compileall、pip check、根 typecheck、production build、rustfmt、离线 cargo check 与 diff check 通过。隔离 Workspace 的真实 API/Assistant 链证明：导入后允许角色的文档进入 `model_context`，拒绝角色保留 denied Authorization 且不进入 context；Preview/导入不调用模型，也不保存来源绝对路径。原生系统对话框的打包目标机操作与 Windows/Linux 安装工件继续归入 F-029 的平台验收。

## M6 F-029 当前验收边界

F-029 的共享代码和当前 Windows 构建已完成：完整 Workspace ZIP 同时保存 manifest、文档、Contract、Cases、Profiles、Ground Truth、SQLite History 与 exports；Preview 纯读取；Restore 以临时同级目录校验后 copy-as-new；桌面原生保存/选择只在 Rust 边界接触绝对路径，切换只保存相对子目录并重启自身 Sidecar。Windows 与 Linux 共用业务代码，平台 config 分别选择 NSIS 与 `.deb`/AppImage，Linux Sidecar/build 脚本已提供。

当前自动基线为 512 个 Python tests、2 个条件性 artifact skip 和 12 个 Playwright E2E。全量 E2E 的文件对话框是 test-only transport，但 ZIP 下载、Preview、Restore 和 Workspace API 均运行生产代码；覆盖 390×844 与取消无写入。compileall、pip check、根 typecheck、Web production build、rustfmt、offline cargo check、Linux shell syntax 和 diff check 通过。F-029 Windows Sidecar、release Desktop EXE 与 current-user NSIS 已重建；指定 release EXE 的启动 smoke 通过，默认 Workspace 成功初始化，退出后没有 Desktop/Sidecar 残留。

上述 F-029 验收当时仍不等于双平台完成：当时的开发机没有 Linux 目标环境，所以配置和 shell syntax 没有被写成 artifact 证据。后续 F-055 已在真实 Debian x86_64 VM 产出并启动 Sidecar、`.deb` 和 AppImage，完成 Windows→Linux→Windows Workspace Archive 往返及 XDG/Secret Service/health/进程清理的机器证据。强化后的非默认 active Workspace pointer 负控制尚待 Debian 真机重跑；另一台干净 Windows 的人工复核仍是独立外部验收边界。

## M6 F-031 当前验收边界

F-031 已在共享业务层完成两条简化连接路径：固定 loopback 的本机 Ollama 发现，以及用户填写单一企业地址后的 OpenAI-compatible `/v1/models` 与四项 Readiness。企业路径不让普通用户选 vLLM/TGI/NIM/Gateway 品牌，不扫局域网、不跟随跨 origin redirect、不自动重试或 fallback。

当前自动基线为 567 个 Python tests、2 个条件 artifact skip 和 13 个 Playwright E2E；compileall、pip check、根 typecheck、Web production build、Rust `cargo check`、`rustfmt --check` 与 diff check 纳入最终验收。Windows Sidecar、release Desktop 与 NSIS 已以当前代码重建；指定 release EXE 的 Desktop smoke 通过，退出后无 Desktop/Sidecar 残留进程。

本机 Ollama `qwen3:8b` 真实执行 Target connectivity、native Tool Calling、Attack connectivity 与 strict JSON 四项探针，结果为 READY、4/4 Plan compatible；本次不保存设置、不调用 DeepSeek。OpenAI-compatible 证据来自受控 Test Server/Transport，证明协议、Bearer、Tool Calling、strict JSON、错误与 Secret 不落盘边界，不写成已连接真实企业 Runtime。

Windows 密钥边界已编译为 Credential Manager 实现，Linux 使用 Secret Service/libsecret，两者都不提供明文文件 fallback。F-031 阶段当时没有 Linux x86_64 目标环境，因此未冒充 Linux 通过；后续 F-055 已在隔离 `dbus-run-session` 和一次性 GNOME Keyring collection 中真实执行 Secret Service store/read/delete/NoEntry，并运行 Linux Sidecar/Desktop 及 `.deb`/AppImage smoke。F-055 最终还以新构建的两种桌面工件真实打开 GTK 文件选择器、返回 WebView，并验证选择动作没有隐式 Preview/Commit/Scan；真实企业 Gateway 和凭据仍不在该证据范围内。

## M6 F-035 当前验收边界

F-035 已完成双入口首次接入向导、PDF/DOCX/TXT/MD 本机文本提取、批量权限与例外项、逐项诊断、纯 Preview、原子 Commit、共享 Retriever 热替换、真实 Contract-derived Plan 与 Guided Audit 接线。全量证据为 588 个 Python tests（2 个条件环境 skip）、19 个 Playwright E2E、4 个 Rust 原生解析测试，以及 compileall、typecheck、production build、cargo check、rustfmt 与 diff check 通过。最新冻结 Sidecar 在隔离 `AGENT_AUDIT_HOME` 首次创建 Workspace 且 `/api/health` 为 ready。

上述 Playwright 文件选择仍使用明确标注的 Test-only Transport，只证明自动化业务链和错误边界。另一次真实 Tauri 人工验收通过 Windows 系统文件夹选择器读取合成临时目录中的 PDF、DOCX、TXT、MD，Preview 为 4 ready，Commit 后成功 4、跳过 0、Retriever 7→11，并显示 4 条 Contract-derived Plan；该证据不依赖 Test-only Transport。F-035 继续保持 In Progress，待补未读源码用户五分钟任务与真实 Tauri 原生错误路径人工证据。

## M6 F-036 稳定性与可恢复性证据

F-036 新增两个必须显式运行、默认不拖慢普通开发流程的验收 Runner。Core Runner 使用明确标记的 `deterministic_test_provider` 与 `tfidf_test_retriever`，在每次新建的隔离 Workspace/SQLite 中执行现有 Contract-derived Source→Sink Plan、Scan、真实 Trace/Finding、同 Plan Replay 与 History read-back；最终工件为 100/100 次成功、100 个 Finding、100 个 Replay pass、History 100。该证据不代表真实 Ollama、DeepSeek、Embedding 或企业 Runtime 的模型稳定性。

Windows Desktop Runner 对显式指定的真实 Desktop artifact 完成 30/30 次 ready、health、正常退出、端口释放与精确进程身份清理，并完成 1/1 次 runner-owned 进程树 crash-recovery；最终孤儿进程与占用端口均为 0。Runner 不发现任意 artifact、不按进程名强杀、不触碰用户 Workspace。首尾 working set 相差 +125,251,584 bytes，但采样来自不同的新进程树，只作为 Observation，不构成泄漏或无泄漏结论。

自动回归基线为 622 个 Python tests（6 个环境/显式长测 skip）与 20 个 Playwright E2E；另有显式 opt-in 的 100 轮 workflow soak 和 1,000 条 Scan History/Acceptance Run 容量测量。Provider 故障保持单次调用、无 retry/fallback、无伪 Finding；DeepSeek Adapter 已补 `max_retries=0`。50 项混合导入、SQLite 锁/损坏恢复和主操作快速双击单请求均通过。F-036 完成时 Linux artifact 尚未执行；该项后来由 F-055 补齐。真实模型重复运行、DPI/键盘人工检查和 F-035 外部用户任务仍是独立外部验收债务。

## M6 F-037 修复参考边界

AgentAudit 的 remediation 是依据当前 Security Contract 和本次 Trace 生成的控制项参考；Replay 的 After 只是将同一 Plan 切换到内置 `secure` Profile 进行模拟复测。它不会写入 active Contract，不会连接或修改企业生产配置，也不构成企业系统根因结论。

Guided 主线在运行 Replay 之前即显示“仅供参考”，结果、历史、Acceptance Run、攻击链页面和 Markdown 导出均保留“不修改企业系统、不替代安全/业务/运维人员根因分析与变更审批”的说明。自动基线仍为 622 个 Python tests 与 20 个 Playwright E2E；Replay DTO、Finding 和确定性判定未改变。

## M6 F-057 工程证据闭环边界

F-057 已在本地完成 Windows/Linux 核心质量矩阵定义、供应链逐项 review register、三项目标环境任务单、性能观测扩展和旧阶段文档事实同步。当前 Windows 开发机回归为 880 个 Python tests 通过（10 skip）、36 个 Playwright E2E 通过、10 个 Rust library tests 通过；typecheck、production build、compileall、pip check、cargo check、源码 rustfmt 与 diff-check 通过。

F-056 release-4 曾有 18 个 RustSec Finding 和 22 个 Python unknown license。F-057 修正 Python scanner，使其读取目标解释器标准 distribution metadata，并让冻结 Sidecar 递归携带 Runtime dependency metadata/许可证文件；release-5 的 Python 42 个组件现为 39 permissive、2 weak-copyleft、1 metadata unknown。原 22 个包均在新 Sidecar 中确认 METADATA 和至少一份许可证文件；最后一项 `py_rust_stemmers` 的 canonical MIT LICENSE 与冻结包含性经人工核实。当前 register 精确对应 18 个 `in_progress` RustSec Finding 和 1 个 `fixed` license review，没有 accepted/allowlisted。

当前机器除 100 轮基线外，另以显式 `--long-soak` 完成 1,000 轮容量运行：1000/1000 workflow、Finding、Replay 通过，p50 27.44 ms、p95 30.97 ms、History 1000、Provider calls 6000，总时长约 28.04 秒。该运行只使用明确标记的 deterministic provider、TF-IDF retriever、7 个合成文档和临时 SQLite；tracemalloc 不是系统 working set，句柄未采集，且 28 秒高迭代运行不是小时级持续运行，不能据此声称真实模型、企业 Runtime、长期资源稳定性或 L4。

`.github/workflows/quality-matrix.yml` 已定义 Windows 2022 和 Ubuntu 24.04 的 Python、Web、E2E 与 Rust 质量门，但尚未取得 GitHub runner 首轮实际结果。干净 Windows 生命周期、Debian 非默认 active Workspace pointer 和真实企业 Gateway/凭据三项均在 `docs/TARGET_ENVIRONMENT_ACCEPTANCE.md` 中保持 `not_verified`；其中干净 Windows 按用户决定暂缓，真实 Gateway 无授权时保持非阻塞外部边界。这些外部证据不会被本地测试或 CI 定义自动替代。

## M6 F-058 本机运行与桌面交互证据

F-058 将固定 loopback Ollama 发现的连接失败、HTTP 异常和无效响应改为稳定中文诊断，不再向页面暴露 `URLError`、`OSError` 等底层异常类型。桌面连接页直接列出 Ollama 实际返回的已安装模型，不限定 `qwen3:8b`；用户仍须显式选择候选模型并通过 Target/Attack connectivity、native Tool Calling 和 strict JSON 四项 Readiness。发现保持单次固定 loopback 请求，不重试、不 fallback、不扫描局域网，也不自动启动 Ollama 或下载模型。

顶部“标准 / 大字”控件在向导自动定位和页面滚动后保持可见。Desktop 关闭事件不再在窗口线程同步等待 Windows 进程树清理：窗口先隐藏，后台只清理由本应用持有身份的 Sidecar 进程树，清理完成后退出。旧 release 单轮总退出耗时为 6,359 ms；新 `0.1.2` 工件为 1,297 ms，退出码 0、端口释放且孤儿进程为 0。当前自动回归为 880 个 Python tests 通过（10 skip）、37 个 Playwright E2E 通过和 11 个 Rust library tests 通过。

## M6 F-059 人话攻击链与分层技术证据

F-059 不改变 Scan、Trace、Finding、Security Contract 或 Replay 的执行与判定。页面只从当前最新 Attempt 的真实 Actor、TraceEvent 和 Finding 确定性投影中文业务摘要；`model_context`、`actor_response` 等内部 Sink 不被解释成业务数据已外流，Retrieval 只表述为候选资料，不声称已进入模型上下文。

宽屏六张攻击链节点卡保持等高。点击“查看证据”后，事实与事件在攻击链下方独立全宽面板显示，因此六张卡的高度不发生变化；系统原始事件和 JSON 仍需二次展开。Finding 编号位于图片外的独立高对比信息块；完整 Trace 默认显示中文事件标题与分块关键字段，原始英文 summary、事件类型和 details 保留在折叠区。

自动证据为 880 个 Python tests 通过（10 skip）、37 个 Playwright E2E 通过；F-059 定向覆盖宽屏卡片等高及展开前后高度不变、390×844 无横向溢出、中文默认层、Finding 编号位置、技术 Trace 字号与原始证据折叠。typecheck、production build、compileall、pip check 和 diff-check 通过；视觉证据见 `artifacts/acceptance/generated/f059-visual-review/attack-chain-panel.png`。当前源码的 Windows `0.1.2` 安装包已重建，SHA-256 为 `A48F40D07ED25FC271B1A783301DDA69A6D7FABA39EE073310327B28ED0A9D05`，指定新 Desktop EXE 的配置与启动 smoke 为 10 passed。

## M6 F-061 扫描证据视觉一致性与操作对齐

F-061 不改变 API、DTO、Provider、Security Contract、Scan、Attempt、Trace、Finding 或 Replay 的执行与判断。单个真实 Attack Plan 直接显示为只读确认卡，多项时才保留真实切换控件；没有为视觉完整性添加虚假计划。结果态继续显示装饰性数据流背景，语义节点与证据仍来自真实 Trace。

扫描状态转换改为浅色证据行；mutation reason 以“本轮攻击策略”正文块呈现，Finding/Passed 色彩只由真实 `attempt.status` 驱动。固定 Case 操作在 1440px 同行贴底，390px 退化为单列且无页面横向溢出。Guided、攻击链报告、验收页和 Desktop 启动失败页同步提升用户可见结论、说明和恢复动作；技术 ID、原始 JSON 与底层异常仍保留在 code 或折叠技术层。

自动证据为 F-061 定向 4/4、全量 45/45 Playwright E2E、887 个 Python tests 通过（10 skip）、typecheck、production build 和指定 release EXE 的 Desktop artifact smoke 10/10。当前 Windows `0.1.2` 安装包为 `artifacts/desktop/generated/知盾 AgentAudit_0.1.2_x64-setup.exe`，SHA-256 `9922BFEE1D5C1954BC25E243678165FBFDB7A02003345C3E6B5FF8B7522BBEF7`。该证据不替代另一台干净 Windows、Debian 非默认 pointer 或真实企业 Gateway 的外部验收。
