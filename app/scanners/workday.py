from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List
from urllib.parse import urlencode

import httpx

from app.models.job import Job, EmploymentType
from app.scanners.base import DataSource, ScannerError
from app.scanners.workday_discovery import WorkdayDiscovery, WorkdayEndpoint


class WorkdayScanner:
    """Scanner for Workday job listings."""

    def __init__(
        self,
        company_name: str,
        base_url: str,
        *,
        page_size: int = 50,
        timeout: float = 15.0,
    ) -> None:
        self.company_name = company_name
        self.base_url = base_url
        self.page_size = page_size
        self._client = httpx.Client(timeout=timeout, follow_redirects=True)
        self._discovery = WorkdayDiscovery(timeout=timeout)

    # ----------------------------------------------------------------------
    # DISCOVER
    # ----------------------------------------------------------------------
    def discover(self):
        """Wrap WorkdayDiscovery into a DiscoveryResult-like object."""

        # Case: base_url already points to jobs endpoint
        if "/wday/cxs/" in self.base_url and self.base_url.endswith("/jobs"):
            return type(
                "Discovery",
                (),
                {
                    "source": DataSource.API,
                    "endpoint": self.base_url,
                    "details": {
                        "discovered_from": "base_url",
                        "method": "POST",
                    },
                },
            )()

        # Otherwise use WorkdayDiscovery
        endpoint: WorkdayEndpoint = self._discovery.discover(
            self.base_url,
            company=self.company_name,
            client=self._client,
        )

        return type(
            "Discovery",
            (),
            {
                "source": DataSource.API,
                "endpoint": endpoint.url,
                "details": {
                    "discovered_from": "workday_discovery_v2",
                    "method": endpoint.method,
                    "tenant": endpoint.tenant,
                    "site": endpoint.site,
                },
            },
        )()

    # ----------------------------------------------------------------------
    # REQUEST JSON
    # ----------------------------------------------------------------------
    def _request_json(self, url: str, *, method: str = "GET", offset: int = 0) -> dict[str, Any]:
        """Perform GET or POST and return JSON with strong error handling."""

        try:
            if method.upper() == "GET":
                response = self._client.get(url)
            else:
                response = self._client.post(url, json={"limit": self.page_size, "offset": offset})

            response.raise_for_status()

        except httpx.TimeoutException:
            raise ScannerError("Timeout while requesting Workday API")

        except httpx.HTTPStatusError:
            raise ScannerError("HTTP error while requesting Workday API")

        # Empty response
        if not response.content:
            raise ScannerError("Empty JSON response")

        # Invalid JSON
        try:
            return response.json()
        except Exception:
            raise ScannerError("Invalid JSON")

    # ----------------------------------------------------------------------
    # FETCH JOBS
    # ----------------------------------------------------------------------
    def fetch_jobs(self, discovery) -> List[dict[str, Any]]:
        """Fetch all jobs using pagination."""

        endpoint = discovery.endpoint
        method = discovery.details.get("method", "GET")

        jobs: List[dict[str, Any]] = []

        # First page
        url = f"{endpoint}?{urlencode({'limit': self.page_size, 'offset': 0})}"
        payload = self._request_json(url, method=method, offset=0)

        try:
            first_page_jobs = self._extract_jobs(payload)
            total = self._extract_total_count(payload)
        except Exception as exc:
            raise ScannerError(str(exc))

        if not first_page_jobs:
            raise ScannerError("Empty Workday response")

        jobs.extend(first_page_jobs)

        # Additional pages
        offset = self.page_size
        while offset < total:
            url = f"{endpoint}?{urlencode({'limit': self.page_size, 'offset': offset})}"
            payload = self._request_json(url, method=method, offset=offset)

            page_jobs = self._extract_jobs(payload)
            jobs.extend(page_jobs)

            offset += self.page_size

        return jobs

    # ----------------------------------------------------------------------
    # EXTRACTORS
    # ----------------------------------------------------------------------
    def _extract_jobs(self, payload: dict[str, Any]) -> List[dict[str, Any]]:
        if "jobPostings" in payload:
            return payload["jobPostings"]
        raise ScannerError("Could not find a jobs list")

    def _extract_total_count(self, payload: dict[str, Any]) -> int:
        if "totalCount" in payload:
            return int(payload["totalCount"])
        raise ScannerError("Could not determine total job count")

    # ----------------------------------------------------------------------
    # NORMALIZE
    # ----------------------------------------------------------------------
    def normalize(self, raw: dict[str, Any]) -> Job | None:
        """Convert raw Workday job into our Job model."""

        job_id = raw.get("job_id") or raw.get("jobId")
        title = raw.get("title")
        location = raw.get("location")
        url_path = raw.get("url") or raw.get("jobUrl")

        if not job_id or not title or not url_path:
            return None

        full_url = url_path
        if full_url.startswith("/"):
            full_url = self.base_url.rstrip("/") + full_url

        posted_raw = raw.get("postedDate")
        posted_at = None
        if posted_raw:
            posted_at = datetime.fromisoformat(posted_raw.replace("Z", "+00:00")).astimezone(timezone.utc)

        employment_raw = raw.get("employmentType", "")
        employment_type = EmploymentType.FULL_TIME if "Full" in employment_raw else EmploymentType.UNKNOWN

        return Job(
            job_id=job_id,
            company=self.company_name,
            title=title,
            location=location,
            url=full_url,
            description=raw.get("description", ""),
            department=raw.get("department", ""),
            posted_date=posted_at,
            employment_type=employment_type,
        )

    # ----------------------------------------------------------------------
    # SCAN
    # ----------------------------------------------------------------------
    def scan(self, company_name: str, base_url: str):
        discovery = self.discover()
        raw_jobs = self.fetch_jobs(discovery)
        return [self.normalize(job) for job in raw_jobs if self.normalize(job) is not None]
