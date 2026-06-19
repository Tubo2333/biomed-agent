# pubmed_tools.py — PubMed 工具定义（供 Agent tool-calling）
#
# 将 PubMedRetriever 的能力封装为 ToolDef，
# LiteratureAgent 的 Act 阶段通过 tool-calling 选择和执行。

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from src.rag.retriever import PubMedRetriever
from src.types import SearchQuery

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# ToolDef — 工具定义（来自 00- §3.2）
# ═══════════════════════════════════════════════════════════════


@dataclass
class ToolDef:
    """Agent 可调用的工具定义。

    Fields:
        name: 工具名称（唯一标识）
        description: 功能描述（LLM 据其判断何时使用）
        parameters: JSON Schema 格式的参数定义
        execute: 实际执行函数
        risk: "low" | "medium" | "high"
        requires_approval: 是否需要人工确认
    """

    name: str
    description: str
    parameters: dict[str, Any]
    execute: Callable[..., Any]
    risk: str = "low"
    requires_approval: bool = False

    def to_openai_schema(self) -> dict[str, Any]:
        """转为 OpenAI function-calling / Anthropic tool 兼容格式。"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": self.parameters,
                "required": list(self.parameters.keys()),
            },
        }


# ═══════════════════════════════════════════════════════════════
# PubMed 工具集
# ═══════════════════════════════════════════════════════════════


def create_pubmed_tools(retriever: PubMedRetriever) -> list[ToolDef]:
    """创建 PubMed 相关的工具定义列表。

    Args:
        retriever: PubMedRetriever 实例

    Returns:
        ToolDef 列表，可直接注入 LiteratureAgent 的工具注册表
    """
    return [
        ToolDef(
            name="pubmed_search",
            description=(
                "Search PubMed for biomedical literature. "
                "Returns paper metadata (title, abstract, authors, journal, year, PMID). "
                "Use this when you need to find published evidence for a specific "
                "biomedical question. Supports MeSH terms, Boolean operators, "
                "and field tags like [gene], [MeSH], [tiab]."
            ),
            parameters={
                "query": {
                    "type": "string",
                    "description": (
                        "PubMed search query. Use MeSH terms where possible, "
                        "Boolean operators (AND, OR, NOT), and field tags. "
                        "Example: 'CSTB[gene] AND colorectal neoplasms[MeSH] AND prognosis'"
                    ),
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results (1-100, default 50)",
                    "default": 50,
                },
            },
            execute=lambda query, max_results=50: retriever.search(
                SearchQuery(query_string=query, max_results=max_results)
            ),
            risk="low",
            requires_approval=False,
        ),
    ]


def get_pubmed_tool_schemas(tools: list[ToolDef]) -> list[dict[str, Any]]:
    """提取工具列表的 OpenAI 兼容 schema。

    Usage:
        schemas = get_pubmed_tool_schemas(tools)
        response = llm_client.chat(messages=[...], tools=schemas)
    """
    return [t.to_openai_schema() for t in tools]
