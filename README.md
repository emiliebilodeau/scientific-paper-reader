# Lecteur scientifique

Lecteur local d’articles scientifiques en PDF : il extrait le texte, le nettoie
(citations, en-têtes, bibliographie), le remet dans l’ordre de lecture et le lit
à voix haute avec les voix du navigateur, phrase par phrase.

Guide d’utilisation complet : [LIRE_MOI.txt](LIRE_MOI.txt).

## Lancer

- Windows : double-cliquer sur `Lancer.bat` (crée `.venv` et installe PyMuPDF la première fois).
- Ailleurs : `python -m venv .venv`, `.venv/bin/pip install -r requirements.txt`, puis `.venv/bin/python app.py`.

## Organisation

| Fichier | Rôle |
| --- | --- |
| `app.py` | Point d’entrée (démarre le serveur local et ouvre le navigateur). |
| `reader/extract.py` | PDF → passages : colonnes, en-têtes/pieds, titres, légendes, équations, bibliographie, paragraphes recollés entre colonnes et pages. |
| `reader/server.py` | Serveur HTTP local (127.0.0.1 seulement, jeton de session). |
| `static/textprep.js` | Nettoyage du texte, mots pour les symboles, découpage en phrases (partagé avec les tests). |
| `static/app.js` | Interface et moteur de lecture (phrase surlignée, reprise si le navigateur saute une phrase). |

## Tests

```
python -m unittest discover -s tests
node --test tests/textprep.test.js
```

Les tests génèrent des PDF synthétiques à deux colonnes (`tests/make_pdf.py`) et
vérifient que chaque paragraphe est extrait en entier et dans l’ordre.
