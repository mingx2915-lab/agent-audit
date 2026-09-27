# F-057 工程证据闭环与跨平台质量门

- 状态：Completed
- 所属里程碑：M6
- 负责人：主代理
- 相关决定：用户要求跳过陌生用户五分钟任务，优先收口供应链、目标环境、CI、文档与性能证据；2026-09-27 用户要求处理首轮 Actions 暴露的问题并重跑验证

## 用户价值

让发布者和评委能够区分“已运行”、“已审阅”、“已处置”和“仍待真实环境验证”，并用可重复的跨平台回归与性能观测取代笼统的工程成熟度表述。

## 范围

- 对 F-056/release-5 中的 RustSec Finding 逐项登记可达性、产品影响、owner、处置路线和期限；同步记录 RustSec 已撤回的 advisories 与当前仍待处置项，不伪造 accepted/allowlisted；
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
- [x] 修正首轮 GitHub Actions 暴露的 Python runner 选择和品牌主图缺失；
- [x] 修复 scan / acceptance SQLite 只读数据库的读取与拒绝写入行为；
- [x] 应用可兼容的已发布依赖补丁；将 10 条已撤回 GTK advisories 标注为撤回记录，并对 8 条仍 active 的 RustSec Finding 保持 pending、完成可达性评估和精确披露；
- [x] 收口三项目标环境的可执行验收入口与证据模板，真实未跑项保持 pending；
- [x] 生成一份当前机器的可复跑性能/资源基线，写明不能外推的边界；
- [x] 只修事实地同步 F-052/F-031 等时间线及当前状态；
- [x] 完成定向回归、仓库 diff 审计与证据索引。

## 验收标准

- [x] release-4 的 40 个 review 项完成逐项核对；release-5 历史集合中的 18 条 RustSec advisory 与 1 个 metadata-unknown license 均有登记；2026-09-27 在线扫描确认当前 8 条 RustSec finding，另 10 条 GTK advisories 已由 RustSec 撤回，未伪造 accepted；
- [x] Windows/Linux CI 均运行核心 Python、Web typecheck/build/E2E 与 Rust check/test/fmt，Windows/Linux Sidecar 构建和 whitespace check 均通过；平台专属工件验收保持独立显式边界；
- [x] 干净 Windows、Debian pointer、真实企业 Gateway 均有单一可执行入口，并且未执行时不显示 passed；
- [x] 性能基线来自实际命令与机器可读结果，不声称真实模型或长期稳定性；
- [x] STATUS、FEATURES、相关功能文档和证据索引的当前事实一致；
- [x] 不包含 Secret、用户企业正文、绝对用户路径或对外网络扫描。

## 验证证据

- 历史供应链证据：`windows-20260831-release-5` 最初报告 Cargo 549 个组件、18 条 RustSec Finding；npm 140 个组件 0 Finding；Python Runtime 42 个组件 0 漏洞 Finding、2 weak-copyleft、1 metadata unknown。后续 advisory 状态有变化，不能把这份旧报告当成当前 scan；
- Python license 根因修复：scanner 现在读取目标解释器 `importlib.metadata` 的 PEP 639 `License-Expression`、可识别 legacy SPDX 与 classifier；unknown 从 22 降到 1。PyInstaller 使用 `copy_metadata("agent-audit-api", recursive=True)`，新冻结 Sidecar 对原 22 个包逐项确认 METADATA 和至少一份 LICENSE/LICENCE/COPYING 文件均存在；
- 当前供应链登记：`data/demo/supply-chain-review.json` 保留 release-5 的 19 项审查来源。RUSTSEC-2024-0411..0420 于 2026-08-14 被 RustSec 撤回，登记为撤回记录（不代表依赖已替换）；其余 8 项保持 `in_progress`。`py_rust_stemmers` scanner 仍保留 `licenseCategory=unknown`，但本机 distribution 的 canonical MIT LICENSE 和冻结 Sidecar 包含性均已核实，人工 review 标记 `fixed`；没有 accepted/allowlisted；
- 登记校验：`python apps/api/scripts/review_supply_chain_evidence.py --summary artifacts/supply-chain-evidence/windows-20260831-release-5/windows-20260831-release-5/summary.json --register data/demo/supply-chain-review.json --validate`，结果 `valid (19 items)`；
- 当前 Windows 开发机：`python -m pytest -q` 为 `880 passed, 10 skipped`；`npm run test:e2e` 为 `36 passed`；Rust library 为 `10 passed`；`typecheck`、production build、`compileall`、`pip check`、`cargo check`、源码 `rustfmt --check` 与 `git diff --check` 通过；
- 性能基线：除原 100/100 外，新增显式 `--long-soak` 的 1,000 轮容量基线 `artifacts/acceptance/generated/f057-core-1000-20260831/stability_ce048cf91e6c.json`；1000/1000 workflow、Finding 与 Replay 通过，p50 `27.44 ms`、p95 `30.97 ms`、History `1000`、Provider calls `6000`，总时长约 `28.04 s`。它仍只使用 deterministic provider、临时 SQLite 和 7 文档合成数据，不是小时级持续运行或真实模型资源结论；
- 新冻结 Windows Sidecar 完成 1 次正常 lifecycle 与 1 次 crash-recovery，结果 passed；这只验证递归 metadata 打包没有破坏启动，不替代干净 Windows 验收；
- 在线供应链扫描：[GitHub Actions run 36322348763](https://github.com/mingx2915-lab/agent-audit/actions/runs/36322348763)，报告生成成功并上传 artifact；npm 140 项 0 finding，Python 40 项 0 vulnerability finding、1 metadata-unknown license 和 2 weak-copyleft，Cargo 549 项中 8 个 pending RustSec Finding。工作流以 `status=findings` 结束，保留扫描失败门，不是扫描器或 setup 故障；
- 2026-09-27 本地修复：quality matrix 的 Python 选择由固定补丁版改为 `3.11`；源码包补回与 Web/desktop 图标 SHA-256 相同的品牌主图 `249B5E795CD117968B0FFBFB4AFC95E1ACD4D6BAF4D5DD3E436A846D050F11BC`；SQLite SELECT 路径只读打开，初始化/迁移与写入仍走显式可写连接。质量矩阵也新增了正式 Windows/Linux Sidecar 构建步骤，避免干净 runner 在 Tauri `externalBin` 检查阶段失败；
- 2026-09-27 Windows 本地质量命令：Python 3.11.9 `894 passed, 22 skipped`，`compileall`、`pip check` 通过；Node 20.19.0 `typecheck`、production build 通过。修复 F-062 图片资源时序断言后，critical-image 用例本机重复 5 次通过；Windows MSVC Rust 验收由 GitHub runner 完成；
- 2026-09-27 Linux/WSL 本地质量命令：Python 3.11.13 `909 passed, 7 skipped`，`compileall`、`pip check` 通过；Rust 1.88 `cargo check --locked` 和 `cargo test --locked --lib`（12 项）通过，Linux Sidecar 按正式脚本构建。Node 20.19.0 `typecheck`、production build 通过；本机 WSL 是 Ubuntu 26.04，Playwright 明确不支持该系统，故本地 Linux E2E 未执行（GitHub 矩阵目标仍为 Ubuntu 24.04）；
- 2026-09-27 依赖处置：将 `pdf-extract` 锁定版本从 0.12.0 更新到兼容补丁版 0.12.1；锁定图仍为 `pdf-extract 0.12.1 -> lopdf 0.42.0 -> ttf-parser 0.25.1`，故 `RUSTSEC-2026-0192` 保持未解决。GitHub 在线扫描读取 2026-09-26 更新的 RustSec Advisory DB，确认当前 8 条 pending；其余 GTK3/glib、urlpattern/unic 与 build-time proc-macro Finding 未做不兼容强升，逐项说明见候选披露；
- 2026-09-27 跨平台矩阵：[GitHub Actions run 36322346424](https://github.com/mingx2915-lab/agent-audit/actions/runs/36322346424)，提交 `2e655c7519cdadbace1c6358ce45e6abf8dcea7d`；Windows 2022 与 Ubuntu 24.04 两个 job 均成功，核心 Python、typecheck/build、完整 E2E、平台 Sidecar、Rust fmt/check/library tests 和 whitespace check 均通过。CI 首次暴露的 F-062 `currentSrc` 空值来自图片资源尚未完成选择时的立即断言；加入真实加载条件后，定向重复用例通过，随后完整矩阵通过；
- 矩阵边界：CI 验证指定 runner 上的构建与回归，不替代另一台干净 Windows PC 的完整安装验收，也不替代独立 Linux 桌面验收。源树未添加许可证，公开复用授权仍由项目所有者决定；
- 外部人工步骤：`docs/TARGET_ENVIRONMENT_ACCEPTANCE.md` 中三项仍为 `not_verified`。用户决定暂缓干净 Windows、之后找人安装；Debian pointer 需要 Linux 目标环境；真实企业 Gateway 找不到时保持非阻塞外部边界，不声称真实企业部署。

## 实施记录

- F-057 是工程证据收口，不改变知盾 AgentAudit 的业务范围；
- CI 能提高持续回归证据，但不替代目标机上的真实安装、凭据存储和工件行为；
- 供应链影响评估和风险处置是两个阶段；本功能不把“已评估”写成“已修复”。
- 2026-08-31：三个 Luna Max 子任务分别完成供应链 review/性能证据、F-057 负向回归、跨平台 CI 与前端可移植性审计；主代理复核并修正 pending unknown license 不得汇总为 `passed` 的生产缺口。
- 2026-09-27：Windows/Ubuntu 矩阵通过后，F-057 工程证据门完成；8 个 RustSec finding 仍按未解决状态披露，三项目标环境验收仍为独立外部证据，不因 CI 通过而自动升级。
- 2026-08-31：用户要求继续完成当前机器可执行项，并明确暂缓干净 Windows 安装验收；本轮只推进供应链许可证/依赖核实、长时间基线与质量矩阵本地验证，不改变 Debian、真实 Gateway 和干净 Windows 的 `not_verified` 状态。
- 2026-08-31：完成 release-5 在线扫描、Python metadata 通用修复、Sidecar 递归 license metadata 打包和 1,000 轮容量 soak。RustSec 剩余 18 项均来自已确认依赖路径：GTK3/Tauri、tauri-utils/urlpattern、构建期 proc macro 或 pdf-extract/lopdf/ttf-parser；不做脱离上游兼容性的单 crate 强升。
- 2026-09-27：用户要求处理 Actions 暴露的 CI/SQLite/RustSec 项；修正 Windows 图片加载断言时序、记录 10 条 RustSec 官方撤回 advisories、披露 8 条当前 pending。GitHub Windows/Ubuntu 矩阵在 `2e655c7` 全部通过；在线供应链报告上传成功且保留 8 个 Finding，因此完成的是工程证据闭环，不是所有依赖风险已清零。
