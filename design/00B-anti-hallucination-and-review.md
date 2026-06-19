# 00-B — 反幻觉框架 × 窗口角色定义 × 审阅协议

> **读者**：你自己（作为五个窗口的审阅者）+ 每个独立 Claude 窗口（作为执行者）
> **用途**：定义统一的五层反幻觉防线，为每个 Step 窗口指定身份、评审标准和审阅清单
> **前提**：先读 `00-master-coordination.md` 了解整体架构

---

## 第一部分：反幻觉五层防线

这是贯穿所有 Step 的统一防线。每个 Step 的窗口必须实现对应层的防御机制。

```
Layer 5: HUMAN REVIEW ─ 关键结论人工确认（你来做）
    ▲
Layer 4: CROSS-VALIDATION ─ Agent 间互检（A4 ReportAgent 验证 A3 输出）
    ▲
Layer 3: POST-HOC VERIFICATION ─ PMID 真实性检查 + 统计量合理性检查
    ▲
Layer 2: STRUCTURAL CONSTRAINT ─ 数据模型强制溯源（EvidenceLink, AnalysisResult）
    ▲
Layer 1: PROMPT CONSTRAINT ─ 所有 LLM 调用内嵌反幻觉指令
```

### Layer 1 — Prompt 约束（每条 LLM 调用必须遵守）

任何发给 LLM 的 system prompt 或 user prompt，如果涉及**科学内容生成**（文献综述、证据整合、假设生成、结果解释、报告撰写），必须包含以下硬约束块：

```
## CRITICAL CONSTRAINTS (MUST FOLLOW)

1. **No Fabrication**: Do NOT fabricate gene functions, pathway associations, 
   protein interactions, disease mechanisms, or biological interpretations 
   that are NOT directly supported by the provided data or cited sources.

2. **Source Attribution**: Every factual claim about biology or medicine MUST 
   be traced to either:
   (a) A specific PMID (PubMed ID) from the retrieved literature, OR
   (b) A specific computed result from the provided analysis data.

3. **Uncertainty Expression**: When evidence is weak, conflicting, or absent, 
   explicitly state so. Use phrases like:
   - "Based on limited evidence (N=1 study)..."
   - "The evidence on this point is conflicting..."
   - "This hypothesis has NOT been experimentally validated..."
   - "We did NOT find published evidence for..."

4. **Quantitative Precision**: Report statistical results with exact values 
   and confidence intervals. Do NOT round p-values to "p<0.05" — report the 
   actual value. Do NOT say "significantly associated" without the effect size.

5. **Negative Results**: Report what was NOT found as clearly as what was 
   found. "We found NO significant association between CSTB and ..." is as 
   important as a positive finding.
```

**注意**：此约束块可以根据具体 task 调整，但 5 条原则（不虚构、溯来源、表不确定性、定量精确、报告阴性结果）不可删除。

### Layer 2 — 结构约束（数据模型内建验证）

所有 Agent 间传递的数据结构必须包含**可验证的溯源字段**。这意味着：

| 数据类型 | 必须包含的溯源字段 | 验证方式 |
|---------|------------------|---------|
| `EvidenceLink` | `supporting_pmids: list[str]` | PMID 必须在 `retrieved_papers` 列表中 |
| `Hypothesis` | `rationale: str` (引用 EvidenceLink) | rationale 中的每个事实主张可追溯到 EvidenceLink |
| `AnalysisResult` | `data_source: str`, `method: str`, `raw_output_file: str` | raw_output_file 必须存在于磁盘 |
| `ReportSection` | `source_agents: list[str]`, `source_artifacts: list[str]` | 每个 artifact 必须可追溯到 Agent 输出 |

**关键规则**：如果 Paper 的 `evidence_summary` 中有一句 "CSTB is overexpressed in colorectal cancer"，这句话必须能从 `evidence_chain` 中找到对应的 EvidenceLink，而该 EvidenceLink 必须有至少 1 个 supporting_pmid。

如果找不到——这就是幻觉。系统应该自动标记该 claim 为 `strength: "unverified"` 或直接剔除。

### Layer 3 — 后验验证（LLM 输出后的程序化检查）

每个 Agent 在收到 LLM 响应后，必须运行以下验证步骤：

```
POST-HOC VERIFICATION PIPELINE
──────────────────────────────
LLM 输出 → 
  V1. PMID 存在性检查: 提取所有 [PMID:xxxxxxxx] → PubMed API 验证存在性
  V2. 基因名验证: 提取所有 gene symbol → 检查是否在输入数据或已知基因列表中
  V3. 统计量合理性: 提取所有 HR/OR/RR/p-value → 检查数值范围 (HR不应>100)
  V4. 一致性检查: 同一 Agent 的多轮输出中，同一事实是否被前后矛盾地描述
  → 清洗后的输出
```

**V1 — PMID 验证器**（Step 1 实现，Step 3 复用）：
```python
def verify_pmids(text: str, retrieved_pmids: set[str]) -> dict:
    """
    提取文本中所有引用的 PMID，检查是否在检索结果中。
    返回: {"valid": [...], "suspicious": [...], "hallucination_rate": float}
    
    suspicious = 格式像 PMID 但不在检索结果中的
    """
```

**V3 — 统计量合理性**（Step 3 实现）：
```python
STAT_SANITY_CHECKS = {
    "hazard_ratio": lambda x: 0.01 < x < 100,
    "p_value": lambda x: 0 <= x <= 1,
    "spearman_rho": lambda x: -1 <= x <= 1,
    "logFC": lambda x: -20 < x < 20,
}
```

### Layer 4 — 交叉验证（Agent 间互检）

**核心原则**：Agent N+1 不盲目信任 Agent N 的输出。Agent N+1 必须对上游输出做最低限度的 sanity check。

具体来说：

```
LiteratureAgent 输出 ──→ OrchestrationAgent 验证:
  "LiteratureReview 中的 evidence_chain 是否内部一致？
   是否有 hypothesis 的 rationale 与 evidence_chain 矛盾？"

OrchestrationAgent 输出 ──→ AnalysisAgent 验证:
  "AnalysisPlan 中的每个分析节点是否有对应的数据源？
   数据源路径是否存在？所需基因是否在数据中？"

AnalysisAgent 输出 ──→ ReportAgent 验证:
  "分析结果是否在统计上合理？
   不同分析节点的结论是否互相矛盾？
   例如：Cox 回归说 CSTB 是保护因素(HR<1)，
   但差异表达说 CSTB 在肿瘤中高表达——这两个需要解释"
```

**实现方式**：每个下游 Agent 在接收上游输入时，运行一个 `validate_upstream()` 方法。该方法输出 warnings（非致命矛盾）和 errors（致命矛盾，需要上游 Agent 重新产出）。

### Layer 5 — 人工审阅（你做最后一道防线）

以下类型的输出**必须经过你的人工确认**才能进入最终报告：

| 需要人工确认的内容 | 原因 |
|------------------|------|
| 每个 Hypothesis 的 `statement` | 科学假设的合理性无法完全自动化判断 |
| EvidenceLink 中 `strength: "strong"` 的 claims | "强证据"是高置信度声明，需要人工抽样验证 |
| 最终报告中的 "Conclusion" 段落 | 结论是对外展示的核心信息 |
| 任何 `hallucination_rate > 0.1` 的 Agent 输出 | 高幻觉率意味着 LLM 可能在不稳定状态 |

---

## 第二部分：五个窗口的身份、评审标准和审阅清单

### 通用原则（适用所有窗口）

1. **每个窗口打开时**，你把它的 Step 设计文档 + `00-master-coordination.md` + 本文档一起粘贴。
2. **窗口启动 prompt 模板**：
   > "你是 [ROLE]。你的任务是 [TASK]。你的输入是 [INPUTS]。你的输出将被 [WHO REVIEWS] 评审，评审标准是 [CRITERIA]。在开始实现之前，先和我讨论你对该 Step 中 [KEY DECISIONS] 的理解和方案。"
3. **每轮对话结束时**，窗口应输出：(a) 本轮完成的工作，(b) 做出的设计决定，(c) 给其他 Step 的接口变更通知。

---

### Step 1 窗口：文献推理 Agent + RAG Pipeline

#### 身份定义
```
你是 Biomedical NLP Engineer。
你擅长：生物医学文献检索（PubMed/MeSH）、信息检索系统（embedding/向量检索）、
科学证据整合、反幻觉 prompt 设计。
你的弱点：不擅长 UI/UX、不擅长 DevOps、不擅长写论文——这些由其他窗口负责。
你的核心信念：没有任何科学主张可以在没有可验证来源的情况下存在于系统中。
```

#### 输入材料
- `00-master-coordination.md`（共享类型 + 共享基础设施）
- `01-literature-rag.md`（Step 1 设计方向）
- 本文档 §第一部分（五层防线）
- `CSTB_paper/references/fetch_pubmed.py`（已有 PubMed 调用代码）
- `生信分析/spatial_agent/modules/m3_llm_enhancer.py`（已有反幻觉 prompt）
- `shared/gfw_probe.py`（GFW 探测）

#### 成功标准（从 01- 中提取，精确化为可验证项）

| # | 标准 | 验证方式 |
|---|------|---------|
| P0-1 | LiteratureAgent 能对 10 个 query 产出 LiteratureReview | 跑 10 次，检查每个输出是否包含全部字段 |
| P0-2 | 每个 LiteratureReview 至少包含 8 篇真实论文 | PMID 存在性检查（Layer 3 V1） |
| P0-3 | 证据链的每个 claim 至少有 1 个 supporting_pmid | 程序化检查 evidence_chain |
| P0-4 | 假设不包含虚构的基因功能 | 基因名验证（Layer 3 V2） |
| P0-5 | 幻觉率 ≤ 15%（即 evidence_chain 中 ≥85% 的 claims 有真实 PMID 支持） | PMID 验证器 |
| P1-1 | Agent 至少 3/10 query 发起了多轮检索 | 检查执行日志中的检索轮数 |
| P1-2 | 至少 1 个 case 识别了证据冲突 | 检查 evidence_chain 的 counter_evidence 字段 |
| P1-3 | 语义检索排序优于关键词排序（人肉评估 3 个 query） | 人肉对比 top-5 的相关性 |

#### 审阅清单（你作为审阅者，每轮对话后检查）

在代码完成前（设计阶段）：
- [ ] Prompt 模板是否包含了 Layer 1 的 5 条约束？
- [ ] EvidenceLink 数据结构是否包含所有溯源字段？
- [ ] 证据整合的逻辑是否有明确的流程（不是"LLM 自己看着办"）？
- [ ] PMID 验证器的设计是否合理？如何处理 PubMed API 不可用的情况？
- [ ] 多轮检索的触发条件是否明确（不是无限循环）？

在代码完成后（验证阶段）：
- [ ] 找 3 个你不会告诉 window 的全新 query，跑 Agent 输出，人肉检查：
  - [ ] 引用的 PMID 是否真实存在？
  - [ ] 论文结论是否被准确表述（不是断章取义）？
  - [ ] 假设是否真的从证据链推理而来（不是凭空生成）？
- [ ] 幻觉率是否真的 ≤ 15%？自己数一遍。
- [ ] 有没有发现 LLM 编造了看起来 plausible 但实际不存在的论文？

#### 该 Step 特有的幻觉风险

| 风险 | 表现 | 防线 |
|------|------|------|
| **论文幻觉** | 引用不存在的 PMID | Layer 3 V1：PMID 验证器 |
| **断章取义** | 引用了真实论文但歪曲了结论 | Layer 5：人工抽样验证（至少查 3 篇原文） |
| **过度推断** | 从"相关"推出"因果"，从"体外"推出"体内" | Layer 1：prompt 约束 → Layer 2：EvidenceLink.strength 降级 |
| **检索偏见** | 只检索支持预设结论的论文 | 多轮检索的 query 应该有正面和反面两个方向 |

---

### Step 2 窗口：生物医学 Agent Benchmark

#### 身份定义
```
你是 Evaluation Methodologist。
你擅长：设计公平、严格、可复现的评测框架。定义 metrics、构建 ground truth、
设计 baseline 对比实验。你对"这个 benchmark 是否真的能区分好 Agent 和坏 Agent"
有偏执般的关注。
你的弱点：不擅长写应用代码、不擅长系统集成——这些由其他窗口负责。
你的核心信念：如果一个 benchmark 不能暴露 Agent 的失败模式，它就是无用的。
```

#### 输入材料
- `00-master-coordination.md`（共享类型）
- `02-biomed-benchmark.md`（Step 2 设计方向）
- 本文档 §第一部分
- `生信分析/spatial_agent/core/constants.py:148-218`（56条质量门控）
- ITIP Phase C/D/E 的已验证计算结果（ground truth 候选）

#### 成功标准

| # | 标准 | 验证方式 |
|---|------|---------|
| P0-1 | 5 个任务全部有明确的 ground truth | 检查每个 task 的 ground_truth 字段是否非空 |
| P0-2 | 3 个 baseline 在全部 5 个任务上跑通 | 检查 benchmark runner 输出 |
| P0-3 | LiteratureAgent 在 T1-LIT 上跑通 | Step 1 产出作为被测对象 |
| P0-4 | hallucination_rate 的检测逻辑能捕获至少 1 个真实幻觉 | 人工注入 1 个假 PMID，检查是否被标记 |
| P1-1 | LiteratureAgent 在 T1-LIT 的 Overall Score > B1 (naive LLM) | 对比表 |
| P1-2 | 至少发现 1 个 B2 (ReAct) 在生物医学场景的失败模式 | 定性分析 |
| P2-1 | 完整的 evaluation rubric（评分细则表） | 文档 |

#### 审阅清单

设计阶段：
- [ ] Ground truth 是怎么构建的？来源是什么？有没有偏差？
- [ ] 如果 ground truth 本身有错（如 ITIP Phase C 的计算可能有 bug），benchmark 会错误地给 Agent 打分吗？
- [ ] Metrics 会不会被 game？有没有 Agent 可以用低质量策略（如大量生成内容）刷高 completion rate 的漏洞？
- [ ] 3 个 baseline 之间的差异是否足够大，能证明 benchmark 的区分度？
- [ ] T1-LIT 的人工评分标准是否明确（不是"你觉得这个综述写得好吗"而是"检查以下 5 个维度..."）？

验证阶段：
- [ ] 自己跑一遍 benchmark，检查每个 task 的输出是否合理。
- [ ] 挑 3 个 agent×task 组合，人肉验证 metrics 计算的正确性。
- [ ] 确认 hallucination_rate 不是在"捉鬼"（把正确的但小众的结论标记为幻觉）。

#### 该 Step 特有的风险

| 风险 | 表现 | 防线 |
|------|------|------|
| **Ground truth 偏差** | 只用 ITIP 的结果作为正确答案，但 ITIP 可能有分析错误 | 至少 2 个独立来源交叉验证 |
| **Metric hacking** | Agent 学会了输出 benchmark 想要的形式，而非正确的内容 | 加入对抗性 test case |
| **Hallucination metric 不敏感** | 没有真正捕获到幻觉 | 注入已知的假数据，检查 recall |

---

### Step 3 窗口：多 Agent 协作闭环 Pipeline

#### 身份定义
```
你是 Multi-Agent Systems Architect。
你擅长：Agent 间通信协议设计、工作流编排、失败恢复、系统集成。
你有丰富的真实数据 pipeline 经验，知道数据流在哪个环节容易断裂。
你的弱点：不擅长做文献综述、不擅长设计 benchmark——这些由 S1/S2 窗口负责。
你的核心信念：一个 Agent 系统的正确性取决于最弱的那个 Agent。
如果 A1 的输出是幻觉，A2/A3/A4 只会放大它。
```

#### 输入材料
- `00-master-coordination.md`
- `03-multi-agent-pipeline.md`
- 本文档 §第一部分（特别是 Layer 4 交叉验证）
- Step 1 的 LiteratureAgent（完整实现）
- Step 2 的 BenchmarkTask 类型（用于接口对齐）
- Spatial Agent 的全部代码（`master.py`, `worker.py`, `message_bus.py`）
- ITIP/CSTB 的分析结果（预计算缓存）

#### 成功标准

| # | 标准 | 验证方式 |
|---|------|---------|
| P0-1 | 4 Agent 串行完成 CSTB 案例全流程，不崩溃 | 端到端运行 |
| P0-2 | A2 → A3 → A4 的数据传递完整（无字段丢失） | 检查各阶段的输入输出 schema |
| P0-3 | A3 至少成功执行 3 个分析任务 | 检查 AnalysisResult |
| P0-4 | A4 产出的报告包含定量结果 + 文献引用 + 局限性 | 人肉阅读报告 |
| P0-5 | 至少 1 个分析任务经历了失败恢复（F2/F3） | 检查执行日志 |
| P1-1 | A2 对不同输入产生不同的 DAG（不是硬编码） | 用 2 个不同 case 测试 |
| P1-2 | A3 的每个工具调用有 why/what/result 记录 | 检查决策日志 |
| P1-3 | Pipeline 实现了 EvalAgent protocol，可被 S2 评测 | 跑 S2 的 runner |
| P1-4 | **交叉验证（Layer 4）生效**：A4 至少报告了 1 个 A3 输出中的 inconsistency | 阅读 A4 的 validate_upstream() 输出 |

#### 审阅清单

设计阶段：
- [ ] A2 (OrchestrationAgent) 的 LLM 规划是真正的推理还是模板填空？如果输入的假设变了，它会产出不同的 DAG 吗？
- [ ] A3 (AnalysisAgent) 的"工具调用"是否真的让 Agent 做了决策（选什么方法、用什么参数），还是只是按固定顺序调固定工具？
- [ ] A4 (ReportAgent) 是否对 A3 的输出做了 Layer 4 交叉验证？
- [ ] 失败恢复的触发条件是否明确？有没有可能进入无限重试循环？
- [ ] R 代码的集成方式（缓存 vs 实时调用）是否清楚？缓存数据是否可验证？

验证阶段：
- [ ] 亲自跑一遍完整 pipeline，记录每一步的耗时，确认没有超过合理范围（单次运行 < 60 分钟）。
- [ ] 检查 A3 的决策日志——Agent 真的在"思考"选什么方法，还是只是执行预定义脚本？
- [ ] A4 产出的报告中，找一个定量结论（如 HR=1.42），反向追溯到原始数据，确认数字正确。
- [ ] 故意制造一个错误（如把 CSTB 表达数据替换成随机噪声），看 A3 是否能检测到并触发 F4 恢复。

#### 该 Step 特有的幻觉风险

| 风险 | 表现 | 防线 |
|------|------|------|
| **错误传播** | A1 的幻觉被 A2 当作事实，被 A3 当作分析目标，被 A4 写入报告 | Layer 4：每个下游 Agent 验证上游输出 |
| **规划幻觉** | A2 生成了不存在的分析方法或数据源 | A3 的 validate_upstream() 检查数据源路径 |
| **解释幻觉** | A3 对统计结果给出错误的生物学解释 | A4 的交叉验证 + Layer 5 人工抽查 |
| **过度报告** | A4 选择性报告有利结果，忽略阴性结果 | Layer 1 prompt 强制要求报告阴性结果 |

---

### Step 4 窗口：技术报告

#### 身份定义
```
你是 Academic Author (Senior PhD Student level)。
你擅长：科学写作、文献综述、数据可视化与解读、论证结构设计。
你的标准：Nature Communications / Bioinformatics 级别的论文质量。
你的弱点：不擅长写代码——报告中的数据必须来自 S1-S3 的实际输出，不能编造。
你的核心信念：一篇论文中没有任何一句话可以在没有数据或引用支持的情况下存在。
```

#### 输入材料
- `00-master-coordination.md`
- `04-technical-report.md`
- 本文档 §第一部分
- Step 1-3 的完整实验数据（JSON 文件 + 日志）
- 已有的写作参考：Spatial 综合研究报告、CSTB 论文草稿、TAOR API 设计文档

#### 成功标准

| # | 标准 | 验证方式 |
|---|------|---------|
| P0-1 | 完整 8 章结构，正文 12-18 页 | 字数统计 |
| P0-2 | 至少 6 张图 + 2 张表，全部从真实数据生成 | 逐图检查数据来源 |
| P0-3 | 至少 30 篇参考文献 | 参考文献计数 |
| P0-4 | Results 的每个数字可追溯到 S1-S3 的输出 | 随机抽 5 个数字验证 |
| P0-5 | Discussion 列出 3+ 条局限性 | 人肉阅读 |
| P1-1 | Related Work 有对比表（≥5 个系统 × 5 个维度） | 检查表 |
| P1-2 | 有外部读者 feedback | 记录 |
| **P0-6** | **报告中的任何一个声称，如果不是来自 S1-S3 的数据，就必须来自参考文献。没有任何"凭空"的论断。** | 全文审计 |

#### 审阅清单

草稿阶段：
- [ ] Introduction — 问题陈述是否清楚？是不是在"为 AI 而 AI"？
- [ ] Related Work — 是否遗漏了重要工作（特别是中国团队的相关工作）？
- [ ] 贡献陈述 — 是否诚实？（不要声称 "state-of-the-art" 如果 benchmark 没那么好）
- [ ] Results — 每个数字是否标注了来源（哪个 Step 的哪个文件）？
- [ ] Discussion — 局限性是否诚实？有没有回避明显的问题（如 benchmark 太小、单案例）？

成稿阶段：
- [ ] 找一个人（不是你自己、不是 Claude）读一遍 Introduction 和 Conclusion。问她/他：你理解这个系统做了什么吗？你觉得它的贡献是什么？
- [ ] 和 S1-S3 的实验数据做一次"全文交叉比对"——报告中每个 quantitative claim 都要能在实验数据中找到对应。
- [ ] 参考文献格式一致、没有缺字段、没有引用预印本却不标注。

#### 该 Step 特有的幻觉风险

| 风险 | 表现 | 防线 |
|------|------|------|
| **数据包装** | 把 S1-S3 中不够好的数据说得很好（"our agent achieves strong performance" 但实际只比 baseline 高 5%） | 定量结果必须带置信区间；Discussion 必须诚实地讨论效果大小 |
| **引用幻觉** | 引用了一篇论文但它的结论和你说的是相反的 | Layer 5：至少抽查 5 篇引用文献的原文 |
| **贡献膨胀** | 声称自己做了实际上没做的事（如在 Related Work 中说"我们解决了前人未解决的问题"） | 每个 claim 必须有 S1-S3 实验数据的直接支撑 |

---

### Step 5 窗口：投递组合打包

#### 身份定义
```
你是 Developer Advocate / Technical Storyteller。
你擅长：将复杂的技术系统转化为 30 秒内能理解的叙述。写 README、做 PPT、
提炼核心信息。你知道面试官的注意力分配模式。
你的弱点：不擅长写底层代码、不擅长跑实验——你的原材料来自 S1-S4。
你的核心信念：一个好的项目如果没有人能理解它，等于不存在。
```

#### 输入材料
- `00-master-coordination.md`
- `05-portfolio-packaging.md`
- Step 1-4 的全部产出
- TAOR demo PPT（模板）+ `build-ppt.js`

#### 成功标准

| # | 标准 | 验证方式 |
|---|------|---------|
| P0-1 | GitHub README 30 秒可理解 | 真人测试 |
| P0-2 | Quick Start 真的能跑通 | 干净 venv 测试 |
| P0-3 | Benchmark 结果表是真实数字 | 对比 S2 输出 |
| P0-4 | PPT 12 张幻灯片完成 | 人肉检查 |
| P1-1 | Quick Start 被至少 1 个其他人跑通 | 记录 |
| P1-2 | CI 通过 | GitHub Actions |

#### 审阅清单

- [ ] README — 陌生人 30 秒能说出"这是做什么的"吗？Quick Start 5 行命令能跑通吗？
- [ ] PPT — 每张幻灯片 ≤ 1 个核心观点吗？第 5 张"技术深潜"是否真的有深度（不是表面描述）？
- [ ] 简历描述 — 5 行涵盖了 JD 的 5 个方向关键词吗？
- [ ] 面试 Q&A — 12 个问题都有答案吗？每个答案有具体例子吗？

#### 该 Step 特有的幻觉风险

这个 Step 不产生新数据，只包装已有数据。所以这里的"幻觉"指的是**过度营销**——把还不够好的结果说成"突破性进展"。这是最危险的，因为面试官能识破。

**防线**：S5 窗口对 S1-S4 产出的任何"重新表述"必须保持原有的效果大小和不确定性表述。不能把 "r=0.15" 说成 "shows correlation"。不能把 "trend towards significance (p=0.06)" 说成 "significant"。

---

## 第三部分：你（主 Agent）在各 Step 之间的职责

五个窗口在执行时，你需要在以下节点介入：

```
S1 窗口 ──[设计决定确认]──→ 你审阅 §审阅清单（设计阶段）
    │                            │
    └──[代码完成]────→ 你审阅 §审阅清单（验证阶段）
                          │
                          确认 P0 全部达成 → S1 完成 ✓
                          │
                          回写 00-master-coordination.md §六（决策日志）
                          │
                          ▼
S2 窗口启动 ←── 你提供: S1 的类型定义 + S1 的 LiteratureAgent
    │
    └──[同样流程]──→ S2 完成 ✓
                          │
                          ▼
S3 窗口启动 ←── 你提供: S1 的 LiteratureAgent + S2 的 BenchmarkTask 类型
    │
    └──[同样流程]──→ S3 完成 ✓
                          │
                          ▼
S4 窗口启动 ←── 你提供: S1/S2/S3 的全部实验数据
    │
    └──[同样流程]──→ S4 完成 ✓
                          │
                          ▼
S5 窗口启动 ←── 你提供: S1-S4 的全部产出
    │
    └──[同样流程]──→ S5 完成 ✓
                          │
                          ▼
                    投递 ✓
```

你在每个节点做的事：
1. **读窗口的输出**（代码、数据、文档）
2. **按审阅清单逐项检查**
3. **如果 P0 不达标**→ 退回窗口，指明具体哪一条不达标
4. **如果 P0 达标**→ 确认完成，回写决策日志，启动下一个 Step 窗口
5. **如果发现跨 Step 的接口变更**→ 更新 `00-master-coordination.md`，通知受影响的其他窗口

---

> **使用说明**：打开任意 Step 窗口时，把此文档 + 对应 Step 的设计文档 + `00-master-coordination.md` 一起作为 context。窗口的身份定义在第一段，告诉 Claude "你是 [ROLE]"。
