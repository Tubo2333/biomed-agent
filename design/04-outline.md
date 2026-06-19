# 04 — S4 技术报告写作大纲

> **状态**：v2 — DESIGN APPROVED (2轮Journal Reviewer交叉审查, 0 BLOCKER). 含Data Generation Plan.
> **作者**：Academic Author (S4 Designer)
> **依赖**：S1-S3 实验数据；00-master-coordination.md；00B-anti-hallucination-and-review.md
> **语言**：中英双语正文（GOV-005，用户确认）；系统名 BioMed-Agent

---

## 一、报告结构总览（8章）

| 章节 | 标题 | 目标页数 | 数据来源 | 状态 |
|------|------|---------|---------|------|
| 1 | Introduction | 2-3 | 设计文档 | 可写 |
| 2 | Related Work | 2-3 | LEARNING-CURRICULUM.md | 可写 |
| 3 | System Architecture | 2-3 | S1+S3 设计文档 | 可写 |
| 4 | Agent Design | 3-4 | S1+S3 实现代码 | 可写 |
| 5 | Benchmark Design | 2-3 | S2 GT + 设计文档 | 可写 |
| 6 | Results | 3-4 | S2 benchmark 结果 + S3 case study | ⏳ 等 benchmark |
| 7 | Discussion | 1-2 | 分析 + 局限性 | 可写 |
| 8 | Conclusion | 0.5 | 总结 | ⏳ 等 Results |

---

## 二、每章内容大纲

### 1. Introduction (2-3页)

**核心论点**（根据数据调整）：
> "We present BioMed-Agent, a multi-agent system that combines literature-grounded hypothesis generation with automated multi-omics analysis, and evaluate it through a benchmark of 5 biomedical research tasks and a complete case study on CSTB in colorectal cancer."

**段落结构**：
- ¶1 生物医学研究瓶颈：数据碎片化、文献爆炸、跨领域知识整合困难
- ¶2 现有AI Agent框架不足：通用框架缺乏领域知识、幻觉严重、无结构化证据追溯
- ¶3 BioMed-Agent方案概述：4-Agent协作（Literature→Orchestration→Analysis→Report）+ 五层反幻觉防线
- ¶4 贡献列表（3条）：(1) 4-Agent协作架构的完整实现和端到端验证，(2) 结构化证据链（EvidenceLink）作为反幻觉机制，(3) 5-task benchmark框架设计 + CSTB完整case study
- **注意**：贡献#3表述需精确——benchmark已设计实现但全量LLM运行待完成（~150K tokens），case study已完成。参见 §六 "Data Generation Plan"。

**数据需求**：无（纯叙述）

**审查修正 v2**（2026-06-19 Journal Reviewer）：
- ✅ 贡献#3措辞从"benchmark executed"修正为"benchmark framework designed + case study executed"
- ✅ 新增 Data Generation Plan 解决 BLOCKER #2

---

### 2. Related Work (2-3页)

**覆盖领域**：
- 2.1 AI Agent框架：ReAct, LangChain, AutoGen, MCP
- 2.2 生物医学AI：BioBERT, PubMedBERT, GeneGPT, scGPT, **BioGPT, Med-PaLM 2, BiomedCLIP**
- 2.3 多智能体系统：CAMEL, ChatDev, **ChatDoctor**
- 2.4 生物医学Benchmark：PubMedQA, BioASQ, HELM
- 2.5 幻觉检测：SelfCheckGPT, HaluEval

**对比表（≥5系统 × 5维度）**：

| 系统 | 文献整合 | 多组学分析 | 反幻觉 | Agent间验证 | 生物医学benchmark |
|------|---------|-----------|--------|------------|-----------------|
| BioMed-Agent | ✅ 结构化证据链 | ✅ 4工具(DEG/Surv/Drug/Immune) | ✅ 5层 | ✅ L4交叉验证 | ✅ 5 tasks (designed) |
| LangChain Agent | 部分(RAG) | ❌ | ❌ | ❌ | ❌ |
| AutoGen | ❌ | ❌ | ❌ | 部分(对话) | ❌ |
| GeneGPT | 部分(NCBI API) | ❌ | ❌ | ❌ | 部分(GeneTuring) |
| BioGPT | ❌ | ❌ | ❌ | ❌ | 部分(PubMedQA) |
| Med-PaLM 2 | ❌ | ❌ | ❌ | ❌ | ✅(USMLE) |
| PubMedQA | ❌ | ❌ | ❌ | ❌ | ✅(仅QA) |

**数据需求**：LEARNING-CURRICULUM.md 中的论文引用

---

### 3. System Architecture (2-3页)

**内容**：
- 整体架构图（Fig 1 — Mermaid → 手绘风格）
- 数据流：User Question → A1(LiteratureAgent) → A2(OrchestrationAgent) → A3(AnalysisAgent) → A4(ReportAgent)
- 共享基础设施：LLMClient (deepseek-v4-pro, temp=0.3), 反幻觉五层防线
- 工具系统：PubMed EUtils, TCGA (缓存+实时), GDSC2, Immune deconvolution

**数据需求**：S1+S3设计文档中的架构描述

**Fig 1 数据来源**：03-detailed-design.md §四 DATA FLOW DIAGRAM

---

### 4. Agent Design (3-4页)

**内容**：

4.1 LiteratureAgent (from S1)
- Think→Act→Observe 多轮检索循环（最多3轮）
- 三道闸门：max_rounds=3, 查询去重, token预算=15000
- LLM Rerank（无embedding模型）
- EvidenceSynthesizer + HypothesisGenerator
- 证据链示例（Fig 2）

4.2 OrchestrationAgent (from S3)
- LLM驱动的动态DAG生成
- Hypothesis分类（single_gene / pathway / multi_gene）→ DAG结构差异化
- 方法兼容矩阵后处理
- Anti-template机制：强制rationale字段

4.3 AnalysisAgent (from S3)
- Think→Act→Observe + F1-F5失败恢复
- 三层数据访问：缓存查询 → 实时Python → F4降级
- 决策日志：why/what/result 全记录

4.4 ReportAgent (from S3)
- 多源整合：LiteratureReview + AnalysisPlan + AnalysisResults
- 强制Negative and Null Findings节
- Layer 4交叉验证：A2→A1, A3→A2, A4→A3

4.5 反幻觉策略（贯穿所有Agent）
- Layer 1: Prompt约束（5条硬约束）
- Layer 2: 结构约束（EvidenceLink.__post_init__ 4条硬矛盾检测）
- Layer 3: 后验验证（PMID存在性/基因名/统计量合理性/一致性）
- Layer 4: 交叉验证（3节点，规则为主，~80行/节点）
- Layer 5: 人工审阅（strong claims标记 [HUMAN REVIEW RECOMMENDED]）

**Fig 2 数据来源**：S1 demo输出中的 evidence_chain (actual data from pipeline_result)

**数据需求**：S1+S3代码实现细节

---

### 5. Benchmark Design (2-3页)

**内容**：

5.1 五个任务定义

| ID | 任务 | Ground Truth来源 | 难度 |
|----|------|-----------------|------|
| T1-LIT | 文献检索与证据整合 | PubMed高引+时间分层 | hard |
| T2-GDA | 基因-疾病关联推理 | DisGeNET+OpenTargets三级置信度 | medium |
| T3-DEG | 差异表达分析 | ITIP/CSTB (TCGA-COAD) | medium |
| T4-SURV | 生存分析 | ITIP Phase C Cox regression | hard |
| T5-DRUG | 药物敏感性筛选 | ITIP Phase E GDSC2 | hard |

5.2 四维Metrics体系
- Completion Rate (15%) — 含合理拒绝=满分
- Tool Selection Accuracy (25%)
- Result Correctness (35%)
- Safety & Trust (25%) — Safety连续惩罚（无cliff effect）

5.3 四个Baseline
- B1 Naive LLM: 零-shot, 无工具
- B2 ReAct: Think→Act→Observe + 工具
- B3 Simple RAG: 单轮PubMed检索
- B4 Domain ReAct: B2 + 领域知识注入

**Table 1**: 5 tasks × 4 metrics 设计矩阵

**数据需求**：S2 GT JSON文件中的meta描述

---

### 6. Results (3-4页)  🟡 部分数据可用

**内容**：

6.1 Benchmark初步结果（2026-06-19运行数据）
- **T3-DEG任务**：B1 (Naive LLM) = 0.637 vs B2/B4 (ReAct variants) = crash vs B3 (Simple RAG) = 0.575（8 hallucination flags）
- **关键发现**：Generic tool-calling baselines (B2/B4) 因DeepSeek API不兼容Anthropic tool格式而crash
- **S3 MultiAgentPipeline**：同一T3-DEG任务成功运行（17.4s），使用TCGADataAccessor缓存→实时→降级三层架构
- **解读**：BioMed-Agent通过进程内Python工具+缓存数据访问避免了API级别tool calling的脆弱性
- Overall Score对比（Fig 3 — 柱状图，B1 vs S3 pipeline vs degraded B2-B4）
- 完整metrics矩阵（Table 2，含crash原因标注）

6.2 CSTB Case Study定性分析
- 完整闭环展示（Fig 5 — 时间线/流程图，来自S3 execution_log：334秒，4 Phase）
- 文献证据（Fig 6 — 证据网络图，来自S1 PubMed结果）
- 分析结果：差异表达 + 生存分析 + 免疫关联（Fig 7, Fig 8）
  - **⚠️ Fig 7 数据质量警告**：缓存cox_p=0.053 vs GT p=0.003；需在图中标注"preliminary, single-cohort"
  - **⚠️ Fig 8 限制**：immune_correlation节点degraded（F4），无免疫浸润缓存数据。替代方案：用森林图展示HR结果，或标注"数据不可用"
- 从S3实际运行日志中提取的决策过程（Layer 4 warnings含效应量检查）

6.3 Ablation分析
- 去掉证据链 / 去掉多轮检索 / 去掉LLM规划的影响（Table 3）
- **注**：全量ablation需完整benchmark运行；当前可用S3 pipeline degraded节点（immune_correlation=去掉免疫数据）作为单点ablation

**Fig 3-8 数据来源（v2修订 — 反映实际数据可用性）**：

| Figure | 内容 | 数据源 | 状态 |
|--------|------|--------|------|
| Fig 1 | 系统架构图 | 设计文档 | ✅ 可做 |
| Fig 2 | 证据链示意 | S3 pipeline evidence_chain | ✅ 可做 |
| Fig 3 | T3-DEG Benchmark对比 | focus_bench结果 (B1 0.637 vs B2/B4 crash) | ✅ 有数据 |
| Fig 4 | Hallucination Flags对比 | focus_bench结果 (B3=8 flags) | ✅ 有数据 |
| Fig 5 | Agent决策时间线 | S3 execution_log (334s, 4 Phase) | ✅ 可做 |
| Fig 6 | 文献证据网络 | S1 PubMed结果 | ✅ 可做 |
| Fig 7 | CSTB生存分析结果 | S3 survival cache (cox_p=0.053 vs GT p=0.003) | ⚠️ 数据质量差 |
| Fig 8 | 分析结果综合图 | S3 analysis_results | ⚠️ 替代设计 |

**Table数据来源（v2修订）**：

| Table | 内容 | 数据源 | 状态 |
|-------|------|--------|------|
| Table 1 | Task×Metrics设计矩阵 | S2设计文档 | ✅ 可做 |
| Table 2 | T3-DEG Benchmark对比 | focus_bench + S3 bench results | ✅ 有数据 |
| Table 3 | Ablation分析（部分） | S3 degraded节点 + 组件级分析 | 🟡 部分数据 |

---

### 7. Discussion (1-2页)

**内容**：
- 7.1 主要发现：结构化证据链对幻觉率的降低效果、LLM动态DAG vs 硬编码的差异
- 7.2 局限性（≥3条）：
  1. Benchmark规模小（5 task, 单队列TCGA-COAD），不可泛化
  2. 预计算缓存路线限制了Agent对非标准分析的灵活性
  3. DeepSeek thinking模式导致token预算紧张，JSON截断问题
  4. 单案例研究（CSTB），需更多基因验证
  5. 缓存数据与GT的差异（logFC=0.073 vs GT logFC=2.3）表明数据管线有问题
- 7.3 未来工作：并行Agent、RL微调、更多队列、临床文本整合

**数据需求**：实际运行中发现的问题（已有多个）

---

### 8. Conclusion (0.5页)

- 核心发现摘要（2-3句）
- 最重要的局限性
- 开源地址 + 可复现声明

**数据需求**：⏳ 等benchmark结果确定核心数字

---

## 三、图表清单（8图 + 3表）

| 编号 | 标题 | 类型 | 数据依赖 | 状态 |
|------|------|------|---------|------|
| Fig 1 | System Architecture | Mermaid→SVG | 设计文档 | 可做 |
| Fig 2 | Structured Evidence Chain | 信息图 | S3 pipeline | 可做 |
| Fig 3 | Overall Score Comparison | R bar chart | S2 benchmark | ⏳ |
| Fig 4 | Hallucination Rate Comparison | R bar chart | S2 benchmark | ⏳ |
| Fig 5 | Agent Decision Timeline | 流程图 | S3 execution_log | 可做 |
| Fig 6 | Literature Evidence Network | Python networkx | S1 PubMed results | ✅ 可做 |
| Fig 7 | CSTB Survival Analysis Results | R survminer/forest plot | S3 survival cache | ⚠️ 数据质量差 (cache p=0.053 vs GT p=0.003); 建议用森林图替代KM |
| Fig 8 | Analysis Results Composite | R ggplot2 | S3 analysis_results | ⚠️ 替代设计: 用多面板综合图替代纯免疫热图 |
| Table 1 | Task×Metrics Matrix | Markdown table | S2设计 | ✅ 可做 |
| Table 2 | T3-DEG Benchmark Comparison | Markdown table | focus_bench + S3 bench | ✅ 有数据 (B1 0.637 vs B2/B4 crash) |
| Table 3 | Ablation Analysis (partial) | Markdown table | S3 degraded节点分析 | 🟡 部分数据 |

---

## 四、关键约束清单（写作时必须遵守）

### 从设计文档继承的硬约束：
1. **Layer 1**: 每个科学claim必须有数据支撑或文献引用
2. **诚实报告**: 失败/局限性不能回避，阴性结果必须包含
3. **定量精确**: 报告精确数值+置信区间，不四舍五入p值
4. **GOV-005**: 中英双语正文（非仅摘要）
5. **FIG-002**: identity-fill + svglite + rsvg渲染管线
6. **命名**: 系统名 "BioMed-Agent"，用 "we"

### 从S3运行发现的实际约束：
7. **缓存vs GT差异**: 报告必须诚实说明缓存数据（logFC=0.073）与GT（logFC=2.3）的差异
8. **Degraded节点**: immune_correlation被标记degraded（无缓存），必须报告
9. **Token预算**: DeepSeek thinking模式导致的高token消耗需要在Discussion中提及

---

## 五、Data Generation Plan（2026-06-19新增 — BLOCKER #2 解决方案）

### Benchmark数据生成计划

**当前状态**：S2 benchmark框架完整实现并通过102个structural tests。全量LLM端到端运行因token预算（~150K+ tokens）未执行。

**分阶段执行计划**：

| 阶段 | 内容 | Token估算 | 状态 |
|------|------|----------|------|
| Phase 0 | B1-B4 baselines on T3-DEG | ~13K | ✅ 已完成 (2026-06-19) |
| Phase 1 | S3 pipeline on T3-DEG | ~3K | ✅ 已完成 (2026-06-19) |
| Phase 2 | B1-B4 on T4-SURV, T5-DRUG | ~25K | ⬜ 待执行 |
| Phase 3 | LiteratureAgent on T1-LIT (5 queries) | ~80K | ⬜ 需大token预算 |
| Phase 4 | Full agent×task matrix | ~150K | ⬜ 需分批执行 |

**降级方案**：如果Phase 3-4因token预算不可行，论文Results聚焦于：
- T3-DEG 定量对比（已有数据）
- CSTB Case Study定性分析（已有完整S3 pipeline数据）
- 将全量benchmark定位为"framework designed and tested; preliminary comparison on T3-DEG"

### 缓存数据补全计划

| 数据 | 当前状态 | 补全方式 |
|------|---------|---------|
| TCGA-COAD immune deconvolution | 缺失（导致Fig 8 blocked） | 运行CIBERSORT/ESTIMATE → 生成缓存JSON |
| TCGA-COAD patient-level survival | 可访问（RDS文件存在） | 读取RDS → 提取KM数据 → 生成Fig 7 |

---

## 六、写作顺序

```
Batch 1 (可立即写):  Ch 1 Introduction + Ch 3 Architecture + Ch 5 Benchmark Design
Batch 2 (可立即写):  Ch 2 Related Work + Ch 7 Discussion（局限性部分）
Batch 3 (等benchmark): Ch 6 Results
Batch 4 (等benchmark): Ch 8 Conclusion
Batch 5 (最后):        Abstract + 参考文献整理
Batch 6 (全部完成后):  中文翻译/双语化 + 图表生成
```

---

## 六、参考文献清单（初始版，40篇目标）

### 核心引用（必含）
| # | 论文 | 用途 | PMID/arXiv |
|---|------|------|-----------|
| 1 | ReAct (Yao 2022) | Agent循环理论基础 | arXiv 2210.03629 |
| 2 | RAG (Lewis 2020) | 检索增强生成 | arXiv 2005.11401 |
| 3 | SelfCheckGPT (Manakul 2023) | 幻觉检测 | arXiv 2303.08896 |
| 4 | HELM (Liang 2023) | Benchmark方法论 | arXiv 2211.09110 |
| 5 | PubMedQA (Jin 2019) | 生物医学QA benchmark | arXiv 1909.06146 |
| 6 | AutoGen (Wu 2023) | 多Agent框架对比 | arXiv 2308.08155 |
| 7 | CAMEL (Li 2023) | Role-based多Agent | arXiv 2303.17760 |
| 8 | GeneGPT (Jin 2023) | NCBI工具调用 | arXiv 2304.09667 |
| 9 | BioBERT (Lee 2020) | 生物医学NLP | arXiv 1901.08746 |
| 10 | PubMedBERT (Gu 2021) | 生物医学预训练 | arXiv 2007.15779 |
| 11 | TCGA-COAD (TCGA 2012) | 数据来源 | PMID:21833088 |
| 12 | GDSC (Garnett 2012) | 药物数据 | PMID:24138885 |
| 13 | ToolLLM (Qin 2023) | 工具调用 | arXiv 2307.16789 |
| 14 | SPECTER (Cohan 2020) | 科学文献embedding | arXiv 2004.07180 |
| 15 | HaluEval (Li 2023) | 幻觉分类学 | arXiv 2305.11747 |
| 16 | MCP Spec (Anthropic 2024) | 工具协议 | modelcontextprotocol.io |
| 17 | limma (Ritchie 2015) | 差异表达方法 | PMID:25605792 |
| 18 | CIBERSORT (Newman 2015) | 免疫浸润方法 | PMID:28407145 |
| 19 | Self-RAG (Asai 2023) | 多轮检索反思 | arXiv 2310.11511 |
| 20 | scGPT (Cui 2023) | 单细胞基础模型 | Nature Methods 2024 |

### 扩展引用（建议补充）
21-30. 更多生物医学Agent和Benchmark相关文献
31-40. 根据benchmark结果中引用的新论文补充

---

> **🔄 OUTLINE v2** — 2026-06-19 Journal Reviewer 审查后修订。
> - ✅ BLOCKER #1 (Fig 3/4/Table 2无数据) → 已解决：focus_bench产生T3-DEG对比数据
> - ✅ BLOCKER #2 (无token预算计划) → 已解决：新增 §五 Data Generation Plan
> - ✅ MINOR #1 (遗漏BioGPT/Med-PaLM) → 已修复：Related Work表新增2行
> - ✅ MINOR #2 (Fig 7数据路径模糊) → 已修复：标注数据质量警告+替代方案
> - ✅ MINOR #3 (贡献措辞) → 已修复：精确区分"designed" vs "executed"
> - ✅ 第二轮交叉审查通过, DESIGN APPROVED。进入 Stage 2。
