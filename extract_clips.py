#!/usr/bin/env python3
"""
Extract the first ~3 seconds of every reel video as a muted, 480p MP4
for the dashboard's "visual hook" preview.

Reads videoUrls from data/<handle>_posts.json files, pipes through ffmpeg,
writes to clips/<shortcode>.mp4. videoUrls from Apify expire within hours,
so run this soon after scraping.
"""
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
CLIPS = ROOT / "clips"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
CLIP_SECONDS = 3


def extract(post):
    sc = post.get("shortCode")
    url = post.get("videoUrl")
    if not sc or not url:
        return (sc or "?", "skip", "no shortcode/videoUrl")
    out = CLIPS / f"{sc}.mp4"
    if out.exists() and out.stat().st_size > 0:
        return (sc, "have", "cached")
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-user_agent", UA,
        "-i", url,
        "-t", str(CLIP_SECONDS),
        "-vf", "scale=-2:480",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "30",
        "-an",
        "-movflags", "+faststart",
        str(out),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=60)
        if r.returncode == 0 and out.exists() and out.stat().st_size > 0:
            return (sc, "ok", f"{out.stat().st_size//1024}KB")
        else:
            if out.exists():
                out.unlink()
            return (sc, "fail", (r.stderr.decode("utf-8", "ignore")[:140] or "non-zero exit"))
    except subprocess.TimeoutExpired:
        return (sc, "timeout", "60s")
    except Exception as e:
        return (sc, "error", str(e)[:140])


def main():
    CLIPS.mkdir(parents=True, exist_ok=True)
    # collect all posts across creators
    posts = []
    for f in sorted(DATA.glob("*_posts.json")):
        with open(f) as fp:
            data = json.load(fp)
        for p in data.get("items", []):
            posts.append(p)
    print(f"queued {len(posts)} reels for clip extraction")

    counts = {"ok": 0, "have": 0, "fail": 0, "skip": 0, "timeout": 0, "error": 0}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for sc, status, info in ex.map(extract, posts):
            counts[status] = counts.get(status, 0) + 1
            if status in ("fail", "timeout", "error"):
                print(f"  ✗ {sc}: {status} — {info}")
            elif status == "ok":
                print(f"  ✓ {sc}: {info}")

    print("\nsummary:", counts)
    total_size = sum(p.stat().st_size for p in CLIPS.glob("*.mp4"))
    print(f"clips/ total: {total_size/1024/1024:.1f} MB")


if __name__ == "__main__":
    main()
