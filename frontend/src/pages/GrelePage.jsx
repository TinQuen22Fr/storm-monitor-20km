import { useCallback, useEffect, useMemo, useState } from "react";
import { Circle, MapContainer, Marker, TileLayer } from "react-leaflet";
import L from "leaflet";
import { LineChart, Line, Tooltip, ResponsiveContainer, XAxis, YAxis, CartesianGrid, ReferenceLine, AreaChart, Area } from "recharts";
import { AlertTriangle, CloudHail, Loader2, MapPin, RefreshCw, Sun, Moon, Globe, Zap, ZapOff } from "lucide-react";
import NavTabs from "@/components/NavTabs";
import { useAuth } from "@/lib/auth";
import { getSevere, listFavorites, LOURDES } from "@/lib/api";
import { setLocalTimezone, fmtLocalTime } from "@/lib/timeFormat";

const HAIL_COLORS = {
  nul: "#10B981",
  faible: "#22C55E",
  modéré: "#F59E0B",
  fort: "#EF4444",
  extrême: "#7F1D1D",
};

function buildLabelIcon(name, color) {
  const safe = (name || "").replace(/[<>&"']/g, "");
  return L.divIcon({
    className: "",
    html: `<div style="display:flex;align-items:center;gap:6px;transform:translateX(8px)">
      <span style="width:10px;height:10px;border-radius:9999px;background:${color};border:2px solid #fff;box-shadow:0 0 0 1px ${color}"></span>
      <span style="font:600 10px/1 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.04em;background:rgba(255,255,255,.95);border:1px solid #E2E8F0;color:#0F172A;padding:3px 6px;white-space:nowrap;box-shadow:0 1px 4px rgba(0,0,0,.06)">${safe}</span>
    </div>`,
    iconSize: [10, 10],
    iconAnchor: [5, 5],
  });
}

function loadVisibility() {
  try {
    const raw = localStorage.getItem("storm.favVisibility");
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function HailScale() {
  const levels = [
    { label: "nul", range: "0-14" },
    { label: "faible", range: "15-29" },
    { label: "modéré", range: "30-49" },
    { label: "fort", range: "50-69" },
    { label: "extrême", range: "70-100" },
  ];
  return (
    <div className="flex flex-wrap items-center gap-2 text-[10px] font-mono" data-testid="hail-scale">
      {levels.map((l) => (
        <div key={l.label} className="flex items-center gap-1.5">
          <span className="w-3 h-3" style={{ background: HAIL_COLORS[l.label] }} />
          <span className="uppercase tracking-[0.15em] text-slate-600">{l.label}</span>
          <span className="text-slate-400 tabular-nums">{l.range}</span>
        </div>
      ))}
    </div>
  );
}

// Fonds de carte Esri (gratuits, sans clé API) — identique à MapPanel.jsx
const BASEMAPS = {
  clair: {
    base: "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
    labels: "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}",
    maxNative: 16,
    attribution: 'Tiles &copy; <a href="https://www.esri.com/">Esri</a> &mdash; Esri, HERE, Garmin &copy; OpenStreetMap contributors',
  },
  sombre: {
    base: "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
    labels: "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}",
    maxNative: 16,
    attribution: 'Tiles &copy; <a href="https://www.esri.com/">Esri</a> &mdash; Esri, HERE, Garmin &copy; OpenStreetMap contributors',
  },
  satellite: {
    base: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    labels: "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
    maxNative: 19,
    attribution: 'Tiles &copy; <a href="https://www.esri.com/">Esri</a> &mdash; Source: Esri, Maxar, Earthstar Geographics',
  },
};

export default function GrelePage() {
  const { user } = useAuth();
  const [favs, setFavs] = useState([]);
  const [severeByZone, setSevereByZone] = useState({}); // {id: severeData}
  const [activeId, setActiveId] = useState("default");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [basemap, setBasemap] = useState(() => {
    try { return localStorage.getItem("storm_basemap") || "clair"; } catch { return "clair"; }
  });
  const bm = BASEMAPS[basemap] || BASEMAPS.clair;
  const changeBasemap = (k) => {
    setBasemap(k);
    try { localStorage.setItem("storm_basemap", k); } catch {}
  };

  // Build the list of zones to monitor (favs cochés OR Lourdes fallback)
  const zones = useMemo(() => {
    if (!user || favs.length === 0) {
      return [{ id: "default", name: "Lourdes", lat: LOURDES.lat, lon: LOURDES.lon }];
    }
    const vis = loadVisibility();
    const visible = favs.filter((f) => vis[f.id] !== false);
    if (visible.length === 0) {
      // user has unticked everything → fall back to Lourdes so the page still works
      return [{ id: "default", name: "Lourdes", lat: LOURDES.lat, lon: LOURDES.lon }];
    }
    return visible.map((f) => ({ id: f.id, name: f.name, lat: f.lat, lon: f.lon }));
  }, [user, favs]);

  // Load favorites once the user is known
  useEffect(() => {
    if (!user) return;
    let cancel = false;
    (async () => {
      try {
        const d = await listFavorites();
        if (!cancel) setFavs(d || []);
      } catch { /* ignore */ }
    })();
    return () => { cancel = true; };
  }, [user]);

  // Pick the first zone as active when zones change
  useEffect(() => {
    if (zones.length === 0) return;
    if (!zones.find((z) => z.id === activeId)) {
      setActiveId(zones[0].id);
    }
  }, [zones, activeId]);

  // Fetch severe for every zone (in parallel). Refresh every 30s so the
  // realtime overlay and the 1h history populate at a useful pace.
  const loadAll = useCallback(async () => {
    if (zones.length === 0) return;
    setLoading(true);
    setError(null);
    try {
      const results = await Promise.allSettled(
        zones.map((z) => getSevere(z.lat, z.lon, 24, 20).then((d) => ({ id: z.id, data: d })))
      );
      const next = {};
      for (const r of results) {
        if (r.status === "fulfilled") next[r.value.id] = r.value.data;
      }
      setSevereByZone(next);
      const first = Object.values(next)[0];
      if (first?.timezone) setLocalTimezone(first.timezone);
    } catch (e) {
      setError("Erreur lors du chargement des prévisions grêle");
    } finally {
      setLoading(false);
    }
  }, [zones]);

  useEffect(() => {
    loadAll();
    const t = setInterval(loadAll, 30_000);
    return () => clearInterval(t);
  }, [loadAll]);

  const activeZone = zones.find((z) => z.id === activeId) || zones[0];
  const activeData = activeZone ? severeByZone[activeZone.id] : null;

  // Center map on the first zone (or average if multi)
  const mapCenter = useMemo(() => {
    if (zones.length === 0) return [LOURDES.lat, LOURDES.lon];
    if (zones.length === 1) return [zones[0].lat, zones[0].lon];
    const avgLat = zones.reduce((s, z) => s + z.lat, 0) / zones.length;
    const avgLon = zones.reduce((s, z) => s + z.lon, 0) / zones.length;
    return [avgLat, avgLon];
  }, [zones]);

  const chartData = (activeData?.hourly || []).map((h) => ({
    time: h.time?.split("T")[1]?.slice(0, 5) || "",
    score: h.hail_score,
    cape: h.cape,
    li: h.lifted_index,
    fzh: h.freezing_level_m,
    shear: h.shear_0_6km,
  }));

  return (
    <div className="min-h-screen bg-slate-50/70" data-testid="grele-page">
      <div className="max-w-7xl mx-auto px-4 lg:px-8 py-6 lg:py-10">
        <NavTabs />

        <header className="mt-8 mb-6 flex items-end justify-between gap-4 flex-wrap">
          <div>
            <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-[0.3em] text-slate-500 font-semibold">
              <CloudHail className="w-4 h-4 text-slate-900" strokeWidth={2.2} />
              Prévision grêle · 24 h glissantes
            </div>
            <h1 className="font-heading text-3xl md:text-4xl font-black tracking-tighter text-slate-900 leading-[0.95] mt-2">
              Risque de grêle<br />
              <span className="text-slate-400">{zones.length} zone{zones.length > 1 ? "s" : ""} surveillée{zones.length > 1 ? "s" : ""}</span>
            </h1>
          </div>
          <button
            onClick={loadAll}
            disabled={loading}
            className="flex items-center gap-2 px-4 h-9 border border-slate-300 bg-white text-slate-900 hover:bg-slate-900 hover:text-white hover:border-slate-900 transition-colors font-mono text-[10px] uppercase tracking-[0.2em] disabled:opacity-50"
            data-testid="grele-refresh"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            Actualiser
          </button>
        </header>

        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 text-xs text-red-800 font-mono" data-testid="grele-error">
            {error}
          </div>
        )}

        {/* Map */}
        <div className="border border-slate-200 bg-white">
          <div className="h-[420px] lg:h-[520px] relative" data-testid="grele-map">
            {/* Sélecteur de fond de carte */}
            <div className="absolute top-4 right-4 z-[500] flex bg-white border border-slate-200 shadow-[0_2px_16px_rgba(0,0,0,0.04)] overflow-hidden" data-testid="basemap-selector">
              {[
                { k: "clair", Icon: Sun, label: "Clair" },
                { k: "sombre", Icon: Moon, label: "Sombre" },
                { k: "satellite", Icon: Globe, label: "Satellite" },
              ].map(({ k, Icon, label }) => (
                <button
                  key={k}
                  onClick={() => changeBasemap(k)}
                  className={`w-11 h-11 flex items-center justify-center transition-colors ${
                    basemap === k ? "bg-slate-900 text-white" : "bg-white text-slate-600 hover:bg-slate-100"
                  }`}
                  title={label}
                  aria-label={label}
                  data-testid={`basemap-${k}`}
                >
                  <Icon className="w-5 h-5" strokeWidth={1.8} />
                </button>
              ))}
            </div>
            <MapContainer
              center={mapCenter}
              zoom={zones.length > 1 ? 6 : 9}
              minZoom={3}
              maxZoom={12}
              scrollWheelZoom
              style={{ height: "100%", width: "100%" }}
            >
              <TileLayer
                key={`base-${basemap}`}
                attribution={bm.attribution}
                url={bm.base}
                maxZoom={19}
                maxNativeZoom={bm.maxNative}
              />
              <TileLayer
                key={`labels-${basemap}`}
                url={bm.labels}
                maxZoom={19}
                maxNativeZoom={bm.maxNative}
                pane="tooltipPane"
              />
              {zones.map((z) => {
                const data = severeByZone[z.id];
                const score = data?.max_hail_score ?? 0;
                const level = data?.max_hail_level || "nul";
                const color = HAIL_COLORS[level] || HAIL_COLORS.nul;
                // Radius proportional to score (50 km min, 120 km max for extrême)
                const r = 50_000 + (score / 100) * 70_000;
                return (
                  <Circle
                    key={`c-${z.id}`}
                    center={[z.lat, z.lon]}
                    radius={r}
                    pathOptions={{ color, fillColor: color, fillOpacity: 0.18, weight: 2 }}
                    eventHandlers={{ click: () => setActiveId(z.id) }}
                  />
                );
              })}
              {zones.map((z) => {
                const data = severeByZone[z.id];
                const level = data?.max_hail_level || "nul";
                const color = HAIL_COLORS[level] || HAIL_COLORS.nul;
                return (
                  <Marker
                    key={`m-${z.id}`}
                    position={[z.lat, z.lon]}
                    icon={buildLabelIcon(z.name, color)}
                    eventHandlers={{ click: () => setActiveId(z.id) }}
                  />
                );
              })}
            </MapContainer>
          </div>
          <div className="px-4 py-3 border-t border-slate-200">
            <HailScale />
          </div>
        </div>

        {/* Zone selector + max scores table */}
        <div className="mt-6 grid grid-cols-1 lg:grid-cols-12 gap-6">
          <div className="lg:col-span-5 border border-slate-200 bg-white p-5" data-testid="grele-zones-list">
            <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400 mb-3">
              Zones surveillées — temps réel · pic 24 h
            </div>
            <ul className="divide-y divide-slate-100">
              {zones.map((z) => {
                const d = severeByZone[z.id];
                const theoretical_max = d?.max_hail_score ?? null;
                const level_max = d?.max_hail_level || "—";
                const rt = d?.realtime || {};
                const rt_score = rt.realtime_h0;
                const theo_h0 = rt.theoretical_h0;
                const surge = !!rt.is_surge;
                const lightning_off = rt.lightning_available === false;
                const color_max = theoretical_max != null ? HAIL_COLORS[level_max] || HAIL_COLORS.nul : "#CBD5E1";
                const isActive = z.id === activeId;
                return (
                  <li key={z.id}>
                    <button
                      onClick={() => setActiveId(z.id)}
                      className={`w-full flex items-center justify-between py-3 px-1 text-left transition-colors ${
                        isActive ? "bg-slate-50" : "hover:bg-slate-50"
                      }`}
                      data-testid={`grele-zone-${z.id}`}
                    >
                      <div className="flex items-center gap-3 min-w-0 flex-1">
                        <span className="w-3 h-3 shrink-0" style={{ background: color_max }} />
                        <div className="min-w-0">
                          <div className="text-sm font-medium text-slate-900 truncate flex items-center gap-2">
                            <span>{z.name}</span>
                            {surge && (
                              <span
                                className="inline-flex items-center gap-0.5 px-1.5 py-0.5 bg-red-600 text-white font-mono text-[9px] uppercase tracking-[0.1em]"
                                title="Saut brutal de l'activité électrique détecté"
                                data-testid={`grele-surge-${z.id}`}
                              >
                                <Zap className="w-2.5 h-2.5" strokeWidth={3} /> surge
                              </span>
                            )}
                            {lightning_off && (
                              <span
                                className="inline-flex items-center gap-0.5 px-1.5 py-0.5 bg-amber-100 text-amber-800 border border-amber-300 font-mono text-[9px] uppercase tracking-[0.1em]"
                                title="Données électriques Blitzortung temporairement indisponibles"
                                data-testid={`grele-lightning-off-${z.id}`}
                              >
                                <ZapOff className="w-2.5 h-2.5" /> n/a
                              </span>
                            )}
                            {isActive && (
                              <span className="font-mono text-[9px] uppercase tracking-[0.15em] text-slate-500">
                                · active
                              </span>
                            )}
                          </div>
                          <div className="font-mono text-[10px] text-slate-400">
                            {d?.max_hail_time
                              ? `pic à ${fmtLocalTime(d.max_hail_time)} · ${level_max}`
                              : loading ? "…" : "pas de pic détecté"}
                          </div>
                        </div>
                      </div>
                      <div className="text-right shrink-0 ml-3 grid grid-cols-2 gap-x-3 gap-y-0">
                        <div className="text-right">
                          <div className={`font-mono text-lg font-medium tabular-nums leading-none ${surge ? "text-red-600" : "text-slate-900"}`}>
                            {rt_score != null ? rt_score.toFixed(0) : (theo_h0 != null ? theo_h0.toFixed(0) : "—")}
                          </div>
                          <div className="font-mono text-[8px] uppercase tracking-[0.15em] text-slate-500 mt-0.5">
                            temps réel
                          </div>
                        </div>
                        <div className="text-right">
                          <div className="font-mono text-lg font-medium text-slate-400 tabular-nums leading-none">
                            {theoretical_max != null ? theoretical_max.toFixed(0) : "—"}
                          </div>
                          <div className="font-mono text-[8px] uppercase tracking-[0.15em] text-slate-400 mt-0.5">
                            pic 24h
                          </div>
                        </div>
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>

            {/* Legend for the two scores */}
            <div className="mt-4 pt-4 border-t border-slate-100 text-[10px] font-mono text-slate-500 leading-relaxed">
              <div className="flex items-center gap-1.5 mb-1">
                <Zap className="w-3 h-3 text-red-600" />
                <span>
                  <strong>Temps réel</strong> = théorique H+0 + boost activité électrique
                  (rayon adaptatif <span className="text-slate-700">≥40 km</span>)
                </span>
              </div>
              <div className="flex items-center gap-1.5">
                <AlertTriangle className="w-3 h-3 text-slate-400" />
                <span><strong>Pic 24h</strong> = score théorique max sur la prévision</span>
              </div>
            </div>
          </div>

          {/* Time-series for active zone */}
          <div className="lg:col-span-7 border border-slate-200 bg-white p-5">
            <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
              <div>
                <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400">
                  Évolution 24 h — {activeZone?.name || "—"}
                </div>
                <div className="font-mono text-xs text-slate-600 mt-0.5 flex items-center gap-2">
                  <MapPin className="w-3 h-3" />
                  {activeZone ? `${activeZone.lat.toFixed(3)}, ${activeZone.lon.toFixed(3)}` : ""}
                </div>
              </div>
              {loading && <Loader2 className="w-4 h-4 animate-spin text-slate-400" />}
            </div>
            {chartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={240}>
                <LineChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="2 4" stroke="#E2E8F0" />
                  <XAxis dataKey="time" tick={{ fontSize: 10, fontFamily: "monospace", fill: "#94A3B8" }} interval={2} />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 10, fontFamily: "monospace", fill: "#94A3B8" }} />
                  <ReferenceLine y={30} stroke="#F59E0B" strokeDasharray="3 3" label={{ value: "modéré", fontSize: 9, fill: "#F59E0B" }} />
                  <ReferenceLine y={50} stroke="#EF4444" strokeDasharray="3 3" label={{ value: "fort", fontSize: 9, fill: "#EF4444" }} />
                  <ReferenceLine y={70} stroke="#7F1D1D" strokeDasharray="3 3" label={{ value: "extrême", fontSize: 9, fill: "#7F1D1D" }} />
                  <Tooltip
                    contentStyle={{ fontSize: 11, fontFamily: "monospace", background: "#0F172A", color: "#fff", border: "none" }}
                    labelStyle={{ color: "#94A3B8" }}
                    formatter={(v, n) => {
                      if (n === "score") return [v?.toFixed(0), "Score grêle"];
                      if (n === "cape") return [v?.toFixed(0), "CAPE (J/kg)"];
                      if (n === "li") return [v?.toFixed(1), "Lifted Index"];
                      if (n === "shear") return [v?.toFixed(1), "Shear 0-6 km (m/s)"];
                      if (n === "fzh") return [v?.toFixed(0), "Isotherme 0°C (m)"];
                      return [v, n];
                    }}
                  />
                  <Line type="monotone" dataKey="score" stroke="#0F172A" strokeWidth={2.5} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-[240px] flex items-center justify-center text-xs text-slate-400 font-mono">
                {loading ? "Chargement…" : "Pas de données"}
              </div>
            )}

            {/* Ingredients summary */}
            {activeData && (
              <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-3 text-[11px] font-mono" data-testid="grele-ingredients">
                {(() => {
                  const peakIdx = activeData.hourly.findIndex((h) => h.time === activeData.max_hail_time);
                  const peak = activeData.hourly[Math.max(0, peakIdx)] || activeData.hourly[0];
                  if (!peak) return null;
                  const cells = [
                    { label: "CAPE", v: peak.cape != null ? `${Math.round(peak.cape)} J/kg` : "—" },
                    { label: "Lifted Index", v: peak.lifted_index != null ? peak.lifted_index.toFixed(1) : "—" },
                    { label: "Shear 0-6 km", v: peak.shear_0_6km != null ? `${peak.shear_0_6km.toFixed(1)} m/s` : "—" },
                    { label: "Iso 0°C", v: peak.freezing_level_m != null ? `${Math.round(peak.freezing_level_m)} m` : "—" },
                  ];
                  return cells.map((c) => (
                    <div key={c.label} className="border border-slate-200 p-2.5">
                      <div className="text-[9px] uppercase tracking-[0.15em] text-slate-400">{c.label}</div>
                      <div className="text-slate-900 tabular-nums mt-0.5">{c.v}</div>
                    </div>
                  ));
                })()}
              </div>
            )}

            {/* 1h history of (theoretical vs realtime) score — the surge witness */}
            {activeData?.history_1h && activeData.history_1h.length > 1 && (
              <div className="mt-5 pt-4 border-t border-slate-100" data-testid="grele-history-1h">
                <div className="flex items-center justify-between mb-2">
                  <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400">
                    Historique 1 h · score temps réel vs théorique
                  </div>
                  {activeData.realtime?.is_surge && (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-red-600 text-white font-mono text-[10px] uppercase tracking-[0.15em]">
                      <Zap className="w-3 h-3" strokeWidth={3} /> surge actif
                    </span>
                  )}
                </div>
                <ResponsiveContainer width="100%" height={120}>
                  <AreaChart
                    data={activeData.history_1h.map((s) => ({
                      time: new Date(s.ts * 1000).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }),
                      theoretical: s.theoretical,
                      realtime: s.realtime,
                      surge: s.is_surge ? s.realtime : null,
                    }))}
                    margin={{ top: 4, right: 4, left: 0, bottom: 0 }}
                  >
                    <defs>
                      <linearGradient id="rtGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#DC2626" stopOpacity={0.5} />
                        <stop offset="100%" stopColor="#DC2626" stopOpacity={0.05} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="2 4" stroke="#E2E8F0" />
                    <XAxis dataKey="time" tick={{ fontSize: 9, fontFamily: "monospace", fill: "#94A3B8" }} interval="preserveStartEnd" />
                    <YAxis domain={[0, 100]} tick={{ fontSize: 9, fontFamily: "monospace", fill: "#94A3B8" }} width={28} />
                    <Tooltip
                      contentStyle={{ fontSize: 10, fontFamily: "monospace", background: "#0F172A", color: "#fff", border: "none" }}
                      labelStyle={{ color: "#94A3B8" }}
                      formatter={(v, n) => {
                        if (n === "theoretical") return [v?.toFixed(0), "Théorique"];
                        if (n === "realtime") return [v?.toFixed(0), "Temps réel"];
                        return [v, n];
                      }}
                    />
                    <Area type="monotone" dataKey="realtime" stroke="#DC2626" strokeWidth={2} fill="url(#rtGrad)" />
                    <Line type="monotone" dataKey="theoretical" stroke="#94A3B8" strokeWidth={1.5} strokeDasharray="3 3" dot={false} />
                  </AreaChart>
                </ResponsiveContainer>
                {(() => {
                  const h = activeData.history_1h;
                  if (h.length < 2) return null;
                  const first = h[0].realtime;
                  const last = h[h.length - 1].realtime;
                  const delta = last - first;
                  const sign = delta >= 0 ? "+" : "";
                  return (
                    <div className={`mt-1 font-mono text-[10px] ${delta >= 5 ? "text-red-600 font-medium" : "text-slate-500"}`}>
                      Δ sur la fenêtre : {sign}{delta.toFixed(1)} pts
                      {delta >= 5 && " — l'orage se développe"}
                    </div>
                  );
                })()}
              </div>
            )}
          </div>
        </div>

        <footer className="pt-6 mt-6 border-t border-slate-100 text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400">
          Données · Open-Meteo (CAPE, Lifted Index, niveaux 300/500/850 hPa, isotherme 0°C). Score composite empirique — informatif, non contractuel.
        </footer>
      </div>
    </div>
  );
}
