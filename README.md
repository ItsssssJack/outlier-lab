# Outlier Lab

Track the top reels across the creators in your niche. Search creators with a live admin UI, set your own refresh schedule, and get a private weekly dashboard with spoken-hook transcripts and 3-second autoplay hook clips. **No AI API key needed** — Apify handles all the AI on their backend.

![Pipeline](https://img.shields.io/badge/pipeline-Admin_UI_→_Apify_→_GitHub_Actions_→_Vercel-orange)
![Cost](https://img.shields.io/badge/cost-~$2--15_per_month-green)
![No AI key](https://img.shields.io/badge/AI_key_required-no-brightgreen)

## What it does

Every refresh interval (you pick the frequency), a GitHub Action runs and:

1. **Apify scrapes** the last 28 days of reels for your tracked creator list
2. **Pulls spoken transcripts** for any new reels (only pays for new ones — saves ~75% vs naive setup)
3. **ffmpeg extracts** the first 3 seconds of each new reel as a muted autoplay clip
4. **Regenerates** a static HTML dashboard with outlier scores, sortable table, filter-by-creator chips, click-row-to-play hook clip
5. **Pushes** the changes back to the repo → **Vercel auto-deploys**

## What you need

| Thing | Why | Cost |
|---|---|---|
| **Apify account** | Does the scraping + transcripts | Free $5/mo credit; ~$10–15/mo for 15 creators weekly |
| **GitHub account** | Hosts the code + runs the cron | Free |
| **Vercel account** | Hosts the dashboard | Free (Hobby tier) |
| **Python 3.10+** | To run the local admin UI | Free |
| **ffmpeg** | For the 3-sec hook clips | Free |

**You do NOT need:** an OpenAI key, Claude key, or any other AI subscription. Apify handles all transcription internally.

## Setup (one time, ~10 minutes)

### 1. Get the code

Click **Use this template** at the top of this repo, then clone your new fork:
```bash
git clone https://github.com/YOUR-USERNAME/outlier-lab.git
cd outlier-lab
```

### 2. Install ffmpeg

macOS:
```bash
brew install ffmpeg
```

### 3. Launch the admin

```bash
python3 serve.py
```

Your browser opens at `http://localhost:4747/admin`. From there:

- **Paste your Apify token** ([get one free](https://console.apify.com/settings/api))
- **Search and add creators** — type a name or handle, see live results with profile photos + follower counts, click "Add" on the ones you want to track
- **Pick a schedule** — daily, every 3 days, weekly Sunday, weekly Monday, monthly, or manual-only
- **Click "Run refresh now"** to generate the dashboard for the first time
- **Click "Open dashboard ↗"** when it's done

### 4. Push to GitHub + add the secret

```bash
git add config.json .github/workflows/refresh.yml
git commit -m "My setup"
git push

# Make APIFY_TOKEN available to GitHub Actions:
gh secret set APIFY_TOKEN < .env
# (or via UI: repo → Settings → Secrets → Actions → New repository secret)
```

### 5. Deploy to Vercel

```bash
vercel
```

Vercel auto-deploys on every push from now on, including the scheduled refresh from GitHub Actions.

### 6. Done

The cron you picked in the admin UI fires automatically. You can also trigger manually any time: repo → Actions → Weekly refresh → Run workflow.

## How the cost stays low

The pipeline uses a **two-pass** approach:
- **Pass 1** (cheap, no transcripts): refreshes plays/likes/comments stats for all reels in your 28-day window
- **Pass 2** (transcripts, expensive add-on): only for reels you haven't transcribed yet

That keeps transcript spend roughly flat at "new reels per interval × seconds × $0.041/min" rather than re-paying for the whole archive every refresh.

## Managing your creator list

Run `python3 serve.py` anytime. The admin remembers everything — search and add new ones, remove old ones, change the schedule. Then `git add config.json && git commit && git push` to propagate the changes to GitHub Actions.

If you prefer the terminal, `python3 configure.py` also works.

## Architecture

```
┌─────────────────────┐   you click "Run"  ┌──────────────────┐
│   localhost admin   │ ──────────────────▶│   Apify scrape   │
│  (python3 serve.py) │◀──── reels + ─────│  + transcripts   │
└──────────┬──────────┘    profile data    └──────────────────┘
           │
           │ refresh.py (download new thumbs + clips, run build.py)
           ▼
┌─────────────────────┐    git push        ┌──────────────────┐
│ index.html + data + │ ──────────────────▶│  Vercel deploy   │
│ thumbs/ + clips/    │                    │  (auto-trigger)  │
└─────────────────────┘                    └──────────────────┘
           ▲                                          │
           │                                          ▼
┌─────────────────────┐                    ┌──────────────────┐
│   GitHub Actions    │                    │  Your dashboard  │
│ (your cron, weekly  │                    │   .vercel.app    │
│ or whatever you pick)│                   └──────────────────┘
└─────────────────────┘
```

## Files

| File | What it is |
|---|---|
| **`serve.py`** | Local admin server — run this to get the UI |
| **`admin.html`** | The admin UI (single page, no framework, served by serve.py) |
| `configure.py` | CLI alternative to the web admin (same job) |
| `refresh.py` | The pipeline orchestrator |
| `build.py` | Renders `index.html` from scraped data |
| `extract_clips.py` | ffmpeg helper for the 3-sec hook clips |
| `config.json` | Your creator list (committed; managed by the admin) |
| `.env` | Your Apify token (gitignored) |
| `.github/workflows/refresh.yml` | The cron job — edited by the admin's schedule picker |
| `vercel.json` | Vercel hosting config |
| `data/`, `thumbs/`, `clips/` | Generated content (committed so Vercel can serve it) |
| `index.html` | The dashboard (welcome page until first refresh runs) |

## Troubleshooting

**A scheduled run failed.** Check repo → Actions → click the failed run → look at "Run refresh pipeline" step. Most common cause:
- `APIFY_TOKEN` not set as a secret → fix via `gh secret set APIFY_TOKEN < .env`
- A handle in your config went private mid-week → remove via admin

**Apify returned 502.** Transient. `refresh.py` retries with exponential backoff automatically. If it still fails, trigger the workflow again.

**The dashboard shows old data.** Check that GitHub Actions actually committed + pushed (look at the latest commit on the repo). If yes, Vercel should auto-redeploy within seconds.

**My profile pictures aren't loading on the admin search results.** Instagram CDN sometimes blocks hotlinked images. The dashboard fixes this by downloading them locally on each refresh; the admin search shows them live so they occasionally 403. Click "Add" anyway — the lookup-and-store happens server-side.

## License

MIT — do what you want with this. Credit appreciated but not required.
