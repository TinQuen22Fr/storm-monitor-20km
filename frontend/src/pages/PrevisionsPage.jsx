import { useCallback, useEffect, useMemo, useState } from "react";
import { LineChart, Line, Tooltip, ResponsiveContainer, XAxis, YAxis, CartesianGrid, ReferenceLine } from "recharts";
import { Loader2, RefreshCw, TrendingUp, Wind } from "lucide-react";
import NavTabs from "@/components/NavTabs";
import FranceMapPanel from "@/components/FranceMapPanel";
import HourlyForecastPanel from "@/components/HourlyForecastPanel";
import VerticalProfileChart from "@/components/VerticalProfileChart";
import AirQualityCard from "@/components/AirQualityCard";
import ErrorBoundary from "@/components/ErrorBoundary";
import { useAuth } from "@/lib/auth";
import { getSevere, listFavorites, LOURDES } from "@/lib/api";
import { setLocalTimezone, fmtLocalTime } from "@/lib/timeFormat";

function loadVisibility() {
  try {
    const raw = localStorage.getItem("storm.favVisibility");
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function ChartCard({ title, subtitle, children, badge, testid }) {
  return (
    <div className="border border-slate-200 bg-white p-5" data-testid={testid}>
      <div className="flex items-start justify-between mb-3 gap-3">
        <div>
          <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400">{title}</div>
          {subtitle && <div className="font-mono text-[10px] text-slate-500 mt-0.5">{subtitle}</div>}
        </div>
        {badge}
      </div>
      {children}
    </div>
  );
}

export default function PrevisionsPage() {
  const { user } = useAuth();
  const [favs, setFavs] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Build the list of available zones (favs cochés en premier, puis autres favs en option, sinon Lourdes)
  const zones = useMemo(() => {
    if (!user || favs.length === 0) {
      return [{ id: "default", name: "Lourdes", lat: LOURDES.lat, lon: LOURDES.lon, visible: true }];
    }
    const vis = loadVisibility();
    const visible = favs.filter((f) => vis[f.id] !== false);
    const hidden = favs.filter((f) => vis[f.id] === false);
    if (visible.length === 0 && hidden.length === 0) {
      return [{ id: "default", name: "Lourdes", lat: LOURDES.lat, lon: LOURDES.lon, visible: true }];
    }
    return [
      ...visible.map((f) => ({ id: f.id, name: f.name, lat: f.lat, lon: f.lon, visible: true })),
      ...hidden.map((f) => ({ id: f.id, name: f.name, lat: f.lat, lon: f.lon, visible: false })),
    ];
  }, [user, favs]);

  // Load favorites
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

  // Default active = first visible zone
  useEffect(() => {
    if (zones.length === 0) return;
    if (!zones.find((z) => z.id === activeId)) {
      setActiveId(zones[0].id);
    }
  }, [zones, activeId]);

  const activeZone = useMemo(
    () => zones.find((z) => z.id === activeId) || zones[0],
    [zones, activeId]
  );

  const loadSevere = useCallback(async () => {
    if (!activeZone) return;
    setLoading(true);
    setError(null);
    try {
      const d = await getSevere(activeZone.lat, activeZone.lon, 48);
      setData(d);
      if (d?.timezone) setLocalTimezone(d.timezone);
    } catch (e) {
      const status = e?.response?.status;
      if (status === 404) {
        setError(
          "Endpoint /api/weather/severe absent du backend (HTTP 404). " +
          "Le serveur tourne sur une branche obsolète. Sur le VPS : " +
          "sudo BRANCH=Version_With_Detector bash /opt/storm-monitor/upgrade.sh"
        );
      } else if (status) {
        setError(`Erreur backend HTTP ${status} sur /api/weather/severe`);
      } else {
        setError("Erreur réseau lors du chargement des prévisions avancées");
      }
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [activeZone]);

  useEffect(() => {
    loadSevere();
    const t = setInterval(loadSevere, 5 * 60_000);
    return () => clearInterval(t);
  }, [loadSevere]);

  const hourly = data?.hourly || [];
  const chartData = hourly.map((h) => ({
    time: h.time?.split("T")[1]?.slice(0, 5) + (h.time?.split("T")[0]?.endsWith("-01") ? " J+1" : ""),
    fullTime: h.time,
    t2m: h.t2m,
    t850: h.t850,
    soil_t: h.soil_t,
    jet: h.jet_speed != null ? h.jet_speed * 3.6 : null, // m/s → km/h pour lecture
    jetDir: h.jet_direction,
    shear06: h.shear_0_6km,
    shear850500: h.shear_850_500,
    vv700: h.vertical_velocity_700,
  }));

  // Pre-compute key extrema for the badges
  const maxJet = hourly.reduce((m, h) => (h.jet_speed != null && h.jet_speed > (m?.jet_speed || -1) ? h : m), null);
  const maxShear = hourly.reduce((m, h) => (h.shear_0_6km != null && h.shear_0_6km > (m?.shear_0_6km || -1) ? h : m), null);

  return (
    <div className="min-h-screen bg-slate-50/70" data-testid="previsions-page">
      <div className="max-w-7xl mx-auto px-4 lg:px-8 py-6 lg:py-10">
        <NavTabs />

        <header className="mt-8 mb-6 flex items-end justify-between gap-4 flex-wrap">
          <div>
            <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-[0.3em] text-slate-500 font-semibold">
              <TrendingUp className="w-4 h-4 text-slate-900" strokeWidth={2.2} />
              Prévisions avancées · 48 h
            </div>
            <h1 className="font-heading text-3xl md:text-4xl font-black tracking-tighter text-slate-900 leading-[0.95] mt-2">
              Paramètres atmosphériques
            </h1>
            <p className="text-sm text-slate-500 mt-2">
              T° sol & 850 hPa · jet stream · cisaillement · vitesse verticale.
            </p>
          </div>
          <button
            onClick={loadSevere}
            disabled={loading}
            className="flex items-center gap-2 px-4 h-9 border border-slate-300 bg-white text-slate-900 hover:bg-slate-900 hover:text-white hover:border-slate-900 transition-colors font-mono text-[10px] uppercase tracking-[0.2em] disabled:opacity-50"
            data-testid="previsions-refresh"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            Actualiser
          </button>
        </header>

        {/* Zone selector */}
        <div className="mb-6 border border-slate-200 bg-white p-5" data-testid="previsions-zone-selector">
          <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400 mb-3">
            Zone affichée
          </div>
          <div className="flex flex-wrap gap-2">
            {zones.map((z) => {
              const isActive = z.id === activeId;
              return (
                <button
                  key={z.id}
                  onClick={() => setActiveId(z.id)}
                  className={`flex items-center gap-2 px-3 h-9 border font-mono text-[11px] transition-colors ${
                    isActive
                      ? "bg-slate-900 text-white border-slate-900"
                      : z.visible
                      ? "bg-blue-50 text-blue-900 border-blue-300 hover:bg-blue-100"
                      : "bg-white text-slate-500 border-slate-300 hover:border-slate-500"
                  }`}
                  data-testid={`previsions-zone-${z.id}`}
                  title={z.visible ? "Zone visible sur la carte" : "Zone masquée — disponible pour aperçu uniquement"}
                >
                  <span>{z.name}</span>
                  {!z.visible && (
                    <span className="font-mono text-[9px] uppercase tracking-[0.15em] opacity-70">
                      masquée
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 text-xs text-red-800 font-mono" data-testid="previsions-error">
            {error}
          </div>
        )}

        {/* Prévisions horaires 24h grand public (T°, % précip/orage, UV, humidité…) */}
        {activeZone && (
          <div className="mb-6">
            <ErrorBoundary label="Erreur lors du rendu des prévisions horaires.">
              <HourlyForecastPanel
                lat={activeZone.lat}
                lon={activeZone.lon}
                name={activeZone.name}
              />
            </ErrorBoundary>
          </div>
        )}

        {/* France-wide interactive map (Windy-style) */}
        <div className="mb-6">
          <ErrorBoundary label="Erreur lors du rendu de la carte France. Recharge la page ou réessaie.">
            <FranceMapPanel favorites={zones} />
          </ErrorBoundary>
        </div>

        {!data && loading && (
          <div className="border border-slate-200 bg-white p-12 flex items-center justify-center">
            <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
          </div>
        )}

        {data && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* T° 2m + 850hPa + sol */}
            <ChartCard
              title="Températures"
              subtitle="sol (2 m) · isotherme 850 hPa (~1500 m) · surface du sol"
              testid="chart-temperatures"
            >
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="2 4" stroke="#E2E8F0" />
                  <XAxis dataKey="time" tick={{ fontSize: 9, fontFamily: "monospace", fill: "#94A3B8" }} interval={5} />
                  <YAxis tick={{ fontSize: 10, fontFamily: "monospace", fill: "#94A3B8" }} unit="°" />
                  <ReferenceLine y={0} stroke="#3B82F6" strokeDasharray="3 3" label={{ value: "0°C", fontSize: 9, fill: "#3B82F6" }} />
                  <Tooltip
                    contentStyle={{ fontSize: 11, fontFamily: "monospace", background: "#0F172A", color: "#fff", border: "none" }}
                    labelStyle={{ color: "#94A3B8" }}
                    formatter={(v, n) => {
                      if (n === "t2m") return [v?.toFixed(1) + "°C", "Air 2m"];
                      if (n === "t850") return [v?.toFixed(1) + "°C", "850 hPa"];
                      if (n === "soil_t") return [v?.toFixed(1) + "°C", "Sol 0cm"];
                      return [v, n];
                    }}
                  />
                  <Line type="monotone" dataKey="t2m" stroke="#DC2626" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="t850" stroke="#7C3AED" strokeWidth={2} dot={false} strokeDasharray="4 3" />
                  <Line type="monotone" dataKey="soil_t" stroke="#D97706" strokeWidth={1.5} dot={false} strokeDasharray="2 2" />
                </LineChart>
              </ResponsiveContainer>
              <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[10px] font-mono">
                <span className="flex items-center gap-1.5"><span className="w-3 h-0.5 bg-red-600" /> Air 2 m</span>
                <span className="flex items-center gap-1.5"><span className="w-3 h-0.5 bg-violet-600" style={{ borderBottom: "2px dashed #7C3AED" }} /> 850 hPa</span>
                <span className="flex items-center gap-1.5"><span className="w-3 h-0.5 bg-amber-600" /> Sol 0 cm</span>
              </div>
            </ChartCard>

            {/* Jet stream 300hPa */}
            <ChartCard
              title="Jet stream · 300 hPa (~9 km)"
              subtitle="vitesse en km/h · indicateur des perturbations de grande échelle"
              testid="chart-jet"
              badge={
                maxJet && (
                  <div className="text-right">
                    <div className="font-mono text-[10px] text-slate-400 uppercase tracking-[0.15em]">pic 48h</div>
                    <div className="font-mono text-lg font-medium text-slate-900 tabular-nums leading-none">
                      {Math.round(maxJet.jet_speed * 3.6)} km/h
                    </div>
                    <div className="font-mono text-[10px] text-slate-500 mt-0.5">
                      {fmtLocalTime(maxJet.time)} · {Math.round(maxJet.jet_direction || 0)}°
                    </div>
                  </div>
                )
              }
            >
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="2 4" stroke="#E2E8F0" />
                  <XAxis dataKey="time" tick={{ fontSize: 9, fontFamily: "monospace", fill: "#94A3B8" }} interval={5} />
                  <YAxis tick={{ fontSize: 10, fontFamily: "monospace", fill: "#94A3B8" }} />
                  <ReferenceLine y={150} stroke="#F59E0B" strokeDasharray="3 3" label={{ value: "150 km/h", fontSize: 9, fill: "#F59E0B" }} />
                  <ReferenceLine y={250} stroke="#DC2626" strokeDasharray="3 3" label={{ value: "250 km/h", fontSize: 9, fill: "#DC2626" }} />
                  <Tooltip
                    contentStyle={{ fontSize: 11, fontFamily: "monospace", background: "#0F172A", color: "#fff", border: "none" }}
                    labelStyle={{ color: "#94A3B8" }}
                    formatter={(v, n) => (n === "jet" ? [v?.toFixed(0) + " km/h", "Jet 300hPa"] : [v, n])}
                  />
                  <Line type="monotone" dataKey="jet" stroke="#0EA5E9" strokeWidth={2.5} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </ChartCard>

            {/* Cisaillement */}
            <ChartCard
              title="Cisaillement (m/s)"
              subtitle="0-6 km (~surface → 500 hPa) · 850-500 hPa · indicateur de structure orageuse"
              testid="chart-shear"
              badge={
                maxShear && (
                  <div className="text-right">
                    <div className="font-mono text-[10px] text-slate-400 uppercase tracking-[0.15em]">pic 0-6 km</div>
                    <div className="font-mono text-lg font-medium text-slate-900 tabular-nums leading-none">
                      {maxShear.shear_0_6km?.toFixed(1)}
                    </div>
                    <div className="font-mono text-[10px] text-slate-500 mt-0.5">
                      {fmtLocalTime(maxShear.time)}
                    </div>
                  </div>
                )
              }
            >
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="2 4" stroke="#E2E8F0" />
                  <XAxis dataKey="time" tick={{ fontSize: 9, fontFamily: "monospace", fill: "#94A3B8" }} interval={5} />
                  <YAxis tick={{ fontSize: 10, fontFamily: "monospace", fill: "#94A3B8" }} unit=" m/s" />
                  <ReferenceLine y={15} stroke="#F59E0B" strokeDasharray="3 3" label={{ value: "modéré", fontSize: 9, fill: "#F59E0B" }} />
                  <ReferenceLine y={25} stroke="#DC2626" strokeDasharray="3 3" label={{ value: "fort", fontSize: 9, fill: "#DC2626" }} />
                  <Tooltip
                    contentStyle={{ fontSize: 11, fontFamily: "monospace", background: "#0F172A", color: "#fff", border: "none" }}
                    labelStyle={{ color: "#94A3B8" }}
                    formatter={(v, n) => {
                      if (n === "shear06") return [v?.toFixed(1) + " m/s", "0-6 km"];
                      if (n === "shear850500") return [v?.toFixed(1) + " m/s", "850-500 hPa"];
                      return [v, n];
                    }}
                  />
                  <Line type="monotone" dataKey="shear06" stroke="#7C3AED" strokeWidth={2.5} dot={false} />
                  <Line type="monotone" dataKey="shear850500" stroke="#94A3B8" strokeWidth={1.5} dot={false} strokeDasharray="3 3" />
                </LineChart>
              </ResponsiveContainer>
              <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[10px] font-mono">
                <span className="flex items-center gap-1.5"><span className="w-3 h-0.5 bg-violet-600" /> 0-6 km</span>
                <span className="flex items-center gap-1.5"><span className="w-3 h-0.5 bg-slate-400" /> 850-500 hPa</span>
              </div>
            </ChartCard>

            {/* Vitesse verticale 700hPa */}
            <ChartCard
              title="Vitesse verticale · 700 hPa (~3 km)"
              subtitle="Pa/s — négatif = ascendance (orage potentiel), positif = subsidence"
              testid="chart-vv"
              badge={<Wind className="w-4 h-4 text-slate-400" />}
            >
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="2 4" stroke="#E2E8F0" />
                  <XAxis dataKey="time" tick={{ fontSize: 9, fontFamily: "monospace", fill: "#94A3B8" }} interval={5} />
                  <YAxis tick={{ fontSize: 10, fontFamily: "monospace", fill: "#94A3B8" }} unit=" Pa/s" />
                  <ReferenceLine y={0} stroke="#94A3B8" />
                  <ReferenceLine y={-0.3} stroke="#7C3AED" strokeDasharray="3 3" label={{ value: "ascendance forte", fontSize: 9, fill: "#7C3AED" }} />
                  <Tooltip
                    contentStyle={{ fontSize: 11, fontFamily: "monospace", background: "#0F172A", color: "#fff", border: "none" }}
                    labelStyle={{ color: "#94A3B8" }}
                    formatter={(v, n) => (n === "vv700" ? [v?.toFixed(3) + " Pa/s", "ω 700hPa"] : [v, n])}
                  />
                  <Line type="monotone" dataKey="vv700" stroke="#0F172A" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </ChartCard>
          </div>
        )}

        {/* Vertical temperature profile for the active zone */}
        {activeZone && (
          <div className="mt-6">
            <ErrorBoundary label="Erreur lors du rendu du profil vertical.">
              <VerticalProfileChart
                lat={activeZone.lat}
                lon={activeZone.lon}
                name={activeZone.name}
              />
            </ErrorBoundary>
          </div>
        )}

        {/* Qualité de l'air (Xweather) pour la zone active */}
        {activeZone && (
          <div className="mt-6">
            <ErrorBoundary label="Erreur lors du rendu de la qualité de l'air.">
              <AirQualityCard
                lat={activeZone.lat}
                lon={activeZone.lon}
                name={activeZone.name}
              />
            </ErrorBoundary>
          </div>
        )}

        <footer className="pt-6 mt-6 border-t border-slate-100 text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400">
          Données · Open-Meteo (pressure level forecast). Cisaillement calculé en différence vectorielle.
        </footer>
      </div>
    </div>
  );
}
