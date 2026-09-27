# 知盾 AgentAudit 下一阶段自动化交付计划

- 状态：Completed
- 适用里程碑：M6 本地双平台产品化
- 当前执行切片：无；P0–P5 已全部完成
- 原则：优先完成可重复、可核查、无需人工制作 PPT/视频的工程证据；同一时间仍只实现一个功能。

## 1. 目标

把现有可运行产品转化为可重复发布、可自动核验、可诚实说明边界的比赛交付物。所有证据必须来自当前代码、真实构建产物或明确标注的 Test-only 环境，禁止手工填写漂亮数字、把测试替身冒充企业系统，或用静态字符串代替真实运行结果。

## 2. 顺序与优先级

| 阶段 | 功能 | 自动化产物 | 启动条件 | 完成边界 |
|---|---|---|---|---|
| P0 | F-051 一键验收与发布证据包 | `summary.html/.md/.json`、环境、测试、截图、Finding/Replay/Acceptance、校验和 | 当前立即开始 | Windows 当前机与 Test-only/真实模型证据严格分栏 |
| P1 | F-052 Windows 安装、升级、卸载自动验收 | 安装前后状态、数据保留、进程/端口、卸载证据 | F-051 完成 | 只操作测试创建的精确安装与隔离数据目录 |
| P2 | F-053 本地脱敏诊断包 | 本地日志、关联 ID、脱敏诊断 ZIP、包含/排除清单 | F-052 暴露真实支持需求后 | 默认不联网、不上传、不含 Secret 与完整企业正文 |
| P3 | F-054 Workspace 与 SQLite 版本迁移 | schema version、顺序 migration、旧版 fixture、失败回滚证据 | 准备第二个可对外版本前 | 迁移前备份，失败不破坏旧数据 |
| P4 | F-055 Linux CI 构建与 artifact smoke | `.deb`/AppImage、Secret Service、Sidecar 生命周期、跨平台 Restore | 有真实 Linux runner 后 | 无真实 Linux 环境时保持未完成，不用静态配置冒充 |
| P5 | F-056 SBOM、许可证与依赖漏洞审计 | SBOM、许可证清单、漏洞结果与处置状态 | 构建矩阵稳定后 | 扫描结果是时间点事实，不宣称永久无漏洞 |

## 3. P0：F-051 一键验收与发布证据包

### 3.1 用户价值

评委或开发者运行一条显式命令，即可得到与当前版本一致的本地证据包，不需要人工整理截图和测试数字。

### 3.2 固定目录

```text
artifacts/release-evidence/<run-id>/
├─ summary.html
├─ summary.md
├─ summary.json
├─ environment.json
├─ manifest.json
├─ checksums.txt
├─ tests/
├─ screenshots/
├─ findings/
├─ replay/
└─ acceptance/
```

### 3.3 证据来源

- 当前 Git revision、脏工作区状态、产品版本、OS/CPU/RAM；
- 显式传入的测试结果与桌面 artifact 检查结果；
- 现有 Acceptance、Finding、Replay JSON/Markdown；
- Playwright 通过专用证据用例生成的固定视口截图；
- EXE、安装包、Sidecar 与证据文件 SHA-256；
- 真实模型、受控 Test-only Provider、当前机器和未验证环境必须分开标注。

### 3.4 信任边界

- 生成器不得启动任意外部扫描、修改用户 Provider、调用真实模型或读取用户真实 Workspace；
- 默认只读取调用者明确提供的工件和隔离运行目录；
- 不复制 Secret、Authorization/x-api-key、完整企业正文、来源绝对路径或用户主目录；
- 缺失证据必须显示 `not_run`、`not_provided` 或 `not_verified`，不得推断为 passed；
- JSON 是唯一结构化事实源，Markdown 与 HTML 从同一 JSON 投影；
- `checksums.txt` 只证明文件完整性，不作为项目进度或业务正确性的状态门。

### 3.5 实施切片

1. 冻结 Evidence Manifest 与 CLI；
2. 生成同源 JSON/Markdown/HTML 和 SHA-256；
3. 增加专用 Playwright 截图证据，不改变业务 API；
4. 接入显式测试/构建工件索引与 Secret/固定路径检查；
5. 在隔离目录运行并记录边界，完成 Windows 当前机证据包。

## 4. P1：Windows 安装生命周期

- 使用隔离 `AGENT_AUDIT_HOME` 和测试专用安装目标；
- 验证首次安装、启动、升级、保留 Workspace/History、卸载、端口释放和进程树清理；
- 只终止本次创建且身份已验证的精确 PID；
- 不清理用户现有 AgentAudit 数据，不修改系统级依赖；
- 输出机器可读 JSON，再由 F-051 收录。

## 5. P2：本地脱敏诊断包

- 本地滚动日志，大小和数量有界；
- Desktop、Sidecar、API、Provider 调用使用可关联但不含 Secret 的 operation ID；
- 一键导出诊断 ZIP 前显示包含/排除项；
- 自动移除 Credential、完整正文、绝对用户路径和环境 Secret；
- 诊断包不能上传网络，也不能代替业务 Trace/Finding。

## 6. P3：数据版本与迁移

- Workspace manifest 与 SQLite schema 使用独立版本；
- migration 必须顺序、幂等且有旧版 fixture；
- 迁移前生成可恢复备份；
- 失败时保留旧 Workspace，不写伪成功版本；
- 验证 History、Acceptance、Contract、文档索引和 active Workspace 指针。

## 7. P4：Linux 真实发布

- 真实 Linux x86_64 runner 构建 Sidecar、Tauri、`.deb` 与 AppImage；
- 验证 XDG config/data/state、Secret Service、loopback、进程树和系统文件选择；
- 验证 Windows ZIP 在 Linux Restore，以及 Linux ZIP 回到 Windows；
- CI 不能提供 Secret Service/桌面会话时，对应步骤必须诚实 skip 或标记 external validation pending。

## 8. P5：供应链证据

- 为 Python、npm、Cargo 依赖生成机器可读 SBOM；
- 生成许可证清单并标记未知、强 copyleft 或分发限制；
- 运行依赖漏洞扫描，保存数据库时间和工具版本；
- 高风险项必须记录影响判断与处理状态，不能仅为了全绿而忽略；
- 输出结果由 F-051 索引，但不阻塞开发者日常运行。

## 9. 总体验收原则

- 每个阶段单独创建 F-xxx 功能文档，前一阶段完成后才能启动下一阶段；
- 所有破坏性或生命周期测试只针对临时目录、测试安装和精确进程；
- 自动化证据不替代 F-035 陌生用户五分钟任务；
- 不因证据生成而新增攻击类别、外部目标扫描、重试或 Provider fallback；
- Linux GUI native picker 已在 F-055 的新 AppImage 与 `.deb` 上通过真实 GTK chooser 自动验收；非默认 active Workspace pointer 加 default 负控制仍须在 Debian 对真实工件重跑。干净 Windows、真实企业 Gateway、真实模型波动和 F-035 陌生用户任务仍保留为外部边界，不得由 Linux artifact 证据代替。
