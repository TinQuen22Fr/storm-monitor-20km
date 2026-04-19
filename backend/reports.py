"""PDF bulletin report generator using reportlab."""
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


LOURDES_TZ = ZoneInfo("Europe/Paris")


def _utc_to_local_str(iso_or_ts, fmt: str = "%d/%m/%Y · %H:%M") -> str:
    """Convert an ISO UTC string (or epoch) to Europe/Paris formatted string."""
    if iso_or_ts is None or iso_or_ts == "":
        return ""
    try:
        if isinstance(iso_or_ts, (int, float)):
            dt = datetime.fromtimestamp(float(iso_or_ts), tz=timezone.utc)
        else:
            s = str(iso_or_ts).replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(LOURDES_TZ).strftime(fmt)
    except Exception:
        return str(iso_or_ts)


SLATE_900 = colors.HexColor("#0F172A")
SLATE_600 = colors.HexColor("#475569")
SLATE_400 = colors.HexColor("#94A3B8")
SLATE_200 = colors.HexColor("#E2E8F0")
RED = colors.HexColor("#DC2626")
AMBER = colors.HexColor("#D97706")
EMERALD = colors.HexColor("#10B981")


def _styles() -> Dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "kicker": ParagraphStyle(
            "kicker",
            parent=base["Normal"],
            fontName="Courier",
            fontSize=7,
            textColor=SLATE_400,
            spaceAfter=4,
            leading=9,
        ),
        "h1": ParagraphStyle(
            "h1",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=28,
            textColor=SLATE_900,
            leading=30,
            spaceAfter=4,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            textColor=SLATE_900,
            leading=14,
            spaceBefore=14,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            textColor=SLATE_600,
            leading=13,
        ),
        "mono": ParagraphStyle(
            "mono",
            parent=base["Normal"],
            fontName="Courier",
            fontSize=8,
            textColor=SLATE_900,
            leading=11,
        ),
        "alert": ParagraphStyle(
            "alert",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11,
            textColor=RED,
            leading=15,
            spaceAfter=4,
        ),
        "safe": ParagraphStyle(
            "safe",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11,
            textColor=EMERALD,
            leading=15,
            spaceAfter=4,
        ),
    }


def _fmt(v: Any, suffix: str = "", decimals: int = 0) -> str:
    if v is None:
        return "—"
    try:
        if decimals:
            return f"{float(v):.{decimals}f}{suffix}"
        return f"{int(round(float(v)))}{suffix}"
    except Exception:
        return str(v)


def build_bulletin_pdf(
    current: Dict,
    zones: Dict,
    history: Dict,
    forecast: Dict,
    strikes: List[Dict],
) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="Bulletin orage — Lourdes",
        author="Suivi d'orage Lourdes",
    )
    s = _styles()
    story: List[Any] = []

    now_local = datetime.now(LOURDES_TZ)
    kicker = f"Bulletin orage · Lourdes · {now_local.strftime('%d %b %Y · %H:%M')} (heure locale)"
    story.append(Paragraph(kicker.upper(), s["kicker"]))
    story.append(Paragraph("Suivi d'orage en temps réel", s["h1"]))
    story.append(Paragraph(
        "Rayon de surveillance : 20 km autour de Lourdes (43.0951°N, -0.0434°E).", s["body"]
    ))

    # Status banner
    storm = bool(zones.get("storm_active"))
    if storm:
        story.append(Spacer(1, 10))
        story.append(Paragraph("⚠ ACTIVITÉ ORAGEUSE DÉTECTÉE", s["alert"]))
        story.append(Paragraph(
            f"CAPE max {_fmt(zones.get('max_cape'))} J/kg · LPI max {_fmt(zones.get('max_lightning_potential'), decimals=1)}.",
            s["body"],
        ))
    else:
        story.append(Spacer(1, 10))
        story.append(Paragraph("● CIEL CALME À MODÉRÉMENT INSTABLE", s["safe"]))
        story.append(Paragraph(
            "Aucune activité orageuse dans un rayon de 20 km au moment du bulletin.",
            s["body"],
        ))

    # Current conditions table
    c = (current or {}).get("current", {})
    cape = current.get("cape")
    lp = current.get("lightning_potential")
    story.append(Paragraph("CONDITIONS ACTUELLES", s["h2"]))
    data = [
        ["Température", _fmt(c.get("temperature_2m"), " °C", 1), "Vent", _fmt(c.get("wind_speed_10m"), " km/h")],
        ["Humidité", _fmt(c.get("relative_humidity_2m"), " %"), "Pression", _fmt(c.get("pressure_msl"), " hPa")],
        ["Rafales", _fmt(c.get("wind_gusts_10m"), " km/h"), "Précip.", _fmt(c.get("precipitation"), " mm", 1)],
        ["CAPE", _fmt(cape, " J/kg"), "LPI", _fmt(lp, "", 1)],
    ]
    t = Table(data, colWidths=[32 * mm, 45 * mm, 32 * mm, 45 * mm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (-1, -1), SLATE_900),
        ("TEXTCOLOR", (0, 0), (0, -1), SLATE_400),
        ("TEXTCOLOR", (2, 0), (2, -1), SLATE_400),
        ("FONTNAME", (1, 0), (1, -1), "Courier"),
        ("FONTNAME", (3, 0), (3, -1), "Courier"),
        ("LINEABOVE", (0, 0), (-1, 0), 0.5, SLATE_200),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, SLATE_200),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t)

    # 24h history summary
    hourly_hist = (history or {}).get("hourly", [])
    storm_hours = sum(1 for h in hourly_hist if h.get("is_storm"))
    total_precip = sum((h.get("precipitation") or 0) for h in hourly_hist)
    max_gust = max((h.get("wind_gust") or 0) for h in hourly_hist) if hourly_hist else 0
    story.append(Paragraph("HISTORIQUE 24 H", s["h2"]))
    story.append(Paragraph(
        f"Heures orageuses : <b>{storm_hours}</b> · Précipitations totales : <b>{total_precip:.1f} mm</b> · Rafale max : <b>{max_gust:.0f} km/h</b>",
        s["body"],
    ))

    # Forecast next 12h
    hourly_fc = (forecast or {}).get("hourly", [])[:12]
    if hourly_fc:
        story.append(Paragraph("PRÉVISION 12 H", s["h2"]))
        rows = [["Heure locale", "T°", "Précip.", "Prob.", "CAPE", "LPI"]]
        for h in hourly_fc:
            ts = h.get("time", "").split("T")[-1][:5]
            rows.append([
                ts,
                _fmt(h.get("temperature"), "°C", 1),
                _fmt(h.get("precipitation"), " mm", 1),
                _fmt(h.get("precipitation_probability"), "%"),
                _fmt(h.get("cape")),
                _fmt(h.get("lightning_potential"), "", 1),
            ])
        t = Table(rows, colWidths=[22 * mm, 22 * mm, 28 * mm, 25 * mm, 25 * mm, 25 * mm])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("TEXTCOLOR", (0, 0), (-1, 0), SLATE_400),
            ("FONTNAME", (0, 1), (-1, -1), "Courier"),
            ("TEXTCOLOR", (0, 1), (-1, -1), SLATE_900),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, SLATE_200),
            ("LINEBELOW", (0, -1), (-1, -1), 0.5, SLATE_200),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t)

    # Recent strikes
    story.append(Paragraph("IMPACTS FOUDRE · DERNIÈRE HEURE", s["h2"]))
    if strikes:
        rows = [["Heure locale", "Lat", "Lon", "Distance"]]
        for st in strikes[:20]:
            rows.append([
                _utc_to_local_str(st.get("ts") or st.get("iso", ""), "%d/%m %H:%M:%S"),
                f"{st.get('lat'):.4f}",
                f"{st.get('lon'):.4f}",
                _fmt(st.get("distance_km"), " km", 1),
            ])
        t = Table(rows, colWidths=[48 * mm, 35 * mm, 35 * mm, 30 * mm])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("TEXTCOLOR", (0, 0), (-1, 0), SLATE_400),
            ("FONTNAME", (0, 1), (-1, -1), "Courier"),
            ("TEXTCOLOR", (0, 1), (-1, -1), SLATE_900),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, SLATE_200),
            ("LINEBELOW", (0, -1), (-1, -1), 0.5, SLATE_200),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t)
    else:
        story.append(Paragraph("Aucun impact de foudre enregistré dans le rayon.", s["body"]))

    # Footer
    story.append(Spacer(1, 18))
    story.append(Paragraph(
        "Sources : Open-Meteo (météo) · Blitzortung.org (foudre). Bulletin informatif — non contractuel.",
        ParagraphStyle("footer", parent=s["body"], fontSize=7, textColor=SLATE_400, leading=10),
    ))

    doc.build(story)
    return buf.getvalue()
