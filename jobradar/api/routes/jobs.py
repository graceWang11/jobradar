"""Matched-jobs endpoint backed by the latest pipeline CSV.

Reads the most recent output/jobs_YYYY-MM-DD.csv, maps each row to the
frontend Job shape, and filters by UserPreferences. Cached by (preferences,
resumeSkills, csv_mtime). ?refresh=1 forces a recompute against the same CSV
(useful right after a cron tick drops a new one).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from jobradar.api.auth import require_auth
from jobradar.api.db import JobMatchCache, get_session
from jobradar.api.jobs_service import (
    cache_key,
    csv_mtime,
    filter_and_score,
    latest_csv,
    load_listings,
    to_job,
)
from jobradar.api.schemas import Job, JobMatchBody, JobMatchResponse

router = APIRouter(prefix="/api/jobs", tags=["jobs"], dependencies=[Depends(require_auth)])


@router.post("/match", response_model=JobMatchResponse, response_model_exclude_none=True)
def match_jobs(
    body: JobMatchBody,
    refresh: int = 0,
    session: Session = Depends(get_session),
) -> JobMatchResponse:
    csv_path = latest_csv()
    if csv_path is None:
        raise HTTPException(status_code=503, detail="no pipeline output available yet")
    mtime = csv_mtime(csv_path)
    key = cache_key(body.preferences, body.resumeSkills, mtime)

    cached = None if refresh else session.get(JobMatchCache, key)
    if cached is not None:
        jobs = [Job.model_validate(j) for j in json.loads(cached.jobs_json)]
        if body.limit and body.limit > 0:
            jobs = jobs[: body.limit]
        return JobMatchResponse(cachedAt=cached.cached_at, fresh=False, jobs=jobs)

    listings = load_listings(csv_path)
    jobs: List[Job] = [to_job(l) for l in listings]
    jobs = filter_and_score(jobs, body.preferences, body.resumeSkills)

    now = datetime.utcnow()
    serialized = json.dumps(
        [j.model_dump(mode="json", exclude_none=True) for j in jobs],
        default=str,
    )
    existing = session.get(JobMatchCache, key)
    if existing is not None:
        existing.jobs_json = serialized
        existing.source_mtime = mtime
        existing.cached_at = now
    else:
        session.add(
            JobMatchCache(
                key=key,
                jobs_json=serialized,
                source_mtime=mtime,
                cached_at=now,
            )
        )
    session.commit()

    if body.limit and body.limit > 0:
        jobs = jobs[: body.limit]
    return JobMatchResponse(cachedAt=now, fresh=True, jobs=jobs)
