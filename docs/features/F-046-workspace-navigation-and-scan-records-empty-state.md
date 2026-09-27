# F-046 工作区导航与扫描记录空态收敛

- 状态：Completed
- 所属里程碑：M6 本地双平台产品化
- 负责人：主代理
- 相关决定：`docs/UI_CONTENT_LAYOUT_ART_AUDIT.md`、`docs/features/F-032-visual-hierarchy-and-human-copy.md`、`docs/features/F-045-typography-and-workspace-layout.md`

## 用户价值

让首次用户和评委从导航名称就能理解任务顺序，并让尚未产生 Scan 的页面看起来是“可以开始的工作区”，而不是两个巨大的未完成空卡。用户应能从空态直接回到核心验收，不需要理解 Audit Setup、Live Audit 或 History 等内部术语。

## 范围

- 将四个顶层工作区名称统一为“核心验收、设置与计划、扫描记录、验收证据”；
- 保留必要的 Scan、Trace、Finding、Replay 技术词，但不再让英文内部工作区名承担导航；
- 将无当前 Scan 且无历史记录时的“攻击过程空卡 + History 箱子空卡”合并为一个代码原生任务空态；
- 空态明确说明会保存 Attempt、Trace 与 Finding，并提供“去核心验收”主操作和刷新记录次操作；
- 有真实 Scan 或历史时继续显示现有完整过程、Attempt、Trace、Finding 与历史恢复能力；
- 保持页面首载只读，不新增 Scan、Replay、Provider 或模型调用；
- 覆盖 1440×900、1920×1080 和 390×844 的视觉与交互回归。

## 非目标

- 不修改 Scan/History API、SQLite、Provider、Security Contract、Finding 或 Replay；
- 不重构有数据时的 Attempt/Trace 详情；
- 不在本功能拆分整个“验收证据”页；
- 不增加新的位图、插画、图标库或联网素材；
- 不把空态伪装成已有结果，不显示 0 Finding/0 Trace 作为运行结论。

## 前后端与数据影响

- Web：调整 `App.vue` 顶层导航、扫描记录页条件渲染和 scoped/global 样式；
- API/Contracts/Desktop/Data/Model/Tool：无；桌面端复用同一 Vue Renderer；
- Tests：增加导航命名、首载无 POST、单一空态、CTA、历史恢复与窄屏无溢出 E2E。

## API 或交互契约

- 首载仍执行当前 GET 请求，不因空态新增任何 POST；
- “去核心验收”只切换本地工作区，不自动启动 Scan；
- “刷新记录”继续调用现有 `GET /api/scans?limit=20`；
- 有当前 `redTeamScan` 时继续展示现有攻击过程；有 `scanHistory` 时继续展示现有历史列表；
- 现有 `workspace-live`、`scan-history` 等关键测试标识保持稳定，新增标识只服务统一空态。

## 实施任务

- [x] 统一四个工作区中文名称与副标；
- [x] 实现扫描记录页单一代码原生空态与 CTA；
- [x] 保留加载、错误、当前 Scan 和历史记录的真实状态分支；
- [x] 补充无自动 POST、CTA、刷新和响应式 E2E；
- [x] 完成主代理实际浏览器复核、typecheck/build、Playwright、Python 回归和 diff check；
- [x] 更新状态并提交 Git。

## 验收标准

- [x] 顶层导航按任务顺序显示“核心验收 → 设置与计划 → 扫描记录 → 验收证据”；
- [x] 空 Workspace 的扫描记录页只出现一个主空态，不出现 Element Plus 箱子插图或两个大型空白面板；
- [x] 空态主按钮能回到核心验收，但不自动发起 Scan；
- [x] 刷新记录只执行历史 GET，不触发 Provider、Scan 或 Replay POST；
- [x] 存在 Scan/History 时原有过程与恢复能力不丢失；
- [x] 1440/1920 下空态一屏完整可见，390×844 无页面级横向溢出；
- [x] 现有 Guided Scan→Finding→Replay、History、Provider 错误与验收证据 E2E 不受影响；
- [x] Web typecheck/build、Playwright、Python 回归与 diff check 通过。

## 验证证据

- `npm run typecheck`：Contracts、Web、Desktop 全部通过；
- `npm run build`：Contracts 与 Web 生产构建通过；仅保留既有 Vite chunk size warning；
- `.venv\Scripts\python.exe -m pytest -q`：623 passed、6 skipped、1 个既有 Starlette/httpx deprecation warning；
- `npx playwright test --reporter=line`：25 passed，包含新增单一空态、无 POST、只读刷新、CTA、390×844 无横向溢出，以及既有真实 Scan→Finding→Replay、History、Provider、Contract、Acceptance 和 Workspace 回归；
- 主代理使用 Test-only Provider 在 1440×1000、1920×1080 与 390×844 实际复核：导航名称一致；空态一屏可见；1920 标题为 29px、内容宽度受 1680px 上限约束；390 页面 `scrollWidth` 不超过 viewport；
- `git diff --check`：通过。

## 实施记录

- 2026-08-30：主代理实际检查 1440×1000 页面，确认“完整审计”同时渲染“等待启动一次 Scan”和带通用箱子插图的“暂无已保存 Scan”，空白高度接近一整屏；导航又混用中文任务名与 Audit 内部术语。
- 2026-08-30：完成四工作区任务命名、单一扫描记录空态与代码原生 Scan→Attempt→Trace→Finding 提示链；有真实 Scan/History 时继续使用原有后端工件和恢复流程。
