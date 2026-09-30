"""Lecteur scientifique local. Python 3.10+, PyMuPDF. No remote PDF service."""
import os

from reader.server import main

if __name__ == '__main__':
    main(open_browser=os.environ.get('READER_NO_BROWSER') != '1', port=int(os.environ.get('READER_PORT', '0')))
