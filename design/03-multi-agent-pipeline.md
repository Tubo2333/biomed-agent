# 03 — Step 3 设计方向：多 Agent 协作闭环 Pipeline

> **目标**：实现 4 个 Agent 协作完成完整的生物医学科研闭环——文献调研 → 分析设计 → 数据执行 → 报告生成
> **工期**：5-7天
> **依赖**：Step 1 的 `LiteratureAgent` 完整实现；Step 2 的 `BenchmarkTask` 类型定义；ITIP/CSTB/Spatial Agent 的已有数据和代码
> **被依赖**：Step 4 的 case study 数据来源；Step 5 的核心 demo

---

## 一、这个 Step 要回答的核心问题

1. 多个 Agent 如何协作完成一个**真实、完整的生物医学研究任务**（而非 toy example）？
2. LLM 驱动的任务规划（"我应该做什么分析"）比规则-based 任务规划好在哪里？差在哪里？
3. Agent 之间的通信——当 LiteratureAgent 产出 3 个假设时，OrchestrationAgent 如何将其转化为分析计划？AnalysisAgent 如何执行这些计划？
4. 在真实数据上跑通全流程时，哪些环节会出问题？Agent 如何从失败中恢复？

---

## 二、已有资产（可直接复用或改写）

| 资产 | 位置 | 可复用内容 |
|------|------|-----------|
| Spatial Master Agent 架构 | `生信分析/spatial_agent/core/master.py` | 6 组件设计（TaskAnalyzer, WorkflowPlanner, ResourceAllocator, ProgressMonitor, QualityGateEnforcer, FinalAssembler） |
| Spatial WorkerAgent 生命周期 | `生信分析/spatial_agent/core/worker.py` | 6 状态 INIT→VALIDATE→EXECUTE→VALIDATE→REPORT→CLEANUP |
| Spatial 文件消息总线 | `生信分析/spatial_agent/core/message_bus.py` | MessageBus 的目录结构和收发逻辑 |
| ITIP Phase C: Cox 回归 | `itip_p1/R/phase_C/prognostic_model.R` | 完整的生存分析 R 代码 |
| ITIP Phase E: 药物敏感性 | `itip_p1/R/phase_E/drug_sensitivity.R` | GDSC2 Spearman 相关分析 |
| ITIP Phase A: 差异表达 | `itip_p1/R/phase_A/scRNA_discovery.R` | TCGA 表达数据处理 |
| CSTB 免疫浸润 | `CSTB_paper/results/module4_immune/` | 免疫细胞丰度估计 |
| M3-LLM 科学叙事 | `生信分析/spatial_agent/modules/m3_llm_enhancer.py` | LLM 驱动的结果解释 |
| M11 Reporter | `生信分析/spatial_agent/modules/m11_reporter.py` | 自动报告生成 |
| Harness TAOR 循环 | `Harness_Engineer/packages/core/src/harness.ts:489-1285` | Think→Act→Observe 的完整实现（作为 Python 实现的参考模型） |

---

## 三、设计方向

### 3.1 四个 Agent 的角色与职责（精确边界）

```
┌──────────────────────────────────────────────────────────────┐
│                      用户输入                                 │
│     "研究 CSTB 在结直肠癌中的预后价值和免疫浸润关联"           │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  Agent 1: LiteratureAgent (来自 Step 1)                       │
│  ─────────────────────────────────────────                   │
│  输入: 自然语言研究问题                                        │
│  输出: LiteratureReview (论文列表 + 证据链 + 假设 + 知识缺口)  │
│                                                              │
│  做了什么:                                                    │
│  1. 将问题拆解为子问题                                        │
│  2. PubMed 检索 + embedding 语义筛选                          │
│  3. 多论文证据整合                                            │
│  4. 识别证据缺口 → 生成假设                                    │
└──────────────────────────┬───────────────────────────────────┘
                           │ LiteratureReview
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  Agent 2: OrchestrationAgent (改造 Spatial Master)            │
│  ─────────────────────────────────────────                   │
│  输入: LiteratureReview + 已知可用数据源                        │
│  输出: AnalysisPlan (DAG of analysis tasks)                   │
│                                                              │
│  做了什么:                                                    │
│  1. 从假设提取可验证的预测                                     │
│  2. 为每个预测匹配分析方法                                     │
│  3. 构建分析 DAG（拓扑排序、依赖管理）                          │
│  4. 为每个分析节点分配数据源和参数                               │
│  5. 识别数据缺口（哪些预测无法用现有数据验证）                   │
└──────────────────────────┬───────────────────────────────────┘
                           │ AnalysisPlan (DAG)
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  Agent 3: AnalysisAgent (整合 ITIP/CSTB 分析能力)             │
│  ─────────────────────────────────────────                   │
│  输入: AnalysisPlan + 真实数据路径                             │
│  输出: AnalysisResults (每个分析节点的定量结果)                 │
│                                                              │
│  做了什么:                                                    │
│  1. 按 DAG 拓扑序执行每个分析节点                              │
│  2. 对每个节点: 选择工具 → 填参数 → 执行 → 解释结果            │
│  3. 如果某节点失败: 分类失败 → 重试/调参/跳过                   │
│  4. 记录每个节点的完整执行日志                                  │
└──────────────────────────┬───────────────────────────────────┘
                           │ AnalysisResults
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  Agent 4: ReportAgent (改造 Spatial M11 Reporter)             │
│  ─────────────────────────────────────────                   │
│  输入: LiteratureReview + AnalysisPlan + AnalysisResults       │
│  输出: structured report (.md + .docx)                        │
│                                                              │
│  做了什么:                                                    │
│  1. 整合文献证据和实验结果                                      │
│  2. 对每个假设: 证据是否支持? 是否被推翻?                       │
│  3. 生成结构化报告 (Introduction→Methods→Results→Discussion)   │
│  4. 标注所有定量结果的来源 (哪个数据、哪个分析、哪个文件)        │
│  5. 列出局限性和下一步方向                                      │
└──────────────────────────────────────────────────────────────┘
```

### 3.2 编排 Agent 的核心设计问题：LLM 驱动的动态 DAG

**关键方向转变**：Spatial Master Agent 的 `plan_workflow()` 是硬编码的拓扑（`master.py:264-278`）——总是 M1→M2→M3→M4→...。OrchestrationAgent 需要改为 **LLM 驱动的动态规划**：

```
输入: LiteratureReview (包含 "CSTB通过M2巨噬细胞介导免疫抑制" 这个假设)
LLM 推理:
  "这个假设涉及三个维度：(1)CSTB在CRC中的表达，(2)CSTB与M2巨噬细胞标志物的相关性，
   (3)CSTB与免疫抑制分子的共表达。验证方案：
   → 差异表达分析 (TCGA-COAD tumor vs normal) 
   → 免疫浸润相关性 (TIMER/CIBERSORT/ssGSEA)
   → 免疫检查点共表达 (PD-L1, CTLA4, LAG3)
   → 生存分析分层 (CSTB高表达+高M2 vs 其他组合)
   数据源: TCGA-COAD (n=303)，已有本地缓存"
输出: AnalysisPlan (4个节点的DAG)
```

**与 Spatial Master Agent 的差异**：
- Spatial: 规则匹配（关键词 "visium" → Visium HD 分析 pipeline）
- 这里: LLM 推理（理解假设→设计验证方案→选择方法→分配数据源）
- 这是 JD 方向①「规划」和「多步决策」的核心体现

### 3.3 分析 Agent 的设计方向：工具调用而非脚本

**关键区别**：ITIP/CSTB 的分析是通过 R 脚本手动执行的。AnalysisAgent 不是把这些脚本包装成 Python subprocess 调用，而是：

1. **定义生物医学分析工具**：每个分析步骤是一个 tool
```python
tools = [
    ToolDef("run_differential_expression", "TCGA tumor vs normal...", ...),
    ToolDef("run_survival_analysis", "Cox regression with given genes...", ...),
    ToolDef("run_immune_correlation", "Correlate gene with immune signatures...", ...),
    ToolDef("run_drug_screening", "GDSC2 Spearman correlation...", ...),
]
```

2. **Agent 决定选哪个工具、用什么参数**：
```
Think: "需要验证 CSTB 在 CRC 中是否差异表达"
Act: tool_call("run_differential_expression", {
    "gene": "CSTB",
    "dataset": "TCGA-COAD",
    "group_col": "sample_type",
    "group_a": "tumor",
    "group_b": "normal"
})
Observe: "CSTB logFC=2.3, adj.P=1.2e-15 → 在肿瘤中显著高表达"
```

3. **工具内部调用已有的 R 代码**（`Rscript temp.R`），但 Agent 不接触 R 代码——Agent 只看到工具的输入输出。

### 3.4 Agent 间通信：轻量消息传递

**方向**：不需要 Spatial MessageBus 的文件系统复杂度。4 个 Agent 在同一个 Python 进程中运行，用内存消息队列。

```python
@dataclass
class AgentMessage:
    sender: str
    receiver: str  
    msg_type: str   # "task" | "result" | "query" | "error"
    payload: dict
    correlation_id: str

class AgentOrchestrator:
    """管理 4 个 Agent 的顺序执行"""
    def run_pipeline(self, user_question: str) -> PipelineResult:
        # Phase 1: Literature
        lit_result = self.literature_agent.run(user_question)
        
        # Phase 2: Planning
        plan = self.orchestration_agent.plan(lit_result)
        
        # Phase 3: Execution
        analysis_results = self.analysis_agent.execute(plan)
        
        # Phase 4: Report
        report = self.report_agent.generate(lit_result, plan, analysis_results)
        
        return PipelineResult(lit_result, plan, analysis_results, report)
```

**不需要并发**。科研工作流天然是顺序的（先看文献→再做实验→再写报告）。Agent 之间的"协作"体现在信息传递的语义理解上（OrchestrationAgent 理解 LiteratureReview 的语义，AnalysisAgent 理解 AnalysisPlan 的语义），而不体现在并行执行。

### 3.5 失败恢复：从 Spatial Agent 的五类失败继承

直接复用 Spatial Agent 的 F1-F5 失败分类 + 恢复策略 + 安全基线回退（`master.py:520-582`）：

| 失败类型 | 生物医学场景示例 | 恢复动作 |
|---------|----------------|---------|
| F1 瞬时 | TCGA API 超时 | 自动重试 3 次 |
| F2 参数 | DEG 结果全是 NA（选错了统计方法） | 调参重试（换 Welch t-test） |
| F3 方法 | Cox PH 假设不满足 | 降级为 KM + log-rank |
| F4 数据 | 基因不在 GDSC2 中 | 标记 degraded，跳过 |
| F5 未知 | 任何未分类错误 | 记录日志，继续下一个分析 |

---

## 四、产出物清单

### 代码文件

| 文件 | 功能 | 新建/整合 |
|------|------|----------|
| `agents/orchestration_agent.py` | LLM 驱动的动态 DAG 规划 | 新建（借鉴 Spatial master.py） |
| `agents/analysis_agent.py` | Think→Act→Observe 分析执行 | 新建（借鉴 ITIP 分析逻辑） |
| `agents/report_agent.py` | 多源聚合 + 结构化报告 | 整合 Spatial M11 reporter |
| `agents/pipeline.py` | AgentOrchestrator: 串联 4 Agent | 新建 |
| `tools/tcga_tools.py` | TCGA 数据查询和分析工具 | 整合 ITIP |
| `tools/survival_tools.py` | 生存分析工具（调用 R） | 整合 ITIP Phase C |
| `tools/drug_tools.py` | GDSC2 药物筛选工具 | 整合 ITIP Phase E |
| `tools/immune_tools.py` | 免疫浸润分析工具 | 整合 CSTB Module 4 |

### 数据产出

| 产出 | 用途 |
|------|------|
| CSTB case study 的完整 PipelineResult | Step 4 的核心案例数据 |
| 每个 Agent 的详细执行日志（每个 Think/Act/Observe 步骤） | Step 4 的 qualitative analysis |
| Agent 间消息传递的完整记录 | Step 4 的架构说明示例 |

---

## 五、成功标准

### P0

- [ ] 4 个 Agent 串行完成 CSTB-CRC 案例研究的全流程
- [ ] LiteratureAgent → OrchestrationAgent → AnalysisAgent → ReportAgent 的数据传递正确
- [ ] AnalysisAgent 至少成功执行 3 个分析任务（差异表达、生存分析、免疫关联）
- [ ] ReportAgent 产出的报告包含定量结果 + 文献引用 + 局限性
- [ ] 至少 1 个分析任务经历了 F2 或 F3 恢复（证明失败恢复机制有效）

### P1

- [ ] OrchestrationAgent 产出的 DAG 不是硬编码的——不同的 LiteratureReview 输入产生不同的分析计划
- [ ] AnalysisAgent 的每个工具调用都有 why/what/result 记录
- [ ] 报告中的每个定量结论都可以追溯到具体的分析节点
- [ ] Pipeline 可被 Step 2 的 BiomedBenchmark 评估（实现了 EvalAgent protocol）

### P2

- [ ] 两个不同的 genes 案例（如 CSTB vs TP53）产生不同的分析计划
- [ ] ReportAgent 对假设的"支持/不支持/需要更多证据"判断与人工评审一致
- [ ] 整个 pipeline 可以在 60 分钟内跑完（包括 LLM 调用）

---

## 六、与其它 Step 的接口

### 消费 Step 1 的
- `LiteratureAgent` 类（作为 pipeline 的 Phase 1）
- `LiteratureReview` / `Hypothesis` / `EvidenceLink` 类型
- `LLMClient`（所有 Agent 共用）

### 消费 Step 2 的
- `BenchmarkTask` 类型（用于定义分析任务的输入输出格式）
- `EvalAgent` protocol（Pipeline 实现此接口，可被 Step 2 的 Runner 评估）

### 导出给 Step 4 的
- `PipelineResult` — CSTB case study 的完整运行结果
- 每个阶段的详细日志
- 定量结果：HR, p-value, correlation coefficient, FDR

### 导出给 Step 5 的
- 端到端 demo 脚本 `demo/run_multi_agent_pipeline.py`

---

## 七、关键设计决定（需要在这个窗口中讨论确认）

1. **R 代码的集成方式**：选项 (a) Python subprocess 调 `Rscript temp.R`（需要写 temp .R file，Rule-R-001）；(b) rpy2 桥接（省了 temp file 但依赖重）；(c) 把 R 代码的输出缓存为 JSON，Python Agent 直接读缓存。**推荐 (c)**——分析是预计算好的（ITIP Phase C/D/E 的结果已验证），Agent 的"工具调用"实际上是查询和解释，而不是实时跑 R。理由：面试 demo 不需要等 R 跑完，而且避免了 Windows 上 Rscript segfault 的风险。

2. **AnalysisAgent 是"真执行"还是"模拟执行"**：这是个核心设计选择。**推荐混合**——差异表达和生存分析用预计算缓存（因为 R 跑得慢且容易炸），药物筛选和免疫关联用实时 Python 计算（数据已经在 pandas DataFrame 里）。面试时诚实说"核心分析是预计算的，Agent 的智能体现在方法选择、参数决策和结果解释"。

3. **Pipeline 是固定的 4 Agent 顺序，还是可扩展的 DAG？** **推荐先固定顺序**。4 个 Agent 的串行执行是科研工作流的自然顺序，不需要过度设计。但 OrchestrationAgent 的 `plan()` 方法输出的 AnalysisPlan 内部可以是 DAG（多个分析任务并行或串行）。

---

> **打开独立 Claude 窗口时**，把此文档和 `00-master-coordination.md` 一起粘贴。告诉它：「请基于这两个文档，实现 Step 3 的多 Agent 协作 Pipeline。先和我讨论 §七 中的关键设计决定，特别是 R 代码的集成方式和分析执行的"真/模拟"边界。确认后再开始写代码。」
