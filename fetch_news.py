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
PB_CAT  = 'https://newsonair.gov.in/?cat={id}&feed=rss2'

# English RSS feeds
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

# Hindi RSS feeds — Prasar Bharati's Hindi news categories
CATEGORY_FEEDS_HI = {
    'top':           [PB_CAT.format(id=358), PB_CAT.format(id=309)],
    'breaking':      [PB_CAT.format(id=358)],
    'national':      [PB_CAT.format(id=358)],
    'politics':      [PB_CAT.format(id=358)],
    'world':         [PB_CAT.format(id=309)],
    'sports':        [PB_CAT.format(id=362)],
    'business':      [PB_CAT.format(id=360)],
    'entertainment': [PB_CAT.format(id=21410)],
    'lifestyle':     [PB_CAT.format(id=21349)],
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


def fetch_pb_images(post_ids):
    """Given a list of Prasar Bharati post IDs, return a dict {post_id: image_url}
    by batch-querying the WordPress REST API for featured media."""
    if not post_ids:
        return {}

    result = {}
    # Batch posts endpoint to get featured_media IDs (max 100 per call)
    BATCH = 100
    media_map = {}  # post_id → featured_media_id

    for i in range(0, len(post_ids), BATCH):
        chunk = post_ids[i:i + BATCH]
        ids_param = ','.join(str(p) for p in chunk)
        url = (f'https://newsonair.gov.in/wp-json/wp/v2/posts'
               f'?include={ids_param}&per_page={BATCH}'
               f'&_fields=id,featured_media')
        try:
            req = urllib.request.Request(url, headers=RSS_UA)
            with urllib.request.urlopen(req, timeout=15) as r:
                posts = json.loads(r.read())
            for p in posts:
                fm = p.get('featured_media', 0)
                if fm and fm != 0:
                    media_map[p['id']] = fm
        except Exception as e:
            print(f'    ✗ WP posts batch: {e}')

    if not media_map:
        return {}

    # Batch media endpoint to get image URLs
    media_ids = list(set(media_map.values()))
    media_url_map = {}  # media_id → image_url

    for i in range(0, len(media_ids), BATCH):
        chunk = media_ids[i:i + BATCH]
        ids_param = ','.join(str(m) for m in chunk)
        url = (f'https://newsonair.gov.in/wp-json/wp/v2/media'
               f'?include={ids_param}&per_page={BATCH}'
               f'&_fields=id,source_url,media_details')
        try:
            req = urllib.request.Request(url, headers=RSS_UA)
            with urllib.request.urlopen(req, timeout=15) as r:
                media_list = json.loads(r.read())
            for m in media_list:
                src = m.get('source_url', '')
                md  = m.get('media_details', {})
                w   = md.get('width', 0)
                h   = md.get('height', 0)
                if not src or not IMG_EXT.search(src) or LOGO_RE.search(src):
                    continue
                if w < 400 or h < 250:
                    continue
                if h > 0 and w > 0 and (h / w) > 1.6:
                    continue
                media_url_map[m['id']] = src
        except Exception as e:
            print(f'    ✗ WP media batch: {e}')

    # Map post_id → image_url
    for post_id, media_id in media_map.items():
        if media_id in media_url_map:
            result[post_id] = media_url_map[media_id]

    return result


def find_image(title, cat, fallback_idx, pb_image=''):
    """Try Prasar Bharati featured image → Wikipedia subjects → Commons keyword search.
    Returns empty if no relevant image found — never uses unrelated placeholders."""

    # 0. Prasar Bharati's own featured image (exact match, authoritative)
    if pb_image:
        return pb_image, 'Prasar Bharati / Akashvani News'

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

        # Extract WordPress post ID from <guid> (format: ?p=12345)
        guid = el.findtext('guid') or ''
        m_pid = re.search(r'[?&]p=(\d+)', guid)
        post_id = int(m_pid.group(1)) if m_pid else 0

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
            'post_id':      post_id,
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

    def fetch_feeds(feeds_dict, label='EN'):
        """Fetch all unique RSS URLs in feeds_dict; return {url: [items]}."""
        unique_urls = set(u for urls in feeds_dict.values() for u in urls)
        raw_by_url  = {}
        print(f'  Fetching {label} RSS feeds...')
        for url in unique_urls:
            items = fetch_rss(url, max_items=20)
            raw_by_url[url] = items
            slug = url.rstrip('/').split('/')[-1] if 'category' in url else url.split('cat=')[-1].split('&')[0]
            print(f'    ✓ {slug}: {len(items)} articles')
        return raw_by_url

    def resolve_images(items_list, label='EN'):
        """Given a flat list of unique items, fetch PB images then fall back to Wikipedia/Commons."""
        total = len(items_list)
        if not total:
            return
        post_ids = [i['post_id'] for i in items_list if i.get('post_id')]
        print(f'  Fetching PB featured images for {len(post_ids)} {label} posts...')
        pb_map = fetch_pb_images(post_ids)
        print(f'  PB images: {sum(1 for p in post_ids if p in pb_map)}/{len(post_ids)}')
        print(f'  Wikipedia/Commons fallback for remaining {label} articles...')

        def _get(idx_item):
            idx, item = idx_item
            pb_img = pb_map.get(item.get('post_id', 0), '')
            img, credit = find_image(item['title'], '', idx, pb_image=pb_img)
            return idx, img, credit

        with ThreadPoolExecutor(max_workers=IMG_WORKERS) as ex:
            futs = {ex.submit(_get, (i, item)): i for i, item in enumerate(items_list)}
            done = 0
            for fut in as_completed(futs):
                i, img, credit = fut.result()
                if img:
                    items_list[i]['image_url']    = img
                    items_list[i]['image_credit'] = credit
                done += 1
                if done % 10 == 0:
                    print(f'    {done}/{total} images resolved...')
        # strip internal field
        for item in items_list:
            item.pop('post_id', None)
        got = sum(1 for i in items_list if i.get('image_url'))
        print(f'  Got {got}/{total} images\n')

    def build_cat_news(feeds_dict, raw_by_url, label='EN'):
        result = {}
        for cat, feed_urls in feeds_dict.items():
            combined = []
            for url in feed_urls:
                combined.extend(raw_by_url.get(url, []))
            processed = dedup_and_sort(combined, prefer_political=(cat == 'politics'))
            result[cat] = processed
            img_n = sum(1 for i in processed if i.get('image_url'))
            print(f'  [{label}][{cat:12}] {len(processed):2} stories ({img_n} with images)')
        return result

    # ── Step 1: English feeds ──
    raw_en = fetch_feeds(CATEGORY_FEEDS, 'EN')
    title_to_item_en = {}
    for items in raw_en.values():
        for item in items:
            if item['title'] not in title_to_item_en:
                title_to_item_en[item['title']] = item
    unique_en = list(title_to_item_en.values())
    if not unique_en:
        print('\n  ERROR: No EN articles fetched. Check internet connection.\n')
        sys.exit(1)
    resolve_images(unique_en, 'EN')

    # ── Step 2: Hindi feeds ──
    raw_hi = fetch_feeds(CATEGORY_FEEDS_HI, 'HI')
    title_to_item_hi = {}
    for items in raw_hi.values():
        for item in items:
            if item['title'] not in title_to_item_hi:
                title_to_item_hi[item['title']] = item
    unique_hi = list(title_to_item_hi.values())
    if unique_hi:
        resolve_images(unique_hi, 'HI')
    else:
        print('  WARN: No Hindi articles fetched — Hindi will mirror English.\n')

    # ── Step 3: build per-category buckets ──
    all_news_en = build_cat_news(CATEGORY_FEEDS, raw_en, 'EN')
    all_news_hi = build_cat_news(CATEGORY_FEEDS_HI, raw_hi, 'HI') if unique_hi else all_news_en

    # Step 4: write news-data.js
    out = {
        'generated': datetime.now().isoformat(),
        'en': all_news_en,
        'hi': all_news_hi,
    }

    js = ('/* Vande Matrabhoomi — Prasar Bharati Live Feed (auto-generated) */\n'
          'window.VM_NEWS = ' + json.dumps(out, ensure_ascii=False, indent=2) + ';\n')

    path = os.path.join(BASE_DIR, 'news-data.js')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(js)

    total_stories = sum(len(v) for v in all_news_en.values())
    ts = datetime.now().strftime('%d %B %Y %H:%M')
    print(f'\n  Done — {total_stories} stories → news-data.js  [{ts}]')
    print(f'  Refresh the browser to see updates.\n')


if __name__ == '__main__':
    run()
