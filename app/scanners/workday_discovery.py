from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from html import unescape
from typing import Any, Iterable
from urllib.parse import quote, urlparse

import httpx

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class WorkdayEndpoint:
    """Resolved Workday API endpoint."""

    url: str
    method: str
    tenant: str
    site: str


@dataclass(slots=True)
class WorkdayHTMLMetadata:
    """Metadata extracted from a Workday career page HTML document."""

    tenant_candidates: list[str] = field(default_factory=list)
    site_candidates: list[str] = field(default_factory=list)
    api_paths: list[str] = field(default_factory=list)
    endpoint_urls: list[str] = field(default_factory=list)
    raw_snippets: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DiscoveryAttemptStats:
    """Diagnostic counters for Workday discovery."""

    html_parsing: str = "pending"
    candidate_endpoints_tested: int = 0
    get_attempts_failed: int = 0
    post_attempts_succeeded: int = 0

    def summary(self) -> str:
        return (
            f"HTML parsing: {self.html_parsing}\n"
            f"Candidate endpoints tested: {self.candidate_endpoints_tested}\n"
            f"GET attempts failed: {self.get_attempts_failed}\n"
            f"POST attempts succeeded: {self.post_attempts_succeeded}"
        )


class WorkdayDiscoveryError(RuntimeError):
    """Raised when Workday endpoint discovery fails."""

    def __init__(
        self,
        *,
        company: str,
        url: str,
        attempts: DiscoveryAttemptStats,
        reason: str,
    ) -> None:
        self.company = company
        self.url = url
        self.attempts = attempts
        self.reason = reason
        super().__init__(self._build_message())

    def _build_message(self) -> str:
        return (
            "WorkdayDiscoveryError:\n"
            f"Company:\n{self.company}\n\n"
            f"URL:\n{self.url}\n\n"
            f"Attempts:\n{self.attempts.summary()}\n\n"
            f"Reason:\n{self.reason}"
        )


class WorkdayDiscovery:
    """Discover a usable Workday jobs API endpoint from a career site."""

    def __init__(self, *, timeout: float = 15.0) -> None:
        self._timeout = timeout

    def discover(
        self,
        url: str,
        *,
        company: str | None = None,
        client: httpx.Client | None = None,
    ) -> WorkdayEndpoint:
        """Discover a working Workday endpoint for a career page."""
        logger.info("Starting Workday discovery")
        attempts = DiscoveryAttemptStats()

        own_client = client is None
        http_client = client or httpx.Client(timeout=self._timeout, follow_redirects=True)

        try:
            try:
                html = self._fetch_html(http_client, url)
                attempts.html_parsing = "completed"
            except httpx.HTTPError as exc:
                logger.warning("Career page fetch failed; continuing with heuristics url=%s error=%s", url, exc)
                html = ""
                attempts.html_parsing = "failed"

            metadata = self.extract_html_metadata(html) if html else WorkdayHTMLMetadata()

            tenant_candidates = self._tenant_candidates(url, metadata)
            site_candidates = self._site_candidates(url, metadata)
            candidates = list(self.generate_candidates(url, tenant_candidates, site_candidates, metadata))

            for candidate in candidates:
                attempts.candidate_endpoints_tested += 1
                logger.debug("Generated candidate: %s", candidate.url)

                result = self.probe_endpoint(http_client, candidate)
                if result is not None:
                    if result.method == "POST":
                        attempts.post_attempts_succeeded += 1

                    logger.info("Valid Workday API discovered: %s", result.url)
                    return result

                attempts.get_attempts_failed += 1
                logger.warning("Candidate rejected: %s", candidate.url)

            raise WorkdayDiscoveryError(
                company=company or self._company_from_url(url),
                url=url,
                attempts=attempts,
                reason="No candidate endpoint returned a valid Workday jobs JSON response",
            )
        finally:
            if own_client:
                http_client.close()

    def extract_html_metadata(self, html: str) -> WorkdayHTMLMetadata:
        """Extract Workday-related metadata from career-page HTML."""
        text = unescape(html)

        metadata = WorkdayHTMLMetadata()

        endpoint_patterns = [
            r"https?://[^\s\"'<>]+/wday/cxs/[^\s\"'<>]+/jobs[^\s\"'<>]*",
            r"/wday/cxs/[^\s\"'<>]+/jobs[^\s\"'<>]*",
        ]
        for pattern in endpoint_patterns:
            for match in re.findall(pattern, text, flags=re.IGNORECASE):
                cleaned = match.strip().rstrip('",\'')
                if cleaned not in metadata.endpoint_urls:
                    metadata.endpoint_urls.append(cleaned)

        tenant_patterns = [
            r'"tenant"\s*:\s*"([^"]+)"',
            r"'tenant'\s*:\s*'([^']+)'",
            r'"tenantId"\s*:\s*"([^"]+)"',
            r"'tenantId'\s*:\s*'([^']+)'",
            r"/wday/cxs/([^/]+)/",
        ]
        for pattern in tenant_patterns:
            for match in re.findall(pattern, text, flags=re.IGNORECASE):
                if match and match not in metadata.tenant_candidates:
                    metadata.tenant_candidates.append(match)

        site_patterns = [
            r'"site"\s*:\s*"([^"]+)"',
            r"'site'\s*:\s*'([^']+)'",
            r'"siteId"\s*:\s*"([^"]+)"',
            r"'siteId'\s*:\s*'([^']+)'",
            r"/wday/cxs/[^/]+/([^/]+)/jobs",
        ]
        for pattern in site_patterns:
            for match in re.findall(pattern, text, flags=re.IGNORECASE):
                if match and match not in metadata.site_candidates:
                    metadata.site_candidates.append(match)

        path_patterns = [
            r'"/wday/cxs/[^"]+"',
            r"'/wday/cxs/[^']+'",
            r'"/wday/cxs/[^"]+/jobs"',
            r"'/wday/cxs/[^']+/jobs'",
        ]
        for pattern in path_patterns:
            for match in re.findall(pattern, text, flags=re.IGNORECASE):
                path = match.strip('"\'')
                if path not in metadata.api_paths:
                    metadata.api_paths.append(path)

        # Keep a few snippets for debugging.
        for needle in ("/wday/cxs/", "jobPostings", "jobs", "tenant", "site"):
            if needle.lower() in text.lower():
                idx = text.lower().find(needle.lower())
                snippet = text[max(0, idx - 120) : idx + 220]
                metadata.raw_snippets.append(snippet)
                if len(metadata.raw_snippets) >= 5:
                    break

        return metadata

    def generate_candidates(
        self,
        career_url: str,
        tenant_candidates: Iterable[str],
        site_candidates: Iterable[str],
        metadata: WorkdayHTMLMetadata,
    ) -> Iterable[WorkdayEndpoint]:
        """Generate Workday endpoint candidates from metadata and URL heuristics."""
        parsed = urlparse(career_url)
        host = parsed.netloc
        base = f"{parsed.scheme}://{host}"

        tenants = self._unique([
            *tenant_candidates,
            self._tenant_from_host(host),
            self._tenant_from_path(parsed.path),
        ])
        sites = self._unique([
            *site_candidates,
            self._site_from_path(parsed.path),
            "Careers",
            "careers",
        ])

        endpoint_urls = self._unique(metadata.endpoint_urls)

        seen: set[tuple[str, str, str, str]] = set()

        # Directly discovered URLs from HTML.
        for endpoint_url in endpoint_urls:
            full_url = self._normalize_endpoint_url(base, endpoint_url)
            for method in ("GET", "POST"):
                item = WorkdayEndpoint(
                    url=full_url,
                    method=method,
                    tenant=self._tenant_from_endpoint(full_url) or tenants[0],
                    site=self._site_from_endpoint(full_url) or sites[0],
                )
                key = (item.url, item.method, item.tenant, item.site)
                if key not in seen:
                    seen.add(key)
                    yield item

        # Heuristic candidates.
        for tenant in tenants:
            for site in sites:
                for variant in self._site_variants(site):
                    url = f"{base}/wday/cxs/{tenant}/{variant}/jobs"
                    for method in ("GET", "POST"):
                        item = WorkdayEndpoint(url=url, method=method, tenant=tenant, site=site)
                        key = (item.url, item.method, item.tenant, item.site)
                        if key not in seen:
                            seen.add(key)
                            yield item

    def probe_endpoint(self, client: httpx.Client, candidate: WorkdayEndpoint) -> WorkdayEndpoint | None:
        """Probe a candidate endpoint with GET, then POST."""
        response = self._request(client, candidate.url, "GET")
        if self.validate_response(response):
            return WorkdayEndpoint(
                url=candidate.url,
                method="GET",
                tenant=candidate.tenant,
                site=candidate.site,
            )

        response = self._request(
            client,
            candidate.url,
            "POST",
            json={"limit": 1, "offset": 0},
        )
        if self.validate_response(response):
            return WorkdayEndpoint(
                url=candidate.url,
                method="POST",
                tenant=candidate.tenant,
                site=candidate.site,
            )

        return None

    def validate_response(self, response: httpx.Response) -> bool:
        """Validate that the response is a usable Workday jobs JSON payload."""
        if response.status_code != 200:
            return False

        content_type = response.headers.get("content-type", "").lower()
        text = response.text.strip()
        if not text:
            return False

        if "<html" in text.lower() or "login" in text.lower():
            return False

        if "json" not in content_type and not self._looks_like_json(text):
            return False

        try:
            payload = response.json()
        except (json.JSONDecodeError, ValueError):
            return False

        if self._looks_like_error_payload(payload):
            return False

        return self._contains_job_fields(payload)

    def _fetch_html(self, client: httpx.Client, url: str) -> str:
        response = client.get(url, headers={"Accept": "text/html,application/xhtml+xml"})
        response.raise_for_status()
        return response.text

    def _request(
        self,
        client: httpx.Client,
        url: str,
        method: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        logger.debug("Probing Workday endpoint: %s %s", method, url)
        if method == "GET":
            return client.get(url, headers=headers)
        return client.post(url, headers=headers, json=json)

    def _contains_job_fields(self, payload: Any) -> bool:
        if isinstance(payload, dict):
            keys = {str(key).lower() for key in payload.keys()}
            if keys.intersection({"jobs", "jobpostings", "postings", "job_postings", "data"}):
                return True
            for value in payload.values():
                if self._contains_job_fields(value):
                    return True
            return False

        if isinstance(payload, list):
            if not payload:
                return False
            for item in payload:
                if isinstance(item, dict):
                    keys = {str(key).lower() for key in item.keys()}
                    if keys.intersection({"title", "jobid", "job_id", "externalid", "postedate", "location"}):
                        return True
                    if "job" in keys or "posting" in keys:
                        return True
            return False

        return False

    def _looks_like_error_payload(self, payload: Any) -> bool:
        if isinstance(payload, dict):
            keys = {str(key).lower() for key in payload.keys()}
            return bool(keys.intersection({"error", "errors", "message", "messages", "loginurl"}))
        return False

    def _looks_like_json(self, text: str) -> bool:
        return text.startswith("{") or text.startswith("[")

    def _normalize_endpoint_url(self, base: str, endpoint_url: str) -> str:
        if endpoint_url.startswith("http://") or endpoint_url.startswith("https://"):
            return endpoint_url
        return base.rstrip("/") + "/" + endpoint_url.lstrip("/")

    def _tenant_candidates(self, career_url: str, metadata: WorkdayHTMLMetadata) -> list[str]:
        parsed = urlparse(career_url)
        items = [*metadata.tenant_candidates, self._tenant_from_host(parsed.netloc), self._tenant_from_path(parsed.path)]
        return self._unique([item for item in items if item])

    def _site_candidates(self, career_url: str, metadata: WorkdayHTMLMetadata) -> list[str]:
        parsed = urlparse(career_url)
        items = [*metadata.site_candidates, self._site_from_path(parsed.path)]
        return self._unique([item for item in items if item])

    def _tenant_from_host(self, host: str) -> str:
        left = host.split(".")[0]
        if left and left.lower().startswith("wd"):
            return ""
        if ".wd" in host:
            return host.split(".wd", 1)[0]
        return left

    def _tenant_from_path(self, path: str) -> str:
        parts = [p for p in path.split("/") if p]
        return parts[0] if parts else ""

    def _site_from_path(self, path: str) -> str:
        parts = [p for p in path.split("/") if p]
        return parts[-1] if parts else "Careers"

    def _site_variants(self, site: str) -> list[str]:
        variants = [
            site,
            site.lower(),
            quote(site, safe=""),
            quote(site.lower(), safe=""),
        ]
        return self._unique(variants)

    def _tenant_from_endpoint(self, url: str) -> str:
        match = re.search(r"/wday/cxs/([^/]+)/", url, flags=re.IGNORECASE)
        return match.group(1) if match else ""

    def _site_from_endpoint(self, url: str) -> str:
        match = re.search(r"/wday/cxs/[^/]+/([^/]+)/jobs", url, flags=re.IGNORECASE)
        return match.group(1) if match else ""

    def _company_from_url(self, url: str) -> str:
        parsed = urlparse(url)
        host = parsed.netloc
        return host.split(".")[0]

    def _unique(self, items: Iterable[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in items:
            if not item:
                continue
            if item not in seen:
                seen.add(item)
                result.append(item)
        return result