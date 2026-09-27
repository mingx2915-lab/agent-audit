# Tests

测试按价值分层：

- `unit/`：Policy、Trace 等确定性规则；
- `integration/`：API、持久化、模型/RAG/Tool Adapter；
- `e2e/`：少量比赛关键路径；
- `fixtures/`：固定角色、资源、策略和 Trace 样例。

不追求无意义的覆盖率数字，优先保护项目核心结论和演示链路。

浏览器 E2E 从仓库根目录执行：

```powershell
npx playwright install chromium
npm run test:e2e
```

`tests/e2e/support/server.py` 只替代外部 Provider/Retriever 波动；真实 Vue、FastAPI、Planner、Target、Trace、Checker、SQLite 和 Replay 均参与执行。配置为单 worker、零重试，不复用已占用的 8000/5173 服务。
