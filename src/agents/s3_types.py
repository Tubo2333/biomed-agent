# s3_types.py — Step 3 shared data types
#
# Defined per design/03-detailed-design.md §二.
# All dataclasses follow 00- §四 code style: dataclass + type hints + __post_init__.
# Every AnalysisResult includes 00B Layer 2 traceability fields
# (data_source, method, raw_output_file).

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.types import Hypothesis, LiteratureReview

# ---------------------------------------------------------------------------
# S3 shared types — to be written back to 00-master-coordination.md §二
# ---------------------------------------------------------------------------


@dataclass
class AnalysisNode:
    """A single node in the analysis DAG. Produced by A2 (LLM reasoning).

    Fields:
        node_id: Unique node identifier, e.g. "node_01_diff_expression"
        task: Analysis type from TASK_VOCABULARY
        gene_list: Target genes (≥1)
        data_source: Absolute path to data file
        method: Analysis method from METHOD_VOCABULARY
        parameters: Method parameters (may be empty)
        depends_on: Node IDs this node depends on (topological edges)
        rationale: WHY LLM chose this method — required for anti-template enforcement
    """

    node_id: str
    task: str
    gene_list: list[str] = field(default_factory=list)
    data_source: str = ""
    method: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    rationale: str = ""

    TASK_VOCABULARY: frozenset[str] = frozenset({
        "differential_expression",
        "survival_analysis",
        "immune_correlation",
        "drug_screening",
        "gene_gene_correlation",
        "pathway_enrichment",
    })

    METHOD_VOCABULARY: frozenset[str] = frozenset({
        "ttest",
        "mann_whitney",
        "limma_voom",
        "cox_regression",
        "km_logrank",
        "spearman",
        "pearson",
        "fdr_bh",
        "fdr_bonferroni",
    })

    def __post_init__(self) -> None:
        if not self.node_id or not self.node_id.strip():
            raise ValueError("node_id must not be empty")
        if self.task not in self.TASK_VOCABULARY:
            raise ValueError(
                f"task must be one of {set(self.TASK_VOCABULARY)}, "
                f"got '{self.task}'"
            )
        if not self.gene_list:
            raise ValueError("gene_list must not be empty")
        if self.method and self.method not in self.METHOD_VOCABULARY:
            raise ValueError(
                f"method must be one of {set(self.METHOD_VOCABULARY)}, "
                f"got '{self.method}'"
            )
        if not self.rationale or not self.rationale.strip():
            raise ValueError(
                "rationale is required for anti-template enforcement"
            )
        if not self.data_source:
            raise ValueError("data_source must not be empty")


@dataclass
class AnalysisPlan:
    """LLM-driven dynamic analysis plan. A2 output → A3 input.

    Different LiteratureReview inputs MUST produce different AnalysisPlans
    (anti-template mechanism verified by P1-1 acceptance test).

    Fields:
        question: Original research question
        hypotheses: From A1 LiteratureReview.hypotheses
        nodes: DAG nodes (≥1)
        edges: Topological edges as (from_node_id, to_node_id) tuples
        data_gaps: Predictions that cannot be tested with available data
    """

    question: str
    hypotheses: list[Hypothesis] = field(default_factory=list)
    nodes: list[AnalysisNode] = field(default_factory=list)
    edges: list[tuple[str, str]] = field(default_factory=list)
    data_gaps: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.nodes:
            raise ValueError("AnalysisPlan must have at least 1 node")
        if not self.hypotheses:
            raise ValueError("AnalysisPlan must reference at least 1 hypothesis")
        # Validate that all edge references exist in nodes
        node_ids = {n.node_id for n in self.nodes}
        for from_id, to_id in self.edges:
            if from_id not in node_ids:
                raise ValueError(f"Edge references unknown node: {from_id}")
            if to_id not in node_ids:
                raise ValueError(f"Edge references unknown node: {to_id}")
        # Cycle detection (DFS) — prevents infinite loop in topological sort
        if not _is_acyclic(self.nodes, self.edges):
            raise ValueError("AnalysisPlan contains a cycle in the DAG")


@dataclass
class AnalysisResult:
    """Execution result of a single analysis node. A3 output → A4 input.

    Includes 00B Layer 2 traceability fields: data_source, method, raw_output_file.
    Includes P1-2 decision log fields: why, what, result_interpretation.
    """

    node_id: str
    task: str
    status: str = "completed"  # "completed" | "degraded" | "failed"
    output: dict[str, Any] = field(default_factory=dict)

    # ── 00B Layer 2 traceability fields ──
    data_source: str = ""
    method: str = ""
    raw_output_file: str = ""

    # ── P1-2 decision log fields ──
    why: str = ""
    what: str = ""
    result_interpretation: str = ""

    # ── Failure recovery fields ──
    failure_type: Optional[str] = None  # None | "F1" | "F2" | "F3" | "F4" | "F5"
    retry_count: int = 0
    degradation_reason: Optional[str] = None

    VALID_STATUSES: frozenset[str] = frozenset({"completed", "degraded", "failed"})
    VALID_FAILURE_TYPES: frozenset[str] = frozenset(
        {"F1", "F2", "F3", "F4", "F5"}
    )

    def __post_init__(self) -> None:
        if self.task not in AnalysisNode.TASK_VOCABULARY:
            raise ValueError(
                f"task must be one of {set(AnalysisNode.TASK_VOCABULARY)}, "
                f"got '{self.task}'"
            )
        if self.status not in self.VALID_STATUSES:
            raise ValueError(
                f"status must be one of {set(self.VALID_STATUSES)}, "
                f"got '{self.status}'"
            )
        if self.failure_type is not None and self.failure_type not in self.VALID_FAILURE_TYPES:
            raise ValueError(
                f"failure_type must be one of {set(self.VALID_FAILURE_TYPES)}, "
                f"got '{self.failure_type}'"
            )
        if not self.data_source:
            raise ValueError("data_source is required for traceability (Layer 2)")
        if not self.method:
            raise ValueError("method is required for traceability (Layer 2)")
        if not self.raw_output_file:
            raise ValueError("raw_output_file is required for traceability (Layer 2)")
        if not self.why or not self.what:
            raise ValueError(
                "why/what are required for decision traceability (P1-2)"
            )


@dataclass
class PipelineResult:
    """Complete output of MultiAgentPipeline.run(). Consumed by Step 4.

    Fields:
        question: Original user question
        literature_review: A1 output (LiteratureReview from S1)
        analysis_plan: A2 output (AnalysisPlan)
        analysis_results: A3 output (list of AnalysisResult, ≥1)
        report: A4 output — full report text in Markdown
        total_tokens: {"input": N, "output": M, "total": N+M}
        execution_log: Step-by-step execution log entries
        layer4_warnings: All WARNINGs from Layer 4 cross-validation
    """

    question: str = ""
    literature_review: Optional[LiteratureReview] = None
    analysis_plan: Optional[AnalysisPlan] = None
    analysis_results: list[AnalysisResult] = field(default_factory=list)
    report: str = ""
    total_tokens: dict[str, int] = field(default_factory=dict)
    execution_log: list[dict[str, Any]] = field(default_factory=list)
    layer4_warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.analysis_results:
            raise ValueError("PipelineResult must have at least 1 AnalysisResult")
        if not self.report or not self.report.strip():
            raise ValueError("report must not be empty")
        if not self.execution_log:
            raise ValueError("execution_log must not be empty")


# ---------------------------------------------------------------------------
# Cache index types — used by tools/tcga_tools.py
# ---------------------------------------------------------------------------

@dataclass
class CachedAnalysis:
    """Metadata for a single cached analysis type.

    Fields:
        file: Path to the cache JSON file
        columns: Output field names, e.g. ["gene", "logFC", "adj_p"]
        dtypes: Field types, e.g. {"logFC": "float64"}
        cached_at: ISO 8601 timestamp of cache generation
        source_script: Path to the source data/script from which this cache was derived
    """

    file: str = ""
    columns: list[str] = field(default_factory=list)
    dtypes: dict[str, str] = field(default_factory=dict)
    cached_at: str = ""
    source_script: str = ""


@dataclass
class DatasetCache:
    """Cache metadata for a single dataset.

    Fields:
        expression_matrix: Path to expression matrix file
        survival_data: Path to survival data file (None if unavailable)
        genes_cached: List of genes with pre-computed results
        analyses_available: analysis_type → CachedAnalysis mapping
    """

    expression_matrix: str = ""
    survival_data: Optional[str] = None
    genes_cached: list[str] = field(default_factory=list)
    analyses_available: dict[str, CachedAnalysis] = field(default_factory=dict)


@dataclass
class CacheIndex:
    """In-memory representation of analysis_cache_index.json.

    Fields:
        datasets: dataset_name → DatasetCache mapping
    """

    datasets: dict[str, DatasetCache] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Layer 4 cross-validation types
# ---------------------------------------------------------------------------

@dataclass
class ValidationReport:
    """Standard output of validate_upstream() methods.

    Produced by Layer 4 cross-validation nodes #1 (A2→A1),
    #2 (A3→A2), #3 (A4→A3).

    Fields:
        validator: Which agent is validating ("A2" | "A3" | "A4")
        validated: Whose output is being validated ("A1" | "A2" | "A3")
        status: "PASS" | "WARNING" | "BLOCKER"
        checks_performed: List of checks that were executed
        warnings: Non-fatal issues found
        blockers: Fatal contradictions (non-empty → status must be "BLOCKER")
    """

    validator: str = ""
    validated: str = ""
    status: str = "PASS"
    checks_performed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)

    VALID_STATUSES: frozenset[str] = frozenset({"PASS", "WARNING", "BLOCKER"})
    VALID_AGENTS: frozenset[str] = frozenset({"A1", "A2", "A3", "A4"})

    def __post_init__(self) -> None:
        if self.validator not in self.VALID_AGENTS:
            raise ValueError(
                f"validator must be one of {set(self.VALID_AGENTS)}, "
                f"got '{self.validator}'"
            )
        if self.validated not in self.VALID_AGENTS:
            raise ValueError(
                f"validated must be one of {set(self.VALID_AGENTS)}, "
                f"got '{self.validated}'"
            )
        if self.status not in self.VALID_STATUSES:
            raise ValueError(
                f"status must be PASS/WARNING/BLOCKER, got '{self.status}'"
            )
        if self.status == "BLOCKER" and not self.blockers:
            raise ValueError(
                "status=BLOCKER but blockers list is empty"
            )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_acyclic(
    nodes: list[AnalysisNode], edges: list[tuple[str, str]]
) -> bool:
    """Check whether the DAG contains a cycle (DFS-based).

    Called from AnalysisPlan.__post_init__ to prevent infinite loops
    in topological sort downstream.
    """
    adj: dict[str, list[str]] = {n.node_id: [] for n in nodes}
    for from_id, to_id in edges:
        if from_id in adj and to_id in adj:
            adj[from_id].append(to_id)

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {nid: WHITE for nid in adj}

    def _dfs(nid: str) -> bool:
        color[nid] = GRAY
        for neighbor in adj.get(nid, []):
            if color.get(neighbor) == GRAY:
                return False  # back edge → cycle
            if color.get(neighbor) == WHITE:
                if not _dfs(neighbor):
                    return False
        color[nid] = BLACK
        return True

    for nid in adj:
        if color[nid] == WHITE:
            if not _dfs(nid):
                return False
    return True
