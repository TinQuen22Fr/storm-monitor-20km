"""Shareable PNG card for WhatsApp / Twitter / messaging.

Generates a 1200x630 (OG-image standard) snapshot of the current storm state
around Lourdes: vigilance color, strike count, closest strike, approach info,
trajectory. No fancy dependencies — pure Pillow.
"""
from __future__ import annotations

import io
import time
from typing import Any, Dict, Optional

from PIL import Image, ImageDraw, ImageFont

from weather import LOURDES_LAT, LOURDES_LON
import analysis as analysis_mod
import lightning as lightning_mod
import vigilance as vigilance_mod

W, H = 1200, 630
BG = (15, 23, 42)       # slate-900
FG = (255, 255, 255)
MUTED = (148, 163, 184) # slate-400

VIGILANCE_FILL = {
    1: (16, 185, 129),
    2: (245, 158, 11),
    3: (234, 88, 12),
    4: (220, 38, 38),
}


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Try to load a decent system font, fall back to default."""
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


async def render_share_card() -> bytes:
    # Fetch data
    try:
        vig = await vigilance_mod.compute_vigilance()
    except Exception:
        vig = None
    strikes = await lightning_mod.store.recent(LOURDES_LAT, LOURDES_LON, 70.0, since_ts=None)
    # last hour only
    now = time.time()
    strikes = [s for s in strikes if now - s["ts"] <= 3600]

    approach = analysis_mod.analyze_approach(LOURDES_LAT, LOURDES_LON, strikes)
    trajectory = analysis_mod.predict_trajectory(LOURDES_LAT, LOURDES_LON, strikes)

    # --- Build image ---
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # Vigilance stripe (left)
    vig_level = 1
    vig_label = "VERT"
    vig_phen = "Pas de vigilance"
    if vig:
        dept = next((x for x in vig["departements"] if x["id"] == "65"), None) or vig["departements"][0]
        vig_level = dept["max_level"]
        vig_label = dept["max_level_fr"].upper()
        worst = [p for p in dept["phenomena"] if p["level"] == vig_level]
        if worst:
            vig_phen = worst[0]["label"]
    d.rectangle((0, 0, 24, H), fill=VIGILANCE_FILL.get(vig_level, VIGILANCE_FILL[1]))

    # Header
    d.text((60, 44), "⚡ SUIVI D'ORAGE · LOURDES", font=_font(24, bold=True), fill=MUTED)
    d.text((60, 80), "Pyrénées · 43.0951°N / -0.0434°E", font=_font(18), fill=MUTED)

    # Vigilance badge
    dot_x, dot_y = 60, 146
    d.ellipse((dot_x, dot_y, dot_x + 20, dot_y + 20), fill=VIGILANCE_FILL.get(vig_level, VIGILANCE_FILL[1]))
    d.text((90, 140), f"VIGILANCE {vig_label}", font=_font(28, bold=True), fill=FG)
    d.text((90, 176), vig_phen, font=_font(20), fill=MUTED)
    d.text((90, 202), "Source : Météo-France (MeteoAlarm)", font=_font(14), fill=(100, 116, 139))

    # Divider
    d.line((60, 244, W - 60, 244), fill=(51, 65, 85), width=1)

    # Strikes stat (big left column)
    strike_count = len(strikes)
    count_color = FG if strike_count == 0 else (252, 211, 77) if strike_count < 10 else (248, 113, 113)
    d.text((60, 276), str(strike_count), font=_font(120, bold=True), fill=count_color)
    d.text((60, 420), "IMPACTS DE FOUDRE", font=_font(16, bold=True), fill=MUTED)
    d.text((60, 446), "Dernière heure · rayon 70 km", font=_font(14), fill=(100, 116, 139))

    # Closest strike / approach info (right column)
    rx = 540
    d.text((rx, 280), "ORAGE LE PLUS PROCHE", font=_font(14, bold=True), fill=MUTED)
    if strikes:
        closest = min(strikes, key=lambda s: s["distance_km"])
        d.text((rx, 306), f"{closest['distance_km']:.1f} km", font=_font(48, bold=True), fill=FG)
        # Time ago
        mins = int((now - closest["ts"]) / 60)
        ago = f"il y a {mins} min" if mins >= 1 else "il y a moins d'1 min"
        d.text((rx, 358), ago, font=_font(16), fill=MUTED)
    else:
        d.text((rx, 306), "Aucun", font=_font(48, bold=True), fill=(71, 85, 105))
        d.text((rx, 358), "Ciel calme", font=_font(16), fill=MUTED)

    # Approach / trajectory
    d.text((rx, 412), "APPROCHE / TRAJECTOIRE", font=_font(14, bold=True), fill=MUTED)
    if approach.get("approaching"):
        speed = approach.get("speed_kmh", 0)
        eta = approach.get("eta_min", 0)
        direction = approach.get("from_compass", "?")
        d.text((rx, 438), f"⚠ Depuis {direction} · {speed} km/h · ETA ~{int(eta)} min",
               font=_font(18, bold=True), fill=(248, 113, 113))
    elif trajectory.get("detected"):
        speed = trajectory.get("speed_kmh", 0)
        compass = trajectory.get("compass", "?")
        d.text((rx, 438), f"Cellule mobile · {speed} km/h vers {compass}",
               font=_font(18, bold=True), fill=(252, 211, 77))
    else:
        d.text((rx, 438), "Pas d'approche détectée", font=_font(18), fill=MUTED)

    # Footer
    footer_y = H - 60
    d.line((60, footer_y - 10, W - 60, footer_y - 10), fill=(51, 65, 85), width=1)
    ts = time.strftime("%d/%m/%Y · %H:%M", time.localtime(now))
    d.text((60, footer_y), f"Mis à jour {ts}", font=_font(14), fill=MUTED)
    d.text((W - 60 - 280, footer_y), "storm-monitor · Open-Meteo · Blitzortung",
           font=_font(12), fill=(100, 116, 139))

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
