# F-057 工程证据闭环与跨平台质量门

- 状态：Implementation Complete / External Acceptance Pending
- 所属里程碑：M6
- 负责人：主代理
- 相关决定：用户要求跳过陌生用户五分钟任务，优先收口供应链、目标环境、CI、文档与性能证据

## 用户价值

让发布者和评委能够区分“已运行”、“已审阅”、“已处置”和“仍待真实环境验证”，并用可重复的跨平台回归与性能观测取代笼统的工程成熟度表述。

## 范围

- 对 F-056 release-4 真实证据中的 18 个 pending RustSec Finding 逐项登记可达性、产品影响、owner、处置路线和期限，不伪造 accepted/allowlisted；
- 对 release-4 的 22 个 Python unknown license 读取目标解释器标准 distribution metadata，并核实冻结 Sidecar 分发包含性；无法由机器字段解析的项目保持 scanner unknown，再以显式人工证据决定；
- 建立 Windows/Linux 核心回归矩阵，保留 Linux release 和 supply-chain 的专项工作流；
- 为干净 Windows、Debian 非默认 active Workspace pointer、真实企业 Gateway/凭据形成统一的可执行验收入口和证据边界；
- 对 F-052/F-031 等少量旧阶段描述做仅修事实的文档同步；
- 在固定环境、固定数据和显式命令下生成性能/资源观测基线，不将单次观测写成 L4 或长期稳定性结论。

## 非目标

- 不执行 F-035 陌生用户五分钟任务；
- 不在没有目标机、真实 Gateway 或授权凭据时伪造 L4 证据；
- 不为追求全绿而静默 allowlist、自动接受风险或做不兼容依赖替换；
- 不新增攻击类别、业务页面、外部扫描、真实邮件外发或企业数据读取；
- 不把 CI runner 等价为干净目标机的安装/升级/卸载人工验收。

## 前后端与数据影响

- Web：无产品功能变更；只允许现有 E2E 跨平台回归所必需的最小修正；
- API：仅补供应链 review 与性能证据的显式离线入口，不新增业务 HTTP API；
- Contracts：无跨端业务 DTO 变更；
- Data/Model/Tool：只读仓库 lockfile、已生成证据和合成/隔离 Workspace；不读用户企业资料或 Provider Secret。

## API 或交互契约

- 供应链 review 是仓库内可审阅文件，每项必须包含稳定唯一键、来源、影响、owner、状态、处置路线和期限；
- `accepted`/`allowlisted` 仍严格沿用 F-056 的 reason/owner/future expiry 契约；影响分析不自动改变 Finding 状态；
- CI 核心矩阵在 Windows/Linux 上使用同一份锁定依赖与明确命令，任一必需步骤失败即失败，不设静默 fallback；
- 目标环境验收必须记录 OS/工件/revision/命令/结果/边界，未执行保持 pending；
- 性能证据必须记录机器、数据规模、Provider/Retriever、重复次数、p50/p95、内存/句柄/进程与数据库观测方法。

## 实施任务

- [x] 建立并校验 18 个 RustSec Finding 和 22 个 Python unknown license 的逐项 review 登记；
- [x] 建立 Windows/Linux 核心回归矩阵，与已有 Linux release / supply-chain workflow 边界一致；
- [x] 收口三项目标环境的可执行验收入口与证据模板，真实未跑项保持 pending；
- [x] 生成一份当前机器的可复跑性能/资源基线，写明不能外推的边界；
- [x] 只修事实地同步 F-052/F-031 等时间线及当前状态；
- [x] 完成定向回归、仓库 diff 审计与证据索引。

## 验收标准

- [x] release-4 的 40 个 review 项完成逐项核对；修正 scanner 后，release-5 当前集合精确收敛为 18 个 RustSec Finding 和 1 个已人工核实的 metadata-unknown license，没有遗漏、重复或虚假 accepted；
- [ ] Windows/Linux CI 均运行核心 Python、Web typecheck/build/E2E 与 Rust check/test/fmt 中适用的回归，平台专属工件验收保持独立显式边界；
- [x] 干净 Windows、Debian pointer、真实企业 Gateway 均有单一可执行入口，并且未执行时不显示 passed；
- [x] 性能基线来自实际命令与机器可读结果，不声称真实模型或长期稳定性；
- [x] STATUS、FEATURES、相关功能文档和证据索引的当前事实一致；
- [x] 不包含 Secret、用户企业正文、绝对用户路径或对外网络扫描。

## 验证证据

- 供应链新证据：`windows-20260831-release-5` 为 `status=findings`；npm 140 个组件全部 permissive、0 Finding；Python Runtime 42 个组件为 39 permissive、2 weak-copyleft、1 metadata unknown、0 Finding；Cargo 549 个组件、18 个 pending RustSec Finding；
- Python license 根因修复：scanner 现在读取目标解释器 `importlib.metadata` 的 PEP 639 `License-Expression`、可识别 legacy SPDX 与 classifier；unknown 从 22 降到 1。PyInstaller 使用 `copy_metadata("agent-audit-api", recursive=True)`，新冻结 Sidecar 对原 22 个包逐项确认 METADATA 和至少一份 LICENSE/LICENCE/COPYING 文件均存在；
- 当前供应链登记：`data/demo/supply-chain-review.json` 与 release-5 精确对应 19 项。18 个 RustSec Finding 为 `in_progress`；`py_rust_stemmers` scanner 仍保留 `licenseCategory=unknown`，但本机 distribution 的 canonical MIT LICENSE 和冻结 Sidecar 包含性均已核实，人工 review 标记 `fixed`；没有 accepted/allowlisted；
- 登记校验：`python apps/api/scripts/review_supply_chain_evidence.py --summary artifacts/supply-chain-evidence/windows-20260831-release-5/windows-20260831-release-5/summary.json --register data/demo/supply-chain-review.json --validate`，结果 `valid (19 items)`；
- 当前 Windows 开发机：`python -m pytest -q` 为 `880 passed, 10 skipped`；`npm run test:e2e` 为 `36 passed`；Rust library 为 `10 passed`；`typecheck`、production build、`compileall`、`pip check`、`cargo check`、源码 `rustfmt --check` 与 `git diff --check` 通过；
- 性能基线：除原 100/100 外，新增显式 `--long-soak` 的 1,000 轮容量基线 `artifacts/acceptance/generated/f057-core-1000-20260831/stability_ce048cf91e6c.json`；1000/1000 workflow、Finding 与 Replay 通过，p50 `27.44 ms`、p95 `30.97 ms`、History `1000`、Provider calls `6000`，总时长约 `28.04 s`。它仍只使用 deterministic provider、临时 SQLite 和 7 文档合成数据，不是小时级持续运行或真实模型资源结论；
- 新冻结 Windows Sidecar 完成 1 次正常 lifecycle 与 1 次 crash-recovery，结果 passed；这只验证递归 metadata 打包没有破坏启动，不替代干净 Windows 验收；
- CI：`.github/workflows/quality-matrix.yml` 已建立 Windows 2022 / Ubuntu 24.04 矩阵，但尚未获得 GitHub runner 的首轮实际结果，因此对应验收项保持未勾选；
- 外部人工步骤：`docs/TARGET_ENVIRONMENT_ACCEPTANCE.md` 中三项仍为 `not_verified`。用户决定暂缓干净 Windows、之后找人安装；Debian pointer 需要 Linux 目标环境；真实企业 Gateway 找不到时保持非阻塞外部边界，不声称真实企业部署。

## 实施记录

- F-057 是工程证据收口，不改变知盾 AgentAudit 的业务范围；
- CI 能提高持续回归证据，但不替代目标机上的真实安装、凭据存储和工件行为；
- 供应链影响评估和风险处置是两个阶段；本功能不把“已评估”写成“已修复”。
- 2026-08-31：三个 Luna Max 子任务分别完成供应链 review/性能证据、F-057 负向回归、跨平台 CI 与前端可移植性审计；主代理复核并修正 pending unknown license 不得汇总为 `passed` 的生产缺口。
- 当前本地实现已收口；F-057 保持未勾选，直到 Windows/Linux 远程矩阵真实运行。三项目标环境验收属于独立外部证据，不因 CI 通过而自动升级。
- 2026-08-31：用户要求继续完成当前机器可执行项，并明确暂缓干净 Windows 安装验收；本轮只推进供应链许可证/依赖核实、长时间基线与质量矩阵本地验证，不改变 Debian、真实 Gateway 和干净 Windows 的 `not_verified` 状态。
- 2026-08-31：完成 release-5 在线扫描、Python metadata 通用修复、Sidecar 递归 license metadata 打包和 1,000 轮容量 soak。RustSec 剩余 18 项均来自已确认依赖路径：GTK3/Tauri、tauri-utils/urlpattern、构建期 proc macro 或 pdf-extract/lopdf/ttf-parser；不做脱离上游兼容性的单 crate 强升。
