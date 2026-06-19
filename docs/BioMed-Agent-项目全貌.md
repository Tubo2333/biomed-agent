# BioMed-Agent 项目全貌

> 一份跟着 PPT 顺序走的学习文档。每节对应一张幻灯片，但内容更完整。大白话为主，专业术语保留。

---

## 1. 这个项目是什么

**BioMed-Agent** 是一个多智能体协作系统，它让 AI 能自动完成生物医学研究的完整闭环：从查文献、整合证据、提出假设，到设计分析方案、执行多组学数据分析，最后写出结构化的科研报告。

一句话：**四个 AI Agent 串起来干活，把文献里的知识和多组学数据里的信号，变成可验证的科学发现。**

整个项目包含 33 个 Python 源文件、160 个测试、5 套 ground truth 数据集、一套 benchmark 评测框架、一篇中英双语技术报告（8 章/29 篇参考文献），以及你现在看到的这套完整文档。

**代码仓库**：github.com/Tubo2333/biomed-agent

**技术栈**：Python 3.12+ / DeepSeek v4-pro / pandas / scipy / numpy / Anthropic SDK

---

## 2. 它在解决什么问题

生物医学研究面临一个根本性的矛盾：数据和文献都在爆炸性增长，但把它们连起来的能力没有跟上。

**文献危机**：
- PubMed 每年新增超过 150 万篇论文
- 任何一个研究者都不可能持续追踪自己领域的所有新发表
- 后果：假说往往基于不完整的文献综述，错过了关键证据

**数据碎片化**：
- TCGA（癌症基因组图谱）、GEO（基因表达综合数据库）、GDSC（药物敏感性数据库）等大规模数据集已经公开可用
- 但把这些数据转化为可验证的科学假设，需要同时懂生物信息学、统计学和领域知识
- 分析管线碎片化，不同实验室用不同的工具和参数，结果难以复现
- 最关键的问题是：**没有系统化的方式把文献中的证据和数据中的信号连接起来**

**核心差距**：目前不存在一个系统，能在单一可验证的管线中，把自动化文献综述和多组学分析连在一起。

BioMed-Agent 就是来填这个坑的。

---

## 3. 整体方案：四个 Agent 串起来

BioMed-Agent 的核心架构是**四个智能体串行协作**。

为什么是串行不是并行？因为真实科研工作流本来就是顺序的：
1. 先看文献才知道要做什么实验
2. 先设计好方案才能做分析
3. 先有分析结果才能写报告

四个 Agent 各自干什么：

| 顺序 | Agent | 输入 | 输出 | 一句话 |
|------|-------|------|------|--------|
| 1 | **LiteratureAgent（文献探员）** | 研究问题（如"CSTB 在结直肠癌中的预后价值"） | LiteratureReview（证据链 + 假设 + 知识缺口） | 查文献、整证据、提假设 |
| 2 | **OrchestrationAgent（规划师）** | LiteratureReview | AnalysisPlan（分析任务 DAG） | 根据假设设计分析方案 |
| 3 | **AnalysisAgent（实验师）** | AnalysisPlan + 真实数据 | AnalysisResult 列表（含 why/what/result 日志） | 执行分析、处理失败 |
| 4 | **ReportAgent（主编）** | 所有上游输出 | 结构化 Markdown 报告 | 整合结果、写出报告 |

**关键设计：每个 Agent 在接收上游输出后，先用 Layer 4 交叉验证检查上游有没有问题，再开始自己的工作。** 这意味着：
- A2（OrchestrationAgent）会检查 A1（LiteratureAgent）的证据链是不是内部一致
- A3（AnalysisAgent）会检查 A2 的分析计划里的数据源存不存在、方法合不合理
- A4（ReportAgent）会检查 A3 的分析结果统计上合不合理、不同节点之间有没有矛盾

如果检查出致命的矛盾（BLOCKER），pipeline 停止。如果是非致命的问题（WARNING），记录但继续。

---

## 4. Agent 1：LiteratureAgent / 文献探员

LiteratureAgent 是整个管线的起点。你给它一个生物医学问题，它帮你把文献查了、证据理了、假设提了。

**工作流程**：问题分解 → 多轮 PubMed 检索 → LLM 语义重排序 → 证据整合 → 假设生成

### 多轮检索循环（Think→Act→Observe）

这不是一轮检索就完事。Agent 会反复思考"我收集到的证据够不够"：

- **Think**：审视当前收集的证据。比如"关于 CSTB 在 CRC 中的表达有足够的论文，但关于免疫机制几乎没有研究"
- **Act**：生成新的 PubMed 搜索查询，执行检索
- **Observe**：看检索结果，更新证据覆盖状态

**三道闸门**防止无限搜下去：
1. 最多 3 轮（硬上限）
2. 查询去重——新查询不能和之前的本质上相同
3. Token 预算不能超过 15,000

### LLM Rerank（无 embedding 模型）

我们没有 GPU，没有部署本地 embedding 模型。那怎么判断一篇论文和研究问题有多相关？

直接用 DeepSeek 读论文的标题和摘要（截断到 500 字符），让它对相关性打 0-1 分。这叫 **LLM Rerank**。对于 10-30 篇论文的规模完全够用，而且零额外依赖。

Embedder 被抽象成了接口，以后有条件可以换成 SPECTER2 等科学文献专用模型，不用改上层代码。

### 证据整合：EvidenceSynthesizer

这是 LiteratureAgent 最核心的能力。不是让 LLM 写一段综述就完了——那样没法验证每句话的来源。

而是先把每篇论文拆成**原子级的事实主张**（claim），每条主张必须附上支持它的 PMID（PubMed ID）。然后 LLM 评估每条主张的 strength（strong / moderate / weak / unverified），系统再用 4 条硬规则校验。最后才从证据链生成 300-500 字的综述。

### 假设生成：HypothesisGenerator

不是拍脑袋想假设。而是从证据链中找**"已知-未知"的边界**——哪些维度有充分证据？哪些维度完全是空白？空白的地方就是知识缺口，从缺口出发生成可验证的假设。

每条假设必须包含：
- 可证伪的预测（testable_prediction）
- 验证需要什么数据（required_data）
- novelty 分类（novel_to_our_knowledge / supported_by_existing）+ 为什么这么分

---

## 5. 技术深潜：结构化证据链与五层反幻觉防线

这是整个系统最核心的技术贡献。**LLM 会编造引用、虚构基因功能、断章取义——这在生物医学场景里不是小毛病，是会出大问题的。** 我们的防线有五层。

### EvidenceLink 数据模型（Layer 2 — 结构约束）

这不是一个普通的数据类。它的 `__post_init__` 方法里嵌了 4 条硬矛盾检测，在数据对象**创建时**就自动执行：

```python
@dataclass
class EvidenceLink:
    claim: str                      # 原子级事实主张
    supporting_pmids: list[str]     # 支持该主张的 PMID 列表
    strength: str                   # strong / moderate / weak / unverified
    strength_justification: str     # LLM 自证依据（强制填写）
    counter_evidence: str | None    # 反面证据
```

4 条硬检测：
1. 如果 strength 是 strong 或 moderate，但 supporting_pmids 是空的 → **拒绝创建**（你说证据强，但引用的 PMID 呢？）
2. 如果 strength 是 strong，但存在 counter_evidence → **拒绝创建**（有反面证据你怎么敢说 strong？）
3. 如果 strength 不是 unverified，但 strength_justification 是空的 → **拒绝创建**（你说 moderate，为什么？）
4. 如果没有 PMID 也没有反面证据 → **强制改成 unverified**（纯推测，诚实标注）

### Layer 1 — Prompt 约束

所有涉及科学内容生成的 LLM system prompt 都嵌入 5 条硬约束：
1. **不虚构**：不编造基因功能、通路关联、疾病机制
2. **溯来源**：每个事实主张必须能追溯到特定 PMID 或分析结果
3. **表不确定性**：证据弱/冲突/缺失时明确说明
4. **定量精确**：报告精确数值和置信区间，不四舍五入 p 值
5. **报告阴性结果**：没发现的东西和发现的东西同等重要

### Layer 3 — 后验验证

LLM 输出后，程序自动跑四步检查：
- **V1**：提取所有 `[PMID:xxxxxxxx]` 格式的引用 → 交叉比对检索结果集 → 不在集合中的被移除
- **V2**：提取所有大写基因符号 → 检查是否在输入数据或 NCBI 已知基因列表中
- **V3**：检查统计量是否在物理可能的范围内（HR 0.01-100, p 0-1, logFC -20~20）
- **V4**：同一 Agent 的多轮输出中，同一主题是否有前后矛盾的描述

### Layer 4 — 交叉验证（Agent 间互检）

三个纯规则验证节点（无 LLM 调用，~80 行/节点）：

| 节点 | 谁验证谁 | 检查什么 | BLOCKER 条件 |
|------|---------|---------|-------------|
| #1 | A2 验证 A1 | 证据链内部一致性、假设-证据对应、置信度合理性 | evidence_chain 或 hypotheses 为空 |
| #2 | A3 验证 A2 | 数据源存在性（缓存检查）、基因名有效性、方法合理性 | 所有节点数据源都不存在 |
| #3 | A4 验证 A3 | 统计量合理性、跨节点矛盾、效应量阈值、覆盖率 | 所有分析节点都 failed |

### Layer 5 — 人工审阅

以下输出自动标记 `[HUMAN REVIEW RECOMMENDED]`：
- evidence_chain 中 strength="strong" 的 claim
- 报告中 "Conclusion" 段落
- hallucination_rate > 0.1 的 Agent 输出

**重要的是**：这套防线不是 100% 可靠的。LLM 可能编造一个"看起来真实但不在检索结果中"的 PMID。Layer 3 V1 可以捕获格式正确的假 PMID，但如果格式罕见或错位，V1 的捕获能力取决于与检索结果集的交叉比对覆盖率。我们没有声称解决了幻觉问题——我们在每一层降低它发生的概率和影响。

---

## 6. Agent 2：OrchestrationAgent / 规划师

OrchestrationAgent 的核心任务是**把假设翻译成分析计划**。它不从固定模板生成方案——不同的 LiteratureReview 输入会产生不同的 DAG。

### 工作流程

1. 读取 LiteratureReview（假设 + 证据链 + 知识缺口）
2. LLM 对每个假设进行分类：
   - **single_gene_prognostic**：单基因与生存/表达的关联 → 小型 DAG（2-3 节点）
   - **pathway_mechanism**：涉及多分子的生物机制 → 中型 DAG（4-6 节点）
   - **multi_gene_drug**：药物敏感性或多基因特征 → 大型 DAG（5+ 节点）
3. 为每个假设匹配合适的分析方法和数据源
4. 构建 DAG（有向无环图）——哪些分析可以独立做，哪些依赖于其他分析的结果

### 反模板机制

每个 AnalysisNode **强制**包含 `rationale` 字段。LLM 必须解释：**为什么为这个假设选择这个方法和这个数据源？** 这不是"因为这是标准做法"能糊弄过去的。如果两个完全不同的假设生成了相同的 DAG，rationale 会暴露这个问题。

### 方法兼容矩阵

LLM 输出 AnalysisPlan 后，系统跑一个程序化校验：
- 这个方法在这个数据类型上能用吗？（比如 Spearman 相关不能用于二分组比较）
- 样本量够吗？（Cox 回归至少需要 30 个事件）
- 这个方法组合在 INVALID_COMBINATIONS 黑名单里吗？

不通过 → LLM 重新规划（最多 2 次）。2 次都不过 → 用最接近的合法方法替换。

**CSTB 案例中的实际表现**：3 条假设 → 4 个分析节点（差异表达 + 免疫关联 + 生存分析 + 药物筛选），每个节点都有独立的 rationale。

---

## 7. Agent 3：AnalysisAgent / 实验师

AnalysisAgent 负责把 AnalysisPlan 里的每个节点变成实际的定量结果。它使用 Think→Act→Observe 循环，但这里的"工具"是真正的数据分析函数。

### 三层数据访问策略

分析工具内部不是直接跑 R 或 Python 计算——而是根据数据可用性走三层回退：

| 层级 | 机制 | 适用分析 | 说明 |
|------|------|---------|------|
| L1 缓存查询 | 从预计算 JSON 直接读取 | DEG / Cox 回归 / KM | 已有验证结果，秒级返回 |
| L2 实时 Python | pandas + scipy.stats 实时计算 | 免疫相关性 / 药物筛选 / 基因-基因相关 | 数据在 DataFrame 里，直接算 |
| L3 F4 降级 | 缓存未命中且不支持实时 | pathway enrichment 等 | 诚实标记 degraded，不编造 |

**为什么用缓存而不是实时跑 R？** Windows 上 `Rscript -e` 会 segfault，子进程调用 R 既慢又脆弱。ITIP/CSTB 的分析结果已经过验证——缓存这些结果为 JSON，让 Agent 的"工具调用"变成查询和解释。Agent 的智能体现在**方法选择、参数决策、结果解释**，不在于重复已有的计算。

### F1-F5 失败恢复

分析不是每次都能跑通的。AnalysisAgent 把失败分成五类，每类有不同的恢复策略：

| 类型 | 触发条件 | 恢复动作 |
|------|---------|---------|
| **F1 瞬时** | API 超时、网络波动 | 自动重试 3 次 |
| **F2 参数** | 输出全 NA、方法选择错误 | 换 fallback 方法，最多 2 次 → 升级为 F4 |
| **F3 方法** | Cox PH 假设违反（Schoenfeld test p<0.05） | 降级为 KM + log-rank |
| **F4 数据** | 基因不在数据中、缓存未命中且不支持实时 | 标记 degraded，跳过该节点 |
| **F5 未知** | 任何未分类错误 | 记录日志，继续下一个节点 |

### 决策日志

每个 AnalysisResult 包含三个可追溯字段：
- **why**：为什么选这个工具 / 这个方法
- **what**：实际做了什么操作
- **result_interpretation**：LLM 对结果的解释

这意味着你可以精确追溯每一步分析决策。

---

## 8. Agent 4：ReportAgent / 主编 + Layer 4 交叉验证

ReportAgent 接收三个上游源的输出（LiteratureReview + AnalysisPlan + AnalysisResults），生成结构化报告。它在生成报告之前先对 A3 的输出做 Layer 4 交叉验证。

### Layer 4 节点 #3（A4 验证 A3）

这是最后一个交叉验证节点，检查 A3 的分析结果：
1. **统计量合理性**：HR 0.01-100、p 0-1、logFC -20~20
2. **跨节点矛盾检测**：比如 Cox 说 CSTB 是保护因素（HR<1），但差异表达说 CSTB 在肿瘤中高表达（logFC>0）——这两个结论生物学上不矛盾（高表达的保护因素也是可能的），但需要解释
3. **效应量阈值检查**：如果 Agent 声称"显著"但 |logFC| < 0.5 或 |log(HR)| < 0.2 → WARNING
4. **覆盖率**：A3 产出的所有 AnalysisResult 都出现在报告里了吗？

### 报告的强制 6 节结构

```
1. Introduction    — 研究背景和问题
2. Methods         — 数据源和分析方法
3. Results         — 每个假设的验证结果（定量 + 效应量 + CI）
4. Negative & Null Findings  — 哪些假设无法验证？哪些分析是零发现？（强制，不允跳过）
5. Discussion      — 与文献的一致性 + 局限性（至少 3 条）
6. Conclusion      — 核心发现摘要
```

**第 4 节是强制写的。** 这是为了防止选择性报告——Agent 不能只写"我们发现了 X 显著"，必须写"我们没有发现 Y""Z 分析因为数据不足而降级"。

---

## 9. Benchmark：怎么评价 Agent 做得好不好

我们说"BioMed-Agent 好"，但"好"是什么意思？需要一个标准化的评测框架来量化。

### 5 个任务

| 编号 | 任务 | 测什么 | 难度 |
|------|------|--------|------|
| T1-LIT | 文献检索与证据整合 | 检索召回率、引用准确性、证据整合质量 | hard |
| T2-GDA | 基因-疾病关联推理 | 从文献和数据库判断基因与疾病的关联强度 | medium |
| T3-DEG | 差异表达分析 | 选择统计方法、执行分析、解释结果 | medium |
| T4-SURV | 生存分析 | Cox 回归、KM 曲线、PH 假设检查 | hard |
| T5-DRUG | 药物敏感性筛选 | Spearman 相关、FDR 校正、药物分类 | hard |

### 4 维指标

| 维度 | 权重 | 测什么 | 防作弊机制 |
|------|------|--------|-----------|
| Completion | 0.15 | 任务是否完成 | 诚实拒绝=满分（防 Agent 学会"编造优于拒绝"） |
| Tool Selection | 0.25 | 方法/工具/参数选对了吗 | 方法声称验证 |
| Correctness | 0.35 | 定量结果是否在 tolerance band 内 | HR ±0.15 / logFC ±0.5或20% / rho ±0.15 |
| Safety | 0.25 | 1 - hallucination_rate | 连续惩罚函数（无 cliff effect） |

**Safety 使用连续惩罚而不是硬门槛**：

```python
penalty = 1.0 - max(0, (0.7 - safety) / 0.7)
overall = (0.15*c + 0.25*t + 0.35*r + 0.25*s) * penalty
```

硬门槛（如 `if safety < 0.7: overall *= 0.5`）的问题是 safety=0.69 和 safety=0.71 只有 0.02 差距，但一个被砍半一个原封不动——这是人为断崖。连续惩罚消除这个问题。

### 4 个 Baseline

| Baseline | 工具调用 | 检索增强 | 领域知识 | 代表什么 |
|----------|---------|---------|---------|---------|
| B1 Naive LLM | ❌ | ❌ | ❌ | 最基础水平——零-shot prompting |
| B2 ReAct | ✅ | ❌ | ❌ | 通用 Agent 框架——Think→Act→Observe + 工具 |
| B3 Simple RAG | ✅ | 单轮 | ❌ | 简单 RAG——搜一次、塞进 prompt |
| B4 Domain ReAct | ✅ | ❌ | 4 条最佳实践 | B2 + 领域知识注入 |

### T3-DEG 初步结果

完整 5×4 agent×task 矩阵需要约 150K tokens，尚未运行。以下是在 T3-DEG（差异表达分析，TCGA-COAD）上的实际数据：

| Agent | Overall Score | 幻觉标记 | 状态 |
|-------|--------------|---------|------|
| B1 Naive LLM | 0.637 | 1 | 完成（正确识别无数据访问，拒绝回答） |
| B2 ReAct | — | — | 崩溃（DeepSeek API 不支持原生 tool-calling） |
| B3 Simple RAG | 0.575 | 8 | 完成（单轮 PubMed 检索） |
| B4 Domain ReAct | — | — | 崩溃（与 B2 同因） |
| S3 Pipeline | — | — | 降级* |

> *S3 Pipeline 在 benchmark 模式下降级是预期行为。Pipeline 的 Task Router 按 task_id 分派——T3-DEG 跳过 Phase 1 LiteratureAgent 直接进入分析阶段。Pipeline 是为端到端研究问题（"研究 CSTB 在 CRC 中"）设计的，不是为单 task benchmark 拿分而优化的。

**重要**：这是单任务、单数据集（TCGA-COAD）、单次运行的结果。不可泛化。

### Ground Truth 的诚实声明

GT 不是共识金标准。每个任务的 GT 都有已知偏差：

| Task | GT 来源 | 已知偏差 |
|------|--------|---------|
| T1-LIT | PubMed 多策略检索 + 高引论文 + 时间分层 | 偏向高引旧论文（已通过 per-year-group Recall@K 缓解） |
| T2-GDA | DisGeNET + Open Targets 双源交叉 → 三级置信度 | 对研究充分的基因/疾病更完整 |
| T3-DEG | ITIP/CSTB 计算结果 + 已发表 TCGA-COAD 独立核对 | 单队列、反映 ITIP 特定分析管线（stepAIC） |
| T4-SURV | 同上 | 同上 |
| T5-DRUG | ITIP Phase E GDSC2 | 限于 GDSC2 中有数据的基因-药物对 |

所有 T3-T5 结果标记为 "exploratory, conditional on TCGA-COAD"。

---

## 10. CSTB 案例研究：完整闭环跑了一遍

我们选了 CSTB（Cystatin B，一种蛋白酶抑制剂）在结直肠癌中作为案例，从头到尾跑了一遍完整管线。

### 运行概况

- **问题**："CSTB 在结直肠癌中的预后价值和免疫浸润关联"
- **总耗时**：334 秒（约 5.6 分钟，大部分是 LLM API 延迟）
- **Token 消耗**：5,153（S3 pipeline 新增，不含 S1 独立模块）
- **Layer 4 WARNING**：2 条（均正确捕获实际数据问题）

### 四阶段分解

| Phase | Agent | 耗时 | 产出 |
|-------|-------|------|------|
| 1 | 文献探员 (LiteratureAgent) | 162.5s | 2 篇论文、3 条假设 |
| 2 | 规划师 (OrchestrationAgent) | 52.6s | 4 个分析节点 DAG |
| 3 | 实验师 (AnalysisAgent) | 76.7s | 3 完成 + 1 降级（免疫） |
| 4 | 主编 (ReportAgent) | 42.3s | 9,447 字符结构化报告 |

### 关键发现

**差异表达**：缓存数据显示 CSTB 在 CRC 肿瘤中基本没有差异表达（logFC=0.073, p=1.85×10⁻⁵）。但这与已发表文献严重矛盾——独立研究一致报告 CSTB 在 CRC 中大幅上调（logFC≈2.3）。**这是数据管线 bug，不是缓存架构的问题。** 缓存生成时可能使用了错误的标准化方法或样本分组。Layer 4 交叉验证正确检测了这个问题——效应量检查生成了 WARNING："claims significance but |logFC|=0.073 < threshold 0.5"。

**免疫相关性**：因缺乏 CIBERSORT 免疫浸润缓存数据，标记为 degraded（F4）。这是 AnalysisAgent 诚实降级机制的典型场景——数据不可用就明确标注，不编造。

**生存分析**：Cox 回归显示 CSTB 高表达有预后更差的趋势（HR=1.46, 95%CI: 0.995-2.133），但边缘不显著（p=0.053）。按 α=0.05 标准不能拒绝零假设。这是数据特征，不是系统错误。

**Layer 4 交叉验证**：两个 WARNING 都正确捕获了实际的数据问题——免疫数据缺失导致 degraded，logFC 效应量低于阈值却声称显著。这证明了交叉验证机制在"非理想数据"下确实在起作用。

### 案例研究的完整数据

所有中间产物都保存为 JSON，可独立检查和复现：
- `data/demo_output/pipeline_result_20260619_160414.json` — 完整 PipelineResult
- `data/cache/tcga_coad_deg.json` — 差异表达缓存
- `data/cache/tcga_coad_surv.json` — 生存分析缓存

---

## 11. 已知局限 — 诚实前置

这些局限在项目的 README、技术报告和所有文档中都是前置展示的，不藏在讨论章节里。

1. **单队列、单案例**：所有多组学分析基于 TCGA-COAD（n≈300）。CSTB 是唯一完整运行的案例研究。结果不可推广到其他癌种或基因。

2. **Benchmark 未全量运行**：5 task × 4 agent 的评测框架已完整实现（102 个结构测试通过），但全量 LLM 端到端运行需要约 150K tokens，仅 T3-DEG 有定量跨 Agent 对比数据。

3. **预计算缓存限制灵活性**：AnalysisAgent 只能执行缓存中存在的分析。非标准方法或未缓存的基因会降级为 F4。这是有意的架构选择——避免了 Windows Rscript segfault、消除了子进程复杂度、保持了低 demo 延迟。代价是分析范围被预计算内容限制。

4. **CSTB 缓存数据有误**：logFC=0.073 vs GT≈2.3。这是数据管线 bug（缓存生成时的标准化或样本分组错误），不是缓存架构的固有问题。根因尚未定位。

5. **DeepSeek thinking mode token 压力**：DeepSeek v4-pro 的 thinking mode 消耗大量 max_tokens，偶尔导致 JSON 截断。已设 thinking_budget_tokens=1600 作为缓解措施，但长响应仍可能触及上限。

6. **无并发**：四 Agent 管线故意设计为串行。对科研工作流而言这是自然的顺序，但挂钟时间随 LLM API 延迟线性增长。

---

## 12. 项目做了什么、没做什么

### 核心贡献

1. **四智能体协作架构**：连接文献综述与多组学分析的完整管线。文献探员 / LiteratureAgent（检索+证据整合）→ 规划师 / OrchestrationAgent（动态 DAG 规划）→ 实验师 / AnalysisAgent（多组学执行+失败恢复）→ 主编 / ReportAgent（证据整合+交叉验证+报告生成）。

2. **结构化证据链（EvidenceLink）**：数据模型级的反幻觉机制。每条科学主张必须有 supporting_pmids，4 条硬矛盾检测在 dataclass 初始化时自动执行。配合 Prompt 约束、后验验证、交叉验证、人工审阅，构成五层防线。

3. **标准化评测框架**：5 个生物医学研究任务 × 4 维指标 × 4 个控制基线的 benchmark 设计。已完整实现和测试（102 tests）。GT 构建方法透明声明，Safety 采用连续惩罚而非硬门槛。

4. **CSTB 端到端案例**：334 秒完整闭环，从文献检索到结构化报告。所有失败和降级节点诚实报告。Layer 4 交叉验证在实际数据上正确触发了 WARNING。

### 项目的边界

- **做了**：文献→假设→分析→报告的全流程架构、反幻觉五层防线、benchmark 框架设计和实现、单案例端到端验证
- **没做**（也不声称做了）：多队列验证、全量 benchmark 运行、GPU 部署、并行 Agent 执行、临床文本整合、强化学习微调

### 项目文件导航

| 想看什么 | 打开哪个文件 |
|---------|------------|
| 5 分钟了解这个项目 | `README.md` / `README_CN.md` |
| 理解系统架构和反幻觉设计 | `ARCHITECTURE.md` |
| 看 CSTB 案例的完整走读 | `CASE_STUDY.md` |
| 了解设计决策背后的理由 | `FAQ.md` |
| 了解 benchmark 框架 | `BENCHMARK.md` |
| 读完整技术报告 | `paper/report.md` |
| 看项目完成状态 | `PROGRESS.md` |
| 看所有代码 | `src/`（33 个 .py 文件） |

---

> 这份文档是对 BioMed-Agent 项目 S1-S5 全部工作的完整梳理。它不是为了面试包装而写——是为了让任何一个想理解、使用、复现这个系统的人，能在最短时间内搞清楚它做了什么、怎么做的、有什么局限。
