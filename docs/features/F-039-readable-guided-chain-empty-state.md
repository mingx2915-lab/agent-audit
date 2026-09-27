# F-039 核心验收空态可读链路

- 状态：Completed
- 所属里程碑：M6 本地双平台产品化
- 负责人：主代理
- 相关决定：`docs/features/F-021-judge-guided-workspace.md`、`docs/features/F-033-original-audit-state-illustrations.md`、`docs/features/F-038-provider-readiness-state-visual.md`

## 用户价值

用户在尚未运行核心验收时，可以直接读懂将要验证的 Actor → Source → Resource → Authorization → Tool → Sink 六个环节，不需要猜一张装饰插画代表什么。

## 范围

- 删除核心验收未运行状态使用的 Contract Trace Path 装饰插画；
- 使用代码原生的六节点预览替代，显示每个节点的人话含义；
- 只对来自当前 Plan 的 Actor、Rule 和 Target 显示实际值，其余节点明确等待真实 Trace；
- Scan 运行中继续使用既有 Evidence Pulse，执行完成继续显示真实 Trace 节点；
- 保持 1440px 与 390px 可读且无横向溢出。

## 非目标

- 不修改 Scan、Planner、Trace、Finding、Replay 或 Provider；
- 不为未执行节点伪造 Source、Resource 或 Tool；
- 不重做运行态或 Replay 插画；
- 不增加 API、Contracts、数据或模型调用。

## 前后端与数据影响

- Web：`GuidedAuditFlow` 未运行空态改为结构化六节点列表，并移除未使用图片资产；
- API、Contracts、Desktop、Data/Model/Tool：无。

## 实施任务

- [x] 登记功能并锁定空态事实边界；
- [x] 用六节点代码原生预览替换装饰插画；
- [x] 删除不再使用的 Contract Trace Path 资产；
- [x] 补充 E2E 并完成 typecheck/build/diff check；
- [x] 更新状态并提交 Git。

## 验收标准

- [x] 未运行时可见六个节点及各自人话含义；
- [x] Actor、Rule、Target 只来自当前 Plan，其他节点明确写为“等待 Trace”；
- [x] 未运行空态不显示图片，不冒充真实 Trace；
- [x] 运行中和运行后原有状态不变；
- [x] 1440×1000 与 390×844 无横向溢出；
- [x] Web typecheck/build 与关键 E2E 通过。

## 验证证据

- `npm run typecheck --workspace @agent-audit/web`：通过；
- `npm run build --workspace @agent-audit/web`：通过，只有既有 Vite chunk-size warning；
- `npx playwright test tests/e2e/persisted_audit.spec.ts --reporter=line`：4 passed；覆盖未运行六节点空态、真实 Scan/Finding/Replay、390×844、Provider 502 与快速双击；
- `git diff --check`：通过，仅有工作区既有 LF→CRLF 提示；
- 删除 `contract-trace-path.webp` 18,382 bytes；运行态 `evidence-pulse.webp` 与 Replay `replay-before-after.webp` 保持不变。
