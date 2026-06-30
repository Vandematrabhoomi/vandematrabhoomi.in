#!/usr/bin/env python3
"""
Vande Matrabhoomi — Prasar Bharati RSS Fetcher
===============================================
Source: Akashvani News / newsonair.gov.in (Official Prasar Bharati)

Articles are text-only; images are sourced from Wikipedia / Wikimedia Commons
using keywords extracted from each headline.

Run manually:  python fetch_news.py
Scheduled:     6x daily via Windows Task Scheduler (setup_auto_update.bat)
"""

import xml.etree.ElementTree as ET
import urllib.request
import urllib.parse
import json
import re
import sys
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from email.utils import parsedate_to_datetime

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

RSS_UA = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/125.0.0.0 Safari/537.36'
    )
}
WIKI_UA = {
    'User-Agent': 'VandeMatrabhoomi/2.0 (https://vm-news.in; news@vm.in)'
}

ATOM    = 'http://www.w3.org/2005/Atom'
CONTENT = 'http://purl.org/rss/1.0/modules/content/'
DC      = 'http://purl.org/dc/elements/1.1/'

SOURCE  = 'Prasar Bharati'
PB_BASE = 'https://newsonair.gov.in/category'

CATEGORY_FEEDS = {
    'top':           [f'{PB_BASE}/national/feed/', f'{PB_BASE}/international/feed/'],
    'breaking':      [f'{PB_BASE}/national/feed/'],
    'national':      [f'{PB_BASE}/national/feed/'],
    'politics':      [f'{PB_BASE}/national/feed/'],
    'world':         [f'{PB_BASE}/international/feed/'],
    'sports':        [f'{PB_BASE}/sports/feed/'],
    'business':      [f'{PB_BASE}/business/feed/'],
    'entertainment': [f'{PB_BASE}/entertainment/feed/'],
    'lifestyle':     [f'{PB_BASE}/health/feed/'],
}

MAX_PER_CAT   = 12
IMG_WORKERS   = 16

# Words to skip when building Wikipedia search terms
STOPWORDS = {
    'a','an','the','and','or','but','in','on','at','to','for','of','with',
    'by','from','as','is','was','are','were','be','been','have','has','had',
    'that','this','its','it','into','over','after','before','during','under',
    'about','amid','across','against','between','through','within','without',
    'per','new','says','said','calls','urges','launches','begins','ends',
    'india','indian','govt','government','minister','ministry','officials',
}

LOGO_RE = re.compile(
    r'(logo|emblem|seal|coat_of_arms|icon|insignia|badge|crest|flag_of|symbol)',
    re.I
)
IMG_EXT = re.compile(r'\.(jpg|jpeg|png|webp)(\?|$)', re.I)


# ── Wikipedia image helpers ───────────────────────────────────────────────────

def wiki_thumb(subject, size=1200):
    """Return a thumbnail URL for a Wikipedia article's lead photo, or ''.
    Validates dimensions and aspect ratio to reject portraits and tiny images."""
    try:
        t   = urllib.parse.quote(subject.strip()[:120])
        url = (f'https://en.wikipedia.org/w/api.php?action=query'
               f'&titles={t}&prop=pageimages&pithumbsize={size}&format=json')
        req = urllib.request.Request(url, headers=WIKI_UA)
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        pages = data.get('query', {}).get('pages', {})
        page  = next(iter(pages.values()), {})
        if page.get('pageid') == -1:
            return ''
        thumb = page.get('thumbnail', {})
        src   = thumb.get('source', '')
        w     = thumb.get('width',  0)
        h     = thumb.get('height', 0)
        if not src or not IMG_EXT.search(src) or LOGO_RE.search(src):
            return ''
        # Reject tiny images and portrait-heavy crops
        if w < 400 or h < 250:
            return ''
        if h > 0 and w > 0 and (h / w) > 1.4:  # reject anything more portrait than 3:4.3
            return ''
        return src
    except Exception:
        pass
    return ''


def commons_search(keywords, size=1000):
    """Search Wikimedia Commons for a relevant photo; return thumburl or ''.
    Validates dimensions and aspect ratio."""
    try:
        q   = urllib.parse.quote(keywords[:80])
        url = (
            'https://commons.wikimedia.org/w/api.php'
            '?action=query&generator=search'
            f'&gsrsearch=filetype%3Abitmap+{q}'
            '&gsrnamespace=6&gsrlimit=20'
            '&prop=imageinfo&iiprop=url%7Cmime%7Csize%7Cdimensions'
            f'&iiurlwidth={size}&format=json'
        )
        req = urllib.request.Request(url, headers=WIKI_UA)
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.loads(r.read())
        pages = data.get('query', {}).get('pages', {})
        for page in sorted(pages.values(), key=lambda p: p.get('index', 9999)):
            ii   = (page.get('imageinfo') or [{}])[0]
            mime = ii.get('mime', '')
            sz   = ii.get('size', 0)
            src  = ii.get('thumburl', '')
            w    = ii.get('width',  0)
            h    = ii.get('height', 0)
            if not src or 'svg' in mime or sz < 50_000 or LOGO_RE.search(src):
                continue
            # Reject small originals and portrait-heavy images
            if w < 600 or h < 380:
                continue
            if h > 0 and w > 0 and (h / w) > 1.4:
                continue
            return src
    except Exception:
        pass
    return ''


def extract_subjects(title):
    """
    Pull capitalised multi-word phrases from title as candidate Wikipedia subjects.
    Returns a list of strings, longest first.
    """
    # Named entity heuristic: runs of Title-Cased words that aren't stopwords
    words  = re.findall(r"[A-Z][a-zA-Z''-]+(?:\s+[A-Z][a-zA-Z''-]+)*", title)
    unique = []
    seen   = set()
    for w in words:
        w2 = w.strip()
        if w2.lower() not in STOPWORDS and w2 not in seen and len(w2) > 2:
            seen.add(w2)
            unique.append(w2)
    # longest first
    return sorted(unique, key=len, reverse=True)


def find_image(title, cat, fallback_idx):
    """Try Wikipedia subjects → Commons keyword search.
    Returns empty if no relevant image found — never uses unrelated placeholders."""
    subjects = extract_subjects(title)

    # 1. Wikipedia page image for named entities in the headline
    for subj in subjects[:3]:
        url = wiki_thumb(subj)
        if url:
            return url, f'Wikipedia – {subj} (CC BY-SA)'

    # 2. Commons keyword search using non-stopword words from the headline
    keywords = ' '.join(w for w in title.split()
                        if w.lower() not in STOPWORDS and len(w) > 3)[:80]
    if keywords:
        url = commons_search(keywords)
        if url:
            return url, 'Wikimedia Commons (CC BY-SA)'

    # No relevant image found — return empty rather than an unrelated stock photo
    return '', ''


# ── RSS parsing ───────────────────────────────────────────────────────────────

def parse_date(s):
    s = (s or '').strip()
    if not s:
        return datetime.now().isoformat()
    try:
        return parsedate_to_datetime(s).isoformat()
    except Exception:
        try:
            return datetime.fromisoformat(s[:19]).isoformat()
        except Exception:
            return s


def strip_tags(html):
    html = html or ''
    html = re.sub(r'<(script|style)[^>]*>.*?</(script|style)>', ' ', html,
                  flags=re.S | re.I)
    text = re.sub(r'<[^>]+>', ' ', html)
    for ent, rep in (('&nbsp;', ' '), ('&amp;', '&'), ('&lt;', '<'),
                     ('&gt;', '>'), ('&quot;', '"'), ('&#39;', "'")):
        text = text.replace(ent, rep)
    return re.sub(r'\s+', ' ', text).strip()


def fetch_rss(url, max_items=20):
    try:
        req = urllib.request.Request(url, headers=RSS_UA)
        with urllib.request.urlopen(req, timeout=22) as r:
            raw = r.read()
    except Exception as e:
        print(f'    ✗ {url}: {e}')
        return []

    text = raw.decode('utf-8', errors='ignore').lstrip('﻿')
    text = re.sub(r'&(?!(amp|lt|gt|quot|apos|#\d+|#x[\da-fA-F]+);)', '&amp;', text)

    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        print(f'    ✗ XML error: {e}')
        return []

    items_el = root.findall('.//item') or root.findall(f'.//{{{ATOM}}}entry')
    results  = []

    for el in items_el[:max_items]:
        title = strip_tags(
            el.findtext('title') or el.findtext(f'{{{ATOM}}}title') or ''
        )
        if not title:
            continue

        link = (el.findtext('link') or '').strip()
        if not link:
            a = el.find(f'{{{ATOM}}}link')
            if a is not None:
                link = a.get('href', '')

        pub     = (el.findtext('pubDate') or
                   el.findtext(f'{{{ATOM}}}published') or
                   el.findtext(f'{{{DC}}}date') or '')
        pub_iso = parse_date(pub)

        desc_raw = el.findtext('description') or el.findtext(f'{{{ATOM}}}summary') or ''
        summary  = strip_tags(desc_raw)[:400].strip()

        full_raw = (el.findtext(f'{{{CONTENT}}}encoded') or
                    el.findtext(f'{{{ATOM}}}content') or '')
        article  = strip_tags(full_raw or desc_raw).strip()
        if len(article) > 3500:
            article = article[:3500].rsplit(' ', 1)[0] + ' …'
        if not article:
            article = summary
        if not summary:
            summary = article[:200]

        results.append({
            'title':        title,
            'summary':      summary,
            'article':      article,
            'date':         pub_iso[:10],
            'pubDate':      pub_iso,
            'link':         link,
            'image_url':    '',
            'image_credit': '',
            'source':       SOURCE,
        })

    return results


# ── Politics keyword ranker ───────────────────────────────────────────────────

POLITICS_RE = re.compile(
    r'\b(parliament|lok sabha|rajya sabha|minister|cabinet|party|election|'
    r'bjp|congress|modi|rahul|gandhi|government|policy|bill|amendment|'
    r'constitution|vote|chief minister|\bcm\b|\bpm\b|prime minister)\b',
    re.I
)


def dedup_and_sort(items, prefer_political=False):
    if prefer_political:
        pol   = [i for i in items if POLITICS_RE.search(i['title'] + ' ' + i['summary'])]
        other = [i for i in items if not POLITICS_RE.search(i['title'] + ' ' + i['summary'])]
        items = pol + other

    seen, deduped = set(), []
    for item in items:
        k = item['title'].lower()[:60]
        if k and k not in seen:
            seen.add(k)
            deduped.append(item)

    # Images first, then sort by date descending within each group
    with_img    = [i for i in deduped if i.get('image_url')]
    without_img = [i for i in deduped if not i.get('image_url')]
    with_img.sort(key=lambda x: x.get('pubDate', ''), reverse=True)
    without_img.sort(key=lambda x: x.get('pubDate', ''), reverse=True)
    return (with_img + without_img)[:MAX_PER_CAT]


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    print(f'\n  Vande Matrabhoomi — Prasar Bharati Fetcher')
    print(f'  Source: newsonair.gov.in  (Akashvani News)')
    print(f'  [{datetime.now().strftime("%d %B %Y, %H:%M")}]\n')

    # Step 1: fetch all unique RSS feeds
    unique_urls = set(u for urls in CATEGORY_FEEDS.values() for u in urls)
    raw_by_url  = {}

    print('  Fetching RSS feeds...')
    for url in unique_urls:
        items = fetch_rss(url, max_items=20)
        raw_by_url[url] = items
        cat_name = url.rstrip('/').split('/')[-2]
        print(f'    ✓ {cat_name}: {len(items)} articles')

    # Step 2: collect all unique articles for image lookup
    link_to_item = {}
    for items in raw_by_url.values():
        for item in items:
            if item['title'] not in link_to_item:
                link_to_item[item['title']] = item

    unique_items = list(link_to_item.values())
    total = len(unique_items)

    if not total:
        print('\n  ERROR: No articles fetched. Check internet connection.\n')
        sys.exit(1)

    print(f'\n  Finding Wikipedia images for {total} articles...')

    def get_img_for(idx_item):
        idx, item = idx_item
        img, credit = find_image(item['title'], 'top', idx)
        return idx, img, credit

    with ThreadPoolExecutor(max_workers=IMG_WORKERS) as ex:
        futs = {ex.submit(get_img_for, (i, item)): i
                for i, item in enumerate(unique_items)}
        done = 0
        for fut in as_completed(futs):
            i, img, credit = fut.result()
            if img:
                unique_items[i]['image_url']    = img
                unique_items[i]['image_credit'] = credit
            done += 1
            if done % 10 == 0:
                print(f'    {done}/{total} images resolved...')

    img_count = sum(1 for i in unique_items if i.get('image_url'))
    print(f'  Got {img_count}/{total} images\n')

    # Step 3: build per-category buckets
    all_news = {}
    for cat, feed_urls in CATEGORY_FEEDS.items():
        combined = []
        for url in feed_urls:
            combined.extend(raw_by_url.get(url, []))

        processed = dedup_and_sort(combined, prefer_political=(cat == 'politics'))
        all_news[cat] = processed
        img_n = sum(1 for i in processed if i.get('image_url'))
        print(f'  [{cat:12}] {len(processed):2} stories  ({img_n} with images)')

    # Step 4: write news-data.js  (images-without-match are left empty — no unrelated placeholders)
    out = {
        'generated': datetime.now().isoformat(),
        'en': all_news,
        'hi': all_news,
    }

    js = ('/* Vande Matrabhoomi — Prasar Bharati Live Feed (auto-generated) */\n'
          'window.VM_NEWS = ' + json.dumps(out, ensure_ascii=False, indent=2) + ';\n')

    path = os.path.join(BASE_DIR, 'news-data.js')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(js)

    total_stories = sum(len(v) for v in all_news.values())
    ts = datetime.now().strftime('%d %B %Y %H:%M')
    print(f'\n  Done — {total_stories} stories → news-data.js  [{ts}]')
    print(f'  Refresh the browser to see updates.\n')


if __name__ == '__main__':
    run()
