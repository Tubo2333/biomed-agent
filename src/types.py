# types.py — 共享数据类型定义（S1 定义，其他 Step 消费）
#
# 严格遵循设计文档: design/01-detailed-design.md §二
# 每一个 dataclass 的字段、类型、验证规则必须与设计文档一致。

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# 共享类型（S1 定义，写入 00- §二，其他 Step 消费）
# ═══════════════════════════════════════════════════════════════


@dataclass
class Paper:
    """单篇 PubMed 论文。

    Fields:
        pmid: PubMed ID，格式 "\\d{8}"，必填
        title: 论文标题，必填，非空
        abstract: 摘要，可为空字符串
        authors: 作者全名列表，至少 1 个
        journal: 期刊简称（ISO Abbreviation），可为 ""
        year: 出版年，范围 1900-2026
        doi: DOI，可为 None
        embedding: 不使用（LLM Rerank 路线），保留字段为 None
        relevance_score: 0-1，LLM Rerank 相关性打分，未评分时为 None
    """

    pmid: str
    title: str
    abstract: str
    authors: list[str]
    journal: str
    year: int
    doi: Optional[str] = None
    embedding: Optional[np.ndarray] = None
    relevance_score: Optional[float] = None

    def __post_init__(self) -> None:
        if not self.pmid or not self.pmid.strip():
            raise ValueError("PMID must not be empty")
        if self.year < 1900 or self.year > 2026:
            raise ValueError(f"Year {self.year} out of valid range [1900, 2026]")
        if self.relevance_score is not None and not (0 <= self.relevance_score <= 1):
            raise ValueError(
                f"relevance_score must be in [0, 1], got {self.relevance_score}"
            )


@dataclass
class EvidenceLink:
    """证据链中的一个原子主张。

    Fields:
        claim: 原子主张，必填，非空
        supporting_pmids: 支持该主张的 PMID 列表
        strength: "strong" | "moderate" | "weak" | "unverified"
        strength_justification: LLM 自证依据，必填
        counter_evidence: 反面证据，None 表示未发现反面证据

    Hard contradiction detection (Layer 2) runs in __post_init__:
        1. strength ∈ {strong, moderate} AND len(supporting_pmids) == 0 → ValueError
        2. strength == "strong" AND counter_evidence is not None → ValueError
        3. strength ∈ {strong, moderate, weak} AND strength_justification empty → ValueError
        4. len(supporting_pmids) == 0 AND counter_evidence is None → strength = "unverified"
    """

    claim: str
    supporting_pmids: list[str] = field(default_factory=list)
    strength: str = "unverified"
    strength_justification: str = ""
    counter_evidence: Optional[str] = None

    VALID_STRENGTHS: frozenset[str] = frozenset(
        {"strong", "moderate", "weak", "unverified"}
    )

    def __post_init__(self) -> None:
        # ── 检测 1: strong/moderate 必须有 PMID ──
        if self.strength in ("strong", "moderate") and len(self.supporting_pmids) == 0:
            raise ValueError(
                f"Hard contradiction: strength='{self.strength}' "
                f"but supporting_pmids is empty. "
                f"Claim: {self.claim[:80]}..."
            )

        # ── 检测 2: strong 不能有反面证据 ──
        if self.strength == "strong" and self.counter_evidence is not None:
            raise ValueError(
                "Hard contradiction: strength='strong' "
                "but counter_evidence is present. "
                f"Claim: {self.claim[:80]}..."
            )

        # ── 检测 3: strength_justification 必填 ──
        if self.strength in ("strong", "moderate", "weak"):
            if not self.strength_justification or not self.strength_justification.strip():
                raise ValueError(
                    f"Hard contradiction: strength='{self.strength}' "
                    f"but strength_justification is empty. "
                    f"Claim: {self.claim[:80]}..."
                )

        # ── 检测 4: 零证据零反面 → 自动标记为 unverified ──
        if len(self.supporting_pmids) == 0 and self.counter_evidence is None:
            self.strength = "unverified"

        # ── strength 值域校验 ──
        if self.strength not in self.VALID_STRENGTHS:
            raise ValueError(
                f"strength must be one of {set(self.VALID_STRENGTHS)}, "
                f"got '{self.strength}'"
            )


@dataclass
class Hypothesis:
    """可验证的科学假设。

    Fields:
        statement: 假设陈述，必填，非空
        rationale: 推理依据（引用 EvidenceLink 中的 claim），必填
        testable_prediction: 可验证的预测，必填
        required_data: 验证所需数据类型，至少 1 个
        novelty: "novel_to_our_knowledge" | "supported_by_existing"
        novelty_justification: 为什么判定为该 novelty，必填
    """

    statement: str
    rationale: str
    testable_prediction: str
    required_data: list[str] = field(default_factory=list)
    novelty: str = "supported_by_existing"
    novelty_justification: str = ""

    VALID_NOVELTY: frozenset[str] = frozenset(
        {"novel_to_our_knowledge", "supported_by_existing"}
    )

    def __post_init__(self) -> None:
        if self.novelty not in self.VALID_NOVELTY:
            raise ValueError(
                f"novelty must be one of {set(self.VALID_NOVELTY)}, "
                f"got '{self.novelty}'"
            )
        if not self.novelty_justification or not self.novelty_justification.strip():
            raise ValueError("novelty_justification is required")
        if not self.required_data:
            raise ValueError("required_data must not be empty")
        if not self.testable_prediction or not self.testable_prediction.strip():
            raise ValueError("testable_prediction must not be empty")


@dataclass
class LiteratureReview:
    """完整的文献调研结果。

    Fields:
        query: 原始查询，必填
        papers_retrieved: 检索到的论文总数（去重后），≥0
        papers_relevant: 筛选后的相关论文
        evidence_summary: 300-500字证据整合，不可为空
        evidence_chain: 证据链，不可为空列表
        hypotheses: 1-3个可验证假设
        confidence: 0-1，整体置信度
        knowledge_gaps: 发现的证据缺口
        citations: 带 PMID 的引用列表
        token_usage: {"input": N, "output": M, "total": N+M}
    """

    query: str
    papers_retrieved: int
    papers_relevant: list[Paper]
    evidence_summary: str
    evidence_chain: list[EvidenceLink]
    hypotheses: list[Hypothesis]
    confidence: float
    knowledge_gaps: list[str] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    token_usage: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.evidence_chain:
            raise ValueError("evidence_chain must not be empty")
        if not (0 <= self.confidence <= 1):
            raise ValueError(
                f"confidence must be in [0, 1], got {self.confidence}"
            )
        if not (1 <= len(self.hypotheses) <= 3):
            raise ValueError(
                f"hypotheses count must be 1-3, got {len(self.hypotheses)}"
            )


# ═══════════════════════════════════════════════════════════════
# Step 1 内部类型（仅 S1 内部使用，不导出）
# ═══════════════════════════════════════════════════════════════


@dataclass
class SearchQuery:
    """PubMed 检索查询。

    Fields:
        query_string: PubMed 查询字符串（支持 MeSH + 自由词）
        max_results: 最大检索篇数，[1, 100]
        sort_by: "relevance" | "date"
        date_range: (start_year, end_year)，None 不限制
    """

    query_string: str
    max_results: int = 50
    sort_by: str = "relevance"
    date_range: Optional[tuple[int, int]] = None

    def __post_init__(self) -> None:
        if self.max_results < 1 or self.max_results > 100:
            raise ValueError(
                f"max_results must be in [1, 100], got {self.max_results}"
            )


@dataclass
class SearchResult:
    """PubMed 检索结果。

    Fields:
        query: 原始查询
        papers: 检索到的论文（仅基础字段）
        total_count: PubMed 返回的总命中数
        retrieval_round: 第几轮检索（从 1 开始）
    """

    query: SearchQuery
    papers: list[Paper]
    total_count: int
    retrieval_round: int


@dataclass
class RerankResult:
    """LLM Rerank 排序结果。

    Fields:
        papers: 按 relevance_score 降序排列的论文，top-K
        scores: pmid → relevance_score 映射
        token_used: LLM Rerank 消耗的 token 数
    """

    papers: list[Paper]
    scores: dict[str, float]
    token_used: int


@dataclass
class RetrievalGate:
    """多轮检索闸门判断结果。

    Fields:
        should_continue: 是否允许继续下一轮检索
        reason: 允许/拒绝的原因
        new_query: 如果允许则为下一轮查询，否则 None
        rounds_used: 当前已用轮数
        token_used_so_far: 当前累计 token
    """

    should_continue: bool
    reason: str
    new_query: Optional[str]
    rounds_used: int
    token_used_so_far: int


# ═══════════════════════════════════════════════════════════════
# 工厂函数 — 从 LLM JSON 输出安全构造类型
# ═══════════════════════════════════════════════════════════════


def make_evidence_link(data: dict[str, Any]) -> Optional[EvidenceLink]:
    """从 LLM 输出的 JSON dict 安全构造 EvidenceLink。

    捕获 __post_init__ 中的 ValueError 并记录日志，
    返回 None 而非抛出异常。调用方必须检查返回值。

    Args:
        data: LLM JSON 输出的单个 evidence link

    Returns:
        EvidenceLink 或 None（验证失败时）
    """
    try:
        link = EvidenceLink(
            claim=data.get("claim", ""),
            supporting_pmids=data.get("supporting_pmids", []),
            strength=data.get("strength", "unverified"),
            strength_justification=data.get("strength_justification", ""),
            counter_evidence=data.get("counter_evidence"),
        )
        return link
    except ValueError as e:
        logger.warning(
            "EvidenceLink construction failed — LLM output rejected. "
            "Error: %s | Raw data keys: %s",
            e,
            list(data.keys()),
        )
        return None


def make_hypothesis(data: dict[str, Any]) -> Optional[Hypothesis]:
    """从 LLM 输出的 JSON dict 安全构造 Hypothesis。

    捕获 __post_init__ 中的 ValueError 并记录日志，
    返回 None 而非抛出异常。

    Args:
        data: LLM JSON 输出的单个 hypothesis

    Returns:
        Hypothesis 或 None（验证失败时）
    """
    try:
        hyp = Hypothesis(
            statement=data.get("statement", ""),
            rationale=data.get("rationale", ""),
            testable_prediction=data.get("testable_prediction", ""),
            required_data=data.get("required_data", []),
            novelty=data.get("novelty", "supported_by_existing"),
            novelty_justification=data.get("novelty_justification", ""),
        )
        return hyp
    except ValueError as e:
        logger.warning(
            "Hypothesis construction failed — LLM output rejected. "
            "Error: %s | Raw data keys: %s",
            e,
            list(data.keys()),
        )
        return None


def make_evidence_chain(raw_links: list[dict[str, Any]]) -> list[EvidenceLink]:
    """从 LLM 输出的 JSON 数组批量构造 EvidenceLink 列表。

    单个 link 构造失败不会影响其他 link。失败的被静默丢弃（已记录日志）。
    这与设计文档 §6.3 的降级策略一致：宁可丢弃有问题的 claim，
    也不让未经验证的数据进入证据链。

    Args:
        raw_links: LLM JSON 输出的 evidence_chain 数组

    Returns:
        验证通过的 EvidenceLink 列表（可能少于输入，但至少 1 个）
    """
    valid_links: list[EvidenceLink] = []
    for i, raw in enumerate(raw_links):
        link = make_evidence_link(raw)
        if link is not None:
            valid_links.append(link)
        else:
            logger.warning(
                "EvidenceLink #%d discarded — failed validation. "
                "Claim preview: %s",
                i,
                str(raw.get("claim", ""))[:80],
            )

    if not valid_links:
        logger.error(
            "All %d EvidenceLink entries failed validation. "
            "Evidence chain will be empty.",
            len(raw_links),
        )

    return valid_links


def make_hypotheses(raw_hyps: list[dict[str, Any]]) -> list[Hypothesis]:
    """从 LLM 输出的 JSON 数组批量构造 Hypothesis 列表。

    单个 hypothesis 构造失败不会影响其他。

    Args:
        raw_hyps: LLM JSON 输出的 hypotheses 数组

    Returns:
        验证通过的 Hypothesis 列表（0-3 个）
    """
    valid_hyps: list[Hypothesis] = []
    for i, raw in enumerate(raw_hyps):
        hyp = make_hypothesis(raw)
        if hyp is not None:
            valid_hyps.append(hyp)
        else:
            logger.warning(
                "Hypothesis #%d discarded — failed validation. "
                "Statement preview: %s",
                i,
                str(raw.get("statement", ""))[:80],
            )

    return valid_hyps[:3]  # 硬上限 3 个


# ═══════════════════════════════════════════════════════════════
# 降级模式占位构造
# ═══════════════════════════════════════════════════════════════


def degradation_evidence_link() -> EvidenceLink:
    """LLM 不可用时创建占位 EvidenceLink。

    满足 __post_init__ 的所有结构约束，
    下游可通过 strength="unverified" 和 claim 内容判断这是降级产出。
    """
    return EvidenceLink(
        claim="LLM_UNAVAILABLE: evidence synthesis skipped",
        supporting_pmids=[],
        strength="unverified",
        strength_justification="LLM API unavailable during degradation mode",
        counter_evidence=None,
    )


def degradation_hypothesis() -> Hypothesis:
    """LLM 不可用时创建占位 Hypothesis。

    满足 __post_init__ 的所有结构约束，
    下游可通过 novelty_justification 和 statement 内容判断这是降级产出。
    """
    return Hypothesis(
        statement="LLM_UNAVAILABLE: hypothesis generation skipped",
        rationale="LLM API unavailable during degradation mode",
        testable_prediction="N/A — hypothesis generation requires LLM",
        required_data=["N/A"],
        novelty="supported_by_existing",
        novelty_justification="Degradation mode — no novelty assessment possible",
    )
