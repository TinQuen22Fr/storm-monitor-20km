import { useCallback, useEffect, useState } from "react";
import { RefreshCw, Zap } from "lucide-react";
import MapPanel from "@/components/MapPanel";
import AlertBanner from "@/components/AlertBanner";
import CurrentConditions from "@/components/CurrentConditions";
import CapeGauge from "@/components/CapeGauge";
import HistoryChart from "@/components/HistoryChart";
import ForecastChart from "@/components/ForecastChart";
import AuthDialog from "@/components/AuthDialog";
import FavoritesList from "@/components/FavoritesList";
import { getCurrent, getForecast, getHistory, getZones, LOURDES } from "@/lib/api";

const REFRESH_MS = 120_000; // 2 min

export default function Dashboard() {
  const [center, setCenter] = useState({ lat: LOURDES.lat, lon: LOURDES.lon, name: "Lourdes" });
  const [current, setCurrent] = useState(null);
  const [forecast, setForecast] = useState(null);
  const [history, setHistory] = useState(null);
  const [zones, setZones] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [lastFetch, setLastFetch] = useState(null);
  const [error, setError] = useState(null);

  const loadAll = useCallback(async () => {
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
    } catch (e) {
      setError("Impossible de contacter le service météo");
    } finally {
      setRefreshing(false);
    }
  }, [center.lat, center.lon]);

  useEffect(() => {
    loadAll();
    const t = setInterval(loadAll, REFRESH_MS);
    return () => clearInterval(t);
  }, [loadAll]);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 h-screen w-full overflow-hidden bg-slate-50" data-testid="dashboard-root">
      {/* Sidebar */}
      <aside
        className="col-span-1 lg:col-span-4 h-full overflow-y-auto bg-white border-r border-slate-200 relative z-10 flex flex-col"
        data-testid="sidebar"
      >
        {/* Alert banner */}
        <AlertBanner
          stormActive={zones?.storm_active}
          maxCape={zones?.max_cape}
          maxLp={zones?.max_lightning_potential}
          fetchedAt={lastFetch}
        />

        {/* Header */}
        <div className="px-6 pt-8 pb-6 border-b border-slate-100 grain relative overflow-hidden">
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
              onClick={loadAll}
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

          {error && (
            <div className="mt-4 p-3 bg-red-50 border border-red-200 text-xs text-red-800 font-mono" data-testid="error-banner">
              {error}
            </div>
          )}
        </div>

        {/* Panels */}
        <div className="px-6 py-6 space-y-6 flex-1">
          {/* Current conditions bento */}
          <div>
            <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400 mb-3">
              Conditions actuelles
            </div>
            <CurrentConditions current={current} />
          </div>

          {/* CAPE gauge */}
          <CapeGauge
            cape={current?.cape ?? zones?.max_cape}
            lightningPotential={current?.lightning_potential ?? zones?.max_lightning_potential}
          />

          {/* History 24h */}
          <HistoryChart hourly={history?.hourly || []} />

          {/* Forecast */}
          <ForecastChart hourly={forecast?.hourly || []} />

          {/* Favorites + auth */}
          <div className="space-y-4">
            <AuthDialog />
            <FavoritesList onSelect={setCenter} activeCenter={center} />
          </div>

          <footer className="pt-6 border-t border-slate-100 text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400">
            Données · Open-Meteo
          </footer>
        </div>
      </aside>

      {/* Map area */}
      <section className="col-span-1 lg:col-span-8 h-full relative z-0" data-testid="map-area">
        <MapPanel zones={zones?.zones || []} center={center} radiusKm={LOURDES.radius} />
      </section>
    </div>
  );
}
