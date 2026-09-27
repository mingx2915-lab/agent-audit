# F-032 评委导向的视觉层级与人话文案

- 状态：Completed
- 所属里程碑：M6 本地双平台产品化
- 负责人：主代理
- 相关决定：`docs/features/F-021-judge-guided-audit-visualization.md`、`docs/features/F-030-original-brand-and-startup-experience.md`

## 用户价值

评委和企业用户打开软件后，应在十秒内知道“先连接、再开始验收、最后看 Finding 与 Replay”，而不是先阅读大段产品解释。界面需要用清楚的视觉优先级表达操作、风险、证据和通过状态，并保留专业人员需要的完整 Trace。

## 当前问题

- 深色背景、深色卡片和青绿色按钮贯穿所有工作区，页面缺少视觉停顿，主操作与次级操作难以区分；
- 首页同时出现连接、资料、攻击计划、Trace、Runtime 和多段边界说明，文字密度高于任务密度；
- 大量英文 kicker、中英混排和“真实、明确、不会、仅”等解释句重复出现，形成明显的 AI 式说明口吻；
- Finding、Replay passed、Readiness、普通信息和按钮共用接近的颜色，评委难以快速识别重点；
- 当前只有 Logo，没有服务于空状态和核心链路理解的原创视觉资产。

## 设计原则

1. **先任务，后解释**：默认视图先给当前状态、一个主动作和结果；边界、Runtime、原始 JSON 放入可展开详情。
2. **一屏一个重点**：同一区块只允许一个视觉主按钮；次级动作使用描边或文字按钮。
3. **颜色有语义**：品牌蓝表示主操作，珊瑚红表示风险/Finding，薄荷绿表示通过/Replay，琥珀表示等待或部分可用，灰白表示普通信息。
4. **深色只做品牌锚点**：深海军蓝保留在顶部品牌栏、Logo 和少量重点面板；主工作区改为浅色中性画布与白色卡片。
5. **证据不删，只分层**：不删除 Trace、Contract、Rule ID、Provider 诊断等事实，只把它们从默认阅读层移到“查看证据/技术详情”。
6. **说人话**：标题说明用户要完成的事；短句优先，不用宣传语，不把技术实现写成每张卡的导语。

## 视觉系统

### 基础色

- `Brand Navy #0B2340`：顶部品牌栏、焦点标题和少量证据面板；
- `Action Blue #4F7CFF`：唯一主操作、当前导航和选中态；
- `Evidence Teal #25BFAE`：通过、Replay after、可信证据；
- `Risk Coral #FF5D5D`：Critical Finding、违规链路和失败状态；
- `Warning Amber #E6A23C`：Readiness partial、等待确认和非阻断提醒；
- `Canvas #F4F7FB`、`Surface #FFFFFF`、`Ink #132238`、`Muted #64748B`：主工作区、卡片和正文。

颜色只表达状态和优先级，不以红绿作为唯一信息来源；状态仍保留文字和图形标记。

### 按钮层级

- Primary：Action Blue 实心，每个区块最多一个；
- Risk action：只用于“查看风险/重新验证风险”，不用于普通导航；
- Success action：只用于 Replay/确认修复后的动作；
- Secondary：白底描边；
- Tertiary：无底色文字按钮；
- Disabled：中性灰，不用降低到不可读。

### 页面层级

- 顶部：紧凑品牌栏，只保留产品名、合成靶场标记和四个工作区；
- 核心验收首页：连接/资料状态采用紧凑摘要；主 Hero 只回答“验证什么”和“现在做什么”；
- 攻击链：Actor → Source → Resource → Authorization → Tool → Sink 是页面视觉中心，违规节点用 Coral，安全阻断用 Teal；
- Finding 与 Replay：Before 风险、After 阻断并排对照，不与普通信息卡同权重；
- 高级工作区：保留完整能力，但默认折叠解释性段落，标题改为任务语言。

## 文案规则

- 页面标题优先控制在 12 个中文字符以内，辅助说明优先控制在 28 个中文字符以内；
- 删除无信息增量的“真实、明确、当前、只会、不会、这里将”等词；
- 英文只保留 Security Contract、Trace、Finding、Replay、Provider 等必要术语；
- 不在每个区块重复“本地、合成、不会联网”，统一放在顶部边界标记和帮助详情；
- 空状态写下一步，例如“连接模型后可开始验收”，不写系统自述；
- 错误文案保留原因和下一步，不使用“请稍后重试”式无诊断兜底。

## 原创图片设计稿（本功能不生成）

本阶段只锁定用途、构图和风格，不调用图像生成服务，不新增位图工件。后续需用户确认后另立资产任务。

### A. 核心验收空状态：Contract Trace Path

- 用途：首页未运行 Scan 时替代大面积文字空白；
- 构图：左侧蓝色 Actor 路径穿过六个抽象节点，在 Authorization 处分为“珊瑚违规路径”和“薄荷阻断路径”，最终指向右侧 Sink 门形；
- 风格：干净的 2.5D 扁平矢量、柔和阴影、透明或浅灰背景；
- 禁用元素：盾牌、锁、指纹、眼睛、黑客兜帽、漏洞虫、现有安全软件常见徽章；
- 不嵌文字，不模仿现有品牌 Logo，不改变用户已确认的知盾 Logo。

### B. Scan 进行中：Evidence Pulse

- 用途：长于一秒的 Scan 运行态；
- 构图：六个节点沿单向轨迹依次点亮，中心有一段 Coral 信号被 Contract 节点捕获；
- 风格：可拆成静态关键帧或轻量动画，不使用加载旋转圈作为主视觉；
- 不出现人物脸、机器人或聊天气泡。

### C. Replay 结果：Before / After Split

- 用途：Replay 完成后的对照摘要；
- 构图：同一条路径左右对照，Before 的 Coral 线到达外部 Sink，After 的 Teal 线在授权节点停止；
- 风格：信息图优先，必须与真实 before/after 数据并列，不能替代证据；
- 不写“100% 安全”等结论，不生成虚构数值。

## 范围

- 重构全局颜色 Token、页面背景、顶部品牌栏、工作区导航和按钮层级；
- 精简核心验收、模型连接、资料导入、Replay、Readiness 与高级入口的可见文案；
- 让默认首页的主动作、攻击链、Finding 和 Replay 形成清楚的视觉顺序；
- 对高级工作区做统一浅色表面、状态色和标题层级整理；
- 保持现有功能、API、DTO、测试选择器和业务证据不变；
- 保持 390×844 窄屏可用且无横向溢出。

## 非目标

- 本功能不生成、编辑或接入任何新图片；
- 不修改用户确认的 Logo，不重新设计品牌标识；
- 不制作 PPT、视频、营销首页或宣传海报；
- 不修改 API、Contracts、Security Contract、Finding 判定、模型连接或 Workspace 逻辑；
- 不通过隐藏错误、删除证据或静态假数据让界面显得“更干净”；
- 不引入新的 UI 框架、图表库、字体 CDN 或联网资源。

## 前后端与数据影响

- Web：调整现有 Vue 组件的视觉 Token、布局与可见文案；复用当前 Logo 和 Element Plus；
- API：无；
- Contracts：无；
- Data/Model/Tool：无；
- Desktop：复用当前 Web Renderer，不新增原生命令。

## API 或交互契约

- 所有业务请求、响应和执行顺序保持不变；
- 现有 `data-testid` 保持稳定；
- 首载不得因视觉重构新增 Provider、Discovery、Readiness、Scan 或 Import POST；
- 主按钮仍调用当前真实 Scan/Replay/Readiness/Import 行为；
- 完整 Trace、Finding evidence、Runtime snapshot 与错误诊断仍可访问。

## 实施任务

- [x] 建立浅色工作台与语义色 Token，重构品牌栏、导航和通用按钮层级；
- [x] 精简核心验收首页与关键操作文案，重排 Scan → Finding → Replay 主线；
- [x] 统一模型连接、资料导入、Readiness 和高级工作区的视觉层级；
- [x] 保持所有现有交互契约与响应式布局；
- [x] 完成 TypeScript typecheck、production build、Playwright 回归和人工截图审查；
- [x] 记录三张原创图片的最终 brief，不生成图片。

## 验收标准

- [x] 1440px 默认首页首屏能明确识别产品、当前准备状态和唯一主操作；
- [x] 主操作、风险、通过、警告和普通信息使用不同且稳定的语义样式；
- [x] 主工作区不再由连续深色卡片组成，深色仅保留为品牌或局部证据锚点；
- [x] 默认路径中的重复解释明显减少，技术详情仍可展开查看；
- [x] Finding 与 Replay before/after 在不阅读原始 JSON 的情况下可快速区分；
- [x] 390×844 无横向溢出，按钮、状态和证据仍可访问；
- [x] 现有 Python tests、Web typecheck/build 与关键 Playwright E2E 通过；
- [x] 本功能没有调用图像生成服务，也没有新增生成图片。

## 验证证据

- 测试命令：`npm run typecheck`；`npm run build --workspace apps/web`；`.venv\Scripts\python.exe -m pytest -q`；`npx playwright test --reporter=line`；`git diff --check`
- 结果：根 TypeScript typecheck 通过；Web production build 通过（只有既有 chunk size warning）；567 passed、2 skipped、1 个既有 Starlette deprecation warning；13 个 Playwright E2E 全部通过；diff check 无 whitespace error
- 人工步骤：使用 Test-only Provider 与隔离 Workspace 在 1440×1000、390×844 复核首次连接、Guided Scan、Critical Finding 和同 Plan Replay；页面无横向溢出，风险/通过/主操作颜色可区分，本地服务复核后已停止

## 实施记录

- F-031 的共享实现和 Windows 证据已完成，但真实 Linux Secret Service/artifact 仍是外部验收债务；该外部阻塞不改变 F-032 的纯 Web Renderer 范围。
- 图片创意本轮只形成设计约束，必须由用户再次确认后才能调用图像生成服务。
- 实际实现只修改现有 Web Renderer 的 App 壳、核心验收组件和支撑组件；没有修改 API、Contracts、业务数据、Logo 或桌面原生命令。
- 三个 Luna Max 分别承担全局壳、核心 Scan/Finding/Replay、连接/资料/高级证据组件，主代理完成组合审查、真实业务 E2E 与视觉截图复核。
