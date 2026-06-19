# 04 — Step 4 设计方向：技术报告 / 论文草稿

> **目标**：将 Step 1-3 的所有实验数据和设计决策，写成一篇有说服力的、可作为 writing sample 提交的技术报告
> **工期**：7-10 天（写作 5 天 + 图表 3 天 + 修改 2 天）
> **依赖**：Step 1 的实验数据（文献检索质量评估）；Step 2 的 benchmark 定量结果；Step 3 的 case study 完整结果
> **被依赖**：Step 5 的 GitHub README 和 PPT 从此报告提取关键数据和图表

---

## 一、这个 Step 要回答的核心问题

1. 这篇报告 / 论文的**核心贡献**是什么？一句话说清楚。
2. 和现有工作（LangChain Agent, AutoGen, BioGPT, GeneGPT）相比，你的系统**在什么维度上更好**？
3. 哪些实验数据是**定量的**（可以说"我们的方法在 X 指标上比 baseline 高 Y%"），哪些是**定性的**（案例研究、日志分析）？
4. 这篇报告是给谁看的？（面试官？学术导师？开源社区？）——决定了写作的语言、深度和侧重点。

---

## 二、已有资产（可直接复用或改写）

| 资产 | 位置 | 可复用内容 |
|------|------|-----------|
| Spatial 综合研究报告 v1.1 | `生信分析/manuscript/综合研究报告_方向C_空间组学智能体系统.md` | 系统架构描述的结构和组织方式 |
| Spatial 英文报告 | `生信分析/manuscript/research_report.md` | 英文科学写作风格 |
| 专利交底书 v2.0 | `生信分析/方向C_技术交底书_v2.0_可落地执行版.md` | 技术方案的严谨描述规范 |
| TAOR API 设计文档 | `Harness_Engineer/Harness_API_Design_v2.md` | 15 章架构规划的结构 |
| CSTB 论文草稿 | `CSTB_paper/` | 生物医学论文的 Introduction/Discussion 写作风格 |
| ITIP 专利 | `itip_p1/outputs/NSCLC-13gene-panel/` | 科学发现的呈现方式 |
| identity-fill 出图 pipeline | R 4.5.2 svglite + rsvg | 科研级图表的渲染管线 |

---

## 三、设计方向

### 3.1 报告定位：一篇 arXiv 风格的 pre-print

**方向**：不是课程作业，不是博客，而是**可以放上 arXiv 的技术报告**。这给面试官的信号是"这个人知道学术写作的标准"。

- 语言：英文（arXiv 风格），但可以有一份中文摘要版本
- 长度：正文 12-18 页 + 参考文献 3-5 页 + 附录
- 结构：标准学术论文 IMRaD（Introduction, Methods, Results, Discussion）
- 引用：30-50 篇参考文献，BibTeX 管理
- 图表：8-10 张图，全部 svglite + rsvg 渲染

### 3.2 核心贡献陈述（一句话）

报告必须有一个清晰的、可辩护的**核心论点**。以下是一些候选，需要在 Step 1-3 完成后根据实际数据选定：

> *"We present a multi-agent system that combines literature-grounded hypothesis generation with automated multi-omics analysis, and show through a benchmark of 5 biomedical tasks that structured evidence chaining reduces hallucination rate by X% compared to naive LLM baselines."*

核心贡献的三个层次（报告必须同时包含）：
1. **系统贡献**：一个 4-Agent 协作架构，连接文献推理和多组学分析
2. **方法贡献**：结构化证据链（EvidenceLink）作为反幻觉机制
3. **实证贡献**：5-task benchmark 上的定量对比 + CSTB case study 的完整演示

### 3.3 报告的 8 个章节

```
1. Introduction (2-3页)
   - 生物医学研究的瓶颈：数据碎片化、文献爆炸、跨领域知识整合
   - 现有 AI Agent 框架在生物医学中的不足：通用框架缺乏领域知识、幻觉问题严重
   - 我们的方案概述
   - 贡献列表 (3 条, bullet points)

2. Related Work (2-3页)
   - AI Agent 框架: ReAct, LangChain, AutoGen, MCP
   - 生物医学 AI: BioBERT, PubMedBERT, GeneGPT, scGPT, BiomedCLIP
   - 多智能体系统: CAMEL, ChatDev, AgentVerse
   - 生物医学 QA/Benchmark: PubMedQA, BioASQ, MedQA, MedMCQA
   - 关键区别表：我们的系统 vs. 现有工作在 5 个维度上的差异

3. System Architecture (2-3页)
   - 整体架构图 (Fig 1)
   - 4 个 Agent 的角色和数据流
   - RAG pipeline 设计
   - 工具系统：PubMed, TCGA, GEO, GDSC2
   - Agent 间通信协议

4. Agent Design (3-4页)
   - 4.1 LiteratureAgent: Think→Act→Observe 多轮检索 + 证据链 + 假设生成
   - 4.2 OrchestrationAgent: LLM 驱动的动态 DAG 生成
   - 4.3 AnalysisAgent: 工具调用的决策过程
   - 4.4 ReportAgent: 多源证据整合
   - 4.5 反幻觉策略 (Fig 2: 结构化证据链示意)

5. Benchmark Design (2-3页)
   - 5.1 五个任务的定义和 ground truth 构建
   - 5.2 四维 metrics 体系
   - 5.3 三个 baseline
   - Table 1: 任务×metrics 矩阵

6. Results (3-4页)
   - 6.1 Benchmark 定量结果
     - Fig 3: Overall Score 对比柱状图 (4 agents × 5 tasks)
     - Fig 4: Hallucination Rate 对比
     - Table 2: 每个任务×每个agent的完整metrics
   - 6.2 CSTB Case Study 定性分析
     - Fig 5: Agent 决策过程的时间线/流程图
     - Fig 6: 文献证据网络图
     - Fig 7: 分析结果（KM曲线 + 免疫相关性热图）
   - 6.3 消融分析
     - Table 3: 去掉证据链/去掉多轮检索/去掉LLM规划 后的性能变化

7. Discussion (1-2页)
   - 7.1 主要发现
   - 7.2 局限性：单任务串行、预计算分析、LLM 仍然存在的幻觉风险
   - 7.3 未来工作：并行Agent、强化学习微调、临床文本整合

8. Conclusion (0.5页)

References (30-50篇)

Appendix
  - A. 每个 Benchmark 任务的完整定义
  - B. CSTB Case Study 的完整日志
  - C. Prompt 模板
```

### 3.4 图表设计（8 张图 + 3 张表）

| 编号 | 内容 | 来源数据 | 出图方式 |
|------|------|---------|---------|
| **Fig 1** | 系统架构图 | 设计文档 | Mermaid → SVG → 手绘风格（参考 TAOR demo PPT 的画风） |
| **Fig 2** | 结构化证据链示意 | Step 1 的 EvidenceLink 示例 | 信息图，手绘 |
| **Fig 3** | Overall Score 对比柱状图 | Step 2 benchmark 结果 | R ggplot2 + identity-fill + svglite |
| **Fig 4** | Hallucination Rate 对比 | Step 2 benchmark 结果 | R ggplot2 |
| **Fig 5** | Agent 决策时间线 | Step 3 case study 日志 | 手绘流程图 |
| **Fig 6** | 文献证据网络图 | Step 1 CSTB query 结果 | Python networkx + matplotlib |
| **Fig 7** | CSTB 生存分析 KM 曲线 | Step 3 AnalysisAgent 输出 | R survminer + svglite |
| **Fig 8** | CSTB 免疫浸润相关性热图 | Step 3 AnalysisAgent 输出 | R ComplexHeatmap + svglite |

| 表格 | 内容 |
|------|------|
| **Table 1** | 5 tasks × 5 metrics 的设计矩阵 |
| **Table 2** | 完整 benchmark 结果 (4 agents × 5 tasks) |
| **Table 3** | 消融分析 |

### 3.5 关键写作原则

1. **每个 claim 必须有数据支撑。** "Our agent achieves higher accuracy" → 必须有具体的数字和统计检验。
2. **诚实地报告失败。** Discussion 中必须列出系统做不到的事。这比"一切都好"更有说服力。
3. **和 baseline 对比，不是和空气对比。** 没有 baseline 的结果 = 没有意义的结果。
4. **代码开源。** 报告中引用 GitHub 仓库地址（这是 JD "开源代码整理"的直接证据）。
5. **使用 Nature 风格的图。** 你已经有了 identity-fill pipeline + Okabe-Ito 配色——这是你的竞争优势。多数 CS 论文的图很丑。

---

## 四、产出物清单

| 产出 | 路径 | 格式 |
|------|------|------|
| 技术报告正文 | `paper/report.md` | Markdown |
| 技术报告 PDF | `paper/report.pdf` | PDF（pandoc 渲染） |
| 参考文献 | `paper/references.bib` | BibTeX |
| 图表源文件 | `paper/figures/*.svg` + `*.png` | SVG (300dpi PNG raster) |
| 图表生成脚本 | `paper/figures/generate_figures.R` | R |
| 中文摘要 | `paper/abstract_cn.md` | Markdown |

---

## 五、成功标准

### P0

- [ ] 完整 8 章结构，正文 12-18 页
- [ ] 至少 6 张图 + 2 张表，全部从真实数据生成
- [ ] 至少 30 篇参考文献，其中至少 15 篇是 2023-2026 年的
- [ ] Results 章节的每个数字都可以追溯到 Step 1-3 的实验输出
- [ ] Discussion 中明确列出 3 条以上局限性

### P1

- [ ] Related Work 中有一个对比表（我们的系统 vs. 5+ 个现有系统）
- [ ] 至少 1 张图经过 nature-figure skill 的 QA 检查
- [ ] 报告被至少 1 个外部读者（没有参与项目的人）读过并给出反馈

### P2

- [ ] PDF 渲染正确（中文字体、代码块、数学公式）
- [ ] 放上 arXiv（或至少准备好 arXiv 格式）

---

## 六、与其它 Step 的接口

### 消费 Step 1 的
- 10 个 query 的 LiteratureReview 结果 → 用于 Fig 6 和 Table 2 的 T1-LIT 行
- 证据链和假设的定性示例 → 用于 Fig 2 和 §4.1

### 消费 Step 2 的
- `results/benchmark_v1.json` → 用于 Fig 3, Fig 4, Table 2 的全部数据
- 3 个 baseline 的详细日志 → 用于 §6.1 的分析

### 消费 Step 3 的
- CSTB case study 的 PipelineResult → 用于 Fig 5, Fig 7, Fig 8, §6.2
- Agent 决策日志 → 用于 Fig 5 和 §4 的示例

### 导出给 Step 5 的
- report.pdf → GitHub 仓库的核心文档
- 所有图表 → README 和 PPT 使用
- 关键数字（"hallucination rate 降低 X%"）→ PPT 的核心论点

---

## 七、关键设计决定（需要在这个窗口中讨论确认）

1. **报告语言**：纯英文（arXiv 风格）vs. 中英双语（符合 GOV-005）。**推荐英文正文 + 中文摘要**。英文正文符合学术规范，中文摘要方便中文面试官快速理解。

2. **"我们"vs."I"**：单人项目用 "I" 还是学术惯例的 "we"？**推荐 "we"**，学术惯例，而且隐含"我和我的 Agent 系统"。

3. **arXiv 是否真的提交**：取决于结果质量。如果 benchmark 结果确实显著优于 baseline，值得提交。如果结果还不够好，报告本身作为 writing sample 也足够有价值。**不需要现在就决定，Step 1-3 完成后再判断。**

4. **系统命名**：给系统一个名字（如 "BioMed-Agent" 或 "LitLab"），让报告和 GitHub 仓库有统一的品牌标识。

---

> **打开独立 Claude 窗口时**，把此文档和 `00-master-coordination.md` 一起粘贴。告诉它：「请基于这两个文档，帮助我规划技术报告的写作。先和我讨论 §三 的核心贡献陈述是否准确（需要根据 Step 1-3 的实际数据调整），然后逐章讨论每章应该包含什么内容和数据。」
