# F-048 核心任务视觉优先级

- 状态：Completed
- 所属里程碑：M6 本地双平台产品化
- 负责人：主代理
- 相关决定：`docs/UI_CONTENT_LAYOUT_ART_AUDIT.md`、`docs/features/F-045-typography-and-workspace-layout.md`、`docs/features/F-047-display-scale-and-desktop-canvas.md`

## 用户价值

让用户进入核心首页后先看到并理解“运行核心验收”，而不是把模型连接、资料准备、Workspace 状态和核心验收都误读成同等级的大卡片。

## 范围

- 建立核心首页的三级视觉优先级：核心验收为唯一主舞台，模型/资料为准备步骤，工程状态为辅助信息；
- 把空闲状态的资料导入区收敛为更窄、更浅、更低的准备栏，去掉大面积空白和重阴影；
- 精简资料区重复的标题、英文计数与 Workspace 文案，保留用户仍能理解的资料数量和索引状态；
- 资料区展开后恢复适合表单与授权预览的工作宽度，不压缩真实导入流程；
- 保持核心验收的深色主舞台、主标题和唯一实心主操作，使其明显高于资料准备入口；
- 补充宽屏层级、紧凑高度、主次按钮和 390px 无溢出回归。

## 非目标

- 不把 Provider、Document Import、Guided Audit 改成同宽同重的统一卡片；
- 不修改资料解析、权限 Preview、Workspace、Retriever、Plan、Scan、Finding 或 Replay；
- 不增加图片、图标库、装饰性动画或新的顶层页面；
- 不在本功能重排完整 Provider Setup 或高级证据页。

## 前后端与数据影响

- Web：只调整 `DocumentImportView` 空闲摘要的文案、宽度、密度、按钮层级和响应式样式；
- API / Contracts / Desktop / Data / Model / Tool：无。

## API 或交互契约

- 页面首载仍只读取当前资料目录，不新增 Preview、Commit、Provider、Scan 或 Replay 请求；
- “添加 / 管理资料”仍只展开现有导入工作区；
- 收起态使用次级按钮，核心验收继续保留页面唯一高强调主操作；
- 展开态继续完整展示原有选择、元数据、授权 Preview、Commit 和可执行 Plan。

## 实施任务

- [x] 收敛资料区收起态的宽度、阴影、留白与文案；
- [x] 建立收起态与展开态不同的工作宽度；
- [x] 锁定核心验收主按钮与资料次按钮的视觉层级；
- [x] 补充宽屏与窄屏 E2E；
- [x] 完成 typecheck、build、Playwright、Python 回归和 Desktop artifact smoke；
- [x] 更新状态并提交 Git。

## 验收标准

- [x] 1920px 大字模式下，资料准备区明显窄于核心验收主舞台，左右各有稳定内收；
- [x] 收起态资料栏不再形成横跨页面的大号空白卡，内容与操作保持紧凑；
- [x] 资料入口使用次级按钮，核心验收仍是该段页面唯一实心主按钮；
- [x] 展开资料管理后，既有导入、Preview、Commit 和 Plan 操作完整可用；
- [x] 390×844 无页面级横向溢出，按钮和状态可读；
- [x] 首载、展开和显示大小切换不新增业务请求。

## 验证证据

- 测试命令：`npm run typecheck --workspace @agent-audit/web`；`npm run build --workspace @agent-audit/web`；`.venv\Scripts\python.exe -m pytest -q`；`npx playwright test --reporter=line`；指定 Desktop artifact smoke；`git diff --check`
- 结果：Web typecheck/build 通过；Python `623 passed, 6 skipped`；Playwright `28 passed`；新 Desktop artifact smoke `10 passed`；仅保留既有 Vite chunk 与 Starlette/httpx warning。
- 人工步骤：在 1920×1080 大字模式核对资料区比核心验收窄 100px CSS、左右各内收 50px，收起卡高度低于 125px；390×844 保持单列且无页面级横向溢出。

## 实施记录

- 2026-08-30：用户指出资料状态卡比下方模块更长且不好看，并进一步纠正“不能把所有功能统一成同样的卡片，必须突出重要功能”。本功能因此从单纯对齐改为明确的主次视觉层级。
- 2026-08-30：完成资料准备栏内收、低阴影、中文状态与次级按钮；展开态继续使用完整工作宽度，核心验收的深色舞台和实心按钮保持唯一高强调。
