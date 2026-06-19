# 学习路线图：从"阴差阳错做出来了"到"知道为什么这样做"

> **目标**：让你的嘴追上你的手。你代码写得出来，但面试时如果被问"你为什么不用 LangChain""你的方法和 AutoGen 有什么区别""ReAct 的局限性是什么"，你不能只说"我觉得这样更好"——你需要能引用论文、说出作者名字、讲清楚 trade-off。
>
> **使用方式**：按顺序读。标 ★ 的是必读（面试可能被问到），标 ◆ 的是选读（时间不够可以看摘要+结论），标 ▲ 的是你已经做了但需要补理论。

---

## 第一部分：AI Agent 基础（你的 TAOR 的理论根基）

> 你实现了 Think→Act→Observe 循环。这叫 ReAct pattern。这一部分告诉你它从哪来、有哪些变体、你的设计选择在学术上叫什么。

### ★ 1.1 ReAct: Synergizing Reasoning and Acting in Language Models
- **作者**：Yao et al., 2022 (Stanford / Google Brain)
- **来源**：arXiv 2210.03629 / ICLR 2023
- **为什么必读**：这是你 TAOR 循环的理论源头。读完你能说："TAOR 的 Think→Act→Observe 实现的是 ReAct pattern，但我们的 TAOR loop 有 X 个关键不同——（1）双向 AsyncGenerator 通道允许用户中途注入决策而不是被动观察，（2）Act 阶段同时支持 tool call 和 subagent spawn……"
- **重点读**：§3 (ReAct 的思考-行动-观察循环的定义), §5.1 (HotpotQA 上的多步推理表现)

### ★ 1.2 ToolLLM: Facilitating Large Language Models to Master 16000+ Real-world APIs
- **作者**：Qin et al., 2023 (Tsinghua / Microsoft)
- **来源**：arXiv 2307.16789 / NeurIPS 2024
- **为什么必读**：TAOR 的 defineTool() + MCP bridge 本质上就是 ToolLLM 想解决的问题——如何让 LLM 可靠地调用大量异构 API。读完你能说："ToolLLM 用 DFS-based search 来做 tool selection，而 TAOR 的选择是……"
- **重点读**：§3 (ToolBench 数据集构建), §4.2 (DFSDT 决策树搜索策略)

### ◆ 1.3 Gorilla: Large Language Model Connected with Massive APIs
- **作者**：Patil et al., 2023 (UC Berkeley / Microsoft)
- **来源**：arXiv 2305.15334
- **为什么选读**：和 ToolLLM 同期的工作，侧重点不同（Gorilla 关注 API 文档理解，ToolLLM 关注多步工具编排）。你的 TAOR 更接近 ToolLLM 的路线。

### ◆ 1.4 Voyager: An Open-Ended Embodied Agent with Large Language Models
- **作者**：Wang et al., 2023 (NVIDIA / Caltech)
- **来源**：arXiv 2305.16291 / NeurIPS 2024
- **为什么选读**：Agent 在 Minecraft 中自动探索和技能学习。它的"自动课程"（automatic curriculum）和你的 TAOR 循环的 maxTurns/stopReason 自动终止有类似之处。开拓思路用。

### ★ 1.5 The MCP Specification
- **作者**：Anthropic, 2024
- **来源**：https://modelcontextprotocol.io/specification (看 "Architecture" 和 "Lifecycle" 两节即可)
- **为什么必读**：你的 MCP bridge 实现了这个 spec。面试官如果问"MCP 和 OpenAI function calling 有什么区别"，你需要能说出：MCP 是 client-server 架构，tools/list + tools/call 两步发现，支持 stdio/SSE 两种 transport，而 function calling 是 in-band 的。读完 spec 你就能说清楚。

---

## 第二部分：RAG 与检索增强（你即将做的 Step 1 的理论根基）

### ★ 2.1 Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks
- **作者**：Lewis et al., 2020 (Facebook AI Research)
- **来源**：arXiv 2005.11401 / NeurIPS 2020
- **为什么必读**：RAG 的原始论文。你的 LiteratureAgent 就是 RAG + 生物医学领域的特化。读完你能说："原始 RAG 是 retriever + generator 的端到端训练，我们的系统用的是 in-context RAG（检索结果塞进 prompt），区别在于……"
- **重点读**：§3 (RAG 的架构：retriever + generator), §5.1 (Open-domain QA 结果)

### ★ 2.2 Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection
- **作者**：Asai et al., 2023 (University of Washington)
- **来源**：arXiv 2310.11511 / ICLR 2024
- **为什么必读**：和你的 LiteratureAgent 设计高度相关——你的 Agent 在第一轮检索后判断"证据是否充足""是否需要补充检索"，这就是 Self-RAG 的 reflection 思想。读完你能引用它来解释为什么你的 Agent 有多轮检索。
- **重点读**：§3.1 (reflection tokens 的设计), §4 (实验结果中 reflection 的贡献)

### ◆ 2.3 REALM: Retrieval-Augmented Language Model Pre-Training
- **作者**：Guu et al., 2020 (Google Research)
- **来源**：arXiv 2002.08909 / ICML 2020
- **为什么选读**：更偏预训练侧的 retrieval augmentation。了解即可，面试不太可能问这么深。

### ★ 2.4 SPECTER: Document-level Embedding of Scientific Papers
- **作者**：Cohan et al., 2020 (Allen Institute for AI)
- **来源**：arXiv 2004.07180 / ACL 2020
- **为什么必读**：你的 LiteratureAgent 需要 embed 科学论文。SPECTER 是专门为科学论文设计的 embedding 模型，比通用 text-embedding-3-small 更懂论文的语义结构。读完你能说："我们目前用的是 OpenAI embedding，但 SPECTER / SPECTER2 在科学文献语义检索上表现更好，因为它是用 citation graph 训练的……"
- **重点读**：§3 (triplet loss 训练方式), §4.1 (SciDocs benchmark 上的表现)

---

## 第三部分：多智能体系统（你的 Spatial Agent + Step 3 的理论根基）

### ★ 3.1 AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation
- **作者**：Wu et al., 2023 (Microsoft Research)
- **来源**：arXiv 2308.08155
- **为什么必读**：多 Agent 框架的代表作。你的 Step 3 Pipeline（4 Agent 协作）和 AutoGen 的设计理念会有直接对比。面试官几乎一定会问"你的系统和 AutoGen 有什么区别"。读完你能说："AutoGen 的核心是 conversation-driven control flow（Agent 之间通过对话协调），而我们的系统是 DAG-driven（OrchestrationAgent 生成执行 DAG，AnalysisAgent 按 DAG 执行）。区别在于……"
- **重点读**：§3 (conversation patterns), §5.1 (coding tasks 上的 multi-agent 表现)

### ★ 3.2 CAMEL: Communicative Agents for "Mind" Exploration
- **作者**：Li et al., 2023 (KAUST)
- **来源**：arXiv 2303.17760 / NeurIPS 2024
- **为什么必读**：提出了 role-playing 作为多 Agent 协作的核心机制。你的 Step 3 给每个 Agent 不同的 system prompt 和工具集，本质上是 role-based agent design。读完你能引用 CAMEL 来支撑你的设计。
- **重点读**：§3 (role-playing framework), §5 (role 分配对任务完成质量的影响)

### ◆ 3.3 ChatDev: Communicative Agents for Software Development
- **作者**：Qian et al., 2023 (Tsinghua)
- **来源**：arXiv 2307.07924 / ACL 2024
- **为什么选读**：多 Agent 在软件工程中的应用（CEO/CTO/Programmer/Reviewer 角色分工）。和你的 4 Agent 科研工作流（Literature→Orchestration→Analysis→Report）在角色设计上有类似之处。开拓思路用。

### ◆ 3.4 Multi-Agent Debate: Improving Factual Accuracy of LLMs
- **作者**：Du et al., 2023 (MIT)
- **来源**：arXiv 2305.14325
- **为什么选读**：多个 Agent 互相辩论来减少幻觉。和你 00B 中 Layer 4（交叉验证）的理念一致——Agent A 的输出被 Agent B 验证。如果你的 benchmark 结果中交叉验证显著降低了幻觉率，你可以引用这篇。

---

## 第四部分：生物医学 AI 与大模型（你的领域知识层）

### ★ 4.1 BioBERT: A Pre-trained Biomedical Language Representation Model
- **作者**：Lee et al., 2020 (Korea University)
- **来源**：arXiv 1901.08746 / Bioinformatics 2020
- **为什么必读**：生物医学 NLP 的经典。读完你能说为什么通用 LLM 在生物医学文本上可能有 gap，以及 domain-specific pre-training 的价值。
- **重点读**：§3 (BioBERT 的预训练), §4.3 (NER 任务上的提升)

### ★ 4.2 PubMedBERT: Domain-Specific Pre-training for Biomedical NLP
- **作者**：Gu et al., 2021 (Microsoft Research)
- **来源**：arXiv 2007.15779
- **为什么必读**：和 BioBERT 同期，但从零开始在 PubMed 上预训练（不是继续训练 BERT）。读完你能在面试时讨论"通用 embedding vs 生物医学专用 embedding"的 trade-off——这正是 Step 1 的设计决定之一。
- **重点读**：§3 (从头预训练 vs 继续训练的对比实验)

### ◆ 4.3 GeneGPT: Augmenting Large Language Models with Domain Tools for Genomics
- **作者**：Jin et al., 2023 (UC San Diego)
- **来源**：arXiv 2304.09667
- **为什么选读**：教 LLM 使用 NCBI API（包括 PubMed）来做基因组学任务。和你的 LiteratureAgent（PubMed 检索→证据整合）在思路上非常接近。读完你能引用它证明"让 LLM 调用生物医学 API 是可行的"。
- **重点读**：§3 (tool-augmented approach), §4.2 (GeneGPT 在 GeneTuring benchmark 上的表现)

### ★ 4.4 scGPT: Toward Building a Foundation Model for Single-Cell Biology
- **作者**：Cui et al., 2023 (University of Toronto / Vector Institute)
- **来源**：bioRxiv 2023 / Nature Methods 2024
- **为什么必读**：单细胞基础模型的代表作。你的 ITIP 和 Spatial Agent 处理的是 bulk 和 spatial 数据，但 scGPT 代表的方向（用 transformer 建模基因表达）是 AI for Science 的热点。面试时能聊到这个说明你关注前沿。
- **重点读**：§2 (预训练目标), §3.1 (cell type annotation 的 zero-shot 表现)

### ◆ 4.5 BioBridge: Multimodal Foundation Model for Biomedical Knowledge
- **作者**：多个团队, 2024-2025
- **为什么选读**：生物医学多模态基础模型（文本+知识图谱+多组学）。了解前沿方向即可。

---

## 第五部分：Benchmark 与评估（你的 Step 2 的理论根基）

### ★ 5.1 Holistic Evaluation of Language Models (HELM)
- **作者**：Liang et al., 2023 (Stanford CRFM)
- **来源**：arXiv 2211.09110
- **为什么必读**：LLM 评估的方法论标杆。你的 Step 2 Benchmark 在思路上应该参考 HELM 的"多维度 × 多场景"评估框架。读完你能说："我们的 benchmark 设计参考了 HELM 的多维评估思想，针对生物医学场景定义了 4 个维度……"
- **重点读**：§2 (评估维度的 taxonomy), §4.1 (scenario 的定义)

### ★ 5.2 PubMedQA: A Dataset for Biomedical Research Question Answering
- **作者**：Jin et al., 2019 (MIT)
- **来源**：arXiv 1909.06146 / EMNLP 2019
- **为什么必读**：生物医学 QA 的经典 benchmark。你的 T1-LIT（文献检索任务）和 PubMedQA 在任务定义上有重叠。读完你能说清楚你的 benchmark 和 PubMedQA 的区别。
- **重点读**：§3 (数据集构建方式), §5 (human performance baseline)

### ★ 5.3 BioASQ: Large-scale Biomedical Semantic Indexing and Question Answering
- **作者**：Tsatsaronis et al., 2015 / 持续更新
- **来源**：BioASQ workshop @ NAACL / 每年更新
- **为什么必读**：比 PubMedQA 更大规模的生物医学 QA benchmark。了解有哪些公开 benchmark 可用，避免你重复造轮子。
- **重点读**：Task descriptions (Task A: 文献分类, Task B: 问答)

### ◆ 5.4 MedQA & MedMCQA: Medical Domain Question Answering
- **作者**：Jin et al., 2024 (MedQA) / Pal et al., 2022 (MedMCQA)
- **来源**：各 arXiv 或 ACL
- **为什么选读**：医学考试题 benchmark。了解医学领域的评估标准，虽然你的 benchmark 侧重研究任务而非考试。

---

## 第六部分：Agent 幻觉与可信度（你的整个系统的核心挑战）

### ★ 6.1 SelfCheckGPT: Zero-Resource Black-Box Hallucination Detection
- **作者**：Manakul et al., 2023 (University of Cambridge)
- **来源**：arXiv 2303.08896 / EMNLP 2023
- **为什么必读**：**和你的系统最直接相关的幻觉检测论文。** SelfCheckGPT 通过让同一个 LLM 多次生成回答、检查一致性来检测幻觉。你的 Layer 3（后验验证）和 Layer 4（交叉验证）可以引用这篇。读完你能说："SelfCheckGPT 用 sampling-based consistency 来检测幻觉，我们借鉴了它的思路，但在生物医学场景中加了额外的结构化约束（PMID 验证 + 统计量合理性检查）。"
- **重点读**：§3 (三种检测方法), §4.3 (passage-level hallucination detection)

### ★ 6.2 HaluEval: A Large-Scale Hallucination Evaluation Benchmark
- **作者**：Li et al., 2023 (Renmin University of China)
- **来源**：arXiv 2305.11747 / ACL 2024
- **为什么必读**：系统性地定义了 5 类幻觉（事实、知识、逻辑、上下文、算术）。你的 00B 中（论文幻觉/断章取义/过度推断/错误传播）可以对齐到这个 taxonomy。读完你的分类会更学术化。
- **重点读**：§3.1 (五类幻觉的定义和示例)

### ◆ 6.3 FACTOID: Faithfulness Evaluation of LLMs
- **作者**：多个团队, 2023-2024
- **为什么选读**：了解 faithfulness（忠实于输入）vs factuality（符合事实）的区别——这个区别对你设计 Layer 2（结构约束）很重要。

### ◆ 6.4 Constitutional AI: Harmlessness from AI Feedback
- **作者**：Bai et al., 2022 (Anthropic)
- **来源**：arXiv 2212.08073
- **为什么选读**：不是直接关于幻觉，但"让 AI 监督 AI"的思路和你 Layer 4 的 Agent 间交叉验证是同源的。面试时如果能提到 Constitutional AI 和你的交叉验证之间的关系，会显得你很懂。

---

## 第七部分：补充学习方式（论文之外的）

### 7.1 值得关注的博客/教程
- **Lilian Weng's Blog** (https://lilianweng.github.io) — OpenAI 研究员的博客。"LLM Powered Autonomous Agents" 和 "Prompt Engineering" 两篇是必读。
- **Anthropic Research Blog** — MCP 协议、Claude 的 system prompt 设计、幻觉缓解策略。
- **Chip Huyen's Blog** (https://huyenchip.com) — ML/AI 系统设计的实战视角。"Building LLM Applications" 系列。
- **LangChain Blog** — 了解他们的设计哲学（即使你不用 LangChain，你也需要知道它在想什么）。

### 7.2 值得看的视频
- **Andrej Karpathy: "State of GPT"** (Microsoft Build 2023, YouTube) — 1 小时讲清楚 LLM 工作原理。必看。
- **Anthropic: "MCP Protocol Deep Dive"** (YouTube) — 如果找到了就看一下，你实现了 MCP consumer，应该看看 spec 作者的讲解。
- **Stanford CS25: Transformers United** (YouTube playlist) — V3 之后的几节关于 Agent 和 Tool Use。

### 7.3 面试前必能脱口而出的关键对比

| 被问到这个 | 你能引用的论文/概念 | 你的系统的立场 |
|-----------|------------------|-------------|
| "为什么不用 LangChain？" | LangChain 的 callback hell 问题 + ReAct 论文 | TAOR 用 AsyncGenerator 双向通道替代 callback，避免了嵌套地狱 |
| "你的系统和 AutoGen 有什么区别？" | AutoGen 论文 §3 conversation patterns | AutoGen 是对话驱动的，TAOR 是 DAG 驱动的。对话灵活但难以审计；DAG 可追溯但灵活性差 |
| "你怎么评估 Agent 好坏？" | HELM (Liang 2023) + PubMedQA + SelfCheckGPT | 我们的 benchmark 参考 HELM 的多维框架，定义了 5 task × 4 metrics × 3 baselines |
| "Hallucination 怎么解决？" | SelfCheckGPT + HaluEval + Constitutional AI | 五层防线：prompt→结构→后验→交叉验证→人审 |
| "为什么用 ReAct 而不是 Plan-then-Execute？" | ReAct vs Plan-and-Solve (Wang 2023) | ReAct 允许中间观察修正计划，对生物医学的未知检索空间更鲁棒 |

---

## 阅读顺序建议

```
Week 1: 1.1 ReAct ★ → 2.1 RAG ★ → 6.1 SelfCheckGPT ★
         （先建 Agent + RAG + 幻觉检测的三角框架）

Week 2: 1.2 ToolLLM ★ → 1.5 MCP Spec ★ → 3.1 AutoGen ★
         （工具调用 + 多Agent框架，补充你的 TAOR 和 Step 3 的理论背景）

Week 3: 4.1 BioBERT ★ → 4.2 PubMedBERT ★ → 4.3 GeneGPT ◆ → 2.4 SPECTER ★
         （生物医学 AI + 科学文献 embedding，补充 Step 1 的领域知识）

Week 4: 5.1 HELM ★ → 5.2 PubMedQA ★ → 6.2 HaluEval ★ → 3.2 CAMEL ◆ → 4.4 scGPT ★
         （Benchmark 方法论 + 幻觉分类学 + 拓展视野）
```

每个论文的阅读方法：先读 Abstract → Introduction 最后两段 → 扫一眼 Figures/Tables → 读 Conclusion → 如果觉得关键再细读 Method。一篇 ★ 论文 30-45 分钟，一篇 ◆ 论文 15-20 分钟。

---

> **最后**：你不必在这个学习计划完成之后才开始做 Step 1。学习和动手可以并行——上午读论文，下午开窗口做设计。论文读到的内容会直接影响你的设计选择，而设计中的困惑会告诉你下一步该读什么。两边互相推动。
