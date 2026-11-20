"""Diagnosis report as PDF (reportlab).

Sections: photo + Grad-CAM, identified plant (scientific name), diagnosis, confidence, status /
uncertainty, symptoms, causes, conditions, treatment plan, recommended products (verified
listings), references, and the model version / disclaimer.
"""
from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (Image, KeepTogether, ListFlowable, ListItem, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)
from xml.sax.saxutils import escape

FOREST = colors.HexColor("#14532D")
EMERALD = colors.HexColor("#059669")
MUTED = colors.HexColor("#5B6B60")
LINE = colors.HexColor("#DDE5DF")
WARN = colors.HexColor("#B45309")

_ss = getSampleStyleSheet()
H1 = ParagraphStyle("h1", parent=_ss["Heading1"], fontName="Helvetica-Bold", fontSize=18, textColor=FOREST, spaceAfter=4)
H2 = ParagraphStyle("h2", parent=_ss["Heading2"], fontName="Helvetica-Bold", fontSize=12.5, textColor=FOREST,
                    spaceBefore=10, spaceAfter=4)
H3 = ParagraphStyle("h3", parent=_ss["Heading3"], fontName="Helvetica-Bold", fontSize=10.5, textColor=colors.black,
                    spaceBefore=6, spaceAfter=2)
P = ParagraphStyle("p", parent=_ss["BodyText"], fontName="Helvetica", fontSize=9.5, leading=13, alignment=TA_LEFT)
SMALL = ParagraphStyle("s", parent=P, fontSize=8, leading=10.5, textColor=MUTED)
NOTE = ParagraphStyle("n", parent=P, textColor=WARN)


def _p(text, style=P):
    return Paragraph(escape(str(text or "—")), style)


def _bullets(items, style=P):
    items = [i for i in (items or []) if i]
    if not items:
        return _p("—", SMALL)
    return ListFlowable([ListItem(_p(i, style), leftIndent=10) for i in items], bulletType="bullet", start="•",
                        leftIndent=10, bulletFontSize=8)


def _img(data: bytes | None, w: float):
    if not data:
        return _p("Image not stored", SMALL)
    im = Image(io.BytesIO(data))
    ratio = im.imageHeight / im.imageWidth
    im.drawWidth, im.drawHeight = w, min(w * ratio, 75 * mm)
    return im


def build_pdf(d: dict, photo: bytes | None, heatmap: bytes | None, user=None, products: list | None = None) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm,
                            bottomMargin=16 * mm, title=f"PlantDoctor report #{d.get('id')}", author="PlantDoctor")
    s = []
    created = d.get("created_at", "")
    try:
        created = datetime.fromisoformat(created).strftime("%d %b %Y, %H:%M %Z")
    except Exception:
        pass
    s += [Paragraph("PlantDoctor — Diagnosis report", H1),
          _p(f"Report #{d.get('id')} · {created} · model {d.get('model_version')}"
             + (f" · prepared for {user.name}" if user else ""), SMALL), Spacer(1, 6)]

    t = Table([[_img(photo, 80 * mm), _img(heatmap, 80 * mm)],
               [_p("Uploaded photo", SMALL), _p("Grad-CAM: regions that most influenced the model", SMALL)]],
              colWidths=[88 * mm, 88 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    s += [t, Spacer(1, 6)]

    plant = d.get("plant") or {}
    info = plant.get("info") or {}
    diag = d.get("diagnosis")
    k = (diag or {}).get("knowledge") or {}
    rows = [
        ["Plant", f"{info.get('name') or plant.get('typed') or '—'}"
                  + (f" ({info.get('scientific')})" if info.get("scientific") else "")],
        ["Plant type", info.get("type") or "—"],
        ["Plant identified by", {"user": "you (typed name)", "image": "the image model"}.get(plant.get("source"), "—")
         + (f" — {plant['confidence'] * 100:.0f}% confidence" if plant.get("confidence") is not None else "")],
        ["Condition", (diag or {}).get("name") or "Not determined"],
        ["Confidence", f"{diag['confidence'] * 100:.1f}%" if diag else "—"],
        ["Result status", d.get("status", "").replace("_", " ")],
    ]
    if k:
        rows += [["Cause / pathogen", k.get("pathogen")], ["Type", k.get("kind")],
                 ["Affected parts", ", ".join(k.get("affected_parts") or []) or "—"]]
    tbl = Table([[_p(a, H3), _p(b)] for a, b in rows], colWidths=[42 * mm, 134 * mm])
    tbl.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    s += [Paragraph("Summary", H2), tbl]
    if d.get("message"):
        s += [Spacer(1, 4), _p(d["message"], NOTE)]

    alts = d.get("alternatives") or []
    if alts:
        s += [Paragraph("Other possibilities considered", H2),
              _bullets([f"{a['name']} ({a.get('crop') or ''}) — {a['probability'] * 100:.1f}%" for a in alts])]
    if d.get("findings"):
        s += [Paragraph("Possible co-occurring problems", H2),
              _bullets([f"{a['name']} — {a['probability'] * 100:.1f}%" for a in d["findings"]])]

    if k and k.get("kind") not in ("healthy", "none"):
        tr = k.get("treatment", {})
        s += [Paragraph("Symptoms", H2), _p(k.get("symptoms")),
              Paragraph("Possible causes", H2), _p(k.get("causes")),
              Paragraph("Conditions that favour it", H2), _p(k.get("conditions")),
              Paragraph("Treatment plan", H2),
              Paragraph("Immediate actions", H3), _bullets(tr.get("immediate")),
              Paragraph("Organic / cultural methods", H3), _bullets(tr.get("organic"))]
        chem = tr.get("chemical") or []
        if chem:
            s += [Paragraph("Chemical options (active ingredients)", H3),
                  _bullets([f"{c['ai']} — {c.get('group', '')}" + (f" ({c['note']})" if c.get("note") else "") for c in chem]),
                  _p(k.get("chemical_notice"), SMALL)]
        s += [Paragraph("Prevention", H3), _bullets(tr.get("preventive")),
              Paragraph("Watering", H3), _p(tr.get("watering")),
              Paragraph("Soil", H3), _p(tr.get("soil")),
              Paragraph("Fertilizer", H3), _p(tr.get("fertilizer")),
              Paragraph("Long-term care", H3), _bullets(tr.get("long_term"))]
    elif k:
        s += [Paragraph("Notes", H2), _p(k.get("symptoms")), _bullets((k.get("treatment") or {}).get("preventive"))]

    if products:
        s += [Paragraph("Products available in Pakistan (verified listings)", H2)]
        prow = [[_p("Product", H3), _p("Active ingredient", H3), _p("Pack / price", H3), _p("Where", H3)]]
        for pr in products[:10]:
            price = f"Rs {pr['price_pkr']:,.0f}" if pr.get("price_pkr") else "—"
            prow.append([_p(pr["title"][:70], SMALL), _p(pr["active_ingredient"][:60], SMALL),
                         _p(f"{pr.get('pack_size') or ''} · {price}", SMALL),
                         Paragraph(f'<link href="{escape(pr["url"])}">{escape(pr["store"])}</link> '
                                   f'(checked {escape(pr["verified_on"])})', SMALL)])
        pt = Table(prow, colWidths=[58 * mm, 46 * mm, 32 * mm, 40 * mm], repeatRows=1)
        pt.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        s += [pt, _p("Prices and availability change; confirm on the store page. Always follow the product label.", SMALL)]

    refs = k.get("references") or []
    if refs:
        s += [Paragraph("References", H2)]
        s += [Paragraph(f'{escape(r["title"])} — {escape(r.get("publisher") or "")}. '
                        f'<link href="{escape(r["url"])}" color="#059669">{escape(r["url"])}</link>', SMALL) for r in refs]
    if d.get("notes"):
        s += [Paragraph("Your notes", H2), _p(d["notes"])]
    s += [Spacer(1, 10), KeepTogether([_p(
        "PlantDoctor is decision support, not a laboratory diagnosis. Image models can be wrong, especially on "
        "photos unlike their training data. Confirm serious findings with an agronomist or your district "
        "Agriculture Extension office before treating. Chemical options name active ingredients only; use a product "
        "registered in Pakistan for the crop and follow its label for dose, interval, pre-harvest interval and "
        "protective equipment.", SMALL)])]

    def footer(c, _doc):
        c.setFont("Helvetica", 7.5)
        c.setFillColor(MUTED)
        c.drawString(16 * mm, 9 * mm, f"PlantDoctor report #{d.get('id')} · page {c.getPageNumber()}")
    doc.build(s, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
