# tcga_tools.py — TCGADataAccessor: three-tier fallback data access layer
#
# Per design/03-detailed-design.md §三 (TCGADataAccessor) and §6.4 (method rules).
# Three-tier strategy: cache hit → real-time Python → F4 degradation.
# Agent calls a single query() interface; the tier selection is internal.

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from src.agents.s3_types import CacheIndex, CachedAnalysis, DatasetCache

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# Method compatibility rules (design §6.4)
# ═══════════════════════════════════════════════════════════════

METHOD_COMPATIBILITY: dict[tuple[str, str], list[str]] = {
    ("continuous_expr", "binary_group"): ["ttest", "mann_whitney", "limma_voom"],
    ("continuous_expr", "survival"): ["cox_regression", "km_logrank"],
    ("continuous_expr", "continuous_immune"): ["spearman", "pearson"],
    ("drug_response", "continuous_expr"): ["spearman", "pearson"],
    ("continuous_expr", "continuous_expr"): ["spearman", "pearson"],
}

SAMPLE_SIZE_CONSTRAINTS: dict[str, Any] = {
    "ttest": lambda n: n >= 6,
    "mann_whitney": lambda n: n >= 6,
    "cox_regression": lambda n: n >= 30,
    "spearman": lambda n: n >= 10,
    "pearson": lambda n: n >= 10,
}

INVALID_COMBINATIONS: frozenset[tuple[str, str]] = frozenset({
    ("anova", "binary_group"),
    ("spearman", "binary_group"),
    ("pearson", "binary_group"),
})

# task → (data_type_1, data_type_2) mapping (design §6.4 M5)
TASK_DATA_TYPES: dict[str, Optional[tuple[str, str]]] = {
    "differential_expression": ("continuous_expr", "binary_group"),
    "survival_analysis": ("continuous_expr", "survival"),
    "immune_correlation": ("continuous_expr", "continuous_immune"),
    "drug_screening": ("drug_response", "continuous_expr"),
    "gene_gene_correlation": ("continuous_expr", "continuous_expr"),
    "pathway_enrichment": None,  # no hard rule, LLM judges
}

# Analysis types NOT supported for real-time fallback (require R or specialized tools)
UNSUPPORTED_REALTIME: frozenset[str] = frozenset({
    "survival_analysis", "cox_regression", "pathway_enrichment",
})

# Analysis types SUPPORTED for real-time fallback (pure Python scipy)
SUPPORTED_REALTIME: frozenset[str] = frozenset({
    "differential_expression", "immune_correlation",
    "drug_screening", "gene_gene_correlation",
})


def _check_method_compatibility(task: str, method: str) -> bool:
    """Check if method is compatible with task type."""
    types = TASK_DATA_TYPES.get(task)
    if types is None:
        return True  # unconstrained task type
    allowed = METHOD_COMPATIBILITY.get(types, [])
    return method in allowed


# ═══════════════════════════════════════════════════════════════
# TCGADataAccessor
# ═══════════════════════════════════════════════════════════════


class CacheMissError(Exception):
    """Raised when both cache and real-time fallback fail (triggers F4)."""


class TCGADataAccessor:
    """Unified TCGA data access layer with three-tier fallback.

    Usage:
        accessor = TCGADataAccessor("data/cache/analysis_cache_index.json")
        result = accessor.query("CSTB", "differential_expression", "TCGA-COAD")
    """

    def __init__(self, cache_index_path: str = "data/cache/analysis_cache_index.json") -> None:
        self._cache_index_path = Path(cache_index_path)
        self._index: CacheIndex = self._load_index()
        # Cache for loaded analysis data: (gene, analysis_type, dataset) → result dict
        self._cache: dict[tuple[str, str, str], dict[str, Any]] = {}

    # ── Public API ──────────────────────────────────────────

    def query(
        self, gene: str, analysis_type: str, dataset: str
    ) -> dict[str, Any]:
        """Query analysis result for a gene.

        Three-tier fallback:
          (1) Cache hit → return cached result
          (2) Cache miss → real-time Python (t-test / Spearman)
          (3) Real-time fails → raise CacheMissError (triggers F4)

        Args:
            gene: Gene symbol, e.g. "CSTB"
            analysis_type: One of TASK_DATA_TYPES keys
            dataset: Dataset name, e.g. "TCGA-COAD"

        Returns:
            Result dict with keys depending on analysis_type

        Raises:
            CacheMissError: Both cache and real-time fallback failed
            ValueError: Unknown dataset or analysis_type
        """
        # ── Tier 1: Cache query ──
        cache_key = (gene, analysis_type, dataset)
        if cache_key in self._cache:
            logger.info("Cache hit: %s/%s/%s", gene, analysis_type, dataset)
            return self._cache[cache_key]

        cached = self._query_cache(gene, analysis_type, dataset)
        if cached is not None:
            self._cache[cache_key] = cached
            return cached

        # ── Tier 2: Real-time Python ──
        if analysis_type in UNSUPPORTED_REALTIME:
            raise CacheMissError(
                f"Analysis type '{analysis_type}' is not supported for "
                f"real-time fallback. Cache miss → F4 degradation."
            )

        if analysis_type not in SUPPORTED_REALTIME:
            raise CacheMissError(
                f"Unknown analysis type '{analysis_type}' — "
                f"not in supported or unsupported lists."
            )

        try:
            realtime = self._realtime_compute(gene, analysis_type, dataset)
            self._cache[cache_key] = realtime
            return realtime
        except Exception as e:
            raise CacheMissError(
                f"Real-time computation failed for {gene}/{analysis_type}/"
                f"{dataset}: {e}"
            ) from e

    def is_cached(self, gene: str, analysis_type: str, dataset: str) -> bool:
        """Check whether a gene×analysis_type×dataset combo has a cache entry."""
        ds = self._index.datasets.get(dataset)
        if ds is None:
            return False
        if gene not in ds.genes_cached:
            return False
        return analysis_type in ds.analyses_available

    def list_cached_genes(self, dataset: str) -> list[str]:
        """List genes with any cached analysis in a dataset."""
        ds = self._index.datasets.get(dataset)
        if ds is None:
            return []
        return list(ds.genes_cached)

    # ── Internal: Cache tier ────────────────────────────────

    def _query_cache(
        self, gene: str, analysis_type: str, dataset: str
    ) -> Optional[dict[str, Any]]:
        """Try to load result from pre-computed cache JSON."""
        ds = self._index.datasets.get(dataset)
        if ds is None:
            logger.warning("Unknown dataset: %s", dataset)
            return None

        if gene not in ds.genes_cached:
            return None

        cached_analysis = ds.analyses_available.get(analysis_type)
        if cached_analysis is None:
            return None

        cache_file = Path(cached_analysis.file)
        if not cache_file.exists():
            logger.warning("Cache file missing: %s", cache_file)
            return None

        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                records = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Failed to read cache file %s: %s", cache_file, e)
            return None

        for record in records:
            if record.get("gene") == gene:
                return record

        return None  # gene not in this cache file

    # ── Internal: Real-time tier ────────────────────────────

    def _realtime_compute(
        self, gene: str, analysis_type: str, dataset: str
    ) -> dict[str, Any]:
        """Compute analysis in pure Python (t-test / Spearman).

        This is a lightweight fallback for when the cache misses.
        Only supports differential_expression (t-test) and
        correlation-type analyses (Spearman).

        Requires the expression matrix to be accessible as CSV/DataFrame.
        """
        ds = self._index.datasets.get(dataset)
        if ds is None:
            raise CacheMissError(f"Unknown dataset: {dataset}")

        expr_path = Path(ds.expression_matrix)
        if not expr_path.exists():
            raise CacheMissError(f"Expression matrix not found: {expr_path}")

        # Load expression data — try CSV first, otherwise note RDS limitation
        if expr_path.suffix == ".csv":
            expr_df = pd.read_csv(expr_path, index_col=0)
        else:
            raise CacheMissError(
                f"Expression matrix is in RDS format ({expr_path}). "
                f"Real-time computation requires CSV export. "
                f"Run the pre-computation script first."
            )

        if gene not in expr_df.index:
            raise CacheMissError(
                f"Gene '{gene}' not found in expression matrix"
            )

        gene_expr = expr_df.loc[gene]

        if analysis_type == "differential_expression":
            return self._compute_ttest(gene, gene_expr, dataset)
        elif analysis_type in (
            "immune_correlation", "drug_screening", "gene_gene_correlation"
        ):
            return self._compute_spearman(gene, gene_expr, dataset)
        else:
            raise CacheMissError(
                f"Real-time compute not implemented for '{analysis_type}'"
            )

    def _compute_ttest(
        self, gene: str, gene_expr: pd.Series, dataset: str
    ) -> dict[str, Any]:
        """Compute Welch t-test for tumor vs normal."""
        # Placeholder: needs sample group labels
        # In real implementation, load clinical data to get tumor/normal labels
        raise CacheMissError(
            "Real-time t-test requires clinical metadata (tumor/normal labels). "
            "Please use pre-computed cache for differential_expression."
        )

    def _compute_spearman(
        self, gene: str, gene_expr: pd.Series, dataset: str
    ) -> dict[str, Any]:
        """Compute Spearman correlation."""
        raise CacheMissError(
            "Real-time Spearman requires a target variable matrix. "
            "Please use pre-computed cache or provide target data."
        )

    # ── Internal: Index loading ─────────────────────────────

    def _load_index(self) -> CacheIndex:
        """Load and parse analysis_cache_index.json."""
        if not self._cache_index_path.exists():
            logger.warning(
                "Cache index not found at %s. Creating empty index.",
                self._cache_index_path,
            )
            return CacheIndex()

        with open(self._cache_index_path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        datasets: dict[str, DatasetCache] = {}
        for ds_name, ds_data in raw.get("datasets", {}).items():
            analyses: dict[str, CachedAnalysis] = {}
            for at_name, at_data in ds_data.get("analyses_available", {}).items():
                analyses[at_name] = CachedAnalysis(
                    file=at_data.get("file", ""),
                    columns=at_data.get("columns", []),
                    dtypes=at_data.get("dtypes", {}),
                    cached_at=at_data.get("cached_at", ""),
                    source_script=at_data.get("source_script", ""),
                )
            datasets[ds_name] = DatasetCache(
                expression_matrix=ds_data.get("expression_matrix", ""),
                survival_data=ds_data.get("survival_data"),
                genes_cached=ds_data.get("genes_cached", []),
                analyses_available=analyses,
            )

        return CacheIndex(datasets=datasets)
