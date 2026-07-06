from __future__ import annotations

from types import SimpleNamespace

from app.runner import run_scanner


class DummyScanner:
    """Minimal scanner double for runner tests."""

    def __init__(self) -> None:
        self.company_name = "Acme"
        self.scan_called = False

    def scan(self) -> SimpleNamespace:
        self.scan_called = True
        return SimpleNamespace(company="Acme", jobs=[], raw_count=0)


def test_run_scanner_delegates_to_scan() -> None:
    scanner = DummyScanner()

    result = run_scanner(scanner)

    assert scanner.scan_called is True
    assert result.company == "Acme"
    assert result.raw_count == 0