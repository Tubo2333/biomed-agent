"""Tests for Step 1 RAG modules (structural — full run needs LLM + PubMed)."""

import pytest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.types import Paper, SearchQuery, SearchResult, EvidenceLink, Hypothesis
from src.rag.embedder import Embedder, LLMRerank
from src.rag.synthesizer import EvidenceSynthesizer
from src.rag.hypothesis_generator import HypothesisGenerator
from src.tools.pubmed_tools import ToolDef, create_pubmed_tools, get_pubmed_tool_schemas
from src.utils.network import check_proxy, NetworkError
from src.llm.client import LLMClient, LLMResponse


class TestToolDef:
    def test_tool_def_creation(self):
        td = ToolDef(
            name="test_tool", description="test",
            parameters={"type": "object", "properties": {}},
            execute=lambda x: x, risk="low", requires_approval=False,
        )
        assert td.name == "test_tool"
        assert td.risk == "low"

    def test_to_openai_schema(self):
        td = ToolDef(
            name="search", description="Search PubMed",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            execute=lambda x: x, risk="low", requires_approval=False,
        )
        schema = td.to_openai_schema()
        assert schema["name"] == "search"
        assert "input_schema" in schema

    def test_create_pubmed_tools(self):
        from src.rag.retriever import PubMedRetriever
        retriever = PubMedRetriever(cache_dir="data/pubmed_cache_test")
        tools = create_pubmed_tools(retriever)
        assert len(tools) == 1
        assert tools[0].name == "pubmed_search"

    def test_get_pubmed_tool_schemas(self):
        td = ToolDef(
            name="t", description="d",
            parameters={"type": "object", "properties": {}},
            execute=lambda x: x, risk="low", requires_approval=False,
        )
        schemas = get_pubmed_tool_schemas([td])
        assert len(schemas) == 1
        assert "name" in schemas[0]


class TestLLMRerank:
    """LLMRerank structural test — no LLM needed."""

    def test_reranker_class_exists(self):
        client = LLMClient(model="test", temperature=0.3)
        reranker = LLMRerank(client, batch_size=5)
        assert reranker.name == "LLMRerank"
        assert isinstance(reranker, Embedder)


class TestSynthesizer:
    """EvidenceSynthesizer structural test."""

    def test_synthesizer_exists(self):
        client = LLMClient(model="test", temperature=0.3)
        synth = EvidenceSynthesizer(client)
        assert hasattr(synth, "synthesize")


class TestHypothesisGenerator:
    """HypothesisGenerator structural test."""

    def test_generator_exists(self):
        client = LLMClient(model="test", temperature=0.3)
        gen = HypothesisGenerator(client)
        assert hasattr(gen, "generate")


class TestNetwork:
    """Network utilities — don't require actual proxy."""

    def test_check_proxy_returns_bool(self):
        result = check_proxy()
        assert isinstance(result, bool)
