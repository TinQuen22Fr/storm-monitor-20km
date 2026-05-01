import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, MapPin, PlayCircle, Zap } from "lucide-react";
import NavTabs from "@/components/NavTabs";
import { api } from "@/lib/api";

/**
 * Replay page — lists detected "storm bursts" from the last 24h strike buffer
 * and lets the user relaunch a dashboard replay by passing ?replay=start:end
 * in the URL. The Dashboard reacts to this and auto-plays the timeline.
 */
export default function ReplayPage() {
  const [events, setEvents] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    let cancel = false;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const { data } = await api.get("/replay/events");
        if (!cancel) setEvents(data.events || []);
      } catch (e) {
        if (!cancel) setError("Impossible de charger les épisodes");
      } finally {
        if (!cancel) setLoading(false);
      }
    };
    load();
    return () => { cancel = true; };
  }, []);

  const playEvent = (ev) => {
    // Pre-roll 5 min before the first strike so the replay builds up naturally
    const pre = Math.max(ev.start_ts - 5 * 60, Math.floor(Date.now() / 1000) - 24 * 3600);
    navigate(`/?replay=${pre}:${ev.end_ts}`);
  };

  const fmtTime = (ts) =>
    new Date(ts * 1000).toLocaleString("fr-FR", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });

  const intensityLabel = (peak) => {
    if (peak >= 30) return { label: "Sévère", color: "#991B1B", bg: "#FEE2E2" };
    if (peak >= 15) return { label: "Fort", color: "#DC2626", bg: "#FEE2E2" };
    if (peak >= 8) return { label: "Modéré", color: "#EA580C", bg: "#FFEDD5" };
    return { label: "Faible", color: "#D97706", bg: "#FEF3C7" };
  };

  return (
    <div className="min-h-screen bg-slate-50" data-testid="replay-page">
      <div className="border-b border-slate-200 bg-white">
        <div className="max-w-[1400px] mx-auto px-6 py-4 flex flex-col md:flex-row md:items-center gap-4">
          <div className="flex-1">
            <div className="font-mono text-[10px] uppercase tracking-[0.25em] text-slate-400">
              Mode replay · 24 dernières heures
            </div>
            <h1 className="font-heading text-2xl font-black tracking-tight text-slate-900">
              Rejouer un orage majeur
            </h1>
          </div>
          <div className="w-full md:w-[480px] shrink-0">
            <NavTabs />
          </div>
        </div>
      </div>

      <div className="max-w-[1400px] mx-auto px-6 py-6 grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Info side panel */}
        <aside className="lg:col-span-1 flex flex-col gap-4">
          <div className="border border-slate-200 bg-white p-5">
            <div className="font-mono text-[10px] uppercase tracking-[0.25em] text-slate-400 mb-3">
              Comment ça marche
            </div>
            <ol className="space-y-2.5 text-sm text-slate-700">
              <li className="flex gap-2.5">
                <span className="font-mono text-xs text-slate-400 shrink-0 tabular-nums">01</span>
                <span>Les orages sont détectés à partir des 24 dernières heures d'impacts de foudre.</span>
              </li>
              <li className="flex gap-2.5">
                <span className="font-mono text-xs text-slate-400 shrink-0 tabular-nums">02</span>
                <span>Une séquence = au moins 5 impacts sur un rayon de 70 km avec moins de 15 min d'écart.</span>
              </li>
              <li className="flex gap-2.5">
                <span className="font-mono text-xs text-slate-400 shrink-0 tabular-nums">03</span>
                <span>Cliquer sur "Rejouer" relance la timeline du Direct en lecture auto sur la période.</span>
              </li>
              <li className="flex gap-2.5">
                <span className="font-mono text-xs text-slate-400 shrink-0 tabular-nums">04</span>
                <span>Nuages, pluie, foudre et trajectoire sont tous synchronisés sur le curseur.</span>
              </li>
            </ol>
          </div>

          <div className="border border-slate-200 bg-white p-5">
            <div className="font-mono text-[10px] uppercase tracking-[0.25em] text-slate-400 mb-2">
              Résumé
            </div>
            <div className="flex items-baseline gap-2 mb-1">
              <span className="font-heading text-4xl font-black tracking-tight text-slate-900 tabular-nums">
                {events ? events.length : "—"}
              </span>
              <span className="font-mono text-[10px] uppercase tracking-[0.15em] text-slate-500">
                épisode{(events?.length || 0) > 1 ? "s" : ""} détecté{(events?.length || 0) > 1 ? "s" : ""}
              </span>
            </div>
            <div className="text-xs text-slate-500 leading-relaxed">
              Basé sur les strikes Blitzortung reçus dans la dernière journée autour de Lourdes.
            </div>
          </div>
        </aside>

        {/* Events list */}
        <main className="lg:col-span-2 flex flex-col gap-3" data-testid="replay-events-list">
          {loading && (
            <div className="border border-slate-200 bg-white p-8 text-center text-slate-400 font-mono text-xs uppercase tracking-[0.2em]">
              Analyse en cours…
            </div>
          )}
          {error && !loading && (
            <div className="border border-red-200 bg-red-50 p-5 text-sm text-red-700" data-testid="replay-error">
              {error}
            </div>
          )}
          {!loading && !error && events?.length === 0 && (
            <div
              className="border border-dashed border-slate-300 bg-white p-10 text-center"
              data-testid="replay-empty"
            >
              <Zap className="w-10 h-10 text-slate-300 mx-auto mb-3" strokeWidth={1.5} />
              <div className="font-heading text-xl font-black tracking-tight text-slate-900 mb-2">
                Aucun épisode détecté
              </div>
              <div className="text-sm text-slate-500 leading-relaxed max-w-md mx-auto">
                Pas d'orage notable dans les dernières 24 heures autour de Lourdes.
                Revenez après la prochaine activité — ou consultez la{" "}
                <Link to="/vigilance" className="text-slate-900 font-medium underline underline-offset-2">
                  carte de vigilance
                </Link>
                .
              </div>
            </div>
          )}
          {!loading && events?.map((ev, idx) => {
            const intensity = intensityLabel(ev.peak_count_10min);
            return (
              <button
                key={ev.id}
                type="button"
                onClick={() => playEvent(ev)}
                className="group border border-slate-200 bg-white p-5 text-left hover:border-slate-900 transition-all flex flex-col sm:flex-row sm:items-center gap-4"
                data-testid={`replay-event-${idx}`}
              >
                <div className="flex items-center gap-4 flex-1 min-w-0">
                  <div
                    className="w-12 h-12 flex items-center justify-center shrink-0 font-mono text-sm font-semibold tabular-nums"
                    style={{ background: intensity.bg, color: intensity.color }}
                  >
                    #{idx + 1}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span
                        className="font-mono text-[10px] uppercase tracking-[0.15em] px-1.5 py-0.5"
                        style={{ background: intensity.bg, color: intensity.color }}
                      >
                        {intensity.label}
                      </span>
                      <span className="font-mono text-[10px] text-slate-400 tabular-nums">
                        {fmtTime(ev.start_ts)} → {fmtTime(ev.end_ts)}
                      </span>
                    </div>
                    <div className="font-heading text-lg font-black tracking-tight text-slate-900 leading-tight">
                      {ev.strike_count} impacts · {ev.duration_min} min
                    </div>
                    <div className="flex items-center gap-3 mt-1 text-[11px] font-mono text-slate-500 tabular-nums">
                      <span className="flex items-center gap-1">
                        <Zap className="w-3 h-3" strokeWidth={2.2} />
                        pic {ev.peak_count_10min}/10min
                      </span>
                      <span className="flex items-center gap-1">
                        <MapPin className="w-3 h-3" strokeWidth={2.2} />
                        {ev.center_lat.toFixed(2)}°, {ev.center_lon.toFixed(2)}°
                      </span>
                      <span>{ev.max_distance_km} km max</span>
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0 font-mono text-[10px] uppercase tracking-[0.18em] text-slate-500 group-hover:text-slate-900 transition-colors">
                  <PlayCircle className="w-4 h-4" strokeWidth={2} />
                  Rejouer
                  <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" strokeWidth={2} />
                </div>
              </button>
            );
          })}
        </main>
      </div>
    </div>
  );
}
