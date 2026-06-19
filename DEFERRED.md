# DEFERRED.md — 已知局限 & 延期项追踪

> **规则**：1.3 集成验证时必须逐项确认。Step 完成前所有 DEFERRED 项要么关闭要么升级为 BLOCKER。

---

## 1.0 — Step 1

| ID | 来源 | 描述 | 严重程度 | 触发条件 | 状态 |
|----|------|------|---------|---------|------|
| D1-01 | 1-B MINOR #2 | V4 一致性检查缺基因名归一化 (CSTB ≠ cystatin B) | LOW | 出现跨 claim 矛盾但漏检时修复 | ⬜ DEFERRED |
| D1-02 | 1-C synthesizer | V2 基因名验证缺 NCBI gene_info 符号数据库（仅黑名单过滤） | LOW | 出现幻觉基因名逃过黑名单时修复 | ⬜ DEFERRED |
| D1-03 | 1-C literature_agent | QUESTION_DECOMPOSE / AGENT_THINK 的 Layer 1 约束为缩写版 | LOW | 这些 prompt 不生成科学主张，缩写足够 | ⬜ DEFERRED |

---

> **最后更新**：2026-06-18 — 1.2 代码审查后创建
