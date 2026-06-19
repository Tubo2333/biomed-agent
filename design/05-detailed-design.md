# 05 — Step 5 详细设计文档：项目可理解性与可复现性

> **状态**：Stage 1 设计深化 — DRAFT
> **作者**：项目维护者
> **依赖**：`00-master-coordination.md` §二（共享类型）、§四（设计哲学）；S1-S4 全部产出
> **目标**：让任何一个想理解、使用、复现这个系统的人（研究者、工程师、学生），能在最短时间内搞清楚它做了什么、怎么跑、有什么局限。不是"包装给面试官看"，而是"把项目交到别人手上"。

---

## 〇、设计基准修正

05-portfolio-packaging.md 的原始叙事围绕"面试展示"组织——30秒法则、HR眼球轨迹、JD关键词覆盖率。这会导致不自觉地 cherry-pick、弱化局限、过度营销。

**S5 修正后的基准**：

> 一个陌生开发者 clone 这个仓库后，能否在不问你任何问题的情况下：
> - 5 分钟内知道这个项目是什么
> - 10 分钟内跑出第一个结果
> - 30 分钟内理解核心架构和设计决策
> - 需要深挖时能找到完整的技术报告和原始数据

所有 S5 产出都以此为目标。面试展示是这个目标自然达成的附带效果，不是目标本身。

---

## 一、MODULE BREAKDOWN（交付物清单）

### 文件清单（共 8 个交付物）

```
biomed-agent/
├── README.md                           # 项目入口（英文，30秒可理解）
├── README_CN.md                        # 中文入口（GOV-005 双语要求）
├── ARCHITECTURE.md                     # 系统架构深度说明
├── BENCHMARK.md                        # 评测框架说明（S2 已产出，需审查更新）
├── CASE_STUDY.md                       # CSTB-CRC 完整案例走读
├── FAQ.md                              # 设计决策与技术细节问答
├── presentation/
│   └── biomed-agent-overview.pptx      # 技术演讲幻灯片
├── .github/
│   └── workflows/
│       └── ci.yml                      # CI 配置（lint + test）
└── (更新) package.json                 # 补充项目元数据
```

### 各交付物职责与依赖

| # | 交付物 | 单一职责 | 规模 | 依赖的 S1-S4 产出 |
|---|--------|---------|------|------------------|
| 1 | `README.md` | 项目入口：是什么→怎么装→怎么跑→核心数据→去哪深挖 | ≤200 行 | Fig1 + T3-DEG benchmark + report.md |
| 2 | `README_CN.md` | 中文版入口，内容与 README.md 对等 | ≤200 行 | 同上 |
| 3 | `ARCHITECTURE.md` | 4 Agent 协作架构 + 反幻觉五层防线 + 关键设计决策 | ≤300 行 | 03-detailed-design + 00B + 00- §六决策日志 |
| 4 | `BENCHMARK.md` | 5 task × 4 metric × 4 baseline 的设计、GT来源、已知局限 | 已存在 | S2 实现 + GT JSON + T3-DEG 运行结果 |
| 5 | `CASE_STUDY.md` | CSTB-CRC 从文献到发现的端到端走读，每一步可追溯 | ≤400 行 | pipeline_result JSON + Fig5/6 + S3 execution_log |
| 6 | `FAQ.md` | 设计决策问答：为什么不用LangChain、为什么缓存路线、已知局限 | ≤200 行 | 00- §六 17条决策 + S1-S4 实际运行发现 |
| 7 | `presentation/biomed-agent-overview.pptx` | 12 张幻灯片，给技术听众的结构化讲解 | 12 slides | Fig1/2/5/6 + benchmark + case study 数据 |
| 8 | `.github/workflows/ci.yml` | lint（ruff）+ pytest（160 tests） | ≤60 行 | tests/ 目录 |

**不需要的内容**（原 05- 中建议但 S5 不做）：
- ~~简历项目描述~~：那是个人材料，不是项目的一部分
- ~~面试 Q&A 文档~~：替换为 FAQ.md（面向所有理解者，不限于面试场景）
- ~~GitHub Pages~~：P2 可选，S5 不强制
- ~~Demo video~~：P2 可选，S5 不强制

---

## 二、DATA MODEL SPEC（内容结构规格）

### 2.1 README.md 内容规格

```markdown
# BioMed-Agent
## 一句话：Multi-agent system for biomedical literature-grounded multi-omics analysis

[架构图 Fig1 — 弓形布局，4 Agent 协作全景]

[Badges: Python 3.12+ | Tests 160 passing | License MIT]

## 🚀 Quick Start（5 行命令出第一个结果）
```bash
git clone https://github.com/Tubo2333/biomed-agent
cd biomed-agent
pip install -r requirements.txt
python demo/run_literature_review.py --question "CSTB in colorectal cancer prognosis"
```
→ 产出 LiteratureReview JSON（真实 PMID + 证据链 + 假设）

## 📊 What It Does（核心能力，一张表）
| Agent | 做什么 | 输入 | 输出 |
|--------|------|------|------|
| LiteratureAgent | PubMed多轮检索 + 结构化证据整合 + 假设生成 | 生物医学问题 | LiteratureReview (证据链+1-3假设) |
| OrchestrationAgent | LLM驱动的动态分析DAG生成 | LiteratureReview | AnalysisPlan (DAG) |
| AnalysisAgent | Think→Act→Observe 多组学分析执行 + F1-F5失败恢复 | AnalysisPlan | AnalysisResults (含决策日志) |
| ReportAgent | 多源整合 + Layer 4交叉验证 + 结构化报告 | 所有上游输出 | Markdown报告 (含阴性结果+局限性) |

## 📈 Key Results（来自 S2 benchmark + S3 pipeline）
T3-DEG任务对比（TCGA-COAD 差异表达分析）：
| Agent | Overall Score | Hallucination Flags | Notes |
|-------|--------------|-------------------|-------|
| B1 Naive LLM | 0.637 | 0 | 零-shot, 无工具 |
| B3 Simple RAG | 0.575 | 8 | 单轮PubMed检索 |
| B2/B4 ReAct | crash | N/A | DeepSeek API tool-calling 不兼容 |
| S3 Pipeline | success (17.4s) | 0 | 进程内Python工具+三层缓存 |

## 🔍 Want to Go Deeper?
- [ARCHITECTURE.md](ARCHITECTURE.md) — 系统架构和反幻觉设计
- [BENCHMARK.md](BENCHMARK.md) — 评测框架设计和GT构建方法
- [CASE_STUDY.md](CASE_STUDY.md) — CSTB-CRC 完整端到端走读
- [paper/report.md](paper/report.md) — 完整技术报告（8章, 中英双语）
- [FAQ.md](FAQ.md) — 设计决策问答

## 📝 Known Limitations（诚实前置，不在文档深处藏）
1. 全量 benchmark 未运行（~150K tokens），当前仅 T3-DEG 有定量对比数据
2. 预计算缓存路线限制了非标准分析的灵活性
3. TCGA-COAD 单队列，结果不可泛化
4. CSTB 缓存数据与 GT 有差异（logFC=0.073 vs GT logFC=2.3）

## 📄 License / Citation
MIT. 引用见 [paper/report.md](paper/report.md) 或 CITATION.cff
```

### 2.2 ARCHITECTURE.md 内容规格

```markdown
# BioMed-Agent Architecture

## 整体架构（Fig1）
[插入 Fig1 弓形架构图]

## 数据流
User Question → A1 LiteratureAgent → A2 OrchestrationAgent → A3 AnalysisAgent → A4 ReportAgent
每个 Agent 间有 Layer 4 交叉验证节点（A2→A1, A3→A2, A4→A3）

## 四个 Agent

### LiteratureAgent（S1）
- Think→Act→Observe 多轮检索（max 3轮）
- 三道闸门：max_rounds=3 / 查询去重 / token预算=15000
- LLM Rerank（无 embedding 模型）
- EvidenceSynthesizer → 结构化证据链
- HypothesisGenerator → 1-3 可验证假设

### OrchestrationAgent（S3）
- LLM 驱动动态 DAG 生成（非硬编码模板）
- Hypothesis 分类：single_gene / pathway_mechanism / multi_gene_drug
- 方法兼容矩阵后处理校验
- Anti-template 机制：每个节点强制 rationale 字段

### AnalysisAgent（S3）
- Think→Act→Observe 分析执行
- 三层数据访问：缓存查询 → 实时Python → F4降级
- F1-F5 失败恢复体系
- 决策日志：why/what/result 全记录

### ReportAgent（S3）
- 多源整合：LiteratureReview + AnalysisPlan + AnalysisResults
- Layer 4 交叉验证（A4→A3）：统计量合理性/跨节点矛盾/效应量阈值/覆盖率
- 强制 Negative and Null Findings 节

## 反幻觉五层防线
| Layer | 机制 | 实现位置 |
|-------|------|---------|
| L1 Prompt | 5条硬约束嵌入所有 LLM system prompt | 全部 prompt 模板 |
| L2 结构 | EvidenceLink.__post_init__ 4条硬矛盾检测 | S1 types.py |
| L3 后验 | PMID存在性/基因名/统计量/一致性 程序化检查 | S1 synthesizer.py + S2 hallucination.py |
| L4 交叉验证 | 3个 validate_upstream() 节点，规则为主 | S3 pipeline.py + report_agent.py |
| L5 人工 | strong claims 标记 [HUMAN REVIEW RECOMMENDED] | S4 report |

## 关键设计决策（完整列表见 FAQ.md）
- 为什么不用 embedding 模型而用 LLM Rerank
- 为什么预计算缓存而不是实时跑 R
- 为什么 4 Agent 串行而不是并发
- 为什么 Safety 用连续惩罚而不是硬门槛
```

### 2.3 CASE_STUDY.md 内容规格

```markdown
# Case Study: CSTB in Colorectal Cancer

## 研究问题
"CSTB 在结直肠癌中的预后价值和免疫浸润关联"

## Phase 1: 文献调研（LiteratureAgent）
- 检索论文数 / 相关论文数
- 证据链摘要（从 pipeline_result JSON 提取）
- 生成的假设（1-3 条）

## Phase 2: 分析规划（OrchestrationAgent）
- LLM 生成的 DAG 结构（节点列表 + 拓扑边）
- 每个节点为什么被选择（rationale）

## Phase 3: 分析执行（AnalysisAgent）
- 差异表达结果（logFC, adj.P — 标注缓存 vs GT 差异）
- 生存分析结果（HR, p-value）
- 免疫关联结果（或标注 degraded）
- 药物筛选结果
- 每个节点的执行状态（completed/degraded/failed）

## Phase 4: 报告生成（ReportAgent）
- Layer 4 交叉验证产生的 WARNING
- 报告中的关键定量发现
- 报告的局限性和阴性结果

## 完整数据
- 原始 PipelineResult JSON: `data/demo_output/pipeline_result_20260619_160414.json`
- 执行时间线: [Fig5]
- 文献证据网络: [Fig6]

## 已知问题
- 缓存 logFC=0.073 与 GT logFC=2.3 存在显著差异（数据管线问题）
- immune_correlation 节点因无缓存数据被标记为 degraded (F4)
- 单案例，不可泛化
```

### 2.4 FAQ.md 内容规格

覆盖的设计决策问答（至少 10 条）：

```
1. 为什么不用 LangChain 或 AutoGen？
→ DAG 驱动 vs 对话驱动；可审计性 vs 对话灵活性

2. 为什么用 LLM Rerank 而不是 embedding 模型？
→ 无 GPU、零额外依赖、语义理解足够（D-001）

3. 为什么预计算缓存而不是实时跑 R？
→ Windows Rscript segfault 风险；demo 不需要等 R 跑完（D-013）

4. 为什么 4 Agent 串行而不是并发？
→ 科研工作流天然顺序；交叉验证需要上游完成（D-004, D-016）

5. Safety 连续惩罚怎么设计的？
→ penalty=1.0-max(0,(0.7-safety)/0.7)，无 cliff effect（D-010）

6. Ground truth 怎么构建的？有偏吗？
→ 半自动混合路线；GT 非共识金标准，有透明声明（D-007, S2 附录B）

7. 系统最大的已知局限是什么？
→ 单队列(TCGA-COAD)、benchmark 未全量运行、预计算缓存限制灵活性

8. 为什么 DeepSeek 而不是 Claude/GPT？
→ 已有 ANTHROPIC_BASE_URL 配置，thinking_mode 适合多步推理

9. 整个 pipeline 跑一次要多久？
→ CSTB case study: 334 秒（含 LLM 调用）；不含 LLM 时 < 30 秒

10. 怎么保证 Agent 不编造引用？
→ Layer 2 结构约束（EvidenceLink 4条硬检测）+ Layer 3 PMID 存在性检查 + Layer 4 交叉验证
```

### 2.5 PPT 内容规格（12 张幻灯片）

| # | 标题 | 内容 | 数据来源 |
|---|------|------|---------|
| 1 | 标题 | BioMed-Agent + 一句话 + 仓库地址 | — |
| 2 | 问题 | 生物医学研究的数据-文献碎片化 | — |
| 3 | 方案概览 | 4 Agent 协作架构图（Fig1 简化版） | Fig1 |
| 4 | LiteratureAgent | PubMed→RAG→证据链→假设 | S1 数据 |
| 5 | **技术深潜：结构化证据链** | EvidenceLink 数据模型 + 反幻觉五层防线 | S1/S4 Fig2 |
| 6 | OrchestrationAgent | LLM 驱动动态 DAG + 假设分类 | S3 数据 |
| 7 | AnalysisAgent | Think→Act→Observe + F1-F5 + 三层缓存 | S3 数据 |
| 8 | ReportAgent + 交叉验证 | Layer 4 三节点 + 效应量检查 | S3 数据 |
| 9 | Benchmark | T3-DEG 对比结果 + 5 task × 4 metric 框架 | S2/S4 Table2 |
| 10 | CSTB Case Study | 端到端走读，每个 Phase 关键发现 | S3 pipeline_result |
| 11 | 已知局限 | 单队列/缓存差异/benchmark未全量/不可泛化 | S4 Discussion |
| 12 | 总结 + 链接 | 核心发现 + GitHub + 报告 PDF | — |

**PPT 制作方式**：复用 Harness_Engineer 的 build-ppt.js（PptxGenJS）模板，warm navy + coral 配色。优先用 SVG 嵌入保证清晰度。

### 2.6 CI 配置规格

```yaml
name: CI
on: [push, pull_request]
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install ruff
      - run: ruff check src/ tests/
  
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -r requirements.txt
      - run: python -m pytest tests/ -v --tb=short
```

注意：CI 中不跑需要 LLM API/代理的测试（那些测试本地跑）。

---

## 三、INTERFACE SPEC（与 S1-S4 产出的对接）

### 每个交付物消费的 S1-S4 数据

| 交付物 | 消费的 S1-S4 产出 | 消费方式 |
|--------|------------------|---------|
| README.md | Fig1 (.png) + T3-DEG benchmark 数据 + report.md 摘要 | 嵌入图片 + 从 benchmark JSON 提取数值 |
| ARCHITECTURE.md | 03-detailed-design.md + 00B + 00- §六 | 提取架构描述，重写为面向外部读者的语言 |
| BENCHMARK.md | S2 代码 + GT JSON + benchmark 结果 JSON | 审查现有内容一致性，更新 T3-DEG 实际数据 |
| CASE_STUDY.md | pipeline_result JSON + S3 execution_log + Fig5/6 | 从 JSON 提取数据，标注每个数据的来源 |
| FAQ.md | 00- §六 17条决策 + S1-S4 实际运行发现 | 提取决策理由，用实际数据说明 |
| PPT | Fig1/2/5/6 + T3-DEG 数据 + pipeline_result | 嵌入 SVG/PNG + 提取关键数字 |
| CI | tests/ 目录 + requirements.txt | 跑 lint + pytest |

### 所有交付物共用的约束

1. **可追溯性**：每个定量数字必须标注数据来源（哪个 JSON 文件的哪个字段）
2. **诚实性**：局限和失败与优点同等篇幅展示
3. **GOV-005**：README + ARCHITECTURE + CASE_STUDY 中英双语
4. **FIG-002**：嵌入的图表使用 svglite + rsvg 渲染的 PNG

---

## 四、DATA FLOW（从 S1-S4 产出到 S5 交付物）

```
S1-S4 全部产出
    │
    ├── README.md / README_CN.md
    │   ← Fig1 (paper/figures/fig1_architecture.png)
    │   ← T3-DEG 对比数据 (results/benchmark_v1_*.json)
    │   ← Quick Start 命令 (demo/run_literature_review.py)
    │   ← 已知局限 (paper/report.md §7)
    │
    ├── ARCHITECTURE.md
    │   ← 4 Agent 设计 (03-detailed-design.md §四)
    │   ← 反幻觉五层防线 (00B)
    │   ← 关键决策 (00-master-coordination.md §六)
    │
    ├── BENCHMARK.md (审查更新)
    │   ← T3-DEG 实际运行数据 (results/benchmark_v1_*.json)
    │   ← 5 GT 数据集现状 (data/benchmark/ground_truth/)
    │
    ├── CASE_STUDY.md
    │   ← PipelineResult (data/demo_output/pipeline_result_*.json)
    │   ← Fig5/6 (paper/figures/)
    │   ← S3 execution_log
    │
    ├── FAQ.md
    │   ← 17 条决策日志 (00- §六)
    │   ← S1-S4 实际运行发现的问题
    │
    ├── presentation/biomed-agent-overview.pptx
    │   ← Fig1/2/5/6 + benchmark 数据 + case study 关键数字
    │   ← 复用 Harness_Engineer/output/build-ppt.js 模板
    │
    └── .github/workflows/ci.yml
        ← tests/ 目录
        ← requirements.txt
```

---

## 五、PROMPT TEMPLATES

S5 不涉及 LLM 调用。所有内容从 S1-S4 产出中提取、重组、重写为面向外部读者的语言。

重写原则（替代 Layer 1 反幻觉约束，适用于文档撰写）：
1. **不凭空添加**：文档中的任何一个声称，如果 S1-S4 中没有，就不能写
2. **不弱化局限**：S1-S4 中标为 degraded/failed/warning 的内容，在 S5 文档中同等标注
3. **定量精确**：数字带来源、带上下文、带已知偏差说明
4. **可操作性**：Quick Start 命令必须实际可运行，不能是伪代码

---

## 六、质量门控（替代反幻觉措施，适用于文档交付物）

### 6.1 事实准确性检查

| 检查项 | 方法 |
|--------|------|
| 每个定量数字有 S1-S4 来源 | 脚本化检查：grep 数字 → 反向查找来源文件 |
| Quick Start 命令可运行 | 干净 venv 中执行 |
| 架构描述与代码一致 | 对比 ARCHITECTURE.md 中的 Agent 名称与 src/ 中的实际类名 |
| Benchmark 数字与 JSON 一致 | 脚本化对比 |

### 6.2 诚实性检查

| 检查项 | 方法 |
|--------|------|
| 局限/失败与优点同等篇幅 | 人肉检查 README 不只在底部小字提局限 |
| 没有 "state-of-the-art" 等无数据支撑的声称 | grep 搜索并逐条核对 |
| Degraded/failed 结果被诚实报告 | 对比 CASE_STUDY.md 与 S3 execution_log |

### 6.3 可理解性检查

| 检查项 | 方法 |
|--------|------|
| 陌生人 5 分钟能说出项目做什么 | 人肉测试（找没参与项目的人） |
| Quick Start 5 行命令产出结果 | 干净 venv 测试 |
| 架构文档 30 分钟能读懂 | 人肉测试 |

---

## 七、实施顺序

```
Phase 1: README.md + README_CN.md        （项目入口，最先需要）
Phase 2: ARCHITECTURE.md                 （深度理解）
Phase 3: CASE_STUDY.md                   （端到端走读）
Phase 4: FAQ.md                          （设计决策问答）
Phase 5: BENCHMARK.md 审查更新           （确保与当前状态一致）
Phase 6: presentation/ PPT               （结构化讲解）
Phase 7: .github/workflows/ci.yml        （CI 配置）
```

---

## 八、与 00- 的对接

### 需要回写 00- §六 的决策

| 编号 | 决策 |
|------|------|
| D-018 | S5 设计基准修正 — 从"面试展示"改为"项目可理解性与可复现性" |
| D-019 | S5 交付物裁减 — 不做简历描述/GitHub Pages/demo video（P2 可选） |
| D-020 | S5 新增 FAQ.md 替代原 05- 的面试 Q&A，面向所有理解者 |
| D-021 | S5 报告语言 — GOV-005 中英双语（README/ARCHITECTURE/CASE_STUDY） |

### 依赖 00- 的内容

- 共享类型定义（§二）— 用于 ARCHITECTURE.md 中的 Agent 接口描述
- 设计哲学（§四）— 用于 FAQ.md 中的设计决策回答
- 决策日志（§六）— 用于 FAQ.md 的原始素材

---

## 附录 A：与 05-portfolio-packaging.md 的差异说明

| 项目 | 原 05- | S5 详细设计 | 理由 |
|------|--------|-----------|------|
| 设计动机 | "面试官在30秒内看懂" | "陌生开发者 clone 后不问你就能跑通" | 为面试包装会破坏诚实性 |
| FAQ | "面试常见问题准备" | 设计决策与技术细节问答（面向所有理解者） | FAQ 是项目文档，不是面试 cheat sheet |
| 简历描述 | 5 行 JD 关键词覆盖 | 剔除 | 简历是个人材料，不属于项目 |
| P2 可选 | 默认包含 | 明确标注 P2 可选、S5 不强制 | 聚焦核心交付物 |
| PPT 目的 | "15分钟面试演讲" | 技术演讲，给技术听众的结构化讲解 | PPT 是项目讲解，不只是面试用 |

---

> **⏸️ DESIGN DRAFT READY** — 等待审查。审查重点：
> 1. 交付物清单是否完整？是否有遗漏的必要文档？
> 2. 内容规格中是否有过度承诺（S1-S4 数据不支持的内容）？
> 3. 已知局限是否被充分前置（不在文档深处藏）？
> 4. 是否有任何"面试导向"的残留措辞？
