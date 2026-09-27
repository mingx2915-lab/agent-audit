# 命名规范

## 项目与目录

- 正式产品名：`知盾 AgentAudit`
- 完整副标题：`企业知识助手业务权限安全验收与自动化红队系统`
- 英文产品标识：`AgentAudit`
- URL、NPM 与容器标识：`agent-audit`
- Python 包与模块：`agent_audit`
- 仓库目录：保留当前工作区名称，不强制重命名用户目录
- 顶层目录使用小写英文复数或常见约定：`apps`、`packages`、`docs`、`tests`、`data`、`artifacts`
- Web 应用：`apps/web`
- API 应用：`apps/api`
- 跨端契约：`packages/contracts`

## 功能与里程碑

- 里程碑：`M0`、`M1`、`M2`……
- 功能：`F-001`、`F-002`……
- 功能文档：`F-003-enterprise-agent-trace-slice.md`
- 功能编号一旦使用不回收；删除功能时保留记录并说明原因。

## Git

- 分支：`feature/f-003-enterprise-trace`、`fix/f-006-contract-result`
- 提交：`type(scope): summary`
- 推荐类型：`feat`、`fix`、`docs`、`test`、`refactor`、`chore`
- 示例：`feat(trace): record source-to-sink events`

## API 与代码

- HTTP 路径使用小写复数与 kebab-case：`/api/test-runs/{id}`
- HTTP JSON 字段统一使用 `camelCase`；Python 内部变量和模块使用 `snake_case`；TypeScript 变量使用 `camelCase`、类型使用 `PascalCase`。
- Type/DTO 使用业务含义命名，例如 `TraceEvent`、`Finding`，避免 `DataInfo`、`CommonResult`。
- 布尔值使用 `is`、`has`、`can` 前缀。
- 时间字段明确语义，例如 `startedAt`、`completedAt`。
- 资源、角色、动作采用稳定的业务标识，不使用展示名称参与权限判断。
- 领域术语优先使用 `SecurityContract`、`Scan`、`TestCase`、`AttackAttempt`、`TraceEvent`、`Finding`、`ReplayResult`。
- 不在代码和界面中继续使用 `AegisAC`、`AgentSec` 或泛化的 `AI Security Platform` 作为产品名。

## 文档

- 项目文档使用简体中文；代码标识、路径和标准技术术语保留英文。
- 状态只使用 `Planned`、`In Progress`、`Blocked`、`Done`。
- 完成项在任务板中同时勾选并添加删除线。
