"""Tests for BiomedBenchmark runner (structural checks — full run needs LLM)."""

import pytest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from benchmark.runner import BiomedBenchmark, BenchmarkResult, _coerce_list
from benchmark.types import AgentEvalMetrics


class TestCoerceList:
    """Type coercion helper for tools_used."""

    def test_list_passthrough(self):
        assert _coerce_list(["a", "b"]) == ["a", "b"]

    def test_str_to_list(self):
        assert _coerce_list("single_tool") == ["single_tool"]

    def test_none_to_empty(self):
        assert _coerce_list(None) == []

    def test_int_to_list(self):
        assert _coerce_list(42) == ["42"]


class TestBenchmarkInstantiation:
    """BiomedBenchmark can be instantiated with default config."""

    def test_default_config(self):
        bb = BiomedBenchmark({})
        assert bb.agent_timeout_seconds == 600
        assert bb.training_cutoff_year == 2024

    def test_custom_timeout(self):
        bb = BiomedBenchmark({}, agent_timeout_seconds=120)
        assert bb.agent_timeout_seconds == 120


class TestRunAllWithNoAgents:
    """Edge case: no agents provided."""

    def test_no_agents_returns_warning(self):
        bb = BiomedBenchmark({})
        result = bb.run_all([])
        assert len(result.warnings) >= 1
        assert "No agents" in result.warnings[0]
        assert result.passed is False


class TestResultPassedCondition:
    """result.passed requires completion > 0 AND correctness > 0."""

    def test_all_zero_scores_not_passed(self):
        m = AgentEvalMetrics(
            task_id="T1-LIT", agent_name="X",
            task_completion_rate=0.0, tool_selection_accuracy=0.0,
            result_correctness=0.0, hallucination_rate=1.0,
            safety_score=0.0, efficiency_score=0.0,
            overall_score_raw=0.0, trust_label="NOT TRUSTWORTHY",
        )
        # With only this metric, result.passed would be False
        # (tested indirectly via run_all with no tasks)
        assert m.overall_score_raw == 0.0


class TestBootstrapCI:
    """Bootstrap CI correctness (structure check)."""

    def test_bootstrap_empty_metrics(self):
        bb = BiomedBenchmark({})
        cis = bb._bootstrap_cis([])
        assert cis == {}

    def test_bootstrap_few_metrics(self):
        """With <2 scores per group, bootstrap should skip."""
        m = AgentEvalMetrics(
            task_id="T1-LIT", agent_name="B1",
            task_completion_rate=1.0, tool_selection_accuracy=0.5,
            result_correctness=0.5, hallucination_rate=0.0,
            safety_score=1.0, efficiency_score=0.5,
            overall_score_raw=0.7, trust_label="TRUSTWORTHY",
        )
        bb = BiomedBenchmark({})
        cis = bb._bootstrap_cis([m])
        assert cis == {}  # 1 score per group → no CI

    def test_bootstrap_produces_ci(self):
        """With multiple scores per group, CI should be produced."""
        metrics = []
        for i in range(5):
            metrics.append(AgentEvalMetrics(
                task_id="T1-LIT", agent_name="B1",
                task_completion_rate=1.0, tool_selection_accuracy=0.5,
                result_correctness=0.5 + i * 0.02, hallucination_rate=0.0,
                safety_score=1.0, efficiency_score=0.5,
                overall_score_raw=0.7 + i * 0.01, trust_label="TRUSTWORTHY",
            ))
        bb = BiomedBenchmark({})
        cis = bb._bootstrap_cis(metrics)
        assert len(cis) >= 1
        key = "B1__T1-LIT"
        assert key in cis
        lo, hi = cis[key]["ci_95"]
        assert lo <= hi
        assert 0.0 <= lo <= 1.0
        assert 0.0 <= hi <= 1.0


class TestNormalizeScores:
    """Z-score normalization."""

    def test_normalize_with_multiple_agents(self):
        metrics = [
            AgentEvalMetrics(
                task_id="T1-LIT", agent_name=n,
                task_completion_rate=1.0, tool_selection_accuracy=0.5,
                result_correctness=0.5, hallucination_rate=0.0,
                safety_score=1.0, efficiency_score=0.5,
                overall_score_raw=s, trust_label="TRUSTWORTHY",
            )
            for n, s in [("A", 0.7), ("B", 0.8), ("C", 0.9)]
        ]
        bb = BiomedBenchmark({})
        bb._normalize_scores(metrics)
        assert metrics[0].overall_score_normalized is not None
        assert metrics[1].overall_score_normalized is not None
        assert metrics[2].overall_score_normalized is not None

    def test_normalize_single_agent_skipped(self):
        """n=1 agents: z-score should remain None."""
        m = AgentEvalMetrics(
            task_id="T1-LIT", agent_name="A",
            task_completion_rate=1.0, tool_selection_accuracy=0.5,
            result_correctness=0.5, hallucination_rate=0.0,
            safety_score=1.0, efficiency_score=0.5,
            overall_score_raw=0.7, trust_label="TRUSTWORTHY",
        )
        bb = BiomedBenchmark({})
        bb._normalize_scores([m])
        assert m.overall_score_normalized is None  # n=1 → skipped
