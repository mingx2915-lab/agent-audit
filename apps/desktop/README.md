# 知盾 AgentAudit 桌面端

这是 Windows/Linux 单用户桌面交付入口。Tauri 负责独立窗口、系统对话框和 Python API Sidecar 生命周期；Vue Renderer 由 `apps/web` 提供，业务规则由 `apps/api` 提供。产品窗口不依赖外部浏览器，Workspace 数据也不写入安装目录。

## 用户运行边界

- Windows NSIS 安装包按当前 Windows 用户安装，普通用户无需 Python、Node、Rust 或外部浏览器；
- Linux 提供 x86_64 `.deb` 与 AppImage 目标；普通用户运行时无需 Python、Node 或 Rust；
- Windows 默认用户数据位于 `%LOCALAPPDATA%\AgentAudit`；Linux 遵守 XDG data/config/state 目录，不依赖仓库路径或安装目录；
- AI Runtime 不打进应用包。应用只保存用户显式确认的非 Secret Ollama 配置，不静默下载模型或自动 fallback；
- 桌面壳只拥有它启动的本机 Sidecar，不会启动、下载、关闭或修改外部 Ollama。
- Workspace 备份是用户显式发起的 ZIP 导出；恢复先 Preview，再确认创建新 Workspace，切换由用户显式完成。

## 本地开发

先准备项目内 Rust/Tauri 工具链和已构建的 Sidecar，再运行：

```powershell
npm run desktop:dev
```

开发窗口仍然使用 Vite Renderer，但不会自动启动 Python 或打开外部浏览器。生产构建使用：

```powershell
npm run desktop:build
```

成功的 Windows release 会在 Tauri target 的 `release/bundle/nsis` 下生成 current-user setup；Linux release 会在 `release/bundle/deb` 与 `release/bundle/appimage` 下生成目标工件。仓库内可交付副本统一放到 `artifacts/desktop/generated/`；该目录和 Sidecar 二进制均为可重建产物，不提交 Git。

先使用项目内 Python 环境构建 Sidecar（不会安装系统全局依赖）：

```powershell
.\scripts\build-sidecar.ps1
```

脚本使用 [agent-audit-sidecar.spec](scripts/agent-audit-sidecar.spec) 生成无控制台窗口的 PyInstaller 单文件，并把仓库 `data/demo` 作为只读 packaged seed 放入 Sidecar 的 `demo-seed` 资源目录。Sidecar 入口应在首次启动时将该 seed 交给 `WorkspaceService.ensure_default`；seed 不是用户 Workspace，升级时不得覆盖已存在 Workspace。

构建前应将带目标三元组后缀的 Sidecar 放入 `src-tauri/binaries/`，例如：

```text
src-tauri/binaries/agent-audit-sidecar-x86_64-pc-windows-msvc.exe
```

Sidecar 由桌面端传入固定的 `--host 127.0.0.1 --port <port> --workspace <path> --ready-file <path>` 参数。桌面窗口关闭时只终止本次启动的 Sidecar，不会操作外部 Ollama。

### Linux 构建

PyInstaller 与 Tauri 都必须在真实 Linux x86_64 环境执行；当前 Windows 主机不能交叉生成可验收的 Linux 工件。准备好 Linux 环境和项目依赖后运行：

```bash
npm run desktop:build:linux
```

该入口会先构建 Linux Sidecar，再执行 contracts、Web 和 Tauri 的 Linux 构建；需要单独重建 Sidecar 时运行 `bash apps/desktop/scripts/build-sidecar.sh`。

`build-sidecar.sh` 默认写入 `apps/desktop/src-tauri/binaries/agent-audit-sidecar-x86_64-unknown-linux-gnu`，也可用 `PYTHON_BIN` 和 `TARGET_TRIPLE` 显式覆盖。脚本不会下载或启动 Ollama；最终 `.deb`/AppImage 仍应在真实 Linux 目标环境进行安装、启动、关闭和 Workspace 迁移 smoke。

### Workspace 备份与恢复

在“高级设置”中展开 Workspace 卡片：

1. “备份当前 Workspace”从 API 获取完整 ZIP，再由系统保存对话框选择位置；
2. “选择备份 ZIP”只读取所选归档并显示只读 Preview；
3. “确认恢复为新 Workspace”创建新的副本，不覆盖当前数据；
4. “切换到此 Workspace”才会让桌面壳保存相对指针、重启自己的 Sidecar 并刷新窗口。

取消任一对话框或 Preview 不会写入 Workspace。绝对路径只存在于 Rust 原生边界，API 和归档仅使用相对 Workspace 标识。
