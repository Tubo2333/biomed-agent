#!/usr/bin/env python
"""Focused benchmark: B1/B2/B3/B4 on T3-DEG (differential expression).
Compares baseline strategies on a concrete analysis task using cached data.
Fast path — no multi-round literature search."""

import json, logging, sys, time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.llm.client import LLMClient
from src.benchmark.runner import BiomedBenchmark
from src.benchmark.baselines import NaiveLLM, ReActAgent, SimpleRAGAgent, DomainReActAgent
from src.benchmark.tasks import load_all_tasks
from src.utils.network import ensure_network

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("focus_bench")

def main():
    try:
        ensure_network()
        print("[OK] Proxy up")
    except Exception as e:
        print(f"[WARN] {e}")

    llm = LLMClient()

    agents = [
        ("B1_NaiveLLM", NaiveLLM(llm_client=llm)),
        ("B2_ReAct", ReActAgent(llm_client=llm)),
        ("B3_SimpleRAG", SimpleRAGAgent(llm_client=llm)),
        ("B4_DomainReAct", DomainReActAgent(llm_client=llm)),
    ]

    tasks = load_all_tasks()
    deg_task = next(t for t in tasks if t.task_id == "T3-DEG")
    print(f"\nTask: {deg_task.task_id} — {deg_task.description}")
    print(f"GT genes: {[g['gene'] for g in deg_task.ground_truth.get('genes', [])]}")
    print(f"Tolerance: logFC ±{deg_task.ground_truth.get('meta',{}).get('tolerance',{}).get('logFC','?')}")
    print()

    benchmark = BiomedBenchmark({"random_seed": 42})
    results = []

    for label, agent in agents:
        t0 = time.time()
        print(f"{'='*50}")
        print(f"Agent: {label}")
        try:
            metrics = benchmark.run_single(agent, deg_task)
            dt = round(time.time() - t0, 1)
            r = {
                "agent": label,
                "task": "T3-DEG",
                "completion": round(metrics.task_completion_rate, 3),
                "tool_selection": round(metrics.tool_selection_accuracy, 3),
                "correctness": round(metrics.result_correctness, 3),
                "hallucination": round(metrics.hallucination_rate, 3),
                "safety": round(metrics.safety_score, 3),
                "overall": round(metrics.overall_score_raw, 3),
                "trust": metrics.trust_label,
                "duration_s": dt,
                "details": str(metrics.details)[:500],
            }
            results.append(r)
            print(f"  Completion: {r['completion']:.3f}")
            print(f"  Tool Select: {r['tool_selection']:.3f}")
            print(f"  Correctness: {r['correctness']:.3f}")
            print(f"  Hallucination: {r['hallucination']:.3f}")
            print(f"  Safety: {r['safety']:.3f}")
            print(f"  Overall: {r['overall']:.3f}")
            print(f"  Trust: {r['trust']}")
            print(f"  Duration: {dt}s")
        except Exception as e:
            dt = round(time.time() - t0, 1)
            print(f"  [FAILED after {dt}s]: {e}")
            results.append({"agent": label, "task": "T3-DEG", "error": str(e), "duration_s": dt})

    # Save results
    out_dir = Path(__file__).resolve().parent.parent / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"benchmark_v1_{ts}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "run_at": ts,
            "task": "T3-DEG",
            "gt_summary": {
                "genes": deg_task.ground_truth.get("genes", []),
                "tolerance": deg_task.ground_truth.get("meta", {}).get("tolerance", {}),
            },
            "results": results,
        }, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to: {out_path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
