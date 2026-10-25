const fs = require("fs");
const d = require("docx");
const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle,
        HeadingLevel, AlignmentType, Footer, PageNumber, LevelFormat, PageBreak } = d;
// 사용: node scripts/export_summary_docx.js YYYY-MM-DD  → reports/{date}_매크로16개항목_요약.docx (docx npm 패키지 필요)
const path = require("path");
const DATE = process.argv[2];
const ROOT = path.resolve(__dirname, "..");
const data = JSON.parse(fs.readFileSync(path.join(ROOT, "reports/tmp", DATE + "_summary_prep.json"), "utf8"));
const OUT = process.argv[3] || path.join(ROOT, "reports", DATE + "_매크로16개항목_요약.docx");
const FONT = "맑은 고딕";
const W = 9638; // A4 본문폭(좌우 여백 1134)
const C = { ink: "1F2937", sub: "6B7280", line: "D1D5DB", head: "E8EEF6", accent: "1E3A5F", warn: "B45309" };

const run = (text, o = {}) => new TextRun({ text, font: FONT, size: o.size || 19, bold: o.bold, color: o.color || C.ink, italics: o.italics });
const para = (children, o = {}) => new Paragraph({ children: Array.isArray(children) ? children : [run(children, o)],
  spacing: { before: o.before ?? 40, after: o.after ?? 40, line: 276 }, alignment: o.align, numbering: o.bullet ? { reference: "b", level: 0 } : undefined,
  keepNext: o.keepNext });
const label = (tag, text) => para([run(tag + " ", { bold: true, color: C.accent }), run(text)], { bullet: true });
const border = { style: BorderStyle.SINGLE, size: 4, color: C.line };
const borders = { top: border, bottom: border, left: border, right: border };
function cell(text, w, o = {}) {
  const lines = Array.isArray(text) ? text : [text];
  return new TableCell({ width: { size: w, type: WidthType.DXA }, borders,
    shading: o.head ? { fill: C.head, type: ShadingType.CLEAR, color: "auto" } : undefined,
    margins: { top: 50, bottom: 50, left: 90, right: 90 },
    children: lines.map(l => new Paragraph({ spacing: { before: 0, after: 0, line: 252 }, alignment: o.align,
      children: [run(l, { size: o.size || 17, bold: o.head || o.bold, color: o.color })] })) });
}
function table(widths, header, rows) {
  return new Table({ width: { size: widths.reduce((a, b) => a + b, 0), type: WidthType.DXA }, columnWidths: widths,
    rows: [new TableRow({ tableHeader: true, children: header.map((h, i) => cell(h, widths[i], { head: true })) }),
           ...rows.map(r => new TableRow({ cantSplit: true, children: r.map((c, i) => cell(c, widths[i])) }))] });
}
const H1 = t => new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { before: 240, after: 120 }, children: [run(t, { size: 28, bold: true, color: C.accent })] });
const H2 = t => new Paragraph({ heading: HeadingLevel.HEADING_2, spacing: { before: 260, after: 80 }, keepNext: true,
  border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: C.accent, space: 2 } }, children: [run(t, { size: 23, bold: true, color: C.accent })] });

const body = [];
body.push(new Paragraph({ spacing: { after: 60 }, children: [run("16개 매크로 항목 요약", { size: 36, bold: true, color: C.accent })] }));
body.push(para([run(`기준일 ${data.date}  ·  자료: ECOS 수기 입력(100대 통계지표·일일지표), 신한투자증권 리포트 5건, 웹 검색`, { size: 18, color: C.sub })], { after: 60 }));
body.push(para([run("표기 ", { size: 17, color: C.sub, bold: true }),
  run("[사실] 데이터·공식 발표  [하우스] 증권사 리포트  [판단] 에이전트 판단  ·  값 플래그: 수기 = ECOS 홈페이지 값, 웹확인 = 웹 검색 값(공식 원문 대조 전), ⚠ = 기준일이 오래된 데이터", { size: 17, color: C.sub })], { after: 160 }));

body.push(H1("한 장 요약"));
const sw = [1850, 2350, 2050, 2628, 760];
body.push(table(sw, ["항목", "현황 핵심 수치 (기준일)", "단기 방향 (3-6M)", "장기 Base (1-3Y)", "확신도"],
  data.topics.map(t => t.missing ? [`${t.no}. ${t.name}`, "미확인", "미확인", "미확인", "—"] : [
    `${t.no}. ${t.name}`,
    t.indicators.slice(0, 1).map(x => `${x.short} ${x.value} (${x.as_of}) [${x.flag}]`).concat(t.indicators.length ? [] : ["미확인"]),
    t.st_dir,
    t.scen[0] ? `${t.scen[0].short} (p=${t.scen[0].prob})` : "—",
    t.st_conf])));
body.push(para([run("하우스 뷰는 신한투자증권 1곳뿐이라 하우스 간 컨센서스·이견은 비교할 수 없음. 미국 지표와 국고 10·30년물은 API 미수집으로 웹확인 값.", { size: 16, color: C.warn })], { before: 80 }));

body.push(new Paragraph({ children: [new PageBreak()] }));
body.push(H1("항목별 정리"));
for (const t of data.topics) {
  body.push(H2(`${t.no}. ${t.name}`));
  if (t.missing) { body.push(para("미확인 — 분석 결과 없음")); continue; }
  if (t.indicators.length) {
    body.push(table([3600, 2200, 1700, 2138], ["지표", "값", "기준일", "출처 플래그"],
      t.indicators.map(x => [x.name, x.value, x.as_of, x.flag])));
  } else {
    body.push(para([run("현황 수치 미확인", { color: C.warn })]));
  }
  body.push(label("현황", t.summary));
  body.push(label("단기", `${t.st_view} (확신도 ${t.st_conf})`));
  body.push(label("장기", t.scen.map(s => `${s.name} ${s.prob}: ${s.text}`).join("  /  ")));
  body.push(label("하우스", t.house + (t.cards.length ? ` (${t.cards.length}건)` : "")));
  if (t.gaps.length) body.push(label("공백", t.gaps.join("; ")));
}

body.push(H1("사용한 증권사 리포트"));
body.push(table([4200, 5438], ["card_id", "비고"], data.cards.map(c => [c, "신한투자증권 (사용자 제공 PDF, 개인 분석용 요약)"])));
body.push(para([run("면책: ", { bold: true, size: 16 }), run("본 자료는 개인 의사결정 보조용 분석 자료이며 투자 권유가 아닙니다. 현황 수치는 기준일 시점의 ECOS 수기 입력값 또는 [웹확인] 표시된 웹 검색 값(공식 원문 대조 전)이고, 전망·시나리오·확률은 하우스 뷰와 에이전트 판단에 기반한 추정입니다. 증권사 리포트의 저작권은 각 발행사에 있습니다.", { size: 16, color: C.sub })], { before: 200 }));

const doc = new Document({
  styles: { default: { document: { run: { font: FONT, size: 19 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true, run: { font: FONT, size: 28, bold: true }, paragraph: { outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true, run: { font: FONT, size: 23, bold: true }, paragraph: { outlineLevel: 1 } }] },
  numbering: { config: [{ reference: "b", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
    style: { paragraph: { indent: { left: 300, hanging: 220 } } } }] }] },
  sections: [{ properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1000, bottom: 1000, left: 1134, right: 1134 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
      children: [run(`매크로 16개 항목 요약 · ${data.date} · `, { size: 15, color: C.sub }), new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 15, color: C.sub })] })] }) },
    children: body }],
});
Packer.toBuffer(doc).then(b => { fs.writeFileSync(OUT, b); console.log("wrote", OUT); });
