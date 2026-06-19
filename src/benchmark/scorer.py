"""
Biomedical Agent Benchmark — Human Scoring Templates & Inter-Rater Reliability.

Per 02-detailed-design.md §三 (scorer.py) and §四 Phase 1d:
  - Generates HumanScoreTemplate for T1-LIT Evidence Integration Score (1-5)
  - Anchoring rubric with 5 concrete anchors
  - Dual-scoring of 4/12 outputs for Cohen's kappa
  - kappa < 0.6 → all EIS conclusions downgraded to "preliminary"
"""

from dataclasses import dataclass


# ──────────────────────────────────────────────────────────────
# HumanScoreTemplate
# ──────────────────────────────────────────────────────────────

@dataclass
class HumanScoreTemplate:
    """A single human-scoring task for T1-LIT Evidence Integration Score."""
    task_id: str = "T1-LIT"
    agent_name: str = ""
    case_index: int = 0
    agent_output: str = ""           # Agent's evidence_summary (full text)
    scoring_rubric: str = ""         # The 1-5 anchoring rubric
    rater_notes: str = ""
    score: int | None = None         # 1-5, None = not yet scored
    score_justification: str = ""


# ──────────────────────────────────────────────────────────────
# Scoring Rubric — 5 Anchors
# ──────────────────────────────────────────────────────────────

EIS_RUBRIC = """
## Evidence Integration Score (EIS) — 1-5 Anchoring Rubric

Score each agent's evidence synthesis on 5 dimensions:
  (A) Completeness: Are all key evidence dimensions covered?
  (B) Traceability: Can every claim be traced to a specific PMID?
  (C) Conflict Awareness: Are evidence conflicts identified and discussed?
  (D) Quantitative Precision: Are effect sizes and confidence intervals reported?
  (E) Honesty: Are limitations and knowledge gaps explicitly stated?

Anchors:
  **1** — No meaningful synthesis. Output is a simple paper list or a
         rewording of abstracts without integration.
  **2** — Partial synthesis. Some claims are integrated but key evidence
         dimensions are missing. Claims lack PMID traceability.
  **3** — Adequate synthesis. Most claims traceable. Evidence conflicts
         noted if present. At least one quantitative result with precision.
  **4** — Good synthesis. All claims traceable to PMIDs. Evidence conflicts
         explicitly discussed. Multiple quantitative results with CIs.
         At least one knowledge gap identified.
  **5** — Excellent synthesis. All of (4) plus: evidence chain is internally
         consistent, hypothesis generation is grounded in evidence gaps,
         conflicting evidence is resolved with reasoning. Reads like a
         mini-systematic review.

Scoring Guide:
  - If the output is < 200 characters → 1
  - If the output contains no PMID references → max 2
  - If the output reports p-values as "p<0.05" without exact values → max 3
  - If the output acknowledges any limitation → at least 3
"""


# ──────────────────────────────────────────────────────────────
# Template Generator
# ──────────────────────────────────────────────────────────────

def create_template(
    agent_name: str,
    agent_output: str,
    case_index: int = 0,
) -> HumanScoreTemplate:
    """
    Create a human scoring template for one agent output.

    Caller (runner.py) invokes this when task_id == "T1-LIT".
    """
    return HumanScoreTemplate(
        task_id="T1-LIT",
        agent_name=agent_name,
        case_index=case_index,
        agent_output=agent_output,
        scoring_rubric=EIS_RUBRIC,
    )


# ──────────────────────────────────────────────────────────────
# Cohen's Kappa — Inter-Rater Reliability
# ──────────────────────────────────────────────────────────────

def compute_kappa(
    rater1_scores: list[int],
    rater2_scores: list[int],
) -> dict:
    """
    Compute Cohen's kappa for two raters scoring the same set of outputs.

    Args:
        rater1_scores: List of integer scores (1-5) from rater 1.
        rater2_scores: List of integer scores (1-5) from rater 2.

    Returns:
        {"kappa": float, "interpretation": str, "preliminary": bool}

    Interpretation (Landis & Koch 1977):
        < 0.00: Poor
        0.00-0.20: Slight
        0.21-0.40: Fair
        0.41-0.60: Moderate
        0.61-0.80: Substantial
        0.81-1.00: Almost Perfect

    Per design: kappa < 0.6 → all EIS conclusions downgraded to "preliminary".
    """
    if len(rater1_scores) != len(rater2_scores):
        raise ValueError("Raters must score the same number of items")
    if len(rater1_scores) == 0:
        return {"kappa": 1.0, "interpretation": "No items to score", "preliminary": False}

    n = len(rater1_scores)
    categories = sorted(set(rater1_scores + rater2_scores))
    n_cat = len(categories)
    cat_to_idx = {c: i for i, c in enumerate(categories)}

    # Observed agreement matrix
    observed = [[0] * n_cat for _ in range(n_cat)]
    for s1, s2 in zip(rater1_scores, rater2_scores):
        observed[cat_to_idx[s1]][cat_to_idx[s2]] += 1

    # Observed agreement proportion
    p_o = sum(observed[i][i] for i in range(n_cat)) / n

    # Expected agreement proportion
    p_e = 0.0
    for i in range(n_cat):
        row_sum = sum(observed[i])
        col_sum = sum(observed[j][i] for j in range(n_cat))
        p_e += (row_sum * col_sum) / (n * n)

    if p_e >= 1.0:
        kappa = 1.0
    else:
        kappa = (p_o - p_e) / (1.0 - p_e)

    kappa = round(kappa, 4)

    if kappa < 0.0:
        interp = "Poor"
    elif kappa < 0.21:
        interp = "Slight"
    elif kappa < 0.41:
        interp = "Fair"
    elif kappa < 0.61:
        interp = "Moderate"
    elif kappa < 0.81:
        interp = "Substantial"
    else:
        interp = "Almost Perfect"

    preliminary = kappa < 0.6

    return {
        "kappa": kappa,
        "interpretation": interp,
        "preliminary": preliminary,
        "note": (
            "Per design doc: κ < 0.6 → EIS conclusions are preliminary. "
            f"κ={kappa:.4f} → {interp}."
        ),
    }


# ──────────────────────────────────────────────────────────────
# Batch Scorer — Read/Write Scoring Files
# ──────────────────────────────────────────────────────────────

def score_batch(
    templates: list[HumanScoreTemplate],
    rater_scores: list[tuple[int, str]],  # (score, justification) per template
) -> list[HumanScoreTemplate]:
    """
    Apply a rater's scores to a batch of templates.

    Args:
        templates: List of unscored templates.
        rater_scores: List of (score: int, justification: str) tuples.

    Returns:
        Templates with scores and justifications filled in.
    """
    if len(templates) != len(rater_scores):
        raise ValueError(
            f"Template count ({len(templates)}) != score count ({len(rater_scores)})"
        )
    for template, (score, justification) in zip(templates, rater_scores):
        if not (1 <= score <= 5):
            raise ValueError(f"Score {score} out of range [1,5]")
        template.score = score
        template.score_justification = justification
    return templates
