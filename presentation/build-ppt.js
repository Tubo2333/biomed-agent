// BioMed-Agent — 学术演讲 PPT (中文为主)
// 12 slides, 16:9, 白底, 高对比度文字
const pptxgen = require("pptxgenjs");
const path = require("path");

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9"; // 10" × 5.625"
pres.author = "BioMed-Agent";
pres.title = "BioMed-Agent";

// ═══════════════════════════════════════
// Color Palette — High contrast on white
// ═══════════════════════════════════════
const C = {
  bg:        "FFFFFF",
  offBg:     "F5F6F8",
  title:     "0D1B2A",  // 深黑蓝
  body:      "1A1A1A",  // 近乎纯黑
  body2:     "444444",  // 次级文字
  gray:      "777777",
  lightGray: "C8CDD4",
  coral:     "C0392B",  // 深红
  coralBg:   "FBEBE9",
  teal:      "0E6655",  // 深绿
  tealBg:    "E0F2EF",
  blue:      "1A5276",  // 深蓝
  blueBg:    "E4F0F8",
  purple:    "5B2C6F",  // 深紫
  purpleBg:  "F0E6F5",
  green:     "1E8449",  // 深绿
  greenBg:   "E5F5EB",
  red:       "922B21",
  redBg:     "FDEDEC",
  white:     "FFFFFF",
};

const FONT = "Microsoft YaHei";
const FONT_EN = "Arial";
const SLIDE_H = 5.625;

// ═══════════════════════════════════════
// Helpers
// ═══════════════════════════════════════

function slideNum(s, n) {
  s.addText(String(n), { x: 9.2, y: 5.15, w: 0.6, h: 0.35, fontSize: 9, color: C.gray, fontFace: FONT_EN, align: "right" });
}

function topBar(s, color) {
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.05, fill: { color } });
}

function addTitle(s, text) {
  topBar(s, C.coral);
  s.addText(text, {
    x: 0.5, y: 0.15, w: 9.0, h: 0.55,
    fontSize: 24, bold: true, color: C.title, fontFace: FONT, margin: 0
  });
}

function body(s, text, x, y, w, h, opts) {
  return s.addText(text, Object.assign({
    x: x || 0.5, y: y || 0.85, w: w || 9.0, h: h || 4.2,
    fontSize: 16, color: C.body, fontFace: FONT, valign: "top", lineSpacing: 28, margin: 0,
  }, opts || {}));
}

function bullets(s, items, x, y, w, h, fontSize) {
  const fs = fontSize || 15;
  return s.addText(
    items.map((t, i) => ({ text: t, options: { bullet: { code: "2022" }, breakLine: i > 0, paraSpaceAfter: 6 } })),
    { x: x || 0.5, y: y || 0.85, w: w || 9.0, h: h || 4.0, fontSize: fs, color: C.body, fontFace: FONT, valign: "top", lineSpacing: 26, margin: 0 }
  );
}

function hbox(s, text, x, y, w, h, bg, tc) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, fill: { color: bg || C.offBg }, rectRadius: 0.06 });
  s.addText(text, { x: x + 0.1, y: y + 0.05, w: w - 0.2, h: h - 0.1, fontSize: 13, color: tc || C.body, fontFace: FONT, valign: "middle", margin: 0 });
}

function img(s, relPath, x, y, w, h) {
  const fp = path.resolve(__dirname, "..", relPath);
  try { s.addImage({ path: fp, x, y, w, h, sizing: { type: "contain", w, h } }); }
  catch (e) { s.addText(`[图: ${relPath}]`, { x, y, w, h, fontSize: 10, color: C.gray, fontFace: FONT_EN, align: "center", valign: "middle" }); }
}

// ═══════════════════════════════════════
// SLIDE 1 — 封面
// ═══════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.bg };
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 0.1, h: SLIDE_H, fill: { color: C.coral } });
  s.addShape(pres.shapes.RECTANGLE, { x: 0.4, y: 0.9, w: 1.0, h: 0.04, fill: { color: C.teal } });

  s.addText("BioMed-Agent", {
    x: 0.4, y: 1.1, w: 9.0, h: 0.9,
    fontSize: 46, bold: true, color: C.title, fontFace: FONT_EN, margin: 0
  });
  s.addText("面向生物医学文献驱动多组学分析的多智能体系统", {
    x: 0.4, y: 2.0, w: 9.0, h: 0.6,
    fontSize: 24, color: C.body2, fontFace: FONT, margin: 0
  });
  s.addText("Multi-Agent System for Biomedical Literature-Grounded Multi-Omics Analysis", {
    x: 0.4, y: 2.5, w: 9.0, h: 0.5,
    fontSize: 16, color: C.gray, fontFace: FONT_EN, margin: 0
  });

  s.addShape(pres.shapes.RECTANGLE, { x: 0.4, y: 4.5, w: 9.0, h: 0.015, fill: { color: C.lightGray } });
  s.addText("技术演讲 · 2026年6月 · github.com/Tubo2333/biomed-agent", {
    x: 0.4, y: 4.6, w: 9.0, h: 0.35,
    fontSize: 12, color: C.gray, fontFace: FONT, margin: 0
  });
}

// ═══════════════════════════════════════
// SLIDE 2 — 问题
// ═══════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.bg };
  addTitle(s, "生物医学研究的双重瓶颈");
  slideNum(s, 2);

  // 左列
  hbox(s, "", 0.4, 0.9, 4.3, 0.38, C.blueBg);
  s.addText("文献危机", { x: 0.6, y: 0.93, w: 3.5, h: 0.32, fontSize: 18, bold: true, color: C.blue, fontFace: FONT, margin: 0 });
  bullets(s, [
    "PubMed 年增 150 万篇论文",
    "单个研究者无法持续追踪",
    "证据分散在数千篇论文中",
    "假说常基于不完整的文献综述",
  ], 0.55, 1.45, 4.0, 2.0, 14);

  // 右列
  hbox(s, "", 5.3, 0.9, 4.3, 0.38, C.tealBg);
  s.addText("数据碎片化", { x: 5.5, y: 0.93, w: 3.5, h: 0.32, fontSize: 18, bold: true, color: C.teal, fontFace: FONT, margin: 0 });
  bullets(s, [
    "TCGA / GEO / GDSC 公开可用",
    "分析需生物信息学 + 统计 + 领域知识",
    "分析管线碎片化，不可复现",
    "无系统化方式将数据与文献证据连接",
  ], 5.45, 1.45, 4.0, 2.0, 14);

  // 底部核心差距
  hbox(s, "核心差距：尚无系统能在单一可验证管线中连接自动化文献综述与多组学分析", 0.4, 3.6, 9.2, 0.6, C.coralBg, C.coral);
}

// ═══════════════════════════════════════
// SLIDE 3 — 方案概览
// ═══════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.bg };
  addTitle(s, "BioMed-Agent：四智能体协作管线");
  slideNum(s, 3);

  img(s, "paper/figures/fig1_architecture.png", 0.3, 0.85, 9.4, 3.85);

  hbox(s, "串行设计 — 每个智能体验证上游输出后再继续（Layer 4 交叉验证），错误不向下游传播", 0.4, 4.85, 9.2, 0.5, C.tealBg, C.teal);
}

// ═══════════════════════════════════════
// SLIDE 4 — LiteratureAgent
// ═══════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.bg };
  addTitle(s, "Agent 1：LiteratureAgent / 文献探员");
  slideNum(s, 4);

  // 流程条
  const steps = [
    ["问题分解", C.blue, C.blueBg],
    ["多轮 PubMed\n检索 (≤3轮)", C.teal, C.tealBg],
    ["LLM 语义\n重排序", C.purple, C.purpleBg],
    ["证据整合\n(EvidenceLink)", C.coral, C.coralBg],
    ["假设生成\n(1-3条)", C.green, C.greenBg],
  ];
  let sx = 0.25;
  steps.forEach(([txt, c, bg]) => {
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: sx, y: 0.95, w: 1.65, h: 1.05, fill: { color: bg }, rectRadius: 0.08 });
    s.addText(txt, { x: sx + 0.05, y: 1.0, w: 1.55, h: 0.95, fontSize: 14, bold: true, color: c, fontFace: FONT, align: "center", valign: "middle", margin: 0 });
    if (sx < 7) {
      s.addText("→", { x: sx + 1.63, y: 1.05, w: 0.35, h: 0.8, fontSize: 20, color: C.gray, fontFace: FONT_EN, align: "center", valign: "middle", margin: 0 });
    }
    sx += 1.95;
  });

  // 关键机制
  bullets(s, [
    "Think→Act→Observe 循环驱动多轮检索",
    "三道闸门防无限循环：最多 3 轮 / 查询去重 / Token 预算 15,000",
    "无 embedding 模型依赖 — 直接用 LLM 逐批打分 (LLM Rerank)",
    "输出 LiteratureReview：证据链 + 1-3 条可验证假设 + 知识缺口",
  ], 0.4, 2.3, 9.2, 2.8, 15);
}

// ═══════════════════════════════════════
// SLIDE 5 — 技术深潜：结构化证据链
// ═══════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.bg };
  addTitle(s, "技术深潜：结构化证据链与五层反幻觉防线");
  slideNum(s, 5);

  // 左：数据模型
  s.addText("EvidenceLink 数据模型", { x: 0.4, y: 0.85, w: 4.5, h: 0.35, fontSize: 16, bold: true, color: C.purple, fontFace: FONT, margin: 0 });
  const fields = [
    ["claim", "原子级事实主张"],
    ["supporting_pmids", "支持该主张的真实 PMID 列表"],
    ["strength", "strong / moderate / weak / unverified"],
    ["strength_justification", "强度分类依据（强制填写）"],
    ["counter_evidence", "反面证据（如有）"],
  ];
  let fy = 1.3;
  fields.forEach(([n, d]) => {
    s.addText(n, { x: 0.5, y: fy, w: 2.3, h: 0.28, fontSize: 12, fontFace: "Consolas", color: C.body, bold: true, margin: 0 });
    s.addText(d, { x: 2.85, y: fy, w: 2.3, h: 0.28, fontSize: 12, color: C.body2, fontFace: FONT, margin: 0 });
    fy += 0.35;
  });

  // 右：4条硬检测
  s.addText("4 条硬矛盾检测 (@ __post_init__)", { x: 5.3, y: 0.85, w: 4.5, h: 0.35, fontSize: 16, bold: true, color: C.coral, fontFace: FONT, margin: 0 });
  bullets(s, [
    "① strong/moderate → 必须有 PMID",
    "② 存在 counter_evidence → 不能为 strong",
    "③ strength ≠ unverified → 必须有 justification",
    "④ 无 PMID 且无反面证据 → 强制 unverified",
  ], 5.4, 1.3, 4.3, 2.0, 13);

  // 底部：五层防线
  hbox(s, "", 0.3, 3.5, 9.4, 1.9, C.offBg);
  s.addText("五层反幻觉防线", { x: 0.5, y: 3.58, w: 9.0, h: 0.32, fontSize: 16, bold: true, color: C.title, fontFace: FONT, margin: 0 });

  const layers = [
    ["L1", "Prompt\n约束", "5条硬规则嵌入\n每个 system prompt", C.green, C.greenBg],
    ["L2", "结构\n校验", "EvidenceLink\n4条硬矛盾检测", C.purple, C.purpleBg],
    ["L3", "后验\n验证", "PMID/基因名/统计量\n程序化检查", C.blue, C.blueBg],
    ["L4", "交叉\n验证", "3节点纯规则\nAgent间互检", C.teal, C.tealBg],
    ["L5", "人工\n审阅", "strong claims 标记\n[HUMAN REVIEW]", C.coral, C.coralBg],
  ];
  layers.forEach(([lbl, title, desc, c, bg], i) => {
    const lx = 0.5 + i * 1.82;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: lx, y: 4.0, w: 1.65, h: 1.2, fill: { color: bg }, rectRadius: 0.06 });
    s.addText(lbl, { x: lx, y: 4.02, w: 0.4, h: 0.25, fontSize: 11, bold: true, color: c, fontFace: FONT_EN, align: "center", margin: 0 });
    s.addText(title, { x: lx + 0.05, y: 4.28, w: 1.55, h: 0.4, fontSize: 12, bold: true, color: C.body, fontFace: FONT, align: "center", margin: 0 });
    s.addText(desc, { x: lx + 0.05, y: 4.65, w: 1.55, h: 0.5, fontSize: 9.5, color: C.body2, fontFace: FONT, align: "center", margin: 0 });
  });
}

// ═══════════════════════════════════════
// SLIDE 6 — OrchestrationAgent
// ═══════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.bg };
  addTitle(s, "Agent 2：OrchestrationAgent / 规划师");
  slideNum(s, 6);

  bullets(s, [
    "输入：LiteratureReview（假设 + 证据链 + 知识缺口）",
    "LLM 对每个假设进行分类 → 决定 DAG 规模：",
    "    single_gene_prognostic → 小型 DAG (2-3 节点)",
    "    pathway_mechanism → 中型 DAG (4-6 节点)",
    "    multi_gene_drug → 大型 DAG (5+ 节点)",
    "每个节点强制包含 rationale 字段（解释为什么选这个方法）",
    "方法兼容矩阵后处理校验 → 不通过则重新规划（最多 2 次）",
    "输出：AnalysisPlan（有向无环图）",
  ], 0.4, 0.85, 6.2, 4.0, 16);

  // 右侧：关键区别
  hbox(s, "", 6.8, 0.85, 2.9, 3.2, C.coralBg);
  s.addText("与固定模板的\n关键区别", { x: 6.95, y: 0.95, w: 2.6, h: 0.6, fontSize: 14, bold: true, color: C.coral, fontFace: FONT, align: "center", margin: 0 });
  s.addText("不同输入\n→\n不同 DAG\n→\n不同分析", { x: 6.95, y: 1.6, w: 2.6, h: 2.0, fontSize: 14, color: C.body, fontFace: FONT, align: "center", valign: "middle", margin: 0 });

  hbox(s, "CSTB 案例：3 条假设 → 4 个分析节点（差异表达 + 免疫关联 + 生存分析 + 药物筛选）", 0.4, 4.95, 9.2, 0.5, C.blueBg, C.blue);
}

// ═══════════════════════════════════════
// SLIDE 7 — AnalysisAgent
// ═══════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.bg };
  addTitle(s, "Agent 3：AnalysisAgent / 实验师");
  slideNum(s, 7);

  // 三层数据访问
  s.addText("三层数据访问策略", { x: 0.4, y: 0.85, w: 4.5, h: 0.3, fontSize: 15, bold: true, color: C.title, fontFace: FONT, margin: 0 });
  const tiers = [
    ["L1 缓存查询", "DEG / Cox / KM", "从预计算 JSON 直接读取", C.teal, C.tealBg],
    ["L2 实时 Python", "免疫 / 药物 / 相关性", "pandas + scipy.stats 实时算", C.blue, C.blueBg],
    ["L3 F4 降级", "缓存未命中且不支持实时", "标记 degraded，诚实跳过", C.red, C.redBg],
  ];
  tiers.forEach(([t, scope, desc, c, bg], i) => {
    const ty = 1.3 + i * 1.1;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.4, y: ty, w: 4.8, h: 0.9, fill: { color: bg }, rectRadius: 0.06 });
    s.addText(t, { x: 0.55, y: ty + 0.05, w: 2.0, h: 0.3, fontSize: 13, bold: true, color: c, fontFace: FONT, margin: 0 });
    s.addText(scope, { x: 2.6, y: ty + 0.05, w: 2.4, h: 0.3, fontSize: 12, color: C.body2, fontFace: FONT, margin: 0 });
    s.addText(desc, { x: 0.55, y: ty + 0.4, w: 4.5, h: 0.4, fontSize: 12, color: C.body2, fontFace: FONT, margin: 0 });
  });

  // F1-F5
  s.addText("F1-F5 失败恢复", { x: 5.6, y: 0.85, w: 4.0, h: 0.3, fontSize: 15, bold: true, color: C.title, fontFace: FONT, margin: 0 });
  const fails = [
    ["F1 瞬时", "自动重试 3 次"],
    ["F2 参数", "换方法重试 → 升级 F4"],
    ["F3 方法", "Cox PH 违反 → 降级 KM"],
    ["F4 数据", "标记 degraded，继续"],
    ["F5 未知", "记录日志，继续"],
  ];
  let ffy = 1.25;
  fails.forEach(([t, a]) => {
    s.addText(t, { x: 5.7, y: ffy, w: 1.2, h: 0.28, fontSize: 12, bold: true, color: C.coral, fontFace: "Consolas", margin: 0 });
    s.addText(a, { x: 7.0, y: ffy, w: 2.6, h: 0.28, fontSize: 13, color: C.body, fontFace: FONT, margin: 0 });
    ffy += 0.42;
  });

  hbox(s, "每个节点记录 why（工具选择）/ what（实际操作）/ result_interpretation（LLM 解释）", 0.4, 4.95, 9.2, 0.5, C.tealBg, C.teal);
}

// ═══════════════════════════════════════
// SLIDE 8 — ReportAgent + L4
// ═══════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.bg };
  addTitle(s, "Agent 4：ReportAgent / 主编 + Layer 4 交叉验证");
  slideNum(s, 8);

  // L4 三节点
  const vnodes = [
    ["A2 → A1", "证据链一致性\n假设-证据对应\n置信度合理性\nBLOCKER: 链条为空", C.purple, C.purpleBg],
    ["A3 → A2", "数据源存在性\n基因名有效性\n方法合理性(矩阵)\nBLOCKER: 全部缺失", C.blue, C.blueBg],
    ["A4 → A3", "统计量合理性\n跨节点矛盾检测\n效应量阈值检查\nBLOCKER: 全部失败", C.coral, C.coralBg],
  ];
  vnodes.forEach(([t, d, c, bg], i) => {
    const vx = 0.4 + i * 3.15;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: vx, y: 0.9, w: 2.95, h: 1.95, fill: { color: bg }, rectRadius: 0.06 });
    s.addText(t, { x: vx + 0.08, y: 0.95, w: 2.8, h: 0.32, fontSize: 14, bold: true, color: c, fontFace: FONT_EN, align: "center", margin: 0 });
    s.addText(d, { x: vx + 0.1, y: 1.35, w: 2.75, h: 1.4, fontSize: 12, color: C.body2, fontFace: FONT, margin: 0 });
  });

  // 纯规则标注
  hbox(s, "纯规则驱动，无 LLM 调用 — 关键词匹配 + 路径检查 + 统计量范围 + 效应量阈值", 0.4, 3.05, 9.2, 0.4, C.purpleBg, C.purple);

  // ReportAgent
  s.addText("ReportAgent / 主编 — 强制 6 节结构", { x: 0.4, y: 3.65, w: 9.0, h: 0.3, fontSize: 15, bold: true, color: C.title, fontFace: FONT, margin: 0 });
  s.addText("Introduction  →  Methods  →  Results  →  Negative & Null Findings  →  Discussion  →  Conclusion", {
    x: 0.4, y: 4.0, w: 9.2, h: 0.4, fontSize: 14, color: C.teal, fontFace: FONT_EN, align: "center", margin: 0
  });
  hbox(s, "强制 \"Negative and Null Findings\" 节 — 未发现的内容与发现同等重要", 0.4, 4.55, 9.2, 0.5, C.coralBg, C.coral);
}

// ═══════════════════════════════════════
// SLIDE 9 — Benchmark
// ═══════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.bg };
  addTitle(s, "Benchmark：5 任务 × 4 维度 × 4 基线");
  slideNum(s, 9);

  // 左列 — 框架
  bullets(s, [
    "5 个任务：T1 文献检索 / T2 基因-疾病关联 / T3 差异表达 / T4 生存分析 / T5 药物筛选",
    "4 维指标：Completion (0.15) / Tool Selection (0.25) / Correctness (0.35) / Safety (0.25)",
    "4 个基线：B1 Naive LLM / B2 ReAct / B3 Simple RAG / B4 Domain ReAct",
    "Safety 连续惩罚函数（无硬门槛 cliff effect）",
  ], 0.4, 0.9, 6.0, 2.0, 15);

  // 右列 — T3-DEG 数据
  hbox(s, "", 6.7, 0.9, 3.0, 2.3, C.offBg);
  s.addText("T3-DEG 初步结果", { x: 6.85, y: 0.95, w: 2.7, h: 0.3, fontSize: 13, bold: true, color: C.coral, fontFace: FONT, margin: 0 });
  const rows = [
    ["B1 Naive LLM", "0.637", "完成"],
    ["B2 ReAct", "—", "API 崩溃"],
    ["B3 Simple RAG", "0.575", "8 标记"],
    ["B4 Domain ReAct", "—", "API 崩溃"],
    ["S3 Pipeline", "—", "降级*"],
  ];
  let ry = 1.35;
  rows.forEach(([agent, score, status]) => {
    s.addText(agent, { x: 6.85, y: ry, w: 1.5, h: 0.25, fontSize: 10, bold: true, color: C.body, fontFace: FONT_EN, margin: 0 });
    s.addText(score, { x: 8.35, y: ry, w: 0.5, h: 0.25, fontSize: 10, fontFace: "Consolas", color: C.body, align: "center", margin: 0 });
    s.addText(status, { x: 8.85, y: ry, w: 0.7, h: 0.25, fontSize: 10, color: C.gray, fontFace: FONT, margin: 0 });
    ry += 0.32;
  });

  // GT 说明
  s.addText("GT 构建：T1 PubMed 高引+时间分层 | T2 DisGeNET+OpenTargets 双源 | T3-T5 ITIP/CSTB（标注 exploratory）", {
    x: 0.4, y: 3.15, w: 9.2, h: 0.5, fontSize: 13, color: C.gray, fontFace: FONT, margin: 0
  });

  hbox(s, "单任务、单数据集 (TCGA-COAD)、单次运行。不可泛化。全量矩阵 (~150K tokens) 待运行。", 0.4, 3.7, 9.2, 0.45, C.coralBg, C.coral);

  // 底部标注
  bullets(s, [
    "* S3 Pipeline 在 benchmark 模式下降级是预期行为 — Task Router 按 task_id 分派，T3-DEG 跳过 LiteratureAgent（文献探员）直接进入分析阶段。Pipeline 为端到端研究问题设计，非单任务 benchmark。",
  ], 0.4, 4.35, 9.2, 1.0, 12);
}

// ═══════════════════════════════════════
// SLIDE 10 — CSTB 案例
// ═══════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.bg };
  addTitle(s, "案例研究：CSTB 在结直肠癌中的完整闭环");
  slideNum(s, 10);

  // 四阶段时间线
  const phases = [
    ["Phase 1", "文献探员\nLiteratureAgent", "162.5s", "2 篇论文\n3 条假设", C.blue],
    ["Phase 2", "规划师\nOrchestrationAgent", "52.6s", "4 个分析节点\n(DAG)", C.teal],
    ["Phase 3", "实验师\nAnalysisAgent", "76.7s", "3 完成\n1 降级 (免疫)", C.purple],
    ["Phase 4", "主编\nReportAgent", "42.3s", "9,447 字符\n结构化报告", C.coral],
  ];
  let px = 0.25;
  phases.forEach(([phase, agent, dur, result, c]) => {
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: px, y: 0.85, w: 2.2, h: 1.65, fill: { color: C.offBg }, rectRadius: 0.06, line: { color: c, width: 1.5 } });
    s.addText(phase, { x: px + 0.08, y: 0.9, w: 2.04, h: 0.25, fontSize: 11, bold: true, color: c, fontFace: FONT_EN, margin: 0 });
    s.addText(agent, { x: px + 0.08, y: 1.15, w: 2.04, h: 0.3, fontSize: 13, bold: true, color: C.body, fontFace: FONT_EN, margin: 0 });
    s.addText(dur, { x: px + 0.08, y: 1.5, w: 2.04, h: 0.25, fontSize: 12, color: C.gray, fontFace: "Consolas", margin: 0 });
    s.addText(result, { x: px + 0.08, y: 1.8, w: 2.04, h: 0.55, fontSize: 11, color: C.body2, fontFace: FONT, margin: 0 });
    px += 2.4;
  });

  // 总耗时
  s.addText("总耗时：334 秒  ·  Token：5,153  ·  Layer 4 WARNING：2 条（均正确捕获数据问题）", {
    x: 0.4, y: 2.75, w: 9.2, h: 0.4, fontSize: 15, bold: true, color: C.title, fontFace: FONT, align: "center", margin: 0
  });

  // 关键发现
  s.addText("关键发现与问题", { x: 0.4, y: 3.25, w: 4.5, h: 0.3, fontSize: 15, bold: true, color: C.title, fontFace: FONT, margin: 0 });
  const findings = [
    ["DEG 缓存错误", "logFC=0.073 vs GT≈2.3", "数据管线 bug（非缓存架构问题）"],
    ["免疫相关性", "degraded (F4)", "无缓存 — 诚实降级而非编造"],
    ["Cox 生存分析", "HR=1.46, p=0.053", "边缘不显著，预后更差趋势"],
    ["L4 交叉验证", "2 条 WARNING", "正确捕获效应量问题 + 免疫数据缺失"],
  ];
  let fy = 3.6;
  findings.forEach(([l, v, n]) => {
    s.addText(l, { x: 0.5, y: fy, w: 1.8, h: 0.28, fontSize: 12, bold: true, color: C.coral, fontFace: FONT, margin: 0 });
    s.addText(v, { x: 2.4, y: fy, w: 2.8, h: 0.28, fontSize: 12, fontFace: "Consolas", color: C.body, margin: 0 });
    s.addText(n, { x: 5.3, y: fy, w: 4.4, h: 0.28, fontSize: 12, color: C.body2, fontFace: FONT, margin: 0 });
    fy += 0.37;
  });
}

// ═══════════════════════════════════════
// SLIDE 11 — 已知局限
// ═══════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.bg };
  addTitle(s, "已知局限");
  slideNum(s, 11);

  const lims = [
    [C.red, "单队列 (TCGA-COAD, n≈300)、单案例 (CSTB)。不可泛化。"],
    [C.coral, "Benchmark 框架完整实现（102 测试），但全量 agent×task 矩阵未运行 (~150K tokens)。"],
    [C.blue, "预计算缓存限制分析灵活性。非标准分析降级为 F4。"],
    [C.red, "CSTB 缓存数据有误 (logFC=0.073 vs GT≈2.3) — 数据管线 bug，根因未定位。"],
    [C.gray, "DeepSeek thinking mode token 压力 — 长响应可能截断 JSON。"],
    [C.gray, "无并发 — 4 Agent 串行。挂钟时间随 LLM API 延迟线性增长。"],
  ];
  lims.forEach(([c, t], i) => {
    s.addShape(pres.shapes.RECTANGLE, { x: 0.4, y: 0.95 + i * 0.62, w: 0.06, h: 0.06, fill: { color: c } });
    s.addText(t, { x: 0.6, y: 0.9 + i * 0.62, w: 9.0, h: 0.5, fontSize: 15, color: C.body, fontFace: FONT, valign: "top", margin: 0 });
  });

  hbox(s, "这些局限在 README、技术报告和所有文档中前置展示，不藏在讨论章节里。", 0.4, 4.8, 9.2, 0.55, C.tealBg, C.teal);
}

// ═══════════════════════════════════════
// SLIDE 12 — 总结
// ═══════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: C.bg };
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 0.1, h: SLIDE_H, fill: { color: C.teal } });
  s.addShape(pres.shapes.RECTANGLE, { x: 0.4, y: 0.8, w: 1.0, h: 0.04, fill: { color: C.coral } });

  s.addText("BioMed-Agent", { x: 0.4, y: 1.0, w: 9.0, h: 0.7, fontSize: 38, bold: true, color: C.title, fontFace: FONT_EN, margin: 0 });
  s.addText("核心贡献", { x: 0.4, y: 1.65, w: 9.0, h: 0.4, fontSize: 20, bold: true, color: C.title, fontFace: FONT, margin: 0 });

  bullets(s, [
    "四智能体协作架构 — 连接文献综述与多组学分析的完整管线",
    "结构化证据链 (EvidenceLink) — 5 层反幻觉防线，数据模型级约束",
    "标准化评测框架 — 5 任务 × 4 维度 × 4 基线（已实现，已测试）",
    "CSTB-CRC 端到端案例 — 334 秒完整闭环，诚实报告失败",
  ], 0.4, 2.2, 9.2, 2.2, 16);

  s.addShape(pres.shapes.RECTANGLE, { x: 0.4, y: 4.2, w: 9.2, h: 0.015, fill: { color: C.lightGray } });
  s.addText("github.com/Tubo2333/biomed-agent    ·    技术报告：paper/report.md    ·    文档：README / ARCHITECTURE / CASE_STUDY / FAQ", {
    x: 0.4, y: 4.35, w: 9.2, h: 0.35, fontSize: 12, color: C.gray, fontFace: FONT, margin: 0
  });
  s.addText("谢谢", { x: 0.4, y: 4.8, w: 9.2, h: 0.5, fontSize: 26, color: C.coral, fontFace: FONT, margin: 0 });
}

// ═══════════════════════════════════════
// Export
// ═══════════════════════════════════════
const outPath = path.resolve(__dirname, "biomed-agent-overview.pptx");
pres.writeFile({ fileName: outPath }).then(() => {
  console.log(`PPTX written: ${outPath}`);
  console.log(`Slides: ${pres.slides.length}`);
}).catch(err => {
  console.error("Error:", err.message);
  process.exit(1);
});
