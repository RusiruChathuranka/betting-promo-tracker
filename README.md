# Sri Lanka Betting Promotion Tracker

Competitive promotion intelligence dashboard for betting platforms serving Sri Lanka.

## What it does
- Scrapes public promotion pages on a scheduled GitHub Actions run.
- Extracts and normalizes offer mechanics such as bonus %, max bonus, minimum deposit, wagering, odds and validity.
- Clusters similar promotions.
- Scores offers within each cluster and highlights the strongest comparable offer.
- Keeps historical snapshots so promotion changes can be detected.
- Publishes a static GitHub Pages dashboard.

## Setup
Add a repository secret named `FIRECRAWL_API_KEY`.

Then run **Actions → Scrape Promotions → Run workflow**.

The scraper uses public promotion pages only. Review each source's terms/robots requirements before adding a source.

## Data
- `data/promotions.json` — latest normalized offers
- `data/history.json` — historical snapshots
- `config/platforms.json` — source pages
- `config/scoring.json` — ranking weights

## Local test
```bash
pip install -r requirements.txt
export FIRECRAWL_API_KEY=your_key
python scraper/run.py
```
