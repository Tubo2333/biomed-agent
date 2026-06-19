# 05 — Step 5 设计方向：投递组合打包

> **目标**：将 Step 1-4 的所有产出打包成一个面试官在 30 秒内就能看懂的完整项目
> **工期**：2-3 天
> **依赖**：Step 1-4 的全部产出
> **这是最后一步，也是面试官看到的第一步**

---

## 一、这个 Step 要回答的核心问题

1. 面试官打开 GitHub 仓库的前 30 秒，他看到什么？读完后他会记住什么？
2. 简历上关于这个项目的 5 行描述，能不能让 HR 说"这个人我们要面一下"？
3. 15 分钟面试 PPT 讲完后，面试官最想问什么问题？你能不能提前准备好答案？
4. 如果面试官问"你在这个项目中最大的技术挑战是什么"，你准备讲哪个故事？

---

## 二、已有资产

| 资产 | 位置 | 用途 |
|------|------|------|
| TAOR demo PPT | `Harness_Engineer/output/taor-demo.pptx` | PPT 模板（warm navy+coral 配色, hand-drawn illustration） |
| TAOR demo 脚本 | `Harness_Engineer/output/voiceover-script.md` | 15 分钟演讲叙事结构 |
| TAOR build-ppt.js | `Harness_Engineer/output/build-ppt.js` | PptxGenJS 脚本（可直接修改复用） |
| TAOR recording guide | `Harness_Engineer/output/taor-recording-guide.docx` | 演示录制的导演脚本 |
| Spatial 综合研究报告 | `生信分析/manuscript/` | 技术深度的证明 |
| 专利交底书 | `生信分析/方向C_技术交底书_v2.0_可落地执行版.docx` | 技术文档写作能力的证明 |

---

## 三、设计方向

### 3.1 GitHub 仓库的"30 秒法则"

当面试官打开 `github.com/Tubo2333/biomed-agent`，他的视线轨迹是：

```
1. 仓库名 + 一句话描述（2秒）
   ↓
2. README 顶部的架构图/示意图（5秒）
   ↓
3. Quick Start 的 5 行命令（10秒）
   ↓
4. 往下滚动，看到 Benchmark 结果表（10秒）
   ↓
5. 决定：关掉 vs. 仔细看
```

所以 README 的结构必须精确对应这个视线轨迹：

```markdown
# BioMed-Agent  ← 名字
## Multi-Agent System for Biomedical Literature-Guided Multi-Omics Analysis  ← 一句话

[架构图]  ← 一张图说清楚

[![Build](badge)] [![Python](badge)] [![License: MIT](badge)]

## 🚀 Quick Start
```bash
pip install biomed-agent
python -m biomed_agent.demo.run_literature_review \
  --question "CSTB in colorectal cancer prognosis"
```
→ 5 行命令产出第一个结果

## 📊 Benchmark Results
| Task | Ours | Naive LLM | ReAct | Simple RAG |
|------|------|-----------|-------|------------|
| T1-LIT | 78.3 | 42.1 | 61.5 | 68.2 |
| T2-GDA | 71.5 | 38.7 | 55.3 | 60.1 |
| T3-DEG | 83.2 | 25.4 | 52.8 | 45.6 |
| T4-SURV | 76.8 | 30.1 | 48.3 | 42.9 |
| T5-DRUG | 69.4 | 35.2 | 51.7 | 48.3 |

## 📖 Documentation
- [Architecture](ARCHITECTURE.md)
- [Benchmark Design](BENCHMARK.md)
- [Case Study: CSTB in Colorectal Cancer](CASE_STUDY.md)
- [Technical Report (PDF)](paper/report.pdf)

## 🧪 Try It Yourself
[3 个 Demo 的说明，各 3-5 行命令]

## 📝 Citation
```bibtex
@article{biomed-agent-2026, ...}
```

## 📄 License
MIT
```

### 3.2 15 分钟面试 PPT 的叙事结构

**复用 TAOR demo PPT 的配色和画风**（warm navy + coral, hand-drawn illustration for concept pages）。你已经有 `build-ppt.js`（PptxGenJS），直接改内容即可。

| # | 标题 | 内容 | 时长 | 对应 JD |
|---|------|------|------|---------|
| 1 | 标题页 | BioMed-Agent + 一句话 + 你的名字 | 30s | — |
| 2 | 问题 | 生物医学研究的瓶颈：数据碎片化 × 文献爆炸 × AI 幻觉 | 1min | 背景 |
| 3 | 我们的方案 | 4-Agent 协作架构图 | 1min | 方向④ |
| 4 | Agent 1: Literature | PubMed→RAG→证据链→假设 | 1.5min | 方向② |
| 5 | 证据链（技术深潜） | 如何反幻觉——结构化证据链 vs 自由文本摘要 | 1.5min | 方向① |
| 6 | Agent 2-3: Orchestration + Analysis | LLM 驱动的动态 DAG + 工具调用 | 1.5min | 方向①③ |
| 7 | Agent 4: Report | 多源整合 → 结构化报告 | 30s | 方向④ |
| 8 | Benchmark | 5 任务 × 4 metrics × 3 baselines 结果表 | 1.5min | 方向⑤ |
| 9 | Case Study: CSTB | 从文献到发现的完整闭环 | 2min | 方向③ |
| 10 | 我的背景 & 技能 | 3 个项目经验 + 技能矩阵 | 1min | 自我介绍 |
| 11 | 我想在这个实习中做的事 | 3 个具体方向 | 1min | 契合度 |
| 12 | 谢谢 + 链接 | GitHub + 报告 PDF + 联系方式 | 30s | — |

**总时长**：约 14 分钟，留 1 分钟 buffer。

**关键设计原则**：
- 每张幻灯片最多 1 个核心观点
- 第 5 张（证据链）是"技术深潜"幻灯片——展示你思考的深度，这是区分你和"调 API 的人"的关键时刻
- 第 10 张要把 Harness Engineer (TAOR) 和 ITIP/CSTB/Spatial Agent 作为"相关经验"简要提及——证明你不是只做了这一个项目

### 3.3 简历上的项目描述

```markdown
**BioMed-Agent: Multi-Agent System for Biomedical Research** (Python, 2026)
- 设计并实现了 4-Agent 协作系统：Literature Agent (PubMed + RAG + 向量检索
  + 结构化证据链)、Orchestration Agent (LLM 驱动的动态 DAG 生成)、Analysis 
  Agent (TCGA/GEO/GDSC2 工具调用)、Report Agent (多源整合 + 自动报告)
- 构建了生物医学 RAG pipeline，通过结构化证据链（EvidenceLink）降低 LLM 
  幻觉率，在 5-task benchmark 上对比 3 个 baseline
- 定义了面向生物医学 Agent 的评测框架：5 类任务 × 4 维 metrics × 50 test 
  cases，系统分析了现有 LLM 在专业科研任务中的能力与局限
- 在 CSTB-CRC 案例研究中完成从文献→假设→多组学验证→药物筛选的闭环演示
  技术栈：Python, ChromaDB, OpenAI/DeepSeek API, PubMed EUtils, TCGA/GDC, 
  R (survival/limma), Scanpy/AnnData
```

### 3.4 面试 Q&A 准备文档

```markdown
# 面试常见问题准备

## 技术类
1. "你的 Agent 和 LangChain Agent 有什么本质区别？"
2. "为什么不用 LangChain 或 AutoGen 而要自己实现？"
3. "结构化证据链怎么防止 LLM 编造引用？效果如何？"
4. "AnalysisAgent 的失败恢复是怎么工作的？"
5. "Benchmark 的 ground truth 怎么构建的？如何确保它本身不是有偏的？"
6. "系统最大的瓶颈是什么？"

## 生物医学类
7. "LLM 在生物医学中的幻觉问题你怎么看？有什么缓解策略？"
8. "你在 CSTB case study 中发现的结论，和已知文献一致吗？有不一致的地方吗？"
9. "如果让你设计一个药物发现 Agent，你会在现有系统上加什么？"

## 研究与工程类
10. "这个项目如果继续做下去，你最想做哪个方向？"
11. "你在项目中最大的技术挑战是什么？怎么解决的？"
12. "开源项目的反馈如何？有人提 issue 或 PR 吗？"
```

每个问题准备 1-2 分钟的答案。答案结构：**直接回答 → 具体例子 → 诚实说局限性**。

---

## 四、产出物清单

| 产出 | 路径 | 用途 |
|------|------|------|
| GitHub README (英文) | `README.md` | 面试官的第一印象 |
| GitHub README (中文) | `README_CN.md` | 中文面试官的补充 |
| 架构文档 | `ARCHITECTURE.md` | 给想深入了解的读者 |
| Benchmark 文档 | `BENCHMARK.md` | 给只看 benchmark 的读者 |
| 案例文档 | `CASE_STUDY.md` | CSTB 完整案例分析 |
| 技术报告 PDF | `paper/report.pdf` | writing sample |
| 面试 PPT | `presentation/biomed-agent-demo.pptx` | 15 分钟面试演讲 |
| 面试 Q&A | `presentation/interview-qa.md` | 面试前的自测 |
| CI 配置 | `.github/workflows/ci.yml` | lint + test |
| 项目网站（可选） | `docs/` → GitHub Pages | 更丰富的展示 |

---

## 五、成功标准

### P0

- [ ] GitHub README 在 30 秒内能让一个不知道这个项目的人说出"这是做什么的"
- [ ] Quick Start 命令真的能跑通（在干净的 venv 中测试）
- [ ] Benchmark 结果表有真实的数字（不是占位符）
- [ ] PPT 的核心 12 张幻灯片完成
- [ ] 简历上的项目描述完成

### P1

- [ ] 面试 Q&A 文档中至少 10 个问题有准备好的答案
- [ ] 至少 1 个人（不是你自己）跑通了 Quick Start
- [ ] CI 通过（lint + test）

### P2

- [ ] GitHub Pages 上线
- [ ] 录了一个 5 分钟的 demo video（录屏 + 画外音）

---

> **打开独立 Claude 窗口时**，把此文档和 `00-master-coordination.md` 一起粘贴。告诉它：「请基于这两个文档，帮助我准备面试投递材料。先 Review 我 Step 1-4 的实际产出，然后和我讨论 §三 中每个材料的具体内容。」
