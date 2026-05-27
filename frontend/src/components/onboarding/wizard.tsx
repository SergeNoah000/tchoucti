"use client";

import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

export interface WizardStep {
  key: string;
  title: string;
  hint?: string;
  required?: boolean;
}

/**
 * Horizontal step indicator with done / current / pending visuals. Lives
 * above the wizard step body. Keeps the user oriented and shows which
 * steps remain.
 */
export function StepIndicator({
  steps,
  currentIndex,
}: {
  steps: WizardStep[];
  currentIndex: number;
}) {
  return (
    <ol className="flex items-center gap-2 overflow-x-auto pb-2">
      {steps.map((s, i) => {
        const done = i < currentIndex;
        const current = i === currentIndex;
        return (
          <li key={s.key} className="flex shrink-0 items-center gap-2">
            <div
              className={cn(
                "flex h-8 w-8 items-center justify-center rounded-full border-2 text-xs font-bold transition-colors",
                done && "border-primary bg-primary text-primary-foreground",
                current && "border-primary bg-background text-primary",
                !done && !current && "border-border bg-background text-muted-foreground",
              )}
            >
              {done ? <Check className="h-4 w-4" /> : i + 1}
            </div>
            <div className="flex flex-col">
              <span
                className={cn(
                  "text-sm font-medium",
                  current ? "text-foreground" : done ? "text-muted-foreground" : "text-muted-foreground/70",
                )}
              >
                {s.title}
              </span>
              {s.required && (
                <span className="text-[10px] uppercase tracking-wide text-destructive/70">
                  Obligatoire
                </span>
              )}
            </div>
            {i < steps.length - 1 && (
              <div
                className={cn(
                  "mx-2 h-px w-8 shrink-0",
                  done ? "bg-primary" : "bg-border",
                )}
              />
            )}
          </li>
        );
      })}
    </ol>
  );
}

/**
 * Wizard chrome: card with header + body + footer (back / skip / next).
 * Step content is the children. Buttons are wired from the parent because
 * each step has different validation logic.
 */
export function WizardCard({
  title,
  description,
  children,
  footer,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
  footer: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-border bg-card shadow-sm">
      <div className="border-b border-border px-6 py-5">
        <h2 className="text-xl font-bold tracking-tight">{title}</h2>
        {description && (
          <p className="mt-1 text-sm text-muted-foreground">{description}</p>
        )}
      </div>
      <div className="space-y-6 px-6 py-6">{children}</div>
      <div className="flex items-center justify-between gap-3 border-t border-border bg-muted/30 px-6 py-4">
        {footer}
      </div>
    </div>
  );
}
