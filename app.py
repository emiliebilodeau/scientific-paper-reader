"""Lecteur scientifique local. Python 3.10+, PyMuPDF. No remote PDF service."""
import collections
import math
import json
import re
import secrets
import threading
import webbrowser
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import fitz

ROOT = Path(__file__).resolve().parent
TOKEN = secrets.token_urlsafe(24)
PDF = None
PDF_LOCK = threading.Lock()
REWRITE_MODEL = 'qwen3.5:4b'
SECTIONS = re.compile(r'^(?:\d+(?:\.\d+)*[. ]*\s*)?(abstract|résumé|introduction|background|methods?|methodology|materials? and methods?|méthodologie|méthodes|results?(?: and discussion)?|résultats|discussion|conclusions?|acknowledg(?:e)?ments?|remerciements|references|références(?: bibliographiques)?|bibliography|bibliographie|appendix|annexe)\s*$', re.I)
REFS = re.compile(r'^(?:\d+[. ]*\s*)?(references|références(?: bibliographiques)?|bibliography|bibliographie)\s*$', re.I)
CAPTION = re.compile(r'^(?:fig(?:ure)?\.?|table(?:au)?)\s*\d+\b', re.I)

def normalized(text):
    return re.sub(r'\s+', ' ', text).strip()

def fingerprint(text):
    """Make recurring headers comparable when the page number changes."""
    value = re.sub(r'https?://\S+|10\.\d{4,9}/\S+', ' URL ', text, flags=re.I)
    value = re.sub(r'\d+', '#', value.lower())
    return re.sub(r'[^a-z#]+', ' ', value).strip()

def column_split(blocks, width):
    """Estimate a genuine central gutter from text-block centers."""
    centers = sorted((b['box'][0]+b['box'][2])/2 for b in blocks
                     if b['box'][2]-b['box'][0] < width*.68)
    candidates = []
    for a, b in zip(centers, centers[1:]):
        gap = b-a
        split = (a+b)/2
        left = sum(x < split for x in centers)
        right = len(centers)-left
        if width*.28 < split < width*.72 and left >= 2 and right >= 2 and gap >= width*.055:
            balance = min(left,right)/max(left,right)
            candidates.append((gap*balance, split))
    return max(candidates)[1] if candidates else None

def ordered(blocks, width):
    """Read spanning material in page order and each column top-to-bottom."""
    split = column_split(blocks, width)
    if split is None:
        return sorted(blocks, key=lambda b:(b['box'][1],b['box'][0]))
    spans = [b for b in blocks if b['box'][2]-b['box'][0] >= width*.68 or
             (b['box'][0] < split-8 and b['box'][2] > split+8)]
    pending = [b for b in blocks if b not in spans]
    out=[]
    for span in sorted(spans,key=lambda b:(b['box'][1],b['box'][0])):
        band=[b for b in pending if b['box'][1] < span['box'][1]]
        out.extend(sorted(band,key=lambda b:(b['box'][0]>=split,b['box'][1],b['box'][0])))
        pending=[b for b in pending if b not in band]
        out.append(span)
    out.extend(sorted(pending,key=lambda b:(b['box'][0]>=split,b['box'][1],b['box'][0])))
    return out

def extract(doc):
    pages, margins, warnings = [], collections.Counter(), []
    for p in doc:
        blocks = []
        for b in p.get_text('dict')['blocks']:
            if b['type'] != 0: continue
            kept=[]
            for line in b['lines']:
                value=''.join(s['text'] for s in line['spans']).strip()
                if not value or re.fullmatch(r'\d{1,4}',value): continue
                # Superscript footnote callouts are common; do not treat them as page numbers.
                kept.append(value)
            text='\n'.join(kept).strip()
            if not text: continue
            spans=[s for line in b['lines'] for s in line['spans']]
            item = {'original':text,'box':list(b['bbox']), 'page':p.number+1,
                    'size': max((s.get('size',0) for s in spans),default=0),
                    'bold':bool(spans) and sum(bool(s.get('flags',0)&16) for s in spans)>=len(spans)*.7}
            blocks.append(item)
            if b['bbox'][1] < p.rect.height*.08 or b['bbox'][3] > p.rect.height*.92:
                margins[(b['bbox'][1] < p.rect.height*.08, fingerprint(text))] += 1
        pages.append((blocks, p.rect.width, p.rect.height))
        if len(p.get_text().strip()) < 40:
            warnings.append(f'Page {p.number+1} : très peu de texte détecté. PDF numérisé ou page graphique; OCR non inclus.')
    items, section, bibliography = [], 'Début de l’article', False
    for blocks, width, height in pages:
        for b in ordered(blocks, width):
            t = normalized(b['original'])
            top=b['box'][1] < height*.08
            bottom=b['box'][3] > height*.92
            # Ignore recurring running heads/feet even when their page number changes.
            if len(pages)>1 and (top or bottom):
                threshold=max(2,math.ceil(len(pages)*.25))
                if margins[(top,fingerprint(t))] >= threshold: continue
            # Page-number-only blocks, plus short running matter in the extreme footer.
            if re.fullmatch(r'(?:page\s*)?\d{1,4}(?:\s*(?:of|/|sur)\s*\d{1,4})?',t,re.I): continue
            if bottom and b['box'][1] > height*.96 and len(t)<100 and b.get('size',12)<10.5:
                continue
            known_heading=bool(SECTIONS.fullmatch(t))
            number=re.match(r'^(\d+(?:\.\d+)*)\.?\s+(.+)$',t)
            depth=number.group(1).count('.') if number else None
            title_case=bool(re.search(r'[A-Za-z]',t)) and t.upper()==t
            numbered_title=bool(number and re.fullmatch(r'[A-Z0-9][A-Z0-9 ,:&()’\'–/-]{1,90}',number.group(2)))
            # Many journal headings are numbered and bold but use names such as
            # "Statistical Model" that are absent from a fixed heading list.
            style_heading=(b.get('bold',False) and len(t)<105 and
                ((numbered_title and b.get('size',0)>=9) or
                 (numbered_title and depth==0 and b.get('size',0)>=9) or
                 (title_case and b.get('size',0)>=11.5)))
            heading = known_heading or style_heading
            if heading:
                # Subsection headings remain grouped under their main section.
                if known_heading or depth in (None,0):
                    section = t
                    bibliography = bool(REFS.fullmatch(t))
            if bibliography: kind = 'reference'
            elif heading: kind = 'heading'
            elif CAPTION.match(t): kind = 'figure' if re.match(r'^fig',t,re.I) else 'table'
            elif (re.search(r'[=∑∫√≤≥≈]',t) and len(t)<240 and len(re.findall(r'\b[A-Za-zÀ-ÿ]{3,}\b',t))<6): kind='equation'
            else: kind='text'
            items.append({**b,'id':len(items),'section':section,'kind':kind})
    if not items:
        raise ValueError('Aucun texte extractible. Cette version nécessite un PDF avec texte sélectionnable (sans OCR).')
    warnings.append('L’ordre des colonnes et le retrait des en-têtes/pieds sont estimés automatiquement. Les titres numérotés sont reconnus selon leur style; vérifie le texte préparé. Les figures et tableaux ne sont pas interprétés.')
    return {'items':items,'pages':len(doc),'warnings':warnings}

def rewrite_passages(rows):
    """Ask the optional Ollama service on this computer to smooth English prose."""
    if not rows or len(rows) > 8:
        raise ValueError('Le lot de reformulation doit contenir de 1 à 8 passages.')
    checked=[]
    for row in rows:
        if not isinstance(row,dict) or not isinstance(row.get('id'),int):
            raise ValueError('Un passage de reformulation est invalide.')
        text=row.get('text','')
        if not isinstance(text,str) or not text.strip() or len(text)>12000:
            raise ValueError('Un passage est vide ou trop long (maximum 12 000 caractères).')
        checked.append({'id':row['id'],'text':text})
    system=("You edit scientific English for listening. Rewrite each passage in clear, "
            "natural spoken English while preserving every factual claim, technical term, "
            "number, unit, uncertainty, qualification, and logical relationship. Do not "
            "add explanations or facts. Do not summarize or shorten substantially. Remove "
            "only citation markers and reference callouts that remain in the text. Keep "
            "each passage separate and retain its integer id. Return JSON only, with the "
            "shape {\"items\":[{\"id\":1,\"text\":\"...\"}]}.")
    payload=json.dumps({'model':REWRITE_MODEL,'stream':False,'format':'json',
        'keep_alive':'5m','options':{'temperature':0.1},
        'messages':[{'role':'system','content':system},
                    {'role':'user','content':json.dumps({'items':checked},ensure_ascii=False)}]},
        ensure_ascii=False).encode('utf-8')
    request=urllib.request.Request('http://127.0.0.1:11434/api/chat',data=payload,
        headers={'Content-Type':'application/json'},method='POST')
    try:
        with urllib.request.urlopen(request,timeout=240) as response:
            result=json.loads(response.read())
    except urllib.error.HTTPError as e:
        if e.code==404:
            raise RuntimeError('Ollama fonctionne, mais le modèle manque. Dans Ollama, lance : ollama run qwen3.5:4b') from e
        raise RuntimeError(f'Ollama a répondu avec une erreur HTTP {e.code}.') from e
    except (urllib.error.URLError,TimeoutError,ConnectionError) as e:
        raise RuntimeError('Le modèle local est indisponible. Installe Ollama, puis télécharge le modèle qwen3.5:4b (instructions dans LIRE_MOI.txt).') from e
    try:
        content=result['message']['content']
        parsed=json.loads(content)
        output=parsed['items']
        by_id={item['id']:item['text'] for item in output
               if isinstance(item,dict) and isinstance(item.get('id'),int)
               and isinstance(item.get('text'),str) and item['text'].strip()}
    except (KeyError,TypeError,ValueError) as e:
        raise RuntimeError('Le modèle a renvoyé une réponse illisible. Réessaie ce lot.') from e
    if set(by_id)!= {row['id'] for row in checked}:
        raise RuntimeError('Le modèle a omis un passage. Rien de ce lot n’a été appliqué; réessaie.')
    return [{'id':row['id'],'text':by_id[row['id']]} for row in checked]

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def send(self, code, data, mime='application/json; charset=utf-8'):
        if isinstance(data, (dict,list)): data=json.dumps(data,ensure_ascii=False).encode()
        elif isinstance(data,str): data=data.encode()
        self.send_response(code)
        self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.end_headers()
        self.wfile.write(data)
    def allowed(self):
        return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'
    def do_GET(self):
        if not self.allowed(): return self.send(403,{'error':'Accès local requis.'})
        u=urlparse(self.path)
        if u.path=='/':
            html=(ROOT/'interface.html').read_text(encoding='utf-8').replace('__TOKEN__',TOKEN)
            return self.send(200,html,'text/html; charset=utf-8')
        if u.path=='/page':
            if parse_qs(u.query).get('token',[''])[0]!=TOKEN: return self.send(403,{'error':'Accès refusé.'})
            try:
                n=int(parse_qs(u.query).get('n',['1'])[0])-1
                with PDF_LOCK:
                    if PDF is None or n<0 or n>=len(PDF): raise ValueError()
                    pix=PDF[n].get_pixmap(matrix=fitz.Matrix(1.4,1.4),alpha=False)
                return self.send(200,pix.tobytes('png'),'image/png')
            except (ValueError, RuntimeError): return self.send(400,{'error':'Page indisponible.'})
        self.send(404,{'error':'Introuvable.'})
    def do_POST(self):
        global PDF
        if not self.allowed() or self.headers.get('X-Reader-Token')!=TOKEN:
            return self.send(403,{'error':'Accès refusé.'})
        if self.path not in ('/upload','/rewrite'): return self.send(404,{'error':'Introuvable.'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            limit=60*1024*1024 if self.path=='/upload' else 256*1024
            if not 0<size<=limit: raise ValueError('Fichier ou lot trop volumineux.')
            data=self.rfile.read(size)
            if self.path=='/rewrite':
                payload=json.loads(data)
                rows=payload.get('items',[])
                if not isinstance(rows,list): raise ValueError('Le lot de reformulation est invalide.')
                output=rewrite_passages(rows)
                return self.send(200,{'items':output})
            if not data.startswith(b'%PDF-'): raise ValueError('Choisir un fichier PDF valide.')
            candidate=fitz.open(stream=data,filetype='pdf')
            try:
                if candidate.needs_pass: raise ValueError('PDF protégé : ouvrir une copie sans mot de passe.')
                if len(candidate)>500: raise ValueError('Cette version accepte au maximum 500 pages.')
                result=extract(candidate)
            except Exception:
                candidate.close()
                raise
            with PDF_LOCK:
                if PDF is not None: PDF.close()
                PDF=candidate
            self.send(200,result)
        except Exception as e:
            self.send(400,{'error':str(e) or 'Impossible de lire ce PDF.'})

def main():
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    url=f'http://127.0.0.1:{server.server_port}/'
    print('\nLecteur scientifique - ouvrir : '+url+'\nFermer cette fenêtre pour arrêter.\n',flush=True)
    threading.Timer(.6,lambda:webbrowser.open(url)).start()
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        server.server_close()
        if PDF is not None: PDF.close()

if __name__=='__main__': main()
