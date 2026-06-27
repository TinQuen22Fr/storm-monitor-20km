import { useEffect, useState } from "react";
import { LineChart, Line, Tooltip, ResponsiveContainer, XAxis, YAxis, CartesianGrid, ReferenceLine } from "recharts";
import { Loader2 } from "lucide-react";
import { getSevereProfile } from "@/lib/api";

/**
 * Vertical temperature profile chart.
 * X = temperature, Y = altitude (meters, log-ish via pressure level mapping).
 * Y axis is inverted so altitude goes UP, like all atmospheric soundings.
 */
export default function VerticalProfileChart({ lat, lon, name = "" }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancel = false;
    setLoading(true);
    setError(null);
    getSevereProfile(lat, lon, 0)
      .then((d) => { if (!cancel) setData(d); })
      .catch((e) => {
        if (!cancel) {
          const s = e?.response?.status;
          setError(s === 404 ? "Endpoint absent (404)" : "Erreur de chargement");
        }
      })
      .finally(() => { if (!cancel) setLoading(false); });
    return () => { cancel = true; };
  }, [lat, lon]);

  const points = (data?.points || []).map((p) => ({
    t: p.temperature_c,
    h: p.height_m,
    label: p.level,
  }));

  // Dry adiabatic reference line (decrease of 9.8°C / 1000 m) anchored at surface
  const surfaceT = points[0]?.t ?? 20;
  const adiabat = points.map((p) => ({
    h: p.h,
    adiabat_t: surfaceT - (9.8 * p.h) / 1000,
  }));
  // Merge for Recharts
  const merged = points.map((p, i) => ({
    ...p,
    adiabat_t: adiabat[i].adiabat_t,
  }));

  return (
    <div className="border border-slate-200 bg-white p-5" data-testid="vertical-profile">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div>
          <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400">
            Profil vertical T° · {name || ""}
          </div>
          <div className="font-mono text-[10px] text-slate-500 mt-0.5">
            Surface → 300 hPa · trait plein = profil prévu · pointillé = adiabatique sèche
          </div>
        </div>
        {loading && <Loader2 className="w-4 h-4 animate-spin text-slate-400" />}
      </div>

      {error && (
        <div className="text-xs text-red-700 bg-red-50 border border-red-200 p-2 font-mono">{error}</div>
      )}

      {merged.length > 0 ? (
        <ResponsiveContainer width="100%" height={340}>
          <LineChart
            data={merged}
            layout="vertical"
            margin={{ top: 10, right: 20, left: 0, bottom: 10 }}
          >
            <CartesianGrid strokeDasharray="2 4" stroke="#E2E8F0" />
            <XAxis
              type="number"
              domain={[-50, 35]}
              tick={{ fontSize: 10, fontFamily: "monospace", fill: "#94A3B8" }}
              unit="°C"
              tickCount={9}
            />
            <YAxis
              type="number"
              dataKey="h"
              domain={[0, 10000]}
              ticks={[0, 1500, 3000, 5500, 9200]}
              tick={{ fontSize: 9, fontFamily: "monospace", fill: "#94A3B8" }}
              tickFormatter={(v) => {
                const map = { 0: "surface", 1500: "850 hPa", 3000: "700 hPa", 5500: "500 hPa", 9200: "300 hPa" };
                return map[v] || `${v} m`;
              }}
              width={70}
            />
            <ReferenceLine x={0} stroke="#3B82F6" strokeDasharray="3 3" label={{ value: "0°C", fontSize: 9, fill: "#3B82F6", position: "top" }} />
            <Tooltip
              contentStyle={{ fontSize: 11, fontFamily: "monospace", background: "#0F172A", color: "#fff", border: "none" }}
              labelStyle={{ color: "#94A3B8" }}
              labelFormatter={(v) => `${v} m`}
              formatter={(val, n) => {
                if (n === "t") return [val?.toFixed(1) + "°C", "T° observée"];
                if (n === "adiabat_t") return [val?.toFixed(1) + "°C", "Adiabatique sèche"];
                return [val, n];
              }}
            />
            <Line
              type="monotone"
              dataKey="adiabat_t"
              stroke="#94A3B8"
              strokeWidth={1.2}
              strokeDasharray="3 3"
              dot={false}
            />
            <Line
              type="monotone"
              dataKey="t"
              stroke="#DC2626"
              strokeWidth={2.5}
              dot={{ r: 4, fill: "#DC2626", stroke: "#fff", strokeWidth: 1.5 }}
            />
          </LineChart>
        </ResponsiveContainer>
      ) : !loading ? (
        <div className="h-[200px] flex items-center justify-center text-xs text-slate-400 font-mono">
          Pas de données
        </div>
      ) : null}

      {/* Table of values */}
      {merged.length > 0 && (
        <div className="mt-4 grid grid-cols-4 sm:grid-cols-7 gap-1.5 text-[10px] font-mono" data-testid="profile-table">
          {merged.map((p) => (
            <div key={p.label} className="border border-slate-200 p-1.5 text-center">
              <div className="text-[9px] uppercase tracking-[0.1em] text-slate-400">{p.label}</div>
              <div className="text-slate-900 tabular-nums mt-0.5">
                {p.t != null ? `${p.t.toFixed(1)}°C` : "—"}
              </div>
              <div className="text-[9px] text-slate-400 tabular-nums">{p.h}m</div>
            </div>
          ))}
        </div>
      )}

      <p className="mt-3 text-[10px] text-slate-500 leading-relaxed">
        L'<strong>adiabatique sèche</strong> (pointillés gris) montre comment une parcelle d'air sèche se refroidirait
        en montant (-9.8°C/km). Si le profil prévu (rouge) est <em>plus froid</em> que l'adiabatique, l'atmosphère
        est instable et favorable aux orages.
      </p>
    </div>
  );
}
