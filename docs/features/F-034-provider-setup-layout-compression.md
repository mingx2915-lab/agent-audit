# F-034 模型连接页结构收敛

- 状态：Completed
- 所属里程碑：M6 本地双平台产品化
- 负责人：主代理
- 相关决定：`docs/features/F-027-first-run-provider-setup.md`、`docs/features/F-031-enterprise-runtime-connection.md`、`docs/features/F-032-visual-hierarchy-and-human-copy.md`

## 用户价值

企业用户第一次连接 AI 时，应在一个连续工作面内完成“选择方式 → 确认地址和模型 → 检查四项能力 → 确认使用”，而不是在多张高空白卡片之间寻找下一步。

## 当前问题

- 标题、连接方式、方法卡、下一步提示、Readiness Header、Readiness 空态和确认栏纵向分散，任务密度低；
- 未检查状态单独占用大卡，右侧只有按钮，无法预览即将检查的四项能力；
- 本机 Ollama 方法卡的信息都挤在左侧，操作按钮孤立在右侧；
- Readiness 完整证据适合技术详情，但不适合作为首次连接的默认阅读层；
- 当前空白是结构性空白，不能通过添加大图填补。

## 设计决定

1. **连续任务面**：标题、方式选择、候选连接、Readiness 和确认栏保持在一个连续流程中。
2. **本机三栏**：桌面端使用“方法 / 地址与模型 / 操作”三栏；窄屏自动单列。
3. **企业字段不缩水**：企业地址继续保留 OpenAI-compatible、地址、认证、API Key、模型和显式地址检查，不把企业连接伪装成本机 Ollama。
4. **四项探针常驻**：候选 Readiness 在未检查时也显示 Target connectivity、Target Tool Calling、Attack connectivity、Attack strict JSON 四个中性槽位；检查后原位更新状态。
5. **证据分层**：默认层只显示四项状态与总结果；Provider facts、耗时、diagnostic 和 Plan compatibility 放入可展开详情。
6. **单一确认栏**：删除独立“确认后即可使用”说明卡，改成紧凑底栏；桌面右对齐取消/确认，窄屏按钮可触达。
7. **图片后置**：本功能不生成或接入连接插画；结构验收完成后再决定是否需要不超过约 220×110 的独立原创资产。

## 范围

- 重排 `ProviderSetupView.vue` 的标题、方式选择、本机/企业方法区和确认栏；
- 为 `ProviderReadinessView.vue` 新增候选连接专用的紧凑展示模式，同时保持完整模式不变；
- 删除候选模式独立的大号“尚未检查”空态，改为四项中性探针；
- 保持首载只 GET、发现/检查/Readiness/保存均由用户显式触发；
- 保持现有 DTO、API、Credential Store 和 Runtime 切换行为不变；
- 保持 390×844 无横向溢出。

## 非目标

- 不新增图片、Logo、动画或第三方 UI 依赖；
- 不修改 Provider discovery、inspection、readiness、保存 API；
- 不扩大自动发现范围，不扫描局域网，不新增 Ollama 以外的自动猜测；
- 不削弱企业地址、Bearer 密钥和显式确认边界；
- 不删除完整 Readiness 证据或 Plan compatibility；
- 不修改核心 Scan、Finding、Replay 和 Acceptance Run 页面。

## 前后端与数据影响

- Web：仅调整 `ProviderSetupView.vue`、`ProviderReadinessView.vue` 及必要测试；
- API：无；
- Contracts：无；
- Data/Model/Tool：无；
- Desktop：无原生命令变化，Credential Store 语义保持不变。

## API 或交互契约

- `ProviderReadinessView` 新增可选 `presentation: "full" | "candidate"`，默认 `full`；
- `candidate` 模式必须始终显示四项固定探针槽位，结果存在时从真实 `ProviderReadinessResult` 映射；
- `full` 模式保持现有 Acceptance/高级证据页面结构与测试契约；
- `ProviderSetupView` 使用 `presentation="candidate"`，现有 `run-test-id="provider-setup-check"` 保持不变；
- 首载和刷新不得新增 Discovery、Inspection、Readiness 或 PUT；
- 草稿变化继续使 Readiness stale，只有重新获得 READY 才能确认使用；
- Bearer 密钥仍只在 Desktop Credential Store 保存，浏览器不得明文保存。

## 实施任务

- [x] ~~重排连接标题、方式卡与本机/企业方法区；~~
- [x] ~~实现候选 Readiness 四探针紧凑展示与折叠详情；~~
- [x] ~~合并底部确认操作栏并删除重复说明/空态；~~
- [x] ~~保持完整 Readiness 与现有业务交互回归；~~
- [x] ~~完成 typecheck、build、Python、Playwright 和人工响应式审查；~~
- [x] ~~更新状态文档并提交 Git。~~

## 验收标准

- [x] ~~1440px 下连接方式、候选地址/模型和操作不再出现单侧堆叠与无意义大空洞；~~
- [x] ~~未检查时即可看到四项探针名称及“未检查”状态，不存在独立大号空态卡；~~
- [x] ~~检查后四项状态、总结果和确认按钮在同一连续工作面内可见；~~
- [x] ~~企业地址、认证、API Key 和模型字段完整保留；~~
- [x] ~~完整 Readiness 证据可展开访问，其他页面的 full 模式不退化；~~
- [x] ~~390×844 自动单列且无横向溢出；~~
- [x] ~~API 请求时序、stale、Cancel 和 Credential Store 行为不变；~~
- [x] ~~typecheck、build、Python 与 Playwright 回归通过。~~

## 验证证据

- 测试命令：`.venv\Scripts\python.exe -m pytest -q`；`npm run typecheck`；`npm run build --workspace @agent-audit/web`；`npx playwright test --reporter=line`；`git diff --check`。
- 结果：567 passed、2 个真实 artifact 条件不满足时诚实 skip、1 个既有 Starlette warning；16 个 Playwright E2E passed；typecheck、production build 与 diff check 通过。
- 人工步骤：使用 Test-only Provider 在 1440px 和 390px 实际检查本机 Ollama、企业地址、未检查/READY Readiness、确认栏和折叠证据；页面无横向溢出，未调用真实模型。

## 实施记录

- 三个 Luna Max 分别负责 Provider Setup、候选 Readiness 和测试；主代理负责契约、组合审查、实际界面与 Git 收口。
