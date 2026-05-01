import { useEffect, useMemo, useState } from "react";
import { MapContainer, GeoJSON, TileLayer } from "react-leaflet";
import { Info, Pin, X } from "lucide-react";
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

// Phenomenon filter — "all" shows the overall max level, any other key narrows to that phenomenon.
const PHENOMENA_FILTERS = [
  { key: "all", label: "Tous", icon: "●" },
  { key: "orage", label: "Orages", icon: "⚡" },
  { key: "vent", label: "Vent", icon: "🌬" },
  { key: "pluie", label: "Pluie-inondation", icon: "🌧" },
  { key: "canicule", label: "Canicule", icon: "🔥" },
  { key: "grand-froid", label: "Grand froid", icon: "❄" },
  { key: "neige", label: "Neige-verglas", icon: "🌨" },
  { key: "brouillard", label: "Brouillard", icon: "🌫" },
  { key: "avalanche", label: "Avalanches", icon: "🗻" },
];

export default function VigilancePage() {
  const [franceGeo, setFranceGeo] = useState(null);
  const [andorraGeo, setAndorraGeo] = useState(null);
  const [vig, setVig] = useState(null);
  const [hover, setHover] = useState(null); // ephemeral — follows the cursor
  const [selected, setSelected] = useState(null); // sticky — set on click
  const [filter, setFilter] = useState("all");

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

  // Pick the level used for coloring based on the current filter.
  // "all" → area.max_level ; otherwise → level of the selected phenomenon.
  const getDisplayLevel = (area) => {
    if (!area) return 1;
    if (filter === "all") return area.max_level;
    const phen = (area.phenomena || []).find((p) => p.key === filter);
    return phen?.level || 1;
  };

  // Index by id for O(1) lookups
  const phenBy = useMemo(() => {
    const m = {};
    if (vig) for (const a of vig.areas || []) m[a.id] = a;
    return m;
  }, [vig]);

  const levelBy = useMemo(() => {
    const m = {};
    if (vig) for (const a of vig.areas || []) m[a.id] = getDisplayLevel(a);
    return m;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vig, filter]);

  const styleFeatureFrance = (feature) => {
    const code = feature.properties.code;
    const lvl = levelBy[code] || 1;
    const base = LEVEL_STYLE[lvl];
    if (selected && selected.id === code) {
      return { ...base, weight: 3, color: "#0F172A", dashArray: null };
    }
    return base;
  };

  const styleFeatureAndorra = () => {
    const base = LEVEL_STYLE[levelBy["AD"] || 1];
    if (selected && selected.id === "AD") {
      return { ...base, weight: 3, color: "#0F172A" };
    }
    return base;
  };

  const onEachFranceDept = (feature, layer) => {
    const code = feature.properties.code;
    layer.on({
      click: (e) => {
        const a = phenBy[code];
        if (a) setSelected(a);
        // Prevent the map's own click handler from immediately clearing the selection
        if (e.originalEvent) e.originalEvent.stopPropagation?.();
      },
      mouseover: (e) => {
        const a = phenBy[code];
        if (a) setHover(a);
        e.target.setStyle({ weight: 2.5, color: "#0F172A" });
      },
      mouseout: (e) => {
        setHover(null);
        e.target.setStyle(styleFeatureFrance(feature));
      },
    });
    const lvl = levelBy[code] || 1;
    const filterName = filter === "all" ? "Vigilance" : `${PHENOMENA_FILTERS.find((p) => p.key === filter).label}`;
    layer.bindTooltip(
      `<div style="font-family:ui-monospace,Menlo,monospace;font-size:11px;line-height:1.4">
        <div style="font-weight:700;text-transform:uppercase;letter-spacing:0.08em">${feature.properties.nom} (${code})</div>
        <div style="margin-top:3px">${filterName} ${LEVEL_NAMES[lvl]}</div>
        <div style="margin-top:3px;color:#64748b">Cliquer pour épingler le détail</div>
      </div>`,
      { sticky: true, direction: "top" }
    );
  };

  const onEachAndorra = (feature, layer) => {
    const a = phenBy["AD"];
    const lvl = levelBy["AD"] || 1;
    layer.on({
      click: (e) => {
        if (a) setSelected(a);
        if (e.originalEvent) e.originalEvent.stopPropagation?.();
      },
      mouseover: (e) => {
        if (a) setHover(a);
        e.target.setStyle({ weight: 2.5, color: "#0F172A" });
      },
      mouseout: (e) => {
        setHover(null);
        e.target.setStyle(styleFeatureAndorra());
      },
    });
    const filterName = filter === "all" ? "Vigilance" : `${PHENOMENA_FILTERS.find((p) => p.key === filter).label}`;
    layer.bindTooltip(
      `<div style="font-family:ui-monospace,Menlo,monospace;font-size:11px;line-height:1.4">
        <div style="font-weight:700;text-transform:uppercase;letter-spacing:0.08em">Andorre (AD)</div>
        <div style="margin-top:3px">${filterName} ${LEVEL_NAMES[lvl]}</div>
        <div style="margin-top:3px;color:#64748b">Cliquer pour épingler le détail</div>
      </div>`,
      { sticky: true, direction: "top" }
    );
  };

  // Counts per level based on current filter
  const counts = { 1: 0, 2: 0, 3: 0, 4: 0 };
  if (vig) {
    for (const a of vig.areas || []) {
      const lvl = getDisplayLevel(a);
      counts[lvl] = (counts[lvl] || 0) + 1;
    }
  }

  // Per-filter availability counter (how many areas are >= yellow for that phenomenon)
  const availability = useMemo(() => {
    const out = {};
    if (!vig) return out;
    for (const p of PHENOMENA_FILTERS) {
      if (p.key === "all") {
        out.all = (vig.areas || []).filter((a) => a.max_level > 1).length;
      } else {
        out[p.key] = (vig.areas || []).filter((a) => {
          const ph = (a.phenomena || []).find((x) => x.key === p.key);
          return ph && ph.level > 1;
        }).length;
      }
    }
    return out;
  }, [vig]);

  const selectedInfo = filter === "all" ? null : PHENOMENA_FILTERS.find((p) => p.key === filter);

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
          {/* Phenomenon filter */}
          <div className="border border-slate-200 bg-white p-5" data-testid="vigilance-filter">
            <div className="font-mono text-[10px] uppercase tracking-[0.25em] text-slate-400 mb-3">
              Filtrer par phénomène
            </div>
            <div className="flex flex-wrap gap-1.5">
              {PHENOMENA_FILTERS.map((p) => {
                const active = filter === p.key;
                const count = availability[p.key] || 0;
                return (
                  <button
                    key={p.key}
                    type="button"
                    onClick={() => setFilter(p.key)}
                    className={`px-2.5 h-7 flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.12em] border transition-colors ${
                      active
                        ? "bg-slate-900 text-white border-slate-900"
                        : "bg-white text-slate-700 border-slate-200 hover:border-slate-900 hover:text-slate-900"
                    }`}
                    data-testid={`vigilance-filter-${p.key}`}
                    title={p.key === "all" ? "Niveau global (max)" : `Vigilance ${p.label.toLowerCase()} uniquement`}
                  >
                    <span aria-hidden>{p.icon}</span>
                    <span>{p.label}</span>
                    {count > 0 && (
                      <span
                        className={`ml-0.5 tabular-nums font-semibold ${
                          active ? "text-white/90" : "text-slate-400"
                        }`}
                      >
                        · {count}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
            {selectedInfo && (
              <div className="mt-3 font-mono text-[10px] text-slate-500 leading-relaxed">
                Affichage limité au phénomène «&nbsp;{selectedInfo.label.toLowerCase()}&nbsp;». Les autres alertes restent dans le panneau de détail.
              </div>
            )}
          </div>

          {/* Overall */}
          {vig && (
            <div className="border border-slate-200 bg-white p-5" data-testid="vigilance-overall">
              <div className="font-mono text-[10px] uppercase tracking-[0.25em] text-slate-400 mb-2">
                {filter === "all" ? "Niveau général" : `Niveau · ${selectedInfo.label}`}
              </div>
              {(() => {
                // When filter ≠ all, recompute overall = max level across areas for that phenomenon.
                let level = vig.overall_level;
                let color = vig.overall_color;
                let labelFr = vig.overall_level_fr;
                let label = vig.overall_label;
                if (filter !== "all") {
                  level = Math.max(1, ...Object.values(levelBy));
                  color = LEVEL_STYLE[level].fillColor;
                  labelFr = LEVEL_NAMES[level];
                  label = LEVEL_LABELS[level];
                }
                return (
                  <>
                    <div className="flex items-center gap-3 mb-2">
                      <span className="w-4 h-4 rounded-full" style={{ background: color }} />
                      <span
                        className="font-heading text-2xl font-black tracking-tight"
                        style={{ color }}
                      >
                        {labelFr.toUpperCase()}
                      </span>
                    </div>
                    <div className="text-sm text-slate-600">{label}</div>
                  </>
                );
              })()}
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

          {/* Selected area detail — click pins, hover previews when nothing pinned */}
          {(() => {
            // Priority: pinned selection > hovered area > default placeholder
            const area = selected || hover;
            const isPinned = !!selected;
            if (!area) {
              return (
                <div className="border border-slate-200 bg-white p-5 text-sm text-slate-500 flex items-start gap-3">
                  <Info className="w-4 h-4 shrink-0 mt-0.5" strokeWidth={1.8} />
                  <div>
                    Survolez un département pour un aperçu, puis <b>cliquez</b> pour épingler le détail.
                  </div>
                </div>
              );
            }
            return (
              <div
                className={`border bg-white p-5 transition-colors ${
                  isPinned
                    ? "border-slate-900 ring-1 ring-slate-900"
                    : "border-slate-200 border-dashed"
                }`}
                data-testid="vigilance-selected-area"
              >
                <div className="flex items-start justify-between gap-2 mb-2">
                  <div className="font-mono text-[10px] uppercase tracking-[0.25em] text-slate-400 flex items-center gap-2">
                    {isPinned && <Pin className="w-3 h-3 text-slate-900" strokeWidth={2.2} />}
                    <span>
                      {isPinned ? "Épinglé · " : "Aperçu · "}
                      {area.country === "AD" ? "Principauté" : "Département"}
                      {area.id !== "AD" ? ` (${area.id})` : ""}
                    </span>
                  </div>
                  {isPinned && (
                    <button
                      type="button"
                      onClick={() => setSelected(null)}
                      className="w-6 h-6 flex items-center justify-center border border-slate-200 hover:bg-slate-900 hover:text-white hover:border-slate-900 transition-colors"
                      data-testid="vigilance-unpin-btn"
                      aria-label="Désépingler"
                      title="Désépingler"
                    >
                      <X className="w-3 h-3" strokeWidth={2.4} />
                    </button>
                  )}
                </div>
                <div className="flex items-center gap-2 mb-3">
                  <span
                    className="w-3 h-3 rounded-full"
                    style={{ background: area.max_color }}
                  />
                  <h3 className="font-heading text-xl font-black tracking-tight text-slate-900">
                    {area.name}
                  </h3>
                </div>
                <div className="text-sm font-medium mb-3" style={{ color: area.max_color }}>
                  Vigilance {area.max_level_fr} · {area.max_label}
                </div>
                <div className="space-y-1.5">
                  {area.phenomena
                    .filter((p) => p.level > 1)
                    .map((p) => (
                      <div
                        key={p.key}
                        className={`flex items-center gap-2 text-[13px] ${
                          filter === p.key ? "ring-1 ring-slate-900 rounded-sm px-1 py-0.5 -mx-1" : ""
                        }`}
                      >
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
                  {area.phenomena.filter((p) => p.level > 1).length === 0 && (
                    <div className="text-sm text-slate-500 italic">
                      Aucune vigilance active
                    </div>
                  )}
                </div>
                {!isPinned && (
                  <div className="mt-3 pt-3 border-t border-slate-100 font-mono text-[10px] text-slate-400 leading-relaxed">
                    Cliquez sur le département pour épingler ce détail.
                  </div>
                )}
              </div>
            );
          })()}

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
                key={`fr-${vig.updated_at}-${filter}-${selected?.id || "none"}`}
                data={franceGeo}
                style={styleFeatureFrance}
                onEachFeature={onEachFranceDept}
              />
            )}
            {andorraGeo && vig && (
              <GeoJSON
                key={`ad-${vig.updated_at}-${filter}-${selected?.id || "none"}`}
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
