# F-058 本机运行引导与桌面交互响应

- 状态：Completed
- 所属里程碑：M6
- 负责人：主代理
- 相关决定：用户反馈本机 Ollama 未启动时页面直接显示 `URLError`，不应暗示必须使用 `qwen3:8b`，且桌面关闭阶段存在明显阻塞

## 用户价值

普通用户在本机模型未启动或没有模型时能直接知道如何处理，并能从 Ollama 实际返回的模型中自主选择；页面滚动后仍可切换字号，关闭窗口时也不会因同步清理后台进程而卡住界面。

## 范围

- 将 Ollama 连接失败、HTTP 异常和响应无效转换为可行动的中文诊断；
- 在本机模型发现区域明确“选择任一已安装模型，以四项 Readiness 实测为准”；
- 让包含字号选择的顶部栏在页面滚动和向导自动定位后保持可见；
- 关闭主窗口时立即结束可见交互，再在后台完成同一 owned Sidecar 进程树清理后退出；
- 保留动态模型枚举与显式选择，不预选、不下载、不 fallback；
- 同步当前使用说明，区分“示例模型”和“固定要求”。

## 非目标

- 不自动启动、安装或下载 Ollama/模型；
- 不根据模型名称猜测能力或跳过 Readiness；
- 不改写历史 `qwen3:8b` 真实验收记录；
- 不扩大到局域网模型发现或任意 Endpoint 扫描。
- 不跳过 Sidecar、端口和孤儿进程清理，也不按进程名终止未知进程。

## 前后端与数据影响

- Web：调整本机发现失败、空模型列表和模型选择说明；顶部栏改为滚动常驻；
- API：返回稳定、可读且不泄露底层异常类型的 Ollama 诊断；
- Desktop：将关闭事件中的同步进程树清理移出窗口事件线程；
- Contracts：无字段变化；
- Data/Model/Tool：无持久化、Provider 或执行语义变化。

## API 或交互契约

- `POST /api/provider-discoveries/ollama` 仍只访问固定 `127.0.0.1:11434/api/tags`；
- 连接失败返回 `status=unavailable`、空模型列表和中文处理建议；
- 发现成功返回 Ollama 的实际模型列表，用户显式选择后仍须通过四项 Readiness 才能保存。

## 实施任务

- [x] 更新 API 诊断与单元/集成断言；
- [x] 更新 Web 模型中立文案与浏览器回归；
- [x] 保持“标准 / 大字”控件在连接区域可见；
- [x] 消除关闭窗口时的可见阻塞，并保留进程/端口清理；
- [x] 同步使用说明并完成定向验证。

## 验收标准

- [x] Ollama 未运行时页面不再显示 `URLError`、`OSError` 等底层异常名；
- [x] 页面明确没有指定必选模型，并继续列出 Ollama 实际返回的所有合法模型；
- [x] 向导滚动到连接区域后仍能直接切换“标准 / 大字”；
- [x] 点击关闭后窗口立即隐藏，Desktop/Sidecar 最终退出、端口释放且无孤儿进程；
- [x] 连接失败仍不重试、不 fallback、不扫描局域网；
- [x] 相关 Python、Web typecheck/build 与 Playwright 定向回归通过。

## 验证证据

- 测试命令：`.venv\Scripts\python.exe -m pytest -q`；`npm run test:e2e`；`npm run typecheck`；`npm run build`；Python `compileall`、`pip check`；Rust library test、`cargo check`、`cargo fmt --check`；真实 Desktop lifecycle；`git diff --check`。
- 结果：Python `880 passed, 10 skipped`；Playwright `37 passed`；Rust library `11 passed`；typecheck、production build、compileall、pip check 与 cargo check 均通过。Python 仅保留一个既有 Starlette/httpx deprecation warning，Web build 仅保留既有 chunk-size warning。
- 人工/工件步骤：已复现当前机 Ollama 已安装但进程未运行、11434 未监听，旧页面显示 `Ollama discovery unavailable (URLError)`；旧 Desktop lifecycle 单轮 `closeElapsedMs=6359`。修复后新 `0.1.2` release Desktop 单轮总退出耗时 `1297 ms`，窗口先隐藏，随后端口释放、孤儿进程为 0、进程退出码为 0；证据位于 `artifacts/acceptance/generated/f058-close-fixed-20260831/evidence/desktop-lifecycle-20260831T133621753213Z-29456/desktop-lifecycle.json`。

## 实施记录

- 历史文档中的 `qwen3:8b` 表示当次真实验收使用的模型，继续作为事实保留；它不是当前产品模型白名单。
- Ollama discovery 仍只发出一次固定 loopback 请求；不可用、HTTP 异常和无效响应分别返回稳定中文诊断，不暴露底层异常类型。
- 模型下拉框直接消费 Ollama 返回列表，E2E 同时返回 `qwen3:8b` 与 `llama3.2:3b` 验证非固定模型枚举；选择后仍经过既有 Readiness。
- 顶部栏使用 sticky 定位，向导自动滚动或用户滚动时“标准 / 大字”继续可见。
- Desktop CloseRequested 先阻止默认关闭并隐藏窗口，再由单次后台 shutdown 执行原有 owned Sidecar 进程树清理，完成后退出应用；没有按进程名终止未知进程。
- 新 Windows 安装包为 `artifacts/desktop/generated/知盾 AgentAudit_0.1.2_x64-setup.exe`。
