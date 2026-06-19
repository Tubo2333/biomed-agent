"""
Biomedical Agent Benchmark — Baseline Agent Implementations.

B1 Naive LLM:     Zero-shot, no tools, no retrieval, no memory.
B2 ReAct:         Standard Think→Act→Observe cycle with tool calling.
B3 Simple RAG:    Single-round PubMed search → top-K → synthesize.
B4 Domain ReAct:  B2 + biomedical domain best practices in system prompt.

All baselines implement the EvalAgent Protocol and share the same LLM backend
(deepseek-v4-pro via LLMClient from Step 1).

Variable control design (per 02-detailed-design.md §1):
  B1: no tools, no retrieval, no multi-round, no domain prompt
  B2: tools, no retrieval, no multi-round, no domain prompt
  B3: tools, single-round retrieval, no multi-round, no domain prompt
  B4: tools, no retrieval, no multi-round, domain prompt

All generation prompts include Layer 1 anti-hallucination constraints.
"""

import json
import re
from typing import Any

from .types import BenchmarkTask, EvalAgent

# Reuse Step 1's LLM client if available, else define a minimal interface
try:
    from ..llm.client import LLMClient  # type: ignore[import-not-found]
except ImportError:
    # Fallback: define minimal interface for standalone usage
    class LLMClient:  # type: ignore[no-redef]
        """Minimal LLM client stub for standalone benchmark usage."""
        def __init__(self, model: str = "deepseek-v4-pro", temperature: float = 0.3):
            self.model = model
            self.temperature = temperature

        def chat(self, messages, model=None, temperature=None,
                 max_tokens=4000, thinking_budget_tokens=1000, tools=None, system=None) -> Any:
            raise NotImplementedError("LLMClient not available — install Step 1")


# ──────────────────────────────────────────────────────────────
# Shared Layer 1 Anti-Hallucination Block
# ──────────────────────────────────────────────────────────────

LAYER_1_CONSTRAINTS = """
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

5. **Negative Results**: Report what was NOT found as clearly as what was found.
"""


B1_OUTPUT_SCHEMA = """
## OUTPUT FORMAT (JSON only, no markdown)
{
  "answer": "Your response to the research question...",
  "confidence": 0.0-1.0,
  "limitations": ["What you cannot answer without access to data/tools"]
}
"""

B3_OUTPUT_SCHEMA = """
## OUTPUT FORMAT (JSON only, no markdown)
{
  "search_query": "the query you used",
  "retrieved_pmids": ["pmid1", "pmid2", ...],
  "synthesis": "your evidence synthesis...",
  "confidence": 0.0-1.0,
  "limitations": ["gaps or uncertainties"]
}
"""


# ──────────────────────────────────────────────────────────────
# B1: Naive LLM
# ──────────────────────────────────────────────────────────────

class NaiveLLM(EvalAgent):
    """
    Zero-shot prompting baseline. No tools, no retrieval, no memory.

    This is the weakest baseline — it relies entirely on the LLM's
    parametric knowledge from pre-training.
    """

    def __init__(self, llm_client: LLMClient):
        self._llm = llm_client

    @property
    def name(self) -> str:
        return "B1-NaiveLLM"

    def run(self, task: BenchmarkTask) -> dict[str, Any]:
        system_prompt = (
            "You are a helpful biomedical research assistant. "
            "Answer the research question to the best of your knowledge. "
            "You do NOT have access to any tools, databases, or retrieval systems. "
            f"{LAYER_1_CONSTRAINTS}"
        )

        user_prompt = (
            f"{task.description}\n\n"
            f"Task input: {json.dumps(task.input, ensure_ascii=False)}\n"
            f"{B1_OUTPUT_SCHEMA}"
        )

        response = self._llm.chat(
            messages=[{"role": "user", "content": user_prompt}],
            system=system_prompt,
            max_tokens=4000, thinking_budget_tokens=1000,
        )

        try:
            output = json.loads(response.content)
        except json.JSONDecodeError:
            output = {"answer": response.content}

        output["tools_used"] = []
        output["retrieved_pmids"] = []
        return output


# ──────────────────────────────────────────────────────────────
# B2: ReAct (Think→Act→Observe)
# ──────────────────────────────────────────────────────────────

class ReActAgent(EvalAgent):
    """
    Standard ReAct pattern: Think → Act → Observe loop with tool calling.

    Has access to tools but no retrieval augmentation and no domain prompt.
    """

    MAX_TURNS = 5

    def __init__(self, llm_client: LLMClient, tools: list[dict] | None = None):
        self._llm = llm_client
        self._tools = tools or _default_tools()

    @property
    def name(self) -> str:
        return "B2-ReAct"

    def run(self, task: BenchmarkTask) -> dict[str, Any]:
        system_prompt = (
            "You are an AI assistant with access to tools. "
            "Use the Think→Act→Observe pattern to solve the task.\n\n"
            "Format:\n"
            "Think: [your reasoning about what to do next]\n"
            "Act: tool_name(param=value, ...)  OR  FinalAnswer([your answer JSON])\n"
            "Observe: [interpretation of the tool result]\n\n"
            f"{LAYER_1_CONSTRAINTS}"
        )

        messages: list[dict] = [
            {"role": "user", "content": (
                f"{task.description}\n\n"
                f"Task input: {json.dumps(task.input, ensure_ascii=False)}"
            )}
        ]

        tools_used: list[str] = []
        final_answer: dict = {}

        for turn in range(self.MAX_TURNS):
            response = self._llm.chat(
                messages=messages,
                system=system_prompt,
                tools=self._tools,
                max_tokens=4000, thinking_budget_tokens=1000,
            )

            content = response.content
            messages.append({"role": "assistant", "content": content})

            # Parse Think / Act / Observe
            action = _parse_react_action(content)
            if action is None:
                # No more actions → extract final answer
                try:
                    final_answer = _extract_json(content)
                except Exception:
                    final_answer = {"answer": content}
                break

            tool_name, tool_params = action
            tools_used.append(tool_name)

            # Execute tool (simulated for benchmark baselines)
            tool_result = _execute_tool(tool_name, tool_params, task)
            observe_msg = f"Observe: {json.dumps(tool_result, ensure_ascii=False)}"
            messages.append({"role": "user", "content": observe_msg})

        if not final_answer:
            final_answer = {"answer": content, "truncated": True}

        final_answer["tools_used"] = tools_used
        final_answer["retrieved_pmids"] = _extract_pmids_from_messages(messages)
        return final_answer


# ──────────────────────────────────────────────────────────────
# B3: Simple RAG
# ──────────────────────────────────────────────────────────────

class SimpleRAGAgent(EvalAgent):
    """
    Single-round PubMed search → top-K → synthesize.

    Has tools + single-round retrieval, but no multi-round reasoning
    and no structured evidence chain.
    """

    def __init__(self, llm_client: LLMClient, tools: list[dict] | None = None):
        self._llm = llm_client
        self._tools = tools or _default_tools()

    @property
    def name(self) -> str:
        return "B3-SimpleRAG"

    def run(self, task: BenchmarkTask) -> dict[str, Any]:
        system_prompt = (
            "You are an AI assistant with access to PubMed search and evidence synthesis. "
            "You can search PubMed ONCE and then synthesize the results.\n\n"
            "Step 1: Search PubMed for relevant papers\n"
            "Step 2: Read the top results\n"
            "Step 3: Synthesize a response\n\n"
            f"{LAYER_1_CONSTRAINTS}"
        )

        user_prompt = (
            f"{task.description}\n\n"
            f"Task input: {json.dumps(task.input, ensure_ascii=False)}\n"
            f"{B3_OUTPUT_SCHEMA}"
        )

        response = self._llm.chat(
            messages=[{"role": "user", "content": user_prompt}],
            system=system_prompt,
            max_tokens=4000, thinking_budget_tokens=1000,
        )

        try:
            output = json.loads(response.content)
        except json.JSONDecodeError:
            output = {"answer": response.content}

        output.setdefault("tools_used", ["pubmed_search"])
        output.setdefault("retrieved_pmids", [])
        return output


# ──────────────────────────────────────────────────────────────
# B4: Domain ReAct
# ──────────────────────────────────────────────────────────────

class DomainReActAgent(EvalAgent):
    """
    B2 + biomedical domain best practices in system prompt.

    Encodes 4 methodology rules:
      1. RNA-seq → limma/DESeq2 (not t-test)
      2. Cox regression → check PH assumption (Schoenfeld test)
      3. Multiple testing → BH (not Bonferroni)
      4. Batch effect → check + report adjustment
    """

    MAX_TURNS = 5

    def __init__(self, llm_client: LLMClient, tools: list[dict] | None = None):
        self._llm = llm_client
        self._tools = tools or _default_tools()

    @property
    def name(self) -> str:
        return "B4-DomainReAct"

    def run(self, task: BenchmarkTask) -> dict[str, Any]:
        system_prompt = (
            "You are a bioinformatics researcher with deep domain expertise. "
            "Use the Think→Act→Observe pattern to solve biomedical data analysis tasks.\n\n"
            "## DOMAIN BEST PRACTICES (MUST FOLLOW)\n\n"
            "1. **Differential Expression**: For RNA-seq data, use limma-voom or DESeq2. "
            "For microarray, use limma. Do NOT use simple t-test for genomic data.\n\n"
            "2. **Survival Analysis**: Always check the proportional hazards assumption "
            "before interpreting Cox regression. If PH violated (p<0.05), report it "
            "and consider KM + log-rank as an alternative.\n\n"
            "3. **Multiple Testing Correction**: Use Benjamini-Hochberg (BH) for FDR "
            "control, not Bonferroni (too conservative for genomic data).\n\n"
            "4. **Batch Effect**: When combining multiple datasets, check for batch effects. "
            "If present, use ComBat or limma::removeBatchEffect, and report the adjustment.\n\n"
            f"{LAYER_1_CONSTRAINTS}"
        )

        messages: list[dict] = [
            {"role": "user", "content": (
                f"{task.description}\n\n"
                f"Task input: {json.dumps(task.input, ensure_ascii=False)}"
            )}
        ]

        tools_used: list[str] = []
        final_answer: dict = {}

        for turn in range(self.MAX_TURNS):
            response = self._llm.chat(
                messages=messages,
                system=system_prompt,
                tools=self._tools,
                max_tokens=4000, thinking_budget_tokens=1000,
            )

            content = response.content
            messages.append({"role": "assistant", "content": content})

            action = _parse_react_action(content)
            if action is None:
                try:
                    final_answer = _extract_json(content)
                except Exception:
                    final_answer = {"answer": content}
                break

            tool_name, tool_params = action
            tools_used.append(tool_name)
            tool_result = _execute_tool(tool_name, tool_params, task)
            messages.append({"role": "user", "content": f"Observe: {json.dumps(tool_result, ensure_ascii=False)}"})

        if not final_answer:
            final_answer = {"answer": content, "truncated": True}

        final_answer["tools_used"] = tools_used
        final_answer["retrieved_pmids"] = _extract_pmids_from_messages(messages)
        return final_answer


# ──────────────────────────────────────────────────────────────
# Tool System (shared by B2, B3, B4)
# ──────────────────────────────────────────────────────────────

def _make_tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    """Build a tool definition in OpenAI/DeepSeek function-calling format."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


def _default_tools() -> list[dict]:
    """Minimal tool definitions for benchmark baselines (OpenAI/DeepSeek compatible)."""
    return [
        _make_tool(
            "search_pubmed",
            "Search PubMed for biomedical literature. Returns PMIDs, titles, and abstracts.",
            {
                "query": {"type": "string", "description": "PubMed search query"},
                "max_results": {"type": "integer", "default": 20},
            },
            ["query"],
        ),
        _make_tool(
            "run_differential_expression",
            "Perform differential expression analysis (limma/DESeq2 for RNA-seq).",
            {
                "gene": {"type": "string"},
                "dataset": {"type": "string"},
                "group_a": {"type": "string"},
                "group_b": {"type": "string"},
            },
            ["gene", "dataset"],
        ),
        _make_tool(
            "run_survival_analysis",
            "Perform Cox regression and Kaplan-Meier survival analysis.",
            {
                "gene": {"type": "string"},
                "dataset": {"type": "string"},
            },
            ["gene", "dataset"],
        ),
        _make_tool(
            "run_drug_screening",
            "Screen drug sensitivity via Spearman correlation on GDSC2.",
            {
                "gene": {"type": "string"},
                "dataset": {"type": "string", "default": "GDSC2"},
            },
            ["gene"],
        ),
    ]


def _execute_tool(name: str, params: dict, task: BenchmarkTask) -> dict:
    """
    Simulated tool execution for benchmark baselines.

    In a real deployment, these would call actual R/Python analysis pipelines.
    For the benchmark, they return plausible stub responses so the baseline
    agents can complete the Think→Act→Observe loop.
    """
    gene = params.get("gene", task.input.get("gene", "UNKNOWN"))

    stubs = {
        "search_pubmed": {
            "results": [
                {"pmid": "99999990", "title": f"{gene} expression in cancer (stub)", "abstract": "..."},
                {"pmid": "99999991", "title": f"Prognostic value of {gene} (stub)", "abstract": "..."},
            ],
            "total_count": 2,
        },
        "run_differential_expression": {
            "gene": gene,
            "logFC": 2.3,
            "p_value": 0.001,
            "adj_p": 0.001,
            "method": "limma-voom (stub)",
        },
        "run_survival_analysis": {
            "gene": gene,
            "HR": 1.42,
            "p_value": 0.003,
            "ph_assumption_p": 0.12,
            "method": "Cox PH (stub)",
        },
        "run_drug_screening": {
            "gene": gene,
            "spearman_rho": -0.35,
            "fdr": 0.002,
            "significant_drugs": 1,
        },
    }

    return stubs.get(name, {"error": f"Unknown tool: {name}", "params": params})


# ──────────────────────────────────────────────────────────────
# Parsing Helpers
# ──────────────────────────────────────────────────────────────

_ACT_PATTERN = re.compile(
    r"Act\s*[:：]\s*(\w+)\s*\(([^)]*)\)",
    re.IGNORECASE,
)


def _parse_react_action(text: str) -> tuple[str, dict] | None:
    """Parse 'Act: tool_name(key1=val1, key2=val2)' from agent output.

    Uses a simple state-machine to handle commas inside quoted values
    (e.g., query=\"colorectal cancer, prognosis\").
    """
    match = _ACT_PATTERN.search(text)
    if match is None:
        if re.search(r"FinalAnswer", text, re.IGNORECASE):
            return None
        return None

    tool_name = match.group(1)
    params_str = match.group(2).strip()

    params: dict = {}
    if not params_str:
        return tool_name, params

    # State-machine parser: track quote depth to avoid splitting on commas inside quotes
    current: list[str] = []
    in_single = False
    in_double = False
    for ch in params_str:
        if ch == "'" and not in_double:
            in_single = not in_single
            current.append(ch)
        elif ch == '"' and not in_single:
            in_double = not in_double
            current.append(ch)
        elif ch == "," and not in_single and not in_double:
            # End of one key=value segment
            _parse_kv("".join(current).strip(), params)
            current = []
        else:
            current.append(ch)

    if current:
        _parse_kv("".join(current).strip(), params)

    return tool_name, params


def _parse_kv(segment: str, params: dict) -> None:
    """Parse a single 'key=value' segment into params dict."""
    if "=" not in segment:
        return
    k, v = segment.split("=", 1)
    key = k.strip()
    val = v.strip().strip("\"'")
    if key:
        params[key] = val


def _extract_json(text: str) -> dict[str, Any]:
    """Extract JSON object from text (may be wrapped in markdown)."""
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try extracting from ```json ... ``` block
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Try extracting first { ... } block
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    raise ValueError(f"Cannot extract JSON from: {text[:200]}")


def _extract_pmids_from_messages(messages: list[dict]) -> list[str]:
    """Extract PMID references from message history."""
    pmid_pattern = re.compile(r"PMID[：:\s]*(\d{1,8})", re.IGNORECASE)
    pmids: list[str] = []
    for msg in messages:
        for match in pmid_pattern.finditer(str(msg.get("content", ""))):
            pmids.append(match.group(1))
    return list(dict.fromkeys(pmids))  # dedup preserving order

