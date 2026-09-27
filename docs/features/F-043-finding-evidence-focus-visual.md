# F-043 Finding 风险证据聚焦视觉

- 状态：Completed
- 所属里程碑：M6 本地双平台产品化
- 负责人：主代理
- 相关决定：`docs/features/F-032-reviewer-focused-visual-hierarchy.md`、`docs/features/F-039-readable-guided-audit-chain.md`

## 用户价值

在 Critical Finding 出现时，用一张克制但有冲击力的原创视觉把评委注意力引向“Trace 在具体证据位置发生违规”，同时继续由代码显示真实 Severity、Rule 和 Evidence sequence，避免把装饰图误当成安全结论。

## 范围

- 为 Guided Audit 的 Critical Finding 标题区域生成并接入一张本地原创宽幅视觉；
- 多束 Evidence Blue Trace 在画面中汇聚到一个紧凑的 Risk Coral 断点；
- 红色只集中于违规证据位置，周围使用短促证据脉冲和定位线；
- 仅在存在真实 Critical Finding 时显示，不用于 passed、未运行或无 Finding 状态；
- 实际 Rule、Evidence sequence、Severity、标题和摘要继续由代码显示。

## 非目标

- 不修改 Finding 判定、Severity、Rule 或 Evidence；
- 不把图片当作 Trace、证据或根因结论；
- 不绘制盾牌、锁、警告三角形、机器人、六边形徽章或文字；
- 不增加视频、GIF、运行时网络资源或持续高频动画；
- 不改 Replay、Provider Readiness 或启动页视觉。

## 前后端与数据影响

- Web：新增一张本地 WebP，并在真实 Critical Finding 卡片标题区按状态显示；
- API、Contracts、Desktop、Data/Model/Tool：无。

## 实施任务

- [x] ~~生成并确认原创 Finding Evidence Focus 宽幅底图；~~
- [x] ~~压缩为项目本地 WebP 并接入 Critical Finding 标题区；~~
- [x] ~~保持真实 Severity、Rule、Evidence 和窄屏可读性；~~
- [x] ~~完成 typecheck、build、核心 E2E 与 diff check；~~
- [x] ~~更新状态并提交 Git。~~

## 验收标准

- [x] ~~蓝色 Trace 明确汇聚到单一珊瑚红证据断点，红色不扩散成整幅风险背景；~~
- [x] ~~图中无文字、Logo、盾牌、锁、警告三角形或常见安全品牌符号；~~
- [x] ~~只有真实 Critical Finding 显示视觉，passed/无 Finding 不显示；~~
- [x] ~~Rule、Evidence sequence、Severity 与 Finding 标题仍来自真实 DTO；~~
- [x] ~~1440 桌面与 390×844 无关键内容裁切和横向溢出；~~
- [x] ~~Web typecheck/build、相关 E2E 与 diff check 通过。~~

## 验证证据

- 测试命令：`npm run typecheck --workspace @agent-audit/web`；`npm run build --workspace @agent-audit/web`；`npx playwright test tests/e2e/persisted_audit.spec.ts --reporter=line`；`git diff --check`
- 结果：Web typecheck/build 通过；Guided 核心路径 4 passed，覆盖真实 Critical Finding、同 Plan Replay、Provider 502 恢复、快速双击单请求与 390×844 无页面溢出；diff check 无 whitespace error。
- 人工步骤：用户确认降低黑色面积后的第二版；最终机械裁切为 1600×640、48.9 KB WebP。标题区左侧深色遮罩保证 Severity/Finding ID/标题可读，珊瑚红断点保留在右侧证据聚焦位置。

## 实施记录

图片只承担“证据在这里发生断裂”的注意力引导；任何 Finding 事实仍必须由 Security Contract 与真实 Trace 产生。

- 2026-08-30：首版暗部过多，用户要求减少黑色；第二版仅抬高深海军蓝层次并增加低强度网格/粒子，未改变 Trace 汇聚与红色断点位置。
- 2026-08-30：最终只在 `finding.severity === "critical"` 时渲染；High、passed、未运行和无 Finding 状态不使用该视觉。
