# BioMed-Agent Architecture

本文档介绍 BioMed-Agent 的系统架构：四个智能体如何协作、数据如何流转、反幻觉防线如何逐层工作、以及关键设计决策背后的理由。

---

## 整体架构

![System Architecture](paper/figures/fig1_architecture.png)

BioMed-Agent 由四个串行协作的智能体组成，每个智能体在接收上游输入后、开始自己的工作前，执行交叉验证（Layer 4）。这模拟了真实科研工作流的信息流和质检节点。

```
用户问题
  │
  ▼
┌─────────────────────────────────────────────┐
│ A1: LiteratureAgent                         │
│ PubMed多轮检索 → 证据链整合 → 假设生成        │
│ 输出: LiteratureReview                       │
└──────────────┬──────────────────────────────┘
               │ LiteratureReview
               ▼
┌─────────────────────────────────────────────┐
│ L4 节点 #1: A2 验证 A1 输出                   │
│ 证据链内部一致性 / 假设-证据对应 / 置信度合理性  │
└──────────────┬──────────────────────────────┘
               │ (PASS / WARNING → 继续)
               ▼
┌─────────────────────────────────────────────┐
│ A2: OrchestrationAgent                      │
│ LLM 驱动动态 DAG 生成 → 方法兼容矩阵校验       │
│ 输出: AnalysisPlan                           │
└──────────────┬──────────────────────────────┘
               │ AnalysisPlan
               ▼
┌─────────────────────────────────────────────┐
│ L4 节点 #2: A3 验证 A2 输出                   │
│ 数据源存在性 / 基因名有效性 / 方法合理性        │
└──────────────┬──────────────────────────────┘
               │ (PASS / WARNING → 继续)
               ▼
┌─────────────────────────────────────────────┐
│ A3: AnalysisAgent                           │
│ Think→Act→Observe + F1-F5 失败恢复           │
│ 输出: list[AnalysisResult]                    │
└──────────────┬──────────────────────────────┘
               │ list[AnalysisResult]
               ▼
┌─────────────────────────────────────────────┐
│ L4 节点 #3: A4 验证 A3 输出                   │
│ 统计量合理性 / 跨节点矛盾 / 效应量阈值 / 覆盖率 │
└──────────────┬──────────────────────────────┘
               │ (PASS / WARNING → 继续)
               ▼
┌─────────────────────────────────────────────┐
│ A4: ReportAgent                             │
│ 多源整合 → 结构化报告 → 强制阴性结果节          │
│ 输出: Markdown 报告                           │
└─────────────────────────────────────────────┘
```

---

## 四个智能体

### LiteratureAgent — 文献检索与证据整合

LiteratureAgent 执行多轮 PubMed 检索，遵循 Think→Act→Observe 循环。

**Think 阶段**：审查已有证据，判断是否充足。如果某维度证据不足（如"关于免疫机制几乎没有研究"），生成补充检索查询。

**Act 阶段**：PubMed esearch + efetch → 去重 → LLM Rerank 语义排序（无 embedding 模型，直接由 LLM 逐批判断论文与问题的相关性，0-1 打分）。

**Observe 阶段**：读取 Rerank 结果，记录本轮新增的论文和证据覆盖变化。

**闸门控制**（防止无限检索）：
1. `max_rounds=3`（硬上限）
2. 查询去重：LLM 判断新查询是否与历史查询本质相同
3. Token 预算：累计超过 15000 时强制终止

**证据整合**：检索完成后，EvidenceSynthesizer 将多篇论文整合为结构化证据链——每条主张（claim）必须有至少 1 个 supporting PMID，由 LLM 初判 strength（strong/moderate/weak/unverified），再由 4 条程序化规则校验。

**假设生成**：HypothesisGenerator 从证据链的"已知-未知"边界识别知识缺口，生成 1-3 个可验证假设。每个假设必须包含：
- 可证伪的预测（testable_prediction）
- 验证所需的数据类型（required_data）
- novelty 分类（novel_to_our_knowledge / supported_by_existing）+ 分类依据

### OrchestrationAgent — 动态分析规划

OrchestrationAgent 不从固定模板生成分析计划。它的核心任务是理解 LiteratureReview 中每个假设的具体内容，然后推理出验证这些假设需要什么分析。

**Hypothesis 分类**（LLM 推理，非硬编码）：
- `single_gene_prognostic`：单基因与生存/表达的关联 → 小型 DAG（2-3 节点）
- `pathway_mechanism`：涉及多分子的生物机制 → 中型 DAG（4-6 节点）
- `multi_gene_drug`：药物敏感性或多基因特征 → 含药物筛选节点的大型 DAG

**方法指派与校验**：LLM 为每个节点选择方法后，系统运行程序化校验——方法是否在 METHOD_COMPATIBILITY 矩阵中？样本量是否满足要求？方法组合是否在 INVALID_COMBINATIONS 黑名单中？不通过则重新规划（最多 2 次）。

**反模板机制**：每个 AnalysisNode 的 `rationale` 字段强制 LLM 解释**为什么**为**这个假设**选择了**这个方法和数据源**。这是区分推理与模板填空的关键字段。

### AnalysisAgent — 多组学分析执行

AnalysisAgent 对 DAG 中的每个节点执行 Think→Act→Observe 循环。

**Think**：审查节点定义 → 选择工具 → 决定参数。如果推荐的方法不合适，提出替代方案（同时记录 `fallback_tool` 和 `fallback_parameters`）。

**Act**：工具调用。工具内部实现三层数据访问：

| 层级 | 机制 | 适用分析 |
|------|------|---------|
| L1 缓存查询 | 从预计算 JSON 缓存直接读取 | 差异表达、Cox 回归、KM |
| L2 实时 Python | pandas + scipy.stats 实时计算 | 免疫相关性、药物筛选、基因-基因相关 |
| L3 F4 降级 | 缓存未命中且不支持实时计算时，标记为 degraded | pathway enrichment 等 |

**Observe**：LLM 解释分析结果 → 生成 `result_interpretation`。程序化后处理提取数值并做统计量范围检查。

**F1-F5 失败恢复**：

| 类型 | 触发条件 | 恢复策略 |
|------|---------|---------|
| F1 瞬时 | API 超时、网络波动 | 自动重试 3 次 |
| F2 参数 | 输出全 NA、方法选择错误 | 使用 fallback_tool，最多 2 次 → 升级 F4 |
| F3 方法 | Cox PH 假设违反（Schoenfeld test p<0.05） | 降级为 KM + log-rank |
| F4 数据 | 基因不在数据中、缓存未命中且不支持实时计算 | 标记 degraded，继续下一节点 |
| F5 未知 | 任何未分类错误 | 记录日志，继续下一节点 |

**决策日志**：每个 AnalysisResult 包含 `why`（为什么选这个工具）、`what`（实际做了什么）、`result_interpretation`（LLM 对结果的解释），确保每个分析步骤可追溯。

### ReportAgent — 证据整合与报告生成

ReportAgent 接收三个上游源的输出（LiteratureReview + AnalysisPlan + AnalysisResults），生成结构化 Markdown 报告。

**报告结构**（6 节）：
1. Introduction — 研究问题和背景
2. Methods — 分析方法和数据源
3. Results — 每个假设的验证结果（定量 + 定性）
4. **Negative and Null Findings**（强制节，不允跳过）— 哪些假设无法用现有数据验证？哪些分析产生了零发现？
5. Discussion — 局限性 + 与文献的一致性讨论
6. Conclusion — 核心发现摘要

**写作硬约束**（Layer 1 prompt 嵌入）：
- 每个定量声称必须标注来源（PMID 或 AnalysisResult node_id）
- 报告精确效应量和置信区间，不四舍五入 p 值
- 不把 "trend towards significance (p=0.06)" 说成 "significant"
- 诚实报告失败和降级节点

---

## 反幻觉五层防线

### Layer 1 — Prompt 约束

所有涉及科学内容生成的 LLM system prompt 嵌入 5 条硬约束：

1. **No Fabrication**：不虚构基因功能、通路关联、疾病机制
2. **Source Attribution**：每个事实声称必须追溯到特定 PMID 或分析结果
3. **Uncertainty Expression**：证据弱/冲突/缺失时明确说明
4. **Quantitative Precision**：报告精确数值和置信区间
5. **Negative Results**：未发现的内容和发现的内容同等显著报告

### Layer 2 — 结构约束（数据模型级）

`EvidenceLink.__post_init__()` 内嵌 4 条硬矛盾检测：

1. `strength ∈ {strong, moderate}` 但 `supporting_pmids` 为空 → 拒绝创建
2. `strength == "strong"` 但 `counter_evidence` 非空 → 拒绝创建
3. `strength ∈ {strong, moderate, weak}` 但 `strength_justification` 为空 → 拒绝创建
4. `supporting_pmids` 为空且 `counter_evidence` 为空 → 强制 `strength="unverified"`

这些检测在 dataclass 初始化时自动执行——如果 LLM 产出了不符合结构约束的 claim，系统不会静默通过。

### Layer 3 — 后验验证

LLM 输出后，程序化执行四步验证：

- **V1**（PMID 存在性）：提取所有 `[PMID:xxxxxxxx]` 格式的引用，交叉比对检索结果集。不在集合中的引用被移除，若移除后 supporting_pmids 为空 → 触发 Layer 2 检测
- **V2**（基因名验证）：提取所有大写基因符号，检查是否在输入数据或 NCBI 已知基因列表中
- **V3**（统计量合理性）：HR 0.01-100, p-value 0-1, Spearman ρ -1~1, logFC -20~20
- **V4**（一致性检查）：同一 Agent 的多轮输出中，同一主题是否有前后矛盾的描述

### Layer 4 — 交叉验证（Agent 间互检）

三个 `validate_upstream()` 节点，纯规则驱动（~80 行/节点），无 LLM 调用：

| 节点 | 验证内容 | BLOCKER 条件 |
|------|---------|-------------|
| A2→A1 | 证据链内部一致性、假设-证据对应、置信度合理性 | evidence_chain 或 hypotheses 为空 |
| A3→A2 | 数据源 `pathlib.Path.exists()`、基因名有效性、方法合理性 | 所有节点数据源都不存在 |
| A4→A3 | 统计量合理性、跨节点矛盾（如 Cox HR<1 + DEG logFC>0）、效应量阈值、节点覆盖率 | 所有节点 status="failed" |

### Layer 5 — 人工审阅

以下输出自动标记 `[HUMAN REVIEW RECOMMENDED]`：
- `evidence_chain` 中 `strength="strong"` 的 claim
- 报告中 "Conclusion" 段落
- `hallucination_rate > 0.1` 的 Agent 输出

---

## 关键技术决策

本项目的所有设计决策记录在 [00-master-coordination.md §六](design/00-master-coordination.md)（编号 D-001 ~ D-017）。以下是四个最直接影响外部理解的决策摘要：

| 决策 | 我们选的 | 没选的 | 一句话理由 |
|------|---------|--------|-----------|
| 检索排序 | LLM Rerank | Embedding 模型 (SPECTER2/OpenAI) | 无 GPU，10-30 篇规模足够 |
| 分析执行 | 预计算缓存 + 实时 Python | 子进程调 R (rpy2/Rscript) | Windows segfault 风险 + demo 延迟 |
| Agent 编排 | 4 Agent 串行 + DAG 内并行 | 全并发 / 对话驱动 (AutoGen) | 科研流天然顺序 + 逐级交叉验证 |
| Safety 评分 | 连续惩罚函数 | 硬门槛 (if safety<0.7 → ×0.5) | 消除 cliff effect |

以下展开说明每个决策的细节：

### 为什么用 LLM Rerank 而不是 embedding 模型？

我们没有 GPU，也不想引入额外的模型依赖。LLM Rerank 直接由 DeepSeek 逐批判断论文与问题的相关性并打分（0-1），对 10-30 篇论文的规模足够有效。Embedder 被抽象为接口——如果后续有条件，可以切换到 SPECTER2 等科学文献专用 embedding 模型而不改上层代码。详见 [FAQ.md](FAQ.md#2-为什么用-llm-rerank-而不是-embedding-模型)。

### 为什么预计算缓存而不是实时跑 R？

Windows 上 `Rscript -e` 会 segfault（Rule-R-001），使用子进程调用 R 不仅慢而且脆弱。ITIP/CSTB 的分析结果已经过验证——缓存这些结果为 JSON，让 Agent 的"工具调用"变成数据查询和解释，而非实时计算。端到端演示不需要等 R 跑完，Agent 的智能体现在方法选择、参数决策和结果解释。详见 [FAQ.md](FAQ.md#3-为什么预计算缓存而不是实时跑-r)。

### 为什么 4 Agent 串行而不是并发？

科研工作流天然是顺序的：必须先看文献才能设计实验，必须有了实验方案才能做分析，必须有了分析结果才能写报告。串行架构还使 Layer 4 交叉验证成为可能——每个 Agent 在接收上游输入时先验证，错误不会向下游传播。详见 [FAQ.md](FAQ.md#4-为什么-4-agent-串行而不是并发)。

### 为什么 Safety 用连续惩罚而不是硬门槛？

硬门槛（`if safety < 0.7: total *= 0.5`）会产生 cliff effect——safety=0.69 和 safety=0.71 之间的人为断崖。BioMed-Agent 使用连续惩罚函数：`penalty = 1.0 - max(0, (0.7 - safety) / 0.7)`，safety 从 0.7 降到 0 的过程中惩罚线性递增。详见 [FAQ.md](FAQ.md#5-safety-连续惩罚怎么设计的)。

---

## 共享基础设施

### LLM 调用

所有 Agent 共用 `LLMClient`（`src/llm/client.py`）：
- 模型：DeepSeek v4-pro（通过 `ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN`）
- 默认 temperature：0.3（生物医学场景需要事实准确性优先于创造性）
- `thinking_budget_tokens=1600`（防止 thinking mode 耗尽 max_tokens 预算）
- 每次调用自动记录 `input_tokens` 和 `output_tokens`

### 网络层

`src/utils/network.py` 封装代理检测（`127.0.0.1:7892`）和 3-retry + exponential backoff。所有网络 I/O（PubMed API 等）通过此层。

### 配置

所有 Step 共用 `config.yaml`（LLM 参数、RAG 参数、benchmark 参数、数据路径、输出路径）。

---

## 更多细节

- 完整的 Agent 接口定义、数据流图的每一步、Prompt 模板 → [03-detailed-design.md](design/03-detailed-design.md)
- Benchmark 框架的任务定义、GT 构建方法、metrics 计算公式 → [BENCHMARK.md](BENCHMARK.md)
- 全部 17 条设计决策的理由和上下文 → [FAQ.md](FAQ.md) + [00-master-coordination.md §六](design/00-master-coordination.md)
- 完整 CSTB 案例走读 → [CASE_STUDY.md](CASE_STUDY.md)
