# F-017 Permission-aware Embedding RAG

- 状态：Done
- 所属里程碑：M4
- 负责人：主代理监督；Backend/Frontend/Test Luna Max 按互斥范围实现
- 相关决定：D-002、D-003、D-004、D-007、D-009、D-019、D-024

## 用户价值

让企业 AI 开发和安全人员既能用中文语义检索验证知识助手的真实 RAG 能力，又能逐步复核“候选文档 → 相似度 → Contract 授权 → model_context”的权限边界。该功能用本地轻量 Embedding 提升技术实现深度，同时保持业务安全结论可解释、可回归。

## 范围

- 使用已通过固定 Query 对比的本地 CPU `BAAI/bge-small-zh-v1.5` 和 FastEmbed ONNX Adapter；
- 新增进程内 `EmbeddingRetriever`，索引已有合成文档的 `title + content`，用 cosine similarity 排序并保持稳定 tie-break；
- 将 Embedding Retriever 作为正常运行主路径，TF-IDF 只保留为显式对照实现和测试注入，不做运行时自动 fallback；
- `AssistantService`、Attack/Scan/Replay/Benchmark/Differential 全部复用同一 Retriever Protocol，不建立第二条 RAG 业务链；
- Retrieval Trace 明确记录 engine、model、dimensions、候选 documentId/score，随后仍由既有 ContractEvaluator 记录逐文档授权，并由实际 `model_context` Sink 表达最终进入结果；
- 新增固定 6 Query 的 `POST /api/retrieval-evaluations`，同时真实执行 TF-IDF 与 Embedding，返回各自排名和 Top-1/MRR；expected 只用于比较，不参与检索排序；
- Web 增加独立的 Retrieval Evaluation 区域，显式运行并展示 Query、expected document、两种排名、Top-1 与选型依据；
- 使用 Test Double 做离线自动验收，再用真实本地 Embedding 模型执行固定 Query 和 permission-aware Assistant 查询。

## 非目标

- 不引入 PostgreSQL、pgvector、Qdrant 服务、Elasticsearch 或云 Embedding API；
- 不做混合检索、Reranker、Chunking 平台、文档上传、任意语料索引或模型训练；
- 不让 Embedding 相似度决定角色、Owner、Tool 或 Sink 权限；
- 不在模型缺失、下载失败或推理失败时静默切回 TF-IDF；
- 不把固定 Query expected 写入实际检索结果，也不根据 expected 重排；
- 不在 F-017 扩充 24+ Ground Truth、持久化或三工作区；这些分别留给 F-018/F-019。

## 前后端与数据影响

- Web：新增 Retrieval Evaluation 执行与对比结果区；现有 Assistant Trace 继续展示真实 Retrieval/Authorization/Context；
- API：新增 `POST /api/retrieval-evaluations`；`create_app` 支持显式 Retriever/Embedder 测试注入，正常默认使用 Embedding；
- Contracts：新增 Retrieval Engine、Ranked Document、Evaluation Case/Result/Metrics 类型；
- Data/Model：不新增业务数据；新增 `fastembed` 运行依赖，本地下载约 90 MB 的 BGE ONNX 权重到用户缓存，不提交模型文件；
- Tool/LLM：检索对比不调用 Target/Attack LLM，不访问真实外部业务系统。

## API 或交互契约

### Retriever Protocol

```text
engine_id: tfidf | embedding
model_name: string | null
dimensions: number | null
search(query: string, limit: int = 3) -> RetrievedDocument[]
```

- `EmbeddingRetriever` 对文档使用 `title + "\n" + content` 建索引；
- cosine score 按降序排列，同分按 `document.id`；
- Query 为空或不是字符串沿用清晰输入错误；`limit <= 0` 返回空列表；
- Embedder 是模型信任边界：文档/Query 向量数量、维度和有限数值必须与契约一致，否则返回可诊断的 Retriever 错误；
- 生产主路径不捕获错误后改走 TF-IDF。

### Retrieval Trace

现有 `retrieval` 事件至少包含：

```text
query
engineId = embedding
modelName = BAAI/bge-small-zh-v1.5
dimensions = 512
candidates[] = { documentId, score }
documentIds[] / scores[]  # 保留既有兼容字段
```

每个 Candidate 后续仍产生既有 Resource Authorization Trace；最终是否进入上下文只看 `sinkType=model_context` 的 `documentIds`。Similarity 不等于 authorization。

### POST /api/retrieval-evaluations

- 不接收任意 Query 或 expected；固定 Query 由服务端维护；
- 不调用 LLM；同一请求分别运行当前 TF-IDF 与当前 Embedding Retriever；
- 模型初始化或推理不可用返回 503，不返回伪造比较结果。

响应：

```text
id
selectedEngine = embedding
modelName / dimensions / indexedDocumentCount
cases[]:
  caseId / query / expectedDocumentId
  tfidfResults[] / embeddingResults[]
  tfidfExpectedRank / embeddingExpectedRank
metrics:
  caseCount
  tfidfTop1Hits / embeddingTop1Hits
  tfidfMrr / embeddingMrr
```

固定 Query 集在实现前锁定如下，expected 只用于执行后计算排名：

| Case | Query | Expected Document |
|---|---|---|
| semantic_budget_allocation | 各团队明年的钱应该怎么分配？ | `doc_finance_budget_001` |
| semantic_hr_lifecycle | 同事加入或离开单位时要办哪些手续？ | `doc_hr_handbook_001` |
| semantic_product_capability | 这家厂商能为其他公司解决什么问题？ | `doc_product_overview_001` |
| semantic_demo_boundary | 测试时怎样避免影响生产系统？ | `doc_demo_usage_guide_001` |
| customer_service_expiry | 远山的这笔服务单什么时候到期？ | `doc_customer_contract_002` |
| semantic_vendor_bypass | 哪项外来材料藏着诱导助手违规的内容？ | `doc_external_vendor_prompt_001` |

模型锁定门：Embedding Top-1 不低于 5/6，且 Top-1 与 MRR 均优于当前 TF-IDF；未通过则保持本功能未完成并重新评估候选模型，不改 expected。真实预对比结果为 Embedding Top-1 6/6、MRR 1.0，TF-IDF Top-1 1/6、MRR 0.555556，因此锁定 BGE。

## 实施任务

- [x] ~~主代理下载候选模型并完成固定 6 Query 的真实 TF-IDF/Embedding 对比，锁定模型与基线~~
- [x] ~~主代理同步 Retriever/Evaluation 跨端契约和依赖声明~~
- [x] ~~Backend Luna Max 实现 Retriever Protocol、FastEmbed Adapter、Embedding 主路径、Trace 和 Evaluation API~~
- [x] ~~Frontend Luna Max 实现 Retrieval Evaluation 执行、指标与逐 Query 排名展示~~
- [x] ~~Test Luna Max 实现向量排序/错误边界、权限过滤 Trace、API 与全量回归测试~~
- [x] ~~主代理审查不含自动 fallback、expected 重排或向量权限判断~~
- [x] ~~运行 pytest、compileall、typecheck、build、pip check 与 diff check~~
- [x] ~~使用真实本地 BGE 模型运行固定对比和 visitor/finance Assistant 权限链~~
- [x] ~~更新状态、架构、决定、README、任务板并提交 Git~~

## 验收标准

- [x] 固定 6 Query 的真实对比满足 Embedding Top-1 ≥ 5/6，且 Top-1/MRR 均优于当前 TF-IDF；
- [x] 正常 `create_app` 和所有 Assistant/Attack/Scan/Replay/Benchmark/Differential 路径使用同一 Embedding Retriever 实例；
- [x] Retrieval Trace 同时保留 engine/model/dimensions、候选 ID/score、逐文档 Authorization 和最终 model_context；
- [x] visitor 的财务语义 Query 可检索财务文档但 secure Profile 不让它进入 context，finance/admin 可进入；
- [x] 漏洞 Profile 仍可用同一候选产生实际 authorization bypass Finding，说明检索事实与权限判定没有混合；
- [x] 模型/推理错误可诊断且不自动切回 TF-IDF；
- [x] Evaluation expected 只计算 rank/metrics，篡改显示字段或最终模型回答不能改变真实排名；
- [x] Web 清晰展示两种检索的逐 Query Top 结果、expected rank、Top-1 和 MRR，不把固定小样本外推为生产准确率；
- [x] 现有 F-003–F-016 行为和测试不回归，目标环境依赖与首次模型下载说明准确。

## 验证证据

- 测试命令：`.venv\Scripts\python.exe -m pytest -q`、`.venv\Scripts\python.exe -m compileall -q apps/api/src tests`、`npm run typecheck`、`npm run build`、`.venv\Scripts\python.exe -m pip check`、`git diff --check`。
- 结果：217 tests passed；Python compileall、前端 typecheck/build、pip check 与 diff check 通过。Vite 只有既有的大 chunk 提示，pytest 只有既有的 Starlette/httpx deprecation warning。
- 真实模型对比：官方 Qdrant ONNX 权重 94,781,076 bytes，SHA-256 `1294ea4b6331115a353d81f96b85e8c8d7fdcc284453d5b2fab5b016230aad38` 校验通过；锁定 Query 集上 Embedding Top-1 6/6、MRR 1.0，TF-IDF Top-1 1/6、MRR 0.555556。
- 人工步骤：通过进程内 FastAPI 真实加载本地 BGE 并执行 Retrieval Evaluation，响应为 200；再以真实 BGE 和不调用 Tool 的确定性 Target Provider 对同一财务语义 Query 执行 visitor/finance/vulnerable 三条 Assistant 链。三者 Top Candidate 均为 `doc_finance_budget_001`：secure visitor 为 denied 且不进入 context，secure finance 为 allowed 且进入 context，vulnerable visitor 为 denied 但进入 context 并产生 `resource_authorization_bypass` Finding。

## 实施记录

- 模型来源：BAAI 原始模型为 MIT 许可、24M 参数；FastEmbed 官方支持列表提供 512 维、约 0.09 GB 的中文 ONNX 版本。
- 模型和依赖下载是用户已授权的 F-017 实施步骤；模型文件仅进入用户缓存，不进入 Git。
- TF-IDF 保留用于明确对照和测试注入，不是生产失败时的降级路径。
- 首版含明显原词的 Query 使两种检索均为 6/6，不能证明语义检索价值，因此未采用；最终固定集保持业务意图与 expected 文档不变，使用自然语义改写减少标题/正文词面泄漏，并保留一条实体明确的双方共同命中 Case。
- 补充调用本地 Ollama `qwen3:8b` 时，visitor 查询完成，但 finance 查询曾选择与问题无关的 `mock_mail_send` 并被既有 Tool 参数边界拒绝为 422；该偶发 Tool 选择不参与检索指标或权限结论，也未为它增加 Prompt 特判，留待 F-020 稳定性场景统一观察。
