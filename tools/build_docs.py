"""Build the same plain-English guide in PDF and Word; runtime needs no docs packages."""

from pathlib import Path
import html, re
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from docx import Document
from docx.shared import Pt, Inches, RGBColor

R = Path(__file__).resolve().parents[1]
D = R / "docs"
text = (D / "USER_GUIDE.md").read_text()
styles = getSampleStyleSheet()
styles.add(
    ParagraphStyle(
        name="BodyGuide",
        fontName="Helvetica",
        fontSize=10,
        leading=15,
        spaceAfter=9,
        splitLongWords=True,
    )
)
styles["Title"].fontName = "Times-Roman"
styles["Title"].fontSize = 30
styles["Heading1"].fontName = "Helvetica-Bold"
styles["Heading1"].fontSize = 15
styles["Heading1"].spaceBefore = 18
styles["Heading1"].textColor = colors.HexColor("#AB2436")
doc = Document()
doc.core_properties.title = "CreaseIQ project guide — version 3.1.0"
doc.styles["Normal"].font.name = "Calibri"
doc.styles["Normal"].font.size = Pt(11)
story = []


def clean(s):
    return (
        s.replace("→", " > ")
        .replace("×", " x ")
        .replace("—", " - ")
        .replace("–", "-")
        .replace("₹", "INR ")
        .replace("’", "'")
        .replace("“", '"')
        .replace("”", '"')
        .replace("−", "-")
    )


def pdf(s, style="BodyGuide"):
    return Paragraph(html.escape(clean(s)).replace("`", ""), styles[style])


blocks = text.split("\n\n")
for block in blocks:
    block = block.strip()
    if not block:
        continue
    if block.startswith("|"):
        rows = [
            [x.strip() for x in line.strip("|").split("|")]
            for line in block.splitlines()
            if not re.fullmatch(r"[| :\-]+", line)
        ]
        table = Table(
            [[pdf(cell) for cell in row] for row in rows],
            repeatRows=1,
            hAlign="LEFT",
            colWidths=[130, 80, 120, 120],
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EDEFE8")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#AB2436")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        story += [table, Spacer(1, 12)]
        t = doc.add_table(rows=1, cols=len(rows[0]))
        t.style = "Light Shading Accent 1"
        for i, x in enumerate(rows[0]):
            t.rows[0].cells[i].text = x
        for row in rows[1:]:
            cells = t.add_row().cells
            for i, x in enumerate(row):
                cells[i].text = x
    elif block.startswith("# "):
        title = block[2:]
        story += [pdf(title, "Title"), Spacer(1, 12)]
        doc.add_heading(title, 0)
    elif block.startswith("## "):
        title = block[3:]
        story.append(pdf(title, "Heading1"))
        doc.add_heading(title, 1)
    else:
        for line in block.splitlines():
            story.append(pdf(line))
            doc.add_paragraph(line.replace("`", ""))


def footer(canvas, document):
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#596B72"))
    canvas.drawString(42, 28, "CREASEIQ 3.1.0 / EDUCATIONAL PROJECT")
    canvas.drawRightString(550, 28, str(document.page))


SimpleDocTemplate(
    str(D / "CreaseIQ_Project_Guide.pdf"),
    title="CreaseIQ Project Guide",
    author="CreaseIQ capstone",
    leftMargin=42,
    rightMargin=42,
    topMargin=40,
    bottomMargin=45,
).build(story, onFirstPage=footer, onLaterPages=footer)
section = doc.sections[0]
section.footer.paragraphs[0].text = "CreaseIQ 3.1.0 | Independent educational project"
doc.save(D / "CreaseIQ_Project_Guide.docx")
print("Generated the final guide in PDF and Word.")
