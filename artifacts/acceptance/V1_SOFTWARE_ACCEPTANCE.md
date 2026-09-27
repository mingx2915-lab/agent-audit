# 知盾 AgentAudit v1.0 软件验收记录

> 历史 M4 基线说明：本文件保留 F-013 至 F-020 的历史验收记录与原始数字，不随 M6 更新；当前 F-026 桌面、Sidecar、安装包和目标机边界见 `artifacts/acceptance/FINAL_ACCEPTANCE.md`。由于干净 Windows 尚未复核，F-026 仍为 `In Progress`，F-027 未启动。

> 记录日期：2026-08-27
> 边界：SYNTHETIC / DEMO ONLY；仅覆盖仓库内受控企业知识助手靶场。

## 结论

M4 F-013 至 F-020 的软件范围已完成。知盾 AgentAudit 已形成可运行的本地 B/S 全栈软件：Security Contract 驱动计划，Red-Team 状态机真实执行 RAG/Mock Tool，Contract Checker 从全过程 Trace 产生 Finding，同攻击完成修复 Replay，并可在 SQLite 历史中跨刷新/重启恢复。该结论不是对任意生产 Agent 或真实企业系统的安全保证。

## 需求证据映射

| 需求 | 已运行证据 |
|---|---|
| RQ-01 Red-Team Agent | F-014 最多三轮状态机与 Trace 驱动变异；浏览器从 Contract-derived Plan 发起真实 Scan |
| RQ-02 Source→Sink 与工具业务约束 | F-015 的 Mock Mail/Export、Sink/Tool Authorization、确定性 Finding 与 Replay；纯内存 Mock 无真实外发 |
| RQ-03 多身份差分 | F-016 固定同任务多 Actor 矩阵，Expected 来自 active Contract，Actual 只来自真实 Trace |
| RQ-04 Permission-aware Embedding RAG | F-017 本地 `BAAI/bge-small-zh-v1.5`，固定 6 Query Top-1 6/6、MRR 1.0，授权过滤与检索分离 |
| RQ-05 Ground Truth 与指标 | F-018 固定 24 个不同语义 Case，四类各 6；默认受控运行 24/24 matched，38 Provider calls，usage 380/190/570 |
| RQ-06 产品工作区与持久化 | F-019 SQLite 不可变 Snapshot/只追加 Replay；F-020 真实浏览器跨两次 reload 恢复同一 Scan 与 Replay |

## 本轮自动验收

- Python：`260 passed`，1 个 Starlette/httpx 既有弃用提示；
- Python compileall：通过；
- pip check：`No broken requirements found`；
- TypeScript/Vue typecheck：通过；
- Vite production build：通过，保留约 1.13 MB JS chunk 的体积提示；
- Playwright Chromium：`3 passed`，单 worker、零重试；
- `git diff --check`：通过；
- 密钥模式扫描：只发现 README 的 `<rotated-key>` 占位符，未发现真实 `sk-` 或 Bearer 凭据。

## 浏览器与启动证据

- 成功链：Audit Setup→resource owner Plan→1 Attempt/12 Trace/2 Finding→reload→History restore→四类 Snapshot→Replay before failed/after passed→再次 reload 后 Replay 仍存在；
- 请求边界：成功链只有 1 次 Scan POST 与 1 次 Replay POST；两次 reload 没有新增 POST；
- 稳定性：成功链无 page error、console error、API 非 2xx 或 request failure；
- 错误链：受控 Provider 502 时停留 Setup，显示 `synthetic E2E target provider unavailable`，按钮恢复可用；
- 窄屏：390×844 下三工作区和 Start Scan 可见，无横向溢出；
- Production smoke：默认 Runtime 为 DeepSeek `deepseek-v4-flash` Adapter + BGE Embedding 512 维 / 7 documents；4 类 Plan 与 Web 首页可读；未触发模型 completion；停止后 8000/5173 均释放。

## 干净环境复现

从当前 Git 提交克隆到 Windows 系统临时目录，重新创建 Python 3.11 venv，执行 editable install、`npm ci` 和 Playwright Chromium 检查后，260 tests、compileall、pip check、typecheck、production build 与最终 3 E2E 均通过。复现不依赖当前工作区未提交文件、默认 SQLite 或真实模型密钥。

实际环境：Python 3.11.9、Node 18.20.8、npm 10.8.2、Playwright 1.55.1。Playwright 版本依据 Node 18 兼容性锁定；当时 npm 最新版要求 Node 20。

## 明确保留的边界

- 当前开发机没有 Docker CLI，Compose 未实际 build/up，不计入已验证路径；
- 本轮未调用 DeepSeek 或 Ollama；历史 F-012–F-017 的本地 Ollama/BGE 证据独立保留；
- Vite 大 bundle 和 Starlette/httpx 弃用提示不影响本轮主链，但应在升级依赖或出现实际性能问题时再处理；
- 不扫描任意外部 Endpoint，不发送真实邮件，不读取真实企业敏感数据；
- 指标只属于固定合成靶场，不能外推生产准确率、攻击覆盖率、性能或商业效果。
