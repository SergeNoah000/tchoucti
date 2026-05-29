"use client";

import { useMemo } from "react";
import { useLocale } from "next-intl";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { CURRENCIES } from "@/lib/currencies";

const LOCALE_MAP: Record<string, string> = { fr: "fr-FR", en: "en-US", de: "de-DE" };

export function CurrencySelect({
  value,
  onValueChange,
  id,
  disabled,
}: {
  value: string;
  onValueChange: (v: string) => void;
  id?: string;
  disabled?: boolean;
}) {
  const locale = LOCALE_MAP[useLocale()] ?? "en-US";
  const names = useMemo(() => new Intl.DisplayNames([locale], { type: "currency" }), [locale]);

  return (
    <Select value={value} onValueChange={onValueChange} disabled={disabled}>
      <SelectTrigger id={id}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {CURRENCIES.map((c) => (
          <SelectItem key={c.code} value={c.code}>
            <span className="font-medium">{c.code}</span>
            <span className="text-muted-foreground"> — {names.of(c.code) ?? c.code}</span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
