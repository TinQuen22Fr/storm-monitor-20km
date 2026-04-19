import { useEffect, useState } from "react";
import { GeoJSON, useMap } from "react-leaflet";
import { api } from "@/lib/api";

const LEVEL_STYLE = {
  1: { fillColor: "#10B981", fillOpacity: 0, color: "#10B981", weight: 0.5, opacity: 0.5 },
  2: { fillColor: "#F59E0B", fillOpacity: 0.22, color: "#D97706", weight: 1.5, opacity: 0.9 },
  3: { fillColor: "#EA580C", fillOpacity: 0.32, color: "#C2410C", weight: 2, opacity: 0.95 },
  4: { fillColor: "#DC2626", fillOpacity: 0.4, color: "#991B1B", weight: 2.5, opacity: 1 },
};

/**
 * Renders the 7 dept polygons (65, 64, 32, 31, 09, 66, 40) coloured according
 * to their vigilance level (source: MeteoAlarm). Polygons for level 1 (green)
 * are drawn transparent so they don't clutter.
 */
export default function VigilancePolygons({ enabled = true }) {
  const [geo, setGeo] = useState(null);
  const [vig, setVig] = useState(null);
  const map = useMap();

  useEffect(() => {
    if (!enabled) return;
    let cancel = false;
    fetch("/geo/lourdes-depts.geojson")
      .then((r) => r.json())
      .then((g) => !cancel && setGeo(g))
      .catch(() => { /* ignore */ });
    return () => { cancel = true; };
  }, [enabled]);

  useEffect(() => {
    if (!enabled) {
      setVig(null);
      return;
    }
    let cancel = false;
    const load = async () => {
      try {
        const { data } = await api.get("/weather/vigilance");
        if (!cancel) setVig(data);
      } catch { /* ignore */ }
    };
    load();
    const t = setInterval(load, 15 * 60_000);
    return () => { cancel = true; clearInterval(t); };
  }, [enabled]);

  useEffect(() => {
    if (!map.getPane("vigilancePane")) {
      map.createPane("vigilancePane");
      map.getPane("vigilancePane").style.zIndex = 395; // below overlayPane (400)
      map.getPane("vigilancePane").style.pointerEvents = "none";
    }
  }, [map]);

  if (!enabled || !geo || !vig) return null;

  const levelByCode = {};
  const phenByCode = {};
  for (const d of vig.departements || []) {
    levelByCode[d.id] = d.max_level;
    phenByCode[d.id] = d.phenomena
      .filter((p) => p.level > 1)
      .map((p) => `${p.label}: ${p.level_fr}`)
      .join(" · ") || "Pas de vigilance";
  }

  const styleFor = (feature) => {
    const code = feature.properties.code;
    const level = levelByCode[code] || 1;
    return LEVEL_STYLE[level] || LEVEL_STYLE[1];
  };

  const onEach = (feature, layer) => {
    const code = feature.properties.code;
    const name = feature.properties.nom;
    const level = levelByCode[code] || 1;
    const levelName = ["-", "vert", "jaune", "orange", "rouge"][level];
    const phens = phenByCode[code] || "";
    layer.bindTooltip(
      `<div style="font-family:ui-monospace,Menlo,monospace;font-size:11px;line-height:1.4">
        <div style="font-weight:700;text-transform:uppercase;letter-spacing:0.1em">
          ${name} (${code})
        </div>
        <div style="margin-top:4px">
          Vigilance ${levelName}
        </div>
        ${phens && level > 1 ? `<div style="margin-top:2px;color:#475569">${phens}</div>` : ""}
      </div>`,
      { sticky: true, direction: "top" }
    );
  };

  // Force re-render when vig updates by keying on vig timestamp
  return (
    <GeoJSON
      key={vig.updated_at}
      data={geo}
      style={styleFor}
      onEachFeature={onEach}
      pane="vigilancePane"
    />
  );
}
