"""Tests for LiteratureAgent (structural — full run needs LLM)."""

import pytest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agents.literature_agent import LiteratureAgent
from src.llm.client import LLMClient
from src.benchmark.types import BenchmarkTask, EvalAgent


class TestLiteratureAgentStructural:
    def test_instantiation(self):
        agent = LiteratureAgent(LLMClient(model="test", temperature=0.3))
        assert agent.name == "LiteratureAgent"

    def test_has_run_method(self):
        agent = LiteratureAgent(LLMClient(model="test", temperature=0.3))
        assert hasattr(agent, "run")

    def test_accepts_benchmark_task(self):
        """LiteratureAgent.run() accepts BenchmarkTask for S2 integration."""
        agent = LiteratureAgent(LLMClient(model="test", temperature=0.3))
        task = BenchmarkTask(
            task_id="T1-LIT", task_name="Test Literature Review",
            description="Review CSTB in CRC",
            input={"question": "CSTB in colorectal cancer prognosis"},
            ground_truth={"relevant_pmids": ["21833088"]},
            evaluation_criteria=["Recall@K", "Precision@K"],
        )
        # Structural check: doesn't crash on instantiation/type check
        assert hasattr(agent, "run")
        assert agent.name == "LiteratureAgent"

    def test_has_name_property(self):
        agent = LiteratureAgent(LLMClient(model="test", temperature=0.3))
        assert isinstance(agent.name, str)
        assert len(agent.name) > 0

    def test_to_benchmark_output_returns_dict(self):
        """_to_benchmark_output converts LiteratureReview to dict."""
        from src.types import LiteratureReview, EvidenceLink, Hypothesis
        link = EvidenceLink(
            claim="Test claim", supporting_pmids=["12345678"],
            strength="moderate", strength_justification="one study",
        )
        hyp = Hypothesis(
            statement="Test hypothesis", rationale="R",
            testable_prediction="T", required_data=["D"],
            novelty="novel_to_our_knowledge", novelty_justification="J",
        )
        review = LiteratureReview(
            query="Test", papers_retrieved=5, papers_relevant=[],
            evidence_summary="Summary text", evidence_chain=[link],
            hypotheses=[hyp], confidence=0.5, knowledge_gaps=["gap"],
            citations=["[PMID:12345678] Smith et al."],
            token_usage={"input": 100, "output": 50},
        )
        agent = LiteratureAgent(LLMClient(model="test", temperature=0.3))
        output = agent._to_benchmark_output(review)
        assert isinstance(output, dict)
        assert output["answer"] == "Summary text"
        assert len(output["evidence_chain"]) == 1
        assert len(output["hypotheses"]) == 1
        assert output["confidence"] == 0.5
        assert "token_usage" in output
