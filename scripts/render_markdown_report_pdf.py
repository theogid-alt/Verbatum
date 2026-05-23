from __future__ import annotations

import html
import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "docs" / "current_state_against_roadmap_may_september.md"
DEFAULT_OUTPUT = ROOT / "docs" / "current_state_against_roadmap_may_september.pdf"


class HorizontalRule(Flowable):
    def __init__(self, width: float, color=colors.HexColor("#d6ddd9")) -> None:
        super().__init__()
        self.width = width
        self.height = 8
        self.color = color

    def wrap(self, avail_width, avail_height):
        self.width = min(self.width, avail_width)
        return self.width, self.height

    def draw(self):
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(0.8)
        self.canv.line(0, self.height / 2, self.width, self.height / 2)


def build_styles():
    base = getSampleStyleSheet()
    return {
        "cover_title": ParagraphStyle(
            "cover_title",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=27,
            leading=33,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#17211f"),
            spaceAfter=14,
        ),
        "cover_subtitle": ParagraphStyle(
            "cover_subtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=11,
            leading=16,
            textColor=colors.HexColor("#5f6d68"),
            spaceAfter=6,
        ),
        "h1": ParagraphStyle(
            "h1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=25,
            textColor=colors.HexColor("#17211f"),
            spaceBefore=18,
            spaceAfter=10,
            keepWithNext=True,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=19,
            textColor=colors.HexColor("#167a5b"),
            spaceBefore=15,
            spaceAfter=7,
            keepWithNext=True,
        ),
        "h3": ParagraphStyle(
            "h3",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=12.5,
            leading=16,
            textColor=colors.HexColor("#155e88"),
            spaceBefore=11,
            spaceAfter=5,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.8,
            leading=14,
            textColor=colors.HexColor("#1f2a27"),
            spaceAfter=7,
        ),
        "small": ParagraphStyle(
            "small",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor("#43504c"),
        ),
        "bullet": ParagraphStyle(
            "bullet",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.4,
            leading=13,
            textColor=colors.HexColor("#1f2a27"),
            leftIndent=4,
        ),
        "toc": ParagraphStyle(
            "toc",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.7,
            leading=13,
            textColor=colors.HexColor("#1f2a27"),
            spaceAfter=3,
        ),
        "code": ParagraphStyle(
            "code",
            parent=base["Code"],
            fontName="Courier",
            fontSize=7.4,
            leading=10,
            textColor=colors.HexColor("#17342b"),
            backColor=colors.HexColor("#f1f5f3"),
            borderColor=colors.HexColor("#d6ddd9"),
            borderWidth=0.4,
            borderPadding=6,
            spaceBefore=4,
            spaceAfter=8,
        ),
        "table_cell": ParagraphStyle(
            "table_cell",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=7.8,
            leading=10,
            textColor=colors.HexColor("#1f2a27"),
        ),
        "table_header": ParagraphStyle(
            "table_header",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=7.7,
            leading=9.5,
            textColor=colors.white,
            alignment=TA_CENTER,
        ),
    }


def paragraph_text(value: str) -> str:
    text = html.escape(value.strip())
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"`([^`]+)`", r"<font name='Courier' size='8'>\1</font>", text)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda match: f"<a href='{html.escape(match.group(2), quote=True)}' color='#155e88'>{match.group(1)}</a>",
        text,
    )
    return text


def parse_blocks(markdown: str):
    lines = markdown.splitlines()
    blocks = []
    paragraph: list[str] = []
    i = 0

    def flush_paragraph():
        nonlocal paragraph
        if paragraph:
            blocks.append(("p", " ".join(line.strip() for line in paragraph).strip()))
            paragraph = []

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            i += 1
            continue
        if stripped.startswith("```"):
            flush_paragraph()
            i += 1
            code: list[str] = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i].rstrip())
                i += 1
            i += 1
            blocks.append(("code", "\n".join(code).rstrip()))
            continue
        if stripped.startswith("#"):
            flush_paragraph()
            level = len(stripped) - len(stripped.lstrip("#"))
            title = stripped[level:].strip()
            blocks.append((f"h{min(level, 3)}", title))
            i += 1
            continue
        if is_table_start(lines, i):
            flush_paragraph()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(parse_table_row(lines[i]))
                i += 1
            blocks.append(("table", rows))
            continue
        if stripped.startswith("- "):
            flush_paragraph()
            items = []
            while i < len(lines) and lines[i].strip().startswith("- "):
                items.append(lines[i].strip()[2:].strip())
                i += 1
            blocks.append(("ul", items))
            continue
        if re.match(r"^\d+[.]\s+", stripped):
            flush_paragraph()
            items = []
            while i < len(lines) and re.match(r"^\d+[.]\s+", lines[i].strip()):
                items.append(re.sub(r"^\d+[.]\s+", "", lines[i].strip()))
                i += 1
            blocks.append(("ol", items))
            continue
        paragraph.append(line)
        i += 1

    flush_paragraph()
    return blocks


def is_table_start(lines: list[str], index: int) -> bool:
    if index + 1 >= len(lines):
        return False
    return lines[index].strip().startswith("|") and re.match(r"^\|?[\s:|-]+\|[\s:|-]+\|?", lines[index + 1].strip()) is not None


def parse_table_row(line: str) -> list[str]:
    stripped = line.strip().strip("|")
    return [cell.strip() for cell in stripped.split("|")]


def table_separator(row: list[str]) -> bool:
    return all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in row if cell)


def heading_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "section"


def build_story(markdown: str, output_path: Path):
    styles = build_styles()
    blocks = parse_blocks(markdown)
    major_sections = [(kind, text) for kind, text in blocks if kind in {"h1", "h2"}]
    story = []
    story.extend(cover_page(styles))
    story.append(PageBreak())
    story.append(Paragraph("Table of Contents", styles["h1"]))
    story.append(HorizontalRule(480))
    for kind, title in major_sections[:60]:
        indent = "&nbsp;&nbsp;&nbsp;&nbsp;" if kind == "h2" else ""
        story.append(Paragraph(f"{indent}{paragraph_text(title)}", styles["toc"]))
    story.append(PageBreak())

    first_content_heading = True
    for kind, content in blocks:
        if kind == "h1":
            if not first_content_heading:
                story.append(PageBreak())
            first_content_heading = False
            story.append(Paragraph(paragraph_text(content), styles["h1"]))
            story.append(HorizontalRule(480))
        elif kind == "h2":
            story.append(Paragraph(paragraph_text(content), styles["h2"]))
        elif kind == "h3":
            story.append(Paragraph(paragraph_text(content), styles["h3"]))
        elif kind == "p":
            story.append(Paragraph(paragraph_text(content), styles["body"]))
        elif kind == "code":
            if content:
                story.append(Preformatted(content, styles["code"], maxLineLength=88))
        elif kind == "ul":
            story.append(list_flowable(content, styles, bullet_type="bullet"))
        elif kind == "ol":
            story.append(list_flowable(content, styles, bullet_type="1"))
        elif kind == "table":
            table = table_flowable(content, styles)
            if table:
                story.append(table)
                story.append(Spacer(1, 6))
    return story


def cover_page(styles):
    return [
        Spacer(1, 42 * mm),
        Paragraph("Verbatim Current State Against Roadmap", styles["cover_title"]),
        Paragraph("May to September technical roadmap comparison and next-step plan", styles["cover_subtitle"]),
        Paragraph("Generated from docs/current_state_against_roadmap_may_september.md", styles["cover_subtitle"]),
        Paragraph("Date: 2026-05-23", styles["cover_subtitle"]),
        Spacer(1, 16),
        HorizontalRule(480, color=colors.HexColor("#167a5b")),
        Spacer(1, 16),
        Paragraph(
            "A readable working report covering the current voice-agent stack, roadmap alignment, future plug-and-play integrations, and evaluation strategy.",
            styles["body"],
        ),
    ]


def list_flowable(items: list[str], styles, *, bullet_type: str):
    flow_items = [
        ListItem(Paragraph(paragraph_text(item), styles["bullet"]), leftIndent=10, bulletColor=colors.HexColor("#167a5b"))
        for item in items
    ]
    return ListFlowable(
        flow_items,
        bulletType=bullet_type,
        leftIndent=15,
        bulletFontName="Helvetica-Bold",
        bulletFontSize=8,
        bulletColor=colors.HexColor("#167a5b"),
        spaceAfter=7,
    )


def table_flowable(rows: list[list[str]], styles):
    rows = [row for row in rows if not table_separator(row)]
    if not rows:
        return None
    max_cols = max(len(row) for row in rows)
    normalized = [row + [""] * (max_cols - len(row)) for row in rows]
    data = []
    for row_index, row in enumerate(normalized):
        style = styles["table_header"] if row_index == 0 else styles["table_cell"]
        data.append([Paragraph(paragraph_text(cell), style) for cell in row])
    available_width = 480
    col_width = available_width / max_cols
    table = Table(data, colWidths=[col_width] * max_cols, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#167a5b")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d6ddd9")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7faf8")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#d6ddd9"))
    canvas.setLineWidth(0.5)
    canvas.line(doc.leftMargin, 15 * mm, doc.pagesize[0] - doc.rightMargin, 15 * mm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#687370"))
    canvas.drawString(doc.leftMargin, 10 * mm, "Verbatim roadmap report")
    canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


def render_pdf(source: Path, output: Path) -> None:
    markdown = source.read_text(encoding="utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    doc = BaseDocTemplate(
        str(output),
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=20 * mm,
        title="Verbatim Current State Against Roadmap",
        author="Verbatim",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    template = PageTemplate(id="report", frames=[frame], onPage=footer)
    doc.addPageTemplates([template])
    doc.build(build_story(markdown, output))


def main() -> None:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SOURCE
    output = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUTPUT
    render_pdf(source, output)
    print(output)


if __name__ == "__main__":
    main()
