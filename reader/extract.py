"""Turn a PDF into an ordered list of passages ready for listening.

The pipeline is: text blocks per page -> reading order (columns) -> removal of
running heads and page numbers -> classification (heading, text, caption,
equation, table cell, reference) -> paragraphs re-joined across column and
page breaks.
"""
import collections
import math
import re

import fitz

SECTIONS = re.compile(
    r'^(?:\d+(?:\.\d+)*\.?\s*|[IVX]+\.\s*)?(abstract|résumé|summary|introduction|background|'
    r'methods?|methodology|materials? and methods?|data and methods?|méthodologie|méthodes|'
    r'results?(?: and discussion)?|résultats|discussion|conclusions?|'
    r'acknowledg(?:e)?ments?|remerciements|references|références(?: bibliographiques)?|'
    r'bibliography|bibliographie|literature cited|appendix|annexe|highlights|keywords?)\s*:?$',
    re.I)
REFS = re.compile(
    r'^(?:\d+\.?\s*|[IVX]+\.\s*)?(references|références(?: bibliographiques)?|'
    r'bibliography|bibliographie|literature cited)\s*$', re.I)
# A caption is "Figure 2." / "Fig. 2:" / "Table 1 |"; "Table 2 shows ..." is prose.
CAPTION = re.compile(r'^(fig(?:ure)?s?\.?|table(?:au)?)\s*([A-Z]?\d+[a-z]?)\s*([.:|—–-]|$)', re.I)
CAPTION_LOOSE = re.compile(r'^(fig(?:ure)?\.?|table(?:au)?)\s*[A-Z]?\d+[a-z]?\b', re.I)
MATH = re.compile(r'[=∑∫√≤≥≈±×÷∂∞∝∈∇]')
PAGE_NUMBER = re.compile(r'(?:page\s*)?\d{1,4}(?:\s*(?:of|/|sur|de)\s*\d{1,4})?', re.I)
TERMINAL = re.compile(r'[.!?:]["”’)\]]*$')
# Superscript numbers such as citation callouts "¹,²" or "[3–5]" markers.
CALLOUT = re.compile(r'^[\d\s,;–\-−*†‡§]+$|^[a-z]$|^[\d,–-]*[a-z]?$')

TEXT_FLAGS = (fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_LIGATURES) | fitz.TEXT_MEDIABOX_CLIP


def normalized(text):
    return re.sub(r'\s+', ' ', text).strip()


def fingerprint(text):
    """Make recurring headers comparable when the page number changes."""
    value = re.sub(r'https?://\S+|10\.\d{4,9}/\S+', ' URL ', text, flags=re.I)
    value = re.sub(r'\d+', '#', value.lower())
    return re.sub(r'[^a-z#]+', ' ', value).strip()


def join_lines(lines):
    """Join PDF lines into one string, repairing words hyphenated at a line end."""
    out = ''
    for line in lines:
        line = line.replace('\xad', '-').strip()
        if not line:
            continue
        if not out:
            out = line
        elif re.search(r'[a-zà-ÿ]-$', out) and re.match(r'[a-zà-ÿ]', line):
            out = out[:-1] + line          # "hydro-" + "logy"
        elif re.search(r'[\dA-Za-z][-–/]$', out):
            out = out + line               # "100-" + "year", "1960–" + "2020"
        else:
            out = out + ' ' + line
    return re.sub(r'\s+', ' ', out).strip()


def _keep_superscript(span, before):
    """Drop citation-like superscripts, keep units such as km² or m s⁻¹."""
    text = span['text'].strip()
    if not text or not CALLOUT.match(text):
        return True
    if text[0] in '-−' or re.search(r'(?:^|\s)[a-zA-Zµ°]{1,3}$', before):
        return True                        # exponent of a unit: km^2, m s^-1
    return False


def _block_lines(block):
    lines = []
    for line in block['lines']:
        parts = []
        for span in line['spans']:
            if span['flags'] & fitz.TEXT_FONT_SUPERSCRIPT and not _keep_superscript(span, ''.join(parts)):
                continue
            parts.append(span['text'])
        text = ''.join(parts).strip()
        if text:
            lines.append(text)
    return lines


def read_blocks(page):
    blocks = []
    for b in page.get_text('dict', flags=TEXT_FLAGS)['blocks']:
        if b['type'] != 0:
            continue
        lines = _block_lines(b)
        if not lines:
            continue
        spans = [s for line in b['lines'] for s in line['spans'] if s['text'].strip()]
        chars = sum(len(s['text']) for s in spans) or 1
        blocks.append({
            'lines': lines,
            'text': join_lines(lines),
            'box': [round(v, 1) for v in b['bbox']],
            'page': page.number + 1,
            'size': round(sum(s['size'] * len(s['text']) for s in spans) / chars, 2),
            'bold': sum(len(s['text']) for s in spans if s['flags'] & fitz.TEXT_FONT_BOLD
                        or 'bold' in s['font'].lower()) >= chars * .7,
        })
    return blocks


def find_gutter(blocks, width):
    """Return the x position of the gap between two columns, or None.

    The gutter is the widest vertical strip in the middle of the page that no
    column-width block crosses. Full-width blocks (titles, abstracts, wide
    figures) are ignored while searching.
    """
    narrow = [b for b in blocks if b['box'][2] - b['box'][0] < width * .6 and len(b['text']) > 1]
    if len(narrow) < 2:
        return None
    step = 2
    lo, hi = int(width * .3), int(width * .7)
    free = [x for x in range(lo, hi, step)
            if not any(b['box'][0] + 1 < x < b['box'][2] - 1 for b in narrow)]
    if not free:
        return None
    runs, start, prev = [], free[0], free[0]
    for x in free[1:] + [None]:
        if x is None or x != prev + step:
            runs.append((prev - start, start, prev))
            if x is not None:
                start = x
        if x is not None:
            prev = x
    _, a, b = max(runs)
    gutter = (a + b) / 2
    left = [n for n in narrow if n['box'][2] <= gutter]
    right = [n for n in narrow if n['box'][0] >= gutter]
    # Both sides must carry real text, otherwise this is a one-column page with
    # a short centred line (a page number, an equation) creating a false gap.
    def amount(side):
        return sum(len(n['text']) for n in side)
    if amount(left) < 150 or amount(right) < 150:
        return None
    return gutter


def reading_order(blocks, width):
    """Read full-width material in page order and each column top-to-bottom."""
    gutter = find_gutter(blocks, width)
    if gutter is None:
        return sorted(blocks, key=lambda b: (round(b['box'][1]), b['box'][0]))
    spans = sorted((b for b in blocks if b['box'][0] < gutter - 2 and b['box'][2] > gutter + 2),
                   key=lambda b: b['box'][1])
    rest = [b for b in blocks if not (b['box'][0] < gutter - 2 and b['box'][2] > gutter + 2)]
    out = []
    for span in spans + [None]:
        limit = span['box'][1] if span else math.inf
        band = [b for b in rest if b['box'][1] < limit]
        rest = [b for b in rest if b['box'][1] >= limit]
        out.extend(sorted(band, key=lambda b: (b['box'][0] >= gutter, b['box'][1], b['box'][0])))
        if span:
            out.append(span)
    return out


def body_size(pages):
    sizes = collections.Counter()
    for blocks, _, _ in pages:
        for b in blocks:
            sizes[round(b['size'] * 2) / 2] += len(b['text'])
    return sizes.most_common(1)[0][0] if sizes else 10


def classify(t, b, body):
    """Return (kind, is_heading, depth) for one block of text."""
    words = re.findall(r'[A-Za-zÀ-ÿ]{3,}', t)
    number = re.match(r'^((?:\d+\.)*\d+|[IVX]+)\.?\s+(\S.*)$', t)
    depth = number.group(1).count('.') if number and number.group(1)[0].isdigit() else (0 if number else None)
    short = len(t) < 110 and not TERMINAL.search(t.rstrip(':')) or len(t) < 60 and t.endswith(':')
    starts_upper = bool(re.match(r'^(?:[\dIVX.]+\s+)?[A-ZÀ-Ý]', t))
    larger = b['size'] >= body + 1
    if SECTIONS.fullmatch(t):
        return 'heading', True, depth
    if short and starts_upper and len(words) <= 14 and (b['bold'] or larger) and not MATH.search(t):
        if number or larger or t.upper() == t or len(words) <= 8:
            return 'heading', True, depth
    if CAPTION.match(t) or (CAPTION_LOOSE.match(t) and b['size'] < body - .4):
        return ('figure' if t.lower().startswith('fig') else 'table'), False, None
    letters = sum(c.isalpha() for c in t)
    if MATH.search(t) and len(t) < 240 and (len(words) <= 2 or (len(words) <= 4 and letters < len(t) * .45)):
        return 'equation', False, None
    digits = sum(c.isdigit() for c in t)
    if len(t) < 90 and digits >= 2 and digits > letters and not TERMINAL.search(t):
        return 'tablecell', False, None
    return 'text', False, None


def extract(doc):
    pages, margins, warnings = [], collections.Counter(), []
    for p in doc:
        blocks = read_blocks(p)
        h = p.rect.height
        for b in blocks:
            if b['box'][1] < h * .08 or b['box'][3] > h * .92:
                margins[(b['box'][1] < h * .08, fingerprint(b['text']))] += 1
        pages.append((blocks, p.rect.width, h))
        if len(p.get_text().strip()) < 40:
            warnings.append(f'Page {p.number + 1} : très peu de texte détecté. '
                            'PDF numérisé ou page graphique; OCR non inclus.')
    body = body_size(pages)
    repeat = max(2, math.ceil(len(pages) * .25))
    items, section, subsection, bibliography = [], 'Début de l’article', '', False
    for blocks, width, height in pages:
        for b in reading_order(blocks, width):
            t = b['text']
            top, bottom = b['box'][1] < height * .08, b['box'][3] > height * .92
            if (top or bottom) and len(pages) > 1 and len(t) < 200 \
                    and margins[(top, fingerprint(t))] >= repeat:
                continue                   # running head or foot
            if PAGE_NUMBER.fullmatch(t) and (top or bottom or len(b['lines']) == 1):
                continue
            kind, heading, depth = classify(t, b, body)
            if bibliography and heading and not SECTIONS.fullmatch(t):
                heading = False            # a bold author name inside the reference list
            if heading:
                if depth in (None, 0) or SECTIONS.fullmatch(t):
                    section, subsection = t, ''
                    bibliography = bool(REFS.fullmatch(t))
                else:
                    subsection = t
            if bibliography:
                kind = 'reference'
            items.append({'id': len(items), 'page': b['page'], 'box': b['box'], 'size': b['size'],
                          'section': section, 'subsection': subsection, 'kind': kind,
                          'original': t})
    if not items:
        raise ValueError('Aucun texte extractible. Cette version nécessite un PDF avec texte '
                         'sélectionnable (sans OCR).')
    items = join_paragraphs(items)
    warnings.append('L’ordre des colonnes et le retrait des en-têtes/pieds sont estimés '
                    'automatiquement; vérifie le texte préparé. Les figures et tableaux ne sont '
                    'pas interprétés.')
    return {'items': items, 'pages': len(doc), 'warnings': warnings}


def continues(prev, cur):
    """True when cur is the rest of a paragraph cut by a column or page break."""
    a, b = prev['original'], cur['original']
    if TERMINAL.search(a) or not b:
        return False
    if re.match(r'^[a-zà-ÿ(,;]', b) or re.search(r'[,;\-–(]$|\b(?:the|of|and|in|a|an|to|for|with|by)$', a):
        return True
    # The paragraph ends mid-sentence; a capitalised continuation is still likely.
    return bool(re.search(r'[A-Za-zÀ-ÿ\d)]$', a)) and not re.match(r'^[•\-–]\s', b)


def join_paragraphs(items):
    """Glue paragraph pieces back together, even around a figure caption."""
    out = []
    for item in items:
        last_text = next((i for i in range(len(out) - 1, -1, -1) if out[i]['kind'] != 'figure'
                          and out[i]['kind'] != 'table' and out[i]['kind'] != 'tablecell'), None)
        if item['kind'] == 'text' and last_text is not None:
            prev = out[last_text]
            if prev['kind'] == 'text' and prev['section'] == item['section'] and continues(prev, item):
                prev['original'] = join_lines([prev['original'], item['original']])
                prev.setdefault('pages', [prev['page']])
                if item['page'] not in prev['pages']:
                    prev['pages'].append(item['page'])
                continue
        out.append(item)
    for i, item in enumerate(out):
        item['id'] = i
    return out
