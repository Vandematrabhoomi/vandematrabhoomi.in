#!/usr/bin/env python3
"""
Vande Matrabhoomi -- Shareable Article Page Generator
======================================================
Reads published Live Desk articles from the public Apps Script endpoint
and writes a static HTML page per article under a/<id>.html, with real
Open Graph meta tags baked in so pasting the link on WhatsApp/Facebook/
Twitter shows that article's own headline, summary, and photo instead of
the generic site preview.

Runs from GitHub Actions (see .github/workflows/update-news.yml), not from
Apps Script -- Apps Script's UrlFetchApp calls are blocked by a Google
OAuth consent restriction on the account this project uses, so pushing
files to GitHub has to happen from here instead.
"""

import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_news  # reuse its Wikipedia/Commons image search (find_image)

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
ARTICLE_DIR = os.path.join(BASE_DIR, "a")
STORIES_URL = "https://script.google.com/macros/s/AKfycbw_UDz41q9C-qnNwkZ5YUnmliSr08i1daJSvvaPi7aXnaH6TQMK-iTwwfQAfAtEZt52/exec?type=story"
SITE_URL    = "https://vandematrabhoomi.in"


# Common Hindi function words (postpositions, pronouns, auxiliary verbs) to
# strip when turning a Hindi headline into a Wikipedia/Commons search query --
# there's no capitalization signal in Devanagari to spot named entities with,
# so filtering stopwords is the only way to surface the words that matter.
HI_STOPWORDS = {
    'के', 'की', 'का', 'को', 'में', 'से', 'पर', 'और', 'या', 'कि', 'भी', 'ही', 'तो',
    'है', 'हैं', 'था', 'थी', 'थे', 'हो', 'होगा', 'होगी', 'होंगे', 'रहा', 'रही', 'रहे',
    'यह', 'वह', 'ये', 'वे', 'इस', 'उस', 'इन', 'उन', 'अपने', 'अपनी', 'अपना',
    'एक', 'दो', 'सभी', 'कुछ', 'जो', 'जब', 'तक', 'साथ', 'बाद', 'लिए', 'द्वारा', 'नहीं',
    'ने', 'गया', 'गई', 'गए', 'हुआ', 'हुई', 'हुए', 'किया', 'करते', 'करने', 'कर', 'करना',
}
HI_WORD_RE = re.compile(r'[ऀ-ॿ]+')


def hi_candidate_phrases(text, limit=8):
    """Turn a Hindi headline into short candidate search phrases, longest
    (most specific) first: consecutive-word bigrams before single words --
    a long query built from every keyword at once matches nothing (Wikipedia
    search dilutes to zero results), but short phrases like "दिल्ली हाईकोर्ट"
    or "ध्रुव राठी" reliably match a real page."""
    words = [w for w in HI_WORD_RE.findall(text or "") if w not in HI_STOPWORDS and len(w) > 1]
    bigrams = [f'{a} {b}' for a, b in zip(words, words[1:])]
    singles = [w for w in words if len(w) > 2]
    seen, out = set(), []
    for phrase in bigrams + singles:
        if phrase not in seen:
            seen.add(phrase)
            out.append(phrase)
    return out[:limit]


def hi_wiki_pageimage(title, size=1200):
    """Same validation rules as fetch_news.wiki_thumb, but against the Hindi
    Wikipedia (hi.wikipedia.org) instead of the English one."""
    try:
        t = urllib.parse.quote(title.strip()[:120])
        url = (f'https://hi.wikipedia.org/w/api.php?action=query'
               f'&titles={t}&prop=pageimages&pithumbsize={size}&format=json')
        req = urllib.request.Request(url, headers=fetch_news.WIKI_UA)
        with fetch_news.urlopen_retry(req, timeout=10) as r:
            data = json.loads(r.read())
        pages = data.get('query', {}).get('pages', {})
        page = next(iter(pages.values()), {})
        if page.get('pageid') == -1:
            return ''
        thumb = page.get('thumbnail', {})
        src, w, h = thumb.get('source', ''), thumb.get('width', 0), thumb.get('height', 0)
        if not src or not fetch_news.IMG_EXT.search(src) or fetch_news.LOGO_RE.search(src):
            return ''
        if w < 400 or h < 250:
            return ''
        if h > 0 and w > 0 and (h / w) > 1.4:
            return ''
        return src
    except Exception:
        return ''


def hi_wiki_search(query, size=1200):
    """Full-text search on Hindi Wikipedia for a page matching `query`, then
    return that page's lead photo. Works on natural Hindi phrases -- MediaWiki's
    search ranks by relevance, so it doesn't need pre-extracted named entities."""
    if not query:
        return ''
    try:
        q = urllib.parse.quote(query[:150])
        url = (f'https://hi.wikipedia.org/w/api.php?action=query&list=search'
               f'&srsearch={q}&srlimit=3&format=json')
        req = urllib.request.Request(url, headers=fetch_news.WIKI_UA)
        with fetch_news.urlopen_retry(req, timeout=10) as r:
            data = json.loads(r.read())
        for res in data.get('query', {}).get('search', []):
            title = res.get('title', '')
            img = hi_wiki_pageimage(title, size) if title else ''
            if img:
                return img
    except Exception:
        pass
    return ''


def find_related_image(story):
    """Look up a photo related to the headline via Wikipedia/Commons (same
    logic fetch_news.py uses for the main news feed). Live Desk articles
    have no attached photo of their own (see KNOWN LIMITATION note in
    subscriber-sheet-script.gs), so without this every share-link preview
    would just show the site logo instead of something relevant."""
    headline = story.get("hl") or ""
    lang = story.get("lang") or "hi"

    try:
        url, _credit = fetch_news.find_image(headline, story.get("cat") or "", 0)
        if url:
            return url
    except Exception:
        pass

    if lang == "hi":
        for phrase in hi_candidate_phrases(headline):
            try:
                url = hi_wiki_search(phrase)
                if url:
                    return url
            except Exception:
                pass
        try:
            url = fetch_news.commons_search(' '.join(hi_candidate_phrases(headline, limit=6)))
            if url:
                return url
        except Exception:
            pass

    return ""


def esc(s):
    return html.escape(s or "", quote=True)


def build_html(story):
    lang = "en" if story.get("lang") == "en" else "hi"
    story_id = story["id"]
    url = f"{SITE_URL}/a/{story_id}.html"
    image = story.get("mediaUrl") or f"{SITE_URL}/assets/vande-logo.png"
    desc = re.sub(r"\s+", " ", (story.get("sum") or story.get("body") or "")).strip()[:200]
    body_paragraphs = [p.strip() for p in re.split(r"\n\n+", story.get("body") or "") if p.strip()]
    body_html = "\n".join(f"<p>{esc(p)}</p>" for p in body_paragraphs)
    back_label = "← वंदे मातृभूमि™ पर और पढ़ें" if lang == "hi" else "← Read more on Vande Matrabhoomi™"
    headline = story.get("hl") or ""
    category = story.get("cat") or ""

    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(headline)} — Vande Matrabhoomi™</title>
<meta name="description" content="{esc(desc)}">
<meta property="og:type" content="article">
<meta property="og:title" content="{esc(headline)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:image" content="{esc(image)}">
<meta property="og:url" content="{esc(url)}">
<meta property="og:site_name" content="Vande Matrabhoomi™">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="{SITE_URL}/assets/vande-logo.png">
<style>
body{{font-family:Georgia,"Noto Serif Devanagari",serif;max-width:720px;margin:0 auto;padding:24px;color:#1a0000;line-height:1.7;background:#fffdf9;}}
.masthead{{display:flex;align-items:center;gap:10px;margin-bottom:24px;border-bottom:3px solid #cc0000;padding-bottom:14px;}}
.masthead img{{height:40px;}}
.masthead span{{font-weight:700;font-size:20px;color:#cc0000;}}
.cat{{display:inline-block;background:#fff0f0;color:#cc0000;font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;padding:3px 10px;border-radius:3px;margin-bottom:10px;}}
h1{{font-size:28px;margin:6px 0 8px;color:#1a0000;}}
.hero{{width:100%;border-radius:6px;margin-bottom:20px;}}
p{{margin:0 0 16px;font-size:17px;}}
.back{{display:inline-block;margin-top:28px;color:#cc0000;font-weight:600;text-decoration:none;}}
</style>
</head>
<body>
<div class="masthead"><img src="{SITE_URL}/assets/vande-logo.png" alt=""><span>वंदे मातृभूमि™ — Vande Matrabhoomi™</span></div>
<div class="cat">{esc(category)}</div>
<h1>{esc(headline)}</h1>
{f'<img class="hero" src="{esc(image)}" alt="">' if story.get("mediaUrl") else ''}
{body_html}
<a class="back" href="{SITE_URL}/#opinion">{esc(back_label)}</a>
</body>
</html>
"""


def run():
    os.makedirs(ARTICLE_DIR, exist_ok=True)
    req = urllib.request.Request(STORIES_URL, headers={"User-Agent": "VandeMatrabhoomi/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        stories = json.loads(resp.read().decode("utf-8"))

    written = 0
    for story in stories:
        path = os.path.join(ARTICLE_DIR, f"{story['id']}.html")
        if os.path.exists(path):
            continue
        if not story.get("mediaUrl"):
            related = find_related_image(story)
            if related:
                story = dict(story, mediaUrl=related)
        with open(path, "w", encoding="utf-8") as f:
            f.write(build_html(story))
        written += 1
        print(f"  wrote a/{story['id']}.html — {story.get('hl', '')[:60]}")

    print(f"Done — {written} new article page(s), {len(stories)} total stories checked.")


if __name__ == "__main__":
    run()
