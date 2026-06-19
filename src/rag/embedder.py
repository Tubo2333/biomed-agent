# embedder.py — Embedder 抽象接口 + LLMRerank 实现
#
# 不依赖 embedding API。通过 LLM 逐批判断论文相关性。
# 设计决定 D-001: LLM Rerank 路线。

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from src.llm.client import LLMClient, LLMError
from src.types import Paper, RerankResult

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# Layer 1 反幻觉约束块（精简版 — Rerank 场景）
# ═══════════════════════════════════════════════════════════════

_RERANK_SYSTEM_PROMPT = """You are a biomedical research assistant. Rate the relevance of each paper
to the given research question. Use a 0-1 scale:
- 1.0 = Directly answers the question, core evidence
- 0.7-0.9 = Highly relevant, provides important supporting evidence
- 0.4-0.6 = Somewhat relevant, tangentially related
- 0.1-0.3 = Marginally relevant
- 0.0 = Not relevant

Consider: Does this paper's topic, findings, and population match the question?

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
  {"pmid": "12345678", "score": 0.8, "reason": "one sentence why"},
  ...
]"""


# ═══════════════════════════════════════════════════════════════
# 抽象接口
# ═══════════════════════════════════════════════════════════════


class Embedder(ABC):
    """嵌入/排序器抽象接口。

    当前唯一实现: LLMRerank。
    设计为可替换 — 后续可接入 text-embedding-3-small、
    PubMedBERT、SPECTER2 等，不改上层代码。
    """

    @abstractmethod
    def rank(
        self, query: str, papers: list[Paper], top_k: int = 10
    ) -> RerankResult:
        """对论文列表按与查询的相关性排序，返回 top-K 结果。

        Args:
            query: 研究问题
            papers: 待排序论文列表
            top_k: 返回前 K 篇

        Returns:
            RerankResult，含排序后论文 + 分数映射 + token 用量
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """实现名称，用于日志和 benchmark 报告。"""
        ...


# ═══════════════════════════════════════════════════════════════
# LLMRerank 实现
# ═══════════════════════════════════════════════════════════════


class LLMRerank(Embedder):
    """使用 LLM（deepseek-v4-pro）做语义重排序。

    不依赖 embedding API。逐批（默认 10 篇/批）发送给 LLM，
    由 LLM 理解论文内容和查询意图后打分 0-1。

    Usage:
        reranker = LLMRerank(llm_client)
        result = reranker.rank("CSTB in CRC prognosis", papers, top_k=10)
        for p in result.papers:
            print(p.pmid, result.scores[p.pmid])
    """

    def __init__(self, llm_client: LLMClient, batch_size: int = 5) -> None:
        self._llm = llm_client
        self._batch_size = batch_size
        logger.info(
            "LLMRerank initialized: batch_size=%d", batch_size
        )

    @property
    def name(self) -> str:
        return "LLMRerank"

    def rank(
        self, query: str, papers: list[Paper], top_k: int = 10
    ) -> RerankResult:
        """对论文列表做 LLM 语义重排序。

        流程：
        1. 将 papers 分成 batch_size 一批
        2. 每批发送给 LLM，获取相关性打分
        3. 合并所有分数，按 score 降序排列
        4. 返回 top-K 结果

        Args:
            query: 研究问题
            papers: 待排序论文列表
            top_k: 返回前 K 篇

        Returns:
            RerankResult，含排序论文 + 分数映射 + 总 token 用量

        Raises:
            LLMError: LLM 调用失败（不重试 — 由上层 Agent 处理）
        """
        if not papers:
            logger.warning("LLMRerank called with empty papers list")
            return RerankResult(papers=[], scores={}, token_used=0)

        all_scores: dict[str, float] = {}
        total_tokens = 0

        # ── 逐批打分 ──
        for i in range(0, len(papers), self._batch_size):
            batch = papers[i : i + self._batch_size]

            # 构建论文 JSON（截断摘要到 500 字符）
            paper_list = []
            for p in batch:
                paper_list.append(
                    {
                        "pmid": p.pmid,
                        "title": p.title,
                        "abstract": p.abstract[:500],
                    }
                )

            user_prompt = (
                f"Research question: {query}\n\n"
                f"Papers to rate:\n{json.dumps(paper_list, ensure_ascii=False)}\n\n"
                f"Rate each paper's relevance. Return JSON array."
            )

            try:
                response = self._llm.chat(
                    messages=[{"role": "user", "content": user_prompt}],
                    system=_RERANK_SYSTEM_PROMPT,
                    max_tokens=4000,
                )
                total_tokens += response.total_tokens

                batch_scores = self._parse_scores(response.content)
                all_scores.update(batch_scores)

            except (LLMError, json.JSONDecodeError, ValueError) as e:
                logger.warning(
                    "LLMRerank batch %d-%d failed: %s. "
                    "Skipping batch, scores remain 0 for these papers.",
                    i,
                    min(i + self._batch_size, len(papers)),
                    e,
                )
                # 失败不阻塞 — 该批论文得 0 分，后续排在末尾
                for p in batch:
                    all_scores.setdefault(p.pmid, 0.0)

        # ── 按分数降序排列 ──
        for p in papers:
            if p.pmid not in all_scores:
                all_scores[p.pmid] = 0.0
            p.relevance_score = all_scores[p.pmid]

        sorted_papers = sorted(
            papers, key=lambda p: all_scores.get(p.pmid, 0.0), reverse=True
        )[:top_k]

        logger.info(
            "LLMRerank complete: %d papers → top %d, token=%d",
            len(papers),
            len(sorted_papers),
            total_tokens,
        )

        return RerankResult(
            papers=sorted_papers,
            scores=all_scores,
            token_used=total_tokens,
        )

    # ── 内部 ────────────────────────────────────────────────

    @staticmethod
    def _parse_scores(llm_output: str) -> dict[str, float]:
        """解析 LLM Rerank 的 JSON 输出 → pmid → score 映射。

        容忍 LLM 输出的微小格式问题：
        - JSON 数组外有多余文字
        - 单个对象的 JSON 而非数组
        """
        # 尝试直接解析
        text = llm_output.strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # 尝试提取 JSON 数组
            start = text.find("[")
            end = text.rfind("]")
            if start != -1 and end != -1 and end > start:
                data = json.loads(text[start : end + 1])
            else:
                raise

        if isinstance(data, dict):
            data = [data]

        scores: dict[str, float] = {}
        for item in data:
            pmid = str(item.get("pmid", ""))
            score = float(item.get("score", 0))
            if pmid:
                # Clamp to [0, 1]
                scores[pmid] = max(0.0, min(1.0, score))

        return scores
