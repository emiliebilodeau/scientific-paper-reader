"""Local web server: serves the interface and turns uploaded PDFs into passages."""
import json
import secrets
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import fitz

from .extract import extract

STATIC = Path(__file__).resolve().parent.parent / 'static'
FILES = {'/app.js': 'text/javascript', '/textprep.js': 'text/javascript', '/style.css': 'text/css'}
TOKEN = secrets.token_urlsafe(24)
PDF = None
PDF_LOCK = threading.Lock()
LAST_PING = None                   # set by the page; the server stops when it goes quiet
IDLE_LIMIT = 10 * 60


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, code, data, mime='application/json; charset=utf-8'):
        if isinstance(data, (dict, list)):
            data = json.dumps(data, ensure_ascii=False).encode()
        elif isinstance(data, str):
            data = data.encode()
        self.send_response(code)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(data)

    def allowed(self):
        return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

    def do_GET(self):
        if not self.allowed():
            return self.send(403, {'error': 'Accès local requis.'})
        u = urlparse(self.path)
        if u.path == '/':
            html = (STATIC / 'index.html').read_text(encoding='utf-8').replace('__TOKEN__', TOKEN)
            return self.send(200, html, 'text/html; charset=utf-8')
        if u.path in FILES:
            return self.send(200, (STATIC / u.path[1:]).read_bytes(), FILES[u.path] + '; charset=utf-8')
        if u.path == '/page':
            query = parse_qs(u.query)
            if query.get('token', [''])[0] != TOKEN:
                return self.send(403, {'error': 'Accès refusé.'})
            try:
                n = int(query.get('n', ['1'])[0]) - 1
                with PDF_LOCK:
                    if PDF is None or not 0 <= n < len(PDF):
                        raise ValueError()
                    pix = PDF[n].get_pixmap(matrix=fitz.Matrix(1.6, 1.6), alpha=False)
                return self.send(200, pix.tobytes('png'), 'image/png')
            except (ValueError, RuntimeError):
                return self.send(400, {'error': 'Page indisponible.'})
        self.send(404, {'error': 'Introuvable.'})

    def do_POST(self):
        global PDF, LAST_PING
        if not self.allowed() or self.headers.get('X-Reader-Token') != TOKEN:
            return self.send(403, {'error': 'Accès refusé.'})
        if self.path == '/ping':
            LAST_PING = time.monotonic()
            return self.send(200, {'ok': True})
        if self.path == '/quit':
            self.send(200, {'ok': True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if self.path != '/upload':
            return self.send(404, {'error': 'Introuvable.'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 60 * 1024 * 1024:
                raise ValueError('Fichier ou lot trop volumineux.')
            data = self.rfile.read(size)
            if not data.startswith(b'%PDF-'):
                raise ValueError('Choisir un fichier PDF valide.')
            candidate = fitz.open(stream=data, filetype='pdf')
            try:
                if candidate.needs_pass:
                    raise ValueError('PDF protégé : ouvrir une copie sans mot de passe.')
                if len(candidate) > 500:
                    raise ValueError('Cette version accepte au maximum 500 pages.')
                result = extract(candidate)
            except Exception:
                candidate.close()
                raise
            with PDF_LOCK:
                if PDF is not None:
                    PDF.close()
                PDF = candidate
            self.send(200, result)
        except Exception as e:
            self.send(400, {'error': str(e) or 'Impossible de lire ce PDF.'})


def stop_when_idle(server):
    """Without a console window, the page is the only way to see the server:
    stop it once no page has pinged for a while (tab or browser closed)."""
    while True:
        time.sleep(30)
        if LAST_PING is not None and time.monotonic() - LAST_PING > IDLE_LIMIT:
            server.shutdown()
            return


def main(open_browser=True, port=0):
    if sys.stdout is None:             # started with pythonw.exe: no console
        log = open(STATIC.parent / 'lecteur.log', 'w', encoding='utf-8', buffering=1)
        sys.stdout = sys.stderr = log
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    url = f'http://127.0.0.1:{server.server_port}/'
    print('\nLecteur scientifique - ouvrir : ' + url +
          '\nPour arrêter : bouton « Quitter » dans la page, ou fermer cette fenêtre.\n', flush=True)
    threading.Thread(target=stop_when_idle, args=(server,), daemon=True).start()
    if open_browser:
        threading.Timer(.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if PDF is not None:
            PDF.close()
