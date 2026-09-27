# F-031 企业 AI Runtime 连接与协议识别

- 状态：External Validation Pending（共享实现、Windows 验收与后续 F-055 Linux Secret Service/artifact 证据完成；真实企业 Gateway/凭据验收待补）
- 所属里程碑：M6 本地双平台产品化
- 负责人：主代理
- 相关决定：`docs/M6_LOCAL_DUAL_PLATFORM_PRODUCT_PLAN.md`、`docs/features/F-027-first-run-local-model-connection.md`

## 用户价值

小企业可以直接使用本机 Ollama；已有私有化 AI 平台的企业则应当连接管理员明确提供的内网模型服务，而不被要求改成 Ollama。普通用户只需要“自动查找本机”或“连接企业地址”，软件负责识别可验证的 API 协议和模型能力，不要求用户理解 vLLM、TGI、NVIDIA NIM 或 Gateway 的内部实现。

## 事实依据与产品结论

多种企业推理运行时已经公开提供 OpenAI-compatible 接口：

- vLLM 提供 `/v1/models`、`/v1/chat/completions` 等接口，Tool Calling 能力取决于模型和运行参数：<https://docs.vllm.ai/en/stable/serving/openai_compatible_server/>；
- Hugging Face TGI 通过 `/v1/chat/completions` 提供 Messages API，并明确记录部分 Tool Calling 行为差异：<https://huggingface.co/docs/text-generation-inference/reference/api_reference>；
- NVIDIA NIM LLM 提供 `/v1/models`、`/v1/chat/completions` 和独立 readiness endpoint：<https://docs.nvidia.com/nim/large-language-models/latest/api-reference.html>；
- LiteLLM Proxy 是集中式 LLM Gateway，同样以 OpenAI-compatible 接口连接下游模型：<https://docs.litellm.ai/>。

因此软件只承诺识别并验收 **Ollama 协议** 或 **OpenAI-compatible Chat Completions 协议**。除非服务返回有规范依据的元数据，否则不根据端口、响应文字或 Header 猜测它一定是 vLLM、TGI、NIM 或某个 Gateway。

## 范围

- 保留当前“自动发现本机 Ollama”，但将它明确为本机快捷入口，不再作为产品唯一 Provider；
- 新增“连接企业 AI Runtime”：用户填写一个明确地址，软件只访问该地址，不扫描局域网；
- 对明确地址执行协议识别：优先读取显式 `/v1/models`；Ollama 只使用其固定 `/api/tags`，不靠错误文本猜类型；
- 统一支持 `ollama` 与 `openai_compatible` 两种 Runtime kind，后者覆盖内网 Gateway、vLLM、TGI、NIM 和其他经真实兼容性检查通过的服务；
- 模型列表可读取时使用下拉选择；不可读取但协议允许时允许手动填写模型 ID，并明确标记“未从服务枚举”；
- 保存前复用 Provider Readiness，实际检查连接、普通回答、Structured Output 与 Tool Calling；
- 支持 `none` 与 `bearer` 两种认证；Bearer Secret 只进入系统 Credential Store，不进入 Provider JSON、Workspace、SQLite、日志、Trace、导出或错误文本；
- Windows 使用系统凭据边界；Linux 使用 Secret Service/libsecret 边界。若目标系统不可用，Bearer 连接必须明确不可保存，不得降级为明文文件；
- 已确认的非 Secret 配置在 Windows/Linux 共用；目标 Provider 与 Attack Provider 第一版继续共用一套设置，避免普通用户理解双 Provider 编排。

## 非目标

- 不扫描企业局域网、Kubernetes、DNS、服务注册中心或硬盘模型目录；
- 不部署、下载、启动、停止或升级 vLLM、TGI、NIM、LiteLLM、Ollama 或模型；
- 不用默认端口列表猜测企业服务，不根据品牌特征做不可靠识别；
- 不支持 Azure OpenAI、AWS Bedrock、Vertex AI 或 Anthropic 专有协议；它们需要独立认证与请求契约，后续有真实企业需求再立功能；
- 不实现负载均衡、路由、fallback、自动重试、模型切换、成本治理或 Gateway 管理；
- 不把 Readiness 结果当 Finding，不修改 Contract Checker、安全结论或 Ground Truth；
- 不把“兼容 `/v1/chat/completions`”等同于“能够通过 Tool Calling/Structured Output 验收”。

## 前后端与数据影响

- Web：把设置入口简化为“自动查找本机”和“连接企业地址”；高级字段只在需要时展开；展示检测到的协议、模型来源、认证状态和四项 Readiness；
- API：新增显式 endpoint inspection、OpenAI-compatible model listing、候选 readiness 和确认接口；只访问请求中的单一 origin；
- Contracts：扩展 Provider kind、认证状态、协议识别、模型候选和连接诊断 DTO；禁止在响应 DTO 中出现 Secret；
- Desktop：新增最小 Credential Store 命令，由桌面壳持有 Secret；Sidecar 只获得运行所需值，不持久化；
- Data/Model/Tool：新增通用 OpenAI-compatible Adapter，继续复用统一 `LLMProvider` 与严格响应规范化；不新增 Finding 类别。

## API 与交互契约

### 简化流程

```text
自动查找本机
→ 固定检查 127.0.0.1:11434
→ 选择模型
→ 检查兼容性
→ 确认使用

连接企业地址
→ 填写 base URL
→ 选择“无需认证 / API Key”
→ 识别协议并读取模型
→ 选择或填写模型 ID
→ 检查兼容性
→ 确认使用
```

### 配置与识别

- `ProviderConnectionSettings.kind`: `ollama | openai_compatible`；
- `baseUrl`: 规范化 service root 或 `/v1` base，不含 credentials/query/fragment；
- `model`: 明确模型 ID；
- `authMode`: `none | bearer`；
- `credentialConfigured`: 只表示系统凭据是否存在，不返回 Secret；
- `ProtocolInspectionResult`: `status`、`protocol`、规范化地址、模型候选、诊断和 `modelsEnumerated`；
- 检查与保存请求中的额外字段一律 422；外部响应在 API 信任边界严格校验。

### 自动识别边界

- “自动”不是扫网：自动查找只访问固定本机 Ollama；
- 企业地址由用户或管理员提供，软件自动完成的是 **协议与能力检查**；
- `/v1/models` 成功只能证明模型枚举接口可用；最终可用性仍由真实 Readiness 决定；
- Redirect 不自动跨 origin；HTTPS 证书错误直接报告，不关闭验证；
- 失败后不回退到 Ollama、DeepSeek 或其他 Provider。

## 实施任务

- [x] ~~基于官方接口固定产品边界、协议层与不猜厂商原则；~~
- [x] ~~扩展共享 DTO 与 Provider Settings，保留 F-027 数据迁移兼容；~~
- [x] ~~实现通用 OpenAI-compatible Adapter 与单地址协议/模型检查；~~
- [x] ~~实现 Windows/Linux 系统 Credential Store 最小边界和 Sidecar Secret 注入；~~
- [x] ~~重构设置 UI 为“自动查找本机 / 连接企业地址”，保留显式 Preview、Readiness、Save、Cancel；~~
- [x] ~~覆盖无认证与 Bearer、错误映射、Secret 不落盘、不扫网和既有主链回归；~~
- [x] ~~完成真实本机 Ollama 与可控 OpenAI-compatible Test Server 验收；~~
- [x] ~~更新架构、状态、验收证据并按功能提交 Git。~~

## 验收标准

- [x] 旧 Ollama 配置无损读取，自动发现仍只访问固定 loopback；
- [x] 用户填写一个内网地址后，系统只访问该 origin 并结构化显示协议、模型与诊断；
- [x] vLLM/TGI/NIM/LiteLLM 类服务不要求用户选择厂商，统一以 OpenAI-compatible 进入实际 Readiness；
- [x] 模型枚举、普通回答、Structured Output、Tool Calling 任一不满足时如实显示，不自动修补、重试或 fallback；
- [x] Bearer Secret 不出现在 Provider JSON、Workspace、SQLite、History、Trace、日志、导出、错误和 API 响应；
- [x] 系统 Credential Store 不可用时拒绝保存 Bearer 配置，不降级明文；
- [x] 首载与刷新不自动访问企业地址、不调用模型；所有外部动作由用户显式触发；
- [x] Guided Audit、Finding、Replay、Benchmark、Acceptance Run 使用确认后的统一 Provider；
- [x] Windows/Linux 共用 DTO 和业务路径，无开发机绝对路径；
- [x] 单元、集成、E2E、typecheck/build、Rust check、artifact smoke 与 diff check 通过。

## 验证证据

- Python：`PYTHONPATH=apps/api/src;. .venv/Scripts/python.exe -m pytest -q` → `567 passed, 2 skipped, 1 warning`；两个 skip 是未提供条件工件时的 Windows/Linux artifact smoke。
- 关键产品链：`npx playwright test --reporter=line` → `13 passed`；覆盖企业地址显式检查、Bearer 系统存储失败不 PUT、旧 Guided/Replay/Acceptance 回归和 390×844。
- Rust/Build：项目内 Rust 1.98 完成 `cargo check`；`rustfmt --check`、根 `typecheck`、Web production build 与 Windows Tauri release/NSIS 重建纳入最终收尾。
- Windows artifact：指定 `R:\cargo-target-release-f026\release\agent-audit-desktop.exe` 运行 Desktop 配置/smoke 为 `10 passed`，退出后无 Desktop/Sidecar 残留进程。
- 真实本地模型：本机 `qwen3:8b` 候选 Readiness 返回 `READY`，Target connectivity/Tool Calling 与 Attack connectivity/strict JSON 四项全部 passed，4/4 Plan compatible；未保存配置、未调用 DeepSeek。
- 受控 OpenAI-compatible 证据来自进程内 Transport/Test Provider，不是真实企业 Runtime 验证。
- 后续 Linux 证据：F-055 已在真实 Debian x86_64 VM 的隔离 `dbus-run-session`/一次性 GNOME Keyring 中完成 Secret Service store/read/delete/NoEntry，并完成 Sidecar、AppImage、`.deb` 和 GTK 原生选择的工件验收；不再将 Linux Credential Store/artifact 写为未执行。
- 未完成：OpenAI-compatible/Anthropic/AgentAudit Adapter 的自动化证据来自受控 Test-only Transport，当前没有被授权的真实企业 Gateway 和凭据；因此 F-031 保持 External Validation Pending，不把协议模拟冒充企业接入。

## 实施记录

- 2026-08-28：用户明确指出企业部署不能只考虑 Ollama，软件必须同时提供足够自动的识别和简单手动连接。F-031 保持单一产品边界，只扩 Runtime 接入，不扩张为企业 AI 综合管理平台。
- 2026-08-28：完成 OpenAI-compatible `/v1/models` 检查、通用 Chat Completions Adapter、四项 Readiness、非 Secret 配置切换、Windows Credential Manager/Linux Secret Service 代码边界与简化 UI；SDK 重试显式关闭。当前 Windows 代码、工件和本地模型证据通过，Linux 真实 Credential Store/artifact 证据待目标环境补齐。
- 2026-08-31：F-055 已补齐真实 Debian Secret Service 与 Linux 桌面工件证据。F-031 的剩余边界改为真实企业 Gateway/凭据验收，不改写 2026-08-28 当时确实无 Linux 环境的历史。
