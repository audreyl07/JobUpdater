from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.company import Company


@dataclass(slots=True)
class CompanyRepository:
    """Repository for company persistence operations."""

    session: Session

    def get_by_id(self, company_id: int) -> Company | None:
        return self.session.get(Company, company_id)

    def get_by_name(self, name: str) -> Company | None:
        stmt = select(Company).where(Company.name == name)
        return self.session.scalar(stmt)

    def list_active(self) -> list[Company]:
        stmt = select(Company).where(Company.active.is_(True)).order_by(Company.name.asc())
        return list(self.session.scalars(stmt).all())

    def create(
        self,
        *,
        name: str,
        scanner_type: str,
        careers_url: str,
        active: bool = True,
    ) -> Company:
        company = Company(
            name=name,
            scanner_type=scanner_type,
            careers_url=careers_url,
            active=active,
        )
        self.session.add(company)
        self.session.flush()
        return company

    def update(
        self,
        company: Company,
        *,
        name: str | None = None,
        scanner_type: str | None = None,
        careers_url: str | None = None,
        active: bool | None = None,
    ) -> Company:
        if name is not None:
            company.name = name
        if scanner_type is not None:
            company.scanner_type = scanner_type
        if careers_url is not None:
            company.careers_url = careers_url
        if active is not None:
            company.active = active

        self.session.flush()
        return company