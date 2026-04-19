import { useCallback, useEffect, useRef, useState } from "react";
import { Bell, BellOff, Download, RefreshCw, Zap } from "lucide-react";
import MapPanel from "@/components/MapPanel";
import AlertBanner from "@/components/AlertBanner";
import ApproachAlert from "@/components/ApproachAlert";
import Timeline from "@/components/Timeline";
import VigilanceBanner from "@/components/VigilanceBanner";
import NavTabs from "@/components/NavTabs";
import CurrentConditions from "@/components/CurrentConditions";
import CapeGauge from "@/components/CapeGauge";
import HistoryChart from "@/components/HistoryChart";
import HistoryDaysChart from "@/components/HistoryDaysChart";
import ForecastChart from "@/components/ForecastChart";
import StormRiskDialog from "@/components/StormRiskDialog";
import AuthDialog from "@/components/AuthDialog";
import FavoritesList from "@/components/FavoritesList";
import { Slider } from "@/components/ui/slider";
import { useIsMobile } from "@/lib/useIsMobile";
import { api, API, getCurrent, getForecast, getHistory, getStrikes, getZones, LOURDES } from "@/lib/api";
import * as notif from "@/lib/notifications";
import * as push from "@/lib/push";

const REFRESH_MS = 120_000;
const STRIKES_MS = 15_000;
const STRIKES_WINDOW_S = 24 * 3600;
const DISPLAY_WINDOW_S = 3600;
const RADIUS_STEPS = [20, 30, 40, 50, 60, 70];
const DEFAULT_RADIUS = 20;

export default function Dashboard() {
  const [center, setCenter] = useState({ lat: LOURDES.lat, lon: LOURDES.lon, name: "Lourdes" });
  const [radius, setRadius] = useState(DEFAULT_RADIUS);
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
  const [pushEnabled, setPushEnabled] = useState(push.isPushEnabled());
  const [approach, setApproach] = useState(null);
  const [cursorTs, setCursorTs] = useState(() => Math.floor(Date.now() / 1000));
  const [playing, setPlaying] = useState(false);
  const isMobile = useIsMobile();

  // "Live" when cursor is within 60s of now
  const nowSec = Math.floor(Date.now() / 1000);
  const isLive = nowSec - cursorTs < 60;

  // Tick cursor forward while live so tiles & strikes stay current
  useEffect(() => {
    if (!isLive) return;
    const t = setInterval(() => setCursorTs(Math.floor(Date.now() / 1000)), 15_000);
    return () => clearInterval(t);
  }, [isLive]);

  // Filter strikes by cursor window for display
  const displayedStrikes = (strikes || []).filter((s) => {
    if (isLive) return nowSec - s.ts <= DISPLAY_WINDOW_S;
    return s.ts <= cursorTs && s.ts >= cursorTs - DISPLAY_WINDOW_S;
  });

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
        getZones(center.lat, center.lon, radius),
      ]);
      setCurrent(c);
      setForecast(f);
      setHistory(h);
      setZones(z);
      setLastFetch(new Date().toISOString());

      if (z.storm_active && !prevStormActive.current) {
        notif.notify("Alerte orage — Lourdes", `Activité orageuse détectée (CAPE ${Math.round(z.max_cape || 0)} J/kg)`);
      }
      prevStormActive.current = z.storm_active;
    } catch (e) {
      setError("Impossible de contacter le service météo");
    } finally {
      setRefreshing(false);
    }
  }, [center.lat, center.lon, radius]);

  const loadStrikes = useCallback(async () => {
    try {
      const since = Date.now() / 1000 - STRIKES_WINDOW_S;
      const data = await getStrikes(center.lat, center.lon, radius, since);
      setStrikes(data.strikes || []);

      const fresh = (data.strikes || []).filter((s) => !seenStrikeTs.current.has(s.ts));
      if (fresh.length > 0 && seenStrikeTs.current.size > 0) {
        const closest = fresh.reduce((m, s) => (s.distance_km < m.distance_km ? s : m), fresh[0]);
        notif.notify(
          `⚡ ${fresh.length} impact${fresh.length > 1 ? "s" : ""} de foudre`,
          `Le plus proche à ${closest.distance_km.toFixed(1)} km de Lourdes`
        );
      }
      for (const s of data.strikes || []) seenStrikeTs.current.add(s.ts);
      if (seenStrikeTs.current.size > 2000) {
        seenStrikeTs.current = new Set([...seenStrikeTs.current].slice(-1000));
      }

      // Approach analysis (use a wider radius, independent of UI radius)
      try {
        const app = await api.get("/storms/approach", {
          params: { lat: center.lat, lon: center.lon, radius_km: 100 },
        });
        const prev = approach?.approaching;
        setApproach(app.data);
        if (app.data?.approaching && !prev) {
          notif.notify(
            "⚠ Orage en approche",
            `Distance ${app.data.min_distance_km} km · ${app.data.speed_kmh} km/h · arrivée ~${Math.round(app.data.eta_min)} min`
          );
        }
      } catch { /* ignore */ }
    } catch { /* silent */ }
  }, [center.lat, center.lon, radius, approach?.approaching]);

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

  const togglePush = async () => {
    if (pushEnabled) {
      await push.unsubscribePush();
      setPushEnabled(false);
    } else {
      const ok = await push.subscribePush();
      setPushEnabled(ok);
    }
  };

  const downloadPdf = () => {
    const url = `${API}/reports/bulletin.pdf?lat=${center.lat}&lon=${center.lon}&radius_km=${radius}`;
    window.open(url, "_blank", "noopener,noreferrer");
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 lg:h-screen w-full lg:overflow-hidden bg-slate-50" data-testid="dashboard-root">
      {/* Map area — visible at top on mobile, right column on desktop */}
      <section
        className={`${
          fullscreen ? "lg:col-span-12" : "lg:col-span-8"
        } col-span-1 order-1 lg:order-2 h-[70vh] lg:h-full relative z-0 flex flex-col`}
        data-testid="map-area"
      >
        <div className="flex-1 min-h-0 relative">
          <MapPanel
            zones={zones?.zones || []}
            strikes={displayedStrikes}
            center={center}
            radiusKm={radius}
            fullscreen={fullscreen}
            onToggleFullscreen={() => setFullscreen((v) => !v)}
            cursorTs={cursorTs}
            isLive={isLive}
          />
        </div>
        <Timeline
          cursorTs={cursorTs}
          onCursorChange={setCursorTs}
          playing={playing}
          setPlaying={setPlaying}
          isLive={isLive}
          onResetLive={() => {
            setPlaying(false);
            setCursorTs(Math.floor(Date.now() / 1000));
          }}
        />
      </section>

      {/* Sidebar */}
      <aside
        className={`${
          fullscreen ? "hidden" : "lg:col-span-4"
        } col-span-1 order-2 lg:order-1 lg:h-full lg:overflow-y-auto bg-white lg:border-r border-t lg:border-t-0 border-slate-200 relative z-10 flex flex-col`}
        data-testid="sidebar"
      >
        <AlertBanner
          stormActive={zones?.storm_active}
          maxCape={zones?.max_cape}
          maxLp={zones?.max_lightning_potential}
          fetchedAt={lastFetch}
        />

        <VigilanceBanner />

        {approach?.approaching && (
          <div className="px-6 pt-4">
            <ApproachAlert approach={approach} />
          </div>
        )}

        <div className="px-6 pt-8 pb-6 border-b border-slate-100 grain relative shrink-0">
          <NavTabs variant="inline" />
          <div className="flex items-start justify-between mb-4 mt-5">
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
            de <span className="font-mono text-slate-900">{radius}&nbsp;km</span> autour de Lourdes.
          </p>

          {/* Radius slider */}
          <div className="mt-6" data-testid="radius-control">
            <div className="flex items-baseline justify-between mb-3">
              <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400">
                Rayon de surveillance
              </span>
              <span className="font-mono text-sm font-medium text-slate-900 tabular-nums">
                {radius}&nbsp;km
              </span>
            </div>
            <Slider
              data-testid="radius-slider"
              value={[radius]}
              min={20}
              max={70}
              step={10}
              onValueChange={(v) => setRadius(v[0])}
              className="mt-1"
            />
            <div className="flex justify-between font-mono text-[9px] uppercase tracking-wider text-slate-400 mt-2">
              {RADIUS_STEPS.map((s) => (
                <button
                  key={s}
                  onClick={() => setRadius(s)}
                  className={`transition-colors ${
                    s === radius ? "text-slate-900 font-semibold" : "hover:text-slate-700"
                  }`}
                  data-testid={`radius-preset-${s}`}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>

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
                {notifEnabled ? "Alertes in-app actives" : "Alertes in-app"}
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

          {/* Push toggle (server-sent, works when tab is closed) */}
          <button
            onClick={togglePush}
            className={`mt-2 w-full flex items-center justify-between px-4 h-10 border transition-colors ${
              pushEnabled
                ? "bg-red-600 text-white border-red-600"
                : "bg-white text-slate-900 border-slate-300 hover:border-red-600"
            }`}
            data-testid="toggle-push"
          >
            <span className="flex items-center gap-2">
              <Bell className="w-4 h-4" strokeWidth={1.8} />
              <span className="font-mono text-[10px] uppercase tracking-[0.2em]">
                {pushEnabled ? "Push serveur actif" : "Push serveur (même fermé)"}
              </span>
            </span>
            <span
              className={`w-8 h-4 rounded-full relative transition-colors ${
                pushEnabled ? "bg-white/20" : "bg-slate-200"
              }`}
            >
              <span
                className={`absolute top-0.5 w-3 h-3 rounded-full transition-all ${
                  pushEnabled ? "left-[18px] bg-white" : "left-0.5 bg-slate-400"
                }`}
              />
            </span>
          </button>

          {/* PDF bulletin */}
          <button
            onClick={downloadPdf}
            className="mt-2 w-full flex items-center justify-center gap-2 px-4 h-10 border border-slate-300 bg-white text-slate-900 hover:bg-slate-900 hover:text-white hover:border-slate-900 transition-colors font-mono text-[10px] uppercase tracking-[0.2em]"
            data-testid="download-bulletin-pdf"
          >
            <Download className="w-4 h-4" strokeWidth={1.8} />
            Bulletin PDF
          </button>

          {/* Storm risk forecast dialog */}
          <StormRiskDialog lat={center.lat} lon={center.lon} />

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
          <HistoryDaysChart days={7} />
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
    </div>
  );
}
