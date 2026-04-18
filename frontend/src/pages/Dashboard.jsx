import { useCallback, useEffect, useRef, useState } from "react";
import { Bell, BellOff, RefreshCw, Zap } from "lucide-react";
import MapPanel from "@/components/MapPanel";
import AlertBanner from "@/components/AlertBanner";
import CurrentConditions from "@/components/CurrentConditions";
import CapeGauge from "@/components/CapeGauge";
import HistoryChart from "@/components/HistoryChart";
import ForecastChart from "@/components/ForecastChart";
import AuthDialog from "@/components/AuthDialog";
import FavoritesList from "@/components/FavoritesList";
import { getCurrent, getForecast, getHistory, getStrikes, getZones, LOURDES } from "@/lib/api";
import * as notif from "@/lib/notifications";

const REFRESH_MS = 120_000; // 2 min for weather
const STRIKES_MS = 15_000; // 15 s for lightning
const STRIKES_WINDOW_S = 3600; // keep last 60 min strikes on map

export default function Dashboard() {
  const [center, setCenter] = useState({ lat: LOURDES.lat, lon: LOURDES.lon, name: "Lourdes" });
  const [current, setCurrent] = useState(null);
  const [forecast, setForecast] = useState(null);
  const [history, setHistory] = useState(null);
  const [zones, setZones] = useState(null);
  const [strikes, setStrikes] = useState([]);
  const [refreshing, setRefreshing] = useState(false);
  const [lastFetch, setLastFetch] = useState(null);
  const [error, setError] = useState(null);
  const [fullscreen, setFullscreen] = useState(false);
  const [notifEnabled, setNotifEnabled] = useState(notif.isEnabled());

  const prevStormActive = useRef(false);
  const seenStrikeTs = useRef(new Set());

  const loadWeather = useCallback(async () => {
    setRefreshing(true);
    setError(null);
    try {
      const [c, f, h, z] = await Promise.all([
        getCurrent(center.lat, center.lon),
        getForecast(center.lat, center.lon),
        getHistory(center.lat, center.lon),
        getZones(center.lat, center.lon, LOURDES.radius),
      ]);
      setCurrent(c);
      setForecast(f);
      setHistory(h);
      setZones(z);
      setLastFetch(new Date().toISOString());

      // Notification on storm activation
      if (z.storm_active && !prevStormActive.current) {
        notif.notify("Alerte orage — Lourdes", `Activité orageuse détectée (CAPE ${Math.round(z.max_cape || 0)} J/kg)`);
      }
      prevStormActive.current = z.storm_active;
    } catch (e) {
      setError("Impossible de contacter le service météo");
    } finally {
      setRefreshing(false);
    }
  }, [center.lat, center.lon]);

  const loadStrikes = useCallback(async () => {
    try {
      const since = Date.now() / 1000 - STRIKES_WINDOW_S;
      const data = await getStrikes(center.lat, center.lon, LOURDES.radius, since);
      setStrikes(data.strikes || []);

      // Notify on fresh strikes (new since last poll)
      const fresh = (data.strikes || []).filter((s) => !seenStrikeTs.current.has(s.ts));
      if (fresh.length > 0 && seenStrikeTs.current.size > 0) {
        const closest = fresh.reduce((m, s) => (s.distance_km < m.distance_km ? s : m), fresh[0]);
        notif.notify(
          `⚡ ${fresh.length} impact${fresh.length > 1 ? "s" : ""} de foudre`,
          `Le plus proche à ${closest.distance_km.toFixed(1)} km de Lourdes`
        );
      }
      for (const s of data.strikes || []) seenStrikeTs.current.add(s.ts);
      // Trim set
      if (seenStrikeTs.current.size > 2000) {
        seenStrikeTs.current = new Set([...seenStrikeTs.current].slice(-1000));
      }
    } catch { /* silent */ }
  }, [center.lat, center.lon]);

  useEffect(() => {
    loadWeather();
    loadStrikes();
    const wt = setInterval(loadWeather, REFRESH_MS);
    const st = setInterval(loadStrikes, STRIKES_MS);
    return () => {
      clearInterval(wt);
      clearInterval(st);
    };
  }, [loadWeather, loadStrikes]);

  const toggleNotif = async () => {
    if (notifEnabled) {
      notif.disable();
      setNotifEnabled(false);
    } else {
      const ok = await notif.enable();
      setNotifEnabled(ok);
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 h-screen w-full overflow-hidden bg-slate-50" data-testid="dashboard-root">
      {/* Sidebar */}
      <aside
        className={`${
          fullscreen ? "hidden" : "col-span-1 lg:col-span-4"
        } h-full overflow-y-auto bg-white border-r border-slate-200 relative z-10 flex flex-col`}
        data-testid="sidebar"
      >
        <AlertBanner
          stormActive={zones?.storm_active}
          maxCape={zones?.max_cape}
          maxLp={zones?.max_lightning_potential}
          fetchedAt={lastFetch}
        />

        <div className="px-6 pt-8 pb-6 border-b border-slate-100 grain relative shrink-0">
          <div className="flex items-start justify-between mb-4">
            <div className="flex items-center gap-2">
              <Zap className="w-4 h-4 text-slate-900" strokeWidth={2.5} />
              <span className="font-mono text-[10px] uppercase tracking-[0.3em] text-slate-500 font-semibold">
                Orage · Lourdes
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="live-dot" />
              <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-red-600 font-semibold">
                En direct
              </span>
            </div>
          </div>
          <h1
            className="font-heading text-4xl md:text-5xl font-black tracking-tighter text-slate-900 leading-[0.95]"
            data-testid="app-title"
          >
            Suivi d'orage<br />
            <span className="text-slate-400">en temps réel.</span>
          </h1>
          <p className="text-sm text-slate-500 mt-4 leading-relaxed max-w-xs">
            Surveillance de l'activité électrique et convective dans un rayon
            de <span className="font-mono text-slate-900">20&nbsp;km</span> autour de Lourdes.
          </p>

          <div className="mt-6 flex items-center justify-between font-mono text-[10px] uppercase tracking-[0.2em] text-slate-400">
            <button
              onClick={loadWeather}
              disabled={refreshing}
              className="flex items-center gap-2 hover:text-slate-900 transition-colors disabled:opacity-50"
              data-testid="refresh-button"
            >
              <RefreshCw className={`w-3 h-3 ${refreshing ? "animate-spin" : ""}`} />
              {refreshing ? "Actualisation…" : "Actualiser"}
            </button>
            <span data-testid="last-fetch-time">
              {lastFetch
                ? new Date(lastFetch).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" })
                : "--:--"}
            </span>
          </div>

          {/* Notifications toggle */}
          <button
            onClick={toggleNotif}
            className={`mt-4 w-full flex items-center justify-between px-4 h-10 border transition-colors ${
              notifEnabled
                ? "bg-slate-900 text-white border-slate-900"
                : "bg-white text-slate-900 border-slate-300 hover:border-slate-900"
            }`}
            data-testid="toggle-notifications"
          >
            <span className="flex items-center gap-2">
              {notifEnabled ? <Bell className="w-4 h-4" strokeWidth={1.8} /> : <BellOff className="w-4 h-4" strokeWidth={1.8} />}
              <span className="font-mono text-[10px] uppercase tracking-[0.2em]">
                {notifEnabled ? "Alertes actives" : "Activer les alertes"}
              </span>
            </span>
            <span
              className={`w-8 h-4 rounded-full relative transition-colors ${
                notifEnabled ? "bg-white/20" : "bg-slate-200"
              }`}
            >
              <span
                className={`absolute top-0.5 w-3 h-3 rounded-full transition-all ${
                  notifEnabled ? "left-[18px] bg-white" : "left-0.5 bg-slate-400"
                }`}
              />
            </span>
          </button>

          {error && (
            <div className="mt-4 p-3 bg-red-50 border border-red-200 text-xs text-red-800 font-mono" data-testid="error-banner">
              {error}
            </div>
          )}
        </div>

        <div className="px-6 py-6 space-y-6 flex-1 shrink-0">
          <div>
            <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400 mb-3">
              Conditions actuelles
            </div>
            <CurrentConditions current={current} />
          </div>

          <CapeGauge
            cape={current?.cape ?? zones?.max_cape}
            lightningPotential={current?.lightning_potential ?? zones?.max_lightning_potential}
          />

          <HistoryChart hourly={history?.hourly || []} />
          <ForecastChart hourly={forecast?.hourly || []} />

          <div className="space-y-4">
            <AuthDialog />
            <FavoritesList onSelect={setCenter} activeCenter={center} />
          </div>

          <footer className="pt-6 border-t border-slate-100 text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400 space-y-1">
            <div>Météo · Open-Meteo</div>
            <div>Foudre · Blitzortung.org</div>
          </footer>
        </div>
      </aside>

      {/* Map area */}
      <section
        className={`${fullscreen ? "col-span-1 lg:col-span-12" : "col-span-1 lg:col-span-8"} h-full relative z-0`}
        data-testid="map-area"
      >
        <MapPanel
          zones={zones?.zones || []}
          strikes={strikes}
          center={center}
          radiusKm={LOURDES.radius}
          fullscreen={fullscreen}
          onToggleFullscreen={() => setFullscreen((v) => !v)}
        />
      </section>
    </div>
  );
}
