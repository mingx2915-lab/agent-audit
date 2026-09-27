# F-059 人话攻击链与分层技术证据

- 状态：Completed
- 所属里程碑：M6
- 负责人：主代理
- 相关决定：用户实屏反馈攻击链默认展示大量内部符号、单节点展开拉高整行、Finding 编号漂在图片上且完整 Trace 字号过小

## 用户价值

评委和普通用户应先看懂“谁受到什么内容影响、读取了什么、权限如何判断、执行了什么、数据去了哪里”，再按需核对内部 ID、字段和原始 JSON；展开一处证据不应破坏整条链的版面。

## 范围

- 为真实攻击链增加一条由当前 Trace 确定性生成的中文过程摘要；
- 六个节点默认显示中文业务动作，内部 ID 和原始字段保留在证据详情；
- 六个节点在宽屏保持等高；节点证据在攻击链下方独立全宽展开，不改变任何节点高度；
- 节点证据中的原始 JSON 改为二次展开；
- Finding 编号移出图片，使用独立高对比信息块；
- 完整 Trace 使用中文事件摘要、较大字号和分块关键字段，原始 details 继续保留。

## 非目标

- 不修改 Trace、Finding、Security Contract、Scan 或 Replay 判定；
- 不让 LLM 生成页面摘要，不根据未出现的事实补全故事；
- 不删除内部 ID、原始字段、时间戳或 JSON；
- 不修改已确认的 Finding 背景图。

## 前后端与数据影响

- Web：调整 `GuidedAuditFlow` 的文案投影、信息层级、展开布局与字号；
- API：无；
- Contracts：无；
- Data/Model/Tool：无执行语义变化。

## API 或交互契约

- 页面继续只消费现有 `Actor`、`TraceEvent`、`Finding` 和 `RedTeamScan` DTO；
- 中文摘要只使用实际 Actor、事件类型、decision、tool、sink、destination 和资源数量；
- 原始 DTO 内容在折叠技术证据中保持可核对。

## 实施任务

- [x] 重写攻击链默认阅读层并保留技术证据；
- [x] 将六张宽屏卡片对齐为等高，并把节点证据移到独立全宽面板；
- [x] 重排 Finding 编号；
- [x] 提升完整 Trace 的阅读字号与字段分组；
- [x] 增加浏览器回归并完成构建验证。

## 验收标准

- [x] 默认攻击链无需理解 `external_document`、`mock_mail_send` 等内部值也能读懂；
- [x] 宽屏六张节点卡等高，展开 Authorization 证据前后六张卡高度均不变化；
- [x] 节点原始 JSON 默认折叠；
- [x] Finding 编号有明确中文标签和独立背景，不覆盖在图片上；
- [x] 完整 Trace 事件标题和关键字段达到正文可读字号，原始 details 可继续展开；
- [x] 390px 窄屏无横向溢出，既有 Scan/Finding/Replay 主链不变。

## 验证证据

- 测试命令：`.venv\Scripts\python.exe -m pytest -q`；`npm run test:e2e`；`npm run typecheck`；`npm run build`；指定新 Desktop EXE 的 `tests/integration/test_desktop_configuration.py`；Python `compileall`、`pip check`；`git diff --check`。
- 结果：Python `880 passed, 10 skipped`；Playwright `37 passed`；F-059 定向 `4 passed`；新 Desktop EXE 定向 `10 passed`；typecheck、production build、compileall、pip check 与 diff-check 通过。production build 只保留既有的大 chunk warning。
- 人工步骤：基于用户 2048px 实屏复核问题；随后对实际 Source→Sink Scan 截图做两轮视觉检查。最终证据 `artifacts/acceptance/generated/f059-visual-review/attack-chain-panel.png` 显示六张节点卡等高，Authorization 证据在下方独立全宽面板展示；Finding 编号与完整 Trace 的截图也确认独立信息块、中文标题、较大关键字段和默认折叠原始事件。

## 实施记录

- 本功能只改变确定性展示投影与 CSS，不生成新的审计结论。
- 三名 Luna Max 分别负责 UI 实现、E2E 回归和独立事实边界审计；主代理整合后额外修正了 business Sink 边界、Retrieval 候选表述、Source 类型文案和等高卡片视觉缺口。
- Windows `0.1.2` 安装包已从当前源码重建到 `artifacts/desktop/generated/知盾 AgentAudit_0.1.2_x64-setup.exe`，SHA-256 为 `A48F40D07ED25FC271B1A783301DDA69A6D7FABA39EE073310327B28ED0A9D05`。
