'use strict';
/* Reader interface: PDF upload, passage list, speech with sentence tracking. */

const $ = id => document.getElementById(id);
const T = window.TextPrep;
const token = document.querySelector('meta[name=reader-token]').content;
const synth = window.speechSynthesis;

let raw = [], passages = [];
let pos = { p: 0, s: 0 };          // passage index, sentence index
let page = 1, pages = 0, sizes = [], voices = [], editing = false;
let running = false, paused = false, generation = 0, current = null, watchdog = null;
let startSeen = false;              // this browser reports onstart, so a missing one means silence

const store = {
  get(k) { try { return localStorage.getItem('reader.' + k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem('reader.' + k, v); } catch { /* private mode */ } },
};

function status(t) { $('status').textContent = t; }

function options() {
  return {
    citations: $('citations').checked, bibliography: $('bibliography').checked,
    notes: $('notes').value, figures: $('figures').value, tables: $('tables').value, equations: $('equations').value,
  };
}

/* ---------- Building passages ---------- */

function withSentences(b) {
  b.sentences = T.chunks(b.text, 400);
  b.ranges = T.locate(b.sentences, b.original);
  return b;
}

function rebuild() {
  halt();
  const opts = options(), section = $('section').value;
  let previous = null;
  passages = [];
  for (const b of raw) {
    if (section && b.section !== section) continue;
    const text = T.prepare(b, opts, previous);
    if (!text) continue;
    previous = b;
    passages.push(withSentences({ ...b, text }));
  }
  render();
  status(passages.length + ' passages préparés. Vérifie le texte avant l’écoute.');
}

function render() {
  const box = $('reading');
  box.replaceChildren();
  passages.forEach((b, i) => box.append(passageElement(b, i)));
  select(0, 0);
}

function passageElement(b, i) {
  const e = document.createElement('div');
  e.id = 'b' + i;
  e.className = 'passage ' + b.kind;
  const meta = document.createElement('span');
  meta.className = 'meta';
  meta.textContent = `Page ${(b.pages || [b.page]).join('–')} · ${b.section}${b.subsection ? ' · ' + b.subsection : ''}`;
  const spoken = document.createElement('div');
  spoken.className = 'spoken';
  b.sentences.forEach((s, j) => {
    const span = document.createElement('span');
    span.className = 's';
    span.id = `s${i}-${j}`;
    span.textContent = s;
    span.onclick = ev => {
      if (editing) return;
      ev.stopPropagation();
      const wasRunning = running && !paused;
      halt();
      select(i, j);
      if (wasRunning) play();
    };
    spoken.append(span, ' ');
  });
  e.append(meta, spoken);
  e.onclick = () => { if (editing && i === pos.p) return; halt(); select(i, 0); };
  return e;
}

/* ---------- Selection and page view ---------- */

function select(p, s) {
  if (!passages.length) { controls(); return; }
  p = Math.max(0, Math.min(passages.length - 1, p));
  s = Math.max(0, Math.min(passages[p].sentences.length - 1, s));
  const moved = p !== pos.p;
  pos = { p, s };
  document.querySelectorAll('.passage.active').forEach(e => e.classList.remove('active'));
  document.querySelectorAll('.s.now').forEach(e => e.classList.remove('now'));
  const e = $('b' + p);
  if (e) e.classList.add('active');
  const span = $(`s${p}-${s}`);
  if (span) {
    span.classList.add('now');
    span.scrollIntoView({ block: 'nearest', behavior: moved ? 'smooth' : 'auto' });
  }
  const marks = sentenceBoxes(passages[p], s);
  showPage(marks.length ? marks[0].page : passages[p].page, marks);
  controls();
}

/** Rectangles, in PDF points, covering sentence s of passage b. */
function sentenceBoxes(b, s) {
  const range = b.ranges && b.ranges[s];
  if (!range || !b.spans) return [];
  const [a, z] = range, out = [];
  for (const [start, end, pg, x0, y0, x1, y1] of b.spans) {
    if (end <= a || start >= z) continue;
    const from = Math.max(0, (a - start) / (end - start)), to = Math.min(1, (z - start) / (end - start));
    out.push({ page: pg, x0: x0 + (x1 - x0) * from, x1: x0 + (x1 - x0) * to, y0, y1 });
  }
  return out;
}

let shownMarks = [];
function drawMarks() {
  const layer = $('marks'), size = sizes[page - 1];
  layer.replaceChildren();
  if (!size) return;
  const [w, h] = size;
  for (const m of shownMarks.filter(m => m.page === page)) {
    const d = document.createElement('div');
    d.className = 'mark';
    Object.assign(d.style, { left: (m.x0 / w * 100) + '%', top: (m.y0 / h * 100) + '%',
      width: ((m.x1 - m.x0) / w * 100) + '%', height: ((m.y1 - m.y0) / h * 100) + '%' });
    layer.append(d);
  }
  const first = layer.firstElementChild, viewer = layer.closest('.viewer');
  if (first && $('pdfpage').complete) {
    const top = first.offsetTop + $('pagebox').offsetTop;
    if (top < viewer.scrollTop + 20 || top > viewer.scrollTop + viewer.clientHeight - 60) {
      viewer.scrollTo({ top: Math.max(0, top - viewer.clientHeight / 3), behavior: 'smooth' });
    }
  }
}

function showPage(n, marks) {
  if (!pages) return;
  page = Math.max(1, Math.min(pages, n));
  if (marks) shownMarks = marks;
  $('empty').style.display = 'none';
  $('pagebox').style.display = 'block';
  const src = '/page?n=' + page + '&token=' + encodeURIComponent(token);
  if (!$('pdfpage').src.endsWith(src)) $('pdfpage').src = src;
  $('pagenum').textContent = `${page} / ${pages}`;
  drawMarks();
}

function controls() {
  const ok = passages.length > 0;
  for (const id of ['play', 'stop', 'previous', 'next', 'back', 'forward', 'edit', 'export']) $(id).disabled = !ok;
  $('play').disabled = !ok || !synth;
  $('play').textContent = running && !paused ? '❚❚ Pause' : paused ? '▶ Reprendre' : '▶ Lire';
  $('progress').textContent = ok ? `${pos.p + 1} / ${passages.length} passages` : 'Aucun passage';
}

/* ---------- Speech ----------
   Each sentence is one utterance, cut shorter at slow speeds so Chrome's
   online voices never reach their ~15 s cutoff. Browsers sometimes end an
   utterance without speaking it (right after cancel(), or when a remote voice
   drops); we detect that from the elapsed time and speak it again instead of
   silently moving on. A watchdog advances if the browser never fires onend.
   Pause is implemented as stop-and-restart of the current sentence, which is
   reliable across Chrome and Edge. */

function rate() { return Number($('rate').value); }
function maxChars() { return Math.round(Math.min(260, Math.max(110, 170 * rate()))); }

function halt() {
  generation++;
  running = false;
  paused = false;
  current = null;
  clearInterval(watchdog);
  if (synth && (synth.speaking || synth.pending)) synth.cancel();
  stopEditing(false);
  controls();
}

function play() {
  if (!passages.length || !synth) return;
  generation++;
  const mine = generation;
  if (synth.speaking || synth.pending) synth.cancel();
  running = true;
  paused = false;
  controls();
  status('Lecture en cours…');
  clearInterval(watchdog);
  watchdog = setInterval(() => checkStalled(mine), 700);
  // Chrome may drop an utterance queued in the same tick as cancel().
  setTimeout(() => speakSentence(mine, 0), 150);
}

function pause() {
  if (!running) return;
  generation++;
  paused = true;
  current = null;
  clearInterval(watchdog);
  if (synth.speaking || synth.pending) synth.cancel();
  controls();
  status('Lecture en pause. Reprendre relit la phrase en cours depuis son début.');
}

function speakSentence(mine, part) {
  if (mine !== generation) return;
  const sentence = passages[pos.p] && passages[pos.p].sentences[pos.s];
  if (sentence === undefined) { finished(); return; }
  const parts = T.chunks(sentence, maxChars());
  if (part >= parts.length) { advance(mine); return; }
  say(mine, parts[part], 0, () => speakSentence(mine, part + 1));
}

function say(mine, text, attempt, done) {
  const u = new SpeechSynthesisUtterance(text);
  const voice = voices.find(v => v.voiceURI === $('voice').value);
  if (voice) { u.voice = voice; u.lang = voice.lang; } else u.lang = 'en-US';
  u.rate = rate();
  const state = { u, text, started: 0, reached: 0, ended: false, attempt, done, queuedAt: Date.now() };
  current = state;
  u.onstart = () => { state.started = Date.now(); startSeen = true; };
  u.onboundary = ev => { state.reached = Math.max(state.reached, ev.charIndex || 0); };
  u.onend = () => ended(mine, state);
  u.onerror = ev => {
    if (mine !== generation || state.ended) return;
    if (ev.error === 'interrupted' || ev.error === 'canceled') { ended(mine, state); return; }
    state.ended = true;
    halt();
    status('Lecture interrompue (' + ev.error + '). Essaie une autre voix, puis Lire.');
  };
  synth.speak(u);
}

function ended(mine, state, neverStarted = false) {
  if (mine !== generation || state.ended) return;
  state.ended = true;
  const elapsed = Date.now() - (state.started || state.queuedAt);
  const expected = state.text.length / (15 * rate()) * 1000;   // ~15 characters per second at 1×
  const skipped = neverStarted || (startSeen && !state.started) ||
    (state.text.length > 25 && elapsed < expected * .25 && state.reached < state.text.length * .5);
  if (skipped && state.attempt < 2) {
    // The browser ended without really speaking: say it again.
    const rest = state.reached > 0 ? state.text.slice(state.text.lastIndexOf(' ', state.reached) + 1) : state.text;
    setTimeout(() => { if (mine === generation) say(mine, rest, state.attempt + 1, state.done); }, 200);
    return;
  }
  setTimeout(() => { if (mine === generation) state.done(); }, 60);
}

function checkStalled(mine) {
  if (mine !== generation || !current || current.ended) return;
  const since = Date.now() - (current.started || current.queuedAt);
  const expected = current.text.length / (15 * rate()) * 1000;
  // Nothing is speaking any more but onend never came.
  if (since > Math.max(4000, expected + 2000) && !synth.speaking && !synth.pending) ended(mine, current, !current.started);
  // Stuck far beyond any plausible duration.
  else if (since > expected * 4 + 8000) { synth.cancel(); ended(mine, current); }
}

function advance(mine) {
  if (mine !== generation) return;
  const b = passages[pos.p];
  if (pos.s + 1 < b.sentences.length) select(pos.p, pos.s + 1);
  else if (pos.p + 1 < passages.length) select(pos.p + 1, 0);
  else { finished(); return; }
  speakSentence(mine, 0);
}

function finished() {
  halt();
  status('Lecture terminée.');
}

function move(dp, ds) {
  const wasRunning = running && !paused;
  halt();
  if (dp) select(pos.p + dp, 0);
  else {
    const b = passages[pos.p];
    if (pos.s + ds >= b.sentences.length && pos.p + 1 < passages.length) select(pos.p + 1, 0);
    else if (pos.s + ds < 0 && pos.p > 0) select(pos.p - 1, passages[pos.p - 1].sentences.length - 1);
    else select(pos.p, pos.s + ds);
  }
  if (wasRunning) play();
}

/* ---------- Voices ---------- */

function refreshVoices() {
  if (!synth) { status('Synthèse vocale indisponible. Utiliser Microsoft Edge ou Chrome.'); return; }
  const wanted = $('voice').value || store.get('voice');
  voices = synth.getVoices().filter(v => v.lang.toLowerCase().startsWith('en'));
  voices.sort((a, b) => (b.localService - a.localService) || a.name.localeCompare(b.name));
  $('voice').replaceChildren();
  for (const v of voices) {
    const o = document.createElement('option');
    o.value = v.voiceURI;
    o.textContent = v.name + ' · ' + v.lang + (v.localService ? ' · locale' : ' · en ligne');
    $('voice').append(o);
  }
  if (voices.some(v => v.voiceURI === wanted)) $('voice').value = wanted;
  if (!voices.length) $('voice').append(new Option('Voix par défaut du navigateur', ''));
}

/* ---------- Editing ---------- */

function stopEditing(save) {
  if (!editing) return;
  const i = pos.p, e = $('b' + i), spoken = e && e.querySelector('.spoken');
  editing = false;
  $('edit').textContent = 'Corriger le passage';
  if (!spoken) return;
  spoken.contentEditable = 'false';
  if (save) {
    const text = spoken.textContent.replace(/\s+/g, ' ').trim();
    passages[i].text = text;
    withSentences(passages[i]);
    status('Correction enregistrée pour cette session.');
  }
  e.replaceWith(passageElement(passages[i], i));
  select(i, 0);
}

/* ---------- Upload ---------- */

async function load(file) {
  if (!file) return;
  halt();
  status('Analyse du PDF…');
  $('file').disabled = true;
  $('rebuild').disabled = true;
  try {
    const res = await fetch('/upload', { method: 'POST', headers: { 'X-Reader-Token': token }, body: file });
    const data = await res.json();
    if (!res.ok) throw Error(data.error);
    raw = data.items;
    pages = data.pages;
    sizes = data.sizes || [];
    $('notice').textContent = data.warnings.join(' ');
    $('section').replaceChildren(new Option('Toutes les sections', ''));
    [...new Set(raw.filter(b => b.kind !== 'reference').map(b => b.section))].forEach(s => $('section').append(new Option(s, s)));
    rebuild();
    status(file.name + ' · ' + pages + ' pages · ' + passages.length + ' passages');
    showPage(1);
  } catch (e) {
    status('Erreur : ' + e.message);
  } finally {
    $('file').disabled = false;
    $('rebuild').disabled = !raw.length;
  }
}

/* ---------- Wiring ---------- */

$('file').onchange = e => load(e.target.files[0]);
$('drop').onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); $('file').click(); } };
document.ondragover = e => e.preventDefault();
document.ondrop = e => { e.preventDefault(); load(e.dataTransfer.files[0]); };

$('play').onclick = () => { if (running && !paused) pause(); else play(); };
$('stop').onclick = () => { halt(); status('Lecture arrêtée. Lire reprend à la phrase surlignée.'); };
$('previous').onclick = () => move(-1, 0);
$('next').onclick = () => move(1, 0);
$('back').onclick = () => move(0, -1);
$('forward').onclick = () => move(0, 1);
$('pdfpage').onload = drawMarks;
$('pageprev').onclick = () => showPage(page - 1);
$('pagenext').onclick = () => showPage(page + 1);
$('section').onchange = rebuild;
$('rebuild').onclick = () => { if (confirm('Repréparer le texte et effacer les corrections manuelles ?')) rebuild(); };
for (const id of ['equations', 'figures', 'tables', 'notes', 'citations', 'bibliography']) {
  $(id).onchange = () => { store.set(id, $(id).type === 'checkbox' ? $(id).checked : $(id).value); if (raw.length) rebuild(); };
  const saved = store.get(id);
  if (saved !== null) { if ($(id).type === 'checkbox') $(id).checked = saved === 'true'; else $(id).value = saved; }
}
$('voice').onchange = () => store.set('voice', $('voice').value);
$('rate').value = store.get('rate') || '1';
$('rate').oninput = () => {
  $('ratevalue').textContent = Number($('rate').value).toFixed(1).replace('.', ',') + '×';
  store.set('rate', $('rate').value);
};
$('rate').oninput();
$('edit').onclick = () => {
  if (editing) { stopEditing(true); return; }
  halt();
  const spoken = $('b' + pos.p).querySelector('.spoken');
  editing = true;
  spoken.contentEditable = 'true';
  spoken.focus();
  $('edit').textContent = 'Enregistrer la correction';
  status('Modifie le passage puis enregistre la correction.');
};
$('export').onclick = () => {
  const url = URL.createObjectURL(new Blob([passages.map(b => b.text).join('\n\n')], { type: 'text/plain;charset=utf-8' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = 'Article_pour_ecoute.txt';
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
document.addEventListener('keydown', e => {
  if (editing || !passages.length || e.ctrlKey || e.metaKey || e.altKey) return;
  if (e.target.closest && e.target.closest('input,select,textarea,[contenteditable=true]')) return;
  if (e.key === ' ' && e.target.closest && e.target.closest('button,label')) return;   // native click
  if (e.key === ' ') { e.preventDefault(); $('play').click(); }
  else if (e.key === 'ArrowRight') { e.preventDefault(); move(e.shiftKey ? 1 : 0, e.shiftKey ? 0 : 1); }
  else if (e.key === 'ArrowLeft') { e.preventDefault(); move(e.shiftKey ? -1 : 0, e.shiftKey ? 0 : -1); }
});

if (synth) { synth.onvoiceschanged = refreshVoices; refreshVoices(); }
else status('Synthèse vocale indisponible dans ce navigateur.');
window.addEventListener('beforeunload', halt);
controls();
