# F-029 双平台安装、Workspace 备份恢复与本地运维

- 状态：External Validation Pending
- 所属里程碑：M6 本地双平台产品化
- 负责人：主代理统筹；Backend / Desktop-Web / Test 三个 Luna Max 分工
- 相关决定：`docs/M6_LOCAL_DUAL_PLATFORM_PRODUCT_PLAN.md`、`docs/ARCHITECTURE.md`、`docs/ACCEPTANCE.md`

## 用户价值

小企业管理员应当像使用普通本地软件一样安装、备份、迁移和恢复知盾 AgentAudit，而不需要仓库、Python、Node、外部浏览器或公网。企业资料、Security Contract、历史 Finding 和 Replay 必须随 Workspace 迁移，并与应用安装目录和 AI Runtime 保持分离。

该能力直接支撑比赛的技术实现、实用价值和用户体验：它证明当前安全闭环不是只能在开发机运行的网页 Demo，而是可以落到 Windows/Linux 单机环境的本地产品。

## 范围

### 1. 可移动 Workspace 备份与恢复

- 用户在桌面窗口中显式选择“备份当前 Workspace”，生成一个标准 ZIP 工件；
- ZIP 保存完整 Workspace 快照，包括 manifest、企业资料、Security Contract、Case/Profile/Ground Truth、SQLite History、Finding/Replay 与 Workspace 导出；
- 用户显式选择 ZIP 后先执行只读 Preview，显示 Workspace 名称、ID、Contract、文档数量、History 是否存在和归档大小；
- 用户确认恢复后，在应用数据目录的 `workspaces/` 下创建一个新的 Workspace，不覆盖当前 Workspace；
- 恢复成功后由用户显式切换到新 Workspace，桌面壳只重启自己持有的 Sidecar，并在就绪后刷新窗口；
- Workspace manifest 和本地激活记录只使用相对目录，不把开发机或来源机器绝对路径写入工件；
- 同一 ZIP 可在 Windows 与 Linux 间迁移，恢复后的 Contract、History、Finding/Replay 和资料语义保持一致。

### 2. Windows/Linux 同源桌面交付

- Windows x64 继续生成 current-user NSIS `setup.exe`，不要求管理员权限；
- Linux x86_64 增加 `.deb` 与 AppImage 构建配置和 Linux 原生 Sidecar 构建脚本；
- Windows/Linux 共用 Vue Renderer、FastAPI Core、Workspace 格式、DTO 和安全判定，不维护两套业务实现；
- Linux 遵守 XDG data/config/state 路径，Sidecar 只绑定 `127.0.0.1`，窗口退出后清理自己启动的 Sidecar 进程树；
- 平台安装、升级和卸载只处理 Application，不覆盖或删除用户 Workspace；
- 原生文件对话框继续用于资料导入、备份保存和恢复选择，不打开外部浏览器。

### 3. 真实构建边界

- Windows 构建和当前机 Desktop/Sidecar smoke 在当前 Windows 环境执行；
- PyInstaller 不是 cross-compiler，Linux Sidecar、`.deb` 与 AppImage 必须在真实 Linux x86_64 环境构建；
- 当前主机没有 WSL、Linux 主机或 Docker，因此 Linux 工件和干净 Linux 安装 smoke 是明确的外部验收项；在真实工件出现前，本功能保持 In Progress，不以配置文件、静态测试或 Windows 产物冒充 Linux 证据。

## 非目标

- 不扩展为企业 AI 综合扫描平台、局域网扫描器或多租户 SaaS；
- 不做服务器版、PostgreSQL、Redis、任务队列、在线账户或自动更新平台；
- 不做 RPM、Snap、Flatpak、macOS、ARM64；
- 不静默下载模型，不把大型 LLM 打进安装包，不启动或关闭外部 Ollama；
- 不做自动云备份、目录持续同步、增量备份、加密归档、签名包或复杂版本迁移框架；
- 当前唯一可持久化 Runtime 是不含 Secret 的 Ollama，因此本功能不先造一个无人使用的 Credential Store 空壳。需要 API Key 的 Provider 进入产品持久化范围时，必须另立功能接入 Windows Credential Manager/DPAPI 与 Linux Secret Service，禁止写入 JSON、SQLite、Workspace、日志或导出。

## 前后端与数据影响

- Web：新增紧凑的“Workspace 备份与恢复”区；显式备份、选择归档、Preview、确认恢复和切换；默认 Guided Audit 主线不被抢占；
- API：新增 Workspace archive 导出、只读 Preview 与 copy-as-new Restore；不接受本机绝对路径；
- Desktop：新增原生保存/打开归档、当前 Workspace 相对指针、Sidecar 切换和 Linux 生命周期；
- Contracts：共享 Backup Preview、Restore Result、Workspace Summary；
- Data：ZIP 内保持现有 portable Workspace 目录结构；恢复目录由应用生成稳定相对名称；
- Build：增加平台专用 Tauri 配置、Linux Sidecar/build 脚本和可复现说明。

## API 或交互契约

### 共享 DTO

```text
WorkspaceSummary
  id, name, relativeDirectory, contractId, contractVersion,
  documentCount, historyIncluded, active

WorkspaceBackupPreview
  formatVersion, workspace, archiveSizeBytes, createdAt

WorkspaceRestoreResult
  workspace, restored, restartRequired
```

`relativeDirectory` 只允许单个 `workspaces/` 子目录名；不返回绝对路径。`historyIncluded` 只说明归档中是否有 History 数据，不把它作为 Finding 或 Gate。

### API

```text
GET  /api/workspace
GET  /api/workspace/backups/current
POST /api/workspace/backups/previews     Content-Type: application/zip
POST /api/workspace/restores             Content-Type: application/zip
```

- `GET /api/workspace/backups/current` 返回完整 ZIP 二进制；
- Preview 是纯读取，不写磁盘、不切换 active Workspace、不调用 Provider；
- Restore 创建新目录；无 Workspace 返回 `409`，非法/不兼容归档返回 `422`，存储错误返回 `500`；
- API 不能在运行中自行终止 Sidecar，切换由 Desktop command 完成；普通开发 Web 可恢复但只显示“下次从该 Workspace 启动”的可读边界。

### Desktop command

```text
save_workspace_backup(bytes, suggested_name)
select_workspace_backup()
activate_workspace(relative_directory)
```

- 取消原生对话框不产生 API 写入；
- `activate_workspace` 只接受 API 返回的相对目录，验证目标是应用 `workspaces/` 下的有效 manifest，原子保存 active 指针后重启 Sidecar；
- Desktop 不解析 Contract、Finding 或 Replay，也不复制后端恢复规则。

## 实施任务

- [x] ~~锁定共享 DTO 与 ZIP/错误契约；~~
- [x] ~~实现 WorkspaceArchiveService、API 和 copy-as-new 原子恢复；~~
- [x] ~~实现桌面原生保存/选择/切换和 Web 简明交互；~~
- [x] ~~将 Tauri 配置拆为通用、Windows、Linux 三层，并补 Linux Sidecar/build 脚本；~~
- [x] ~~实现 Windows/Linux Sidecar 关闭语义及 XDG 路径测试；~~
- [x] ~~更新桌面 README、架构与验收文档；~~
- [x] ~~运行 Python unit/integration、TypeScript、Web build、Playwright、Rust 和 Windows artifact smoke；~~
- [x] 在 Linux x86_64 环境生成真实 Sidecar、`.deb`、AppImage 并执行启动/退出/迁移 smoke（由 F-055 真实 Debian VM 证据补齐）；
- [ ] 在另一台干净 Windows 环境补 NSIS 安装/升级/卸载证据。

## 验收标准

- [x] ~~备份包含完整 Workspace，Preview 不写磁盘、不调用 Provider；~~
- [x] ~~Restore 永不覆盖 active Workspace，失败不留下可被列出的半成品；~~
- [x] ~~恢复后 Contract、24 Case、SQLite History、Finding/Replay 和导入文档与源 Workspace 一致；~~
- [x] Windows→Linux、Linux→Windows 的归档格式相同，不含来源绝对路径（F-055 生产 Archive roundtrip 证据）；
- [ ] 用户一次确认即可切换恢复后的 Workspace，切换后窗口重新就绪且无旧 Sidecar 残留（实现与 E2E 已通过，待两个真实平台 artifact smoke）；
- [ ] Windows NSIS 和 Linux `.deb`/AppImage 的真实工件均可在目标环境安装或运行；
- [ ] 目标机无需仓库、Python、Node、Rust 或外部浏览器；
- [ ] 升级不覆盖 Workspace，卸载默认保留企业数据；
- [ ] 离线且已有本地 Ollama 时 Guided Audit 主链可运行；
- [ ] 自动测试、关键 E2E、构建检查、artifact smoke 与 `git diff --check` 通过（共享代码与 Windows 已通过，Linux artifact 待补）。

## 验证证据

- 当前自动测试：512 passed、2 skipped、12 Playwright passed；两个 skip 分别是未显式提供 Desktop artifact 的常规全量运行，以及非 Linux/未提供 Linux artifact；
- Windows 工件：F-029 Sidecar、release Desktop EXE 与 current-user NSIS 已重建；指定 release EXE 的真实启动 smoke 1 passed，默认 Workspace 初始化成功且退出后无 Desktop/Sidecar 残留；
- Linux 工件：后续 F-055 已在真实 Debian 12 / Linux 6.1 x86_64 VM 构建并验证 Sidecar、AppImage 和 `.deb`，最终机器证据为 `22 passed / 0 failed / 0 not_verified`；当时的无 Linux 环境描述仅作为 2026-08-28 历史保留；
- 自动命令：全量 pytest、全量 Playwright、compileall、pip check、根 typecheck、Web production build、rustfmt、offline cargo check、Linux shell syntax、Windows Sidecar/NSIS build 与 diff check 均通过；Web build 只有既有的 chunk size warning，pytest 只有既有 Starlette/httpx deprecation warning；
- 人工/外部步骤：真实 Windows Desktop 启动/关闭已验证；备份→Preview→恢复→切换的生产 API + Renderer 链由 E2E 验证，后续 F-055 已补齐真实 Linux 和跨平台 Archive 证据。另一台干净 Windows 与增强 pointer Debian 重跑仍待对应目标环境。

## 官方构建依据

- Tauri 官方平台配置支持 `tauri.windows.conf.json` 与 `tauri.linux.conf.json` 合并主配置；
- Tauri 官方 Linux 文档要求在 Linux 构建 AppImage/`.deb`，并建议使用兼容基线较旧的发行版；
- PyInstaller 官方明确不是 cross-compiler；Windows Sidecar 必须在 Windows 构建，Linux Sidecar 必须在 Linux 构建；
- Linux 目录遵守 freedesktop.org XDG Base Directory 规范。

参考：

- https://v2.tauri.app/reference/config/
- https://v2.tauri.app/distribute/appimage/
- https://v2.tauri.app/distribute/debian/
- https://v2.tauri.app/start/prerequisites/
- https://pyinstaller.org/en/stable/
- https://specifications.freedesktop.org/basedir/0.8/

## 实施记录

- 2026-08-28：启动 F-029。当前 Windows 主机可继续实现和验证 Windows/共享代码，但没有 WSL、Docker 或 Linux 主机；Linux 真实工件保持外部验收项。
- 2026-08-28：为遵守克制实现原则，Credential Store 改为“出现真实 Secret Provider 持久化需求时另立功能”，本功能不实现没有消费者的安全空壳。
- 2026-08-28：共享实现与当前 Windows 构建完成。主审修正了两个会破坏迁移的路径偏差：Restore 统一写入 `default_workspace_dir.parent`，Linux Rust/Python 统一使用 XDG 下小写 `agent-audit`。SQLite 只归档 online backup 生成的主库，不携带 WAL/SHM。
- 2026-08-28：F-029 保持 In Progress；未生成 Linux 工件，也未完成另一台干净 Windows 安装/升级/卸载证据。
- 2026-08-28：共享实现无剩余可在当前主机推进的工作；因缺少真实 Linux 与另一台干净 Windows 环境，状态转为 Blocked。该状态不等于完成，外部证据补齐后再恢复验收。
- 2026-08-31：F-055 已补齐 Debian Sidecar/`.deb`/AppImage、XDG、Secret Service、GTK 原生选择和双向 Archive 证据。状态由 Blocked 改为 External Validation Pending；仍缺另一台干净 Windows 复核，以及增强后非默认 active Workspace pointer 的 Debian 真机重跑。
