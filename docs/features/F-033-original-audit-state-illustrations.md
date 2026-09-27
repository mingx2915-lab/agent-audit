# F-033 原创审计状态插画

- 状态：Completed
- 所属里程碑：M6 本地双平台产品化
- 负责人：主代理
- 相关决定：`docs/features/F-032-visual-hierarchy-and-human-copy.md`、`docs/features/F-030-original-brand-and-startup-experience.md`

## 用户价值

评委和企业用户无需阅读长段说明，也能从空态、运行态和 Replay 对照中快速看懂“审计链如何流动、风险在哪里、修复后在哪里被阻断”。

## 范围

- 依据 F-032 已确认的三份 brief 生成三张原创状态插画；
- 将 Contract Trace Path 用于尚未执行 Scan 的核心验收空态；
- 将 Evidence Pulse 用于 Scan 运行态；
- 将 Before / After Split 用于 Replay 结果摘要；
- 插画只辅助真实状态，Trace、Finding、Rule ID 与 Replay 数据继续作为结论依据；
- 保持 390×844 窄屏可用，不新增网络图片依赖。

## 非目标

- 不修改用户已确认的知盾 Logo、桌面图标或启动画面；
- 不制作 PPT、视频、海报或营销首页；
- 不模仿现有品牌、产品 Logo 或常见盾牌、锁、眼睛、漏洞虫等安全图标；
- 不在图片中嵌入结论、数值或产品文案；
- 不修改 API、Contracts、业务数据或 Finding 判定。

## 前后端与数据影响

- Web：新增三张本地位图资产，并按真实 UI 状态接入现有组件；
- API：无；
- Contracts：无；
- Data/Model/Tool：无；
- Desktop：复用 Web Renderer 与打包资源，不新增原生命令。

## API 或交互契约

- 首载不得因图片接入新增任何 API 请求；
- `loading`、`latestAttempt` 与 `replay` 仍是图片显示的唯一状态来源；
- 插画使用装饰性语义，不能遮挡按钮、状态文本或证据；
- 现有 `data-testid` 与业务操作保持不变。

## 实施任务

- [x] 生成 Contract Trace Path、Evidence Pulse、Before / After Split 三张原创插画；
- [x] 将最终图片复制到仓库并以稳定文件名登记；
- [x] 接入核心验收空态、Scan 运行态与 Replay 结果；
- [x] 完成 typecheck、production build、Playwright 与响应式人工审查；
- [x] 更新状态文档并提交 Git。

## 验收标准

- [x] 三张图片均为本次原创生成，不含现成 Logo、商标文字或常见安全品牌主图形；
- [x] 未执行、执行中、Replay 完成三个状态能明显区分；
- [x] 图片不取代真实 Finding、Trace 或 Replay 数据；
- [x] 1440px 与 390px 下不裁切关键路径、不产生横向溢出；
- [x] 页面首载和业务请求数量不因图片变化；
- [x] Web typecheck/build 与关键 E2E 通过。

## 验证证据

- 测试命令：`npm run typecheck`；`npm run build --workspace apps/web`；`npx playwright test --reporter=line`；`.venv\Scripts\python.exe -m pytest -q`；`git diff --check`
- 结果：根 TypeScript typecheck 通过；Web production build 通过（只有既有 chunk size warning）；13 个 Playwright E2E 通过；567 passed、2 skipped、1 个既有 Starlette deprecation warning；diff check 无 whitespace error
- 人工步骤：使用 Test-only Provider 与隔离 Workspace 在 1440×1000、390×844 复核空态、Guided Scan、Critical Finding 与同 Plan Replay；桌面和窄屏均无横向溢出，服务已停止。

## 实施记录

- 图片采用同一套米白画布、蓝色主链、珊瑚风险、薄荷修复视觉语言；不使用文字、人物、盾牌、锁、眼睛、漏洞虫、警告牌或现有品牌元素。
- 图像生成只产出视觉素材，不参与安全结论，最终判断仍来自 Security Contract 与真实 Trace。
- 生成方式为 text-to-image；三张图均使用 3:2 横向构图，并压缩为 1200×800 WebP。最终提示分别要求：Contract 路径在授权节点分出风险/阻断；Evidence Pulse 沿六节点点亮并捕获异常；Replay 使用上下两条同构链呈现风险到达与修复阻断。
- 最终资产为 `apps/web/src/assets/illustrations/contract-trace-path.webp`、`evidence-pulse.webp`、`replay-before-after.webp`，合计约 69 KB，无运行时联网依赖。
- 后续 F-039 根据实际用户反馈撤下了无法独立解释的 Contract Trace Path 空态插画，改为代码原生六节点预览；本记录保留 F-033 当时的实现事实。
