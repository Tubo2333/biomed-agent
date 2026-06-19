# 03 — Step 3 详细设计文档：多 Agent 协作闭环 Pipeline

> **状态**：Stage 1 设计深化 — DESIGN LOCKED（第二轮交叉审查通过：0 BLOCKER, 0 MINOR）
> **作者**：Multi-Agent Systems Architect (窗口 3-A)
> **审查**：Bioinformatics Pipeline Engineer (窗口 3-B)，两轮审查（初审 10 MINOR + 再审全部通过）
> **依赖**：`00-master-coordination.md` §二（共享类型）、§四（设计哲学）；Step 1 的 `LiteratureAgent`（完整实现）；Step 2 的 `BenchmarkTask`/`EvalAgent` Protocol
> **同步产出**：本文档一旦锁定，所有实现必须严格遵循。偏差必须先更新本文档。

---

## 一、MODULE BREAKDOWN

### 文件清单（共 8 个文件）

```
biomed-agent/
├── src/
│   └── agents/
│       ├── orchestration_agent.py   # A2: LLM 驱动的动态 DAG 规划
│       ├── analysis_agent.py        # A3: Think→Act→Observe 分析执行
│       ├── report_agent.py          # A4: 多源聚合 + 结构化报告 + Layer 4 交叉验证
│       └── pipeline.py              # AgentOrchestrator: 串联 4 Agent + EvalAgent Protocol
│   └── tools/
│       ├── tcga_tools.py            # TCGA 数据查询（缓存 + 实时 Python 三层回退）
│       ├── survival_tools.py        # 生存分析工具（缓存查询 + 结果解释）
│       ├── drug_tools.py            # GDSC2 药物筛选工具（实时 Python Spearman）
│       └── immune_tools.py          # 免疫浸润关联工具（实时 Python）
├── data/
│   └── cache/
│       ├── analysis_cache_index.json # 缓存索引：数据集→分析类型→文件路径+Schema
│       ├── tcga_coad_deg.json        # 差异表达缓存
│       └── tcga_coad_surv.json       # 生存分析缓存
├── demo/
│   └── run_pipeline.py              # 端到端 Demo：CSTB-CRC 完整 case study
└── tests/
    ├── test_orchestration_agent.py
    ├── test_analysis_agent.py
    ├── test_report_agent.py
    ├── test_pipeline.py
    ├── test_tcga_tools.py
    ├── test_survival_tools.py
    ├── test_drug_tools.py
    ├── test_immune_tools.py
    ├── test_layer4_cross_validation.py
    ├── test_adversarial.py          # 注入测试（P0-5, P1-4）
    └── test_evalagent_protocol.py   # S2 Benchmark 集成测试
```

### 文件职责与依赖

| # | 文件 | 单一职责 | 大约行数 | 依赖 |
|---|------|---------|---------|------|
| 1 | `agents/orchestration_agent.py` | LLM 驱动动态 DAG 生成：从 LiteratureReview 推理分析计划 | 300 | S1: `types.py` 的 LiteratureReview/Hypothesis；LLMClient |
| 2 | `agents/analysis_agent.py` | Think→Act→Observe 分析执行 + F1-F5 失败恢复 + 决策日志 | 350 | S1: LLMClient；tools/*；S2: BenchmarkTask（类型） |
| 3 | `agents/report_agent.py` | 多源整合 + Layer 4 交叉验证（A4→A3） + 效应量检查 + 结构化报告 | 350 | S1: `types.py`；内置类型 AnalysisResult/AnalysisPlan |
| 4 | `agents/pipeline.py` | AgentOrchestrator 串联 + Layer 4 交叉验证（A2→A1, A3→A2） + EvalAgent Protocol 适配 (Task Router) | 200 | 上述所有 Agent；S2: `BenchmarkTask`/`EvalAgent` |
| 5 | `tools/tcga_tools.py` | TCGADataAccessor：三层回退（缓存→实时Python→F4）+ 数据→方法兼容矩阵 | 200 | 缓存索引 JSON；pandas；scipy.stats |
| 6 | `tools/survival_tools.py` | 生存分析工具：缓存查询 + F3 降级（PH 违反→KM+log-rank） | 200 | TCGADataAccessor；S3 内部类型 AnalysisResult |
| 7 | `tools/drug_tools.py` | GDSC2 药物筛选：实时 Python Spearman + FDR 校正 | 150 | pandas；scipy.stats；GDSC2 数据 |
| 8 | `tools/immune_tools.py` | 免疫浸润关联：基因 vs 免疫细胞丰度 Spearman 相关 | 150 | pandas；scipy.stats；免疫浸润数据 |

**说明**：
- 无 `vector_store.py` 和 `embedder.py`：S3 不负责 RAG——LiteratureAgent 已在 S1 完整实现。
- 无消息队列/MessageBus：4 Agent 在同一 Python 进程中顺序执行，用函数参数传递数据。科研工作流天然是顺序的。
- 无并发框架：内层 DAG 的并行（max 2）用 Python threading（简单场景），不引入 asyncio。
- 所有文件 ≤ 400 行（较 00- §四的 500 行约束更紧）。
- `pipeline.py` 中的 `validate_upstream()` 方法实现 A2→A1 和 A3→A2 两个交叉验证节点（~80行/节点）；A4→A3 节点在 `report_agent.py`。

---

## 二、DATA MODEL SPEC

### 2.1 共享类型（S3 新增，需回写 00- §二，S4 消费）

#### AnalysisNode（DAG 的一个节点）

```python
@dataclass
class AnalysisNode:
    """DAG 中的一个分析节点。A2 的 LLM 推理产出。"""
    node_id: str                          # "node_01_diff_expression"，唯一标识，必填
    task: str                             # 分析类型（见 TASK_VOCABULARY），必填
    gene_list: list[str]                  # 目标基因列表，至少 1 个
    data_source: str                      # 数据文件绝对路径，必填
    method: str                           # 分析方法名（见 METHOD_VOCABULARY），必填
    parameters: dict[str, Any]            # 方法参数，可为空
    depends_on: list[str]                 # 依赖的 node_id 列表（拓扑边），可为空
    rationale: str                        # LLM 为什么选择这个方法，必填（反模板机制）

    TASK_VOCABULARY = frozenset({
        "differential_expression", "survival_analysis",
        "immune_correlation", "drug_screening",
        "gene_gene_correlation", "pathway_enrichment"
    })

    METHOD_VOCABULARY = frozenset({
        "ttest", "mann_whitney", "limma_voom",
        "cox_regression", "km_logrank",
        "spearman", "pearson",
        "fdr_bh", "fdr_bonferroni"
    })

    def __post_init__(self):
        if not self.node_id or not self.node_id.strip():
            raise ValueError("node_id must not be empty")
        if self.task not in self.TASK_VOCABULARY:
            raise ValueError(f"task must be one of {self.TASK_VOCABULARY}")
        if not self.gene_list:
            raise ValueError("gene_list must not be empty")
        if self.method and self.method not in self.METHOD_VOCABULARY:
            raise ValueError(f"method must be one of {self.METHOD_VOCABULARY}")
        if not self.rationale or not self.rationale.strip():
            raise ValueError("rationale is required for anti-template enforcement")
        if not self.data_source:
            raise ValueError("data_source must not be empty")
```

#### AnalysisPlan（A2 输出 = 动态 DAG）

```python
@dataclass
class AnalysisPlan:
    """LLM 驱动的动态分析计划。不同的 LiteratureReview → 不同的 AnalysisPlan。"""
    question: str                         # 原始研究问题
    hypotheses: list[Hypothesis]          # 来自 A1 的 LiteratureReview.hypotheses
    nodes: list[AnalysisNode]             # DAG 节点列表，至少 1 个
    edges: list[tuple[str, str]]          # (from_node_id, to_node_id)，拓扑边
    data_gaps: list[str]                  # A2 标记的"数据无法覆盖的预测"

    def __post_init__(self):
        if not self.nodes:
            raise ValueError("AnalysisPlan must have at least 1 node")
        if not self.hypotheses:
            raise ValueError("AnalysisPlan must reference at least 1 hypothesis")
        # 验证所有 edges 引用的 node_id 都在 nodes 中
        node_ids = {n.node_id for n in self.nodes}
        for from_id, to_id in self.edges:
            if from_id not in node_ids:
                raise ValueError(f"Edge references unknown node: {from_id}")
            if to_id not in node_ids:
                raise ValueError(f"Edge references unknown node: {to_id}")
```

#### AnalysisResult（A3 输出 = 单个分析节点的执行结果）

```python
@dataclass
class AnalysisResult:
    """单个分析节点的执行结果。满足 00B Layer 2 溯源字段要求。"""
    node_id: str                          # 对应 AnalysisNode.node_id
    task: str                             # 分析类型
    status: str                           # "completed" | "degraded" | "failed"
    output: dict[str, Any]                # 定量结果，如 {"HR": 1.42, "p_value": 0.003, ...}

    # ── 00B Layer 2 溯源字段 ──
    data_source: str                      # 数据源路径
    method: str                           # 实际使用的方法
    raw_output_file: str                  # 磁盘上的原始输出文件路径

    # ── P1-2 决策日志字段 ──
    why: str                              # 为什么选这个工具/方法
    what: str                             # 实际做了什么操作
    result_interpretation: str            # LLM 对结果的解释

    # ── 失败恢复字段 ──
    failure_type: str | None              # None | "F1" | "F2" | "F3" | "F4" | "F5"
    retry_count: int                      # 重试次数
    degradation_reason: str | None        # 如果是 degraded，记录原因

    VALID_STATUSES = frozenset({"completed", "degraded", "failed"})
    VALID_FAILURE_TYPES = frozenset({"F1", "F2", "F3", "F4", "F5", None})

    def __post_init__(self):
        if self.status not in self.VALID_STATUSES:
            raise ValueError(f"status must be one of {self.VALID_STATUSES}")
        if self.failure_type not in self.VALID_FAILURE_TYPES:
            raise ValueError(f"failure_type must be one of {self.VALID_FAILURE_TYPES}")
        if not self.data_source:
            raise ValueError("data_source is required for traceability (Layer 2)")
        if not self.method:
            raise ValueError("method is required for traceability (Layer 2)")
        if not self.raw_output_file:
            raise ValueError("raw_output_file is required for traceability (Layer 2)")
        if not self.why or not self.what:
            raise ValueError("why/what are required for decision traceability (P1-2)")
```

#### PipelineResult（4 Agent 全流程顶层容器）

```python
@dataclass
class PipelineResult:
    """MultiAgentPipeline.run() 的完整输出。S4 消费此类型。"""
    question: str                         # 原始用户问题
    literature_review: LiteratureReview   # A1 输出
    analysis_plan: AnalysisPlan           # A2 输出
    analysis_results: list[AnalysisResult] # A3 输出
    report: str                           # A4 输出的报告全文 (.md)
    total_tokens: dict[str, int]          # {"input": N, "output": M, "total": N+M}
    execution_log: list[dict[str, Any]]   # 每一步的详细日志
    layer4_warnings: list[str]            # Layer 4 交叉验证产生的所有 WARNING

    def __post_init__(self):
        if not self.analysis_results:
            raise ValueError("PipelineResult must have at least 1 AnalysisResult")
        if not self.report or not self.report.strip():
            raise ValueError("report must not be empty")
        if not self.execution_log:
            raise ValueError("execution_log must not be empty")
```

### 2.2 工具输入输出类型（S3 内部使用，不导出）

#### CacheIndex（缓存索引文件类型）

```python
@dataclass
class CacheIndex:
    """analysis_cache_index.json 的内存表示。"""
    datasets: dict[str, DatasetCache]     # dataset_name → DatasetCache

@dataclass
class DatasetCache:
    expression_matrix: str                # 表达矩阵文件路径
    survival_data: str | None             # 生存数据文件路径
    genes_cached: list[str]               # 有预计算缓存的基因列表
    analyses_available: dict[str, CachedAnalysis]  # analysis_type → schema

@dataclass
class CachedAnalysis:
    file: str                             # 缓存 JSON 文件路径
    columns: list[str]                    # 输出字段名列表，如 ["gene", "logFC", "adj_p"]
    dtypes: dict[str, str]                # 字段类型，如 {"logFC": "float64"}
    cached_at: str                        # ISO 8601 缓存生成时间
    source_script: str                    # 生成缓存的分析脚本路径
```

#### ValidationReport（Layer 4 交叉验证输出）

```python
@dataclass
class ValidationReport:
    """validate_upstream() 方法的标准输出。"""
    validator: str                        # 哪个 Agent 在验证（"A2" | "A3" | "A4"）
    validated: str                        # 在验证谁的输出（"A1" | "A2" | "A3"）
    status: str                           # "PASS" | "WARNING" | "BLOCKER"
    checks_performed: list[str]           # 执行了哪些检查
    warnings: list[str]                   # 非致命的注意项
    blockers: list[str]                   # 致命的矛盾（触发 BLOCKER 时非空）

    def __post_init__(self):
        if self.status not in {"PASS", "WARNING", "BLOCKER"}:
            raise ValueError(f"status must be PASS/WARNING/BLOCKER, got {self.status}")
        if self.status == "BLOCKER" and not self.blockers:
            raise ValueError("status=BLOCKER but blockers list is empty")
```

### 2.3 与 00- 共享类型的对应关系

| 00- §二 类型 | S3 中的角色 | 差异说明 |
|-------------|-----------|---------|
| `LiteratureReview` | A1→A2 传递，S1 类型直接复用 | 无修改 |
| `Hypothesis` | 作为 AnalysisPlan.hypotheses 的条目 | 无修改 |
| `BenchmarkTask` | Task Router 的输入类型 | 无修改（S2 定义） |
| `EvalAgent` (Protocol) | MultiAgentPipeline 实现此 Protocol | 无修改（S2 定义） |
| **AnalysisNode** | S3 新增，DAG 节点类型 | 需回写 00- §二 |
| **AnalysisPlan** | S3 新增，A2→A3 的数据传递类型 | 需回写 00- §二 |
| **AnalysisResult** | S3 新增，A3→A4 的数据传递类型（含 Layer 2 溯源） | 需回写 00- §二 |
| **PipelineResult** | S3 新增，S4 消费的顶层类型 | 需回写 00- §二 |

**需要在 00- §六 回写的决策**：
- D-013 (新增): R 代码集成 — 预计算缓存 + 实时 Python，无 subprocess R
- D-014 (新增): 三层混合执行 — 🔵缓存查询(DEG/Survival) + 🟢实时Python(免疫/药物) + 🟡降级F4
- D-015 (新增): Layer 4 交叉验证 — 三个节点，规则为主(~80行/节点)，LLM仅边界WARNING
- D-016 (新增): Pipeline 架构 — 外层固定 4 Agent 串行 + 内层 LLM 驱动动态 DAG
- D-017 (新增): EvalAgent Protocol 适配 — Task Router 按 task_id 分派

---

## 三、INTERFACE SPEC

### 3.1 导出给其他 Step 的 public 接口

#### MultiAgentPipeline（S4/S5 消费；S2 通过 EvalAgent Protocol 评测）

```python
class MultiAgentPipeline:
    """
    4 Agent 协作的完整生物医学研究 Pipeline。
    实现 EvalAgent Protocol，可被 S2 的 BiomedBenchmark 评估。

    用法（自然语言模式）:
        pipeline = MultiAgentPipeline(llm_client=client, config=config)
        result: PipelineResult = pipeline.run(
            "CSTB 在结直肠癌中的预后价值和免疫浸润关联"
        )

    用法（Benchmark 模式）:
        task = BenchmarkTask(task_id="T3-DEG", ...)
        output: dict = pipeline.run(task)  # EvalAgent Protocol

    内部流程:
        Phase 1: LiteratureAgent.run(question) → LiteratureReview
        Phase 2: OrchestrationAgent.plan(review) → AnalysisPlan
        Phase 3: AnalysisAgent.execute(plan) → list[AnalysisResult]
        Phase 4: ReportAgent.generate(review, plan, results) → str (报告)
        每个 Phase 间运行 Layer 4 交叉验证
    """

    def __init__(self, llm_client: LLMClient, config: dict | None = None):
        """
        初始化 Pipeline，组装 4 个 Agent。

        Args:
            llm_client: 统一的 LLM 客户端（所有 Agent 共用）
            config: 配置字典，包含缓存路径、数据集路径等
        """

    def run(
        self, question_or_task: str | BenchmarkTask
    ) -> PipelineResult | dict[str, Any]:
        """
        执行完整的生物医学研究 Pipeline。

        Union 签名与 S1 LiteratureAgent.run() 保持一致：
        - 输入 str → 返回 PipelineResult（自然语言模式）
        - 输入 BenchmarkTask → 返回 dict（EvalAgent Protocol 模式）

        Task Router 分派逻辑（BenchmarkTask 模式）:
          T1-LIT → 委托 S1 LiteratureAgent
          T2-GDA → Phase 1 + 简化 Phase 2（不生成完整 DAG）
          T3-DEG/T4-SURV/T5-DRUG → 跳过 Phase 1，task.input 直接驱动 A2+A3

        Raises:
            NetworkError: 代理不可用
            ValidationBlockedError: Layer 4 交叉验证 BLOCKER
        """

    @property
    def name(self) -> str:
        """EvalAgent Protocol 要求。"""
        return "MultiAgentPipeline"
```

#### OrchestrationAgent（可独立使用，但主要通过 Pipeline 调用）

```python
class OrchestrationAgent:
    """
    LLM 驱动的动态 DAG 生成。

    用法:
        orch = OrchestrationAgent(llm_client=client, config=config)
        plan: AnalysisPlan = orch.plan(literature_review)
    """

    def __init__(self, llm_client: LLMClient, config: dict | None = None):
        """初始化 A2，注入 LLM 客户端和数据源清单。"""

    def plan(self, review: LiteratureReview) -> AnalysisPlan:
        """
        从 LiteratureReview 推理分析计划。

        步骤：
        1. 提取 hypotheses 中的可验证预测
        2. 为每个预测匹配分析方法（LLM 推理 + 方法兼容矩阵校验）
        3. 构建 DAG（拓扑排序、依赖管理）
        4. 为每个节点分配数据源和参数
        5. 识别数据缺口（哪些预测无法用现有数据验证）

        Raises:
            LLMError: LLM 调用失败
            ValueError: LiteratureReview 的 hypotheses 为空
        """

    def validate_upstream(self, review: LiteratureReview) -> ValidationReport:
        """
        Layer 4 交叉验证节点 #1: A2 验证 A1 输出。

        检查项:
        1. 证据链内部一致性：扫描 evidence_chain，检测相反方向 claim
        2. 假设-证据对应：每个 hypothesis 的 rationale 是否引用实际存在的 claim
        3. 置信度合理性：如果 ≥50% claim 是 weak/unverified 但 confidence > 0.7 → WARNING
        4. BLOCKER: evidence_chain 为空 或 hypotheses 为空
        """

    def plan_from_task(self, task: BenchmarkTask) -> AnalysisPlan:
        """
        从 BenchmarkTask（非 LiteratureReview）构建 AnalysisPlan。
        用于 T3-DEG/T4-SURV/T5-DRUG 的 Benchmark 模式。
        """
```

#### AnalysisAgent（可独立使用，但主要通过 Pipeline 调用）

```python
class AnalysisAgent:
    """
    Think→Act→Observe 分析执行 Agent。
    实现了工具选择、参数填充、结果解释三个子步骤。

    用法:
        analyzer = AnalysisAgent(llm_client=client, tools=[...], config=config)
        results: list[AnalysisResult] = analyzer.execute(plan)
    """

    def __init__(
        self,
        llm_client: LLMClient,
        tools: list[ToolDef],
        config: dict | None = None,
    ):
        """初始化 A3，注入工具列表（TCGA/Survival/Drug/Immune tools）。"""

    def execute(self, plan: AnalysisPlan) -> list[AnalysisResult]:
        """
        按 DAG 拓扑序执行每个分析节点。

        对每个节点:
          1. Think: 审查节点定义 → 选择工具 → 决定参数
          2. Act: 调用工具 → 接收结果
          3. Observe: 解释结果 → 判断是否需要重试/降级
          4. 如果失败: F1-F5 分类 → 恢复或降级
          5. 记录 why/what/result 到 AnalysisResult

        失败恢复:
          F1 (瞬时): 自动重试 3 次
          F2 (参数): 换替代方法，最多 2 次重试 → 第 3 次升级 F4
          F3 (方法): Cox PH 不满足 → 降级为 KM + log-rank
          F4 (数据): 标记 degraded，跳过该节点
          F5 (未知): 记录日志，继续下一个节点

        Raises:
            LLMError: Think 阶段 LLM 调用失败且无法降级
        """

    def validate_upstream(self, plan: AnalysisPlan) -> ValidationReport:
        """
        Layer 4 交叉验证节点 #2: A3 验证 A2 输出。

        检查项:
        1. 数据源存在性：每个节点的 data_source → pathlib.Path.exists()
        2. 基因名有效性：plan 中的基因是否在数据列中存在
        3. 方法合理性：方法是否在 METHOD_COMPATIBILITY 矩阵中允许
        4. BLOCKER: plan 中所有节点的数据源都不存在
        """
```

#### ReportAgent（可独立使用，但主要通过 Pipeline 调用）

```python
class ReportAgent:
    """
    多源证据聚合 + 结构化报告生成 + Layer 4 交叉验证（A4→A3）。

    用法:
        reporter = ReportAgent(llm_client=client, config=config)
        report: str = reporter.generate(review, plan, results)
    """

    def __init__(self, llm_client: LLMClient, config: dict | None = None):
        """初始化 A4。"""

    def generate(
        self,
        review: LiteratureReview,
        plan: AnalysisPlan,
        results: list[AnalysisResult],
    ) -> str:
        """
        生成结构化 Markdown 报告。

        报告结构（6 节）:
        1. Introduction — 研究问题和背景
        2. Methods — 分析方法和数据源
        3. Results — 每个假设的验证结果（包含所有分析节点的定量结果）
        4. Negative and Null Findings — 阴性结果和未验证的预测（强制节）
        5. Discussion — 局限性 + 与文献的一致性讨论
        6. Conclusion — 核心发现摘要

        关键写作原则（Layer 1 prompt 约束）:
        - 每个 claim 必须有数据支撑
        - 诚实地报告失败和局限性
        - 包含效应量，不只是 p-value
        - 报告未发现的内容
        """

    def validate_upstream(self, results: list[AnalysisResult]) -> ValidationReport:
        """
        Layer 4 交叉验证节点 #3: A4 验证 A3 输出。

        检查项:
        1. 统计量合理性（复用 S2 V3 硬规则）: HR 0.01-100, p 0-1, logFC -20~20
        2. 跨节点矛盾检测: Cox 说保护(HR<1) + DEG 说高表达(logFC>0) → WARNING
        3. 效应量阈值检查: 声称 "significant" 但效应量低于阈值 → WARNING
        4. 分析覆盖率: A3 产出的节点 vs 报告中提及的节点 → WARNING 如果覆盖 < 100%
        5. BLOCKER: 所有节点的 status 都是 "failed"

        效应量阈值:
          |logFC| < 0.5 → 生物意义微弱
          |log(HR)| < 0.2 → 效应微弱
          |spearman_r| < 0.3 → 弱相关
        """
```

#### 工具类（Tools — 供 AnalysisAgent 使用）

```python
class TCGADataAccessor:
    """
    TCGA 数据统一访问层。三层回退策略。
    封装了"先查缓存 → 缓存未命中 → 实时 Python → 都失败 → F4"的逻辑。

    用法:
        accessor = TCGADataAccessor(cache_index_path="data/cache/analysis_cache_index.json")
        result = accessor.query(gene="CSTB", analysis_type="differential_expression", dataset="TCGA-COAD")

    Raises:
        CacheMissError: 缓存未命中 + 实时计算也失败（F4 触发）
    """

    def __init__(self, cache_index_path: str):
        """从 analysis_cache_index.json 加载缓存索引。"""

    def query(self, gene: str, analysis_type: str, dataset: str) -> dict[str, Any]:
        """
        查询分析结果。三层回退：
        (1) 缓存命中 → 直接返回
        (2) 缓存未命中 → 实时 Python 计算（仅支持 t-test/Spearman）
       - Analysis types NOT supported for real-time fallback: survival_analysis,
         cox_regression, pathway_enrichment (require R or specialized tools;
         cache miss -> immediate F4 degradation)
       - Analysis types SUPPORTED for real-time fallback: differential_expression
         (t-test/Mann-Whitney), immune_correlation (Spearman/Pearson),
         drug_screening (Spearman), gene_gene_correlation (Spearman/Pearson)
        (3) 实时计算失败 → raise CacheMissError（触发 F4）
        """

    def is_cached(self, gene: str, analysis_type: str, dataset: str) -> bool:
        """检查基因×分析类型的缓存是否可用。"""

    def list_cached_genes(self, dataset: str) -> list[str]:
        """列出某数据集中有缓存的基因。"""


class SurvivalTools:
    """生存分析工具集：缓存查询 + F3 降级。"""

    @staticmethod
    def query_cox(gene: str, dataset: str, accessor: TCGADataAccessor) -> dict:
        """
        查询 Cox 回归结果（缓存优先）。

        返回: {"HR": float, "CI_lower": float, "CI_upper": float,
               "p_value": float, "ph_test_p": float, "n": int}

        F3 降级: 如果 ph_test_p < 0.05 → 标记 ph_violation=true
                 → AnalysisAgent 切换到 KM+log-rank
        """

    @staticmethod
    def query_km(gene: str, dataset: str, accessor: TCGADataAccessor) -> dict:
        """查询 KM 曲线数据（缓存优先）。"""


class DrugTools:
    """GDSC2 药物敏感性筛选：实时 Python Spearman 相关。"""

    @staticmethod
    def screen_gene(
        gene: str, gdsc_expr: pd.DataFrame, gdsc_response: pd.DataFrame
    ) -> dict:
        """
        对单个基因执行药物筛选。

        步骤：
        1. 提取基因在 GDSC2 细胞系中的表达值
        2. 与所有药物的 IC50 计算 Spearman 相关
        3. BH FDR 校正
        4. 返回 top-10 最显著关联

        返回: {"gene": str, "top_drugs": list[dict], "fdr_threshold": float}
        """


class ImmuneTools:
    """免疫浸润关联：实时 Python Spearman 相关。"""

    @staticmethod
    def correlate_gene_immune(
        gene: str,
        expr: pd.DataFrame,
        immune_scores: pd.DataFrame,
        methods: list[str] | None = None,
    ) -> dict:
        """
        计算基因表达与免疫细胞丰度的相关性。

        返回: {"gene": str, "correlations": dict[method, dict[cell_type, dict[r, p]]]}
        """
```

### 3.2 消费其他 Step 的接口

| 来源 | 消费内容 | 用于 |
|------|---------|------|
| S1 `src/types.py` | `LiteratureReview`, `Hypothesis`, `EvidenceLink`, `Paper` | A1→A2 数据传递 |
| S1 `src/agents/literature_agent.py` | `LiteratureAgent` 类 | Pipeline Phase 1 |
| S1 `src/llm/client.py` | `LLMClient` | 所有 Agent 的 LLM 调用 |
| S1 `src/utils/network.py` | `ensure_network()` | 启动时的网络检查 |
| S2 `src/benchmark/types.py` | `BenchmarkTask`, `EvalAgent` Protocol | Task Router + EvalAgent 实现 |
| ITIP `milestones/` | `milestone_p1C_model.rds`, `milestone_p1E_drug.rds` | 缓存数据来源（读为 JSON） |
| CSTB `results/module4_immune/` | 免疫浸润估计数据 | 免疫工具的数据源 |

### 3.3 接口依赖关系图

```
外部消费方:
  Step 4 → PipelineResult (CSTB case study 完整结果)
  Step 5 → 同上
  Step 2 → MultiAgentPipeline (as EvalAgent, 通过 BiomedBenchmark 评测)

S3 内部依赖链:
  pipeline.py  ← S1:LiteratureAgent, S1:LLMClient, orchestration_agent,
                 analysis_agent, report_agent, S2:BenchmarkTask
  orchestration_agent.py  ← S1:LLMClient, S1:types (LiteratureReview/Hypothesis)
  analysis_agent.py  ← S1:LLMClient, tools/*, S2:BenchmarkTask (类型)
  report_agent.py  ← S1:LLMClient, S3 内部类型 (AnalysisResult/AnalysisPlan)
  tools/tcga_tools.py  ← 缓存索引 JSON, pandas, scipy.stats, pathlib
  tools/survival_tools.py  ← TCGADataAccessor
  tools/drug_tools.py  ← pandas, scipy.stats
  tools/immune_tools.py  ← pandas, scipy.stats
```

---

## 四、DATA FLOW DIAGRAM

### 主流程：MultiAgentPipeline.run(question)

```
USER QUESTION: "CSTB 在结直肠癌中的预后价值和免疫浸润关联"
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│ Phase 1: LiteratureAgent.run(question)  [S1 代码, 无 LLM 调用新增]  │
│                                                              │
│  复用 S1 完整实现:                                             │
│    问题分解 → 多轮检索(Think→Act→Observe, max 3) → 证据整合 → 假设生成  │
│                                                              │
│  输出: LiteratureReview                                       │
│  新增: S3 pipeline 在 Phase 1 后调用 S1 EvidenceSynthesizer._verify_pmids (via pipeline.literature_agent._synthesizer)()        │
│        (复用 Layer 3 V1, 确保缓存的旧产物 PMID 不过期)         │
│  token: ~5000-12000 (取决于检索轮数)                           │
└──────────────┬───────────────────────────────────────────────┘
               │ LiteratureReview
               ▼
┌──────────────────────────────────────────────────────────────┐
│ Layer 4 交叉验证节点 #1: A2.validate_upstream(A1 输出)          │
│  - 证据链内部一致性检查                                         │
│  - 假设-证据对应验证                                            │
│  - 置信度合理性检查                                             │
│  BLOCKER → ValidationBlockedError (停止 pipeline)              │
│  WARNING → 记录到 PipelineResult.layer4_warnings               │
└──────────────┬───────────────────────────────────────────────┘
               │ (if PASS or WARNING)
               ▼
┌──────────────────────────────────────────────────────────────┐
│ Phase 2: OrchestrationAgent.plan(review)  (LLM 调用 #1)       │
│                                                              │
│  输入: LiteratureReview (hypotheses + evidence_chain + gaps)   │
│  处理: LLM 推理每一个 hypothesis → 提取可验证预测 → 匹配方法 →  │
│       构建 DAG → 分配数据源 → 标记数据缺口                       │
│                                                              │
│  反模板机制 (system prompt 硬约束):                              │
│    "Derive each analysis node from SPECIFIC hypothesis content"│
│    每个节点的 rationale 字段强制 LLM 解释 WHY                    │
│                                                              │
│  方法兼容矩阵校验 (后处理, 无 LLM):                              │
│    对 LLM 输出的每个节点, 检查:                                 │
│    - method 是否在 METHOD_COMPATIBILITY[数据→分析] 中?           │
│    - 样本量是否满足 SAMPLE_SIZE_CONSTRAINTS[method]?            │
│    - 方法组合是否在 INVALID_COMBINATIONS 中?                    │
│    不通过 → LLM 重新规划 (max 2 次) 或用最接近方法替换            │
│                                                              │
│  输出: AnalysisPlan (DAG of N AnalysisNode)                    │
│  token: ~1000 in + ~600 out                                   │
└──────────────┬───────────────────────────────────────────────┘
               │ AnalysisPlan
               ▼
┌──────────────────────────────────────────────────────────────┐
│ Layer 4 交叉验证节点 #2: A3.validate_upstream(A2 输出)          │
│  - 每个节点 data_source → pathlib.Path.exists()                │
│  - 基因名在目标数据中有效性验证                                   │
│  - 方法合理性二次校验 (规则层)                                    │
│  BLOCKER: 所有节点的数据源都不存在                                │
└──────────────┬───────────────────────────────────────────────┘
               │ (if PASS or WARNING)
               ▼
┌──────────────────────────────────────────────────────────────┐
│ Phase 3: AnalysisAgent.execute(plan)                          │
│                                                              │
│  按 DAG 拓扑序遍历每个 AnalysisNode:                            │
│                                                              │
│  对每个节点:                                                   │
│    ┌─────────────────────────────────────────────────┐       │
│    │ Think (LLM 调用 #2.N):                           │       │
│    │   审查节点定义 → 选择工具 → 决定参数 → 记录 why     │       │
│    │   token: ~300 in + ~150 out per node             │       │
│    ├─────────────────────────────────────────────────┤       │
│    │ Act:                                              │       │
│    │   工具内部: 缓存查询 → 实时 Python → F4             │       │
│    │   token: 0 (无 LLM 调用)                          │       │
│    ├─────────────────────────────────────────────────┤       │
    │    │ Observe (LLM 调用 #2.N+1):                        │       │
    │    │   LLM 解释工具输出 → 生成 result_interpretation    │       │
    │    │   token: ~200 in + ~150 out per node              │       │
    │    │   程序化后处理: 提取数值 → 统计量检查 → 记录 what   │       │
│    │     F1 瞬时错误 → 自动重试 3 次                      │       │
    |    |     F2 param error -> try fallback_tool, max 2 retries -> upgrade to F4  |       |
│    │     F3 方法降级 → KM+log-rank 替代 Cox              │       │
│    │     F4 数据不可用 → AnalysisResult.status="degraded"│       │
│    │     F5 未知 → 日志记录, 继续下一个节点                │       │
│    └─────────────────────────────────────────────────┘       │
│                                                              │
│  并行优化: 无依赖的节点可用 threading 并行执行 (max 2).          │
│  默认串行执行各节点。                                          │
│                                                              │
│  输出: list[AnalysisResult] (长度 = len(nodes))               │
    │  token: 约 750 per node × N nodes (Think ~450 + Observe ~300)│
└──────────────┬───────────────────────────────────────────────┘
               │ list[AnalysisResult]
               ▼
┌──────────────────────────────────────────────────────────────┐
│ Layer 4 交叉验证节点 #3: A4.validate_upstream(A3 输出)          │
│  - 统计量合理性 (HR 0.01-100, p 0-1, logFC -20~20)            │
│  - 跨节点矛盾检测 (Cox 保护 vs DEG 高表达)                      │
│  - 效应量阈值检查 (声称"显著"但效应量小)                         │
│  - 节点覆盖率 (A3 产出了哪些节点 vs 报告覆盖了哪些)              │
│  BLOCKER: 所有 result 的 status 都是 "failed"                 │
└──────────────┬───────────────────────────────────────────────┘
               │ (if PASS or WARNING)
               ▼
┌──────────────────────────────────────────────────────────────┐
│ Phase 4: ReportAgent.generate(review, plan, results)          │
│          (LLM 调用 #3)                                        │
│                                                              │
│  输入: LiteratureReview + AnalysisPlan + list[AnalysisResult]  │
│  处理: LLM 整合三源 → 生成结构化报告                             │
│                                                              │
│  报告包含:                                                     │
│    1. Introduction (研究背景)                                  │
│    2. Methods (分析方法)                                       │
│    3. Results (每个假设 × 每个节点的定量结果)                   │
│    4. Negative and Null Findings (强制节)                      │
│    5. Discussion (局限性 + 文献一致性)                          │
│    6. Conclusion                                               │
│                                                              │
│  每个 strong claim 附带 [HUMAN REVIEW RECOMMENDED] 标记        │
│                                                              │
│  输出: str (Markdown 报告全文)                                  │
│  token: ~3000 in + ~1500 out                                  │
└──────────────┬───────────────────────────────────────────────┘
               │ str (report.md)
               ▼
┌──────────────────────────────────────────────────────────────┐
│ 组装 PipelineResult                                            │
│  聚合 Phase 1-4 全部输出 + token 统计 + 执行日志 + Layer 4 WARNINGs │
│  校验: PipelineResult.__post_init__                            │
└──────────────┬───────────────────────────────────────────────┘
               │ PipelineResult
               ▼
            返回 / 持久化为 JSON
```

### LLM 调用次数估算

| Phase | 调用次数 | 说明 |
|-------|---------|------|
| 1 (LiteratureAgent) | 4-12 次 | S1 的原有调用（问题分解+多轮检索+证据整合+假设生成） |
| 2 (OrchestrationAgent) | 1 次 (+ 可能重试) | LLM 规划 DAG；方法校验不通过时触发重新规划（max 2） |
| 3 (AnalysisAgent) | N × (2 (Think + Observe)) = 2N 次 | N = DAG 节点数, 通常 3-5；每个节点 1 次 Think |
| 4 (ReportAgent) | 1 次 | LLM 生成结构化报告 |
| **总计（不含 S1）** | **7-11 次** | 新增 LLM 调用都在 S3 中 |

### Token 预算估算（S3 新增部分，不含 S1 Phase 1）

| 场景 | 估计 token |
|------|-----------|
| 最小 (3 节点 DAG) | ~4500 |
| 典型 (4-5 节点 DAG) | ~6500 |
| 最大 (7+ 节点 DAG, 含 2 次规划重试) | ~10000 |

---

## 五、PROMPT TEMPLATES

### 通用前缀：Layer 1 反幻觉约束块（所有 LLM 调用必须包含）

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

---

### Prompt 1: OrchestrationAgent — DAG 规划 (ORCHESTRATION_PLAN)

**调用位置**: Phase 2, `OrchestrationAgent.plan()`

**System Prompt**:
```
You are a bioinformatics research methodologist. Your task is to design an
analysis plan (as a DAG of analysis tasks) to test a set of hypotheses using
available multi-omics data.

## DATA SOURCES AVAILABLE
{data_sources_description}

## ANALYSIS METHODS AVAILABLE
{available_methods_description}

## CRITICAL: DO NOT USE A FIXED TEMPLATE

1. Derive each analysis node from the SPECIFIC content of each hypothesis,
   NOT from a pre-determined list of analysis types.
2. If the hypothesis is about a single gene's prognostic value, the DAG
   should be smaller and focused on survival + expression.
3. If the hypothesis is about a signaling pathway or mechanism (e.g., "CSTB
   promotes immune evasion through M2 polarization"), include pathway-level
   analysis nodes (correlation network, multi-gene co-expression).
4. If the hypothesis involves multiple genes or drug targets, the DAG
   should include drug sensitivity screening nodes.

## HYPOTHESIS CLASSIFICATION (MUST CLASSIFY BEFORE DAG DESIGN)
Before designing the DAG, classify each hypothesis into one of:
(a) single_gene_prognostic -- hypothesis about one gene association with survival/expression.
    Expected DAG: smaller (2-3 nodes), focused on expression + survival.
(b) pathway_mechanism -- hypothesis about a biological mechanism involving multiple molecules.
    Expected DAG: larger (4-6 nodes), including correlation network and multi-gene nodes.
(c) multi_gene_drug -- hypothesis about drug sensitivity or multi-gene signatures.
    Expected DAG: includes drug screening nodes, may have 5+ nodes.
Your DAG structure MUST differ by classification. Include the classification in each node rationale.


{LAYER_1_CONSTRAINTS_BLOCK}

## OUTPUT FORMAT (JSON)
{
  "nodes": [
    {
      "node_id": "node_01_diff_expression",
      "task": "differential_expression",
      "gene_list": ["CSTB"],
      "data_source": "D:/C-file/itip_p1/data/tcga/COAD_expr.csv",
      "method": "limma_voom",
      "parameters": {"group_col": "sample_type", "group_a": "tumor", "group_b": "normal"},
      "depends_on": [],
      "rationale": "Hypothesis 'CSTB is overexpressed in CRC' directly predicts differential expression. TCGA-COAD is the appropriate dataset with n=303. Limma-voom is chosen because..."
    }
  ],
  "edges": [
    ["node_01_diff_expression", "node_03_survival_stratified"]
  ],
  "data_gaps": [
    "No spatial transcriptomics data available to test the M2 colocalization prediction"
  ]
}

For each node, the "rationale" field MUST explain WHY this specific method
and data source were chosen for this specific hypothesis. This is the most
important field — it proves you are reasoning, not template-filling.
```

**User Prompt**:
```
Research question: {question}

Hypotheses from literature review ({n_hypotheses} hypotheses):

{hypotheses_json}

Evidence chain ({n_claims} claims):
{evidence_chain_summary}

Knowledge gaps identified:
{knowledge_gaps}

Design an analysis plan as a DAG to test these hypotheses.
```

**输入变量**: `{question}`, `{n_hypotheses}`, `{hypotheses_json}`, `{n_claims}`, `{evidence_chain_summary}`, `{knowledge_gaps}`, `{data_sources_description}`, `{available_methods_description}`

**输出后处理**: 方法兼容矩阵校验 → 不通过的方法 → LLM 重新规划（max 2 次）

---

### Prompt 2: AnalysisAgent — Think 阶段 (ANALYSIS_THINK)

**调用位置**: Phase 3 每个节点, `AnalysisAgent._think()`

**System Prompt**:
```
You are a computational biologist executing a pre-defined analysis node.
You are in the THINK phase. Your job is to decide HOW to execute this node.

Available tools and their descriptions:
{tools_description}

## TASK
Node ID: {node_id}
Analysis task: {task}
Target genes: {gene_list}
Data source: {data_source}
Suggested method: {suggested_method}

## YOUR JOB
1. Select the appropriate tool from the available tools
2. Decide on the specific parameters based on the data context
3. If the suggested method seems inappropriate, propose an alternative
4. Record WHY you chose this tool and these parameters

{LAYER_1_CONSTRAINTS_BLOCK}

## OUTPUT FORMAT (JSON)
{
  "tool_choice": "run_differential_expression",
  "parameters": {
    "gene": "CSTB",
    "dataset": "TCGA-COAD",
    "method": "limma_voom"
  },
  "why": "Limma-voom is the recommended method for RNA-seq differential expression with n>300. The data source is TCGA-COAD RNA-seq count data...",
  "fallback_tool": "run_ttest",
  "fallback_parameters": {
    "gene": "CSTB",
    "dataset": "TCGA-COAD"
  }
}
```

**User Prompt**:
```
Execute analysis node: {node_id}

Context from upstream nodes (already completed):
{upstream_results_summary}

Available data context:
- Sample size: {n_samples}
- Data type: {data_type}
- Genes available in data: {genes_in_data}

Proceed with THINK phase.
```

**输入变量**: `{node_id}`, `{task}`, `{gene_list}`, `{data_source}`, `{suggested_method}`, `{upstream_results_summary}`, `{n_samples}`, `{data_type}`, `{genes_in_data}`

---

### Prompt 3: ReportAgent — 报告生成 (REPORT_GENERATION)

**调用位置**: Phase 4, `ReportAgent.generate()`

**System Prompt**:
```
You are a senior bioinformatics researcher writing a structured case study
report. Your report will be read by a hiring manager evaluating your
scientific reasoning ability.

## REPORT STRUCTURE (MUST FOLLOW)

### 1. Introduction
- Background on the gene(s) and disease
- The specific research question
- Summary of literature evidence found

### 2. Methods
- Data sources used (dataset, sample size)
- Analysis methods applied (one line each)
- Any limitations of the methods

### 3. Results
For EACH hypothesis:
- Hypothesis statement
- What the analysis found (exact numbers, effect sizes, confidence intervals)
- Whether the evidence supports, contradicts, or is inconclusive about the hypothesis

### 4. Negative and Null Findings (MANDATORY — DO NOT SKIP)
- Which hypotheses could NOT be tested with available data? Why?
- Which analyses produced null results?
- Which genes were NOT found to be significant?

### 5. Discussion
- How do these results compare with the literature evidence?
- What are the limitations of this analysis? (list at least 3)
- What would be the next steps if this were a real research project?

### 6. Conclusion
- 2-3 sentence summary of the core finding
- The most important limitation to keep in mind

## CRITICAL WRITING RULES

1. **Every quantitative claim MUST cite its source**: either a PMID from the
   literature review, or a specific AnalysisResult node. Format: [PMID:xxxxxxxx]
   or [Node: node_id].
2. **Report exact effect sizes**, not just p-values. "CSTB was significantly
   overexpressed (logFC=2.3, adj.P=1.2e-15)" — not "CSTB was significantly
   overexpressed".
3. **Do NOT overstate**: "trend towards significance (p=0.06)" is NOT "significant".
4. **Be honest about failures**: if an analysis degraded or failed, say so in
   the report.

{LAYER_1_CONSTRAINTS_BLOCK}
```

**User Prompt**:
```
Research question: {question}

Literature evidence ({n_papers} papers, {n_claims} claims):
{literature_summary}

Analysis plan ({n_nodes} nodes):
{plan_summary}

Analysis results:
{results_formatted}

Degraded or failed nodes:
{degraded_nodes_summary}

Layer 4 validation warnings:
{validation_warnings}

Generate a complete structured report. Include the Negative and Null Findings section.
```

**输入变量**: `{question}`, `{n_papers}`, `{n_claims}`, `{literature_summary}`, `{n_nodes}`, `{plan_summary}`, `{results_formatted}`, `{degraded_nodes_summary}`, `{validation_warnings}`

---

### Prompt 汇总表

| # | Prompt ID | LLM 调用次数 | 每次 token (估) | Layer 1 约束 |
|---|-----------|-------------|----------------|-------------|
| 1 | ORCHESTRATION_PLAN | 1 (+ 最多 2 重试) | ~1600 | ✅ |
| 2 | ANALYSIS_THINK | N (N=节点数, 通常 3-5) | ~450/节点 | ✅ |
| 2b | ANALYSIS_OBSERVE | N (per node) | ~350/node | YES |
| 3 | REPORT_GENERATION | 1 | ~4500 | ✅ |

---

## 六、ANTI-HALLUCINATION MEASURES

### 6.1 防线实现映射

| 防线层 | 该 Step 实现位置 | 具体机制 | 代码量 |
|--------|-----------------|---------|--------|
| **Layer 1** (Prompt) | 所有 3 个 Prompt 模板（ORCHESTRATION_PLAN, ANALYSIS_THINK, REPORT_GENERATION） | 通用约束块嵌入每个 system prompt | 模板内嵌 |
| **Layer 2** (结构) | `AnalysisResult` dataclass — `__post_init__` | data_source/method/raw_output_file 三个溯源字段强制非空 | ~15 行 |
| **Layer 3** (后验) | S3 Phase 1 后调用 S1 `_verify_pmids()`；A3 的 METHOD_COMPATIBILITY 矩阵校验 | V1 PMID 验证 + 方法合理性程序化校验 | 复用 S1 + ~30 行 |
| **Layer 4** (交叉验证) | `pipeline.py`（节点 #1, #2）+ `report_agent.py`（节点 #3） | 3 个 validate_upstream() 方法，规则为主 | ~240 行 (3×80) |
| **Layer 5** (人工) | ReportAgent 对 strong claims 标记 `[HUMAN REVIEW RECOMMENDED]` | 交付物中显式标注需人工确认的内容 | 你执行 |

### 6.2 Layer 4 交叉验证详细实现

#### 节点 #1：A2 验证 A1 输出（位置：`pipeline.py` — `OrchestrationAgent.validate_upstream()`）

```python
def validate_upstream(self, review: LiteratureReview) -> ValidationReport:
    """Layer 4 节点 #1: A2 验证 A1 的 LiteratureReview。"""
    checks = ["evidence_chain_internal_consistency",
              "hypothesis_evidence_correspondence",
              "confidence_reasonableness",
              "non_empty_chain_and_hypotheses"]
    warnings = []
    blockers = []

    # Check 1: 证据链内部一致性
    claims = {link.claim for link in review.evidence_chain}
    # 检测相反方向的 claim（简化版 — 基于关键词方向检测）
    # 注意：基因名归一化（D1-01 deferred）的局限声明在代码注释中
    positive_genes = set()  # 与积极结果关联的基因
    negative_genes = set()  # 与消极结果关联的基因
    for link in review.evidence_chain:
        # 简化: 检测 claim 中的方向性关键词
        ...

    # Check 2: 假设-证据对应
    for i, hyp in enumerate(review.hypotheses):
        # 检查 rationale 是否引用了 evidence_chain 中实际存在的 claim
        mentioned_claims = [c for c in claims if c[:30] in hyp.rationale]
        if not mentioned_claims:
            warnings.append(
                f"Hypothesis #{i+1} rationale does not cite any claim "
                f"from evidence_chain"
            )

    # Check 3: 置信度合理性
    weak_or_unverified = sum(
        1 for link in review.evidence_chain
        if link.strength in ("weak", "unverified")
    )
    if weak_or_unverified / len(review.evidence_chain) >= 0.5:
        if review.confidence > 0.7:
            warnings.append(
                f"Confidence ({review.confidence}) is high but "
                f"{weak_or_unverified}/{len(review.evidence_chain)} claims "
                f"are weak/unverified"
            )

    # Check 4: BLOCKER 条件
    if not review.evidence_chain:
        blockers.append("evidence_chain is empty")
    if not review.hypotheses:
        blockers.append("hypotheses list is empty")

    status = "BLOCKER" if blockers else ("WARNING" if warnings else "PASS")
    return ValidationReport(
        validator="A2", validated="A1", status=status,
        checks_performed=checks, warnings=warnings, blockers=blockers,
    )
```

#### 节点 #2：A3 验证 A2 输出（位置：`pipeline.py` — `AnalysisAgent.validate_upstream()`）

```python
def validate_upstream(self, plan: AnalysisPlan) -> ValidationReport:
    """Layer 4 节点 #2: A3 验证 A2 的 AnalysisPlan。"""
    checks = ["data_source_existence", "gene_validity",
              "method_reasonableness", "at_least_one_valid_source"]
    warnings = []
    blockers = []

    valid_sources = 0
    for node in plan.nodes:
        # Check 1: 数据源存在性
        if not Path(node.data_source).exists():
            warnings.append(f"{node.node_id}: data_source not found: {node.data_source}")
        else:
            valid_sources += 1

        # Check 2: 基因名有效性（简化 — 在实现时与 TCGADataAccessor 交互）
        ...

        # Check 3: 方法合理性（规则矩阵）
        method_ok = _check_method_compatibility(node.task, node.method)
        if not method_ok:
            warnings.append(
                f"{node.node_id}: method '{node.method}' is not in "
                f"METHOD_COMPATIBILITY for task '{node.task}'"
            )

    # Check 4: BLOCKER 条件
    if valid_sources == 0:
        blockers.append("All nodes reference non-existent data sources")

    status = "BLOCKER" if blockers else ("WARNING" if warnings else "PASS")
    return ValidationReport(
        validator="A3", validated="A2", status=status,
        checks_performed=checks, warnings=warnings, blockers=blockers,
    )
```

#### 节点 #3：A4 验证 A3 输出（位置：`report_agent.py` — `ReportAgent.validate_upstream()`）

```python
def validate_upstream(self, results: list[AnalysisResult]) -> ValidationReport:
    """Layer 4 节点 #3: A4 验证 A3 的 AnalysisResults。"""
    checks = ["statistical_sanity", "cross_node_contradiction",
              "effect_size_claims", "node_coverage", "not_all_failed"]
    warnings = []
    blockers = []

    # Check 1: 统计量合理性（复用 S2 V3 硬规则）
    for r in results:
        for key, value in r.output.items():
            if key.startswith("HR") and not (0.01 < value < 100):
                warnings.append(f"{r.node_id}: HR={value} out of [0.01, 100]")
            if "p_value" in key and not (0 <= value <= 1):
                warnings.append(f"{r.node_id}: p_value={value} out of [0, 1]")
            if key == "logFC" and not (-20 < value < 20):
                warnings.append(f"{r.node_id}: logFC={value} out of [-20, 20]")

    # Check 2: 跨节点矛盾检测
    # 检测 "Cox 说保护(HR<1) + DEG 说高表达(logFC>0)" 矛盾
    for i, r1 in enumerate(results):
        for r2 in results[i+1:]:
            if _is_contradictory(r1, r2):
                warnings.append(
                    f"Potential contradiction: {r1.node_id} "
                    f"(HR={r1.output.get('HR')}) vs {r2.node_id} "
                    f"(logFC={r2.output.get('logFC')}) — needs biological explanation"
                )

    # Check 3: 效应量阈值检查
    effect_warnings = check_effect_size_claims(results)  # 见 §6.3
    warnings.extend(effect_warnings)

    # Check 4: 所有节点都失败 → BLOCKER
    if all(r.status == "failed" for r in results):
        blockers.append("All analysis nodes failed")

    status = "BLOCKER" if blockers else ("WARNING" if warnings else "PASS")
    return ValidationReport(
        validator="A4", validated="A3", status=status,
        checks_performed=checks, warnings=warnings, blockers=blockers,
    )
```

### 6.3 效应量阈值检查

位置：`report_agent.py` — `check_effect_size_claims()`

```python
EFFECT_SIZE_THRESHOLDS = {
    "logFC": 0.5,      # |logFC| < 0.5 → 生物意义微弱
    "HR": 0.2,         # |log(HR)| < 0.2 → 效应微弱（exp(0.2)≈1.22, exp(-0.2)≈0.82）
    "spearman_r": 0.3, # |r| < 0.3 → 弱相关
}

SIGNIFICANCE_KEYWORDS = [
    "significant", "significantly", "strong", "strongly",
    "显著", "明显", "重要", "关键"
]

def check_effect_size_claims(results: list[AnalysisResult]) -> list[str]:
    """
    检查 A3 结果中声称 "significant" 但效应量低于阈值的声明。

    Args:
        results: A3 产出的 AnalysisResult 列表

    Returns:
        WARNING 消息列表
    """
    warnings = []
    for r in results:
        interpretation = r.result_interpretation.lower()
        # 检查是否有 "显著/strong/significant" 声明
        has_significance_claim = any(
            kw.lower() in interpretation for kw in SIGNIFICANCE_KEYWORDS
        )
        if not has_significance_claim:
            continue

        # 检查效应量
        output = r.output
        if "logFC" in output and abs(output["logFC"]) < EFFECT_SIZE_THRESHOLDS["logFC"]:
            warnings.append(
                f"{r.node_id}: claims significance but |logFC|={abs(output['logFC']):.2f} "
                f"< threshold {EFFECT_SIZE_THRESHOLDS['logFC']}"
            )
        if "HR" in output:
            log_hr = abs(math.log(output["HR"]))
            if log_hr < EFFECT_SIZE_THRESHOLDS["HR"]:
                warnings.append(
                    f"{r.node_id}: claims significance but |log(HR)|={log_hr:.3f} "
                    f"< threshold {EFFECT_SIZE_THRESHOLDS['HR']}"
                )
        # Spearman r 检查同理
        ...
    return warnings
```

### 6.4 方法合理性规则集

位置：`tools/tcga_tools.py`

```python
# 数据→方法兼容矩阵
METHOD_COMPATIBILITY = {
    ("continuous_expr", "binary_group"): ["ttest", "mann_whitney", "limma_voom"],
    ("continuous_expr", "survival"): ["cox_regression", "km_logrank"],
    ("continuous_expr", "continuous_immune"): ["spearman", "pearson"],
    ("drug_response", "continuous_expr"): ["spearman", "pearson"],
    ("continuous_expr", "continuous_expr"): ["spearman", "pearson"],
}

# 样本量约束
SAMPLE_SIZE_CONSTRAINTS = {
    "ttest": lambda n: n >= 6,           # 每组至少 3
    "mann_whitney": lambda n: n >= 6,
    "cox_regression": lambda n: n >= 30,  # 至少 30 个事件
    "spearman": lambda n: n >= 10,
    "pearson": lambda n: n >= 10,
}

# 已知无效组合黑名单
INVALID_COMBINATIONS = [
    ("anova", "binary_group"),        # 二分组用 ANOVA 不合理
    ("spearman", "binary_group"),     # Spearman 需要连续变量
    ("pearson", "binary_group"),      # Pearson 也需要连续变量
]

def _check_method_compatibility(task: str, method: str) -> bool:
    """Check if method is compatible with task type."""
    TASK_DATA_TYPES = {
        "differential_expression": ("continuous_expr", "binary_group"),
        "survival_analysis": ("continuous_expr", "survival"),
        "immune_correlation": ("continuous_expr", "continuous_immune"),
        "drug_screening": ("drug_response", "continuous_expr"),
        "gene_gene_correlation": ("continuous_expr", "continuous_expr"),
        "pathway_enrichment": None,  # no hard rule, LLM judges
    }
    types = TASK_DATA_TYPES.get(task)
    if types is None:
        return True
    allowed = METHOD_COMPATIBILITY.get(types, [])
    return method in allowed

### 6.5 该 Step 特有的四种幻觉风险及应对

| 风险 | 表现 | 应对（该 Step 的实现） |
|------|------|----------------------|
| **错误传播** | A1 的幻觉被 A2 当作事实 → A3 分析 → A4 写入报告 | Layer 4 三个验证节点 + S1 Layer 3 V1 (EvidenceSynthesizer._verify_pmids, via pipeline.literature_agent._synthesizer) `_verify_pmids()` 复用 + strong claims 标记 [HUMAN REVIEW RECOMMENDED] |
| **规划幻觉** | A2 生成不存在的数据源或分析方法 | 节点 #2: `pathlib.Path.exists()` + METHOD_COMPATIBILITY 矩阵 + 基因名验证 |
| **解释幻觉** | A3 对统计结果给出错误生物学解释（如声称显著但效应量为零） | 节点 #3: `check_effect_size_claims()` + 跨节点矛盾检测 + 效应量阈值硬规则 |
| **过度报告** | A4 选择性报告有利结果，忽略阴性结果 | Prompt 3 强制 "Negative and Null Findings" 节 + 节点 #3 的覆盖率比对 |

### 6.6 P1-4 验证方案（交叉验证框架的自我验证）

位置：`tests/test_adversarial.py`

```
验证方法：注入已知矛盾，验证交叉验证框架正确检出

测试用例：
  TC1: 空 evidence_chain → 节点 #1 应产生 BLOCKER
  TC2: 所有 data_source 路径不存在 → 节点 #2 应产生 BLOCKER
  TC3: 所有 AnalysisResult status 为 "failed" → 节点 #3 应产生 BLOCKER
  TC4: 注入 HR=500 → 节点 #3 统计量合理性检查应产生 WARNING
  TC5: 注入 logFC=3.0 + HR=0.5（保护因素）矛盾 → 节点 #3 跨节点矛盾检测应产生 WARNING
  TC6: 注入 logFC=0.3 + result_interpretation="significantly overexpressed"
       → 节点 #3 效应量检查应产生 WARNING
  TC7: 注入不存在的 PMID → Phase 1 后的 _verify_pmids() 应标记（S1 Layer 3 V1 (EvidenceSynthesizer._verify_pmids, via pipeline.literature_agent._synthesizer)）
  TC8: 4 个 AnalysisResult 中只有 3 个出现在报告中 → 节点 #3 覆盖率检查应产生 WARNING
  TC9: logFC=-3.0 + result_interpretation=significantly overexpressed -> direction contradiction -> WARNING

注入时机：CI 运行时 + 首次手动验证时
验收标准：所有 TC1-TC8 的期望输出与实际输出一致
```

---

## 附录 A：与已有资产的整合映射

| 已有资产 | 整合到 |
|---------|--------|
| S1 `LiteratureAgent` + `LiteratureReview` | `pipeline.py` Phase 1 — 完整复用，无修改 |
| S1 `LLMClient` | 所有 Agent 共用 |
| S1 `src/types.py` — `EvidenceLink`, `Hypothesis`, `Paper` | A1→A2 数据传递，无修改 |
| S2 `BenchmarkTask` + `EvalAgent` Protocol | `pipeline.py` Task Router + `run()` 签名 |
| Spatial `master.py` — 6 组件 + 拓扑排序 | `orchestration_agent.py` — 理念参考，实现不同（LLM 驱动 vs 硬编码） |
| Spatial F1-F5 失败分类 | `analysis_agent.py` — 直接复用分类体系，增加 F2 重试上限 |
| ITIP Phase C/E 结果 | `data/cache/tcga_coad_surv.json` — 缓存数据来源 |
| CSTB Module 4 免疫浸润 | `tools/immune_tools.py` — 数据源 |
| S1 `_verify_pmids()` | Phase 1 后复用，确保 PMID 验证 |

## 附录 B：与 02-detailed-design.md 的接口对齐

| S2 定义 | S3 消费方式 |
|---------|-----------|
| `EvalAgent` Protocol | `MultiAgentPipeline` 实现 `run(BenchmarkTask) -> dict` |
| `BenchmarkTask.VALID_TASK_IDS` | Task Router 按 task_id 分派（T1→S1, T2→Phase1+2, T3-T5→Phase2+3） |
| `AgentEvalMetrics` | S3 不直接使用 — 由 S2 的 `BiomedBenchmark.run_all()` 对 S3 输出计算 |
| `ContaminationRiskReport` | S3 不实现 — S2 的 contamination check 独立运行 |

**T6-EE 扩展**（P2，待协调）：
- S3 建议 S2 新增 `T6-EE`（End-to-End）任务，测试完整 A1→A4 流程
- 需要 S2 在 `BenchmarkTask.VALID_TASK_IDS` 中添加 T6-EE
- GT 来源：已发表 TCGA-COAD 分析的关键定量结果

## 附录 C：编码阶段注意事项（第二轮审查 5 条非阻塞建议）

在实现阶段必须注意：
1. Four new dataclasses must have complete __post_init__ validation.
   -> Implementation: src/agents/orchestration_agent.py (AnalysisNode),
      src/agents/pipeline.py (AnalysisPlan, PipelineResult),
      src/agents/analysis_agent.py (AnalysisResult)
2. Cache index JSON schema: columns: list[str] + dtypes: dict[str, str] + cached_at: str.
   -> Implementation: tools/tcga_tools.py -- CacheIndex/CachedAnalysis dataclass
3. P0-5 injection tests cover F2 (small sample), F3 (PH violation), F4 (missing gene).
   -> Implementation: tests/test_adversarial.py
      (test_f2_small_sample, test_f3_ph_violation, test_f4_missing_gene)
4. check_effect_size_claims(results: list[AnalysisResult]) -> list[str] confirmed.
   -> Implementation: agents/report_agent.py -- ReportAgent.validate_upstream()
5. Adversarial injection must include direction contradiction (TC9: logFC=-3.0
   but claims significantly overexpressed).
   -> Implementation: tests/test_adversarial.py -- test_tc9_direction_contradiction

---

> **⏸️ DESIGN COMPLETE — AWAITING REVIEW**（Stage 1 最终确认）
> 第二轮交叉审查已通过（0 BLOCKER, 0 MINOR — DESIGN LOCKED）。
> 等待主 Agent 确认后进入 Stage 2（增量实现）。
