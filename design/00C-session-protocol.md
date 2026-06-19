# 00-C — 窗口会话协议：如何让每个 Step 做得又完整又好又不跑偏

> **读者**：你自己（作为每个窗口的启动者和审阅者）
> **用途**：精确到每个阶段的 prompt 模板、审阅方法、跑偏检测信号
> **核心理念**：设计→审阅→修改→锁定→实现→审阅→修改→锁定→完成。永不跳步。

## 编号约定

| 文档中旧称 | 新编号 | 含义 |
|-----------|--------|------|
| Stage 1 | **X.1** | 设计深化 |
| Stage 2 | **X.2** | 增量实现 |
| Stage 3 | **X.3** | 集成验证 |
| Step 1 | **1.0** | 文献推理 Agent + RAG |
| Step 2 | **2.0** | Benchmark |
| Step 3 | **3.0** | 多 Agent Pipeline |
| Step 4 | **4.0** | 技术报告 |
| Step 5 | **5.0** | 投递打包 |

例：1.2 = Step 1 的增量实现；3.1 = Step 3 的设计深化。

---

## 一、为什么窗口会跑偏

独立窗口最大的敌人不是能力不足，是**上下文漂移**。五个常见漂移模式：

| 漂移模式 | 表现 | 根因 |
|---------|------|------|
| **范围蔓延** | 窗口开始做 Step 3 的事，尽管它被分配的是 Step 1 | 没有明确的边界约束 |
| **过度工程** | 为了一个简单的 retriever 写了一个插件系统 | 没有"够好就行"的标准 |
| **哲学偏离** | 窗口决定用 LangChain 而不是我们定义的 Agent 模式 | 没有在启动时锁定设计哲学 |
| **忽略上游** | 窗口定义了自己的 Paper 类型，和 `00-` 里的不一样 | 没有强制要求读共享类型 |
| **跳过审阅** | 窗口直接开始写代码，没有先和你确认设计 | 没有强制执行阶段门控 |

---

## 二、每个窗口的三阶段门控

```
┌─────────────────────────────────────────────────────────┐
│                    会话生命周期                          │
│                                                         │
│  STAGE 1: DESIGN DEEPENING                              │
│  ─────────────────────                                  │
│  输入: Step设计方向文档 + 00- + 00B                      │
│  输出: 详细设计文档 (每个模块的精确接口+数据流+伪代码)     │
│  门控: 你审阅通过 → 锁定设计 → 进入 Stage 2              │
│  禁止: 写任何实现代码                                    │
│                                                         │
│  STAGE 2: INCREMENTAL IMPLEMENTATION                    │
│  ─────────────────────────────                          │
│  输入: Stage 1 锁定的详细设计                             │
│  输出: 逐个文件的实现代码 + 测试 + 运行验证               │
│  门控: 每完成一个文件 → 审阅 → 锁定 → 下一个文件          │
│  禁止: 跳过审阅直接写下一个文件                           │
│                                                         │
│  STAGE 3: INTEGRATION VERIFICATION                      │
│  ───────────────────────────                            │
│  输入: Stage 2 的全部代码                                 │
│  输出: 对00-中定义的共享接口的兼容性验证报告               │
│  门控: 所有 P0 成功标准达成 → Step 完成                   │
└─────────────────────────────────────────────────────────┘
```

**每个 Stage 之间，你必须主动说"通过"或"不通过"。不通过就停留在当前 Stage 继续修改直到通过。**

---

## 三、Stage 1：设计深化 — 让窗口把方向文档变成精确设计

### 3.1 启动 prompt 模板

在窗口的第一条消息中粘贴以下内容（替换 `[STEP_NUMBER]` 和 `[ROLE]`）：

```
=== CONTEXT DOCUMENTS ===
[粘贴 00-master-coordination.md 全文]

[粘贴 00B-anti-hallucination-and-review.md 全文]

[粘贴 0[N]-[step-name].md 全文]

=== SESSION INSTRUCTIONS ===

你是 [ROLE]。你的任务是完成 Step [N] 的详细设计。

⛔ STAGE 1 RULES (CURRENT STAGE):
- 你只能做设计，不能写任何实现代码。
- 如果我在任何时候说 "REVIEW BLOCKER: [具体问题]"，你必须
  先解决这个问题再继续。
- 如果你在设计中发现需要修改 00-master-coordination.md 
  中的共享类型，必须先向我提出并等我确认。

📋 你需要产出的详细设计文档必须包含以下 6 个部分：

1. MODULE BREAKDOWN
   列出该 Step 需要的每一个 .py 文件
   每个文件：文件名、单一职责（一句话）、大约行数、依赖的其他文件

2. DATA MODEL SPEC
   定义该 Step 产出/消费的每一个 dataclass
   每个 dataclass：所有字段及其类型、必填/可选、验证规则
   如果某个类型已在 00- 中定义，直接引用，不要重新定义

3. INTERFACE SPEC
   定义该 Step 暴露给其他 Step 的每一个 public 函数/类
   每个接口：函数签名、参数类型、返回值类型、异常类型
   标注哪些接口是其他 Step 依赖的（从 00- 中确认）

4. DATA FLOW DIAGRAM (文字版)
   从输入到输出的数据流
   每个处理步骤：输入数据类型 → 处理逻辑 → 输出数据类型
   标注哪一步调用了 LLM

5. PROMPT TEMPLATES
   该 Step 中每一个 LLM 调用的 system prompt 和 user prompt 模板
   每个 prompt 必须包含 00B 中 Layer 1 的 5 条约束
   标注每个 prompt 的输入变量和预期输出格式

6. ANTI-HALLUCINATION MEASURES
   该 Step 实现了 00B 中哪些层的防线
   每层防线：具体代码位置（哪个文件）、验证逻辑（伪代码）
   该 Step 特有的幻觉风险和应对

⏸️ 完成以上 6 部分后，输出 "DESIGN COMPLETE — AWAITING REVIEW"。
   在我说 "DESIGN APPROVED" 之前，不要写任何实现代码。
```

### 3.2 你收到 "DESIGN COMPLETE" 后的审阅步骤

**第一遍：结构完整性检查**（5分钟）
- [ ] 6 个部分都写了吗？有没有跳过的？
- [ ] 每个部分有实质内容吗？（不是"待定"、"后续确定"）
- [ ] 引用了 00- 中的共享类型吗？（如果没有引用 → 它可能在重新发明轮子）

**第二遍：接口一致性检查**（10分钟）
- [ ] 该 Step 暴露的接口是否和 00- 中"导出给其他 Step"的一致？
- [ ] 该 Step 消费的接口是否和 00- 中"消费其他 Step"的一致？
- [ ] 数据类型是否和 00- §二 中的定义一致？如果新增了类型，是否需要回写 00-？

**第三遍：哲学一致性检查**（5分钟）
- [ ] Agent 设计是否符合 00- §四的约定（Think→Act→Observe，不是 LLM+工具列表）？
- [ ] 反幻觉策略是否符合 00B 的五层框架？
- [ ] Prompt 模板是否包含 Layer 1 的 5 条约束？

**第四遍：可行性检查**（5分钟）
- [ ] 有没有依赖不存在的东西？（如"用 GPU 跑 PubMedBERT"但你没有 GPU）
- [ ] 文件数量是否合理？（Step 1 应该 8-10 个文件，不是 30 个）
- [ ] 有没有明显的过度工程？（如为 2 个 LLM 调用写了一个"统一的 LLM 抽象工厂"）

### 3.3 常见的 Stage 1 跑偏信号

| 跑偏信号 | 你应该说的话 |
|---------|------------|
| 设计文档中有 "TODO: figure out later" | "REVIEW BLOCKER: 设计阶段不能有 TODO。如果你不确定某个设计决定，现在提出来讨论。" |
| 定义了和 00- 冲突的类型 | "REVIEW BLOCKER: Paper 类型已在 00- §2.1 中定义。你必须复用那个定义，不能重新定义。如果需要修改 00-，现在提出。" |
| 开始写代码了 | "⛔ 你在 Stage 1。Stage 1 只能设计。删掉代码，回到设计文档。" |
| 过度简化（"让 LLM 自己决定"） | "REVIEW BLOCKER: '让 LLM 自己决定'不是设计。你需要给出具体的 prompt 模板、输入格式、输出解析逻辑。" |
| 文件数量太多（>15个文件） | "WARNING: 你设计了 N 个文件。Step 1 的目标是 8-10 个文件。检查是否有可以合并的。" |

### 3.4 确认通过的话术

如果审阅通过：
```
DESIGN APPROVED. 进入 Stage 2。

在 Stage 2 中：
- 一次实现一个文件
- 每完成一个文件，输出 "FILE COMPLETE: [filename] — AWAITING REVIEW"
- 在我说 "FILE APPROVED" 之前，不要开始下一个文件
- 实现顺序：核心数据类型 → 基础工具 → LLM 客户端 → Agent 逻辑 → Demo 脚本
```

如果有修改意见：
```
DESIGN NOT APPROVED. 以下问题需要修改：

1. [具体问题 1] — 期望的修改：[具体期望]
2. [具体问题 2] — 期望的修改：[具体期望]

修改后重新输出 "DESIGN COMPLETE — AWAITING REVIEW"。
```

---

## 四、Stage 2：增量实现 — 一步一步走，每步都审

### 4.1 实现顺序（强制）

不管哪个 Step，实现必须遵循这个顺序：

```
Phase A: 核心数据类型 (定义该 Step 的 dataclass)
    ↓
Phase B: 基础设施 (LLM 客户端、工具基类、配置加载)
    ↓
Phase C: 功能模块 (按依赖顺序，从最底层到最上层)
    ↓
Phase D: Agent 主体 (Think→Act→Observe 循环)
    ↓
Phase E: Demo 脚本 (可运行的端到端示例)
    ↓
Phase F: 测试 (验证正确性)
```

窗口不能在 Phase A 完成之前碰 Phase C。每个 Phase 内部，一次一个文件。

### 4.2 每个文件的审阅协议

窗口每完成一个文件，输出 `FILE COMPLETE: [filename] — AWAITING REVIEW`。

你检查三个东西：

**检查 1：类型标注**
- [ ] 所有函数有 type hints？
- [ ] 没有 `Any` 类型的滥用？（允许在 LLM 响应解析处使用，不允许在核心逻辑中使用）
- [ ] 导入的类型是否来自正确的位置？（共享类型来自 `00-` 的定义，不是本地重复定义）

**检查 2：与设计文档一致性**
- [ ] 函数签名是否和 Stage 1 中定义的接口一致？
- [ ] 数据结构是否和 Stage 1 中定义的 Data Model 一致？
- [ ] 如果有不一致——设计文档需要更新，还是代码需要修改？

**检查 3：反幻觉措施到位**
- [ ] 如果该文件包含 LLM 调用：prompt 是否包含 Layer 1 约束？
- [ ] 如果该文件处理 LLM 输出：是否有 Layer 3 验证逻辑？
- [ ] 如果该文件定义数据结构：是否有 Layer 2 溯源字段？

### 4.3 常见的 Stage 2 跑偏信号

| 跑偏信号 | 你应该说的话 |
|---------|------------|
| 同时提交了 3 个文件 | "⛔ Stage 2 规则：一次一个文件。我只审阅你最后提交的那个。把其他的撤回。" |
| 代码中有 `# TODO` | "REVIEW BLOCKER: Stage 2 不能有 TODO。如果某个功能你还没实现，先标记为 `raise NotImplementedError` 并说明原因。" |
| 跳过测试 | "REVIEW BLOCKER: 每个文件至少需要一个对应的 test case。为 [filename] 补充测试。" |
| 实现偏离了设计 | "REVIEW BLOCKER: 你在 Stage 1 中设计的是 [X]，但你实现的是 [Y]。解释为什么偏离了设计。如果偏离是合理的，先更新设计文档。" |

### 4.4 文件批准话术

```
FILE APPROVED: [filename]. 继续下一个文件。
当前进度: [N]/[Total] 文件完成。
下一个文件: [next filename] — 它的职责是 [一句话]。
```

---

## 五、Stage 3：集成验证

所有文件完成后，窗口输出 `ALL FILES COMPLETE — AWAITING INTEGRATION VERIFICATION`。

### 5.1 集成验证 prompt

```
现在进入 Stage 3: Integration Verification。

请完成以下验证并输出报告：

1. INTERFACE COMPATIBILITY CHECK
   - 该 Step 导出给其他 Step 的接口是否和 00-master-coordination.md 一致？
   - 该 Step 消费其他 Step 的接口是否和预期一致？
   - 如果有不一致，标记为 BLOCKER。

2. ANTI-HALLUCINATION COVERAGE CHECK
   - 遍历该 Step 中每一个 LLM 调用点
   - 确认每个调用点都有对应层的防线
   - 列出覆盖率: N/N LLM 调用点有防线

3. P0 SUCCESS CRITERIA CHECK
   - 参考 00B 中该 Step 的 P0 成功标准
   - 逐条验证是否达成
   - 如果未达成，标记为 BLOCKER

4. CROSS-STEP DATA FLOW VERIFICATION
   - 该 Step 的输入是否可以从上游 Step 的输出中获取？（如果不是 Step 1）
   - 该 Step 的输出格式是否可以被下游 Step 消费？（如果不是 Step 5）

输出格式：
   PASS: [通过的检查项]
   WARNING: [非致命的注意项]
   BLOCKER: [必须修复的问题]
```

### 5.2 最终确认

如果 Stage 3 没有 BLOCKER：
```
STEP [N] COMPLETE.
该 Step 的最终产出:
- 代码: [列出所有文件]
- 数据: [列出所有数据产出]
- 接口: [列出对其他 Step 的导出]

如果该 Step 做出了任何影响 00-master-coordination.md 的决定，
现在回写到 00- 的 §六 决策日志。
```

---

## 六、你开每个窗口前需要检查的启动清单

打开窗口前，确认你手上有这些材料：

- [ ] `00-master-coordination.md` — 全文
- [ ] `00B-anti-hallucination-and-review.md` — 全文
- [ ] `0[N]-[step-name].md` — 该 Step 的设计方向文档（全文）
- [ ] 该 Step 依赖的上游产出（Step 1 无上游依赖；Step 2 依赖 S1 的类型定义；Step 3 依赖 S1 完整实现 + S2 类型；Step 4 依赖 S1-S3 实验数据；Step 5 依赖全部）
- [ ] 该 Step 可复用的已有资产列表（在每个 Step 设计文档的 §二 中列出）
- [ ] 本文档 §三（Stage 1 启动 prompt 模板）

---

## 七、关于 Brainstorming Skill 的使用

`brainstorming` skill 适合在 **Stage 1 的前半段** 使用——当你和窗口讨论设计决定、需要发散思考时。但不适合在整个 Stage 1 全程使用。

**什么时候用 brainstorming**：
- 面对 §三中的"需要在这个窗口内做出的设计决定"时
- 例如 Step 1：embedding 模型选什么、向量数据库选什么、EvidenceLink 的 strength 怎么判定
- 例如 Step 3：R 代码集成方式、AnalysisAgent 真/模拟执行的边界

**什么时候不用 brainstorming**：
- 已经在执行 Stage 2（写代码）时
- 已经做了设计决定并锁定后
- 做审阅检查时（审阅是收敛的，不是发散的）

**如果你在一个窗口中用 brainstorming**，在 prompt 中加上这个约束：

```
使用 brainstorming skill 探索以下设计选择的 trade-off:
[具体的 2-3 个设计问题]

约束：
- 所有选项必须与 00-master-coordination.md §四的设计哲学一致
- 不能选择与已有资产冲突的方案（例如不能假设有 GPU）
- 不能选择需要安装 10+ 个新依赖的方案
- 探索完成后，你需要给出推荐选项 + 理由，然后等待我确认
```

---

## 八、快速参考卡（给你贴在屏幕上的）

```
┌──────────────────────────────────────────────────────────┐
│              窗口会话速查表                               │
├──────────────────────────────────────────────────────────┤
│ 启动: 粘贴 00- + 00B + 0N + Stage 1 prompt              │
│                                                          │
│ Stage 1: 设计深化                                        │
│   窗口输出: DESIGN COMPLETE — AWAITING REVIEW             │
│   你检查: 结构完整性 → 接口一致性 → 哲学一致性 → 可行性   │
│   你说: DESIGN APPROVED 或 DESIGN NOT APPROVED           │
│                                                          │
│ Stage 2: 增量实现                                        │
│   窗口输出: FILE COMPLETE: xxx — AWAITING REVIEW          │
│   你检查: 类型标注 → 与设计一致 → 反幻觉措施到位          │
│   你说: FILE APPROVED 或 FILE NOT APPROVED               │
│                                                          │
│ Stage 3: 集成验证                                        │
│   窗口输出: 4 项验证报告                                  │
│   你说: STEP COMPLETE 或 列出 BLOCKER                    │
│                                                          │
│ 跑偏关键词: TODO / 让LLM自己决定 / 一次提交多个文件       │
│ 你的武器: REVIEW BLOCKER / ⛔ Stage N 规则 / 先更新设计   │
└──────────────────────────────────────────────────────────┘
```

---

> **总结**：三个 Stage，两个门控（DESIGN APPROVED 和 STEP COMPLETE），N 个文件级审阅。每次窗口说 "AWAITING REVIEW" 时，你停下来检查。每次你发现问题时，说 "REVIEW BLOCKER"。不跳步，不妥协，不因为"看起来差不多"就放行。
