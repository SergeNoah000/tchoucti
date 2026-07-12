"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  Banknote,
  Info,
  ChevronDown,
  ChevronRight,
  CheckCircle2,
  Clock,
  Coins,
  TrendingUp,
  Users,
  CalendarClock,
} from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/common/empty-state";
import { caissesApi, type CaisseProjection, type LoanDetailProjection } from "@/lib/api";
import { useFormatters } from "@/lib/format";
import { formatDate, cn } from "@/lib/utils";

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
  const hasMine = data.my_apport > 0 || data.my_expected_return > 0;
  const cur = data.currency ?? currency ?? "";

  return (
    <div className="space-y-4">
      {/* Texte d'intro explicatif */}
      <p className="text-sm text-muted-foreground">{t("intro")}</p>

      {/* Mode de distribution */}
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

      {/* Mon résumé */}
      {hasMine && (
        <Card className="border-primary/30">
          <CardContent className="space-y-2 p-4">
            <div className="grid gap-3 sm:grid-cols-4">
              <Mini label={t("myApport")} value={fmt.currency(data.my_apport)} help={t("myApportHelp")} />
              <Mini label={t("myCollected")} value={fmt.currency(data.my_collected)} accent="emerald" help={t("myCollectedHelp")} />
              <Mini label={t("myUpcoming")} value={fmt.currency(data.my_upcoming)} accent="sky" help={t("myUpcomingHelp")} />
              <Mini label={t("myAtCassation")} value={fmt.currency(data.my_expected_at_cassation)} accent strong help={t("myAtCassationHelp")} />
            </div>
          </CardContent>
        </Card>
      )}

      {/* Totaux caisse */}
      <div className="grid gap-3 sm:grid-cols-3">
        <StatCard icon={Banknote} label={t("activePrincipal")} value={fmt.currency(data.total_principal_active)} />
        <StatCard icon={CheckCircle2} label={t("collectedInterest")} value={fmt.currency(data.total_interest_collected)} accent="emerald" />
        <StatCard icon={Clock} label={t("upcomingInterest")} value={fmt.currency(data.total_interest_upcoming)} accent="sky" />
      </div>

      {/* Prêts (collapse par prêt) */}
      <div className="space-y-2">
        <h3 className="text-sm font-semibold">{t("loansTitle")}</h3>
        {data.loans.length === 0 ? (
          <EmptyState icon={Banknote} title={t("noLoans")} description={t("noLoansDesc")} />
        ) : (
          <div className="space-y-2">
            {data.loans.map((l) => (
              <LoanRow
                key={l.loan_id}
                loan={l}
                open={openLoan === l.loan_id}
                onToggle={() => setOpenLoan(openLoan === l.loan_id ? null : l.loan_id)}
                isAdmin={data.is_admin_view}
                cur={cur}
                fmt={fmt}
                t={t}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function LoanRow({
  loan: l,
  open,
  onToggle,
  isAdmin,
  cur,
  fmt,
  t,
}: {
  loan: LoanDetailProjection;
  open: boolean;
  onToggle: () => void;
  isAdmin: boolean;
  cur: string;
  fmt: ReturnType<typeof useFormatters>;
  t: ReturnType<typeof useTranslations>;
}) {
  // Montants « par unité » (fractions) → 2 décimales, indépendamment de la devise.
  const perUnit = (v: number) =>
    `${v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 3 })}${cur ? " " + cur : ""}`;
  const interestPerLent = l.principal > 0 ? l.total_interest / l.principal : 0;

  return (
    <Card>
      <CardContent className="p-0">
        <button
          type="button"
          onClick={onToggle}
          className="flex w-full flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 text-left"
        >
          {open ? <ChevronDown className="h-4 w-4 shrink-0" /> : <ChevronRight className="h-4 w-4 shrink-0" />}
          <span className="font-mono text-xs">{l.reference}</span>
          <span className="min-w-0 flex-1 truncate text-sm text-muted-foreground">{l.borrower_name || "—"}</span>
          <span className="text-xs text-muted-foreground">{t("lentAmount")}: {fmt.currency(l.principal)}</span>
          {l.my_amount_at_loan > 0 && (
            <span className="text-xs font-medium text-primary">
              {t("myPart")}: {fmt.currency(l.my_expected_return)}
            </span>
          )}
        </button>

        {open && (
          <div className="space-y-3 border-t px-4 py-3">
            {/* Faits du prêt, en langage simple */}
            <div className="grid gap-2 sm:grid-cols-2">
              <PlainFact
                icon={Banknote}
                title={t("factLentTitle")}
                value={fmt.currency(l.principal)}
                help={t("factLentHelp")}
              />
              <PlainFact
                icon={CalendarClock}
                title={t("factMonthsTitle")}
                value={t("factMonthsValue", { n: l.remaining_installments })}
                help={t("factMonthsHelp")}
              />
              <PlainFact
                icon={TrendingUp}
                title={t("factRapportTitle")}
                value={t("factRapportValue", { amount: perUnit(interestPerLent) })}
                help={t("factRapportHelp", { pct: l.rentability_pct })}
              />
              <PlainFact
                icon={Coins}
                title={t("factRevenueTitle")}
                value={t("factRevenueValue", { amount: perUnit(l.revenue_per_unit_invested) })}
                help={t("factRevenueHelp")}
                accent
              />
            </div>

            {/* Ma part sur ce prêt */}
            {l.my_amount_at_loan > 0 && (
              <div className="rounded-lg bg-primary/5 px-3 py-2 text-sm">
                <p className="font-medium">{t("myPartOnLoan")}</p>
                <p className="mt-0.5 text-muted-foreground">
                  {t("myPartExplain", {
                    amount: fmt.currency(l.my_amount_at_loan),
                    pct: l.my_share_pct,
                    total: fmt.currency(l.total_at_loan),
                  })}
                </p>
                <p className="mt-1">
                  {t("colUpcoming")}: <b className="text-sky-600 dark:text-sky-400">{fmt.currency(l.my_upcoming)}</b>
                  {" · "}
                  {t("colCollected")}: <b className="text-emerald-600 dark:text-emerald-400">{fmt.currency(l.my_collected)}</b>
                </p>
              </div>
            )}

            {/* Échéancier avec MA part */}
            {l.my_schedule.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[440px] text-sm">
                  <thead>
                    <tr className="border-b text-left text-xs text-muted-foreground">
                      <th className="py-1.5 pr-3 font-medium">{t("colDate")}</th>
                      <th className="py-1.5 pr-3 font-medium">{t("colStatus")}</th>
                      <th className="py-1.5 pr-3 text-right font-medium">{t("colInterestTotal")}</th>
                      <th className="py-1.5 text-right font-medium">{t("colMyShare")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {l.my_schedule.map((e, i) => (
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
                        <td className="py-1.5 pr-3 text-right tabular-nums text-muted-foreground">{fmt.currency(e.interest_total)}</td>
                        <td className="py-1.5 text-right tabular-nums font-medium">{fmt.currency(e.my_share)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Admin : répartition par contributeur sur ce prêt */}
            {isAdmin && l.contributors.length > 0 && (
              <div className="space-y-1.5">
                <p className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground">
                  <Users className="h-3.5 w-3.5" /> {t("contributorsOnLoan")}
                </p>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[520px] text-sm">
                    <thead>
                      <tr className="border-b text-left text-xs text-muted-foreground">
                        <th className="py-1.5 pr-3 font-medium">{t("colMember")}</th>
                        <th className="py-1.5 pr-3 text-right font-medium">{t("colAmountAtLoan")}</th>
                        <th className="py-1.5 pr-3 text-right font-medium">{t("colShare")}</th>
                        <th className="py-1.5 pr-3 text-right font-medium">{t("colCollected")}</th>
                        <th className="py-1.5 text-right font-medium">{t("colUpcoming")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {l.contributors.map((c) => (
                        <tr key={c.membership_id} className="border-b last:border-0">
                          <td className="py-1.5 pr-3">{c.member_name || "—"}</td>
                          <td className="py-1.5 pr-3 text-right tabular-nums">{fmt.currency(c.amount_at_loan)}</td>
                          <td className="py-1.5 pr-3 text-right tabular-nums">{c.share_pct}%</td>
                          <td className="py-1.5 pr-3 text-right tabular-nums text-emerald-600 dark:text-emerald-400">{fmt.currency(c.collected)}</td>
                          <td className="py-1.5 text-right tabular-nums text-sky-600 dark:text-sky-400">{fmt.currency(c.upcoming)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function PlainFact({
  icon: Icon,
  title,
  value,
  help,
  accent,
}: {
  icon: typeof Banknote;
  title: string;
  value: string;
  help: string;
  accent?: boolean;
}) {
  return (
    <div className="flex gap-2.5 rounded-lg border border-border/50 px-3 py-2">
      <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", accent ? "text-emerald-600 dark:text-emerald-400" : "text-muted-foreground")} />
      <div className="min-w-0">
        <p className="text-xs font-medium text-muted-foreground">{title}</p>
        <p className={cn("font-semibold", accent && "text-emerald-700 dark:text-emerald-400")}>{value}</p>
        <p className="mt-0.5 text-[11px] leading-snug text-muted-foreground">{help}</p>
      </div>
    </div>
  );
}

function Mini({ label, value, accent, strong, help }: { label: string; value: string; accent?: "emerald" | "sky" | boolean; strong?: boolean; help?: string }) {
  const cls =
    accent === "emerald" ? "text-emerald-600 dark:text-emerald-400"
      : accent === "sky" ? "text-sky-600 dark:text-sky-400"
        : accent ? "text-primary" : "";
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={cn("font-semibold tabular-nums", strong ? "text-lg" : "text-base", cls)}>{value}</p>
      {help && <p className="mt-0.5 text-[11px] leading-snug text-muted-foreground">{help}</p>}
    </div>
  );
}

function StatCard({ icon: Icon, label, value, accent }: { icon: typeof Banknote; label: string; value: string; accent?: "emerald" | "sky" }) {
  const cls = accent === "emerald" ? "text-emerald-600 dark:text-emerald-400" : accent === "sky" ? "text-sky-600 dark:text-sky-400" : "text-primary";
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
