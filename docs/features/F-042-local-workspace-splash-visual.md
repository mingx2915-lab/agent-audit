# F-042 本地工作台启动视觉

- 状态：Completed
- 所属里程碑：M6 本地双平台产品化
- 负责人：主代理
- 相关决定：`docs/features/F-030-original-brand-and-splash.md`

## 用户价值

桌面应用启动时以清晰、克制且区别于攻击链的视觉语言表达“本地 Workspace 与审计环境正在建立”，利用现有启动页右侧空区增强完成度，同时保留真实启动状态与失败诊断。

## 范围

- 使用用户确认的原创透明工作台背景填充 Splash 右侧空区；
- 左侧继续保留现有 Logo、产品名、状态、进度和本地处理边界；
- 启动中对背景做轻量归位感，Ready 时短暂亮起，失败/停止时冻结并降亮；
- `prefers-reduced-motion` 下禁用背景运动；
- 保持 720×440 无边框窗口和现有 Sidecar 生命周期。

## 非目标

- 不修改 Logo；
- 不改变 Sidecar 启动、ready、failed 或 stopped 判定；
- 不用图片伪造启动阶段或成功状态；
- 不增加视频、GIF、持续网络资源或横向数据流；
- 不把 Splash 改成宣传海报。

## 前后端与数据影响

- Web Splash：新增一张本地 WebP，调整背景、层级与状态驱动动效；
- Desktop：本功能不改变窗口尺寸、Sidecar 或关闭流程；
- API、Contracts、Data/Model/Tool：无。

## 实施任务

- [x] ~~将确认图片压缩为 1440×880 WebP；~~
- [x] ~~接入 Splash 并保持左侧信息可读；~~
- [x] ~~增加 starting/ready/failed/stopped 与 reduced-motion 视觉边界；~~
- [x] ~~完成 typecheck、build、相关测试与 diff check；~~
- [x] ~~更新状态并提交 Git。~~

## 验收标准

- [x] ~~图片主要占据右侧，Logo、标题和启动状态不被遮挡；~~
- [x] ~~启动页不再复用攻击链横向数据流语言；~~
- [x] ~~starting、ready、failed、stopped 均由真实 runtime state 驱动；~~
- [x] ~~failed/stopped 保留可读错误和退出按钮；~~
- [x] ~~reduced-motion 下无背景移动；~~
- [x] ~~720×440 无裁切、溢出、黑框或白边；~~
- [x] ~~Web/Desktop typecheck、production build 与相关测试通过。~~

## 验证证据

- 测试命令：`.venv\Scripts\python.exe -m pytest tests/integration/test_brand_startup.py -q`；指定新 release EXE 后执行 `.venv\Scripts\python.exe -m pytest tests/integration/test_desktop_configuration.py -q`；`npm run typecheck`；`npm run build`；配置项目内 Rust 工具链后执行 `npm run desktop:build`；`git diff --check`
- 结果：品牌/启动集成测试 5 passed；新 release Desktop artifact 配置与启动 smoke 10 passed；Contracts/Web/Desktop TypeScript typecheck 通过；Contracts/Web production build 通过；Tauri release EXE 与 NSIS current-user 安装包重建成功；diff check 无 whitespace error。
- 人工步骤：在 720×440 实际视口打开 `splash.html`，确认右侧 Workspace 轮廓可见、左侧 Logo/标题/状态清晰，四周无白边、额外黑框或溢出；浏览器因没有 Tauri invoke 显示失败态，验证了失败诊断和退出动作仍可读，真实 Desktop 状态链未修改。

## 实施记录

图片只负责右侧透明工作台与空间层次；Logo、文字、进度、错误和真实状态全部保留为代码原生元素。

- 2026-08-30：用户确认透明工作台方向适合填补 Splash 右侧空区；最终资产机械压缩为 1440×880、45 KB WebP，不包含文字、品牌标识或横向攻击链。
- 2026-08-30：背景以一次性 900ms 轻量归位进入；Ready 只按真实状态提亮，failed/stopped 冻结并降亮，`prefers-reduced-motion` 下禁用背景动画。未延长 Ready、未修改 Sidecar 生命周期。
