# drug_tools.py — GDSC2 drug sensitivity screening (real-time Python Spearman)
#
# Per design/03-detailed-design.md §三 (DrugTools).
# Real-time computation: gene expression vs drug IC50 Spearman correlation.
# BH FDR correction for multiple testing.

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

logger = logging.getLogger(__name__)


class DrugTools:
    """GDSC2 drug sensitivity screening via real-time Spearman correlation.

    Usage:
        results = DrugTools.screen_gene("CSTB", gdsc_expr_df, gdsc_response_df)
    """

    @staticmethod
    def screen_gene(
        gene: str,
        gdsc_expr: pd.DataFrame,
        gdsc_response: pd.DataFrame,
        top_k: int = 10,
        fdr_threshold: float = 0.05,
    ) -> dict[str, Any]:
        """Screen drugs correlated with a gene's expression in GDSC2.

        Steps:
          1. Extract gene expression across GDSC2 cell lines
          2. Spearman correlation with all drug IC50 values
          3. BH FDR correction
          4. Return top-k most significant associations

        Args:
            gene: Gene symbol
            gdsc_expr: Gene expression matrix (genes × cell_lines)
            gdsc_response: Drug response matrix (drugs × cell_lines)
            top_k: Number of top associations to return
            fdr_threshold: BH FDR significance threshold

        Returns:
            {
                "gene": str, "n_cell_lines": int, "n_drugs_tested": int,
                "top_drugs": list[dict], "fdr_threshold": float,
                "n_significant": int
            }

        Raises:
            ValueError: Gene not in expression matrix
        """
        if gene not in gdsc_expr.index:
            raise ValueError(f"Gene '{gene}' not found in GDSC2 expression matrix")

        gene_expr = gdsc_expr.loc[gene]

        # Find common cell lines
        common_cl = gene_expr.index.intersection(gdsc_response.columns)
        if len(common_cl) < 10:
            logger.warning(
                "Only %d common cell lines for %s — results may be unreliable",
                len(common_cl), gene,
            )

        gene_vals = gene_expr[common_cl].values.astype(float)

        results = []
        for drug in gdsc_response.index:
            drug_vals = gdsc_response.loc[drug, common_cl].values.astype(float)

            # Remove NaN
            mask = ~(np.isnan(gene_vals) | np.isnan(drug_vals))
            if mask.sum() < 10:
                continue

            rho, p_val = stats.spearmanr(gene_vals[mask], drug_vals[mask])
            results.append({
                "drug": drug,
                "spearman_r": float(rho),
                "p_value": float(p_val),
                "n_cell_lines": int(mask.sum()),
            })

        if not results:
            return {
                "gene": gene,
                "n_cell_lines": len(common_cl),
                "n_drugs_tested": 0,
                "top_drugs": [],
                "fdr_threshold": fdr_threshold,
                "n_significant": 0,
            }

        # Sort by p-value and apply BH correction
        results_df = pd.DataFrame(results)
        results_df = results_df.sort_values("p_value")

        # Benjamini-Hochberg FDR
        n = len(results_df)
        results_df["rank"] = range(1, n + 1)
        results_df["fdr_bh"] = results_df["p_value"] * n / results_df["rank"]
        # Ensure monotonicity
        results_df["fdr_bh"] = results_df["fdr_bh"].iloc[::-1].cummin()[::-1]

        significant = results_df[results_df["fdr_bh"] < fdr_threshold]
        top = results_df.head(top_k)

        return {
            "gene": gene,
            "n_cell_lines": len(common_cl),
            "n_drugs_tested": n,
            "top_drugs": top[["drug", "spearman_r", "p_value", "fdr_bh"]].to_dict(
                orient="records"
            ),
            "fdr_threshold": fdr_threshold,
            "n_significant": len(significant),
        }
