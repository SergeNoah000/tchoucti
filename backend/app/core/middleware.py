"""Tenant middleware: resolves subdomain → tenant context attached to request.state."""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.tenant import parse_host


class TenantMiddleware(BaseHTTPMiddleware):
    """Attach a `TenantContext` to every request.

    Frontends address the API in two ways:
      1) Same-origin via Nginx (preferred) — host = groupement.tchoucti.com
      2) Direct dev calls — host = localhost:18000 → public (no tenant)

    Endpoints can either:
      - Be tenant-aware (use deps `RequireGroupement`)
      - Or ignore the tenant (public endpoints, super-admin endpoints)
    """

    async def dispatch(self, request: Request, call_next):
        host = request.headers.get("host") or request.headers.get("x-forwarded-host")
        # Allow explicit override via `X-Tenant-Slug` (handy in dev / mobile clients).
        override = request.headers.get("x-tenant-slug")
        if override:
            from app.core.tenant import TenantContext
            ctx = TenantContext(groupement_slug=override.lower(), raw_host=host)
        else:
            ctx = parse_host(host)
        request.state.tenant = ctx
        response = await call_next(request)
        return response
