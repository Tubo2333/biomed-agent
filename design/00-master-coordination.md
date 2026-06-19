# 00 — 主协调文档：五步之间的依赖、共享契约与一致性约束

> **读者**：你自己 + 每个独立 Claude 窗口
> **用途**：确保五个窗口各自的产出能拼在一起，不出现接口不一致、类型冲突、哲学矛盾
> **更新规则**：任何窗口做出影响其他步骤的设计决定，必须回写此文档

---

## 一、五步全景与依赖关系

```
                    ┌─────────────────────────┐
                    │  Step 1: Literature RAG │
                    │  (4-5天)                │
                    │  定义共享数据类型 ★     │
                    └───────────┬─────────────┘
                                │ 导出: LiteratureReview, Hypothesis,
                                │       Paper, BiomedEmbedder, 
                                │       EvidenceSynthesizer
                                │
            ┌───────────────────┼───────────────────┐
            ▼                   ▼                   ▼
┌───────────────────┐  ┌───────────────────┐  ┌───────────────────┐
│ Step 2: Benchmark │  │ Step 3: Pipeline  │  │ (Step 4 依赖两者) │
│ (5-6天, 可并行)   │  │ (5-7天, 依赖S1)  │  │                   │
│                   │  │                   │  │                   │
│ 导出:             │  │ 消费: S1的类型    │  │                   │
│ BenchmarkTask     │  │ 导出: CaseStudy   │  │                   │
│ AgentEvalMetrics  │  │       Result      │  │                   │
│ BiomedBenchmark   │  │                   │  │                   │
└────────┬──────────┘  └────────┬──────────┘  │                   │
         │                      │              │                   │
         └──────────────────────┼──────────────┘                   │
                                ▼                                  │
                    ┌───────────────────┐                          │
                    │ Step 4: Report    │                          │
                    │ (7-10天)          │                          │
                    │ 消费: S1/S2/S3的  │                          │
                    │ 所有输出          │                          │
                    └────────┬──────────┘                          │
                             ▼                                     │
                    ┌───────────────────┐                          │
                    │ Step 5: Portfolio │                          │
                    │ (2-3天)           │                          │
                    │ 消费: 所有产出    │                          │
                    └───────────────────┘                          │
```

**关键依赖约束**：
- Step 2 与 Step 1 **可部分并行**：Step 2 只需要 Step 1 定义好 `LiteratureReview` 和 `Paper` 的数据结构，不需要 Step 1 的实现完成。但 Step 2 的 T1-LIT（文献检索任务）需要用 Step 1 的 Agent 作为被测对象，所以 Step 2 的 runner 部分需要等 Step 1 完成。
- Step 3 **必须等 Step 1 完成**：因为 Step 3 的 LiteratureAgent 就是 Step 1 的产出物。
- Step 4 **必须等 Step 1-3 全部完成**：没有实验数据写不了报告。
- Step 5 **必须等 Step 4 完成**：报告是 portfolio 的核心内容。

---

## 二、共享数据类型（所有步骤必须遵守的契约）

### 2.1 Paper（Step 1 定义，Step 2/3/4 消费）

```python
@dataclass
class Paper:
    pmid: str                    # PubMed ID
    title: str
    abstract: str
    authors: list[str]
    journal: str
    year: int
    doi: str | None
    embedding: np.ndarray | None # 向量表示，检索用
    relevance_score: float | None # 与查询的相关性
```

### 2.2 LiteratureReview（Step 1 定义，Step 2/3/4 消费）

```python
@dataclass
class LiteratureReview:
    query: str                            # 原始查询
    papers_retrieved: int                 # 检索到的论文数
    papers_relevant: list[Paper]          # 筛选后的相关论文
    evidence_summary: str                 # 300-500字证据整合
    evidence_chain: list[EvidenceLink]    # 证据链
    hypotheses: list[Hypothesis]          # 1-3个可验证假设
    confidence: float                     # 0-1, 整体置信度
    knowledge_gaps: list[str]             # 发现的证据缺口
    citations: list[str]                  # 带PMID的引用列表
    token_usage: dict[str, int]           # {"input": N, "output": M}

@dataclass
class EvidenceLink:
    claim: str                            # 一个原子主张
    supporting_pmids: list[str]           # 支持该主张的PMID
    strength: str                         # "strong" | "moderate" | "weak" | "unverified"
    strength_justification: str           # LLM 自证依据（S1 D-002: 强制，即使 weak 也需填写）
    counter_evidence: str | None          # 反面证据

@dataclass
class Hypothesis:
    statement: str                        # 假设陈述
    rationale: str                        # 推理依据
    testable_prediction: str              # 可验证的预测
    required_data: list[str]              # 验证所需数据类型
    novelty: str                          # "novel_to_our_knowledge" | "supported_by_existing"（S1 D-003: 二分类）
    novelty_justification: str            # 为什么判定为该 novelty（S1 D-003: 强制）
```

### 2.3 BenchmarkTask（Step 2 定义，Step 1 和 Step 3 作为被测对象）

```python
@dataclass
class BenchmarkTask:
    task_id: str                          # "T1-LIT", "T2-GDA", ...
    task_name: str                        # 人类可读名称
    description: str                      # 任务描述
    input: dict[str, Any]                 # 任务输入（取决于任务类型）
    ground_truth: dict[str, Any]          # 正确答案
    evaluation_criteria: list[str]        # 评估维度
    difficulty: str                       # "easy" | "medium" | "hard"
    category: str                         # "retrieval" | "association" | "analysis" | "reasoning"

@dataclass
class AgentEvalMetrics:
    task_id: str
    agent_name: str
    task_completion_rate: float           # 0-1
    tool_selection_accuracy: float        # 0-1
    result_correctness: float             # 0-1
    hallucination_rate: float             # 0-1 (越低越好)
    safety_score: float                   # 0-1 (= 1 - hallucination_rate, S2 D-010)
    efficiency_score: float               # token消耗 vs 任务复杂度
    overall_score_raw: float              # 加权原始总分（含 Safety 惩罚后）
    overall_score_normalized: float | None # Z-score 归一化后（跨 task 可比）
    trust_label: str                      # "TRUSTWORTHY" | "BORDERLINE" | "NOT TRUSTWORTHY"
    details: dict[str, Any]               # 详细评估日志
```

### 2.4 AgentMessage（Step 3 定义，Step 3 内部使用）

```python
@dataclass
class AgentMessage:
    sender: str                           # agent_id
    receiver: str                         # agent_id
    message_type: str                     # "task_assign" | "task_complete" | "query" | "response"
    payload: dict[str, Any]
    correlation_id: str                   # workflow级标识
    timestamp: str                        # ISO 8601
```

### 2.5 ContaminationRiskReport（Step 2 定义，Step 4 消费）

```python
@dataclass
class ContaminationRiskReport:
    task_id: str                          # 被检查的Task
    agent_name: str                       # 探测Agent名（通常为NaiveLLM-Probe）
    risk_score: float                     # 0-1，越高越可能被预训练污染
    naive_llm_answer_matches_gt: bool     # Naive LLM（无数据）是否答对
    gt_overlaps_training_cutoff: bool     # GT是否在LLM训练截止前发布
    recommendation: str                   # "OK" | "CAUTION" | "INVESTIGATE"
    details: str                          # 人类可读解释
```

**注意**：此类型是 advisory-only（建议性质），不作为 benchmark 有效性的 gate。

---

## 三、共享基础设施（所有步骤使用相同的模式）

### 3.1 LLM 调用模式

所有 Step 使用统一的 LLM 调用封装：

```python
# src/llm/client.py  — 所有步骤共用的 LLM 客户端
class LLMClient:
    def chat(self, messages: list[dict], 
             model: str = "deepseek-v4-pro",
             temperature: float = 0.3,
             max_tokens: int = 2000,
             tools: list[dict] | None = None) -> LLMResponse
    def stream(self, ...) -> AsyncGenerator[LLMEvent]
```

**设计决策**（所有步骤必须一致）：
- 默认 model: deepseek-v4-pro（通过已有的 `~/.claude/settings.json` 中的 `ANTHROPIC_AUTH_TOKEN` + `ANTHROPIC_BASE_URL`）
- 默认 temperature: 0.3（生物医学场景需要事实准确性 > 创造性）
- 所有 prompt 必须包含 "DO NOT fabricate" 约束
- 所有 LLM 响应必须记录 token 用量

### 3.2 工具定义模式

```python
# src/tools/base.py  — 所有步骤共用的工具基类
@dataclass
class ToolDef:
    name: str
    description: str
    parameters: dict          # JSON Schema
    execute: Callable
    risk: str                 # "low" | "medium" | "high"
    requires_approval: bool
```

### 3.3 配置管理

所有步骤共用同一个配置文件：

```yaml
# config.yaml
llm:
  model: deepseek-v4-pro
  temperature: 0.3
  max_tokens: 2000

rag:
  embedding_model: text-embedding-3-small
  vector_db_path: ./data/vector_db
  top_k_retrieval: 10

benchmark:
  n_test_cases_per_task: 10
  random_seed: 42

data:
  tcga_cache: D:/C-file/itip_p1/data/tcga/
  gdsc_cache: D:/C-file/CSTB_paper/data/gdsc2/
  pubmed_cache: ./data/pubmed_cache/

output:
  results_dir: ./results
  figures_dir: ./paper/figures
```

### 3.4 GFW 探测模式

所有涉及网络 I/O 的代码使用统一模式（来自 `shared/gfw_probe.py`）：
```python
# src/utils/network.py
def check_proxy() -> bool   # 检查 127.0.0.1:7892
def ensure_network() -> None # PROXY_DOWN → raise NetworkError
```

---

## 四、Step 之间的设计哲学一致性（铁律）

以下原则必须在所有五个 Step 中保持一致，不能出现 A 窗口说"用 LangChain"而 B 窗口说"从零写"的情况：

### 4.1 Agent 设计哲学

- **Agent ≠ LLM + 工具列表。** Agent = Think→Act→Observe 循环，每个 Act 阶段包含工具选择、参数填充、结果解释三个子步骤。
- **Prompt 先行。** 每个 Agent 的 system prompt 是其最核心的"代码"。prompt 中必须定义：角色、可用工具、输出格式、约束条件（尤其是反幻觉约束）。
- **所有 Agent 决策必须可追溯。** 每个步骤记录 why（为什么选这个工具/参数）、what（实际做了什么）、result（结果是什么）。

### 4.2 反幻觉策略（全线一致）

1. **所有 LLM 输出涉及基因名、统计量、文献引用时，必须可验证**：基因名→检查是否在输入数据中，统计量→检查数值合理性，文献→PMID 必须真实。
2. **科学叙事 prompt 必须包含硬约束**：`"Only describe what the data shows. Do not fabricate gene functions, pathway associations, or biological interpretations not directly supported by the provided data."`
3. **所有定量结果必须有来源追踪**：从 LLM 输出中可以追溯到原始数据或原始论文。

### 4.3 代码风格与目录结构

- 所有 Python 代码使用 `dataclass` + type hints
- 单文件不超过 500 行（超过则拆分）
- 每个 Agent 一个文件，每个工具组一个文件
- tests/ 目录镜像 src/ 结构

### 4.4 评估优先

- 任何 Agent 或 pipeline 实现后，**必须有对应的 benchmark 评估结果**才能算"完成"
- 评估结果写入 `results/` 目录，格式为 JSON，Step 4 的报告自动读取

---

## 五、每个 Step 的输入/输出清单

| Step | 输入（依赖其他Step的什么） | 输出（被其他Step消费的什么） |
|------|--------------------------|---------------------------|
| **S1** | 无外部依赖。使用已有数据：PubMed API, `shared/gfw_probe.py` | `LiteratureAgent`, `LiteratureReview`类型, `Paper`类型, `BiomedEmbedder`, `EvidenceSynthesizer`, RAG pipeline组件 |
| **S2** | S1定义的`LiteratureReview`和`Paper`类型。S1实现的`LiteratureAgent`(作为被测对象) | `BenchmarkTask`类型, `AgentEvalMetrics`类型, `BiomedBenchmark`, 5个任务定义(含ground truth), baseline结果 |
| **S3** | S1的`LiteratureAgent`(完整实现), S1的RAG组件。S2的`BenchmarkTask`定义。已有数据：ITIP, CSTB, Spatial outputs | `OrchestrationAgent`, `AnalysisAgent`, CSTB case study完整运行结果, 多Agent消息日志 |
| **S4** | S1的实验数据(文献review质量), S2的实验数据(benchmark结果), S3的实验数据(case study定量结果) | 技术报告(.md+.pdf), 8张图(.svg+.png), references.bib |
| **S5** | S1-S4的全部产出 | GitHub仓库, README(中英), PPT, 面试Q&A文档 |

---

## 六、决策日志

每个 Step 的窗口在做出影响其他步骤的设计决定时，必须在此记录。

| 编号 | 日期 | Step | 决策 | 影响范围 |
|------|------|------|------|---------|
| D-001 | 2026-06-16 | S1 | Embedding: LLM Rerank路线（无embedding模型、无向量数据库）。已实现: `LLMRerank` | S2(T1-LIT基线), S3(检索质量) |
| D-002 | 2026-06-16 | S1 | EvidenceLink strength: LLM自证 + 硬矛盾检测（4条if），规则只降不升。已实现: `EvidenceLink.__post_init__` | S2(幻觉检测逻辑) |
| D-003 | 2026-06-18 | S2 | Benchmark难度分级: easy/medium/hard 基于GT可争议程度和任务复杂度 | S1(测试任务难度), S3(case study评估) |
| D-004 | 2026-06-19 | S3 | Agent间通信: 4 Agent在同一个Python进程中串行执行，用函数参数传递数据，无消息队列/MessageBus | S4(架构描述) |
| D-005 | — | S4 | 待定: 报告语言(纯英文 vs 中英双语) | S5(GitHub README语言) |
| D-013 | 2026-06-19 | S3 | R代码集成: 预计算缓存 + 实时Python，无subprocess R调用。已实现: `TCGADataAccessor`三层回退 | S4(报告方法描述) |
| D-014 | 2026-06-19 | S3 | 三层混合执行: 🔵缓存查询(DEG/Survival) + 🟢实时Python(免疫/药物) + 🟡降级F4。Agent不感知底层分派 | S3内部 |
| D-015 | 2026-06-19 | S3 | Layer 4交叉验证: 3个validate_upstream()节点(规则为主~80行/节点)，LLM仅边界WARNING触发。已实现: A2→A1, A3→A2, A4→A3 | S4(反幻觉架构描述) |
| D-016 | 2026-06-19 | S3 | Pipeline架构: 外层固定4 Agent串行 + 内层LLM驱动动态DAG。已实现: `OrchestrationAgent.plan()` | S4(架构描述) |
| D-017 | 2026-06-19 | S3 | EvalAgent Protocol适配: Task Router按task_id分派(T1→S1, T2→Phase1+2, T3-T5→Phase2+3)。已实现: `MultiAgentPipeline.run()` | S2(评测S3) |
| D-006 | 2026-06-16 | S1 | 多轮检索触发: LLM提议 + 三道闸门（max_rounds=3, 查询去重, token预算=15000）。已实现: `LiteratureAgent._think()` + `RetrievalGate` | S3(pipeline检索) |
| D-012 | 2026-06-18 | S1+S2 | LiteratureAgent实现EvalAgent Protocol: `run()`接受`str\|BenchmarkTask`，`_to_benchmark_output()`适配。S2可通过`BiomedBenchmark`评估S1 | S2(T1-LIT评测), S3(pipeline集成) |
| D-007 | 2026-06-18 | S2 | GT构建: 半自动混合路线—T1用PubMed高引+时间分层，T2用DisGeNET+OpenTargets三级置信度，T3-T5用ITIP/CSTB+tolerance bands | S3(分析基准), S4(报告数据源) |
| D-008 | 2026-06-18 | S2 | 幻觉检测: 硬规则V1(PMID)/V2(基因名)/V3(统计量) + 软分级LLM辅助 + 方法学白名单(≥24篇,不对Agent暴露) | S1(Layer 3验证), S3(Layer 4交叉验证) |
| D-009 | 2026-06-18 | S2 | Baseline设计: 4个baseline(B1 Naive/B2 ReAct/B3 SimpleRAG/B4 DomainReAct)，控制变量递进（工具→检索→多轮→领域知识） | S3(对比基线), S4(报告对比) |
| D-010 | 2026-06-18 | S2 | Safety Gate: 连续惩罚`penalty=1.0-max(0,(0.7-safety)/0.7)`替代硬门槛，首次运行后校准 | S3(pipeline评估), S4(Safety指标) |
| D-011 | 2026-06-18 | S2 | 统计方法: Bootstrap CI(gene-level,附i.i.d.违反正告)+Z-score归一化(n<5不稳定)+预注册hypothesis+BH校正 | S4(统计分析) |

---

## 七、各 Step 设计文档索引

| 文档 | 文件 | 核心问题 |
|------|------|---------|
| Step 1 | [01-literature-rag.md](01-literature-rag.md) | 如何让Agent从PubMed检索论文→embed→整合证据→生成假设？ |
| Step 1 详细设计 | [01-detailed-design.md](01-detailed-design.md) | S1完整设计（10文件，5 Prompt模板，4层防线） |
| Step 2 | [02-biomed-benchmark.md](02-biomed-benchmark.md) | 如何定义5类生物医学任务、4维metrics、4个baseline？ |
| Step 2 详细设计 | [02-detailed-design.md](02-detailed-design.md) | S2完整设计（9文件，6 Prompt模板，Safety连续惩罚，Tolerance Bands） |
| Step 3 | [03-multi-agent-pipeline.md](03-multi-agent-pipeline.md) | 如何让4个Agent协作完成文献→分析→报告的闭环？ |
| Step 4 | [04-technical-report.md](04-technical-report.md) | 如何把S1-S3的结果写成一篇有说服力的技术报告？ |
| Step 5 | [05-portfolio-packaging.md](05-portfolio-packaging.md) | 如何把所有产出打包成一个面试官30秒就能看懂的项目？ |

---

> **使用说明**：打开任意 Step 文档前，先读此文档的 §二（共享数据类型）和 §四（设计哲学一致性）。如果在该 Step 中需要修改或新增共享类型，先回写此文档的 §二和 §六。
