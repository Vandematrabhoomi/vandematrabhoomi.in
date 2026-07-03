#!/usr/bin/env python3
"""
Vande Matrabhoomi -- AI News Generator (FREE via Groq)
=======================================================
SETUP (one time):
  1. pip install groq
  2. console.groq.com -> API Keys -> Create Key
  3. Paste key below
  4. Double-click to run, then refresh browser
"""

from groq import Groq
from concurrent.futures import ThreadPoolExecutor, as_completed
import json, os, sys, re, time, urllib.request, urllib.parse
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

API_KEY = os.environ.get("GROQ_API_KEY", "")
MODEL   = "meta-llama/llama-4-scout-17b-16e-instruct"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMG_DIR  = os.path.join(BASE_DIR, "assets", "images")
os.makedirs(IMG_DIR, exist_ok=True)

WP_UA = {"User-Agent": "VandeMatrabhoomi/2.0 (https://github.com/vm-news; news@vm.in)"}

LOGO_WORDS = ('logo', 'emblem', 'seal', 'coat_of_arms', 'icon',
              'insignia', 'badge', 'crest', 'flag_of', 'symbol')

def _is_photo(url):
    s = url.lower().split("?")[0]
    if not any(s.endswith(x) for x in ('.jpg', '.jpeg', '.png', '.webp')):
        return False
    if '.svg' in s:
        return False
    fname = s.rsplit("/", 1)[-1]
    return not any(kw in fname for kw in LOGO_WORDS)


# ── Get proper thumbnail URL via Wikipedia pageimages API ────────────────────
# This is the ONLY reliable way — never manually construct /Npx- thumbnail URLs
# because Wikimedia now enforces allowed sizes (only API-returned sizes are valid).
def wiki_thumb(article_title, size=640):
    """
    Returns a valid thumbnail URL for the Wikipedia article's lead image,
    at the nearest allowed size to `size`. Returns "" on failure.
    """
    try:
        t   = urllib.parse.quote(article_title.strip()[:120])
        url = (f"https://en.wikipedia.org/w/api.php?action=query"
               f"&titles={t}&prop=pageimages&pithumbsize={size}&format=json")
        req = urllib.request.Request(url, headers=WP_UA)
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.loads(r.read())
        pages = d.get("query", {}).get("pages", {})
        page  = next(iter(pages.values()), {})
        if page.get("pageid") == -1:        # article doesn't exist
            return ""
        src = page.get("thumbnail", {}).get("source", "")
        return src if (src and _is_photo(src)) else ""
    except Exception:
        return ""


# ── Wikimedia Commons keyword search — returns API-provided thumburl ──────────
def commons_thumb(keywords):
    """Search Commons for a real photo. Returns API-provided thumburl (always valid)."""
    try:
        q   = urllib.parse.quote(keywords[:80])
        url = (
            "https://commons.wikimedia.org/w/api.php"
            "?action=query&generator=search"
            f"&gsrsearch=filetype%3Abitmap+{q}"
            "&gsrnamespace=6&gsrlimit=20"
            "&prop=imageinfo&iiprop=url%7Cmime%7Csize"
            "&iiurlwidth=640&format=json"
        )
        req = urllib.request.Request(url, headers=WP_UA)
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        pages = data.get("query", {}).get("pages", {})
        for page in sorted(pages.values(), key=lambda p: p.get("index", 9999)):
            ii   = (page.get("imageinfo") or [{}])[0]
            mime = ii.get("mime", "")
            size = ii.get("size", 0)
            src  = ii.get("thumburl") or ""     # API-provided, always valid size
            if src and "svg" not in mime and size > 60_000 and _is_photo(src):
                return src
    except Exception:
        pass
    return ""


# ── Per-category fallback Wikipedia articles (cycled so each story differs) ──
FALLBACK_ARTICLES = {
    "breaking":      ["India Gate", "Parliament of India", "Mumbai", "Red Fort", "Kerala", "New Delhi"],
    "top":           ["India Gate", "Mumbai", "Red Fort", "Kerala", "Taj Mahal", "New Delhi"],
    "national":      ["India Gate", "Red Fort", "Kerala", "Mumbai", "Ganges", "Taj Mahal"],
    "politics":      ["Parliament of India", "India Gate", "New Delhi", "Red Fort", "Mumbai", "Kerala"],
    "world":         ["India Gate", "Taj Mahal", "Mumbai", "Parliament of India", "Red Fort", "New Delhi"],
    "sports":        ["Cricket", "India Gate", "Wankhede Stadium", "Red Fort", "Kerala", "Mumbai"],
    "business":      ["Bombay Stock Exchange", "Mumbai", "India Gate", "New Delhi", "Kerala", "Red Fort"],
    "entertainment": ["Mumbai", "India Gate", "Taj Mahal", "Kerala", "Red Fort", "New Delhi"],
    "lifestyle":     ["Kerala", "Taj Mahal", "India Gate", "Mumbai", "Ganges", "Red Fort"],
}


def get_remote_url(story, cat, idx):
    """
    Find the best image URL for a story (does not download).
    Priority: wiki_subject1 → wiki_subject2 → commons keywords → fallback article pool.
    All URLs are API-provided thumbnails (valid Wikimedia sizes).
    """
    for subj in [story.get("wiki_subject1",""), story.get("wiki_subject2","")]:
        if subj:
            u = wiki_thumb(subj)
            if u:
                return u, f"Wikipedia – {subj} (CC BY-SA)"

    kw = story.get("photo_keywords","")
    if kw:
        u = commons_thumb(kw)
        if u:
            return u, "Wikimedia Commons (CC BY-SA)"

    # Fallback: cycle through category-appropriate Wikipedia articles
    pool    = FALLBACK_ARTICLES.get(cat, FALLBACK_ARTICLES["top"])
    article = pool[idx % len(pool)]
    u = wiki_thumb(article)
    return (u, f"Wikipedia – {article} (CC BY-SA)") if u else ("", "")


def download_url(remote, filepath):
    """Download remote URL → local file. Returns True on success."""
    try:
        req = urllib.request.Request(remote, headers={
            **WP_UA,
            "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
        })
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read()
        if len(data) < 8_000:
            return False
        with open(filepath, "wb") as f:
            f.write(data)
        return True
    except Exception:
        return False


def add_images(stories, cat):
    """
    Fetch + download images for all stories in parallel.
    Saves files to assets/images/cat_N.jpg and stores relative paths.
    """
    # Phase 1: find remote URLs in parallel
    remote_map = {}
    credit_map = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(get_remote_url, s, cat, i): i for i, s in enumerate(stories)}
        for f in as_completed(futs):
            i = futs[f]
            remote_map[i], credit_map[i] = f.result()

    # Phase 2: download in parallel
    def download_one(i):
        remote = remote_map.get(i, "")
        if not remote:
            return i, "", ""
        ext    = ".jpg" if any(remote.lower().endswith(x) for x in ('.jpg','.jpeg')) else ".png"
        fname  = f"{cat}_{i}{ext}"
        local  = os.path.join(IMG_DIR, fname)
        ok     = download_url(remote, local)
        if ok:
            return i, f"assets/images/{fname}", credit_map.get(i, "Wikimedia (CC BY-SA)")
        return i, "", ""

    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(download_one, i): i for i in range(len(stories))}
        for f in as_completed(futs):
            i, local_path, credit = f.result()
            stories[i]["image_url"]    = local_path
            stories[i]["image_credit"] = credit

    return stories


# ── Categories ───────────────────────────────────────────────────────────────
CATEGORIES = {
    "breaking":      ("5 urgent breaking news headlines from India — short punchy", 5),
    "top":           ("most important news from India today", 2),
    "national":      ("national India — society, governance, infrastructure", 2),
    "politics":      ("Indian politics — Parliament, parties, government decisions", 2),
    "world":         ("world news relevant to India — diplomacy, global events", 2),
    "sports":        ("Indian sports — cricket, hockey, kabaddi, athletics", 2),
    "business":      ("Indian economy — markets, RBI, startups, trade, inflation", 2),
    "entertainment": ("Indian entertainment — Bollywood, OTT, music, celebrities", 2),
    "lifestyle":     ("Indian lifestyle — health, food, travel, wellness, culture", 2),
}


def generate(client, cat, topic, n):
    today = datetime.now().strftime("%Y-%m-%d")
    if cat == "breaking":
        prompt = f"""You are a journalist for Vande Matrabhoomi, an Indian news portal. Today is {today}.

Write {n} urgent breaking news headlines from India. title_en/title_hi ≤12 words each. summary_en/summary_hi 1 sentence each. article_en/article_hi same as summary (1 sentence).

For EACH story provide:
wiki_subject1 — specific named PERSON or PLACE with a Wikipedia photo (e.g. "Narendra Modi", "Mumbai", "Red Fort")
wiki_subject2 — different named person or place as backup
photo_keywords — 4-6 words describing what the photo visually shows

Return ONLY valid JSON:
{{"stories":[{{"title_en":"...","title_hi":"...","summary_en":"...","summary_hi":"...","article_en":"...","article_hi":"...","date":"{today}","wiki_subject1":"...","wiki_subject2":"...","photo_keywords":"..."}}]}}"""
    else:
        prompt = f"""You are a senior journalist for Vande Matrabhoomi, an Indian news portal. Today is {today}.

Write {n} news stories about: {topic}.

For EACH story you MUST provide ALL of these fields:

title_en / title_hi — the headline in English and Hindi

summary_en / summary_hi — ONE sentence (used on news cards as a teaser)

article_en — a full newspaper article in English with EXACTLY 3 paragraphs separated by \\n\\n.
  Each paragraph: 5-7 sentences, rich detail, journalist quality. Total: 280-350 words minimum.
  Do NOT use bullet points or headings — flowing prose only.

article_hi — the same full article written in Hindi. EXACTLY 3 paragraphs separated by \\n\\n.
  Each paragraph: 5-7 sentences. Total: 250-320 words minimum. Flowing prose only.

wiki_subject1 — specific named PERSON or PLACE in the story with a real Wikipedia photograph.
  GOOD: "Narendra Modi", "Virat Kohli", "Mumbai", "Red Fort", "Neeraj Chopra"
  BAD: "Indian Railways", "Ministry of Finance", "Government of India"

wiki_subject2 — a different named person or place as backup

photo_keywords — 4-6 English words describing what the ideal news photo visually shows

Return ONLY valid JSON:
{{
  "stories": [
    {{
      "title_en": "...",
      "title_hi": "...",
      "summary_en": "One sentence teaser.",
      "summary_hi": "एक वाक्य में सारांश।",
      "article_en": "Full paragraph 1...\\n\\nFull paragraph 2...\\n\\nFull paragraph 3...",
      "article_hi": "पूरा अनुच्छेद 1...\\n\\nपूरा अनुच्छेद 2...\\n\\nपूरा अनुच्छेद 3...",
      "date": "{today}",
      "wiki_subject1": "...",
      "wiki_subject2": "...",
      "photo_keywords": "..."
    }}
  ]
}}"""

    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.5,
        max_tokens=8192,
    )
    stories = json.loads(resp.choices[0].message.content).get("stories", [])
    for s in stories:
        if not s.get("date"):
            s["date"] = today
    return stories


def main():
    if API_KEY == "YOUR_KEY_HERE":
        print("\n  ERROR: Paste your Groq key into the script.\n")
        return

    client = Groq(api_key=API_KEY)
    print(f"\n  Vande Matrabhoomi — News Generator")
    print(f"  {datetime.now().strftime('%d %B %Y, %H:%M')}\n")

    # Wipe old images so disk usage stays constant (~8 MB)
    for f in os.listdir(IMG_DIR):
        try:
            os.remove(os.path.join(IMG_DIR, f))
        except Exception:
            pass
    print("  Old images cleared.\n")

    all_news, total = {}, 0

    for cat, (topic, n) in CATEGORIES.items():
        print(f"  [{cat:12}]", end=" ", flush=True)
        stories = []
        for attempt in range(3):
            try:
                stories = generate(client, cat, topic, n)
                break
            except Exception as e:
                if attempt < 2:
                    print(f"retry...", end=" ", flush=True)
                    time.sleep(8)
                else:
                    print(f"FAILED — {e}")
        if stories:
            try:
                print(f"downloading images...", end=" ", flush=True)
                stories = add_images(stories, cat)
                hits    = sum(1 for s in stories if s.get("image_url"))
                all_news[cat] = stories
                total += len(stories)
                print(f"OK  ({hits}/{len(stories)} images)")
            except Exception as e:
                print(f"image error — {e}")
                all_news[cat] = stories
                total += len(stories)
        else:
            all_news[cat] = []
        time.sleep(5)

    if not total:
        print("\n  No stories generated. Check API key at console.groq.com\n")
        return

    out = {"generated": datetime.now().isoformat(), "categories": all_news}
    js  = "/* Vande Matrabhoomi — AI News */\n"
    js += "window.VM_NEWS = " + json.dumps(out, ensure_ascii=False, indent=2) + ";\n"

    with open(os.path.join(BASE_DIR, "news-data.js"), "w", encoding="utf-8") as f:
        f.write(js)

    print(f"\n  Done! {total} stories saved. Images in assets/images/")
    print(f"  Refresh the browser.\n")


if __name__ == "__main__":
    main()
