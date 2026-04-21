import { useEffect, useState } from "react";
import { MapContainer, GeoJSON, TileLayer } from "react-leaflet";
import { AlertTriangle, Info } from "lucide-react";
import NavTabs from "@/components/NavTabs";
import { api } from "@/lib/api";

const LEVEL_STYLE = {
  1: { fillColor: "#10B981", fillOpacity: 0.05, color: "#94A3B8", weight: 0.6 },
  2: { fillColor: "#F59E0B", fillOpacity: 0.55, color: "#D97706", weight: 1 },
  3: { fillColor: "#EA580C", fillOpacity: 0.65, color: "#C2410C", weight: 1.4 },
  4: { fillColor: "#DC2626", fillOpacity: 0.72, color: "#991B1B", weight: 1.8 },
};

const LEVEL_NAMES = { 1: "vert", 2: "jaune", 3: "orange", 4: "rouge" };
const LEVEL_LABELS = {
  1: "Pas de vigilance particulière",
  2: "Soyez attentif",
  3: "Soyez très vigilant",
  4: "Vigilance absolue",
};

export default function VigilancePage() {
  const [franceGeo, setFranceGeo] = useState(null);
  const [andorraGeo, setAndorraGeo] = useState(null);
  const [vig, setVig] = useState(null);
  const [hover, setHover] = useState(null);

  useEffect(() => {
    fetch("/geo/france-depts.geojson").then((r) => r.json()).then(setFranceGeo).catch(() => {});
    fetch("/geo/andorra.geojson").then((r) => r.json()).then(setAndorraGeo).catch(() => {});
  }, []);

  useEffect(() => {
    let cancel = false;
    const load = async () => {
      try {
        const { data } = await api.get("/weather/vigilance/full");
        if (!cancel) setVig(data);
      } catch { /* ignore */ }
    };
    load();
    const t = setInterval(load, 15 * 60_000);
    return () => { cancel = true; clearInterval(t); };
  }, []);

  const levelBy = {};
  const phenBy = {};
  if (vig) {
    for (const a of vig.areas || []) {
      levelBy[a.id] = a.max_level;
      phenBy[a.id] = a;
    }
  }

  const styleFeatureFrance = (feature) => {
    const code = feature.properties.code;
    const lvl = levelBy[code] || 1;
    return LEVEL_STYLE[lvl];
  };

  const styleFeatureAndorra = () => {
    const lvl = levelBy["AD"] || 1;
    return LEVEL_STYLE[lvl];
  };

  const onEachFranceDept = (feature, layer) => {
    const code = feature.properties.code;
    layer.on({
      click: () => {
        const a = phenBy[code];
        if (a) setHover(a);
      },
      mouseover: (e) => {
        const a = phenBy[code];
        if (a) setHover(a);
        e.target.setStyle({ weight: 2.5, color: "#0F172A" });
      },
      mouseout: (e) => {
        e.target.setStyle(styleFeatureFrance(feature));
      },
    });
    const a = phenBy[code];
    const level = a?.max_level || 1;
    layer.bindTooltip(
      `<div style="font-family:ui-monospace,Menlo,monospace;font-size:11px;line-height:1.4">
        <div style="font-weight:700;text-transform:uppercase;letter-spacing:0.08em">${feature.properties.nom} (${code})</div>
        <div style="margin-top:3px">Vigilance ${LEVEL_NAMES[level]}</div>
      </div>`,
      { sticky: true, direction: "top" }
    );
  };

  const onEachAndorra = (feature, layer) => {
    const a = phenBy["AD"];
    const level = a?.max_level || 1;
    layer.on({
      click: () => { if (a) setHover(a); },
      mouseover: (e) => {
        if (a) setHover(a);
        e.target.setStyle({ weight: 2.5, color: "#0F172A" });
      },
      mouseout: (e) => {
        e.target.setStyle(styleFeatureAndorra());
      },
    });
    layer.bindTooltip(
      `<div style="font-family:ui-monospace,Menlo,monospace;font-size:11px;line-height:1.4">
        <div style="font-weight:700;text-transform:uppercase;letter-spacing:0.08em">Andorre (AD)</div>
        <div style="margin-top:3px">Vigilance ${LEVEL_NAMES[level]}</div>
      </div>`,
      { sticky: true, direction: "top" }
    );
  };

  // Counts per level
  const counts = { 1: 0, 2: 0, 3: 0, 4: 0 };
  if (vig) {
    for (const a of vig.areas || []) counts[a.max_level] = (counts[a.max_level] || 0) + 1;
  }

  return (
    <div className="min-h-screen bg-slate-50" data-testid="vigilance-page">
      <div className="border-b border-slate-200 bg-white">
        <div className="max-w-[1800px] mx-auto px-6 py-4 flex flex-col md:flex-row md:items-center gap-4">
          <div className="flex-1">
            <div className="font-mono text-[10px] uppercase tracking-[0.25em] text-slate-400">
              Vigilance officielle · MeteoAlarm
            </div>
            <h1 className="font-heading text-2xl font-black tracking-tight text-slate-900">
              Carte de vigilance · France + Andorre
            </h1>
          </div>
          <div className="w-full md:w-96 shrink-0">
            <NavTabs />
          </div>
        </div>
      </div>

      <div className="max-w-[1800px] mx-auto px-6 py-6 grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Left panel */}
        <aside className="lg:col-span-1 flex flex-col gap-4">
          {/* Overall */}
          {vig && (
            <div className="border border-slate-200 bg-white p-5" data-testid="vigilance-overall">
              <div className="font-mono text-[10px] uppercase tracking-[0.25em] text-slate-400 mb-2">
                Niveau général
              </div>
              <div className="flex items-center gap-3 mb-2">
                <span
                  className="w-4 h-4 rounded-full"
                  style={{ background: vig.overall_color }}
                />
                <span className="font-heading text-2xl font-black tracking-tight" style={{ color: vig.overall_color }}>
                  {vig.overall_level_fr.toUpperCase()}
                </span>
              </div>
              <div className="text-sm text-slate-600">{vig.overall_label}</div>
            </div>
          )}

          {/* Legend */}
          <div className="border border-slate-200 bg-white p-5">
            <div className="font-mono text-[10px] uppercase tracking-[0.25em] text-slate-400 mb-3">
              Légende
            </div>
            <div className="space-y-2">
              {[4, 3, 2, 1].map((lv) => (
                <div key={lv} className="flex items-center gap-3 text-sm" data-testid={`legend-${lv}`}>
                  <span
                    className="w-3 h-3 rounded-sm"
                    style={{ background: LEVEL_STYLE[lv].fillColor, opacity: lv === 1 ? 0.4 : 1 }}
                  />
                  <span className="font-medium capitalize text-slate-700 w-16">{LEVEL_NAMES[lv]}</span>
                  <span className="text-slate-500 flex-1">{LEVEL_LABELS[lv]}</span>
                  <span className="font-mono text-xs text-slate-400 tabular-nums">{counts[lv]}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Selected area detail */}
          {hover ? (
            <div
              className="border border-slate-200 bg-white p-5"
              data-testid="vigilance-selected-area"
            >
              <div className="font-mono text-[10px] uppercase tracking-[0.25em] text-slate-400 mb-2">
                {hover.country === "AD" ? "Principauté" : "Département"} {hover.id !== "AD" ? `(${hover.id})` : ""}
              </div>
              <div className="flex items-center gap-2 mb-3">
                <span
                  className="w-3 h-3 rounded-full"
                  style={{ background: hover.max_color }}
                />
                <h3 className="font-heading text-xl font-black tracking-tight text-slate-900">
                  {hover.name}
                </h3>
              </div>
              <div className="text-sm font-medium mb-3" style={{ color: hover.max_color }}>
                Vigilance {hover.max_level_fr} · {hover.max_label}
              </div>
              <div className="space-y-1.5">
                {hover.phenomena
                  .filter((p) => p.level > 1)
                  .map((p) => (
                    <div key={p.key} className="flex items-center gap-2 text-[13px]">
                      <span
                        className="w-2 h-2 rounded-full"
                        style={{ background: p.color }}
                      />
                      <span className="text-slate-700 flex-1">{p.label}</span>
                      <span className="font-mono text-xs capitalize" style={{ color: p.color }}>
                        {p.level_fr}
                      </span>
                    </div>
                  ))}
                {hover.phenomena.filter((p) => p.level > 1).length === 0 && (
                  <div className="text-sm text-slate-500 italic">
                    Aucune vigilance active
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="border border-slate-200 bg-white p-5 text-sm text-slate-500 flex items-start gap-3">
              <Info className="w-4 h-4 shrink-0 mt-0.5" strokeWidth={1.8} />
              <div>Survolez ou cliquez sur un département pour afficher le détail des vigilances.</div>
            </div>
          )}

          {/* Source */}
          {vig && (
            <div className="text-[10px] font-mono text-slate-400 leading-relaxed">
              {vig.source_label}
              {vig.updated_at && (
                <div className="mt-1">
                  Mis à jour · {new Date(vig.updated_at * 1000).toLocaleString("fr-FR")}
                </div>
              )}
            </div>
          )}
        </aside>

        {/* Map */}
        <main className="lg:col-span-3 h-[75vh] border border-slate-200 bg-white relative" data-testid="vigilance-map-container">
          <MapContainer
            center={[46.5, 2.0]}
            zoom={6}
            minZoom={5}
            maxZoom={9}
            scrollWheelZoom
            style={{ height: "100%", width: "100%", background: "#F8FAFC" }}
          >
            <TileLayer
              url="https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png"
              attribution='&copy; CARTO &copy; OSM'
              maxZoom={19}
            />
            <TileLayer
              url="https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png"
              attribution=''
              maxZoom={19}
              pane="tooltipPane"
            />
            {franceGeo && vig && (
              <GeoJSON
                key={`fr-${vig.updated_at}`}
                data={franceGeo}
                style={styleFeatureFrance}
                onEachFeature={onEachFranceDept}
              />
            )}
            {andorraGeo && vig && (
              <GeoJSON
                key={`ad-${vig.updated_at}`}
                data={andorraGeo}
                style={styleFeatureAndorra}
                onEachFeature={onEachAndorra}
              />
            )}
          </MapContainer>
        </main>
      </div>
    </div>
  );
}
