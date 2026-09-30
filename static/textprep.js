/* Text preparation for listening: cleaning, math wording and sentence splitting.
   Shared by the browser (window.TextPrep) and the Node tests (require). */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.TextPrep = factory();
}(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const LIGATURES = { 'ﬁ': 'fi', 'ﬂ': 'fl', 'ﬀ': 'ff', 'ﬃ': 'ffi', 'ﬄ': 'ffl', 'ﬅ': 'st', 'ﬆ': 'st' };
  const NAME = "[A-ZÀ-Ý][A-Za-zÀ-ÿ'’\\-]+";
  const YEAR = '(?:1[89]|20)\\d{2}[a-z]?';
  // "Smith, 2019", "Smith and Jones 2019", "Smith et al., 2019a, 2020", "Smith & Jones, 2019"
  const CITE = new RegExp('^(?:(?:e\\.g\\.|i\\.e\\.|see(?: also)?|cf\\.|but see|reviewed in)[,\\s]+)?' +
    '(?:(?:van |von |de |du |le |la |di )?' + NAME + '(?:\\s+(?:et\\s+al\\.?|(?:and|&)\\s+(?:van |von |de )?' + NAME + '))?' +
    '|[A-Z]{2,}),?\\s+(?:' + YEAR + '|in press|submitted)(?:\\s*,\\s*' + YEAR + ')*' +
    '(?:,\\s*(?:p|pp)\\.\\s*\\d+(?:[–-]\\d+)?)?$');

  const ABBREVIATIONS = ['e.g', 'i.e', 'et al', 'etc', 'vs', 'cf', 'fig', 'figs', 'eq', 'eqs', 'ref', 'refs',
    'approx', 'ca', 'resp', 'dr', 'mr', 'mrs', 'ms', 'prof', 'st', 'no', 'vol', 'pp', 'p', 'ed', 'eds',
    'sect', 'sec', 'tab', 'suppl', 'min', 'max', 'avg', 'std', 'var', 'inc', 'ltd', 'co', 'jr', 'sr', 'dept',
    'univ', 'n.b', 'a.k.a', 'u.s', 'sp', 'spp', 'var', 'al'];

  /** Remove author-year citations inside parentheses, keep any other content. */
  function dropAuthorYear(text) {
    return text.replace(/\s*\(([^()]*)\)/g, (whole, inside) => {
      if (!/(?:1[89]|20)\d{2}|in press/.test(inside)) return whole;
      const parts = inside.split(/\s*;\s*/);
      const kept = parts.filter(p => !CITE.test(p.trim()));
      if (kept.length === parts.length) return whole;
      if (!kept.length) return '';
      return ' (' + kept.join('; ') + ')';
    })
      // Narrative citation: "Smith et al. (2019) showed" -> "Smith et al. showed"
      .replace(new RegExp('(' + NAME + '(?:\\s+et\\s+al\\.?|\\s+(?:and|&)\\s+' + NAME + ')?)\\s*\\((' + YEAR + '(?:\\s*[,;]\\s*' + YEAR + ')*)\\)', 'g'), '$1');
  }

  function clean(text, opts = {}) {
    let t = String(text || '');
    t = t.replace(/[ﬁﬂﬀﬃﬄﬅﬆ]/g, c => LIGATURES[c]).replace(/­/g, '');
    t = t.replace(/([A-Za-zÀ-ÿ])-\s*\n\s*([a-zà-ÿ])/g, '$1$2').replace(/\s+/g, ' ').trim();
    if (opts.citations !== false) {
      // Numeric callouts: [3], [3, 5], [3–7], [3,5–7]
      t = t.replace(/\s*\[\s*\d+(?:\s*[,;–-]\s*\d+)*\s*\]/g, '');
      t = dropAuthorYear(t);
    }
    t = t.replace(/https?:\/\/\S+/g, '').replace(/\b(?:doi:\s*)?10\.\d{4,9}\/\S+/gi, '');
    t = words(t);
    return t.replace(/\s+([,.;:!?)])/g, '$1').replace(/\(\s+/g, '(').replace(/\(\s*\)/g, '')
      .replace(/([,;])\s*([,;.])/g, '$2').replace(/\s{2,}/g, ' ').trim();
  }

  /** Say simple symbols as words so the voice does not stop or spell them. */
  function words(t) {
    return t
      .replace(/\b([A-Za-z])\s*=\s*([A-Za-z0-9]+)\s*\/\s*([A-Za-z0-9]+)\b/g, '$1 equals $2 divided by $3')
      .replace(/(\S)\s*=\s*/g, '$1 equals ')
      .replace(/\s*±\s*/g, ' plus or minus ')
      .replace(/\s*≈\s*/g, ' approximately ')
      .replace(/\s*≤\s*/g, ' less than or equal to ')
      .replace(/\s*≥\s*/g, ' greater than or equal to ')
      .replace(/(\d)\s*[×x]\s*10\s*[\^]?([−-]?\d+)/g, (m, a, e) => a + ' times ten to the ' + e.replace('−', 'minus ').replace('-', 'minus '))
      .replace(/\s+<\s+/g, ' less than ').replace(/\s+>\s+/g, ' greater than ')
      .replace(/−(?=\d)/g, 'minus ')
      .replace(/(\d)\s*°C\b/g, '$1 degrees Celsius')
      .replace(/(\d)\s*%/g, '$1 percent')
      .replace(/²/g, ' squared').replace(/³/g, ' cubed')
      .replace(/⁻¹/g, ' to the minus one').replace(/\bp\s*<\s*/g, 'p less than ');
  }

  function isAbbreviation(before) {
    const m = before.match(/(?:^|[\s(])((?:[A-Za-z]\.)*[A-Za-z]+)$/);
    if (!m) return false;
    const word = m[1].toLowerCase();
    if (ABBREVIATIONS.includes(word)) return true;
    if (/^[A-Z]$/.test(m[1])) return true;          // initials: J. R. Smith
    return /^(?:[a-z]\.)+[a-z]$/i.test(m[1]);         // e.g, i.e, U.S
  }

  /** Split into sentences, protecting abbreviations, decimals and initials. */
  function sentences(text) {
    const t = String(text || '').replace(/\s+/g, ' ').trim();
    if (!t) return [];
    const out = [];
    let start = 0;
    const re = /([.!?]["”’)\]]*)\s+(?=["“‘(\[]?[A-Z0-9À-Ý])/g;
    let m;
    while ((m = re.exec(t))) {
      const end = m.index + m[1].length;
      const before = t.slice(start, m.index);
      if (m[1][0] === '.' && (isAbbreviation(before) || /^[\dIVX]+(?:\.\d+)*$/.test(before.trim()))) continue;
      out.push(t.slice(start, end).trim());
      start = re.lastIndex;
    }
    if (start < t.length) out.push(t.slice(start).trim());
    return out.filter(Boolean);
  }

  /** Cut a sentence that is too long for one utterance at a natural pause. */
  function limit(sentence, max) {
    const out = [];
    let rest = sentence;
    while (rest.length > max) {
      let cut = -1;
      for (const mark of ['; ', ': ', ', ', ' – ', ' — ', ' (']) {
        const at = rest.lastIndexOf(mark, max);
        if (at > cut) cut = at + (mark === ' (' ? 0 : mark.length - 1);
      }
      if (cut < max * .4) cut = rest.lastIndexOf(' ', max);
      if (cut < 1) cut = max;
      out.push(rest.slice(0, cut + 1).trim());
      rest = rest.slice(cut + 1).trim();
    }
    if (rest) out.push(rest);
    return out;
  }

  /** Speakable units: sentences, long ones split. Joined, they equal the text. */
  function chunks(text, max = 220) {
    return sentences(text).flatMap(s => limit(s, max));
  }

  const SYMBOLS = { '=': ' equals ', '×': ' times ', '÷': ' divided by ', '+': ' plus ', '−': ' minus ',
    'α': ' alpha ', 'β': ' beta ', 'γ': ' gamma ', 'δ': ' delta ', 'λ': ' lambda ', 'μ': ' mu ',
    'σ': ' sigma ', 'θ': ' theta ', '∑': ' sum ', '√': ' square root of ', '≤': ' less than or equal to ',
    '≥': ' greater than or equal to ', '/': ' divided by ', '^': ' to the power ' };

  /**
   * Text to speak for one extracted item, or '' to skip it.
   * opts: {citations, bibliography, notes: skip|read, figures: read|skip, tables: announce|read|skip,
   *        equations: announce|read|skip}
   * previous: the item spoken just before, to avoid repeating an announcement.
   */
  function prepare(item, opts = {}, previous = null) {
    const kind = item.kind;
    if (kind === 'reference' && opts.bibliography !== false) return '';
    if (kind === 'note' && opts.notes !== 'read') return '';
    if (kind === 'figure' && opts.figures === 'skip') return '';
    if (kind === 'table' || kind === 'tablecell') {
      const mode = opts.tables || 'announce';
      if (mode === 'skip') return '';
      if (mode === 'announce') {
        if (kind === 'tablecell') return '';
        return 'A table is presented here. See page ' + item.page + '.';
      }
      return clean(item.text || item.original, opts);
    }
    if (kind === 'equation') {
      const mode = opts.equations || 'announce';
      if (mode === 'skip') return '';
      if (mode === 'announce') {
        return previous && previous.kind === 'equation' ? '' : 'An equation is presented here. See page ' + item.page + '.';
      }
      return clean(String(item.text || item.original).replace(/[=×÷+−αβγδλμσθ∑√≤≥/^]/g, c => SYMBOLS[c]), opts);
    }
    return clean(item.text || item.original, opts);
  }

  function tokens(text) {
    const out = [], re = /[A-Za-zÀ-ÿ0-9]+/g;
    let m;
    while ((m = re.exec(text))) out.push({ w: m[0].toLowerCase(), s: m.index, e: m.index + m[0].length });
    return out;
  }

  /**
   * Where each spoken sentence comes from in the original extracted text, as
   * [start, end] character offsets (or null). Cleaning removed citations and
   * turned symbols into words, so sentences are matched by their first and
   * last words, searching forward from the previous sentence.
   */
  function locate(sents, original) {
    const src = tokens(original || '');
    const out = [];
    let cursor = 0;
    const matchAt = (seq, i) => seq.every((w, k) => src[i + k] && src[i + k].w === w);
    for (const sentence of sents) {
      const words = tokens(sentence).map(t => t.w);
      if (!words.length || cursor >= src.length) { out.push(null); continue; }
      const reach = Math.min(src.length, cursor + words.length * 2 + 25);
      let start = -1;
      for (let skip = 0; skip < Math.min(4, words.length) && start < 0; skip++) {
        for (let n = Math.min(3, words.length - skip); n >= 1 && start < 0; n--) {
          if (n === 1 && words[skip].length < 4) continue;
          for (let i = cursor; i < reach && start < 0; i++) if (matchAt(words.slice(skip, skip + n), i)) start = Math.max(cursor, i - skip);
        }
      }
      if (start < 0) start = cursor;
      let end = -1;
      const guess = start + words.length - 1;
      for (let n = Math.min(3, words.length); n >= 1 && end < 0; n--) {
        const tail = words.slice(words.length - n);
        let best = -1;
        for (let i = start; i < Math.min(src.length, start + words.length * 2 + 25); i++) {
          if (matchAt(tail, i) && (best < 0 || Math.abs(i + n - 1 - guess) < Math.abs(best - guess))) best = i + n - 1;
        }
        end = best;
      }
      if (end < start) end = Math.min(src.length - 1, guess);
      out.push([src[start].s, src[end].e]);
      cursor = end + 1;
    }
    return out;
  }

  return { clean, sentences, chunks, prepare, dropAuthorYear, locate };
}));
