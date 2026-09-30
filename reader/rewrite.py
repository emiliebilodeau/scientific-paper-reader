"""Optional rewording of English prose by a local Ollama model."""
import json
import re
import urllib.error
import urllib.request

MODEL = 'qwen3.5:4b'
OLLAMA = 'http://127.0.0.1:11434/api/chat'
MAX_BATCH = 4

SYSTEM = ("You edit scientific English for listening. Rewrite each passage in clear, natural "
          "spoken English while preserving every factual claim, technical term, number, unit, "
          "uncertainty, qualification, and logical relationship. Do not add explanations or "
          "facts. Do not summarize, do not shorten, do not skip any sentence. Remove only "
          "citation markers and reference callouts that remain in the text. Keep each passage "
          "separate and retain its integer id. Return JSON only, with the shape "
          "{\"items\":[{\"id\":1,\"text\":\"...\"}]}.")


def numbers(text):
    return set(re.findall(r'\d+(?:[.,]\d+)?', text))


def faithful(original, rewritten):
    """Reject a rewrite that dropped content: too short, or numbers missing."""
    a, b = len(original.split()), len(rewritten.split())
    if a >= 12 and b < a * .75:
        return False
    return numbers(original) <= numbers(rewritten)


def check(rows):
    if not isinstance(rows, list) or not 0 < len(rows) <= MAX_BATCH:
        raise ValueError(f'Le lot de reformulation doit contenir de 1 à {MAX_BATCH} passages.')
    checked = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('id'), int):
            raise ValueError('Un passage de reformulation est invalide.')
        text = row.get('text', '')
        if not isinstance(text, str) or not text.strip() or len(text) > 6000:
            raise ValueError('Un passage est vide ou trop long (maximum 6 000 caractères).')
        checked.append({'id': row['id'], 'text': text})
    return checked


def call(payload):
    request = urllib.request.Request(OLLAMA, data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                                     headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise RuntimeError(f'Ollama fonctionne, mais le modèle manque. Dans Ollama, lance : ollama run {MODEL}') from e
        raise RuntimeError(f'Ollama a répondu avec une erreur HTTP {e.code}.') from e
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise RuntimeError(f'Le modèle local est indisponible. Installe Ollama, puis télécharge le modèle {MODEL} '
                           '(instructions dans LIRE_MOI.txt).') from e


def rewrite_passages(rows):
    """Return [{'id', 'text', 'kept_original'}]; unfaithful rewrites fall back to the original."""
    checked = check(rows)
    result = call({
        'model': MODEL, 'stream': False, 'format': 'json', 'think': False, 'keep_alive': '5m',
        # Ollama's default context is small and silently truncates long prompts.
        'options': {'temperature': 0.1, 'num_ctx': 8192},
        'messages': [{'role': 'system', 'content': SYSTEM},
                     {'role': 'user', 'content': json.dumps({'items': checked}, ensure_ascii=False)}]})
    try:
        output = json.loads(result['message']['content'])['items']
        by_id = {item['id']: item['text'] for item in output
                 if isinstance(item, dict) and isinstance(item.get('id'), int)
                 and isinstance(item.get('text'), str) and item['text'].strip()}
    except (KeyError, TypeError, ValueError) as e:
        raise RuntimeError('Le modèle a renvoyé une réponse illisible. Réessaie cette section.') from e
    out = []
    for row in checked:
        text = by_id.get(row['id'])
        ok = text is not None and faithful(row['text'], text)
        out.append({'id': row['id'], 'text': text if ok else row['text'], 'kept_original': not ok})
    return out
