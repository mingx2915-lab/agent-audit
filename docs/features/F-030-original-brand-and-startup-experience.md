# F-030 原创品牌标识与桌面启动体验

- 状态：Completed
- 所属里程碑：M6 本地双平台产品化
- 负责人：主代理
- 相关决定：`docs/M6_LOCAL_DUAL_PLATFORM_PRODUCT_PLAN.md`、`docs/NAMING.md`、`docs/ARCHITECTURE.md`

## 用户价值

知盾 AgentAudit 需要一套与产品真实能力一致、在小尺寸和双平台安装环境中清晰可辨的原创品牌标识。启动过程应当用克制的本地状态画面说明 Workspace 与 Sidecar 正在准备，而不是让用户面对空白窗口或误以为软件卡死。该能力直接改善比赛的用户体验与展示效果，但不改变或夸大安全结论。

## 范围

- 以 `Contract → Trace → Finding → Replay` 为语义主线，采用用户最终确认的蓝色字形、青绿色开放框与红色连接线标识；
- 用户指定的高分辨率 RGBA PNG 是唯一视觉母稿，只允许移除棋盘格、生成透明背景和机械缩放，不再重画或改变构图比例；
- 形成图形标识、`知盾 AgentAudit` 横向组合和启动画面三类资产；
- 生成 Windows/Linux/Tauri 所需的 ICO、ICNS 与 PNG 尺寸，保持小尺寸清晰；
- 新增本地 Tauri Splash window，显示真实 Sidecar 启动状态，Ready 后关闭并显示主窗口；
- Web/Desktop 中的品牌入口、安装包图标和窗口图标使用同一套源资产；
- 保存设计来源、候选筛选、相似性检索范围与不能由本功能保证的法律边界。

## 非目标

- 不承诺仅凭视觉设计或自动检索即可获得法律意义上的“绝对不侵权”；
- 不模仿任何现有安全、杀毒、AI、云服务或开发工具品牌；
- 不使用第三方 Logo、图标包、未确认授权的字体或图库元素；
- 不制作 PPT、视频、宣传海报或新的产品功能页面；
- 不人为延长启动时间，不显示虚假百分比或预制成功动画；
- 不改动 Security Contract、Trace、Finding、Replay 或 Provider 的业务逻辑。

## 前后端与数据影响

- Web：复用最终 PNG 标识，品牌入口和必要空态保持一致；不重排核心 Guided Audit 信息架构；
- API：无新业务 API；Splash 只消费桌面壳已有的本地运行状态；
- Contracts：原则上无新业务 DTO；若桌面启动状态需要跨边界展示，只复用或最小扩展现有 Desktop runtime status；
- Desktop：替换主图标资产，新增 Splash window 与 Ready/Failed 状态投影；
- Data/Model/Tool：无影响，不调用 Provider，不写 Workspace 业务数据。

## 视觉与交互契约

### 标识语义

最终方向为用户确认的 **知盾连接标识**：左侧蓝色抽象字形表达“知”，右侧青绿色开放框表达受控边界，中间短红线表达被审计的风险连接。最终构图不再做二次图形再设计。

色彩基线：

- Midnight：`#0B1F33`；
- Audit Teal：`#2EC4B6`；
- Evidence Blue：`#5B8FF9`；
- Risk Coral：`#FF5A5F`，只作为 Finding/风险状态辅助色；
- Paper：`#F3FAF8`。

标识必须先通过 16、24、32、48、256 px 可读性检查；颜色不能成为区分状态的唯一手段。

### 启动画面

- Tauri 主窗口保持隐藏，Splash 立即显示；
- Splash 只显示本地资产，不加载公网资源、GIF 或视频；
- 状态与真实生命周期一致：准备 Workspace、启动本地审计服务、检查运行环境、已就绪；
- Ready 后立即关闭 Splash 并显示主窗口，不设置虚假等待；
- Failed 时保留可读诊断和退出动作，不显示已就绪；
- Windows 与 Linux 使用同一视觉，平台差异只保留系统窗口与图标格式。

## 原创性与相似风险控制

- 三个候选先以纯黑白轮廓评审，排除依靠渐变或文字掩盖轮廓相似的问题；
- 对最终候选记录关键构成、禁止构成和推导过程；
- 检查同类 Security/AI/Audit 产品的高频图形，并对最终候选做公开图像与商标近似检索；
- 检索结论只能写为“在已检查范围内未发现明显近似”，不能写“保证不侵权”；
- 商业发布或申请商标前，由商标专业人员在目标法域和类别做最终清查；
- 保留用户指定原图、透明化生成提示、最终 RGBA 母稿和版本记录；当前标识不包含第三方字体或图库元素。

## 实施任务

- [x] ~~锁定品牌语义、禁止构成、色彩和相似风险边界；~~
- [x] ~~调研常见安全/AI 软件标识并建立避免清单；~~
- [x] ~~完成候选比较，由用户指定并锁定唯一最终图；~~
- [x] ~~从用户指定原图仅提取透明背景，形成最终 RGBA 母稿；~~
- [x] ~~替换 Web/Desktop 品牌源资产并生成 Windows/Linux 图标集；~~
- [x] ~~实现真实生命周期 Splash，覆盖 Ready/Failed/关闭行为；~~
- [x] ~~运行自动测试、typecheck、Web/Desktop build、Rust 检查与人工视觉验收；~~
- [x] ~~更新状态、资产说明和验证证据并提交 Git。~~

## 验收标准

- [x] ~~最终轮廓不使用盾牌、锁、钥匙孔、指纹、眼睛、机器人头像或六边形电路作为主体；~~
- [x] ~~在 16、24、32、48、256 px 和明暗背景中可辨，不依赖颜色表达唯一信息；~~
- [x] ~~Web、窗口、任务栏、安装包和 Linux 图标来自同一 RGBA 母稿；~~
- [x] ~~Splash 的显示、Ready、Failed 和关闭均来自真实 Desktop/Sidecar 状态，无假进度、无公网资源；~~
- [x] ~~新视觉不遮挡 Guided Audit 主线，390×844 与桌面最小窗口无横向溢出；~~
- [x] ~~已记录公开相似性检索范围、发现和法律边界，未作绝对不侵权承诺；~~
- [x] ~~相关自动检查、构建、artifact smoke 与 `git diff --check` 通过。~~

## 验证证据

- 测试命令：`.venv\Scripts\python.exe -m pytest -q`；`npx playwright test --reporter=line`；`npm run typecheck`；`npm run build`；`cargo check --offline`；`npm run desktop:build`
- 结果：Python 516 passed / 2 skipped；Playwright 12 passed；TypeScript、Web/Contracts build、Rust check、Windows release 与 NSIS build 通过。
- 人工步骤：用户指定并确认最终彩色构图；32 px 平台图标核对通过；真实 Windows release 启动后 Splash 投影 `starting`，Ready 后主窗口显示，Sidecar 保持运行且 `/api/health` 返回 200。

## 实施记录

- 2026-08-28：用户授权主代理负责整体视觉把关。F-029 共享实现与 Windows 工件已经完成，但真实 Linux 与干净 Windows 证据受外部环境阻塞；F-029 转为 Blocked，F-030 成为唯一活动功能。
- 2026-08-28：用户否决重新绘制方案并最终指定 `codex-clipboard-89ada0bf-7332-4b37-a8a9-b885e98bd867.png`。后续必须直接使用该构图，只进行透明背景提取和平台尺寸导出。
- 2026-08-28：真实 release 启动发现两处生命周期竞态：WebView 早于 setup 读取默认 stopped；关闭 Splash 被全局 CloseRequested 错误当作退出并终止 Sidecar。现已将进程初态固定为 starting，且只允许 main 窗口关闭触发 Sidecar shutdown。重新构建后 Sidecar 进程保持、状态 ready、health 200。
