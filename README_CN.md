# BioMed-Agent

**面向生物医学文献驱动多组学分析的多智能体系统。**

BioMed-Agent 通过四个协作智能体将自动化文献综述与多组学数据分析连接起来：LiteratureAgent（PubMed 检索 + 结构化证据整合）、OrchestrationAgent（LLM 驱动的动态分析规划）、AnalysisAgent（多组学执行 + 失败恢复）、ReportAgent（证据整合 + 交叉验证）。五层反幻觉防线覆盖提示工程、结构约束、后验验证、跨智能体验证和人工审查。

![系统架构](paper/figures/fig1_architecture.png)

---

## 🚀 快速开始

```bash
git clone https://github.com/Tubo2333/biomed-agent
cd biomed-agent
pip install -r requirements.txt
python demo/run_literature_review.py "CSTB 在结直肠癌中的预后价值"
```

这会运行 LiteratureAgent——它搜索 PubMed、按相关性排序论文、整合结构化证据链、生成可验证假设。输出写入 `data/demo_output/`。

运行完整的四智能体管线：

```bash
python demo/run_pipeline.py "CSTB 在结直肠癌中的预后价值与免疫浸润关联"
```

整个过程大约需要 5-6 分钟（大部分时间为 LLM API 耗时），产出 `PipelineResult`，包含文献综述、分析计划、多组学结果和结构化科研报告。

---

## 复现本工作

本项目是一个**研究型参考系统**——不是 pip 包、不是 SaaS 产品。它是一套完整垂直展示：设计 → 实现 → 评测 → 案例 → 技术报告。价值在于全局视野，而非一键执行。

### 开箱即用

```bash
# 结构测试 — 除了 numpy 零外部依赖
pip install numpy
python -m pytest tests/ -v --tb=short \
    --ignore=tests/test_s1_agent.py \
    --ignore=tests/test_s1_rag.py \
    --ignore=tests/test_runner.py \
    --ignore=tests/test_adversarial.py
```

约 130 个测试覆盖数据模型完整性、幻觉检测规则、benchmark 指标、工具兼容性检查。无需网络、无需 LLM、无需代理。

### 需要配置的部分

要运行完整的端到端 pipeline 或 benchmark：

| 依赖项 | 用途 | 配置方式 |
|--------|------|---------|
| **LLM API 访问** | 所有 Agent 推理（文献探员、规划师、实验师、主编）使用 LLM 调用 | 设置 `ANTHROPIC_AUTH_TOKEN` 和 `ANTHROPIC_BASE_URL` 环境变量，或配置 `~/.claude/settings.json`。默认模型：DeepSeek v4-pro（通过 Anthropic SDK）。换成其他 provider 只需改 `src/llm/client.py`。 |
| **代理（可选）** | 仅网络屏蔽 PubMed/LLM API 时需要 | 设置 `BIOMED_PROXY_HOST=127.0.0.1` 和 `BIOMED_PROXY_PORT=7892`。不设则所有网络调用直连，不做代理检查。 |
| **预计算分析缓存** | 实验师从 `data/cache/*.json` 读取差异表达和生存分析结果 | CSTB/TCGA-COAD 的缓存文件已包含。添加自己的基因或数据集：外部跑分析（R/Python），按缓存 JSON schema 保存结果（见 `data/cache/analysis_cache_index.json`），重新运行 pipeline。无缓存时实验师对该节点降级为 F4——不会编造数据。 |

### 环境注意事项

- **GFW 用户（中国）**：设置 `BIOMED_PROXY_HOST` 和 `BIOMED_PROXY_PORT`。PubMed API 和 LLM 端点无代理无法访问。
- **非 GFW 用户**：不需要代理。不设 `BIOMED_PROXY_*` 即可，网络调用直连。
- **Windows 用户**：`Rscript -e` 在此平台会 segfault。因此实验师使用预计算缓存而非实时调用 R。如需实时 R 执行，使用 Linux/macOS。
- **换用其他 LLM**：编辑 `src/llm/client.py`，将 Anthropic SDK 替换为 OpenAI、LiteLLM 或你偏好的 provider。LLM 客户端约 250 行，与系统其他部分隔离。

---

## 系统做什么

| 智能体 | 角色 | 输入 | 输出 |
|-------|------|------|------|
| **LiteratureAgent** | 多轮 PubMed 检索 → 证据链整合 → 假设生成 | 生物医学研究问题 | `LiteratureReview`（证据链 + 1-3 假设 + 知识缺口） |
| **OrchestrationAgent** | LLM 驱动的动态分析 DAG 生成 | `LiteratureReview` | `AnalysisPlan`（分析节点 DAG，非固定模板） |
| **AnalysisAgent** | Think→Act→Observe 多组学执行 + F1-F5 失败恢复 | `AnalysisPlan` + 真实数据 | `AnalysisResult` 列表（含 why/what/result 决策日志） |
| **ReportAgent** | 多源整合 + Layer 4 交叉验证 + 结构化报告 | 所有上游输出 | Markdown 报告（含强制阴性/零发现章节） |

管线**故意设计为串行**——每个智能体在进入下一步之前验证其上游输入（Layer 4 交叉验证）。这反映了自然的科研工作流（文献调研 → 实验设计 → 数据分析 → 撰写报告），并确保错误不会静默传播。

---

## 反幻觉：五层防线

幻觉在生物医学语境中尤其危险。BioMed-Agent 实现了五层防线：

| 层 | 机制 | 位置 |
|----|------|------|
| **L1** Prompt | 5 条硬约束嵌入每个 LLM system prompt（不虚构、溯来源、表不确定性、定量精确、报告阴性结果） | 所有 prompt 模板 |
| **L2** 结构 | `EvidenceLink` 数据类强制约束：每个主张必须有 supporting_pmid；`strength="strong"` 但有反面证据时拒绝创建 | `src/types.py` |
| **L3** 后验 | 程序化验证：PMID 存在性、基因名有效性、统计量合理性（HR 0.01-100, p 0-1）、跨主张一致性 | S1 synthesizer, S2 hallucination detector |
| **L4** 交叉验证 | 三个 `validate_upstream()` 节点：A2 查 A1（证据链内部一致性）、A3 查 A2（数据源存在性）、A4 查 A3（统计量合理性 + 跨节点矛盾 + 效应量） | S3 pipeline, report agent |
| **L5** 人工 | `hallucination_rate > 0.1` 或 `strength="strong"` 的输出标记 `[HUMAN REVIEW RECOMMENDED]` | 所有最终输出 |

---

## Benchmark

我们设计了一个面向生物医学智能体能力的标准化评测框架：**5 个任务 × 4 个维度 × 4 个基线**。

T3-DEG（差异表达分析，TCGA-COAD）上的初步对比：

| 智能体 | Overall Score | 幻觉标记 | 状态 |
|-------|--------------|---------|------|
| B1 Naive LLM（零-shot） | 0.637 | 1 | 完成（拒绝回答——正确识别无数据访问权限） |
| B2 ReAct | — | — | 崩溃（DeepSeek API tool-calling 不兼容） |
| B3 Simple RAG | 0.575 | 8 | 完成（单轮 PubMed 检索） |
| B4 Domain ReAct | — | — | 崩溃（与 B2 相同的 API 不兼容） |
| **BioMed-Agent S3 Pipeline** | — | — | 降级（pipeline 为端到端案例研究设计，非单任务 benchmark 模式） |

**关于这些数字的重要说明**：
- 这是单一数据集（TCGA-COAD）上的单任务对比，不可泛化。
- B2/B4 崩溃源于 DeepSeek 的 Anthropic 格式 API 不完全支持原生 tool-calling——BioMed-Agent 通过使用进程内 Python 工具避免了此问题。
- S3 pipeline 在 benchmark 模式下降级是预期行为：pipeline 的 Task Router 按 `task_id` 分派——T3-DEG/T4-SURV/T5-DRUG 跳过 Phase 1（LiteratureAgent），直接用 task input dict 进入 Phase 2+3。Pipeline 是为开放式研究问题（"研究 CSTB 在 CRC 中"）构建的，不是为孤立单任务 benchmark 拿高分而设计。其端到端能力体现在 CSTB 案例研究中，不在这里。
- 全量 agent×task 矩阵 benchmark（~150K tokens）尚未执行。评测框架已完整设计和实现（102 个结构测试通过）；上述 T3-DEG 对比是唯一可用的跨智能体定量数据。

详见 [BENCHMARK.md](BENCHMARK.md)——任务定义、ground truth 构建方法、指标公式、已知评测局限。

---

## 项目结构

```
biomed-agent/
├── src/
│   ├── types.py              # 共享数据类（Paper, EvidenceLink, Hypothesis 等）
│   ├── llm/client.py         # 统一 LLM 客户端（DeepSeek v4-pro, temperature=0.3）
│   ├── utils/network.py      # 代理检测 + 重试
│   ├── rag/                  # S1：文献 RAG pipeline
│   │   ├── retriever.py      #   PubMed EUtils + 缓存
│   │   ├── embedder.py       #   LLM Rerank（无 embedding 模型）
│   │   ├── synthesizer.py    #   EvidenceSynthesizer
│   │   └── hypothesis_generator.py
│   ├── agents/               # S1 + S3：智能体实现
│   │   ├── literature_agent.py
│   │   ├── orchestration_agent.py
│   │   ├── analysis_agent.py
│   │   ├── report_agent.py
│   │   └── pipeline.py       #   四智能体编排器
│   ├── benchmark/            # S2：评测框架
│   │   ├── tasks.py          #   5 个任务定义 + ground truth 加载
│   │   ├── metrics.py        #   4 维指标计算
│   │   ├── hallucination.py  #   硬规则 + 软分级 + 方法学白名单
│   │   ├── baselines.py      #   B1-B4 基线智能体
│   │   ├── runner.py         #   BiomedBenchmark 主循环
│   │   └── reporter.py       #   Z-score 归一化 + 导出
│   └── tools/                # S3：多组学分析工具
│       ├── tcga_tools.py     #   三层数据访问（缓存 → 实时 Python → F4 降级）
│       ├── survival_tools.py #   Cox 回归 + KM（缓存优先 + F3 PH 违反降级）
│       ├── drug_tools.py     #   GDSC2 Spearman 相关 + BH FDR
│       └── immune_tools.py   #   免疫浸润相关性
├── tests/                    # 160 个测试（覆盖 S1/S2/S3）
├── data/
│   ├── benchmark/ground_truth/  # 5 个任务的 GT JSON 文件
│   ├── cache/                   # 预计算分析缓存
│   └── demo_output/             # Pipeline 运行输出
├── paper/
│   ├── report.md             # 完整技术报告（8 章，中英双语）
│   └── figures/              # 架构、证据链、时间线、网络图
├── demo/                     # 可运行的端到端脚本
├── design/                   # 设计文档（00- 至 05-）
├── BENCHMARK.md              # Benchmark 设计文档
├── ARCHITECTURE.md            # 架构深度解读
├── CASE_STUDY.md              # CSTB-CRC 完整走读
├── FAQ.md                     # 设计决策问答
└── PROGRESS.md                # 项目状态追踪
```

---

## 深入阅读

- [ARCHITECTURE.md](ARCHITECTURE.md) — 系统架构、智能体设计、反幻觉层详解
- [BENCHMARK.md](BENCHMARK.md) — 评测框架：任务定义、ground truth 构建、指标、基线
- [CASE_STUDY.md](CASE_STUDY.md) — CSTB 在结直肠癌中：完整端到端走读，真实数据
- [paper/report.md](paper/report.md) — 完整技术报告（8 章，中英双语，29 篇参考文献）
- [FAQ.md](FAQ.md) — 设计决策与权衡问答
- [PROGRESS.md](PROGRESS.md) — 已完成、已延期、已知问题的追踪

---

## 已知局限

这些不藏在讨论章节里。评估这个系统请从这里开始：

1. **单队列、单案例**：所有多组学分析使用 TCGA-COAD（n=303）。CSTB 是唯一完整运行的案例研究。结果不可推广到其他癌种或基因。
2. **Benchmark 未全量运行**：5 task × 4 agent 的评测框架已完整实现（102 个结构测试通过），但仅 T3-DEG 有定量跨智能体对比数据。全量运行需 ~150K tokens。
3. **预计算缓存限制了分析灵活性**：差异表达和生存分析从预计算 JSON 缓存中提供结果。AnalysisAgent 可以执行缓存中存在的任何分析，但非标准方法或未缓存的基因会降级为 F4（数据不可用）。这是有意的架构选择——它避免了 Windows Rscript segfault、消除了子进程复杂度、保持了低 demo 延迟。代价是智能体的分析范围被预计算内容所限制。详见 [FAQ.md](FAQ.md#3-为什么预计算缓存而不是实时跑-r)。
4. **CSTB 缓存数据是错的——不是缓存方案的问题，是数据管线 bug**：缓存的 CSTB 在 TCGA-COAD 中 logFC 为 0.073（基本持平），但已发表研究一致报告 logFC ≈ 2.3（肿瘤中显著上调）。这不是缓存架构的固有问题——这意味着缓存生成时使用了错误的标准化或样本分组。这是一个 bug，不是 trade-off。我们尚未根因定位。案例研究和报告中凡是出现这个数字的地方都做了明确标注。
5. **DeepSeek API thinking 模式的 token 压力**：DeepSeek v4-pro thinking mode 消耗大量 `max_tokens` 预算，偶尔导致 JSON 截断。已设 `thinking_budget_tokens=1600` 作为默认缓解措施，但长响应（特别是证据整合）仍可能触及上限。
6. **无并发**：四智能体管线故意设计为串行。对科研工作流而言这是自然的（文献→设计→执行→写作），但意味着挂钟时间随 LLM API 延迟线性增长。

---

## 引用

```bibtex
@article{biomed-agent-2026,
  title = {BioMed-Agent: A Multi-Agent System for Biomedical Literature-Grounded Multi-Omics Analysis},
  author = {},
  year = {2026},
  note = {Technical report. Repository: https://github.com/Tubo2333/biomed-agent}
}
```

## 许可证

MIT
