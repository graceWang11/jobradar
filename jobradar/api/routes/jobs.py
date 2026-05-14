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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from jobradar.api.auth import require_auth
from jobradar.api.db import JobMatchCache, TrackedJob, get_session
from jobradar.api.jobs_service import (
    cache_key,
    csv_mtime,
    filter_and_score,
    latest_csv,
    load_listings,
    to_job,
)
from jobradar.api.schemas import (
    Job,
    JobMatchBody,
    JobMatchResponse,
    TrackedJobIn,
    TrackedJobOut,
)

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
        session.commit()
    else:
        session.add(
            JobMatchCache(
                key=key,
                jobs_json=serialized,
                source_mtime=mtime,
                cached_at=now,
            )
        )
        try:
            session.commit()
        except IntegrityError:
            # Concurrent request inserted the same key first. Same inputs
            # produce the same output, so just drop our insert and return.
            session.rollback()

    if body.limit and body.limit > 0:
        jobs = jobs[: body.limit]
    return JobMatchResponse(cachedAt=now, fresh=True, jobs=jobs)


# ── Tracked jobs (saved / applied / pipeline) ────────────────────────────────


def _row_to_tracked_out(row: TrackedJob) -> TrackedJobOut:
    return TrackedJobOut(
        jobId=row.job_id,
        status=row.status,  # type: ignore[arg-type]
        trackedAt=row.tracked_at,
        updatedAt=row.updated_at,
        job=Job.model_validate(json.loads(row.job_json)),
    )


@router.get("/tracked", response_model=List[TrackedJobOut], response_model_exclude_none=True)
def list_tracked(session: Session = Depends(get_session)) -> List[TrackedJobOut]:
    rows = (
        session.query(TrackedJob)
        .order_by(TrackedJob.updated_at.desc())
        .all()
    )
    return [_row_to_tracked_out(r) for r in rows]


@router.put(
    "/tracked/{job_id}",
    response_model=TrackedJobOut,
    response_model_exclude_none=True,
)
def upsert_tracked(
    job_id: str,
    body: TrackedJobIn,
    session: Session = Depends(get_session),
) -> TrackedJobOut:
    if body.job.id != job_id:
        raise HTTPException(status_code=400, detail="job.id must match path job_id")
    now = datetime.utcnow()
    snapshot = json.dumps(body.job.model_dump(mode="json", exclude_none=True), default=str)
    row = session.get(TrackedJob, job_id)
    if row is None:
        row = TrackedJob(
            job_id=job_id,
            status=body.status,
            job_json=snapshot,
            tracked_at=now,
            updated_at=now,
        )
        session.add(row)
    else:
        row.status = body.status
        row.job_json = snapshot
        row.updated_at = now
    session.commit()
    session.refresh(row)
    return _row_to_tracked_out(row)


@router.delete("/tracked/{job_id}")
def delete_tracked(job_id: str, session: Session = Depends(get_session)) -> dict:
    row = session.get(TrackedJob, job_id)
    if row is None:
        return {"jobId": job_id, "removed": False}
    session.delete(row)
    session.commit()
    return {"jobId": job_id, "removed": True}
