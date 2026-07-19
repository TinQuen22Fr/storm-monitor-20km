import { useEffect, useState } from "react";
import { Marker, useMap } from "react-leaflet";
import L from "leaflet";
import { api } from "@/lib/api";

function colorForSpeed(kmh) {
  if (kmh < 15) return "#64748B"; // slate-500
  if (kmh < 30) return "#0EA5E9"; // sky-500
  if (kmh < 50) return "#F59E0B"; // amber-500
  if (kmh < 70) return "#EA580C"; // orange-600
  return "#DC2626"; // red-600
}

function buildArrowIcon(speed, direction) {
  const color = colorForSpeed(speed);
  const size = Math.max(22, Math.min(42, 22 + speed / 2));
  const rot = (direction + 180) % 360;
  const label = Math.round(speed);
  const delay = (Math.random() * 1.5).toFixed(2);
  // Rotation sur le conteneur (style inline), animation UNIQUEMENT sur le svg
  // interne : une animation de `transform` sur le conteneur écraserait la
  // rotation inline. Le label vitesse est hors du repère tourné, sous la flèche.
  return L.divIcon({
    className: "",
    html: `<div style="width:${size}px;height:${size + 14}px;position:relative">
      <div style="width:${size}px;height:${size}px;transform:rotate(${rot}deg);transform-origin:center">
        <svg class="wind-arrow-anim" viewBox="0 0 24 24" width="${size}" height="${size}" style="animation-delay:${delay}s;filter:drop-shadow(0 1px 1px rgba(0,0,0,0.25))">
          <path d="M12 2 L16 10 L13 10 L13 22 L11 22 L11 10 L8 10 Z"
                fill="${color}" stroke="#ffffff" stroke-width="1" stroke-linejoin="round" />
        </svg>
      </div>
      <span style="position:absolute;left:50%;top:${size}px;transform:translateX(-50%);font-family:'IBM Plex Mono',monospace;font-size:9px;font-weight:700;line-height:1;color:#fff;background:rgba(15,23,42,0.75);padding:1px 4px;border-radius:6px;white-space:nowrap;pointer-events:none">${label} km/h</span>
    </div>`,
    iconSize: [size, size + 14],
    iconAnchor: [size / 2, size / 2],
  });
}

export default function WindLayer({ center, radiusKm, enabled, onMaxSpeedChange }) {
  const [arrows, setArrows] = useState([]);
  const map = useMap();

  useEffect(() => {
    if (!enabled) {
      setArrows([]);
      onMaxSpeedChange && onMaxSpeedChange(null);
      return;
    }
    let cancel = false;
    const load = async () => {
      try {
        const { data } = await api.get("/weather/wind-grid", {
          params: { lat: center.lat, lon: center.lon, radius_km: radiusKm },
        });
        if (cancel) return;
        setArrows(data.arrows || []);
        onMaxSpeedChange && onMaxSpeedChange(data.max_speed);
      } catch { /* ignore */ }
    };
    // Chargement uniquement à l'activation de la couche (pas de polling)
    load();
    return () => {
      cancel = true;
    };
  }, [enabled, center.lat, center.lon, radiusKm, onMaxSpeedChange]);

  // Ensure a dedicated pane above markers
  useEffect(() => {
    if (!map.getPane("windPane")) {
      map.createPane("windPane");
      map.getPane("windPane").style.zIndex = 650;
      map.getPane("windPane").style.pointerEvents = "none";
    }
  }, [map]);

  if (!enabled) return null;

  return (
    <>
      {arrows.map((a, i) => (
        <Marker
          key={`wind-${a.lat}-${a.lon}-${i}`}
          position={[a.lat, a.lon]}
          icon={buildArrowIcon(a.speed, a.direction)}
          pane="windPane"
          interactive={false}
        />
      ))}
    </>
  );
}
