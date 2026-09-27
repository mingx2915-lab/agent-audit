# F-047 可切换界面大小与桌面画布适配

- 状态：Completed
- 所属里程碑：M6 本地双平台产品化
- 负责人：主代理
- 相关决定：`docs/UI_CONTENT_LAYOUT_ART_AUDIT.md`、`docs/features/F-045-typography-and-workspace-layout.md`

## 用户价值

让用户在桌面大屏、投屏和不同视距下自行选择可读的界面大小，不再依赖操作系统临时缩放，也不因软件窗口变大而继续看到偏小的正文和工程字段。

## 范围

- 顶部提供“标准 / 大字”两档界面大小，选择后立即作用于整个 Renderer；
- 新用户默认使用“大字”（120%），已有选择保存在本机浏览器存储中并在下次启动恢复；
- 大字模式统一放大标题、正文、按钮、表单、Trace、代码字段与图片容器，而不是只修改少数标题；
- 桌面大屏继续使用现有受限阅读宽度，缩放后不得出现页面级横向溢出；
- 390px 窄屏保持现有响应式布局，不机械放大造成横向滚动；
- 桌面默认窗口从 1440×900 调整为更适合大屏审阅的 1600×1000，仍允许用户缩放、最大化和调整窗口。

## 非目标

- 不修改 Security Contract、Plan、Scan、Trace、Finding、Replay 或 Provider；
- 不增加系统级 DPI 探测、平台专用字体或复杂无障碍设置中心；
- 不逐个重写全部组件的局部 Typography；
- 不在移动端强制桌面缩放。

## 前后端与数据影响

- Web：新增本地显示偏好、顶部切换控件和全局界面缩放样式；
- Desktop：只调整主窗口默认尺寸，继续复用同一 Vue Renderer；
- API/Contracts/Data/Model/Tool：无；
- Storage：只保存非敏感的 `agent-audit.display-scale` 本机显示偏好。

## API 或交互契约

- 切换显示大小只写入 `localStorage`，不发起 GET/POST；
- 无已保存值时默认 `large`；保存值只接受 `standard` 或 `large`；
- 760px 以下不应用桌面整体缩放，但继续保留用户选择供回到桌面窗口时使用。

## 实施任务

- [x] 固定显示偏好与本地持久化契约；
- [x] 实现顶部标准/大字切换与全局缩放；
- [x] 调整桌面默认窗口尺寸；
- [x] 补充无请求、持久化、桌面可读性与窄屏无溢出测试；
- [x] 完成 typecheck/build、Playwright、Python 回归、桌面重编译和人工复核；
- [x] 更新状态并提交 Git。

## 验收标准

- [x] 首次打开默认显示“大字”，顶部明确显示当前选择；
- [x] 切换“标准 / 大字”立即改变完整界面比例，刷新后保持；
- [x] 切换过程中不新增 API、Provider、Scan 或 Replay 请求；
- [x] 1440/1920 桌面窗口中攻击链、结果数字、Replay 声明和技术详情可读性明显提升；
- [x] 390×844 无页面级横向溢出；
- [x] 桌面新窗口默认 1600×1000，仍可缩放和最大化；
- [x] 现有 Guided Scan→Finding→Replay 与全部工作区回归通过。

## 验证证据

- 测试命令：`npm run typecheck`；`npm run build`；`.venv\Scripts\python.exe -m pytest -q`；`npx playwright test --reporter=line`；指定 Desktop artifact smoke；`git diff --check`
- 结果：TypeScript 全工作区与 Contracts/Web production build 通过；Python `623 passed, 6 skipped`；Playwright `27 passed`；新 release Desktop artifact smoke `10 passed`；仅保留既有 Vite chunk 与 Starlette/httpx warning。
- 人工步骤：在 1920×1080 验证默认 120% 大字、主内容区实际宽度 1728px、导航文字实际高度约 21px、页面无横向溢出；在 1024×700 与 390×844 复核最小桌面/窄屏边界。

## 实施记录

- 2026-08-30：用户在最新版桌面截图中确认，窗口放大后攻击链节点、结果指标、技术详情和 Replay 声明仍偏小，并要求软件内可自行切换大小。
- 2026-08-30：完成顶部“标准 / 大字”切换、本机偏好持久化、默认 120% 大字和 1600×1000 桌面窗口；显示切换不触发任何业务请求。
