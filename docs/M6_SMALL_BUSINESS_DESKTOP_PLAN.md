# M6 小企业桌面化与可移植部署计划

> 历史说明：本文件保留 F-026 的 Windows-first 决策与实现背景。2026-08-28 起，M6 后续开发的权威主控规格改为 `docs/M6_LOCAL_DUAL_PLATFORM_PRODUCT_PLAN.md`；发生冲突时以后者和用户最新要求为准。

> 项目：知盾 AgentAudit——企业知识助手业务权限安全验收与自动化红队系统  
> 状态：In Progress（F-026 当前机实现与安装验收完成，等待干净 Windows 复核）
> 前置基线：M5 F-021 至 F-025 已完成  
> 范围：只继续完善软件；不制作 PPT、演讲稿或视频

## 1. 结论

知盾 AgentAudit 的下一阶段目标不是继续增加攻击 Prompt，而是从“需要开发环境启动的 Web 项目”变成“小企业管理员可以直接安装和使用的桌面安全验收软件”。

用户最终体验必须是：

1. 下载并安装；
2. 双击桌面图标打开独立窗口；
3. 软件自动发现本机可用 AI，或用一个简化表单手动连接；
4. 通过系统文件/文件夹选择窗口导入企业资料；
5. 确认最小角色与 Security Contract；
6. 在同一桌面窗口运行 Guided Audit、Finding、Replay 和 Acceptance Run；
7. 关闭窗口后，本机后台随之退出，历史和 Workspace 保留。

用户不需要打开浏览器、记忆 `127.0.0.1`、手动运行 Python/Node 命令或理解仓库目录。CLI/CI 作为高级工程入口继续保留，但不作为普通用户主路径。

## 2. 产品定位

### 2.1 推荐使用方式

首个企业化版本定位为**单管理员桌面验收工具**：安装在安全负责人、IT 管理员或 AI 项目负责人的 Windows 电脑上，对经过授权导入的企业资料和规则执行上线前安全验收。

它不是员工日常聊天客户端，也不是任意生产系统扫描器。第一阶段不要求所有员工安装，不开放匿名局域网访问，不直接连接真实邮件、CRM、IAM 或生产敏感数据。

### 2.2 产品边界

继续保持四条核心主张：

1. Security Contract 描述身份、资源、工具、动作、审批、阈值和 Sink；
2. 同时覆盖 Outside-in 与 Inside-out；
3. Finding 由真实 Retrieval、Authorization、Tool、Sink Trace 和 Contract 确定性产生；
4. 同一攻击完成发现、定位、修复配置和 Replay。

桌面化只改变安装、配置、数据定位和交互入口，不改变安全判定来源，不把 Finding 移到桌面壳或 LLM 中计算。

## 3. 锁定的桌面技术路线

### 3.1 采用 Tauri 桌面壳，不重写业务界面

新增 `apps/desktop`，使用 Tauri 创建无地址栏、无外部浏览器的桌面窗口；现有 `apps/web` 继续作为窗口 Renderer，现有 `apps/api` 继续负责业务、安全规则和持久化。

```text
AgentAudit.exe
├─ Tauri Native Window
│  └─ 复用 Vue Renderer（用户看见的是桌面窗口）
├─ AgentAudit API Sidecar
│  └─ 打包后的 Python/FastAPI 本机后台
├─ AI Runtime Connector
│  └─ Ollama / OpenAI-compatible Provider
└─ Audit Workspace
   └─ Documents / Contract / Cases / History / Exports
```

Tauri 官方支持把 Python API 等外部程序作为 Sidecar 随安装包分发，也支持系统原生文件/目录选择和保存对话框：

- [Tauri Sidecar 官方文档](https://v2.tauri.app/develop/sidecar/)
- [Tauri Dialog 官方文档](https://v2.tauri.app/plugin/dialog/)
- [Tauri Windows Installer 官方文档](https://v2.tauri.app/distribute/windows-installer/)

### 3.2 “不用浏览器”的准确含义

- 用户不打开 Edge、Chrome 或其他外部浏览器；
- 用户不输入 URL，不看端口，不手动启动前后端；
- 软件以独立窗口、桌面图标、开始菜单项和卸载入口交付；
- 内部可复用系统 WebView 渲染现有 Vue，以避免重写成熟 UI；
- FastAPI 只绑定本机回环地址，由桌面壳启动、探活和关闭；不默认暴露到局域网；
- 开发期浏览器 E2E 可继续作为 Renderer 回归测试，但交付验收必须增加真实桌面窗口启动测试。

选择 Tauri 而不是 PySide/Qt，是为了复用已经通过 7 条 E2E 的 Vue 主线；选择 Tauri 而不是 Electron，是为了不在安装包中再携带完整 Chromium。若后续实测 Tauri Sidecar 打包无法稳定通过 Windows 干净机验收，再用证据重新决策，不提前维护两套桌面技术栈。

## 4. 软件、AI 与企业资料分离

### 4.1 Application Core

只包含桌面窗口、API、Contract Checker、Trace、Finding、Replay、Benchmark 和 Acceptance Run。应用升级不得覆盖企业 Workspace、模型缓存或历史数据库。

### 4.2 AI Runtime

AI Runtime 独立于软件安装包：

- 本机 Ollama；
- 内网管理员明确填写的 Ollama/OpenAI-compatible 服务；
- 显式配置的外部 Provider；
- Embedding 模型及其缓存。

第一版不把数 GB LLM 打进安装包，不自动下载大模型，不自动切换 Provider。模型安装和下载只能由用户明确确认。

### 4.3 Audit Workspace

每个企业或项目使用独立 Workspace：

```text
workspace/
├─ documents/       经授权导入的知识资料快照
├─ contract/        Security Contract 与角色/资源元数据
├─ cases/           合成或企业确认的 Ground Truth Case
├─ history/         SQLite Scan/Replay/Acceptance 历史
└─ exports/         用户主动导出的 JSON/Markdown
```

运行数据使用 Workspace 相对标识，不把开发机盘符、用户名、安装目录或模型缓存绝对路径写入 Finding、Acceptance Run 和导出报告。用户移动整个 Workspace 后，应能在另一位置重新打开。

## 5. 默认路径与可移植性

路径由操作系统 API 决定，代码中不得拼写用户电脑的固定盘符。

### 5.1 Windows 桌面单用户模式（F-026 首选）

```text
程序：安装器管理的应用目录
配置：%LOCALAPPDATA%\AgentAudit\config
数据：%LOCALAPPDATA%\AgentAudit\data
默认 Workspace：%LOCALAPPDATA%\AgentAudit\workspaces\default
日志：%LOCALAPPDATA%\AgentAudit\logs
```

该模式不要求管理员权限，适合小企业负责人在一台电脑上快速使用。后续若增加 Windows Service/多用户机器模式，再使用 `%ProgramData%\AgentAudit`，不在 F-026 同时实现两种服务模型。

### 5.2 Linux/服务器候选模式

```text
程序：/opt/agent-audit
配置：/etc/agent-audit
数据：/var/lib/agent-audit
日志：/var/log/agent-audit
```

### 5.3 Docker/NAS 候选模式

- 镜像内程序只读；
- `/var/lib/agent-audit` 使用 Named Volume 保存数据库和应用状态；
- 用户明确选择的企业资料目录以只读 Bind Mount 接入；
- Secret 使用 Compose Secret，不写入镜像、Workspace、SQLite 或导出。

F-026 只先完成 Windows 桌面主路径；Linux、Docker/NAS 保留相同 Workspace 契约，待 Windows 干净机通过后进入 F-029，避免三平台同时开发导致主线失控。

## 6. 首次启动必须足够简单

首次打开只展示四步向导，不显示 JSON、端口或环境变量：

```text
欢迎
→ 选择 AI
→ 导入资料
→ 确认角色与规则
→ 运行首次验收
```

完成后进入现有 Guided Audit。高级 Provider、Contract JSON、完整 Trace、Benchmark 和历史继续存在，但放入高级设置或证据工作区。

## 7. AI 自动发现与手动连接

### 7.1 自动发现（默认）

“自动检测本机 AI”只做有限、可解释的发现：

1. 检查已知本机 Ollama 地址 `127.0.0.1:11434`；
2. 调用 Ollama `/api/tags` 获取真实已安装模型，不扫描模型文件夹；
3. 对用户选择或候选模型执行现有 Provider Readiness；
4. 根据固定的 connectivity、Tool Calling、strict JSON 结果显示“完全兼容 / 部分兼容 / 不可用”；
5. 若只有一个完全兼容模型，可默认高亮，但必须由用户点击确认；
6. 保存已确认的 Provider 配置，后续启动只检查状态，不擅自换模型。

自动发现不得扫描整个局域网、枚举硬盘、静默下载模型、重试到通过、修改模型输出或自动 fallback。

### 7.2 手动连接（简化）

普通表单只保留：

- 类型：本机 Ollama / 内网 AI / 云端 AI；
- 地址；
- 模型下拉框或模型名；
- API Key（仅需要时）；
- “测试连接并检查兼容性”。

Target Provider 与 Attack Provider 默认使用同一个已确认模型，但后端仍分别执行 Readiness；需要分开时才展开高级设置。API Key 使用操作系统 Credential Store 或等价安全边界，不进入普通配置文件、日志、数据库和导出。

## 8. 文档手动选择与自动发现

### 8.1 默认：导入副本

用户点击“导入资料”，通过系统原生文件/文件夹选择窗口选择资料。软件先显示预览，再把确认的文件复制为 Workspace 快照。这样即使原目录移动、U 盘拔出或 NAS 暂时不可用，历史验收仍可复现。

### 8.2 高级：连接共享文件夹

管理员可选择本地目录或已挂载的企业共享目录，软件只在该明确目录内只读扫描。第一版不扫描整个硬盘或局域网，也不主动连接未知 NAS。

### 8.3 自动处理边界

自动能力可以：

- 枚举所选目录中的受支持文件；
- 显示文件数、大小、类型、无法读取项和重复展示名；
- 根据目录结构生成部门/来源候选；
- 提示需要补充 owner、sensitivity、trust level 的资料；
- 在用户确认后建立索引。

自动能力不能：

- 把 LLM 猜测的部门、敏感等级或访问权限直接写成 active Contract；
- 未经确认持续监控整台电脑；
- 因解析失败跳过文件后仍声称全部导入成功；
- 把原始绝对路径写进公开报告。

首版文档格式按真实解析能力逐项验收。纯文本 `.txt/.md` 可优先；带文字层的 `.docx/.pdf` 后续按同一 Import Contract 增加。扫描版 PDF/OCR 未完成前必须显示“不支持”，不能把空文本当成功。

## 9. 小企业日常使用流程

### 9.1 第一次部署

1. 安装并打开 AgentAudit；
2. 自动发现本地模型，或手动连接内网/云端模型；
3. 运行 Readiness，确认兼容性；
4. 新建 Workspace 并导入经授权资料；
5. 从“管理层、财务、销售、客服、普通员工、外部访客”模板开始配置角色；
6. 审核文档 owner、敏感等级和访问规则；
7. 运行一条 Guided Audit 和首次 Acceptance Run。

### 9.2 日常操作

- 打开桌面软件；
- 选择 Workspace；
- 查看模型和资料是否就绪；
- 运行 Guided Audit 或完整 Acceptance Run；
- 查看 Finding 和 Replay；
- 按需导出 JSON/Markdown；
- 关闭软件。

软件更新只替换 Application Core；Workspace、Provider 选择、SQLite 历史和用户导出必须保留。

## 10. 最小企业安全与运维边界

Windows 单用户桌面主路径只供当前登录用户使用：

- Sidecar 只监听 `127.0.0.1`；
- 桌面壳启动成功后才显示主窗口；关闭主窗口时终止自己启动的 Sidecar；
- API Key 使用系统凭据存储；
- Workspace、日志和导出遵守当前用户文件权限；
- 不默认开放局域网端口；
- 不实现完整 IAM、SSO、多租户或员工账号系统。

若以后进入局域网多人模式，必须作为独立功能增加身份验证、TLS、管理员/只读角色、备份和访问日志，不能直接把本地 Sidecar 改成 `0.0.0.0` 就宣称企业可用。

## 11. 固定功能顺序

### F-026 桌面壳与可移植 Workspace 基础

- 新增 Tauri 独立窗口和 Windows 安装包；
- Python API 打包为 Sidecar，窗口负责启动、健康检查和关闭；
- 将 Demo/Data/History 路径从仓库布局迁移到显式 Workspace；
- 使用系统应用数据目录和原生打开/保存对话框；
- 保留现有 Guided Audit 和高级证据能力；
- 不实现模型自动发现和企业文档解析。

### F-027 首次启动向导与模型发现

- 自动发现本机 Ollama 与真实模型列表；
- 简化手动连接；
- 复用 Provider Readiness 形成兼容性推荐；
- 保存用户确认的配置，不自动切换 Provider；
- 完成“安装后无需环境变量即可选择模型”的桌面主链。

### F-028 企业 Workspace 与资料导入

- 原生文件/文件夹选择；
- 默认导入副本，高级只读连接指定目录；
- 文档预览、解析结果、失败项和元数据确认；
- 角色/资源模板与 Security Contract Preview；
- 不连接任意生产 Agent，不自动决定权限。

### F-029 小企业安装、迁移与运维

- Windows 干净机安装/升级/卸载验收；
- Workspace 备份、恢复和迁移；
- Secret 存储与脱敏诊断；
- 评估 Linux、Docker/NAS 的实际需求后只实现有证据的第二部署路径；
- 局域网多人模式继续作为条件项，不与单用户桌面主链混做。

## 12. F-026 已锁定的公共接口

- `AppPaths`：config/data/log/default workspace 的系统路径；
- `WorkspaceManifest`：Workspace ID、名称、版本和相对目录，不含开发机绝对路径；
- `WorkspaceService`：create/open/list，不负责模型或安全判定；
- `DesktopRuntimeStatus`：Sidecar starting/ready/failed/stopped；
- 桌面壳只负责生命周期、系统对话框和保存文件，业务 DTO 继续来自 `packages/contracts`；
- API 不再通过 `Path(__file__).parents[...]` 把仓库当运行时数据目录；Demo 作为可导入的内置示例 Workspace，而不是不可替换的生产数据根。

## 13. 验收标准

M6 完成至少证明：

1. 在没有仓库、Python、Node 和手动环境变量的 Windows 干净用户环境安装；
2. 双击图标出现独立桌面窗口，不打开外部浏览器或命令行窗口；
3. 窗口启动/关闭能正确管理 Sidecar，不遗留监听进程；
4. 默认数据写入系统应用数据目录，程序目录保持可替换；
5. 从任意目录创建、移动和重新打开 Workspace，历史与 Contract 不丢失；
6. 自动发现只识别本机 Ollama 候选，手动连接保持简单，任何选择都由用户确认；
7. 导入只扫描用户选择的目录，失败项可见，不伪造解析成功；
8. 导出、SQLite 和日志不包含 API Key、Authorization header 或开发机固定路径；
9. Guided Audit、Finding、Replay、Acceptance Run 与现有确定性结论不退化；
10. 保持 Python tests、TypeScript typecheck/build、桌面启动 E2E、安装包 smoke 和 diff check 通过；
11. 本地模型结果如实记录，不用 retry、fallback、输出修补或修改 Ground Truth 制造通过。

## 14. 明确不做

- 不重写为两套 Vue/Qt UI；
- 不把整个 LLM 打入第一版安装包；
- 不扫描整块硬盘、整个局域网或任意外部 Endpoint；
- 不自动判断企业真实权限并直接发布 Contract；
- 不默认开放局域网访问；
- 不做完整 IAM、SSO、多租户、云同步、消息队列或微服务；
- 不因桌面化删除 CLI/CI、API 契约或现有测试；
- 不把 Tauri/WebView 描述成纯 Win32 原生控件；对用户承诺的是“独立桌面窗口、无需外部浏览器”，不是虚假的技术描述。

## 15. 停检点

F-026 已按 `docs/features/F-026-desktop-portable-workspace.md` 锁定 Windows 单用户桌面主路径和上述公共接口，并由三个互斥代理完成 Desktop、Backend/Workspace、Test 垂直切片。当前构建机上的 release 与 NSIS 安装/卸载已通过，尚缺另一台无仓库、无 Python/Node 的干净 Windows 复核。

该停检点是 F-026 启动时的历史决定。2026-08-28 用户在保留干净 Windows 未验收事实的前提下，明确授权按 `docs/M6_LOCAL_DUAL_PLATFORM_PRODUCT_PLAN.md` 启动 F-027；企业文档解析和第二平台打包仍分别留在 F-028/F-029。
