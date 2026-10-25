"""Bounded official-source lookup. Search public identifiers, never incident/chat text."""
from datetime import datetime, timezone
from functools import lru_cache
from html.parser import HTMLParser
import hashlib
import os
import re
import time
from urllib.parse import urljoin, urlsplit

import httpx

VERSION = 'official-web-v1'
ALLOWED_HOSTS = {'www.cdc.gov', 'www.osha.gov', 'www.ilo.org', 'chemicalsafety.ilo.org'}
CAS_INDEX = 'https://www.cdc.gov/niosh/npg/npgdcas.html'


def allowed_url(url):
    p = urlsplit(url)
    return (p.scheme == 'https' and p.hostname in ALLOWED_HOSTS
            and not p.username and not p.password and p.port in (None, 443))


class PageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.links, self.hidden = [], [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'nav', 'header', 'footer'):
            self.hidden += 1
        if tag == 'a':
            self.links.append(dict(attrs).get('href', ''))
        if tag in ('p', 'div', 'tr', 'br', 'h1', 'h2', 'h3', 'h4', 'li'):
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'nav', 'header', 'footer'):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, value):
        if not self.hidden:
            self.parts.append(value)

    def text(self):
        return '\n'.join(re.sub(r'\s+', ' ', s).strip() for s in ''.join(self.parts).splitlines() if s.strip())


def fetch_html(client, url):
    # Validate every redirect. Search credentials are supplied ONLY to the Naver request.
    for _ in range(4):
        if not allowed_url(url):
            raise ValueError('unapproved_source')
        with client.stream('GET', url, follow_redirects=False) as response:
            if response.is_redirect:
                url = urljoin(url, response.headers.get('location', ''))
                continue
            response.raise_for_status()
            if 'text/html' not in response.headers.get('content-type', ''):
                raise ValueError('unsupported_content_type')
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > 1_500_000:
                    raise ValueError('source_too_large')
            return url, body.decode('utf-8', errors='replace')
    raise ValueError('redirect_limit')


def focused_excerpt(text):
    # Preserve health/response sections even on pages with long navigation or tables.
    lines = text.splitlines()
    keys = ('exposure routes', 'symptoms', 'target organs', 'personal protection', 'first aid',
            'incompatibilities', 'fire fighting', 'spillage', 'chemical dangers', 'ghs', 'classification')
    positions = [i for i, line in enumerate(lines) if any(k in line.lower() for k in keys)]
    chosen = set(range(min(20, len(lines))))
    for pos in positions:
        chosen.update(range(pos, min(pos + 22, len(lines))))
    return '\n'.join(lines[i] for i in sorted(chosen))[:7500]


@lru_cache(maxsize=4)
def cdc_index(day):
    with httpx.Client(timeout=6, follow_redirects=False) as client:
        _, page = fetch_html(client, CAS_INDEX)
    # CDC lists CAS and a substance link in the same table row.
    result = {}
    for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>', page, re.S | re.I):
        cas = re.search(r'\b\d{2,7}-\d{2}-\d\b', row)
        link = re.search(r'href=[\"\']([^\"\']*npgd\d+\.html)[\"\']', row, re.I)
        if cas and link:
            result[cas[0]] = urljoin(CAS_INDEX, link[1])
    return result


def lookup(materials, gaps, *, enabled=True, client=None):
    """At most two identified materials and two fetched pages, with explicit failure state."""
    report = {'version': VERSION, 'status': 'not_needed', 'queries': [], 'results': [],
              'unresolved': list(gaps), 'errors': []}
    if not gaps or not materials:
        return report
    if not enabled:
        report['status'] = 'disabled'
        return report
    report['status'] = 'no_verified_source'
    owned = client is None
    client = client or httpx.Client(timeout=6, follow_redirects=False)
    started = time.monotonic()
    try:
        for material in materials[:2]:
            if time.monotonic() - started > 20:
                report['errors'].append('lookup_time_budget')
                break
            cas = material.get('cas_raw', '')
            if not re.fullmatch(r'\d{2,7}-\d{2}-\d', cas):
                continue
            urls = []
            client_id, secret = os.getenv('NAVER_CLIENT_ID'), os.getenv('NAVER_CLIENT_SECRET')
            if client_id and secret:
                query = f'{cas} chemical safety first aid site:cdc.gov/niosh/npg'
                report['queries'].append(query)
                try:
                    response = client.get('https://openapi.naver.com/v1/search/webkr.json',
                        params={'query': query, 'display': 5},
                        headers={'X-Naver-Client-Id': client_id, 'X-Naver-Client-Secret': secret})
                    response.raise_for_status()
                    urls = [item['link'] for item in response.json().get('items', [])
                            if allowed_url(item.get('link', ''))]
                except (httpx.HTTPError, ValueError, KeyError):
                    report['errors'].append('naver_search_unavailable')
            # CAS-index fallback is also an official lookup, not a guessed chemical URL.
            try:
                direct = cdc_index(datetime.now(timezone.utc).date().isoformat()).get(cas)
                if direct:
                    urls.insert(0, direct)
            except (httpx.HTTPError, ValueError):
                report['errors'].append('cdc_index_unavailable')
            for url in list(dict.fromkeys(urls))[:3]:
                if time.monotonic() - started > 25:
                    break
                try:
                    final_url, raw = fetch_html(client, url)
                    parser = PageText(); parser.feed(raw)
                    text = parser.text()
                    # Reject indexes/search results and CAS mentions unrelated to a substance page.
                    if not re.search(r'/npg/npgd\d+\.html$', urlsplit(final_url).path):
                        continue
                    if cas not in text or 'First Aid' not in text:
                        continue
                    text = focused_excerpt(text)
                    row = {'chunk_id': 'web-' + hashlib.sha256((final_url + text).encode()).hexdigest()[:24],
                           'doc_id': 'official_web', 'doc_type': 'official_web',
                           'filename': 'CDC/NIOSH ' + material['name_raw'],
                           'source_url': final_url, 'pdf_page_start': None, 'pdf_page_end': None,
                           'content_type': 'official_web', 'graph_group': 'web', 'cas_raw': cas,
                           'fetched_at': datetime.now(timezone.utc).isoformat(),
                           'identity_basis': 'CAS_exact_match_in_substance_page',
                           'text': text, 'source_sha256': hashlib.sha256(raw.encode()).hexdigest(),
                           'limitations': 'NIOSH substance reference; not the specific product SDS or local hospital directory'}
                    report['results'].append(row)
                    break
                except (httpx.HTTPError, ValueError):
                    report['errors'].append('official_page_unavailable')
        if report['results']:
            report['status'] = 'supplemented'
        return report
    finally:
        if owned:
            client.close()
