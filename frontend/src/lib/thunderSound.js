let ctx = null;

function getCtx() {
  if (!ctx) {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    ctx = new AC();
  }
  return ctx;
}

export async function unlockAudio() {
  const c = getCtx();
  if (c && c.state === "suspended") {
    try { await c.resume(); } catch { /* ignore */ }
  }
  return c;
}

export function playThunder() {
  const c = getCtx();
  if (!c || c.state !== "running") return false;
  const now = c.currentTime;

  // Craquement initial (claquement de foudre)
  const crackDur = 0.09;
  const crackBuf = c.createBuffer(1, Math.floor(c.sampleRate * crackDur), c.sampleRate);
  const cd = crackBuf.getChannelData(0);
  for (let i = 0; i < cd.length; i++) cd[i] = (Math.random() * 2 - 1) * (1 - i / cd.length) ** 2;
  const crack = c.createBufferSource();
  crack.buffer = crackBuf;
  const crackHp = c.createBiquadFilter();
  crackHp.type = "highpass";
  crackHp.frequency.value = 1500;
  const crackGain = c.createGain();
  crackGain.gain.setValueAtTime(0.45, now);
  crack.connect(crackHp).connect(crackGain).connect(c.destination);
  crack.start(now);

  // Grondement de tonnerre (bruit filtré, décroissance ~1.6s)
  const dur = 1.6;
  const buf = c.createBuffer(1, Math.floor(c.sampleRate * dur), c.sampleRate);
  const d = buf.getChannelData(0);
  for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
  const src = c.createBufferSource();
  src.buffer = buf;
  const lp = c.createBiquadFilter();
  lp.type = "lowpass";
  lp.frequency.setValueAtTime(480, now);
  lp.frequency.exponentialRampToValueAtTime(80, now + dur);
  const g = c.createGain();
  g.gain.setValueAtTime(0.0001, now);
  g.gain.exponentialRampToValueAtTime(0.5, now + 0.06);
  g.gain.exponentialRampToValueAtTime(0.0001, now + dur);
  src.connect(lp).connect(g).connect(c.destination);
  src.start(now + 0.04);
  return true;
}
