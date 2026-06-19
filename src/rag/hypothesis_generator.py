# hypothesis_generator.py — HypothesisGenerator: 证据缺口 → 可验证假设
#
# 从"已知-未知"边界生成 1-3 个可验证的科学假设。
# Novelty 二分类: novel_to_our_knowledge / supported_by_existing

from __future__ import annotations

import json
import logging
from src.llm.client import LLMClient, LLMError
from src.types import (
    EvidenceLink,
    Hypothesis,
    degradation_hypothesis,
    make_hypotheses,
)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# Prompt 5: 假设生成（含 Layer 1 五条约束）
# ═══════════════════════════════════════════════════════════════

_HYPOTHESIS_GENERATION_SYSTEM = """You are a creative but rigorous biomedical scientist. Your task is to
generate testable hypotheses from the boundary between what is known
and what is unknown.

Rules:
1. Each hypothesis MUST be grounded in the provided evidence chain
2. Each hypothesis MUST have a specific, falsifiable prediction
3. Each hypothesis MUST specify what data would be needed to test it
4. Classify each as:
   - "novel_to_our_knowledge": No paper in the provided evidence chain directly
     proposes this hypothesis
   - "supported_by_existing": The hypothesis or close variants appear in
     the provided papers (even if not yet validated)
5. Provide a novelty_justification explaining the classification
6. Generate 1-3 hypotheses — quality over quantity

A good hypothesis fills an evidence gap without overreaching.
A bad hypothesis invents genes, pathways, or mechanisms not mentioned in the papers.

## CRITICAL CONSTRAINTS (MUST FOLLOW)

1. **No Fabrication**: Do NOT fabricate gene functions, pathway associations,
   protein interactions, disease mechanisms, or biological interpretations
   that are NOT directly supported by the provided data or cited sources.

2. **Source Attribution**: Every factual claim about biology or medicine MUST
   be traced to either:
   (a) A specific PMID (PubMed ID) from the retrieved literature, OR
   (b) A specific computed result from the provided analysis data.

3. **Uncertainty Expression**: When evidence is weak, conflicting, or absent,
   explicitly state so. Use phrases like:
   - "Based on limited evidence (N=1 study)..."
   - "The evidence on this point is conflicting..."
   - "This hypothesis has NOT been experimentally validated..."
   - "We did NOT find published evidence for..."

4. **Quantitative Precision**: Report statistical results with exact values
   and confidence intervals. Do NOT round p-values to "p<0.05" — report the
   actual value. Do NOT say "significantly associated" without the effect size.

5. **Negative Results**: Report what was NOT found as clearly as what was
   found. "We found NO significant association between CSTB and ..." is as
   important as a positive finding.

## OUTPUT FORMAT (JSON array ONLY — no other text)
[
  {
    "statement": "CSTB promotes immune evasion in CRC through M2 macrophage polarization",
    "rationale": "Evidence shows CSTB associated with poor prognosis [PMID:...], but no mechanistic link examined",
    "testable_prediction": "CSTB knockdown reduces M2 markers (CD163, CD206) in co-culture",
    "required_data": ["CRC cell lines", "monocyte co-culture", "M2 marker flow panel"],
    "novelty": "novel_to_our_knowledge",
    "novelty_justification": "No paper in the evidence chain directly tested CSTB→M2 mechanistic link"
  }
]"""


# ═══════════════════════════════════════════════════════════════
# HypothesisGenerator
# ═══════════════════════════════════════════════════════════════


class HypothesisGenerator:
    """证据缺口 → 可验证的科学假设。

    Usage:
        gen = HypothesisGenerator(llm_client)
        hypotheses = gen.generate(evidence_chain, knowledge_gaps, question)
    """

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    # ── Public API ──────────────────────────────────────────

    def generate(
        self,
        evidence_chain: list[EvidenceLink],
        knowledge_gaps: list[str],
        question: str,
    ) -> list[Hypothesis]:
        """从证据链和知识缺口生成 1-3 个可验证假设。

        Args:
            evidence_chain: EvidenceSynthesizer 产出的证据链
            knowledge_gaps: 证据缺口列表
            question: 原始研究问题

        Returns:
            1-3 个 Hypothesis，已含 novelty 分类

        Raises:
            ValueError: evidence_chain 为空
            LLMError: LLM 调用失败
        """
        if not evidence_chain:
            raise ValueError("evidence_chain must not be empty")

        # ── 构建 evidence_chain JSON ──
        chain_json = []
        for link in evidence_chain:
            chain_json.append(
                {
                    "claim": link.claim,
                    "supporting_pmids": link.supporting_pmids,
                    "strength": link.strength,
                }
            )

        try:
            hypotheses = self._call_generation_llm(
                chain_json, knowledge_gaps, question
            )
        except (LLMError, json.JSONDecodeError, ValueError) as e:
            logger.error(
                "Hypothesis generation failed: %s. Using degradation.", e
            )
            return [degradation_hypothesis()]

        if not hypotheses:
            logger.warning(
                "All hypotheses failed validation. Using degradation."
            )
            return [degradation_hypothesis()]

        # 硬上限 3 个
        return hypotheses[:3]

    # ── LLM 调用 ────────────────────────────────────────────

    def _call_generation_llm(
        self,
        evidence_chain_json: list[dict],
        knowledge_gaps: list[str],
        question: str,
    ) -> list[Hypothesis]:
        """调用 LLM 生成假设（Prompt 5）。"""
        user_prompt = (
            f"Research question: {question}\n\n"
            f"Evidence chain ({len(evidence_chain_json)} claims):\n"
            f"{json.dumps(evidence_chain_json, ensure_ascii=False, indent=2)}\n\n"
            f"Knowledge gaps identified:\n"
            f"{json.dumps(knowledge_gaps, ensure_ascii=False, indent=2)}\n\n"
            f"Generate 1-3 testable hypotheses based on the known-unknown boundary."
        )

        response = self._llm.chat(
            messages=[{"role": "user", "content": user_prompt}],
            system=_HYPOTHESIS_GENERATION_SYSTEM,
            max_tokens=6000,
        )

        try:
            raw_hyps = self._parse_json_response(response.content)
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(
                "Failed to parse hypothesis LLM output: %s. "
                "Last 200 chars: %s",
                e,
                response.content[-200:],
            )
            return [degradation_hypothesis()]

        return make_hypotheses(raw_hyps)

    # ── 工具 ────────────────────────────────────────────────

    @staticmethod
    def _parse_json_response(text: str) -> list[dict]:
        """解析 LLM JSON 输出（数组）。容忍多余文字。"""
        text = text.strip()
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                data = [data]
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            start = text.find("[")
            end = text.rfind("]")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    pass
            logger.error(
                "Failed to parse hypothesis JSON. Last 200 chars: %s",
                text[-200:],
            )
            raise
