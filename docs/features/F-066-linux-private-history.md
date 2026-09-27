# F-066 Linux 历史库与诊断日志私有权限

- 状态：Done
- 所属里程碑：M6
- 负责人：主代理
- 相关决定：用户 2026-09-18 提供新版 Linux 实装回归报告；F-065 独立 GUI 验收继续待补

## 用户价值

防止同机其他 Linux 用户读取包含 Scan、Contract、Replay 和 Acceptance 快照的历史库。

## 范围

- SQLite 主库创建为 0600；当前 Workspace 的 history 目录为 0700。
- 打开旧 Workspace 或历史库时收紧原有库及现存 SQLite 辅助文件权限，保留数据。
- 实测新生成的 WAL、SHM、journal 权限。
- 应用日志目录为 0700，日志及轮转文件为 0600；日志内容仍保持固定字段、无业务正文。
- 验证 Linux 源码及重新冻结 Sidecar；Linux Debian 修正包使用递增的包修订号。

## 非目标

- 不修改安全判定、检索、模型连接、前端或视频。
- 不扫描其他 Workspace，不修改共享父目录，不使用全局 umask。
- 不把日志元数据可读夸大为业务正文或密钥泄漏；不把缺 WebKitGTK 的容器当作 GUI 验收通过。

## 前后端与数据影响

- Web：无。
- API：仅本地文件创建及已选 Workspace 打开边界。
- Contracts：无。
- Data/Model/Tool：历史数据和 Schema 保持原样，权限变为仅文件所有者可读写。

## API 或交互契约

打开已选 Workspace 后自动收紧旧历史库权限；无法设置权限时返回现有可诊断存储错误，不吞掉异常。

## 实施任务

- [x] 先复现新旧库、WAL/SHM、日志与轮转权限失败。
- [x] 在创建/打开边界实施私有权限，并覆盖恢复旧 Workspace。
- [x] Linux/Windows 相关回归及另一个 Linux 用户的读取拒绝验证。
- [x] 新冻结 Linux Sidecar 和递增 Debian 修订号包交付。

## 验收标准

- [x] 宽松 umask 下，新库在 SQLite 首次访问前即为 0600。
- [x] 旧库及现存 WAL/SHM 收紧后数据仍可读；新生成辅助文件权限为 0600。
- [x] 新建、打开、恢复的 Workspace history 目录为 0700。
- [x] 日志及既有/新增轮转文件为 0600。
- [x] 其他非特权用户读取数据库、辅助文件与日志被拒绝。
- [x] 相关存储、迁移、日志回归和新冻结包检查通过。

## 验证证据

- Windows：`.venv/Scripts/python.exe -m pytest tests/unit tests/integration -q`，894 passed / 18 skipped。
- Linux 构建容器：`.venv/bin/python -m pytest tests/unit tests/integration -q`，907 passed / 5 skipped。包括本功能 11 项 POSIX 权限测试；Windows 对这些 POSIX 测试明确跳过。
- TDD：实施前 8 项真实 Linux 权限检查失败，实施后通过；后续补充共享父目录、Archive Restore 和权限失败不打开数据库三项检查。
- 另一个 Linux 用户实测：0644 正控制可读取；修正后的主库、WAL、SHM、日志和轮转文件均为 0600，nobody 读取均获 PermissionError，所有者两条合成记录保留。
- 新 Debian 包实际解出 Sidecar：Docker 无网络接口、全新模型缓存，6 项 BGE 检索评测通过；Health 返回实际端口；旧 0644 主库及存活 WAL/SHM 自动收紧为 0600，旧数据保留；history/日志目录为 0700；SIGTERM 后状态 stopped 且无残留进程组；端口冲突保留 failed。
- SIGTERM 校验记录：Uvicorn 完成 lifespan 关闭后重新触发 SIGTERM，实际 POSIX 返回码为 -15，属于该运行时的正常信号退出；本轮初始验证脚本错误要求 0，已依据运行时源码、stopped 状态和进程清理结果修正脚本，未修改应用生命周期。
- 发布：`artifacts/deliverables/AgentAudit-0.1.2-2-linux-f066-20260918/AgentAudit-0.1.2-2-linux-x64.deb`。Debian Version 为 0.1.2-2，dpkg 版本比较确认高于 0.1.2；包内 Sidecar 与新冻结二进制一致。应用上游版本保持 0.1.2，使用 Debian 安全修订号。
- 验证日志与可复跑脚本：`output/f066-private-storage-20260918/`；交付目录附证据、说明与 SHA-256。
- 人工步骤：用户报告新版 0.1.2 离线 BGE、Health 端口、绑定失败状态、Sidecar SIGTERM、中文/空格路径通过；报告来源为用户提供的外部回归，不冒充本轮自测。

## 实施记录

F-065 GUI 外部验收仍待补；本功能只修已确认的本地权限边界。包内 Sidecar 解包运行检查不等于独立桌面安装/窗口验收；本轮未重建 Windows 安装包或 Linux AppImage。旧包保留；旧 Workspace 在新版打开时自动修正权限，未扫描其他 Workspace。

### 2026-09-27 只读数据库回归补充

- schema-current 的既有 SQLite 库可通过 SQLite `mode=ro` 查询；SELECT 不触发 Schema 写迁移。缺库仍显式初始化，旧 Schema 的迁移仍要求可写连接。
- 对 owner-only 的 0400 数据库保留只读权限；不因读取尝试恢复写权限。保存到只读库时返回原有 `unable to save audit scan` / `unable to save acceptance run` 错误。
- 定向 Linux 权限与 storage recovery 测试：24 passed。全量本地 Linux Python：909 passed / 7 skipped；Windows：893 passed / 23 skipped（POSIX 权限测试按平台跳过）。
