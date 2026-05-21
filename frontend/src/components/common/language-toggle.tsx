"use client";

import { useTransition } from "react";
import { useLocale } from "next-intl";
import { locales, type Locale } from "@/i18n/config";

import { cn } from "@/lib/utils";

export function LanguageToggle({ className }: { className?: string }) {
  const locale = useLocale();
  const [isPending, startTransition] = useTransition();

  const switchTo = (next: Locale) => {
    if (next === locale) return;
    startTransition(() => {
      document.cookie = `NEXT_LOCALE=${next};path=/;max-age=31536000;samesite=lax`;
      window.location.reload();
    });
  };

  return (
    <div
      className={cn(
        "inline-flex items-center rounded-full border border-border bg-muted/50 p-0.5 text-xs font-semibold",
        className
      )}
      role="group"
      aria-label="Language"
    >
      {locales.map((loc) => {
        const active = locale === loc;
        return (
          <button
            key={loc}
            type="button"
            onClick={() => switchTo(loc)}
            disabled={isPending}
            className={cn(
              "rounded-full px-2.5 py-1 transition-colors flex items-center gap-1",
              active
                ? "bg-primary text-primary-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            )}
            aria-pressed={active}
          >
            <span className="uppercase">{loc}</span>
          </button>

        );
      })}
    </div>
  );
}
