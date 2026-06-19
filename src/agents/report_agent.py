# report_agent.py — A4: Multi-source aggregation + structured report + Layer 4
#
# Per design/03-detailed-design.md §三 (ReportAgent), §五 Prompt 3, and §6.3.
# Consumes LiteratureReview + AnalysisPlan + list[AnalysisResult] → Markdown report.
# Layer 4 cross-validation node #3: validate_upstream(A3 output).
# Effect size threshold checking: check_effect_size_claims().

from __future__ import annotations

import json
import logging
import math
from typing import Any

from src.llm.client import LLMClient, LLMError
from src.types import LiteratureReview
from src.agents.s3_types import (
    AnalysisPlan,
    AnalysisResult,
    ValidationReport,
)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# Effect size thresholds (design §6.3)
# ═══════════════════════════════════════════════════════════════

EFFECT_SIZE_THRESHOLDS = {
    "logFC": 0.5,      # |logFC| < 0.5 → weak biological significance
    "HR": 0.2,         # |log(HR)| < 0.2 → weak effect (exp(0.2)≈1.22)
    "spearman_r": 0.3, # |r| < 0.3 → weak correlation
}

SIGNIFICANCE_KEYWORDS = [
    "significant", "significantly", "strong", "strongly",
    "显著", "明显", "重要", "关键",
]

# ═══════════════════════════════════════════════════════════════
# Prompt: Report Generation (design §五 Prompt 3)
# ═══════════════════════════════════════════════════════════════

_REPORT_GENERATION_SYSTEM = """You are a senior bioinformatics researcher writing a structured case study
report. Your report will be read by a hiring manager evaluating your
scientific reasoning ability.

## REPORT STRUCTURE (MUST FOLLOW)

### 1. Introduction
- Background on the gene(s) and disease
- The specific research question
- Summary of literature evidence found

### 2. Methods
- Data sources used (dataset, sample size)
- Analysis methods applied (one line each)
- Any limitations of the methods

### 3. Results
For EACH hypothesis:
- Hypothesis statement
- What the analysis found (exact numbers, effect sizes, confidence intervals)
- Whether the evidence supports, contradicts, or is inconclusive about the hypothesis

### 4. Negative and Null Findings (MANDATORY — DO NOT SKIP)
- Which hypotheses could NOT be tested with available data? Why?
- Which analyses produced null results?
- Which genes were NOT found to be significant?

### 5. Discussion
- How do these results compare with the literature evidence?
- What are the limitations of this analysis? (list at least 3)
- What would be the next steps if this were a real research project?

### 6. Conclusion
- 2-3 sentence summary of the core finding
- The most important limitation to keep in mind

## CRITICAL WRITING RULES

1. **Every quantitative claim MUST cite its source**: either a PMID from the
   literature review, or a specific node_id from the analysis results.
   Format: [PMID:xxxxxxxx] or [Node: node_id].
2. **Report exact effect sizes**, not just p-values. "CSTB was significantly
   overexpressed (logFC=0.07, adj.P=3.7e-05)" — not "CSTB was significantly
   overexpressed".
3. **Do NOT overstate**: "trend towards significance (p=0.06)" is NOT
   "significant". "Weak correlation (r=0.15)" is NOT "strong correlation".
4. **Be honest about failures**: if an analysis degraded or failed, say so
   in the report.

## CRITICAL CONSTRAINTS (MUST FOLLOW)

1. **No Fabrication**: Do NOT fabricate gene functions, pathway associations,
   protein interactions, disease mechanisms, or biological interpretations
   that are NOT directly supported by the provided data or cited sources.

2. **Source Attribution**: Every factual claim about biology or medicine MUST
   be traced to either:
   (a) A specific PMID (PubMed ID) from the retrieved literature, OR
   (b) A specific computed result from the provided analysis data.

3. **Uncertainty Expression**: When evidence is weak, conflicting, or absent,
   explicitly state so.

4. **Quantitative Precision**: Report statistical results with exact values
   and confidence intervals.

5. **Negative Results**: Report what was NOT found as clearly as what was
   found."""


def check_effect_size_claims(results: list[AnalysisResult]) -> list[str]:
    """Check A3 results for significance claims with insufficient effect sizes.

    Args:
        results: A3 output list of AnalysisResult

    Returns:
        List of WARNING messages
    """
    warnings = []
    for r in results:
        interpretation = r.result_interpretation.lower()
        has_significance_claim = any(
            kw.lower() in interpretation for kw in SIGNIFICANCE_KEYWORDS
        )
        if not has_significance_claim:
            continue

        output = r.output

        # logFC check
        if "log2FC" in output:
            logfc = output["log2FC"]
            if logfc is not None and abs(logfc) < EFFECT_SIZE_THRESHOLDS["logFC"]:
                warnings.append(
                    f"{r.node_id}: claims significance but |logFC|={abs(logfc):.3f} "
                    f"< threshold {EFFECT_SIZE_THRESHOLDS['logFC']}"
                )

        # HR check
        if "HR" in output:
            hr = output["HR"]
            if hr is not None and hr > 0:
                log_hr = abs(math.log(hr))
                if log_hr < EFFECT_SIZE_THRESHOLDS["HR"]:
                    warnings.append(
                        f"{r.node_id}: claims significance but |log(HR)|={log_hr:.3f} "
                        f"< threshold {EFFECT_SIZE_THRESHOLDS['HR']}"
                    )

        # Spearman r check
        if "spearman_r" in output:
            r_val = output["spearman_r"]
            if r_val is not None and abs(r_val) < EFFECT_SIZE_THRESHOLDS["spearman_r"]:
                warnings.append(
                    f"{r.node_id}: claims significance but |r|={abs(r_val):.3f} "
                    f"< threshold {EFFECT_SIZE_THRESHOLDS['spearman_r']}"
                )

    return warnings


class ReportAgent:
    """Multi-source aggregation + structured report generation (A4).

    Usage:
        reporter = ReportAgent(llm_client=client, config={})
        report: str = reporter.generate(review, plan, results)
    """

    def __init__(
        self, llm_client: LLMClient, config: dict | None = None
    ) -> None:
        self._llm = llm_client
        self._config = config or {}

    # ── Public API ──────────────────────────────────────────

    def generate(
        self,
        review: LiteratureReview,
        plan: AnalysisPlan,
        results: list[AnalysisResult],
    ) -> str:
        """Generate structured Markdown report from all three upstream sources.

        Report structure (6 sections):
          1. Introduction
          2. Methods
          3. Results
          4. Negative and Null Findings (MANDATORY)
          5. Discussion
          6. Conclusion

        Strong claims marked with [HUMAN REVIEW RECOMMENDED].

        Args:
            review: A1 LiteratureReview
            plan: A2 AnalysisPlan
            results: A3 list of AnalysisResult

        Returns:
            Full Markdown report string

        Raises:
            LLMError: LLM call fails
        """
        # Build context for the prompt
        lit_summary = self._format_literature(review)
        plan_summary = self._format_plan(plan)
        results_formatted = self._format_results(results)
        degraded_summary = self._format_degraded(results)
        validation_warnings = check_effect_size_claims(results)

        user_prompt = (
            f"Research question: {review.query}\n\n"
            f"Literature evidence ({review.papers_retrieved} papers, "
            f"{len(review.evidence_chain)} claims):\n"
            f"{lit_summary}\n\n"
            f"Analysis plan ({len(plan.nodes)} nodes):\n"
            f"{plan_summary}\n\n"
            f"Analysis results:\n"
            f"{results_formatted}\n\n"
            f"Degraded or failed nodes:\n"
            f"{degraded_summary}\n\n"
            f"Effect size validation warnings:\n"
            f"{json.dumps(validation_warnings, ensure_ascii=False)}\n\n"
            f"Generate a complete structured report. Include the Negative "
            f"and Null Findings section."
        )

        try:
            response = self._llm.chat(
                messages=[{"role": "user", "content": user_prompt}],
                system=_REPORT_GENERATION_SYSTEM,
                max_tokens=8000, thinking_budget_tokens=2000,
            )
            report = response.content

            # Mark strong claims for human review
            report = self._mark_strong_claims(report, review)

            return report
        except LLMError as e:
            logger.error("Report generation failed: %s", e)
            raise

    def validate_upstream(self, results: list[AnalysisResult]) -> ValidationReport:
        """Layer 4 cross-validation node #3: A4 validates A3 output.

        Checks:
          1. Statistical sanity (HR 0.01-100, p 0-1, logFC -20~20)
          2. Cross-node contradiction detection
          3. Effect size claim checking
          4. Node coverage (all results covered in report)
          5. BLOCKER: all results status == "failed"
        """
        checks = [
            "statistical_sanity",
            "cross_node_contradiction",
            "effect_size_claims",
            "not_all_failed",
        ]
        warnings: list[str] = []
        blockers: list[str] = []

        # Check 1: Statistical sanity (reuse S2 V3 hard rules)
        for r in results:
            for key, value in r.output.items():
                if key == "HR" and value is not None and not (0.01 < value < 100):
                    warnings.append(f"{r.node_id}: HR={value} out of [0.01, 100]")
                if "p_value" in key and value is not None and not (0 <= value <= 1):
                    warnings.append(f"{r.node_id}: {key}={value} out of [0, 1]")
                if key == "log2FC" and value is not None and not (-20 < value < 20):
                    warnings.append(f"{r.node_id}: logFC={value} out of [-20, 20]")

        # Check 2: Cross-node contradiction
        for i, r1 in enumerate(results):
            for r2 in results[i + 1 :]:
                hr1 = r1.output.get("HR")
                logfc2 = r2.output.get("log2FC")
                if (
                    hr1 is not None and logfc2 is not None
                    and hr1 < 1.0 and logfc2 > 0
                ):
                    warnings.append(
                        f"Potential contradiction: {r1.node_id} HR={hr1:.3f} "
                        f"(protective) vs {r2.node_id} logFC={logfc2:.3f} "
                        f"(overexpressed) — needs biological explanation"
                    )

        # Check 3: Effect size claims
        effect_warnings = check_effect_size_claims(results)
        warnings.extend(effect_warnings)

        # Check 4: BLOCKER — all failed
        if results and all(r.status == "failed" for r in results):
            blockers.append("All analysis nodes failed")

    # NOTE: Check "node_coverage" (A3 nodes vs report-mentioned nodes) is
    # deferred to pipeline.py after report generation, because validate_upstream
    # runs BEFORE the report is generated. See pipeline.py Phase 4 post-check.

        status = "BLOCKER" if blockers else ("WARNING" if warnings else "PASS")
        return ValidationReport(
            validator="A4",
            validated="A3",
            status=status,
            checks_performed=checks,
            warnings=warnings,
            blockers=blockers,
        )

    # ── Formatting helpers ──────────────────────────────────

    @staticmethod
    def _format_literature(review: LiteratureReview) -> str:
        """Format literature evidence for the prompt."""
        parts = [
            f"Query: {review.query}",
            f"Papers retrieved: {review.papers_retrieved}",
            f"Evidence chain ({len(review.evidence_chain)} claims):",
        ]
        for link in review.evidence_chain[:10]:
            parts.append(
                f"  - [{link.strength}] {link.claim[:120]} "
                f"(PMIDs: {link.supporting_pmids[:3]})"
            )
        parts.append(f"Knowledge gaps: {review.knowledge_gaps}")
        return "\n".join(parts)

    @staticmethod
    def _format_plan(plan: AnalysisPlan) -> str:
        """Format analysis plan for the prompt."""
        parts = [f"Question: {plan.question}"]
        for node in plan.nodes:
            parts.append(
                f"  - {node.node_id}: {node.task} on {node.gene_list} "
                f"via {node.method} [{node.rationale[:80]}...]"
            )
        if plan.data_gaps:
            parts.append(f"Data gaps: {plan.data_gaps}")
        return "\n".join(parts)

    @staticmethod
    def _format_results(results: list[AnalysisResult]) -> str:
        """Format analysis results for the prompt."""
        parts = []
        for r in results:
            status_mark = "✓" if r.status == "completed" else "✗"
            parts.append(
                f"  {status_mark} {r.node_id} ({r.task}): "
                f"status={r.status}, method={r.method}"
            )
            if r.output:
                parts.append(f"    Output: {json.dumps(r.output, ensure_ascii=False)[:200]}")
            if r.result_interpretation:
                parts.append(f"    Interpretation: {r.result_interpretation[:200]}")
            if r.degradation_reason:
                parts.append(f"    Degradation: {r.degradation_reason}")
        return "\n".join(parts)

    @staticmethod
    def _format_degraded(results: list[AnalysisResult]) -> str:
        """Summarize degraded/failed nodes."""
        degraded = [r for r in results if r.status in ("degraded", "failed")]
        if not degraded:
            return "None — all analyses completed successfully."
        parts = []
        for r in degraded:
            parts.append(
                f"  - {r.node_id}: {r.status} — {r.degradation_reason or 'unknown'}"
            )
        return "\n".join(parts)

    @staticmethod
    def _mark_strong_claims(report: str, review: LiteratureReview) -> str:
        """Mark strong evidence claims for human review."""
        # Add [HUMAN REVIEW RECOMMENDED] markers for strong claims
        strong_pmids = {
            link.supporting_pmids[0]
            for link in review.evidence_chain
            if link.strength == "strong" and link.supporting_pmids
        }
        if strong_pmids:
            note = (
                "\n\n---\n**[HUMAN REVIEW RECOMMENDED]** "
                "The following claims are based on 'strong' evidence per the "
                "structured evidence chain. Verify these claims against the "
                "original papers:\n"
            )
            for pmid in list(strong_pmids)[:5]:
                note += f"- [PMID:{pmid}]\n"
            report += note
        return report
