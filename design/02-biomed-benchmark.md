# 02 — Step 2 设计方向：生物医学 Agent Benchmark

> **目标**：构建一个面向生物医学 Agent 的标准化评测框架，包含 5 类任务、4 维 metrics、3 个 baseline
> **工期**：5-6天
> **依赖**：Step 1 定义的 `LiteratureReview`, `Paper`, `Hypothesis` 类型；Step 1 实现的 `LiteratureAgent`（作为 T1-LIT 的被测对象）
> **被依赖**：Step 3 用此框架评估多 Agent pipeline；Step 4 的定量结果全部来自此框架

---

## 一、这个 Step 要回答的核心问题

1. 当你声称"我们的生物医学 Agent 系统很好"时，**"好"是什么意思**？如何量化？
2. 与 naive LLM（零-shot，无工具）、标准 ReAct pattern、简单 RAG 相比，你的 Agent 到底好多少？在哪些维度好？
3. 生物医学 Agent 的"幻觉"如何定义和检测？
4. 这些评测任务是否覆盖了生物医学研究的关键能力？

---

## 二、已有资产（可直接复用或改写）

| 资产 | 位置 | 可复用内容 |
|------|------|-----------|
| 56 条质量门控定义 | `生信分析/spatial_agent/core/constants.py:148-218` | 改写为 benchmark 的 evaluation criteria |
| ITIP Phase C 的 Cox 回归 ground truth | `itip_p1/R/phase_C/prognostic_model.R` | T4-SURV 任务的正确答案 |
| ITIP Phase E 的 GDSC2 药物关联 | `itip_p1/R/phase_E/drug_sensitivity.R` | T5-DRUG 任务的正确答案 |
| CSTB 模块的基因-癌症关联 | `CSTB_paper/results/module3_genetics/` | T2-GDA 任务的部分 ground truth |
| 10 个 ICI 队列的差异表达结果 | `itip_p1/prepare_ici_data.R` | T3-DEG 任务的参考数据 |
| Harness Engineer 的 test infrastructure | `Harness_Engineer/packages/*/tests/` | 测试框架的设计模式 |
| Spatial Agent 的 Evaluator | `生信分析/spatial_agent/modules/m6_evaluator.py` | 三级门控（G1完整性→G2正确性→G3生物学合理性）的评估逻辑 |

---

## 三、设计方向

### 3.1 五个任务的精确定义

#### T1-LIT: 文献检索与证据整合

```
任务描述: 给定生物医学问题，检索相关文献并整合证据
输入: 自然语言问题 (e.g. "CSTB在结直肠癌中作为预后标志物的证据")
评测对象: LiteratureAgent (来自Step 1) vs. baseline agents
Ground Truth: 人工标注的相关论文列表 (≥15篇, 由领域知识+PubMed验证)
主要指标:
  - Recall@K: ground truth论文在检索结果top-K中的比例
  - Precision@K: 检索结果top-K中真正相关的比例
  - Evidence Integration Score: 证据整合的完整性和准确性 (1-5分, 人工评分)
  - Citation Accuracy: 引用的PMID是否真实、结论是否准确反映原文
```

#### T2-GDA: 基因-疾病关联推理

```
任务描述: 给定基因和疾病，判断关联强度并给出证据
输入: gene_symbol + disease_name (e.g. "CSTB" + "colorectal cancer")
评测对象: Agent需要搜索文献+数据库来判断关联
Ground Truth: 从 DisGeNET, Open Targets, 和已知文献中提取的关联强度
主要指标:
  - Association Accuracy: 判断的关联强度是否与ground truth一致
  - Evidence Quality: 引用的证据是否可靠
  - False Discovery Rate: 声称有关联但实际无充分证据的比例
```

#### T3-DEG: 差异表达分析

```
任务描述: 给定表达矩阵，正确执行差异表达分析
输入: TCGA-COAD tumor vs normal 表达矩阵 (真实数据, 子集)
评测对象: Agent 需要选择统计方法、执行分析、解释结果
Ground Truth: 已知的差异表达基因列表 (来自已发表的TCGA-COAD分析)
主要指标:
  - Method Selection Accuracy: 是否选择了正确的统计方法
  - Result Correctness: logFC和adjusted p-value是否在合理范围内
  - Step Completeness: 是否执行了必要的步骤 (标准化→检验→多重校正)
  - Interpretation Quality: 对结果的解释是否准确
```

#### T4-SURV: 生存分析

```
任务描述: 给定表达+生存数据，正确构建预后模型
输入: TCGA-COAD 表达矩阵 + 生存数据 (真实数据, n=303)
评测对象: Agent 需要执行 Cox 回归、绘制 KM 曲线
Ground Truth: ITIP Phase C 的计算结果 (已验证)
主要指标:
  - HR Accuracy: Hazard Ratio 是否在 ground truth 的 ±0.1 范围内
  - P-value Consistency: p-value 的方向性结论是否一致
  - KM Plot Correctness: 分组方式、统计检验是否正确
  - Proportional Hazards Check: Agent 是否检查了 PH 假设
```

#### T5-DRUG: 药物敏感性筛选

```
任务描述: 给定基因列表，筛选相关药物
输入: 基因列表 (来自空间转录组学标志物) + GDSC2 药物敏感性数据
评测对象: Agent 需要执行相关性分析、多重检验校正
Ground Truth: ITIP Phase E 的计算结果
主要指标:
  - Correlation Accuracy: Spearman rho 是否在 ground truth 的合理范围内
  - FDR Control: 是否执行了正确的多重检验校正
  - Drug Classification: 敏感性/耐药性分类的准确性
  - Missing Data Handling: 如何处理 GDSC2 中缺失的基因
```

### 3.2 四维 Metrics 体系

```
┌─────────────────────────────────────────────────────────┐
│                    Agent 评估四维度                       │
├───────────────┬───────────────┬───────────────┬─────────┤
│ Completion    │ Tool Selection│ Result        │ Safety  │
│ Rate          │ Accuracy      │ Correctness   │ & Trust │
│ (能不能做完)   │ (会不会选工具) │ (结果对不对)   │ (可不可信)│
├───────────────┼───────────────┼───────────────┼─────────┤
│ 任务是否成功   │ 是否选了正确的 │ 数值结果是否   │ 虚构引用 │
│ 完成(不crash) │ 工具/方法/参数│ 在ground truth│ 的比例   │
│               │               │ 可接受范围内   │         │
│ 是否陷入死循环 │ 是否用了不该用 │ 统计推断方向   │ 虚构基因 │
│               │ 的工具        │ 是否正确       │ 功能     │
│ 是否超时      │ 工具调用顺序   │ 效应量估计     │ 虚构数据 │
│               │ 是否合理      │ 是否合理       │ 虚构结论 │
└───────────────┴───────────────┴───────────────┴─────────┘

加权总分 = 0.15 × Completion + 0.25 × ToolSelection
         + 0.35 × Correctness + 0.25 × Safety
```

**需要在这个窗口内做出的设计决定**：
- 各维度权重的最终数值（上面是初版建议）
- Hallucination 的具体检测方式：(a) 检查 PMID 是否存在于 PubMed；(b) 检查基因名是否在输入数据中；(c) 检查统计量是否在物理可能范围内（如 HR 不会 >100）
- 每个任务的 pass/fail 阈值

### 3.3 三个 Baseline

| Baseline | 实现 | 代表什么 |
|----------|------|---------|
| **B1: Naive LLM** | 零-shot prompting，无工具，无 RAG，无记忆 | 最基础的水平。如果连这个都比不过，Agent 设计有根本问题 |
| **B2: ReAct Pattern** | 标准 Think→Act→Observe 循环 + 工具调用，但无领域 prompt、无检索增强 | 通用 Agent 框架的水平。衡量领域知识注入的效果 |
| **B3: Simple RAG** | 固定检索 pipeline（搜→embed→top-K→塞进 prompt）+ 工具调用，但无多轮、无证据链 | 简单 RAG 的水平。衡量多轮推理和结构化证据整合的效果 |

**关键设计方向**：三个 baseline 共用同一个 LLM（deepseek-v4-pro），控制变量。差异只在于：(1) 有无工具，(2) 有无检索，(3) 有无多轮推理+证据链。

### 3.4 Benchmark Runner 设计

**方向**：Runner 是纯函数式的——输入一个 Agent 对象 + 一个 Task，输出 AgentEvalMetrics。Agent 对象遵循统一接口：

```python
class EvalAgent(Protocol):
    def run(self, task: BenchmarkTask) -> AgentOutput:
        """执行任务，返回结构化输出"""
    @property
    def name(self) -> str:
        """Agent 名称，用于报告"""
```

这样 Step 1 的 LiteratureAgent、Step 3 的 MultiAgentPipeline、以及三个 baseline，都实现同一个接口，可以被同一个 Runner 评估。

---

## 四、产出物清单

### 代码文件

| 文件 | 功能 | 新建/整合 |
|------|------|----------|
| `benchmark/tasks.py` | 5 个 BenchmarkTask 定义 + ground truth 数据加载 | 新建 |
| `benchmark/metrics.py` | AgentEvalMetrics 计算逻辑 | 新建 |
| `benchmark/runner.py` | BiomedBenchmark: 运行全部任务 → 生成报告 | 新建 |
| `benchmark/baselines.py` | B1/B2/B3 三个 baseline Agent 实现 | 新建 |
| `benchmark/data/` | Ground truth 数据（JSON 格式，小文件） | 整合 ITIP/CSTB |

### 数据产出

| 产出 | 用途 |
|------|------|
| `results/benchmark_v1.json` | 完整 benchmark 结果（Step 4 的核心数据源） |
| `results/benchmark_comparison.csv` | Agent × Task 对比矩阵 |

### 文档产出

| 文档 | 内容 |
|------|------|
| `BENCHMARK.md` | Benchmark 设计文档（任务定义、metrics 解释、如何使用） |

---

## 五、成功标准

### P0

- [ ] 5 个任务全部有明确的 ground truth（可以是不完美的，但必须有）
- [ ] 3 个 baseline 在全部 5 个任务上跑通并产出可比较的 metrics
- [ ] LiteratureAgent（Step 1 产出）在 T1-LIT 上跑通并产出 metrics
- [ ] hallucination_rate 的检测逻辑能捕捉到至少 1 个真实的幻觉案例
- [ ] `BiomedBenchmark.run_all(agent)` 可以在 30 分钟内跑完全部 5 个任务

### P1

- [ ] LiteratureAgent 在 T1-LIT 的 Overall Score 显著高于 B1（naive LLM）
- [ ] 至少发现 1 个 B2（ReAct）在生物医学场景中的具体失败模式（为什么通用框架不够）
- [ ] 每个任务的评估标准有明确的、可执行的定义（不是"人肉判断"）

### P2

- [ ] 完整的 evaluation rubric（评分细则表），可供他人复现
- [ ] Benchmark 可扩展到新任务（添加新 task 只需实现接口，不改 Runner）

---

## 六、与其它 Step 的接口

### 消费 Step 1 的
- `LiteratureReview` / `Paper` / `Hypothesis` 类型（类型定义必须一致）
- `LiteratureAgent.run()` 方法（作为 T1-LIT 的被测对象）

### 导出给 Step 3 的
- `BenchmarkTask` 和 `AgentEvalMetrics` 类型定义
- `EvalAgent` Protocol（Step 3 的 MultiAgentPipeline 实现此接口）
- `BiomedBenchmark` runner（Step 3 用同一框架评估自己）

### 导出给 Step 4 的
- `results/benchmark_v1.json` — 全部定量结果
- 每个 Agent×Task 的详细评估日志

---

## 七、关键设计决定（需要在这个窗口中讨论确认）

1. **Ground truth 的来源**：人肉标注 vs. 从公开数据库提取 vs. 用已有的 ITIP/CSTB 计算结果。推荐混合：T1-LIT 和 T2-GDA 用公开数据库 + 人工验证；T3-DEG/T4-SURV/T5-DRUG 用 ITIP/CSTB 的已验证结果。
2. **人工评分的程度**：T1-LIT 的 Evidence Integration Score 需要人工评分（1-5）。评多少？建议每个 agent 在每个 task 上抽 3 个案例做人工评分，其余用自动 metric。
3. **Benchmark 的规模**：5 tasks × 10 cases × 4 agents × 3 baselines = 需要跑大量任务。建议先跑通 5 tasks × 3 cases 的缩小版，验证 pipeline 正确性后再扩展。
4. **分数归一化**：不同 task 的分数 scale 不同（Recall@K 是 0-1，人工评分是 1-5）。需要统一归一化到 0-100。

---

> **打开独立 Claude 窗口时**，把此文档和 `00-master-coordination.md` 一起粘贴。告诉它：「请基于这两个文档，设计 Step 2 的 Benchmark 框架。先和我讨论 §三 和 §七 中的设计决定，特别是 5 个任务的具体 ground truth 怎么构建，确认后再开始写代码。」
