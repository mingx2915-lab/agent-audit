# Acceptance Artifacts

存放人可读、可复现的验收证据。当前交付索引：

- `DEMO_RUNBOOK.md`：五分钟演示步骤、时间预算与透明备份策略；
- `JUDGE_QUICK_START.md`：评委三分钟理解、核心证据检查和可信边界；
- `SUBMISSION_BRIEF.md`：申报事实底稿与评分证据映射；
- `DEFENSE_QA.md`：模拟答辩问题、事实回答与边界；
- `FINAL_ACCEPTANCE.md`：当前自动验收、Desktop/安装器证据与未完成边界；
- `V1_SOFTWARE_ACCEPTANCE.md`：M4 F-013 至 F-020 的历史软件验收基线。

自动生成的大体积输出放入 `generated/`，该目录默认不提交 Git。验收不依赖工件哈希。

比赛封面、技术架构和 Replay 流程示意位于 `artifacts/visuals/`。其中的概念图不能代替软件实际运行产生的 Trace、Finding、Replay、Acceptance Run 或目标机安装证据。
