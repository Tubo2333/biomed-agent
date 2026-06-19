# orchestration_agent.py — A2: LLM-driven dynamic DAG generation
#
# Per design/03-detailed-design.md §三 (OrchestrationAgent) and §五 Prompt 1.
# Consumes LiteratureReview from A1 → produces AnalysisPlan.
# Layer 4 cross-validation node #1: validate_upstream(A1 output).
#
# Anti-template mechanism:
#   - Prompt requires hypothesis classification (single_gene / pathway / multi_gene)
#   - Each node MUST include a "rationale" field (enforced by AnalysisNode.__post_init__)
#   - Method compatibility matrix post-processing catches invalid method assignments

from __future__ import annotations

import json
import logging
from typing import Any

from src.llm.client import LLMClient, LLMError
from src.types import LiteratureReview, Hypothesis
from src.agents.s3_prompts import ORCHESTRATION_PLAN_SYSTEM
from src.agents.s3_types import (
    AnalysisNode,
    AnalysisPlan,
    ValidationReport,
)
from src.tools.tcga_tools import (
    METHOD_COMPATIBILITY,
    SAMPLE_SIZE_CONSTRAINTS,
    INVALID_COMBINATIONS,
    TASK_DATA_TYPES,
    _check_method_compatibility,
)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# Prompt: Orchestration Plan (design §五 Prompt 1)
# ═══════════════════════════════════════════════════════════════


class OrchestrationAgent:
    """LLM-driven dynamic DAG generation (A2).

    Usage:
        orch = OrchestrationAgent(llm_client=client, config=config)
        plan: AnalysisPlan = orch.plan(literature_review)
    """

    def __init__(
        self, llm_client: LLMClient, config: dict | None = None
    ) -> None:
        self._llm = llm_client
        self._config = config or {}
        self._max_plan_retries = 2
        # Logical → relative data path mapping (configurable via config dict)
        self._data_paths = {
            "tcga_coad": "data/cache/",
            "gdsc2": "data/cache/",
            **self._config.get("data_paths", {}),
        }

    def _resolve_data_path(self, dataset: str) -> str:
        """Resolve a logical dataset name to a relative data path."""
        return self._data_paths.get(dataset, f"data/{dataset}/")

    # ── Public API ──────────────────────────────────────────

    def plan(self, review: LiteratureReview) -> AnalysisPlan:
        """Generate an AnalysisPlan from a LiteratureReview.

        Steps:
          1. Extract testable predictions from hypotheses
          2. LLM reasons about analysis methods for each prediction
          3. Build DAG with topological ordering
          4. Post-process: method compatibility check
          5. Identify data gaps

        Args:
            review: A1 output with hypotheses + evidence_chain + knowledge_gaps

        Returns:
            AnalysisPlan with DAG nodes and edges

        Raises:
            ValueError: hypotheses list is empty
            LLMError: LLM call fails after retries
        """
        if not review.hypotheses:
            raise ValueError("LiteratureReview has no hypotheses — cannot plan")

        question = review.query
        n_hypotheses = len(review.hypotheses)
        n_claims = len(review.evidence_chain)

        # Build hypotheses JSON for the prompt
        hypotheses_json = json.dumps(
            [
                {
                    "index": i,
                    "statement": h.statement,
                    "rationale": h.rationale,
                    "testable_prediction": h.testable_prediction,
                    "required_data": h.required_data,
                    "novelty": h.novelty,
                }
                for i, h in enumerate(review.hypotheses)
            ],
            ensure_ascii=False,
            indent=2,
        )

        evidence_summary = json.dumps(
            [
                {"claim": link.claim, "strength": link.strength}
                for link in review.evidence_chain
            ],
            ensure_ascii=False,
            indent=2,
        )

        knowledge_gaps = json.dumps(review.knowledge_gaps, ensure_ascii=False)

        user_prompt = (
            f"Research question: {question}\n\n"
            f"Hypotheses from literature review ({n_hypotheses} hypotheses):\n\n"
            f"{hypotheses_json}\n\n"
            f"Evidence chain ({n_claims} claims):\n"
            f"{evidence_summary}\n\n"
            f"Knowledge gaps identified:\n"
            f"{knowledge_gaps}\n\n"
            f"Design an analysis plan as a DAG to test these hypotheses."
        )

        for attempt in range(self._max_plan_retries + 1):
            try:
                response = self._llm.chat(
                    messages=[{"role": "user", "content": user_prompt}],
                    system=ORCHESTRATION_PLAN_SYSTEM,
                    max_tokens=8000,
                    thinking_budget_tokens=2000,
                )
                data = self._parse_json(response.content)
                # Log hypothesis classifications (anti-template audit)
                classifications = data.get("hypothesis_classifications", [])
                if classifications:
                    logger.info(
                        "Hypothesis classifications: %s",
                        [(c.get("hypothesis_index"), c.get("class"))
                         for c in classifications],
                    )
                else:
                    logger.warning(
                        "LLM did not provide hypothesis_classifications — "
                        "anti-template enforcement weakened"
                    )
                plan = self._build_plan(question, review.hypotheses, data)

                # Post-process: method compatibility check
                invalid_nodes = []
                for node in plan.nodes:
                    # Check sample size constraints
                    try:
                        n_samples = 300  # TCGA-COAD default; refine per dataset
                        if node.method in SAMPLE_SIZE_CONSTRAINTS:
                            if not SAMPLE_SIZE_CONSTRAINTS[node.method](n_samples):
                                invalid_nodes.append(
                                    f"{node.node_id}: method {node.method} requires "
                                    "larger sample size"
                                )
                    except Exception:
                        pass  # sample size check is advisory

                    # Check invalid combinations
                    for inv_task, inv_method in INVALID_COMBINATIONS:
                        if node.task == inv_task and node.method == inv_method:
                            invalid_nodes.append(
                                f"{node.node_id}: invalid combination "
                                f"({node.task}, {node.method})"
                            )
                    if node.method and not _check_method_compatibility(
                        node.task, node.method
                    ):
                        invalid_nodes.append(node.node_id)

                if invalid_nodes:
                    if attempt < self._max_plan_retries:
                        logger.warning(
                            "Method compatibility failed for nodes: %s. "
                            "Retry %d/%d.",
                            invalid_nodes, attempt + 1, self._max_plan_retries,
                        )
                        continue
                    else:
                        logger.warning(
                            "Method compatibility still failing after %d retries "
                            "for nodes: %s. Using closest valid method.",
                            self._max_plan_retries, invalid_nodes,
                        )
                        plan = self._fix_invalid_methods(plan)

                return plan

            except (LLMError, json.JSONDecodeError, ValueError) as e:
                if attempt < self._max_plan_retries:
                    logger.warning(
                        "Plan generation failed (attempt %d/%d): %s",
                        attempt + 1, self._max_plan_retries, e,
                    )
                else:
                    raise LLMError(
                        f"OrchestrationAgent.plan() failed after "
                        f"{self._max_plan_retries + 1} attempts: {e}"
                    ) from e

        # Should not reach here
        raise LLMError("OrchestrationAgent.plan() failed — unexpected code path")

    def validate_upstream(self, review: LiteratureReview) -> ValidationReport:
        """Layer 4 cross-validation node #1: A2 validates A1 output.

        Checks:
          1. Evidence chain internal consistency (opposing claims)
          2. Hypothesis-evidence correspondence
          3. Confidence reasonableness
          4. BLOCKER: empty evidence_chain or hypotheses
        """
        checks = [
            "evidence_chain_internal_consistency",
            "hypothesis_evidence_correspondence",
            "confidence_reasonableness",
            "non_empty_chain_and_hypotheses",
        ]
        warnings: list[str] = []
        blockers: list[str] = []

        # Check 1: Evidence chain internal consistency
        # Detect opposing-direction claims (simplified keyword-based)
        claims = [link.claim for link in review.evidence_chain]
        # Note: gene name normalization (D1-01 deferred) limitation declared here
        positive_terms = {"overexpressed", "upregulated", "high", "increased", "promotes"}
        negative_terms = {"downregulated", "low", "decreased", "suppresses", "inhibits"}
        for i, c1 in enumerate(claims):
            for c2 in claims[i + 1 :]:
                c1_pos = any(t in c1.lower() for t in positive_terms)
                c1_neg = any(t in c1.lower() for t in negative_terms)
                c2_pos = any(t in c2.lower() for t in positive_terms)
                c2_neg = any(t in c2.lower() for t in negative_terms)
                if (c1_pos and c2_neg) or (c1_neg and c2_pos):
                    # Same gene? Simple heuristic: first uppercase word
                    warnings.append(
                        "Potential conflict in evidence_chain: "
                        f"{c1[:60]}... vs {c2[:60]}..."
                    )
                    break  # one conflict per claim is enough

        # Check 2: Hypothesis-evidence correspondence
        for i, hyp in enumerate(review.hypotheses):
            cited_claims = [
                c for c in claims
                if any(word in hyp.rationale for word in c.split()[:3])
            ]
            if not cited_claims:
                warnings.append(
                    f"Hypothesis #{i+1} rationale does not clearly cite "
                    f"any claim from evidence_chain"
                )

        # Check 3: Confidence reasonableness
        weak_or_unverified = sum(
            1 for link in review.evidence_chain
            if link.strength in ("weak", "unverified")
        )
        total = len(review.evidence_chain)
        if total > 0 and weak_or_unverified / total >= 0.5:
            if review.confidence > 0.7:
                warnings.append(
                    f"Confidence ({review.confidence:.2f}) is high but "
                    f"{weak_or_unverified}/{total} claims are weak/unverified"
                )

        # Check 4: BLOCKER conditions
        if not review.evidence_chain:
            blockers.append("evidence_chain is empty")
        if not review.hypotheses:
            blockers.append("hypotheses list is empty")

        status = "BLOCKER" if blockers else ("WARNING" if warnings else "PASS")
        return ValidationReport(
            validator="A2",
            validated="A1",
            status=status,
            checks_performed=checks,
            warnings=warnings,
            blockers=blockers,
        )

    def plan_from_task(self, task: Any) -> AnalysisPlan:
        """Build AnalysisPlan directly from a BenchmarkTask (benchmark mode).

        Used for T3-DEG/T4-SURV/T5-DRUG tasks where the task.input contains
        gene names and dataset info — no literature review needed.

        Args:
            task: BenchmarkTask with task.input containing gene(s) and dataset

        Returns:
            AnalysisPlan with a minimal DAG based on task_id
        """
        task_id = task.task_id
        task_input = task.input

        gene = task_input.get("gene", task_input.get("gene_list", ["CSTB"]))
        if isinstance(gene, str):
            gene_list = [gene]
        else:
            gene_list = gene

        if task_id == "T3-DEG":
            nodes = [
                AnalysisNode(
                    node_id="node_01_deg",
                    task="differential_expression",
                    gene_list=gene_list,
                    data_source=self._resolve_data_path("tcga_coad"),
                    method="limma_voom",
                    parameters={"group_col": "sample_type"},
                    depends_on=[],
                    rationale=f"Benchmark task {task_id}: differential expression for {gene_list}",
                )
            ]
        elif task_id == "T4-SURV":
            nodes = [
                AnalysisNode(
                    node_id="node_01_surv",
                    task="survival_analysis",
                    gene_list=gene_list,
                    data_source=self._resolve_data_path("tcga_coad"),
                    method="cox_regression",
                    parameters={},
                    depends_on=[],
                    rationale=f"Benchmark task {task_id}: survival analysis for {gene_list}",
                )
            ]
        elif task_id == "T5-DRUG":
            nodes = [
                AnalysisNode(
                    node_id="node_01_drug",
                    task="drug_screening",
                    gene_list=gene_list,
                    data_source=self._resolve_data_path("gdsc2"),
                    method="spearman",
                    parameters={"fdr_threshold": 0.05},
                    depends_on=[],
                    rationale=f"Benchmark task {task_id}: drug screening for {gene_list}",
                )
            ]
        else:
            raise ValueError(f"plan_from_task not supported for task_id={task_id}")

        # Benchmark mode: create a placeholder hypothesis to satisfy
        # AnalysisPlan.__post_init__ (requires ≥1 hypothesis).
        from src.types import Hypothesis
        placeholder_hyp = Hypothesis(
            statement=f"Benchmark {task_id}",
            rationale=f"Automated benchmark task: {task.description}",
            testable_prediction=f"Gene {gene_list} analyzed via {task_id}",
            required_data=["TCGA-COAD"],
            novelty="supported_by_existing",
            novelty_justification="Benchmark mode — hypothesis auto-generated",
        )
        return AnalysisPlan(
            question=task.description,
            hypotheses=[placeholder_hyp],
            nodes=nodes,
            edges=[],
            data_gaps=[],
        )

    # ── Internal helpers ────────────────────────────────────

    @staticmethod
    def _parse_json(text: str) -> dict:
        """Parse LLM JSON output, tolerating extra text."""
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

    @staticmethod
    def _build_plan(
        question: str, hypotheses: list[Hypothesis], data: dict
    ) -> AnalysisPlan:
        """Construct AnalysisPlan from LLM JSON output."""
        nodes = []
        for raw_node in data.get("nodes", []):
            node = AnalysisNode(
                node_id=raw_node.get("node_id", ""),
                task=raw_node.get("task", ""),
                gene_list=raw_node.get("gene_list", []),
                data_source=raw_node.get("data_source", ""),
                method=raw_node.get("method", ""),
                parameters=raw_node.get("parameters", {}),
                depends_on=raw_node.get("depends_on", []),
                rationale=raw_node.get("rationale", ""),
            )
            nodes.append(node)

        edges = [
            tuple(edge) for edge in data.get("edges", []) if len(edge) == 2
        ]
        data_gaps = data.get("data_gaps", [])

        return AnalysisPlan(
            question=question,
            hypotheses=list(hypotheses),
            nodes=nodes,
            edges=edges,
            data_gaps=data_gaps,
        )

    @staticmethod
    def _fix_invalid_methods(plan: AnalysisPlan) -> AnalysisPlan:
        """Replace invalid methods with the first compatible method."""
        for node in plan.nodes:
            if node.method and not _check_method_compatibility(
                node.task, node.method
            ):
                types = TASK_DATA_TYPES.get(node.task)
                if types:
                    allowed = METHOD_COMPATIBILITY.get(types, [])
                    if allowed:
                        old_method = node.method
                        node.method = allowed[0]
                        node.rationale += (
                            f" | Method corrected from '{old_method}' "
                            f"to '{allowed[0]}' by compatibility matrix."
                        )
        return plan
