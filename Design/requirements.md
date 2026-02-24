Requirements – JobRadar Project

Local → GitHub-ready workflow for aggregating junior/graduate tech jobs in Adelaide & Melbourne, with visa-friendly analysis and automated delivery.

This document defines the functional, technical, and operational requirements for Stage 1 of the JobRadar system.

1. Project Objective

Build a reliable local workflow that:

Collects fresh junior/graduate tech job listings

Focuses on:

Software development

Junior/associate architecture

Early-career programming programs

Targets:

Adelaide

Melbourne

Evaluates visa friendliness (485 likelihood)

Aggregates all jobs into one unified dataset

Outputs a clean table

Sends results to inbox

Can later be deployed to GitHub for automation and public sharing

2. Scope
Included in Stage 1

Local execution

Structured job aggregation

Email alert ingestion

Data normalization

Deduplication

Visa scoring (heuristic)

CSV + HTML outputs

Email delivery

Excluded from Stage 1

Web UI/dashboard

Machine learning classification

Full LinkedIn scraping

Public website deployment

Cloud infrastructure

3. Functional Requirements
3.1 Job Collection

System must collect job listings from:

Structured sources

Prosple

GradConnection

Jora

(optional later: Indeed, APS jobs)

Alert-based sources

LinkedIn job alerts (email)

Seek job alerts (email)

Collection must include:

job title

company

location

URL

summary snippet

posting date (if available)

3.2 Filtering Logic

Jobs must be filtered based on:

Location

Adelaide

Melbourne

optional: hybrid/remote (Australia-based)

Experience level

Graduate

Junior

Entry-level

Associate

Early career

Role categories

Software:

software engineer

software developer

backend

frontend

full stack

dev roles

Architecture:

junior architect

associate architect

solutions architect (junior)

Programs:

graduate programs

rotational programs

internship pathways

3.3 Data Normalization

All job sources must be converted into a unified schema.

Fields required:

source

title

company

location

url

date_found

summary

tags

visa_score

visa_reason

hash_id

3.4 Deduplication

System must remove duplicate job entries using:

canonical URL comparison OR

title + company + location similarity

System must maintain local state to prevent repeated alerts.

3.5 Visa Friendliness Analysis

System must compute a visa likelihood score using keyword heuristics.

Negative indicators:

citizen required

PR only

clearance required

Neutral indicators:

full working rights

Positive indicators:

sponsorship available

international candidates welcome

temporary visa accepted

Output:

visa_score (0–5)

visa_reason (text explanation)

3.6 Output Generation

System must generate:

CSV file

HTML table

optional Markdown export

Table must include:

date found

source

role title

company

location

link

summary

tags

visa score

visa reason

3.7 Email Delivery

System must:

send daily job summary to inbox

include:

HTML table in body

CSV attachment

Email must support:

Gmail SMTP

Outlook SMTP

3.8 Execution

System must be runnable locally via command:

python -m jobradar run

Optional flags:

--since 24h

--city melbourne

--dry-run

4. Technical Requirements
4.1 Programming Language

Primary:

Python 3.10+

4.2 Libraries

Required:

requests / httpx

BeautifulSoup / lxml

pandas

pydantic or dataclasses

smtplib

python-dotenv

schedule / cron integration

4.3 Configuration

System must use:

config.yaml:

keywords

locations

filters

.env:

email credentials

SMTP settings

4.4 Storage

Local persistence required:

Options:

sqlite
OR

JSON state file

Used for:

dedupe tracking

historical job storage

4.5 Architecture Structure

Expected modules:

/connectors
/core
/config
/output
/data

5. Non-Functional Requirements
5.1 Stability

System must:

avoid login scraping

use structured sources

rely on alert ingestion where needed

5.2 Maintainability

modular connectors

config-driven filtering

reusable components

5.3 Performance

System must:

complete run within minutes

handle hundreds of listings per run

avoid excessive requests

5.4 Compliance & Safety

System must:

respect platform ToS

avoid scraping behind authentication

implement rate limiting

5.5 Security

Credentials must:

never be hardcoded

be stored in .env

be excluded from GitHub commits

6. User Requirements

Target user:

international graduates

485 visa holders

early career tech job seekers

Melbourne / Adelaide based

User needs:

reduce manual job searching

centralised opportunity list

visa-friendly awareness

daily automation

7. Operational Requirements
7.1 Scheduling

System must support:

cron (macOS/Linux)

Windows Task Scheduler

7.2 GitHub Readiness

Project must support:

repository hosting

documentation

future GitHub Actions automation

8. Constraints

Visa filtering cannot be exact

LinkedIn & Seek scraping avoided

Architecture junior roles may be low volume

Data freshness depends on source update frequency

9. Future Requirements (Post-Stage 1)

GitHub Actions daily runs

public dashboard

ML ranking

company career portal connectors

Slack / Telegram alerts

web UI

10. Acceptance Criteria

Stage 1 is considered complete when:

workflow runs locally

collects jobs from at least 3 sources

filters correctly by role + location

deduplicates listings

generates CSV + HTML output

calculates visa score

sends email successfully
