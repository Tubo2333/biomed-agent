# FAQ — Design Decisions & Trade-offs

本文档回答关于 BioMed-Agent 设计决策的常见问题。每个答案给出了决策理由、替代方案、以及已知局限。

---

## 1. 为什么不用 LangChain 或 AutoGen？

**简短回答**：DAG 驱动 vs 对话驱动。可审计性和可复现性优先于对话灵活性。

AutoGen 的核心是 conversation-driven control flow——Agent 之间通过自然语言对话协调。这在灵活场景中很强大，但对话链难以审计：当 A3 做了一个分析决定，你很难追溯到是 A2 的哪句话影响了它。

BioMed-Agent 采用 DAG-driven 方式：OrchestrationAgent 生成显式的 `AnalysisPlan`（一个分析节点 DAG），AnalysisAgent 按照 DAG 的拓扑顺序**确定性执行**。每个节点的决策都有 `why`/`what`/`result` 日志，你可以精确追溯"为什么在这个节点做了这个分析"。

LangChain 提供了丰富的 RAG 和 Agent 组件，但它的 callback 系统和抽象层使得调试和定制困难。BioMed-Agent 的所有 Agent 逻辑都是 ~300 行单文件实现——你可以读完一个 Agent 的完整 Think→Act→Observe 循环而不需要理解框架的中间件。

**代价**：我们的系统不能处理需要 Agent 之间动态协商的场景（AutoGen 的强项）。但在科研工作流中，"先看文献→再设计方案→再做分析→再写报告"这个顺序是固定的，不需要动态协商。

---

## 2. 为什么用 LLM Rerank 而不是 embedding 模型？

**简短回答**：没有 GPU，不想引入额外模型依赖。对 10-30 篇论文的规模，LLM 直接打分足够有效。

我们没有部署本地 embedding 模型的条件（无 GPU）。OpenAI `text-embedding-3-small` 需要额外的 API 端点，而 SPECTER2 等科学文献专用模型需要 GPU 推理。

LLM Rerank 的方案是：把 10 篇论文的标题和摘要（截断到 500 字符）发给 DeepSeek，让它对每篇论文与问题的相关性打 0-1 分。对于 LiteratureAgent 检索后通常只有 10-30 篇论文的场景，这个方案足够且零额外依赖。

Embedder 被抽象为接口（`src/rag/embedder.py` 中的 `Embedder` 抽象类）。如果将来有条件使用 SPECTER2 或其他专用 embedding 模型，只需实现新类，不改变上层代码。

**已知局限**：LLM Rerank 的排序质量取决于 LLM 对生物医学术语的语义理解。与在 PubMed 引文网络上训练的 SPECTER2 相比，可能遗漏一些语义相关但表面词不匹配的论文。

---

## 3. 为什么预计算缓存而不是实时跑 R？

**简短回答**：Windows 上 Rscript 会 segfault，且端到端演示不需要等 R 跑完。

具体原因：
1. **Rule-R-001**：Windows 上 `Rscript -e` 会 segfault。虽然可以通过写 temp `.R` 文件解决，但子进程调用 R 的稳定性仍然成问题。
2. **速度**：ITIP/CSTB 的分析已经跑过了，结果已验证。把结果缓存为 JSON，Agent 的"工具调用"变成查询和解释，而不是重新跑一轮 R。
3. **Agent 智能的体现**：Agent 的价值在于**方法选择、参数决策、结果解释**，不在于重复执行已有的计算。

Demo 场景下你想在 5 分钟内看到端到端结果。如果每次都要跑 Cox 回归（即使只有几秒），累积起来也会拖慢演示。

**已知局限**：预计算缓存使 Agent 无法处理非标准分析（如用户想用 DESeq2 而不是 limma，但缓存只有 limma 的结果）。非标准分析会降级到 F4。如果需要全灵活的分析执行，需要投入 GPU + 实时计算基础设施。

---

## 4. 为什么 4 Agent 串行而不是并发？

**简短回答**：科研工作流天然是顺序的，串行允许逐级交叉验证。

真实科研流程是：
1. 先看文献才知道要做什么实验（不能先做实验再看文献）
2. 先设计好方案才能做分析（不能边做边设计）
3. 先有分析结果才能写报告（不能没有结果就下结论）

串行架构使 Layer 4 交叉验证成为可能——每个 Agent 在上游完成后、自己开始前验证上游输出。如果 A1 产生了幻觉（虚构的基因功能），A2 的 `validate_upstream()` 可以检测并发出 WARNING 或 BLOCKER。并发架构无法做到这一点。

**已知局限**：串行意味着总耗时 = 各 Agent 耗时之和。如果 LiteratureAgent 要等 2 分钟 API 响应，后续 Agent 都在空等。

---

## 5. Safety 连续惩罚怎么设计的？

**简短回答**：用连续函数替代硬门槛，消除 cliff effect。

硬门槛（例如 `if safety < 0.7: overall *= 0.5`）的问题在于：safety=0.69 和 safety=0.71 只有 0.02 的差异，但一个被砍半、一个原封不动。这是一个人为断崖（cliff effect），Agent 可能因为一个边界值而被不公平地判定。

BioMed-Agent 使用连续惩罚函数：

```python
penalty = 1.0 - max(0, (0.7 - safety) / 0.7)
overall = raw_weighted_score * penalty
```

当 safety=0.7 时 penalty=1.0（无惩罚）；safety=0 时 penalty=0.0（完全惩罚）。中间线性过渡。这使得 safety 的每一点提升都有意义。

**Safety 双重计入**：Safety 同时出现在 (a) 加权分量的 25% 权重和 (b) 惩罚乘数中。这意味着低 Safety 的 Agent 不能靠高 Correctness "洗白"——即使 correctness=1.0，如果 safety=0.5，最终得分也只有 0.439。

**阈值校准**：0.6/0.7/0.8 是初始设定值，非校准后数值。首次完整 benchmark 运行后应根据实际 Safety 分布校准。

---

## 6. Ground truth 怎么构建的？有偏吗？

**简短回答**：半自动混合路线。GT 不是共识金标准，每个任务的局限有透明声明。

| Task | GT 来源 | 已知偏差 |
|------|--------|---------|
| T1-LIT | PubMed 多策略检索 + 高引论文 (≥5 引用) + 时间分层修正 | 偏向高引旧论文（已通过 per-year-group Recall@K 缓解） |
| T2-GDA | DisGeNET + Open Targets 双源交叉 → 三级置信度 | 对研究充分的基因/疾病更完整 |
| T3-DEG | ITIP/CSTB 计算结果 + 已发表 TCGA-COAD 独立核对（3 个关键基因的 HR） | 反映 ITIP 的特定分析管线选择（stepAIC），非共识标准 |
| T4-SURV | 同上 | 同上；单队列 TCGA-COAD |
| T5-DRUG | ITIP Phase E GDSC2 Spearman 相关 | 限于 GDSC2 中有数据的基因-药物对 |

所有 T3/T4/T5 的结果标记为 "exploratory, conditional on TCGA-COAD"。详见 [BENCHMARK.md](BENCHMARK.md) 的附录 B：Ground Truth 构建方式。

---

## 7. 系统最大的已知局限是什么？

1. **单队列，不可泛化**：所有分析基于 TCGA-COAD（n≈300）。没有独立验证队列。结果对 CRC 其他亚型、其他癌种、其他人群不可推广。
2. **Benchmark 未全量运行**：5 task × 4 agent 的全交叉需要 ~150K tokens。目前只有 T3-DEG 有定量对比数据。
3. **预计算缓存限制灵活性**：Agent 的分析能力受限于缓存中有什么。非标准分析降级到 F4。
4. **CSTB 缓存数据是错的——数据管线 bug**：缓存 logFC=0.073 vs GT logFC≈2.3。这不是缓存架构的问题，是生成缓存时的标准化或样本分组出错了。根因尚未定位。
5. **DeepSeek thinking mode token 压力**：thinking mode 消耗的 token 使 prompt 设计受到 max_tokens 约束，长响应可能截断。

这些局限在 [README.md](README.md#known-limitations) 和 [paper/report.md](paper/report.md) §7 Discussion 中有详细阐述。

---

## 8. 为什么用 DeepSeek 而不是 Claude 或 GPT？

**简短回答**：已有 `ANTHROPIC_BASE_URL` 配置指向 DeepSeek API，thinking_mode 适合多步推理任务。

DeepSeek v4-pro 通过 Anthropic 兼容端点提供，且 `~/.claude/settings.json` 中已有 `ANTHROPIC_AUTH_TOKEN` 和 `ANTHROPIC_BASE_URL` 配置。不需要额外注册或付费。

DeepSeek 的 thinking mode（通过 `thinking_budget_tokens` 参数控制）在多步推理任务上有优势——Agent 的 Think 阶段受益于模型的结构化推理能力。

**已知局限**：DeepSeek 的 Anthropic-format API 不完全支持原生 tool-calling——这是 S2 benchmark 中 B2/B4 (ReAct variants) 崩溃的原因。BioMed-Agent 通过使用进程内 Python 工具（而非依赖 API 的 tool-calling 机制）避免了此问题。

---

## 9. 整个 pipeline 跑一次要多久？

CSTB case study 总共 334 秒（约 5.6 分钟）。时间细分：

| Phase | 耗时 | 比例 |
|-------|------|------|
| LiteratureAgent（文献检索 + 证据整合） | 162.5s | 48.7% |
| OrchestrationAgent（DAG 规划） | 52.6s | 15.7% |
| AnalysisAgent（4 节点执行） | 76.7s | 23.0% |
| ReportAgent（报告生成） | 42.3s | 12.7% |

其中几乎全部时间都是 LLM API 延迟。纯计算（缓存查询、统计分析）在秒级完成。如果代理或 API 慢，LiteratureAgent 可能超过 3 分钟。如果代理断连，降级模式可在 ~10 秒内返回（使用占位 EvidenceLink 和 Hypothesis）。

---

## 10. 怎么保证 Agent 不编造引用？

五层防线协同工作：

- **Layer 2**（结构）：EvidenceLink 的数据模型级约束——如果 LLM 产出了一个 `strength="strong"` 的 claim 但没有 supporting_pmids，系统拒绝创建该对象。
- **Layer 3**（后验）：提取 LLM 输出中所有 `[PMID:xxxxxxxx]` 格式的引用，交叉比对实际检索结果集。不在集合中的引用被移除。如果移除后 claim 失去了所有 supporting_pmids → 触发 Layer 2 检测。
- **Layer 4**（交叉验证）：A2 检查 A1 的 evidence_chain 是否内部一致（同一条证据链中不会出现互相矛盾的 claim）。A4 检查 A3 的分析结果——如果声称"显著"但效应量微小，发出 WARNING。
- **Layer 5**（人工）：所有 `strength="strong"` 的 claim 和 `hallucination_rate > 0.1` 的输出被标记为 `[HUMAN REVIEW RECOMMENDED]`。

但这套防线不是 100% 可靠的。LLM 可能编造一个"看起来真实但在检索结果中不存在"的 PMID——Layer 3 V1 可以捕获格式正确的虚假 PMID，但如果 LLM 编造了一个格式错误或罕见的 PMID，V1 的捕获能力取决于与检索结果集的交叉比对覆盖率。

---

## 11. 文献检索为什么只有 2 篇论文？（CSTB case study）

CSTB case study 中 LiteratureAgent 只检索到 2 篇论文。这是一个已知问题，可能原因：

1. **GFW 网络限制**：PubMed API 在中国大陆经过代理访问，网络延迟和 TCP RST 注入可能导致部分检索请求失败
2. **查询构建策略**：当前的查询分解（question decomposition）策略可能过于严格，缩小了检索范围
3. **LLM Rerank 过滤过猛**：LLM Rerank 可能将一些低相关性但有价值的论文排除了

T1-LIT benchmark 任务专门设计用于评估和诊断这个问题——通过 Recall@K 和 Precision@K 指标量化检索质量。但该任务的全量 LLM 运行尚未完成。

---

## 12. 为什么方法学白名单不对 Agent 暴露？

S2 hallucination 检测器维护了一个 ≥20 篇常用生物信息学方法论文的白名单（如 limma PMID:25605792, DESeq2 PMID:23193258）。Agent 经常引用这些方法论文来解释它们使用的工具——如果不加白名单，这些引用会被硬规则 V1（PMID 存在性检查）误判为幻觉。

但白名单的内容**不对 Agent 的 prompt 或配置暴露**。原因是：如果 Agent 知道了白名单，它可能学会"安全地"引用白名单中的 PMID 来避免被标记，即使它实际并没有使用对应的方法。

这个设计权衡意味着：白名单需要定期维护（每季度增删 2-3 篇），防止长期运行的 Agent 通过多次 benchmark 间接学习白名单内容。
