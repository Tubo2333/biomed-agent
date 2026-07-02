# BioMed-Agent Runtime Benchmark Results

> Collected: 2026-07-02 04:46 UTC
> Model: deepseek-v4-pro
> Agent: LiteratureAgent (PubMed retrieval + evidence synthesis + hypothesis generation)

## Per-Task Metrics

| 任务 | 类型 | 难度 | 耗时(s) | Token | 工具调用 | 论文数 | 假设数 | 成本($) | 成功 |
|------|------|------|---------|-------|---------|--------|--------|---------|------|
| T1 | 文献综述 | simple | 482.7 | 45762 | 5 | 29 | 2 | $0.0096 | OK |
| T2 | 文献综述 | simple | 479.5 | 46336 | 6 | 30 | 2 | $0.0098 | OK |
| T3 | 文献综述+关联推理 | medium | 277.6 | 15142 | 2 | 10 | 3 | $0.0032 | OK |
| T4 | 文献综述+多组学 | hard | 551.3 | 52076 | 5 | 26 | 3 | $0.0109 | OK |
| T5 | 文献综述+多组学 | medium | 149.0 | 4899 | 1 | 1 | 2 | $0.0012 | OK |
| **平均** | | | **388.0** | **32843** | **3.8** | **19.2** | **2.4** | **$0.0069** | **5/5** |

## Summary

| 指标 | 数值 |
|------|------|
| 任务总数 | 5 |
| 成功率 | 5/5 (100%) |
| 平均耗时 | 388.0s |
| 平均 Token/任务 | 32843 |
| 平均成本/任务 | $0.0069 |
| 总成本 (5 任务) | $0.0347 |
| 失败数 | 0 |

## Analysis

**瓶颈**：单任务平均耗时 388.0s（6.5 分钟），最慢的 T4（免疫检查点抑制剂生物标志物，跨多种癌症）花了 551s。耗时大头是 PubMed EUtils API 往返（每轮 esearch+efetch 共 2 次 HTTP 调用，GFW 代理下延迟显著）和 LLM 证据整合（T4 单次 EvidenceSynthesis 消耗 ~2000 input tokens）。T5 仅 149s 是因为 PubMed 两次返回 0 结果，Agent 只用 1 篇论文完成了整合。

**最贵环节**：EvidenceSynthesis 和 HypothesisGeneration 是 token 大户。T4 单任务消耗 52,076 tokens（input 约 35K + output 约 17K），是 T3（15K tokens）的 3.5 倍——差异来自论文数量（26 vs 10）和问题复杂度。Depth 驱动 token 的规律很明显：论文多 → 证据链长 → token 开销大。

**Thinking mode 的代价**：T2 的 4 次 LLM 调用都因为 thinking mode 耗尽 max_tokens 预算，文本块为空，系统降级到 thinking content tail。这导致证据整合质量下降，但没有崩溃。如果 thinking_budget_tokens 设得太高或 max_tokens 太低，这个问题会频繁出现。

**成功率**：5/5（100%）。但 T1 有一条 EvidenceLink 被 Layer 2 硬检测拦截（LLM 声称 strength=strong 但同时存在 counter_evidence），系统正确拒绝了该主张——反幻觉防线在实际运行中生效了。

**错误恢复**：T1 的 PubMed 首次请求 502（GFW 代理抖动），自动 retry 后成功。T3 的问题分解 JSON 被截断（Unterminated string），Agent 降级为用原始问题直接检索——F2 参数错误恢复生效。

## Notes

- 所有数据来自真实 LLM 调用，非模拟
- 模型定价：DeepSeek v4-pro — $0.14/M input, $0.28/M output
- 测试环境：Windows 11, Python 3.12, proxy @ 127.0.0.1:7892
- 工具调用仅统计 LiteratureAgent 的 PubMed 检索 + LLM Rerank 轮次
