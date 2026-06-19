"""Tests for Step 1 shared types (Paper, LiteratureReview, EvidenceLink, Hypothesis)."""

import pytest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.types import (
    Paper, LiteratureReview, EvidenceLink, Hypothesis,
    make_evidence_link, make_hypothesis,
    degradation_evidence_link, degradation_hypothesis,
)


class TestPaper:
    def test_valid_paper(self):
        p = Paper(
            pmid="12345678", title="Test", abstract="Abstract",
            authors=["Smith J"], journal="Nature", year=2023,
        )
        assert p.pmid == "12345678"

    def test_empty_pmid_raises(self):
        with pytest.raises(ValueError):
            Paper(pmid="", title="T", abstract="A", authors=["S"], journal="J", year=2023)

    def test_year_out_of_range_raises(self):
        with pytest.raises(ValueError):
            Paper(pmid="1", title="T", abstract="A", authors=["S"], journal="J", year=1800)

    def test_relevance_score_out_of_range_raises(self):
        with pytest.raises(ValueError):
            Paper(pmid="1", title="T", abstract="A", authors=["S"], journal="J", year=2023, relevance_score=2.0)


class TestEvidenceLink:
    def test_valid_strong(self):
        link = EvidenceLink(
            claim="CSTB is overexpressed in CRC",
            supporting_pmids=["12345678", "23456789", "34567890"],
            strength="strong",
            strength_justification="3 independent cohorts, n>2000",
        )
        assert link.strength == "strong"

    def test_strong_without_pmids_raises(self):
        with pytest.raises(ValueError):
            EvidenceLink(
                claim="X", supporting_pmids=[],
                strength="strong", strength_justification="test",
            )

    def test_strong_with_counter_evidence_raises(self):
        with pytest.raises(ValueError):
            EvidenceLink(
                claim="X", supporting_pmids=["1"],
                strength="strong", strength_justification="test",
                counter_evidence="conflicting study exists",
            )

    def test_unverified_is_valid(self):
        link = EvidenceLink(
            claim="Unverified claim",
            supporting_pmids=[],
            strength="unverified",
            strength_justification="No supporting evidence found",
        )
        assert link.strength == "unverified"

    def test_make_evidence_link_factory(self):
        link = make_evidence_link({
            "claim": "Test", "supporting_pmids": ["1"],
            "strength": "moderate", "strength_justification": "ok",
        })
        assert link is not None
        assert link.claim == "Test"

    def test_make_evidence_link_returns_none_on_invalid(self):
        link = make_evidence_link({
            "claim": "X", "supporting_pmids": [],
            "strength": "strong", "strength_justification": "test",
        })
        assert link is None


class TestHypothesis:
    def test_valid_hypothesis(self):
        h = Hypothesis(
            statement="CSTB mediates immune evasion",
            rationale="Based on evidence from PMID:1",
            testable_prediction="CSTB KD reduces M2 markers",
            required_data=["CRC cell lines"],
            novelty="novel_to_our_knowledge",
            novelty_justification="No paper tests mechanism",
        )
        assert h.statement

    def test_empty_required_data_raises(self):
        with pytest.raises(ValueError):
            Hypothesis(
                statement="X", rationale="R", testable_prediction="T",
                required_data=[], novelty="novel_to_our_knowledge",
                novelty_justification="J",
            )

    def test_make_hypothesis_factory(self):
        h = make_hypothesis({
            "statement": "X", "rationale": "R", "testable_prediction": "T",
            "required_data": ["D"], "novelty": "novel_to_our_knowledge",
            "novelty_justification": "J",
        })
        assert h is not None

    def test_make_hypothesis_none_on_invalid(self):
        h = make_hypothesis({
            "statement": "X", "rationale": "R", "testable_prediction": "",
            "required_data": [], "novelty": "novel_to_our_knowledge",
            "novelty_justification": "J",
        })
        assert h is None


class TestLiteratureReview:
    def test_valid_review(self):
        link = EvidenceLink(
            claim="CSTB associated with poor prognosis",
            supporting_pmids=["1"], strength="moderate",
            strength_justification="one study, n=300",
        )
        hyp = Hypothesis(
            statement="CSTB is a prognostic biomarker",
            rationale="From evidence chain", testable_prediction="CSTB correlates with OS",
            required_data=["survival data"], novelty="novel_to_our_knowledge",
            novelty_justification="Not proposed in retrieved papers",
        )
        review = LiteratureReview(
            query="CSTB in CRC", papers_retrieved=10,
            papers_relevant=[], evidence_summary="Summary",
            evidence_chain=[link], hypotheses=[hyp],
            confidence=0.7, knowledge_gaps=["gap1"],
            citations=["[PMID:1] Smith et al."],
            token_usage={"input": 100, "output": 50},
        )
        assert review.confidence == 0.7

    def test_empty_evidence_chain_raises(self):
        with pytest.raises(ValueError):
            LiteratureReview(
                query="Q", papers_retrieved=0, papers_relevant=[],
                evidence_summary="S", evidence_chain=[],
                hypotheses=[], confidence=0.5,
                knowledge_gaps=[], citations=[], token_usage={},
            )


class TestDegradation:
    def test_degradation_produces_valid_objects(self):
        link = degradation_evidence_link()
        assert link.strength == "unverified"
        assert "LLM_UNAVAILABLE" in link.claim

        hyp = degradation_hypothesis()
        assert hyp.novelty == "supported_by_existing"
        assert "LLM_UNAVAILABLE" in hyp.statement
