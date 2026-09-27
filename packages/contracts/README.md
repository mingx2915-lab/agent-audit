# Shared Contracts

存放前后端真正共享的 API Schema、DTO 和稳定枚举。

这里只维护跨端契约，不建立通用工具箱，也不把后端领域逻辑复制到前端。

F-003 至 F-006 已形成查询、Security Contract、Source/Sink Trace 和 Finding 契约。F-007 增加固定双攻击者 Case，F-008 增加 Contract-derived Plan，F-009 增加修复 Replay，F-010 增加 Ground Truth 指标。F-011 增加以现有 ReplayResult 为事实输入的 `AttackChainReport`；不包含持久化历史或服务端文件类型。
