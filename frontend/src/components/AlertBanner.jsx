import { AlertTriangle, ShieldCheck } from "lucide-react";

export default function AlertBanner({ stormActive, maxCape, maxLp, fetchedAt }) {
  const formatted = fetchedAt
    ? new Date(fetchedAt).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" })
    : "--:--:--";

  if (stormActive) {
    return (
      <div
        className="sticky top-0 z-20 backdrop-blur-xl bg-red-600/10 border-b border-red-600/30 px-6 py-5"
        data-testid="alert-banner-storm"
      >
        <div className="flex items-start gap-4">
          <AlertTriangle className="w-6 h-6 text-red-600 shrink-0 mt-0.5" strokeWidth={2.5} />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span className="live-dot" />
              <span className="font-mono text-[10px] uppercase tracking-[0.25em] text-red-700 font-semibold">
                Alerte · {formatted}
              </span>
            </div>
            <div className="font-heading text-xl font-black text-red-900 leading-tight tracking-tight">
              Activité orageuse détectée
            </div>
            <div className="font-mono text-[11px] text-red-800/80 mt-2">
              CAPE max <b>{Math.round(maxCape || 0)}</b> J/kg · LPI max <b>{(maxLp || 0).toFixed(1)}</b>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      className="sticky top-0 z-20 backdrop-blur-xl bg-emerald-600/5 border-b border-emerald-600/20 px-6 py-5"
      data-testid="alert-banner-calm"
    >
      <div className="flex items-start gap-4">
        <ShieldCheck className="w-6 h-6 text-emerald-600 shrink-0 mt-0.5" strokeWidth={2} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="w-2 h-2 rounded-full bg-emerald-500" />
            <span className="font-mono text-[10px] uppercase tracking-[0.25em] text-emerald-700 font-semibold">
              Calme · {formatted}
            </span>
          </div>
          <div className="font-heading text-xl font-black text-slate-900 leading-tight tracking-tight">
            Ciel dégagé à modérément instable
          </div>
          <div className="font-mono text-[11px] text-slate-500 mt-2">
            Aucune activité orageuse dans un rayon de 20 km
          </div>
        </div>
      </div>
    </div>
  );
}
