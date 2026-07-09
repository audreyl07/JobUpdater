from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, joinedload

from app.models.job import Job, JobHash, JobStatus


@dataclass(slots=True)
class JobRepository:
    """Repository for persisted job postings and content hashes."""

    session: Session

    def get_by_id(self, job_id: int) -> Job | None:
        return self.session.get(Job, job_id)

    def get_by_external_id(self, company_id: int, external_job_id: str) -> Job | None:
        stmt = (
            select(Job)
            .options(joinedload(Job.hash_record))
            .where(
                Job.company_id == company_id,
                Job.external_job_id == external_job_id,
            )
        )
        return self.session.scalar(stmt)

    def list_by_company(self, company_id: int) -> list[Job]:
        stmt = (
            select(Job)
            .options(joinedload(Job.hash_record))
            .where(Job.company_id == company_id)
            .order_by(Job.id.asc())
        )
        return list(self.session.scalars(stmt).all())

    def list_active_by_company(self, company_id: int) -> list[Job]:
        stmt = (
            select(Job)
            .options(joinedload(Job.hash_record))
            .where(
                Job.company_id == company_id,
                Job.status == JobStatus.ACTIVE,
            )
            .order_by(Job.id.asc())
        )
        return list(self.session.scalars(stmt).all())

    def preload_by_company(self, company_id: int) -> dict[str, Job]:
        """
        Preload all jobs for a company into a dict keyed by external_job_id.

        This supports O(1) reconciliation during a scan sync pass.
        """
        jobs = self.list_by_company(company_id)
        return {job.external_job_id: job for job in jobs}

    def insert(
        self,
        job: Job,
        *,
        content_hash: str | None = None,
    ) -> Job:
        if content_hash is not None:
            job.hash_record = JobHash(content_hash=content_hash)

        self.session.add(job)
        self.session.flush()
        return job

    def insert_many(
        self,
        jobs: Sequence[Job],
        *,
        content_hashes: Sequence[str | None] | None = None,
    ) -> list[Job]:
        if content_hashes is not None and len(content_hashes) != len(jobs):
            raise ValueError("content_hashes must match jobs length.")

        for index, job in enumerate(jobs):
            if content_hashes is not None and content_hashes[index] is not None:
                job.hash_record = JobHash(content_hash=content_hashes[index] or "")

        self.session.add_all(jobs)
        self.session.flush()
        return list(jobs)

    def update(
        self,
        job: Job,
        *,
        title: str | None = None,
        location: str | None = None,
        department: str | None = None,
        employment_type: str | None = None,
        remote: bool | None = None,
        salary: str | None = None,
        url: str | None = None,
        description: str | None = None,
        posted_date: datetime | None = None,
        first_seen: datetime | None = None,
        last_seen: datetime | None = None,
        status: str | None = None,
        content_hash: str | None = None,
    ) -> Job:
        if title is not None:
            job.title = title
        if location is not None:
            job.location = location
        if department is not None:
            job.department = department
        if employment_type is not None:
            job.employment_type = employment_type
        if remote is not None:
            job.remote = remote
        if salary is not None:
            job.salary = salary
        if url is not None:
            job.url = url
        if description is not None:
            job.description = description
        if posted_date is not None:
            job.posted_date = posted_date
        if first_seen is not None:
            job.first_seen = first_seen
        if last_seen is not None:
            job.last_seen = last_seen
        if status is not None:
            job.status = status

        if content_hash is not None:
            if job.hash_record is None:
                job.hash_record = JobHash(content_hash=content_hash)
            else:
                job.hash_record.content_hash = content_hash

        self.session.flush()
        return job

    def update_many(self, jobs: Sequence[Job]) -> list[Job]:
        self.session.flush()
        return list(jobs)

    def mark_removed(self, job: Job) -> Job:
        job.status = JobStatus.REMOVED
        self.session.flush()
        return job

    def mark_removed_many(self, jobs: Sequence[Job]) -> list[Job]:
        for job in jobs:
            job.status = JobStatus.REMOVED

        self.session.flush()
        return list(jobs)

    def update_last_seen(self, job: Job, last_seen: datetime) -> Job:
        job.last_seen = last_seen
        self.session.flush()
        return job

    def mark_removed_missing_external_ids(
        self,
        company_id: int,
        active_external_ids: set[str],
    ) -> int:
        """
        Mark jobs as REMOVED when they were not present in the current scan.
        """
        stmt = select(Job).where(
            Job.company_id == company_id,
            Job.status == JobStatus.ACTIVE,
        )
        jobs = list(self.session.scalars(stmt).all())
        removed = 0

        for job in jobs:
            if job.external_job_id not in active_external_ids:
                job.status = JobStatus.REMOVED
                removed += 1

        self.session.flush()
        return removed