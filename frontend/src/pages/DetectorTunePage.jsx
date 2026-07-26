import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, CheckCircle2, Copy, Radio, RefreshCw, Sliders, Target } from "lucide-react";
import { toast } from "sonner";
import NavTabs from "@/components/NavTabs";
import { api } from "@/lib/api";
import { fmtLocalTime } from "@/lib/timeFormat";

const REFRESH_MS = 5_000;
const TARGET_HZ = 500_000;

function bigStat({ label, value, unit, accent, testId }) {
  return { label, value, unit, accent, testId };
}

function StatBlock({ tile }) {
  return (
    <div
      className={`border border-slate-200 bg-white p-6 ${tile.accent || ""}`}
      data-testid={tile.testId}
    >
      <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400 mb-2">
        {tile.label}
      </div>
      <div className="flex items-baseline gap-1">
        <span className="font-mono text-4xl font-medium text-slate-900 tabular-nums leading-none">
          {tile.value}
        </span>
        {tile.unit && <span className="font-mono text-sm text-slate-400">{tile.unit}</span>}
      </div>
    </div>
  );
}

export default function DetectorTunePage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      try {
        const { data: d } = await api.get("/detector/tune");
        if (!cancelled) {
          setData(d);
          setError(null);
        }
      } catch {
        if (!cancelled) setError("Impossible de joindre le backend");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    run();
    const t = setInterval(run, REFRESH_MS);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, []);

  const cur = data?.current;
  const sug = data?.suggestion;
  const online = !!data?.online;
  const inSpec = cur?.in_spec;

  const copySnippet = async () => {
    if (sug?.tune_cap == null) return;
    const snip = `lightning.tuneCap(${sug.tune_cap});  // suggéré par l'autotune Storm Monitor`;
    try {
      await navigator.clipboard.writeText(snip);
      toast.success("Snippet copié");
    } catch {
      toast.error("Impossible de copier");
    }
  };

  // Gauge: clamp f within [490_000, 510_000] for display
  const f = cur?.freq_hz ?? TARGET_HZ;
  const minDisp = 490_000;
  const maxDisp = 510_000;
  const gaugePct = Math.max(
    0,
    Math.min(100, ((f - minDisp) / (maxDisp - minDisp)) * 100)
  );
  // Target position in the gauge (always center if range is symmetric)
  const targetPct = ((TARGET_HZ - minDisp) / (maxDisp - minDisp)) * 100;

  return (
    <div className="min-h-screen w-full bg-slate-50/70" data-testid="detector-tune-page">
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-6 lg:px-8 py-6 flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div>
            <Link
              to="/detector"
              className="inline-flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-[0.2em] text-slate-500 hover:text-slate-900 transition-colors mb-2"
              data-testid="back-to-detector"
            >
              <ArrowLeft className="w-3 h-3" strokeWidth={2.5} />
              Retour au détecteur
            </Link>
            <div className="flex items-center gap-2 mb-1">
              <Target className="w-4 h-4 text-slate-900" strokeWidth={2.5} />
              <span className="font-mono text-[10px] uppercase tracking-[0.3em] text-slate-500 font-semibold">
                Wizard · Tune Antenna
              </span>
            </div>
            <h1 className="font-heading text-3xl lg:text-4xl font-black tracking-tighter text-slate-900">
              Autotune assisté · sans oscilloscope
            </h1>
            <p className="text-sm text-slate-500 mt-2 max-w-xl">
              Cette page reçoit en direct la fréquence de résonance d&apos;antenne
              mesurée par le détecteur (via <span className="font-mono">readAntennaFreq()</span>)
              et propose la valeur de <span className="font-mono">tuneCap</span> à appliquer
              pour ramener la résonance vers 500 kHz.
            </p>
          </div>
          <div className="w-full lg:w-80 shrink-0">
            <NavTabs variant="inline" />
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 lg:px-8 py-8 lg:py-10 space-y-8">
        {/* Status banner */}
        <section
          className={`border p-5 flex items-center gap-4 ${
            online ? "border-emerald-200 bg-emerald-50" : "border-amber-200 bg-amber-50"
          }`}
          data-testid="tune-status-banner"
        >
          <Radio
            className={`w-6 h-6 shrink-0 ${
              online ? "text-emerald-700 animate-pulse" : "text-amber-700"
            }`}
            strokeWidth={2}
          />
          <div className="flex-1 min-w-0">
            <div
              className={`font-mono text-[10px] uppercase tracking-[0.25em] font-semibold ${
                online ? "text-emerald-800" : "text-amber-900"
              }`}
              data-testid="tune-status-label"
            >
              {online ? "Mesures reçues" : "En attente de mesures"}
            </div>
            <div className="font-heading text-lg font-bold text-slate-900 mt-0.5">
              {online && cur
                ? `Dernière trame · ${fmtLocalTime(cur.timestamp)}`
                : "Lance le sketch Autotune_To_Backend sur ton Arduino"}
            </div>
            <div className="text-[11px] font-mono text-slate-500 mt-0.5">
              Fenêtre de capture : {data?.window_minutes ?? 10} min · auto-refresh {REFRESH_MS / 1000} s
            </div>
          </div>
          {!online && (
            <div className="shrink-0 hidden md:flex items-center gap-2 text-[10px] font-mono uppercase tracking-[0.2em] text-amber-900">
              <RefreshCw className="w-3 h-3 animate-spin" /> Polling
            </div>
          )}
        </section>

        {error && (
          <div
            className="p-4 border border-red-200 bg-red-50 text-sm text-red-800 font-mono"
            data-testid="tune-error"
          >
            {error}
          </div>
        )}

        {/* Stats grid */}
        {cur && (
          <section className="grid grid-cols-2 lg:grid-cols-4 gap-0 -m-px" data-testid="tune-stats">
            <StatBlock
              tile={bigStat({
                label: "Fréquence mesurée",
                value: (cur.freq_hz / 1000).toFixed(2),
                unit: "kHz",
                testId: "tune-stat-freq",
              })}
            />
            <StatBlock
              tile={bigStat({
                label: "Écart vs 500 kHz",
                value: `${cur.delta_pct > 0 ? "+" : ""}${cur.delta_pct.toFixed(2)}`,
                unit: "%",
                accent: inSpec ? "" : "border-red-300",
                testId: "tune-stat-delta",
              })}
            />
            <StatBlock
              tile={bigStat({
                label: "Capacité actuelle",
                value: cur.tune_cap,
                unit: "/ 15",
                testId: "tune-stat-current-cap",
              })}
            />
            <StatBlock
              tile={bigStat({
                label: "Capacité suggérée",
                value: sug?.tune_cap ?? "—",
                unit: sug ? "/ 15" : "",
                accent: "bg-slate-900 text-white border-slate-900",
                testId: "tune-stat-suggested-cap",
              })}
            />
          </section>
        )}

        {/* Gauge */}
        {cur && (
          <section
            className="border border-slate-200 bg-white p-6 lg:p-8"
            data-testid="tune-gauge"
          >
            <div className="flex items-start justify-between mb-5">
              <div>
                <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-400 mb-1">
                  Résonance d&apos;antenne
                </div>
                <h2 className="font-heading text-lg font-bold text-slate-900">
                  Fréquence en direct vs cible 500 kHz
                </h2>
              </div>
              {inSpec ? (
                <span className="inline-flex items-center gap-1.5 px-3 h-7 font-mono text-[10px] uppercase tracking-[0.18em] border border-emerald-300 bg-emerald-50 text-emerald-800">
                  <CheckCircle2 className="w-3.5 h-3.5" /> Dans la spec ±3,5%
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 px-3 h-7 font-mono text-[10px] uppercase tracking-[0.18em] border border-red-300 bg-red-50 text-red-800">
                  Hors spec · ajuster tuneCap
                </span>
              )}
            </div>

            <div className="relative h-12 bg-slate-100 border border-slate-200">
              {/* Spec zone (±3.5% = 482.5-517.5 kHz, clamped to 490-510 display range) */}
              <div
                className="absolute top-0 bottom-0 bg-emerald-100"
                style={{ left: "0%", right: "0%" }}
              />
              {/* Out-of-spec zones */}
              <div
                className="absolute top-0 bottom-0 bg-red-50"
                style={{ left: "0%", width: "12.5%" }}
              />
              <div
                className="absolute top-0 bottom-0 bg-red-50"
                style={{ right: "0%", width: "12.5%" }}
              />
              {/* Target marker */}
              <div
                className="absolute top-0 bottom-0 w-px bg-slate-900"
                style={{ left: `${targetPct}%` }}
              />
              <div
                className="absolute top-[-22px] -translate-x-1/2 font-mono text-[9px] uppercase tracking-[0.15em] text-slate-600"
                style={{ left: `${targetPct}%` }}
              >
                500 kHz
              </div>
              {/* Current marker */}
              <div
                className="absolute top-[-4px] bottom-[-4px] w-1 bg-red-600 transition-all duration-500"
                style={{ left: `calc(${gaugePct}% - 2px)` }}
                data-testid="tune-gauge-needle"
              />
              <div
                className="absolute top-[52px] -translate-x-1/2 font-mono text-[10px] tabular-nums font-semibold text-red-700"
                style={{ left: `${gaugePct}%` }}
              >
                {(cur.freq_hz / 1000).toFixed(2)} kHz
              </div>
            </div>
            <div className="flex justify-between mt-10 font-mono text-[9px] uppercase tracking-[0.15em] text-slate-400">
              <span>490 kHz</span>
              <span>495</span>
              <span>500</span>
              <span>505</span>
              <span>510 kHz</span>
            </div>
          </section>
        )}

        {/* Calibration panel — shows whether we use defaults or learned slope */}
        {data?.calibration && (
          <section
            className={`border p-6 lg:p-8 ${
              data.calibration.adaptive
                ? "border-emerald-300 bg-emerald-50"
                : "border-slate-200 bg-white"
            }`}
            data-testid="tune-calibration-panel"
          >
            <div className="flex items-start gap-4 flex-col md:flex-row">
              <div className="flex items-center gap-2 shrink-0">
                <Sliders
                  className={`w-5 h-5 ${data.calibration.adaptive ? "text-emerald-700" : "text-slate-400"}`}
                  strokeWidth={2}
                />
                <span
                  className={`font-mono text-[10px] uppercase tracking-[0.25em] font-semibold ${
                    data.calibration.adaptive ? "text-emerald-800" : "text-slate-500"
                  }`}
                >
                  {data.calibration.adaptive ? "Auto-calibration active" : "Approximation par défaut"}
                </span>
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-baseline gap-2">
                  <span className="font-mono text-2xl font-medium text-slate-900 tabular-nums leading-none">
                    {data.calibration.hz_per_step.toFixed(0)}
                  </span>
                  <span className="font-mono text-sm text-slate-500">Hz / pas de capacité</span>
                </div>
                {data.calibration.adaptive ? (
                  <p className="text-[12px] text-slate-700 mt-2 leading-relaxed">
                    Sensibilité calibrée sur <strong>{(data.calibration.points || []).length}</strong>
                    {" "}valeur(s) de <code className="font-mono">tuneCap</code> mesurées, R² ={" "}
                    <span className="font-mono">{data.calibration.r_squared?.toFixed(4)}</span>.
                    Les suggestions ci-dessous utilisent cette sensibilité réelle au lieu de l&apos;approximation théorique (~1400 Hz/pas).
                  </p>
                ) : (
                  <p className="text-[12px] text-slate-600 mt-2 leading-relaxed">
                    Pour calibrer ton capteur précisément, fais 2 ou 3 reflashs successifs avec des
                    valeurs différentes de <code className="font-mono">lightning.tuneCap()</code>{" "}
                    (par ex. 0, 5, 10) — le wizard apprendra alors la sensibilité réelle{" "}
                    <strong>de ton module</strong> et améliorera ses suggestions.
                  </p>
                )}
                {data.calibration.points && data.calibration.points.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-2" data-testid="tune-calibration-points">
                    {data.calibration.points.map((p) => (
                      <span
                        key={p.tune_cap}
                        className="inline-flex items-center gap-2 px-2.5 h-6 font-mono text-[10px] border border-slate-300 bg-white text-slate-700"
                      >
                        cap={p.tune_cap} → {(p.median_freq_hz / 1000).toFixed(2)} kHz
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </section>
        )}

        {/* Action card */}
        {sug && cur && (
          <section
            className="border border-slate-900 bg-slate-900 text-white p-6 lg:p-8"
            data-testid="tune-action-card"
          >
            <div className="flex items-start justify-between gap-6 flex-col lg:flex-row">
              <div className="flex-1 min-w-0">
                <div className="font-mono text-[10px] uppercase tracking-[0.25em] text-slate-300 mb-2">
                  Recommandation
                </div>
                <h2 className="font-heading text-xl lg:text-2xl font-bold mb-3">
                  {sug.tune_cap === cur.tune_cap
                    ? "C'est déjà la meilleure valeur — rien à changer."
                    : `Reflashe ton sketch avec lightning.tuneCap(${sug.tune_cap})`}
                </h2>
                <p className="text-sm text-slate-300 leading-relaxed max-w-2xl">
                  {sug.note}{" "}
                  Après reflash, la fréquence attendue est{" "}
                  <span className="font-mono text-white">
                    {((TARGET_HZ + sug.expected_delta_hz_after) / 1000).toFixed(2)} kHz
                  </span>
                  {" "}(soit{" "}
                  <span className="font-mono text-white">
                    {sug.expected_delta_hz_after > 0 ? "+" : ""}
                    {(sug.expected_delta_hz_after / TARGET_HZ * 100).toFixed(2)} %
                  </span>
                  {" "}d&apos;écart).
                </p>
              </div>
              <button
                onClick={copySnippet}
                disabled={sug.tune_cap === cur.tune_cap}
                className="shrink-0 inline-flex items-center gap-2 px-5 h-11 bg-white text-slate-900 hover:bg-violet-300 transition-colors font-mono text-[10px] uppercase tracking-[0.2em] disabled:opacity-40 disabled:hover:bg-white"
                data-testid="tune-copy-snippet"
              >
                <Copy className="w-4 h-4" strokeWidth={2} />
                Copier le snippet
              </button>
            </div>
          </section>
        )}

        {/* Recent samples */}
        {data?.samples && data.samples.length > 0 && (
          <section className="border border-slate-200 bg-white" data-testid="tune-samples-table">
            <div className="px-6 py-4 border-b border-slate-100">
              <h2 className="font-heading text-sm font-bold text-slate-900">
                Mesures récentes
              </h2>
            </div>
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50 text-[10px] font-mono uppercase tracking-wider text-slate-400">
                  <th className="text-left px-6 py-2.5 font-medium">Heure</th>
                  <th className="text-right px-6 py-2.5 font-medium">Fréquence</th>
                  <th className="text-right px-6 py-2.5 font-medium">Écart</th>
                  <th className="text-right px-6 py-2.5 font-medium">tuneCap</th>
                </tr>
              </thead>
              <tbody>
                {data.samples.slice(0, 15).map((s, i) => {
                  const deltaPct = ((s.freq_hz - TARGET_HZ) / TARGET_HZ) * 100;
                  return (
                    <tr key={i} className="border-t border-slate-100 hover:bg-slate-50">
                      <td className="px-6 py-3 font-mono text-slate-900 tabular-nums text-[12px]">
                        {fmtLocalTime(s.timestamp)}
                      </td>
                      <td className="px-6 py-3 font-mono text-right tabular-nums text-slate-900">
                        {(s.freq_hz / 1000).toFixed(2)} kHz
                      </td>
                      <td
                        className={`px-6 py-3 font-mono text-right tabular-nums ${
                          Math.abs(deltaPct) <= 3.5 ? "text-emerald-700" : "text-red-700"
                        }`}
                      >
                        {deltaPct > 0 ? "+" : ""}
                        {deltaPct.toFixed(2)} %
                      </td>
                      <td className="px-6 py-3 font-mono text-right tabular-nums text-slate-900">
                        {s.tune_cap}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </section>
        )}

        {/* Help when no data */}
        {!online && !loading && (
          <section className="border border-slate-200 bg-white p-8" data-testid="tune-help">
            <h2 className="font-heading text-xl font-bold text-slate-900 mb-3">
              Comment ça marche ?
            </h2>
            <ol className="space-y-2 text-sm text-slate-700 list-decimal list-inside">
              <li>
                Flashe le sketch{" "}
                <code className="font-mono text-slate-900">
                  hardware/Tune_Antenna/Autotune_To_Backend_I2C.ino
                </code>{" "}
                (ou la version SPI) sur ton Arduino.
              </li>
              <li>
                Le sketch lit la fréquence d&apos;antenne via{" "}
                <code className="font-mono text-slate-900">readAntennaFreq()</code>{" "}
                toutes les 2 secondes et la pousse au backend.
              </li>
              <li>
                Cette page affiche en direct la fréquence, l&apos;écart vs 500 kHz et
                la valeur de <code className="font-mono">tuneCap</code> à appliquer.
              </li>
              <li>
                Une fois la valeur optimale trouvée, reporte-la dans ton sketch
                principal (<code className="font-mono">Arduino_StormDetector.ino</code>)
                avec <code className="font-mono">lightning.tuneCap(N);</code>
              </li>
            </ol>
          </section>
        )}

        <footer className="pt-8 border-t border-slate-100 font-mono text-[10px] uppercase tracking-[0.2em] text-slate-400">
          Wizard · /detector/tune · readAntennaFreq() · AS3935
        </footer>
      </main>
    </div>
  );
}
