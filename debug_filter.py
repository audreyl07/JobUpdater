from app.config.loader import ConfigLoader
from app.scanners.manager import ScannerManager
from app.scanners.workday import WorkdayScanner
from pathlib import Path

config = ConfigLoader().load(Path("config/companies.yaml"))
scanner_factories = {
    "workday": lambda company: WorkdayScanner(
        company_name=company.name,
        base_url=company.url,
        page_size=20,
        timeout=30.0,
    )
}
manager = ScannerManager(scanner_factories)
jobs = manager.run(config)

job = jobs[0]
print(type(job))
print(job)
print(vars(job) if hasattr(job, "__dict__") else "no __dict__ (maybe slots?)")
print("location:", repr(getattr(job, "location", "<MISSING>")))
print("employment_type:", repr(getattr(job, "employment_type", "<MISSING>")))
