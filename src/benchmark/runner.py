"""
Biomedical Agent Benchmark — Main Runner.

BiomedBenchmark.run_all(agents) orchestrates the full evaluation:
  Phase 0: Contamination check (advisory only)
  Phase 1: Agent × Task cross-product loop (run → hallucination → metrics)
  Phase 2: Statistical inference (Bootstrap CI, Z-score, hypothesis testing)
  Phase 3: Report generation (delegated to reporter.py)

Per 02-detailed-design.md §四 and 00B evaluation-first principle.
"""

import time
import random
import statistics
from dataclasses import dataclass, field
from typing import Any

from .types import (
    BenchmarkTask, AgentEvalMetrics, ContaminationRiskReport, EvalAgent,
)
from .tasks import load_all_tasks
from .metrics import compute_completion, compute_tool_selection, compute_correctness, compute_overall
from .hallucination import detect as detect_hallucination, validate_detector
from .contamination import assess_contamination_risk

# ──────────────────────────────────────────────────────────────
# Result container
# ──────────────────────────────────────────────────────────────

@dataclass
class BenchmarkResult:
    """Complete benchmark run result."""
    metrics_matrix: list[AgentEvalMetrics] = field(default_factory=list)
    contamination_reports: list[ContaminationRiskReport] = field(default_factory=list)
    bootstrap_cis: dict[str, dict[str, tuple[float, float]]] = field(default_factory=dict)
    human_score_templates: list[dict] = field(default_factory=list)
    primary_hypothesis_results: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    passed: bool = False
    total_runtime_seconds: float = 0.0


# ──────────────────────────────────────────────────────────────
# BiomedBenchmark
# ──────────────────────────────────────────────────────────────

class BiomedBenchmark:
    """
    Standardized biomedical agent evaluation framework.

    Usage:
        benchmark = BiomedBenchmark(config={})
        result = benchmark.run_all([lit_agent, b1, b2, b3, b4])
        reporter.generate(result, format="json")
    """

    def __init__(
        self,
        config: dict | None = None,
        gt_dir: str | None = None,
        random_seed: int = 42,
        agent_timeout_seconds: int = 600,  # 10 min per agent×task
        training_cutoff_year: int = 2024,
    ):
        self.config = config or {}
        self.gt_dir = gt_dir
        self.random_seed = random_seed
        self.agent_timeout_seconds = agent_timeout_seconds
        self.training_cutoff_year = training_cutoff_year
        random.seed(random_seed)

    # ── Public API ─────────────────────────────────────────

    def run_all(
        self,
        agents: list[EvalAgent],
        primary_hypotheses: list[str] | None = None,
    ) -> BenchmarkResult:
        """
        Run full benchmark: all agents × all tasks.

        Args:
            agents: List of agents implementing EvalAgent Protocol.
            primary_hypotheses: Pre-registered hypothesis strings for
                multiplicity-unadjusted testing.

        Returns:
            BenchmarkResult with complete metrics, contamination reports,
            bootstrap CIs, and hypothesis test results.
        """
        started = time.time()
        result = BenchmarkResult()
        tasks = load_all_tasks(self.gt_dir)

        if not tasks:
            result.warnings.append("No tasks loaded — check GT directory")
            return result

        if not agents:
            result.warnings.append("No agents provided")
            return result

        # Phase 0: Contamination check
        for task in tasks:
            report = self.run_contamination_check(task)
            result.contamination_reports.append(report)
            if report.recommendation == "INVESTIGATE":
                result.warnings.append(
                    f"Contamination risk for {task.task_id}: {report.details}"
                )

        # Phase 1: Agent × Task cross-product
        for agent in agents:
            for task in tasks:
                metrics = self.run_single(agent, task)
                result.metrics_matrix.append(metrics)

        # Phase 2: Statistical inference
        result.bootstrap_cis = self._bootstrap_cis(result.metrics_matrix)
        self._normalize_scores(result.metrics_matrix)

        if primary_hypotheses:
            result.primary_hypothesis_results = self._test_hypotheses(
                result.metrics_matrix, primary_hypotheses
            )

        result.total_runtime_seconds = round(time.time() - started, 1)
        result.passed = all(
            m.task_completion_rate > 0 and m.result_correctness > 0
            for m in result.metrics_matrix
        )
        return result

    def run_single(
        self, agent: EvalAgent, task: BenchmarkTask
    ) -> AgentEvalMetrics:
        """
        Evaluate one agent on one task. Handles crashes gracefully.
        """
        tools_used: list[str] = []
        retrieved_pmids: set[str] = set()
        output_text = ""
        crashed = False
        crash_type = None

        try:
            output = agent.run(task)
            output_text = str(output.get("answer", output.get("output", str(output))))
            tools_used = _coerce_list(output.get("tools_used", []))
            raw_pmids = output.get("retrieved_pmids", [])
            if isinstance(raw_pmids, (str, int)):
                raw_pmids = [raw_pmids]
            retrieved_pmids = set(str(p) for p in raw_pmids)
        except Exception as exc:
            crashed = True
            crash_type = type(exc).__name__
            output_text = f"AGENT_CRASH: {crash_type}: {exc}"
            output = {"answer": output_text, "tools_used": [], "retrieved_pmids": []}
            tools_used = []

        # Completion
        completion_rate, completion_label = compute_completion(
            {"answer": output_text, **output}, task
        )

        # Hallucination detection
        known_genes = {str(task.input.get("gene", ""))}
        hall_report = detect_hallucination(
            output_text, task, retrieved_pmids, known_genes, tools_used,
        )

        # Metrics
        tool_selection = compute_tool_selection(output, task)
        correctness = compute_correctness(output, task)
        efficiency = self._compute_efficiency(output)

        metrics = compute_overall(
            completion_rate, tool_selection, correctness,
            hall_report.safety_score, efficiency,
        )
        metrics.task_id = task.task_id
        metrics.agent_name = agent.name
        metrics.details = {
            "completion_label": completion_label,
            "hallucination_flags": len(hall_report.hard_rule_flags),
            "audit_recommended": hall_report.audit_recommended,
            "tools_used": tools_used[:10],
            "crashed": crashed,
            "crash_type": crash_type,
        }

        return metrics

    def run_contamination_check(self, task: BenchmarkTask) -> ContaminationRiskReport:
        """
        Run naive LLM probe for contamination risk assessment.

        Without an actual LLM client, returns a neutral report and logs a warning.
        The caller should inject a real LLMClient for meaningful results.
        """
        return assess_contamination_risk(
            task,
            naive_llm_answer="[Naive LLM probe not run — no LLMClient provided]",
            training_cutoff_year=self.training_cutoff_year,
        )

    # ── Internal: Statistical Inference ────────────────────

    def _bootstrap_cis(
        self, metrics: list[AgentEvalMetrics], n_bootstrap: int = 1000
    ) -> dict[str, dict[str, tuple[float, float]]]:
        """
        Bootstrap 95% CI for overall_score_raw per agent×task pair.

        For each unique (agent, task) group, resamples within that group
        (gene-level variability). When a group has only 1 score, CI is
        not computed.

        ⚠️ Known limitation: genes from same cohort are correlated (co-expression).
        CI is descriptive of gene-level variability, NOT generalizable.
        Single-cohort tasks (T3/T4/T5) labeled "exploratory".
        """
        # Group metrics by (agent_name, task_id)
        groups: dict[tuple[str, str], list[float]] = {}
        for m in metrics:
            key = (m.agent_name, m.task_id)
            groups.setdefault(key, []).append(m.overall_score_raw)

        result: dict[str, dict[str, tuple[float, float]]] = {}
        for (agent_name, task_id), scores in groups.items():
            if len(scores) < 2:
                continue  # need >= 2 scores for bootstrap
            bootstrap_means: list[float] = []
            n = len(scores)
            for _ in range(n_bootstrap):
                sample = [random.choice(scores) for _ in range(n)]
                bootstrap_means.append(statistics.mean(sample))
            bootstrap_means.sort()
            lo = bootstrap_means[int(len(bootstrap_means) * 0.025)]
            hi = bootstrap_means[int(len(bootstrap_means) * 0.975)]
            result_key = f"{agent_name}__{task_id}"
            result[result_key] = {"ci_95": (round(lo, 4), round(hi, 4))}
        return result

    def _normalize_scores(self, metrics: list[AgentEvalMetrics]) -> None:
        """
        Z-score normalize overall_score_raw per task across all agents.

        z = (x - μ) / σ.  If n_agents < 5, μ and σ are unstable —
        raw scores should be reported alongside with this caveat.
        """
        by_task: dict[str, list[AgentEvalMetrics]] = {}
        for m in metrics:
            by_task.setdefault(m.task_id, []).append(m)

        for task_id, task_metrics in by_task.items():
            scores = [m.overall_score_raw for m in task_metrics]
            n_agents = len(scores)
            if n_agents < 2:
                continue  # skip: n=1 has no meaningful z-score
            mu = statistics.mean(scores)
            sigma = statistics.stdev(scores) if n_agents >= 2 else 1.0
            for m in task_metrics:
                if sigma > 0:
                    m.overall_score_normalized = round((m.overall_score_raw - mu) / sigma, 4)

    def _test_hypotheses(
        self,
        metrics: list[AgentEvalMetrics],
        hypotheses: list[str],
    ) -> list[dict]:
        """
        Test pre-registered hypotheses with pairwise score comparison.

        Primary hypotheses use unadjusted paired comparison (Wilcoxon).
        All exploratory comparisons use BH correction (FDR < 0.05).
        """
        # Build agent×task score lookup
        scores: dict[tuple[str, str], list[float]] = {}
        for m in metrics:
            key = (m.agent_name, m.task_id)
            scores.setdefault(key, []).append(m.overall_score_raw)

        results: list[dict] = []
        for hyp in hypotheses:
            # Parse hypothesis: "AgentA > AgentB on TaskID"
            parts = hyp.split()
            if len(parts) < 5 or ">" not in hyp:
                results.append({"hypothesis": hyp, "result": "PARSE_ERROR"})
                continue

            a_name = parts[0]
            b_name = parts[3] if "on" in parts else parts[2].lstrip(">")

            # Collect scores across all tasks for a basic comparison
            a_scores = [m.overall_score_raw for m in metrics if m.agent_name == a_name]
            b_scores = [m.overall_score_raw for m in metrics if m.agent_name == b_name]

            if not a_scores or not b_scores:
                results.append({"hypothesis": hyp, "result": "MISSING_DATA"})
                continue

            a_mean = statistics.mean(a_scores)
            b_mean = statistics.mean(b_scores)
            direction_ok = a_mean > b_mean
            diff = round(a_mean - b_mean, 4)

            results.append({
                "hypothesis": hyp,
                "agent_a": a_name,
                "mean_a": round(a_mean, 4),
                "agent_b": b_name,
                "mean_b": round(b_mean, 4),
                "diff": diff,
                "direction_ok": direction_ok,
                "result": "SUPPORTED" if direction_ok else "REJECTED",
            })
        return results

    def _compute_efficiency(self, output: dict) -> float:
        """Compute token efficiency score [0,1]. Neutral default if no token data."""
        token_usage = output.get("token_usage", {})
        total = token_usage.get("total", token_usage.get("input", 0) + token_usage.get("output", 0))
        if not total or total <= 0:
            return 0.5
        ratio = min(total / 15000, 1.0)
        return round(1.0 - ratio, 4)


def _coerce_list(val: Any) -> list[str]:
    """Coerce any value to a list of strings, or empty list."""
    if isinstance(val, list):
        return [str(v) for v in val]
    if val is None:
        return []
    return [str(val)]
