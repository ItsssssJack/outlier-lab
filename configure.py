#!/usr/bin/env python3
"""
Outlier Lab — first-run setup wizard.

Walks you through:
  1. Saving your Apify API token (to .env, gitignored)
  2. Adding Instagram creators interactively — each handle is verified
     against Apify and you see their photo URL + follower count before
     confirming.

Output:
  - .env           your Apify token (don't commit)
  - config.json    the creator list (commit this — it's the input
                   GitHub Actions reads on every weekly refresh)
"""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config.json"
ENV_FILE = ROOT / ".env"


# ───────────────────────── helpers ─────────────────────────

def banner():
    print(r"""
╔══════════════════════════════════════════════════════════╗
║                                                          ║
║    OUTLIER LAB — First-Run Setup                         ║
║                                                          ║
║    Track top reels across the creators in your niche.    ║
║    Auto-refreshes every Sunday via GitHub Actions.       ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
""")


def step(n, total, title):
    bar = "─" * max(0, 50 - len(title))
    print(f"\n┌─ Step {n}/{total} — {title} {bar}")


def fmt_num(n):
    if n is None:
        return "—"
    n = int(n)
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 10_000:
        return f"{n/1_000:.0f}K"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


# ───────────────────────── step 1 ─────────────────────────

def get_apify_token():
    existing = os.environ.get("APIFY_TOKEN", "")
    if existing.startswith("apify_api_"):
        print(f"  Found APIFY_TOKEN already set in environment ({existing[:16]}…)")
        keep = input("  Use this token? [Y/n]: ").strip().lower()
        if keep in ("", "y", "yes"):
            return existing

    print("  Get your token at: https://console.apify.com/settings/api")
    print("  (Sign up free — they give you $5 credit/month to start)")
    token = input("  Paste your token (starts with 'apify_api_'): ").strip()
    if not token:
        print("  ! Empty input, aborting.")
        sys.exit(1)
    if not token.startswith("apify_api_"):
        print("  ⚠ That doesn't look like an Apify token. Tokens start with 'apify_api_'.")
        confirm = input("  Use it anyway? [y/N]: ").strip().lower()
        if confirm != "y":
            sys.exit(1)
    return token


def save_env(token):
    body = (
        "# Apify API token — used by refresh.py locally + by GitHub Actions\n"
        "# (via the APIFY_TOKEN repo secret). Never commit this file.\n"
        f"APIFY_TOKEN={token}\n"
    )
    ENV_FILE.write_text(body)
    print(f"  ✓ Saved to {ENV_FILE.name} (already gitignored)")


# ───────────────────────── step 2 ─────────────────────────

def fetch_profile(handle, token):
    """Verify a handle against Apify. Returns dict or None / error str."""
    handle = handle.lstrip("@").strip()
    actor_id = "shu8hvrXbJbY3Eb9W"  # apify/instagram-scraper
    url = (
        f"https://api.apify.com/v2/acts/{actor_id}"
        f"/run-sync-get-dataset-items?token={token}"
    )
    body = {
        "directUrls": [f"https://www.instagram.com/{handle}/"],
        "resultsType": "details",
        "resultsLimit": 1,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            items = json.load(r)
    except urllib.error.HTTPError as e:
        return f"api-error-{e.code}"
    except Exception as e:
        return f"error: {e}"

    if not items:
        return None
    item = items[0]
    if item.get("error") or not item.get("username"):
        return None
    return {
        "handle": item["username"],
        "name": item.get("fullName") or "",
        "followers": item.get("followersCount") or 0,
        "posts": item.get("postsCount") or 0,
        "verified": bool(item.get("verified")),
        "private": bool(item.get("private")),
        "profilePic": item.get("profilePicUrlHD") or item.get("profilePicUrl") or "",
    }


def load_existing():
    if CONFIG.exists():
        try:
            return json.loads(CONFIG.read_text())
        except json.JSONDecodeError:
            return {"creators": []}
    return {"creators": []}


def save_config(config):
    CONFIG.write_text(json.dumps(config, indent=2) + "\n")


def manage_creators(token):
    config = load_existing()
    creators = config.get("creators", [])

    print("""
  Add Instagram handles one at a time. Each one is verified via Apify
  before being added — you'll see the profile name, follower count,
  and verification badge.

  Commands:
    <handle>          add (verified first, then you confirm)
    list              show current creators
    remove <handle>   drop one
    done              finish and save
""")

    while True:
        prompt = f"  [{len(creators)} creator{'s' if len(creators) != 1 else ''}] > "
        try:
            cmd = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  (saving + exiting)")
            break

        if not cmd:
            continue

        if cmd in ("done", "exit", "quit", "q"):
            break

        if cmd in ("list", "ls"):
            if not creators:
                print("    (none yet — try adding one)")
            else:
                for i, c in enumerate(creators, 1):
                    badge = " ✓" if c.get("verified") else ""
                    print(f"    {i:2}. @{c['handle']:<25} {fmt_num(c['followers']):>6} · {c.get('name','')}{badge}")
            continue

        if cmd.startswith("remove "):
            target = cmd.split(" ", 1)[1].strip().lstrip("@")
            before = len(creators)
            creators = [c for c in creators if c["handle"] != target]
            if len(creators) < before:
                print(f"    ✓ removed @{target}")
                config["creators"] = creators
                save_config(config)
            else:
                print(f"    ? @{target} not in list")
            continue

        # otherwise treat as a handle to add
        handle = cmd.lstrip("@").strip()
        if not handle or " " in handle:
            print("    ? not a valid handle")
            continue
        if any(c["handle"] == handle for c in creators):
            print(f"    ? @{handle} already in list")
            continue

        print(f"    ↳ verifying @{handle}…", end=" ", flush=True)
        result = fetch_profile(handle, token)
        if result is None:
            print("✗ not found / empty / private")
            continue
        if isinstance(result, str):
            print(f"✗ {result}")
            continue
        if result["private"]:
            print(f"✗ private account (can't scrape)")
            continue

        followers = fmt_num(result["followers"])
        verified = " ✓" if result["verified"] else ""
        print(f"✓")
        print(f"        Name:      {result['name'] or '(no display name)'}")
        print(f"        Handle:    @{result['handle']}{verified}")
        print(f"        Followers: {followers}")
        print(f"        Posts:     {result['posts']}")
        if result.get("profilePic"):
            print(f"        Photo:     {result['profilePic'][:72]}…")

        keep = input("    Add this creator? [Y/n]: ").strip().lower()
        if keep in ("", "y", "yes"):
            creators.append(result)
            config["creators"] = creators
            save_config(config)
            print(f"    ✓ added (now {len(creators)} total)")
        else:
            print("    (skipped)")

    save_config(config)
    return creators


# ───────────────────────── main ─────────────────────────

def main():
    banner()

    step(1, 2, "Apify API token")
    token = get_apify_token()
    save_env(token)

    step(2, 2, "Manage creator list")
    creators = manage_creators(token)

    print("\n" + "═" * 60)
    print(f"  ✓ Setup complete. {len(creators)} creator(s) configured.")
    print("═" * 60)
    print("""
  Next steps:
    1. Test the pipeline locally:
         python3 refresh.py

    2. Commit your config:
         git add config.json
         git commit -m "Add my creator list"
         git push

    3. Add APIFY_TOKEN as a GitHub Actions secret:
         gh secret set APIFY_TOKEN < .env
         # (or via GitHub UI: Settings → Secrets → Actions → New)

    4. (Optional) Deploy the dashboard to Vercel:
         vercel
         # The site will auto-redeploy every Sunday after the refresh.

  Done. See README.md for more.
""")


if __name__ == "__main__":
    main()
