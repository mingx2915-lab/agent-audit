# F-065 离线检索模型与 Sidecar 启动状态修正

- 状态：In Progress
- 所属里程碑：M6
- 负责人：主代理
- 相关决定：无

## 用户价值

保证新机器安装后可离线运行固定 BGE 检索模型，准确显示启动失败原因与实际监听端口，支撑比赛可复现交付。

## 范围

- 发布包携带固定 BGE ONNX 与 tokenizer，冻结运行只加载随包模型。
- 端口绑定失败保留 failed 与原因；Health 返回实际端口。
- 重建 Windows/Linux 安装包并进行空缓存离线推理与生命周期验证。

## 非目标

- 不改变检索算法、安全判定、模型连接方式或视频；不做 BM25 fallback。

## 前后端与数据影响

- Web：纳入已授权的历史复测浅色修正，无新增交互。
- API：固定模型资源选择和 Sidecar 生命周期。
- Contracts：现有 DesktopRuntimeStatus 结构不变。
- Data/Model/Tool：同一 BAAI/bge-small-zh-v1.5，512 维。

## API 或交互契约

记录必要的请求、响应和关键状态，不复制全部实现细节。

## 实施任务

- [x] 固定模型资源准备、随包冻结与离线加载。
- [x] 启动绑定失败和 Health 端口修正；重建双平台安装包。
- [x] Windows 主窗口关闭异常定位：原 runner 错选无标题 WebView HWND，明确主窗口关闭正常。
- [ ] 独立 Linux 使用者完整桌面体验验收（外部验收待补，不是本地实现阻塞）。

## 验收标准

- [x] 空缓存、禁止下载情况下双平台实际冻结程序完成 BGE 检索推理；Windows 真 qwen3:8b 助手查询 200。
- [x] 实际端口冲突保留 failed、原因和非零退出；Health 端口正确。
- [x] 正确定位真实 Windows 主窗口后正常关闭，退出码 0；原多轮 runner 选择窗口缺陷与早期进程观察失败单独保留，不宣称多轮 runner 通过。

## 验证证据

- 测试命令：Windows/Linux pytest tests/unit tests/integration -q；npm run typecheck；F-065 定向测试；f065-frozen-smoke.py；Linux Xvfb Desktop artifact smoke。
- 结果：Windows 894 passed/7 skipped；Linux 898 passed/3 skipped；最新 Linux F-065 22/22 通过；全端 typecheck 通过；双平台实际冻结离线检索、Windows 实际助手查询、端口冲突均通过；Linux 新 deb Desktop 初始化 smoke 1/1。
- 工件：artifacts/deliverables/AgentAudit-0.1.2-installers-f065-20260918/；旧安装包完整保留。

## 实施记录

记录重要偏差、剩余问题和下一步。不要记录逐行编码日志。

## 本轮实际边界

三项源码修正和新版 Windows NSIS/Linux deb/AppImage 已交付。Windows NSIS 使用 Tauri 原生成脚本并以 /INPUTCHARSET UTF8 编译，未修改生成脚本。冻结 Windows 模型资源逐文件与固定清单匹配。并行构建时曾出现一次检索 503，后续独立检索和真实助手查询通过，未证明该次失败根因，记录保留。Windows 桌面 lifecycle 两轮+恢复和独立一轮均未全通过，主要为进程观察失败及 CloseMainWindow 验证失败；各次 Sidecar health/Workspace ready 成功、退出端口释放，但不能冒充完整桌面启停通过。因此 F-065 保持 In Progress，下一步复核该桌面验证异常；独立使用者的 Linux GUI 验收仍需目标机执行。未改变原有 22/24 历史真实模型固定验收结论，没有修改视频。

后续关闭复核：EnumWindows 观察到同一程序 PID 下同时存在真正“知盾 AgentAudit”可见主窗与无标题的可见 WebView 窗口；Get-Process.MainWindowHandle 返回的是无标题窗口。明确选择真实主窗后 WM_CLOSE 正常退出，RC=0。没有修改应用关闭逻辑，原 runner 选择窗口的验证缺陷未冒充通过，原失败工件完整保留。
