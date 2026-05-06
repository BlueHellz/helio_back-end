"""ReportLab PDFs: solar roof design page and optional full proposal (estimate)."""

from __future__ import annotations

from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.flowables import Flowable

_PANEL_W_DEFAULT = 400.0

_BRAND_HEADER = colors.HexColor("#0f172a")
_BRAND_ACCENT = colors.HexColor("#0284c7")
_ROOF_FILL = colors.HexColor("#e2e8f0")
_ROOF_STROKE = colors.HexColor("#64748b")
_PANEL_DOT = colors.HexColor("#0c4a6e")


def _money_usd(n: float | int | None) -> str:
    if n is None:
        return "—"
    try:
        v = float(n)
    except (TypeError, ValueError):
        return "—"
    sign = "-" if v < 0 else ""
    v = abs(v)
    return f"{sign}${v:,.2f}"


def _get(d: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def _panel_count(design: dict[str, Any]) -> int:
    ac = _get(design, "activeConfig", "active_config", default=[]) or []
    return len(ac) if isinstance(ac, list) else 0


def _system_kw_dc(design: dict[str, Any], estimate: dict[str, Any] | None) -> float:
    if estimate:
        v = _get(estimate, "systemSizeKw", "system_size_kw")
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    n = _panel_count(design)
    return n * (_PANEL_W_DEFAULT / 1000.0)


def _yearly_kwh(design: dict[str, Any], estimate: dict[str, Any] | None) -> float | None:
    if estimate:
        v = _get(estimate, "annualProductionKwh", "annual_production_kwh")
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    v = _get(design, "yearlyEnergyDcKwh", "yearly_energy_dc_kwh")
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _roof_area_sqm(design: dict[str, Any]) -> float | None:
    wr = _get(design, "wholeRoofStats", "whole_roof_stats")
    if not isinstance(wr, dict):
        return None
    a = _get(wr, "area", "areaMeters2", "area_meters2")
    if a is None:
        return None
    try:
        return float(a)
    except (TypeError, ValueError):
        return None


class _RoofDiagram(Flowable):
    """Simplified roof footprint + panel markers from canvas coordinates in designData."""

    def __init__(self, design: dict[str, Any], width: float, height: float) -> None:
        Flowable.__init__(self)
        self._design = design
        self.width = width
        self.height = height

    def draw(self) -> None:
        canvas = self.canv
        segments = _get(self._design, "segments", default=[]) or []
        panels = _get(self._design, "activeConfig", "active_config", default=[]) or []
        if not isinstance(segments, list):
            segments = []
        if not isinstance(panels, list):
            panels = []

        xs: list[float] = []
        ys: list[float] = []
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            poly = seg.get("polygon") or []
            for p in poly:
                if not isinstance(p, dict):
                    continue
                xs.append(float(p.get("x", 0)))
                ys.append(float(p.get("y", 0)))
        for pan in panels:
            if not isinstance(pan, dict):
                continue
            c = pan.get("center") or {}
            if isinstance(c, dict) and "x" in c and "y" in c:
                xs.append(float(c["x"]))
                ys.append(float(c["y"]))

        canvas.setStrokeColor(_ROOF_STROKE)
        canvas.setFillColor(colors.white)
        canvas.roundRect(0, 0, self.width, self.height, 6, fill=1, stroke=1)

        if not xs:
            canvas.setFont("Helvetica-Oblique", 9)
            canvas.setFillColor(colors.HexColor("#64748b"))
            canvas.drawCentredString(self.width / 2, self.height / 2, "Roof diagram unavailable")
            return

        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        w_dat = max_x - min_x or 1.0
        h_dat = max_y - min_y or 1.0
        margin = 14.0
        scale = min((self.width - 2 * margin) / w_dat, (self.height - 2 * margin) / h_dat)

        def tx(x: float) -> float:
            return (x - min_x) * scale + margin

        def ty_flip(y: float) -> float:
            return margin + (max_y - y) * scale

        for seg in segments:
            if not isinstance(seg, dict):
                continue
            poly = seg.get("polygon") or []
            if len(poly) < 3:
                continue
            path = canvas.beginPath()
            first = True
            for p in poly:
                if not isinstance(p, dict):
                    continue
                px, py = tx(float(p.get("x", 0))), ty_flip(float(p.get("y", 0)))
                if first:
                    path.moveTo(px, py)
                    first = False
                else:
                    path.lineTo(px, py)
            path.close()
            canvas.setFillColor(_ROOF_FILL)
            canvas.setStrokeColor(_ROOF_STROKE)
            canvas.drawPath(path, fill=1, stroke=1)

        pr = max(1.8, scale * min(w_dat, h_dat) * 0.012)
        canvas.setFillColor(_PANEL_DOT)
        canvas.setStrokeColor(colors.HexColor("#0369a1"))
        for pan in panels:
            if not isinstance(pan, dict):
                continue
            c = pan.get("center") or {}
            if not isinstance(c, dict) or "x" not in c or "y" not in c:
                continue
            px, py = tx(float(c["x"])), ty_flip(float(c["y"]))
            canvas.circle(px, py, pr, fill=1, stroke=1)


def _base_styles() -> tuple[Any, ParagraphStyle, ParagraphStyle, ParagraphStyle]:
    base = getSampleStyleSheet()
    title = ParagraphStyle(
        name="ProposalTitle",
        parent=base["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=18,
        textColor=_BRAND_HEADER,
        spaceAfter=6,
    )
    sub = ParagraphStyle(
        name="ProposalSub",
        parent=base["Normal"],
        fontSize=11,
        textColor=colors.HexColor("#334155"),
        spaceAfter=14,
    )
    body = ParagraphStyle(
        name="ProposalBody",
        parent=base["Normal"],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#1e293b"),
    )
    return base, title, sub, body


def render_design_pdf_bytes(design_data: dict[str, Any]) -> bytes:
    """Single branded page: roof diagram, system specs, panel count."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        topMargin=0.65 * inch,
        bottomMargin=0.65 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
    )
    _, title, sub, body = _base_styles()
    story: list[Any] = []

    story.append(Paragraph("LIMYÈ", ParagraphStyle("Brand", parent=title, fontSize=11, textColor=_BRAND_ACCENT)))
    story.append(Paragraph("Solar roof design", title))
    story.append(Paragraph("Prepared for your home — system layout and key specifications.", sub))

    story.append(
        Table(
            [[Paragraph("<b>Design summary</b>", body)]],
            colWidths=[6.5 * inch],
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), _BRAND_HEADER),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            ),
        )
    )
    story.append(Spacer(1, 0.15 * inch))

    diagram = _RoofDiagram(design_data, width=6.5 * inch, height=3.0 * inch)
    story.append(diagram)
    story.append(Spacer(1, 0.2 * inch))

    n = _panel_count(design_data)
    kw = _system_kw_dc(design_data, None)
    yk = _yearly_kwh(design_data, None)
    area = _roof_area_sqm(design_data)

    spec_rows: list[list[Any]] = [
        [Paragraph("<b>Panels (layout)</b>", body), Paragraph(str(n), body)],
        [Paragraph("<b>Approx. system size (DC)</b>", body), Paragraph(f"{kw:.2f} kW", body)],
    ]
    if yk is not None:
        spec_rows.append(
            [Paragraph("<b>Est. annual production (DC)</b>", body), Paragraph(f"{yk:,.0f} kWh", body)]
        )
    if area is not None:
        spec_rows.append(
            [Paragraph("<b>Modeled roof area</b>", body), Paragraph(f"{area:,.0f} m²", body)]
        )

    spec_table = Table(spec_rows, colWidths=[3.1 * inch, 3.4 * inch])
    spec_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(spec_table)
    story.append(Spacer(1, 0.25 * inch))
    story.append(
        Paragraph(
            "<i>Figures reflect Google Solar building insights and LIMYÈ layout assumptions. "
            "Final engineering may vary.</i>",
            ParagraphStyle("Fine", parent=body, fontSize=8, textColor=colors.HexColor("#64748b")),
        )
    )

    doc.build(story)
    return buf.getvalue()


def render_estimate_pdf_bytes(design_data: dict[str, Any], estimate_data: dict[str, Any] | None) -> bytes:
    """Proposal-style document: design summary plus optional market estimate breakdown."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        topMargin=0.65 * inch,
        bottomMargin=0.65 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
    )
    _, title, sub, body = _base_styles()
    small = ParagraphStyle(
        name="Small",
        parent=body,
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#475569"),
    )
    story: list[Any] = []

    story.append(Paragraph("LIMYÈ", ParagraphStyle("Brand", parent=title, fontSize=11, textColor=_BRAND_ACCENT)))
    story.append(Paragraph("Solar proposal", title))
    story.append(
        Paragraph(
            "Design snapshot and projected value — savings and incentives are illustrative until "
            "a site-specific contract is finalized.",
            sub,
        )
    )

    # --- Design summary block
    story.append(
        Table(
            [[Paragraph("<b>Design overview</b>", body)]],
            colWidths=[6.5 * inch],
            style=TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), _BRAND_HEADER),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            ),
        )
    )
    story.append(Spacer(1, 0.12 * inch))

    diagram = _RoofDiagram(design_data, width=6.0 * inch, height=2.6 * inch)
    story.append(diagram)
    story.append(Spacer(1, 0.15 * inch))

    n = _panel_count(design_data)
    if estimate_data:
        pn = _get(estimate_data, "panelCount", "panel_count")
        if pn is not None:
            try:
                n = int(pn)
            except (TypeError, ValueError):
                pass

    kw = _system_kw_dc(design_data, estimate_data)
    yk = _yearly_kwh(design_data, estimate_data)
    overview_rows = [
        [Paragraph("<b>Panels</b>", body), Paragraph(str(n), body)],
        [Paragraph("<b>System size (DC)</b>", body), Paragraph(f"{kw:.2f} kW", body)],
    ]
    if yk is not None:
        overview_rows.append([Paragraph("<b>Year-1 production (est.)</b>", body), Paragraph(f"{yk:,.0f} kWh", body)])

    ot = Table(overview_rows, colWidths=[3.1 * inch, 3.4 * inch])
    ot.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f1f5f9")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(ot)
    story.append(Spacer(1, 0.22 * inch))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0"), spaceBefore=4, spaceAfter=12))

    # --- Estimate / economics
    if estimate_data:
        tc = _get(estimate_data, "totalCost", "total_cost")
        s25 = _get(estimate_data, "savings25yr", "savings_25yr")
        pb = _get(estimate_data, "paybackYears", "payback_years")

        incentives = estimate_data.get("incentives") or []
        if not isinstance(incentives, list):
            incentives = []

        summary_rows = [
            [Paragraph("<b>Investment</b>", body), Paragraph(_money_usd(tc), body)],
            [
                Paragraph("<b>Illustrative lifetime savings</b>", body),
                Paragraph(_money_usd(s25), body),
            ],
            [
                Paragraph("<b>Simple payback (illustrative)</b>", body),
                Paragraph(f"{pb} yr" if pb is not None else "—", body),
            ],
        ]
        st = Table(summary_rows, colWidths=[3.5 * inch, 3 * inch])
        st.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                    ("BOX", (0, 0), (-1, -1), 0.75, _BRAND_ACCENT),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("LINEBELOW", (0, 0), (-1, -2), 0.25, colors.HexColor("#e2e8f0")),
                ]
            )
        )
        story.append(Paragraph("<b>Economics snapshot</b>", title))
        story.append(Spacer(1, 0.08 * inch))
        story.append(st)
        story.append(Spacer(1, 0.2 * inch))

        if incentives:
            story.append(Paragraph("<b>Incentives</b>", ParagraphStyle("H2", parent=title, fontSize=13)))
            story.append(Spacer(1, 0.06 * inch))
            for inc in incentives:
                if not isinstance(inc, dict):
                    continue
                name = str(inc.get("name") or inc.get("label") or "Incentive")
                amt = inc.get("amountUsd") or inc.get("amount_usd")
                pct = inc.get("percentOfCost") or inc.get("percent_of_cost")
                line = f"• {name}"
                if pct is not None:
                    line += f" ({pct}% of project)"
                line += f" — {_money_usd(amt if amt is not None else None)}"
                story.append(Paragraph(line, body))
            story.append(Spacer(1, 0.18 * inch))

        equip = estimate_data.get("equipmentBreakdown") or estimate_data.get("equipment_breakdown") or []
        if isinstance(equip, list) and equip:
            story.append(Paragraph("<b>Cost breakdown (illustrative)</b>", ParagraphStyle("H2", parent=title, fontSize=13)))
            story.append(Spacer(1, 0.06 * inch))
            er: list[list[Any]] = [
                [Paragraph("<b>Category</b>", body), Paragraph("<b>Share</b>", body), Paragraph("<b>Amount</b>", body)]
            ]
            for row in equip:
                if not isinstance(row, dict):
                    continue
                cat = str(row.get("category") or "—")
                pct = row.get("percent") or row.get("pct")
                amt = row.get("amountUsd") or row.get("amount_usd")
                er.append(
                    [
                        Paragraph(cat, body),
                        Paragraph(f"{pct}%" if pct is not None else "—", body),
                        Paragraph(_money_usd(amt if amt is not None else None), body),
                    ]
                )
            et = Table(er, colWidths=[2.6 * inch, 1.2 * inch, 2.5 * inch])
            et.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), _BRAND_HEADER),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
                        ("LEFTPADDING", (0, 0), (-1, -1), 7),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ]
                )
            )
            story.append(et)

        story.append(Spacer(1, 0.25 * inch))
        story.append(
            Paragraph(
                "<i>Market-based assumptions (tariffs, equipment costs, incentives) are simplified. "
                "Your installer will confirm pricing, interconnection, and incentive eligibility.</i>",
                small,
            )
        )
    else:
        story.append(Paragraph("<b>Estimate details</b>", ParagraphStyle("H2", parent=title, fontSize=13)))
        story.append(
            Paragraph(
                "No savings or pricing estimate was attached to this package. "
                "Run an estimate in the LIMYÈ app and save again to receive a full "
                "cost, savings, and incentive breakdown in this document.",
                body,
            )
        )
        story.append(Spacer(1, 0.15 * inch))
        story.append(
            Paragraph(
                "We can still help you review the roof layout and system size shown above with a "
                "local installation partner when you are ready.",
                body,
            )
        )

    doc.build(story)
    return buf.getvalue()


__all__ = ["render_design_pdf_bytes", "render_estimate_pdf_bytes"]
