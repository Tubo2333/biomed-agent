"""Generate Fig 2: Structured Evidence Chain — EvidenceLink data model diagram."""

from pathlib import Path
import matplotlib
matplotlib.use("SVG")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

fig, ax = plt.subplots(figsize=(14, 6))
ax.set_xlim(0, 14)
ax.set_ylim(0, 6)
ax.axis("off")

# Colors
C_CLAIM = "#00B07C"
C_PMID = "#0395D8"
C_STRENGTH = "#7B1FA2"
C_COUNTER = "#E84040"
C_GAP = "#F9A825"

def box(ax, x, y, w, h, text, color, fontsize=8.5):
    rect = mpatches.FancyBboxPatch((x-w/2, y-h/2), w, h, boxstyle="round,pad=0.12",
                                    facecolor=color, edgecolor="white", linewidth=2)
    ax.add_patch(rect)
    ax.text(x, y, text, ha="center", va="center", fontsize=fontsize, fontweight="bold", color="white")

def arrow(ax, x1, y1, x2, y2):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="->", color="#555555", lw=1.8))

# ═══ Claim (center) ═══
box(ax, 7, 4.5, 5.5, 1.2,
    "Claim: \"CSTB shows trend toward unfavorable\nprognosis in CRC (HR=1.46, p=0.053)\"",
    C_CLAIM, fontsize=9)

# ═══ Supporting PMIDs (left) ═══
box(ax, 2.5, 5.0, 2.8, 0.9,
    "Supporting PMIDs\n[PMID:10690531]\n[PMID:21833088]",
    C_PMID, fontsize=8)
arrow(ax, 4.0, 5.0, 4.2, 4.7)

# ═══ Strength (right) ═══
box(ax, 11, 5.0, 3.0, 1.5,
    "Strength: \"moderate\"\nJustification:\n\"1 study (n=345),\nconsistent direction,\nlimited to serum\"",
    C_STRENGTH, fontsize=7.5)
arrow(ax, 9.8, 4.7, 9.5, 4.9)

# ═══ Counter-evidence (bottom-right) ═══
box(ax, 11, 2.5, 3.0, 1.1,
    "Counter-Evidence:\n\"Serum CSTB no diff.\nbetween patients\nand controls\"",
    C_COUNTER, fontsize=7.5)
arrow(ax, 7.5, 3.7, 10, 3.0)

# ═══ Knowledge Gaps (bottom-left) ═══
box(ax, 2.5, 1.5, 5.0, 2.0,
    "Knowledge Gaps:\n[1] No tissue-level CSTB expression data in CRC\n[2] No immune infiltration correlation studies\n[3] No functional/mechanistic studies\n[4] No drug target screening for CSTB in CRC",
    C_GAP, fontsize=7.5)
arrow(ax, 6.5, 3.3, 3.5, 2.2)

# ═══ 4 Hard Rules (bottom strip) ═══
rules = [
    "Rule 1: strength={strong,moderate} requires >=1 PMID",
    "Rule 2: strength=\"strong\" cannot have counter-evidence",
    "Rule 3: strength_justification is mandatory",
    "Rule 4: Zero PMIDs + no counter → auto \"unverified\"",
]
for i, rule in enumerate(rules):
    ax.text(0.3, 0.8 - i*0.25, f"{rule}", fontsize=7, fontfamily="monospace", color="#555555",
            bbox=dict(boxstyle="round,pad=0.15", facecolor="#F5F5F5", edgecolor="#DDDDDD", alpha=0.8))

# ═══ Annotations ═══
ax.text(7, 5.6, "EvidenceLink Data Model", ha="center", fontsize=12, fontweight="bold", color="#333333")
ax.text(7, 5.35, "Fig 2 — Structured Evidence Chain with Built-in Contradiction Detection",
        ha="center", fontsize=9, color="#888888")

ax.text(0.3, 1.3, "Layer 2: Structural Constraint — __post_init__ validators",
        fontsize=8, fontstyle="italic", color="#999999")

plt.tight_layout(pad=1)
svg_path = Path(__file__).resolve().parent / "fig2_evidence_chain.svg"
png_path = Path(__file__).resolve().parent / "fig2_evidence_chain.png"
plt.savefig(svg_path, dpi=150, bbox_inches="tight", format="svg")
plt.savefig(png_path, dpi=150, bbox_inches="tight", format="png")
print(f"Saved: {svg_path}")
print(f"Saved: {png_path}")
