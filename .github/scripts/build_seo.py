"""diforum.org 검색 등록용 sitemap.xml·rss.xml 생성기.

    python .github/scripts/build_seo.py           # 생성(저장소 루트에 sitemap.xml·rss.xml)
    python .github/scripts/build_seo.py --check   # 생성 결과 검증(XML 파싱·URL↔파일·robots.txt)

- sitemap: 첫 화면, 루트의 뉴스레터 호별 페이지(YYYY-MM-주제.html), update/·forum/·library/ 아래 페이지.
  lastmod는 파일의 git 마지막 커밋 시각. 허용 목록 밖·noindex·canonical이 다른 주소인 페이지는 빼고 목록을 출력한다.
- rss: update/feed.json(DI 동향 최근 글)에서 만든다. sitemap에 실린 update/<no>.html 글만 넣는다.
  feed.json이 깨져 있으면 기존 rss.xml을 그대로 두고 sitemap은 계속 갱신한다.
- 출력은 입력이 같으면 항상 같다(생성 시각을 넣지 않음) → 바뀐 것이 없으면 커밋도 생기지 않는다.
- 표준 라이브러리만 쓴다(GitHub Actions에서 그대로 실행).
"""
import argparse
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from html.parser import HTMLParser
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[2]
SITE = 'https://diforum.org'
KST = timezone(timedelta(hours=9))

# 공개 페이지 허용 목록(저장소 루트 기준 경로 정규식)
INCLUDE = [
    r'index\.html',
    r'\d{4}-\d{2}-[a-z0-9-]+\.html',      # 뉴스레터 호별 페이지
    r'update/[^/]+\.html',               # DI 동향 글·목록
    r'forum/[^/]+\.html',
    r'library/(?:[^/]+/)?index\.html',
]
RSS_ITEM = r'update/[0-9]{6}(?:-[0-9]+)?\.html'   # RSS에는 DI 동향 글만
SAFE_PATH = re.compile(r'[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*')   # URL에 그대로 쓸 수 있는 경로만
# 허용 목록 밖이지만 일부러 뺀 페이지의 사유(보고용). 여기 없는 것은 '허용 목록 밖'으로 표시.
REASONS = [
    (r'update-test/.*', '시험용 DI 동향(noindex)'),
    (r'confirm\.html', '구독 확인 페이지(noindex)'),
    (r'naver[0-9a-f]+\.html', '네이버 소유확인 파일'),
    (r'google[0-9a-f]+\.html', '구글 소유확인 파일'),
    (r'kpbma-.*-qa-.*\.html', '수강생 전용 페이지(noindex)'),
    (r'privacy\.html', '개인정보 처리방침(검색 대상 아님)'),
]


class HeadMeta(HTMLParser):
    """<meta name=robots>·<link rel=canonical>을 속성 순서·공백·대소문자와 관계없이 읽는다."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.noindex = False
        self.canonical = None

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or '') for k, v in attrs}
        if tag == 'meta' and a.get('name', '').strip().lower() in ('robots', 'googlebot'):
            words = [w.strip() for w in a.get('content', '').lower().split(',')]
            if 'noindex' in words or 'none' in words:
                self.noindex = True
        elif tag == 'link' and 'canonical' in a.get('rel', '').lower().split() and self.canonical is None:
            self.canonical = a.get('href', '').strip() or None

    handle_startendtag = handle_starttag


def head_meta(path):
    p = HeadMeta()
    text = path.read_text(encoding='utf-8', errors='replace')
    end = text.lower().find('</head>')
    p.feed(text[:end if end > 0 else 200000])
    return p


def git(*args):
    r = subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
    return r.stdout.strip() if r.returncode == 0 else ''


def lastmod(rel):
    iso = git('log', '-1', '--format=%cI', '--', rel)
    if iso:
        return iso
    # 아직 커밋 전인 파일(로컬 시험)은 파일 수정 시각
    return datetime.fromtimestamp((ROOT / rel).stat().st_mtime, KST).isoformat(timespec='seconds')


def url_of(rel):
    if rel == 'index.html':
        return SITE + '/'
    if rel.endswith('/index.html'):
        return f'{SITE}/{rel[:-len("index.html")]}'
    return f'{SITE}/{rel}'


def rel_of(url):
    """sitemap·rss의 URL → 저장소 기준 상대 경로(사이트 밖·이상한 경로·없는 파일이면 None)."""
    if not isinstance(url, str) or not url.startswith(SITE + '/'):
        return None
    rel = url[len(SITE) + 1:]
    if rel == '' or rel.endswith('/'):
        rel += 'index.html'
    if not SAFE_PATH.fullmatch(rel) or '..' in rel.split('/'):
        return None
    return rel if (ROOT / rel).is_file() else None


def collect():
    files = git('ls-files', '*.html').splitlines() or [
        p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*.html') if '.git' not in p.parts]
    pages, excluded = [], []
    for rel in sorted(files):
        if not (ROOT / rel).is_file():
            continue
        if not any(re.fullmatch(p, rel) for p in INCLUDE):
            why = next((w for p, w in REASONS if re.fullmatch(p, rel)), '허용 목록 밖')
            excluded.append((rel, why))
            continue
        if not SAFE_PATH.fullmatch(rel):
            excluded.append((rel, 'URL에 그대로 쓸 수 없는 문자가 있는 파일 이름'))
            continue
        meta = head_meta(ROOT / rel)
        if meta.noindex:
            excluded.append((rel, 'noindex 메타'))
            continue
        if meta.canonical and meta.canonical != url_of(rel):
            # 다른 주소를 대표 주소로 지정한 페이지는 검색엔진이 중복으로 본다 → 대표 주소 쪽만 싣는다
            excluded.append((rel, f'canonical이 다른 주소({meta.canonical})'))
            continue
        pages.append(rel)
    return pages, excluded


def build_sitemap(pages):
    # 첫 화면 → 목록 페이지 → 나머지(경로순)
    def key(rel):
        return (rel != 'index.html', not rel.endswith('index.html'), rel)
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for rel in sorted(pages, key=key):
        out.append(f'  <url><loc>{escape(url_of(rel))}</loc><lastmod>{lastmod(rel)}</lastmod></url>')
    out.append('</urlset>')
    return '\n'.join(out) + '\n'


def clean(s):
    # XML 1.0에서 허용되지 않는 제어 문자 제거
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', s if isinstance(s, str) else '').strip()


def pub_date(day, rel):
    """feed.json의 날짜를 쓰되, 그날 첫 커밋 시각이 있으면 그 시각(같은 날 글의 순서 유지)."""
    added = git('log', '--diff-filter=A', '--format=%cI', '--', rel).splitlines()
    if added:
        t = datetime.fromisoformat(added[-1]).astimezone(KST)
        if t.date() == day.date():
            return t
    return day.replace(hour=9)


def build_rss(public):
    """public: sitemap에 실린 상대 경로 집합. 반환 (rss 문자열 또는 None, 넣은 수, 뺀 항목 목록)."""
    try:
        feed = json.loads((ROOT / 'update' / 'feed.json').read_text(encoding='utf-8'))
    except (OSError, ValueError) as e:
        return None, 0, [f'feed.json을 읽지 못함({e.__class__.__name__}) — 기존 rss.xml 유지']
    if not isinstance(feed, list):
        return None, 0, ['feed.json 최상위가 배열이 아님 — 기존 rss.xml 유지']
    items, skipped = [], []
    for it in feed:
        if not isinstance(it, dict):
            skipped.append(f'{str(it)[:30]}: 항목 형식 오류')
            continue
        name = clean(it.get('no')) or clean(it.get('url')) or '?'
        rel = rel_of(clean(it.get('url')))
        if not rel or not re.fullmatch(RSS_ITEM, rel) or rel not in public:
            skipped.append(f'{name}: 공개된 update 글 주소가 아님')
            continue
        title, summary = clean(it.get('title')), clean(it.get('summary'))
        try:
            day = datetime.strptime(clean(it.get('date')), '%Y-%m-%d').replace(tzinfo=KST)
        except ValueError:
            skipped.append(f'{name}: 날짜 형식 오류')
            continue
        if not title and not summary:
            skipped.append(f'{name}: 제목·요약 없음')
            continue
        items.append((pub_date(day, rel), it, url_of(rel), title, summary))
    items.sort(key=lambda x: (x[0], x[2]), reverse=True)
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
           '<channel>',
           '  <title>DI 동향 · Update for Data Integrity | DI Forum</title>',
           f'  <link>{SITE}/update/</link>',
           f'  <atom:link href="{SITE}/rss.xml" rel="self" type="application/rss+xml"/>',
           '  <description>데이터 완전성(Data Integrity) 규제 동향과 실무 해설 — DI Forum, Operated by i&amp;CP</description>',
           '  <language>ko</language>']
    for t, it, url, title, summary in items:
        out.append('  <item>')
        if title:
            out.append(f'    <title>{escape(title)}</title>')
        out += [f'    <link>{escape(url)}</link>',
                f'    <guid isPermaLink="true">{escape(url)}</guid>',
                f'    <pubDate>{format_datetime(t)}</pubDate>']
        if clean(it.get('category')):
            out.append(f'    <category>{escape(clean(it.get("category")))}</category>')
        if summary:
            out.append(f'    <description>{escape(summary)}</description>')
        out.append('  </item>')
    out += ['</channel>', '</rss>']
    return '\n'.join(out) + '\n', len(items), skipped


def write(name, text):
    p = ROOT / name
    old = p.read_text(encoding='utf-8') if p.is_file() else None
    if old != text:
        p.write_text(text, encoding='utf-8', newline='\n')
    return old != text


def check():
    errs = []
    pages, _ = collect()
    public = {url_of(r) for r in pages}
    ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    sm = ET.parse(ROOT / 'sitemap.xml').getroot()
    locs = [u.findtext('s:loc', namespaces=ns) for u in sm.findall('s:url', ns)]
    for u in sm.findall('s:url', ns):
        lm = u.findtext('s:lastmod', namespaces=ns) or ''
        try:
            datetime.fromisoformat(lm)
        except ValueError:
            errs.append(f'sitemap lastmod 형식 오류: {lm}')
    if len(locs) != len(set(locs)):
        errs.append('sitemap에 중복 URL')
    for loc in locs:
        rel = rel_of(loc)
        if not rel:
            errs.append(f'sitemap URL에 해당 파일 없음: {loc}')
            continue
        meta = head_meta(ROOT / rel)
        if meta.noindex:
            errs.append(f'sitemap에 noindex 페이지: {loc}')
        if meta.canonical and meta.canonical != loc:
            errs.append(f'canonical 불일치: {loc} ↔ {meta.canonical}')
    rss = ET.parse(ROOT / 'rss.xml').getroot()
    ch = rss.find('channel')
    if rss.tag != 'rss' or ch is None:
        errs.append('rss.xml 구조 오류')
        items = []
    else:
        items = ch.findall('item')
    for it in items:
        link = (it.findtext('link') or '').strip()
        if not ((it.findtext('title') or '').strip() or (it.findtext('description') or '').strip()):
            errs.append(f'rss item에 title·description 모두 없음: {link}')
        try:
            datetime.strptime((it.findtext('pubDate') or '').strip(), '%a, %d %b %Y %H:%M:%S %z')
        except ValueError:
            errs.append(f'rss pubDate 형식 오류: {link}')
        if link not in public or not re.fullmatch(RSS_ITEM, rel_of(link) or ''):
            errs.append(f'rss 링크가 공개된 update 글이 아님: {link}')
    robots = (ROOT / 'robots.txt').read_text(encoding='utf-8') if (ROOT / 'robots.txt').is_file() else ''
    for line in ('User-agent: *', 'Allow: /', f'Sitemap: {SITE}/sitemap.xml'):
        if line not in robots.splitlines():
            errs.append(f'robots.txt에 "{line}" 없음')
    print(f'검증: sitemap URL {len(locs)}개, rss 글 {len(items)}건, 오류 {len(errs)}건')
    for e in errs:
        print('  ✕', e)
    return not errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true', help='생성 결과만 검증')
    a = ap.parse_args()
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if a.check:
        sys.exit(0 if check() else 1)
    pages, excluded = collect()
    c1 = write('sitemap.xml', build_sitemap(pages))
    print(f'sitemap.xml: URL {len(pages)}개{" (갱신)" if c1 else " (변경 없음)"}')
    rss, n, skipped = build_rss(set(pages))
    if rss is None:
        print('rss.xml: 갱신하지 않음')
    else:
        c2 = write('rss.xml', rss)
        print(f'rss.xml: 글 {n}건{" (갱신)" if c2 else " (변경 없음)"}')
    print(f'sitemap에서 뺀 페이지 {len(excluded)}개:')
    for rel, why in excluded:
        print(f'  - {rel}: {why}')
    if skipped:
        print(f'rss에서 뺀 항목 {len(skipped)}개:')
        for s in skipped:
            print(f'  - {s}')


if __name__ == '__main__':
    main()
