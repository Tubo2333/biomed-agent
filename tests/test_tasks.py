"""Tests for benchmark task definitions and ground truth loading."""

import pytest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from benchmark.tasks import (
    load_all_tasks, make_t2_gda_tasks,
    TOLERANCE_BANDS, _check_tolerance, _check_direction,
)
from benchmark.types import BenchmarkTask


class TestToleranceBands:
    """Verify Appendix A tolerance bands are correctly defined and checked."""

    def test_logfc_absolute_pass(self):
        """logFC within absolute bound should pass."""
        assert _check_tolerance(2.3, 2.3, ("logfc", (0.5, 0.20))) is True

    def test_logfc_absolute_boundary(self):
        """logFC exactly at absolute boundary should pass."""
        assert _check_tolerance(2.8, 2.3, ("logfc", (0.5, 0.20))) is True

    def test_logfc_relative_pass(self):
        """Small logFC values should pass via relative bound."""
        assert _check_tolerance(0.55, 0.5, ("logfc", (0.5, 0.20))) is True

    def test_logfc_fail(self):
        """logFC exceeding both bounds should fail."""
        assert _check_tolerance(3.5, 2.3, ("logfc", (0.5, 0.20))) is False

    def test_hr_multiplicative_pass(self):
        """HR within ±15% should pass."""
        assert _check_tolerance(1.42, 1.42, ("multiplicative", (0.85, 1.15))) is True
        assert _check_tolerance(1.25, 1.42, ("multiplicative", (0.85, 1.15))) is True

    def test_hr_multiplicative_fail(self):
        """HR outside ±15% should fail."""
        assert _check_tolerance(2.0, 1.42, ("multiplicative", (0.85, 1.15))) is False

    def test_direction_pass(self):
        """Same-side significance should pass."""
        assert _check_direction(0.003, 0.001) is True

    def test_direction_fail(self):
        """Opposite-side significance should fail."""
        assert _check_direction(0.003, 0.15) is False

    def test_unknown_mode_raises(self):
        """Unknown tolerance mode should raise ValueError."""
        with pytest.raises(ValueError):
            _check_tolerance(1.0, 1.0, ("unknown_mode", (0.5, 1.5)))


class TestTaskLoading:
    """Verify all 5 task types load with non-empty ground truth."""

    def test_all_tasks_load(self):
        tasks = load_all_tasks()
        assert len(tasks) >= 5, f"Expected >= 5 tasks, got {len(tasks)}"

    def test_each_task_has_non_empty_gt(self):
        for task in load_all_tasks():
            assert task.ground_truth, f"{task.task_id}: ground_truth is empty"

    def test_each_task_has_valid_id(self):
        for task in load_all_tasks():
            assert task.task_id in BenchmarkTask.VALID_TASK_IDS

    def test_tolerance_bands_cover_all_analysis_tasks(self):
        """T3/T4/T5 must have tolerance bands defined."""
        assert "T3-DEG" in TOLERANCE_BANDS
        assert "T4-SURV" in TOLERANCE_BANDS
        assert "T5-DRUG" in TOLERANCE_BANDS


class TestT2GDALowConfidence:
    """T2-GDA low-confidence entries must have exclude_from_primary flag."""

    def test_low_confidence_has_exclude_flag(self):
        tasks = make_t2_gda_tasks()
        low_tasks = [t for t in tasks if t.ground_truth.get("confidence") == "low"]
        for t in low_tasks:
            assert t.ground_truth.get("exclude_from_primary") is True, (
                f"Low-confidence task {t.task_name} missing exclude_from_primary"
            )


class TestTaskDescriptionsBilingual:
    """All task descriptions must include both Chinese and English per GOV-005."""

    def test_descriptions_are_bilingual(self):
        for task in load_all_tasks():
            has_cn = any("一" <= ch <= "鿿" for ch in task.description)
            has_en = any(c.isascii() and c.isalpha() for c in task.description)
            assert has_cn or has_en, (
                f"{task.task_id}: description should have content"
            )
