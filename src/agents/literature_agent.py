# literature_agent.py — LiteratureAgent: Think→Act→Observe 多轮文献检索与证据整合
#
# Step 1 的核心编排模块。组合 Retriever + Embedder + Synthesizer + HypothesisGenerator，
# 实现完整的多轮文献调研 Agent 循环。

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from src.llm.client import LLMClient, LLMError
from src.rag.retriever import PubMedRetriever
from src.rag.embedder import LLMRerank
from src.rag.synthesizer import EvidenceSynthesizer
from src.rag.hypothesis_generator import HypothesisGenerator
from src.agents.question_decomposer import decompose_question
from src.tools.pubmed_tools import (
    ToolDef,
    create_pubmed_tools,
    get_pubmed_tool_schemas,
)
from src.types import (
    LiteratureReview,
    Paper,
    RetrievalGate,
    SearchQuery,
    SearchResult,
    degradation_evidence_link,
    degradation_hypothesis,
)
from src.utils.network import ensure_network

# S2 EvalAgent Protocol compatibility — optional import
try:
    from src.benchmark.types import BenchmarkTask as _BenchmarkTask
except ImportError:
    _BenchmarkTask = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# Prompts
# ═══════════════════════════════════════════════════════════════

_AGENT_THINK_SYSTEM = """You are a biomedical literature analyst conducting a systematic review.
You are in the THINK phase of a multi-round literature search process.

Your task is to review the evidence collected so far and decide:
1. Is the evidence sufficient to synthesize a reliable answer?
2. If NOT sufficient — what specific gap exists, and what new search would fill it?
3. If sufficient — say "SUFFICIENT" and prepare to synthesize.

When judging sufficiency, consider:
- Do we have evidence on ALL dimensions of the original question?
- For each dimension, do we have at least 2 independent studies?
- Are there blatant contradictions that need resolution?
- Is there a major dimension completely unaddressed?

## CRITICAL CONSTRAINTS (MUST FOLLOW)

1. **No Fabrication**: Do NOT fabricate anything not in the evidence.
2. **Source Attribution**: Base all reasoning on the provided evidence summary.
3. **Uncertainty Expression**: Explicitly state when evidence is insufficient.
4. **Quantitative Precision**: Cite exact numbers where available.
5. **Negative Results**: Report missing dimensions clearly.

## OUTPUT FORMAT (JSON object ONLY)
{
  "decision": "CONTINUE",
  "reasoning": "Detailed reasoning about evidence status...",
  "gap_description": "What specific gap exists and why a new search is needed",
  "new_search_query": "PubMed-ready search string for the gap",
  "confidence_in_decision": 0.8
}

If sufficient, set decision="SUFFICIENT", gap_description=null, new_search_query=null."""

_TOKEN_BUDGET = 15000
_MAX_ROUNDS = 3


# ═══════════════════════════════════════════════════════════════
# LiteratureAgent
# ═══════════════════════════════════════════════════════════════


class LiteratureAgent:
    """Think→Act→Observe 多轮文献检索与证据整合 Agent。

    Usage:
        client = LLMClient()
        agent = LiteratureAgent(llm_client=client, config={})
        review: LiteratureReview = agent.run(
            "CSTB in colorectal cancer prognosis"
        )
    """

    def __init__(self, llm_client: LLMClient, config: dict | None = None) -> None:
        self._llm = llm_client
        self._config = config or {}

        # ── 子模块 ──
        self._retriever = PubMedRetriever(
            cache_dir=self._config.get("pubmed_cache_dir", "data/pubmed_cache")
        )
        self._reranker = LLMRerank(llm_client, batch_size=10)
        self._synthesizer = EvidenceSynthesizer(llm_client)
        self._hypothesis_gen = HypothesisGenerator(llm_client)
        self._pubmed_tools = create_pubmed_tools(self._retriever)

        # ── 运行状态（每次 run() 重置）──
        self._round: int = 0
        self._total_tokens: dict[str, int] = {"input": 0, "output": 0}
        self._all_papers: list[Paper] = []
        self._previous_queries: list[str] = []
        self._retrieval_log: list[dict] = []

    @property
    def name(self) -> str:
        return "LiteratureAgent"

    # ── Public API ──────────────────────────────────────────

    def run(
        self, question_or_task: str | _BenchmarkTask
    ) -> LiteratureReview | dict[str, Any]:
        """Execute the full literature review pipeline.

        Accepts either a plain question string or a BenchmarkTask (from Step 2).
        When given a BenchmarkTask, extracts the question from task.input and
        returns a dict compatible with EvalAgent Protocol.

        1. 分解问题 / Decompose question → 生成初始搜索
        2. Think→Act→Observe 多轮循环 (max 3 rounds)
        3. 证据整合 / Evidence synthesis
        4. 假设生成 / Hypothesis generation
        5. 返回 LiteratureReview (str) or dict (BenchmarkTask)
        """
        # ── EvalAgent Protocol adapter ──
        if _BenchmarkTask is not None and isinstance(question_or_task, _BenchmarkTask):
            task = question_or_task
            question = task.input.get("question", task.description)
            review = self._run_question(question)
            return self._to_benchmark_output(review)
        else:
            return self._run_question(str(question_or_task))

    def _run_question(self, question: str) -> LiteratureReview:
        """Core pipeline: str question → LiteratureReview."""
        self._reset()
        ensure_network()

        # ── Phase 0: 问题分解 ──
        search_queries = decompose_question(self._llm, question)

        # ── Phase 1: 多轮检索循环 ──
        for self._round in range(1, _MAX_ROUNDS + 1):
            # Think
            gate = self._think(question)
            if gate is None and self._round > 1:
                # First round: no think needed, just execute initial queries
                pass
            elif gate is not None and not gate.should_continue:
                logger.info(
                    "Retrieval stopped at round %d: %s",
                    self._round,
                    gate.reason,
                )
                break

            # Act
            queries_this_round = (
                search_queries if self._round == 1
                else [SearchQuery(gate.new_query)] if gate and gate.new_query
                else []
            )
            if not queries_this_round:
                break

            for sq in queries_this_round:
                try:
                    result: SearchResult = self._retriever.search(
                        sq, retrieval_round=self._round
                    )
                except Exception as e:
                    logger.error("PubMed search failed: %s", e)
                    continue

                if result.papers:
                    self._previous_queries.append(sq.query_string)

                    # Observe: Rerank
                    reranked = self._reranker.rank(
                        question, result.papers, top_k=10
                    )
                    self._total_tokens["input"] += reranked.token_used // 2
                    self._total_tokens["output"] += reranked.token_used // 2

                    for p in reranked.papers:
                        if p.pmid not in {ep.pmid for ep in self._all_papers}:
                            self._all_papers.append(p)

                    self._retrieval_log.append(
                        {
                            "round": self._round,
                            "query": sq.query_string,
                            "papers_found": len(result.papers),
                            "papers_kept": len(reranked.papers),
                        }
                    )

            # Token budget check
            if self._total_tokens["input"] + self._total_tokens["output"] >= _TOKEN_BUDGET:
                logger.info("Token budget exhausted at round %d", self._round)
                break

        # ── Phase 2: 证据整合 ──
        if self._all_papers:
            chain, summary, confidence, gaps, citations = (
                self._synthesizer.synthesize(self._all_papers, question)
            )
        else:
            chain = [degradation_evidence_link()]
            summary = "No papers retrieved — evidence synthesis skipped."
            confidence = 0.0
            gaps = ["No papers retrieved from PubMed"]
            citations = []

        # ── Phase 3: 假设生成 ──
        if chain and chain[0].strength != "unverified":
            hypotheses = self._hypothesis_gen.generate(chain, gaps, question)
        else:
            hypotheses = [degradation_hypothesis()]

        # ── Phase 4: 组装 ──
        papers_relevant = [
            p for p in self._all_papers
            if p.relevance_score is not None and p.relevance_score >= 0.4
        ]
        if not papers_relevant:
            papers_relevant = self._all_papers[:10]

        return LiteratureReview(
            query=question,
            papers_retrieved=len(self._all_papers),
            papers_relevant=papers_relevant,
            evidence_summary=summary,
            evidence_chain=chain,
            hypotheses=hypotheses,
            confidence=confidence,
            knowledge_gaps=gaps,
            citations=citations,
            token_usage=self._total_tokens,
        )

    # ── Phase 1: Think ──────────────────────────────────────

    def _think(self, question: str) -> RetrievalGate | None:
        """LLM 审查证据并决定是否继续检索。"""
        # Build evidence summary for the Think prompt
        evidence_brief = self._build_evidence_brief()

        try:
            response = self._llm.chat(
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Original question: {question}\n\n"
                            f"Round {self._round} of {_MAX_ROUNDS}.\n\n"
                            f"Evidence collected so far ({len(self._all_papers)} papers "
                            f"across {self._round - 1} rounds):\n\n"
                            f"{evidence_brief}\n\n"
                            f"Search queries already executed:\n"
                            f"{json.dumps(self._previous_queries, ensure_ascii=False)}\n\n"
                            f"Should we continue to another search round, "
                            f"or is the evidence sufficient?"
                        ),
                    }
                ],
                system=_AGENT_THINK_SYSTEM,
                max_tokens=6000, thinking_budget_tokens=1500,
            )
            self._track_tokens(response.input_tokens, response.output_tokens)
            data = self._parse_json_response(response.content)

            decision = data.get("decision", "SUFFICIENT")
            new_query = data.get("new_search_query")

            # ── Gate 1: hard max rounds ──
            if self._round >= _MAX_ROUNDS:
                return RetrievalGate(
                    should_continue=False,
                    reason=f"Max rounds ({_MAX_ROUNDS}) reached",
                    new_query=None,
                    rounds_used=self._round,
                    token_used_so_far=self._total_tokens["input"]
                    + self._total_tokens["output"],
                )

            # ── Gate 2: query dedup ──
            if new_query and self._is_duplicate_query(new_query):
                return RetrievalGate(
                    should_continue=False,
                    reason="New query is semantically duplicate of a previous query",
                    new_query=None,
                    rounds_used=self._round,
                    token_used_so_far=self._total_tokens["input"]
                    + self._total_tokens["output"],
                )

            # ── Gate 3: token budget ──
            cumulative = self._total_tokens["input"] + self._total_tokens["output"]
            if cumulative >= _TOKEN_BUDGET:
                return RetrievalGate(
                    should_continue=False,
                    reason=f"Token budget ({_TOKEN_BUDGET}) exhausted",
                    new_query=None,
                    rounds_used=self._round,
                    token_used_so_far=cumulative,
                )

            return RetrievalGate(
                should_continue=(decision == "CONTINUE" and new_query is not None),
                reason=(
                    "LLM determined evidence is sufficient"
                    if decision == "SUFFICIENT"
                    else f"LLM wants to search: {data.get('gap_description', '')}"
                ),
                new_query=new_query if decision == "CONTINUE" else None,
                rounds_used=self._round,
                token_used_so_far=cumulative,
            )

        except (LLMError, json.JSONDecodeError, ValueError) as e:
            logger.warning("Think phase failed in round %d: %s", self._round, e)
            # Round 1: Think 失败不阻止初始检索 — Phase 0 的分解查询仍有质量保证
            # Round 2+: 无法迭代优化，保守停止
            if self._round == 1:
                return RetrievalGate(
                    should_continue=True,
                    reason=f"Think LLM call failed in round 1, executing Phase 0 queries. Error: {e}",
                    new_query=None,  # 使用 Phase 0 的原始查询
                    rounds_used=self._round,
                    token_used_so_far=self._total_tokens["input"]
                    + self._total_tokens["output"],
                )
            else:
                return RetrievalGate(
                    should_continue=False,
                    reason=f"Think LLM call failed in round {self._round}: {e}",
                    new_query=None,
                    rounds_used=self._round,
                    token_used_so_far=self._total_tokens["input"]
                    + self._total_tokens["output"],
                )

    # ── Gate helpers ────────────────────────────────────────

    def _is_duplicate_query(self, new_query: str) -> bool:
        """Gate 2: 用 LLM 判定新查询是否和已有查询语义重复。"""
        if not self._previous_queries:
            return False
        try:
            response = self._llm.chat(
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"New query: {new_query}\n\n"
                            f"Previous queries: {json.dumps(self._previous_queries)}\n\n"
                            f"Are these two search queries looking for essentially "
                            f"the same information? Answer ONLY 'yes' or 'no'."
                        ),
                    }
                ],
                max_tokens=500, thinking_budget_tokens=None,
            )
            self._track_tokens(response.input_tokens, response.output_tokens)
            return response.content.strip().lower().startswith("yes")
        except LLMError:
            return False  # 保守：网络问题时允许继续

    def _build_evidence_brief(self) -> str:
        """为 Think prompt 构建证据摘要。"""
        if not self._all_papers:
            return "No papers collected yet."
        briefs = []
        for p in self._all_papers[:15]:
            score = (
                f"score={p.relevance_score:.1f}"
                if p.relevance_score is not None
                else "unranked"
            )
            briefs.append(
                f"PMID:{p.pmid} [{score}] {p.title[:100]} ({p.journal}, {p.year})"
            )
        return "\n".join(briefs)

    # ── Token tracking ──────────────────────────────────────

    def _track_tokens(self, input_t: int, output_t: int) -> None:
        self._total_tokens["input"] += input_t
        self._total_tokens["output"] += output_t

    def _reset(self) -> None:
        self._round = 0
        self._total_tokens = {"input": 0, "output": 0}
        self._all_papers = []
        self._previous_queries = []
        self._retrieval_log = []

    # ── Tool ────────────────────────────────────────────────

    @staticmethod
    def _parse_json_response(text: str) -> dict:
        """解析 LLM JSON 输出，容忍多余文字。"""
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            for bracket in [("[", "]"), ("{", "}")]:
                start = text.find(bracket[0])
                end = text.rfind(bracket[1])
                if start != -1 and end != -1 and end > start:
                    try:
                        return json.loads(text[start : end + 1])
                    except json.JSONDecodeError:
                        continue
            raise

    # ── EvalAgent Protocol adapter ────────────────────────────

    def _to_benchmark_output(self, review: LiteratureReview) -> dict[str, Any]:
        """Convert LiteratureReview to EvalAgent Protocol-compatible dict."""
        import dataclasses

        return {
            "answer": review.evidence_summary,
            "output": review.evidence_summary,
            "evidence_chain": [
                dataclasses.asdict(link) for link in review.evidence_chain
            ],
            "hypotheses": [
                dataclasses.asdict(h) for h in review.hypotheses
            ],
            "tools_used": [
                "pubmed_search",
                "evidence_synthesis",
                "hypothesis_generation",
            ],
            "retrieved_pmids": [
                p.pmid for p in review.papers_relevant
            ],
            "token_usage": review.token_usage,
            "confidence": review.confidence,
            "knowledge_gaps": review.knowledge_gaps,
        }
