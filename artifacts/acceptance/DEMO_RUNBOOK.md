# Windows 桌面版五分钟演示 Runbook

> SYNTHETIC / DEMO ONLY。演示对象是仓库内受控企业知识助手、合成数据和 Mock Enterprise Tools，不扫描外部系统、不发送真实邮件。默认入口是 Windows 桌面应用；演示不要求打开浏览器、访问本机 URL 或启动 API/Web 终端。

## 演示目标

五分钟内完成一条可复核的主线：

```text
Guided Source→Sink Scan → 严重 Critical Finding → 同一 Attack Plan Replay
```

现场要证明的是：Security Contract 派生攻击目标，真实 Retrieval、Authorization、Tool 与 Sink 事件进入 Trace，Contract Checker 根据实际 Trace 产生 Finding；切换修复配置后，对同一 `plan / actor / target / message` 执行 Replay 并通过。主线结论来自桌面应用启动的真实 Sidecar 和业务链路，不来自预制动画、静态 JSON 或手工改写结果。

## 台前准备（不计入五分钟）

1. 使用当前用户安装的 NSIS 包 `artifacts/desktop/generated/知盾 AgentAudit_0.1.2_x64-setup.exe` 完成安装，随后从开始菜单或桌面快捷方式启动“知盾 AgentAudit”。普通用户不需要 Python、Node、Rust、浏览器或单独的 API/Web 进程。
2. 应用数据默认位于 `%LOCALAPPDATA%\AgentAudit`，默认 Workspace 为 `%LOCALAPPDATA%\AgentAudit\workspaces\default`。首次启动应由 packaged `demo-seed` 创建 Workspace；不要把开发仓库路径当作现场运行数据根。
3. 本地 Ollama 仍需提前安装、启动并至少准备一个候选模型。桌面连接页会从固定 `127.0.0.1:11434` 动态列出实际模型；不限定 `qwen3:8b`，用户选中候选模型并完成四项 Readiness 后再确认设置。
4. F-027 已提供首次连接向导、固定 loopback 发现与显式模型选择；它不自动启动 Ollama、不下载或预选模型，也不 retry/fallback。演示前可完成连接设置，但不得展示任何企业密钥。
5. 启动后确认只出现 AgentAudit 独立窗口，Sidecar 已 ready，首页停留在“核心验收”。若弹出外部浏览器、命令行窗口或开发服务器，停止演示并按失败路径记录。
6. 如需展示 Readiness 或 24 Case Acceptance，优先使用已有真实保存记录。没有对应真实记录时应跳过，不为本次材料临时伪造、改写或补跑结果；它们是高级证据，不是五分钟主线的前置条件。

## 五分钟主线

| 时间 | 桌面应用操作 | 讲解主张 | 必须指向的真实证据 |
|---|---|---|---|
| 0:00–0:25 | 双击“知盾 AgentAudit”，停留在“核心验收”工作区 | 这是 Windows 单用户桌面交付；应用、Sidecar 和 Workspace 分离，普通用户不需要浏览器或本机 URL | 独立桌面窗口；默认 Workspace 已加载；页面标注 `SYNTHETIC / DEMO ONLY` |
| 0:25–1:25 | 点击“开始核心验收” | Guided 主线自动使用 Contract-derived 的 Source→Sink Plan，不让评委先理解 JSON 或 API | 页面显示 Actor、Target、Rule、Attacker；真实 Scan/Attempt 返回后再投影攻击链，不展示猜测结果 |
| 1:25–2:25 | 在“真实攻击链”区域展开关键节点 | 重点不是模型最后说了什么，而是 Source、Resource、Authorization、Tool、Sink 是否真的发生 | `Actor → Source → Resource → Authorization → Tool → Sink`；Trace event sequence、授权决策、Source trust、资源和 Sink 事实 |
| 2:25–3:25 | 聚焦页面的“严重 Critical”Finding | Contract Checker 从实际 Trace 定位业务规则违规；Finding 不由 expected 字段或 LLM 单独裁决 | `severity=critical`、`ruleId`、Finding category、evidence sequence，以及对应的真实 Trace 事件 |
| 3:25–4:25 | 点击“应用修复并 Replay”，等待结果 | 不换 Actor、Target、Message 或 Plan；只应用修复配置，验证同一攻击是否被阻断 | BEFORE `FAILED` 且存在 Finding；AFTER `BLOCKED`/不再到达受限 Sink、`PASSED`；页面显示 `REPLAY PASSED` |
| 4:25–5:00 | 回到 Replay 结论，口述闭环；评委追问时再打开高级证据 | 价值是“发现 → 定位 → 修复 → 同攻击回归”，Readiness/24 Case 是质量与兼容性补充证据 | BEFORE/AFTER 共用同一 `plan / actor / target / message`；Replay 结论和两侧 Trace 对得上 |

### 主线通过条件

- Scan 的 Attempt、Trace 和 Finding 均由当前桌面应用真实返回；不能只显示计划或预制 Finding。
- Critical Finding 必须能回指 `ruleId` 与 evidence sequence，且能在 Trace 中看到对应的 Authorization、Resource、Tool 或 Sink 事实。
- Replay 必须是同一 Attack Plan；修复前后只比较真实执行配置和结果，不能换目标后宣称“同攻击”。
- AFTER 必须证明受限资源或外部 Sink 没有越过修复后的授权边界，且 Replay 状态为 `PASSED`。

## 高级证据（按需展开）

| 证据 | 桌面应用中的位置 | 现场应说明 |
|---|---|---|
| Provider Readiness | “核心验收”或“证据与评测”区域的 Readiness 卡片 | 这是 connectivity、native Tool Calling、strict JSON 等兼容性探针；它不直接决定 Finding，也不替代主线 Trace。 |
| 24 Case Acceptance | “证据与评测”工作区的 Acceptance Run 历史/详情 | 固定 24 Case 是质量门证据；应展示已保存 Run 的真实 Provider、指标、Gate/verdict 和调用边界，不把 Readiness 或 Test Double 结果冒充实时本地模型结果。 |
| Contract / 完整 Trace | “Contract 与 Plan”“完整 Trace”工作区 | 用于回答规则如何派生计划、每个事件如何进入证据链；不是五分钟开始前的必经页面。 |

高级证据必须与保存的 Run 一致。若现场没有可核对的真实记录，直接说明“本次只展示 Guided 主线”，不得临时修改 Ground Truth、数据库或页面结果。

## 本地模型与产品边界

- F-026 提供桌面窗口、Sidecar 生命周期、loopback API、可移植 Workspace 和当前 Windows 安装包；F-027 在此基础上提供固定 loopback Ollama 发现、模型显式选择和 Readiness。
- 产品不自动启动 Ollama、不下载或预选模型、不静默切换 Provider，也不 retry/fallback；候选模型是否可用由四项 Readiness 的实际结果决定。
- 当前 F-026 已通过当前开发机的实现、构建、release、Sidecar 和 NSIS 验收，但尚未在无仓库、无 Python/Node 的另一台干净 Windows 复核；演示材料不得宣称 F-026 已完成。
- 数据、角色、文档、客户和外部动作均为合成/Mock；不连接真实邮箱、CRM、企业文件或任意外部 Endpoint。

## 透明备份与失败处理

允许使用已有的、明确标注为“预先实际执行”的 Trace/报告 JSON、Markdown 或截图继续解释；本次材料更新不新增模型 Run、不生成新截图、不把静态工件注入页面。

出现以下情况时不得记为主线通过：

- Ollama 不可用、模型未显式配置或 Sidecar 未 ready；应直说 Provider/运行环境不可用，不切换 Provider。
- BEFORE 没有真实 denied→model_context 或 Source→Sink 证据却出现 Finding；
- AFTER 仍把受限资源带入上下文或仍到达受限 Sink；
- 更换 `actor`、`target`、`message` 或 `plan` 后声称是同攻击 Replay；
- 报告或高级证据触发额外模型调用，却没有如实说明；
- 页面、日志、截图或导出暴露密钥、真实个人信息或外部目标。

主线失败时可以展示已有自动化测试和历史保存证据，但要明确它们是独立的预先执行证据，不能说成当前桌面现场已通过。
