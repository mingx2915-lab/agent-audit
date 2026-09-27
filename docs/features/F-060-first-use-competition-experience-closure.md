# F-060 首次使用、比赛表达与视觉体验收口

- 状态：Completed
- 所属里程碑：M6 本地双平台产品化
- 负责人：主代理统筹；Backend / Frontend / Test 三名 Luna Max 分工实现
- 相关决定：`docs/PRODUCT_EXPERIENCE_COMPETITION_AUDIT.md`、`docs/features/F-035-enterprise-ai-onboarding.md`、`docs/features/F-045-typography-and-workspace-layout.md`、`docs/features/F-059-human-readable-audit-evidence.md`

## 用户价值

首次用户打开软件后应立即知道产品用途、当前任务和下一步；发生可恢复问题时能理解原因并直接处理；比赛评委无需先学习工程术语，也能看懂“测试什么风险、风险如何发生、证据在哪里、复测是否通过”。

## 范围

- 把首次入口从“向导下面继续堆完整页面”收敛为真实互斥路径：未选择路径时不展开全部业务模块；选择合成演示或自有助手后，只展示当前需要完成的步骤；
- 合成演示继续明确依赖用户确认的 Provider，不伪装为无需模型的新执行；修正文案中“立即查看”与实际前置条件的冲突；
- 将未配置、检查中、已就绪、需要处理和执行失败分开呈现，未配置不显示为系统错误；
- Provider、资料、Scan / Replay 的用户错误按“发生阶段、可确认原因、影响、恢复动作、技术详情”分层展示；前端依据明确的操作来源选择动作，不按错误文本做字符串猜测；
- API 在不改变响应形状的前提下，补齐本机发现、企业地址、认证、超时和 Provider 执行边界的稳定中文诊断；不 retry、不 fallback、不扫描局域网；
- 核心比赛路径采用“业务结论 → 中文过程证据 → 技术详情”三层信息；默认层减少 Provider、Plan、Actor、Source、Sink、Ground Truth 等工程词直出；
- 收口核心首页、连接、Guided Audit、Finding / Replay 和验收证据入口的字号、对比度、卡片、按钮和间距；沿用现有 Typography tokens，不以新增全局 zoom 或 `!important` 补丁代替迁移；
- 保留完整 Rule、Trace、Runtime、原始 JSON 和 operation ID 的可访问性；
- 增加首次入口、错误恢复、评委业务表达、标准/大字与宽窄屏的自动化和实际界面证据。

## 非目标

- 不修改 Security Contract、Retrieval、Authorization、Tool、Sink、Finding 或 Replay 判定；
- 不新增保存示例播放器、正式合成 Provider 或 Test-only Transport 到发布产品；
- 不把内置合成数据、自动化结果或历史截图冒充真实企业运行；
- 不重做所有高级实验工具，不删除专业字段或原始证据；
- 不新增 UI 框架、字体 CDN、插画、动效或联网资源；
- 不自动安装、下载、启动 Ollama 或模型，不自动 retry / fallback；
- 不扩展 IAM、SSO、任意外部扫描或企业 Connector。

## 前后端与数据影响

- Web：首次路径与当前步骤编排；可行动问题展示；核心比赛路径业务文案与视觉 token 迁移；技术详情分层；
- API：只调整既有错误诊断内容和明确的失败边界，不改变 endpoint 或 JSON shape；
- Contracts：无公共 DTO 变更；如实现中发现必须改变契约，由主代理先锁定再修改；
- Desktop：不改进程生命周期、文件选择器和 Credential Store；复用现有 Renderer；
- Data/Model/Tool：不改变持久化、模型调用、工具执行和审计语义。

## API 或交互契约

- 首载仍只读取现有状态，不自动 Discovery、Readiness、Scan、Replay、Import 或模型调用；
- 未选择首次路径时不渲染完整 Provider / Document / Guided 主体；选择路径只改变本地界面状态，不发业务请求；
- 合成演示路径在 Provider 未配置时只显示连接任务；Provider 已配置后才开放当前真实 Guided Audit；
- 自有助手路径按真实状态依次引导连接、资料、权限规则、Plan 和 Guided Audit；刷新后由真实保存状态恢复完成度；
- 任一问题只能从其明确操作来源生成，默认层显示用户可执行动作，HTTP 状态和原始 diagnostic 保留在技术详情；
- 用户主动点击“重新检测/重新执行”才发送对应请求；不得自动重试；
- 技术术语的中文投影只使用当前 DTO 中存在的事实，不让 LLM 生成页面结论。

## 实施任务

- [x] Backend：审查并补齐 Provider / Scan 相关稳定中文诊断，保持 API shape 与网络边界；
- [x] Frontend：实现互斥首次路径、当前步骤、可行动问题卡和核心比赛表达/视觉收口；
- [x] Test：增加首次路径无自动请求、未配置非错误、错误恢复、业务阅读层、宽窄屏与证据可访问回归；
- [x] 主代理：审查三路 diff、处理跨端一致性、修复组合问题并完成实际界面复核；
- [x] 运行定向与全量 Python、Playwright、typecheck/build、Desktop 相关验证；
- [x] 更新功能状态、任务板、STATUS 和实际验证证据。

## 验收标准

- [x] 未选择首次路径时只显示产品用途和两个互斥入口，不继续展开完整连接、资料、Guided Audit 和高级结果；
- [x] 选择合成演示后，未配置 Provider 被显示为待完成任务而非系统错误；页面不再承诺无需前置条件即可“立即查看真实结果”；
- [x] 选择自有助手后，页面根据真实状态给出唯一下一步，完成一步后自然进入下一步；
- [x] 首次路径选择本身不触发 Discovery、Readiness、Import、Scan、Replay 或模型请求；
- [x] Ollama 未启动、无模型、企业地址无效、认证失败、超时和 Provider 502 均显示发生阶段、可确认原因、影响、恢复动作与折叠技术详情；
- [x] 默认核心路径无需理解内部 ID 和英文 DTO 字段，也能回答“发生了什么、证据在哪、复测是否通过”；
- [x] Rule、Trace、Runtime、原始 JSON 与 operation ID 未删除且可展开核对；
- [x] 用户必须阅读的说明不再由 8–11px 或接近禁用态的浅灰色承载；Monospace 只用于技术值；
- [x] 1440×900、1920×1080、390×844、标准/大字和未配置/错误/Finding/Replay 状态无页面级横向溢出或主操作歧义；
- [x] 不改变现有 Scan、Finding、Replay、Provider、Import、Contract 与持久化业务结果；
- [x] 相关定向测试和现有全量质量门通过；无法完成的真实陌生用户证据保持未完成，不用自动化冒充。

## 验证证据

- `.venv\Scripts\python.exe -m pytest -q --tb=short`：`886 passed, 10 skipped`；skip 均为既有环境或显式条件，不以本轮改动隐藏失败；
- `npm run test:e2e -- --reporter=dot`：`41 passed`；其中 F-060 首次使用 4 项覆盖未选路径、路径选择无业务 POST、未配置 Provider、Ollama 可恢复问题卡、1440 / 1920 / 390 和标准/大字；
- `npm run typecheck`、`npm run build`、`.venv\Scripts\python.exe -m compileall -q apps/api/src`、`.venv\Scripts\python.exe -m pip check`、`git diff --check`：通过；build 继续保留既有 chunk size warning，不是本轮新增失败；
- 从当前源码重新冻结 Sidecar 并构建 Windows Desktop release/NSIS；指定新 `agent-audit-desktop.exe` 的真实启动、默认 Workspace 初始化与关闭 smoke 为 `10 passed`；统一交付目录中的 `0.1.2` 安装包 SHA-256 为 `CBE73D97E47B3CED65BAD63EE15821F07BBA0352363C7265624E2BAAB9B988E6`，与 Tauri bundle 原件一致；
- 受控 API 回归验证 Ollama 未启动/空模型、企业 401/超时/无效响应和 Provider 502；均保持单次调用、无 retry/fallback、无原始异常与 Secret 回显；
- 实际界面复核：1440×900 与 1920×1080 大字模式下，攻击链六节点展开前后高度分别保持 `303.39px` 与 `321.78px`；证据面板位于整行下方且宽度分别约 `1268px` 与 `1320.8px`，未再拉伸其他节点；
- 本轮仍未以真实企业 Gateway、真实 Ollama 现场网络或未读源码陌生用户完成验收；这些边界继续作为外部证据，不由 Test-only Provider 或自动化代替。

## 实施记录

- 2026-09-01：用户将“小字与排版一般”“首次启动出错且不知道怎么办”“表达偏技术、比赛评委看不懂”确认为同一轮产品收口问题，并授权主代理审查、三个 Luna Max 分工实现。
- 主代理锁定无公共 DTO 变更的初始边界；如后端需要结构化新字段，必须先停止跨端实现并由主代理修改 Contracts，避免各端自行发明协议。
- 三名 Luna Max 分别完成 API 诊断、Web 首次使用/比赛表达和测试回归；主代理复核后将旧测试从“要求回显原始英文异常”迁移为“验证中文可行动语义且禁止回显”，并把既有 E2E 显式接入真实首次路径，不绕过生产状态机。
- API 保持既有 endpoint、HTTP 状态、JSON shape 和单次请求语义；Web 保留 Rule、Trace、Runtime、原始 JSON、operation ID 与业务判定；未新增 retry、fallback、局域网扫描、图片或依赖。
