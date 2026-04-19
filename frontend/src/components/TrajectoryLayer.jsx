import { useEffect, useState } from "react";
import L from "leaflet";
import { CircleMarker, Polyline, useMap } from "react-leaflet";
import { api } from "@/lib/api";

export default function TrajectoryLayer({ center, enabled = true, fitSignal = 0 }) {
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
        const { data } = await api.get("/storms/trajectory", {
          params: { lat: center.lat, lon: center.lon, radius_km: 70, project_minutes: 45 },
        });
        if (!cancel) setTraj(data?.detected ? data : null);
      } catch { /* ignore */ }
    };
    load();
    const t = setInterval(load, 30_000);
    return () => {
      cancel = true;
      clearInterval(t);
    };
  }, [enabled, center.lat, center.lon]);

  // Click-to-fit: when fitSignal increments, zoom map to include trajectory + center
  useEffect(() => {
    if (!fitSignal || !traj || !traj.waypoints?.length) return;
    const points = traj.waypoints.map((w) => [w.lat, w.lon]);
    const bounds = L.latLngBounds([...points, [center.lat, center.lon]]);
    map.flyToBounds(bounds, { padding: [60, 60], duration: 0.8, maxZoom: 10 });
  }, [fitSignal, traj, center.lat, center.lon, map]);

  if (!traj || !traj.waypoints?.length) return null;

  const points = traj.waypoints.map((w) => [w.lat, w.lon]);
  const head = traj.waypoints[traj.waypoints.length - 1];

  return (
    <>
      <Polyline
        positions={points}
        pathOptions={{
          color: "#DC2626",
          weight: 3,
          opacity: 0.9,
          className: "trajectory-path",
        }}
        pane="trajectoryPane"
      />
      {/* Starting point */}
      <CircleMarker
        center={[points[0][0], points[0][1]]}
        radius={5}
        pathOptions={{
          color: "#0F172A",
          fillColor: "#DC2626",
          fillOpacity: 1,
          weight: 2,
        }}
        pane="trajectoryPane"
      />
      {/* Head / predicted position */}
      <CircleMarker
        center={[head.lat, head.lon]}
        radius={8}
        pathOptions={{
          color: "#DC2626",
          fillColor: "#FFFFFF",
          fillOpacity: 1,
          weight: 3,
        }}
        pane="trajectoryPane"
      />
    </>
  );
}
