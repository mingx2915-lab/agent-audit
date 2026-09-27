# F-012 五分钟演示、申报材料与模拟答辩

- 状态：Complete
- 所属里程碑：M3
- 负责人：主代理监督；Backend/Frontend/Test Luna 做只读交付审计，主代理统一材料与 Git
- 相关决定：D-002、D-003、D-004、D-007、D-009、D-012、D-015、D-016、D-017、D-018

## 用户价值

把已经通过自动验收的 MVP 整理成一套能在新环境复现、五分钟内讲清创新主线、并经得起评委追问的比赛交付包，使所有对外主张都能回到真实页面、API、Trace、Finding、Replay 和 Ground Truth 证据。

## 范围

- 修订根 README 与前后端说明，给出真实依赖、安装、环境变量、验证和本地启动命令；
- 准备最小 Docker Compose 交付配置，复用现有 FastAPI/Vue 应用，不引入数据库、队列或额外服务；
- 在 `artifacts/acceptance/` 建立：
  - 五分钟演示 Runbook；
  - 申报摘要与技术证据映射；
  - 模拟答辩问题与基于仓库事实的回答；
  - 最终验收摘要、命令结果和现场检查清单；
- 演示主线固定为：正常使用 → Security Contract → Contract-driven Attack → Trace/Finding → 修复 Replay → 攻击链报告 → Ground Truth 指标；
- 所有材料明确 `SYNTHETIC / DEMO ONLY`、受控靶场和 Mock Tool 边界；
- 先完成全部不启动验证；首次启动后只做一轮关键路径现场验收和必要截图索引。
- 在用户明确授权后，以本机 Ollama `qwen3:8b` 作为零付费的首次现场 Provider；通过显式环境变量选择，不改变 DeepSeek 默认值；
- 本地模型先验收正常查询、资源型 Replay、报告和 Tool Calling；若 Tool Calling 不稳定，准确记录事实并请用户决定是否安装更强模型。

## 非目标

- 新攻击类型、新业务规则、新 API、新 Dashboard 区域或视觉重构；
- 任意外部 Endpoint 扫描、真实企业数据、真实邮件或真实客户系统；
- PostgreSQL/pgvector、Redis、消息队列、Kubernetes、完整 IAM 或多租户；
- 为答辩制造无法由仓库验证的性能、覆盖率、用户数量或生产部署主张；
- 自动生成 PPT、视频、PDF/DOCX 或适配尚未提供的比赛表单；
- 在用户确认前启动前后端、Docker 或发送真实 DeepSeek 请求。
- 自动探测后静默切换 Provider、Provider 失败后回退伪造回答，或为了让 8B 模型通过而加入 Prompt 特判。

## 前后端与数据影响

- Web：不改业务能力；仅允许为可复现部署增加最小容器/代理配置；
- API：不改业务能力；允许增加显式 Ollama Provider Adapter 和运行时 Provider 选择器；
- Contracts：无变化；
- Data/Model/Tool：无变化，继续使用合成 JSON、TF-IDF、Mock Customer Tool 与可替换 Provider Adapter。

## 交付契约

### 本地运行

- 后端从 `apps/api` 安装并以 `agent_audit_api.main:app` 启动；
- 前端从仓库根安装 workspace 依赖并以现有 Vite 代理访问 `/api`；
- `DEEPSEEK_API_KEY` 只从后端环境读取；任何文档、脚本、镜像和日志不得包含密钥；
- 静态/进程内测试不需要真实密钥；需要模型的页面操作只有在用户确认后执行。
- `AGENT_AUDIT_LLM_PROVIDER=ollama` 时只连接显式 `OLLAMA_BASE_URL` 与 `OLLAMA_MODEL`，不读取 DeepSeek 密钥；默认 Provider 仍为 `deepseek`；
- Ollama 请求使用官方 OpenAI-compatible Chat Completions、Tool Calling 与 `reasoning_effort=none`，不使用 `/no_think` 等 Prompt 技巧。

### 演示证据

每个演示步骤必须登记：操作、页面/API 结果、要讲的主张、对应真实证据、失败时允许采用的明确备份。备份只能是已保存的测试摘要、Trace JSON 或截图，不得用预制结果冒充当次在线执行。

### 申报与答辩

- 事实与解释分开：代码/测试可验证的是事实，比赛价值与适用范围属于解释；
- 指标只引用 Ground Truth Runner 的实际定义和当前固定 Case 数；
- 主动说明局限：受控合成靶场、Mock Tool、比赛 MVP、不是 Runtime Firewall，也不是任意目标扫描器。

## 实施任务

- [x] ~~主代理固定 F-012 交付边界与启动门~~
- [x] ~~Backend Luna 审计后端安装、入口、Provider 与容器化最小要求~~
- [x] ~~Frontend Luna 审计前端构建、代理、页面演示顺序与容器化最小要求~~
- [x] ~~Test Luna 审计最终验证命令、指标与证据主张~~
- [x] ~~主代理完成 README、最小 Compose 配置与验收材料~~
- [x] ~~执行全量测试、编译、typecheck、build 与配置静态检查~~
- [x] ~~提前告知用户并取得本地 Ollama 启动/模型请求确认~~
- [x] ~~实现并验证显式 Ollama Provider 与运行时选择器~~
- [x] ~~获准后执行现场关键路径、记录实际结果与必要截图索引~~
- [x] ~~完成模拟答辩复核、状态更新和最终提交~~

## 验收标准

- [x] ~~README 完整记录依赖、安装、验证与双应用启动步骤；当前 Python/Node 路径已实际启动，第二台全新机器未重复安装并已明确为不声明项；~~
- [x] ~~Compose 配置只包含现有 Web/API，未引入无需求基础设施，且密钥不写入镜像或仓库；~~
- [x] ~~五分钟 Runbook 在时间预算内覆盖完整主线和至少一个真实 Replay；~~
- [x] ~~申报摘要中的创新性、技术实现、实用价值、用户体验和展示效果均有仓库证据映射；~~
- [x] ~~模拟答辩准确解释 Contract、双攻击者、Trace、Hybrid Judge、Replay、Ground Truth 与局限；~~
- [x] ~~自动验收全部通过，指标与 Case 数和实际实现一致；~~
- [x] ~~所有材料明确合成数据/Mock Tool/受控目标，不包含密钥或无法验证的夸大主张；~~
- [x] ~~获准启动后，页面 → API → Target → Trace → Finding → Replay → Report 的现场主链路通过；~~
- [x] ~~未新增业务功能、外部扫描、复杂基础设施或偏离主线的交付物；~~
- [x] ~~本地 Ollama 选择不影响默认 DeepSeek 路径，不自动回退，thinking 明确关闭；~~
- [x] ~~最终状态文档、功能任务板与 Git 记录一致。~~

## 验证证据

- 测试命令：`.venv\Scripts\python.exe -m pytest -q`；`.venv\Scripts\python.exe -m pytest --collect-only -q`；`.venv\Scripts\python.exe -m compileall -q apps/api/src tests`；`.venv\Scripts\python.exe -c "from agent_audit_api.main import app; print(app.title)"`；`.venv\Scripts\python.exe -m pip check`；`npm run typecheck`；`npm run build`；`git diff --check`
- 结果：106 passed、106 collected；Python compileall、ASGI import 与 pip check 通过；contracts/web typecheck 与 production build 通过；diff check 通过。保留 1 个 TestClient 上游弃用提示和 Vite chunk size 提示。
- 人工步骤：本地 Ollama `qwen3:8b` 正常查询、资源 Replay、纯报告下载、真实 Tool Calling 与 6 Case Benchmark 全部通过；Benchmark 6/6 matched，Recall 1、FPR 0、Policy Accuracy 1、Replay Pass Rate 1，Scan Time 15,870.48 ms。浏览器 console error 为 0，四张截图登记在 `FINAL_ACCEPTANCE.md`。
- 启动状态：API/Web 已在验收后停止，端口 8000/5173 已释放；未发送 DeepSeek 请求

## 实施记录

- 2026-08-26：F-011 完成后开始 F-012。现有 103 个后端测试及前端 typecheck/build 已通过；本功能不再增加产品能力，只把已完成能力转化为可复现、可评分、可答辩的交付证据。
- 2026-08-26：未收到具体比赛表单或 PPT 模板，因此先产出可复用 Markdown 事实底稿，不臆造主办方字段；若后续提供模板，再做格式适配。
- 2026-08-26：完成根/前后端 README、双服务 Compose、API/Web Dockerfile 与 Nginx 反向代理；容器端口只绑定回环地址，`.dockerignore` 排除密钥和本地产物。当前机器无 Docker CLI，因此只记录静态审计结果，不声称容器已验收。
- 2026-08-26：完成五分钟 Runbook、申报事实底稿、18 问模拟答辩与最终验收清单。材料明确 6 个固定合成 Case 的指标不能外推生产准确率，也不声称持久化、真实 IAM/CRM 或向量数据库已实现。
- 2026-08-26：非启动验收全部通过。下一步必须先向用户说明将启动的两个本地服务、密钥注入方式和现场检查范围，得到确认后才能继续。
- 2026-08-26：用户授权先启动本机 Ollama 目标测试，已发现 `qwen3:8b`（Q4_K_M、40,960 context）声明支持 completion/tools/thinking，Ollama API `127.0.0.1:11434` 可访问且当前无模型加载。首次现场验收不调用 DeepSeek。
- 2026-08-26：增加显式 `ollama` Provider 与运行时选择器；默认仍为 `deepseek`，Ollama 使用 `reasoning_effort=none`，未知/失败 Provider 不自动回退。新增 3 个单元测试后全量为 106 tests。
- 2026-08-26：现场主链通过。正常公开查询 12-event Trace / passed；资源 Replay before failed（2 Findings）→ after passed（0 Findings）；报告已下载到本机 Downloads；工具计划真实产生 denied → tool_call → tool_result 与 Finding；6 Case Benchmark 6/6 matched。截图保存在 gitignored 的 `artifacts/acceptance/generated/`。
- 2026-08-26：完成最终回归并停止 API/Web。Docker CLI 不可用、真实 DeepSeek 和第二台全新机器安装未验证，均已明确记录且不冒充完成。
