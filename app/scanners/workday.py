from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import httpx

from app.models.job import EmploymentType, Job
from app.scanners.base import BaseScanner, DataSource, DiscoveryResult, ScannerError

logger = logging.getLogger(__name__)


class WorkdayScanner(BaseScanner):
    """Scanner for Workday career sites.

    This scanner prefers Workday JSON endpoints and keeps the raw Workday
    response shape private to this module.
    """

    def __init__(
        self,
        company_name: str,
        base_url: str,
        *,
        timeout: float = 30.0,
        page_size: int = 50,
    ) -> None:
        self.company_name = company_name
        self.base_url = base_url.rstrip("/")
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
                details={"discovered_from": "base_url"},
            )

        html = self._fetch_text(self.base_url)
        endpoint = self._find_jobs_endpoint(html)

        if not endpoint:
            raise ScannerError(
                f"Could not discover a Workday jobs JSON endpoint for "
                f"{self.company_name}"
            )

        logger.info(
            "Discovered Workday endpoint company=%s endpoint=%s",
            self.company_name,
            endpoint,
        )
        return DiscoveryResult(
            source=DataSource.API,
            endpoint=endpoint,
            details={"discovered_from": "html"},
        )

    def fetch_jobs(self, discovery: DiscoveryResult) -> list[dict[str, Any]]:
        """Fetch all raw job records from the discovered Workday endpoint."""
        if discovery.source is not DataSource.API:
            raise ScannerError(
                f"{self.company_name} requires API fetching in this step; "
                "browser mode is not implemented"
            )

        logger.info(
            "Starting fetch company=%s request_url=%s",
            self.company_name,
            discovery.endpoint,
        )

        all_jobs: list[dict[str, Any]] = []
        offset = 0
        page_number = 1

        while True:
            request_url = self._with_query_params(
                discovery.endpoint,
                {
                    "offset": str(offset),
                    "limit": str(self.page_size),
                },
            )

            logger.info(
                "Requesting page company=%s page=%s url=%s",
                self.company_name,
                page_number,
                request_url,
            )

            payload = self._request_json(request_url)
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
                (
                    "job_id",
                    "jobId",
                    "requisitionId",
                    "requisition_id",
                    "id",
                    "jobPostingId",
                    "requisitionNumber",
                ),
            )
            title = self._first_non_empty(
                raw_job,
                ("title", "jobTitle", "positionTitle", "name"),
            )
            location = self._first_non_empty(
                raw_job,
                ("location", "locationsText", "locationText", "primaryLocation"),
            )
            url = self._extract_url(raw_job)
            description = self._optional_string(
                raw_job,
                ("description", "jobDescription", "jobDescriptionText", "content"),
            )
            department = self._optional_string(
                raw_job,
                ("department", "jobFamily", "organization", "businessUnit"),
            )
            posted_date = self._parse_datetime(
                self._optional_string(
                    raw_job,
                    (
                        "postedDate",
                        "postedOn",
                        "datePosted",
                        "publishDate",
                        "createdOn",
                    ),
                )
            )
            employment_type = self._parse_employment_type(raw_job)

            if not job_id or not title or not location or not url:
                logger.warning(
                    "Skipping malformed job company=%s raw_keys=%s",
                    self.company_name,
                    sorted(raw_job.keys()),
                )
                return None

            return Job(
                job_id=job_id,
                title=title,
                company=self.company_name,
                location=location,
                department=department,
                employment_type=employment_type,
                posted_date=posted_date,
                url=url,
                description=description,
            )
        except (TypeError, ValueError) as exc:
            logger.error(
                "Failed to normalize job company=%s error=%s raw_job=%s",
                self.company_name,
                exc,
                raw_job,
            )
            return None

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def _fetch_text(self, url: str) -> str:
        try:
            response = self._client.get(url)
            response.raise_for_status()
            if not response.text.strip():
                raise ScannerError(f"Empty response from {url}")
            return response.text
        except httpx.TimeoutException as exc:
            logger.error(
                "Timeout company=%s url=%s error=%s",
                self.company_name,
                url,
                exc,
            )
            raise ScannerError(f"Timeout while requesting {url}") from exc
        except httpx.HTTPStatusError as exc:
            logger.error(
                "HTTP error company=%s url=%s error=%s",
                self.company_name,
                url,
                exc,
            )
            raise ScannerError(f"HTTP error while requesting {url}") from exc
        except httpx.HTTPError as exc:
            logger.error(
                "Network error company=%s url=%s error=%s",
                self.company_name,
                url,
                exc,
            )
            raise ScannerError(f"Network error while requesting {url}") from exc

    def _request_json(self, url: str) -> Any:
        try:
            response = self._client.get(url)
            response.raise_for_status()
            if not response.content:
                raise ScannerError(f"Empty JSON response from {url}")
            return response.json()
        except httpx.TimeoutException as exc:
            logger.error(
                "Timeout company=%s url=%s error=%s",
                self.company_name,
                url,
                exc,
            )
            raise ScannerError(f"Timeout while requesting {url}") from exc
        except (ValueError, httpx.DecodingError) as exc:
            logger.error(
                "Invalid JSON company=%s url=%s error=%s",
                self.company_name,
                url,
                exc,
            )
            raise ScannerError(f"Invalid JSON returned by {url}") from exc
        except httpx.HTTPStatusError as exc:
            logger.error(
                "HTTP error company=%s url=%s error=%s",
                self.company_name,
                url,
                exc,
            )
            raise ScannerError(f"HTTP error while requesting {url}") from exc
        except httpx.HTTPError as exc:
            logger.error(
                "Network error company=%s url=%s error=%s",
                self.company_name,
                url,
                exc,
            )
            raise ScannerError(f"Network error while requesting {url}") from exc

    def _find_jobs_endpoint(self, html: str) -> str | None:
        patterns = (
            r"https?://[^\"'\s>]+/wday/cxs/[^\"'\s>]+/jobs[^\"'\s<]*",
            r"/wday/cxs/[^\"'\s>]+/jobs[^\"'\s<]*",
        )
        for pattern in patterns:
            match = re.search(pattern, html, flags=re.IGNORECASE)
            if match:
                candidate = match.group(0)
                return urljoin(self.base_url + "/", candidate)
        return None

    def _looks_like_workday_jobs_endpoint(self, url: str) -> bool:
        return "/wday/cxs/" in url and "/jobs" in url

    def _extract_jobs(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]

        if not isinstance(payload, dict):
            raise ScannerError(
                f"Unexpected Workday response format for {self.company_name}: "
                f"{type(payload)!r}"
            )

        for key in (
            "jobPostings",
            "jobs",
            "requisitions",
            "results",
            "items",
            "data",
        ):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]

        raise ScannerError(
            f"Could not find a jobs list in Workday response for {self.company_name}"
        )

    def _extract_total_count(self, payload: Any) -> int | None:
        if not isinstance(payload, dict):
            return None

        for key in ("total", "totalCount", "totalResults", "count", "numResults"):
            value = payload.get(key)
            if isinstance(value, int):
                return value

        return None

    def _extract_url(self, raw_job: dict[str, Any]) -> str | None:
        candidate = self._optional_string(
            raw_job,
            (
                "url",
                "jobUrl",
                "jobPostingUrl",
                "externalUrl",
                "externalApplyUrl",
                "externalPath",
                "jobPath",
                "path",
            ),
        )
        if not candidate:
            return None

        if candidate.startswith("http://") or candidate.startswith("https://"):
            return candidate

        return urljoin(self.base_url + "/", candidate)

    def _parse_employment_type(self, raw_job: dict[str, Any]) -> EmploymentType:
        value = self._optional_string(
            raw_job,
            ("employmentType", "jobType", "type", "employment"),
        )
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

    def _first_non_empty(
        self,
        raw_job: dict[str, Any],
        keys: tuple[str, ...],
    ) -> str | None:
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

    def _optional_string(
        self,
        raw_job: dict[str, Any],
        keys: tuple[str, ...],
    ) -> str | None:
        return self._first_non_empty(raw_job, keys)

    def _with_query_params(self, url: str, params: dict[str, str]) -> str:
        parsed = urlparse(url)
        existing_params = dict(parse_qsl(parsed.query, keep_blank_values=True))
        existing_params.update(params)
        return urlunparse(parsed._replace(query=urlencode(existing_params)))