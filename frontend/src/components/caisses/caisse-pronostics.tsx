"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  Banknote,
  Percent,
  Info,
  ChevronDown,
  ChevronRight,
  CheckCircle2,
  Clock,
} from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/empty-state";
import { caissesApi, type CaisseProjection } from "@/lib/api";
import { useFormatters } from "@/lib/format";
import { formatDate } from "@/lib/utils";
import { cn } from "@/lib/utils";

export function CaissePronostics({
  caisseId,
  currency,
}: {
  caisseId: string;
  currency?: string | null;
}) {
  const t = useTranslations("caissePronostics");
  const fmt = useFormatters(currency ?? undefined);
  const [openLoan, setOpenLoan] = useState<string | null>(null);

  const { data, isLoading } = useQuery<CaisseProjection>({
    queryKey: ["caisse", caisseId, "projections"],
    queryFn: () => caissesApi.projections(caisseId),
    enabled: !!caisseId,
  });

  if (isLoading || !data) return <Skeleton className="h-48 w-full rounded-xl" />;

  const kept = data.interest_distribution === "kept";

  return (
    <div className="space-y-4">
      {/* Bandeau : mode de distribution des intérêts */}
      <div
        className={cn(
          "flex items-start gap-2 rounded-lg border px-3 py-2 text-sm",
          kept
            ? "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900/40 dark:bg-amber-900/15 dark:text-amber-300"
            : "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900/40 dark:bg-emerald-900/15 dark:text-emerald-300",
        )}
      >
        <Info className="mt-0.5 h-4 w-4 shrink-0" />
        <span>{kept ? t("modeKept") : t("modeShared")}</span>
      </div>

      {/* Totaux : capital prêté, intérêts encaissés, intérêts à venir */}
      <div className="grid gap-3 sm:grid-cols-3">
        <StatCard icon={Banknote} label={t("activePrincipal")} value={fmt.currency(data.total_principal_active)} />
        <StatCard icon={CheckCircle2} label={t("collectedInterest")} value={fmt.currency(data.total_interest_collected)} accent="emerald" />
        <StatCard icon={Clock} label={t("upcomingInterest")} value={fmt.currency(data.total_interest_upcoming)} accent="sky" />
      </div>

      {/* Ma part */}
      {data.my && (
        <Card className="border-primary/30">
          <CardContent className="flex flex-wrap items-center gap-x-6 gap-y-2 p-4">
            <div className="flex items-center gap-2 font-medium">
              <Percent className="h-4 w-4 text-primary" />
              {t("myShare")}
            </div>
            <span className="text-sm text-muted-foreground">
              {t("myApport")}: <span className="font-medium text-foreground">{fmt.currency(data.my.apport_cum)}</span> ({data.my.weight_pct}%)
            </span>
            <span className="text-sm">
              {t("myCollected")}:{" "}
              <span className="font-semibold text-emerald-600 dark:text-emerald-400">
                {fmt.currency(data.my.interest_collected_share)}
              </span>
            </span>
            <span className="ml-auto text-sm">
              {t("myUpcoming")}:{" "}
              <span className="text-lg font-semibold text-sky-600 dark:text-sky-400">
                {fmt.currency(data.my.interest_upcoming_share)}
              </span>
            </span>
          </CardContent>
        </Card>
      )}

      {/* Prêts financés par la caisse (chaque prêt dépliable → échéancier) */}
      <div className="space-y-2">
        <h3 className="text-sm font-semibold">{t("loansTitle")}</h3>
        {data.loans.length === 0 ? (
          <EmptyState icon={Banknote} title={t("noLoans")} description={t("noLoansDesc")} />
        ) : (
          <div className="space-y-2">
            {data.loans.map((l) => {
              const open = openLoan === l.loan_id;
              return (
                <Card key={l.loan_id}>
                  <CardContent className="p-0">
                    <button
                      type="button"
                      onClick={() => setOpenLoan(open ? null : l.loan_id)}
                      className="flex w-full flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 text-left"
                    >
                      {open ? <ChevronDown className="h-4 w-4 shrink-0" /> : <ChevronRight className="h-4 w-4 shrink-0" />}
                      <span className="font-mono text-xs">{l.reference}</span>
                      <span className="min-w-0 flex-1 truncate text-sm text-muted-foreground">{l.borrower_name || "—"}</span>
                      <span className="text-xs text-muted-foreground">{t("colPrincipal")}: {fmt.currency(l.principal)}</span>
                      <Badge variant="secondary" className="text-[10px]">{t("rentab")} {l.rentability_pct}%</Badge>
                      <span className="text-xs text-emerald-600 dark:text-emerald-400">{t("collectedShort")}: {fmt.currency(l.interest_collected)}</span>
                      <span className="text-xs text-sky-600 dark:text-sky-400">{t("upcomingShort")}: {fmt.currency(l.interest_upcoming)}</span>
                    </button>
                    {open && (
                      <div className="border-t px-4 py-2">
                        <ScheduleTable schedule={l.schedule} fmt={fmt} t={t} />
                      </div>
                    )}
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </div>

      {/* Échéancier consolidé (tous prêts) par date */}
      {data.timeline.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold">{t("timelineTitle")}</h3>
          <Card>
            <CardContent className="p-3">
              <ScheduleTable schedule={data.timeline} fmt={fmt} t={t} />
            </CardContent>
          </Card>
        </div>
      )}

      {/* Répartition par contributeur — VISIBLE PAR TOUS */}
      {data.contributors.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold">{t("contributorsTitle")}</h3>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] text-sm">
              <thead>
                <tr className="border-b text-left text-xs text-muted-foreground">
                  <th className="py-2 pr-3 font-medium">{t("colMember")}</th>
                  <th className="py-2 pr-3 text-right font-medium">{t("colApport")}</th>
                  <th className="py-2 pr-3 text-right font-medium">{t("colWeight")}</th>
                  <th className="py-2 pr-3 text-right font-medium">{t("colCollected")}</th>
                  <th className="py-2 text-right font-medium">{t("colUpcoming")}</th>
                </tr>
              </thead>
              <tbody>
                {data.contributors.map((c) => {
                  const mine = data.my && c.membership_id === data.my.membership_id;
                  return (
                    <tr key={c.membership_id} className={cn("border-b last:border-0", mine && "bg-primary/5")}>
                      <td className="py-2 pr-3">
                        {c.member_name || "—"}
                        {mine && <Badge variant="outline" className="ml-2 text-[10px]">{t("me")}</Badge>}
                      </td>
                      <td className="py-2 pr-3 text-right tabular-nums">{fmt.currency(c.apport_cum)}</td>
                      <td className="py-2 pr-3 text-right tabular-nums">{c.weight_pct}%</td>
                      <td className="py-2 pr-3 text-right tabular-nums text-emerald-600 dark:text-emerald-400">
                        {fmt.currency(c.interest_collected_share)}
                      </td>
                      <td className="py-2 text-right tabular-nums text-sky-600 dark:text-sky-400">
                        {fmt.currency(c.interest_upcoming_share)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function ScheduleTable({
  schedule,
  fmt,
  t,
}: {
  schedule: { due_on: string; interest: number; collected: boolean }[];
  fmt: ReturnType<typeof useFormatters>;
  t: ReturnType<typeof useTranslations>;
}) {
  if (schedule.length === 0) {
    return <p className="py-2 text-center text-xs text-muted-foreground">{t("noSchedule")}</p>;
  }
  return (
    <table className="w-full text-sm">
      <tbody>
        {schedule.map((e, i) => (
          <tr key={i} className="border-b last:border-0">
            <td className="py-1.5 pr-3">{formatDate(e.due_on)}</td>
            <td className="py-1.5 pr-3">
              {e.collected ? (
                <span className="inline-flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400">
                  <CheckCircle2 className="h-3 w-3" /> {t("collectedShort")}
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 text-xs text-sky-600 dark:text-sky-400">
                  <Clock className="h-3 w-3" /> {t("upcomingShort")}
                </span>
              )}
            </td>
            <td className="py-1.5 text-right tabular-nums font-medium">{fmt.currency(e.interest)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  accent,
}: {
  icon: typeof Banknote;
  label: string;
  value: string;
  accent?: "emerald" | "sky";
}) {
  const cls =
    accent === "emerald"
      ? "text-emerald-600 dark:text-emerald-400"
      : accent === "sky"
        ? "text-sky-600 dark:text-sky-400"
        : "text-primary";
  return (
    <Card>
      <CardContent className="flex items-center gap-3 p-4">
        <Icon className={cn("h-6 w-6 shrink-0", cls)} />
        <div className="min-w-0">
          <p className="truncate text-xs text-muted-foreground">{label}</p>
          <p className="text-lg font-semibold">{value}</p>
        </div>
      </CardContent>
    </Card>
  );
}
