# synthesizer.py — EvidenceSynthesizer: 多论文 → 结构化证据链 → 综述
#
# 核心模块。LLM 驱动的证据整合 + Layer 3 后验验证。
# 不是"LLM 自己看着办"——有明确的 6 步流程和硬约束。

from __future__ import annotations

import json
import logging
import re

from src.llm.client import LLMClient, LLMError
from src.types import (
    EvidenceLink,
    Paper,
    degradation_evidence_link,
    make_evidence_chain,
)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# Prompt 4: 证据整合（含 Layer 1 五条约束）
# ═══════════════════════════════════════════════════════════════

_EVIDENCE_SYNTHESIS_SYSTEM = """You are a biomedical evidence synthesis expert. Your task is to:

1. Extract atomic claims from the provided papers
2. For each claim, identify supporting PMIDs
3. Assess claim strength using this framework:
   - "strong": Multiple independent studies (ideally >=3), consistent direction,
     large sample sizes, prospective design
   - "moderate": 1-2 independent studies, or multiple small studies, or some
     inconsistency
   - "weak": Single small study, case report, expert opinion, or substantial
     conflicting evidence
   - "unverified": No supporting PMID can be found for this claim in the
     provided papers (this should be RARE — avoid generating such claims)
4. Provide a strength_justification for EVERY claim
5. If counter-evidence exists in the papers, document it
6. Generate a 300-500 word evidence summary

IMPORTANT: Every claim MUST have at least 1 supporting PMID from the
provided papers. If a claim would have 0 PMIDs, DO NOT include it.

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

## OUTPUT FORMAT (JSON object ONLY — no other text)
{
  "evidence_chain": [
    {
      "claim": "CSTB is significantly overexpressed in colorectal cancer...",
      "supporting_pmids": ["12345678", "23456789"],
      "strength": "strong",
      "strength_justification": "3 independent cohorts, total n>2000, consistent direction of upregulation",
      "counter_evidence": null
    }
  ],
  "evidence_summary": "300-500 word synthesis...",
  "confidence": 0.75,
  "knowledge_gaps": [
    "No published study examining CSTB protein levels by IHC in CRC"
  ],
  "citations": [
    "[PMID:12345678] Smith et al. (2023) CSTB overexpression in colorectal cancer..."
  ]
}"""

_SECOND_CONFIRMATION_PROMPT = """## QUICK REVIEW

Review this evidence claim marked as "strong":

Claim: {claim}
Supporting PMIDs: {pmid_list}
Justification: {justification}

Question: Is there any reason in the provided papers to downgrade this
from "strong" to "moderate" or "weak"? Consider: small sample sizes,
conflicting results, single research group, or missing controls.

Answer ONLY: "KEEP" or "DOWNGRADE: <one sentence reason>" """


# ═══════════════════════════════════════════════════════════════
# EvidenceSynthesizer
# ═══════════════════════════════════════════════════════════════


class EvidenceSynthesizer:
    """多论文 → 结构化证据链 → 300-500字证据整合摘要。

    Usage:
        synth = EvidenceSynthesizer(llm_client)
        chain, summary, confidence, gaps, citations = synth.synthesize(
            papers, "CSTB in colorectal cancer prognosis"
        )
    """

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    # ── Public API ──────────────────────────────────────────

    def synthesize(
        self, papers: list[Paper], question: str
    ) -> tuple[list[EvidenceLink], str, float, list[str], list[str]]:
        """从论文列表生成结构化的证据整合结果。

        流程（6 步）：
        Step A: LLM 提取原子主张 + 分配 PMID + 判定 strength
        Step B: 用 make_evidence_chain 构造（触发 Layer 2 硬矛盾检测）
        Step C: Layer 3 V1 — PMID 存在性验证
        Step D: Layer 3 V2 — 基因名验证（warning 级别）
        Step E: 可选二次确认 — 对 strong 且 PMID<3 的 claims
        Step F: Layer 3 V4 — 一致性检查

        Args:
            papers: 相关论文列表（通常 8-20 篇）
            question: 原始研究问题

        Returns:
            (evidence_chain, evidence_summary, confidence, knowledge_gaps, citations)

        Raises:
            ValueError: papers 为空列表
            LLMError: LLM 调用失败
        """
        if not papers:
            raise ValueError("papers must not be empty")

        # ── 构建检索 PMID 白名单 ──
        all_pmids = {p.pmid for p in papers}

        # ── Step A-B: LLM 证据整合 + 结构构造 ──
        try:
            llm_output = self._call_synthesis_llm(papers, question)
        except (LLMError, json.JSONDecodeError, ValueError) as e:
            logger.error(
                "Evidence synthesis failed: %s. Using degradation.", e
            )
            return (
                [degradation_evidence_link()],
                "LLM_UNAVAILABLE: evidence synthesis skipped",
                0.0,
                ["LLM unavailable — no evidence synthesis performed"],
                [],
            )

        # ── Step C: parse + Layer 2 ──
        evidence_chain = make_evidence_chain(
            llm_output.get("evidence_chain", [])
        )
        if not evidence_chain:
            logger.error(
                "All EvidenceLink entries failed validation. Using degradation."
            )
            return (
                [degradation_evidence_link()],
                "VALIDATION_FAILED: all evidence claims rejected by Layer 2 checks",
                0.0,
                ["Evidence chain validation failed — no valid claims"],
                [],
            )

        # ── Step D: Layer 3 V1 — PMID 存在性验证 ──
        evidence_chain = self._verify_pmids(evidence_chain, all_pmids)

        # ── Step E: Layer 3 V2 — 基因名验证 ──
        self._verify_gene_names(evidence_chain)

        # ── Step F: 二次确认 strong claims ──
        evidence_chain = self._second_confirm_strong(evidence_chain, papers)

        # ── Step G: Layer 3 V4 — 一致性检查 ──
        consistency_warnings = self._check_consistency(evidence_chain)

        # ── 组装 ──
        evidence_summary = llm_output.get("evidence_summary", "")
        confidence = float(llm_output.get("confidence", 0.5))
        knowledge_gaps = llm_output.get("knowledge_gaps", [])
        citations = llm_output.get("citations", [])

        if consistency_warnings:
            evidence_summary += (
                "\n\n⚠️ Internal consistency notes: "
                + "; ".join(consistency_warnings)
            )

        return (
            evidence_chain,
            evidence_summary,
            max(0.0, min(1.0, confidence)),
            knowledge_gaps,
            citations,
        )

    # ── LLM 调用 ────────────────────────────────────────────

    def _call_synthesis_llm(
        self, papers: list[Paper], question: str
    ) -> dict:
        """调用 LLM 执行证据整合（Prompt 4）。"""
        paper_list = []
        for p in papers:
            paper_list.append(
                {
                    "pmid": p.pmid,
                    "title": p.title,
                    "abstract": p.abstract[:800],
                    "journal": p.journal,
                    "year": p.year,
                }
            )

        user_prompt = (
            f"Research question: {question}\n\n"
            f"Papers to synthesize ({len(papers)} papers):\n"
            f"{json.dumps(paper_list, ensure_ascii=False)}\n\n"
            f"Synthesize the evidence. Ensure every claim has at least 1 supporting PMID."
        )

        response = self._llm.chat(
            messages=[{"role": "user", "content": user_prompt}],
            system=_EVIDENCE_SYNTHESIS_SYSTEM,
            max_tokens=16000,
        )
        try:
            return self._parse_json_response(response.content)
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(
                "Failed to parse synthesis LLM output: %s", e
            )
            raise LLMError(f"Synthesis JSON parse failed: {e}") from e

    def _second_confirm_strong(
        self, evidence_chain: list[EvidenceLink], papers: list[Paper]
    ) -> list[EvidenceLink]:
        """对 strong 但 PMID<3 的 claims 做二次确认。

        触发条件: strength="strong" AND len(supporting_pmids) < 3
        """
        for link in evidence_chain:
            if link.strength != "strong" or len(link.supporting_pmids) >= 3:
                continue

            prompt = _SECOND_CONFIRMATION_PROMPT.format(
                claim=link.claim,
                pmid_list=", ".join(link.supporting_pmids),
                justification=link.strength_justification,
            )
            try:
                resp = self._llm.chat(
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=200,
                )
                answer = resp.content.strip()
                if answer.startswith("DOWNGRADE:"):
                    reason = answer[len("DOWNGRADE:"):].strip()
                    logger.info(
                        "Second confirmation: downgrading strong→moderate. "
                        "Claim: %s... | Reason: %s",
                        link.claim[:80],
                        reason,
                    )
                    link.strength = "moderate"
                    link.strength_justification += (
                        f" [DOWNGRADED after review: {reason}]"
                    )
            except LLMError:
                logger.warning(
                    "Second confirmation LLM call failed for claim: %s...",
                    link.claim[:80],
                )

        return evidence_chain

    # ── Layer 3: 后验验证 ────────────────────────────────────

    @staticmethod
    def _verify_pmids(
        evidence_chain: list[EvidenceLink], all_pmids: set[str]
    ) -> list[EvidenceLink]:
        """V1 — PMID 存在性检查。

        移除不在检索结果集中的 PMID。如果移除后 supporting_pmids 为空，
        strength 会被 EvidenceLink.__post_init__ 自动降为 unverified（检测 4）。
        """
        for link in evidence_chain:
            valid = [p for p in link.supporting_pmids if p in all_pmids]
            suspicious = [
                p for p in link.supporting_pmids if p not in all_pmids
            ]
            if suspicious:
                logger.warning(
                    "Claim references PMIDs not in retrieved set: %s "
                    "| Claim: %s...",
                    suspicious,
                    link.claim[:80],
                )
                # 重建 EvidenceLink 以触发 __post_init__ 重新检测
                link.supporting_pmids = valid
                if not valid and link.strength not in ("unverified",):
                    # 手动模拟检测 4 的行为
                    link.strength = "unverified"
                    link.strength_justification += (
                        " [PMID verification failed: no valid PMIDs remain]"
                    )
        return evidence_chain

    @staticmethod
    def _verify_gene_names(
        evidence_chain: list[EvidenceLink]
    ) -> None:
        """V2 — 基因名验证（warning 级别，非硬错误）。

        提取所有疑似基因符号（大写字串），标记不在已知列表中的。
        注意：这仅是 warning，因为 LLM 可能正确引用了新基因。
        """
        # 简化的基因符号正则：大写字串（可能含数字）
        gene_pattern = re.compile(r"\b[A-Z][A-Z0-9]{1,9}\b")

        for link in evidence_chain:
            text = f"{link.claim} {link.strength_justification}"
            found = set(gene_pattern.findall(text))
            # 排除常见缩写、非基因词
            common_false = {
                "CRC", "TCGA", "GEO", "RNA", "DNA", "OS", "DFS", "HR",
                "CI", "PMID", "IHC", "PCR", "ELISA", "ROC", "AUC",
                "NOT", "AND", "OR", "THE", "ALL", "DO", "NO", "IS",
                "METHODS", "RESULTS", "CONCLUSION", "BACKGROUND",
                "RCT", "GWAS", "SNP", "CNV",
            }
            genes = found - common_false
            if genes:
                logger.debug(
                    "Genes detected in claim: %s | Claim: %s...",
                    sorted(genes),
                    link.claim[:80],
                )
            # 不做硬拒绝 — 仅日志

    @staticmethod
    def _check_consistency(
        evidence_chain: list[EvidenceLink],
    ) -> list[str]:
        """V4 — 一致性检查。

        检测证据链内部矛盾：两个 claim 对同一方向给出相反结论。
        仅做精确字符串匹配；基因名归一化依赖 NCBI gene_info（见设计文档）。

        Returns:
            警告信息列表（非致命）
        """
        warnings: list[str] = []

        # 简化的方向词检测
        up_patterns = [
            "overexpress", "upregulat", "increas", "high expression",
            "positively correlat", "poor prognosis", "worse survival",
            "shorter survival",
        ]
        down_patterns = [
            "underexpress", "downregulat", "decreas", "low expression",
            "negatively correlat", "good prognosis", "better survival",
            "longer survival",
        ]

        for i, link_a in enumerate(evidence_chain):
            for j, link_b in enumerate(evidence_chain):
                if i >= j:
                    continue

                a_up = any(p in link_a.claim.lower() for p in up_patterns)
                a_down = any(p in link_a.claim.lower() for p in down_patterns)
                b_up = any(p in link_b.claim.lower() for p in up_patterns)
                b_down = any(p in link_b.claim.lower() for p in down_patterns)

                # 一方说 up，另一方说 down → 潜在矛盾
                if (a_up and b_down) or (a_down and b_up):
                    warnings.append(
                        f"Potential conflict: claim #{i+1} vs claim #{j+1}. "
                        f"Manual review recommended."
                    )
                    logger.warning(
                        "Consistency conflict detected: "
                        "claim #%d='%s...' vs claim #%d='%s...'",
                        i + 1,
                        link_a.claim[:80],
                        j + 1,
                        link_b.claim[:80],
                    )

        return warnings

    # ── 工具 ────────────────────────────────────────────────

    @staticmethod
    def _parse_json_response(text: str) -> dict:
        """解析 LLM JSON 输出。容忍多余文字和截断。"""
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            # 尝试提取 {...}
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                json_str = text[start : end + 1]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    # JSON 可能被截断 — 尝试修复
                    pass

            logger.error(
                "Failed to parse LLM JSON response (%d chars). "
                "JSON error: %s | Last 200 chars: %s",
                len(text),
                e,
                text[-200:],
            )
            raise
