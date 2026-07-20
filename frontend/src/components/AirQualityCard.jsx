import { useEffect, useState } from "react";
import { Loader2, Leaf } from "lucide-react";
import { getAirQuality } from "@/lib/api";

const CAT_STYLES = {
  good: { bg: "bg-emerald-500", text: "text-emerald-700", bar: "#10B981" },
  moderate: { bg: "bg-yellow-400", text: "text-yellow-700", bar: "#EAB308" },
  usg: { bg: "bg-orange-500", text: "text-orange-700", bar: "#F97316" },
  unhealthy: { bg: "bg-red-500", text: "text-red-700", bar: "#EF4444" },
  "very unhealthy": { bg: "bg-purple-600", text: "text-purple-700", bar: "#9333EA" },
  hazardous: { bg: "bg-rose-900", text: "text-rose-900", bar: "#881337" },
};

const POLLUTANT_LABELS = {
  o3: "Ozone (O₃)",
  "pm2.5": "Particules PM2.5",
  pm10: "Particules PM10",
  co: "Monoxyde carbone",
  no2: "Dioxyde azote",
  so2: "Dioxyde soufre",
};

export default function AirQualityCard({ lat, lon, name }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancel = false;
    setLoading(true);
    setError(false);
    getAirQuality(lat, lon)
      .then((d) => { if (!cancel) setData(d); })
      .catch(() => { if (!cancel) setError(true); })
      .finally(() => { if (!cancel) setLoading(false); });
    return () => { cancel = true; };
  }, [lat, lon]);

  const style = CAT_STYLES[data?.category?.toLowerCase()] || CAT_STYLES.moderate;

  return (
    <div className="border border-slate-200 bg-white p-5" data-testid="airquality-card">
      <div className="flex items-start justify-between mb-3 gap-3">
        <div>
          <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400 flex items-center gap-1.5">
            <Leaf className="w-3 h-3" /> Qualité de l&apos;air · {name}
          </div>
          <div className="font-mono text-[10px] text-slate-500 mt-0.5">
            indice AQI (US EPA) · dominant + détail polluants
          </div>
        </div>
        {data && (
          <div className="text-right" data-testid="airquality-aqi-badge">
            <div className={`inline-flex items-center justify-center w-14 h-14 ${style.bg} text-white font-mono text-xl font-semibold tabular-nums`}>
              {data.aqi ?? "—"}
            </div>
            <div className={`font-mono text-[10px] uppercase tracking-[0.15em] mt-1 ${style.text}`}>
              {data.category_fr || "—"}
            </div>
          </div>
        )}
      </div>

      {loading && (
        <div className="py-8 flex justify-center">
          <Loader2 className="w-5 h-5 animate-spin text-slate-400" />
        </div>
      )}
      {error && !loading && (
        <div className="py-4 text-xs font-mono text-slate-500" data-testid="airquality-error">
          Qualité de l&apos;air indisponible (Xweather non configuré ou erreur réseau).
        </div>
      )}

      {data && !loading && (
        <>
          <div className="space-y-1.5" data-testid="airquality-pollutants">
            {(data.pollutants || []).map((p) => {
              const ps = CAT_STYLES[p.category?.toLowerCase()] || CAT_STYLES.moderate;
              const isDominant = p.type === data.dominant;
              return (
                <div key={p.type} className="flex items-center gap-2">
                  <span className={`font-mono text-[10px] w-32 shrink-0 ${isDominant ? "text-slate-900 font-semibold" : "text-slate-500"}`}>
                    {POLLUTANT_LABELS[p.type] || p.type}
                    {isDominant && " ◂"}
                  </span>
                  <div className="flex-1 h-2 bg-slate-100 overflow-hidden">
                    <div
                      className="h-full transition-[width]"
                      style={{ width: `${Math.min(100, (p.aqi ?? 0) / 3)}%`, background: ps.bar }}
                    />
                  </div>
                  <span className="font-mono text-[10px] tabular-nums text-slate-700 w-8 text-right">
                    {p.aqi ?? "—"}
                  </span>
                </div>
              );
            })}
          </div>
          <div className="mt-3 pt-2 border-t border-slate-100 font-mono text-[9px] uppercase tracking-[0.2em] text-slate-400">
            Source · Xweather (Vaisala) · maj toutes les 30 min
          </div>
        </>
      )}
    </div>
  );
}
