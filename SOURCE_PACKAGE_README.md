# 知盾 AgentAudit 源码包

- 发布版本：`v0.1.3`
- 源码文件：`AgentAudit-0.1.3-source-20260928.zip`
- 来源：Git tag `v0.1.3` 指向的已提交 Git tree；不包含工作树中的临时文件。
- 署名团队：鉴权未来（GitHub：`mingx2915-lab`）。详见 `AUTHORS.md` 与 `AUTHENTICITY.md`。
- 当前 GPG 发布密钥：`AUTHENTICITY-public-key.asc`，指纹 `AB62 DBAA C751 F68C C34B 8411 CFA7 99F4 18EF F202`。
- 历史 `v0.1.2` 密钥保存在 `AUTHENTICITY-public-key-20260927.asc`。
- 本版本有团队署名注释的入口文件：API `main.py`、Web `main.ts`、Tauri `main.rs`。

本源码 ZIP 不含 `.git` 历史、虚拟环境、`node_modules`、构建缓存、模型缓存或发布二进制。安装包作为 Release 独立资产提供。固定 BGE 模型按 `apps/desktop/scripts/prepare_embedding_model.py` 提供的流程准备；Ollama 和企业 AI Runtime 不随包提供。

仓库未附 `LICENSE`，本源码包不授予一般复用、修改或再发布许可。Release 提供签名的校验清单；按 `AUTHENTICITY.md` 中的步骤先核对完整公钥指纹，再验证签名和文件哈希。若 GitHub 尚未标记新公钥，离线验签可确认签名与该公钥匹配，但身份归属仍需单独核对该指纹。
