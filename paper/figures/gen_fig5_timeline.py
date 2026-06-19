"""Generate Fig 5: Agent Decision Timeline — clean horizontal Gantt-style chart.
Outputs SVG and PNG."""

import json
from pathlib import Path
import matplotlib
matplotlib.use("SVG")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

DATA = Path(__file__).resolve().parent.parent.parent / "data/demo_output/pipeline_result_20260619_160414.json"
with open(DATA, encoding="utf-8") as f:
    result = json.load(f)

log = result["execution_log"]

# Build phases from log, merging L4 gates into adjacent phases
phases = []
for entry in log:
    phase = entry.get("phase", "")
    agent = entry.get("agent", "")
    duration = entry.get("duration_s", 0)
    if isinstance(phase, str) and ("L4" in phase or "coverage" in phase):
        continue  # L4 gates are sub-second, skip for visual clarity
    if duration > 0:
        phases.append({
            "agent": agent,
            "duration": duration,
            "details": entry,
        })

# Colors
colors = ["#00B07C", "#E84040", "#0395D8", "#7B1FA2"]
labels_cn = [
    "Phase 1\nLiteratureAgent\nPubMed + Evidence Synthesis",
    "Phase 2\nOrchestrationAgent\nLLM Dynamic DAG Planning",
    "Phase 3\nAnalysisAgent\nMulti-Omics Execution",
    "Phase 4\nReportAgent\nStructured Report Generation",
]

fig, ax = plt.subplots(figsize=(14, 4))

cumulative = 0
bar_height = 0.5
y_positions = [1, 1, 1, 1]  # all on same row

for i, (p, color, label) in enumerate(zip(phases, colors, labels_cn)):
    d = p["duration"]
    # Draw bar
    ax.barh(1, d, bar_height, left=cumulative, color=color, edgecolor="white", linewidth=2)
    # Duration label inside bar
    if d > 30:
        ax.text(cumulative + d/2, 1, f"{d:.0f}s", ha="center", va="center",
                fontsize=10, fontweight="bold", color="white")
    else:
        ax.text(cumulative + d + 2, 1, f"{d:.0f}s", ha="left", va="center",
                fontsize=9, fontweight="bold", color=color)
    # Phase label above bar
    ax.text(cumulative + d/2, 1.35, label, ha="center", va="bottom",
            fontsize=8.5, fontweight="bold", color=color)
    cumulative += d

# Total
ax.axvline(x=cumulative, color="black", linewidth=1.5, linestyle="--")
ax.text(cumulative + 3, 0.7, f"Total: {cumulative:.0f}s (≈{cumulative/60:.1f} min)",
        fontsize=10, fontweight="bold", color="#333333")

# Decoration
ax.set_ylim(0.3, 1.8)
ax.set_xlim(-10, cumulative * 1.18)
ax.set_yticks([])
ax.set_xlabel("Elapsed Time (seconds)", fontsize=11, labelpad=10)
ax.set_title("BioMed-Agent: CSTB Case Study — Agent Execution Timeline\nFig 5 — S3 MultiAgentPipeline, 2026-06-19\n4 Agents, 4 Analysis Nodes, 334s Total",
             fontsize=12, fontweight="bold", pad=15)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.spines["left"].set_visible(False)
ax.grid(axis="x", alpha=0.25, linewidth=0.5)

plt.tight_layout(pad=1.5)

# Save SVG
svg_path = Path(__file__).resolve().parent / "fig5_timeline.svg"
plt.savefig(svg_path, dpi=150, bbox_inches="tight", format="svg")
print(f"SVG saved: {svg_path}")

# Save PNG
png_path = Path(__file__).resolve().parent / "fig5_timeline.png"
plt.savefig(png_path, dpi=150, bbox_inches="tight", format="png")
print(f"PNG saved: {png_path}")
