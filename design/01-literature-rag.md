# 01 — Step 1 设计方向：文献推理 Agent + 生物医学 RAG Pipeline

> **目标**：构建一个能从 PubMed 检索论文、嵌入向量化、多论文证据整合、生成可验证假设的 Agent
> **工期**：4-5天
> **依赖**：无外部依赖。定义共享数据类型（Paper, LiteratureReview, Hypothesis）
> **被依赖**：Step 2 消费其类型定义和 Agent 实现；Step 3 消费其 Agent 作为子模块

---

## 一、这个 Step 要回答的核心问题

1. 给定一个生物医学问题（如"CSTB 在结直肠癌中的预后价值"），Agent 如何：
   - 将问题分解为可检索的子问题？
   - 从 PubMed 检索相关论文并筛选？
   - 将论文嵌入向量空间，支持语义检索？
   - 从多篇论文中整合证据（而非简单摘要）？
   - 识别证据之间的冲突？
   - 从证据缺口生成可验证的假设？

2. 这个 Agent 的"好"与"差"如何判断？（为 Step 2 的 Benchmark 提供输入）

---

## 二、已有资产（可直接复用或改写）

| 资产 | 位置 | 可复用内容 |
|------|------|-----------|
| PubMed EUtils 调用模式 | `CSTB_paper/references/fetch_pubmed.py` | esearch + efetch + 解析 XML |
| GFW 探测 + retry | `shared/gfw_probe.py` | proxy_check + 3-retry backoff |
| MCP bridge 工具定义模式 | `Harness_Engineer/packages/mcp/src/bridge.ts` | stdio transport, tools/list, tools/call（改写为 Python） |
| M3-LLM 科学叙事 prompt | `生信分析/spatial_agent/modules/m3_llm_enhancer.py` | "DO NOT fabricate"约束, temperature=0.3, DeepSeek调用 |
| Compressor embed 层设计 | `Harness_Engineer/packages/compressor/src/strategies/embed.ts` | 嵌入检索的设计理念 |
| Zotero 文献管理 | `.claude/skills/zotero-auto-cite/scripts/zotero_bridge.py` | 文献导入/去重/引用格式 |

---

## 三、设计方向（不是实现细节，是方向性的设计选择）

### 3.1 检索策略：混合检索（关键词 + 语义）

**方向**：不依赖单一的 PubMed 关键词搜索。先用 MeSH 词 + 自由词做初步检索，再用 embedding 做语义重排序。

**需要在这个窗口内做出的设计决定**：
- Embedding 模型选什么？选项：(a) OpenAI `text-embedding-3-small`（便宜，1536维，生物医学语义不如专用模型）；(b) PubMedBERT（本地推理，需要 GPU，但生物医学语义更好）；(c) 微软 `BioMedCLIP` 或 `SPECTER2`（专门为科学文献设计的 embedding）。**推荐方向**：先用 (a) 快速跑通，embedding 层抽象成接口，后续可替换。
- 向量数据库选什么？选项：(a) ChromaDB（轻量，Python 原生）；(b) lancedb（更快，列式存储）；(c) 直接用 numpy + json（零依赖，但慢）。**推荐方向**：ChromaDB，因为文档最友好，LangChain 生态成熟（面试时提到可以顺带说"我知道 LangChain 怎么用"）。
- 检索结果多少篇？检索 50 篇 → 语义筛选到 15 篇 → LLM 整合时用 top 10。这个数字需要在真实 query 上测试调整。

### 3.2 证据整合策略：结构化证据链，不是自由文本摘要

**方向**：LLM 不直接输出一段综述文字。而是先输出结构化的"证据链"（claim → supporting evidence → counter evidence → strength），再由证据链生成综述和假设。

**理由**（面试时要说）：
- 自由文本摘要难以验证——你说"CSTB 在 CRC 中高表达"，这句话来自哪篇论文？哪个 Figure？
- 结构化证据链每一步都可追溯到 PMID 和具体数据
- 这是反幻觉的核心机制——如果 LLM 编造了一个 claim 但没有 supporting PMID，系统自动标记为低置信度

**需要在这个窗口内做出的设计决定**：
- EvidenceLink 的 strength 如何判定？选项：(a) LLM 自行判断（快但可能不一致）；(b) 规则：≥3 篇独立研究支持=strong, 1-2篇=moderate, 仅1篇且样本量小=weak；(c) 混合：LLM 初判 + 规则校验。**推荐方向**：(c)，LLM 初判 + 规则校验（如检查是否有 PMID、是否同一课题组重复发表）。

### 3.3 假设生成策略：从证据缺口出发

**方向**：假设不是凭空生成的，而是从"已知-未知"的边界产生的。
- 识别证据缺口（"没有研究 CSTB 和免疫浸润的关联""没有 CSTB 的药物靶点筛选"）
- 基于已有证据链推断（"已知 CSTB 与不良预后相关，机制可能与免疫逃逸有关，因此假设 CSTB 通过 M2 巨噬细胞介导免疫抑制"）
- 每个假设必须有 testable prediction 和 required_data

**需要在这个窗口内做出的设计决定**：
- 假设的 novelty 分类标准：从未被任何检索到的论文直接提出的 = novel；被提出但未验证的 = extension；已有验证但方法不同 = confirmation。
- 假设数量控制在 1-3 个（质量 > 数量）。

### 3.4 Agent 循环设计：Think→Act→Observe，多轮检索

**方向**：不是一轮检索就结束。Agent 在第一轮检索后发现证据不足或方向偏离时，应该自动发起第二轮检索。

```
Think: "用户问 CSTB 在 CRC 中的预后价值。我需要找：(1)CSTB在CRC中的表达数据，(2)CSTB与CRC生存的关联，(3)CSTB在CRC中的功能机制。"
Act: PubMed search "CSTB colorectal cancer prognosis" → 获得 23 篇
Observe: "检索到 23 篇，其中 8 篇直接相关。但是关于免疫机制的证据不足。"
Think: "补充检索 CSTB 与免疫微环境的关系。"
Act: PubMed search "CSTB immune infiltration tumor microenvironment" → 获得 15 篇
Observe: "现在有足够证据整合。开始 synthesize。"
```

**需要在这个窗口内做出的设计决定**：
- 最多几轮检索？推荐 3 轮（初始 + 补充 + 验证）。
- 什么条件触发补充检索？推荐：证据链中某个维度的 supporting_pmids < 2，或 LLM 判断"关于 X 方面的证据不足"。
- 每轮检索的关键词由谁生成？推荐 LLM 根据上一轮的 observation 自动生成。

---

## 四、产出物清单

### 代码文件（放在 `biomed-agent/src/` 下）

| 文件 | 功能 | 大约行数 | 新建/整合 |
|------|------|---------|----------|
| `rag/retriever.py` | PubMed API 调用 + 结果解析 + 缓存 | 300 | 新建（整合 CSTB fetch_pubmed） |
| `rag/embedder.py` | embedding 抽象接口 + OpenAI/text-embedding-3-small 实现 | 150 | 新建 |
| `rag/vector_store.py` | ChromaDB 封装（增删查） | 150 | 新建 |
| `rag/synthesizer.py` | EvidenceSynthesizer: 多论文→证据链→综述 | 300 | 新建 |
| `rag/hypothesis_generator.py` | HypothesisGenerator: 证据缺口→假设 | 150 | 新建 |
| `agents/literature_agent.py` | LiteratureAgent: Think→Act→Observe 循环 | 400 | 新建 |
| `tools/pubmed_tools.py` | PubMed 工具定义（供 Agent tool-calling） | 150 | 整合 |
| `llm/client.py` | 统一 LLM 调用客户端 | 100 | 整合 M3-LLM 模式 |
| `utils/network.py` | GFW 探测 + retry | 50 | 整合 shared/gfw_probe |

### 数据产出

| 产出 | 用途 |
|------|------|
| 10 个真实生物医学 query 的 LiteratureReview 结果 | Step 2 的 benchmark ground truth 候选；Step 4 的案例素材 |
| 每个 query 的 token 用量统计 | Step 2 的 efficiency_score 计算 |
| embedding 缓存的向量数据库文件 | Step 3 的 LiteratureAgent 快速启动 |

### 文档产出

| 文档 | 内容 |
|------|------|
| `design/01-literature-rag.md` 的更新版 | 记录最终的设计决定和理由 |
| `README` 中关于 RAG pipeline 的部分 | 架构简述 + 快速开始 |

---

## 五、成功标准

### 必须达成（P0）

- [ ] LiteratureAgent 能对 10 个不同的生物医学问题产出结构化的 LiteratureReview
- [ ] 每个 LiteratureReview 包含至少 8 篇真实论文（PMID 可验证）
- [ ] 证据链的每个 claim 至少有 1 个 supporting PMID
- [ ] 假设的 testable_prediction 中不包含虚构的基因功能
- [ ] PubMed 检索 + embedding + LLM 全链路在代理可用时跑通
- [ ] 代码可以通过 `from biomed_agent.agents.literature_agent import LiteratureAgent` 导入

### 应该达成（P1）

- [ ] 至少在 3 个 query 上，Agent 自动发起了补充检索（多轮循环）
- [ ] 证据链中至少有 1 处识别了 evidence conflict（如两篇论文结论矛盾）
- [ ] embedding 检索的语义相关性优于纯关键词检索（人肉评估即可）
- [ ] 单次完整 review 的 token 消耗在 5000-15000 之间

### 最好达成（P2）

- [ ] embedding 模型可替换（接口抽象，换模型不改上层代码）
- [ ] 检索结果缓存（同一 query 不重复调 PubMed API）
- [ ] 对 10 个 query 的结果做了人工质量评分（为 Step 2 提供数据）

---

## 六、与其它 Step 的接口

### 导出给 Step 2 的
- `LiteratureReview` 和 `Paper` 和 `Hypothesis` 的 dataclass 定义（**必须在 Step 1 的前 1 天内确定并写入 `00-master-coordination.md`**）
- `LiteratureAgent.run(question)` 方法签名
- 10 个 query 的运行结果（JSON 文件）

### 导出给 Step 3 的
- `LiteratureAgent` 完整实现（作为 Step 3 多 Agent pipeline 的文献调研 Agent）
- `EvidenceSynthesizer` 和 `HypothesisGenerator`（可独立使用）
- `LLMClient`（Step 3 的其它 Agent 共用）

### 导出给 Step 4 的
- 10 个 query 的定量评估数据（检索论文数、证据链数量、假设数量、token 用量）
- 3-5 个最佳案例的详细输出（用作报告中的 qualitative analysis）

---

## 七、关键风险与应对

| 风险 | 可能性 | 应对 |
|------|--------|------|
| PubMed API 在 GFW 下不稳定 | 中 | 已有 3-retry + backoff 模式。增加本地缓存机制 |
| 某些 query 检索结果太少（<5篇） | 中 | Agent 自动扩大搜索范围（去掉癌种限定、增加同义词） |
| LLM 在证据整合时幻觉（编造引用） | 高 | 严格的 post-hoc 验证：每个 claim 的 PMID 必须在检索结果中真实存在 |
| embedding 模型对生物医学术语的语义理解差 | 中 | 先用 text-embedding-3-small 测试，如果效果差则切换到 PubMedBERT |
| DeepSeek API 并发限制 | 低 | 已有 `ANTHROPIC_AUTH_TOKEN` + `ANTHROPIC_BASE_URL` 配置，单线程调用 |

---

> **打开独立 Claude 窗口时**，把此文档和 `00-master-coordination.md` 一起粘贴。告诉它：「请基于这两个文档的设计方向，实现 Step 1 的 Literature Agent + RAG pipeline。先和我讨论 §三 中的设计决定，确认后再开始写代码。」
