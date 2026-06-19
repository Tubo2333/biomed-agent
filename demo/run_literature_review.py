#!/usr/bin/env python
# run_literature_review.py — LiteratureAgent 端到端 Demo
#
# Usage:
#   python demo/run_literature_review.py "CSTB in colorectal cancer prognosis"
#   python demo/run_literature_review.py --interactive
#
# Output: LiteratureReview JSON → data/demo_output/<timestamp>/

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.llm.client import LLMClient
from src.agents.literature_agent import LiteratureAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

OUTPUT_DIR = Path("data/demo_output")


def run_demo(question: str) -> None:
    """运行单次文献调研并保存结果。"""
    client = LLMClient()
    agent = LiteratureAgent(client)

    print(f"\n{'='*60}")
    print(f"LiteratureAgent Demo")
    print(f"Question: {question}")
    print(f"{'='*60}\n")

    review = agent.run(question)

    # ── 保存 ──
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = OUTPUT_DIR / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    output = {
        "question": review.query,
        "papers_retrieved": review.papers_retrieved,
        "papers_relevant_count": len(review.papers_relevant),
        "evidence_summary": review.evidence_summary,
        "confidence": review.confidence,
        "knowledge_gaps": review.knowledge_gaps,
        "citations": review.citations,
        "token_usage": review.token_usage,
        "evidence_chain": [
            {
                "claim": link.claim,
                "supporting_pmids": link.supporting_pmids,
                "strength": link.strength,
                "counter_evidence": link.counter_evidence,
            }
            for link in review.evidence_chain
        ],
        "hypotheses": [
            {
                "statement": h.statement,
                "testable_prediction": h.testable_prediction,
                "novelty": h.novelty,
                "required_data": h.required_data,
            }
            for h in review.hypotheses
        ],
    }

    json_path = out_dir / "literature_review.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # ── 控制台摘要 ──
    print(f"Papers: {review.papers_retrieved} retrieved, "
          f"{len(review.papers_relevant)} relevant")
    print(f"Claims: {len(review.evidence_chain)}")
    for link in review.evidence_chain:
        print(f"  [{link.strength}] {link.claim[:120]}")
    print(f"\nHypotheses: {len(review.hypotheses)}")
    for h in review.hypotheses:
        print(f"  [{h.novelty}] {h.statement[:120]}")
    print(f"\nConfidence: {review.confidence:.2f}")
    print(f"Knowledge gaps: {len(review.knowledge_gaps)}")
    print(f"Token usage: {review.token_usage}")
    print(f"\nSaved to: {json_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="LiteratureAgent — Biomedical Literature Review Demo"
    )
    parser.add_argument(
        "question",
        nargs="?",
        default="CSTB as a prognostic biomarker in colorectal cancer",
        help="Biomedical research question",
    )
    args = parser.parse_args()

    try:
        run_demo(args.question)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(1)
