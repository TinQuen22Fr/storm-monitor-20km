import { useEffect, useState } from "react";
import { CloudSun } from "lucide-react";

function formatAge(seconds) {
  if (seconds < 60) return `${Math.max(0, Math.round(seconds))} s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min`;
  return `${(seconds / 3600).toFixed(1)} h`;
}

export const DataFreshnessBadge = ({ fetchedAt }) => {
  const [, setTick] = useState(0);

  useEffect(() => {
    const t = setInterval(() => setTick((v) => v + 1), 15_000);
    return () => clearInterval(t);
  }, []);

  const ageS = fetchedAt ? (Date.now() - new Date(fetchedAt).getTime()) / 1000 : null;
  const stale = ageS == null || ageS >= 30 * 60;
  const warn = !stale && ageS >= 5 * 60;

  const cls = stale
    ? "bg-red-600 text-white"
    : warn
      ? "bg-amber-400 text-slate-900"
      : "bg-emerald-500 text-white";

  return (
    <div
      data-testid="data-freshness-badge"
      className={`absolute top-3 left-1/2 -translate-x-1/2 z-[1000] flex items-center gap-1.5 px-2.5 py-1 rounded-full shadow-md font-mono text-[10px] uppercase tracking-wider ${cls}`}
      title="Âge des données Open-Meteo (zones convectives). Rouge = données périmées ou quota API épuisé."
    >
      <CloudSun className="w-3 h-3" strokeWidth={2.5} />
      {ageS == null ? "Open-Meteo · aucune donnée" : `Open-Meteo · il y a ${formatAge(ageS)}`}
    </div>
  );
};

export default DataFreshnessBadge;
