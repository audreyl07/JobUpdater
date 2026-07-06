from __future__ import annotations

import html
import logging
import re
from datetime import datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import httpx

from app.models.job import EmploymentType, Job
from app.scanners.base import BaseScanner, DataSource, DiscoveryResult, ScannerError
from app.scanners.workday_discovery import WorkdayDiscovery, WorkdayEndpoint, WorkdayDiscoveryError

logger = logging.getLogger(__name__)


class WorkdayScanner(BaseScanner):
    """Scanner for Workday career sites."""

    def __init__(
        self,
        company_name: str,
        base_url: str,
        *,
        timeout: float = 30.0,
        page_size: int = 50,
    ) -> None:
        self.company_name = company_name.strip()
        self.base_url = base_url.strip().rstrip("/")
        self.timeout = timeout
        self.page_size = page_size
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0 Safari/537.36"
                ),
                "Accept": "application/json, text/plain, */*",
            },
        )
        self._discovery = WorkdayDiscovery(timeout=self.timeout)
        super().__init__()

    def discover(self) -> DiscoveryResult:
        """Find the Workday JSON endpoint for this company."""
        logger.info(
            "Starting discovery company=%s url=%s",
            self.company_name,
            self.base_url,
        )

        if self._looks_like_workday_jobs_endpoint(self.base_url):
            return DiscoveryResult(
                source=DataSource.API,
                endpoint=self.base_url,
                details={"discovered_from": "base_url", "method": "GET"},
            )

        endpoint = self._discovery.discover(
            self.base_url,
            company=self.company_name,
            client=self._client,
        )

        logger.info(
            "Discovered Workday endpoint company=%s endpoint=%s",
            self.company_name,
            endpoint.url,
        )
        return DiscoveryResult(
            source=DataSource.API,
            endpoint=endpoint.url,
            details={
                "discovered_from": "workday_discovery_v2",
                "method": endpoint.method,
                "tenant": endpoint.tenant,
                "site": endpoint.site,
            },
        )

    def scan(
        self,
        company: str | None = None,
        career_url: str | None = None,
    ) -> list[Job]:
        """Scan a Workday career site and return normalized jobs."""
        if company is not None:
            self.company_name = company.strip()
        if career_url is not None:
            self.base_url = career_url.strip().rstrip("/")

        discovery = self.discover()
        raw_jobs = self.fetch_jobs(discovery)
        return [job for job in (self.normalize(raw) for raw in raw_jobs) if job is not None]

    def _looks_like_workday_jobs_endpoint(self, url: str) -> bool:
        """Return True when the URL already points at a Workday jobs API endpoint."""
        parsed = urlparse(url)
        return bool(re.search(r"/wday/cxs/[^/]+/[^/]+/jobs/?$", parsed.path, flags=re.IGNORECASE))

    def _extract_jobs(self, payload: Any) -> list[dict[str, Any]]:
        """Extract job records from a Workday JSON payload."""
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]

        if isinstance(payload, dict):
            for key in ("jobPostings", "jobs", "postings", "data", "items", "results"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]

            for value in payload.values():
                if isinstance(value, list):
                    dict_items = [item for item in value if isinstance(item, dict)]
                    if dict_items:
                        return dict_items

        raise ScannerError("Could not find a jobs list in Workday payload")

    def _extract_total_count(self, payload: Any) -> int | None:
        """Extract a total result count when Workday provides one."""
        if isinstance(payload, dict):
            for key in ("totalCount", "total", "count", "jobCount", "totalJobs"):
                value = payload.get(key)
                if isinstance(value, int):
                    return value
                if isinstance(value, str) and value.isdigit():
                    return int(value)

        if isinstance(payload, list):
            return len(payload)

        return None

    def fetch_jobs(self, discovery: DiscoveryResult) -> list[dict[str, Any]]:
        """Fetch all raw job records from the discovered Workday endpoint."""
        if discovery.source is not DataSource.API:
            raise ScannerError(
                f"{self.company_name} requires API fetching in this step; browser mode is not implemented"
            )

        logger.info(
            "Starting fetch company=%s request_url=%s",
            self.company_name,
            discovery.endpoint,
        )

        method = str(discovery.details.get("method", "GET")).upper()

        all_jobs: list[dict[str, Any]] = []
        offset = 0
        page_number = 1

        while True:
            if method == "POST":
                request_url = discovery.endpoint
            else:
                request_url = self._with_query_params(
                    discovery.endpoint,
                    {"offset": str(offset), "limit": str(self.page_size)},
                )

            logger.info(
                "Requesting page company=%s page=%s url=%s method=%s",
                self.company_name,
                page_number,
                request_url,
                method,
            )

            payload = self._request_json(request_url, method=method, offset=offset)
            page_jobs = self._extract_jobs(payload)

            logger.info(
                "Retrieved jobs company=%s page=%s count=%s",
                self.company_name,
                page_number,
                len(page_jobs),
            )

            if page_number == 1 and not page_jobs:
                raise ScannerError(f"Empty Workday response for {self.company_name}")

            all_jobs.extend(page_jobs)

            total = self._extract_total_count(payload)
            if total is not None and len(all_jobs) >= total:
                break

            if len(page_jobs) < self.page_size:
                break

            offset += self.page_size
            page_number += 1

        logger.info(
            "Completed fetch company=%s total_jobs=%s",
            self.company_name,
            len(all_jobs),
        )
        return all_jobs

    def normalize(self, raw_job: dict[str, Any]) -> Job | None:
        """Convert one Workday record into the standardized Job model."""
        try:
            job_id = self._first_non_empty(
                raw_job,
                ("job_id", "jobId", "requisitionId", "requisition_id", "id", "jobPostingId"),
            )
            title = self._first_non_empty(raw_job, ("title", "jobTitle", "positionTitle", "name"))
            location = self._extract_location(raw_job)
            url = self._extract_url(raw_job)
            description = self._optional_string(
                raw_job,
                ("description", "jobDescription", "jobDescriptionText", "content"),
            )
            employment_type = self._parse_employment_type(raw_job)
            posted_at = self._parse_datetime(
                self._optional_string(
                    raw_job,
                    ("postedAt", "postedDate", "postedOn", "datePosted", "publishDate", "createdOn"),
                )
            )

            if not job_id or not title or not location or not url:
                logger.warning(
                    "Skipping malformed job company=%s raw_keys=%s",
                    self.company_name,
                    sorted(raw_job.keys()),
                )
                return None

            return Job(
                job_id=job_id,
                company=self.company_name,
                title=title,
                location=location,
                url=url,
                description=description,
                employment_type=employment_type,
                posted_at=posted_at,
            )
        except (TypeError, ValueError) as exc:
            logger.error(
                "Failed to normalize job company=%s error=%s raw_job=%s",
                self.company_name,
                exc,
                raw_job,
            )
            return None

    def _request_json(self, url: str, *, method: str = "GET", offset: int = 0) -> Any:
        try:
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
            }

            if method.upper() == "POST":
                response = self._client.post(
                    url,
                    headers=headers,
                    json={"limit": self.page_size, "offset": offset},
                )
            else:
                response = self._client.get(url, headers=headers)

            response.raise_for_status()
            if not response.content:
                raise ScannerError(f"Empty JSON response from {url}")
            return response.json()
        except httpx.TimeoutException as exc:
            logger.error("Timeout company=%s url=%s error=%s", self.company_name, url, exc)
            raise ScannerError(f"Timeout while requesting {url}") from exc
        except (ValueError, httpx.DecodingError) as exc:
            logger.error("Invalid JSON company=%s url=%s error=%s", self.company_name, url, exc)
            raise ScannerError(f"Invalid JSON returned by {url}") from exc
        except httpx.HTTPStatusError as exc:
            logger.error("HTTP error company=%s url=%s error=%s", self.company_name, url, exc)
            raise ScannerError(f"HTTP error while requesting {url}") from exc
        except httpx.HTTPError as exc:
            logger.error("Network error company=%s url=%s error=%s", self.company_name, url, exc)
            raise ScannerError(f"Network error while requesting {url}") from exc

    def _extract_location(self, raw_job: dict[str, Any]) -> str | None:
        """Extract a readable location string from a Workday job payload."""
        value = self._first_non_empty(
            raw_job,
            ("location", "locationsText", "locationText", "primaryLocation"),
        )
        if value:
            return value

        location = raw_job.get("location")
        if isinstance(location, dict):
            return self._first_non_empty(location, ("descriptor", "name", "title", "text"))
        if isinstance(location, list) and location:
            first = location[0]
            if isinstance(first, dict):
                return self._first_non_empty(first, ("descriptor", "name", "title", "text"))

        return None

    def _extract_url(self, raw_job: dict[str, Any]) -> str | None:
        candidate = self._optional_string(
            raw_job,
            ("url", "jobUrl", "jobPostingUrl", "externalUrl", "externalApplyUrl", "externalPath", "path"),
        )
        if not candidate:
            return None

        if candidate.startswith(("http://", "https://")):
            return candidate

        return urljoin(self.base_url + "/", candidate)

    def _parse_employment_type(self, raw_job: dict[str, Any]) -> EmploymentType:
        value = self._optional_string(raw_job, ("employmentType", "jobType", "type", "employment"))
        if not value:
            return EmploymentType.UNKNOWN

        normalized = value.strip().lower()
        if any(token in normalized for token in ("full", "regular", "fte")):
            return EmploymentType.FULL_TIME
        if any(token in normalized for token in ("part", "pt")):
            return EmploymentType.PART_TIME
        if any(token in normalized for token in ("intern", "internship")):
            return EmploymentType.INTERN
        if any(token in normalized for token in ("contract", "contractor", "contingent")):
            return EmploymentType.CONTRACT
        if any(token in normalized for token in ("temp", "temporary")):
            return EmploymentType.TEMPORARY

        return EmploymentType.UNKNOWN

    def _parse_datetime(self, value: str | None) -> datetime | None:
        if not value:
            return None

        candidates = (value, value.replace("Z", "+00:00"))
        for candidate in candidates:
            try:
                return datetime.fromisoformat(candidate)
            except ValueError:
                pass

        for fmt in (
            "%Y-%m-%d",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%m/%d/%Y",
            "%d/%m/%Y",
        ):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue

        return None

    def _first_non_empty(self, raw_job: dict[str, Any], keys: tuple[str, ...]) -> str | None:
        for key in keys:
            value = raw_job.get(key)
            if isinstance(value, str):
                stripped = value.strip()
                if stripped:
                    return stripped
            elif value is not None:
                text = str(value).strip()
                if text:
                    return text
        return None

    def _optional_string(self, raw_job: dict[str, Any], keys: tuple[str, ...]) -> str | None:
        return self._first_non_empty(raw_job, keys)

    def _with_query_params(self, url: str, params: dict[str, str]) -> str:
        parsed = urlparse(url)
        existing_params = dict(parse_qsl(parsed.query, keep_blank_values=True))
        existing_params.update(params)
        return urlunparse(parsed._replace(query=urlencode(existing_params)))

    def _fetch_jobs_payload(self, client: httpx.Client, endpoint: WorkdayEndpoint) -> dict[str, object] | list[object]:
        """Fetch Workday jobs payload using the discovered HTTP method."""
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        if endpoint.method == "POST":
            response = client.post(
                endpoint.url,
                headers=headers,
                json={"limit": self.page_size, "offset": 0},
            )
        else:
            response = client.get(endpoint.url, headers=headers)

        response.raise_for_status()
        return response.json()