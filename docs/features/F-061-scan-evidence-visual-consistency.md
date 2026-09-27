# F-061 扫描证据视觉一致性与操作对齐

- 状态：Completed
- 所属里程碑：M6 本地双平台产品化
- 负责人：主代理
- 相关决定：用户实屏反馈真实攻击链缺少背景图、单一 Attack Plan 仍显示下拉框、扫描过程低对比、策略理由过小、固定 Case 操作按钮错位

## 用户价值

评委和普通用户在查看真实扫描结果时，应获得一致、清晰且不制造虚假选择的界面：只有一个 Plan 时直接确认当前计划；关键攻击策略醒目可读；扫描过程和操作按钮保持稳定对齐。

## 范围

- 真实攻击链结果继续显示已有审计数据流视觉背景，不只在空态显示；
- Attack Plan 只有一项时显示只读当前计划卡，多项时保留真实切换控件；
- 将扫描状态转换从旧深灰条改为符合浅色工作台的可读过程列表；
- 将 Attack Attempt 的 mutation reason 改为正文级“本轮攻击策略”，Finding 轮次使用风险色强调；
- 固定 Case 卡片按内容自适应，同时把同行执行按钮对齐到底部；
- 将 Desktop 启动失败页改为用户影响、恢复动作和折叠技术详情，不再默认展示截断的原始异常；
- 增加单/多 Plan、真实结果背景、Reason 风险层级、Case 按钮对齐和宽窄屏回归。

## 非目标

- 不为填充下拉框新增虚假 Attack Plan；
- 不修改 Planner、Scan、Attempt、Trace、Finding、Replay 或 Security Contract 判定；
- 不改变 API、Contracts、持久化数据或 Provider 调用；
- 不使用固定卡片高度掩盖内容差异，不删除技术 ID 或完整证据。

## 前后端与数据影响

- Web：条件渲染 Plan 控件；调整 Guided 攻击链、扫描过程、策略理由、Case 卡片与 Desktop splash 启动失败样式；
- API：无；
- Contracts：无；
- Data/Model/Tool：无执行语义变化。

## API 或交互契约

- `attackPlans.length === 1` 时仍使用该真实 Plan ID 启动 Scan，但页面不渲染可展开选择控件；
- `attackPlans.length > 1` 时保留现有选择和切换行为；
- 视觉强调只依据当前 Attempt 的真实 `status`，不从 mutation reason 文本推断风险；
- 攻击链背景为装饰层，节点、证据面板和无障碍阅读顺序保持不变。

## 实施任务

- [x] 修复攻击链结果态背景与单 Plan 呈现；
- [x] 重做扫描过程、策略理由和固定 Case 对齐；
- [x] 收口 Desktop splash 的失败解释与技术详情分层；
- [x] 增加针对性 E2E 和响应式视觉检查；
- [x] 完成主审、构建与相关全量回归；
- [x] 更新任务板、STATUS 和验证证据。

## 验收标准

- [x] 空态和真实结果态均存在一张装饰性攻击链背景图，节点文字对比度不降低；
- [x] 一个 Plan 时没有下拉箭头或伪切换，多 Plan 时仍可切换并执行选中 Plan；
- [x] 状态转换列表不再使用整块深灰底，正文达到现有 body-small 字号；
- [x] Finding Attempt 的“本轮攻击策略”使用风险色信息块，正文不小于 14px；非 Finding Attempt 不误标红；
- [x] 1440px 同行固定 Case 执行按钮底边一致，390px 单列无横向溢出；
- [x] Desktop 启动失败默认层不显示原始异常，明确说明数据影响和恢复动作，原始诊断仍可展开；
- [x] 原有 Scan、Finding、Trace、Replay 结果与请求次数不变。

## 验证证据

- 测试命令：`npm run typecheck`、`npm run build`、`npx playwright test tests/e2e/f061_scan_evidence_visual_consistency.spec.ts --reporter=dot`、`npm run test:e2e -- --reporter=dot`、`.venv\\Scripts\\python.exe -m pytest -q --tb=short`、指定 release EXE 的 `tests/integration/test_desktop_configuration.py`
- 结果：typecheck 与 production build 通过；F-061 定向 4/4、全量 Playwright 45/45、Python 887 passed / 10 skipped、Desktop artifact smoke 10/10；Windows NSIS 已按当前源码重建。
- 人工步骤：复核全量 E2E 生成的 Guided Critical Finding 与 Acceptance Summary 截图；攻击链六节点、Finding 编号独立块、结果态背景和技术证据分层均保持可读。
- 当前安装包：`artifacts/desktop/generated/知盾 AgentAudit_0.1.2_x64-setup.exe`，SHA-256 `9922BFEE1D5C1954BC25E243678165FBFDB7A02003345C3E6B5FF8B7522BBEF7`。

## 实施记录

- 2026-09-01：根据用户五张实屏截图建立本轮最小视觉与交互收口；选择“单 Plan 静态确认、多 Plan 才显示选择器”，不新增没有安全语义的 Plan。
- 2026-09-01：三个 Luna Max 分别完成主工作台、Guided/报告/验收和视觉回归；主代理审查后修正一条把“结果态背景消失”视为正确行为的旧 E2E 断言，并完成全量回归与 Windows 安装包重建。
