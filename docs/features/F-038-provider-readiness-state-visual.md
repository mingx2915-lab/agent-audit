# F-038 Provider Readiness 状态视觉

- 状态：Completed
- 所属里程碑：M6 本地双平台产品化
- 负责人：主代理
- 相关决定：`docs/features/F-032-visual-hierarchy-and-human-copy.md`、`docs/features/F-033-original-audit-state-illustrations.md`、`docs/features/F-034-provider-setup-layout-compression.md`

## 用户价值

用户在不阅读四项技术探针细节时，也能一眼区分候选 AI 链路“尚未打通”与“已通过 Readiness”；详细结论仍由真实探针数据支撑。

## 范围

- 新增同一构图的红色阻塞、绿色畅通两张原创本地状态图；
- 将状态图接入候选模型 Readiness 区，不改变现有连接、探针与保存流程；
- `ready` 时显示绿色畅通图，未检查、检查中、`partial`、`unavailable` 或错误时显示红色未就绪图；
- 状态变化时执行短时间淡入和能量扫过动效，`prefers-reduced-motion` 下取消动画；
- 保持 390px 窄屏不溢出，不增加运行时网络图片依赖。

## 非目标

- 不修改 Provider Readiness 判定、探针或保存条件；
- 不用图片取代四项探针、错误文本或 Plan compatibility；
- 不把未检查冒充成已证明的 Provider 故障；
- 不修改 API、Contracts、Desktop 原生层、Security Contract、Finding 或 Replay。

## 前后端与数据影响

- Web：新增两张本地 WebP，在 `ProviderSetupView` 中按现有 `readinessResult`、`readinessLoading`和错误状态投影；
- API：无；
- Contracts：无；
- Data/Model/Tool：无；
- Desktop：随 Web Renderer 打包，不新增原生命令。

## API 或交互契约

- 首载、刷新和状态切换不增加任何 HTTP 请求；
- 绿色图的唯一数据条件为 `readinessResult.status === "ready"`；
- 其他状态仅表示“候选链路尚未就绪”，不表示确定的故障根因；
- 原有 `data-testid`、按钮、探针列表和错误语义保持不变。

## 实施任务

- [x] 压缩并登记红/绿两张原创状态资产；
- [x] 在候选 Readiness 区接入真实状态投影；
- [x] 增加短切换动画及 reduced-motion 边界；
- [x] 补充关键 E2E 断言并完成响应式审查；
- [x] 完成 typecheck、build、E2E 和 diff check。

## 验收标准

- [x] 未检查或未就绪时不显示绿色畅通结论；
- [x] 真实候选 Readiness 返回 `ready` 后，同一位置切换为绿色畅通图；
- [x] 切换不触发额外 API 请求，不改变保存条件；
- [x] 红/绿图不遮挡四项探针、错误或主操作；
- [x] 1440px 与 390px 不出现横向溢出或关键内容裁切；
- [x] Web typecheck/build 与 Provider Setup E2E 通过。

## 验证证据

- `npm run typecheck --workspace @agent-audit/web`：通过；
- `npm run build --workspace @agent-audit/web`：通过，只有既有 Vite chunk-size warning；
- `npx playwright test tests/e2e/provider_setup.spec.ts --reporter=line`：5 passed；
- `git diff --check`：通过，仅有工作区既有 LF→CRLF 提示；
- 人工复核：本地 Test-only Provider 页面中，初始红色阻塞图与 `ready` 后绿色畅通图均在同一位置完整显示；1440×1000 与 390×844 E2E 无横向溢出，普通桌面窗口实际检查无额外图片边框或关键裁切。

## 实施记录

- 两张图由同一原创构图生成：红色版以局部阻塞和下游熄灭表示未打通，绿色版仅点亮后两个模块表示已畅通；图片不含文字、商标、盾牌、锁或现成安全品牌图形。
- 状态切换采用约半秒交叉淡入与一次性光扫；检查中只有短蓝色扫光，`prefers-reduced-motion` 下全部静止。
