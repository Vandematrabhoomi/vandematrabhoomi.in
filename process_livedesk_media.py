#!/usr/bin/env python3
"""
Vande Matrabhoomi -- Live Desk Photo Processor
================================================
The Live Desk publisher (index.html) can't upload photos directly: the Apps
Script backend for this project can't make any outbound call (DriveApp and
UrlFetchApp are both blocked by an account-level restriction -- see the
PHOTOS note in subscriber-sheet-script.gs). So instead, the browser resizes
each photo, splits it into base64 chunks, and stores those chunks as plain
sheet rows via a normal write (not an outbound call, so it isn't blocked).

This script runs from GitHub Actions (see .github/workflows/update-news.yml),
fetches any pending chunk sets via the script's public doGet(?type=media)
endpoint, reassembles each photo, writes it under assets/livedesk/<id>.jpg,
and calls back via doPost({type:'setMediaUrl'}) so the article's MediaUrl
column -- and the live site -- picks up the real photo.
"""

import base64
import json
import os
import sys
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR   = os.path.join(BASE_DIR, "assets", "livedesk")
SCRIPT_URL  = "https://script.google.com/macros/s/AKfycbw_UDz41q9C-qnNwkZ5YUnmliSr08i1daJSvvaPi7aXnaH6TQMK-iTwwfQAfAtEZt52/exec"
SITE_URL    = "https://vandematrabhoomi.in"
UA          = {"User-Agent": "VandeMatrabhoomi/1.0"}


def fetch_pending():
    req = urllib.request.Request(SCRIPT_URL + "?type=media", headers=UA)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def set_media_url(story_id, url):
    req = urllib.request.Request(
        SCRIPT_URL,
        data=json.dumps({"type": "setMediaUrl", "id": story_id, "url": url}).encode("utf-8"),
        headers=UA,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def run():
    os.makedirs(MEDIA_DIR, exist_ok=True)
    pending = fetch_pending()
    if not pending:
        print("No pending Live Desk photos.")
        return

    processed = 0
    for item in pending:
        story_id = item.get("id")
        chunks = item.get("chunks") or []
        if not story_id or not chunks:
            continue
        try:
            b64 = "".join(chunks)
            image_bytes = base64.b64decode(b64)
            filename = f"{story_id}.jpg"
            path = os.path.join(MEDIA_DIR, filename)
            with open(path, "wb") as f:
                f.write(image_bytes)

            url = f"{SITE_URL}/assets/livedesk/{filename}"
            result = set_media_url(story_id, url)
            if "error" in result:
                print(f"  setMediaUrl failed for {story_id}: {result}")
                continue

            processed += 1
            print(f"  wrote assets/livedesk/{filename} ({len(image_bytes)} bytes) and updated MediaUrl")
        except Exception as exc:
            print(f"  failed to process story {story_id}: {exc}")

    print(f"Done — {processed} photo(s) processed, {len(pending)} pending story(ies) checked.")


if __name__ == "__main__":
    run()
