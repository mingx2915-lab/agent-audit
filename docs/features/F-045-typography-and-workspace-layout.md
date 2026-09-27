# F-045 统一 Typography 与关键工作区宽屏重构

- 状态：Completed
- 所属里程碑：M6 本地双平台产品化
- 负责人：主代理统筹；3 个 Luna Max 分别负责设计系统、Plan 工作区、身份差分工作区
- 相关决定：`docs/UI_CONTENT_LAYOUT_ART_AUDIT.md`、`docs/features/F-032-reviewer-focused-visual-hierarchy.md`

## 用户价值

让评委和普通企业用户在 1440p、1080p 与更大桌面窗口中能迅速看清标题、任务、证据和主操作，不再面对字号零散、工程字段过小、卡片过密、按钮错位和大屏只增加空白的问题。

## 范围

- 为 Web 建立统一的 Display、H1、H2、H3、Body、Body small、Label、Code Typography tokens，并在 1024–1439、1440–1919、≥1920 三档桌面宽度有受限缩放；
- 建立普通阅读区与证据宽数据区的统一宽屏容器、区块间距、标题起点和文字行长规则；
- 将“可执行测试计划”从三列全量长卡改为 Plan 列表 + 选中详情，默认优先显示业务验证目标，技术字段进入详情；
- Plan 主操作位置稳定；未执行的 Plan 不显示 Replay，已产生相同 Plan 的真实 Scan 后才在结果上下文显示次级 Replay；
- 重排“身份差分验收”：任务与 Profile 作为清晰双字段，主按钮贴近标题/任务，默认摘要只展示验证目标、Actor 数、Target 与类别；
- 保留所有现有 API、AttackPlan、Differential、Scan、Finding、Replay 与 Test-only Provider 行为，不复制后端判定到 Web；
- 补充 1440×900、1920×1080、2560×1440 与 390×844 的布局回归，覆盖长短 Plan 内容和按钮基线。

## 非目标

- 不在本功能重做核心首页、Provider Setup、资料导入、完整 History、Contract Editor 或所有 Evidence 子工具；
- 不修改 API、Contracts、Security Contract、Plan 生成、Finding、Replay 或模型调用；
- 不增加新图片、图表库、运行时网络素材或宣传性动效；
- 不把所有文字机械放大，不让正文无限随视口增长；
- 不用固定卡片高度截断 Rule、错误、风险结论或证据。

## 前后端与数据影响

- Web：新增语义化 Typography/宽屏 tokens；新增 Plan 列表详情与身份差分任务组件；调整 `App.vue` 接线和相关样式；
- API：无；
- Contracts：无；继续使用现有 `AttackPlan`、`DifferentialTask`、`DifferentialAuditResult`；
- Desktop：复用同一 Vue Renderer，无原生生命周期变化；
- Data/Model/Tool：无。

## API 或交互契约

- 页面首载仍只读取现有数据，不增加自动 Scan、Replay、Differential 或 Provider 调用；
- Plan 列表选择只改变本地选中详情，不触发 API；“执行”继续调用现有 Plan execute；
- Replay 入口只在当前已有真实 Scan 且 `scan.planId` 与选中 Plan 一致时出现，继续调用现有 Replay API；
- Differential 的 Task/Profile 变化只更新本地选择并清空陈旧结果，只有用户点击“运行对比”才调用现有 Differential API；
- 技术详情必须可访问，不能因默认收起而删除 Plan ID、Rule、Profile、Message、Expected categories 或 Trace 证据。

## 实施任务

- [x] 建立统一 Typography、文字颜色、行高、容器和宽屏 tokens；
- [x] 实现 Plan 列表 + 选中详情，移除三列长卡与残行；
- [x] 固定 Plan 操作基线，并把 Replay 收敛为满足真实前置条件后的次操作；
- [x] 重排身份差分任务/Profile/主操作/摘要和未运行状态；
- [x] 主代理完成两个组件接线、文案裁决与 scoped diff 审查；
- [x] 补充长短 Plan、无自动请求、Replay 前置条件、宽屏与 390px E2E；
- [x] 完成 Web typecheck/build、相关 Playwright、Python 回归与 diff check；
- [x] 更新状态并提交 Git。

## 验收标准

- [x] H1/H2/H3/Body/Label/Code 使用统一 token；正式可读文字不再以 8–10px 显示；
- [x] 1440、1920、2560 宽度下标题和正文按规格受限增大，正文行长和工作区宽度不无限拉伸；
- [x] Plan 数量为 4 时不出现下一行仅一张卡和右侧大片空白；
- [x] Plan 描述为 1、3、8 行时，列表主操作保持同一列/基线，详情不截断真实字段；
- [x] 未执行 Plan 不显示 Replay；相同 Plan 的真实 Scan 完成后才显示 Replay 次操作；
- [x] 身份差分默认一屏可见任务、Profile、业务验证目标、Actor 数和主按钮；未运行空态不占半屏；
- [x] 390×844 无页面级横向溢出；键盘可以选择 Plan、展开详情并触发操作；
- [x] 现有 Guided Scan→Finding→Replay、Provider 502、Contract/Document/Acceptance 主回归不受影响；
- [x] Web typecheck/build、相关 Playwright、Python 回归与 diff check 通过。

## 验证证据

- 测试命令：`npm run typecheck`；`npm run build`；`.venv\Scripts\python.exe -m pytest -q`；`npx playwright test --reporter=dot`；`git diff --check`
- 结果：TypeScript 全工作区通过；Contracts/Web production build 通过（仅保留既有 chunk size warning）；Python `623 passed, 6 skipped`；Playwright `23 passed`；diff check 通过。
- 人工步骤：主代理使用 Test-only Provider 在 1920×1080 检查 Display/H2 实际为 56px/29px、Plan 四个执行按钮同列、列表与详情信息层级；在 390×844 检查主标题、固定 Case 和页面级横向溢出；1440、1920、2560 与 390 四档同时由 E2E 锁定。

## 实施记录

- 2026-08-30：用户在大屏截图中指出同级标题、正文与工程字段字号不统一，窗口放大后文字仍偏小；Plan 卡主按钮与 Replay 因内容长度不同而明显上下错位。
- 2026-08-30：主代理确认源码大量使用 8–12px 固定字号，主样式只有窄屏断点；本功能只处理设计系统和两个明确问题区，不顺手重写全站。
- 2026-08-30：三个 Luna Max 分别完成 Typography/宽屏 tokens、Plan 列表详情和身份差分工作区；主代理完成接线、删除旧模板、修正 Display token、真实浏览器复核和全量回归。
