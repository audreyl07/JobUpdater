"""Initial schema: companies, jobs, job_hashes, scan_history, notifications.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-07-09

Notes on job_hashes vs jobs.content_hash:
    `jobs.content_hash` holds the CURRENT hash for fast diffing during a
    scan (avoids a join on every comparison). `job_hashes` is an append-only
    audit trail of every hash a job has had over time, useful for debugging
    "why did this job re-notify" questions. job_sync_service.py writes to
    jobs.content_hash on every insert/update; writing history rows to
    job_hashes is optional/future work and not required for the sync logic
    to function.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


job_status_enum = sa.Enum("ACTIVE", "REMOVED", name="job_status")
scan_status_enum = sa.Enum("RUNNING", "SUCCESS", "FAILED", name="scan_status")


def upgrade() -> None:
    bind = op.get_bind()
    job_status_enum.create(bind, checkfirst=True)
    scan_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False, unique=True),
        sa.Column("career_site_url", sa.String(length=2048), nullable=False),
        sa.Column("scanner_type", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_job_id", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("location", sa.String(length=500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("department", sa.String(length=255), nullable=True),
        sa.Column("salary", sa.String(length=255), nullable=True),
        sa.Column("employment_type", sa.String(length=100), nullable=True),
        sa.Column("url", sa.String(length=2048), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("status", job_status_enum, nullable=False, server_default="ACTIVE"),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "company_id", "external_job_id", name="uq_jobs_company_external_id"
        ),
    )
    op.create_index("ix_jobs_company_id", "jobs", ["company_id"])
    op.create_index("ix_jobs_status", "jobs", ["status"])

    op.create_table(
        "job_hashes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "job_id",
            sa.Integer(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_job_hashes_job_id", "job_hashes", ["job_id"])

    op.create_table(
        "scan_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", scan_status_enum, nullable=False, server_default="RUNNING"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("jobs_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("jobs_added", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("jobs_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("jobs_removed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.String(length=2000), nullable=True),
    )
    op.create_index("ix_scan_history_company_id", "scan_history", ["company_id"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "job_id",
            sa.Integer(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reason", sa.String(length=100), nullable=False),
        sa.Column(
            "notified_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        # One notification per job: enforces dedup at the DB level in
        # addition to the application-level check in NotificationRepository.
        sa.UniqueConstraint("job_id", name="uq_notifications_job_id"),
    )
    op.create_index("ix_notifications_company_id", "notifications", ["company_id"])


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("scan_history")
    op.drop_table("job_hashes")
    op.drop_table("jobs")
    op.drop_table("companies")

    bind = op.get_bind()
    scan_status_enum.drop(bind, checkfirst=True)
    job_status_enum.drop(bind, checkfirst=True)