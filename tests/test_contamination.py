"""Tests for contamination risk assessment (advisory only)."""

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from benchmark.contamination import assess_contamination_risk
from benchmark.types import BenchmarkTask, ContaminationRiskReport


def _make_task(**gt_kwargs):
    return BenchmarkTask(
        task_id="T2-GDA", task_name="t", description="t",
        input={"gene": "CSTB", "disease": "CRC"},
        ground_truth=gt_kwargs,
        evaluation_criteria=["test"],
    )


class TestContaminationRisk:
    """Contamination risk scoring logic."""

    def test_match_plus_precutoff_investigate(self):
        """Naive LLM matches GT + GT pre-cutoff → risk=0.8, INVESTIGATE."""
        task = _make_task(
            gene="CSTB", association="associated", direction="unfavorable",
            meta={"year": 2022},
        )
        report = assess_contamination_risk(
            task, "CSTB is associated with CRC and shows unfavorable prognosis",
            training_cutoff_year=2024,
        )
        assert report.risk_score == 0.8
        assert report.recommendation == "INVESTIGATE"
        assert report.naive_llm_answer_matches_gt is True
        assert report.gt_overlaps_training_cutoff is True

    def test_no_match_post_cutoff_ok(self):
        """No match + GT after cutoff → risk=0.0, OK."""
        task = _make_task(
            gene="CSTB", association="associated",
            meta={"year": 2025},
        )
        report = assess_contamination_risk(
            task, "I do not know the answer.",
            training_cutoff_year=2024,
        )
        assert report.risk_score == 0.0
        assert report.recommendation == "OK"

    def test_match_only_caution(self):
        """Match only, no pre-cutoff → risk=0.5, CAUTION."""
        task = _make_task(
            gene="TP53",
            meta={"year": 2025},
        )
        report = assess_contamination_risk(
            task, "TP53 is a tumor suppressor gene.",
            training_cutoff_year=2024,
        )
        assert report.risk_score == 0.5
        assert report.recommendation == "CAUTION"

    def test_precutoff_only_ok(self):
        """No match, but GT pre-cutoff → risk=0.3, OK."""
        task = _make_task(
            gene="CSTB", association="associated",
            meta={"year": 2022},
        )
        report = assess_contamination_risk(
            task, "I don't know anything about this.",
            training_cutoff_year=2024,
        )
        assert report.risk_score == 0.3
        assert report.recommendation == "OK"

    def test_output_is_contamination_risk_report(self):
        """Return type is ContaminationRiskReport dataclass."""
        task = _make_task(gene="X", meta={"year": 2020})
        report = assess_contamination_risk(task, "blah", 2024)
        assert isinstance(report, ContaminationRiskReport)
        assert report.task_id == "T2-GDA"
        assert report.agent_name == "NaiveLLM-Probe"

    def test_risk_score_in_range(self):
        """Risk score always in [0, 1]."""
        task = _make_task(gene="X", meta={"year": 2020})
        for answer in ["X is a gene.", "I don't know.", ""]:
            report = assess_contamination_risk(task, answer, 2024)
            assert 0.0 <= report.risk_score <= 1.0

    def test_missing_meta_year(self):
        """Missing year in meta → no pre-cutoff component."""
        task = _make_task(gene="CSTB")
        report = assess_contamination_risk(
            task, "CSTB is a gene.", training_cutoff_year=2024,
        )
        assert report.gt_overlaps_training_cutoff is False
        assert report.risk_score <= 0.5  # only match component possible
