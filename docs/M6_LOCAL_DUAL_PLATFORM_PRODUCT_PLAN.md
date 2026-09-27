# M6 本地双平台产品计划

> 项目：知盾 AgentAudit——企业知识助手业务权限安全验收与自动化红队系统  
> 状态：Active  
> 适用范围：F-027 至 F-029；F-026 保留为已经实现的 Windows 桌面与可移植 Workspace 基础  
> 用户最新决定：产品保持单一、聚焦，不扩张为企业 AI 综合安全平台；同一代码库交付 Windows 与 Linux 安装包

## 1. 产品结论

知盾 AgentAudit 的正式产品形态是：

> **本地部署的企业知识助手业务权限安全验收工具。**

它只解决一条完整主线：

```text
导入经授权的企业知识与身份规则
→ 连接本地或内网 AI Runtime
→ 根据 Security Contract 生成受控攻击
→ 记录 Retrieval / Authorization / Tool / Sink Trace
→ 确定性产生 Finding
→ 给出修复配置
→ 对同一攻击执行 Replay
→ 保存 Acceptance Run 与报告
```

本项目不扩张为 LLM、RAG、MCP、依赖、基础设施、云资产和合规检查的扫描器总和。创新和技术深度继续来自 Security Contract、Outside-in / Inside-out、全过程 Trace 与同攻击 Replay，而不是功能目录数量。

## 2. 三个必须分离的边界

### 2.1 Application Core

安装包包含桌面窗口、本机 Sidecar、Security Contract、Attack Planner、Trace、Contract Checker、Finding、Replay、Benchmark 和 Acceptance Run。

应用升级只替换程序，不覆盖模型、企业 Workspace、SQLite 历史或用户导出。

### 2.2 AI Runtime

AI Runtime 独立安装和运行：

- 本机 Ollama；
- 企业内网中由管理员明确填写的 Ollama/OpenAI-compatible 服务（Gateway、vLLM、TGI、NVIDIA NIM 等统一按实际协议能力验收，不猜厂商品牌）；
- 后续经明确授权增加的其他 Provider。

第一版不把数 GB 的 LLM 打进安装包，不静默下载模型、不扫描模型文件目录、不自动切换 Provider，也不在连接失败后 fallback。准确承诺是“**不依赖公网；存在已确认的本地或内网模型时可完整运行**”，而不是“没有任何模型也能运行所有攻击测试”。

### 2.3 Audit Workspace

Workspace 只保存企业验收资料：

```text
workspace/
├─ documents/       经用户确认导入的资料快照
├─ contract/        角色、资源元数据与 Security Contract
├─ cases/           测试 Case 与 Ground Truth
├─ history/         SQLite Scan / Replay / Acceptance 历史
└─ exports/         用户主动导出的证据与报告
```

Manifest 和业务 DTO 只保存相对路径。Workspace 整体移动后仍可打开；应用卸载和升级默认不删除 Workspace。

## 3. 单一产品，不做综合平台

### 3.1 必须做

- 企业知识助手/Agent 的业务权限验收；
- 资源 owner、敏感等级、工具动作、审批、数量阈值和外部 Sink 规则；
- Outside-in 与 Inside-out 两类攻击视角；
- 真实 Retrieval、Authorization、Tool Call、Tool Result、Sink Trace；
- Finding、修复建议、同 Plan Replay 与 Acceptance Run；
- 本地数据、可移动 Workspace、安装包和可诊断错误；
- Windows 与 Linux 的同一产品体验。

### 3.2 明确不做

- 企业 AI 全资产管理、拓扑平台或 CMDB；
- 通用 Prompt、MCP、Vector DB、依赖、主机和云基础设施扫描器集合；
- 任意外部 Endpoint 或整个局域网扫描；
- PostgreSQL、Redis、对象存储、消息队列、微服务和 Kubernetes；
- OAuth、SSO、完整 RBAC、多租户、计费和 SaaS 控制台；
- 自研模型、模型训练或把大型模型打进安装包；
- 为展示效果增加 retry、输出修补、静默 fallback 或修改 Ground Truth。

## 4. 双平台不是两套软件

Windows 与 Linux 共用：

- `apps/web` Vue Renderer；
- `apps/api` Python/FastAPI 业务核心；
- `apps/desktop` Tauri 窗口和 Sidecar 生命周期；
- `packages/contracts` 跨端 DTO；
- Workspace 格式、SQLite Schema、安全判断和测试 Case。

平台差异只允许存在于：系统路径、Credential Store、原生文件对话框、Sidecar 文件名和安装包构建配置。禁止维护 Windows 业务逻辑和 Linux 业务逻辑两套分支。

### 4.1 Windows 交付

- Windows 10/11 x64；
- NSIS `setup.exe`；
- 当前用户安装，不要求管理员权限；
- 独立桌面窗口，不打开外部浏览器或命令行窗口；
- 数据位于 `%LOCALAPPDATA%\AgentAudit`；
- Secret 后续使用 Windows Credential Manager / DPAPI 系统边界。

### 4.2 Linux 交付

首个 Linux 目标只锁定 x86_64：

- `.deb`：Ubuntu/Debian 正式安装；
- `.AppImage`：便携运行；
- 暂不做 RPM、Snap、Flatpak 和 ARM64，除非出现真实目标环境。

Linux 桌面版使用 XDG 单用户路径，不把服务器目录误用于桌面：

```text
配置：$XDG_CONFIG_HOME/agent-audit
数据：$XDG_DATA_HOME/agent-audit
缓存：$XDG_CACHE_HOME/agent-audit
日志：$XDG_STATE_HOME/agent-audit
默认 Workspace：$XDG_DATA_HOME/agent-audit/workspaces/default
```

环境变量缺失时分别使用 `~/.config`、`~/.local/share`、`~/.cache` 和 `~/.local/state`。Secret 后续使用 Secret Service/libsecret 系统边界。`/opt`、`/etc` 和 `/var/lib` 只属于未来独立规划的内网服务器版本，不用于当前桌面版。

## 5. 普通用户主流程

首次启动只呈现五个动作：

```text
欢迎
→ 选择或连接本地/内网 AI
→ 导入企业资料
→ 确认角色与 Security Contract
→ 运行首次 Guided Audit
→ 查看 Finding 与 Replay
```

普通用户不需要理解浏览器、端口、Python、Node、环境变量、模型缓存路径或 JSON。完整 Trace、Advanced Contract、Benchmark、CLI/CI 和 Acceptance 历史继续保留在高级证据区。

## 6. 自动与手动连接边界

### 6.1 自动发现与协议识别

自动发现只允许：

1. 检查固定本机 Ollama 地址 `127.0.0.1:11434`；
2. 调用 Ollama `/api/tags` 读取真实模型列表；
3. 显示模型名称和可用状态；
4. 对用户选择的模型显式运行现有 Provider Readiness；
5. 由用户确认并保存。

不扫描硬盘模型目录，不扫描局域网，不静默下载，不自动选择后立即运行，也不在后续启动时擅自换模型。

企业服务的“自动”只表示：对用户明确填写的单一地址读取 `/v1/models` 并执行真实能力检查。不得用默认端口扫描、Header、错误文字或模型名称猜测厂商品牌；服务没有可靠元数据时只显示 `OpenAI-compatible`。

### 6.2 手动连接

普通表单只保留：

- 连接类型；
- 地址；
- 模型；
- API Key（仅 Provider 需要时出现）；
- “测试连接与兼容性”；
- “确认使用”。

F-027 已完成不需要 Secret 的本机/内网 Ollama。F-031 在出现真实企业连接需求后实现系统 Credential Store，并扩展到受控的 OpenAI-compatible Runtime；不能把 Key 写进 JSON、SQLite、Workspace、日志、Trace、错误或导出。

## 7. 数据、日志和报告边界

- SQLite 继续作为单机历史数据库，不为假设中的 PostgreSQL 迁移提前引入 ORM；
- 日志只保存运行诊断、Scan/Case ID 和非敏感错误，不记录 API Key、Authorization Header 或原始敏感文档；
- 当前真实导出为 JSON/Markdown，PDF/HTML 只有出现明确交付需求后再做；
- 备份单位是完整 Workspace，恢复后必须保留 Contract、History、Finding 和 Replay；
- 不建立复杂任务队列、断点续扫和自动重试。当前显式同步验收失败时保存可读错误，不伪造半成品成功记录。

## 8. 功能顺序

### F-026 Windows 桌面与可移植 Workspace 基础

代码、当前机 release、Sidecar 和 NSIS 已完成。另一台无仓库、无 Python/Node 的 Windows 安装证据仍待补，保留为外部验收债务，不伪装完成。用户已在 2026-08-28 明确要求继续双平台产品开发，因此该外部证据不再阻塞共享代码演进。

### F-027 首次启动与本地/内网模型连接

- 自动发现本机 Ollama 和真实模型列表；
- 简化手动 Ollama 地址与模型连接；
- 复用 Provider Readiness；
- 用户确认后保存非 Secret 配置并立即成为当前 Runtime；
- Windows/Linux 共用 Provider 配置与 UI，不自动下载或 fallback。

### F-028 企业 Workspace 与资料导入

- 原生文件/文件夹选择；
- 默认复制快照；文件夹选择同样生成可移动、可复现的 Workspace 快照，持续只读连接待真实需求后另立功能；
- 解析预览、失败项和元数据确认；
- 角色/资源模板与 Contract Preview；
- 不自动决定企业真实权限。

### F-029 双平台安装、迁移与本地运维

- Windows 干净机 NSIS 安装/升级/卸载；
- Linux 干净环境 `.deb` 与 AppImage 安装/启动/退出；
- XDG 路径、Linux Sidecar、系统文件对话框和进程清理；
- Workspace 备份、恢复和跨路径迁移；
- Credential Store 只在需要持久化真实 Secret Provider 时另立功能接入；当前无 Secret 的 Ollama 配置不提前建设空壳；
- 软件升级不覆盖 Workspace，卸载默认保留企业数据。

### F-030 原创品牌标识与桌面启动体验

- 使用用户指定的唯一 RGBA 标识生成平台图标；
- 真实 Sidecar 状态 Splash；
- Windows release 已验证 Splash → Ready → 主窗口且关闭不误杀 Sidecar。

### F-031 企业 AI Runtime 连接与协议识别

- 保留固定 loopback Ollama 自动发现；
- 用户明确填写企业 Runtime 地址，自动识别 Ollama/OpenAI-compatible 协议和模型能力；
- 统一连接 Gateway、vLLM、TGI、NVIDIA NIM 等 OpenAI-compatible 服务，不要求普通用户判断厂商；
- Bearer Secret 进入系统 Credential Store，不进入业务数据；
- 不扫描局域网、不做 Provider fallback、不扩张为模型管理平台。

当前状态：共享 DTO、OpenAI-compatible Adapter、单 origin 检查、四项 Readiness、简化 UI、Windows Credential Manager/Linux Secret Service 代码边界和 Windows 工件已实现；本机 Ollama 真实验收与受控 OpenAI-compatible 验收通过。后续 F-055 已在真实 Debian x86_64 环境补齐 Secret Service 和 Linux Desktop artifact 证据；F-031 仍不勾选，是因为尚无被授权的真实企业 Gateway/凭据验收，不是 Linux 证据缺失。

### F-032 评委导向的视觉层级与人话文案

- 主工作区从连续深色卡片改为浅色工作台，深色只承担品牌与局部证据锚点；
- 用 Action Blue、Risk Coral、Evidence Teal、Warning Amber 区分主操作、风险、通过与提醒；
- 默认路径先显示准备状态、唯一主操作、攻击链、Finding 与 Replay，技术说明进入详情层；
- 精简重复的中英 kicker 和 AI 式解释句，不删除 Trace、Contract、Rule ID 或错误诊断；
- 原创视觉资产只锁定构图 brief，当前不生成图片、不修改既有 Logo；
- 不修改 API、Contracts、Provider、Workspace 或确定性安全结论。

当前状态：已完成。现有 Web Renderer 和 Desktop 共用同一套浅色工作台与语义色；567 tests、13 个 Playwright E2E、typecheck/build 和 1440px/390px 人工截图复核通过。三张原创图片只保留设计 brief，尚未生成。

### 后续候选，不进入当前主线

- 签名离线规则更新包；
- PDF/HTML 报告；
- Linux ARM64/RPM；
- 内网多人服务端、TLS、身份认证和访问日志。

## 9. 双平台完成标准

M6 只有在以下证据都真实存在时才能完成：

1. Windows 与 Linux 均有可安装/可运行的真实构建工件；
2. 目标机不需要仓库、Python、Node 或外部浏览器；
3. 拔掉公网后，已安装的本地 Ollama 或可达内网模型仍能完成 Guided Audit；
4. 自动发现只访问固定 loopback Ollama，手动连接只访问用户填写地址；
5. 两个平台使用同一 Workspace 格式，移动/备份/恢复后历史和 Contract 不丢失；
6. 安装升级不覆盖 Workspace，关闭窗口不遗留 Sidecar；
7. 导出、日志、SQLite 和错误信息不包含 Secret 或开发机绝对路径；
8. 相同 Contract、Case 和确定性 Test Provider 在两平台产生相同 Finding/Replay 结论；
9. Python tests、TypeScript typecheck/build、关键 E2E、Rust check、安装包 smoke 和 diff check 通过；
10. 真实模型能力不足时如实显示 Readiness/Gate 结果，不用重试或特判制造通过。

## 10. 防漂移恢复口令

上下文压缩或新会话恢复后，按以下主线判断所有新增需求：

```text
单一产品：企业知识助手业务权限安全验收
三分离：Application / AI Runtime / Audit Workspace
双平台：一套代码，Windows NSIS + Linux deb/AppImage
核心证据：Contract → Trace → Finding → same-plan Replay
先 F-027，再 F-028，再 F-029
不扩张为综合扫描平台，不引入云原生 SaaS 基础设施
```

不能直接对应这条主线的功能写入 Parking Lot，不顺手实现。
