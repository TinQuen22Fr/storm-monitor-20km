import { useCallback, useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import { Copy, Database, RefreshCw, Zap } from "lucide-react";
import { toast } from "sonner";
import NavTabs from "@/components/NavTabs";
import { api } from "@/lib/api";
import { fmtLocal, fmtLocalTime } from "@/lib/timeFormat";

const sampleCurl = (apiBase) =>
  `curl -X POST ${apiBase}/api/upload_storm \\
  -H "Content-Type: application/json" \\
  -H "X-API-Key: VOTRE_CLE_API" \\
  -d '{"distance": 5.4, "energy": 28.3, "timestamp": "${new Date().toISOString()}"}'`;

function StatTile({ label, value, unit, testId }) {
  return (
    <div className="border border-slate-200 bg-white p-6" data-testid={testId}>
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

export default function History() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await api.get("/storm_uploads");
      setItems(data.items || []);
    } catch (e) {
      setError("Impossible de charger les données stockées");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Order oldest -> newest for time-series charts
  const chrono = [...items].sort((a, b) => a.timestamp.localeCompare(b.timestamp));
  const series = chrono.map((it) => ({
    t: new Date(it.timestamp).getTime(),
    label: fmtLocal(it.timestamp, {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    }),
    energy: it.energy,
    distance: it.distance,
  }));

  const totalEnergy = series.reduce((s, d) => s + d.energy, 0);
  const avgDistance = series.length
    ? series.reduce((s, d) => s + d.distance, 0) / series.length
    : 0;
  const maxEnergy = series.length ? Math.max(...series.map((d) => d.energy)) : 0;

  // Distance histogram buckets (0-10, 10-20, ...)
  const bucketSize = 10;
  const buckets = {};
  for (const d of series) {
    const b = Math.floor(d.distance / bucketSize) * bucketSize;
    const key = `${b}-${b + bucketSize} km`;
    buckets[key] = (buckets[key] || 0) + 1;
  }
  const histogram = Object.entries(buckets)
    .map(([range, count]) => ({ range, count }))
    .sort((a, b) => parseInt(a.range) - parseInt(b.range));

  const apiBase = process.env.REACT_APP_BACKEND_URL;
  const copyCurl = async () => {
    try {
      await navigator.clipboard.writeText(sampleCurl(apiBase));
      toast.success("Commande curl copiée");
    } catch {
      toast.error("Impossible de copier");
    }
  };

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
    <div className="min-h-screen w-full bg-slate-50/70" data-testid="history-page">
      {/* Header */}
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-8 py-6 flex items-center justify-between gap-6">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Zap className="w-4 h-4 text-slate-900" strokeWidth={2.5} />
              <span className="font-mono text-[10px] uppercase tracking-[0.3em] text-slate-500 font-semibold">
                Orage · Lourdes
              </span>
            </div>
            <h1 className="font-heading text-3xl font-black tracking-tighter text-slate-900">
              Historique · Données reçues
            </h1>
          </div>
          <div className="w-64 shrink-0">
            <NavTabs variant="inline" />
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-8 py-10 space-y-8">
        {/* Stats */}
        <section className="grid grid-cols-1 md:grid-cols-4 gap-0 -m-px">
          <StatTile label="Événements" value={series.length} testId="stat-count" />
          <StatTile
            label="Énergie totale"
            value={totalEnergy.toFixed(1)}
            unit="kJ"
            testId="stat-total-energy"
          />
          <StatTile
            label="Énergie max"
            value={maxEnergy.toFixed(1)}
            unit="kJ"
            testId="stat-max-energy"
          />
          <StatTile
            label="Distance moy."
            value={avgDistance.toFixed(1)}
            unit="km"
            testId="stat-avg-distance"
          />
        </section>

        {/* Controls */}
        <section className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <button
              onClick={load}
              disabled={loading}
              className="flex items-center gap-2 px-4 h-10 border border-slate-300 bg-white text-slate-900 hover:bg-slate-900 hover:text-white hover:border-slate-900 transition-colors font-mono text-[10px] uppercase tracking-[0.2em] disabled:opacity-50"
              data-testid="reload-history"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} strokeWidth={1.8} />
              {loading ? "Chargement…" : "Recharger"}
            </button>
            <button
              onClick={copyCurl}
              className="flex items-center gap-2 px-4 h-10 border border-slate-300 bg-white text-slate-900 hover:bg-slate-900 hover:text-white hover:border-slate-900 transition-colors font-mono text-[10px] uppercase tracking-[0.2em]"
              data-testid="copy-curl"
            >
              <Copy className="w-4 h-4" strokeWidth={1.8} />
              Copier commande curl
            </button>
          </div>
          <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-400 flex items-center gap-2">
            <Database className="w-3 h-3" /> storm_data.json
          </span>
        </section>

        {error && (
          <div className="p-4 border border-red-200 bg-red-50 text-sm text-red-800 font-mono">
            {error}
          </div>
        )}

        {series.length === 0 && !loading && (
          <section className="border border-slate-200 bg-white p-12 text-center">
            <div className="font-heading text-2xl font-bold text-slate-900 mb-2">
              Aucune donnée enregistrée
            </div>
            <p className="text-sm text-slate-500 mb-6">
              Envoyez votre premier événement d'orage via l'API sécurisée pour voir les graphiques.
            </p>
            <pre
              className="text-left bg-slate-900 text-slate-100 font-mono text-[11px] leading-relaxed p-5 overflow-x-auto max-w-2xl mx-auto"
              data-testid="curl-example"
            >
              <code>{sampleCurl(apiBase)}</code>
            </pre>
            <p className="text-[11px] font-mono uppercase tracking-wider text-slate-400 mt-4">
              Clé API attendue dans le header{" "}
              <span className="text-slate-900">X-API-Key</span>
            </p>
          </section>
        )}

        {series.length > 0 && (
          <>
            {/* Energy over time */}
            <section className="border border-slate-200 bg-white p-8" data-testid="chart-energy-time">
              <div className="flex items-start justify-between mb-6">
                <div>
                  <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400 mb-1">
                    Série temporelle
                  </div>
                  <h2 className="font-heading text-xl font-bold text-slate-900">
                    Énergie au fil du temps
                  </h2>
                </div>
                <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-400">
                  unité : kJ
                </span>
              </div>
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={series}>
                    <defs>
                      <linearGradient id="energyFill" x1="0" y1="0" x2="0" y2="1">
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
                      interval={Math.max(0, Math.floor(series.length / 8))}
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
                      fill="url(#energyFill)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </section>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-0 -m-px">
              {/* Distance scatter */}
              <section
                className="border border-slate-200 bg-white p-8"
                data-testid="chart-distance-scatter"
              >
                <div className="flex items-start justify-between mb-6">
                  <div>
                    <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400 mb-1">
                      Corrélation
                    </div>
                    <h2 className="font-heading text-xl font-bold text-slate-900">
                      Distance × Énergie
                    </h2>
                  </div>
                  <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-400">
                    {series.length} points
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
                      <ZAxis range={[60, 60]} />
                      <Tooltip {...chartTooltip} cursor={{ strokeDasharray: "3 3" }} />
                      <Scatter data={series} fill="#0F172A" />
                    </ScatterChart>
                  </ResponsiveContainer>
                </div>
              </section>

              {/* Distance histogram */}
              <section
                className="border border-slate-200 bg-white p-8"
                data-testid="chart-distance-histogram"
              >
                <div className="flex items-start justify-between mb-6">
                  <div>
                    <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400 mb-1">
                      Distribution
                    </div>
                    <h2 className="font-heading text-xl font-bold text-slate-900">
                      Par tranche de distance
                    </h2>
                  </div>
                  <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-400">
                    tranche : 10 km
                  </span>
                </div>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={histogram}>
                      <CartesianGrid strokeDasharray="2 4" stroke="#E2E8F0" vertical={false} />
                      <XAxis
                        dataKey="range"
                        tick={{ fontSize: 10, fontFamily: "IBM Plex Mono", fill: "#94A3B8" }}
                        axisLine={{ stroke: "#E2E8F0" }}
                        tickLine={false}
                      />
                      <YAxis
                        allowDecimals={false}
                        tick={{ fontSize: 10, fontFamily: "IBM Plex Mono", fill: "#94A3B8" }}
                        axisLine={false}
                        tickLine={false}
                      />
                      <Tooltip {...chartTooltip} cursor={{ fill: "rgba(15,23,42,0.04)" }} />
                      <Bar dataKey="count" radius={0}>
                        {histogram.map((entry, i) => (
                          <Cell key={i} fill={i % 2 === 0 ? "#0F172A" : "#334155"} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </section>
            </div>

            {/* Records table */}
            <section className="border border-slate-200 bg-white" data-testid="records-table">
              <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
                <h2 className="font-heading text-sm font-bold text-slate-900">Derniers événements</h2>
                <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-400">
                  {Math.min(items.length, 25)} / {items.length}
                </span>
              </div>
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-slate-50 text-[10px] font-mono uppercase tracking-wider text-slate-400">
                    <th className="text-left px-6 py-2.5 font-medium">Timestamp</th>
                    <th className="text-right px-6 py-2.5 font-medium">Distance</th>
                    <th className="text-right px-6 py-2.5 font-medium">Énergie</th>
                    <th className="text-right px-6 py-2.5 font-medium">Reçu à</th>
                  </tr>
                </thead>
                <tbody>
                  {items.slice(0, 25).map((it) => (
                    <tr key={it.id} className="border-t border-slate-100 hover:bg-slate-50">
                      <td className="px-6 py-3 font-mono text-slate-900">
                        {fmtLocal(it.timestamp)}
                      </td>
                      <td className="px-6 py-3 font-mono text-right tabular-nums text-slate-900">
                        {it.distance.toFixed(2)} km
                      </td>
                      <td className="px-6 py-3 font-mono text-right tabular-nums text-slate-900">
                        {it.energy.toFixed(2)} kJ
                      </td>
                      <td className="px-6 py-3 font-mono text-right text-[11px] text-slate-400">
                        {fmtLocalTime(it.received_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          </>
        )}

        <footer className="pt-8 border-t border-slate-100 font-mono text-[10px] uppercase tracking-[0.2em] text-slate-400">
          Source · storm_data.json (persistant, côté serveur)
        </footer>
      </main>
    </div>
  );
}
