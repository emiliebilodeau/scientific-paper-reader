const test = require('node:test');
const assert = require('node:assert');
const T = require('../static/textprep.js');

const squash = s => s.replace(/\s+/g, ' ').trim();

test('chunks never lose or reorder text', () => {
  const samples = [
    'Regional methods transfer information, e.g. by regression. The approach is used. Is it? Yes.',
    'J. R. Smith measured 3.5 m at St. Lawrence in Fig. 2. Values (i.e. peaks) rose by 4.2 %.',
    'word, '.repeat(120) + 'end.',
    'A sentence without a final period',
  ];
  for (const s of samples) {
    for (const max of [80, 110, 220, 400]) assert.strictEqual(T.chunks(s, max).join(' '), squash(s));
  }
});

test('sentences respect abbreviations, initials and decimals', () => {
  assert.deepStrictEqual(T.sentences('We used e.g. rivers. Smith et al. found 3.5 m. J. R. Smith agreed. See Fig. 2. Done.'), [
    'We used e.g. rivers.', 'Smith et al. found 3.5 m.', 'J. R. Smith agreed.', 'See Fig. 2.', 'Done.',
  ]);
  assert.deepStrictEqual(T.sentences('2.1. Study area'), ['2.1. Study area']);
  assert.deepStrictEqual(T.sentences('5. Conclusions'), ['5. Conclusions']);
});

test('long sentences are cut at natural pauses', () => {
  const s = 'The model, which was fitted to annual maxima at each of the seventy-one stations, ' +
    'reproduced the observed floods well; errors were largest for small basins, where local storage dominates.';
  const parts = T.chunks(s, 110);
  assert.ok(parts.every(p => p.length <= 111), parts);
  assert.match(parts[0], /[,;]$/);
});

test('author-year citations are removed, other parenthetical content is kept', () => {
  const opts = { citations: true };
  assert.strictEqual(T.clean('by regression (Jalbert et al., 2022; Smith and Jones, 2019).', opts), 'by regression.');
  assert.strictEqual(T.clean('stations (see Hosking and Wallis, 1997, for a discussion) are used.', opts),
    'stations (see Hosking and Wallis, 1997, for a discussion) are used.');
  assert.strictEqual(T.clean('three regions (n = 24; Smith, 2020) exist.', opts), 'three regions (n equals 24) exist.');
  assert.strictEqual(T.clean('Smith et al. (2019) showed it [3, 5–7].', opts), 'Smith et al. showed it.');
  assert.strictEqual(T.clean('Smith et al. (2019) showed it [3].', { citations: false }), 'Smith et al. (2019) showed it [3].');
});

test('simple math is spoken as words', () => {
  assert.strictEqual(T.clean('so I = Q/D here'), 'so I equals Q divided by D here');
  assert.strictEqual(T.clean('a 14 % error at 5 °C, 12 km²'), 'a 14 percent error at 5 degrees Celsius, 12 km squared');
});

test('prepare follows the reading options', () => {
  const eq = { kind: 'equation', original: 'I = Q / D', page: 2 };
  assert.match(T.prepare(eq, { equations: 'announce' }), /equation is presented here. See page 2/);
  assert.strictEqual(T.prepare(eq, { equations: 'announce' }, eq), '', 'announce a run of equations once');
  assert.strictEqual(T.prepare(eq, { equations: 'skip' }), '');
  assert.strictEqual(T.prepare({ kind: 'reference', original: 'Smith, 2019.' }, { bibliography: true }), '');
  assert.strictEqual(T.prepare({ kind: 'tablecell', original: '0.84 0.91' }, { tables: 'announce' }), '');
  assert.strictEqual(T.prepare({ kind: 'text', original: 'where Q = discharge.' }, {}), 'where Q equals discharge.');
});

test('locate maps cleaned sentences back to the original text', () => {
  const original = 'Flood analysis is hard (Smith et al., 2019). We define I = Q/D here [3]. The 100-year flood rose by 14 %.';
  const spoken = T.chunks(T.clean(original, { citations: true }), 400);
  assert.strictEqual(spoken.length, 3);
  const where = T.locate(spoken, original).map(([a, b]) => original.slice(a, b));
  assert.deepStrictEqual(where, ['Flood analysis is hard', 'We define I = Q/D here', 'The 100-year flood rose by 14']);
});
