# AgentAudit API

FastAPI 模块化单体，包含受控企业知识助手、本地 BGE Embedding Retriever、TF-IDF 对照、Mock Enterprise Tools、Security Contract、Trace、Finding、Attack Plan、Replay、24 Case Benchmark、Provider usage、SQLite Run History 与纯 Markdown Report Builder。

从仓库根目录安装：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".\apps\api[dev]"
```

正常运行使用 FastEmbed `BAAI/bge-small-zh-v1.5`（512 维、CPU、懒加载）。首次真实检索会下载约 90 MB ONNX 权重到用户缓存；模型文件不进入 Git。TF-IDF 只用于固定 Retrieval Evaluation 对照或显式测试注入，模型失败不会触发自动 fallback。

验证：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q apps/api/src tests
```

启动入口：

```powershell
.\.venv\Scripts\python.exe -m uvicorn agent_audit_api.main:app --app-dir apps/api/src --host 127.0.0.1 --port 8000
```

运行时通过 `AGENT_AUDIT_LLM_PROVIDER` 显式选择 Provider，默认值为 `deepseek`：

```powershell
# 默认 DeepSeek
$env:AGENT_AUDIT_LLM_PROVIDER = "deepseek"
$env:DEEPSEEK_API_KEY = "<rotated-key>"

# 或本地 Ollama
$env:AGENT_AUDIT_LLM_PROVIDER = "ollama"
$env:OLLAMA_BASE_URL = "http://127.0.0.1:11434/v1"
$env:OLLAMA_MODEL = "<已安装的模型名称>"
```

DeepSeek 只从 `DEEPSEEK_API_KEY` 读取认证信息；Ollama 不读取该密钥，并通过 OpenAI-compatible Chat Completions/Tool Calling 发送 `reasoning_effort=none`。`OLLAMA_MODEL` 应填写本机实际安装的模型名称，产品不限定 `qwen3:8b`，兼容性以 Readiness 实测为准。测试通过构造参数注入 Test Double。未知 Provider 或请求失败会返回可诊断错误，不自动探测、不切换 Provider，也不回退为伪造结果。

Run History 默认写入 `data/runtime/agent_audit.sqlite3`，可通过 `AGENT_AUDIT_DB_PATH` 显式改到其他本地路径。`POST /api/scans` 成功后保存完整快照；`GET /api/scans`、`GET /api/scans/{scanId}` 与 `POST /api/scans/{scanId}/replays` 提供跨重启恢复和只追加 Replay。`GET /api/runtime` 只返回当前 Provider/Retriever 元数据，不触发模型或检索。数据库不保存 API Key 或 Authorization header，存储错误不会静默降级为内存历史。

合成数据位于仓库 `data/demo/`；默认 loader 依赖仓库目录结构，因此 Docker 镜像以 editable package 保留 `/workspace/apps/api` 与 `/workspace/data` 的相对布局。
