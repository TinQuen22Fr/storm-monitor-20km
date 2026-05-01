import { useEffect, useRef, useState } from "react";
import { Pause, Play, Rewind } from "lucide-react";

const SPEED_OPTIONS = [1, 2, 4, 8];
const SPEED_STORAGE_KEY = "storm.timeline.speed";

/**
 * Unified 24h timeline that drives clouds + rain + strikes display in sync.
 * Props:
 *   - cursorTs (epoch seconds) current time cursor
 *   - onCursorChange(ts)
 *   - playing / setPlaying
 *   - isLive (bool) whether cursor is at "now"
 *   - onResetLive()
 */
export default function Timeline({
  cursorTs,
  onCursorChange,
  playing,
  setPlaying,
  isLive,
  onResetLive,
}) {
  const nowRef = useRef(Math.floor(Date.now() / 1000));
  const [nowTs, setNowTs] = useState(nowRef.current);
  // Playback speed multiplier — persisted across reloads
  const [speed, setSpeed] = useState(() => {
    try {
      const saved = parseInt(localStorage.getItem(SPEED_STORAGE_KEY) || "1", 10);
      return SPEED_OPTIONS.includes(saved) ? saved : 1;
    } catch { return 1; }
  });
  useEffect(() => {
    try { localStorage.setItem(SPEED_STORAGE_KEY, String(speed)); } catch { /* ignore */ }
  }, [speed]);

  // Keep "now" in sync every 30s
  useEffect(() => {
    const t = setInterval(() => setNowTs(Math.floor(Date.now() / 1000)), 30_000);
    return () => clearInterval(t);
  }, []);

  // Auto-advance every 400ms when playing & not at live.
  // We use a ref for cursorTs so that the interval is created ONCE (when
  // playing flips on) and reads the latest cursor on each tick, instead of
  // tearing down + recreating the timer at every cursor update (which made
  // the playback feel stuttering and prone to early-stop bugs).
  const cursorRef = useRef(cursorTs);
  useEffect(() => { cursorRef.current = cursorTs; }, [cursorTs]);
  const nowRefT = useRef(nowTs);
  useEffect(() => { nowRefT.current = nowTs; }, [nowTs]);

  useEffect(() => {
    if (!playing) return;
    const stepSec = 300; // 5 min per tick
    const intervalMs = Math.max(50, Math.round(400 / speed));
    const t = setInterval(() => {
      const next = cursorRef.current + stepSec;
      const limit = nowRefT.current;
      if (next >= limit) {
        onCursorChange(limit);
        setPlaying(false);
      } else {
        onCursorChange(next);
      }
    }, intervalMs);
    return () => clearInterval(t);
  }, [playing, speed, onCursorChange, setPlaying]);

  /**
   * Play button click handler.
   * When already at live, clicking Play has no meaning (nothing to advance to)
   * and the auto-stop fires immediately. We rewind by 30 min so the playback
   * has something to reveal — replay of "the last half hour".
   */
  const handlePlayClick = () => {
    if (!playing && isLive) {
      onCursorChange(nowTs - 30 * 60);
      setPlaying(true);
      return;
    }
    setPlaying((p) => !p);
  };

  const past24h = nowTs - 24 * 3600;
  const pct = ((cursorTs - past24h) / (nowTs - past24h)) * 100;

  const dateStr = new Date(cursorTs * 1000).toLocaleString("fr-FR", {
    weekday: "short",
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });

  const minutesAgo = Math.round((nowTs - cursorTs) / 60);

  const PRESETS = [
    { label: "Maintenant", offset: 0 },
    { label: "-30 min", offset: 30 * 60 },
    { label: "-1 h", offset: 3600 },
    { label: "-3 h", offset: 3 * 3600 },
    { label: "-6 h", offset: 6 * 3600 },
    { label: "-12 h", offset: 12 * 3600 },
  ];

  const activePreset = PRESETS.reduce((best, p) => {
    const diff = Math.abs(nowTs - p.offset - cursorTs);
    return !best || diff < best.diff ? { ...p, diff } : best;
  }, null);

  return (
    <div
      className="relative bg-white border-t border-slate-200 w-full shrink-0"
      data-testid="timeline"
    >
      <div className="flex items-center gap-3 px-4 py-3">
        <button
          onClick={handlePlayClick}
          className="w-9 h-9 border border-slate-300 hover:bg-slate-900 hover:text-white hover:border-slate-900 transition-colors flex items-center justify-center shrink-0"
          data-testid="timeline-play"
          aria-label={playing ? "Pause" : "Lecture"}
          title={!playing && isLive ? "Rejouer les 30 dernières minutes" : (playing ? "Pause" : "Lecture")}
        >
          {playing ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
        </button>

        {/* Speed selector — cycles ×1 → ×2 → ×4 → ×8 → ×1 */}
        <button
          type="button"
          onClick={() => {
            const idx = SPEED_OPTIONS.indexOf(speed);
            const next = SPEED_OPTIONS[(idx + 1) % SPEED_OPTIONS.length];
            setSpeed(next);
          }}
          className={`h-9 px-2.5 border font-mono text-[11px] font-semibold tabular-nums transition-colors shrink-0 ${
            speed > 1
              ? "bg-slate-900 text-white border-slate-900"
              : "bg-white text-slate-600 border-slate-300 hover:border-slate-900 hover:text-slate-900"
          }`}
          data-testid="timeline-speed"
          aria-label={`Vitesse ×${speed}, cliquer pour changer`}
          title={`Vitesse de lecture ×${speed} (cliquer pour cycler ×1/×2/×4/×8)`}
        >
          ×{speed}
        </button>

        <div className="flex-1 min-w-0">
          <div className="flex items-baseline justify-between mb-1">
            <span
              className={`font-mono text-[10px] uppercase tracking-[0.2em] font-semibold ${
                isLive ? "text-red-600" : "text-slate-700"
              }`}
            >
              {isLive ? "● En direct" : `↺ Rejeu · il y a ${minutesAgo} min`}
            </span>
            <span className="font-mono text-[10px] text-slate-500 tabular-nums">{dateStr}</span>
          </div>
          <div className="relative">
            <input
              type="range"
              min={past24h}
              max={nowTs}
              step={60}
              value={cursorTs}
              onChange={(e) => {
                setPlaying(false);
                onCursorChange(parseInt(e.target.value, 10));
              }}
              className="w-full h-1 accent-slate-900"
              data-testid="timeline-slider"
            />
            {/* Live marker */}
            <div
              className="absolute top-0 right-0 h-3 w-[2px] bg-red-600 pointer-events-none"
              style={{ transform: "translateY(-1px)" }}
              title="Maintenant"
            />
          </div>
          <div className="flex justify-between font-mono text-[9px] uppercase tracking-wider text-slate-400 mt-1">
            <span>-24h</span>
            <span>-12h</span>
            <span>-6h</span>
            <span>-3h</span>
            <span>now</span>
          </div>
        </div>

        {!isLive && (
          <button
            onClick={onResetLive}
            className="w-9 h-9 border border-red-600 text-red-600 hover:bg-red-600 hover:text-white transition-colors flex items-center justify-center shrink-0"
            data-testid="timeline-reset-live"
            aria-label="Retour au direct"
            title="Retour au direct"
          >
            <Rewind className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      <div className="hidden sm:block border-t border-slate-100 px-4 py-2 flex items-center gap-1.5 overflow-x-auto">
        <span className="font-mono text-[9px] uppercase tracking-[0.2em] text-slate-400 shrink-0 mr-2">
          Sauter à
        </span>
        {PRESETS.map((p) => {
          const isActive = activePreset && activePreset.label === p.label && activePreset.diff < 120;
          return (
            <button
              key={p.label}
              onClick={() => {
                setPlaying(false);
                onCursorChange(nowTs - p.offset);
              }}
              className={`px-2.5 h-7 font-mono text-[10px] uppercase tracking-[0.15em] border transition-colors shrink-0 ${
                isActive
                  ? "bg-slate-900 text-white border-slate-900"
                  : "bg-white text-slate-700 border-slate-200 hover:border-slate-900 hover:text-slate-900"
              }`}
              data-testid={`timeline-preset-${p.offset}`}
            >
              {p.label}
            </button>
          );
        })}
      </div>
      <div className="sm:hidden border-t border-slate-100 px-3 py-2 flex items-center gap-1 overflow-x-auto">
        {PRESETS.map((p) => (
          <button
            key={p.label}
            onClick={() => {
              setPlaying(false);
              onCursorChange(nowTs - p.offset);
            }}
            className="px-2 h-7 font-mono text-[10px] uppercase border border-slate-200 shrink-0"
            data-testid={`timeline-preset-mobile-${p.offset}`}
          >
            {p.label}
          </button>
        ))}
      </div>
      <div
        className="absolute top-0 left-0 h-[2px] bg-slate-900 pointer-events-none transition-all"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
