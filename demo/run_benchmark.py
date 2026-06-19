#!/usr/bin/env python
"""Quick benchmark run — LiteratureAgent + B1 vs selected tasks.
Saves results for S4 report."""

import json, logging, sys, time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.llm.client import LLMClient
from src.agents.literature_agent import LiteratureAgent
from src.benchmark.runner import BiomedBenchmark
from src.benchmark.baselines import NaiveLLM, ReActAgent, SimpleRAGAgent, DomainReActAgent
from src.benchmark.tasks import load_all_tasks
from src.utils.network import ensure_network

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("run_benchmark")

def main():
    # Check network
    try:
        ensure_network()
        print("[OK] Network available")
    except Exception as e:
        print(f"[WARN] Network: {e}")

    llm = LLMClient()

    # Create agents
    lit_agent = LiteratureAgent(llm_client=llm, config={})
    b1 = NaiveLLM(llm_client=llm)
    b2 = ReActAgent(llm_client=llm)       # has tool support
    b3 = SimpleRAGAgent(llm_client=llm)    # has PubMed search
    b4 = DomainReActAgent(llm_client=llm)  # domain knowledge

    agents = [lit_agent, b1, b2, b3, b4]

    # Load tasks — run T1-LIT (literature) and T3-DEG (expression) first
    tasks = load_all_tasks()
    print(f"Loaded {len(tasks)} tasks: {[t.task_id for t in tasks]}")

    # Filter to a quick subset for initial data
    quick_tasks = [t for t in tasks if t.task_id in ("T1-LIT", "T3-DEG")]
    print(f"Running quick benchmark: {[t.task_id for t in quick_tasks]}")

    # Override run_all's task loading by patching
    benchmark = BiomedBenchmark({"random_seed": 42})

    results_data = []
    start = time.time()

    # Manual run — agent × task
    for agent in agents:
        for task in quick_tasks:
            t0 = time.time()
            print(f"\n{'='*50}")
            print(f"Agent: {agent.name}   Task: {task.task_id}")
            print(f"{'='*50}")
            try:
                metrics = benchmark.run_single(agent, task)
                dt = round(time.time() - t0, 1)
                print(f"  Completion: {metrics.task_completion_rate:.2f}")
                print(f"  Correctness: {metrics.result_correctness:.2f}")
                print(f"  Hallucination: {metrics.hallucination_rate:.2f}")
                print(f"  Overall: {metrics.overall_score_raw:.2f}")
                print(f"  Trust: {metrics.trust_label}")
                print(f"  Duration: {dt}s")
                results_data.append({
                    "agent": agent.name,
                    "task": task.task_id,
                    "completion": metrics.task_completion_rate,
                    "correctness": metrics.result_correctness,
                    "hallucination": metrics.hallucination_rate,
                    "overall": metrics.overall_score_raw,
                    "trust": metrics.trust_label,
                    "duration_s": dt,
                })
            except Exception as e:
                dt = round(time.time() - t0, 1)
                print(f"  [FAILED after {dt}s]: {e}")
                results_data.append({
                    "agent": agent.name,
                    "task": task.task_id,
                    "error": str(e),
                    "duration_s": dt,
                })

    total = round(time.time() - start, 1)
    print(f"\n{'='*50}")
    print(f"Benchmark complete in {total}s ({total/60:.1f} min)")
    print(f"Results: {len(results_data)} agent×task pairs")

    # Save
    out_dir = Path(__file__).resolve().parent.parent / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"benchmark_v1_{ts}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "run_at": ts,
            "agents": [a.name for a in agents],
            "tasks": [t.task_id for t in quick_tasks],
            "results": results_data,
            "total_duration_s": total,
        }, f, ensure_ascii=False, indent=2)
    print(f"Saved to: {out_path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
