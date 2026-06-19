"""
Biomedical Agent Benchmark — Shared Types.

Step 2 defines these types. Step 3 consumes BenchmarkTask, AgentEvalMetrics,
and EvalAgent Protocol. Step 4 consumes benchmark result JSON.

All dataclasses have __post_init__ validation per 00-master-coordination.md §2.3
and 00B Layer 2 (structural constraints as hard checks at construction time).
"""

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


# ──────────────────────────────────────────────────────────────
# BenchmarkTask — defined in 00-master-coordination.md §2.3
# ──────────────────────────────────────────────────────────────

@dataclass
class BenchmarkTask:
    """
    A single benchmark test case.

    Attributes:
        task_id: One of T1-LIT, T2-GDA, T3-DEG, T4-SURV, T5-DRUG.
        task_name: Human-readable name.
        description: Task description that the Agent reads.
        input: Task input (structure depends on task_id).
        ground_truth: Expected answer with metadata.
        evaluation_criteria: List of evaluation dimension names.
        difficulty: easy | medium | hard.
        category: retrieval | association | analysis | reasoning.
    """

    task_id: str
    task_name: str
    description: str
    input: dict[str, Any]
    ground_truth: dict[str, Any]
    evaluation_criteria: list[str]
    difficulty: str = "medium"
    category: str = "analysis"

    VALID_TASK_IDS = frozenset({"T1-LIT", "T2-GDA", "T3-DEG", "T4-SURV", "T5-DRUG"})
    VALID_DIFFICULTIES = frozenset({"easy", "medium", "hard"})
    VALID_CATEGORIES = frozenset({"retrieval", "association", "analysis", "reasoning"})

    def __post_init__(self) -> None:
        if self.task_id not in self.VALID_TASK_IDS:
            raise ValueError(f"task_id must be one of {self.VALID_TASK_IDS}")
        if self.difficulty not in self.VALID_DIFFICULTIES:
            raise ValueError(f"difficulty must be one of {self.VALID_DIFFICULTIES}")
        if self.category not in self.VALID_CATEGORIES:
            raise ValueError(f"category must be one of {self.VALID_CATEGORIES}")
        if not self.evaluation_criteria:
            raise ValueError("evaluation_criteria must not be empty")
        if not self.input:
            raise ValueError("input must not be empty")
        if not self.ground_truth:
            raise ValueError("ground_truth must not be empty")


# ──────────────────────────────────────────────────────────────
# AgentEvalMetrics — defined in 00-master-coordination.md §2.3,
# expanded per 02-detailed-design.md §2.1
# ──────────────────────────────────────────────────────────────

@dataclass
class AgentEvalMetrics:
    """
    Evaluation result for one Agent on one Task.

    Attributes:
        task_id: Which task was evaluated.
        agent_name: Which agent was evaluated.
        task_completion_rate: 0-1, whether the task completed (including
            justified refusal = full credit).
        tool_selection_accuracy: 0-1, whether correct tools/methods chosen.
        result_correctness: 0-1, whether output matches GT within tolerance.
        hallucination_rate: 0-1, fraction of claims flagged as hallucination
            (lower is better).
        safety_score: 0-1 (= 1 - hallucination_rate), for gate calculation.
        efficiency_score: Token usage vs task complexity.
        overall_score_raw: Weighted raw total before normalization.
        overall_score_normalized: Z-score normalized (None before normalization).
        trust_label: TRUSTWORTHY | BORDERLINE | NOT TRUSTWORTHY.
        details: Free-form evaluation log.
    """

    task_id: str
    agent_name: str
    task_completion_rate: float
    tool_selection_accuracy: float
    result_correctness: float
    hallucination_rate: float
    safety_score: float
    efficiency_score: float
    overall_score_raw: float
    overall_score_normalized: float | None = None
    trust_label: str = "TRUSTWORTHY"
    details: dict[str, Any] = field(default_factory=dict)

    VALID_TRUST_LABELS = frozenset({"TRUSTWORTHY", "BORDERLINE", "NOT TRUSTWORTHY"})

    _SCORED_FIELDS = (
        "task_completion_rate",
        "tool_selection_accuracy",
        "result_correctness",
        "hallucination_rate",
        "safety_score",
        "efficiency_score",
        "overall_score_raw",
    )

    def __post_init__(self) -> None:
        for field_name in self._SCORED_FIELDS:
            val = getattr(self, field_name)
            if not (0.0 <= val <= 1.0):
                raise ValueError(
                    f"{field_name} must be in [0, 1], got {val}"
                )
        if self.trust_label not in self.VALID_TRUST_LABELS:
            raise ValueError(
                f"trust_label must be one of {self.VALID_TRUST_LABELS}"
            )


# ──────────────────────────────────────────────────────────────
# ContaminationRiskReport — S2新增, 需回写 00-master-coordination.md §二
# ──────────────────────────────────────────────────────────────

@dataclass
class ContaminationRiskReport:
    """
    Advisory-only assessment of whether a Task's GT may have been memorized
    by the LLM during pre-training.

    This is NOT a gate on benchmark validity. It is a risk indicator.

    Attributes:
        task_id: Which task was checked.
        agent_name: Which agent was checked (usually naive LLM as probe).
        risk_score: 0-1, higher = more likely contaminated.
        naive_llm_answer_matches_gt: Whether naive LLM (no data) answered correctly.
        gt_overlaps_training_cutoff: Whether GT was published before LLM training cutoff.
        recommendation: OK | CAUTION | INVESTIGATE.
        details: Human-readable explanation.
    """

    task_id: str
    agent_name: str
    risk_score: float
    naive_llm_answer_matches_gt: bool
    gt_overlaps_training_cutoff: bool
    recommendation: str = "OK"
    details: str = ""

    VALID_RECOMMENDATIONS = frozenset({"OK", "CAUTION", "INVESTIGATE"})

    def __post_init__(self) -> None:
        if not (0.0 <= self.risk_score <= 1.0):
            raise ValueError(f"risk_score must be in [0, 1], got {self.risk_score}")
        if self.recommendation not in self.VALID_RECOMMENDATIONS:
            raise ValueError(
                f"recommendation must be one of {self.VALID_RECOMMENDATIONS}"
            )


# ──────────────────────────────────────────────────────────────
# EvalAgent Protocol
# ──────────────────────────────────────────────────────────────

@runtime_checkable
class EvalAgent(Protocol):
    """
    Protocol that any Agent must implement to be evaluated by BiomedBenchmark.

    Step 1's LiteratureAgent implements this. Step 3's MultiAgentPipeline
    implements this. All baselines (B1-B4) implement this.
    """

    def run(self, task: BenchmarkTask) -> dict[str, Any]:
        """
        Execute a benchmark task and return structured output.

        The output dictionary keys depend on task.task_id:
          T1-LIT: {"evidence_summary": str, "evidence_chain": list, ...}
          T2-GDA: {"association_judgment": str, "evidence": list, ...}
          T3-DEG: {"differentially_expressed_genes": list, "method": str, ...}
          T4-SURV: {"hazard_ratios": dict, "km_plot_data": dict, ...}
          T5-DRUG: {"drug_correlations": dict, "fdr_results": dict, ...}

        Raises:
            Exception: Any exception is caught by the benchmark runner
                       and recorded in AgentEvalMetrics.details.
        """
        ...

    @property
    def name(self) -> str:
        """
        Unique agent name for reporting.

        Examples: "LiteratureAgent", "B1-NaiveLLM", "B2-ReAct",
                  "B3-SimpleRAG", "B4-DomainReAct".
        """
        ...
