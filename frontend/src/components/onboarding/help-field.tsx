"use client";

import { Info, Lightbulb } from "lucide-react";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

/**
 * Field wrapper that surfaces help + a concrete example next to the label,
 * not behind a tooltip. Used throughout config screens so admins (often
 * non-technical) understand *what* each field controls before filling it in.
 *
 * The example renders only when provided — keep examples concrete (numbers,
 * names) so the user can pattern-match to their own situation.
 */
export function HelpField({
  label,
  hint,
  example,
  required,
  children,
  className,
}: {
  label: string;
  hint?: string;
  example?: string;
  required?: boolean;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("space-y-1.5", className)}>
      <Label className="flex items-center gap-1">
        {label}
        {required && <span className="text-destructive">*</span>}
      </Label>
      {children}
      {hint && (
        <p className="flex gap-1.5 text-xs text-muted-foreground">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>{hint}</span>
        </p>
      )}
      {example && (
        <p className="flex gap-1.5 rounded-md bg-amber-50 px-2 py-1.5 text-xs text-amber-900 dark:bg-amber-900/15 dark:text-amber-300">
          <Lightbulb className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>{example}</span>
        </p>
      )}
    </div>
  );
}

/**
 * Callout to summarise what a config block will actually do — surfaces the
 * downstream behavior in plain language so the admin can validate her mental
 * model before saving.
 */
export function ConfigPreview({
  children,
  intent = "info",
}: {
  children: React.ReactNode;
  intent?: "info" | "success" | "warning";
}) {
  const tone =
    intent === "success"
      ? "border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-900/40 dark:bg-emerald-900/20 dark:text-emerald-200"
      : intent === "warning"
        ? "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900/40 dark:bg-amber-900/20 dark:text-amber-200"
        : "border-sky-200 bg-sky-50 text-sky-900 dark:border-sky-900/40 dark:bg-sky-900/20 dark:text-sky-200";
  return (
    <div className={cn("rounded-lg border px-3 py-2.5 text-sm leading-relaxed", tone)}>
      {children}
    </div>
  );
}
