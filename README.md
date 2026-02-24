# JobRadar

Local → GitHub-ready workflow for aggregating junior/graduate tech jobs in Adelaide & Melbourne, with visa-friendly analysis and automated email delivery.

## What it does

- Collects fresh junior/graduate tech job listings from **Prosple**, **GradConnection**, **Jora**, and **email alerts** (LinkedIn, Seek)
- Filters for **Graduate / Junior / Entry-level** software development, architecture, and program roles
- Targets **Adelaide** and **Melbourne**
- Scores each job for **485 visa friendliness** using heuristic keyword analysis
- Deduplicates listings across runs
- Outputs a clean **CSV + HTML table**
- Sends a **daily email summary** to your inbox

## Quick Start

```bash
# 1. Clone and install
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env with your email credentials

# 3. Run
python -m jobradar run

# Options
python -m jobradar run --city melbourne
python -m jobradar run --since 24h
python -m jobradar run --dry-run
```

## Setup

### Email credentials (Gmail)
1. Enable 2FA on your Google account
2. Generate an **App Password**: Google Account → Security → App Passwords
3. Add to `.env`:
   ```
   EMAIL_ADDRESS=you@gmail.com
   EMAIL_PASSWORD=your_16_char_app_password
   EMAIL_TO=you@gmail.com
   ```

### LinkedIn / Seek alert ingestion (optional)
1. Set up job alerts on LinkedIn and Seek (email delivery)
2. Configure IMAP in `.env`
3. Enable `email_alerts` in `config.yaml`

## Project Structure

```
jobradar/
├── connectors/
│   ├── prosple.py        # Prosple graduate jobs
│   ├── gradconnection.py # GradConnection graduate jobs
│   ├── jora.py           # Jora job aggregator
│   └── email_alerts.py   # LinkedIn/Seek email alert parser
├── core/
│   ├── models.py         # JobListing data model
│   ├── normalize.py      # Data normalization & tagging
│   ├── dedupe.py         # Deduplication engine
│   ├── visa_scoring.py   # 485 visa friendliness scoring
│   ├── output.py         # CSV / HTML / Markdown output
│   └── email_sender.py   # SMTP email delivery
config.yaml               # Keywords, locations, filters
.env                      # Credentials (never committed)
output/                   # Generated output files
data/                     # State tracking (dedupe)
```

## Scheduling (daily automation)

**macOS (cron):**
```bash
crontab -e
# Add: run at 7am daily
0 7 * * * /usr/bin/python3 -m jobradar run
```

**Windows Task Scheduler:** Create a basic task running `python -m jobradar run`

## Visa Scoring (485)

Each job receives a score from 0–5:

| Score | Meaning |
|-------|---------|
| 0–1   | Likely citizen/PR only |
| 2–3   | Neutral / unknown |
| 4–5   | Visa-friendly signals detected |

Positive signals: "sponsorship available", "international candidates welcome", "temporary visa accepted"
Negative signals: "citizen required", "PR only", "clearance required", "NV1"

## Stage 2 (future)

- GitHub Actions daily automation
- Public dashboard
- ML-based job ranking
- Slack / Telegram alerts
