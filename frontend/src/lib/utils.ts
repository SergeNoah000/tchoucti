import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Root domain the tenant subdomains hang off (e.g. myappsuite.com). Driven by
 *  NEXT_PUBLIC_ROOT_DOMAIN so dev shows `.localhost` and prod the real domain. */
export const ROOT_DOMAIN = (process.env.NEXT_PUBLIC_ROOT_DOMAIN || "myappsuite.com").toLowerCase();

/** Public host of a groupement: `{subdomain}.{rootDomain}`. */
export function groupementHost(g: { subdomain?: string | null; slug: string }): string {
  return `${g.subdomain || g.slug}.${ROOT_DOMAIN}`;
}

/** Canonical login URL for an association: `{protocol}//{groupement-subdomain}.{rootDomain}[:port]/a/{slug}`.
 *  Reads protocol + port from `window.location` so dev (localhost:13000) and prod
 *  (https://…) sortent toujours la bonne URL. SSR-safe : retourne null hors browser. */
export function associationLoginUrl(association: {
  slug: string;
  groupement_subdomain?: string | null;
}): string | null {
  if (typeof window === "undefined") return null;
  const sub = association.groupement_subdomain;
  if (!sub) return null;
  const port = window.location.port ? `:${window.location.port}` : "";
  return `${window.location.protocol}//${sub}.${ROOT_DOMAIN}${port}/a/${association.slug}`;
}

/** Format a number as XAF currency (Cameroon default), no decimals. */
export function formatCurrency(amount: number | string, currency = "XAF", locale = "fr-FR"): string {
  const n = typeof amount === "string" ? parseFloat(amount) : amount;
  if (Number.isNaN(n)) return "—";
  try {
    return new Intl.NumberFormat(locale, {
      style: "currency",
      currency,
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(n);
  } catch {
    return `${n.toLocaleString(locale)} ${currency}`;
  }
}

/** Format a date to a human-readable string. */
export function formatDate(date: string | Date, locale = "fr-FR"): string {
  const d = typeof date === "string" ? new Date(date) : date;
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(locale, { day: "2-digit", month: "short", year: "numeric" });
}

export function formatDateTime(date: string | Date, locale = "fr-FR"): string {
  const d = typeof date === "string" ? new Date(date) : date;
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString(locale, {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function initials(name?: string | null): string {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0]!.slice(0, 2).toUpperCase();
  return (parts[0]![0]! + parts[parts.length - 1]![0]!).toUpperCase();
}
