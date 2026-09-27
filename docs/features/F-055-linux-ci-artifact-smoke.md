# F-055 Linux CI 构建与 artifact smoke

- 状态：Completed
- 所属里程碑：M6
- 负责人：主代理
- 相关决定：执行 `docs/NEXT_AUTOMATED_DELIVERY_PLAN.md` 的 P4

## 用户价值

Linux 用户应获得与 Windows 同一源码、同一 Workspace 格式和同一安全边界的可安装桌面程序。发布证据必须来自真实 Linux x86_64 runner 构建和运行，不能用 Windows cross-compile、静态配置检查或测试替身冒充。

## 公共约定

- Linux 使用 XDG config/data/state 目录，不写 Windows 路径或用户仓库路径；
- Linux 构建统一使用 Rust `1.88.0`；该版本与当前锁定的 Linux 依赖 MSRV 一致，不通过降级传递依赖规避编译要求；
- Sidecar 仍只监听 `127.0.0.1`，由 Desktop 启动、探活和终止自己的精确进程树；
- Bearer/x-api-key 只进入 Linux Secret Service，不允许明文配置 fallback；
- `.deb`、AppImage 与 Sidecar 均从当前 commit 的真实 Linux x86_64 runner 生成并记录 SHA-256；
- Windows 与 Linux 继续使用同一相对路径 Workspace manifest 和 F-054 schema migration；
- CI 缺少图形会话或 Secret Service 时，对应测试明确标为环境未满足，不得推断 passed。

## 范围

- 固定 Linux 构建依赖和可重复的 Sidecar/Tauri build 脚本；
- CI 生成 `.deb`、AppImage、Sidecar、checksums 与机器可读 artifact smoke 结果；
- Linux artifact 启动、Workspace seed/migration、health、关闭和残留进程验证；
- XDG config/data/state 与 active Workspace pointer 验证；
- Secret Service 存取/清除和不可用时的可读错误验证；
- Windows ZIP→Linux Restore 与 Linux ZIP→Windows Restore 互通验证。

## 非目标

- 不自动安装或修改用户系统级 Linux 依赖；
- 不引入 Snap/Flatpak、自动更新、代码签名或远程上传；
- 不用 Wine、Windows cross-compile 或静态文件扫描替代真实 Linux 运行；
- 不调用真实模型或扫描任意外部企业目标。

## 实施任务

- [x] 固定 Linux CI runner、系统依赖、Rust/Python/Node 版本与缓存边界；
- [x] 构建 Linux Sidecar、Tauri Desktop、`.deb` 与 AppImage；
- [x] 验证 XDG、loopback、精确进程树、active Workspace 路径契约与真实 Linux GUI 原生文件选择；
- [x] 验证 Secret Service 存取/清除与不可用错误；
- [x] 验证双向 Workspace ZIP Restore；
- [x] 生成 artifact smoke JSON 与 checksums。

## 验收标准

- [x] 真实 Linux x86_64 runner 产出可启动 `.deb`/AppImage 与匹配 Sidecar；
- [x] 首次启动和 legacy Workspace migration 后 health ready，业务文件/History 保留；
- [x] 关闭后 Desktop/Sidecar 无残留，端口释放；
- [x] config/data/state 与 Secret 只进入规定的 XDG/Secret Service 边界；
- [x] Windows/Linux Workspace ZIP 双向 Restore 可读且 schema/业务数据一致；
- [x] 真实 artifact smoke、测试、构建、校验和与限制说明均有机器可读证据。

## 当前环境审计

- 当前已在真实 Debian x86_64 VM 执行构建入口；Rust `1.88.0`、Python/Node 依赖和 XDG data/config/state 分离路径已进入真实构建链；
- Secret Service probe 已在隔离 `dbus-run-session`、临时 HOME/XDG runtime 和一次性 GNOME Keyring collection 中真实完成 store/read/delete/NoEntry，未复用用户 keyring、未输出 Secret；
- Windows→Debian→Windows Workspace Archive 已使用生产 `WorkspaceArchiveService.restore()` / `backup()` 做双向证据；manifest、业务成员、SQLite `user_version`、integrity、History marker 与 WAL/SHM 排除均进入机器可读记录；
- 真实 VM 已依次暴露并修复：Sidecar 必须先生成才能编译 probe、PyInstaller config 隔离被脚本覆盖、GNOME Keyring collection 锁定、workspace npm cwd 导致 Tauri config 相对路径失效、临时 HOME 导致 rustup/toolchain/cache 不可见，以及 Sidecar `starting` 状态被过早判断；
- `linuxdeploy` 构建阻塞已完成诊断和修复；最终 Debian VM artifact evidence 为 `22 passed / 0 failed / 0 not_verified`。
- 实际验收暴露并修复了五个 Tauri 原生文件对话框 command 在主线程调用 `blocking_*` 的 GTK 死锁；这些 command 现在按 `tauri-plugin-dialog` 约定使用 async command，文件大小、扩展名、绝对路径不出原生边界等规则未改变。
- 当前 evidence runner 对 AppImage / `.deb` 分别核验 config/data/state 三根分离、非默认 active Workspace 相对指针、default manifest 负控制、Sidecar status、进程与端口清理；官方 `tauri-driver`/WebKitWebDriver 负责标准 WebView 点击，`xdotool` 仅在精确标题的 GTK chooser 获得焦点后输入隔离合成文件。两种 r27 工件的 GTK picker 均已返回 WebView且未隐式触发 Preview、Commit 或 Scan；非默认 pointer 增强是在 r27 后加入，尚待 Debian 真机重跑。

## 验证证据

- 已验证：真实 Debian VM 中隔离 Secret Service probe passed；
- 已验证：Windows→Debian→Windows Archive 生产格式往返及 SQLite/业务 marker 保留；
- 已验证：Rust `1.88.0` 与 Linux XDG data/config/state 路径进入当前 CI/build/evidence 契约；
- 自动化入口：`.github/workflows/linux-release.yml`、`apps/desktop/scripts/build-linux-release.sh`、`apps/desktop/scripts/linux_artifact_evidence.py`、`apps/api/scripts/verify_workspace_archive_roundtrip.py`；
- 最终机器证据：产品版本 `0.1.2`，平台 Debian 12 / Linux `6.1` x86_64，`22 passed / 0 failed / 0 not_verified`；证据下载到 ignored `artifacts/desktop/generated/linux-0.1.2-r27/`；
- AppImage：`168008184` bytes，SHA-256 `d34966c316446254b9b024483e22511a6974636112a0d4d1d2b45331e777b89f`；
- `.deb`：`73919638` bytes，SHA-256 `8d450813214777f6d477ef96f3d581c7f564c3ad97dc7c7406860259d83d5208`；
- Sidecar：`65403912` bytes，SHA-256 `d52654a48c7ad9258375ecfe4e88d80f44810ddcc5c9b691196034d1e356e66d`；
- 原生选择独立证据：`evidence/native-picker.json`，SHA-256 `02ddf6c4e95ae0f2b52caaf7b8c34dca2c6cc1263994bd216999f3f8c3fa39a3`；总证据 `evidence/summary.json` SHA-256 `576d18eb81dcafba738093f7bcfbf94b2f931db588813aa9bf2d916a55a1c1f3`。
- r27 的 22 项中，旧 active pointer 检查使用默认 Workspace 目标；它不能证明 pointer 被消费。增强脚本改用 `workspaces/pointer-target` 并拒绝 default/越界目标；当时未具备可用的本机 Debian/WSL/Docker 验证环境，新增断言未包含在旧 summary 中。2026-09-18 已取得下述新机器证据。
- 边界：选择器只读取 runner 创建的 `synthetic-picker.md`，未导入、未扫描，也未调用真实 Provider；未读源码用户五分钟任务、真实企业 Gateway 与真实模型波动仍是独立外部验收，不由本证据覆盖。

## 2026-09-18 当前源码 WSL 原生构建复核

- 环境：WSL2 Ubuntu 中的 Debian 12 x86_64 Docker 容器；Rust 1.88.0、Node 20.19.0、Python 3.11.2，Python 依赖版本按当前 Windows Runtime 锁定。源码复制到 Linux 文件系统，保留 Windows 原项目。
- 新 `.deb`/AppImage/Sidecar 真正构建；`linux-evidence/summary.json` 为 22 passed / 0 failed / 0 not_verified，非默认 pointer 与 default manifest 负控制本次真实执行。
- 原生 GTK 选择器 2/2 通过，使用隔离的已保存非秘密 Ollama 配置夹具以进入自有助手路径；`inferenceVerified=false`、`readinessVerified=false`，不冒充真实模型连接。标准字号采用 WebDriver 兼容性前提，不声称该字号按钮本身已原生点击。
- 测试环境用 C.UTF-8 提供中文窗口标题，用 tini 子进程收割保证容器内关闭进程组可核验；未改变产品清理算法。Secret Service 在隔离 DBus/GNOME Keyring 中真实存取、删除。
- 修正两项过时测试：当前 schema 的只读数据库可读取、写入应报错；工件 symlink 的错误文本应为 symlink。Linux 全量 Python 895 passed / 3 skipped；Windows 对应定向 24 passed / 3 skipped，Linux evidence 单测 25 passed。
- 交付路径：`artifacts/deliverables/AgentAudit-0.1.2-installers-20260918/`；新工件哈希以该目录 manifest 为准。`.deb` 为解包运行验证，不是独立机器 apt 安装/卸载验收；WSL 图形会话不替代独立 Linux 桌面完整体验。`TARGET_ENVIRONMENT_ACCEPTANCE` 三个独立任务未自动升级。
