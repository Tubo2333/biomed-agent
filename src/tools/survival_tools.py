# survival_tools.py — Survival analysis tools (cache query + F3 degradation)
#
# Per design/03-detailed-design.md §三 (SurvivalTools).
# Cox regression results come from pre-computed cache.
# F3 degradation: PH assumption violated → downgrade to KM + log-rank.

from __future__ import annotations

import logging
from typing import Any

from src.tools.tcga_tools import TCGADataAccessor, CacheMissError

logger = logging.getLogger(__name__)


class SurvivalTools:
    """Survival analysis tools: cache-first with F3 degradation path.

    Usage:
        accessor = TCGADataAccessor("data/cache/analysis_cache_index.json")
        cox = SurvivalTools.query_cox("CSTB", "TCGA-COAD", accessor)
        km = SurvivalTools.query_km("CSTB", "TCGA-COAD", accessor)
    """

    @staticmethod
    def query_cox(
        gene: str, dataset: str, accessor: TCGADataAccessor
    ) -> dict[str, Any]:
        """Query Cox regression results (cache-first).

        Returns:
            {
                "gene": str, "HR": float, "CI_lower": float, "CI_upper": float,
                "p_value": float, "ph_test_p": float | None, "n": int,
                "n_events": int, "ph_violation": bool,
                "method": "cox_regression" | "km_logrank"
            }

        F3 degradation:
            If the pre-computed result has a significant PH test
            (ph_test_p < 0.05), ph_violation is set to True.
            The caller (AnalysisAgent) should switch to KM+log-rank.
        """
        try:
            raw = accessor.query(gene, "survival_analysis", dataset)
        except CacheMissError as e:
            logger.warning(
                "Survival cache miss for %s/%s: %s. Triggering F4.", gene, dataset, e
            )
            raise

        result: dict[str, Any] = {
            "gene": gene,
            "HR": raw.get("cox_hr"),
            "CI_lower": raw.get("cox_ci_lower"),
            "CI_upper": raw.get("cox_ci_upper"),
            "p_value": raw.get("cox_p"),
            "ph_test_p": raw.get("ph_test_p"),  # may be absent
            "n": raw.get("n"),
            "n_events": raw.get("n_events"),
            "ph_violation": False,
            "method": "cox_regression",
        }

        # Schema validation: critical fields must not be None
        for key in ("HR", "CI_lower", "CI_upper", "p_value"):
            if result[key] is None:
                logger.warning(
                    "Missing critical field '%s' in survival cache for %s/%s",
                    key, gene, dataset,
                )

        # F3 check: PH assumption
        ph_p = result.get("ph_test_p")
        if ph_p is not None and ph_p < 0.05:
            logger.info(
                "PH assumption violated for %s (ph_test_p=%.4f). "
                "F3 degradation: Cox → KM+log-rank.",
                gene, ph_p,
            )
            result["ph_violation"] = True
            result["method"] = "km_logrank"

        return result

    @staticmethod
    def query_km(
        gene: str, dataset: str, accessor: TCGADataAccessor
    ) -> dict[str, Any]:
        """Query KM curve data.

        Returns a dict with log-rank p-value and basic survival summary.
        Currently backed by the same survival_analysis cache as query_cox.
        """
        try:
            raw = accessor.query(gene, "survival_analysis", dataset)
        except CacheMissError as e:
            logger.warning(
                "Survival cache miss for %s/%s: %s. Triggering F4.", gene, dataset, e
            )
            raise

        return {
            "gene": gene,
            "logrank_p": raw.get("logrank_p"),
            "n": raw.get("n"),
            "n_events": raw.get("n_events"),
            "method": "km_logrank",
        }
