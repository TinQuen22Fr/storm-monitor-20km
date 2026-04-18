import { useEffect, useMemo, useState } from "react";
import { Circle, MapContainer, Marker, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import { LOURDES } from "@/lib/api";

// Fix default icon paths (disable default markers)
delete L.Icon.Default.prototype._getIconUrl;

function buildCenterIcon() {
  return L.divIcon({
    className: "",
    html: `<div class="center-pin" data-testid="map-center-pin"></div>`,
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

function Recenter({ center }) {
  const map = useMap();
  useEffect(() => {
    map.setView(center, map.getZoom(), { animate: true });
  }, [center, map]);
  return null;
}

export default function MapPanel({ zones = [], center = LOURDES, radiusKm = LOURDES.radius }) {
  const centerLL = useMemo(() => [center.lat, center.lon], [center.lat, center.lon]);
  const centerIcon = useMemo(() => buildCenterIcon(), []);
  const [zoom] = useState(11);

  return (
    <div className="relative h-full w-full" data-testid="map-panel">
      <MapContainer
        center={centerLL}
        zoom={zoom}
        minZoom={9}
        maxZoom={15}
        scrollWheelZoom
        zoomControl
        style={{ height: "100%", width: "100%" }}
      >
        <TileLayer
          attribution='&copy; <a href="https://carto.com/attributions">CARTO</a> &copy; OpenStreetMap'
          url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
        />
        <Recenter center={centerLL} />
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
        {zones.map((z, i) => (
          <Marker
            key={`${z.lat}-${z.lon}-${i}`}
            position={[z.lat, z.lon]}
            icon={buildStormIcon(z)}
          />
        ))}
      </MapContainer>

      {/* Floating legend - bottom left */}
      <div
        className="absolute bottom-6 left-6 z-[500] bg-white border border-slate-200 p-4 shadow-[0_2px_16px_rgba(0,0,0,0.04)]"
        data-testid="map-legend"
      >
        <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400 mb-3">Intensité</div>
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
        </div>
      </div>

      {/* Floating map title */}
      <div className="absolute top-6 left-6 z-[500] bg-white/90 backdrop-blur-md border border-slate-200 px-5 py-3">
        <div className="text-[10px] font-mono uppercase tracking-[0.3em] text-slate-400">Zone surveillée</div>
        <div className="font-heading text-lg font-bold text-slate-900 leading-tight">
          Lourdes · 20 km
        </div>
        <div className="font-mono text-[10px] text-slate-500 mt-1">
          43.0951°N · -0.0434°E
        </div>
      </div>
    </div>
  );
}
