# pipeline.py — AgentOrchestrator: 4-Agent serial pipeline + EvalAgent Protocol
#
# Per design/03-detailed-design.md §三 (MultiAgentPipeline) and §四 (Data Flow).
# Connects LiteratureAgent (S1) → OrchestrationAgent (A2) → AnalysisAgent (A3) → ReportAgent (A4).
# Layer 4 cross-validation nodes #1 and #2 run between phases.
# Task Router adapts for S2 BiomedBenchmark evaluation.

from __future__ import annotations

import logging
import time
from typing import Any

from src.llm.client import LLMClient
from src.agents.literature_agent import LiteratureAgent
from src.agents.orchestration_agent import OrchestrationAgent
from src.agents.analysis_agent import AnalysisAgent
from src.agents.report_agent import ReportAgent
from src.agents.s3_types import (
    AnalysisPlan,
    AnalysisResult,
    PipelineResult,
    ValidationReport,
)
from src.tools.tcga_tools import TCGADataAccessor
from src.utils.network import ensure_network

# S2 EvalAgent Protocol compatibility
try:
    from src.benchmark.types import BenchmarkTask as _BenchmarkTask
except ImportError:
    _BenchmarkTask = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class ValidationBlockedError(Exception):
    """Raised when Layer 4 cross-validation returns BLOCKER."""


class MultiAgentPipeline:
    """4-Agent biomed research pipeline. Implements EvalAgent Protocol.

    Usage (natural language mode):
        pipeline = MultiAgentPipeline(llm_client=client, config=config)
        result: PipelineResult = pipeline.run(
            "CSTB in colorectal cancer prognosis"
        )

    Usage (benchmark mode):
        task = BenchmarkTask(task_id="T3-DEG", ...)
        output: dict = pipeline.run(task)  # returns EvalAgent-compatible dict

    Internal flow:
        Phase 1: LiteratureAgent.run(question) → LiteratureReview
        Phase 2: OrchestrationAgent.plan(review) → AnalysisPlan
        Phase 3: AnalysisAgent.execute(plan) → list[AnalysisResult]
        Phase 4: ReportAgent.generate(review, plan, results) → str
        Layer 4 cross-validation runs between each phase.
    """

    def __init__(
        self, llm_client: LLMClient, config: dict | None = None
    ) -> None:
        self._llm = llm_client
        self._config = config or {}

        # ── Sub-agents ──
        self._literature_agent = LiteratureAgent(llm_client, config)
        self._orchestration_agent = OrchestrationAgent(llm_client, config)
        self._tcga = TCGADataAccessor(
            self._config.get(
                "cache_index_path", "data/cache/analysis_cache_index.json"
            )
        )
        self._analysis_agent = AnalysisAgent(
            llm_client, tools={"tcga": self._tcga}, config=config
        )
        self._report_agent = ReportAgent(llm_client, config)

    @property
    def name(self) -> str:
        """EvalAgent Protocol requirement."""
        return "MultiAgentPipeline"

    # ── Public API ──────────────────────────────────────────

    def run(
        self, question_or_task: str | _BenchmarkTask
    ) -> PipelineResult | dict[str, Any]:
        """Execute the full 4-Agent biomed research pipeline.

        Union signature — consistent with S1 LiteratureAgent.run():
          - str input → returns PipelineResult (natural language mode)
          - BenchmarkTask input → returns dict (EvalAgent Protocol mode)

        Task Router dispatch (BenchmarkTask mode):
          T1-LIT → delegate to S1 LiteratureAgent
          T2-GDA → Phase 1 + simplified Phase 2 (no full DAG)
          T3-DEG/T4-SURV/T5-DRUG → skip Phase 1, task.input drives A2+A3

        Raises:
            ValidationBlockedError: Layer 4 BLOCKER
        """
        # ── EvalAgent Protocol adapter ──
        if _BenchmarkTask is not None and isinstance(question_or_task, _BenchmarkTask):
            return self._run_benchmark(question_or_task)
        else:
            return self._run_question(str(question_or_task))

    # ── Natural language mode ───────────────────────────────

    def _run_question(self, question: str) -> PipelineResult:
        """Full 4-agent pipeline for a natural language question."""
        ensure_network()
        execution_log: list[dict[str, Any]] = []
        layer4_warnings: list[str] = []
        total_tokens = {"input": 0, "output": 0}

        # ── Phase 1: LiteratureAgent ──
        t0 = time.time()
        review = self._literature_agent.run(question)
        execution_log.append({
            "phase": 1, "agent": "LiteratureAgent",
            "duration_s": round(time.time() - t0, 2),
            "papers_retrieved": review.papers_retrieved,
        })
        total_tokens["input"] += review.token_usage.get("input", 0)
        total_tokens["output"] += review.token_usage.get("output", 0)

        # ── Phase 1 post-check: PMID verification (Layer 3 V1) ──
        # Reuse S1 EvidenceSynthesizer._verify_pmids via
        # pipeline.literature_agent._synthesizer.
        # _verify_pmids mutates evidence_chain in-place (strips invalid PMIDs,
        # downgrades to "unverified") and returns the mutated list.
        try:
            synthesizer = self._literature_agent._synthesizer
            if hasattr(synthesizer, '_verify_pmids'):
                before_count = sum(
                    len(link.supporting_pmids) for link in review.evidence_chain
                )
                synthesizer._verify_pmids(
                    review.evidence_chain,
                    {p.pmid for p in review.papers_relevant}
                )
                after_count = sum(
                    len(link.supporting_pmids) for link in review.evidence_chain
                )
                if after_count < before_count:
                    layer4_warnings.append(
                        f"PMID verification: {before_count - after_count} "
                        f"invalid PMID(s) removed from evidence_chain"
                    )
                unverified = sum(
                    1 for link in review.evidence_chain
                    if link.strength == "unverified"
                )
                if unverified > 0:
                    layer4_warnings.append(
                        f"PMID verification: {unverified} claim(s) downgraded "
                        f"to 'unverified' due to missing PMID support"
                    )
        except Exception as e:
            logger.warning("PMID verification skipped: %s", e)

        # ── Layer 4 node #1: A2 validates A1 ──
        v1 = self._orchestration_agent.validate_upstream(review)
        execution_log.append({"phase": "L4-1", "validation": v1.status})
        if v1.status == "BLOCKER":
            raise ValidationBlockedError(
                f"Layer 4 node #1 BLOCKER: {v1.blockers}"
            )
        layer4_warnings.extend(v1.warnings)

        # ── Phase 2: OrchestrationAgent ──
        t0 = time.time()
        plan = self._orchestration_agent.plan(review)
        execution_log.append({
            "phase": 2, "agent": "OrchestrationAgent",
            "duration_s": round(time.time() - t0, 2),
            "n_nodes": len(plan.nodes),
        })

        # ── Layer 4 node #2: A3 validates A2 ──
        v2 = self._analysis_agent.validate_upstream(plan)
        execution_log.append({"phase": "L4-2", "validation": v2.status})
        if v2.status == "BLOCKER":
            raise ValidationBlockedError(
                f"Layer 4 node #2 BLOCKER: {v2.blockers}"
            )
        layer4_warnings.extend(v2.warnings)

        # ── Phase 3: AnalysisAgent ──
        t0 = time.time()
        results = self._analysis_agent.execute(plan)
        execution_log.append({
            "phase": 3, "agent": "AnalysisAgent",
            "duration_s": round(time.time() - t0, 2),
            "n_results": len(results),
            "n_degraded": sum(1 for r in results if r.status == "degraded"),
            "n_failed": sum(1 for r in results if r.status == "failed"),
        })

        # ── Layer 4 node #3: A4 validates A3 ──
        v3 = self._report_agent.validate_upstream(results)
        execution_log.append({"phase": "L4-3", "validation": v3.status})
        if v3.status == "BLOCKER":
            raise ValidationBlockedError(
                f"Layer 4 node #3 BLOCKER: {v3.blockers}"
            )
        layer4_warnings.extend(v3.warnings)

        # ── Phase 4: ReportAgent ──
        t0 = time.time()
        report = self._report_agent.generate(review, plan, results)
        execution_log.append({
            "phase": 4, "agent": "ReportAgent",
            "duration_s": round(time.time() - t0, 2),
            "report_length_chars": len(report),
        })

        total_tokens["total"] = total_tokens["input"] + total_tokens["output"]

        # ── Node coverage check (deferred from ReportAgent.validate_upstream) ──
        # The report is only available after Phase 4, so coverage is checked here.
        reported_nodes = {
            node.node_id for node in plan.nodes
            if node.node_id in report
        }
        uncovered = [
            r.node_id for r in results
            if r.node_id not in reported_nodes
        ]
        if uncovered:
            layer4_warnings.append(
                f"Node coverage: {len(uncovered)}/{len(results)} nodes "
                f"not mentioned in report: {uncovered}"
            )
        execution_log.append({
            "phase": "L4-coverage",
            "covered": len(reported_nodes),
            "total": len(results),
        })

        return PipelineResult(
            question=question,
            literature_review=review,
            analysis_plan=plan,
            analysis_results=results,
            report=report,
            total_tokens=total_tokens,
            execution_log=execution_log,
            layer4_warnings=layer4_warnings,
        )

    # ── Benchmark mode (EvalAgent Protocol) ──────────────────

    def _run_benchmark(self, task: _BenchmarkTask) -> dict[str, Any]:
        """Task Router: delegate benchmark task to appropriate agent(s).

        T1-LIT → delegate to S1 LiteratureAgent (full EvalAgent Protocol)
        T2-GDA → Phase 1 + simplified Phase 2 (no full DAG)
        T3-DEG/T4-SURV/T5-DRUG → skip Phase 1, task.input drives A2+A3
        """
        task_id = task.task_id

        if task_id == "T1-LIT":
            # Delegate entirely to S1
            return self._literature_agent.run(task)

        elif task_id == "T2-GDA":
            # Phase 1 + simplified association assessment
            question = task.input.get("question", task.description)
            review = self._literature_agent.run(question)
            # Simplified: just return literature evidence for association
            return {
                "answer": review.evidence_summary,
                "association_judgment": "see evidence_summary",
                "evidence": [
                    {"claim": link.claim, "strength": link.strength}
                    for link in review.evidence_chain
                ],
                "retrieved_pmids": [
                    p.pmid for p in review.papers_relevant
                ],
                "token_usage": review.token_usage,
                "confidence": review.confidence,
            }

        elif task_id in ("T3-DEG", "T4-SURV", "T5-DRUG"):
            # Skip Phase 1 — use task.input directly for A2+A3
            plan = self._orchestration_agent.plan_from_task(task)
            results = self._analysis_agent.execute(plan)
            return self._format_as_analysis_output(task_id, results)

        else:
            raise ValueError(
                f"Task Router: unknown task_id '{task_id}'"
            )

    # ── Output formatters ───────────────────────────────────

    @staticmethod
    def _format_as_analysis_output(
        task_id: str, results: list[AnalysisResult]
    ) -> dict[str, Any]:
        """Format AnalysisResults as EvalAgent Protocol dict."""
        if not results:
            return {"error": "No analysis results produced"}

        r = results[0]  # Single-node tasks (T3-T5)

        if task_id == "T3-DEG":
            return {
                "differentially_expressed_genes": r.output.get("gene"),
                "logFC": r.output.get("log2FC"),
                "p_value": r.output.get("p_value"),
                "p_adj": r.output.get("p_adj"),
                "method": r.method,
                "status": r.status,
            }
        elif task_id == "T4-SURV":
            return {
                "hazard_ratios": {r.output.get("gene", ""): r.output.get("HR")},
                "cox_p_value": r.output.get("p_value"),
                "ph_violation": r.output.get("ph_violation", False),
                "method": r.method,
                "status": r.status,
            }
        elif task_id == "T5-DRUG":
            return {
                "drug_correlations": r.output.get("top_drugs", []),
                "n_significant": r.output.get("n_significant", 0),
                "fdr_threshold": r.output.get("fdr_threshold", 0.05),
                "method": r.method,
                "status": r.status,
            }
        else:
            return {"output": r.output, "method": r.method, "status": r.status}
