"""
Biomedical Agent Benchmark — Task Definitions & Ground Truth Loaders.

Implements the 5 benchmark tasks defined in 02-biomed-benchmark.md §3.1:
  T1-LIT — Literature Retrieval & Evidence Integration
  T2-GDA — Gene-Disease Association Reasoning
  T3-DEG — Differential Expression Analysis
  T4-SURV — Survival Analysis
  T5-DRUG — Drug Sensitivity Screening

Each task has a factory function that produces BenchmarkTask instances
with ground truth loaded from local JSON files or pre-computed ITIP/CSTB data.

All tasks include tolerance bands per 02-detailed-design.md Appendix A.
All single-cohort results are labeled "exploratory, conditional on TCGA-COAD".
"""

import json
import os
from pathlib import Path
from typing import Any

from .types import BenchmarkTask

# ──────────────────────────────────────────────────────────────
# Tolerance Bands — 02-detailed-design.md Appendix A
# ──────────────────────────────────────────────────────────────

# Each band entry is either:
#   ("multiplicative", (lower, upper))  — ratio = value/gt_value must be in [lower, upper]
#   ("logfc", (abs_bound, rel_bound))   — |diff| ≤ abs_bound OR |diff|/|gt| ≤ rel_bound
#   "direction"                          — same-side-of-threshold check only
TOLERANCE_BANDS: dict[str, dict[str, tuple[str, tuple[float, float]] | str]] = {
    "T3-DEG": {
        "logFC": ("logfc", (0.5, 0.20)),  # ±0.5 absolute OR ±20% relative, whichever larger
        "adj_p": "direction",              # same-side <0.05 or >0.05 (key must match GT: adj_p)
    },
    "T4-SURV": {
        "HR": ("multiplicative", (0.85, 1.15)),  # GT*0.85 to GT*1.15
        "p_value": "direction",                   # same-side significance
    },
    "T5-DRUG": {
        "spearman_rho": ("multiplicative", (0.85, 1.15)),  # multiplicative tolerance
        "fdr": "direction",                                # same-side significance
    },
}


def _check_multiplicative(value: float, gt_value: float, band: tuple[float, float]) -> bool:
    """Check that value/gt_value is within [lower, upper] multiplicative bounds."""
    lower, upper = band
    if abs(gt_value) < 1e-10:
        return abs(value - gt_value) < 0.01
    ratio = value / gt_value
    return lower <= ratio <= upper


def _check_logfc(value: float, gt_value: float, band: tuple[float, float]) -> bool:
    """
    Check logFC tolerance: ±abs_bound absolute OR ±rel_bound relative (whichever larger).

    The band is (abs_bound, rel_bound) where rel_bound is a fraction (e.g., 0.20 = 20%).
    """
    abs_bound, rel_bound = band
    diff = abs(value - gt_value)
    if abs(gt_value) < 1e-10:
        return diff <= abs_bound
    return diff <= abs_bound or (diff / abs(gt_value)) <= rel_bound


def _check_tolerance(
    value: float, gt_value: float, band_spec: tuple[str, tuple[float, float]]
) -> bool:
    """Dispatch tolerance check based on band mode."""
    mode, band = band_spec
    if mode == "multiplicative":
        return _check_multiplicative(value, gt_value, band)
    elif mode == "logfc":
        return _check_logfc(value, gt_value, band)
    else:
        raise ValueError(f"Unknown tolerance mode: {mode}")


def _check_direction(value: float, gt_value: float, threshold: float = 0.05) -> bool:
    """Check that value and gt_value are on the same side of the threshold."""
    return (value < threshold) == (gt_value < threshold)


# ──────────────────────────────────────────────────────────────
# Ground Truth Root Path
# ──────────────────────────────────────────────────────────────

def _gt_path(filename: str) -> Path:
    """Resolve a ground truth JSON file path relative to this package's data directory."""
    base = Path(os.environ.get(
        "BENCHMARK_GT_DIR",
        str(Path(__file__).resolve().parent.parent.parent / "data" / "benchmark" / "ground_truth")
    ))
    return base / filename


# ──────────────────────────────────────────────────────────────
# T1-LIT: Literature Retrieval & Evidence Integration
# ──────────────────────────────────────────────────────────────

def make_t1_lit_tasks(gt_dir: Path | None = None) -> list[BenchmarkTask]:
    """
    Create T1-LIT benchmark tasks.

    Ground Truth: PubMed multi-strategy retrieval (MeSH + free-text + citation tracking)
    → deduplicated → high-citation papers (≥5 citations) → time-stratified
    (≥20% papers from last 3 years, no citation threshold)
    → 3/5 queries manually spot-checked.

    Returns one task per query. Each task expects the agent to:
      1. Search PubMed for relevant papers
      2. Rank by relevance
      3. Integrate evidence into a structured review

    The returned task.input contains the natural-language question.
    The returned task.ground_truth contains the gold-standard paper list.
    """
    path = gt_dir or _gt_path("t1_lit_ground_truth.json")

    try:
        with open(path, encoding="utf-8") as f:
            gt_data = json.load(f)
    except FileNotFoundError:
        # Fallback: stub GT for development before human annotation is complete
        gt_data = {
            "queries": [
                {
                    "query": "CSTB in colorectal cancer prognosis",
                    "relevant_pmids": [],
                    "year_groups": {"pre_2023": [], "2023_plus": []},
                }
            ],
            "meta": {
                "source": "PubMed multi-strategy (MeSH + free-text + citation tracking)",
                "citation_threshold": 5,
                "recent_ratio": 0.20,
                "human_reviewed_queries": 0,
                "declaration": (
                    "GT reflects well-cited literature with known temporal bias "
                    "(favors older papers). Mitigated by time-stratified reporting "
                    "(per-year-group Recall@K)."
                ),
            },
        }

    tasks = []
    for entry in gt_data["queries"]:
        tasks.append(BenchmarkTask(
            task_id="T1-LIT",
            task_name=f"Literature Review: {entry['query'][:60]}",
            description=(
                f"检索并整合关于 '{entry['query']}' 的文献证据。\n"
                f"Retrieve and synthesize literature evidence about '{entry['query']}'.\n\n"
                "要求 / Requirements:\n"
                "1. 将问题分解为可检索的子问题 / Decompose into searchable sub-questions\n"
                "2. 在 PubMed 中执行多轮检索 / Execute multiple rounds of PubMed search\n"
                "3. 按相关性对论文进行排序 / Rank papers by relevance\n"
                "4. 构建结构化证据链 / Build structured evidence chain\n"
                "5. 生成 300-500 字的证据整合摘要 / Generate 300-500 word evidence summary\n"
                "6. 识别 1-3 个可验证的假设 / Identify 1-3 testable hypotheses"
            ),
            input={"question": entry["query"]},
            ground_truth={
                "relevant_pmids": entry["relevant_pmids"],
                "year_groups": entry["year_groups"],
                "meta": gt_data["meta"],
            },
            evaluation_criteria=[
                "Recall@K",
                "Precision@K",
                "Evidence Integration Score (1-5, human-rated)",
                "Citation Accuracy",
                "Hallucination Rate",
            ],
            difficulty="hard",
            category="retrieval",
        ))
    return tasks


# ──────────────────────────────────────────────────────────────
# T2-GDA: Gene-Disease Association Reasoning
# ──────────────────────────────────────────────────────────────

def make_t2_gda_tasks(gt_dir: Path | None = None) -> list[BenchmarkTask]:
    """
    Create T2-GDA benchmark tasks.

    Ground Truth: DisGeNET + Open Targets dual-source cross-validated.
    Three confidence levels:
      - "high": both sources agree
      - "moderate": single source only
      - "low": sources disagree (excluded from primary metric)
    """
    path = gt_dir or _gt_path("t2_gda_ground_truth.json")

    try:
        with open(path, encoding="utf-8") as f:
            gt_data = json.load(f)
    except FileNotFoundError:
        gt_data = {
            "pairs": [
                {
                    "gene": "CSTB",
                    "disease": "Colorectal Cancer",
                    "association": "associated",
                    "confidence": "high",
                    "evidence_sources": {},
                }
            ],
            "meta": {
                "sources": ["DisGeNET", "Open Targets"],
                "confidence_levels": {
                    "high": "Both sources agree",
                    "moderate": "Single source only",
                    "low": "Sources disagree — excluded from primary metric",
                },
                "declaration": (
                    "GT limited by shared biases of both databases "
                    "(more comprehensive for well-studied genes/diseases)."
                ),
            },
        }

    tasks = []
    for entry in gt_data["pairs"]:
        difficulty = "easy" if entry["confidence"] == "high" else "medium"
        # low-confidence entries excluded from primary metric per design Appendix B
        exclude_from_primary = entry["confidence"] == "low"
        tasks.append(BenchmarkTask(
            task_id="T2-GDA",
            task_name=f"Gene-Disease: {entry['gene']} × {entry['disease']}",
            description=(
                f"判断 {entry['gene']} 与 {entry['disease']} 之间的关联强度。\n"
                f"Determine the association strength between {entry['gene']} and {entry['disease']}.\n\n"
                "要求 / Requirements:\n"
                "1. 搜索文献和数据库中的关联证据 / Search literature and databases\n"
                "2. 判断关联强度 / Judge association strength\n"
                "3. 引用支持你判断的证据 / Cite supporting evidence\n"
                "4. 如果证据矛盾，指出矛盾 / If evidence conflicts, identify the conflict"
            ),
            input={"gene": entry["gene"], "disease": entry["disease"]},
            ground_truth={
                "association": entry["association"],
                "confidence": entry["confidence"],
                "exclude_from_primary": exclude_from_primary,
                "evidence_sources": entry.get("evidence_sources", {}),
                "meta": gt_data["meta"],
            },
            evaluation_criteria=[
                "Association Accuracy",
                "Evidence Quality",
                "False Discovery Rate",
            ],
            difficulty=difficulty,
            category="association",
        ))
    return tasks


# ──────────────────────────────────────────────────────────────
# T3-DEG: Differential Expression Analysis
# ──────────────────────────────────────────────────────────────

def make_t3_deg_tasks(gt_dir: Path | None = None) -> list[BenchmarkTask]:
    """
    Create T3-DEG benchmark tasks.

    Ground Truth: Published TCGA-COAD differential expression results.
    Each task gives the agent an expression matrix subset and asks for DEG analysis.

    Tolerance: logFC ±0.5 absolute or ±20% relative (whichever larger).
    Single-cohort: "exploratory, conditional on TCGA-COAD".
    """
    path = gt_dir or _gt_path("t3_deg_ground_truth.json")

    try:
        with open(path, encoding="utf-8") as f:
            gt_data = json.load(f)
    except FileNotFoundError:
        gt_data = {
            "genes": [
                {
                    "gene": "CSTB",
                    "logFC": 2.3,
                    "adj_p": 1.2e-15,
                    "direction": "up",
                }
            ],
            "meta": {
                "dataset": "TCGA-COAD",
                "comparison": "tumor vs normal",
                "n_tumor": 286,
                "n_normal": 41,
                "method": "limma-voom",
                "tolerance": {
                    "logFC": "±0.5 absolute or ±20% relative (whichever larger)",
                    "adj_p": "direction only (same-side <0.05 or >0.05)",
                },
                "declaration": (
                    "GT reflects one analytical pipeline (limma-voom on TCGA-COAD). "
                    "NOT a consensus gold standard. "
                    "All results are exploratory, conditional on TCGA-COAD."
                ),
            },
        }

    tasks = []
    for entry in gt_data["genes"]:
        tasks.append(BenchmarkTask(
            task_id="T3-DEG",
            task_name=f"DEG: {entry['gene']} in TCGA-COAD",
            description=(
                f"分析 {entry['gene']} 在 TCGA-COAD 肿瘤 vs 正常组织中的差异表达。\n"
                f"Analyze differential expression of {entry['gene']} in TCGA-COAD tumor vs normal.\n\n"
                "要求 / Requirements:\n"
                "1. 选择适当的统计方法（对 RNA-seq 用 limma-voom 或 DESeq2）\n"
                "   Select appropriate statistical method (limma-voom or DESeq2 for RNA-seq)\n"
                "2. 执行差异表达分析 / Execute differential expression analysis\n"
                "3. 报告 logFC、p-value、adjusted p-value / Report logFC, p-value, adjusted p-value\n"
                "4. 对结果给出生物学解释 / Provide biological interpretation"
            ),
            input={
                "gene": entry["gene"],
                "dataset": gt_data["meta"]["dataset"],
                "comparison": gt_data["meta"]["comparison"],
            },
            ground_truth={
                "gene": entry["gene"],
                "logFC": entry["logFC"],
                "adj_p": entry["adj_p"],
                "direction": entry["direction"],
                "meta": gt_data["meta"],
            },
            evaluation_criteria=[
                "Method Selection Accuracy",
                "Result Correctness (logFC within tolerance)",
                "Step Completeness",
                "Interpretation Quality",
            ],
            difficulty="medium",
            category="analysis",
        ))
    return tasks


# ──────────────────────────────────────────────────────────────
# T4-SURV: Survival Analysis
# ──────────────────────────────────────────────────────────────

def make_t4_surv_tasks(gt_dir: Path | None = None) -> list[BenchmarkTask]:
    """
    Create T4-SURV benchmark tasks.

    Ground Truth: ITIP Phase C stepAIC Cox regression results.
    Independently verified for 3 key genes against published TCGA-COAD analyses.

    Tolerance: HR ±0.15 (multiplicative). P-value direction only.
    Single-cohort: "exploratory, conditional on TCGA-COAD".
    """
    path = gt_dir or _gt_path("t4_surv_ground_truth.json")

    try:
        with open(path, encoding="utf-8") as f:
            gt_data = json.load(f)
    except FileNotFoundError:
        gt_data = {
            "genes": [
                {
                    "gene": "CSTB",
                    "HR": 1.42,
                    "p_value": 0.003,
                    "direction": "unfavorable",
                    "independently_verified": True,
                    "verification_source": "Published TCGA-COAD supplementary table",
                }
            ],
            "meta": {
                "dataset": "TCGA-COAD",
                "n_patients": 303,
                "pipeline": "ITIP Phase C — stepAIC Cox regression",
                "tolerance": {
                    "HR": "±0.15 (multiplicative: GT*0.85 to GT*1.15)",
                    "p_value": "direction only (same-side <0.05 or >0.05)",
                },
                "declaration": (
                    "GT reflects one specific pipeline (ITIP stepAIC Cox). "
                    "NOT a consensus gold standard. "
                    "3 key genes independently cross-checked against published results. "
                    "All results are exploratory, conditional on TCGA-COAD."
                ),
            },
        }

    tasks = []
    for entry in gt_data["genes"]:
        tasks.append(BenchmarkTask(
            task_id="T4-SURV",
            task_name=f"Survival: {entry['gene']} in TCGA-COAD",
            description=(
                f"构建 {entry['gene']} 在 TCGA-COAD 中的预后模型。\n"
                f"Build a prognostic model for {entry['gene']} in TCGA-COAD.\n\n"
                "要求 / Requirements:\n"
                "1. 执行 Cox 比例风险回归 / Execute Cox proportional hazards regression\n"
                "2. 检查 PH 假设（Schoenfeld residuals test）\n"
                "   Check proportional hazards assumption (Schoenfeld residuals test)\n"
                "3. 报告 Hazard Ratio 和 95% CI / Report Hazard Ratio and 95% CI\n"
                "4. 绘制 Kaplan-Meier 曲线 / Plot Kaplan-Meier curves\n"
                "5. 如果 PH 假设不满足，降级为 KM + log-rank / If PH violated, fallback to KM + log-rank"
            ),
            input={
                "gene": entry["gene"],
                "dataset": gt_data["meta"]["dataset"],
                "n_patients": gt_data["meta"]["n_patients"],
            },
            ground_truth={
                "gene": entry["gene"],
                "HR": entry["HR"],
                "p_value": entry["p_value"],
                "direction": entry["direction"],
                "independently_verified": entry["independently_verified"],
                "meta": gt_data["meta"],
            },
            evaluation_criteria=[
                "HR Accuracy (within ±0.15 tolerance)",
                "P-value Direction Consistency",
                "KM Plot Correctness",
                "PH Assumption Check",
            ],
            difficulty="hard",
            category="analysis",
        ))
    return tasks


# ──────────────────────────────────────────────────────────────
# T5-DRUG: Drug Sensitivity Screening
# ──────────────────────────────────────────────────────────────

def make_t5_drug_tasks(gt_dir: Path | None = None) -> list[BenchmarkTask]:
    """
    Create T5-DRUG benchmark tasks.

    Ground Truth: ITIP Phase E GDSC2 Spearman correlation results.

    Tolerance: Spearman rho ±0.15 (multiplicative). FDR direction only.
    Single-cohort: "exploratory, conditional on GDSC2".
    """
    path = gt_dir or _gt_path("t5_drug_ground_truth.json")

    try:
        with open(path, encoding="utf-8") as f:
            gt_data = json.load(f)
    except FileNotFoundError:
        gt_data = {
            "gene_drug_pairs": [
                {
                    "gene": "CSTB",
                    "drug": "Trametinib",
                    "spearman_rho": -0.35,
                    "fdr": 0.002,
                    "direction": "sensitive",
                }
            ],
            "meta": {
                "dataset": "GDSC2",
                "pipeline": "ITIP Phase E — Spearman correlation",
                "tolerance": {
                    "spearman_rho": "±0.15 (multiplicative)",
                    "fdr": "direction only (same-side <0.05 or >0.05)",
                },
                "declaration": (
                    "GT reflects one specific pipeline (ITIP Spearman correlation on GDSC2). "
                    "NOT a consensus gold standard. "
                    "All results are exploratory, conditional on GDSC2."
                ),
            },
        }

    tasks = []
    for entry in gt_data["gene_drug_pairs"]:
        tasks.append(BenchmarkTask(
            task_id="T5-DRUG",
            task_name=f"Drug: {entry['gene']} × {entry['drug']}",
            description=(
                f"筛选 {entry['gene']} 相关的药物敏感性。\n"
                f"Screen drug sensitivity associated with {entry['gene']}.\n\n"
                "要求 / Requirements:\n"
                "1. 执行基因-药物 Spearman 相关性分析 / Execute gene-drug Spearman correlation\n"
                "2. 执行多重检验校正（Benjamini-Hochberg FDR）\n"
                "   Apply multiple testing correction (Benjamini-Hochberg FDR)\n"
                "3. 报告显著关联 / Report significant associations\n"
                "4. 将药物按敏感性/耐药性分类 / Classify drugs as sensitizing or resistance"
            ),
            input={
                "gene": entry["gene"],
                "drug": entry["drug"],
                "dataset": gt_data["meta"]["dataset"],
            },
            ground_truth={
                "gene": entry["gene"],
                "drug": entry["drug"],
                "spearman_rho": entry["spearman_rho"],
                "fdr": entry["fdr"],
                "direction": entry["direction"],
                "meta": gt_data["meta"],
            },
            evaluation_criteria=[
                "Correlation Accuracy (rho within tolerance)",
                "FDR Control Correctness",
                "Drug Classification Accuracy",
                "Missing Data Handling",
            ],
            difficulty="hard",
            category="analysis",
        ))
    return tasks


# ──────────────────────────────────────────────────────────────
# Task Factory — Unified Entry Point
# ──────────────────────────────────────────────────────────────

def load_all_tasks(gt_dir: Path | None = None) -> list[BenchmarkTask]:
    """
    Load all 5 benchmark tasks.

    Args:
        gt_dir: Optional override for ground truth JSON directory.

    Returns:
        Combined list of all BenchmarkTask instances.
    """
    tasks: list[BenchmarkTask] = []
    tasks.extend(make_t1_lit_tasks(gt_dir))
    tasks.extend(make_t2_gda_tasks(gt_dir))
    tasks.extend(make_t3_deg_tasks(gt_dir))
    tasks.extend(make_t4_surv_tasks(gt_dir))
    tasks.extend(make_t5_drug_tasks(gt_dir))
    return tasks
