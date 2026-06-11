"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  CalendarClock,
  CheckCircle2,
  HandCoins,
  HeartHandshake,
  ListChecks,
  Wallet,
} from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { meetingsApi } from "@/lib/api";
import { useFormatters } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { MeetingPrep } from "@/lib/types";

/**
 * Panneau « Préparez votre séance » — rappel de la prochaine séance, des
 * éléments financiers attendus, et des actions en attente pour le bureau.
 * Affiché sur le tableau de bord membre comme bureau/admin.
 */
export function MeetingPrepCard({
  associationId,
  currency,
}: {
  associationId?: string;
  currency?: string;
}) {
  const t = useTranslations("meetingPrep");
  const fmt = useFormatters(currency);

  const { data, isLoading } = useQuery<MeetingPrep>({
    queryKey: ["meeting-prep", associationId],
    queryFn: () => meetingsApi.prep(associationId!),
    enabled: !!associationId,
  });

  if (!associationId || isLoading || !data) return null;
  // Rien à préparer : pas de séance à venir et aucune action en attente.
  const hasActions =
    data.pending_aids + data.aids_to_pay + data.pending_loans + data.loans_to_disburse + data.repayments_due > 0;
  if (!data.next_meeting && !hasActions && data.expected_activities.length === 0) return null;

  const nm = data.next_meeting;
  // Urgence : J-1 ou jour même → ton ambre ; sinon neutre.
  const urgent = nm != null && nm.days_until <= 1;

  const countdownLabel = (days: number) => {
    if (days < 0) return t("overdue", { days: Math.abs(days) });
    if (days === 0) return t("today");
    if (days === 1) return t("tomorrow");
    return t("inDays", { days });
  };

  const actionItems: { key: string; icon: typeof HandCoins; count: number; label: string; href: string }[] = [
    { key: "pending_aids", icon: HeartHandshake, count: data.pending_aids, label: t("pendingAids"), href: "/dashboard/social-aid" },
    { key: "aids_to_pay", icon: HeartHandshake, count: data.aids_to_pay, label: t("aidsToPay"), href: "/dashboard/social-aid" },
    { key: "pending_loans", icon: HandCoins, count: data.pending_loans, label: t("pendingLoans"), href: "/dashboard/loans" },
    { key: "loans_to_disburse", icon: HandCoins, count: data.loans_to_disburse, label: t("loansToDisburse"), href: "/dashboard/loans" },
    { key: "repayments_due", icon: Wallet, count: data.repayments_due, label: t("repaymentsDue"), href: "/dashboard/loans" },
  ].filter((it) => it.count > 0);

  return (
    <Card className={cn(urgent && "border-amber-300 dark:border-amber-700")}>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <CalendarClock className={cn("h-5 w-5", urgent ? "text-amber-600 dark:text-amber-400" : "text-primary")} />
          {t("title")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Prochaine séance */}
        {nm ? (
          <div
            className={cn(
              "flex items-center justify-between gap-3 rounded-lg border p-3",
              urgent ? "border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30" : "border-border bg-muted/30",
            )}
          >
            <div className="min-w-0">
              <p className="truncate font-medium">{nm.title}</p>
              <p className="text-xs text-muted-foreground">{fmt.date(nm.scheduled_on)}</p>
            </div>
            <div className="flex shrink-0 flex-col items-end gap-1.5">
              <Badge variant={urgent ? "warning" : "secondary"}>{countdownLabel(nm.days_until)}</Badge>
              <Button asChild size="sm" variant="ghost" className="h-7 px-2 text-xs">
                <Link href={`/dashboard/meetings/${nm.id}`}>{t("open")}</Link>
              </Button>
            </div>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">{t("noUpcoming")}</p>
        )}

        {/* Éléments financiers attendus */}
        {data.expected_activities.length > 0 && (
          <div>
            <p className="mb-2 flex items-center gap-1.5 text-sm font-medium">
              <ListChecks className="h-4 w-4 text-muted-foreground" />
              {t("expectedTitle")}
            </p>
            <ul className="space-y-1">
              {data.expected_activities.map((a, i) => (
                <li key={i} className="flex items-center justify-between gap-2 text-sm">
                  <span className="flex items-center gap-1.5 truncate">
                    <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                    <span className="truncate">{a.name}</span>
                    {a.is_required && (
                      <Badge variant="outline" className="text-[10px]">{t("required")}</Badge>
                    )}
                  </span>
                  {a.amount != null && a.amount > 0 && (
                    <span className="shrink-0 tabular-nums text-muted-foreground">{fmt.currency(a.amount)}</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Actions en attente (bureau) */}
        {data.is_bureau && actionItems.length > 0 && (
          <div>
            <p className="mb-2 text-sm font-medium">{t("actionsTitle")}</p>
            <div className="flex flex-wrap gap-2">
              {actionItems.map((it) => (
                <Button key={it.key} asChild size="sm" variant="outline" className="h-8 gap-1.5">
                  <Link href={it.href}>
                    <it.icon className="h-3.5 w-3.5" />
                    {it.label}
                    <Badge variant="brand" className="ml-0.5 text-[10px]">{it.count}</Badge>
                  </Link>
                </Button>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
