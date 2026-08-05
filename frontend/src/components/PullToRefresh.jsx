import { useEffect, useRef, useState } from "react";
import { RefreshCw } from "lucide-react";

const THRESHOLD = 75;

/**
 * Tirer-vers-le-bas (mobile) : quand la page est tout en haut, un balayage
 * vers le bas déclenche onRefresh(). Ignoré si le geste démarre sur la carte
 * Leaflet (pour ne pas gêner le déplacement de la carte).
 */
export default function PullToRefresh({ onRefresh }) {
  const [pull, setPull] = useState(0);
  const [busy, setBusy] = useState(false);
  const startY = useRef(null);
  const pullRef = useRef(0);
  const busyRef = useRef(false);

  useEffect(() => {
    const onStart = (e) => {
      if (busyRef.current || window.scrollY > 2 || e.touches.length !== 1) return;
      if (e.target.closest && e.target.closest(".leaflet-container")) return;
      startY.current = e.touches[0].clientY;
    };
    const onMove = (e) => {
      if (startY.current == null || busyRef.current) return;
      const dy = e.touches[0].clientY - startY.current;
      const p = dy > 0 && window.scrollY <= 2 ? Math.min(dy, 140) : 0;
      pullRef.current = p;
      setPull(p);
    };
    const onEnd = async () => {
      if (startY.current == null) return;
      const dist = pullRef.current;
      startY.current = null;
      pullRef.current = 0;
      if (dist >= THRESHOLD && !busyRef.current) {
        busyRef.current = true;
        setBusy(true);
        setPull(0);
        try { await onRefresh(); } catch { /* silencieux */ }
        busyRef.current = false;
        setBusy(false);
      } else {
        setPull(0);
      }
    };
    window.addEventListener("touchstart", onStart, { passive: true });
    window.addEventListener("touchmove", onMove, { passive: true });
    window.addEventListener("touchend", onEnd, { passive: true });
    return () => {
      window.removeEventListener("touchstart", onStart);
      window.removeEventListener("touchmove", onMove);
      window.removeEventListener("touchend", onEnd);
    };
  }, [onRefresh]);

  if (pull <= 0 && !busy) return null;
  return (
    <div
      className="fixed top-0 left-0 right-0 z-[1200] flex justify-center pointer-events-none"
      style={{ transform: `translateY(${busy ? 18 : Math.min(pull * 0.5, 60)}px)`, transition: busy ? "transform 0.15s" : "none" }}
      data-testid="pull-to-refresh-indicator"
    >
      <div className="bg-white border border-slate-300 shadow-lg rounded-full p-2.5">
        <RefreshCw
          className={`w-5 h-5 ${pull >= THRESHOLD || busy ? "text-blue-600" : "text-slate-500"} ${busy ? "animate-spin" : ""}`}
          strokeWidth={2}
          style={busy ? undefined : { transform: `rotate(${pull * 2.5}deg)`, opacity: Math.min(0.3 + pull / THRESHOLD, 1) }}
        />
      </div>
    </div>
  );
}
