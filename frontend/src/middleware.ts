import { NextResponse, type NextRequest } from "next/server";

/**
 * Tenant middleware — resolves the tenant from the host header.
 *
 *  admin.{rootDomain}       → platform admin space  (rewrites to /admin/...)
 *  {slug}.{rootDomain}      → groupement space      (sets x-tenant-slug header)
 *  {rootDomain}             → public landing
 *
 * Headers set for downstream pages / API client:
 *   x-tenant-slug      — the resolved groupement slug (if any)
 *   x-tenant-admin     — "1" if platform admin host
 *   x-tenant-host      — the raw host
 */
const ROOT_DOMAIN = (process.env.NEXT_PUBLIC_ROOT_DOMAIN || "localhost").toLowerCase();

function resolveTenant(host: string): { isAdmin: boolean; slug: string | null } {
  // Strip :port
  const h = host.split(":")[0]?.toLowerCase() || "";
  // Exactly the root domain → no tenant
  if (h === ROOT_DOMAIN || h === `www.${ROOT_DOMAIN}`) {
    return { isAdmin: false, slug: null };
  }
  // Has a subdomain
  if (h.endsWith(`.${ROOT_DOMAIN}`)) {
    const sub = h.slice(0, -1 - ROOT_DOMAIN.length); // "admin" or "demo" etc.
    const first = sub.split(".")[0] || "";
    if (first === "admin") return { isAdmin: true, slug: null };
    if (first === "www" || !first) return { isAdmin: false, slug: null };
    return { isAdmin: false, slug: first };
  }
  // Foreign host (custom domain mapped later) — for now treat as root
  return { isAdmin: false, slug: null };
}

export function middleware(req: NextRequest) {
  const host = req.headers.get("host") || "";
  const { isAdmin, slug } = resolveTenant(host);

  const url = req.nextUrl.clone();
  const pathname = url.pathname;

  // Skip static / api / _next
  if (
    pathname.startsWith("/_next") ||
    pathname.startsWith("/api") ||
    pathname.startsWith("/favicon") ||
    pathname.startsWith("/icon") ||
    pathname.includes(".")
  ) {
    return NextResponse.next();
  }

  const requestHeaders = new Headers(req.headers);
  requestHeaders.set("x-tenant-host", host);
  if (slug) requestHeaders.set("x-tenant-slug", slug);
  if (isAdmin) requestHeaders.set("x-tenant-admin", "1");

  // Rewrite rules so URL stays clean for the user
  //   admin.{root}/anything   →  /admin/anything (under the hood)
  //   {slug}.{root}/anything  →  /(tenant)/anything (under the hood)
  if (isAdmin && !pathname.startsWith("/admin")) {
    url.pathname = `/admin${pathname === "/" ? "" : pathname}`;
    return NextResponse.rewrite(url, { request: { headers: requestHeaders } });
  }
  if (slug && !pathname.startsWith("/t/")) {
    // We keep tenant pages flat (no "/t/slug" in URL). The downstream layout
    // reads the x-tenant-slug header to know which groupement to load.
  }

  return NextResponse.next({ request: { headers: requestHeaders } });
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|icon.svg).*)"],
};
