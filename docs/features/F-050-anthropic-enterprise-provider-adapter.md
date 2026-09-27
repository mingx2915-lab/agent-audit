# F-050 Anthropic 与企业 Provider 适配协议

- 状态：Completed
- 所属里程碑：M6
- 负责人：主代理
- 相关决定：延续 F-031 的本地优先、单连接、Secret 不落明文与显式 Readiness 边界

## 用户价值

让使用 Claude Gateway 或企业自有模型网关的小企业，在不改造知盾业务链、不暴露凭据、也不依赖公网的前提下，选择一个明确协议接入现有验收流程；用户无需把所有企业接口伪装成 Ollama 或 OpenAI。

## 范围

- 在既有 `ollama`、`openai_compatible` 之外增加 `anthropic_compatible`，适配 Anthropic Messages API 与采用同一协议的 Claude Gateway；
- 增加版本化的 `agent_audit_adapter` 企业桥接协议，供企业在内网把特殊模型协议转换成知盾的固定 Canonical Provider DTO；
- 企业地址流程允许用户明确选择协议，也允许在用户显式点击检查后对该单一地址做受控兼容性检查；检查结果只推荐协议，不自动保存、不启动 Scan；
- Provider Readiness 继续使用四项真实探针，只有 READY 才能确认使用；运行时固定使用已保存协议，不重试、不降级、不跨协议 fallback；
- Bearer 与 `x-api-key` 凭据只通过瞬时请求和桌面 OS Credential Store 传递，不写入配置、History、Trace、日志或错误文本；
- 保留本机 Ollama 的一键发现和既有 OpenAI-compatible 连接。

## 非目标

- 不把 Claude Code CLI、MCP Server、Bedrock IAM 或 Vertex IAM 当作本功能的 Provider 协议；
- 不扫描局域网、端口或任意外部目标，只检查用户明确输入的一个 origin；
- 不允许用户粘贴任意代码、请求模板、JSONPath、Header 名称或转换脚本；企业特殊格式必须由企业侧受控桥接服务实现；
- 不在失败后自动切换 Provider、协议、模型或凭据；
- 不宣称受控测试替身等于真实企业网关验收。

## 前后端与数据影响

- Web：企业连接表单增加简洁协议选择、Anthropic/Claude Gateway 与企业适配器说明、对应凭据方式和检查结果；
- API：新增 Anthropic Provider Adapter；扩展单地址 Inspection、候选 Readiness、保存和 Runtime Provider factory；实现版本化企业适配器客户端；
- Contracts：扩展 Provider kind、protocol、auth mode、inspection/capability DTO；旧配置仍可读取；
- Desktop：沿用同一个 OS Credential Store 槽位，切换 endpoint、协议或 auth mode 时不得复用不匹配的 Secret；
- Data/Model/Tool：只保存非秘密 Provider settings；Security Contract、Trace、Finding 与 Replay 语义不变。

## API 或交互契约

- Provider kind：`ollama | openai_compatible | anthropic_compatible | agent_audit_adapter`；
- Auth mode：`none | bearer | x_api_key`。`x_api_key` 仅表示固定 `x-api-key` 认证，不开放自定义 Header；
- Anthropic 请求使用固定受支持的 `anthropic-version` 与 `/v1/messages`，把现有 Canonical messages/tools 显式转换为 Anthropic content blocks、`tool_use` 与 `tool_result`，再严格归一化为既有 `LLMResponse`；
- 企业适配器在固定版本路径暴露 capability manifest、models 与 completion；manifest 必须声明协议版本和 text/tool-calling/structured-output/usage 能力，Readiness 仍以真实探针为准；
- Inspection 只访问用户输入 origin 下的固定只读路径，拒绝 Redirect；无法无歧义识别时返回可读结果并要求用户手选，不猜测；模型无法枚举时允许手填 model ID，但仍须通过 Readiness；
- 保存请求可带一次性 credential，但响应和持久化设置永不回显 credential；设置变更前不替换当前 Runtime，Readiness/保存失败不改变已有连接。

## 实施任务

- [x] 冻结 Contracts、企业适配器 v1 manifest 与错误边界；
- [x] 实现 Anthropic Messages Provider 与企业适配器客户端；
- [x] 扩展 Inspection、Readiness、保存和 Runtime factory；
- [x] 收敛 Web/Desktop 连接交互和 Secret 生命周期；
- [x] 补齐 Provider、API、Desktop、E2E 和回归测试；
- [x] 完成真实构建、文档和验收收口。

## 验收标准

- [x] 受控 Anthropic-compatible 服务的文本、Tool Call、Tool Result、JSON 与 usage 四项 Readiness 可真实通过；非法 content block、401、5xx、超时和 malformed JSON 可读失败，单次调用且无 fallback；
- [x] 企业适配器只有版本与 capability manifest 合法时可进入候选 Readiness，完成同一套 Canonical Provider 行为；
- [x] 用户未点击检查/Readiness/保存时无外部请求；检查只访问输入的单一 origin，不跟随 Redirect、不扫描邻近地址；
- [x] 切换地址、协议、认证或 Secret 后旧检查结果失效；保存失败不替换当前 Runtime；
- [x] Secret 不出现在配置文件、API 响应、History、Trace、Finding、日志与错误中，Desktop 不提供明文 fallback；
- [x] 既有 Ollama/OpenAI-compatible 流程和旧 settings 兼容；390px、标准/大字模式无横向溢出；
- [x] Python、Contracts/Web/Desktop typecheck、Playwright、Rust check/test、Desktop artifact smoke 与差异检查通过。

## 验证证据

- Python：`.venv\Scripts\python.exe -m pytest -q`，`692 passed, 6 skipped, 1 warning`；F-050 Provider/API 定向 `69 passed`；
- Web：`npm run typecheck`、`npm run build` 通过；`npx playwright test --reporter=line` 为 `31 passed`，包含 F-050 三条显式连接、stale、取消和 390px 用例；
- Rust：`cargo check`、`cargo test --lib`（4 passed）与 `rustfmt --check` 通过；
- 构建：重新生成 PyInstaller Sidecar、Windows release EXE 与 NSIS 安装包；指定真实 release EXE 的 Desktop artifact smoke 为 `1 passed`，退出后未发现该桌面或 Sidecar 路径的残留进程；
- 差异：`compileall`、Contracts typecheck 与 `git diff --check` 通过；
- 边界：自动化使用明确的受控 Test-only Anthropic/Adapter transport，不宣称等同真实企业网关；真实企业 Claude Gateway、企业 Bridge、Linux Secret Service 与 Linux 安装产物仍需在目标环境外部验收。

## 实施记录

- 术语使用“Anthropic / Claude Gateway”，不把 Claude Code 产品本身误写为 API 格式；Claude Code 作为待测 Agent Runtime 的命令、文件与 MCP Trace 属于后续独立能力。
- 企业自定义格式通过企业侧 Bridge 转为固定 `agent_audit_adapter` v1，不在桌面软件中执行任意转换代码。
