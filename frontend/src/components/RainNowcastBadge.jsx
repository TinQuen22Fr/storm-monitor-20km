import { useEffect, useState } from "react";
import { CloudRain, Umbrella } from "lucide-react";
import { getRainNowcast } from "@/lib/api";

export default function RainNowcastBadge({ lat, lon, refreshTick = 0 }) {
  const [data, setData] = useState(null);

  useEffect(() => {
    let cancel = false;
    const load = () =>
      getRainNowcast(lat, lon)
        .then((d) => { if (!cancel) setData(d); })
        .catch(() => { if (!cancel) setData(null); });
    load();
    const t = setInterval(load, 5 * 60_000);
    return () => { cancel = true; clearInterval(t); };
  }, [lat, lon, refreshTick]);

  if (!data) return null;

  const raining = data.raining_now;
  const soon = !raining && data.next_rain_minutes != null && data.next_rain_minutes <= 120;

  let cls, Icon, text;
  if (raining) {
    cls = "bg-blue-600 text-white";
    Icon = CloudRain;
    text = "Pluie en cours";
  } else if (soon) {
    cls = "bg-blue-50 text-blue-800 border border-blue-200";
    Icon = Umbrella;
    text = `Pluie dans ~${data.next_rain_minutes} min · ${data.next_rain_mm.toFixed(1)} mm`;
  } else {
    cls = "bg-slate-50 text-slate-500 border border-slate-200";
    Icon = Umbrella;
    text = "Pas de pluie prévue · 2 h";
  }

  return (
    <div
      className={`flex items-center gap-2 px-3 py-2 font-mono text-[11px] ${cls}`}
      data-testid="rain-nowcast-badge"
      title="Prévision pluie 15 min — modèle AROME Météo-France 1,5 km via Open-Meteo"
    >
      <Icon className="w-3.5 h-3.5 shrink-0" strokeWidth={1.8} />
      <span>{text}</span>
      <span className="ml-auto text-[9px] uppercase tracking-[0.15em] opacity-60">AROME 15 min</span>
    </div>
  );
}
