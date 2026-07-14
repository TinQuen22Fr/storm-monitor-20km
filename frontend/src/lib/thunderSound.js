let ctx = null;
let thunderBuffer = null;
let bufferLoading = null;
let isPlaying = false;

const THUNDER_WAV_URL = `${process.env.PUBLIC_URL || ""}/sounds/thunder-strike.wav`;

function getCtx() {
  if (!ctx) {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    ctx = new AC();
  }
  return ctx;
}

function loadThunderBuffer() {
  if (thunderBuffer) return Promise.resolve(thunderBuffer);
  if (bufferLoading) return bufferLoading;
  const c = getCtx();
  if (!c) return Promise.resolve(null);
  bufferLoading = fetch(THUNDER_WAV_URL)
    .then((r) => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.arrayBuffer();
    })
    .then((ab) => c.decodeAudioData(ab))
    .then((buf) => {
      thunderBuffer = buf;
      return buf;
    })
    .catch(() => {
      bufferLoading = null;
      return null;
    });
  return bufferLoading;
}

export async function unlockAudio() {
  const c = getCtx();
  if (c && c.state === "suspended") {
    try { await c.resume(); } catch { /* ignore */ }
  }
  loadThunderBuffer();
  return c;
}

/** Joue le son de tonnerre (fichier .wav ~15 s).
 * Anti-superposition : si la piste est déjà en cours de lecture,
 * un nouvel impact ne relance PAS une deuxième piste par-dessus. */
export function playThunder() {
  const c = getCtx();
  if (!c || c.state !== "running") return false;
  if (isPlaying) return false;

  if (thunderBuffer) {
    isPlaying = true;
    const src = c.createBufferSource();
    src.buffer = thunderBuffer;
    const g = c.createGain();
    g.gain.value = 0.9;
    src.connect(g).connect(c.destination);
    const clear = () => { isPlaying = false; };
    src.onended = clear;
    // Filet de sécurité si onended ne remonte pas (webview)
    setTimeout(clear, (thunderBuffer.duration + 1) * 1000);
    src.start();
    return true;
  }

  // Fichier pas encore décodé : on lance le chargement et on joue le
  // tonnerre synthétisé en attendant (même règle anti-superposition).
  loadThunderBuffer();
  return playSynthThunder(c);
}

function playSynthThunder(c) {
  const now = c.currentTime;
  const dur = 1.6;
  isPlaying = true;
  setTimeout(() => { isPlaying = false; }, (dur + 0.2) * 1000);

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
