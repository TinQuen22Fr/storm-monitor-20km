import { useEffect, useRef, useState } from "react";
import { Circle, MapContainer, Marker, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import { X, Volume2, VolumeX } from "lucide-react";
import { api, LOURDES } from "@/lib/api";
import { playThunder, unlockAudio, ensureThunderBuffer } from "@/lib/thunderSound";

/**
 * Fullscreen dark "Night Storm" mode.
 * - Dark CartoDB tiles
 * - Auto-zoom to encompass recent strikes within 70km
 * - Plays a thunder sound on each new visible strike (volume decreases with distance)
 */
function strikeIcon(ageSec) {
  const fresh = ageSec < 30;
  const recent = ageSec < 120;
  const color = fresh ? "#FDE047" : recent ? "#F59E0B" : "#EF4444";
  const glow = fresh ? "#FACC15" : recent ? "#D97706" : "#991B1B";
  const size = fresh ? 20 : 14;
  return L.divIcon({
    className: "",
    html: `<div style="width:${size}px;height:${size}px;position:relative;">
      ${fresh ? `<span style="position:absolute;inset:0;border-radius:50%;background:${color};opacity:0.45;animation:stormPing 1.2s ease-out infinite"></span>` : ""}
      <svg viewBox="0 0 24 24" width="${size}" height="${size}" style="filter:drop-shadow(0 0 6px ${glow})">
        <path d="M13 2L3 14h7l-1 8 11-12h-7l0-8z" fill="${color}" stroke="${glow}" stroke-width="1.5" stroke-linejoin="round"/>
      </svg>
    </div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

function AutoFit({ strikes, center }) {
  const map = useMap();
  useEffect(() => {
    if (!strikes.length) {
      map.setView([center.lat, center.lon], 9, { animate: true });
      return;
    }
    const points = strikes.map((s) => [s.lat, s.lon]);
    points.push([center.lat, center.lon]);
    const bounds = L.latLngBounds(points);
    map.flyToBounds(bounds, { padding: [40, 40], duration: 0.6, maxZoom: 11 });
  }, [strikes, center.lat, center.lon, map]);
  return null;
}

/* Son géré par @/lib/thunderSound (AudioContext partagé, débloqué au geste utilisateur) */

export default function NightStormMode({ open, onClose, center = LOURDES }) {
  const [strikes, setStrikes] = useState([]);
  const [soundOn, setSoundOn] = useState(true);
  const seenTs = useRef(new Set());
  const now = Date.now() / 1000;

  useEffect(() => {
    if (!open) return;
    let cancel = false;
    const load = async () => {
      try {
        const since = Date.now() / 1000 - 30 * 60;
        const { data } = await api.get("/lightning/strikes", {
          params: { lat: center.lat, lon: center.lon, radius_km: 70, since },
        });
        if (cancel) return;
        const all = data.strikes || [];
        // Nouveaux impacts visibles → tonnerre, volume dégressif avec la distance
        const fresh = all.filter(
          (s) => !seenTs.current.has(s.ts) && (Date.now() / 1000 - s.ts) < 300
        );
        if (soundOn && fresh.length > 0 && seenTs.current.size > 0) {
          const minDist = Math.min(...fresh.map((s) => s.distance_km ?? 70));
          const volume = Math.max(0.25, 0.9 * (1 - minDist / 100));
          playThunder(false, volume);
        }
        for (const s of all) seenTs.current.add(s.ts);
        setStrikes(all);
      } catch { /* ignore */ }
    };
    load();
    const t = setInterval(load, 10_000);
    return () => {
      cancel = true;
      clearInterval(t);
    };
  }, [open, center.lat, center.lon, soundOn]);

  useEffect(() => {
    if (open) {
      document.body.style.overflow = "hidden";
      unlockAudio();
    } else {
      document.body.style.overflow = "";
      seenTs.current = new Set();
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  if (!open) return null;

  const nearest = strikes.reduce(
    (m, s) => (m === null || s.distance_km < m.distance_km ? s : m),
    null
  );

  return (
    <div
      className="fixed inset-0 z-[2000] bg-black text-white"
      data-testid="night-storm-mode"
    >
      <MapContainer
        center={[center.lat, center.lon]}
        zoom={9}
        scrollWheelZoom
        zoomControl={false}
        style={{ height: "100%", width: "100%", background: "#0F172A" }}
      >
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          attribution='&copy; CARTO &copy; OSM'
          maxZoom={19}
        />
        <AutoFit strikes={strikes} center={center} />
        <Circle
          center={[center.lat, center.lon]}
          radius={20 * 1000}
          pathOptions={{
            color: "#EF4444",
            weight: 1.5,
            dashArray: "4 6",
            fillOpacity: 0,
          }}
        />
        <Circle
          center={[center.lat, center.lon]}
          radius={70 * 1000}
          pathOptions={{
            color: "#64748B",
            weight: 1,
            dashArray: "2 8",
            fillOpacity: 0,
          }}
        />
        <Marker
          position={[center.lat, center.lon]}
          icon={L.divIcon({
            className: "",
            html: `<div style="width:14px;height:14px;border-radius:50%;background:#EF4444;border:3px solid #fff;box-shadow:0 0 0 2px #EF4444,0 0 20px #EF4444"></div>`,
            iconSize: [14, 14],
            iconAnchor: [7, 7],
          })}
        />
        {strikes.map((s, i) => (
          <Marker
            key={`${s.ts}-${i}`}
            position={[s.lat, s.lon]}
            icon={strikeIcon(now - s.ts)}
          />
        ))}
      </MapContainer>

      {/* Top bar */}
      <div className="absolute top-0 left-0 right-0 z-[3000] bg-gradient-to-b from-black/95 to-transparent px-6 py-4 flex items-center justify-between pointer-events-auto">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.3em] text-red-500 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
            Mode soirée orage
          </div>
          <div className="font-heading text-2xl font-black tracking-tight text-white mt-1">
            {strikes.length} impact{strikes.length !== 1 ? "s" : ""} · 30 dernières min
          </div>
          {nearest && (
            <div className="font-mono text-xs text-slate-300 mt-1">
              Le plus proche à {nearest.distance_km.toFixed(1)} km
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={async () => {
              const next = !soundOn;
              setSoundOn(next);
              if (next) {
                await unlockAudio();
                // Attend le décodage du .wav pour jouer LE fichier, pas le repli
                await ensureThunderBuffer();
                playThunder(true);
              }
            }}
            className={`w-11 h-11 border flex items-center justify-center transition-colors ${
              soundOn
                ? "bg-red-600 border-red-600 text-white"
                : "bg-transparent border-slate-600 text-slate-400 hover:text-white"
            }`}
            title={soundOn ? "Couper le son" : "Activer le son"}
            data-testid="night-mode-sound"
          >
            {soundOn ? <Volume2 className="w-5 h-5" /> : <VolumeX className="w-5 h-5" />}
          </button>
          <button
            onClick={onClose}
            className="w-11 h-11 border border-slate-600 bg-transparent text-slate-400 hover:text-white hover:border-white transition-colors flex items-center justify-center"
            title="Quitter le mode soirée"
            data-testid="night-mode-close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Bottom legend */}
      <div className="absolute bottom-6 left-6 z-[3000] flex items-center gap-5 text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400 bg-black/80 backdrop-blur px-4 py-2 border border-slate-800 pointer-events-auto">
        <span className="flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-yellow-300" />&lt;30s</span>
        <span className="flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-orange-500" />&lt;2min</span>
        <span className="flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-red-600" />Plus ancien</span>
        <span className="text-slate-600 pl-2 border-l border-slate-800">Auto-zoom · Son impacts &lt; 30 km</span>
      </div>
    </div>
  );
}
