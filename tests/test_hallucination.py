"""Tests for hallucination detection (V1/V2/V3 + P0-4 validation)."""

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from benchmark.hallucination import (
    detect, validate_detector, _extract_pmids, _verify_genes,
    _check_statistics, METHODS_WHITELIST,
    _NON_GENE_ACRONYMS,
)
from benchmark.types import BenchmarkTask


def _make_task(**kwargs):
    return BenchmarkTask(
        task_id="T1-LIT", task_name="t", description="t",
        input={"gene": "CSTB"},
        ground_truth=kwargs.get("ground_truth", {"gene": "CSTB"}),
        evaluation_criteria=["test"],
    )


class TestPMIDExtraction:
    """V1: PMID extraction from 3 common formats."""

    def test_format_pmid_colon(self):
        pmids = _extract_pmids("See PMID: 12345678 for details.")
        assert "12345678" in pmids

    def test_format_bracket(self):
        pmids = _extract_pmids("Evidence from [PMID:12345678].")
        assert "12345678" in pmids

    def test_format_pubmed_id(self):
        pmids = _extract_pmids("PubMed ID: 12345678")
        assert "12345678" in pmids

    def test_no_false_positive(self):
        pmids = _extract_pmids("No references here.")
        assert pmids == []


class TestV1PMIDCheck:
    """V1: PMID existence verification."""

    def test_retrieved_pmid_passes(self):
        report = detect(
            "Result: CSTB is significant [PMID:12345678].",
            _make_task(), retrieved_pmids={"12345678"},
        )
        hard = [f for f in report.hard_rule_flags if f.get("hallucination")]
        assert len(hard) == 0

    def test_unretrieved_pmid_flagged(self):
        report = detect(
            "Result: CSTB is significant [PMID:99999999].",
            _make_task(), retrieved_pmids={"12345678"},
        )
        hard = [f for f in report.hard_rule_flags if f.get("hallucination")]
        assert len(hard) >= 1

    def test_whitelist_pmid_passes(self):
        """Methodology citations in whitelist should not be flagged as hallucination."""
        whitelist_pmid = list(METHODS_WHITELIST.keys())[0]
        report = detect(
            f"We used the method from [PMID:{whitelist_pmid}].",
            _make_task(), retrieved_pmids=set(),
        )
        hard = [f for f in report.hard_rule_flags if f.get("hallucination")]
        assert len(hard) == 0


class TestV2GeneCheck:
    """V2: Gene name verification (warning-only)."""

    def test_known_gene_passes(self):
        flags = _verify_genes("CSTB is overexpressed.", {"CSTB"})
        assert len(flags) == 0

    def test_unknown_gene_warns(self):
        flags = _verify_genes("ZBTB99 is a novel biomarker.", {"CSTB"})
        assert len(flags) >= 1
        assert flags[0]["hallucination"] is False  # V2 is warning-only

    def test_acronym_filtered(self):
        """Non-gene acronyms (e.g., TCGA, DNA) should be filtered."""
        flags = _verify_genes("TCGA data shows DNA and RNA levels.", {"CSTB"})
        # TCGA, DNA, RNA are in _NON_GENE_ACRONYMS
        assert all(f["gene_symbol"] not in _NON_GENE_ACRONYMS for f in flags)

    def test_real_gene_symbols_not_filtered(self):
        """Real gene symbols must not be in _NON_GENE_ACRONYMS."""
        # WT1 is a real gene (Wilms tumor 1) — verify it's NOT in the exclusion set
        assert "WT1" not in _NON_GENE_ACRONYMS


class TestV3StatSanity:
    """V3: Statistic sanity bounds."""

    def test_realistic_hr_passes(self):
        flags = _check_statistics("HR = 2.3 (95% CI 1.5-3.2)")
        hard = [f for f in flags if f.get("hallucination")]
        assert len(hard) == 0

    def test_impossible_hr_flagged(self):
        flags = _check_statistics("HR = 500.0")
        hard = [f for f in flags if f.get("hallucination")]
        assert len(hard) >= 1

    def test_negative_p_flagged(self):
        flags = _check_statistics("p = -0.05")
        hard = [f for f in flags if f.get("hallucination")]
        assert len(hard) >= 1

    def test_valid_p_value_passes(self):
        flags = _check_statistics("p = 0.003")
        hard = [f for f in flags if f.get("hallucination")]
        assert len(hard) == 0


class TestP04Validation:
    """P0-4: Detector self-test with known-true/fake items."""

    def test_validate_detector_passes(self):
        result = validate_detector()
        assert result["passed"] is True
        assert result["recall"] >= 0.8
        assert result["precision"] >= 0.9

    def test_validate_detector_has_details(self):
        result = validate_detector()
        assert "details" in result
        assert len(result["details"]) > 0


class TestMethodClaimVerification:
    """Anti-exploitation measure #2: method claims vs actual tool usage."""

    def test_matching_tool_no_flag(self):
        report = detect(
            "Used limma [PMID:25605792].",
            _make_task(), set(), {"CSTB"},
            tools_used=["limma_voom", "run_differential_expression"],
        )
        mismatches = [
            f for f in report.hard_rule_flags
            if f.get("method_verified") is False
        ]
        assert len(mismatches) == 0

    def test_mismatched_tool_detected(self):
        report = detect(
            "Used limma [PMID:25605792].",
            _make_task(), set(), {"CSTB"},
            tools_used=["run_survival_analysis"],
        )
        mismatches = [
            f for f in report.hard_rule_flags
            if f.get("method_verified") is False
        ]
        assert len(mismatches) == 1
        assert "not matched" in mismatches[0]["note"]


class TestWhitelistIntegrity:
    """Methods whitelist requirements."""

    def test_whitelist_size(self):
        assert len(METHODS_WHITELIST) >= 24

    def test_whitelist_pmids_are_strings(self):
        for pmid in METHODS_WHITELIST:
            assert isinstance(pmid, str)
            assert pmid.isdigit(), f"PMID {pmid} is not numeric"
