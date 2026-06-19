"""Generate Fig 6: Clean left-to-right flow with non-overlapping vertical bands.
Agnes v2 feedback: radical spacing, no overlap possible."""

import json
from pathlib import Path
import matplotlib
matplotlib.use("SVG")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

DATA = Path(__file__).resolve().parent.parent.parent / "data/demo_output/pipeline_result_20260619_160414.json"
with open(DATA, encoding="utf-8") as f:
    pipe = json.load(f)

fig, ax = plt.subplots(figsize=(24, 14))
ax.set_xlim(0, 24)
ax.set_ylim(0, 14)
ax.axis("off")

C = {
    "question": "#C62828",
    "lit": "#0395D8",
    "hyp": "#7B1FA2",
    "analysis": "#00B07C",
    "degraded": "#B2DFDB",
    "warning": "#FF8F00",
    "report": "#1565C0",
    "arrow": "#444444",
}

def box(ax, x, y, w, h, text, color, fs=9, tc="white", ec="white", ls="-", alpha=1.0):
    rect = mpatches.FancyBboxPatch(
        (x-w/2, y-h/2), w, h, boxstyle="round,pad=0.2",
        facecolor=color, edgecolor=ec, linewidth=3 if ls=="--" else 2,
        alpha=alpha, linestyle=ls,
    )
    ax.add_patch(rect)
    ax.text(x, y, text, ha="center", va="center", fontsize=fs, fontweight="bold", color=tc)

def arr(ax, x1, y1, x2, y2):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="->", color=C["arrow"], lw=2.5))

# ═══ Column centers (6 columns, 3.5 units apart) ═══
XC = [2.5, 6.0, 9.5, 13.0, 16.5, 20.0]

# Column headers
for x, hdr in zip(XC, ["QUESTION", "LITERATURE", "HYPOTHESES", "ANALYSIS", "VALIDATION", "OUTPUT"]):
    ax.text(x, 13.5, hdr, ha="center", fontsize=11, fontweight="bold", color="#555555")

# ═══ Row 1: Full pipeline flow (center y=10) ═══
Y_MAIN = 10.0

# Question
box(ax, XC[0], Y_MAIN, 3.2, 1.5, "Research\nQuestion\nCSTB in CRC", C["question"], fs=10)
# Lit
box(ax, XC[1], Y_MAIN, 3.2, 1.5, f"PubMed Search\n{pipe['papers_retrieved']} papers\n3 rounds", C["lit"], fs=9)
arr(ax, XC[0]+1.6, Y_MAIN, XC[1]-1.6, Y_MAIN)

# Hypotheses — spread across 3 rows
hyps = pipe["hypotheses"]
hyp_texts = [
    "H1: CSTB mRNA upregulated\nin CRC vs normal tissue",
    "H2: CSTB expression correlates\nwith M2 macrophage infiltration",
    "H3: High CSTB protein is adverse\nprognostic factor in CRC patients",
]
HY = [12.0, Y_MAIN, 8.0]  # wider vertical spacing — Agnes v3 alignment fix
for i, (txt, y) in enumerate(zip(hyp_texts, HY)):
    box(ax, XC[2], y, 5.5, 1.4, txt, C["hyp"], fs=8.5)
    arr(ax, XC[1]+1.6, Y_MAIN, XC[2]-2.75, y)

# Analysis nodes — spread across same 3 rows
analysis_info = [
    ("Differential Expression\nCSTB, TCGA-COAD (n=331)\nlogFC=0.073, p_adj=3.7e-5", C["analysis"], "solid"),
    ("Immune Correlation\nDEGRADED: no cache", C["degraded"], "dashed"),
    ("Survival Analysis\nCox Regression, TCGA-COAD\nHR=1.46, p=0.053", C["analysis"], "solid"),
]
for i, (txt, color, ls) in enumerate(analysis_info):
    y = HY[i]
    tc = "#333333" if color == C["degraded"] else "white"
    ec = "#F9A825" if color == C["degraded"] else "white"
    alpha = 0.6 if color == C["degraded"] else 1.0
    box(ax, XC[3], y, 4.0, 1.5, txt, color, fs=7.5, tc=tc, ec=ec, ls=ls, alpha=alpha)
    arr(ax, XC[2]+2.75, y, XC[3]-2.0, y)

# Warnings
warn_texts = [
    "W1: No cache for\nimmune_correlation task",
    "W2: CSTB gene not in\nimmune gene cache",
    "W3: |logFC|=0.073\nbelow threshold 0.5",
]
for i, txt in enumerate(warn_texts):
    box(ax, XC[4], HY[i], 4.2, 1.2, txt, C["warning"], fs=7.5, tc="#333333")
    arr(ax, XC[3]+2.0, HY[i], XC[4]-2.1, HY[i])

# Report
box(ax, XC[5], Y_MAIN, 3.2, 2.0,
    f"Structured Report\n{len(pipe.get('report',''))} chars\n6 sections\n+ L4 warnings\n+ [HUMAN REVIEW]",
    C["report"], fs=8.5)
for y in HY:
    arr(ax, XC[4]+2.1, y, XC[5]-1.6, Y_MAIN)

# ═══ Bottom: Legend + Stats ═══
legend_y = 3.0
legend = [
    mpatches.Patch(facecolor=C["lit"], label="Literature Retrieval"),
    mpatches.Patch(facecolor=C["hyp"], label="Generated Hypotheses"),
    mpatches.Patch(facecolor=C["analysis"], label="Analysis (completed)"),
    mpatches.Patch(facecolor=C["degraded"], label="Analysis (degraded)", edgecolor="#F9A825"),
    mpatches.Patch(facecolor=C["warning"], label="Layer 4 Warning"),
    mpatches.Patch(facecolor=C["report"], label="Report Output"),
]
ax.legend(handles=legend, loc="upper center", ncol=6, fontsize=8.5, framealpha=0.85,
          bbox_to_anchor=(0.5, 0.15))

# Stats bar
stats = (f"{pipe['papers_retrieved']} papers retrieved | {len(hyps)} hypotheses generated | "
         f"3 analysis nodes (2 completed, 1 degraded) | {len(pipe.get('layer4_warnings',[]))} Layer 4 warnings | "
         f"Report: {len(pipe.get('report',''))} characters")
ax.text(12, 1.5, stats, ha="center", fontsize=8.5, style="italic", color="#666666",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="#FAFAFA", edgecolor="#DDDDDD"))

ax.set_title(
    "BioMed-Agent: CSTB Case Study — Evidence-to-Results Pipeline\n"
    "Fig 6 — Multi-Agent Pipeline Execution Flow (S3, 2026-06-19)",
    fontsize=14, fontweight="bold", pad=15,
)

plt.tight_layout(pad=1)
svg_path = Path(__file__).resolve().parent / "fig6_evidence_network.svg"
png_path = Path(__file__).resolve().parent / "fig6_evidence_network.png"
plt.savefig(svg_path, dpi=150, bbox_inches="tight", format="svg")
plt.savefig(png_path, dpi=150, bbox_inches="tight", format="png")
print(f"OK: {pipe['papers_retrieved']} papers, {len(hyps)} hypotheses, 3 nodes, {len(pipe.get('layer4_warnings',[]))} warnings")
