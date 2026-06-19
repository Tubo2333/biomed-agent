"""Question decomposer for LiteratureAgent Phase 0."""

import json
import logging

from src.llm.client import LLMClient
from src.types import SearchQuery

logger = logging.getLogger(__name__)

_QUESTION_DECOMPOSE_SYSTEM = """You are a biomedical research methodologist. Your task is to decompose a
research question into PubMed-searchable sub-questions.

Given a complex biomedical question, break it down into 1-3 focused sub-questions,
each targeting a specific dimension of evidence:
- Clinical/epidemiological evidence (prognosis, diagnosis, prevalence)
- Molecular mechanism evidence (pathway, interaction, function)
- Therapeutic evidence (drug response, target, clinical trial)

For each sub-question, output a PubMed-ready search string using:
- MeSH terms where possible
- Boolean operators (AND, OR, NOT)
- Field tags ([MeSH], [tiab], [gene])

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

4. **Quantitative Precision**: Report statistical results with exact values.

5. **Negative Results**: Report what was NOT found as clearly as what was found.

## OUTPUT FORMAT (JSON)
[
  {
    "sub_question": "What is the association between CSTB expression and prognosis?",
    "search_query": "CSTB[gene] AND (colorectal neoplasms[MeSH]) AND prognosis[MeSH]",
    "dimension": "clinical",
    "rationale": "..."
  }
]"""


def decompose_question(llm: LLMClient, question: str) -> list[SearchQuery]:
    """LLM decomposes a research question into 1-3 PubMed search queries.

    Args:
        llm: LLM client for inference.
        question: Natural language research question.

    Returns:
        List of SearchQuery objects ready for PubMed retrieval.
    """
    try:
        response = llm.chat(
            messages=[{
                "role": "user",
                "content": f"Research question: {question}\n\nDecompose this question into focused PubMed search queries.",
            }],
            system=_QUESTION_DECOMPOSE_SYSTEM,
            max_tokens=2000, thinking_budget_tokens=800,
        )
    except Exception as e:
        logger.warning("Question decomposition failed: %s. Using original question.", e)
        return [SearchQuery(query_string=question)]

    try:
        data = _parse_json(response.content)
        if not isinstance(data, list) or len(data) == 0:
            raise ValueError("Expected non-empty JSON array")
    except Exception as e:
        logger.warning("Failed to parse decomposition result: %s. Using original question.", e)
        return [SearchQuery(query_string=question)]

    queries: list[SearchQuery] = []
    for item in data[:3]:
        sq_str = item.get("search_query", item.get("query", question))
        # Validate minimum query quality
        if len(sq_str) < 10:
            continue
        queries.append(SearchQuery(query_string=sq_str))
        logger.info("Sub-question: %s -> %s", item.get("dimension", "?"), sq_str[:80])

    if not queries:
        queries = [SearchQuery(query_string=question)]

    return queries


def _parse_json(text: str) -> dict | list:
    """Parse LLM JSON output, tolerating extraneous text."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        for bracket in [("[", "]"), ("{", "}")]:
            start = text.find(bracket[0])
            end = text.rfind(bracket[1])
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    continue
        raise
