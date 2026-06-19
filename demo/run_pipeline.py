#!/usr/bin/env python
# run_pipeline.py — End-to-end demo: CSTB-CRC complete case study
#
# Per design/03-detailed-design.md demo script.
# Runs the full 4-Agent pipeline on a CSTB colorectal cancer question.
# Requires LLM API access (proxy up).

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.llm.client import LLMClient
from src.agents.pipeline import MultiAgentPipeline
from src.utils.network import ensure_network

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("demo")


def main():
    """Run the CSTB-CRC case study pipeline."""
    question = (
        "CSTB 在结直肠癌中的预后价值和免疫浸润关联 / "
        "CSTB in colorectal cancer: prognostic value and immune infiltration"
    )

    print("=" * 60)
    print("BioMed-Agent Step 3 — Multi-Agent Pipeline Demo")
    print("=" * 60)
    print(f"\nResearch question: {question}\n")

    # Check network
    try:
        ensure_network()
        print("[OK] Network available (proxy up)")
    except Exception as e:
        print(f"[WARN] Network check failed: {e}")
        print("      Attempting LLM call anyway...")

    # Initialize
    client = LLMClient()
    pipeline = MultiAgentPipeline(
        llm_client=client,
        config={
            "cache_index_path": "data/cache/analysis_cache_index.json",
            "pubmed_cache_dir": "data/pubmed_cache/",
        },
    )

    print(f"Pipeline initialized: {pipeline.name}")
    print(f"  - LiteratureAgent (S1): ready")
    print(f"  - OrchestrationAgent (A2): ready")
    print(f"  - AnalysisAgent (A3): ready (TCGA-COAD cache)")
    print(f"  - ReportAgent (A4): ready")
    print()

    # Run pipeline
    print("Running pipeline...")
    print("-" * 40)

    try:
        result = pipeline.run(question)

        print("-" * 40)
        print(f"\nPipeline complete!")
        print(f"  Literature: {result.literature_review.papers_retrieved} papers")
        print(f"  Analysis plan: {len(result.analysis_plan.nodes)} nodes")
        print(f"  Analysis results: {len(result.analysis_results)} nodes executed")
        degraded = sum(
            1 for r in result.analysis_results if r.status == "degraded"
        )
        failed = sum(
            1 for r in result.analysis_results if r.status == "failed"
        )
        print(f"    Completed: {len(result.analysis_results) - degraded - failed}")
        print(f"    Degraded: {degraded}")
        print(f"    Failed: {failed}")
        print(f"  Report: {len(result.report)} chars")
        print(f"  Tokens: {result.total_tokens}")
        print(f"  Layer 4 warnings: {len(result.layer4_warnings)}")
        for w in result.layer4_warnings:
            print(f"    - {w}")

        # Save output
        out_dir = Path(__file__).resolve().parent.parent / "data" / "demo_output"
        out_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = out_dir / f"pipeline_result_{timestamp}.json"

        # Serialize PipelineResult (simplified)
        output_data = {
            "question": result.question,
            "papers_retrieved": result.literature_review.papers_retrieved,
            "hypotheses": [
                {
                    "statement": h.statement,
                    "novelty": h.novelty,
                }
                for h in result.literature_review.hypotheses
            ],
            "n_analysis_nodes": len(result.analysis_plan.nodes),
            "n_results": len(result.analysis_results),
            "report": result.report[:500] + ("..." if len(result.report) > 500 else ""),
            "total_tokens": result.total_tokens,
            "execution_log": result.execution_log,
            "layer4_warnings": result.layer4_warnings,
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        print(f"\nOutput saved to: {out_path}")

    except Exception as e:
        logger.error("Pipeline failed: %s", e, exc_info=True)
        print(f"\n[ERROR] Pipeline failed: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
