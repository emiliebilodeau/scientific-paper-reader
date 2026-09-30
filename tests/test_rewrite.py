import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reader import rewrite  # noqa: E402

ORIGINAL = ('The regional model reproduced the observed 100-year flood with a median relative '
            'error of 14 %, and errors were largest for small basins.')


class Faithful(unittest.TestCase):
    def test_accepts_a_close_rewording(self):
        self.assertTrue(rewrite.faithful(ORIGINAL, 'The regional model reproduced the observed 100-year '
                                         'flood with a median relative error of 14 percent; errors '
                                         'were largest for small basins.'))

    def test_rejects_a_summary(self):
        self.assertFalse(rewrite.faithful(ORIGINAL, 'The model worked, with 100-year floods off by 14 %.'))

    def test_rejects_a_lost_number(self):
        self.assertFalse(rewrite.faithful(ORIGINAL, 'The regional model reproduced the observed hundred-year '
                                          'flood with a median relative error of 14 %, and errors were '
                                          'largest for small basins.'))

    def test_unfaithful_rewrite_falls_back_to_original(self):
        rewrite.call, real = (lambda payload: {'message': {'content':
                              '{"items":[{"id":3,"text":"Short."}]}'}}), rewrite.call
        try:
            out = rewrite.rewrite_passages([{'id': 3, 'text': ORIGINAL}])
        finally:
            rewrite.call = real
        self.assertEqual(out, [{'id': 3, 'text': ORIGINAL, 'kept_original': True}])


if __name__ == '__main__':
    unittest.main()
