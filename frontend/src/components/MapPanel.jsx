import { useEffect, useMemo, useState } from "react";
import { Circle, MapContainer, Marker, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import { Crosshair, Maximize2, Minimize2 } from "lucide-react";
import { LOURDES } from "@/lib/api";
import {
  WeatherTileLayer,
  WeatherLayersPanel,
  useWeatherLayersState,
} from "@/components/WeatherLayers";
import WindLayer from "@/components/WindLayer";
import TrajectoryLayer from "@/components/TrajectoryLayer";
import TrajectoryBadge from "@/components/TrajectoryBadge";
import { useIsMobile } from "@/lib/useIsMobile";

delete L.Icon.Default.prototype._getIconUrl;

function buildCenterIcon() {
  return L.divIcon({
    className: "",
    html: `<div class="center-pin" data-testid="map-center-pin"></div>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
  });
}

function buildUserIcon() {
  return L.divIcon({
    className: "",
    html: `<div style="width:14px;height:14px;border-radius:9999px;background:#2563EB;border:3px solid #fff;box-shadow:0 0 0 1px #2563EB, 0 0 12px rgba(37,99,235,0.6)"></div>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
  });
}

function buildStormIcon(zone) {
  const severity = zone.severity ?? 0;
  const isThunder = zone.is_thunder;
  const color = isThunder ? "#DC2626" : severity >= 60 ? "#DC2626" : severity >= 30 ? "#D97706" : "#10B981";
  const size = Math.max(12, Math.min(24, 12 + severity / 7));
  const ping = isThunder || severity >= 40;
  return L.divIcon({
    className: "",
    html: `<div class="storm-marker-wrapper" style="width:${size}px;height:${size}px">
      ${ping ? `<span class="storm-marker-ping" style="background:${color}"></span>` : ""}
      <span class="storm-marker-core" style="width:${size}px;height:${size}px;background:${color};border:2px solid #fff;box-shadow:0 0 0 1px ${color}"></span>
    </div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

function buildStrikeIcon(ageSec) {
  // New strikes are bright, older fade to dark
  const fresh = ageSec < 60;
  const recent = ageSec < 300;
  const color = fresh ? "#FDE047" : recent ? "#F59E0B" : "#DC2626";
  const border = fresh ? "#FACC15" : recent ? "#D97706" : "#B91C1C";
  return L.divIcon({
    className: "",
    html: `<div class="storm-marker-wrapper" style="width:14px;height:14px">
      ${fresh ? `<span class="storm-marker-ping" style="background:${color}"></span>` : ""}
      <svg class="storm-marker-core" viewBox="0 0 24 24" width="14" height="14" style="filter:drop-shadow(0 0 3px ${border})">
        <path d="M13 2L3 14h7l-1 8 11-12h-7l0-8z" fill="${color}" stroke="${border}" stroke-width="1.5" stroke-linejoin="round"/>
      </svg>
    </div>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
  });
}

function FitToRadius({ center, radiusKm, override }) {
  const map = useMap();
  useEffect(() => {
    if (override) {
      map.setView(center, override, { animate: true });
      return;
    }
    const zoomForRadius = radiusKm >= 60 ? 9 : radiusKm >= 40 ? 10 : 11;
    map.setView(center, zoomForRadius, { animate: true });
  }, [center, radiusKm, override, map]);
  return null;
}

function InvalidateOnResize({ trigger }) {
  const map = useMap();
  useEffect(() => {
    const t = setTimeout(() => map.invalidateSize(), 320);
    return () => clearTimeout(t);
  }, [trigger, map]);
  return null;
}

export default function MapPanel({
  zones = [],
  strikes = [],
  center = LOURDES,
  radiusKm = LOURDES.radius,
  fullscreen = false,
  onToggleFullscreen,
  cursorTs = null,
  isLive = true,
}) {
  const centerLL = useMemo(() => [center.lat, center.lon], [center.lat, center.lon]);
  const centerIcon = useMemo(() => buildCenterIcon(), []);
  const userIcon = useMemo(() => buildUserIcon(), []);
  const [zoom] = useState(11);
  const [userPos, setUserPos] = useState(null);
  const [locating, setLocating] = useState(false);
  const [locError, setLocError] = useState(null);

  const locate = () => {
    if (!navigator.geolocation) {
      setLocError("Géolocalisation non supportée");
      setTimeout(() => setLocError(null), 3000);
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setUserPos([pos.coords.latitude, pos.coords.longitude]);
        setLocating(false);
      },
      () => {
        setLocError("Position indisponible");
        setLocating(false);
        setTimeout(() => setLocError(null), 3000);
      },
      { enableHighAccuracy: true, timeout: 10000 }
    );
  };

  const now = Date.now() / 1000;
  const wx = useWeatherLayersState({ cursorTs, isLive });
  const isMobile = useIsMobile();
  const [fitSignal, setFitSignal] = useState(0);
  // Auto-zoom to 7 when Rain is active (to see broader storm context beyond 20-70km)
  const zoomOverride = wx.showRain ? 7 : null;

  return (
    <div className="relative h-full w-full" data-testid="map-panel">
      <MapContainer
        center={centerLL}
        zoom={zoom}
        minZoom={2}
        maxZoom={18}
        scrollWheelZoom
        zoomControl
        worldCopyJump
        style={{ height: "100%", width: "100%" }}
      >
        <TileLayer
          attribution='&copy; <a href="https://carto.com/attributions">CARTO</a> &copy; OpenStreetMap'
          url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
          minZoom={2}
          maxZoom={20}
        />
        <WeatherTileLayer url={wx.url} showClouds={wx.showClouds} showRain={wx.showRain} />
        <WindLayer
          center={center}
          radiusKm={radiusKm}
          enabled={wx.showWind}
          onMaxSpeedChange={wx.setWindMaxSpeed}
        />
        <TrajectoryLayer
          center={center}
          enabled={wx.showTrajectory}
          fitSignal={fitSignal}
          cursorTs={cursorTs}
          isLive={isLive}
        />
        <FitToRadius center={centerLL} radiusKm={radiusKm} override={zoomOverride} />
        <InvalidateOnResize trigger={fullscreen} />
        <Circle
          center={centerLL}
          radius={radiusKm * 1000}
          pathOptions={{
            color: "#0F172A",
            weight: 2,
            dashArray: "6 8",
            fillColor: "#0F172A",
            fillOpacity: 0.04,
          }}
        />
        <Marker position={centerLL} icon={centerIcon} />
        {userPos && <Marker position={userPos} icon={userIcon} />}
        {zones.map((z, i) => (
          <Marker
            key={`zone-${z.lat}-${z.lon}-${i}`}
            position={[z.lat, z.lon]}
            icon={buildStormIcon(z)}
          />
        ))}
        {strikes.map((s, i) => (
          <Marker
            key={`strike-${s.ts}-${i}`}
            position={[s.lat, s.lon]}
            icon={buildStrikeIcon(now - s.ts)}
          />
        ))}
      </MapContainer>

      {/* Floating legend - bottom left */}
      <div
        className="absolute bottom-6 left-6 z-[500] bg-white border border-slate-200 p-4 shadow-[0_2px_16px_rgba(0,0,0,0.04)]"
        data-testid="map-legend"
      >
        <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400 mb-3">Légende</div>
        <div className="flex flex-col gap-2 text-xs">
          <div className="flex items-center gap-3">
            <span className="w-3 h-3 rounded-full" style={{ background: "#10B981" }} />
            <span className="text-slate-700">Calme</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="w-3 h-3 rounded-full" style={{ background: "#D97706" }} />
            <span className="text-slate-700">Convectif</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="w-3 h-3 rounded-full" style={{ background: "#DC2626" }} />
            <span className="text-slate-700">Orageux</span>
          </div>
          <div className="flex items-center gap-3 border-t border-slate-100 pt-2 mt-1">
            <svg viewBox="0 0 24 24" width="14" height="14">
              <path
                d="M13 2L3 14h7l-1 8 11-12h-7l0-8z"
                fill="#FDE047"
                stroke="#FACC15"
                strokeWidth="1.5"
                strokeLinejoin="round"
              />
            </svg>
            <span className="text-slate-700">Impact foudre</span>
          </div>
        </div>
      </div>

      {/* Floating map title */}
      <div className="absolute top-6 left-6 z-[500] bg-white/90 backdrop-blur-md border border-slate-200 px-5 py-3">
        <div className="text-[10px] font-mono uppercase tracking-[0.3em] text-slate-400">Zone surveillée</div>
        <div className="font-heading text-lg font-bold text-slate-900 leading-tight">
          Lourdes · {radiusKm} km
        </div>
        <div className="font-mono text-[10px] text-slate-500 mt-1">
          43.0951°N · -0.0434°E
        </div>
      </div>

      {/* Floating controls - top right */}
      <div className="absolute top-6 right-6 z-[500] flex flex-col gap-2">
        <button
          onClick={locate}
          disabled={locating}
          className="w-11 h-11 bg-white border border-slate-200 hover:bg-slate-900 hover:text-white hover:border-slate-900 transition-colors flex items-center justify-center shadow-[0_2px_16px_rgba(0,0,0,0.04)] disabled:opacity-50"
          title="Ma position"
          aria-label="Ma position"
          data-testid="geolocate-button"
        >
          <Crosshair className={`w-5 h-5 ${locating ? "animate-spin" : ""}`} strokeWidth={1.8} />
        </button>
        <button
          onClick={onToggleFullscreen}
          className="w-11 h-11 bg-white border border-slate-200 hover:bg-slate-900 hover:text-white hover:border-slate-900 transition-colors flex items-center justify-center shadow-[0_2px_16px_rgba(0,0,0,0.04)]"
          title={fullscreen ? "Quitter le plein écran" : "Plein écran"}
          aria-label="Plein écran"
          data-testid="fullscreen-button"
        >
          {fullscreen ? <Minimize2 className="w-5 h-5" strokeWidth={1.8} /> : <Maximize2 className="w-5 h-5" strokeWidth={1.8} />}
        </button>
      </div>

      {locError && (
        <div className="absolute top-20 right-6 z-[500] bg-red-50 border border-red-200 px-4 py-2 text-xs text-red-800 font-mono">
          {locError}
        </div>
      )}

      {strikes.length > 0 && (
        <div className="absolute top-32 right-6 z-[500] bg-white border border-red-200 px-4 py-3 shadow-[0_2px_16px_rgba(0,0,0,0.04)]" data-testid="strikes-badge">
          <div className="flex items-center gap-3">
            <span className="live-dot" />
            <div>
              <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400">Impacts 1h</div>
              <div className="font-mono text-lg font-medium text-slate-900 leading-none mt-1">
                {strikes.length}
              </div>
            </div>
          </div>
        </div>
      )}

      <WeatherLayersPanel {...wx} isMobile={isMobile} timelineDriven />
      <TrajectoryBadge
        center={center}
        enabled={wx.showTrajectory}
        onFit={() => setFitSignal((s) => s + 1)}
        cursorTs={cursorTs}
        isLive={isLive}
      />
    </div>
  );
}
