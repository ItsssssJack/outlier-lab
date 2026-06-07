# Outlier Lab

Track the top reels across the creators in your niche. Auto-refreshes every Sunday with new scrapes, spoken-hook transcripts, and 3-second autoplay clips. Pure data dashboard — no AI inference on your end, no servers to run, no maintenance.

![Architecture](https://img.shields.io/badge/pipeline-Apify_→_GitHub_Actions_→_Vercel-orange)
![Cost](https://img.shields.io/badge/cost-~$2--10_per_month-green)

## What it does

Every Sunday morning, a GitHub Action runs and:

1. Calls **Apify** to scrape the last 28 days of reels for your tracked creator list
2. Pulls **spoken-word transcripts** (not just captions) for any new reels — only pays for transcripts on reels it hasn't seen before
3. Uses **ffmpeg** to extract the first 3 seconds of each new reel as a muted autoplay clip
4. Regenerates a static HTML dashboard with everything: outlier scores, sortable table, filterable by creator, click any row to play the 3-sec hook clip inline
5. Pushes the changes back to the repo → **Vercel auto-deploys** your fresh dashboard

You wake up Sunday → fresh viral intel for your niche, no clicks required.

## What you need

| Thing | Why | Cost |
|---|---|---|
| **Apify account** | Does the Instagram scraping + transcripts | Free tier: $5/mo credit. Realistic: $10–15/mo for 15 creators weekly |
| **GitHub account** | Hosts the code + runs the weekly cron | Free (private repos included) |
| **Vercel account** | Hosts the dashboard | Free (Hobby tier) |
| **Python 3.10+** | To run the one-time setup wizard | Free |
| **ffmpeg** | To extract clip previews (also runs in GH Actions) | Free |

**No AI API key needed.** Apify does all the AI internally (Instagram parsing + speech-to-text on their backend). You just pay Apify.

## Setup (one time, ~10 minutes)

### 1. Get the code

Click **Use this template** at the top of this repo, or:
```bash
git clone https://github.com/YOUR-USERNAME/outlier-lab.git
cd outlier-lab
```

### 2. Install ffmpeg (if you don't have it)

macOS:
```bash
brew install ffmpeg
```

### 3. Run the setup wizard

```bash
python3 configure.py
```

It will:
- Ask for your Apify token (get one free at https://console.apify.com/settings/api)
- Let you add Instagram creators one at a time — each one verified live so you see the profile name, follower count, and verified badge before confirming
- Save your token to `.env` (gitignored) and your creator list to `config.json` (committed)

### 4. Test the pipeline locally

```bash
python3 refresh.py
open index.html
```

You should see your dashboard with the latest reels.

### 5. Push to GitHub + add the secret

```bash
git add config.json
git commit -m "Add my creator list"
git push

# Make APIFY_TOKEN available to GitHub Actions:
gh secret set APIFY_TOKEN < .env
# (or via UI: repo → Settings → Secrets → Actions → New repository secret)
```

### 6. Deploy to Vercel

```bash
vercel
```

Vercel will auto-deploy on every push from now on, including the weekly refresh from GitHub Actions.

### 7. That's it

The cron in `.github/workflows/refresh.yml` fires every Sunday at 7 AM ET (11:00 UTC). You can change the schedule by editing that cron string. You can also trigger a manual run anytime: repo → Actions → Weekly refresh → Run workflow.

## How the cost stays low

The pipeline uses a **two-pass** approach:
- **Pass 1** (cheap, no transcripts): refreshes plays/likes/comments stats for all reels in your 28-day window
- **Pass 2** (transcripts, expensive add-on): only for reels you don't already have transcripts for

That means transcript spend stays roughly flat at "new reels per week × seconds × $0.041/min" rather than re-paying every week for the whole archive.

## Managing your creator list later

Run `python3 configure.py` again anytime. It picks up your existing list and lets you add or remove creators interactively.

Or edit `config.json` directly — just keep the structure shown in `config.example.json`.

## Architecture

```
┌──────────────────┐    every Sunday   ┌──────────────────┐
│  GitHub Actions  │ ─────────────────▶│   Apify scrape   │
│   (cron + py)    │◀──── reels JSON ──│  + transcripts   │
└────────┬─────────┘                   └──────────────────┘
         │
         │ python3 refresh.py
         │  (download new thumbs + clips, run build.py)
         ▼
┌──────────────────┐    git push       ┌──────────────────┐
│   index.html +   │ ─────────────────▶│  Vercel deploy   │
│  data/clips/etc  │                   │  (auto-trigger)  │
└──────────────────┘                   └──────────────────┘
                                                │
                                                ▼
                                       ┌──────────────────┐
                                       │  Your dashboard  │
                                       │   .vercel.app    │
                                       └──────────────────┘
```

## Files

| File | What it is |
|---|---|
| `configure.py` | One-time setup wizard (token + creator list) |
| `refresh.py` | The weekly pipeline orchestrator |
| `build.py` | Renders `index.html` from scraped data |
| `extract_clips.py` | ffmpeg helper — first 3 sec of each reel as MP4 |
| `config.json` | Your creator list (committed; managed by `configure.py`) |
| `.env` | Your Apify token (gitignored; loaded by `refresh.py` locally) |
| `.github/workflows/refresh.yml` | The weekly cron + steps |
| `vercel.json` | Vercel hosting config (cache headers, etc.) |
| `data/` | Scraped JSON, one file per creator (committed) |
| `thumbs/` | Reel cover images (committed) |
| `clips/` | 3-second hook MP4s (committed) |
| `index.html` | The generated dashboard (committed) |

## Troubleshooting

**The Sunday workflow failed.** Check repo → Actions → click the failed run → look at the "Run refresh pipeline" step. The two most common failures:
- `APIFY_TOKEN` not set as a secret → fix via `gh secret set APIFY_TOKEN < .env`
- An Instagram handle in your config doesn't exist or is private → remove it via `python3 configure.py`

**Apify returned 502.** Transient. `refresh.py` retries with exponential backoff automatically. If it still fails, just trigger the workflow again.

**The dashboard is showing old data.** Check that GitHub Actions actually committed + pushed. If a creator's account went private mid-week, the pipeline skips them but the rest still update.

## License

MIT — do what you want with this. Credit appreciated but not required.
