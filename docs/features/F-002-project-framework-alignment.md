# F-002 按新框架统一产品命名与主线

- 状态：Done
- 所属里程碑：M0
- 负责人：Codex
- 相关决定：D-006、D-007、D-008、D-009、D-010

## 用户价值

让后续开发、前后端设计、验收和比赛叙事都以同一份项目框架为准，避免继续沿用 AegisAC 的旧命名或退化为通用 Prompt Scanner。

## 范围

- 正式命名为“知盾 AgentAudit——企业知识助手业务权限安全验收与自动化红队系统”；
- 将 Security Contract、双攻击者、全过程 Trace 和修复 Replay 固定为产品主张；
- 将企业知识助手靶场、四类核心场景、Hybrid Judge 和 Ground Truth 测试写入范围与验收；
- 锁定 Vue/FastAPI/PostgreSQL/Docker Compose 的真实全栈技术基线；
- 明确模型厂商、Case 数量、复杂多轮攻击和 PDF 等不是不可变主约束；
- 明确只使用受控靶场、合成数据和 Mock Tools。

## 非目标

- 实现任何前端、后端、RAG 或 Agent 代码；
- 验证调研报告中每一条市场数据和产品事实；
- 锁定具体模型供应商或版本；
- 建立任意外部目标验证、DNS Challenge 或复杂授权硬门；
- 导入报告中的内部引用占位符作为正式比赛引用。

## 前后端与数据影响

- Web：统一 Dashboard 领域为 Contract、Scan、Trace、Finding、Replay；
- API：统一模块边界为 Orchestrator、Target、Trace、Contract、Judge、Finding、Replay；
- Contracts：确定首批共享领域对象名称；
- Data/Model/Tool：采用“星云科技”合成数据和 Mock Enterprise Tools，模型通过 Provider Adapter 接入。

## 实施任务

- [x] 更新产品名称和一句话定位
- [x] 更新项目主约束与防偏移规则
- [x] 更新功能路线图和编号
- [x] 更新架构、技术栈和领域对象
- [x] 更新核心验收与安全边界
- [x] 更新前后端及 Demo 数据目录说明

## 验收标准

- [x] 项目主文档不再使用 AegisAC 作为当前产品名
- [x] Security Contract、双攻击者、全过程 Trace、Hybrid Judge 与 Replay 在主线和验收中一致
- [x] MVP 明确为一个受控企业知识助手靶场和四类核心安全场景
- [x] 技术栈能够支撑真实前后端，又未引入微服务、Kubernetes 或完整 IAM
- [x] 模型厂商和报告中的可变建议未被误写成不可变主线
- [x] F-002 在任务板中勾选并划掉，状态页指向新的下一功能

## 验证证据

- 文档一致性：8 项自动检查全部通过，包括正式名称、F-002 完成标记、F-003 下一步、核心主张、技术栈和 Replay 验收
- 旧名称检查：AegisAC/AgentSec 只保留在历史决定和“禁止继续使用”的说明中
- Git 检查：`git diff --check` 无空白错误
- 人工核对：`AGENTS.md`、`PROJECT.md`、`FEATURES.md`、`ARCHITECTURE.md`、`ACCEPTANCE.md` 和 `STATUS.md` 的主线一致

## 实施记录

新框架中的研究结论被区分为稳定产品约束、当前技术基线和可调整候选项。没有把具体模型版本、固定 Case 数量或扩展功能固化成代码门禁。
