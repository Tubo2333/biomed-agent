# test_tcga_tools.py — Tests for TCGADataAccessor and method compatibility rules
#
# Covers: cache queries, three-tier fallback, method compatibility matrix,
# task-data-type mapping, CacheMissError propagation.

import pytest

from src.tools.tcga_tools import (
    TCGADataAccessor,
    CacheMissError,
    TASK_DATA_TYPES,
    SAMPLE_SIZE_CONSTRAINTS,
    INVALID_COMBINATIONS,
    UNSUPPORTED_REALTIME,
    SUPPORTED_REALTIME,
    _check_method_compatibility,
)


# ═══════════════════════════════════════════════════════════════
# Cache query tests
# ═══════════════════════════════════════════════════════════════

class TestCacheQuery:
    """Test cache-based data access (Tier 1 of three-tier fallback)."""

    def test_load_cache_index(self):
        """Cache index should load and expose TCGA-COAD dataset."""
        accessor = TCGADataAccessor("data/cache/analysis_cache_index.json")
        assert "TCGA-COAD" in accessor._index.datasets
        ds = accessor._index.datasets["TCGA-COAD"]
        assert "CSTB" in ds.genes_cached
        assert "differential_expression" in ds.analyses_available
        assert "survival_analysis" in ds.analyses_available

    def test_query_deg_cstb(self):
        """Differential expression query for CSTB should return real data."""
        accessor = TCGADataAccessor("data/cache/analysis_cache_index.json")
        result = accessor.query("CSTB", "differential_expression", "TCGA-COAD")
        assert result["gene"] == "CSTB"
        assert "log2FC" in result
        assert "p_adj" in result
        assert isinstance(result["log2FC"], float)

    def test_query_survival_cstb(self):
        """Survival analysis query for CSTB should return real data."""
        accessor = TCGADataAccessor("data/cache/analysis_cache_index.json")
        result = accessor.query("CSTB", "survival_analysis", "TCGA-COAD")
        assert result["gene"] == "CSTB"
        assert "cox_hr" in result
        assert result["cox_hr"] > 0

    def test_is_cached(self):
        """is_cached should correctly report cache availability."""
        accessor = TCGADataAccessor("data/cache/analysis_cache_index.json")
        assert accessor.is_cached("CSTB", "differential_expression", "TCGA-COAD")
        assert not accessor.is_cached("TP53", "differential_expression", "TCGA-COAD")
        assert not accessor.is_cached("CSTB", "drug_screening", "TCGA-COAD")

    def test_list_cached_genes(self):
        """list_cached_genes should return the right genes."""
        accessor = TCGADataAccessor("data/cache/analysis_cache_index.json")
        genes = accessor.list_cached_genes("TCGA-COAD")
        assert "CSTB" in genes

    def test_memory_cache_hit(self):
        """Second query for same gene should hit in-memory cache."""
        accessor = TCGADataAccessor("data/cache/analysis_cache_index.json")
        result1 = accessor.query("CSTB", "differential_expression", "TCGA-COAD")
        result2 = accessor.query("CSTB", "differential_expression", "TCGA-COAD")
        assert result1 is result2  # same object, cached in memory


class TestCacheMiss:
    """Test CacheMissError for uncached genes and unsupported real-time types."""

    def test_uncached_gene_survival_raises(self):
        """Uncached gene with unsupported realtime should raise CacheMissError."""
        accessor = TCGADataAccessor("data/cache/analysis_cache_index.json")
        with pytest.raises(CacheMissError):
            accessor.query("TP53", "survival_analysis", "TCGA-COAD")

    def test_unknown_dataset_returns_none(self):
        """Unknown dataset should return None from _query_cache."""
        accessor = TCGADataAccessor("data/cache/analysis_cache_index.json")
        assert not accessor.is_cached("CSTB", "differential_expression", "UNKNOWN")


class TestEmptyCacheIndex:
    """Test behavior when cache index is missing."""

    def test_missing_index_creates_empty(self):
        """Missing cache index should create an empty CacheIndex."""
        accessor = TCGADataAccessor("nonexistent/path/cache_index.json")
        assert accessor._index.datasets == {}
        assert accessor.list_cached_genes("ANY") == []


# ═══════════════════════════════════════════════════════════════
# Method compatibility tests
# ═══════════════════════════════════════════════════════════════

class TestMethodCompatibility:
    """Test METHOD_COMPATIBILITY matrix and _check_method_compatibility."""

    def test_valid_combinations(self):
        """Known valid task-method pairs should pass."""
        assert _check_method_compatibility("differential_expression", "ttest")
        assert _check_method_compatibility("differential_expression", "limma_voom")
        assert _check_method_compatibility("survival_analysis", "cox_regression")
        assert _check_method_compatibility("immune_correlation", "spearman")
        assert _check_method_compatibility("drug_screening", "spearman")

    def test_invalid_combinations(self):
        """Invalid task-method pairs should fail."""
        assert not _check_method_compatibility("differential_expression", "cox_regression")
        assert not _check_method_compatibility("survival_analysis", "ttest")
        assert not _check_method_compatibility("differential_expression", "spearman")

    def test_pathway_enrichment_unconstrained(self):
        """pathway_enrichment has no hard rules — all methods pass."""
        assert _check_method_compatibility("pathway_enrichment", "any_method")

    def test_unknown_task_unconstrained(self):
        """Unknown tasks should pass (no compatibility rules defined)."""
        assert _check_method_compatibility("unknown_task", "any_method")


class TestTaskDataTypes:
    """Test TASK_DATA_TYPES mapping coverage."""

    def test_all_design_tasks_covered(self):
        """All 6 task types from the design document should be in TASK_DATA_TYPES."""
        expected = {
            "differential_expression", "survival_analysis",
            "immune_correlation", "drug_screening",
            "gene_gene_correlation", "pathway_enrichment",
        }
        assert set(TASK_DATA_TYPES.keys()) == expected

    def test_pathway_enrichment_is_none(self):
        """pathway_enrichment should map to None (LLM judges)."""
        assert TASK_DATA_TYPES["pathway_enrichment"] is None


class TestFrozensetImmutability:
    """All analysis type sets should be immutable."""

    def test_unsupported_realtime_is_frozenset(self):
        assert isinstance(UNSUPPORTED_REALTIME, frozenset)

    def test_supported_realtime_is_frozenset(self):
        assert isinstance(SUPPORTED_REALTIME, frozenset)

    def test_invalid_combinations_is_frozenset(self):
        assert isinstance(INVALID_COMBINATIONS, frozenset)


class TestSampleSizeConstraints:
    """Test sample size constraint lambdas."""

    def test_ttest_n6_passes(self):
        assert SAMPLE_SIZE_CONSTRAINTS["ttest"](6)

    def test_ttest_n5_fails(self):
        assert not SAMPLE_SIZE_CONSTRAINTS["ttest"](5)

    def test_cox_n30_passes(self):
        assert SAMPLE_SIZE_CONSTRAINTS["cox_regression"](30)

    def test_cox_n29_fails(self):
        assert not SAMPLE_SIZE_CONSTRAINTS["cox_regression"](29)

    def test_spearman_n10_passes(self):
        assert SAMPLE_SIZE_CONSTRAINTS["spearman"](10)
