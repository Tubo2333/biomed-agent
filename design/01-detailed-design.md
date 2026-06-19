# 01 — Step 1 详细设计文档：文献推理 Agent + 生物医学 RAG Pipeline

> **状态**：Stage 1 设计深化 — AWAITING REVIEW
> **作者**：Biomedical NLP Engineer (窗口 1-A)
> **依赖**：`00-master-coordination.md` §二（共享类型）、§四（设计哲学）
> **同步产出**：本文档一旦锁定，所有实现必须严格遵循。偏差必须先更新本文档。

---

## 一、MODULE BREAKDOWN

### 文件清单（共 10 个文件）

```
biomed-agent/
├── src/
│   ├── types.py                    # 共享数据类型定义（S1 定义，其他 Step 消费）
│   ├── llm/
│   │   └── client.py               # 统一 LLM 调用客户端
│   ├── utils/
│   │   └── network.py              # GFW 探测 + retry 封装
│   ├── rag/
│   │   ├── retriever.py            # PubMed EUtils 调用 + 结果解析 + 缓存
│   │   ├── embedder.py             # Embedder 抽象接口 + LLMRerank 实现
│   │   ├── synthesizer.py          # EvidenceSynthesizer: 多论文 → 证据链 → 综述
│   │   └── hypothesis_generator.py # HypothesisGenerator: 证据缺口 → 假设
│   ├── tools/
│   │   └── pubmed_tools.py         # PubMed ToolDef 定义（供 Agent tool-calling）
│   └── agents/
│       └── literature_agent.py     # LiteratureAgent: Think→Act→Observe 多轮循环
├── demo/
│   └── run_literature_review.py    # 端到端 Demo 脚本
└── tests/
    ├── test_retriever.py
    ├── test_embedder.py
    ├── test_synthesizer.py
    ├── test_hypothesis_generator.py
    └── test_literature_agent.py
```

### 文件职责与依赖

| # | 文件 | 单一职责 | 大约行数 | 依赖 |
|---|------|---------|---------|------|
| 0 | `types.py` | 定义该 Step 产出/消费的每一个 dataclass | 120 | 无 |
| 1 | `utils/network.py` | 代理检测 + 网络可达性保障 | 50 | 无（整合 `shared/gfw_probe.py`） |
| 2 | `llm/client.py` | 封装 LLM 调用，统一 token 记录、temperature=0.3 | 100 | `utils/network.py` |
| 3 | `rag/retriever.py` | PubMed esearch + efetch + XML 解析 + 本地缓存 | 300 | `utils/network.py`, `types.py` |
| 4 | `rag/embedder.py` | Embedder 抽象类 + LLMRerank 实现（无 embedding 模型） | 120 | `llm/client.py`, `types.py` |
| 5 | `rag/synthesizer.py` | 多论文 → 结构化证据链 → evidence_summary（300-500字） | 300 | `llm/client.py`, `types.py` |
| 6 | `rag/hypothesis_generator.py` | 证据缺口识别 + 假设生成 + novelty 分类 | 180 | `llm/client.py`, `types.py` |
| 7 | `tools/pubmed_tools.py` | PubMed 工具定义（ToolDef），供 Agent tool-calling | 120 | `rag/retriever.py`, `types.py` |
| 8 | `agents/literature_agent.py` | Think→Act→Observe 主循环，多轮检索编排 | 350 | 上述所有模块 |
| 9 | `demo/run_literature_review.py` | 端到端 demo：接收 question → 输出 LiteratureReview | 60 | `agents/literature_agent.py` |

**说明**：
- **无 `vector_store.py`**：设计决定 #1 选择 LLM Rerank 路线，不使用 embedding 模型和向量数据库。
- **无单独 `cache.py`**：检索缓存逻辑内嵌在 `retriever.py` 中，使用 JSON 文件缓存（`data/pubmed_cache/`），不需要独立的缓存模块。
- 所有文件 ≤ 400 行（01- 原设计 `literature_agent.py` 预估 400 行，这里收紧到 350）。

---

## 二、DATA MODEL SPEC

### 2.1 共享类型（S1 定义，写入 00- §二，其他 Step 消费）

以下类型与 `00-master-coordination.md` §二完全一致，此处精确化字段约束和验证规则。

#### Paper

```python
@dataclass
class Paper:
    pmid: str                           # PubMed ID，格式: "\\d{8}"，必填
    title: str                          # 论文标题，必填，非空
    abstract: str                       # 摘要，可为空字符串（极少数 PubMed 条目无摘要）
    authors: list[str]                  # 作者全名列表（PubMed XML 中 LastName + ForeName），至少 1 个
    journal: str                        # 期刊简称（ISO Abbreviation），可为 ""
    year: int                           # 出版年，范围 1900-2026
    doi: str | None                     # DOI，可为 None
    embedding: np.ndarray | None        # 不使用（LLM Rerank 路线），保留字段为 None
    relevance_score: float | None       # 0-1，LLM Rerank 相关性打分，未评分时为 None

    def __post_init__(self):
        if not self.pmid or not self.pmid.strip():
            raise ValueError("PMID must not be empty")
        if self.year < 1900 or self.year > 2026:
            raise ValueError(f"Year {self.year} out of valid range")
        if self.relevance_score is not None and not (0 <= self.relevance_score <= 1):
            raise ValueError("relevance_score must be in [0,1]")
```

#### LiteratureReview

```python
@dataclass
class LiteratureReview:
    query: str                          # 原始查询，必填
    papers_retrieved: int               # 检索到的论文总数（去重后），≥0
    papers_relevant: list[Paper]        # 筛选后的相关论文，长度 ≤ papers_retrieved
    evidence_summary: str               # 300-500字证据整合，不可为空
    evidence_chain: list[EvidenceLink]  # 证据链，不可为空列表
    hypotheses: list[Hypothesis]        # 1-3个可验证假设
    confidence: float                   # 0-1, 整体置信度
    knowledge_gaps: list[str]           # 发现的证据缺口（自然语言描述）
    citations: list[str]                # 带 PMID 的引用列表，格式: "[PMID:12345678] FirstAuthor et al. (Year) Title"
    token_usage: dict[str, int]         # {"input": N, "output": M, "total": N+M}

    def __post_init__(self):
        if not self.evidence_chain:
            raise ValueError("evidence_chain must not be empty")
        if not (0 <= self.confidence <= 1):
            raise ValueError("confidence must be in [0,1]")
        if not (1 <= len(self.hypotheses) <= 3):
            raise ValueError("hypotheses count must be 1-3")
```

#### EvidenceLink

```python
@dataclass
class EvidenceLink:
    claim: str                          # 原子主张，必填，非空
    supporting_pmids: list[str]         # 支持该主张的 PMID，可为空列表
    strength: str                       # "strong" | "moderate" | "weak" | "unverified"
    strength_justification: str         # LLM 自证依据，必填（即使 strength 是 weak）
    counter_evidence: str | None        # 反面证据，None 表示未发现反面证据

    def __post_init__(self):
        valid_strengths = {"strong", "moderate", "weak", "unverified"}
        if self.strength not in valid_strengths:
            raise ValueError(f"strength must be one of {valid_strengths}")
        if self.strength in ("strong", "moderate") and len(self.supporting_pmids) == 0:
            raise ValueError(  # 这是硬矛盾检测 Layer 2 在 __post_init__ 中的第一条线
                f"strength='{self.strength}' but supporting_pmids is empty"
            )
        if self.strength == "strong" and self.counter_evidence is not None:
            raise ValueError(  # 硬矛盾检测第二条线
                "strength='strong' but counter_evidence is present"
            )
        if not self.strength_justification:
            raise ValueError("strength_justification is required for traceability")
```

#### Hypothesis

```python
@dataclass
class Hypothesis:
    statement: str                      # 假设陈述，必填，非空
    rationale: str                      # 推理依据（引用 EvidenceLink 中的 claim），必填
    testable_prediction: str            # 可验证的预测，必填，不能是纯推测
    required_data: list[str]            # 验证所需数据类型，至少 1 个
    novelty: str                        # "novel_to_our_knowledge" | "supported_by_existing"
    novelty_justification: str          # 为什么判定为该 novelty，必填

    def __post_init__(self):
        valid_novelty = {"novel_to_our_knowledge", "supported_by_existing"}
        if self.novelty not in valid_novelty:
            raise ValueError(f"novelty must be one of {valid_novelty}")
        if not self.novelty_justification:
            raise ValueError("novelty_justification is required")
        if not self.required_data:
            raise ValueError("required_data must not be empty")
        if not self.testable_prediction:
            raise ValueError("testable_prediction must not be empty")
```

### 2.2 Step 1 内部类型（仅 S1 内部使用，不导出）

#### SearchQuery（Retriever 输入）

```python
@dataclass
class SearchQuery:
    query_string: str                   # PubMed 查询字符串（支持 MeSH + 自由词）
    max_results: int = 50               # 最大检索篇数
    sort_by: str = "relevance"          # "relevance" | "date"
    date_range: tuple[int, int] | None = None  # (start_year, end_year)，None 不限制

    def __post_init__(self):
        if self.max_results < 1 or self.max_results > 100:
            raise ValueError("max_results must be in [1, 100]")
```

#### SearchResult（Retriever 输出）

```python
@dataclass
class SearchResult:
    query: SearchQuery
    papers: list[Paper]                 # 检索到的论文（仅包含 pmid, title, abstract, authors, journal, year, doi）
    total_count: int                    # PubMed 返回的总命中数（可能大于 len(papers)）
    retrieval_round: int                # 第几轮检索（从 1 开始）
```

#### RerankResult（Embedder 输出）

```python
@dataclass
class RerankResult:
    papers: list[Paper]                 # 排序后的论文（按 relevance_score 降序，top-K）
    scores: dict[str, float]            # pmid → relevance_score 映射
    token_used: int                     # LLM Rerank 消耗的 token
```

#### RetrievalGate（多轮检索闸门判断结果）

```python
@dataclass
class RetrievalGate:
    should_continue: bool               # 是否允许继续下一轮检索
    reason: str                         # 允许/拒绝的原因
    new_query: str | None               # 如果允许，LLM 生成的下一轮查询；否则 None
    rounds_used: int                    # 当前已用轮数
    token_used_so_far: int              # 当前已用 token
```

---

## 三、INTERFACE SPEC

### 3.1 导出给其他 Step 的 public 接口

#### LiteratureAgent（S2 消费其类型，S3 消费其完整实现）

```python
class LiteratureAgent:
    """
    Think→Act→Observe 多轮文献检索与证据整合 Agent。

    用法:
        agent = LiteratureAgent(llm_client=client, config=config)
        review: LiteratureReview = agent.run("CSTB in colorectal cancer prognosis")
    """

    def __init__(self, llm_client: LLMClient, config: dict):
        """初始化 Agent，注入 LLM 客户端和配置。"""

    def run(self, question: str) -> LiteratureReview:
        """
        执行完整的文献调研流程：
        1. 分解问题 → 生成初始搜索
        2. Think→Act→Observe 多轮循环（最多 3 轮）
        3. 证据整合（EvidenceSynthesizer）
        4. 假设生成（HypothesisGenerator）
        5. 返回结构化的 LiteratureReview

        Raises:
            NetworkError: 代理不可用
            PubMedAPIError: PubMed API 返回错误
            TokenBudgetExceededError: 超过 token 预算
        """

    @property
    def name(self) -> str:
        """Agent 名称，用于日志记录和 Step 2 的 benchmark 报告。"""
        return "LiteratureAgent"
```

#### EvidenceSynthesizer（S3 可独立使用）

```python
class EvidenceSynthesizer:
    """
    多论文 → 结构化证据链 → 300-500字证据整合摘要。

    用法:
        synth = EvidenceSynthesizer(llm_client=client)
        result = synth.synthesize(papers: list[Paper], question: str) -> tuple[
            list[EvidenceLink],  # 证据链
            str,                 # evidence_summary
            float,               # confidence
            list[str],           # knowledge_gaps
            list[str]            # citations
        ]
    """

    def synthesize(
        self, papers: list[Paper], question: str
    ) -> tuple[list[EvidenceLink], str, float, list[str], list[str]]:
        """从论文列表生成结构化的证据整合结果。
        
        Args:
            papers: 相关论文列表（通常 8-15 篇）
            question: 原始研究问题
            
        Returns:
            evidence_chain: 原子主张列表，每个带 supporting_pmids + strength
            evidence_summary: 300-500字整合摘要
            confidence: 整体置信度 [0,1]
            knowledge_gaps: 发现的证据缺口
            citations: 格式化引用列表
            
        Raises:
            ValueError: papers 为空列表
            LLMError: LLM 调用失败
        """
```

#### HypothesisGenerator（S3 可独立使用）

```python
class HypothesisGenerator:
    """
    证据缺口 → 可验证假设。

    用法:
        gen = HypothesisGenerator(llm_client=client)
        hypotheses = gen.generate(
            evidence_chain=links,
            knowledge_gaps=gaps,
            question=question
        )
    """

    def generate(
        self,
        evidence_chain: list[EvidenceLink],
        knowledge_gaps: list[str],
        question: str
    ) -> list[Hypothesis]:
        """从证据链和知识缺口生成 1-3 个可验证假设。
        
        Args:
            evidence_chain: EvidenceSynthesizer 产出的证据链
            knowledge_gaps: 证据缺口列表
            question: 原始研究问题
            
        Returns:
            hypotheses: 1-3 个 Hypothesis，已含 novelty 分类
            
        Raises:
            ValueError: evidence_chain 为空
            LLMError: LLM 调用失败
        """
```

#### LLMClient（S3 的其他 Agent 共用）

```python
@dataclass
class LLMResponse:
    content: str
    input_tokens: int
    output_tokens: int
    model: str
    finish_reason: str

class LLMClient:
    """
    统一 LLM 调用客户端。所有 Step 共用。

    用法:
        client = LLMClient(model="deepseek-v4-pro", temperature=0.3)
        response = client.chat(messages=[...], max_tokens=2000)
    """

    def __init__(self, model: str = "deepseek-v4-pro", temperature: float = 0.3):
        """初始化客户端。从 ~/.claude/settings.json 读取 ANTHROPIC_AUTH_TOKEN + ANTHROPIC_BASE_URL。"""

    def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int = 2000,
        tools: list[dict] | None = None,
        system: str | None = None,
    ) -> LLMResponse:
        """同步 LLM 调用。自动记录 token 用量。system 参数用于传入 Layer 1 反幻觉约束块。"""

    def check_connectivity(self) -> bool:
        """检查 LLM API 是否可达（通过代理）。"""
```

#### Embedder（抽象接口，S3/S4 可替换实现）

```python
class Embedder(ABC):
    """嵌入/排序器抽象接口。当前实现: LLMRerank。"""

    @abstractmethod
    def rank(self, query: str, papers: list[Paper], top_k: int = 10) -> RerankResult:
        """对论文列表按与查询的相关性排序，返回 top-K 结果。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """实现名称，用于日志。"""


class LLMRerank(Embedder):
    """
    使用 LLM（deepseek-v4-pro）做语义重排序。
    不依赖 embedding API，通过 LLM 逐批判断论文相关性。

    流程：每批 10 篇论文 → LLM 打分 0-1 → 合并排序 → 返回 top-K
    """

    def __init__(self, llm_client: LLMClient, batch_size: int = 10):
        ...

    def rank(self, query: str, papers: list[Paper], top_k: int = 10) -> RerankResult:
        ...
```

#### Retriever

```python
class PubMedRetriever:
    """
    PubMed EUtils 检索 + 结果解析 + 本地缓存。

    用法:
        retriever = PubMedRetriever(cache_dir="./data/pubmed_cache")
        result = retriever.search(SearchQuery("CSTB[Gene] AND colorectal cancer[MeSH]", max_results=50))
    """

    def search(self, query: SearchQuery, retrieval_round: int = 1) -> SearchResult:
        """
        执行 PubMed 检索。

        步骤：
        1. 检查本地缓存（query string → 缓存文件）
        2. 缓存未命中 → esearch → efetch → 解析 XML
        3. 写入缓存
        4. 返回 SearchResult

        Raises:
            NetworkError: 代理不可用
            PubMedAPIError: EUtils 返回错误（3 次重试后）
        """
```

### 3.2 接口依赖关系图

```
外部消费方:
  Step 2 → LiteratureReview, Paper, Hypothesis (类型), LiteratureAgent.run() (方法)
  Step 3 → LiteratureAgent (完整), EvidenceSynthesizer, HypothesisGenerator, LLMClient, Embedder
  Step 4 → 10个query的LiteratureReview结果 (JSON)

S1 内部依赖链:
  types.py  ← 无依赖
  utils/network.py  ← 无依赖
  llm/client.py  ← utils/network.py, types.py
  rag/retriever.py  ← utils/network.py, types.py
  rag/embedder.py  ← llm/client.py, types.py
  rag/synthesizer.py  ← llm/client.py, types.py
  rag/hypothesis_generator.py  ← llm/client.py, types.py
  tools/pubmed_tools.py  ← rag/retriever.py, types.py
  agents/literature_agent.py  ← 上述所有
  demo/run_literature_review.py  ← agents/literature_agent.py
```

---

## 四、DATA FLOW DIAGRAM

### 主流程：LiteratureAgent.run(question)

```
USER QUESTION: "CSTB 在结直肠癌中的预后价值"
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│ Phase 0: 问题分解 (LLM 调用 #1)                               │
│  输入: user question                                          │
│  处理: LLMClient.chat(prompt=QUESTION_DECOMPOSE)               │
│  输出: list[SearchQuery] (1-3个子查询，每个含 MeSH + 自由词)   │
│  token: ~500 in + ~200 out                                    │
└──────────────┬───────────────────────────────────────────────┘
               │ list[SearchQuery]
               ▼
┌──────────────────────────────────────────────────────────────┐
│ Phase 1: 多轮检索循环 (Think→Act→Observe, 最多 3 轮)          │
│                                                              │
│  循环入口 (round N):                                          │
│    Think (LLM 调用 #2.N):                                     │
│      - 审查上一轮 Observation                                 │
│      - 判断是否需要、以及为什么需要补充检索                     │
│      - 输出: str (思考结果) + continue_flag (bool)             │
│      token: ~300 in + ~150 out                                │
│                                                              │
│    闸门 1: max_rounds check (硬限制 ≤3)                       │
│    闸门 2: 查询去重 (LLM 判定: "这个查询和之前的本质相同吗?")   │
│    闸门 3: token 预算 (累计 < 15000)                           │
│    → 任意闸门关闭 → break → 进入 Phase 2                      │
│                                                              │
│    Act: PubMedRetriever.search(new_query)                     │
│      输出: SearchResult (≤50篇论文)                            │
│                                                              │
│    Observe: LLMRerank.rank(query, papers, top_k=10)           │
│      (LLM 调用 #3.N): 逐批判断相关性，输出 top-10               │
│      token: ~150 per batch × ceil(papers/10) batches          │
│    输出: RerankResult (10篇带 relevance_score 的论文)          │
│                                                              │
│  退出条件（满足任一）:                                         │
│    - round = 3（硬上限）                                      │
│    - LLM Think 返回 continue=False                            │
│    - 累计 token > 15000                                       │
│    - 查询去重检测到重复                                        │
└──────────────┬───────────────────────────────────────────────┘
               │ list[Paper] (去重合并后通常 10-20 篇)
               ▼
┌──────────────────────────────────────────────────────────────┐
│ Phase 2: 证据整合 (LLM 调用 #4)                               │
│  输入: papers (全部检索结果去重) + user question               │
│  处理: EvidenceSynthesizer.synthesize()                       │
│    Step A: 提取原子主张 (claim extraction)                     │
│    Step B: 为每个主张分配 supporting_pmids                     │
│    Step C: 判定 strength + 输出 justification                 │
│    Step D: 硬矛盾检测 (Layer 2, 4条if语句)                     │
│    Step E: 可选二次确认 (Layer 3, 针对 strong claims)          │
│    Step F: 生成 evidence_summary (300-500字)                   │
│  输出: (evidence_chain, summary, confidence, gaps, citations)  │
│  token: ~2000 in + ~800 out (+ 二次确认 ~500)                  │
└──────────────┬───────────────────────────────────────────────┘
               │ evidence_chain + gaps
               ▼
┌──────────────────────────────────────────────────────────────┐
│ Phase 3: 假设生成 (LLM 调用 #5)                               │
│  输入: evidence_chain + knowledge_gaps + user question         │
│  处理: HypothesisGenerator.generate()                         │
│    Step A: 从 knowledge_gaps 识别"已知-未知"边界               │
│    Step B: 生成候选假设                                        │
│    Step C: 评估每个假设的 testable_prediction                  │
│    Step D: 判定 novelty (二分类 + justification)               │
│    Step E: 选择最优 1-3 个假设                                 │
│  输出: list[Hypothesis]                                       │
│  token: ~1000 in + ~500 out                                   │
└──────────────┬───────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────┐
│ Phase 4: 组装 LiteratureReview                                │
│  聚合全部数据 → 建 LiteratureReview dataclass                  │
│  校验: __post_init__ 全覆盖                                   │
│  token_usage: 累计所有 LLM 调用的 input + output               │
└──────────────┬───────────────────────────────────────────────┘
               │ LiteratureReview
               ▼
            返回 / 持久化为 JSON
```

### LLM 调用次数估算

| Phase | 调用次数 | 说明 |
|-------|---------|------|
| 0 (问题分解) | 1 | 固定 |
| 1 (多轮检索) | `N × 2` 到 `N × (2 + batches)` | N=轮数(1-3), Think=1次/轮, Rerank=1次×ceil(papers/10)批 |
| 2 (证据整合) | 1 + 可选(strong_count次) | 二次确认仅针对 strong claims |
| 3 (假设生成) | 1 | 固定 |
| **总计** | **4-12 次** | 最坏情况: 3轮×2 + 3批rerank + 2证据整合 +1假设 = 12次 |

### Token 预算估算

| 场景 | 估计 token |
|------|-----------|
| 最简（1轮，10篇论文） | ~4000 |
| 典型（2轮，15-20篇论文） | ~8000 |
| 最复杂（3轮，25-30篇论文） | ~12000 |
| 硬上限 | 15000（代码层强制） |

---

## 五、PROMPT TEMPLATES

### 通用前缀：Layer 1 反幻觉约束块

以下约束块**嵌入该 Step 中每一个 LLM 调用的 system prompt**（共 5 种 prompt 模板）。

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

### Prompt 1: 问题分解（QUESTION_DECOMPOSE）

**调用位置**: Phase 0, `LiteratureAgent._decompose_question()`

**System Prompt**:
```
You are a biomedical research methodologist. Your task is to decompose a 
research question into PubMed-searchable sub-questions.

Given a complex biomedical question, break it down into 1-3 focused sub-questions, 
each targeting a specific dimension of evidence:
- Clinical/epidemiological evidence (prognosis, diagnosis, prevalence)
- Molecular mechanism evidence (pathway, interaction, function)
- Therapeutic evidence (drug response, target, clinical trial)

For each sub-question, output a PubMed-ready search string using:
- MeSH terms where possible
- Boolean operators (AND, OR, NOT)
- Field tags ([MeSH], [tiab], [gene])

{LAYER_1_CONSTRAINTS_BLOCK}

## OUTPUT FORMAT (JSON)
[
  {
    "sub_question": "What is the association between CSTB expression and prognosis in colorectal cancer patients?",
    "search_query": "CSTB[gene] AND (colorectal neoplasms[MeSH] OR colorectal cancer[tiab]) AND (prognosis[MeSH] OR survival[tiab])",
    "dimension": "clinical",
    "rationale": "..."
  },
  ...
]
```

**User Prompt**:
```
Research question: {question}

Decompose this question into focused PubMed search queries.
```

**输入变量**: `{question}` — 用户原始研究问题
**预期输出**: JSON 数组，每个元素含 sub_question / search_query / dimension / rationale

---

### Prompt 2: Think 阶段（AGENT_THINK）

**调用位置**: Phase 1 每轮循环, `LiteratureAgent._think()`

**System Prompt**:
```
You are a biomedical literature analyst conducting a systematic review.
You are in the THINK phase of a multi-round literature search process.

Your task is to review the evidence collected so far and decide:
1. Is the evidence sufficient to synthesize a reliable answer?
2. If NOT sufficient — what specific gap exists, and what new search would fill it?
3. If sufficient — say "SUFFICIENT" and prepare to synthesize.

When judging sufficiency, consider:
- Do we have evidence on ALL dimensions of the original question?
- For each dimension, do we have at least 2 independent studies?
- Are there blatant contradictions that need resolution?
- Is there a major dimension completely unaddressed?

{LAYER_1_CONSTRAINTS_BLOCK}

## OUTPUT FORMAT (JSON)
{
  "decision": "CONTINUE" | "SUFFICIENT",
  "reasoning": "Detailed reasoning about evidence status...",
  "gap_description": "If CONTINUE: what specific gap? If SUFFICIENT: null",
  "new_search_query": "If CONTINUE: PubMed-ready search string. If SUFFICIENT: null",
  "confidence_in_decision": 0.0-1.0
}
```

**User Prompt**:
```
Original question: {question}

Round {round_number} of {max_rounds}.

Evidence collected so far ({total_papers} papers across {round_number} rounds):

{evidence_summary_from_previous_rounds}

Search queries already executed:
{previous_queries}

Should we continue to another search round, or is the evidence sufficient?
```

**输入变量**: `{question}`, `{round_number}`, `{max_rounds}`, `{total_papers}`, `{evidence_summary_from_previous_rounds}`, `{previous_queries}`
**预期输出**: JSON，含 decision / reasoning / gap_description / new_search_query / confidence_in_decision

---

### Prompt 3: LLM Rerank（LLM_RERANK）

**调用位置**: Phase 1 Observe 阶段, `LLMRerank.rank()`

**System Prompt**:
```
You are a biomedical research assistant. Rate the relevance of each paper 
to the given research question. Use a 0-1 scale:
- 1.0 = Directly answers the question, core evidence
- 0.7-0.9 = Highly relevant, provides important supporting evidence
- 0.4-0.6 = Somewhat relevant, tangentially related
- 0.1-0.3 = Marginally relevant
- 0.0 = Not relevant

Consider: Does this paper's topic, findings, and population match the question?

{LAYER_1_CONSTRAINTS_BLOCK}

## OUTPUT FORMAT (JSON)
[
  {"pmid": "12345678", "score": 0.8, "reason": "one sentence why"},
  ...
]
```

**User Prompt**:
```
Research question: {question}

Papers to rate:
{paper_list_json}

Rate each paper's relevance. Return JSON array.
```

**输入变量**: `{question}`, `{paper_list_json}` — JSON 数组，每项含 pmid, title, abstract (截断到 500 字符)
**预期输出**: JSON 数组，每项含 pmid / score / reason
**批处理**: 每批 10 篇，合并后按 score 降序，取 top-K

---

### Prompt 4: 证据整合（EVIDENCE_SYNTHESIS）

**调用位置**: Phase 2, `EvidenceSynthesizer.synthesize()`

**System Prompt**:
```
You are a biomedical evidence synthesis expert. Your task is to:

1. Extract atomic claims from the provided papers
2. For each claim, identify supporting PMIDs
3. Assess claim strength using this framework:
   - "strong": Multiple independent studies (ideally ≥3), consistent direction, 
     large sample sizes, prospective design
   - "moderate": 1-2 independent studies, or multiple small studies, or some 
     inconsistency
   - "weak": Single small study, case report, expert opinion, or substantial 
     conflicting evidence
   - "unverified": No supporting PMID can be found for this claim in the 
     provided papers (this should be RARE — avoid generating such claims)
4. Provide a strength_justification for EVERY claim
5. If counter-evidence exists in the papers, document it
6. Generate a 300-500 word evidence summary

IMPORTANT: Every claim MUST have at least 1 supporting PMID from the 
provided papers. If a claim would have 0 PMIDs, DO NOT include it.

{LAYER_1_CONSTRAINTS_BLOCK}

## OUTPUT FORMAT (JSON)
{
  "evidence_chain": [
    {
      "claim": "CSTB is significantly overexpressed in colorectal cancer...",
      "supporting_pmids": ["12345678", "23456789"],
      "strength": "strong",
      "strength_justification": "3 independent cohorts, total n>2000, consistent direction of upregulation, all used TCGA and GEO validation",
      "counter_evidence": null
    },
    ...
  ],
  "evidence_summary": "300-500 word synthesis...",
  "confidence": 0.75,
  "knowledge_gaps": [
    "No published study examining CSTB protein levels by IHC in CRC",
    "No randomized trial data on CSTB as a treatment selection biomarker"
  ],
  "citations": [
    "[PMID:12345678] Smith et al. (2023) CSTB overexpression in colorectal cancer...",
    ...
  ]
}
```

**User Prompt**:
```
Research question: {question}

Papers to synthesize ({count} papers):
{paper_list_with_abstracts}

Synthesize the evidence. Ensure every claim has at least 1 supporting PMID.
```

**输入变量**: `{question}`, `{count}`, `{paper_list_with_abstracts}` — 去重合并后的全部相关论文（10-20篇）
**预期输出**: JSON，含 evidence_chain / evidence_summary / confidence / knowledge_gaps / citations

**二次确认 Prompt**（仅针对 strong claims，可选调用，Synthesizer 内部触发）:
```
## QUICK REVIEW

Review this evidence claim marked as "strong":

Claim: {claim}
Supporting PMIDs: {pmid_list}
Justification: {justification}

Question: Is there any reason in the provided papers to downgrade this 
from "strong" to "moderate" or "weak"? Consider: small sample sizes, 
conflicting results, single research group, or missing controls.

Answer ONLY: "KEEP" or "DOWNGRADE: <one sentence reason>"
```
**触发条件**: `strength == "strong"` 且 `len(supporting_pmids) < 3`（即LLM声称strong但证据数量偏少的边界情况）
**输入变量**: `{claim}`, `{pmid_list}`, `{justification}`
**预期输出**: "KEEP" 或 "DOWNGRADE: <reason>"

---

### Prompt 5: 假设生成（HYPOTHESIS_GENERATION）

**调用位置**: Phase 3, `HypothesisGenerator.generate()`

**System Prompt**:
```
You are a creative but rigorous biomedical scientist. Your task is to 
generate testable hypotheses from the boundary between what is known 
and what is unknown.

Rules:
1. Each hypothesis MUST be grounded in the provided evidence chain
2. Each hypothesis MUST have a specific, falsifiable prediction
3. Each hypothesis MUST specify what data would be needed to test it
4. Classify each as:
   - "novel_to_our_knowledge": No paper in the provided evidence chain directly 
     proposes this hypothesis
   - "supported_by_existing": The hypothesis or close variants appear in 
     the provided papers (even if not yet validated)
5. Provide a novelty_justification explaining the classification
6. Generate 1-3 hypotheses — quality over quantity

A good hypothesis fills an evidence gap without overreaching.
A bad hypothesis invents genes, pathways, or mechanisms not mentioned in the papers.

{LAYER_1_CONSTRAINTS_BLOCK}

## OUTPUT FORMAT (JSON)
[
  {
    "statement": "CSTB promotes immune evasion in CRC through M2 macrophage polarization",
    "rationale": "Evidence chain shows (a) CSTB associated with poor prognosis [PMID:...], (b) CSTB expression correlates with M2 markers in TCGA [PMID:...], but no study has examined the mechanistic link",
    "testable_prediction": "CSTB knockdown in CRC cell lines reduces M2 polarization markers (CD163, CD206) in co-culture with monocytes",
    "required_data": ["CRC cell lines with CSTB knockdown", "monocyte co-culture system", "M2 marker flow cytometry panel"],
    "novelty": "novel_to_our_knowledge",
    "novelty_justification": "No paper in the evidence chain directly tested the CSTB→M2 polarization mechanistic link; existing studies only report correlation"
  }
]
```

**User Prompt**:
```
Research question: {question}

Evidence chain ({n_links} claims):
{evidence_chain_json}

Knowledge gaps identified:
{knowledge_gaps}

Generate 1-3 testable hypotheses based on the known-unknown boundary.
```

**输入变量**: `{question}`, `{evidence_chain_json}`, `{knowledge_gaps}`
**预期输出**: JSON 数组，每项含 statement / rationale / testable_prediction / required_data / novelty / novelty_justification

---

### Prompt 汇总表

| # | Prompt ID | LLM 调用次数 | 每次 token (估) | Layer 1 约束 |
|---|-----------|-------------|----------------|-------------|
| 1 | QUESTION_DECOMPOSE | 1 | ~700 | ✅ |
| 2 | AGENT_THINK | 1-3 | ~450 | ✅ |
| 3 | LLM_RERANK | 1-3 批 | ~500/批 | ✅ |
| 4 | EVIDENCE_SYNTHESIS | 1 + 可选二次确认 | ~2800 + ~300 | ✅ |
| 5 | HYPOTHESIS_GENERATION | 1 | ~1500 | ✅ |

---

## 六、ANTI-HALLUCINATION MEASURES

### 6.1 防线实现映射

| 防线层 | 该 Step 实现位置 | 具体机制 | 代码量 |
|--------|-----------------|---------|--------|
| **Layer 1** (Prompt) | 所有 5 个 Prompt 模板 | 通用约束块嵌入每个 system prompt | 模板内嵌 |
| **Layer 2** (结构) | `types.py` — `EvidenceLink.__post_init__` | 4 条硬矛盾检测（见下文） | ~15 行 |
| **Layer 3** (后验) | `rag/synthesizer.py` — `PMIDVerifier` | V1: PMID 存在性检查；V2: 基因名验证；V4: 一致性检查 | ~80 行 |
| **Layer 5** (人工) | Demo 输出 + 成功标准验证 | 所有 strong claims 输出供人工抽查 | 你执行 |

注意：Layer 4（交叉验证）在 S3 实现，S1 不负责任何交叉验证。

### 6.2 Layer 2 硬矛盾检测（4 条 if 语句）

位置：`types.py` 中 `EvidenceLink.__post_init__()`

```
检测 1: strength ∈ {strong, moderate} AND len(supporting_pmids) == 0
       → ValueError，拒绝创建该 EvidenceLink
       
检测 2: strength == "strong" AND counter_evidence is not None
       → ValueError，拒绝创建
       
检测 3: strength ∈ {strong, moderate, weak} AND strength_justification 为空
       → ValueError，拒绝创建
       
检测 4: len(supporting_pmids) == 0 AND counter_evidence is None
       → strength 强制设为 "unverified"（唯一合法的情况：纯推测但标记了）
```

这 4 条检测在 dataclass 初始化时自动执行，不需要额外的验证调用。如果 LLM 输出不符合这些约束，`from_dict()` 工厂函数会捕获 ValueError 并记录，不会静默通过。

### 6.3 Layer 3 后验验证管线

位置：`rag/synthesizer.py` → `PMIDVerifier` 类

```
LLM 输出（evidence_chain JSON）
    │
    ▼
V1: PMID 存在性检查
    def _verify_pmids(evidence_chain, all_retrieved_pmids: set[str]):
        for link in evidence_chain:
            valid = [p for p in link.supporting_pmids if p in all_retrieved_pmids]
            suspicious = [p for p in link.supporting_pmids if p not in all_retrieved_pmids]
            if suspicious:
                log.warning(f"Claim '{link.claim[:50]}...' references PMIDs not in retrieved set: {suspicious}")
                # 移除不在检索结果中的 PMID
                link.supporting_pmids = valid
                # 如果移除后为空且 strength 不是 unverified → 重新检测硬矛盾
    │
    ▼
V2: 基因名验证（NEW — 该 Step 特有）
    def _verify_gene_names(text: str, known_genes: set[str]):
        # 提取所有大写字串（如 CSTB, TP53, EGFR）
        # 检查是否在 NCBI 已知基因符号列表中（本地加载的 gene_info 子集）
        # 如果出现不在列表中的基因 → 标记 warning
        # 注意：这不是硬错误，因为可能是 LLM 正确引用了新发现的基因
    │
    ▼
V4: 一致性检查（跨 evidence_chain）
    def _check_consistency(evidence_chain):
        # 检测矛盾：两个 claim 对同一个基因/疾病给出相反方向的结论
        # 例如：claim1="CSTB 高表达与预后差相关" vs claim2="CSTB 与预后无关"
        # 这不是错误，而是需要标记的 evidence conflict
        # 如果检测到矛盾 → 在 evidence_summary 中增加 "conflicting evidence exists" 描述
        
        # ⚠️ 基因名归一化：生物医学文本中同一基因有多种表达方式
        # （CSTB / cystatin B / stefin B / Cystatin-B）
        # 实现时必须做最小限度的别名展开，否则会漏掉矛盾检测：
        #   - 加载 NCBI gene_info 的 Symbol + Synonyms 字段构建别名表
        #   - 对每个 claim 中的基因实体，归一化到官方 Symbol 后再比较
        #   - 如果本地无 gene_info，降级为精确字符串匹配 + 在代码注释中标注已知局限
        # 疾病名同理（colorectal cancer / CRC / colon carcinoma），
        # 但疾病归一化优先级低（无标准字典），先做基因归一化
```

### 6.4 该 Step 特有的四种幻觉风险及应对

| 风险 | 表现 | 应对（该 Step 的实现） |
|------|------|----------------------|
| **论文幻觉** | 引用不存在的 PMID | V1: `_verify_pmids()` — 交叉比对检索结果集 |
| **断章取义** | 引用了真实论文但歪曲了结论 | Layer 5: 人工抽样验证（S1 的审阅清单要求至少查 3 篇原文） |
| **过度推断** | 从"相关"推出"因果"，从"体外"推出"体内" | Prompt 1-5 中的 Layer 1 约束 + strength 必须带 justification（LLM 自证） |
| **检索偏见** | 只检索支持预设结论的论文 | 多轮检索的 Think prompt 要求 LLM 主动查找 counter_evidence；如果 counter_evidence 全部为 None，二次确认 prompt 会询问 |

### 6.5 降级策略：LLM 不可用时的退化行为

如果 LLM API 不可用（代理断开、API 配额耗尽等），系统必须优雅降级，不能直接崩溃：

```
Phase 0 (问题分解) → 使用简单规则替代：按 "AND" 分割原问题，生成单个宽泛查询
Phase 1 (Think) → 跳过，固定执行 1 轮检索
Phase 1 (Rerank) → 跳过，保留 PubMed 默认相关性排序
Phase 2 (证据整合) → 跳过，创建占位 EvidenceLink:
    EvidenceLink(
        claim="LLM_UNAVAILABLE: evidence synthesis skipped",
        supporting_pmids=[],
        strength="unverified",
        strength_justification="LLM API unavailable during degradation mode",
        counter_evidence=None
    )
    confidence = 0.0, knowledge_gaps = ["LLM unavailable — no evidence synthesis performed"]
Phase 3 (假设生成) → 跳过，创建占位 Hypothesis:
    Hypothesis(
        statement="LLM_UNAVAILABLE: hypothesis generation skipped",
        rationale="LLM API unavailable during degradation mode",
        testable_prediction="N/A — hypothesis generation requires LLM",
        required_data=["N/A"],
        novelty="supported_by_existing",
        novelty_justification="Degradation mode — no novelty assessment possible"
    )
Phase 4 (组装) → 产出 LiteratureReview，confidence = 0.0
    注意：占位 EvidenceLink 和 Hypothesis 对象满足 __post_init__ 的结构约束
    （evidence_chain 非空、hypotheses 长度 1-3）
```

**降级后仍然返回有效的 LiteratureReview 对象**（不是抛异常）。占位对象确保 `__post_init__` 的所有结构约束都能通过，但内容明确标记为 `LLM_UNAVAILABLE`，下游消费者可以通过检查 `confidence == 0.0` 和 `strength == "unverified"` 判断这是降级产出。这让 Step 2 的 benchmark 仍可评估"LLM 不可用时的 Agent 行为"。

---

## 附录 A：与已有资产的整合映射

| 已有资产 | 整合到 |
|---------|--------|
| `CSTB_paper/references/fetch_pubmed.py` — esearch + efetch + XML 解析 | `rag/retriever.py`：复用 PubMed API 调用模式，增加缓存层 |
| `shared/gfw_probe.py` — proxy_check + 3-retry backoff | `utils/network.py`：直接复制，微调为 `ensure_network()` + `NetworkError` |
| `生信分析/spatial_agent/modules/m3_llm_enhancer.py` — DeepSeek 调用 + "DO NOT fabricate" | `llm/client.py`：复用 LLM 调用封装，提取 temperature=0.3 和反幻觉约束 |

## 附录 B：与 00- 共享类型的对应关系

| 00- §二 类型 | 本文档位置 | 差异说明 |
|-------------|-----------|---------|
| `Paper` | §2.1 | 新增 `relevance_score: float \| None`；`embedding` 字段保留但始终为 None |
| `LiteratureReview` | §2.1 | 与 00- 完全一致 |
| `EvidenceLink` | §2.1 | 新增 `strength_justification: str`（LLM 自证要求）；`strength` 增加 `"unverified"` 选项 |
| `Hypothesis` | §2.1 | `novelty` 从三分类简化为二分类（`"novel_to_our_knowledge"` / `"supported_by_existing"`）；新增 `novelty_justification: str` |

**需要在 00- §六 回写的决策**：
- D-001: Embedding 模型 — 选择 LLM Rerank 路线，无 embedding 模型，无向量数据库
- D-002: EvidenceLink strength — LLM 自证 + 硬矛盾检测（4 if），规则只降不升
- D-003: Hypothesis novelty — 二分类（novel_to_our_knowledge / supported_by_existing）
- D-006 (新增): 多轮检索触发 — LLM 提议 + 三道闸门（max_rounds=3, 查询去重, token预算=15000）

---

> **⏸️ DESIGN DRAFT READY** — 等待 Reviewer (窗口 1-B: Bioinformatics Researcher) 交叉审查。
