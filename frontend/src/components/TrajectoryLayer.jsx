import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import { Circle, CircleMarker, Polygon, Polyline, useMap } from "react-leaflet";
import { api } from "@/lib/api";

/**
 * Build an arrow polygon pointing from `from` to `to`. Returns a list of
 * [lat, lon] pairs forming a triangle/arrowhead at the `to` end.
 */
function makeArrowPolygon(from, to, widthDeg = 0.04) {
  const [lat1, lon1] = from;
  const [lat2, lon2] = to;
  // Compute bearing for perpendicular offsets
  const dLat = lat2 - lat1;
  const dLon = lon2 - lon1;
  const len = Math.hypot(dLat, dLon);
  if (len === 0) return [];
  // Perpendicular unit vector (in degrees, good enough for short distances)
  const perpLat = -dLon / len;
  const perpLon = dLat / len;
  // Arrow head is at `to`, base at 80% of the way
  const baseLat = lat1 + dLat * 0.8;
  const baseLon = lon1 + dLon * 0.8;
  return [
    [lat1 + perpLat * widthDeg * 0.4, lon1 + perpLon * widthDeg * 0.4],
    [baseLat + perpLat * widthDeg * 0.6, baseLon + perpLon * widthDeg * 0.6],
    [baseLat + perpLat * widthDeg * 1.3, baseLon + perpLon * widthDeg * 1.3],
    [lat2, lon2],
    [baseLat - perpLat * widthDeg * 1.3, baseLon - perpLon * widthDeg * 1.3],
    [baseLat - perpLat * widthDeg * 0.6, baseLon - perpLon * widthDeg * 0.6],
    [lat1 - perpLat * widthDeg * 0.4, lon1 - perpLon * widthDeg * 0.4],
  ];
}

export default function TrajectoryLayer({ center, enabled = true, fitSignal = 0, cursorTs = null, isLive = true }) {
  const [traj, setTraj] = useState(null);
  const map = useMap();

  useEffect(() => {
    if (!map.getPane("trajectoryPane")) {
      map.createPane("trajectoryPane");
      map.getPane("trajectoryPane").style.zIndex = 620;
      map.getPane("trajectoryPane").style.pointerEvents = "none";
    }
  }, [map]);

  useEffect(() => {
    if (!enabled) {
      setTraj(null);
      return;
    }
    let cancel = false;
    const load = async () => {
      try {
        const params = { lat: center.lat, lon: center.lon, radius_km: 70, project_minutes: 45 };
        if (!isLive && cursorTs) params.at_ts = cursorTs;
        const { data } = await api.get("/storms/trajectory", { params });
        if (!cancel) setTraj(data?.detected ? data : null);
      } catch { /* ignore */ }
    };
    load();
    if (!isLive) return () => { cancel = true; };
    const t = setInterval(load, 30_000);
    return () => {
      cancel = true;
      clearInterval(t);
    };
  }, [enabled, center.lat, center.lon, cursorTs, isLive]);

  const lastFitConsumed = useRef(0);
  useEffect(() => {
    // One-shot : ne cadre que sur un NOUVEAU clic utilisateur (fitSignal incrémenté),
    // jamais sur les mises à jour de trajectoire (replay/scrub) — la carte reste
    // centrée sur la ville sélectionnée.
    if (!fitSignal || fitSignal === lastFitConsumed.current) return;
    if (!traj || !traj.waypoints?.length) return;
    lastFitConsumed.current = fitSignal;
    const points = traj.waypoints.map((w) => [w.lat, w.lon]);
    const bounds = L.latLngBounds([...points, [center.lat, center.lon]]);
    map.flyToBounds(bounds, { padding: [60, 60], duration: 0.8, maxZoom: 10 });
  }, [fitSignal, traj, center.lat, center.lon, map]);

  if (!traj || !traj.waypoints?.length) return null;

  const points = traj.waypoints.map((w) => [w.lat, w.lon]);
  const head = traj.waypoints[traj.waypoints.length - 1];
  const start = traj.waypoints[0];

  // ---- Visual model — Meteorage-inspired storm-cell zones ----
  // Each waypoint becomes a semi-transparent grey "storm cell" zone.
  // Past = darker grey, future projection = lighter & dashed arrow polygon.
  const fillColor = isLive ? "#475569" : "#7C3AED";   // grey-slate when live
  const arrowColor = isLive ? "#1E293B" : "#4C1D95";  // darker shade for the arrow

  // Cell radius in meters — grows slightly for forecast points
  const baseRadiusM = 6500;
  const forecastBoost = 1200;

  return (
    <>
      {/* Storm cells along the trajectory (grey blobs) */}
      {traj.waypoints.map((w, idx) => {
        const isFuture = (w.t_offset_min ?? 0) > 0;
        const radius = baseRadiusM + (isFuture ? forecastBoost * (idx / traj.waypoints.length) : 0);
        return (
          <Circle
            key={`cell-${idx}`}
            center={[w.lat, w.lon]}
            radius={radius}
            pathOptions={{
              color: fillColor,
              weight: 0.5,
              fillColor,
              fillOpacity: isFuture ? 0.12 : 0.22,
              className: "storm-cell-zone",
            }}
            pane="trajectoryPane"
          />
        );
      })}

      {/* Thin dashed track linking the cells (subtle, no longer the main visual) */}
      <Polyline
        positions={points}
        pathOptions={{
          color: fillColor,
          weight: 1,
          opacity: 0.45,
          dashArray: "2 4",
        }}
        pane="trajectoryPane"
      />

      {/* Arrow polygon at the projection head — shows direction */}
      {points.length >= 2 && (
        <Polygon
          positions={makeArrowPolygon(points[Math.max(0, points.length - 2)], points[points.length - 1])}
          pathOptions={{
            color: arrowColor,
            fillColor: arrowColor,
            fillOpacity: 0.55,
            weight: 1.2,
          }}
          pane="trajectoryPane"
        />
      )}

      {/* Discrete starting point */}
      <CircleMarker
        center={[start.lat, start.lon]}
        radius={4}
        pathOptions={{
          color: arrowColor,
          fillColor: "#FFFFFF",
          fillOpacity: 1,
          weight: 1.5,
        }}
        pane="trajectoryPane"
      />

      {/* Subtle head marker */}
      <CircleMarker
        center={[head.lat, head.lon]}
        radius={5}
        pathOptions={{
          color: arrowColor,
          fillColor: arrowColor,
          fillOpacity: 0.9,
          weight: 1.5,
        }}
        pane="trajectoryPane"
      />
    </>
  );
}
