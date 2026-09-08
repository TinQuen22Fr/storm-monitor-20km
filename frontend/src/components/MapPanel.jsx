import { useEffect, useMemo, useState } from "react";
import { Circle, MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import { Crosshair, Maximize2, Minimize2, Sun, Moon, Globe, Radio, EyeOff } from "lucide-react";
import { toast } from "sonner";
import { LOURDES, getObservations, adminUpdateObservationStatus } from "@/lib/api";
import { useAuth } from "@/lib/auth";
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

// Fonds de carte Esri (gratuits, sans clé API)
const BASEMAPS = {
  clair: {
    base: "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
    labels: "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}",
    maxNative: 16,
    attribution: 'Tiles &copy; <a href="https://www.esri.com/">Esri</a> &mdash; Esri, HERE, Garmin &copy; OpenStreetMap contributors',
  },
  sombre: {
    base: "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
    labels: "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}",
    maxNative: 16,
    attribution: 'Tiles &copy; <a href="https://www.esri.com/">Esri</a> &mdash; Esri, HERE, Garmin &copy; OpenStreetMap contributors',
  },
  satellite: {
    base: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    labels: "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
    maxNative: 19,
    attribution: 'Tiles &copy; <a href="https://www.esri.com/">Esri</a> &mdash; Source: Esri, Maxar, Earthstar Geographics',
  },
};

function buildCenterIcon() {
  return L.divIcon({
    className: "",
    html: `<div class="center-pin" data-testid="map-center-pin"></div>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
  });
}

function buildOverlayCenterIcon(name) {
  // Smaller, blue-toned center pin for secondary zones, labelled with the place name
  const label = (name || "").replace(/[<>&"']/g, "");
  return L.divIcon({
    className: "",
    html: `<div style="display:flex;align-items:center;gap:6px;transform:translateX(8px)">
      <span style="width:10px;height:10px;border-radius:9999px;background:#2563EB;border:2px solid #fff;box-shadow:0 0 0 1px #2563EB"></span>
      <span style="font:600 10px/1 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.04em;background:rgba(255,255,255,.92);border:1px solid #DBEAFE;color:#1E3A8A;padding:3px 6px;white-space:nowrap;box-shadow:0 1px 4px rgba(0,0,0,.06)">${label}</span>
    </div>`,
    iconSize: [10, 10],
    iconAnchor: [5, 5],
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

// ---------- Observations terrain communautaires (C2) ----------
const OBSERVATION_TYPE_PRIORITY = ["hail", "wind_gust", "thunder", "lightning", "rain_heavy"];
const OBSERVATION_TYPE_META = {
  thunder: { emoji: "\u{1F329}\uFE0F", label: "Tonnerre" },
  lightning: { emoji: "\u26A1", label: "\u00C9clairs" },
  hail: { emoji: "\u{1F9CA}", label: "Gr\u00EAle" },
  rain_heavy: { emoji: "\u{1F327}\uFE0F", label: "Pluie intense" },
  wind_gust: { emoji: "\u{1F4A8}", label: "Fortes rafales" },
};

function pickPriorityObservationType(types = []) {
  for (const t of OBSERVATION_TYPE_PRIORITY) {
    if (types.includes(t)) return t;
  }
  return types[0];
}

function buildObservationIcon(obs) {
  const priorityType = pickPriorityObservationType(obs.types || []);
  const meta = OBSERVATION_TYPE_META[priorityType];
  const emoji = meta ? meta.emoji : "\u{1F4E1}";
  const color = "#F59E0B"; // amber-500
  const border = "#FFFFFF";
  return L.divIcon({
    className: "",
    html: `<div class="storm-marker-wrapper" style="width:22px;height:22px">
      <span class="storm-marker-ping" style="background:${color}"></span>
      <div class="storm-marker-core" style="width:22px;height:22px;background:${color};border:2px solid ${border};box-shadow:0 0 0 1px ${color},0 2px 6px rgba(0,0,0,0.35);display:flex;align-items:center;justify-content:center;font-size:12px;line-height:1">${emoji}</div>
    </div>`,
    iconSize: [22, 22],
    iconAnchor: [11, 11],
    popupAnchor: [0, -11],
  });
}

function formatRelativeMinutes(timestamp) {
  const ageSec = Math.max(0, Date.now() / 1000 - timestamp);
  const minutes = Math.floor(ageSec / 60);
  if (minutes < 1) return "\u00E0 l'instant";
  if (minutes < 60) return `il y a ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const restMin = minutes % 60;
  return `il y a ${hours} h${restMin > 0 ? ` ${restMin} min` : ""}`;
}

function FitToRadius({ center, radiusKm, recenterSignal = 0 }) {
  const map = useMap();
  useEffect(() => {
    const zoomForRadius = radiusKm >= 60 ? 9 : radiusKm >= 40 ? 10 : 11;
    map.setView(center, zoomForRadius, { animate: true });
  }, [center, radiusKm, map, recenterSignal]);
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
  overlays = [],
  noZone = false,
  recenterSignal = 0,
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

  const [basemap, setBasemap] = useState(() => {
    try { return localStorage.getItem("storm_basemap") || "clair"; } catch { return "clair"; }
  });
  const bm = BASEMAPS[basemap] || BASEMAPS.clair;
  const changeBasemap = (k) => {
    setBasemap(k);
    try { localStorage.setItem("storm_basemap", k); } catch {}
  };

  const now = Date.now() / 1000;
  const wx = useWeatherLayersState({ cursorTs, isLive });
  const isMobile = useIsMobile();
  const [fitSignal, setFitSignal] = useState(0);

  // Observations terrain communautaires (C2)
  const { user } = useAuth();
  const [observations, setObservations] = useState([]);
  const [showObservations, setShowObservations] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const loadObservations = () => {
      getObservations({ window_s: 7200 })
        .then((data) => {
          if (cancelled) return;
          const list = Array.isArray(data) ? data : [];
          setObservations(list.filter((o) => o && typeof o.lat === "number" && typeof o.lon === "number"));
        })
        .catch(() => {
          // Silencieux : on n'interrompt pas la carte si les observations échouent
        });
    };
    loadObservations();
    const intervalId = setInterval(loadObservations, 45000);
    return () => {
      cancelled = true;
      clearInterval(intervalId);
    };
  }, []);

  const handleHideObservation = async (obsId) => {
    try {
      await adminUpdateObservationStatus(obsId, "hidden");
      setObservations((prev) => prev.filter((o) => o.id !== obsId));
      toast.success("Observation masquée");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Erreur lors de la modération");
    }
  };

  return (
    <div className="relative h-full w-full flex flex-col" data-testid="map-panel">
      <div className="relative h-[60vh] lg:h-auto lg:flex-1 lg:min-h-0">
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
          key={`base-${basemap}`}
          attribution={bm.attribution}
          url={bm.base}
          minZoom={2}
          maxZoom={20}
          maxNativeZoom={bm.maxNative}
        />
        <TileLayer
          key={`labels-${basemap}`}
          url={bm.labels}
          minZoom={2}
          maxZoom={20}
          maxNativeZoom={bm.maxNative}
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
        <FitToRadius center={centerLL} radiusKm={radiusKm} recenterSignal={recenterSignal} />
        <InvalidateOnResize trigger={fullscreen} />
        {!noZone && (
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
        )}
        {/* Repère fixe : zone cruciale des 20 km (rouge), visible dès que le rayon dépasse 20 km */}
        {!noZone && radiusKm > 20 && (
          <Circle
            center={centerLL}
            radius={20 * 1000}
            pathOptions={{
              color: "#DC2626",
              weight: 2,
              dashArray: "4 6",
              fillColor: "#DC2626",
              fillOpacity: 0.03,
            }}
          />
        )}
        {!noZone && <Marker position={centerLL} icon={centerIcon} />}
        {userPos && <Marker position={userPos} icon={userIcon} />}
        {/* Secondary monitoring zones (multi-favoris) */}
        {overlays.map((ov) => (
          <Circle
            key={`ov-circle-${ov.id}`}
            center={[ov.lat, ov.lon]}
            radius={(ov.radiusKm ?? radiusKm) * 1000}
            pathOptions={{
              color: "#2563EB",
              weight: 1.5,
              dashArray: "4 6",
              fillColor: "#2563EB",
              fillOpacity: 0.05,
            }}
          />
        ))}
        {/* Repère fixe 20 km sur chaque zone favorite secondaire */}
        {overlays
          .filter((ov) => (ov.radiusKm ?? radiusKm) > 20)
          .map((ov) => (
            <Circle
              key={`ov-circle20-${ov.id}`}
              center={[ov.lat, ov.lon]}
              radius={20 * 1000}
              pathOptions={{
                color: "#DC2626",
                weight: 2,
                dashArray: "4 6",
                fillColor: "#DC2626",
                fillOpacity: 0.03,
              }}
            />
          ))}
        {overlays.map((ov) => (
          <Marker
            key={`ov-marker-${ov.id}`}
            position={[ov.lat, ov.lon]}
            icon={buildOverlayCenterIcon(ov.name)}
          />
        ))}
        {overlays.flatMap((ov) =>
          (ov.zones || []).map((z, i) => (
            <Marker
              key={`ov-zone-${ov.id}-${z.lat}-${z.lon}-${i}`}
              position={[z.lat, z.lon]}
              icon={buildStormIcon(z)}
            />
          ))
        )}
        {overlays.flatMap((ov) =>
          (ov.strikes || []).map((s, i) => (
            <Marker
              key={`ov-strike-${ov.id}-${s.ts}-${i}`}
              position={[s.lat, s.lon]}
              icon={buildStrikeIcon(now - s.ts)}
            />
          ))
        )}
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
        {/* Observations terrain communautaires (C2) */}
        {showObservations &&
          observations.map((obs) => (
            <Marker
              key={`obs-${obs.id}`}
              position={[obs.lat, obs.lon]}
              icon={buildObservationIcon(obs)}
              data-testid="observation-marker"
            >
              <Popup>
                <div className="min-w-[180px] font-mono text-xs">
                  <div className="font-heading text-sm font-bold text-slate-900">
                    {obs.user_name || "Observateur local"}
                  </div>
                  <div className="text-slate-500 mt-0.5">{formatRelativeMinutes(obs.timestamp)}</div>
                  <div className="flex flex-wrap gap-1 mt-2">
                    {(obs.types || []).map((t) => {
                      const meta = OBSERVATION_TYPE_META[t];
                      if (!meta) return null;
                      return (
                        <span
                          key={t}
                          className="inline-flex items-center gap-1 bg-amber-50 border border-amber-200 text-amber-800 px-2 py-0.5"
                        >
                          {meta.emoji} {meta.label}
                        </span>
                      );
                    })}
                  </div>
                  {obs.comment && (
                    <div className="italic text-slate-600 mt-2 border-t border-slate-200 pt-2">
                      "{obs.comment}"
                    </div>
                  )}
                  {user?.is_admin && (
                    <button
                      onClick={() => handleHideObservation(obs.id)}
                      className="mt-3 w-full flex items-center justify-center gap-1.5 border-t border-slate-200 pt-2 text-red-600 hover:text-red-700 hover:bg-red-50 transition-colors text-[10px] uppercase tracking-wider font-mono py-1"
                      data-testid={`admin-hide-observation-${obs.id}`}
                    >
                      <EyeOff className="w-3 h-3" />
                      Masquer l'observation
                    </button>
                  )}
                </div>
              </Popup>
            </Marker>
          ))}
      </MapContainer>

      {/* Floating legend - bottom left — DESKTOP ONLY */}
      <div
        className="hidden md:block absolute bottom-6 left-6 z-[500] bg-white border border-slate-200 p-4 shadow-[0_2px_16px_rgba(0,0,0,0.04)]"
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

      {/* Floating map title — DESKTOP layout. On mobile, compact version moved below */}
      <div className="hidden md:block absolute top-6 left-6 z-[500] bg-white/90 backdrop-blur-md border border-slate-200 px-5 py-3 max-w-[280px]">
        <div className="text-[10px] font-mono uppercase tracking-[0.3em] text-slate-400">Zone surveillée</div>
        {noZone ? (
          <div className="font-heading text-base font-bold text-blue-700 leading-tight mt-1">
            Aucune zone sélectionnée
          </div>
        ) : (
          <>
            <div className="font-heading text-lg font-bold text-slate-900 leading-tight truncate">
              {center.name} · {radiusKm} km
            </div>
            <div className="font-mono text-[10px] text-slate-500 mt-1 tabular-nums">
              {center.lat.toFixed(4)}°N · {center.lon.toFixed(4)}°E
            </div>
          </>
        )}
        {overlays.length > 0 && (
          <div className="mt-2 pt-2 border-t border-slate-200 font-mono text-[10px] text-blue-700 uppercase tracking-[0.15em]">
            {noZone ? "" : "+ "}{overlays.length} zone{overlays.length > 1 ? "s" : ""}{noZone ? " visible" : " secondaire"}{overlays.length > 1 ? "s" : ""}
          </div>
        )}
      </div>

      {/* Floating controls - top right */}
      <div className="absolute top-6 right-6 z-[500] flex flex-col gap-2 items-end">
        <div
          className="flex bg-white border border-slate-200 shadow-[0_2px_16px_rgba(0,0,0,0.04)] overflow-hidden"
          data-testid="basemap-selector"
        >
          {[
            { k: "clair", Icon: Sun, label: "Clair" },
            { k: "sombre", Icon: Moon, label: "Sombre" },
            { k: "satellite", Icon: Globe, label: "Satellite" },
          ].map(({ k, Icon, label }) => (
            <button
              key={k}
              onClick={() => changeBasemap(k)}
              className={`w-11 h-11 flex items-center justify-center transition-colors ${
                basemap === k ? "bg-slate-900 text-white" : "bg-white text-slate-600 hover:bg-slate-100"
              }`}
              title={`Fond ${label}`}
              aria-label={`Fond de carte ${label}`}
              data-testid={`basemap-${k}`}
            >
              <Icon className="w-5 h-5" strokeWidth={1.8} />
            </button>
          ))}
        </div>
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
          onClick={() => setShowObservations((v) => !v)}
          className={`relative w-11 h-11 border transition-colors flex items-center justify-center shadow-[0_2px_16px_rgba(0,0,0,0.04)] ${
            showObservations
              ? "bg-amber-500 text-white border-amber-500 hover:bg-amber-600"
              : "bg-white text-slate-600 border-slate-200 hover:bg-slate-900 hover:text-white hover:border-slate-900"
          }`}
          title={showObservations ? "Masquer les observations citoyennes" : "Afficher les observations citoyennes"}
          aria-label="Observations citoyennes"
          aria-pressed={showObservations}
          data-testid="toggle-observations-layer"
        >
          <Radio className="w-5 h-5" strokeWidth={1.8} />
          {showObservations && observations.length > 0 && (
            <span className="absolute -top-1.5 -right-1.5 min-w-[18px] h-[18px] px-1 bg-slate-900 text-white text-[10px] font-mono font-bold rounded-full flex items-center justify-center border border-white">
              {observations.length}
            </span>
          )}
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
        <div className="absolute top-48 right-6 z-[500] bg-red-50 border border-red-200 px-4 py-2 text-xs text-red-800 font-mono">
          {locError}
        </div>
      )}

      {strikes.length > 0 && (
        <div className="absolute top-[188px] right-6 z-[500] bg-white border border-red-200 px-4 py-3 shadow-[0_2px_16px_rgba(0,0,0,0.04)]" data-testid="strikes-badge">
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

      <WeatherLayersPanel {...wx} isMobile={false} timelineDriven hideOnMobile />
      <TrajectoryBadge
        center={center}
        enabled={wx.showTrajectory && !isMobile}
        onFit={() => setFitSignal((s) => s + 1)}
        cursorTs={cursorTs}
        isLive={isLive}
      />
      </div>

      {/* ============================================================ */}
      {/* MOBILE info panel — placed BELOW the map (visible on Redmi etc) */}
      {/* All controls and info that were absolute overlays on desktop  */}
      {/* are mirrored here in static flow so the map stays clean.      */}
      {/* ============================================================ */}
      <div className="md:hidden bg-white border-t border-slate-200" data-testid="mobile-info-panel">
        {/* Zone surveillée — same content as desktop overlay */}
        <div className="px-4 py-3 border-b border-slate-100">
          <div className="text-[10px] font-mono uppercase tracking-[0.3em] text-slate-400">Zone surveillée</div>
          {noZone ? (
            <div className="font-heading text-base font-bold text-blue-700 leading-tight mt-1">
              Aucune zone sélectionnée
            </div>
          ) : (
            <>
              <div className="font-heading text-lg font-bold text-slate-900 leading-tight">
                {center.name} · {radiusKm} km
              </div>
              <div className="font-mono text-[10px] text-slate-500 mt-1 tabular-nums">
                {center.lat.toFixed(4)}°N · {center.lon.toFixed(4)}°E
              </div>
            </>
          )}
          {overlays.length > 0 && (
            <div className="mt-2 pt-2 border-t border-slate-200 font-mono text-[10px] text-blue-700 uppercase tracking-[0.15em]">
              {noZone ? "" : "+ "}{overlays.length} zone{overlays.length > 1 ? "s" : ""}{noZone ? " visible" : " secondaire"}{overlays.length > 1 ? "s" : ""}
            </div>
          )}
        </div>

        {/* Weather layer toggles (Nuages / Pluie / Vent / Trajet) */}
        <div className="border-b border-slate-100">
          <WeatherLayersPanel {...wx} isMobile timelineDriven />
        </div>

        {/* Trajectory inline detail when active */}
        {wx.showTrajectory && (
          <div className="px-4 py-3 border-b border-slate-100">
            <TrajectoryBadge
              center={center}
              enabled={wx.showTrajectory}
              onFit={() => setFitSignal((s) => s + 1)}
              cursorTs={cursorTs}
              isLive={isLive}
              inline
            />
          </div>
        )}

        {/* Full legend — same as desktop overlay */}
        <div className="px-4 py-3">
          <div className="font-mono text-[10px] uppercase tracking-[0.3em] text-slate-400 mb-2">Légende</div>
          <div className="grid grid-cols-2 gap-x-3 gap-y-2 text-[12px]">
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full" style={{ background: "#10B981" }} />
              <span className="text-slate-700">Zone calme</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full" style={{ background: "#D97706" }} />
              <span className="text-slate-700">Zone convective</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full" style={{ background: "#DC2626" }} />
              <span className="text-slate-700">Zone orageuse</span>
            </div>
            <div className="flex items-center gap-2">
              <svg viewBox="0 0 24 24" width="13" height="13">
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
      </div>
    </div>
  );
}
