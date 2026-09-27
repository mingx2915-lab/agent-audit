# F-041 Replay Before/After 同构状态视觉

- 状态：Completed
- 所属里程碑：M6 本地双平台产品化
- 负责人：主代理
- 相关决定：`docs/features/F-037-remediation-advisory-boundary.md`、`docs/features/F-038-provider-readiness-state-visual.md`

## 用户价值

用户可以一眼理解同一攻击在修复参考前发生阻塞风险、模拟复测后恢复畅通的状态变化，同时仍以真实 Before/After Trace、Finding 和 Replay 结论作为判断依据。

## 范围

- 生成一组相同构图、相同节点位置的原创 Replay 状态背景；
- Before 使用蓝色链路与局部红色阻塞，After 使用相同链路恢复为蓝绿畅通；
- Replay 成功时做一次短交叉淡入；Replay 未通过时保留 Before 风险状态；
- `prefers-reduced-motion` 下停用切换动效；
- 图片只作为结果标题区的辅助状态视觉，不替代实际 Trace。

## 非目标

- 不修改 Replay 执行、secure Profile、Finding、Contract 或修复建议；
- 不用绿色图片冒充失败 Replay 已修复；
- 不增加视频、循环动画或运行时网络资源；
- 不在图片中放文字、图标、品牌标识或具体企业系统。

## 前后端与数据影响

- Web：替换既有 Replay 装饰图为两张同构本地 WebP，并根据真实 Replay status 控制状态与一次性切换；
- API、Contracts、Desktop、Data/Model/Tool：无。

## 实施任务

- [x] 生成并审查同构 Before/After 原创图片；
- [x] 压缩为本地 WebP 并接入 Replay 结果；
- [x] 锁定成功/失败状态与 reduced-motion 边界；
- [x] 完成 typecheck、build、关键 E2E 与 diff check；
- [x] 更新状态并提交 Git。

## 验收标准

- [x] 两张图构图一致，只有阻塞/畅通状态不同；
- [x] Before 明确表现蓝色链路的局部红色阻塞，不是全屏红色；
- [x] After 同一位置恢复为蓝绿畅通，不残留红色风险语义；
- [x] 只有真实 passed Replay 才切换到 After，failed 保持 Before；
- [x] 动效短、只执行一次，reduced-motion 下停用；
- [x] 图片不含文字/Logo，不替代真实 Before/After 证据；
- [x] 1440×1000 与 390×844 无横向溢出；
- [x] Web typecheck/build 与关键 E2E 通过。

## 验证证据

- `npm run typecheck --workspace @agent-audit/web`：通过；
- `npm run build --workspace @agent-audit/web`：通过，只有既有 Vite chunk-size warning；
- `npx playwright test tests/e2e/persisted_audit.spec.ts --reporter=line`：4 passed；锁定真实 passed Replay 的状态类与两张无语义替代图片，并继续覆盖真实 Scan/Finding/Replay、390×844、Provider 502 与快速双击；
- `git diff --check`：通过，仅有工作区既有 LF→CRLF 提示；
- 人工步骤：用户逐次审查 Before 构图，最终要求落实为梗阻前移、左向红色粒子拖尾、下游结构保留 35%–45% 冷蓝轮廓；After 从同一修正版生成。

## 实施记录

图片以同一底图连续编辑生成，避免两张独立概念图在节点位置、镜头和节奏上漂移。既有 `replay-before-after.webp` 已由两张可独立控制状态的 WebP 替换。
