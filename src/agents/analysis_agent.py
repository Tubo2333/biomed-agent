# analysis_agent.py — A3: Think→Act→Observe analysis executor
#
# Per design/03-detailed-design.md §三 (AnalysisAgent) and §五 Prompt 2.
# Consumes AnalysisPlan from A2 → produces list[AnalysisResult].
# Implements F1-F5 failure recovery.
# Layer 4 cross-validation node #2: validate_upstream(A2 output).

from __future__ import annotations

import json
import logging
import traceback
from pathlib import Path
from typing import Any, Optional

from src.llm.client import LLMClient, LLMError
from src.agents.s3_prompts import ANALYSIS_THINK_SYSTEM, ANALYSIS_OBSERVE_SYSTEM
from src.agents.s3_types import (
    AnalysisNode,
    AnalysisPlan,
    AnalysisResult,
    ValidationReport,
)
from src.tools.tcga_tools import TCGADataAccessor, CacheMissError, _check_method_compatibility
from src.tools.survival_tools import SurvivalTools
from src.tools.drug_tools import DrugTools
from src.tools.immune_tools import ImmuneTools

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# AnalysisAgent
# ═══════════════════════════════════════════════════════════════

MAX_PARAM_RETRIES = 2  # F2: max retries before upgrading to F4
MAX_F1_RETRIES = 3     # F1: transient error retries


class AnalysisAgent:
    """Think→Act→Observe analysis executor (A3).

    Usage:
        tools = {"tcga": TCGADataAccessor(...)}
        analyzer = AnalysisAgent(llm_client=client, tools=tools, config={})
        results: list[AnalysisResult] = analyzer.execute(plan)
    """

    def __init__(
        self,
        llm_client: LLMClient,
        tools: dict[str, Any] | None = None,
        config: dict | None = None,
    ) -> None:
        self._llm = llm_client
        self._tools = tools or {}
        self._config = config or {}
        self._tcga: Optional[TCGADataAccessor] = self._tools.get("tcga")

    # ── Public API ──────────────────────────────────────────

    def execute(self, plan: AnalysisPlan) -> list[AnalysisResult]:
        """Execute all nodes in an AnalysisPlan in topological order.

        For each node:
          1. Think: LLM selects tool and parameters
          2. Act: invoke tool (cache → real-time → F4)
          3. Observe: LLM interprets result
          4. F1-F5 failure recovery as needed
          5. Record why/what/result_interpretation in AnalysisResult

        Args:
            plan: A2 output containing DAG nodes

        Returns:
            List of AnalysisResult (one per node)
        """
        # Topological sort
        sorted_nodes = self._topological_sort(plan.nodes, plan.edges)
        results: list[AnalysisResult] = []

        # Execute upstream results for dependency context
        completed: dict[str, AnalysisResult] = {}

        for node in sorted_nodes:
            # Gather upstream context
            upstream = {
                nid: completed[nid].output
                for nid in node.depends_on
                if nid in completed
            }

            result = self._execute_node(node, upstream)
            results.append(result)
            completed[node.node_id] = result

        return results

    def validate_upstream(self, plan: AnalysisPlan) -> ValidationReport:
        """Layer 4 cross-validation node #2: A3 validates A2 output.

        Checks:
          1. Data source existence (pathlib.Path.exists)
          2. Gene name validity in target data
          3. Method reasonableness via compatibility matrix
          4. BLOCKER: all nodes reference non-existent data sources
        """
        checks = [
            "data_source_existence",
            "gene_validity",
            "method_reasonableness",
            "at_least_one_valid_source",
        ]
        warnings: list[str] = []
        blockers: list[str] = []
        valid_sources = 0

        for node in plan.nodes:
            # Check 1: Data availability via cache (not literal path existence)
            # The LLM generates conceptual data_source strings; actual data
            # goes through TCGADataAccessor which reads from cache JSON files.
            cache_available = False
            if self._tcga:
                for gene in node.gene_list:
                    if self._tcga.is_cached(gene, node.task, "TCGA-COAD"):
                        cache_available = True
                        break
            # Also check literal path as fallback
            data_path = Path(node.data_source) if node.data_source else None
            if data_path and data_path.exists():
                cache_available = True

            if cache_available:
                valid_sources += 1
            else:
                warnings.append(
                    f"{node.node_id}: data_source not found at "
                    f"'{node.data_source}' and no cache available for "
                    f"task '{node.task}' genes {node.gene_list}"
                )

            # Check 2: Gene validity in target data
            if self._tcga:
                for gene in node.gene_list:
                    if not self._tcga.is_cached(
                        gene, node.task, "TCGA-COAD"
                    ):
                        warnings.append(
                            f"{node.node_id}: gene '{gene}' not in cache for "
                            f"task '{node.task}' — may need real-time computation"
                        )

            # Check 3: Method reasonableness
            if node.method and not _check_method_compatibility(
                node.task, node.method
            ):
                warnings.append(
                    f"{node.node_id}: method '{node.method}' is not compatible "
                    f"with task '{node.task}'"
                )

        # Check 4: BLOCKER condition
        if valid_sources == 0 and plan.nodes:
            blockers.append(
                "All nodes reference non-existent data sources"
            )

        status = "BLOCKER" if blockers else ("WARNING" if warnings else "PASS")
        return ValidationReport(
            validator="A3",
            validated="A2",
            status=status,
            checks_performed=checks,
            warnings=warnings,
            blockers=blockers,
        )

    # ── Node execution ──────────────────────────────────────

    def _execute_node(
        self, node: AnalysisNode, upstream: dict[str, dict]
    ) -> AnalysisResult:
        """Execute a single DAG node through Think→Act→Observe."""
        param_retries = 0
        last_error: Optional[Exception] = None

        while param_retries <= MAX_PARAM_RETRIES:
            try:
                # ── Think ──
                think_result = self._think(node, upstream, param_retries)

                # ── Act ──
                tool_output = self._act(think_result)

                # ── Observe ──
                observe_result = self._observe(node, tool_output)

                return AnalysisResult(
                    node_id=node.node_id,
                    task=node.task,
                    status="completed",
                    output=tool_output,
                    data_source=node.data_source,
                    method=think_result.get("tool_choice", node.method),
                    raw_output_file=node.data_source,  # cache file = raw data source
                    why=think_result.get("why", ""),
                    what=f"Called {think_result.get('tool_choice', 'unknown')} "
                         f"with params {json.dumps(think_result.get('parameters', {}))}",
                    result_interpretation=observe_result.get(
                        "result_interpretation", ""
                    ),
                    failure_type=None,
                    retry_count=param_retries,
                    degradation_reason=None,
                )

            except CacheMissError as e:
                # F4: Data unavailable — degraded, skip
                logger.warning("F4: %s — degrading node %s", e, node.node_id)
                return AnalysisResult(
                    node_id=node.node_id,
                    task=node.task,
                    status="degraded",
                    output={"error": str(e)},
                    data_source=node.data_source,
                    method=node.method,
                    raw_output_file=node.data_source,  # cache file = raw data source
                    why=think_result.get("why", "") if "think_result" in dir() else "",
                    what=f"CacheMissError: {e}",
                    result_interpretation=f"Analysis degraded: {e}",
                    failure_type="F4",
                    retry_count=param_retries,
                    degradation_reason=str(e),
                )

            except (ValueError, KeyError) as e:
                # F2: Parameter error — try fallback
                param_retries += 1
                last_error = e
                if param_retries <= MAX_PARAM_RETRIES:
                    logger.info(
                        "F2: %s — retry %d/%d with fallback",
                        e, param_retries, MAX_PARAM_RETRIES,
                    )
                else:
                    logger.warning(
                        "F2: %s — max retries exhausted, upgrading to F4", e
                    )
                    return AnalysisResult(
                        node_id=node.node_id,
                        task=node.task,
                        status="degraded",
                        output={"error": str(e)},
                        data_source=node.data_source,
                        method=node.method,
                        raw_output_file=node.data_source,  # cache file = raw data source
                        why=think_result.get("why", "") if "think_result" in dir() else "",
                        what=f"F2 exhausted after {param_retries} retries: {e}",
                        result_interpretation=f"Analysis degraded after {param_retries} parameter retries: {e}",
                        failure_type="F2",
                        retry_count=param_retries,
                        degradation_reason=f"F2→F4: {e}",
                    )

            except Exception as e:
                # F5: Unknown — log and skip
                logger.error("F5: Unexpected error in node %s: %s", node.node_id, e)
                logger.error(traceback.format_exc())
                return AnalysisResult(
                    node_id=node.node_id,
                    task=node.task,
                    status="failed",
                    output={"error": str(e)},
                    data_source=node.data_source,
                    method=node.method,
                    raw_output_file=node.data_source,  # cache file = raw data source
                    why="",
                    what=f"F5 unexpected error: {e}",
                    result_interpretation=f"Analysis failed: {e}",
                    failure_type="F5",
                    retry_count=0,
                    degradation_reason=str(e),
                )

        # Should not reach here
        return AnalysisResult(
            node_id=node.node_id, task=node.task, status="failed",
            output={}, data_source=node.data_source, method=node.method,
            raw_output_file="unreachable_fallback", why="unreachable", what="unreachable",
            result_interpretation="", failure_type="F5", retry_count=0,
        )

    # ── Think ───────────────────────────────────────────────

    def _think(
        self, node: AnalysisNode, upstream: dict, retry_count: int
    ) -> dict:
        """LLM Think phase: select tool and parameters."""
        tools_desc = self._describe_tools()

        upstream_summary = json.dumps(
            {nid: list(out.keys()) for nid, out in upstream.items()},
            ensure_ascii=False,
        )

        user_prompt = (
            f"Execute analysis node: {node.node_id}\n\n"
            f"Task: {node.task}\n"
            f"Target genes: {node.gene_list}\n"
            f"Data source: {node.data_source}\n"
            f"Suggested method: {node.method}\n"
            f"Current retry: {retry_count}\n\n"
            f"Context from upstream nodes:\n{upstream_summary}\n\n"
            f"Proceed with THINK phase."
        )

        for f1_attempt in range(MAX_F1_RETRIES + 1):
            try:
                response = self._llm.chat(
                    messages=[{"role": "user", "content": user_prompt}],
                    system=ANALYSIS_THINK_SYSTEM,
                    max_tokens=4000, thinking_budget_tokens=1000,
                )
                return self._parse_json(response.content)
            except LLMError as e:
                if f1_attempt < MAX_F1_RETRIES:
                    logger.info(
                        "F1: Think LLM error (attempt %d/%d), retrying: %s",
                        f1_attempt + 1, MAX_F1_RETRIES, e,
                    )
                    continue
        # All F1 retries exhausted — use node defaults
        logger.warning("Think LLM call failed after %d F1 retries — using node defaults",
                       MAX_F1_RETRIES)
        return {
            "tool_choice": f"run_{node.task}",
            "parameters": {"gene": node.gene_list[0] if node.gene_list else "CSTB"},
            "why": f"Think phase degraded: LLM error after {MAX_F1_RETRIES} retries",
            "fallback_tool": None,
            "fallback_parameters": {},
        }

    # ── Act ─────────────────────────────────────────────────

    def _act(self, think_result: dict) -> dict[str, Any]:
        """Invoke the selected tool and return its output."""
        tool_name = think_result.get("tool_choice", "")
        params = think_result.get("parameters", {})

        # Route to the appropriate tool
        gene = params.get("gene", "CSTB")
        dataset = params.get("dataset", "TCGA-COAD")

        if "differential_expression" in tool_name or "deg" in tool_name:
            return self._run_deg(gene, dataset)
        elif "survival" in tool_name or "cox" in tool_name:
            return self._run_survival(gene, dataset)
        elif "immune" in tool_name:
            return self._run_immune(gene, dataset)
        elif "drug" in tool_name:
            return self._run_drug(gene, dataset)
        else:
            # Unknown tool — try by task type from think context
            raise ValueError(f"Unknown tool: {tool_name}")

    def _run_deg(self, gene: str, dataset: str) -> dict:
        """Run differential expression query."""
        if not self._tcga:
            raise CacheMissError("TCGA accessor not initialized")
        raw = self._tcga.query(gene, "differential_expression", dataset)
        return {
            "gene": gene,
            "log2FC": raw.get("log2FC"),
            "p_value": raw.get("p_value"),
            "p_adj": raw.get("p_adj"),
            "t_stat": raw.get("t_stat"),
            "n_tumor": raw.get("n_tumor"),
            "n_normal": raw.get("n_normal"),
        }

    def _run_survival(self, gene: str, dataset: str) -> dict:
        """Run survival analysis query."""
        if not self._tcga:
            raise CacheMissError("TCGA accessor not initialized")
        # F3 degradation handled inside SurvivalTools.query_cox
        cox = SurvivalTools.query_cox(gene, dataset, self._tcga)
        return cox

    def _run_immune(self, gene: str, dataset: str) -> dict:
        """Run immune correlation query."""
        # Simplified: placeholder for real immune data loading
        raise CacheMissError(
            "Immune correlation requires immune scores DataFrame. "
            "Load immune data into the tools dict."
        )

    def _run_drug(self, gene: str, dataset: str) -> dict:
        """Run drug screening query."""
        raise CacheMissError(
            "Drug screening requires GDSC2 expression and response DataFrames. "
            "Load GDSC2 data into the tools dict."
        )

    # ── Observe ─────────────────────────────────────────────

    def _observe(self, node: AnalysisNode, tool_output: dict) -> dict:
        """LLM Observe phase: interpret analysis results.

        Uses ANALYSIS_OBSERVE prompt (LLM call #2.N+1 per design §五).
        """
        try:
            response = self._llm.chat(
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Node: {node.node_id} ({node.task})\n"
                            f"Genes: {node.gene_list}\n"
                            f"Tool output: {json.dumps(tool_output, ensure_ascii=False)}\n\n"
                            f"Interpret this result."
                        ),
                    }
                ],
                system=ANALYSIS_OBSERVE_SYSTEM,
                max_tokens=3000, thinking_budget_tokens=800,
            )
            return self._parse_json(response.content)
        except (LLMError, json.JSONDecodeError) as e:
            logger.warning("Observe LLM call failed: %s — using basic interpretation", e)
            return {
                "result_interpretation": f"Analysis completed. "
                f"Output keys: {list(tool_output.keys())}",
                "supports_hypothesis": None,
                "caveats": [f"LLM interpretation degraded: {e}"],
            }

    # ── Helpers ─────────────────────────────────────────────

    @staticmethod
    def _topological_sort(
        nodes: list[AnalysisNode], edges: list[tuple[str, str]]
    ) -> list[AnalysisNode]:
        """Sort nodes in topological order based on depends_on/edges."""
        # Build adjacency and in-degree
        node_map = {n.node_id: n for n in nodes}
        in_degree: dict[str, int] = {n.node_id: 0 for n in nodes}
        adj: dict[str, list[str]] = {n.node_id: [] for n in nodes}

        for n in nodes:
            for dep in n.depends_on:
                if dep in node_map:
                    adj[dep].append(n.node_id)
                    in_degree[n.node_id] += 1

        for from_id, to_id in edges:
            if from_id in node_map and to_id in node_map:
                if to_id not in adj.get(from_id, []):
                    adj[from_id].append(to_id)
                    in_degree[to_id] += 1

        # Kahn's algorithm
        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        sorted_ids = []
        while queue:
            nid = queue.pop(0)
            sorted_ids.append(nid)
            for neighbor in adj.get(nid, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # Return nodes in sorted order (fallback: original order)
        sorted_nodes = [node_map[nid] for nid in sorted_ids if nid in node_map]
        for n in nodes:
            if n.node_id not in sorted_ids:
                sorted_nodes.append(n)
        return sorted_nodes

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
    def _describe_tools() -> str:
        return "\n".join([
            "- run_differential_expression(gene, dataset): Query pre-computed DEG",
            "- run_survival_analysis(gene, dataset): Query Cox regression / KM",
            "- run_immune_correlation(gene, dataset): Spearman with immune scores",
            "- run_drug_screening(gene): Spearman with GDSC2 drug IC50",
        ])
