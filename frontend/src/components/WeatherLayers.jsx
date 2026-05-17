import { useEffect, useRef, useState } from "react";
import { TileLayer, useMap } from "react-leaflet";
import { Activity, Cloud, CloudRain, Pause, Play, Wind } from "lucide-react";

const RAINVIEWER_API = "https://api.rainviewer.com/public/weather-maps.json";
const FRAME_DURATION_MS = 800;

// NASA GIBS - MODIS Terra true-color satellite imagery (includes clouds as white masses)
const GIBS_BASE =
  "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/MODIS_Terra_CorrectedReflectance_TrueColor/default";
const GIBS_TMS = "GoogleMapsCompatible_Level9";

function ymd(date) {
  const y = date.getUTCFullYear();
  const m = String(date.getUTCMonth() + 1).padStart(2, "0");
  const d = String(date.getUTCDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function buildCloudsUrl(dateStr) {
  return `${GIBS_BASE}/${dateStr}/${GIBS_TMS}/{z}/{y}/{x}.jpeg`;
}

function buildRadarUrl(host, path) {
  // Color 4 = The Weather Channel style (professional pro radar look)
  // Options: smooth=1, snow=1 (distinguish snow)
  return `${host}${path}/256/{z}/{x}/{y}/4/1_1.png`;
}

function cloudFrames() {
  // Last 5 days (Yesterday backwards — today's image is usually processed next day)
  const frames = [];
  const now = new Date();
  for (let i = 5; i >= 1; i--) {
    const d = new Date(now.getTime() - i * 86400000);
    frames.push({ time: Math.floor(d.getTime() / 1000), date: ymd(d) });
  }
  return frames;
}

export function useWeatherLayersState({ cursorTs = null, isLive = true } = {}) {
  const [rvData, setRvData] = useState(null);
  const [showClouds, setShowClouds] = useState(false);
  const [showRain, setShowRain] = useState(false);
  const [showWind, setShowWind] = useState(false);
  const [showTrajectory, setShowTrajectory] = useState(true);
  const [windMaxSpeed, setWindMaxSpeed] = useState(null);
  const [frame, setFrame] = useState(0);
  const [playing, setPlaying] = useState(false);
  const tickRef = useRef(null);

  useEffect(() => {
    let cancel = false;
    const fetchData = async () => {
      try {
        const res = await fetch(RAINVIEWER_API);
        const json = await res.json();
        if (!cancel) setRvData(json);
      } catch { /* ignore */ }
    };
    fetchData();
    const t = setInterval(fetchData, 5 * 60_000);
    return () => {
      cancel = true;
      clearInterval(t);
    };
  }, []);

  const cloudsFrames = cloudFrames();
  const radarFrames = rvData?.radar?.past || [];
  const activeFrames = showRain ? radarFrames : showClouds ? cloudsFrames : [];

  useEffect(() => {
    // When a global timeline cursor is driving and not live, disable auto-play
    if (!isLive) {
      clearInterval(tickRef.current);
      return;
    }
    if (!playing || activeFrames.length === 0 || (!showRain && !showClouds)) {
      clearInterval(tickRef.current);
      return;
    }
    tickRef.current = setInterval(() => {
      setFrame((f) => (f + 1) % activeFrames.length);
    }, FRAME_DURATION_MS);
    return () => clearInterval(tickRef.current);
  }, [playing, activeFrames.length, showRain, showClouds, isLive]);

  // When cursor is set (non-live), snap frame to closest timestamp
  useEffect(() => {
    if (isLive || cursorTs == null || activeFrames.length === 0) return;
    let best = 0;
    let bestDiff = Infinity;
    for (let i = 0; i < activeFrames.length; i++) {
      const d = Math.abs(activeFrames[i].time - cursorTs);
      if (d < bestDiff) {
        bestDiff = d;
        best = i;
      }
    }
    setFrame(best);
  }, [cursorTs, isLive, activeFrames]);

  useEffect(() => {
    if (activeFrames.length > 0 && isLive) setFrame(activeFrames.length - 1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showRain, showClouds, activeFrames.length]);

  const toggleClouds = () =>
    setShowClouds((v) => {
      const next = !v;
      if (next) setShowRain(false);
      return next;
    });
  const toggleRain = () =>
    setShowRain((v) => {
      const next = !v;
      if (next) setShowClouds(false);
      return next;
    });
  const toggleWind = () => setShowWind((v) => !v);
  const toggleTrajectory = () => setShowTrajectory((v) => !v);

  const currentFrame = activeFrames[frame];
  let url = null;
  let frameLabel = null;
  if (showClouds && currentFrame) {
    url = buildCloudsUrl(currentFrame.date);
    frameLabel = new Date(currentFrame.time * 1000).toLocaleDateString("fr-FR", {
      weekday: "short",
      day: "2-digit",
      month: "short",
    });
  } else if (showRain && currentFrame && rvData) {
    url = buildRadarUrl(rvData.host, currentFrame.path);
    frameLabel = new Date(currentFrame.time * 1000).toLocaleTimeString("fr-FR", {
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  return {
    url,
    showClouds,
    showRain,
    showWind,
    showTrajectory,
    toggleClouds,
    toggleRain,
    toggleWind,
    toggleTrajectory,
    windMaxSpeed,
    setWindMaxSpeed,
    activeFrames,
    frame,
    setFrame,
    playing,
    setPlaying,
    frameLabel,
  };
}

export function WeatherTileLayer({ url, showClouds, showRain }) {
  const map = useMap();
  useEffect(() => {
    if (map.getPane("weatherPane")) return;
    map.createPane("weatherPane");
    map.getPane("weatherPane").style.zIndex = 350;
    map.getPane("weatherPane").style.pointerEvents = "none";
  }, [map]);
  if (!url) return null;
  return (
    <TileLayer
      key={url}
      url={url}
      opacity={showClouds ? 0.85 : 0.75}
      tileSize={256}
      pane="weatherPane"
      maxNativeZoom={showClouds ? 9 : 10}
      maxZoom={20}
      noWrap
    />
  );
}

export function WeatherLayersPanel({
  showClouds,
  showRain,
  showWind,
  showTrajectory,
  toggleClouds,
  toggleRain,
  toggleWind,
  toggleTrajectory,
  windMaxSpeed,
  activeFrames,
  frame,
  setFrame,
  playing,
  setPlaying,
  frameLabel,
  isMobile = false,
  timelineDriven = false,
  hideOnMobile = false,
}) {
  return (
    <div
      className={`bg-white border border-slate-200 shadow-[0_2px_24px_rgba(0,0,0,0.06)] flex flex-col ${
        isMobile
          ? "static border-0"
          : `absolute z-[600] bottom-20 right-6 ${hideOnMobile ? "hidden md:flex" : ""}`
      }`}
      data-testid="weather-layers-panel"
    >
      <div className="flex">
        <button
          onClick={toggleClouds}
          className={`flex-1 flex items-center justify-center gap-2 px-3 h-11 border-r border-slate-200 transition-colors font-mono text-[10px] uppercase tracking-[0.2em] ${
            showClouds
              ? "bg-slate-900 text-white"
              : "bg-white text-slate-700 hover:text-slate-900"
          }`}
          data-testid="toggle-clouds"
          title="Masses nuageuses (satellite MODIS)"
        >
          <Cloud className="w-4 h-4" strokeWidth={1.8} />
          Nuages
        </button>
        <button
          onClick={toggleRain}
          className={`flex-1 flex items-center justify-center gap-2 px-3 h-11 border-r border-slate-200 transition-colors font-mono text-[10px] uppercase tracking-[0.2em] ${
            showRain
              ? "bg-slate-900 text-white"
              : "bg-white text-slate-700 hover:text-slate-900"
          }`}
          data-testid="toggle-rain"
          title="Radar précipitations (RainViewer)"
        >
          <CloudRain className="w-4 h-4" strokeWidth={1.8} />
          Pluie
        </button>
        <button
          onClick={toggleWind}
          className={`flex-1 flex items-center justify-center gap-2 px-3 h-11 border-r border-slate-200 transition-colors font-mono text-[10px] uppercase tracking-[0.2em] ${
            showWind
              ? "bg-slate-900 text-white"
              : "bg-white text-slate-700 hover:text-slate-900"
          }`}
          data-testid="toggle-wind"
          title="Vecteurs de vent (Open-Meteo)"
        >
          <Wind className="w-4 h-4" strokeWidth={1.8} />
          Vent
          {showWind && windMaxSpeed !== null && (
            <span className="ml-1 font-mono text-[9px] opacity-80">
              {Math.round(windMaxSpeed)}
            </span>
          )}
        </button>
        <button
          onClick={toggleTrajectory}
          className={`flex-1 flex items-center justify-center gap-2 px-3 h-11 transition-colors font-mono text-[10px] uppercase tracking-[0.2em] ${
            showTrajectory
              ? "bg-red-600 text-white"
              : "bg-white text-slate-700 hover:text-slate-900"
          }`}
          data-testid="toggle-trajectory"
          title="Trajectoire prédite de l'orage (régression linéaire)"
        >
          <Activity className="w-4 h-4" strokeWidth={1.8} />
          Trajet
        </button>
      </div>

      {(showClouds || showRain) && activeFrames.length > 0 && (
        <div className="border-t border-slate-200 px-4 py-3 flex items-center gap-3">
          <button
            onClick={() => setPlaying((p) => !p)}
            className="w-7 h-7 border border-slate-300 hover:bg-slate-900 hover:text-white hover:border-slate-900 transition-colors flex items-center justify-center shrink-0"
            data-testid="play-pause-frames"
            aria-label={playing ? "Pause" : "Lecture"}
          >
            {playing ? <Pause className="w-3 h-3" /> : <Play className="w-3 h-3" />}
          </button>
          <input
            type="range"
            min={0}
            max={activeFrames.length - 1}
            value={frame}
            onChange={(e) => {
              setPlaying(false);
              setFrame(parseInt(e.target.value, 10));
            }}
            className="flex-1 h-1 accent-slate-900"
            data-testid="frame-slider"
          />
          <span className="font-mono text-[10px] tabular-nums text-slate-900 min-w-[70px] text-right">
            {frameLabel}
          </span>
        </div>
      )}

      {(showClouds || showRain || showWind) && (
        <div className="border-t border-slate-200 px-4 py-2 font-mono text-[9px] uppercase tracking-[0.2em] text-slate-400">
          {showClouds
            ? "Source · NASA MODIS Terra"
            : showRain
            ? "Source · RainViewer radar"
            : "Source · Open-Meteo vent"}
        </div>
      )}
    </div>
  );
}
