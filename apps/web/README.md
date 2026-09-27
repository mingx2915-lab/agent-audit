# AgentAudit Web

Vue 3 + TypeScript + Element Plus 单页软件客户端。页面按 Audit Setup、Live Audit、Findings & Replay 三个互斥工作区组织真实 API 返回的 Contract/Runtime、Attack Plan/Scan、Trace/Finding、历史 Snapshot/Replay、Differential、Retrieval Evaluation、24 Case Benchmark 与 AttackChainReport，不在前端复制权限判定、Finding 或检索指标计算，也不使用浏览器存储伪造审计历史。

从仓库根目录安装和验证：

```powershell
npm ci
npx playwright install chromium
npm run typecheck
npm run build
npm run test:e2e
```

`test:e2e` 从仓库根目录启动 Test-only FastAPI 与真实 Vite 客户端，使用临时 SQLite 和显式 Test Double 覆盖持久化 Scan/Replay、刷新恢复、窄屏主操作及 Provider 可读错误。它不调用 DeepSeek/Ollama，也不通过浏览器拦截伪造核心 API 结果。

启动开发服务器：

```powershell
npm run dev --workspace @agent-audit/web -- --host 127.0.0.1 --port 5173 --strictPort
```

开发模式把 `/api` 代理到 `http://127.0.0.1:8000`。生产容器由 Nginx 提供静态文件，并把同一路径代理到 Compose 中的 `api:8000`；浏览器不接触模型密钥。
