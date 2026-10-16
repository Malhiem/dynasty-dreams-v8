"""Bounded table and code flowables for the Security export."""
import re
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, Preformatted, Table, TableStyle


def wrapped_code(text, style):
    # Box-drawing separators in source comments are decoration, not code syntax.
    text = text.translate({n: "-" for n in range(0x2500, 0x2580)})
    text = text.replace("→", "->").replace("←", "<-").replace("≡", "==").replace("≥", ">=").replace("≤", "<=")
    bounded = ParagraphStyle("bounded_code", parent=style, leftIndent=0, rightIndent=0)
    # Courier at 8pt is 4.8pt per character; 85 columns stays within a 504pt frame.
    return [Preformatted(text, bounded, maxLineLength=85, splitChars=" ", newLineChars="")]


def markdown_table(lines, body, inline):
    rows = [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines]
    rows = [row for row in rows if not all(re.fullmatch(r"[:\- ]+", cell) for cell in row)]
    columns = max(len(row) for row in rows)
    style = ParagraphStyle("table_cell", parent=body, fontSize=8, leading=11, spaceAfter=0, wordWrap="CJK")
    # Each cell wraps independently; headers repeat after page breaks.
    data = [[Paragraph(inline(cell), style) for cell in row + [""] * (columns - len(row))] for row in rows]
    widths = ([55, 155, 294] if columns == 3 else [120, 384] if columns == 2 else [504 / columns] * columns)
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0f2fe")),
        ("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#bae6fd")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    return table
