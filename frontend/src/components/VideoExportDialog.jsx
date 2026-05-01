import { useEffect, useRef, useState } from "react";
import { Check, Copy, Download, Loader2, PlayCircle, Share2, Video, X } from "lucide-react";
import { api } from "@/lib/api";

/**
 * Modal dialog that orchestrates MP4 video export:
 * 1. POST /api/replay/video (optional demo_id) → job_id
 * 2. Poll /api/replay/video/{job_id} every 1.5s until done/failed
 * 3. Show <video> player + download + WhatsApp share
 *
 * Props:
 *   - open (bool)
 *   - onClose()
 *   - event: { start_ts, end_ts, label, center_lat, center_lon, id }
 *   - isDemo (bool) — if true, sends demo_id=event.id
 */
export default function VideoExportDialog({ open, onClose, event, isDemo = false }) {
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);
  const pollRef = useRef(null);

  useEffect(() => {
    if (!open || !event) return;
    let cancel = false;
    const start = async () => {
      setError(null);
      setJob(null);
      try {
        const { data } = await api.post("/replay/video", {
          start_ts: event.start_ts,
          end_ts: event.end_ts,
          lat: event.center_lat || 43.0951,
          lon: event.center_lon || -0.0434,
          radius_km: 70,
          label: event.label || "Replay Storm Monitoring",
          demo_id: isDemo ? event.id : null,
        });
        if (cancel) return;
        const jid = data.job_id;
        // Poll status
        pollRef.current = setInterval(async () => {
          try {
            const s = await api.get(`/replay/video/${jid}`);
            if (cancel) return;
            setJob(s.data);
            if (s.data.status === "done" || s.data.status === "failed") {
              clearInterval(pollRef.current);
            }
          } catch { /* ignore */ }
        }, 1500);
      } catch (e) {
        setError(e?.response?.data?.detail || "Impossible de lancer l'export vidéo");
      }
    };
    start();
    return () => {
      cancel = true;
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [open, event, isDemo]);

  if (!open) return null;

  const mp4AbsUrl = job?.mp4_url
    ? `${(process.env.REACT_APP_BACKEND_URL || "").replace(/\/$/, "")}${job.mp4_url}`
    : null;

  const copyLink = async () => {
    if (!mp4AbsUrl) return;
    try {
      await navigator.clipboard.writeText(mp4AbsUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* ignore */ }
  };

  const shareWhatsApp = () => {
    if (!mp4AbsUrl) return;
    const text = `${event?.label || "Replay"} · Storm Monitoring Lourdes\n${mp4AbsUrl}`;
    window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, "_blank", "noopener");
  };

  const progress = job?.progress ?? 0;
  const status = job?.status || "queued";

  return (
    <div
      className="fixed inset-0 z-[2000] bg-slate-900/80 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in"
      data-testid="video-export-dialog"
      role="dialog"
      aria-modal="true"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="bg-white max-w-lg w-full border border-slate-200 shadow-[0_24px_72px_rgba(0,0,0,0.25)]">
        <div className="flex items-center gap-3 px-5 py-4 border-b border-slate-200">
          <Video className="w-4 h-4 text-slate-900" strokeWidth={2.2} />
          <div className="flex-1 min-w-0">
            <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-500">
              Export MP4
            </div>
            <div className="font-heading text-base font-black tracking-tight text-slate-900 truncate">
              {event?.label || "Replay"}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="w-8 h-8 border border-slate-200 hover:bg-slate-900 hover:text-white hover:border-slate-900 transition-colors flex items-center justify-center"
            data-testid="video-export-close"
            aria-label="Fermer"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="px-5 py-5">
          {error && (
            <div className="p-4 bg-red-50 border border-red-200 text-sm text-red-700" data-testid="video-export-error">
              {error}
            </div>
          )}

          {!error && (status === "queued" || status === "running") && (
            <div className="text-center py-6" data-testid="video-export-progress">
              <Loader2 className="w-8 h-8 mx-auto text-slate-900 animate-spin mb-4" strokeWidth={1.8} />
              <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-500 mb-2">
                Génération en cours
              </div>
              <div className="font-heading text-3xl font-black tabular-nums text-slate-900 mb-3">
                {progress}%
              </div>
              <div className="h-1.5 bg-slate-100 w-full overflow-hidden">
                <div
                  className="h-full bg-slate-900 transition-all"
                  style={{ width: `${progress}%` }}
                />
              </div>
              <div className="text-xs text-slate-500 mt-4 leading-relaxed">
                Rendu Pillow + assemblage FFmpeg · peut prendre 15-45 s.
              </div>
            </div>
          )}

          {!error && status === "done" && mp4AbsUrl && (
            <div data-testid="video-export-done">
              <video
                src={mp4AbsUrl}
                controls
                autoPlay
                loop
                muted
                playsInline
                className="w-full border border-slate-200 bg-slate-900"
                data-testid="video-export-player"
              />
              <div className="flex items-center gap-2 mt-4">
                <a
                  href={mp4AbsUrl}
                  download
                  className="flex-1 h-10 flex items-center justify-center gap-2 bg-slate-900 text-white hover:bg-slate-700 transition-colors font-mono text-[10px] uppercase tracking-[0.18em]"
                  data-testid="video-download-btn"
                >
                  <Download className="w-3.5 h-3.5" strokeWidth={2.4} />
                  Télécharger
                </a>
                <button
                  type="button"
                  onClick={shareWhatsApp}
                  className="flex-1 h-10 flex items-center justify-center gap-2 border border-slate-900 text-slate-900 hover:bg-emerald-600 hover:text-white hover:border-emerald-600 transition-colors font-mono text-[10px] uppercase tracking-[0.18em]"
                  data-testid="video-whatsapp-btn"
                >
                  <Share2 className="w-3.5 h-3.5" strokeWidth={2.4} />
                  WhatsApp
                </button>
                <button
                  type="button"
                  onClick={copyLink}
                  className="w-10 h-10 border border-slate-200 hover:border-slate-900 transition-colors flex items-center justify-center"
                  data-testid="video-copy-btn"
                  title="Copier le lien"
                  aria-label="Copier le lien"
                >
                  {copied ? (
                    <Check className="w-3.5 h-3.5 text-emerald-600" strokeWidth={2.4} />
                  ) : (
                    <Copy className="w-3.5 h-3.5" strokeWidth={2.4} />
                  )}
                </button>
              </div>
              <div className="text-[10px] font-mono text-slate-400 mt-3 text-center leading-relaxed">
                Le fichier est cached 24 h sur le serveur · format MP4 H.264 720p
              </div>
            </div>
          )}

          {!error && status === "failed" && (
            <div className="p-4 bg-red-50 border border-red-200 text-sm text-red-700" data-testid="video-export-failed">
              <div className="font-semibold mb-1">Échec de la génération</div>
              <div className="text-xs font-mono">{job?.error || "Erreur inconnue"}</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
