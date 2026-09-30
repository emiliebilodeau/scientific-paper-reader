import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from make_pdf import ARTICLE, glued_heading_page, two_column_article  # noqa: E402
from reader.extract import extract, find_gutter, join_lines, read_blocks  # noqa: E402


def prose():
    """The article's paragraphs as plain text, superscript citations removed."""
    return [re.sub(r'(?<=[a-z]{4})<sup>[\d,]+</sup>', '', t).replace('<sup>', '').replace('</sup>', '')
            for k, t in ARTICLE if k == 'p']


def squash(text):
    return re.sub(r'\s+', ' ', text).strip()


class TwoColumnArticle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items = extract(two_column_article())['items']
        cls.text = [i for i in cls.items if i['kind'] == 'text']

    def test_every_paragraph_is_kept_whole_and_in_order(self):
        spoken = ' '.join(squash(i['original']) for i in self.text)
        position = 0
        for paragraph in prose():
            found = spoken.find(squash(paragraph), position)
            self.assertGreaterEqual(found, 0, 'missing or broken: ' + paragraph[:70])
            position = found

    def test_columns_are_not_interleaved(self):
        sections = [i['section'] for i in self.items if i['kind'] != 'reference']
        order = list(dict.fromkeys(sections))
        self.assertEqual(order, ['Début de l’article', '1. Introduction', '2. Data and methods',
                                 '3. Results', '4. Discussion', '5. Conclusions'])

    def test_only_the_bibliography_is_marked_as_reference(self):
        refs = [i['original'] for i in self.items if i['kind'] == 'reference']
        self.assertEqual(len(refs), 3)
        self.assertTrue(refs[0].startswith('References'))

    def test_classification(self):
        kind = {squash(i['original']): i['kind'] for i in self.items}
        self.assertEqual(kind['I = Q / D'], 'equation')
        self.assertEqual(kind['where Q = discharge and D = drainage area.'], 'text')
        self.assertEqual(kind['Table 1. Cross-validation scores for the three regions.'], 'table')
        self.assertEqual(kind['2.2. Statistical model'], 'heading')
        self.assertEqual(kind['1.1 IDF Curves'], 'heading')
        sub = next(i for i in self.items if i['original'].startswith('Intensity-duration'))
        self.assertEqual((sub['section'], sub['subsection']), ('1. Introduction', '1.1 IDF Curves'))

    def test_every_line_keeps_its_place_on_the_page(self):
        for item in self.items:
            covered = ''.join(item['original'][s[0]:s[1]] for s in item['spans'])
            self.assertEqual(covered.replace(' ', ''), item['original'].replace(' ', ''))
            for start, end, page, x0, y0, x1, y1 in item['spans']:
                self.assertTrue(0 <= x0 < x1 <= 612 and 0 <= y0 < y1 <= 792)

    def test_citation_superscripts_dropped_unit_exponents_kept(self):
        joined = ' '.join(i['original'] for i in self.text)
        self.assertIn('problem in hydrology.', joined)
        self.assertIn('850 m3 s−1', joined)

    def test_gutter_found_between_columns(self):
        doc = two_column_article()
        gutter = find_gutter(read_blocks(doc[0]), doc[0].rect.width)
        self.assertTrue(286 < gutter < 326, gutter)


class LongArticle(unittest.TestCase):
    def test_running_heads_removed_and_paragraphs_joined_across_breaks(self):
        items = extract(two_column_article(repeat=4))['items']
        text = [i for i in items if i['kind'] == 'text']
        self.assertFalse(any('Journal of Hydrology 612' in i['original'] for i in text))
        self.assertTrue(any(len(i.get('pages', [])) > 1 for i in text), 'no paragraph spans two pages')
        spoken = ' '.join(squash(i['original']) for i in text)
        for paragraph in prose():
            self.assertEqual(spoken.count(squash(paragraph)), 4, paragraph[:60])
        # A paragraph never starts in the middle of a sentence.
        for i in text:
            self.assertRegex(i['original'], r'^[A-Zw(]', i['original'][:60])


class OneColumnArticle(unittest.TestCase):
    def test_single_column_is_read_top_to_bottom(self):
        doc = two_column_article(columns=1)
        self.assertIsNone(find_gutter(read_blocks(doc[0]), doc[0].rect.width))
        spoken = ' '.join(squash(i['original']) for i in extract(doc)['items'] if i['kind'] == 'text')
        for paragraph in prose():
            self.assertIn(squash(paragraph), spoken)


class Headings(unittest.TestCase):
    def test_plain_numbered_subsection_glued_to_its_paragraph(self):
        items = extract(glued_heading_page())['items']
        self.assertEqual([i['kind'] for i in items], ['heading', 'text'])
        self.assertEqual(items[0]['original'], '1.1 IDF Curves')
        self.assertEqual(items[1]['subsection'], '1.1 IDF Curves')


class Lines(unittest.TestCase):
    def test_hyphenation(self):
        self.assertEqual(join_lines(['a hydro-', 'logical model']), 'a hydrological model')
        self.assertEqual(join_lines(['the 100-', 'year flood']), 'the 100-year flood')
        self.assertEqual(join_lines(['two', 'lines']), 'two lines')


if __name__ == '__main__':
    unittest.main()
