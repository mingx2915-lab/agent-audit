# F-027 首次启动与本地/内网模型连接

- 状态：Completed
- 所属里程碑：M6
- 负责人：主代理监督；Backend、Frontend/Desktop、Test Luna Max 按互斥范围实现
- 相关决定：`docs/M6_LOCAL_DUAL_PLATFORM_PRODUCT_PLAN.md`

## 用户价值

Windows 或 Linux 用户安装后不需要配置环境变量、打开浏览器或理解 Provider 参数；软件能够有限发现本机 Ollama，用户也能用简化表单连接明确的内网 Ollama，并在确认后立即用于当前 Target/Attack Runtime。

## 范围

- 固定检查本机 `127.0.0.1:11434` 的 Ollama `/api/tags`，列出真实已安装模型；
- 手动连接只支持用户明确填写的 Ollama 地址与模型，不扫描局域网；
- 对候选模型显式运行现有 Provider Readiness，结果不转为 Finding；
- 用户确认后保存不含 Secret 的 Provider 设置，并使当前应用 Runtime 使用该设置；
- 后续启动读取已确认配置，但只检查状态，不自动更换模型；
- 新增首次启动/未配置状态和简化连接 UI；高级审计能力保持可访问；
- Provider 设置、发现和 UI 契约保持 Windows/Linux 共用，不写平台绝对路径。

## 非目标

- 不下载、启动、停止、升级或删除 Ollama/模型；
- 不扫描硬盘模型目录、局域网或任意外部 Endpoint；
- 不实现 DeepSeek/OpenAI API Key 持久化；Secret Provider 留到系统 Credential Store 完成后；
- 不自动 fallback、重试到通过、修补输出或修改模型响应；
- 不实现 F-028 文档导入、F-029 Linux 安装包或 Workspace 备份；
- 不改动 Contract Checker、Finding 或 Replay 判定。

## 前后端与数据影响

- Web：新增首次启动 Provider Setup；自动发现、手动地址、模型选择、Readiness、确认和可读错误；
- API：新增 Provider 设置读取、Ollama 发现、候选 Readiness 和确认接口；确认后更新共享 Runtime；
- Contracts：新增 Provider 配置、发现候选、Setup 状态与请求/响应 DTO；
- Data/Model/Tool：非 Secret 配置保存在应用 config 目录，不进入 Workspace/SQLite/导出；使用现有 Ollama Adapter 和 Readiness，不增加 Tool 或 Finding 类别。

## API 或交互契约

公共 DTO 由 `packages/contracts` 锁定，最低表达：

- `ProviderConnectionSettings`：`kind=ollama`、规范化 `baseUrl`、`model`；
- `ProviderSetupState`：是否已确认、当前非 Secret 设置与当前 Runtime 摘要；
- `OllamaDiscoveryResult`：固定 endpoint、available/unavailable、真实模型列表和可读诊断；
- 候选检查请求：携带 Ollama 地址与模型，返回既有 `ProviderReadinessResult`；
- 确认请求：只接受已经由用户选择的 Ollama 地址与模型，保存后返回更新的 Setup State。

所有外部响应在 API 信任边界严格校验。发现失败直接显示诊断，不回退到默认模型；读取页面不得自动发起发现、Readiness 或模型调用。

## 实施任务

- [x] ~~主代理固定共享 DTO 和路由语义；~~
- [x] ~~Backend 实现跨平台非 Secret 设置存储、有限 Ollama 发现、候选 Readiness 和当前 Runtime 更新；~~
- [x] ~~Frontend/Desktop 实现首次启动与设置入口，不复制后端判定；~~
- [x] ~~Test 覆盖有限发现、持久化、即时生效、无自动调用、错误边界和既有主链回归；~~
- [x] ~~主代理完成集成审查、全量验证、实际本地 Ollama 显式验收和 Git 提交。~~

## 验收标准

- [x] 页面首次加载不调用 `/api/tags`、Readiness 或模型；
- [x] 用户点击自动发现时只访问固定 loopback Ollama，并展示真实模型列表；
- [x] 手动连接只访问用户提交的单一地址，不扫描其他主机；
- [x] 选择模型后可显式运行四项既有 Readiness，失败不保存、不 fallback、不生成 Finding；
- [x] 用户确认后非 Secret 设置持久化，当前 Runtime 立即使用该模型，重启后仍能读取；
- [x] 配置文件、Workspace、SQLite、日志和导出均不出现 API Key；
- [x] Windows/Linux 路径解析测试证明配置不依赖开发机绝对路径；
- [x] Guided Audit、Finding、Replay、Acceptance Run 和历史回归不退化；
- [x] Python tests、compileall、pip check、typecheck/build、关键 E2E 和 diff check 通过；
- [x] 本地 Ollama 真实验收只在主代理明确执行时运行，结果如实记录。

## 验证证据

- 测试命令：`.venv\Scripts\python.exe -m pytest -q`；`npx playwright test --reporter=line`；`npm run typecheck`；`npm run build`；`.venv\Scripts\python.exe -m compileall -q apps/api/src tests`；`.venv\Scripts\python.exe -m pip check`；`git diff --check`
- 结果：`461 passed, 1 skipped, 1 warning`；Playwright `8 passed`；compileall、pip check、contracts/web/desktop typecheck、production build 与 diff check 通过。唯一 skip 仍是未指定真实 Desktop `.exe` 时的诚实 artifact 条件项；Vite 仅保留既有大 chunk warning。
- 人工步骤：主代理使用进程内 TestClient 明确访问本机 `http://127.0.0.1:11434`，自动发现真实 `qwen3:8b`；候选 Readiness 的 Target connectivity、Target native Tool Calling、Attack connectivity、Attack strict JSON 四项均 passed，Target/Attack 均 ready，4/4 active Plan compatible。使用临时 AppPaths/History，不 PUT 真实用户配置，不调用 DeepSeek。

## 实施记录

- 2026-08-28：用户确认采用单一聚焦产品、Application/AI Runtime/Workspace 三分离和 Windows/Linux 双平台方向，并明确要求三个 Luna Max 开发。F-026 的干净 Windows 外部证据继续保留，但不再阻塞共享代码演进。
- 2026-08-28：Backend、Frontend/Desktop、Test 三个 Luna Max 完成互斥切片；主代理修正 discovery service-root、禁止 redirect、已配置后的 compact UX、Vue `runTestId` 与显式 Provider 注入隔离，并完成全量与本地 Ollama 真实验收。
