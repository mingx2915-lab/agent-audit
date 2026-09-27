# F-026 桌面壳与可移植 Workspace 基础

- 状态：Implementation Complete / External Acceptance Pending
- 所属里程碑：M6
- 负责人：主代理监督；Desktop、Backend/Workspace、Test Luna Max 按互斥范围实现
- 相关决定：`docs/M6_SMALL_BUSINESS_DESKTOP_PLAN.md`

## 用户价值

小企业管理员不再打开浏览器、输入本机 URL 或运行 Python/Node 命令。安装后双击知盾 AgentAudit 桌面图标即可进入现有 Guided Audit；软件、AI Runtime 和企业 Workspace 分离，移动安装目录或 Workspace 不破坏 Contract、History 与导出。

## 范围

- 新增 `apps/desktop` Tauri 桌面壳，Windows 用户看到独立窗口而非外部浏览器；
- 复用现有 Vue Renderer，不重写 Security Contract、Trace、Finding、Replay 和 Acceptance UI；
- 将 Python/FastAPI 打包为 Sidecar，由桌面壳启动、等待 ready、关闭时终止；
- Sidecar 只监听 `127.0.0.1`，内部端口和进程对普通用户不可见；
- 新增系统路径解析和显式 Workspace 领域边界；Windows 默认数据位于 `%LOCALAPPDATA%\AgentAudit`，测试/开发可用 `AGENT_AUDIT_HOME` 显式覆盖；
- 默认 Workspace 由随应用分发的合成 Demo Seed 首次创建，后续启动读取 Workspace，不再把开发仓库路径当作安装运行时数据根；
- Workspace 使用 manifest 与相对目录表达 documents、contract、cases、history、exports；
- 现有 API、CLI/CI 和浏览器开发入口继续可用；桌面窗口为普通用户默认交付路径；
- 产出可双击的 Windows 安装包或 setup executable，并在当前机器执行安装包/便携构建 smoke。

## 非目标

- 不实现 F-027 的 Ollama 自动发现、模型下载或首次启动 Provider 向导；
- 不实现 F-028 的 `.docx/.pdf` 企业资料解析或共享目录同步；
- 不实现局域网多人服务、IAM、SSO、管理员/Viewer 账户或 TLS；
- 不开放任意外部 Endpoint，不连接真实邮件、CRM 或生产数据；
- 不改写安全判定，不增加攻击类别，不为本地小模型增加 retry/fallback；
- 不同时开发 Electron、PySide/Qt、Linux/macOS 安装包或 Docker/NAS 新路径。

## 公共接口与目录约定

### Python

- `agent_audit_api.app_paths.AppPaths`
  - `config_dir`
  - `data_dir`
  - `logs_dir`
  - `default_workspace_dir`
- `agent_audit_api.app_paths.resolve_app_paths(home_override: Path | None = None) -> AppPaths`
- `agent_audit_api.workspace.WorkspaceManifest`
  - `id: str`
  - `name: str`
  - `version: int`
  - `documents_dir: str = "documents"`
  - `contract_dir: str = "contract"`
  - `cases_dir: str = "cases"`
  - `history_dir: str = "history"`
  - `exports_dir: str = "exports"`
- `agent_audit_api.workspace.AuditWorkspace`
  - runtime-only `root: Path`
  - validated `manifest: WorkspaceManifest`
  - methods/properties resolve only declared relative members below `root`
- `agent_audit_api.workspace.WorkspaceService`
  - `create(root, name, seed_dir=None)`
  - `open(root)`
  - `ensure_default(seed_dir)`
- `agent_audit_api.desktop_sidecar`
  - executable/module entry accepts only locked local lifecycle arguments needed by Desktop；不接受任意 target、case 或 Contract 输入。

### Workspace layout

```text
workspace/
├─ agent-audit-workspace.json
├─ documents/
│  ├─ actors.json
│  ├─ knowledge_documents.json
│  └─ customers.json
├─ contract/
│  └─ security_contract.json
├─ cases/
│  ├─ attack_cases.json
│  ├─ target_profiles.json
│  └─ ground_truth_cases.json
├─ history/
│  └─ agent_audit.sqlite3
└─ exports/
```

Manifest 和业务 DTO 不保存 Workspace 绝对路径。绝对路径只存在于当前机器的本地运行配置和进程内 `AuditWorkspace.root`。

### Desktop/Web

- Tauri Product Name：`知盾 AgentAudit`；Identifier：`com.agent-audit.desktop`；代码目录 `apps/desktop`；
- 桌面壳只负责窗口、Sidecar 生命周期、系统路径/对话框和启动错误；不复制业务 DTO 或权限判断；
- Renderer 的 API Base 在普通 Web 开发时继续使用同源 `/api`，在桌面运行时使用桌面壳提供的本机 Sidecar origin；不在源码写开发机绝对路径；
- 窗口关闭只终止本次桌面壳创建的 Sidecar，不结束外部 Ollama；
- Sidecar ready 失败显示可读桌面错误，不打开外部浏览器、不静默切换到开发服务器。

## 数据与迁移边界

- 仓库 `data/demo` 仍是合成 Seed 的开发源；桌面安装包将它作为只读资源分发；
- 第一次启动把 Seed 复制成默认 Workspace，之后只读取 Workspace 快照；应用升级不覆盖已存在 Workspace；
- 现有默认开发/测试调用保持兼容，但所有 Loader 增加显式 Workspace/Data Path 注入，桌面生产入口必须使用 Workspace；
- F-026 不迁移用户当前仓库内 `data/runtime/agent_audit.sqlite3`；桌面默认创建独立 History，旧数据仍可由开发模式读取；
- 不使用文档哈希或工件哈希管理迁移；已存在 manifest 时不重复 Seed，结构错误直接给出可诊断错误。

## 实施任务

- [x] ~~主代理创建 F-026 文档并锁定 Desktop/API/Workspace 公共边界~~
- [x] ~~Backend/Workspace Luna Max 实现 AppPaths、Workspace、Loader 注入和 Desktop Sidecar 入口~~
- [x] ~~Desktop Luna Max 实现 Tauri 窗口、Sidecar 生命周期、Renderer API Base 与 Windows bundle 配置~~
- [x] ~~Test Luna Max 覆盖路径、Workspace、Loader、生命周期契约和旧主线回归~~
- [x] ~~主代理在项目内 `.tools/` 准备 Rust/Tauri/PyInstaller 所需工具，不修改系统全局工具链~~
- [x] ~~主代理审查 Sidecar/Workspace 信任边界、整合共享配置并构建真实 Windows bundle~~
- [x] ~~完成当前 Windows 环境的 Python/Web/E2E/Desktop/安装包验收~~
- [ ] 在另一台无仓库、无 Python/Node 的干净 Windows 环境安装并复核
- [x] ~~更新 README、STATUS、FEATURES、ROADMAP、ARCHITECTURE、ACCEPTANCE 并提交 Git~~

## 验收标准

- [x] 从项目生成 Windows 桌面可执行文件和 NSIS 安装包，普通用户无需安装 Python、Node 或打开浏览器；
- [x] 双击后只出现 AgentAudit 桌面窗口，不弹出命令行和外部浏览器；
- [x] Desktop 启动自己的 Sidecar，API ready 后加载现有 Vue，关闭后该 Sidecar 不再监听；
- [x] Sidecar 仅绑定 `127.0.0.1`，不结束或修改外部 Ollama；
- [x] 默认路径使用 `%LOCALAPPDATA%\AgentAudit` 或测试显式覆盖，不读取开发机固定盘符；
- [x] 首次创建默认 Workspace，第二次打开不覆盖 Contract/History；
- [x] Workspace 移动到其他目录后可重新打开，manifest 与导出不包含原绝对路径；
- [x] Desktop 生产入口的 actors/documents/customers/contract/cases/profiles/ground truth/history 全部来自同一 Workspace；
- [x] Guided Audit、Finding、Replay、Acceptance Run 与 24 Case 行为不因桌面化改变；
- [x] Sidecar 缺失、Workspace 无效或内部端口占用时错误可诊断，不打开开发服务器、不 fallback；
- [x] 现有 pytest、compileall、pip check、typecheck、production build 和浏览器 E2E 继续通过；
- [x] 新增 Workspace 单元/集成测试、Desktop 配置测试、桌面启动/关闭 smoke 和 bundle 内容检查；
- [x] Windows 当前机安装/启动/退出 smoke 通过，并因本机没有干净 Windows 环境而如实保留 F-026 未完成；
- [x] `git diff --check` 和密钥/开发机绝对路径扫描通过。

## 验证证据

- Python：`.venv\Scripts\python.exe -m pytest -q` 为 `416 passed, 1 skipped`；默认跳过项只是在未指定真实桌面 `.exe` 时不冒充 bundle smoke。指定本次 release `.exe` 后，Desktop 配置与真实启动 smoke 为 `7 passed`；
- Python 静态与环境：`compileall`、`pip check` 通过；
- Web/Desktop Renderer：根 `npm run typecheck`、`npm run build` 通过，Vite 仅保留既有大 chunk warning；
- 用户主链：`npm run test:e2e` 为 `7 passed`，Guided Audit、Finding、Replay、Contract Editor、Acceptance Run、窄屏和 Provider 错误路径未回退；
- Rust：项目内 Rust/MSVC 工具链完成 `cargo check`、release 编译、`rustfmt --check`；未安装系统全局 Rust；
- Sidecar：PyInstaller one-file 真实启动后状态为 ready，`GET /api/health` 为 200，packaged `demo-seed` 首次生成完整 Workspace，按所属 PID 结束进程树后无 Sidecar 残留；
- Windows bundle：真实 release 桌面程序启动后创建默认 manifest 并保持运行，关闭后 Desktop/Sidecar 均无残留；NSIS 安装器在当前用户环境完成安装、启动、Workspace seed、退出和卸载，安装目录与注册表项清理完成；
- 安装器副本：`artifacts/desktop/generated/知盾 AgentAudit_0.1.0_x64-setup.exe`（构建产物被 Git 忽略，可由 `desktop:sidecar` 与 `desktop:build` 重建）；
- 未完成证据：当前 Windows 版本没有可用 Windows Sandbox，也没有第二台干净 Windows，因此尚未证明“无仓库、无 Python/Node”的目标机安装；F-026 不勾选。2026-08-28 用户已将该项转为外部验收债务并授权 F-027 继续。

## 实施记录

- 2026-08-27：用户明确授权进入 M6，并要求三个 Luna Max 开发；需要的工具下载到项目目录。F-026 不提前实现 F-027/F-028。
- 2026-08-27：三个 Luna Max 分别完成 Backend/Workspace、Desktop 和 Tests；主代理审查并修正 Windows manifest 路径、Seed 原子创建、PyInstaller frozen import/logging、Tauri plugin 配置与 one-file 进程树清理。
- 2026-08-27：项目内 Rust/MSVC/PyInstaller 工具链生成真实 Sidecar、release Desktop 与 NSIS setup；当前机安装、首次启动、Workspace seed、退出、卸载完成。因无可用 Windows Sandbox/第二台干净 Windows，功能保持 In Progress。
- 2026-08-28：用户将产品方向明确为单一聚焦的本地双平台软件，并授权继续开发。F-026 的干净 Windows 外部安装证据仍未完成，因此本功能不勾选；其实现状态改为 `Implementation Complete / External Acceptance Pending`，不再作为共享 F-027 代码演进的阻塞门。
