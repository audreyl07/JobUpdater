from __future__ import annotations

from types import SimpleNamespace

import main as main_module


def test_parse_args_parses_cli_arguments(monkeypatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "main.py",
            "Acme",
            "https://example.workday.com/wday/cxs/acme/jobs",
            "--page-size",
            "25",
            "--timeout",
            "12.5",
        ],
    )

    args = main_module.parse_args()

    assert args.company_name == "Acme"
    assert args.base_url == "https://example.workday.com/wday/cxs/acme/jobs"
    assert args.page_size == 25
    assert args.timeout == 12.5


def test_main_wires_scanner_and_runner(monkeypatch, capsys) -> None:
    created = {}

    def fake_parse_args() -> SimpleNamespace:
        return SimpleNamespace(
            company_name="Acme",
            base_url="https://example.workday.com/wday/cxs/acme/jobs",
            page_size=25,
            timeout=12.5,
        )

    class FakeScanner:
        def __init__(
            self,
            company_name: str,
            base_url: str,
            timeout: float,
            page_size: int,
        ) -> None:
            created["company_name"] = company_name
            created["base_url"] = base_url
            created["timeout"] = timeout
            created["page_size"] = page_size
            self.company_name = company_name

    fake_result = SimpleNamespace(company="Acme", jobs=[object(), object()], raw_count=2)

    monkeypatch.setattr(main_module, "parse_args", fake_parse_args)
    monkeypatch.setattr(main_module, "WorkdayScanner", FakeScanner)
    monkeypatch.setattr(main_module, "run_scanner", lambda scanner: fake_result)

    exit_code = main_module.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    assert created == {
        "company_name": "Acme",
        "base_url": "https://example.workday.com/wday/cxs/acme/jobs",
        "timeout": 12.5,
        "page_size": 25,
    }
    assert "Acme: 2 jobs found" in captured.out