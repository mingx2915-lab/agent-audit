# F-028 企业 Workspace 与资料导入

- 状态：Completed
- 所属里程碑：M6 本地双平台产品化
- 负责人：主代理统筹；Backend、Frontend/Desktop、Tests 三个 Luna Max 互斥实现
- 相关决定：`docs/M6_LOCAL_DUAL_PLATFORM_PRODUCT_PLAN.md`

## 用户价值

小企业管理员可在 Windows/Linux 桌面窗口中选择自己的企业知识资料，先看解析结果和权限元数据，再明确确认导入。成功导入的资料成为可移动 Audit Workspace 的本地快照，并立即进入现有 Retrieval、Authorization、Trace、Finding 与 Replay 主链；软件不替用户猜测真实权限。

## 范围

- 通过 Tauri 原生对话框选择多个文件或一个文件夹，不打开外部浏览器。
- 第一版真实解析 UTF-8 `.txt` 与 `.md`；不支持项逐项显示原因，不伪装成功。
- 原生边界只把文件名、相对路径、格式、大小和文本内容交给 Renderer/API；业务 DTO、Workspace、日志和报告不保存开发机或企业机器的绝对路径。
- 导入前提供解析预览，用户逐项确认标题、业务范围、敏感等级、Owner 与来源可信度。
- 服务端根据显式元数据生成资源标签；不调用 LLM 推断角色、Owner、敏感等级或权限。
- 用户确认后，把文档内容追加到当前 Workspace 的 `documents/knowledge_documents.json` 快照；已有 Seed、Contract 和 History 不被覆盖。
- 成功写入后立即替换同一进程内共享 Retriever 索引，新文档无需重启即可参与真实查询和权限 Trace。
- 页面显示当前 Workspace 文档目录、导入成功/跳过项和 Retriever 已索引数量。
- 提供候选文档对 active Security Contract 的确定性授权预览：按现有 ResourceRule 分角色列出允许/拒绝，不修改 Contract，也不自动创建规则。

## 非目标

- 不解析 PDF、DOCX、图片、OCR、压缩包或网页；这些格式只显示“当前版本不支持”。
- 不持续监视或同步外部目录，不保存外部绝对路径。文件夹选择在 F-028 中同样生成 Workspace 快照；持续只读连接因会破坏可移动性和历史复现，待真实需求后另立功能。
- 不扫描整台电脑、用户目录、局域网共享、云盘或任意 Endpoint。
- 不自动修改 Security Contract，不用 LLM 猜企业权限，不建立通用文档管理系统。
- 不在本功能做文档编辑、删除、版本控制、去重、向量数据库或后台任务队列。
- 不提前实现 F-029 的备份恢复、Linux 安装包和 Credential Store。

## 前后端与数据影响

- Web：新增紧凑的“企业资料”工作区，完成选择、预览、元数据确认、Contract 授权预览、确认导入与结果展示。
- Desktop：新增原生文件/文件夹读取命令；只读取用户本次明确选择的 `.txt`/`.md`，返回相对名称与内容，不把绝对路径传入业务 API。
- API：新增纯预览、确认导入和文档目录接口；预览无写入，导入只允许有效 Workspace。
- Contracts：新增 `DocumentImportSource`、Preview、Metadata、Authorization Preview、Commit Result 与 Document Summary DTO。
- Data/Model/Tool：原子更新当前 Workspace 文档 JSON；用同一个 Embedder/engine 重建共享 Retriever，不触发 Provider、Tool、Scan 或 Acceptance Run。

## API 或交互契约

### 原生选择结果

`select_document_files` 和 `select_document_folder` 返回：

```text
displayName / relativePath / extension / sizeBytes / content | diagnostic
```

- `relativePath` 只相对本次选择根目录；不得包含盘符、UNC 根或 `..` 越界。
- `.txt`/`.md` 必须为 UTF-8 文本；读取失败作为该项 diagnostic 返回，不中断其他项预览。
- 单文件最大 2 MiB、单次最多 50 项；限制在原生信任边界和 API 信任边界一致执行。

### HTTP

- `POST /api/document-imports/previews`
  - 输入：`{ documents: DocumentImportDraft[] }`；每项同时包含原生选择结果与用户显式确认的 Metadata。
  - 输出：逐项 `ready | unsupported | invalid`、标题建议、内容预览与原因，以及 active Contract 对候选元数据的授权矩阵；无文件写入、无 Provider 调用。
- `POST /api/document-imports`
  - 输入：用户确认的 ready 文档与显式 Metadata；服务端重新验证输入。
  - 输出：导入文档摘要、跳过项、Retriever metadata；只在完整目录写入与索引重建成功后返回成功。
- `GET /api/workspace/documents`
  - 输出：当前文档摘要和 Retriever metadata；不返回完整敏感内容。

### 元数据映射

- `sensitivity`: `public | confidential`
- `businessScope`: `general | customer | finance | hr`
- `ownerId`: 当前合成/企业 Actor ID 或 `null`
- `trustLevel`: `trusted | untrusted`
- 标签由服务端稳定生成：`sensitivity` + 非 general 的 `businessScope`；不额外注入 expected 或演示结论。
- `sourceType` 由可信度稳定映射：`trusted -> knowledge_base`，`untrusted -> external_document`。

## 实施任务

- [x] ~~锁定跨端 DTO 和功能文档。~~
- [x] ~~实现原生文件/文件夹选择与逐项 UTF-8 读取。~~
- [x] ~~实现预览、Contract 授权矩阵、Workspace 原子写入和 Retriever 热替换。~~
- [x] ~~实现企业资料 UI 与当前目录展示。~~
- [x] ~~补充核心单元、API 集成、Desktop 契约和关键 E2E。~~
- [x] ~~执行全量 Python、TypeScript、build、Playwright、Rust/diff 验收并记录证据。~~

## 验收标准

- [x] ~~首次打开企业资料区只 GET 当前目录，不弹系统对话框、不 POST、不调用模型。~~
- [x] ~~用户可通过原生对话框选择多个 `.txt`/`.md` 或一个文件夹；取消不产生 API 写入。~~
- [x] ~~ready、unsupported、invalid 项逐项可见；绝对路径不进入 API payload、Workspace JSON、History、日志或页面。~~
- [x] ~~用户必须明确确认标题、业务范围、敏感等级、Owner 和可信度后才能导入；软件不自动决定企业权限。~~
- [x] ~~Preview 无副作用，Contract 授权矩阵完全由 active Contract 和候选标签/Owner 计算。~~
- [x] ~~导入成功后 Workspace 原文档、Contract、History 保留，新文档立即进入共享 Retriever；无需重启。~~
- [x] ~~secure Profile 下，允许角色可把导入文档带入 `model_context`，拒绝角色只有 denied Authorization 且不进入 context；结论来自真实 Trace。~~
- [x] ~~导入失败不留下半写 JSON 或部分 Retriever 状态；错误可读且不自动重试/fallback。~~
- [x] ~~Windows/Linux 共用 DTO、API 和 UI；平台差异只在 Tauri 原生选择命令。~~
- [x] ~~390×844 无页面级横向溢出，既有 Guided/Provider Setup/Acceptance Run 回归通过。~~

## 验证证据

- 测试命令：`.venv/Scripts/python.exe -m pytest -q`；`npm run typecheck`；`npm run build --workspace @agent-audit/web`；`npm run test:e2e`；Python `compileall`；`pip check`；Rust `rustfmt --check` 与离线 `cargo check`；`git diff --check`。
- 结果：487 passed、1 个仅在未提供 Desktop artifact 时诚实 skip、1 个既有 Starlette/httpx 弃用 warning；10 个 Playwright E2E passed；其余命令通过。Vite 仅保留既有大 chunk warning。
- 行为证据：隔离 seed-backed Workspace 中完成两批文档追加，保留 Seed、Contract 和 History；导入文档无需重启即被 Retriever 命中，财务角色进入 `model_context`，访客产生 denied Authorization 且不进入 context。浏览器 E2E 使用显式 test-only picker transport，不替换 Preview/Commit/Workspace/Contract/Retriever 生产链路。

## 实施记录

- F-028 将长期计划中的“高级只读连接目录”收敛为“用户明确选择目录后生成快照”。持久连接会保存外部路径、引入同步语义并削弱 Workspace 可移动性与历史可复现性，当前没有足够需求证据支持实现。
- PDF/DOCX/OCR 只有在真实企业样本与依赖体积边界明确后另立功能；本功能只对真实支持的格式声明成功。
- 本功能没有启动真实模型或写入用户真实配置；Provider 调用次数在 Preview、目录和导入路径中保持为零。
