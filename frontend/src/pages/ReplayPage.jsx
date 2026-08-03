import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, MapPin, PlayCircle, Sparkles, Video, Zap } from "lucide-react";
import NavTabs from "@/components/NavTabs";
import VideoExportDialog from "@/components/VideoExportDialog";
import { api } from "@/lib/api";
import { fmtLocal } from "@/lib/timeFormat";

/**
 * Replay page — lists detected "storm bursts" from the last 24h strike buffer
 * and lets the user relaunch a dashboard replay by passing ?replay=start:end
 * in the URL. The Dashboard reacts to this and auto-plays the timeline.
 *
 * Also exposes reconstructed "demo" episodes (Pyrenees-type) for showcasing the
 * Replay + MP4 export features when no live storm is active.
 */
export default function ReplayPage() {
  const [events, setEvents] = useState(null);
  const [demos, setDemos] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [videoOpen, setVideoOpen] = useState(false);
  const [videoEvent, setVideoEvent] = useState(null);
  const [videoIsDemo, setVideoIsDemo] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    let cancel = false;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const [evRes, demosRes] = await Promise.all([
          api.get("/replay/events"),
          api.get("/replay/demos"),
        ]);
        if (!cancel) {
          setEvents(evRes.data.events || []);
          setDemos(demosRes.data.demos || []);
        }
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
    const pre = Math.max(ev.start_ts - 5 * 60, Math.floor(Date.now() / 1000) - 24 * 3600);
    navigate(`/?replay=${pre}:${ev.end_ts}`);
  };

  const exportVideo = (ev, isDemo = false) => {
    setVideoEvent(ev);
    setVideoIsDemo(isDemo);
    setVideoOpen(true);
  };

  const fmtTime = (ts) =>
    fmtLocal(ts, {
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
    <div className="min-h-screen bg-slate-50/70" data-testid="replay-page">
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
                <span>"Exporter MP4" génère une vidéo partageable (WhatsApp, Twitter) en quelques secondes.</span>
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
        <main className="lg:col-span-2 flex flex-col gap-6" data-testid="replay-events-list">
          {/* DEMO section — always visible to showcase features */}
          {demos && demos.length > 0 && (
            <section data-testid="replay-demo-section">
              <div className="flex items-center gap-2 mb-3">
                <Sparkles className="w-3.5 h-3.5 text-violet-600" strokeWidth={2.4} />
                <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-violet-700 font-semibold">
                  Démos · reconstitutions Pyrénées
                </span>
              </div>
              <div className="text-[11px] text-slate-500 mb-3 leading-relaxed">
                Épisodes scénarisés (données plausibles reconstruites) pour tester le Replay et l'export vidéo même en temps calme.
              </div>
              <div className="flex flex-col gap-3">
                {demos.map((dem, idx) => (
                  <div
                    key={dem.id}
                    className="border border-violet-200 bg-gradient-to-br from-violet-50 to-white p-5"
                    data-testid={`replay-demo-${idx}`}
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <span className="font-mono text-[10px] uppercase tracking-[0.18em] px-2 py-0.5 bg-violet-700 text-white">
                        Démo
                      </span>
                      <span className="font-mono text-[10px] text-slate-500 tabular-nums">
                        {fmtTime(dem.start_ts)} → {fmtTime(dem.end_ts)}
                      </span>
                    </div>
                    <div className="font-heading text-lg font-black tracking-tight text-slate-900 leading-tight mb-1">
                      {dem.label}
                    </div>
                    <div className="text-sm text-slate-600 mb-2">{dem.subtitle}</div>
                    <div className="text-[12px] text-slate-500 mb-3 leading-relaxed">
                      {dem.description}
                    </div>
                    <div className="flex items-center gap-3 mb-4 text-[11px] font-mono text-slate-500 tabular-nums">
                      <span className="flex items-center gap-1">
                        <Zap className="w-3 h-3" strokeWidth={2.2} />
                        {dem.strike_count} impacts
                      </span>
                      <span>{dem.duration_min} min</span>
                      <span>pic {dem.peak_count_10min}/10min</span>
                    </div>
                    <div className="flex flex-col sm:flex-row gap-2">
                      <button
                        type="button"
                        onClick={() => playEvent(dem)}
                        className="flex-1 h-9 flex items-center justify-center gap-2 bg-violet-700 text-white hover:bg-violet-900 transition-colors font-mono text-[10px] uppercase tracking-[0.18em]"
                        data-testid={`replay-demo-play-${idx}`}
                      >
                        <PlayCircle className="w-3.5 h-3.5" strokeWidth={2.2} />
                        Rejouer dans le Direct
                      </button>
                      <button
                        type="button"
                        onClick={() => exportVideo(dem, true)}
                        className="flex-1 h-9 flex items-center justify-center gap-2 border border-violet-700 text-violet-700 hover:bg-violet-700 hover:text-white transition-colors font-mono text-[10px] uppercase tracking-[0.18em]"
                        data-testid={`replay-demo-video-${idx}`}
                      >
                        <Video className="w-3.5 h-3.5" strokeWidth={2.2} />
                        Exporter MP4
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Real events section */}
          <section>
            {(events?.length || 0) > 0 && (
              <div className="flex items-center gap-2 mb-3">
                <Zap className="w-3.5 h-3.5 text-slate-900" strokeWidth={2.4} />
                <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-slate-700 font-semibold">
                  Événements réels · 24h
                </span>
              </div>
            )}
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
                  Aucun épisode réel détecté
                </div>
                <div className="text-sm text-slate-500 leading-relaxed max-w-md mx-auto">
                  Pas d&apos;orage notable dans les dernières 24 heures autour de Lourdes.
                  Testez le Replay + MP4 avec les démos ci-dessus, ou consultez la{" "}
                  <Link to="/vigilance" className="text-slate-900 font-medium underline underline-offset-2">
                    carte de vigilance
                  </Link>
                  .
                </div>
              </div>
            )}
            <div className="flex flex-col gap-3">
              {!loading && events?.map((ev, idx) => {
                const intensity = intensityLabel(ev.peak_count_10min);
                return (
                  <div
                    key={ev.id}
                    className="group border border-slate-200 bg-white p-5 hover:border-slate-900 transition-all"
                    data-testid={`replay-event-${idx}`}
                  >
                    <div className="flex flex-col sm:flex-row sm:items-center gap-4">
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
                    </div>
                    <div className="flex flex-col sm:flex-row gap-2 mt-4">
                      <button
                        type="button"
                        onClick={() => playEvent(ev)}
                        className="flex-1 h-9 flex items-center justify-center gap-2 bg-slate-900 text-white hover:bg-slate-700 transition-colors font-mono text-[10px] uppercase tracking-[0.18em]"
                        data-testid={`replay-event-play-${idx}`}
                      >
                        <PlayCircle className="w-3.5 h-3.5" strokeWidth={2.2} />
                        Rejouer
                        <ArrowRight className="w-3 h-3 opacity-60 group-hover:translate-x-0.5 transition-transform" strokeWidth={2.4} />
                      </button>
                      <button
                        type="button"
                        onClick={() => exportVideo({
                          ...ev,
                          label: `Orage du ${fmtTime(ev.start_ts)} (${ev.strike_count} impacts)`,
                        }, false)}
                        className="flex-1 h-9 flex items-center justify-center gap-2 border border-slate-900 text-slate-900 hover:bg-slate-900 hover:text-white transition-colors font-mono text-[10px] uppercase tracking-[0.18em]"
                        data-testid={`replay-event-video-${idx}`}
                      >
                        <Video className="w-3.5 h-3.5" strokeWidth={2.2} />
                        Exporter MP4
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        </main>
      </div>

      <VideoExportDialog
        open={videoOpen}
        onClose={() => setVideoOpen(false)}
        event={videoEvent}
        isDemo={videoIsDemo}
      />
    </div>
  );
}
