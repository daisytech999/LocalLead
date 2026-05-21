"""Branded PDF audit report for a single lead.

Mirrors the brutalist look of the site: heavy black headers, red accents,
hard rules. Optionally white-labeled with the freelancer's own name (Agency).
"""

import io
import json

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

INK = colors.HexColor("#0a0a0a")
RED = colors.HexColor("#d63838")
GRAY = colors.HexColor("#8a8a82")
CREAM = colors.HexColor("#f4f1ea")

MARGIN = 0.75 * inch


def _hotness(score):
    if score is None:
        return "UNKNOWN"
    return "HOT LEAD" if score >= 80 else "WARM LEAD" if score >= 60 else "COLD LEAD"


def build_report(lead, brand: str = "LocalLead") -> bytes:
    width, height = letter
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)

    # Header band
    c.setFillColor(INK)
    c.rect(0, height - 1.4 * inch, width, 1.4 * inch, fill=1, stroke=0)
    c.setFillColor(CREAM)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(MARGIN, height - 0.75 * inch, "WEBSITE AUDIT REPORT")
    c.setFillColor(RED)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(MARGIN, height - 1.05 * inch, f"PREPARED BY {brand.upper()}")

    y = height - 1.9 * inch

    # Business name + score
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 26)
    c.drawString(MARGIN, y, (lead.name or "Unknown")[:38].upper())

    score = lead.score
    sc_color = RED if (score or 0) >= 80 else colors.HexColor("#e87d2a") if (score or 0) >= 60 else GRAY
    c.setFillColor(sc_color)
    c.setFont("Helvetica-Bold", 44)
    c.drawRightString(width - MARGIN, y - 6, str(score) if score is not None else "—")
    c.setFont("Helvetica-Bold", 9)
    c.drawRightString(width - MARGIN, y - 22, _hotness(score))

    y -= 0.5 * inch
    c.setFillColor(GRAY)
    c.setFont("Helvetica", 10)
    for line in [lead.address, lead.phone, lead.contact_email, lead.website]:
        if line:
            c.drawString(MARGIN, y, str(line)[:80])
            y -= 14

    # Divider
    y -= 8
    c.setStrokeColor(INK)
    c.setLineWidth(1.5)
    c.line(MARGIN, y, width - MARGIN, y)
    y -= 26

    # Audit findings
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(MARGIN, y, "WHAT WE FOUND")
    y -= 22

    audit = json.loads(lead.audit_json) if lead.audit_json else []
    issues = [f for f in audit if f.get("failed")]
    passed = [f for f in audit if not f.get("failed")]

    c.setFont("Helvetica", 10)
    if not issues:
        c.setFillColor(GRAY)
        c.drawString(MARGIN, y, "No major issues detected.")
        y -= 16
    for f in issues:
        if y < MARGIN + 1.2 * inch:
            c.showPage()
            y = height - MARGIN
        c.setFillColor(RED)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(MARGIN, y, "X")
        c.setFillColor(INK)
        c.drawString(MARGIN + 0.25 * inch, y, f.get("label", ""))
        if f.get("detail"):
            c.setFillColor(GRAY)
            c.setFont("Helvetica-Oblique", 9)
            c.drawString(MARGIN + 0.25 * inch, y - 12, str(f["detail"])[:90])
            y -= 12
        y -= 20

    # Passed checks summary
    if passed:
        y -= 6
        c.setFillColor(GRAY)
        c.setFont("Helvetica-Oblique", 9)
        c.drawString(MARGIN, y, "Passing: " + ", ".join(f["label"] for f in passed)[:110])
        y -= 18

    # Footer CTA band
    c.setFillColor(RED)
    c.rect(0, MARGIN - 0.15 * inch, width, 0.7 * inch, fill=1, stroke=0)
    c.setFillColor(CREAM)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(MARGIN, MARGIN + 0.18 * inch, "Let's fix these. Get in touch.")
    c.setFont("Helvetica", 8)
    c.drawRightString(width - MARGIN, MARGIN + 0.2 * inch, f"Audit by {brand}")

    c.showPage()
    c.save()
    return buf.getvalue()
