# CLAUDE.md — biomed-agent/

## Project Status
- **S1** LiteratureAgent + RAG: ✅ Complete (11 files, design+impl+verify)
- **S2** Benchmark Framework: ✅ Complete (9 files, 102 tests, 5 GT datasets)
- **S3** Multi-Agent Pipeline: ✅ Complete (14 files, 58 tests, end-to-end run)
- **S4** Technical Report: ✅ Complete (report.md 673 lines/8 chapters/29 refs, 4 Mermaid figures Agnes QC PASS)
- **S5** Portfolio Packaging: ⬜ Pending

## Key Files
- Progress tracker: `PROGRESS.md`
- Design docs: `design/` (00-master-coordination.md through 04-outline.md)
- Report: `paper/report.md`
- Figures: `paper/figures/` (fig1/2/5/6 .mmd + .svg + .png)
- S3 pipeline output: `data/demo_output/pipeline_result_20260619_160414.json`
- Benchmark data: `results/benchmark_v1_*.json`

## Tooling
- Mermaid diagrams: `mermaid-cli` 11.15 + Puppeteer chromium via `PUPPETEER_EXECUTABLE_PATH` env var pointing to a chrome-headless-shell binary
- Figure QC: Agnes Vision API (agnes-2.0-flash)
- LLM: DeepSeek v4-pro via Anthropic SDK, thinking_budget_tokens=1600 default

## P0 Gaps (transparently tracked)
- P0-2: 4/6 figures (Fig 3/4/7/8 deferred per Data Generation Plan)
- P0-3: 29/30 references
- analysis_agent.py: 502 lines (2 over 500-line ceiling)
