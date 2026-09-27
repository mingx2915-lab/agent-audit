# F-063 品牌视觉恢复与比赛可读性重构

- 状态：In Progress
- 所属里程碑：M6 本地双平台产品化
- 负责人：主代理（审查与共享设计系统）；三个 Luna Max（分区实现与测试）
- 相关决定：用户批准 `docs/VISUAL_RECONSTRUCTION_PLAN.md`，要求主代理审查并分配三个 Luna Max 实施

## 用户价值

2026-09-09 模型入口修正：设置与计划页增加常驻“模型连接”目录和 ProviderSetupView，复用现有已连接摘要、更改/取消、发现和确认逻辑。解决引导连接完成后模型选择无常驻入口的问题。Web typecheck 通过；真实浏览器验证“更改连接 → 查找本机模型”显示 qwen3:8b，未重新确认或切换当前连接。修改前备份：`output/model-entry-20260909/App.before.vue`。

2026-09-09 试用修正：确认 AI 连接后，等待下一步渲染完成，再定位当前操作区并聚焦按钮，避免连接面板卸载后沿用旧滚动位置。390×844 自定义路径与 1440×900 合成演示路径的按钮完整可见、焦点及不自动运行断言通过（2/2）；Web typecheck 通过。证据与修改前备份：`output/provider-scroll-20260909/`。使用独立 8002/5175 测试服务，保留用户 8000/5173 试用服务。F-063 整体仍为 In Progress。

评委和首次用户需要在五分钟内先看懂风险结论、业务过程和下一步，同时保留知盾 AgentAudit 原有的品牌识别与审计证据氛围。重构应结合旧版优秀美术和当前版清晰交互，避免在“科技感但难读”与“易读但平淡”之间二选一。

## 范围

- 建立唯一共享的品牌色、排版、间距、圆角、阴影、图标和状态视觉规则；
- 恢复旧版 navy/blue/teal/coral 语义、深色证据舞台和现有状态插图；
- 保留四工作区、中文业务结论、攻击链等高、独立证据展开、Finding 编号块、Replay 边界、字号模式和响应式能力；
- 完成检查后收起首次使用区，使真实 Finding 结果进入首屏主体；
- 重构首次使用、Guided Audit、Finding、攻击链、Replay、Provider、文档、规则、扫描记录和验收证据的层级；
- 清理关键用户文字的小字号和低对比度，并统一移动端触控尺寸；
- 增加 F-063 桌面、投屏、大字、移动端和真实核心链路回归。

## 非目标

- 不修改 API、Contracts、Provider 协议、Security Contract、Scan、Trace、Finding、Replay 或 Acceptance 判定；
- 不增加攻击类型、模型、真实企业连接、重试、fallback 或结果后处理；
- 不重新生成已有状态插图，除非经审查证明现有资源无法表达必要状态；
- 不用静态截图、假数据或概念图代替真实前端和后端执行；
- 不处理干净 Windows、Debian 非默认 pointer、真实企业 Gateway 或 RustSec 外部/维护债务；
- 不制作比赛 PPT、Word、PDF 或视频。

## 前后端与数据影响

- Web：统一设计 tokens、应用壳、核心演示链路和次级工作区视觉/信息层级；
- API：无；
- Contracts：无；
- Data/Model/Tool：无执行语义变化；
- Tests：新增/更新视觉结构、响应式、状态图片映射和核心交互 E2E。

## API 或交互契约

- 四个 `WorkspaceId`、入口选择、Provider、资料导入、Scan、Finding、证据展开、Replay、历史、Acceptance 和下载行为保持不变；
- 完成一次检查后，首次使用完整面板收为 56–72px 的当前路径栏，风险结果成为首屏主体；
- Critical Finding 首层顺序为中文风险结论、因果说明、四项业务事实、Finding 视觉、Replay 主操作、攻击链与进一步证据；
- 六阶段攻击链保持等高，证据在独立面板展开，不拉伸其他节点；窄屏改为纵向链；
- 图片只由真实状态驱动：运行中、Critical、Replay Before/After、Provider blocked/connected、Acceptance 分别使用对应原有资源；
- 首次入口不显示与路径选择无直接关系的独立审计状态图；允许旧版浅色网络图作为低干扰环境底纹，但不得成为内容模块或降低文字对比度；
- 首次入口不得使用包住两条任务路径的沉重深色大舞台；允许为组织层级采用轻薄的白色、浅色或半透明容器，两条路径应清楚呈现并让环境底纹若隐若现而不穿透正文；
- 四工作区导航使用一个轻薄的大矩形容器，四个入口仅以内部竖向分隔线组织，不再各自绘制独立方框；当前入口只使用轻微底色和短下划线强调；
- 单一 Attack Plan 显示静态摘要，多项才显示选择器；
- 技术 ID、Rule、Runtime、原始 JSON 和完整 Trace 保持可访问但默认不抢占业务层；
- 标准/大字设置继续持久化，390px 不产生页面级横向溢出。

## 设计基准

- 主规格：`docs/VISUAL_RECONSTRUCTION_PLAN.md`；
- 旧版事实截图：`artifacts/acceptance/generated/f059-visual-review/`；
- 当前概念参考：`artifacts/acceptance/generated/f062-visual-concept/`；
- F-063 已审查概念：`artifacts/acceptance/generated/f063-visual-concept/first-use-brand-restoration-concept.png`、`critical-finding-brand-restoration-concept.png`、`critical-finding-mobile-concept.png`；
- 原有业务美术：`apps/web/src/assets/illustrations/`；
- 视觉组合：浅色业务工作台 + 深色品牌/证据锚点；
- 核心色：Brand Navy `#0B2340`、Action Blue `#4F7CFF`、Evidence Teal `#25BFAE`、Risk Coral `#FF5D5D`、Warning Amber `#E6A23C`、Canvas `#F4F7FB`、Surface `#FFFFFF`、Ink `#132238`、Muted `#64748B`。

## 实施任务

- [x] 冻结桌面/移动端关键状态基准并完成三张核心概念审查；
- [x] 建立共享视觉 tokens、基础排版和状态/证据容器；
- [x] 重构应用壳与首次使用完成态折叠；
- [x] 重构 Guided Audit、Critical Finding、攻击链与 Replay；
- [x] 重构 Provider、资料、规则、记录与验收证据；
- [x] 收口默认字号、对比度、44px 触控目标、长 ID 和移动端；
- [x] 更新 F-063 E2E 并完成真实浏览器、typecheck、build 和相关回归；
- [x] 完成概念/实现对照、安装版边界记录和文档收口。

## 验收标准

- [x] 首次进入保留两条路径，完成检查后首用区收为紧凑路径栏，Finding 结果进入首屏主体；
- [x] 原有状态插图按真实状态清晰展示，不作为全局低透明水印，不遮挡文字；
- [x] Critical Finding 首屏可直接读出风险、原因、四项业务事实和 Replay 主操作；
- [x] 攻击链宽屏六节点等高，证据独立展开；390px 纵向排列且无横向溢出；
- [x] Replay Before/After 对称展示，并明确只是参考配置模拟、未修改企业系统；
- [x] Provider、资料、规则、记录和验收证据使用同一视觉系统和内容分层；
- [x] 关键错误、下一步、证据说明不使用 8–12px 小字，主要文字满足对比度要求；
- [x] 标准/大字、1280×800、1440×900、1600×1000、1920×1080、390×844 均通过关键布局检查；
- [x] 核心交互、请求次数、API/DTO 和安全判定保持不变；
- [x] Web typecheck、production build、F-063 定向 E2E 与现有关键回归通过；
- [x] Browser/IAB console 无新增 warning/error，并完成参考与最新截图的 `view_image` 对照。

## 验证证据

- `npm run typecheck --workspace @agent-audit/web`：通过；
- `npm run build --workspace @agent-audit/web`：通过，仅保留既有主 chunk 大于 500 kB 警告；
- `npx playwright test tests/e2e/f063_brand_visual_restoration.spec.ts`：8 passed；
- `npx playwright test tests/e2e/f045_layout.spec.ts tests/e2e/f047_display_scale.spec.ts tests/e2e/f061_scan_evidence_visual_consistency.spec.ts tests/e2e/f062_editorial_visual_system.spec.ts tests/e2e/f063_brand_visual_restoration.spec.ts tests/e2e/provider_setup.spec.ts tests/e2e/persisted_audit.spec.ts`：30 passed；
- `npx playwright test`：56 passed；
- Browser/IAB：真实 `http://localhost:5173/` 已复核 1024×768、1440×900、标准/大字、390×844、首次入口、设置页、扫描记录、Acceptance、Critical Finding、攻击链证据展开、Replay 与完整报告；最终页面无横向溢出，未发现新增 console error；
- 实测：1024×768 两条首次路径 CTA 均完整可见；390×844 标题无孤字、字号控件 44×44px；攻击链六节点桌面等高约 247.2px，单节点证据展开不改变其他节点高度；Replay Before/After 等高约 713px，移动端计划事实为单列；
- 第二轮视觉巡检将完整 Trace 与原始事件详情改为默认折叠，展开后的 raw/code 正文提高到 13px；案例区移除无意义外层嵌套框；扫描记录主事实标题改为中文比赛表达；Acceptance、资料、Contract、Workspace 与 Provider 状态区同步提高关键正文、错误和下一步的可读性；
- 第三轮实屏反馈修复 592×844 中间宽度下四工作区导航被放大为单卡的问题，四入口保持在同一紧凑矩形轨道；手动查询输入由 6 行收为 4 行并与回答区对齐；Provider Readiness 图片桌面高度提高为 `clamp(208px, 17vw, 240px)`、移动端为 180px；核心 Finding、Trace、Replay、攻击链和 Provider 的 `details > summary` 统一具备至少 44px 点击高度、明确箭头、hover 与 focus-visible；
- Browser/IAB 第三轮实测：大字模式 592×844 导航约 69px 高且四入口同排；1440×900 Provider connected 图片实显 288px、`object-fit: cover`，技术详情点击区约 53px；核心结果页 23 个可见折叠标题与 11 个证据/Replay 操作均无小于 44×44px 的目标，三个关键折叠区可正常展开，页面无横向溢出，console 无 warning/error；
- 概念/实现对照：保留浅色网络氛围、双路径结构、navy 品牌栏、四步任务节奏与深色证据舞台；按用户最新决定，实际四工作区导航改为一个轻薄大矩形容器加三条内部竖向分隔，而非概念图中的无框导航；
- 安装版边界：当前源码已重新冻结 Windows Sidecar、构建 Tauri release 与 NSIS，指定新 Desktop EXE 的 artifact smoke 为 10 passed；安装包 SHA-256 为 `4103AF44F246609D83947A09F39455856F6C9679567EC0AD33DAE64D91BE1D20`。尚未完成另一台干净 Windows 和真实安装窗口的最终视觉复核，因此 F-063 继续保持 `In Progress`。
- 最新反馈验证：固定 Case 风险分类已改为“预期风险类型 + 珊瑚色资源授权绕过”的单行信息栏，两张 Case 的信息栏与执行按钮均对齐；四个 Plan 在宽屏为有独立边框和间距的 2×2 卡片，同排等高且操作贴底，列表区与详情区底边对齐，390×844 收为单列且无横向溢出；选择最后一个 Plan 可正常刷新详情且不产生隐式写请求，页面 console 无新增 warning/error。
- 折叠与排版验证：Plan“技术详情”默认收起，Finding 证据、原结论、历史 Contract JSON、Replay Trace 等折叠入口均为至少 44px 高、14px 正文和统一 SVG 箭头，键盘焦点可见；桌面 raw/code 为 13px 等宽字体，中文标题取消不自然的额外字距；真实受控 Scan→Critical Finding→Replay→Acceptance 路径在 1440×900 与 390×844 下无页面横向溢出，移动端长 ID、状态标签与报告按钮均在视口内，console warning/error 与 page error 均为 0。
- 设置页相邻区块验证：可执行测试计划与手动查询/Agent 回答区域之间固定保留 16px 垂直间距；大字窄屏浏览器实测 gap 为 16px、document width 未超出 viewport，console warning/error 为 0；对应 F-063 定向 E2E 1/1 与 Web typecheck 通过。

## 实施记录

- 2026-09-02：用户批准视觉恢复计划，明确由主代理审查并分配三个 Luna Max 实施。
- 2026-09-02：开始前确认 M6、F-062 完成事实与大量未提交工作树；F-063 禁止全量回滚，只做选择性视觉迁移。
- 2026-09-02：用户否决首次入口右侧独立无语义数据流图，但确认旧版浅色网络背景具有比赛装饰价值；规则修正为“浅色环境底纹可保留，深色状态图只在真实运行/证据状态中使用”。
- 2026-09-02：用户进一步否决包住主模块的深色大框，但不禁止合理的白色、浅色或半透明容器；首次入口以美观和清晰层级为准，避免沉重黑框，使用轻表面与适度透明度让浅色背景只作为隐约可见的比赛氛围层。
- 2026-09-02：三个 Luna Max 分区完成核心链路、次级工作区与 F-063 回归；主代理复核后统一共享 tokens、首次入口、Finding、攻击链、Replay、Provider、资料、规则、运维和验收页的视觉层级，未修改 API、DTO 或安全判定。
- 2026-09-02：按最新实屏反馈将四工作区导航从四个独立方框改为一个整体轻表面，内部使用三条分隔线；active 状态仅保留轻蓝底和居中短下划线，并加入结构回归断言。
- 2026-09-02：按用户要求再次启用 frontend-app-builder 与 frontend-testing-debugging 完成全站视觉巡检，并由三个 Luna Max 分别迭代应用壳、核心证据链和六个次级工作区；主代理复核后补齐 Replay raw/code 字号、案例区嵌套框和扫描记录中文主标签，定向 21/21、全量 52/52 E2E 通过。
- 2026-09-02：按三张最新实屏反馈再次由三个 Luna Max 分区处理应用壳、核心折叠区与 Provider Readiness，主代理接管第三路回复异常并完成集成审查；定向 28/28、全量 54/54 E2E、typecheck、production build、Browser/IAB 交互与无溢出检查通过。按用户要求暂不构建软件安装版，F-063 仍保持 `In Progress`。
- 2026-09-02：用户随后要求封装当前软件、源码与测试；主代理重新冻结 Sidecar，完成 Windows Tauri release/NSIS 构建及新 EXE artifact smoke 10/10，并生成包含软件、当前源码、测试、文档和校验清单的统一交付 ZIP。F-063 仍保留真实安装窗口视觉复核边界。
- 2026-09-04：按用户最新截图调整固定 Case 风险分类和可执行计划布局；使用 frontend-app-builder 与 frontend-testing-debugging 做最小范围实现和 Playwright 实屏验证，Web typecheck、production build、F-045/F-063 定向 10/10 与全量 55/55 E2E 通过。浏览器插件在当前会话不可用，实屏与交互检查使用项目既有 Playwright；真实安装窗口复核仍未完成，功能状态保持 `In Progress`。
- 2026-09-04：继续使用 frontend-app-builder 与 frontend-testing-debugging 完成全站折叠、字体和移动端溢出复核；Plan 技术详情改为默认折叠，证据类 disclosure 统一交互规格，补齐 390px Scan/Replay 自适应并新增真实链路回归。Web typecheck、production build、F-063 8/8、关键视觉 30/30、全量 56/56 E2E 与 diff-check 通过；当前会话无 Browser 插件，采用 Playwright 加截图视觉对照，未修改 API、Contracts 或安全判定，真实安装窗口复核仍保留。
- 2026-09-04：按用户实屏反馈在两个连续设置区块之间增加 16px 垂直留白，并将间距写入既有 F-063 布局回归；定向 E2E 1/1、Web typecheck、窄屏实测和 console 检查通过，右侧预览服务已恢复。

## 2026-09-08 比赛入口与计划卡片试改

- 用户要求：不用前端设计 Skill，突出比赛价值，保留能解释的技术，让首次用户更容易开始；本轮只改展示层。
- 首次入口改为权限安全问题与执行证据说明，推荐合成演示；新增 Security Contract / Trace / Replay 三段技术说明，区分模型生成与规则判定，并保留模拟复测边界。
- 计划卡片保留 2×2 与移动单列，将执行按钮放到卡片底部独立一行；完整描述保留在所选详情中，卡片主层只保留名称、身份与对象。设置页说明明确引导首次用户从核心验收开始。
- 未修改 script 中的业务逻辑、API、Contracts、权限或审计判定。修改前副本与本轮 diff 在 output/f063-competition-pass-before/、output/f063-competition-pass.diff。
- 验证：Web typecheck 与 production build 通过（保留既有 chunk >500 kB 提示）；F-060、F-063、persisted_audit 共 16/16 E2E 通过，覆盖首次操作请求边界、Scan/Finding/Replay、历史恢复和移动端无溢出。之后仅将入口标题改为更审慎的“用执行证据来验证”，计划提示去掉“右侧”以适配移动端。
- Browser/IAB 已看到更新后的首次入口与技术说明，窄窗大字模式实屏已复核；测试后端和 Vite 已恢复，供用户查看。尚未进行陌生用户计时测试，不能声称已证明几分钟独立上手；未重建桌面安装包，F-063 保持 In Progress。

## 2026-09-08 完整前端预览交付

- 用户已授权先完成本轮再评价，明确保留可回退入口，不使用设计 Skill。
- 范围：应用壳、首用路径、设置/证据页目录、连接和资料说明、风险证据与复测导航、次级空态及技术标签；复用现有业务行为。
- 验收：页面导航不触发业务请求；首次入口、连接、导入、Scan/Finding/Replay、历史和质量验收回归；桌面与窄屏实屏；可回退脚本默认只检查，遇到本轮后新增改动时拒绝覆盖。
- 当前状态：本轮 Web 前端预览已交付，F-063 继续 In Progress，待用户评价及真实安装窗口复核；本轮未重建安装包。
- 实现：首用推荐入口与三段技术说明；选择路径后收起重复标题；设置/证据页增加原生锚点目录；结果按风险、Trace、Replay 引导阅读；连接与资料使用中文步骤；运维移至高级运行之后；统一卡片、页头与空态间距。
- 验证：Web typecheck、production build 通过（既有 chunk >500 kB 提示保留）；定向 15/15 与全量 58/58 Playwright 通过。新增目录保留未提交输入、无业务写入、标题不被顶栏遮挡和结果导航/Replay 请求次数断言；390px 无横向溢出。最终仅补齐第二入口的说明标签，浏览器复核卡片对齐。
- 首轮回归暴露的锚点遮挡已用根滚动容器 scroll-padding 修正；旧 Scan 标签断言同步为中英双语。首用白屏 trace 记录 ERR_NETWORK_CHANGED，未添加重试或应用兜底，之后定向及全量均通过。
- Browser/IAB 复核了首页、桌面目录跳转和连接步骤；完整结果/Replay 页面使用本轮 E2E 截图复核。预览是 tests.e2e.support.server 确定性测试后端，不是现场真实模型验收。尚无陌生用户独立上手计时证据。
- 回退目录：output/frontend-review-20260908-150140/，由 output/frontend-review-current.txt 指向。before/after、changed-files.json 与 changes.diff 只覆盖本轮差异；rollback.ps1 默认只检查，加 -Apply 恢复。后续改动冲突时整次拒绝覆盖；已在临时副本验证检查、恢复、重复恢复与冲突拒绝。
- 证据：output/frontend-review-final-tests.log、output/frontend-review-build.log、回退目录内 evidence/；不覆盖其他功能的未提交修改，不自动推送。

## 2026-09-08 美术增强预览

- 用户认可现有布局，反馈美术偏少。本轮保留交互和布局主线，增加品牌主视觉与技术图形，不使用前端设计 Skill。
- 无 API、数据或判定变化；验收包含首屏操作可见、窄屏无溢出、图片加载和既有关键 E2E。独立回退点 output/frontend-art-20260908/。

- 已交付：原创 SVG 权限边界主视觉（文档、玻璃盾、工具节点与回放环）；Security Contract / Trace / Replay 三张原创矢量说明图；深蓝品牌横幅与配套青绿图形。图片为概念示意，不表达实际验收通过状态。
- 最终页面采用代码绘制的 SVG（约 5 KB），生成的立体图片仅保存在 output/frontend-art-20260908/generated-alternative.png 供比较，不作为应用依赖。未使用前端设计 Skill；仅使用 imagegen Skill 生成对比方案。
- 验证：typecheck、production build、F-060/F-062/F-063 共 17/17 E2E 通过；Browser/IAB 实屏复核 1440px、1024×768 标准字号双入口完整可见和 390px 适配。未改业务逻辑、API、安全判定或现有结果插图。
- 本轮独立回退包 output/frontend-art-20260908/（before/after、changed-files.json、rollback.ps1）默认只检查，加 -Apply 恢复用户刚认可的布局版本并移除本轮新增 SVG。临时副本验证整轮恢复、重复恢复和后续编辑冲突保护通过。安装包未更新，F-063 仍保留安装窗口验收边界。

## 2026-09-09 生成主视觉与配套美术精修预览

- 用户选定生成版本替代首页 SVG 主视觉；保留三张矢量技术图，统一深蓝证据底板、青绿线条与入口图标材质。只改展示层，图片完整适配容器，不裁去文档和工具节点。
- 独立回退点 output/frontend-art-20260909/，保留此前工作区改动和旧 SVG；不重建安装包。

- 完成：接入用户选定生成图，桌面/窄屏均以 contain 完整展示；三张技术图统一深蓝底板，入口图标增加轻微立体层次，卡片保留原透明底色并叠加青绿/蓝色淡渐变。保留所有业务文案与交互。
- 验证命令：`npm run typecheck --workspace @agent-audit/web`、`npm run build --workspace @agent-audit/web`、`npx playwright test tests/e2e/f060_first_use.spec.ts tests/e2e/f062_editorial_visual_system.spec.ts tests/e2e/f063_brand_visual_restoration.spec.ts`；类型/构建通过，最终 17/17 E2E 通过（首用、1024px CTA、390px 无溢出、Scan/Finding/Replay）。首次运行发现卡片透明度被 background 简写重置，已改为 background-image 叠加，保持原底色；测试未放宽。
- Browser/IAB 已复核整页构图与技术插画，主图实际加载宽度 1536、object-fit 为 contain。预览恢复为确定性测试后端；未进行真实模型或安装窗口验收，F-063 保持 In Progress。
- 回退包含本轮前后副本、差异、日志与 rollback.ps1；默认只检查，加 -Apply 恢复上一版。临时副本已验证恢复、重复恢复和后续编辑冲突拒绝。新增 PNG 原样复制，旧 SVG 保留。

## 2026-09-09 后续工作区密度精修预览

- 用户要求保留满意的首页，收紧后几页空白，避免过度装饰。范围仅 styles.css 的次级页头、目录、空态和查询卡片，以及验收证据页头内边距；不新增插图，不修改业务逻辑。独立回退点 output/frontend-density-20260909/。

- 完成：次级页头下距 40→24px，目录间距 28→20px；扫描空态取消 280px 最小高度，以内容决定高度，按钮与说明间距收紧；通用空态最小高度 276→168px；查询卡片内边距 28/30→22/24px；验收页头最大内边距 40→28px、列间距上限 64→28px。少量青绿标题侧线与区块分隔，不新增插画、不修改首页组件。
- 验证命令：`npm run typecheck --workspace @agent-audit/web`、`npm run build --workspace @agent-audit/web`、`npx playwright test`。类型与构建通过（既有 chunk 提示），全量 58/58 E2E 通过；Browser/IAB 已查看设置、扫描记录与验收证据页。源码 diff-check 通过。
- 独立回退包 output/frontend-density-20260909/ 已验证只读检查、临时副本恢复与后续编辑冲突拒绝；预览使用确定性测试后端，未更新安装包，F-063 继续保留安装窗口验收边界。

## 2026-09-09 次级工作区少量图形补充预览

- 用户澄清允许少量美术，避免滥用。本轮仅补设置页头权限计划矢量插画、扫描空态四个语义图标；不增加新区域，不修改业务逻辑。窄屏隐藏非必要页头插画，流程图标保留。回退点 output/frontend-accents-20260909/。

- 已完成设置页头原创 SVG 与扫描流程四图标。`npm run typecheck --workspace @agent-audit/web`、`npm run build --workspace @agent-audit/web` 通过；`npx playwright test tests/e2e/f063_brand_visual_restoration.spec.ts tests/e2e/scan_records_empty.spec.ts` 12/12 通过，涵盖 390px、目录与 Scan/Replay。Browser 实屏确认设置插画位于右侧，不覆盖文案。
- 回退包已验证临时副本恢复与冲突保护。未修改首页、业务请求和判定；预览仍使用确定性测试后端，未更新安装包，F-063 保持 In Progress。

## 2026-09-09 权限规则摘要紧凑布局预览

- 针对用户截图中的全宽长行，角色改为宽屏三列，资源/工具/外发规则改为宽屏双列；窄屏单列。名称、ID 和属性纵向成组，去除重复分类眉题，少量灰蓝底色与青绿侧线；不改编辑模式、字段或权限逻辑。回退点 output/contract-layout-20260909/。

- 完成并验证：`npm run typecheck --workspace @agent-audit/web`、`npm run build --workspace @agent-audit/web` 通过；`npx playwright test tests/e2e/contract_editor.spec.ts tests/e2e/f063_brand_visual_restoration.spec.ts` 12/12 通过，覆盖权限编辑、窄屏与 Scan/Replay。Browser 实屏确认角色三列、规则双列、名称与 ID 相邻；不截断长 ID。
- 修改范围仅 SecurityContractEditor.vue 的只读摘要模板和样式、项目记录；回退包临时副本恢复和后续修改冲突保护已验证。未更新安装包，F-063 保持既有验收边界。

## 2026-09-18 当前工作树双平台安装包交付

- 用户授权把当前软件封装为 Windows/Linux 安装包，并要求测试代理下载速度；本轮不使用前端设计 Skill，不修改业务实现或安全判定。
- 已从当前工作树冻结 Sidecar、构建 Windows NSIS 和原生 Linux `.deb`/AppImage；三个安装包、安装说明、输入源码清单、依赖约束和机器证据在 `artifacts/deliverables/AgentAudit-0.1.2-installers-20260918/`。
- 验证：全端 `npm run typecheck` 通过；Windows `pytest -q tests/unit tests/integration` 891 passed/7 skipped，Linux 同范围 895 passed/3 skipped；新 Windows EXE 两轮启停与一次精确 owned-process 崩溃恢复通过，冻结 API 七项只读检查含真实本机模型发现通过；Linux artifact 检查 22/22，含增强 pointer 与真实 GTK chooser 2/2。
- 本轮仅修正 POSIX 只读库与 symlink 错误文本两项测试、原生选择器首用路径夹具；修改前副本在 `output/installer-validation-tests-before-20260918/`。构建输入清单保留原快照，manifest 单独列明构建后验证文件变化，未将新哈希冒充旧构建输入。
- 代理测速采用同文件 4 MiB Range 两轮；PyPI 显式直连更快，GitHub raw 通过显式代理成功。区域组切换短测不足以证明稳定国家排名，原代理组选择已恢复。
- 边界：未完成干净 Windows 的新包安装/升级/卸载、独立 Linux 桌面完整用户流程、安装窗口全链路视觉验收；真实 qwen3 固定验收历史 22/24 不变。F-063 保持 In Progress。

- 2026-09-18 页面试用修正：历史复测卡片统一浅色背景，Before/After 使用白色，提示和状态保留原有语义色，编号及配置文字加深，并允许长编号在窄屏换行。仅 styles.css 样式变更；Web typecheck/build、真实 E2E 服务下 Scan→Replay→保存→重开主链路通过，桌面/移动端复核工件与回退备份在 output/history-colors-20260918/。现有视频仍保留旧录屏，安装包未重新构建。F-063 整体保持 In Progress。
