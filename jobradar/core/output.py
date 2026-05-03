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
    h2   {{ color: #2c3e50; margin-top: 28px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th   {{ background: #2c3e50; color: white; padding: 8px; text-align: left; }}
    td   {{ border: 1px solid #ddd; padding: 6px; vertical-align: top; }}
    tr:nth-child(even) {{ background: #f9f9f9; }}
    .score-high {{ color: green; font-weight: bold; }}
    .score-low  {{ color: red; font-weight: bold; }}
    .score-mid  {{ color: #888; }}
    .match-high {{ color: #1a7abf; font-weight: bold; }}
    .match-mid  {{ color: #888; }}
    .top5-card  {{ border: 1px solid #b0cfe8; border-radius: 6px; padding: 12px 16px;
                   margin-bottom: 10px; background: #f0f7ff; }}
    .top5-card h3 {{ margin: 0 0 4px 0; font-size: 14px; }}
    .top5-card p  {{ margin: 2px 0; color: #444; }}
    .badge {{ display: inline-block; border-radius: 3px; padding: 1px 6px;
              font-size: 11px; font-weight: bold; margin-right: 4px; }}
    .badge-match {{ background: #d0eaff; color: #1a6fa0; }}
    .badge-visa  {{ background: #d4edda; color: #1a6630; }}
    a {{ color: #2980b9; }}
  </style>
</head>
<body>
  <h1>JobRadar – Junior/Grad Tech Jobs</h1>
  <p>Adelaide &amp; Melbourne | Run date: {run_date} | {count} listings</p>
  <h2>⭐ Top 5 – Apply Today</h2>
{top5_section}
  <h2>All New Jobs</h2>
  <table>
    <thead>
      <tr>
        <th>Date</th><th>Source</th><th>Title</th><th>Company</th>
        <th>Location</th><th>Summary</th><th>Tags</th>
        <th>Match</th><th>Match Skills</th>
        <th>Visa</th><th>Visa Reason</th>
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
        <td class="{match_class}">{match_score}</td>
        <td>{match_skills}</td>
        <td class="{score_class}">{visa_score}</td>
        <td>{visa_reason}</td>
      </tr>"""


def _score_class(score: int) -> str:
    if score >= 4:
        return "score-high"
    if score <= 1:
        return "score-low"
    return "score-mid"


def _match_class(score: int) -> str:
    return "match-high" if score >= 6 else "match-mid"


def _build_top5_html(jobs: List[JobListing]) -> str:
    candidates = [j for j in jobs if j.match_score >= 0]
    candidates.sort(key=lambda j: -(j.match_score * 2 + j.visa_score))
    top5 = candidates[:5]
    if not top5:
        return "  <p><em>No scored jobs yet.</em></p>"
    cards = []
    for j in top5:
        cards.append(
            f'  <div class="top5-card">'
            f'<h3><a href="{j.url}" target="_blank">{_esc(j.title)}</a> — {_esc(j.company)}</h3>'
            f'<p>{_esc(j.location)} · {j.source} · {j.date_found}</p>'
            f'<p>'
            f'<span class="badge badge-match">Match {j.match_score}/10</span>'
            f'<span class="badge badge-visa">Visa {j.visa_score}/5</span>'
            f'Skills: {_esc(j.match_skills)}'
            f'</p>'
            f'<p style="color:#555">{_esc(j.summary[:200])}</p>'
            f'</div>'
        )
    return "\n".join(cards)


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
                match_score=j.match_score if j.match_score >= 0 else "–",
                match_class=_match_class(j.match_score),
                match_skills=_esc(j.match_skills),
                visa_score=j.visa_score if j.visa_score >= 0 else "–",
                score_class=_score_class(j.visa_score),
                visa_reason=_esc(j.visa_reason),
            )
        )

    html = _HTML_TEMPLATE.format(
        run_date=run_date,
        count=len(jobs),
        top5_section=_build_top5_html(jobs),
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
