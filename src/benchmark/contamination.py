"""
Biomedical Agent Benchmark — Pre-training Contamination Risk Indicator.

Per 02-detailed-design.md: naive LLM probe to assess GT memorization risk.
ADVISORY ONLY. NOT a gate on benchmark validity. One public function.
Known limits: conflates memorization with reasoning; public GT is ubiquitous.
"""

from .types import BenchmarkTask, ContaminationRiskReport


def assess_contamination_risk(
    task: BenchmarkTask,
    naive_llm_answer: str,
    training_cutoff_year: int = 2024,
) -> ContaminationRiskReport:
    """
    Assess risk that a task's GT was memorized during LLM pre-training.

    Caller (runner.py) sends task description to naive LLM (no tools/no data),
    then passes the LLM's raw answer here.

    Heuristic scoring: +0.5 if answer matches GT, +0.3 if GT pre-cutoff.
    """
    answer_matches = _match(naive_llm_answer, task)
    gt_year = _gt_year(task)
    overlaps = gt_year is not None and gt_year <= training_cutoff_year

    risk = min((0.5 if answer_matches else 0.0) + (0.3 if overlaps else 0.0), 1.0)

    if risk >= 0.8:
        rec = "INVESTIGATE"
    elif risk >= 0.5:
        rec = "CAUTION"
    else:
        rec = "OK"

    return ContaminationRiskReport(
        task_id=task.task_id,
        agent_name="NaiveLLM-Probe",
        risk_score=risk,
        naive_llm_answer_matches_gt=answer_matches,
        gt_overlaps_training_cutoff=overlaps,
        recommendation=rec,
        details=(
            f"Match={answer_matches}, GT_year={gt_year or '?'}(cutoff={training_cutoff_year}), "
            f"risk={risk}"
        ),
    )


def _match(answer: str, task: BenchmarkTask) -> bool:
    """Heuristic semantic match: naive LLM answer contains GT key terms."""
    a = answer.lower()
    gt = task.ground_truth
    gene = str(gt.get("gene", "")).lower()
    assoc = str(gt.get("association", "")).lower()
    direc = str(gt.get("direction", "")).lower()
    checks = [
        gene in a if gene and len(gene) > 1 else None,
        assoc in a if assoc and len(assoc) > 1 else None,
        direc in a if direc and len(direc) > 1 else None,
    ]
    checks = [c for c in checks if c is not None]
    if not checks:
        gt_w = set(str(gt).lower().split())
        a_w = set(a.split())
        return len(gt_w & a_w) / max(len(gt_w), 1) > 0.3 if len(gt_w) > 5 else False
    return sum(checks) >= max(1, len(checks) * 0.5)


def _gt_year(task: BenchmarkTask) -> int | None:
    """Extract GT publication year from task metadata."""
    meta = task.ground_truth.get("meta")
    y = meta.get("year") if isinstance(meta, dict) else None
    try:
        return int(y)
    except (ValueError, TypeError):
        return None
