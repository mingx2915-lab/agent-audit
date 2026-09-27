# F-044 扫描运行中 Evidence Pulse 视觉

- 状态：Completed
- 所属里程碑：M6 本地双平台产品化
- 负责人：主代理
- 相关决定：`docs/features/F-032-reviewer-focused-visual-hierarchy.md`、`docs/features/F-039-readable-guided-audit-chain.md`

## 用户价值

在 Guided Audit 扫描真正运行时，让用户一眼理解软件正在沿 Retrieval、Authorization、Tool 与 Sink 链路采集证据，而不是已经作出通过或失败判断。

## 范围

- 替换 Guided Audit 现有运行态插图，生成一张本地原创宽幅 Evidence Pulse 视觉；
- 多条 Evidence Blue 数据流通过四个形状明确不同的审计模块，分别对应 Retrieval、Authorization、Tool 与 Sink；
- 只在一条路径上使用紧凑的 Warning Amber 扫描脉冲，不使用红色、绿色或阻塞形状；
- 在真实 Scan 请求的 loading 期间显示，并使用低频 CSS 扫光；
- `prefers-reduced-motion` 下停止动画，仍保留静态证据采集语义。

## 非目标

- 不修改 Scan、Trace、Finding、Replay、API 或模型调用；
- 不用图片表示 passed、failed、阻断或放行；
- 不把图片当作真实 Trace 或验收证据；
- 不绘制文字、Logo、盾牌、锁、警告三角形、火箭或飞船；
- 不增加 GIF、视频、运行时网络资源或高频循环动画。

## 前后端与数据影响

- Web：替换一张本地 WebP，调整 Guided Audit loading 展示与扫光；
- API、Contracts、Desktop、Data/Model/Tool：无。

## 实施任务

- [x] ~~生成并确认原创 Evidence Pulse 宽幅底图；~~
- [x] ~~压缩为本地 WebP 并替换运行态插图；~~
- [x] ~~完成 loading-only 扫光、reduced-motion 与窄屏适配；~~
- [x] ~~补充 E2E 运行态可见边界；~~
- [x] ~~完成 typecheck、build、E2E 与 diff check；~~
- [x] ~~更新状态并提交 Git。~~

## 验收标准

- [x] ~~画面可读为多条蓝色数据流正在经过四个审计阶段；~~
- [x] ~~琥珀色只是移动扫描脉冲，不呈现阻塞、失败或通过；~~
- [x] ~~只在真实 Scan loading 期间显示，请求结束后移除；~~
- [x] ~~快速双击仍只发送一次 Scan，视觉不改变业务状态；~~
- [x] ~~390×844 与桌面宽度无横向溢出或关键裁切；~~
- [x] ~~Web typecheck/build、相关 E2E 与 diff check 通过。~~

## 验证证据

- 测试命令：`npm run typecheck --workspace @agent-audit/web`；`npm run build --workspace @agent-audit/web`；`npx playwright test tests/e2e/persisted_audit.spec.ts --reporter=line`；`git diff --check`
- 结果：Web typecheck/build 通过；Guided 核心路径 4 passed，覆盖请求前不显示、请求期间显示、请求后移除、快速双击单请求、390×844、Finding/Replay 和 Provider 502 恢复；diff check 无 whitespace error。
- 素材：内置 imagegen 生成原始 PNG，机械裁切压缩为 1600×615、122.5 KB WebP；运行时无网络依赖。

## 实施记录

- 2026-08-30：用户要求替换普通运行态插图，固定语义为“正在采集证据”，不得表示最终结论。
- 2026-08-30：用户指出首版琥珀脉冲不明显；二版将脉冲扩大并提亮，但保留蓝色数据流连续穿过，避免被误解为阻塞。
- 2026-08-30：CSS 只在 loading 图层上执行 3.8 秒低频琥珀扫光，`prefers-reduced-motion` 下停用。
