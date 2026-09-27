# F-054 Workspace 与 SQLite 版本迁移

- 状态：Completed
- 所属里程碑：M6
- 负责人：主代理
- 相关决定：执行 `docs/NEXT_AUTOMATED_DELIVERY_PLAN.md` 的 P3

## 用户价值

用户升级知盾 AgentAudit 时，旧 Workspace 中的业务文档、Security Contract、Scan/Replay History 和 Acceptance Run 应按明确版本顺序升级。迁移失败时必须保留可恢复的旧数据，不得把部分写入冒充为成功。

## 公共约定

- Workspace manifest 新增独立 `schemaVersion`；保留现有 `version` 字段的旧语义，不用它代替 Schema 版本；
- 旧 manifest 不含 `schemaVersion` 时只按明确 legacy v1 处理；高于当前支持版本的 Workspace 直接拒绝，不降级打开；
- SQLite 使用 `PRAGMA user_version` 与 Workspace manifest 版本分开管理；无版本的历史库按可验证表结构进入顺序 migration；
- Scan History 和 Acceptance History 共用一个 SQLite 迁移入口，不得由两个 Repository 各自无版本建表；
- 迁移只在打开用户明确选择的 Workspace 时运行，不扫描其他目录，不启动 Provider 或外部网络请求。

## 迁移与备份边界

- 任何写入前生成一个可恢复的完整 Workspace 备份，包含 manifest、文档、Contract、Cases、History 和 exports；
- SQLite 备份使用 SQLite online backup，不把 `-wal`/`-shm` 作为普通文件复制；
- migration 必须按版本逐步执行，每步在事务或同等原子边界内完成；缺失中间版本时不跨级；
- 迁移失败后，active Workspace、manifest、SQLite rows 和 active-workspace 指针保持旧状态；备份路径可诊断，但不写入用户主目录或 Secret；
- 同一已迁移 Workspace 重新打开幂等，不重复备份、不重写业务文件、不修改 History 行。

## 范围

- Workspace manifest schema version 与 legacy v1 识别；
- SQLite `user_version` 与顺序 migration registry；
- 迁移前 Workspace ZIP 备份、失败保留与幂等打开；
- Desktop Sidecar 首启、Workspace Restore 和 active Workspace 切换的同一迁移入口；
- 真实 legacy fixture 中的 Contract、文档、Scan/Replay、Acceptance 与指针验证。

## 非目标

- 不引入 ORM、PostgreSQL、云迁移服务、分布式锁或自动上传；
- 不修改 Security Contract 判定、Finding、Replay 或 Provider 请求语义；
- 不尝试猜测未知高版本 Schema，不在损坏数据上做降级修复；
- 不为本功能新增一套远程更新系统或复杂 UI。

## 实施任务

- [x] 冻结 Workspace/SQLite 当前版本、legacy 识别和 migration registry；
- [x] 实现迁移前可恢复备份和失败不破坏旧数据；
- [x] 让 Audit/Acceptance Repository 共用一个 SQLite schema manager；
- [x] 接入 Sidecar 首启、Restore 与 active Workspace 切换；
- [x] 增加 legacy fixture、顺序/幂等/高版本/损坏/事务失败测试；
- [x] 使用旧版本真实 Workspace 执行升级并复核全部数据。

## 验收标准

- [x] 新 Workspace 写入当前 `schemaVersion`，新 SQLite 写入当前 `user_version`；
- [x] legacy Workspace 与无版本 SQLite 按每个中间版本顺序迁移；
- [x] 升级后 Contract、文档、Scan/Replay、Acceptance 与 active 指针均可读；
- [x] 故障注入时 manifest 与业务 JSON 保持原字节，SQLite 保持完整性、旧行和逻辑 Schema 一致，并保留可恢复备份；
- [x] 重复打开不重复迁移或备份，高版本和损坏输入给出可诊断错误；
- [x] 迁移过程无外网请求、无 Secret/绝对开发机路径进入 Workspace 或 History；
- [x] 定向测试、全量 Python/E2E、typecheck/build、Rust check/test/fmt 与 diff-check 通过。

## 验证证据

- Python：全量 `pytest -q` 为 786 passed、9 skipped、1 个既有 Starlette warning；F-054 最终定向 50 passed；
- 浏览器：全量 Playwright 36 passed；Workspace 保存→Preview→Restore→迁移准备→激活走真实业务 API；
- 前端：根 `npm run typecheck` 与 `npm run build` 通过；
- Rust：`cargo test --lib` 9 passed，`cargo check` 与 `cargo fmt -- --check` 通过；Windows active pointer 使用原子替换；
- 冻结 Sidecar：SHA-256 `7D5494CC5F92BAABCB6B2D50F35F2E3E5D44DEF9A991D3D6F145850D654F3DB8`；真实启动 legacy v1 Workspace 后 health ready，manifest/SQLite 均为 v2，旧 marker 保留，迁移 ZIP 为 9 个成员且无 WAL/SHM，清理后残留进程 0；
- Windows Desktop 0.1.2：EXE SHA-256 `65B9DF2A59DB41DFD82313EB30E22425A134840534371C0F593383944A558B03`，NSIS SHA-256 `C9857EEC4EB5F5F56D1EAEA891E05D94BB8965D4955BF47AF35D6D9762EE2D7B`；隔离 legacy Workspace 启动迁移、health、备份和旧数据均通过，关闭后 Desktop/Sidecar 残留均为 0；
- `compileall` 与 `git diff --check` 通过；验证只使用 `.tools` 下隔离目录，未读取或修改用户真实 AgentAudit 数据。
