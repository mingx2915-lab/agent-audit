# F-049 验收证据空态与运行范围视觉层级

- 状态：Completed
- 所属里程碑：M6
- 负责人：主代理
- 相关审计：`docs/UI_CONTENT_LAYOUT_ART_AUDIT.md`

## 用户价值

让评委和首次用户在尚无 Acceptance Run 时也能立即看懂“一次完整验收会检查什么、应该点击哪里、运行后会留下什么”，避免用两张横跨页面的大白卡重复表达空状态。

## 范围

- 将 Acceptance 页首改为“价值主张 + 固定验收范围”的两栏结构；
- 以代码原生流程展示固定 24 Case、5 项 Gate、2 组身份差分和同 Plan Replay，明确它们是运行范围而非已通过结果；
- 只保留“开始验收”为实心主操作，“刷新历史”为次级操作；
- 将零历史状态压缩为紧凑的结果入口，说明运行后保存的结论、Finding、Replay 与证据文件；
- 在应用最底层青色画布使用右侧加权的本地证据网络底纹，贯穿各工作区的卡片间隙与长页面；页首证据汇聚图仍作为独立主视觉；
- 将全局中性白色 Surface 统一为高透明度玻璃白，让底纹在所有普通卡片中轻微可见；实心主操作与风险/状态色保持原有不透明语义；
- 保持已有 Acceptance API、历史、详情、对比和下载行为不变；
- 保持 390px 窄屏可用，并尊重全局标准/大字显示模式。

## 非目标

- 不新增模型调用、验收步骤、指标或判定，不使用与审计语义无关的宣传插图；
- 不把固定运行范围显示成实际结果；
- 不修改 Acceptance Runner、DTO、SQLite、导出或历史语义；
- 不重构已有运行后详情页。

## 前后端与数据影响

- Web：修改 `AcceptanceRunsView.vue` 的页首、空历史模板与样式，并增加两张原创本地 WebP 视觉资产；
- Tests：补充页首范围、空态密度、主次按钮和窄屏无溢出验收；
- API、Contracts、Desktop lifecycle、数据：无影响。

## 验收标准

- [x] ~~1920 宽屏下页首右侧有明确的固定验收范围，不再是按钮旁的大块无意义空白；~~
- [x] ~~固定范围显示 24 Case、5 Gate、2 Differential、1 Replay，且明确标注为“运行范围”而非当前状态；~~
- [x] ~~“开始验收”是页首唯一实心主按钮，刷新保持次级；~~
- [x] ~~零历史状态不保留运行后列表所需的大卡高度，并说明将保存的四类结果；~~
- [x] ~~首载、刷新、选择历史仍不 POST，只有显式点击开始才运行；~~
- [x] ~~390×844 无横向溢出，按钮与范围信息可读；~~
- [x] ~~Web typecheck/build、Acceptance E2E、全量回归和 Desktop artifact smoke 通过。~~

## 实施任务

- [x] ~~重排页首与固定验收范围；~~
- [x] ~~收敛历史空态；~~
- [x] ~~增加自动化视觉结构与交互边界验收；~~
- [x] ~~完成全量验证、桌面重编译与文档收口。~~

## 验证证据

- 新增 1600px、27.7 KB 页首证据汇聚图；图中 24 点矩阵、5 道 Gate、身份对比与 Replay 环在右侧汇入本地记录，不使用结果色或安全品牌常见符号；
- 新增 1536×1024、48.4 KB 整页证据网络底纹；它只挂在应用 `.app-shell` 最底层青色画布，不属于任何组件或卡片，右侧节点密集而左侧保持安静阅读区；
- 1920 宽屏自动验收锁定右侧布局、背景资产、空历史高度与主次按钮；390×844 锁定范围可读和无横向溢出；
- `npm run typecheck --workspace @agent-audit/web`、`npm run build --workspace @agent-audit/web`：通过，build 仅有既有 chunk-size warning；
- `npx playwright test tests/e2e/acceptance_runs.spec.ts --reporter=line`：2 passed；全量 Playwright：28 passed；
- `.venv\\Scripts\\python.exe -m pytest -q`：623 passed、6 skipped、1 个既有 Starlette/httpx warning；
- `compileall apps/api/src tests`、`git diff --check`：通过；
- Desktop release artifact：`.tools/cargo-target-release-f049/release/agent-audit-desktop.exe`；NSIS：`.tools/cargo-target-release-f049/release/bundle/nsis/知盾 AgentAudit_0.1.0_x64-setup.exe`；
- `AGENT_AUDIT_DESKTOP_ARTIFACT=... test_desktop_configuration.py -q`：10 passed；最终 release 已真实启动，Desktop PID 51124 与其 Sidecar 均来自 F-049 独立构建目录。
