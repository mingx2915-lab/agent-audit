# F-052 Windows 安装、升级、卸载自动验收

- 状态：Completed
- 所属里程碑：M6
- 负责人：主代理
- 相关决定：执行 `docs/NEXT_AUTOMATED_DELIVERY_PLAN.md` 的 P1；必须使用两个明确版本的安装包

## 用户价值

用隔离、可重复的自动化流程证明 Windows 安装包可以安装、首次启动、升级和卸载，并且升级与卸载不会覆盖或删除企业 Workspace、History 和 Acceptance 证据。

## 范围

- 新增独立 Windows 安装生命周期 Runner，不扩写桌面启停 Runner；
- 使用 Runner 创建的隔离安装根目录与 `AGENT_AUDIT_HOME`；
- 使用不同版本的 baseline/upgrade NSIS 安装包；
- 验证首次启动、Workspace seed、SQLite integrity、升级保留和卸载边界；
- 生成同源 JSON/Markdown 证据并返回可用于 CI 的退出码。

## 非目标

- 不在开发机默认安装目录进行破坏性试验；
- 不按进程名批量结束进程，不删除用户目录，不修改系统级注册表项；
- 不把重复安装同一版本称为升级；
- 不调用真实模型、企业 Gateway 或外部目标；
- 不处理 Linux 安装包，Linux 留给 F-055。

## 安全边界

- 只允许绝对且由 Runner 创建的空安装根目录和空 `AGENT_AUDIT_HOME`；
- 只接受唯一匹配产品标识、版本和安装路径的 HKCU 卸载项；
- 只清理 Runner 启动的精确 PID 与已验证后代；
- 卸载前必须验证 UninstallString 的可执行文件位于已验证安装根目录；
- 任一身份、路径或注册表匹配不唯一时立即失败，不猜测、不扩大范围。

## 实施任务

- [x] 冻结 Runner CLI、证据 DTO、安装目录和注册表契约；
- [x] 构建两个明确版本的 NSIS 工件；
- [x] 实现 baseline install → launch → 数据写入 → exit；
- [x] 实现 upgrade install → 数据/SQLite/manifest 保留核对；
- [x] 实现 uninstall → 程序/注册表/进程清理且用户数据保留；
- [x] 增加失败边界、同版本拒绝与不可破坏路径测试；
- [x] 在当前 Windows 环境运行一次真实生命周期并复核证据。

## 验收标准

- [x] baseline 与 upgrade 的产品版本不同，版本关系可验证；
- [x] 首次启动创建合法 default Workspace 与可读 SQLite；
- [x] 升级前后 manifest ID、业务目录/Contract 内容、History/Acceptance 明确记录和 SQLite integrity 一致；
- [x] 升级不会重新覆盖已有 seed 或丢失 Runner 创建的证据；
- [x] 卸载后安装目录和唯一 HKCU 卸载项消失，相关进程/端口无残留；
- [x] 卸载后隔离 `AGENT_AUDIT_HOME`、Workspace 和 SQLite 仍存在且可读；
- [x] JSON/Markdown 同源，错误不泄露 Secret 或扩大清理范围；
- [x] 定向测试、相关回归、diff-check 与真实 Windows 生命周期通过。

## 验证证据

- 最新真实生命周期：`0.1.1` baseline NSIS → 隔离启动/资料 marker/受控 Scan、Finding、同 Plan Replay 与 24 Case Acceptance → `0.1.2` 原位升级 → 再启动 → 卸载；`13/13 checks passed`。
- 证据：`artifacts/desktop/generated/windows-install-lifecycle-0.1.1-to-0.1.2/windows-install-lifecycle.json` 与同目录 Markdown；两者不进入 Git。JSON SHA-256 为 `509349758885b9ecfa7adcb9c0faa6875e152cb7df109d4467e045a743f7f625`，Markdown SHA-256 为 `c7605d3e7b86f386371073ef8f190da4393a67b4c205bc2a6f3eb0b98ec78f85`。
- 数据保留：升级前、升级后与卸载后 SQLite 均为 `integrity_check=ok`，且同一个非空 Scan ID `c5bde448-a51d-492d-90f3-bb02701efac5` 和 Acceptance ID `acceptance_ee0855bd5b47` 仍可读。
- 本轮定向回归：F-051/F-052/F-055 合并切片 `70 passed, 1 skipped`。
- 本轮全量回归：`867 passed, 10 skipped, 1 warning`；根 `npm run typecheck`、`npm run build`、Playwright `36 passed`、Rust check/10 tests/rustfmt 与 `git diff --check` 通过。
- 真实运行后：安装目录、HKCU 卸载项、厂商产品键和相关进程均不存在；隔离 home/Workspace/SQLite 保留且快照一致。

## 实施记录

- 当前最新真实基线为 `0.1.1` NSIS，升级工件为 `0.1.2`；Runner 仍会拒绝同版本或同文件冒充升级。
- 本证据来自当前 Windows 验收机的 runner-owned 隔离目录；它证明安装生命周期实现，但不替代另一台无仓库、无 Python/Node 的干净 Windows 复核。
- 当前 Tauri NSIS 使用 `currentUser`。Runner 在执行前必须先用只读测试确认自定义安装目录和卸载项语义；不满足即停止，不在默认位置尝试。
- 真实验收暴露并修复三个 NSIS 边界：Registry `InstallLocation` 的成对引号、`_?=` 导致卸载器无法自删、安装目录与 Registry 清理的最终一致性窗口；三者均有严格测试，未引入递归清理或模糊匹配。
