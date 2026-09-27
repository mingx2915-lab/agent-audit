# F-035 企业 AI 接入与首次验收向导

- 状态：External Validation Pending（软件实现完成，陌生用户与真实原生错误人工证据待补）
- 所属里程碑：M6 本地双平台产品化
- 负责人：主代理
- 相关决定：`docs/features/F-028-workspace-document-import.md`、`docs/features/F-031-enterprise-runtime-connection.md`、`docs/features/F-034-provider-setup-layout-compression.md`

## 用户价值

用户不需要理解 Workspace、Retriever、UTF-8、JSON 或测试 Case，也能从空白安装状态完成一次真实的企业知识助手安全验收。

本功能的判断标准不是“接口能跑”，而是：**没有阅读源码和开发文档的用户，在五分钟内知道软件需要什么、为什么需要，并完成“连接 AI → 添加知识 → 确认权限 → 运行检查 → 查看 Finding / Replay”。**

## 当前问题与事实边界

### 当前产品问题

- “导入企业知识资料”没有说明要选择的是 AI 会检索的业务文档，而不是模型目录、项目源码、数据库或软件自己的 Workspace；
- “选择文件夹”看起来像让用户寻找一个固定系统目录，实际却是选择任意包含原始业务文档的来源文件夹；
- 当前只支持 UTF-8 `.txt` / `.md`，与企业常见 PDF、Word 文档不匹配；
- Tauri command 返回的具体错误是字符串，Web 只识别 `Error`，导致权限、数量、路径等诊断被折叠为“无法读取所选资料”；
- 文档元数据一次展示过多技术字段，用户不知道哪些必须确认；
- 导入完成后没有自然引导到“为这批资料运行什么检查”；
- 现有 E2E 使用 Test-only 文件选择 Transport，证明了 Preview → Commit → Retrieval 链路，但没有证明真实安装版系统文件对话框对普通用户可用。

### 产品事实

企业 AI 通常由模型 Runtime、知识来源、业务工具和身份权限共同组成。当前软件已经能够：

- 连接固定本机 Ollama 或用户明确填写的 OpenAI-compatible 企业 Runtime；
- 对导入 Workspace 的知识快照执行 Retrieval 与 Authorization Trace；
- 检查资源越权、Tool 业务约束、Source → Sink 和 Replay；
- 保存本地 History、Acceptance Run 和报告。

当前软件不能自动理解或接管任意企业业务，也不扫描局域网、数据库、SharePoint、Confluence、CRM 或 ERP。本功能只把现有受控能力组织成可完成的接入流程，并补齐常用离线文件格式。

## 产品流程

首次使用只提供两个明确入口：

### 路径 A：先看内置演示

```text
使用合成演示资料
→ 显示演示包含的角色、公开资料、客户合同和财务资料
→ 直接运行固定 Guided Audit
→ 查看真实 Trace、Finding 和 Replay
```

该路径必须始终标注“合成演示”，不能写成企业真实结果。

### 路径 B：验收我的知识助手

```text
1. 连接本机或企业 AI
2. 添加 AI 实际会检索的业务文档
3. 确认部门、资料归属和敏感等级
4. 预览允许/拒绝访问矩阵
5. 选择一个由 Contract 派生的首次检查
6. 运行 Guided Audit
7. 查看 Finding 与同 Plan Replay
```

页面必须在每一步回答三个问题：

1. 现在要提供什么；
2. 软件会如何使用它；
3. 完成后下一步是什么。

## 用户应该提供什么

“添加知识”页面只接收 **企业知识助手实际可能检索的内容**，并给出可点选示例：

| 资料类型 | 示例 | 建议元数据 |
|---|---|---|
| 公开知识 | 产品说明、公开 FAQ | public / product |
| 内部制度 | 员工手册、操作流程 | internal / department |
| 客户资料 | 合同、客户服务记录 | confidential / owner |
| 财务资料 | 预算、报价、审批文件 | confidential / finance |

页面必须明确说明以下内容不是导入对象：模型文件、Ollama/vLLM 安装目录、项目源码、API Key、数据库文件、软件自己的 Workspace。

## 范围

### 1. 首次接入向导

- 在桌面主流程提供“使用合成演示”和“验收我的知识助手”两个入口；
- 复用现有 Provider Setup、Document Import、Contract Preview、Planner 和 Guided Audit，不复制业务判断；
- 显示步骤进度、当前缺口和唯一主操作；允许退出后继续，不自动运行模型；
- 已完成步骤读取真实状态，不用前端假数据标记完成。

### 2. 知识来源选择

- 文案改为“添加 AI 会检索的业务文档”；
- 支持单文件、多文件和文件夹；文件夹可以位于桌面、文档盘、移动盘或企业批准的本地挂载目录，不存在固定“待导入文件夹”；
- 第一阶段支持 `.pdf`、`.docx`、`.txt`、`.md`；PDF / DOCX 只提取文本，不执行宏、不访问外链、不处理加密文件；
- 文件夹递归时只收集支持格式，其他文件显示为跳过项，不因一个无关 JSON 或图片使整批失败；
- 保留批次数量和单文件大小上限，但在选择前可见，并对超限项目逐项说明；
- 取消选择不写入 Workspace；Preview 前不写入 Workspace。

### 3. 权限确认

- 自动提取文件名、标题建议和文件类型；AI 只能提出元数据建议，不能直接成为正式权限；
- 普通层只要求确认：资料类别、允许部门/角色、敏感等级，以及客户类资料的 Owner；
- 支持对整批应用相同设置，再单独修改例外项；
- Advanced 层保留完整标签、source type 和 Contract rule 细节；
- 后端使用 active Security Contract 生成允许/拒绝矩阵，Web 不复制授权判断。

### 4. 导入后的首次检查

- 成功导入后显示新增资料数量、跳过项和索引状态；
- 根据 active Contract 与真实导入资产展示可执行的 Contract-derived Plan；
- 用户显式选择 Plan 后进入现有 Guided Audit；
- 如果当前 Contract 无法派生有效 Plan，说明缺少哪个角色或规则，并返回 Contract Preview，而不是生成假的检查；
- Finding 仍只来自真实 Trace 与 Contract Checker，文件标题、AI 建议和 expected 不参与最终判定。

### 5. 真实错误与恢复

- 保留 Tauri/Rust 返回的具体可读错误，不再折叠为统一“无法读取所选资料”；
- 区分：用户取消、没有支持文件、文件无权限、编码或解析失败、超出数量、单项过大、加密文档和索引失败；
- 一批中部分文件失败时允许用户查看并移除失败项，再继续 Preview；
- Index/Workspace 写入失败保持原有原子边界，不留下半导入目录或半更新 Retriever。

## 非目标

- 不扫描整个硬盘或局域网；
- 不自动连接 SharePoint、Confluence、文件服务器、数据库、CRM、ERP 或向量数据库；这些 Connector 需要独立授权和后续功能文档；
- 不读取未经用户选择的目录，不持续监控来源文件夹；
- 不支持任意二进制格式、图片 OCR、音视频、邮件归档、Excel 业务表或压缩包递归；
- 不让 LLM 自动决定真实企业角色、权限、Owner、审批或敏感等级；
- 不建设通用 ETL、DLP、文档管理或企业资产发现平台；
- 不改变 Security Contract、Trace、Finding 和 Replay 的确定性边界。

## 前后端与数据影响

- Web：新增首次接入向导；重构 Document Import 的普通层、批量元数据和导入后 CTA；
- Desktop：真实系统文件/文件夹选择、支持格式过滤和原生错误透传；
- API：扩展文档解析状态和接入进度所需的只读状态，不新增任意目标扫描；
- Contracts：增加接入步骤状态、解析格式/诊断和批量元数据请求所需 DTO；
- Data：导入后仍只保存标准化文本快照、相对来源和用户确认的元数据；不把来源绝对路径写入 Workspace；
- Model：解析与权限 Preview 不调用模型；元数据建议如使用模型必须由用户显式触发，并与正式 Contract 确认分离；
- Tool：不新增真实企业 Tool Connector。

## API 或交互契约

- 首载和刷新只能读取当前接入状态，不自动发现、解析、运行 Readiness 或执行 Audit；
- 原生选择器返回每项明确状态：`ready`、`unsupported`、`invalid`，以及可读 diagnostic；
- PDF / DOCX 解析发生在本机 Sidecar，不上传文件；后端只接收标准化 Draft；
- Preview 是纯计算；只有用户确认导入才写 Workspace 和热替换共享 Retriever；
- 导入成功返回 imported、skipped、index metadata 和可执行 Plan 摘要；
- 任何建议字段必须明确标记为 draft；只有用户确认后的字段进入 Security Contract / document metadata；
- Source 绝对路径只存在于 Desktop 原生边界，不进入 API、Trace、History、错误导出或报告。

## 实施顺序

### 阶段 1：把现有功能变得可理解

- [x] 修复 Tauri 字符串错误被 Web 折叠的问题；
- [x] 改写导入标题、支持格式、示例和非导入对象说明；
- [x] 把“选择文件”设为默认主操作，“选择文件夹”作为批量方式；
- [x] 为文件夹空目录、无支持文件和部分失败提供明确结果；
- [x] 使用真实桌面窗口完成一次系统文件对话框人工验收。

### 阶段 2：补齐企业常用离线文档

- [x] 增加 PDF、DOCX 本地文本提取；
- [x] 锁定不执行宏、不访问外链、不解析加密文档的安全边界；
- [x] 文件夹只收集支持格式，并逐项展示跳过原因；
- [x] 保持可移动 Workspace、原子写入和 Retriever 热替换。

### 阶段 3：首次接入向导

- [x] 实现演示/自有知识助手双入口；
- [x] 复用真实 Provider Setup、Import、Contract Preview 与 Planner 状态；
- [x] 实现批量元数据确认和例外项修改；
- [x] 导入成功后直接进入一个真实 Contract-derived Guided Audit；
- [x] 中途退出后从已保存的非敏感状态恢复，不自动重跑外部动作。

### 阶段 4：真实用户路径验收

- [x] 保留业务 API E2E 的 Test-only Transport；
- [x] 另增安装版/开发版真实系统文件选择人工验收，不以 Transport 代替；
- [x] 使用一个全新临时企业资料目录完成 PDF、DOCX、TXT、MD 混合导入；
- [x] 验证允许角色进入 `model_context`、拒绝角色保留 denied Authorization 且不进入 context；
- [ ] 从空白启动到首个 Guided Audit 控制在五分钟内；
- [ ] 由未阅读源码的人按页面文字完成一次任务，并记录卡点。

## 验收标准

- [x] 首屏明确说明软件需要 AI 地址、业务文档和角色权限，不出现 Workspace/JSON/UTF-8 作为普通用户前置知识；
- [x] 用户能区分“来源文件夹”和“软件保存的 Workspace”，无需寻找固定导入目录；
- [x] 用户能在一个普通文件夹中混放 PDF、DOCX、TXT、MD 和无关文件，软件只处理支持项并逐项说明其他项目；
- [ ] 真实 Tauri 文件选择错误显示原始可读原因，不再统一为“无法读取所选资料”；
- [x] 普通用户可以批量设置权限，只对例外文档单独修改；
- [x] Preview 前不写 Workspace，取消不写入，Commit 失败不改变旧 catalog / Retriever；
- [x] 导入后出现真实可执行 Plan；无法派生时显示缺失规则，不伪造 Plan；
- [x] 同一导入文档在允许/拒绝身份下产生真实且隔离的 Retrieval / Authorization Trace；
- [x] 用户能从首次启动完成 Guided Audit → Finding → Replay，关键步骤无隐藏按钮和技术猜测；
- [x] Windows 真实文件对话框人工验收通过；Linux 证据只能在真实 Linux 环境存在时记录；
- [x] Python tests、typecheck、build、Playwright、Desktop check 和 diff check 通过。

## 验证证据

- Python：`.venv\Scripts\python.exe -m pytest -q` → `588 passed, 2 skipped, 1 warning`；`compileall -q apps/api/src tests` 通过；
- Web/Desktop TypeScript：根 `npm run typecheck` 通过；根 `npm run build` 通过，仅保留既有 Vite chunk size warning；
- E2E：`npx playwright test --reporter=line` → `19 passed`，其中 F-035 三项覆盖混合格式、逐项跳过、双入口、批量元数据、真实 Plan → Scan、错误透传和 390×844；
- Rust：`cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml --lib` → `4 passed`；`cargo check` 与 `cargo fmt -- --check` 通过；真实测试覆盖 PDF/DOCX 文本、实体、加密、损坏、无文本、20 MiB/2 MiB 边界和文件夹逐项跳过；
- Desktop Sidecar：使用最新代码重新打包后，在隔离 `AGENT_AUDIT_HOME` 首次启动并创建默认 Workspace，`/api/health` 返回 `ready`；测试结束后按本次进程树清理，无残留；
- Windows 人工证据：真实 Tauri 开发版窗口通过 Windows 系统文件夹选择器选择 `tmp/f035-manual`，本机解析 1 份 PDF、1 份 DOCX、1 份 TXT、1 份 MD，Preview 为 `4 ready`；确认后成功导入 4 项、跳过 0 项，Retriever 从 7 项热更新到 11 项，并显示 4 条真实 Contract-derived Plan。目录仅含合成资料，绝对来源路径未进入页面工件；该证据不由 Test-only Transport 替代。
- 未完成的人工证据：仍需由未阅读源码的人从空白状态完成一次五分钟首次验收任务并记录卡点；真实 Tauri 错误对话框的原始可读错误路径也保持未勾选，不能以成功选择或自动化错误注入代替。

## 实施记录

- 2026-08-28：用户在已了解产品目标的情况下仍无法判断应该选择哪个文件夹、放入什么内容。该事实证明 F-028 的技术链路验收不能代表首次使用体验完成。
- 2026-08-28：三名 Luna Max 分别完成后端/契约、Desktop/Web、测试切片；主代理修复并实测 DOCX XML GeneralRef 与结构化加密 PDF fixture，完成全量 Python/Web/E2E/Rust 回归。
- 2026-08-28：主代理在真实 Tauri 窗口中完成 Windows 系统文件夹选择、四格式 Preview、Commit 与热索引人工验收；同时修复首次打开时把未执行 Audit 误显示为“已完成一次真实 Trace 验收”的 computed ref 判断。功能继续保持 In Progress，仅剩未读源码用户五分钟任务和真实原生错误路径人工证据。
- 当前实现仍可作为底层 Document Import 垂直切片，但普通用户入口和完成定义必须由本功能重新收敛。
- 企业 SharePoint、Confluence、数据库和业务 Tool Connector 只记录为后续授权方向，不纳入 F-035，避免把单一产品扩大成综合扫描平台。
