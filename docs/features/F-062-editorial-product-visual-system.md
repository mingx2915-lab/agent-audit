# F-062 编辑式产品视觉系统与去模板化收口

- 状态：Completed
- 所属里程碑：M6 本地双平台产品化
- 负责人：主代理
- 相关决定：用户认为当前功能基本完整，但整体仍有明显 AI 模板感，要求以新前端技能统一审查并由三个 Luna Max 并行优化

## 用户价值

评委和普通用户应首先看到一款成熟、可信、可长期使用的企业桌面工具，而不是由渐变背景、浮动卡片、等宽小字和技术装饰堆叠出的 AI Dashboard。界面需要用稳定的排版、清楚的中文结论和一致的任务结构帮助用户理解“检查了什么、发生了什么、为什么违规、下一步做什么”。

## 范围

- 以两张 F-062 设计概念图为视觉基准，统一应用壳、首次入口和核心验收结果态；
- 将全局视觉从整页装饰性网络背景、玻璃感和卡片堆叠收敛为真白/冷灰编辑式工作台、细分隔线和开放式布局；
- 复用已有攻击链数据流、Finding 聚焦、Replay Before/After 和 Provider Readiness 原创图片，但只放在对应真实状态与证据区域，不再整页铺底或遮盖文字；
- 将四个工作区改为单一水平任务导航，保留名称、说明和真实选中状态；
- 首次入口使用一个结构框内的两条选择行，不再并排显示两个浮动卡片；
- 核心验收结果优先呈现中文业务结论、上下文、六阶段攻击链、Finding 证据和 Replay 操作；
- 同步检查设置、资料、验收、历史和错误状态中的小字、等宽字体、容器、按钮与信息层级；
- 增加桌面与窄屏视觉、交互和关键文案回归。

## 非目标

- 不修改 API、Contracts、Provider、Workspace、Security Contract、Scan、Trace、Finding 或 Replay 判定；
- 不新增模型、攻击计划、指标、页面或产品主张；
- 不把概念图或截图作为静态 UI 嵌入产品；已有原创状态图片按真实条件继续复用；
- 不删除 Rule、Trace、Runtime、原始 JSON 或诊断信息，只调整默认层与技术详情层；
- 不为视觉效果增加 retry、fallback、数据修补或固定业务结果。

## 前后端与数据影响

- Web：调整全局 tokens、应用壳、导航、首次入口、Guided Audit、Finding/Replay 和其他工作区的视觉与信息层级；
- API：无；
- Contracts：无；
- Data/Model/Tool：无执行语义变化。

## API 或交互契约

- 保持现有四个 `WorkspaceId`、入口选择、Scan、证据展开、Replay 和下载行为；
- 选中状态、风险色和通过色仍只由真实状态驱动；
- 攻击链节点保持六阶段顺序，展开证据不改变其他节点高度；
- 标准/大字设置继续本地持久化，窄屏不产生页面级横向溢出；
- 默认层使用中文业务表达，真实 ID 与原始证据仍可访问。

## 设计基准

- `artifacts/acceptance/generated/f062-visual-concept/first-use-editorial-concept.png`
- `artifacts/acceptance/generated/f062-visual-concept/critical-finding-editorial-concept.png`

设计系统：真白与冷灰画布；安静的深海军蓝顶栏；Action Blue、Evidence Teal、Risk Coral 只承担真实语义；正文主要使用中文 UI sans-serif；等宽字体仅用于真实 ID/代码；6–10px 圆角；细边线；极少阴影；开放式 band、rail、row 和 evidence sheet 优先于卡片网格。

## 实施任务

- [x] 建立 F-062 全局 tokens、应用壳、水平任务导航和首次入口；
- [x] 重构 Guided Audit 的结果头、上下文、攻击链、Finding 与 Replay 信息层级；
- [x] 同步其他工作区的小字、容器、按钮和错误状态；
- [x] 增加 F-062 桌面/窄屏与核心交互 E2E；
- [x] 完成主审、概念图对照、真实浏览器复核和全量相关回归；
- [x] 更新 STATUS、FEATURES 与验证证据。

## 验收标准

- [x] 1600×1000 首屏不再把装饰性网络图作为整页固定背景，不再显示玻璃卡片或四张浮动导航卡；已有原创图片在对应内容区克制复用；
- [x] 首次入口在单一结构框中显示两条选择路径，标题、说明、隐私边界和操作层级清楚；
- [x] 真实 Critical Finding 结果在一个桌面视口内可读出业务结论、四项上下文、六阶段攻击链、规则、Evidence Sequence 和 Replay 操作；
- [x] 非 ID/代码的用户可见标签、说明和操作不再默认使用等宽字体，正文与关键操作不使用微小字号；
- [x] 攻击链节点宽屏等高，证据展开不拉伸其他节点；390×844 无页面级横向溢出；
- [x] Provider、资料、验收、历史和错误状态遵循同一字体、容器与语义色规则；
- [x] 原有入口选择、Scan、Finding、证据展开、Replay、字号切换及请求次数保持不变；
- [x] typecheck、production build、F-062 定向 E2E 和现有关键视觉回归通过。

## 验证证据

- `npm run typecheck`：通过；Contracts、Web、Desktop TypeScript 均无错误；
- `npm run build`：通过；仅保留既有 Vite chunk-size warning；
- `npx playwright test tests/e2e/f062_editorial_visual_system.spec.ts --reporter=dot`：3 passed；
- F-060/F-061/F-062、布局、字号和 Provider 关键回归：22 passed；
- `npm run test:e2e -- --reporter=dot`：48 passed；
- `git diff --check`：通过；
- Browser/IAB：1600×1000 与 390×844 实际交互复核通过；运行真实 Test-only `source_sink` Scan 得到 Critical Finding，证据展开前后六节点高度不变，390px `scrollWidth <= innerWidth`，console warn/error 为空；
- 截图方法：Browser/IAB `tab.screenshot`；概念图与最新桌面/移动截图均以 `view_image` 原尺寸复核。

## 视觉对照记录

| 对照项 | 实现结论 |
| --- | --- |
| 顶栏与导航 | 与概念一致：深海军蓝品牌顶栏、单一水平任务导航、细分隔线；保留真实标准/大字状态。 |
| 首次入口 | 与概念一致：一个结构框内两条等宽选择行，不再使用并排浮动卡片。 |
| 画布与容器 | 与概念一致：真白/冷灰、开放式 band/rail/row，减少阴影、渐变和重复圆角容器。 |
| 字体与小字 | 与概念一致：中文 UI 字体承担标题、说明和操作；等宽字体仅保留真实 ID/代码；正文和关键标签不再使用微小字号。 |
| 结果层级 | 与概念一致：中文业务结论 → 四项上下文 → 六阶段攻击链 → Finding evidence sheet → Replay。 |
| 原图复用 | 按用户追加要求有意偏离无图概念：保留 `acceptance-page-evidence-network`、`audit-chain-data-flow`、`finding-evidence-focus`、Replay Before/After 与 Provider Readiness，改为局部、状态驱动且不压字。 |
| 窄屏 | 390×844 改为纵向任务流，无页面级横向溢出；字号切换仍可用。 |

首屏概念文案“资料仅保存在本机，选择后不会自动运行模型”在实现中沿用既有且更准确的边界表达“不上传文件 · 不自动运行模型”；这是有意的 copy 差异，不改变行为。除用户追加的原图复用和上述边界文案外，没有未说明的视觉偏差。

## 实施记录

- 2026-09-02：完成当前 1600×1000 首屏与历史 Critical Finding 截图审查；确认主要 AI 感来自装饰性背景、浮卡网格、过多等宽/英文小字、模糊浅色文案和重复容器。
- 2026-09-02：使用 Frontend App Builder 与 Image Gen 生成两张不作为产品静态资产的设计基准；视觉方向锁定为编辑式企业工作台，不增加新产品功能。
- 2026-09-02：用户要求复用原有图片；概念图中完全无图片的表达调整为“局部、状态驱动、文字不压图”，保留现有原创资产的产品价值。
- 2026-09-02：三个 Luna Max 分别完成应用壳/首次入口、Guided Audit/Finding/Replay、次级工作区/E2E；主代理完成 diff、真实浏览器、响应式、交互、console、typecheck、build 和 48 项全量 E2E 审查。
- 2026-09-02：主审修正两个 F-062 E2E 定位/滚动断言，并同步 Acceptance 旧视觉测试：不再要求整页网络背景，改为验证内容区原始证据图与纯白证据表面。
