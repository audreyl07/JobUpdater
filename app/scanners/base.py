"""
Abstract base class for all company career-site scanners.

Every company (IBM, and later Cisco, Nokia, ...) gets one subclass of
`BaseScanner`. This file defines the CONTRACT that subclasses must
fulfil, and a few small immutable data types used to communicate
results between stages, so that:

  - Adding a new company never requires touching this file, the
    filters module, or the database module.
  - Filtering, deduplication, and persistence code can be written once,
    against `Job` objects, and work for every company.

Pipeline shape (each method's job):

    discover()    -> DiscoveryResult   # "how do I get data from this company?"
    fetch_jobs()  -> list[RawJob]      # "get me the raw records"
    normalize()   -> Job               # "convert ONE raw record to our schema"
    scan()        -> ScanResult        # orchestrates the three above

Deliberately NOT part of this class: filtering and database
persistence. Those are cross-cutting concerns that operate on `Job`
objects regardless of which company produced them, so they live in
`app/filters` and `app/database` and are composed by the caller (e.g.
`main.py` or a future scheduler), not baked into every scanner.
This is also why `scan()` returns raw normalized jobs rather than
"new jobs" - "new" is a database-layer concept (has it been seen
before?), not something a scanner can know on its own.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.models.job import Job
from app.utils.logger import get_logger, kv

logger = get_logger(__name__)


class DataSource(str, Enum):
    """How a scanner ultimately obtained its data.

    Recorded on every `ScanResult` (and on every `Job.source`) so that
    monitoring/alerting can tell "IBM scanner is running in degraded
    Playwright-fallback mode" apart from "IBM scanner is using its
    normal API path" without reading logs line-by-line.
    """

    API = "api"
    BROWSER = "browser"


@dataclass(frozen=True)
class DiscoveryResult:
    """Output of `discover()`: describes HOW jobs will be fetched.

    Attributes:
        source: Whether an API was found (`DataSource.API`) or we must
            fall back to browser automation (`DataSource.BROWSER`).
        endpoint: The concrete URL (API endpoint or the search page URL
            to drive with Playwright) that `fetch_jobs()` should use.
            Kept here - rather than re-discovered inside `fetch_jobs()`
            - so discovery is a single, cacheable, loggable step and
            `fetch_jobs()` stays a pure "given an endpoint, get pages"
            function.
        details: Free-form extra info for logging/debugging (e.g. which
            headers were required, or why the API path was rejected).
            Never used for control flow - only for humans reading logs.
    """

    source: DataSource
    endpoint: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ScanResult:
    """Output of `scan()`: the full result of one scan pass for one company.

    Attributes:
        company: Name of the company scanned (mirrors `Job.company`).
        source: Which data source was actually used for this run.
        jobs: All normalized jobs currently posted, matching nothing
            more than "this scanner found them" - filtering and
            new-vs-seen logic happen downstream.
        raw_count: Number of raw records fetch_jobs() returned, BEFORE
            normalization. Kept alongside `len(jobs)` because a
            mismatch (raw_count > len(jobs)) signals normalize()
            silently dropped records - a bug we want visible in logs,
            not hidden.
    """

    company: str
    source: DataSource
    jobs: list[Job]
    raw_count: int


class ScannerError(Exception):
    """Raised for scanner-specific failures (discovery failed, API down, etc.).

    A dedicated exception type (rather than letting `httpx`/Playwright
    exceptions bubble up raw) lets callers (schedulers, CLI, tests)
    catch "this company's scan failed" in one place regardless of
    which company or which underlying library raised it.
    """


class BaseScanner(ABC):
    """Abstract base class every company scanner must extend.

    Subclasses MUST implement all four abstract methods below.
    Subclasses MUST NOT expose raw API/HTML payloads outside of
    `fetch_jobs()` / `normalize()` - by the time `scan()` returns,
    everything is a `Job`.
    """

    #: Can be overridden by subclasses or set in `__init__()`.
    company_name: str = ""

    def __init__(self) -> None:
        company_name = getattr(self, "company_name", "").strip()
        if not company_name:
            raise ValueError(
                f"{type(self).__name__} must set a non-empty `company_name`"
            )
        self.company_name = company_name

    @abstractmethod
    def discover(self) -> DiscoveryResult:
        """Determine how this company's job listings can be retrieved.

        Must check for a stable API first (REST/GraphQL/known ATS
        endpoint) and only report `DataSource.BROWSER` if no such API
        exists or it is not usable. This method should be safe to call
        repeatedly (e.g. cheap enough to call once per scan) and must
        not raise for "no API found" - that's a normal, expected
        outcome, not an error. It SHOULD raise `ScannerError` if it
        cannot determine anything at all (e.g. the careers site itself
        is unreachable).
        """
        raise NotImplementedError

    @abstractmethod
    def fetch_jobs(self, discovery: DiscoveryResult) -> list[dict[str, Any]]:
        """Retrieve all raw job records using the method `discover()` selected.

        Must handle pagination internally - the returned list should be
        the complete set of currently-posted jobs (subject to whatever
        server-side filtering was configured), not just one page.

        Returns raw, source-shaped dicts (whatever the API/DOM gives
        us). These are intentionally untyped (`dict[str, Any]`) because
        every company's raw shape is different; `normalize()` is the
        only place allowed to understand that shape.
        """
        raise NotImplementedError

    @abstractmethod
    def normalize(self, raw_job: dict[str, Any]) -> Job | None:
        """Convert one raw record into a `Job`.

        Returns `None` (rather than raising) if a single record is
        malformed/unparseable - one bad record should never abort an
        entire scan. `scan()` is responsible for logging when this
        happens and continuing with the rest.
        """
        raise NotImplementedError

    def scan(self) -> ScanResult:
        """Run the full discover -> fetch -> normalize pipeline."""
        logger.info("Scanning %s", self.company_name)

        discovery = self.discover()
        logger.info(
            "Discovery complete %s",
            kv(
                company=self.company_name,
                source=discovery.source.value,
                endpoint=discovery.endpoint,
            ),
        )

        raw_jobs = self.fetch_jobs(discovery)
        logger.info("Found %s jobs %s", len(raw_jobs), kv(company=self.company_name))

        jobs: list[Job] = []
        dropped = 0
        for raw_job in raw_jobs:
            job = self.normalize(raw_job)
            if job is None:
                dropped += 1
                continue
            jobs.append(job)

        if dropped:
            logger.warning(
                "Dropped unparseable records %s",
                kv(company=self.company_name, dropped=dropped),
            )

        return ScanResult(
            company=self.company_name,
            source=discovery.source,
            jobs=jobs,
            raw_count=len(raw_jobs),
        )
