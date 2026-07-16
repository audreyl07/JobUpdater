from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, List
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright
from app.scanners.base import BaseScanner, DataSource, ScanResult, ScannerError

from app.models.job import EmploymentType, NormalizedJob
from app.scanners.workday_discovery import WorkdayDiscovery, WorkdayEndpoint


class WorkdayScanner(BaseScanner):
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
        self._timeout_ms = timeout * 1000
        self._discovery = WorkdayDiscovery(timeout=timeout)

    def discover(self):
        parsed = urlparse(self.base_url)
        path = parsed.path.rstrip("/")

        if "/wday/cxs/" in path and path.endswith("/jobs"):
            return type(
                "Discovery",
                (),
                {
                    "source": DataSource.API,
                    "endpoint": self.base_url,
                    "details": {"discovered_from": "base_url", "method": "POST"},
                },
            )()

        endpoint: WorkdayEndpoint = self._discovery.discover(
            self.base_url,
            company=self.company_name,
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

    def _parse_tenant_site(self, url: str) -> tuple[str, str]:
        match = re.search(r"/wday/cxs/([^/]+)/([^/]+)/jobs", url, flags=re.IGNORECASE)
        if not match:
            return "", "Careers"
        return match.group(1), match.group(2)

    def fetch_jobs(self, discovery) -> List[dict[str, Any]]:
        """Fetch all jobs using pagination, via a single Playwright browser session."""
        endpoint = discovery.endpoint
        tenant, site = self._parse_tenant_site(endpoint)
        netloc = urlparse(endpoint).netloc

        jobs: List[dict[str, Any]] = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            # Warm up the session on the real careers page first
            page.goto(f"https://{netloc}/en-US/{site}", wait_until="networkidle", timeout=self._timeout_ms)

            offset = 0
            payload = self._request_json(page, endpoint, offset=offset)

            try:
                first_page_jobs = self._extract_jobs(payload)
                total = self._extract_total_count(payload)
            except Exception as exc:
                browser.close()
                raise ScannerError(str(exc)) from exc

            if not first_page_jobs:
                browser.close()
                raise ScannerError("Empty Workday response")

            jobs.extend(first_page_jobs)

            offset = self.page_size
            while offset < total:
                payload = self._request_json(page, endpoint, offset=offset)
                page_jobs = self._extract_jobs(payload)
                jobs.extend(page_jobs)
                offset += self.page_size

            browser.close()

        return jobs

    def _request_json(self, page, url: str, *, offset: int = 0) -> dict:
        try:
            response = page.request.post(
                url,
                data=json.dumps({
                    "appliedFacets": {},
                    "limit": self.page_size,
                    "offset": offset,
                    "searchText": "",
                }),
                headers={"Content-Type": "application/json"},
                timeout=self._timeout_ms,
            )

            if response.status != 200:
                raise ScannerError(
                    f"HTTP error while requesting Workday API: {response.status} {response.text()}"
                )

            try:
                return response.json()
            except ValueError as exc:
                raise ScannerError("Invalid JSON response from Workday API") from exc

        except ScannerError:
            raise
        except Exception as exc:
            raise ScannerError(f"Request error while requesting Workday API: {exc}") from exc

    def _extract_jobs(self, payload: dict[str, Any]) -> List[dict[str, Any]]:
        if "jobPostings" in payload:
            return payload["jobPostings"]
        raise ScannerError("Could not find a jobs list")

    def _extract_total_count(self, payload: dict[str, Any]) -> int:
        if "total" in payload:
            return int(payload["total"])
        raise ScannerError("Could not determine total job count")

    def normalize(self, raw: dict[str, Any]) -> NormalizedJob | None:
        """Convert raw Workday job (list-endpoint shape) into our NormalizedJob model."""
        print(json.dumps(raw, indent=2))
        external_path = raw.get("externalPath")
        title = raw.get("title")

        if not external_path or not title:
            return None

        # Job ID comes from bulletFields (typically the requisition number) or externalPath
        bullet_fields = raw.get("bulletFields") or []
        job_id = bullet_fields[0] if bullet_fields else external_path

        full_url = external_path
        if full_url.startswith("/"):
            netloc_base = self.base_url.split("/wday/cxs/")[0]
            full_url = f"{netloc_base}/en-US/{self._parse_tenant_site(self.base_url)[1]}{full_url}"

        location = raw.get("locationsText")

        # postedOn is a relative string like "Posted 6 Days Ago" — not a parseable date
        posted_at = None

        return NormalizedJob(
            job_id=job_id,
            company=self.company_name,
            title=title,
            location=location,
            url=full_url,
            description="",
            department="",
            posted_date=posted_at,
            employment_type=EmploymentType.UNKNOWN,
        )