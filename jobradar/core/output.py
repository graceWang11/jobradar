"""Output generation: CSV, HTML, and Markdown."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import List

import pandas as pd

from jobradar.core.models import JobListing

_OUTPUT_DIR = Path(__file__).resolve().parents[2] / "output"

# ── HTML template ─────────────────────────────────────────────────────────────

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>JobRadar – {run_date}</title>
  <style>
    body {{ font-family: Arial, sans-serif; font-size: 13px; margin: 20px; }}
    h1   {{ color: #2c3e50; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th   {{ background: #2c3e50; color: white; padding: 8px; text-align: left; }}
    td   {{ border: 1px solid #ddd; padding: 6px; vertical-align: top; }}
    tr:nth-child(even) {{ background: #f9f9f9; }}
    .score-high {{ color: green; font-weight: bold; }}
    .score-low  {{ color: red; font-weight: bold; }}
    .score-mid  {{ color: #888; }}
    a {{ color: #2980b9; }}
  </style>
</head>
<body>
  <h1>JobRadar – Junior/Grad Tech Jobs</h1>
  <p>Adelaide &amp; Melbourne | Run date: {run_date} | {count} listings</p>
  <table>
    <thead>
      <tr>
        <th>Date</th><th>Source</th><th>Title</th><th>Company</th>
        <th>Location</th><th>Summary</th><th>Tags</th>
        <th>Visa Score</th><th>Visa Reason</th>
      </tr>
    </thead>
    <tbody>
{rows}
    </tbody>
  </table>
</body>
</html>
"""

_ROW_TEMPLATE = """\
      <tr>
        <td>{date_found}</td>
        <td>{source}</td>
        <td><a href="{url}" target="_blank">{title}</a></td>
        <td>{company}</td>
        <td>{location}</td>
        <td>{summary}</td>
        <td>{tags}</td>
        <td class="{score_class}">{visa_score}</td>
        <td>{visa_reason}</td>
      </tr>"""


def _score_class(score: int) -> str:
    if score >= 4:
        return "score-high"
    if score <= 1:
        return "score-low"
    return "score-mid"


# ── Public API ────────────────────────────────────────────────────────────────

def save_csv(jobs: List[JobListing], run_date: date | None = None) -> Path:
    """Write jobs to output/jobs_YYYY-MM-DD.csv and return the path."""
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    run_date = run_date or date.today()
    path = _OUTPUT_DIR / f"jobs_{run_date}.csv"
    rows = [j.to_dict() for j in jobs]
    df = pd.DataFrame(rows)
    df.to_csv(path, index=False, encoding="utf-8")
    print(f"[output] CSV saved → {path}")
    return path


def save_html(jobs: List[JobListing], run_date: date | None = None) -> Path:
    """Write jobs to output/jobs_YYYY-MM-DD.html and return the path."""
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    run_date = run_date or date.today()
    path = _OUTPUT_DIR / f"jobs_{run_date}.html"

    rows_html = []
    for j in jobs:
        rows_html.append(
            _ROW_TEMPLATE.format(
                date_found=j.date_found,
                source=j.source,
                url=j.url,
                title=_esc(j.title),
                company=_esc(j.company),
                location=_esc(j.location),
                summary=_esc(j.summary[:200]),
                tags=", ".join(j.tags),
                visa_score=j.visa_score if j.visa_score >= 0 else "–",
                score_class=_score_class(j.visa_score),
                visa_reason=_esc(j.visa_reason),
            )
        )

    html = _HTML_TEMPLATE.format(
        run_date=run_date,
        count=len(jobs),
        rows="\n".join(rows_html),
    )
    path.write_text(html, encoding="utf-8")
    print(f"[output] HTML saved → {path}")
    return path


def save_markdown(jobs: List[JobListing], run_date: date | None = None) -> Path:
    """Write jobs to output/jobs_YYYY-MM-DD.md and return the path."""
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    run_date = run_date or date.today()
    path = _OUTPUT_DIR / f"jobs_{run_date}.md"

    lines = [
        f"# JobRadar – {run_date}",
        f"",
        f"*Adelaide & Melbourne | {len(jobs)} listings*",
        "",
        "| Date | Source | Title | Company | Location | Tags | Visa | Visa Reason |",
        "|------|--------|-------|---------|----------|------|------|-------------|",
    ]
    for j in jobs:
        lines.append(
            f"| {j.date_found} | {j.source} | [{j.title}]({j.url}) | "
            f"{j.company} | {j.location} | {', '.join(j.tags)} | "
            f"{j.visa_score if j.visa_score >= 0 else '–'} | {j.visa_reason} |"
        )

    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[output] Markdown saved → {path}")
    return path


def _esc(text: str) -> str:
    """Minimal HTML escaping."""
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
    )
