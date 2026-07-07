from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.models.job import EmploymentType
from app.scanners.base import DataSource, ScanResult, ScannerError
from app.scanners.workday import WorkdayScanner
from app.scanners.workday_discovery import DiscoveryAttemptStats, WorkdayDiscoveryError, WorkdayEndpoint


def test_discover_returns_base_url_when_already_jobs_endpoint() -> None:
    base_url = "https://example.wd5.myworkdayjobs.com/wday/cxs/acme/jobs"
    scanner = WorkdayScanner(
        company_name="Acme",
        base_url=base_url,
    )

    discovery = scanner.discover()

    assert discovery.source == DataSource.API
    assert discovery.endpoint == base_url
    assert discovery.details["discovered_from"] == "base_url"


def test_discover_finds_endpoint_from_html(monkeypatch: pytest.MonkeyPatch) -> None:
    scanner = WorkdayScanner(
        company_name="Acme",
        base_url="https://example.wd5.myworkdayjobs.com/Careers",
    )

    expected = "https://example.wd5.myworkdayjobs.com/wday/cxs/acme/jobs"

    monkeypatch.setattr(
        scanner._discovery,
        "discover",
        lambda *args, **kwargs: WorkdayEndpoint(
            url=expected,
            method="POST",
            tenant="acme",
            site="Careers",
        ),
    )

    discovery = scanner.discover()

    assert discovery.source == DataSource.API
    assert discovery.endpoint == expected
    assert discovery.details["discovered_from"] == "workday_discovery_v2"
    assert discovery.details["method"] == "POST"
    assert discovery.details["tenant"] == "acme"
    assert discovery.details["site"] == "Careers"


def test_fetch_jobs_paginates_all_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    scanner = WorkdayScanner(
        company_name="Acme",
        base_url="https://example.workday.com",
        page_size=2,
    )

    discovery = type(
        "Discovery",
        (),
        {
            "source": DataSource.API,
            "endpoint": "https://example.workday.com/wday/cxs/acme/jobs",
            "details": {"method": "GET"},
        },
    )()

    requested_urls: list[str] = []

    def fake_request_json(url: str, *, method: str = "GET", offset: int = 0) -> dict[str, Any]:
        requested_urls.append(url)
        query = parse_qs(urlparse(url).query)
        offset = int(query["offset"][0])

        if offset == 0:
            return {
                "jobPostings": [
                    {"job_id": "1", "title": "Engineer I", "location": "Remote", "url": "/job/1"},
                    {"job_id": "2", "title": "Engineer II", "location": "Remote", "url": "/job/2"},
                ],
                "totalCount": 3,
            }

        return {
            "jobPostings": [
                {"job_id": "3", "title": "Engineer III", "location": "Remote", "url": "/job/3"},
            ],
            "totalCount": 3,
        }

    monkeypatch.setattr(scanner, "_request_json", fake_request_json)
    monkeypatch.setattr(scanner, "_extract_jobs", lambda payload: payload["jobPostings"], raising=False)
    monkeypatch.setattr(scanner, "_extract_total_count", lambda payload: payload["totalCount"], raising=False)

    jobs = scanner.fetch_jobs(discovery)

    assert len(jobs) == 3
    assert len(requested_urls) == 2
    assert "offset=0" in requested_urls[0]
    assert "offset=2" in requested_urls[1]
    assert all("limit=2" in url for url in requested_urls)


def test_fetch_jobs_raises_on_empty_first_page(monkeypatch: pytest.MonkeyPatch) -> None:
    scanner = WorkdayScanner(
        company_name="Acme",
        base_url="https://example.workday.com",
    )

    discovery = type(
        "Discovery",
        (),
        {
            "source": DataSource.API,
            "endpoint": "https://example.workday.com/wday/cxs/acme/jobs",
            "details": {"method": "GET"},
        },
    )()

    monkeypatch.setattr(scanner, "_request_json", lambda url, **kwargs: {"jobPostings": []})
    monkeypatch.setattr(scanner, "_extract_jobs", lambda payload: [], raising=False)
    monkeypatch.setattr(scanner, "_extract_total_count", lambda payload: 0, raising=False)

    with pytest.raises(ScannerError, match="Empty Workday response"):
        scanner.fetch_jobs(discovery)


def test_normalize_converts_raw_job() -> None:
    scanner = WorkdayScanner(
        company_name="Acme",
        base_url="https://example.workday.com",
    )

    raw_job = {
        "job_id": "REQ-123",
        "title": "Senior Python Engineer",
        "location": "Ottawa, Canada",
        "jobUrl": "/wday/cxs/acme/jobs/REQ-123",
        "description": "<p>Build job monitoring tools.</p>",
        "department": "Engineering",
        "postedDate": "2026-01-02T03:04:05Z",
        "employmentType": "Regular Full-Time",
    }

    job = scanner.normalize(raw_job)

    assert job is not None
    assert job.job_id == "REQ-123"
    assert job.company == "Acme"
    assert job.title == "Senior Python Engineer"
    assert job.location == "Ottawa, Canada"
    assert job.url == "https://example.workday.com/wday/cxs/acme/jobs/REQ-123"
    assert job.employment_type == EmploymentType.FULL_TIME
    assert job.posted_date == datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def test_scan_orchestrates_discover_fetch_and_normalize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanner = WorkdayScanner(
        company_name="Acme",
        base_url="https://example.workday.com",
    )

    endpoint = WorkdayEndpoint(
        url="https://example.workday.com/wday/cxs/acme/jobs",
        method="GET",
        tenant="acme",
        site="Careers",
    )

    raw_jobs = [
        {
            "job_id": "REQ-1",
            "title": "Python Engineer",
            "location": "Remote",
            "url": "/wday/cxs/acme/jobs/REQ-1",
        }
    ]

    monkeypatch.setattr(scanner._discovery, "discover", lambda *args, **kwargs: endpoint)
    monkeypatch.setattr(scanner, "fetch_jobs", lambda discovery: raw_jobs)
    monkeypatch.setattr(scanner, "normalize", lambda raw: "parsed")

    result = scanner.scan("Acme", "https://example.workday.com")

    assert isinstance(result, ScanResult)
    assert result.company == "Acme"
    assert result.jobs == ["parsed"]
    assert result.raw_count == 1


def test_request_json_raises_on_invalid_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanner = WorkdayScanner(
        company_name="Acme",
        base_url="https://example.workday.com",
    )

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        @property
        def content(self) -> bytes:
            return b"{invalid json"

        def json(self) -> Any:
            raise ValueError("Invalid JSON")

    monkeypatch.setattr(scanner._client, "get", lambda url, **kwargs: FakeResponse())

    with pytest.raises(ScannerError, match="Invalid JSON"):
        scanner._request_json("https://example.workday.com/wday/cxs/acme/jobs")


def test_discover_raises_when_no_endpoint_is_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanner = WorkdayScanner(
        company_name="Acme",
        base_url="https://example.workday.com",
    )

    monkeypatch.setattr(
        scanner._discovery,
        "discover",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            WorkdayDiscoveryError(
                company="Acme",
                url=scanner.base_url,
                attempts=DiscoveryAttemptStats(html_parsing="completed", candidate_endpoints_tested=3),
                reason="No candidate endpoint returned a valid Workday jobs JSON response",
            )
        ),
    )

    with pytest.raises(WorkdayDiscoveryError, match="No candidate endpoint returned"):
        scanner.discover()


def test_request_json_raises_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    scanner = WorkdayScanner(
        company_name="Acme",
        base_url="https://example.workday.com",
    )

    def fake_get(url: str, **kwargs: Any) -> Any:
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(scanner._client, "get", fake_get)

    with pytest.raises(ScannerError, match="Timeout while requesting"):
        scanner._request_json("https://example.workday.com/wday/cxs/acme/jobs")


def test_request_json_raises_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    scanner = WorkdayScanner(
        company_name="Acme",
        base_url="https://example.workday.com",
    )

    request = httpx.Request("GET", "https://example.workday.com/wday/cxs/acme/jobs")
    response = httpx.Response(status_code=500, request=request)

    class FakeResponse:
        def raise_for_status(self) -> None:
            raise httpx.HTTPStatusError("server error", request=request, response=response)

        @property
        def content(self) -> bytes:
            return b"{}"

        def json(self) -> Any:
            return {}

    monkeypatch.setattr(scanner._client, "get", lambda url, **kwargs: FakeResponse())

    with pytest.raises(ScannerError, match="HTTP error while requesting"):
        scanner._request_json("https://example.workday.com/wday/cxs/acme/jobs")


def test_request_json_raises_on_empty_response(monkeypatch: pytest.MonkeyPatch) -> None:
    scanner = WorkdayScanner(
        company_name="Acme",
        base_url="https://example.workday.com",
    )

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        @property
        def content(self) -> bytes:
            return b""

        def json(self) -> Any:
            return {}

    monkeypatch.setattr(scanner._client, "get", lambda url, **kwargs: FakeResponse())

    with pytest.raises(ScannerError, match="Empty JSON response"):
        scanner._request_json("https://example.workday.com/wday/cxs/acme/jobs")


def test_fetch_jobs_raises_on_unexpected_payload_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanner = WorkdayScanner(
        company_name="Acme",
        base_url="https://example.workday.com",
    )

    discovery = type(
        "Discovery",
        (),
        {
            "source": DataSource.API,
            "endpoint": "https://example.workday.com/wday/cxs/acme/jobs",
            "details": {"method": "GET"},
        },
    )()

    monkeypatch.setattr(scanner, "_request_json", lambda url, **kwargs: {"unexpected": []})
    monkeypatch.setattr(
        scanner,
        "_extract_jobs",
        lambda payload: (_ for _ in ()).throw(ScannerError("Could not find a jobs list")),
        raising=False,
    )
    monkeypatch.setattr(scanner, "_extract_total_count", lambda payload: None, raising=False)

    with pytest.raises(ScannerError, match="Could not find a jobs list"):
        scanner.fetch_jobs(discovery)


def test_normalize_returns_none_for_malformed_job() -> None:
    scanner = WorkdayScanner(
        company_name="Acme",
        base_url="https://example.workday.com",
    )

    raw_job = {
        "title": "",
        "location": "Remote",
        "url": "",
    }

    assert scanner.normalize(raw_job) is None