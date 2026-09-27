# F-056 SBOM、许可证与依赖漏洞审计

- 状态：Completed
- 所属里程碑：M6
- 负责人：主代理
- 相关决定：执行 `docs/NEXT_AUTOMATED_DELIVERY_PLAN.md` 的 P5

## 用户价值

发布者和评委可以用一条显式命令获得当前锁定依赖的机器可读供应链证据，区分“已扫描且无发现”“存在待处置项”“工具或数据源不完整”和“执行失败”，避免把没有运行扫描误写成没有漏洞。

## 范围

- 从仓库当前 `package-lock.json`、`apps/api/pyproject.toml`/已解析 Python 环境和 `apps/desktop/src-tauri/Cargo.lock` 生成 Python、npm、Cargo 三生态机器可读 SBOM；
- 生成许可证清单，明确 unknown、强 copyleft、分发限制和需要人工确认的依赖；
- 通过显式命令运行三生态漏洞审计，记录 advisory 来源、数据源状态、工具版本和执行时间；
- 生成 JSON 唯一事实源、同源 Markdown 投影和 `checksums.txt`；
- 任何漏洞接受、allowlist 或处置决定必须包含理由、owner 和 expiry。

## 非目标

- 不扫描企业 Workspace、业务文档、Provider 配置、Credential Store、Secret 或用户默认应用目录；
- 不自动修改 lockfile、升级依赖、删除包或替开发者接受风险；
- 不把一次扫描解释为永久无漏洞，也不把工具缺失、离线数据库过期或网络失败解释为 passed；
- 不默认联网、不上传仓库或工件；只有调用者显式开启官方漏洞数据源查询时才允许对应工具访问其官方数据源；
- 不新增 Web/Desktop 业务页面，不启动真实模型、Provider 或外部目标扫描。

## 前后端与数据影响

- Web：无；
- API：不新增 HTTP API；新增仓库显式 CLI/脚本和离线 DTO/投影；
- Contracts：无跨端业务 DTO；
- Data/Model/Tool：只读取显式仓库 manifests/lockfiles 与工具输出；默认写入 ignored `artifacts/supply-chain-evidence/<run-id>/`，不读取企业数据。

## API 或交互契约

仓库入口：

```text
python apps/api/scripts/build_supply_chain_evidence.py \
  --output-dir artifacts/supply-chain-evidence \
  [--run-id <safe-id>] \
  [--online] \
  [--python-executable <path>] \
  [--pip-audit-python <path>] \
  [--npm-tool <path>] \
  [--cargo-tool <path>] \
  [--cargo-audit-tool <path>] \
  [--decisions <repository-json>]
```

- 默认不联网；只有显式 `--online` 才允许审计工具访问声明的官方漏洞数据源，脚本本身不上传代码或工件；
- 输出目录必须是新建或空目录，同一 `run-id` 不覆盖；所有 manifest/artifact 路径为输出根内 POSIX 相对路径；
- Python 公共类型：`SupplyChainEvidenceRunner`、`SupplyChainSummary`、`EcosystemResult`、`Component`、`LicenseRecord`、`Finding`、`FindingDecision`、`ToolFact`；
- `summary.json` 是唯一事实源，`summary.md` 只从同一最终 DTO 投影；`checksums.txt` 排除自身；
- 总状态至少为：
  - `passed`：三个生态的必需 SBOM/许可证/漏洞步骤均完成，且不存在未接受的 Finding；
  - `findings`：扫描完成且存在待处置 Finding；
  - `incomplete`：工具、漏洞数据库或数据源未提供、过期、离线不可用或某生态未完成；
  - `failed`：输入、工具执行、解析、输出或信任边界失败；
- `SupplyChainFinding` 至少包含：`ecosystem`、`package`、`version`、`advisory`、`severity`、`source`、`status`、`impact`、`decision`；
- Finding 的 `decision` 不是空字符串绕过项。任何 `accepted`/`allowlisted` 状态必须有非空 `reason`、`owner`、未来 `expiry`；过期决定重新成为待处置 Finding；
- 高风险 Finding 不得静默忽略；若工具只提供未知 severity，保留 `unknown`，不得自行降级；
- 每个生态记录 SBOM/许可证/漏洞步骤状态、工具名与版本、开始/完成时间、漏洞数据库或官方数据源名称/更新时间/可用状态；环境或工具失败必须留下结构化状态，不能生成“0 vulnerabilities”假结论。

## 实施任务

- [x] 冻结三生态 Component、License、Finding、Tool/Data Source DTO 与状态聚合规则；
- [x] 实现显式、隔离且不可覆盖的 runner/CLI；
- [x] 从当前 npm/Cargo lockfile 与 Python resolved runtime closure 生成机器可读 SBOM 与许可证清单；
- [x] 接入显式官方漏洞数据源工具并保留 offline/incomplete 边界；
- [x] 实现 accepted/allowlist 决定的 reason/owner/expiry 信任边界；
- [x] 生成同源 JSON/Markdown/checksums，并由 F-051 索引；
- [x] 完成隔离、Secret、路径、工具失败、过期决定和高风险不静默忽略测试。

## 验收标准

- [x] Python、npm、Cargo 三生态均有来自当前 lockfile 或明确标注 resolved environment 的机器可读 SBOM 和许可证记录；
- [x] 漏洞结果能区分 passed/findings/incomplete/failed，工具或数据源失败不显示无漏洞；
- [x] 每个 Finding 具有完整生态、包、版本、advisory、severity、source、status、impact 与 decision；
- [x] accepted/allowlist 只有在 reason、owner、未来 expiry 完整时有效，过期项恢复待处置；
- [x] JSON/Markdown/checksums 同源且可复算，输出不含绝对用户路径、Secret、企业 Workspace 或业务正文；
- [x] 默认流程不调用真实模型/Provider、不上传仓库；显式在线漏洞查询只访问声明的官方数据源；
- [x] 高风险 Finding 未处置时总状态不得为 passed。

## 验证证据

- 真实在线命令：`.venv/Scripts/python.exe apps/api/scripts/build_supply_chain_evidence.py --output-dir artifacts/supply-chain-evidence --run-id windows-20260831-release-4 --online --python-executable .venv/Scripts/python.exe --pip-audit-python <isolated-pip-audit-python> --cargo-tool <cargo> --cargo-audit-tool <cargo-audit>`
- 真实结果：`status=findings`；npm 140 个组件、Python runtime closure 42 个组件均完成扫描且 0 个产品 Finding；Cargo 549 个组件发现 18 个 pending RustSec Finding（17 个 unmaintained、1 个 `glib 0.18.5` unsound）；没有 accepted/allowlisted 决定。
- 数据源与工具：npm 10.8.2、pip-audit 2.10.1、cargo-audit 0.22.2；RustSec `last-updated=2026-08-29T08:11:09+02:00`。
- 完整性：`checksums.txt` 全部复算一致；输出无仓库/用户绝对路径和 Secret。前两次 RustSec 网络查询失败均保留为 `incomplete`，未冒充无漏洞。
- 自动回归：全量 Python 855 passed、10 skipped；Playwright 36 passed；根 typecheck/build、compileall、pip check、Rust fmt/check 与 10 个 lib tests 均通过；官方 npm audit 为 0。
- 人工步骤：无

## 实施记录

- 根 `package-lock.json` 与 Desktop `Cargo.lock` 是 lockfile；Python 只登记目标环境中与当前 `pyproject.toml` runtime requirements 匹配的 resolved closure，并明确 `lockfile=false`，不会把宽版本约束冒充 lockfile；
- cargo-audit、npm 和 pip-audit 使用隔离临时 Home/cache；Cargo metadata 只对当前 lockfile 使用 `--locked --offline`。网络扫描可继承标准 proxy routing，但不继承 Provider Credential 或用户 Cargo credentials/config；
- npm 依赖已将 Vite 升至 6.4.3，当前官方 npm audit 为 0；
- Python 22 个许可证表达式仍是 unknown，Cargo 有 7 个 weak-copyleft，均保持 `reviewRequired=true`；
- RustSec 18 项仍待人工影响评估。GTK3/glib 项来自当前 Tauri Linux 传递依赖，不能为追求全绿而静默忽略或做不兼容替换；
- 漏洞扫描是时间点事实，完成 F-056 代表证据链完成，不代表依赖永久安全或 Finding 已处置。
