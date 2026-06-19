// Convert all .md files in design/ to .docx (Chinese-safe)
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  HeadingLevel, AlignmentType, BorderStyle, WidthType,
} = require("docx");

const DESIGN_DIR = __dirname;

// ── Simple markdown parser ──
function parseMd(text) {
  const lines = text.split("\n");
  const blocks = [];
  let i = 0;
  let inCodeBlock = false;
  let codeLines = [];
  let codeLang = "";
  let inTable = false;
  let tableRows = [];
  let listItems = [];

  function flushList() {
    if (listItems.length > 0) {
      blocks.push({ type: "bullet_list", items: listItems });
      listItems = [];
    }
  }

  function flushTable() {
    if (tableRows.length > 1) {
      blocks.push({ type: "table", rows: tableRows });
    }
    tableRows = [];
    inTable = false;
  }

  while (i < lines.length) {
    const raw = lines[i];
    const line = raw.trim();

    // Code block toggle
    if (line.startsWith("```")) {
      flushList();
      if (!inCodeBlock) {
        inCodeBlock = true;
        codeLang = line.slice(3).trim();
        codeLines = [];
      } else {
        blocks.push({ type: "code", lang: codeLang, lines: codeLines });
        inCodeBlock = false;
        codeLines = [];
      }
      i++;
      continue;
    }

    if (inCodeBlock) {
      codeLines.push(raw);
      i++;
      continue;
    }

    // Empty line
    if (line === "") {
      flushList();
      i++;
      continue;
    }

    // Horizontal rule
    if (line === "---" || line === "***" || line === "___") {
      flushList();
      flushTable();
      blocks.push({ type: "hr" });
      i++;
      continue;
    }

    // Heading
    const hMatch = line.match(/^(#{1,6})\s+(.+)/);
    if (hMatch) {
      flushList();
      flushTable();
      blocks.push({ type: "heading", level: hMatch[1].length, text: hMatch[2] });
      i++;
      continue;
    }

    // Table (detect | ... | ... |)
    if (line.startsWith("|") && line.endsWith("|")) {
      flushList();
      const cells = line.split("|").slice(1, -1).map(c => c.trim());
      // Skip separator row
      if (cells.every(c => /^[-:]+$/.test(c))) { i++; continue; }
      if (!inTable) { inTable = true; tableRows = []; }
      tableRows.push({ type: "row", cells });
      i++;
      continue;
    } else if (inTable) {
      flushTable();
      continue; // re-evaluate this line
    }

    // Blockquote
    if (line.startsWith("> ")) {
      flushList();
      const qtLines = [];
      while (i < lines.length && lines[i].trim().startsWith("> ")) {
        qtLines.push(lines[i].trim().slice(2));
        i++;
      }
      blocks.push({ type: "blockquote", lines: qtLines });
      continue;
    }

    // Bullet list
    const ulMatch = line.match(/^[\-\*]\s+(.+)/);
    if (ulMatch) {
      flushTable();
      listItems.push({ text: ulMatch[1], depth: (raw.match(/^(\s*)/)[0].length / 2) | 0 });
      i++;
      continue;
    }

    // Numbered list
    const olMatch = line.match(/^\d+[\.\)]\s+(.+)/);
    if (olMatch) {
      flushTable();
      flushList();
      blocks.push({ type: "ordered_item", text: olMatch[1] });
      i++;
      continue;
    }

    // Regular paragraph
    flushTable();
    flushList();
    blocks.push({ type: "paragraph", text: line });
    i++;
  }

  flushList();
  flushTable();
  return blocks;
}

// ── Inline parser: bold **, italic *, code `, link []() ──
function parseInline(text) {
  const runs = [];
  let i = 0;
  while (i < text.length) {
    // Bold **...**
    if (text[i] === "*" && text[i + 1] === "*") {
      const end = text.indexOf("**", i + 2);
      if (end > i) {
        runs.push(...parseInline(text.slice(i + 2, end)).map(r => ({ ...r, bold: true })));
        i = end + 2;
        continue;
      }
    }
    // Inline code `...`
    if (text[i] === "`") {
      const end = text.indexOf("`", i + 1);
      if (end > i) {
        runs.push({ text: text.slice(i + 1, end), font: "Consolas", size: 18 });
        i = end + 1;
        continue;
      }
    }
    // Link [text](url)
    if (text[i] === "[") {
      const closeB = text.indexOf("]", i);
      const openP = text.indexOf("(", closeB);
      const closeP = text.indexOf(")", openP);
      if (closeB > i && openP === closeB + 1 && closeP > openP) {
        const linkText = text.slice(i + 1, closeB);
        const linkUrl = text.slice(openP + 1, closeP);
        runs.push({ text: linkText, color: "0563C1", underline: true });
        i = closeP + 1;
        continue;
      }
    }
    // Plain text chunk
    let j = i;
    while (j < text.length && text[j] !== "*" && text[j] !== "`" && text[j] !== "[") j++;
    if (j > i) {
      runs.push({ text: text.slice(i, j) });
      i = j;
      continue;
    }
    runs.push({ text: text[i] });
    i++;
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

// ── Block to Paragraph/Table ──
function blockToDocx(block) {
  switch (block.type) {
    case "heading": {
      const level = Math.min(block.level, 4);
      const headingLevels = [
        HeadingLevel.HEADING_1, HeadingLevel.HEADING_2,
        HeadingLevel.HEADING_3, HeadingLevel.HEADING_4,
      ];
      return new Paragraph({
        heading: headingLevels[level - 1],
        children: [new TextRun({ text: block.text, bold: true, font: { name: "Microsoft YaHei" } })],
        spacing: { before: 300, after: 150 },
      });
    }

    case "paragraph": {
      const runs = parseInline(block.text);
      return new Paragraph({
        children: runsToTextRuns(runs),
        spacing: { after: 80 },
      });
    }

    case "bullet_list": {
      return block.items.map((item, idx) =>
        new Paragraph({
          children: [
            new TextRun({ text: "• ", bold: true }),
            ...runsToTextRuns(parseInline(item.text)),
          ],
          indent: { left: item.depth * 360 + 360 },
          spacing: { after: 40 },
        })
      );
    }

    case "ordered_item": {
      return new Paragraph({
        children: runsToTextRuns(parseInline(block.text)),
        indent: { left: 360 },
        spacing: { after: 40 },
      });
    }

    case "code": {
      const codeText = block.lines.join("\n");
      return new Paragraph({
        children: [new TextRun({ text: codeText, font: { name: "Consolas" }, size: 18 })],
        shading: { fill: "F2F2F2" },
        spacing: { after: 80 },
        indent: { left: 180 },
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
          const cellText = row.cells[c] || "";
          cells.push(new TableCell({
            children: [new Paragraph({
              children: runsToTextRuns(parseInline(cellText)),
              spacing: { after: 0 },
            })],
            shading: ri === 0 ? { fill: "E8E8E8" } : undefined,
            width: { size: 100 / colCount, type: WidthType.PERCENTAGE },
          }));
        }
        return new TableRow({ children: cells });
      });
      return new Table({
        rows,
        width: { size: 100, type: WidthType.PERCENTAGE },
      });
    }

    case "hr": {
      return new Paragraph({
        children: [new TextRun({ text: "─".repeat(60), color: "CCCCCC", size: 16 })],
        spacing: { before: 200, after: 200 },
        alignment: AlignmentType.CENTER,
      });
    }

    default:
      return [];
  }
}

// ── Main: convert all .md files ──
async function convertAll() {
  const files = fs.readdirSync(DESIGN_DIR).filter(f => f.endsWith(".md"));
  console.log(`Found ${files.length} .md files to convert\n`);

  for (const filename of files) {
    const mdPath = path.join(DESIGN_DIR, filename);
    const docxPath = path.join(DESIGN_DIR, filename.replace(".md", ".docx"));
    const text = fs.readFileSync(mdPath, "utf-8");

    console.log(`  Converting: ${filename}`);
    const blocks = parseMd(text);

    const docxChildren = [];
    for (const block of blocks) {
      const result = blockToDocx(block);
      if (Array.isArray(result)) {
        docxChildren.push(...result.flat());
      } else {
        docxChildren.push(result);
      }
    }

    const doc = new Document({
      styles: {
        default: {
          document: {
            run: { font: { name: "Microsoft YaHei" }, size: 22 },
          },
        },
      },
      sections: [{ children: docxChildren }],
    });

    const buffer = await Packer.toBuffer(doc);
    fs.writeFileSync(docxPath, buffer);
    console.log(`    → ${filename.replace(".md", ".docx")} (${(buffer.length / 1024).toFixed(1)} KB)`);
  }

  console.log(`\nDone. ${files.length} files converted.`);
}

convertAll().catch(err => { console.error(err); process.exit(1); });
