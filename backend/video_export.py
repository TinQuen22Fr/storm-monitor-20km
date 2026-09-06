"""MP4 video export of a replay episode.

Renders each frame with Pillow (cached CARTO basemap tiles + strike markers +
HUD overlay) then assembles them with ffmpeg into an H.264 MP4 suitable for
WhatsApp / Twitter sharing.

Design notes
------------
- Frame cadence: 1 frame every 30s of event time = 2× real-time speed at 24 fps
  output (so a 45-min event → ~90 frames → ~4s video). Fast-paced, punchy.
- Basemap: CARTO light_all tiles cached locally forever (same tiles over and
  over — minimal network usage).
- Strikes fade from bright yellow/red (fresh) to dim grey (older). Radius
  circle + center pin always drawn. Bottom bar shows localized timestamp +
  strike count + episode label.
- Jobs run as asyncio tasks; progress exposed via in-memory dict.
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
import shutil
import subprocess
import time
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# ----- Paths -----
CACHE_ROOT = Path(os.environ.get("VIDEO_CACHE_DIR", "/tmp/storm_videos"))
TILES_DIR = CACHE_ROOT / "tiles"
OUTPUT_DIR = CACHE_ROOT / "output"
for p in (TILES_DIR, OUTPUT_DIR):
    p.mkdir(parents=True, exist_ok=True)

# Font discovery (DejaVu is installed via install.sh)
_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


# ----- Tile math (Slippy map tile names) -----
def _lonlat_to_tile(lon: float, lat: float, z: int) -> tuple[int, int]:
    lat_rad = math.radians(lat)
    n = 2 ** z
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


def _lonlat_to_pixel(lon: float, lat: float, z: int) -> tuple[float, float]:
    """World pixel coordinates (256 px tiles)."""
    lat_rad = math.radians(lat)
    n = 2 ** z
    x = (lon + 180.0) / 360.0 * n * 256.0
    y = (1.0 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2.0 * n * 256.0
    return x, y


# ----- Tile fetching / caching -----
TILE_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"
FALLBACK_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"


async def _fetch_tile(z: int, x: int, y: int) -> Optional[Image.Image]:
    """Fetch or load a single basemap tile. Cached forever on disk."""
    cache_file = TILES_DIR / f"{z}_{x}_{y}.png"
    if cache_file.exists():
        try:
            return Image.open(cache_file).convert("RGB")
        except Exception:
            cache_file.unlink(missing_ok=True)

    for url_tmpl in (TILE_URL, FALLBACK_TILE_URL):
        url = url_tmpl.format(z=z, x=x, y=y)
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as c:
                r = await c.get(url, headers={"User-Agent": "StormMonitoring/1.0 (demo)"})
                if r.status_code == 200:
                    img = Image.open(BytesIO(r.content)).convert("RGB")
                    img.save(cache_file, "PNG")
                    return img
        except Exception as e:
            logger.warning("Tile fetch failed %s: %s", url, e)
    return None


async def _build_basemap(
    center_lat: float,
    center_lon: float,
    radius_km: float,
    width: int,
    height: int,
    zoom: int = 9,
) -> tuple[Image.Image, callable]:
    """Build a basemap image covering the ROI + return a projector.

    projector(lat, lon) → (px, py) pixel coordinates on the returned image.
    """
    # Tile range derived from the PIXEL bbox of the final crop (± 1 tile margin)
    # so the composite always fully covers the frame — no black bands, center
    # guaranteed at the middle of the image.
    cx, cy = _lonlat_to_pixel(center_lon, center_lat, zoom)
    tx0 = int((cx - width / 2) // 256) - 1
    tx1 = int((cx + width / 2) // 256) + 1
    ty0 = int((cy - height / 2) // 256) - 1
    ty1 = int((cy + height / 2) // 256) + 1
    n_max = 2 ** zoom - 1
    tx0, ty0 = max(0, tx0), max(0, ty0)
    tx1, ty1 = min(n_max, tx1), min(n_max, ty1)

    # Assemble tiles
    tiles_w = tx1 - tx0 + 1
    tiles_h = ty1 - ty0 + 1
    composite_w = tiles_w * 256
    composite_h = tiles_h * 256
    composite = Image.new("RGB", (composite_w, composite_h), (226, 232, 240))

    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            tile = await _fetch_tile(zoom, tx, ty)
            if tile is not None:
                composite.paste(tile, ((tx - tx0) * 256, (ty - ty0) * 256))

    # Origin in world pixels
    origin_x = tx0 * 256
    origin_y = ty0 * 256

    # Project center in composite coords
    cx_comp = cx - origin_x
    cy_comp = cy - origin_y

    # Crop to desired (width, height) centered on center
    left = int(cx_comp - width / 2)
    top = int(cy_comp - height / 2)
    left = max(0, min(left, composite_w - width))
    top = max(0, min(top, composite_h - height))
    cropped = composite.crop((left, top, left + width, top + height))

    def project(lat: float, lon: float) -> tuple[float, float]:
        px_world, py_world = _lonlat_to_pixel(lon, lat, zoom)
        return px_world - origin_x - left, py_world - origin_y - top

    return cropped, project


# ----- Frame rendering -----
COLOR_BG_PANEL = (15, 23, 42)           # slate-900
COLOR_TEXT = (255, 255, 255)
COLOR_ACCENT = (253, 224, 71)           # yellow-300
COLOR_RADIUS = (15, 23, 42)
COLOR_STRIKE_FRESH = (220, 38, 38)       # red-600
COLOR_STRIKE_MID = (234, 88, 12)         # orange-600
COLOR_STRIKE_OLD = (148, 163, 184)       # slate-400


def _strike_color(age_s: float) -> tuple[int, int, int]:
    if age_s < 300:
        return COLOR_STRIKE_FRESH
    if age_s < 1200:
        return COLOR_STRIKE_MID
    return COLOR_STRIKE_OLD


def _render_frame(
    base: Image.Image,
    project,
    center_lat: float,
    center_lon: float,
    radius_km: float,
    strikes: List[Dict[str, Any]],
    frame_ts: float,
    event_label: str,
    strike_count_total: int,
    zoom: int,
) -> Image.Image:
    img = base.copy()
    draw = ImageDraw.Draw(img, "RGBA")
    w, h = img.size

    # Radius circle (dashed approximation via short arcs)
    cx, cy = project(center_lat, center_lon)
    # pixels per km at zoom z at this lat
    px_per_km = 256.0 * (2 ** zoom) / (40075.016 * math.cos(math.radians(center_lat)))
    r_px = radius_km * px_per_km
    draw.ellipse(
        [cx - r_px, cy - r_px, cx + r_px, cy + r_px],
        outline=COLOR_RADIUS + (255,),
        width=2,
    )
    # Soft fill on radius
    draw.ellipse(
        [cx - r_px, cy - r_px, cx + r_px, cy + r_px],
        fill=(15, 23, 42, 18),
    )

    # Strikes (only those <= frame_ts)
    shown = [s for s in strikes if s["ts"] <= frame_ts]
    for s in shown:
        sx, sy = project(float(s["lat"]), float(s["lon"]))
        if not (0 <= sx < w and 0 <= sy < h):
            continue
        age = frame_ts - s["ts"]
        color = _strike_color(age)
        # Fresh = big + ping
        if age < 60:
            draw.ellipse([sx - 10, sy - 10, sx + 10, sy + 10], fill=color + (40,))
            draw.ellipse([sx - 5, sy - 5, sx + 5, sy + 5], fill=color + (255,), outline=(255, 255, 255, 255), width=1)
        elif age < 600:
            draw.ellipse([sx - 4, sy - 4, sx + 4, sy + 4], fill=color + (220,), outline=(255, 255, 255, 160), width=1)
        else:
            draw.ellipse([sx - 3, sy - 3, sx + 3, sy + 3], fill=color + (160,))

    # Center pin
    draw.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill=(15, 23, 42, 255), outline=(255, 255, 255, 255), width=2)

    # Top label bar
    bar_h = 48
    draw.rectangle([0, 0, w, bar_h], fill=(15, 23, 42, 220))
    font_h1 = _load_font(16)
    font_small = _load_font(11)
    draw.text((16, 8), "STORM MONITORING · REPLAY", fill=COLOR_ACCENT, font=font_small)
    draw.text((16, 22), event_label[:80], fill=COLOR_TEXT, font=font_h1)

    # Bottom HUD
    hud_h = 64
    draw.rectangle([0, h - hud_h, w, h], fill=(15, 23, 42, 230))
    # Timestamp
    tm = time.localtime(frame_ts)
    ts_str = time.strftime("%a %d %b · %H:%M", tm)
    font_ts = _load_font(22)
    draw.text((16, h - hud_h + 12), ts_str, fill=COLOR_TEXT, font=font_ts)
    # Strike count
    count_str = f"{len(shown)} / {strike_count_total} impacts"
    font_cnt = _load_font(16)
    bbox = draw.textbbox((0, 0), count_str, font=font_cnt)
    cw = bbox[2] - bbox[0]
    draw.text((w - cw - 16, h - hud_h + 20), count_str, fill=COLOR_ACCENT, font=font_cnt)
    # Author credit (bottom-right tiny)
    author = "Build & Idea by Quentin Dumont"
    bbox = draw.textbbox((0, 0), author, font=font_small)
    aw = bbox[2] - bbox[0]
    draw.text((w - aw - 16, h - hud_h + 44), author, fill=(148, 163, 184, 255), font=font_small)

    return img


# ----- Job manager -----
# Simple in-memory dict. For single-process uvicorn this is enough.
_JOBS: Dict[str, Dict[str, Any]] = {}
_JOB_LOCK = asyncio.Lock()


def _now() -> float:
    return time.time()


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    j = _JOBS.get(job_id)
    if not j:
        return None
    # Don't leak internals like strikes list
    return {
        "job_id": j["job_id"],
        "status": j["status"],
        "progress": j.get("progress", 0),
        "created_at": j["created_at"],
        "finished_at": j.get("finished_at"),
        "label": j.get("label"),
        "mp4_path": str(j["mp4_path"]) if j.get("mp4_path") else None,
        "mp4_url": j.get("mp4_url"),
        "error": j.get("error"),
        "strike_count": j.get("strike_count"),
        "duration_s": j.get("duration_s"),
    }


async def start_job(
    strikes: List[Dict[str, Any]],
    start_ts: float,
    end_ts: float,
    center_lat: float,
    center_lon: float,
    radius_km: float,
    label: str,
    view_radius_km: float | None = None,
) -> str:
    job_id = f"vid-{uuid.uuid4().hex[:10]}"
    job: Dict[str, Any] = {
        "job_id": job_id,
        "status": "queued",
        "progress": 0,
        "created_at": _now(),
        "label": label,
        "mp4_path": None,
        "strike_count": len(strikes),
        "duration_s": end_ts - start_ts,
    }
    async with _JOB_LOCK:
        _JOBS[job_id] = job
    asyncio.create_task(
        _run_job(job_id, strikes, start_ts, end_ts, center_lat, center_lon, radius_km, label, view_radius_km)
    )
    return job_id


async def _run_job(
    job_id: str,
    strikes: List[Dict[str, Any]],
    start_ts: float,
    end_ts: float,
    center_lat: float,
    center_lon: float,
    radius_km: float,
    label: str,
    view_radius_km: float | None = None,
) -> None:
    job = _JOBS[job_id]
    job["status"] = "running"
    try:
        if not shutil.which("ffmpeg"):
            raise RuntimeError("ffmpeg not installed on this server — run install.sh to provision it")

        # radius_km = cercle de la zone surveillée ; view_radius_km = champ de vue
        # (>= rayon de détection pour que les impacts en périphérie restent visibles)
        view_radius = view_radius_km if view_radius_km is not None else max(radius_km, 70.0)
        width, height = 720, 720
        # Zoom auto : le plus grand zoom où le champ de vue tient dans le cadre
        zoom = 11
        while zoom > 7:
            ppk = 256.0 * (2 ** zoom) / (40075.016 * math.cos(math.radians(center_lat)))
            if 2 * view_radius * ppk * 1.15 <= min(width, height):
                break
            zoom -= 1
        duration = max(60.0, end_ts - start_ts)

        # 1 frame every 30 s event time
        step_s = 30.0
        n_frames = max(10, int(duration / step_s) + 1)
        fps = 24

        # Build basemap once
        base, project = await _build_basemap(center_lat, center_lon, view_radius, width, height, zoom)

        strikes_sorted = sorted(strikes, key=lambda s: s["ts"])
        frames_dir = OUTPUT_DIR / job_id
        frames_dir.mkdir(parents=True, exist_ok=True)

        for i in range(n_frames):
            frame_ts = start_ts + i * step_s
            img = _render_frame(
                base, project, center_lat, center_lon, radius_km,
                strikes_sorted, frame_ts, label, len(strikes_sorted), zoom,
            )
            img.save(frames_dir / f"f_{i:05d}.png", "PNG", optimize=False)
            job["progress"] = int((i + 1) / n_frames * 85)  # keep 15 % for ffmpeg
            await asyncio.sleep(0)  # yield

        # Hold last frame ~2s
        last_frame = frames_dir / f"f_{n_frames - 1:05d}.png"
        for k in range(fps * 2):
            shutil.copy(last_frame, frames_dir / f"f_{n_frames + k:05d}.png")

        # Assemble via ffmpeg
        out_mp4 = OUTPUT_DIR / f"{job_id}.mp4"
        cmd = [
            "ffmpeg", "-y", "-framerate", str(fps),
            "-i", str(frames_dir / "f_%05d.png"),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-preset", "fast", "-crf", "23",
            str(out_mp4),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {stderr.decode()[-300:]}")

        # Clean frames
        shutil.rmtree(frames_dir, ignore_errors=True)

        job["status"] = "done"
        job["progress"] = 100
        job["finished_at"] = _now()
        job["mp4_path"] = out_mp4
        job["mp4_url"] = f"/api/replay/video/{job_id}/file.mp4"
    except Exception as e:
        logger.exception("Video job %s failed", job_id)
        job["status"] = "failed"
        job["error"] = str(e)[:300]
        job["finished_at"] = _now()


def purge_old(max_age_h: int = 24) -> int:
    """Delete MP4s and job entries older than max_age_h."""
    cutoff = _now() - max_age_h * 3600
    removed = 0
    for job_id, j in list(_JOBS.items()):
        if j.get("finished_at") and j["finished_at"] < cutoff:
            if j.get("mp4_path"):
                try:
                    Path(j["mp4_path"]).unlink(missing_ok=True)
                except Exception:
                    pass
            _JOBS.pop(job_id, None)
            removed += 1
    return removed
