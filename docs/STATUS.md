# 当前状态

> 本文件是上下文恢复的第一入口。每次新会话或上下文压缩后，必须先读取本文件及其指定的功能文档。

## 项目阶段

- 状态：M6 本地双平台产品化进行中
- 当前里程碑：M6 本地双平台产品化
- 当前活动功能：无；F-066 权限修正已完成，F-065/F-063 外部 GUI 验收待补
- 当前功能文档：`docs/features/F-066-linux-private-history.md`
- 2026-09-18 安装包交付：当前工作树已生成 Windows NSIS、Linux `.deb`/AppImage，交付目录 `artifacts/deliverables/AgentAudit-0.1.2-installers-20260918/`。Windows 新 EXE 两轮启停、一次崩溃恢复及冻结 API 七项只读检查通过；WSL2 Debian 12 原生构建及 artifact 检查 22/22，通过非默认 pointer 与两次真实 GTK 文件选择。全端 typecheck、Windows Python 891 passed/7 skipped、Linux Python 895 passed/3 skipped。仅修正验证脚本/测试的过时前提，未改业务实现；真实模型固定验收仍为历史 22/24。干净 Windows、独立 Linux 桌面、企业 Gateway 与完整安装窗口视觉验收仍未被本轮替代，F-063 保持 In Progress。下载按来源实测并选路，代理原选择已恢复，详见交付目录 `下载测速.md`。
- 2026-09-09：用户优先要求的 F-064 权限拦截执行结果已完成。固定 Case/Plan 被拒绝时返回结构化结果和 Trace，界面显示中文拦截说明与此前风险。891 Python、2 项定向 E2E、全端 typecheck 通过；真实 qwen3:8b Case 返回 200/blocked、11 步 Trace、1 项资源越权。试用后端已重启；F-063 安装验收仍待完成，历史 Benchmark 22/24 结论未变。详见 `docs/features/F-064-blocked-execution-results.md`。
- 2026-09-09 试用反馈：设置页补回常驻“模型连接”入口；已连接摘要可进入“更改连接”。Web typecheck 和真实本机模型发现界面验证通过，当前连接未变更，备份见 `output/model-entry-20260909/`。
- 2026-09-09 试用反馈：修复“确认使用”后沿用旧滚动位置的问题，保存后定位下一步按钮；两条路径定向 E2E 2/2 与 Web typecheck 通过。用户试用服务继续运行，备份/证据在 `output/provider-scroll-20260909/`。
- 2026-09-09 功能巡检：887 Python + 58 E2E + 2 稳定性检查通过；真实 qwen3:8b 四类扫描与 Replay 全通过，但固定验收仅 22/24 匹配（Owner 文档用例追加工具调用被拒绝，CI Gate failed）。导入、契约编辑、备份恢复、诊断、历史/导出和重启读回已复核。详见 `docs/FUNCTIONAL_AUDIT_2026-09-09.md`；未改业务逻辑，安装窗口验收仍未完成。
- 长期主控规格：`docs/M6_LOCAL_DUAL_PLATFORM_PRODUCT_PLAN.md`；F-026 历史规格保留为 `docs/M6_SMALL_BUSINESS_DESKTOP_PLAN.md`，M5/M4 基线继续保留
- 软件工程质量评估：`docs/SOFTWARE_ENGINEERING_QUALITY_ASSESSMENT.md`；用于恢复稳定性、可用性、发布与维护性判断，不代表新功能已启动
- 下一候选功能：无；继续已授权的外部安装验收，不自动扩展 Parking Lot
- 当前下一步：交付 Linux 0.1.2-2 权限修正包，等待独立 Linux 桌面实装及 GUI 回归；F-065/F-063 原有外部验收继续待补，不以包内 Sidecar 冒烟替代。
- 阻塞项：无本地实现阻塞。Windows/Linux matrix 尚未远程运行；三项目标环境均为 `not_verified`。Python license review 已闭合；18 个 RustSec Finding 仍是已分析、已分配但尚未完成上游迁移的维护债务

## 当前功能进展

- 2026-09-18 F-066 已完成：history 0700，SQLite 主库/现存辅助文件及诊断日志 0600；旧 Workspace 打开时修正，数据保留。Windows 894 passed/18 skipped，Linux 907 passed/5 skipped；nobody 正负控制及实际新包断网空缓存 BGE 六项通过。Linux .deb Debian 修订号递增为 0.1.2-2，交付 artifacts/deliverables/AgentAudit-0.1.2-2-linux-f066-20260918/。Windows 安装包与 AppImage 未重建，独立 GUI 验收未被替代。
- 2026-09-18 用户提供新版 Linux 外部实装回归：离线 BGE、Health 实际端口、绑定失败状态、SIGTERM、中文/空格路径和 GET 冒烟通过；发现历史 SQLite 0644 可被其他用户读取。F-066 按此报告修正主库、辅助文件和日志权限；F-065 独立 GUI 验收保持待补，缺 WebKitGTK 的容器未算应用故障或 GUI 通过。

- 2026-09-18 F-065：模型随包及启动状态三项实现已修正；新版交付 artifacts/deliverables/AgentAudit-0.1.2-installers-f065-20260918/，详见当前功能文档中的通过证据与未闭合 Windows 桌面验证问题。

- 用户优先授权 F-065：修复独立 Linux 检查暴露的模型资源和启动状态问题，F-063 安装窗口验收暂挂起，未宣告完成。

- 2026-09-18 页面试用修正：历史复测卡片统一浅色背景，Before/After 使用白色，提示和状态保留原有语义色，编号及配置文字加深，并允许长编号在窄屏换行。仅 styles.css 样式变更；Web typecheck/build、真实 E2E 服务下 Scan→Replay→保存→重开主链路通过，桌面/移动端复核工件与回退备份在 output/history-colors-20260918/。现有视频仍保留旧录屏，安装包未重新构建。F-063 整体保持 In Progress。

- 2026-09-09 权限摘要布局：角色宽屏三列、规则双列，名称/编号/属性成组，窄屏单列；12/12 回归及 typecheck/build 通过，回退点 output/contract-layout-20260909/。

- 2026-09-09：次级页补少量图形，设置页头权限计划 SVG、扫描流程四图标；12/12 定向 E2E、typecheck/build 与实屏复核通过。回退点 output/frontend-accents-20260909/。

- 2026-09-09 后续工作区密度精修：保留首页，收紧设置/扫描/证据页头、目录、空态及查询卡片留白，仅增加细线强调；typecheck/build、58/58 E2E 和实屏复核通过。回退点 output/frontend-density-20260909/。

- 2026-09-09：按用户选择改用生成的权限边界主图，配套技术插图、入口图标及卡片材质精修完成；typecheck/build、17/17 关键 E2E 通过，Browser/IAB 已复核。独立回退点 output/frontend-art-20260909/；既有安装窗口验收边界不变。

- 2026-09-08 美术增强：用户认可布局后，补充原创 SVG 主视觉及三张技术说明图；typecheck/build 和 17/17 定向 E2E 通过，独立回退点 output/frontend-art-20260908/。当前网页采用自行绘制版本，生图仅留作比较。

- 2026-09-08 F-063 完整前端预览已交付：首用重点、技术说明、设置/证据目录、结果阅读路线和连接/资料说明已统一；Web typecheck/build、定向 15/15 和全量 58/58 E2E 通过，Browser/IAB 已复核。回退入口 output/frontend-review-20260908-150140/rollback.ps1（默认只检查，-Apply 恢复本轮）。当前预览使用确定性测试后端，未重建安装包、未进行陌生用户计时验收；下一步由用户评价视觉，并继续既有安装窗口复核。

- 2026-09-08 F-063 比赛入口与计划卡片试改：首次入口突出权限风险与执行证据，新增 Security Contract / Trace / Replay 通俗说明，计划卡片执行按钮独立置底；Web typecheck/build 与相关 16/16 E2E 通过，浏览器预览已恢复。待用户评价本轮视觉效果；未重建安装包，陌生用户计时验证仍未进行。

- F-063 源码实现与浏览器验收已收口：恢复浅色网络氛围、双路径首用节奏、navy 品牌锚点和深色证据舞台；四工作区导航按最新实屏反馈收为一个大矩形容器加内部竖向分隔；首次入口、Finding、攻击链、Replay 与六个次级组件统一可读层级，未修改 API、Contracts 或安全判定；
- F-063 第二、三轮 Skill 视觉巡检与三个 Luna Max 分区迭代已收口：1024×768 CTA 完整可见，390×844 标题无孤字且字号控件达到 44×44px；592×844 四工作区仍保持同一紧凑矩形轨道，手动查询输入与回答区密度更平衡；Provider Readiness 图片增加纵向展示空间；攻击链、Finding、Replay、Trace 与 Provider 折叠/证据操作均达到至少 44px 点击高度并具备明确展开反馈；
- F-063 当前验证为 Web typecheck、production build、关键视觉回归 30/30 与全量 56/56 Playwright、592×844/1024×768/1440×900/390×844 Browser/IAB、Windows Sidecar/Tauri release/NSIS 重建和 Desktop artifact smoke 10/10 通过；新安装包 SHA-256 为 `4103AF44F246609D83947A09F39455856F6C9679567EC0AD33DAE64D91BE1D20`。因真实安装窗口的资源、缩放和关键流程视觉复核尚未完成，继续保持 `In Progress`；
- F-063 最新界面反馈已收口：固定 Case 的“预期风险类型 / 资源授权绕过”改为同一行、跨卡对齐的珊瑚风险信息栏；四个可执行计划拆成有间距的 2×2 独立卡片，同排等高、操作区贴底，左侧卡片区与右侧详情区底边对齐，390px 下收为无横向溢出的单列；仅将 `Expected categories` 改为中文标签，未改业务数据或请求行为；
- F-063 全站折叠与排版复核已收口：Plan“技术详情”默认折叠；Finding、Trace、历史快照、Replay 和 Acceptance 的折叠入口统一为至少 44px、14px 正文和同构 SVG 箭头；UI 字体栈优先中文系统字体，代码/原始 JSON 独立使用 13px 等宽字体；390×844 的 Scan、Replay、长 ID 和操作区均无横向溢出，未修改 API、Contracts 或安全判定；
- F-063 设置页区块节奏按最新实屏反馈微调：可执行测试计划与手动查询/Agent 回答之间增加 16px 垂直留白，避免两排白色容器边框贴合；大字窄屏实测间距为 16px、无横向溢出，定向 E2E 与 Web typecheck 通过；

- F-062 已完成：应用壳、首次入口、核心验收、攻击链、Finding、Replay、Provider、资料与验收证据统一为真白/冷灰编辑式企业工作台；去除整页固定网络背景、玻璃卡片和过度等宽小字，默认层优先中文业务结论；
- F-062 按用户要求保留原有业务插图，但只在首次入口、攻击链、Critical Finding、Replay、Provider Readiness 与验收证据的真实内容/状态区域局部使用，不再压字或充当整页背景；
- F-062 未修改 API、Contracts、Provider、Security Contract、Scan、Trace、Finding 或 Replay 判定；typecheck、production build、48/48 Playwright、diff-check 以及 1600×1000/390×844 Browser/IAB 实屏与 console 检查通过；
- F-061 已完成：真实 Scan 结果态继续保留攻击链背景；单 Plan 使用静态确认、多 Plan 才显示真实选择器；状态转换改为浅色证据行；mutation reason 改为正文级“本轮攻击策略”并只按真实 Attempt status 使用风险/通过色；固定 Case 操作同行贴底；Guided、攻击链报告、验收页和 Desktop 启动失败页的同类字号、信息层级与恢复说明同步收口；
- F-061 未修改 API、DTO、Provider、Security Contract、Scan/Finding/Trace/Replay 判定或调用次数；定向 4/4 与全量 45/45 Playwright、887 Python passed（10 skip）、typecheck、production build、Desktop artifact smoke 10/10 和 diff-check 通过；当前 Windows 安装包 SHA-256 为 `9922BFEE1D5C1954BC25E243678165FBFDB7A02003345C3E6B5FF8B7522BBEF7`；
- F-060 已完成：首次入口改为合成演示/自有助手互斥路径，未选择时不展开完整业务模块；选择只改变本地状态，不触发 Discovery、Readiness、Import、Scan、Replay 或模型请求；未配置 Provider 作为待完成任务呈现；
- F-060 已将 Provider、资料、Guided Scan 和 Replay 问题统一为“阶段、原因、影响、恢复动作、折叠技术详情”，后端按异常类型、HTTP 状态和执行阶段生成中文诊断，不解析异常字符串、不回显 Secret、不新增 retry/fallback/局域网扫描；
- F-060 核心路径默认使用业务结论与中文过程，Rule、Trace、Runtime、原始 JSON 和 operation ID 保持可访问；问题卡关键标签和操作不低于 14px；1440/1920 大字攻击链证据面板复核为整行展开且不拉伸六节点；
- F-060 回归为 886 Python passed（10 个环境/显式 skip）、41 Playwright passed；typecheck、production build、compileall、pip check 与 diff-check 通过；当前源码重新冻结 Sidecar 并构建 Windows Desktop release/NSIS，指定新 EXE 的真实启动 smoke 为 10 passed；统一交付安装包 SHA-256 为 `CBE73D97E47B3CED65BAD63EE15821F07BBA0352363C7265624E2BAAB9B988E6`；真实企业 Gateway、真实 Ollama 现场网络和未读源码陌生用户证据均未被自动化冒充；

- F-059 已完成：攻击链默认层改为确定性中文业务过程，宽屏六节点等高；节点证据移到下方独立全宽面板，展开不再拉长任何卡片，原始 JSON 保持二次折叠；Finding 编号使用独立高对比信息块，完整 Trace 改为中文事件标题、正文级字号和分块关键字段；不修改任何审计判定；
- F-059 回归为 880 Python passed（10 个环境/显式 skip）、37 Playwright passed；typecheck、production build、compileall、pip check 与 diff-check 通过；
- F-059 当轮 Windows `0.1.2` 安装包曾按该轮源码重建；当前交付制品已由后续 F-060 重建并以上述 F-060 SHA-256 为准；
- F-058 已完成：Ollama 未运行、HTTP 异常和无效响应改为可行动的中文诊断，不再暴露底层异常名；模型选择动态展示实际安装项且不限定 `qwen3:8b`，仍以四项 Readiness 为准；顶部字号栏滚动常驻；Desktop 关闭时先隐藏窗口、后台精确清理 owned Sidecar。新 `0.1.2` lifecycle 总退出耗时 1,297 ms，旧基线为 6,359 ms，端口均释放且无孤儿进程；
- F-058 回归为 880 Python passed（10 个环境/显式 skip）、37 Playwright passed、11 Rust library tests passed；typecheck、production build、compileall、pip check、cargo check 与源码 rustfmt 通过；
- F-057 本地实现已收口：新增 Windows 2022 / Ubuntu 24.04 核心质量矩阵；release-4 的 40 项供应链 review 已逐项核对，release-5 当前 register 收敛为 19 项；三项目标环境任务单和可复跑性能观测已建立；文档时间线已按 F-055 后续事实同步；
- F-057 当前 Windows 回归为 880 Python passed（10 个环境/显式 skip）、36 Playwright passed、10 Rust library tests passed；typecheck、production build、compileall、pip check、cargo check、源码 rustfmt 与 diff-check 通过；
- F-057 release-5 在线证据把 Python unknown license 从 22 降到 1：scanner 新增目标解释器标准 distribution metadata 读取；新冻结 Sidecar 递归携带 Runtime metadata，原 22 个包均逐项确认 METADATA 和 LICENSE 文件存在；最后一项 `py_rust_stemmers` 以本机 canonical MIT LICENSE 与冻结包含性完成显式人工 review；
- F-057 当前 register 与 release-5 精确对应 19 项：18 个 RustSec Finding 继续 `in_progress`，唯一 metadata-unknown license 为 `fixed`，没有 accepted/allowlisted。glib 受影响 `VariantStrIter` API 经仓库与完整 resolved Cargo source 搜索为不可达；其余依赖路径均已按 Cargo tree 登记；
- F-057 新增 1,000 轮显式容量 soak：1000/1000 workflow/Finding/Replay 通过，p50 27.44 ms、p95 30.97 ms、History 1000、Provider calls 6000，总时长约 28.04 秒；这不是小时级或真实模型长期稳定性结论；
- F-057 保持 External Acceptance Pending：新 CI matrix 尚未取得 GitHub Windows/Linux 首轮实际结果；干净 Windows、Debian 非默认 pointer 和真实企业 Gateway 均保持 `not_verified`；
- F-056 已完成：新增 Python/npm/Cargo 三生态 SBOM、许可证与漏洞证据 runner/CLI、同源 JSON/Markdown/checksums、显式离线/在线边界、风险决定约束、官方 CI workflow，并接入 F-051 release evidence；
- F-056 真实在线证据 `windows-20260831-release-4` 为 `status=findings`：npm 140、Python runtime 42 个组件均 0 产品 Finding；Cargo 549 个组件有 18 个 pending RustSec Finding（17 unmaintained、1 glib unsound），没有接受或 allowlist。Python 22 个 unknown license、Cargo 7 个 weak-copyleft 保持人工 review；checksum 复算一致且无绝对路径/Secret；
- F-056 最终回归为 855 Python passed（10 个环境/显式 skip）、36 Playwright passed、10 Rust lib tests passed；root typecheck/build、compileall、pip check、Rust fmt/check、npm audit 和 diff-check 通过；
- P0–P5 自动化交付计划已全部完成：F-051 发布证据、F-052 Windows 生命周期、F-053 诊断包、F-054 数据迁移、F-055 Linux artifact smoke、F-056 供应链证据均已有实现与对应证据；
- P0–P5 闭环审计后的当前回归为 867 Python passed（10 个环境/显式 skip）、36 Playwright passed、10 Rust lib tests passed；root typecheck/build、compileall、pip check、Rust fmt/check、Linux shell syntax 与 diff-check 通过；

- F-055 已完成：真实 Debian VM 对版本 `0.1.2` 的新 AppImage、`.deb` 和 Sidecar 完成完整构建与 artifact smoke，机器证据为 22 passed、0 failed、0 not_verified；XDG、Secret Service、loopback health、legacy migration、进程/端口清理、probe不入发布包和真实 GTK 文件选择均由脚本入口验证；
- F-055 三份工件 SHA-256：AppImage `d34966c316446254b9b024483e22511a6974636112a0d4d1d2b45331e777b89f`，`.deb` `8d450813214777f6d477ef96f3d581c7f564c3ad97dc7c7406860259d83d5208`，Sidecar `d52654a48c7ad9258375ecfe4e88d80f44810ddcc5c9b691196034d1e356e66d`；两种桌面工件均通过官方 WebDriver 标准点击与精确标题 GTK chooser 返回隔离合成文件，且未隐式触发 Preview、Commit 或 Scan；
- r27 的 active Workspace pointer 检查使用默认目标，不能证明 Desktop 确实消费 pointer。当前脚本已改为非默认 `workspaces/pointer-target` 并以 default manifest 为负控制，单元测试覆盖写入、读取、默认目标和越界拒绝；真实 Debian 工件尚未用增强脚本重跑，因此不把旧 r27 summary 写成该新增断言已通过；

- F-054 已完成：Workspace manifest 使用独立 `schemaVersion=2`，SQLite 使用 `user_version=2` 与顺序 migration；Audit/Acceptance 共用一个 Schema Manager，升级前保存完整 ZIP，失败回滚且高版本/损坏/缺结构输入不写入；
- F-054 已接入 Sidecar 首启、Restore 后准备和 active Workspace 切换前准备；Windows active pointer 使用原子替换。全量 786 Python passed（9 skip）、36 Playwright passed、9 Rust passed，typecheck/build/check/fmt/diff-check 通过；
- 真实 0.1.2 frozen Sidecar 与 Windows Desktop 均完成 legacy v1→v2 迁移、旧 marker/业务文件保留、health ready、迁移备份与精确进程树清理；Desktop EXE/NSIS 已从当前源码独立重建；

- F-053 已完成：新增本地有界结构化日志、operation ID、诊断 Preview/Export、严格允许清单 ZIP 和 Desktop 原生保存；不上传、不收集 SQLite/业务正文/Provider 配置，不声称自动根因；
- F-053 真实冻结验收修复了 FastAPI lifespan 与 Sidecar status hook 不兼容的启动缺陷；修复后 Sidecar 和 Windows Desktop release 均 ready，诊断 ZIP 成员/版本/operation ID 验证通过，树清理残留为 0；
- F-053 回归证据：769 Python passed（9 个显式/环境 skip）、36 Playwright passed、8 Rust passed、typecheck/build/check/fmt/diff-check 通过；Windows 0.1.1 release EXE 与 NSIS 已从当前源码重建；
- F-052 已完成：当前 Windows 真实执行 `0.1.0` baseline 安装、隔离 Desktop 启停、资料写入、受控 Scan/Replay、`0.1.1` 原位升级和卸载，`13/13 checks passed`；升级前后 Workspace/SQLite 快照一致，卸载后程序/Registry/进程消失且隔离用户数据保留；
- F-051 已完成：一键编排 Python、typecheck/build、专用截图、Cargo 与真实 Desktop smoke，生成同源 JSON/Markdown/HTML、相对路径 manifest 和 SHA-256；当前 Windows 实际证据包 14/14 passed，19 个 checksum 重算一致，无用户主目录/常见 Secret 命中且无进程残留；
- P0–P5 已由 F-051 至 F-056 全部完成，依次覆盖发布证据、Windows 生命周期、脱敏诊断、数据迁移、Linux 真实发布与供应链证据；

- F-050 已完成：企业连接新增 Anthropic / Claude Gateway 与固定 `agent_audit_adapter.v1` 两种协议；检查只访问用户明确输入的单一 origin，拒绝 Redirect，运行时固定一个协议且无 retry/fallback；
- F-050 将 Anthropic Messages 的 system、tool_use/tool_result、usage 与企业 Adapter 的 strict camelCase Canonical DTO 接入同一四项 Readiness、保存和 Scan Runtime；Secret 只进入瞬时请求与 Desktop OS Credential Store；
- F-050 验收为 692 个 Python tests（6 个环境/显式条件 skip）、31 个 Playwright E2E、根 typecheck/build、Rust check/4 tests/rustfmt、重新构建的 Sidecar、Windows release EXE/NSIS 与真实 Desktop artifact smoke 全部通过；受控 Test-only transport 不冒充真实企业网关，真实 Claude Gateway/企业 Bridge 与 Linux 仍是外部验收债务；

- F-049 已完成：验收证据页首改为“全链路验收主张 + 固定运行范围”两栏结构，右侧用 24 Case、5 Gate、2 Differential、1 Replay 与原创证据汇聚背景解释一次运行的固定范围；
- F-049 将零历史大空卡收为紧凑结果入口，主按钮成为唯一实心操作；1920/390 Acceptance E2E、623 Python tests、28 Playwright、typecheck/build 与 Desktop artifact smoke 全部通过；

- F-048 已完成：核心首页建立明确主次层级；资料导入收起态改为窄于核心验收的轻量准备栏，去除重阴影和重复计数，使用次级描边操作；展开后恢复完整工作宽度；
- F-048 保持核心验收为唯一深色主舞台和实心主操作；1920 大字层级、390 窄屏、资料 Preview/Commit、623 Python tests、28 Playwright、typecheck/build 与 Desktop artifact smoke 全部通过；

- F-047 已完成：顶部新增“标准 / 大字”显示切换，新用户默认 120% 大字并在本机记住选择；显示切换不触发 API、Provider、Scan 或 Replay；
- F-047 将桌面默认窗口调整为 1600×1000；1920 大字内容区实际约 1728px、无横向溢出，390 窄屏不应用桌面整体缩放；623 Python tests、27 Playwright、typecheck/build、Desktop artifact smoke 与 diff-check 全部通过；

- F-046 已完成：四个顶层任务统一为“核心验收、设置与计划、扫描记录、验收证据”；无 Scan/History 时只显示一个代码原生 Scan→Attempt→Trace→Finding 任务空态，不再并排展示两块空卡或通用箱子插图；
- F-046 的“去核心验收”和“刷新记录”均保持显式、只读边界；真实 Scan/History 过程与恢复能力不变；1440/1920/390 实屏复核、623 Python tests、25 Playwright、typecheck/build/diff-check 全部通过；

- F-045 已完成：建立 Display/H1/H2/H3/Body/Label/Code Typography 与 1440/1920 宽屏 tokens；把三列 Plan 长卡改为列表+详情，四个执行按钮固定在同一操作列，Replay 只在同 Plan 的真实 Scan 完成后出现；
- F-045 身份差分已重排为紧凑任务/Profile/主操作/摘要工作区；1440/1920/2560/390 E2E、实际 1920/390 浏览器复核、623 Python tests、23 Playwright、typecheck/build/diff-check 全部通过；未修改 API、Contracts、Finding/Replay 判定或模型调用；

- F-044 已完成：Guided Audit 运行态替换为 1600×615 本地原创 Evidence Pulse 视觉；多条蓝色数据流经过四个异构审计阶段，单个明亮琥珀扫描脉冲不中断蓝色主流；
- F-044 只在真实 Scan loading 期间显示，请求结束即移除；3.8 秒低频扫光在 reduced-motion 下停用，不使用红/绿、不表示 passed/failed；
- F-044 验收为 Web typecheck/build、Guided 核心路径 4 个 E2E、390×844、快速双击单请求、Finding/Replay 与 502 恢复回归全部通过；

- F-043 已完成：真实 Critical Finding 卡片顶部新增 1600×640、48.9 KB 本地原创 Evidence Focus 视觉；多束 Evidence Blue Trace 汇聚到单一 Risk Coral 证据断点，图片无文字和常见安全品牌符号；
- F-043 只在 `severity=critical` 时显示，Severity、Finding ID、标题、摘要、Rule ID 与 Evidence sequence 继续来自真实 DTO；High、passed、未运行或无 Finding 状态不显示图片；
- F-043 验收为 Web typecheck/build、Guided 核心路径 4 个 E2E、390×844 无页面溢出及 diff check 通过；未修改 Finding 判定、Trace、Replay 或 API；

- F-042 已完成：用户确认的透明本地工作台背景以 1440×880、45 KB WebP 接入桌面 Splash 右侧；左侧 Logo、产品名、真实状态、错误与本地处理边界保持代码原生且清晰可读；
- F-042 的 starting 使用一次性轻量归位，ready 按真实状态提亮，failed/stopped 冻结降亮，`prefers-reduced-motion` 下无背景移动；未延长启动时间、未修改 Sidecar 生命周期或伪造进度；
- F-042 验收为品牌/启动集成测试 5 passed、新 release Desktop artifact smoke 10 passed、根 typecheck、Contracts/Web build、Tauri release EXE 与 NSIS rebuild、720×440 人工视觉复核及 diff check 通过；

- F-041 已完成：Replay 结果区使用同构 Before/After 两张本地原创图；Before 为亮蓝来流在前段被紧凑红色梗阻并带左向粒子拖尾，下游保留低能冷蓝轮廓，After 在相同构图中恢复蓝绿畅通；
- F-041 仅当真实 Replay status=`passed` 时播放一次 820ms 交叉淡入，failed 保持 Before，`prefers-reduced-motion` 下直接显示实际终态；未修改 Replay、Profile、Finding 或修复参考；
- F-041 验收为 Web typecheck/build、Guided 核心路径 4 个 E2E 与 diff check 通过；

- F-040 已完成：用户确认的原创蓝色数据流图以本地 1600×640 WebP 接入未运行六节点预览；默认背景强度约 58%，节点使用半透明深蓝玻璃层，真实 Trace 出现后移除；
- F-040 未修改 Plan、Scan、Trace、Finding 或 Replay；Web typecheck/build、Guided 核心路径 4 个 E2E 与 diff check 通过；

- F-039 已完成：Guided Audit 未运行空态撤下无法独立解释的 Contract Trace Path 插画，改为代码原生 Actor → Source → Resource → Authorization → Tool → Sink 六节点预览；Actor、Rule、Target 来自当前 Plan，其余节点明确等待 Trace；
- F-039 未修改 Scan、Finding、Replay 或 API；核心链路 4 个 browser E2E、1440×1000/390×844、Web typecheck/build 与 diff check 通过；

- F-038 已完成：候选 Provider Readiness 新增同构红色阻塞/绿色畅通两张本地原创状态图；未检查、检查中和未就绪保持红色，仅真实 `ready` 切换为绿色；不改 API、探针、保存条件或 Finding；
- F-038 状态切换采用短交叉淡入、一次性绿色光扫与检查中蓝色扫光，`prefers-reduced-motion` 下停用；1440×1000/390×844 响应式 E2E、Web typecheck/build 和实际浏览器复核通过；

- F-037 已完成：Replay 区统一改为“修复参考与模拟复测”，提示在执行前即可见，并随历史、Acceptance Run、攻击链页面和 Markdown 报告保留；明确不修改企业系统、不构成根因结论、不替代人工核查和变更审批；
- F-037 未改变 Replay 的执行事实：After 仍只使用内置 `secure` Profile，active Contract、企业配置、Finding 和 API DTO 均不修改；全量 622 Python tests、20 Playwright E2E、Web typecheck/build 通过；
- F-036 已完成当前声明范围：隔离 deterministic 核心工作流 100/100，当前 Windows Desktop artifact 启停 30/30、crash-recovery 1/1，最终端口占用与孤儿进程均为 0；
- F-036 默认全量为 622 个 Python tests（6 个环境/显式长测 skip）和 20 个 Playwright E2E；50 项混合导入、Provider 单次失败、SQLite 锁/损坏恢复、1,000 条 History/Acceptance 与快速双击单请求均已覆盖；
- F-036 只修复测试实际暴露的问题：DeepSeek Adapter 显式 `max_retries=0`，Desktop Runner 修正中文路径编码、窗口关闭等待和精确孤儿进程采样；未增加攻击类型、重试、fallback 或生产生命周期推测性重写；
- F-036 的 100 轮结果来自明确标记的 Test Provider/TF-IDF，真实模型、Linux、DPI/键盘和外部用户证据未被冒充为完成；
- F-035 已转为 External Validation Pending：软件实现和当前机自动/人工验收不变，未读源码用户五分钟任务和真实 Tauri 原生错误路径仍未完成，不勾选；

- F-035 已开始：把“连接 AI、添加 AI 会检索的业务文档、确认权限、运行首次 Guided Audit”收敛成普通用户可完成的向导；
- F-035 明确承认现有 Test-only 文件选择 E2E 不能替代真实系统对话框验收，并将 PDF/DOCX、本机错误透传、批量权限与五分钟首次任务列为完成条件；
- F-035 软件实现与自动验收已收口：双入口向导、PDF/DOCX/TXT/MD 本机解析、批量权限与例外项、逐项诊断、真实 Contract-derived Plan 和 Guided Audit 已接通；全量 588 Python tests、19 Playwright E2E、4 Rust native tests、typecheck/build/check/fmt/diff-check 通过；
- 最新 Sidecar 已在隔离目录真实启动、创建 Workspace 并返回 health ready；真实 Windows 系统文件夹选择器已完成 PDF/DOCX/TXT/MD 四格式人工导入，结果为成功 4 项、跳过 0 项、Retriever 7→11，并派生 4 条真实 Plan；F-035 仍因未读源码用户五分钟任务和真实原生错误路径证据未完成而不勾选；

- F-034 已完成：模型连接页收敛为“选择方式 → 地址/模型 → 四项 Readiness → 确认使用”的连续任务面；本机 Ollama 使用 3/6/3 三栏，企业地址继续保留 URL、认证、Bearer 和手填模型；
- 候选 Readiness 未检查时即显示目标连通性、目标工具调用、攻击连通性和严格 JSON 四项状态，完整 Provider facts、诊断与 Plan compatibility 仍可展开；
- F-034 验收为 567 个 Python tests（2 个条件 artifact skip）、16 个 Playwright E2E、根 typecheck、Web build 与 diff check 通过；1440px 与 390px 人工复核无横向溢出，未调用真实模型；

- F-033 已完成：新增 Contract Trace Path、Evidence Pulse、Before / After Split 三张原创 3:2 状态插画；分别用于核心验收空态、Scan 运行态和 Replay 结果，不替代真实 Trace/Finding；
- 三张本地 WebP 合计约 69 KB，无运行时联网依赖；1440×1000 和 390×844 人工复核无关键路径裁切或横向溢出；
- F-033 验收为 567 个 Python tests（2 个条件 artifact skip）、13 个 Playwright E2E、根 typecheck、Web build 与 diff check 通过；

- F-032 已完成：主工作区改为浅色工作台，深海军蓝只保留品牌锚点；Action Blue、Risk Coral、Evidence Teal 与 Warning Amber 分别承担操作、风险、通过和提醒语义；
- 首页、模型连接、资料导入、核心攻击链、Finding、Replay 和高级证据区已统一视觉层级并精简可见文案；Runtime、Trace、Rule ID 与错误诊断仍可访问；
- 图片只完成 Contract Trace Path、Evidence Pulse、Before/After Split 三张原创资产 brief，本轮未调用图像生成服务、未新增图片；
- F-032 验收为 567 个 Python tests（2 个条件 artifact skip）、13 个 Playwright E2E、根 typecheck、Web build 与 diff check 通过；1440×1000 和 390×844 实际截图已人工复核；
- F-031 的共享代码与 Windows 验收已经收尾，真实 Linux Secret Service/artifact 仍作为外部验收债务保留，不与 F-032 并行改业务实现；
- F-031 已完成“自动查找本机”和“连接企业地址”两条普通用户路径；企业地址只访问用户明确填写的单一 origin，以 OpenAI-compatible `/v1/models` + 四项 Readiness 验收，不猜厂商、不扫网、不 retry/fallback；
- Bearer 只通过 Desktop 系统 Credential Store 进入 Sidecar 当前进程，Provider JSON、Workspace、SQLite、History、Trace、日志和 API 响应不保存 Secret；新地址不复用旧连接的进程密钥；
- 当前自动基线为 567 个 Python tests（2 个条件 artifact skip）与 13 个 Playwright E2E；项目内 Rust `cargo check`、Windows release/NSIS 重建与指定 EXE smoke 通过；
- 本机 Ollama `qwen3:8b` 真实候选 Readiness 为 READY，Target connectivity/Tool Calling 与 Attack connectivity/strict JSON 四项 passed，4/4 Plan compatible；未保存配置、未调用 DeepSeek。

## 最近完成

> 以下 F-001 至 F-012 是 v0.5 基础闭环历史，不等于 v1.0 竞赛强化版完成。

- 完成 F-062：用编辑式企业工作台统一应用壳、首次入口、核心验收及次级工作区；保留原有业务插图并改为局部、状态驱动使用；
- F-062 验收：48 个 Playwright、typecheck、production build、1600×1000/390×844 Browser/IAB 实屏、console 与 diff-check 全部通过；未修改后端安全执行语义。

- 完成 F-061：按用户实屏反馈修复结果态背景、单项假选择器、深灰状态条、微小策略原因、Case 操作错位，并同步收口报告、验收与启动失败页的同类表达问题；
- F-061 验收：45 个 Playwright、887 个 Python tests（10 skip）、typecheck、production build 和指定 release EXE smoke 全部通过；Windows `0.1.2` NSIS 已重建。

- 完成 F-039：删除核心验收未运行状态的纯装饰插画，改用可读的六节点代码原生流程；计划值与尚未发生的 Trace 事实明确区分；
- F-039 验收：Guided 核心路径 4 个 browser E2E、Web typecheck/build 与 diff check 通过；390×844 无横向溢出，运行中和真实 Trace 结果保持不变。

- 完成 F-038：把同一构图的红色阻塞与绿色畅通状态图接入候选 Provider Readiness，并以真实 `ready` 状态驱动短切换动效；图片不替代四项探针或错误诊断；
- F-038 验收：Provider Setup 5 个 browser E2E、Web typecheck/build 与 diff check 通过，1440×1000 和 390×844 无横向溢出；本地 Test-only Provider 实际复核红→绿切换，不调用真实模型。

- 完成 F-034：模型连接页去除独立大号空态与重复下一步说明，本机 Ollama、企业 OpenAI-compatible 地址、四项候选 Readiness 和确认栏形成连续任务面；完整 Readiness 证据模式保持不变；
- F-034 验收：567 tests、16 browser E2E、根 typecheck、Web production build 与 diff check 通过；使用 Test-only Provider 实际复核 1440px/390px、本机/企业、stale/Cancel/Bearer 边界，无真实模型请求。

- 完成 F-033：把三张原创审计状态插画接入空态、运行态和 Replay 结果；图片不含文字或常见安全品牌图形，只辅助真实 Contract/Trace 证据；
- F-033 验收：567 tests、13 browser E2E、根 typecheck、Web production build 与 diff check 通过；1440×1000 和 390×844 实际复核无横向溢出。

- 完成 F-032：把连续深色页面重构为浅色工作台，顶部与攻击链保留深色证据锚点；主操作、Finding、Replay/通过和警告分别使用蓝、珊瑚、薄荷与琥珀语义色，首页和高级区删除重复的 AI 式说明；
- F-032 验收：567 tests、13 browser E2E、根 typecheck、Web production build 与 diff check 通过；使用 Test-only Provider 实际复核 Guided Scan → Critical Finding → same-plan Replay 和 390×844，无真实模型请求、无图片生成。

- F-029 当前机实现完成、双平台外部验收待补：新增完整 Workspace ZIP、纯 Preview、copy-as-new Restore、原生保存/选择/切换、active Workspace 相对指针、Windows/Linux 平台配置、Linux Sidecar/build 脚本和 Linux 进程树清理；
- F-029 当时的当前机验收为 512 个 Python tests（2 个真实 artifact 条件不满足时诚实 skip）与 12 个 Playwright E2E；后续 F-055 已补齐真实 Linux `.deb`/AppImage、active Workspace pointer、系统文件选择和 Windows→Linux→Windows Archive 生产格式往返。F-029 仍不勾选仅因另一台干净 Windows 属独立外部验收债务，不再归因于 Linux 未验证。

- 完成 F-028：新增 Tauri 原生多文件/文件夹选择、UTF-8 `.txt`/`.md` 逐项读取、显式企业权限元数据确认、纯 Contract 授权 Preview、Workspace 原子快照追加和共享 Retriever 热替换；空闲页面保持紧凑状态卡，导入资料无需重启即可进入真实 Authorization Trace；
- F-028 验收：487 个 Python tests（另 1 个无 Desktop artifact 时诚实 skip）与 10 个 Playwright E2E、compileall、pip check、typecheck、production build、rustfmt、离线 cargo check 和 diff check 通过；隔离 Workspace 实证允许角色进入 `model_context`、拒绝角色只有 denied Authorization，不调用真实模型、不写用户真实配置。

- 完成 F-027：新增固定 loopback Ollama 自动发现、单地址手动连接、候选四项 Provider Readiness、非 Secret 配置持久化和即时 Runtime 切换；已配置后首页收敛为紧凑状态卡，Windows/Linux 共用 DTO 与 UI，Linux 设置遵守 XDG config/data/state；
- F-027 验收：461 个 Python tests（另 1 个无 Desktop artifact 时诚实 skip）与 8 个 Playwright E2E、compileall、pip check、typecheck、production build 和 diff check 通过；本地 `qwen3:8b` 真实发现与四项 Readiness 均 passed，4/4 Plan compatible，未写真实用户配置、未调用 DeepSeek。

- F-026 当前机实现完成、外部验收待补：新增 Tauri v2 Windows 独立窗口、PyInstaller FastAPI Sidecar、loopback 生命周期、`%LOCALAPPDATA%\AgentAudit` 路径边界和可移动 manifest Workspace；所有生产 Loader、History 与 Benchmark 由同一 Workspace 注入，Web 开发入口继续保留；
- F-026 当前机验收：416 个 Python 测试（另 1 个无 artifact 时诚实 skip）与 7 个 Playwright E2E、compileall、pip check、typecheck、production build、cargo check、rustfmt 和 diff check 通过；真实 Sidecar ready/health/seed/tree-kill、release Desktop 启动/关闭及 NSIS 当前用户安装/启动/卸载通过。尚缺另一台干净 Windows 复核，所以不勾选 F-026；用户已把该项转为外部验收债务并授权 F-027 继续。
- 比赛事实材料已同步到当前桌面版：申报底稿、答辩问答、五分钟桌面 Runbook、最终验收、评委快速指南与视觉资产统一使用 24 Case、416 tests、7 E2E、SQLite/Acceptance Run、Ollama 22/24 Gate failed 和 F-026 未完成边界；概念图明确不替代真实运行证据。

- 完成 F-025：把 Provider Readiness、6 Query Retrieval、两个多身份 Differential、固定 24 Case CI Gate、固定 Source→Sink Scan 与同 Plan Replay 统一为显式 Acceptance Run；完整成功后追加到同一 SQLite 文件的独立历史表，支持回看、与上一 Run 对比及 JSON/Markdown 下载；
- F-025 验收：373 tests + 7 browser E2E、compileall、pip check、typecheck、production build 与 diff check 通过；本地 Ollama `qwen3:8b` 真实 Run 已持久化，Readiness ready、22/24 matched、Recall 1、FPR 0、Policy Accuracy 0.95、Replay 1，Gate 如实 failed，未重试、fallback、改 Ground Truth 或调用 DeepSeek。

- 完成 F-024：新增仅运行仓库固定 24 Case 的 `agent-audit ci-gate`，HTTP Benchmark 与 CLI 复用同一真实 Runtime，固定五项确定性 Gate、0/1/2 退出码与 JSON/Markdown 工件；
- F-024 验收：335 tests + 5 browser E2E、compileall、pip check、typecheck、production build 与 diff check 通过；本地 Ollama `qwen3:8b` 真实运行为 22/24 matched、Recall 1、FPR 0、Policy Accuracy 0.95、Replay 1，CLI 如实返回 1 并保留两个实际阻断状态差异，未重试、fallback 或调用 DeepSeek。

- 完成 F-023：新增 Visual/Advanced 共用 Security Contract Draft、无副作用 Preview API、稳定结构化字段 Diff 和真实 Planner Plan Impact；保存前可见影响，取消不写入，保存后刷新 active Contract/Plans；
- F-023 验收：310 tests + 5 browser E2E、compileall、pip check、typecheck、production build 与 diff check 通过；浏览器实测关闭资源 owner-match 后显示 1 个字段变化并将 Plans 从 4 减为 3，保存只 PUT 一次，未调用任何模型。

- 完成 F-022：新增显式 Provider Readiness API 与核心页兼容矩阵，Target/Attack 分角色执行 connectivity、native Tool Calling、strict JSON 四项单次探针；失败不重试、不 fallback、不写 Finding、不阻止 Scan；
- F-022 验收：300 tests + 3 browser E2E、compileall、pip check、typecheck、production build 与 diff check 通过；本地 Ollama `qwen3:8b` 四项真实探针均 passed，两个角色 READY、四类 active Plan 均 compatible，未调用 DeepSeek。

- 完成 F-021：默认 Web 首页收敛为 Source→Sink 引导式核心验收，真实 Trace 投影 Actor→Source→Resource→Authorization→Tool→Sink；Finding 与同 Plan Replay Before/After 进入同一主线，完整证据和高级能力降为可展开/次级工作区；
- F-021 验收：260 tests + 3 browser E2E、compileall、pip check、typecheck、production build 与 diff check 通过；本地 Ollama `qwen3:8b` 实跑得到 1 Attempt、18 Trace、1 Critical Finding，Replay 达成 before failed/after blocked+passed，未调用 DeepSeek。

- 完成 F-013：新增长期主控规格 `docs/COMPETITION_V1_DEVELOPMENT.md`，依据正式评分表重启 M4；明确 v0.5/v1.0 边界、F-014 至 F-020 顺序、三代理职责、上下文恢复协议和软件/材料边界；
- F-013 验收：三个 Luna Max 只读审计完成；106 tests passed，必读文件、diff check 与本次 diff 密钥模式扫描通过；未启动服务或发送真实模型请求。
- 完成 F-014：新增最多三轮的显式 Red-Team Scan 状态机、严格 JSON LLM 变体生成器、独立 Attack Provider 注入、`POST /api/scans` 与 Web Live Audit；Actor/Rule/Target 固定来自 current Contract-derived Plan，Finding 仍由既有 Contract Checker 决定；
- F-014 验收：134 tests passed，Python compileall、前端 typecheck/build 与 diff check 通过；本地 Ollama `qwen3:8b` 受控 Scan 返回 1 Attempt、12 Trace、2 Findings 与 `finding_detected`，未启动监听服务或调用 DeepSeek。
- 完成 F-015：Security Contract 新增 Tool 数量/审批约束和 SinkRule，新增纯内存 Mock Mail/Customer Export，Contract-derived Planner、Assistant Trace、Checker、Replay、Report、F-014 Scan 和 Web 全部接通 `source_sink` 与 `tool_record_limit` 两类计划；
- F-015 验收：170 tests passed，Python compileall、前端 typecheck/build 与 diff check 通过；本地 Ollama `qwen3:8b` 原生 Tool Call 完成 18 条 Source→Sink Trace 和 critical Finding，同 Plan Replay 达成 before failed/after blocked+passed，未启动监听服务或调用 DeepSeek。
- 完成 F-016：新增两个从合成资产派生的标准化多身份任务、Expected→Actual 差分 Runner、GET/POST API 和 Web 矩阵；Expected 来自 active Contract，Actual 只投影每个 Actor 的真实 model_context/Tool Result Trace；
- F-016 验收：193 tests passed，Python compileall、前端 typecheck/build 与 diff check 通过；本地 Ollama `qwen3:8b` 对同一五身份财务任务完成漏洞/secure 对比，漏洞 Profile mismatch=3 且有实际 Finding，secure Profile mismatch=0，未启动监听服务或调用 DeepSeek。
- 完成 F-017：本地 FastEmbed `BAAI/bge-small-zh-v1.5` 成为共享 Permission-aware RAG 主路径，新增 Retriever Protocol、Embedding Trace、固定 Retrieval Evaluation API 和 Web 对比区；TF-IDF 仅保留为显式对照/测试注入且不自动 fallback；
- F-017 验收：217 tests passed，Python compileall、前端 typecheck/build、pip check 与 diff check 通过；真实 BGE 固定 6 Query Top-1 6/6、MRR 1.0，TF-IDF 为 1/6、0.555556；同一财务候选在 secure visitor/finance 和 vulnerable visitor 下分别证明 denied 不进 context、allowed 进 context、denied 仍进 context 并产生 Finding，未启动监听服务或调用 DeepSeek。
- 完成 F-018：固定 Ground Truth 扩为 24 个非填充 Case，四类各 6；真实 Runner 复用 Assistant/Plan/Replay，新增 completed/blocked、Attempts、Provider calls、ASR、Mean Attempts、Category Counts 与 Token usage，并在 Web 展示逐 Case 证据；
- F-018 验收：242 tests passed，Python compileall、前端 typecheck/build、pip check 与 diff check 通过；默认本地 BGE + 受控 Provider 实跑 24/24 matched，11 安全控制、9 违规、4 Replay，38 次 Provider 调用，usage 380/190/570，成本保持未知；结果仅适用于固定合成靶场，未启动监听服务或调用 DeepSeek/Ollama。
- 完成 F-019：新增标准库 SQLite Run History，完整保存 Scan/Attempt/Trace/Finding 与 Contract/Plan/Profile/Runtime 不可变 Snapshot；历史 Replay 使用保存时的 Plan/Contract 真实执行并只追加；Web 收敛为 Audit Setup、Live Audit、Findings & Replay 三个工作区；
- F-019 验收：260 tests passed，Python compileall、前端 typecheck/build、pip check 与 diff check 通过；默认本地 BGE + 临时 SQLite + 受控 Provider 完成 Scan→重建 App→恢复→Replay→再次恢复，得到 1 Finding 与 before failed/after passed，未启动监听服务或调用 DeepSeek/Ollama。
- 完成 F-020：新增真实 Playwright 浏览器 E2E、Test-only Provider/临时 SQLite 启动支持、关键工作区可访问选择器和 Runtime 防重复刷新；覆盖成功持久化主链、390×844 窄屏与 Provider 502 可读错误；
- F-020 验收：当前工作区 260 tests + 3 browser E2E 通过，compileall、pip check、typecheck、production build、diff check 通过；主代理人工浏览器复核无非预期 console/network 错误；干净 Git 副本全新安装后复现通过；真实 production API/Web 启动 smoke 返回默认 DeepSeek Adapter + BGE Runtime 元数据且端口正常释放，未发送模型请求。

- 建立仓库级主约束与上下文恢复规则；
- 建立单仓库前后端目录；
- 建立功能文档、任务板、验收和命名体系；
- 明确不采用文档哈希、复杂硬门和过度防御实现。
- 依据新项目框架，将产品正式收敛为“知盾 AgentAudit”；
- 固定 Security Contract、双攻击者、全过程 Trace 与修复 Replay 四条主张；
- 锁定真实全栈技术基线，同时保留模型供应商可替换性。
- 固定开发总指令、DeepSeek Flash 非思考配置和“启动前必须告知”边界；
- 完成 F-003：Vue 页面、FastAPI API、TF-IDF Retriever、Mock Customer Tool、DeepSeek Provider Adapter 与结构化 Trace 已形成最小真实垂直切片；
- F-003 验收：后端 16 tests passed，Python compileall、前端 typecheck/build 通过；未启动服务或发送真实模型请求。
- 完成 F-004：Security Contract Schema、默认合成配置、确定性 Resource/Tool Evaluator、GET/PUT API 与 JSON 编辑区已形成真实垂直切片；
- F-004 验收：后端 28 tests passed，Python compileall、前端 typecheck/build 通过；授权单一来源检查通过，仍未启动服务或发送真实模型请求。
- 完成 F-005：请求级 TraceCollector、文档来源属性、Source→model_context→actor_response Sink 事实链与前端可读摘要已形成真实垂直切片；
- F-005 验收：后端 33 tests passed，Python compileall、前端 typecheck/build 通过；事实采集与规则判断职责分离，仍未启动服务或发送真实模型请求。
- 完成 F-006：确定性 ContractChecker、可选 Semantic Review、评估 API 与前端 Finding 区已形成 Hybrid Judge 垂直切片；
- F-006 验收：后端 50 tests passed，Python compileall、前端 typecheck/build 通过；语义解释不能覆盖确定性 Finding，仍未启动服务或发送真实模型请求。
- 完成 F-007：两个仓库内固定 Outside-in/Inside-out Case、显式 secure/observe-only Target Profile、真实 Case Executor/API 与前端执行区已形成双攻击者垂直切片；
- F-007 验收：后端 61 tests passed，Python compileall、前端 typecheck/build 通过；Finding 来自实际 Trace，期望类别不参与判定，仍未启动服务或发送真实模型请求。
- 完成 F-008：active Security Contract 与合成资产可确定性派生资源/工具 owner-scope 计划，并复用既有 Executor、Target Agent、Trace 与 Checker 执行；
- F-008 验收：后端 76 tests passed，Python compileall、前端 typecheck/build 通过；Contract 更新会刷新计划，工具 Finding 来自实际 Tool Call，仍未启动服务或发送真实模型请求。
- 完成 F-009：同一 Contract-derived Plan 可在漏洞/secure Profile 下真实执行两次，生成确定性修复建议、before/after Trace 与 Replay 结论；
- F-009 验收：后端 84 tests passed，Python compileall、前端 typecheck/build 通过；资源与工具 Replay 均证明 failed→passed，工具阻断不伪造 QueryResult，仍未启动服务或发送真实模型请求。
- 完成 F-010：固定 6 Case Ground Truth 可复用 secure Assistant、Plan Executor 与 Replay Executor 顺序执行，并从实际结果计算五项质量证据；
- F-010 验收：后端 97 tests passed，Python compileall、前端 typecheck/build 通过；默认离线指标为 Recall 1、FPR 0、Policy Accuracy 1、Replay Pass 1，仍未启动服务或发送真实模型请求。
- 完成 F-011：已完成 Replay 可纯生成结构化 AttackChainReport 与 Markdown，前端以独立双栏组件展示 before/after Trace、Finding、Rule 和修复项，并由用户手动下载；
- F-011 验收：后端 103 tests passed，Python compileall、前端 typecheck/build 通过；报告不重新判定、不增加 Provider 调用、不访问 active Contract，仍未启动服务或发送真实模型请求。
- 完成 F-012：README、双服务 Compose、五分钟 Runbook、申报事实底稿、模拟答辩与最终验收材料已完成；显式 Ollama Provider/运行时选择器保持 DeepSeek 默认值、不自动回退并关闭 thinking；
- F-012 自动验收：106 tests passed / collected，Python compileall、ASGI import、pip check、前端 typecheck/build 与 diff check 通过；
- F-012 现场验收：本地 `qwen3:8b` 正常查询、资源 Replay、报告下载、Tool Calling 和 6 Case Benchmark 均通过；6/6 matched，Recall 1、FPR 0、Policy Accuracy 1、Replay Pass Rate 1，Scan Time 15,870.48 ms；API/Web 已停止，未调用 DeepSeek。

## 下一步

M5 的 F-021 至 F-025 已全部完成；M6 当前代码主线已推进到 F-063，P0–P5 自动化交付计划全部完成，下一步不自动扩功能：

1. 默认先检查 Guided Source→Sink 攻击链、Critical Finding 与同 Plan Replay；
2. 在高级验收区检查 Provider Readiness、Contract Preview、固定 Gate 和 Acceptance Run 历史/对比/下载；
3. 现场模型显式使用本地 Ollama；不自动回退或消耗 DeepSeek API；
4. 本地 `qwen3:8b` 的 22/24 是已知真实模型边界，不通过重试或改 Ground Truth 隐藏；
5. F-059、F-060、F-061 已完成人话攻击链、Finding/Trace 技术分层、首次使用、问题恢复、结果态视觉与操作对齐收口；后续视觉修改必须继续服务真实 Contract → Trace → Finding → Replay 主线；
6. M6 后续方向见 `docs/M6_LOCAL_DUAL_PLATFORM_PRODUCT_PLAN.md`；当前按用户决定跳过 F-035 陌生用户任务，优先取得 Windows/Linux quality matrix 首轮结果，并执行 `docs/TARGET_ENVIRONMENT_ACCEPTANCE.md` 的三项外部验收；未获得新决定前不制作 PPT/视频，也不启动 Parking Lot 扩展。

## 状态更新规则

- 开始功能：填写“当前活动功能”和对应文档路径；
- 中断功能：准确记录已完成、未完成和下一条操作；
- 完成功能：清空当前活动功能，更新最近完成与下一候选功能；
- 发现阻塞：写明事实、影响和需要的决定，不用模糊描述代替。
