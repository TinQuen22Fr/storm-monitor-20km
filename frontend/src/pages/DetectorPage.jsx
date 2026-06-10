import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import { Activity, Cpu, RefreshCw, Target, Wifi, WifiOff, Zap } from "lucide-react";
import { Link } from "react-router-dom";
import NavTabs from "@/components/NavTabs";
import { api } from "@/lib/api";

const REFRESH_MS = 15_000;

function StatTile({ label, value, unit, testId, accent }) {
  return (
    <div
      className={`border border-slate-200 bg-white p-6 ${accent || ""}`}
      data-testid={testId}
    >
      <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400 mb-2">
        {label}
      </div>
      <div className="flex items-baseline gap-1">
        <span className="font-mono text-4xl font-medium text-slate-900 tabular-nums leading-none">
          {value}
        </span>
        {unit && <span className="font-mono text-sm text-slate-400">{unit}</span>}
      </div>
    </div>
  );
}

function KindBadge({ kind }) {
  const map = {
    lightning: { label: "Foudre", bg: "bg-red-50", fg: "text-red-700", border: "border-red-200" },
    disturber: { label: "Parasite", bg: "bg-amber-50", fg: "text-amber-800", border: "border-amber-200" },
    heartbeat: { label: "Ping", bg: "bg-slate-50", fg: "text-slate-500", border: "border-slate-200" },
  };
  const s = map[kind] || map.lightning;
  return (
    <span
      className={`inline-flex items-center px-2 h-5 font-mono text-[9px] uppercase tracking-[0.18em] border ${s.bg} ${s.fg} ${s.border}`}
    >
      {s.label}
    </span>
  );
}

export default function DetectorPage() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastFetch, setLastFetch] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await api.get("/detector/status");
      setStatus(data);
      setLastFetch(new Date());
    } catch {
      setError("Impossible de joindre le backend détecteur");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      try {
        const { data } = await api.get("/detector/status");
        if (!cancelled) {
          setStatus(data);
          setLastFetch(new Date());
          setError(null);
        }
      } catch {
        if (!cancelled) setError("Impossible de joindre le backend détecteur");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    run();
    const t = setInterval(run, REFRESH_MS);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, []);

  const lightnings = useMemo(
    () =>
      (status?.recent || [])
        .filter((r) => (r.kind || "lightning") === "lightning")
        .slice()
        .sort((a, b) => a.timestamp.localeCompare(b.timestamp))
        .map((it) => ({
          t: new Date(it.timestamp).getTime(),
          label: new Date(it.timestamp).toLocaleTimeString("fr-FR", {
            hour: "2-digit",
            minute: "2-digit",
          }),
          energy: it.energy,
          distance: it.distance,
        })),
    [status?.recent]
  );

  const online = !!status?.online;
  const stats = status?.stats_24h || {};
  const apiBase = process.env.REACT_APP_BACKEND_URL;

  const chartTooltip = {
    contentStyle: {
      background: "#0F172A",
      border: "none",
      borderRadius: 0,
      fontFamily: "IBM Plex Mono",
      fontSize: 11,
      color: "#fff",
      padding: "8px 12px",
    },
    labelStyle: { color: "#94A3B8" },
    itemStyle: { color: "#fff" },
  };

  return (
    <div className="min-h-screen w-full bg-slate-50" data-testid="detector-page">
      {/* Header */}
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-6 lg:px-8 py-6 flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Cpu className="w-4 h-4 text-slate-900" strokeWidth={2.5} />
              <span className="font-mono text-[10px] uppercase tracking-[0.3em] text-slate-500 font-semibold">
                Module · AS3935
              </span>
            </div>
            <h1 className="font-heading text-3xl lg:text-4xl font-black tracking-tighter text-slate-900">
              Détecteur d&apos;orage · live
            </h1>
            <p className="text-sm text-slate-500 mt-2 max-w-xl">
              Données capturées en direct par le détecteur Franklin AS3935 sur site.
              Heartbeat toutes les 5 minutes — événements remontés à chaque impact détecté.
            </p>
          </div>
          <div className="w-full lg:w-80 shrink-0">
            <NavTabs variant="inline" />
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 lg:px-8 py-8 lg:py-10 space-y-8">
        {/* Status banner */}
        <section
          className={`border p-5 flex items-center gap-4 ${
            online ? "border-emerald-200 bg-emerald-50" : "border-red-200 bg-red-50"
          }`}
          data-testid="detector-status-banner"
        >
          {online ? (
            <Wifi className="w-6 h-6 text-emerald-700 shrink-0" strokeWidth={2} />
          ) : (
            <WifiOff className="w-6 h-6 text-red-700 shrink-0" strokeWidth={2} />
          )}
          <div className="flex-1 min-w-0">
            <div
              className={`font-mono text-[10px] uppercase tracking-[0.25em] font-semibold ${
                online ? "text-emerald-800" : "text-red-800"
              }`}
              data-testid="detector-status-label"
            >
              {online ? "Détecteur en ligne" : "Détecteur hors ligne"}
            </div>
            <div className="font-heading text-lg font-bold text-slate-900 mt-0.5">
              {status?.last_seen
                ? `Dernier signal · ${new Date(status.last_seen).toLocaleString("fr-FR")}`
                : "Aucune donnée reçue"}
            </div>
            <div className="text-[11px] font-mono text-slate-500 mt-0.5">
              Fenêtre de présence : {status?.window_minutes ?? 10} min · auto-refresh {REFRESH_MS / 1000} s
            </div>
          </div>
          <button
            onClick={load}
            disabled={loading}
            className="shrink-0 flex items-center gap-2 px-4 h-10 border border-slate-300 bg-white text-slate-900 hover:bg-slate-900 hover:text-white hover:border-slate-900 transition-colors font-mono text-[10px] uppercase tracking-[0.2em] disabled:opacity-50"
            data-testid="detector-refresh"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} strokeWidth={1.8} />
            {loading ? "…" : "Rafraîchir"}
          </button>
          <Link
            to="/detector/tune"
            className="shrink-0 inline-flex items-center gap-2 px-4 h-10 border border-slate-900 bg-slate-900 text-white hover:bg-violet-700 hover:border-violet-700 transition-colors font-mono text-[10px] uppercase tracking-[0.2em]"
            data-testid="open-tune-wizard"
          >
            <Target className="w-4 h-4" strokeWidth={2} />
            Autotune antenne
          </Link>
        </section>

        {error && (
          <div
            className="p-4 border border-red-200 bg-red-50 text-sm text-red-800 font-mono"
            data-testid="detector-error"
          >
            {error}
          </div>
        )}

        {/* Stats 24h */}
        <section className="grid grid-cols-2 lg:grid-cols-4 gap-0 -m-px" data-testid="detector-stats">
          <StatTile
            label="Impacts 24h"
            value={stats.lightnings ?? 0}
            testId="stat-lightnings-24h"
          />
          <StatTile
            label="Parasites 24h"
            value={stats.disturbers ?? 0}
            testId="stat-disturbers-24h"
          />
          <StatTile
            label="Distance min"
            value={stats.closest_km != null ? stats.closest_km.toFixed(1) : "—"}
            unit={stats.closest_km != null ? "km" : ""}
            testId="stat-closest-km"
          />
          <StatTile
            label="Énergie max"
            value={stats.max_energy != null ? stats.max_energy.toFixed(1) : "—"}
            unit={stats.max_energy != null ? "kJ" : ""}
            testId="stat-max-energy"
          />
        </section>

        {/* Charts */}
        {lightnings.length > 0 && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-0 -m-px">
            <section
              className="border border-slate-200 bg-white p-6 lg:p-8"
              data-testid="chart-energy-24h"
            >
              <div className="flex items-start justify-between mb-5">
                <div>
                  <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400 mb-1">
                    Série 24 h
                  </div>
                  <h2 className="font-heading text-lg font-bold text-slate-900">
                    Énergie des impacts
                  </h2>
                </div>
                <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-400">
                  unité · kJ
                </span>
              </div>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={lightnings}>
                    <defs>
                      <linearGradient id="detEnergy" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#DC2626" stopOpacity={0.35} />
                        <stop offset="100%" stopColor="#DC2626" stopOpacity={0.02} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="2 4" stroke="#E2E8F0" vertical={false} />
                    <XAxis
                      dataKey="label"
                      tick={{ fontSize: 10, fontFamily: "IBM Plex Mono", fill: "#94A3B8" }}
                      axisLine={{ stroke: "#E2E8F0" }}
                      tickLine={false}
                      interval={Math.max(0, Math.floor(lightnings.length / 6))}
                    />
                    <YAxis
                      tick={{ fontSize: 10, fontFamily: "IBM Plex Mono", fill: "#94A3B8" }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <Tooltip {...chartTooltip} formatter={(v) => [`${Number(v).toFixed(2)} kJ`, "Énergie"]} />
                    <Area
                      type="monotone"
                      dataKey="energy"
                      stroke="#DC2626"
                      strokeWidth={2}
                      fill="url(#detEnergy)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </section>

            <section
              className="border border-slate-200 bg-white p-6 lg:p-8"
              data-testid="chart-scatter-24h"
            >
              <div className="flex items-start justify-between mb-5">
                <div>
                  <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400 mb-1">
                    Corrélation
                  </div>
                  <h2 className="font-heading text-lg font-bold text-slate-900">
                    Distance × Énergie
                  </h2>
                </div>
                <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-400">
                  {lightnings.length} points
                </span>
              </div>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <ScatterChart margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                    <CartesianGrid strokeDasharray="2 4" stroke="#E2E8F0" />
                    <XAxis
                      type="number"
                      dataKey="distance"
                      name="Distance"
                      unit=" km"
                      tick={{ fontSize: 10, fontFamily: "IBM Plex Mono", fill: "#94A3B8" }}
                      axisLine={{ stroke: "#E2E8F0" }}
                    />
                    <YAxis
                      type="number"
                      dataKey="energy"
                      name="Énergie"
                      unit=" kJ"
                      tick={{ fontSize: 10, fontFamily: "IBM Plex Mono", fill: "#94A3B8" }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <ZAxis range={[80, 80]} />
                    <Tooltip {...chartTooltip} cursor={{ strokeDasharray: "3 3" }} />
                    <Scatter data={lightnings} fill="#0F172A" />
                  </ScatterChart>
                </ResponsiveContainer>
              </div>
            </section>
          </div>
        )}

        {/* Recent events feed */}
        <section className="border border-slate-200 bg-white" data-testid="detector-feed">
          <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <Activity className="w-4 h-4 text-slate-900" strokeWidth={2} />
              <h2 className="font-heading text-sm font-bold text-slate-900">
                Flux récent · 24 h
              </h2>
            </div>
            <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-400">
              {(status?.recent || []).length} événements · maj{" "}
              {lastFetch ? lastFetch.toLocaleTimeString("fr-FR") : "--:--"}
            </span>
          </div>
          {(status?.recent || []).length === 0 ? (
            <div className="p-10 text-center">
              <Zap className="w-8 h-8 text-slate-300 mx-auto mb-3" strokeWidth={1.5} />
              <div className="font-mono text-[11px] uppercase tracking-[0.2em] text-slate-400">
                En attente de données du détecteur…
              </div>
              <pre
                className="mt-6 text-left bg-slate-900 text-slate-100 font-mono text-[10px] leading-relaxed p-4 overflow-x-auto max-w-xl mx-auto"
                data-testid="detector-curl-example"
              >
                <code>{`curl -X POST ${apiBase}/api/upload_storm \\
  -H "Content-Type: application/json" \\
  -H "X-API-Key: <UPLOAD_API_KEY>" \\
  -d '{"kind":"lightning","distance":3.4,"energy":42.1,
       "device_id":"as3935-lourdes-01"}'`}</code>
              </pre>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50 text-[10px] font-mono uppercase tracking-wider text-slate-400">
                  <th className="text-left px-6 py-2.5 font-medium">Heure</th>
                  <th className="text-left px-6 py-2.5 font-medium">Type</th>
                  <th className="text-right px-6 py-2.5 font-medium">Distance</th>
                  <th className="text-right px-6 py-2.5 font-medium">Énergie</th>
                  <th className="text-right px-6 py-2.5 font-medium hidden md:table-cell">Device</th>
                </tr>
              </thead>
              <tbody>
                {(status?.recent || []).slice(0, 25).map((it) => {
                  const kind = it.kind || "lightning";
                  return (
                    <tr
                      key={it.id}
                      className="border-t border-slate-100 hover:bg-slate-50"
                      data-testid={`detector-row-${it.id}`}
                    >
                      <td className="px-6 py-3 font-mono text-slate-900 tabular-nums">
                        {new Date(it.timestamp).toLocaleTimeString("fr-FR")}
                      </td>
                      <td className="px-6 py-3">
                        <KindBadge kind={kind} />
                      </td>
                      <td className="px-6 py-3 font-mono text-right tabular-nums text-slate-900">
                        {kind === "lightning" ? `${it.distance.toFixed(1)} km` : "—"}
                      </td>
                      <td className="px-6 py-3 font-mono text-right tabular-nums text-slate-900">
                        {kind === "lightning" ? `${it.energy.toFixed(1)} kJ` : "—"}
                      </td>
                      <td className="px-6 py-3 font-mono text-right text-[11px] text-slate-400 hidden md:table-cell">
                        {it.device_id || "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </section>

        <footer className="pt-8 border-t border-slate-100 font-mono text-[10px] uppercase tracking-[0.2em] text-slate-400">
          Détecteur · AS3935 · Franklin Lightning Detector · /api/upload_storm
        </footer>
      </main>
    </div>
  );
}
