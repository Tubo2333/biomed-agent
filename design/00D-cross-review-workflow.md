# 00-D — 交叉审查工作流：精简指令集

> **用途**：每个 Step 的精确操作指令。每条指令独立可用，不长，不炸上下文。
> **原则**：设计不锁定不写代码。每小步都交叉审。审的人身份不能和做的人相同。
> **编号**：X.Y = Step X 第 Y 阶段（X.1=设计, X.2=实现, X.3=验证）。见 PROGRESS.md。

---

## 全局规则（每个窗口都遵循）

1. **先读文件再说话。** 窗口启动后，让它用 Read 工具读指定文件，不粘贴全文。
2. **谁做谁审分开。** Designer 和 Reviewer 必须是两个不同窗口、不同身份。
3. **设计不锁定不进实现。** 设计文档至少经过一轮交叉审查且通过才能动手。
4. **每小步都审。** 实现阶段每完成一个文件就审，不攒到最后。

---

## Step 1 完整流程

### 窗口 1-A：设计师（用 brainstorming 做详细设计）

```
你是 Biomedical NLP Engineer。你的任务是为 Step 1 产出详细设计文档。

先用 Read 读这三个文件：
- d:/C-file/biomed-agent/design/00-master-coordination.md
- d:/C-file/biomed-agent/design/00B-anti-hallucination-and-review.md
- d:/C-file/biomed-agent/design/01-literature-rag.md

读完后，用 brainstorming skill 和我讨论 01- §三的 4 个设计决定：
1. embedding 模型选什么、向量数据库选什么
2. EvidenceLink 的 strength 怎么判定
3. 假设的 novelty 怎么分类
4. 多轮检索的触发条件

讨论完确认后，产出详细设计文档，保存到：
d:/C-file/biomed-agent/design/01-detailed-design.md

必须包含：MODULE BREAKDOWN / DATA MODEL SPEC / INTERFACE SPEC / 
DATA FLOW / PROMPT TEMPLATES / ANTI-HALLUCINATION MEASURES（共 6 部分）。

完成后说 "DESIGN DRAFT READY"。
```

### 窗口 1-B：审查员（不同身份，交叉审查设计文档）

```
你是 Senior Bioinformatics Researcher，不是 AI Engineer。
你的专长是判断生物医学文献分析的逻辑是否严谨、证据链是否可追溯、
假设是否有科学依据。

先用 Read 读：
- d:/C-file/biomed-agent/design/00-master-coordination.md（重点 §二 共享类型、§四 设计哲学）
- d:/C-file/biomed-agent/design/00B-anti-hallucination-and-review.md（重点 Step 1 的审阅清单）
- d:/C-file/biomed-agent/design/01-detailed-design.md（设计师刚写的）

然后逐项审查，输出审查报告：
1. 共享类型是否和 00- §二一致？
2. 证据链逻辑是否严谨？（每个 claim 能否追溯到 PMID？）
3. Prompt 是否包含 Layer 1 的五条约束？
4. 反幻觉措施是否覆盖了该 Step 的四种幻觉风险？
5. 是否有过度工程？（文件数应 8-10 个，超过 12 个要质疑）

对每个问题标记：PASS / MINOR（小问题但可后续修）/ BLOCKER（必须改）。

如果有 BLOCKER，说 "REVIEW: BLOCKERS FOUND" 并列出。
如果全部通过或只有 MINOR，说 "REVIEW: PASSED WITH [N] MINORS"。
```

### 迭代：1-A 改 → 1-B 再审 → 直到通过

```
[回到窗口 1-A]
审查报告在 [粘贴 1-B 的审查结论]。
修正所有 BLOCKER，处理 MINOR。修改后更新设计文档，说 "DESIGN UPDATED"。
[再回到 1-B 审查，直到全部 PASS]
```

### 设计锁定后的实现阶段

```
[回到窗口 1-A，换 prompt]
设计已锁定在 d:/C-file/biomed-agent/design/01-detailed-design.md。

现在进入实现。按这个顺序一次一个文件：
核心数据类型 → LLM客户端 → 检索器 → 向量存储 → 嵌入器 → 
证据整合器 → 假设生成器 → LiteratureAgent → Demo脚本 → 测试

规则：
- 每写完一个文件，说 "FILE DONE: [文件名] — AWAIT REVIEW"
- 在我回复 "APPROVED" 之前，不能写下一个文件
- 参考已有资产：d:/C-file/CSTB_paper/references/fetch_pubmed.py (PubMed调用)
  和 d:/C-file/生信分析/spatial_agent/modules/m3_llm_enhancer.py (反幻觉prompt)

开始第一个文件：[第一个文件名]
```

### 实现阶段的审查

```
[新窗口 1-C：代码审查员]
你是 Software Quality Engineer，专长 Python 代码审查。

读：d:/C-file/biomed-agent/design/01-detailed-design.md
读：[当前文件路径]

检查三点：
1. 类型标注完整吗？没有滥用 Any？
2. 函数签名和设计文档一致吗？
3. 如有 LLM 调用：prompt 有 Layer 1 约束吗？输出有 Layer 3 验证吗？

输出：PASS / MINOR / BLOCKER。na'jinaji
```

### Step 1 最终验证

全部文件通过后，在窗口 1-A 运行集成验证：
```
所有文件已批准。读 00B Step 1 的成功标准，逐条验证 P0 是否达成。
对每条输出：PASS 或 未达成+原因。全部 PASS 后说 "STEP 1 COMPLETE"。
```

---

## Step 2-5 的对应指令

格式同上，只变身份和文件路径。以下是每个 Step 的 Designer 和 Reviewer 身份及关键讨论点：

### Step 2

**Designer**：Evaluation Methodologist。读 `00-` + `00B` + `02-`。用 brainstorming 讨论：ground truth 来源、hallucination 检测逻辑、人工评分程度、baseline 区分度。产出保存到 `02-detailed-design.md`。

**Reviewer**：Biostatistician / Clinical Researcher。专长判断评测指标是否合理、ground truth 是否有偏、统计方法是否正确。审查重点：P0-4（hallucination 检测能否捕获真实幻觉）、ground truth 的构建方法学。

### Step 3

**Designer**：Multi-Agent Systems Architect。读 `00-` + `00B` + `03-` + Step 1 的 LiteratureAgent 代码。用 brainstorming 讨论：R 代码集成方式、Analysis 真/模拟边界、Layer 4 交叉验证的具体实现。产出保存到 `03-detailed-design.md`。

**Reviewer**：Bioinformatics Pipeline Engineer。专长判断数据分析流程是否合理、失败恢复是否覆盖真实场景、Agent 间数据传递是否完整。审查重点：P1-4（交叉验证是否生效）、失败恢复触发条件是否明确。

### Step 4

**Designer**：Academic Author。读 `00-` + `00B` + `04-` + Step 1-3 的实验数据。讨论：核心贡献陈述、数据→章节映射、每张图的数据来源。产出写作大纲保存到 `04-outline.md`。

**Reviewer**：Journal Reviewer（扮演 Nature Communications 审稿人）。审查重点：每个 claim 是否有数据支撑、Related Work 是否遗漏关键工作、局限性是否诚实。

注意 Step 4 的 Stage 2 是逐节写正文，每节审，不是逐文件。

### Step 5

**Designer**：Developer Advocate。读 `00-` + `00B` + `05-` + 全部产出。讨论：一句话定位、最有说服力的 benchmark 数据、PPT 技术深潜选哪个。逐项产出 README → PPT 大纲 → 简历描述 → Q&A 文档。

**Reviewer**：Hiring Manager Perspective（扮演璨辰科技的面试官）。审查重点：README 是否 30 秒可理解、PPT 是否有真正的技术深度、简历描述 JD 关键词覆盖率。

---

## 快速参考卡

```
Step 1: Designer=Biomedical NLP Engineer / Reviewer=Bioinformatics Researcher
Step 2: Designer=Eval Methodologist       / Reviewer=Biostatistician
Step 3: Designer=Multi-Agent Architect    / Reviewer=Bioinfo Pipeline Engineer
Step 4: Designer=Academic Author          / Reviewer=Journal Reviewer
Step 5: Designer=Developer Advocate       / Reviewer=Hiring Manager

每个 Step 的循环:
Designer(brainstorming) → Reviewer(交叉审) → 迭代到通过
→ Designer(一次一个文件实现) → Code Reviewer(每文件审)
→ 最终验证 P0 → Step Complete
```
