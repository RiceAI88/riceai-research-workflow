#!/usr/bin/env python3
"""Local, source-traceable literature workspace helpers. No model/API keys required."""
import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse, unquote
from urllib.request import build_opener, ProxyHandler, Request

VERSION = '0.1.0'
BASE = 'http://127.0.0.1:23119/api/users/0'
ROOT = Path(__file__).resolve().parent.parent
# Bypass environment HTTP proxies for the explicitly local Zotero API.
OPENER = build_opener(ProxyHandler({}))


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        tmp = Path(f.name)
    tmp.replace(path)


def workspace(raw):
    p = Path(raw).expanduser().resolve()
    if not (p / '.paperflow/library.json').is_file():
        raise ValueError('Not an initialized vault. Run init first.')
    return p


def read_library(vault):
    return json.loads((vault / '.paperflow/library.json').read_text(encoding='utf-8'))


def save_library(vault, lib):
    atomic_json(vault / '.paperflow/library.json', lib)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def valid_id(value):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', value):
        raise ValueError('Paper ID must contain only letters, digits, underscore or dash.')
    return value


def init_vault(raw):
    p = Path(raw).expanduser().resolve()
    for name in ['papers', 'notes', 'topics', 'templates', '.paperflow/text']:
        (p / name).mkdir(parents=True, exist_ok=True)
    if not (p / '.paperflow/library.json').exists():
        save_library(p, {'version': 1, 'papers': {}})
    template = p / 'templates/paper-note.md'
    if not template.exists():
        shutil.copyfile(ROOT / 'assets/paper-note.md', template)
    return {'vault': str(p), 'status': 'ready', 'existing_files_preserved': True}


def api(route, **params):
    url = BASE + route + ('?' + urlencode(params) if params else '')
    req = Request(url, headers={'Zotero-API-Version': '3', 'Accept': 'application/json'})
    with OPENER.open(req, timeout=15) as response:
        body = response.read().decode('utf-8')
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return body


def fetch_pages(route, limit, **params):
    result = []
    while len(result) < limit:
        count = min(100, limit - len(result))
        batch = api(route, start=len(result), limit=count, **params)
        if not isinstance(batch, list):
            raise ValueError('Expected an array from Zotero.')
        result.extend(batch)
        if len(batch) < count:
            break
    return result


def normalize(item):
    d = item.get('data', item)
    if d.get('itemType') in ['attachment', 'note', 'annotation']:
        return None
    key = d.get('key') or item.get('key') or d.get('itemKey')
    lib = item.get('library', {})
    if key:
        identifier = valid_id('z' + str(lib.get('id', '0')) + '-' + valid_id(str(key)))
    else:
        seed = json.dumps([d.get('DOI', ''), d.get('title', ''), d.get('date', ''), d.get('creators', [])], sort_keys=True)
        identifier = 'meta-' + hashlib.sha256(seed.encode()).hexdigest()[:16]
    authors = []
    for c in d.get('creators', []):
        authors.append(c.get('name') or ' '.join(x for x in [c.get('firstName'), c.get('lastName')] if x))
    return {'id': identifier, 'zotero_key': key, 'library_id': lib.get('id'), 'library_type': lib.get('type', 'user'),
            'title': d.get('title', ''), 'authors': authors, 'date': d.get('date', ''),
            'doi': d.get('DOI', ''), 'url': d.get('url', ''),
            'abstract': d.get('abstractNote', ''), 'collections': d.get('collections', []),
            'tags': [x.get('tag', '') for x in d.get('tags', []) if isinstance(x, dict)]}


def merge(vault, records):
    lib = read_library(vault)
    ids = []
    for item in records:
        rec = normalize(item)
        if rec:
            # Preserve locally registered PDFs/extractions and never overwrite notes.
            old = lib['papers'].get(rec['id'], {})
            lib['papers'][rec['id']] = {**old, **rec}
            ids.append(rec['id'])
    save_library(vault, lib)
    return {'imported': len(ids), 'ids': ids, 'pdfs_imported': False}


def import_json(vault, path):
    records = json.loads(Path(path).expanduser().read_text(encoding='utf-8'))
    if isinstance(records, dict):
        records = records.get('items')
    if not isinstance(records, list):
        raise ValueError('Expected Zotero JSON array or an object with items array (not CSL JSON).')
    return merge(vault, records)


def add_pdf(vault, path, identifier, title=None):
    source = Path(path).expanduser().resolve(strict=True)
    if source.suffix.lower() != '.pdf' or not source.is_file():
        raise ValueError('Expected an existing PDF file.')
    checksum = digest(source)
    identifier = valid_id(identifier or 'pdf-' + checksum[:16])
    lib = read_library(vault)
    old = lib['papers'].get(identifier, {})
    target = vault / 'papers' / (identifier + '.pdf')
    if old.get('sha256') and old['sha256'] != checksum:
        raise ValueError('This paper ID already points to different content; use a new ID.')
    if target.exists() and digest(target) != checksum:
        raise ValueError('Existing PDF differs; refusing to overwrite it.')
    if not target.exists():
        shutil.copyfile(source, target)
    lib['papers'][identifier] = {**old, 'id': identifier, 'title': title or old.get('title') or source.stem,
                                 'pdf': target.relative_to(vault).as_posix(), 'sha256': checksum}
    save_library(vault, lib)
    return {'id': identifier, 'pdf': str(target), 'sha256': checksum}


def import_attachment(vault, identifier, key):
    valid_id(identifier)
    lib = read_library(vault)
    if identifier not in lib['papers']:
        raise ValueError('Import the parent paper metadata first.')
    parent = lib['papers'][identifier]
    if parent.get('library_type', 'user') != 'user':
        raise ValueError('Automatic attachment import currently supports the local user library only; use add-pdf for groups.')
    children = fetch_pages('/items/' + str(parent.get('zotero_key')) + '/children', 1000)
    match = [x for x in children if x.get('key') == key or x.get('data', {}).get('key') == key]
    if not match or match[0].get('data', {}).get('contentType') != 'application/pdf':
        raise ValueError('Attachment must be a PDF child of this paper.')
    link = api('/items/' + valid_id(key) + '/file/view/url')
    if isinstance(link, dict):
        link = link.get('url')
    if not isinstance(link, str) or urlparse(link).scheme != 'file' or urlparse(link).netloc not in ('', 'localhost'):
        raise ValueError('Expected a local file URL; linked web attachments are not downloaded.')
    return add_pdf(vault, unquote(urlparse(link).path), identifier)


def extract(vault, identifier):
    valid_id(identifier)
    lib = read_library(vault)
    paper = lib['papers'][identifier]
    pdf = vault / paper['pdf']
    if digest(pdf) != paper['sha256']:
        raise ValueError('PDF changed since registration; use a new paper ID.')
    if importlib.util.find_spec('pypdf'):
        from pypdf import PdfReader
        pages = [page.extract_text() or '' for page in PdfReader(str(pdf)).pages]
    elif shutil.which('pdftotext'):
        proc = subprocess.run(['pdftotext', '-layout', str(pdf), '-'], check=True, capture_output=True, text=True)
        pages = proc.stdout.split('\f')
        if pages and not pages[-1].strip():
            pages.pop()
    else:
        raise ValueError('PDF extraction needs pypdf or pdftotext. Example: uv run --with pypdf python paperflow.py extract ...')
    target = vault / '.paperflow/text' / (identifier + '.md')
    text = '# ' + paper['title'] + '\n\n' + '\n\n'.join(f'## PDF page {i}\n\n{t}' for i, t in enumerate(pages, 1))
    target.write_text(text, encoding='utf-8')
    paper.update({'text': target.relative_to(vault).as_posix(), 'pages': len(pages),
                  'text_sha256': digest(target), 'empty_pages': [i for i, t in enumerate(pages, 1) if not t.strip()]})
    save_library(vault, lib)
    return {'text': str(target), 'pages': len(pages), 'empty_pages': paper['empty_pages'],
            'note': 'Physical PDF page numbers, not printed page labels; empty pages may need OCR.'}


def search(vault, query, top):
    # Local literal keyword search, NOT embeddings or exhaustive semantic retrieval.
    terms = [x.casefold() for x in query.split() if x]
    if not terms:
        raise ValueError('Query must not be empty.')
    lib = read_library(vault)
    hits = []
    for pid, rec in lib['papers'].items():
        candidates = []
        if rec.get('text'):
            candidates.append(vault / rec['text'])
        candidates.extend((vault / 'notes').glob(pid + '.md'))
        for path in candidates:
            if not path.exists():
                continue
            body = path.read_text(encoding='utf-8')
            sections = re.split(r'(?m)(?=^## )', body)
            for section in sections:
                lowered = section.casefold()
                score = sum(lowered.count(t) for t in terms)
                if score:
                    lines = section.splitlines()
                    hits.append({'id': pid, 'title': rec.get('title'), 'file': path.relative_to(vault).as_posix(),
                                 'section': lines[0] if lines else '', 'score': score,
                                 'snippet': next((line[:350] for line in lines if any(t in line.casefold() for t in terms)), '')})
    hits.sort(key=lambda x: (-x['score'], x['id'], x['section']))
    return {'method': 'literal-keywords', 'query': query, 'hits': hits[:top], 'matched_sections': len(hits)}


def check(vault):
    vault = vault.resolve()
    lib = read_library(vault)
    errors = []
    for pid, rec in lib['papers'].items():
        for field, checksum in [('pdf', 'sha256'), ('text', 'text_sha256')]:
            if field in rec:
                path = (vault / rec[field]).resolve()
                if not path.is_relative_to(vault):
                    errors.append(f'{pid}: {field} escapes vault')
                elif not path.is_file():
                    errors.append(f'{pid}: missing {field}')
                elif checksum in rec and digest(path) != rec[checksum]:
                    errors.append(f'{pid}: changed {field}')
        note = vault / 'notes' / (pid + '.md')
        if note.exists() and rec.get('sha256'):
            if 'source_sha256: "' + rec['sha256'] + '"' not in note.read_text(encoding='utf-8'):
                errors.append(f'{pid}: note missing current source_sha256')
    return {'ok': not errors, 'papers': len(lib['papers']), 'errors': errors,
            'scope': 'File integrity only; citation meaning and claims require original-PDF verification.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('doctor')
    p = sub.add_parser('init'); p.add_argument('--vault', required=True)
    for name in ['import-json', 'add-pdf', 'extract', 'search', 'check', 'sync-zotero', 'collections', 'children', 'import-attachment']:
        p = sub.add_parser(name); p.add_argument('--vault', required=True)
        if name == 'import-json': p.add_argument('--file', required=True)
        if name == 'add-pdf':
            p.add_argument('--file', required=True); p.add_argument('--id'); p.add_argument('--title')
        if name in ['extract', 'children', 'import-attachment']: p.add_argument('--id', required=True)
        if name == 'import-attachment': p.add_argument('--attachment', required=True)
        if name == 'search': p.add_argument('--query', required=True); p.add_argument('--top', type=int, default=10)
        if name == 'sync-zotero':
            p.add_argument('--query'); p.add_argument('--collection'); p.add_argument('--limit', type=int, default=100)
    args = parser.parse_args()
    try:
        if args.command == 'doctor':
            try:
                api('/items/top', limit=1)
                zotero = 'ready'
            except (URLError, OSError, ValueError):
                zotero = 'unavailable: open Zotero and enable its local API, or use import-json/add-pdf'
            emit({'version': VERSION, 'zotero_local_api': zotero,
                  'pypdf': bool(importlib.util.find_spec('pypdf')), 'pdftotext': bool(shutil.which('pdftotext'))})
            return 0
        if args.command == 'init':
            emit(init_vault(args.vault)); return 0
        vault = workspace(args.vault)
        if args.command == 'import-json': result = import_json(vault, args.file)
        elif args.command == 'add-pdf': result = add_pdf(vault, args.file, args.id, args.title)
        elif args.command == 'extract': result = extract(vault, args.id)
        elif args.command == 'search': result = search(vault, args.query, args.top)
        elif args.command == 'check': result = check(vault)
        elif args.command == 'sync-zotero':
            if not 1 <= args.limit <= 10000: raise ValueError('limit must be 1–10000')
            if args.collection: valid_id(args.collection)
            route = '/collections/' + args.collection + '/items/top' if args.collection else '/items/top'
            result = merge(vault, fetch_pages(route, args.limit, **({'q': args.query} if args.query else {})))
        elif args.command == 'collections': result = fetch_pages('/collections', 10000)
        elif args.command == 'children':
            paper = read_library(vault)['papers'][valid_id(args.id)]
            if not paper.get('zotero_key'): raise ValueError('This paper has no Zotero key.')
            result = fetch_pages('/items/' + paper['zotero_key'] + '/children', 1000)
        elif args.command == 'import-attachment': result = import_attachment(vault, args.id, args.attachment)
        emit(result)
        return 1 if args.command == 'check' and not result['ok'] else 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as e:
        emit({'error': str(e), 'command': args.command}); return 1


if __name__ == '__main__':
    sys.exit(main())
