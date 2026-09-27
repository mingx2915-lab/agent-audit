# 开发总指令

> 本文件把用户的最初愿望转化为持续可执行的开发边界。每个功能开始前都应与 `AGENTS.md`、`PROJECT.md` 和当前功能文档一起读取。

## 目标

在本科竞赛可控规模内，把已经完成的 v0.5 基础闭环继续开发为可运行、可解释、可复现的 **知盾 AgentAudit v1.0 竞赛强化版**：

```text
受控企业知识助手靶场
→ Security Contract 驱动测试
→ Outside-in / Inside-out 攻击执行
→ Retrieval / Authorization / Tool / Sink Trace
→ Hybrid Judge Finding
→ 修复配置
→ 同攻击 Replay
```

## 尺度控制

### 不能做大

- 不做通用 AI 安全平台或 AI 版 Burp Suite；
- 不做任意外部 Endpoint 扫描；
- 不做完整 IAM、企业 Connector、MCP 生态、Runtime Firewall、多租户 SaaS；
- 不引入微服务、Redis、消息队列、Kubernetes 或自研模型；
- 不为低概率情况增加重复校验、复杂重试、硬状态门和过度抽象；
- 不在当前功能之外顺手增加攻击类型、页面或基础设施。

### 不能做小

- 不能退化为 Prompt 分类器或“Prompt → Model → Judge → 分数”；
- 前端、API、Target Agent、RAG/Mock Tool、Trace 必须形成真实调用链；
- 不能只看最终回答，必须保留实际 Retrieval、Authorization、Tool 和 Sink 证据；
- 不能只展示发现漏洞，最终必须完成同攻击修复 Replay；
- 不能用静态页面、预制动画或手工改库冒充运行结果。

## 开发顺序

F-003 至 F-012 是已完成的 v0.5 历史。当前严格按 `docs/COMPETITION_V1_DEVELOPMENT.md` 与 `docs/FEATURES.md` 的 F-013 至 F-020 顺序推进。同一时间原则上只有一个功能 `In Progress`。主代理可以把当前功能拆给多个子代理并行，但不得同时启动下一个功能。

每个功能：

1. 创建或读取 `docs/features/F-xxx-*.md`；
2. 固定本功能范围、非目标、API/数据影响和验收标准；
3. 按互斥文件范围分工；
4. 实现最小真实垂直切片；
5. 执行静态检查、编译和不启动服务的测试；
6. 主代理审查 diff、集成契约并验证验收项；
7. 更新功能文档、`STATUS.md` 和 `FEATURES.md`；
8. 只有全部验收通过才勾选并划掉。

## 多代理规则

- 主代理负责需求解释、共享契约、架构决定、Git、集成和最终验收；
- Backend Luna 只写 `apps/api` 与 `data/demo`；
- Frontend Luna 只写 `apps/web`；
- Test Luna 只写 `tests`；
- 三个子代理都必须先读取项目主约束和当前功能文档；
- 子代理不得修改 `AGENTS.md`、`docs`、`packages/contracts` 或其他代理负责目录；
- 子代理不得启动服务、发真实模型请求、提交 Git 或扩大功能范围；
- 发现共享契约问题时只报告，由主代理统一修改。

## Provider 与启动限制

- 首个模型 Provider：DeepSeek OpenAI-compatible API；
- Base URL：`https://api.deepseek.com`；
- Model：`deepseek-v4-flash`；
- Thinking：显式 `disabled`；
- 密钥只能从后端环境变量 `DEEPSEEK_API_KEY` 读取；
- 密钥不得写入代码、文档、测试、日志或 Git；
- 当前聊天中出现过的密钥不写入工作区，正式启动前建议由用户换新并在本机设置；
- 测试允许显式注入 Test Double，但产品运行时不得在 Provider 失败后静默伪造模型结果。

在软件接近可运行闭环前：

- 不启动前端或后端服务；
- 不启动 Docker 服务；
- 不发送真实 DeepSeek API 请求；
- 允许安装依赖、静态检查、编译、单元测试和不监听端口的进程内集成测试。

首次启动任何服务或首次发送真实模型请求前，主代理必须先向用户说明将启动什么、使用什么环境变量、预期验证什么，并等待用户确认。

DeepSeek 参数依据：

- <https://api-docs.deepseek.com/>
- <https://api-docs.deepseek.com/guides/thinking_mode/>

## 当前执行指令

M0 至 M5 已完成，当前只执行 M6 `docs/M6_LOCAL_DUAL_PLATFORM_PRODUCT_PLAN.md`。产品保持为单一聚焦的企业知识助手业务权限安全验收工具，Application、AI Runtime 与 Audit Workspace 分离；一套代码交付 Windows 与 Linux，不扩张为综合 AI 安全扫描平台。

当前功能为 F-027，后续严格按 F-028、F-029 顺序。当前不制作 PPT、视频或演讲材料。正式 DeepSeek 请求仍需单独授权；本地 Ollama 的发现、Readiness 和真实调用必须由用户操作或主代理明确验收触发，关闭 thinking 且禁止静默 fallback。
