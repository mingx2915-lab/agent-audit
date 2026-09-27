# F-040 核心验收数据流氛围层

- 状态：Completed
- 所属里程碑：M6 本地双平台产品化
- 负责人：主代理
- 相关决定：`docs/features/F-039-readable-guided-chain-empty-state.md`

## 用户价值

用户在阅读六节点核心验收预览时，能够感受到数据沿审计链路流动，同时仍以代码原生节点为信息主体，不再出现大片单调深色空白。

## 范围

- 将用户确认的原创蓝色数据流图片作为六节点未运行预览的低强度背景；
- 图片只承担空间与流动氛围，不表达风险、通过或真实 Trace；
- 使用中低不透明度、轻量中心衰减与悬停增强，让背景明确可见且节点文字优先；
- 保持 1440px 与 390px 布局不溢出。

## 非目标

- 不替换六节点、不把图片当作证据；
- 不修改 Scan、Trace、Finding、Replay 或 Provider；
- 不把背景用于运行中或已有真实 Trace 的状态；
- 不增加持续动画、视频或运行时网络资源。

## 前后端与数据影响

- Web：新增一张本地 WebP 氛围资产，并只在 Guided Audit 未运行预览中渲染；
- API、Contracts、Desktop、Data/Model/Tool：无。

## 实施任务

- [x] 将确认图片转为适合客户端加载的 1600×640 WebP；
- [x] 接入六节点预览并控制视觉强度；
- [x] 完成 typecheck、build、关键 E2E 与 diff check；
- [x] 更新状态并提交 Git。

## 验收标准

- [x] 图片只在未运行六节点预览中出现；
- [x] 图片满幅、无黑框或白边，节点文字仍是第一视觉层；
- [x] 默认背景强度约 58%，节点使用半透明深蓝承载文字；悬停不超过约 68%，减少动态偏好时不增强；
- [x] 运行中和真实 Trace 状态保持不变；
- [x] 1440×1000 与 390×844 无横向溢出；
- [x] Web typecheck/build 与关键 E2E 通过。

## 验证证据

- `npm run typecheck --workspace @agent-audit/web`：通过；
- `npm run build --workspace @agent-audit/web`：通过，只有既有 Vite chunk-size warning；
- `npx playwright test tests/e2e/persisted_audit.spec.ts --reporter=line`：4 passed；锁定空态背景存在且无语义替代、真实 Trace 后背景移除，并覆盖 390×844、Provider 502 与快速双击；
- `git diff --check`：通过，仅有工作区既有 LF→CRLF 提示；
- 人工步骤：用户在本地页面确认增强后的背景强度“还行”。

## 实施记录

本功能使用用户本轮确认的原创数据流生成图，只作为代码节点背后的装饰层。语义、状态和验收结论继续由真实 Plan、Trace 与 Finding 提供。
