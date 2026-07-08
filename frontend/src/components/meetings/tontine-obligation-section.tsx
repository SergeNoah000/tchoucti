"use client";

import { useState } from "react";
import { CircleSlash, AlertTriangle } from "lucide-react";

import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { cn } from "@/lib/utils";
import type { useFormatters } from "@/lib/format";
import type { useTranslations } from "next-intl";

interface AgendaRow {
  activity_id: string;
  label: string;
  default_amount: number;
  is_required: boolean;
  context: Record<string, unknown>;
}

/**
 * Section « action tontine » d'un membre en séance. Chaque tontine EXIGE une
 * décision explicite du saisisseur : « a tout donné » (toggle → montant plein),
 * un montant partiel (saisie), ou « rien donné » (0, confirmé par un modal).
 * Tant qu'une tontine n'est pas décidée, elle apparaît « à décider » et bloque
 * l'enregistrement du membre (cf. MemberRow).
 */
export function TontineObligationSection({
  title,
  rows,
  amounts,
  setAmount,
  canEdit,
  fmt,
  t,
}: {
  title: string;
  rows: AgendaRow[];
  amounts: Record<string, string>;
  setAmount: (activityId: string, value: string) => void;
  canEdit: boolean;
  fmt: ReturnType<typeof useFormatters>;
  t: ReturnType<typeof useTranslations>;
}) {
  const [zeroTarget, setZeroTarget] = useState<AgendaRow | null>(null);

  if (rows.length === 0) return null;

  return (
    <div className="space-y-1.5">
      <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{title}</p>
      <div className="grid grid-cols-1 gap-2">
        {rows.map((r) => {
          const raw = (amounts[r.activity_id] ?? "").trim();
          const decided = raw !== "";
          const num = parseInt(raw, 10);
          const full = r.default_amount > 0 ? String(r.default_amount) : "";
          const isFull = decided && r.default_amount > 0 && num === r.default_amount;
          const isZero = decided && num === 0;
          const isPartial = decided && num > 0 && num !== r.default_amount;

          const status = !decided
            ? { label: t("tontineTodo"), cls: "text-destructive" }
            : isFull
              ? { label: t("tontineGaveAll"), cls: "text-emerald-600 dark:text-emerald-400" }
              : isZero
                ? { label: t("tontineGaveNothing"), cls: "text-muted-foreground" }
                : { label: t("tontinePartial"), cls: "text-amber-600 dark:text-amber-400" };

          return (
            <div
              key={`${r.activity_id}-${JSON.stringify(r.context)}`}
              className={cn(
                "rounded-lg border px-3 py-2",
                decided ? "border-border/50 bg-muted/20" : "border-destructive/40 bg-destructive/5",
              )}
            >
              <div className="flex items-center gap-2">
                <span className="min-w-0 flex-1 truncate text-sm">{r.label}</span>
                {!canEdit && (
                  <span className="shrink-0 text-right text-sm tabular-nums">
                    <span className="font-medium">{fmt.currency(decided ? num : 0)}</span>
                    {r.default_amount > 0 && (
                      <span className="text-muted-foreground"> / {fmt.currency(r.default_amount)}</span>
                    )}
                  </span>
                )}
                <span className={cn("flex items-center gap-1 text-[10px] font-semibold uppercase", status.cls)}>
                  {!decided && <AlertTriangle className="h-3 w-3" />}
                  {status.label}
                </span>
              </div>

              {canEdit && (
                <div className="mt-2 flex flex-wrap items-center gap-3">
                  {/* Toggle « a tout donné » → remplit le montant plein */}
                  <label className="flex items-center gap-1.5 text-xs">
                    <Switch
                      checked={isFull}
                      onCheckedChange={(on) => setAmount(r.activity_id, on ? full : "")}
                      disabled={r.default_amount <= 0}
                    />
                    {t("tontineGaveAll")}
                  </label>

                  {/* Saisie d'un montant partiel */}
                  <Input
                    type="number"
                    inputMode="numeric"
                    min={0}
                    value={raw}
                    onChange={(e) => setAmount(r.activity_id, e.target.value)}
                    placeholder={t("tontineAmount")}
                    className="h-8 w-28 text-right text-sm"
                  />

                  {/* « Rien donné » → confirmation modale → 0 */}
                  <Button
                    type="button"
                    size="sm"
                    variant={isZero ? "secondary" : "ghost"}
                    className="h-8 gap-1.5"
                    onClick={() => setZeroTarget(r)}
                  >
                    <CircleSlash className="h-3.5 w-3.5" />
                    {t("tontineNothingBtn")}
                  </Button>

                  {r.default_amount > 0 && (
                    <span className="text-[11px] text-muted-foreground">
                      {t("tontineExpected")}: {fmt.currency(r.default_amount)}
                    </span>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <AlertDialog open={!!zeroTarget} onOpenChange={(o) => !o && setZeroTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("tontineZeroConfirmTitle")}</AlertDialogTitle>
            <AlertDialogDescription>
              {zeroTarget ? t("tontineZeroConfirmDesc", { activity: zeroTarget.label }) : ""}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (zeroTarget) setAmount(zeroTarget.activity_id, "0");
                setZeroTarget(null);
              }}
            >
              {t("tontineZeroConfirmOk")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
