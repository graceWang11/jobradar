STAGE 1 – JOBRADAR PROJECT PLAN
Local workflow → GitHub-ready → Daily junior/graduate tech job aggregation
Target: Adelaide & Melbourne | International-friendly (485 visa holders)

PROJECT GOAL

Build a local workflow that:

Collects fresh junior/graduate software development, architecture, and early programming program jobs

Across Adelaide and Melbourne

From major job websites including:
LinkedIn, Seek, Jora, GradConnection, Prosple, and other relevant platforms

Considers visa friendliness for international workers (485 visa holders)

Aggregates all jobs into a single clean table

Sends the results to inbox (email)

Can later be pushed to GitHub for public use and automation

Stage 1 focuses on a stable, achievable MVP:
Local execution → structured data → email output.

STAGE 1 SUCCESS CRITERIA

When Stage 1 is complete:

Running one command will:

Collect fresh jobs

Filter for:

Graduate / Junior / Entry-level roles

Software development / architecture / programming programs

Melbourne & Adelaide

Analyse visa friendliness (485 likelihood scoring)

Remove duplicates

Output a clean table (CSV + HTML)

Send the result to inbox

OVERALL APPROACH (HYBRID MODEL)

We use a hybrid data collection strategy to balance:

stability

legal safety

automation

coverage

Data sources divided into two categories:

A) Structured-friendly sources (direct collection)

Prosple

GradConnection

Jora

Indeed (optional)

APS Jobs / grad portals (future)

These will be accessed via:

public search pages

stable listing extraction

RSS feeds where available

B) Alert-based sources (no scraping)

LinkedIn

Seek

Approach:

user creates job alerts

alerts sent via email

workflow parses email content

extracts job links and summaries

This avoids fragile scraping and login restrictions.

FILTER DEFINITIONS

Locations:

Adelaide

Melbourne

Optional: Hybrid / Remote (Australia-based)

Job levels:

graduate

junior

entry

associate

early career

Role categories:

Software Engineering:

software engineer

software developer

backend

frontend

full stack

devops (optional)

Architecture:

junior architect

associate architect

solutions architect (junior)

technical architect (associate)

Programs:

graduate program

tech graduate

rotation program

internship-to-perm

VISA (485) FRIENDLINESS SCORING

Since most job ads do not explicitly mention 485 visa:

A heuristic scoring model will be applied.

Score range: 0–5

Negative indicators:

"Australian citizen required"

"PR only"

"Baseline clearance"

"NV1 clearance"

"Must be citizen"

Moderate negatives:

"Must have permanent work rights"

Positive indicators:

"Visa sponsorship available"

"International candidates welcome"

"Temporary visa accepted"

"Work rights in Australia"

Each job will include:

visa_score

visa_reason (explainable text)

NORMALISED DATA MODEL

Every job collected becomes a unified object:

Fields:

source

title

company

location

url

date_posted / date_found

summary/snippet

tags:

Graduate

Junior

Program

SWE

Architecture

visa_score

visa_reason

hash_id (for dedupe)

DEDUPLICATION LOGIC

Remove duplicates using:

canonical job URL
OR

similarity match:
(title + company + location)

State tracking stored locally via:

state.json
OR

sqlite database

This prevents re-sending the same job daily.

OUTPUT FORMAT

Files generated:

output/jobs.csv

output/jobs.html

output/jobs.md (for GitHub later)

Columns:

Date found

Source

Title

Company

Location

Link

Summary

Tags

Visa score

Visa reason

EMAIL DELIVERY

Email contains:

subject:
"Daily Junior/Grad Jobs – Adelaide & Melbourne – YYYY-MM-DD"

embedded HTML table

CSV attachment

Delivery via:

Gmail SMTP or Outlook SMTP

Credentials stored locally in:
.env file

LOCAL EXECUTION

Command:

python -m jobradar run

Optional flags:

--since 24h
--city melbourne
--dry-run

Scheduling:

macOS:

cron / launchd

Windows:

Task Scheduler

GITHUB-READY ARCHITECTURE

Planned repo structure:

/connectors
prosple.py
gradconnection.py
jora.py
email_alerts.py

/core
normalize.py
dedupe.py
visa_scoring.py
output.py
email_sender.py

/config.yaml
/.env.example
/README.md
/output/
/data/

STAGE 1 BUILD ORDER

Milestone sequence:

Repo skeleton + config + unified data model

Prosple connector

GradConnection connector

Jora connector

Deduplication engine

Visa scoring engine

CSV + HTML output

Email sender

LinkedIn/Seek via alert ingestion

FUTURE STAGES (NOT PART OF STAGE 1)

GitHub Actions daily automation

Public dashboard

Community fork support

ML-based job classification

Advanced visa prediction

Company career portal connectors

Notification via Slack/Telegram

REALITY CONSTRAINTS

LinkedIn and Seek scraping avoided for stability and ToS compliance

Visa filtering cannot be exact → likelihood model used

Early career architecture roles are rarer → expect lower volume

Job freshness depends on source update frequency

FINAL OBJECTIVE

Create a sustainable, reusable job aggregation workflow that:

helps international graduates (485 visa holders)

centralises early career tech opportunities

reduces manual job searching

can be shared publicly via GitHub

can run daily with minimal maintenance
