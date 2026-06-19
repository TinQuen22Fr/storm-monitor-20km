"""PDF bulletin report generator using reportlab. Supports multi-zone bulletins."""
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


DEFAULT_TZ = ZoneInfo("Europe/Paris")


def _resolve_tz(tz_name: Optional[str]) -> ZoneInfo:
    if not tz_name:
        return DEFAULT_TZ
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return DEFAULT_TZ


def _utc_to_local_str(iso_or_ts, tz: ZoneInfo, fmt: str = "%d/%m/%Y · %H:%M") -> str:
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
        return dt.astimezone(tz).strftime(fmt)
    except Exception:
        return str(iso_or_ts)


SLATE_900 = colors.HexColor("#0F172A")
SLATE_600 = colors.HexColor("#475569")
SLATE_400 = colors.HexColor("#94A3B8")
SLATE_200 = colors.HexColor("#E2E8F0")
SLATE_50 = colors.HexColor("#F8FAFC")
BLUE_700 = colors.HexColor("#1D4ED8")
RED = colors.HexColor("#DC2626")
AMBER = colors.HexColor("#D97706")
EMERALD = colors.HexColor("#10B981")


def _styles() -> Dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "kicker": ParagraphStyle("kicker", parent=base["Normal"], fontName="Courier",
                                 fontSize=7, textColor=SLATE_400, spaceAfter=4, leading=9),
        "h1": ParagraphStyle("h1", parent=base["Normal"], fontName="Helvetica-Bold",
                             fontSize=28, textColor=SLATE_900, leading=30, spaceAfter=4),
        "zone_h": ParagraphStyle("zone_h", parent=base["Normal"], fontName="Helvetica-Bold",
                                 fontSize=20, textColor=SLATE_900, leading=24, spaceBefore=4, spaceAfter=2),
        "zone_sub": ParagraphStyle("zone_sub", parent=base["Normal"], fontName="Courier",
                                   fontSize=8, textColor=SLATE_400, leading=12, spaceAfter=8),
        "h2": ParagraphStyle("h2", parent=base["Normal"], fontName="Helvetica-Bold",
                             fontSize=10, textColor=SLATE_900, leading=14, spaceBefore=14, spaceAfter=6),
        "body": ParagraphStyle("body", parent=base["Normal"], fontName="Helvetica",
                               fontSize=9, textColor=SLATE_600, leading=13),
        "alert": ParagraphStyle("alert", parent=base["Normal"], fontName="Helvetica-Bold",
                                fontSize=11, textColor=RED, leading=15, spaceAfter=4),
        "safe": ParagraphStyle("safe", parent=base["Normal"], fontName="Helvetica-Bold",
                               fontSize=11, textColor=EMERALD, leading=15, spaceAfter=4),
        "zone_link": ParagraphStyle("zone_link", parent=base["Normal"], fontName="Helvetica",
                                    fontSize=9, textColor=BLUE_700, leading=14),
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


def _append_zone_section(story: List[Any], s: Dict[str, ParagraphStyle], zd: Dict, tz: ZoneInfo) -> None:
    """Append a single zone's section to the story list (in place)."""
    name = zd.get("name", "—")
    lat = float(zd.get("lat", 0.0))
    lon = float(zd.get("lon", 0.0))
    radius_int = int(round(float(zd.get("radius_km", 20.0))))
    current = zd.get("current") or {}
    zones = zd.get("zones") or {}
    history = zd.get("history") or {}
    forecast = zd.get("forecast") or {}
    strikes = zd.get("strikes") or []

    story.append(Paragraph(name, s["zone_h"]))
    story.append(Paragraph(
        f"Rayon {radius_int} km · {lat:.4f}°N · {lon:.4f}°E",
        s["zone_sub"],
    ))

    # Status
    if bool(zones.get("storm_active")):
        story.append(Paragraph("⚠ ACTIVITÉ ORAGEUSE DÉTECTÉE", s["alert"]))
        story.append(Paragraph(
            f"CAPE max {_fmt(zones.get('max_cape'))} J/kg · LPI max {_fmt(zones.get('max_lightning_potential'), decimals=1)}.",
            s["body"],
        ))
    else:
        story.append(Paragraph("● CIEL CALME À MODÉRÉMENT INSTABLE", s["safe"]))
        story.append(Paragraph(
            f"Aucune activité orageuse dans un rayon de {radius_int} km au moment du bulletin.",
            s["body"],
        ))

    # Current conditions
    c = current.get("current", {})
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

    # 24h history
    hourly_hist = history.get("hourly", [])
    storm_hours = sum(1 for h in hourly_hist if h.get("is_storm"))
    total_precip = sum((h.get("precipitation") or 0) for h in hourly_hist)
    max_gust = max((h.get("wind_gust") or 0) for h in hourly_hist) if hourly_hist else 0
    story.append(Paragraph("HISTORIQUE 24 H", s["h2"]))
    story.append(Paragraph(
        f"Heures orageuses : <b>{storm_hours}</b> · Précipitations totales : <b>{total_precip:.1f} mm</b> · Rafale max : <b>{max_gust:.0f} km/h</b>",
        s["body"],
    ))

    # Forecast 12h
    hourly_fc = (forecast.get("hourly") or [])[:12]
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

    # Strikes
    story.append(Paragraph("IMPACTS FOUDRE · DERNIÈRE HEURE", s["h2"]))
    if strikes:
        rows = [["Heure locale", "Lat", "Lon", "Distance"]]
        for st in strikes[:20]:
            rows.append([
                _utc_to_local_str(st.get("ts") or st.get("iso", ""), tz, "%d/%m %H:%M:%S"),
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


def build_bulletin_pdf(zones_payload: List[Dict], tz_name: Optional[str] = None) -> bytes:
    """
    Build a (possibly multi-zone) storm bulletin PDF.

    zones_payload: list of dicts, each containing:
        - name: str
        - lat: float
        - lon: float
        - radius_km: float
        - current: dict (from fetch_current)
        - zones: dict (from fetch_storm_zones)
        - history: dict (from fetch_history_24h)
        - forecast: dict (from fetch_forecast)
        - strikes: List[dict]
    """
    if not zones_payload:
        raise ValueError("zones_payload must contain at least one zone")

    # Use the first zone's TZ as the reference (they're usually all in the same TZ for FR)
    tz = _resolve_tz(tz_name or (zones_payload[0].get("current") or {}).get("timezone"))
    s = _styles()
    story: List[Any] = []

    n = len(zones_payload)
    now_local = datetime.now(tz)
    names = [z.get("name", "—") for z in zones_payload]
    title_suffix = names[0] if n == 1 else f"{n} zones surveillées"

    # ---- Global header ----
    kicker = f"Bulletin orage · {title_suffix} · {now_local.strftime('%d %b %Y · %H:%M')} (heure locale)"
    story.append(Paragraph(kicker.upper(), s["kicker"]))
    story.append(Paragraph("Suivi d'orage en temps réel", s["h1"]))

    if n == 1:
        # Single zone: keep the layout compact, no cover page
        story.append(Paragraph(
            f"Rayon de surveillance : {int(round(float(zones_payload[0].get('radius_km', 20))))} km "
            f"autour de {zones_payload[0].get('name', '—')} "
            f"({float(zones_payload[0].get('lat', 0)):.4f}°N, {float(zones_payload[0].get('lon', 0)):.4f}°E).",
            s["body"],
        ))
        story.append(Spacer(1, 10))
        _append_zone_section(story, s, zones_payload[0], tz)
    else:
        # Multi-zone cover: list all monitored zones
        story.append(Paragraph(
            f"<b>{n}</b> zones surveillées simultanément. "
            f"Chaque zone fait l'objet d'une page détaillée ci-après.",
            s["body"],
        ))
        story.append(Spacer(1, 10))
        cover_rows = [["#", "Zone", "Rayon", "Coordonnées", "État"]]
        for i, z in enumerate(zones_payload, start=1):
            storm_flag = bool((z.get("zones") or {}).get("storm_active"))
            cover_rows.append([
                str(i),
                z.get("name", "—"),
                f"{int(round(float(z.get('radius_km', 20))))} km",
                f"{float(z.get('lat', 0)):.3f}, {float(z.get('lon', 0)):.3f}",
                "ORAGEUSE" if storm_flag else "calme",
            ])
        cover = Table(cover_rows, colWidths=[8 * mm, 60 * mm, 18 * mm, 45 * mm, 28 * mm])
        cover.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TEXTCOLOR", (0, 0), (-1, 0), SLATE_400),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("TEXTCOLOR", (0, 1), (-1, -1), SLATE_900),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, SLATE_200),
            ("LINEBELOW", (0, -1), (-1, -1), 0.5, SLATE_200),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BACKGROUND", (0, 0), (-1, 0), SLATE_50),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        # Colorize the "État" column row by row
        for i, z in enumerate(zones_payload, start=1):
            if bool((z.get("zones") or {}).get("storm_active")):
                cover.setStyle(TableStyle([("TEXTCOLOR", (4, i), (4, i), RED),
                                           ("FONTNAME", (4, i), (4, i), "Helvetica-Bold")]))
            else:
                cover.setStyle(TableStyle([("TEXTCOLOR", (4, i), (4, i), EMERALD)]))
        story.append(cover)

        # One section per zone, page-broken
        for idx, zd in enumerate(zones_payload):
            story.append(PageBreak())
            story.append(Paragraph(f"ZONE {idx + 1} / {n}", s["kicker"]))
            _append_zone_section(story, s, zd, tz)

    # Footer
    story.append(Spacer(1, 18))
    story.append(Paragraph(
        "Sources : Open-Meteo (météo) · Blitzortung.org (foudre). Bulletin informatif — non contractuel.",
        ParagraphStyle("footer", parent=s["body"], fontSize=7, textColor=SLATE_400, leading=10),
    ))

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"Bulletin orage — {title_suffix}",
        author=f"Suivi d'orage · {title_suffix}",
    )
    doc.build(story)
    return buf.getvalue()
