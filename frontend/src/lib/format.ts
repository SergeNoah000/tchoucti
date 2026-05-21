import { useLocale } from "next-intl";

const LOCALE_MAP: Record<string, string> = {
  fr: "fr-FR",
  en: "en-US",
  de: "de-DE",
};

function toIntlLocale(locale: string): string {
  return LOCALE_MAP[locale] ?? locale;
}

/**
 * Build a stable set of formatters bound to the current next-intl locale.
 * Keeps `XAF` as default currency until the backend exposes a per-tenant value.
 */
export function useFormatters(currency: string = "XAF") {
  const locale = toIntlLocale(useLocale());

  return {
    currency: (n: number | string | null | undefined): string => {
      if (n === null || n === undefined) return "—";
      const num = typeof n === "string" ? parseFloat(n) : n;
      if (Number.isNaN(num)) return "—";
      try {
        return new Intl.NumberFormat(locale, {
          style: "currency",
          currency,
          minimumFractionDigits: 0,
          maximumFractionDigits: 0,
        }).format(num);
      } catch {
        return `${num.toLocaleString(locale)} ${currency}`;
      }
    },
    date: (d: string | Date | null | undefined, opts?: Intl.DateTimeFormatOptions): string => {
      if (!d) return "—";
      const date = typeof d === "string" ? new Date(d) : d;
      if (Number.isNaN(date.getTime())) return "—";
      return date.toLocaleDateString(
        locale,
        opts ?? { day: "2-digit", month: "short", year: "numeric" }
      );
    },
    longDate: (d: string | Date | null | undefined): string => {
      if (!d) return "—";
      const date = typeof d === "string" ? new Date(d) : d;
      if (Number.isNaN(date.getTime())) return "—";
      return date.toLocaleDateString(locale, {
        weekday: "long",
        day: "numeric",
        month: "long",
        year: "numeric",
      });
    },
    dayMonth: (d: string | Date | null | undefined): { day: string; month: string } => {
      if (!d) return { day: "—", month: "" };
      const date = typeof d === "string" ? new Date(d) : d;
      if (Number.isNaN(date.getTime())) return { day: "—", month: "" };
      return {
        day: date.toLocaleDateString(locale, { day: "numeric" }),
        month: date.toLocaleDateString(locale, { month: "short" }),
      };
    },
  };
}
