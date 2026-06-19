# immune_tools.py — Immune infiltration correlation (real-time Python Spearman)
#
# Per design/03-detailed-design.md §三 (ImmuneTools).
# Computes gene expression vs immune cell abundance correlations.
# Supports multiple immune deconvolution methods (CIBERSORT, TIMER, ssGSEA, etc.).

from __future__ import annotations

import logging
from typing import Any, Optional

import numpy as np
import pandas as pd
from scipy import stats

logger = logging.getLogger(__name__)


class ImmuneTools:
    """Immune infiltration correlation via real-time Spearman correlation.

    Usage:
        results = ImmuneTools.correlate_gene_immune(
            "CSTB", expr_df, immune_scores_df
        )
    """

    DEFAULT_METHODS = ["CIBERSORT", "TIMER", "ssGSEA", "ESTIMATE", "quanTIseq", "EPIC"]

    @staticmethod
    def correlate_gene_immune(
        gene: str,
        expr: pd.DataFrame,
        immune_scores: pd.DataFrame,
        methods: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Compute gene expression vs immune cell abundance correlations.

        Args:
            gene: Gene symbol
            expr: Expression matrix (genes × samples)
            immune_scores: Immune scores (cell_types × samples for each method).
                MultiIndex columns recommended: (method, cell_type).
            methods: Which immune methods to use (default: all available)

        Returns:
            {
                "gene": str, "n_samples": int,
                "correlations": {
                    method_name: {
                        cell_type: {"spearman_r": float, "p_value": float}
                    }
                }
            }

        Raises:
            ValueError: Gene not in expression matrix, or no common samples
        """
        if gene not in expr.index:
            raise ValueError(f"Gene '{gene}' not found in expression matrix")

        gene_expr = expr.loc[gene]

        if methods is None:
            # Auto-detect from column levels or use defaults
            if isinstance(immune_scores.columns, pd.MultiIndex):
                methods = list(immune_scores.columns.get_level_values(0).unique())
            else:
                methods = ImmuneTools.DEFAULT_METHODS

        correlations: dict[str, dict[str, dict[str, float]]] = {}

        for method in methods:
            method_cors: dict[str, dict[str, float]] = {}

            if isinstance(immune_scores.columns, pd.MultiIndex):
                if method not in immune_scores.columns.get_level_values(0):
                    continue
                method_df = immune_scores[method]
            else:
                # Single-level columns: try to match by prefix
                matching = [c for c in immune_scores.columns if c.startswith(method)]
                if not matching:
                    continue
                method_df = immune_scores[matching]

            for cell_type in method_df.columns:
                immune_vals = method_df[cell_type]

                # Find common samples
                common = gene_expr.index.intersection(immune_vals.index)
                if len(common) < 10:
                    logger.info(
                        "Skipping %s/%s: only %d common samples",
                        method, cell_type, len(common),
                    )
                    continue

                gv = gene_expr[common].values.astype(float)
                iv = immune_vals[common].values.astype(float)

                # Remove NaN
                mask = ~(np.isnan(gv) | np.isnan(iv))
                if mask.sum() < 10:
                    continue

                rho, p_val = stats.spearmanr(gv[mask], iv[mask])
                method_cors[cell_type] = {
                    "spearman_r": round(float(rho), 4),
                    "p_value": float(p_val),
                }

            if method_cors:
                correlations[method] = method_cors

        return {
            "gene": gene,
            "n_samples": len(gene_expr),
            "correlations": correlations,
        }
