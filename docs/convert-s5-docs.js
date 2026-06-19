// Convert S5 documentation .md files to .docx (Chinese-safe, GOV-005 compliant)
// Usage: node docs/convert-s5-docs.js
// Output: docs/*.docx (NOT uploaded to git — see .gitignore)

const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  HeadingLevel, AlignmentType, BorderStyle, WidthType,
} = require("docx");

const ROOT = path.resolve(__dirname, "..");
const OUT_DIR = __dirname;

const FILES = [
  "README.md",
  "README_CN.md",
  "ARCHITECTURE.md",
  "CASE_STUDY.md",
  "FAQ.md",
  "BENCHMARK.md",
];

// ═══════════════════════════════════════
// Markdown parser (same as design/convert-to-docx.js)
// ═══════════════════════════════════════

function parseMd(text) {
  const lines = text.split("\n");
  const blocks = [];
  let i = 0;
  let inCodeBlock = false, codeLines = [], codeLang = "";
  let inTable = false, tableRows = [];
  let listItems = [];

  function flushList() {
    if (listItems.length > 0) { blocks.push({ type: "bullet_list", items: [...listItems] }); listItems = []; }
  }
  function flushTable() {
    if (tableRows.length > 1) { blocks.push({ type: "table", rows: [...tableRows] }); }
    tableRows = []; inTable = false;
  }

  while (i < lines.length) {
    const raw = lines[i];
    const line = raw.trim();

    if (line.startsWith("```")) {
      flushList();
      if (!inCodeBlock) { inCodeBlock = true; codeLang = line.slice(3).trim(); codeLines = []; }
      else { blocks.push({ type: "code", lang: codeLang, lines: [...codeLines] }); inCodeBlock = false; codeLines = []; }
      i++; continue;
    }
    if (inCodeBlock) { codeLines.push(raw); i++; continue; }
    if (line === "") { flushList(); i++; continue; }
    if (line === "---" || line === "***" || line === "___") { flushList(); flushTable(); blocks.push({ type: "hr" }); i++; continue; }

    const hMatch = line.match(/^(#{1,6})\s+(.+)/);
    if (hMatch) { flushList(); flushTable(); blocks.push({ type: "heading", level: hMatch[1].length, text: hMatch[2] }); i++; continue; }

    if (line.startsWith("|") && line.endsWith("|")) {
      flushList();
      const cells = line.split("|").slice(1, -1).map(c => c.trim());
      if (cells.every(c => /^[-:]+$/.test(c))) { i++; continue; }
      if (!inTable) { inTable = true; tableRows = []; }
      tableRows.push({ cells });
      i++; continue;
    } else if (inTable) { flushTable(); continue; }

    if (line.startsWith("> ")) {
      flushList();
      const qtLines = [];
      while (i < lines.length && lines[i].trim().startsWith("> ")) { qtLines.push(lines[i].trim().slice(2)); i++; }
      blocks.push({ type: "blockquote", lines: qtLines }); continue;
    }

    const ulMatch = line.match(/^[\-\*]\s+(.+)/);
    if (ulMatch) { flushTable(); const depth = (raw.match(/^(\s*)/)[0].length / 2) | 0; listItems.push({ text: ulMatch[1], depth }); i++; continue; }

    const olMatch = line.match(/^\d+[\.\)]\s+(.+)/);
    if (olMatch) { flushTable(); flushList(); blocks.push({ type: "ordered_item", text: olMatch[1] }); i++; continue; }

    flushTable(); flushList();
    blocks.push({ type: "paragraph", text: line });
    i++;
  }
  flushList(); flushTable();
  return blocks;
}

function parseInline(text) {
  const runs = [];
  let i = 0;
  while (i < text.length) {
    if (text[i] === "*" && text[i + 1] === "*") {
      const end = text.indexOf("**", i + 2);
      if (end > i) { runs.push(...parseInline(text.slice(i + 2, end)).map(r => ({ ...r, bold: true }))); i = end + 2; continue; }
    }
    if (text[i] === "`") {
      const end = text.indexOf("`", i + 1);
      if (end > i) { runs.push({ text: text.slice(i + 1, end), font: "Consolas", size: 18 }); i = end + 1; continue; }
    }
    if (text[i] === "[") {
      const closeB = text.indexOf("]", i), openP = text.indexOf("(", closeB), closeP = text.indexOf(")", openP);
      if (closeB > i && openP === closeB + 1 && closeP > openP) {
        runs.push({ text: text.slice(i + 1, closeB), color: "0563C1", underline: true }); i = closeP + 1; continue;
      }
    }
    let j = i;
    while (j < text.length && text[j] !== "*" && text[j] !== "`" && text[j] !== "[") j++;
    if (j > i) { runs.push({ text: text.slice(i, j) }); i = j; continue; }
    runs.push({ text: text[i] }); i++;
  }
  return runs;
}

function runsToTextRuns(runs) {
  return runs.map(r => {
    const opts = { text: r.text };
    if (r.bold) opts.bold = true;
    if (r.font) opts.font = { name: r.font };
    if (r.size) opts.size = r.size;
    if (r.color) opts.color = r.color;
    if (r.underline) opts.underline = {};
    return new TextRun(opts);
  });
}

function blockToDocx(block) {
  switch (block.type) {
    case "heading": {
      const lvl = Math.min(block.level, 4);
      const levels = [HeadingLevel.HEADING_1, HeadingLevel.HEADING_2, HeadingLevel.HEADING_3, HeadingLevel.HEADING_4];
      return new Paragraph({
        heading: levels[lvl - 1],
        children: [new TextRun({ text: block.text, bold: true, font: { name: "Microsoft YaHei" } })],
        spacing: { before: 300, after: 150 },
      });
    }
    case "paragraph": {
      const runs = parseInline(block.text);
      return new Paragraph({ children: runsToTextRuns(runs), spacing: { after: 80 } });
    }
    case "bullet_list": {
      return block.items.map(item =>
        new Paragraph({
          children: [new TextRun({ text: "• ", bold: true }), ...runsToTextRuns(parseInline(item.text))],
          indent: { left: item.depth * 360 + 360 }, spacing: { after: 40 },
        })
      );
    }
    case "ordered_item": {
      return new Paragraph({ children: runsToTextRuns(parseInline(block.text)), indent: { left: 360 }, spacing: { after: 40 } });
    }
    case "code": {
      return new Paragraph({
        children: [new TextRun({ text: block.lines.join("\n"), font: { name: "Consolas" }, size: 18 })],
        shading: { fill: "F2F2F2" }, spacing: { after: 80 }, indent: { left: 180 },
      });
    }
    case "blockquote": {
      return block.lines.map(line =>
        new Paragraph({
          children: [new TextRun({ text: line, italics: true, color: "666666" })],
          indent: { left: 540 },
          border: { left: { style: BorderStyle.SINGLE, color: "CCCCCC", size: 6 } },
          spacing: { after: 40 },
        })
      );
    }
    case "table": {
      if (block.rows.length === 0) return [];
      const colCount = Math.max(...block.rows.map(r => r.cells.length));
      const rows = block.rows.map((row, ri) => {
        const cells = [];
        for (let c = 0; c < colCount; c++) {
          cells.push(new TableCell({
            children: [new Paragraph({ children: runsToTextRuns(parseInline(row.cells[c] || "")), spacing: { after: 0 } })],
            shading: ri === 0 ? { fill: "E8E8E8" } : undefined,
            width: { size: 100 / colCount, type: WidthType.PERCENTAGE },
          }));
        }
        return new TableRow({ children: cells });
      });
      return new Table({ rows, width: { size: 100, type: WidthType.PERCENTAGE } });
    }
    case "hr": {
      return new Paragraph({
        children: [new TextRun({ text: "─".repeat(60), color: "CCCCCC", size: 16 })],
        spacing: { before: 200, after: 200 }, alignment: AlignmentType.CENTER,
      });
    }
    default: return [];
  }
}

// ═══════════════════════════════════════
// Main
// ═══════════════════════════════════════

async function convertAll() {
  console.log("BioMed-Agent S5 Docs → DOCX\n");

  for (const filename of FILES) {
    const mdPath = path.join(ROOT, filename);
    if (!fs.existsSync(mdPath)) { console.log(`  SKIP (not found): ${filename}`); continue; }

    const docxPath = path.join(OUT_DIR, filename.replace(".md", ".docx"));
    const text = fs.readFileSync(mdPath, "utf-8");
    console.log(`  Converting: ${filename} (${text.length} chars)`);

    const blocks = parseMd(text);
    const docxChildren = [];
    for (const block of blocks) {
      const result = blockToDocx(block);
      if (Array.isArray(result)) docxChildren.push(...result.flat());
      else docxChildren.push(result);
    }

    const doc = new Document({
      styles: {
        default: {
          document: { run: { font: { name: "Microsoft YaHei" }, size: 22 } },
        },
      },
      sections: [{ children: docxChildren }],
    });

    const buffer = await Packer.toBuffer(doc);
    fs.writeFileSync(docxPath, buffer);
    console.log(`    → ${filename.replace(".md", ".docx")} (${(buffer.length / 1024).toFixed(1)} KB)`);
  }
  console.log(`\nDone. ${FILES.length} files → ${OUT_DIR}/`);
}

convertAll().catch(err => { console.error(err); process.exit(1); });
