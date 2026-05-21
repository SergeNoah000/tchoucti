"""Tenant resolution from subdomain.

Strategy:
  admin.{base}         → SuperAdmin platform context (no groupement)
  {slug}.{base}        → Groupement(slug=...)
  Other / unknown      → no tenant (public routes only)
"""
from dataclasses import dataclass
from typing import Optional

from app.core.config import settings


@dataclass
class TenantContext:
    is_platform_admin: bool = False
    groupement_slug: Optional[str] = None
    raw_host: Optional[str] = None

    @property
    def is_groupement(self) -> bool:
        return self.groupement_slug is not None

    @property
    def is_public(self) -> bool:
        return not self.is_platform_admin and not self.is_groupement


def parse_host(host: Optional[str]) -> TenantContext:
    """Extract tenant info from a `Host` header.

    Examples (APP_BASE_DOMAIN=localhost):
        admin.localhost:3000   → platform_admin
        demo.localhost:3000    → groupement_slug=demo
        localhost:3000         → public

    Production (APP_BASE_DOMAIN=tchoucti.com):
        admin.tchoucti.com         → platform_admin
        groupement-a.tchoucti.com  → groupement_slug=groupement-a
        tchoucti.com               → public (landing)
    """
    if not host:
        return TenantContext(raw_host=host)

    # Strip port
    hostname = host.split(":", 1)[0].lower()

    base = settings.APP_BASE_DOMAIN.lower()
    admin_sub = settings.PLATFORM_ADMIN_SUBDOMAIN.lower()

    # Direct match on base domain → public
    if hostname == base:
        return TenantContext(raw_host=host)

    suffix = "." + base
    if not hostname.endswith(suffix):
        # Unknown domain
        return TenantContext(raw_host=host)

    subdomain = hostname[: -len(suffix)]

    # Sub-subdomain (e.g. assoc.groupement.tchoucti.com) → take the LAST level as groupement
    if "." in subdomain:
        # For now, we only support 1-level subdomains for tenant resolution.
        # The path /a/{assoc} is used for associations.
        subdomain = subdomain.rsplit(".", 1)[-1]

    if subdomain == admin_sub:
        return TenantContext(is_platform_admin=True, raw_host=host)

    return TenantContext(groupement_slug=subdomain, raw_host=host)
