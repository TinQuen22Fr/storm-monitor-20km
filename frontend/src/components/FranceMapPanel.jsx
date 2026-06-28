import { useEffect, useMemo, useRef, useState } from "react";
import { MapContainer, Marker, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import { Loader2 } from "lucide-react";
import { getSevereGrid, listFavorites, LOURDES } from "@/lib/api";

// =========================================================================
// Color palettes per param (Windy.com-inspired smooth gradients).
// Each palette is a list of [stop_0_to_1, [r, g, b]].
// =========================================================================
const PALETTES = {
  // Temperature: blue (cold) → cyan → green → yellow → orange → red → purple
  t_thermal: [
    [0.00, [76, 0, 153]],     // -30°C
    [0.12, [37, 0, 178]],
    [0.22, [0, 80, 255]],
    [0.32, [0, 180, 255]],
    [0.42, [40, 230, 200]],
    [0.50, [80, 230, 60]],    // 0°C (mapped to ~50% by min/max scaling)
    [0.62, [230, 230, 60]],
    [0.72, [255, 180, 30]],
    [0.82, [255, 90, 30]],
    [0.92, [220, 30, 30]],
    [1.00, [120, 0, 60]],     // +40°C
  ],
  // Sequential heatmap for CAPE, Jet, Shear, Hail
  heat: [
    [0.00, [255, 255, 224]],
    [0.18, [255, 220, 110]],
    [0.40, [255, 150, 40]],
    [0.65, [220, 40, 40]],
    [0.85, [120, 0, 30]],
    [1.00, [40, 0, 20]],
  ],
  // Diverging for vertical velocity (negative = ascendance = red, positive = subsidence = blue)
  divergent: [
    [0.00, [10, 30, 120]],
    [0.25, [80, 140, 220]],
    [0.50, [245, 245, 245]],
    [0.75, [240, 130, 60]],
    [1.00, [150, 0, 30]],
  ],
  // Sequential for freezing level (low = orange = bas = grêle possible, high = blue = haut = pas de grêle)
  freezing: [
    [0.00, [240, 60, 30]],
    [0.30, [255, 165, 40]],
    [0.55, [255, 230, 130]],
    [0.80, [120, 200, 230]],
    [1.00, [30, 80, 200]],
  ],
};

const PARAMS = {
  t850: {
    label: "T° 850 hPa",
    palette: "t_thermal",
    unit: "°C",
    range: [-30, 40],      // fixed scale for readability (overrides min/max)
    decimals: 1,
    description: "Température à ~1500 m. Indicateur clé des masses d'air.",
  },
  t2m: {
    label: "T° 2 m",
    palette: "t_thermal",
    unit: "°C",
    range: [-15, 40],
    decimals: 1,
    description: "Température de l'air mesurée à 2 m du sol.",
  },
  soil_t: {
    label: "T° sol (0 cm)",
    palette: "t_thermal",
    unit: "°C",
    range: [-10, 45],
    decimals: 1,
    description: "Température à la surface du sol — sensibilité solaire.",
  },
  jet_speed: {
    label: "Jet 300 hPa",
    palette: "heat",
    unit: "km/h",
    valueScale: 3.6,        // m/s → km/h
    range: [0, 300],
    decimals: 0,
    description: "Vitesse du vent vers ~9 km. > 200 km/h = jet stream marqué.",
  },
  shear_0_6km: {
    label: "Cisaillement 0-6 km",
    palette: "heat",
    unit: "m/s",
    range: [0, 35],
    decimals: 1,
    description: "Cisaillement vertical surface ↔ 500 hPa. > 20 = structure orageuse possible.",
  },
  vv700: {
    label: "ω 700 hPa",
    palette: "divergent",
    unit: "Pa/s",
    range: [-0.8, 0.8],
    decimals: 2,
    description: "Vitesse verticale. Négatif = ascendance (orage), positif = subsidence.",
    invert: false,
  },
  hail_score: {
    label: "Risque grêle",
    palette: "heat",
    unit: "/100",
    range: [0, 100],
    decimals: 0,
    description: "Score composite empirique (CAPE × LI × shear × iso 0°C).",
  },
  cape: {
    label: "CAPE",
    palette: "heat",
    unit: "J/kg",
    range: [0, 3500],
    decimals: 0,
    description: "Énergie convective disponible. > 1500 = instabilité significative.",
  },
  freezing_level: {
    label: "Iso 0°C",
    palette: "freezing",
    unit: "m",
    range: [0, 5000],
    decimals: 0,
    description: "Altitude de l'isotherme 0°C. Bas = grêle peut atteindre le sol.",
  },
};

function lerpColor(c1, c2, t) {
  return [
    Math.round(c1[0] + (c2[0] - c1[0]) * t),
    Math.round(c1[1] + (c2[1] - c1[1]) * t),
    Math.round(c1[2] + (c2[2] - c1[2]) * t),
  ];
}

function paletteColor(palette, t) {
  t = Math.max(0, Math.min(1, t));
  for (let i = 0; i < palette.length - 1; i++) {
    if (t <= palette[i + 1][0]) {
      const span = palette[i + 1][0] - palette[i][0] || 1e-6;
      const local = (t - palette[i][0]) / span;
      return lerpColor(palette[i][1], palette[i + 1][1], local);
    }
  }
  return palette[palette.length - 1][1];
}

// IDW interpolation overlay using a canvas placed inside the leaflet map pane.
function IdwOverlay({ lats, lons, values, palette, range, param }) {
  const map = useMap();
  const canvasRef = useRef(null);

  useEffect(() => {
    if (!map) return;
    let canvas = canvasRef.current;
    if (!canvas) {
      canvas = document.createElement("canvas");
      canvas.style.position = "absolute";
      canvas.style.left = "0";
      canvas.style.top = "0";
      canvas.style.pointerEvents = "none";
      canvas.style.zIndex = "200";
      canvas.style.opacity = "0.72";
      const pane = map.getPanes().overlayPane;
      pane.appendChild(canvas);
      canvasRef.current = canvas;
    }

    function render() {
      const size = map.getSize();
      canvas.width = size.x;
      canvas.height = size.y;

      // Anchor the canvas to the top-left of the map pixel origin
      const origin = map.containerPointToLayerPoint([0, 0]);
      L.DomUtil.setPosition(canvas, origin);

      const ctx = canvas.getContext("2d");
      ctx.clearRect(0, 0, size.x, size.y);
      if (!lats?.length || !values?.length) return;

      // Convert all grid points to pixel coords once
      const points = [];
      for (let i = 0; i < lats.length; i++) {
        const v = values[i];
        if (v == null) continue;
        const p = map.latLngToContainerPoint([lats[i], lons[i]]);
        points.push({ x: p.x, y: p.y, v });
      }
      if (points.length === 0) return;

      const [vmin, vmax] = range;
      const span = vmax - vmin || 1e-6;
      const CELL = 6; // px — IDW per cell for performance
      const POWER = 2.5;
      const img = ctx.createImageData(size.x, size.y);
      const data = img.data;

      for (let py = 0; py < size.y; py += CELL) {
        for (let px = 0; px < size.x; px += CELL) {
          // Compute IDW from the 6 closest grid points
          let nearest = points
            .map((pt) => ({ d2: (pt.x - px) ** 2 + (pt.y - py) ** 2, v: pt.v }))
            .sort((a, b) => a.d2 - b.d2)
            .slice(0, 6);
          let num = 0;
          let den = 0;
          for (const { d2, v } of nearest) {
            if (d2 < 1) {
              num = v;
              den = 1;
              break;
            }
            const w = 1 / Math.pow(d2, POWER / 2);
            num += w * v;
            den += w;
          }
          const val = num / den;
          const t = (val - vmin) / span;
          const [r, g, b] = paletteColor(palette, t);

          for (let yy = 0; yy < CELL && py + yy < size.y; yy++) {
            for (let xx = 0; xx < CELL && px + xx < size.x; xx++) {
              const idx = ((py + yy) * size.x + (px + xx)) * 4;
              data[idx] = r;
              data[idx + 1] = g;
              data[idx + 2] = b;
              data[idx + 3] = 235;
            }
          }
        }
      }
      ctx.putImageData(img, 0, 0);
    }

    render();
    map.on("move zoom resize viewreset", render);
    return () => {
      map.off("move zoom resize viewreset", render);
      if (canvas?.parentNode) canvas.parentNode.removeChild(canvas);
      canvasRef.current = null;
    };
  }, [map, lats, lons, values, palette, range[0], range[1], param]); // eslint-disable-line react-hooks/exhaustive-deps

  return null;
}

// Legend showing the gradient + min/max
function Legend({ paletteKey, range, unit, decimals }) {
  const stops = PALETTES[paletteKey];
  const bg = `linear-gradient(to right, ${stops
    .map(([s, [r, g, b]]) => `rgb(${r},${g},${b}) ${(s * 100).toFixed(0)}%`)
    .join(", ")})`;
  const ticks = 5;
  const tickVals = Array.from({ length: ticks }, (_, i) =>
    (range[0] + ((range[1] - range[0]) * i) / (ticks - 1)).toFixed(decimals)
  );
  return (
    <div className="mt-2">
      <div className="h-3 w-full border border-slate-300" style={{ background: bg }} />
      <div className="flex justify-between font-mono text-[9px] text-slate-500 mt-1 tabular-nums">
        {tickVals.map((v, i) => (
          <span key={i}>
            {v}
            {i === ticks - 1 ? ` ${unit}` : ""}
          </span>
        ))}
      </div>
    </div>
  );
}

// Helper: get the value at (lat, lon) by IDW from the grid points
function valueAt(lat, lon, lats, lons, values) {
  if (!Array.isArray(lats) || !Array.isArray(lons) || !Array.isArray(values)) return null;
  if (lats.length === 0) return null;
  let num = 0;
  let den = 0;
  const POWER = 2.5;
  for (let i = 0; i < lats.length; i++) {
    if (values[i] == null) continue;
    const d2 = (lats[i] - lat) ** 2 + (lons[i] - lon) ** 2;
    if (d2 < 1e-8) return values[i];
    const w = 1 / Math.pow(d2, POWER / 2);
    num += w * values[i];
    den += w;
  }
  return den > 0 ? num / den : null;
}

export default function FranceMapPanel({ favorites = [] }) {
  const [param, setParam] = useState("t850");
  const [hour, setHour] = useState(0);
  const [grid, setGrid] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const cfg = PARAMS[param];

  useEffect(() => {
    let cancel = false;
    setLoading(true);
    setError(null);
    getSevereGrid(param, hour)
      .then((d) => {
        if (cancel) return;
        // Apply value scaling if needed (e.g. m/s → km/h for jet)
        if (cfg.valueScale && d.values) {
          d.values = d.values.map((v) => (v == null ? null : v * cfg.valueScale));
        }
        setGrid(d);
      })
      .catch((e) => {
        if (!cancel) {
          const s = e?.response?.status;
          setError(s === 404 ? "Endpoint absent (404)" : "Erreur de chargement");
        }
      })
      .finally(() => !cancel && setLoading(false));
    return () => { cancel = true; };
  }, [param, hour]); // eslint-disable-line react-hooks/exhaustive-deps

  const displayedTime = useMemo(() => {
    if (!grid?.time) return "—";
    try {
      const d = new Date(grid.time + "Z");
      return d.toLocaleString("fr-FR", {
        weekday: "short", day: "2-digit", month: "short",
        hour: "2-digit", minute: "2-digit",
      });
    } catch {
      return grid.time;
    }
  }, [grid]);

  return (
    <div className="border border-slate-200 bg-white" data-testid="france-map-panel">
      <div className="p-5 border-b border-slate-100">
        <div className="flex flex-wrap items-end justify-between gap-3 mb-3">
          <div>
            <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400">
              Carte France · {cfg.label}
            </div>
            <div className="font-heading text-xl font-bold text-slate-900 leading-tight">
              {cfg.label}
              <span className="font-mono text-xs font-normal text-slate-500 ml-2">
                {cfg.unit}
              </span>
            </div>
            <p className="text-[11px] text-slate-500 mt-1 max-w-md">{cfg.description}</p>
          </div>
          <div className="text-right">
            <div className="font-mono text-[10px] text-slate-400 uppercase tracking-[0.15em]">
              Échéance · UTC
            </div>
            <div className="font-mono text-xs text-slate-700 tabular-nums">
              {displayedTime}
            </div>
            <div className="font-mono text-[10px] text-slate-400 mt-0.5">
              H+{hour}
            </div>
          </div>
        </div>

        {/* Param selector */}
        <div className="flex flex-wrap gap-1.5 mb-3" data-testid="map-param-selector">
          {Object.entries(PARAMS).map(([k, v]) => (
            <button
              key={k}
              onClick={() => setParam(k)}
              className={`px-2.5 h-7 border font-mono text-[10px] uppercase tracking-[0.1em] transition-colors ${
                k === param
                  ? "bg-slate-900 text-white border-slate-900"
                  : "bg-white text-slate-700 border-slate-300 hover:border-slate-500"
              }`}
              data-testid={`map-param-${k}`}
            >
              {v.label}
            </button>
          ))}
        </div>

        {/* Time slider */}
        <div className="flex items-center gap-3">
          <span className="font-mono text-[10px] text-slate-500 shrink-0">H+0</span>
          <input
            type="range"
            min={0}
            max={47}
            value={hour}
            onChange={(e) => setHour(parseInt(e.target.value))}
            className="flex-1 accent-slate-900"
            data-testid="map-hour-slider"
          />
          <span className="font-mono text-[10px] text-slate-500 shrink-0">H+47</span>
          <span className="font-mono text-xs text-slate-900 w-12 text-right tabular-nums">
            H+{hour}
          </span>
        </div>
      </div>

      {/* Map */}
      <div className="relative" style={{ height: 520 }}>
        <MapContainer
          center={[46.7, 2.5]}
          zoom={5}
          minZoom={4}
          maxZoom={9}
          scrollWheelZoom
          style={{ height: "100%", width: "100%", background: "#F1F5F9" }}
        >
          <TileLayer
            attribution="&copy; CARTO &copy; OpenStreetMap"
            url="https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png"
          />
          {grid && Array.isArray(grid.lats) && grid.lats.length > 0 && (
            <IdwOverlay
              lats={grid.lats}
              lons={grid.lons}
              values={grid.values}
              palette={PALETTES[cfg.palette]}
              range={cfg.range}
              param={param}
            />
          )}
          <TileLayer
            url="https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png"
            zIndex={500}
            opacity={0.85}
          />
          {/* Favorite markers with exact interpolated value */}
          {grid && Array.isArray(grid.lats) && grid.lats.length > 0 &&
            favorites.map((f) => {
              const v = valueAt(f.lat, f.lon, grid.lats, grid.lons, grid.values);
              return (
                <Marker
                  key={`fav-${f.id}`}
                  position={[f.lat, f.lon]}
                  icon={L.divIcon({
                    className: "",
                    html: `<div style="display:flex;align-items:center;gap:6px;transform:translateX(8px)">
                      <span style="width:10px;height:10px;border-radius:9999px;background:#0F172A;border:2px solid #fff;box-shadow:0 0 0 1px #0F172A"></span>
                      <span style="font:600 10px/1 ui-monospace,Menlo,monospace;background:rgba(255,255,255,.95);border:1px solid #CBD5E1;color:#0F172A;padding:3px 6px;white-space:nowrap;box-shadow:0 1px 4px rgba(0,0,0,.1)">${(f.name || "").replace(/[<>&"']/g, "")} · ${
                      v == null ? "—" : v.toFixed(cfg.decimals)
                    } ${cfg.unit}</span>
                    </div>`,
                    iconSize: [10, 10],
                    iconAnchor: [5, 5],
                  })}
                />
              );
            })}
        </MapContainer>

        {loading && (
          <div className="absolute top-3 right-3 z-[500] bg-white/95 border border-slate-200 px-2 py-1 font-mono text-[10px] text-slate-600 flex items-center gap-2">
            <Loader2 className="w-3 h-3 animate-spin" />
            Chargement…
          </div>
        )}
        {error && (
          <div className="absolute top-3 right-3 z-[500] bg-red-50 border border-red-200 px-2 py-1 font-mono text-[10px] text-red-700">
            {error}
          </div>
        )}
        {!loading && !error && grid && (!Array.isArray(grid.lats) || grid.lats.length === 0) && (
          <div className="absolute top-3 right-3 z-[500] bg-amber-50 border border-amber-200 px-2 py-1 font-mono text-[10px] text-amber-800">
            Données indisponibles pour ce paramètre/échéance
          </div>
        )}
      </div>

      {/* Legend */}
      <div className="p-4 border-t border-slate-100">
        <Legend
          paletteKey={cfg.palette}
          range={cfg.range}
          unit={cfg.unit}
          decimals={cfg.decimals}
        />
      </div>
    </div>
  );
}
