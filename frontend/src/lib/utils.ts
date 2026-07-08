import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Domaine racine sur lequel pendent les sous-domaines des tenants.
 *  Priorité : NEXT_PUBLIC_ROOT_DOMAIN si défini ; SINON on prend le DOMAINE RÉEL
 *  sur lequel l'app est servie (au lieu de fixer « myappsuite.com »), en
 *  retirant le sous-domaine courant (ex. admin.exemple.com → exemple.com). */
export function rootDomain(): string {
  const env = process.env.NEXT_PUBLIC_ROOT_DOMAIN;
  if (env) return env.toLowerCase();
  if (typeof window !== "undefined") {
    const h = window.location.hostname.toLowerCase();
    if (h === "localhost" || /^\d+(\.\d+){3}$/.test(h)) return h;
    const parts = h.split(".");
    // exemple.com → exemple.com ; admin.exemple.com → exemple.com.
    return parts.length > 2 ? parts.slice(-2).join(".") : h;
  }
  return "myappsuite.com";
}

/** @deprecated Utilise rootDomain() (dynamique). Conservé pour compat. */
export const ROOT_DOMAIN = (process.env.NEXT_PUBLIC_ROOT_DOMAIN || "myappsuite.com").toLowerCase();

/** Public host of a groupement: `{subdomain}.{rootDomain}`. */
export function groupementHost(g: { subdomain?: string | null; slug: string }): string {
  return `${g.subdomain || g.slug}.${rootDomain()}`;
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
  return `${window.location.protocol}//${sub}.${rootDomain()}${port}/a/${association.slug}`;
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
