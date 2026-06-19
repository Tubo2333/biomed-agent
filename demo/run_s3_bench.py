#!/usr/bin/env python
"""Run S3 MultiAgentPipeline on T3-DEG benchmark task.
Task Router skips Phase 1 (no PubMed), uses cached TCGA-COAD data directly.
This gives us the direct comparison: BioMed-Agent vs baselines on the same task."""

import json, logging, sys, time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.llm.client import LLMClient
from src.agents.pipeline import MultiAgentPipeline
from src.benchmark.tasks import load_all_tasks
from src.utils.network import ensure_network

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("s3_bench")

def main():
    try:
        ensure_network()
        print("[OK] Proxy up")
    except Exception as e:
        print(f"[WARN] {e}")

    llm = LLMClient()
    pipeline = MultiAgentPipeline(
        llm_client=llm,
        config={"cache_index_path": "data/cache/analysis_cache_index.json"},
    )
    print(f"Pipeline: {pipeline.name}")

    tasks = load_all_tasks()
    deg_task = next(t for t in tasks if t.task_id == "T3-DEG")

    t0 = time.time()
    print(f"\nRunning S3 pipeline on {deg_task.task_id}...")
    try:
        # S3 pipeline implements EvalAgent protocol: run(BenchmarkTask) -> dict
        result = pipeline.run(deg_task)
        dt = round(time.time() - t0, 1)
        print(f"  Duration: {dt}s")
        print(f"  Output keys: {list(result.keys()) if isinstance(result, dict) else type(result).__name__}")
        if isinstance(result, dict):
            print(f"  Answer preview: {str(result.get('answer', result.get('report', '')))[:300]}")
        elif hasattr(result, 'analysis_results'):
            print(f"  Analysis nodes: {len(result.analysis_results)}")
            for r in result.analysis_results:
                print(f"    {r.node_id}: {r.status} — {str(r.output)[:100]}")

        # Save
        out_dir = Path(__file__).resolve().parent.parent / "results"
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = out_dir / f"s3_benchmark_{ts}.json"
        output_data = {
            "run_at": ts, "task": "T3-DEG", "agent": "MultiAgentPipeline",
            "duration_s": dt,
            "result_type": type(result).__name__,
        }
        if isinstance(result, dict):
            output_data.update({
                k: str(v)[:500] for k, v in result.items()
                if k not in ('execution_log',)
            })
        elif hasattr(result, 'analysis_results'):
            output_data["n_results"] = len(result.analysis_results)
            output_data["report_preview"] = result.report[:500] if hasattr(result, 'report') else 'N/A'
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        print(f"\nSaved to: {out_path}")

    except Exception as e:
        dt = round(time.time() - t0, 1)
        print(f"  [FAILED after {dt}s]: {e}")
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())
