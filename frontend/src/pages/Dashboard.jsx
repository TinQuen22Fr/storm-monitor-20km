import { useCallback, useEffect, useRef, useState } from "react";
import { Bell, BellOff, Download, LocateFixed, Map as MapIcon, MapPin, Moon, PlayCircle, RefreshCw, Share2, X, Zap } from "lucide-react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import MapPanel from "@/components/MapPanel";
import DataFreshnessBadge from "@/components/DataFreshnessBadge";
import AlertBanner from "@/components/AlertBanner";
import ApproachAlert from "@/components/ApproachAlert";
import Timeline from "@/components/Timeline";
import VigilanceBanner from "@/components/VigilanceBanner";
import NightStormMode from "@/components/NightStormMode";
import NavTabs from "@/components/NavTabs";
import CurrentConditions from "@/components/CurrentConditions";
import RainNowcastBadge from "@/components/RainNowcastBadge";
import CapeGauge from "@/components/CapeGauge";
import HistoryChart from "@/components/HistoryChart";
import HistoryDaysChart from "@/components/HistoryDaysChart";
import ForecastChart from "@/components/ForecastChart";
import StormRiskDialog from "@/components/StormRiskDialog";
import AuthDialog from "@/components/AuthDialog";
import DataSourceBadge from "@/components/DataSourceBadge";
import FavoritesList from "@/components/FavoritesList";
import { Slider } from "@/components/ui/slider";
import { useIsMobile } from "@/lib/useIsMobile";
import { api, API, getCurrent, getForecast, getHistory, getStrikes, getZones, listFavorites, LOURDES } from "@/lib/api";
import * as notif from "@/lib/notifications";
import * as push from "@/lib/push";
import { setLocalTimezone, fmtLocal, fmtLocalTime } from "@/lib/timeFormat";
import { useAuth } from "@/lib/auth";

const STRIKES_MS = 15_000;
const STRIKES_WINDOW_S = 24 * 3600;
const DISPLAY_WINDOW_S = 3600;
const RADIUS_STEPS = [20, 30, 40, 50, 60];
const DEFAULT_RADIUS = 20;

export default function Dashboard() {
  const { user } = useAuth();
  const [center, setCenter] = useState({ lat: LOURDES.lat, lon: LOURDES.lon, name: "Lourdes" });
  const [centerAutoLoaded, setCenterAutoLoaded] = useState(false);
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
  const [nightMode, setNightMode] = useState(false);
  const [shareCopied, setShareCopied] = useState(false);
  const [replay, setReplay] = useState(null); // { start_ts, end_ts } when replaying a past event
  const [replayEventsCount, setReplayEventsCount] = useState(0);
  const [gpsLock, setGpsLock] = useState(() => {
    try { return localStorage.getItem("storm.gpsLock") === "1"; } catch { return false; }
  });
  const [gpsLockError, setGpsLockError] = useState(null);
  const [visibleFavs, setVisibleFavs] = useState([]); // list of {id, lat, lon, name} from FavoritesList
  const [overlayData, setOverlayData] = useState({}); // { favId: { zones, strikes } }
  const isMobile = useIsMobile();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  // "Live" when cursor is within 60s of now
  const nowSec = Math.floor(Date.now() / 1000);
  const isLive = nowSec - cursorTs < 60;

  // No active zone = user is logged in but has unticked all their favorites
  const noZone = !!user && visibleFavs.length === 0;

  // Callback from FavoritesList: handle visibility changes AND auto-switch focus
  // when the current center is no longer in the visible list.
  const handleVisibleChange = useCallback((visible) => {
    setVisibleFavs(visible);
    if (!user) return;
    const centerStillVisible = visible.some(
      (f) => Math.abs(f.lat - center.lat) < 0.001 && Math.abs(f.lon - center.lon) < 0.001
    );
    if (centerStillVisible) return;
    if (visible.length > 0) {
      const f = visible[0];
      setCenter({ id: f.id, lat: f.lat, lon: f.lon, name: f.name });
    }
    // else: noZone === true, we keep the last center but stop fetching (see loadWeather/loadStrikes)
  }, [user, center.lat, center.lon]);

  // Bootstrap replay mode from ?replay=start:end (from ReplayPage)
  useEffect(() => {
    const param = searchParams.get("replay");
    if (!param) return;
    const [s, e] = param.split(":").map((x) => parseInt(x, 10));
    if (!s || !e || e <= s) return;
    setReplay({ start_ts: s, end_ts: e });
    setCursorTs(s);
    setPlaying(true);
    // Clean URL after consuming the param (user can bookmark the replay route instead)
    setSearchParams({}, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-exit replay when cursor reaches end or user manually scrubs back to live
  useEffect(() => {
    if (!replay) return;
    if (cursorTs >= replay.end_ts) {
      setPlaying(false);
      // Stay frozen on the last frame — user exits via the banner button
    }
  }, [cursorTs, replay]);

  const exitReplay = useCallback(() => {
    setReplay(null);
    setPlaying(false);
    setCursorTs(Math.floor(Date.now() / 1000));
  }, []);

  // When user logs in (or page reloads with token), auto-set center to their first favorite.
  // Only runs once per user to avoid overriding their explicit selections later.
  useEffect(() => {
    if (!user) {
      // Logout → back to Lourdes if we had auto-loaded a favorite
      if (centerAutoLoaded) {
        setCenter({ lat: LOURDES.lat, lon: LOURDES.lon, name: "Lourdes" });
        setCenterAutoLoaded(false);
      }
      return;
    }
    if (centerAutoLoaded) return;
    let cancel = false;
    (async () => {
      try {
        const favs = await listFavorites();
        if (cancel || !favs || favs.length === 0) return;
        const first = favs[0];
        setCenter({ lat: first.lat, lon: first.lon, name: first.name });
        setCenterAutoLoaded(true);
      } catch { /* ignore — keep Lourdes */ }
    })();
    return () => { cancel = true; };
  }, [user, centerAutoLoaded]);

  // GPS lock — continuously track user position and recenter map + monitoring zone
  useEffect(() => {
    if (!gpsLock) return;
    if (!navigator.geolocation) {
      setGpsLockError("Géolocalisation non supportée");
      setGpsLock(false);
      try { localStorage.setItem("storm.gpsLock", "0"); } catch { /* ignore */ }
      setTimeout(() => setGpsLockError(null), 4000);
      return;
    }
    const id = navigator.geolocation.watchPosition(
      (pos) => {
        setCenter({ lat: pos.coords.latitude, lon: pos.coords.longitude, name: "Ma position" });
      },
      () => {
        setGpsLockError("Position GPS indisponible");
        setGpsLock(false);
        try { localStorage.setItem("storm.gpsLock", "0"); } catch { /* ignore */ }
        setTimeout(() => setGpsLockError(null), 4000);
      },
      { enableHighAccuracy: true, maximumAge: 30_000, timeout: 15_000 }
    );
    return () => navigator.geolocation.clearWatch(id);
  }, [gpsLock]);

  const toggleGpsLock = useCallback(() => {
    setGpsLock((v) => {
      const nv = !v;
      try { localStorage.setItem("storm.gpsLock", nv ? "1" : "0"); } catch { /* ignore */ }
      // When disabling, return monitoring zone to Lourdes
      if (!nv) {
        setCenter({ lat: LOURDES.lat, lon: LOURDES.lon, name: "Lourdes" });
      }
      return nv;
    });
  }, []);

  // Fetch count of available replay events periodically so the "Rejouer un orage" CTA is informed
  useEffect(() => {
    let cancel = false;
    const load = async () => {
      try {
        const { data } = await api.get("/replay/events");
        if (!cancel) setReplayEventsCount((data.events || []).length);
      } catch { /* ignore */ }
    };
    load();
    const t = setInterval(load, 5 * 60_000);
    return () => { cancel = true; clearInterval(t); };
  }, []);

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

  // Secondary monitoring zones (multi-favoris): keep only the visible ones that are
  // NOT the current focus (the center is already drawn by the main fetch).
  const extraFavs = (visibleFavs || []).filter(
    (f) =>
      !(Math.abs(f.lat - center.lat) < 0.001 && Math.abs(f.lon - center.lon) < 0.001)
  );

  // Merge fetched data with the favs descriptors so MapPanel always knows the names
  const visibleOverlays = extraFavs.map((f) => ({
    id: f.id,
    lat: f.lat,
    lon: f.lon,
    name: f.name,
    radiusKm: radius,
    zones: overlayData[f.id]?.zones || [],
    strikes: (overlayData[f.id]?.strikes || []).filter((s) =>
      isLive ? nowSec - s.ts <= DISPLAY_WINDOW_S : s.ts <= cursorTs && s.ts >= cursorTs - DISPLAY_WINDOW_S
    ),
  }));

  const prevStormActive = useRef(false);
  const seenStrikeTs = useRef(new Set());

  const loadWeather = useCallback(async () => {
    if (noZone) {
      setCurrent(null);
      setForecast(null);
      setHistory(null);
      setZones(null);
      setApproach(null);
      return;
    }
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

      // Update the global "monitored location timezone" so all timestamps
      // displayed in the app use this TZ (Lourdes → Europe/Paris, DST handled
      // automatically by Open-Meteo via timezone=auto)
      if (c?.timezone) setLocalTimezone(c.timezone);

      if (z.storm_active && !prevStormActive.current) {
        notif.notify(`Alerte orage — ${center.name}`, `Activité orageuse détectée (CAPE ${Math.round(z.max_cape || 0)} J/kg)`);
      }
      prevStormActive.current = z.storm_active;
    } catch (e) {
      setError("Impossible de contacter le service météo");
    } finally {
      setRefreshing(false);
    }
  }, [center.lat, center.lon, center.name, radius, noZone]);

  const loadStrikes = useCallback(async () => {
    if (noZone) {
      setStrikes([]);
      return;
    }
    try {
      const since = Date.now() / 1000 - STRIKES_WINDOW_S;
      const data = await getStrikes(center.lat, center.lon, radius, since);
      setStrikes(data.strikes || []);

      const fresh = (data.strikes || []).filter((s) => !seenStrikeTs.current.has(s.ts));
      if (fresh.length > 0 && seenStrikeTs.current.size > 0) {
        const closest = fresh.reduce((m, s) => (s.distance_km < m.distance_km ? s : m), fresh[0]);
        notif.notify(
          `⚡ ${fresh.length} impact${fresh.length > 1 ? "s" : ""} de foudre`,
          `Le plus proche à ${closest.distance_km.toFixed(1)} km de ${center.name}`
        );
      }
      for (const s of data.strikes || []) seenStrikeTs.current.add(s.ts);
      if (seenStrikeTs.current.size > 2000) {
        seenStrikeTs.current = new Set([...seenStrikeTs.current].slice(-1000));
      }

      // Approach analysis (use configured radius + buffer, capped at 70km)
      try {
        const app = await api.get("/storms/approach", {
          params: { lat: center.lat, lon: center.lon, radius_km: 70 },
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
  }, [center.lat, center.lon, center.name, radius, approach?.approaching, noZone]);

  useEffect(() => {
    // Météo (zones Open-Meteo) : AUCUN polling automatique — chargement initial
    // + bouton « Actualiser » uniquement. Les impacts Blitzortung restent en
    // quasi temps réel (websocket local, 0 appel Open-Meteo).
    loadWeather();
    loadStrikes();
    const st = setInterval(loadStrikes, STRIKES_MS);
    return () => {
      clearInterval(st);
    };
  }, [loadWeather, loadStrikes]);

  // Fetch zones + strikes for each secondary (non-focus) visible favorite.
  // Refresh every 30s to keep the multi-zone overlay live without hammering the API.
  // Stable signature so we don't re-trigger on object identity changes.
  const overlayKey = visibleFavs
    .map((f) => `${f.id}:${f.lat.toFixed(3)},${f.lon.toFixed(3)}`)
    .join("|");
  useEffect(() => {
    const targets = (visibleFavs || []).filter(
      (f) => !(Math.abs(f.lat - center.lat) < 0.001 && Math.abs(f.lon - center.lon) < 0.001)
    );
    if (targets.length === 0) {
      setOverlayData((prev) => (Object.keys(prev).length === 0 ? prev : {}));
      return;
    }
    let cancel = false;
    const fetchAll = async () => {
      const since = Date.now() / 1000 - STRIKES_WINDOW_S;
      const results = await Promise.allSettled(
        targets.map(async (f) => {
          const [z, s] = await Promise.all([
            getZones(f.lat, f.lon, radius),
            getStrikes(f.lat, f.lon, radius, since),
          ]);
          return { id: f.id, zones: z.zones || [], strikes: s.strikes || [] };
        })
      );
      if (cancel) return;
      setOverlayData(() => {
        const next = {};
        for (const r of results) {
          if (r.status === "fulfilled") next[r.value.id] = { zones: r.value.zones, strikes: r.value.strikes };
        }
        return next;
      });
    };
    // Chargement unique (pas de polling) — zones Open-Meteo 100 % à la demande
    fetchAll();
    return () => {
      cancel = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [overlayKey, center.lat, center.lon, radius]);

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
    if (noZone) return;
    // Build the multi-zone query: active center first, then each secondary visible zone.
    const all = [
      { name: center.name, lat: center.lat, lon: center.lon, r: radius },
      ...visibleOverlays.map((o) => ({ name: o.name, lat: o.lat, lon: o.lon, r: o.radiusKm })),
    ];
    const qs = all
      .map((z) => `z=${encodeURIComponent(`${z.name}|${z.lat}|${z.lon}|${z.r}`)}`)
      .join("&");
    const url = `${API}/reports/bulletin.pdf?${qs}`;
    window.open(url, "_blank", "noopener,noreferrer");
  };

  const shareCard = async () => {
    const url = `${API}/share/card.png?t=${Date.now()}`;
    // Try Web Share API (mobile) first with image
    try {
      if (navigator.share) {
        const res = await fetch(url);
        const blob = await res.blob();
        const file = new File([blob], "orage-lourdes.png", { type: "image/png" });
        if (navigator.canShare && navigator.canShare({ files: [file] })) {
          await navigator.share({
            title: `Suivi d'orage · ${center.name}`,
            text: `État actuel autour de ${center.name}`,
            files: [file],
          });
          return;
        }
      }
    } catch { /* fall back to copy */ }
    // Desktop fallback: open image in new tab & copy URL
    try {
      await navigator.clipboard.writeText(url);
      setShareCopied(true);
      setTimeout(() => setShareCopied(false), 2000);
    } catch { /* ignore */ }
    window.open(url, "_blank", "noopener,noreferrer");
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 lg:h-screen w-full lg:overflow-hidden bg-slate-50/70" data-testid="dashboard-root">
      {/* Map area — visible at top on mobile, right column on desktop */}
      <section
        className={`${
          fullscreen ? "lg:col-span-12" : "lg:col-span-8"
        } col-span-1 order-1 lg:order-2 h-auto lg:h-full relative z-0 flex flex-col`}
        data-testid="map-area"
      >
        <div className="lg:flex-1 lg:min-h-0 relative">
          <MapPanel
            zones={zones?.zones || []}
            strikes={displayedStrikes}
            center={center}
            radiusKm={radius}
            fullscreen={fullscreen}
            onToggleFullscreen={() => setFullscreen((v) => !v)}
            cursorTs={cursorTs}
            isLive={isLive}
            overlays={visibleOverlays}
            noZone={noZone}
          />
          {!noZone && <DataFreshnessBadge fetchedAt={zones?.fetched_at} />}
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
        } col-span-1 order-2 lg:order-1 lg:h-full lg:overflow-y-auto bg-white/80 lg:border-r border-t lg:border-t-0 border-slate-200 relative z-10 flex flex-col`}
        data-testid="sidebar"
      >
        <AlertBanner
          stormActive={zones?.storm_active}
          maxCape={zones?.max_cape}
          maxLp={zones?.max_lightning_potential}
          fetchedAt={lastFetch}
        />

        {replay && (
          <div
            className="px-6 py-3 bg-violet-50 border-b border-violet-200 flex items-center gap-3"
            data-testid="replay-banner"
          >
            <PlayCircle
              className={`w-4 h-4 text-violet-700 shrink-0 ${playing ? "animate-pulse" : ""}`}
              strokeWidth={2.2}
            />
            <div className="flex-1 min-w-0">
              <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-violet-700 font-semibold">
                Mode replay · lecture {playing ? "en cours" : "en pause"}
              </div>
              <div className="text-[11px] text-violet-900 font-mono tabular-nums mt-0.5">
                {fmtLocal(replay.start_ts, {
                  day: "2-digit",
                  month: "short",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
                {" → "}
                {fmtLocalTime(replay.end_ts)}
              </div>
            </div>
            <button
              type="button"
              onClick={exitReplay}
              className="shrink-0 h-8 px-3 flex items-center gap-1.5 border border-violet-300 hover:bg-violet-700 hover:text-white hover:border-violet-700 transition-colors font-mono text-[10px] uppercase tracking-[0.18em] text-violet-900"
              data-testid="replay-exit-btn"
              aria-label="Sortir du mode replay"
            >
              <X className="w-3 h-3" strokeWidth={2.5} />
              Sortir
            </button>
          </div>
        )}

        {!replay && replayEventsCount > 0 && (
          <button
            type="button"
            onClick={() => navigate("/replay")}
            className="w-full px-6 py-3 bg-slate-900 hover:bg-violet-700 transition-colors text-left flex items-center gap-3 group"
            data-testid="replay-cta"
          >
            <PlayCircle className="w-4 h-4 text-violet-300 shrink-0" strokeWidth={2.2} />
            <div className="flex-1 min-w-0">
              <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-violet-300 font-semibold">
                Mode replay disponible
              </div>
              <div className="text-[12px] text-white font-medium mt-0.5 truncate">
                Rejouer les {replayEventsCount} épisode{replayEventsCount > 1 ? "s" : ""} détecté{replayEventsCount > 1 ? "s" : ""} des 24h
              </div>
            </div>
            <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-white/80 group-hover:text-white transition-colors shrink-0">
              →
            </span>
          </button>
        )}

        <VigilanceBanner />

        {(current?.degraded || zones?.degraded) && (
          <div
            className="px-6 py-2 bg-amber-50 border-b border-amber-200 flex items-center gap-2 text-[11px] font-mono text-amber-900"
            data-testid="degraded-banner"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse shrink-0" />
            <span>Service météo limité par le fournisseur — reprise automatique sous quelques minutes.</span>
          </div>
        )}

        {approach?.approaching && (
          <div className="px-6 pt-4">
            <ApproachAlert approach={approach} />
          </div>
        )}

        <div className="px-6 pt-8 pb-6 border-b border-slate-100 grain relative shrink-0">
          <NavTabs variant="inline" />
          <div className="flex items-start justify-between mb-4 mt-5">
            <div className="flex items-center gap-2 min-w-0">
              <Zap className="w-4 h-4 text-slate-900 shrink-0" strokeWidth={2.5} />
              <span className="font-mono text-[10px] uppercase tracking-[0.3em] text-slate-500 font-semibold truncate">
                {noZone ? "Aucune zone" : `Orage · ${center.name}`}
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
            Suivi d&apos;orage<br />
            <span className="text-slate-400">en temps réel.</span>
          </h1>
          {noZone ? (
            <div
              className="mt-4 p-4 border border-blue-200 bg-blue-50"
              data-testid="no-zone-placeholder"
            >
              <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-blue-700 font-semibold mb-1">
                Aucune zone sélectionnée
              </div>
              <p className="text-sm text-blue-900 leading-relaxed">
                Coche un lieu dans <span className="font-mono">Mes lieux</span> pour reprendre la surveillance.
              </p>
            </div>
          ) : (
            <p className="text-sm text-slate-500 mt-4 leading-relaxed max-w-xs">
              Surveillance de l&apos;activité électrique et convective dans un rayon
              de <span className="font-mono text-slate-900">{radius}&nbsp;km</span> autour de <span className="font-mono text-slate-900">{center.name}</span>
              {visibleOverlays.length > 0 && (
                <>
                  {" "}
                  <span className="font-mono text-blue-700">
                    + {visibleOverlays.length} autre{visibleOverlays.length > 1 ? "s" : ""} zone{visibleOverlays.length > 1 ? "s" : ""}
                  </span>
                </>
              )}
              .
            </p>
          )}

          {/* Credibility badge — TOA Blitzortung */}
          <div className="mt-4">
            <DataSourceBadge />
          </div>

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
              max={60}
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
                ? fmtLocalTime(lastFetch, { second: "2-digit" })
                : "--:--"}
            </span>
          </div>

          {/* GPS lock — track me & recenter monitoring zone */}
          <button
            onClick={toggleGpsLock}
            className={`mt-4 w-full flex items-center justify-between px-4 h-10 border transition-colors ${
              gpsLock
                ? "bg-blue-600 text-white border-blue-600"
                : "bg-white text-slate-900 border-slate-300 hover:border-blue-600"
            }`}
            data-testid="toggle-gps-lock"
            aria-pressed={gpsLock}
          >
            <span className="flex items-center gap-2">
              {gpsLock ? <LocateFixed className="w-4 h-4" strokeWidth={1.8} /> : <MapPin className="w-4 h-4" strokeWidth={1.8} />}
              <span className="font-mono text-[10px] uppercase tracking-[0.2em]">
                {gpsLock ? "GPS épinglé · me suivre" : "Épingler ma position GPS"}
              </span>
            </span>
            <span
              className={`w-8 h-4 rounded-full relative transition-colors ${
                gpsLock ? "bg-white/20" : "bg-slate-200"
              }`}
            >
              <span
                className={`absolute top-0.5 w-3 h-3 rounded-full transition-all ${
                  gpsLock ? "left-[18px] bg-white" : "left-0.5 bg-slate-400"
                }`}
              />
            </span>
          </button>
          {gpsLockError && (
            <div
              className="mt-2 px-3 py-2 bg-red-50 border border-red-200 text-[11px] font-mono text-red-800"
              data-testid="gps-lock-error"
            >
              {gpsLockError}
            </div>
          )}

          {/* Notifications toggle */}
          <button
            onClick={toggleNotif}
            className={`mt-2 w-full flex items-center justify-between px-4 h-10 border transition-colors ${
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

          {/* Send push test (only when push is enabled) */}
          {pushEnabled && (
            <button
              onClick={() => push.sendTestPush()}
              className="mt-2 w-full flex items-center justify-center gap-2 px-4 h-10 border border-red-600 bg-white text-red-700 hover:bg-red-600 hover:text-white transition-colors font-mono text-[10px] uppercase tracking-[0.2em]"
              data-testid="send-push-test"
            >
              <Zap className="w-4 h-4" strokeWidth={1.8} />
              Envoyer un test
            </button>
          )}

          {/* PDF bulletin */}
          <button
            onClick={downloadPdf}
            disabled={noZone}
            className="mt-2 w-full flex items-center justify-center gap-2 px-4 h-10 border border-slate-300 bg-white text-slate-900 hover:bg-slate-900 hover:text-white hover:border-slate-900 transition-colors font-mono text-[10px] uppercase tracking-[0.2em] disabled:opacity-40 disabled:hover:bg-white disabled:hover:text-slate-900 disabled:hover:border-slate-300 disabled:cursor-not-allowed"
            data-testid="download-bulletin-pdf"
            title={noZone ? "Coche au moins une zone pour générer un bulletin" : undefined}
          >
            <Download className="w-4 h-4" strokeWidth={1.8} />
            Bulletin PDF{!noZone && visibleOverlays.length > 0 ? ` · ${visibleOverlays.length + 1} zones` : ""}
          </button>

          {/* Share card */}
          <button
            onClick={shareCard}
            className="mt-2 w-full flex items-center justify-center gap-2 px-4 h-10 border border-slate-300 bg-white text-slate-900 hover:bg-slate-900 hover:text-white hover:border-slate-900 transition-colors font-mono text-[10px] uppercase tracking-[0.2em]"
            data-testid="share-card-button"
          >
            <Share2 className="w-4 h-4" strokeWidth={1.8} />
            {shareCopied ? "Lien copié ✓" : "Partager (WhatsApp…)"}
          </button>

          {/* Night storm mode */}
          <button
            onClick={() => setNightMode(true)}
            className="mt-2 w-full flex items-center justify-center gap-2 px-4 h-10 border border-slate-900 bg-slate-900 text-white hover:bg-black transition-colors font-mono text-[10px] uppercase tracking-[0.2em]"
            data-testid="night-mode-button"
          >
            <Moon className="w-4 h-4" strokeWidth={1.8} />
            Mode soirée orage
          </button>

          {/* Vigilance map link */}
          <Link
            to="/vigilance"
            className="mt-2 w-full flex items-center justify-center gap-2 px-4 h-10 border border-amber-500 bg-amber-50 text-amber-900 hover:bg-amber-500 hover:text-white transition-colors font-mono text-[10px] uppercase tracking-[0.2em]"
            data-testid="open-vigilance-map"
          >
            <MapIcon className="w-4 h-4" strokeWidth={1.8} />
            Carte vigilance France
          </Link>

          {/* Storm risk forecast dialog */}
          <StormRiskDialog lat={center.lat} lon={center.lon} />

          {error && (
            <div className="mt-4 p-3 bg-red-50 border border-red-200 text-xs text-red-800 font-mono" data-testid="error-banner">
              {error}
            </div>
          )}
        </div>

        <div className="px-6 py-6 space-y-6 flex-1 shrink-0">
          <div className={noZone ? "opacity-40 pointer-events-none select-none" : ""} aria-hidden={noZone}>
            <div className="mb-4">
              <RainNowcastBadge lat={center.lat} lon={center.lon} />
            </div>
            <div>
              <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400 mb-3">
                Conditions actuelles
              </div>
              <CurrentConditions current={current} />
            </div>

            <div className="mt-6">
              <CapeGauge
                cape={current?.cape ?? zones?.max_cape}
                lightningPotential={current?.lightning_potential ?? zones?.max_lightning_potential}
              />
            </div>

            <div className="mt-6 space-y-6">
              <HistoryChart hourly={history?.hourly || []} />
              <HistoryDaysChart days={7} />
              <ForecastChart hourly={forecast?.hourly || []} />
            </div>
          </div>

          <div className="space-y-4">
            <AuthDialog />
            <FavoritesList
              onSelect={(c) => {
                if (gpsLock) {
                  setGpsLock(false);
                  try { localStorage.setItem("storm.gpsLock", "0"); } catch { /* ignore */ }
                }
                setCenter(c);
              }}
              onVisibleChange={handleVisibleChange}
              activeCenter={center}
            />
          </div>

          <footer className="pt-6 border-t border-slate-100 text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400 space-y-1">
            <div>Météo · Open-Meteo</div>
            <div>Foudre · Blitzortung.org</div>
          </footer>
        </div>
      </aside>

      <NightStormMode
        open={nightMode}
        onClose={() => setNightMode(false)}
        center={center}
      />
    </div>
  );
}
