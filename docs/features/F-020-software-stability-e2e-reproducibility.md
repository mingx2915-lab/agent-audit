# F-020 软件稳定性、浏览器 E2E 与目标环境复现

- 状态：Done
- 所属里程碑：M4
- 负责人：主代理监督；Backend/Frontend/Test Luna Max 按互斥范围实现
- 相关决定：D-004、D-009、D-012、D-019、D-021、D-027、D-028

## 用户价值

把已经完成的 Contract→Scan→Trace/Finding→Replay 软件能力变成可重复交付的完整产品：评审人员能从真实浏览器客户端完成关键流程，开发者能在声明的目标环境安装、启动、重启和复验，而不是只相信后端测试、静态页面或历史演示材料。

## 范围

- 增加至少一条提交到仓库的真实浏览器 E2E，覆盖 Audit Setup→Start Scan→Live Audit Attempt/Trace/Finding→刷新/History restore→Findings & Replay→再次刷新恢复；
- E2E 启动真实 Vue/Vite 客户端与 FastAPI API，通过 Test-only 显式 Provider/Retriever 和临时 SQLite 保持确定性，不依赖 DeepSeek/Ollama，也不拦截核心 Scan/Replay 响应伪造结果；
- 为关键用户动作增加少量稳定、可读的可访问名称或 `data-testid`，不写静态源码字符串测试；
- 复核并修复会影响主链的 loading、后返回请求覆盖、可读错误、刷新恢复和重复点击问题；
- 验证本地 Windows 目标环境的 Python/Node 安装、全量自动测试、生产构建、API/Web 启动与端口关闭；
- 在干净的本地临时副本中执行依赖安装与构建/测试，证明说明文档不是依赖当前工作区缓存；
- 更新根/前后端 README、软件验收记录和防漂移文档，形成 v1.0 软件完成结论与仍未验证边界。

## 非目标

- 不新增攻击类别、Security Contract 字段、Ground Truth Case、指标、模型 Provider、企业 Connector 或业务页面；
- 不为了 E2E 添加生产环境“测试模式”API、前端假数据、浏览器本地历史或 expected→actual 捷径；
- 不把截图、DOM 文案或网络 Mock 当作后端 Scan/Trace/Finding/Replay 已执行的证据；
- 不修补本地模型偶发 Tool 选择，不增加 Prompt 特判、自动 fallback、重试矩阵或模型输出后处理；
- 不重写为 Electron/Tauri，不制作 `.exe` 安装器、PPT、视频、申报排版或宣传材料；
- 当前机器没有 Docker CLI 时，不声称 Compose 已 build/up 验收；只允许修正静态配置并准确记录未验证事实；
- 不以任意覆盖率、文档哈希、截图哈希或主观性能阈值作为完成硬门。

## 前后端与数据影响

- Web：只增加关键主链稳定选择器及 E2E 暴露出的最小状态/错误修复；保持三个互斥工作区，不重做视觉系统；
- API：原则上不新增业务路由；只修复 E2E 或重启验收证明的真实稳定性问题，运行就绪可复用现有 `/api/runtime`；
- Contracts：原则上无新增字段；若 E2E 发现跨端契约缺口，必须先由主代理更新并记录原因；
- Tests：新增 Playwright 配置、真实浏览器用例和 Test-only API 启动支持；测试数据写系统临时目录，不写默认 Run History；
- Runtime：本地 Python 3.11 + Node 18 为本机已声明主路径；DeepSeek/Ollama 只用于另行授权的模型现场验证，不属于确定性 E2E。

## E2E 与复现契约

### 浏览器主链

```text
打开真实 Web 客户端
→ Audit Setup 显示 active Contract / Runtime / Contract-derived Plan
→ 选择 resource_owner_scope Plan 并 Start Scan
→ Live Audit 显示 completed、Attempt、Trace 与真实 Finding
→ 刷新页面，不自动发起 Scan/模型调用
→ 从 Recent Scan History 恢复相同 Scan
→ 进入 Findings & Replay，核对保存的 Contract/Plan/Profile/Runtime Snapshot
→ POST 历史 Replay，显示 Before failed / After passed 与完整 Trace
→ 再次刷新并从 History 恢复，已保存 Replay 仍存在
```

- 浏览器测试必须由真实点击触发 `POST /api/scans` 和 `POST /api/scans/{id}/replays`；
- API Test Double 只替代外部模型与语义检索波动，权限、Planner、Scan 状态机、Target、Trace、Checker、SQLite 和 Replay 均运行生产代码；
- E2E 记录关键 API 调用次数，刷新阶段不得出现新的 Scan/Replay POST；
- 页面不得出现未处理异常、console error 或失败的关键 API 请求；
- Test-only Server/Provider 放在 `tests/e2e`，不得被 production app 自动选择。

### 目标环境

- 固定验收环境事实：Windows、Python 3.11、Node 18、npm；具体实际版本写入验证证据；
- 干净临时副本至少执行 Python editable 安装、`npm ci`、全量 pytest、compileall、pip check、typecheck、production build 和浏览器 E2E；
- 本地服务必须真实监听回环地址，浏览器通过 Vite `/api` 代理访问 API；验收后关闭进程并确认端口释放；
- 默认本地 BGE 至少完成一次无监听的真实检索/权限链；浏览器 E2E 使用显式 Test Double，不重复消耗模型；
- Docker CLI 若不可用，Compose 保持 `Not verified`；只有实际 `docker compose build/up` 成功后才能改为已验证。

## 实施任务

- [x] ~~主代理锁定浏览器主链、Test Double 边界、目标环境和未验证事实~~
- [x] ~~Backend Luna Max 复核 API 启动/重启/SQLite/错误边界，只修复实际稳定性缺陷~~
- [x] ~~Frontend Luna Max 增加关键可访问选择器并修复 E2E 暴露的工作区状态问题~~
- [x] ~~Test Luna Max 实现 Playwright 环境、Test-only API 和完整浏览器持久化主链~~
- [x] ~~主代理使用浏览器复核桌面与窄屏主链可理解性、关键 console/network 错误和刷新行为~~
- [x] ~~主代理执行当前工作区与干净临时副本的完整验收，并确认端口释放~~
- [x] ~~审查无生产测试模式、无真实外部动作、无密钥、无 expected 污染、无静默 fallback~~
- [x] ~~更新 README、架构、STATUS、FEATURES 和 v1.0 软件验收记录~~
- [x] ~~提交 F-020 Git；M4 软件开发完成前不制作材料~~

## 验收标准

- [x] ~~仓库包含并通过真实 Playwright 浏览器 E2E，主链覆盖 Setup→Scan→Live→刷新恢复→Finding→Replay→再次恢复；~~
- [x] ~~Scan、Trace、Finding、Snapshot 与 Replay 来自真实后端/SQLite 工件，浏览器测试没有 route fulfill 核心结果或前端静态假数据；~~
- [x] ~~刷新只执行 GET 恢复，重复点击受 loading 状态约束，晚返回请求不会覆盖当前 Scan/Replay；~~
- [x] ~~主链关键错误以用户可读信息呈现，页面无未处理异常和非预期关键 console/network error；~~
- [x] ~~桌面与窄屏下三个工作区可切换、主按钮可见、核心证据不被遮挡；~~
- [x] ~~当前工作区全量 pytest、compileall、pip check、typecheck、production build、E2E 和 diff check 通过；~~
- [x] ~~干净临时副本能依 README 安装并完成同一自动验收，不依赖未提交文件或默认 SQLite；~~
- [x] ~~API/Web 真实启动后关键只读接口和页面可访问，验收结束端口释放；~~
- [x] ~~RQ-01 至 RQ-06 均能映射到已运行证据，固定 24 Case 仍真实执行并保持可审阅结果；~~
- [x] ~~Docker、DeepSeek、Ollama 等未在本轮实际运行的路径保持明确未验证，不外推生产准确率、稳定性或性能。~~

## 验证证据

- 当前工作区：`.venv\Scripts\python.exe -m pytest -q` 为 `260 passed`；Python `compileall`、`pip check`、前端 `typecheck` / production `build`、`git diff --check` 均通过。
- 浏览器 E2E：`npm run test:e2e` 为 `3 passed`，零重试；成功链只产生 1 次 Scan POST 和 1 次 Replay POST，两次 reload 均未新增 POST；Provider 502 用例显示原始可读错误并恢复按钮状态。
- 主代理浏览器复核：桌面端读取到 12 条 Trace、2 个真实 Finding、四类 Snapshot 与 before failed / after passed；浏览器 warning/error 为 0。390×844 下三个工作区与 Start Scan 均可见，无页面横向溢出。
- 干净副本：从 Git 提交克隆后全新创建 Python venv、执行 editable install、`npm ci`、Playwright Chromium 检查，再通过 260 tests、compileall、pip check、typecheck、build 和 3 E2E；不依赖当前工作区缓存、未提交文件或默认 SQLite。
- Production smoke：真实 `agent_audit_api.main:app` 返回 `deepseek / deepseek-v4-flash` 与 `embedding / BAAI/bge-small-zh-v1.5 / 512 / 7 documents` 元数据，4 类 Contract-derived Plan 可读，Web 首页可达；未触发模型 completion，停止后 8000/5173 端口均释放。

## 实施记录

- F-020 是软件完成门，不是新一轮功能扩张。只有 E2E 或目标环境验收暴露的真实缺陷才允许改生产代码。
- 当前开发机未发现 Docker CLI；Compose 继续保留静态配置但不计入通过项。本机已识别 Python 3.11.9、Node 18.20.8、npm 10.8.2。
- 既有 Vite 生产构建有大 bundle 警告；除非浏览器验收证明它影响核心交互，本功能只如实记录，不为消除警告进行无证据拆包重构。
- Backend Luna 只读审计未发现需要修改的生产 API 稳定性缺陷；Frontend 只增加 18 个关键选择器、工作区精确 aria-label 和 Runtime 防重复刷新。E2E Test Double 位于 `tests/e2e`，生产 app 没有测试模式。
- Playwright 锁定 `1.55.1`，因为本机声明的 Node 18 不满足当时最新版 `1.62.1` 的 Node 20 要求；配置显式绕过本机 HTTP proxy 的 localhost 流量，不复用未知端口服务且不隐藏重试。
- 干净复现目录因执行安全策略拒绝递归删除而暂留在当时的系统 `%TEMP%` 目录（约 345.6 MiB）；其内容仅为本地 Git 副本与重新安装的依赖，不属于仓库或软件运行数据。
