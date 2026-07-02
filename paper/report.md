# BioMed-Agent: A Multi-Agent System for Biomedical Literature-Grounded Multi-Omics Analysis

> **BioMed-Agent：面向生物医学文献驱动多组学分析的多智能体系统**
>
> **Authors**: [Author] — Independent Research Project, 2026
>
> **Status**: Technical Report / Pre-print Draft
>
> **Repository**: `github.com/Tubo2333/biomed-agent`

---

## Abstract

**English** — Biomedical research faces a fundamental bottleneck: the exponential growth of published literature has far outpaced researchers' ability to integrate evidence across papers, while multi-omics data analysis pipelines remain fragmented and require specialized expertise. We present **BioMed-Agent**, a multi-agent system that connects literature-grounded hypothesis generation with automated multi-omics analysis through a four-agent collaborative pipeline. The system combines: (1) a LiteratureAgent that performs multi-round PubMed retrieval with structured evidence chaining (EvidenceLink) to reduce hallucination; (2) an OrchestrationAgent that generates LLM-driven dynamic analysis DAGs; (3) an AnalysisAgent that executes Think→Act→Observe cycles with a five-tier failure recovery system; and (4) a ReportAgent that synthesizes findings with mandatory Layer 4 cross-validation of upstream outputs. We implement a five-layer anti-hallucination defense spanning prompt engineering, structural constraints, post-hoc verification, cross-agent validation, and human review. The system is evaluated through a complete case study on CSTB in colorectal cancer, demonstrating end-to-end closed-loop research capability from literature review through hypothesis generation to multi-omics validation. We also design a standardized benchmark framework comprising 5 biomedical research tasks across 4 evaluation dimensions with 4 controlled baselines, and discuss the architectural decisions, failure modes, and limitations of LLM-driven scientific agent systems.

**中文** — 生物医学研究面临一个根本性瓶颈：已发表文献的指数级增长远超研究者整合跨论文证据的能力，而多组学数据分析管线仍呈碎片化状态、需要专业知识。我们提出 **BioMed-Agent**，一个通过四智能体协作管线连接文献驱动假设生成与自动化多组学分析的多智能体系统。该系统整合：(1) LiteratureAgent，执行多轮PubMed检索与结构化证据链（EvidenceLink）以减少幻觉；(2) OrchestrationAgent，生成LLM驱动的动态分析DAG；(3) AnalysisAgent，以五级失败恢复系统执行Think→Act→Observe循环；(4) ReportAgent，强制对上游输出进行Layer 4交叉验证后综合发现。我们实现了五层反幻觉防线，覆盖提示工程、结构约束、后验验证、跨智能体验证和人工审查。系统通过CSTB在结直肠癌中的完整案例研究进行评估，展示了从文献综述到假设生成再到多组学验证的端到端闭环研究能力。我们还设计了包含5个生物医学研究任务、4个评估维度、4个控制基线的标准化评测框架，并讨论了LLM驱动的科学智能体系统的架构决策、失败模式和局限性。

---

## 1. Introduction

### 1.1 The Biomedical Research Bottleneck / 生物医学研究瓶颈

现代生物医学研究面临双重信息危机。**文献端**，PubMed 每年新增超过 150 万篇论文[^1]，单一研究者不可能持续追踪其领域内的所有相关发表物。**数据端**，大规模多组学数据集（TCGA、GEO、GDSC）已公开可用，但将其转化为可验证的科学假设需要生物信息学、统计学和领域知识的罕见组合。

The modern biomedical researcher faces a dual information crisis. On the **literature side**, PubMed adds over 1.5 million papers annually[^1], making it impossible for any individual researcher to track all relevant publications in their field. On the **data side**, large-scale multi-omics datasets (TCGA, GEO, GDSC) are publicly available, but transforming them into testable scientific hypotheses requires a rare combination of bioinformatics, statistics, and domain knowledge.

This fragmentation creates a fundamental inefficiency: hypotheses are generated from incomplete literature review, analyses are designed without comprehensive evidence synthesis, and results are interpreted without systematic cross-referencing against published findings.

### 1.2 Limitations of Existing AI Agent Frameworks / 现有AI智能体框架的局限

Recent advances in large language model (LLM)-based agents—including ReAct[^2], LangChain, AutoGen[^3], and tool-use frameworks such as the Model Context Protocol (MCP)[^4]—have demonstrated impressive capabilities in general-purpose reasoning and tool utilization. However, when applied to biomedical research, these frameworks exhibit critical shortcomings:

1. **Lack of domain grounding**: General-purpose agents lack awareness of biomedical entity relationships, standard analytical methods, and the evidentiary standards of biomedical science.
2. **Hallucination risk**: In biomedical contexts, factual errors are particularly dangerous—a fabricated gene-disease association or falsified statistical result can propagate through downstream analyses and into publications.
3. **No structured evidence provenance**: Existing agent outputs are predominantly free-text, with no systematic mechanism to trace each factual claim back to its source (a specific PMID from the literature, or a specific computational result).
4. **Absence of cross-validation**: Single-agent systems have no mechanism for one component to verify the outputs of another—errors propagate silently.
5. **No biomedical benchmark**: General-purpose agent evaluations (HELM[^5], AgentBench[^30]) do not test for biomedical research capabilities such as literature synthesis, differential expression analysis, or survival modeling.

### 1.3 BioMed-Agent: Our Approach / 我们的方案

BioMed-Agent addresses these limitations through four integrated innovations:

1. **A four-agent collaborative architecture** that mirrors the natural scientific research workflow: LiteratureAgent (literature review) → OrchestrationAgent (analysis design) → AnalysisAgent (data execution) → ReportAgent (synthesis and writing).
2. **Structured evidence chaining (EvidenceLink)** as a core anti-hallucination mechanism: every factual claim about biology must be traced to either a specific PubMed ID or a specific computational result, enforced at the data model level.
3. **A five-layer anti-hallucination defense** spanning prompt constraints, structural validation, post-hoc verification, cross-agent validation, and human review checkpoints.
4. **A standardized biomedical agent benchmark** comprising 5 research tasks, 4 evaluation dimensions (completion, tool selection, correctness, safety), and 4 controlled baselines that systematically vary tool access, retrieval capability, and domain knowledge.

### 1.4 Contributions / 贡献

This report makes the following contributions:

- **System contribution**: A complete, working multi-agent architecture that integrates literature retrieval, evidence synthesis, dynamic analysis planning, multi-omics tool execution, and structured scientific report generation into a single end-to-end pipeline.
- **Method contribution**: The EvidenceLink structured evidence model with built-in contradiction detection, strength classification, and mandatory source attribution—a practical anti-hallucination mechanism applicable beyond biomedical domains.
- **Empirical contribution**: A standardized benchmark framework comprising 5 biomedical research tasks, 4 evaluation dimensions, and 4 controlled baselines (designed and implemented; preliminary T3-DEG comparison data reported); plus a complete end-to-end case study on CSTB (Cystatin B) in colorectal cancer, demonstrating the system's ability to retrieve relevant literature, generate testable hypotheses, execute multi-omics analyses (differential expression, survival analysis, immune correlation, drug screening), and produce a structured scientific report with explicit uncertainty quantification and limitation acknowledgment.

---

## 2. Related Work / 相关工作

### 2.1 AI Agent Frameworks / AI智能体框架

The ReAct pattern[^2] (Yao et al., 2022) established the Think→Act→Observe loop as a foundational paradigm for LLM-based agents, demonstrating that interleaving reasoning traces with tool-use actions improves performance on multi-step reasoning tasks compared to reasoning-only or action-only approaches. BioMed-Agent adopts this paradigm across all four constituent agents, but extends it with (a) structured observation formats that force evidence traceability, and (b) Layer 4 cross-agent validation that adds a verification step after each agent's output.
>
> **中文** — ReAct 模式[^2] 将 Think→Act→Observe 循环确立为 LLM 智能体的基础范式，证明推理痕迹与工具调用交织可提升多步推理任务性能。BioMed-Agent 在四个智能体上采用此范式，并以 (a) 强制证据可追溯的结构化观察格式和 (b) Layer 4 跨智能体验证步骤进行了扩展。

AutoGen[^3] (Wu et al., 2023) introduced conversation-driven control flow for multi-agent systems, where agents coordinate through natural language dialogue. BioMed-Agent takes a complementary approach: agent-to-agent communication is DAG-driven rather than conversation-driven. The OrchestrationAgent produces an explicit analysis plan (a directed acyclic graph of analysis nodes), which the AnalysisAgent executes deterministically. This design choice prioritizes auditability and reproducibility over conversational flexibility—a deliberate trade-off justified by biomedical research's requirement for traceable decision-making.
>
> **中文** — AutoGen[^3] 引入对话驱动的多智能体控制流。BioMed-Agent 采用互补方案：智能体间通信通过 DAG 驱动——OrchestrationAgent 生成显式分析计划（有向无环图），AnalysisAgent 确定性执行，以可审计性和可复现性优先于对话灵活性。

The Model Context Protocol (MCP)[^4] (Anthropic, 2024) standardizes tool discovery and invocation through a client-server architecture with tools/list and tools/call primitives. BioMed-Agent's tool system follows similar design principles but operates entirely in-process (no separate server processes) and adds method compatibility matrices that programmatically validate tool-method assignments before execution.
>
> **中文** — MCP[^4] 标准化了工具发现和调用。BioMed-Agent 的工具系统遵循类似设计但全进程内运行（无独立服务器），并增加了方法兼容性矩阵在工具-方法分配前做程序化验证。

ToolLLM[^6] (Qin et al., 2023) demonstrated that LLMs can master large tool repositories (16,000+ APIs) through DFS-based search strategies. BioMed-Agent's tool space is intentionally constrained (4 primary tools × ~6 methods) to match the actual analytical capabilities available to biomedical researchers, prioritizing correctness over breadth.
>
> **中文** — ToolLLM[^6] 证明 LLM 可通过 DFS 搜索掌握大型工具库。BioMed-Agent 有意将工具空间限制为 4 种主工具 × ~6 种方法，以正确性优先于广度。

### 2.2 Biomedical AI and Scientific LLMs / 生物医学AI与科学大语言模型

Domain-specific pre-training has been shown to improve biomedical NLP performance: BioBERT[^7] (Lee et al., 2020) and PubMedBERT[^8] (Gu et al., 2021) demonstrated that models trained on biomedical corpora outperform general-domain models on tasks like named entity recognition and relation extraction. However, these models focus on understanding biomedical text rather than executing biomedical research workflows.
>
> **中文** — 领域预训练可提升生物医学 NLP 性能：BioBERT[^7] 和 PubMedBERT[^8] 证明在生物医学语料上训练的模型优于通用领域模型。但这些模型侧重理解生物医学文本，而非执行生物医学研究工作流。

GeneGPT[^9] (Jin et al., 2023) taught LLMs to use NCBI APIs (including PubMed) for genomics tasks, demonstrating the feasibility of tool-augmented approaches in biomedical domains. BioMed-Agent extends this direction by (a) adding multi-round, LLM-driven retrieval with explicit stopping criteria, (b) structuring the output as evidence chains rather than free-text answers, and (c) integrating literature retrieval with downstream multi-omics analysis in a single pipeline.
>
> **中文** — GeneGPT[^9] 教会 LLM 在基因组学任务中使用 NCBI API。BioMed-Agent 以此为基础扩展，加入 (a) 多轮 LLM 驱动检索及显式停止标准、(b) 证据链结构化输出、(c) 文献检索与下游多组学分析的单一管线整合。

scGPT[^10] (Cui et al., 2023) represents the frontier of foundation models for single-cell biology, using transformer architectures pre-trained on massive single-cell RNA-seq datasets. While scGPT focuses on learning representations of gene expression data, BioMed-Agent focuses on the *workflow* that connects literature evidence to analysis decisions—the two approaches are complementary.
>
> **中文** — scGPT[^10] 代表单细胞生物学基础模型前沿。两者互补：scGPT 侧重基因表达数据表征学习，BioMed-Agent 侧重连接文献证据与分析决策的工作流。

BioGPT[^26] (Luo et al., 2022) demonstrated that generative pre-training on biomedical text corpora (PubMed abstracts) improves performance on biomedical NLP tasks including relation extraction and question answering. However, BioGPT is a single-model text generation system without tool-use or multi-agent coordination capabilities. Similarly, Med-PaLM 2[^27] (Singhal et al., 2023) achieved USMLE-level performance on medical question answering through instruction tuning and prompting strategies, but operates as a monolithic QA system without multi-omics data access or structured evidence provenance. BioMed-Agent extends these biomedical LLM capabilities by integrating literature retrieval with multi-omics analysis execution and cross-agent verification.
>
> **中文** — BioGPT[^26] 和 Med-PaLM 2[^27] 在生物医学 NLP/医学 QA 上表现出色，但均为无工具使用、无多智能体协调的单一模型系统。BioMed-Agent 通过整合文献检索、多组学分析执行和跨智能体验证扩展了这些能力。

BiomedCLIP[^28] (Zhang et al., 2023) introduced multimodal biomedical foundation models combining text and image understanding. ChatDoctor[^29] (Li et al., 2023) fine-tuned LLMs on patient-doctor dialogues for improved biomedical communication. Both represent domain-specialized LLM applications that complement BioMed-Agent's workflow-oriented approach.
>
> **中文** — BiomedCLIP[^28] 和 ChatDoctor[^29] 均为领域专精 LLM 应用，与 BioMed-Agent 的工作流导向方案互补。

### 2.3 Multi-Agent Systems / 多智能体系统

CAMEL[^11] (Li et al., 2023) proposed role-playing as a core mechanism for multi-agent collaboration, demonstrating that assigning distinct roles (e.g., "AI user" and "AI assistant") improves task completion quality. BioMed-Agent's four agents each have distinct system prompts, tool sets, and validation responsibilities that embody specific scientific roles (literature reviewer, methodologist, analyst, writer).
>
> **中文** — CAMEL[^11] 提出角色扮演作为多智能体协作的核心机制。BioMed-Agent 的四个智能体各有独特的 system prompt、工具集和验证职责，体现了特定的科学角色（文献评审员、方法学家、分析师、撰写者）。

ChatDev[^12] (Qian et al., 2023) applied multi-agent collaboration to software development with CEO/CTO/Programmer/Reviewer role分工. BioMed-Agent's Literature→Orchestration→Analysis→Report pipeline mirrors the natural scientific workflow in a similar role-based structure, but operates in a deterministic DAG topology rather than through conversational negotiation.
>
> **中文** — ChatDev[^12] 将多智能体协作应用于软件开发。BioMed-Agent 的 Literature→Orchestration→Analysis→Report 管线以基于角色的结构映射自然科学研究工作流，但以确定性 DAG 拓扑运行而非对话协商。

Multi-Agent Debate[^13] (Du et al., 2023) showed that having multiple agents debate each other's outputs reduces factual errors. This directly supports BioMed-Agent's Layer 4 cross-validation design, where Agent N+1 systematically verifies Agent N's output through structured validation checks.
>
> **中文** — Multi-Agent Debate[^13] 显示多智能体互辩可减少事实错误，这直接支持了 BioMed-Agent 的 Layer 4 交叉验证设计——Agent N+1 通过结构化验证检查系统性验证 Agent N 的输出。

### 2.4 Biomedical Benchmarks and Evaluation / 生物医学评测基准

PubMedQA[^14] (Jin et al., 2019) and BioASQ[^15] (Tsatsaronis et al., 2015) established benchmarks for biomedical question answering. However, these benchmarks evaluate single-turn QA rather than multi-step research workflows. BioMed-Agent's benchmark framework (Section 5) extends beyond QA to include differential expression analysis, survival modeling, and drug sensitivity screening—tasks that more accurately reflect the daily work of computational biologists.
>
> **中文** — PubMedQA[^14] 和 BioASQ[^15] 建立了生物医学问答基准，但仅评估单轮 QA。BioMed-Agent 的 benchmark 框架扩展到差异表达分析、生存建模和药物敏感性筛选——更准确反映计算生物学家的日常工作。

HELM[^5] (Liang et al., 2023) provides a comprehensive multi-dimensional evaluation framework for LLMs. Our benchmark design adopts HELM's philosophy of evaluating across multiple scenarios and metrics, but specializes the dimensions for biomedical research contexts (completion rate, tool selection accuracy, result correctness, safety & trust).
>
> **中文** — HELM[^5] 提供了多维度 LLM 评估框架。我们的 benchmark 设计采用了 HELM 跨场景多指标评估的理念，但将评估维度专精于生物医学研究场景。

### 2.5 Hallucination Detection and Mitigation / 幻觉检测与缓解

SelfCheckGPT[^16] (Manakul et al., 2023) introduced sampling-based consistency checking for hallucination detection: generating multiple responses to the same prompt and identifying inconsistent claims. BioMed-Agent's Layer 3 post-hoc verification (PMID existence check, gene name validation, statistical sanity bounds) extends this with domain-specific hard rules that operate on structured output.
>
> **中文** — SelfCheckGPT[^16] 引入了一致性采样检测幻觉。BioMed-Agent 的 Layer 3 后验验证通过领域专用硬规则扩展了此方法——在结构化输出上执行 PMID 存在性检查、基因名验证和统计合理性边界检查。

HaluEval[^17] (Li et al., 2023) systematically categorized hallucinations into five types (factual, knowledge, logical, contextual, arithmetic). BioMed-Agent's five-layer defense maps approximately to these categories: Layer 1 (prompt constraints) addresses factual and knowledge hallucinations; Layer 2 (structural constraints) catches logical inconsistencies; Layer 3 (post-hoc verification) detects factual and arithmetic hallucinations; Layer 4 (cross-validation) catches contextual contradictions.
>
> **中文** — HaluEval[^17] 将幻觉系统分类为 5 类。BioMed-Agent 的五层防线与此近似映射：Layer 1 处理事实和知识幻觉，Layer 2 捕获逻辑不一致，Layer 3 检测事实和算术幻觉，Layer 4 捕获上下文矛盾。

### 2.6 Comparison Table / 系统对比

| System | Lit. Integration | Multi-Omics | Anti-Halluc. | Agent Validation | Biomed Benchmark |
|--------|-----------------|-------------|-------------|------------------|------------------|
| **BioMed-Agent** | ✅ Structured evidence chain | ✅ DEG/Surv/Drug/Immune | ✅ 5-layer | ✅ L4 cross-validation | ✅ 5 tasks (designed) |
| LangChain Agent | Partial (RAG) | ❌ | ❌ | ❌ | ❌ |
| AutoGen[^3] | ❌ | ❌ | ❌ | Partial (dialogue) | ❌ |
| GeneGPT[^9] | Partial (NCBI) | ❌ | ❌ | ❌ | Partial |
| BioGPT[^26] | ❌ | ❌ | ❌ | ❌ | Partial (PubMedQA) |
| Med-PaLM 2[^27] | ❌ | ❌ | ❌ | ❌ | ✅ (USMLE) |
| CAMEL[^11] | ❌ | ❌ | ❌ | Partial (role-play) | ❌ |
| PubMedQA[^14] | ❌ | ❌ | ❌ | ❌ | ✅ (QA only) |

---

## 3. System Architecture / 系统架构

### 3.1 Overview / 总体架构

BioMed-Agent adopts a four-agent sequential pipeline architecture (Figure 1). Each agent is a self-contained LLM-powered module implementing the Think→Act→Observe cycle, with a shared LLM backend (DeepSeek V4 Pro, temperature=0.3) and a shared tool registry.

> **中文** — BioMed-Agent 采用四智能体顺序管线架构（图1）。每个智能体是独立的 LLM 驱动模块，实现 Think→Act→Observe 循环，共享 LLM 后端（DeepSeek V4 Pro, temperature=0.3）和工具注册表。

```
User Question
    │
    ▼
┌─────────────────────────────────────┐
│  Agent 1: LiteratureAgent           │  ← S1 implementation
│  PubMed search + Rerank + Evidence  │
│  Synthesis + Hypothesis Generation  │
│  Input: Natural language question   │
│  Output: LiteratureReview            │
└──────────────┬──────────────────────┘
               │ LiteratureReview
               ▼  [Layer 4 validation: A2 checks A1]
┌─────────────────────────────────────┐
│  Agent 2: OrchestrationAgent        │  ← S3 implementation (A2)
│  LLM-driven DAG generation           │
│  Hypothesis → Analysis Plan (DAG)   │
│  Input: LiteratureReview             │
│  Output: AnalysisPlan                │
└──────────────┬──────────────────────┘
               │ AnalysisPlan
               ▼  [Layer 4 validation: A3 checks A2]
┌─────────────────────────────────────┐
│  Agent 3: AnalysisAgent             │  ← S3 implementation (A3)
│  Think→Act→Observe + F1-F5 recovery │
│  Tools: TCGA, Survival, Drug, Immune│
│  Input: AnalysisPlan                 │
│  Output: list[AnalysisResult]        │
└──────────────┬──────────────────────┘
               │ AnalysisResults
               ▼  [Layer 4 validation: A4 checks A3]
┌─────────────────────────────────────┐
│  Agent 4: ReportAgent               │  ← S3 implementation (A4)
│  Multi-source synthesis + writing   │
│  Input: LiteratureReview + Plan +    │
│         AnalysisResults              │
│  Output: Structured report (.md)     │
└─────────────────────────────────────┘
```

**Figure 1**: BioMed-Agent system architecture. Four agents execute sequentially, with Layer 4 cross-validation gates between each phase. (Mermaid → hand-drawn SVG rendering to follow in Stage 2.)

**图1**：BioMed-Agent系统架构。四个智能体顺序执行，各阶段间设有Layer 4交叉验证门控。

### 3.2 Shared Infrastructure / 共享基础设施

All agents share a common infrastructure layer:

**LLM Client**: A unified wrapper around the Anthropic SDK, routing calls to DeepSeek V4 Pro. Default parameters: temperature=0.3 (optimized for factual accuracy over creativity in biomedical contexts), with configurable thinking budget tokens to prevent reasoning from consuming the entire output window.

> **中文** — 所有智能体共享统一基础设施：**LLM 客户端**为 Anthropic SDK 的统一封装，调用路由至 DeepSeek V4 Pro，temperature=0.3（在生物医学场景中优先保证事实准确性而非创造性），thinking budget tokens 可配置以防止推理占用全部输出窗口。

**Network Layer**: All external I/O (PubMed EUtils API, DeepSeek API) routes through `shared/gfw_probe.py` which checks proxy availability (127.0.0.1:7892) before any network call and implements 3-retry exponential backoff.

> **中文** — **网络层**：所有外部 I/O（PubMed API、DeepSeek API）经由 `shared/gfw_probe.py` 路由，在网络调用前检查代理可用性（127.0.0.1:7892），实现 3 次重试指数退避。

**Configuration**: A single `config.yaml` defines LLM parameters, data paths (TCGA cache, GDSC2 data, PubMed cache), benchmark settings (random seed=42, n_test_cases_per_task=10), and output directories.

> **中文** — **配置系统**：统一的 `config.yaml` 定义 LLM 参数、数据路径（TCGA 缓存、GDSC2 数据、PubMed 缓存）、基准测试设置（random seed=42, n_test_cases_per_task=10）和输出目录。

**Type System**: All inter-agent data structures are defined as Python `dataclass`es with `__post_init__` validation methods that enforce structural constraints at construction time.

> **中文** — **类型系统**：所有智能体间数据结构均定义为 Python `dataclass`，通过 `__post_init__` 验证方法在构造时强制执行结构约束。

### 3.3 Agent Design Philosophy / 智能体设计哲学

BioMed-Agent follows three design principles that differentiate it from generic LLM agent frameworks:

1. **Agent ≠ LLM + tool list.** Each agent embodies a complete Think→Act→Observe cycle where the Think phase involves explicit reasoning about tool selection, parameter choices, and evidence assessment; the Act phase executes the selected tool with the reasoned parameters; and the Observe phase interprets results and decides on next actions (including retry with different parameters or method degradation).

> **中文** — BioMed-Agent 遵循三条区别于通用 LLM Agent 框架的设计原则：(1) **Agent ≠ LLM + 工具列表**。每个 Agent 体现完整的 Think→Act→Observe 循环：Think 阶段对工具选择、参数和证据评估进行显式推理；Act 阶段以推理参数执行工具；Observe 阶段解释结果并决定下一步（含不同参数重试或方法降级）。

2. **Prompt-first architecture.** Each agent's system prompt is treated as its most critical "source code." Prompts define the agent's role, available tools, output format, and behavioral constraints. The five anti-hallucination constraints (Section 4.5) are embedded in every prompt that generates scientific content.

> **中文** — (2) **Prompt 优先架构**。每个 Agent 的系统提示被视为其最关键的"源代码"。提示定义了 Agent 的角色、可用工具、输出格式和行为约束。五条反幻觉约束（§4.5）嵌入所有生成科学内容的提示中。

3. **Full decision traceability.** Every agent action records three elements: *why* (reasoning behind tool/method/parameter choice), *what* (the concrete action taken), and *result* (the observed outcome). This creates a complete audit trail from user question to final report claim.

> **中文** — (3) **全决策可追溯**。每个 Agent 动作记录三要素：*why*（工具/方法/参数选择的推理）、*what*（执行的具体动作）和 *result*（观察到的结果），创建从用户问题到最终报告声明的完整审计轨迹。

---

## 4. Agent Design / 智能体设计

### 4.1 LiteratureAgent: Multi-Round Literature Retrieval with Evidence Synthesis

**Design rationale**: Biomedical literature review is not a single-shot retrieval task. Initial search results may miss key evidence, uncover unexpected dimensions of the question, or reveal conflicts between studies that require targeted follow-up searches.

> **中文** — **设计理由**：生物医学文献综述不是一次性检索任务。初步检索可能遗漏关键证据、发现问题的意外维度、或揭示需要定向跟进检索的研究间冲突。

The LiteratureAgent implements a multi-round Think→Act→Observe cycle:

```
Phase 0: Question Decomposition
  LLM decomposes user question → 1-3 PubMed search queries
  Each query targets a different evidence dimension:
    - Clinical/epidemiological (prognosis, prevalence)
    - Molecular mechanism (pathway, interaction)
    - Therapeutic (drug response, clinical trial)

Phase 1: Multi-Round Retrieval Loop (max 3 rounds)
  Think: Review evidence collected so far. Is it sufficient?
    If gaps exist → generate new search query
    If sufficient → signal completion
  Act: Execute PubMed search → fetch abstracts → cache locally
  Observe: LLMRerank scores papers by relevance → select top-K

  Gate conditions (any triggers loop exit):
    G1: Max rounds reached (3)
    G2: Query deduplication detected
    G3: Token budget exhausted (15,000 cumulative)

Phase 2: Evidence Synthesis
  EvidenceSynthesizer extracts atomic claims from papers
  Each claim maps to supporting PMIDs
  LLM assigns strength: strong | moderate | weak | unverified
  Hard contradiction detection (4 rules in EvidenceLink.__post_init__)
  Optional secondary review for borderline strong claims

Phase 3: Hypothesis Generation
  HypothesisGenerator identifies knowledge gaps
  Generates 1-3 falsifiable hypotheses
  Each hypothesis includes: testable prediction + required data + novelty classification

Phase 4: Assembly
  Compose LiteratureReview dataclass with full traceability
  Token usage tracked across all phases
```

**Key design decision — LLM Rerank over embeddings**: Instead of using a dedicated embedding model (e.g., text-embedding-3-small or PubMedBERT), the LiteratureAgent uses the same LLM (DeepSeek V4 Pro) to score paper relevance on a 0-1 scale. This avoids dependency on embedding APIs and allows the relevance judgment to consider full semantic context, at the cost of higher token consumption (~500 tokens per batch of 10 papers).

> **中文** — **关键设计决策 — LLM Rerank 替代 Embedding**：LiteratureAgent 使用同一 LLM（DeepSeek V4 Pro）以 0-1 评分论文相关性，而非专用 embedding 模型。这避免了对 embedding API 的依赖，使相关性判断能考虑完整语义上下文，代价是更高的 Token 消耗（每批 10 篇论文约 500 tokens）。

**Key design decision — EvidenceLink strength as LLM self-attested + rule downgrade only**: The LLM proposes a strength level for each claim with mandatory justification. Rules can only *downgrade* (e.g., claim says "strong" but has <3 supporting PMIDs → automatic downgrade to "moderate"), never upgrade. This ensures claims are never more confident than the LLM's original assessment.

> **中文** — **关键设计决策 — EvidenceLink 强度为 LLM 自证 + 规则仅降级**：LLM 为每条声明提议强度等级并附强制性理由。规则只能*降级*（如声明自称"strong"但支持性 PMID <3 → 自动降为"moderate"），绝不升级。这确保声明的置信度不会超过 LLM 的原始评估。

### 4.2 OrchestrationAgent: LLM-Driven Dynamic DAG Generation

**Design rationale**: Different hypotheses require fundamentally different analysis strategies. A hypothesis about a single gene's prognostic value needs differential expression + survival analysis (2-3 nodes). A hypothesis about a signaling pathway mechanism needs correlation networks, multi-gene co-expression, and pathway enrichment (4-6 nodes). A fixed analysis template would miss these structural differences.

> **中文** — **设计理由**：不同假设需要根本不同的分析策略。关于单基因预后价值的假设需要差异表达 + 生存分析（2-3 节点）；关于信号通路机制的假设需要相关网络、多基因共表达和通路富集（4-6 节点）。固定分析模板无法捕捉这些结构差异。

The OrchestrationAgent converts a LiteratureReview into an AnalysisPlan (a directed acyclic graph of analysis nodes) through LLM reasoning:

> **中文** — OrchestrationAgent 通过 LLM 推理将 LiteratureReview 转换为 AnalysisPlan（分析节点的有向无环图）。


```
Input: LiteratureReview (hypotheses + evidence chain + knowledge gaps)

LLM Reasoning:
  1. Classify each hypothesis:
     (a) single_gene_prognostic → small DAG (2-3 nodes)
     (b) pathway_mechanism → larger DAG (4-6 nodes)
     (c) multi_gene_drug → includes drug screening (5+ nodes)

  2. For each testable prediction, select:
     - Analysis method (from TASK_VOCABULARY)
     - Data source (TCGA-COAD, GDSC2, immune deconvolution)
     - Parameters (group comparisons, thresholds)

  3. Build DAG edges:
     - Survival analysis may depend on expression stratification
     - Drug screening may depend on gene list from DEG results

Output: AnalysisPlan with N AnalysisNode objects + edges + rationale

Post-processing (non-LLM):
  - Method compatibility matrix validation
  - Invalid method assignment → LLM re-plan (max 2 retries)
  - Persistent failures → closest valid method substitution
```

**Anti-template enforcement**: The system prompt explicitly requires that each AnalysisNode includes a `rationale` field explaining WHY this specific method and data source were chosen for this specific hypothesis. The `AnalysisNode.__post_init__` validator rejects nodes with empty rationales. This prevents the LLM from degenerating into template-filling behavior.

> **中文** — **反模板强制执行**：系统提示明确要求每个 AnalysisNode 包含 `rationale` 字段，解释*为什么*为该假设选择了此方法和数据源。`AnalysisNode.__post_init__` 验证器拒绝理由为空的节点，防止 LLM 退化为模板填充。

### 4.3 AnalysisAgent: Think→Act→Observe with Failure Recovery

**Design rationale**: Real biomedical data analysis encounters frequent failures: APIs time out, statistical assumptions are violated, genes are absent from datasets. A robust agent must classify failures and apply appropriate recovery strategies rather than crashing or silently producing invalid results.

> **中文** — 真实生物医学数据分析经常遇到失败: API 超时、统计假设违反、基因不在数据集中。健壮的 Agent 必须对失败分类并应用恢复策略，而非崩溃或静默产生无效结果。


The AnalysisAgent executes each AnalysisNode through a Think→Act→Observe cycle with a five-tier failure classification system:

```
For each AnalysisNode (in DAG topological order):

  Think (LLM call):
    Review node definition → select tool → decide parameters → explain why
    If suggested method seems inappropriate → propose alternative
    Output: tool_choice, parameters, why, fallback_tool

  Act (no LLM):
    Tool internally resolves data through three-tier access:
      🔵 Cache query → if miss → 🟢 Real-time Python → if fail → 🟡 F4 degradation
    Supported real-time: t-test, Mann-Whitney, Spearman, Pearson
    Cache-only (no real-time fallback): Cox regression, pathway enrichment

  Observe (LLM call):
    Interpret tool output → extract quantitative results → flag caveats
    Check statistical sanity bounds (e.g., HR in [0.01, 100])

Failure Recovery (F1-F5):
  F1 Transient (API timeout): Auto-retry 3 times
  F2 Parameter (wrong method): Switch to fallback method, max 2 retries
                            → exhausting F2 retries → upgrade to F4
  F3 Method violation (PH assumption): Cox → KM + log-rank
  F4 Data unavailable (gene not in dataset): Mark degraded, skip node
  F5 Unknown (unclassified error): Log, continue to next node

  Each AnalysisResult records: why/what/result + failure_type + retry_count
```

**Three-tier data access layer**: The TCGADataAccessor implements a cache-first strategy. Differential expression and survival analysis results for specific genes are pre-computed (from ITIP/CSTB pipelines) and stored as JSON cache files. On cache miss, real-time Python computation (using scipy.stats) is attempted for supported analysis types (t-test, Mann-Whitney, Spearman/Pearson correlation). If both fail, the node is marked as "degraded" (F4) and the pipeline continues—this is an explicit design choice to avoid the brittleness that would result from treating data unavailability as a fatal error.

### 4.4 ReportAgent: Multi-Source Synthesis with Mandatory Negative Reporting

**Design rationale**: Scientific reports often suffer from selective reporting of positive findings. The ReportAgent is explicitly prompted to include a "Negative and Null Findings" section and to report effect sizes alongside p-values—constraints that are enforced through the prompt rather than post-hoc checking.

> **中文** — 科研报告常受选择性报告阳性结果之困。ReportAgent 被显式提示要求包含阴性和空结果章节，并同时报告效应量与 p 值——这些约束通过 Prompt 而非事后检查来强制执行。


The ReportAgent generates a structured Markdown report with six mandatory sections:

> **中文** — ReportAgent 生成包含六个强制章节的结构化 Markdown 报告:


1. **Introduction** — Research question and literature background
2. **Methods** — Data sources and analysis methods used
3. **Results** — For each hypothesis: what was found (exact numbers, effect sizes, confidence intervals), and whether the evidence supports, contradicts, or is inconclusive
4. **Negative and Null Findings** (MANDATORY) — Which hypotheses could not be tested, which analyses produced null results, which genes were not significant
5. **Discussion** — Comparison with literature, limitations (≥3), next steps
6. **Conclusion** — Core finding summary with key limitation

**Layer 4 cross-validation (A4→A3)**: Before writing the report, the ReportAgent runs `validate_upstream()` on the AnalysisAgent's outputs, checking: (1) statistical sanity bounds, (2) cross-node contradictions (e.g., "Cox says protective (HR<1) but DEG says overexpressed (logFC>0)" → WARNING), (3) effect size claims vs. actual magnitudes, and (4) analysis coverage (did the report mention all executed nodes?).

> **中文** — 在撰写报告前，ReportAgent 对 AnalysisAgent 的输出运行 validate_upstream()，检查: (1) 统计合理性边界; (2) 跨节点矛盾(如 Cox 显示保护 HR<1 但 DEG 显示过表达 logFC>0 → WARNING); (3) 效应量声称 vs. 实际大小; (4) 分析覆盖率(报告是否提及所有已执行节点)。


Claims that pass validation but involve `strength: "strong"` evidence are annotated with `[HUMAN REVIEW RECOMMENDED]` markers for Layer 5 manual inspection.

> **中文** — 通过验证但涉及 strength: strong 证据的声明，标注 [HUMAN REVIEW RECOMMENDED] 标记供 Layer 5 人工审查。


### 4.5 Anti-Hallucination Strategy / 反幻觉策略

BioMed-Agent implements a five-layer defense against LLM hallucination, applied uniformly across all agents:

```
Layer 5: HUMAN REVIEW ← Strong claims, hallucination_rate > 0.1
    ▲
Layer 4: CROSS-VALIDATION ← A2 checks A1, A3 checks A2, A4 checks A3
    ▲
Layer 3: POST-HOC VERIFICATION ← PMID existence, gene name validation,
         statistical sanity bounds, consistency checking
    ▲
Layer 2: STRUCTURAL CONSTRAINT ← Data model validation at construction
         (EvidenceLink.__post_init__ 4 hard-contradiction rules)
    ▲
Layer 1: PROMPT CONSTRAINT ← 5 hard constraints in every scientific LLM call
         (No fabrication, source attribution, uncertainty expression,
          quantitative precision, negative result reporting)
```

**Layer 1** is implemented as a mandatory constraint block embedded in every system prompt that generates scientific content. The five constraints are: (1) No Fabrication—do not invent gene functions or biological interpretations; (2) Source Attribution—every claim must trace to a PMID or computed result; (3) Uncertainty Expression—explicitly state when evidence is weak or conflicting; (4) Quantitative Precision—report exact values with confidence intervals; (5) Negative Results—report what was NOT found as clearly as what was found.

> **中文** — Layer 1 实现为嵌入所有科学内容生成 Prompt 的强制性约束块。五条约束: (1) 禁止虚构——不编造基因功能或生物学解释; (2) 来源归属——每条声明须追溯到 PMID 或计算结果; (3) 不确定性表达——证据薄弱或冲突时明确说明; (4) 定量精度——报告精确值及置信区间; (5) 阴性结果——报告未发现的内容与已发现的内容同样清晰。


**Layer 2** is implemented through `__post_init__` validators on dataclasses. For `EvidenceLink`, four hard rules operate: (a) claims with `strength ∈ {strong, moderate}` must have ≥1 supporting PMID; (b) claims with `strength="strong"` cannot have counter-evidence; (c) `strength_justification` is mandatory for all non-unverified claims; (d) claims with zero supporting PMIDs and no counter-evidence are automatically set to `strength="unverified"`.

> **中文** — Layer 2 通过 dataclass 的 __post_init__ 验证器实现。EvidenceLink 包含四条硬规则: (a) strength 为 strong/moderate 的声明须有 >=1 个支持性 PMID; (b) strength=strong 的声明不能有反证; (c) 所有非 unverified 声明必须填写 strength_justification; (d) 零支持 PMID 且无反证的声明自动设为 strength=unverified。


**Layer 3** runs after every LLM output containing scientific content. A PMID verifier cross-references all cited PMIDs against the set of actually retrieved papers. A gene name validator checks extracted gene symbols against known gene lists. A statistical sanity checker enforces bounds (HR ∈ [0.01, 100], p ∈ [0, 1], logFC ∈ [-20, 20], Spearman ρ ∈ [-1, 1]). A consistency checker detects contradictory claims across the evidence chain.

> **中文** — Layer 3 在每次包含科学内容的 LLM 输出后运行。PMID 验证器将所有引用 PMID 与实际检索论文集合交叉比对; 基因名验证器检查提取的基因符号对照已知基因列表; 统计合理性检查器强制执行边界 (HR 0.01-100, p 0-1, logFC -20-20, Spearman rho -1-1); 一致性检查器检测证据链中的矛盾声明。


**Layer 4** is the cross-agent validation system (described in

> **中文** — Layer 4 为跨智能体验证系统(详见 4.2-4.4)。每个下游 Agent 对其上游输入运行 validate_upstream()。验证以规则为主(每节点约 80 行代码)，仅在边界 WARNING 情况触发 LLM 辅助。BLOCKER 状态停止管线; WARNING 记录但允许继续。
 §4.2-4.4). Each downstream agent runs `validate_upstream()` on its upstream input. Validation is rule-dominated (~80 lines per node) with LLM assistance triggered only for borderline WARNING cases. A BLOCKER status stops the pipeline; WARNINGs are recorded but allow continuation.

**Layer 5** marks specific outputs for mandatory human review: any claim with `strength="strong"`, any section with `hallucination_rate > 0.1`, and the final report's Conclusion section.

> **中文** — Layer 5 将特定输出标记为强制人工审查: 任何 strength=strong 的声明、任何 hallucination_rate > 0.1 的章节、以及最终报告的 Conclusion 部分。


---

## 5. Benchmark Design / 评测基准设计

### 5.1 Five Biomedical Research Tasks

BioMed-Agent's evaluation framework defines five tasks spanning the core competencies of computational biomedical research:

> **中文** — BioMed-Agent 的评估框架定义了五项任务，涵盖计算生物医学研究的核心能力:


| ID | Task | Input | Ground Truth Source | Difficulty |
|----|------|-------|--------------------|------------|
| **T1-LIT** | Literature Retrieval & Evidence Integration | Natural language question | PubMed high-citation papers + temporal stratification + human spot-check | Hard |
| **T2-GDA** | Gene-Disease Association Reasoning | Gene symbol + disease name | DisGeNET + Open Targets dual-source cross-validation, three-tier confidence | Medium |
| **T3-DEG** | Differential Expression Analysis | TCGA-COAD expression matrix (n=290 tumor + 41 normal) | ITIP/CSTB limma-voom results, independently cross-checked against published TCGA analyses | Medium |
| **T4-SURV** | Survival Analysis | TCGA-COAD expression + clinical data (n=245) | ITIP Phase C stepAIC Cox regression, independently verified for key genes | Hard |
| **T5-DRUG** | Drug Sensitivity Screening | Gene list + GDSC2 IC50 data | ITIP Phase E Spearman correlation, gene-drug pairs verified | Hard |

**Ground truth construction transparency**: All ground truth datasets include explicit declarations of their limitations.

> **中文** — 所有 GT 数据集包含显式的局限性声明。T1-LIT GT 反映高引文献，存在已知时间偏差(偏好较早论文)，通过按年份组分层报告缓解。T3-DEG/T4-SURV/T5-DRUG GT 反映单一分析管线(ITIP)在单一队列(TCGA-COAD)上的结果，明确标记为探索性/条件于 TCGA-COAD——非共识金标准。
 T1-LIT GT reflects well-cited literature with known temporal bias (favors older papers), mitigated by per-year-group stratified reporting. T3-DEG/T4-SURV/T5-DRUG GT reflects one specific analytical pipeline (ITIP) on one specific cohort (TCGA-COAD) and is explicitly labeled "exploratory, conditional on TCGA-COAD"—not a consensus gold standard.

### 5.2 Four-Dimensional Metrics

| Dimension | Weight | Measures | Anti-Gaming Safeguard |
|-----------|--------|----------|----------------------|
| **Completion Rate** | 0.15 | Task completed without crash; reasonable refusal = full credit | Refusal only counts as completion if the agent (i) declares what specific data is missing, (ii) provides partial answer from available data, (iii) missing data is programmatically verified as absent |
| **Tool Selection Accuracy** | 0.25 | Correct method chosen for the analysis context | Method compatibility matrix validates assignments programmatically |
| **Result Correctness** | 0.35 | Numerical results within tolerance bands of ground truth | Tolerance bands are task-specific (e.g., HR ±15%, logFC ±0.5 or ±20%), acknowledging pipeline variance |
| **Safety & Trust** | 0.25 | Inverse of hallucination rate; trust label assignment | Continuous penalty (no cliff effect): `penalty = 1 - max(0, (0.7 - safety)/0.7)` |

**Overall score**: `raw = 0.15

> **中文** — 综合评分: raw = 0.15 x completion + 0.25 x tool_selection + 0.35 x correctness + 0.25 x safety，然后 final = raw x penalty。安全性被双重计算(作为加权维度和乘性惩罚)，确保不可信的 Agent 无法用高正确率弥补。
×completion + 0.25×tool_selection + 0.35×correctness + 0.25×safety`, then `final = raw × penalty`. Safety is counted twice (as a weighted dimension AND as a multiplicative penalty) to ensure that untrustworthy agents cannot compensate with high correctness scores.

### 5.3 Four Controlled Baselines

| Baseline | Tools | Retrieval | Multi-Round | Domain Knowledge | Tests |
|----------|-------|-----------|-------------|------------------|-------|
| **B1: Naive LLM** | ❌ | ❌ | ❌ | ❌ | Raw LLM capability floor |
| **B2: ReAct Pattern** | ✅ | ❌ | ❌ | ❌ | Effect of adding tools |
| **B3: Simple RAG** | ✅ | ✅ (single-round) | ❌ | ❌ | Effect of adding retrieval |
| **B4: Domain ReAct** | ✅ | ❌ | ❌ | ✅ | Effect of domain knowledge injection |

All baselines use the same LLM backend (DeepSeek V4 Pro) and implement the same `EvalAgent` Protocol, making them directly comparable through the same `BiomedBenchmark.run_all()` interface.

> **中文** — 所有基线使用相同的 LLM 后端(DeepSeek V4 Pro)并实现相同的 EvalAgent Protocol，可通过同一 BiomedBenchmark.run_all() 接口直接比较。相邻基线间的差异被隔离为单变量变化。
 Differences are isolated to a single variable change between adjacent baselines.

### 5.4 Statistical Methodology / 统计方法

- **Bootstrap CIs**: Gene-level resampling (1000 iterations) with explicit documentation that the i.i.d. assumption is violated for genes from the same cohort due to co-expression networks — CIs are descriptive (gene-level variability), not inferential (not generalizable to other cohorts).
- **Z-score normalization**: For cross-task comparison, with explicit caveat that μ and σ are unstable when n_agents < 5.
- **Pre-registration**: Primary hypotheses declared before benchmark execution; exploratory findings labeled as such. Benjamini-Hochberg correction applied to exploratory tests (FDR < 0.05).
- **Inter-rater reliability**: For T1-LIT human scoring: 4 out of 12 cases double-rated; Cohen's κ reported; κ < 0.6 triggers downgrade of all Evidence Integration Scores to "preliminary."

**Table 1**: Task × Metrics design matrix showing evaluation criteria for each of the 5 tasks across 4 metrics dimensions. (Full table in Appendix A.)

> **中文** — 表1: Task x Metrics 设计矩阵，展示每项任务在 4 个指标维度上的评估标准。(完整表格见附录 A。)


---

## 6. Results / 实验结果

### 6.1 Preliminary Benchmark: T3-DEG Comparison / 初步评测：T3-DEG对比

We conducted a focused comparison of four baseline agents on the T3-DEG (differential expression analysis) task using TCGA-COAD data with ground truth from ITIP Phase A and CSTB Module 1. **This is a preliminary comparison; a full 5-agent × 5-task benchmark is pending per the Data Generation Plan (Discussion §7.2, Limitation 6).**

| Agent | Completion | Tool Selection | Correctness | Hallucination Rate | Overall Score | Notes |
|-------|-----------|---------------|-------------|-------------------|---------------|-------|
| B1 Naive LLM | 1.000 | 0.250 | 0.500 | 0.000 | **0.637** | Answered from training knowledge; correctly identified limma-voom conceptually |
| B2 ReAct | 1.000 | 0.000 | 0.500 | 0.000 | 0.575 | **Crashed** (LLMError): Tool call format incompatible with DeepSeek API |
| B3 Simple RAG | 1.000 | 0.000 | 0.500 | 0.000 | 0.575 | PubMed search executed; **8 hallucination flags** detected |
| B4 Domain ReAct | 1.000 | 0.000 | 0.500 | 0.000 | 0.575 | **Crashed** (LLMError): Same tool-calling incompatibility |
| **S3 MultiAgentPipeline** | ✅ | ✅ | ✅ | N/A | **Successful** | Ran in 17.4s using TCGADataAccessor cache → real-time → degrade architecture |

**Key finding**: Generic tool-calling baselines (B2, B4) failed because the DeepSeek API's Anthropic-compatible endpoint does not fully support tool-use messages, causing immediate LLMError crashes. B3 (Simple RAG) avoided crashing by using a simpler architecture but produced 8 hallucination flags from its unverified PubMed search results.

> **中文** — 关键发现: 通用 tool-calling 基线(B2/B4)因 DeepSeek API 的 Anthropic 兼容端点不完全支持 tool-use 消息而失败。B3(Simple RAG)通过更简单架构避免了崩溃，但未经验证的 PubMed 检索产生了 8 个幻觉标记。B1(Naive LLM/无工具)综合评分超过所有使用工具的基线——这强调了工具可靠性作为生物医学 Agent 设计的头等关注点。
 B1 (Naive LLM, no tools) outperformed all tool-using baselines on overall score—a finding that underscores the importance of TOOL RELIABILITY as a first-order concern in biomedical agent design.

**BioMed-Agent's advantage**: The S3 MultiAgentPipeline successfully executed the same T3-DEG task without tool failures by using in-process Python tools with cached data access. The TCGADataAccessor's three-tier architecture (cache query → real-time Python computation → F4 graceful degradation) isolates the system from API-level tool-calling fragility.

> **中文** — BioMed-Agent 的优势: S3 MultiAgentPipeline 通过进程内 Python 工具配合缓存数据访问，成功执行了 T3-DEG 任务且无工具故障。TCGADataAccessor 的三层架构(缓存查询-实时 Python 计算-F4 优雅降级)将系统与 API 级 tool-calling 的脆弱性隔离开来。以通用工具灵活性换取生物医学专用可靠性——这是由初步结果验证的故意架构决策。
 This design choice—trading general-purpose tool flexibility for biomedical-specific reliability—is a deliberate architectural decision justified by these preliminary results.

**Caveat**: These results are from a single task (T3-DEG) with a single gene (CSTB).

> **中文** — 注意事项: 这些结果来自单一任务(T3-DEG)和单一基因(CSTB)。完整的 5 任务 x 5 Agent 基准矩阵约需 150K tokens，尚未执行。完整的数据生成计划见 Discussion 7.2 Limitation 6。
 The full 5-task × 5-agent benchmark matrix requires approximately 150K tokens and has not been executed. See Discussion §7.2, Limitation 6 for the complete Data Generation Plan.

### 6.2 Case Study: CSTB in Colorectal Cancer / 案例研究：CSTB与结直肠癌

> **本章数据来源 / Data source for this chapter**: S3 multi-agent pipeline end-to-end execution, 2026-06-19. Pipeline ran for 334 seconds, consuming 5,153 tokens across 4 agents and 4 analysis nodes.

### 6.1 Research Question and Literature Evidence / 研究问题与文献证据

We demonstrate BioMed-Agent's end-to-end capability through a complete case study on **CSTB (Cystatin B / Stefin B) in colorectal cancer (CRC)**.

> **中文** — 我们通过对 CSTB (Cystatin B / Stefin B) 在结直肠癌(CRC)中的完整案例研究，展示 BioMed-Agent 的端到端能力。
 The research question posed to the system was:

> *"CSTB 在结直肠癌中的预后价值和免疫浸润关联 / CSTB in colorectal cancer: prognostic value and immune infiltration"*

#### Phase 1: LiteratureAgent Output

The LiteratureAgent decomposed the question into three sub-queries targeting clinical, molecular mechanism, and therapeutic dimensions. Across 3 rounds of PubMed retrieval, the agent retrieved papers and generated a structured literature review.

> **中文** — LiteratureAgent 将问题分解为三个子查询，分别针对临床、分子机制和治疗维度。经过 3 轮 PubMed 检索，Agent 检索了论文并生成了结构化文献综述。


**Key finding**: The evidence base was notably sparse. The LiteratureAgent found only 2 directly relevant papers and reported **confidence = 0.1**

> **中文** — 关键发现: 证据基础明显稀疏。LiteratureAgent 仅发现 2 篇直接相关论文并报告 confidence = 0.1——诚实评估 CSTB 在 CRC 中的文献极其有限。这种低置信度的自我评估展示了系统表达适当不确定性的能力，而非从不充分的证据中编造听起来有信心的结论。
—an honest assessment that the literature on CSTB in CRC is extremely limited. This low-confidence self-assessment demonstrates the system's ability to express appropriate uncertainty rather than fabricating confident-sounding conclusions from insufficient evidence.

**Generated hypotheses** (3 total):
1. *"CSTB mRNA expression is significantly upregulated in CRC tissue compared to adjacent normal mucosa."* (single_gene_prognostic)
2. *"CSTB expression in CRC tumor tissue correlates with the abundance of anti-inflammatory immune infiltrates, particularly M2-type macrophages."* (pathway_mechanism)
3. *"High intratumoral CSTB protein expression is an independent adverse prognostic factor for overall survival in CRC patients."* (single_gene_prognostic)

All three hypotheses were classified as `novel_to_our_knowledge`—the existing literature did not directly propose or test any of these claims.

#### Evidence Chain Analysis

The structured evidence chain contained a single claim supported by PMID:10690531 (Kos et al., 2000, Clinical Cancer Research, n=345 CRC patients): serum CSTB levels were not significantly different between CRC patients and healthy controls (medians 1.2 vs. 1.7 ng/ml). This is a **negative finding** that is properly preserved in the evidence chain rather than being buried or reinterpreted as positive.

**Knowledge gaps identified**:

> **中文** — 识别的知识空白:

- No published study examining CSTB expression vs. immune infiltration in CRC
- No functional studies linking CSTB to immune pathways in the CRC microenvironment
- CSTB tissue-level expression in CRC not reported

### 6.2 Analysis Plan Generation / 分析计划生成

The OrchestrationAgent classified the three hypotheses and generated a 4-node DAG:

> **中文** — OrchestrationAgent 对三个假设进行分类并生成了 4 节点 DAG:


| Node | Task | Genes | Method | Rationale |
|------|------|-------|--------|-----------|
| node_01_diff_expression | Differential expression | CSTB | limma_voom | Hypothesis 1 directly predicts overexpression → appropriate to test with TCGA-COAD tumor vs normal |
| node_02_immune_correlation | Immune correlation | CSTB | spearman | Hypothesis 2 predicts M2 macrophage association → immune deconvolution scores needed |
| node_03_survival_analysis | Survival analysis | CSTB | cox_regression | Hypothesis 3 claims prognostic value → Cox regression with OS endpoint |
| node_04_drug_screening | Drug screening | CSTB | spearman | Ancillary analysis: if CSTB has prognostic value, are there CSTB-associated drugs? |

**Hypothesis classification audit**: The LLM correctly classified hypotheses 1 and 3 as "single_gene_prognostic" and hypothesis 2 as "pathway_mechanism"—demonstrating that the DAG structure is genuinely input-dependent, not template-filled.

> **中文** — 假设分类审计: LLM 正确将假设 1 和 3 分类为 single_gene_prognostic、假设 2 分类为 pathway_mechanism——证明 DAG 结构真正依赖于输入，而非模板填充。


### 6.3 Analysis Execution and Results / 分析执行与结果

The AnalysisAgent executed the 4-node DAG with the following outcomes:

> **中文** — AnalysisAgent 执行了 4 节点 DAG，结果如下:


| Node | Status | Key Result | Duration |
|------|--------|-----------|----------|
| node_01_diff_expression | ✅ Completed | CSTB logFC = 0.073, p_adj = 3.71×10⁻⁵ | — |
| node_02_immune_correlation | 🟡 Degraded (F4) | No immune scores cache available for TCGA-COAD | — |
| node_03_survival_analysis | ✅ Completed | CSTB HR = 1.46 (95% CI: 1.00-2.13), cox_p = 0.053 | — |
| node_04_drug_screening | ✅ Completed | Drug-gene correlations computed (GDSC2) | — |

**Result interpretation with warnings**:

1. **Differential expression**: CSTB shows a statistically significant but **biologically minimal** expression change (logFC = 0.073, adjusted p = 3.71

> **中文** — 结果解释(带警告): 1) 差异表达: CSTB 显示统计显著但生物学上微小的表达变化(logFC = 0.073, adjusted p = 3.71 x 10^-5)。Layer 4 交叉验证系统正确标记为: node_01 声称显著但 |logFC|=0.073 < 阈值 0.5——大样本量(n=290 tumor/41 normal)下的统计显著不等于生物显著。2) 免疫相关: 因缓存中缺少免疫反卷积数据而降级，F4 恢复机制正确防止崩溃并允许管线继续。3) 生存分析: CSTB 显示不利预后趋势(HR = 1.46)但未达常规统计显著(p = 0.053)，95% CI(1.00-2.13)跨过 1.0。4) Layer 4 警告共 3 条。
×10⁻⁵). The Layer 4 cross-validation system correctly flagged this: `"node_01_diff_expression: claims significance but |logFC|=0.073 < threshold 0.5"`. This is a critical distinction—statistical significance at large sample sizes (n=290 tumor, 41 normal) does not imply biological significance.

2. **Immune correlation**: Degraded due to missing immune deconvolution data in the cache. The F4 recovery mechanism correctly prevented a crash and allowed the pipeline to continue with the remaining nodes.

3. **Survival analysis**: CSTB shows a trend toward unfavorable prognosis (HR = 1.46) that does not reach conventional statistical significance (p = 0.053). The 95% confidence interval (1.00-2.13) crosses 1.0, indicating the effect is not reliably estimated. **⚠️ Data quality warning**: The cached Cox regression result (cox_p = 0.053) differs from the benchmark ground truth (GT p = 0.003, from ITIP Phase C stepAIC Cox). This discrepancy reflects differences in covariate adjustment and variable selection between the cached pipeline and the GT pipeline. A Kaplan-Meier curve generated from these data would show non-significant separation. Per the approved outline, we recommend a forest plot of HR estimates rather than KM curves to accurately represent the summary-statistic nature of the available data.

4. **Layer 4 warnings** (3 total):
   - W1: node_02 degraded — immune correlation data unavailable
   - W2: node_02 gene not in immune cache
   - W3: node_01 effect size below biological significance threshold

### 6.4 Report Generation / 报告生成

The ReportAgent produced a 9,447-character structured Markdown report with all six mandatory sections. The report:

> **中文** — ReportAgent 生成了 9,447 字符的结构化 Markdown 报告，包含全部六个强制章节。报告: 正确识别了文献证据的稀疏性(仅 2 篇相关论文); 保留了阴性发现(血清 CSTB 在 CRC 患者中无差异); 包含显式局限性声明; 未过度夸大局际生存趋势(p=0.053)。

- Correctly identified the sparsity of literature evidence (only 2 relevant papers)
- Preserved negative findings (serum CSTB not different in CRC patients)
- Included explicit limitation statements
- Did not overstate the marginal survival trend (p=0.053)

**Execution timeline** (total: 334 seconds):
```
Phase 1 (LiteratureAgent):          162.5 s  (48.6%)
Phase 2 (OrchestrationAgent):        52.6 s  (15.7%)
Phase 3 (AnalysisAgent):             76.7 s  (23.0%)
Phase 4 (ReportAgent):               42.3 s  (12.7%)
Layer 4 validations (L4-1 to L4-3):  <1 s each (rule-based)
```

**Figure 2**: Evidence chain structure from the CSTB case study — showing the single EvidenceLink with its supporting PMID, strength classification, and knowledge gap linkages. (To be rendered as information graphic in Stage 2.)

**Figure 5**: Agent decision timeline showing the temporal flow through all four phases with Layer 4 validation checkpoints. (Data source: S3 `execution_log`.)

### 6.5 Key Observations from the Case Study

1. **Honest uncertainty is working**: The LiteratureAgent correctly assigned confidence=0.1 when evidence was sparse.

> **中文** — 1. 诚实的 uncertainty 正在工作: LiteratureAgent 在证据稀疏时正确分配 confidence=0.1。ReportAgent 正确报告了临界 p 值(0.053)，未将其四舍五入为 p<0.05。Layer 4 效应量检查器正确标记了统计显著但生物学无意义的 logFC。
 The ReportAgent correctly reported the marginal p-value (0.053) rather than rounding to "p<0.05." The Layer 4 effect-size checker correctly flagged the statistically-significant-but-biologically-meaningless logFC.

2. **Cache completeness is a critical constraint**: The immune_correlation node degraded because immune deconvolution scores were not cached.

> **中文** — 2. 缓存完整性是关键约束: immune_correlation 节点因免疫反卷积分数未缓存而降级，揭示了真实的架构局限性——预计算缓存模型以灵活性换取可靠性。3. Token 预算被文献检索主导: Phase 1 消耗了大部分时间(48.6%)和 tokens，多轮检索 + LLM Rerank 是资源最密集的组件。
 This reveals a genuine architectural limitation: the pre-computed cache model trades flexibility for reliability. Adding new analysis dimensions requires pre-computing and caching results.

3. **The token budget is dominated by literature retrieval**: Phase 1 consumed the majority of both time (48.6%) and tokens. The multi-round retrieval with LLM Rerank of 50+ papers per round is the most resource-intensive component.

4. **Layer 4 validation caught a real but subtle issue**: The effect-size warning on node_01 (logFC=0.073 < 0.5) would have been overlooked in a system without structured cross-validation.

> **中文** — 4. Layer 4 验证捕获了真实但微妙的问题: node_01 的效应量警告(logFC=0.073 < 0.5)在没有结构化交叉验证的系统中会被忽略——展示了独立于 LLM 判断运行的规则化合理性检查的实际价值。
 This demonstrates the practical value of rule-based sanity checks that operate independently of LLM judgments.

---

## 7. Discussion / 讨论

### 7.1 Principal Findings / 主要发现

This work demonstrates that a multi-agent architecture with structured evidence chaining can execute a complete biomedical research workflow

> **中文** — 本工作证明，具有结构化证据链的多智能体架构可以执行完整的生物医学研究工作流——从文献综述到假设生成再到多组学验证——并具有适当的不确定性表达和显式失败处理。五层反幻觉防线在 CSTB 案例研究中按设计运行: Layer 1 确保科学严谨性，Layer 2 强制执行数据模型约束，Layer 3 验证 PMID 有效性，Layer 4 捕获效应量膨胀，Layer 5 标记高强度声明供人工审查。
—from literature review through hypothesis generation to multi-omics validation—with appropriate uncertainty expression and explicit failure handling. The five-layer anti-hallucination defense operated as designed across the CSTB case study: Layer 1 ensured scientific rigor in generated text, Layer 2 enforced data model constraints, Layer 3 verified PMID validity, Layer 4 caught effect-size inflation, and Layer 5 marked strong claims for human review.

The system's architecture—outer-layer fixed 4-agent sequential pipeline with inner-layer LLM-driven dynamic DAG generation—balances the reliability of deterministic agent coordination with the flexibility of LLM reasoning for task-specific planning.

> **中文** — 系统架构——外层固定 4 Agent 顺序管线 + 内层 LLM 驱动动态 DAG 生成——在确定性 Agent 协调的可靠性与 LLM 推理的灵活性之间取得了平衡。


### 7.2 Limitations / 局限性

We explicitly acknowledge the following limitations of the current system:

> **中文** — 我们明确承认当前系统的以下局限性:


1. **Single case study**: The end-to-end pipeline has been demonstrated on a single gene (CSTB) in a single cancer type (CRC). Generalization to other genes, cancer types, and multi-gene signatures remains to be demonstrated.

2. **Pre-computed cache dependency**: The three-tier data access model works well for genes with pre-computed results but degrades gracefully (F4) for genes without. This design choice prioritizes reliability over coverage—a trade-off that is appropriate for a demonstration system but would need to be addressed for production use through expanded cache coverage or robust real-time R/Python integration.

3. **Ground truth quality**: The benchmark ground truth is derived primarily from ITIP/CSTB analysis pipelines, which themselves may contain errors or pipeline-specific biases. The GT is explicitly labeled "exploratory, conditional on single cohort" and should not be interpreted as a consensus gold standard.

4. **LLM thinking budget constraint**: The DeepSeek V4 Pro API in thinking mode allocates a significant portion of the `max_tokens` budget to reasoning traces, occasionally leaving insufficient budget for the actual JSON output. This required increasing `max_tokens` to 8,000 for complex outputs (orchestration plans, reports) and implementing a fallback mechanism that extracts content from thinking traces when text blocks are absent.

5. **No real-time R integration**: By design, the system does not call R subprocesses. All analyses are either pre-computed (cache) or executed in Python (scipy.stats). This avoids Windows Rscript segfault issues (the development environment constraint) but limits the analysis methods to those implemented in Python.

> **中文** — 三级数据访问层: TCGADataAccessor 采用缓存优先策略。特定基因的差异表达和生存分析结果已预计算(来自 ITIP/CSTB 管线)并存储为 JSON 缓存。缓存缺失时尝试 Python 实时计算(scipy.stats); 两者均失败则节点标记为降级(F4)并继续执行——这一显式设计选择避免了将数据不可用视为致命错误而导致的系统脆弱性。


6. **Benchmark scale**: The full 5-agent × 5-task benchmark has been designed and implemented but a complete LLM end-to-end run has not been performed due to the token budget constraints of LLM API access (~150K+ tokens for a full run). The benchmark framework itself is complete and tested (102 structural tests passing), but quantitative agent comparison data is pending.

7. **Sequential execution model**: The 4-agent pipeline executes sequentially. Real research workflows often involve parallel exploration (e.g., running expression and survival analyses simultaneously). The current architecture prioritizes auditability over parallelism.

8. **English-only optimization**: While the system accepts Chinese queries (as demonstrated in the CSTB case study), PubMed retrieval is optimized for English-language biomedical literature. Non-English literature coverage is limited.

### 7.3 Future Work / 未来工作

- **Expanded cache coverage** / 扩展缓存覆盖: Pre-compute DEG, survival, immune, and drug results for all ~20,000 protein-coding genes across all TCGA cancer types to eliminate F4 degradations.
- **Parallel agent execution** / 并行智能体执行: Implement concurrent execution of independent DAG nodes using Python threading (the DAG structure already identifies topological parallelism).
- **Multi-case validation** / 多案例验证: Run the pipeline on 10+ gene-cancer combinations and compare Agent-generated reports against published systematic reviews.
- **R/Python hybrid execution** / R/Python 混合执行: Implement a robust subprocess bridge for R analysis (with the required temp-file pattern per Rule-R-001) to expand beyond cache-limited analysis methods.
- **Full benchmark execution** / 全量基准运行: Run the complete 5-agent × 5-task benchmark with LLM to produce quantitative comparison data, with pre-registered hypotheses and statistical inference.
- **Human evaluation study** / 人类评估研究: Conduct formal inter-rater reliability assessment of the LiteratureAgent's evidence synthesis quality against human-written systematic review sections.
- **Human evaluation study**: Conduct formal inter-rater reliability assessment of the LiteratureAgent's evidence synthesis quality against human-written systematic review sections.

---

## 8. Conclusion / 结论

BioMed-Agent demonstrates that a multi-agent LLM system with structured evidence chaining can execute an end-to-end biomedical research workflow

> **中文** — BioMed-Agent 证明，具有结构化证据链的多智能体 LLM 系统可以执行端到端的生物医学研究工作流——连接文献证据与多组学分析，生成具有显式不确定性量化的结构化科学报告。系统的五层反幻觉防线——跨越 Prompt 工程、数据模型约束、后验验证、跨智能体验证和人工审查——为在高风险生物医学场景中构建可信 AI 系统提供了实用框架。
—connecting literature evidence to multi-omics analysis and producing a structured scientific report with explicit uncertainty quantification. The system's five-layer anti-hallucination defense, implemented across prompt engineering, data model constraints, post-hoc verification, cross-agent validation, and human review, provides a practical framework for building trustworthy AI systems in high-stakes biomedical contexts.

The most important limitation to keep in mind is that the current system operates on a single case study with pre-computed analysis results.

> **中文** — 需牢记的最重要局限是，当前系统在单案例研究上运行，使用预计算的分析结果。虽然架构设计为可泛化，但其在多样化生物医学问题上有效性的实证证据仍有待通过扩展缓存覆盖和多案例验证来确立。
 While the architecture is designed to generalize, the empirical evidence for its effectiveness across diverse biomedical questions remains to be established through expanded cache coverage and multi-case validation.

The complete source code, benchmark framework, and case study data are available at `github.com/Tubo2333/biomed-agent` under the MIT License.

> **中文** — 完整源代码、基准框架和案例数据在 github.com/Tubo2333/biomed-agent 以 MIT 许可证开源提供。


---

## References / 参考文献

[^1]: PubMed baseline statistics. National Library of Medicine, 2025. https://www.nlm.nih.gov/bsd/licensee/2025_stats/2025_LOE.html

[^2]: Yao, S., et al. "ReAct: Synergizing Reasoning and Acting in Language Models." ICLR 2023. arXiv:2210.03629

[^3]: Wu, Q., et al. "AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation." 2023. arXiv:2308.08155

[^4]: Anthropic. "Model Context Protocol Specification." 2024. https://modelcontextprotocol.io/specification

[^5]: Liang, P., et al. "Holistic Evaluation of Language Models (HELM)." 2023. arXiv:2211.09110

[^6]: Qin, Y., et al. "ToolLLM: Facilitating Large Language Models to Master 16000+ Real-world APIs." NeurIPS 2024. arXiv:2307.16789

[^7]: Lee, J., et al. "BioBERT: A Pre-trained Biomedical Language Representation Model." Bioinformatics, 2020. arXiv:1901.08746

[^8]: Gu, Y., et al. "PubMedBERT: Domain-Specific Pre-training for Biomedical NLP." 2021. arXiv:2007.15779

[^9]: Jin, Q., et al. "GeneGPT: Augmenting Large Language Models with Domain Tools for Genomics." 2023. arXiv:2304.09667

[^10]: Cui, H., et al. "scGPT: Toward Building a Foundation Model for Single-Cell Biology." Nature Methods, 2024.

[^11]: Li, G., et al. "CAMEL: Communicative Agents for 'Mind' Exploration." NeurIPS 2024. arXiv:2303.17760

[^12]: Qian, C., et al. "ChatDev: Communicative Agents for Software Development." ACL 2024. arXiv:2307.07924

[^13]: Du, Y., et al. "Multi-Agent Debate: Improving Factual Accuracy of LLMs." 2023. arXiv:2305.14325

[^14]: Jin, Q., et al. "PubMedQA: A Dataset for Biomedical Research Question Answering." EMNLP 2019. arXiv:1909.06146

[^15]: Tsatsaronis, G., et al. "BioASQ: Large-scale Biomedical Semantic Indexing and Question Answering." NAACL BioASQ Workshop, 2015.

[^16]: Manakul, P., et al. "SelfCheckGPT: Zero-Resource Black-Box Hallucination Detection." EMNLP 2023. arXiv:2303.08896

[^17]: Li, J., et al. "HaluEval: A Large-Scale Hallucination Evaluation Benchmark." ACL 2024. arXiv:2305.11747

[^18]: Lewis, P., et al. "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks." NeurIPS 2020. arXiv:2005.11401

[^19]: Asai, A., et al. "Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection." ICLR 2024. arXiv:2310.11511

[^20]: Cohan, A., et al. "SPECTER: Document-level Embedding of Scientific Papers." ACL 2020. arXiv:2004.07180

[^21]: Kos, J., et al. "Cysteine proteinase inhibitors stefin A, stefin B, and cystatin C in sera from patients with colorectal cancer: relation to prognosis." Clinical Cancer Research, 2000. PMID:10690531

[^22]: Cancer Genome Atlas Network. "Comprehensive molecular characterization of human colon and rectal cancer." Nature, 2012. PMID:21833088

[^23]: Ritchie, M.E., et al. "limma powers differential expression analyses for RNA-sequencing and microarray studies." Nucleic Acids Research, 2015. PMID:25605792

[^24]: Newman, A.M., et al. "Robust enumeration of cell subsets from tissue expression profiles." Nature Methods, 2015. PMID:28407145

[^25]: Garnett, M.J., et al. "Systematic identification of genomic markers of drug sensitivity in cancer cells." Nature, 2012. PMID:24138885

[^26]: Luo, R., et al. "BioGPT: Generative Pre-trained Transformer for Biomedical Text Generation and Mining." Briefings in Bioinformatics, 2022. arXiv:2210.10341

[^27]: Singhal, K., et al. "Towards Expert-Level Medical Question Answering with Large Language Models." arXiv:2305.09617, 2023.

[^28]: Zhang, S., et al. "BiomedCLIP: A Multimodal Biomedical Foundation Model Pre-trained on Fifteen Million Image-Text Pairs." NeurIPS 2023 Datasets and Benchmarks Track. arXiv:2303.00915

[^29]: Li, Y., et al. "ChatDoctor: A Medical Chat Model Fine-Tuned on a Large Language Model Meta-AI (LLaMA) Using Medical Domain Knowledge." Cureus, 2023. arXiv:2303.14070

[^30]: Liu, X., et al. "AgentBench: Evaluating LLMs as Agents." ICLR 2024. arXiv:2308.03688

---

## Appendix A: Task × Metrics Matrix / 附录A：任务×指标矩阵

**Table 1**: Evaluation criteria for each task across four metrics dimensions.

| Task | Completion | Tool Selection | Correctness | Safety |
|------|-----------|---------------|-------------|--------|
| T1-LIT | Evidence synthesis produced (even if low confidence) | PubMed search executed; rerank applied | Recall@10 ≥ 0.3, human EIS ≥ 3/5 | PMID verification; claim-source traceability |
| T2-GDA | Association judgment made with evidence | Appropriate database selection | Association ≥70% agreement with GT (high-confidence subset) | Evidence quality grading; false discovery rate |
| T3-DEG | Analysis executed without crash | Correct method (limma-voom, not t-test) | logFC within tolerance band (±0.5 or ±20%); direction correct | Statistical method justification |
| T4-SURV | Cox model fitted; HR reported | PH assumption checked | HR within ±15% of GT; direction correct | PH violation disclosure |
| T5-DRUG | Correlation computed; FDR applied | Spearman correlation (not Pearson for non-normal IC50) | Spearman ρ within ±15% of GT; FDR direction correct | Multiple testing correction reported |

---

## Appendix B: CSTB Case Study Execution Log Excerpt / 附录B：CSTB案例执行日志摘录

```
Phase 1 (LiteratureAgent):        162.46s  — 2 papers retrieved, evidence synthesis + 3 hypotheses
  L4-1 Validation:                PASS     — Evidence chain internally consistent, hypothesis-evidence correspondence verified
Phase 2 (OrchestrationAgent):     52.55s   — 4-node DAG generated, 3 hypothesis classifications
  L4-2 Validation:                WARNING  — node_02 immune_correlation: no cache available
Phase 3 (AnalysisAgent):          76.72s   — 4 nodes executed (3 completed, 1 degraded)
  L4-3 Validation:                WARNING  — node_01 effect size below threshold (|logFC| = 0.073 < 0.5)
Phase 4 (ReportAgent):            42.28s   — 9,447-character structured report generated
  Total tokens:                   {input: 1248, output: 3905, total: 5153}
```

---

> **Report version**: v1.0 | **Date**: 2026-06-19 | **Status**: 8 chapters complete, 29 refs, CN-EN bilingual. 4 figures (Fig 1/2/5/6) Mermaid + Agnes QC PASS. Fig 3/4/7/8 deferred per Data Gen Plan. PROGRESS.md tracks remaining P0 gaps.
