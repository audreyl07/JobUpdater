from __future__ import annotations

import httpx
import pytest

from app.scanners.workday_discovery import WorkdayDiscovery, WorkdayDiscoveryError


def test_html_contains_workday_endpoint() -> None:
    html = """
    <html>
      <script>
        window.__WORKDAY_CONFIG__ = {
          "tenant": "ciena",
          "site": "Careers",
          "apiPath": "/wday/cxs/ciena/Careers/jobs"
        };
      </script>
    </html>
    """

    discovery = WorkdayDiscovery()
    metadata = discovery.extract_html_metadata(html)

    assert "ciena" in metadata.tenant_candidates
    assert "Careers" in metadata.site_candidates
    assert "/wday/cxs/ciena/Careers/jobs" in metadata.endpoint_urls


def test_only_guessed_endpoint_works() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/Careers":
            return httpx.Response(200, text="<html>Career Site</html>", request=request)

        if request.url.path == "/wday/cxs/ciena/Careers/jobs" and request.method == "GET":
            return httpx.Response(404, json={"error": "not found"}, request=request)

        if request.url.path == "/wday/cxs/ciena/Careers/jobs" and request.method == "POST":
            return httpx.Response(
                200,
                json={"jobPostings": [{"title": "Engineer", "jobId": "1"}]},
                request=request,
            )

        return httpx.Response(404, json={"error": "not found"}, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    discovery = WorkdayDiscovery()

    endpoint = discovery.discover("https://ciena.wd5.myworkdayjobs.com/Careers", company="ciena", client=client)

    assert endpoint.url.endswith("/wday/cxs/ciena/Careers/jobs")
    assert endpoint.method == "POST"
    assert endpoint.tenant == "ciena"
    assert endpoint.site == "Careers"


def test_get_fails_but_post_succeeds() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/Careers":
            return httpx.Response(
                200,
                text='<html><script>var x={"tenant":"ciena","site":"Careers"}</script></html>',
                request=request,
            )

        if request.url.path == "/wday/cxs/ciena/Careers/jobs" and request.method == "GET":
            return httpx.Response(200, text="<html>Login</html>", headers={"content-type": "text/html"}, request=request)

        if request.url.path == "/wday/cxs/ciena/Careers/jobs" and request.method == "POST":
            return httpx.Response(
                200,
                json={"total": 1, "jobPostings": [{"title": "Engineer", "jobId": "1"}]},
                request=request,
            )

        return httpx.Response(404, json={"error": "not found"}, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    discovery = WorkdayDiscovery()

    endpoint = discovery.discover("https://ciena.wd5.myworkdayjobs.com/Careers", company="ciena", client=client)

    assert endpoint.method == "POST"
    assert endpoint.url.endswith("/wday/cxs/ciena/Careers/jobs")


def test_no_endpoint_exists_raises_clear_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/Careers":
            return httpx.Response(200, text="<html>No Workday metadata here</html>", request=request)
        return httpx.Response(404, json={"error": "not found"}, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    discovery = WorkdayDiscovery()

    with pytest.raises(WorkdayDiscoveryError) as exc:
        discovery.discover("https://ciena.wd5.myworkdayjobs.com/Careers", company="ciena", client=client)

    message = str(exc.value)
    assert "Company:" in message
    assert "ciena" in message
    assert "Candidate endpoints tested:" in message
    assert "Reason:" in message