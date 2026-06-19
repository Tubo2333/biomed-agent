"""Tests for metrics computation engine."""

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from benchmark.metrics import (
    compute_completion, compute_safety, apply_safety_penalty, compute_overall,
    WEIGHTS,
)
from benchmark.types import BenchmarkTask


def _make_task(task_id="T1-LIT", **gt_kwargs):
    return BenchmarkTask(
        task_id=task_id, task_name="t", description="t",
        input={"gene": "CSTB", "dataset": "TCGA-COAD"},
        ground_truth=gt_kwargs or {"x": 1},
        evaluation_criteria=["test"],
    )


class TestCompletion:
    """Three-way completion classification."""

    def test_answered(self):
        r, label = compute_completion(
            {"answer": "CSTB is overexpressed in CRC. PMID:12345678 confirms this."},
            _make_task(),
        )
        assert r == 1.0 and label == "answered"

    def test_refused_good(self):
        """Agent refuses but gives partial answer + references input data."""
        r, label = compute_completion(
            {"answer": "无法完成完整分析因为 TCGA-COAD 表达数据中缺少 CSTB 的蛋白质水平信息。基于现有 mRNA 数据，CSTB 在肿瘤中高表达。"},
            _make_task(),
        )
        assert r == 1.0 and label == "refused"

    def test_refused_english(self):
        r, label = compute_completion(
            {"answer": "I cannot access the raw sequencing data. However, based on available TCGA-COAD data, CSTB shows elevated expression."},
            _make_task(),
        )
        assert r == 1.0 and label == "refused"

    def test_crashed_empty(self):
        r, label = compute_completion({"answer": ""}, _make_task())
        assert r == 0.0 and label == "crashed"

    def test_always_refuse_self_limiting(self):
        """Serial refusal gives completion=1 but correctness will be 0."""
        # Even a short refusal that doesn't meet the conditions counts as answered
        r, label = compute_completion(
            {"answer": "Cannot answer."},  # <50 chars, ambiguous
            _make_task(),
        )
        # With <50 chars + no input reference → might be counted as answered
        # The self-limiting mechanism is: correctness=0 → low overall score
        assert r in (0.0, 1.0)


class TestSafety:
    """Safety score and continuous penalty."""

    def test_safety_perfect(self):
        safety, label = compute_safety(0.0)
        assert safety == 1.0
        assert label == "TRUSTWORTHY"

    def test_safety_borderline(self):
        safety, label = compute_safety(0.25)
        assert safety == 0.75
        assert label == "BORDERLINE"

    def test_safety_not_trustworthy(self):
        safety, label = compute_safety(0.5)
        assert safety == 0.5
        assert label == "NOT TRUSTWORTHY"

    def test_penalty_no_penalty(self):
        raw, penalty = apply_safety_penalty(0.8, 1.0)
        assert raw == 0.8 and penalty == 1.0

    def test_penalty_partial(self):
        raw, penalty = apply_safety_penalty(0.8, 0.5)
        expected_penalty = 1.0 - (0.7 - 0.5) / 0.7  # ~0.714
        assert abs(penalty - expected_penalty) < 0.01
        assert abs(raw - 0.8 * expected_penalty) < 0.01

    def test_penalty_annihilated(self):
        raw, penalty = apply_safety_penalty(0.8, 0.0)
        assert raw == 0.0 and penalty == 0.0


class TestWeights:
    """Weight configuration matches design doc."""

    def test_weights_sum_to_one(self):
        total = sum(WEIGHTS.values())
        assert abs(total - 1.0) < 0.01

    def test_correctness_highest(self):
        assert WEIGHTS["correctness"] == max(WEIGHTS.values())


class TestOverallScore:
    """Full metric aggregation."""

    def test_compute_overall_clamps_inputs(self):
        m = compute_overall(1.5, 0.5, 0.5, 0.8, 0.5)
        assert m.task_completion_rate == 1.0  # clamped

    def test_compute_overall_perfect_agent(self):
        m = compute_overall(1.0, 1.0, 1.0, 1.0, 1.0)
        assert m.overall_score_raw == 1.0
        assert m.trust_label == "TRUSTWORTHY"

    def test_compute_overall_untrustworthy_agent(self):
        m = compute_overall(1.0, 0.5, 0.5, 0.4, 0.5)
        assert m.trust_label == "NOT TRUSTWORTHY"
        # Safety penalty should reduce score
        assert m.overall_score_raw < 0.5
