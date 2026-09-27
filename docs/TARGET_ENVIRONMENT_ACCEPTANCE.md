# F-057 目标环境验收任务单

- 状态：3 项均待对应目标环境/授权，当前不计为 passed
- 范围：干净 Windows、Debian 非默认 active Workspace pointer、真实企业 Gateway/凭据
- 非目标：不执行 F-035 陌生用户五分钟任务

## 统一证据规则

每项必须记录：任务 ID、owner、开始/完成时间、Git revision、产品版本、OS/架构、工件 SHA-256、执行入口、机器可读结果、人工观察和未覆盖边界。

状态只允许：

- `not_verified`：未在声明目标环境执行；
- `incomplete`：已执行，但环境、工件或证据不完整；
- `failed`：必需检查失败；
- `passed`：声明范围的全部必需检查真实通过。

CI runner、Test-only Transport、开发机隔离目录不自动升级为下列目标环境的 `passed`。证据不得保存 Secret、Authorization Header、完整企业正文或用户绝对路径。

## TGT-WIN-CLEAN-01：干净 Windows 安装生命周期

- 当前状态：`not_verified`
- 协调状态：用户决定暂缓，由用户后续寻找独立安装执行人；当前代理不在开发机上冒充干净机证据
- Owner：Windows 目标机执行人；主代理审核证据
- 环境：Windows 10/11 x64；无仓库、无 Python/Node/Rust；当前用户未安装 AgentAudit
- 截止：2026-09-15

唯一自动验收入口：

```powershell
python apps/desktop/scripts/windows_install_lifecycle_runner.py `
  --baseline-installer <absolute-0.1.1-nsis.exe> `
  --baseline-version 0.1.1 `
  --upgrade-installer <absolute-0.1.2-nsis.exe> `
  --upgrade-version 0.1.2 `
  --sandbox-root <absolute-new-space-free-runner-directory>
```

Runner 仅能操作它自己创建的 sandbox、隔离 `AGENT_AUDIT_HOME` 与精确匹配的 HKCU 卸载项。证据必须包含 baseline→升级→卸载、Workspace/SQLite/Scan/Acceptance 保留、进程/端口清理和用户数据保留。

> 该 Runner 本身依赖 Python，因此应由验收 U 盘/管理端提供；验收重点是被测安装包和已安装产品不得依赖目标机的仓库、Python/Node/Rust。若目标机不允许验收脚本运行，则需在同一台机器上按相同检查项人工执行，状态不得因没有 Runner 而直接写 passed。

## TGT-DEB-POINTER-01：Debian 非默认 pointer 增强重跑

- 当前状态：`not_verified`（r27 的旧 default pointer 证据不等于本项）
- Owner：Linux release 执行人；主代理审核证据
- 环境：Debian 12 x86_64，真实 AppImage/`.deb`/Sidecar，Xvfb/WebKitWebDriver/GTK/Secret Service 依赖完整
- 截止：2026-09-15

首选入口：在 GitHub Actions 手动执行 `.github/workflows/linux-release.yml`。对已有工件的直接入口：

```bash
python apps/desktop/scripts/linux_artifact_evidence.py \
  --appimage <AgentAudit.AppImage> \
  --deb <agent-audit.deb> \
  --sidecar <agent-audit-sidecar> \
  --output-dir <new-empty-evidence-dir> \
  --version 0.1.2 \
  --secret-service-verified \
  --picker-evidence <native-picker.json>
```

必须在 AppImage 和 `.deb` 隔离 Runtime 中使用 `workspaces/pointer-target`，以 default manifest 作负控制；任一 pointer 未被消费、回退 default、越界、native picker 不匹配工件或存在 `not_verified` 均不得 passed。

## TGT-GATEWAY-01：真实企业 Gateway/凭据

- 当前状态：`not_verified`
- Owner：被授权的企业 Gateway 管理员；主代理只接收脱敏证据
- 环境：管理员明确提供的单一 HTTPS origin、模型 ID、限权测试凭据和允许时间窗
- 截止：待企业授权确认后 7 天内
- 协调状态：当前预计无法取得真实企业 Gateway；该项保持非阻塞外部验收，不以公共 API、普通代理或 Test-only Transport 替代

唯一产品入口：使用当前 release Desktop artifact 的“连接企业地址”，不使用 Test-only Transport。

```text
输入单一 origin 和认证模式
→ 显式执行协议/模型检查
→ 选择或手填管理员指定的 model ID
→ 执行 Target connectivity / Tool Calling / Attack connectivity / strict JSON
→ 确认非 Secret 配置和系统 Credential Store
→ 在合成 Workspace 运行一次 Guided Audit / Finding / Replay
→ 导出脱敏诊断与 Acceptance 证据
```

必需事实：只访问输入 origin；不跟随跨 origin Redirect；每个 Readiness 探针仅一次调用；无 retry/fallback；Secret 不出现在 Provider JSON、Workspace、SQLite、History、Trace、日志、诊断包、报告或截图。

## 当前协调结论

| 任务 | 可在当前 Windows 开发机完成 | 所需新权限/环境 | 当前状态 |
|---|---|---|---|
| TGT-WIN-CLEAN-01 | 否 | 另一台干净 Windows 或可用 Sandbox | `not_verified` |
| TGT-DEB-POINTER-01 | 否 | Debian x86_64/CI 权限与新构建工件 | `not_verified` |
| TGT-GATEWAY-01 | 否 | 企业授权的 origin/model/凭据/时间窗 | `not_verified` |

这三项未完成不阻塞 F-057 的自动化和文档收口，但阻塞 L4、“干净目标机已验证”和“真实企业 Runtime 已接入”三类主张。
