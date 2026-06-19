"""
Biomedical Agent Benchmark — Report Generation.

Per 02-detailed-design.md §三 and §四 Phase 3:
  - Z-score normalized + raw dual reporting
  - Radar chart data (5 tasks × 4 metrics matrix)
  - JSON export (for Step 4 consumption)
  - CSV comparison matrix
  - Markdown summary report

No LLM calls. No network I/O. Pure data transformation.
"""

import json
import csv
import io
from dataclasses import dataclass, field

from .types import AgentEvalMetrics, ContaminationRiskReport


# ──────────────────────────────────────────────────────────────
# Report Container
# ──────────────────────────────────────────────────────────────

@dataclass
class BenchmarkReport:
    """Complete benchmark report ready for serialization."""
    title: str = "Biomedical Agent Benchmark Report"
    agents: list[str] = field(default_factory=list)
    tasks: list[str] = field(default_factory=list)
    raw_matrix: dict[str, dict[str, dict[str, float]]] = field(default_factory=dict)
    normalized_matrix: dict[str, dict[str, dict[str, float]]] = field(default_factory=dict)
    trust_labels: dict[str, dict[str, str]] = field(default_factory=dict)
    contamination: list[dict] = field(default_factory=list)
    bootstrap_cis: dict[str, dict] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    passed: bool = False
    runtime_seconds: float = 0.0
    n_agents_caveat: str = ""


# ──────────────────────────────────────────────────────────────
# Report Generator
# ──────────────────────────────────────────────────────────────

def generate(
    metrics: list[AgentEvalMetrics],
    contamination_reports: list[ContaminationRiskReport] | None = None,
    bootstrap_cis: dict | None = None,
    warnings: list[str] | None = None,
    passed: bool = False,
    runtime_seconds: float = 0.0,
) -> BenchmarkReport:
    """
    Generate a complete benchmark report from raw metrics.

    Args:
        metrics: Flat list of AgentEvalMetrics from runner.
        contamination_reports: Optional contamination risk assessments.
        bootstrap_cis: Optional bootstrap confidence intervals.
        warnings: Optional warning messages from runner.
        passed: Whether all tasks passed the minimum bar.
        runtime_seconds: Total benchmark run time.

    Returns:
        BenchmarkReport ready for serialization.
    """
    report = BenchmarkReport()
    report.passed = passed
    report.runtime_seconds = runtime_seconds
    report.warnings = warnings or []
    report.bootstrap_cis = bootstrap_cis or {}

    if contamination_reports:
        report.contamination = [
            {
                "task_id": c.task_id,
                "risk_score": c.risk_score,
                "recommendation": c.recommendation,
                "details": c.details,
            }
            for c in contamination_reports
        ]

    agents = sorted(set(m.agent_name for m in metrics))
    tasks = sorted(set(m.task_id for m in metrics))
    report.agents = agents
    report.tasks = tasks

    # Z-score caveat
    n_agents = len(agents)
    if n_agents < 5:
        report.n_agents_caveat = (
            f"WARNING: only {n_agents} agents evaluated. "
            "Z-score μ and σ are unstable with n < 5. "
            "Use raw scores for primary comparison. "
            "Normalized scores are supplementary."
        )

    # Build raw matrix: agent × task × metric_name
    for m in metrics:
        agent = m.agent_name
        task = m.task_id
        report.raw_matrix.setdefault(agent, {})
        report.raw_matrix[agent][task] = {
            "completion": m.task_completion_rate,
            "tool_selection": m.tool_selection_accuracy,
            "correctness": m.result_correctness,
            "safety": m.safety_score,
            "overall_raw": m.overall_score_raw,
        }
        report.trust_labels.setdefault(agent, {})
        report.trust_labels[agent][task] = m.trust_label

    # Build normalized matrix (overall_score_normalized)
    for m in metrics:
        if m.overall_score_normalized is not None:
            agent = m.agent_name
            task = m.task_id
            report.normalized_matrix.setdefault(agent, {})
            report.normalized_matrix[agent][task] = {
                "overall_z": m.overall_score_normalized,
            }

    return report


# ──────────────────────────────────────────────────────────────
# Serializers
# ──────────────────────────────────────────────────────────────

def to_json(report: BenchmarkReport, path: str | None = None) -> str:
    """Serialize report to JSON. Writes file if path is given."""
    data = {
        "title": report.title,
        "passed": report.passed,
        "runtime_seconds": report.runtime_seconds,
        "n_agents_caveat": report.n_agents_caveat,
        "agents": report.agents,
        "tasks": report.tasks,
        "raw_matrix": report.raw_matrix,
        "normalized_matrix": report.normalized_matrix,
        "trust_labels": report.trust_labels,
        "contamination": report.contamination,
        "bootstrap_cis": report.bootstrap_cis,
        "warnings": report.warnings,
    }
    json_str = json.dumps(data, ensure_ascii=False, indent=2)
    if path:
        with open(path, "w", encoding="utf-8") as f:
            f.write(json_str)
    return json_str


def to_csv(report: BenchmarkReport, path: str | None = None) -> str:
    """Serialize report to CSV (agent × task comparison matrix)."""
    output = io.StringIO()
    writer = csv.writer(output)

    header = ["Agent", "Task", "Completion", "ToolSelection",
              "Correctness", "Safety", "OverallRaw", "OverallZ", "TrustLabel"]
    writer.writerow(header)

    for agent in report.agents:
        for task in report.tasks:
            raw = report.raw_matrix.get(agent, {}).get(task, {})
            norm = report.normalized_matrix.get(agent, {}).get(task, {})
            trust = report.trust_labels.get(agent, {}).get(task, "")
            writer.writerow([
                agent, task,
                raw.get("completion"),
                raw.get("tool_selection"),
                raw.get("correctness"),
                raw.get("safety"),
                raw.get("overall_raw"),
                norm.get("overall_z"),
                trust,
            ])

    csv_str = output.getvalue()
    if path:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(csv_str)
    return csv_str


def to_markdown(report: BenchmarkReport) -> str:
    """Generate a human-readable Markdown summary."""
    lines = [
        f"# {report.title}",
        "",
        f"**Passed**: {report.passed} | **Runtime**: {report.runtime_seconds}s | **Agents**: {len(report.agents)} | **Tasks**: {len(report.tasks)}",
        "",
    ]

    if report.warnings:
        lines.append("## ⚠️ Warnings")
        for w in report.warnings:
            lines.append(f"- {w}")
        lines.append("")

    if report.n_agents_caveat:
        lines.append(f"> {report.n_agents_caveat}")
        lines.append("")

    # Overall score table
    lines.append("## Overall Score (Raw)")
    lines.append("")
    header = "| Agent | " + " | ".join(report.tasks) + " |"
    lines.append(header)
    lines.append("|" + "---|" * (len(report.tasks) + 1))

    for agent in report.agents:
        scores = []
        for task in report.tasks:
            raw = report.raw_matrix.get(agent, {}).get(task, {})
            score = raw.get("overall_raw", "")
            trust = report.trust_labels.get(agent, {}).get(task, "")
            s = f"{score:.3f}" if isinstance(score, (int, float)) else str(score)
            if trust == "NOT TRUSTWORTHY":
                s += " ⚠️"
            elif trust == "BORDERLINE":
                s += " ⚡"
            scores.append(s)
        lines.append(f"| {agent} | " + " | ".join(scores) + " |")

    lines.append("")

    # Safety score table
    lines.append("## Safety Score")
    lines.append("")
    lines.append("| Agent | " + " | ".join(report.tasks) + " |")
    lines.append("|" + "---|" * (len(report.tasks) + 1))

    for agent in report.agents:
        scores = []
        for task in report.tasks:
            raw = report.raw_matrix.get(agent, {}).get(task, {})
            s = raw.get("safety", "")
            scores.append(f"{s:.3f}" if isinstance(s, (int, float)) else str(s))
        lines.append(f"| {agent} | " + " | ".join(scores) + " |")

    lines.append("")

    # Contamination
    if report.contamination:
        lines.append("## Contamination Risk")
        for c in report.contamination:
            lines.append(f"- **{c['task_id']}**: risk={c['risk_score']} → {c['recommendation']}")
        lines.append("")

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
# Radar Chart Data
# ──────────────────────────────────────────────────────────────

def radar_data(report: BenchmarkReport) -> dict:
    """
    Generate radar chart-ready data: per-task per-agent 4-metric vectors.

    Returns a dict suitable for matplotlib radar charts or Plotly.
    """
    metrics_names = ["completion", "tool_selection", "correctness", "safety"]
    data: dict[str, dict[str, list[float]]] = {}

    for task in report.tasks:
        data.setdefault(task, {})
        for agent in report.agents:
            raw = report.raw_matrix.get(agent, {}).get(task, {})
            data[task][agent] = [raw.get(m) for m in metrics_names]  # None if missing, distinguishable from 0.0

    return {
        "metrics": metrics_names,
        "tasks": data,
        "n_agents_caveat": report.n_agents_caveat,
    }
