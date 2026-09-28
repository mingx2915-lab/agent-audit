# 知盾 AgentAudit

**企业知识助手业务权限安全验收与自动化红队系统**

知盾 AgentAudit 在仓库内的合成企业知识助手靶场中，验证 Agent 是否遵守 Security Contract，并用真实执行产生的 Retrieval、Authorization、Tool、Sink Trace 定位业务权限违规，最后对同一攻击完成修复 Replay。

> 团队署名与源码快照验证：[AUTHORS.md](AUTHORS.md) · [AUTHENTICITY.md](AUTHENTICITY.md)。

> SYNTHETIC / DEMO ONLY：仓库只包含合成角色、文档和客户数据，Enterprise Tool 为 Mock；系统不扫描任意外部目标，也不发送真实邮件。

```text
Security Contract
      ↓
Outside-in / Inside-out Plan → Target Agent → RAG / Mock Tool
                                      ↓
Actor → Source → Authorization → Tool → Sink → Finding
                                      ↓
                              Remediation Replay
```

## 已完成的 v1.0 竞赛软件

- Vue 3 + TypeScript Dashboard 与 FastAPI 模块化单体；
- Security Contract 驱动的资源/工具 owner-scope 授权；
- 固定 Outside-in 与 Inside-out Case；
- 本地 BGE Permission-aware Embedding Retriever、TF-IDF 对照、Mock Enterprise Tools 与可替换 LLM Provider Adapter；
- 全过程 Trace、确定性 Contract Checker 和辅助 Semantic Review；
- Contract-derived Attack Plan、真实执行 Finding、同攻击修复 Replay；
- 多身份差分、固定 Retrieval Evaluation、24 个四类 Ground Truth Case、扩展质量指标、Provider usage 和 Markdown 攻击链报告；
- SQLite Run History 与 Audit Setup、Live Audit、Findings & Replay 三工作区；刷新或重启后可恢复原 Scan 快照并追加历史 Replay；
- 可视化 Security Contract 编辑/影响 Preview、显式 Provider Readiness、固定 CLI/CI Gate；
- 统一 Acceptance Run：一次保存 Readiness、Retrieval、Differential、24 Case Gate、Guided Scan/Finding/Replay，支持历史对比和 JSON/Markdown 下载；
- Windows 桌面交付基础：Tauri 独立窗口、内置 FastAPI Sidecar、可移动 Workspace 与 current-user NSIS 安装包；当前机已验证，另一台干净 Windows 复核仍待完成；
- 真实 Playwright 浏览器验收：Guided 主链、Contract Editor、Acceptance Run、390×844 窄屏和 Provider 错误路径。

## Windows 桌面版

普通用户使用桌面安装包，不需要安装 Python、Node，也不需要打开浏览器或输入本机 URL。安装包请从 [AgentAudit 最新版本下载页](https://github.com/mingx2915-lab/agent-audit/releases/latest) 获取；Windows x64 安装器为该页中的 `AgentAudit-0.1.3-windows-x64-setup.exe`。

安装后启动“知盾 AgentAudit”。应用文件、AI Runtime 和企业 Audit Workspace 相互分离：

- 应用安装在当前 Windows 用户目录；
- 合成 Demo 首次复制到 `%LOCALAPPDATA%\AgentAudit\workspaces\default`，以后升级或重启不会覆盖 Contract 与 History；
- Workspace manifest 只保存相对目录，移动 Workspace 后仍可重新打开；
- 本机后台只监听 `127.0.0.1`，关闭桌面窗口会结束本次应用创建的 Sidecar，不会关闭外部 Ollama；
- 桌面包不捆绑或自动下载大语言模型权重。首次使用 BGE Embedding 时会下载约 90 MB 的 ONNX 模型到用户缓存，离线使用须先准备缓存。连接页可发现固定 loopback 上的本机 Ollama，并动态列出实际已安装模型；用户显式选择后仍须通过四项 Provider Readiness，系统不会按模型名称跳过验证。

本版本的 NSIS 安装器通过 Windows 2022 发布工作流构建；安装、两轮启动/关闭、受控崩溃恢复和卸载的结果以该版本对应的 Actions 记录为准。另一台干净 Windows 的人工安装与完整窗口视觉流程仍待复核。

## Linux 桌面版

本次版本提供 Debian/Ubuntu x86_64 安装包 `AgentAudit-0.1.3-linux-x64.deb`，从 [AgentAudit 最新版本下载页](https://github.com/mingx2915-lab/agent-audit/releases/latest) 获取。本次 Release 同时提供 `AgentAudit-0.1.3-linux-x64.AppImage`。桌面运行依赖兼容的 GTK/WebKitGTK 环境；密钥持久化使用 Secret Service。

本版本的 Linux 工件通过 Ubuntu 24.04 发布工作流构建；AppImage 和 `.deb` 的真实 GTK 文件选择、启动与凭据证据以该版本对应的 Actions 记录为准。`.deb` 自动化检查使用解包后的实际程序；另一台机器的 apt 安装与独立 Linux 桌面用户流程仍待复核。原生选择器使用隔离的非秘密连接配置夹具，未验证真实模型推理。

## 源码开发环境要求

- Python 3.11 或更高版本；
- Node.js 18 或更高版本与 npm（当前验收环境为 18.20.8）；
- 可选：Docker Compose，用于双容器演示；
- 模型路径二选一：默认 DeepSeek 需要 `DEEPSEEK_API_KEY`；本地演练可显式选择 Ollama。

## 本地安装

在仓库根目录执行：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".\apps\api[dev]"
npm ci
npx playwright install chromium
```

API 第一次执行 Embedding 检索时，FastEmbed 会下载约 90 MB 的 `BAAI/bge-small-zh-v1.5` ONNX 权重到用户缓存；模型文件不写入仓库。模型初始化或推理失败会返回明确错误，不自动切回 TF-IDF。

Linux/macOS 对应的 Python 命令为：

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -e './apps/api[dev]'
npm ci
```

## CLI / CI 安全门

显式选择本地 Ollama 后，可运行仓库内固定 24 个 Ground Truth Case。命令只接受输出目录，生成 `ci-gate.json` 与 `ci-gate.md`：

```powershell
$env:AGENT_AUDIT_LLM_PROVIDER = "ollama"
$env:OLLAMA_MODEL = "<已安装的模型名称>"
agent-audit ci-gate --output-dir artifacts/acceptance/generated/ci-gate
```

也可使用模块入口：

```powershell
.\.venv\Scripts\python.exe -m agent_audit_api.cli ci-gate --output-dir artifacts/acceptance/generated/ci-gate
```

退出码为 `0`（固定门全部通过）、`1`（门检查回退）或 `2`（参数、运行配置、Provider/Retriever、数据或工件写入错误）。CLI 不自动重试或切换 Provider。

## 不启动服务的验收

Windows：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q apps/api/src tests
npm run typecheck
npm run build
npm run test:e2e
```

当前 F-026 工作树基线为 416 个 Python 单元/进程内集成测试与 7 个真实浏览器 E2E 通过；指定真实 release `.exe` 后桌面启动测试也通过。E2E 启动真实 Web/API/SQLite，只替代外部模型和检索波动，不读取真实模型密钥。受控 Provider 的固定 24 Case 为 24/24 matched；本地 Ollama `qwen3:8b` 的真实 Acceptance Run 为 22/24 matched、Recall 1、FPR 0、Policy Accuracy 0.95、Replay 1，Gate 如实失败。结果只适用于固定合成靶场，不外推生产准确率。

## 本地启动

先在启动 API 的终端显式选择一种 Provider。不要把密钥写进仓库、`.env.example`、截图或日志；聊天中出现过的旧密钥应在正式演示前轮换。

默认 DeepSeek：

```powershell
$env:AGENT_AUDIT_LLM_PROVIDER = "deepseek"
$env:DEEPSEEK_API_KEY = "<rotated-key>"
```

本地 Ollama 演练（不读取 DeepSeek 密钥）：

```powershell
$env:AGENT_AUDIT_LLM_PROVIDER = "ollama"
$env:OLLAMA_BASE_URL = "http://127.0.0.1:11434/v1"
$env:OLLAMA_MODEL = "<已安装的模型名称>"
Remove-Item Env:DEEPSEEK_API_KEY -ErrorAction SilentlyContinue
```

Ollama 需提前启动并已下载所选模型。桌面端会动态列出 Ollama 返回的已安装模型，不限定 `qwen3:8b`；能否用于当前验收以四项 Provider Readiness 的实际结果为准。该路径使用 OpenAI-compatible Chat Completions 与 Tool Calling，并发送 `reasoning_effort=none`；Provider 不会自动探测或静默回退。

终端一，从仓库根目录启动 API：

```powershell
.\.venv\Scripts\python.exe -m uvicorn agent_audit_api.main:app --app-dir apps/api/src --host 127.0.0.1 --port 8000
```

终端二，从仓库根目录启动 Web：

```powershell
npm run dev --workspace @agent-audit/web -- --host 127.0.0.1 --port 5173 --strictPort
```

浏览器访问 `http://127.0.0.1:5173`。Vite 会把 `/api` 代理到 `http://127.0.0.1:8000`。DeepSeek 未配置密钥或显式选择的本地 Provider 不可用时，静态页面和只读 API 仍可加载，但需要模型的查询、攻击、Replay 或 Benchmark 会返回明确错误，不会伪造回答或切换 Provider。

成功的 Red-Team Scan、Replay 和完整 Acceptance Run 默认保存在 `data/runtime/agent_audit.sqlite3` 的独立追加表中；该文件被 Git 忽略。需要改变位置时，在启动 API 前设置 `AGENT_AUDIT_DB_PATH`。历史不保存模型密钥或 Authorization header，也不在数据库故障时退回内存结果。页面首次加载只读取历史；只有用户点击“运行完整验收”才调用模型并新增 Acceptance Run。

## Docker Compose

配置只包含现有 `web` 与 `api`，没有数据库、队列或隐藏 Demo 服务：

```powershell
$env:DEEPSEEK_API_KEY = "<rotated-key>"
docker compose up --build
```

完成后访问 `http://127.0.0.1:5173`。Compose 只把环境变量传给 API 容器，不把密钥写入镜像。当前开发机未安装 Docker，配置尚未在本机实际构建；本地 Python/Node 启动与 Ollama 现场链路已验证，详见最终验收记录。

## 五分钟演示与比赛材料

- 演示 Runbook：`artifacts/acceptance/DEMO_RUNBOOK.md`
- 评委快速指南：`artifacts/acceptance/JUDGE_QUICK_START.md`
- 申报事实底稿：`artifacts/acceptance/SUBMISSION_BRIEF.md`
- 模拟答辩：`artifacts/acceptance/DEFENSE_QA.md`
- 最终验收：`artifacts/acceptance/FINAL_ACCEPTANCE.md`
- 比赛视觉资产：`artifacts/visuals/`

## 仓库导航

- 当前状态：`docs/STATUS.md`
- 项目主线：`docs/PROJECT.md`
- 功能任务板：`docs/FEATURES.md`
- 架构与验收：`docs/ARCHITECTURE.md`、`docs/ACCEPTANCE.md`
- 合成数据：`data/demo/`
- 前后端共享契约：`packages/contracts/`

项目边界与比赛主张以 `AGENTS.md` 和 `docs/PROJECT.md` 为准。
